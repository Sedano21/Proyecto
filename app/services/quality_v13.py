"""Calidad – indicaciones del 30-oct-2026 (V13).

Lotes:
- Observado con categoría (plaga para fumigar, piedra, vencimiento, hongueados, granos infestados): Calidad lo observa
  (también durante el proceso de producción); alerta inmediata a Almacén, Calidad y Producción y recordatorio semanal
  mientras siga en stock.
- Bloqueados (no disponibles): solo Calidad los libera. Almacén (o Producción) solicita la liberación y Calidad aprueba.
  Las reservas y los análisis solo usan lo disponible.
- Fumigación: Calidad pone el lote en fumigación con inicio y fecha prevista de liberación (y zona); al llegar la fecha
  se le recuerda liberar.
- Fechas de producción: un lote puede tener varias; se registran varias a la vez y cada una tiene su estado.
- Solicitudes de revisión a Calidad: ¿apto para proceso?, ¿va a fumigación?, liberación.

Producción ↔ Calidad:
- Observaciones de Calidad en la línea con fases (notificación → atención → fin con motivo), por uno o varios pallets.
- Validación de la merma al terminar el proceso: grano bueno y dañado, fotos; conformidad o pedido de reproceso. Si
  Producción no atiende el reproceso en «horas_reproceso» (48 h), vuelve la alerta a Calidad.
- Material que usará Producción (antes de producir): lote, producto, calidad y fecha de vencimiento.
- Saldo por proceso en cada línea.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Incident, LineObservation, MermaValidation, ProductionReport, ProductionRequest, RepackRequest,
                      ReviewRequest, StockLot, now)
from . import alerts
from .core import BusinessError, audit, has_perm, param

BLOQUEADOS = ("OBSERVADO", "PENDIENTE_REVISION", "EN_FUMIGACION", "NO_UTILIZABLE", "DANADO")


def _cal(user, txt="Lo registra Calidad."):
    if not (has_perm(user, "calidad.registrar") or has_perm(user, "calidad.liberar")):
        raise BusinessError(txt)


def _d(v):
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


# ------------------------------------------------------------------ lotes
def observe_lot(user, lot, categoria, detalle=""):
    from ..catalogs import OBS_CATEGORIAS
    from .stock import change_lot_state
    _cal(user, "Observa un lote Calidad.")
    cats = dict(OBS_CATEGORIAS)
    if categoria not in cats:
        raise BusinessError("Elija la categoría de la observación.")
    if lot.estado != "OBSERVADO":
        change_lot_state(lot, "OBSERVADO", user, f"Calidad: {cats[categoria]}. {detalle}".strip(), _calidad=True)
        lot = _segment(lot, "OBSERVADO")
    lot.observacion = {"categoria": categoria, "nombre": cats[categoria], "detalle": (detalle or "").strip(),
                       "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    alerts.emit("LOTE_OBSERVADO", f"Lote {lot.lote} observado: {cats[categoria].lower()}",
                f"{lot.product_code} {lot.product.descripcion if lot.product else ''} · {lot.cantidad:g} en {lot.warehouse_code}. "
                f"{detalle}".strip(), "StockLot", lot.id, prioridad="ALTA", dedup_key=f"LOTE_OBS:{lot.id}:0", creado_por=user)
    audit(user, "LOTE_OBSERVADO", "StockLot", lot.id, lot.observacion)
    return lot


def _segment(lot, estado):
    """Tras un cambio de estado el lote pudo fusionarse con otro segmento del mismo lote: devuelve el que quedó."""
    if lot.estado == estado and lot.cantidad > 0:
        return lot
    return db().execute(select(StockLot).where(StockLot.product_code == lot.product_code, StockLot.lote == lot.lote,
                                               StockLot.warehouse_code == lot.warehouse_code,
                                               StockLot.estado == estado)).scalars().first() or lot


def check_observed(hoy=None):
    """Recordatorio semanal de los lotes observados que siguen en stock (hasta que se usen)."""
    hoy = hoy or date.today()
    cada = int(param("dias_recordatorio_lote_observado", 7) or 7)
    n = 0
    for lot in db().execute(select(StockLot).where(StockLot.estado == "OBSERVADO", StockLot.cantidad > 0)).scalars():
        ts = (lot.observacion or {}).get("ts")
        if not ts:
            continue
        dias = (hoy - datetime.fromisoformat(ts).date()).days
        if dias >= cada:
            semana = dias // cada
            alerts.emit("LOTE_OBSERVADO", f"Recordatorio: lote {lot.lote} sigue observado ({(lot.observacion or {}).get('nombre', '')})",
                        f"{lot.product_code} · {lot.cantidad:g} en {lot.warehouse_code} · observado hace {dias} días. Defina su uso.",
                        "StockLot", lot.id, dedup_key=f"LOTE_OBS:{lot.id}:{semana}")
            n += 1
    return n


def request_review(user, lot, tipo, motivo=""):
    if not (has_perm(user, "calidad.revision_solicitar") or has_perm(user, "stock.cambiar_estado")):
        raise BusinessError("Solicitan la revisión Almacén, Producción o Logística.")
    if tipo not in ("APTO_PROCESO", "FUMIGACION", "LIBERACION"):
        raise BusinessError("Tipo de revisión no válido.")
    if tipo == "LIBERACION" and lot.estado not in BLOQUEADOS:
        raise BusinessError("El lote no está bloqueado.")
    if not (motivo or "").strip() and tipo == "LIBERACION":
        raise BusinessError("Indique por qué se pide liberar el lote.")
    r = ReviewRequest(lot_id=lot.id, tipo=tipo, motivo=(motivo or "").strip(), solicitado_por=user.id)
    db().add(r)
    db().flush()
    if tipo == "LIBERACION":
        lot.liberacion_solicitada = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "motivo": motivo.strip()}
    nombre = {"APTO_PROCESO": "¿apto para proceso?", "FUMIGACION": "¿va a fumigación?", "LIBERACION": "liberación"}[tipo]
    alerts.emit("REVISION_LOTE", f"Revisión de lote {lot.lote}: {nombre}",
                f"{lot.product_code} · {lot.cantidad:g} en {lot.warehouse_code} ({lot.estado.replace('_', ' ').lower()}). "
                f"Solicita {user.nombre}. {motivo}".strip(), "ReviewRequest", r.id, dedup_key=f"REVISION:{r.id}", creado_por=user)
    audit(user, "REVISION_SOLICITADA", "StockLot", lot.id, {"tipo": tipo, "motivo": motivo})
    return r


def resolve_review(user, r, resultado, comentario="", inicio=None, liberacion=None, zona=""):
    """Calidad resuelve: APTO (queda disponible), NO_APTO (no utilizable), A_FUMIGACION (con fechas), LIBERADO o
    RECHAZADO (liberación)."""
    from .stock import change_lot_state
    if not has_perm(user, "calidad.liberar"):
        raise BusinessError("Resuelve Calidad.")
    if r.estado != "PENDIENTE":
        raise BusinessError("La solicitud ya fue resuelta.")
    validos = {"APTO_PROCESO": ("APTO", "NO_APTO", "A_FUMIGACION"), "FUMIGACION": ("A_FUMIGACION", "APTO", "NO_APTO"),
               "LIBERACION": ("LIBERADO", "RECHAZADO", "A_FUMIGACION")}[r.tipo]
    if resultado not in validos:
        raise BusinessError("Resultado no válido para esta solicitud.")
    if resultado in ("NO_APTO", "RECHAZADO") and not (comentario or "").strip():
        raise BusinessError("Indique el motivo.")
    lot = r.lot
    if resultado in ("APTO", "LIBERADO") and lot.estado != "DISPONIBLE":
        change_lot_state(lot, "DISPONIBLE", user, f"Calidad: {comentario or resultado.lower()}", _calidad=True)
        lot.liberacion_solicitada = {}
        lot.observacion = {}
    elif resultado == "NO_APTO":
        change_lot_state(lot, "NO_UTILIZABLE", user, f"Calidad: {comentario}", _calidad=True)
    elif resultado == "A_FUMIGACION":
        set_fumigation(user, lot, inicio or date.today(), liberacion, zona)
    if resultado == "RECHAZADO":
        lot.liberacion_solicitada = {}
    r.estado, r.resultado, r.comentario, r.resuelto_por, r.resuelto_ts = "RESUELTA", resultado, (comentario or "").strip(), \
        user.id, now()
    alerts.close_by_system(f"REVISION:{r.id}", f"Resuelta: {resultado.lower()}")
    audit(user, "REVISION_RESUELTA", "StockLot", lot.id, {"tipo": r.tipo, "resultado": resultado, "comentario": comentario})
    return r


def set_fumigation(user, lot, inicio, liberacion, zona=""):
    from .stock import change_lot_state
    _cal(user, "Pone el lote en fumigación Calidad.")
    inicio, liberacion = _d(inicio) or date.today(), _d(liberacion)
    if liberacion is None:
        raise BusinessError("Indique la fecha prevista de liberación.")
    if liberacion < inicio:
        raise BusinessError("La liberación no puede ser antes del inicio de la fumigación.")
    if lot.estado != "EN_FUMIGACION":
        change_lot_state(lot, "EN_FUMIGACION", user, f"Calidad: fumigación del {inicio:%d/%m} al {liberacion:%d/%m}", _calidad=True)
        lot = _segment(lot, "EN_FUMIGACION")
    lot.fumigacion = {"inicio": inicio.isoformat(), "liberacion": liberacion.isoformat(), "zona": (zona or "").strip(),
                      "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    lot.fumigacion_programada = None
    audit(user, "LOTE_FUMIGACION", "StockLot", lot.id, lot.fumigacion)
    return lot


def check_fumigation_release(hoy=None):
    hoy = hoy or date.today()
    n = 0
    for lot in db().execute(select(StockLot).where(StockLot.estado == "EN_FUMIGACION", StockLot.cantidad > 0)).scalars():
        lib = (lot.fumigacion or {}).get("liberacion")
        if lib and date.fromisoformat(lib) <= hoy:
            alerts.emit("FUMIGACION_LIBERAR", f"Liberar lote {lot.lote}: terminó la fumigación ({date.fromisoformat(lib):%d/%m})",
                        f"{lot.product_code} · {lot.cantidad:g} en {lot.warehouse_code}. Evalúe y libere.", "StockLot", lot.id,
                        dedup_key=f"FUMI_LIB:{lot.id}:{lib}")
            n += 1
    return n


ESTADOS_FECHA = ("DISPONIBLE", "OBSERVADO", "EN_FUMIGACION", "NO_UTILIZABLE", "LIBERADO")


def add_production_dates(user, lot, filas):
    """Registra varias fechas de producción del lote a la vez: [{fecha, cantidad, estado, nota}]."""
    if not (has_perm(user, "stock.cambiar_estado") or has_perm(user, "calidad.registrar") or has_perm(user, "produccion.liquidar")):
        raise BusinessError("Registran las fechas de producción Almacén, Calidad o Producción.")
    nuevas = []
    existentes = {x["fecha"] for x in lot.fechas_produccion or []}
    for x in filas:
        f = _d(x.get("fecha"))
        if f is None:
            continue
        if f.isoformat() in existentes:
            raise BusinessError(f"La fecha {f:%d/%m/%Y} ya está registrada en el lote.")
        est = (x.get("estado") or "DISPONIBLE").upper()
        if est not in ESTADOS_FECHA:
            raise BusinessError("Estado de la fecha no válido.")
        try:
            cant = float(x["cantidad"]) if x.get("cantidad") not in (None, "") else None
        except ValueError:
            raise BusinessError("Cantidad inválida.")
        nuevas.append({"fecha": f.isoformat(), "cantidad": cant, "estado": est, "nota": (x.get("nota") or "").strip(),
                       "user": user.nombre, "ts": now().isoformat(timespec="minutes")})
        existentes.add(f.isoformat())
    if not nuevas:
        raise BusinessError("Indique al menos una fecha de producción.")
    lot.fechas_produccion = sorted(list(lot.fechas_produccion or []) + nuevas, key=lambda x: x["fecha"])
    if lot.fecha_fab is None or date.fromisoformat(nuevas[0]["fecha"]) < lot.fecha_fab:
        lot.fecha_fab = min(date.fromisoformat(x["fecha"]) for x in lot.fechas_produccion)
    audit(user, "LOTE_FECHAS_PRODUCCION", "StockLot", lot.id, {"nuevas": nuevas})
    return lot


def update_production_date(user, lot, fecha, estado, nota=""):
    if not (has_perm(user, "calidad.registrar") or has_perm(user, "stock.cambiar_estado")):
        raise BusinessError("Cambian el estado de una fecha de producción Calidad o Almacén.")
    if estado not in ESTADOS_FECHA:
        raise BusinessError("Estado no válido.")
    filas = [dict(x) for x in lot.fechas_produccion or []]
    x = next((f for f in filas if f["fecha"] == str(fecha)[:10]), None)
    if x is None:
        raise BusinessError("Fecha no registrada en el lote.")
    x.update({"estado": estado, "nota": (nota or x.get("nota") or "").strip(), "modificado_por": user.nombre,
              "modificado_ts": now().isoformat(timespec="minutes")})
    lot.fechas_produccion = filas
    audit(user, "LOTE_FECHA_ESTADO", "StockLot", lot.id, {"fecha": x["fecha"], "estado": estado})
    return lot


# ------------------------------------------------------------------ bandeja de Calidad
def inbox(hoy=None):
    """Devoluciones (las de calidad primero), reempaques por evaluar y aprobados, solicitudes de revisión y lotes
    bloqueados con su estado."""
    from .catalogs_helpers import incident_group
    from .incidents_flow import needs_part2
    dev = []
    for i in db().execute(select(Incident).order_by(Incident.id.desc()).limit(200)).scalars():
        if needs_part2(i) or incident_group(i.tipo) == "CALIDAD":
            dev.append({"i": i, "calidad": incident_group(i.tipo) == "CALIDAD"})
    dev.sort(key=lambda x: (not x["calidad"], -x["i"].id))
    reemp = list(db().execute(select(RepackRequest).where(RepackRequest.estado.in_(
        ("SOLICITADA", "APROBADA", "EN_EJECUCION"))).order_by(RepackRequest.ts.desc())).scalars())
    revisiones = list(db().execute(select(ReviewRequest).where(ReviewRequest.estado == "PENDIENTE")
                                   .order_by(ReviewRequest.ts)).scalars())
    bloqueados = list(db().execute(select(StockLot).where(StockLot.estado.in_(BLOQUEADOS), StockLot.cantidad > 0)
                                   .order_by(StockLot.estado, StockLot.product_code)).scalars())
    return {"devoluciones": dev, "reempaques": reemp, "revisiones": revisiones, "bloqueados": bloqueados}


def repack_detail(r):
    """Para la lista de reempaques: vencimiento del lote, y marca y presentación del producto destino."""
    from ..models import Product
    dest = db().get(Product, r.producto_destino) if r.producto_destino else None
    return {"fv": r.lot.fecha_venc if r.lot else None, "nueva_fv": r.nueva_fecha_venc,
            "marca": (dest.marca if dest else "") or "", "presentacion": (dest.presentacion if dest else "") or "",
            "destino": dest}


# ------------------------------------------------------------------ material para producción y saldo por línea
def materials_for_production(dias=7, hoy=None):
    """Antes de producir: material de las solicitudes validadas o programadas (lista de materiales) con los lotes
    disponibles que se usarían (FEFO): lote, producto, calidad y fecha de vencimiento."""
    from .production import active_bom, is_desmedro
    from .stock import free_qty
    hoy = hoy or date.today()
    v = active_bom()
    comp = defaultdict(list)
    if v is not None:
        from ..models import BOMLine
        for b in db().execute(select(BOMLine).where(BOMLine.version_id == v.id)).scalars():
            if not is_desmedro(b.componente, b.componente_desc):
                comp[b.padre].append((b.componente, (b.cantidad or 0) / (b.cantidad_bom or 1)))
    reqs = [r for r in db().execute(select(ProductionRequest).where(ProductionRequest.estado.in_(
        ("VALIDADA", "PROGRAMADA", "EN_PROCESO")))).scalars()
        if not r.fecha_programada or r.fecha_programada <= hoy + timedelta(days=dias)]
    filas = []
    for r in reqs:
        for code, ratio in comp.get(r.product_code, []) or [(r.product_code, 0)]:
            if not ratio:
                continue
            necesario = r.cantidad * ratio
            lotes = sorted([l for l in db().execute(select(StockLot).where(StockLot.product_code == code,
                                                                              StockLot.estado == "DISPONIBLE",
                                                                              StockLot.cantidad > 0)).scalars()],
                           key=lambda l: (l.fecha_venc or date.max))
            pend, usa = necesario, []
            for l in lotes:
                if pend <= 1e-9:
                    break
                q = min(free_qty(l), pend)
                if q > 0:
                    usa.append({"lote": l.lote, "cantidad": round(q, 2), "fv": l.fecha_venc, "almacen": l.warehouse_code,
                                "calidad": (l.product.calidad if l.product else "") or ""})
                    pend -= q
            filas.append({"req": r, "producto": code, "descripcion": lotes[0].product.descripcion if lotes and lotes[0].product else "",
                          "necesario": round(necesario, 2), "lotes": usa, "faltante": round(max(pend, 0), 2)})
    return filas


def balance_by_line(desde=None, hasta=None):
    """Saldo por proceso en cada línea: procesado − producido − merma − remanente (partes cerrados del periodo)."""
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=6)
    acc = defaultdict(lambda: {"partes": 0, "entrada": 0.0, "producido": 0.0, "merma": 0.0, "remanente": 0.0})
    for r in db().execute(select(ProductionReport).where(ProductionReport.fecha >= desde, ProductionReport.fecha <= hasta)).scalars():
        if r.estado in ("PROGRAMADO", "ANULADO", "EN PROCESO", "PAUSADO"):
            continue
        x = acc[(r.tipo, r.linea)]
        x["partes"] += 1
        x["entrada"] += r.peso_entrada_kg or 0
        prod = r.granel_kg or 0
        if r.tipo == "ENVASADO" and r.unidades and r.presentacion_kg:
            prod = r.unidades * r.presentacion_kg
        x["producido"] += prod
        x["merma"] += r.desmedro_kg or ((r.desmedro_pct or 0) * (r.peso_entrada_kg or 0) / 100)
        x["remanente"] += r.sobrante_kg or 0
    out = []
    for (tipo, linea), x in sorted(acc.items()):
        saldo = x["entrada"] - x["producido"] - x["merma"] - x["remanente"]
        out.append({"proceso": "Envasado" if tipo == "ENVASADO" else "Selección", "linea": linea,
                    **{k: round(v, 1) if isinstance(v, float) else v for k, v in x.items()}, "saldo": round(saldo, 1)})
    return {"desde": desde, "hasta": hasta, "filas": out}


# ------------------------------------------------------------------ observaciones en la línea
def observe_line(user, linea, descripcion, pallets=None, report=None, fotos=None):
    _cal(user, "Las observaciones en la línea las registra Calidad.")
    if not (descripcion or "").strip():
        raise BusinessError("Describa la observación.")
    pls = [{"pallet": str(p.get("pallet") or "").strip(), "detalle": (p.get("detalle") or "").strip()}
           for p in (pallets or []) if str(p.get("pallet") or "").strip()]
    o = LineObservation(linea=linea or (report.linea if report else ""), report_id=report.id if report else None,
                        descripcion=descripcion.strip(), pallets=pls, fotos=list(fotos or []), user_id=user.id,
                        historial=[{"fase": "NOTIFICADA", "user": user.nombre, "ts": now().isoformat(timespec="minutes")}])
    if not o.linea:
        raise BusinessError("Indique la línea.")
    db().add(o)
    db().flush()
    alerts.emit("OBS_LINEA", f"Observación de Calidad en {o.linea}" + (f" ({len(pls)} pallet(s))" if pls else ""),
                descripcion.strip() + ("" if not pls else " · Pallets: " + ", ".join(p["pallet"] for p in pls)),
                "LineObservation", o.id, prioridad="ALTA", dedup_key=f"OBS_LINEA:{o.id}", creado_por=user)
    audit(user, "OBS_LINEA", "LineObservation", o.id, {"linea": o.linea, "pallets": len(pls)})
    return o


def advance_observation(user, o, fase, motivo=""):
    if fase not in ("EN_ATENCION", "CERRADA"):
        raise BusinessError("Fase no válida.")
    if not (has_perm(user, "calidad.registrar") or has_perm(user, "produccion.liquidar")):
        raise BusinessError("Atienden la observación Producción y Calidad.")
    orden = ["NOTIFICADA", "EN_ATENCION", "CERRADA"]
    if orden.index(fase) <= orden.index(o.fase):
        raise BusinessError("La observación ya pasó esa fase.")
    if fase == "CERRADA":
        if not has_perm(user, "calidad.registrar"):
            raise BusinessError("Cierra la observación Calidad.")
        if not (motivo or "").strip():
            raise BusinessError("Indique el motivo del cierre.")
        o.motivo_cierre = motivo.strip()
        alerts.close_by_system(f"OBS_LINEA:{o.id}", f"Cerrada: {motivo}")
    o.fase = fase
    o.historial = list(o.historial or []) + [{"fase": fase, "user": user.nombre, "motivo": (motivo or "").strip(),
                                              "ts": now().isoformat(timespec="minutes")}]
    audit(user, f"OBS_LINEA_{fase}", "LineObservation", o.id, {"motivo": motivo})
    return o


# ------------------------------------------------------------------ validación de merma
def limite_merma(linea):
    cfg = param("merma_limite_gerencia_pct", {}) or {}
    v = cfg.get(linea, cfg.get("*"))
    return float(v) if v not in (None, "") else float(param("umbral_merma_pct", 5) or 5)


def open_merma_validation(report, user=None):
    """Al terminar el proceso se abre la validación de merma para Calidad (una por parte)."""
    if db().execute(select(MermaValidation).where(MermaValidation.report_id == report.id)).first():
        return None
    mv = MermaValidation(report_id=report.id, merma_pct=report.desmedro_pct, limite_pct=limite_merma(report.linea))
    db().add(mv)
    db().flush()
    fuera = mv.merma_pct is not None and mv.merma_pct > mv.limite_pct
    alerts.emit("MERMA_VALIDAR", f"Validar merma de {report.linea} (OF {report.of or '-'}): {report.desmedro_pct or 0} %"
                + (" ▲ sobre el límite" if fuera else ""),
                f"Producto {report.product_code}. Límite de Gerencia {mv.limite_pct:g} %. Registre grano bueno y dañado y dé "
                "conformidad o pida reproceso.", "MermaValidation", mv.id, prioridad="ALTA" if fuera else "MEDIA",
                dedup_key=f"MERMA_VAL:{mv.id}", creado_por=user)
    return mv


def validate_merma(user, mv, conforme, grano_bueno=None, grano_danado=None, fotos=None, observacion=""):
    _cal(user, "Valida la merma Calidad.")
    if mv.estado != "PENDIENTE":
        raise BusinessError("La merma ya fue validada.")
    try:
        gb = float(grano_bueno) if grano_bueno not in (None, "") else None
        gd = float(grano_danado) if grano_danado not in (None, "") else None
    except ValueError:
        raise BusinessError("Kilos inválidos.")
    if gb is None or gd is None:
        raise BusinessError("Registre los kg de grano bueno y de grano dañado.")
    if not conforme and not (observacion or "").strip():
        raise BusinessError("Indique qué debe reprocesarse.")
    mv.grano_bueno_kg, mv.grano_danado_kg = gb, gd
    mv.fotos = list(mv.fotos or []) + list(fotos or [])
    mv.observacion = (observacion or "").strip()
    mv.validado_por, mv.validado_ts = user.id, now()
    alerts.close_by_system(f"MERMA_VAL:{mv.id}", "Merma validada")
    r = mv.report
    if conforme:
        mv.estado = "CONFORME"
    else:
        mv.estado = "REPROCESO"
        mv.reproceso = {"solicitado_ts": now().isoformat(timespec="minutes"), "solicitado_por": user.nombre}
        alerts.emit("REPROCESO_SOLICITADO", f"Reprocesar merma de {r.linea} (OF {r.of or '-'})",
                    f"{gb:g} kg de grano bueno recuperable en la merma. {observacion}".strip(), "MermaValidation", mv.id,
                    prioridad="ALTA", dedup_key=f"REPROC:{mv.id}", creado_por=user)
    audit(user, "MERMA_VALIDADA", "MermaValidation", mv.id, {"conforme": conforme, "bueno": gb, "danado": gd})
    return mv


def attend_reprocess(user, mv, nota=""):
    if not has_perm(user, "produccion.liquidar"):
        raise BusinessError("El reproceso lo registra Producción.")
    if mv.estado != "REPROCESO":
        raise BusinessError("No hay reproceso pendiente.")
    mv.estado = "REPROCESADO"
    mv.reproceso = dict(mv.reproceso or {}, atendido_ts=now().isoformat(timespec="minutes"), atendido_por=user.nombre,
                        nota=(nota or "").strip())
    alerts.close_by_system(f"REPROC:{mv.id}", "Reproceso atendido")
    alerts.close_by_system(f"REPROC_VENC:{mv.id}", "Reproceso atendido")
    audit(user, "REPROCESO_ATENDIDO", "MermaValidation", mv.id, {"nota": nota})
    return mv


def check_reprocess(ahora=None):
    ahora = ahora or now()
    h = int(param("horas_reproceso", 48) or 48)
    n = 0
    for mv in db().execute(select(MermaValidation).where(MermaValidation.estado == "REPROCESO")).scalars():
        ts = datetime.fromisoformat((mv.reproceso or {}).get("solicitado_ts") or mv.validado_ts.isoformat())
        if ahora - ts > timedelta(hours=h):
            alerts.emit("REPROCESO_VENCIDO", f"Reproceso no atendido en {h} h: {mv.report.linea} (OF {mv.report.of or '-'})",
                        f"Calidad lo pidió el {ts:%d/%m %H:%M}.", "MermaValidation", mv.id, prioridad="ALTA",
                        dedup_key=f"REPROC_VENC:{mv.id}")
            n += 1
    return n
