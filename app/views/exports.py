"""Construcción de filas para exportación a Excel (IF §19 'Permitir descargar/exportar registros')."""
from sqlalchemy import select

from ..db import db
from ..models import (AuditLog, Incident, Liquidation, ProductionRequest, PurchaseRequest, QualityRecord, Route, SalesOrder,
                      StockLot)
from ..services.alerts import visible_alerts
from ..services.orders import order_amount, order_weight_kg
from ..services.stock import free_qty, reserved_qty


def build_rows(entidad, user):
    s = db()
    if entidad == "ov":
        h = ["OV", "Cliente", "Vendedor", "Emisión", "Fecha comprometida", "Urgente", "Estado", "Estado stock",
             "Cobertura unidades %", "Cobertura líneas %", "Decisión parcial", "Motivo detención", "Monto", "Kg"]
        rows = [[o.numero, o.customer.nombre, o.vendedor_nombre, o.fecha_emision, o.fecha_compromiso, o.urgente, o.estado,
                 o.estado_stock, o.cobertura_unidades, o.cobertura_lineas, o.decision_parcial, o.motivo_detencion,
                 order_amount(o), order_weight_kg(o, "solicitado")[0]] for o in s.execute(select(SalesOrder)).scalars()]
    elif entidad == "stock":
        h = ["Artículo", "Descripción", "Almacén", "Lote", "Cantidad SAP", "Cantidad verificada", "Reservado", "Libre",
             "Estado", "Vence", "Fabricación", "Verificado", "Origen"]
        rows = [[l.product_code, l.product.descripcion if l.product else "", l.warehouse_code, l.lote, l.cantidad,
                 l.cantidad_verificada, reserved_qty(l), free_qty(l), l.estado, l.fecha_venc, l.fecha_fab, l.verificado,
                 l.origen] for l in s.execute(select(StockLot).where(StockLot.cantidad > 0)).scalars()]
    elif entidad == "alertas":
        h = ["#", "Tipo", "Título", "Área", "Prioridad", "Estado", "Creada", "Asignado a", "Cerrada", "Motivo", "Acción"]
        rows = [[a.id, a.type_code, a.titulo, a.area, a.prioridad, a.estado, a.creado_ts,
                 a.asignado.nombre if a.asignado else "", a.cerrado_ts, a.motivo_cierre, a.accion_tomada]
                for a in visible_alerts(user)]
    elif entidad == "auditoria":
        h = ["#", "Fecha", "Usuario", "Acción", "Entidad", "Id", "Detalle"]
        rows = [[a.id, a.ts, a.user.nombre if a.user else "", a.accion, a.entidad, a.entidad_id, a.detalle]
                for a in s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(20000)).scalars()]
    elif entidad == "compras":
        h = ["#", "Producto", "Cantidad", "Necesidad", "Origen", "Estado", "Proveedor", "OC", "Fecha prevista",
             "Recibido", "Diferencias"]
        rows = [[r.id, r.product_code, r.cantidad, r.fecha_necesidad, r.origen, r.estado, r.proveedor, r.numero_oc,
                 r.fecha_prevista, r.cantidad_recibida, r.diferencias] for r in s.execute(select(PurchaseRequest)).scalars()]
    elif entidad == "produccion":
        h = ["#", "Producto", "Cantidad", "OV", "Fecha requerida", "Estado", "Línea", "Programada", "Inicio", "Fin"]
        rows = [[r.id, r.product_code, r.cantidad, r.order.numero if r.order else "", r.fecha_requerida, r.estado,
                 r.line_code, r.fecha_programada, r.inicio_ts, r.fin_ts] for r in s.execute(select(ProductionRequest)).scalars()]
    elif entidad == "liquidaciones":
        h = ["Documento", "Producto", "Lote", "Planificada", "Completada", "Recibida", "Diferencia", "Estado", "Merma MP kg",
             "Merma granel kg", "Origen"]
        rows = [[l.numero_documento, l.product_code, l.lote, l.cantidad_planificada, l.cantidad_completada,
                 l.cantidad_recibida, l.diferencia, l.estado, l.merma_mp_kg, l.merma_granel_kg, l.origen]
                for l in s.execute(select(Liquidation)).scalars()]
    elif entidad == "incidencias":
        h = ["#", "Fecha", "Tipo", "OV", "Ruta", "Descripción", "Estado"]
        rows = [[i.id, i.ts, i.tipo, i.order.numero if i.order else "", i.route_id, i.descripcion, i.estado]
                for i in s.execute(select(Incident)).scalars()]
    elif entidad == "rutas":
        h = ["Ruta", "Fecha", "Zona", "Unidad", "Conductor", "Externo", "Estado", "Kg", "OV", "Estado parada", "Entrega"]
        rows = []
        for r in s.execute(select(Route)).scalars():
            for st in r.stops:
                rows.append([r.id, r.fecha, r.zona, r.vehicle.placa if r.vehicle else "", r.driver.nombre if r.driver else "",
                             r.requiere_externo, r.estado, st.peso_kg, st.order.numero, st.estado, st.entrega_ts])
    elif entidad == "calidad":
        h = ["#", "Fecha", "Formato", "Código", "Producto", "Lote", "Resultado", "Observaciones", "Datos"]
        rows = [[q.id, q.fecha, q.formato, q.codigo_formato, q.product_code, q.lote, q.resultado, q.observaciones, q.datos]
                for q in s.execute(select(QualityRecord)).scalars()]
    else:
        h, rows = [], []
    return h, rows
