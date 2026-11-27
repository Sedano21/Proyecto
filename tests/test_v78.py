"""V78 (27-nov-2026): en Asistencia, el Jefe de Mantenimiento ve a su personal con usuario en el sistema (técnicos de
mantenimiento y personal de limpieza) sin darlo de alta a mano. Solo datos ficticios."""
from .test_v64 import _cliente

ROLES_MANT = ("TECNICO_MANTENIMIENTO", "PERSONAL_LIMPIEZA")


def _usuarios_mant(s):
    from app.models import User
    return s.query(User).filter(User.role_code.in_(ROLES_MANT)).all()


def test_jefe_de_mantenimiento_ve_a_tecnicos_y_limpieza(app, s, U):
    from app.services import attendance as asvc
    assert asvc.sincronizar_usuarios(None) > 0
    s.commit()
    vistos = asvc.workers_of(U("jefe.mantenimiento"), ver=True)
    ligados = {w.user_id for w in vistos}
    usuarios = _usuarios_mant(s)
    assert usuarios and all(u.id in ligados for u in usuarios if u.activo)
    assert all(w.area == "Mantenimiento" for w in vistos)
    # también los que registra (no solo los que ve)
    assert {w.user_id for w in asvc.workers_of(U("jefe.mantenimiento"))} >= {u.id for u in usuarios if u.activo}


def test_pantalla_de_asistencia_del_jefe_de_mantenimiento(app, s, U):
    html = _cliente(app, "jefe.mantenimiento").get("/produccion/asistencia").get_data(as_text=True)
    for u in _usuarios_mant(s):
        assert " ".join(u.nombre.split()).upper() in html
    # Producción no ve al personal de Mantenimiento
    html_prod = _cliente(app, "jefe.produccion").get("/produccion/asistencia").get_data(as_text=True)
    assert all(" ".join(u.nombre.split()).upper() not in html_prod for u in _usuarios_mant(s))


def test_no_duplica_y_liga_al_colaborador_existente(app, s, U):
    from app.models import Worker
    from app.services import attendance as asvc
    u = U("tecnico.mant1")
    previo = Worker(nombre=" ".join(u.nombre.split()).upper(), area="Mantenimiento", puesto="Técnico de mantenimiento")
    s.add(previo)
    s.commit()
    asvc.sincronizar_usuarios(None)
    asvc.sincronizar_usuarios(None)
    s.commit()
    del_usuario = s.query(Worker).filter(Worker.user_id == u.id).all()
    assert [w.id for w in del_usuario] == [previo.id]  # se ligó el que existía, sin crear otro
    assert s.query(Worker).filter(Worker.nombre == previo.nombre).count() == 1
    assert asvc.sincronizar_usuarios(None) == 0  # ya está al día: no cambia nada


def test_usuario_desactivado_deja_de_figurar_y_vuelve_al_reactivarse(app, s, U):
    from app.models import Worker
    from app.services import attendance as asvc
    asvc.sincronizar_usuarios(None)
    u = U("limpieza1")
    u.activo = False
    asvc.sincronizar_usuarios(None)
    s.commit()
    w = s.query(Worker).filter(Worker.user_id == u.id).one()
    assert not w.activo
    assert w.id not in {x.id for x in asvc.workers_of(U("jefe.mantenimiento"), activos=True)}
    u.activo = True
    asvc.sincronizar_usuarios(None)
    s.commit()
    assert s.get(Worker, w.id).activo


def test_baja_manual_del_jefe_se_respeta(app, s, U):
    """Si el jefe da de baja al colaborador a mano, la sincronización no lo vuelve a activar."""
    from app.models import Worker
    from app.services import attendance as asvc
    asvc.sincronizar_usuarios(None)
    s.commit()
    u = U("tecnico.mant2")
    w = s.query(Worker).filter(Worker.user_id == u.id).one()
    asvc.save_worker(U("jefe.mantenimiento"), {"nombre": w.nombre, "puesto": w.puesto, "activo": "0"}, w)
    s.commit()
    asvc.sincronizar_usuarios(None)
    s.commit()
    assert not s.get(Worker, w.id).activo


def test_sin_configuracion_no_hace_nada(app, s):
    from app.models import Worker
    from app.services import attendance as asvc
    from app.services.core import set_param
    set_param("asistencia_roles_por_area", {})
    s.commit()
    assert asvc.sincronizar_usuarios(None) == 0
    assert s.query(Worker).filter(Worker.user_id.isnot(None)).count() == 0


def test_muestra_usuario_y_rol(app, s, U):
    html = _cliente(app, "jefe.mantenimiento").get("/produccion/asistencia").get_data(as_text=True)
    for u in _usuarios_mant(s):
        assert f"Usuario: <b>{u.username}</b>" in html and u.role.nombre in html  # el rol va en la columna de puesto


def test_nombre_y_rol_siguen_al_usuario(app, s, U):
    from app.models import Worker
    from app.services import attendance as asvc
    asvc.sincronizar_usuarios(None)
    s.commit()
    u = U("tecnico.mant1")
    u.nombre = "Técnico Demo Renombrado"
    asvc.sincronizar_usuarios(None)
    s.commit()
    w = s.query(Worker).filter(Worker.user_id == u.id).one()
    assert w.nombre == "TÉCNICO DEMO RENOMBRADO" and w.puesto == u.role.nombre


def _opciones(html, nombre_select):
    import re
    m = re.search(r'<select name="' + nombre_select + r'"[^>]*>(.*?)</select>', html, re.S)
    return m.group(1) if m else ""


def test_trabajos_ofrece_tecnicos_con_usuario(app, s, U):
    html = _cliente(app, "jefe.mantenimiento").get("/planta/trabajos").get_data(as_text=True)
    ops = _opciones(html, "asignado_worker_id")
    for u in _usuarios_mant(s):
        if u.role_code == "TECNICO_MANTENIMIENTO":
            assert f"({u.username})" in ops
        else:
            assert f"({u.username})" not in ops  # el personal de limpieza no se ofrece para trabajos


def test_limpieza_ofrece_personal_de_limpieza_con_usuario(app, s, U):
    html = _cliente(app, "jefe.mantenimiento").get("/planta/limpieza").get_data(as_text=True)
    ops = _opciones(html, "worker_id")
    for u in _usuarios_mant(s):
        if u.role_code == "PERSONAL_LIMPIEZA":
            assert f"({u.username})" in ops
        else:
            assert f"({u.username})" not in ops  # los técnicos no se ofrecen para asignar zonas


def test_asignar_trabajo_y_zona_al_personal_con_usuario(app, s, U):
    """Flujo completo: el trabajo y la limpieza asignados le aparecen al técnico y a la persona en su propia vista."""
    from datetime import date
    from app.models import Worker
    from app.services import attendance as asvc, limpieza as lp, mant_trabajos as mt
    asvc.sincronizar_usuarios(None)
    s.commit()
    jefe, tec, lim = U("jefe.mantenimiento"), U("tecnico.mant1"), U("limpieza1")
    w_tec = s.query(Worker).filter(Worker.user_id == tec.id).one()
    w_lim = s.query(Worker).filter(Worker.user_id == lim.id).one()
    assert w_tec in mt.technicians() and w_lim not in mt.technicians()
    assert w_lim in lp.staff(solo_limpieza=True) and w_tec not in lp.staff(solo_limpieza=True)
    zona = lp.zones()[0]
    lp.assign(jefe, date.today(), w_lim.id, [zona.id])
    s.commit()
    w, mias = lp.mine(lim)
    assert w.id == w_lim.id and [c.zone_id for c in mias] == [zona.id]


def test_verificacion_periodica_sincroniza(app, s):
    from app.models import Worker
    from app.services.scheduler import run_checks
    out = run_checks()
    assert not str(out.get("personal_con_usuario", "")).startswith("error")
    assert s.query(Worker).filter(Worker.user_id.isnot(None), Worker.area == "Mantenimiento").count() >= 4
