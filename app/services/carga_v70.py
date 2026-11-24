"""V70 (24-nov-2026): aviso de carga entre el chofer y Almacén, y evidencias de la carga.

1. **El chofer avisa que la unidad está lista para cargar.** Marca que está limpia y dónde está: dentro del almacén
   1560, del 1524 u otro lugar (lo escribe).
2. **La alerta llega al almacén que corresponde según lo que se despacha:**
   - granel (GR) o materia prima (MP): al personal del almacén de «carga_almacen_granel» (1524);
   - producto terminado: al de «carga_almacen_pt» (1560).
   Si la ruta lleva ambos, les llega a los dos. El personal es el que tiene ese almacén asignado en su usuario; si
   no hay nadie asignado, la alerta va a los perfiles de Almacén.
3. **Almacén responde** que inició el traslado y la carga, e indica a quién se asignó. El chofer y Distribución
   reciben el aviso y pueden hacer el seguimiento.
4. **Evidencias.** Durante la carga, Almacén sube fotos del antes y del después y, si puede, un video de cómo se
   carga. Así se revisan las quejas de mercadería mal paletizada.
5. **Salida.** Antes de salir firman Seguridad, el chofer y el Auxiliar de Despacho (solo si la ruta lleva uno).
   El visto bueno de Calidad es opcional. Luego el Líder Operativo autoriza la salida, como antes."""
from sqlalchemy import select

from ..db import db
from ..models import Route, User, Warehouse, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

ETAPAS = {"carga_antes": "Antes de la carga", "carga_despues": "Después de la carga", "carga_video": "Video de la carga"}
ROLES_ALMACEN = ["LIDER_ALMACEN", "ASIST_ALMACEN", "SUPERV_ALMACEN", "COORD_ALMACEN"]


def _clave_almacen(product):
    from .stock import product_kind
    k = product_kind(product)
    return str(param("carga_almacen_granel", "1524")) if k in ("GR", "MP") else str(param("carga_almacen_pt", "1560"))


def almacenes_de(route):
    """Almacenes (1524 / 1560) a los que les toca cargar la ruta, según los productos de sus OV."""
    out = []
    for st in route.stops:
        for ln in st.order.lines:
            if ln.activa:
                k = _clave_almacen(ln.product)
                if k not in out:
                    out.append(k)
    return out


def _codigos(clave):
    """Códigos de almacén del módulo que corresponden a «1524» o «1560» (por código o por nombre)."""
    clave = str(clave).strip().upper()
    return [w.code for w in db().execute(select(Warehouse)).scalars()
            if w.code.upper() == clave or (w.nombre or "").strip().upper() == clave
            or (w.nombre or "").strip().upper().startswith(clave + " ") or clave in (w.nombre or "").upper().split()]


def personal_de(clave):
    codes = _codigos(clave)
    if not codes:
        return []
    return [u for u in db().execute(select(User).where(User.activo.is_(True), User.almacen.in_(codes))).scalars()
            if u.role_code in ROLES_ALMACEN or (u.role and getattr(u.role, "area", "") == "Almacén")]


def _es_chofer(route, user):
    drv = route.driver
    return drv is not None and drv.user_id and drv.user_id == user.id


def unidad_lista(user, route, limpia, ubicacion, otra="", nota=""):
    """El chofer avisa que la unidad está lista para cargar (limpia y dentro del almacén)."""
    sin_cuenta = route.driver is not None and not route.driver.user_id
    if not (_es_chofer(route, user) or (sin_cuenta and has_perm(user, "distribucion.programar"))
            or (route.driver is None and has_perm(user, "distribucion.programar"))):
        raise BusinessError("Avisa que la unidad está lista el chofer de la ruta.")
    if route.estado not in ("PROPUESTA", "CONFIRMADA"):
        raise BusinessError("La ruta ya salió o está cerrada.")
    if not limpia:
        raise BusinessError("Confirme que la unidad está limpia antes de avisar.")
    ubicacion = (ubicacion or "").strip()
    if ubicacion == "OTRO":
        ubicacion = (otra or "").strip()
    if not ubicacion:
        raise BusinessError("Indique dónde está la unidad (almacén 1560, 1524 u otro lugar).")
    destinos = almacenes_de(route)
    ac = dict(route.aviso_carga or {})
    ac["lista"] = {"user": user.nombre, "user_id": user.id, "ts": now().isoformat(timespec="minutes"), "limpia": True,
                   "ubicacion": ubicacion[:60], "nota": (nota or "").strip()[:300], "almacenes": destinos}
    ac.pop("respuesta", None)
    route.aviso_carga = ac
    usuarios = [u.id for k in destinos for u in personal_de(k)]
    placa = route.vehicle.placa if route.vehicle else (route.transportista or {}).get("placa", "")
    qué = " y ".join(("granel / MP" if k == str(param("carga_almacen_granel", "1524")) else "producto terminado") + f" ({k})"
                     for k in destinos)
    alerts.emit("CARGA_UNIDAD_LISTA", f"Unidad {placa} lista para cargar · ruta #{route.id}",
                f"Unidad limpia, en {ubicacion}. Cargar: {qué or 'sin productos'}. "
                f"OV: {', '.join(st.order.numero for st in route.stops)}. {nota or ''}".strip(),
                "Route", route.id, prioridad="ALTA", extra_users=usuarios,
                extra_roles=None if usuarios else ROLES_ALMACEN, dedup_key=f"CARGA_LISTA:{route.id}:{ac['lista']['ts']}",
                creado_por=user)
    audit(user, "CARGA_UNIDAD_LISTA", "Route", route.id, ac["lista"])
    return ac["lista"]


def responder(user, route, asignados, nota=""):
    """Almacén responde que inició el traslado y la carga, y a quién se lo asignó."""
    if not (has_perm(user, "picking.asignar") or has_perm(user, "distribucion.carga")):
        raise BusinessError("Responde el Líder, el Asistente, el Supervisor o el Coordinador de Almacén.")
    ac = dict(route.aviso_carga or {})
    if not ac.get("lista"):
        raise BusinessError("El chofer aún no avisó que la unidad está lista.")
    ids = []
    for x in asignados or []:
        if str(x).isdigit() and int(x) not in ids:
            ids.append(int(x))
    if not ids:
        raise BusinessError("Indique a quién asignó el traslado y la carga.")
    personas = [db().get(User, i) for i in ids]
    if any(p is None for p in personas):
        raise BusinessError("Persona no encontrada.")
    ac["respuesta"] = {"user": user.nombre, "user_id": user.id, "ts": now().isoformat(timespec="minutes"),
                       "asignados": [{"id": p.id, "nombre": p.nombre} for p in personas], "nota": (nota or "").strip()[:300]}
    route.aviso_carga = ac
    chofer = [route.driver.user_id] if route.driver and route.driver.user_id else []
    alerts.emit("CARGA_INICIADA", f"Almacén inició el traslado y la carga · ruta #{route.id}",
                f"Asignado a: {', '.join(p.nombre for p in personas)}. {nota or ''}".strip(), "Route", route.id,
                extra_users=chofer + ids, creado_por=user)
    audit(user, "CARGA_INICIADA", "Route", route.id, ac["respuesta"])
    return ac["respuesta"]


def subir_evidencia(user, route, etapa, archivos, nota=""):
    """Fotos del antes y del después de la carga y video (archivos ya guardados)."""
    if etapa not in ETAPAS:
        raise BusinessError("Elija si es el antes, el después o el video de la carga.")
    if not (has_perm(user, "picking.asignar") or has_perm(user, "distribucion.carga") or has_perm(user, "tareas.ejecutar")
            or has_perm(user, "movimiento.ejecutar")):
        raise BusinessError("Suben las evidencias de la carga el personal de Almacén.")
    if not archivos:
        raise BusinessError("Adjunte al menos una foto o video.")
    if route.estado not in ("PROPUESTA", "CONFIRMADA"):
        raise BusinessError("La ruta ya salió: las evidencias de carga se suben antes de la salida.")
    fotos = dict(route.fotos or {})
    lista = list(fotos.get(etapa) or [])
    for a in archivos:
        lista.append({"archivo": a, "user": user.nombre, "ts": now().isoformat(timespec="minutes"), "nota": (nota or "")[:200]})
    fotos[etapa] = lista
    route.fotos = fotos
    audit(user, "CARGA_EVIDENCIA", "Route", route.id, {"etapa": etapa, "archivos": len(archivos)})
    return lista


def falta_para_salir(route):
    """Lo que falta para salir: novedades de la carga sin resolver y, si se exigen, las fotos del antes y el después."""
    out = [f"resolver {'el faltante' if x['tipo'] == 'FALTANTE' else 'el sobrante'} de {x['producto']} ({x['cantidad']:g})"
           for x in novedades_abiertas(route)]
    if param("carga_exigir_fotos", False):
        f = route.fotos or {}
        out += [ETAPAS[e] for e in ("carga_antes", "carga_despues") if not f.get(e)]
    return out


def de_hoy(user=None):
    """Rutas de hoy y mañana con su aviso de carga (para la pantalla de Almacén)."""
    from datetime import date, timedelta
    hoy = date.today()
    return list(db().execute(select(Route).where(Route.fecha >= hoy - timedelta(days=1), Route.fecha <= hoy + timedelta(days=1),
                                                 Route.estado.in_(("PROPUESTA", "CONFIRMADA", "EN_RUTA")))
                             .order_by(Route.fecha, Route.id)).scalars())


# ------------------------------------------------------------------ novedades de la carga (faltante / sobrante)
PUEDEN_REPORTAR = ("distribucion.carga", "picking.asignar", "distribucion.visto_bueno_salida", "distribucion.seguridad",
                   "distribucion.visto_bueno_calidad", "tareas.ejecutar", "distribucion.entrega")


def items_carga(route):
    """SKU de la pre-guía de la ruta para elegir el que falta o sobra: [(order_line_id, texto)]."""
    from .despacho import preguia
    return [(it["order_line_id"], f"OV {g['order'].numero} · {it['codigo']} {it['descripcion']} · pre-guía {it['cantidad']:g}")
            for g in preguia(route) for it in g["items"]]


def reportar_novedad(user, route, tipo, cantidad, order_line_id=None, producto="", nota=""):
    """Al validar la carga, cualquiera de los que validan reporta ahí mismo qué SKU falta o sobra y cuánto."""
    from ..models import Product, SalesOrderLine
    from .distribution import _incident
    if not any(has_perm(user, p) for p in PUEDEN_REPORTAR):
        raise BusinessError("Reportan las novedades de la carga Almacén, el Auxiliar de Despacho, el chofer, Seguridad o Calidad.")
    if route.estado not in ("PROPUESTA", "CONFIRMADA"):
        raise BusinessError("La ruta ya salió.")
    tipo = (tipo or "").upper()
    if tipo not in ("FALTANTE", "SOBRANTE"):
        raise BusinessError("Elija si falta o sobra mercadería.")
    try:
        q = float(str(cantidad).replace(",", "."))
    except (TypeError, ValueError):
        raise BusinessError("Indique la cantidad.")
    if q <= 0:
        raise BusinessError("La cantidad debe ser mayor que 0.")
    ln = db().get(SalesOrderLine, int(order_line_id)) if str(order_line_id or "").isdigit() else None
    if ln is not None and ln.order_id not in [st.order_id for st in route.stops]:
        raise BusinessError("Ese producto no es de esta ruta.")
    code = ln.product_code if ln is not None else (producto or "").strip().upper().split(" ")[0]
    if not code or (ln is None and db().get(Product, code) is None):
        raise BusinessError("Elija el producto de la pre-guía (o escriba el código si sobra algo que no está en ella).")
    if tipo == "FALTANTE" and ln is None:
        raise BusinessError("Un faltante se reporta sobre un producto de la pre-guía.")
    ac = dict(route.aviso_carga or {})
    nov = list(ac.get("novedades") or [])
    reg = {"n": len(nov) + 1, "tipo": tipo, "producto": code, "order_line_id": ln.id if ln else None,
           "ov": ln.order.numero if ln else "", "cantidad": q, "nota": (nota or "").strip()[:300], "user": user.nombre,
           "user_id": user.id, "ts": now().isoformat(timespec="minutes"), "resuelta": None}
    nov.append(reg)
    ac["novedades"] = nov
    route.aviso_carga = ac
    route.carga_validada = False
    _incident(user, "CARGA_FALTANTE" if tipo == "FALTANTE" else "CARGA_SOBRANTE", route=route,
              order=ln.order if ln else None, cantidad=q,
              descripcion=f"{'Falta' if tipo == 'FALTANTE' else 'Sobra'} {q:g} de {code} al validar la carga. {reg['nota']}".strip())
    usuarios = [u.id for k in almacenes_de(route) for u in personal_de(k)]
    alerts.emit("CARGA_INCONGRUENCIA", f"Ruta #{route.id}: {'falta' if tipo == 'FALTANTE' else 'sobra'} {code} en la carga",
                f"{q:g} {'por completar' if tipo == 'FALTANTE' else 'por retirar'}. Reportó {user.nombre}. {reg['nota']}".strip(),
                "Route", route.id, extra_users=usuarios, creado_por=user)
    audit(user, "CARGA_NOVEDAD", "Route", route.id, reg)
    return reg


def resolver_novedad(user, route, n, nota=""):
    """Almacén completa lo que falta o retira lo que sobra y lo marca resuelto."""
    if not has_perm(user, "picking.asignar"):
        raise BusinessError("La resuelve Almacén (Líder, Asistente, Supervisor o Coordinador).")
    ac = dict(route.aviso_carga or {})
    nov = [dict(x) for x in ac.get("novedades") or []]
    x = next((x for x in nov if x["n"] == int(n)), None)
    if x is None or x.get("resuelta"):
        raise BusinessError("Novedad no encontrada o ya resuelta.")
    x["resuelta"] = {"user": user.nombre, "ts": now().isoformat(timespec="minutes"), "nota": (nota or "").strip()[:300]}
    ac["novedades"] = nov
    route.aviso_carga = ac
    audit(user, "CARGA_NOVEDAD_RESUELTA", "Route", route.id, x)
    return x


def novedades_abiertas(route):
    return [x for x in (route.aviso_carga or {}).get("novedades") or [] if not x.get("resuelta")]
