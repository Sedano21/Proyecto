"""V52 (17-nov-2026): facturación del mes desde SAP.

«Cómo va la empresa» mostraba como «Venta del mes» la suma de las OV del módulo, que no es la facturación que reporta
Comercial (facturas − notas de crédito de SAP). Además, las facturas de SAP solo quedaban en el módulo si el cliente ya
existía en su maestro. Aquí se leen de SAP todas las facturas y notas de crédito (no anuladas) con su total en soles
(DocTotal, moneda local) y su IGV (VatSum), sin depender del maestro de clientes."""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SapBilling, now
from .core import param


def sync(user, sl=None, desde=None):
    from . import sap_sl
    from .sap_v31 import historial_desde
    hay = db().execute(select(SapBilling.id).limit(1)).first() is not None
    # V70: si las facturas leídas antes aún no traen de qué guía y OV salen, se relee todo el historial una vez
    sin_origen = hay and any(not (x.origenes or {}).get("leido") for x in db().execute(
        select(SapBilling).order_by(SapBilling.id.desc()).limit(50)).scalars())
    if sin_origen and desde is None:
        from .sap_v31 import historial_desde as _hd
        desde = _hd()
    hoy = date.today()
    # la primera vez, desde el inicio del historial (para comparar con el año anterior); luego, el mes en curso y el
    # anterior (las notas de crédito o anulaciones tardías)
    desde = desde or ((hoy.replace(day=1) - timedelta(days=1)).replace(day=1) if hay else historial_desde())
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    try:
        if propio:
            sl.login()
        docs = []
        for tipo, ent in (("FACTURA", "Invoices"), ("NOTA_CREDITO", "CreditNotes")):
            for d in sl.get_all(ent, {"$filter": f"DocDate ge '{desde.isoformat()}'",
                                      "$select": "DocEntry,DocNum,FolioPrefixString,FolioNumber,CardCode,CardName,DocDate,"
                                                 "DocCurrency,DocTotal,VatSum,Cancelled,DocumentLines"}):
                docs.append((tipo, d))
        # V70: OV de origen (líneas basadas en una OV, BaseType 17) para ver la factura en la OV
        from .sap_v29 import _por_entry
        ovs = _por_entry(sl, "Orders", [ln.get("BaseEntry") for _, d in docs for ln in d.get("DocumentLines") or []
                                        if ln.get("BaseType") == 17], "DocEntry,DocNum")
    finally:
        if propio:
            sl.logout()
    existentes = {x.clave: x for x in db().execute(select(SapBilling).where(SapBilling.fecha >= desde)).scalars()}
    nuevas = act = anuladas = 0
    vistos = set()
    for tipo, d in docs:
        clave = f"{tipo}:{d.get('DocEntry')}"
        vistos.add(clave)
        if d.get("Cancelled") in ("tYES", "csYes", "Y"):
            if clave in existentes:
                db().delete(existentes.pop(clave))
                anuladas += 1
            continue
        try:
            fecha = sap_sl._d(d.get("DocDate"))
        except ValueError:
            fecha = None
        if fecha is None:
            continue
        datos = {"tipo": tipo, "numero": sap_sl._folio(d), "fecha": fecha, "cardcode": (d.get("CardCode") or "")[:30],
                 "cliente": (d.get("CardName") or "")[:200], "moneda": (d.get("DocCurrency") or "")[:10],
                 "total": float(d.get("DocTotal") or 0), "igv": float(d.get("VatSum") or 0),
                 "origenes": origenes(d, ovs)}
        x = existentes.get(clave)
        if x is None:
            db().add(SapBilling(clave=clave, ts=now(), **datos))
            nuevas += 1
        elif any(getattr(x, k) != v for k, v in datos.items()):
            for k, v in datos.items():
                setattr(x, k, v)
            act += 1
    db().flush()
    return {"desde": desde.isoformat(), "leidas": len(docs), "nuevas": nuevas, "actualizadas": act, "anuladas": anuladas}


def origenes(d, ovs=None):
    """V70: {guias: [DocEntry de la entrega], ovs: [DocNum de la OV]} de las líneas de la factura (BaseType 15 = entrega,
    17 = orden de venta)."""
    guias, nums = [], []
    for ln in d.get("DocumentLines") or []:
        if ln.get("BaseType") == 15 and ln.get("BaseEntry") and int(ln["BaseEntry"]) not in guias:
            guias.append(int(ln["BaseEntry"]))
        if ln.get("BaseType") == 17 and ln.get("BaseEntry"):
            n = str(((ovs or {}).get(ln["BaseEntry"]) or {}).get("DocNum") or "")
            if n and n not in nums:
                nums.append(n)
    return {"guias": guias, "ovs": nums, "leido": True}


def resumen(desde, hasta, canal=""):
    """Facturación del periodo: facturas, notas de crédito y neto, con y sin IGV. None si no hay datos de SAP."""
    q = select(SapBilling).where(SapBilling.fecha >= desde, SapBilling.fecha <= hasta)
    docs = list(db().execute(q).scalars())
    if not docs and db().execute(select(SapBilling.id).limit(1)).first() is None:
        return None
    if canal:
        from ..models import Customer
        from .margin import channel
        nombres = {d.cliente for d in docs}
        canal_de = {c.nombre: channel(c) for c in db().execute(select(Customer).where(Customer.nombre.in_(list(nombres) or [""])))
                    .scalars()}
        docs = [d for d in docs if canal_de.get(d.cliente) == canal]
    fac = [d for d in docs if d.tipo == "FACTURA"]
    nc = [d for d in docs if d.tipo == "NOTA_CREDITO"]
    t = lambda xs: round(sum(x.total for x in xs), 2)  # noqa: E731
    b = lambda xs: round(sum(x.total - x.igv for x in xs), 2)  # noqa: E731
    return {"facturas": t(fac), "notas_credito": t(nc), "neto": round(t(fac) - t(nc), 2), "n_facturas": len(fac),
            "n_notas": len(nc), "facturas_sin_igv": b(fac), "notas_sin_igv": b(nc), "neto_sin_igv": round(b(fac) - b(nc), 2),
            "desde": desde, "hasta": hasta, "ultima": max((d.fecha for d in docs), default=None)}


def ov_del_periodo(desde, hasta, canal=""):
    """V55: las OV de SAP con despacho (fecha de entrega) en el periodo, sin las anuladas: su valor en soles con y sin
    IGV (líneas de la OV), lo ya despachado (proporcional a lo entregado) y lo que falta despachar; además, las que
    se ingresaron (emitieron) en el periodo. None si las OV de SAP aún no traen su valor (se completa en la próxima
    lectura del historial)."""
    from ..models import SapOrderLine
    if db().execute(select(SapOrderLine.id).where(SapOrderLine.total != 0).limit(1)).first() is None:
        return None
    lineas = list(db().execute(select(SapOrderLine).where(SapOrderLine.fecha_entrega >= desde,
                                                          SapOrderLine.fecha_entrega <= hasta,
                                                          SapOrderLine.estado != "CANCELADA")).scalars())
    ingresadas = list(db().execute(select(SapOrderLine).where(SapOrderLine.fecha >= desde, SapOrderLine.fecha <= hasta,
                                                              SapOrderLine.estado != "CANCELADA")).scalars())
    if canal:
        from ..models import Customer
        from .margin import channel
        nombres = {x.cliente for x in lineas + ingresadas}
        canal_de = {c.nombre: channel(c) for c in db().execute(select(Customer).where(Customer.nombre.in_(list(nombres) or [""])))
                    .scalars()}
        lineas = [x for x in lineas if canal_de.get(x.cliente) == canal]
        ingresadas = [x for x in ingresadas if canal_de.get(x.cliente) == canal]
    con = lambda x: (x.total or 0) + (x.igv or 0)  # noqa: E731
    frac = lambda x: min((x.entregado or 0) / x.cantidad, 1.0) if x.cantidad else 0.0  # noqa: E731
    total = sum(con(x) for x in lineas)
    desp = sum(con(x) * frac(x) for x in lineas)
    return {"total": round(total, 2), "sin_igv": round(sum(x.total or 0 for x in lineas), 2),
            "despachado": round(desp, 2), "por_despachar": round(total - desp, 2), "n": len({x.docnum for x in lineas}),
            "ingresadas": round(sum(con(x) for x in ingresadas), 2), "n_ingresadas": len({x.docnum for x in ingresadas}),
            "desde": desde, "hasta": hasta}


def detalle(desde, hasta, tipo=""):
    """V55: documentos de SAP del periodo (facturas y notas de crédito), con el resumen y el neto por cliente."""
    q = select(SapBilling).where(SapBilling.fecha >= desde, SapBilling.fecha <= hasta)
    docs = list(db().execute(q.order_by(SapBilling.fecha.desc(), SapBilling.numero)).scalars())
    por_cli = {}
    for d in docs:
        c = por_cli.setdefault(d.cliente or d.cardcode, {"cliente": d.cliente or d.cardcode, "facturas": 0.0, "notas": 0.0,
                                                          "n_facturas": 0, "n_notas": 0})
        if d.tipo == "FACTURA":
            c["facturas"] += d.total
            c["n_facturas"] += 1
        else:
            c["notas"] += d.total
            c["n_notas"] += 1
    for c in por_cli.values():
        c["neto"] = round(c["facturas"] - c["notas"], 2)
    lista = [d for d in docs if not tipo or d.tipo == tipo]
    return {"resumen": resumen(desde, hasta), "docs": lista,
            "clientes": sorted(por_cli.values(), key=lambda c: -c["neto"])}


def ov_detalle(desde, hasta):
    """V55: OV de SAP con despacho en el periodo, una fila por OV: cliente, fecha, estado, valor, despachado y saldo."""
    from ..models import SapOrderLine
    lineas = list(db().execute(select(SapOrderLine).where(SapOrderLine.fecha_entrega >= desde,
                                                          SapOrderLine.fecha_entrega <= hasta,
                                                          SapOrderLine.estado != "CANCELADA")).scalars())
    ovs = {}
    for x in lineas:
        con = (x.total or 0) + (x.igv or 0)
        frac = min((x.entregado or 0) / x.cantidad, 1.0) if x.cantidad else 0.0
        o = ovs.setdefault(x.docnum, {"docnum": x.docnum, "cliente": x.cliente, "fecha": x.fecha, "entrega": x.fecha_entrega,
                                      "estado": x.estado, "clase": x.clase, "total": 0.0, "despachado": 0.0, "lineas": 0})
        o["total"] += con
        o["despachado"] += con * frac
        o["lineas"] += 1
    for o in ovs.values():
        o["saldo"] = round(o["total"] - o["despachado"], 2)
    return sorted(ovs.values(), key=lambda o: (o["entrega"] or date.min, o["docnum"]))


def _guias_del_periodo(desde, hasta, canal=""):
    """V58: líneas de las guías (entregas) de SAP con fecha en el periodo, con su valor en soles con IGV. Si una línea
    aún no trae su valor (antes de releer el historial), se valoriza con el precio de su OV en SAP."""
    from collections import defaultdict
    from ..models import SapMovement, SapOrderLine
    movs = list(db().execute(select(SapMovement).where(SapMovement.tipo == "GUIA", SapMovement.fecha >= desde,
                                                       SapMovement.fecha <= hasta)).scalars())
    if canal:
        from ..models import Customer
        from .margin import channel
        nombres = {m.cliente for m in movs}
        canal_de = {c.nombre: channel(c) for c in db().execute(select(Customer).where(Customer.nombre.in_(list(nombres) or [""])))
                    .scalars()}
        movs = [m for m in movs if canal_de.get(m.cliente) == canal]
    ovs = sorted({m.ov_numero for m in movs if m.ov_numero})
    pedido, precio, precio_sin, estado_ov = defaultdict(float), {}, {}, {}
    for i in range(0, len(ovs), 500):
        for ln in db().execute(select(SapOrderLine).where(SapOrderLine.docnum.in_(ovs[i:i + 500]))).scalars():
            pedido[(ln.docnum, ln.product_code)] += ln.cantidad or 0
            if ln.cantidad:
                precio[(ln.docnum, ln.product_code)] = ((ln.total or 0) + (ln.igv or 0)) / ln.cantidad
                precio_sin[(ln.docnum, ln.product_code)] = (ln.total or 0) / ln.cantidad
            estado_ov.setdefault(ln.docnum, set()).add(ln.estado)
    guiado_total = defaultdict(float)  # todo lo guiado de esas OV (también en otros meses), para saber si quedó completa
    for i in range(0, len(ovs), 500):
        for m in db().execute(select(SapMovement).where(SapMovement.tipo == "GUIA",
                                                        SapMovement.ov_numero.in_(ovs[i:i + 500]))).scalars():
            guiado_total[(m.ov_numero, m.product_code)] += m.cantidad or 0
    filas, valorizado_ov = [], 0
    for m in movs:
        v, sin = (m.total or 0) + (m.igv or 0), (m.total or 0)
        if not v and (m.ov_numero, m.product_code) in precio:
            v = (m.cantidad or 0) * precio[(m.ov_numero, m.product_code)]
            sin = (m.cantidad or 0) * precio_sin[(m.ov_numero, m.product_code)]
            valorizado_ov += 1
        m._sin_igv = sin
        filas.append((m, v))

    def tipo_ov(ov):
        if not ov or not any(k[0] == ov for k in pedido):
            return "SIN_OV"
        completa = all(guiado_total[k] >= q - 1e-9 for k, q in pedido.items() if k[0] == ov)
        return "COMPLETA" if completa else ("CERRADA_PARCIAL" if estado_ov.get(ov, set()) <= {"CERRADA", "CANCELADA"} else "PARCIAL")
    return filas, tipo_ov, valorizado_ov


def entregado(desde, hasta, canal=""):
    """V58: valor de todo lo entregado (guías de SAP) en el periodo: despachos completos, parciales y sin OV."""
    from ..models import SapMovement
    if db().execute(select(SapMovement.id).where(SapMovement.tipo == "GUIA").limit(1)).first() is None:
        return None
    filas, tipo_ov, por_precio_ov = _guias_del_periodo(desde, hasta, canal)
    total = sum(v for _, v in filas)
    sin_igv = sum(m._sin_igv for m, _ in filas)
    por_tipo = {"COMPLETA": 0.0, "PARCIAL": 0.0, "CERRADA_PARCIAL": 0.0, "SIN_OV": 0.0}
    ovs_tipo = {}
    for m, v in filas:
        t = ovs_tipo.setdefault(m.ov_numero or f"_{m.docentry}", tipo_ov(m.ov_numero))
        por_tipo[t] += v
    return {"total": round(total, 2), "sin_igv": round(sin_igv, 2), "guias": len({m.docentry for m, _ in filas}),
            "ovs": len({m.ov_numero for m, _ in filas if m.ov_numero}), "por_tipo": {k: round(v, 2) for k, v in por_tipo.items()},
            "n_tipo": {k: sum(1 for x in ovs_tipo.values() if x == k) for k in por_tipo},
            "estimadas": por_precio_ov, "desde": desde, "hasta": hasta}


def entregado_detalle(desde, hasta, canal=""):
    """Una fila por guía: fecha, guía, cliente, OV, tipo de despacho de la OV, productos y valor."""
    filas, tipo_ov, _ = _guias_del_periodo(desde, hasta, canal)
    guias = {}
    for m, v in filas:
        g = guias.setdefault(m.docentry, {"docentry": m.docentry, "guia": m.documento, "fecha": m.fecha, "cliente": m.cliente,
                                          "ov": m.ov_numero, "tipo": tipo_ov(m.ov_numero), "valor": 0.0, "lineas": 0,
                                          "estimada": False})
        g["valor"] += v
        g["lineas"] += 1
        g["estimada"] = g["estimada"] or not m.total
    return sorted(guias.values(), key=lambda g: (g["fecha"] or date.min, g["guia"]), reverse=True)
