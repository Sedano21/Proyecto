"""Evaluación de opciones para atender una OV (decisión del 14-oct y especificación maestra §6).

El sistema calcula, por línea pendiente, todas las rutas (A stock en almacén principal, B producción, C traslado desde
otro almacén, D compra, E reempaque) con cantidad que cubre, plazo, fecha estimada, si cumple la fecha comprometida y la
vida útil restante frente a lo que exige el cliente; recomienda la mejor y explica por qué. Nada se ejecuta ni se
reserva solo: la persona responsable revisa la información completa de la OV y de todas las opciones, aprueba la
pre-solicitud y registra el motivo de su elección.
"""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import OVDecision, ProductionRequest, PurchaseRequest, RepackRequest, Transfer
from .core import BusinessError, audit, param

RUTAS = {"A": "Stock en almacén principal", "B": "Producción", "C": "Traslado desde otro almacén", "D": "Compra",
         "E": "Reempaque"}
RUTA_DE_PRESOLICITUD = {"PRODUCCION": "B", "TRASLADO": "C", "COMPRA": "D", "REEMPAQUE": "E"}


def meses_restantes(fecha_venc, ref):
    if not fecha_venc:
        return None
    return round((fecha_venc - ref).days / 30.44, 1)


def _vida(lot, order):
    from .customer_conditions import min_shelf_months
    m = meses_restantes(lot.fecha_venc, order.fecha_compromiso)
    exige = min_shelf_months(order.customer, lot.product)
    return {"meses": m, "exige": exige, "cumple": None if m is None or exige is None else m >= exige,
            "vence": lot.fecha_venc}


def _plazo(clave, defecto):
    v = param(clave, defecto)
    return int(v) if v not in (None, "") else None


def evaluate(order, hoy=None):
    """Opciones por línea con faltante (o con stock aún sin reservar por estar pendiente de aprobación)."""
    from .production import material_requirements
    from .purchasing import lead_time_for
    from .stock import (free_qty, line_reserved, lot_usable, lots_of, principal_warehouses,
                        _sort_lots, alternatives_for_order)
    hoy = hoy or date.today()
    s = db()
    alts = {a["line"].id: a for a in alternatives_for_order(order)}
    out = []
    for line in order.lines:
        if not line.activa:
            continue
        necesario = max(line.cantidad - line.despachado, 0)
        pendiente = necesario - line_reserved(line)
        if pendiente <= 1e-9:
            continue
        p = line.product
        ops = []
        # A) stock libre en almacenes principales (se reserva al aprobar / al entrar a la ventana)
        principales = [w.code for w in principal_warehouses(p)]
        lotes_a = [l for l in _sort_lots(lots_of(line.product_code, principales))
                   if lot_usable(l, order.fecha_compromiso, order.customer)[0] and free_qty(l) > 1e-9]
        libre_a = sum(free_qty(l) for l in lotes_a)
        if libre_a > 0:
            ops.append({"ruta": "A", "viable": True, "cantidad": min(libre_a, pendiente), "plazo": 0, "fecha": hoy,
                        "vida": _vida(lotes_a[0], order), "detalle": ", ".join(f"{l.lote} ({free_qty(l):g})" for l in lotes_a[:4])})
        a = alts.get(line.id) or {"otros_almacenes": [], "reempaque": [], "produccion": None, "compra": None}
        # C) traslado
        pt = _plazo("tiempo_traslado_dias", 2)
        for x in a["otros_almacenes"]:
            if x["apto"] and x["libre"] > 0:
                ops.append({"ruta": "C", "viable": True, "cantidad": min(x["libre"], pendiente), "plazo": pt,
                            "fecha": hoy + timedelta(days=pt or 0), "vida": _vida(x["lot"], order),
                            "detalle": f"Lote {x['lot'].lote} en {x['lot'].warehouse_code}"})
        # E) reempaque
        pr = _plazo("tiempo_reempaque_dias", 3)
        for x in a["reempaque"]:
            if x["cantidad"] > 0:
                ops.append({"ruta": "E", "viable": True, "cantidad": min(x["cantidad"], pendiente), "plazo": pr,
                            "fecha": hoy + timedelta(days=pr or 0), "vida": None,
                            "detalle": f"{x['tipo'].replace('_', ' ').lower()} · lote {x['lot'].lote} · {x['motivo']}"})
        # B) producción
        req = a["produccion"] or material_requirements(line.product_code, pendiente)
        if req and req.get("bom_encontrada"):
            pp = _plazo("tiempo_produccion_dias", 2)
            falt = [m["componente"] for m in req["materiales"] if m["faltante"] > 1e-9]
            ops.append({"ruta": "B", "viable": not falt, "cantidad": pendiente, "plazo": pp,
                        "fecha": hoy + timedelta(days=pp or 0), "vida": None,
                        "detalle": "Materiales disponibles" if not falt else "Faltan materiales: " + ", ".join(falt[:5])})
        # D) compra
        if a["compra"] is not None or not (req and req.get("bom_encontrada")):
            lt, _modo = lead_time_for(p) if p else (None, "")
            dias = lt.dias_max if lt else None
            ops.append({"ruta": "D", "viable": dias is not None, "cantidad": pendiente, "plazo": dias,
                        "fecha": hoy + timedelta(days=dias) if dias is not None else None, "vida": None,
                        "detalle": f"Plazo {lt.categoria} {lt.dias_min}-{lt.dias_max} días" if lt else
                        "Sin plazo de compra configurado para el artículo"})
        for o in ops:
            o["nombre"] = RUTAS[o["ruta"]]
            o["cumple"] = None if o["fecha"] is None else o["fecha"] <= order.fecha_compromiso
            o["cubre_todo"] = o["cantidad"] >= pendiente - 1e-9
        rec, porque = _recomendar(ops, pendiente, order)
        out.append({"line": line, "pendiente": pendiente, "opciones": ops, "recomendada": rec, "porque": porque,
                    "presolicitudes": presolicitudes(order, line.product_code)})
    return out


def _recomendar(ops, pendiente, order):
    orden = [RUTA_DE_PRESOLICITUD.get(x) for x in (param("orden_presolicitudes", []) or [])]
    rank = {r: i for i, r in enumerate(["A"] + [r for r in orden if r])}
    viables = [o for o in ops if o["viable"] and (o["vida"] is None or o["vida"]["cumple"] is not False)]
    if not viables:
        return None, "Ninguna opción es viable con la información disponible: revisar con Comercial (renegociar fecha o despacho parcial)."
    viables.sort(key=lambda o: (o["cumple"] is not True, not o["cubre_todo"], rank.get(o["ruta"], 9), o["plazo"] or 0))
    r = viables[0]
    partes = [f"{r['nombre']}: cubre {r['cantidad']:g} de {pendiente:g}"]
    if r["fecha"] is not None:
        partes.append(f"disponible el {r['fecha']:%d/%m/%Y} ({'cumple' if r['cumple'] else 'NO cumple'} la fecha comprometida "
                      f"{order.fecha_compromiso:%d/%m/%Y})")
    if r["vida"] and r["vida"]["meses"] is not None:
        partes.append(f"vida útil restante {r['vida']['meses']} meses"
                      + (f" (el cliente exige {r['vida']['exige']})" if r["vida"]["exige"] else ""))
    if not r["cubre_todo"]:
        partes.append("no cubre todo: el saldo requiere otra opción")
    if r["cumple"] is False:
        partes.append("RIESGO: ninguna opción viable llega a tiempo")
    otras = [o for o in viables[1:] if o["ruta"] != r["ruta"]]
    if otras:
        partes.append("frente a " + "; ".join(f"{o['nombre']} ({o['plazo'] if o['plazo'] is not None else '?'} días)" for o in otras[:3]))
    return r, ". ".join(partes) + "."


def presolicitudes(order, product_code):
    """Pre-solicitudes y solicitudes abiertas de la OV para el producto, con su ruta y si esperan aprobación."""
    s = db()
    out = []
    for r in s.execute(select(ProductionRequest).where(ProductionRequest.order_id == order.id,
                                                       ProductionRequest.product_code == product_code)).scalars():
        out.append({"ruta": "B", "tipo": "PRODUCCION", "id": r.id, "cantidad": r.cantidad, "estado": r.estado,
                    "pendiente": r.estado == "BORRADOR"})
    for r in s.execute(select(RepackRequest).where(RepackRequest.order_id == order.id,
                                                   RepackRequest.producto_destino == product_code)).scalars():
        out.append({"ruta": "E", "tipo": "REEMPAQUE", "id": r.id, "cantidad": r.cantidad_destino or r.cantidad,
                    "estado": r.estado, "pendiente": r.estado == "PRE_SOLICITUD"})
    for t in s.execute(select(Transfer).where(Transfer.order_id == order.id)).scalars():
        if t.lot.product_code == product_code:
            out.append({"ruta": "C", "tipo": "TRASLADO", "id": t.id, "cantidad": t.cantidad, "estado": t.estado,
                        "pendiente": t.estado == "SOLICITADO"})
    for r in s.execute(select(PurchaseRequest).where(PurchaseRequest.order_id == order.id,
                                                     PurchaseRequest.product_code == product_code)).scalars():
        out.append({"ruta": "D", "tipo": "COMPRA", "id": r.id, "cantidad": r.cantidad, "estado": r.estado,
                    "pendiente": r.estado == "PENDIENTE_LOGISTICA"})
    return out


def decide(order, user, tipo, entidad_id, aprobar, motivo, resumen=None):
    """La persona responsable aprueba (o rechaza) la pre-solicitud tras revisar la OV y todas las opciones; el motivo de
    la elección es obligatorio y queda registrado junto con la recomendación del sistema."""
    from . import production as prod
    from . import purchasing as buy
    from . import repack
    from . import transfers as trs
    if not (motivo or "").strip() or len(motivo.strip()) < 5:
        raise BusinessError("Indique por qué elige (o rechaza) esta opción.")
    try:
        entidad_id = int(entidad_id)
    except (TypeError, ValueError):
        raise BusinessError("Pre-solicitud no válida.") from None
    s = db()
    if tipo == "TRASLADO":
        t = s.get(Transfer, int(entidad_id))
        if t is None or t.order_id != order.id:
            raise BusinessError("Traslado no encontrado para esta OV.")
        trs.authorize(t, user, aprobar, motivo)
    elif tipo == "REEMPAQUE":
        r = s.get(RepackRequest, int(entidad_id))
        if r is None or r.order_id != order.id:
            raise BusinessError("Reempaque no encontrado para esta OV.")
        repack.approve_presolicitud(r, user, aprobar, motivo)
    elif tipo == "COMPRA":
        r = s.get(PurchaseRequest, int(entidad_id))
        if r is None or r.order_id != order.id:
            raise BusinessError("Compra no encontrada para esta OV.")
        buy.approve_logistics(r, user, aprobar, motivo)
    elif tipo == "PRODUCCION":
        r = s.get(ProductionRequest, int(entidad_id))
        if r is None or r.order_id != order.id:
            raise BusinessError("Solicitud de producción no encontrada para esta OV.")
        from .core import has_perm
        if not has_perm(user, "produccion.solicitud"):
            raise BusinessError("La pre-solicitud de producción la revisa y envía Almacén.")
        if aprobar:
            prod.send_request(r, user)
        else:
            r.estado = "RECHAZADA"
            r.observacion = (r.observacion + "\n" if r.observacion else "") + f"Rechazada: {motivo}"
    else:
        raise BusinessError("Tipo de pre-solicitud no válido.")
    dec = OVDecision(order_id=order.id, tipo="ELECCION_OPCION", estado="APROBADA" if aprobar else "RECHAZADA",
                     detalle={"pre_solicitud": tipo, "id": int(entidad_id), "resumen_opciones": resumen or {}},
                     comentario=motivo.strip(), user_id=user.id)
    s.add(dec)
    audit(user, "PRESOLICITUD_" + ("APROBADA" if aprobar else "RECHAZADA"), "SalesOrder", order.numero,
          {"tipo": tipo, "id": int(entidad_id), "motivo": motivo.strip(), "recomendacion": (resumen or {}).get("recomendada")})
    return dec
