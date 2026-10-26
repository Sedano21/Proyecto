"""Penalidades de clientes (observaciones del módulo V7, 26-oct-2026).

- Condiciones: Comercial registra sin límite los tipos de penalidad del cliente (de la lista o uno nuevo) con su monto
  (fijo en S/ o % de la OV); al guardarlas se actualiza solo la tabla de condiciones y penalidades del cliente.
- Detección: al registrar la entrega, el sistema compara la entrega con las condiciones del cliente (fecha
  comprometida, entrega parcial y fill rate mínimo) y registra la «penalidad calculada». Alerta al vendedor o ejecutivo,
  al Coordinador y al Jefe Comercial para que registren si se PAGÓ (monto pagado) o se DESESTIMÓ (motivo).
- Indicador de gestión comercial: calculada vs pagada vs desestimada, por vendedor y por cliente.
"""
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import Customer, CustomerCondition, CustomerPenalty, now
from . import alerts
from .core import BusinessError, audit, has_perm

ESTADOS = ("PENDIENTE", "PAGADA", "DESESTIMADA")


def _txt(tipo):
    from .customer_conditions import TIPO_TXT
    return TIPO_TXT.get(tipo, tipo.replace("_", " ").capitalize())


def condition_for(customer, crear=False):
    from .customer_conditions import for_customer, norm_name
    c = for_customer(customer)
    if c is None and crear:
        nn = norm_name(customer.nombre)
        if db().execute(select(CustomerCondition).where(CustomerCondition.nombre_norm == nn)).scalars().first():
            nn = f"{nn} {customer.ruc}"
        c = CustomerCondition(nombre=customer.nombre, nombre_norm=nn, ruc=customer.ruc or "",
                              customer_id=customer.id, origen="Ficha del cliente (módulo)")
        db().add(c)
        db().flush()
    return c


def save_conditions(customer, user, filas):
    """filas: [{"tipo", "nombre" (si es nuevo), "modo" FIJO/PCT_OV, "valor"}]. Reemplaza la tabla de penalidades del
    cliente (sin límite de filas). FILL_RATE se calcula con el mínimo del cliente."""
    if not (has_perm(user, "clientes.editar") or has_perm(user, "clientes.canal")):
        raise BusinessError("Su rol no edita condiciones de clientes.")
    cond = condition_for(customer, crear=True)
    tipos, montos = [], {}
    for i, f in enumerate(filas, start=1):
        t = (f.get("tipo") or "").strip().upper()
        if t == "OTRO":
            nombre = " ".join((f.get("nombre") or "").split())
            if not nombre:
                raise BusinessError(f"Fila {i}: indique el nombre de la penalidad nueva.")
            t = "_".join(nombre.upper().split())[:50]
        if not t:
            continue
        if t in tipos:
            raise BusinessError(f"Fila {i}: la penalidad «{_txt(t)}» está repetida.")
        tipos.append(t)
        valor = str(f.get("valor") or "").strip()
        if valor and t != "FILL_RATE":
            modo = f.get("modo") or "FIJO"
            if modo not in ("FIJO", "PCT_OV"):
                raise BusinessError("Modo de penalidad no válido.")
            try:
                v = float(valor)
            except ValueError:
                raise BusinessError(f"Fila {i}: monto inválido.")
            if v < 0 or (modo == "PCT_OV" and v > 100):
                raise BusinessError(f"Fila {i}: monto inválido.")
            montos[t] = {"modo": modo, "valor": v}
    antes = {"tipos": cond.penalidad_tipos, "montos": cond.penalidad_montos}
    cond.penalidad_tipos = tipos
    cond.penalidad_montos = montos
    audit(user, "CLIENTE_PENALIDADES", "Customer", customer.ruc, {"antes": antes, "despues": {"tipos": tipos, "montos": montos}})
    return cond


def _monto(cfg, total):
    if not cfg or cfg.get("valor") in (None, ""):
        return 0.0, "Monto no definido en la ficha del cliente"
    v = float(cfg["valor"])
    if cfg.get("modo") == "PCT_OV":
        return round(total * v / 100.0, 2), f"{v:g}% del monto de la OV (S/ {total:,.2f})"
    return round(v, 2), "Monto fijo de la ficha del cliente"


def detect_for_order(order, user=None, fecha_entrega=None):
    """Compara la entrega con las condiciones del cliente y registra las penalidades calculadas (sin duplicar)."""
    from .orders import order_amount
    cond = condition_for(order.customer)
    if cond is None or not cond.penalidad_tipos:
        return []
    fecha_entrega = fecha_entrega or date.today()
    total = order_amount(order)
    pedido = sum(l.cantidad for l in order.lines if l.activa) or 0
    entregado = sum(l.entregado for l in order.lines if l.activa)
    fill = (entregado / pedido * 100.0) if pedido else 100.0
    no_atendido = sum(max(l.cantidad - l.entregado, 0) * (l.precio_unitario or 0) for l in order.lines if l.activa)
    hallazgos = []
    for t in cond.penalidad_tipos:
        if t == "FECHA_ENTREGA" and fecha_entrega > order.fecha_compromiso:
            m, base = _monto((cond.penalidad_montos or {}).get(t), total)
            hallazgos.append((t, f"Entregada el {fecha_entrega:%d/%m/%Y}, comprometida el {order.fecha_compromiso:%d/%m/%Y}", m, base))
        elif t == "ENTREGA_PARCIAL" and entregado < pedido - 1e-9:
            m, base = _monto((cond.penalidad_montos or {}).get(t), total)
            hallazgos.append((t, f"Entrega parcial: {entregado:g} de {pedido:g}", m, base))
        elif t == "FILL_RATE" and cond.fill_rate_min_pct and fill < cond.fill_rate_min_pct - 1e-9:
            hallazgos.append((t, f"Fill rate {fill:.1f}% bajo el mínimo del cliente {cond.fill_rate_min_pct:g}%",
                              round(no_atendido, 2), "Monto no atendido de la OV"))
    nuevas = []
    for t, desc, m, base in hallazgos:
        ya = db().execute(select(CustomerPenalty).where(CustomerPenalty.order_id == order.id,
                                                        CustomerPenalty.tipo == t)).scalars().first()
        if ya:
            continue
        p = CustomerPenalty(customer_id=order.customer_id, order_id=order.id, tipo=t, descripcion=desc, origen="SISTEMA",
                            fecha=fecha_entrega, monto_calculado=m, base_calculo=base[:250], vendedor_id=order.vendedor_id,
                            creado_por=user.id if user else None)
        db().add(p)
        db().flush()
        nuevas.append(p)
        _alert(p, user)
    return nuevas


def _alert(p, user):
    alerts.emit("CLIENTE_PENALIDAD", f"Penalidad {_txt(p.tipo)}: {p.customer.nombre}"
                + (f" · OV {p.order.numero}" if p.order else ""),
                f"{p.descripcion}. Penalidad calculada S/ {p.monto_calculado:,.2f}. Registre si se pagó o se desestimó.",
                "CustomerPenalty", p.id, extra_users=[p.vendedor_id] if p.vendedor_id else None,
                dedup_key=f"PENALIDAD:{p.id}", creado_por=user)


def register(customer, user, tipo, descripcion, monto_calculado, order=None, fecha=None):
    """Comercial registra una penalidad que el cliente aplicó (p. ej. comunicada por correo)."""
    if not has_perm(user, "clientes.penalidad"):
        raise BusinessError("Su rol no registra penalidades.")
    if not (tipo or "").strip():
        raise BusinessError("Indique el tipo de penalidad.")
    try:
        m = float(monto_calculado or 0)
    except ValueError:
        raise BusinessError("Monto inválido.")
    if m < 0:
        raise BusinessError("Monto inválido.")
    p = CustomerPenalty(customer_id=customer.id, order_id=order.id if order else None, tipo=tipo.strip().upper()[:60],
                        descripcion=(descripcion or "").strip(), origen="MANUAL", fecha=fecha or date.today(),
                        monto_calculado=m, base_calculo="Registrada por Comercial",
                        vendedor_id=(order.vendedor_id if order else None) or customer.vendedor_id,
                        creado_por=user.id)
    db().add(p)
    db().flush()
    audit(user, "PENALIDAD_REGISTRADA", "Customer", customer.ruc, {"tipo": p.tipo, "monto": m})
    _alert(p, user)
    return p


def resolve(p, user, estado, monto_pagado=None, comentario=""):
    if not has_perm(user, "clientes.penalidad"):
        raise BusinessError("Registran el resultado el vendedor o ejecutivo, el Coordinador o el Jefe Comercial.")
    if user.role_code == "EJECUTIVO_VENTAS" and p.vendedor_id and p.vendedor_id != user.id:
        raise BusinessError("Solo el vendedor responsable, el Coordinador o el Jefe Comercial.")
    if estado not in ("PAGADA", "DESESTIMADA"):
        raise BusinessError("Elija Pagada o Desestimada.")
    if estado == "PAGADA":
        try:
            monto_pagado = float(monto_pagado)
        except (TypeError, ValueError):
            raise BusinessError("Indique el monto pagado.")
        if monto_pagado < 0:
            raise BusinessError("Monto pagado inválido.")
    elif not (comentario or "").strip():
        raise BusinessError("Indique por qué se desestimó.")
    p.estado = estado
    p.monto_pagado = monto_pagado if estado == "PAGADA" else 0.0
    p.comentario = (comentario or "").strip()
    p.resuelto_por = user.id
    p.resuelto_ts = now()
    audit(user, f"PENALIDAD_{estado}", "CustomerPenalty", p.id, {"monto_pagado": p.monto_pagado, "comentario": p.comentario})
    alerts.close_by_system(f"PENALIDAD:{p.id}", f"{estado.capitalize()} por {user.nombre}")


def indicator(desde=None, hasta=None, customer_id=None):
    """Indicador de gestión comercial: calculada vs pagada vs desestimada, total y por vendedor."""
    q = select(CustomerPenalty)
    if desde:
        q = q.where(CustomerPenalty.fecha >= desde)
    if hasta:
        q = q.where(CustomerPenalty.fecha <= hasta)
    if customer_id:
        q = q.where(CustomerPenalty.customer_id == customer_id)
    rows = list(db().execute(q.order_by(CustomerPenalty.fecha.desc())).scalars())

    def resumen(rs):
        calc = sum(r.monto_calculado for r in rs)
        pag = sum(r.monto_pagado or 0 for r in rs if r.estado == "PAGADA")
        des = sum(r.monto_calculado for r in rs if r.estado == "DESESTIMADA")
        return {"n": len(rs), "calculada": round(calc, 2), "pagada": round(pag, 2), "desestimada": round(des, 2),
                "pendiente": round(sum(r.monto_calculado for r in rs if r.estado == "PENDIENTE"), 2),
                "pendientes": sum(1 for r in rs if r.estado == "PENDIENTE"),
                "pct_desestimada": round(des / calc * 100, 1) if calc else 0.0}
    por_vend = {}
    for r in rows:
        por_vend.setdefault(r.vendedor.nombre if r.vendedor else "(sin vendedor)", []).append(r)
    return {"total": resumen(rows), "por_vendedor": {k: resumen(v) for k, v in sorted(por_vend.items())}, "rows": rows}


def next_customer_code():
    """V7: código de cliente correlativo respetando el formato de los códigos de SAP (mismo prefijo y ancho)."""
    import re
    codes = [c for c in db().execute(select(Customer.codigo_sap).where(Customer.codigo_sap != "")).scalars() if c]
    from .core import param
    pref, ancho, mayor = param("prefijo_codigo_cliente", "C") or "C", 6, 0
    pats = {}
    for c in codes:
        m = re.fullmatch(r"([A-Za-z]*)(\d+)", c.strip())
        if m:
            pats.setdefault(m.group(1).upper(), []).append(m.group(2))
    if pats:
        pref = max(pats, key=lambda k: len(pats[k]))  # el prefijo más usado en SAP
        nums = pats[pref]
        ancho = max(len(n) for n in nums)
        mayor = max(int(n) for n in nums)
    return f"{pref}{mayor + 1:0{ancho}d}"
