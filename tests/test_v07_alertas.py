"""Observaciones al demo v0.6: alertas como tareas (estados, incidencia, designación en la misma área, aprobación
desde la alerta) y visibilidad por área."""
import pytest

from app.services import alert_actions
from app.services import alerts as al
from app.services.core import BusinessError

from .conftest import alerts_of


def test_aviso_informativo_se_reconoce_y_tarea_no(s, U, new_order):
    o = new_order([("PT-905", 10)])
    info = alerts_of(s, "OV_COMPLETA", o.id)[0]
    assert not al.is_task(info)
    with pytest.raises(BusinessError, match="informativas"):
        al.assign(info, U("coord.almacen"), U("aux.almacen").id)
    al.acknowledge(info, U("coord.almacen"))
    assert info.estado == "RECONOCIDA"


def test_designar_solo_en_la_misma_area_y_llega_al_inicio(s, U, new_order):
    o = new_order([("PT-901", 99999)])
    a = alerts_of(s, "OV_FALTANTE", o.id)[0]
    assert al.is_task(a) and a.estado == "PENDIENTE"
    with pytest.raises(BusinessError, match="misma área"):
        al.assign(a, U("coord.almacen"), U("compras").id)
    with pytest.raises(BusinessError, match="responsable"):
        al.attend(a, U("coord.almacen"))  # sin responsable no hay «en ejecución»
    al.assign(a, U("coord.almacen"), U("lider.almacen").id, "Revisar ubicaciones")
    s.flush()
    assert a in al.my_tasks(U("lider.almacen"))
    aviso = alerts_of(s, "TAREA_ASIGNADA")[-1]
    assert U("lider.almacen").id in aviso.usuarios and aviso.entidad_id == str(a.id)
    al.assign(a, U("coord.almacen"), rol="AUX_ALMACEN")  # a un cargo de su área
    assert a.asignado_rol == "AUX_ALMACEN" and a in al.my_tasks(U("aux.almacen"))


def test_incidencia_no_cierra_la_tarea(s, U, new_order):
    o = new_order([("PT-901", 99999)])
    a = alerts_of(s, "OV_FALTANTE", o.id)[0]
    al.take(a, U("coord.almacen"))
    al.attend(a, U("coord.almacen"))
    inc = al.open_incident(a, U("coord.almacen"), "Lote sin etiqueta", "Se separó el lote", U("lider.almacen").id)
    s.flush()
    assert a.estado == "INCIDENCIA" and not al.is_closed(a)
    with pytest.raises(BusinessError, match="incidencia"):
        al.complete(a, U("coord.almacen"), "x", "y")
    al.close_by_system(a.dedup_key, "condición resuelta")
    assert a.estado == "INCIDENCIA"  # el sistema no cierra una tarea con incidencia abierta
    al.resolve_incident(inc, U("lider.almacen"), "Se reetiquetó")
    assert a.estado == "EN_EJECUCION" and inc.estado == "RESUELTA"
    al.complete(a, U("coord.almacen"), "Traslado realizado", "Guía T-1", proceso_pendiente="Recepción en destino")
    assert a.estado == "COMPLETADA" and a.proceso_pendiente == "Recepción en destino"


def test_aprobar_precio_desde_la_alerta_con_motivo(s, U, new_order):
    from app.services.stock import line_reserved
    o = new_order([("PT-905", 10)], precio=0.01)
    a = alerts_of(s, "OV_PRECIO_BAJO_MINIMO", o.id)[0]
    assert alert_actions.can_decide(a) and alert_actions.motivo_obligatorio(a)
    with pytest.raises(BusinessError, match="motivo"):
        alert_actions.decide(a, U("jefe.ventas"), True, "")
    alert_actions.decide(a, U("jefe.ventas"), True, "Cliente estratégico, precio de campaña")
    assert a.estado == "COMPLETADA" and a.resultado == "APROBADA"
    assert not o.retenida_precio and line_reserved(o.lines[0]) == 10  # pasa a evaluación y reserva


def test_desaprobar_precio_mantiene_la_ov_detenida(s, U, new_order):
    o = new_order([("PT-905", 10)], precio=0.01)
    a = alerts_of(s, "OV_PRECIO_BAJO_MINIMO", o.id)[0]
    with pytest.raises(BusinessError, match="motivo"):
        alert_actions.decide(a, U("coord.ventas"), False, "")
    alert_actions.decide(a, U("coord.ventas"), False, "Precio fuera de política")
    assert a.estado == "DESAPROBADA" and o.retenida_precio and "desaprobado" in o.motivo_detencion


def test_tipos_y_visibilidad_por_area(s, U):
    dist = {t.code for t in al.visible_types(U("coord.distribucion"))}
    assert "MERMA_FUERA_PARAMETRO" not in dist and "OV_CAMBIO" in dist and "RUTA_EXTERNO_VALIDAR" in dist
    assert len(al.visible_types(U("gerente.operaciones"))) == len(al.visible_types(U("sistemas")))
    fum = {t.code: t for t in al.visible_types(U("jefe.logistica"))}
    assert "FUMIGACION_PROXIMA" in fum and "GERENCIA_OPERACIONES" in fum["FUMIGACION_PROXIMA"].roles
