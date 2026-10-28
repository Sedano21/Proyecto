"""Informe predeterminado por área y plantillas del informe personalizado (rediseño de informes, 28-oct-2026).

- Informe predeterminado: el informe institucional del área del usuario, disponible sin configurar nada. Si el área no
  tiene un informe propio, su predeterminado es una configuración institucional del informe personalizado.
- Plantillas: configuraciones guardadas del informe personalizado. PERSONAL (solo su dueño) o COMPARTIDA (la publica
  una jefatura para su área). Al abrir una plantilla se vuelven a aplicar las reglas de visibilidad del perfil que la
  usa, de modo que nunca muestra columnas o indicadores que ese perfil no puede ver.
"""
from datetime import datetime

from sqlalchemy import or_, select

from ..db import db
from ..models import ReportTemplate
from .core import BusinessError, audit, has_perm
from .indicators import areas_of

# informe -> metadatos de la cabecera institucional: área, fuentes y limitaciones conocidas
META = {
    "gestion": {"area": "Comercial", "fuentes": "OV del módulo y cargadas desde SAP, facturación, metas registradas",
                "limites": "La facturación se toma de SAP cuando está cargada; si no, de las OV despachadas."},
    "comercial": {"area": "Comercial", "fuentes": "OV, historial de ventas, clientes y listas de precios",
                  "limites": ""},
    "produccion": {"area": "Producción", "fuentes": "Partes de producción, liquidaciones, plan de producción y tabla de "
                                                    "capacidades", "limites": "La correspondencia de los grupos de capacidad con "
                                                    "las líneas del sistema está por confirmar."},
    "almacen": {"area": "Almacén", "fuentes": "Cargas de stock de SAP y movimientos del módulo",
                "limites": "El stock es el de la última carga de SAP autorizada."},
    "distribucion": {"area": "Distribución", "fuentes": "Rutas, paradas, vehículos e incidencias", "limites": ""},
    "reempaque": {"area": "Calidad", "fuentes": "Solicitudes de reempaque y fumigación", "limites": ""},
    "cumplimiento": {"area": "Gestión de personas", "fuentes": "Alertas y tareas, turnos registrados", "limites": ""},
}

# área -> informe predeterminado (nombre de informe) o configuración institucional del informe personalizado
PREDETERMINADO = {
    "Gerencia": "gestion", "Sistemas": "gestion", "Comercial": "gestion", "Producción": "produccion",
    "Almacén": "almacen", "Logística": "almacen", "Distribución": "distribucion", "Calidad": "reempaque",
    "Compras": {"fuente": "compras", "titulo": "Compras nacionales del periodo"},
    "Importaciones": {"fuente": "importaciones", "titulo": "Importaciones del periodo"},
    "Finanzas": {"fuente": "facturas", "titulo": "Facturas y saldos del periodo"},
    "Facturación": {"fuente": "facturas", "titulo": "Facturas del periodo"},
}
ORDEN_AREAS = ("Gerencia", "Comercial", "Producción", "Almacén", "Logística", "Distribución", "Calidad", "Compras",
               "Importaciones", "Finanzas", "Facturación", "Sistemas")


def default_for(user, disponibles, fuentes):
    """{tipo: 'informe'|'personalizado', nombre|config, titulo} o None. disponibles: {nombre: título} que el usuario
    puede abrir; fuentes: fuentes del informe personalizado que puede consultar."""
    areas = areas_of(user)
    for area in ORDEN_AREAS:
        if area not in areas or area not in PREDETERMINADO:
            continue
        x = PREDETERMINADO[area]
        if isinstance(x, str) and x in disponibles:
            return {"tipo": "informe", "nombre": x, "titulo": disponibles[x], "area": area}
        if isinstance(x, dict) and x["fuente"] in fuentes:
            return {"tipo": "personalizado", "config": {"fuente": x["fuente"], "ver": "1"}, "titulo": x["titulo"],
                    "area": area}
    if disponibles:
        k = next(iter(disponibles))
        return {"tipo": "informe", "nombre": k, "titulo": disponibles[k], "area": META.get(k, {}).get("area", "")}
    return None


# ------------------------------------------------------------------------------------------------------- plantillas
CLAVES = ("fuente", "col", "q", "agrupar", "elem", "ind", "tipo_grafico", "medida", "dias")  # «cfg» se agrega al abrir


def config_from_args(args):
    """Configuración guardable a partir de los parámetros del formulario. El periodo se guarda como «últimos N días»
    para que la plantilla sirva en cualquier fecha."""
    from datetime import date
    cfg = {}
    for k in CLAVES:
        v = args.getlist(k) if k in ("col", "elem", "ind") else args.get(k)
        if v:
            cfg[k] = v
    try:
        d1, d2 = args.get("desde"), args.get("hasta")
        if d1:
            cfg["dias"] = ((date.fromisoformat(d2) if d2 else date.today()) - date.fromisoformat(d1)).days
    except ValueError:
        pass
    return cfg


def templates_for(user):
    """Plantillas que el usuario puede usar: las suyas y las compartidas con su área (o con todas, si es Gerencia)."""
    areas = areas_of(user)
    compartidas = ReportTemplate.alcance == "COMPARTIDA"
    if "Gerencia" not in areas:
        compartidas = compartidas & ReportTemplate.area.in_(sorted(areas) or [""])
    q = select(ReportTemplate).where(or_(ReportTemplate.user_id == user.id, compartidas))
    return list(db().execute(q.order_by(ReportTemplate.alcance.desc(), ReportTemplate.nombre)).scalars())


def save_template(user, nombre, cfg, compartir=False, area=""):
    nombre = (nombre or "").strip()
    if not nombre:
        raise BusinessError("Ponga un nombre a la plantilla.")
    if not cfg.get("fuente"):
        raise BusinessError("Elija primero la fuente de datos del informe.")
    alcance = "PERSONAL"
    if compartir:
        if not has_perm(user, "informes.plantillas_compartidas"):
            raise BusinessError("Publican plantillas para el área las jefaturas y coordinaciones.")
        alcance = "COMPARTIDA"
        area = area or sorted(areas_of(user))[0]
        if area not in areas_of(user) and "Gerencia" not in areas_of(user):
            raise BusinessError("Solo puede compartir con su propia área.")
    t = db().execute(select(ReportTemplate).where(ReportTemplate.user_id == user.id, ReportTemplate.nombre == nombre[:80])
                     ).scalars().first()
    if t is None:
        t = ReportTemplate(nombre=nombre[:80], user_id=user.id)
        db().add(t)
    else:
        t.actualizado_ts = datetime.now()
    t.alcance, t.area, t.config = alcance, area if alcance == "COMPARTIDA" else "", dict(cfg)
    db().flush()
    audit(user, "PLANTILLA_INFORME", "ReportTemplate", t.id, {"nombre": t.nombre, "alcance": alcance, "area": t.area})
    return t


def get_template(user, tid):
    t = db().get(ReportTemplate, int(tid))
    if t is None or t not in templates_for(user):
        raise BusinessError("Plantilla no disponible para su perfil.")
    return t


def delete_template(user, tid):
    t = db().get(ReportTemplate, int(tid))
    if t is None or t.user_id != user.id:
        raise BusinessError("Solo quien creó la plantilla puede eliminarla.")
    audit(user, "PLANTILLA_INFORME_ELIMINADA", "ReportTemplate", t.id, {"nombre": t.nombre})
    db().delete(t)
