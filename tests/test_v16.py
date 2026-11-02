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
    assert GGA in param("parcial_aprobadores") and "GERENCIA_OPERACIONES" not in param("parcial_aprobadores")
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
    # el Jefe la ve y puede atenderla, pero no le suena (va dirigida a la Coordinación)
    assert alerts.can_see(jaf, a) and not alerts.is_direct(jaf, a) and alerts.is_direct(coord, a)
    c = app.test_client()
    login(c, "jefe.finanzas")
    est = c.get("/alertas/estado.json").get_json()
    assert all(not r["tarea"] for r in est["recientes"] if r["id"] == a.id)
    # la Coordinación no la atiende en su plazo: se alerta al Jefe de Administración y Finanzas
    a.creado_ts = datetime.now() - timedelta(days=3)
    s.commit()
    assert check_overdue() >= 1
    av = s.query(Alert).filter_by(type_code="TAREA_INCUMPLIDA", entidad_id=str(a.id)).one()
    assert JAF in av.roles and alerts.is_direct(jaf, av)


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
