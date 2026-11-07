"""Simulación integral de operaciones — ENTORNO DE PRUEBAS (07-nov-2026).

Infraestructura que protege la información real mientras se generan 14 días de operación ficticia:

- Candado de entorno: solo se ejecuta con la variable SIMULACION_HABILITADA=1 o en modo demostración (DEMO_MODE), y se
  niega si la escritura en SAP está habilitada.
- Registro de cambios: durante una corrida, cada fila que se crea queda en ``sim_records`` (CREADO) y cada fila que ya
  existía y se modifica o elimina guarda sus valores previos (MODIFICADO / ELIMINADO). La limpieza restaura lo previo
  y borra solo lo creado por la simulación, en orden inverso.
- Reloj simulado: las transacciones de cada día se registran con la fecha y hora de ese día, a través de los mismos
  servicios del sistema. El reloj solo cambia en el hilo que ejecuta la simulación; el resto del sistema sigue con la
  hora real.
- Numeración aparte: OV, OC, guías de contingencia y certificados llevan el prefijo «SIM-» y no consumen correlativos.
- Sin salidas externas: mientras exista una simulación cargada no se envían notificaciones push ni correos, ni se
  conecta a SAP (lectura o escritura).
"""
import json
import os
import shutil
import sys
import threading
from datetime import date as _real_date
from datetime import datetime as _real_datetime
from datetime import time as _time
from datetime import timedelta

from sqlalchemy import Date, DateTime, event, inspect, insert, select

from ..db import SessionLocal, db

PREFIJO = "SIM-"
_LOCAL = threading.local()
_CACHE = {"ts": None, "hay": False}


# ------------------------------------------------------------------ estado del hilo
def activo():
    """True en el hilo que está generando la simulación."""
    return getattr(_LOCAL, "run_id", None) is not None


def prefijo():
    return PREFIJO if activo() else ""


def habilitada(app=None):
    """None si la simulación se puede ejecutar en este entorno; si no, el motivo."""
    from flask import current_app
    app = app or current_app
    if os.environ.get("SIMULACION_HABILITADA") != "1" and not app.config.get("DEMO_MODE"):
        return ("La simulación solo se ejecuta en el ENTORNO DE PRUEBAS (variable SIMULACION_HABILITADA=1 o modo "
                "demostración). En producción no está disponible.")
    try:
        from . import sap_sl
        if sap_sl.configured() and sap_sl.write_enabled() is None:
            return "Este entorno tiene la escritura en SAP habilitada: la simulación no se ejecuta aquí."
    except Exception:  # noqa: BLE001
        pass
    return None


def hay_simulacion():
    """True si hay datos de simulación cargados (se consulta como máximo cada 30 s)."""
    if activo():
        return True
    ahora = _real_datetime.now()
    try:
        bind = id(db().get_bind())
    except Exception:  # noqa: BLE001
        bind = None
    if _CACHE["ts"] is None or _CACHE.get("bind") != bind or (ahora - _CACHE["ts"]).total_seconds() > 30:
        _CACHE["bind"] = bind
        from ..models import SimRun
        try:
            _CACHE["hay"] = db().execute(select(SimRun.id).where(SimRun.estado.in_(("GENERANDO", "GENERADA", "FALLIDA")))
                                         ).first() is not None
        except Exception:  # noqa: BLE001  (tabla aún no migrada)
            _CACHE["hay"] = False
        _CACHE["ts"] = ahora
    return _CACHE["hay"]


def _refrescar_cache():
    _CACHE["ts"] = None


def bloqueo_externo():
    """Motivo por el que no se debe salir a sistemas externos (push, correo, SAP), o None."""
    if activo() or hay_simulacion():
        return "Entorno de pruebas con simulación cargada: no se envían notificaciones ni se conecta a SAP."
    return None


# ------------------------------------------------------------------ reloj simulado
class _MetaDate(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _real_date)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _real_date)


class _MetaDateTime(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _real_datetime)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _real_datetime)


def _ahora_sim():
    return getattr(_LOCAL, "ahora", None)


class SimDate(_real_date, metaclass=_MetaDate):
    @classmethod
    def today(cls):
        a = _ahora_sim()
        return _real_date(a.year, a.month, a.day) if a is not None else _real_date.today()


class SimDateTime(_real_datetime, metaclass=_MetaDateTime):
    @classmethod
    def now(cls, tz=None):
        a = _ahora_sim()
        return a if a is not None and tz is None else _real_datetime.now(tz)

    @classmethod
    def today(cls):
        return cls.now()


_PARCHADOS = []
_LOCK = threading.Lock()


def _instalar_reloj():
    """Reemplaza ``date`` y ``datetime`` en los módulos de la aplicación por versiones que, solo en el hilo de la
    simulación, devuelven la fecha simulada. Fuera de ese hilo se comportan igual que las originales."""
    with _LOCK:
        if _PARCHADOS:
            return
        import importlib
        import pkgutil
        import app.services as _srv
        for m in pkgutil.iter_modules(_srv.__path__):  # todos los servicios cargados antes de cambiar el reloj
            try:
                importlib.import_module(f"app.services.{m.name}")
            except Exception:  # noqa: BLE001
                pass
        for nombre, mod in list(sys.modules.items()):
            if not (nombre == "app" or nombre.startswith("app.")) or mod is None:
                continue
            for attr, real, sim in (("date", _real_date, SimDate), ("datetime", _real_datetime, SimDateTime)):
                if getattr(mod, attr, None) is real:
                    setattr(mod, attr, sim)
                    _PARCHADOS.append((mod, attr, real))


def _retirar_reloj():
    with _LOCK:
        while _PARCHADOS:
            mod, attr, real = _PARCHADOS.pop()
            setattr(mod, attr, real)


def fijar_hora(d, h=8, m=0):
    """Mueve el reloj simulado al día d a la hora h:m."""
    _LOCAL.ahora = _real_datetime.combine(_real_date(d.year, d.month, d.day), _time(h % 24, m % 60))


def avanzar(minutos):
    _LOCAL.ahora = _LOCAL.ahora + timedelta(minutes=minutos)


def ahora():
    return _ahora_sim() or _real_datetime.now()


# ------------------------------------------------------------------ registro de cambios
def _clave(obj):
    mapper = inspect(obj).mapper
    vals = mapper.primary_key_from_instance(obj)
    cols = [mapper.get_property_by_column(c).key for c in mapper.primary_key]
    return json.dumps(dict(zip(cols, vals)), default=str)


def _json(v):
    if isinstance(v, _real_datetime):
        return {"__dt": v.isoformat()}
    if isinstance(v, _real_date):
        return {"__d": v.isoformat()}
    return v


def _desde_json(v):
    if isinstance(v, dict) and set(v) == {"__dt"}:
        return _real_datetime.fromisoformat(v["__dt"])
    if isinstance(v, dict) and set(v) == {"__d"}:
        return _real_date.fromisoformat(v["__d"])
    return v


def _excluido(obj):
    from ..models import SimRecord, SimRun
    return isinstance(obj, (SimRun, SimRecord))


def _antes_de_guardar(session, flush_context, instances):
    run = getattr(_LOCAL, "run_id", None)
    if run is None or session.info.get("sim_run") != run:
        return
    creados = session.info.setdefault("sim_creados", set())
    vistos = session.info.setdefault("sim_modificados", set())
    filas = []
    for obj in list(session.dirty) + list(session.deleted):
        if _excluido(obj) or not inspect(obj).has_identity:
            continue
        tabla = obj.__table__.name
        clave = _clave(obj)
        if (tabla, clave) in creados:
            continue
        eliminado = obj in session.deleted
        mapper = inspect(obj).mapper
        previos = {}
        for attr in mapper.column_attrs:
            hist = inspect(obj).attrs[attr.key].history
            if eliminado:
                val = hist.deleted[0] if hist.deleted else (hist.unchanged[0] if hist.unchanged else None)
                previos[attr.key] = _json(val)
            elif hist.deleted:
                previos[attr.key] = _json(hist.deleted[0])
        if not previos:
            continue
        marca = (tabla, clave, "E" if eliminado else "M")
        if marca in vistos:  # ya se guardó el valor original de esta fila; solo se agregan columnas nuevas
            ya = session.info.setdefault("sim_previos", {}).get(marca, set())
            previos = {k: v for k, v in previos.items() if k not in ya}
            if not previos:
                continue
        vistos.add(marca)
        session.info.setdefault("sim_previos", {}).setdefault(marca, set()).update(previos)
        filas.append({"run_id": run, "tabla": tabla, "clave": clave, "accion": "ELIMINADO" if eliminado else "MODIFICADO",
                      "previos": previos})
    if filas:
        session.info.setdefault("sim_pendientes", []).extend(filas)


def _despues_de_guardar(session, flush_context):
    run = getattr(_LOCAL, "run_id", None)
    if run is None or session.info.get("sim_run") != run:
        return
    from ..models import SimRecord
    creados = session.info.setdefault("sim_creados", set())
    filas = session.info.pop("sim_pendientes", [])
    for obj in session.new:
        if _excluido(obj):
            continue
        tabla, clave = obj.__table__.name, _clave(obj)
        creados.add((tabla, clave))
        filas.append({"run_id": run, "tabla": tabla, "clave": clave, "accion": "CREADO", "previos": {}})
    if filas:
        session.connection().execute(insert(SimRecord.__table__), filas)


event.listen(SessionLocal, "before_flush", _antes_de_guardar)
event.listen(SessionLocal, "after_flush", _despues_de_guardar)


class corrida:
    """Contexto de una corrida: activa el registro y el reloj en este hilo."""

    def __init__(self, run_id):
        self.run_id = run_id

    def __enter__(self):
        _instalar_reloj()
        _LOCAL.run_id = self.run_id
        s = db()
        s.info["sim_run"] = self.run_id
        s.info["sim_creados"] = set()
        s.info["sim_modificados"] = set()
        s.info["sim_previos"] = {}
        return self

    def __exit__(self, *exc):
        s = db()
        for k in ("sim_run", "sim_creados", "sim_modificados", "sim_previos", "sim_pendientes"):
            s.info.pop(k, None)
        _LOCAL.run_id = None
        _LOCAL.ahora = None
        _retirar_reloj()
        _refrescar_cache()
        return False


# ------------------------------------------------------------------ archivos de evidencia simulada
def carpeta(upload_dir, run_id):
    return os.path.join(upload_dir, "simulacion", str(run_id))


def evidencia(upload_dir, run_id, nombre="evidencia"):
    """Imagen de muestra rotulada «SIMULACIÓN – ENTORNO DE PRUEBAS» (una por tipo). Devuelve la ruta relativa al
    directorio de cargas, como guardan las fotos los servicios."""
    rel = os.path.join("simulacion", str(run_id), f"{nombre}.png")
    ruta = os.path.join(upload_dir, rel)
    if not os.path.exists(ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (480, 320), (236, 240, 244))
            d = ImageDraw.Draw(img)
            d.rectangle([8, 8, 472, 312], outline=(200, 60, 60), width=6)
            d.text((40, 120), "SIMULACION - ENTORNO DE PRUEBAS", fill=(160, 30, 30))
            d.text((40, 160), f"Evidencia ficticia: {nombre}", fill=(40, 40, 40))
            img.save(ruta)
        except Exception:  # noqa: BLE001
            open(ruta, "wb").close()
    return rel


# ------------------------------------------------------------------ limpieza
def _tabla_modelo():
    from ..db import Base
    return {m.class_.__table__.name: m.class_ for m in Base.registry.mappers}


def limpiar(user=None, upload_dir=None, run_id=None):
    """Elimina SOLO lo que creó la simulación y devuelve a su valor previo lo que modificó. Devuelve un resumen."""
    from ..models import SimRecord, SimRun
    s = db()
    q = select(SimRun).where(SimRun.estado != "LIMPIADA")
    if run_id:
        q = q.where(SimRun.id == int(run_id))
    runs = list(s.execute(q.order_by(SimRun.id.desc())).scalars())
    modelos = _tabla_modelo()
    res = {"corridas": 0, "eliminados": 0, "restaurados": 0, "no_encontrados": 0}
    for run in runs:
        recs = list(s.execute(select(SimRecord).where(SimRecord.run_id == run.id).order_by(SimRecord.id.desc())).scalars())
        # 1) filas existentes: se devuelven a sus valores previos (el más antiguo manda)
        previos = {}
        for r in sorted((r for r in recs if r.accion == "MODIFICADO"), key=lambda r: r.id):
            d = previos.setdefault((r.tabla, r.clave), {})
            for k, v in (r.previos or {}).items():
                d.setdefault(k, v)
        for (tabla, clave), vals in previos.items():
            m = modelos.get(tabla)
            obj = s.get(m, json.loads(clave)) if m else None
            if obj is None:
                res["no_encontrados"] += 1
                continue
            for k, v in vals.items():
                setattr(obj, k, _desde_json(v))
            res["restaurados"] += 1
        s.flush()
        # 2) filas creadas: se borran tabla por tabla en el orden inverso de sus dependencias (primero los hijos) y,
        #    dentro de cada tabla, de la más nueva a la más antigua
        from ..db import Base
        por_tabla = {}
        for r in recs:
            if r.accion == "CREADO":
                por_tabla.setdefault(r.tabla, []).append(r)
        for t in reversed(Base.metadata.sorted_tables):
            m = modelos.get(t.name)
            for r in sorted(por_tabla.get(t.name, []), key=lambda r: -r.id):
                obj = s.get(m, json.loads(r.clave)) if m else None
                if obj is None:
                    continue
                s.delete(obj)
                res["eliminados"] += 1
            s.flush()
        # 3) filas existentes que la simulación eliminó: se vuelven a crear
        for r in recs:
            if r.accion == "ELIMINADO" and modelos.get(r.tabla) is not None:
                m = modelos[r.tabla]
                if s.get(m, json.loads(r.clave)) is None:
                    s.add(m(**{k: _desde_json(v) for k, v in (r.previos or {}).items()}))
                    res["restaurados"] += 1
        s.flush()
        s.query(SimRecord).filter(SimRecord.run_id == run.id).delete()
        run.estado = "LIMPIADA"
        run.limpiado_ts = _real_datetime.now().replace(microsecond=0)
        res["corridas"] += 1
        if upload_dir:
            shutil.rmtree(carpeta(upload_dir, run.id), ignore_errors=True)
    from .core import audit
    audit(user, "SIMULACION_LIMPIADA", "SimRun", ",".join(str(r.id) for r in runs), res)
    _refrescar_cache()
    return res


def ultima():
    from ..models import SimRun
    return db().execute(select(SimRun).order_by(SimRun.id.desc())).scalars().first()


def conteo_por_tabla(run_id):
    from sqlalchemy import func
    from ..models import SimRecord
    q = select(SimRecord.tabla, SimRecord.accion, func.count()).where(SimRecord.run_id == run_id).group_by(
        SimRecord.tabla, SimRecord.accion)
    out = {}
    for t, a, n in db().execute(q):
        out.setdefault(t, {})[a] = n
    return dict(sorted(out.items(), key=lambda kv: -sum(kv[1].values())))


def ids_creados(run_id, tabla):
    """Ids (clave «id») de las filas de una tabla que creó la corrida."""
    from ..models import SimRecord
    out = []
    for c in db().execute(select(SimRecord.clave).where(SimRecord.run_id == run_id, SimRecord.tabla == tabla,
                                                        SimRecord.accion == "CREADO")).scalars():
        v = json.loads(c).get("id")
        if v is not None:
            out.append(int(v))
    return out


__all__ = ["activo", "prefijo", "habilitada", "hay_simulacion", "bloqueo_externo", "corrida", "fijar_hora", "avanzar",
           "ahora", "evidencia", "limpiar", "ultima", "conteo_por_tabla", "ids_creados", "Date", "DateTime"]
