"""V74 (25-nov-2026): pedidos de Calidad.

- Especificaciones por producto: Calidad ve los archivos del producto que ya están en la base de datos (carpeta del
  producto: ficha técnica, especificaciones de calidad y certificados) y sube o actualiza las especificaciones en PDF o
  Excel. Del Excel se muestra la primera hoja en pantalla, para leerla sin descargarla.
- Referencia de los certificados por tipo de producto: la tabla «palabra del producto → norma de referencia» la
  mantiene Calidad (parámetro «referencias_ntp»). El certificado la toma sola.
- Informe de recepción de Calidad en Abastecimiento: compras nacionales (sobre la compra) e importaciones.
- Controles de Calidad en el proceso en tiempo real: la Jefatura, la Supervisión y el Asistente de Calidad registran
  en el parte en curso el parámetro controlado, el valor y si está conforme.
"""
import os
import uuid

from sqlalchemy import select

from ..db import db
from ..models import ImportFollowup, ProductDocument, ProductionReport, PurchaseRequest, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

EXT_ESPEC = (".pdf", ".xlsx", ".xls")
CARPETAS_CALIDAD = {"ESPECIFICACIONES": "Especificaciones de calidad", "FICHA_TECNICA": "Ficha técnica",
                    "CERTIFICADOS": "Certificados"}


def guardar_archivo(fs, upload_dir, prefijo, exts=EXT_ESPEC):
    if fs is None or not getattr(fs, "filename", ""):
        return "", ""
    ext = os.path.splitext(fs.filename)[1].lower()
    if ext not in exts:
        raise BusinessError(f"{fs.filename}: use PDF o Excel ({', '.join(e.strip('.') for e in exts)}).")
    os.makedirs(upload_dir, exist_ok=True)
    name = f"{prefijo}_{uuid.uuid4().hex[:10]}{ext}"
    fs.save(os.path.join(upload_dir, name))
    return name, os.path.basename(fs.filename)[:200]


# ------------------------------------------------------------------ especificaciones por producto
def documentos(product_code):
    """Archivos vigentes del producto en las carpetas que usa Calidad, del más reciente al más antiguo."""
    out = {k: [] for k in CARPETAS_CALIDAD}
    for d in db().execute(select(ProductDocument).where(ProductDocument.product_code == product_code,
                                                        ProductDocument.vigente.is_(True),
                                                        ProductDocument.carpeta.in_(list(CARPETAS_CALIDAD)))
                          .order_by(ProductDocument.ts.desc())).scalars():
        out[d.carpeta].append(d)
    return out


def con_especificacion():
    """Códigos de producto con al menos un archivo de especificación o ficha técnica vigente."""
    return set(db().execute(select(ProductDocument.product_code).where(
        ProductDocument.vigente.is_(True), ProductDocument.carpeta.in_(["ESPECIFICACIONES", "FICHA_TECNICA"]))).scalars())


def subir(user, product, carpeta, archivos, reemplazar=False):
    """archivos: [(archivo_guardado, nombre_original)]. reemplazar=True retira los vigentes de esa carpeta (actualizar)."""
    if not has_perm(user, "calidad.especificaciones"):
        raise BusinessError("Suben o actualizan las especificaciones la Jefatura y la Supervisión de Calidad.")
    if carpeta not in CARPETAS_CALIDAD:
        raise BusinessError("Carpeta no válida.")
    archivos = [a for a in archivos if a and a[0]]
    if not archivos:
        raise BusinessError("Adjunte el archivo (PDF o Excel).")
    retirados = 0
    if reemplazar:
        for d in documentos(product.code)[carpeta]:
            d.vigente = False
            retirados += 1
    nuevos = []
    for arch, nombre in archivos:
        d = ProductDocument(product_code=product.code, carpeta=carpeta, nombre=nombre or arch, archivo=arch, user_id=user.id)
        db().add(d)
        nuevos.append(d)
    db().flush()
    audit(user, "ESPECIFICACION_CALIDAD", "Product", product.code,
          {"carpeta": carpeta, "archivos": [d.archivo for d in nuevos], "reemplazo": retirados})
    return nuevos, retirados


def retirar(user, doc):
    if not has_perm(user, "calidad.especificaciones"):
        raise BusinessError("Retiran archivos la Jefatura y la Supervisión de Calidad.")
    if doc.carpeta not in CARPETAS_CALIDAD:
        raise BusinessError("Ese archivo no es de Calidad.")
    doc.vigente = False
    audit(user, "ESPECIFICACION_RETIRADA", "Product", doc.product_code, {"archivo": doc.archivo})


def vista_excel(path, max_filas=40, max_cols=14):
    """Primera hoja del Excel como tabla (lo que se ve en pantalla). Devuelve (hoja, filas) o (None, [])."""
    if not path or not os.path.exists(path) or not path.lower().endswith((".xlsx", ".xlsm")):
        return None, []
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        filas = []
        for row in ws.iter_rows(max_row=max_filas, max_col=max_cols, values_only=True):
            vals = ["" if v is None else (v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v)) for v in row]
            if any(x.strip() for x in vals):
                filas.append(vals)
        wb.close()
        # quita las columnas vacías del final
        ancho = max((max((i for i, v in enumerate(f) if v.strip()), default=-1) for f in filas), default=-1) + 1
        return ws.title, [f[:ancho] for f in filas]
    except Exception:  # noqa: BLE001 — un Excel dañado no debe romper la pantalla; se descarga igual
        return None, []


# ------------------------------------------------------------------ referencias de los certificados
def referencias():
    return dict(param("referencias_ntp", {}) or {})


def guardar_referencias(user, filas):
    """filas: [(tipo de producto / palabra, referencia)]. Reemplaza la tabla completa."""
    if not has_perm(user, "calidad.certificado_revisar"):
        raise BusinessError("La tabla de referencias la mantiene Calidad (Jefatura o Supervisión).")
    nueva = {}
    for k, v in filas:
        k, v = (k or "").strip().upper(), (v or "").strip()
        if not k and not v:
            continue
        if not k or not v:
            raise BusinessError("Cada fila necesita el tipo de producto y su referencia.")
        if k in nueva:
            raise BusinessError(f"El tipo {k} está repetido.")
        nueva[k] = v
    from .core import set_param
    set_param("referencias_ntp", nueva, user)
    return nueva


# ------------------------------------------------------------------ informe de recepción (compras nacionales)
ESTADOS_RECIBIDA = ("ORDEN_GENERADA", "RECIBIDA", "RECIBIDA_CON_DIFERENCIAS", "RECIBIDA_BAJO_OBSERVACION", "CERRADA")


def compras_para_informe(limite=150):
    return list(db().execute(select(PurchaseRequest).where(PurchaseRequest.estado.in_(ESTADOS_RECIBIDA))
                             .order_by(PurchaseRequest.id.desc()).limit(limite)).scalars())


def importaciones_para_informe(limite=150):
    return list(db().execute(select(ImportFollowup).order_by(ImportFollowup.id.desc()).limit(limite)).scalars())


def informe_compra(pr):
    return (pr.analisis or {}).get("informe_calidad") or {}


def subir_informe_compra(user, pr, archivo, nombre="", nota="", resultado=""):
    if not has_perm(user, "calidad.registrar"):
        raise BusinessError("El informe de recepción lo registra Calidad.")
    if not archivo:
        raise BusinessError("Adjunte el informe (PDF o Excel).")
    resultado = (resultado or "").upper()
    if resultado not in ("", "CONFORME", "NO_CONFORME", "OBSERVADO"):
        raise BusinessError("Resultado no válido.")
    an = dict(pr.analisis or {})
    hist = list(an.get("informes_calidad") or [])
    inf = {"archivo": archivo, "nombre": nombre or archivo, "nota": (nota or "").strip(), "resultado": resultado,
           "user": user.nombre, "ts": now().isoformat(timespec="minutes")}
    hist.append(inf)
    an["informes_calidad"], an["informe_calidad"] = hist, inf
    pr.analisis = an
    alerts.emit("COMPRA_INFORME_CALIDAD", f"Informe de recepción de Calidad: compra #{pr.id} ({pr.product_code})",
                (f"Resultado: {resultado.replace('_', ' ').lower()}. " if resultado else "") + (inf["nota"] or "Informe subido por Calidad."),
                "PurchaseRequest", pr.id, creado_por=user, dedup_key=f"COMPINF:{pr.id}:{inf['ts']}")
    audit(user, "COMPRA_INFORME_CALIDAD", "PurchaseRequest", pr.id, inf)
    return inf


# ------------------------------------------------------------------ controles de Calidad en el proceso
def parametros_sugeridos():
    return list(param("calidad_parametros_proceso", []) or [])


def registrar_control(user, rep, parametro, valor="", conforme=True, observacion=""):
    if not has_perm(user, "calidad.registrar"):
        raise BusinessError("Registra los controles del proceso Calidad.")
    if rep.estado not in ("EN PROCESO", "PAUSADO", "PROGRAMADO"):
        raise BusinessError("El parte ya terminó: el control se registra mientras el proceso está en curso.")
    parametro = (parametro or "").strip()
    if not parametro:
        raise BusinessError("Indique qué se controló (parámetro).")
    observacion = (observacion or "").strip()
    if not conforme and not observacion:
        raise BusinessError("Indique qué está fuera de lo esperado (no conforme).")
    lst = list(rep.controles_calidad or [])
    c = {"n": len(lst) + 1, "parametro": parametro[:80], "valor": (str(valor or "")).strip()[:60], "conforme": bool(conforme),
         "observacion": observacion[:300], "user": user.nombre, "rol": user.role.nombre if user.role else "",
         "ts": now().isoformat(timespec="minutes")}
    lst.append(c)
    rep.controles_calidad = lst
    if not conforme:
        alerts.emit("CALIDAD_CONTROL_PROCESO", f"Control de Calidad no conforme: {rep.linea} {rep.product_code}",
                    f"{parametro}{(' = ' + c['valor']) if c['valor'] else ''}: {observacion} ({user.nombre}).",
                    "ProductionReport", rep.id, prioridad="ALTA", creado_por=user)
    audit(user, "CALIDAD_CONTROL_PROCESO", "ProductionReport", rep.id, c)
    return c


def partes_en_curso():
    return list(db().execute(select(ProductionReport).where(ProductionReport.estado.in_(("EN PROCESO", "PAUSADO")))
                             .order_by(ProductionReport.linea)).scalars())


# ------------------------------------------------------------------ certificados: detalle del picking
def picking_de_certificado(c):
    """Lo despachado que corresponde al certificado: lo registrado en el picking (formato de control de despacho) de la
    OV del certificado o, si no tiene OV, del mismo producto y lote. Solo lectura para Calidad."""
    from ..models import PickingRecord, PickingTask, SalesOrderLine, StockLot
    lote = ((c.datos or {}).get("lote") or "").strip()
    if not lote and c.lot_id:
        lot = db().get(StockLot, c.lot_id)
        lote = lot.lote if lot else ""
    q = select(PickingRecord).join(SalesOrderLine, PickingRecord.line_id == SalesOrderLine.id)
    if c.order_id:
        q = q.where(PickingRecord.order_id == c.order_id)
    elif lote:
        q = q.where(PickingRecord.lote == lote, SalesOrderLine.product_code == c.product_code)
    else:
        return {"registros": [], "tareas": [], "lote": lote}
    regs = list(db().execute(q.order_by(PickingRecord.ts.desc()).limit(100)).scalars())
    ids = sorted({r.task_id for r in regs if r.task_id} | set(
        db().execute(select(PickingTask.id).where(PickingTask.order_id == c.order_id)).scalars() if c.order_id else set()))
    tareas = [db().get(PickingTask, i) for i in ids]
    return {"registros": regs, "tareas": [t for t in tareas if t is not None], "lote": lote}
