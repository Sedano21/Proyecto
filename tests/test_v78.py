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
