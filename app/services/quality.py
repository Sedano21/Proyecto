"""Calidad (IF §9.3, §9.4) y formatos operativos REG-*.

Cada formato se define con sus campos tal como figuran en el documento fuente. Las evaluaciones automáticas
solo usan límites documentados (PCC1 de REG-HACCP-CAL-002; especificación 'Calidad superior' de REG-CAL-005;
criterios de peso de REG-CAL-003). La decisión final (aprobado/desaprobado) la registra Calidad.
"""
from datetime import date

from sqlalchemy import func, select

from ..catalogs import CRITERIO_PESO_PENDIENTE, CRITERIOS_PESO, PCC1_HUMEDAD, SPEC_CALIDAD_SUPERIOR
from ..db import db
from ..models import Certificate, Liquidation, Product, QualityRecord, StockLot, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

DEFECTOS_MUESTREO = [
    ("humedad", "Humedad (%)"), ("grano_enfermo", "Grano enfermo (%)"), ("grano_infestado", "Grano infestado (%)"),
    ("grano_picado", "Grano picado (%)"), ("grano_partido", "Grano partido (%)"), ("grano_cascara", "Grano cáscara (%)"),
    ("grano_abierto", "Grano abierto (%)"), ("grano_descascarado", "Grano descascarado máx. (%)"),
    ("grano_arrugado", "Grano arrugado y/o chupado (%)"), ("grano_quemado", "Grano quemado (%)"),
    ("grano_panza_blanca", "Grano panza blanca (%)"), ("grano_inmaduro", "Granos inmaduros (%)"),
    ("grano_vitreo", "Grano vítreos (%)"), ("grano_germinado", "Grano germinado (%)"),
    ("total_danado", "Total grano dañado (%)"), ("materias_extranas", "Materias extrañas (%)"),
    ("variedad_contrastante", "Variedad contrastantes (%)"), ("piedras", "Piedrecillas, piedras (cantidad)"),
    ("insectos", "Insectos (cantidad)"),
]

# Definición de formatos: código, nombre, campos [(clave, etiqueta, tipo)]
FORMATOS = {
    "MUESTREO": ("REG-CAL-002 / CP-FOR-CAL-10", "Ficha de muestreo de producto",
                 [("muestra_tipo", "Muestra (MUESTRA / GRANEL / MP)", "text"), ("proveedor", "Proveedor", "text"),
                  ("procedencia", "Procedencia", "text"), ("cantidad_muestra", "Cantidad de muestra evaluada", "text")]
                 + [(k, l, "number") for k, l in DEFECTOS_MUESTREO]),
    "RECEPCION_MP": ("REG-HACCP-CAL-002", "Control de recepción de materia prima (PCC1)",
                     [("tipo_ingreso", "M.P. / SERV.", "text"), ("proveedor_cliente", "Proveedor / Cliente", "text"),
                      ("calidad", "Calidad", "text"), ("nacional_importado", "N / I", "text"),
                      ("datos_etiqueta", "Datos de etiqueta", "text"), ("sacos", "Cantidad (sacos)", "number"),
                      ("kg", "Cantidad (kg)", "number"), ("total_kg", "Total (kg)", "number"),
                      ("impurezas_conforme", "Impurezas conforme (√=sí / X=no)", "bool"),
                      ("plaga_conforme", "Plaga conforme (√=sí / X=no)", "bool"),
                      ("grupo_humedad", "Grupo PCC1", "pcc1"), ("humedad", "Humedad (%)", "number"),
                      ("sacos_muestreados", "N° sacos muestreados / FH", "text")]),
    "FUMIGACION": ("REG-BPM-CAL-005", "Registro de control de fumigación de grano",
                   [("inicio_fecha", "Inicio: fecha", "date"), ("inicio_operario", "Inicio: operario", "text"),
                    ("inicio_hora", "Inicio: hora", "text"), ("fin_fecha", "Fin (desactivación): fecha", "date"),
                    ("fin_operario", "Fin: operario", "text"), ("fin_hora", "Fin: hora", "text"),
                    ("tipo_fumigacion", "Tipo de fumigación (BL / CTNR)", "text"), ("sacos", "N° sacos", "number"),
                    ("peso_kg", "Peso (kg)", "number"), ("producto_quimico", "Producto químico", "text"),
                    ("dosis_tabletas", "Dosis (tabletas)", "number"), ("lote_quimico", "Lote del químico", "text")]),
    "NO_CONFORME": ("REG-BPM-CAL-013", "Reporte de producto no conforme",
                    [("proveedor_cliente", "Proveedor / Cliente", "text"), ("fecha_produccion", "Fecha de producción", "date"),
                     ("fecha_vencimiento", "Fecha de vencimiento", "date"), ("cantidad", "Cantidad de producto", "number"),
                     ("motivo", "Motivo de la no conformidad", "textarea"), ("acciones", "Acciones tomadas", "textarea"),
                     ("destino", "Destino (Separación / Contención / Devolución / Suspensión de provisión)", "text"),
                     ("informo_cliente", "Se informó al cliente (sí/no)", "bool"),
                     ("autoriza_concesion", "Quién autoriza la aceptación bajo concesión", "text")]),
    "QUEJA": ("REG-HACCP-CAL-003", "Quejas del cliente",
              [("cliente", "Cliente", "text"), ("motivo", "Motivo de la queja", "textarea"),
               ("disposicion", "Disposición del producto", "textarea")]),
    "NC_ACCION": ("REG-HACCP-CAL-006", "Reporte de no conformidad y acciones correctivas",
                  [("origen", "Origen (Queja o reclamo / Auditoría interna / Resultado de indicador / Auditoría externa / "
                              "Encuesta de satisfacción / Revisión gerencial / Otro)", "text"),
                   ("nro_accion", "Nro. acción", "text"), ("descripcion", "Descripción del reclamo", "textarea"),
                   ("etapas", "Etapas por las que pasó el producto (etapa/objetivo/trazabilidad/observación)", "textarea"),
                   ("cinco_porques", "Análisis de causa raíz (5 porqués)", "textarea"),
                   ("plan_accion", "Plan de acción (descripción/recursos/responsable/fecha)", "textarea"),
                   ("estado_accion", "Estado de la acción (ABIERTA / CERRADA / REPLANTEADA)", "text"),
                   ("fecha_revision", "Fecha de revisión", "date"), ("revisado_por", "Revisado por / cargo", "text")]),
    "CONTROL_PESOS": ("REG-CAL-003", "Control de pesos, rotulado y sellado de PT",
                      [("hora", "Hora", "text"), ("marca", "Marca", "text"), ("peso1", "Peso #1 (kg)", "number"),
                       ("peso2", "Peso #2 (kg)", "number"), ("peso3", "Peso #3 (kg)", "number"), ("peso4", "Peso #4 (kg)", "number"),
                       ("balanza", "Balanza", "text"), ("maquina", "Máquina", "text"), ("operario", "Operario", "text"),
                       ("rotulado_conforme", "Rotulado conforme", "bool"), ("sellado_h_conforme", "Sellado horizontal conforme", "bool"),
                       ("sellado_v_conforme", "Sellado vertical conforme", "bool")]),
    "CONTROL_GRANOS": ("REG-CAL-014", "Ficha de control de calidad de granos",
                       [("proceso", "Proceso", "text"), ("hora", "Hora", "text"), ("marca_calidad", "Marca / calidad", "text"),
                        ("cantidad_muestra_kg", "Cantidad de muestra (kg)", "number"),
                        ("lugar_muestra", "Lugar toma de muestra", "text")] + [(k, l, "number") for k, l in DEFECTOS_MUESTREO
                                                                                if k not in ("piedras", "insectos")]
                       + [("grano_entero", "Grano entero (%)", "number")]),
    "RECEPCION_IMPORTADO": ("REG-CAL-005", "Informe de recepción de materia prima – productos importados",
                            [("para", "Para", "text"), ("referencia", "Referencia (proveedor)", "text"),
                             ("lote_interno", "Lote interno", "text"), ("proveedor", "Proveedor", "text"),
                             ("fecha_ingreso", "Fecha de ingreso", "date"), ("lotes_proveedor", "Lote(s) del producto / F. venc.", "text"),
                             ("peso_neto_saco", "Peso neto / saco", "text"), ("procedencia", "Procedencia", "text"),
                             ("revision_documentaria", "Revisión de información documentaria", "textarea"),
                             ("humedad", "Humedad (%)", "number"), ("grano_enfermo", "Grano enfermo (%)", "number"),
                             ("grano_picado", "Grano picado (%)", "number"), ("grano_partido", "Grano partido o quebrado (%)", "number"),
                             ("grano_arrugado", "Grano arrugado (%)", "number"), ("materias_extranas", "Materias extrañas (%)", "number"),
                             ("variedad_contrastante", "Variedad contrastante (%)", "number"),
                             ("organoleptico", "Análisis organoléptico", "textarea"), ("conclusiones", "Conclusiones", "textarea"),
                             ("recomendaciones", "Recomendaciones", "textarea")]),
    "VEHICULO": ("REG-BPM-CAL-011", "Control de vehículos de transporte de MP y PT",
                 [("hora", "Hora", "text"), ("chofer", "Nombre chofer", "text"), ("placa", "Placa", "text"),
                  ("tipo_producto", "Tipo de producto (MP / PT)", "text"), ("limpieza_desinfeccion", "Limpieza y desinfección conforme", "bool"),
                  ("ausencia_plagas", "Ausencia de plagas", "bool"), ("ausencia_contaminantes", "Ausencia de contaminantes", "bool"),
                  ("contenedor", "Contenedor (C/L/A/I/R/M/P/O)", "text"), ("pallets_limpieza", "Pallets: limpieza conforme", "bool"),
                  ("pallets_integridad", "Pallets: integridad conforme", "bool"), ("estiba_conforme", "Estiba del producto conforme", "bool"),
                  ("acciones", "Observaciones y/o acciones correctivas", "textarea")]),
    "DISENO_BOBINA": ("IF §9.3", "Validación de diseño de bobina",
                      [("proveedor", "Proveedor", "text"), ("version_diseno", "Versión del diseño", "text"),
                       ("informacion_correcta", "Contiene la información correcta", "bool"),
                       ("detalle", "Detalle de la revisión", "textarea")]),
    "PROCESO": ("IF §9.3", "Registro de datos de proceso (asistente de Calidad)",
                [("linea", "Línea", "text"), ("parametro", "Parámetro", "text"), ("valor", "Valor", "text"),
                 ("detalle", "Detalle", "textarea")]),
    "INSPECCION_CARGA": ("IF §9.3", "Inspección de la carga en el despacho",
                         [("ruta", "Ruta / despacho", "text"), ("estado_carga", "Carga conforme", "bool"),
                          ("detalle", "Detalle", "textarea")]),
}


def pcc1_limit(grupo):
    for code, _, lim in PCC1_HUMEDAD:
        if code == grupo:
            return lim
    return None


def peso_criterio(peso_nominal):
    if peso_nominal is None:
        return None
    for nominal, crit in CRITERIOS_PESO.items():
        if abs(nominal - peso_nominal) < 1e-6:
            return crit
    return None


def auto_evaluate(formato, datos, product=None):
    """Devuelve (resultado_sugerido, hallazgos[]) según límites documentados."""
    hallazgos = []
    res = ""
    if formato == "RECEPCION_MP":
        lim = pcc1_limit(datos.get("grupo_humedad") or (product.grupo_humedad if product else "") or "OTROS")
        h = datos.get("humedad")
        ok = True
        if h is not None and lim is not None:
            if h > lim:
                ok = False
                hallazgos.append(f"Humedad {h}% supera el límite crítico PCC1 ≤ {lim}%")
            else:
                hallazgos.append(f"Humedad {h}% dentro del límite PCC1 ≤ {lim}%")
        for k, lbl in (("impurezas_conforme", "Impurezas"), ("plaga_conforme", "Plaga")):
            if datos.get(k) is False:
                ok = False
                hallazgos.append(f"{lbl}: No conforme")
        res = "CONFORME" if ok else "NO_CONFORME"
    elif formato in ("MUESTREO", "RECEPCION_IMPORTADO", "CONTROL_GRANOS"):
        ok = True
        for k, lim in SPEC_CALIDAD_SUPERIOR.items():
            v = datos.get(k)
            if v is None and k == "total_defectos":
                parts = [datos.get(x) for x in ("grano_enfermo", "grano_picado", "grano_partido", "grano_arrugado",
                                                  "materias_extranas", "variedad_contrastante")]
                if any(p is not None for p in parts):
                    v = round(sum(p or 0 for p in parts), 3)
            if v is None:
                continue
            if v > lim + 1e-9:
                ok = False
                hallazgos.append(f"{k}: {v} > máx. {lim} (Calidad superior, REG-CAL-005)")
        if datos.get("insectos"):
            ok = False
            hallazgos.append(f"Insectos: {datos.get('insectos')}")
        res = "CONFORME" if ok else "NO_CONFORME"
        hallazgos.append("Referencia: especificación 'Calidad superior' de REG-CAL-005; la decisión final es de Calidad.")
    elif formato == "CONTROL_PESOS":
        crit = peso_criterio(product.peso_kg if product else None)
        ok = True
        if crit is None:
            hallazgos.append("Sin criterio documentado para esta presentación. " + CRITERIO_PESO_PENDIENTE)
        else:
            _, mn, mx = crit
            for i in range(1, 5):
                v = datos.get(f"peso{i}")
                if v is not None and not (mn <= v <= mx):
                    ok = False
                    hallazgos.append(f"Peso #{i} = {v} kg fuera de [{mn}, {mx}] kg")
        for k in ("rotulado_conforme", "sellado_h_conforme", "sellado_v_conforme"):
            if datos.get(k) is False:
                ok = False
                hallazgos.append(f"{k}: No conforme")
        res = "CONFORME" if ok else "NO_CONFORME"
    elif formato == "VEHICULO":
        malos = [k for k in ("limpieza_desinfeccion", "ausencia_plagas", "ausencia_contaminantes", "pallets_limpieza",
                             "pallets_integridad", "estiba_conforme") if datos.get(k) is False]
        res = "NO_CONFORME" if malos else "CONFORME"
        if malos:
            hallazgos.append("No conforme: " + ", ".join(malos) + ". Debe repetirse el procedimiento de higiene (REG-BPM-CAL-011).")
    elif formato == "DISENO_BOBINA":
        res = "CONFORME" if datos.get("informacion_correcta") else "NO_CONFORME"
    elif formato == "NO_CONFORME":
        res = "NO_CONFORME"
    elif formato == "INSPECCION_CARGA":
        res = "CONFORME" if datos.get("estado_carga") else "NO_CONFORME"
    return res, hallazgos


def parse_form(formato, form):
    """Convierte un formulario HTML a datos tipados según la definición del formato."""
    from datetime import date as _d
    datos = {}
    for key, _, tipo in FORMATOS[formato][2]:
        raw = (form.get(key) or "").strip()
        if tipo == "number":
            datos[key] = float(raw.replace(",", ".")) if raw else None
        elif tipo == "bool":
            datos[key] = None if raw == "" else raw in ("1", "si", "sí", "on", "true", "C", "√")
        elif tipo == "date":
            datos[key] = _d.fromisoformat(raw).isoformat() if raw else None
        else:
            datos[key] = raw
    return datos


def register(user, formato, datos, product_code=None, lote="", lot_id=None, resultado=None, observaciones="",
             referencia_tipo="", referencia_id=None, fecha=None):
    if formato not in FORMATOS:
        raise BusinessError("Formato no válido.")
    perm = "distribucion.seguridad" if formato == "VEHICULO" and has_perm(user, "distribucion.seguridad") else "calidad.registrar"
    if not has_perm(user, perm):
        raise BusinessError("Su rol no registra este formato.")
    product = db().get(Product, product_code) if product_code else None
    if lot_id:
        lot = db().get(StockLot, int(lot_id))
        if lot:
            product = product or lot.product
            product_code = product_code or lot.product_code
            lote = lote or lot.lote
    sugerido, hallazgos = auto_evaluate(formato, datos, product)
    datos = dict(datos)
    datos["_evaluacion_automatica"] = {"resultado": sugerido, "hallazgos": hallazgos}
    rec = QualityRecord(formato=formato, codigo_formato=FORMATOS[formato][0], product_code=product_code, lote=lote,
                        lot_id=int(lot_id) if lot_id else None, datos=datos, resultado=resultado or sugerido,
                        observaciones=observaciones, user_id=user.id, referencia_tipo=referencia_tipo,
                        referencia_id=referencia_id, fecha=fecha or date.today())
    db().add(rec)
    db().flush()
    if rec.resultado in ("NO_CONFORME", "DESAPROBADO") and formato not in ("QUEJA",):
        alerts.emit("CALIDAD_NO_CONFORME", f"{FORMATOS[formato][1]}: no conforme ({product_code or '-'} {lote})",
                    "; ".join(hallazgos) or observaciones, "QualityRecord", rec.id, creado_por=user)
    if formato == "FUMIGACION" and rec.lot_id:
        _apply_fumigation(rec, user)
    audit(user, "CALIDAD_REGISTRO", "QualityRecord", rec.id, {"formato": formato, "resultado": rec.resultado})
    return rec


def _apply_fumigation(rec, user):
    from .stock import change_lot_state
    lot = db().get(StockLot, rec.lot_id)
    if rec.datos.get("fin_fecha"):
        if lot.estado == "EN_FUMIGACION":
            change_lot_state(lot, "PENDIENTE_REVISION", user, f"Fin de fumigación (registro #{rec.id}); requiere liberación")
    elif rec.datos.get("inicio_fecha"):
        change_lot_state(lot, "EN_FUMIGACION", user, f"Inicio de fumigación (registro #{rec.id})")


def release_lot(lot, user, aprobar, motivo, estado_rechazo="NO_UTILIZABLE"):
    """Liberación por Calidad: Pendiente de revisión -> Disponible (o No utilizable/Dañado)."""
    from .stock import change_lot_state
    if not has_perm(user, "calidad.liberar"):
        raise BusinessError("La liberación la realiza Calidad (IF §9.3).")
    if lot.estado not in ("PENDIENTE_REVISION", "NO_UTILIZABLE"):
        raise BusinessError("Solo se liberan lotes Pendientes de revisión o No utilizables tratados.")
    destino = "DISPONIBLE" if aprobar else estado_rechazo
    lot.verificado = True
    lot.fecha_verificacion = lot.fecha_verificacion or now()
    change_lot_state(lot, destino, user, f"Calidad: {motivo}")
    alerts.close_by_system(f"PEND_REV:{lot.id}", "Lote evaluado por Calidad")


# ------------------------------ certificados -------------------------------
def _next_number(serie):
    anio = date.today().year
    prefijo = f"CP{anio}-{serie}"
    n = db().execute(select(func.count(Certificate.id)).where(Certificate.numero.like(f"{prefijo}%"))).scalar() or 0
    return f"{prefijo}{n + 1:04d}"


def certificate_data(lot, order=None):
    """Arma los datos del certificado desde Producción (lote), Calidad (registros) y el pedido."""
    s = db()
    p = lot.product
    liq = s.execute(select(Liquidation).where(Liquidation.product_code == lot.product_code, Liquidation.lote == lot.lote)
                    .order_by(Liquidation.id.desc())).scalars().first()
    recs = list(s.execute(select(QualityRecord).where(QualityRecord.lote == lot.lote,
                                                      QualityRecord.formato.in_(["MUESTREO", "CONTROL_GRANOS", "RECEPCION_MP",
                                                                                 "RECEPCION_IMPORTADO"]))
                          .order_by(QualityRecord.id.desc())).scalars())
    rec = recs[0] if recs else None
    pend = "(pendiente: dato de Calidad)"
    tam = None
    if liq and p and p.peso_kg:
        tam = f"{liq.cantidad_completada * p.peso_kg:,.0f} kg"
    elif liq:
        tam = f"{liq.cantidad_completada:g} {p.um if p else ''}"
    sanidad = []
    if rec:
        for k, lbl in DEFECTOS_MUESTREO:
            v = rec.datos.get(k)
            if v is not None and k != "humedad":
                sanidad.append({"analisis": lbl, "resultado": f"{v}", "conclusion": "CONFORME" if rec.resultado == "CONFORME" else "REVISAR"})
    humedad = rec.datos.get("humedad") if rec else None
    return {
        "producto_declarado": (p.producto_base or p.descripcion) if p else lot.product_code,
        "descripcion_articulo": p.descripcion if p else "",
        "lote": lot.lote,
        "fecha_produccion": (lot.fecha_fab or (liq.fecha_fab if liq else None)).isoformat() if (lot.fecha_fab or (liq and liq.fecha_fab)) else "",
        "fecha_vencimiento": lot.fecha_venc.isoformat() if lot.fecha_venc else "",
        "marca": p.marca if p else "", "grado": p.calidad if p else "",
        "procesado_por": param("empresa_razon_social", ""), "ruc": param("empresa_ruc", ""),
        "autorizacion_sanitaria": param("autorizacion_sanitaria", ""),
        "presentacion_muestra": p.presentacion if p else "",
        "pais_origen": rec.datos.get("procedencia", "") if rec else "",
        "tamano_lote": tam or pend,
        "fecha_analisis": rec.fecha.isoformat() if rec else pend,
        "organoleptico": [{"analisis": "COLOR", "resultado": pend, "especificacion": "", "conclusion": ""},
                          {"analisis": "OLOR Y SABOR", "resultado": pend, "especificacion": "", "conclusion": ""},
                          {"analisis": "ASPECTO", "resultado": pend, "especificacion": "", "conclusion": ""}],
        "humedad": {"resultado": f"{humedad}%" if humedad is not None else pend, "especificacion": "MAX. 15%",
                    "conclusion": ("CONFORME" if humedad is not None and humedad <= 15 else ("NO CONFORME" if humedad is not None else ""))},
        "sanidad": sanidad,
        "inocuidad": "",
        "conclusiones": "",
        "pedido": order.numero if order else "", "cliente": order.customer.nombre if order else "",
        "fuente_calidad": f"Registro #{rec.id} ({rec.codigo_formato})" if rec else "Sin registro de Calidad para el lote",
        "fuente_produccion": f"Liquidación {liq.numero_documento}" if liq else "Sin liquidación registrada",
    }


def generate_certificate(lot, user=None, order=None):
    series = param("series_certificado", {}) or {}
    p = lot.product
    serie = series.get(p.tipo if p and p.tipo else lot.product_code[:2], series.get(lot.product_code[:2], "PT"))
    cert = Certificate(numero=_next_number(serie), serie=serie, lot_id=lot.id, order_id=order.id if order else None,
                       product_code=lot.product_code, datos=certificate_data(lot, order))
    db().add(cert)
    db().flush()
    alerts.emit("CERTIFICADO_REVISION", f"Revisar certificado {cert.numero}",
                f"Lote {lot.lote} de {lot.product_code}{' – OV ' + order.numero if order else ''}.", "Certificate", cert.id,
                dedup_key=f"CERT:{cert.id}", creado_por=user)
    audit(user, "CERTIFICADO_GENERADO", "Certificate", cert.numero, {"lote": lot.lote})
    return cert


def autogenerate_for_order(order, user=None):
    """Genera certificados para los lotes de un pedido listo para despacho (IF §9.4)."""
    out = []
    s = db()
    for line in order.lines:
        for r in line.reservations:
            if r.estado != "ACTIVA":
                continue
            exists = s.execute(select(Certificate).where(Certificate.lot_id == r.lot_id, Certificate.order_id == order.id,
                                                         Certificate.estado != "ANULADO")).scalars().first()
            if exists is None:
                out.append(generate_certificate(r.lot, user, order))
    return out


EDITABLE_CERT_FIELDS = ["producto_declarado", "lote", "fecha_produccion", "fecha_vencimiento", "marca", "grado",
                        "procesado_por", "ruc", "autorizacion_sanitaria", "presentacion_muestra", "pais_origen",
                        "tamano_lote", "fecha_analisis", "inocuidad", "conclusiones"]


def review_certificate(cert, user, cambios, aprobar=False):
    if not has_perm(user, "calidad.certificado_revisar"):
        raise BusinessError("Revisa el Supervisor o la Jefatura de Calidad (IF §9.4).")
    if cert.estado == "APROBADO" and cambios:
        raise BusinessError("El certificado ya fue aprobado.")
    datos = dict(cert.datos)
    log = list(cert.cambios or [])
    for k, v in cambios.items():
        if k.startswith("org_") or k.startswith("hum_"):
            continue
        if k in EDITABLE_CERT_FIELDS and str(datos.get(k, "")) != str(v):
            log.append({"campo": k, "antes": datos.get(k), "despues": v, "user": user.nombre, "ts": now().isoformat()})
            datos[k] = v
    org = [dict(x) for x in datos.get("organoleptico", [])]
    for i, item in enumerate(org):
        for f in ("resultado", "especificacion", "conclusion"):
            key = f"org_{i}_{f}"
            if key in cambios and cambios[key] != item.get(f):
                log.append({"campo": f"organoleptico[{item['analisis']}].{f}", "antes": item.get(f), "despues": cambios[key],
                            "user": user.nombre, "ts": now().isoformat()})
                item[f] = cambios[key]
    datos["organoleptico"] = org
    hum = dict(datos.get("humedad", {}))
    for f in ("resultado", "especificacion", "conclusion"):
        key = f"hum_{f}"
        if key in cambios and cambios[key] != hum.get(f):
            log.append({"campo": f"humedad.{f}", "antes": hum.get(f), "despues": cambios[key], "user": user.nombre,
                        "ts": now().isoformat()})
            hum[f] = cambios[key]
    datos["humedad"] = hum
    cert.datos = datos
    cert.cambios = log
    if aprobar:
        pend = [k for k, v in datos.items() if isinstance(v, str) and "pendiente" in v.lower()]
        pend += [f"organoleptico[{o['analisis']}]" for o in org if "pendiente" in str(o.get("resultado", "")).lower()]
        if "pendiente" in str(hum.get("resultado", "")).lower():
            pend.append("humedad")
        if pend:
            raise BusinessError("No se puede aprobar: hay datos pendientes: " + ", ".join(pend))
        cert.estado = "APROBADO"
        cert.revisado_por = user.id
        cert.revisado_ts = now()
        alerts.close_by_system(f"CERT:{cert.id}", "Certificado aprobado")
    audit(user, "CERTIFICADO_APROBADO" if aprobar else "CERTIFICADO_EDITADO", "Certificate", cert.numero,
          {"cambios": len(log)})
