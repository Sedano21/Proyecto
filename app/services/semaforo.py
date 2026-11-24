"""V70 (24-nov-2026): semáforo de inventarios y análisis de rotación, siguiendo el análisis de abastecimiento que
Operaciones presentó a Gerencia (ficha por familia).

Semáforo, por producto y agrupado por familia:
- **Stock**: el stock utilizable del módulo (disponible, verificado, no vencido), incluido lo reservado para OV.
- **OV abiertas**: lo que falta despachar de las OV abiertas del módulo, sin borradores.
- **Llegadas**: lo pendiente de ingresar de las órdenes de compra abiertas de SAP, en su fecha de entrega.
- **Saldo** = stock + llegadas − OV abiertas.
- **Sin stock el**: se recorre día a día: las OV salen en su fecha comprometida (las vencidas, hoy) y las llegadas
  entran en su fecha de entrega. Es el primer día en que el saldo queda negativo.
- **Stock de seguridad** = z × σ × √(plazo ÷ 30). σ es la desviación de la venta mensual de los últimos 12 meses.
  z sale del parámetro «semaforo_z» (1,65 = 95 %). El plazo es el de su categoría de reposición o, si no tiene,
  «semaforo_plazo_dias».
- **Estado**:
  - ROJO: el saldo final no cubre las OV.
  - TEMPORAL: cubre al final, pero se queda sin stock hasta que llega lo pedido.
  - ÁMBAR: cubre las OV, pero queda por debajo del stock de seguridad (hay que comprar o producir).
  - VERDE: cubre las OV y el stock de seguridad.
Venta: las guías de SAP (salidas a clientes). Si no hay, el historial de salidas cargado.

Análisis de rotación, por familia:
- venta mensual de 12 meses frente al año anterior;
- meses y semanas pico;
- presentaciones preferidas;
- clientes habituales (compran en 3 o más de los últimos 6 meses) y ocasionales;
- stock de seguridad de la familia en kg y en días.
Todo en kilos, con el peso por unidad de cada producto."""
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Product, SalesHistory, SalesOrder, SapMovement
from .core import param

ORDEN = {"ROJO": 0, "TEMPORAL": 1, "AMBAR": 2, "VERDE": 3, "SIN_MOVIMIENTO": 4}
NOMBRE = {"ROJO": "Rojo", "TEMPORAL": "Temporal", "AMBAR": "Ámbar", "VERDE": "Verde", "SIN_MOVIMIENTO": "Sin movimiento"}


def _mes(d):
    return f"{d:%Y-%m}"


def _meses_atras(ref, n):
    y, m = ref.year, ref.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}-{m:02d}")
    return list(reversed(out))  # n meses completos anteriores al mes en curso


def _kg_u(p):
    from .orders import kg_unidad
    return kg_unidad(p) if p is not None else 0.0


def salidas(desde, hasta, codes=None):
    """Líneas de venta [(fecha, código, cantidad, cliente)]: guías de SAP o, si no hay, el historial cargado."""
    q = select(SapMovement).where(SapMovement.tipo == "GUIA", SapMovement.fecha >= desde, SapMovement.fecha <= hasta)
    if codes is not None:
        q = q.where(SapMovement.product_code.in_(list(codes) or [""]))
    out = [(m.fecha, m.product_code, m.cantidad or 0, m.cliente or "") for m in db().execute(q).scalars()]
    if out:
        return out, "guías de SAP"
    q = select(SalesHistory).where(SalesHistory.fecha >= desde, SalesHistory.fecha <= hasta,
                                   SalesHistory.origen != "CONSUMO_PRODUCCION")
    if codes is not None:
        q = q.where(SalesHistory.product_code.in_(list(codes) or [""]))
    return [(h.fecha, h.product_code, h.cantidad or 0, "") for h in db().execute(q).scalars()], "historial cargado"


def _sigma(vals):
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _plazo(p):
    from .purchasing import lead_time_for
    lt, _ = lead_time_for(p) if p is not None and p.categoria_reposicion else (None, None)
    return lt.dias_max if lt else int(param("semaforo_plazo_dias", 30) or 30)


def stock_seguridad(serie, plazo_dias):
    z = float(param("semaforo_z", 1.65) or 1.65)
    return z * _sigma(serie) * math.sqrt(max(plazo_dias, 1) / 30)


def _ov_abiertas():
    """{código: [(fecha, cantidad, OV, cliente)]} de lo que falta despachar de las OV abiertas del módulo."""
    from .stock import ORDEN_ESTADOS_CERRADOS
    out = defaultdict(list)
    for o in db().execute(select(SalesOrder).where(SalesOrder.estado.notin_(ORDEN_ESTADOS_CERRADOS + ("BORRADOR",)))).scalars():
        for ln in o.lines:
            if not ln.activa:
                continue
            falta = (ln.cantidad or 0) - (ln.despachado or 0)
            if falta > 1e-9:
                out[ln.product_code].append((o.fecha_compromiso, falta, o.numero, o.customer.nombre if o.customer else ""))
    return out


def _stock_utilizable():
    from .stock import lot_usable
    from ..models import StockLot
    out = defaultdict(float)
    for lot in db().execute(select(StockLot).where(StockLot.cantidad > 0)).scalars():
        if lot_usable(lot)[0]:
            out[lot.product_code] += lot.cantidad or 0
    return out


def semaforo(ref=None, familia="", q="", tipo=""):
    from .abastecimiento import pendientes
    ref = ref or date.today()
    meses = _meses_atras(ref, 12)
    ini = date(int(meses[0][:4]), int(meses[0][5:]), 1)
    ventas, fuente = salidas(ini, ref)
    por_mes = defaultdict(lambda: defaultdict(float))
    for f, c, cant, _ in ventas:
        por_mes[c][_mes(f)] += cant
    stock = _stock_utilizable()
    ov = _ov_abiertas()
    lleg = pendientes(None, ref)
    codes = set(stock) | set(ov) | set(lleg) | set(por_mes)
    prods = {p.code: p for p in db().execute(select(Product).where(Product.code.in_(list(codes) or [""]))).scalars()}
    filas = []
    for code in sorted(codes):
        p = prods.get(code)
        if p is None:
            continue
        if familia and (p.familia or "(sin familia)") != familia:
            continue
        if tipo and (p.tipo or "") != tipo:
            continue
        if q and q.upper() not in code.upper() and q.upper() not in (p.descripcion or "").upper():
            continue
        serie = [por_mes[code].get(m, 0.0) for m in meses]
        venta_mes = sum(serie) / len(serie)
        plazo = _plazo(p)
        ss = stock_seguridad(serie, plazo)
        st = stock.get(code, 0.0)
        ovs = ov.get(code, [])
        ll = lleg.get(code, [])
        ov_total = sum(x[1] for x in ovs)
        ll_total = sum(x["pendiente"] for x in ll)
        saldo = st + ll_total - ov_total
        # día a día
        eventos = defaultdict(float)
        for f, cant, _, _ in ovs:
            eventos[max(f or ref, ref)] -= cant
        for x in ll:
            eventos[max(x["entrega"] or ref, ref)] += x["pendiente"]
        s, sin_stock, vuelve = st, None, None
        for d in sorted(eventos):
            s += eventos[d]
            if s < -1e-9 and sin_stock is None:
                sin_stock = d
            if sin_stock is not None and vuelve is None and s >= -1e-9 and d > sin_stock:
                vuelve = d
        vencidas = sum(cant for f, cant, _, _ in ovs if f and f < ref)
        if not (st or ov_total or ll_total or venta_mes):
            estado = "SIN_MOVIMIENTO"
        elif saldo < -1e-9:
            estado = "ROJO"
        elif sin_stock is not None:
            estado = "TEMPORAL"
        elif saldo < ss - 1e-9:
            estado = "AMBAR"
        else:
            estado = "VERDE"
        k = _kg_u(p)
        prox = min((x["entrega"] for x in ll if x["entrega"] and x["entrega"] >= ref), default=None)
        filas.append({"code": code, "descripcion": p.descripcion, "familia": p.familia or "(sin familia)", "tipo": p.tipo or "",
                      "marca": p.marca or "", "presentacion": p.presentacion or "", "um": p.um, "kg_u": k,
                      "stock": round(st, 2), "ov": round(ov_total, 2), "ov_vencidas": round(vencidas, 2), "n_ov": len(ovs),
                      "llegadas": round(ll_total, 2), "proxima_llegada": prox, "saldo": round(saldo, 2),
                      "venta_mes": round(venta_mes, 2), "seguridad": round(ss, 2), "plazo_dias": plazo,
                      "cobertura_dias": round(st / (venta_mes / 30), 1) if venta_mes > 0 else None,
                      "sin_stock": sin_stock, "vuelve": vuelve, "estado": estado,
                      "compra_minima": round(max(ss - saldo, 0), 2) if estado in ("ROJO", "TEMPORAL", "AMBAR") else 0.0,
                      "kg": {x: round(v * k, 1) for x, v in (("stock", st), ("ov", ov_total), ("llegadas", ll_total),
                                                             ("saldo", saldo), ("seguridad", ss), ("venta_mes", venta_mes))},
                      "ovs": sorted(ovs, key=lambda x: (x[0] or date.max)), "oc": ll})
    filas.sort(key=lambda f: (ORDEN[f["estado"]], f["sin_stock"] or date.max, f["code"]))
    fams = defaultdict(lambda: {"n": 0, "ROJO": 0, "TEMPORAL": 0, "AMBAR": 0, "VERDE": 0, "SIN_MOVIMIENTO": 0,
                                "stock_kg": 0.0, "ov_kg": 0.0, "llegadas_kg": 0.0, "saldo_kg": 0.0, "seguridad_kg": 0.0,
                                "sin_stock": None})
    for f in filas:
        g = fams[f["familia"]]
        g["n"] += 1
        g[f["estado"]] += 1
        for k2 in ("stock", "ov", "llegadas", "saldo", "seguridad"):
            g[f"{k2}_kg"] += f["kg"][k2]
        if f["sin_stock"] and (g["sin_stock"] is None or f["sin_stock"] < g["sin_stock"]):
            g["sin_stock"] = f["sin_stock"]
    familias = []
    for nombre, g in fams.items():
        peor = min((e for e in ORDEN if g[e]), key=lambda e: ORDEN[e], default="SIN_MOVIMIENTO")
        familias.append(dict(g, familia=nombre, estado=peor,
                             **{k2: round(g[k2], 1) for k2 in ("stock_kg", "ov_kg", "llegadas_kg", "saldo_kg", "seguridad_kg")}))
    familias.sort(key=lambda g: (ORDEN[g["estado"]], g["sin_stock"] or date.max, g["familia"]))
    tot = {e: sum(1 for f in filas if f["estado"] == e) for e in ORDEN}
    return {"filas": filas, "familias": familias, "tot": tot, "ref": ref, "fuente": fuente, "meses": meses,
            "z": float(param("semaforo_z", 1.65) or 1.65)}


def rotacion(familia="", ref=None, code=""):
    """Análisis de rotación de una familia (o de un producto) en kg."""
    ref = ref or date.today()
    meses = _meses_atras(ref, 12)
    ini = date(int(meses[0][:4]), int(meses[0][5:]), 1)
    ini_ant = date(ini.year - 1, ini.month, 1)
    prods = {p.code: p for p in db().execute(select(Product)).scalars()
             if (not familia or (p.familia or "(sin familia)") == familia) and (not code or p.code == code)}
    ventas, fuente = salidas(ini_ant, ref, list(prods))
    kg = defaultdict(float)
    kg_ant = defaultdict(float)
    semanas = defaultdict(float)
    dia_sem = defaultdict(float)
    por_pres = defaultdict(float)
    por_cod = defaultdict(float)
    cli_meses = defaultdict(set)
    cli_kg = defaultdict(float)
    ult6 = set(meses[-6:])
    for f, c, cant, cli in ventas:
        k = cant * _kg_u(prods.get(c))
        m = _mes(f)
        if f >= ini:
            kg[m] += k
            lunes = f - timedelta(days=f.weekday())
            semanas[lunes] += k
            dia_sem[f.weekday()] += k
            if m in ult6:
                p = prods.get(c)
                por_pres[f"{p.tipo or '—'} · {p.presentacion or 'sin presentación'}" if p else c] += k
                por_cod[c] += k
                if cli:
                    cli_meses[cli].add(m)
                    cli_kg[cli] += k
        else:
            kg_ant[f"{f.year + 1}-{f.month:02d}"] += k
    serie = [round(kg.get(m, 0.0), 1) for m in meses]
    serie_ant = [round(kg_ant.get(m, 0.0), 1) for m in meses]
    prom = sum(serie) / len(serie)
    plazos = [_plazo(p) for p in prods.values()]
    plazo = round(sum(plazos) / len(plazos)) if plazos else int(param("semaforo_plazo_dias", 30) or 30)
    ss = stock_seguridad(serie, plazo)
    tot6 = sum(por_pres.values()) or 1
    habituales = sorted(((c, len(ms), cli_kg[c]) for c, ms in cli_meses.items() if len(ms) >= 3), key=lambda x: -x[2])
    ocasionales = sorted(((c, len(ms), cli_kg[c]) for c, ms in cli_meses.items() if len(ms) < 3), key=lambda x: -x[2])
    picos = sorted(zip(meses, serie), key=lambda x: -x[1])
    nombres_dia = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    tot_dia = sum(dia_sem.values()) or 1
    return {"familia": familia, "code": code, "fuente": fuente, "meses": meses, "serie": serie, "serie_ant": serie_ant,
            "promedio": round(prom, 1), "sigma": round(_sigma(serie), 1),
            "cv": round(_sigma(serie) / prom, 2) if prom else None, "plazo": plazo, "z": float(param("semaforo_z", 1.65) or 1.65),
            "seguridad_kg": round(ss, 1), "seguridad_dias": round(ss / (prom / 30), 1) if prom else None,
            "pico": picos[0] if picos and picos[0][1] else None, "valle": picos[-1] if picos else None,
            "semanas_pico": sorted(semanas.items(), key=lambda x: -x[1])[:5],
            "dias": [(nombres_dia[d], round(100 * dia_sem.get(d, 0) / tot_dia, 1)) for d in range(7)],
            "presentaciones": [(k, round(v, 1), round(100 * v / tot6, 1)) for k, v in sorted(por_pres.items(), key=lambda x: -x[1])],
            "codigos": [(c, prods[c].descripcion if c in prods else "", round(v, 1), round(100 * v / tot6, 1))
                        for c, v in sorted(por_cod.items(), key=lambda x: -x[1])[:15]],
            "habituales": habituales, "ocasionales": ocasionales,
            "anual": round(sum(serie), 1), "anual_ant": round(sum(serie_ant), 1),
            "familias": sorted({p.familia or "(sin familia)" for p in db().execute(select(Product)).scalars()})}
