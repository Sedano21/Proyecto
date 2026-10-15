"""Manual de usuario por rol (obs. demo v0.7: «Manual de usuario para cada rol»).

El manual se arma con las pantallas que el rol tiene autorizadas (los mismos permisos que aplica el sistema), una
descripción de su papel en el proceso y sus tareas paso a paso. Las secciones generales explican el uso común de la
interfaz (navegación, alertas con sonido, formularios, informes en PDF)."""
from flask import url_for
from sqlalchemy import select

from .db import db
from .models import RolePermission

# (permisos: basta uno, área, título, endpoint, args, texto)
PANTALLAS = [
    (["dashboard.ver", "alertas.ver"], "Panel", "Inicio", "main.dashboard", {}, "Sus tareas y alertas abiertas (las urgentes primero), indicadores de su área y accesos rápidos."),
    (["alertas.ver"], "Panel", "Alertas y tareas", "main.alerts", {}, "Todo lo que requiere su acción («Acción requerida») y los avisos («Información»). Lo que su perfil no puede aprobar, desestimar ni asignar aparece como información."),
    (["informes.comercial", "informes.reempaque", "informes.produccion", "informes.distribucion", "informes.almacen"], "Panel", "Informes", "rep.home", {}, "Informes de su área con gráficos, descarga en PDF y Excel, y el informe personalizado («Arme su informe»)."),
    (["ov.ver"], "Comercial", "Órdenes de venta", "com.orders", {}, "Lista priorizada. En cada OV: ojo = ver detalle, lápiz = editar, tres puntos = más opciones (renegociar fecha, proponer producto disponible, expediente, imprimir, cancelar)."),
    (["ov.crear"], "Comercial", "Registrar OV", "com.order_new", {}, "Alta de OV: cliente, fecha vigente, entrega y líneas con producto, cantidad y precio (obligatorios)."),
    (["ov.regularizar"], "Comercial", "Regularización de OV", "com.regularization", {}, "OV con fecha pasada u hora ya transcurrida: se registran sin reservar stock y luego se liberan con fecha vigente o se cierran como registro."),
    (["clientes.ver"], "Comercial", "Clientes", "com.customer_list", {}, "Fichas de clientes, canal, condiciones y comportamiento de compra."),
    (["precios.ver"], "Comercial", "Listas de precios", "com.prices", {}, "Precios mínimos vigentes por canal."),
    (["costos.ver"], "Comercial", "Costos vs mercado", "com.costs", {}, "Costo, precios de mercado, competencia y sustitutos con análisis y recomendaciones automáticas."),
    (["costos.ver"], "Comercial", "Productos sustitutos", "com.market_substitutes", {}, "Relación de sustitutos por producto base (individual o Excel)."),
    (["stock.ver"], "Almacén", "Stock y reservas", "alm.stock", {}, "Stock por almacén, lote y estado; reservas por OV; movimientos."),
    (["preparacion.registrar", "ov.ver"], "Almacén", "Preparación (picking)", "com.preparation", {}, "Avance de preparación por OV y corte."),
    (["picking.asignar", "tareas.ejecutar", "preparacion.registrar"], "Almacén", "Programación de picking", "alm.picking_schedule", {}, "Preplaneamiento del picking por fecha; asignación a una persona o a un grupo; formato de control de despacho."),
    (["traslados.ver"], "Almacén", "Traslados", "alm.transfers", {}, "Solicitudes, autorizaciones, salida y llegada de traslados entre almacenes."),
    (["reempaque.ver"], "Almacén", "Reempaque", "alm.repacks", {}, "Pre-solicitudes y solicitudes de reempaque con evaluación de Calidad."),
    (["stock.conteo"], "Almacén", "Conteos físicos", "alm.counts", {}, "Conteos y diferencias contra el sistema."),
    (["stock.cargar", "ov.importar", "precios.editar", "costos.cargar", "produccion.bom_cargar", "produccion.liquidar"], "Almacén", "Cargas de archivos", "alm.uploads", {}, "Carga de archivos en Excel o PDF (stock de SAP, OV, listas, liquidaciones…) con revisión antes de aplicar."),
    (["produccion.ver"], "Producción", "Solicitudes y programa", "prod.requests", {}, "Requerimientos por OV y consolidado por producto, fechas y cantidades."),
    (["produccion.ver"], "Producción", "Planeamiento", "prod.plan", {}, "Plan mensual, semanal y diario preprogramado por el sistema; lo edita el Jefe de Producción. Seguimiento de materiales faltantes y su fecha estimada de llegada."),
    (["produccion.ver"], "Producción", "Lista de materiales", "prod.bom", {}, "Lista de materiales por artículo y su aprobación."),
    (["produccion.ver"], "Producción", "Liquidaciones y partes", "prod.liquidations", {}, "Liquidaciones de producción y partes diarios por línea."),
    (["calidad.ver"], "Calidad", "Liberación y registros", "cal.home", {}, "Registros antes, durante y después de producción; liberación de lotes."),
    (["calidad.ver"], "Calidad", "Certificados", "cal.certificates", {}, "Pre-certificados (se emiten después del picking) y certificados; el avance se guarda como borrador."),
    (["compras.ver"], "Abastecimiento", "Compras nacionales", "buy.purchases", {}, "Pre-solicitudes agrupadas por producto y fecha, con la OV de origen, cotizaciones y aprobaciones."),
    (["compras.ver"], "Abastecimiento", "Análisis de reposición", "buy.replenishment", {}, "Quiebres de stock y tiempos de reposición."),
    (["importaciones.ver"], "Abastecimiento", "Importaciones", "buy.imports", {}, "Embarques y fases de importación."),
    (["distribucion.ver"], "Distribución", "Programación y rutas", "dist.routes", {}, "Rutas, pre-guía, aprobación de la guía, carga, salida y entregas."),
    (["distribucion.ver"], "Distribución", "Incidencias", "dist.incidents", {}, "Incidencias de distribución por tipo y subtipo."),
    (["distribucion.flota"], "Distribución", "Flota y conductores", "dist.fleet", {}, "Vehículos, conductores, documentos y mantenimiento."),
    (["config.ver"], "Administración", "Configuración", "main.config", {}, "Parámetros, almacenes, plazos, líneas de producción, canales y reglas de alertas."),
    (["usuarios.administrar"], "Administración", "Usuarios y permisos", "main.users", {}, "Usuarios, roles y matriz de permisos."),
    (["alertas.configurar"], "Administración", "Configurar alertas", "main.alert_config", {}, "Tipos de alerta, destinatarios, urgencia y naturaleza."),
    (["auditoria.ver"], "Administración", "Auditoría", "main.audit", {}, "Registro de acciones por usuario."),
]

GENERAL = [
    {"titulo": "Cómo moverse en el sistema", "pasos": [
        "El menú lateral muestra solo lo que su rol tiene autorizado. En computadora se contrae con el botón de la barra superior; en celular se abre con el botón de menú.",
        "Las migas de pan (arriba) indican dónde está; el chip «Stock SAP» indica la fecha de la última carga de stock (no es tiempo real).",
        "En los detalles (por ejemplo una OV) la información está organizada en pestañas: Resumen, Productos y reservas, Condición y opciones, Editar, Gestionar, Expediente e Historial.",
        "En las listas, cada registro tiene iconos de acción: ojo (ver), lápiz (editar) y tres puntos (más opciones)."]},
    {"titulo": "Alertas y sonido", "pasos": [
        "La campana muestra cuántas alertas abiertas tiene. Cuando llega una alerta nueva suena un aviso y aparece un mensaje en la esquina.",
        "Las alertas importantes (urgencia ALTA que usted debe atender) tienen un sonido distinto, más insistente, y se repiten cada cierto tiempo hasta que se resuelvan.",
        "El botón del parlante (junto a la campana) silencia o activa el sonido en su equipo. El navegador solo permite sonar después de que usted toque o haga clic en la página una vez.",
        "Una tarea que otra área debe completar se ve como «Derivada · pendiente <área>» para su seguimiento."]},
    {"titulo": "Formularios: lo escrito no se borra", "pasos": [
        "Los campos obligatorios tienen un asterisco rojo. Si falta alguno, el campo se resalta en rojo con su mensaje y no se pierde nada de lo escrito.",
        "Si el sistema rechaza el guardado (por ejemplo, una fecha pasada), la pantalla vuelve con sus datos y resalta lo que debe corregir.",
        "Las acciones importantes (confirmar un certificado, cancelar una OV, aprobar) piden confirmación en una ventana antes de ejecutarse."]},
    {"titulo": "Cargas de archivos (Excel y PDF)", "pasos": [
        "Las cargas aceptan Excel (.xlsx) y PDF. Del PDF se lee la tabla con los mismos encabezados que el Excel; si no se reconoce, el sistema lo indica.",
        "Toda carga muestra una revisión previa y solo se aplica cuando usted la confirma."]},
    {"titulo": "Informes en PDF y su propio informe", "pasos": [
        "Cada informe tiene el botón «Descargar PDF» y «Excel».",
        "En «Arme su informe» elige la fuente de datos, las columnas, el periodo y los filtros; puede verlo en pantalla y descargarlo en PDF o Excel."]},
]


def _perms(role_code):
    return {rp.perm_code for rp in db().execute(select(RolePermission).where(RolePermission.role_code == role_code)).scalars()}


def for_role(role):
    from .manual_roles import ROLES
    perms = _perms(role.code)
    grupos = {}
    for req, area, titulo, ep, args, texto in PANTALLAS:
        if any(p in perms for p in req):
            try:
                u = url_for(ep, **args)
            except Exception:  # noqa: BLE001
                u = ""
            grupos.setdefault(area, []).append({"titulo": titulo, "texto": texto, "url": u})
    info = ROLES.get(role.code, {})
    return {"resumen": info.get("resumen") or f"{role.nombre} del área {role.area}.", "no_hace": info.get("no_hace", ""),
            "tareas": info.get("tareas", []), "pantallas": list(grupos.items()), "general": GENERAL}
