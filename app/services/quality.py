"""Calidad (IF §9.3, §9.4) y formatos operativos REG-*.

Cada formato se define con sus campos tal como figuran en el documento fuente. Las evaluaciones automáticas
solo usan límites documentados (PCC1 de REG-HACCP-CAL-002; especificación 'Calidad superior' de REG-CAL-005;
criterios de peso de REG-CAL-003). La decisión final (aprobado/desaprobado) la registra Calidad.
"""
from datetime import date, timedelta

from sqlalchemy import func, select

from ..catalogs import CRITERIO_PESO_PENDIENTE, CRITERIOS_PESO, PCC1_HUMEDAD, SPEC_CALIDAD_SUPERIOR
from ..db import db
from ..models import Certificate, Liquidation, Product, QualityRecord, SalesOrder, StockLot, now
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

# Encabezado de cada formato tal como figura en el documento (cuadro "REGISTRO · Código · Versión · Fecha · Página").
# Los formatos sin documento fuente (IF §9.3) no tienen versión: se imprimen con el membrete y su referencia.
ENCABEZADOS = {
    "MUESTREO": ("REG-CAL-002", "02", "18/03/2024"), "RECEPCION_MP": ("REG-HACCP-CAL-002", "02", "18/03/2024"),
    "FUMIGACION": ("REG-BPM-CAL-005", "02", "18/03/2024"), "NO_CONFORME": ("REG-BPM-CAL-013", "01", "18/03/2024"),
    "QUEJA": ("REG-HACCP-CAL-003", "02", "18/03/2024"), "NC_ACCION": ("REG-HACCP-CAL-006", "1", "18/03/2024"),
    "CONTROL_PESOS": ("REG-CAL-003", "03", "18/03/2024"), "CONTROL_GRANOS": ("REG-CAL-014", "03", "18/03/2024"),
    "RECEPCION_IMPORTADO": ("REG-CAL-005", "02", "18/03/2024"), "VEHICULO": ("REG-BPM-CAL-011", "02", "11/03/2024"),
}

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
    # Observaciones al demo v0.6: cualquier persona de Calidad registra el análisis en cada evaluación y el
    # precertificado lo toma automáticamente (sin código de documento fuente: registro del sistema).
    "ANALISIS_LOTE": ("Registro del sistema", "Análisis del lote para el certificado (organoléptico, fisicoquímico y sanidad-aspecto)",
                      [("org_color", "Organoléptico: color", "text"), ("org_olor_sabor", "Organoléptico: olor y sabor", "text"),
                       ("org_olor", "Organoléptico: olor", "text"), ("org_sabor", "Organoléptico: sabor", "text"),
                       ("org_aspecto", "Organoléptico: aspecto / apariencia", "text"),
                       ("humedad", "Fisicoquímico: humedad (%)", "number")]
                      + [(k, f"Sanidad-aspecto: {l}", "number") for k, l in DEFECTOS_MUESTREO if k != "humedad"]),
}

# Obs. demo v0.7 (Asistente de Calidad): registros antes, durante y después del proceso de producción
FORMATOS.update({
    "PREVIO_PRODUCCION": ("Registro del sistema (obs. demo v0.7)", "Antes de producir: higiene del personal y de los equipos",
                          [("linea", "Línea", "text"), ("of", "Orden de fabricación / solicitud", "text"),
                           ("personal_higiene", "Todo el personal cumplió las normas de higiene", "bool"),
                           ("equipos_calidad_higiene", "Todos los equipos cumplieron las normas de calidad e higiene", "bool"),
                           ("detalle", "Detalle / acciones correctivas", "textarea")]),
    "LOTE_PRODUCIDO": ("Registro del sistema (obs. demo v0.7)", "Durante la producción: ingreso de nuevo lote",
                       [("linea", "Línea", "text"), ("of", "Orden de fabricación (como en la liquidación)", "text"),
                        ("hora", "Hora", "text"), ("cantidad", "Cantidad producida del lote (UM del artículo)", "number"),
                        ("fecha_produccion", "Fecha de producción", "date"), ("fecha_vencimiento", "Fecha de vencimiento", "date"),
                        ("detalle", "Datos de la ficha / observaciones", "textarea")]),
    "POST_PRODUCCION": ("Registro del sistema (obs. demo v0.7)", "Después de producir: cierre del proceso",
                        [("linea", "Línea", "text"), ("of", "Orden de fabricación", "text"),
                         ("limpieza_equipos", "Limpieza y desinfección de equipos al terminar", "bool"),
                         ("producto_conforme", "Producto terminado conforme", "bool"),
                         ("detalle", "Detalle / acciones correctivas", "textarea")]),
    "VEHICULO_SEGURIDAD": ("REG-BPM-CAL-011 (parte de Seguridad)", "Control de vehículos de transporte de MP y PT (Seguridad)",
                           [("placa", "Placa (la programada)", "text"), ("chofer", "Chofer (el programado)", "text"),
                            ("vehiculo_en_orden", "El vehículo está en orden", "bool"),
                            ("detalle", "Qué debe subsanarse (si no está en orden)", "textarea")]),
})
# V13 (30-oct-2026): las horas se eligen con reloj; la fumigación indica la zona (lista de zonas, almacén externo u
# otro con «dónde»); el «registro de datos de proceso» se retira (se conserva para leer los registros anteriores) y
# el «ingreso de nuevo lote» lo registra solo Producción.
for _k, (_c, _n, _campos) in list(FORMATOS.items()):
    FORMATOS[_k] = (_c, _n, [(k, l, "time" if (k == "hora" or k.endswith("_hora")) and t == "text" else t) for k, l, t in _campos])
FORMATOS["FUMIGACION"][2].insert(0, ("zona", "Zona (lugar de la fumigación)", "zona"))
FORMATOS_RETIRADOS = {"PROCESO"}
FORMATOS_PRODUCCION = {"LOTE_PRODUCIDO"}
# formatos por etapa del proceso (pantalla de Calidad)
ETAPAS_PRODUCCION = {
    "Antes de producir": ["PREVIO_PRODUCCION", "RECEPCION_MP", "RECEPCION_IMPORTADO", "MUESTREO", "DISENO_BOBINA"],
    "Durante la producción": ["CONTROL_GRANOS", "CONTROL_PESOS"],
    "Después de producir": ["POST_PRODUCCION", "ANALISIS_LOTE", "INSPECCION_CARGA", "NO_CONFORME"],
}


def lot_entries_vs_liquidation(liq):
    """Contraste del lote registrado por Calidad durante la producción con la liquidación (obs. demo v0.7)."""
    recs = list(db().execute(select(QualityRecord).where(QualityRecord.formato == "LOTE_PRODUCIDO",
                                                         QualityRecord.lote == liq.lote,
                                                         QualityRecord.product_code == liq.product_code)).scalars())
    if not recs:
        return None
    reg = sum(float((r.datos or {}).get("cantidad") or 0) for r in recs)
    return {"registros": recs, "calidad": reg, "liquidado": liq.cantidad_completada,
            "diferencia": round(liq.cantidad_completada - reg, 4), "coincide": abs(liq.cantidad_completada - reg) < 1e-6}


ORG_CLAVES = {"COLOR": "org_color", "OLOR Y SABOR": "org_olor_sabor", "ASPECTO": "org_aspecto", "APARIENCIA": "org_aspecto",
              "OLOR": "org_olor", "SABOR": "org_sabor"}


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


def _lbl(formato):
    return {k: l for k, l, _ in FORMATOS[formato][2]}


class _Lbl(dict):
    def __missing__(self, f):
        self[f] = _lbl(f)
        return self[f]


FORMATO_LBL = _Lbl()


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
    elif formato in ("PREVIO_PRODUCCION", "POST_PRODUCCION"):
        claves = ("personal_higiene", "equipos_calidad_higiene") if formato == "PREVIO_PRODUCCION" else ("limpieza_equipos", "producto_conforme")
        malos = [FORMATO_LBL[formato].get(k, k) for k in claves if datos.get(k) is False]
        res = "NO_CONFORME" if malos else ("CONFORME" if all(datos.get(k) for k in claves) else "")
        if malos:
            hallazgos.append("No cumple: " + "; ".join(malos))
    elif formato == "VEHICULO_SEGURIDAD":
        res = "CONFORME" if datos.get("vehiculo_en_orden") else ("NO_CONFORME" if datos.get("vehiculo_en_orden") is False else "")
        if res == "NO_CONFORME":
            hallazgos.append("Vehículo no está en orden: " + (datos.get("detalle") or "debe subsanarse"))
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
        elif tipo == "zona" and raw == "OTRO":
            donde = (form.get(f"{key}_otro") or "").strip()
            if not donde:
                raise BusinessError("Indique dónde se realiza la fumigación.")
            datos[key] = f"Otro: {donde}"
        else:
            datos[key] = raw
    return datos


def register(user, formato, datos, product_code=None, lote="", lot_id=None, resultado=None, observaciones="",
             referencia_tipo="", referencia_id=None, fecha=None):
    if formato not in FORMATOS or formato in FORMATOS_RETIRADOS:
        raise BusinessError("Formato no válido.")
    perm = "distribucion.seguridad" if formato in ("VEHICULO", "VEHICULO_SEGURIDAD") and has_perm(user, "distribucion.seguridad") \
        else ("produccion.lote_nuevo" if formato in FORMATOS_PRODUCCION else "calidad.registrar")
    if not has_perm(user, perm):
        raise BusinessError("Su rol no registra este formato.")
    if formato == "VEHICULO_SEGURIDAD" and datos.get("vehiculo_en_orden") is False and not (datos.get("detalle") or "").strip():
        raise BusinessError("Indique qué debe subsanarse del vehículo.")
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
    if formato == "VEHICULO_SEGURIDAD" and rec.resultado == "NO_CONFORME":
        alerts.emit("VEHICULO_SUBSANAR", f"Vehículo {datos.get('placa') or ''} no está en orden: subsanar",
                    f"Chofer {datos.get('chofer') or '-'}. {datos.get('detalle') or ''}", "QualityRecord", rec.id, creado_por=user)
    if formato == "LOTE_PRODUCIDO" and lote:
        _contrastar_lote(rec, user)
    if formato == "FUMIGACION" and rec.lot_id:
        _apply_fumigation(rec, user)
    if formato == "ANALISIS_LOTE" and lote:
        refresh_draft_certificates(lote, user)
    audit(user, "CALIDAD_REGISTRO", "QualityRecord", rec.id, {"formato": formato, "resultado": rec.resultado})
    return rec


def _contrastar_lote(rec, user):
    """Si el lote ya fue liquidado, contrasta lo registrado por Calidad con la liquidación y alerta las diferencias."""
    from ..models import Liquidation
    for liq in db().execute(select(Liquidation).where(Liquidation.lote == rec.lote,
                                                      Liquidation.product_code == rec.product_code)).scalars():
        c = lot_entries_vs_liquidation(liq)
        if c and not c["coincide"]:
            alerts.emit("CALIDAD_VS_LIQUIDACION", f"Lote {liq.lote}: Calidad registró {c['calidad']:g} y se liquidó {c['liquidado']:g}",
                        f"{liq.product_code}, liquidación {liq.numero_documento}. Revisar antes de que Almacén confirme la recepción.",
                        "Liquidation", liq.id, dedup_key=f"CAL_LIQ:{liq.id}", creado_por=user)


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
    if lot.estado not in ("PENDIENTE_REVISION", "NO_UTILIZABLE", "OBSERVADO", "EN_FUMIGACION"):
        raise BusinessError("Solo se liberan lotes bloqueados (pendientes de revisión, observados, en fumigación o no utilizables tratados).")
    destino = "DISPONIBLE" if aprobar else estado_rechazo
    lot.verificado = True
    lot.fecha_verificacion = lot.fecha_verificacion or now()
    lid = lot.id
    change_lot_state(lot, destino, user, f"Calidad: {motivo}", _calidad=True)
    if aprobar:  # V13: se cierran la observación, la fumigación y la solicitud de liberación
        from .quality_v13 import _segment
        lot = _segment(lot, destino)
        lot.observacion, lot.liberacion_solicitada = {}, {}
        if lot.fumigacion:
            lot.fumigacion = dict(lot.fumigacion, liberado=now().isoformat(timespec="minutes"))
        from ..models import ReviewRequest
        for r in db().execute(select(ReviewRequest).where(ReviewRequest.lot_id == lid, ReviewRequest.estado == "PENDIENTE",
                                                         ReviewRequest.tipo == "LIBERACION")).scalars():
            r.estado, r.resultado, r.resuelto_por, r.resuelto_ts = "RESUELTA", "LIBERADO", user.id, now()
            alerts.close_by_system(f"REVISION:{r.id}", "Lote liberado por Calidad")
    alerts.close_by_system(f"PEND_REV:{lid}", "Lote evaluado por Calidad")


# ------------------------------ certificados -------------------------------
def _next_number(serie):
    anio = date.today().year
    prefijo = f"CP{anio}-{serie}"
    n = db().execute(select(func.count(Certificate.id)).where(Certificate.numero.like(f"{prefijo}%"))).scalar() or 0
    return f"{prefijo}{n + 1:04d}"


# Tipos de certificado con formato propio (modelos N°CP2026-PT3756, MP276 y CA0764; respuesta del 13-oct: "existen
# diversos tipos de certificado de calidad"). Todos comparten el membrete (logos, marca de agua y pie).
CERT_TIPOS = {
    "PT": {"nombre": "Producto terminado (modelo PT3756)", "subtitulo": "INFORME DE ENSAYOS FISICOQUIMICO Y ORGANOLEPTICO",
           "campos": ["producto_declarado", "lote", "fecha_produccion", "fecha_vencimiento", "marca", "procesado_por", "ruc",
                      "autorizacion_sanitaria", "presentacion_muestra", "pais_origen", "tamano_lote", "fecha_analisis"],
           "organoleptico": ["COLOR", "OLOR Y SABOR", "ASPECTO"], "especificacion": True, "sanidad": True, "inocuidad": True,
           "referencias": True, "conclusion": "normas"},
    "MP": {"nombre": "Materia prima / granel (modelo MP276)", "subtitulo": "INFORME DE ENSAYOS FISICOQUIMICO Y ORGANOLEPTICO",
           "campos": ["producto_declarado", "lote", "fecha_produccion", "fecha_vencimiento", "grado", "procesado_por", "ruc",
                      "autorizacion_sanitaria", "presentacion_muestra", "pais_origen", "tamano_lote", "fecha_analisis"],
           "organoleptico": ["COLOR", "OLOR Y SABOR", "ASPECTO"], "especificacion": False, "sanidad": True, "inocuidad": False,
           "referencias": True, "conclusion": "normas"},
    "CA": {"nombre": "Cosecha Andina (modelo CA0764)", "subtitulo": "",
           "campos": ["producto_declarado", "lote", "fecha_produccion", "fecha_vencimiento", "marca", "procesado_por", "ruc",
                      "registro_sanitario", "presentacion_muestra", "fecha_analisis"],
           "organoleptico": ["Apariencia", "Color", "Olor", "Sabor"], "especificacion": True, "sanidad": False, "inocuidad": False,
           "referencias": False, "conclusion": "codex"},
}
CERT_ETIQUETAS = {"producto_declarado": "PRODUCTO DECLARADO", "lote": "LOTE", "fecha_produccion": "FECHA DE PRODUCCIÓN",
                  "fecha_vencimiento": "FECHA DE VENCIMIENTO", "marca": "MARCA", "grado": "GRADO", "procesado_por": "PROCESADO POR",
                  "ruc": "RUC", "autorizacion_sanitaria": "AUTORIZACION SANITARIA", "registro_sanitario": "REGISTRO SANITARIO",
                  "presentacion_muestra": "PRESENTACIÓN DE LA MUESTRA", "pais_origen": "PAÍS DE ORIGEN",
                  "tamano_lote": "TAMAÑO DE LOTE", "fecha_analisis": "FECHA DE ANALISIS"}
# V13: etiqueta de quién procesa (modelos del 30-oct-2026: «Procesado por», «Procesado y envasado por», «Importado,
# procesado y envasado por») y filas de datos adicionales (etiqueta + descripción) que Calidad agrega o quita.
CERT_PROCESADO = ["PROCESADO Y ENVASADO POR", "PROCESADO POR", "IMPORTADO, PROCESADO Y ENVASADO POR"]
CERT_ETIQUETAS["procesado_por"] = CERT_PROCESADO[0]
HUMEDAD_METODO = ("NTP 205.002-1979(Revisada 2016) Cereales y Menestras. Determinación de contenido de humedad, Método Usual.")
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]


def fecha_larga(d):
    """'22 de Setiembre del 2026' (formato de los certificados modelo)."""
    return f"{d.day} de {MESES[d.month - 1]} del {d.year}"


def certificate_type_for(lot):
    p = lot.product
    por_marca = {str(k).upper(): v for k, v in (param("tipo_certificado_por_marca", {}) or {}).items()}
    if p and (p.marca or "").upper() in por_marca and por_marca[(p.marca or "").upper()] in CERT_TIPOS:
        return por_marca[(p.marca or "").upper()]
    series = param("series_certificado", {}) or {}
    t = series.get(p.tipo if p and p.tipo else lot.product_code[:2], series.get(lot.product_code[:2], "PT"))
    return t if t in CERT_TIPOS else "PT"


def _referencia_ntp(producto):
    for k, v in (param("referencias_ntp", {}) or {}).items():
        if str(k).upper() in (producto or "").upper():
            return v
    return ""


def _fmt_fecha(d):
    return d.strftime("%d-%m-%y") if d else ""


def _marca_de(p):
    """Marca tomada de la descripción del artículo ('… - MARCA X') cuando el maestro no la trae."""
    if p is None or " - " not in (p.descripcion or ""):
        return ""
    return p.descripcion.rsplit(" - ", 1)[1].strip()


def _org(nombre, analisis, pend):
    clave = ORG_CLAVES.get(nombre.upper())
    v = (analisis.datos or {}).get(clave) if analisis and clave else None
    if v in (None, ""):
        return {"analisis": nombre, "resultado": pend, "especificacion": "", "conclusion": ""}
    return {"analisis": nombre, "resultado": str(v), "especificacion": "",
            "conclusion": "CONFORME" if analisis.resultado in ("CONFORME", "APROBADO") else "REVISAR"}


def refresh_draft_certificates(lote, user=None):
    """Al registrar un análisis, los certificados en borrador del lote toman los nuevos resultados."""
    n = 0
    for c in db().execute(select(Certificate).join(StockLot, Certificate.lot_id == StockLot.id)
                          .where(StockLot.lote == lote, Certificate.estado == "BORRADOR")).scalars():
        lot = db().get(StockLot, c.lot_id)
        order = db().get(SalesOrder, c.order_id) if c.order_id else None
        nuevos = certificate_data(lot, order, (c.datos or {}).get("tipo", c.serie))
        datos = dict(c.datos or {})
        for k in ("organoleptico", "humedad", "sanidad", "fecha_analisis", "fuente_calidad", "fecha_produccion",
                  "fecha_vencimiento", "marca", "pais_origen"):
            datos[k] = nuevos[k]
        c.datos = datos
        n += 1
    return n


def certificate_data(lot, order=None, tipo=None):
    """Arma los datos del certificado desde Producción (lote), Calidad (registros) y el pedido, según el tipo."""
    s = db()
    p = lot.product
    tipo = tipo or certificate_type_for(lot)
    td = CERT_TIPOS[tipo]
    liq = s.execute(select(Liquidation).where(Liquidation.product_code == lot.product_code, Liquidation.lote == lot.lote)
                    .order_by(Liquidation.id.desc())).scalars().first()
    recs = list(s.execute(select(QualityRecord).where(QualityRecord.lote == lot.lote,
                                                      QualityRecord.formato.in_(["ANALISIS_LOTE", "MUESTREO", "CONTROL_GRANOS",
                                                                                 "RECEPCION_MP", "RECEPCION_IMPORTADO"]))
                          .order_by(QualityRecord.id.desc())).scalars())
    analisis = next((r for r in recs if r.formato == "ANALISIS_LOTE"), None)
    rec = recs[0] if recs else None
    pend = "(pendiente: dato de Calidad)"
    tam = None
    if liq and p and p.peso_kg:
        tam = f"{liq.cantidad_completada * p.peso_kg:,.0f} kg"
    elif liq:
        tam = f"{liq.cantidad_completada:g} {p.um if p else ''}"
    sanidad = []
    if rec and td["sanidad"]:
        for k, lbl in DEFECTOS_MUESTREO:
            v = rec.datos.get(k)
            if v is not None and k != "humedad":
                sanidad.append({"analisis": lbl, "resultado": f"{v}", "conclusion": "CONFORME" if rec.resultado == "CONFORME" else "REVISAR"})
    humedad = rec.datos.get("humedad") if rec else None
    hmax = (param("humedad_maxima_por_tipo", {}) or {}).get(tipo) if td["especificacion"] else None
    producto = (p.producto_base or p.descripcion) if p else lot.product_code
    ref = _referencia_ntp(producto) if td["referencias"] else ""
    fp = lot.fecha_fab or (liq.fecha_fab if liq else None)
    fv = lot.fecha_venc or (liq.fecha_venc if liq else None)
    marca = (p.marca if p else "") or _marca_de(p)
    if humedad is None:
        hum_concl = ""
    elif hmax is not None:
        hum_concl = "CONFORME" if humedad <= hmax else "NO CONFORME"
    else:
        hum_concl = "CONFORME" if rec.resultado == "CONFORME" else "REVISAR"
    if td["conclusion"] == "codex":
        concl = (f"El área de aseguramiento de Calidad de la empresa “Corporación Productiva SAC” certifica que el producto "
                 f"denominado como “{producto}” cumple con las especificaciones de calidad según la ficha técnica del producto y "
                 f"el Codex Alimentarius (normas alimentarias aceptadas internacionalmente), garantizando la conformidad del producto.")
    else:
        concl = (f"El área de aseguramiento de Calidad de la empresa “Corporación Productiva SAC” certifica que el producto "
                 f"denominado como “{producto}” cumple con las especificaciones de calidad según las Normas Técnicas "
                 f"especificadas para cada ensayo, garantizando la conformidad del producto.")
    return {
        "tipo": tipo,
        "producto_declarado": producto,
        "descripcion_articulo": p.descripcion if p else "",
        "lote": lot.lote,
        "fecha_produccion": _fmt_fecha(fp),
        "fecha_vencimiento": _fmt_fecha(fv),
        "marca": marca, "grado": p.calidad if p else "",
        "procesado_por": param("empresa_razon_social", ""), "ruc": param("empresa_ruc", ""),
        "autorizacion_sanitaria": param("autorizacion_sanitaria", ""),
        "registro_sanitario": pend if "registro_sanitario" in td["campos"] else "",
        "presentacion_muestra": p.presentacion if p else "",
        "pais_origen": next((r.datos.get("procedencia") for r in recs if (r.datos or {}).get("procedencia")), ""),
        "tamano_lote": tam or pend,
        "fecha_analisis": _fmt_fecha(rec.fecha) if rec else pend,
        "organoleptico": [_org(a, analisis, pend) for a in td["organoleptico"]],
        "humedad": {"resultado": f"{humedad}%" if humedad is not None else pend,
                    "especificacion": (f"MÁX. {hmax:g} %" if hmax is not None else ""), "conclusion": hum_concl},
        "referencia_organoleptico": f"ANALSIS ORGANOLÉPTICO: {ref}" if ref else "",
        "referencia_fisicoquimico": (f"{HUMEDAD_METODO} ANÁLISIS FÍSICOS-QUÍMICOS: {ref}" if ref and tipo == "PT"
                                     else (f"ANÁLISIS FÍSICOS-QUÍMICOS: {ref}" if ref else "")),
        "referencia_sanidad": f"ANÁLISIS SANIDAD ASPECTO: {ref}" if ref and td["sanidad"] else "",
        "sanidad": sanidad,
        "inocuidad": (f"El producto cumple con el Decreto Supremo Nº004-2011-AG y sus modificatorias, por lo que el {producto}, "
                      f"es un producto CONFORME.") if td["inocuidad"] else "",
        "conclusiones": concl,
        "fecha_emision": fecha_larga(date.today()),
        "pedido": order.numero if order else "", "cliente": order.customer.nombre if order else "",
        "fuente_calidad": f"Registro #{rec.id} ({rec.codigo_formato})" if rec else "Sin registro de Calidad para el lote",
        "fuente_produccion": f"Liquidación {liq.numero_documento}" if liq else "Sin liquidación registrada",
    }


def generate_certificate(lot, user=None, order=None, tipo=None):
    tipo = tipo or certificate_type_for(lot)
    if tipo not in CERT_TIPOS:
        raise BusinessError(f"Tipo de certificado desconocido: {tipo}")
    cert = Certificate(numero=_next_number(tipo), serie=tipo, lot_id=lot.id, order_id=order.id if order else None,
                       product_code=lot.product_code, datos=certificate_data(lot, order, tipo))
    db().add(cert)
    db().flush()
    alerts.emit("CERTIFICADO_REVISION", f"Revisar certificado {cert.numero}",
                f"Lote {lot.lote} de {lot.product_code}{' – OV ' + order.numero if order else ''}.", "Certificate", cert.id,
                dedup_key=f"CERT:{cert.id}", creado_por=user)
    audit(user, "CERTIFICADO_GENERADO", "Certificate", cert.numero, {"lote": lot.lote, "tipo": tipo})
    return cert


def regenerate_certificate(cert, user, tipo):
    """Calidad cambia el tipo de un borrador: se anula y se genera uno nuevo del tipo indicado."""
    if not has_perm(user, "calidad.certificado_revisar"):
        raise BusinessError("Revisa el Supervisor o la Jefatura de Calidad (IF §9.4).")
    if cert.estado != "BORRADOR":
        raise BusinessError("Solo se regenera un certificado en borrador.")
    if tipo not in CERT_TIPOS or tipo == (cert.datos or {}).get("tipo", cert.serie):
        raise BusinessError("Elija un tipo de certificado distinto.")
    lot = db().get(StockLot, cert.lot_id) if cert.lot_id else None
    if lot is None:
        raise BusinessError("El certificado no tiene lote asociado.")
    order = db().get(SalesOrder, cert.order_id) if cert.order_id else None
    cert.estado = "ANULADO"
    alerts.close_by_system(f"CERT:{cert.id}", f"Certificado regenerado como tipo {tipo}")
    audit(user, "CERTIFICADO_REGENERADO", "Certificate", cert.numero, {"tipo": tipo})
    return generate_certificate(lot, user, order, tipo)


def autogenerate_for_order(order, user=None):
    """Genera certificados para los lotes de un pedido listo para despacho (IF §9.4)."""
    out = []
    s = db()
    lotes_activos = {r.lot_id for l in order.lines for r in l.reservations if r.estado == "ACTIVA"}
    for c in s.execute(select(Certificate).where(Certificate.order_id == order.id, Certificate.estado == "BORRADOR")).scalars():
        if c.lot_id not in lotes_activos:
            c.estado = "ANULADO"  # el lote ya no forma parte del pedido (cambio de reserva o de OV)
            alerts.close_by_system(f"CERT:{c.id}", "Certificado anulado: el lote ya no está en el pedido")
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
                        "procesado_por", "ruc", "autorizacion_sanitaria", "registro_sanitario", "presentacion_muestra",
                        "pais_origen", "tamano_lote", "fecha_analisis", "inocuidad", "conclusiones", "fecha_emision",
                        "referencia_organoleptico", "referencia_fisicoquimico", "referencia_sanidad"]


def review_certificate(cert, user, cambios, aprobar=False):
    if not has_perm(user, "calidad.certificado_revisar"):
        raise BusinessError("Revisa el Supervisor o la Jefatura de Calidad (IF §9.4).")
    if cert.estado == "APROBADO" and cambios:
        raise BusinessError("El certificado ya fue aprobado.")
    datos = dict(cert.datos)
    log = list(cert.cambios or [])
    cambios = dict(cambios)
    if "procesado_etiqueta" in cambios:
        v = cambios.pop("procesado_etiqueta")
        if v not in CERT_PROCESADO:
            raise BusinessError("Etiqueta de «procesado por» no válida.")
        if datos.get("procesado_etiqueta", CERT_PROCESADO[0]) != v:
            log.append({"campo": "procesado_etiqueta", "antes": datos.get("procesado_etiqueta", CERT_PROCESADO[0]), "despues": v,
                        "user": user.nombre, "ts": now().isoformat()})
            datos["procesado_etiqueta"] = v
    if "datos_adicionales" in cambios:
        filas = [{"etiqueta": str(e).strip(), "descripcion": str(d).strip()} for e, d in cambios.pop("datos_adicionales")
                 if str(e).strip() or str(d).strip()]
        if any(not f["etiqueta"] for f in filas):
            raise BusinessError("Cada dato adicional necesita su etiqueta.")
        if filas != list(datos.get("datos_adicionales") or []):
            log.append({"campo": "datos_adicionales", "antes": len(datos.get("datos_adicionales") or []), "despues": len(filas),
                        "user": user.nombre, "ts": now().isoformat()})
            datos["datos_adicionales"] = filas
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
        alerts.emit("CERTIFICADO_LISTO", f"Certificado {cert.numero} aprobado y cargado",
                    f"Lote {datos.get('lote')} · {cert.product_code}" + (f" · OV {datos.get('pedido')}" if datos.get("pedido") else "")
                    + (" (con correcciones manuales)" if log else ""), "Certificate", cert.id, creado_por=user)
    audit(user, "CERTIFICADO_APROBADO" if aprobar else "CERTIFICADO_EDITADO", "Certificate", cert.numero,
          {"cambios": len(log)})


# ------------------------------ planeamiento de fumigación (13-oct) ---------
def fumigation_due(lot):
    """Fecha en que el lote debe fumigarse: la programada por Calidad/Almacén o, si no hay, el fin del tiempo máximo de
    almacenamiento del artículo (fecha de ingreso + tiempo máximo), que hoy dispara 'evaluar fumigación'."""
    if lot.fumigacion_programada:
        return lot.fumigacion_programada, "programada"
    p = lot.product
    if lot.fecha_admision and p and p.tiempo_max_almacen_dias:
        return lot.fecha_admision + timedelta(days=p.tiempo_max_almacen_dias), "tiempo máximo de almacenamiento"
    return None, ""


def fumigation_plan(horizonte=30, hoy=None):
    hoy = hoy or date.today()
    out = []
    for lot in db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado != "EN_FUMIGACION")).scalars():
        f, origen = fumigation_due(lot)
        if f is not None and (f - hoy).days <= horizonte:
            out.append({"lot": lot, "fecha": f, "dias": (f - hoy).days, "origen": origen})
    return sorted(out, key=lambda x: x["fecha"])


def schedule_fumigation(lot, user, fecha):
    if not (has_perm(user, "calidad.registrar") or has_perm(user, "stock.cambiar_estado")):
        raise BusinessError("La fumigación la programa Calidad o Almacén.")
    lot.fumigacion_programada = fecha
    audit(user, "FUMIGACION_PROGRAMADA", "StockLot", lot.id, {"lote": lot.lote, "fecha": fecha.isoformat() if fecha else None})


def fumigation_alerts(hoy=None):
    """Avisos a Calidad 7 días antes, 3 días antes y el mismo día de la fumigación (parámetro 'dias_aviso_fumigacion')."""
    hoy = hoy or date.today()
    dias = [int(x) for x in (param("dias_aviso_fumigacion", [7, 3, 0]) or [])]
    n = 0
    for x in fumigation_plan(max(dias or [0]), hoy):
        if x["dias"] in dias or (x["dias"] < 0 and 0 in dias):
            lot = x["lot"]
            cuando = "HOY" if x["dias"] == 0 else (f"en {x['dias']} días" if x["dias"] > 0 else f"vencida hace {-x['dias']} días")
            alerts.emit("FUMIGACION_PROXIMA", f"Fumigación {cuando}: lote {lot.lote}",
                        f"{lot.product_code} {lot.product.descripcion if lot.product else ''} · {lot.cantidad:g} en "
                        f"{lot.warehouse_code} · fecha {x['fecha']:%d/%m/%Y} ({x['origen']}). Planificar la fumigación.",
                        "StockLot", lot.id, dedup_key=f"FUMI:{lot.id}:{x['fecha']}:{x['dias'] if x['dias'] >= 0 else 'venc'}")
            n += 1
    return n


def fumigation_counts():
    """V7: cuántas veces se envió a fumigación cada producto y cada lote (cada paso a «En fumigación» registrado)."""
    from collections import Counter
    from ..models import AuditLog
    por_lote, por_prod, ultima = Counter(), Counter(), {}
    for a in db().execute(select(AuditLog).where(AuditLog.accion == "LOTE_ESTADO").order_by(AuditLog.ts)).scalars():
        d = a.detalle or {}
        if d.get("a") != "EN_FUMIGACION":
            continue
        k = (d.get("producto") or "", d.get("lote") or "")
        por_lote[k] += 1
        por_prod[k[0]] += 1
        ultima[k] = a.ts
    from ..models import Product
    nombres = {p.code: p.descripcion for p in db().execute(select(Product).where(Product.code.in_(list(por_prod) or [""]))).scalars()}
    return {"productos": [(c, nombres.get(c, ""), n) for c, n in por_prod.most_common()],
            "lotes": [(c, l, n, ultima[(c, l)]) for (c, l), n in por_lote.most_common()]}
