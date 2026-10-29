"""Análisis de la proyección de demanda (V12, 29-oct-2026).

Comercial carga la proyección por producto (y canal, marca y presentación del producto). El sistema la contrasta con:
- el stock disponible en todos los almacenes: producto terminado, materia prima, externos y almacenes de producción
  (sin la merma, que no sirve para el cálculo, ni los lotes no disponibles);
- las importaciones que llegan en el mes y las compras nacionales ya programadas;
- la producción ya solicitada o en curso.

Y entrega tres vistas, cada una para quien la necesita:
1. Presolicitudes de compra (Compras, Gerencia de Operaciones y Gerencia General): materia prima que falta, con la
   fecha máxima para pedirla según el tiempo de reposición de su categoría. No se muestra a Producción.
2. Llegadas del mes (Almacén, Logística y Gerencia de Operaciones): importaciones y compras con su fecha estimada.
3. Preprogramación de producción (Producción y Gerencia de Operaciones): lo que hay que producir para cubrir la
   demanda manteniendo un stock de reserva, repartido por línea según su capacidad real (kg/día de la tabla de
   capacidades) en los días hábiles del mes. Si la demanda supera la capacidad, se indica cuánto falta.

Fórmulas (parámetros entre comillas):
- reserva = demanda del mes × «stock_reserva_dias» / 30
- a producir (PT) = máx(demanda + reserva − stock − producción en curso, 0)
- MP requerida = a producir × cantidad del componente / cantidad base de la lista de materiales (sin desmedro)
  + demanda directa de MP/granel
- MP faltante = máx(MP requerida + reserva − stock − importaciones del mes − compras programadas, 0)
- fecha máxima para pedir = fecha de necesidad − días máximos de reposición de la categoría
"""
import calendar as cal
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from ..db import db
from ..models import (BOMLine, DemandForecast, ImportShipment, Product, ProductionReport, ProductionRequest,
                      PurchaseRequest, StockLot, Warehouse)
from .core import BusinessError, audit, has_perm, param

COMPRAS_CERRADAS = ("RECIBIDA", "RECIBIDA_CON_DIFERENCIAS", "RECIBIDA_BAJO_OBSERVACION", "CERRADA", "RECHAZADA",
                    "CANCELADA", "ANULADA")
PROD_ABIERTAS = ("BORRADOR", "ENVIADA", "VALIDADA", "PROGRAMADA", "EN_PROCESO")


def _rango(mes):
    y, m = int(mes[:4]), int(mes[5:7])
    ini = date(y, m, 1)
    return ini, date(y, m, cal.monthrange(y, m)[1])


def _kg(p, q):
    if p is None:
        return 0.0
    return q if (p.um or "").upper().startswith("K") else q * (p.peso_kg or 0)


def roles_presolicitud():
    return set(param("demanda_presolicitud_roles", ["COMPRAS", "GERENCIA_OPERACIONES", "GERENCIA_GENERAL"]) or [])


def can_see(user, vista):
    """Qué parte del análisis ve cada perfil (V12)."""
    from .indicators import areas_of
    areas = areas_of(user)
    if vista == "compras":
        return user.role_code in roles_presolicitud()
    if vista == "llegadas":
        return bool(areas & {"Almacén", "Logística"}) or user.role_code in ("GERENCIA_OPERACIONES", "GERENCIA_GENERAL")
    if vista == "produccion":
        return "Producción" in areas or user.role_code in ("GERENCIA_OPERACIONES", "GERENCIA_GENERAL")
    return False


def _stock():
    """Stock libre por producto y por uso del almacén, sin merma ni lotes no disponibles."""
    from .production import is_desmedro
    from .stock import free_qty
    usos = {w.code: w.uso for w in db().execute(select(Warehouse)).scalars()}
    out = defaultdict(lambda: defaultdict(float))
    for lot in db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado == "DISPONIBLE")).scalars():
        p = lot.product
        if is_desmedro(lot.product_code, p.descripcion if p else ""):
            continue
        out[lot.product_code][usos.get(lot.warehouse_code, "OTRO")] += free_qty(lot)
    return out


def _linea_habitual():
    """Línea donde se produjo cada producto con más frecuencia (partes de los últimos 180 días)."""
    c = defaultdict(Counter)
    for r in db().execute(select(ProductionReport).where(ProductionReport.fecha >= date.today() - timedelta(days=180))).scalars():
        c[r.product_code][r.linea] += 1
    return {k: v.most_common(1)[0][0] for k, v in c.items()}


def _cap_linea():
    out = {}
    for g in param("capacidad_lineas", []) or []:
        ls = g.get("lineas") or []
        for l in ls:
            if g.get("kg_dia"):
                out[l] = float(g["kg_dia"]) / len(ls)
    return out


def _bom():
    from .production import active_bom, is_desmedro
    v = active_bom()
    if v is None:
        return {}
    out = defaultdict(list)
    for b in db().execute(select(BOMLine).where(BOMLine.version_id == v.id)).scalars():
        if is_desmedro(b.componente, b.componente_desc):
            continue
        out[b.padre].append((b.componente, (b.cantidad or 0) / (b.cantidad_bom or 1)))
    return out


def analyze(mes=None, hoy=None):
    from .stock import product_kind
    hoy = hoy or date.today()
    mes = mes or f"{hoy:%Y-%m}"
    ini, fin = _rango(mes)
    necesidad = max(ini, hoy)
    dias_res = float(param("stock_reserva_dias", 7) or 0)
    marcas_propias = {m.strip().upper() for m in (param("marcas_propias", []) or []) if m.strip()}
    # demanda del mes
    dem = defaultdict(lambda: {"cantidad": 0.0, "canales": set()})
    for f in db().execute(select(DemandForecast).where(DemandForecast.mes == mes)).scalars():
        dem[f.product_code]["cantidad"] += f.cantidad
        if f.canal:
            dem[f.product_code]["canales"].add(f.canal)
    stock = _stock()
    # producción ya solicitada o en curso
    en_curso = defaultdict(float)
    for r in db().execute(select(ProductionRequest).where(ProductionRequest.estado.in_(PROD_ABIERTAS))).scalars():
        en_curso[r.product_code] += r.cantidad
    # llegadas del mes: importaciones y compras programadas
    llegadas = []
    entrante = defaultdict(float)
    for i in db().execute(select(ImportShipment).where(ImportShipment.estado == "EN_CURSO")).scalars():
        if i.fecha_llegada_estimada and i.fecha_llegada_estimada <= fin:
            q = i.cantidad - (i.cantidad_recibida or 0)
            entrante[i.product_code] += q
            llegadas.append({"tipo": "Importación", "ref": i.referencia, "producto": i.product_code, "cantidad": q,
                             "fecha": i.fecha_llegada_estimada, "almacen": i.warehouse_code or "", "proveedor": i.proveedor})
    for c in db().execute(select(PurchaseRequest).where(PurchaseRequest.estado.notin_(COMPRAS_CERRADAS))).scalars():
        f = c.fecha_prevista or c.fecha_necesidad
        if c.numero_oc or c.estado == "ORDEN_GENERADA":  # compra ya programada (con orden de compra)
            if f and f <= fin:
                q = c.cantidad - (c.cantidad_recibida or 0)
                entrante[c.product_code] += q
                llegadas.append({"tipo": "Compra nacional", "ref": c.numero_oc or f"#{c.id}", "producto": c.product_code,
                                 "cantidad": q, "fecha": f, "almacen": c.warehouse_code or "", "proveedor": c.proveedor})
    llegadas.sort(key=lambda x: x["fecha"])
    bom = _bom()
    filas, prod_req, mp_req = [], defaultdict(float), defaultdict(float)
    for code, x in sorted(dem.items()):
        p = db().get(Product, code)
        tipo = product_kind(p)
        st = stock.get(code, {})
        st_total = sum(st.values())
        reserva = x["cantidad"] * dias_res / 30
        marca = (p.marca if p else "") or ""
        segmento = ("Granel" if tipo == "GR" else "Materia prima" if tipo == "MP" else
                    ("Marca blanca" if marcas_propias and marca and marca.upper() not in marcas_propias else "Producto terminado"))
        fila = {"code": code, "descripcion": p.descripcion if p else "", "tipo": tipo, "segmento": segmento, "marca": marca,
                "presentacion": (p.presentacion if p else "") or "", "canales": sorted(x["canales"]),
                "demanda": round(x["cantidad"], 2), "reserva": round(reserva, 2), "stock": {k: round(v, 2) for k, v in st.items()},
                "stock_total": round(st_total, 2), "en_curso": round(en_curso.get(code, 0), 2),
                "entrante": round(entrante.get(code, 0), 2)}
        if tipo == "PT" or code in bom:
            fila["a_producir"] = round(max(x["cantidad"] + reserva - st_total - en_curso.get(code, 0), 0), 2)
            prod_req[code] += fila["a_producir"]
            for comp, ratio in bom.get(code, []):
                mp_req[comp] += fila["a_producir"] * ratio
        else:
            fila["a_producir"] = 0.0
            mp_req[code] += x["cantidad"] + reserva  # se vende directo (granel / MP)
        fila["cobertura"] = round(100 * min(st_total + en_curso.get(code, 0) + entrante.get(code, 0), x["cantidad"])
                                  / x["cantidad"], 1) if x["cantidad"] else None
        filas.append(fila)
    # presolicitudes de compra de MP
    from .purchasing import lead_time_for
    presol = []
    for code, req in sorted(mp_req.items()):
        p = db().get(Product, code)
        disp = sum(stock.get(code, {}).values()) + entrante.get(code, 0)
        falta = round(max(req - disp, 0), 2)
        if falta <= 0:
            continue
        lt, _ = lead_time_for(p) if p else (None, None)
        dias = lt.dias_max if lt else None
        fmax = necesidad - timedelta(days=dias) if dias is not None else None
        presol.append({"code": code, "descripcion": p.descripcion if p else "", "requerido": round(req, 2),
                       "disponible": round(disp, 2), "faltante": falta, "fecha_necesidad": necesidad, "lead_dias": dias,
                       "fecha_maxima": fmax, "vencida": fmax is not None and fmax < hoy,
                       "categoria": (p.categoria_reposicion if p else "") or "",
                       "sin_plazo": dias is None})
    presol.sort(key=lambda x: (x["fecha_maxima"] or date.max))
    # preprogramación de producción por capacidad real de cada línea
    from .calendar import day_factor, holidays
    fer = holidays()
    dias_mes = [necesidad + timedelta(days=i) for i in range((fin - necesidad).days + 1)]
    habiles = [(d, day_factor(d, fer)) for d in dias_mes if day_factor(d, fer) > 0]
    cap = _cap_linea()
    habitual = _linea_habitual()
    envasado = [l for l in ("R1", "R2", "R3", "ENV_MANUAL") if cap.get(l)]
    uso_linea = defaultdict(float)  # días de línea ya asignados
    programa, deficit = [], []
    for code, q in sorted(prod_req.items(), key=lambda kv: -kv[1]):
        if q <= 0:
            continue
        p = db().get(Product, code)
        kg = _kg(p, q)
        linea = habitual.get(code) if cap.get(habitual.get(code, "")) else None
        if linea is None and envasado:
            linea = min(envasado, key=lambda l: uso_linea[l] / (len(habiles) or 1))  # la menos cargada
        if linea is None:
            deficit.append({"code": code, "kg": round(kg, 1), "motivo": "sin línea con capacidad registrada"})
            continue
        dias_nec = kg / cap[linea] if cap[linea] else None
        disponibles = sum(f for _, f in habiles) - uso_linea[linea]
        asignado_dias = min(dias_nec, max(disponibles, 0)) if dias_nec else 0
        inicio_idx = uso_linea[linea]
        uso_linea[linea] += asignado_dias
        fecha_ini = _fecha_en(habiles, inicio_idx)
        fecha_fin = _fecha_en(habiles, inicio_idx + asignado_dias - 1e-6) if asignado_dias else None
        kg_ok = round(asignado_dias * cap[linea], 1)
        fila = {"code": code, "descripcion": p.descripcion if p else "", "cantidad": round(q, 2), "kg": round(kg, 1),
                "linea": linea, "linea_fuente": "habitual" if habitual.get(code) == linea else "menos cargada",
                "dias": round(dias_nec, 1) if dias_nec else None, "inicio": fecha_ini, "fin": fecha_fin,
                "kg_programable": kg_ok, "kg_sin_capacidad": round(max(kg - kg_ok, 0), 1)}
        programa.append(fila)
        if fila["kg_sin_capacidad"] > 0:
            deficit.append({"code": code, "kg": fila["kg_sin_capacidad"], "motivo": f"capacidad de {linea} agotada en el mes"})
    uso = [{"linea": l, "dias_asignados": round(v, 1), "dias_habiles": round(sum(f for _, f in habiles), 1),
            "uso_pct": round(100 * v / sum(f for _, f in habiles), 1) if habiles else None} for l, v in sorted(uso_linea.items())]
    return {"mes": mes, "inicio": ini, "fin": fin, "necesidad": necesidad, "filas": filas, "presolicitudes": presol,
            "llegadas": llegadas, "programa": programa, "deficit": deficit, "uso_lineas": uso,
            "reserva_dias": dias_res, "kg_deficit": round(sum(x["kg"] for x in deficit), 1),
            "segmentos": dict(Counter(f["segmento"] for f in filas))}


def _fecha_en(habiles, idx):
    """Fecha del día hábil número idx (acumulando jornadas parciales)."""
    acc = 0.0
    for d, f in habiles:
        acc += f
        if acc > idx:
            return d
    return habiles[-1][0] if habiles else None


def to_plan(user, mes):
    """Pasa la preprogramación al planeamiento (entradas «SISTEMA» por día y línea que el Jefe revisa y edita)."""
    from ..models import ProductionPlan
    if not (has_perm(user, "produccion.programar") or has_perm(user, "produccion.liquidar")):
        raise BusinessError("El planeamiento lo actualiza Producción.")
    d = analyze(mes)
    nuevas = []
    for x in d["programa"]:
        if not x["inicio"] or not x["kg_programable"]:
            continue
        q = round(x["cantidad"] * (x["kg_programable"] / x["kg"]), 4) if x["kg"] else x["cantidad"]
        pl = ProductionPlan(periodo="DIA", fecha=x["inicio"], product_code=x["code"], cantidad=q, line_code=x["linea"],
                            comentario=f"Preprogramado desde la proyección de demanda {mes} (con stock de reserva de "
                                       f"{d['reserva_dias']:g} días); fin estimado {x['fin']:%d/%m}." if x["fin"] else "",
                            origen="SISTEMA", user_id=user.id)
        db().add(pl)
        nuevas.append(pl)
    db().flush()
    audit(user, "PLAN_DESDE_PROYECCION", "ProductionPlan", ",".join(str(p.id) for p in nuevas), {"mes": mes})
    return nuevas


def create_presolicitud(user, mes, code):
    """Compras genera la presolicitud de compra de una MP faltante (queda en borrador con su análisis)."""
    if user.role_code not in roles_presolicitud() and not has_perm(user, "compras.gestionar"):
        raise BusinessError("Genera la presolicitud Compras.")
    d = analyze(mes)
    x = next((p for p in d["presolicitudes"] if p["code"] == code), None)
    if x is None:
        raise BusinessError("Ese producto ya no tiene faltante en la proyección.")
    r = PurchaseRequest(product_code=code, cantidad=x["faltante"], fecha_necesidad=x["fecha_necesidad"],
                        origen="REPOSICION", estado="BORRADOR",
                        analisis={"fuente": f"Proyección de demanda {mes}", "requerido": x["requerido"],
                                  "disponible": x["disponible"], "fecha_maxima": x["fecha_maxima"].isoformat() if x["fecha_maxima"] else None,
                                  "lead_dias": x["lead_dias"]})
    db().add(r)
    db().flush()
    audit(user, "PRESOLICITUD_PROYECCION", "PurchaseRequest", r.id, {"mes": mes, "producto": code})
    return r


def check_purchase_deadlines(hoy=None):
    """Aviso a Compras, Gerencia de Operaciones y Gerencia General cuando se acerca (o pasó) la fecha máxima para pedir
    una MP faltante de la proyección (una vez por producto y mes)."""
    from . import alerts
    hoy = hoy or date.today()
    aviso = int(param("demanda_aviso_compra_dias", 7) or 7)
    n = 0
    for mes in (f"{hoy:%Y-%m}", f"{(hoy.replace(day=1) + timedelta(days=32)):%Y-%m}"):
        for x in analyze(mes, hoy)["presolicitudes"]:
            if x["fecha_maxima"] and x["fecha_maxima"] <= hoy + timedelta(days=aviso):
                alerts.emit("PROYECCION_COMPRA", f"Pedir {x['code']} antes del {x['fecha_maxima']:%d/%m/%Y}" +
                            (" (fecha vencida)" if x["vencida"] else ""),
                            f"Proyección {mes}: faltan {x['faltante']:,.2f} de {x['descripcion']}. Reposición "
                            f"{x['lead_dias']} días; se necesita desde el {x['fecha_necesidad']:%d/%m/%Y}.",
                            "Product", x["code"], prioridad="ALTA" if x["vencida"] else "MEDIA",
                            dedup_key=f"PROY_COMPRA:{mes}:{x['code']}")
                n += 1
    return n
