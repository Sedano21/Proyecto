"""V24 (06-nov-2026): tipo de cambio SUNAT del día.

Se actualiza solo (tarea programada diaria): lee la publicación de SUNAT («tipo_cambio_url», solo lectura; formato
«dd/mm/aaaa|compra|venta|»). Si no hay conexión, se usa el último disponible y se alerta para registrarlo a mano.
Para valorizar compras e importaciones en dólares se usa el tipo de cambio de VENTA del día (o el último anterior).
"""
from datetime import date, datetime

from sqlalchemy import select

from ..db import db
from ..models import ExchangeRate
from .core import BusinessError, audit, has_perm, param


def ultimo(fecha=None):
    q = select(ExchangeRate).order_by(ExchangeRate.fecha.desc())
    if fecha:
        q = q.where(ExchangeRate.fecha <= fecha)
    return db().execute(q).scalars().first()


def rate(fecha=None):
    r = ultimo(fecha)
    return r.venta if r else None


def guardar(fecha, compra, venta, fuente="SUNAT", user=None):
    if not compra or not venta or compra <= 0 or venta <= 0 or venta > 20:
        raise BusinessError("Tipo de cambio inválido.")
    r = db().execute(select(ExchangeRate).where(ExchangeRate.fecha == fecha)).scalars().first()
    if r is None:
        r = ExchangeRate(fecha=fecha, compra=compra, venta=venta, fuente=fuente)
        db().add(r)
    r.compra, r.venta, r.fuente = float(compra), float(venta), fuente
    db().flush()
    if user is not None:
        audit(user, "TIPO_CAMBIO_REGISTRADO", "ExchangeRate", fecha.isoformat(), {"compra": compra, "venta": venta})
    return r


def parse_sunat(texto):
    """«06/11/2026|3.751|3.758|» → (fecha, compra, venta)."""
    for linea in (texto or "").strip().splitlines():
        partes = [p.strip() for p in linea.split("|") if p.strip()]
        if len(partes) >= 3:
            try:
                return datetime.strptime(partes[0], "%d/%m/%Y").date(), float(partes[1]), float(partes[2])
            except ValueError:
                continue
    raise BusinessError("Formato de tipo de cambio SUNAT no reconocido.")


def actualizar(fetch=None, hoy=None):
    """Tarea diaria. fetch(url) -> texto (se inyecta en pruebas). Devuelve el registro o None si no se pudo."""
    from . import alerts
    hoy = hoy or date.today()
    existente = db().execute(select(ExchangeRate).where(ExchangeRate.fecha == hoy)).scalars().first()
    if existente is not None:
        return existente
    url = param("tipo_cambio_url", "") or ""
    try:
        if fetch is None:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (URL configurable, solo lectura)
                texto = resp.read().decode("latin-1")
        else:
            texto = fetch(url)
        f, compra, venta = parse_sunat(texto)
        return guardar(f, compra, venta, "SUNAT")
    except Exception as e:  # noqa: BLE001  sin conexión: se avisa para registrarlo a mano
        alerts.emit("TIPO_CAMBIO_PENDIENTE", f"Tipo de cambio SUNAT del {hoy:%d/%m/%Y} no disponible",
                    f"No se pudo leer de SUNAT ({str(e)[:120]}). Se usa el último registrado: "
                    f"{(ultimo().venta if ultimo() else 'ninguno')}. Regístrelo a mano.", "ExchangeRate", hoy.isoformat(),
                    dedup_key=f"TC:{hoy}")
        return None


def manual(user, fecha, compra, venta):
    if not has_perm(user, "tipo_cambio.registrar"):
        raise BusinessError("Registran el tipo de cambio Costos y Presupuestos o Finanzas.")
    r = guardar(fecha, compra, venta, "MANUAL", user)
    from . import alerts
    alerts.close_by_system(f"TC:{fecha}", f"Registrado a mano por {user.nombre}")
    return r
