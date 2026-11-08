"""V25 (08-nov-2026): necesidad semanal de ingresos de la empresa frente a la meta y a la venta real.

- Administración y Finanzas registra cuánto necesita ingresar la empresa cada semana (lunes a domingo).
- La meta de la semana sale de la meta GENERAL del mes (metas comerciales) repartida por días hábiles (lunes a sábado).
- Si la necesidad difiere de la meta más que la tolerancia («ingreso_semanal_tolerancia_pct»), se exige el motivo de la
  variación; queda en el historial.
- Al cerrar la semana, si la venta no alcanzó la necesidad, se avisa a la Jefatura Comercial y a Finanzas.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import SalesOrder, SalesTarget, WeeklyRevenueNeed
from . import alerts
from .core import BusinessError, audit, has_perm, param

EXCLUIR = ("CANCELADA", "BORRADOR", "REGULARIZACION_OBSERVADA")


def lunes(d):
    return d - timedelta(days=d.weekday())


def _habiles(desde, hasta):
    n, d = 0, desde
    while d <= hasta:
        n += d.weekday() < 6
        d += timedelta(days=1)
    return n


def meta_semana(semana):
    """Meta GENERAL prorrateada por días hábiles; la semana puede cruzar dos meses."""
    total, d = 0.0, semana
    fin = semana + timedelta(days=6)
    while d <= fin:
        ini_mes = d.replace(day=1)
        fin_mes = (ini_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        m = db().execute(select(SalesTarget).where(SalesTarget.mes == f"{d:%Y-%m}", SalesTarget.alcance == "GENERAL")).scalars().first()
        tramo_fin = min(fin, fin_mes)
        if m and m.soles:
            total += m.soles * _habiles(d, tramo_fin) / max(_habiles(ini_mes, fin_mes), 1)
        d = tramo_fin + timedelta(days=1)
    return round(total, 2) if total else None


def venta(desde, hasta):
    from .orders import order_amount
    return round(sum(order_amount(o) for o in db().execute(select(SalesOrder).where(
        SalesOrder.fecha_emision >= desde, SalesOrder.fecha_emision <= hasta, SalesOrder.estado.notin_(EXCLUIR))).scalars()), 2)


def registrar(user, semana, monto, nota="", motivo=""):
    if not has_perm(user, "finanzas.necesidad_semanal"):
        raise BusinessError("La necesidad semanal la registra Administración y Finanzas.")
    if semana is None:
        raise BusinessError("Indique la semana.")
    semana = lunes(semana)
    try:
        monto = float(str(monto).replace(",", ""))
    except (TypeError, ValueError):
        raise BusinessError("Monto inválido.") from None
    if monto <= 0:
        raise BusinessError("El monto debe ser mayor que cero.")
    meta = meta_semana(semana)
    tol = float(param("ingreso_semanal_tolerancia_pct", 5) or 0)
    motivo = (motivo or "").strip()
    if meta and abs(monto - meta) / meta * 100 > tol and not motivo:
        raise BusinessError(f"Lo que necesita la empresa (S/ {monto:,.0f}) difiere de la meta de la semana (S/ {meta:,.0f}) "
                            f"en más de {tol:g} %: registre el motivo de la variación.")
    s = db()
    r = s.execute(select(WeeklyRevenueNeed).where(WeeklyRevenueNeed.semana == semana)).scalars().first()
    if r is None:
        r = WeeklyRevenueNeed(semana=semana, monto=monto, user_id=user.id, historial=[])
        s.add(r)
    hist = list(r.historial or [])
    hist.append({"monto": monto, "meta": meta, "motivo": motivo, "nota": (nota or "").strip(), "user": user.nombre,
                 "ts": datetime.now().isoformat(timespec="minutes")})
    r.monto, r.nota, r.variacion_motivo, r.historial, r.user_id = monto, (nota or "").strip(), motivo, hist, user.id
    s.flush()
    audit(user, "NECESIDAD_SEMANAL", "WeeklyRevenueNeed", r.id, hist[-1])
    return r


def semanas(hoy=None, n=6):
    """Últimas n semanas (la actual incluida): venta, meta, necesidad, diferencias y variación registrada."""
    hoy = hoy or date.today()
    out = []
    for k in range(n - 1, -1, -1):
        sem = lunes(hoy) - timedelta(weeks=k)
        fin = sem + timedelta(days=6)
        v = venta(sem, min(fin, hoy))
        meta = meta_semana(sem)
        nec = db().execute(select(WeeklyRevenueNeed).where(WeeklyRevenueNeed.semana == sem)).scalars().first()
        out.append({"semana": sem, "fin": fin, "en_curso": fin >= hoy, "venta": v, "meta": meta,
                    "necesidad": nec.monto if nec else None, "nota": nec.nota if nec else "",
                    "variacion_motivo": nec.variacion_motivo if nec else "",
                    "vs_necesidad": round(v - nec.monto, 2) if nec else None,
                    "vs_meta": round(v - meta, 2) if meta else None,
                    "avance_necesidad": round(100 * v / nec.monto, 1) if nec and nec.monto else None,
                    "historial": nec.historial if nec else []})
    return out


def revisar_semana_cerrada(hoy=None):
    """Tarea programada: la semana anterior cerrada sin alcanzar lo que necesitaba la empresa → aviso a Comercial y Finanzas."""
    hoy = hoy or date.today()
    sem = lunes(hoy) - timedelta(weeks=1)
    nec = db().execute(select(WeeklyRevenueNeed).where(WeeklyRevenueNeed.semana == sem)).scalars().first()
    if nec is None:
        return 0
    v = venta(sem, sem + timedelta(days=6))
    if v >= nec.monto:
        return 0
    alerts.emit("INGRESO_SEMANAL_VARIACION", f"Semana del {sem:%d/%m}: venta S/ {v:,.0f} de S/ {nec.monto:,.0f} que necesitaba la empresa",
                f"Faltaron S/ {nec.monto - v:,.0f} ({100 * v / nec.monto:.0f} % de lo necesario). {nec.nota}".strip(),
                "WeeklyRevenueNeed", nec.id, dedup_key=f"INGSEM:{sem.isoformat()}")
    return 1
