"""V24 (06-nov-2026): compras nacionales por OV, cliente o motivo, consolidado por producto y cotizaciones con histórico.

Solicitud de compra nacional:
- puede ser para una OV, para un cliente, o quedar en blanco e indicar el motivo (stock de seguridad, reposición u otro
  que se especifica);
- si se indica OV y cliente, la OV debe ser de ese cliente.

Consolidado por producto (lo ven Compras nacionales y el Gerente General Adjunto). Para cada cliente se juntan lo pedido
por sus OV y lo pedido «para el cliente»:
- si las OV pertenecen al mismo cliente para el que también se pidió, lo pedido para el cliente ya las incluye: se toma
  lo mayor (ejemplo: 1 t por la OV565 y 2 t para «pepito»; si la OV565 es de pepito, se compran 2 t);
- si la OV es de otro cliente, se suma (1 t + 2 t = 3 t);
- al final se suma lo que se pide para stock de seguridad, reposición u otro motivo.

Cotizaciones: Compras nacionales o el Gerente General Adjunto registran tantas como quieran por producto o solicitud,
a mano (origen o mercado, proveedor, fecha estimada de entrega, calidad, precio, moneda, unidad) o con archivo. Todas se
guardan como histórico. Cada cotización se compara (en S/ por la unidad, con el tipo de cambio SUNAT del día si es en
dólares) con el promedio de los últimos 30 días, del último trimestre y del mismo mes del año anterior; si se aparta más
de «compras_alerta_variacion_pct», se alerta.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Customer, Product, PurchaseRequest, SalesOrder, SupplierQuote
from . import alerts
from .core import BusinessError, audit, has_perm, param

CERRADAS = ("RECIBIDA", "RECIBIDA_CON_DIFERENCIAS", "RECIBIDA_BAJO_OBSERVACION", "CERRADA", "RECHAZADA", "CANCELADA",
            "ANULADA")
MOTIVOS = {"STOCK_SEGURIDAD": "Stock de seguridad", "REPOSICION": "Reposición", "OTRO": "Otro"}


def puede_cotizar(user):
    return has_perm(user, "compras.cotizar")


def _orden(numero):
    if not numero:
        return None
    return db().execute(select(SalesOrder).where(SalesOrder.numero == numero.strip())).scalars().first()


def create(user, product_code, cantidad, fecha_necesidad=None, ov="", customer_id=None, motivo_tipo="", motivo="",
           centro_costo=""):
    """Solicitud de compra nacional con su destino: OV, cliente o motivo."""
    from .purchasing import create_request
    o = _orden(ov) if ov else None
    if ov and o is None:
        raise BusinessError(f"No existe la OV {ov}.")
    c = db().get(Customer, int(customer_id)) if customer_id else None
    if o is not None and c is not None and o.customer_id != c.id:
        raise BusinessError(f"La OV {o.numero} es del cliente {o.customer.nombre}, no de {c.nombre}.")
    motivo_tipo = (motivo_tipo or "").strip().upper()
    motivo = (motivo or "").strip()
    if o is None and c is None:
        if motivo_tipo not in MOTIVOS:
            raise BusinessError("Sin OV ni cliente, indique el motivo: stock de seguridad, reposición u otro.")
        if motivo_tipo == "OTRO" and not motivo:
            raise BusinessError("Especifique el motivo («Otro»).")
    origen = "OV" if o is not None else ("CLIENTE" if c is not None else motivo_tipo[:20])
    from .centros_costo import validar
    centro_costo = validar(centro_costo)
    previos = None
    r = create_request(user, product_code, cantidad, fecha_necesidad, "OV" if o is not None else "ALMACEN", o)
    an = dict(r.analisis or {})
    det = list(an.get("destinos") or [])
    if not det and r.cantidad - float(cantidad) > 1e-9:
        # se agrupó en una solicitud anterior sin detalle: se conserva lo que ya tenía como aportes
        previos = _destinos(r, excluir=float(cantidad), excluir_ov=o.numero if o is not None else None)
        det = previos
    if c is not None and r.customer_id is None and not previos:
        r.customer_id = c.id
    if o is None and c is None and not r.motivo_tipo:
        r.motivo_tipo = motivo_tipo
    det.append({"tipo": "OV" if o is not None else ("CLIENTE" if c is not None else motivo_tipo),
                "ov": o.numero if o is not None else "", "customer_id": (o.customer_id if o is not None else (c.id if c else None)),
                "cliente": (o.customer.nombre if o is not None else (c.nombre if c else "")), "cantidad": float(cantidad),
                "motivo": motivo, "user": user.nombre, "fecha": date.today().isoformat()})
    an["destinos"] = det
    if centro_costo and not r.centro_costo:
        r.centro_costo = centro_costo
    r.analisis = an
    audit(user, "COMPRA_NACIONAL_DESTINO", "PurchaseRequest", r.id, det[-1])
    return r


def _destinos(r, excluir=0.0, excluir_ov=None):
    """Aportes de una solicitud: los registrados en V24 o, para las anteriores, los de sus OV y su motivo.
    excluir / excluir_ov: aporte recién agregado que todavía no tiene detalle (no se cuenta dos veces)."""
    det = list((r.analisis or {}).get("destinos") or [])
    if det and not excluir:
        return det
    out = []
    ords = list(r.ordenes or [])
    if excluir_ov:
        for i in range(len(ords) - 1, -1, -1):
            if ords[i].get("numero") == excluir_ov:
                ords.pop(i)
                break
    for x in ords:
        o = _orden(x.get("numero"))
        out.append({"tipo": "OV", "ov": x.get("numero", ""), "customer_id": o.customer_id if o else None,
                    "cliente": o.customer.nombre if o else "", "cantidad": float(x.get("cantidad") or 0), "motivo": ""})
    resto = r.cantidad - excluir - sum(d["cantidad"] for d in out)
    if resto > 1e-9:
        if r.customer_id:
            c = db().get(Customer, r.customer_id)
            out.append({"tipo": "CLIENTE", "ov": "", "customer_id": r.customer_id, "cliente": c.nombre if c else "",
                        "cantidad": resto, "motivo": ""})
        else:
            out.append({"tipo": r.motivo_tipo or "REPOSICION", "ov": "", "customer_id": None, "cliente": "",
                        "cantidad": resto, "motivo": (r.motivo or "")[:120]})
    return out


def consolidado(product_code=None):
    """Por producto: total a comprar con el detalle por cliente (OV y pedido para el cliente) y por motivo."""
    q = select(PurchaseRequest).where(PurchaseRequest.estado.notin_(CERRADAS)).order_by(PurchaseRequest.product_code,
                                                                                       PurchaseRequest.id)
    if product_code:
        q = q.where(PurchaseRequest.product_code == product_code)
    por_prod = defaultdict(list)
    for r in db().execute(q).scalars():
        por_prod[r.product_code].append(r)
    out = []
    for code, reqs in sorted(por_prod.items()):
        p = db().get(Product, code)
        clientes = defaultdict(lambda: {"ovs": [], "ov_total": 0.0, "directo": 0.0, "solicitudes": set()})
        motivos = defaultdict(lambda: {"cantidad": 0.0, "detalle": [], "solicitudes": set()})
        for r in reqs:
            for d in _destinos(r):
                if d["tipo"] in ("OV", "CLIENTE") and d.get("customer_id"):
                    cl = clientes[(d["customer_id"], d["cliente"])]
                    cl["solicitudes"].add(r.id)
                    if d["tipo"] == "OV":
                        cl["ovs"].append({"ov": d["ov"], "cantidad": d["cantidad"], "solicitud": r.id})
                        cl["ov_total"] += d["cantidad"]
                    else:
                        cl["directo"] += d["cantidad"]
                else:
                    m = motivos[d["tipo"] or "REPOSICION"]
                    m["cantidad"] += d["cantidad"]
                    m["solicitudes"].add(r.id)
                    if d.get("motivo"):
                        m["detalle"].append(d["motivo"])
        filas_cli = []
        for (cid, nombre), cl in sorted(clientes.items(), key=lambda kv: kv[0][1]):
            if cl["directo"] and cl["ov_total"]:
                cant = max(cl["directo"], cl["ov_total"])
                ovs = ", ".join(x["ov"] for x in cl["ovs"])
                nota = (f"{'La OV' if len(cl['ovs']) == 1 else 'Las OV'} {ovs} {'es' if len(cl['ovs']) == 1 else 'son'} de "
                        f"{nombre}: ya {'está' if len(cl['ovs']) == 1 else 'están'} dentro de lo pedido para el cliente; se toma "
                        f"{cant:g} (no se suma).")
            else:
                cant = cl["directo"] + cl["ov_total"]
                nota = ""
            filas_cli.append({"customer_id": cid, "cliente": nombre, "ovs": cl["ovs"], "ov_total": round(cl["ov_total"], 3),
                              "directo": round(cl["directo"], 3), "cantidad": round(cant, 3), "nota": nota,
                              "solicitudes": sorted(cl["solicitudes"])})
        filas_mot = [{"motivo": MOTIVOS.get(k, k), "codigo": k, "cantidad": round(v["cantidad"], 3),
                      "detalle": "; ".join(dict.fromkeys(v["detalle"]))[:200], "solicitudes": sorted(v["solicitudes"])}
                     for k, v in sorted(motivos.items())]
        tot_cli = sum(f["cantidad"] for f in filas_cli)
        tot_mot = sum(f["cantidad"] for f in filas_mot)
        pedido = sum(r.cantidad for r in reqs)
        um = (p.um if p else "") or ""
        out.append({"code": code, "descripcion": p.descripcion if p else "",
                    "um": "kg" if um.upper().startswith("K") else um.lower(),
                    "clientes": filas_cli, "motivos": filas_mot, "total_clientes": round(tot_cli, 3),
                    "total_motivos": round(tot_mot, 3), "total": round(tot_cli + tot_mot, 3),
                    "pedido_bruto": round(pedido, 3), "duplicado": round(pedido - tot_cli - tot_mot, 3),
                    "solicitudes": [r.id for r in reqs],
                    # cotizaciones vigentes: las de estas solicitudes o de los últimos 30 días (el resto es histórico)
                    "cotizaciones": [q for q in quotes(code) if set(q.request_ids or []) & {r.id for r in reqs}
                                     or q.fecha >= date.today() - timedelta(days=30)][:8],
                    "n_historico": len(quotes(code))})
    return out


# ------------------------------------------------------------------ cotizaciones e histórico
def _tc(fecha=None):
    from .tipo_cambio import rate
    return rate(fecha)


def precio_soles(q):
    """Precio de la cotización en S/ por su unidad (con el TC guardado o el del día)."""
    if (q.moneda or "PEN").upper() in ("PEN", "S/", "SOLES"):
        return q.precio
    tc = q.tipo_cambio or _tc(q.fecha)
    return q.precio * tc if tc else None


def quotes(product_code):
    return list(db().execute(select(SupplierQuote).where(SupplierQuote.product_code == product_code)
                             .order_by(SupplierQuote.fecha.desc(), SupplierQuote.id.desc())).scalars())


def comparar(q):
    """Precio de la cotización frente al histórico del mismo producto y unidad."""
    ps = precio_soles(q)
    if ps is None:
        return {"precio_soles": None, "comparaciones": [], "alerta": ""}
    hist = [x for x in quotes(q.product_code) if x.id != q.id and (x.um or "").upper() == (q.um or "").upper()]
    tol = float(param("compras_alerta_variacion_pct", 10) or 10)
    f = q.fecha or date.today()
    tramos = [("Últimos 30 días", f - timedelta(days=30), f), ("Último trimestre", f - timedelta(days=90), f),
              ("Mismo mes del año anterior", f - timedelta(days=380), f - timedelta(days=350))]
    comps, avisos = [], []
    for nombre, ini, fin in tramos:
        vals = [precio_soles(x) for x in hist if ini <= x.fecha <= fin and precio_soles(x) is not None]
        if not vals:
            comps.append({"tramo": nombre, "promedio": None, "var_pct": None, "n": 0})
            continue
        prom = sum(vals) / len(vals)
        var = round(100 * (ps - prom) / prom, 1) if prom else None
        comps.append({"tramo": nombre, "promedio": round(prom, 3), "var_pct": var, "n": len(vals)})
        if var is not None and abs(var) > tol:
            avisos.append(f"{'por encima' if var > 0 else 'por debajo'} {abs(var):g} % de {nombre.lower()}")
    return {"precio_soles": round(ps, 3), "comparaciones": comps,
            "alerta": ("Precio " + "; ".join(avisos) + ".") if avisos else ""}


def add_quote(user, product_code, datos, archivo=""):
    if not puede_cotizar(user):
        raise BusinessError("Registran cotizaciones Compras nacionales o el Gerente General Adjunto.")
    p = db().get(Product, (product_code or "").strip().upper())
    if p is None:
        raise BusinessError("Producto no existe.")
    proveedor = (datos.get("proveedor") or "").strip()
    if not proveedor:
        raise BusinessError("Indique el proveedor.")
    try:
        precio = float(str(datos.get("precio") or "").replace(",", "."))
    except ValueError:
        raise BusinessError("Precio inválido.") from None
    if precio <= 0:
        raise BusinessError("Precio inválido.")
    fe = datos.get("fecha_entrega") or None
    if isinstance(fe, str) and fe:
        fe = date.fromisoformat(fe[:10])
    cant = datos.get("cantidad")
    moneda = (datos.get("moneda") or "PEN").upper()
    reqs = [int(x) for x in (datos.get("request_ids") or []) if str(x).isdigit()]
    q = SupplierQuote(product_code=p.code, request_ids=reqs, origen=(datos.get("origen") or "").strip()[:80],
                      proveedor=proveedor[:160], fecha_entrega=fe or None, calidad=(datos.get("calidad") or "").strip()[:160],
                      precio=precio, moneda=moneda, um=(datos.get("um") or p.um or "KG").strip().upper()[:20],
                      cantidad=float(cant) if cant not in (None, "") else None, archivo=archivo or "",
                      observacion=(datos.get("observacion") or "").strip(),
                      tipo_cambio=_tc() if moneda != "PEN" else None, fecha=date.today(), user_id=user.id)
    db().add(q)
    db().flush()
    c = comparar(q)
    if c["alerta"]:
        alerts.emit("COMPRA_PRECIO_VARIACION", f"Cotización {p.code} de {proveedor}: {c['alerta']}",
                    f"{q.precio:g} {q.moneda}/{q.um} (S/ {c['precio_soles']:g}). " +
                    "; ".join(f"{x['tramo']}: S/ {x['promedio']:g}" for x in c["comparaciones"] if x["promedio"]),
                    "SupplierQuote", q.id, dedup_key=f"PRECIO:{q.id}", creado_por=user)
    audit(user, "COTIZACION_REGISTRADA", "SupplierQuote", q.id, {"producto": p.code, "proveedor": proveedor, "precio": precio,
                                                                 "moneda": moneda, "solicitudes": reqs})
    return q, c


def choose(user, q):
    if not puede_cotizar(user):
        raise BusinessError("Elige la cotización Compras nacionales o el Gerente General Adjunto.")
    for x in quotes(q.product_code):
        if set(x.request_ids or []) & set(q.request_ids or []) or not q.request_ids:
            x.elegida = False
    q.elegida = True
    for rid in q.request_ids or []:
        r = db().get(PurchaseRequest, rid)
        if r is not None and r.estado not in CERRADAS:
            r.proveedor, r.precio = q.proveedor, precio_soles(q)
            r.cotizacion = f"{q.proveedor} · {q.precio:g} {q.moneda}/{q.um} · entrega {q.fecha_entrega or '-'} · {q.calidad}"
    audit(user, "COTIZACION_ELEGIDA", "SupplierQuote", q.id, {"solicitudes": q.request_ids})
    return q


def historial(product_code, meses=12):
    """Serie mensual del precio promedio cotizado (S/ por unidad) para el gráfico."""
    desde = date.today() - timedelta(days=31 * meses)
    acc = defaultdict(list)
    for q in quotes(product_code):
        if q.fecha >= desde and precio_soles(q) is not None:
            acc[f"{q.fecha:%Y-%m}"].append(precio_soles(q))
    return [(m, round(sum(v) / len(v), 3)) for m, v in sorted(acc.items())]
