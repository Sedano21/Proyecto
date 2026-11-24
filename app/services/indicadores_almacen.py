"""V70 (24-nov-2026): indicadores de pedidos y operación para el Líder Operativo, el Asistente, el Supervisor y el
Coordinador de Almacén, en una sola pantalla:
- pedidos de hoy y de mañana por etapa (kg y número de OV);
- atrasados;
- picking del día y tiempo promedio de picking de los últimos 7 días (de la foto de inicio a la foto de «listo»);
- movimientos punto a punto pendientes, en curso y terminados hoy, con su tiempo promedio;
- reempaques abiertos;
- pedidos de última hora por validar;
- OTIF del mes."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import MoveRequest, PickingTask, RepackRequest, SalesOrder


def _min(a, b):
    return (b - a).total_seconds() / 60 if a and b else None


def tablero(hoy=None):
    from .estado_ov import ETAPAS, etapa, kilos
    hoy = hoy or date.today()
    manana = hoy + timedelta(days=1)
    ords = list(db().execute(select(SalesOrder).where(SalesOrder.fecha_compromiso >= hoy - timedelta(days=30),
                                                      SalesOrder.fecha_compromiso <= manana)).scalars())
    nombres = {k: n for k, n, _ in ETAPAS}
    por_dia = {hoy: defaultdict(lambda: [0, 0.0]), manana: defaultdict(lambda: [0, 0.0])}
    atrasadas = []
    for o in ords:
        e = etapa(o)
        kp, kd = kilos(o)
        if o.fecha_compromiso in por_dia and e not in ("CANCELADA", "BORRADOR"):
            por_dia[o.fecha_compromiso][e][0] += 1
            por_dia[o.fecha_compromiso][e][1] += kp
        if o.fecha_compromiso < hoy and e not in ("DESPACHADA", "ENTREGADA", "CERRADA", "CANCELADA", "BORRADOR"):
            atrasadas.append({"o": o, "etapa": nombres.get(e, e), "dias": (hoy - o.fecha_compromiso).days, "kg": kp - kd})
    atrasadas.sort(key=lambda x: -x["dias"])
    # picking
    picks_hoy = list(db().execute(select(PickingTask).where(PickingTask.fecha == hoy)).scalars())
    est_pick = Counter(t.estado for t in picks_hoy)
    semana = list(db().execute(select(PickingTask).where(PickingTask.fin_ts >= datetime.combine(hoy - timedelta(days=7),
                                                                                                 datetime.min.time()))).scalars())
    tiempos = [m for m in (_min(t.inicio_ts, t.fin_ts) for t in semana) if m is not None and m >= 0]
    # movimientos
    movs = list(db().execute(select(MoveRequest).where(MoveRequest.estado.in_(("SOLICITADA", "EN_CURSO")))).scalars())
    hechos = list(db().execute(select(MoveRequest).where(MoveRequest.fin_ts >= datetime.combine(hoy, datetime.min.time()))).scalars())
    t_mov = [m for m in (_min(x.inicio_ts, x.fin_ts) for x in hechos) if m is not None and m >= 0]
    reemp = list(db().execute(select(RepackRequest).where(RepackRequest.estado.notin_(("EJECUTADA", "DESESTIMADA",
                                                                                         "DESAPROBADA", "RECHAZADA")))).scalars())
    from . import almacen_v66 as av
    tardias = av.por_validar()
    try:
        from .seguimiento import nivel_comercial_sap
        from .comercial_v23 import fin_de_mes
        n = nivel_comercial_sap(hoy.replace(day=1), fin_de_mes(hoy.replace(day=1)), "")
    except Exception:  # noqa: BLE001 - sin historial de SAP
        n = None
    if n is None:
        from .comercial_v23 import nivel_periodo
        n = nivel_periodo(hoy.replace(day=1), None, hoy)
    return {"hoy": hoy, "manana": manana, "etapas": ETAPAS,
            "por_dia": {d: {k: (v[0], round(v[1], 1)) for k, v in x.items()} for d, x in por_dia.items()},
            "atrasadas": atrasadas, "picking": {"total": len(picks_hoy), "estados": dict(est_pick),
                                                "prom_min": round(sum(tiempos) / len(tiempos)) if tiempos else None,
                                                "n_semana": len(tiempos)},
            "movimientos": {"pendientes": sum(1 for m in movs if m.estado == "SOLICITADA"),
                            "en_curso": sum(1 for m in movs if m.estado == "EN_CURSO"), "hechos_hoy": len(hechos),
                            "prom_min": round(sum(t_mov) / len(t_mov)) if t_mov else None},
            "reempaques": len(reemp), "tardias": len(tardias), "otif": n.get("otif") if n else None,
            "otif_n": n.get("n") if n else None}
