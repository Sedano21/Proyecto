"""Liquidación de proceso CP-OPE-004 (formato «LIQUIDACIONES 2026», 30-oct-2026). Solo Producción.

- Se prellena con los partes de producción que registran los asistentes (línea, SKU, lote, kg de ingreso, salida,
  desmedro, remanente, horas y operarios); luego Producción completa y ajusta el formato.
- Variante PR: uno o varios procesos (cada uno con su tabla PROCESO / CALIDAD / SACOS / PESO POR SACO / SALDO / TOTAL /
  MOVIMIENTO / %, desviación, horas, operarios y desmedro). Variante PF: un proceso con costo MO + CIF y costo del
  desmedro.
- Los campos de «Datos del servicio» y «Datos del producto», las filas y los procesos se agregan o quitan.
- Fotos (referencias gráficas del lote) y observaciones. Exportación a Excel con el diseño y las fórmulas del formato.
"""
import io
import os
from datetime import date, datetime

from sqlalchemy import func, select

from ..db import db
from ..models import ProcessLiquidation, ProductionReport, StockLot, now
from .core import BusinessError, audit, has_perm, param

CODIGO = "CP- OPE - 004"
PERM = "produccion.liquidacion_proceso"
# filas de desmedro del formato (proceso «graneal a MP» del modelo)
DESMEDRO_FILAS = ["TALLA S (Malla inferior)", "TALLA L (Malla superior)", "MALLA CENTRAL", "ASPIRACION",
                  "DESCARTE (Piedra,Tallo,Paja)", "D. GRAVIMETRICA", "D. OPTICA", "PISO"]
SERVICIO_PR = ["Proceso", "Proceso N°1", "Proceso N°2", "Proceso N°3", "Fecha de recepción", "Fecha del reporte"]
SERVICIO_PF = ["Proceso", "Proceso N°1", "Proceso N°2", "Proceso N°3", "Fecha de recepción", "Fecha de proceso"]
PRODUCTO = ["Descripción", "Marca", "Proveedor", "Procedencia", "Lote", "Calidad", "FP", "FV", "Empaque primario",
            "Empaque secundario", "Peso neto (KG)", "Peso del saco (KG)"]
ORDINALES = ["1ER", "2DO", "3ER", "4TO", "5TO", "6TO", "7MO", "8VO", "9NO", "10MO"]


def _req(user):
    if not has_perm(user, PERM):
        raise BusinessError("La liquidación de proceso la registra Producción.")


def _num(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        raise BusinessError(f"Valor numérico inválido: «{v}».")


def _f(d):
    return d.strftime("%d/%m/%Y") if isinstance(d, (date, datetime)) else (d or "")


def _fila(proceso, calidad, sacos=None, peso_saco=None, saldo=None):
    return {"proceso": proceso, "calidad": calidad, "sacos": sacos, "peso_saco": peso_saco, "saldo": saldo}


def _proceso_de_parte(r, n):
    """Tabla de un proceso a partir del parte del asistente."""
    filas = [_fila("INGRESO", "GRANEL", r.sacos, r.peso_saco_kg, None if r.sacos and r.peso_saco_kg else r.peso_entrada_kg)]
    filas.append(_fila("SALIDA - MP", "MP", None, None, (r.granel_kg or 0) + (r.mp_kg or 0) or None))
    if r.cal3_kg:
        filas.append(_fila("SALIDA - TERCERA", "TERCERA", None, None, r.cal3_kg))
    if r.desmedro_kg:
        filas.append(_fila("SALIDA - DESMEDRO", "DESMEDRO (total del parte)", None, None, r.desmedro_kg))
    filas += [_fila("SALIDA - DESMEDRO", c) for c in DESMEDRO_FILAS]
    if r.sobrante_kg:
        filas.append(_fila("SALIDA - REMANENTE", "REMANENTE", None, None, r.sobrante_kg))
    return {"titulo": f"{ORDINALES[n] if n < len(ORDINALES) else n + 1} PROCESO : {r.linea}", "filas": filas,
            "horas": r.horas, "operarios": r.operarios, "report_id": r.id}


def reports_for(linea="", product_code="", lote="", limit=200):
    q = select(ProductionReport).where(ProductionReport.estado.notin_(("PROGRAMADO", "ANULADO")))
    if linea:
        q = q.where(ProductionReport.linea == linea)
    if product_code:
        q = q.where(ProductionReport.product_code == product_code)
    if lote:
        q = q.where((ProductionReport.lote == lote) | (ProductionReport.lote_pt == lote))
    return list(db().execute(q.order_by(ProductionReport.fecha.desc(), ProductionReport.id.desc()).limit(limit)).scalars())


def create(user, report_ids, variante="PR"):
    """Crea la liquidación con los partes elegidos (mismo SKU): un proceso por parte (PR) o un proceso sumado (PF)."""
    _req(user)
    if variante not in ("PR", "PF"):
        raise BusinessError("Variante no válida.")
    reps = [db().get(ProductionReport, int(i)) for i in report_ids or []]
    reps = sorted([r for r in reps if r is not None], key=lambda r: (r.fecha, r.id))
    if not reps:
        raise BusinessError("Elija al menos un parte de producción.")
    if len({r.product_code for r in reps}) > 1:
        raise BusinessError("Los partes elegidos deben ser del mismo SKU.")
    r0 = reps[0]
    p = r0.product
    lote = r0.lote or r0.lote_pt or ""
    lot = db().execute(select(StockLot).where(StockLot.product_code == (r0.mp_codigo or r0.product_code), StockLot.lote == lote)
                       ).scalars().first() if lote else None
    lineas = list(dict.fromkeys(r.linea for r in reps))
    servicio_labels = SERVICIO_PR if variante == "PR" else SERVICIO_PF
    serv_vals = ["", *(lineas + ["", "", ""])[:3], _f(lot.fecha_admision) if lot and lot.fecha_admision else "",
                 _f(reps[-1].fecha)]
    prod_vals = {"Descripción": p.descripcion if p else r0.product_code, "Marca": (p.marca if p else "") or "",
                 "Lote": lote, "Calidad": (p.calidad if p else "") or "",
                 "FP": _f(lot.fecha_fab) if lot and lot.fecha_fab else "",
                 "FV": _f(r0.fv_mp or (lot.fecha_venc if lot else None)),
                 "Peso del saco (KG)": "", "Peso neto (KG)": r0.peso_saco_kg if r0.peso_saco_kg else ""}
    if variante == "PR":
        procesos = [_proceso_de_parte(r, n) for n, r in enumerate(reps)]
    else:
        ent = sum(r.peso_entrada_kg or 0 for r in reps)
        sal = sum((r.granel_kg or 0) + (r.mp_kg or 0) + (r.cal3_kg or 0) for r in reps)
        des = sum(r.desmedro_kg or 0 for r in reps)
        procesos = [{"titulo": "", "filas": [_fila("INGRESO", "GRANEL", None, None, ent), _fila("SALIDA", "PROCESADO", None, None, sal),
                                             _fila("SALIDA", "DESMEDRO", None, None, des)],
                     "horas": sum(r.horas or 0 for r in reps) or None, "operarios": max((r.operarios or 0) for r in reps) or None}]
    numero = (db().execute(select(func.max(ProcessLiquidation.numero))).scalar() or 0) + 1
    liq = ProcessLiquidation(numero=numero, variante=variante, product_code=r0.product_code, lote=lote,
                             linea=" / ".join(lineas), fecha=reps[-1].fecha,
                             servicio=[{"etiqueta": e, "valor": v} for e, v in zip(servicio_labels, serv_vals)],
                             producto=[{"etiqueta": e, "valor": prod_vals.get(e, "")} for e in PRODUCTO],
                             procesos=procesos, costos={}, report_ids=[r.id for r in reps], user_id=user.id,
                             historial=[{"evento": "CREADA", "user": user.nombre, "ts": now().isoformat(timespec="minutes")}])
    db().add(liq)
    db().flush()
    audit(user, "LIQ_PROCESO_CREADA", "ProcessLiquidation", liq.id, {"partes": liq.report_ids, "variante": variante})
    return liq


def _campos(etqs, vals):
    out = []
    for e, v in zip(etqs, vals):
        e, v = (e or "").strip(), (v or "").strip()
        if e or v:
            if not e:
                raise BusinessError("Cada campo agregado necesita su nombre.")
            out.append({"etiqueta": e, "valor": v})
    return out


def update(user, liq, form):
    """Guarda lo editado (form: MultiDict). Campos y filas vacíos se quitan; los nuevos se agregan."""
    _req(user)
    if liq.estado == "CERRADA":
        raise BusinessError("La liquidación está cerrada.")
    g = form.getlist
    liq.servicio = _campos(g("s_etq"), g("s_val"))
    liq.producto = _campos(g("p_etq"), g("p_val"))
    procesos = []
    for i, ant in enumerate(liq.procesos or []):
        if form.get(f"quitar_{i}"):
            continue
        filas = []
        for pr, ca, sa, ps, so in zip(g(f"f{i}_proceso"), g(f"f{i}_calidad"), g(f"f{i}_sacos"), g(f"f{i}_peso"), g(f"f{i}_saldo")):
            if not any(x.strip() for x in (pr, ca, sa, ps, so)):
                continue
            filas.append(_fila(pr.strip(), ca.strip(), _num(sa), _num(ps), _num(so)))
        if filas and filas[0]["proceso"].upper() != "INGRESO":
            raise BusinessError("La primera fila de cada proceso debe ser el INGRESO.")
        procesos.append({"titulo": (form.get(f"t{i}") or "").strip(), "filas": filas, "horas": _num(form.get(f"h{i}")),
                         "operarios": _num(form.get(f"o{i}")), "report_id": ant.get("report_id")})
    if form.get("agregar_proceso"):
        n = len(procesos)
        procesos.append({"titulo": f"{ORDINALES[n] if n < len(ORDINALES) else n + 1} PROCESO : ", "horas": None, "operarios": None,
                         "filas": [_fila("INGRESO", "GRANEL"), _fila("SALIDA - MP", "MP")] + [_fila("SALIDA - DESMEDRO", c)
                                                                                             for c in DESMEDRO_FILAS]})
    if not procesos:
        raise BusinessError("La liquidación debe tener al menos un proceso.")
    liq.procesos = procesos
    if liq.variante == "PF":
        liq.costos = {k: _num(form.get(k)) for k in ("mo_seleccion", "mo_reproceso", "costo_hora", "cif_reproceso",
                                                      "costo_unidad", "costo_kg_desmedro")}
    liq.observaciones = (form.get("observaciones") or "").strip()
    quitar = set(g("quitar_foto"))
    liq.fotos = [f for f in liq.fotos or [] if f not in quitar]
    liq.historial = list(liq.historial or []) + [{"evento": "EDITADA", "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    audit(user, "LIQ_PROCESO_EDITADA", "ProcessLiquidation", liq.id, {})
    return liq


def add_photos(user, liq, nombres):
    _req(user)
    if liq.estado == "CERRADA":
        raise BusinessError("La liquidación está cerrada.")
    liq.fotos = list(liq.fotos or []) + [n for n in nombres if n]
    return liq


def close(user, liq):
    _req(user)
    c = calc(liq)
    if any(p["ingreso"] <= 0 for p in c["procesos"]):
        raise BusinessError("Cada proceso necesita el total de INGRESO para cerrar la liquidación.")
    liq.estado = "CERRADA"
    liq.historial = list(liq.historial or []) + [{"evento": "CERRADA", "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    audit(user, "LIQ_PROCESO_CERRADA", "ProcessLiquidation", liq.id, {})
    return liq


def reopen(user, liq):
    _req(user)
    if user.role_code != "JEFE_PRODUCCION":
        raise BusinessError("Reabre la liquidación el Jefe de Producción.")
    liq.estado = "BORRADOR"
    liq.historial = list(liq.historial or []) + [{"evento": "REABIERTA", "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    return liq


def calc(liq):
    """Cálculos del formato: TOTAL = sacos × peso por saco + saldo; MOVIMIENTO = −total en el ingreso y +total en las
    salidas; % = movimiento ÷ total de ingreso; DESVIACIÓN = suma de movimientos; DESMEDRO = filas de desmedro ÷ ingreso.
    PF: MO = (selección + reproceso) h × costo por hora; CIF = (kg de ingreso + reproceso) × costo por unidad; costo
    unitario = total ÷ unidades del CIF; costo del desmedro = kg de desmedro × costo por kg."""
    procesos = []
    for p in liq.procesos or []:
        filas, ingreso = [], 0.0
        for k, f in enumerate(p.get("filas") or []):
            total = (f.get("sacos") or 0) * (f.get("peso_saco") or 0) + (f.get("saldo") or 0)
            if k == 0:
                ingreso = total
            filas.append(dict(f, total=round(total, 2), mov=round(-total if k == 0 else total, 2),
                              pct=round(100 * total / ingreso, 2) if k and ingreso else None))
        desmedro = sum(x["total"] for x in filas[1:] if "DESMEDRO" in (x["proceso"] or "").upper()
                       or "DESMEDRO" in (x["calidad"] or "").upper())
        procesos.append(dict(p, filas=filas, ingreso=round(ingreso, 2), desviacion=round(sum(x["mov"] for x in filas), 2),
                             desmedro_kg=round(desmedro, 2), desmedro_pct=round(100 * desmedro / ingreso, 2) if ingreso else None))
    out = {"procesos": procesos}
    if liq.variante == "PF" and procesos:
        c = liq.costos or {}
        p0 = procesos[0]
        horas = (c.get("mo_seleccion") or 0) + (c.get("mo_reproceso") or 0)
        mo = horas * (c.get("costo_hora") or 0)
        unidades = p0["ingreso"] + (c.get("cif_reproceso") or 0)
        cif = unidades * (c.get("costo_unidad") or 0)
        des = p0["desmedro_kg"]
        out["costos"] = {"horas": horas, "mo": round(mo, 2), "unidades": round(unidades, 2), "cif": round(cif, 2),
                         "total": round(mo + cif, 2), "unitario": round((mo + cif) / unidades, 4) if unidades else None,
                         "desmedro_kg": des, "desmedro_costo": round(des * (c.get("costo_kg_desmedro") or 0), 2)}
    return out


def pie():
    return param("liquidacion_proceso_pie", []) or []


# ------------------------------------------------------------------ Excel con el diseño del formato
def export_excel(liq, static_dir, upload_dir):
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    VERDE, ETQ, CELESTE, OSCURO, GRIS, AMARILLO = "548235", "D6DCE4", "D9E1F2", "3A3838", "F2F2F2", "FFF2CC"
    thin = Side(style="thin", color="808080")
    caja = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook()
    ws = wb.active
    ws.title = f"LIQUIDACION {liq.numero:05d}"[:31]
    ws.sheet_view.showGridLines = False
    for col, w in zip("ABCDEFGHI", (5.7, 24.3, 23.4, 12.0, 14.6, 19.7, 15.1, 13.7, 9.0)):
        ws.column_dimensions[col].width = w

    def put(ref, v, bold=False, fill=None, color="000000", size=9, align=None, fmt=None, border=True):
        c = ws[ref]
        c.value = v
        c.font = Font(name="Calibri", bold=bold, size=size, color=color)
        if fill:
            c.fill = PatternFill("solid", fgColor=fill)
        if align:
            c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
        if fmt:
            c.number_format = fmt
        if border:
            c.border = caja
        return c

    # cabecera
    ws.merge_cells("B2:B4")
    ws.merge_cells("C2:G4")
    put("C2", "LIQUIDACION DE PROCESO ", bold=True, size=14, align="center", border=False)
    for r, t in ((2, CODIGO), (3, "OPERACIONES"), (4, f" N° {liq.numero:05d}")):
        ws.merge_cells(f"H{r}:I{r}")
        put(f"H{r}", t, bold=True, size=8, align="center")
    logo = os.path.join(static_dir, "img", "logo_corporacion_productiva.png")
    if os.path.exists(logo):
        im = XLImage(logo)
        im.width, im.height = 170, 40
        ws.add_image(im, "B2")
    # datos del servicio y del producto
    put("B6", "DATOS DEL SERVICIO", bold=True, fill=VERDE, color="FFFFFF")
    put("C6", "", fill=VERDE)
    ws.merge_cells("E6:I6")
    put("E6", "DATOS DEL PRODUCTO", bold=True, fill=VERDE, color="FFFFFF", align="center")
    fila = 7
    for x in liq.servicio or []:
        put(f"B{fila}", x["etiqueta"], fill=ETQ)
        put(f"C{fila}", x["valor"], fill=GRIS, align="left")
        fila += 1
    prod = liq.producto or []
    for k in range(0, len(prod), 2):
        r = 7 + k // 2
        put(f"E{r}", prod[k]["etiqueta"], fill=ETQ)
        put(f"F{r}", prod[k]["valor"], fill=GRIS, align="left")
        if k + 1 < len(prod):
            put(f"G{r}", prod[k + 1]["etiqueta"], fill=ETQ)
            ws.merge_cells(f"H{r}:I{r}")
            put(f"H{r}", prod[k + 1]["valor"], fill=GRIS, align="left")
    fila = max(fila, 7 + (len(prod) + 1) // 2) + 1
    cab = ["PROCESO", "CALIDAD", "SACOS (UNI)", "PESO POR SACO (KG)", "SALDO (KG)", "TOTAL (KG)", "MOVIMIENTO (KG)", "%"]
    c = calc(liq)
    for p in c["procesos"]:
        if p.get("titulo"):
            ws.merge_cells(f"B{fila}:I{fila}")
            put(f"B{fila}", p["titulo"], bold=True, fill=CELESTE, align="left")
            fila += 2
        for j, t in enumerate(cab if liq.variante == "PR" else cab[:-1]):
            put(f"{'BCDEFGHI'[j]}{fila}", t, bold=True, fill=OSCURO, color="FFFFFF", align="center")
        fila += 1
        r_ing = fila
        for k, f in enumerate(p["filas"]):
            put(f"B{fila}", f["proceso"])
            put(f"C{fila}", f["calidad"])
            put(f"D{fila}", f["sacos"], fmt="0.00", align="center")
            put(f"E{fila}", f["peso_saco"], fmt="0.00", align="center")
            put(f"F{fila}", f["saldo"], fmt="0.00", align="center")
            put(f"G{fila}", f"=D{fila}*E{fila}+F{fila}", fmt="0.00", align="right")
            put(f"H{fila}", f"=G{fila}*-1" if k == 0 else f"=G{fila}", fmt="0.00", align="right")
            if liq.variante == "PR":
                put(f"I{fila}", None if k == 0 else f"=IF(G${r_ing}=0,0,H{fila}/G${r_ing})", fmt="0.00%", align="center")
            fila += 1
        put(f"G{fila}", "DESVIACIÓN KG", bold=True, fill=CELESTE, align="center")
        put(f"H{fila}", f"=SUM(H{r_ing}:H{fila - 1})", bold=True, fill=GRIS, fmt="0.00", align="right")
        fila += 1
        des = [r_ing + k for k, f in enumerate(p["filas"]) if k and ("DESMEDRO" in (f["proceso"] or "").upper()
                                                                     or "DESMEDRO" in (f["calidad"] or "").upper())]
        put(f"B{fila}", "TOTAL DE HR", bold=True, fill=ETQ)
        put(f"C{fila}", p.get("horas"), align="center")
        put(f"E{fila}", "NRO DE OPE.", bold=True, fill=ETQ)
        put(f"F{fila}", p.get("operarios"), align="center")
        put(f"G{fila}", "DESMEDRO", bold=True, fill=CELESTE, align="center")
        suma = "+".join(f"G{r}" for r in des) or "0"
        put(f"H{fila}", f"=IF(G{r_ing}=0,0,({suma})/G{r_ing})", bold=True, fill=GRIS, fmt="0.00%", align="right")
        fila += 3
    if liq.variante == "PF" and "costos" in c:
        k = liq.costos or {}
        ws.merge_cells(f"B{fila}:I{fila}")
        put(f"B{fila}", "COSTO MO + CIF", bold=True, fill=CELESTE, align="center")
        fila += 2
        for j, t in enumerate(["COSTOS", "SELECCIÓN", "REPROCESO", "TOTAL", "UNI. DE MEDIDA", "COSTO", "SUBTOTAL"]):
            put(f"{'BCDEFGH'[j]}{fila}", t, bold=True, fill=OSCURO, color="FFFFFF", align="center")
        r1 = fila + 1
        put(f"B{r1}", "MANO DE OBRA"); put(f"C{r1}", k.get("mo_seleccion")); put(f"D{r1}", k.get("mo_reproceso"))
        put(f"E{r1}", f"=SUM(C{r1}:D{r1})"); put(f"F{r1}", "HORAS"); put(f"G{r1}", k.get("costo_hora"), fmt='"S/" #,##0.00')
        put(f"H{r1}", f"=G{r1}*E{r1}", fmt='"S/" #,##0.00')
        r2 = r1 + 1
        put(f"B{r2}", "CIF"); put(f"C{r2}", c["procesos"][0]["ingreso"], fmt="#,##0.00"); put(f"D{r2}", k.get("cif_reproceso"))
        put(f"E{r2}", f"=SUM(C{r2}:D{r2})", fmt="#,##0.00"); put(f"F{r2}", "UNIDADES")
        put(f"G{r2}", k.get("costo_unidad"), fmt='"S/" #,##0.00'); put(f"H{r2}", f"=G{r2}*E{r2}", fmt='"S/" #,##0.00')
        put(f"G{r2 + 1}", "TOTAL", bold=True); put(f"H{r2 + 1}", f"=SUM(H{r1}:H{r2})", bold=True, fmt='"S/" #,##0.00')
        put(f"G{r2 + 2}", "COSTO UNITARIO", bold=True)
        put(f"H{r2 + 2}", f"=IF(E{r2}=0,0,H{r2 + 1}/E{r2})", bold=True, fmt='"S/" #,##0.00')
        fila = r2 + 4
        ws.merge_cells(f"B{fila}:I{fila}")
        put(f"B{fila}", "COSTO DE DESMEDRO", bold=True, fill=CELESTE, align="center")
        fila += 2
        for j, t in enumerate(["GASTOS", "SACOS (UNI)", "PESO POR SACO (KG)", "SALDO (KG)", "TOTAL (KG)", "COSTO (KG)", "SUBTOTAL"]):
            put(f"{'BCDEFGH'[j]}{fila}", t, bold=True, fill=OSCURO, color="FFFFFF", align="center")
        fila += 1
        put(f"B{fila}", "INGRESO"); put(f"F{fila}", c["costos"]["desmedro_kg"], fmt="0.00")
        put(f"G{fila}", k.get("costo_kg_desmedro"), fmt='"S/" #,##0.00'); put(f"H{fila}", f"=G{fila}*F{fila}", fmt='"S/" #,##0.00')
        put(f"G{fila + 1}", "TOTAL", bold=True); put(f"H{fila + 1}", f"=H{fila}", bold=True, fmt='"S/" #,##0.00')
        fila += 4
    # referencias gráficas y observaciones
    ws.merge_cells(f"B{fila}:F{fila}")
    put(f"B{fila}", "REFERENCIAS GRÁFICAS DEL LOTE RECEPCIONADO", bold=True, fill=VERDE, color="FFFFFF", align="center")
    ws.merge_cells(f"G{fila}:I{fila}")
    put(f"G{fila}", "OBSERVACIONES", bold=True, fill=VERDE, color="FFFFFF", align="center")
    top = fila + 2
    ws.merge_cells(f"B{top}:F{top + 10}")
    ws.merge_cells(f"G{top}:I{top + 10}")
    put(f"G{top}", liq.observaciones, fill=AMARILLO, size=8, align="center")
    col = 0
    for f in (liq.fotos or [])[:4]:
        path = os.path.join(upload_dir, os.path.basename(f))
        if not os.path.exists(path) or not path.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        try:
            im = XLImage(path)
        except Exception:  # imagen dañada o formato no soportado por openpyxl
            continue
        ratio = im.height / im.width if im.width else 1
        im.width, im.height = 130, int(130 * ratio) if ratio < 1.6 else 200
        ws.add_image(im, f"{'BCDE'[col]}{top}")
        col += 1
    fila = top + 13
    for k, t in enumerate(pie()):
        ws.merge_cells(f"C{fila + k}:G{fila + k}")
        put(f"C{fila + k}", t, size=9, align="center", border=False)
    for nombre, celda in (("logo_cosecha_andina.png", f"B{fila - 1}"), ("logo_cantaclaro.png", f"H{fila - 1}")):
        p = os.path.join(static_dir, "img", nombre)
        if os.path.exists(p):
            im = XLImage(p)
            im.width, im.height = 70, 70
            ws.add_image(im, celda)
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
