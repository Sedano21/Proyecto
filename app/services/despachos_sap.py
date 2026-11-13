"""V26 (11-nov-2026): OV abiertas de SAP frente a sus guías (entregas) de SAP: qué despachos están completos,
incompletos (parciales) o sin despacho, y si lo guiado cuadra con lo que SAP marca como entregado en la OV.

Fuente: la última carga de «Órdenes de venta abiertas» (cantidad solicitada y entregada por línea, según SAP) y la
última carga de «Entregas (guías)» (guía, fecha, producto y cantidad). Solo lee: no cambia nada en el módulo ni en SAP.
"""
from collections import defaultdict

from sqlalchemy import select

from ..db import db
from ..models import CustomerInvoice, UploadBatch

TOL = 1e-6


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _ultima(tipo):
    return db().execute(select(UploadBatch).where(UploadBatch.tipo == tipo, UploadBatch.estado != "ANULADO")
                        .order_by(UploadBatch.id.desc())).scalars().first()


def estado_ov(lineas):
    sol = sum(l["solicitado"] for l in lineas)
    ent = sum(l["entregado"] for l in lineas)
    if ent <= TOL:
        return "SIN_DESPACHO"
    if all(l["entregado"] + TOL >= l["solicitado"] for l in lineas):
        return "COMPLETO"
    return "PARCIAL"


def conciliar(ov_batch=None, guias_batch=None, clase=None):
    """V29: clase = VENTA (órdenes de venta), SERVICIO (órdenes de servicio) o None (todas).
    [{ov, cliente, fecha, estado, lineas[{producto, solicitado, entregado, pendiente, guiado, cuadra}], guias, alerta}]"""
    from .orders import order_by_number
    ovb = ov_batch or _ultima("OV")
    gub = guias_batch or _ultima("DESPACHOS")
    if ovb is None:
        return {"ov_batch": None, "guias_batch": gub, "filas": [], "tot": {}}
    guias = defaultdict(lambda: {"guias": {}, "cant": defaultdict(float), "facturas": set()})
    if gub is not None:
        for r in gub.rows:
            if r.excluida:
                continue
            d = r.datos or {}
            g = guias[_txt(d.get("ov"))]
            if _txt(d.get("guia")):
                g["guias"][_txt(d["guia"])] = _txt(d.get("fecha"))[:10]
            if _txt(d.get("factura")):
                g["facturas"].add(_txt(d["factura"]))
            g["cant"][_txt(d.get("producto"))] += _num(d.get("cantidad"))
    ovs = {}
    for r in ovb.rows:
        if r.excluida:
            continue
        d = r.datos or {}
        if _txt(d.get("estado")).lower().startswith("cerr"):
            continue
        n = _txt(d.get("numero"))
        o = ovs.setdefault(n, {"ov": n, "cliente": _txt(d.get("cliente")), "fecha": _txt(d.get("fecha_compromiso"))[:10],
                               "clase": "SERVICIO" if _txt(d.get("clase")).upper() == "SERVICIO" else "VENTA",
                               "serie": _txt(d.get("serie")),
                               "lineas": defaultdict(lambda: {"solicitado": 0.0, "entregado": 0.0})})
        ln = o["lineas"][_txt(d.get("producto"))]
        ln["solicitado"] += _num(d.get("solicitado"))
        ln["entregado"] += _num(d.get("entregado"))
        ln["descripcion"] = _txt(d.get("descripcion"))
    filas, tot = [], defaultdict(int)
    from .core import param
    from .notas_credito_ov import aplicadas_por_ov
    por_clase = defaultdict(int)
    for o in ovs.values():
        por_clase[o["clase"]] += 1
    if clase:
        ovs = {k: v for k, v in ovs.items() if v["clase"] == clase}
    servicios = defaultdict(list)
    for x in ((param("sap_servicios_ultimo", {}) or {}).get("filas") or []):
        servicios[_txt(x.get("ov"))].append(x)
    for n, o in ovs.items():
        g = guias.get(n)
        lineas = []
        ncs = aplicadas_por_ov(n)  # V29: lo que una nota de crédito sacó del despacho
        for prod, ln in o["lineas"].items():
            guiado = g["cant"].get(prod, 0.0) if g else 0.0
            lineas.append({"producto": prod, "descripcion": ln.get("descripcion", ""), "solicitado": ln["solicitado"],
                           "nota_credito": ncs.get(prod, 0.0),
                           "entregado": ln["entregado"], "pendiente": max(ln["solicitado"] - ln["entregado"], 0.0),
                           "guiado": guiado, "cuadra": abs(guiado - ln["entregado"]) <= TOL or (g is None and ln["entregado"] <= TOL)})
        est = estado_ov(lineas)
        alertas = []
        if est == "COMPLETO":
            alertas.append("Entregada completa en SAP pero la OV sigue abierta: cerrarla en SAP.")
        if ncs:
            alertas.append("Nota de crédito: no se despacha " + ", ".join(f"{k} {v:g}" for k, v in ncs.items())
                           + " (ya descontado del picking en el módulo).")
            if est == "PARCIAL" and all(l["entregado"] + l["nota_credito"] + TOL >= l["solicitado"] for l in lineas):
                alertas.append("Con la nota de crédito, lo entregado completa la OV: cerrarla en SAP.")
        if est != "SIN_DESPACHO" and not g:
            alertas.append("SAP la marca con entregas, pero no hay guías en la carga de entregas (¿guía anterior al periodo "
                           "traído? Amplíe «sap_despachos_dias»).")
        elif g and any(not l["cuadra"] for l in lineas):
            alertas.append("Lo guiado no cuadra con lo entregado en la OV (revise guías anteriores al periodo o anuladas).")
        mod = order_by_number(n)
        facturas = set((g or {}).get("facturas", set()))
        if mod is not None:  # V27: también las facturas traídas de SAP a Finanzas que están unidas a la OV
            facturas |= {inv.numero for inv in db().execute(select(CustomerInvoice).where(
                CustomerInvoice.order_id == mod.id, CustomerInvoice.tipo == "FACTURA")).scalars()}
        ords = servicios.get(n, [])
        if ords and est != "COMPLETO":  # V27: OV de maquila atendida con orden de servicio/fabricación
            plan = sum(x["planificado"] for x in ords)
            comp = sum(x["completado"] for x in ords)
            alertas.append(f"Orden de fabricación: {comp:g} de {plan:g} completado"
                           + (" (completa: falta despacharla)" if plan and comp + TOL >= plan else "") + ".")
        filas.append({"ov": n, "cliente": o["cliente"], "fecha": o["fecha"], "estado": est, "lineas": lineas,
                      "clase": o["clase"], "serie": o["serie"],
                      "guias": sorted((g or {}).get("guias", {}).items()), "facturas": sorted(facturas),
                      "servicios": ords, "alertas": alertas, "modulo": mod})
        tot["CON_SERVICIO"] += 1 if ords else 0
        tot[est] += 1
        tot["CON_ALERTA"] += 1 if alertas else 0
    orden = {"PARCIAL": 0, "COMPLETO": 1, "SIN_DESPACHO": 2}
    filas.sort(key=lambda f: (orden[f["estado"]], f["fecha"], f["ov"]))
    tot["TOTAL"] = len(filas)
    return {"ov_batch": ovb, "guias_batch": gub, "filas": filas, "tot": dict(tot), "por_clase": dict(por_clase),
            "servicios_ts": (param("sap_servicios_ultimo", {}) or {}).get("ts", "")}


def excel(res):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "OV vs guías"
    ws.append(["Orden", "Clase", "Serie", "Estado en SAP", "Emisión", "Cliente", "Fecha compromiso", "Estado", "Producto", "Descripción", "Solicitado", "Entregado (SAP)",
               "Pendiente", "Nota de crédito (no se despacha)", "Guiado (guías)", "Cuadra", "Guías", "Facturas",
               "Órdenes de fabricación", "Observación"])
    for c in ws[1]:
        c.font = Font(bold=True)
    txt = {"PARCIAL": "Incompleto (parcial)", "COMPLETO": "Completo", "SIN_DESPACHO": "Sin despacho"}
    for f in res["filas"]:
        for ln in f["lineas"]:
            ws.append([f["ov"], "Servicio" if f.get("clase") == "SERVICIO" else "Venta", f.get("serie", ""),
                       {"ABIERTA": "Abierta", "CERRADA": "Cerrada"}.get(f.get("sap", "ABIERTA"), f.get("sap", "")),
                       f.get("emision", ""), f["cliente"],
                       f["fecha"], txt[f["estado"]], ln["producto"], ln["descripcion"], ln["solicitado"],
                       ln["entregado"], ln["pendiente"], ln.get("nota_credito", 0), ln["guiado"], "Sí" if ln["cuadra"] else "No",
                       ", ".join(gn for gn, _ in f["guias"]), ", ".join(f["facturas"]),
                       "; ".join(f"OF {x['orden']} {x['completado']:g}/{x['planificado']:g} {x['estado']}" for x in f.get("servicios", [])),
                       " ".join(f["alertas"])])
    ws.freeze_panes = "A2"
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ------------------------------------------------------------------ V31 (13-nov-2026): historial desde julio
def meses_historial(hoy=None):
    from datetime import date
    from .sap_v31 import historial_desde
    hoy = hoy or date.today()
    d = historial_desde().replace(day=1)
    out = []
    while d <= hoy.replace(day=1):
        out.append(f"{d:%Y-%m}")
        d = (d.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
    return out


def conciliar_historial(mes="", clase=None, situacion="ABIERTAS"):
    """Órdenes de SAP desde julio (abiertas y cerradas) frente a sus guías de SAP. mes = «AAAA-MM» de la fecha de la
    orden (emisión) o vacío (todos); situacion = ABIERTAS, CERRADAS o TODAS (en SAP)."""
    from .core import param
    from .notas_credito_ov import aplicadas_por_ov
    from .orders import order_by_number
    from ..models import SapMovement, SapOrderLine
    s = db()
    q = select(SapOrderLine).where(SapOrderLine.estado != "CANCELADA")
    if mes:
        from datetime import date
        ini = date(int(mes[:4]), int(mes[5:7]), 1)
        fin = (ini.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
        q = q.where(SapOrderLine.fecha >= ini, SapOrderLine.fecha < fin)
    ordenes = {}
    for r in s.execute(q.order_by(SapOrderLine.fecha, SapOrderLine.docnum, SapOrderLine.id)).scalars():
        o = ordenes.setdefault(r.docnum, {"ov": r.docnum, "cliente": r.cliente, "fecha": r.fecha_entrega.isoformat() if r.fecha_entrega else "",
                                          "emision": r.fecha.isoformat() if r.fecha else "", "clase": r.clase or "VENTA",
                                          "serie": r.serie, "sap": r.estado,
                                          "lineas": defaultdict(lambda: {"solicitado": 0.0, "entregado": 0.0, "descripcion": ""})})
        ln = o["lineas"][r.product_code]
        ln["solicitado"] += r.cantidad
        ln["entregado"] += r.entregado
        ln["descripcion"] = r.descripcion
    por_clase, por_sit = defaultdict(int), defaultdict(int)
    for o in ordenes.values():
        por_clase[o["clase"]] += 1
        por_sit[o["sap"]] += 1
    if clase:
        ordenes = {k: v for k, v in ordenes.items() if v["clase"] == clase}
    if situacion in ("ABIERTAS", "CERRADAS"):
        ordenes = {k: v for k, v in ordenes.items() if v["sap"] == situacion[:-1]}
    guias = defaultdict(lambda: {"guias": {}, "cant": defaultdict(float)})
    if ordenes:
        nums = list(ordenes)
        for i in range(0, len(nums), 500):
            for m in s.execute(select(SapMovement).where(SapMovement.tipo == "GUIA", SapMovement.ov_numero.in_(nums[i:i + 500]))).scalars():
                g = guias[m.ov_numero]
                g["guias"][m.documento] = m.fecha.isoformat() if m.fecha else ""
                g["cant"][m.product_code] += m.cantidad
    servicios = defaultdict(list)
    for x in ((param("sap_servicios_ultimo", {}) or {}).get("filas") or []):
        servicios[_txt(x.get("ov"))].append(x)
    filas, tot = [], defaultdict(int)
    for n, o in ordenes.items():
        g = guias.get(n)
        ncs = aplicadas_por_ov(n)
        lineas = []
        for prod, ln in o["lineas"].items():
            guiado = g["cant"].get(prod, 0.0) if g else 0.0
            lineas.append({"producto": prod, "descripcion": ln["descripcion"], "solicitado": ln["solicitado"],
                           "nota_credito": ncs.get(prod, 0.0), "entregado": ln["entregado"],
                           "pendiente": max(ln["solicitado"] - ln["entregado"], 0.0) if o["sap"] == "ABIERTA" else 0.0,
                           "sin_entregar": max(ln["solicitado"] - ln["entregado"], 0.0),
                           "guiado": guiado, "cuadra": abs(guiado - ln["entregado"]) <= TOL})
        est = estado_ov(lineas)
        alertas = []
        if o["sap"] == "ABIERTA" and est == "COMPLETO":
            alertas.append("Entregada completa en SAP pero la orden sigue abierta: cerrarla en SAP.")
        if o["sap"] == "CERRADA" and est != "COMPLETO":
            alertas.append("Cerrada en SAP con saldo sin entregar" + (" (sin ninguna entrega)." if est == "SIN_DESPACHO" else "."))
        if ncs:
            alertas.append("Nota de crédito: no se despacha " + ", ".join(f"{k} {v:g}" for k, v in ncs.items()) + ".")
        if any(not l["cuadra"] for l in lineas):
            alertas.append("Lo guiado no cuadra con lo entregado según la orden (guías anteriores a julio, anuladas o devueltas).")
        mod = order_by_number(n)
        facturas = set()
        if mod is not None:
            facturas = {inv.numero for inv in s.execute(select(CustomerInvoice).where(
                CustomerInvoice.order_id == mod.id, CustomerInvoice.tipo == "FACTURA")).scalars()}
        ords = servicios.get(n, [])
        if ords and est != "COMPLETO":
            plan = sum(x["planificado"] for x in ords)
            comp = sum(x["completado"] for x in ords)
            alertas.append(f"Orden de fabricación: {comp:g} de {plan:g} completado"
                           + (" (completa: falta despacharla)" if plan and comp + TOL >= plan else "") + ".")
        filas.append({"ov": n, "cliente": o["cliente"], "fecha": o["fecha"], "emision": o["emision"], "estado": est,
                      "sap": o["sap"], "lineas": lineas, "clase": o["clase"], "serie": o["serie"],
                      "guias": sorted((g or {}).get("guias", {}).items()), "facturas": sorted(facturas),
                      "servicios": ords, "alertas": alertas, "modulo": mod})
        tot[est] += 1
        tot["CON_ALERTA"] += 1 if alertas else 0
        tot["CON_SERVICIO"] += 1 if ords else 0
    orden = {"PARCIAL": 0, "COMPLETO": 1, "SIN_DESPACHO": 2}
    filas.sort(key=lambda f: (orden[f["estado"]], f["emision"], f["ov"]))
    tot["TOTAL"] = len(filas)
    ult = param("sap_ordenes_ultimo", {}) or {}
    return {"ov_batch": None, "guias_batch": None, "filas": filas, "tot": dict(tot), "por_clase": dict(por_clase),
            "por_situacion": dict(por_sit), "historial": True, "historial_ts": (ult.get("ts") or "").replace("T", " "),
            "historial_desde": ult.get("desde", ""),
            "servicios_ts": (param("sap_servicios_ultimo", {}) or {}).get("ts", "")}
