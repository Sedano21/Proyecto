"""V25 (08-nov-2026): recomendaciones de la preprogramación de rutas.

Revisa las rutas propuestas o confirmadas del día y las OV por despachar, y recomienda (no cambia nada por sí solo):
- capacidad: rutas con baja ocupación que caben juntas en una unidad (consolidar) y rutas con sobrecarga (repartir);
- lugar de entrega: OV del mismo cliente y punto de entrega repartidas en rutas distintas o sin programar (consolidar);
- horario: citas incompatibles en la misma ruta (muy seguidas o antes de la hora de salida), citas por confirmar y
  OV sin cita que conviene coordinar (modificar la cita).
Los umbrales son parámetros configurables (estado PROPUESTO hasta que Distribución los valide)."""
from collections import defaultdict

from sqlalchemy import select

from ..db import db
from ..models import Route
from .core import param


def _min(h):
    h = (h or "").strip()[:5]
    try:
        hh, mm = h.split(":")
        return int(hh) * 60 + int(mm)
    except ValueError:
        return None


def _lugar(o):
    """Cliente + punto de entrega (lugar de entrega, o la dirección y el distrito de la OV)."""
    lugar = (o.lugar_entrega or "").strip().upper() or f"{(o.direccion or '').strip().upper()}|{(o.distrito or '').strip().upper()}"
    return (o.customer_id, lugar)


def _lugar_txt(o):
    return o.lugar_entrega or ", ".join(x for x in (o.direccion, o.distrito) if x) or "su dirección"


def _cap(r):
    return r.vehicle.capacidad_kg if r.vehicle is not None and r.vehicle.capacidad_kg else None


def recomendaciones(fecha, pendientes=None):
    from .distribution import _zone, dispatchable_orders, orders_in_active_route
    from .orders import order_weight_kg
    rutas = list(db().execute(select(Route).where(Route.fecha == fecha, Route.estado.in_(("PROPUESTA", "CONFIRMADA")))
                              .order_by(Route.id)).scalars())
    occ_min = float(param("ruta_ocupacion_minima_pct", 60) or 0)
    gap = float(param("minutos_minimos_entre_citas", 45) or 0)
    out = []

    def rec(tipo, titulo, detalle, rutas_ids=(), prioridad="MEDIA"):
        out.append({"tipo": tipo, "titulo": titulo, "detalle": detalle, "rutas": list(rutas_ids), "prioridad": prioridad})

    # 1) capacidad: sobrecarga y rutas con poca carga que caben juntas
    bajas = []
    for r in rutas:
        cap = _cap(r)
        if not cap:
            continue
        uso = 100 * (r.peso_total or 0) / cap
        if uso > 100 + 1e-9:
            rec("CAPACIDAD", f"Ruta #{r.id}: sobrecarga ({uso:.0f} % de {r.vehicle.placa})",
                f"Lleva {r.peso_total:,.0f} kg y la unidad admite {cap:,.0f} kg: pase una parada a otra ruta de "
                f"{r.zona or 'la zona'} o use una unidad mayor.", [r.id], "ALTA")
        elif uso < occ_min:
            bajas.append((r, uso))
    usadas = set()
    for i, (a, ua) in enumerate(bajas):
        if a.id in usadas:
            continue
        for b, ub in bajas[i + 1:]:
            if b.id in usadas:
                continue
            total = (a.peso_total or 0) + (b.peso_total or 0)
            mayor = a if _cap(a) >= _cap(b) else b
            misma_zona = (a.zona or "") == (b.zona or "")
            if total <= _cap(mayor) + 1e-9 and (misma_zona or param("consolidar_entre_zonas", False)):
                otra = b if mayor is a else a
                rec("CONSOLIDAR", f"Consolidar las rutas #{a.id} y #{b.id} en {mayor.vehicle.placa}",
                    f"Van con {ua:.0f} % y {ub:.0f} % de ocupación ({a.zona or '—'}). Juntas suman {total:,.0f} kg y caben en "
                    f"{mayor.vehicle.placa} ({_cap(mayor):,.0f} kg): mueva las paradas de la ruta #{otra.id} y libere "
                    f"{otra.vehicle.placa if otra.vehicle else 'esa unidad'}.", [a.id, b.id])
                usadas |= {a.id, b.id}
                break
        else:
            if a.id not in usadas:
                rec("CAPACIDAD", f"Ruta #{a.id}: baja ocupación ({ua:.0f} %)",
                    f"{a.peso_total:,.0f} kg en {a.vehicle.placa} ({_cap(a):,.0f} kg). Si hay una unidad menor disponible, "
                    f"úsela; o sume OV de {a.zona or 'la zona'} que se puedan adelantar.", [a.id], "BAJA")

    # 2) lugar de entrega: mismo cliente y punto en rutas distintas, o pendiente fuera de la ruta que ya va allí
    por_lugar = defaultdict(list)
    for r in rutas:
        for st in r.stops:
            por_lugar[_lugar(st.order)].append((r, st.order))
    for (cli, _), items in por_lugar.items():
        ids = sorted({r.id for r, _ in items})
        if len(ids) > 1:
            o = items[0][1]
            rec("CONSOLIDAR", f"{o.customer.nombre}: el mismo punto de entrega en {len(ids)} rutas",
                f"Las OV {', '.join(x.numero for _, x in items)} van a {_lugar_txt(o)} en las rutas "
                f"{', '.join('#' + str(i) for i in ids)}. Llévelas en una sola ruta si la capacidad lo permite.", ids)
    if pendientes is None:
        usados = orders_in_active_route()
        pendientes = [o for o in dispatchable_orders(fecha, require_prepared=False) if o.id not in usados]
    for o in pendientes:
        dest = por_lugar.get(_lugar(o))
        if not dest:
            continue
        r = dest[0][0]
        peso = order_weight_kg(o)[0]
        cap = _cap(r)
        cabe = cap is None or (r.peso_total or 0) + peso <= cap + 1e-9
        rec("CONSOLIDAR", f"OV {o.numero}: sumar a la ruta #{r.id}",
            f"{o.customer.nombre} ya recibe en {_lugar_txt(o)} con la ruta #{r.id}. "
            + (f"Agregue la OV ({peso:,.0f} kg): cabe en {r.vehicle.placa}." if cabe and r.vehicle else
               f"Agregue la OV ({peso:,.0f} kg)." if cabe else
               f"No cabe ({peso:,.0f} kg); evalúe una unidad mayor o coordinar otra fecha con el cliente."), [r.id])

    # 3) horario de las citas dentro de cada ruta
    for r in rutas:
        salida = _min(r.hora_salida_prog)
        citas = sorted(((m, st.order) for st in r.stops for m in [_min(st.order.hora_cita)] if m is not None),
                       key=lambda x: x[0])
        if salida is not None:
            for m, o in citas:
                if m < salida:
                    rec("CITA", f"OV {o.numero}: la cita ({o.hora_cita}) es antes de la salida ({r.hora_salida_prog})",
                        f"Adelante la salida de la ruta #{r.id} o coordine con {o.customer.nombre} un nuevo horario de cita.",
                        [r.id], "ALTA")
        for (m1, o1), (m2, o2) in zip(citas, citas[1:]):
            if gap and m2 - m1 < gap and _lugar(o1) != _lugar(o2):
                rec("CITA", f"Ruta #{r.id}: citas muy seguidas ({o1.hora_cita} y {o2.hora_cita})",
                    f"Entre {o1.customer.nombre} y {o2.customer.nombre} hay {m2 - m1} min (mínimo {gap:g}). "
                    f"Modifique una de las citas o pase la OV {o2.numero} a otra ruta de "
                    f"{_zone(o2)}.", [r.id], "ALTA")
        for st in r.stops:
            o = st.order
            if o.customer.requiere_cita and not o.cita_confirmada:
                rec("CITA", f"OV {o.numero}: confirmar la cita",
                    f"{o.customer.nombre} requiere cita y no está confirmada (ruta #{r.id}). Confírmela o reprograme.",
                    [r.id])
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    out.sort(key=lambda x: orden.get(x["prioridad"], 3))
    return out
