"""V27 (11-nov-2026): solicitudes de fumigación.

1. Calidad, Producción o Almacén solicita: elige uno o varios lotes y la cantidad de cada uno (puede ser el lote
   completo o una parte) y el motivo.
2. Calidad aprueba (o rechaza): elige el lugar (los 2 contenedores o el patio, parámetro «fumigacion_lugares»), la fecha
   de inicio y la de liberación.
3. Almacén ve el checklist de lo que ingresa a fumigar y confirma lote por lote la cantidad que ingresó. Esa cantidad
   pasa a «En fumigación» (si es parte del lote, el lote se separa). Desde ahí sigue el flujo de siempre: aviso de
   liberación en la fecha indicada y liberación por Calidad.
"""
from datetime import date

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
                + f". Motivo: {motivo}. Calidad aprueba, elige el lugar y la fecha de liberación.",
                "FumigationRequest", r.id, creado_por=user, dedup_key=f"FUMI_SOL:{r.id}")
    audit(user, "FUMIGACION_SOLICITADA", "FumigationRequest", r.id, {"area": area, "lineas": out})
    return r


def aprobar(user, r, lugar, inicio, liberacion, comentario=""):
    if not has_perm(user, "fumigacion.aprobar"):
        raise BusinessError("La fumigación la aprueba Calidad.")
    if r.estado != "SOLICITADA":
        raise BusinessError("La solicitud ya fue atendida.")
    if lugar not in lugares():
        raise BusinessError("Elija dónde se fumiga: " + ", ".join(lugares()) + ".")
    inicio, liberacion = _d(inicio) or date.today(), _d(liberacion)
    if liberacion is None:
        raise BusinessError("Indique la fecha de liberación.")
    if liberacion < inicio:
        raise BusinessError("La liberación no puede ser antes del inicio.")
    r.estado, r.lugar, r.inicio, r.liberacion = "APROBADA", lugar, inicio, liberacion
    r.aprobacion = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "comentario": (comentario or "").strip()}
    alerts.close_by_system(f"FUMI_SOL:{r.id}", "Aprobada por Calidad")
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
    if r.estado != "SOLICITADA":
        raise BusinessError("La solicitud ya fue atendida.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo del rechazo.")
    r.estado = "RECHAZADA"
    r.aprobacion = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "comentario": motivo.strip(), "rechazo": True}
    alerts.close_by_system(f"FUMI_SOL:{r.id}", "Rechazada por Calidad")
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
