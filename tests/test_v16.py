"""V16 (02-nov-2026): sin Gerencia de Operaciones (todo pasa al Gerente General Adjunto), Supervisores de Almacén 1560 y
1524, Jefe de Administración y Finanzas con el poder de la Coordinación de Finanzas (y aviso si ésta no atiende),
ejecutivos comerciales en vez de vendedores, avisos en rojo y sonidos por urgencia."""
import os
from datetime import datetime, timedelta

from app import catalogs as C
from app.models import Alert, AlertType, AuditLog, Param, Role, RolePermission, User
from app.services import alerts
from app.services.core import has_perm, param, roles_of

from .test_web import login

GGA, JAF = "GERENTE_GENERAL_ADJUNTO", "JEFE_ADMIN_FINANZAS"


def test_sin_gerencia_de_operaciones_y_sus_funciones_al_gga(s, U):
    assert s.get(Role, "GERENCIA_OPERACIONES") is None
    assert all(r[0] != "GERENCIA_OPERACIONES" for r in C.ROLES)
    gga = U("gerente.adjunto")
    for perm in ("terceros.aprobar", "ov.aprobar_parcial", "compras.aprobar_mayor_volumen"):
        assert has_perm(gga, perm), perm
    # V17: luego el despacho parcial pasó a la Jefatura de Logística o la de Operaciones
    assert "GERENCIA_OPERACIONES" not in param("parcial_aprobadores")
    assert GGA in s.get(AlertType, "TERCERO_POR_APROBAR").roles
    jefes = param("jefe_por_rol")
    assert jefes["JEFE_LOGISTICA"] == [GGA] and jefes[GGA] == ["GERENCIA_GENERAL"] and "GERENCIA_OPERACIONES" not in jefes
    assert s.query(User).filter_by(username="gerente.operaciones").first() is None


def test_base_existente_pasa_usuarios_permisos_alertas_y_parametros_al_gga(s, U):
    from app import seed
    s.add(Role(code="GERENCIA_OPERACIONES", nombre="Gerencia de Operaciones", area="Gerencia"))
    s.flush()
    s.add(RolePermission(role_code="GERENCIA_OPERACIONES", perm_code="terceros.aprobar", origen="DEFINIDO", fuente="x"))
    u = U("coord.ventas")
    u.role_code = "GERENCIA_OPERACIONES"
    t = s.get(AlertType, "TERCERO_POR_APROBAR")
    t.roles = ["GERENCIA_OPERACIONES"]
    a = alerts.emit("TERCERO_POR_APROBAR", "Tercero de prueba", "", "X", 1)
    p = s.get(Param, "jefe_por_rol")
    v = dict(p.valor["v"])
    v["JEFE_LOGISTICA"] = ["GERENCIA_OPERACIONES"]
    v["GERENCIA_OPERACIONES"] = ["GERENCIA_GENERAL"]
    v.pop("COORD_FINANZAS", None)
    p.valor = {"v": v}
    s.commit()
    assert seed._merge_roles() >= 1
    s.commit()
    assert s.get(Role, "GERENCIA_OPERACIONES") is None
    assert U("coord.ventas").role_code == GGA
    assert s.get(AlertType, "TERCERO_POR_APROBAR").roles == [GGA] and s.get(Alert, a.id).roles == [GGA]
    jefes = param("jefe_por_rol")
    assert jefes["JEFE_LOGISTICA"] == [GGA] and jefes[GGA] == ["GERENCIA_GENERAL"] and jefes["COORD_FINANZAS"] == [JAF]
    assert s.query(AuditLog).filter_by(accion="PERFIL_RETIRADO_CATALOGO", entidad_id="GERENCIA_OPERACIONES").count() == 1


def test_supervisores_de_almacen_y_ejecutivos_comerciales(s, U):
    assert s.get(Role, "COORD_ALMACEN").nombre == "Supervisor de Almacén 1560"
    assert s.get(Role, "COORD_ALMACEN_MP").nombre == "Supervisor de Almacén 1524"
    assert s.get(Role, "EJECUTIVO_VENTAS").nombre == "Ejecutivo Comercial"
    assert U("coord.almacen").nombre == "Supervisor de Almacén 1560"
    assert U("coord.almacen.mp").nombre == "Supervisor de Almacén 1524"
    assert U("vendedor1").nombre == "Ejecutivo Comercial 1" and U("vendedor2").nombre == "Ejecutivo Comercial 2"
    assert not any("Coordinador de Almacén" in r[1] or "Coordinación de Almacén" in r[1] for r in C.ROLES)


def test_jefe_de_administracion_y_finanzas(app, s, U):
    from app.services.shifts import check_overdue
    jaf, coord = U("jefe.finanzas"), U("coord.finanzas")
    assert jaf.role_code == JAF and "COORD_FINANZAS" in roles_of(jaf)
    perms_coord = {rp.perm_code for rp in s.query(RolePermission).filter_by(role_code="COORD_FINANZAS")}
    assert perms_coord and all(has_perm(jaf, p) for p in perms_coord)
    a = alerts.emit("CONDICION_PAGO_SOLICITADA", "Condición de pago de prueba", "", "Customer", 1)
    s.commit()
    # V22 (06-nov-2026): el Jefe de Administración y Finanzas solo recibe sus propias alertas (presupuesto superado);
    # las de la Coordinación de Finanzas ni los avisos de escalamiento le llegan
    assert not alerts.can_see(jaf, a) and alerts.is_direct(coord, a)
    a.creado_ts = datetime.now() - timedelta(days=3)
    s.commit()
    check_overdue()
    av = s.query(Alert).filter_by(type_code="TAREA_INCUMPLIDA", entidad_id=str(a.id)).all()
    assert all(JAF not in x.roles for x in av)


def test_avisos_en_rojo_y_sonidos_por_urgencia(app):
    raiz = os.path.join(os.path.dirname(__file__), "..", "app", "static")
    css = open(os.path.join(raiz, "style.css"), encoding="utf-8").read()
    js = open(os.path.join(raiz, "app.js"), encoding="utf-8").read()
    assert ".reco-big.MEDIA{background:linear-gradient(135deg,#b71c1c,#d32f2f);color:#fff}" in css
    assert "PATRONES" in js and "ALTA: [" in js and "BAJA: [" in js and "createDynamicsCompressor" in js
    c = app.test_client()
    login(c, "sistemas")
    html = c.get("/alertas/configuracion").get_data(as_text=True)
    assert "Probar urgente" in html


# ----------------------------------------------------------- correcciones del 02-nov-2026 (servidor)
def test_fechas_aaaammdd_de_la_consulta_de_sap():
    from datetime import date
    from app.services.uploads import _date
    assert _date("20270411") == date(2027, 4, 11) and _date(20270411) == date(2027, 4, 11) and _date("20270411.0") == date(2027, 4, 11)


def test_cliente_del_extranjero(s, U):
    import pytest
    from app.services import customers as csv_
    from app.services.core import BusinessError
    with pytest.raises(BusinessError, match="país"):
        csv_.save_customer(U("coord.ventas"), None, {"ruc": "76.123.456-7", "tipo_documento": "EXTRANJERO", "nombre": "CLIENTE DEMO CL",
                                                     "grupo": "INSTITUCIONAL"})
    c = csv_.save_customer(U("coord.ventas"), None, {"ruc": "76.123.456-7", "tipo_documento": "EXTRANJERO", "pais": "Chile",
                                                     "nombre": "CLIENTE DEMO CL", "grupo": "INSTITUCIONAL"})
    assert c.tipo_documento == "EXTRANJERO" and c.pais == "CHILE" and c.ruc == "76.123.456-7" and not c.ubigeo
    with pytest.raises(BusinessError, match="RUC: 11"):
        csv_.save_customer(U("coord.ventas"), None, {"ruc": "123", "nombre": "X", "grupo": "INSTITUCIONAL", "ubigeo": "150101"})
    from app.services import sap_sl
    assert sap_sl._doc_extranjero({"FederalTaxID": "76.123.456-7", "CardCode": "CE001"}) == "76.123.456-7"
    assert sap_sl._doc_extranjero({"FederalTaxID": "", "CardCode": "ce001"}) == "CE001"


def test_una_verificacion_que_falla_no_detiene_las_demas_ni_a_sap(s, monkeypatch):
    from app.services import scheduler
    llamadas = []

    def falla():
        raise RuntimeError("dato raro")
    pasos = [("sap_service_layer", lambda: llamadas.append("sap") or 1), ("rota", falla), ("otra", lambda: llamadas.append("otra") or 2)]
    monkeypatch.setattr(scheduler, "_pasos", lambda user, today: pasos)
    out = scheduler.run_checks()
    assert llamadas == ["sap", "otra"] and out["rota"].startswith("error: RuntimeError") and out["otra"] == 2


def test_probar_conexion_quita_el_aviso_de_sap(s, monkeypatch):
    from app.services import sap_sl

    class SL:
        def login(self):
            return {"Version": "1000160"}

        def logout(self):
            pass
    sap_sl._set_state(False, "Connection refused")
    s.commit()
    assert sap_sl.connection_state()["ok"] is False
    sap_sl.test_connection(SL())
    assert sap_sl.connection_state()["ok"] is True


def test_ov_de_sap_busca_al_cliente_por_su_codigo_y_no_cae_por_textos_largos(s, U, tmp_path):
    import openpyxl
    from app.models import Customer, SalesOrder
    from app.services import uploads as up
    c = s.query(Customer).first()
    c.codigo_sap = "C-DEMO-1"
    s.commit()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OVS"
    ws.append(["Número de documento", "Estado", "Fecha de Emisión", "Fecha de Vencimiento", "Vendedor", "Ruc", "Código de cliente",
               "Nombre de cliente", "Dirección", "Código de Producto", "Descripción de Producto", "Solicitado", "Moneda"])
    ws.append([77001, "Abierto", "20261102", "20261110", "X" * 300, "000999", "C-DEMO-1", "OTRO NOMBRE", "D" * 400,
               "PT-901", "Producto demo", 5, "SOL"])
    ws.append([77002, "Abierto", "20261102", "20261110", "", "20999999991", "C-NUEVO-9", "CLIENTE DEMO NUEVO " + "Z" * 250,
               "Av. " + "Y" * 400, "PT-901", "Producto demo", 3, "SOL"])
    p = str(tmp_path / "ov.xlsx")
    wb.save(p)
    b = up.create_batch(U("coord.ventas"), "OV", p, "ov.xlsx")
    up.confirm(b, U("coord.ventas"))
    s.commit()
    assert s.query(SalesOrder).filter_by(numero="77001").one().customer_id == c.id
    nuevo = s.query(SalesOrder).filter_by(numero="77002").one().customer
    assert nuevo.codigo_sap == "C-NUEVO-9" and len(nuevo.direccion) == 250 and len(nuevo.nombre) == 200


def test_version_instalada_y_errores_de_base_como_mensaje(app, s, U):
    from sqlalchemy.exc import IntegrityError
    from app.views.common import act
    assert app.config["APP_VERSION"].startswith("1.0.0-mb")
    with app.test_request_context("/"):
        def rompe():
            raise IntegrityError("INSERT", {}, Exception("duplicate key value violates unique constraint"))
        r = act(rompe, "ok", "/")
        assert r.status_code == 302
        from flask import get_flashed_messages
        assert any("rechazó un dato" in m for m in get_flashed_messages())


def test_textos_largos_se_recortan_en_vez_de_rechazar_el_guardado(s):
    from app.models import Customer
    c = s.query(Customer).first()
    c.direccion = "Av. " + "X" * 500
    s.commit()
    s.refresh(c)
    assert len(c.direccion) == 250
