"""Ronda del 23-oct-2026 (2): almacenes habilitados, trazabilidad de todo cambio, cuentas por puesto sin «demo», alta de
usuarios por Sistemas, tabla GS1 en Configuración comercial, velocidades y tolerancias en Configuración de Producción,
verificaciones cada minuto con candado."""
from collections import Counter

import pytest
from sqlalchemy import select

from app.services.core import BusinessError, param

from .test_web import csrf, login


def test_cuentas_por_puesto_sin_demo(s):
    from app.models import Driver, User
    users = list(s.execute(select(User)).scalars())
    assert not [u.nombre for u in users if "demo" in u.nombre.lower()]
    n = Counter(u.role_code for u in users)
    # organigrama de Logística: 5 choferes, 5 auxiliares de despacho, 2 supervisores, 2 líderes, 3 montacarguistas,
    # 5 auxiliares de almacén (4 en 1560 y 1 en 1524)
    assert (n["CONDUCTOR"], n["AUX_DESPACHO"], n["SUPERV_ALMACEN"], n["LIDER_ALMACEN"], n["MONTACARGUISTA"],
            n["AUX_ALMACEN"]) == (5, 5, 2, 2, 3, 5)
    assert {u.nombre for u in users if u.role_code == "CONDUCTOR"} == {f"Chofer {i}" for i in range(1, 6)}
    assert s.execute(select(User).filter_by(username="superv.almacen.mp")).scalar_one().almacen == "EXT-002"
    ligados = [d for d in s.execute(select(Driver)).scalars() if d.user_id]
    assert len(ligados) == 5


def test_sync_quita_demo_y_agrega_cuentas(s, U):
    from app.models import User
    from app.seed import add_missing_demo_users, sync_catalogs
    U("jefe.logistica").nombre = "Jefatura de Logística (demo)"
    U("conductor5").username = "conductor5.baja"  # simula una base anterior sin esa cuenta
    s.flush()
    sync_catalogs()
    assert U("jefe.logistica").nombre == "Jefe de Logística"
    assert add_missing_demo_users() == ["conductor5"]
    assert s.execute(select(User).filter_by(username="conductor5")).scalar_one().nombre == "Chofer 5"


def test_sistemas_crea_usuarios_de_cualquier_perfil_y_queda_trazado(app, s):
    from app.models import AuditLog, Role, User
    c = app.test_client()
    login(c, "sistemas")
    html = c.get("/usuarios").get_data(as_text=True)
    for r in s.execute(select(Role)).scalars():
        assert f'value="{r.code}"' in html
    tok = csrf(c, "/usuarios")
    r = c.post("/usuarios", data={"_csrf": tok, "username": "chofer6", "nombre": "Chofer 6", "role_code": "CONDUCTOR",
                                  "email": "", "password": "Clave.Segura2026", "almacen": ""}, follow_redirects=True)
    assert "Usuario guardado" in r.get_data(as_text=True)
    u = s.execute(select(User).filter_by(username="chofer6")).scalar_one()
    assert u.debe_cambiar_clave and u.role_code == "CONDUCTOR"
    # edición: nombre y almacén; el cambio queda con el valor anterior y el nuevo; la contraseña nunca se registra
    r = c.post("/usuarios", data={"_csrf": tok, "id": u.id, "nombre": "Chofer 6 (refuerzo)", "role_code": "CONDUCTOR",
                                  "email": "", "activo": "1", "password": "Otra.Clave2026", "almacen": "ALM-001"},
               follow_redirects=True)
    assert "Usuario guardado" in r.get_data(as_text=True)
    s.expire_all()
    cambios = [a for a in s.execute(select(AuditLog).where(AuditLog.accion == "DATOS_CAMBIO", AuditLog.entidad == "User",
                                                             AuditLog.entidad_id == str(u.id))).scalars()]
    det = cambios[-1].detalle["cambios"]
    assert det["nombre"] == ["Chofer 6", "Chofer 6 (refuerzo)"] and det["almacen"] == ["", "ALM-001"]
    assert det["password_hash"][0] == "***" and "pbkdf2" not in str(det)
    altas = s.execute(select(AuditLog).where(AuditLog.accion == "DATOS_ALTA", AuditLog.entidad == "User")).scalars().all()
    assert altas and "password_hash" not in altas[-1].detalle["valores"]
    assert cambios[-1].user_id == s.execute(select(User).filter_by(username="sistemas")).scalar_one().id
    # la bitácora filtra por usuario y entidad
    assert "Chofer 6 (refuerzo)" in c.get(f"/auditoria?entidad=User&entidad_id={u.id}").get_data(as_text=True)


def test_almacen_no_habilitado_no_se_usa(s):
    from app.models import StockLot, Warehouse
    from app.services import stock
    lot = s.execute(select(StockLot).where(StockLot.warehouse_code == "ALM-001")).scalars().first()
    assert stock.lot_usable(lot)[1] != "Almacén ALM-001 no habilitado en Configuración"
    s.get(Warehouse, "ALM-001").habilitado = False
    s.flush()
    ok, motivo = stock.lot_usable(lot)
    assert not ok and "no habilitado" in motivo
    assert "ALM-001" not in stock.enabled_warehouses()


def test_tabla_gs1_solo_jefe_y_gerente_comercial(app, s, U):
    from app.models import ProductGTIN
    from app.services import parte
    with pytest.raises(BusinessError):
        parte.save_gtin(U("jefe.produccion"), {"gtin": "7750000000017", "product_code": "PT-901"})
    with pytest.raises(BusinessError):
        parte.save_gtin(U("sistemas"), {"gtin": "7750000000017", "product_code": "PT-901"})
    parte.save_gtin(U("gerente.comercial"), {"gtin": "7750000000017", "product_code": "pt-901", "marca": "M"})
    assert s.get(ProductGTIN, "7750000000017").product_code == "PT-901"
    c = app.test_client()
    login(c, "jefe.ventas")
    tok = csrf(c, "/ov/configuracion")
    r = c.post("/ov/configuracion", data={"_csrf": tok, "accion": "gtin_baja", "gtin": "7750000000017"}, follow_redirects=True)
    assert "GTIN retirado" in r.get_data(as_text=True)
    assert s.get(ProductGTIN, "7750000000017") is None
    # Producción la ve en su panel, sin poder cargarla
    c2 = app.test_client()
    login(c2, "jefe.produccion")
    html = c2.get("/produccion/configuracion").get_data(as_text=True)
    assert "solo consulta" in html and 'value="gs1"' not in html
    from app.services.core import has_perm
    assert not has_perm(U("sistemas"), "catalogo.fotos") and has_perm(U("gerente.comercial"), "catalogo.fotos")


def test_velocidades_y_tolerancias_en_panel_de_produccion(app):
    c = app.test_client()
    login(c, "jefe.produccion")
    tok = csrf(c, "/produccion/configuracion")
    r = c.post("/produccion/configuracion", data={
        "_csrf": tok, "accion": "velocidades",
        "maquina": ["CIMBRIA", "r2", "R2", ""], "presentacion": ["", "0.25", "", ""], "valor": ["1800", "38", "45", ""]},
        follow_redirects=True)
    assert "Velocidades nominales guardadas" in r.get_data(as_text=True)
    assert param("velocidad_nominal") == {"CIMBRIA": 1800.0, "R2|0.25": 38.0, "R2": 45.0}
    html = c.get("/produccion/configuracion").get_data(as_text=True)
    assert "kg/h" in html and "und/min" in html
    r = c.post("/produccion/configuracion", data={
        "_csrf": tok, "accion": "tolerancias", "linea": ["TRUER", "R*"], "presentacion": ["", "5"],
        "min_pct": ["90", "99"], "max_pct": ["100", "98"]}, follow_redirects=True)
    assert "mínimo no puede ser mayor" in r.get_data(as_text=True)
    c.post("/produccion/configuracion", data={"_csrf": tok, "accion": "tolerancias", "linea": ["TRUER", "R*"],
                                               "presentacion": ["", "5"], "min_pct": ["90", "97.5"], "max_pct": ["100", "100.5"]})
    from app.services.parte import tolerance_for
    assert tolerance_for("R1", 5)["min_pct"] == 97.5 and tolerance_for("TRUER")["min_pct"] == 90
    # un ejecutivo no entra al panel
    c3 = app.test_client()
    login(c3, "vendedor1")
    assert c3.get("/produccion/configuracion").status_code in (302, 403)


def test_permiso_retirado_una_sola_vez(s):
    from app.models import RolePermission
    from app.seed import sync_catalogs

    def tiene():
        return s.execute(select(RolePermission).filter_by(role_code="SISTEMAS", perm_code="catalogo.fotos")).first() is not None
    s.add(RolePermission(role_code="SISTEMAS", perm_code="catalogo.fotos", origen="DEFINIDO", fuente="base anterior"))
    s.flush()
    sync_catalogs()
    assert not tiene()
    s.add(RolePermission(role_code="SISTEMAS", perm_code="catalogo.fotos", origen="DEFINIDO", fuente="reasignado por Sistemas"))
    s.flush()
    sync_catalogs()
    assert tiene()  # lo que Sistemas vuelve a asignar no se retira de nuevo


def test_candado_de_verificaciones(tmp_path):
    from app.services.scheduler import _lock
    p = str(tmp_path / "v.lock")
    a = _lock(p)
    assert a and _lock(p) is False
    a.close()
    b = _lock(p)
    assert b
    b.close()


def test_carga_stock_solo_almacenes_habilitados(s, U, tmp_path):
    from datetime import date, timedelta
    from app.models import StockLot, Warehouse
    from app.services import uploads as up
    from .test_controles import _stock_file
    s.get(Warehouse, "EXT-002").habilitado = False
    s.flush()
    antes = {(l.lote, l.cantidad) for l in s.query(StockLot).filter_by(warehouse_code="EXT-002")}
    hoy = date.today()
    p = _stock_file(tmp_path, [["PT-905", "QUINUA", "L905Z", "ALM-001", 50, hoy + timedelta(days=300), None, None],
                               ["MP-901", "MP", "LNUEVO", "EXT-002", 70, hoy + timedelta(days=300), None, None],
                               ["MP-901", "MP", "LX", "ALM-NUEVO", 10, hoy + timedelta(days=300), None, None]])
    b = up.create_batch(U("coord.almacen"), "STOCK", p, "st.xlsx")
    r = up.confirm(b, U("coord.almacen"))
    s.flush()
    assert s.query(StockLot).filter_by(lote="L905Z").one().cantidad == 50
    assert not s.query(StockLot).filter_by(lote="LNUEVO").first() and not s.query(StockLot).filter_by(lote="LX").first()
    assert {(l.lote, l.cantidad) for l in s.query(StockLot).filter_by(warehouse_code="EXT-002")} == antes
    assert s.get(Warehouse, "ALM-NUEVO").habilitado is False  # el almacén nuevo queda por habilitar
    assert "no habilitados" in str(r)
