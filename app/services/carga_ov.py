"""V64 (marcha blanca comercial, 20-nov-2026): carga masiva de OV con la plantilla homologada del módulo.

- La plantilla (Excel o CSV) tiene una fila por producto; las filas con el mismo cliente, N° de OC y fecha comprometida
  forman una OV. Así la pueden llenar a mano, con una macro o con la IA (que entrega un CSV).
- Cada OV se registra igual que en el formulario (mismas validaciones: cliente, fecha, corte, precio mínimo, IGV por
  línea, total de la OC). Sin el archivo de la OC queda en BORRADOR hasta adjuntarla (la OC es obligatoria).
- Mientras el módulo está en prueba, la OV cargada NO se envía a SAP hasta que alguien de Comercial la revise y la valide
  («Validar y enviar a SAP» en la OV), para confirmar que la carga tomó bien los datos.
- Si el cliente usa sus propios códigos, «homologacion_sku_cliente» ({RUC: {código del cliente: código nuestro}}) los
  convierte; la tabla de homologación la entrega Comercial.
"""
import csv
import io
import os
from collections import OrderedDict
from datetime import date, datetime

from sqlalchemy import select

from ..db import db
from ..models import Customer, SalesOrder, now
from .core import BusinessError, audit, has_perm, param

COLUMNAS = ["RUC del cliente", "N° de OC", "Total de la OC (con IGV)", "Fecha comprometida (dd/mm/aaaa)", "Canal",
            "Modalidad (ENTREGA o RECOJO)", "Hora de cita", "Código del producto", "Código del cliente (opcional)",
            "Cantidad", "Precio unitario sin IGV", "IGV (AFECTO o EXONERADO)", "Ejecutivo comercial", "Comentario"]
_ALIAS = {
    "ruc": ("RUC DEL CLIENTE", "RUC", "CLIENTE RUC", "DOCUMENTO"),
    "oc": ("N° DE OC", "NRO OC", "N° OC", "OC", "ORDEN DE COMPRA", "NUMATCARD"),
    "oc_total": ("TOTAL DE LA OC (CON IGV)", "TOTAL OC", "TOTAL DE LA OC"),
    "fecha": ("FECHA COMPROMETIDA (DD/MM/AAAA)", "FECHA COMPROMETIDA", "FECHA DE ENTREGA", "FECHA ENTREGA"),
    "canal": ("CANAL",),
    "modalidad": ("MODALIDAD (ENTREGA O RECOJO)", "MODALIDAD"),
    "hora": ("HORA DE CITA", "HORA CITA", "CITA"),
    "codigo": ("CÓDIGO DEL PRODUCTO", "CODIGO DEL PRODUCTO", "CÓDIGO", "CODIGO", "SKU", "ITEMCODE"),
    "codigo_cliente": ("CÓDIGO DEL CLIENTE (OPCIONAL)", "CODIGO DEL CLIENTE", "SKU CLIENTE", "CÓDIGO DEL CLIENTE"),
    "cantidad": ("CANTIDAD",),
    "precio": ("PRECIO UNITARIO SIN IGV", "PRECIO UNITARIO", "PRECIO"),
    "igv": ("IGV (AFECTO O EXONERADO)", "IGV", "IMPUESTO", "TAXCODE"),
    "ejecutivo": ("EJECUTIVO COMERCIAL", "EJECUTIVO", "VENDEDOR"),
    "comentario": ("COMENTARIO", "COMENTARIOS", "OBSERVACIÓN"),
}


def plantilla():
    """Excel vacío con las columnas de la plantilla y una hoja de instrucciones (sin datos reales)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "OV"
    ws.append(COLUMNAS)
    ins = wb.create_sheet("Instrucciones")
    for t in ["Una fila por producto. Las filas con el mismo RUC, N° de OC y fecha comprometida forman una OV.",
              "Fecha comprometida: dd/mm/aaaa. Modalidad: ENTREGA (a la dirección fiscal del cliente) o RECOJO.",
              "Cantidad en la unidad del producto (kilos para granel y MP; unidades para PT). Precio sin IGV.",
              "IGV: AFECTO o EXONERADO (vacío: el último usado para el producto).",
              "Sin el archivo de la OC, la OV queda en borrador: adjúntela en la OV.",
              "Mientras el módulo está en prueba, cada OV cargada se revisa y se valida antes de enviarse a SAP.",
              "También se acepta CSV con estas mismas columnas (separado por coma o punto y coma)."]:
        ins.append([t])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _norm(h):
    return " ".join(str(h or "").strip().upper().split())


def _leer(path):
    """Filas (dict por clave interna) de un Excel o CSV."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, "rb") as f:
            raw = f.read()
        texto = raw.decode("utf-8-sig", errors="replace")
        dialecto = csv.Sniffer().sniff(texto[:2000], delimiters=",;\t") if texto.strip() else csv.excel
        filas = list(csv.reader(io.StringIO(texto), dialecto))
    else:
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb["OV"] if "OV" in wb.sheetnames else wb.worksheets[0]
        filas = [list(r) for r in ws.iter_rows(values_only=True)]
    if not filas:
        raise BusinessError("El archivo está vacío.")
    cab = [_norm(h) for h in filas[0]]
    idx = {}
    for clave, nombres in _ALIAS.items():
        for n in nombres:
            if n in cab:
                idx[clave] = cab.index(n)
                break
    faltan = [c for c in ("ruc", "codigo", "cantidad", "fecha") if c not in idx]
    if faltan:
        raise BusinessError("Faltan columnas en la plantilla: " + ", ".join(faltan) + ". Use la plantilla del módulo.")
    out = []
    for n, r in enumerate(filas[1:], start=2):
        if not any(str(x or "").strip() for x in r):
            continue
        out.append({"fila": n, **{k: (r[i] if i < len(r) else None) for k, i in idx.items()}})
    return out


def _fecha(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise BusinessError(f"fecha no válida «{t}» (use dd/mm/aaaa)")


def _num(v, nombre, obligatorio=True):
    if v in (None, ""):
        if obligatorio:
            raise BusinessError(f"falta {nombre}")
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("S/", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise BusinessError(f"{nombre} no válido «{v}»")


def importar(user, path, nombre_archivo=""):
    """Crea las OV del archivo. Devuelve {creadas: [números], borradores: [números], errores: [texto]}."""
    if not has_perm(user, "ov.crear"):
        raise BusinessError("Su rol no puede registrar OV.")
    from .orders import create_order, pickup_delivery, tax_codes, usuario_por_nombre_sap
    afecto, exo = tax_codes()
    homolog = param("homologacion_sku_cliente", {}) or {}
    grupos = OrderedDict()
    errores = []
    for r in _leer(path):
        try:
            ruc = str(r.get("ruc") or "").strip().split(".")[0]
            c = db().execute(select(Customer).where(Customer.ruc == ruc)).scalars().first()
            if c is None:
                raise BusinessError(f"cliente con RUC {ruc or '(vacío)'} no registrado")
            fecha = _fecha(r.get("fecha"))
            codigo = str(r.get("codigo") or "").strip().upper()
            if not codigo and r.get("codigo_cliente"):
                codigo = str((homolog.get(ruc) or {}).get(str(r["codigo_cliente"]).strip()) or "").upper()
                if not codigo:
                    raise BusinessError(f"el código del cliente «{r['codigo_cliente']}» no está en la homologación")
            if not codigo:
                raise BusinessError("falta el código del producto")
            igv = _norm(r.get("igv"))
            tax = afecto if igv.startswith("AFEC") or igv == afecto else (exo if igv.startswith(("EXO", "INAF")) or igv == exo else "")
            linea = {"product_code": codigo, "cantidad": _num(r.get("cantidad"), "la cantidad"),
                     "precio_unitario": _num(r.get("precio"), "el precio", False) or 0, "tax_code": tax}
            clave = (c.id, str(r.get("oc") or "").strip(), fecha)
            g = grupos.setdefault(clave, {"c": c, "fecha": fecha, "oc": clave[1], "filas": [], "lineas": [],
                                          "oc_total": _num(r.get("oc_total"), "el total de la OC", False),
                                          "canal": str(r.get("canal") or "").strip().upper(),
                                          "modalidad": _norm(r.get("modalidad")) or "ENTREGA",
                                          "hora": str(r.get("hora") or "").strip(), "ejecutivo": str(r.get("ejecutivo") or "").strip(),
                                          "comentario": str(r.get("comentario") or "").strip()})
            g["filas"].append(r["fila"])
            g["lineas"].append(linea)
        except BusinessError as e:
            errores.append(f"Fila {r['fila']}: {e}")
    creadas, borradores = [], []
    for g in grupos.values():
        filas = f"filas {g['filas'][0]}–{g['filas'][-1]}" if len(g["filas"]) > 1 else f"fila {g['filas'][0]}"
        try:
            with db().begin_nested():
                vend = usuario_por_nombre_sap(g["ejecutivo"]) if g["ejecutivo"] else None
                o = create_order(user, None, g["c"].id, g["fecha"], g["lineas"], hora_cita=g["hora"],
                                 comentarios=g["comentario"], vendedor_id=vend.id if vend else None,
                                 entrega=pickup_delivery() if g["modalidad"] == "RECOJO" else None,
                                 canal_precio=g["canal"], oc_numero=g["oc"], oc_total=g["oc_total"])
                env = dict(o.sap_envio or {})
                env.update({"por_validar": True, "carga": nombre_archivo or "plantilla", "ts_carga": now().isoformat(timespec="seconds")})
                o.sap_envio = env
                (borradores if o.estado == "BORRADOR" else creadas).append(o.numero)
        except BusinessError as e:
            errores.append(f"{g['c'].nombre} OC {g['oc'] or '-'} ({filas}): {e}")
    audit(user, "OV_CARGA_PLANTILLA", "SalesOrder", nombre_archivo or "plantilla",
          {"creadas": creadas, "borradores": borradores, "errores": errores[:50]})
    return {"creadas": creadas, "borradores": borradores, "errores": errores}


def por_validar():
    return [o for o in db().execute(select(SalesOrder).where(SalesOrder.origen == "MODULO")
                                    .order_by(SalesOrder.id.desc()).limit(500)).scalars()
            if (o.sap_envio or {}).get("por_validar")]


def validar(user, order):
    """Comercial revisó la OV cargada: ya puede enviarse a SAP."""
    if not (has_perm(user, "ov.crear") or has_perm(user, "ov.modificar")):
        raise BusinessError("Validan las OV cargadas Comercial (quien registra o modifica OV).")
    env = dict(order.sap_envio or {})
    if not env.get("por_validar"):
        raise BusinessError("La OV no está pendiente de validación.")
    env.pop("por_validar", None)
    env["validada_carga"] = {"user": user.nombre, "ts": now().isoformat(timespec="seconds")}
    order.sap_envio = env
    audit(user, "OV_CARGA_VALIDADA", "SalesOrder", order.numero, {})
