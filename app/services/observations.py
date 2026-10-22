"""Observaciones de los usuarios (marcha blanca, 22-oct-2026): botón «Reportar observación» en cada pantalla y bandeja
para la revisión diaria que prioriza Gerencia General con el equipo de desarrollo."""
from sqlalchemy import select

from ..db import db
from ..models import Observation, now
from . import alerts
from .core import BusinessError, audit, has_perm

TIPOS = {"ERROR": "Algo no funciona", "MEJORA": "Sugerencia de mejora", "DUDA": "Duda de uso"}
CLASIFICACION = {"SIN_CLASIFICAR": "Sin clasificar", "BLOQUEANTE": "Bloqueante (se corrige de inmediato)",
                 "MAYOR": "Mayor (se corrige en la noche)", "MENOR": "Menor (lista de pendientes)",
                 "MEJORA": "Mejora (lista de pendientes)"}
ESTADOS = {"ABIERTA": "Abierta", "EN_CURSO": "En curso", "CORREGIDA": "Corregida", "DESCARTADA": "Descartada"}


def report(user, comentario, url="", pantalla="", tipo="ERROR", impide=False, captura="", version=""):
    comentario = (comentario or "").strip()
    if not comentario:
        raise BusinessError("Describa la observación.")
    if tipo not in TIPOS:
        tipo = "ERROR"
    o = Observation(user_id=user.id, url=(url or "")[:400], pantalla=(pantalla or "")[:200], tipo=tipo,
                    comentario=comentario, captura=captura or "", version=version or "",
                    clasificacion="BLOQUEANTE" if impide else "SIN_CLASIFICAR")
    db().add(o)
    db().flush()
    alerts.emit("OBSERVACION_REPORTADA", f"Observación #{o.id} de {user.nombre}: {comentario[:120]}",
                f"{TIPOS[tipo]}{' · le impide trabajar' if impide else ''}. Pantalla: {pantalla or url}.",
                "Observation", o.id, prioridad="ALTA" if impide else None, creado_por=user)
    audit(user, "OBSERVACION_REPORTADA", "Observation", o.id, {"tipo": tipo, "impide": bool(impide), "url": url})
    return o


def update(user, o, clasificacion=None, estado=None, respuesta=None):
    if not has_perm(user, "observaciones.gestionar"):
        raise BusinessError("Las observaciones las clasifica y atiende Gerencia General con Sistemas.")
    antes = {"clasificacion": o.clasificacion, "estado": o.estado}
    if clasificacion in CLASIFICACION:
        o.clasificacion = clasificacion
    if estado in ESTADOS:
        if estado in ("CORREGIDA", "DESCARTADA") and not ((respuesta or o.respuesta or "").strip()):
            raise BusinessError("Indique la respuesta (qué se corrigió o por qué se descarta).")
        o.estado = estado
        if estado in ("CORREGIDA", "DESCARTADA"):
            o.atendido_por, o.atendido_ts = user.id, now()
    if respuesta is not None:
        o.respuesta = respuesta.strip()
    audit(user, "OBSERVACION_ACTUALIZADA", "Observation", o.id,
          {"antes": antes, "clasificacion": o.clasificacion, "estado": o.estado})
    if o.estado in ("CORREGIDA", "DESCARTADA") and o.user_id:
        alerts.emit("OBSERVACION_REPORTADA", f"Su observación #{o.id} fue {ESTADOS[o.estado].lower()}",
                    o.respuesta, "Observation", o.id, extra_users=[o.user_id], creado_por=user,
                    dedup_key=f"OBS_RESP:{o.id}:{o.estado}")


def listing(user, estado="", clasificacion="", propias=False):
    q = select(Observation).order_by(Observation.ts.desc())
    if propias or not has_perm(user, "observaciones.gestionar"):
        q = q.where(Observation.user_id == user.id)
    if estado:
        q = q.where(Observation.estado == estado)
    if clasificacion:
        q = q.where(Observation.clasificacion == clasificacion)
    return list(db().execute(q.limit(1000)).scalars())
