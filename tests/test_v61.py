"""V61 (19-nov-2026): parámetros de lista escritos a mano y tarjetas de la proyección de demanda responsivas."""


def test_lista_escrita_a_mano(app):
    from app.services.core import coerce_param
    assert coerce_param("list", "[ALM-001, ALM-003, EXT-014]") == ["ALM-001", "ALM-003", "EXT-014"]
    assert coerce_param("list", "ALM-001\nALM-002") == ["ALM-001", "ALM-002"]
    assert coerce_param("list", '["PT", "MQ"]') == ["PT", "MQ"]
    assert coerce_param("list", "'A'; 'B'") == ["A", "B"]
    assert coerce_param("list", "1, 2.5") == [1, 2.5]


def test_guardar_almacenes_utilizables_desde_configuracion(app, s, U):
    from app.services.core import param, set_param, coerce_param
    set_param("abastecimiento_almacenes_utilizables", coerce_param("list", "[ALM-001, ALM-003]"), U("sistemas"))
    s.commit()
    assert param("abastecimiento_almacenes_utilizables") == ["ALM-001", "ALM-003"]
