"""Pre-solicitudes automáticas ante faltante (TO-BE COPROD-ONE; decisión Q15 del 12-oct-2026).

Cuando una OV queda con faltante, el sistema genera la pre-solicitud de la primera opción viable en el orden
configurado (por defecto: producir, reempaque, traslado desde almacén externo, compra). Si la opción solo cubre una
parte, el saldo pasa a la siguiente. Nada se ejecuta solo: cada pre-solicitud la aprueba la persona responsable
(Almacén envía la de producción, el Coordinador de Almacén la de reempaque (Q12), el Jefe o Coordinador de Logística
la de traslado (Q13) y el Jefe de Logística la de compra (Q14)). Lo ya solicitado para la OV se descuenta para no
duplicar al reevaluar.
"""
from sqlalchemy import select

from ..db import db
from ..models import ProductionRequest, PurchaseRequest, RepackRequest, Transfer
from . import alerts
from .core import audit, param

OPEN_PROD = ("BORRADOR", "ENVIADA", "VALIDADA", "PROGRAMADA", "EN_PROCESO")
OPEN_REPACK = ("PRE_SOLICITUD", "SOLICITADA", "APROBADA", "EN_EJECUCION")
OPEN_TRANSFER = ("SOLICITADO", "AUTORIZADO", "EN_TRANSITO")
VIABLES = ("PRODUCCION", "REEMPAQUE", "TRASLADO", "COMPRA")


def open_requested(order, product_code):
    """Cantidad ya solicitada para la OV y el producto por cualquier vía (manual o automática) aún abierta."""
    from .purchasing import OPEN_STATES
    s = db()
    total = 0.0
    total += sum(r.cantidad for r in s.execute(select(ProductionRequest).where(
        ProductionRequest.order_id == order.id, ProductionRequest.product_code == product_code,
        ProductionRequest.estado.in_(OPEN_PROD))).scalars())
    for r in s.execute(select(RepackRequest).where(RepackRequest.order_id == order.id,
                                                    RepackRequest.producto_destino == product_code,
                                                    RepackRequest.estado.in_(OPEN_REPACK))).scalars():
        total += r.cantidad_destino if r.cantidad_destino else r.cantidad
    total += sum(t.cantidad for t in s.execute(select(Transfer).where(
        Transfer.order_id == order.id, Transfer.estado.in_(OPEN_TRANSFER))).scalars() if t.lot.product_code == product_code)
    for r in s.execute(select(PurchaseRequest).where(PurchaseRequest.product_code == product_code,
                                                      PurchaseRequest.estado.in_(OPEN_STATES))).scalars():
        if r.ordenes:  # presolicitud agrupada (obs. demo v0.7): solo cuenta la parte de esta OV
            total += sum(x.get("cantidad") or 0 for x in r.ordenes if x.get("order_id") == order.id)
        elif r.order_id == order.id:
            total += r.cantidad
    return total


def _units_from(src_product, dst_product, dst_units):
    """Unidades del producto origen necesarias para obtener dst_units del destino (por peso, si se conoce)."""
    if src_product.code == dst_product.code:
        return dst_units
    if src_product.peso_kg and dst_product.peso_kg:
        return dst_units * dst_product.peso_kg / src_product.peso_kg
    return None


def generate_for_order(order, user=None):
    """Las pre-solicitudes las crea el sistema (sin usuario); 'user' solo queda en la auditoría como quien originó la
    evaluación."""
    if not param("presolicitudes_automaticas", True):
        return []
    from . import production as prod
    from . import purchasing as buy
    from . import repack
    from . import transfers as trs
    from .stock import alternatives_for_order, principal_warehouses
    orden = [o for o in (param("orden_presolicitudes", list(VIABLES)) or []) if o in VIABLES]
    creadas = []
    for item in alternatives_for_order(order):
        line = item["line"]
        product = line.product
        pend = item["faltante"] - open_requested(order, line.product_code)
        for opcion in orden:
            if pend <= 1e-9:
                break
            if opcion == "PRODUCCION":
                req = item["produccion"]
                if req and req.get("factible"):
                    r = prod.create_request(line.product_code, pend, None, order=order,
                                            observacion="Pre-solicitud automática por faltante (Q15). Almacén revisa y envía.")
                    creadas.append(("Producción", f"#{r.id}", line.product_code, pend))
                    pend = 0
            elif opcion == "REEMPAQUE":
                for op in item["reempaque"]:
                    if pend <= 1e-9:
                        break
                    lot = op["lot"]
                    src = lot.product
                    disp = op["cantidad"]
                    if disp <= 1e-9 or src is None:
                        continue
                    origen_necesario = _units_from(src, product, pend)
                    if origen_necesario is None:
                        continue  # sin peso no se puede convertir la presentación
                    usar = min(disp, origen_necesario)
                    obtiene = pend if usar >= origen_necesario - 1e-9 else usar * (src.peso_kg or 1) / (product.peso_kg or 1) \
                        if src.code != product.code else usar
                    r = repack.request(None, op["tipo"], lot.id, usar, producto_destino=line.product_code,
                                       cantidad_destino=obtiene, order=order, presolicitud=True,
                                       motivo=f"Pre-solicitud automática por faltante de la OV {order.numero} (Q15). {op['motivo']}")
                    creadas.append(("Reempaque", f"#{r.id}", line.product_code, obtiene))
                    pend -= obtiene
            elif opcion == "TRASLADO":
                destinos = principal_warehouses(product)
                if not destinos:
                    continue
                for alt in item["otros_almacenes"]:
                    if pend <= 1e-9:
                        break
                    if not alt["apto"]:
                        continue
                    disp = trs.transferable_qty(alt["lot"])
                    if disp <= 1e-9:
                        continue
                    q = min(disp, pend)
                    t = trs.request_transfer(None, alt["lot"].id, destinos[0].code, q, order, sistema=True,
                                             observacion=f"Pre-solicitud automática por faltante de la OV {order.numero} (Q15)")
                    creadas.append(("Traslado", f"#{t.id}", line.product_code, q))
                    pend -= q
            elif opcion == "COMPRA":
                if item["compra"]:
                    r = buy.create_request(None, line.product_code, pend, order.fecha_compromiso, origen="OV", order=order,
                                           sistema=True)
                    creadas.append(("Compra", f"#{r.id}", line.product_code, pend))
                    pend = 0
    if creadas:
        alerts.emit("PRESOLICITUD_AUTOMATICA", f"Pre-solicitudes generadas para la OV {order.numero}",
                    "; ".join(f"{t} {n}: {p} × {q:g}" for t, n, p, q in creadas) + ". Requieren aprobación del responsable.",
                    "SalesOrder", order.id, creado_por=user)
        audit(user, "PRESOLICITUDES_AUTOMATICAS", "SalesOrder", order.numero,
              {"creadas": [{"tipo": t, "id": n, "producto": p, "cantidad": q} for t, n, p, q in creadas]})
    return creadas
