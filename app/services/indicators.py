"""Matriz de pertinencia de indicadores por área y perfil (rediseño de informes, 28-oct-2026).

Cada indicador tiene un área propietaria, las áreas que lo ven en su vista predeterminada (OBLIGATORIO), las que pueden
agregarlo a un informe personalizado (DISPONIBLE) y el motivo funcional. Para cualquier otra área es NO_VISIBLE.

- Es la única fuente de control: el inicio, los informes predeterminados, el informe personalizado (columnas, gráficos,
  exportaciones PDF/Excel) y las plantillas guardadas la consultan. Un indicador NO_VISIBLE no aparece en ninguna de ellas.
- Exclusiones de la empresa: el parámetro «indicadores_ocultos» ({área o código de rol: [códigos]}) retira indicadores de
  un área o perfil y prevalece sobre la matriz. Ocultar no borra el dato ni lo quita a las demás áreas.
- Visibilidad no es seguridad: los datos con restricción (montos, costos, finanzas) además exigen su permiso
  (`requiere`); si el usuario no lo tiene, el indicador es NO_VISIBLE aunque su área lo tenga en la matriz.
- La asignación de áreas se basa en las responsabilidades documentadas de cada perfil (catálogo de roles) y es
  PROPUESTA: la empresa la ajusta con «indicadores_ocultos» sin cambiar el código.
"""
from .core import param, roles_of

OBLIGATORIO, DISPONIBLE, NO_VISIBLE = "OBLIGATORIO", "DISPONIBLE", "NO_VISIBLE"
TODAS = ("Gerencia", "Sistemas")  # Gerencia ve el conjunto; Sistemas da soporte a todas las áreas

# código: (nombre, área propietaria, bloque, áreas OBLIGATORIO, áreas DISPONIBLE, permiso requerido (alguno), motivo)
INDICADORES = {
    # --- pedidos (situación de las OV) ---
    "PED_PENDIENTES": ("Pedidos pendientes y su cobertura de stock", "Comercial", "Pedidos",
                       ("Comercial", "Almacén", "Logística", "Distribución"), ("Finanzas", "Facturación"), (),
                       "Saber cuántas OV faltan atender y cuántas tienen stock completo para planificar la atención."),
    "PED_COBERTURA": ("Cobertura promedio de stock de los pedidos", "Logística", "Pedidos",
                      ("Comercial", "Almacén", "Logística"), (), (),
                      "Detectar pedidos sin stock suficiente para reponer, trasladar o renegociar la fecha."),
    "OTIF_SALIDA": ("OTIF a la salida (completo y a tiempo)", "Logística", "Pedidos",
                    ("Comercial", "Almacén", "Logística", "Distribución"), ("Calidad",), (),
                    "Medir el nivel de servicio comprometido con el cliente (decisión Q2)."),
    "FILL_RATE": ("Fill rate a la salida (unidades, líneas y pedidos al 100 %)", "Logística", "Pedidos",
                  ("Comercial", "Almacén", "Logística", "Distribución"), (), (),
                  "Medir cuánto de lo pedido salió; base para corregir faltantes en preparación."),
    "VOLUMEN_OV_KG": ("Volumen de OV en kg (total y pendiente)", "Comercial", "Pedidos",
                      ("Comercial", "Logística"), ("Almacén", "Distribución"), (),
                      "Dimensionar la carga de preparación y transporte del periodo."),
    "RECHAZOS": ("Rechazos, devoluciones y entregas parciales", "Distribución", "Pedidos",
                 ("Comercial", "Distribución", "Logística", "Calidad"), ("Almacén",), (),
                 "Gestionar la causa con el cliente (Comercial), en ruta (Distribución) o del producto (Calidad)."),
    "MONTO_OV": ("Monto de OV en S/ (total y pendiente)", "Comercial", "Comercial",
                 ("Comercial",), ("Finanzas", "Facturación"), ("dashboard.precios", "finanzas.ver"),
                 "Seguimiento de la venta; Finanzas lo usa para créditos y cobranza."),
    "PRECIO_BAJO_MINIMO": ("OV con precio en el límite o bajo el mínimo de lista", "Comercial", "Comercial",
                           ("Comercial",), (), ("dashboard.precios",),
                           "Comercial confirma o corrige precios fuera de política."),
    # --- operación (almacén, despacho, abastecimiento) ---
    "T_PREPARACION": ("Tiempo promedio de preparación", "Almacén", "Operación", ("Almacén", "Logística"),
                      ("Distribución",), (), "Controlar la productividad del picking."),
    "T_DESPACHO": ("Tiempo de preparado a salida", "Distribución", "Operación", ("Almacén", "Distribución", "Logística"),
                   (), (), "Detectar demoras entre el fin de la preparación y la salida del camión."),
    "COMPRAS_PENDIENTES": ("Compras pendientes", "Compras", "Operación", ("Compras", "Importaciones", "Logística"),
                           ("Almacén",), (), "Seguir las solicitudes de compra abiertas."),
    "PRODUCCION_PENDIENTE": ("Solicitudes de producción pendientes", "Producción", "Operación",
                             ("Producción", "Logística"), ("Almacén",), (),
                             "Producción programa y atiende las solicitudes abiertas."),
    "DIF_INVENTARIO": ("Diferencias de inventario en conteos", "Almacén", "Operación", ("Almacén", "Logística"), (), (),
                       "Almacén corrige y concilia con SAP."),
    "DIF_RECEPCION_PT": ("Diferencias en la recepción de producto terminado", "Almacén", "Operación",
                         ("Almacén", "Producción", "Logística"), (), (),
                         "Producción y Almacén aclaran lo liquidado frente a lo recibido."),
    # --- seguimiento ---
    "PED_DETENIDOS": ("Pedidos detenidos y motivo", "Comercial", "Seguimiento",
                      ("Comercial", "Almacén", "Logística"), ("Finanzas", "Distribución"), (),
                      "Liberar los pedidos detenidos (precio, crédito, stock, orden de compra)."),
    "PED_ESTADOS": ("Pedidos por estado", "Comercial", "Seguimiento", ("Comercial", "Logística"),
                    ("Almacén", "Distribución"), (), "Vista de la cartera de pedidos por etapa."),
    "FALTANTES": ("Faltantes por producto (unidades no reservadas)", "Logística", "Seguimiento",
                  ("Almacén", "Logística", "Producción", "Compras"), ("Comercial",), (),
                  "Dato operativo para decidir qué producir, comprar o trasladar."),
    "FILL_DETALLE": ("Fill rate por pedido despachado", "Logística", "Seguimiento", ("Logística", "Distribución"),
                     ("Comercial", "Almacén"), (), "Revisar pedido por pedido lo que salió incompleto o tarde."),
    "CAUSAS_ERROR": ("Dónde están los mayores errores (por etapa)", "Logística", "Seguimiento",
                     ("Logística", "Almacén", "Distribución", "Calidad"), ("Comercial",), (),
                     "Atacar la etapa que más falla."),
    "INCIDENCIAS": ("Incidencias por tipo", "Distribución", "Seguimiento", ("Distribución", "Calidad", "Logística"),
                    ("Almacén", "Comercial"), (), "Gestionar las incidencias abiertas de su ámbito."),
    # --- producción ---
    "PROD_CUMPLIMIENTO": ("Cumplimiento del programa de producción", "Producción", "Producción",
                          ("Producción",), ("Logística",), (), "Producción mide si ejecutó lo planificado."),
    "PROD_PRODUCIDO": ("Producido frente al plan (kg y unidades)", "Producción", "Producción", ("Producción",),
                       ("Logística", "Almacén"), (), "Volumen ejecutado y su brecha con el plan."),
    "PROD_RENDIMIENTO": ("Rendimiento y desmedro por línea", "Producción", "Producción", ("Producción",),
                         ("Calidad",), (), "Controlar mermas y calibración por línea."),
    "PROD_MERMA_FUERA": ("Mermas fuera de lo proyectado", "Producción", "Producción", ("Producción",), ("Calidad",), (),
                         "Investigar las liquidaciones con merma fuera de tolerancia."),
    "PROD_CAPACIDAD": ("Uso de capacidad por línea", "Producción", "Producción", ("Producción",), ("Logística",), (),
                       "Detectar líneas sub- o sobreutilizadas."),
    "PROD_PARADAS": ("Paradas de línea y demoras de atención", "Producción", "Producción", ("Producción",), (), (),
                     "Reducir paradas y solicitudes atendidas tarde."),
    "PROD_OEE": ("OEE (disponibilidad, rendimiento y calidad)", "Producción", "Producción", ("Producción",), (), (),
                 "Eficiencia global de los equipos."),
    # --- columnas sensibles del informe personalizado ---
    "MONTOS_VENTA": ("Montos de venta (precio, importe, total, proyección, gasto)", "Comercial", "Datos",
                     ("Comercial",), ("Finanzas", "Facturación"), ("dashboard.precios", "finanzas.ver"),
                     "Información comercial; no corresponde a áreas operativas."),
    "COSTO_COMPRA": ("Precio de compra", "Compras", "Datos", ("Compras", "Importaciones"), ("Logística", "Finanzas"), (),
                     "Gestión de compras y costos de abastecimiento."),
    "COSTO_TRANSPORTE": ("Costo de transporte", "Distribución", "Datos", ("Distribución", "Logística"), ("Finanzas",), (),
                         "Control del costo de la flota y de los transportistas."),
}

# columnas del informe personalizado ligadas a un indicador sensible
COLUMNAS = {("ov", "monto"): "MONTOS_VENTA", ("ov_lineas", "precio"): "MONTOS_VENTA",
            ("ov_lineas", "importe"): "MONTOS_VENTA", ("cotizaciones", "total"): "MONTOS_VENTA",
            ("oportunidades", "proyeccion"): "MONTOS_VENTA", ("acciones", "gasto"): "MONTOS_VENTA",
            ("compras", "precio"): "COSTO_COMPRA", ("rutas", "costo"): "COSTO_TRANSPORTE"}


def areas_of(user):
    from ..db import db
    from ..models import Role
    return {r.area for r in (db().get(Role, c) for c in roles_of(user)) if r is not None}


def _ocultos(user):
    cfg = param("indicadores_ocultos", {}) or {}
    claves = areas_of(user) | roles_of(user)
    return {c for k, v in cfg.items() if k in claves for c in (v or [])}


def level(user, code):
    """OBLIGATORIO, DISPONIBLE o NO_VISIBLE para el usuario."""
    from .core import has_perm
    ind = INDICADORES.get(code)
    if ind is None or user is None:
        return NO_VISIBLE
    _, _, _, obl, disp, requiere, _ = ind
    if code in _ocultos(user):
        return NO_VISIBLE
    if requiere and not any(has_perm(user, p) for p in requiere):
        return NO_VISIBLE
    areas = areas_of(user)
    if areas & (set(obl) | set(TODAS)):
        return OBLIGATORIO
    if areas & set(disp):
        return DISPONIBLE
    return NO_VISIBLE


def visible(user, code):
    return level(user, code) != NO_VISIBLE


def default_set(user):
    return {c for c in INDICADORES if level(user, c) == OBLIGATORIO}


def column_allowed(user, fuente, col):
    code = COLUMNAS.get((fuente, col))
    return code is None or visible(user, code)


def matrix():
    """Filas de la matriz para la documentación y la pantalla de configuración."""
    return [{"codigo": c, "nombre": n, "propietaria": a, "bloque": b, "obligatorio": list(TODAS) + list(o),
             "disponible": list(d), "requiere": list(r), "motivo": m}
            for c, (n, a, b, o, d, r, m) in INDICADORES.items()]


def for_user(user):
    """Indicadores del usuario agrupados por bloque: [(bloque, [(código, nombre, nivel)])]."""
    out = {}
    for c, ind in INDICADORES.items():
        lv = level(user, c)
        if lv != NO_VISIBLE and ind[2] != "Datos":
            out.setdefault(ind[2], []).append((c, ind[0], lv))
    return list(out.items())


# ---------------------------------------------------------------------------------------------------------------- valores
def production_summary(desde=None, hasta=None, mios=None):
    """Indicadores de Producción del periodo (por defecto, últimos 30 días) y desviaciones que requieren acción."""
    from sqlalchemy import select
    from ..db import db
    from ..models import ProductionReport
    from . import reports as rsvc
    mios = mios if mios is not None else set(INDICADORES)
    d = rsvc.produccion(desde, hasta)
    cap = rsvc.produccion_capacidad(d["desde"], d["hasta"])
    ent = sum(x["entrada"] for x in d["lineas"])
    sal = sum(x["salida"] for x in d["lineas"])
    des = sum(x["desmedro"] for x in d["lineas"])
    capacidad = sum(f["capacidad"] for f in cap["filas"])
    producido = sum(f["producido"] for f in cap["filas"])
    oees = [r.indicadores.get("oee") for r in db().execute(select(ProductionReport).where(
        ProductionReport.fecha >= d["desde"], ProductionReport.fecha <= d["hasta"],
        ProductionReport.estado != "PROGRAMADO")).scalars() if (r.indicadores or {}).get("oee") is not None]
    umbral = float(param("umbral_merma_pct", 5) or 5)
    alertas = []
    if "PROD_CUMPLIMIENTO" in mios and d["plan"]["tasa"] is not None and d["plan"]["tasa"] < 90:
        alertas.append(("ALTA", f"Cumplimiento del programa {d['plan']['tasa']} % (referencia 90 %): revise capacidad, "
                                "materiales y paradas en el informe de producción."))
    fuera = [m for m in d["merma"] if m["fuera"]]
    if "PROD_MERMA_FUERA" in mios and fuera:
        alertas.append(("MEDIA", f"{len(fuera)} liquidación(es) con merma fuera de lo proyectado: "
                                 + ", ".join(m["liq"].numero_documento for m in fuera[:4]) + "."))
    if "PROD_PARADAS" in mios and cap["demoradas"]:
        alertas.append(("MEDIA", f"{len(cap['demoradas'])} solicitud(es) de producción atendidas después de la fecha "
                                 "requerida o vencidas."))
    return {"d": d, "cap": cap, "rend": round(100 * sal / ent, 1) if ent else None,
            "desm": round(100 * des / ent, 1) if ent else None, "umbral_merma": umbral,
            "uso": round(100 * producido / capacidad, 1) if capacidad else None,
            "oee": round(sum(oees) / len(oees), 1) if oees else None, "n_oee": len(oees), "alertas": alertas}


def _pct(x):
    return "—" if x is None else f"{x} %"


def values(user, codes, desde=None, hasta=None):
    """Valor de cada indicador pedido que el usuario puede ver: [{codigo, nombre, valor, detalle}]. Los no visibles
    se descartan aquí (no basta con no ofrecerlos en pantalla)."""
    from .kpis import compute
    codes = [c for c in codes if c in INDICADORES and visible(user, c) and INDICADORES[c][2] != "Datos"]
    if not codes:
        return []
    k = compute(desde, hasta) if any(not c.startswith("PROD_") for c in codes) else {}
    p = production_summary(desde, hasta, set(codes)) if any(c.startswith("PROD_") for c in codes) else {}

    def otif(t):
        return (f"{t[0]} %", f"{t[1]} de {t[2]} pedidos completos y a tiempo") if t else ("—", "sin despachos en el periodo")
    fx = {
        "PED_PENDIENTES": lambda: (k["pendientes"], f"{k['completos']} con stock completo · {k['incompletos']} incompletos"),
        "PED_COBERTURA": lambda: (_pct(k["cobertura_unidades_prom"]), f"por líneas {_pct(k['cobertura_lineas_prom'])}"),
        "OTIF_SALIDA": lambda: otif(k["otif_salida"]),
        "FILL_RATE": lambda: (_pct(k["fill_rate_unidades"]), f"líneas {_pct(k['fill_rate_lineas'])}"),
        "VOLUMEN_OV_KG": lambda: (f"{k['volumen_kg']:,.0f} kg", f"pendiente {k['volumen_pendiente_kg']:,.0f} kg"),
        "RECHAZOS": lambda: (k["rechazos"], f"{k['devoluciones']} devoluciones · {k['entregas_parciales']} parciales"),
        "MONTO_OV": lambda: (f"S/ {k['monto_total']:,.2f}", f"pendiente S/ {k['monto_pendiente']:,.2f}"),
        "PRECIO_BAJO_MINIMO": lambda: (k["precio_bajo_minimo"], f"{k['ov_sin_precio']} OV sin precio"),
        "T_PREPARACION": lambda: ("—" if k["tiempo_preparacion_h"] is None else f"{k['tiempo_preparacion_h']} h", "promedio"),
        "T_DESPACHO": lambda: ("—" if k["tiempo_despacho_h"] is None else f"{k['tiempo_despacho_h']} h", "promedio"),
        "COMPRAS_PENDIENTES": lambda: (k["compras_pendientes"], "solicitudes abiertas"),
        "PRODUCCION_PENDIENTE": lambda: (k["produccion_pendiente"], "solicitudes abiertas"),
        "DIF_INVENTARIO": lambda: (k["diferencias_inventario"], "líneas de conteo con diferencia"),
        "DIF_RECEPCION_PT": lambda: (k["diferencias_liquidacion"], "liquidaciones recibidas con diferencia"),
        "PED_DETENIDOS": lambda: (len(k["detenidos"]), "pedidos con motivo de detención"),
        "PED_ESTADOS": lambda: (k["n_ordenes"], ", ".join(f"{e} {n}" for e, n in k["estados"].items())[:120]),
        "FALTANTES": lambda: (len(k["faltantes"]), ", ".join(f"{c} ({q:g})" for c, q in k["faltantes"][:4])),
        "FILL_DETALLE": lambda: (len(k["fill_detalle"]), "pedidos despachados con su fill rate"),
        "CAUSAS_ERROR": lambda: (len(k["fill_causas"]), (lambda c: f"principal: {c[0][1]} ({c[0][2]})" if c else "sin fallas")(k["fill_causas"])),
        "INCIDENCIAS": lambda: (sum(k["incidencias"].values()), ", ".join(f"{t} {n}" for t, n in k["incidencias"].items())[:120]),
        "PROD_CUMPLIMIENTO": lambda: (_pct(p["d"]["plan"]["tasa"]), "Σ mín(real, plan) / Σ plan · referencia 90 %"),
        "PROD_PRODUCIDO": lambda: (f"{p['d']['kg']:,.0f} kg", f"{p['d']['unidades']:,.0f} unidades · {p['d']['liquidaciones']} liquidaciones"),
        "PROD_RENDIMIENTO": lambda: (_pct(p["rend"]), f"desmedro {_pct(p['desm'])} (umbral {p['umbral_merma']:g} %)"),
        "PROD_MERMA_FUERA": lambda: (sum(1 for m in p["d"]["merma"] if m["fuera"]), f"de {len(p['d']['merma'])} con proyección"),
        "PROD_CAPACIDAD": lambda: (_pct(p["uso"]), "kg procesados / capacidad"),
        "PROD_PARADAS": lambda: (len(p["cap"]["paradas"]), f"{p['cap']['paradas_min']} min · {len(p['cap']['demoradas'])} atendidas tarde"),
        "PROD_OEE": lambda: (_pct(p["oee"]), f"{p['n_oee']} partes con dato"),
    }
    out = []
    for c in codes:
        v, det = fx[c]()
        out.append({"codigo": c, "nombre": INDICADORES[c][0], "valor": v, "detalle": det})
    return out
