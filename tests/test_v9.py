"""Respuestas del cuestionario operativo V9 (28-oct-2026) y carga de usuarios por Excel."""
from datetime import date, timedelta

import pytest
from openpyxl import Workbook

from app.services.core import BusinessError

from .conftest import alerts_of

LN = [{"product_code": "PT-905", "cantidad": 5, "precio_unitario": 10}]


def _reg(U, cust, numero):
    from app.services import orders as osvc
    return osvc.create_order(U("asist.ventas"), numero, cust().id, date.today() - timedelta(days=2), LN, regularizacion="x")


def test_regularizacion_sin_guia_no_cierra_y_distribucion_la_adjunta(s, U, cust):
    from app.services import orders as osvc
    o = _reg(U, cust, "V9-1")
    s.flush()
    with pytest.raises(BusinessError, match="guía"):
        osvc.regularize_close(o, U("coord.ventas"), "Salió el sábado")
    assert o.estado == "REGULARIZADA"
    osvc.request_regularization_guide(o, U("asist.ventas"))
    s.flush()
    assert alerts_of(s, "REGULARIZACION_GUIA", o.id)
    with pytest.raises(BusinessError, match="Distribución"):
        osvc.attach_regularization_guide(o, U("aux.almacen"), "T001-9", "g.pdf")
    osvc.attach_regularization_guide(o, U("coord.distribucion"), "t001-9", "g.pdf")
    assert o.regularizacion["guia"]["numero"] == "T001-9"
    osvc.regularize_close(o, U("jefe.ventas"), "Salió el sábado")
    assert o.estado == "REGULARIZADA_CERRADA"


def test_regularizacion_la_registra_el_asistente_pero_no_la_cierra(s, U, cust):
    from app.services import orders as osvc
    o = _reg(U, cust, "V9-2")
    s.flush()
    osvc.attach_regularization_guide(o, U("asist.ventas"), "T001-10", "g.pdf")
    with pytest.raises(BusinessError, match="cierran"):
        osvc.regularize_close(o, U("asist.ventas"), "x")
    osvc.regularize_close(o, U("gerente.comercial"), "x")
    assert o.estado == "REGULARIZADA_CERRADA"


def test_penalidad_vencida_alerta_al_jefe_y_solo_el_desestima(s, U, cust):
    from app.services import penalties as pen
    c = cust()
    p = pen.register(c, U("coord.ventas"), "FECHA_ENTREGA", "Llegó tarde", 120, fecha=date.today() - timedelta(days=8))
    s.flush()
    assert pen.check_overdue(date.today()) >= 1
    s.flush()
    assert alerts_of(s, "PENALIDAD_VENCIDA", p.id)
    with pytest.raises(BusinessError, match="Jefe Comercial"):
        pen.resolve(p, U("coord.ventas"), "DESESTIMADA", comentario="x")
    with pytest.raises(BusinessError, match="por qué"):
        pen.resolve(p, U("jefe.ventas"), "DESESTIMADA")
    pen.resolve(p, U("jefe.ventas"), "DESESTIMADA", comentario="Acuerdo con el cliente")
    assert p.estado == "DESESTIMADA"


def _xlsx(tmp_path, filas):
    wb = Workbook()
    ws = wb.active
    ws.append(["DNI", "APELLIDOS Y NOMBRES", "Área", "Correos", "Rol"])
    for f in filas:
        ws.append(f)
    path = tmp_path / "usuarios.xlsx"
    wb.save(path)
    return str(path)


def test_carga_de_usuarios_por_excel(s, U, tmp_path):
    from app.models import User
    from app.services.users_import import import_users
    path = _xlsx(tmp_path, [
        ["00000001", "PEREZ GOMEZ ANA", "Ejecutivo Comercial", "aperez@corporacionproductiva.com", "EJECUTIVO_VENTAS"],
        ["00000002", "RIOS LUIS", "Facturación", "lrios@corporacionproductiva.com", "Facturación"],
        ["00000003", "SOTO EVA", "Marketing", "esoto@corporacionproductiva.com", ""],
        ["00000004", "DIAZ JUAN", "Tesorería", "jdiaz@corporacionproductiva", "COORD_FINANZAS"],
        ["00000005", "LUNA PIA", "Compras", "pluna@otro.com", "COMPRAS"],
    ])
    with pytest.raises(BusinessError, match="Sistemas"):
        import_users(U("coord.ventas"), path)
    r = import_users(U("sistemas"), path)
    assert len(r["creados"]) == 2 and len(r["sin_rol"]) == 1 and len(r["errores"]) == 2
    u = s.query(User).filter_by(email="aperez@corporacionproductiva.com").one()
    assert u.username == "aperez" and u.role_code == "EJECUTIVO_VENTAS" and u.nombre == "Perez Gomez Ana"
    assert u.debe_cambiar_clave and not hasattr(u, "dni")
    r2 = import_users(U("sistemas"), path)  # volver a cargar no duplica
    assert not r2["creados"] and s.query(User).filter_by(email="aperez@corporacionproductiva.com").count() == 1
