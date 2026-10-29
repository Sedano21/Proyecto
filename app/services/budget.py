"""Presupuesto del área de Distribución (V12, 29-oct-2026), según el modelo «Presupuesto proyectado – Logística».

- Partidas por categoría y concepto (p. ej. «Gasto de transporte AWT415 – combustible»), con el tipo de vehículo y la
  placa, y el presupuesto de cada mes. Se carga con el mismo Excel del modelo o partida por partida.
- Lo registra el Coordinador de Distribución y lo envía; Administración y Finanzas lo aprueba u observa.
- Gasto real del mes: el registrado a mano por partida y, automáticamente, el de los sistemas del módulo:
  transporte tercero (unidades externas) y mantenimientos de la flota (preventivo, correctivo y revisión técnica por placa).
- Alerta cuando el gasto del periodo llega al porcentaje configurado (75 %) del presupuesto del periodo, y desviaciones
  por partida.
"""
import re
from collections import defaultdict
from datetime import date

from sqlalchemy import select

from ..db import db
from ..models import AreaBudget, BudgetLine, ThirdPartyTransport, VehicleMaintenance, now
from . import alerts
from .core import BusinessError, audit, has_perm, param

MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "SEP": 9, "OCT": 10,
         "NOV": 11, "DIC": 12}


def _fuente(categoria, concepto):
    c = f"{categoria} {concepto}".upper()
    if "EXTERNA" in c or "ALQUILER" in c:
        return "TERCEROS"
    if "REVISI" in c and "TECNICA" in c.replace("É", "E"):
        return "REVISION_TECNICA"
    if "PREVENTIVO" in c:
        return "MANT_PREVENTIVO"
    if "CORRECTIVO" in c:
        return "MANT_CORRECTIVO"
    return "MANUAL"


def get(area, anio, crear=False, user=None):
    b = db().execute(select(AreaBudget).where(AreaBudget.area == area, AreaBudget.anio == anio)).scalars().first()
    if b is None and crear:
        b = AreaBudget(area=area, anio=anio, creado_por=user.id if user else None)
        db().add(b)
        db().flush()
    return b


def _editable(user, b):
    if not has_perm(user, "presupuesto.registrar"):
        raise BusinessError("El presupuesto lo registra el Coordinador de Distribución.")
    if b.estado == "APROBADO":
        raise BusinessError("El presupuesto ya está aprobado: para cambiarlo, Finanzas debe observarlo.")


def import_excel(user, path, anio=None):
    """Carga el modelo de Excel: columnas «Nombre», «Glosa 01», «Glosa 02» y por mes «Ene-26» (presupuesto) y
    «Real Ene» (gasto real). Las filas de categoría (sin montos) agrupan las partidas siguientes."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = next((w for w in wb.worksheets if any("PRESUPUESTO" in str(c or "").upper()
                                                for r in w.iter_rows(max_row=3, max_col=12, values_only=True) for c in r)),
              wb.active)
    filas = list(ws.iter_rows(max_row=400, max_col=40, values_only=True))
    hi = next((i for i, r in enumerate(filas) if r and any(str(c or "").strip().upper() == "NOMBRE" for c in r)), None)
    if hi is None:
        raise BusinessError("No se encontró el encabezado «Nombre» del modelo de presupuesto.")
    cab = [str(c or "").strip() for c in filas[hi]]
    i_nom = next(i for i, c in enumerate(cab) if c.upper() == "NOMBRE")
    i_g1 = next((i for i, c in enumerate(cab) if c.upper().replace(" ", "") == "GLOSA01"), None)
    i_g2 = next((i for i, c in enumerate(cab) if c.upper().replace(" ", "") == "GLOSA02"), None)
    pres, real = {}, {}
    for i, c in enumerate(cab):
        u = c.upper()
        m = re.match(r"^REAL\s+([A-Z]{3})", u)
        if m and m.group(1) in MESES:
            real[i] = MESES[m.group(1)]
            continue
        m = re.match(r"^([A-Z]{3})[-\s]?(\d{2,4})$", u)
        if m and m.group(1) in MESES:
            pres[i] = MESES[m.group(1)]
            if anio is None:
                y = int(m.group(2))
                anio = y + 2000 if y < 100 else y
    if not pres:
        raise BusinessError("No se encontraron columnas de meses (p. ej. «Ene-26»).")
    anio = anio or date.today().year
    b = get("Distribución", anio, True, user)
    _editable(user, b)
    b.lines.clear()  # se reemplazan todas las partidas por las del archivo
    db().flush()
    categoria, n = "", 0

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    for r in filas[hi + 1:]:
        if not r or r[i_nom] in (None, ""):
            continue
        nombre = " ".join(str(r[i_nom]).split())
        p = {str(m): num(r[i]) for i, m in pres.items() if i < len(r)}
        if not any(p.values()):
            categoria = nombre  # fila de categoría
            continue
        rv = {str(m): num(r[i]) for i, m in real.items() if i < len(r) and r[i] not in (None, "")}
        g1 = " ".join(str(r[i_g1] or "").split()) if i_g1 is not None and i_g1 < len(r) else ""
        g2 = " ".join(str(r[i_g2] or "").split()) if i_g2 is not None and i_g2 < len(r) else ""
        placa = g2 if re.match(r"^[A-Z0-9]{3}-?\d{3}$", g2.upper()) else ""
        b.lines.append(BudgetLine(categoria=categoria or "GENERAL", concepto=nombre[:160], glosa=(g1 or g2)[:80],
                                  placa=placa.replace("-", "").upper(), fuente_real=_fuente(categoria, nombre), presupuesto=p,
                                  real=rv))
        n += 1
    b.estado = "BORRADOR"
    b.historial = list(b.historial or []) + [{"evento": "CARGA_EXCEL", "partidas": n, "user": user.nombre,
                                              "ts": now().isoformat(timespec="minutes")}]
    db().flush()
    audit(user, "PRESUPUESTO_CARGADO", "AreaBudget", b.id, {"anio": anio, "partidas": n})
    return b


def save_line(user, b, datos, line=None):
    _editable(user, b)
    if not (datos.get("concepto") or "").strip():
        raise BusinessError("Indique el concepto de la partida.")
    p = {}
    for m in range(1, 13):
        v = datos.get(f"m{m}")
        if v not in (None, ""):
            try:
                p[str(m)] = float(v)
            except ValueError:
                raise BusinessError(f"Monto inválido en el mes {m}.")
    if line is None:
        line = BudgetLine()
        b.lines.append(line)
    line.categoria = (datos.get("categoria") or "GENERAL").strip()[:80]
    line.concepto = datos["concepto"].strip()[:160]
    line.glosa = (datos.get("glosa") or "").strip()[:80]
    line.placa = (datos.get("placa") or "").replace("-", "").strip().upper()[:20]
    line.fuente_real = datos.get("fuente_real") or _fuente(line.categoria, line.concepto)
    line.presupuesto = p
    db().add(line)
    db().flush()
    return line


def register_real(user, line, mes, monto):
    if not has_perm(user, "presupuesto.registrar"):
        raise BusinessError("El gasto real lo registra el Coordinador de Distribución.")
    r = dict(line.real or {})
    r[str(int(mes))] = float(monto)
    line.real = r
    audit(user, "PRESUPUESTO_REAL", "BudgetLine", line.id, {"mes": mes, "monto": monto})
    return line


def submit(user, b):
    _editable(user, b)
    if not b.lines:
        raise BusinessError("El presupuesto no tiene partidas.")
    b.estado = "ENVIADO"
    b.historial = list(b.historial or []) + [{"evento": "ENVIADO", "user": user.nombre, "ts": now().isoformat(timespec="minutes")}]
    alerts.emit("PRESUPUESTO_POR_APROBAR", f"Presupuesto {b.area} {b.anio} por aprobar",
                f"Total anual S/ {total(b)['presupuesto']:,.2f} en {len(b.lines)} partidas.", "AreaBudget", b.id,
                dedup_key=f"PRES_APROB:{b.id}:{len(b.historial)}", creado_por=user)
    audit(user, "PRESUPUESTO_ENVIADO", "AreaBudget", b.id)
    return b


def decide(user, b, aprobar, comentario=""):
    if not has_perm(user, "presupuesto.aprobar"):
        raise BusinessError("El presupuesto lo aprueba Administración y Finanzas.")
    if b.estado != "ENVIADO":
        raise BusinessError("El presupuesto no está enviado para aprobación.")
    if not aprobar and not (comentario or "").strip():
        raise BusinessError("Indique la observación.")
    b.estado = "APROBADO" if aprobar else "OBSERVADO"
    b.aprobacion = {"aprobado": aprobar, "user": user.nombre, "ts": now().isoformat(timespec="minutes"),
                    "comentario": (comentario or "").strip()}
    b.historial = list(b.historial or []) + [{"evento": b.estado, "user": user.nombre, "comentario": comentario,
                                              "ts": now().isoformat(timespec="minutes")}]
    alerts.close_by_system(f"PRES_APROB:{b.id}:{len(b.historial) - 1}", b.estado.lower())
    audit(user, "PRESUPUESTO_" + b.estado, "AreaBudget", b.id, b.aprobacion)
    return b


def _auto_real(anio):
    """Gasto real que el módulo ya conoce, por fuente, placa y mes."""
    out = defaultdict(float)  # (fuente, placa, mes) -> S/
    for t in db().execute(select(ThirdPartyTransport).where(ThirdPartyTransport.estado.notin_(("RECHAZADO", "POR_APROBAR")))).scalars():
        f = t.fecha_servicio or t.ts.date()
        if f.year == anio and t.monto:
            out[("TERCEROS", "", f.month)] += t.monto
    for m in db().execute(select(VehicleMaintenance)).scalars():
        if m.fecha.year == anio and m.costo:
            fuente = "REVISION_TECNICA" if "REVISI" in (m.descripcion or "").upper() else \
                ("MANT_PREVENTIVO" if m.tipo == "PREVENTIVO" else "MANT_CORRECTIVO")
            out[(fuente, (m.vehicle.placa if m.vehicle else "").replace("-", "").upper(), m.fecha.month)] += m.costo
    return out


def line_real(line, mes, auto):
    manual = float((line.real or {}).get(str(mes)) or 0)
    if line.fuente_real == "MANUAL":
        return manual
    a = auto.get((line.fuente_real, line.placa, mes), 0.0) if line.fuente_real != "TERCEROS" else 0.0
    return manual + a


def total(b):
    return {"presupuesto": sum(sum((l.presupuesto or {}).values()) for l in b.lines)}


def consumption(b, hasta_mes=None):
    """Presupuesto vs real por partida, por categoría y total, acumulado al mes indicado (por defecto el actual)."""
    hasta_mes = hasta_mes or (date.today().month if date.today().year == b.anio else 12)
    auto = _auto_real(b.anio)
    filas, cat = [], defaultdict(lambda: {"presupuesto": 0.0, "real": 0.0})
    for l in b.lines:
        p = sum(float((l.presupuesto or {}).get(str(m)) or 0) for m in range(1, hasta_mes + 1))
        r = sum(line_real(l, m, auto) for m in range(1, hasta_mes + 1))
        filas.append({"line": l, "presupuesto": round(p, 2), "real": round(r, 2),
                      "pct": round(100 * r / p, 1) if p else None, "anual": round(sum((l.presupuesto or {}).values()), 2)})
        cat[l.categoria]["presupuesto"] += p
        cat[l.categoria]["real"] += r
    # terceros: el gasto real del módulo se compara con todas las partidas de unidades externas juntas
    terceros_auto = sum(v for (f, _, m), v in auto.items() if f == "TERCEROS" and m <= hasta_mes)
    if terceros_auto:
        cats_ext = {l.categoria for l in b.lines if l.fuente_real == "TERCEROS"}
        destino = next(iter(cats_ext), "DISTRIBUCIÓN CON UNIDADES EXTERNAS")
        cat[destino]["real"] += terceros_auto
    tp = sum(x["presupuesto"] for x in cat.values())
    tr = sum(x["real"] for x in cat.values())
    return {"hasta_mes": hasta_mes, "filas": filas, "terceros_modulo": round(terceros_auto, 2),
            "categorias": [{"categoria": k, "presupuesto": round(v["presupuesto"], 2), "real": round(v["real"], 2),
                            "pct": round(100 * v["real"] / v["presupuesto"], 1) if v["presupuesto"] else None}
                           for k, v in cat.items()],
            "presupuesto": round(tp, 2), "real": round(tr, 2), "pct": round(100 * tr / tp, 1) if tp else None}


def check_consumption(hoy=None):
    """Alerta al llegar al «presupuesto_alerta_pct» (75 %) del presupuesto acumulado del periodo, total y por categoría."""
    hoy = hoy or date.today()
    umbral = float(param("presupuesto_alerta_pct", 75) or 75)
    n = 0
    for b in db().execute(select(AreaBudget).where(AreaBudget.anio == hoy.year, AreaBudget.estado == "APROBADO")).scalars():
        c = consumption(b, hoy.month)
        grupos = [("total", c["presupuesto"], c["real"], c["pct"])] + [(x["categoria"], x["presupuesto"], x["real"], x["pct"])
                                                                        for x in c["categorias"]]
        for nombre, p, r, pct in grupos:
            if pct is not None and pct >= umbral:
                alerts.emit("PRESUPUESTO_CONSUMO", f"Presupuesto de {b.area} {nombre}: {pct} % consumido",
                            f"Gasto S/ {r:,.2f} de S/ {p:,.2f} presupuestados a {hoy:%m/%Y}. "
                            + ("Se superó el presupuesto: revisar y justificar la desviación." if pct >= 100 else
                               "Se recomienda moderar el gasto en lo que resta del periodo."),
                            "AreaBudget", b.id, prioridad="ALTA" if pct >= 100 else "MEDIA",
                            dedup_key=f"PRES_CONS:{b.id}:{nombre}:{hoy:%Y%m}:{'100' if pct >= 100 else 'U'}")
                n += 1
    return n
