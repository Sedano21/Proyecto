"""Documentos impresos con membrete: Orden de venta (formato OV N° 1635389, foto del 13-oct)."""
from .core import param

_UNI = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece",
        "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós",
        "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
_DEC = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CEN = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
        "ochocientos", "novecientos"]


def _menor_mil(n):
    if n == 0:
        return ""
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    partes = [_CEN[c]] if c else []
    if r < 30:
        if r:
            partes.append(_UNI[r])
    else:
        d, u = divmod(r, 10)
        partes.append(_DEC[d] + (f" y {_UNI[u]}" if u else ""))
    return " ".join(partes)


def numero_en_letras(n):
    """Entero no negativo en letras (español), p. ej. 49204 -> 'cuarenta y nueve mil doscientos cuatro'."""
    n = int(n)
    if n == 0:
        return "cero"
    partes = []
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    if millones:
        partes.append("un millón" if millones == 1 else f"{numero_en_letras(millones)} millones")
    if miles:
        partes.append("mil" if miles == 1 else f"{_menor_mil(miles)} mil")
    if unidades:
        partes.append(_menor_mil(unidades))
    texto = " ".join(partes)
    return texto.replace("veintiuno mil", "veintiún mil").replace("uno mil", "un mil")


def monto_en_letras(monto, moneda="SOLES"):
    """'cuarenta y nueve mil doscientos cuatro y 76 / 100 SOLES' (como en el formato de OV)."""
    cent = round(float(monto) * 100)
    entero, dec = divmod(cent, 100)
    return f"{numero_en_letras(entero)} y {dec:02d} / 100 {moneda}"


def ov_document(order):
    """Datos de la OV para el formato impreso. El IGV se calcula solo en líneas con código de impuesto IGV."""
    lineas = []
    importe = igv = 0.0
    tasa = 0.18
    for l in order.lines:
        if not l.activa:
            continue
        bruto = (l.cantidad or 0) * (l.precio_unitario or 0)
        imp = round(bruto - (l.descuento or 0), 2)
        importe += imp
        if (l.tax_code or "").upper() == "IGV":
            igv += round(imp * tasa, 2)
        p = l.product
        lineas.append({"codigo": l.product_code, "descripcion": p.descripcion if p else l.product_code,
                       "um": l.um_venta or ("NIU" if not p or p.um != "KILOGRAMO" else "KGM"), "cantidad": l.cantidad,
                       "v_uni": l.precio_unitario or 0, "tax_code": l.tax_code or "-", "descuento": l.descuento or 0,
                       "importe": imp})
    total = round(importe + igv, 2)
    moneda = order.moneda or "SOLES"
    return {"lineas": lineas, "importe": round(importe, 2), "igv": round(igv, 2), "total": total, "moneda": moneda,
            "en_letras": monto_en_letras(total, moneda), "cod_cliente": f"C{order.customer.ruc}",
            "razon_social": param("empresa_razon_social_completa", ""), "ruc": param("empresa_ruc", ""),
            "direccion": param("empresa_direccion", []), "cuentas": param("ov_cuentas_bancarias", []),
            "instrucciones": param("ov_instrucciones_pago", []), "asistencia": param("ov_servicios_asistencia", [])}
