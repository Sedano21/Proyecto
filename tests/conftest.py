import os
import sys
import tempfile
from datetime import date, timedelta

import pytest

os.environ.setdefault("PASSWORD_HASH_METHOD", "pbkdf2:sha256:1000")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.db import SessionLocal  # noqa: E402


@pytest.fixture()
def app():
    """Base nueva por prueba. Con TEST_DATABASE_URL (p. ej. PostgreSQL) se recrea el esquema en esa base."""
    d = tempfile.mkdtemp(prefix="opstest_")
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{d}/test.db"
    if os.environ.get("TEST_DATABASE_URL"):
        from app.db import Base, init_engine
        from app import models  # noqa: F401
        eng = init_engine(url)
        Base.metadata.drop_all(eng)
    app = create_app({"DATABASE_URL": url, "TESTING": True, "UPLOAD_DIR": d, "DEMO_MODE": True})
    with app.app_context():
        from app.seed import seed_catalogs, seed_demo
        seed_catalogs()
        seed_demo(os.path.join(d, "demo"))
        # el corte de las 12:00 para despachar mañana depende de la hora en que corren las pruebas: se desactiva aquí y
        # se prueba con hora fija en test_ronda_23oct.py
        from app.services.core import set_param
        set_param("hora_corte_ov_dia_siguiente", "")
        SessionLocal().commit()
        yield app
        SessionLocal.remove()


@pytest.fixture()
def s(app):
    return SessionLocal()


@pytest.fixture()
def U(s):
    """Acceso a usuarios demo por nombre de usuario."""
    from app.models import User

    def get(username):
        return s.query(User).filter_by(username=username).one()
    return get


@pytest.fixture()
def cust(s):
    from app.models import Customer

    def get(ruc="20000000001"):
        return s.query(Customer).filter_by(ruc=ruc).one()
    return get


@pytest.fixture()
def today():
    return date.today()


@pytest.fixture()
def new_order(s, U, cust, today):
    from app.services.orders import create_order
    counter = {"n": 0}

    def make(lines, ruc="20000000001", dias=3, user="coord.ventas", urgente=False, vendedor="vendedor1", precio=999.0):
        """precio: precio de venta de cada línea (por defecto sobre cualquier mínimo de lista, para no detener la OV)."""
        counter["n"] += 1
        # una OV con fecha pasada ya no se registra (obs. demo v0.7): se simula el paso del tiempo sobre una OV de hoy
        o = create_order(U(user), f"T-{counter['n']:03d}", cust(ruc).id, today + timedelta(days=max(dias, 0)),
                         [{"product_code": c, "cantidad": q, "precio_unitario": precio} for c, q in lines], urgente=urgente,
                         vendedor_id=U(vendedor).id if vendedor else None, oc_archivo="oc_prueba.pdf")
        if dias < 0:
            o.fecha_compromiso = today + timedelta(days=dias)
        s.commit()
        return o
    return make


def alerts_of(s, type_code, entidad_id=None):
    from app.models import Alert
    q = s.query(Alert).filter_by(type_code=type_code)
    if entidad_id is not None:
        q = q.filter_by(entidad_id=str(entidad_id))
    return q.all()
