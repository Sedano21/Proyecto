"""Conexión con SAP Business One mediante el Service Layer (ronda del 26-oct-2026).

El conector trae de SAP las órdenes de venta abiertas, los clientes, los artículos, las entregas (guías) y, con consultas
SQL guardadas en el Service Layer, el stock por lote y las liquidaciones de producción. Escritura en SAP (solo en las
bases de «sap_escritura_empresas»): las cotizaciones y, desde V10, las OV registradas en el módulo (crear, actualizar,
cancelar; ver push_order).

Los datos traídos se convierten al mismo formato de las exportaciones de SAP y pasan por el mismo flujo de las cargas:
validación, revisión y autorización (o autorización automática para los tipos configurados en `sap_autoconfirmar`),
con su auditoría y la conciliación de la marcha blanca.

Configuración en el servidor (variables de entorno; nunca en la base ni en el repositorio):
  SAP_SL_URL       https://servidor-sap:50000/b1s/v1   (o /b1s/v2)
  SAP_SL_COMPANY   base de datos de la empresa en SAP (CompanyDB)
  SAP_SL_USER      usuario de integración de SAP B1 (lectura; escribe OV y cotizaciones solo en bases autorizadas)
  SAP_SL_PASSWORD  su contraseña
  SAP_SL_CA        ruta del certificado de la CA del servidor SAP (si usa un certificado propio); SAP_SL_VERIFY=0 lo
                   desactiva (solo para pruebas internas)
  SAP_SYNC_USER    usuario del módulo con cuyo perfil se crean las cargas automáticas
  SAP_SYNC_MIN     minutos entre sincronizaciones automáticas (0 o vacío: solo manual)
Consultas SQL guardadas (SQLQueries del Service Layer) para lo que no tiene una entidad estándar:
  parámetro sap_consultas = {"STOCK": "<código de la consulta>", "LIQUIDACION": "<código>"} con columnas nombradas como
  en la exportación (Número de artículo, Lote, Almacén, Cantidad, Fecha de vencimiento…).
"""
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from http.cookiejar import CookieJar

from .core import BusinessError, audit, param

TIPOS_SAP = {"OV": "Órdenes de venta abiertas", "CLIENTES": "Clientes", "PRODUCTOS": "Artículos",
             "DESPACHOS": "Entregas (guías)", "STOCK": "Stock por lote", "LIQUIDACION": "Liquidaciones de producción"}
MAX_PAGINAS = 400


def _base_url(u):
    """V8 (S01): se acepta la dirección del servidor (https://servidor:50000/) y se completa la ruta del Service Layer."""
    u = (u or "").strip().rstrip("/")
    if u and "/b1s/" not in u + "/":
        u += "/b1s/v1"
    return u


def config():
    return {"url": _base_url(os.environ.get("SAP_SL_URL", "")), "company": os.environ.get("SAP_SL_COMPANY", "").strip(),
            "user": os.environ.get("SAP_SL_USER", "").strip(), "password": os.environ.get("SAP_SL_PASSWORD", ""),
            "ca": os.environ.get("SAP_SL_CA", "").strip(), "verify": os.environ.get("SAP_SL_VERIFY", "1") != "0",
            "timeout": float(os.environ.get("SAP_SL_TIMEOUT", "60") or 60)}


def configured():
    c = config()
    return bool(c["url"] and c["company"] and c["user"] and c["password"])


class SapConnectionError(BusinessError):
    """SAP no responde (túnel o red caídos): lo pendiente queda en cola y se reintenta; no es un rechazo de SAP."""


class ServiceLayer:
    """Cliente mínimo del Service Layer (OData). opener: para pruebas, función (request, timeout) → respuesta."""

    def __init__(self, cfg=None, opener=None):
        self.cfg = cfg or config()
        if not (self.cfg["url"] and self.cfg["company"] and self.cfg["user"] and self.cfg["password"]):
            raise BusinessError("La conexión con SAP no está configurada en el servidor (SAP_SL_URL, SAP_SL_COMPANY, "
                                "SAP_SL_USER, SAP_SL_PASSWORD).")
        self._manual_cookie = opener is not None  # con el opener propio, la sesión la lleva el CookieJar (incluye ROUTEID)
        if opener is not None:
            self._open = opener
        else:
            ctx = ssl.create_default_context(cafile=self.cfg["ca"] or None)
            if not self.cfg["verify"]:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            od = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()),
                                             urllib.request.HTTPSHandler(context=ctx))
            self._open = lambda req, timeout: od.open(req, timeout=timeout)
        self.session = None

    def _req(self, method, path, body=None, headers=None):
        url = path if path.startswith("http") else f"{self.cfg['url']}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=dict({"Content-Type": "application/json", "Accept": "application/json"},
                                                  **(headers or {})))
        if self.session and self._manual_cookie:
            req.add_header("Cookie", f"B1SESSION={self.session}")
        try:
            with self._open(req, self.cfg["timeout"]) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("error", {}).get("message", {})
                msg = msg.get("value") if isinstance(msg, dict) else msg
            except Exception:  # noqa: BLE001
                msg = str(e)
            raise BusinessError(f"SAP respondió {e.code}: {msg}")
        except (urllib.error.URLError, OSError) as e:
            raise SapConnectionError(f"No se pudo conectar con SAP: {e}")
        return json.loads(raw.decode() or "{}") if raw else {}

    def login(self):
        r = self._req("POST", "Login", {"CompanyDB": self.cfg["company"], "UserName": self.cfg["user"],
                                         "Password": self.cfg["password"]})
        self.session = r.get("SessionId")
        if not self.session:
            raise BusinessError("SAP no devolvió la sesión (revise la empresa, el usuario y la contraseña).")
        return r

    def logout(self):
        if self.session:
            try:
                self._req("POST", "Logout")
            finally:
                self.session = None

    def get_all(self, path, params=None):
        """GET con paginación (odata.nextLink / @odata.nextLink)."""
        q = ("?" + urllib.parse.urlencode(params, safe="$,'() ")) if params else ""
        url, out = path + q, []
        for _ in range(MAX_PAGINAS):
            r = self._req("GET", url, headers={"Prefer": "odata.maxpagesize=500"})
            out += r.get("value", [])
            nxt = r.get("odata.nextLink") or r.get("@odata.nextLink")
            if not nxt:
                return out
            url = nxt  # relativo a la raíz del Service Layer (p. ej. «Orders?$skip=500»)
        raise BusinessError("La consulta a SAP devolvió demasiadas páginas.")

    def sql_query(self, code):
        """Consulta SQL guardada en el Service Layer (SQLQueries('código')/List)."""
        return self.get_all(f"SQLQueries('{code}')/List")

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *a):
        self.logout()
        return False


# ------------------------------------------------------------------ conversión a los formatos de exportación
def _d(v):
    if not v:
        return None
    return date.fromisoformat(str(v)[:10])


def _bp_index(sl, codes):
    """RUC, dirección y grupo de los socios de negocio citados."""
    out = {}
    codes = sorted({c for c in codes if c})
    for i in range(0, len(codes), 20):
        filtro = " or ".join(f"CardCode eq '{c}'" for c in codes[i:i + 20])
        for bp in sl.get_all("BusinessPartners", {"$select": "CardCode,CardName,FederalTaxID,GroupCode,Address,City,County",
                                                  "$filter": filtro}):
            out[bp["CardCode"]] = bp
    return out


def rows_ov(sl):
    vend = {x["SalesEmployeeCode"]: x.get("SalesEmployeeName", "") for x in sl.get_all("SalesPersons")}
    ords = sl.get_all("Orders", {"$filter": "DocumentStatus eq 'bost_Open'",
                                 "$select": "DocNum,DocDate,DocDueDate,CardCode,CardName,Comments,SalesPersonCode,Address2,"
                                            "DocCurrency,PaymentGroupCode,DocumentLines"})
    bps = _bp_index(sl, [o.get("CardCode") for o in ords])
    filas = []
    for o in ords:
        bp = bps.get(o.get("CardCode"), {})
        for ln in o.get("DocumentLines") or []:
            qty = float(ln.get("Quantity") or 0)
            filas.append({"Número de documento": o.get("DocNum"), "Estado": "Abierto", "Fecha de Emisión": _d(o.get("DocDate")),
                          "Fecha de Vencimiento": _d(o.get("DocDueDate")), "Vendedor": vend.get(o.get("SalesPersonCode"), ""),
                          "Ruc": bp.get("FederalTaxID") or o.get("CardCode"), "Nombre de cliente": o.get("CardName"),
                          "Dirección": o.get("Address2") or bp.get("Address") or "", "Distrito": bp.get("County") or "",
                          "Provincia": bp.get("City") or "", "Código de Producto": ln.get("ItemCode"),
                          "Descripción de Producto": ln.get("ItemDescription"), "Solicitado": qty,
                          "Entregado": qty - float(ln.get("RemainingOpenQuantity") or 0),
                          "Unidad de medida": ln.get("UoMCode") or ln.get("MeasureUnit") or "",
                          "P. Unitario SOLES": ln.get("Price"), "Moneda": o.get("DocCurrency") or "",
                          "Comentarios": o.get("Comments") or "", "TaxCode": ln.get("TaxCode") or ""})
    # V7: las OV cerradas recientemente se traen solo para cerrar en el módulo las que SAP ya atendió (no se importan)
    desde = (date.today() - timedelta(days=7)).isoformat()
    for o in sl.get_all("Orders", {"$filter": f"DocumentStatus eq 'bost_Close' and UpdateDate ge '{desde}'",
                                   "$select": "DocNum,DocDueDate,CardCode,CardName,DocumentLines"}):
        for ln in (o.get("DocumentLines") or [])[:1]:
            filas.append({"Número de documento": o.get("DocNum"), "Estado": "Cerrado",
                          "Fecha de Vencimiento": _d(o.get("DocDueDate")), "Ruc": o.get("CardCode"),
                          "Nombre de cliente": o.get("CardName"), "Código de Producto": ln.get("ItemCode"),
                          "Solicitado": float(ln.get("Quantity") or 0)})
    return filas


def _ruc_de(bp):
    """RUC/DNI del socio de negocio: FederalTaxID (LicTradNum); si viene vacío o con otros caracteres, los dígitos del
    propio FederalTaxID o del código del cliente (en Perú es usual «C» + RUC, p. ej. C20123456789)."""
    import re
    for v in (bp.get("FederalTaxID"), bp.get("CardCode")):
        dig = re.sub(r"\D", "", str(v or ""))
        if len(dig) in (8, 11):
            return dig
    return str(bp.get("FederalTaxID") or "").strip()


def rows_clientes(sl):
    out = []
    for bp in sl.get_all("BusinessPartners", {"$filter": "CardType eq 'cCustomer'",
                                              "$select": "CardCode,CardName,FederalTaxID,Address,City,County,Phone1,"
                                                         "EmailAddress,ContactPerson"}):
        out.append({"RUC": _ruc_de(bp), "Nombre de cliente": bp.get("CardName"), "Código de cliente": bp.get("CardCode"),
                    "Dirección": bp.get("Address") or "", "Distrito": bp.get("County") or "", "Provincia": bp.get("City") or "",
                    "Teléfono": bp.get("Phone1") or "", "Correo electrónico": bp.get("EmailAddress") or "",
                    "Persona de contacto": bp.get("ContactPerson") or ""})
    return out


def rows_productos(sl):
    return [{"Código de Producto": it.get("ItemCode"), "Descripción de Producto": it.get("ItemName"),
             "PPB": it.get("SalesUnitWeight")}
            for it in sl.get_all("Items", {"$select": "ItemCode,ItemName,SalesUnitWeight", "$filter": "Valid eq 'tYES'"})]


def rows_despachos(sl, desde=None):
    desde = desde or date.today()
    ords = {}
    out = []
    for dn in sl.get_all("DeliveryNotes", {"$filter": f"DocDate ge '{desde.isoformat()}'",
                                           "$select": "DocNum,DocDate,FolioPrefixString,FolioNumber,DocumentLines"}):
        guia = f"{dn.get('FolioPrefixString') or ''}-{dn.get('FolioNumber')}" if dn.get("FolioNumber") else str(dn.get("DocNum"))
        for ln in dn.get("DocumentLines") or []:
            ov = ""
            if ln.get("BaseType") == 17 and ln.get("BaseEntry"):
                if ln["BaseEntry"] not in ords:
                    ords[ln["BaseEntry"]] = sl._req("GET", f"Orders({ln['BaseEntry']})?$select=DocNum").get("DocNum")
                ov = ords[ln["BaseEntry"]]
            out.append({"Número de OV": ov, "Número de guía": guia, "Fecha": _d(dn.get("DocDate")),
                        "Código de producto": ln.get("ItemCode"), "Cantidad": ln.get("Quantity")})
    return out


def rows_consulta(sl, tipo):
    code = (param("sap_consultas", {}) or {}).get(tipo)
    if not code:
        raise BusinessError(f"{TIPOS_SAP[tipo]}: SAP no tiene una entidad estándar para este dato; configure en "
                            f"sap_consultas la consulta SQL guardada en el Service Layer para «{tipo}».")
    return sl.sql_query(code)


def fetch(tipo, sl):
    fn = {"OV": rows_ov, "CLIENTES": rows_clientes, "PRODUCTOS": rows_productos, "DESPACHOS": rows_despachos}.get(tipo)
    return fn(sl) if fn else rows_consulta(sl, tipo)


def _write_excel(tipo, filas, upload_dir):
    from openpyxl import Workbook
    from .uploads import SPECS
    spec = SPECS[tipo]
    cab = list(dict.fromkeys(k for f in filas for k in f)) or [v[0] for v in spec["cols"].values()]
    wb = Workbook()
    ws = wb.active
    ws.title = (spec.get("hojas") or ["SAP"])[0]
    ws.append(cab)
    for f in filas:
        ws.append([f.get(c) for c in cab])
    os.makedirs(upload_dir, exist_ok=True)
    nombre = f"SAP_SL_{tipo}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    path = os.path.join(upload_dir, nombre)
    wb.save(path)
    return path, nombre


def sync(tipo, user, upload_dir, sl=None, autoconfirmar=None, solo_si_cambia=False):
    """Trae un tipo de dato de SAP y crea la carga con el flujo normal (validación y autorización)."""
    from .uploads import SPECS, confirm, create_batch
    if tipo not in TIPOS_SAP:
        raise BusinessError("Tipo de dato de SAP no válido.")
    propio = sl is None
    sl = sl or ServiceLayer()
    try:
        if propio:
            sl.login()
        filas = fetch(tipo, sl)
    finally:
        if propio:
            sl.logout()
    if not filas:
        raise BusinessError(f"SAP no devolvió datos de {TIPOS_SAP[tipo].lower()}.")
    # V8 (S07): con sincronización cada minuto no se crea una carga nueva si SAP no cambió nada desde la anterior
    import hashlib
    huella = hashlib.sha256(json.dumps(filas, sort_keys=True, default=str).encode()).hexdigest()
    from ..db import db
    from ..models import Param
    clave = f"sap_sync_huella_{tipo}"
    prev = db().get(Param, clave)
    if solo_si_cambia and prev is not None and (prev.valor or {}).get("v") == huella:
        return None
    if prev is None:
        prev = Param(key=clave, valor={"v": huella}, tipo="str", grupo="Integración SAP",
                     descripcion="Huella de la última sincronización (interno)", estado="DEFINIDO", fuente="Sistema")
        db().add(prev)
    else:
        prev.valor = {"v": huella}
    path, nombre = _write_excel(tipo, filas, upload_dir)
    b = create_batch(user, tipo, path, nombre)
    auto = autoconfirmar if autoconfirmar is not None else tipo in (param("sap_autoconfirmar", []) or [])
    if auto and b.estado != "VALIDADO_CON_ERRORES" and SPECS[tipo]["confirm_perm"]:
        confirm(b, user)
    audit(user, "SAP_SL_SINCRONIZADO", "UploadBatch", b.id, {"tipo": tipo, "filas": len(filas), "autoconfirmada": bool(auto)})
    return b


def test_connection(sl=None):
    sl = sl or ServiceLayer()
    r = sl.login()
    sl.logout()
    return {"version": r.get("Version", ""), "timeout_min": r.get("SessionTimeout")}


# ------------------------------------------------------------------ V15: estado de la conexión con SAP
def connection_state():
    """{ok, desde, error, ts}: lo actualiza la sincronización automática."""
    return param("sap_estado_conexion", {}) or {}


def _set_state(ok, error="", ahora=None):
    from ..db import db
    from ..models import Param
    from . import alerts
    ahora = ahora or datetime.now()
    prev = connection_state()
    estado = {"ok": ok, "ts": ahora.isoformat(timespec="minutes"), "error": (error or "")[:240],
              "desde": prev.get("desde") if (prev.get("ok") is False and not ok) else ahora.isoformat(timespec="minutes")}
    p = db().get(Param, "sap_estado_conexion")
    if p is None:
        p = Param(key="sap_estado_conexion", valor={"v": estado}, tipo="dict", grupo="Integración SAP",
                  descripcion="Estado de la conexión con SAP (lo actualiza la sincronización automática).", estado="DEFINIDO",
                  fuente="V15")
        db().add(p)
    else:
        p.valor = {"v": estado}
    from sqlalchemy import func, select
    from ..models import SalesOrder
    if not ok and prev.get("ok") is not False:
        cola = db().execute(select(func.count(SalesOrder.id)).where(SalesOrder.origen == "MODULO",
                                                                     SalesOrder.sap_docentry.is_(None))).scalar() or 0
        alerts.emit("SAP_SIN_CONEXION", "SAP sin conexión: lo registrado queda en cola",
                    f"{error}. Las OV y guías se guardan en el módulo y se envían solas al volver la conexión "
                    f"(OV sin número de SAP: {cola}). Revise el túnel a SAP.", "Param", "sap_estado_conexion",
                    prioridad="ALTA", dedup_key="SAP_SIN_CONEXION")
    elif ok and prev.get("ok") is False:
        alerts.close_by_system("SAP_SIN_CONEXION", f"Conexión con SAP restablecida ({ahora:%d/%m %H:%M})")
    return estado


def scheduled_sync(ahora=None):
    """Sincronización automática (SAP_SYNC_MIN) de los tipos de `sap_sync_tipos` con el perfil de SAP_SYNC_USER."""
    from flask import current_app
    from sqlalchemy import select
    from ..db import db
    from ..models import UploadBatch, User
    minutos = int(os.environ.get("SAP_SYNC_MIN", "0") or 0)
    if minutos <= 0 or not configured():
        return 0
    ahora = ahora or datetime.now()
    horario = (param("sap_sync_horario", "06:00-21:00") or "").strip()  # V8 (S07): cada minuto de 06:00 a 21:00
    if horario and "-" in horario:
        ini, fin = [x.strip() for x in horario.split("-", 1)]
        if not (ini <= f"{ahora:%H:%M}" <= fin):
            return 0
    try:  # V15: primero se comprueba la conexión (túnel); si no hay, todo queda en cola y no se generan más alertas
        test_connection()
        _set_state(True, ahora=ahora)
    except SapConnectionError as e:
        _set_state(False, str(e), ahora)
        return 0
    except BusinessError as e:  # SAP respondió pero rechazó el ingreso (usuario, clave o base)
        _set_state(False, str(e), ahora)
        return 0
    try:  # V10: primero se envían a SAP las OV del módulo (y, V12, las guías validadas); luego se trae lo que cambió en SAP
        push_pending_orders(ahora)
        push_pending_guides()
    except SapConnectionError as e:
        _set_state(False, str(e), ahora)
        return 0
    except BusinessError as e:
        from . import alerts
        alerts.emit("CARGA_SAP_DESACTUALIZADA", "No se pudo enviar las OV a SAP", str(e), "UploadBatch", "",
                    dedup_key=f"SAP_SL_PUSH:{ahora:%Y%m%d%H}")
    u = db().execute(select(User).where(User.username == os.environ.get("SAP_SYNC_USER", ""))).scalars().first()
    if u is None:
        return 0
    n = 0
    for tipo in param("sap_sync_tipos", []) or []:
        ult = db().execute(select(UploadBatch).where(UploadBatch.archivo.like(f"SAP_SL_{tipo}_%"))
                           .order_by(UploadBatch.id.desc())).scalars().first()
        if ult is not None and ult.ts and (ahora - ult.ts).total_seconds() < minutos * 60:
            continue
        try:
            if sync(tipo, u, current_app.config["UPLOAD_DIR"], solo_si_cambia=True) is not None:
                n += 1
        except SapConnectionError as e:
            _set_state(False, str(e), ahora)
            break
        except BusinessError as e:
            from . import alerts
            alerts.emit("CARGA_SAP_DESACTUALIZADA", f"Sincronización con SAP fallida: {TIPOS_SAP.get(tipo, tipo)}", str(e),
                        "UploadBatch", "", dedup_key=f"SAP_SL_ERR:{tipo}:{ahora:%Y%m%d%H}")
    return n


# ------------------------------------------------------------------ cotizaciones (ofertas de venta) – V7
def pull_quotes(user, sl=None, dias=90):
    """Trae de SAP las ofertas de venta (Quotations) de los últimos días y las registra como cotizaciones del módulo
    (origen SAP), sin duplicar: se identifican por su número de documento de SAP. Solo lectura en SAP."""
    from sqlalchemy import select
    from ..db import db
    from ..models import Customer, Product, Quote
    from .core import has_perm
    if not (has_perm(user, "oportunidades.registrar") or has_perm(user, "oportunidades.ver_todas")):
        raise BusinessError("Su rol no gestiona cotizaciones.")
    desde = (date.today() - timedelta(days=dias)).isoformat()
    own = sl is None
    sl = sl or ServiceLayer()
    if own:
        sl.login()
    try:
        docs = sl.get_all("Quotations", {"$filter": f"DocDate ge '{desde}'",
                                         "$select": "DocNum,DocDate,DocDueDate,CardCode,CardName,Comments,DocumentStatus,"
                                                    "DocTotal,DocumentLines"})
        bps = _bp_index(sl, [d.get("CardCode") for d in docs])
    finally:
        if own:
            sl.logout()
    nuevas = actualizadas = sin_cliente = 0
    for d in docs:
        bp = bps.get(d.get("CardCode"), {})
        ruc = bp.get("FederalTaxID") or ""
        c = db().execute(select(Customer).where(Customer.ruc == ruc)).scalars().first() if ruc else None
        if c is None:
            c = db().execute(select(Customer).where(Customer.codigo_sap == d.get("CardCode"))).scalars().first()
        if c is None:
            sin_cliente += 1
            continue
        filas = []
        for ln in d.get("DocumentLines") or []:
            p = db().get(Product, ln.get("ItemCode") or "")
            filas.append({"product_code": ln.get("ItemCode"), "descripcion": (p.descripcion if p else ln.get("ItemDescription")) or "",
                          "cantidad": float(ln.get("Quantity") or 0), "precio": float(ln.get("Price") or 0),
                          "um": ln.get("UoMCode") or ""})
        num = str(d.get("DocNum"))
        q = db().execute(select(Quote).where(Quote.sap_docnum == num, Quote.origen == "SAP")).scalars().first()
        estado = "EMITIDA" if d.get("DocumentStatus") in (None, "bost_Open") else "ACEPTADA"
        if q is None:
            q = Quote(numero=f"SAP-{num}", customer_id=c.id, fecha=_d(d.get("DocDate")) or date.today(),
                      vigencia=_d(d.get("DocDueDate")), lineas=filas, total=float(d.get("DocTotal") or 0),
                      observacion=d.get("Comments") or "", user_id=user.id, origen="SAP", sap_docnum=num, estado=estado)
            db().add(q)
            db().flush()
            nuevas += 1
        else:
            q.lineas, q.total, q.vigencia = filas, float(d.get("DocTotal") or 0), _d(d.get("DocDueDate"))
            if q.estado == "EMITIDA":
                q.estado = estado
            actualizadas += 1
    audit(user, "SAP_COTIZACIONES", "Quote", "", {"nuevas": nuevas, "actualizadas": actualizadas, "sin_cliente": sin_cliente})
    return {"nuevas": nuevas, "actualizadas": actualizadas, "sin_cliente": sin_cliente}


def push_quote(q, user, sl=None):
    """Registra en SAP una cotización del módulo (POST Quotations). Es ESCRITURA en SAP: solo funciona si el parámetro
    «sap_escritura_cotizaciones» fue habilitado con la autorización de la empresa; por defecto está deshabilitado."""
    if not param("sap_escritura_cotizaciones", False):
        raise BusinessError("La escritura de cotizaciones en SAP no está autorizada (parámetro «sap_escritura_cotizaciones»).")
    empresas = [e.strip().upper() for e in (param("sap_escritura_empresas", []) or [])]
    if (sl.cfg if sl is not None else config())["company"].upper() not in empresas:  # V8 (S06): solo la base autorizada
        raise BusinessError("La escritura en SAP solo está autorizada en la base de pruebas indicada en "
                            "«sap_escritura_empresas».")
    if q.origen == "SAP" or q.sap_docnum:
        raise BusinessError("La cotización ya está en SAP.")
    card = q.customer.codigo_sap
    if not card:
        raise BusinessError("El cliente no tiene código de SAP.")
    body = {"CardCode": card, "DocDate": q.fecha.isoformat(), "DocDueDate": (q.vigencia or q.fecha).isoformat(),
            "Comments": f"Cotización {q.numero} del módulo. {q.observacion or ''}"[:250],
            "DocumentLines": [{"ItemCode": f["product_code"], "Quantity": f["cantidad"], "UnitPrice": f["precio"]}
                              for f in q.lineas]}
    own = sl is None
    sl = sl or ServiceLayer()
    if own:
        sl.login()
    try:
        r = sl._req("POST", "Quotations", body)
    finally:
        if own:
            sl.logout()
    q.sap_docnum = str(r.get("DocNum") or "")
    audit(user, "SAP_COTIZACION_ENVIADA", "Quote", q.numero, {"sap_docnum": q.sap_docnum})
    return q.sap_docnum


# ------------------------------------------------------------------ OV del módulo → SAP (V10, 28-oct-2026)
# Lo registrado en el módulo debe quedar en SAP: la OV se crea en SAP (POST Orders), sus cambios se envían (PATCH) y su
# cancelación también (Cancel). Es ESCRITURA en SAP: solo en las bases de «sap_escritura_empresas» (hoy, solo la de
# pruebas) y con «sap_escritura_ov» activo. Se procesa en la sincronización automática, no al guardar: si SAP no
# responde, la OV queda pendiente y se reintenta, sin perder nada en el módulo.
OV_NO_SE_ENVIAN = ("BORRADOR", "BLOQUEADA", "REGULARIZADA", "REGULARIZADA_CERRADA", "REGULARIZACION_OBSERVADA")
OV_SE_ACTUALIZAN = ("REGISTRADA", "EVALUADA", "EN_PREPARACION", "PREPARADA")
REINTENTO_MIN = 10


def write_enabled(cfg=None):
    """None si se puede escribir OV en SAP; si no, el motivo."""
    if not param("sap_escritura_ov", False):
        return "La creación de OV en SAP está desactivada (parámetro «sap_escritura_ov»)."
    cfg = cfg or config()
    empresas = [e.strip().upper() for e in (param("sap_escritura_empresas", []) or [])]
    if (cfg.get("company") or "").upper() not in empresas:
        return f"La escritura en SAP no está autorizada para la base «{cfg.get('company') or '-'}» («sap_escritura_empresas»)."
    return None


def order_payload(o):
    lines = []
    for l in o.lines:
        if not l.activa or l.cantidad <= 0:
            continue
        d = {"ItemCode": l.product_code, "Quantity": round(l.cantidad, 6), "UnitPrice": round(l.precio_unitario or 0, 6)}
        bruto = l.cantidad * (l.precio_unitario or 0)
        if (l.descuento or 0) > 0 and bruto > 0:  # en el módulo el descuento es un importe; SAP lo recibe en %
            d["DiscountPercent"] = round(100 * l.descuento / bruto, 4)
        if l.tax_code:
            d["TaxCode"] = l.tax_code
        lines.append(d)
    body = {"CardCode": o.customer.codigo_sap or "", "DocDate": (o.fecha_emision or date.today()).isoformat(),
            "DocDueDate": o.fecha_compromiso.isoformat(), "NumAtCard": (o.oc_numero or "")[:100],
            "Comments": f"OV {o.numero} del módulo de operaciones. {o.comentarios or ''}".strip()[:254],
            "DocumentLines": lines}
    if o.direccion:
        body["Address2"] = ", ".join(x for x in (o.direccion, o.distrito, o.provincia) if x)[:254]
    return body


def _hash(body):
    import hashlib
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def pending_action(o):
    """Qué falta hacer en SAP con la OV: CREAR, ACTUALIZAR, CANCELAR o None."""
    if o.origen != "MODULO" or o.estado in OV_NO_SE_ENVIAN or o.retenida_precio:
        return None
    env = o.sap_envio or {}
    if env.get("conflicto"):  # V15: cambió en SAP; no se pisa hasta que alguien decida
        return None
    if o.estado == "CANCELADA":
        return "CANCELAR" if o.sap_docentry and not env.get("cancelada") else None
    if not o.sap_docentry:
        return "CREAR"
    if o.estado in OV_SE_ACTUALIZAN and env.get("hash") != _hash(order_payload(o)):
        return "ACTUALIZAR"
    return None


def _find_existing(sl, o):
    """OV ya creada en SAP por un envío anterior (se marca en Comentarios con «OV <número> del módulo»)."""
    marca = f"OV {o.numero} del módulo".replace("'", "''")
    try:
        r = sl._req("GET", "Orders?" + urllib.parse.urlencode(
            {"$filter": f"startswith(Comments,'{marca}') and CardCode eq '{(o.customer.codigo_sap or '').replace(chr(39), '')}'",
             "$select": "DocEntry,DocNum"}, safe="$,'() "))
    except SapConnectionError:
        raise
    except BusinessError:  # el filtro no está disponible en esta versión: se crea normalmente
        return None
    vals = r.get("value") or []
    return vals[0] if vals else None


def _sap_stamp(sl, docentry):
    """Marca de la última modificación de la OV en SAP (para detectar cambios hechos en SAP)."""
    if not docentry:
        return None
    try:
        r = sl._req("GET", f"Orders({docentry})?$select=UpdateDate,UpdateTime,DocumentStatus,Cancelled")
    except SapConnectionError:
        raise
    except BusinessError:
        return None
    return {k: r.get(k) for k in ("UpdateDate", "UpdateTime", "DocumentStatus", "Cancelled")}


def _sap_conflict(sl, o, env):
    actual = _sap_stamp(sl, o.sap_docentry)
    if not actual:
        return None
    if actual.get("Cancelled") == "tYES":
        return "La OV fue cancelada en SAP."
    if actual.get("DocumentStatus") == "bost_Close":
        return "La OV ya está cerrada en SAP (entregada o facturada)."
    previo = env.get("sap_stamp")
    if previo and (previo.get("UpdateDate"), previo.get("UpdateTime")) != (actual.get("UpdateDate"), actual.get("UpdateTime")):
        return f"La OV fue modificada en SAP ({actual.get('UpdateDate', '')[:10]} {actual.get('UpdateTime') or ''})."
    return None


def push_order(o, user=None, sl=None, forzar=False):
    """Crea, actualiza o cancela en SAP la OV del módulo. Devuelve la acción realizada (o None si no había nada)."""
    from . import alerts
    if forzar and (o.sap_envio or {}).get("conflicto"):  # decisión humana: se envía lo del módulo pese al cambio en SAP
        env0 = dict(o.sap_envio)
        env0.pop("conflicto", None)
        env0["estado"] = "PENDIENTE"
        o.sap_envio = env0
    accion = pending_action(o)
    if accion is None:
        return None
    motivo = write_enabled(sl.cfg if sl is not None else None)
    if motivo:
        raise BusinessError(motivo)
    body = order_payload(o)
    env = dict(o.sap_envio or {})
    env.update({"ts": datetime.now().isoformat(timespec="seconds"), "accion": accion})
    own = sl is None
    try:
        if accion != "CANCELAR":
            if not body["CardCode"]:
                raise BusinessError(f"El cliente {o.customer.nombre} no tiene código de SAP: créelo en SAP o registre su código.")
            if not body["DocumentLines"]:
                raise BusinessError("La OV no tiene líneas activas.")
        sl = sl or ServiceLayer()
        if own:
            sl.login()
        try:
            if accion == "CREAR":
                # V15: si un envío anterior llegó a SAP pero se cortó la respuesta (túnel caído), la OV ya existe:
                # se enlaza en lugar de crear un duplicado
                previo = _find_existing(sl, o)
                if previo:
                    r = previo
                else:
                    r = sl._req("POST", "Orders", body)
                o.sap_docentry = int(r.get("DocEntry")) if r.get("DocEntry") is not None else None
                o.sap_docnum = str(r.get("DocNum") or "")
            else:
                # V15: si en SAP la OV cambió (otra persona la editó, se cerró o se canceló) desde nuestro último
                # envío, no se sobrescribe: queda en conflicto para que Comercial o Sistemas decida
                motivo = None if forzar else _sap_conflict(sl, o, env)
                if motivo:
                    env.update({"conflicto": motivo, "estado": "CONFLICTO", "ts": datetime.now().isoformat(timespec="seconds")})
                    o.sap_envio = env
                    alerts.emit("SAP_OV_ERROR", f"OV {o.numero}: cambió en SAP; no se sobrescribió", motivo + " Revise la OV y "
                                "decida en su ficha («Enviar a SAP de todos modos» o ajustar el módulo).", "SalesOrder", o.id,
                                prioridad="ALTA", extra_users=[o.creado_por] if o.creado_por else None,
                                dedup_key=f"SAP_OV_CONF:{o.id}")
                    return None
                if accion == "ACTUALIZAR":
                    sl._req("PATCH", f"Orders({o.sap_docentry})", body, headers={"B1S-ReplaceCollectionsOnPatch": "true"})
                else:
                    sl._req("POST", f"Orders({o.sap_docentry})/Cancel")
                    env["cancelada"] = True
            env["sap_stamp"] = _sap_stamp(sl, o.sap_docentry)
            env.pop("conflicto", None)
        finally:
            if own:
                sl.logout()
    except SapConnectionError as e:  # V15: sin conexión, la OV queda en cola sin alerta por OV (hay una alerta general)
        env.update({"estado": "EN_COLA", "error": str(e)[:300]})
        o.sap_envio = env
        raise
    except BusinessError as e:
        env.update({"estado": "ERROR", "error": str(e)[:300], "intentos": int(env.get("intentos") or 0) + 1})
        o.sap_envio = env
        alerts.emit("SAP_OV_ERROR", f"OV {o.numero} no se pudo {'crear' if accion == 'CREAR' else 'actualizar'} en SAP",
                    f"{e}. Se reintenta automáticamente cada {REINTENTO_MIN} minutos.", "SalesOrder", o.id,
                    prioridad="ALTA", extra_users=[o.creado_por] if o.creado_por else None,
                    dedup_key=f"SAP_OV_ERR:{o.id}")
        raise
    if env.get("estado") == "CONFLICTO" and env.get("conflicto"):
        return None
    env.update({"estado": "CANCELADA" if accion == "CANCELAR" else "ENVIADA", "error": "", "intentos": 0,
                "hash": _hash(body)})
    alerts.close_by_system(f"SAP_OV_CONF:{o.id}", "Resuelto")
    o.sap_envio = env
    alerts.close_by_system(f"SAP_OV_ERR:{o.id}", f"OV registrada en SAP ({o.sap_docnum})")
    audit(user, f"SAP_OV_{accion}", "SalesOrder", o.numero, {"sap_docnum": o.sap_docnum, "docentry": o.sap_docentry})
    return accion


def push_pending_orders(ahora=None, sl=None):
    """Envía a SAP las OV del módulo pendientes (las que fallaron se reintentan cada REINTENTO_MIN minutos)."""
    from sqlalchemy import or_, select
    from ..db import db
    from ..models import SalesOrder
    if write_enabled(sl.cfg if sl is not None else None) or (sl is None and not configured()):
        return 0
    ahora = ahora or datetime.now()
    cand = []
    for o in db().execute(select(SalesOrder).where(SalesOrder.origen == "MODULO",
                                                   SalesOrder.estado.notin_(OV_NO_SE_ENVIAN),
                                                   or_(SalesOrder.sap_docentry.is_(None),
                                                       SalesOrder.estado.in_(OV_SE_ACTUALIZAN + ("CANCELADA",))))).scalars():
        env = o.sap_envio or {}
        if env.get("estado") == "ERROR" and env.get("ts") and \
                (ahora - datetime.fromisoformat(env["ts"])).total_seconds() < REINTENTO_MIN * 60:
            continue
        if pending_action(o):
            cand.append(o)
    if not cand:
        return 0
    own = sl is None
    sl = sl or ServiceLayer()
    if own:
        sl.login()
    n = 0
    try:
        for o in cand:
            try:
                if push_order(o, None, sl):
                    n += 1
            except SapConnectionError:
                break  # SAP no responde: el resto queda en cola para el próximo intento
            except BusinessError:
                continue
    finally:
        if own:
            sl.logout()
    return n


def push_order_now(o, user, forzar=False):
    """Envío manual (o reintento) de una OV a SAP desde su ficha."""
    from .core import has_perm
    if not (has_perm(user, "ov.modificar") or has_perm(user, "usuarios.administrar")):
        raise BusinessError("Envían la OV a SAP el Coordinador o el Jefe Comercial, o Sistemas.")
    if forzar and (o.sap_envio or {}).get("conflicto"):  # V15: decisión humana ante un cambio hecho en SAP
        env = dict(o.sap_envio)
        env.pop("conflicto", None)
        env["estado"] = "PENDIENTE"
        o.sap_envio = env
        audit(user, "SAP_OV_CONFLICTO_FORZADO", "SalesOrder", o.numero, {})
        return push_order(o, user, forzar=True)
    if pending_action(o) is None:
        raise BusinessError("La OV no tiene nada pendiente de enviar a SAP." if o.sap_docnum or o.estado == "CANCELADA" else
                            "Esta OV no se envía a SAP en su estado actual (borrador, bloqueada, retenida por precio, "
                            "regularización o cargada desde SAP).")
    if not configured():
        raise BusinessError("La conexión con SAP no está configurada en el servidor.")
    return push_order(o, user)


# ------------------------------------------------------------------ guía (entrega) en SAP – V12, 29-oct-2026
def push_delivery(o, preguia, sl=None):
    """Crea en SAP la entrega (DeliveryNotes) basada en la OV ya registrada en SAP, con lo preparado y sus lotes.
    BaseLine es la posición de la línea en la OV enviada por el módulo (mismo orden que order_payload)."""
    motivo = write_enabled(sl.cfg if sl is not None else None)
    if motivo:
        raise BusinessError(motivo)
    if not o.sap_docentry:
        raise BusinessError("La OV aún no está registrada en SAP: la guía se registrará cuando se cree la OV en SAP.")
    prep = {x["codigo"]: x for x in (preguia or {}).get("items") or []}
    lines = []
    pos = 0
    for l in o.lines:
        if not l.activa or l.cantidad <= 0:
            continue
        x = prep.get(l.product_code)
        if x and x["preparado"] > 0:
            d = {"BaseType": 17, "BaseEntry": o.sap_docentry, "BaseLine": pos, "Quantity": x["preparado"]}
            lotes = [{"BatchNumber": b["lote"], "Quantity": b["cantidad"]} for b in x.get("lotes") or [] if b.get("lote")]
            if lotes:
                d["BatchNumbers"] = lotes
            lines.append(d)
        pos += 1
    if not lines:
        raise BusinessError("La pre-guía no tiene cantidades preparadas.")
    body = {"CardCode": o.customer.codigo_sap or "", "DocDate": preguia.get("fecha_guia"), "TaxDate": preguia.get("fecha_guia"),
            "Comments": f"Guía de la OV {o.numero} (pre-guía validada en el módulo).", "DocumentLines": lines}
    own = sl is None
    sl = sl or ServiceLayer()
    if own:
        sl.login()
    try:
        r = sl._req("POST", "DeliveryNotes", body)
    finally:
        if own:
            sl.logout()
    audit(None, "SAP_GUIA_CREADA", "SalesOrder", o.numero, {"docnum": r.get("DocNum")})
    return r


def patch_delivery_date(docentry, fecha, sl=None):
    motivo = write_enabled(sl.cfg if sl is not None else None)
    if motivo:
        raise BusinessError(motivo)
    own = sl is None
    sl = sl or ServiceLayer()
    if own:
        sl.login()
    try:
        sl._req("PATCH", f"DeliveryNotes({docentry})", {"DocDate": fecha, "TaxDate": fecha})
    finally:
        if own:
            sl.logout()


def push_pending_guides(sl=None):
    """Reintento de las guías validadas que aún no están en SAP (o con un cambio de fecha pendiente)."""
    from sqlalchemy import select
    from ..db import db
    from ..models import SalesOrder
    from .guides import try_push
    if write_enabled(sl.cfg if sl is not None else None) or (sl is None and not configured()):
        return 0
    n = 0
    for o in db().execute(select(SalesOrder).where(SalesOrder.sap_docentry.isnot(None))).scalars():
        sap = (o.preguia or {}).get("sap") or {}
        if (o.preguia or {}).get("estado") == "VALIDADA" and (sap.get("estado") == "PENDIENTE" or sap.get("fecha_pendiente")):
            if try_push(o, None, sl).get("estado") == "ENVIADA":
                n += 1
    return n


# ------------------------------------------------------------------ V15: diagnóstico antes de pasar a la base real
def diagnostics():
    """Líneas de texto para revisar la integración: configuración, ingreso, lectura de maestros y documentos,
    almacenes habilitados que no existen en SAP, permiso de escritura y la cola de OV del módulo."""
    from sqlalchemy import select
    from ..db import db
    from ..models import SalesOrder, Warehouse
    out = []
    cfg = config()
    out.append(f"Service Layer: {cfg['url'] or '(sin configurar)'} · base: {cfg['company'] or '-'} · usuario: {cfg['user'] or '-'}")
    motivo = write_enabled(cfg)
    out.append("Escritura de OV en SAP: " + ("PERMITIDA en esta base" if not motivo else f"NO ({motivo})"))
    est = connection_state()
    if est:
        out.append(f"Último estado de la conexión: {'OK' if est.get('ok') else 'CAÍDA desde ' + str(est.get('desde'))} ({est.get('ts')})")
    try:
        sl = ServiceLayer()
        r = sl.login()
    except BusinessError as e:
        out.append(f"INGRESO A SAP: FALLA → {e}")
        return out
    out.append(f"Ingreso a SAP: OK (versión {r.get('Version', '-')}, sesión de {r.get('SessionTimeout', '-')} min)")
    try:
        for nombre, ruta in (("Clientes", "BusinessPartners/$count?$filter=CardType%20eq%20'cCustomer'"),
                             ("Artículos válidos", "Items/$count?$filter=Valid%20eq%20'tYES'"),
                             ("OV abiertas", "Orders/$count?$filter=DocumentStatus%20eq%20'bost_Open'"),
                             ("Entregas (guías) del mes", f"DeliveryNotes/$count?$filter=DocDate%20ge%20'{date.today().replace(day=1).isoformat()}'")):
            try:
                out.append(f"  {nombre}: {sl._req('GET', ruta)}")
            except BusinessError as e:
                out.append(f"  {nombre}: no se pudo leer → {e}")
        try:
            sap_whs = {w.get("WarehouseCode") for w in sl.get_all("Warehouses", {"$select": "WarehouseCode"})}
            hab = [w.code for w in db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True))).scalars()]
            faltan = [c for c in hab if c not in sap_whs]
            out.append(f"  Almacenes en SAP: {len(sap_whs)} · habilitados en el módulo: {len(hab)}"
                       + (f" · NO existen en SAP: {', '.join(faltan)}" if faltan else " · todos existen en SAP"))
        except BusinessError as e:
            out.append(f"  Almacenes: no se pudo leer → {e}")
        try:
            sin = [c for c in (bp.get("FederalTaxID") for bp in sl.get_all("BusinessPartners", {
                "$filter": "CardType eq 'cCustomer'", "$select": "CardCode,FederalTaxID"}))
                   if not (str(c or "").strip())]
            out.append(f"  Clientes sin RUC en SAP (FederalTaxID vacío): {len(sin)} (el módulo usa los dígitos del código si son 8 u 11)")
        except BusinessError as e:
            out.append(f"  RUC de clientes: no se pudo leer → {e}")
    finally:
        try:
            sl.logout()
        except BusinessError:
            pass
    ovs = list(db().execute(select(SalesOrder).where(SalesOrder.origen == "MODULO")).scalars())
    cola = [o for o in ovs if pending_action(o)]
    conf = [o for o in ovs if (o.sap_envio or {}).get("conflicto")]
    err = [o for o in ovs if (o.sap_envio or {}).get("estado") == "ERROR"]
    out.append(f"OV del módulo: {len(ovs)} · en cola para SAP: {len(cola)} · con error: {len(err)} · en conflicto: {len(conf)}")
    for o in err[:5]:
        out.append(f"  OV {o.numero}: {(o.sap_envio or {}).get('error', '')}")
    for o in conf[:5]:
        out.append(f"  OV {o.numero}: {(o.sap_envio or {}).get('conflicto', '')}")
    return out
