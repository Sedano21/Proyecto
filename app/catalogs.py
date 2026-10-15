"""Catálogos iniciales derivados de la documentación fuente.

Convenciones de origen (IF = Informe Funcional, v1.0, 9-oct-2026):
- DEFINIDO: regla expresamente indicada en la documentación.
- PROPUESTO: organización derivada (p.ej. del alcance por área, IF §3) que requiere validación.
- PENDIENTE: valor/decisión que la documentación declara pendiente; se deja configurable y vacío o inactivo.
- proceso actual: valor observado en archivos operativos actuales (Excel/PDF/diagrama); no es regla aprobada.
- DEMO: valor colocado solo para demostrar el prototipo; debe reemplazarse.
"""

IF = "Informe Funcional"
TOBE = "Diagrama de procesos COPROD-ONE (L5)"
Q3 = "Decisión del usuario Q3 (11 y 12-oct-2026)"
Q4 = "Decisión del usuario Q4 (11-oct-2026)"
R12 = "Decisión del usuario (12-oct-2026)"
R13 = "Decisión del usuario (13-oct-2026)"
R14 = "Decisión del usuario (13-oct-2026, segunda parte)"
O6 = "Observaciones al demo v0.6 (14-oct-2026)"
CANAL_GRANEL = "MAYORISTA GRANEL"
VIRTUALES = ["ALM-002", "ALM-004", "ALM-005", "ALM-006", "ALM-007", "ALM-012", "EXT-007", "EXT-013", "PRO-*"]

# ---------------------------------------------------------------------------
# Roles (IF §15)
# ---------------------------------------------------------------------------
ROLES = [
    # code, nombre, area, fuente, observacion
    ("GERENCIA_GENERAL", "Gerencia General", "Gerencia", f"{IF} §3, §14, §15", "Acceso completo; puede aprobar en nombre de otros roles (Q4)."),
    ("GERENCIA_OPERACIONES", "Gerencia de Operaciones", "Gerencia", f"{IF} §3, §15", "Vista y autorizaciones de su ámbito."),
    ("SISTEMAS", "Sistemas", "Sistemas", f"{IF} §3, §15, §16", "Acceso completo sin aprobar en nombre de otros roles (Q4)."),
    ("GERENTE_COMERCIAL", "Gerente Comercial", "Comercial", f"{IF} §15", ""),
    ("JEFE_VENTAS", "Jefe Comercial (Jefe de Ventas)", "Comercial", f"{IF} §5, §15; {R13}",
     "Único rol que modifica las listas de precios (Q11)."),
    ("COORD_VENTAS", "Coordinador de Ventas", "Comercial", f"{IF} §5, §15", ""),
    ("ASIST_VENTAS", "Asistente de Ventas", "Comercial", f"{IF} §5, §15", "Modifica OV solo con autorización."),
    ("EJECUTIVO_VENTAS", "Ejecutivo de Ventas (vendedor por canal)", "Comercial", f"{IF} §5, §15", "Vendedor responsable de la OV."),
    ("COORD_ALMACEN", "Coordinación de Almacén 1560 (producto terminado)", "Almacén", f"{IF} §6, §15; decisión Q17 (12-oct-2026)",
     "Maneja el almacén 1560 (ALM-001) y el tránsito de Producción ALM-003."),
    ("COORD_ALMACEN_MP", "Coordinación de Almacén 1524 (materia prima, granel e insumos)", "Almacén",
     f"{TOBE} (dos coordinadores); decisión Q17 (12-oct-2026)", "Maneja el almacén 1524 (EXT-002)."),
    ("SUPERV_ALMACEN", "Supervisión de Almacén (por almacén)", "Almacén", f"{IF} §15", ""),
    ("LIDER_ALMACEN", "Líder Operativo de Almacén", "Almacén", f"{IF} §15; diagrama de proceso actual L5", "Autoriza la salida del camión (Q16)."),
    ("AUX_ALMACEN", "Auxiliar / Asistente de Almacén", "Almacén", f"{IF} §6.2, §15", ""),
    ("MONTACARGUISTA", "Montacarguista", "Almacén", f"{IF} §8.3, §15", ""),
    ("COORD_DISTRIBUCION", "Coordinador de Distribución", "Distribución", f"{IF} §12, §15", ""),
    ("ASIST_DISTRIBUCION", "Asistente de Distribución", "Distribución", f"{IF} §15", ""),
    ("CONDUCTOR", "Conductor", "Distribución", f"{IF} §15", ""),
    ("AUX_DESPACHO", "Auxiliar de Despacho", "Distribución", f"{IF} §12.3, §15", ""),
    ("JEFE_LOGISTICA", "Jefatura de Logística", "Logística", f"{IF} §6.2, §13, §15", ""),
    ("COORD_LOGISTICA", "Coordinación de Logística", "Logística", f"{IF} §15", ""),
    ("JEFE_PRODUCCION", "Jefatura de Producción", "Producción", f"{IF} §8, §15", ""),
    ("ASIST_PRODUCCION", "Asistente de Producción", "Producción", f"{IF} §15; {R14}", "Hoy son dos asistentes; no existe Coordinación de Producción."),
    ("JEFE_CALIDAD", "Jefatura de Calidad", "Calidad", f"{IF} §9, §15", ""),
    ("SUPERV_CALIDAD", "Supervisor de Calidad", "Calidad", f"{IF} §9.3, §15", ""),
    ("ASIST_CALIDAD", "Asistente de Calidad", "Calidad", f"{IF} §9.3, §15", ""),
    ("COMPRAS", "Coordinador de Compras", "Compras", f"{IF} §10, §15", ""),
    ("IMPORTACIONES", "Coordinador de Importación", "Importaciones", f"{IF} §11, §15; {R13} Q10", "Responsable de las fases de importación."),
    ("SEGURIDAD", "Seguridad", "Seguridad", f"{IF} §12.2, §13, §15", ""),
    ("FACTURACION", "Facturación", "Facturación", "Diagrama de procesos COPROD-ONE (carril Facturación)", "Evalúa el pedido validado y carga la factura."),
]

# ---------------------------------------------------------------------------
# Permisos (separación consulta/edición/aprobación/administración, IF §19)
# ---------------------------------------------------------------------------
PERMISSIONS = [
    ("dashboard.ver", "Ver tablero de indicadores", "Gerencial", "consulta"),
    ("ov.ver", "Consultar órdenes de venta", "Comercial", "consulta"),
    ("ov.crear", "Registrar OV", "Comercial", "edicion"),
    ("ov.modificar", "Modificar OV directamente (solo Ejecutivo de cuenta, Coordinador y Jefe Comercial)", "Comercial", "exclusivo"),
    ("ov.solicitar_modificacion", "Solicitar modificación de OV (requiere autorización)", "Comercial", "edicion"),
    ("ov.autorizar_modificacion", "Autorizar modificación de OV solicitada por Asistente", "Comercial", "aprobacion"),
    ("ov.cancelar", "Cancelar OV", "Comercial", "aprobacion"),
    ("ov.renegociar", "Registrar renegociación de fecha / cambio de producto", "Comercial", "edicion"),
    ("ov.aprobar_parcial", "Aprobar despacho parcial", "Logística", "aprobacion"),
    ("ov.decidir_alternativa", "Decidir uso de stock de otros almacenes", "Logística", "aprobacion"),
    ("ov.importar", "Importar OV desde exportación SAP", "Comercial", "edicion"),
    ("precios.ver", "Consultar listas de precios", "Comercial", "consulta"),
    ("precios.editar", "Cargar y modificar listas de precios mínimos y su vigencia (solo Jefe Comercial)", "Comercial", "exclusivo"),
    ("costos.ver", "Ver costos de la empresa y el análisis costo vs mercado", "Comercial", "exclusivo"),
    ("costos.cargar", "Cargar costos y precios de mercado", "Comercial", "exclusivo"),
    ("ov.aprobar_precio", "Liberar una OV retenida por precio en el límite o bajo el mínimo", "Comercial", "exclusivo"),
    ("clientes.canal", "Asignar canal de precios y cargar condiciones de clientes (penalidades, lotes)", "Comercial", "exclusivo"),
    ("stock.ver", "Consultar stock y reservas", "Almacén", "consulta"),
    ("stock.cargar", "Cargar archivos de stock/movimientos (validación previa)", "Almacén", "edicion"),
    ("stock.autorizar_carga", "Autorizar/confirmar carga de stock", "Almacén", "aprobacion"),
    ("stock.cambiar_estado", "Cambiar estado de stock (dañado, no utilizable, etc.)", "Almacén", "edicion"),
    ("stock.conteo", "Registrar conteos físicos", "Almacén", "edicion"),
    ("preparacion.registrar", "Registrar preparación/picking", "Almacén", "edicion"),
    ("traslados.ver", "Consultar traslados", "Logística", "consulta"),
    ("traslado.solicitar", "Solicitar traslado", "Logística", "edicion"),
    ("traslado.autorizar", "Autorizar traslado", "Logística", "aprobacion"),
    ("traslado.salida", "Registrar salida de traslado", "Almacén", "edicion"),
    ("traslado.recibir", "Confirmar recepción de traslado en destino", "Almacén", "edicion"),
    ("reempaque.ver", "Consultar reempaques", "Calidad", "consulta"),
    ("reempaque.solicitar", "Solicitar reempaque y aprobar/enviar la pre-solicitud a Calidad", "Almacén", "aprobacion"),
    ("reempaque.evaluar", "Evaluar y aprobar/desaprobar reempaque", "Calidad", "aprobacion"),
    ("reempaque.ejecutar", "Ejecutar y registrar reempaque", "Producción", "edicion"),
    ("produccion.ver", "Consultar producción", "Producción", "consulta"),
    ("produccion.bom_cargar", "Cargar lista de materiales (Excel)", "Producción", "edicion"),
    ("produccion.solicitud", "Crear/revisar/enviar solicitud preliminar de producción", "Almacén", "edicion"),
    ("produccion.validar", "Validar solicitud (lista, disponibilidad real, capacidad, plazo)", "Producción", "aprobacion"),
    ("produccion.programar", "Programar producción", "Producción", "edicion"),
    ("produccion.registrar", "Registrar inicio/fin de producción", "Producción", "edicion"),
    ("produccion.liquidar", "Registrar/cargar liquidación", "Producción", "edicion"),
    ("produccion.recibir_pt", "Validar recepción de PT y diferencias", "Almacén", "edicion"),
    ("calidad.ver", "Consultar registros de Calidad", "Calidad", "consulta"),
    ("calidad.registrar", "Registrar datos de Calidad (formatos)", "Calidad", "edicion"),
    ("calidad.liberar", "Liberar producto / cambiar estado por Calidad", "Calidad", "aprobacion"),
    ("calidad.certificado_revisar", "Revisar, corregir y aprobar certificados", "Calidad", "aprobacion"),
    ("calidad.evaluar_muestra", "Evaluar muestras de compras/importaciones", "Calidad", "aprobacion"),
    ("compras.ver", "Consultar compras", "Compras", "consulta"),
    ("compras.solicitar", "Originar solicitud de compra", "Almacén", "edicion"),
    ("compras.aprobar_solicitud", "Aprobar la solicitud de compra antes de pasar a Compras", "Logística", "aprobacion"),
    ("compras.gestionar", "Cotizar, generar orden y actualizar fechas", "Compras", "edicion"),
    ("compras.aprobar_mayor_volumen", "Aprobar compra de mayor volumen", "Gerencia", "aprobacion"),
    ("compras.recibir", "Registrar recepción de compra", "Almacén", "edicion"),
    ("compras.autorizar_bajo_observacion", "Autorizar recepción bajo observaciones", "Gerencia", "aprobacion"),
    ("importaciones.ver", "Consultar importaciones", "Importaciones", "consulta"),
    ("importaciones.gestionar", "Registrar importaciones, fases y fechas", "Importaciones", "edicion"),
    ("importaciones.recibir", "Registrar recepción de importación", "Almacén", "edicion"),
    ("distribucion.ver", "Consultar distribución", "Distribución", "consulta"),
    ("distribucion.programar", "Generar/ajustar programación de rutas", "Distribución", "edicion"),
    ("distribucion.flota", "Mantener flota y conductores", "Distribución", "edicion"),
    ("distribucion.validar_externo", "Validar el transporte externo asignado a una ruta", "Distribución", "aprobacion"),
    ("distribucion.confirmar_salida", "Autorizar y confirmar la salida del camión", "Almacén", "aprobacion"),
    ("distribucion.visto_bueno_salida", "Dar visto bueno a la salida del camión (Auxiliar de Despacho)", "Distribución", "aprobacion"),
    ("distribucion.aprobar_salida_discrepancia", "Aprobar la salida con discrepancia de guía mientras se resuelve", "Logística", "aprobacion"),
    ("distribucion.seguridad", "Control de Seguridad: ingreso, inspección, carga vs guía y revisión de documentos", "Seguridad", "edicion"),
    ("distribucion.entrega", "Registrar avance y entrega con evidencia", "Distribución", "edicion"),
    ("distribucion.incidencia", "Registrar incidencias", "Distribución", "edicion"),
    ("distribucion.documentos", "Generar/cargar guía y emitir folio de documentos", "Distribución", "edicion"),
    ("distribucion.carga", "Registrar fotos y validación de la carga (auxiliar y chofer)", "Distribución", "edicion"),
    ("facturacion.cargar", "Evaluar pedido validado y cargar factura", "Facturación", "edicion"),
    ("alertas.ver", "Ver alertas propias/del rol", "Alertas", "consulta"),
    ("alertas.gestionar", "Asignar, atender, comentar y cerrar alertas", "Alertas", "edicion"),
    ("alertas.ver_todas", "Ver alertas de todas las áreas", "Alertas", "consulta"),
    ("alertas.configurar", "Configurar destinatarios/canales/urgencia de alertas", "Alertas", "administracion"),
    ("config.ver", "Consultar configuración", "Configuración", "consulta"),
    ("config.editar", "Editar configuración y catálogos (solo Sistemas)", "Configuración", "exclusivo"),
    ("usuarios.administrar", "Administrar usuarios y matriz de permisos", "Configuración", "administracion"),
    ("auditoria.ver", "Consultar bitácora de auditoría (solo Sistemas)", "Configuración", "exclusivo"),
    # Observaciones al demo v0.6: visibilidad por área
    ("dashboard.precios", "Tablero: montos de OV y OV con precio en el límite o bajo el mínimo", "Gerencial", "consulta"),
    ("dashboard.operaciones", "Tablero: tiempos de preparación y salida, compras/producción pendientes, diferencias de inventario", "Gerencial", "consulta"),
    ("dashboard.merma", "Tablero: merma prevista vs real", "Gerencial", "consulta"),
    ("informes.comercial", "Informe Comercial (ventas, comportamiento de clientes, penalidades)", "Informes", "consulta"),
    ("informes.reempaque", "Informe de Reempaque (cómo se atendieron las solicitudes)", "Informes", "consulta"),
    ("informes.produccion", "Informe de Producción (capacidad, programado vs real, solicitudes)", "Informes", "consulta"),
    ("informes.distribucion", "Informe de Distribución (a tiempo, desviación, costos de transporte y estiba)", "Informes", "consulta"),
    ("informes.almacen", "Informe de movimiento de stock del almacén (picos, bajas, demoras, stock de reserva)", "Informes", "consulta"),
    ("ov.opciones", "Ver las opciones evaluadas por el sistema para una OV y aprobar/derivar sus pre-solicitudes", "Almacén", "consulta"),
    ("clientes.ver", "Consultar fichas de clientes", "Comercial", "consulta"),
    ("clientes.editar", "Modificar o completar fichas de clientes (solo Comercial)", "Comercial", "exclusivo"),
    ("produccion.bom_aprobar", "Revisar y aprobar/modificar la lista de materiales usada para producir", "Producción", "aprobacion"),
    ("flota.ver", "Consultar seguimiento de flota (SOAT, impuestos, multas, combustible, mantenimiento)", "Distribución", "consulta"),
    ("tareas.ejecutar", "Registrar inicio y fin de tareas operativas con foto (picking, traslado interno)", "Almacén", "edicion"),
    ("picking.asignar", "Asignar el picking preprogramado a auxiliares o grupos", "Almacén", "edicion"),
    ("export.datos", "Exportar registros", "General", "consulta"),
]
ALL_PERMS = [p[0] for p in PERMISSIONS]

_VIEW_OPS = ["dashboard.ver", "ov.ver", "stock.ver", "traslados.ver", "reempaque.ver", "produccion.ver",
             "calidad.ver", "compras.ver", "importaciones.ver", "distribucion.ver", "alertas.ver",
             "alertas.gestionar", "export.datos"]

# role -> list of (perm, origen, fuente)
def _d(perms, fuente):
    return [(p, "DEFINIDO", fuente) for p in perms]


def _p(perms, fuente=f"{IF} §3 (alcance por área) – propuesto"):
    return [(p, "PROPUESTO", fuente) for p in perms]


ROLE_PERMISSIONS = {
    "GERENCIA_GENERAL": _p(["costos.ver"], "Respuestas del 13-oct (R4): visibilidad del costo – propuesto") + _d([p for p, _, _, t in PERMISSIONS if t != "exclusivo"] + ["precios.ver"],
                           f"{IF} §15; {Q4}: acceso completo, incluso aprobar en nombre de otros roles "
                           f"(salvo los permisos exclusivos: precios y venta bajo mínimo del Jefe Comercial, {R13} Q11; "
                           f"configuración de Sistemas, {R14})"),
    "SISTEMAS": _d(["config.editar", "clientes.canal"], f"{R14}: Sistemas tiene todo el panel de configuración") + _d(
        [p for p, _, _, t in PERMISSIONS if t not in ("aprobacion", "exclusivo")] + ["precios.ver"],
                   f"{IF} §15-§16; {Q4}: acceso completo pero NO aprueba en nombre de otros roles"),
    "GERENCIA_OPERACIONES": _p(_VIEW_OPS + ["config.ver"]) + _d(
        ["ov.renegociar"], f"{IF} §4.5, §5 (participa en renegociación)") + _d(
        ["ov.aprobar_parcial"], f"{Q3}: aprueba Gerencia de Operaciones o Jefatura de Logística") + _d(
        ["compras.autorizar_bajo_observacion"], f"{IF} §10.8") + _p(
        ["compras.aprobar_mayor_volumen"], f"{IF} §7 – participación de GO requiere validación"),
    "GERENTE_COMERCIAL": _p(["costos.ver"], "Respuestas del 13-oct (R4): visibilidad del costo – propuesto") + _p(["precios.ver", "dashboard.ver", "ov.ver", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "export.datos"]),
    "JEFE_VENTAS": _d(["precios.ver", "precios.editar"], f"{R13} Q11: único con autorización para modificar precios") + _p(
        ["costos.ver", "costos.cargar"], "Respuestas del 13-oct (R4, R5): costos y precios de mercado los gestiona Comercial – propuesto") + _d(
        ["ov.modificar"], f"Observaciones al demo v0.5 (13-oct): modificar OV solo Ejecutivo de cuenta, Coordinador y Jefe Comercial") + _d(
        ["ov.aprobar_precio"], f"{R14}: la OV bajo el mínimo queda detenida hasta la confirmación del Coordinador Comercial o Jefe Comercial") + _d(
        ["clientes.canal"], f"{R14}: el Jefe Comercial asigna y traslada clientes de canal") + _p(["dashboard.ver", "ov.ver", "ov.crear", "ov.modificar", "ov.importar", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "export.datos"]) + _d(
        ["ov.cancelar", "ov.autorizar_modificacion"], f"{IF} §5") + _d(
        ["ov.renegociar"], f"{IF} §4.5, §5 (Comercial participa)"),
    "COORD_VENTAS": _d(["ov.aprobar_precio"], f"{R14}: confirma OV detenida por precio (Coordinador Comercial)") + _p(
        ["costos.ver"], "Respuestas del 13-oct (R4): confirma OV bajo costo – propuesto") + _d(
        ["ov.modificar"], f"Observaciones al demo v0.5 (13-oct): modificar OV solo Ejecutivo de cuenta, Coordinador y Jefe Comercial") + _p(["precios.ver", "dashboard.ver", "ov.ver", "ov.crear", "ov.modificar", "ov.importar", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "export.datos"]) + _d(
        ["ov.cancelar", "ov.autorizar_modificacion"], f"{IF} §5") + _d(
        ["ov.renegociar"], f"{IF} §4.5, §5 (Comercial participa)"),
    "ASIST_VENTAS": _d(["ov.crear"], "Diagrama de proceso actual L5 (Asistente comercial ingresa la OV)") + _d(
        ["ov.solicitar_modificacion"], f"{IF} §5 (modifica con autorización)") + _d(
        ["ov.importar"], f"{TOBE}: el asistente carga el consolidado de OV emitidas y cambios") + _p(["ov.ver", "stock.ver", "alertas.ver"]),
    "EJECUTIVO_VENTAS": _d(["ov.modificar"], f"Observaciones al demo v0.5 (13-oct): modificar OV solo Ejecutivo de cuenta, Coordinador y Jefe Comercial") + _p(["ov.ver", "ov.crear", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar"]) + _d(
        ["ov.autorizar_modificacion"], f"{IF} §5 (vendedor responsable autoriza; solo sus OV)") + _d(
        ["ov.renegociar"], f"{IF} §5 (Comercial puede renegociar)"),
    "COORD_ALMACEN": _p(_VIEW_OPS + ["stock.cargar", "stock.autorizar_carga", "stock.cambiar_estado", "stock.conteo",
                                     "preparacion.registrar", "traslado.salida", "importaciones.recibir"]) + _d(
        ["traslado.recibir"], f"{IF} §6.2, §13") + _d(["reempaque.solicitar"], f"{IF} §9.1; {R12} Q12: aprueba la pre-solicitud") + _d(
        ["produccion.solicitud"], f"{IF} §8.2 (Almacén revisa y envía)") + _d(
        ["compras.solicitar"], f"{IF} §7, §10.1") + _d(["compras.recibir", "produccion.recibir_pt"], f"{IF} §8.3, §10.6-10.7"),
    "SUPERV_ALMACEN": _p(["dashboard.ver", "ov.ver", "stock.ver", "traslados.ver", "reempaque.ver", "produccion.ver",
                          "compras.ver", "importaciones.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar",
                          "stock.cargar", "stock.cambiar_estado", "stock.conteo", "preparacion.registrar",
                          "traslado.salida", "traslado.recibir", "reempaque.solicitar", "produccion.solicitud",
                          "compras.solicitar", "compras.recibir", "produccion.recibir_pt", "importaciones.recibir", "export.datos"]),
    "LIDER_ALMACEN": _p(["ov.ver", "stock.ver", "alertas.ver", "alertas.gestionar", "stock.conteo", "traslados.ver",
                         "distribucion.ver"]) + _d(
        ["preparacion.registrar"], "Diagrama de proceso actual L5 (Líder operativo designa y verifica picking)") + _d(
        ["distribucion.confirmar_salida"], f"{R12} Q16: el Líder Operativo autoriza la salida"),
    "AUX_ALMACEN": _p(["ov.ver", "stock.ver", "alertas.ver", "stock.conteo", "preparacion.registrar", "traslados.ver"]) + _d(
        ["traslado.recibir"], f"{IF} §6.2 (Coordinador de Almacén o asistente confirma recepción)"),
    "MONTACARGUISTA": _p(["stock.ver", "alertas.ver", "alertas.gestionar"], f"{IF} §8.3 (recibe alerta de liquidación) – propuesto"),
    "COORD_DISTRIBUCION": _p(["dashboard.ver", "ov.ver", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar",
                              "distribucion.programar", "distribucion.flota", "distribucion.entrega", "distribucion.incidencia", "export.datos"]) + _d(
        ["distribucion.documentos"], f"{TOBE}: Distribución genera/carga guía e imprime folio") + _d(
        ["distribucion.validar_externo"], "Observaciones al demo v0.5 (13-oct): el sistema puede asignar transporte externo pero lo valida el coordinador de distribución"),
    "ASIST_DISTRIBUCION": _p(["ov.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "distribucion.programar",
                              "distribucion.flota", "distribucion.entrega", "distribucion.incidencia", "distribucion.documentos"]),
    "CONDUCTOR": _p(["distribucion.ver", "alertas.ver", "distribucion.entrega", "distribucion.incidencia"]) + _d(
        ["distribucion.carga"], f"{TOBE}: validación de carga y foto (auxiliar y chofer)"),
    "AUX_DESPACHO": _p(["distribucion.ver", "alertas.ver", "alertas.gestionar"]) + _d(
        ["distribucion.visto_bueno_salida"], f"{R13} Q16: visto bueno de Seguridad, Líder Operativo y Auxiliar de Despacho") + _d(
        ["distribucion.incidencia"], f"{IF} §12.3") + _d(
        ["distribucion.carga", "distribucion.entrega"], f"{TOBE}: fotos, validación de carga, entrega con foto y guía firmada"),
    "JEFE_LOGISTICA": _d(["traslado.salida", "traslado.recibir", "stock.cambiar_estado", "stock.conteo"],
                         f"{R13} Q5: maneja los almacenes virtuales (solo esos)") + _p(_VIEW_OPS + ["traslado.solicitar"]) + _d(
        ["traslado.autorizar", "ov.decidir_alternativa"], f"{IF} §4.5, §6.2, §13; {R12} Q13") + _d(
        ["ov.aprobar_parcial"], f"{Q3}: aprueba Gerencia de Operaciones o Jefatura de Logística") + _d(
        ["compras.aprobar_solicitud"], f"{R12} Q14: el Jefe de Logística aprueba la solicitud de compra") + _d(
        ["distribucion.aprobar_salida_discrepancia"], f"{R12} Q8"),
    "COORD_LOGISTICA": _d(["traslado.salida", "traslado.recibir", "stock.cambiar_estado", "stock.conteo"],
                          f"{R13} Q5: maneja los almacenes virtuales (solo esos)") + _p(_VIEW_OPS + ["traslado.solicitar"]) + _d(
        ["ov.decidir_alternativa"], f"{IF} §4.5, §6.2 (Logística decide)") + _d(
        ["traslado.autorizar"], f"{R12} Q13: aprueba el Jefe o el Coordinador de Logística") + _d(
        ["distribucion.aprobar_salida_discrepancia"], f"{R12} Q8"),
    "JEFE_PRODUCCION": _p(["dashboard.ver", "ov.ver", "stock.ver", "produccion.ver", "reempaque.ver", "calidad.ver",
                           "alertas.ver", "alertas.gestionar", "produccion.bom_cargar", "produccion.programar",
                           "produccion.registrar", "produccion.liquidar", "export.datos"]) + _d(
        ["produccion.validar"], f"{IF} §8.2") + _d(["reempaque.ejecutar"], f"{IF} §9.1"),
    "ASIST_PRODUCCION": _p(["produccion.ver", "reempaque.ver", "stock.ver", "alertas.ver", "produccion.registrar",
                            "produccion.liquidar", "reempaque.ejecutar"]),
    "JEFE_CALIDAD": _p(["dashboard.ver", "ov.ver", "stock.ver", "calidad.ver", "reempaque.ver", "produccion.ver",
                        "compras.ver", "importaciones.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar",
                        "calidad.registrar", "export.datos"]) + _d(
        ["reempaque.evaluar", "calidad.liberar", "calidad.evaluar_muestra"], f"{IF} §9.1, §9.3, §10.3") + _d(
        ["calidad.certificado_revisar"], f"{IF} §9.3, §9.4"),
    "SUPERV_CALIDAD": _p(["ov.ver", "stock.ver", "calidad.ver", "reempaque.ver", "produccion.ver", "compras.ver",
                          "importaciones.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "calidad.registrar",
                          "reempaque.evaluar", "calidad.liberar", "calidad.evaluar_muestra"]) + _d(
        ["calidad.certificado_revisar"], f"{IF} §9.3, §9.4"),
    "ASIST_CALIDAD": _p(["stock.ver", "calidad.ver", "reempaque.ver", "produccion.ver", "alertas.ver"]) + _d(
        ["calidad.registrar"], f"{IF} §9.3 (registro de datos de proceso por el asistente)"),
    "COMPRAS": _p(["dashboard.ver", "stock.ver", "compras.ver", "importaciones.ver", "alertas.ver", "alertas.gestionar", "export.datos"]) + _d(
        ["compras.gestionar"], f"{IF} §10"),
    "IMPORTACIONES": _p(["stock.ver", "compras.ver", "importaciones.ver", "alertas.ver", "alertas.gestionar"]) + _d(
        ["importaciones.gestionar"], f"{IF} §11"),
    "SEGURIDAD": _p(["distribucion.ver", "traslados.ver", "alertas.ver", "alertas.gestionar"]) + _d(
        ["distribucion.seguridad"], f"{IF} §12.2, §13; {TOBE}: revisa documentos completos (la salida la autoriza el Líder Operativo, Q16)"),
    "FACTURACION": _p(["ov.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar"], TOBE) + _d(
        ["facturacion.cargar"], f"{TOBE}: evaluar pedido validado, generar factura en SAP y cargarla al sistema"),
}

ROLE_PERMISSIONS["COORD_ALMACEN_MP"] = [(p, o, f"{R12} Q17: mismas funciones que el coordinador 1560, sobre el almacén 1524")
                                       for p, o, _ in ROLE_PERMISSIONS["COORD_ALMACEN"]]

# Observaciones al demo v0.6 (14-oct): visibilidad por área.
_COMERCIAL_ROLES = ["JEFE_VENTAS", "COORD_VENTAS", "ASIST_VENTAS", "EJECUTIVO_VENTAS", "GERENTE_COMERCIAL"]
_O6 = {
    "dashboard.precios": (["JEFE_VENTAS", "COORD_VENTAS", "GERENTE_COMERCIAL"], "DEFINIDO", ["GERENCIA_OPERACIONES"]),
    "dashboard.operaciones": (["COORD_ALMACEN", "COORD_ALMACEN_MP", "SUPERV_ALMACEN", "JEFE_LOGISTICA", "COORD_LOGISTICA",
                               "JEFE_PRODUCCION", "GERENCIA_OPERACIONES"], "DEFINIDO", ["COMPRAS", "COORD_DISTRIBUCION"]),
    "dashboard.merma": (["JEFE_PRODUCCION", "JEFE_LOGISTICA", "COORD_LOGISTICA", "GERENCIA_OPERACIONES"], "DEFINIDO",
                        ["ASIST_PRODUCCION"]),
    "informes.comercial": (_COMERCIAL_ROLES, "DEFINIDO", []),
    "informes.reempaque": (["COORD_ALMACEN", "COORD_ALMACEN_MP", "JEFE_PRODUCCION", "ASIST_PRODUCCION"], "DEFINIDO",
                           ["JEFE_CALIDAD", "SUPERV_CALIDAD", "JEFE_LOGISTICA", "COORD_LOGISTICA", "SUPERV_ALMACEN"]),
    "informes.produccion": (["JEFE_PRODUCCION", "ASIST_PRODUCCION"], "DEFINIDO", ["JEFE_LOGISTICA"]),
    "informes.distribucion": (["COORD_DISTRIBUCION", "ASIST_DISTRIBUCION"], "DEFINIDO", ["JEFE_LOGISTICA", "COORD_LOGISTICA"]),
    "informes.almacen": (["COORD_ALMACEN", "COORD_ALMACEN_MP"], "DEFINIDO",
                         ["LIDER_ALMACEN", "SUPERV_ALMACEN", "JEFE_LOGISTICA", "COORD_LOGISTICA"]),
    "ov.opciones": (["COORD_ALMACEN", "COORD_ALMACEN_MP", "JEFE_LOGISTICA", "COORD_LOGISTICA", "GERENCIA_OPERACIONES"],
                    "DEFINIDO", []),
    "clientes.ver": (_COMERCIAL_ROLES + ["COORD_ALMACEN", "COORD_ALMACEN_MP", "COORD_DISTRIBUCION", "ASIST_DISTRIBUCION",
                                         "GERENCIA_OPERACIONES"], "DEFINIDO", []),
    "clientes.editar": (_COMERCIAL_ROLES, "DEFINIDO", []),
    "produccion.bom_aprobar": (["JEFE_PRODUCCION", "ASIST_PRODUCCION"], "DEFINIDO", []),
    "produccion.bom_cargar": (["ASIST_PRODUCCION"], "DEFINIDO", []),
    "flota.ver": (["COORD_DISTRIBUCION", "ASIST_DISTRIBUCION"], "DEFINIDO", ["JEFE_LOGISTICA", "GERENCIA_OPERACIONES"]),
    "tareas.ejecutar": (["MONTACARGUISTA", "AUX_ALMACEN"], "DEFINIDO", ["LIDER_ALMACEN"]),
    "picking.asignar": (["LIDER_ALMACEN", "COORD_ALMACEN", "COORD_ALMACEN_MP"], "DEFINIDO", []),
    "auditoria.ver": (["SISTEMAS"], "DEFINIDO", []),
}
for _perm, (_def, _o, _prop) in _O6.items():
    for _r in _def:
        ROLE_PERMISSIONS.setdefault(_r, []).append((_perm, _o, f"{O6}"))
    for _r in _prop:
        ROLE_PERMISSIONS.setdefault(_r, []).append((_perm, "PROPUESTO", f"{O6} – propuesto, por validar"))
# Retiros (observaciones al demo v0.6): Almacén no accede a los registros de Calidad (formatos); la BOM la aprueba
# Producción y no Almacén.
_RETIROS = {"COORD_ALMACEN": {"calidad.ver"}, "COORD_ALMACEN_MP": {"calidad.ver"},
            "MONTACARGUISTA": {"alertas.gestionar"}}  # el montacarguista no asigna tareas; inicia y termina con foto
for _r, _quitar in _RETIROS.items():
    ROLE_PERMISSIONS[_r] = [x for x in ROLE_PERMISSIONS[_r] if x[0] not in _quitar]

# ---------------------------------------------------------------------------
# Tipos de alerta (IF §14 y secciones de proceso)
# ---------------------------------------------------------------------------
_ALM = ["COORD_ALMACEN", "COORD_ALMACEN_MP"]  # el sistema filtra por el almacén involucrado (Q17)
_LOG = ["JEFE_LOGISTICA", "COORD_LOGISTICA"]
_GO = ["GERENCIA_OPERACIONES"]
_COM = ["JEFE_VENTAS", "COORD_VENTAS"]
_DIST = ["COORD_DISTRIBUCION", "ASIST_DISTRIBUCION"]
_CAL = ["JEFE_CALIDAD", "SUPERV_CALIDAD"]
_PROD = ["JEFE_PRODUCCION", "ASIST_PRODUCCION"]  # no existe Coordinación de Producción ({R14})

ALERT_TYPES = [
    # code, nombre, area, grupo, prioridad, roles, origen, fuente, condicion, correo
    ("OV_FALTANTE", "Faltante de stock en OV", "Almacén", "Faltantes y cobertura", "ALTA", _ALM + _LOG + _GO, "DEFINIDO",
     f"{IF} §6.3", "Al evaluar una OV nueva o modificada con cobertura < 100 %.", True),
    ("OV_DECISION_PARCIAL", "Decisión de despacho parcial requerida", "Logística", "Faltantes y cobertura", "ALTA",
     ["JEFE_LOGISTICA"] + _GO + _COM, "DEFINIDO", f"{IF} §6.3; aprueba GO o Jefatura de Logística (Q3)",
     "OV con faltante y stock reservado parcial. Comercial es informado; aprueba GO o Jefatura de Logística.", True),
    ("OV_COMPLETA", "OV completa con stock reservado", "Almacén", "Estados de pedidos", "MEDIA",
     ["JEFE_LOGISTICA", "JEFE_VENTAS"] + _ALM, "DEFINIDO", "Diagrama de procesos COPROD-ONE: 'Avisar (Jefe de logística, Jefe comercial, coordinador almacén)'",
     "La evaluación reserva el 100 % de la OV.", False),
    ("OV_SALDO_REPROGRAMADO", "Saldo de despacho parcial reprogramado", "Comercial", "Faltantes y cobertura", "ALTA",
     _COM + _ALM + ["JEFE_LOGISTICA"] + _GO, "PROPUESTO", "Decisión Q3 (11-oct-2026): lo que falta despachar se reprograma",
     "Al salir un despacho parcial se crea la OV de saldo con la fecha reprogramada.", True),
    ("OV_PARCIAL_APROBADO", "Despacho parcial aprobado", "Distribución", "Rutas", "ALTA", _DIST, "DEFINIDO",
     f"{IF} §6.3", "Se aprueba entrega parcial; se genera propuesta de ruta.", True),
    ("OV_CAMBIO", "Cambio de OV con reserva existente", "Comercial", "Cambios de OV", "MEDIA", _LOG + _ALM + _GO + _DIST, "DEFINIDO",
     f"{IF} §6.3, §14; {O6}: Distribución recibe los cambios que afectan su plan (p. ej. fecha de entrega)", "Modificación de una OV que ya tenía reservas.", True),
    ("OV_MODIF_SOLICITUD", "Solicitud de modificación de OV (Asistente)", "Comercial", "Cambios de OV", "MEDIA", _COM, "DEFINIDO",
     f"{IF} §5", "El Asistente de Ventas solicita modificar una OV; autorizan Coord./Jefe de Ventas o vendedor responsable.", True),
    ("OV_CANCELADA", "OV cancelada (reserva y ruta liberadas)", "Comercial", "Cambios de OV", "MEDIA", _ALM + _DIST + ["JEFE_LOGISTICA"],
     "PROPUESTO", f"{IF} §5, §14", "Cancelación por Coordinador o Jefe de Ventas.", True),
    ("OV_ESTADO", "Cambio de estado de pedido", "Comercial", "Estados de pedidos", "BAJA", ["COORD_VENTAS"], "PROPUESTO",
     f"{IF} §14", "Cambio de estado relevante de la OV (preparada, despachada, entregada).", False),
    ("OV_80_PREPARACION", "Pedido al 80 % de preparación", "Almacén", "Estados de pedidos", "MEDIA", _DIST + ["COORD_VENTAS"],
     "PROPUESTO", f"{IF} §14 (condición definida; destinatarios propuestos)", "Avance de preparación ≥ umbral configurado (80 %).", False),
    ("OV_PREPARADA", "Término del picking: pedido listo para despacho", "Almacén", "Estados de pedidos", "MEDIA",
     _COM + _GO + ["JEFE_LOGISTICA"] + _DIST + _CAL, "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Generar alerta (comercial, GO, jefe de logística) y documentos para calidad, distribución'",
     "Preparación al 100 %.", True),
    ("OV_RETRASO", "OV no despachada en la fecha comprometida", "Distribución", "Retrasos", "ALTA", _GO + ["JEFE_LOGISTICA", "COORD_VENTAS"],
     "PROPUESTO", f"{IF} §14 ('retrasos')", "Fecha comprometida vencida sin salida registrada.", True),
    ("RESERVA_AFECTADA", "Reserva afectada por actualización de stock", "Almacén", "Faltantes y cobertura", "ALTA", _ALM + ["JEFE_LOGISTICA"],
     "PROPUESTO", f"{IF} §14 ('reservas')", "La nueva carga reduce un lote por debajo de lo reservado.", True),
    ("STOCK_CARGA_DIFERENCIAS", "Diferencias/errores en carga de stock", "Sistemas", "Diferencias de inventario", "MEDIA",
     ["SISTEMAS"] + _ALM, "DEFINIDO", f"{IF} §6.4 (alertar a Sistemas)", "Carga confirmada con filas corregidas/excluidas o diferencias.", True),
    ("INVENTARIO_DIFERENCIA", "Diferencia de inventario en conteo físico", "Almacén", "Diferencias de inventario", "MEDIA",
     ["SISTEMAS"] + _ALM + _GO, "PROPUESTO", f"{IF} §6.4, §14", "Conteo cerrado con faltantes o sobrantes.", True),
    ("STOCK_PENDIENTE_REVISION", "Carga recibida pendiente de revisión de Calidad", "Calidad", "Calidad", "MEDIA", _CAL, "PROPUESTO",
     f"{IF} §6.1, §9.4", "Nuevo lote en estado Pendiente de revisión.", False),
    ("STOCK_NO_UTILIZABLE", "Producto no utilizable / requiere fumigación", "Calidad", "Fumigación y no utilizables", "ALTA",
     _CAL + _ALM + ["JEFE_LOGISTICA"], "PROPUESTO", f"{IF} §6.1, §14", "Lote pasa a No utilizable o supera tiempo máximo de almacenamiento configurado.", True),
    ("FUMIGACION", "Fumigación iniciada/finalizada", "Calidad", "Fumigación y no utilizables", "MEDIA", _CAL + _ALM + _LOG + _GO, "DEFINIDO",
     f"{IF} §14; REG-BPM-CAL-005; {O6}: la reciben Almacén, Calidad, Logística y GO", "Registro de inicio/fin de fumigación.", False),
    ("VENCIMIENTO_PROXIMO", "Lote próximo a vencer", "Almacén", "Faltantes y cobertura", "MEDIA", _ALM + ["COORD_VENTAS"], "PENDIENTE",
     f"{IF} §21 (caso 'vencimiento'); umbral no definido", "Solo si se configura 'dias_vencimiento_proximo'.", False),
    ("TRASLADO_SOLICITADO", "Traslado pendiente de autorización", "Logística", "Traslados", "MEDIA", _LOG, "DEFINIDO",
     f"{IF} §6.2, §13; {R12} Q13", "Se solicita (o el sistema pre-solicita) un traslado desde almacén alternativo.", True),
    ("TRASLADO_AUTORIZADO", "Traslado autorizado", "Almacén", "Traslados", "MEDIA", _ALM + ["AUX_ALMACEN", "MONTACARGUISTA"], "DEFINIDO",
     f"{IF} §13; {O6}: la planeación del traslado le llega al montacarguista", "Logística autoriza el traslado.", False),
    ("COTIZACION_IMPACTO", "Cotización con impacto en precios", "Comercial", "Indicadores", "ALTA",
     ["JEFE_VENTAS", "GERENTE_COMERCIAL", "COMPRAS", "IMPORTACIONES"] + _GO, "DEFINIDO",
     "Decisión del usuario (14-oct-2026): comparar cotizaciones de importación y compras nacionales y reportes de importación (internet y Estado) con los precios para ver el posible impacto",
     "Una cotización deja el margen sobre el precio mínimo bajo el umbral o supera el precio de referencia de mercado/importación.", False),
    ("RESERVA_VENCIDA", "Reserva que supera el plazo máximo", "Almacén", "Estados de pedidos", "MEDIA",
     _ALM + _LOG + ["COORD_VENTAS"], "DEFINIDO", "Decisión del usuario (14-oct-2026): plazo máximo de reserva 7 días por el espacio físico del almacén",
     "Stock reservado para una OV hace más días que el plazo máximo (ocupa espacio). Se avisa también al vendedor.", False),
    ("TRASLADO_LLEGADA", "Llegada programada de traslado", "Almacén", "Traslados", "MEDIA", _ALM + ["AUX_ALMACEN", "MONTACARGUISTA"] + _CAL + ["ASIST_CALIDAD"],
     "DEFINIDO", "Observaciones al demo v0.5 (13-oct): al autorizar se ingresa fecha y hora de llegada para alertar a Calidad (revisión) y Almacén (almacenamiento)",
     "Se registra o cambia la fecha y hora de llegada de un traslado autorizado; se repite el día de la llegada si no se recibió.", False),
    ("COMPRA_SOBRE_COSTO_MAXIMO", "Cotización sobre el costo máximo de compra", "Compras", "Compras", "ALTA",
     ["COMPRAS"] + _LOG, "DEFINIDO",
     "Observaciones al demo v0.5 (13-oct): costo máximo a que se debe comprar para no caer en pérdida (configurable)",
     "El precio cotizado supera el costo máximo de compra configurado para el artículo.", False),
    ("FUMIGACION_PROXIMA", "Fumigación próxima (7 días, 3 días y el mismo día)", "Calidad", "Calidad", "ALTA",
     _CAL + ["ASIST_CALIDAD"] + _ALM + _LOG + _GO, "DEFINIDO",
     "Observaciones al demo v0.5 (13-oct): alerta a Calidad 7 días antes, 3 días antes y el mismo día para planear la fumigación",
     "Lote con fumigación programada o con fin del tiempo máximo de almacenamiento a 7, 3 o 0 días.", False),
    ("RUTA_EXTERNO_VALIDAR", "Ruta con transporte externo por validar", "Distribución", "Programación", "ALTA",
     ["COORD_DISTRIBUCION"], "DEFINIDO", "Observaciones al demo v0.5 (13-oct): el transporte externo lo valida el coordinador de distribución",
     "La programación asigna transporte externo (sin unidad propia con capacidad o unidad de tercero).", False),
    ("RUTA_TRAFICO", "Tráfico que puede comprometer la entrega", "Distribución", "Programación", "ALTA",
     ["COORD_DISTRIBUCION", "ASIST_DISTRIBUCION"] + _LOG, "DEFINIDO",
     "Observaciones al demo v0.5 (13-oct): alertas de tráfico que podrían comprometer la entrega",
     "Con el servicio de mapas configurado: el tráfico agrega más del umbral o una cita ya no se alcanza. Se avisa también al vendedor.", False),
    ("BOM_OBSERVADA", "Lista de materiales observada por Producción", "Producción", "Solicitudes", "MEDIA",
     ["JEFE_PRODUCCION", "SISTEMAS"], "DEFINIDO",
     "Observaciones al demo v0.5 (13-oct): Producción visualiza si la lista de materiales asignada es la correcta",
     "Producción indica que la lista de materiales de una solicitud no es la correcta.", False),
    ("TRASLADO_DIFERENCIA", "Diferencia en recepción de traslado", "Logística", "Traslados", "ALTA", ["JEFE_LOGISTICA"] + _ALM + _GO,
     "PROPUESTO", f"{IF} §13", "Cantidad recibida distinta a la enviada.", True),
    ("OV_PRECIO_BAJO_MINIMO", "OV detenida: precio en el límite o por debajo de la lista", "Comercial", "Cambios de OV", "ALTA",
     ["JEFE_VENTAS", "COORD_VENTAS", "GERENTE_COMERCIAL"], "DEFINIDO",
     f"{R13} Q11; {R14}: se alerta y queda detenida hasta la confirmación del Coordinador o Jefe Comercial",
     "Línea de OV (incluidas las muestras comerciales) con precio igual o menor al mínimo de lista del canal. También se "
     "avisa al vendedor de la OV.", True),
    ("OV_PRECIO_BAJO_COSTO", "OV detenida: precio de venta por debajo del costo", "Comercial", "Cambios de OV", "ALTA",
     ["JEFE_VENTAS", "COORD_VENTAS", "GERENTE_COMERCIAL"], "DEFINIDO",
     "Respuestas del 13-oct (R4): 'validar que ninguna venta se realice por debajo' del costo",
     "Línea de OV con precio menor al costo vigente del artículo en la unidad de venta. La OV queda detenida hasta la "
     "confirmación del Coordinador o Jefe Comercial. El mensaje no muestra el costo a quien no tiene 'costos.ver'.", True),
    ("COSTO_SOBRE_MERCADO", "Costo de la empresa sobre o cerca del precio de mercado", "Comercial", "Indicadores", "MEDIA",
     ["JEFE_VENTAS", "GERENTE_COMERCIAL"], "DEFINIDO",
     "Respuestas del 13-oct (R4): comparar automáticamente contra costos de mercado y tendencias",
     "Comparación automática diaria: costo por kg del artículo vs último precio mayorista del producto base, con "
     "tendencia y recomendación.", True),
    ("PRECIO_FALTANTE", "Producto o cliente sin precio mínimo", "Comercial", "Cambios de OV", "MEDIA", ["JEFE_VENTAS"], "DEFINIDO",
     f"{R14}: 'el sistema debe botar una alerta y en base a eso ir completando'",
     "Una OV trae un producto sin precio mínimo para el canal del cliente, o un cliente sin canal de precios asignado.", True),
    ("LISTA_PRECIOS_VENCIDA", "Lista de precios vencida o por vencer", "Comercial", "Cambios de fechas", "MEDIA", ["JEFE_VENTAS"],
     "DEFINIDO", f"{R14}: 'se avisa pero no se bloquea'", "Fecha de vencimiento de la lista alcanzada (o dentro del aviso).", True),
    ("CARGA_SAP_DESACTUALIZADA", "Carga de SAP sin actualizar", "Sistemas", "Diferencias de inventario", "ALTA", ["SISTEMAS"],
     "DEFINIDO", f"{R14}: cada área exporta a diario, con cortes de 2 veces al día como mínimo",
     "La última carga autorizada de un tipo supera las horas configuradas; se avisa al área responsable y a Sistemas.", False),
    ("PRESOLICITUD_AUTOMATICA", "Pre-solicitudes generadas por faltante", "Almacén", "Solicitudes", "ALTA", _ALM + _LOG,
     "DEFINIDO", f"{TOBE}; {R12} Q15 (orden: producir, reempaque, traslado, compra)",
     "La OV queda con faltante y el sistema genera la pre-solicitud de la primera opción viable.", True),
    ("PRODUCCION_SOLICITUD", "Solicitud de producción enviada", "Producción", "Solicitudes", "ALTA", _PROD, "DEFINIDO",
     f"{IF} §8.2, §14", "Almacén envía solicitud preliminar.", True),
    ("PRODUCCION_RESPUESTA", "Solicitud de producción validada/rechazada", "Producción", "Solicitudes", "MEDIA", _ALM + ["COORD_VENTAS"],
     "PROPUESTO", f"{IF} §8.2", "Producción valida o rechaza.", True),
    ("LIQUIDACION_MONTACARGUISTA", "Liquidación registrada: mover producto terminado", "Almacén", "Solicitudes", "ALTA",
     ["MONTACARGUISTA"] + _ALM, "DEFINIDO", f"{IF} §8.3", "Al registrar una liquidación.", False),
    ("LIQUIDACION_DIFERENCIA", "Diferencia entre liquidación y recepción de PT", "Almacén", "Diferencias de inventario", "ALTA",
     _PROD + _ALM, "PROPUESTO", f"{IF} §8.3; hoja 'Cruce' de Recep. pt.xlsx", "Recepción física ≠ cantidad completada.", True),
    ("MERMA_FUERA_PARAMETRO", "Merma fuera de parámetros", "Producción", "Merma", "ALTA", _PROD + _GO, "PENDIENTE",
     f"{IF} §14 ('cuando se defina el umbral')", "Solo si se configura 'umbral_merma_pct'.", True),
    ("REEMPAQUE_PRESOLICITUD", "Pre-solicitud de reempaque por aprobar", "Almacén", "Solicitudes", "ALTA", _ALM, "DEFINIDO",
     f"{TOBE}; {R12} Q12", "El sistema genera la pre-solicitud; el Coordinador de Almacén la aprueba y envía a Calidad.", True),
    ("REEMPAQUE_SOLICITUD", "Solicitud de reempaque para evaluación", "Calidad", "Solicitudes", "ALTA", _CAL, "DEFINIDO",
     f"{IF} §9.1; {R12} Q12", "El Coordinador de Almacén aprueba y envía la solicitud.", True),
    ("REEMPAQUE_APROBADO", "Reempaque aprobado: ejecutar", "Producción", "Solicitudes", "ALTA", _ALM + _PROD, "DEFINIDO",
     f"{IF} §9.1 (notifica a Almacén y envía a Producción)", "Calidad aprueba.", True),
    ("REEMPAQUE_DESAPROBADO", "Reempaque desaprobado", "Almacén", "Solicitudes", "MEDIA", _ALM, "PROPUESTO", f"{IF} §9.1",
     "Calidad desaprueba.", True),
    ("COMPRA_APROBACION_LOGISTICA", "Solicitud de compra por aprobar (Jefe de Logística)", "Logística", "Solicitudes", "ALTA",
     ["JEFE_LOGISTICA"], "DEFINIDO", f"{TOBE}; {R12} Q14", "Almacén envía la solicitud o el sistema genera la pre-solicitud.", True),
    ("COMPRA_SOLICITUD", "Solicitud de compra aprobada por Logística", "Compras", "Solicitudes", "MEDIA", ["COMPRAS"], "DEFINIDO",
     f"{IF} §10.1, §14; {R12} Q14", "El Jefe de Logística aprueba la solicitud.", True),
    ("COMPRA_MUESTRA", "Muestra de compra para evaluación", "Calidad", "Solicitudes", "MEDIA", _CAL, "DEFINIDO", f"{IF} §10.2-10.3",
     "Compras lleva muestra a Calidad.", True),
    ("COMPRA_APROBACION_GERENCIA", "Compra que requiere aprobación de Gerencia de Operaciones", "Gerencia", "Solicitudes", "ALTA", _GO,
     "DEFINIDO", f"{IF} §7; decisión del usuario (14-oct-2026): materia prima siempre requiere a Gerencia de Operaciones",
     "Compra de materia prima (siempre) o de mayor volumen (cantidad ≥ umbral configurado).", True),
    ("COMPRA_RECEPCION_PROGRAMAR", "Programar recepción de compra", "Almacén", "Cambios de fechas", "MEDIA", _ALM, "DEFINIDO",
     f"{IF} §10.6", "Compras registra fecha prevista de recepción.", True),
    ("COMPRA_FECHA_CAMBIO", "Cambio de fecha de compra nacional", "Compras", "Cambios de fechas", "MEDIA", _ALM + _GO, "DEFINIDO",
     f"{IF} §10 (cambios generan alerta a Almacén y GO)", "Compras modifica la fecha prevista.", True),
    ("COMPRA_DIFERENCIA", "Diferencias en recepción de compra", "Compras", "Diferencias de inventario", "ALTA", ["COMPRAS"] + _CAL,
     "DEFINIDO", f"{IF} §10.7", "Almacén/Calidad detectan diferencias.", True),
    ("REPOSICION_SUGERIDA", "Reposición sugerida", "Almacén", "Solicitudes", "MEDIA", _ALM + ["COMPRAS"], "PROPUESTO",
     f"{IF} §7 (alerta, cantidad sugerida, fecha estimada)", "Análisis de reposición detecta necesidad.", True),
    ("IMPORT_LLEGADA", "Llegada estimada de importación", "Importaciones", "Cambios de fechas", "MEDIA", _ALM + _LOG, "DEFINIDO",
     f"{IF} §11", "Registro o actualización de la llegada estimada.", True),
    ("IMPORT_MODIFICACION", "Modificación de fechas de importación", "Importaciones", "Cambios de fechas", "ALTA", _GO + _ALM + _LOG,
     "DEFINIDO", f"{IF} §11", "Cambio de fecha de llegada o fase.", True),
    ("IMPORT_FASE_VENCIDA", "Fase de importación fuera de fecha", "Importaciones", "Retrasos", "ALTA", ["IMPORTACIONES"], "DEFINIDO",
     f"{IF} §11", "Fecha prevista de fase vencida sin fecha real.", True),
    ("IMPORT_RECORDATORIO", "Recordatorio de fase de importación", "Importaciones", "Cambios de fechas", "BAJA", ["IMPORTACIONES"],
     "DEFINIDO", f"{IF} §11 (recordatorios configurables)", "Faltan N días para la fecha prevista de una fase.", False),
    ("IMPORT_DIFERENCIA", "Diferencias en recepción de importación", "Importaciones", "Diferencias de inventario", "ALTA",
     ["IMPORTACIONES"] + _CAL, "DEFINIDO", f"{IF} §11", "Recepción con diferencias.", True),
    ("DIST_PROGRAMACION", "Programación de distribución generada", "Distribución", "Rutas", "MEDIA", _DIST + _LOG + _GO + _COM + _CAL,
     "DEFINIDO", f"{IF} §12.1; diagrama de procesos: notificar a todas las áreas (calidad, comercial, GO, jefe de logística)",
     "Se genera/confirma la programación de rutas.", True),
    ("RUTA_ASIGNADA", "Ruta asignada (chofer y auxiliar)", "Distribución", "Rutas", "MEDIA", ["AUX_DESPACHO", "CONDUCTOR"], "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Generar alerta para chofer y auxiliar de las rutas que le fueron asignadas'", "Distribución aprueba la ruta.", False),
    ("MONTACARGUISTA_DESPACHO", "Trasladar mercadería a la zona de despacho", "Almacén", "Rutas", "MEDIA", ["MONTACARGUISTA"], "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Generar alerta para el traslado del montacarguista'", "Ruta aprobada con pedidos preparados.", False),
    ("CARGA_INCONGRUENCIA", "Incongruencia en la carga: validación cruzada", "Almacén", "Guías", "ALTA", ["LIDER_ALMACEN", "COORD_ALMACEN"],
     "DEFINIDO", "Diagrama de procesos COPROD-ONE: 'Avisar a almacenero asignado para la validación cruzada'",
     "El auxiliar detecta productos incorrectos o incompletos frente a la pre-guía.", True),
    ("CAMION_CARGADO", "Camión cargado y validado", "Distribución", "Rutas", "MEDIA",
     _COM + _GO + ["JEFE_LOGISTICA", "COORD_DISTRIBUCION", "FACTURACION"], "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Generar alerta de camión cargado (comercial, GO, jefe de logística, distribución, facturación)'",
     "Carga validada completa y correcta con foto.", True),
    ("INC_CARGA", "Incidencia durante la carga (Seguridad)", "Seguridad", "Incidencias", "ALTA",
     ["COORD_DISTRIBUCION", "JEFE_LOGISTICA"] + _GO, "PROPUESTO", "Diagrama de procesos COPROD-ONE: 'Subir foto de la incidencia ocurrida mientras se despachaba'",
     "Seguridad registra una incidencia con foto, motivo y hora.", True),
    ("DOCUMENTOS_FALTANTES", "Documentos faltantes para la salida", "Seguridad", "Guías", "ALTA",
     ["COORD_DISTRIBUCION", "FACTURACION", "JEFE_LOGISTICA"] + _CAL + _GO, "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Reportar documentos faltantes (distribución, facturación, calidad, jefe logística, GO)'",
     "Seguridad revisa y faltan guía, factura o certificado aprobado.", True),
    ("DIST_LLEGADA", "Llegada al punto de entrega", "Distribución", "Rutas", "BAJA", ["COORD_DISTRIBUCION", "JEFE_LOGISTICA"] + _GO,
     "DEFINIDO", "Diagrama de procesos COPROD-ONE: 'Notificar a coordinador de distribución, jefe de logística, GO que se llegó'", "Llegada registrada.", False),
    ("DIST_ENTREGADO", "Pedido entregado con conformidad", "Distribución", "Rutas", "BAJA",
     ["COORD_DISTRIBUCION", "JEFE_LOGISTICA"] + _GO + _COM, "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Notificar a coordinador de distribución, jefe de logística, GO, comercial que se entregó'", "Entrega con foto y guía firmada.", False),
    ("DIST_AVANCE_RUTA", "Avance de ruta", "Distribución", "Rutas", "BAJA", _COM + _LOG + ["COORD_DISTRIBUCION"], "DEFINIDO",
     f"{IF} §12.3", "Salida, llegada, entrega.", False),
    ("GUIA_DISCREPANCIA", "Discrepancia entre carga y guía: salida bloqueada", "Seguridad", "Guías", "ALTA",
     ["COORD_DISTRIBUCION", "SEGURIDAD"] + _LOG, "DEFINIDO", f"{IF} §12.2, §14; {R12} Q8",
     "Cantidad cargada ≠ guía o presentación no coincide. Bloquea la salida salvo aprobación de Logística.", True),
    ("SALIDA_CON_DISCREPANCIA", "Salida aprobada con guía por resolver", "Logística", "Guías", "ALTA",
     ["COORD_DISTRIBUCION", "SEGURIDAD", "LIDER_ALMACEN"] + _LOG + _GO, "DEFINIDO", f"{R12} Q8",
     "Jefe o Coordinador de Logística aprueba la salida mientras se resuelve la guía.", True),
    ("INC_RECHAZO_CALIDAD", "Incidencia de calidad (rechazo, infestación, fuera de características)", "Distribución", "Incidencias", "ALTA",
     ["GERENCIA_GENERAL"] + _GO + _LOG + _ALM + _COM + ["COORD_DISTRIBUCION"] + _CAL, "DEFINIDO",
     f"{IF} §12.3 (tabla de destinatarios); diagrama de procesos (coord. distribución); observaciones al demo v0.5 (tipo Calidad: también a Calidad)",
     "Incidencia de tipo Calidad.", True),
    ("INC_GENERAL", "Incidencia de distribución (llegada tarde u otra condición)", "Distribución", "Incidencias", "ALTA",
     _GO + _LOG + _ALM + _COM + ["COORD_DISTRIBUCION"], "DEFINIDO", f"{IF} §12.3 (tabla de destinatarios); diagrama de procesos (coord. distribución)",
     "Retraso, rechazo por cita, devolución, parcial, vehículo esperando, etc.", True),
    ("CERTIFICADO_REVISION", "Certificado pre-elaborado pendiente de revisión", "Calidad", "Certificados", "MEDIA", _CAL, "DEFINIDO",
     f"{IF} §9.3, §9.4; diagrama de procesos: 'Informar a Calidad para la validación del certificado pre-elaborado'",
     "Se genera el certificado cuando la OV queda completa (diagrama de procesos) o al terminar la preparación.", False),
    ("CERTIFICADO_LISTO", "Certificado aprobado y cargado", "Calidad", "Certificados", "MEDIA",
     ["COORD_DISTRIBUCION"] + _GO + ["JEFE_LOGISTICA"], "DEFINIDO",
     "Diagrama de procesos COPROD-ONE: 'Notifica a distribución, GO, jefe de logística que el certificado fue cargado'", "Calidad aprueba el certificado.", False),
    ("CALIDAD_NO_CONFORME", "Producto/registro no conforme", "Calidad", "Calidad", "ALTA", _CAL + _GO, "PROPUESTO",
     "REG-BPM-CAL-013, REG-HACCP-CAL-002", "Registro de Calidad con resultado No conforme.", True),
]

ALERT_TYPES += [
    ("OV_CONDICION_CLIENTE", "Stock que no cumple la condición del cliente", "Almacén", "Faltantes y cobertura", "ALTA",
     _ALM + _LOG, "DEFINIDO", f"{O6}: solo se toman productos que cumplan la condición del cliente; si no, se alerta el motivo",
     "Hay lotes del producto pero no cumplen la vida útil u otra condición del cliente.", True),
    ("CLIENTE_VARIACION_COMPRA", "Cliente pide más o menos de lo habitual", "Comercial", "Comportamiento de clientes", "MEDIA",
     _COM + ["GERENTE_COMERCIAL"], "DEFINIDO", f"{O6}: alertas si el cliente pide menos o más y de qué productos o presentaciones",
     "Variación de la cantidad pedida por producto o presentación sobre el umbral configurado.", False),
    ("PICKING_PROGRAMADO", "Picking preprogramado por el sistema", "Almacén", "Preparación", "MEDIA",
     ["LIDER_ALMACEN"] + _ALM, "DEFINIDO", f"{O6}: al líder y al coordinador de almacén les llega la preprogramación del picking",
     "OV lista para preparar: picking programado con auxiliar propuesto para revisar y asignar.", True),
    ("PICKING_ASIGNADO", "Picking asignado", "Almacén", "Preparación", "MEDIA", [], "DEFINIDO",
     f"{O6}: al auxiliar le llega su programación de picking", "Se le asignó un picking (persona o grupo).", True),
    ("FLOTA_DOCUMENTO", "Documento del vehículo por vencer o vencido (SOAT, revisión, impuestos)", "Distribución", "Flota",
     "ALTA", _DIST, "DEFINIDO", f"{O6}: alerta cuando el SOAT, impuestos u otros estén por vencer",
     "Vencimiento dentro de los días de aviso configurados.", True),
    ("FLOTA_MANTENIMIENTO", "Mantenimiento de vehículo por kilometraje o fecha", "Distribución", "Flota", "MEDIA", _DIST,
     "DEFINIDO", f"{O6}: alertas respecto a los kilometrajes y estado de mantenimiento",
     "El vehículo se acerca al kilometraje o fecha del próximo mantenimiento.", True),
    ("TAREA_ASIGNADA", "Tarea designada a usted o a su cargo", "General", "Tareas", "MEDIA", [], "DEFINIDO",
     f"{O6}: el designado recibe la tarea en su inicio y una alerta", "Una persona de su área le designó una tarea.", True),
]

# Naturaleza de cada tipo (observaciones al demo v0.6): solo se vuelven tareas las que requieren aprobación o atención;
# las informativas se reconocen. Clasificación PROPUESTA, editable en Configuración de alertas.
ALERT_INFORMATIVAS = {"CLIENTE_VARIACION_COMPRA", "OV_COMPLETA", "OV_SALDO_REPROGRAMADO", "OV_CANCELADA", "OV_ESTADO", "OV_80_PREPARACION", "OV_PREPARADA",
                      "VENCIMIENTO_PROXIMO", "FUMIGACION", "COTIZACION_IMPACTO", "COSTO_SOBRE_MERCADO", "PRODUCCION_RESPUESTA",
                      "REEMPAQUE_DESAPROBADO", "COMPRA_FECHA_CAMBIO", "IMPORT_LLEGADA", "IMPORT_MODIFICACION",
                      "IMPORT_RECORDATORIO", "DIST_PROGRAMACION", "CAMION_CARGADO", "DIST_LLEGADA", "DIST_ENTREGADO",
                      "DIST_AVANCE_RUTA", "CERTIFICADO_LISTO"}

# Incidencias (IF §12.3) organizadas por tipo y subtipo (observaciones al demo v0.5, 13-oct).
# "Llegada tarde" y "rechazo por cita fuera de hora" son la misma incidencia.
INCIDENT_GROUPS = [("CALIDAD", "Calidad"), ("LOGISTICA", "Logística"), ("CLIENTE", "Cliente / Comercial")]
INCIDENT_SUBTYPES = [
    # código, nombre, tipo
    ("INFESTACION_INTERNA", "Infestación interna", "CALIDAD"),
    ("INFESTACION_EXTERNA", "Infestación externa", "CALIDAD"),
    ("FUERA_CARACTERISTICAS", "Producto fuera de características", "CALIDAD"),
    ("RECHAZO_CALIDAD", "Rechazo por calidad", "CALIDAD"),
    ("PARTICULARIDAD_DESCARGA", "Particularidad detectada en la mercadería en la misma descarga", "CALIDAD"),
    ("LLEGADA_TARDE", "Llegada tarde / rechazo por cita fuera de hora", "LOGISTICA"),
    ("ENTREGA_PARCIAL", "Entrega parcial", "LOGISTICA"),
    ("PRODUCTO_ROTO", "Producto roto", "LOGISTICA"),
    ("RETRASO", "Retraso en ruta", "LOGISTICA"),
    ("VEHICULO_ESPERANDO", "Vehículo esperando", "LOGISTICA"),
    ("CAMBIO_RUTA", "Cambio de ruta", "LOGISTICA"),
    ("CONDUCTOR_NO_DISPONIBLE", "Falta de disponibilidad del conductor", "LOGISTICA"),
    ("INCIDENCIA_CARGA", "Incidencia durante la carga, registrada por Seguridad", "LOGISTICA"),
    ("CLIENTE_AUSENTE", "Cliente ausente", "CLIENTE"),
    ("CLIENTE_NO_RETIRA", "Cliente que no retira pedido", "CLIENTE"),
    ("RECHAZO_OTRO", "Rechazo (otro motivo)", "CLIENTE"),
    ("DEVOLUCION", "Devolución", "CLIENTE"),
    ("CANCELACION", "Cancelación", "CLIENTE"),
]
INCIDENT_TYPES = [(c, n) for c, n, _ in INCIDENT_SUBTYPES]
INCIDENT_GROUP = {c: g for c, _, g in INCIDENT_SUBTYPES}
INCIDENT_ALIASES = {"RECHAZO_CITA": "LLEGADA_TARDE"}  # registros anteriores

# Gerencia General: tipos que recibe directamente por correo por defecto (el resto en panel). IF §14.
GG_DIRECT_DEFAULT = ["INC_RECHAZO_CALIDAD"]

# ---------------------------------------------------------------------------
# Parámetros (IF §16)
# ---------------------------------------------------------------------------
PARAMS = [
    # key, valor, tipo, grupo, descripcion, estado, fuente
    ("margen_reposicion_dias", None, "int", "Reposición",
     "Margen adicional (días naturales) por posibles atrasos; aplicable por producto/material (campo en catálogo) o global.",
     "PENDIENTE", f"{IF} §7, §16, §20"),
    ("periodo_analisis_dias", 15, "int", "Reposición",
     "Período de análisis por defecto para consumo promedio (cada producto puede tener el suyo).",
     "ACTUAL", "Macro VBA 'TraerLotesStock' (PROM_15D) en PCP 2026 - J.xlsm"),
    ("factor_stock_seguridad", 0.30, "float", "Reposición",
     "Stock de seguridad como % del consumo mensual promedio observado en el Excel actual. Solo se aplica si 'usar_stock_seguridad' = sí.",
     "ACTUAL", "Rotacion de inventario - Almacenes.xlsx, hoja Reporte ('30% stk seg')"),
    ("usar_stock_seguridad", False, "bool", "Reposición",
     "Aplicar el factor de stock de seguridad proceso actual en el análisis de reposición.", "PENDIENTE", f"{IF} §16 (stock mínimo configurable)"),
    ("umbral_mayor_volumen", None, "float", "Compras",
     "Valor a partir del cual una compra se considera de mayor volumen (en la unidad elegida abajo).", "PENDIENTE", f"{IF} §7, §20; {R14}"),
    ("umbral_mayor_volumen_unidad", "KG", "str", "Compras",
     "Unidad del umbral: KG (cantidad × peso del artículo), UNIDADES o SOLES (cantidad × precio cotizado).",
     "DEFINIDO", f"{R14}: se configura en el panel"),
    ("tiempo_traslado_dias", 2, "int", "Almacén", "Plazo estimado de un traslado desde almacén externo (para comparar opciones de la OV).",
     "PROPUESTO", "Especificación funcional maestra (14-oct) §5.2: referencia inicial ~2 días"),
    ("tiempo_produccion_dias", 2, "int", "Producción", "Plazo estimado de producción (para comparar opciones de la OV).",
     "PROPUESTO", "Especificación funcional maestra (14-oct) §5.2: referencia inicial 1–2 días"),
    ("tiempo_reempaque_dias", 3, "int", "Almacén", "Plazo estimado de reempaque (para comparar opciones de la OV).",
     "PROPUESTO", "Especificación funcional maestra (14-oct) §5.2: referencia inicial 2–3 días"),
    ("variacion_compra_alerta_pct", 30, "float", "Comercial",
     "Variación (%) de la cantidad pedida por producto o presentación de un cliente que genera alerta (segunda mitad del periodo vs primera).",
     "PROPUESTO", "Observaciones al demo v0.6: alertas si el cliente pide menos o más; umbral por validar"),
    ("variacion_compra_dias", 90, "int", "Comercial", "Periodo (días) para comparar el comportamiento de compra del cliente.",
     "PROPUESTO", "Observaciones al demo v0.6; periodo por validar"),
    ("dias_picking_antes_despacho", 1, "int", "Almacén",
     "Días antes de la fecha comprometida en que el sistema preprograma el picking (nunca antes de hoy).",
     "DEFINIDO", "Observaciones al demo v0.6; confirmado por el usuario (15-oct-2026): 1 día"),
    ("dias_aviso_documentos_vehiculo", 15, "int", "Distribución",
     "Días de anticipación con que se avisa el vencimiento de SOAT, revisión técnica y demás documentos del vehículo.",
     "DEFINIDO", "Observaciones al demo v0.6; confirmado por el usuario (15-oct-2026): 15 días"),
    ("margen_km_mantenimiento", 500, "float", "Distribución",
     "Kilómetros antes del mantenimiento programado en que se avisa a Distribución.",
     "DEFINIDO", "Observaciones al demo v0.6; confirmado por el usuario (15-oct-2026): 500 km"),
    ("capacidad_lineas", [
        {"grupo": "IQ+CIMB", "proceso": "SELECCION", "lineas": ["CIMBRIA"], "kg_dia": 25500},
        {"grupo": "TRUER", "proceso": "SELECCION", "lineas": ["TRUER"], "kg_dia": 12750},
        {"grupo": "SEL. MANUAL", "proceso": "SELECCION", "lineas": ["SEL_MANUAL"], "kg_dia": 4250},
        {"grupo": "RAUMAK 1 Y 2", "proceso": "ENVASADO", "lineas": ["R1", "R2"], "kg_dia": 18700},
        {"grupo": "RAUMAK 3", "proceso": "ENVASADO", "lineas": ["R3"], "kg_dia": 29750},
        {"grupo": "ENV. MANUAL", "proceso": "ENVASADO", "lineas": ["ENV_MANUAL"], "kg_dia": 2550}], "list", "Producción",
     "Capacidad por línea (kg/día) por proceso. La relación de cada grupo con las líneas del sistema (IQ+CIMB = Cimbria; "
     "RAUMAK 1 y 2 = R1 y R2; RAUMAK 3 = R3) es una interpretación por confirmar.",
     "DEFINIDO", "Tabla de capacidades enviada por el usuario (14-oct-2026); la correspondencia con los códigos de línea es propuesta"),
    ("dias_operacion", {"0": 1, "1": 1, "2": 1, "3": 1, "4": 1, "5": 0.5, "6": 0}, "dict", "Producción",
     "Fracción de jornada operativa por día de la semana (0 = lunes … 6 = domingo) para calcular la capacidad del periodo.",
     "DEFINIDO", "Decisión del usuario (15-oct-2026): sábados hasta mediodía; domingos no se opera"),
    ("feriados", [], "list", "Producción",
     "Feriados sin operación (fechas AAAA-MM-DD). No se cuentan en la capacidad del periodo.",
     "DEFINIDO", "Decisión del usuario (15-oct-2026): feriados no se opera; la lista de fechas la registra Sistemas"),
    ("plazo_max_reserva_dias", 7, "int", "Almacén",
     "Plazo máximo de reserva por el espacio físico del almacén: el stock de una OV se reserva recién desde esta cantidad de "
     "días antes de la fecha comprometida (antes solo se calcula la cobertura proyectada) y se alerta si una reserva supera el plazo.",
     "DEFINIDO", "Decisión del usuario (14-oct-2026): 'Plazo máximo de reserva 7 días por el espacio físico de almacén'"),
    ("tipos_compra_requieren_go", ["MP", "GR"], "list", "Compras",
     "Tipos de artículo cuya compra requiere SIEMPRE la aprobación de Gerencia de Operaciones, sin importar el volumen.",
     "DEFINIDO", "Decisión del usuario (14-oct-2026): 'compras materia prima requiere autorización de Gerencia de Operaciones sí o sí'; "
     "observaciones al demo v0.6: también las de granel (GR)"),
    ("mayor_volumen_requiere_go", True, "bool", "Compras",
     "La compra de mayor volumen requiere aprobación de Gerencia de Operaciones (además del Jefe de Logística).",
     "DEFINIDO", f"{IF} §7; {R14}: configuración automática Gerencia de Operaciones"),
    ("merma_pct_global", None, "float", "Producción",
     "Porcentaje de merma por defecto (el catálogo de producto/material puede tener uno propio).", "PENDIENTE", f"{IF} §8.1, §16, §20"),
    ("prefijos_no_material_bom", ["RE-"], "list", "Producción",
     "Prefijos de componentes BOM que no son materiales inventariables (mano de obra, costo CIF). No se verifican contra stock.",
     "PROPUESTO", "LISTA DE MATERIALES 2026.xlsx (RE-xxx = 'MANO DE OBRA' / 'COSTO CIF')"),
    ("umbral_merma_pct", None, "float", "Producción",
     "Merma real (%) a partir de la cual se alerta 'merma fuera de parámetros'.", "PENDIENTE", f"{IF} §14"),
    ("cortes_preparacion", [], "list", "Almacén",
     "Horarios de corte (HH:MM) que organizan la preparación.", "PENDIENTE", f"{IF} §4.9, §16"),
    ("tiempos_preparacion", {"PEQUENO": "20-30 min", "MEDIANO": "1 h - 1 h 30", "GRANDE": "4 h (requiere 2 días de anticipación)"},
     "dict", "Almacén", "Tiempos de preparación iniciales por tamaño de pedido (provisionales; medir y ajustar).",
     "ACTUAL", "Diagrama de proceso actual L5 (Revisar el stock físico vs. lo solicitado); IF §20"),
    ("umbrales_tamano_pedido_kg", None, "dict", "Almacén",
     "Límites en kg para clasificar pedido pequeño/mediano/grande.", "PENDIENTE", "No definido en la documentación"),
    ("umbral_alerta_preparacion_pct", 80, "int", "Almacén", "Avance de preparación que dispara la alerta.", "DEFINIDO", f"{IF} §14"),
    ("orden_prioridad", ["fecha_compromiso", "penalidad", "completitud", "urgencia"], "list", "Almacén",
     "Criterios de prioridad en el orden aplicado. 'penalidad': a igual fecha, primero el cliente con penalidades más "
     "severas (lista de clientes con penalidades). Validado el 13-oct (R3).",
     "DEFINIDO", f"{IF} §1, §5, §12.1; {R14} (lista de clientes con penalidades para priorizar)"),
    ("peso_penalidad", {"RETIRO_PROVEEDOR": 5, "FECHA_ENTREGA": 4, "FILL_RATE": 4, "ENTREGA_PARCIAL": 3,
                        "RUPTURA_STOCK": 3, "VENTANA_HORARIA": 2, "PESO": 2, "PALETIZADO": 2, "DOCUMENTOS": 1,
                        "NO_CONFORMIDADES": 1}, "dict", "Almacén",
     "Peso de cada tipo de penalidad del cliente para la prioridad (suma). Validados el 13-oct (R3).",
     "DEFINIDO", f"{R14}; respuesta del 13-oct (R3)"),
    ("aplicar_vida_util_cliente", True, "bool", "Almacén",
     "La vida útil de la lista de clientes es la vida útil RESTANTE mínima al despacho (meses calendario; admite excepciones "
     "como '6 MESES HARINAS'): la reserva excluye lotes que no la cumplen.", "DEFINIDO",
     f"{R14}; respuesta del 13-oct (R1)"),
    ("almacen_transito_produccion", "ALM-003", "str", "Producción",
     "Almacén virtual de tránsito donde Producción deja el producto terminado hasta la validación de Almacén.",
     "DEFINIDO", f"{R12} Q5"),
    ("uso_almacen_por_tipo", {"PT": "PT", "GR": "MP_INSUMOS", "MP": "MP_INSUMOS", "INSUMO": "MP_INSUMOS"}, "dict", "Almacén",
     "Almacén principal según tipo de artículo (TIPO de la tabla DATA: PT/GR/MP; insumos EN-/SU- = INSUMO).",
     "DEFINIDO", f"{IF} §6.2 (1560 = PT; 1524 = materia prima, granel e insumos)"),
    ("politica_lotes", "FEFO", "str", "Almacén",
     "Orden de consumo de lotes al reservar (FEFO = primero en vencer, primero en salir).", "PROPUESTO", f"{IF} §22 (respetar lote y vencimiento)"),
    ("dias_vencimiento_proximo", None, "int", "Almacén", "Días previos al vencimiento para alertar.", "PENDIENTE", "No definido"),
    ("estado_lote_nuevo_carga", "PENDIENTE_REVISION", "str", "Almacén",
     "Estado de los lotes nuevos que trae una carga SAP posterior a la base inicial: quedan pendientes de revisión de "
     "Calidad (no se reservan hasta liberarse).", "DEFINIDO", f"{IF} §6.1; {R13} Q6"),
    ("carga_autorizada_verifica", True, "bool", "Almacén",
     "Una carga revisada y autorizada marca los lotes como verificados (hasta que un conteo registre diferencias).",
     "PROPUESTO", f"{IF} §6.3-6.4"),
    ("reevaluar_tras_carga", True, "bool", "Almacén",
     "Reevaluar automáticamente OV con faltantes (por prioridad) al ingresar stock.", "PROPUESTO", f"{IF} §1, §6.3"),
    ("bloquear_salida_con_discrepancia", True, "bool", "Distribución",
     "Una discrepancia carga vs guía bloquea la salida; el Jefe o el Coordinador de Logística puede aprobar la salida "
     "mientras se resuelve la guía.", "DEFINIDO", f"{IF} §12.2; {R12} Q8"),
    ("margen_por_proveedor", {}, "dict", "Reposición",
     "Días de margen adicional por proveedor habitual del artículo ({proveedor: días}); prevalece sobre el margen global.",
     "DEFINIDO", f"{IF} §16; {R14}: configurable en el panel"),
    ("excepciones_bom", {}, "dict", "Producción",
     "Excepciones a la proporcionalidad lineal: {producto: {componente: cantidad fija por orden}}; esa cantidad no se "
     "escala con el tamaño de la orden.", "DEFINIDO", f"{IF} §20; {R14}: configurable en el panel"),
    ("conversiones_calidad_permitidas", [], "list", "Calidad",
     "Conversiones de calidad permitidas en reempaque, como 'EXTRA>SUPERIOR'. Vacío = todas se proponen para evaluación de Calidad.",
     "DEFINIDO", f"{IF} §9.2; {R14}: configurable en el panel"),
    ("clasificacion_abc_pct", {"A": 80, "B": 95}, "dict", "Reposición",
     "Clasificación ABC por consumo acumulado del período de análisis: A hasta el % indicado, B hasta su %, C el resto.",
     "PROPUESTO", f"Excel de rotación (A/B/C); {R14}: configurable en el panel"),
    ("orden_asignacion_flota", ["PROPIO", "TERCERO", "EXTERNO"], "list", "Distribución",
     "Orden en que la propuesta de rutas asigna unidades (propias, de terceros, transporte externo).",
     "DEFINIDO", f"{IF} §12.1; {R14}: configurable en el panel"),
    ("vehiculos_por_zona", {}, "dict", "Distribución",
     "Restricción opcional de unidades por zona: {zona o distrito: [placas]}. Vacío = cualquier unidad.",
     "DEFINIDO", f"{IF} §12.1; {R14}: configurable en el panel"),
    ("horas_max_sin_carga", {"STOCK": 12, "OV": 12, "LIQUIDACION": 12, "SALIDAS": 24}, "dict", "Sistemas",
     "Horas máximas desde la última carga autorizada de cada tipo antes de alertar (2 cortes al día = 12 h).",
     "DEFINIDO", f"{R14}: diario, 2 cortes al día como mínimo"),
    ("responsable_carga", {"STOCK": ["COORD_ALMACEN", "COORD_ALMACEN_MP"], "OV": ["ASIST_VENTAS"],
                           "LIQUIDACION": ["ASIST_PRODUCCION"], "SALIDAS": ["COORD_ALMACEN"]}, "dict", "Sistemas",
     "Área (roles) que genera y sube cada exportación de SAP; recibe la alerta de carga desactualizada.",
     "PROPUESTO", f"{R14}: 'cada área'"),
    ("correo_habilitado", False, "bool", "Sistemas",
     "Enviar alertas por correo. Hoy no hay servidor de correo: las alertas quedan en el sistema.", "DEFINIDO", f"{R14}"),
    ("retencion_datos_personales_dias", None, "int", "Sistemas",
     "Días que se conservan fotos de entrega y datos personales de conductores antes de depurarlos. Vacío = no se depura. "
     "Debe fijarse según lo que permita la Ley 29733 y las normas aplicables (validación legal).", "PENDIENTE", f"{R14}"),
    ("tolerancia_discrepancia_guia", 0, "float", "Distribución",
     "Diferencia (unidades) entre guía y carga que se tolera sin considerarla discrepancia.", "PENDIENTE", f"{R12} Q8 (tolerancia no indicada)"),
    ("zonas_distrito", {}, "dict", "Distribución",
     "Agrupación de distritos en zonas de reparto (si está vacío se agrupa por distrito).", "PENDIENTE", f"{IF} §12.1"),
    ("capacidad_externo_kg", [2000, 25000], "list", "Distribución",
     "Rango de capacidad de transportes externos (kg).", "ACTUAL", "Imagen tabla de transportes (2 TN a 25 TN)"),
    ("otif_definicion", "SALIDA", "str", "Indicadores",
     "OTIF = pedido que sale del almacén completo y a tiempo (la variante ENTREGA queda como referencia).", "DEFINIDO", f"{IF} §17; {R12} Q2"),
    ("etapa_por_incidencia", {"SALIDA_INCOMPLETA": "Abastecimiento (stock, producción, compras)",
                              "SALIDA_TARDIA": "Preparación y despacho", "RECHAZO_CALIDAD": "Calidad", "PARTICULARIDAD_DESCARGA": "Almacén (preparación/carga)",
                              "INCIDENCIA_CARGA": "Almacén (preparación/carga)", "INFESTACION_INTERNA": "Calidad",
                              "INFESTACION_EXTERNA": "Calidad", "FUERA_CARACTERISTICAS": "Calidad", "PRODUCTO_ROTO": "Distribución",
                              "LLEGADA_TARDE": "Distribución", "RETRASO": "Distribución", "VEHICULO_ESPERANDO": "Distribución",
                              "CAMBIO_RUTA": "Distribución", "CONDUCTOR_NO_DISPONIBLE": "Distribución",
                              "CLIENTE_AUSENTE": "Cliente / Comercial", "CLIENTE_NO_RETIRA": "Cliente / Comercial",
                              "CANCELACION": "Cliente / Comercial", "ENTREGA_PARCIAL": "Distribución",
                              "DEVOLUCION": "Sin clasificar", "RECHAZO_OTRO": "Sin clasificar"},
     "dict", "Indicadores",
     "Etapa del proceso a la que se atribuye cada motivo de rechazo/incidencia en el análisis del fill rate.",
     "PROPUESTO", f"{R12} Q2 ('identificar en qué parte del proceso están los mayores errores')"),
    ("ambito_gerencia_operaciones", ["Almacén", "Distribución", "Logística", "Producción", "Calidad", "Compras",
                                    "Importaciones", "Seguridad", "Comercial", "Gerencia"], "list", "Alertas",
     "Áreas cuyas alertas ve Gerencia de Operaciones.", "PENDIENTE", f"{IF} §14 ('alertas de su ámbito')"),
    ("acceso_completo_omite_aprobaciones", False, "bool", "Seguridad",
     "Gerencia General tiene acceso completo y puede aprobar en nombre de otros roles (queda auditado como tal); Sistemas tiene "
     "acceso completo pero no aprueba. Ningún paso se omite.", "DEFINIDO", f"{IF} §15; {Q4}"),
    ("parcial_aprobadores", ["GERENCIA_OPERACIONES", "JEFE_LOGISTICA"], "list", "Logística",
     "Roles que pueden aprobar el despacho parcial. Gerencia General puede aprobar en nombre de ellos.", "DEFINIDO", Q3),
    ("parcial_modo", "CUALQUIERA", "str", "Logística",
     "CUALQUIERA: basta la aprobación de uno de los roles; TODOS: deben aprobar todos.", "DEFINIDO",
     f"{Q3}: 'Gerencia de Operaciones o Jefe de Logística' (12-oct)"),
    ("presolicitudes_automaticas", True, "bool", "Almacén",
     "Ante un faltante el sistema genera la pre-solicitud de la primera opción viable (las personas aprueban).",
     "DEFINIDO", f"{TOBE}; {R12} Q15"),
    ("orden_presolicitudes", ["PRODUCCION", "REEMPAQUE", "TRASLADO", "COMPRA"], "list", "Almacén",
     "Orden de preferencia de la pre-solicitud automática; si la primera opción no cubre todo, el saldo pasa a la siguiente.",
     "DEFINIDO", f"{R12} Q15: producir, reempaque, traslado desde almacén externo, compra"),
    ("alcance_almacen_por_rol", {"COORD_ALMACEN": ["ALM-001", "ALM-003"] + VIRTUALES, "COORD_ALMACEN_MP": ["EXT-002"],
                                 "COORD_LOGISTICA": VIRTUALES, "JEFE_LOGISTICA": VIRTUALES}, "dict", "Almacén",
     "Almacenes que maneja cada rol: solo actúa sobre los suyos (los no asignados, como los alternativos, los opera "
     "cualquier coordinador). 'PRO-*' abarca todos los códigos que empiezan con PRO-. Las alertas de almacén se dirigen "
     "al coordinador del almacén involucrado.", "DEFINIDO",
     f"{R12} Q17 (1560 y 1524); {R13} Q5 (virtuales: Coord. 1560, Coord. y Jefe de Logística) y Q17 (alternativos: cualquiera)"),
    ("vistos_buenos_salida", ["SEGURIDAD", "AUX_DESPACHO", "LIDER_ALMACEN"], "list", "Distribución",
     "Roles cuya autorización y visto bueno requiere la salida del camión (el Líder Operativo da el último).",
     "DEFINIDO", f"{R13} Q16"),
    ("canal_precio_por_grupo", {"MAYORISTA": "MAYORISTA", "INSTITUCIONAL": "INSTITUCIONAL", "CUENTAS CLAVE": "CUENTAS CLAVE",
                                "MARCA BLANCA": "MARCA BLANCA", "CATERING": "CATERING",
                                "HOTELES - RESTAURANTES": "HOTELES - RESTAURANTES", "AUTOSERVICIOS": "AUTOSERVICIOS",
                                "ENTRETENIMIENTO": "ENTRETENIMIENTO", "E-COMMERCE": "E-COMMERCE",
                                "DISTRIBUIDORES": "DISTRIBUIDORES"}, "dict", "Comercial",
     "Columna de la lista de precios mínimos que corresponde a cada grupo de cliente. OFICINA, CANASTERIA y MINORISTA (presentes en "
     "las OV) no tienen columna en la lista: sus OV quedan sin precio hasta definirlo.", "PROPUESTO",
     f"{R13} Q11; columnas de PRICE_LIST_OCT-NOV_26 y 'Grupo de cliente' de la exportación OVS"),
    ("margen_alerta_precio_pct", 0, "float", "Comercial",
     "La alerta salta si el precio de venta está por debajo del mínimo de lista o a menos de este % por encima "
     "('en el límite'). Con 0 se alerta solo si es igual o menor al mínimo.", "PENDIENTE",
     f"{R13} Q11 ('alertar si está en el límite o por debajo')"),
    ("lista_granel_canales", [CANAL_GRANEL], "list", "Comercial",
     "Canales de precio que usan la lista 'Mayorista granel' (mínimo por kg y por saco). La lista se elige por el canal del "
     "cliente: granel (sin proceso de empaque) o presentaciones (lista por canal).", "DEFINIDO",
     f"{R14}: 'son por el tipo de canal'"),
    ("aviso_vencimiento_lista_dias", 7, "int", "Comercial",
     "Días antes del vencimiento de una lista de precios en que se avisa al Jefe Comercial (no se bloquea su uso).",
     "PROPUESTO", f"{R14}"),
    ("retener_ov_bajo_minimo", True, "bool", "Comercial",
     "La OV con precio en el límite o bajo el mínimo queda detenida (no se prepara ni despacha) hasta su confirmación.",
     "DEFINIDO", f"{R14}"),
    ("programar_ruta_automatica", True, "bool", "Distribución",
     "Al quedar una OV completa (o con parcial aprobado) el sistema la programa automáticamente en la mejor ruta propuesta.",
     "DEFINIDO", "Diagrama de procesos COPROD-ONE: 'Programar automáticamente la mejor ruta para el despacho'"),
    ("certificado_previo_al_picking", True, "bool", "Calidad",
     "Pre-elaborar los certificados al quedar la OV completa (antes del picking) para validación de Calidad.",
     "DEFINIDO", "Diagrama de procesos COPROD-ONE: 'Informar a Calidad para la validación del certificado pre-elaborado'"),
    ("documentos_salida", ["GUIA", "FACTURA", "CERTIFICADO"], "list", "Distribución",
     "Documentos que Seguridad verifica por pedido antes de autorizar la salida (certificado = aprobado por Calidad).",
     "DEFINIDO", "Diagrama de procesos COPROD-ONE: Seguridad 'Documentos completos?' / reportar faltantes a distribución, facturación y calidad"),
    ("empresa_razon_social", "CORPORACION PRODUCTIVA S.A.C.", "str", "Certificados", "Procesado por (certificados).", "DEFINIDO",
     "Certificados N°CP2026-PT3756 / MP276 / CA0764"),
    ("empresa_ruc", "20517540341", "str", "Certificados", "RUC del emisor (certificados).", "DEFINIDO", "Certificados N°CP2026-*"),
    ("autorizacion_sanitaria", "Nº000502- MIDAGRI-SENASA-LIMA CALLAO", "str", "Certificados",
     "Autorización sanitaria (los modelos muestran 'MIDAGRI' y 'MINAGRI'; confirmar).", "PENDIENTE", "Certificados N°CP2026-MP276 y PT3756"),
    ("conceptos_costo_importacion", ["Flete internacional", "Seguro", "Derechos y aranceles", "Agente de aduanas",
                                     "Almacenaje / depósito temporal", "Transporte local", "Otros"], "list", "Compras",
     "Conceptos sugeridos para los costos asociados a la importación (lista editable).", "PROPUESTO",
     "Observaciones al demo v0.5 (13-oct): en importaciones tener en cuenta el contenedor, el lugar de almacenamiento y los costos asociados"),
    ("pct_externo_alerta", 30, "float", "Distribución",
     "En el informe de distribución se recomienda revisar la flota cuando el % de rutas con transporte externo supera este valor.",
     "PROPUESTO", "Observaciones al demo v0.5 (13-oct): cuántos fueron con transporte propio y cuántos con externo"),
    ("tiempo_por_parada_min", 30, "int", "Distribución", "Minutos de descarga por parada para el tiempo estimado de la ruta.",
     "PROPUESTO", "Observaciones al demo v0.5 (13-oct): tiempo estimado de la ruta"),
    ("tiempo_traslado_base_min", 45, "int", "Distribución",
     "Minutos por tramo cuando no hay servicio de mapas configurado (estimación sin tráfico).", "PROPUESTO",
     "Observaciones al demo v0.5 (13-oct): tiempo estimado de la ruta"),
    ("umbral_trafico_pct", 25, "float", "Distribución", "% de tiempo adicional por tráfico a partir del cual se alerta.",
     "PROPUESTO", "Observaciones al demo v0.5 (13-oct): alertas de tráfico"),
    ("dias_aviso_fumigacion", [7, 3, 0], "list", "Calidad",
     "Días de anticipación de los avisos de fumigación a Calidad.", "DEFINIDO", "Observaciones al demo v0.5 (13-oct)"),
    ("prefijos_desmedro_bom", ["ME-"], "list", "Producción",
     "Prefijos de los artículos de desmedro (= merma) en la lista de materiales; no se tratan como material a consumir.",
     "DEFINIDO", "LISTA DE MATERIALES 2026 (componentes 'X - DESMEDRO'); observaciones al demo v0.5 (13-oct)"),
    ("tolerancia_merma_pp", 1, "float", "Producción",
     "Diferencia (puntos porcentuales) entre merma ejecutada y proyectada a partir de la cual se marca la desviación.",
     "PROPUESTO", "Observaciones al demo v0.5 (13-oct): contrastar merma proyectada vs ejecutada"),
    ("margen_minimo_reporte_pct", 10, "float", "Comercial",
     "En el informe comercial se recomienda revisar los productos con margen menor a este %.", "PROPUESTO",
     "Observaciones al demo v0.5 (13-oct): margen promedio y por producto"),
    ("margen_alerta_costo_mercado_pct", 0, "float", "Comercial",
     "Alerta cuando el precio de mercado supera al costo por kg en menos de este % (0 = solo si el costo supera al mercado).",
     "PROPUESTO", "Respuestas del 13-oct (R4)"),
    ("tendencia_mercado_umbral_pct", 5, "float", "Comercial",
     "Variación del precio de mercado (último vs promedio de 90 días) a partir de la cual se considera alza o baja.",
     "PROPUESTO", "Respuestas del 13-oct (R4: tendencias)"),
    ("antiguedad_max_precio_mercado_dias", 45, "int", "Comercial",
     "Antigüedad máxima del precio de mercado antes de recomendar su actualización.", "PROPUESTO", "Respuestas del 13-oct (R5)"),
    ("retener_ov_bajo_costo", True, "bool", "Comercial",
     "La OV con precio menor al costo queda detenida hasta la confirmación del Coordinador o Jefe Comercial.", "DEFINIDO",
     "Respuestas del 13-oct (R4): ninguna venta por debajo del costo"),
    ("series_certificado", {"PT": "PT", "MQ": "PT", "AB": "PT", "MP": "MP", "GR": "MP"}, "dict", "Certificados",
     "Tipo/serie de certificado por tipo de artículo (CP{año}-{serie}{correlativo}). Tipos con formato propio: PT, MP y CA.",
     "DEFINIDO", "Certificados N°CP2026-PT3756 / MP276 / CA0764; respuesta 13-oct (diversos tipos de certificado)"),
    ("tipo_certificado_por_marca", {"COSECHA ANDINA": "CA"}, "dict", "Certificados",
     "Marca que usa un tipo de certificado propio (prevalece sobre el tipo de artículo). Calidad puede regenerar un borrador con otro tipo.",
     "PROPUESTO", "Certificado N°CP2026-CA0764 (marca COSECHA ANDINA); criterio de la serie CA no documentado"),
    ("humedad_maxima_por_tipo", {"PT": 15, "CA": 21}, "dict", "Certificados",
     "Especificación de humedad máxima (%) que se propone en el certificado según su tipo; editable en el borrador.",
     "PROPUESTO", "Certificados PT3756 (MAX. 15%) y CA0764 (MÁX. 21 %); MP276 no muestra especificación"),
    ("referencias_ntp", {"FRIJOL": "NTP-205.015.2015 LEGUMINOSAS DE GRANO SECO. Frijol",
                         "LENTEJA": "NTP-205.022.2014 LEGUMINOSA. Lenteja"}, "dict", "Certificados",
     "Norma técnica de referencia por producto base (se busca la palabra en el producto declarado). Productos sin norma: Calidad la completa.",
     "PROPUESTO", "Certificados PT3756 (frijol) y MP276 (lenteja)"),
    ("certificado_firmante", {"nombre": "Ing. Liesbet Cordova Garcia", "cargo": "Jefe de Aseguramiento de Calidad"}, "dict",
     "Certificados", "Firmante del certificado. La imagen de la firma no se guarda en el repositorio: la carga Sistemas en el servidor "
     "y se imprime solo en certificados aprobados.", "DEFINIDO", "Certificados N°CP2026-PT3756 / MP276 / CA0764"),
    ("documentos_pie", ["Av. Aviación Nº1560 - La Victoria - Lima / Telf: 303-6446 / Cel.: 998 256 589 / 984 173 183",
                        "E-mail: ventas1@corporacionproductiva.com / ventas2@corporacionproductiva.com",
                        "ventas3@corporacionproductiva.com / gvila@corporacionproductiva.com",
                        "www.corporacionproductiva.com / www.cosechaandina.com"], "list", "Documentos",
     "Pie de página de los documentos impresos (certificado).", "DEFINIDO", "Certificados N°CP2026-* (membrete)"),
    ("empresa_razon_social_completa", "CORPORACION PRODUCTIVA SOCIEDAD ANONIMA CERRADA", "str", "Documentos",
     "Razón social en la cabecera de la OV.", "DEFINIDO", "Formato de OV N° 1635389 (foto, 13-oct)"),
    ("empresa_direccion", ["AV. AVIACION NRO. 1560 (FRENTE AL GRIFO PRIMAX)", "LIMA - LIMA - LA VICTORIA"], "list", "Documentos",
     "Dirección del emisor en la cabecera de la OV y guía.", "DEFINIDO", "Formato de OV N° 1635389 (foto, 13-oct)"),
    ("ov_cuentas_bancarias", [
        {"banco": "BBVA", "soles": "0011-0163-37-0100043731 CÓDIGO DE RECAUDO (6721)", "dolares": "0011-0163-0100043758"},
        {"banco": "BCP", "soles": "194-2211886-0-81", "dolares": "194-2190284-1-89"},
        {"banco": "Banco de la Nación", "soles": "00-098-054618 (CUENTA DE DETRACCIONES)", "dolares": "-"},
        {"banco": "Scotiabank", "soles": "000-2171108", "dolares": "000-5130001"},
        {"banco": "BanBif", "soles": "7000729570", "dolares": "7000729589"},
        {"banco": "Interbank", "soles": "200-3004622764", "dolares": "200-3004622771"}], "list", "Documentos",
     "Cuentas bancarias impresas en la OV.", "DEFINIDO", "Formato de OV N° 1635389 (foto, 13-oct)"),
    ("ov_instrucciones_pago", ["Instrucciones de pago para clientes de provincia:",
                               "Realizar el depósito a nuestra cuenta con el código de recaudo \"6721\".",
                               "Si paga por aplicativo, seleccionar \"Pago de servicios\" y colocar como nombre de empresa Corporación Productiva.",
                               "Detracciones: Realizar el abono únicamente a nuestra cuenta del Banco de la Nación."], "list", "Documentos",
     "Instrucciones de pago impresas en la OV.", "DEFINIDO", "Formato de OV N° 1635389 (foto, 13-oct)"),
    ("ov_servicios_asistencia", [{"telefono": "+51 959 393 886", "area": "Asistencia Logistica"},
                                 {"telefono": "+51 971 442 700", "area": "Asistencia Calidad"}], "list", "Documentos",
     "Servicios de asistencia impresos en la OV.", "DEFINIDO", "Formato de OV N° 1635389 (foto, 13-oct)"),
    ("muestreo_tiempo_min_por_lote", 30, "int", "Calidad", "Tiempo orientativo de muestreo por lote en reempaque.", "ACTUAL",
     f"{IF} §9.2 (orientativo)"),
]

# Plazos de reposición (IF §7) – días naturales.
LEAD_TIMES = [
    ("Bobinas", 25, 30, None, None, "Bobinas"),
    ("Bobinas", 30, 40, 11, 12, "Bobinas en campaña de canastería (noviembre–diciembre)"),
    ("GR y MP", 5, 7, None, None, "Granel y materia prima"),
    ("Harinas", 7, 10, None, None, "Harinas"),
    ("Film", 2, 5, None, None, "Film"),
    ("Sacos sin estampado", 1, 2, None, None, "Sacos sin estampado"),
    ("Sacos con estampado", 5, 7, None, None, "Sacos con estampado"),
    ("Ribbons", 2, 5, None, None, "Ribbons"),
    ("Etiquetas adhesivas", 2, 5, None, None, "Etiquetas adhesivas"),
]

# Almacenes (IF §6.2; correspondencia código SAP ↔ nombre operativo: hoja 'stock almacenes' de Rotación de inventario)
WAREHOUSES = [
    # code, nombre, uso, prioridad, reservable, fuente, observacion
    ("ALM-001", "1560", "PT", 1, True, f"{IF} §6.2; Rotacion de inventario (1560 = ALM-001)", "Prioridad para stock actual de producto terminado."),
    ("EXT-002", "1524", "MP_INSUMOS", 1, True, f"{IF} §6.2; Rotacion de inventario (1524 = EXT-002)", "Materia prima, granel e insumos."),
    ("EXT-001", "767", "ALTERNATIVO", 2, True, f"{IF} §6.2 (Ext-001 = almacén 767)", "Alternativo: Logística decide; no hay traslado automático."),
    ("EXT-005", "Trujillo 1", "ALTERNATIVO", 3, True, f"{IF} §6.2", "En el Excel de rotación figura como 'Atsac 1' (nombre a confirmar)."),
    ("EXT-010", "Trujillo 2", "ALTERNATIVO", 4, True, f"{IF} §6.2", "En el Excel de rotación figura como 'Atsac 2' (nombre a confirmar)."),
    ("EXT-014", "Isabelita", "ALTERNATIVO", 5, True, f"{IF} §6.2", ""),
    ("ALM-003", "Tránsito de Producción", "TRANSITO_PRODUCCION", 90, False, f"{R12} Q5",
     "Almacén virtual: producto terminado por Producción hasta que Almacén lo valida y pasa a ALM-001."),
    ("ALM-010", "No se utiliza", "NO_UTILIZADO", 99, False, f"{R12} Q5", "Almacén virtual no utilizado."),
] + [(c, f"Virtual {c}", "VIRTUAL", 95, False, f"{R13} Q5", "Almacén virtual (no reservable); lo manejan Coord. 1560, Coord. y Jefe de Logística.")
     for c in VIRTUALES if not c.endswith("*")] + [
]

# Líneas de producción (PDF de formatos de producción). Capacidad no documentada.
PRODUCTION_LINES = [
    ("R1", "Envasado automático R1", "ENVASADOS R1 R2 Y R3.pdf"),
    ("R2", "Envasado automático R2", "ENVASADOS R1 R2 Y R3.pdf"),
    ("R3", "Envasado automático R3", "ENVASADOS R1 R2 Y R3.pdf"),
    ("TRUER", "Línea Truer", "LINEA TRUER.pdf"),
    ("CIMBRIA", "Línea Cimbria", "Linea cimbria.pdf"),
    ("SEL_MANUAL", "Selección manual", "SEL-MANUAL.pdf"),
    ("ENV_MANUAL", "Envasado manual", "Tabla de capacidad por línea (14-oct-2026)"),
]

# Límites críticos de humedad PCC1 (REG-HACCP-CAL-002)
PCC1_HUMEDAD = [
    ("QUINUA_CANIHUA_MOTE", "Quinua y cañihua, maíz mote", 12.5),
    ("PAPA_SECA_CEBADA_TOSTADA", "Papa seca y cebada tostada", 10.0),
    ("TRIGO_CEBADA_CRUDA", "Trigo, cebada cruda", 14.5),
    ("MAIZ_AMILACEO", "Maíz amiláceo", 14.0),
    ("OTROS", "Otros productos", 15.0),
]

# Especificación de defectos 'Calidad superior' (REG-CAL-005, ref. NTP 205.015:2015). Máximos en %.
SPEC_CALIDAD_SUPERIOR = {
    "humedad": 15.0, "grano_enfermo": 0.0, "grano_picado": 2.0, "grano_partido": 2.0, "grano_arrugado": 2.0,
    "materias_extranas": 0.08, "variedad_contrastante": 2.0, "total_defectos": 8.08,
}

# Criterios de peso (REG-CAL-003). nominal_kg -> (objetivo, min, max). 50 kg queda pendiente (texto inconsistente en el formato).
CRITERIOS_PESO = {
    0.25: (0.255, 0.250, 0.260),
    0.5: (0.505, 0.500, 0.510),
    5.0: (5.025, 5.000, 5.050),
}
CRITERIO_PESO_PENDIENTE = "50 kg: el formato indica '50.08 kg < 5.0 Kg >5.010 kg' (inconsistente); requiere confirmación de Calidad."

# Fases de importación para demostración (las fases reales están pendientes – IF §20)
DEMO_IMPORT_PHASES = [
    (1, "Embarque en origen", 0, 2, "IMPORTACIONES"),
    (2, "Arribo a puerto", 20, 3, "IMPORTACIONES"),
    (3, "Nacionalización / despacho aduanero", 25, 2, "IMPORTACIONES"),
    (4, "Llegada a almacén", 28, 2, "IMPORTACIONES"),
]

REPACK_TYPES = [
    ("ACTUALIZACION_FECHA", "Actualización de fecha de producción",
     "No hay materia prima, pero sí producto apto del mes anterior. Calidad muestrea bolsa y aprueba/desaprueba. Aprox. 1 h; muestreo ~30 min por lote."),
    ("CAMBIO_PRESENTACION", "Cambio de presentación",
     "No hay materia prima; se conserva la información y se cambia la presentación (p.ej. 10 kg a 5 kg). Tiempo similar; medir."),
    ("CONVERSION_CALIDAD", "Conversión de calidad",
     "No hay material de la misma calidad; se revisan conversión, SKU, lote, fecha de producción y disposición. Criterios pendientes de Calidad."),
]
