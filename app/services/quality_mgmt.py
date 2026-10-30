"""Gestión de Calidad (V13, 30-oct-2026): inspecciones externas e internas, visitas y fumigaciones de almacenes
externos, hallazgos con tareas a las áreas, quejas y no conformidades, formatos de verificación por puntos y el
consolidado de formatos en Excel (exportación e importación de una base anterior)."""
import io
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import ExternalVisit, Inspection, QualityRecord, Warehouse, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

# área → perfiles que reciben la tarea de levantar un hallazgo
AREAS_TAREA = {"Producción": ["JEFE_PRODUCCION", "ASIST_PRODUCCION"], "Almacén": ["COORD_ALMACEN", "COORD_ALMACEN_MP", "SUPERV_ALMACEN"],
               "Logística": ["JEFE_LOGISTICA", "COORD_LOGISTICA"], "Distribución": ["COORD_DISTRIBUCION", "ASIST_DISTRIBUCION"],
               "Calidad": ["JEFE_CALIDAD", "SUPERV_CALIDAD", "ASIST_CALIDAD"], "Comercial": ["JEFE_VENTAS", "GERENTE_COMERCIAL"],
               "Compras": ["COMPRAS"], "Finanzas": ["COORD_FINANZAS"], "Seguridad": ["SEGURIDAD"],
               "Operaciones": ["GERENCIA_OPERACIONES"]}


def _g(user):
    if not has_perm(user, "calidad.gestion"):
        raise BusinessError("Lo registra Calidad.")


def _log(obj, user, evento, **x):
    obj.historial = list(obj.historial or []) + [{"evento": evento, "user": user.nombre, "ts": now().isoformat(timespec="minutes"), **x}]


def _d(v):
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


# ------------------------------------------------------------------ hallazgos con tareas
def add_finding(user, obj, descripcion, area, plazo=None, foto=""):
    """Hallazgo de una inspección o visita: se asigna como tarea al área para su levantamiento."""
    _g(user)
    if not (descripcion or "").strip():
        raise BusinessError("Describa el hallazgo.")
    if area not in AREAS_TAREA:
        raise BusinessError("Elija el área responsable.")
    n = len(obj.hallazgos or []) + 1
    origen = f"{'Inspección' if isinstance(obj, Inspection) else 'Visita'} #{obj.id}"
    a = alerts.emit("HALLAZGO_TAREA", f"Levantar hallazgo {n} de la {origen.lower()}: {descripcion[:60]}",
                    f"{descripcion}. Área: {area}." + (f" Plazo: {_d(plazo):%d/%m/%Y}." if plazo else ""),
                    type(obj).__name__, obj.id, prioridad="ALTA", extra_roles=AREAS_TAREA[area],
                    dedup_key=f"HALLAZGO:{type(obj).__name__}:{obj.id}:{n}", creado_por=user)
    obj.hallazgos = list(obj.hallazgos or []) + [{"n": n, "descripcion": descripcion.strip(), "area": area,
                                                  "plazo": _d(plazo).isoformat() if plazo else "", "foto": foto or "",
                                                  "alert_id": a.id if a is not None else None, "estado": "ABIERTO",
                                                  "ts": now().isoformat(timespec="minutes")}]
    _log(obj, user, "HALLAZGO", n=n, area=area)
    return obj


def close_finding(user, obj, n, evidencia="", foto=""):
    if not (has_perm(user, "calidad.gestion") or has_perm(user, "alertas.gestionar")):
        raise BusinessError("Sin permiso.")
    hs = [dict(h) for h in obj.hallazgos or []]
    h = next((x for x in hs if x["n"] == int(n)), None)
    if h is None or h["estado"] == "LEVANTADO":
        raise BusinessError("Hallazgo no encontrado o ya levantado.")
    if not (evidencia or "").strip():
        raise BusinessError("Describa cómo se levantó el hallazgo.")
    h.update({"estado": "LEVANTADO", "evidencia": evidencia.strip(), "foto_cierre": foto or "", "cerrado_por": user.nombre,
              "cerrado_ts": now().isoformat(timespec="minutes")})
    obj.hallazgos = hs
    alerts.close_by_system(f"HALLAZGO:{type(obj).__name__}:{obj.id}:{h['n']}", "Hallazgo levantado")
    _log(obj, user, "HALLAZGO_LEVANTADO", n=h["n"])
    return obj


# ------------------------------------------------------------------ inspecciones
def schedule_inspection(user, datos):
    """Fase 1: programación (cliente que la solicita, empresa que la ejecuta, fecha y hora)."""
    _g(user)
    tipo = (datos.get("tipo") or "EXTERNA").upper()
    if tipo not in ("EXTERNA", "INTERNA"):
        raise BusinessError("Tipo de inspección no válido.")
    fecha = _d(datos.get("fecha"))
    if fecha is None:
        raise BusinessError("Indique la fecha de ejecución.")
    if tipo == "EXTERNA" and not ((datos.get("cliente") or "").strip() and (datos.get("empresa") or "").strip()):
        raise BusinessError("Indique el cliente que la solicitó y la empresa que la ejecuta.")
    i = Inspection(tipo=tipo, cliente=(datos.get("cliente") or "").strip(), empresa=(datos.get("empresa") or "").strip(),
                   alcance=(datos.get("alcance") or "").strip(), fecha=fecha, hora_inicio=(datos.get("hora_inicio") or "").strip()[:5],
                   user_id=user.id)
    db().add(i)
    db().flush()
    _log(i, user, "PROGRAMADA")
    if tipo == "EXTERNA":
        alerts.emit("INSPECCION", f"Inspección {i.empresa} ({i.cliente}) el {fecha:%d/%m/%Y}" + (f" a las {i.hora_inicio}" if i.hora_inicio else ""),
                    f"Alcance: {i.alcance or '-'}. Preparar las áreas.", "Inspection", i.id, dedup_key=f"INSP:{i.id}:P", creado_por=user)
    audit(user, "INSPECCION_PROGRAMADA", "Inspection", i.id, {"tipo": tipo})
    return i


def start_inspection(user, i, hora_inicio=""):
    """Fase 2: inicia el registro y el proceso."""
    _g(user)
    if i.fase != "PROGRAMADA":
        raise BusinessError("La inspección ya inició.")
    i.fase = "EN_PROCESO"
    i.hora_inicio = (hora_inicio or i.hora_inicio or f"{now():%H:%M}")[:5]
    _log(i, user, "EN_PROCESO", hora=i.hora_inicio)
    return i


def close_inspection(user, i, resultado, puntaje=None, n_hallazgos=None, fotos_resultado=None, fotos_hallazgos=None):
    """Fase 3: aprobado o desaprobado, puntaje, número de hallazgos y fotos."""
    _g(user)
    if i.fase != "EN_PROCESO":
        raise BusinessError("Primero inicie la inspección.")
    if resultado not in ("APROBADO", "DESAPROBADO"):
        raise BusinessError("Indique si fue aprobada o desaprobada.")
    try:
        i.puntaje = float(puntaje) if puntaje not in (None, "") else None
        i.n_hallazgos = int(n_hallazgos) if n_hallazgos not in (None, "") else len(i.hallazgos or [])
    except ValueError:
        raise BusinessError("Puntaje o número de hallazgos inválido.")
    i.resultado, i.fase = resultado, "CERRADA"
    i.fotos_resultado = list(i.fotos_resultado or []) + list(fotos_resultado or [])
    i.fotos_hallazgos = list(i.fotos_hallazgos or []) + list(fotos_hallazgos or [])
    _log(i, user, "CERRADA", resultado=resultado, puntaje=i.puntaje)
    if i.tipo == "EXTERNA":
        alerts.emit("INSPECCION", f"Inspección {i.empresa}: {resultado.lower()}" + (f" ({i.puntaje:g} puntos)" if i.puntaje is not None else ""),
                    f"{i.n_hallazgos or 0} hallazgo(s). Cliente: {i.cliente}.", "Inspection", i.id,
                    prioridad="ALTA" if resultado == "DESAPROBADO" else "MEDIA", dedup_key=f"INSP:{i.id}:R", creado_por=user)
    audit(user, "INSPECCION_CERRADA", "Inspection", i.id, {"resultado": resultado, "puntaje": i.puntaje})
    return i


# ------------------------------------------------------------------ visitas y fumigación de almacenes externos
def external_warehouses():
    return list(db().execute(select(Warehouse).where(Warehouse.uso == "ALTERNATIVO").order_by(Warehouse.code)).scalars())


def propose_visit(user, warehouse_code, cuando, tipo="VISITA", observacion=""):
    _g(user)
    w = db().get(Warehouse, warehouse_code)
    if w is None:
        raise BusinessError("Elija el almacén externo.")
    if tipo not in ("VISITA", "FUMIGACION"):
        raise BusinessError("Tipo no válido.")
    cuando = cuando if isinstance(cuando, datetime) else datetime.fromisoformat(str(cuando))
    v = ExternalVisit(warehouse_code=w.code, tipo=tipo, propuesta=cuando, observacion=(observacion or "").strip(), user_id=user.id)
    db().add(v)
    db().flush()
    _log(v, user, "PROPUESTA", fecha=cuando.isoformat(timespec="minutes"))
    alerts.emit("VISITA_ALMACEN_EXTERNO", f"Calidad propone {'visita' if tipo == 'VISITA' else 'fumigación'} a {w.nombre}: "
                                          f"{cuando:%d/%m/%Y %H:%M}", "Confirme o reprograme la fecha y hora.",
                "ExternalVisit", v.id, dedup_key=f"VISITA:{v.id}:{len(v.historial)}", creado_por=user)
    return v


def answer_visit(user, v, confirmar, nueva=None, motivo=""):
    """Almacén confirma la fecha propuesta o la reprograma (con motivo)."""
    if not (has_perm(user, "stock.cambiar_estado") or has_perm(user, "stock.autorizar_carga")):
        raise BusinessError("Confirma o reprograma la visita Almacén.")
    if v.estado not in ("PROPUESTA", "REPROGRAMADA"):
        raise BusinessError("La visita ya fue confirmada.")
    alerts.close_by_system(f"VISITA:{v.id}:{len(v.historial)}", "Respondida")
    if confirmar:
        v.estado = "CONFIRMADA"
        v.confirmacion = {"user": user.nombre, "ts": now().isoformat(timespec="minutes")}
        _log(v, user, "CONFIRMADA")
    else:
        if nueva is None or not (motivo or "").strip():
            raise BusinessError("Indique la nueva fecha y hora y el motivo.")
        nueva = nueva if isinstance(nueva, datetime) else datetime.fromisoformat(str(nueva))
        v.propuesta, v.estado = nueva, "REPROGRAMADA"
        _log(v, user, "REPROGRAMADA", fecha=nueva.isoformat(timespec="minutes"), motivo=motivo.strip())
        alerts.emit("VISITA_ALMACEN_EXTERNO", f"Almacén reprogramó la visita a {v.warehouse.nombre}: {nueva:%d/%m/%Y %H:%M}",
                    f"Motivo: {motivo}.", "ExternalVisit", v.id, extra_roles=["JEFE_CALIDAD", "SUPERV_CALIDAD"],
                    dedup_key=f"VISITA:{v.id}:{len(v.historial)}", creado_por=user)
    return v


def complete_visit(user, v, observacion=""):
    _g(user)
    if v.estado not in ("CONFIRMADA", "REPROGRAMADA"):
        raise BusinessError("La visita aún no está confirmada.")
    v.estado = "REALIZADA"
    v.observacion = ((v.observacion + "\n") if v.observacion else "") + (observacion or "").strip()
    _log(v, user, "REALIZADA")
    return v


# ------------------------------------------------------------------ quejas y no conformidades
def complaints_report(desde=None, hasta=None):
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=90)
    q = select(QualityRecord).where(QualityRecord.formato.in_(("QUEJA", "NC_ACCION", "NO_CONFORME")),
                                    QualityRecord.fecha >= desde, QualityRecord.fecha <= hasta).order_by(QualityRecord.fecha.desc())
    rows = list(db().execute(q).scalars())
    quejas = [r for r in rows if r.formato == "QUEJA"]
    ncs = [r for r in rows if r.formato == "NC_ACCION"]
    abiertas = [r for r in ncs if ((r.datos or {}).get("estado_accion") or "ABIERTA").upper() != "CERRADA"]
    por_cliente = defaultdict(int)
    for r in quejas:
        por_cliente[(r.datos or {}).get("cliente") or "-"] += 1
    return {"desde": desde, "hasta": hasta, "quejas": quejas, "ncs": ncs, "no_conformes": [r for r in rows if r.formato == "NO_CONFORME"],
            "abiertas": abiertas, "por_cliente": sorted(por_cliente.items(), key=lambda x: -x[1])}


# ------------------------------------------------------------------ formatos de verificación por puntos
def checklist_points(formato):
    from ..catalogs import CHECKLIST_CALIDAD
    if formato not in CHECKLIST_CALIDAD:
        raise BusinessError("Formato no válido.")
    codigo, nombre, grupos = CHECKLIST_CALIDAD[formato]
    extra = (param("checklist_calidad_puntos", {}) or {}).get(formato)
    if not grupos and extra:
        grupos = [("", list(extra))]
    return codigo, nombre, grupos


def save_points(user, formato, texto):
    """Calidad registra los puntos de un formato que aún no los tiene (uno por línea)."""
    from .core import set_param
    if not has_perm(user, "calidad.formatos_configurar"):
        raise BusinessError("Configura los formatos el Jefe de Calidad.")
    puntos = [x.strip() for x in (texto or "").splitlines() if x.strip()]
    if not puntos:
        raise BusinessError("Escriba al menos un punto de verificación.")
    cfg = dict(param("checklist_calidad_puntos", {}) or {})
    cfg[formato] = puntos
    set_param("checklist_calidad_puntos", cfg, user)
    return puntos


def register_checklist(user, formato, fecha, valores, observaciones):
    """Registro del día: C (conforme) / NC (no conforme) por punto y la observación o acción correctiva."""
    if not has_perm(user, "calidad.registrar"):
        raise BusinessError("Registra Calidad.")
    codigo, nombre, grupos = checklist_points(formato)
    puntos = [p for _, ps in grupos for p in ps]
    if not puntos:
        raise BusinessError("El formato aún no tiene puntos de verificación.")
    marcas = {}
    for i, p in enumerate(puntos):
        v = (valores.get(str(i)) or "").upper()
        if v not in ("C", "NC"):
            raise BusinessError(f"Marque C o N/C en «{p}».")
        marcas[p] = v
        if v == "NC" and not (observaciones.get(str(i)) or "").strip():
            raise BusinessError(f"«{p}» no conforme: indique la observación o acción correctiva.")
    nc = [p for p, v in marcas.items() if v == "NC"]
    r = QualityRecord(formato=formato, codigo_formato=codigo, fecha=_d(fecha) or date.today(),
                      datos={"marcas": marcas, "observaciones": {puntos[int(k)]: v.strip() for k, v in observaciones.items()
                                                                 if v and v.strip() and k.isdigit() and int(k) < len(puntos)}},
                      resultado="NO_CONFORME" if nc else "CONFORME", observaciones="; ".join(nc), user_id=user.id)
    db().add(r)
    db().flush()
    if nc:
        alerts.emit("CALIDAD_NO_CONFORME", f"{nombre}: {len(nc)} punto(s) no conforme(s)", ", ".join(nc[:8]),
                    "QualityRecord", r.id, creado_por=user)
    audit(user, "CALIDAD_REGISTRO", "QualityRecord", r.id, {"formato": formato, "nc": len(nc)})
    return r


# ------------------------------------------------------------------ consolidado de formatos en Excel
FORMATOS_MP = ("RECEPCION_MP", "RECEPCION_IMPORTADO", "MUESTREO", "FUMIGACION")


def _all_formats():
    from ..catalogs import CHECKLIST_CALIDAD
    from .quality import FORMATOS
    out = {k: (v[0], v[1], [(c, l) for c, l, _ in v[2]]) for k, v in FORMATOS.items()}
    for k, (cod, nom, _) in CHECKLIST_CALIDAD.items():
        out[k] = (cod, nom, [])
    return out


def export_consolidated(desde=None, hasta=None, formatos=None, solo_mp=False):
    """Un libro con una hoja por formato: fecha, producto, lote, resultado, observaciones y todos los campos."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=30)
    defs = _all_formats()
    sel = [f for f in (formatos or defs) if f in defs and (not solo_mp or f in FORMATOS_MP)]
    q = select(QualityRecord).where(QualityRecord.fecha >= desde, QualityRecord.fecha <= hasta, QualityRecord.formato.in_(sel))
    por = defaultdict(list)
    for r in db().execute(q.order_by(QualityRecord.fecha, QualityRecord.id)).scalars():
        por[r.formato].append(r)
    wb = Workbook()
    wb.remove(wb.active)
    resumen = wb.create_sheet("Resumen")
    resumen.append(["Consolidado de formatos de Calidad", f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y}"])
    resumen.append(["Formato", "Código", "Registros", "No conformes"])
    for f in sel:
        cod, nom, campos = defs[f]
        rs = por.get(f, [])
        resumen.append([nom, cod, len(rs), sum(1 for r in rs if r.resultado in ("NO_CONFORME", "DESAPROBADO"))])
        if not rs:
            continue
        ws = wb.create_sheet(f[:31])
        extra = sorted({k for r in rs for k in (r.datos or {}) if k not in {c for c, _ in campos}} - {"marcas", "observaciones"})
        cab = ["N.°", "Fecha", "Producto", "Lote", "Resultado", "Observaciones", "Registró"] + [l for _, l in campos] + extra
        if not campos and any((r.datos or {}).get("marcas") for r in rs):
            puntos = list(dict.fromkeys(p for r in rs for p in (r.datos or {}).get("marcas", {})))
            cab += puntos
        else:
            puntos = []
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="007A3D")
        for r in rs:
            d = r.datos or {}
            fila = [r.id, r.fecha, r.product_code or "", r.lote or "", r.resultado or "", r.observaciones or "",
                    r.user.nombre if r.user else ""] + [d.get(c, "") for c, _ in campos] + [d.get(k, "") for k in extra]
            fila += [(d.get("marcas") or {}).get(p, "") for p in puntos]
            ws.append([v if not isinstance(v, (list, dict)) else str(v) for v in fila])
        ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def import_consolidated(user, path):
    """Carga una base anterior con el mismo formato del consolidado (una hoja por formato, encabezados iguales). Las
    filas ya cargadas (mismo formato, fecha, producto, lote y N.° original) no se duplican."""
    from openpyxl import load_workbook
    if not has_perm(user, "calidad.registrar"):
        raise BusinessError("Carga la base Calidad.")
    defs = _all_formats()
    wb = load_workbook(path, data_only=True, read_only=True)
    n, omitidas, errores = 0, 0, []
    vistos = {(r.formato, (r.datos or {}).get("n_original")) for r in db().execute(select(QualityRecord)).scalars()
              if (r.datos or {}).get("n_original")}
    for ws in wb.worksheets:
        f = ws.title.strip().upper()
        if f not in defs:
            continue
        cod, nom, campos = defs[f]
        filas = list(ws.iter_rows(values_only=True))
        if not filas:
            continue
        cab = [str(c or "").strip() for c in filas[0]]
        idx = {c: i for i, c in enumerate(cab)}
        lbl_a_clave = {l: c for c, l in campos}
        for k, row in enumerate(filas[1:], start=2):
            if not any(row):
                continue
            g = lambda c: row[idx[c]] if c in idx and idx[c] < len(row) else None  # noqa: E731
            num = g("N.°")
            if num and (f, f"{num}") in vistos:
                omitidas += 1
                continue
            fecha = g("Fecha")
            try:
                fecha = fecha.date() if isinstance(fecha, datetime) else (fecha if isinstance(fecha, date) else date.fromisoformat(str(fecha)[:10]))
            except (TypeError, ValueError):
                errores.append(f"{ws.title} fila {k}: fecha inválida")
                continue
            datos = {"n_original": f"{num}" if num else "", "importado": True}
            for c in cab:
                if c in lbl_a_clave and g(c) not in (None, ""):
                    datos[lbl_a_clave[c]] = g(c) if not isinstance(g(c), (date, datetime)) else str(g(c))[:10]
            db().add(QualityRecord(formato=f, codigo_formato=cod, fecha=fecha, product_code=(str(g("Producto") or "") or None),
                                   lote=str(g("Lote") or ""), resultado=str(g("Resultado") or ""),
                                   observaciones=str(g("Observaciones") or ""), datos=datos, user_id=user.id,
                                   estado="IMPORTADO"))
            n += 1
    db().flush()
    audit(user, "CALIDAD_CONSOLIDADO_CARGADO", "QualityRecord", "", {"registros": n, "omitidas": omitidas})
    return {"cargados": n, "omitidos": omitidas, "errores": errores}
