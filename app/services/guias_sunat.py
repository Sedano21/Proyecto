"""V27 (11-nov-2026): regularización de guías de remisión emitidas directamente en SUNAT.

Cuando SAP falla, Despacho emite la guía en el portal de SUNAT. Para no digitarla de nuevo en SAP:
1. Asistencia o Coordinación de Distribución (o el Auxiliar de Despacho) sube el PDF de SUNAT o su XML. El sistema
   lee serie y número, fechas, destinatario (RUC), placa y los productos con lote, FP, FV y cantidad.
2. Se une a su OV: sola si hay una sola OV abierta del cliente con esos productos; si no, se elige.
3. El Jefe de Operaciones indica si ese producto **ya se descontó** del inventario o si hay que **descontarlo** (se
   descuenta del lote en el módulo).
4. «Enviar a SAP» crea en SAP la entrega basada en la OV, con la serie y el número de SUNAT y los lotes. Es escritura en
   SAP: solo en las bases autorizadas («sap_escritura_empresas»).
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime

from sqlalchemy import select

from ..db import db
from ..models import SalesOrder, StockLot, SunatGuide, now
from . import alerts
from . import lotes as lotes_svc
from .core import BusinessError, audit, has_perm

MOTIVOS = ("Venta sujeta a confirmación del comprador", "Venta", "Compra", "Traslado entre establecimientos de la misma empresa",
           "Traslado emisor itinerante", "Consignación", "Devolución", "Importación", "Exportación",
           "Recojo de bienes transformados", "Otros")
_COD = r"[A-Za-z]{2,3}-\d{2,6}[A-Za-z0-9.]*"


def _sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _fecha(txt):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _num(txt):
    t = (txt or "").strip().replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _lote_en(texto):
    m = re.search(r"lote\s*:?\s*([^\s]+)(?:\s+fp\s*:?\s*([\d/-]{6,10}))?(?:\s+fv\s*:?\s*([\d/-]{6,10}))?", texto, re.I)
    if not m:
        return {}
    return {"lote": m.group(1).strip().rstrip(";"), "fp": _fecha(m.group(2)).isoformat() if m.group(2) and _fecha(m.group(2)) else "",
            "fv": _fecha(m.group(3)).isoformat() if m.group(3) and _fecha(m.group(3)) else ""}


def parse_text(texto):
    """Lee el texto de la representación impresa de la guía de SUNAT (PDF)."""
    t = texto or ""
    plano = _sin_tildes(t)
    g = {}
    m = re.search(r"N[°º]\s*([A-Z0-9]{4})\s*-\s*(\d{1,8})", t)
    if not m:
        raise BusinessError("No se encontró la serie y el número de la guía (p. ej. «N° EG07 - 00000442»).")
    g["serie"], g["numero"] = m.group(1), str(int(m.group(2)))
    fechas = re.findall(r"(\d{2}/\d{2}/\d{4})(\s+\d{1,2}:\d{2})?", t)
    con_hora = [f for f, h in fechas if h]
    sin_hora = [f for f, h in fechas if not h]
    g["fecha_emision"] = _fecha(con_hora[0]) if con_hora else (_fecha(fechas[0][0]) if fechas else None)
    g["fecha_traslado"] = _fecha(sin_hora[0]) if sin_hora else g["fecha_emision"]
    m = re.search(r"Destinatario\s*:\s*(.+?)\s*-\s*(?:REGISTRO UNICO DE CONTRIBUYENTES|DOCUMENTO NACIONAL DE IDENTIDAD|RUC|DNI)"
                  r"[^\d]{0,12}(\d{8,11})", plano, re.I | re.S)
    if m:
        g["destinatario"] = " ".join(m.group(1).split())
        g["destinatario_ruc"] = m.group(2)
    else:
        m = re.search(r"Destinatario[^\d]{0,200}?(\d{11})", plano, re.I | re.S)
        g["destinatario"], g["destinatario_ruc"] = "", m.group(1) if m else ""
    m = re.search(r"Placa de vehiculo\s*:?\s*([A-Z0-9-]{5,8})", plano, re.I)
    g["placa"] = m.group(1).replace("-", "").upper() if m else ""
    g["motivo"] = next((x for x in MOTIVOS if re.search(r"(?<![a-z])" + re.escape(_sin_tildes(x)) + r"(?![a-z])", plano, re.I)), "")
    m = re.search(r"Punto de llegada\s+(.+?)(?:\n\s*\n|Datos del Destinatario)", t, re.S)
    g["llegada"] = " ".join(m.group(1).split())[:250] if m else ""
    lineas = []
    filas = [x.rstrip() for x in t.splitlines()]
    for i, ln in enumerate(filas):
        # 1) texto extraído por pypdf: «pt-147 UNIDAD (NIU)1 NO 24.00» con la descripción y el lote en las 2 líneas previas
        m = re.match(rf"^\s*({_COD})\s+(.+?\(\w+\))\s*\d+\s+(?:SI|NO)\s+([\d.,]+)\s*$", ln)
        if m:
            previas = [x for x in filas[max(0, i - 3):i] if x.strip()]
            lote = next((_lote_en(x) for x in reversed(previas) if re.search(r"\blote\b", x, re.I)), {})
            desc = next((x.strip() for x in reversed(previas) if not re.search(r"\blote\b", x, re.I)), "")
            lineas.append({"codigo": m.group(1).upper(), "descripcion": desc, "um": m.group(2).strip(), "cantidad": _num(m.group(3)), **lote})
            continue
        # 2) texto con columnas («1  NO  pt-147  descripción  UNIDAD (NIU)  24.00») y el lote en la línea siguiente
        m = re.match(rf"^\s*\d+\s+(?:SI|NO)\s+({_COD})\s+(.+?)\s{{2,}}(.+?\(\w+\))\s+([\d.,]+)\s*$", ln)
        if m:
            sig = " ".join(filas[i + 1:i + 3])
            lineas.append({"codigo": m.group(1).upper(), "descripcion": m.group(2).strip(), "um": m.group(3).strip(),
                           "cantidad": _num(m.group(4)), **_lote_en(sig)})
    if not lineas:
        raise BusinessError("No se encontraron los bienes de la guía (código, descripción y cantidad).")
    for x in lineas:
        x.setdefault("lote", "")
        x.setdefault("fp", "")
        x.setdefault("fv", "")
    g["lineas"] = lineas
    return g


def _x(el, *nombres):
    """Primer descendiente con alguno de esos nombres locales (sin espacio de nombres)."""
    for e in el.iter():
        if e.tag.split("}")[-1] in nombres:
            return e
    return None


def _xs(el, nombre):
    return [e for e in el.iter() if e.tag.split("}")[-1] == nombre]


def parse_xml(data):
    """Lee el XML UBL de la guía de remisión (DespatchAdvice) que entrega SUNAT."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise BusinessError("El XML de la guía no es válido.") from None
    if root.tag.split("}")[-1] != "DespatchAdvice":
        raise BusinessError("El XML no es una guía de remisión (DespatchAdvice).")
    ident = next((e.text for e in root if e.tag.split("}")[-1] == "ID"), "") or ""
    if "-" not in ident:
        raise BusinessError("El XML no trae la serie y el número de la guía.")
    serie, numero = ident.split("-", 1)
    g = {"serie": serie.strip(), "numero": str(int(numero.strip()))}
    fe = next((e.text for e in root if e.tag.split("}")[-1] == "IssueDate"), "")
    g["fecha_emision"] = _fecha(fe) if fe else None
    sp = _x(root, "ShipmentPeriod", "TransitPeriod")
    st = _x(sp, "StartDate") if sp is not None else None
    g["fecha_traslado"] = _fecha(st.text) if st is not None and st.text else g["fecha_emision"]
    dc = _x(root, "DeliveryCustomerParty")
    g["destinatario_ruc"] = (_x(dc, "ID").text or "").strip() if dc is not None and _x(dc, "ID") is not None else ""
    nom = _x(dc, "RegistrationName") if dc is not None else None
    g["destinatario"] = (nom.text or "").strip() if nom is not None else ""
    mot = _x(root, "HandlingInstructions", "Information")
    g["motivo"] = (mot.text or "").strip()[:60] if mot is not None else ""
    pl = _x(root, "LicensePlateID")
    g["placa"] = (pl.text or "").replace("-", "").upper() if pl is not None else ""
    da = _x(root, "DeliveryAddress")
    g["llegada"] = " ".join((_x(da, "Line").text or "").split())[:250] if da is not None and _x(da, "Line") is not None else ""
    lineas = []
    for dl in _xs(root, "DespatchLine"):
        q = _x(dl, "DeliveredQuantity")
        it = _x(dl, "Item")
        desc = " ".join(((_x(it, "Description").text or "") if it is not None and _x(it, "Description") is not None else "").split())
        cod = _x(it, "SellersItemIdentification") if it is not None else None
        codigo = (_x(cod, "ID").text or "").strip().upper() if cod is not None and _x(cod, "ID") is not None else ""
        lineas.append({"codigo": codigo, "descripcion": re.split(r"\blote\b", desc, flags=re.I)[0].strip(),
                       "um": q.get("unitCode", "") if q is not None else "", "cantidad": _num(q.text) if q is not None else None,
                       **({"lote": "", "fp": "", "fv": ""} | _lote_en(desc))})
    if not lineas:
        raise BusinessError("El XML no trae bienes (DespatchLine).")
    g["lineas"] = lineas
    return g


def leer_archivo(path):
    if path.lower().endswith(".xml"):
        with open(path, "rb") as f:
            return parse_xml(f.read())
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
        return parse_text(texto)
    raise BusinessError("Suba el PDF de la guía de SUNAT o su XML.")


# ------------------------------------------------------------------ registro y OV
def _req(user):
    if not has_perm(user, "guias.sunat_cargar"):
        raise BusinessError("Cargan las guías de SUNAT Distribución y el Auxiliar de Despacho.")


def candidatas(g):
    """OV abiertas del destinatario que tienen los productos de la guía (las de más coincidencias primero)."""
    from ..models import Customer
    if not g.destinatario_ruc:
        return []
    cods = {x["codigo"] for x in g.lineas or []}
    out = []
    for o in db().execute(select(SalesOrder).join(Customer).where(
            Customer.ruc == g.destinatario_ruc,
            SalesOrder.estado.notin_(("CANCELADA", "ENTREGADA", "BORRADOR")))).scalars():
        n = len(cods & {l.product_code for l in o.lines if l.activa})
        if n:
            out.append((n, o))
    out.sort(key=lambda x: (-x[0], x[1].fecha_compromiso or date.max))
    return [o for _, o in out]


def registrar(user, path, nombre_archivo="", archivo_rel=""):
    _req(user)
    d = leer_archivo(path)
    ya = db().execute(select(SunatGuide).where(SunatGuide.serie == d["serie"], SunatGuide.numero == d["numero"],
                                               SunatGuide.estado != "ANULADA")).scalars().first()
    if ya is not None:
        raise BusinessError(f"La guía {d['serie']}-{d['numero']} ya está cargada (#{ya.id}).")
    g = SunatGuide(serie=d["serie"], numero=d["numero"], fecha_emision=d.get("fecha_emision"),
                   fecha_traslado=d.get("fecha_traslado"), motivo=d.get("motivo", "")[:60],
                   destinatario_ruc=d.get("destinatario_ruc", ""), destinatario=(d.get("destinatario") or "")[:200],
                   llegada=d.get("llegada", ""), placa=d.get("placa", ""), lineas=d["lineas"],
                   archivo=archivo_rel or __import__("os").path.basename(path),
                   user_id=user.id, inventario={}, sap={})
    db().add(g)
    db().flush()
    cand = candidatas(g)
    if len(cand) == 1:
        unir(user, g, cand[0].id)
    alerts.emit("GUIA_SUNAT_INVENTARIO", f"Guía SUNAT {g.serie}-{g.numero}: ¿ya se descontó del inventario?",
                f"{g.destinatario or g.destinatario_ruc} · {len(g.lineas)} producto(s). Indique si el producto ya se descontó "
                "del inventario o si hay que descontarlo.", "SunatGuide", g.id, creado_por=user,
                dedup_key=f"GUIA_SUNAT_INV:{g.id}")
    audit(user, "GUIA_SUNAT_CARGADA", "SunatGuide", g.id, {"guia": f"{g.serie}-{g.numero}", "archivo": nombre_archivo})
    return g


def unir(user, g, order_id=None, sap_ov="", motivo=""):
    _req(user)
    o = db().get(SalesOrder, int(order_id)) if order_id else None
    if order_id and o is None:
        raise BusinessError("OV no encontrada.")
    if not o and not (sap_ov or "").strip():
        raise BusinessError("Elija la OV del módulo o escriba el número de la OV en SAP.")
    # solo es «cambio» si pasa a otra OV (completar el número de SAP de la misma OV no lo es)
    nuevo_sap = (sap_ov or "").strip()
    cambio = bool((g.order_id and (o is None or o.id != g.order_id))
                  or (not g.order_id and g.sap_ov and (o is not None or (nuevo_sap and nuevo_sap != g.sap_ov))))
    if cambio:
        # V47: cambiar la OV de una guía ya unida (p. ej. cerraron la OV y crearon otra para la guía SUNAT)
        if (g.sap or {}).get("estado") == "OK":
            raise BusinessError("La guía ya está registrada en SAP con su OV: el cambio se hace en SAP.")
        if (g.inventario or {}).get("decision") == "DESCONTADO":
            raise BusinessError("El stock de esta guía ya se descontó con las reservas de la OV anterior: primero corrija "
                                "la decisión de inventario.")
        if not (motivo or "").strip():
            raise BusinessError("Indique por qué cambia la OV (p. ej. «se cerró la OV y se creó otra»).")
        anterior = {"order_id": g.order_id, "ov": g.order.numero if g.order else "", "sap_ov": g.sap_ov}
    g.order_id = o.id if o else None
    g.sap_ov = (sap_ov or (o.sap_docnum if o is not None and o.sap_docnum else (o.numero if o is not None else ""))).strip()[:20]
    if o is not None:  # la guía de la parada de la ruta toma el número de SUNAT si aún no tiene
        from ..models import RouteStop
        for st in db().execute(select(RouteStop).where(RouteStop.order_id == o.id)).scalars():
            if not st.guia_numero:
                st.guia_numero = f"{g.serie}-{g.numero}"
    if cambio:
        g.ediciones = list(g.ediciones or []) + [{"user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                                                  "motivo": motivo.strip(), "cambio_ov": True, "antes": anterior,
                                                  "lineas_cambiadas": False}]
        if (g.sap or {}).get("estado") == "ERROR":
            g.sap = dict(g.sap, ov_cambiada=True)
    audit(user, "GUIA_SUNAT_OV", "SunatGuide", g.id, {"ov": o.numero if o else "", "sap_ov": g.sap_ov,
                                                       **({"antes": anterior, "motivo": motivo} if cambio else {})})
    return g


# ------------------------------------------------------------------ inventario (Jefe de Operaciones)
def _lote_modulo(codigo, lote, cantidad):
    """Lote del módulo para descontar: mismo producto y lote (puntos/comas y mayúsculas indistintas), con saldo."""
    formas = {x.upper() for x in lotes_svc.escrituras(lote.upper())} | {lote.upper()}
    lots = [x for x in db().execute(select(StockLot).where(StockLot.product_code == codigo, StockLot.cantidad > 0)).scalars()
            if (x.lote or "").upper() in formas]
    lots.sort(key=lambda x: -x.cantidad)
    return lots


def decidir_inventario(user, g, decision, nota=""):
    if not has_perm(user, "guias.regularizar_inventario"):
        raise BusinessError("Esta decisión la toma el Jefe de Operaciones.")
    if g.inventario.get("decision"):
        raise BusinessError("El inventario de esta guía ya fue decidido.")
    decision = (decision or "").upper()
    if decision not in ("YA_DESCONTADO", "DESCONTAR"):
        raise BusinessError("Indique si el producto ya se descontó o si hay que descontarlo.")
    detalle = []
    if decision == "DESCONTAR":
        faltan = []
        for x in g.lineas:
            q = float(x.get("cantidad") or 0)
            lots = _lote_modulo(x["codigo"], x.get("lote") or "", q)
            disp = sum(l.cantidad for l in lots)
            if not x.get("lote") or disp + 1e-9 < q:
                faltan.append(f"{x['codigo']} lote {x.get('lote') or '(sin lote)'}: guía {q:g}, en el módulo {disp:g}")
        if faltan:
            raise BusinessError("No hay saldo suficiente para descontar: " + "; ".join(faltan) +
                                ". Revise el lote o marque «ya se descontó» si el inventario ya lo reflejaba.")
        for x in g.lineas:
            q = float(x.get("cantidad") or 0)
            for lot in _lote_modulo(x["codigo"], x["lote"], q):
                if q <= 1e-9:
                    break
                tomado = min(q, lot.cantidad)
                lot.cantidad = round(lot.cantidad - tomado, 6)
                q -= tomado
                detalle.append({"producto": x["codigo"], "lote": lot.lote, "almacen": lot.warehouse_code, "cantidad": tomado})
                _consumir_reserva(g, lot, tomado)
    g.inventario = {"decision": "DESCONTADO" if decision == "DESCONTAR" else "YA_DESCONTADO", "detalle": detalle,
                    "nota": (nota or "").strip(), "user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                    **({"historial": g.inventario["historial"]} if (g.inventario or {}).get("historial") else {})}
    alerts.close_by_system(f"GUIA_SUNAT_INV:{g.id}", "Inventario decidido")
    audit(user, "GUIA_SUNAT_INVENTARIO", "SunatGuide", g.id, g.inventario)
    return g


def corregir_inventario(user, g, motivo):
    """V42: la Gerencia o Jefatura de Operaciones corrige una decisión de inventario equivocada. Si se había descontado
    del lote, se devuelve lo descontado a los mismos lotes; la guía vuelve a «inventario por decidir» y se decide de nuevo.
    No se permite si la guía ya está registrada en SAP."""
    from ..models import StockLot as _SL
    if not has_perm(user, "guias.corregir_inventario"):
        raise BusinessError("La corrección la hace la Gerencia o la Jefatura de Operaciones.")
    if not (g.inventario or {}).get("decision"):
        raise BusinessError("Esta guía aún no tiene decisión de inventario.")
    if (g.sap or {}).get("estado") == "OK":
        raise BusinessError("La guía ya está registrada en SAP: la corrección se hace en SAP.")
    if not (motivo or "").strip():
        raise BusinessError("Indique el motivo de la corrección.")
    previa = dict(g.inventario)
    for d in previa.get("detalle") or []:
        lot = db().execute(select(_SL).where(_SL.product_code == d["producto"], _SL.lote == d["lote"],
                                             _SL.warehouse_code == d["almacen"])).scalars().first()
        if lot is not None:
            lot.cantidad = round((lot.cantidad or 0) + float(d["cantidad"]), 6)
    hist = list(previa.pop("historial", []) or [])
    hist.append(dict(previa, corregido_por=user.nombre, motivo=motivo.strip(), corregido_ts=now().isoformat(timespec="minutes")))
    g.inventario = {"historial": hist}
    audit(user, "GUIA_SUNAT_INVENTARIO_CORREGIDO", "SunatGuide", g.id, {"previa": previa, "motivo": motivo})
    return g


def _consumir_reserva(g, lot, cantidad):
    """Si la OV unida tenía reservado ese lote, la reserva se consume en lo despachado (no se descuenta dos veces)."""
    if g.order is None:
        return
    for l in g.order.lines:
        for r in l.reservations:
            if r.estado == "ACTIVA" and r.lot_id == lot.id and cantidad > 1e-9:
                usado = min(r.cantidad, cantidad)
                r.cantidad = round(r.cantidad - usado, 6)
                cantidad -= usado
                if r.cantidad <= 1e-9:
                    r.estado = "CONSUMIDA"


# ------------------------------------------------------------------ SAP
def campos_de_entregas(sl, serie=""):
    """V41: la localización de SAP exige en la entrega el tipo de operación de inventarios (campos de usuario como
    U_EXX_TIPOOPER). Logística no los escribe a mano: quedan en sus entregas. Se toman de las últimas 30 entregas de
    SAP (de la misma serie de guía si las hay) los campos U_ de tipo u operación con su valor más usado.
    {"cabecera": {campo: valor}, "lineas": {campo: valor}}"""
    import re
    from collections import Counter
    try:
        docs = sl.get_all("DeliveryNotes", {"$orderby": "DocEntry desc", "$top": "30"})[:30]
    except Exception:  # noqa: BLE001  (sin lectura posible: se envía sin estos campos, como antes)
        return {}
    misma = [d for d in docs if isinstance(d, dict) and str(d.get("FolioPrefixString") or "") == str(serie)]
    docs = misma or [d for d in docs if isinstance(d, dict)]

    def mas_usados(filas):
        c, orig = {}, {}
        for f in filas:
            for k, v in f.items():
                # V42: también el «tipo de documento» de la pestaña Finanzas (campo estándar Indicator de SAP)
                if (k == "Indicator" or k.startswith("U_") and re.search(r"OPER|TPO|TIPO", k, re.I)) and v not in (None, ""):
                    c.setdefault(k, Counter())[str(v)] += 1
                    orig[(k, str(v))] = v  # se envía con el mismo tipo de dato que tiene en SAP
        return {k: orig[(k, x.most_common(1)[0][0])] for k, x in c.items()}
    out = {"cabecera": mas_usados(docs),
           "lineas": mas_usados([ln for d in docs for ln in d.get("DocumentLines") or [] if isinstance(ln, dict)])}
    # V44: la serie de numeración de SAP (p. ej. «EG07») es la de las entregas con el mismo prefijo de folio; sin ella SAP
    # usa su serie por defecto («0001») y la guía no se distingue en SAP
    con_serie = [d for d in misma if d.get("Series")]
    if not con_serie and serie:
        try:
            p = str(serie).replace("'", "''")
            con_serie = [d for d in sl.get_all("DeliveryNotes", {"$filter": f"FolioPrefixString eq '{p}'",
                                                                  "$select": "DocEntry,Series,FolioPrefixString",
                                                                  "$orderby": "DocEntry desc", "$top": "5"})[:5]
                         if isinstance(d, dict) and d.get("Series") and str(d.get("FolioPrefixString") or "") == str(serie)]
        except Exception:  # noqa: BLE001
            con_serie = []
    if con_serie:
        out["series"] = Counter(d["Series"] for d in con_serie).most_common(1)[0][0]
    return out


def enviar_sap(user, g, sl=None):
    """Crea en SAP la entrega (guía) basada en la OV de SAP, con la serie y el número de SUNAT y los lotes."""
    from . import sap_sl
    if not has_perm(user, "stock.ingreso_sap"):  # V35: la Jefatura de Operaciones la reenvía tras el préstamo
        _req(user)
    if not g.sap_ov:
        raise BusinessError("Primero una la guía a su OV (o indique el número de la OV en SAP).")
    if (g.sap or {}).get("estado") == "OK":
        raise BusinessError("La guía ya está registrada en SAP.")
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    try:
        if propio:
            sl.login()
        motivo = sap_sl.write_enabled(sl.cfg)
        if motivo:
            raise BusinessError(motivo)
        ords = sl.get_all("Orders", {"$filter": f"DocNum eq {int(g.sap_ov)}", "$select": "DocEntry,DocNum,CardCode,DocumentLines"})
        if not ords:
            raise BusinessError(f"No se encontró la OV {g.sap_ov} en SAP.")
        # V34: el número de OV se repite entre series: se toma la que tiene saldo abierto de los productos de la guía
        codigos = {x["codigo"] for x in g.lineas}

        def _cubre(o):
            abiertos = {ln.get("ItemCode") for ln in o.get("DocumentLines") or [] if float(ln.get("RemainingOpenQuantity") or 0) > 0}
            return len(codigos & abiertos)
        ov = max(ords, key=_cubre)
        abiertas = {}
        for ln in ov.get("DocumentLines") or []:
            abiertas.setdefault(ln.get("ItemCode"), []).append(ln)
        # V34: una sola línea de entrega por línea de la OV (SAP no acepta dos líneas con la misma BaseLine); los lotes
        # del mismo producto van juntos en BatchNumbers. Si la OV tiene el producto en varias líneas, se reparte por saldo.
        por_linea, orden = {}, []
        saldo = {}
        for x in g.lineas:
            cant = float(x["cantidad"] or 0)
            cand = [ln for ln in abiertas.get(x["codigo"], []) if float(ln.get("RemainingOpenQuantity") or 0) > 0]
            if not cand:
                raise BusinessError(f"La OV {g.sap_ov} no tiene saldo abierto de {x['codigo']} en SAP.")
            lot_mod = _lote_modulo(x["codigo"], x.get("lote") or "", 0)
            lote_sap = lot_mod[0].lote if lot_mod else (x.get("lote") or "").upper()
            for ln in cand:
                if cant <= 1e-9:
                    break
                k = ln["LineNum"]
                libre = saldo.setdefault(k, float(ln.get("RemainingOpenQuantity") or 0))
                usar = min(cant, libre) if ln is not cand[-1] else cant  # lo que exceda va en la última línea (SAP avisa)
                if usar <= 1e-9:
                    continue
                if k not in por_linea:
                    por_linea[k] = {"BaseType": 17, "BaseEntry": ov["DocEntry"], "BaseLine": k, "Quantity": 0.0,
                                    "BatchNumbers": []}
                    orden.append(k)
                d = por_linea[k]
                d["Quantity"] = round(d["Quantity"] + usar, 6)
                if lote_sap:
                    b = next((b for b in d["BatchNumbers"] if b["BatchNumber"] == lote_sap), None)
                    if b:
                        b["Quantity"] = round(b["Quantity"] + usar, 6)
                    else:
                        d["BatchNumbers"].append({"BatchNumber": lote_sap, "Quantity": usar})
                saldo[k] = libre - usar
                cant -= usar
        lines = [por_linea[k] for k in orden]
        for d in lines:
            if not d["BatchNumbers"]:
                d.pop("BatchNumbers")
        body = {"CardCode": ov["CardCode"], "DocDate": (g.fecha_traslado or g.fecha_emision or date.today()).isoformat(),
                "FolioPrefixString": g.serie, "FolioNumber": int(g.numero),
                "Comments": f"Guía emitida en SUNAT {g.serie}-{g.numero} (regularizada desde el módulo de operaciones)",
                "DocumentLines": lines}
        udf = campos_de_entregas(sl, g.serie)  # V41: tipo de operación de la localización, como en las entregas de SAP
        for k, v in udf.get("cabecera", {}).items():
            body.setdefault(k, v)
        if udf.get("series"):
            body["Series"] = udf["series"]
        for k, v in udf.get("lineas", {}).items():
            for d in lines:
                d.setdefault(k, v)
        r = sl._req("POST", "DeliveryNotes", body)
    except BusinessError as e:
        g.sap = {"estado": "ERROR", "error": str(e)[:500], "ts": now().isoformat(timespec="minutes"),
                 **({"udf": udf} if locals().get("udf") else {})}
        audit(user, "GUIA_SUNAT_SAP_ERROR", "SunatGuide", g.id, g.sap)
        if es_inventario_negativo(str(e)):
            pedir_prestamo(user, g, str(e))
        raise
    finally:
        if propio:
            try:
                sl.logout()
            except BusinessError:
                pass
    g.sap = {"estado": "OK", "docentry": r.get("DocEntry"), "docnum": r.get("DocNum"), "user": user.nombre,
             "ts": now().isoformat(timespec="minutes"), **({"udf": udf} if udf else {})}
    g.estado = "ENVIADA_SAP"
    audit(user, "GUIA_SUNAT_SAP", "SunatGuide", g.id, g.sap)
    return g



# ------------------------------------------------------------------ V35 (14-nov-2026)
def es_inventario_negativo(msg):
    m = (msg or "").lower()
    return "negative inventory" in m or "inventario negativo" in m or "falls into negative" in m


def pedir_prestamo(user, g, error=""):
    """SAP no acepta la guía porque el stock ya se descontó en SAP (p. ej. por un reconteo del mismo día): queda un
    PRÉSTAMO pendiente y se avisa a la Jefatura de Operaciones, la Coordinación de Distribución y la Jefatura de Logística
    para que se ingrese la mercadería (Ingreso de mercadería) y la guía pueda pasar a SAP."""
    if (g.prestamo or {}).get("estado") == "PENDIENTE":
        return g
    g.prestamo = {"estado": "PENDIENTE", "error": (error or "")[:300], "ts": now().isoformat(timespec="minutes"),
                  "lineas": [{"codigo": x["codigo"], "descripcion": x.get("descripcion", ""), "lote": x.get("lote", ""),
                              "cantidad": x.get("cantidad"), "fp": x.get("fp", ""), "fv": x.get("fv", "")} for x in g.lineas]}
    alerts.emit("PRESTAMO_STOCK", f"Guía {g.serie}-{g.numero}: SAP no tiene stock para registrarla (préstamo)",
                "SAP rechazó la guía por inventario negativo: el stock ya se descontó en SAP (p. ej. por un reconteo). "
                "Para que la guía pase a SAP, registre el ingreso de mercadería (préstamo) de: "
                + "; ".join(f"{x['codigo']} lote {x.get('lote') or '—'} × {x.get('cantidad')}" for x in g.lineas[:10])
                + ". El inventario del módulo no se toca: revise la decisión de inventario de la guía para no descontar dos "
                  "veces.", "SunatGuide", g.id, prioridad="ALTA", dedup_key=f"PRESTAMO:{g.id}", creado_por=user)
    audit(user, "GUIA_SUNAT_PRESTAMO", "SunatGuide", g.id, {"error": error[:300]})
    return g


def conciliar_con_sap():
    """Las guías SUNAT del módulo que alguien ya registró en SAP (o que el módulo registró) quedan como «en SAP» con su
    entrega, según las guías leídas de SAP (historial). Devuelve cuántas se actualizaron."""
    from ..models import SapMovement, SunatGuide
    n = 0
    for g in db().execute(select(SunatGuide).where(SunatGuide.estado != "ANULADA")).scalars():
        if (g.sap or {}).get("estado") == "OK":
            continue
        try:
            folio = f"{g.serie.upper()}-{int(g.numero)}"
        except ValueError:
            folio = f"{g.serie.upper()}-{g.numero}"
        m = db().execute(select(SapMovement).where(SapMovement.tipo == "GUIA", SapMovement.documento == folio)).scalars().first()
        if m is None:
            continue
        g.sap = {"estado": "OK", "docentry": m.docentry, "docnum": "", "origen": "SAP", "ts": now().isoformat(timespec="minutes"),
                 "nota": "Registrada en SAP (encontrada en las guías de SAP)"}
        g.estado = "ENVIADA_SAP"
        if (g.prestamo or {}).get("estado") == "PENDIENTE":
            g.prestamo = dict(g.prestamo, estado="RESUELTO_EN_SAP")
        n += 1
    return n


# ------------------------------------------------------------------ V46: editar la guía al subirla
def editar(user, g, datos):
    """Quien sube la guía puede corregirla (lo que leyó del PDF/XML puede no ser lo que salió: «salió menos», un lote
    distinto, una línea de más) y dejar una observación. datos: dict/MultiDict con fecha_traslado, placa, observacion,
    motivo (obligatorio si cambian las líneas) y las listas codigo, descripcion, lote, fp, fv, cantidad, um.
    No se edita una guía ya registrada en SAP ni una cuyo stock ya se descontó en el módulo (primero se corrige esa
    decisión). Cada edición queda en el historial de la guía y en la auditoría."""
    from ..models import Product
    if not (has_perm(user, "guias.sunat_cargar") or has_perm(user, "guias.regularizar_inventario")):
        raise BusinessError("Editan la guía Distribución y la Jefatura de Operaciones.")
    if (g.sap or {}).get("estado") == "OK":
        raise BusinessError("La guía ya está registrada en SAP: la corrección se hace en SAP.")
    if (g.inventario or {}).get("decision") == "DESCONTADO":
        raise BusinessError("El stock de esta guía ya se descontó en el módulo: primero corrija la decisión de inventario.")
    get = datos.getlist if hasattr(datos, "getlist") else (lambda k: datos.get(k) or [])
    cods, descs, lotes_, fps, fvs, cants, ums = (get(k) for k in ("codigo", "descripcion", "lote", "fp", "fv", "cantidad", "um"))
    nuevas = []
    for i, code in enumerate(cods):
        code = (code or "").strip().upper()
        q = (cants[i] if i < len(cants) else "") or ""
        if not code and not str(q).strip():
            continue
        if not code:
            raise BusinessError(f"Línea {i + 1}: falta el código.")
        try:
            cant = float(str(q).replace(",", "."))
        except ValueError:
            raise BusinessError(f"Línea {i + 1} ({code}): cantidad no válida.")
        if cant < 0:
            raise BusinessError(f"Línea {i + 1} ({code}): la cantidad no puede ser negativa.")
        p = db().get(Product, code)
        nuevas.append({"codigo": code, "descripcion": ((descs[i] if i < len(descs) else "") or (p.descripcion if p else "")).strip(),
                       "lote": ((lotes_[i] if i < len(lotes_) else "") or "").strip(),
                       "fp": ((fps[i] if i < len(fps) else "") or "").strip(), "fv": ((fvs[i] if i < len(fvs) else "") or "").strip(),
                       "cantidad": cant, "um": ((ums[i] if i < len(ums) else "") or "").strip()})
    if not nuevas:
        raise BusinessError("La guía debe tener al menos una línea.")
    antes = {"lineas": list(g.lineas or []), "fecha_traslado": g.fecha_traslado.isoformat() if g.fecha_traslado else "",
             "placa": g.placa, "observacion": g.observacion or ""}
    def clave(xs):
        return [(str(x.get("codigo") or ""), str(x.get("lote") or ""), float(x.get("cantidad") or 0),
                 str(x.get("fp") or ""), str(x.get("fv") or "")) for x in xs]
    cambia_lineas = clave(antes["lineas"]) != clave(nuevas)
    motivo = (datos.get("motivo") or "").strip()
    if cambia_lineas and not motivo:
        raise BusinessError("Indique el motivo del cambio en las líneas (p. ej. «salió menos», «lote distinto»).")
    ft = (datos.get("fecha_traslado") or "").strip()
    if ft:
        try:
            g.fecha_traslado = date.fromisoformat(ft)
        except ValueError:
            raise BusinessError("Fecha de traslado no válida.")
    g.placa = (datos.get("placa") if datos.get("placa") is not None else g.placa or "").strip().upper()[:15]
    g.observacion = (datos.get("observacion") if datos.get("observacion") is not None else g.observacion or "").strip()
    g.lineas = nuevas
    if (g.sap or {}).get("estado") == "ERROR":
        g.sap = dict(g.sap, editada_despues_del_error=True)
    g.ediciones = list(g.ediciones or []) + [{"user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                                              "motivo": motivo, "antes": antes,
                                              "lineas_cambiadas": cambia_lineas}]
    audit(user, "GUIA_SUNAT_EDITADA", "SunatGuide", g.id, {"motivo": motivo, "antes": antes, "despues": nuevas})
    return g
