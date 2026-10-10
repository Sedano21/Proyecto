"""Catálogos iniciales derivados de la documentación fuente.

Convenciones de origen (IF = Informe Funcional, v1.0, 9-oct-2026):
- DEFINIDO: regla expresamente indicada en la documentación.
- PROPUESTO: organización derivada (p.ej. del alcance por área, IF §3) que requiere validación.
- PENDIENTE: valor/decisión que la documentación declara pendiente; se deja configurable y vacío o inactivo.
- AS-IS: valor observado en archivos operativos actuales (Excel/PDF/diagrama); no es regla aprobada.
- DEMO: valor colocado solo para demostrar el prototipo; debe reemplazarse.
"""

IF = "Informe Funcional"

# ---------------------------------------------------------------------------
# Roles (IF §15)
# ---------------------------------------------------------------------------
ROLES = [
    # code, nombre, area, fuente, observacion
    ("GERENCIA_GENERAL", "Gerencia General", "Gerencia", f"{IF} §3, §14, §15", "Acceso a todas las áreas; 'acceso completo' pendiente de precisar (IF §15)."),
    ("GERENCIA_OPERACIONES", "Gerencia de Operaciones", "Gerencia", f"{IF} §3, §15", "Vista y autorizaciones de su ámbito."),
    ("SISTEMAS", "Sistemas", "Sistemas", f"{IF} §3, §15, §16", "Se indicó acceso completo; administración y configuración."),
    ("GERENTE_COMERCIAL", "Gerente Comercial", "Comercial", f"{IF} §15", ""),
    ("JEFE_VENTAS", "Jefe de Ventas", "Comercial", f"{IF} §5, §15", ""),
    ("COORD_VENTAS", "Coordinador de Ventas", "Comercial", f"{IF} §5, §15", ""),
    ("ASIST_VENTAS", "Asistente de Ventas", "Comercial", f"{IF} §5, §15", "Modifica OV solo con autorización."),
    ("EJECUTIVO_VENTAS", "Ejecutivo de Ventas (vendedor por canal)", "Comercial", f"{IF} §5, §15", "Vendedor responsable de la OV."),
    ("COORD_ALMACEN", "Coordinación de Almacén", "Almacén", f"{IF} §6, §15", ""),
    ("SUPERV_ALMACEN", "Supervisión de Almacén (por almacén)", "Almacén", f"{IF} §15", ""),
    ("LIDER_ALMACEN", "Líder Operativo de Almacén", "Almacén", f"{IF} §15; diagrama AS-IS L5", ""),
    ("AUX_ALMACEN", "Auxiliar / Asistente de Almacén", "Almacén", f"{IF} §6.2, §15", ""),
    ("MONTACARGUISTA", "Montacarguista", "Almacén", f"{IF} §8.3, §15", ""),
    ("COORD_DISTRIBUCION", "Coordinador de Distribución", "Distribución", f"{IF} §12, §15", ""),
    ("ASIST_DISTRIBUCION", "Asistente de Distribución", "Distribución", f"{IF} §15", ""),
    ("CONDUCTOR", "Conductor", "Distribución", f"{IF} §15", ""),
    ("AUX_DESPACHO", "Auxiliar de Despacho", "Distribución", f"{IF} §12.3, §15", ""),
    ("JEFE_LOGISTICA", "Jefatura de Logística", "Logística", f"{IF} §6.2, §13, §15", ""),
    ("COORD_LOGISTICA", "Coordinación de Logística", "Logística", f"{IF} §15", ""),
    ("JEFE_PRODUCCION", "Jefatura de Producción", "Producción", f"{IF} §8, §15", ""),
    ("COORD_PRODUCCION", "Coordinación de Producción (por validar)", "Producción", f"{IF} §15", "La existencia del rol está 'por validar' (IF §15)."),
    ("ASIST_PRODUCCION", "Asistente de Producción", "Producción", f"{IF} §15", ""),
    ("JEFE_CALIDAD", "Jefatura de Calidad", "Calidad", f"{IF} §9, §15", ""),
    ("SUPERV_CALIDAD", "Supervisor de Calidad", "Calidad", f"{IF} §9.3, §15", ""),
    ("ASIST_CALIDAD", "Asistente de Calidad", "Calidad", f"{IF} §9.3, §15", ""),
    ("COMPRAS", "Coordinador de Compras", "Compras", f"{IF} §10, §15", ""),
    ("IMPORTACIONES", "Importaciones", "Importaciones", f"{IF} §11, §15", ""),
    ("SEGURIDAD", "Seguridad", "Seguridad", f"{IF} §12.2, §13, §15", ""),
]

# ---------------------------------------------------------------------------
# Permisos (separación consulta/edición/aprobación/administración, IF §19)
# ---------------------------------------------------------------------------
PERMISSIONS = [
    ("dashboard.ver", "Ver tablero de indicadores", "Gerencial", "consulta"),
    ("ov.ver", "Consultar órdenes de venta", "Comercial", "consulta"),
    ("ov.crear", "Registrar OV", "Comercial", "edicion"),
    ("ov.modificar", "Modificar OV directamente", "Comercial", "edicion"),
    ("ov.solicitar_modificacion", "Solicitar modificación de OV (requiere autorización)", "Comercial", "edicion"),
    ("ov.autorizar_modificacion", "Autorizar modificación de OV solicitada por Asistente", "Comercial", "aprobacion"),
    ("ov.cancelar", "Cancelar OV", "Comercial", "aprobacion"),
    ("ov.renegociar", "Registrar renegociación de fecha / cambio de producto", "Comercial", "edicion"),
    ("ov.aprobar_parcial", "Decidir despacho parcial", "Logística", "aprobacion"),
    ("ov.decidir_alternativa", "Decidir uso de stock de otros almacenes", "Logística", "aprobacion"),
    ("ov.importar", "Importar OV desde exportación SAP", "Comercial", "edicion"),
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
    ("reempaque.solicitar", "Solicitar reempaque", "Almacén", "edicion"),
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
    ("distribucion.confirmar_salida", "Confirmar salida de despacho", "Distribución", "aprobacion"),
    ("distribucion.seguridad", "Control de Seguridad: ingreso, inspección y carga vs guía", "Seguridad", "edicion"),
    ("distribucion.entrega", "Registrar avance y entrega con evidencia", "Distribución", "edicion"),
    ("distribucion.incidencia", "Registrar incidencias", "Distribución", "edicion"),
    ("alertas.ver", "Ver alertas propias/del rol", "Alertas", "consulta"),
    ("alertas.gestionar", "Asignar, atender, comentar y cerrar alertas", "Alertas", "edicion"),
    ("alertas.ver_todas", "Ver alertas de todas las áreas", "Alertas", "consulta"),
    ("alertas.configurar", "Configurar destinatarios/canales/urgencia de alertas", "Alertas", "administracion"),
    ("config.ver", "Consultar configuración", "Configuración", "consulta"),
    ("config.editar", "Editar configuración y catálogos", "Configuración", "administracion"),
    ("usuarios.administrar", "Administrar usuarios y matriz de permisos", "Configuración", "administracion"),
    ("auditoria.ver", "Consultar bitácora de auditoría", "Configuración", "consulta"),
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
    "GERENCIA_GENERAL": _d(ALL_PERMS, f"{IF} §15 'acceso a todas las áreas' / 'acceso completo'"),
    "SISTEMAS": _d(ALL_PERMS, f"{IF} §15 'Sistemas: acceso completo'; §16 administra configuración"),
    "GERENCIA_OPERACIONES": _p(_VIEW_OPS + ["config.ver"]) + _d(
        ["ov.aprobar_parcial", "ov.renegociar"], f"{IF} §4.5, §5 (participa en renegociación y despacho parcial)") + _d(
        ["compras.autorizar_bajo_observacion"], f"{IF} §10.8") + _p(
        ["compras.aprobar_mayor_volumen"], f"{IF} §7 – participación de GO requiere validación"),
    "GERENTE_COMERCIAL": _p(["dashboard.ver", "ov.ver", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "export.datos"]),
    "JEFE_VENTAS": _p(["dashboard.ver", "ov.ver", "ov.crear", "ov.modificar", "ov.importar", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "export.datos"]) + _d(
        ["ov.cancelar", "ov.autorizar_modificacion"], f"{IF} §5") + _d(
        ["ov.renegociar", "ov.aprobar_parcial"], f"{IF} §4.5, §5, §6.3 (Comercial participa)"),
    "COORD_VENTAS": _p(["dashboard.ver", "ov.ver", "ov.crear", "ov.modificar", "ov.importar", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "export.datos"]) + _d(
        ["ov.cancelar", "ov.autorizar_modificacion"], f"{IF} §5") + _d(
        ["ov.renegociar", "ov.aprobar_parcial"], f"{IF} §4.5, §5, §6.3 (Comercial participa)"),
    "ASIST_VENTAS": _d(["ov.crear"], "Diagrama AS-IS L5 (Asistente comercial ingresa la OV)") + _d(
        ["ov.solicitar_modificacion"], f"{IF} §5 (modifica con autorización)") + _p(["ov.ver", "stock.ver", "alertas.ver"]),
    "EJECUTIVO_VENTAS": _p(["ov.ver", "ov.crear", "ov.modificar", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar"]) + _d(
        ["ov.autorizar_modificacion"], f"{IF} §5 (vendedor responsable autoriza; solo sus OV)") + _d(
        ["ov.renegociar"], f"{IF} §5 (Comercial puede renegociar)"),
    "COORD_ALMACEN": _p(_VIEW_OPS + ["stock.cargar", "stock.autorizar_carga", "stock.cambiar_estado", "stock.conteo",
                                     "preparacion.registrar", "traslado.salida", "importaciones.recibir"]) + _d(
        ["traslado.recibir"], f"{IF} §6.2, §13") + _d(["reempaque.solicitar"], f"{IF} §9.1") + _d(
        ["produccion.solicitud"], f"{IF} §8.2 (Almacén revisa y envía)") + _d(
        ["compras.solicitar"], f"{IF} §7, §10.1") + _d(["compras.recibir", "produccion.recibir_pt"], f"{IF} §8.3, §10.6-10.7"),
    "SUPERV_ALMACEN": _p(["dashboard.ver", "ov.ver", "stock.ver", "traslados.ver", "reempaque.ver", "produccion.ver",
                          "compras.ver", "importaciones.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar",
                          "stock.cargar", "stock.cambiar_estado", "stock.conteo", "preparacion.registrar",
                          "traslado.salida", "traslado.recibir", "reempaque.solicitar", "produccion.solicitud",
                          "compras.solicitar", "compras.recibir", "produccion.recibir_pt", "importaciones.recibir", "export.datos"]),
    "LIDER_ALMACEN": _p(["ov.ver", "stock.ver", "alertas.ver", "alertas.gestionar", "stock.conteo", "traslados.ver"]) + _d(
        ["preparacion.registrar"], "Diagrama AS-IS L5 (Líder operativo designa y verifica picking)"),
    "AUX_ALMACEN": _p(["ov.ver", "stock.ver", "alertas.ver", "stock.conteo", "preparacion.registrar", "traslados.ver"]) + _d(
        ["traslado.recibir"], f"{IF} §6.2 (Coordinador de Almacén o asistente confirma recepción)"),
    "MONTACARGUISTA": _p(["stock.ver", "alertas.ver", "alertas.gestionar"], f"{IF} §8.3 (recibe alerta de liquidación) – propuesto"),
    "COORD_DISTRIBUCION": _p(["dashboard.ver", "ov.ver", "stock.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar",
                              "distribucion.programar", "distribucion.flota", "distribucion.entrega", "distribucion.incidencia", "export.datos"]) + _d(
        ["distribucion.confirmar_salida"], f"{IF} §4.11, §12.2"),
    "ASIST_DISTRIBUCION": _p(["ov.ver", "distribucion.ver", "alertas.ver", "alertas.gestionar", "distribucion.programar",
                              "distribucion.flota", "distribucion.entrega", "distribucion.incidencia"]),
    "CONDUCTOR": _p(["distribucion.ver", "alertas.ver", "distribucion.entrega", "distribucion.incidencia"]),
    "AUX_DESPACHO": _p(["distribucion.ver", "alertas.ver", "distribucion.entrega"]) + _d(
        ["distribucion.incidencia"], f"{IF} §12.3"),
    "JEFE_LOGISTICA": _p(_VIEW_OPS + ["traslado.solicitar"]) + _d(
        ["traslado.autorizar", "ov.decidir_alternativa"], f"{IF} §4.5, §6.2, §13") + _d(
        ["ov.aprobar_parcial"], f"{IF} §6.3"),
    "COORD_LOGISTICA": _p(_VIEW_OPS + ["traslado.solicitar"]) + _d(
        ["ov.decidir_alternativa"], f"{IF} §4.5, §6.2 (Logística decide)"),
    "JEFE_PRODUCCION": _p(["dashboard.ver", "ov.ver", "stock.ver", "produccion.ver", "reempaque.ver", "calidad.ver",
                           "alertas.ver", "alertas.gestionar", "produccion.bom_cargar", "produccion.programar",
                           "produccion.registrar", "produccion.liquidar", "export.datos"]) + _d(
        ["produccion.validar"], f"{IF} §8.2") + _d(["reempaque.ejecutar"], f"{IF} §9.1"),
    "COORD_PRODUCCION": _p(["ov.ver", "stock.ver", "produccion.ver", "reempaque.ver", "alertas.ver", "alertas.gestionar",
                            "produccion.programar", "produccion.registrar", "produccion.liquidar", "produccion.validar",
                            "reempaque.ejecutar"], f"{IF} §15 – rol por validar"),
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
        ["distribucion.seguridad"], f"{IF} §12.2, §13"),
}

# ---------------------------------------------------------------------------
# Tipos de alerta (IF §14 y secciones de proceso)
# ---------------------------------------------------------------------------
_ALM = ["COORD_ALMACEN"]
_LOG = ["JEFE_LOGISTICA", "COORD_LOGISTICA"]
_GO = ["GERENCIA_OPERACIONES"]
_COM = ["JEFE_VENTAS", "COORD_VENTAS"]
_DIST = ["COORD_DISTRIBUCION", "ASIST_DISTRIBUCION"]
_CAL = ["JEFE_CALIDAD", "SUPERV_CALIDAD"]
_PROD = ["JEFE_PRODUCCION", "COORD_PRODUCCION"]

ALERT_TYPES = [
    # code, nombre, area, grupo, prioridad, roles, origen, fuente, condicion, correo
    ("OV_FALTANTE", "Faltante de stock en OV", "Almacén", "Faltantes y cobertura", "ALTA", _ALM + _LOG + _GO, "DEFINIDO",
     f"{IF} §6.3", "Al evaluar una OV nueva o modificada con cobertura < 100 %.", True),
    ("OV_DECISION_PARCIAL", "Decisión de despacho parcial requerida", "Logística", "Faltantes y cobertura", "ALTA",
     ["JEFE_LOGISTICA"] + _GO + _COM, "DEFINIDO", f"{IF} §6.3", "OV con faltante y stock reservado parcial.", True),
    ("OV_PARCIAL_APROBADO", "Despacho parcial aprobado", "Distribución", "Rutas", "ALTA", _DIST, "DEFINIDO",
     f"{IF} §6.3", "Se aprueba entrega parcial; se genera propuesta de ruta.", True),
    ("OV_CAMBIO", "Cambio de OV con reserva existente", "Comercial", "Cambios de OV", "MEDIA", _LOG + _ALM + _GO, "DEFINIDO",
     f"{IF} §6.3, §14", "Modificación de una OV que ya tenía reservas.", True),
    ("OV_MODIF_SOLICITUD", "Solicitud de modificación de OV (Asistente)", "Comercial", "Cambios de OV", "MEDIA", _COM, "DEFINIDO",
     f"{IF} §5", "El Asistente de Ventas solicita modificar una OV; autorizan Coord./Jefe de Ventas o vendedor responsable.", True),
    ("OV_CANCELADA", "OV cancelada (reserva y ruta liberadas)", "Comercial", "Cambios de OV", "MEDIA", _ALM + _DIST + ["JEFE_LOGISTICA"],
     "PROPUESTO", f"{IF} §5, §14", "Cancelación por Coordinador o Jefe de Ventas.", True),
    ("OV_ESTADO", "Cambio de estado de pedido", "Comercial", "Estados de pedidos", "BAJA", ["COORD_VENTAS"], "PROPUESTO",
     f"{IF} §14", "Cambio de estado relevante de la OV (preparada, despachada, entregada).", False),
    ("OV_80_PREPARACION", "Pedido al 80 % de preparación", "Almacén", "Estados de pedidos", "MEDIA", _DIST + ["COORD_VENTAS"],
     "PROPUESTO", f"{IF} §14 (condición definida; destinatarios propuestos)", "Avance de preparación ≥ umbral configurado (80 %).", False),
    ("OV_PREPARADA", "Pedido preparado y listo para despacho", "Almacén", "Estados de pedidos", "MEDIA", _DIST + ["COORD_VENTAS"],
     "PROPUESTO", "Diagrama AS-IS L5 ('Aviso a Distribución: pedido completo')", "Preparación al 100 %.", False),
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
    ("FUMIGACION", "Fumigación iniciada/finalizada", "Calidad", "Fumigación y no utilizables", "MEDIA", _CAL + _ALM, "PROPUESTO",
     f"{IF} §14; REG-BPM-CAL-005", "Registro de inicio/fin de fumigación.", False),
    ("VENCIMIENTO_PROXIMO", "Lote próximo a vencer", "Almacén", "Faltantes y cobertura", "MEDIA", _ALM + ["COORD_VENTAS"], "PENDIENTE",
     f"{IF} §21 (caso 'vencimiento'); umbral no definido", "Solo si se configura 'dias_vencimiento_proximo'.", False),
    ("TRASLADO_SOLICITADO", "Traslado pendiente de autorización", "Logística", "Traslados", "MEDIA", ["JEFE_LOGISTICA"], "DEFINIDO",
     f"{IF} §6.2, §13", "Se solicita traslado desde almacén alternativo.", True),
    ("TRASLADO_AUTORIZADO", "Traslado autorizado", "Almacén", "Traslados", "MEDIA", _ALM + ["AUX_ALMACEN"], "PROPUESTO",
     f"{IF} §13", "Logística autoriza el traslado.", False),
    ("TRASLADO_DIFERENCIA", "Diferencia en recepción de traslado", "Logística", "Traslados", "ALTA", ["JEFE_LOGISTICA"] + _ALM + _GO,
     "PROPUESTO", f"{IF} §13", "Cantidad recibida distinta a la enviada.", True),
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
    ("REEMPAQUE_SOLICITUD", "Solicitud de reempaque para evaluación", "Calidad", "Solicitudes", "ALTA", _CAL, "DEFINIDO",
     f"{IF} §9.1", "Almacén inicia solicitud.", True),
    ("REEMPAQUE_APROBADO", "Reempaque aprobado: ejecutar", "Producción", "Solicitudes", "ALTA", _ALM + _PROD, "DEFINIDO",
     f"{IF} §9.1 (notifica a Almacén y envía a Producción)", "Calidad aprueba.", True),
    ("REEMPAQUE_DESAPROBADO", "Reempaque desaprobado", "Almacén", "Solicitudes", "MEDIA", _ALM, "PROPUESTO", f"{IF} §9.1",
     "Calidad desaprueba.", True),
    ("COMPRA_SOLICITUD", "Solicitud de compra originada en Almacén", "Compras", "Solicitudes", "MEDIA", ["COMPRAS"], "DEFINIDO",
     f"{IF} §10.1, §14", "Almacén envía solicitud.", True),
    ("COMPRA_MUESTRA", "Muestra de compra para evaluación", "Calidad", "Solicitudes", "MEDIA", _CAL, "DEFINIDO", f"{IF} §10.2-10.3",
     "Compras lleva muestra a Calidad.", True),
    ("COMPRA_APROBACION_GERENCIA", "Compra de mayor volumen requiere aprobación", "Gerencia", "Solicitudes", "ALTA", _GO, "PENDIENTE",
     f"{IF} §7 (umbral y participación por validar)", "Cantidad ≥ umbral configurado.", True),
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
    ("DIST_PROGRAMACION", "Programación de distribución generada", "Distribución", "Rutas", "MEDIA", _DIST + _LOG + _GO + _COM,
     "DEFINIDO", f"{IF} §12.1", "Se genera/confirma la programación de rutas.", True),
    ("DIST_AVANCE_RUTA", "Avance de ruta", "Distribución", "Rutas", "BAJA", _COM + _LOG + ["COORD_DISTRIBUCION"], "DEFINIDO",
     f"{IF} §12.3", "Salida, llegada, entrega.", False),
    ("GUIA_DISCREPANCIA", "Discrepancia entre carga y guía", "Seguridad", "Guías", "ALTA", ["COORD_DISTRIBUCION", "SEGURIDAD", "JEFE_LOGISTICA"],
     "PROPUESTO", f"{IF} §12.2, §14", "Cantidad cargada ≠ guía o presentación no coincide.", True),
    ("INC_RECHAZO_CALIDAD", "Rechazo por calidad", "Distribución", "Incidencias", "ALTA",
     ["GERENCIA_GENERAL"] + _GO + _LOG + _ALM + _COM, "DEFINIDO", f"{IF} §12.3 (tabla de destinatarios)", "Incidencia tipo rechazo por calidad.", True),
    ("INC_GENERAL", "Incidencia de distribución (llegada tarde u otra condición)", "Distribución", "Incidencias", "ALTA",
     _GO + _LOG + _ALM + _COM, "DEFINIDO", f"{IF} §12.3 (tabla de destinatarios)", "Retraso, ausente, parcial, devolución, vehículo esperando, etc.", True),
    ("CERTIFICADO_REVISION", "Certificado autogenerado pendiente de revisión", "Calidad", "Certificados", "MEDIA", _CAL, "DEFINIDO",
     f"{IF} §9.3, §9.4", "Se genera un certificado para lote de pedido listo para despacho.", False),
    ("CALIDAD_NO_CONFORME", "Producto/registro no conforme", "Calidad", "Calidad", "ALTA", _CAL + _GO, "PROPUESTO",
     "REG-BPM-CAL-013, REG-HACCP-CAL-002", "Registro de Calidad con resultado No conforme.", True),
]

# Tipos de incidencia (IF §12.3)
INCIDENT_TYPES = [
    ("RETRASO", "Retraso"),
    ("LLEGADA_TARDE", "Llegada tarde"),
    ("CLIENTE_AUSENTE", "Cliente ausente"),
    ("RECHAZO_CALIDAD", "Rechazo por calidad"),
    ("RECHAZO_OTRO", "Rechazo (otro motivo)"),
    ("ENTREGA_PARCIAL", "Entrega parcial"),
    ("DEVOLUCION", "Devolución"),
    ("CANCELACION", "Cancelación"),
    ("CAMBIO_RUTA", "Cambio de ruta"),
    ("VEHICULO_ESPERANDO", "Vehículo esperando"),
    ("CLIENTE_NO_RETIRA", "Cliente que no retira pedido"),
    ("CONDUCTOR_NO_DISPONIBLE", "Falta de disponibilidad del conductor"),
]

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
     "AS-IS", "Macro VBA 'TraerLotesStock' (PROM_15D) en PCP 2026 - J.xlsm"),
    ("factor_stock_seguridad", 0.30, "float", "Reposición",
     "Stock de seguridad como % del consumo mensual promedio observado en el Excel actual. Solo se aplica si 'usar_stock_seguridad' = sí.",
     "AS-IS", "Rotacion de inventario - Almacenes.xlsx, hoja Reporte ('30% stk seg')"),
    ("usar_stock_seguridad", False, "bool", "Reposición",
     "Aplicar el factor de stock de seguridad AS-IS en el análisis de reposición.", "PENDIENTE", f"{IF} §16 (stock mínimo configurable)"),
    ("umbral_mayor_volumen", None, "float", "Compras",
     "Cantidad a partir de la cual una compra se considera de mayor volumen.", "PENDIENTE", f"{IF} §7, §20"),
    ("mayor_volumen_requiere_go", True, "bool", "Compras",
     "Si la compra de mayor volumen requiere aprobación de Gerencia de Operaciones.", "PENDIENTE", f"{IF} §7, §20"),
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
     "AS-IS", "Diagrama AS-IS L5 (Revisar el stock físico vs. lo solicitado); IF §20"),
    ("umbrales_tamano_pedido_kg", None, "dict", "Almacén",
     "Límites en kg para clasificar pedido pequeño/mediano/grande.", "PENDIENTE", "No definido en la documentación"),
    ("umbral_alerta_preparacion_pct", 80, "int", "Almacén", "Avance de preparación que dispara la alerta.", "DEFINIDO", f"{IF} §14"),
    ("orden_prioridad", ["fecha_compromiso", "completitud", "urgencia"], "list", "Almacén",
     "Criterios de prioridad en el orden aplicado (los criterios están definidos; el orden de desempate es propuesto).",
     "PROPUESTO", f"{IF} §1, §5, §12.1"),
    ("uso_almacen_por_tipo", {"PT": "PT", "GR": "MP_INSUMOS", "MP": "MP_INSUMOS", "INSUMO": "MP_INSUMOS"}, "dict", "Almacén",
     "Almacén principal según tipo de artículo (TIPO de la tabla DATA: PT/GR/MP; insumos EN-/SU- = INSUMO).",
     "DEFINIDO", f"{IF} §6.2 (1560 = PT; 1524 = materia prima, granel e insumos)"),
    ("politica_lotes", "FEFO", "str", "Almacén",
     "Orden de consumo de lotes al reservar (FEFO = primero en vencer, primero en salir).", "PROPUESTO", f"{IF} §22 (respetar lote y vencimiento)"),
    ("dias_vencimiento_proximo", None, "int", "Almacén", "Días previos al vencimiento para alertar.", "PENDIENTE", "No definido"),
    ("estado_lote_nuevo_carga", "DISPONIBLE", "str", "Almacén",
     "Estado asignado a lotes nuevos que aparecen en una carga SAP (DISPONIBLE o PENDIENTE_REVISION).", "PENDIENTE",
     f"{IF} §6.1 (Pendiente de revisión = carga recibida) vs. base inicial"),
    ("carga_autorizada_verifica", True, "bool", "Almacén",
     "Una carga revisada y autorizada marca los lotes como verificados (hasta que un conteo registre diferencias).",
     "PROPUESTO", f"{IF} §6.3-6.4"),
    ("reevaluar_tras_carga", True, "bool", "Almacén",
     "Reevaluar automáticamente OV con faltantes (por prioridad) al ingresar stock.", "PROPUESTO", f"{IF} §1, §6.3"),
    ("bloquear_salida_con_discrepancia", False, "bool", "Distribución",
     "Bloquear la confirmación de salida si hay discrepancias carga vs guía (si no, solo advierte y alerta).",
     "PENDIENTE", f"{IF} §12.2, §20"),
    ("zonas_distrito", {}, "dict", "Distribución",
     "Agrupación de distritos en zonas de reparto (si está vacío se agrupa por distrito).", "PENDIENTE", f"{IF} §12.1"),
    ("capacidad_externo_kg", [2000, 25000], "list", "Distribución",
     "Rango de capacidad de transportes externos (kg).", "AS-IS", "Imagen tabla de transportes (2 TN a 25 TN)"),
    ("otif_definicion", "AMBAS", "str", "Indicadores",
     "SALIDA (pedido completo que salió a tiempo), ENTREGA (completo y a tiempo en destino) o AMBAS.", "PENDIENTE", f"{IF} §17, §20"),
    ("ambito_gerencia_operaciones", ["Almacén", "Distribución", "Logística", "Producción", "Calidad", "Compras",
                                    "Importaciones", "Seguridad", "Comercial", "Gerencia"], "list", "Alertas",
     "Áreas cuyas alertas ve Gerencia de Operaciones.", "PENDIENTE", f"{IF} §14 ('alertas de su ámbito')"),
    ("acceso_completo_omite_aprobaciones", False, "bool", "Seguridad",
     "Si GG/Sistemas pueden omitir pasos de aprobación. Por defecto NO: pueden aprobar, pero ningún paso se salta y todo queda auditado.",
     "PENDIENTE", f"{IF} §15, §20"),
    ("empresa_razon_social", "CORPORACION PRODUCTIVA S.A.C.", "str", "Certificados", "Procesado por (certificados).", "DEFINIDO",
     "Certificados N°CP2026-PT3756 / MP276 / CA0764"),
    ("empresa_ruc", "20517540341", "str", "Certificados", "RUC del emisor (certificados).", "DEFINIDO", "Certificados N°CP2026-*"),
    ("autorizacion_sanitaria", "Nº000502- MIDAGRI-SENASA-LIMA CALLAO", "str", "Certificados",
     "Autorización sanitaria (los modelos muestran 'MIDAGRI' y 'MINAGRI'; confirmar).", "PENDIENTE", "Certificados N°CP2026-MP276 y PT3756"),
    ("series_certificado", {"PT": "PT", "MQ": "PT", "AB": "PT", "MP": "MP", "GR": "MP"}, "dict", "Certificados",
     "Serie de numeración por tipo de artículo (CP{año}-{serie}{correlativo}). La serie 'CA' existe en los modelos pero su criterio no está documentado.",
     "PENDIENTE", "Certificados N°CP2026-PT3756 / MP276 / CA0764"),
    ("muestreo_tiempo_min_por_lote", 30, "int", "Calidad", "Tiempo orientativo de muestreo por lote en reempaque.", "AS-IS",
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
]

# Líneas de producción (PDF de formatos de producción). Capacidad no documentada.
PRODUCTION_LINES = [
    ("R1", "Envasado automático R1", "ENVASADOS R1 R2 Y R3.pdf"),
    ("R2", "Envasado automático R2", "ENVASADOS R1 R2 Y R3.pdf"),
    ("R3", "Envasado automático R3", "ENVASADOS R1 R2 Y R3.pdf"),
    ("TRUER", "Línea Truer", "LINEA TRUER.pdf"),
    ("CIMBRIA", "Línea Cimbria", "Linea cimbria.pdf"),
    ("SEL_MANUAL", "Selección manual", "SEL-MANUAL.pdf"),
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
    (4, "Llegada a almacén", 28, 2, "COORD_ALMACEN"),
]

REPACK_TYPES = [
    ("ACTUALIZACION_FECHA", "Actualización de fecha de producción",
     "No hay materia prima, pero sí producto apto del mes anterior. Calidad muestrea bolsa y aprueba/desaprueba. Aprox. 1 h; muestreo ~30 min por lote."),
    ("CAMBIO_PRESENTACION", "Cambio de presentación",
     "No hay materia prima; se conserva la información y se cambia la presentación (p.ej. 10 kg a 5 kg). Tiempo similar; medir."),
    ("CONVERSION_CALIDAD", "Conversión de calidad",
     "No hay material de la misma calidad; se revisan conversión, SKU, lote, fecha de producción y disposición. Criterios pendientes de Calidad."),
]
