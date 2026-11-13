"""V32 (13-nov-2026): vigilante de SAP. Corre en su propio servicio del servidor (operaciones-sap.service), fuera de los
procesos de la web (que se renuevan cada cierto número de pedidos y cortaban las sincronizaciones largas).

Cada minuto (dentro de «sap_sync_horario»):
1. Pregunta a SAP qué documentos se crearon o modificaron desde ayer (OV, guías, facturas y notas de crédito, entradas y
   salidas de inventario). Es una consulta liviana: solo número de documento y fecha y hora de modificación.
2. Si algo cambió, trae solo eso:
   - OV → carga de OV (se aplica sola si «OV» está en «sap_autoconfirmar»; si no, queda para revisar) e historial;
   - guías → carga de guías (si está en «sap_sync_tipos») e historial;
   - facturas y notas de crédito → facturas de los últimos días (con las notas de crédito sobre OV) y facturas de reserva;
   - inventario → historial de consumos de producción y balance de peso de las órdenes de fabricación.
3. Cada hora, clientes, artículos y stock (los que estén en «sap_sync_tipos»), solo si SAP cambió.
4. Envía a SAP las OV y guías del módulo pendientes (en las bases autorizadas).

El botón «Actualizar con SAP» deja un pedido que el vigilante atiende en segundos (revisa todo sin esperar el minuto).
Si el vigilante no está corriendo, la web hace la misma revisión en segundo plano.
"""
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta

from .core import BusinessError, param

GRUPOS = {"OV": ("Orders",), "GUIAS": ("DeliveryNotes",), "FACTURAS": ("Invoices", "CreditNotes"),
          "INVENTARIO": ("InventoryGenExits", "InventoryGenEntries")}
LATIDO_MAX_SEG = 180


def _p(key, default=None):
    from ..db import db
    from ..models import Param
    x = db().get(Param, key)
    return (x.valor or {}).get("v", default) if x is not None and isinstance(x.valor, dict) else default


def _set(key, valor, desc):
    from ..db import db
    from ..models import Param
    s = db()
    x = s.get(Param, key)
    if x is None:
        x = Param(key=key, valor={"v": valor}, tipo="dict", grupo="Integración SAP", descripcion=desc, estado="DEFINIDO",
                  fuente="Sistema")
        s.add(x)
    else:
        x.valor = {"v": valor}


def vivo():
    """True si el vigilante dio señales de vida hace menos de 3 minutos."""
    t = _p("sap_vigia_latido")
    try:
        return t is not None and (datetime.now() - datetime.fromisoformat(t)).total_seconds() < LATIDO_MAX_SEG
    except (TypeError, ValueError):
        return False


def pedir_actualizacion(user):
    """El botón «Actualizar con SAP»: deja el pedido para el vigilante."""
    from . import sap_sl
    sap_sl._job_set("ACTUALIZAR", {"estado": "EN_CURSO", "inicio": datetime.now().isoformat(timespec="seconds"),
                                   "usuario": user.nombre, "via": "vigilante"})
    _set("sap_vigia_pedido", {"ts": datetime.now().isoformat(timespec="seconds"), "usuario": user.nombre},
         "Pedido de actualización con SAP (interno)")


def _firma(sl, entidad, desde, con_hora):
    sel = "DocEntry,UpdateDate" + (",UpdateTime" if con_hora else "")
    filas = sl.get_all(entidad, {"$select": sel, "$filter": f"UpdateDate ge '{desde.isoformat()}'"})
    datos = sorted((f.get("DocEntry"), str(f.get("UpdateDate")), str(f.get("UpdateTime", ""))) for f in filas)
    return hashlib.sha256(json.dumps(datos).encode()).hexdigest(), len(filas)


def cambios(sl, previas, hoy=None):
    """{grupo: True/False} según si cambió algún documento desde ayer, y las firmas nuevas."""
    hoy = hoy or date.today()
    desde = hoy - timedelta(days=1)
    con_hora = _p("sap_vigia_con_hora", True)
    nuevas, out = {}, {}
    for grupo, entidades in GRUPOS.items():
        partes = []
        for ent in entidades:
            try:
                partes.append(_firma(sl, ent, desde, con_hora)[0])
            except BusinessError as e:
                if con_hora and "UpdateTime" in str(e):
                    con_hora = False
                    _set("sap_vigia_con_hora", False, "El Service Layer no expone UpdateTime (interno)")
                    partes.append(_firma(sl, ent, desde, False)[0])
                else:
                    partes.append(f"error:{ent}")
        nuevas[grupo] = "|".join(partes)
        out[grupo] = nuevas[grupo] != previas.get(grupo)
    return out, nuevas


def ciclo(user, upload_dir, forzar=False, sl=None):
    """Una revisión. Devuelve el resumen de lo que se trajo."""
    from ..db import db
    from . import balance_of, facturas_reserva, sap_sl, sap_v31
    propio = sl is None
    sl = sl or sap_sl.ServiceLayer()
    res = {}
    tipos = param("sap_sync_tipos", []) or []
    auto = param("sap_autoconfirmar", []) or []

    def paso(nombre, fn):
        _set("sap_vigia_latido", datetime.now().isoformat(timespec="seconds"), "Último latido del vigilante (interno)")
        db().commit()
        try:
            with db().begin_nested():
                r = fn()
            db().commit()
            res[nombre] = r if isinstance(r, str) else "ok"
        except sap_sl.SapConnectionError:
            raise
        except BusinessError as e:
            db().rollback()
            res[nombre] = f"error: {str(e)[:150]}"

    def carga(tipo):
        b = sap_sl.sync(tipo, user, upload_dir, sl=sl, solo_si_cambia=True, autoconfirmar=tipo in auto)
        return "sin cambios" if b is None else f"carga #{b.id} ({b.estado.lower()})"
    try:
        if propio:
            sl.login()
        sap_sl._set_state(True)
        previas = _p("sap_vigia_firmas", {}) or {}
        cambio, nuevas = cambios(sl, previas)
        if forzar:
            cambio = {k: True for k in cambio}
        if cambio["OV"] or cambio["GUIAS"] or cambio["INVENTARIO"] or not sap_v31.tiene_historial():
            paso("historial", lambda: sap_v31.sync_historial(user, sl=sl))
        if cambio["FACTURAS"]:
            paso("reservas", lambda: facturas_reserva.sync(user, sl=sl))
        if cambio["OV"]:
            paso("OV", lambda: carga("OV"))
        if cambio["GUIAS"] and "DESPACHOS" in tipos:
            paso("DESPACHOS", lambda: carga("DESPACHOS"))
        if cambio["FACTURAS"]:
            paso("facturas", lambda: sap_sl.sync_facturas(user, sl=sl, desde=date.today() - timedelta(days=3)))
        if cambio["INVENTARIO"]:
            paso("balance_of", lambda: balance_of.sync(user, sl=sl))
            if "LIQUIDACION" in tipos:
                paso("LIQUIDACION", lambda: carga("LIQUIDACION"))
        ult_hora = _p("sap_vigia_horario", "")
        if forzar or not ult_hora or (datetime.now() - datetime.fromisoformat(ult_hora)).total_seconds() > 3600:
            for t in ("CLIENTES", "PRODUCTOS", "STOCK"):
                if t in tipos:
                    paso(t, lambda t=t: carga(t))
            _set("sap_vigia_horario", datetime.now().isoformat(timespec="seconds"), "Última revisión horaria (interno)")
        paso("envios", lambda: (sap_sl.push_pending_orders(sl=sl), sap_sl.push_pending_guides(sl=sl)) and "ok")
        _set("sap_vigia_firmas", nuevas, "Firmas de los documentos de SAP de ayer y hoy (interno)")
        db().commit()
    finally:
        if propio:
            try:
                sl.logout()
            except Exception:  # noqa: BLE001
                pass
    return res


def _usuario():
    from sqlalchemy import select
    from ..db import db
    from ..models import User
    u = db().execute(select(User).where(User.username == os.environ.get("SAP_SYNC_USER", ""))).scalars().first()
    return u or db().execute(select(User).where(User.role_code == "SISTEMAS", User.activo.is_(True))).scalars().first()


def _en_horario(ahora):
    h = (param("sap_sync_horario", "06:00-21:00") or "").strip()
    if h and "-" in h:
        ini, fin = [x.strip() for x in h.split("-", 1)]
        return ini <= f"{ahora:%H:%M}" <= fin
    return True


def vigilar(app, cada_seg=None, una_vez=False):
    """Bucle del servicio operaciones-sap: revisa cada «cada_seg» (60) segundos y atiende el botón en segundos."""
    from ..db import SessionLocal, db
    from . import sap_sl
    cada = int(cada_seg or os.environ.get("SAP_VIGIA_SEG", "60") or 60)
    ultimo = 0.0
    while True:
        with app.app_context():
            try:
                _set("sap_vigia_latido", datetime.now().isoformat(timespec="seconds"), "Último latido del vigilante (interno)")
                db().commit()
                pedido = _p("sap_vigia_pedido")
                ahora = datetime.now()
                if sap_sl.configured() and (pedido or (time.time() - ultimo >= cada and _en_horario(ahora))):
                    u = _usuario()
                    if u is not None:
                        ini = ahora.isoformat(timespec="seconds")
                        if pedido:
                            _set("sap_vigia_pedido", None, "Pedido de actualización con SAP (interno)")
                            db().commit()
                        try:
                            r = ciclo(u, app.config["UPLOAD_DIR"], forzar=bool(pedido))
                            if pedido:
                                sap_sl._job_set("ACTUALIZAR", {"estado": "OK", "inicio": ini, "usuario": pedido.get("usuario", ""),
                                                               "fin": datetime.now().isoformat(timespec="seconds"), "resumen": r})
                        except sap_sl.SapConnectionError as e:
                            db().rollback()
                            sap_sl._set_state(False, str(e))
                            if pedido:
                                sap_sl._job_set("ACTUALIZAR", {"estado": "ERROR", "inicio": ini, "usuario": pedido.get("usuario", ""),
                                                               "fin": datetime.now().isoformat(timespec="seconds"), "error": str(e)[:300]})
                        db().commit()
                    ultimo = time.time()
            except Exception as e:  # noqa: BLE001  (el vigilante no se detiene por un error; se registra y sigue)
                db().rollback()
                print(f"[sap-vigia] {datetime.now():%F %T} error: {e}", flush=True)
            finally:
                SessionLocal.remove()
        if una_vez:
            return
        time.sleep(5)
