"""Personal de Producción y asistencia (ronda 23-oct-2026): el Jefe de Producción y el asistente que lo tenga en su alcance
registran asistencia, falta, vacaciones, descanso médico o tardanza (la marcación de entrada y salida está en otro sistema)."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Attendance, Worker
from .core import BusinessError, audit, has_perm, param, user_scope


def area_of(user):
    """Área cuyo personal ve y registra el usuario: Producción, o la propia (p. ej. el Jefe de Logística, sección 5)."""
    if has_perm(user, "produccion.asistencia"):
        return "Producción"
    if has_perm(user, "personal.comercial") and not has_perm(user, "asistencia.area"):
        return "Comercial"  # V24: Jefatura Comercial registra a sus vendedores con su canal
    from .alerts import user_area
    return user_area(user) if has_perm(user, "asistencia.area") else None


def visible_areas(user):
    """V17: áreas cuyo personal ve el usuario. None = todas (Jefatura de Operaciones y Gerencias, permiso
    «asistencia.todas»). Almacén y Logística ven solo su propio personal, no el de Producción
    (parámetro «asistencia_areas_por_rol»; por defecto, el área del perfil)."""
    if has_perm(user, "asistencia.todas"):
        return None
    from .alerts import user_area
    out = set()
    if has_perm(user, "produccion.asistencia") and user_area(user) in ("Producción", ""):
        out.add("Producción")
    if has_perm(user, "asistencia.area") or has_perm(user, "asistencia.ver_area"):
        out |= set((param("asistencia_areas_por_rol", {}) or {}).get(user.role_code) or [user_area(user)])
    if has_perm(user, "personal.comercial"):
        out.add("Comercial")
    return out


def alta_config(area):
    """V24: qué se pide al registrar a un colaborador de esa área (parámetro «alta_personal_por_area»)."""
    cfg = (param("alta_personal_por_area", {}) or {}).get(area or "") or {}
    return {"campos": list(cfg.get("campos") or []), "puestos": list(cfg.get("puestos") or [])}


def workers_of(user, activos=False, ver=False):
    """Personal que el usuario registra (ver=False: su área) o que puede ver (ver=True: visible_areas)."""
    q = select(Worker).order_by(Worker.area, Worker.linea, Worker.nombre)
    if activos:
        q = q.where(Worker.activo.is_(True))
    if ver:
        areas = visible_areas(user)
        return [w for w in db().execute(q).scalars() if areas is None or (w.area or "Producción") in areas]
    area = area_of(user)
    return [w for w in db().execute(q).scalars() if (w.area or "Producción") == area] if area else []


def can_register(user):
    if has_perm(user, "personal.comercial") and not has_perm(user, "produccion.asistencia"):
        return True
    if has_perm(user, "asistencia.area") and not has_perm(user, "produccion.asistencia"):
        return True
    if not has_perm(user, "produccion.asistencia"):
        return False
    if user.role_code == "ASIST_PRODUCCION":
        sc = user_scope(user)
        return bool(sc.get("asistencia") or sc.get("permisos_de") == "JEFE_PRODUCCION")
    return True


def _require(user):
    if not can_register(user):
        raise BusinessError("Registra la asistencia el Jefe de Producción o el asistente designado.")


def states():
    return param("asistencia_estados", []) or []


def save_worker(user, datos, w=None):
    _require(user)
    nombre = (datos.get("nombre") or "").strip().upper()
    if not nombre:
        raise BusinessError("Indique el nombre del colaborador.")
    doc = (datos.get("documento") or "").strip()
    if doc and (not doc.isalnum() or len(doc) > 15):
        raise BusinessError("Documento inválido.")
    puesto = (datos.get("puesto") or "").strip()  # V18: puesto de la lista o «Otro» escrito
    if puesto == "__OTRO__":
        puesto = (datos.get("puesto_otro") or "").strip()
        if not puesto:
            raise BusinessError("Escriba el puesto («Otro»).")
    area = area_of(user) or "Producción"
    cfg = alta_config(area)
    # V24: cada área pide lo suyo: Producción línea y puesto (p. ej. maquinista); Comercial el canal; Limpieza y
    # Mantenimiento solo el colaborador; Logística el puesto (auxiliar de almacén o de despacho)
    linea = (datos.get("linea") or "").strip() if "linea" in cfg["campos"] or area == "Producción" else ""
    canal = (datos.get("canal") or "").strip() if "canal" in cfg["campos"] else ""
    if "canal" in cfg["campos"] and not canal:
        raise BusinessError("Indique el canal del vendedor.")
    if canal:
        from .prices import canales
        if canal not in canales():
            raise BusinessError(f"Canal no válido: {canal}.")
    if w is None:
        w = Worker(nombre=nombre)
        db().add(w)
    w.nombre, w.documento = nombre, doc
    w.area = area
    w.linea = linea
    w.canal = canal
    sub = (datos.get("sublinea") or "").strip() if "sublinea" in cfg["campos"] else ""
    w.puesto = puesto[:60]
    w.sublinea = (sub or puesto or "").strip()[:40]
    w.externo = str(datos.get("externo", "")) in ("1", "on", "true")
    w.activo = str(datos.get("activo", "1")) in ("1", "on", "true")
    db().flush()
    audit(user, "COLABORADOR_GUARDADO", "Worker", w.id, {"nombre": nombre, "area": area, "linea": w.linea,
                                                           "puesto": w.puesto, "canal": w.canal})
    return w


def register_day(user, fecha, marcas, observaciones=None, lineas=None):
    """marcas: {worker_id: estado}. Reemplaza el estado del día de cada colaborador. lineas (V18): {worker_id: línea}
    en la que trabajó ese día, si se reorganizó el equipo."""
    _require(user)
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    if fecha > date.today():
        raise BusinessError("No se registra asistencia de días futuros.")
    validos = set(states())
    n = 0
    for wid, estado in marcas.items():
        if not estado:
            continue
        if estado not in validos:
            raise BusinessError(f"Estado de asistencia no válido: {estado}.")
        w = db().get(Worker, int(wid))
        if w is None or (w.area or "Producción") != area_of(user):
            continue
        a = db().execute(select(Attendance).where(Attendance.worker_id == w.id, Attendance.fecha == fecha)).scalars().first()
        if a is None:
            a = Attendance(worker_id=w.id, fecha=fecha, estado=estado)
            db().add(a)
        a.estado = estado
        a.observacion = ((observaciones or {}).get(str(wid)) or "").strip()[:250]
        nueva = ((lineas or {}).get(str(wid)) or "").strip()[:20]
        a.linea = "" if nueva == (w.linea or "") else nueva
        a.user_id = user.id
        n += 1
    audit(user, "ASISTENCIA_REGISTRADA", "Attendance", fecha.isoformat(), {"registros": n})
    return n


def day(fecha):
    return {a.worker_id: a for a in db().execute(select(Attendance).where(Attendance.fecha == fecha)).scalars()}


def summary(desde=None, hasta=None, linea="", area="Producción", areas=False):
    """areas: conjunto de áreas (None = todas); si se omite, se usa «area»."""
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=29)
    if areas is False:
        areas = {area}
    rows = [a for a in db().execute(select(Attendance).where(Attendance.fecha >= desde, Attendance.fecha <= hasta)).scalars()
            if areas is None or (a.worker.area or "Producción") in areas]
    por = defaultdict(Counter)
    for a in rows:
        if linea and a.worker.linea != linea:
            continue
        por[a.worker][a.estado] += 1
    total = Counter(a.estado for a in rows if not linea or a.worker.linea == linea)
    return {"desde": desde, "hasta": hasta, "por_persona": sorted(por.items(), key=lambda x: x[0].nombre), "total": total,
            "estados": states()}


def positions(user):
    """V18: puestos para la lista del colaborador: los perfiles de las áreas del usuario (o los configurados en
    «puestos_por_area»), más «Otro» que se escribe. V24: si el área tiene puestos en «alta_personal_por_area», solo
    esos (p. ej. Logística: auxiliar de almacén o de despacho)."""
    propios = alta_config(area_of(user)).get("puestos")
    if propios:
        return propios
    from sqlalchemy import select as _sel
    from ..models import Role
    areas = visible_areas(user)
    cfg = param("puestos_por_area", {}) or {}
    out = []
    for a in sorted(areas or cfg.keys() or []):
        out += list(cfg.get(a) or [])
    roles = db().execute(_sel(Role).order_by(Role.nombre)).scalars()
    out += [r.nombre for r in roles if areas is None or r.area in areas]
    return list(dict.fromkeys(x for x in out if x))


def import_workers(user, path):
    """V18: alta de colaboradores desde Excel (Nombre, Documento, Puesto o Línea, Externo). Devuelve (nuevos, actualizados)."""
    _require(user)
    from openpyxl import load_workbook
    ws = load_workbook(path, read_only=True, data_only=True).active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        raise BusinessError("El archivo está vacío.")
    cab = [str(c or "").strip().lower() for c in filas[0]]

    def col(*nombres):
        return next((i for i, c in enumerate(cab) if c in nombres), None)
    i_nom, i_doc = col("nombre", "colaborador", "apellidos y nombres"), col("documento", "dni", "doc")
    i_pue, i_lin, i_ext = col("puesto", "cargo"), col("línea", "linea"), col("externo")
    if i_nom is None:
        raise BusinessError("Falta la columna «Nombre».")
    nuevos = act = 0
    for f in filas[1:]:
        nombre = str(f[i_nom] or "").strip().upper() if i_nom < len(f) else ""
        if not nombre:
            continue
        doc = str(f[i_doc] or "").strip() if i_doc is not None and i_doc < len(f) else ""
        if doc.endswith(".0"):
            doc = doc[:-2]
        w = None
        if doc:
            w = db().execute(select(Worker).where(Worker.documento == doc)).scalars().first()
        w = w or db().execute(select(Worker).where(Worker.nombre == nombre, Worker.area == (area_of(user) or "Producción"))).scalars().first()
        datos = {"nombre": nombre, "documento": doc,
                 "puesto": str(f[i_pue] or "").strip() if i_pue is not None and i_pue < len(f) else "",
                 "linea": str(f[i_lin] or "").strip() if i_lin is not None and i_lin < len(f) else "",
                 "externo": "1" if (i_ext is not None and i_ext < len(f) and str(f[i_ext] or "").strip().lower() in ("si", "sí", "1", "x", "true")) else ""}
        if w is None:
            nuevos += 1
        else:
            act += 1
        save_worker(user, datos, w)
    return nuevos, act
