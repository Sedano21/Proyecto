"""V69 (23-nov-2026): avance de la proyección de Comercial por ejecutivo. Por cada ejecutivo y producto: lo proyectado,
lo vendido (OV del mes) en kilos y %, lo despachado de lo vendido, lo pendiente por despachar y lo pendiente por
vender.

- El ejecutivo de una proyección es el que se indicó al registrarla (formulario o columna «ejecutivo» del Excel)
  o, si no se indicó, el ejecutivo responsable del cliente. Si no hay ninguno, va a «(sin ejecutivo asignado)».
- El ejecutivo de una OV es su vendedor del módulo o, si viene de SAP con otro nombre, el usuario que tiene ese
  nombre en «Vendedores de SAP por usuario».
- Cuando un ejecutivo toma la cartera de otro, se le asigna el nombre del otro en esa misma pantalla. Así ve
  como suyas las OV de esa cartera y también la proyección que registró el otro.
"""
from collections import defaultdict

from sqlalchemy import select

from ..db import db
from ..models import DemandForecast, SalesOrder, User

_NO_VENTA = ("BORRADOR", "CANCELADA")


def _duenos():
    """{nombre (usuario o vendedor de SAP): user_id del que hoy lleva esa cartera}."""
    us = list(db().execute(select(User)).scalars())
    out = {u.nombre: u.id for u in us if u.nombre}
    for u in us:  # quien tiene el nombre como vendedor de SAP es el que lleva esa cartera
        if not u.activo:
            continue
        for n in (u.vendedores_sap or []):
            n = str(n).strip()
            if n:
                out[n] = u.id
    return out


def avance(mes, ejecutivo_id=None):
    from .demanda_v23 import _rango_mes
    from .orders import kg_unidad
    ini, fin = _rango_mes(mes)
    duenos = _duenos()
    nombres = {u.id: u.nombre for u in db().execute(select(User)).scalars()}

    def dueno_de(uid):
        return duenos.get(nombres.get(uid), uid) if uid else None

    data = defaultdict(lambda: defaultdict(lambda: {"proyectado": 0.0, "vendido": 0.0, "despachado": 0.0,
                                                    "producto": None, "clientes": set(), "ovs": set()}))
    for f in db().execute(select(DemandForecast).where(DemandForecast.mes == mes)).scalars():
        e = dueno_de(f.ejecutivo_id or (f.customer.vendedor_id if f.customer is not None else None))
        x = data[e][f.product_code]
        x["proyectado"] += (f.cantidad or 0) * kg_unidad(f.product)
        x["producto"] = f.product
        if f.customer is not None:
            x["clientes"].add(f.customer.nombre)
    ords = db().execute(select(SalesOrder).where(SalesOrder.fecha_compromiso >= ini, SalesOrder.fecha_compromiso <= fin,
                                                 SalesOrder.estado.notin_(_NO_VENTA))).scalars()
    for o in ords:
        e = o.vendedor_id
        if o.vendedor_nombre and o.vendedor_nombre in duenos and (not e or nombres.get(e) != o.vendedor_nombre):
            e = duenos[o.vendedor_nombre]
        e = dueno_de(e) if e else None
        for l in o.lines:
            if not l.activa:
                continue
            k = kg_unidad(l.product)
            x = data[e][l.product_code]
            x["vendido"] += (l.cantidad or 0) * k
            x["despachado"] += min(l.despachado or 0, l.cantidad or 0) * k
            x["producto"] = x["producto"] or l.product
            x["ovs"].add(o.numero)
    ejecutivos = []
    for e, prods in data.items():
        if ejecutivo_id and e != int(ejecutivo_id):
            continue
        filas = []
        for code, x in prods.items():
            p, v, dsp = x["proyectado"], x["vendido"], x["despachado"]
            filas.append({"code": code, "descripcion": x["producto"].descripcion if x["producto"] else "",
                          "clientes": sorted(x["clientes"]), "n_ov": len(x["ovs"]),
                          "proyectado_kg": round(p, 1), "vendido_kg": round(v, 1),
                          "pct_vendido": round(100 * v / p, 1) if p else None,
                          "despachado_kg": round(dsp, 1), "pct_despachado": round(100 * dsp / v, 1) if v else None,
                          "por_despachar_kg": round(max(v - dsp, 0), 1), "por_vender_kg": round(max(p - v, 0), 1),
                          "sin_proyeccion": p <= 0})
        filas.sort(key=lambda f: (-f["proyectado_kg"], -f["vendido_kg"]))
        t = {k: round(sum(f[k] for f in filas), 1) for k in ("proyectado_kg", "vendido_kg", "despachado_kg",
                                                              "por_despachar_kg", "por_vender_kg")}
        t["pct_vendido"] = round(100 * t["vendido_kg"] / t["proyectado_kg"], 1) if t["proyectado_kg"] else None
        t["pct_despachado"] = round(100 * t["despachado_kg"] / t["vendido_kg"], 1) if t["vendido_kg"] else None
        ejecutivos.append({"id": e, "nombre": nombres.get(e) or "(sin ejecutivo asignado)", "filas": filas, "total": t})
    ejecutivos.sort(key=lambda x: (x["id"] is None, -x["total"]["proyectado_kg"]))
    return {"mes": mes, "ejecutivos": ejecutivos}
