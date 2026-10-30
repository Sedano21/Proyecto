"""Módulo de oportunidades (ronda 23-oct-2026; reemplaza el de SAP): acciones con el cliente (visita, llamada, reunión
virtual, mensajería, carta u oficio), oportunidades con productos de interés y proyección mensual, cotizaciones (oferta de
venta) y funnel. El prospecto pasa a cliente con al menos una acción registrada y su orden de compra."""
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import func, select

from ..db import db
from ..models import CustomerAction, Opportunity, Quote, now
from .core import BusinessError, audit, has_perm, param

ESTADOS = {"ABIERTA": "Abierta", "COTIZADA": "Cotizada", "NEGOCIACION": "En negociación", "GANADA": "Ganada",
           "PERDIDA": "Perdida"}
ORDEN_FUNNEL = ["ABIERTA", "COTIZADA", "NEGOCIACION", "GANADA"]


def _require(user):
    if not has_perm(user, "oportunidades.registrar"):
        raise BusinessError("Registran oportunidades los ejecutivos, el coordinador y el jefe comercial.")


def _own(user, customer=None, opp=None):
    if has_perm(user, "oportunidades.ver_todas"):
        return
    vid = (opp.vendedor_id if opp is not None else None) or (customer.vendedor_id if customer is not None else None)
    if vid not in (None, user.id):
        raise BusinessError("Solo puede gestionar sus propios clientes y oportunidades.")


def _num(v):
    v = str(v or "").replace(",", "").strip()
    return float(v) if v else None


def save_opportunity(user, customer, datos, opp=None):
    _require(user)
    _own(user, customer, opp)
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        raise BusinessError("Indique un título para la oportunidad (p. ej. «Ingreso de quinua 5 kg a la cadena»).")
    nuevo = opp is None
    if nuevo:
        opp = Opportunity(customer_id=customer.id, vendedor_id=user.id if user.role_code == "EJECUTIVO_VENTAS" else
                          (customer.vendedor_id or user.id), titulo=titulo,
                          tipo="NUEVO" if customer.es_prospecto else "ADICIONAL")
        db().add(opp)
    opp.titulo = titulo
    # V7: varios productos del catálogo (se guarda el código; el texto libre se conserva si no es un código)
    vals = datos.getlist("productos") if hasattr(datos, "getlist") else [datos.get("productos") or ""]
    # V13: proyección por producto (kg y S/ por mes en cada fila); el total de la oportunidad es la suma
    kgs = datos.getlist("prod_kg") if hasattr(datos, "getlist") else []
    sols = datos.getlist("prod_soles") if hasattr(datos, "getlist") else []
    from ..models import Product
    prods, detalle = [], []
    for i, v in enumerate(vals):
        for x in str(v or "").split(","):
            x = x.strip()
            code = x.split(" ")[0].upper() if x else ""
            item = code if code and db().get(Product, code) is not None else x
            if item and item not in prods:
                prods.append(item)
                kg, so = _num(kgs[i] if i < len(kgs) else None), _num(sols[i] if i < len(sols) else None)
                if (kg is not None and kg < 0) or (so is not None and so < 0):
                    raise BusinessError("La proyección por producto no puede ser negativa.")
                detalle.append({"producto": item, "kg_mes": kg, "soles_mes": so})
    opp.productos = ", ".join(prods)
    opp.detalle_productos = detalle
    con_kg = [d["kg_mes"] for d in detalle if d["kg_mes"] is not None]
    con_so = [d["soles_mes"] for d in detalle if d["soles_mes"] is not None]
    opp.proyeccion_mensual = round(sum(con_so), 2) if con_so else _num(datos.get("proyeccion_mensual"))
    opp.proyeccion_kg = round(sum(con_kg), 2) if con_kg else _num(datos.get("proyeccion_kg"))
    db().flush()
    audit(user, "OPORTUNIDAD_GUARDADA", "Opportunity", opp.id, {"cliente": customer.ruc, "nuevo": nuevo})
    return opp


def set_state(user, opp, estado, motivo=""):
    _require(user)
    _own(user, opp=opp)
    estado = (estado or "").upper()
    if estado not in ESTADOS:
        raise BusinessError("Estado inválido.")
    if estado in ("GANADA", "PERDIDA") and not (motivo or "").strip():
        raise BusinessError("Indique el motivo o el detalle del cierre.")
    opp.estado = estado
    if estado in ("GANADA", "PERDIDA"):
        opp.cerrado_ts = now()
        opp.motivo_cierre = motivo.strip()
    audit(user, "OPORTUNIDAD_ESTADO", "Opportunity", opp.id, {"estado": estado, "motivo": motivo})
    return opp


def add_action(user, customer, tipo, fecha, resultado="", gasto=None, opp=None, proxima=None):
    _require(user)
    _own(user, customer, opp)
    tipos = param("tipos_accion_cliente", []) or []
    if tipo not in tipos:
        raise BusinessError("Elija el tipo de acción.")
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha) if fecha else date.today()
    if isinstance(proxima, str):
        proxima = date.fromisoformat(proxima) if proxima else None
    if not (resultado or "").strip():
        raise BusinessError("Describa el resultado de la acción (qué se conversó o acordó).")
    a = CustomerAction(customer_id=customer.id, opportunity_id=opp.id if opp else None, tipo=tipo, fecha=fecha or date.today(),
                       gasto=_num(gasto), resultado=resultado.strip(), proxima_accion=proxima, user_id=user.id)
    db().add(a)
    db().flush()
    audit(user, "ACCION_CLIENTE", "Customer", customer.ruc, {"tipo": tipo, "fecha": a.fecha, "oportunidad": opp.id if opp else None})
    return a


def next_quote_number():
    n = db().execute(select(func.count(Quote.id))).scalar() or 0
    return f"COT-{date.today():%Y}-{n + 1:05d}"


def save_quote(user, customer, lineas, vigencia=None, opp=None, observacion=""):
    _require(user)
    _own(user, customer, opp)
    from ..models import Product
    filas = []
    for ln in lineas:
        code = (ln.get("product_code") or "").strip().upper().split(" ")[0]
        if not code:
            continue
        p = db().get(Product, code)
        if p is None:
            raise BusinessError(f"Producto {code} no existe.")
        try:
            q, pr = float(ln.get("cantidad")), float(ln.get("precio"))
        except (TypeError, ValueError):
            raise BusinessError(f"{code}: cantidad y precio son obligatorios.")
        if q <= 0 or pr <= 0:
            raise BusinessError(f"{code}: cantidad y precio deben ser mayores que cero.")
        from .orders import unit_for
        filas.append({"product_code": code, "descripcion": p.descripcion, "cantidad": q, "precio": pr, "um": unit_for(p)})
    if not filas:
        raise BusinessError("La cotización necesita al menos un producto con cantidad y precio.")
    if isinstance(vigencia, str):
        vigencia = date.fromisoformat(vigencia) if vigencia else None
    q = Quote(numero=next_quote_number(), customer_id=customer.id, opportunity_id=opp.id if opp else None, fecha=date.today(),
              vigencia=vigencia, lineas=filas, total=round(sum(f["cantidad"] * f["precio"] for f in filas), 2),
              observacion=(observacion or "").strip(), user_id=user.id)
    db().add(q)
    if opp is not None and opp.estado == "ABIERTA":
        opp.estado = "COTIZADA"
    db().flush()
    audit(user, "COTIZACION_EMITIDA", "Quote", q.numero, {"cliente": customer.ruc, "total": q.total})
    return q


def set_quote_state(user, q, estado):
    _require(user)
    estado = (estado or "").upper()
    if estado not in ("EMITIDA", "ACEPTADA", "RECHAZADA", "VENCIDA"):
        raise BusinessError("Estado inválido.")
    q.estado = estado
    if estado == "ACEPTADA" and q.opportunity is not None and q.opportunity.estado in ("ABIERTA", "COTIZADA"):
        q.opportunity.estado = "NEGOCIACION"
    audit(user, "COTIZACION_ESTADO", "Quote", q.numero, {"estado": estado})
    return q


def convert_prospect(user, customer, oc_archivo):
    """El prospecto pasa a cliente: requiere una acción registrada (si así se configura) y su orden de compra."""
    _require(user)
    _own(user, customer)
    if not customer.es_prospecto:
        raise BusinessError("El cliente ya no es prospecto.")
    if param("exigir_accion_cliente_nuevo", True):
        n = db().execute(select(func.count(CustomerAction.id)).where(CustomerAction.customer_id == customer.id)).scalar()
        if not n:
            raise BusinessError("Registre al menos una acción con el cliente (visita, llamada, reunión…) antes de convertirlo.")
    if not oc_archivo:
        raise BusinessError("Adjunte la orden de compra del cliente para pasarlo de prospecto a cliente.")
    customer.es_prospecto = False
    customer.convertido = {"oc": oc_archivo, "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    for o in db().execute(select(Opportunity).where(Opportunity.customer_id == customer.id,
                                                    Opportunity.estado.in_(["ABIERTA", "COTIZADA", "NEGOCIACION"]))).scalars():
        o.estado, o.cerrado_ts, o.motivo_cierre = "GANADA", now(), "El prospecto pasó a cliente con su orden de compra."
    audit(user, "PROSPECTO_CONVERTIDO", "Customer", customer.ruc, {"oc": oc_archivo})
    return customer


def listing(user, estado="", vendedor_id=None):
    q = select(Opportunity).order_by(Opportunity.creado_ts.desc())
    if estado:
        q = q.where(Opportunity.estado == estado)
    rows = list(db().execute(q).scalars())
    if not has_perm(user, "oportunidades.ver_todas"):
        rows = [o for o in rows if o.vendedor_id == user.id]
    elif vendedor_id:
        rows = [o for o in rows if o.vendedor_id == int(vendedor_id)]
    return rows


def funnel(user, desde=None, hasta=None):
    """Funnel por etapa, conversión y desempeño por vendedor (acciones, gasto, cotizaciones, ganadas)."""
    rows = listing(user)
    if desde:
        rows = [o for o in rows if o.creado_ts.date() >= desde]
    if hasta:
        rows = [o for o in rows if o.creado_ts.date() <= hasta]
    etapas = Counter(o.estado for o in rows)
    acc = list(db().execute(select(CustomerAction)).scalars())
    quotes = list(db().execute(select(Quote)).scalars())
    if not has_perm(user, "oportunidades.ver_todas"):
        acc = [a for a in acc if a.user_id == user.id]
        quotes = [q for q in quotes if q.user_id == user.id]
    if desde:
        acc = [a for a in acc if a.fecha >= desde]
        quotes = [q for q in quotes if q.fecha >= desde]
    if hasta:
        acc = [a for a in acc if a.fecha <= hasta]
        quotes = [q for q in quotes if q.fecha <= hasta]
    vend = defaultdict(lambda: Counter())
    gasto = defaultdict(float)
    for a in acc:
        n = a.user.nombre if a.user else "-"
        vend[n]["acciones"] += 1
        vend[n][f"t:{a.tipo}"] += 1
        gasto[n] += a.gasto or 0
    for q in quotes:
        n = q.user.nombre if q.user else "-"
        vend[n]["cotizaciones"] += 1
        vend[n]["cotizado"] += q.total
    for o in rows:
        n = o.vendedor.nombre if o.vendedor else "-"
        vend[n]["oportunidades"] += 1
        vend[n]["ganadas"] += o.estado == "GANADA"
        vend[n]["perdidas"] += o.estado == "PERDIDA"
        vend[n]["proyeccion"] += o.proyeccion_mensual or 0 if o.estado not in ("PERDIDA",) else 0
    cerradas = etapas["GANADA"] + etapas["PERDIDA"]
    return {"etapas": [(e, ESTADOS[e], etapas[e]) for e in ORDEN_FUNNEL + ["PERDIDA"]], "total": len(rows),
            "conversion": round(100 * etapas["GANADA"] / cerradas, 1) if cerradas else None,
            "vendedores": sorted(((n, c, round(gasto[n], 2)) for n, c in vend.items()), key=lambda x: -x[1]["acciones"]),
            "tipos": param("tipos_accion_cliente", []) or [], "acciones": len(acc), "cotizaciones": len(quotes)}
