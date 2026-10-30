"""Incidencias de distribución: paso 2 y flujo de devoluciones (V12, 29-oct-2026).

- Paso 1: se registra al momento en que sucede (registro existente de incidencias).
- Paso 2: al retornar el vehículo, en devoluciones, entregas parciales y cancelaciones se registra lo que realmente
  vuelve. Sin el paso 2 no se puede terminar el checklist de retorno.
- Con el paso 2 se crea una tarea a Almacén, que confirma lo recibido.
- Luego:
  - si la OV ya está facturada (factura registrada desde SAP o en la entrega), Administración y Finanzas valida si
    procede la nota de crédito y, con ambas confirmaciones, el Coordinador de Distribución la solicita mostrando la
    factura;
  - si no está facturada, el Coordinador de Distribución solicita la devolución.
- Coordinador y Asistente de Distribución, Jefe de Logística y Gerencia de Operaciones pueden modificar la incidencia;
  cada cambio queda registrado con su motivo.
"""
from sqlalchemy import select

from ..db import db
from ..models import CustomerInvoice, Incident, now
from . import alerts
from .core import BusinessError, audit, has_perm

TIPOS_RETORNO = ("DEVOLUCION", "CANCELACION", "RECHAZO_CALIDAD", "RECHAZO_OTRO", "CLIENTE_AUSENTE", "CLIENTE_NO_RETIRA",
                 "ENTREGA_PARCIAL", "LLEGADA_TARDE")


def needs_part2(i):
    return (i.entrega or "") in ("PARCIAL", "NINGUNA") or i.tipo in TIPOS_RETORNO


def invoice_of(i):
    """Factura de la OV de la incidencia (registrada desde SAP, por Finanzas o en la entrega)."""
    if i.order_id is None:
        return None
    f = db().execute(select(CustomerInvoice).where(CustomerInvoice.order_id == i.order_id,
                                                   CustomerInvoice.tipo == "FACTURA").order_by(CustomerInvoice.id.desc())
                     ).scalars().first()
    if f is not None:
        return {"numero": f.numero, "fecha": f.fecha.isoformat(), "monto": f.monto, "archivo": f.archivo, "origen": f.origen}
    from ..models import RouteStop
    st = db().get(RouteStop, i.stop_id) if i.stop_id else None
    if st is not None and st.factura_numero:
        return {"numero": st.factura_numero, "fecha": st.factura_ts.date().isoformat() if st.factura_ts else "",
                "monto": None, "archivo": st.factura_path, "origen": "ENTREGA"}
    return None


def _flujo(i, paso, datos):
    f = dict(i.flujo or {})
    f[paso] = dict(f.get(paso) or {}, **datos)
    i.flujo = f


def register_part2(user, i, lineas, observacion=""):
    """lineas: [{producto, cantidad}] lo que realmente vuelve al almacén."""
    if not (has_perm(user, "distribucion.incidencia") or has_perm(user, "distribucion.incidencia_editar")):
        raise BusinessError("Registra el paso 2 quien registró la incidencia o Distribución.")
    if not needs_part2(i):
        raise BusinessError("Esta incidencia no tiene retorno de mercadería.")
    if (i.parte2 or {}).get("ts"):
        raise BusinessError("El paso 2 ya fue registrado.")
    filas = []
    for x in lineas or []:
        try:
            q = float(x.get("cantidad") or 0)
        except (TypeError, ValueError):
            raise BusinessError("Cantidad devuelta inválida.")
        if q < 0:
            raise BusinessError("La cantidad devuelta no puede ser negativa.")
        if (x.get("producto") or "").strip():
            filas.append({"producto": x["producto"].strip(), "cantidad": q})
    if not filas:
        raise BusinessError("Indique lo que retorna (producto y cantidad).")
    i.parte2 = {"lineas": filas, "observacion": (observacion or "").strip(), "user": user.nombre, "user_id": user.id,
                "ts": now().isoformat(timespec="minutes")}
    _flujo(i, "almacen", {"estado": "PENDIENTE"})
    alerts.emit("INCIDENCIA_ALMACEN", f"Confirmar retorno de la incidencia #{i.id}" + (f" (OV {i.order.numero})" if i.order else ""),
                "Retorna: " + "; ".join(f"{x['producto']} × {x['cantidad']:g}" for x in filas) + ".",
                "Incident", i.id, dedup_key=f"INC_ALM:{i.id}", creado_por=user)
    if i.grupo == "CALIDAD":  # V13: la devolución por causa de calidad la evalúa Calidad
        alerts.emit("DEVOLUCION_CALIDAD", f"Devolución por calidad: incidencia #{i.id}" + (f" (OV {i.order.numero})" if i.order else ""),
                    "Retorna: " + "; ".join(f"{x['producto']} × {x['cantidad']:g}" for x in filas) + ". Evalúe el producto devuelto.",
                    "Incident", i.id, dedup_key=f"DEV_CAL:{i.id}", creado_por=user)
    audit(user, "INCIDENCIA_PASO2", "Incident", i.id, i.parte2)
    return i


def warehouse_confirm(user, i, conforme, observacion=""):
    if not (has_perm(user, "stock.cambiar_estado") or has_perm(user, "stock.autorizar_carga")):
        raise BusinessError("Confirma lo devuelto Almacén.")
    if (i.flujo or {}).get("almacen", {}).get("estado") != "PENDIENTE":
        raise BusinessError("La incidencia no está pendiente de Almacén.")
    if not conforme and not (observacion or "").strip():
        raise BusinessError("Indique la diferencia encontrada.")
    _flujo(i, "almacen", {"estado": "CONFORME" if conforme else "CON_DIFERENCIA", "observacion": (observacion or "").strip(),
                          "user": user.nombre, "ts": now().isoformat(timespec="minutes")})
    alerts.close_by_system(f"INC_ALM:{i.id}", "Almacén confirmó lo devuelto")
    fac = invoice_of(i)
    if fac:
        _flujo(i, "finanzas", {"estado": "PENDIENTE", "factura": fac})
        alerts.emit("INCIDENCIA_NC", f"Validar nota de crédito: incidencia #{i.id}, factura {fac['numero']}",
                    f"La OV {i.order.numero if i.order else ''} está facturada ({fac['numero']}). Almacén: "
                    f"{'conforme' if conforme else 'con diferencia: ' + observacion}.", "Incident", i.id,
                    dedup_key=f"INC_NC:{i.id}", creado_por=user)
    else:
        _flujo(i, "devolucion", {"estado": "PENDIENTE", "tipo": "SOLICITUD_DEVOLUCION"})
        alerts.emit("INCIDENCIA_DEVOLUCION", f"Solicitar devolución: incidencia #{i.id}",
                    f"La OV {i.order.numero if i.order else ''} no está facturada: registre la solicitud de devolución.",
                    "Incident", i.id, dedup_key=f"INC_DEV:{i.id}", creado_por=user)
    audit(user, "INCIDENCIA_ALMACEN", "Incident", i.id, {"conforme": conforme, "observacion": observacion})
    return i


def finance_validate(user, i, procede, observacion=""):
    if not has_perm(user, "finanzas.gestionar"):
        raise BusinessError("Valida la nota de crédito Administración y Finanzas.")
    if (i.flujo or {}).get("finanzas", {}).get("estado") != "PENDIENTE":
        raise BusinessError("La incidencia no está pendiente de Finanzas.")
    if not (observacion or "").strip():
        raise BusinessError("Indique el sustento de la validación.")
    _flujo(i, "finanzas", {"estado": "PROCEDE_NC" if procede else "NO_PROCEDE", "observacion": observacion.strip(),
                           "user": user.nombre, "ts": now().isoformat(timespec="minutes")})
    alerts.close_by_system(f"INC_NC:{i.id}", "Finanzas validó")
    if procede:
        fac = i.flujo["finanzas"].get("factura") or {}
        _flujo(i, "devolucion", {"estado": "PENDIENTE", "tipo": "SOLICITUD_NC", "factura": fac.get("numero")})
        alerts.emit("INCIDENCIA_DEVOLUCION", f"Solicitar nota de crédito: incidencia #{i.id}, factura {fac.get('numero')}",
                    "Almacén y Finanzas confirmaron: solicite la nota de crédito.", "Incident", i.id,
                    dedup_key=f"INC_DEV:{i.id}", creado_por=user)
    audit(user, "INCIDENCIA_FINANZAS", "Incident", i.id, {"procede": procede, "observacion": observacion})
    return i


def request_return(user, i, numero, observacion=""):
    """El Coordinador de Distribución registra la solicitud de devolución o de nota de crédito."""
    if not has_perm(user, "distribucion.programar"):
        raise BusinessError("La solicitud la registra el Coordinador de Distribución.")
    dv = (i.flujo or {}).get("devolucion", {})
    if dv.get("estado") != "PENDIENTE":
        raise BusinessError("No hay una solicitud de devolución o nota de crédito pendiente.")
    if not (numero or "").strip():
        raise BusinessError("Indique el número de la solicitud.")
    _flujo(i, "devolucion", {"estado": "SOLICITADA", "numero": numero.strip(), "observacion": (observacion or "").strip(),
                             "user": user.nombre, "ts": now().isoformat(timespec="minutes")})
    alerts.close_by_system(f"INC_DEV:{i.id}", f"Solicitud {numero} registrada")
    i.estado = "CERRADA"
    audit(user, "INCIDENCIA_SOLICITUD", "Incident", i.id, {"tipo": dv.get("tipo"), "numero": numero})
    return i


EDITABLES = ("descripcion", "tipo", "cantidad_afectada", "estado")


def edit(user, i, cambios, motivo):
    if not has_perm(user, "distribucion.incidencia_editar"):
        raise BusinessError("Modifican la incidencia Distribución, el Jefe de Logística o Gerencia de Operaciones.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo de la modificación.")
    from ..catalogs import INCIDENT_TYPES
    antes, despues = {}, {}
    for k in EDITABLES:
        if k in cambios and cambios[k] not in (None, ""):
            v = cambios[k]
            if k == "tipo" and v not in dict(INCIDENT_TYPES):
                raise BusinessError("Subtipo de incidencia no válido.")
            if k == "cantidad_afectada":
                v = float(v)
            if getattr(i, k) != v:
                antes[k], despues[k] = getattr(i, k), v
                setattr(i, k, v)
    if not despues:
        raise BusinessError("No hay cambios.")
    i.historial = list(i.historial or []) + [{"antes": antes, "despues": despues, "motivo": motivo.strip(),
                                              "user": user.nombre, "rol": user.role_code,
                                              "ts": now().isoformat(timespec="minutes")}]
    audit(user, "INCIDENCIA_MODIFICADA", "Incident", i.id, {"antes": antes, "despues": despues, "motivo": motivo})
    return i


def pending_for(user):
    """Incidencias con un paso del flujo pendiente que le corresponde al usuario."""
    out = []
    for i in db().execute(select(Incident).where(Incident.estado != "CERRADA").order_by(Incident.id.desc()).limit(300)).scalars():
        f = i.flujo or {}
        if needs_part2(i) and not (i.parte2 or {}).get("ts") and has_perm(user, "distribucion.incidencia"):
            out.append((i, "Paso 2: registrar lo que retorna"))
        elif f.get("almacen", {}).get("estado") == "PENDIENTE" and has_perm(user, "stock.cambiar_estado"):
            out.append((i, "Almacén: confirmar lo devuelto"))
        elif f.get("finanzas", {}).get("estado") == "PENDIENTE" and has_perm(user, "finanzas.gestionar"):
            out.append((i, "Finanzas: validar nota de crédito"))
        elif f.get("devolucion", {}).get("estado") == "PENDIENTE" and has_perm(user, "distribucion.programar"):
            out.append((i, "Solicitar " + ("nota de crédito" if f["devolucion"].get("tipo") == "SOLICITUD_NC" else "devolución")))
    return out
