"""Ayudas de presentación sobre los catálogos."""
from ..catalogs import INCIDENT_TYPES, REPACK_TYPES

_REPACK = {c: n for c, n, _ in REPACK_TYPES}
_INC = dict(INCIDENT_TYPES)


def repack_type_name(code):
    return _REPACK.get(code, code)


def incident_type_name(code):
    return _INC.get(code, code)
