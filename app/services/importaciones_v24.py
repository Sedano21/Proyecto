"""V24 (06-nov-2026): seguimiento de importaciones (cuadro de Importaciones), gastos extra, contratos, alertas y precios.

El cuadro tiene las columnas que usa Importaciones: código SAP (o «POR CONFIRMAR»), contrato, proveedor, ítem, país de
origen, contenedores, fecha de llegada, días libres, fecha máxima de retiro (= llegada + días libres), 1) status de
SENASA, 2) liberación del BL, 3) retiro (fecha real o tentativa) e información del almacén de recepción. Lo registran
la Coordinación y la Asistencia de Importaciones (también desde Excel con esas columnas).

Alertas (a Gerente General Adjunto, Coordinación y Asistencia de Importaciones):
- retiro próximo: faltan «import_alerta_retiro_dias» días para la fecha máxima de retiro y no se retiró;
- sobreestadía: pasó la fecha máxima sin retiro; se estima el costo = contenedores × días × costo por contenedor y día
  (del contrato o «import_sobreestadia_usd_dia»);
- retraso / trámite pendiente: la carga llegó y SENASA o el BL siguen pendientes; o el retiro tentativo es posterior a
  la fecha máxima;
- penalidad: a favor de la empresa si la llegada es posterior a la fecha pactada en el contrato (días × penalidad por
  día); en contra por sobreestadía o devolución tardía de contenedor (gastos registrados);
- inconveniente: cualquier incidencia que se reporte.

Precios: con el precio de compra del contrato (USD por unidad) y el tipo de cambio SUNAT se compara, por producto, el
costo importado (más los gastos extra prorrateados) con las cotizaciones nacionales.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import ImportFollowup, Product
from . import alerts
from .core import BusinessError, audit, has_perm, param

ESTADOS = {"EN_TRANSITO": "En tránsito", "EN_PUERTO": "En puerto", "RETIRADO": "Retirado", "CERRADO": "Cerrado"}
TIPOS_GASTO = ["Sobreestadía", "Devolución tarde de contenedor", "Almacenaje", "Flete adicional", "Inspección / SENASA",
               "Agente de aduanas", "Otro"]
COLUMNAS_EXCEL = ["CÓDIGO SAP", "CONTRATO", "PROVEEDOR", "ITEM", "PAÍS DE ORIGEN", "CONTENEDORES", "FECHA DE LLEGADA",
                  "DÍAS LIBRES", "FECHA MÁXIMO DE RETIRO", "1 STATUS DE SENASA", "2 STATUS-LIBERACIÓN DE BL",
                  "3 STATUS-RETIRO(FECHA REAL O TENTATIVA)", "INFORMACIÓN DEL ALMACÉN DE RECEPCIÓN"]


def _req(user):
    if not has_perm(user, "importaciones.seguimiento"):
        raise BusinessError("Registran la Coordinación o la Asistencia de Importaciones.")


def fecha_max_retiro(f):
    return f.fecha_llegada + timedelta(days=int(f.dias_libres or 0)) if f.fecha_llegada else None


def _fecha(v, ref=None):
    """Acepta date, «dd/mm/aaaa», «aaaa-mm-dd» o «09-nov» (año de la llegada o el actual)."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v).strip().lower()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t[:10], fmt).date()
        except ValueError:
            pass
    meses = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10,
             "nov": 11, "dic": 12}
    partes = t.replace(" ", "-").split("-")
    if len(partes) >= 2 and partes[0].isdigit() and partes[1][:3] in meses:
        y = (ref or date.today()).year
        d = date(y, meses[partes[1][:3]], int(partes[0]))
        if ref and d < ref - timedelta(days=180):
            d = date(y + 1, d.month, d.day)
        return d
    raise BusinessError(f"Fecha no reconocida: {v}.")


def save(user, datos, f=None):
    _req(user)
    contrato = (datos.get("contrato") or "").strip()
    proveedor = (datos.get("proveedor") or "").strip()
    item = (datos.get("item") or "").strip()
    if not (contrato and proveedor and item):
        raise BusinessError("Indique contrato, proveedor e ítem.")
    nuevo = f is None
    if f is None:
        f = ImportFollowup(contrato=contrato, proveedor=proveedor, item=item, user_id=user.id)
        db().add(f)
    antes = {"llegada": f.fecha_llegada, "retiro": f.retiro_fecha, "senasa": f.status_senasa, "bl": f.status_bl}
    f.codigo_sap = (datos.get("codigo_sap") or "POR CONFIRMAR").strip().upper()[:40]
    f.contrato, f.proveedor, f.item = contrato[:60], proveedor[:160], item.upper()[:160]
    f.pais_origen = (datos.get("pais_origen") or "").strip().upper()[:60]
    f.contenedores = int(float(datos.get("contenedores") or 1))
    f.kg = float(datos["kg"]) if datos.get("kg") not in (None, "") else f.kg
    f.fecha_llegada = _fecha(datos.get("fecha_llegada"))
    f.dias_libres = int(float(datos.get("dias_libres") or 0))
    f.status_senasa = (datos.get("status_senasa") or "PENDIENTE").strip().upper()[:60]
    f.status_bl = (datos.get("status_bl") or "PENDIENTE DE LIBERACIÓN DE BL").strip().upper()[:80]
    f.retiro_fecha = _fecha(datos.get("retiro_fecha"), f.fecha_llegada)
    f.retiro_real = str(datos.get("retiro_real", "")) in ("1", "on", "true", "REAL")
    f.almacen_info = (datos.get("almacen_info") or "PENDIENTE").strip()[:160]
    for k in ("precio", "penalidad_dia", "sobreestadia_dia"):
        if datos.get(k) not in (None, ""):
            setattr(f, k, float(str(datos[k]).replace(",", ".")))
    if datos.get("moneda"):
        f.moneda = datos["moneda"].strip().upper()[:5]
    if datos.get("um"):
        f.um = datos["um"].strip().upper()[:20]
    if datos.get("fecha_entrega_contrato") not in (None, ""):
        f.fecha_entrega_contrato = _fecha(datos.get("fecha_entrega_contrato"))
    if datos.get("contrato_archivo"):
        f.contrato_archivo = datos["contrato_archivo"]
    f.estado = ("RETIRADO" if f.retiro_real else
                ("EN_PUERTO" if f.fecha_llegada and f.fecha_llegada <= date.today() else "EN_TRANSITO"))
    if datos.get("estado") in ESTADOS:
        f.estado = datos["estado"]
    db().flush()
    despues = {"llegada": f.fecha_llegada, "retiro": f.retiro_fecha, "senasa": f.status_senasa, "bl": f.status_bl}
    cambios = {k: str(v) for k, v in antes.items() if v != despues[k]}
    # V28: historial con día y hora de cada cambio de status (SENASA, BL, llegada y retiro)
    if not nuevo and cambios:
        from ..models import now as _now
        hist = list(f.historial_status or [])
        etiq = {"senasa": "SENASA", "bl": "BL", "llegada": "Llegada", "retiro": "Retiro"}
        for k in cambios:
            de, a = antes[k], despues[k]
            hist.append({"campo": etiq[k], "de": de.strftime("%d/%m/%Y") if hasattr(de, "strftime") else (de or ""),
                         "a": a.strftime("%d/%m/%Y") if hasattr(a, "strftime") else (a or ""),
                         "ts": _now().isoformat(timespec="minutes"), "user": user.nombre})
        f.historial_status = hist
    audit(user, "IMPORTACION_SEGUIMIENTO", "ImportFollowup", f.id, {"nuevo": nuevo, "cambios": cambios})
    if not nuevo and "llegada" in cambios and antes["llegada"] and f.fecha_llegada and f.fecha_llegada > antes["llegada"]:
        alerts.emit("IMPORT_RETRASO", f"{f.item} ({f.contrato}): la llegada se movió al {f.fecha_llegada:%d/%m}",
                    f"Antes {antes['llegada']:%d/%m/%Y}. Proveedor {f.proveedor}.", "ImportFollowup", f.id,
                    dedup_key=f"IMPLLEG:{f.id}:{f.fecha_llegada}", creado_por=user)
    return f


def add_expense(user, f, tipo, monto, moneda="USD", detalle="", archivo="", fecha=None):
    _req(user)
    if tipo not in TIPOS_GASTO:
        raise BusinessError("Tipo de gasto no válido.")
    try:
        monto = float(str(monto).replace(",", "."))
    except ValueError:
        raise BusinessError("Monto inválido.") from None
    if monto <= 0:
        raise BusinessError("Monto inválido.")
    g = list(f.gastos or [])
    g.append({"tipo": tipo, "monto": monto, "moneda": (moneda or "USD").upper(), "detalle": (detalle or "").strip(),
              "archivo": archivo, "fecha": (fecha or date.today()).isoformat(), "user": user.nombre})
    f.gastos = g
    if tipo in ("Sobreestadía", "Devolución tarde de contenedor"):
        alerts.emit("IMPORT_PENALIDAD", f"Gasto en contra: {tipo.lower()} en {f.item} ({f.contrato})",
                    f"{monto:,.2f} {moneda}. {detalle}".strip(), "ImportFollowup", f.id,
                    dedup_key=f"IMPGAS:{f.id}:{len(g)}", creado_por=user)
    audit(user, "IMPORTACION_GASTO", "ImportFollowup", f.id, g[-1])
    return f


def add_incident(user, f, tipo, detalle):
    _req(user)
    detalle = (detalle or "").strip()
    if not detalle:
        raise BusinessError("Describa el inconveniente.")
    inc = list(f.incidencias or [])
    inc.append({"tipo": (tipo or "Otro").strip(), "detalle": detalle, "fecha": date.today().isoformat(), "user": user.nombre})
    f.incidencias = inc
    alerts.emit("IMPORT_INCIDENCIA", f"{tipo or 'Inconveniente'} en {f.item} ({f.contrato})", detalle, "ImportFollowup", f.id,
                dedup_key=f"IMPINC:{f.id}:{len(inc)}", creado_por=user)
    audit(user, "IMPORTACION_INCIDENCIA", "ImportFollowup", f.id, inc[-1])
    return f


TIPOS_DOC = {"CERTIFICADO_ORIGEN": "Certificado de origen", "FITOSANITARIO": "Certificado fitosanitario",
             "PACKING_LIST": "Packing list", "CALIDAD": "Certificado de calidad", "FUMIGACION": "Certificado de fumigación",
             "OTRO": "Otro"}


def add_document(user, f, tipo, archivo, nombre="", nota=""):
    """V25: Importaciones sube los documentos de la importación (uno o varios por tipo)."""
    _req(user)
    if tipo not in TIPOS_DOC:
        raise BusinessError("Tipo de documento no válido.")
    if not archivo:
        raise BusinessError("Adjunte el documento.")
    if tipo == "OTRO" and not (nombre or "").strip():
        raise BusinessError("Indique qué documento es.")
    docs = list(f.documentos or [])
    docs.append({"tipo": tipo, "archivo": archivo, "nombre": (nombre or "").strip() or TIPOS_DOC[tipo],
                 "nota": (nota or "").strip(), "fecha": date.today().isoformat(), "user": user.nombre})
    f.documentos = docs
    audit(user, "IMPORTACION_DOCUMENTO", "ImportFollowup", f.id, docs[-1])
    return f


def missing_documents(f):
    """Documentos obligatorios que aún no se suben (todos menos «Otro»)."""
    tiene = {d.get("tipo") for d in (f.documentos or [])}
    return [n for k, n in TIPOS_DOC.items() if k != "OTRO" and k not in tiene]


def upload_quality_report(user, f, archivo, nota=""):
    """V25: Calidad sube el informe de recepción de la importación en PDF (la otra opción es generarlo con REG-CAL-005)."""
    from .core import has_perm
    if not has_perm(user, "calidad.registrar"):
        raise BusinessError("El informe de recepción lo registra Calidad.")
    if not archivo:
        raise BusinessError("Adjunte el informe en PDF.")
    if not archivo.lower().endswith(".pdf"):
        raise BusinessError("El informe debe ser un PDF.")
    f.informe_calidad = {"modo": "PDF", "archivo": archivo, "nota": (nota or "").strip(), "user": user.nombre,
                         "ts": datetime.now().isoformat(timespec="minutes")}
    _avisar_informe(f, user)
    audit(user, "IMPORTACION_INFORME_CALIDAD", "ImportFollowup", f.id, f.informe_calidad)
    return f


def link_quality_record(f, rec, user):
    """V25: el informe generado con el formato REG-CAL-005 queda vinculado a la importación."""
    f.informe_calidad = {"modo": "GENERADO", "record_id": rec.id, "resultado": rec.resultado, "user": user.nombre,
                         "ts": datetime.now().isoformat(timespec="minutes")}
    _avisar_informe(f, user)


def _avisar_informe(f, user):
    alerts.emit("IMPORT_INFORME_CALIDAD", f"Informe de recepción de Calidad: {f.item} ({f.contrato})",
                ("Resultado: " + f.informe_calidad.get("resultado") + ". ") if f.informe_calidad.get("resultado") else
                "Informe en PDF subido por Calidad.", "ImportFollowup", f.id, dedup_key=f"IMPINF:{f.id}:{f.informe_calidad.get('ts')}",
                creado_por=user)


def total_gastos(f, tc=None):
    """Gastos extra en USD (los en S/ se convierten con el TC)."""
    from .tipo_cambio import rate
    tc = tc or rate()
    t = 0.0
    for g in f.gastos or []:
        m = float(g.get("monto") or 0)
        t += m / tc if (g.get("moneda") or "USD") in ("PEN", "S/") and tc else m
    return round(t, 2)


def estado(f, hoy=None):
    """Lectura de cada fila: días para el retiro, semáforo, riesgo de sobreestadía y penalidad a favor."""
    hoy = hoy or date.today()
    fmax = fecha_max_retiro(f)
    dias = (fmax - hoy).days if fmax else None
    retirado = f.retiro_real or f.estado in ("RETIRADO", "CERRADO")
    costo_dia = f.sobreestadia_dia if f.sobreestadia_dia is not None else float(param("import_sobreestadia_usd_dia", 0) or 0)
    sobre = 0
    if fmax and not retirado and hoy > fmax:
        sobre = (hoy - fmax).days
    elif fmax and f.retiro_fecha and f.retiro_fecha > fmax:
        sobre = (f.retiro_fecha - fmax).days
    riesgo = round(sobre * (f.contenedores or 1) * costo_dia, 2) if costo_dia else None
    a_favor = None
    if f.fecha_entrega_contrato and f.fecha_llegada and f.fecha_llegada > f.fecha_entrega_contrato and f.penalidad_dia:
        a_favor = round((f.fecha_llegada - f.fecha_entrega_contrato).days * f.penalidad_dia, 2)
    pend = [x for x, v in (("SENASA", f.status_senasa), ("BL", f.status_bl)) if "PENDIENTE" in (v or "").upper()]
    if retirado:
        sem = "ok"
    elif dias is not None and dias < 0:
        sem = "err"
    elif dias is not None and dias <= max(param("import_alerta_retiro_dias", [5, 2, 0]) or [5]):
        sem = "warn"
    elif f.retiro_fecha and fmax and f.retiro_fecha > fmax:
        sem = "warn"
    else:
        sem = ""
    return {"fmax": fmax, "dias_retiro": dias, "semaforo": sem, "sobreestadia_dias": sobre, "riesgo_sobreestadia": riesgo,
            "penalidad_a_favor": a_favor, "pendientes": pend, "retirado": retirado, "gastos": total_gastos(f)}


def board(hoy=None, incluir_cerradas=False):
    q = select(ImportFollowup).order_by(ImportFollowup.fecha_llegada, ImportFollowup.id)
    if not incluir_cerradas:
        q = q.where(ImportFollowup.estado != "CERRADO")
    filas = [{"f": f, **estado(f, hoy)} for f in db().execute(q).scalars()]
    tot = {"contenedores": sum(x["f"].contenedores or 0 for x in filas),
           "por_retirar": sum(1 for x in filas if not x["retirado"]),
           "en_riesgo": sum(1 for x in filas if x["semaforo"] in ("warn", "err")),
           "sobreestadia": sum(1 for x in filas if x["sobreestadia_dias"]),
           "gastos_usd": round(sum(x["gastos"] for x in filas), 2),
           "riesgo_usd": round(sum(x["riesgo_sobreestadia"] or 0 for x in filas), 2),
           "a_favor_usd": round(sum(x["penalidad_a_favor"] or 0 for x in filas), 2)}
    return {"filas": filas, "tot": tot}


def check_alerts(hoy=None):
    """Tarea diaria: retiro próximo, sobreestadía, trámites pendientes con la carga en puerto y penalidad a favor."""
    hoy = hoy or date.today()
    avisos = set(int(x) for x in (param("import_alerta_retiro_dias", [5, 2, 0]) or []))
    n = 0
    for x in board(hoy)["filas"]:
        f = x["f"]
        if x["retirado"]:
            continue
        if x["dias_retiro"] is not None and x["dias_retiro"] in avisos:
            alerts.emit("IMPORT_RETIRO_PROXIMO", f"{f.item} ({f.contrato}): {x['dias_retiro']} día(s) para el retiro máximo",
                        f"Fecha máxima {x['fmax']:%d/%m/%Y}; {f.contenedores} contenedor(es). SENASA: {f.status_senasa}. "
                        f"BL: {f.status_bl}.", "ImportFollowup", f.id, dedup_key=f"IMPRET:{f.id}:{x['dias_retiro']}")
            n += 1
        if x["dias_retiro"] is not None and x["dias_retiro"] < 0:
            alerts.emit("IMPORT_SOBREESTADIA", f"{f.item} ({f.contrato}): {x['sobreestadia_dias']} día(s) de sobreestadía",
                        f"Venció el {x['fmax']:%d/%m/%Y}." + (f" Costo estimado: USD {x['riesgo_sobreestadia']:,.2f}."
                                                              if x["riesgo_sobreestadia"] else ""),
                        "ImportFollowup", f.id, dedup_key=f"IMPSOB:{f.id}:{hoy.isocalendar()[1]}")
            n += 1
        if f.fecha_llegada and f.fecha_llegada <= hoy and x["pendientes"]:
            alerts.emit("IMPORT_RETRASO", f"{f.item} ({f.contrato}) en puerto con {' y '.join(x['pendientes'])} pendiente",
                        f"Llegó el {f.fecha_llegada:%d/%m}; fecha máxima de retiro {x['fmax']:%d/%m}.", "ImportFollowup", f.id,
                        dedup_key=f"IMPPEN:{f.id}:{'-'.join(x['pendientes'])}")
            n += 1
        if x["penalidad_a_favor"]:
            alerts.emit("IMPORT_PENALIDAD", f"Posible penalidad A FAVOR: {f.proveedor} entregó tarde ({f.contrato})",
                        f"Pactado {f.fecha_entrega_contrato:%d/%m}, llegada {f.fecha_llegada:%d/%m}: "
                        f"{f.moneda} {x['penalidad_a_favor']:,.2f} según el contrato.", "ImportFollowup", f.id,
                        dedup_key=f"IMPFAV:{f.id}")
            n += 1
    return n


def import_excel(user, path):
    """Carga el cuadro con las columnas de Importaciones. Si el contrato ya existe, lo actualiza."""
    from openpyxl import load_workbook
    _req(user)
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    filas = list(ws.iter_rows(values_only=True))
    cab_i = next((i for i, r in enumerate(filas[:10]) if r and any(str(c or "").strip().upper() == "CONTRATO" for c in r)), None)
    if cab_i is None:
        raise BusinessError("No se encontró la cabecera (columna CONTRATO).")

    def norm(t):
        return " ".join(str(t or "").upper().replace("Í", "I").replace("Ó", "O").replace("Á", "A").replace("É", "E").split())
    cab = [norm(c) for c in filas[cab_i]]

    def col(*claves):
        for i, c in enumerate(cab):
            if any(k in c for k in claves):
                return i
        return None
    idx = {"codigo_sap": col("CODIGO SAP"), "contrato": col("CONTRATO"), "proveedor": col("PROVEEDOR"), "item": col("ITEM"),
           "pais_origen": col("PAIS"), "contenedores": col("CONTENEDOR"), "fecha_llegada": col("FECHA DE LLEGADA"),
           "dias_libres": col("DIAS LIBRES"), "status_senasa": col("SENASA"), "status_bl": col("BL"),
           "retiro_fecha": col("RETIRO("), "almacen_info": col("ALMACEN")}
    nuevos = act = 0
    for r in filas[cab_i + 1:]:
        if not r or not any(r):
            continue
        datos = {k: (r[i] if i is not None and i < len(r) else None) for k, i in idx.items()}
        if not datos.get("contrato"):
            continue
        datos = {k: (v if not isinstance(v, str) else v.strip()) for k, v in datos.items()}
        datos["contrato"] = str(datos["contrato"])
        f = db().execute(select(ImportFollowup).where(ImportFollowup.contrato == datos["contrato"])).scalars().first()
        if f is not None:
            for k in ("precio", "penalidad_dia", "sobreestadia_dia", "fecha_entrega_contrato", "moneda", "um"):
                datos.setdefault(k, getattr(f, k))
        save(user, datos, f)
        nuevos += f is None
        act += f is not None
    return nuevos, act


def excel(hoy=None):
    """Excel del cuadro con las mismas columnas (más semáforo, gastos y penalidades)."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    d = board(hoy)
    wb = Workbook()
    ws = wb.active
    ws.title = "Importaciones"
    ws.append(COLUMNAS_EXCEL + ["SEMÁFORO", "GASTOS EXTRA USD", "RIESGO SOBREESTADÍA USD", "PENALIDAD A FAVOR"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3864")
    colores = {"err": "F8D7DA", "warn": "FFF3CD", "ok": "D4EDDA"}
    for x in d["filas"]:
        f = x["f"]
        ws.append([f.codigo_sap, f.contrato, f.proveedor, f.item, f.pais_origen, f.contenedores, f.fecha_llegada,
                   f.dias_libres, x["fmax"], f.status_senasa, f.status_bl,
                   (f"{f.retiro_fecha:%d-%m}" + ("" if f.retiro_real else " (tentativa)")) if f.retiro_fecha else "",
                   f.almacen_info, {"err": "VENCIDO", "warn": "POR VENCER", "ok": "RETIRADO"}.get(x["semaforo"], ""),
                   x["gastos"], x["riesgo_sobreestadia"] or 0, x["penalidad_a_favor"] or 0])
        if x["semaforo"] in colores:
            for c in ws[ws.max_row]:
                c.fill = PatternFill("solid", fgColor=colores[x["semaforo"]])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def precios_importado_vs_nacional():
    """Por producto (código SAP): costo importado en S/ por kg (precio + gastos prorrateados, con TC) vs el promedio de
    las cotizaciones nacionales de los últimos 90 días."""
    from .compras_v24 import precio_soles, quotes
    from .tipo_cambio import rate
    tc = rate()
    por = defaultdict(lambda: {"imp": [], "nac": []})
    for f in db().execute(select(ImportFollowup).where(ImportFollowup.precio.isnot(None))).scalars():
        if not f.codigo_sap or f.codigo_sap == "POR CONFIRMAR" or not tc:
            continue
        um = (f.um or "TM").upper()
        factor = 1000 if um in ("TM", "T", "TON") else 1
        kg = f.kg or 0  # sin kg registrados no se prorratean los gastos extra
        precio_kg = f.precio / factor
        extra_kg = (total_gastos(f, tc) / kg) if kg else 0
        mon = 1 if (f.moneda or "USD") in ("PEN", "S/") else tc
        por[f.codigo_sap]["imp"].append((precio_kg + extra_kg) * mon)
    desde = date.today() - timedelta(days=90)
    for code in list(por):
        for q in quotes(code):
            if q.fecha >= desde and (q.um or "").upper() in ("KG", "KILOGRAMO"):
                ps = precio_soles(q)
                if ps:
                    por[code]["nac"].append(ps)
    filas = []
    for code, v in sorted(por.items()):
        p = db().get(Product, code)
        imp = sum(v["imp"]) / len(v["imp"]) if v["imp"] else None
        nac = sum(v["nac"]) / len(v["nac"]) if v["nac"] else None
        filas.append({"code": code, "descripcion": p.descripcion if p else "", "importado_kg": round(imp, 3) if imp else None,
                      "nacional_kg": round(nac, 3) if nac else None,
                      "dif_pct": round(100 * (imp - nac) / nac, 1) if imp and nac else None,
                      "conviene": ("Nacional" if imp and nac and nac < imp else "Importado" if imp and nac else "—")})
    return {"tc": tc, "filas": filas}



# ------------------------------------------------------------------ V28 (11-nov-2026): retrasos
CAMPOS_RETRASO = {"SENASA": "SENASA", "BL": "Liberación de BL", "LLEGADA": "Llegada del buque / naviera",
                  "RETIRO": "Retiro del contenedor", "OTRO": "Otro"}


def register_delay(user, f, campo, motivo, fecha_nueva):
    """Importaciones registra un retraso (de SENASA, del BL, de la naviera…): motivo y fecha modificada. Si la nueva
    fecha pasa la fecha máxima de retiro, se avisa el riesgo de sobreestadía."""
    from ..models import now as _now
    _req(user)
    campo = (campo or "").upper()
    if campo not in CAMPOS_RETRASO:
        raise BusinessError("Indique qué se retrasó.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise BusinessError("Indique el motivo del retraso.")
    nueva = _fecha(fecha_nueva) if fecha_nueva not in (None, "") else None
    if nueva is None:
        raise BusinessError("Indique la fecha modificada (nueva fecha estimada).")
    antes = None
    if campo == "LLEGADA":
        antes, f.fecha_llegada = f.fecha_llegada, nueva
    elif campo == "RETIRO":
        antes, f.retiro_fecha, f.retiro_real = f.retiro_fecha, nueva, False
    r = {"campo": campo, "nombre": CAMPOS_RETRASO[campo], "motivo": motivo,
         "fecha_antes": antes.isoformat() if antes else "", "fecha_nueva": nueva.isoformat(),
         "ts": _now().isoformat(timespec="minutes"), "user": user.nombre}
    f.retrasos = list(f.retrasos or []) + [r]
    hist = list(f.historial_status or [])
    hist.append({"campo": f"Retraso · {CAMPOS_RETRASO[campo]}", "de": antes.strftime("%d/%m/%Y") if antes else "",
                 "a": nueva.strftime("%d/%m/%Y"), "ts": r["ts"], "user": user.nombre, "motivo": motivo})
    f.historial_status = hist
    fmax = fecha_max_retiro(f)
    riesgo = bool(fmax and nueva > fmax and campo in ("SENASA", "BL", "RETIRO", "OTRO"))
    alerts.emit("IMPORT_RETRASO", f"{f.item} ({f.contrato}): retraso de {CAMPOS_RETRASO[campo].lower()} al {nueva:%d/%m}",
                f"Motivo: {motivo}." + (f" Fecha anterior {antes:%d/%m/%Y}." if antes else "")
                + (f" Supera la fecha máxima de retiro ({fmax:%d/%m/%Y}): riesgo de sobreestadía." if riesgo else ""),
                "ImportFollowup", f.id, creado_por=user, prioridad="ALTA" if riesgo else None,
                dedup_key=f"IMPRETRASO:{f.id}:{campo}:{nueva.isoformat()}")
    audit(user, "IMPORTACION_RETRASO", "ImportFollowup", f.id, r)
    return f
