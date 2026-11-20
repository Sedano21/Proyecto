"""V54 (17-nov-2026): la OV del módulo se mantiene al día con SAP, sin esperar a que alguien lo registre en el módulo.

- Guías: lo guiado en SAP (entregas basadas en la OV) y en las guías SUNAT subidas al módulo que aún no están en SAP se
  descuenta de cada línea (despachado). Si cubre todo lo pedido la OV queda DESPACHADA (cerrada para Operaciones); si
  cubre una parte, DESPACHO_PARCIAL (el saldo sigue pendiente y conserva su reserva; lo ya guiado libera la suya).
- La OV anulada en SAP sin guías queda CANCELADA; la cerrada en SAP con parte guiada queda CERRADA (el saldo no se
  atenderá). Nada de esto se envía a SAP: SAP es la fuente.
- Bloqueos: por ahora la OV solo se bloquea por precio (V44). Las OV que quedaron BLOQUEADAS antes por anticipación o
  por falta de opción se reactivan y se vuelven a evaluar; la evaluación de si se llega o no a la fecha se sigue
  mostrando (sin bloquear).
"""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from ..db import db
from ..models import SalesOrder
from .core import audit, param

TOL = 1e-6


def _nums(o):
    return {x for x in (o.numero, o.sap_docnum) if x}


def guias_de(orders):
    """{order_id: [{documento, fecha, origen, lineas: {codigo: cantidad}}]} con las guías de SAP y las guías SUNAT del
    módulo que todavía no están en SAP (una guía SUNAT ya registrada en SAP se cuenta una sola vez)."""
    from ..models import SapMovement, SunatGuide
    por_num = {}
    for o in orders:
        for n in _nums(o):
            por_num[n] = o.id
    out = defaultdict(dict)
    nums = list(por_num)
    for i in range(0, len(nums), 500):
        for m in db().execute(select(SapMovement).where(SapMovement.tipo == "GUIA",
                                                        SapMovement.ov_numero.in_(nums[i:i + 500]))).scalars():
            oid = por_num[m.ov_numero]
            g = out[oid].setdefault(m.documento or f"SAP {m.docentry}",
                                    {"documento": m.documento or f"SAP {m.docentry}", "fecha": m.fecha, "origen": "SAP",
                                     "docentry": m.docentry, "lineas": defaultdict(float)})
            g["lineas"][m.product_code] += m.cantidad or 0
    ids = [o.id for o in orders] or [-1]
    for i in range(0, len(ids), 500):
        for sg in db().execute(select(SunatGuide).where(SunatGuide.order_id.in_(ids[i:i + 500]),
                                                        SunatGuide.estado != "ANULADA")).scalars():
            try:
                folio = f"{sg.serie.upper()}-{int(sg.numero)}"
            except ValueError:
                folio = f"{sg.serie.upper()}-{sg.numero}"
            if folio in out[sg.order_id] or (sg.sap or {}).get("estado") == "OK" and any(
                    g.get("docentry") == (sg.sap or {}).get("docentry") for g in out[sg.order_id].values()):
                continue
            g = out[sg.order_id].setdefault(folio, {"documento": folio, "fecha": sg.fecha_traslado, "origen": "MODULO",
                                                    "lineas": defaultdict(float)})
            for ln in sg.lineas or []:
                g["lineas"][str(ln.get("codigo") or "")] += float(ln.get("cantidad") or 0)
    return {oid: sorted(gs.values(), key=lambda g: (g["fecha"] is None, g["fecha"] or datetime.min.date()))
            for oid, gs in out.items()}


def estado_sap(orders):
    """{order_id: ABIERTA / CERRADA / CANCELADA} según las líneas de la OV en SAP (si SAP la tiene)."""
    from ..models import SapOrderLine
    por_num = {n: o.id for o in orders for n in _nums(o)}
    ests = defaultdict(set)
    nums = list(por_num)
    for i in range(0, len(nums), 500):
        for ln in db().execute(select(SapOrderLine).where(SapOrderLine.docnum.in_(nums[i:i + 500]))).scalars():
            ests[por_num[ln.docnum]].add(ln.estado)
    out = {}
    for oid, e in ests.items():
        if e == {"CANCELADA"}:
            out[oid] = "CANCELADA"
        elif e <= {"CERRADA", "CANCELADA"}:
            out[oid] = "CERRADA"
        else:
            out[oid] = "ABIERTA"
    return out


def _repartir(o, guias):
    """Lo guiado por producto repartido entre las líneas activas de la OV (hasta lo pedido). {line_id: cantidad}."""
    tot = defaultdict(float)
    for g in guias:
        for c, q in g["lineas"].items():
            tot[c] += q
    out = {}
    for ln in sorted([l for l in o.lines if l.activa], key=lambda l: l.id):
        q = min(tot.get(ln.product_code, 0.0), ln.cantidad or 0)
        out[ln.id] = q
        tot[ln.product_code] = tot.get(ln.product_code, 0.0) - q
    return out


def _liberar_guiado(o, motivo):
    """Libera las reservas de lo que ya salió con guía (la línea solo reserva su saldo)."""
    from .stock import _release
    for ln in o.lines:
        saldo = max((ln.cantidad or 0) - (ln.despachado or 0), 0.0) if ln.activa else 0.0
        activas = sorted([r for r in ln.reservations if r.estado == "ACTIVA"], key=lambda r: r.id)
        for r in activas:
            if saldo <= TOL:
                _release(r, motivo)
                continue
            if r.cantidad > saldo + TOL:
                r.cantidad = saldo
            saldo -= r.cantidad


def sincronizar(user=None, orders=None):
    """Aplica a las OV del módulo lo que SAP ya registró (guías, cierre, anulación). orders=None: todas las abiertas.
    Devuelve el resumen de lo que cambió."""
    from .stock import ORDEN_ESTADOS_CERRADOS, release_order
    if orders is None:
        orders = list(db().execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS))).scalars())
    else:
        orders = [o for o in orders if o.estado not in ORDEN_ESTADOS_CERRADOS]
    res = {"despachadas": [], "parciales": [], "canceladas": [], "cerradas": []}
    if not orders:
        return res
    guias = guias_de(orders)
    sap = estado_sap(orders)
    for o in orders:
        gs = guias.get(o.id, [])
        est_sap = sap.get(o.id)
        antes = o.estado
        if gs:
            rep = _repartir(o, gs)
            for ln in o.lines:
                if ln.id in rep and rep[ln.id] > (ln.despachado or 0) + TOL:
                    ln.despachado = rep[ln.id]
            if o.salida_ts is None and gs[0]["fecha"]:
                o.salida_ts = datetime.combine(gs[0]["fecha"], datetime.min.time())
        activas = [l for l in o.lines if l.activa]
        guiado = sum(min(l.despachado or 0, l.cantidad or 0) for l in activas)
        completo = bool(activas) and all((l.despachado or 0) >= (l.cantidad or 0) - TOL for l in activas)
        docs = ", ".join(g["documento"] for g in gs)
        if completo and gs:
            release_order(o, f"Despachada según guía(s) {docs}")
            o.estado = "DESPACHADA"
            o.motivo_detencion = ""
            res["despachadas"].append(o.numero)
        elif est_sap == "CANCELADA" and guiado <= TOL:
            release_order(o, "OV anulada en SAP")
            o.estado = "CANCELADA"
            o.cancelacion_motivo = o.cancelacion_motivo or "Anulada en SAP"
            res["canceladas"].append(o.numero)
        elif est_sap == "CERRADA":
            release_order(o, "OV cerrada en SAP")
            from .orders import saldo_kg
            kg = round(saldo_kg(o), 2)  # V64: cerrada (no cancelada): cuenta como pedido; el saldo es venta perdida
            o.cierre = o.cierre or {"tipo": "CERRADA", "causal": "Cerrada en SAP", "comentario": "", "user": "SAP",
                                    "ts": datetime.now().isoformat(timespec="seconds"), "origen": "SAP",
                                    "venta_perdida": kg > TOL, "kg_perdidos": kg}
            o.estado = "CERRADA"
            o.motivo_detencion = (f"Cerrada en SAP con despacho parcial ({docs}); el saldo no se atenderá" if guiado > TOL
                                  else "Cerrada en SAP sin guía")
            res["cerradas"].append(o.numero)
        elif guiado > TOL:
            _liberar_guiado(o, f"Ya despachado con guía(s) {docs}")
            if o.estado != "DESPACHO_PARCIAL":
                o.estado = "DESPACHO_PARCIAL"
                res["parciales"].append(o.numero)
        if o.estado != antes:
            audit(user, "OV_ESTADO_DESDE_SAP", "SalesOrder", o.numero,
                  {"antes": antes, "despues": o.estado, "guias": [g["documento"] for g in gs], "sap": est_sap or ""})
    db().flush()
    return res


# ------------------------------------------------------------------ bloqueos: por ahora solo por precio
def regla_activa(tipo):
    if tipo == "EMISION":
        return bool(int(param("dias_minimos_emision_ov", 0) or 0))
    if tipo == "SIN_OPCION":
        return bool(param("bloquear_ov_sin_opcion", False))
    return True


def reactivar_bloqueadas(user=None, orders=None):
    """Las OV BLOQUEADAS por una regla que hoy está apagada (anticipación, sin opción) se reactivan y se evalúan otra
    vez (reservan stock). Queda guardado si con lo que hay se llega o no a la fecha, como información."""
    from .commitment import open_commitment
    from .orders import _hist, unfeasible_lines
    from .stock import evaluate_order
    q = select(SalesOrder).where(SalesOrder.estado == "BLOQUEADA")
    orders = [o for o in orders if o.estado == "BLOQUEADA"] if orders is not None else list(db().execute(q).scalars())
    out = []
    for o in orders:
        b = o.bloqueo_ov or {}
        tipo = b.get("tipo") or ""
        if not tipo or regla_activa(tipo):
            continue
        nb = _hist(o, "DESBLOQUEO_REGLA_INACTIVA", user,
                   motivo="Por ahora la OV solo se bloquea por precio: se reactiva y se vuelve a evaluar")
        nb.update({k: v for k, v in b.items() if k != "historial"})
        nb["estado"] = "LEVANTADO"
        nb["motivo_original"] = b.get("motivo", "")
        o.estado = "REGISTRADA"
        o.motivo_detencion = ""
        try:
            evaluate_order(o, user, "REACTIVACION")
            falta = unfeasible_lines(o)
        except Exception as e:  # noqa: BLE001 - la reactivación no debe frenar la sincronización
            falta = [{"producto": "", "analisis": f"No se pudo evaluar: {str(e)[:120]}"}]
        nb["evaluacion"] = {"ts": datetime.now().isoformat(timespec="minutes"), "llega": not falta, "lineas": falta}
        o.bloqueo_ov = nb
        open_commitment(o)
        audit(user, "OV_REACTIVADA", "SalesOrder", o.numero, {"tipo": tipo, "motivo": b.get("motivo", ""),
                                                              "llega_a_la_fecha": not falta})
        out.append(o.numero)
    db().flush()
    return out


def motivo_detencion(o):
    """Por qué la OV está detenida o bloqueada, en palabras, para la pantalla."""
    b = o.bloqueo_ov or {}
    if o.retenida_precio:
        return o.motivo_detencion or "Detenida por precio bajo el mínimo: requiere confirmación comercial."
    if o.estado == "BLOQUEADA":
        return b.get("motivo") or o.motivo_detencion or "Bloqueada"
    return o.motivo_detencion or ""


def al_dia(user=None, orders=None):
    """Lo que se llama al abrir una pantalla de OV: estado desde SAP y bloqueos fuera de regla. Devuelve si cambió algo."""
    r = sincronizar(user, orders)
    rb = reactivar_bloqueadas(user, orders)
    return any(r.values()) or bool(rb)


def al_dia_vista(orders=None):
    """Para las pantallas: aplica lo de SAP (como el sistema) y guarda; si algo falla, la pantalla se muestra igual con
    lo que había (el vigilante lo vuelve a intentar)."""
    import logging
    try:
        with db().begin_nested():
            cambio = al_dia(None, orders)
        if cambio:
            db().commit()
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("OV al día con SAP")
        db().rollback()
