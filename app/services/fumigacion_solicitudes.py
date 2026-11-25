"""V27 (11-nov-2026): solicitudes de fumigación.

1. Calidad, Producción o Almacén solicita: elige uno o varios lotes y la cantidad de cada uno (puede ser el lote
   completo o una parte) y el motivo.
2. Calidad aprueba (o rechaza): elige el lugar (los 2 contenedores o el patio, parámetro «fumigacion_lugares»), la fecha
   de inicio y la de liberación.
3. Almacén ve el checklist de lo que ingresa a fumigar y confirma lote por lote la cantidad que ingresó. Esa cantidad
   pasa a «En fumigación» (si es parte del lote, el lote se separa). Desde ahí sigue el flujo de siempre: aviso de
   liberación en la fecha indicada y liberación por Calidad.

V74 (25-nov-2026, Calidad): el flujo queda en cinco pasos.
1. Almacén (o Producción, o Calidad) solicita la revisión de los lotes.
2. Calidad decide si se fumiga o no se fumiga («no» = rechazada).
3. Si se fumiga, a Almacén le llega la alerta para confirmar que hay espacio. Sin espacio, la solicitud queda
   pendiente («Sin espacio») hasta que Almacén lo confirme.
4. Con el espacio confirmado, Calidad programa: lugar, inicio y liberación. Se prefieren martes, jueves y sábado
   (parámetro «fumigacion_dias_preferidos»); otro día pide el motivo.
5. Almacén confirma con el checklist lo que ingresa a fumigar.
Estados: SOLICITADA → POR_ESPACIO (o SIN_ESPACIO) → POR_PROGRAMAR → APROBADA (programada) → EN_FUMIGACION; o RECHAZADA.
"""
from datetime import date, timedelta

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select

from ..db import db
from ..models import FumigationRequest, StockLot, now
from . import alerts
from .core import BusinessError, audit, has_perm, param


def lugares():
    return list(param("fumigacion_lugares", ["Contenedor 1", "Contenedor 2", "Patio"]) or [])


def _d(v):
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def solicitar(user, area, motivo, lineas):
    if not has_perm(user, "fumigacion.solicitar"):
        raise BusinessError("Solicitan fumigación Calidad, Producción y Almacén.")
    if area not in ("Calidad", "Producción", "Almacén"):
        raise BusinessError("Indique el área que solicita (Calidad, Producción o Almacén).")
    motivo = (motivo or "").strip()
    if not motivo:
        raise BusinessError("Indique el motivo de la fumigación.")
    out, vistos = [], set()
    for i, x in enumerate(lineas or [], 1):
        if not x.get("lot_id"):
            continue
        lot = db().get(StockLot, int(x["lot_id"]))
        if lot is None or lot.cantidad <= 0:
            raise BusinessError(f"Línea {i}: lote no encontrado o sin stock.")
        if lot.estado == "EN_FUMIGACION":
            raise BusinessError(f"Línea {i}: el lote {lot.lote} ya está en fumigación.")
        if lot.id in vistos:
            raise BusinessError(f"Línea {i}: el lote {lot.lote} está repetido.")
        try:
            q = float(str(x.get("cantidad") or lot.cantidad).replace(",", "."))
        except ValueError:
            raise BusinessError(f"Línea {i}: cantidad inválida.") from None
        if q <= 0 or q > lot.cantidad + 1e-9:
            raise BusinessError(f"Línea {i}: la cantidad debe ser mayor que cero y hasta {lot.cantidad:g} (stock del lote {lot.lote}).")
        vistos.add(lot.id)
        out.append({"lot_id": lot.id, "lote": lot.lote, "product_code": lot.product_code, "warehouse_code": lot.warehouse_code,
                    "cantidad": q, "completo": q >= lot.cantidad - 1e-9, "ingresado": None})
    if not out:
        raise BusinessError("Agregue al menos un lote a fumigar.")
    r = FumigationRequest(area=area, motivo=motivo, lineas=out, user_id=user.id, aprobacion={}, ingreso={})
    db().add(r)
    db().flush()
    alerts.emit("FUMIGACION_SOLICITADA", f"Solicitud de fumigación #{r.id} ({area})",
                f"{len(out)} lote(s): " + ", ".join(f"{x['lote']} ({x['cantidad']:g})" for x in out[:6])
                + f". Motivo: {motivo}. Calidad revisa y decide si se fumiga.",
                "FumigationRequest", r.id, creado_por=user, dedup_key=f"FUMI_SOL:{r.id}")
    audit(user, "FUMIGACION_SOLICITADA", "FumigationRequest", r.id, {"area": area, "lineas": out})
    return r


ESTADOS = {"SOLICITADA": "Por decidir (Calidad)", "POR_ESPACIO": "Se fumiga: Almacén confirma el espacio",
           "SIN_ESPACIO": "Pendiente: sin espacio", "POR_PROGRAMAR": "Espacio confirmado: Calidad programa",
           "APROBADA": "Programada: Almacén confirma el ingreso", "EN_FUMIGACION": "En fumigación",
           "RECHAZADA": "No se fumiga"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def dias_preferidos():
    """Días de la semana preferidos para fumigar (0 = lunes): martes, jueves y sábado."""
    return [int(x) for x in (param("fumigacion_dias_preferidos", [1, 3, 5]) or []) if str(x).isdigit() and int(x) < 7]


def proximo_dia_preferido(desde=None):
    d = desde or date.today()
    pref = dias_preferidos()
    if not pref:
        return d
    for i in range(8):
        x = d + timedelta(days=i)
        if x.weekday() in pref:
            return x
    return d


def decidir(user, r, fumigar, comentario=""):
    """Paso 2: Calidad revisa la solicitud y decide si se fumiga o no."""
    if not has_perm(user, "fumigacion.aprobar"):
        raise BusinessError("Decide si se fumiga Calidad.")
    if r.estado != "SOLICITADA":
        raise BusinessError("La solicitud ya fue revisada.")
    comentario = (comentario or "").strip()
    if not fumigar:
        if not comentario:
            raise BusinessError("Indique por qué no se fumiga.")
        return rechazar(user, r, comentario)
    fl = dict(r.flujo or {})
    fl["decision"] = {"fumigar": True, "user": user.nombre, "ts": now().isoformat(timespec="minutes"), "comentario": comentario}
    r.flujo = fl
    r.estado = "POR_ESPACIO"
    alerts.close_by_system(f"FUMI_SOL:{r.id}", "Calidad decidió fumigar")
    alerts.emit("FUMIGACION_ESPACIO", f"Fumigación #{r.id}: confirme si hay espacio para fumigar",
                "Calidad decidió fumigar " + ", ".join(f"{x['lote']} ({x['cantidad']:g}, {x['warehouse_code']})" for x in r.lineas[:8])
                + (f". {comentario}" if comentario else "") + ". Confirme el espacio; sin espacio, la solicitud queda pendiente.",
                "FumigationRequest", r.id, creado_por=user, dedup_key=f"FUMI_ESP:{r.id}")
    audit(user, "FUMIGACION_DECIDIDA", "FumigationRequest", r.id, {"fumigar": True, "comentario": comentario})
    return r


def confirmar_espacio(user, r, hay, lugar="", nota=""):
    """Paso 3: Almacén confirma si hay espacio. Sin espacio queda pendiente hasta que lo confirme."""
    if not has_perm(user, "fumigacion.ingreso"):
        raise BusinessError("El espacio lo confirma Almacén.")
    if r.estado not in ("POR_ESPACIO", "SIN_ESPACIO"):
        raise BusinessError("Esta solicitud no espera la confirmación del espacio.")
    lugar = (lugar or "").strip()
    if hay and lugar and lugar not in lugares():
        raise BusinessError("Elija el lugar de la lista: " + ", ".join(lugares()) + ".")
    if not hay and not (nota or "").strip():
        raise BusinessError("Indique por qué no hay espacio (queda pendiente).")
    fl = dict(r.flujo or {})
    fl["espacio"] = list(fl.get("espacio") or []) + [{"hay": bool(hay), "lugar": lugar, "user": user.nombre,
                                                       "ts": now().isoformat(timespec="minutes"), "nota": (nota or "").strip()}]
    r.flujo = fl
    if not hay:
        r.estado = "SIN_ESPACIO"
        audit(user, "FUMIGACION_SIN_ESPACIO", "FumigationRequest", r.id, {"nota": nota})
        return r  # la alerta sigue abierta hasta que Almacén confirme el espacio
    r.estado = "POR_PROGRAMAR"
    alerts.close_by_system(f"FUMI_ESP:{r.id}", "Espacio confirmado por Almacén")
    sug = proximo_dia_preferido()
    alerts.emit("FUMIGACION_PROGRAMAR", f"Fumigación #{r.id}: espacio confirmado, programe la fumigación",
                f"Almacén confirmó el espacio{(' en ' + lugar) if lugar else ''}. Próximo día preferido: {DIAS[sug.weekday()]} "
                f"{sug:%d/%m}.", "FumigationRequest", r.id, creado_por=user, dedup_key=f"FUMI_PROG:{r.id}")
    audit(user, "FUMIGACION_ESPACIO", "FumigationRequest", r.id, {"lugar": lugar, "nota": nota})
    return r


def lugar_sugerido(r):
    esp = [x for x in (r.flujo or {}).get("espacio") or [] if x.get("hay")]
    return esp[-1].get("lugar", "") if esp else ""


def aprobar(user, r, lugar, inicio, liberacion, comentario=""):
    """Paso 4 (programar): lugar, inicio y liberación. Solo después de que Almacén confirmó el espacio."""
    if not has_perm(user, "fumigacion.aprobar"):
        raise BusinessError("La fumigación la programa Calidad.")
    if r.estado in ("SOLICITADA",):
        raise BusinessError("Primero decida si se fumiga; luego Almacén confirma el espacio.")
    if r.estado in ("POR_ESPACIO", "SIN_ESPACIO"):
        raise BusinessError("Falta que Almacén confirme el espacio.")
    if r.estado != "POR_PROGRAMAR":
        raise BusinessError("La solicitud ya fue programada o atendida.")
    if lugar not in lugares():
        raise BusinessError("Elija dónde se fumiga: " + ", ".join(lugares()) + ".")
    inicio, liberacion = _d(inicio) or date.today(), _d(liberacion)
    if liberacion is None:
        raise BusinessError("Indique la fecha de liberación.")
    if liberacion < inicio:
        raise BusinessError("La liberación no puede ser antes del inicio.")
    pref = dias_preferidos()
    if pref and inicio.weekday() not in pref and not (comentario or "").strip():
        raise BusinessError(f"Se fumiga de preferencia {', '.join(DIAS[d] for d in pref)}: el {DIAS[inicio.weekday()]} "
                            "necesita el motivo en el comentario.")
    r.estado, r.lugar, r.inicio, r.liberacion = "APROBADA", lugar, inicio, liberacion
    r.aprobacion = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "comentario": (comentario or "").strip()}
    alerts.close_by_system(f"FUMI_PROG:{r.id}", "Programada por Calidad")
    alerts.emit("FUMIGACION_INGRESO", f"Fumigación #{r.id} aprobada: ingresar a {lugar} el {inicio:%d/%m}",
                "Checklist de lo que ingresa: " + ", ".join(f"{x['lote']} ({x['cantidad']:g}, {x['warehouse_code']})"
                                                           for x in r.lineas[:8])
                + f". Liberación prevista: {liberacion:%d/%m/%Y}.", "FumigationRequest", r.id, creado_por=user,
                dedup_key=f"FUMI_ING:{r.id}")
    audit(user, "FUMIGACION_APROBADA", "FumigationRequest", r.id, {"lugar": lugar, "inicio": inicio.isoformat(),
                                                                    "liberacion": liberacion.isoformat()})
    return r


def rechazar(user, r, motivo):
    if not has_perm(user, "fumigacion.aprobar"):
        raise BusinessError("La fumigación la aprueba o rechaza Calidad.")
    if r.estado not in ("SOLICITADA", "POR_ESPACIO", "SIN_ESPACIO", "POR_PROGRAMAR"):
        raise BusinessError("La solicitud ya fue atendida.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo del rechazo.")
    r.estado = "RECHAZADA"
    r.aprobacion = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "comentario": motivo.strip(), "rechazo": True}
    for k in ("FUMI_SOL", "FUMI_ESP", "FUMI_PROG"):
        alerts.close_by_system(f"{k}:{r.id}", "No se fumiga (Calidad)")
    audit(user, "FUMIGACION_RECHAZADA", "FumigationRequest", r.id, {"motivo": motivo})
    return r


def _a_fumigacion(lot, cantidad, user, motivo):
    """Pasa a «En fumigación» todo el lote o solo una parte (esa parte queda como segmento del mismo lote)."""
    from .stock import _release, change_lot_state
    from .quality_v13 import _segment
    from .core import check_warehouse_scope
    check_warehouse_scope(user, lot.warehouse_code)
    if cantidad >= lot.cantidad - 1e-9:
        change_lot_state(lot, "EN_FUMIGACION", user, motivo, _calidad=True)
        return _segment(lot, "EN_FUMIGACION")
    twin = db().execute(select(StockLot).where(StockLot.product_code == lot.product_code, StockLot.warehouse_code == lot.warehouse_code,
                                               StockLot.lote == lot.lote, StockLot.estado == "EN_FUMIGACION")).scalars().first()
    if twin is not None:
        twin.cantidad = round(twin.cantidad + cantidad, 6)
        seg = twin
    else:
        cols = {c.key: getattr(lot, c.key) for c in sa_inspect(StockLot).mapper.column_attrs if c.key != "id"}
        cols.update(cantidad=cantidad, estado="EN_FUMIGACION", estado_anterior=lot.estado, motivo_estado=motivo,
                    cantidad_verificada=None)
        seg = StockLot(**cols)
        db().add(seg)
    lot.cantidad = round(lot.cantidad - cantidad, 6)
    if lot.cantidad_verificada is not None:
        lot.cantidad_verificada = max(0.0, lot.cantidad_verificada - cantidad)
    # las reservas que ya no caben en lo que queda disponible del lote se liberan (la OV se vuelve a evaluar)
    reservado = 0.0
    for r in sorted((r for r in lot.reservations if r.estado == "ACTIVA"), key=lambda r: r.id):
        if reservado + r.cantidad > lot.cantidad + 1e-9:
            _release(r, f"Parte del lote {lot.lote} pasó a fumigación")
        else:
            reservado += r.cantidad
    db().flush()
    return seg


def confirmar_ingreso(user, r, cantidades, observacion=""):
    """Checklist de Almacén: {lot_id: cantidad que ingresó} (0 o vacío = no ingresó)."""
    if not has_perm(user, "fumigacion.ingreso"):
        raise BusinessError("El ingreso a fumigación lo confirma Almacén.")
    if r.estado != "APROBADA":
        raise BusinessError("Solo se confirma el ingreso de solicitudes aprobadas por Calidad.")
    nuevas, alguno = [], False
    for x in r.lineas:
        try:
            q = float(str(cantidades.get(str(x["lot_id"])) or 0).replace(",", "."))
        except ValueError:
            raise BusinessError(f"Cantidad inválida en el lote {x['lote']}.") from None
        y = dict(x)
        if q <= 0:
            y["ingresado"] = 0.0
            nuevas.append(y)
            continue
        lot = db().get(StockLot, x["lot_id"])
        if lot is None or q > lot.cantidad + 1e-9:
            raise BusinessError(f"Lote {x['lote']}: ingresan {q:g} pero el lote tiene {lot.cantidad if lot else 0:g}.")
        seg = _a_fumigacion(lot, q, user, f"Fumigación #{r.id} en {r.lugar} del {r.inicio:%d/%m} al {r.liberacion:%d/%m}")
        seg.fumigacion = {"inicio": r.inicio.isoformat(), "liberacion": r.liberacion.isoformat(), "zona": r.lugar,
                          "solicitud": r.id, "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
        y["ingresado"] = q
        nuevas.append(y)
        alguno = True
    if not alguno:
        raise BusinessError("Marque la cantidad que ingresó de al menos un lote.")
    r.lineas = nuevas
    r.estado = "EN_FUMIGACION"
    r.ingreso = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "observacion": (observacion or "").strip()}
    alerts.close_by_system(f"FUMI_ING:{r.id}", "Ingreso confirmado por Almacén")
    audit(user, "FUMIGACION_INGRESO", "FumigationRequest", r.id, {"lineas": nuevas})
    return r


def lotes_disponibles():
    return list(db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado != "EN_FUMIGACION")
                             .order_by(StockLot.product_code, StockLot.lote)).scalars())


def listar(estado=""):
    q = select(FumigationRequest).order_by(FumigationRequest.id.desc())
    if estado:
        q = q.where(FumigationRequest.estado == estado)
    return list(db().execute(q.limit(200)).scalars())
