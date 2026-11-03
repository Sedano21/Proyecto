"""Ficha de cliente (observaciones al demo v0.5, 13-oct): datos, lugares de entrega, contacto, condiciones, penalidades
y comportamiento de compra. Los datos también se cargan desde el maestro de clientes exportado de SAP."""
from collections import Counter, defaultdict
from statistics import mean

from sqlalchemy import select

from ..db import db
from ..models import Customer, CustomerSite, Incident, SalesOrder
from .core import BusinessError, audit, has_perm, param

CAMPOS = ("nombre", "grupo", "direccion", "distrito", "provincia", "horario_recepcion", "contacto", "telefono", "correo",
          "codigo_sap", "observaciones", "certificaciones", "penalidades")
MAX_CONTACTOS = 3  # hasta 3 celulares y 3 correos (observaciones al demo v0.6)


def _lista(datos, clave):
    if hasattr(datos, "getlist"):
        vals = datos.getlist(clave)
    else:
        vals = datos.get(clave) or []
        vals = [vals] if isinstance(vals, str) else list(vals)
    return [str(v).strip() for v in vals if str(v or "").strip()]


def _require(user):
    if not has_perm(user, "clientes.editar"):
        raise BusinessError("La ficha del cliente la modifica o completa solo el área Comercial.")


def _ubigeo(valor, obligatorio):
    v = (valor or "").strip()
    if not v and obligatorio:
        raise BusinessError("El ubigeo (6 dígitos) es obligatorio: se usa en la guía de remisión.")
    if v and (not v.isdigit() or len(v) != 6):
        raise BusinessError("Ubigeo inválido: son 6 dígitos (departamento, provincia y distrito).")
    return v


TIPOS_DOCUMENTO = {"RUC": "RUC (11 dígitos)", "DNI": "DNI (8 dígitos)",
                   "EXTRANJERO": "Cliente del extranjero (identificación fiscal de su país)"}
PAISES_PERU = ("", "PE", "PER", "PERU", "PERÚ")


def check_document(numero, tipo=None, pais=None):
    """V16: valida el documento del cliente según su tipo. Perú: RUC de 11 dígitos o DNI de 8. Extranjero: la
    identificación fiscal de su país (letras, números, guion o punto; 3 a 20 caracteres) y el país obligatorio.
    Devuelve (número, tipo, país)."""
    import re
    numero = (numero or "").strip()
    pais = (pais or "").strip()
    tipo = (tipo or "").strip().upper() or ("DNI" if len(numero) == 8 and numero.isdigit() else "RUC")
    if tipo == "EXTRANJERO":
        numero = numero.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/ ]{1,18}[A-Z0-9]", numero):
            raise BusinessError("Identificación del cliente del extranjero: 3 a 20 letras o números (puede llevar guion o punto).")
        if pais.upper() in PAISES_PERU:
            raise BusinessError("Indique el país del cliente del extranjero.")
        return numero, tipo, pais.upper()[:60]
    if tipo == "DNI" and not (numero.isdigit() and len(numero) == 8):
        raise BusinessError("DNI: 8 dígitos.")
    if tipo == "RUC" and not (numero.isdigit() and len(numero) == 11):
        raise BusinessError("RUC: 11 dígitos. Si el cliente es del extranjero, elija «Cliente del extranjero».")
    if tipo not in TIPOS_DOCUMENTO:
        raise BusinessError("Tipo de documento no válido.")
    return numero, tipo, "PERÚ"


def save_customer(user, c, datos):
    _require(user)
    nuevo = c is None
    if nuevo:
        ruc, tipo_doc, pais = check_document(datos.get("ruc"), datos.get("tipo_documento"), datos.get("pais"))
        if db().execute(select(Customer).where(Customer.ruc == ruc)).scalars().first():
            raise BusinessError("Ya existe un cliente con ese RUC o documento.")
        # ronda 23-oct-2026: el cliente creado en el módulo empieza como prospecto (pasa a cliente con una acción y su
        # orden de compra) y sin condición de pago: Finanzas la aprueba
        c = Customer(ruc=ruc, nombre="", condicion_estado="SIN_SOLICITAR", tipo_documento=tipo_doc, pais=pais,
                     es_prospecto=str(datos.get("prospecto", "1")) in ("1", "on", "true", "True"))
        db().add(c)
    if nuevo or "ubigeo" in datos:  # el ubigeo es peruano: no se exige al cliente del extranjero
        c.ubigeo = _ubigeo(datos.get("ubigeo"), nuevo and c.tipo_documento != "EXTRANJERO")
    for k in CAMPOS:
        if k in datos and datos[k] is not None:
            setattr(c, k, str(datos[k]).strip())
    # V7: se respetan los códigos de SAP; el cliente nuevo recibe el siguiente código correlativo con el mismo formato
    if nuevo and not (c.codigo_sap or "").strip():
        from .penalties import next_customer_code
        c.codigo_sap = next_customer_code()
    if c.codigo_sap and db().execute(select(Customer).where(Customer.codigo_sap == c.codigo_sap,
                                                            Customer.id != (c.id or 0))).scalars().first():
        raise BusinessError(f"El código de cliente {c.codigo_sap} ya pertenece a otro cliente (código de SAP).")
    if "canal_precio" in datos and (datos.get("canal_precio") or "") != (c.canal_precio or ""):
        if not has_perm(user, "clientes.canal"):
            raise BusinessError("El canal de precios del cliente lo asigna el Jefe Comercial o Sistemas.")
        audit(user, "CLIENTE_CANAL", "Customer", c.ruc, {"antes": c.canal_precio, "despues": datos["canal_precio"]})
        c.canal_precio = (datos["canal_precio"] or "").strip()
    if "requiere_cita" in datos:
        c.requiere_cita = str(datos["requiere_cita"]) in ("1", "true", "True", "on")
    if "requiere_auxiliar" in datos:  # V8 (D01): el cliente pide auxiliar acompañante en la entrega
        c.requiere_auxiliar = str(datos["requiere_auxiliar"]) in ("1", "true", "True", "on")
    if "vida_util_min_dias" in datos:
        v = str(datos.get("vida_util_min_dias") or "").strip()
        c.vida_util_min_dias = int(v) if v else None
    if "celulares" in datos:
        cels = _lista(datos, "celulares")
        if len(cels) > MAX_CONTACTOS:
            raise BusinessError("Máximo 3 celulares.")
        if any(not x.replace(" ", "").replace("+", "").isdigit() for x in cels):
            raise BusinessError("Celular inválido (solo números).")
        c.celulares = cels
    if "correos" in datos:
        mails = _lista(datos, "correos")
        if len(mails) > MAX_CONTACTOS:
            raise BusinessError("Máximo 3 correos.")
        if any("@" not in x for x in mails):
            raise BusinessError("Correo inválido.")
        c.correos = mails
        c.correo = mails[0] if mails else ""
    if "tiene_contrato" in datos:
        c.tiene_contrato = str(datos["tiene_contrato"]) in ("1", "true", "True", "on")
    if datos.get("contrato_archivo"):
        c.contrato_archivo = datos["contrato_archivo"]
        c.tiene_contrato = True
    if "vendedor_id" in datos:
        v = str(datos.get("vendedor_id") or "").strip()
        c.vendedor_id = int(v) if v else None
    if c.correo and "@" not in c.correo:
        raise BusinessError("Correo inválido.")
    if not c.nombre:
        raise BusinessError("Nombre obligatorio.")
    db().flush()
    audit(user, "CLIENTE_GUARDADO", "Customer", c.ruc, {"nuevo": nuevo})
    return c


def save_site(user, c, datos, site=None):
    _require(user)
    nuevo = site is None
    if site is None:
        site = CustomerSite(customer_id=c.id, nombre="")
        db().add(site)
    if nuevo or "ubigeo" in datos:
        site.ubigeo = _ubigeo(datos.get("ubigeo"), nuevo)
    for k in ("nombre", "direccion", "distrito", "provincia", "referencia", "horario_recepcion", "contacto", "telefono"):
        if k in datos:
            setattr(site, k, (datos.get(k) or "").strip())
    if "activo" in datos:
        site.activo = str(datos["activo"]) in ("1", "on", "true")
    if hasattr(datos, "getlist") and "c_nombre" in datos:  # V14: varios contactos, teléfonos y correos por lugar
        import re
        contactos = []
        for n, t, m in zip(datos.getlist("c_nombre"), datos.getlist("c_telefono"), datos.getlist("c_correo")):
            n, t, m = n.strip(), t.strip(), m.strip()
            if not (n or t or m):
                continue
            correos = [x.strip() for x in re.split(r"[;,\s]+", m) if x.strip()]
            for x in correos:
                if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", x):
                    raise BusinessError(f"Correo inválido: «{x}».")
            contactos.append({"nombre": n, "telefono": t, "correo": ", ".join(correos)})
        site.contactos = contactos
        site.contacto = contactos[0]["nombre"] if contactos else ""
        site.telefono = contactos[0]["telefono"] if contactos else ""
    if not site.nombre or not site.direccion or not site.distrito or not site.provincia:
        raise BusinessError("Nombre, dirección, distrito y provincia del lugar de entrega son obligatorios.")
    db().flush()
    audit(user, "CLIENTE_LUGAR_GUARDADO", "Customer", c.ruc, {"lugar": site.nombre})
    return site


def search(q="", grupo="", canal="", vendedor_id=None):
    """Búsqueda de clientes por nombre o RUC, grupo, canal de precios o ejecutivo comercial responsable."""
    from .prices import channel_of
    rows = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    q = (q or "").strip().upper()
    if q:
        rows = [c for c in rows if q in c.nombre.upper() or q in c.ruc]
    if grupo:
        rows = [c for c in rows if (c.grupo or "").upper() == grupo.upper()]
    if canal:
        rows = [c for c in rows if (channel_of(c) or "") == canal]
    if vendedor_id:
        vid = int(vendedor_id)
        rows = [c for c in rows if c.vendedor_id == vid or (c.vendedor_id is None and vid in _vendedores_ov(c))]
    return rows


def search_query(q="", grupo="", canal="", vendedor_id=None):
    """V19: la misma búsqueda como consulta SQL, para paginar sin traer todos los clientes."""
    from sqlalchemy import exists, func, or_
    st = select(Customer).order_by(Customer.nombre)
    q = (q or "").strip().upper()
    if q:
        st = st.where(or_(func.upper(Customer.nombre).contains(q), Customer.ruc.contains(q)))
    if grupo:
        st = st.where(func.upper(Customer.grupo) == grupo.upper())
    if canal:
        grupos = [g for g, c in (param("canal_precio_por_grupo", {}) or {}).items() if c == canal]
        cond = Customer.canal_precio == canal
        if grupos:
            cond = or_(cond, (func.coalesce(Customer.canal_precio, "") == "") & func.upper(Customer.grupo).in_(grupos))
        st = st.where(cond)
    if vendedor_id:
        vid = int(vendedor_id)
        st = st.where(or_(Customer.vendedor_id == vid,
                          Customer.vendedor_id.is_(None) & exists().where((SalesOrder.customer_id == Customer.id)
                                                                          & (SalesOrder.vendedor_id == vid))))
    return st


def _vendedores_ov(c):
    return {o.vendedor_id for o in db().execute(select(SalesOrder).where(SalesOrder.customer_id == c.id)).scalars()
            if o.vendedor_id}


def profile(c):
    """Indicadores de compra del cliente a partir de sus OV en el sistema."""
    from .orders import order_amount, order_weight_kg
    ovs = list(db().execute(select(SalesOrder).where(SalesOrder.customer_id == c.id).order_by(SalesOrder.fecha_emision)).scalars())
    validas = [o for o in ovs if o.estado not in ("CANCELADA", "BORRADOR")]  # venta real (ronda 23-oct-2026)
    fechas = sorted({o.fecha_emision for o in validas if o.fecha_emision})
    gaps = [(b - a).days for a, b in zip(fechas, fechas[1:])]
    prods = Counter()
    soles_prod = defaultdict(float)
    for o in validas:
        for l in o.lines:
            if l.activa:
                prods[l.product_code] += l.cantidad
                soles_prod[l.product_code] += l.cantidad * (l.precio_unitario or 0)
    incompletas = [o for o in validas if o.estado in ("DESPACHADA", "ENTREGADA") and any(
        l.activa and l.despachado + 1e-9 < l.cantidad for l in o.lines)]
    incid = list(db().execute(select(Incident).join(SalesOrder, Incident.order_id == SalesOrder.id)
                              .where(SalesOrder.customer_id == c.id).order_by(Incident.id.desc())).scalars())
    # pedido vs atendido vs facturado, en S/ y en kg (ronda 23-oct-2026)
    atendido_s = atendido_kg = 0.0
    for o in validas:
        for l in o.lines:
            if l.activa and l.despachado:
                atendido_s += l.despachado * (l.precio_unitario or 0)
                p = l.product
                atendido_kg += l.despachado * (1 if (p.um or "").upper().startswith("K") else (p.peso_kg or 0)) if p else 0
    from .finance import statement
    est = statement(c)
    pedido_s = sum(order_amount(o) for o in validas)
    canceladas = [o for o in ovs if o.estado == "CANCELADA"]
    return {"ovs": list(reversed(ovs))[:50], "n": len(validas), "soles": pedido_s,
            "atendido_soles": round(atendido_s, 2), "atendido_kg": round(atendido_kg, 1),
            "facturado_soles": est["facturado"], "atencion_pct": round(100 * atendido_s / pedido_s, 1) if pedido_s else None,
            "cuenta": est, "canceladas": len(canceladas), "canceladas_soles": sum(order_amount(o) for o in canceladas),
            "kg": sum(order_weight_kg(o, "solicitado")[0] for o in validas),
            "ticket": mean([order_amount(o) for o in validas]) if validas else 0,
            "ultima": fechas[-1] if fechas else None, "frecuencia_dias": round(mean(gaps), 1) if gaps else None,
            "top": [(k, q, soles_prod[k]) for k, q in prods.most_common(10)], "incompletas": len(incompletas),
            "incidencias": incid[:20]}


# ------------------------- canales y grupos (obs. demo v0.7) --------------
def customer_groups():
    """Grupos de cliente para la lista desplegable: los de SAP ya usados, los del mapeo grupo → canal y los agregados."""
    from .core import param
    vals = {(c or "").strip().upper() for c in db().execute(select(Customer.grupo)).scalars()}
    vals |= {k.strip().upper() for k in (param("canal_precio_por_grupo", {}) or {})}
    vals |= {str(x).strip().upper() for x in (param("grupos_cliente_adicionales", []) or [])}
    return sorted(v for v in vals if v)


def add_channel(user, nombre):
    """Agrega un canal de precios (Coordinador de Ventas, Jefe de Ventas o Sistemas)."""
    from .core import param, set_param
    from .prices import canales
    if not has_perm(user, "canales.gestionar"):
        raise BusinessError("Agregar canales corresponde al Coordinador de Ventas, al Jefe de Ventas o a Sistemas.")
    n = " ".join((nombre or "").upper().split())
    if not n:
        raise BusinessError("Indique el nombre del canal.")
    if n in canales():
        raise BusinessError(f"El canal {n} ya existe.")
    set_param("canales_adicionales", list(param("canales_adicionales", []) or []) + [n], user)
    audit(user, "CANAL_AGREGADO", "Param", "canales_adicionales", {"canal": n})
    return n


def add_group(user, nombre, canal=""):
    """Agrega un grupo de cliente y, si se indica, el canal de precios que le corresponde."""
    from .core import param, set_param
    from .prices import canales
    if not has_perm(user, "canales.gestionar"):
        raise BusinessError("Agregar grupos corresponde al Coordinador de Ventas, al Jefe de Ventas o a Sistemas.")
    n = " ".join((nombre or "").upper().split())
    if not n:
        raise BusinessError("Indique el nombre del grupo.")
    if n in customer_groups():
        raise BusinessError(f"El grupo {n} ya existe.")
    canal = " ".join((canal or "").upper().split())
    if canal and canal not in canales():
        raise BusinessError(f"El canal {canal} no existe: agréguelo primero.")
    set_param("grupos_cliente_adicionales", list(param("grupos_cliente_adicionales", []) or []) + [n], user)
    if canal:
        m = dict(param("canal_precio_por_grupo", {}) or {})
        m[n] = canal
        set_param("canal_precio_por_grupo", m, user)
    audit(user, "GRUPO_CLIENTE_AGREGADO", "Param", "grupos_cliente_adicionales", {"grupo": n, "canal": canal})
    return n
