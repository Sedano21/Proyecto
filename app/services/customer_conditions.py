"""Condiciones comerciales por cliente (archivo 'LISTA DE CLIENTES - CON PENALIDADES Y LOTES', 13-oct-2026).

- Lotes por SKU ("1 LOTE POR SKU", "2 LOTES POR SKU"): la reserva no usa más lotes de los permitidos por producto.
- Penalidades: se clasifican por tipo (ventana horaria, fecha de entrega PAE, fill rate, paletizado, documentos, peso,
  ruptura de stock, no conformidades) y se muestran en la OV, la preparación y la ruta. Con el criterio 'penalidad' en el
  orden de prioridad, a igual fecha comprometida se atiende primero al cliente con penalidades más severas (pesos
  configurables, propuestos).
- Vida útil: es la vida útil RESTANTE mínima al despacho (confirmado el 13-oct, R1). Se mide en meses calendario y
  admite excepciones por familia ("12 MESES / 6 MESES HARINAS": harinas con 6 meses).
- El archivo original no trae RUC (se agregará después, R2): si la fila trae RUC se vincula por RUC; si no, por nombre
  normalizado con los clientes existentes y con los que se creen después al importar OV.
"""
import calendar
from datetime import date
import re
import unicodedata

from sqlalchemy import select

from ..db import db
from ..models import Customer, CustomerCondition
from .core import param

TIPOS = [
    ("VENTANA_HORARIA", r"VENTANA HORARIA"),
    ("FECHA_ENTREGA", r"FECHA DE ENTREGA|PAE"),
    ("FILL_RATE", r"FILL RATE"),
    ("RETIRO_PROVEEDOR", r"RETIRO (DE )?PROVEEDOR|BLOQUEO"),
    ("PALETIZADO", r"PALETIZADO"),
    ("DOCUMENTOS", r"DOCUMENTOS"),
    ("PESO", r"PESO"),
    ("ENTREGA_PARCIAL", r"FALTA DE ENTREGA|PARCIAL"),
    ("RUPTURA_STOCK", r"RUPTURA"),
    ("NO_CONFORMIDADES", r"NO CONFORMIDADES"),
]
TIPO_TXT = {"VENTANA_HORARIA": "ventana horaria", "FECHA_ENTREGA": "fecha de entrega", "FILL_RATE": "fill rate",
            "RETIRO_PROVEEDOR": "bloqueo/retiro de proveedor", "PALETIZADO": "paletizado", "DOCUMENTOS": "documentos",
            "PESO": "peso", "ENTREGA_PARCIAL": "falta de entrega o parcial", "RUPTURA_STOCK": "ruptura de stock no informada",
            "NO_CONFORMIDADES": "no conformidades reiteradas"}


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


def parse(lotes, vida, penalidades):
    out = {"max_lotes_por_sku": None, "vida_util_meses": None, "penalidad_tipos": [], "fill_rate_min_pct": None}
    m = re.search(r"(\d+)\s*LOTE", str(lotes or "").upper())
    if m:
        out["max_lotes_por_sku"] = int(m.group(1))
    m = re.search(r"(\d+)\s*MES", str(vida or "").upper())
    if m:
        out["vida_util_meses"] = int(m.group(1))
    txt = str(penalidades or "").upper()
    out["penalidad_tipos"] = [t for t, rx in TIPOS if re.search(rx, txt)]
    fr = [float(x) for x in re.findall(r"FILL RATE\s*<\s*(\d+(?:\.\d+)?)\s*%", txt)]
    if fr:
        out["fill_rate_min_pct"] = max(fr)
    return out


def for_customer(customer):
    if customer is None:
        return None
    s = db()
    c = s.execute(select(CustomerCondition).where(CustomerCondition.customer_id == customer.id)).scalars().first()
    if c is None and customer.ruc:
        c = s.execute(select(CustomerCondition).where(CustomerCondition.ruc == customer.ruc)).scalars().first()
        if c is not None and c.customer_id is None:
            c.customer_id = customer.id  # vínculo por RUC
    if c is None:
        c = s.execute(select(CustomerCondition).where(CustomerCondition.nombre_norm == norm_name(customer.nombre))).scalars().first()
        if c is not None and c.ruc and c.ruc != customer.ruc:
            c = None  # la condición pertenece a otro RUC con el mismo nombre
        if c is not None and c.customer_id is None:
            c.customer_id = customer.id  # vínculo por nombre
    return c


def max_lots(customer):
    c = for_customer(customer)
    return c.max_lotes_por_sku if c and c.max_lotes_por_sku else None


def penalty_score(customer):
    c = for_customer(customer)
    if c is None:
        return 0
    pesos = param("peso_penalidad", {}) or {}
    return sum(float(pesos.get(t, 0) or 0) for t in (c.penalidad_tipos or []))


def add_months(d, meses):
    m = d.month - 1 + meses
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def shelf_rule(texto):
    """'12 MESES / 6 MESES HARINAS' -> (12, {'HARINA': 6})."""
    general, excep = None, {}
    for parte in re.split(r"[/;,]", str(texto or "").upper()):
        m = re.search(r"(\d+)\s*MES(?:ES)?\s*(.*)", parte.strip())
        if not m:
            continue
        fam = m.group(2).strip()
        if fam:
            excep[re.sub(r"S$", "", fam.split()[0])] = int(m.group(1))
        elif general is None:
            general = int(m.group(1))
    return general, excep


def min_shelf_months(customer, product=None):
    """Meses de vida útil restante mínima que exige el cliente para el producto (None si no aplica)."""
    if not param("aplicar_vida_util_cliente", False):
        return None
    c = for_customer(customer)
    if c is None:
        return None
    general, excep = shelf_rule(c.vida_util_texto) if c.vida_util_texto else (c.vida_util_meses, {})
    if product is not None and excep:
        nombre = f"{product.descripcion or ''} {product.producto_base or ''}".upper()
        for fam, meses in excep.items():
            if fam in nombre:
                return meses
    return general or c.vida_util_meses


def min_shelf_date(customer, product, ref):
    """Fecha mínima de vencimiento aceptable para despachar en 'ref' (meses calendario)."""
    meses = min_shelf_months(customer, product)
    return add_months(ref, meses) if meses else None


def min_shelf_days(customer):
    meses = min_shelf_months(customer)
    return meses * 30 if meses else None


def summary(customer):
    c = for_customer(customer)
    if c is None:
        return ""
    partes = []
    if c.max_lotes_por_sku:
        partes.append(f"máx. {c.max_lotes_por_sku} lote(s) por SKU")
    if c.vida_util_texto:
        partes.append(f"vida útil restante mín. al despacho {c.vida_util_texto.lower()}")
    if c.penalidad_tipos:
        partes.append("penalidades: " + ", ".join(TIPO_TXT.get(t, t) for t in c.penalidad_tipos))
    return "; ".join(partes)


def link_all():
    """Vincula condiciones pendientes con clientes existentes por nombre normalizado."""
    s = db()
    todos = list(s.execute(select(Customer)).scalars())
    por_nombre = {norm_name(c.nombre): c for c in todos}
    por_ruc = {c.ruc: c for c in todos}
    n = 0
    for cond in s.execute(select(CustomerCondition).where(CustomerCondition.customer_id.is_(None))).scalars():
        cu = por_ruc.get(cond.ruc) if cond.ruc else por_nombre.get(cond.nombre_norm)
        if cu is not None:
            cond.customer_id = cu.id
            n += 1
    return n


def penalty_estimate(order):
    """Penalidad estimada de la OV según las condiciones del cliente (observación del 14-oct, Asistente de Ventas).
    - Fill rate: si la cobertura de la OV queda bajo el mínimo del cliente, se estima lo no atendido (S/) más el margen
      perdido cuando hay costo vigente (el rebate no se puede calcular: no hay dato).
    - Otros tipos: se usa el monto registrado en la ficha del cliente (fijo o % de la OV); si no hay, se indica.
    Devuelve [{tipo, texto, riesgo, monto, base}]."""
    from .costs import cost_for_line
    from .orders import order_amount
    c = for_customer(order.customer)
    if c is None or not c.penalidad_tipos:
        return []
    montos = c.penalidad_montos or {}
    total = order_amount(order)
    out = []
    incompleta = order.estado_stock in ("INCOMPLETA", "SIN_STOCK") or (order.cobertura_unidades or 100) < 100
    for t in c.penalidad_tipos:
        item = {"tipo": t, "texto": TIPO_TXT.get(t, t), "riesgo": None, "monto": None, "base": ""}
        if t == "FILL_RATE" and c.fill_rate_min_pct:
            item["riesgo"] = (order.cobertura_unidades or 0) < c.fill_rate_min_pct
            no_atendido = sum(max(l.cantidad - l.despachado, 0) * (l.precio_unitario or 0) for l in order.lines if l.activa) \
                * max(0.0, 1 - (order.cobertura_unidades or 0) / 100.0)
            margen = 0.0
            for l in order.lines:
                if l.activa:
                    costo = cost_for_line(l)
                    if costo is not None and l.precio_unitario:
                        margen += (l.precio_unitario - costo) * l.cantidad * max(0.0, 1 - (order.cobertura_unidades or 0) / 100.0)
            item["monto"] = round(no_atendido + margen, 2) if item["riesgo"] else 0.0
            item["base"] = (f"Cobertura {order.cobertura_unidades}% vs mínimo {c.fill_rate_min_pct:g}%: no atendido S/ "
                            f"{no_atendido:,.2f} + margen perdido S/ {margen:,.2f} (rebate: sin dato)")
        else:
            if t in ("FECHA_ENTREGA", "ENTREGA_PARCIAL", "RUPTURA_STOCK"):
                item["riesgo"] = incompleta
            cfg = montos.get(t) or {}
            if cfg.get("valor") not in (None, ""):
                v = float(cfg["valor"])
                item["monto"] = round(total * v / 100.0, 2) if cfg.get("modo") == "PCT_OV" else round(v, 2)
                item["base"] = f"{v:g}% del monto de la OV" if cfg.get("modo") == "PCT_OV" else "Monto fijo registrado en la ficha"
            else:
                item["base"] = "Monto no definido en la lista del cliente: regístrelo en la ficha del cliente"
        out.append(item)
    return out


def set_penalty_amounts(cond, user, valores):
    """Comercial registra el monto de cada tipo de penalidad (fijo en S/ o % de la OV)."""
    from .core import BusinessError, audit, has_perm
    if not (has_perm(user, "clientes.editar") or has_perm(user, "clientes.canal")):
        raise BusinessError("Su rol no edita condiciones de clientes.")
    nuevo = {}
    for t, (modo, valor) in valores.items():
        if valor in (None, ""):
            continue
        if modo not in ("FIJO", "PCT_OV"):
            raise BusinessError("Modo de penalidad no válido.")
        v = float(valor)
        if v < 0 or (modo == "PCT_OV" and v > 100):
            raise BusinessError("Monto de penalidad inválido.")
        nuevo[t] = {"modo": modo, "valor": v}
    audit(user, "CLIENTE_PENALIDAD_MONTOS", "CustomerCondition", cond.nombre, {"antes": cond.penalidad_montos, "despues": nuevo})
    cond.penalidad_montos = nuevo


def by_product(order):
    """Condición del cliente aplicada a cada producto de la OV (observaciones al demo v0.6): vida útil restante mínima
    al despacho para ESE producto (con la excepción por familia, p. ej. harinas), lotes por SKU, cuántos lotes cumplen y,
    si no alcanza, por qué y las opciones aplicables en el orden decidido por el usuario (15-oct-2026):
    1. producción, 2. reempaque, 3. traslado externo, 4. compra (ver action_options)."""
    from .stock import line_reserved, lot_usable, lots_of, principal_warehouses
    c = for_customer(order.customer)
    out = []
    for line in order.lines:
        if not line.activa or line.product is None:
            continue
        p = line.product
        meses = min_shelf_months(order.customer, p)
        texto = []
        if meses:
            texto.append(f"vida útil restante mínima al despacho {meses} meses"
                         + (" (regla por familia)" if c and c.vida_util_texto and str(meses) != str(c.vida_util_meses) else ""))
        if order.customer.vida_util_min_dias:
            texto.append(f"vida útil mínima {order.customer.vida_util_min_dias} días")
        if c and c.max_lotes_por_sku:
            texto.append(f"máx. {c.max_lotes_por_sku} lote(s) por SKU")
        necesario = max(line.cantidad - line.despachado, 0)
        faltante = max(necesario - line_reserved(line), 0)
        cumplen, por_fecha = [], []
        for lot in lots_of(line.product_code, [w.code for w in principal_warehouses(p)]):
            ok, why = lot_usable(lot, order.fecha_compromiso, order.customer)
            if ok:
                cumplen.append(lot)
            elif "Vida útil" in why or "Vencido" in why:
                por_fecha.append((lot, why))
        accion, motivo, opciones = "", "", []
        if faltante > 1e-9:
            motivo = ("; ".join(f"lote {l.lote}: {w}" for l, w in por_fecha[:3]) if por_fecha
                      else "No hay stock que cumpla la condición del cliente")
            opciones = action_options(order, line, faltante, por_fecha)
            accion = " → ".join(f"{i}. {o}" for i, o in enumerate(opciones, 1)) if opciones else "Sin opciones disponibles"
        out.append({"line": line, "condicion": "; ".join(texto) or "Sin condición específica para este producto",
                    "meses": meses, "cumplen": len(cumplen), "no_cumplen": len(por_fecha), "faltante": faltante,
                    "motivo": motivo, "accion": accion, "opciones": opciones})
    return out


def action_options(order, line, faltante, por_fecha):
    """Opciones cuando el stock no cumple la condición del cliente, en el orden decidido el 15-oct-2026 (el mismo de las
    pre-solicitudes, Q15): 1) producción, 2) reempaque (si lo único que falla es el vencimiento), 3) traslado desde un
    almacén externo con lote que cumpla, 4) compra. Solo se listan las aplicables."""
    from .production import material_requirements
    from .stock import alternative_warehouses, free_qty, lot_usable, lots_of
    nombres = {"PRODUCCION": "Producir", "REEMPAQUE": "Reempaque por actualización de fecha",
               "TRASLADO": "Traslado desde almacén externo", "COMPRA": "Compra"}
    orden = [x for x in (param("orden_presolicitudes", []) or []) if x in nombres] or list(nombres)
    out = []
    for o in orden:
        if o == "PRODUCCION":
            req = material_requirements(line.product_code, faltante)
            if req.get("bom_encontrada"):
                out.append(nombres[o] + ("" if req.get("factible") else " (revisar materiales)"))
        elif o == "REEMPAQUE" and por_fecha:
            cant = sum(l.cantidad for l, _ in por_fecha)
            out.append(nombres[o] + ("" if cant >= faltante - 1e-9 else f" (cubre {cant:g} de {faltante:g})"))
        elif o == "TRASLADO":
            externos = [l for l in lots_of(line.product_code, [w.code for w in alternative_warehouses()])
                        if lot_usable(l, order.fecha_compromiso, order.customer)[0] and free_qty(l) > 1e-9]
            if externos:
                out.append(nombres[o] + " (" + ", ".join(sorted({l.warehouse_code for l in externos})) + ")")
        elif o == "COMPRA":
            out.append(nombres[o])
    return out


def check_condition_alerts(order, user=None):
    """Alerta a Almacén y Logística el motivo cuando el stock existente no cumple la condición del cliente."""
    from . import alerts
    for x in by_product(order):
        key = f"OV_COND:{order.id}:{x['line'].id}"
        if x["no_cumplen"] and x["faltante"] > 1e-9:
            alerts.emit("OV_CONDICION_CLIENTE", f"OV {order.numero}: {x['line'].product_code} no cumple la condición del cliente",
                        f"{x['line'].product.descripcion}. Condición: {x['condicion']}. Motivo: {x['motivo']}. "
                        f"Acción sugerida: {x['accion']}.", "SalesOrder", order.id, dedup_key=key, creado_por=user)
        else:
            alerts.close_by_system(key, "La línea ya cumple o no tiene faltante")
