"""Conexión con SAP Business One mediante el Service Layer (ronda del 26-oct-2026). SOLO LECTURA.

El conector trae de SAP las órdenes de venta abiertas, los clientes, los artículos, las entregas (guías) y, con consultas
SQL guardadas en el Service Layer, el stock por lote y las liquidaciones de producción. No escribe nada en SAP: solo
usa GET y el inicio y cierre de sesión (POST /Login y /Logout).

Los datos traídos se convierten al mismo formato de las exportaciones de SAP y pasan por el mismo flujo de las cargas:
validación, revisión y autorización (o autorización automática para los tipos configurados en `sap_autoconfirmar`),
con su auditoría y la conciliación de la marcha blanca.

Configuración en el servidor (variables de entorno; nunca en la base ni en el repositorio):
  SAP_SL_URL       https://servidor-sap:50000/b1s/v1   (o /b1s/v2)
  SAP_SL_COMPANY   base de datos de la empresa en SAP (CompanyDB)
  SAP_SL_USER      usuario de SAP B1 de solo consulta para la integración
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
from datetime import date, datetime
from http.cookiejar import CookieJar

from .core import BusinessError, audit, param

TIPOS_SAP = {"OV": "Órdenes de venta abiertas", "CLIENTES": "Clientes", "PRODUCTOS": "Artículos",
             "DESPACHOS": "Entregas (guías)", "STOCK": "Stock por lote", "LIQUIDACION": "Liquidaciones de producción"}
MAX_PAGINAS = 400


def config():
    return {"url": os.environ.get("SAP_SL_URL", "").strip().rstrip("/"), "company": os.environ.get("SAP_SL_COMPANY", "").strip(),
            "user": os.environ.get("SAP_SL_USER", "").strip(), "password": os.environ.get("SAP_SL_PASSWORD", ""),
            "ca": os.environ.get("SAP_SL_CA", "").strip(), "verify": os.environ.get("SAP_SL_VERIFY", "1") != "0",
            "timeout": float(os.environ.get("SAP_SL_TIMEOUT", "60") or 60)}


def configured():
    c = config()
    return bool(c["url"] and c["company"] and c["user"] and c["password"])


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
            raise BusinessError(f"No se pudo conectar con SAP: {e}")
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
    return filas


def rows_clientes(sl):
    out = []
    for bp in sl.get_all("BusinessPartners", {"$filter": "CardType eq 'cCustomer'",
                                              "$select": "CardCode,CardName,FederalTaxID,Address,City,County,Phone1,"
                                                         "EmailAddress,ContactPerson"}):
        out.append({"RUC": bp.get("FederalTaxID") or "", "Nombre de cliente": bp.get("CardName"), "Código de cliente": bp.get("CardCode"),
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


def sync(tipo, user, upload_dir, sl=None, autoconfirmar=None):
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


def scheduled_sync(ahora=None):
    """Sincronización automática (SAP_SYNC_MIN) de los tipos de `sap_sync_tipos` con el perfil de SAP_SYNC_USER."""
    from flask import current_app
    from sqlalchemy import select
    from ..db import db
    from ..models import UploadBatch, User
    minutos = int(os.environ.get("SAP_SYNC_MIN", "0") or 0)
    if minutos <= 0 or not configured():
        return 0
    u = db().execute(select(User).where(User.username == os.environ.get("SAP_SYNC_USER", ""))).scalars().first()
    if u is None:
        return 0
    ahora = ahora or datetime.now()
    n = 0
    for tipo in param("sap_sync_tipos", []) or []:
        ult = db().execute(select(UploadBatch).where(UploadBatch.archivo.like(f"SAP_SL_{tipo}_%"))
                           .order_by(UploadBatch.id.desc())).scalars().first()
        if ult is not None and ult.ts and (ahora - ult.ts).total_seconds() < minutos * 60:
            continue
        try:
            sync(tipo, u, current_app.config["UPLOAD_DIR"])
            n += 1
        except BusinessError as e:
            from . import alerts
            alerts.emit("CARGA_SAP_DESACTUALIZADA", f"Sincronización con SAP fallida: {TIPOS_SAP.get(tipo, tipo)}", str(e),
                        "UploadBatch", "", dedup_key=f"SAP_SL_ERR:{tipo}:{ahora:%Y%m%d%H}")
    return n
