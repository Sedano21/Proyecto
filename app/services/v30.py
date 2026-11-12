"""V30 (12-nov-2026):
1. Ubicación física de cada lote en el almacén (la editan Supervisor de Almacén, Líder Operativo, Jefatura y
   Coordinación de Logística; los demás con acceso al stock la ven).
2. Clientes sin ningún movimiento ni pedido en los últimos «clientes_inactividad_meses» (18) meses: la Jefatura y la
   Coordinación Comercial los revisan y deciden excluirlos, mantenerlos (incluir) o editarlos.
3. Expediente por cliente: sus guías, facturas y notas de crédito.
"""
from datetime import date, timedelta

from sqlalchemy import func, select

from ..db import db
from ..models import Customer, CustomerInvoice, SalesOrder, StockLot, now
from .core import BusinessError, audit, has_perm, param


# ------------------------------------------------------------------ 1. ubicación del lote
def set_location(user, lot, ubicacion):
    if not has_perm(user, "stock.ubicacion"):
        raise BusinessError("La ubicación la editan el Supervisor de Almacén, el Líder Operativo y Logística.")
    nueva = " ".join((ubicacion or "").split()).upper()[:80]
    if nueva == (lot.ubicacion or ""):
        return lot
    hist = list(lot.ubicacion_hist or [])
    hist.append({"de": lot.ubicacion or "", "a": nueva, "user": user.nombre, "ts": now().isoformat(timespec="minutes")})
    lot.ubicacion_hist = hist[-50:]
    lot.ubicacion = nueva
    audit(user, "LOTE_UBICACION", "StockLot", lot.id, {"lote": lot.lote, "de": hist[-1]["de"], "a": nueva})
    return lot


def ubicaciones_usadas():
    return sorted({u for (u,) in db().execute(select(StockLot.ubicacion).where(StockLot.ubicacion != "",
                                                                               StockLot.cantidad > 0).distinct())})


# ------------------------------------------------------------------ 2. clientes sin movimiento
def _meses():
    return int(param("clientes_inactividad_meses", 18) or 18)


def ultimo_movimiento():
    """{customer_id: fecha del último movimiento}: OV (emisión), facturas o notas de crédito y cotizaciones (el historial
    de ventas no trae el cliente)."""
    from ..models import Quote
    s = db()
    out = {}

    def tomar(q):
        for cid, f in s.execute(q):
            if cid is None or f is None:
                continue
            f = f.date() if hasattr(f, "date") and not isinstance(f, date) else f
            if cid not in out or f > out[cid]:
                out[cid] = f
    tomar(select(SalesOrder.customer_id, func.max(SalesOrder.fecha_emision)).group_by(SalesOrder.customer_id))
    tomar(select(CustomerInvoice.customer_id, func.max(CustomerInvoice.fecha)).group_by(CustomerInvoice.customer_id))
    tomar(select(Quote.customer_id, func.max(Quote.fecha)).group_by(Quote.customer_id))
    return out


def inactivos(hoy=None, ver="PENDIENTES"):
    """Clientes sin movimiento desde hace más de 18 meses (o sin ningún movimiento registrado).
    ver = PENDIENTES (sin decisión, o mantenidos antes de que se cumplan otros 18 meses), EXCLUIDOS, INCLUIDOS o TODOS."""
    hoy = hoy or date.today()
    limite = hoy - timedelta(days=round(_meses() * 30.44))
    ult = ultimo_movimiento()
    filas = []
    for c in db().execute(select(Customer).where(Customer.es_prospecto.is_(False)).order_by(Customer.nombre)).scalars():
        f = ult.get(c.id)
        dec = c.inactividad or {}
        incluido_desde = None
        if dec.get("estado") == "INCLUIDO":
            try:
                incluido_desde = date.fromisoformat(dec["ts"][:10])
            except (KeyError, ValueError):
                incluido_desde = None
        sin_mov = f is None or f < limite
        if not sin_mov and not c.excluido:
            continue
        if ver == "EXCLUIDOS" and not c.excluido:
            continue
        if ver == "INCLUIDOS" and dec.get("estado") != "INCLUIDO":
            continue
        if ver == "PENDIENTES":
            if c.excluido:
                continue
            if incluido_desde and incluido_desde >= limite:
                continue  # lo mantuvieron hace menos de 18 meses: vuelve a la lista cuando se cumplan
        filas.append({"c": c, "ultimo": f, "meses": None if f is None else round((hoy - f).days / 30.44, 1),
                      "decision": dec})
    return {"filas": filas, "limite": limite, "meses": _meses()}


def decidir(user, c, accion, motivo=""):
    if not has_perm(user, "clientes.inactivos"):
        raise BusinessError("La revisión de clientes sin movimiento la hacen la Jefatura y la Coordinación Comercial.")
    if accion not in ("EXCLUIR", "INCLUIR"):
        raise BusinessError("Acción no válida.")
    if accion == "EXCLUIR" and not (motivo or "").strip():
        raise BusinessError("Indique el motivo para excluir al cliente.")
    hist = list((c.inactividad or {}).get("historial", []))
    d = {"estado": "EXCLUIDO" if accion == "EXCLUIR" else "INCLUIDO", "motivo": (motivo or "").strip()[:300],
         "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    hist.append(d)
    c.inactividad = dict(d, historial=hist[-20:])
    c.excluido = accion == "EXCLUIR"
    audit(user, "CLIENTE_INACTIVO_" + d["estado"], "Customer", c.id, {"motivo": d["motivo"]})
    return c


def reactivar_por_movimiento(customer, user=None, origen=""):
    """Un cliente excluido que vuelve a tener un pedido queda incluido de nuevo (queda en su historial)."""
    if customer is None or not customer.excluido:
        return
    hist = list((customer.inactividad or {}).get("historial", []))
    d = {"estado": "INCLUIDO", "motivo": f"Volvió a tener movimiento ({origen})"[:300], "user": user.nombre if user else "Sistema",
         "ts": now().isoformat(timespec="minutes")}
    hist.append(d)
    customer.inactividad = dict(d, historial=hist[-20:])
    customer.excluido = False


# ------------------------------------------------------------------ 3. expediente: guías, facturas y notas de crédito
def documentos_cliente(customer, desde=None, hasta=None):
    """Guías (de las cargas de entregas de SAP y las pre-guías y guías SUNAT del módulo), facturas y notas de crédito
    del cliente."""
    from ..models import SunatGuide, UploadBatch, UploadRow
    s = db()
    ovs = {o.numero: o for o in s.execute(select(SalesOrder).where(SalesOrder.customer_id == customer.id)).scalars()}
    nums = set(ovs) | {o.sap_docnum for o in ovs.values() if o.sap_docnum}
    guias = {}
    ult = s.execute(select(UploadBatch).where(UploadBatch.tipo == "DESPACHOS", UploadBatch.estado != "ANULADO")
                    .order_by(UploadBatch.id.desc()).limit(6)).scalars().all()
    for b in ult:
        for r in s.execute(select(UploadRow).where(UploadRow.batch_id == b.id, UploadRow.excluida.is_(False))).scalars():
            d = r.datos or {}
            ov = str(d.get("ov") or "").strip()
            if ov.endswith(".0"):
                ov = ov[:-2]
            if ov not in nums or not d.get("guia"):
                continue
            g = guias.setdefault(str(d["guia"]), {"guia": str(d["guia"]), "fecha": str(d.get("fecha") or "")[:10], "ov": ov,
                                                  "factura": str(d.get("factura") or ""), "origen": "SAP", "lineas": 0})
            g["lineas"] += 1
    for sg in s.execute(select(SunatGuide).where(SunatGuide.order_id.in_([o.id for o in ovs.values()] or [0]))).scalars():
        k = f"{sg.serie}-{sg.numero}"
        guias.setdefault(k, {"guia": k, "fecha": str(sg.fecha_emision or "")[:10],
                             "ov": sg.order.numero if sg.order else "", "factura": "", "origen": "SUNAT", "lineas": len(sg.lineas or [])})
    for o in ovs.values():
        pg = o.preguia or {}
        n = (pg.get("sap") or {}).get("docnum")  # guía validada en el módulo y registrada en SAP
        if n and str(n) not in guias:
            guias[str(n)] = {"guia": str(n), "fecha": str(pg.get("fecha_guia") or "")[:10], "ov": o.numero, "factura": "",
                             "origen": "MÓDULO", "lineas": len(pg.get("items") or [])}
    q = select(CustomerInvoice).where(CustomerInvoice.customer_id == customer.id)
    if desde:
        q = q.where(CustomerInvoice.fecha >= desde)
    if hasta:
        q = q.where(CustomerInvoice.fecha <= hasta)
    docs = list(s.execute(q.order_by(CustomerInvoice.fecha.desc())).scalars())
    g_list = sorted(guias.values(), key=lambda x: x["fecha"], reverse=True)
    if desde or hasta:
        g_list = [x for x in g_list if (not desde or x["fecha"] >= desde.isoformat()) and (not hasta or x["fecha"] <= hasta.isoformat())]
    return {"guias": g_list, "facturas": [d for d in docs if d.tipo != "NOTA_CREDITO"],
            "notas_credito": [d for d in docs if d.tipo == "NOTA_CREDITO"]}
