"""Depuración de datos personales (Ley 29733): fotos de entrega más antiguas que la retención configurada.
El plazo ('retencion_datos_personales_dias') lo fija la organización con su asesoría legal; vacío = no se depura."""
import os
from datetime import datetime, timedelta

from sqlalchemy import select

from ..db import db
from ..models import RouteStop
from .core import audit, param


def purge_photos(upload_dir, aplicar=False, ahora=None):
    dias = param("retencion_datos_personales_dias")
    if not dias:
        return {"estado": "retención no configurada: no se depura nada"}
    limite = (ahora or datetime.now()) - timedelta(days=int(dias))
    candidatos = []
    for st in db().execute(select(RouteStop).where(RouteStop.entrega_ts.is_not(None), RouteStop.entrega_ts < limite)).scalars():
        if st.foto_path:
            candidatos.append(st)
    borrados = 0
    if aplicar:
        base = os.path.realpath(upload_dir)
        for st in candidatos:
            ruta = os.path.realpath(os.path.join(upload_dir, os.path.basename(st.foto_path)))
            if ruta.startswith(base + os.sep) and os.path.exists(ruta):
                os.remove(ruta)
                borrados += 1
            st.foto_path = ""
        audit(None, "DEPURACION_FOTOS", "RouteStop", "", {"limite": limite.isoformat(), "registros": len(candidatos),
                                                          "archivos": borrados})
    return {"limite": limite.date().isoformat(), "registros": len(candidatos), "archivos_borrados": borrados,
            "aplicado": aplicar}
