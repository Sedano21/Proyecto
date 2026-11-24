"""V70 (24-nov-2026): recorrido punto a punto de cada vehículo en el día. Por ejemplo: planta o central → cliente X →
cliente Y → cliente Z → retorno a la central → nueva carga → cliente R… Cada ruta del vehículo es una vuelta; se
ordenan por la hora de salida programada (o la real). Muestra el estado de cada entrega y el auxiliar de despacho
que va en cada vuelta (o «sin auxiliar»)."""
from collections import defaultdict
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import Route, User

ESTADO_PARADA = {"PENDIENTE": "por salir", "EN_CAMINO": "en camino", "LLEGADA": "llegó", "ENTREGADO": "entregado",
                 "ENTREGADA": "entregado", "ENTREGA_PARCIAL": "entrega parcial", "RECHAZADO": "rechazado",
                 "NO_ENTREGADO": "no entregado", "DEVUELTO": "devuelto"}


def del_dia(fecha=None):
    fecha = fecha or date.today()
    rutas = list(db().execute(select(Route).where(Route.fecha == fecha, Route.estado != "ANULADA")).scalars())
    por = defaultdict(list)
    for r in rutas:
        if r.vehicle is not None:
            clave = (r.vehicle.placa, r.vehicle.capacidad_kg)
        else:
            clave = ((r.transportista or {}).get("placa") or f"sin unidad (ruta #{r.id})", None)
        por[clave].append(r)
    nombres = {u.id: u.nombre for u in db().execute(select(User)).scalars()}
    out = []
    for (placa, cap), rs in por.items():
        rs.sort(key=lambda r: (r.salida_ts.strftime("%H:%M") if r.salida_ts else (r.hora_salida_prog or "99:99"), r.id))
        pasos = []
        for i, r in enumerate(rs, start=1):
            auxs = list(r.auxiliares or ([r.auxiliar_id] if r.auxiliar_id else []))
            pasos.append({"tipo": "CARGA", "texto": "Central / planta: carga" + (" (nueva carga)" if i > 1 else ""),
                          "ruta": r, "vuelta": i, "estado": "hecho" if r.salida_ts else
                          ("en carga" if (r.aviso_carga or {}).get("respuesta") else "por cargar"),
                          "hora": r.salida_ts.strftime("%H:%M") if r.salida_ts else r.hora_salida_prog,
                          "auxiliares": [nombres.get(a, f"#{a}") for a in auxs]})
            for st in sorted(r.stops, key=lambda s: s.orden or 0):
                pasos.append({"tipo": "ENTREGA", "texto": st.order.customer.nombre, "ov": st.order, "stop": st, "ruta": r,
                              "vuelta": i, "estado": ESTADO_PARADA.get(st.estado, (st.estado or "").lower()),
                              "hecho": st.estado in ("ENTREGADO", "ENTREGADA", "ENTREGA_PARCIAL"),
                              "hora": (st.entrega_ts or st.llegada_ts).strftime("%H:%M") if (st.entrega_ts or st.llegada_ts) else "",
                              "kg": st.peso_kg})
            pasos.append({"tipo": "RETORNO", "texto": "Retorno a la central", "ruta": r, "vuelta": i,
                          "estado": "hecho" if r.retorno_ts else ("pendiente" if r.salida_ts else ""),
                          "hora": r.retorno_ts.strftime("%H:%M") if r.retorno_ts else ""})
        entregas = [p for p in pasos if p["tipo"] == "ENTREGA"]
        out.append({"placa": placa, "capacidad": cap, "rutas": rs, "pasos": pasos, "vueltas": len(rs),
                    "chofer": next((r.driver.nombre for r in rs if r.driver), (rs[0].transportista or {}).get("nombre", "")),
                    "entregas": len(entregas), "entregadas": sum(1 for p in entregas if p["hecho"])})
    out.sort(key=lambda v: v["placa"])
    return {"fecha": fecha, "vehiculos": out}
