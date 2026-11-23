"""V67 (23-nov-2026): marcha blanca del montacarguista. Varias fotos y ubicación del lote al terminar un movimiento, un
lote en varios lugares, foto en el chat, usuario con perfil adicional («dual») e inicio en sus tareas. Datos ficticios."""
import io

import pytest

from app.models import StockLot
from app.services.core import BusinessError

from .test_v64 import _cliente


def test_lote_en_varias_ubicaciones(s, U):
    from app.services import v30
    lot = s.query(StockLot).filter(StockLot.cantidad >= 10).first()
    v30.set_location(U("montacarguista"), lot, "A-01-2: 4; b-03-1: 3")
    assert lot.ubicaciones == [{"ubicacion": "A-01-2", "cantidad": 4.0}, {"ubicacion": "B-03-1", "cantidad": 3.0}]
    s.flush()
    assert "A-01-2: 4" in lot.ubicacion and "B-03-1" in v30.ubicaciones_usadas()
    with pytest.raises(BusinessError):
        v30.set_location(U("montacarguista"), lot, f"A-01: {lot.cantidad + 100}; B-02: 1")
    v30.set_location(U("montacarguista"), lot, "C-05")
    assert lot.ubicacion == "C-05" and lot.ubicaciones == []


def test_terminar_movimiento_con_varias_fotos_y_ubicacion(s, U):
    from app.services import supply
    mc = U("montacarguista")
    lot = s.query(StockLot).filter(StockLot.cantidad > 0).first()
    m = supply.request_move(mc, "PATIO", "RACK B", equipo=[str(mc.id)])  # el montacarguista registra su propia tarea
    supply.start_move(mc, m, "ini.jpg")
    with pytest.raises(BusinessError, match="foto de validación"):
        supply.finish_move(mc, m, "")
    supply.finish_move(mc, m, "fin.jpg", "", ["vacio.jpg", "firma.jpg"], lot.id, "B-02-1")
    assert m.estado == "COMPLETADA" and m.fotos == ["vacio.jpg", "firma.jpg"] and lot.ubicacion == "B-02-1"


def test_chat_con_foto(app, s, U):
    from app.models import ChatMessage
    c = _cliente(app, "montacarguista")
    para = U("lider.almacen")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    c.post("/chat/", data={"para_id": para.id, "texto": "", "foto": (io.BytesIO(png), "foto.png")},
           content_type="multipart/form-data")
    m = s.query(ChatMessage).order_by(ChatMessage.id.desc()).first()
    assert m is not None and m.archivo.startswith("chat_") and m.texto == "(foto)"


def test_usuario_dual_y_inicio_en_tareas(app, s, U):
    import app.catalogs as cat
    from app.services.core import has_perm
    mc = U("montacarguista")
    propio = {p[0] for p in cat.ROLE_PERMISSIONS["MONTACARGUISTA"]}
    del_chofer = next(p[0] for p in cat.ROLE_PERMISSIONS["CONDUCTOR"] if p[0] not in propio)
    assert not has_perm(mc, del_chofer)
    _cliente(app, "sistemas").post("/usuarios", data={"accion": "perfil_adicional", "user_id": mc.id, "roles": ["CONDUCTOR"]})
    s.expire_all()
    assert has_perm(U("montacarguista"), del_chofer)
    r = _cliente(app, "montacarguista").get("/")
    assert r.status_code == 302 and "/movimientos" in r.headers["Location"]
