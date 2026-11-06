"""V22 (06-nov-2026): sugerencias automáticas para mejorar la eficiencia.

El sistema revisa la operación de los últimos días y propone acciones. Cada sugerencia indica el área, la evidencia
(con números del propio sistema) y qué evaluar. No inventa costos: cuando falta un dato (p. ej. el costo de una unidad
propia) lo pide en el parámetro correspondiente.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (Absence, Breakdown, CleaningAssignment, Incident, ReturnReceipt, Route, ThirdPartyTransport, Ticket,
                      Vehicle, WorkOrder)
from .core import param


def _s(area, titulo, evidencia, accion, impacto="MEDIO", enlace=None):
    return {"area": area, "titulo": titulo, "evidencia": evidencia, "accion": accion, "impacto": impacto, "enlace": enlace}


def third_party(dias=90, hoy=None):
    """Transporte tercero frecuente: comparar con compra o alquiler por periodo largo."""
    hoy = hoy or date.today()
    desde = hoy - timedelta(days=dias)
    serv = [t for t in db().execute(select(ThirdPartyTransport).where(ThirdPartyTransport.ts >= desde)).scalars()
            if t.estado != "RECHAZADO"]
    rutas = list(db().execute(select(Route).where(Route.fecha >= desde, Route.requiere_externo.is_(True),
                                                  Route.estado.in_(("CONFIRMADA", "EN_RUTA", "CERRADA")))).scalars())
    out = []
    por_tipo = defaultdict(lambda: {"n": 0, "monto": 0.0, "proveedores": Counter()})
    for t in serv:
        k = (t.tipo_vehiculo or "SIN TIPO").upper()
        por_tipo[k]["n"] += 1
        por_tipo[k]["monto"] += t.monto or 0
        por_tipo[k]["proveedores"][t.proveedor] += 1
    for r in rutas:
        if r.costo_transporte and not any(t.route_id == r.id for t in serv):
            k = (r.vehicle.tipo_unidad or r.vehicle.descripcion if r.vehicle else "SIN TIPO").upper()
            por_tipo[k]["n"] += 1
            por_tipo[k]["monto"] += r.costo_transporte or 0
    ref = {str(k).upper(): v for k, v in (param("costo_mensual_unidad_ref", {}) or {}).items()}
    meses = max(dias / 30, 1)
    for tipo, d in sorted(por_tipo.items(), key=lambda x: -x[1]["monto"]):
        if d["n"] < 4:
            continue
        mensual = d["monto"] / meses
        prov, n_prov = (d["proveedores"].most_common(1)[0] if d["proveedores"] else ("-", 0))
        evid = (f"{d['n']} servicios de transporte tercero ({tipo}) en {dias} días; gasto S/ {d['monto']:,.0f} "
                f"(≈ S/ {mensual:,.0f} al mes). Proveedor más usado: {prov} ({n_prov}).")
        if tipo in ref and ref[tipo]:
            ahorro = mensual - float(ref[tipo])
            accion = (f"Una unidad propia o alquilada por periodo cuesta ≈ S/ {float(ref[tipo]):,.0f} al mes: "
                      + (f"ahorro estimado S/ {ahorro:,.0f} al mes. Evaluar la compra o un alquiler de largo plazo."
                         if ahorro > 0 else "hoy el tercero sale más barato; renegociar tarifa por volumen."))
        else:
            accion = ("Evaluar la compra de una unidad o un alquiler por periodos más largos, y negociar con el proveedor "
                      "una tarifa por volumen. Registre el costo mensual de referencia por tipo de unidad "
                      "(parámetro «costo_mensual_unidad_ref») para que el sistema calcule el ahorro.")
        out.append(_s("Distribución", f"Uso frecuente de transporte tercero ({tipo})", evid, accion,
                      "ALTO" if mensual > 3000 else "MEDIO", "dist.routes"))
    return out


def overloads(dias=60, hoy=None):
    from .rutas_manual import vehicle_load_stats
    out = []
    for x in vehicle_load_stats(dias, hoy):
        v = x["v"]
        if x["sobrecargas"] and x["rutas"]:
            out.append(_s("Distribución", f"{v.placa} sale con sobrecarga",
                          f"{x['sobrecargas']} de {x['rutas']} rutas ({x['pct_sobrecarga']} %) superaron el peso permitido de "
                          f"{x['permitido']:,.0f} kg; máximo {x['maximo']:,.0f} kg.",
                          "Repartir la carga en otra unidad o usar una unidad mayor: riesgo de multa, desgaste y accidentes.",
                          "ALTO", "v22.vehicle_loads"))
        elif x["uso_prom_pct"] is not None and x["rutas"] >= 5 and x["uso_prom_pct"] < 35:
            out.append(_s("Distribución", f"{v.placa} sale casi vacía",
                          f"Uso promedio {x['uso_prom_pct']} % de su capacidad en {x['rutas']} rutas.",
                          "Consolidar rutas o usar una unidad más pequeña para ese tipo de reparto.", "MEDIO",
                          "v22.vehicle_loads"))
    return out


def breakdowns(dias=120, hoy=None):
    hoy = hoy or date.today()
    out = []
    c = Counter(b.vehicle_id for b in db().execute(select(Breakdown).where(Breakdown.ts >= hoy - timedelta(days=dias))).scalars())
    for vid, n in c.items():
        if n >= 3:
            v = db().get(Vehicle, vid)
            out.append(_s("Mantenimiento", f"Averías repetidas en {v.placa}",
                          f"{n} averías en {dias} días.",
                          "Revisar el plan preventivo de la unidad y evaluar su reemplazo si el costo de reparación sigue subiendo.",
                          "MEDIO", "mant.home"))
    return out


def machines(dias=30, hoy=None):
    from .mant_trabajos import machine_summary
    out = []
    for m in machine_summary(dias, hoy):
        if m["paradas_mant_min"] >= 240:
            out.append(_s("Producción", f"{m['nombre']}: paradas por mantenimiento o avería",
                          f"{m['paradas_mant_min']} minutos detenida por mantenimiento o fallas en {dias} días.",
                          "Programar un preventivo, revisar la calibración y las piezas de desgaste con el Jefe de "
                          "Mantenimiento.", "ALTO", "mant2.machines"))
    return out


def tickets(dias=60, hoy=None):
    hoy = hoy or date.today()
    out = []
    rows = list(db().execute(select(Ticket).where(Ticket.ts >= hoy - timedelta(days=dias))).scalars())
    c = Counter((t.lugar.strip().upper(), t.categoria) for t in rows if t.lugar)
    for (lugar, cat), n in c.most_common(5):
        if n >= 3:
            out.append(_s("Mantenimiento", f"Averías repetidas: {cat} en {lugar.title()}",
                          f"{n} tickets en {dias} días.", "Atender la causa de fondo (no solo el síntoma).", "MEDIO",
                          "v22.tickets"))
    abiertos = [t for t in rows if t.estado in ("ABIERTO", "ASIGNADO", "EN_PROCESO") and t.urgente
                and t.ts.date() < hoy - timedelta(days=1)]
    if abiertos:
        out.append(_s("Mantenimiento", "Tickets urgentes con más de un día abiertos",
                      f"{len(abiertos)} ticket(s) urgentes sin resolver.", "Priorizar y asignar técnico.", "ALTO",
                      "v22.tickets"))
    return out


def returns(dias=60, hoy=None):
    hoy = hoy or date.today()
    out = []
    c = Counter()
    for r in db().execute(select(ReturnReceipt).where(ReturnReceipt.ts >= hoy - timedelta(days=dias))).scalars():
        c[r.order.customer.nombre] += 1
    for cli, n in c.most_common(3):
        if n >= 3:
            out.append(_s("Comercial", f"Devoluciones frecuentes de {cli}", f"{n} devoluciones en {dias} días.",
                          "Revisar con el cliente las causas (horario, calidad, pedido) y ajustar la condición de entrega.",
                          "MEDIO", "dist.incidents"))
    inc = Counter(i.tipo for i in db().execute(select(Incident).where(Incident.ts >= hoy - timedelta(days=dias))).scalars())
    for tipo, n in inc.most_common(2):
        if n >= 5:
            out.append(_s("Distribución", f"Incidencia recurrente: {tipo.replace('_', ' ').lower()}",
                          f"{n} incidencias en {dias} días.", "Analizar la causa raíz con el área responsable.", "MEDIO",
                          "dist.incidents"))
    return out


def absences(dias=60, hoy=None):
    hoy = hoy or date.today()
    out = []
    rows = list(db().execute(select(Absence).where(Absence.anulada.is_(False), Absence.tipo == "FALTA_INJUSTIFICADA",
                                                   Absence.desde >= hoy - timedelta(days=dias))).scalars())
    c = Counter(a.nombre for a in rows)
    for nombre, n in c.items():
        if n >= 3:
            out.append(_s("Gestión Humana", f"Faltas injustificadas repetidas: {nombre}", f"{n} faltas en {dias} días.",
                          "Conversar con la persona y su jefe; planificar reemplazos.", "MEDIO", "v22.absences"))
    return out


def cleaning(dias=14, hoy=None):
    from .limpieza import performance
    hoy = hoy or date.today()
    d = performance(hoy - timedelta(days=dias), hoy - timedelta(days=1))
    out = []
    for z in d["zonas"]:
        if z["programadas"] >= 5 and (z["pct"] or 0) < 80:
            out.append(_s("Mantenimiento", f"Limpieza incompleta en {z['nombre']}",
                          f"{z['hechas']} de {z['programadas']} limpiezas ({z['pct']} %) en {dias} días.",
                          "Reasignar personal o ajustar la frecuencia de la zona.", "MEDIO", "mant2.cleaning"))
    return out


def maintenance_backlog(hoy=None):
    hoy = hoy or date.today()
    venc = list(db().execute(select(WorkOrder).where(WorkOrder.estado.in_(("PROGRAMADA", "ASIGNADA", "EN_PROCESO")),
                                                     WorkOrder.fecha_programada < hoy)).scalars())
    if len(venc) >= 3:
        return [_s("Mantenimiento", "Trabajos de mantenimiento vencidos", f"{len(venc)} trabajos pasaron su fecha.",
                   "Reprogramar o asignar más personal; revisar si el cronograma es realista.", "ALTO", "mant2.works")]
    return []


GENERADORES = (third_party, overloads, breakdowns, machines, tickets, returns, absences, cleaning, maintenance_backlog)


def all_suggestions(hoy=None):
    out = []
    for fn in GENERADORES:
        try:
            out.extend(fn(hoy=hoy))
        except Exception:  # noqa: BLE001  una sugerencia que falla no impide ver las demás
            import logging
            logging.getLogger("operaciones").exception("Sugerencia %s", fn.__name__)
    orden = {"ALTO": 0, "MEDIO": 1, "BAJO": 2}
    return sorted(out, key=lambda s: (orden.get(s["impacto"], 9), s["area"]))
