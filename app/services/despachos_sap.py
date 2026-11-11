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
    ws.append(["Orden", "Clase", "Serie", "Cliente", "Fecha compromiso", "Estado", "Producto", "Descripción", "Solicitado", "Entregado (SAP)",
               "Pendiente", "Nota de crédito (no se despacha)", "Guiado (guías)", "Cuadra", "Guías", "Facturas",
               "Órdenes de fabricación", "Observación"])
    for c in ws[1]:
        c.font = Font(bold=True)
    txt = {"PARCIAL": "Incompleto (parcial)", "COMPLETO": "Completo", "SIN_DESPACHO": "Sin despacho"}
    for f in res["filas"]:
        for ln in f["lineas"]:
            ws.append([f["ov"], "Servicio" if f.get("clase") == "SERVICIO" else "Venta", f.get("serie", ""), f["cliente"],
                       f["fecha"], txt[f["estado"]], ln["producto"], ln["descripcion"], ln["solicitado"],
                       ln["entregado"], ln["pendiente"], ln.get("nota_credito", 0), ln["guiado"], "Sí" if ln["cuadra"] else "No",
                       ", ".join(gn for gn, _ in f["guias"]), ", ".join(f["facturas"]),
                       "; ".join(f"OF {x['orden']} {x['completado']:g}/{x['planificado']:g} {x['estado']}" for x in f.get("servicios", [])),
                       " ".join(f["alertas"])])
    ws.freeze_panes = "A2"
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
