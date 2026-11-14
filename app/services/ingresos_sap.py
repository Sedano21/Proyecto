"""V35 (14-nov-2026): ingreso de mercadería a SAP (entrada de mercancías, InventoryGenEntries) por la Jefatura de
Operaciones.

Uso principal: el PRÉSTAMO de stock cuando una guía emitida en SUNAT no pasa a SAP porque SAP ya descontó ese stock
(p. ej. por un reconteo del mismo día) y responde «Quantity falls into negative inventory». Se ingresa la mercadería
(producto, lote, cantidad, FP, FV, almacén y, si se conoce, el costo) y, si el ingreso está unido a una guía, se vuelve a
enviar la guía a SAP.

- Solo escribe en las bases de SAP autorizadas («sap_escritura_empresas»).
- No toca el stock del módulo: la siguiente carga de stock de SAP lo refleja (así no se cuenta dos veces).
"""
from datetime import date

from ..db import db
from ..models import GoodsReceipt, Product, now
from . import alerts
from .core import BusinessError, audit, has_perm, param


def _fecha(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise BusinessError(f"Fecha no válida: {v}")


def _num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        raise BusinessError(f"Número no válido: {v}")


def lineas_de(form_lineas):
    """Valida las líneas del formulario: [{codigo, lote, cantidad, fp, fv, precio}]."""
    out = []
    for i, x in enumerate(form_lineas, 1):
        codigo = (x.get("codigo") or "").strip().upper().split(" ")[0]
        if not codigo and not x.get("cantidad"):
            continue
        p = db().get(Product, codigo)
        if p is None:
            raise BusinessError(f"Línea {i}: el producto {codigo or '(vacío)'} no existe.")
        cant = _num(x.get("cantidad"))
        if not cant or cant <= 0:
            raise BusinessError(f"Línea {i}: indique la cantidad.")
        lote = (x.get("lote") or "").strip().upper()
        if not lote:
            raise BusinessError(f"Línea {i}: indique el lote.")
        fp, fv = _fecha(x.get("fp")), _fecha(x.get("fv"))
        if fp and fv and fv < fp:
            raise BusinessError(f"Línea {i}: la fecha de vencimiento es anterior a la de producción.")
        out.append({"codigo": codigo, "descripcion": p.descripcion, "lote": lote, "cantidad": cant,
                    "fp": fp.isoformat() if fp else "", "fv": fv.isoformat() if fv else "",
                    "precio": _num(x.get("precio"))})
    if not out:
        raise BusinessError("Agregue al menos un producto.")
    return out


def mensaje_error(err):
    """Explicación del error de SAP para la Jefatura de Operaciones."""
    e = err or ""
    if "Inventory account is not defined" in e or "AccountCode" in e:
        return (e + " · SAP necesita la CUENTA CONTABLE de compensación para la entrada de mercancías (no es el costo). "
                "Escriba la cuenta tal como la ve en SAP (p. ej. 2841119-00-00): el sistema la convierte a su código "
                "interno. Luego pulse «Reintentar en SAP».")
    return e


def registrar(user, fecha, almacen, motivo, lineas, guia=None, sl=None, cuenta=""):
    """Registra el ingreso y lo envía a SAP. Si está unido a una guía con préstamo pendiente, la vuelve a enviar."""
    if not has_perm(user, "stock.ingreso_sap"):
        raise BusinessError("El ingreso de mercadería a SAP lo registra la Jefatura de Operaciones.")
    almacen = (almacen or "").strip().upper()
    if not almacen:
        raise BusinessError("Indique el almacén de SAP donde ingresa la mercadería.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise BusinessError("Indique el motivo (p. ej. préstamo para registrar la guía SUNAT EG07-457).")
    ing = GoodsReceipt(fecha=_fecha(fecha) or date.today(), almacen=almacen, motivo=motivo, lineas=lineas_de(lineas),
                       guia_id=guia.id if guia else None, user_id=user.id,
                       sap={"cuenta": (cuenta or "").strip()} if (cuenta or "").strip() else {})
    db().add(ing)
    db().flush()
    audit(user, "INGRESO_MERCADERIA", "GoodsReceipt", ing.id, {"almacen": almacen, "lineas": ing.lineas, "motivo": motivo})
    enviar(user, ing, sl)
    _reenviar_guia(user, ing, guia, sl)
    return ing


def reintentar(user, ing, cuenta="", sl=None):
    """V36: vuelve a enviar a SAP un ingreso que SAP rechazó (p. ej. tras definir la cuenta contable)."""
    if not has_perm(user, "stock.ingreso_sap"):
        raise BusinessError("El ingreso de mercadería a SAP lo registra la Jefatura de Operaciones.")
    if ing.estado == "EN_SAP":
        raise BusinessError("Ese ingreso ya está en SAP.")
    if (cuenta or "").strip():
        ing.sap = dict(ing.sap or {}, cuenta=cuenta.strip())
    enviar(user, ing, sl)
    _reenviar_guia(user, ing, ing.guia, sl)
    return ing


def _reenviar_guia(user, ing, guia, sl):
    if guia is not None and ing.estado == "EN_SAP":
        guia.prestamo = dict(guia.prestamo or {}, estado="INGRESADO", ingreso_id=ing.id)
        from . import guias_sunat as gs
        try:
            gs.enviar_sap(user, guia, sl=sl)
        except BusinessError as e:  # el ingreso queda hecho; la guía muestra su error y se reintenta
            ing.sap = dict(ing.sap, guia_error=str(e)[:300])


def resolver_cuenta(sl, texto):
    """V37: con el plan de cuentas segmentado, SAP muestra la cuenta como «2841119-00-00», pero el Service Layer espera
    su código interno (p. ej. «_SYS00000000315»). Se busca en el plan de cuentas por el código tal como se escribió, por
    el formato visible y por el formato sin separadores. Devuelve (código interno, nombre)."""
    import re
    t = (texto or "").strip()
    if not t:
        return "", ""
    sin_sep = re.sub(r"[^0-9A-Za-z]", "", t)
    candidatos = [("Code", t), ("FormatCode", t), ("FormatCode", sin_sep)]
    if sin_sep != t:
        candidatos.append(("Code", sin_sep))
    sin_permiso = True
    for campo, valor in candidatos:
        try:
            filas = sl.get_all("ChartOfAccounts", {"$filter": f"{campo} eq '{valor}'", "$select": "Code,Name,FormatCode"})
            sin_permiso = False
        except BusinessError:
            filas = []
        if filas:
            return filas[0].get("Code") or t, filas[0].get("Name") or ""
    try:  # el formato visible puede tener otros separadores: se compara sin separadores entre las cuentas con ese inicio
        filas = sl.get_all("ChartOfAccounts", {"$filter": f"startswith(FormatCode, '{sin_sep[:4]}')",
                                               "$select": "Code,Name,FormatCode"})
        for f in filas:
            if re.sub(r"[^0-9A-Za-z]", "", f.get("FormatCode") or "") == sin_sep:
                return f.get("Code"), f.get("Name") or ""
    except BusinessError:
        pass
    if sin_permiso:  # el usuario de integración no puede leer el plan de cuentas: se envía tal como se escribió
        return t, ""
    raise BusinessError(f"La cuenta {t} no se encontró en el plan de cuentas de SAP (ni como código interno ni como "
                        "formato). Verifique el número con Contabilidad.")


def enviar(user, ing, sl=None):
    from . import sap_sl
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    try:
        if propio:
            sl.login()
        motivo = sap_sl.write_enabled(sl.cfg)
        if motivo:
            raise BusinessError(motivo)
        cuenta_txt = ((ing.sap or {}).get("cuenta") or param("ingreso_mercaderia_cuenta", "") or "").strip()
        cuenta, cuenta_nombre = resolver_cuenta(sl, cuenta_txt) if cuenta_txt else ("", "")
        lineas = []
        for x in ing.lineas:
            d = {"ItemCode": x["codigo"], "Quantity": x["cantidad"], "WarehouseCode": ing.almacen,
                 "BatchNumbers": [dict({"BatchNumber": x["lote"], "Quantity": x["cantidad"]},
                                       **({"ManufacturingDate": x["fp"]} if x.get("fp") else {}),
                                       **({"ExpiryDate": x["fv"]} if x.get("fv") else {}))]}
            if x.get("precio"):
                d["UnitPrice"] = x["precio"]
            if cuenta:
                d["AccountCode"] = cuenta
            lineas.append(d)
        body = {"DocDate": ing.fecha.isoformat(), "Comments": f"Ingreso desde el módulo de operaciones: {ing.motivo}"[:254],
                "DocumentLines": lineas}
        r = sl._req("POST", "InventoryGenEntries", body)
    except BusinessError as e:
        ing.estado = "ERROR"
        ing.sap = {"error": str(e)[:500], "ts": now().isoformat(timespec="minutes"),
                   **({"cuenta": ing.sap["cuenta"]} if (ing.sap or {}).get("cuenta") else {})}
        audit(user, "INGRESO_MERCADERIA_ERROR", "GoodsReceipt", ing.id, ing.sap)
        return ing
    finally:
        if propio:
            try:
                sl.logout()
            except BusinessError:
                pass
    ing.estado = "EN_SAP"
    ing.sap = {"docentry": r.get("DocEntry"), "docnum": r.get("DocNum"), "ts": now().isoformat(timespec="minutes"),
               **({"cuenta_sap": cuenta, "cuenta_nombre": cuenta_nombre} if cuenta else {}),
               **({"cuenta": ing.sap["cuenta"]} if (ing.sap or {}).get("cuenta") else {})}
    audit(user, "INGRESO_MERCADERIA_SAP", "GoodsReceipt", ing.id, ing.sap)
    if ing.guia_id:
        alerts.close_by_system(f"PRESTAMO:{ing.guia_id}", f"Ingreso de mercadería #{ing.id} registrado en SAP")
    return ing
