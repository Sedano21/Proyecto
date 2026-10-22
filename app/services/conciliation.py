"""Conciliación con SAP durante la marcha blanca en paralelo (respuestas del 22-oct-2026).

Cada carga de SAP (stock, OV, liquidaciones, despachos y facturas; tres cortes al día) se compara con lo registrado en
el módulo. Cualquier diferencia se registra y alerta al área responsable, que la regulariza (corrigió el dato en SAP o en
el módulo) o levanta la observación con su motivo. Cuando no queda ninguna pendiente de la carga, la alerta se cierra.
"""
from collections import defaultdict

from sqlalchemy import select

from ..db import db
from ..models import Role, SapDiscrepancy, now
from . import alerts
from .core import BusinessError, audit, has_perm

AREA = {"STOCK": "Almacén", "OV": "Comercial", "LIQUIDACION": "Producción", "DESPACHO": "Distribución",
        "FACTURA": "Facturación"}
TIPO_ALERTA = {"STOCK": "CONCILIACION_STOCK", "OV": "CONCILIACION_OV", "LIQUIDACION": "CONCILIACION_PRODUCCION",
               "DESPACHO": "CONCILIACION_DESPACHO", "FACTURA": "CONCILIACION_FACTURA"}
ORIGEN_TXT = {"STOCK": "Stock", "OV": "Órdenes de venta", "LIQUIDACION": "Liquidaciones", "DESPACHO": "Despachos (guías)",
              "FACTURA": "Facturas"}


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


class Collector:
    """Acumula las diferencias de una carga y, al cerrar, emite una alerta por área."""

    def __init__(self, batch, user):
        self.batch, self.user, self.items = batch, user, []

    def add(self, origen, referencia, campo, valor_sap, valor_modulo, detalle="", product_code="", lote="", almacen=""):
        d = SapDiscrepancy(origen=origen, area=AREA[origen], upload_id=self.batch.id if self.batch else None,
                           referencia=str(referencia or "")[:80], product_code=product_code or "", lote=lote or "",
                           almacen=almacen or "", campo=campo, valor_sap=_fmt(valor_sap)[:200],
                           valor_modulo=_fmt(valor_modulo)[:200], detalle=detalle)
        db().add(d)
        self.items.append(d)
        return d

    def close(self):
        db().flush()
        por = defaultdict(list)
        for d in self.items:
            por[d.origen].append(d)
        for origen, ds in por.items():
            ejemplos = "; ".join(f"{d.referencia or d.product_code} {d.campo}: SAP {d.valor_sap} / módulo {d.valor_modulo}"
                                 for d in ds[:5])
            alerts.emit(TIPO_ALERTA[origen], f"Conciliación SAP: {len(ds)} diferencia(s) en {ORIGEN_TXT[origen].lower()} "
                        f"(carga #{self.batch.id})",
                        f"{ejemplos}{' …' if len(ds) > 5 else ''}. Regularice o levante cada observación en «Conciliación SAP».",
                        "UploadBatch", self.batch.id, creado_por=self.user, dedup_key=f"CONC:{self.batch.id}:{origen}")
        if self.items:
            audit(self.user, "CONCILIACION_DIFERENCIAS", "UploadBatch", self.batch.id,
                  {o: len(v) for o, v in por.items()})
        return len(self.items)


def can_resolve(user, d):
    if not has_perm(user, "conciliacion.resolver"):
        return False
    if has_perm(user, "vista.total") or user.role_code in ("SISTEMAS", "GERENCIA_GENERAL"):
        return True
    r = db().get(Role, user.role_code)
    area = r.area if r else ""
    # Logística responde también por Almacén; Distribución por los despachos
    return d.area == area or (area == "Logística" and d.area == "Almacén")


def resolve(user, ids, accion, motivo):
    """accion: REGULARIZADA (se corrigió en SAP o en el módulo) o LEVANTADA (la diferencia se explica)."""
    if accion not in ("REGULARIZADA", "LEVANTADA"):
        raise BusinessError("Acción no válida.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise BusinessError("Indique qué se hizo o por qué se levanta la observación.")
    ds = [db().get(SapDiscrepancy, int(i)) for i in ids if str(i).strip()]
    ds = [d for d in ds if d is not None and d.estado == "PENDIENTE"]
    if not ds:
        raise BusinessError("Seleccione al menos una diferencia pendiente.")
    for d in ds:
        if not can_resolve(user, d):
            raise BusinessError(f"Su rol no resuelve diferencias de {d.area}.")
        d.estado, d.motivo, d.resuelto_por, d.resuelto_ts = accion, motivo, user.id, now()
    db().flush()
    for upload_id, origen in {(d.upload_id, d.origen) for d in ds}:
        quedan = db().execute(select(SapDiscrepancy.id).where(SapDiscrepancy.upload_id == upload_id,
                                                              SapDiscrepancy.origen == origen,
                                                              SapDiscrepancy.estado == "PENDIENTE")).first()
        if quedan is None:
            alerts.close_by_system(f"CONC:{upload_id}:{origen}", "Todas las diferencias de la carga fueron atendidas")
    audit(user, f"CONCILIACION_{accion}", "SapDiscrepancy", ",".join(str(d.id) for d in ds), {"motivo": motivo})
    return len(ds)


def listing(estado="PENDIENTE", area="", origen=""):
    q = select(SapDiscrepancy).order_by(SapDiscrepancy.ts.desc(), SapDiscrepancy.id.desc())
    if estado:
        q = q.where(SapDiscrepancy.estado == estado)
    if area:
        q = q.where(SapDiscrepancy.area == area)
    if origen:
        q = q.where(SapDiscrepancy.origen == origen)
    return list(db().execute(q.limit(2000)).scalars())


def summary():
    out = defaultdict(lambda: defaultdict(int))
    for d in db().execute(select(SapDiscrepancy)).scalars():
        out[d.area][d.estado] += 1
    return {a: dict(v) for a, v in out.items()}
