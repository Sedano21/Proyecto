"""V29 (11-nov-2026): notas de crédito de SAP sobre OV que todavía no se despachan.

Cuando en SAP se emite una nota de crédito sobre la factura hecha desde la OV (factura de reserva o factura anticipada),
lo acreditado ya no se despacha:
- se descuenta de la cantidad por despachar de la línea de la OV en el módulo (lo ya despachado no se toca);
- se liberan las reservas que sobran (las más recientes primero);
- si ya se preparó más de lo que queda, se avisa para devolverlo al stock;
- si no queda nada por despachar en la OV, la OV se cierra en el módulo;
- se avisa a Comercial, Almacén y Distribución, y el picking y la OV muestran qué NO se despacha.
Si la nota es sobre la factura de una guía (la mercadería ya salió), solo se registra: no cambia el picking.
Cada línea de nota se aplica una sola vez.
"""
from sqlalchemy import func, select

from ..db import db
from ..models import OrderCreditNote
from . import alerts
from .core import audit

TOL = 1e-6
ORIGEN_TXT = {"FACTURA_RESERVA": "factura de reserva", "FACTURA_OV": "factura hecha desde la OV",
              "FACTURA_GUIA": "factura de la guía (ya despachado)"}


def _fecha(v):
    from datetime import date
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _liberar_exceso(line, motivo):
    from .stock import _release, line_reserved
    necesario = max(line.cantidad - (line.despachado or 0), 0) if line.activa else 0.0
    exceso = line_reserved(line) - necesario
    liberado = 0.0
    for r in sorted([r for r in line.reservations if r.estado == "ACTIVA"], key=lambda r: r.id, reverse=True):
        if exceso <= TOL:
            break
        if r.cantidad <= exceso + TOL:
            exceso -= r.cantidad
            liberado += r.cantidad
            _release(r, motivo)
        else:
            r.cantidad -= exceso
            liberado += exceso
            exceso = 0
    return liberado


def aplicar(user, filas):
    """Registra y aplica las líneas de notas de crédito leídas de SAP. Devuelve el resumen."""
    from .orders import order_by_number
    from .stock import ORDEN_ESTADOS_CERRADOS
    s = db()
    ya = {c for (c,) in s.execute(select(OrderCreditNote.clave))}
    res = {"leidas": len(filas), "aplicadas": 0, "ya_despachado": 0, "sin_ov": 0, "repetidas": 0}
    tocadas = {}
    for f in filas:
        if f["clave"] in ya:
            res["repetidas"] += 1
            continue
        ya.add(f["clave"])
        o = order_by_number(f["ov"])
        nc = OrderCreditNote(clave=f["clave"][:40], nc_numero=f["nc_numero"][:40], factura=f.get("factura", "")[:40],
                             fecha=_fecha(f.get("fecha")), ov_numero=str(f["ov"])[:30], order_id=o.id if o else None,
                             product_code=f["producto"][:30], cantidad=float(f["cantidad"] or 0), origen=f.get("origen", ""),
                             comentario=f.get("comentario", ""))
        s.add(nc)
        if o is None:
            nc.estado = "SIN_OV"
            res["sin_ov"] += 1
            continue
        line = next((l for l in o.lines if l.activa and l.product_code == nc.product_code), None)
        pend = max(line.cantidad - (line.despachado or 0), 0) if line is not None else 0.0
        if nc.origen == "FACTURA_GUIA" or o.estado in ORDEN_ESTADOS_CERRADOS or line is None or pend <= TOL:
            nc.estado = "YA_DESPACHADO"
            res["ya_despachado"] += 1
            continue
        apl = min(nc.cantidad, pend)
        nc.line_id = line.id
        nc.aplicada = apl
        if line.cantidad_venta and line.cantidad:
            line.cantidad_venta = round(line.cantidad_venta * (line.cantidad - apl) / line.cantidad, 6)
        line.cantidad -= apl
        if line.cantidad - (line.despachado or 0) <= TOL and (line.despachado or 0) <= TOL:
            line.activa = False
        nc.liberado = _liberar_exceso(line, f"Nota de crédito {nc.nc_numero}: no se despacha")
        nc.estado = "APLICADA"
        res["aplicadas"] += 1
        tocadas.setdefault(o.id, (o, []))[1].append((nc, line))
    s.flush()
    for o, items in tocadas.values():
        _avisar(o, items, user)
    if filas:
        audit(user, "NOTAS_CREDITO_OV", "OrderCreditNote", "", res)
    return res


def _avisar(o, items, user):
    detalle, sobrepreparado = [], []
    for nc, line in items:
        detalle.append(f"{nc.product_code}: no despachar {nc.aplicada:g} (nota {nc.nc_numero}, {ORIGEN_TXT.get(nc.origen, '')}); "
                       f"queda por despachar {max(line.cantidad - (line.despachado or 0), 0):g}"
                       + (f"; reservas liberadas {nc.liberado:g}" if nc.liberado > TOL else ""))
        if (line.preparado or 0) > line.cantidad + TOL:
            sobrepreparado.append(f"{nc.product_code}: preparado {line.preparado:g}, ahora corresponde {line.cantidad:g} "
                                  f"(devolver {line.preparado - line.cantidad:g} al stock)")
    queda = any(l.activa and l.cantidad - (l.despachado or 0) > TOL for l in o.lines)
    if not queda and not any((l.despachado or 0) > TOL for l in o.lines):
        from .stock import release_order
        release_order(o, "Nota de crédito: la OV ya no tiene nada por despachar")
        o.estado = "CERRADA"
        o.motivo_detencion = "Cerrada por nota de crédito en SAP: no queda nada por despachar."[:250]
    msg = "; ".join(detalle) + "."
    if sobrepreparado:
        msg += " ATENCIÓN, ya se preparó de más: " + "; ".join(sobrepreparado) + "."
    if o.estado == "CERRADA":
        msg += " La OV queda CERRADA en el módulo: no se despacha."
    alerts.emit("OV_NOTA_CREDITO", f"Nota de crédito en la OV {o.numero} ({o.customer.nombre if o.customer else ''}): "
                                   f"cambia lo que se despacha", msg, "SalesOrder", o.id,
                prioridad="ALTA" if sobrepreparado or o.estado in ("EN_PREPARACION", "LISTA", "PREPARADA") else None,
                extra_users=[o.vendedor_id] if o.vendedor_id else None,
                dedup_key=f"OV_NC:{o.id}:{','.join(nc.clave for nc, _ in items)}"[:120], creado_por=user)


def aplicadas_por_ov(numero):
    """{producto: cantidad dejada de despachar por notas de crédito} de una OV."""
    q = select(OrderCreditNote.product_code, func.sum(OrderCreditNote.aplicada)).where(
        OrderCreditNote.ov_numero == str(numero), OrderCreditNote.estado == "APLICADA").group_by(OrderCreditNote.product_code)
    return {p: float(c or 0) for p, c in db().execute(q)}


def de_orden(order):
    """Notas de crédito unidas a la OV (para mostrarlas en la OV y en el picking)."""
    if order is None or order.id is None:
        return []
    from sqlalchemy import or_
    nums = [n for n in (order.numero, order.sap_docnum) if n]
    return list(db().execute(select(OrderCreditNote).where(or_(OrderCreditNote.order_id == order.id,
                                                               OrderCreditNote.ov_numero.in_(nums)))
                             .order_by(OrderCreditNote.id)).scalars())


def listado(estado=""):
    q = select(OrderCreditNote).order_by(OrderCreditNote.id.desc())
    if estado:
        q = q.where(OrderCreditNote.estado == estado)
    return list(db().execute(q.limit(500)).scalars())
