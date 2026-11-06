"""V22 (06-nov-2026): Mantenimiento general de la planta (Jefe de Mantenimiento).

- Trabajos preventivos y correctivos por zona o máquina, asignados a un técnico con anticipación o el mismo día.
- Foto antes y después de cada trabajo (obligatorias para terminarlo), repuestos y costo.
- Cronograma de mantenimiento (Excel) y avisos 7, 3 y 0 días antes de un preventivo (configurable en su panel).
- Tiempos de respuesta e informe por periodo de los trabajos ejecutados.
- Bitácora de máquinas de producción: configuración, calibración y cambio de piezas; paradas por mantenimiento por línea.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import MachineLog, SanitationZone, WorkOrder, Worker, now
from . import alerts
from .core import BusinessError, audit, has_perm, param, set_param

TIPOS = {"PREVENTIVO": "Preventivo", "CORRECTIVO": "Correctivo"}
ESTADOS = {"PROGRAMADA": "Programada", "ASIGNADA": "Asignada", "EN_PROCESO": "En proceso", "TERMINADA": "Terminada",
           "CANCELADA": "Cancelada"}
TIPOS_MAQUINA = {"CONFIGURACION": "Configuración", "CALIBRACION": "Calibración", "CAMBIO_PIEZA": "Cambio de pieza",
                 "AJUSTE": "Ajuste"}


def _req(user):
    if not has_perm(user, "mantenimiento.gestionar"):
        raise BusinessError("Los trabajos de mantenimiento los programa el Jefe de Mantenimiento.")


def _fecha(v):
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise BusinessError(f"Fecha inválida: {s}")


def technicians():
    return list(db().execute(select(Worker).where(Worker.area == "Mantenimiento", Worker.activo.is_(True))
                             .order_by(Worker.nombre)).scalars())


def machines():
    from ..catalogs import PRODUCTION_LINES
    return [(c, n) for c, n, _ in PRODUCTION_LINES]


def save(user, datos, wo=None):
    _req(user)
    tipo = (datos.get("tipo") or "").upper()
    if tipo not in TIPOS:
        raise BusinessError("Indique si es preventivo o correctivo.")
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        raise BusinessError("Indique el trabajo a realizar.")
    fecha = _fecha(datos.get("fecha_programada")) or date.today()
    zone_id = int(datos["zone_id"]) if datos.get("zone_id") else None
    maquina = (datos.get("maquina") or "").strip()
    if zone_id and db().get(SanitationZone, zone_id) is None:
        raise BusinessError("Zona no válida.")
    wid = int(datos["asignado_worker_id"]) if datos.get("asignado_worker_id") else None
    nuevo = wo is None
    if nuevo:
        wo = WorkOrder(tipo=tipo, titulo=titulo, fecha_programada=fecha, user_id=user.id,
                       origen=(datos.get("origen") or "MANUAL").upper(), ticket_id=datos.get("ticket_id"))
        db().add(wo)
    wo.tipo, wo.titulo, wo.fecha_programada = tipo, titulo, fecha
    wo.descripcion = (datos.get("descripcion") or "").strip()
    wo.zone_id, wo.maquina = zone_id, maquina
    wo.con_calidad = str(datos.get("con_calidad", "")).lower() in ("1", "true", "on", "si", "sí")
    db().flush()
    if wid:
        assign(user, wo, wid)
    elif nuevo:
        wo.asignacion = "EL_DIA"
    audit(user, "OT_GUARDADA", "WorkOrder", wo.id, {"tipo": tipo, "titulo": titulo, "fecha": str(fecha)})
    return wo


def assign(user, wo, worker_id):
    _req(user)
    if wo.estado in ("TERMINADA", "CANCELADA"):
        raise BusinessError("El trabajo ya está cerrado.")
    w = db().get(Worker, int(worker_id))
    if w is None or not w.activo:
        raise BusinessError("Elija un técnico activo.")
    from .ausencias import ausencia_de, texto
    a = ausencia_de("WORKER", w.id, wo.fecha_programada)
    if a is not None:
        raise BusinessError(f"{w.nombre} no está disponible el {wo.fecha_programada:%d/%m/%Y}: {texto(a)}.")
    wo.asignado_worker_id = w.id
    wo.asignacion = "ANTICIPADA" if wo.fecha_programada > date.today() else "EL_DIA"
    if wo.estado == "PROGRAMADA":
        wo.estado = "ASIGNADA"
    if w.user_id:
        alerts.emit("TRABAJO_ASIGNADO", f"Trabajo #{wo.id} {wo.fecha_programada:%d/%m}: {wo.titulo}",
                    f"{TIPOS[wo.tipo]} · {lugar(wo)}", "WorkOrder", wo.id, extra_users=[w.user_id],
                    dedup_key=f"OT_ASIG:{wo.id}:{w.id}", creado_por=user)
    audit(user, "OT_ASIGNADA", "WorkOrder", wo.id, {"tecnico": w.nombre, "asignacion": wo.asignacion})


def lugar(wo):
    if wo.zone is not None:
        return wo.zone.nombre
    if wo.maquina:
        return dict(machines()).get(wo.maquina, wo.maquina)
    return "-"


def _ejecutor(user, wo):
    if has_perm(user, "mantenimiento.gestionar"):
        return True
    w = db().execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    return has_perm(user, "mantenimiento.ejecutar") and w is not None and wo.asignado_worker_id == w.id


def start(user, wo, fotos_antes):
    if not _ejecutor(user, wo):
        raise BusinessError("Inicia el trabajo el técnico asignado o el Jefe de Mantenimiento.")
    if wo.estado not in ("PROGRAMADA", "ASIGNADA"):
        raise BusinessError("El trabajo ya inició o está cerrado.")
    fotos_antes = [x for x in (fotos_antes or []) if x]
    if not fotos_antes:
        raise BusinessError("Suba la foto de ANTES del trabajo.")
    wo.fotos_antes = list(wo.fotos_antes or []) + fotos_antes
    wo.estado = "EN_PROCESO"
    wo.inicio_ts = now()
    audit(user, "OT_INICIO", "WorkOrder", wo.id, {"fotos": len(fotos_antes)})


def finish(user, wo, fotos_despues, observacion="", repuestos=None, costo=None):
    if not _ejecutor(user, wo):
        raise BusinessError("Termina el trabajo el técnico asignado o el Jefe de Mantenimiento.")
    if wo.estado != "EN_PROCESO":
        raise BusinessError("El trabajo no está en proceso (registre primero la foto de antes).")
    fotos_despues = [x for x in (fotos_despues or []) if x]
    if not fotos_despues:
        raise BusinessError("Suba la foto de DESPUÉS del trabajo.")
    wo.fotos_despues = list(wo.fotos_despues or []) + fotos_despues
    wo.observacion = (observacion or "").strip()
    wo.repuestos = [r for r in (repuestos or []) if (r.get("pieza") or "").strip()]
    try:
        wo.costo = float(costo) if costo not in (None, "") else None
    except ValueError:
        raise BusinessError("Costo inválido.") from None
    wo.estado = "TERMINADA"
    wo.fin_ts = now()
    if wo.ticket_id:
        from ..models import Ticket
        t = db().get(Ticket, wo.ticket_id)
        if t is not None and t.estado not in ("RESUELTO", "RECHAZADO"):
            t.estado = "RESUELTO"
            t.resuelto_ts = now()
            t.solucion = f"Trabajo #{wo.id} terminado. {wo.observacion}".strip()
            alerts.close_by_system(f"TICKET:{t.id}", "Trabajo terminado")
    for r in wo.repuestos:  # el cambio de piezas de una máquina queda en su bitácora
        if wo.maquina:
            db().add(MachineLog(maquina=wo.maquina, tipo="CAMBIO_PIEZA", pieza=r.get("pieza", "")[:120],
                                detalle=f"Trabajo #{wo.id}: {wo.titulo}", costo=_num(r.get("costo")),
                                evidencias=fotos_despues, user_id=user.id))
    alerts.close_by_system(f"OT_ASIG:{wo.id}:{wo.asignado_worker_id}", "Trabajo terminado")
    audit(user, "OT_FIN", "WorkOrder", wo.id, {"fotos": len(fotos_despues), "costo": wo.costo})


def cancel(user, wo, motivo):
    _req(user)
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo.")
    wo.estado = "CANCELADA"
    wo.observacion = (motivo or "").strip()
    audit(user, "OT_CANCELADA", "WorkOrder", wo.id, {"motivo": motivo})


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def mine(user, fecha=None):
    w = db().execute(select(Worker).where(Worker.user_id == user.id)).scalars().first()
    if w is None:
        return []
    q = select(WorkOrder).where(WorkOrder.asignado_worker_id == w.id, WorkOrder.estado.in_(("ASIGNADA", "EN_PROCESO",
                                                                                           "PROGRAMADA")))
    if fecha:
        q = q.where(WorkOrder.fecha_programada <= fecha)
    return list(db().execute(q.order_by(WorkOrder.fecha_programada)).scalars())


def board(desde=None, hasta=None, estado=None, tipo=None):
    q = select(WorkOrder).order_by(WorkOrder.fecha_programada, WorkOrder.id)
    if desde:
        q = q.where(WorkOrder.fecha_programada >= desde)
    if hasta:
        q = q.where(WorkOrder.fecha_programada <= hasta)
    if estado == "ABIERTOS":
        q = q.where(WorkOrder.estado.in_(("PROGRAMADA", "ASIGNADA", "EN_PROCESO")))
    elif estado:
        q = q.where(WorkOrder.estado == estado)
    if tipo:
        q = q.where(WorkOrder.tipo == tipo)
    return list(db().execute(q).scalars())


# ------------------------------------------------------------------ alertas configurables 7 / 3 / 0
def alert_days():
    out = []
    for x in param("mant_alerta_dias", [7, 3, 0]) or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return sorted(set(out), reverse=True)


def set_alert_days(user, texto):
    _req(user)
    try:
        dias = sorted({int(x) for x in str(texto).replace(";", ",").split(",") if x.strip() != ""}, reverse=True)
    except ValueError:
        raise BusinessError("Escriba los días separados por comas, p. ej. 7, 3, 0.") from None
    if not dias or any(d < 0 or d > 60 for d in dias):
        raise BusinessError("Use días entre 0 y 60.")
    set_param("mant_alerta_dias", dias, user)
    return dias


def check_alerts(hoy=None):
    """Tarea programada: avisos antes del inicio de los preventivos (y al técnico el día del trabajo)."""
    hoy = hoy or date.today()
    dias = alert_days()
    n = 0
    if not dias:
        return 0
    for wo in board(hoy, hoy + timedelta(days=max(dias)), "ABIERTOS", "PREVENTIVO"):
        faltan = (wo.fecha_programada - hoy).days
        if faltan in dias and faltan not in (wo.avisos or []):
            alerts.emit("MANT_PREVENTIVO_PROXIMO",
                        f"Preventivo {'HOY' if faltan == 0 else f'en {faltan} día(s)'}: {wo.titulo}",
                        f"{lugar(wo)} · {wo.fecha_programada:%d/%m/%Y}"
                        + (f" · asignado a {wo.asignado.nombre}" if wo.asignado else " · sin técnico asignado")
                        + (" · coordinar con Calidad (fumigación)" if wo.con_calidad else ""),
                        "WorkOrder", wo.id, prioridad="ALTA" if faltan == 0 else None,
                        dedup_key=f"OT_AVISO:{wo.id}:{faltan}")
            wo.avisos = list(wo.avisos or []) + [faltan]
            n += 1
    return n


# ------------------------------------------------------------------ cronograma (Excel)
def import_schedule(user, path):
    """Columnas: Fecha, Trabajo, Tipo (Preventivo/Correctivo), Zona o Máquina, Técnico (opcional), Detalle (opcional)."""
    _req(user)
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        raise BusinessError("El archivo está vacío.")
    cab = [str(c or "").strip().lower() for c in filas[0]]

    def col(*nombres):
        for n in nombres:
            for i, c in enumerate(cab):
                if c.startswith(n):
                    return i
        return None
    i_f, i_t, i_tipo = col("fecha"), col("trabajo", "tarea", "actividad"), col("tipo")
    i_z, i_tec, i_det = col("zona", "máquina", "maquina", "equipo"), col("técnico", "tecnico", "responsable"), col("detalle", "descripción", "descripcion")
    if i_f is None or i_t is None:
        raise BusinessError("El cronograma necesita las columnas «Fecha» y «Trabajo».")
    zonas = {z.nombre.upper(): z for z in db().execute(select(SanitationZone)).scalars()}
    maqs = {c.upper(): c for c, _ in machines()} | {n.upper(): c for c, n in machines()}
    tecs = {w.nombre.upper(): w for w in technicians()}
    creados, errores = 0, []
    for n, f in enumerate(filas[1:], start=2):
        if not f or all(v in (None, "") for v in f):
            continue
        try:
            datos = {"fecha_programada": _fecha(f[i_f]), "titulo": str(f[i_t] or "").strip(),
                     "tipo": ("CORRECTIVO" if i_tipo is not None and str(f[i_tipo] or "").strip().upper().startswith("C")
                              else "PREVENTIVO"), "origen": "CRONOGRAMA",
                     "descripcion": str(f[i_det] or "").strip() if i_det is not None else ""}
            lugar_txt = str(f[i_z] or "").strip().upper() if i_z is not None else ""
            if lugar_txt in zonas:
                datos["zone_id"] = zonas[lugar_txt].id
            elif lugar_txt in maqs:
                datos["maquina"] = maqs[lugar_txt]
            elif lugar_txt:
                datos["descripcion"] = (datos["descripcion"] + f" · Lugar: {lugar_txt}").strip(" ·")
            tec = str(f[i_tec] or "").strip().upper() if i_tec is not None else ""
            if tec and tec in tecs:
                datos["asignado_worker_id"] = tecs[tec].id
            save(user, datos)
            creados += 1
        except BusinessError as ex:
            errores.append(f"Fila {n}: {ex}")
    return creados, errores


# ------------------------------------------------------------------ tiempos e informe
def _h(a, b):
    return round((b - a).total_seconds() / 3600, 1) if a and b else None


def report(desde, hasta):
    """Trabajos del periodo: ejecutados, pendientes, a tiempo, duración y costo; por técnico y por zona."""
    rows = board(desde, hasta)
    hechos = [w for w in rows if w.estado == "TERMINADA"]
    a_tiempo = [w for w in hechos if w.fin_ts and w.fin_ts.date() <= w.fecha_programada]
    dur = [_h(w.inicio_ts, w.fin_ts) for w in hechos if w.inicio_ts and w.fin_ts]
    por_tec = defaultdict(lambda: {"asignados": 0, "terminados": 0, "horas": 0.0})
    por_lugar = defaultdict(lambda: {"preventivos": 0, "correctivos": 0, "costo": 0.0})
    for w in rows:
        if w.estado == "CANCELADA":
            continue
        k = w.asignado.nombre if w.asignado else "Sin asignar"
        por_tec[k]["asignados"] += 1
        if w.estado == "TERMINADA":
            por_tec[k]["terminados"] += 1
            por_tec[k]["horas"] += _h(w.inicio_ts, w.fin_ts) or 0
        pl = por_lugar[lugar(w)]
        pl["preventivos" if w.tipo == "PREVENTIVO" else "correctivos"] += 1
        pl["costo"] += w.costo or 0
    return {"desde": desde, "hasta": hasta, "filas": rows, "terminados": len(hechos),
            "pendientes": len([w for w in rows if w.estado in ("PROGRAMADA", "ASIGNADA", "EN_PROCESO")]),
            "vencidos": len([w for w in rows if w.estado in ("PROGRAMADA", "ASIGNADA", "EN_PROCESO")
                             and w.fecha_programada < date.today()]),
            "a_tiempo_pct": round(100 * len(a_tiempo) / len(hechos), 1) if hechos else None,
            "duracion_prom_h": round(sum(dur) / len(dur), 1) if dur else None,
            "costo": round(sum(w.costo or 0 for w in hechos), 2),
            "preventivos": len([w for w in rows if w.tipo == "PREVENTIVO" and w.estado != "CANCELADA"]),
            "correctivos": len([w for w in rows if w.tipo == "CORRECTIVO" and w.estado != "CANCELADA"]),
            "por_tecnico": dict(por_tec), "por_lugar": dict(por_lugar)}


def report_excel(desde, hasta):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font
    d = report(desde, hasta)
    wb = Workbook()
    ws = wb.active
    ws.title = "Trabajos"
    ws.append([f"Trabajos de mantenimiento del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["N.°", "Tipo", "Trabajo", "Zona / máquina", "Programado", "Técnico", "Estado", "Inicio", "Fin", "Horas",
               "Fotos antes", "Fotos después", "Repuestos", "Costo S/", "Observación"])
    for c in ws[2]:
        c.font = Font(bold=True)
    for w in d["filas"]:
        ws.append([w.id, TIPOS[w.tipo], w.titulo, lugar(w), w.fecha_programada, w.asignado.nombre if w.asignado else "",
                   ESTADOS.get(w.estado, w.estado), w.inicio_ts, w.fin_ts, _h(w.inicio_ts, w.fin_ts), len(w.fotos_antes or []),
                   len(w.fotos_despues or []), ", ".join(r.get("pieza", "") for r in (w.repuestos or [])), w.costo,
                   w.observacion])
    ws2 = wb.create_sheet("Resumen")
    for k, v in (("Terminados", d["terminados"]), ("Pendientes", d["pendientes"]), ("Vencidos", d["vencidos"]),
                 ("A tiempo %", d["a_tiempo_pct"]), ("Duración promedio (h)", d["duracion_prom_h"]), ("Costo S/", d["costo"])):
        ws2.append([k, v])
    ws2.append([])
    ws2.append(["Técnico", "Asignados", "Terminados", "Horas"])
    for k, v in d["por_tecnico"].items():
        ws2.append([k, v["asignados"], v["terminados"], round(v["horas"], 1)])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ------------------------------------------------------------------ máquinas de producción
def log_machine(user, maquina, tipo, detalle="", pieza="", costo=None, parametros=None, evidencias=None, proxima=None):
    if not has_perm(user, "maquinas.registrar"):
        raise BusinessError("Registra la bitácora de máquinas Mantenimiento o el Jefe de Producción.")
    if maquina not in dict(machines()):
        raise BusinessError("Máquina no válida.")
    tipo = (tipo or "").upper()
    if tipo not in TIPOS_MAQUINA:
        raise BusinessError("Tipo de registro no válido.")
    if not (detalle or "").strip() and not (pieza or "").strip():
        raise BusinessError("Describa la configuración, calibración o la pieza cambiada.")
    if tipo == "CAMBIO_PIEZA" and not (pieza or "").strip():
        raise BusinessError("Indique la pieza cambiada.")
    m = MachineLog(maquina=maquina, tipo=tipo, detalle=(detalle or "").strip(), pieza=(pieza or "").strip()[:120],
                   costo=_num(costo), parametros=parametros or {}, evidencias=[x for x in (evidencias or []) if x],
                   proxima=_fecha(proxima), user_id=user.id)
    db().add(m)
    db().flush()
    audit(user, "MAQUINA_BITACORA", "MachineLog", m.id, {"maquina": maquina, "tipo": tipo})
    return m


def machine_summary(dias=30, hoy=None):
    """Por máquina: última configuración y calibración, piezas cambiadas, próxima calibración y minutos de parada por
    mantenimiento o avería según los partes de producción (para el análisis de eficiencia)."""
    from ..models import ProductionReport
    hoy = hoy or date.today()
    desde = hoy - timedelta(days=dias)
    paradas = defaultdict(lambda: defaultdict(float))
    for r in db().execute(select(ProductionReport).where(ProductionReport.fecha >= desde)).scalars():
        for p in r.pausas or []:
            if not p.get("inicio") or not p.get("fin"):
                continue
            try:
                mins = (datetime.fromisoformat(p["fin"]) - datetime.fromisoformat(p["inicio"])).total_seconds() / 60
            except ValueError:
                continue
            paradas[r.linea][(p.get("causa") or "-").upper()] += mins
    out = []
    for code, nombre in machines():
        logs = list(db().execute(select(MachineLog).where(MachineLog.maquina == code).order_by(MachineLog.ts.desc())).scalars())
        ult = lambda t: next((l for l in logs if l.tipo == t), None)  # noqa: E731
        p = paradas.get(code, {})
        mant = sum(v for k, v in p.items() if "MANTEN" in k or "AVER" in k or "FALLA" in k)
        out.append({"code": code, "nombre": nombre, "config": ult("CONFIGURACION"), "calibracion": ult("CALIBRACION"),
                    "piezas": [l for l in logs if l.tipo == "CAMBIO_PIEZA"][:5], "logs": logs[:10],
                    "proxima": min([l.proxima for l in logs if l.proxima and l.proxima >= hoy] or [None], key=lambda x: x or date.max),
                    "paradas_min": round(sum(p.values())), "paradas_mant_min": round(mant),
                    "causas": sorted(((k, round(v)) for k, v in p.items()), key=lambda x: -x[1])[:5]})
    return out
