"""Seguimiento de flota (observaciones al demo v0.6, Coordinador de Distribución).

SOAT, revisión técnica, impuesto vehicular, multas y otros documentos por vehículo con alerta de vencimiento; consumo
de combustible (rendimiento km por galón entre cargas); mantenimiento con alerta por kilometraje o fecha; y, ante una
multa o incidencia, qué conductor tenía el vehículo y qué ruta siguió ese día.
"""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Driver, FuelLog, Route, Vehicle, VehicleDocument, VehicleMaintenance
from . import alerts
from .core import BusinessError, audit, has_perm, param

TIPOS_DOC = {"SOAT": "SOAT", "REVISION_TECNICA": "Revisión técnica", "IMPUESTO_VEHICULAR": "Impuesto vehicular",
             "MULTA": "Multa / papeleta", "OTRO": "Otro"}


def _req(user):
    if not has_perm(user, "distribucion.flota"):
        raise BusinessError("La flota la mantiene Distribución.")


def _km(vehicle, km):
    if km is not None and (vehicle.km_actual is None or km > vehicle.km_actual):
        vehicle.km_actual = km


def who_had(vehicle, fecha):
    """Rutas del vehículo en la fecha: conductor y pedidos/zonas recorridas."""
    rutas = list(db().execute(select(Route).where(Route.vehicle_id == vehicle.id, Route.fecha == fecha,
                                                  Route.estado != "ANULADA")).scalars())
    return [{"route": r, "conductor": r.driver.nombre if r.driver else "-", "zona": r.zona,
             "paradas": [f"OV {st.order.numero} · {st.order.customer.nombre} · {st.order.distrito}" for st in r.stops],
             "salida": r.salida_ts, "retorno": r.retorno_ts} for r in rutas]


def add_document(user, vehicle, tipo, numero="", fecha=None, vencimiento=None, monto=None, estado="", observacion="",
                 archivo="", hora=""):
    _req(user)
    if tipo not in TIPOS_DOC:
        raise BusinessError("Tipo de documento no válido.")
    if tipo != "MULTA" and vencimiento is None:
        raise BusinessError("Indique la fecha de vencimiento.")
    if tipo == "MULTA" and fecha is None:
        raise BusinessError("Indique la fecha de la multa.")
    d = VehicleDocument(vehicle_id=vehicle.id, tipo=tipo, numero=(numero or "").strip(), fecha=fecha, hora=(hora or "").strip(),
                        vencimiento=vencimiento, monto=monto, estado=estado or ("PENDIENTE" if tipo == "MULTA" else "VIGENTE"),
                        observacion=(observacion or "").strip(), archivo=archivo or "", user_id=user.id)
    if tipo == "MULTA":  # quién tenía el vehículo y qué ruta siguió
        rutas = who_had(vehicle, fecha)
        if rutas:
            d.route_id = rutas[0]["route"].id
            d.driver_id = rutas[0]["route"].driver_id
    db().add(d)
    db().flush()
    audit(user, "FLOTA_DOCUMENTO", "Vehicle", vehicle.placa, {"tipo": tipo, "numero": d.numero, "vencimiento": str(vencimiento)})
    return d


def add_fuel(user, vehicle, fecha, km, galones, monto=None, route_id=None, driver_id=None):
    if not (has_perm(user, "distribucion.flota") or has_perm(user, "distribucion.entrega")):
        raise BusinessError("El consumo de combustible lo registra Distribución o el conductor.")
    if not km or not galones or galones <= 0:
        raise BusinessError("Indique kilometraje y galones.")
    if vehicle.km_actual and km < vehicle.km_actual - 1e-9:
        raise BusinessError(f"El kilometraje ({km:g}) es menor al último registrado ({vehicle.km_actual:g}).")
    f = FuelLog(vehicle_id=vehicle.id, fecha=fecha or date.today(), km=km, galones=galones, monto=monto,
                route_id=route_id, driver_id=driver_id, user_id=user.id)
    db().add(f)
    _km(vehicle, km)
    db().flush()
    audit(user, "FLOTA_COMBUSTIBLE", "Vehicle", vehicle.placa, {"km": km, "galones": galones, "monto": monto})
    return f


def add_maintenance(user, vehicle, fecha, tipo, km=None, descripcion="", costo=None, proximo_km=None, proxima_fecha=None):
    _req(user)
    if tipo not in ("PREVENTIVO", "CORRECTIVO"):
        raise BusinessError("Tipo de mantenimiento no válido.")
    m = VehicleMaintenance(vehicle_id=vehicle.id, fecha=fecha or date.today(), tipo=tipo, km=km, descripcion=descripcion,
                           costo=costo, proximo_km=proximo_km, proxima_fecha=proxima_fecha, user_id=user.id)
    db().add(m)
    _km(vehicle, km)
    db().flush()
    alerts.close_by_system(f"FLOTA_MANT:{vehicle.id}", "Mantenimiento registrado")
    audit(user, "FLOTA_MANTENIMIENTO", "Vehicle", vehicle.placa, {"tipo": tipo, "km": km, "proximo_km": proximo_km})
    return m


def fuel_efficiency(vehicle):
    """Rendimiento (km/galón) entre cargas consecutivas: galones de la carga posterior cubren los km recorridos."""
    logs = list(db().execute(select(FuelLog).where(FuelLog.vehicle_id == vehicle.id).order_by(FuelLog.km)).scalars())
    out = []
    for a, b in zip(logs, logs[1:]):
        km = b.km - a.km
        out.append({"desde": a.fecha, "hasta": b.fecha, "km": km, "galones": b.galones,
                    "km_galon": round(km / b.galones, 2) if b.galones else None,
                    "costo_km": round(b.monto / km, 3) if b.monto and km else None})
    return out


def status(vehicle, hoy=None):
    hoy = hoy or date.today()
    s = db()
    docs = list(s.execute(select(VehicleDocument).where(VehicleDocument.vehicle_id == vehicle.id)
                          .order_by(VehicleDocument.vencimiento.desc().nullslast(), VehicleDocument.id.desc())).scalars())
    ult = {}
    for d in docs:
        if d.tipo != "MULTA" and d.tipo not in ult:
            ult[d.tipo] = d
    mant = s.execute(select(VehicleMaintenance).where(VehicleMaintenance.vehicle_id == vehicle.id)
                     .order_by(VehicleMaintenance.fecha.desc(), VehicleMaintenance.id.desc())).scalars().first()
    ef = fuel_efficiency(vehicle)
    return {"documentos": ult, "multas": [d for d in docs if d.tipo == "MULTA"], "mantenimiento": mant,
            "km_restantes": (mant.proximo_km - vehicle.km_actual) if mant and mant.proximo_km and vehicle.km_actual else None,
            "rendimiento": ef[-1]["km_galon"] if ef else None, "consumos": ef[-10:],
            "vencidos": [d for d in ult.values() if d.vencimiento and d.vencimiento < hoy]}


def check_alerts(hoy=None):
    """Tarea programada: documentos por vencer y mantenimiento por kilometraje o fecha."""
    hoy = hoy or date.today()
    dias = int(param("dias_aviso_documentos_vehiculo", 15) or 15)
    margen = float(param("margen_km_mantenimiento", 500) or 500)
    n = 0
    for v in db().execute(select(Vehicle)).scalars():
        st = status(v, hoy)
        for d in st["documentos"].values():
            if d.vencimiento and d.vencimiento <= hoy + timedelta(days=dias):
                vencido = d.vencimiento < hoy
                alerts.emit("FLOTA_DOCUMENTO", f"{TIPOS_DOC[d.tipo]} del vehículo {v.placa} {'vencido' if vencido else 'por vencer'} "
                            f"({d.vencimiento:%d/%m/%Y})", f"Documento {d.numero or '-'}.", "Vehicle", v.id,
                            prioridad="ALTA" if vencido else None, dedup_key=f"FLOTA_DOC:{d.id}:{'V' if vencido else 'P'}")
                n += 1
        m = st["mantenimiento"]
        if m and ((st["km_restantes"] is not None and st["km_restantes"] <= margen)
                  or (m.proxima_fecha and m.proxima_fecha <= hoy + timedelta(days=dias))):
            alerts.emit("FLOTA_MANTENIMIENTO", f"Mantenimiento próximo del vehículo {v.placa}",
                        f"Km actual {v.km_actual or '-'}; próximo a los {m.proximo_km or '-'} km"
                        f"{' o el ' + m.proxima_fecha.strftime('%d/%m/%Y') if m.proxima_fecha else ''}.", "Vehicle", v.id,
                        dedup_key=f"FLOTA_MANT:{v.id}")
            n += 1
    return n


def drivers():
    return list(db().execute(select(Driver).order_by(Driver.nombre)).scalars())
