"""V60 (19-nov-2026): motor de reposición por grano, con el método del «Excel Maestro de Abastecimiento» de la Jefatura
de Operaciones, alimentado con los datos de SAP y del módulo y recalculado cada vez que se abre.

Por grano (familia: todos los códigos GR, MP, PT y MQ del mismo grano, en kg):
1. **Demanda base** (kg/mes). Por defecto el promedio de 6 meses; el de 3 meses si difiere más del 30 % (cambio de
   tendencia). Se puede elegir otra base por grano: 3m, 6m, 12m o la proyección de Comercial.
2. **Demanda del horizonte** (lead time + periodo de revisión), cliente por cliente. Para cada cliente se toma lo
   mayor entre su OV vigente y su recompra habitual (venta habitual × factor k × horizonte / 30). Las OV con más de 60
   días no se cuentan: se confirman con Comercial.
3. **Factor MP**. Convierte la venta en granel necesario: (1 − %procesado) + %procesado / (rend. selección × rend.
   envasado).
4. **Stock de seguridad** = z(ABC) × σ mensual (con tope en la base) × √(LT/30) × factor MP.
   **Punto de pedido** = venta durante el lead time + stock de seguridad.
5. **Compra sugerida** = demanda del horizonte × factor MP + stock de seguridad − stock utilizable − en camino. En las
   importaciones se redondea a contenedores (kg por FCL).
6. **Fecha para emitir la OC**: hoy, si la posición (stock + en camino − OV) ya está bajo el punto de pedido; si no,
   cuando llegue a él con la venta base.
7. **Fechas de agotamiento**, con simulación diaria del stock y de las llegadas en su fecha, en cuatro escenarios:
   - A: solo OV vigentes;
   - B: venta histórica;
   - C: proyección de Comercial;
   - D: OV + recompra (el plan).

   **Compra puente** (importado): lo que se vende entre el agotamiento D y la llegada de una OC emitida hoy.
8. **Clasificación**: compra o importación inmediata, prioritaria o programada, requiere validación (clase C) o no
   comprar (baja rotación).
9. **Destino** de la compra: granel / MP seleccionada / PT, según la mezcla de venta del grano.

Fuentes: guías de SAP (salidas reales por cliente y código), OV de SAP (pendientes), stock por lote del módulo (solo
almacenes utilizables), OC abiertas de SAP (en camino) y proyección de Comercial cargada en el módulo. Los supuestos
son parámetros (Compras / Abastecimiento). Es un análisis de apoyo: nada se compra solo.
"""
import math
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Product, SapMovement, SapOrderLine, SapPurchaseLine
from .core import param

NACIONAL, IMPORTADO = "NACIONAL", "IMPORTADO"
BASES = ("Prom. 3m", "Prom. 6m", "Prom. 12m", "Proyección Comercial")


def _norm(t):
    t = "".join(c for c in unicodedata.normalize("NFD", (t or "").upper()) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", t).split())


def _p(k, d):
    v = param(k, d)
    return d if v in (None, "") else v


def granos_config():
    """[{grano, origen, alias[], base, rend_seleccion, kg_fcl, lead_time}] (parámetro «abastecimiento_granos»)."""
    out = []
    for g in _p("abastecimiento_granos", []) or []:
        if isinstance(g, dict) and g.get("grano"):
            out.append(dict(g, grano=_norm(g["grano"]), origen=(g.get("origen") or NACIONAL).upper(),
                            alias=[_norm(a) for a in g.get("alias") or []]))
    return out


def grano_de(descripcion, cfg=None):
    """Grano de un artículo por su descripción: el nombre (o alias) más largo que contiene; si no, «OTROS»."""
    cfg = cfg if cfg is not None else granos_config()
    d = _norm((descripcion or "").split("*")[0]) or _norm(descripcion)
    mejor, largo = "OTROS", 0
    for g in cfg:
        for nombre in [g["grano"]] + g["alias"]:
            if nombre and re.search(r"(^| )" + re.escape(nombre) + r"( |$)", d) and len(nombre) > largo:
                mejor, largo = g["grano"], len(nombre)
    return mejor


def canal_de(code):
    c = (code or "").upper()
    return "G" if c.startswith("GR") else "MP" if c.startswith("MP") else "PT"


class _Prod:
    """Caché de artículos: grano y kg por unidad."""

    def __init__(self):
        from .stock import product_kind
        self.cfg = granos_config()
        self.p = {}
        for p in db().execute(select(Product)).scalars():
            kg = p.peso_kg or (1.0 if (p.um or "").upper().startswith("K") or product_kind(p) in ("GR", "MP") else 0.0)
            self.p[p.code] = (grano_de(p.descripcion, self.cfg), kg, p)

    def grano(self, code):
        x = self.p.get(code)
        return x[0] if x else "OTROS"

    def kg(self, code, q):
        x = self.p.get(code)
        return (q or 0) * (x[1] if x else 0.0)


def _meses(ref, n):
    """Lista de n meses completos anteriores a ref ('AAAA-MM'), del más antiguo al más reciente."""
    y, m = ref.year, ref.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}-{m:02d}")
    return list(reversed(out))


def _clase_abc(valores):
    """ABC por valor de venta acumulado: A hasta 80 %, B hasta 95 %, C el resto."""
    tot = sum(valores.values()) or 0
    out, acum = {}, 0.0
    for k, v in sorted(valores.items(), key=lambda x: -x[1]):
        acum += v
        out[k] = "A" if tot and acum / tot <= 0.80 + 1e-9 else "B" if tot and acum / tot <= 0.95 + 1e-9 else "C"
        if tot and v / tot >= 0.80:  # un solo grano con más del 80 % también es A
            out[k] = "A"
    return out


def _sim(ref, stock, llegadas, ov_por_dia, tasa_dia, modo, horizonte):
    """Primer día en que el saldo queda bajo cero (simulación diaria). Consumo acumulado al día d:
    - modo «ov»: solo las OV;
    - modo «max»: lo mayor entre las OV acumuladas y la tasa × d (venta histórica o proyección de Comercial);
    - modo «suma»: las OV más la tasa × d (recompra esperada de los clientes)."""
    lleg = ovc = 0.0
    for d in range(horizonte + 1):
        dia = ref + timedelta(days=d)
        lleg += llegadas.get(dia, 0.0)
        ovc += ov_por_dia.get(dia, 0.0)
        cons = ovc if modo == "ov" else max(ovc, tasa_dia * (d + 1)) if modo == "max" else ovc + tasa_dia * (d + 1)
        saldo = stock + lleg - cons
        if saldo < -1e-6:
            return dia, saldo
    return None, None


def calcular(ref=None, solo=None):
    """{grano: resultado} con todo el detalle del plan. solo: un grano para el detalle (calcula igual todos los granos
    para el ABC)."""
    ref = ref or date.today()
    P = _Prod()
    cfg = {g["grano"]: g for g in P.cfg}
    m12 = _meses(ref, 12)
    m6, m3 = m12[-6:], m12[-3:]
    desde12 = date.fromisoformat(m12[0] + "-01")
    firme_dias = int(_p("abastecimiento_ov_firme_dias", 60))
    oc_max = int(_p("abastecimiento_oc_max_dias", 60))
    cambio = float(_p("abastecimiento_cambio_tendencia", 0.30))
    rend_env = float(_p("abastecimiento_rend_envasado", 0.98))
    z = {"A": float(_p("abastecimiento_z_a", 1.65)), "B": float(_p("abastecimiento_z_b", 1.28)),
         "C": float(_p("abastecimiento_z_c", 1.04))}
    sim_dias = int(_p("abastecimiento_dias_simulacion", 120))

    # 1) ventas (guías de SAP) de 12 meses por grano, mes, canal y cliente
    venta = defaultdict(lambda: defaultdict(float))            # grano -> mes -> kg
    canal = defaultdict(lambda: defaultdict(float))            # grano -> G/MP/PT -> kg (6 meses)
    valor = defaultdict(float)                                 # grano -> S/ 12 meses
    cli = defaultdict(lambda: defaultdict(lambda: {"fechas": set(), "kg": 0.0, "por_mes": defaultdict(float),
                                                   "canal": defaultdict(float)}))
    for m in db().execute(select(SapMovement).where(SapMovement.tipo == "GUIA", SapMovement.fecha >= desde12,
                                                    SapMovement.fecha < ref.replace(day=1))).scalars():
        g = P.grano(m.product_code)
        kg = P.kg(m.product_code, m.cantidad)
        mes = f"{m.fecha:%Y-%m}"
        venta[g][mes] += kg
        valor[g] += (m.total or 0)
        if mes in m6:
            canal[g][canal_de(m.product_code)] += kg
            c = cli[g][m.cliente or "SIN CLIENTE"]
            c["fechas"].add(m.fecha)
            c["kg"] += kg
            c["por_mes"][mes] += kg
            c["canal"][canal_de(m.product_code)] += kg
    # 2) OV de SAP pendientes por grano y cliente
    ov = defaultdict(list)
    for ln in db().execute(select(SapOrderLine).where(SapOrderLine.estado == "ABIERTA",
                                                      SapOrderLine.clase != "SERVICIO")).scalars():
        pend = (ln.cantidad or 0) - (ln.entregado or 0)
        if pend <= 1e-9 or ln.linea_cerrada:
            continue
        g = P.grano(ln.product_code)
        firme = ln.fecha is None or (ref - ln.fecha).days <= firme_dias
        ov[g].append({"ov": ln.docnum, "cliente": ln.cliente, "codigo": ln.product_code, "kg": P.kg(ln.product_code, pend),
                      "entrega": ln.fecha_entrega, "emision": ln.fecha, "tipo": canal_de(ln.product_code), "firme": firme})
    # 3) stock utilizable por grano (lotes del módulo en almacenes utilizables)
    from ..models import StockLot
    from .stock import lot_usable
    utiles = {str(x).strip().upper() for x in (_p("abastecimiento_almacenes_utilizables", []) or []) if str(x).strip()}
    stock = defaultdict(float)
    for lot in db().execute(select(StockLot).where(StockLot.cantidad > 0)).scalars():
        if utiles and (lot.warehouse_code or "").upper() not in utiles:
            continue
        ok, _ = lot_usable(lot)
        if ok:
            stock[P.grano(lot.product_code)] += P.kg(lot.product_code, lot.cantidad)
    # 4) en camino: saldo de OC abiertas de SAP (las de más de «oc_max» días se muestran aparte: por depurar)
    camino, llegadas, oc_viejas, oc_det = defaultdict(float), defaultdict(lambda: defaultdict(float)), defaultdict(float), defaultdict(list)
    for x in db().execute(select(SapPurchaseLine).where(SapPurchaseLine.tipo == "OC", SapPurchaseLine.estado == "ABIERTA")).scalars():
        pend = (x.cantidad or 0) - (x.recibido or 0)
        if pend <= 1e-9:
            continue
        g = P.grano(x.product_code)
        kg = P.kg(x.product_code, pend)
        if x.fecha and (ref - x.fecha).days > oc_max:
            oc_viejas[g] += kg
            continue
        camino[g] += kg
        llegadas[g][max(x.fecha_entrega or ref, ref)] += kg
        oc_det[g].append({"oc": x.docnum, "proveedor": x.proveedor, "kg": kg, "entrega": x.fecha_entrega})
    # 5) proyección de Comercial del mes en curso
    from ..models import DemandForecast
    comercial = defaultdict(float)
    for f in db().execute(select(DemandForecast).where(DemandForecast.mes == f"{ref:%Y-%m}")).scalars():
        comercial[P.grano(f.product_code)] += P.kg(f.product_code, f.cantidad)
    # 6) precio de compra (S/ por kg) de las OC de SAP del último año
    precio = defaultdict(lambda: [0.0, 0.0])
    proveedores = defaultdict(lambda: defaultdict(float))
    for x in db().execute(select(SapPurchaseLine).where(SapPurchaseLine.tipo == "OC", SapPurchaseLine.estado != "CANCELADA",
                                                        SapPurchaseLine.fecha >= ref - timedelta(days=365))).scalars():
        g = P.grano(x.product_code)
        kg = P.kg(x.product_code, x.cantidad)
        if kg > 0:
            precio[g][0] += x.total or 0
            precio[g][1] += kg
            proveedores[g][x.proveedor] += kg

    granos = set(venta) | set(ov) | set(stock) | set(camino) | set(cfg)
    granos.discard("OTROS")
    abc = _clase_abc({g: valor[g] for g in granos})
    out = {}
    for g in granos:
        c = cfg.get(g, {})
        origen = (c.get("origen") or NACIONAL).upper()
        serie = [venta[g].get(m, 0.0) for m in m12]
        p3, p6, p12 = sum(serie[-3:]) / 3, sum(serie[-6:]) / 6, sum(serie) / 12
        sigma = statistics.pstdev(serie) if len(serie) > 1 else 0.0
        recomendada = "Sin venta" if p6 <= 0 else ("Prom. 3m" if abs(p3 / p6 - 1) > cambio else "Prom. 6m")
        elegida = c.get("base") if c.get("base") in BASES else (recomendada if recomendada != "Sin venta" else "Prom. 6m")
        base = {"Prom. 3m": p3, "Prom. 6m": p6, "Prom. 12m": p12, "Proyección Comercial": comercial[g]}.get(elegida, p6)
        tot_canal = sum(canal[g].values())
        procesado = (canal[g]["MP"] + canal[g]["PT"]) / tot_canal if tot_canal else 0.0
        rsel = float(c.get("rend_seleccion") or _p("abastecimiento_rend_seleccion", 0.95))
        fmp = (1 - procesado) + procesado / (rsel * rend_env) if rsel else 1.0
        harina = g in ("HARINAS", "MAICENA")
        lt = int(c.get("lead_time") or (_p("abastecimiento_lt_importacion", 50) if origen == IMPORTADO else
                                         _p("abastecimiento_lt_harinas", 10) if harina else _p("abastecimiento_lt_nacional", 7)))
        rev = int(_p("abastecimiento_revision_importacion", 30) if origen == IMPORTADO else _p("abastecimiento_revision_nacional", 15))
        clase = abc.get(g, "C")
        cv = sigma / p12 if p12 else None
        xyz = "" if cv is None else ("X" if cv <= 0.5 else "Y" if cv <= 1.0 else "Z")
        ss = z[clase] * min(sigma, base) * math.sqrt(lt / 30) * fmp
        rop = base * fmp * lt / 30 + ss
        k = base / p6 if p6 else 1.0
        horizonte = lt + rev
        # demanda del horizonte cliente por cliente
        ov_firmes = [x for x in ov[g] if x["firme"]]
        ov_cli = defaultdict(float)
        for x in ov_firmes:
            ov_cli[x["cliente"]] += x["kg"]
        comp = []
        for nombre in set(cli[g]) | set(ov_cli):
            cc = cli[g].get(nombre)
            n = len(cc["fechas"]) if cc else 0
            habitual = (cc["kg"] / 6) if cc else 0.0
            cada = (180 / n) if n else None
            ultima = max(cc["fechas"]) if cc and cc["fechas"] else None
            sin = (ref - ultima).days if ultima else None
            if n <= 2:
                estado = "Ocasional"
            elif sin is not None and sin > max(3 * (cada or 0), 120):
                estado = "Inactivo"
            elif sin is not None and cada and sin > cada:
                estado = "Atrasado"
            else:
                estado = "Activo"
            esperado = 0.0 if estado == "Inactivo" else habitual * k * horizonte / 30
            en_ov = ov_cli.get(nombre, 0.0)
            total = max(en_ov, esperado)
            comp.append({"cliente": nombre, "estado": estado, "compras": n, "cada": round(cada) if cada else None,
                         "kg_compra": (cc["kg"] / n) if n else None, "ultima": ultima, "en_ov": en_ov,
                         "recompra": max(total - en_ov, 0.0), "total": total,
                         "canal": max(cc["canal"], key=cc["canal"].get) if cc and cc["canal"] else ""})
        comp.sort(key=lambda x: -x["total"])
        dem_h = sum(x["total"] for x in comp)
        maximo = dem_h * fmp + ss
        st = stock[g]
        ov_total = sum(x["kg"] for x in ov_firmes)
        posicion = st + camino[g] - ov_total
        uso_dia = base * fmp / 30
        cobertura = posicion / uso_dia if uso_dia > 0 else None
        compra = max(0.0, maximo - st - camino[g])
        kg_fcl = float(c.get("kg_fcl") or _p("abastecimiento_kg_fcl", 24000))
        fcl = math.ceil(compra / kg_fcl) if origen == IMPORTADO and compra > 0 and kg_fcl else 0
        a_pedir = fcl * kg_fcl if fcl else (math.ceil(compra / 1000) * 1000 if compra > 0 else 0.0)
        if base <= 0:
            emitir = None
        elif posicion <= rop:
            emitir = ref
        else:
            emitir = ref + timedelta(days=round((posicion - rop) / uso_dia))
        # simulación de agotamiento (cuatro escenarios)
        ov_dia = defaultdict(float)
        for x in ov_firmes:
            ov_dia[max(x["entrega"] or ref, ref)] += x["kg"]
        lleg = llegadas[g]
        dias = sim_dias
        agota_a, _ = _sim(ref, st, lleg, ov_dia, 0.0, "ov", dias)
        agota_b, _ = _sim(ref, st, lleg, ov_dia, p6 * fmp / 30, "max", dias)
        agota_c, _ = _sim(ref, st, lleg, ov_dia, comercial[g] * fmp / 30, "max", dias) if comercial[g] else (None, None)
        recompra = sum(x["recompra"] for x in comp)
        agota_d, _ = _sim(ref, st, lleg, ov_dia, recompra * fmp / max(horizonte, 1), "suma", dias)
        puente = 0.0
        llegada_oc_hoy = ref + timedelta(days=lt)
        if origen == IMPORTADO and agota_d and agota_d < llegada_oc_hoy:
            puente = (recompra * fmp / max(horizonte, 1)) * (llegada_oc_hoy - agota_d).days
        if compra <= 0:
            clasif = "NO COMPRAR" + (" - baja rotación" if cobertura is not None and cobertura > 180 else "")
        elif clase == "C":
            clasif = "REQUIERE VALIDACIÓN"
        elif origen == IMPORTADO:
            clasif = "IMPORTACIÓN INMEDIATA" if emitir and emitir <= ref else "PROGRAMAR IMPORTACIÓN"
        else:
            clasif = ("COMPRA INMEDIATA" if cobertura is not None and cobertura <= lt else "COMPRA PRIORITARIA") \
                if emitir and emitir <= ref else "PROGRAMAR COMPRA"
        pr = precio[g][0] / precio[g][1] if precio[g][1] else None
        tot_dest = canal[g]["G"] + canal[g]["MP"] / rsel + canal[g]["PT"] / (rsel * rend_env) if tot_canal else 0
        destino = {k2: (compra * v / tot_dest if tot_dest else 0.0) for k2, v in
                   (("granel", canal[g]["G"]), ("mp", canal[g]["MP"] / rsel if rsel else 0),
                    ("pt", canal[g]["PT"] / (rsel * rend_env) if rsel else 0))}
        out[g] = {
            "grano": g, "origen": origen, "responsable": "Coordinador de Importación" if origen == IMPORTADO else "Coordinador de Compras",
            "abc": clase, "xyz": xyz, "cv": cv, "serie": list(zip(m12, serie)), "p3": p3, "p6": p6, "p12": p12,
            "comercial": comercial[g], "recomendada": recomendada, "base_elegida": elegida, "base": base, "sigma": sigma,
            "procesado": procesado, "rend_seleccion": rsel, "factor_mp": fmp, "lead_time": lt, "revision": rev,
            "horizonte": horizonte, "z": z[clase], "ss": ss, "ss_dias": ss / uso_dia if uso_dia else None, "rop": rop,
            "k": k, "demanda_horizonte": dem_h, "maximo": maximo, "stock": st, "camino": camino[g],
            "oc_por_depurar": oc_viejas[g], "oc": sorted(oc_det[g], key=lambda x: x["entrega"] or date.max),
            "ov_total": ov_total, "ov_a_confirmar": sum(x["kg"] for x in ov[g] if not x["firme"]),
            "ov": sorted(ov[g], key=lambda x: -x["kg"]), "posicion": posicion, "cobertura": cobertura, "compra": compra,
            "kg_fcl": kg_fcl, "fcl": fcl, "a_pedir": a_pedir, "precio": pr, "presupuesto": a_pedir * pr if pr else None,
            "emitir": emitir, "agota": {"A": agota_a, "B": agota_b, "C": agota_c, "D": agota_d}, "puente": puente,
            "clasificacion": clasif, "clientes": comp, "recompra": recompra,
            "canal": {k2: canal[g][k2] for k2 in ("G", "MP", "PT")}, "destino": destino,
            "proveedores": [n for n, _ in sorted(proveedores[g].items(), key=lambda x: -x[1])[:3] if n],
            "llegadas": sorted(((d, q) for d, q in lleg.items()), key=lambda x: x[0]),
        }
    return out


ORDEN_CLASE = {"IMPORTACIÓN INMEDIATA": 0, "COMPRA INMEDIATA": 0, "COMPRA PRIORITARIA": 1, "PROGRAMAR IMPORTACIÓN": 2,
               "PROGRAMAR COMPRA": 2, "REQUIERE VALIDACIÓN": 3}


def tablero(ref=None, origen="", q=""):
    filas = list(calcular(ref).values())
    if origen:
        filas = [f for f in filas if f["origen"] == origen]
    if q:
        qq = _norm(q)
        filas = [f for f in filas if qq in f["grano"]]
    filas.sort(key=lambda f: (ORDEN_CLASE.get(f["clasificacion"], 9), f["emitir"] or date.max, -f["compra"]))
    return filas
