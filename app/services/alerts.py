"""Motor de alertas y tareas (IF §14; observaciones al demo v0.6).

- Canales: panel del módulo y correo (correo real solo si hay SMTP configurado; si no, queda en bandeja
  con estado SIN_SMTP, sin simular el envío). Celular: etapa futura (no implementado).
- Naturaleza por tipo: TAREA (requiere aprobación o atención) o INFORMATIVA (solo se reconoce). No toda notificación
  es una tarea. Además, una tarea que el perfil no puede aprobar, desestimar, designar ni ejecutar se le presenta como
  información (obs. demo v0.7): la atiende quien corresponde.
- Estados de una tarea: PENDIENTE (requiere atención) -> EN_EJECUCION (un responsable comenzó) -> COMPLETADA (acción
  finalizada con su evidencia) o DESAPROBADA (desistida/desaprobada con motivo). INCIDENCIA: discrepancia o impedimento;
  no cierra ni elimina la tarea: registra situación, acciones, responsable y resolución, y al resolverse la tarea
  vuelve a su estado anterior. Una tarea completada puede dejar un proceso posterior pendiente (recepción,
  contabilización).
- Una alerta informativa se RECONOCE (queda leída) sin pasar por los estados de tarea.
- Designar: solo a personas o cargos de la misma área de quien designa (respeta la línea de comunicación); el
  designado recibe la alerta TAREA_ASIGNADA y la ve en su inicio. «En ejecución» y «Completar» aparecen solo cuando la
  tarea tiene responsable.
- Visibilidad: destinatarios por rol/usuario y área; Gerencia General, Gerencia de Operaciones y Sistemas ven todo.
"""
from sqlalchemy import select

from ..db import db
from ..models import Alert, AlertEvent, AlertIncident, AlertType, EmailOutbox, GGAlertPreference, Role, User, now
from .core import BusinessError, audit, has_perm, param, roles_of, users_with_roles

ESTADOS_TAREA = ["PENDIENTE", "EN_EJECUCION", "INCIDENCIA", "COMPLETADA", "DESAPROBADA"]
ESTADOS_INFO = ["PENDIENTE", "RECONOCIDA"]
ESTADOS = ["PENDIENTE", "EN_EJECUCION", "INCIDENCIA", "COMPLETADA", "DESAPROBADA", "RECONOCIDA"]
CERRADOS = ("COMPLETADA", "DESAPROBADA", "RECONOCIDA")
ESTADO_TXT = {"PENDIENTE": "Pendiente", "EN_EJECUCION": "En ejecución", "INCIDENCIA": "Incidencia",
              "COMPLETADA": "Completada", "DESAPROBADA": "Desistida / desaprobada", "RECONOCIDA": "Reconocida"}
VEN_TODO = ("GERENCIA_GENERAL", "GERENTE_GENERAL_ADJUNTO", "GERENCIA_OPERACIONES", "SISTEMAS")
PRIORIDAD_ORDEN = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}


def emit(type_code, titulo, mensaje="", entidad="", entidad_id="", prioridad=None, extra_roles=None,
         extra_users=None, dedup_key="", creado_por=None):
    """Crea una alerta según la configuración de su tipo. Devuelve la alerta (o la existente si dedup)."""
    s = db()
    t = s.get(AlertType, type_code)
    if t is None:
        raise BusinessError(f"Tipo de alerta no configurado: {type_code}")
    if not t.activo:
        return None
    if dedup_key:
        existing = s.execute(select(Alert).where(Alert.dedup_key == dedup_key, Alert.estado.notin_(CERRADOS))).scalars().first()
        if existing:
            return existing
    roles = list(dict.fromkeys((t.roles or []) + (extra_roles or [])))
    roles = _filter_by_warehouse(roles, entidad, entidad_id)
    usuarios = list(dict.fromkeys((t.usuarios or []) + [u for u in (extra_users or []) if u]))
    a = Alert(type_code=type_code, titulo=titulo[:250], mensaje=mensaje, prioridad=prioridad or t.prioridad,
              area=t.area, entidad=entidad, entidad_id=str(entidad_id), roles=roles, usuarios=usuarios,
              dedup_key=dedup_key, creado_por=creado_por.id if creado_por else None)
    s.add(a)
    s.flush()
    s.add(AlertEvent(alert_id=a.id, user_id=creado_por.id if creado_por else None, accion="CREADA",
                     comentario=f"Destinatarios: roles {', '.join(roles) or '-'}; usuarios {usuarios or '-'}"))
    if t.enviar_correo and param("correo_habilitado", False):
        _queue_emails(a, t, roles, usuarios)
    return a


def entity_warehouses(entidad, entidad_id):
    """Almacenes involucrados en la entidad de la alerta (para dirigirla al coordinador que corresponde, Q17)."""
    from ..models import (Liquidation, ProductionRequest, PurchaseRequest, RepackRequest, Route, SalesOrder, StockLot,
                          Transfer, Product, PhysicalCount, ImportShipment)
    from .stock import principal_warehouses
    s = db()
    try:
        eid = int(entidad_id)
    except (TypeError, ValueError):
        return set()

    def principal(code):
        p = s.get(Product, code)
        return {w.code for w in principal_warehouses(p)} if p else set()

    def order_whs(o):
        out = set()
        for l in o.lines:
            out |= principal(l.product_code)
            out |= {r.lot.warehouse_code for r in l.reservations if r.estado == "ACTIVA"}
        return out
    obj = None
    model = {"SalesOrder": SalesOrder, "StockLot": StockLot, "Transfer": Transfer, "PurchaseRequest": PurchaseRequest,
             "RepackRequest": RepackRequest, "Liquidation": Liquidation, "ProductionRequest": ProductionRequest,
             "Route": Route, "PhysicalCount": PhysicalCount, "ImportShipment": ImportShipment}.get(entidad)
    if model is not None:
        obj = s.get(model, eid)
    if obj is None:
        return set()
    if entidad == "SalesOrder":
        return order_whs(obj)
    if entidad in ("StockLot", "PhysicalCount"):
        return {obj.warehouse_code}
    if entidad == "Transfer":
        return {obj.lot.warehouse_code, obj.destino_code}
    if entidad == "PurchaseRequest":
        return {obj.warehouse_code} if obj.warehouse_code else principal(obj.product_code)
    if entidad == "ImportShipment":
        return {obj.warehouse_code} if obj.warehouse_code else principal(obj.product_code)
    if entidad == "RepackRequest":
        return {obj.lot.warehouse_code}
    if entidad == "Liquidation":
        return {param("almacen_transito_produccion", "ALM-003")} | principal(obj.product_code)
    if entidad == "ProductionRequest":
        return principal(obj.product_code)
    if entidad == "Route":
        out = set()
        for st in obj.stops:
            out |= order_whs(st.order)
        return out
    return set()


def _filter_by_warehouse(roles, entidad, entidad_id):
    """Quita los coordinadores cuyo almacén no está involucrado. Si no se puede determinar, avisa a todos."""
    from .core import warehouse_scopes, wh_in
    # solo se dirige entre coordinadores de almacén; Logística recibe sus alertas sin filtrar
    scopes = {r: v for r, v in warehouse_scopes().items() if r.startswith("COORD_ALMACEN")}
    if not any(r in scopes for r in roles):
        return roles
    whs = entity_warehouses(entidad, entidad_id)
    if not whs:
        return roles
    filtrados = [r for r in roles if r not in scopes or any(wh_in(w, scopes[r]) for w in whs)]
    if not any(r in scopes for r in filtrados):  # ningún almacén asignado involucrado: avisa a todos los coordinadores
        return roles
    return filtrados


def _queue_emails(alert, t, roles, usuarios):
    s = db()
    destinatarios = {u.id: u for u in users_with_roles(roles)}
    for uid in usuarios:
        u = s.get(User, uid)
        if u and u.activo:
            destinatarios[u.id] = u
    # Gerencia General recibe directamente solo los tipos configurados (IF §14)
    for u in list(destinatarios.values()):
        if u.role_code in ("GERENCIA_GENERAL", "GERENTE_GENERAL_ADJUNTO"):
            pref = s.execute(select(GGAlertPreference).where(GGAlertPreference.user_id == u.id,
                                                             GGAlertPreference.type_code == t.code)).scalars().first()
            if not (pref and pref.recibir_directo):
                destinatarios.pop(u.id)
    for u in destinatarios.values():
        if not u.email:
            continue
        s.add(EmailOutbox(alert_id=alert.id, destinatario=u.email,
                          asunto=f"[{alert.prioridad}] {alert.titulo}",
                          cuerpo=f"{alert.mensaje}\n\nTipo: {t.nombre}\nÁrea: {alert.area}\nAlerta #{alert.id}"))


# ------------------------------ visibilidad --------------------------------
def visible_alerts(user, estado=None, area=None, prioridad=None, grupo=None, type_code=None, solo_abiertas=False):
    """Alertas visibles para el usuario con filtros (área, estado, urgencia, grupo/tipo). IF §14, §22."""
    q = select(Alert).order_by(Alert.creado_ts.desc(), Alert.id.desc())
    if estado:
        q = q.where(Alert.estado == estado)
    if solo_abiertas:
        q = q.where(Alert.estado.notin_(CERRADOS))
    if area:
        q = q.where(Alert.area == area)
    if prioridad:
        q = q.where(Alert.prioridad == prioridad)
    if type_code:
        q = q.where(Alert.type_code == type_code)
    rows = [a for a in db().execute(q).scalars() if can_see(user, a)]
    if grupo:
        rows = [a for a in rows if a.type and a.type.grupo == grupo]
    return rows


def user_area(user):
    return user.role.area if user is not None and user.role is not None else ""


def sees_all(user):
    return user is not None and (user.role_code in VEN_TODO or has_perm(user, "alertas.ver_todas"))


def inbox(user, **filtros):
    """Alertas visibles del usuario limitadas a los tipos de su área (o que se comunican con ella) y a lo designado."""
    rows = visible_alerts(user, **filtros)
    if sees_all(user):
        return rows
    codes = {t.code for t in visible_types(user)}
    return [a for a in rows if a.type_code in codes or is_assignee(user, a)]


def can_see(user, alert):
    if user is None:
        return False
    if sees_all(user):
        return True
    roles = roles_of(user)
    return (bool(roles & set(alert.roles or [])) or user.id in (alert.usuarios or []) or alert.asignado_a == user.id
            or (alert.asignado_rol and alert.asignado_rol in roles))


def visible_types(user):
    """Tipos de alerta que el usuario puede filtrar: los de su área o los que se comunican con su área (su rol es
    destinatario). Gerencias y Sistemas ven todos."""
    tipos = list(db().execute(select(AlertType).order_by(AlertType.area, AlertType.nombre)).scalars())
    if sees_all(user):
        return tipos
    area = user_area(user)
    roles = roles_of(user)
    return [t for t in tipos if t.area == area or roles & set(t.roles or [])]


def is_task(alert):
    return (alert.type.naturaleza if alert.type else "TAREA") != "INFORMATIVA"


def can_act(user, alert):
    """¿El perfil puede accionar la tarea: aprobarla o desestimarla, designarla o ejecutarla? (obs. demo v0.7: todo lo
    que el perfil no pueda aprobar, desestimar o asignar se le presenta como información)."""
    from .alert_actions import HANDLERS, user_can_decide
    if user is None or not is_task(alert):
        return False
    if is_assignee(user, alert):
        return True
    if alert.type_code in HANDLERS:
        if user_can_decide(user, alert):
            return True
    if has_perm(user, "alertas.gestionar") and user_area(user) == alert.area:
        return True  # designa dentro de su área
    return has_perm(user, "tareas.ejecutar") and bool(roles_of(user) & set(alert.roles or []))


def nature_for(user, alert):
    """Naturaleza con la que el usuario ve la alerta: TAREA solo si puede accionarla; si no, INFORMATIVA."""
    return "TAREA" if can_act(user, alert) else "INFORMATIVA"


def is_closed(alert):
    return alert.estado in CERRADOS


def is_assignee(user, alert):
    return alert.asignado_a == user.id or (bool(alert.asignado_rol) and alert.asignado_rol in roles_of(user))


def assignable(user):
    """Personas y cargos a los que el usuario puede designar: solo de su misma área."""
    s = db()
    area = user_area(user)
    roles = list(s.execute(select(Role).where(Role.area == area).order_by(Role.nombre)).scalars())
    codes = {r.code for r in roles}
    users = [u for u in s.execute(select(User).where(User.activo.is_(True)).order_by(User.nombre)).scalars()
             if u.role_code in codes]
    return users, roles


def my_tasks(user):
    """Tareas abiertas designadas al usuario o a su cargo (panel de inicio)."""
    q = select(Alert).where(Alert.estado.notin_(CERRADOS)).order_by(Alert.creado_ts.desc())
    return [a for a in db().execute(q).scalars() if is_assignee(user, a)]


def _check(user, alert):
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if not has_perm(user, "alertas.gestionar") and not is_assignee(user, alert):
        raise BusinessError("Su rol no puede gestionar alertas.")
    if is_closed(alert):
        raise BusinessError("La alerta ya está cerrada.")


def _event(alert, user, accion, comentario=""):
    db().add(AlertEvent(alert_id=alert.id, user_id=user.id if user else None, accion=accion, comentario=comentario))


# ------------------------------- ciclo de vida -----------------------------
def assign(alert, user, assignee_id=None, comentario="", rol=None):
    """Designa la tarea a una persona o a un cargo de la misma área de quien designa."""
    _check(user, alert)
    if not is_task(alert):
        raise BusinessError("Las alertas informativas no se designan: solo se reconocen.")
    s = db()
    area = user_area(user)
    if assignee_id:
        assignee = s.get(User, int(assignee_id))
        if assignee is None or not assignee.activo:
            raise BusinessError("Usuario no encontrado.")
        if user_area(assignee) != area:
            raise BusinessError("Solo puede designar a personas de su misma área; el sistema deriva a las otras áreas "
                                "según las reglas del proceso.")
        alert.asignado_a, alert.asignado_rol = assignee.id, ""
        destino, extra = assignee.nombre, {"extra_users": [assignee.id]}
        if assignee.id not in (alert.usuarios or []):
            alert.usuarios = (alert.usuarios or []) + [assignee.id]
    elif rol:
        r = s.get(Role, rol)
        if r is None or r.area != area:
            raise BusinessError("Solo puede designar a cargos de su misma área.")
        alert.asignado_a, alert.asignado_rol = None, r.code
        destino, extra = r.nombre, {"extra_roles": [r.code]}
    else:
        raise BusinessError("Indique la persona o el cargo a designar.")
    alert.asignado_por = user.id
    if alert.estado != "INCIDENCIA":
        alert.estado = "PENDIENTE"
    _event(alert, user, "DESIGNADA", f"Designada a {destino}. {comentario}".strip())
    audit(user, "ALERTA_DESIGNADA", "Alert", alert.id, {"asignado_a": alert.asignado_a, "rol": alert.asignado_rol})
    emit("TAREA_ASIGNADA", f"Le designaron la tarea #{alert.id}: {alert.titulo}"[:250],
         f"Designada por {user.nombre}. {comentario}".strip(), "Alert", alert.id, prioridad=alert.prioridad,
         creado_por=user, dedup_key=f"TAREA_ASIGNADA:{alert.id}:{alert.asignado_a or alert.asignado_rol}", **extra)


def take(alert, user, comentario=""):
    """Tomar la tarea (designársela a uno mismo)."""
    assign(alert, user, user.id, comentario or "Tomada por el responsable.")


def attend(alert, user, comentario=""):
    """En ejecución: solo cuando la tarea tiene responsable, y lo marca el responsable."""
    _check(user, alert)
    if not (alert.asignado_a or alert.asignado_rol):
        raise BusinessError("La tarea no tiene responsable: tómela o desígnela primero.")
    if not is_assignee(user, alert):
        raise BusinessError("Solo el responsable designado marca la tarea en ejecución.")
    if alert.estado == "INCIDENCIA":
        raise BusinessError("La tarea tiene una incidencia abierta: resuélvala primero.")
    alert.estado = "EN_EJECUCION"
    if not alert.asignado_a:
        alert.asignado_a = user.id
    _event(alert, user, "EN_EJECUCION", comentario)
    audit(user, "ALERTA_EN_EJECUCION", "Alert", alert.id)


def start_with_photo(alert, user, foto, comentario=""):
    """Tarea operativa (montacarguista, auxiliar): indica que inició con una foto; no designa a nadie."""
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if not has_perm(user, "tareas.ejecutar"):
        raise BusinessError("Su rol no ejecuta tareas operativas.")
    if is_closed(alert) or alert.estado == "INCIDENCIA":
        raise BusinessError("La tarea no está pendiente.")
    if alert.asignado_a and alert.asignado_a != user.id:
        raise BusinessError("La tarea la está ejecutando otra persona.")
    if not foto:
        raise BusinessError("Tome la foto al iniciar la tarea.")
    alert.asignado_a = user.id
    alert.estado = "EN_EJECUCION"
    alert.foto_inicio = foto
    _event(alert, user, "EN_EJECUCION", f"Inició con foto. {comentario}".strip())
    audit(user, "TAREA_INICIADA_CON_FOTO", "Alert", alert.id, {"foto": foto})


def finish_with_photo(alert, user, foto, observacion=""):
    if not is_assignee(user, alert) or alert.estado != "EN_EJECUCION":
        raise BusinessError("Primero inicie la tarea con su foto.")
    if not foto:
        raise BusinessError("Tome la foto al terminar la tarea.")
    complete(alert, user, observacion.strip() or "Terminada", "Terminada con foto", evidencia=foto)


def comment(alert, user, texto):
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if not texto.strip():
        raise BusinessError("El comentario está vacío.")
    _event(alert, user, "COMENTARIO", texto.strip())


def complete(alert, user, motivo, accion, evidencia="", proceso_pendiente=""):
    """Completada: la acción terminó y se registró la evidencia. Puede quedar un proceso posterior pendiente."""
    _check(user, alert)
    if not is_task(alert):
        raise BusinessError("Las alertas informativas se reconocen, no se completan.")
    if not (alert.asignado_a or alert.asignado_rol):
        raise BusinessError("La tarea no tiene responsable: tómela o desígnela primero.")
    if not (is_assignee(user, alert) or alert.asignado_por == user.id or sees_all(user)):
        raise BusinessError("Completa la tarea su responsable o quien la designó.")
    if alert.estado == "INCIDENCIA":
        raise BusinessError("La tarea tiene una incidencia abierta: resuélvala primero.")
    if not (motivo or "").strip() or not (accion or "").strip():
        raise BusinessError("Para completar se requiere el detalle y la acción tomada (evidencia).")
    desde = last_id()
    _finish(alert, user, "COMPLETADA", motivo.strip(), accion.strip(), "ATENDIDA")
    db().flush()
    mark_derived(alert, desde, user)
    alert.evidencia = evidencia or alert.evidencia
    alert.proceso_pendiente = (proceso_pendiente or "").strip()
    audit(user, "ALERTA_COMPLETADA", "Alert", alert.id, {"motivo": motivo, "accion": accion, "evidencia": evidencia,
                                                        "proceso_pendiente": alert.proceso_pendiente})


def close(alert, user, motivo, accion):
    """Compatibilidad: cerrar = completar (tarea) o reconocer (informativa)."""
    if not is_task(alert):
        return acknowledge(alert, user, motivo)
    if not (alert.asignado_a or alert.asignado_rol):
        _check(user, alert)
        alert.asignado_a = user.id
    return complete(alert, user, motivo, accion)


def acknowledge(alert, user, comentario=""):
    """Alerta informativa: se reconoce (leída) sin convertirse en tarea."""
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if is_task(alert):
        raise BusinessError("Esta alerta es una tarea: requiere responsable y se completa con su evidencia.")
    if is_closed(alert):
        raise BusinessError("La alerta ya está cerrada.")
    _finish(alert, user, "RECONOCIDA", comentario.strip() or "Leída", "Reconocida", "RECONOCIDA")


def _finish(alert, user, estado, motivo, accion, resultado):
    alert.estado = estado
    alert.resultado = resultado
    alert.cerrado_ts = now()
    alert.cerrado_por = user.id if user else None
    alert.motivo_cierre = motivo
    alert.accion_tomada = accion
    _event(alert, user, estado, f"Motivo: {motivo} | Acción: {accion}")


def open_incident(alert, user, situacion, acciones="", responsable_id=None):
    """Incidencia: discrepancia o impedimento. No cierra ni elimina la tarea original."""
    _check(user, alert)
    if not (situacion or "").strip():
        raise BusinessError("Describa la situación de la incidencia.")
    s = db()
    resp = s.get(User, int(responsable_id)) if responsable_id else user
    if resp is None:
        raise BusinessError("Responsable no encontrado.")
    inc = AlertIncident(alert_id=alert.id, situacion=situacion.strip(), acciones=(acciones or "").strip(),
                        responsable_id=resp.id, creado_por=user.id, estado_previo=alert.estado)
    s.add(inc)
    if resp.id not in (alert.usuarios or []):  # el responsable de la incidencia ve la tarea
        alert.usuarios = (alert.usuarios or []) + [resp.id]
    alert.estado = "INCIDENCIA"
    _event(alert, user, "INCIDENCIA", f"{situacion.strip()} · Responsable: {resp.nombre}")
    audit(user, "ALERTA_INCIDENCIA", "Alert", alert.id, {"situacion": situacion, "responsable": resp.id})
    return inc


def resolve_incident(inc, user, resolucion, acciones=""):
    alert = inc.alert
    if not can_see(user, alert):
        raise BusinessError("No tiene visibilidad sobre esta alerta.")
    if inc.estado != "ABIERTA":
        raise BusinessError("La incidencia ya está resuelta.")
    if not (resolucion or "").strip():
        raise BusinessError("Registre la resolución de la incidencia.")
    inc.resolucion = resolucion.strip()
    if acciones:
        inc.acciones = (inc.acciones + "\n" if inc.acciones else "") + acciones.strip()
    inc.estado = "RESUELTA"
    inc.resuelto_ts = now()
    inc.resuelto_por = user.id
    if not any(i.estado == "ABIERTA" for i in alert.incidents if i is not inc):
        alert.estado = inc.estado_previo if inc.estado_previo in ("PENDIENTE", "EN_EJECUCION") else "PENDIENTE"
    _event(alert, user, "INCIDENCIA_RESUELTA", resolucion.strip())
    audit(user, "ALERTA_INCIDENCIA_RESUELTA", "Alert", alert.id, {"incidencia": inc.id, "resolucion": resolucion})


def close_by_system(dedup_key, motivo):
    """Completa automáticamente alertas abiertas cuya condición desapareció (p.ej. faltante cubierto o aprobación
    registrada en su pantalla). No toca las que tienen una incidencia abierta."""
    for a in db().execute(select(Alert).where(Alert.dedup_key == dedup_key, Alert.estado.notin_(CERRADOS))).scalars():
        if a.estado == "INCIDENCIA":
            _event(a, None, "COMENTARIO", f"Sistema: {motivo} (la incidencia sigue abierta)")
            continue
        a.estado = "COMPLETADA" if is_task(a) else "RECONOCIDA"
        a.resultado = a.resultado or "SISTEMA"
        a.cerrado_ts = now()
        a.motivo_cierre = motivo
        a.accion_tomada = "Cierre automático por el sistema: la condición ya no se cumple o se resolvió en su pantalla."
        _event(a, None, a.estado, f"Sistema: {motivo}")


# ------------------------------ derivación ---------------------------------
ESTADO_TXT["DERIVADA"] = "Derivada a otra área"


def get(aid):
    return db().get(Alert, aid)


def last_id():
    from sqlalchemy import func
    return db().execute(select(func.max(Alert.id))).scalar() or 0


def mark_derived(alert, desde_id, user=None):
    """Registra las tareas que el sistema generó para otra área como consecuencia de esta (aprobación o cierre)."""
    nuevas = [x for x in db().execute(select(Alert).where(Alert.id > desde_id)).scalars()
              if x.id != alert.id and x.area != alert.area and is_task(x)]
    if nuevas:
        alert.derivadas = list(dict.fromkeys((alert.derivadas or []) + [x.id for x in nuevas]))
        _event(alert, user, "DERIVADA", "Derivada a " + ", ".join(sorted({x.area for x in nuevas}))
               + " (tareas " + ", ".join(f"#{x.id}" for x in nuevas) + ")")
    return nuevas


def display_state(alert):
    """(clase, texto) del estado a mostrar: si la tarea se derivó a otra área y allí sigue abierta, se muestra
    «Derivada · pendiente <área>» para el análisis; cuando el área destino la cierra, el estado propio."""
    if alert.derivadas:
        abiertas = [x for x in (db().get(Alert, i) for i in alert.derivadas) if x is not None and x.estado not in CERRADOS]
        if abiertas:
            return "DERIVADA", "Derivada · pendiente " + ", ".join(sorted({x.area for x in abiertas}))
    return alert.estado, ESTADO_TXT.get(alert.estado, alert.estado)


def by_priority(user, rows):
    """V7: orden del panel de alertas: abiertas antes que cerradas; dentro de ellas, las que requieren acción del usuario
    (tareas) antes que las informativas; luego por urgencia (ALTA, MEDIA, BAJA) y las más recientes primero."""
    def key(a):
        cerrada = a.estado in CERRADOS
        accion = nature_for(user, a) == "TAREA"
        return (cerrada, not accion, PRIORIDAD_ORDEN.get(a.prioridad, 9), -(a.creado_ts.timestamp() if a.creado_ts else 0), -a.id)
    return sorted(rows, key=key)
