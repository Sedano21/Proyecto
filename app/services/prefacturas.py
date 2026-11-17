"""V56 (17-nov-2026): facturación semiautomática con validación del facturador.

1. **Pre-factura desde la guía.** Por cada guía (entrega) de SAP que sigue abierta, es decir aún no facturada, el
   sistema prepara la factura con los productos, cantidades, precios, descuentos e impuestos de la guía. La guía puede
   venir de la pre-guía validada en el módulo o haberse hecho en SAP. Avisa a Facturación.
2. **Validación del facturador.** El facturador revisa: corrige cantidades, precios o descuentos mal digitados, quita
   ítems, cambia la fecha y deja una observación. Si cambian las líneas, el motivo es obligatorio y todo queda en el
   historial. Luego valida u observa, o la descarta con motivo.
3. **A SAP.** Recién al validar se crea la factura en SAP **basada en la guía**, como la haría el facturador en SAP:
   Invoices con BaseType 15. Si la escritura en SAP no está habilitada o falla, queda pendiente y se reintenta. La
   factura queda en el expediente de la OV.
4. **Regularización SUNAT.** La factura emitida directamente en SUNAT (XML o PDF) se sube y se lee: serie y número,
   fecha, cliente (RUC), total y, del XML, los ítems. Se une a la guía que factura (sola si hay una sola del cliente).
   Al validarla se registra en SAP con la serie y el número de SUNAT. Si SAP ya facturó esa guía, la pre-factura se
   cierra sola («Facturada en SAP»).
"""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from sqlalchemy import select

from ..db import db
from ..models import Customer, OrderAttachment, Prefactura, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

ABIERTAS = ("POR_VALIDAR", "OBSERVADA")
ESTADOS = {"POR_VALIDAR": "Por validar", "OBSERVADA": "Observada", "VALIDADA": "Validada (por enviar a SAP)",
           "ENVIADA_SAP": "Facturada en SAP desde el módulo", "FACTURADA_EN_SAP": "Facturada directamente en SAP",
           "DESCARTADA": "Descartada"}


def _req(user):
    if not has_perm(user, "facturacion.cargar"):
        raise BusinessError("Las pre-facturas las revisa y valida Facturación.")


def total(p):
    t = 0.0
    for x in p.lineas or []:
        t += (x.get("cantidad") or 0) * (x.get("precio") or 0) * (1 - (x.get("descuento") or 0) / 100)
    return round(t, 2)


def _hist(p, user, accion, **extra):
    p.ediciones = list(p.ediciones or []) + [dict({"accion": accion, "user": user.nombre if user else "Sistema",
                                                   "ts": now().isoformat(timespec="minutes")}, **extra)]


# ------------------------------------------------------------------ V57: condiciones de pago de SAP (forma de pago)
def condiciones():
    """[{codigo, nombre, dias}] leídas de SAP (PaymentTermsTypes)."""
    return list(param("sap_condiciones_pago", []) or [])


def leer_condiciones(sl):
    from .core import set_param
    try:
        filas = sl.get_all("PaymentTermsTypes", {"$select": "GroupNumber,PaymentTermsGroupName,NumberOfAdditionalDays,"
                                                            "NumberOfAdditionalMonths"})
    except BusinessError:
        return condiciones()
    lst = [{"codigo": int(f["GroupNumber"]), "nombre": f.get("PaymentTermsGroupName") or str(f["GroupNumber"]),
            "dias": int(f.get("NumberOfAdditionalDays") or 0) + 30 * int(f.get("NumberOfAdditionalMonths") or 0)}
           for f in filas if f.get("GroupNumber") is not None]
    if lst and lst != condiciones():
        set_param("sap_condiciones_pago", lst)
    return lst or condiciones()


def _aplicar_condicion(p, codigo):
    """Forma de pago y vencimiento según la condición de pago de SAP (el vencimiento se puede cambiar)."""
    if codigo in (None, ""):
        return
    c = next((x for x in condiciones() if x["codigo"] == int(codigo)), None)
    p.forma_pago_codigo = int(codigo)
    p.forma_pago = (c["nombre"] if c else str(codigo))[:80]
    if c is not None:
        from datetime import timedelta
        p.vencimiento = (p.fecha or date.today()) + timedelta(days=c["dias"])


# ------------------------------------------------------------------ 1. pre-factura desde las guías abiertas de SAP
def _lineas_de_entrega(d):
    out = []
    for ln in d.get("DocumentLines") or []:
        if not ln.get("ItemCode"):
            continue
        q = float(ln.get("Quantity") or 0)
        abierta = float(ln["RemainingOpenQuantity"]) if ln.get("RemainingOpenQuantity") is not None else q
        if abierta <= 1e-9 or ln.get("LineStatus") == "bost_Close":
            continue
        precio = ln.get("UnitPrice")
        if precio is None:
            precio = ln.get("Price") or 0
        out.append({"linea": ln.get("LineNum", 0), "codigo": ln["ItemCode"], "descripcion": ln.get("ItemDescription") or "",
                    "um": ln.get("MeasureUnit") or ln.get("UoMCode") or "", "cantidad": abierta, "maximo": abierta,
                    "precio": float(precio or 0), "descuento": float(ln.get("DiscountPercent") or 0),
                    "impuesto": ln.get("TaxCode") or "", "almacen": ln.get("WarehouseCode") or "",
                    "base_ov": ln.get("BaseEntry") if ln.get("BaseType") == 17 else None})
    return out


def _abiertas_sap(sl):
    from .sap_sl import _folio
    from .sap_v31 import historial_desde
    return sl.get_all("DeliveryNotes", {"$filter": f"DocumentStatus eq 'bost_Open' and Cancelled eq 'tNO' and "
                                                   f"DocDate ge '{historial_desde().isoformat()}'",
                                        "$select": "DocEntry,DocNum,FolioPrefixString,FolioNumber,DocDate,CardCode,CardName,"
                                                   "DocCurrency,NumAtCard,PaymentGroupCode,DocDueDate,DocumentLines"}), _folio


def sincronizar(user=None, sl=None):
    """Prepara la pre-factura de cada guía abierta de SAP que aún no tiene una, y cierra las pre-facturas cuya guía ya se
    facturó en SAP por otro camino. Devuelve {nuevas, facturadas_en_sap}."""
    from . import sap_sl
    from .orders import order_by_number
    from .sap_v29 import _por_entry
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    try:
        if propio:
            sl.login()
        docs, folio = _abiertas_sap(sl)
        ovs = _por_entry(sl, "Orders", [ln.get("BaseEntry") for d in docs for ln in d.get("DocumentLines") or []
                                        if ln.get("BaseType") == 17], "DocEntry,DocNum")
        leer_condiciones(sl)
    finally:
        if propio:
            sl.logout()
    abiertas = {int(d["DocEntry"]): d for d in docs}
    existentes = {p.entrega_docentry: p for p in db().execute(select(Prefactura).where(
        Prefactura.entrega_docentry.isnot(None))).scalars()}
    nuevas, cerradas = [], []
    for de, d in abiertas.items():
        if de in existentes:
            continue
        lineas = _lineas_de_entrega(d)
        if not lineas:
            continue
        for x in lineas:
            x["entrega"], x["guia"] = de, folio(d)
        ov = next((str(ovs.get(x["base_ov"], {}).get("DocNum") or "") for x in lineas if x.get("base_ov")), "")
        o = order_by_number(ov) if ov else None
        p = Prefactura(origen="SAP", estado="POR_VALIDAR", entrega_docentry=de, guia=folio(d), ov_numero=ov,
                       order_id=o.id if o else None, cardcode=(d.get("CardCode") or "")[:30],
                       cliente=(d.get("CardName") or "")[:200], fecha=date.today(),
                       moneda=(d.get("DocCurrency") or "")[:10], lineas=lineas, sap={}, ediciones=[],
                       oc_cliente=(d.get("NumAtCard") or (o.oc_numero if o else "") or "")[:100])
        _aplicar_condicion(p, d.get("PaymentGroupCode"))
        c = db().execute(select(Customer).where(Customer.codigo_sap == p.cardcode)).scalars().first() if p.cardcode else None
        p.ruc = (c.ruc if c else "")[:15]
        db().add(p)
        db().flush()
        _hist(p, None, "GENERADA", detalle=f"Desde la guía {p.guia} de SAP")
        alerts.emit("PREFACTURA_POR_VALIDAR", f"Factura por validar: guía {p.guia} · {p.cliente}",
                    f"OV {ov or '—'} · {len(lineas)} ítem(s) · S/ {total(p):,.2f} sin IGV. Revise y valide para crearla en SAP.",
                    "Prefactura", p.id, dedup_key=f"PREFACTURA:{p.id}", creado_por=user)
        nuevas.append(p.guia)
    for de, p in existentes.items():
        if p.estado in ABIERTAS + ("VALIDADA",) and de not in abiertas and (p.sap or {}).get("estado") != "OK":
            p.estado = "FACTURADA_EN_SAP"
            _hist(p, None, "FACTURADA_EN_SAP", detalle="La guía ya no está abierta en SAP: se facturó (o cerró) en SAP")
            alerts.close_by_system(f"PREFACTURA:{p.id}", "La guía ya se facturó en SAP")
            cerradas.append(p.guia)
    db().flush()
    from .core import set_param
    res = {"nuevas": nuevas, "facturadas_en_sap": cerradas}
    set_param("prefacturas_ultima", dict(ts=now().isoformat(timespec="minutes"), guias_abiertas=len(abiertas),
                                          nuevas=len(nuevas), facturadas_en_sap=len(cerradas)), user)
    return res


def sincronizar_seguro(user=None, sl=None):
    """Para el vigilante: un error inesperado no frena el resto de la revisión."""
    from .sap_sl import SapConnectionError
    try:
        r = sincronizar(user, sl)
        return f"{len(r['nuevas'])} nuevas, {len(r['facturadas_en_sap'])} facturadas en SAP"
    except (BusinessError, SapConnectionError):
        raise
    except Exception as e:  # noqa: BLE001
        raise BusinessError(f"No se pudieron preparar las facturas desde las guías de SAP: {str(e)[:200]}") from e


# ------------------------------------------------------------------ 2. revisión del facturador
def editar(user, p, datos):
    """datos: fecha, observacion, motivo y, por línea i, cantidad_i, precio_i, descuento_i y quitar_i."""
    _req(user)
    if p.estado not in ABIERTAS:
        raise BusinessError("Solo se edita una pre-factura por validar u observada.")
    antes = [dict(x) for x in p.lineas or []]
    nuevas = []
    for i, x in enumerate(antes):
        x = dict(x)
        if datos.get(f"quitar_{i}"):
            continue
        for campo, k in (("cantidad", f"cantidad_{i}"), ("precio", f"precio_{i}"), ("descuento", f"descuento_{i}")):
            v = datos.get(k)
            if v is None or str(v).strip() == "":
                continue
            try:
                v = float(str(v).replace(",", "."))
            except ValueError:
                raise BusinessError(f"{x['codigo']}: {campo} no válido.") from None
            if v < 0:
                raise BusinessError(f"{x['codigo']}: {campo} no puede ser negativo.")
            x[campo] = v
        if x.get("maximo") is not None and x["cantidad"] > x["maximo"] + 1e-9:
            raise BusinessError(f"{x['codigo']}: no se puede facturar más de lo guiado ({x['maximo']:g}).")
        if x["descuento"] > 100:
            raise BusinessError(f"{x['codigo']}: el descuento es un porcentaje (0 a 100).")
        if x["cantidad"] <= 1e-9:
            continue  # cantidad 0 = se quita
        nuevas.append(x)
    if not nuevas:
        raise BusinessError("La factura debe tener al menos un ítem; si no corresponde facturar, descártela.")
    clave = lambda xs: [(x["codigo"], x.get("linea"), round(x["cantidad"], 6), round(x["precio"], 6), round(x["descuento"], 4))  # noqa: E731
                        for x in xs]
    cambia = clave(antes) != clave(nuevas)
    motivo = (datos.get("motivo") or "").strip()
    if cambia and not motivo:
        raise BusinessError("Indique el motivo del cambio en los ítems (p. ej. «precio mal digitado», «no se factura»).")
    f = (datos.get("fecha") or "").strip()
    if f:
        try:
            p.fecha = date.fromisoformat(f)
        except ValueError:
            raise BusinessError("Fecha no válida.") from None
    if datos.get("observacion") is not None:
        p.observacion = datos.get("observacion").strip()[:1000]
    if datos.get("oc_cliente") is not None:
        p.oc_cliente = datos.get("oc_cliente").strip()[:100]
    fp = (datos.get("forma_pago_codigo") or "").strip() if isinstance(datos.get("forma_pago_codigo"), str) else datos.get("forma_pago_codigo")
    if fp not in (None, "") and str(fp) != str(p.forma_pago_codigo or ""):
        _aplicar_condicion(p, int(fp))
    v = (datos.get("vencimiento") or "").strip()
    if v:
        try:
            p.vencimiento = date.fromisoformat(v)
        except ValueError:
            raise BusinessError("Fecha de vencimiento no válida.") from None
    if p.vencimiento and p.fecha and p.vencimiento < p.fecha:
        raise BusinessError("El vencimiento no puede ser anterior a la fecha de la factura.")
    p.lineas = nuevas
    _hist(p, user, "EDITADA", motivo=motivo, lineas_cambiadas=cambia, antes=antes if cambia else None)
    audit(user, "PREFACTURA_EDITADA", "Prefactura", p.id, {"motivo": motivo, "cambia_lineas": cambia})
    return p


def validar(user, p, aprobar=True, observacion="", sl=None):
    _req(user)
    if p.estado not in ABIERTAS:
        raise BusinessError("La pre-factura no está por validar.")
    if p.origen == "SUNAT" and not p.entrega_docentry:
        raise BusinessError("Una primero la factura de SUNAT a la guía que factura.")
    obs = (observacion or "").strip()
    if aprobar and not (p.forma_pago_codigo is not None or p.forma_pago):
        raise BusinessError("Elija la forma de pago antes de validar.")
    if not aprobar:
        if not obs:
            raise BusinessError("Indique qué se observa.")
        p.estado = "OBSERVADA"
        _hist(p, user, "OBSERVADA", observacion=obs)
        audit(user, "PREFACTURA_OBSERVADA", "Prefactura", p.id, {"observacion": obs})
        if p.order_id and p.order and p.order.vendedor_id:
            alerts.emit("PREFACTURA_OBSERVADA", f"Factura observada: guía {p.guia} · {p.cliente}", obs, "Prefactura", p.id,
                        extra_users=[p.order.vendedor_id], dedup_key=f"PREFACTURA_OBS:{p.id}", creado_por=user)
        return p
    if obs:
        p.observacion = (p.observacion + "\n" if p.observacion else "") + obs
    p.estado = "VALIDADA"
    p.validado_por, p.validado_ts = user.nombre, now()
    p.sap = {"estado": "PENDIENTE"}
    _hist(p, user, "VALIDADA", observacion=obs)
    audit(user, "PREFACTURA_VALIDADA", "Prefactura", p.id, {"total": total(p)})
    alerts.close_by_system(f"PREFACTURA:{p.id}", "Pre-factura validada")
    enviar(p, user, sl)
    return p


def descartar(user, p, motivo):
    _req(user)
    if p.estado not in ABIERTAS:
        raise BusinessError("Solo se descarta una pre-factura por validar u observada.")
    if not (motivo or "").strip():
        raise BusinessError("Indique por qué se descarta (p. ej. «se factura con otra guía», «muestra sin valor»).")
    p.estado = "DESCARTADA"
    _hist(p, user, "DESCARTADA", motivo=motivo.strip())
    audit(user, "PREFACTURA_DESCARTADA", "Prefactura", p.id, {"motivo": motivo})
    alerts.close_by_system(f"PREFACTURA:{p.id}", "Pre-factura descartada")
    return p


# ------------------------------------------------------------------ 3. factura en SAP basada en la guía
def payload(p):
    lineas = []
    for x in p.lineas or []:
        d = {"BaseType": 15, "BaseEntry": x.get("entrega") or p.entrega_docentry, "BaseLine": x["linea"], "Quantity": x["cantidad"],
             "UnitPrice": x["precio"], "DiscountPercent": x.get("descuento") or 0}
        if x.get("impuesto"):
            d["TaxCode"] = x["impuesto"]
        lineas.append(d)
    body = {"CardCode": p.cardcode, "DocDate": (p.fecha or date.today()).isoformat(),
            "TaxDate": (p.fecha or date.today()).isoformat(),
            "Comments": (f"Factura de la guía {p.guia}" + (f" (OV {p.ov_numero})" if p.ov_numero else "")
                         + " validada en el módulo." + (f" {p.observacion}" if p.observacion else ""))[:254],
            "DocumentLines": lineas}
    if p.forma_pago_codigo is not None:
        body["PaymentGroupCode"] = p.forma_pago_codigo
    if p.vencimiento:
        body["DocDueDate"] = p.vencimiento.isoformat()
    if p.oc_cliente:
        body["NumAtCard"] = p.oc_cliente[:100]
    if p.origen == "SUNAT" and p.serie and p.numero:
        body["FolioPrefixString"], body["FolioNumber"] = p.serie, int(p.numero)
    return body


def enviar(p, user=None, sl=None):
    """Crea la factura en SAP (si la escritura está habilitada). Si no se puede, queda pendiente con el motivo."""
    from . import sap_sl
    if p.estado != "VALIDADA" or (p.sap or {}).get("estado") == "OK":
        return p.sap
    sap = dict(p.sap or {})
    try:
        motivo = sap_sl.write_enabled(sl.cfg if sl is not None else None)
        if motivo:
            raise BusinessError(motivo)
        if not p.entrega_docentry or not p.cardcode:
            raise BusinessError("Falta la guía de SAP o el cliente: no se puede crear la factura basada en la guía.")
        propio = sl is None
        sl = sl or sap_sl.ServiceLayer()
        if propio:
            sl.login()
        try:
            r = sl._req("POST", "Invoices", payload(p))
        finally:
            if propio:
                sl.logout()
        sap = {"estado": "OK", "docentry": r.get("DocEntry"), "docnum": str(r.get("DocNum") or ""),
               "folio": sap_sl._folio(r) if r.get("FolioNumber") else "", "ts": now().isoformat(timespec="minutes"),
               "error": ""}
        p.estado = "ENVIADA_SAP"
        _hist(p, user, "ENVIADA_SAP", docnum=sap["docnum"])
        if p.order_id:
            numero = sap["folio"] or (f"{p.serie}-{p.numero}" if p.serie else sap["docnum"])
            db().add(OrderAttachment(order_id=p.order_id, tipo="FACTURA", nombre=f"Factura {numero} (SAP)", archivo=p.archivo or "",
                                     observacion=f"Creada en SAP desde la pre-factura validada de la guía {p.guia}.",
                                     user_id=user.id if user else None))
        audit(user, "SAP_FACTURA_CREADA", "Prefactura", p.id, {"docnum": sap["docnum"], "guia": p.guia})
    except BusinessError as e:
        sap.update({"estado": "PENDIENTE" if "escritura" in str(e).lower() or "configur" in str(e).lower() else "ERROR",
                    "error": str(e)[:300], "ts": now().isoformat(timespec="minutes")})
        if sap["estado"] == "ERROR":
            alerts.emit("PREFACTURA_ERROR_SAP", f"SAP no aceptó la factura de la guía {p.guia}", str(e)[:300], "Prefactura",
                        p.id, dedup_key=f"PREFACTURA_ERR:{p.id}", creado_por=user)
    p.sap = sap
    return sap


def reabrir(user, p, motivo):
    """La factura validada que SAP rechazó vuelve a revisión para corregirla."""
    _req(user)
    if p.estado != "VALIDADA" or (p.sap or {}).get("estado") == "OK":
        raise BusinessError("Solo se reabre una pre-factura validada que aún no está en SAP.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo.")
    p.estado = "POR_VALIDAR"
    _hist(p, user, "REABIERTA", motivo=motivo.strip(), error_sap=(p.sap or {}).get("error", ""))
    p.sap = {}
    return p


def enviar_pendientes(sl=None):
    n = 0
    for p in db().execute(select(Prefactura).where(Prefactura.estado == "VALIDADA")).scalars():
        if (p.sap or {}).get("estado") == "PENDIENTE" and enviar(p, None, sl).get("estado") == "OK":
            n += 1
    return n


# ------------------------------------------------------------------ 4. regularización de facturas emitidas en SUNAT
def _t(el, *ruta):
    for nombre in ruta:
        if el is None:
            return None
        el = next((e for e in el.iter() if e.tag.split("}")[-1] == nombre), None)
    return el


def _hijos(el, nombre):
    return [e for e in el if e.tag.split("}")[-1] == nombre]


def parse_xml(data):
    """XML UBL 2.1 de la factura electrónica (Invoice) que entrega SUNAT."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise BusinessError("El XML de la factura no es válido.") from None
    if root.tag.split("}")[-1] != "Invoice":
        raise BusinessError("El XML no es una factura (Invoice).")
    ident = next((e.text for e in root if e.tag.split("}")[-1] == "ID"), "") or ""
    if "-" not in ident:
        raise BusinessError("El XML no trae la serie y el número de la factura.")
    serie, numero = ident.split("-", 1)
    f = {"serie": serie.strip().upper(), "numero": str(int(numero.strip()))}
    fe = next((e.text for e in root if e.tag.split("}")[-1] == "IssueDate"), "")
    f["fecha"] = date.fromisoformat(fe[:10]) if fe else None
    f["moneda"] = next((e.text for e in root if e.tag.split("}")[-1] == "DocumentCurrencyCode"), "") or ""
    cli = _t(root, "AccountingCustomerParty")
    rid = _t(cli, "PartyIdentification", "ID") if cli is not None else None
    f["ruc"] = (rid.text or "").strip() if rid is not None else ""
    nom = _t(cli, "RegistrationName") if cli is not None else None
    f["cliente"] = (nom.text or "").strip() if nom is not None else ""
    tot = _t(root, "LegalMonetaryTotal", "PayableAmount")
    f["total"] = float(tot.text) if tot is not None and tot.text else None
    lineas = []
    for il in _hijos(root, "InvoiceLine"):
        q = _t(il, "InvoicedQuantity")
        cod = _t(il, "SellersItemIdentification", "ID")
        desc = _t(il, "Description")
        precio = _t(il, "Price", "PriceAmount")
        lineas.append({"codigo": (cod.text or "").strip().upper() if cod is not None else "",
                       "descripcion": " ".join((desc.text or "").split()) if desc is not None else "",
                       "um": q.get("unitCode", "") if q is not None else "",
                       "cantidad": float(q.text) if q is not None and q.text else 0.0,
                       "precio": float(precio.text) if precio is not None and precio.text else 0.0, "descuento": 0.0})
    f["lineas"] = lineas
    gr = [(_t(d, "ID").text or "").strip() for d in _hijos(root, "DespatchDocumentReference") if _t(d, "ID") is not None]
    f["guias"] = [x for x in gr if x]
    oc = _t(root, "OrderReference", "ID")
    f["oc"] = (oc.text or "").strip() if oc is not None else ""
    pt = [e for e in _hijos(root, "PaymentTerms")]
    f["forma_pago"] = next(((_t(e, "PaymentMeansID").text or "").strip() for e in pt
                            if _t(e, "PaymentMeansID") is not None and (_t(e, "PaymentMeansID").text or "").strip()), "")
    venc = next((_t(e, "PaymentDueDate") for e in pt if _t(e, "PaymentDueDate") is not None), None)
    f["vencimiento"] = date.fromisoformat(venc.text[:10]) if venc is not None and venc.text else None
    return f


def parse_text(texto):
    """Representación impresa (PDF) de la factura: serie y número, fecha, RUC del cliente y total. Los ítems se toman de
    la guía a la que se une (el PDF no siempre trae los códigos)."""
    t = texto or ""
    m = re.search(r"\b(F[A-Z0-9]{3})\s*-\s*(\d{1,8})\b", t)
    if not m:
        raise BusinessError("No se encontró la serie y el número de la factura (p. ej. «F001-00000123»).")
    f = {"serie": m.group(1).upper(), "numero": str(int(m.group(2))), "lineas": [], "moneda": ""}
    propio = str(param("empresa_ruc", "") or "")
    rucs = [r for r in re.findall(r"\b(\d{11})\b", t) if r != propio]
    f["ruc"] = rucs[0] if rucs else ""
    fechas = re.findall(r"(\d{2}/\d{2}/\d{4})", t)
    f["fecha"] = datetime.strptime(fechas[0], "%d/%m/%Y").date() if fechas else None
    m = re.search(r"importe\s+total[\s\S]{0,60}?([\d,]+\.\d{2})", t, re.I) or \
        re.search(r"total\s+a\s+pagar[\s\S]{0,40}?([\d,]+\.\d{2})", t, re.I)
    f["total"] = float(m.group(1).replace(",", "")) if m else None
    m = re.search(r"fecha\s+de\s+emisi[oó]n\s*:?\s*(\d{2}/\d{2}/\d{4})", t, re.I)
    if m:
        f["fecha"] = datetime.strptime(m.group(1), "%d/%m/%Y").date()
    m = re.search(r"fecha\s+de\s+vencimiento\s*:?\s*(\d{2}/\d{2}/\d{4})", t, re.I)
    f["vencimiento"] = datetime.strptime(m.group(1), "%d/%m/%Y").date() if m else None
    m = re.search(r"forma\s+de\s+pago\s*:?\s*(CR[EÉ]DITO|CONTADO)", t, re.I)
    f["forma_pago"] = m.group(1).upper().replace("É", "E") if m else ""
    m = re.search(r"orden\s+de[\s\S]{0,25}?(\d{6,})", t, re.I)
    f["oc"] = m.group(1) if m else ""
    m = re.search(r"gu[ií]a\(?s?\)?\s+de\s+remisi[oó]n\s*:?\s*([A-Z0-9]{4}\s*-\s*\d+(?:\s*[,;/]\s*[A-Z0-9]{4}\s*-\s*\d+)*)", t, re.I)
    f["guias"] = [re.sub(r"\s", "", x) for x in re.split(r"[,;/]", m.group(1))] if m else []
    # ítems: «10.00 MP-902 DESCRIPCION 5.00 50.00» (cantidad, código, descripción, P.U., valor)
    for ln in t.splitlines():
        m = re.match(r"^\s*([\d.,]+)\s+([A-Za-z]{2,3}-\d{2,6}[A-Za-z0-9.]*)\s+(.+?)\s+([\d.,]+)\s+([\d.,]+)\s*$", ln)
        if m:
            try:
                q, pu = float(m.group(1).replace(",", "")), float(m.group(4).replace(",", ""))
            except ValueError:
                continue
            f["lineas"].append({"codigo": m.group(2).upper(), "descripcion": m.group(3).strip(), "um": "", "cantidad": q,
                                "precio": pu, "descuento": 0.0})
    c = db().execute(select(Customer).where(Customer.ruc == f["ruc"])).scalars().first() if f["ruc"] else None
    f["cliente"] = c.nombre if c else ""
    return f


def leer_archivo(path):
    if path.lower().endswith(".xml"):
        with open(path, "rb") as fh:
            return parse_xml(fh.read())
    from pypdf import PdfReader
    texto = "\n".join(pg.extract_text() or "" for pg in PdfReader(path).pages)
    return parse_text(texto)


def _norm(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").upper()) if unicodedata.category(c) != "Mn")


def _norm_guia(g):
    """{'T001-123'} sin ceros a la izquierda ni espacios, para comparar el número de guía que cita la factura."""
    out = set()
    for x in re.split(r"[,;/]", g or ""):
        m = re.match(r"\s*([A-Z0-9]{4})\s*-\s*0*(\d+)", x.upper())
        if m:
            out.add(f"{m.group(1)}-{m.group(2)}")
    return out


def candidatas(p):
    """Pre-facturas de guías de SAP del mismo cliente aún por validar, a las que se puede unir la factura de SUNAT."""
    q = select(Prefactura).where(Prefactura.origen == "SAP", Prefactura.estado.in_(ABIERTAS))
    out = []
    for x in db().execute(q).scalars():
        if (p.ruc and x.ruc == p.ruc) or (p.cardcode and x.cardcode == p.cardcode) or \
                (p.cliente and x.cliente.strip().upper() == p.cliente.strip().upper()):
            out.append(x)
    return out


def registrar_sunat(user, path, nombre="", archivo_rel=""):
    _req(user)
    f = leer_archivo(path)
    dup = db().execute(select(Prefactura).where(Prefactura.serie == f["serie"], Prefactura.numero == f["numero"],
                                                Prefactura.estado != "DESCARTADA")).scalars().first()
    if dup is not None:
        raise BusinessError(f"La factura {f['serie']}-{f['numero']} ya se subió (pre-factura #{dup.id}).")
    c = db().execute(select(Customer).where(Customer.ruc == f["ruc"])).scalars().first() if f["ruc"] else None
    p = Prefactura(origen="SUNAT", estado="POR_VALIDAR", serie=f["serie"], numero=f["numero"], ruc=f["ruc"][:15],
                   cliente=(f.get("cliente") or (c.nombre if c else ""))[:200], cardcode=(c.codigo_sap if c else "")[:30],
                   fecha=f.get("fecha") or date.today(), moneda=f.get("moneda", "")[:10], lineas=f.get("lineas") or [],
                   total_sunat=f.get("total"), archivo=archivo_rel, sap={}, ediciones=[], user_id=user.id,
                   oc_cliente=(f.get("oc") or "")[:100], vencimiento=f.get("vencimiento"))
    fp = (f.get("forma_pago") or "").upper()
    if fp:
        c_fp = next((x for x in condiciones() if fp[:5] in _norm(x["nombre"])), None)
        p.forma_pago = (c_fp["nombre"] if c_fp else fp.title())[:80]
        p.forma_pago_codigo = c_fp["codigo"] if c_fp else None
    db().add(p)
    db().flush()
    _hist(p, user, "SUBIDA", archivo=nombre)
    cands = candidatas(p)
    citadas = set().union(*[_norm_guia(g) for g in f.get("guias") or []]) if f.get("guias") else set()
    por_guia = [c for c in cands if _norm_guia(c.guia) & citadas]
    elegidas = por_guia or (cands if len(cands) == 1 else [])
    if elegidas:
        unir(user, p, elegidas[0], "La factura cita la guía " + elegidas[0].guia if por_guia else "Única guía abierta del cliente")
        if len(elegidas) > 1:
            juntar(user, p, elegidas[1:], "La factura cita varias guías")
    audit(user, "FACTURA_SUNAT_SUBIDA", "Prefactura", p.id, {"factura": f"{p.serie}-{p.numero}", "ruc": p.ruc})
    return p


def unir(user, p, guia_p, motivo=""):
    """Une la factura de SUNAT a la pre-factura de la guía que factura: toma su guía, cliente y líneas de SAP (las
    cantidades y precios del XML, si coinciden por código, reemplazan los de la guía) y descarta la pre-factura de la
    guía, que queda reemplazada por esta."""
    _req(user)
    if p.origen != "SUNAT" or p.estado not in ABIERTAS:
        raise BusinessError("Solo se une una factura de SUNAT por validar.")
    if guia_p.origen != "SAP" or guia_p.estado not in ABIERTAS:
        raise BusinessError("La guía elegida ya no está por facturar.")
    del_xml = {x["codigo"]: x for x in p.lineas or [] if x.get("codigo")}
    lineas = []
    for x in guia_p.lineas or []:
        x = dict(x)
        s = del_xml.get(x["codigo"])
        if s:
            x["cantidad"] = min(s["cantidad"], x.get("maximo") or s["cantidad"])
            x["precio"] = s["precio"] or x["precio"]
        lineas.append(x)
    p.lineas = lineas
    p.entrega_docentry, p.guia, p.ov_numero, p.order_id = guia_p.entrega_docentry, guia_p.guia, guia_p.ov_numero, guia_p.order_id
    p.cardcode = p.cardcode or guia_p.cardcode
    p.cliente = p.cliente or guia_p.cliente
    p.oc_cliente = p.oc_cliente or guia_p.oc_cliente
    if p.forma_pago_codigo is None and guia_p.forma_pago_codigo is not None:
        p.forma_pago_codigo, p.forma_pago = guia_p.forma_pago_codigo, guia_p.forma_pago
        p.vencimiento = p.vencimiento or guia_p.vencimiento
    guia_p.estado = "DESCARTADA"
    guia_p.entrega_docentry = None  # la guía pasa a la factura de SUNAT (una guía, una pre-factura)
    _hist(guia_p, user, "REEMPLAZADA", detalle=f"Se factura con la factura de SUNAT {p.serie}-{p.numero}")
    _hist(p, user, "UNIDA", guia=p.guia, motivo=motivo)
    alerts.close_by_system(f"PREFACTURA:{guia_p.id}", f"Facturada en SUNAT con {p.serie}-{p.numero}")
    db().flush()
    return p


# ------------------------------------------------------------------ V57: de guías a factura (varias guías, una factura)
def juntables(p):
    """Otras pre-facturas por validar del mismo cliente (de otras guías) que se pueden facturar juntas con esta."""
    if p.estado not in ABIERTAS or not p.cardcode:
        return []
    return [x for x in db().execute(select(Prefactura).where(Prefactura.id != p.id, Prefactura.origen == "SAP",
                                                             Prefactura.cardcode == p.cardcode,
                                                             Prefactura.estado.in_(ABIERTAS))).scalars()]


def juntar(user, p, otras, motivo=""):
    """Factura varias guías del mismo cliente en una sola: las líneas de las otras pre-facturas pasan a esta (cada una con
    su guía de origen) y aquellas quedan descartadas como «unidas»."""
    _req(user)
    if p.estado not in ABIERTAS:
        raise BusinessError("Solo se juntan guías en una pre-factura por validar.")
    if not otras:
        raise BusinessError("Elija las guías que se facturan junto con esta.")
    lineas = [dict(x, entrega=x.get("entrega") or p.entrega_docentry, guia=x.get("guia") or p.guia) for x in p.lineas or []]
    guias = [g.strip() for g in (p.guia or "").split(",") if g.strip()]
    for q in otras:
        if q.id == p.id or q.cardcode != p.cardcode or q.estado not in ABIERTAS or q.origen != "SAP":
            raise BusinessError(f"La pre-factura #{q.id} no se puede juntar (otro cliente o ya no está por validar).")
        for x in q.lineas or []:
            lineas.append(dict(x, entrega=x.get("entrega") or q.entrega_docentry, guia=x.get("guia") or q.guia))
        guias.append(q.guia)
        if q.ov_numero and q.ov_numero not in (p.ov_numero or ""):
            p.ov_numero = ((p.ov_numero + ", ") if p.ov_numero else "") + q.ov_numero
        q.estado = "DESCARTADA"
        _hist(q, user, "UNIDA", detalle=f"Se factura junto con la pre-factura #{p.id}")
        alerts.close_by_system(f"PREFACTURA:{q.id}", f"Unida a la pre-factura #{p.id}")
    p.lineas = lineas
    p.guia = ", ".join(dict.fromkeys(guias))[:40]
    _hist(p, user, "GUIAS_JUNTADAS", detalle="Guías: " + ", ".join(dict.fromkeys(guias)), motivo=motivo)
    audit(user, "PREFACTURA_GUIAS_JUNTADAS", "Prefactura", p.id, {"guias": guias})
    db().flush()
    return p


def de_la_orden(order_id):
    return list(db().execute(select(Prefactura).where(Prefactura.order_id == order_id).order_by(Prefactura.id)).scalars())
