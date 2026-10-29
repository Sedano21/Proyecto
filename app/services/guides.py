"""Pre-guía, guía y corte de rutas (V12, 29-oct-2026).

- Al terminar el picking se genera la pre-guía de la OV (lo preparado contra lo pedido, con lotes). La revisan y validan
  el Coordinador o el Asistente de Distribución; validada, se registra como guía (entrega) en SAP y queda en el
  expediente del cliente (documentos de la OV).
- Las guías y pre-guías solo las modifican el Coordinador y el Asistente de Distribución.
- La fecha de la pre-guía o de la guía emitida se puede cambiar indicando el motivo (p. ej. se emitió para hoy y el
  pedido sale mañana). El cambio va a SAP; si el cambio se hace en SAP, llega al módulo con la sincronización de despachos.
- Corte de rutas: las rutas del día siguiente se planifican hasta las 15:00 del día anterior. Lo que se prepare o se pida
  para mañana después del corte se registra y se alerta a Distribución para que confirme si entra en la ruta.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import OrderAttachment, RouteStop, SalesOrder, now
from . import alerts
from .core import BusinessError, audit, has_perm, param


def _guarda(user):
    if not has_perm(user, "distribucion.guia_modificar"):
        raise BusinessError("Las guías las validan y modifican el Coordinador y el Asistente de Distribución.")


def _stop(order):
    return db().execute(select(RouteStop).where(RouteStop.order_id == order.id).order_by(RouteStop.id.desc())).scalars().first()


def generate(order, user=None):
    """Pre-guía de la OV con lo preparado (y sus lotes) frente a lo pedido."""
    items, dif = [], []
    for l in order.lines:
        if not l.activa:
            continue
        res = [r for r in l.reservations if r.estado in ("ACTIVA", "CONSUMIDA")]
        prep = l.preparado if l.preparado > 0 else sum(r.cantidad for r in res if r.estado == "ACTIVA")
        items.append({"codigo": l.product_code, "descripcion": l.product.descripcion if l.product else "",
                      "pedido": l.cantidad, "preparado": prep,
                      "lotes": [{"lote": r.lot.lote, "cantidad": r.cantidad, "fv": r.lot.fecha_venc.isoformat() if r.lot.fecha_venc else ""}
                                for r in res]})
        if abs(prep - l.cantidad) > 1e-9:
            dif.append(f"{l.product_code}: pedido {l.cantidad:g}, preparado {prep:g}")
    order.preguia = {"estado": "POR_VALIDAR", "items": items, "diferencias": dif,
                     "fecha_guia": order.fecha_compromiso.isoformat() if order.fecha_compromiso else date.today().isoformat(),
                     "generada_ts": now().isoformat(timespec="minutes"), "cambios": []}
    alerts.emit("GUIA_POR_VALIDAR", f"Pre-guía de la OV {order.numero} por validar",
                f"{order.customer.nombre}. " + ("Diferencias con la OV: " + "; ".join(dif) + "." if dif else "Preparado igual a la OV."),
                "SalesOrder", order.id, prioridad="ALTA" if dif else None, dedup_key=f"PREGUIA:{order.id}", creado_por=user)
    return order.preguia


def validate(user, order, aprobar, observacion="", fecha_guia=None):
    _guarda(user)
    pg = dict(order.preguia or {})
    if pg.get("estado") not in ("POR_VALIDAR", "OBSERVADA"):
        raise BusinessError("La OV no tiene una pre-guía por validar.")
    if not aprobar and not (observacion or "").strip():
        raise BusinessError("Indique qué se observa de la pre-guía.")
    if pg.get("diferencias") and aprobar and not (observacion or "").strip():
        raise BusinessError("La pre-guía tiene diferencias con la OV: indique por qué se valida así.")
    if fecha_guia:
        pg["fecha_guia"] = (fecha_guia if isinstance(fecha_guia, date) else date.fromisoformat(str(fecha_guia)[:10])).isoformat()
    pg.update({"estado": "VALIDADA" if aprobar else "OBSERVADA", "validado_por": user.nombre,
               "validado_ts": now().isoformat(timespec="minutes"), "observacion": (observacion or "").strip()})
    if aprobar:
        pg["sap"] = {"estado": "PENDIENTE"}
    order.preguia = pg
    st = _stop(order)
    if st is not None and aprobar:
        st.fecha_guia = date.fromisoformat(pg["fecha_guia"])
    alerts.close_by_system(f"PREGUIA:{order.id}", "Pre-guía validada" if aprobar else "Pre-guía observada")
    audit(user, "PREGUIA_VALIDADA" if aprobar else "PREGUIA_OBSERVADA", "SalesOrder", order.numero,
          {"observacion": observacion, "fecha_guia": pg.get("fecha_guia")})
    if aprobar:
        try_push(order, user)
    return pg


def try_push(order, user=None, sl=None):
    """Registra la guía en SAP (entrega basada en la OV) si la escritura está habilitada; si no, queda pendiente."""
    from . import sap_sl
    pg = dict(order.preguia or {})
    sap = dict(pg.get("sap") or {})
    try:
        if sap.get("docentry"):
            if sap.get("fecha_pendiente"):
                sap_sl.patch_delivery_date(sap["docentry"], pg["fecha_guia"], sl)
                sap.pop("fecha_pendiente", None)
                sap["estado"] = "ENVIADA"
        else:
            r = sap_sl.push_delivery(order, pg, sl)
            sap.update({"estado": "ENVIADA", "docnum": str(r.get("DocNum") or ""), "docentry": r.get("DocEntry")})
            _to_file(order, sap["docnum"], user)
        sap["error"] = ""
    except BusinessError as e:
        sap.update({"estado": "PENDIENTE", "error": str(e)[:250]})
    pg["sap"] = sap
    order.preguia = pg
    st = _stop(order)
    if st is not None and sap.get("docnum"):
        if not st.guia_numero:
            st.guia_numero, st.guia_origen = sap["docnum"], "SAP"
        st.guia_sap_docentry = sap.get("docentry")
    return sap


def _to_file(order, numero, user):
    """La guía registrada queda en el expediente del cliente (documentos de la OV)."""
    db().add(OrderAttachment(order_id=order.id, tipo="GUIA", nombre=f"Guía de remisión {numero} (SAP)",
                             archivo="", observacion="Registrada en SAP desde la pre-guía validada.",
                             user_id=user.id if user else None))


def change_date(user, order, nueva, motivo):
    _guarda(user)
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo del cambio de fecha (p. ej. el pedido sale mañana).")
    pg = dict(order.preguia or {})
    if not pg:
        raise BusinessError("La OV no tiene pre-guía ni guía.")
    nueva = nueva if isinstance(nueva, date) else date.fromisoformat(str(nueva)[:10])
    antes = pg.get("fecha_guia")
    if antes == nueva.isoformat():
        raise BusinessError("Es la misma fecha.")
    pg["fecha_guia"] = nueva.isoformat()
    pg["cambios"] = list(pg.get("cambios") or []) + [{"campo": "fecha", "de": antes, "a": nueva.isoformat(),
                                                      "motivo": motivo.strip(), "user": user.nombre, "origen": "MODULO",
                                                      "ts": now().isoformat(timespec="minutes")}]
    sap = dict(pg.get("sap") or {})
    if sap.get("docentry"):
        sap["fecha_pendiente"] = True
    pg["sap"] = sap
    order.preguia = pg
    st = _stop(order)
    if st is not None:
        st.fecha_guia = nueva
        st.guia_cambios = list(st.guia_cambios or []) + [pg["cambios"][-1]]
    audit(user, "GUIA_FECHA", "SalesOrder", order.numero, {"de": antes, "a": nueva.isoformat(), "motivo": motivo})
    if sap.get("docentry"):
        try_push(order, user)
    return pg


def apply_sap_date(order, guia, fecha):
    """Sincronización desde SAP: si la fecha de la guía cambió en SAP, se actualiza en el módulo (con rastro)."""
    pg = dict(order.preguia or {})
    sap = pg.get("sap") or {}
    if not pg or (sap.get("docnum") and guia not in (sap.get("docnum"),)) or not fecha:
        return False
    f = fecha.isoformat() if isinstance(fecha, date) else str(fecha)[:10]
    if pg.get("fecha_guia") == f:
        return False
    pg["cambios"] = list(pg.get("cambios") or []) + [{"campo": "fecha", "de": pg.get("fecha_guia"), "a": f, "motivo": "Cambio en SAP",
                                                      "user": "SAP", "origen": "SAP", "ts": now().isoformat(timespec="minutes")}]
    pg["fecha_guia"] = f
    order.preguia = pg
    st = _stop(order)
    if st is not None:
        st.fecha_guia = date.fromisoformat(f)
    return True


def pending_validation():
    return [o for o in db().execute(select(SalesOrder).where(SalesOrder.estado.in_(
        ("PREPARADA", "PROGRAMADA", "EN_PREPARACION")))).scalars() if (o.preguia or {}).get("estado") in ("POR_VALIDAR", "OBSERVADA")]


# ------------------------------------------------------------------ corte de rutas
def after_cutoff(fecha_despacho, ahora=None):
    """True si es para mañana y ya pasó la hora de corte de rutas (15:00 por defecto)."""
    corte = (param("hora_corte_rutas", "15:00") or "").strip()[:5]
    if not corte or fecha_despacho is None:
        return False
    ahora = ahora or datetime.now()
    return fecha_despacho == ahora.date() + timedelta(days=1) and f"{ahora:%H:%M}" > corte


def alert_after_cutoff(order, motivo, user=None, ahora=None):
    if not after_cutoff(order.fecha_compromiso, ahora):
        return False
    alerts.emit("RUTA_FUERA_CORTE", f"OV {order.numero} para mañana después del corte de rutas",
                f"{motivo} después de las {param('hora_corte_rutas', '15:00')}. {order.customer.nombre}, "
                f"{order.distrito or ''}. Confirme si se incluye en la ruta de mañana o se reprograma.",
                "SalesOrder", order.id, dedup_key=f"FUERA_CORTE:{order.id}", creado_por=user)
    return True


def check_route_planning(ahora=None):
    """Después de la hora de corte, si hay OV para mañana listas para despacho sin ruta, se avisa a Distribución
    (una vez por día): las rutas del día siguiente se planifican a más tardar a esa hora."""
    from .distribution import dispatchable_orders, orders_in_active_route
    ahora = ahora or datetime.now()
    corte = (param("hora_corte_rutas", "15:00") or "").strip()[:5]
    if not corte or f"{ahora:%H:%M}" <= corte:
        return 0
    manana = ahora.date() + timedelta(days=1)
    try:
        en_ruta = orders_in_active_route()
        sin = [o for o in dispatchable_orders(manana, require_prepared=False) if o.id not in en_ruta
               and o.fecha_compromiso == manana]
    except Exception:  # noqa: BLE001 - la verificación no debe detener las demás
        return 0
    if not sin:
        return 0
    alerts.emit("RUTA_FUERA_CORTE", f"Rutas de mañana sin planificar: {len(sin)} OV",
                f"Pasó la hora de corte ({corte}): " + ", ".join(o.numero for o in sin[:10]) + ". Planifique las rutas del "
                f"{manana:%d/%m/%Y}.", "Route", "", prioridad="ALTA", dedup_key=f"RUTAS_MANANA:{manana:%Y%m%d}")
    return 1
