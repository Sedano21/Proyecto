"""Ayudas de presentación sobre los catálogos."""
from ..catalogs import INCIDENT_ALIASES, INCIDENT_GROUP, INCIDENT_GROUPS, INCIDENT_TYPES, REPACK_TYPES

_REPACK = {c: n for c, n, _ in REPACK_TYPES}
_INC = dict(INCIDENT_TYPES)


def repack_type_name(code):
    return _REPACK.get(code, code)


def incident_type_name(code):
    code = INCIDENT_ALIASES.get(code, code)
    return _INC.get(code, code)


def incident_group(code):
    return INCIDENT_GROUP.get(INCIDENT_ALIASES.get(code, code), "")


def incident_group_name(code):
    return dict(INCIDENT_GROUPS).get(incident_group(code), "")
