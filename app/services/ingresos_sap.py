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


# ------------------------------------------------------------------ V38: campos de usuario de SAP de la entrada
def campos_sap(sl=None, refrescar=False):
    """Campos de usuario de la entrada de mercancías (cabecera OIGN y líneas IGN1) que la localización de SAP exige, como
    el «tipo de operación de inventarios» (código de SUNAT). Se leen de SAP (UserFieldsMD) con sus valores válidos y
    se guardan en «ingreso_mercaderia_campos_sap». [{nombre, tabla, descripcion, obligatorio, valores: [[v, d]]}]"""
    import re
    from .core import set_param
    cache = param("ingreso_mercaderia_campos_sap", {}) or {}
    if cache.get("campos") is not None and not refrescar:
        return cache["campos"]
    from . import sap_sl
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    campos = []
    try:
        if propio:
            sl.login()
        for tabla in ("OIGN", "IGN1"):
            try:
                metas = sl.get_all("UserFieldsMD", {"$filter": f"TableName eq '{tabla}'"})
            except BusinessError:
                metas = []
            for f in metas:
                desc = f.get("Description") or ""
                oblig = f.get("Mandatory") == "tYES"
                if not (oblig or re.search(r"operaci|motivo|tipo", desc, re.I) or re.search(r"OPER|TPO", f.get("Name", ""))):
                    continue
                campos.append({"nombre": "U_" + f.get("Name", ""), "tabla": tabla, "descripcion": desc,
                               "obligatorio": oblig, "defecto": f.get("DefaultValue") or "",
                               "valores": [[v.get("Value"), v.get("Description") or v.get("Value")]
                                           for v in (f.get("ValidValuesMD") or [])]})
        # V39: lo que Logística deja en sus propias entradas de mercancías (p. ej. los préstamos): SAP completa el tipo
        # de operación aunque nadie lo escriba. Se toman las últimas entradas y se sugiere el valor más usado.
        try:
            recientes = sl.get_all("InventoryGenEntries", {"$orderby": "DocEntry desc", "$top": "30"})[:30]
        except BusinessError:
            recientes = []
        from collections import Counter
        conocidos = {c["nombre"] for c in campos}
        if not campos:  # sin metadatos legibles: se deducen de los documentos (campos U_ de tipo u operación con valor)
            for d in recientes:
                for k, v in d.items():
                    if k.startswith("U_") and v not in (None, "") and re.search(r"OPER|TPO|TIPO", k, re.I) and k not in conocidos:
                        campos.append({"nombre": k, "tabla": "OIGN", "descripcion": k[2:], "obligatorio": False,
                                       "defecto": "", "valores": []})
                        conocidos.add(k)
        for c in campos:
            if c["tabla"] == "OIGN":
                usados = Counter(str(d.get(c["nombre"])) for d in recientes if d.get(c["nombre"]) not in (None, ""))
            else:
                usados = Counter(str(ln.get(c["nombre"])) for d in recientes for ln in d.get("DocumentLines") or []
                                 if ln.get(c["nombre"]) not in (None, ""))
            c["usados"] = usados.most_common(5)
            c["sugerido"] = usados.most_common(1)[0][0] if usados else (c.get("defecto") or "")
        # V40: la localización también exige el folio (prefijo y número) de la entrada. Se propone el prefijo que usa
        # Logística; el número, si se deja vacío, es el siguiente al último de ese prefijo (se calcula al enviar).
        prefijos = Counter(str(d["FolioPrefixString"]) for d in recientes if d.get("FolioPrefixString"))
        pref = prefijos.most_common(1)[0][0] if prefijos else ""
        nums = [int(d["FolioNumber"]) for d in recientes if str(d.get("FolioPrefixString") or "") == pref
                and str(d.get("FolioNumber") or "").isdigit()]
        campos.append({"nombre": "FolioPrefixString", "tabla": "FOLIO", "descripcion": "Prefijo de folio",
                       "obligatorio": True, "defecto": "", "valores": [], "usados": prefijos.most_common(5),
                       "sugerido": pref})
        campos.append({"nombre": "FolioNumber", "tabla": "FOLIO", "descripcion": "Número de folio", "obligatorio": True,
                       "defecto": "", "valores": [], "usados": [], "sugerido": "",
                       "ultimo": max(nums) if nums else None})
    finally:
        if propio:
            try:
                sl.logout()
            except BusinessError:
                pass
    set_param("ingreso_mercaderia_campos_sap", {"ts": now().isoformat(timespec="minutes"), "campos": campos})
    return campos


def mensaje_error(err):
    """Explicación del error de SAP para la Jefatura de Operaciones."""
    e = err or ""
    if "tipo de operaci" in e.lower():
        return (e + " · La localización de SAP exige el TIPO DE OPERACIÓN de inventario (código de SUNAT) en la entrada. "
                "El sistema ya leyó de SAP el que queda en las entradas de Logística y lo propone en «Datos que pide SAP»: "
                "pulse «Reintentar en SAP». Si la lista sigue vacía, pulse «Leer campos de SAP».")
    if "folio" in e.lower():
        return (e + " · La localización de SAP exige el FOLIO de la entrada (prefijo y número). El sistema propone en "
                "«Datos que pide SAP» el prefijo que usa Logística; si deja el número vacío, toma el siguiente al último "
                "de ese prefijo en SAP. Pulse «Leer campos de SAP» y luego «Reintentar en SAP». Si no sabe qué prefijo "
                "corresponde, pregúntelo a Logística o Contabilidad.")
    if "Inventory account is not defined" in e or "AccountCode" in e:
        return (e + " · SAP necesita la CUENTA CONTABLE de compensación para la entrada de mercancías (no es el costo). "
                "Escriba la cuenta tal como la ve en SAP (p. ej. 2841119-00-00): el sistema la convierte a su código "
                "interno. Luego pulse «Reintentar en SAP».")
    return e


def registrar(user, fecha, almacen, motivo, lineas, guia=None, sl=None, cuenta="", udf=None):
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
                       sap=dict({"cuenta": (cuenta or "").strip()} if (cuenta or "").strip() else {},
                                **({"udf": {k: v for k, v in udf.items() if v}} if udf else {})))
    db().add(ing)
    db().flush()
    audit(user, "INGRESO_MERCADERIA", "GoodsReceipt", ing.id, {"almacen": almacen, "lineas": ing.lineas, "motivo": motivo})
    enviar(user, ing, sl)
    _reenviar_guia(user, ing, guia, sl)
    return ing


def reintentar(user, ing, cuenta="", sl=None, udf=None):
    """V36: vuelve a enviar a SAP un ingreso que SAP rechazó (p. ej. tras definir la cuenta contable)."""
    if not has_perm(user, "stock.ingreso_sap"):
        raise BusinessError("El ingreso de mercadería a SAP lo registra la Jefatura de Operaciones.")
    if ing.estado == "EN_SAP":
        raise BusinessError("Ese ingreso ya está en SAP.")
    if (cuenta or "").strip():
        ing.sap = dict(ing.sap or {}, cuenta=cuenta.strip())
    if udf:
        ing.sap = dict(ing.sap or {}, udf={k: v for k, v in udf.items() if v})
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


def siguiente_folio(sl, prefijo):
    """V40: el número de folio siguiente al último de las entradas de mercancías de SAP con ese prefijo."""
    p = str(prefijo).replace("'", "''")
    try:
        docs = sl.get_all("InventoryGenEntries", {"$filter": f"FolioPrefixString eq '{p}'", "$select": "DocEntry,FolioNumber",
                                                  "$orderby": "FolioNumber desc", "$top": "1"})[:1]
    except BusinessError:
        docs = []
    ult = docs[0].get("FolioNumber") if docs else None
    return int(ult) + 1 if str(ult or "").isdigit() else 1


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
        # V38: campos de usuario que exige la localización (p. ej. tipo de operación de inventarios): los elegidos en el
        # ingreso o, si no, los valores por defecto de «ingreso_mercaderia_valores»
        # orden: lo elegido en el ingreso > el valor por defecto del parámetro > el que usa Logística en SAP (sugerido)
        sugeridos = {c["nombre"]: c.get("sugerido") for c in (param("ingreso_mercaderia_campos_sap", {}) or {}).get("campos", [])
                     if c.get("sugerido")}
        udf = dict(sugeridos, **(param("ingreso_mercaderia_valores", {}) or {}), **((ing.sap or {}).get("udf") or {}))
        lineas_campo = {c["nombre"] for c in (param("ingreso_mercaderia_campos_sap", {}) or {}).get("campos", [])
                        if c.get("tabla") == "IGN1"}
        for k, v in udf.items():
            if not v:
                continue
            if k in lineas_campo:
                for d in lineas:
                    d[k] = v
            else:
                body[k] = v
        if body.get("FolioPrefixString") and not body.get("FolioNumber"):
            body["FolioNumber"] = siguiente_folio(sl, body["FolioPrefixString"])
        if body.get("FolioNumber"):
            try:
                body["FolioNumber"] = int(str(body["FolioNumber"]).strip())
            except ValueError:
                raise BusinessError("El número de folio debe ser un número entero.")
        r = sl._req("POST", "InventoryGenEntries", body)
    except BusinessError as e:
        ing.estado = "ERROR"
        ing.sap = {"error": str(e)[:500], "ts": now().isoformat(timespec="minutes"),
                   **({"cuenta": ing.sap["cuenta"]} if (ing.sap or {}).get("cuenta") else {}),
                   **({"udf": ing.sap["udf"]} if (ing.sap or {}).get("udf") else {})}
        if "tipo de operaci" in str(e).lower() or "folio" in str(e).lower():
            try:  # se leen de SAP los campos que pide, para mostrarlos en la pantalla
                campos_sap(sl, refrescar=True)
            except Exception:  # noqa: BLE001
                pass
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
               **({"udf": udf} if udf else {}),
               **({"cuenta_sap": cuenta, "cuenta_nombre": cuenta_nombre} if cuenta else {}),
               **({"cuenta": ing.sap["cuenta"]} if (ing.sap or {}).get("cuenta") else {})}
    audit(user, "INGRESO_MERCADERIA_SAP", "GoodsReceipt", ing.id, ing.sap)
    if ing.guia_id:
        alerts.close_by_system(f"PRESTAMO:{ing.guia_id}", f"Ingreso de mercadería #{ing.id} registrado en SAP")
    return ing


# ------------------------------------------------------------------ V44/V48: lo que falta para el préstamo
def _stock_sap(sl, codigos, almacen):
    """V48: stock de SAP en este momento. Con la consulta de stock por lote configurada (sap_consultas.STOCK) se tiene por
    artículo, lote y almacén; si no, por artículo y almacén (Items/ItemWarehouseInfoCollection, entidad estándar)."""
    code = (param("sap_consultas", {}) or {}).get("STOCK")
    if code:
        por = {}
        for r in sl.sql_query(code):
            item = r.get("ItemCode") or r.get("Número de artículo") or r.get("articulo")
            lote = r.get("DistNumber") or r.get("Lote") or ""
            whs = r.get("WhsCode") or r.get("Almacén") or r.get("almacen") or ""
            if item in codigos and (not almacen or whs == almacen):
                k = (item, str(lote).upper())
                por[k] = por.get(k, 0) + float(r.get("Quantity") or r.get("Cantidad") or 0)
        return {"por_lote": por, "fuente": "SAP en este momento (stock por lote)"}
    por = {}
    for c in sorted(codigos):
        it = sl._req("GET", f"Items('{c}')?$select=ItemCode,ItemWarehouseInfoCollection")
        for w in (it or {}).get("ItemWarehouseInfoCollection") or []:
            if not almacen or w.get("WarehouseCode") == almacen:
                por[c] = por.get(c, 0) + float(w.get("InStock") or 0)
    return {"por_articulo": por, "fuente": "SAP en este momento (stock del artículo en el almacén; SAP no da el lote "
                                           "sin la consulta de stock por lote)"}


def faltante(guia, almacen="", sl=None):
    """Por cada línea de la guía: lo que pide la guía, lo que SAP tiene (V48: consultado a SAP en el momento; si SAP no
    responde, la última carga de stock de SAP del módulo) y lo que falta ingresar (guía − stock, nunca negativo). Es una
    propuesta: el encargado la revisa y la edita antes de registrar el ingreso."""
    from sqlalchemy import select as _select
    from ..models import StockLot
    from . import lotes as _lotes
    from . import sap_sl
    from .stock import stock_freshness
    lineas = (guia.prestamo or {}).get("lineas") or guia.lineas or []
    codigos = {x.get("codigo") for x in lineas if x.get("codigo")}
    sap, aviso = None, ""
    if sl is not None or sap_sl.configured():
        propio = sl is None
        try:
            sl = sl or sap_sl.ServiceLayer()
            if propio:
                sl.login()
            sap = _stock_sap(sl, codigos, almacen)
        except Exception as e:  # noqa: BLE001  (sin respuesta de SAP: se usa la última carga de stock)
            aviso = f"SAP no respondió ({str(e)[:120]}): se usó la última carga de stock de SAP."
        finally:
            if propio and sl is not None:
                try:
                    sl.logout()
                except Exception:  # noqa: BLE001
                    pass
    restante = dict((sap or {}).get("por_articulo") or {})
    filas = []
    for x in lineas:
        q = float(x.get("cantidad") or 0)
        lote = (x.get("lote") or "").strip()
        lots = [l for l in db().execute(_select(StockLot).where(StockLot.product_code == x.get("codigo"))).scalars()
                if lote and _lotes.misma(l.lote or "", lote) and (not almacen or l.warehouse_code == almacen)]
        if sap and "por_lote" in sap:
            disp = sum(v for (c, lt), v in sap["por_lote"].items() if c == x.get("codigo") and _lotes.misma(lt, lote))
        elif sap:
            disp = min(restante.get(x.get("codigo"), 0), q)  # el stock del artículo se reparte entre sus líneas
            restante[x.get("codigo")] = restante.get(x.get("codigo"), 0) - disp
        else:
            disp = sum(max(l.cantidad or 0, 0) for l in lots)
        disp = round(disp, 3)
        filas.append(dict(x, guia=q, stock_sap=disp, cantidad=round(max(q - disp, 0), 3),
                          fp=x.get("fp") or (min([l.fecha_fab for l in lots if l.fecha_fab] or [None]) or ""),
                          fv=x.get("fv") or (min([l.fecha_venc for l in lots if l.fecha_venc] or [None]) or "")))
    info = stock_freshness()
    fuente = sap["fuente"] if sap else (f"última carga de stock de SAP ({info['ts']:%d/%m/%Y %H:%M})" if info else
                                        "stock del módulo")
    return {"filas": filas, "stock_ts": info["ts"] if info else None, "almacen": almacen, "fuente": fuente, "aviso": aviso}
