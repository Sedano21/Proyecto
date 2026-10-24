"""Contenido del manual de usuario por rol: papel en el proceso, lo que no le corresponde y tareas paso a paso.

Describe las funciones tal como están implementadas en el sistema (prototipo v0.9). Las pantallas autorizadas se
listan aparte, a partir de los permisos del rol (app/manual.py).
"""


def _t(titulo, donde, *pasos):
    return {"titulo": titulo, "donde": donde, "pasos": list(pasos)}


ALERTA = _t("Atender sus alertas y tareas", "Inicio · Alertas y tareas",
            "Revise en Inicio «Mis tareas» y «Alertas abiertas»; las de urgencia alta aparecen primero y suenan distinto.",
            "Abra la alerta: verá qué ocurrió, el documento relacionado y quién debe atenderla.",
            "Si es «Acción requerida», apruebe o desapruebe (con motivo cuando corresponde), desígnela a alguien de su área o "
            "márquela en ejecución y complétela con la evidencia.",
            "Si es «Información», no requiere acción de su perfil: puede seguir su avance o comentar.",
            "Cuando el sistema deriva la tarea a otra área, la verá como «Derivada · pendiente <área>» hasta que esa área la cierre.")

ROLES = {
    "GERENCIA_GENERAL": {
        "resumen": "Visualiza todas las funciones, informes y movimientos de todas las áreas, y puede aprobar en nombre de otros "
                   "roles (salvo los permisos exclusivos de Comercial y de Sistemas).",
        "no_hace": "Modificar listas de precios ni la configuración del sistema (son exclusivas del Jefe Comercial y de Sistemas).",
        "tareas": [ALERTA,
                   _t("Revisar el estado de la operación", "Inicio · Informes",
                      "En Inicio revise los indicadores de pedidos, comercial y operación.",
                      "En Informes abra el informe del área, descárguelo en PDF o Excel, o arme su propio informe.",
                      "En Auditoría consulte los movimientos de cualquier usuario.")]},
    "GERENCIA_OPERACIONES": {
        "resumen": "Visualiza todas las funciones, informes y movimientos de todas las áreas. Aprueba la ejecución de las compras "
                   "(con las cotizaciones), el despacho parcial y la recepción bajo observación.",
        "no_hace": "Autorizar presolicitudes de compra (lo hacen Logística o el Coordinador de Almacén) ni asignar picking.",
        "tareas": [ALERTA,
                   _t("Aprobar la ejecución de una compra", "Alertas · Compras nacionales → detalle",
                      "Abra la alerta «Aprobar ejecución de la compra».",
                      "Revise el motivo (quiebre de stock, OV de origen y pedidos similares) y las cotizaciones registradas por Compras.",
                      "Pulse «Aprobar ejecución» (o rechace con motivo). Compras podrá generar la orden."),
                   _t("Aprobar un despacho parcial", "OV → Resumen", "Abra la OV detenida por cobertura incompleta.",
                      "Indique la fecha a la que se reprograma el saldo y apruebe.")]},
    "SISTEMAS": {
        "resumen": "Administra la configuración, usuarios, permisos y alertas. Tiene acceso completo sin aprobar en nombre de otros roles.",
        "no_hace": "Aprobar documentos de las áreas.",
        "tareas": [_t("Configurar parámetros, líneas, canales y alertas", "Administración · Configuración",
                      "Cada cambio crea una versión del parámetro y queda auditado.",
                      "En «Líneas de producción» se ajusta la capacidad por grupo de líneas.",
                      "En «Canales y grupos» se agregan canales de precios y grupos de cliente.",
                      "En «Configurar alertas» se definen destinatarios, urgencia y naturaleza de cada tipo de alerta.",
                      "En «Datos de la guía» se modifican el correo, la web y el punto de partida por almacén."),
                   _t("Cargar los feriados del año", "Configuración · Feriados",
                      "Suba el Excel o PDF con Fecha, Nombre y (opcional) Se trabaja; reemplaza los feriados de ese año.",
                      "También puede agregar o quitar feriados uno por uno."),
                   _t("Administrar usuarios", "Administración · Usuarios", "Cree el usuario, asigne su rol y, si es personal "
                      "de almacén, su almacén (para el picking).")]},
    "GERENTE_COMERCIAL": {"resumen": "Consulta pedidos, clientes, informes comerciales y alertas de Comercial.", "tareas": [ALERTA]},
    "JEFE_VENTAS": {
        "resumen": "Dirige Comercial: confirma precios fuera de rango, modifica listas de precios, asigna canales, autoriza "
                   "modificaciones de OV y gestiona costos y precios de mercado.",
        "tareas": [ALERTA,
                   _t("Confirmar un precio por debajo del mínimo o del costo", "Alerta de precio · OV → Resumen",
                      "Abra la OV detenida por precio.", "Escriba el motivo y confirme: quedará registrado su nombre como "
                      "quien aprobó el precio fuera del rango (visible en la OV y en la lista de OV)."),
                   _t("Registrar precios de competencia y sustitutos", "Costos vs mercado · Análisis de mercado",
                      "Elija el producto base de la lista desplegable, el origen (competencia, sustituto o mercado), el precio por kg y la fecha.",
                      "También puede importar un informe en Excel o PDF y confirmar las filas compatibles.",
                      "La recomendación automática se actualiza al instante: p. ej. «estamos 15 % más arriba que el sustituto y "
                      "10 % más abajo respecto a la competencia»."),
                   _t("Agregar un canal o un grupo de cliente", "Administración · Canales y grupos",
                      "Escriba el nombre y confirme. El canal queda disponible en la OV y en la ficha del cliente."),
                   _t("Regularizar una OV con fecha pasada", "Comercial · Regularización de OV",
                      "Registre la OV con su motivo: no reserva stock.",
                      "Luego libérela con una fecha vigente (se evalúa y reserva) o ciérrela como registro.")]},
    "COORD_VENTAS": {
        "resumen": "Registra y modifica OV, confirma precios fuera de rango, autoriza modificaciones y agrega canales.",
        "tareas": [ALERTA,
                   _t("Registrar una OV", "Comercial · Registrar OV",
                      "Elija el cliente y una fecha comprometida vigente (no se aceptan fechas pasadas ni horas ya transcurridas).",
                      "Complete la entrega y las líneas: producto, cantidad y precio son obligatorios.",
                      "Si falta algo, el campo se resalta y no se borra nada de lo escrito.",
                      "Al guardar, el sistema evalúa stock, reservas y condiciones del cliente."),
                   _t("Editar una OV", "Órdenes de venta",
                      "En la lista, pulse el lápiz junto a la OV (o «Editar» en el detalle).",
                      "Cambie fecha, cita, comentarios o líneas y confirme; la OV se reevalúa."),
                   _t("Gestionar una OV", "OV → Gestionar", "Renegociar fecha, proponer producto disponible o cancelar (con motivo).")]},
    "ASIST_VENTAS": {
        "resumen": "Registra OV y clientes; solicita modificaciones (las autoriza Comercial) y regulariza OV con fecha pasada.",
        "no_hace": "Modificar OV directamente ni confirmar precios fuera de rango.",
        "tareas": [ALERTA,
                   _t("Registrar un cliente nuevo", "Comercial · Clientes",
                      "Ingrese RUC, razón social y elija el grupo de la lista desplegable; luego complete la ficha."),
                   _t("Registrar una OV", "Comercial · Registrar OV", "Producto, cantidad y precio son obligatorios en cada línea; "
                      "la fecha debe ser vigente. Para fechas pasadas use «Regularización de OV»."),
                   _t("Solicitar una modificación", "Órdenes de venta → lápiz",
                      "Pulse el lápiz de la OV, indique los cambios y el motivo, y envíe la solicitud para su autorización.")]},
    "EJECUTIVO_VENTAS": {
        "resumen": "Vendedor responsable de su canal: registra y modifica sus OV, renegocia fechas y regulariza OV con fecha pasada.",
        "tareas": [ALERTA, _t("Seguir sus pedidos", "Órdenes de venta → detalle",
                              "La pestaña «Resumen» muestra el avance; «Expediente» reúne OV, certificado, guía y factura.")]},
    "COORD_ALMACEN": {
        "resumen": "Coordina el almacén 1560: stock, cargas de SAP, picking, opciones ante faltantes, presolicitudes de "
                   "reempaque y compra, y recepción de producto terminado.",
        "tareas": [ALERTA,
                   _t("Cargar el stock de SAP (Excel o PDF)", "Almacén · Cargas de archivos",
                      "Elija el tipo de carga y suba el archivo; revise errores y advertencias y autorice la carga."),
                   _t("Asignar o modificar el picking", "Almacén · Programación de picking",
                      "Abra la tarea (icono de personas): elija «Una persona» (lista desplegable) o «Un grupo» (sin límite).",
                      "Vea el preplaneamiento del día para repartir la carga."),
                   _t("Autorizar una presolicitud de compra", "Alerta «Presolicitud de compra por autorizar»",
                      "Revise la OV de origen y el motivo (quiebre de stock, pedidos similares, plazo de reposición) y autorice: "
                      "pasa a Compras. La ejecución la aprueba Gerencia de Operaciones."),
                   _t("Evaluar opciones ante faltante", "OV → Condición y opciones",
                      "El sistema ordena las opciones: 1 producción, 2 reempaque, 3 traslado externo, 4 compra; elija con motivo.")]},
    "COORD_ALMACEN_MP": {"resumen": "Mismas funciones que la Coordinación de Almacén 1560, sobre el almacén 1524 (materia prima, "
                                    "granel e insumos).", "tareas": [ALERTA]},
    "SUPERV_ALMACEN": {"resumen": "Supervisa el almacén: stock, conteos, reempaques e informes.", "tareas": [ALERTA]},
    "LIDER_ALMACEN": {
        "resumen": "Líder operativo: asigna el picking a una persona o a un grupo, valida la planificación y autoriza la salida del camión.",
        "tareas": [ALERTA,
                   _t("Asignar el picking", "Almacén · Programación de picking → tarea",
                      "Revise el preplaneamiento del día (OV, líneas y personas).",
                      "Elija «Una persona» y selecciónela de la lista, o «Un grupo» y marque a todas las personas.",
                      "Guarde: a cada persona le llega su alerta."),
                   _t("Autorizar la salida del camión", "Distribución · Ruta → Vistos buenos",
                      "Verifique el checklist, el kilometraje y los vistos buenos, y autorice la salida.")]},
    "AUX_ALMACEN": {
        "resumen": "Realiza el picking asignado con el formato de seguimiento de control de despacho.",
        "no_hace": "Asignar picking ni modificar lote, fechas o cantidades solicitadas del formato.",
        "tareas": [ALERTA,
                   _t("Hacer el picking", "Almacén · Programación de picking → su tarea",
                      "1. Inicie con la foto: se abre el formato ya completado con el stock reservado.",
                      "2. Llene solo «Despachado und» de cada fila y pulse «Registrar» (los bultos se calculan solos).",
                      "Si picó otro lote: «Cambiar lote», elija el lote picado, el motivo (rotura o dañado, infestación, "
                      "contaminación o difícil acceso) y la observación. El formato y el stock se actualizan al instante.",
                      "3. Al terminar, suba la foto de la mercadería lista para el despacho.")]},
    "MONTACARGUISTA": {"resumen": "Traslada la mercadería a la zona de despacho y atiende los movimientos punto a punto que "
                                  "solicitan las áreas: inicia y termina con foto.",
                       "tareas": [_t("Atender un traslado", "Alertas", "Abra la tarea, inicie con foto y termínela con foto."),
                                  _t("Atender un movimiento punto a punto", "Almacén · Movimientos punto a punto",
                                     "Tome la solicitud con la foto del origen y termínela con la foto de validación en el destino.")]},
    "COORD_DISTRIBUCION": {
        "resumen": "Programa rutas, ve la pre-guía, aprueba la guía y consulta el expediente completo de cada OV "
                   "(OV, certificado, guía y factura). No ve líneas, reservas ni lotes de la OV.",
        "tareas": [ALERTA,
                   _t("Aprobar la guía", "Distribución · Ruta → 3. Documentos por pedido",
                      "Abra «ver guía» o la pre-guía y revise los datos.", "Pulse «Aprobar guía» (con comentario opcional)."),
                   _t("Ver el expediente de una OV", "OV → Expediente", "Pulse «Ver expediente completo» para ver o imprimir todo junto.")]},
    "ASIST_DISTRIBUCION": {"resumen": "Apoya la programación de rutas, la flota y los documentos; aprueba la guía como el Coordinador.",
                           "tareas": [ALERTA]},
    "CONDUCTOR": {"resumen": "Registra las fotos del vehículo al salir y al retornar, las llegadas y la conformidad digital de "
                             "cada entrega.",
                  "no_hace": "Dar conformidad del estado del producto (compete a Calidad, Distribución y Almacén).",
                  "tareas": [_t("Registrar la conformidad de una entrega", "Distribución · Mis entregas",
                                "Toque «Llegué»; en «Registrar conformidad» anote nombre y DNI de quien recibe, pida su firma en "
                                "pantalla y suba la foto de la entrega y la guía firmada.")]},
    "AUX_DESPACHO": {"resumen": "Consulta y reporta el estado de las guías de remisión; valida la carga y da su visto bueno a "
                                "la salida (Q16).",
                     "tareas": [_t("Reportar el estado de una guía", "Distribución · Guías de remisión",
                                   "Busque la guía y con el lápiz indique su estado (firmada, observada, devuelta…)."), ALERTA]},
    "JEFE_LOGISTICA": {
        "resumen": "Autoriza presolicitudes de compra y traslados, decide alternativas ante faltantes y aprueba salidas con discrepancia.",
        "tareas": [ALERTA,
                   _t("Autorizar presolicitudes de compra", "Abastecimiento · Compras nacionales",
                      "Las presolicitudes del mismo producto y fecha de entrega llegan agrupadas, con todas sus OV de origen y el motivo.",
                      "Autorice para que pasen a Compras.")]},
    "COORD_LOGISTICA": {"resumen": "Mismas autorizaciones que el Jefe de Logística en presolicitudes de compra y traslados.",
                        "tareas": [ALERTA]},
    "JEFE_PRODUCCION": {
        "resumen": "Valida y programa la producción, revisa el planeamiento preprogramado por el sistema y lo edita.",
        "tareas": [ALERTA,
                   _t("Validar una solicitud de producción", "Producción · Solicitudes → detalle",
                      "Confirme lista de insumos, capacidad y plazo. Si faltan materiales puede aprobar igual: el sistema "
                      "pide los faltantes a Compras y alerta el quiebre de stock."),
                   _t("Revisar el planeamiento", "Producción · Planeamiento",
                      "Vea los requerimientos consolidados por producto y periodo (día, semana o mes).",
                      "Pulse «Preprogramar» y edite las cantidades con su motivo.",
                      "Consulte los materiales faltantes y su fecha estimada de llegada.",
                      "En «Feriados del año» marque los feriados que se trabajarán según la necesidad: cuentan como día normal."),
                   _t("Programar en una línea", "Solicitud → Programar",
                      "Elija la línea y la fecha: se verifica la capacidad del grupo de líneas con la jornada (sábado medio día; "
                      "domingos y feriados no se opera).")]},
    "ASIST_PRODUCCION": {
        "resumen": "Registra partes y liquidaciones, carga listas de materiales y consulta requerimientos y faltantes.",
        "tareas": [ALERTA, _t("Consultar qué producir", "Producción · Planeamiento",
                              "Revise el consolidado por producto, fecha y cantidad y el seguimiento de materiales faltantes.")]},
    "JEFE_CALIDAD": {"resumen": "Revisa y aprueba certificados, libera lotes y evalúa reempaques y muestras.", "tareas": [ALERTA]},
    "SUPERV_CALIDAD": {
        "resumen": "Revisa y aprueba certificados (el precertificado se emite después del picking), libera lotes y evalúa reempaques.",
        "tareas": [ALERTA,
                   _t("Revisar un certificado", "Calidad · Certificados → detalle",
                      "Corrija los datos y pulse «Guardar avance»: queda como borrador y puede continuar después.",
                      "Pulse «Confirmar y aprobar»: se pide confirmación; si falta un dato, se guarda lo escrito y se indica qué falta.")]},
    "ASIST_CALIDAD": {
        "resumen": "Registra la información de Calidad antes, durante y después de la producción.",
        "tareas": [_t("Registrar antes de producir", "Calidad · Liberación y registros → Antes de producir",
                      "Marque si todo el personal cumplió las normas de higiene y si los equipos cumplieron las normas de calidad e higiene."),
                   _t("Registrar durante la producción", "Durante la producción → Ingreso de nuevo lote",
                      "Registre el lote, la cantidad y los datos de la ficha. Se contrasta con la liquidación; el stock se "
                      "actualiza cuando Almacén confirma la recepción."),
                   _t("Registrar después de producir", "Después de producir", "Cierre del proceso, análisis del lote para el certificado.")]},
    "COMPRAS": {
        "resumen": "Recibe las presolicitudes autorizadas, registra cotizaciones, pide la aprobación de ejecución a Gerencia de "
                   "Operaciones y genera la orden de compra.",
        "tareas": [ALERTA,
                   _t("Gestionar una compra", "Abastecimiento · Compras nacionales → detalle",
                      "Registre al menos 3 cotizaciones (proveedor, precio, plazo y archivo) y elija la que se propone.",
                      "Pulse «Pedir aprobación de ejecución a Gerencia de Operaciones».",
                      "Con la aprobación, genere la orden con su fecha prevista de recepción.")]},
    "IMPORTACIONES": {"resumen": "Gestiona embarques y fases de importación y registra precios de importación.", "tareas": [ALERTA]},
    "SEGURIDAD": {
        "resumen": "Controla las salidas (rutas) y las llegadas de compras e importaciones, con fotos.",
        "no_hace": "Validar la limpieza o la estiba del vehículo (lo hace Calidad).",
        "tareas": [ALERTA,
                   _t("Validar la salida contra la guía", "Distribución · Ruta → 4. Seguridad",
                      "Compare ítem por ítem lo que debe salir (guía) con lo que sale.",
                      "Deje marcado «conforme» o desmárquelo y escriba el motivo de la no conformidad; puede subir una foto."),
                   _t("Registrar las horas del despacho", "Ruta → Horas del despacho",
                      "Registre la hora de inicio del despacho, la de partida del vehículo y la de retorno."),
                   _t("Controlar el vehículo", "Seguridad · Control de vehículos",
                      "Valide placa y chofer programados y si el vehículo está en orden; si no, describa qué subsanar (se alerta a Distribución)."),
                   _t("Validar llegadas de compras e importaciones", "Seguridad · Llegadas de compras e importaciones",
                      "Registre la cantidad que ingresa, placa y chofer; marque conforme o registre el incidente con foto (se notifica).")]},
    "FACTURACION": {"resumen": "Evalúa el pedido validado y carga la factura de SAP en la ruta.", "tareas": [ALERTA]},
}

# ------------------------------------------------------------------ ronda del 23-oct-2026
ROLES["COORD_FINANZAS"] = {
    "resumen": "Aprueba las condiciones de pago de los clientes, carga las facturas y notas de crédito, confirma los pagos "
               "que sube Comercial y gestiona la cobranza de las facturas vencidas.",
    "no_hace": "Registrar OV ni modificar la ficha comercial del cliente (lo hace Comercial).",
    "tareas": [ALERTA,
               _t("Aprobar una condición de pago", "Finanzas · Cobranza y condiciones → cliente",
                  "Abra la alerta «Condición de pago por aprobar» o el cuadro de Finanzas.",
                  "En la ficha del cliente revise la condición (contado o crédito, monto y plazo) y los documentos del tramo.",
                  "Apruebe, observe (indique qué falta) o rechace con el motivo. Sin aprobación el cliente solo tiene OV de muestra."),
               _t("Cargar facturas y notas de crédito", "Finanzas · Cobranza y condiciones",
                  "Suba el Excel exportado de SAP (número, tipo, RUC, OV, fechas, monto, saldo).",
                  "Adjunte los PDF: individual (un número) o consolidado (varios números separados por coma).",
                  "O registre una factura o nota de crédito manualmente; la nota de crédito descuenta el saldo de su factura."),
               _t("Confirmar pagos y gestionar vencidas", "Finanzas · Cobranza y condiciones",
                  "Confirme u observe los comprobantes que subieron los vendedores: al confirmar se descuenta el saldo.",
                  "Gestione las vencidas por antigüedad (1-15, 16-30, 31-60 y más de 60 días); el vendedor recibe la alerta.",
                  "Todo queda en el archivo del cliente: deuda, facturas, pagos y documentos.")]}
_COM_R23 = [_t("Registrar una OV con su orden de compra", "Comercial · Registrar OV",
               "La unidad la fija el código (granel y MP en kilos; envasado en unidades).",
               "Adjunte la orden de compra del cliente o la plantilla del pedido por WhatsApp o correo; sin ella la OV queda "
               "como borrador y no se evalúa (adjúntela después desde la OV).",
               "Después de las 12:00 no se registra una OV para despachar mañana.",
               "Si Operaciones responde «No cumple», le llega la alerta para negociar con el cliente."),
            _t("Oportunidades, acciones y cotizaciones", "Comercial · Oportunidades",
               "Registre cada acción con el cliente (visita, llamada, reunión virtual, mensajería, carta u oficio) con su resultado.",
               "Cree la oportunidad con los productos de interés y la proyección mensual; emita cotizaciones desde ella.",
               "Para pasar un prospecto a cliente: una acción registrada y su orden de compra (ficha del cliente)."),
            _t("Condición de pago y pagos del cliente", "Clientes → ficha → Finanzas",
               "Solicite la condición de pago con los documentos del tramo; Finanzas la aprueba.",
               "Suba los comprobantes de pago de sus clientes; Finanzas los confirma y se actualiza la deuda.")]
for _r in ("JEFE_VENTAS", "COORD_VENTAS", "EJECUTIVO_VENTAS"):
    ROLES.setdefault(_r, {"resumen": "", "tareas": [ALERTA]})["tareas"] = list(ROLES[_r].get("tareas", [])) + _COM_R23
ROLES["JEFE_VENTAS"]["tareas"].append(_t(
    "Configuración comercial", "Comercial · Configuración comercial",
    "Configure por defecto, por canal y por cliente los rebates (comercial, logística, B2B, no devolución) y los gastos.",
    "Registre el mercaderismo por cliente y mes, los objetivos de venta y las reglas de incentivo por canal y vendedor.",
    "Revise el margen (Comercial · Margen), los objetivos y los incentivos; apruebe los precios de mercado de los vendedores."))
_PROD_R23 = [_t("Parte en línea", "Producción · Partes de producción",
                "Inicie el parte con línea, producto, EAN escaneado, lote y kg de MP (si el EAN no coincide se alerta).",
                "Pause con la causa de la lista (y foto si desea) y reanude; el tiempo muerto se suma solo.",
                "Al finalizar registre operarios, pallets, defectos por causa y colaboradores: se calculan rendimiento, "
                "desviación de peso, horas efectivas, velocidad y OEE."),
             _t("Liquidar", "Producción · Liquidaciones",
                "Registre horas trabajadas y operarios (SAP los exige) y los kg de MP.",
                "Si el rendimiento está fuera del rango de la línea y presentación, o las horas pasan del tope, la liquidación "
                "queda bloqueada hasta corregirla y se alerta al Jefe de Producción."),
             _t("Control de producción y tablero OEE", "Producción · Control de producción / Tablero OEE",
                "Revise el reporte diario, semanal o mensual: producción vs plan por línea, horas efectivas, kg/h, asistencia, "
                "hallazgos y acciones.", "En el tablero OEE vea disponibilidad, rendimiento, calidad y el Pareto de causas.")]
for _r in ("JEFE_PRODUCCION", "ASIST_PRODUCCION"):
    ROLES.setdefault(_r, {"resumen": "", "tareas": [ALERTA]})["tareas"] = list(ROLES[_r].get("tareas", [])) + _PROD_R23
ROLES["JEFE_PRODUCCION"]["tareas"].append(_t(
    "Validar cambios y configurar", "Producción · Planeamiento / Configuración de Producción",
    "Valide o rechace los cambios al programa que proponen los asistentes.",
    "Configure velocidades nominales, causas, tolerancias, líneas de cada asistente y cargue la tabla GS1 ↔ SAP.",
    "Registre la asistencia del personal (también el asistente designado)."))
for _r in ("JEFE_CALIDAD", "SUPERV_CALIDAD", "ASIST_CALIDAD"):
    ROLES.setdefault(_r, {"resumen": "", "tareas": [ALERTA]})["tareas"] = list(ROLES[_r].get("tareas", [])) + [_t(
        "Bloquear un parte de producción", "Producción · Partes de producción → ver parte",
        "Si encuentra un problema, bloquee el parte indicando el motivo (se alerta a Producción).",
        "Tras la fumigación o el reproceso, libérelo indicando la acción realizada.")]
for _r in ("JEFE_LOGISTICA", "COORD_LOGISTICA", "COORD_ALMACEN", "COORD_ALMACEN_MP"):
    ROLES.setdefault(_r, {"resumen": "", "tareas": [ALERTA]})["tareas"] = list(ROLES[_r].get("tareas", [])) + [_t(
        "Responder CUMPLE / NO CUMPLE", "OV → Resumen → Orden de compra y compromiso",
        "Al evaluar la OV responda si se cumplirá la fecha (con stock completo el sistema responde «Cumple» solo).",
        "Si no se cumplirá, indique el motivo y una fecha estimada: Comercial recibe la alerta. Sin respuesta en el plazo "
        "se alerta a Operaciones y a Comercial.",
        "Para cambiar la fecha de despacho, envíe la solicitud a Comercial desde la OV.")]
