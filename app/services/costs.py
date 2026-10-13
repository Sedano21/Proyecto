"""Costos de la empresa y precios de mercado (respuestas del 13-oct, R4 y R5).

Escenario 1 – ninguna venta por debajo del costo: cada línea de OV se compara con el costo vigente del artículo (en la
unidad de venta: unidad/presentación, kg o saco). Si el precio es menor al costo, la OV queda detenida igual que con el
precio mínimo (confirma el Coordinador o el Jefe Comercial) y se alerta a quienes ven costos.
Escenario 2 – comparación automática con el mercado: el sistema cruza el costo por kg de cada artículo con el último
precio de mercado del producto base (mayorista, minorista o importación) y su tendencia, y emite recomendaciones. Se
recalcula cada vez que se cargan costos o precios de mercado y en la tarea programada diaria.
El costo se carga desde la columna 'COSTO EMPRESA' de las listas de precios o desde un Excel de costos.
"""
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import MarketPrice, Product, ProductCost, now
from .core import BusinessError, audit, has_perm, param


def _require(user, perm="costos.cargar"):
    if not has_perm(user, perm):
        raise BusinessError("Solo el Jefe Comercial carga costos y precios de mercado.")


def replace_costs(items, user, origen):
    """items: dicts product_code, descripcion, costo, unidad (UND/KG). Versiona solo los que cambian."""
    _require(user)
    s = db()
    ts = now()
    nuevos = cambios = 0
    for it in items:
        if it.get("costo") in (None, "") or float(it["costo"]) <= 0:
            continue
        code = it["product_code"].strip().upper()
        unidad = (it.get("unidad") or "UND").upper()
        old = s.execute(select(ProductCost).where(ProductCost.product_code == code, ProductCost.unidad == unidad,
                                                  ProductCost.vigente.is_(True))).scalars().first()
        if old is not None:
            if abs(old.costo - float(it["costo"])) < 1e-9:
                continue
            old.vigente, old.hasta = False, ts
            cambios += 1
        else:
            nuevos += 1
        s.add(ProductCost(product_code=code, descripcion=it.get("descripcion", ""), costo=float(it["costo"]), unidad=unidad,
                          desde=ts, origen=origen, user_id=user.id if user else None))
    s.flush()
    audit(user, "COSTOS_CARGADOS", "ProductCost", origen, {"nuevos": nuevos, "modificados": cambios})
    return {"costos_nuevos": nuevos, "costos_modificados": cambios}


def current_cost(product_code):
    rows = list(db().execute(select(ProductCost).where(ProductCost.product_code == product_code,
                                                       ProductCost.vigente.is_(True))).scalars())
    return {r.unidad: r for r in rows}


def cost_per_kg(product):
    c = current_cost(product.code)
    if "KG" in c:
        return c["KG"].costo
    if "UND" in c and product.peso_kg:
        return c["UND"].costo / product.peso_kg
    return None


def cost_for_line(line, kg_saco=None):
    """Costo en la unidad en que la línea guarda el precio (unidad o kg) o None si no hay costo."""
    p = line.product
    if p is None:
        return None
    c = current_cost(p.code)
    if not c:
        return None
    um = (line.um_venta or "").upper()
    # SACO: la línea guarda cantidad y precio por kg (orders.convert_sale_units)
    es_kg = um in ("KG", "SACO") or (not um and (p.um or "").upper().startswith("K"))
    if es_kg:
        return cost_per_kg(p)
    if "UND" in c:
        return c["UND"].costo
    return c["KG"].costo * p.peso_kg if p.peso_kg else None


# ------------------------------ mercado --------------------------------------
def add_market_prices(rows, user, origen):
    _require(user)
    s = db()
    n = 0
    for r in rows:
        if not r.get("producto") or not r.get("precio_kg") or not r.get("fecha"):
            continue
        dup = s.execute(select(MarketPrice).where(MarketPrice.producto == r["producto"].upper(),
                                                  MarketPrice.variedad == (r.get("variedad") or "").upper(),
                                                  MarketPrice.tipo_precio == (r.get("tipo_precio") or "MAYORISTA").upper(),
                                                  MarketPrice.mercado == (r.get("mercado") or ""),
                                                  MarketPrice.fecha == r["fecha"])).scalars().first()
        if dup is not None:
            dup.precio_kg = float(r["precio_kg"])
            continue
        s.add(MarketPrice(producto=r["producto"].upper(), variedad=(r.get("variedad") or "").upper(),
                          precio_kg=float(r["precio_kg"]), tipo_precio=(r.get("tipo_precio") or "MAYORISTA").upper(),
                          mercado=r.get("mercado") or "", fecha=r["fecha"], fuente=r.get("fuente") or "", url=r.get("url") or "",
                          origen=origen, user_id=user.id if user else None))
        n += 1
    s.flush()
    audit(user, "PRECIOS_MERCADO_CARGADOS", "MarketPrice", origen, {"filas": n})
    return {"precios_mercado": n}


def _base(product):
    return ((product.producto_base or product.descripcion or "").upper().split("*")[0]).strip()


def _match(base, productos):
    """Producto de mercado más específico contenido en el producto base del artículo (p. ej. 'FRIJOL CANARIO')."""
    cands = [m for m in productos if m and m in base]
    return max(cands, key=len) if cands else None


def trend(series):
    """series: [(fecha, precio)] ordenada. Variación % del último precio contra el promedio de los 90 días previos."""
    if len(series) < 2:
        return None
    ult_f, ult = series[-1]
    prev = [p for f, p in series[:-1] if f >= ult_f - timedelta(days=90)] or [series[-2][1]]
    base = sum(prev) / len(prev)
    return round((ult - base) / base * 100, 1) if base else None


def market_analysis(tipo_precio="MAYORISTA"):
    """Cruce automático costo vs mercado, con tendencia y recomendación por artículo con costo vigente."""
    s = db()
    mp = list(s.execute(select(MarketPrice).where(MarketPrice.tipo_precio == tipo_precio)
                        .order_by(MarketPrice.producto, MarketPrice.fecha)).scalars())
    series = {}
    for m in mp:
        series.setdefault(m.producto, []).append((m.fecha, m.precio_kg, m))
    umbral = float(param("margen_alerta_costo_mercado_pct", 0) or 0)
    alza = float(param("tendencia_mercado_umbral_pct", 5) or 5)
    out = []
    codes = sorted({c.product_code for c in s.execute(select(ProductCost).where(ProductCost.vigente.is_(True))).scalars()})
    for code in codes:
        p = s.get(Product, code)
        if p is None:
            continue
        ckg = cost_per_kg(p)
        base = _base(p)
        mk = _match(base, list(series))
        row = {"code": code, "descripcion": p.descripcion, "base": base, "costo_kg": ckg, "mercado": mk, "precio_mercado": None,
               "fecha": None, "fuente": "", "brecha_pct": None, "tendencia_pct": None, "serie": [], "recomendaciones": []}
        if mk:
            ser = series[mk]
            f, precio, m = ser[-1]
            row.update(precio_mercado=precio, fecha=f, fuente=f"{m.mercado} · {m.fuente}".strip(" ·"),
                       tendencia_pct=trend([(x[0], x[1]) for x in ser]), serie=[(x[0].isoformat(), x[1]) for x in ser[-24:]])
            if ckg is not None and precio:
                row["brecha_pct"] = round((precio - ckg) / precio * 100, 1)
        rec = row["recomendaciones"]
        if ckg is None:
            rec.append("Sin costo por kg (falta el peso del artículo o el costo).")
        elif not mk:
            rec.append("Sin precio de mercado para el producto base: cargar la referencia.")
        else:
            if row["brecha_pct"] is not None and row["brecha_pct"] < umbral:
                rec.append(f"Costo por kg {'sobre' if row['brecha_pct'] < 0 else 'muy cerca de'} el precio {tipo_precio.lower()}"
                           " de mercado: revisar costo de compra/proveedor y el precio mínimo de lista.")
            t = row["tendencia_pct"]
            if t is not None and t >= alza:
                rec.append(f"Mercado al alza ({t:+.1f} %): evaluar adelantar compras y revisar precios mínimos.")
            elif t is not None and t <= -alza:
                rec.append(f"Mercado a la baja ({t:+.1f} %): evaluar postergar compras; vigilar competitividad del precio.")
            if row["fecha"] and (date.today() - row["fecha"]).days > int(param("antiguedad_max_precio_mercado_dias", 45) or 45):
                rec.append(f"Precio de mercado desactualizado ({row['fecha']:%d/%m/%Y}): actualizar la referencia.")
        out.append(row)
    return out


def check_market_alerts(user=None):
    """Tarea programada: alerta cuando el costo por kg queda sobre (o dentro del umbral de) el precio de mercado."""
    from . import alerts
    n = 0
    for r in market_analysis():
        key = f"COSTO_MERCADO:{r['code']}"
        if r["brecha_pct"] is not None and r["brecha_pct"] < float(param("margen_alerta_costo_mercado_pct", 0) or 0):
            alerts.emit("COSTO_SOBRE_MERCADO", f"{r['code']}: costo vs mercado {r['brecha_pct']:+.1f} %",
                        f"{r['descripcion']}: costo S/ {r['costo_kg']:.2f}/kg; mercado ({r['mercado']}) S/ "
                        f"{r['precio_mercado']:.2f}/kg al {r['fecha']:%d/%m/%Y}. " + " ".join(r["recomendaciones"]),
                        "Product", r["code"], dedup_key=key, creado_por=user)
            n += 1
        else:
            alerts.close_by_system(key, "Costo bajo el precio de mercado")
    return n


# ------------------------- impacto de cotizaciones (14-oct) ------------------
def _por_kg(product, valor_um):
    """Convierte un valor por UM del artículo a S/ por kg."""
    if valor_um is None or product is None:
        return None
    if (product.um or "").upper().startswith("K"):
        return valor_um
    return valor_um / product.peso_kg if product.peso_kg else None


def minimum_price_kg(product):
    """Precio mínimo de lista por kg más bajo (granel por kg o el menor canal / peso de la presentación)."""
    from ..models import PriceItem
    s = db()
    g = s.execute(select(PriceItem).where(PriceItem.lista == "GRANEL", PriceItem.vigente.is_(True),
                                          PriceItem.product_code == product.code)).scalars().first()
    if g is not None and g.precio_kg:
        return g.precio_kg
    ps = [i.precio for i in s.execute(select(PriceItem).where(PriceItem.lista == "GENERAL", PriceItem.vigente.is_(True),
                                                                PriceItem.product_code == product.code)).scalars() if i.precio]
    return _por_kg(product, min(ps)) if ps else None


def _demanda_kg(product, dias=90):
    from ..models import SalesHistory
    desde = date.today() - timedelta(days=dias)
    q = sum(h.cantidad for h in db().execute(select(SalesHistory).where(SalesHistory.product_code == product.code,
                                                                         SalesHistory.fecha >= desde)).scalars())
    return _por_kg(product, q) if q else None


def quote_impact(product_codes=None):
    """Para cada artículo con cotización (compras nacionales o importación) compara el nuevo costo con el costo vigente,
    el precio de mercado (mayorista e importación: reportes del Estado o de internet) y el precio mínimo de lista, y
    estima el impacto en soles sobre la demanda de los últimos 90 días."""
    from ..models import ImportShipment, PurchaseRequest
    from .imports import cost_summary
    s = db()
    cot = {}
    for r in s.execute(select(PurchaseRequest).where(PurchaseRequest.precio.is_not(None),
                                                     PurchaseRequest.estado != "ANULADA").order_by(PurchaseRequest.ts)).scalars():
        cot[r.product_code] = cot.get(r.product_code, {})
        cot[r.product_code]["nacional"] = (r, _por_kg(r.product, r.precio))
    for sh in s.execute(select(ImportShipment).where(ImportShipment.valor_mercaderia.is_not(None)).order_by(ImportShipment.ts)).scalars():
        cs = cost_summary(sh)
        cot.setdefault(sh.product_code, {})["importacion"] = (sh, _por_kg(sh.product, cs["costo_puesto_unidad"]))
    mp = list(s.execute(select(MarketPrice).order_by(MarketPrice.fecha)).scalars())
    umbral = float(param("margen_minimo_reporte_pct", 10) or 10)
    out = []
    for code, fuentes in sorted(cot.items()):
        if product_codes and code not in product_codes:
            continue
        p = s.get(Product, code)
        if p is None:
            continue
        base = _base(p)
        ref = {}
        for tipo in ("MAYORISTA", "IMPORTACION"):
            cand = [m for m in mp if m.tipo_precio == tipo and _match(base, [m.producto]) == m.producto]
            if cand:
                ref[tipo] = cand[-1]
        actual = cost_per_kg(p)
        minimo = minimum_price_kg(p)
        demanda = _demanda_kg(p)
        for origen, (doc, nuevo) in fuentes.items():
            if nuevo is None:
                continue
            fila = {"code": code, "descripcion": p.descripcion, "origen": origen, "doc": doc, "nuevo_kg": round(nuevo, 4),
                    "actual_kg": round(actual, 4) if actual is not None else None,
                    "var_pct": round((nuevo - actual) / actual * 100, 1) if actual else None,
                    "mayorista": ref.get("MAYORISTA"), "importacion_ref": ref.get("IMPORTACION"),
                    "minimo_kg": round(minimo, 4) if minimo else None,
                    "margen_min_pct": round((minimo - nuevo) / minimo * 100, 1) if minimo else None,
                    "demanda_kg_90d": round(demanda, 1) if demanda else None, "impacto_soles": None, "recomendaciones": []}
            if actual is not None and demanda:
                fila["impacto_soles"] = round((nuevo - actual) * demanda, 2)
            rec = fila["recomendaciones"]
            if fila["margen_min_pct"] is not None and fila["margen_min_pct"] < umbral:
                rec.append(f"Con este costo el margen sobre el precio mínimo de lista queda en {fila['margen_min_pct']} %: "
                           "revisar la lista de precios antes de comprar.")
            for tipo, m in ref.items():
                if nuevo > m.precio_kg:
                    rec.append(f"La cotización supera el precio {tipo.lower()} de referencia ({m.precio_kg:.2f} al {m.fecha:%d/%m/%Y}, "
                               f"{m.fuente or m.mercado}): negociar o evaluar otra fuente.")
            if fila["var_pct"] is not None and fila["var_pct"] >= float(param("tendencia_mercado_umbral_pct", 5) or 5):
                rec.append(f"Sube el costo {fila['var_pct']:+.1f} % respecto al vigente"
                           + (f" (≈ S/ {fila['impacto_soles']:,.0f} sobre la demanda de 90 días)." if fila["impacto_soles"] else "."))
            if "nacional" in fuentes and "importacion" in fuentes and origen == "importacion":
                nac = fuentes["nacional"][1]
                if nac:
                    mejor = "importación" if nuevo < nac else "compra nacional"
                    rec.append(f"Comparación: importación S/ {nuevo:.2f}/kg vs nacional S/ {nac:.2f}/kg → conviene {mejor}.")
            out.append(fila)
    return out


def check_quote_impact(product, user=None):
    """Al registrar una cotización: alerta si deja el margen sobre el precio mínimo bajo el umbral o supera el mercado."""
    from . import alerts
    if product is None:
        return
    for f in quote_impact([product.code]):
        key = f"COTIZACION_IMPACTO:{product.code}:{f['origen']}"
        if f["recomendaciones"] and (f["margen_min_pct"] is not None and f["margen_min_pct"] < float(param("margen_minimo_reporte_pct", 10) or 10)
                                     or any("supera el precio" in r for r in f["recomendaciones"])):
            alerts.emit("COTIZACION_IMPACTO", f"{product.code}: impacto de la cotización ({f['origen']}) en precios",
                        " ".join(f["recomendaciones"]), "Product", product.code, dedup_key=key, creado_por=user)
        else:
            alerts.close_by_system(key, "Cotización dentro de márgenes")
