"""V69 (23-nov-2026): análisis adjuntos al informe de reposición. Fichas ejecutivas en PDF, presentaciones y Excel,
con un título, la familia y un comentario. Los ve quien ve el informe."""
import os
import uuid

from sqlalchemy import select

from ..db import db
from ..models import ReplenishmentAnalysis
from .core import BusinessError, audit, has_perm

EXT = (".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".png", ".jpg", ".jpeg")
PERMS = ("tablero.empresa", "compras.ver", "compras.consolidado")


def _puede(user):
    if not any(has_perm(user, p) for p in PERMS):
        raise BusinessError("Su perfil no ve el informe de reposición.")


def guardar_archivos(files, upload_dir):
    """Guarda los archivos subidos. Devuelve [{"archivo", "nombre"}]. Rechaza los formatos no permitidos."""
    out = []
    for fs in files or []:
        if fs is None or not getattr(fs, "filename", ""):
            continue
        ext = os.path.splitext(fs.filename)[1].lower()
        if ext not in EXT:
            raise BusinessError(f"{fs.filename}: formato no permitido (PDF, PowerPoint, Excel, Word, CSV o imagen).")
        os.makedirs(upload_dir, exist_ok=True)
        name = f"reposicion_{uuid.uuid4().hex[:10]}{ext}"
        fs.save(os.path.join(upload_dir, name))
        out.append({"archivo": name, "nombre": os.path.basename(fs.filename)[:200]})
    return out


def registrar(user, titulo, archivos, familia="", comentario=""):
    _puede(user)
    titulo = (titulo or "").strip()
    if not titulo:
        raise BusinessError("Indique el título del análisis.")
    if not archivos:
        raise BusinessError("Adjunte al menos un archivo.")
    a = ReplenishmentAnalysis(titulo=titulo[:200], familia=(familia or "").strip()[:120],
                              comentario=(comentario or "").strip()[:2000], archivos=list(archivos), user_id=user.id)
    db().add(a)
    db().flush()
    audit(user, "REPOSICION_ANALISIS", "ReplenishmentAnalysis", a.id, {"titulo": a.titulo, "archivos": len(archivos)})
    return a


def retirar(user, a):
    """Lo retira quien lo subió o quien ve el tablero de la empresa."""
    if a.user_id != user.id and not has_perm(user, "tablero.empresa"):
        raise BusinessError("Solo lo retira quien lo subió o la Gerencia.")
    a.vigente = False
    audit(user, "REPOSICION_ANALISIS_RETIRADO", "ReplenishmentAnalysis", a.id, {})


def vigentes():
    return list(db().execute(select(ReplenishmentAnalysis).where(ReplenishmentAnalysis.vigente.is_(True))
                             .order_by(ReplenishmentAnalysis.ts.desc())).scalars())
