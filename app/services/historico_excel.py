"""V51 (17-nov-2026): cargar el histórico del Excel CONTROL DE PRODUCCION (libro de Producción con muchas pestañas).

Cada pestaña se reconoce por su nombre y su encabezado y va a su lugar en el módulo:
- PROGRAMACION → planeamiento diario (mismas reglas que «Actualizar con Excel»).
- IQ+CIMB, TRUER, SEL. MANUAL, ENV. MANUAL, ENVASADO R1 R2 R3, CANARIO SUMAQ → partes de producción por línea (kg de
  entrada y salida, rendimiento, OF, estado, horas, paradas y su causa, colaboradores y maquinista).
- ASISTENCIA… → colaboradores (por DNI) y su asistencia diaria.
- CONTROL DE MERMA, CONTROL MP-CAL 3, DESMT. Y/O TRANSF., REQ. DE MP, SUMINISTROS y la hoja de OF de SAP → histórico
  de movimientos de Producción (tabla historico_produccion).
- Las pestañas de resumen (REPORTE DE PRODUCCION, DASHBOARD, TABLERO, AdC, tablas dinámicas) y las que el sistema ya
  trae de SAP (OV, STOCK ALM, maestro de artículos, EANS, COD) no se cargan: se informa por qué.
Solo se carga desde «historico_produccion_desde» (1-ene-2026) hasta hoy; las fechas fuera de ese rango (mal digitadas)
se informan. Se puede volver a subir el libro: lo ya cargado no se duplica."""
import hashlib
import json
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from ..db import db
from ..models import Attendance, ProductionHistory, ProductionReport, Worker, now
from . import plan_excel as pe
from .core import BusinessError, audit, has_perm, param

LINEAS = {"iq+cimb": ("CIMBRIA", "SELECCION"), "truer": ("TRUER", "SELECCION"), "sel. manual": ("SEL_MANUAL", "SELECCION"),
          "env. manual": ("ENV_MANUAL", "ENVASADO"), "envasado r1 r2 r3": (None, "ENVASADO"),
          "canario sumaq": (None, "ENVASADO")}
HISTORICO = {"control de merma": "MERMA", "control mp-cal 3": "MP_CAL3", "desmt. yo transf.": "DESMONTAJE",
             "desmt. y/o transf.": "DESMONTAJE", "req. de mp": "REQ_MP", "suministros": "SUMINISTRO"}
NO_SE_CARGAN = {"reporte de produccion": "resumen calculado con fórmulas: el módulo lo calcula con los partes",
                "dashboard": "resumen calculado", "tablero": "resumen calculado (vacío)",
                "adc": "resumen calculado (con celdas #REF!)", "ov": "las OV llegan de SAP",
                "stock alm": "el stock llega de SAP", "eans": "tabla de EAN: se mantiene en Configuración",
                "cod": "maestro de códigos: llega de SAP", "hoja 16": "maestro de artículos: llega de SAP",
                "control externo": "pestaña de apoyo sin encabezado de datos", "req": "asistencia antigua sin fechas (solo L M M J V S)"}
ENV_LINEAS = {"raumak 1": "R1", "raumak 2": "R2", "raumak 3": "R3", "r 1 y 2": "R1", "r1 y r2": "R1", "r1&r2": "R1",
              "r1": "R1", "r2": "R2", "r3": "R3"}
ESTADOS = {"LIQ. EXT.": "LIQ. EXT. LIQUIDADO", "LIQ EXT": "LIQ. EXT. LIQUIDADO"}


def _desde():
    try:
        return date.fromisoformat(str(param("historico_produccion_desde", "2026-01-01") or "2026-01-01")[:10])
    except ValueError:
        return date(2026, 1, 1)


def fecha_x(v):
    """Fecha de Excel: celda de fecha, número de serie de Excel o texto (dd/mm/aaaa, dd.mm.aa)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:
            return date(1899, 12, 30) + timedelta(days=int(v))
        return None
    t = str(v or "").strip().replace(".", "/").replace("-", "/")
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(t[:10], fmt).date()
        except ValueError:
            continue
    return None


def _hora(v):
    if isinstance(v, datetime):
        v = v.time()
    if isinstance(v, time):
        return f"{v:%H:%M}"
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1:
        m = round(v * 24 * 60)
        return f"{m // 60:02d}:{m % 60:02d}"
    return str(v or "").strip()[:8]


def _num(v):
    if isinstance(v, bool) or v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _cab(filas, *obligatorias, maximo=8):
    """Fila del encabezado: la primera (de las primeras «maximo») que tiene todas las columnas obligatorias."""
    for h, fila in enumerate(filas[:maximo]):
        nombres = [pe._norm(c) for c in fila]
        if all(any(n == o or n.startswith(o) for n in nombres) for o in obligatorias):
            return h, nombres
    return None, []


def _idx(nombres, *opciones, todos=False):
    out = [i for i, n in enumerate(nombres) if any(n == o or n.startswith(o) for o in opciones)]
    return out if todos else (out[0] if out else None)


def _pref(nombres, *opciones):
    """Como _idx, pero la prioridad la da el orden de las opciones (la primera opción que exista)."""
    for o in opciones:
        i = _idx(nombres, o)
        if i is not None:
            return i
    return None


def _val(r, i):
    return r[i] if i is not None and i < len(r) else None


def _resumen(hoja, destino):
    return {"hoja": hoja, "destino": destino, "cargadas": 0, "existentes": 0, "sin_producto": 0, "errores": []}


def _error(res, fila, motivo):
    if len(res["errores"]) < 25:
        res["errores"].append({"fila": fila, "motivo": motivo})
    res["n_errores"] = res.get("n_errores", 0) + 1


# ------------------------------------------------------------------ partes por línea
def _linea_env(v):
    t = pe._norm(v)
    if t in ENV_LINEAS:
        return ENV_LINEAS[t]
    try:
        return pe._linea(v) or ""
    except BusinessError:
        return _txt(v)[:20]


def partes_linea(user, ws, titulo, linea_fija, tipo, por_prod, existentes):
    res = _resumen(ws.title, f"Partes de producción · {linea_fija or 'líneas de envasado'}")
    filas = [list(r) for r in ws.iter_rows(values_only=True)]
    h, n = _cab(filas, "fecha", "of")
    if h is None:
        h, n = _cab(filas, "fecha", "lote")
    if h is None:
        _error(res, 0, "No se encontró el encabezado (FECHA, LOTE, OF).")
        return res
    ix = {k: _idx(n, *v) for k, v in {
        "fecha": ("fecha",), "op": ("# op",), "ini": ("hora inicio",), "fin": ("hora fin", "hora final"),
        "turno": ("turno",), "cliente": ("cliente",), "codigo": ("codigo gr", "codigo mp", "codigo"),
        "desc": ("descripcion",), "linea": ("linea",), "lote": ("lote pt", "lote"), "fv": ("f.v.",),
        "present": ("presentacion", "present."), "of": ("of",), "estado": ("estado",), "obs": ("observacion",),
        "nota": ("nota",), "granel": ("granel",), "cal3": ("cal3", "cal 3"), "desm": ("desm.",),
        "total": ("total",), "rend": ("% rend",), "unid": ("total unid",), "mp_total": ("total mp kg", "total mp - kg",
                                                                                      "total  mp - kg"),
        "sobrante": ("sobrante mp",), "saldo": ("saldo",), "horas": ("total hr efectivas", "total hr", "total horas",
                                                                       "t. horas x cola."),
        "horas_col": ("t. horas x cola.",), "inactivo": ("tiempo inactivo",), "refrig": ("refrig",),
        "causa": ("causa",), "parada": ("parada de maq",), "ratio": ("ratio",), "seleccion": ("seleccion",),
        "maquinista": ("maquinista",), "calidad": ("calidad",)}.items()}
    ix["horas"] = _pref(n, "total hr efectivas", "total hr", "total horas", "t. horas x cola.")
    mp_cols = _idx(n, "mp", todos=True)
    desm_cols = _idx(n, "total desmedro", todos=True)
    colab = _idx(n, "colab", "maq. 0", "maq 0", todos=True)
    desde, hoy = _desde(), date.today()
    for k, r in enumerate(filas[h + 1:], start=h + 2):
        fv = _val(r, ix["fecha"])
        if fv in (None, "") or (isinstance(fv, str) and not any(c.isdigit() for c in fv)):
            continue  # separadores de mes («ENERO») y filas vacías
        f = fecha_x(fv)
        if f is None or not (desde <= f <= hoy):
            _error(res, k, f"fecha fuera de rango o mal digitada ({fv if not isinstance(fv, (int, float)) else f or fv})")
            continue
        linea = linea_fija or _linea_env(_val(r, ix["linea"]))
        # producto: código si lo hay; si no, el nombre (columna DESCRIPCION, la que sigue a CODIGO o la primera «MP»)
        code = _txt(_val(r, ix["codigo"])).upper().split(" ")[0] if ix["codigo"] is not None else ""
        nombre = _txt(_val(r, ix["desc"]))
        if not nombre and ix["codigo"] is not None:
            nombre = _txt(_val(r, ix["codigo"] + 1)) if isinstance(_val(r, ix["codigo"] + 1), str) else ""
        if not nombre:
            nombre = next((_txt(r[i]) for i in mp_cols if i < len(r) and isinstance(r[i], str) and r[i].strip()), "")
        if code and code not in por_prod.values():
            code = pe._buscar_producto(por_prod, code) or code
        if not code or code not in por_prod.values():
            code = pe._buscar_producto(por_prod, nombre) or ""
        if not code:
            res["sin_producto"] += 1
        lote, hora_i = _txt(_val(r, ix["lote"]))[:60], _hora(_val(r, ix["ini"]))
        of = _txt(_val(r, ix["of"]))[:30]
        clave = (linea, f, hora_i, lote, of)
        if clave in existentes:
            res["existentes"] += 1
            continue
        mp_kg = next((_num(r[i]) for i in reversed(mp_cols) if i < len(r) and _num(r[i]) is not None), None)
        if tipo == "ENVASADO":
            entrada = _num(_val(r, ix["mp_total"])) or 0.0
            unid = _num(_val(r, ix["unid"]))
            pres = _num(_val(r, ix["present"]))
            salida = (unid or 0) * (pres or 0)
            desm = 0.0
        elif ix["seleccion"] is not None:  # selección manual: entrada, desmedro y saldo; la salida buena es MP
            entrada = _num(_val(r, ix["mp_total"])) or 0.0
            desm = next((_num(r[i]) for i in reversed(desm_cols) if i < len(r) and _num(r[i]) is not None), 0.0) or 0.0
            mp_kg = max(entrada - desm - (_num(_val(r, ix["saldo"])) or 0), 0.0)
            salida, unid, pres = 0.0, None, None
        else:  # selección automática: TOTAL = MP + calidad 3 + desmedro (= lo que entró); la salida buena es MP
            desm = _num(_val(r, ix["desm"])) or 0.0
            cal3 = _num(_val(r, ix["cal3"])) or 0.0
            entrada = _num(_val(r, ix["total"])) or ((mp_kg or 0) + cal3 + desm)
            if mp_kg is None:
                mp_kg = max(entrada - cal3 - desm, 0.0)
            salida, unid, pres = 0.0, None, None
        rend = _num(_val(r, ix["rend"]))
        if rend is not None and rend <= 5:
            rend = rend * 100
        inactivo, refrig = _num(_val(r, ix["inactivo"])), _num(_val(r, ix["refrig"]))
        # «TIEMPO INACTIVO» (horas) incluye el refrigerio: la parada es lo que excede al refrigerio
        parada_h = max((inactivo or 0) - (refrig or 0), 0) + (_num(_val(r, ix["parada"])) or 0)
        personas = []
        for i in colab:
            nom = _txt(_val(r, i))
            if nom and not nom.replace(".", "").isdigit():
                personas.append({"nombre": nom[:120], "rol": "maquinista" if pe._norm(n[i]).startswith("maq") else "colaborador"})
        if ix["seleccion"] is not None and _txt(_val(r, ix["seleccion"])):
            personas.append({"nombre": _txt(_val(r, ix["seleccion"]))[:120], "rol": "seleccion", "kg": entrada,
                             "horas": _num(_val(r, ix["horas_col"]))})
        maquinista = _txt(_val(r, ix["maquinista"])) or next((p["nombre"] for p in personas if p["rol"] == "maquinista"), "")
        estado = _txt(_val(r, ix["estado"])).upper()
        estado = ESTADOS.get(estado, estado) if estado else "LIQUIDADO"
        from .parte import ESTADOS_PARTE
        obs = " · ".join(x for x in (_txt(_val(r, ix["obs"])), _txt(_val(r, ix["nota"]))) if x)
        if estado not in ESTADOS_PARTE:
            obs, estado = (f"Estado en el Excel: {estado}. " + obs).strip(), "LIQUIDADO"
        rep = ProductionReport(
            linea=linea[:20], tipo=tipo, fecha=f, op=_txt(_val(r, ix["op"]))[:20], of=of, turno=_txt(_val(r, ix["turno"]))[:20],
            hora_inicio=hora_i, hora_fin=_hora(_val(r, ix["fin"])), horas=_num(_val(r, ix["horas"])),
            operarios=len([p for p in personas if p["rol"] != "seleccion"]) or None, cliente=_txt(_val(r, ix["cliente"]))[:120],
            product_code=code, lote=lote, peso_entrada_kg=round(entrada, 3), granel_kg=round(salida, 3),
            mp_kg=round(mp_kg or 0, 3) if tipo == "SELECCION" else 0,
            cal3_kg=_num(_val(r, ix["cal3"])) or 0, desmedro_kg=round(desm, 3), presentacion_kg=pres, unidades=unid,
            sobrante_kg=_num(_val(r, ix["sobrante"])) or 0, rendimiento_pct=round(rend, 2) if rend is not None else None,
            desmedro_pct=round(100 * desm / entrada, 2) if entrada and desm else None,
            ratio_kg_hora=_num(_val(r, ix["ratio"])), parada_min=round(parada_h * 60) if parada_h else None,
            motivo_parada=_txt(_val(r, ix["causa"]))[:160], refrigerio_min=round(refrig * 60) if refrig else None,
            estado=estado, observacion=obs, user_id=user.id, maquinista=maquinista[:120],
            fv_pt=fecha_x(_val(r, ix["fv"])), colaboradores=personas,
            indicadores={"origen": "EXCEL CONTROL DE PRODUCCION", "hoja": ws.title, "fila": k, "producto_excel": nombre[:120],
                         "calidad": _txt(_val(r, ix["calidad"]))[:30]})
        db().add(rep)
        existentes.add(clave)
        res["cargadas"] += 1
    db().flush()
    return res


# ------------------------------------------------------------------ asistencia
def asistencia(user, ws):
    res = _resumen(ws.title, "Colaboradores y asistencia")
    filas = [list(r) for r in ws.iter_rows(values_only=True)]
    h, n = _cab(filas, "dni", "colaboradores")
    if h is None:
        _error(res, 0, "No se encontró el encabezado (DNI, COLABORADORES).")
        return res
    i_dni, i_nom, i_lin, i_sub = _idx(n, "dni"), _idx(n, "colaboradores"), _idx(n, "linea"), _idx(n, "sublinea")
    fechas = {j: c.date() if isinstance(c, datetime) else c for j, c in enumerate(filas[h])
              if isinstance(c, (datetime, date))}
    desde, hoy = _desde(), date.today()
    # hasta el último día con alguna asistencia marcada (los días siguientes aún no se llenaron)
    ultimo = max([fechas[j] for r in filas[h + 1:] for j in fechas if j < len(r) and r[j] is True] or [desde])
    nuevos = 0
    for k, r in enumerate(filas[h + 1:], start=h + 2):
        nom = _txt(_val(r, i_nom)).upper()
        dni = _txt(_val(r, i_dni))
        if not nom:
            continue
        w = db().execute(select(Worker).where(Worker.documento == dni)).scalars().first() if dni else None
        w = w or db().execute(select(Worker).where(Worker.nombre == nom)).scalars().first()
        if w is None:
            w = Worker(nombre=nom[:160], documento=dni[:20], area="Producción", activo=True, user_id=user.id)
            db().add(w)
            nuevos += 1
        w.linea = (_txt(_val(r, i_lin)) or w.linea or "")[:20]
        w.sublinea = (_txt(_val(r, i_sub)) or w.sublinea or "")[:40]
        if dni and not w.documento:
            w.documento = dni[:20]
        db().flush()
        ya = {a.fecha for a in db().execute(select(Attendance).where(Attendance.worker_id == w.id)).scalars()}
        for j, f in fechas.items():
            v = _val(r, j)
            if f in ya or not (desde <= f <= min(hoy, ultimo)) or v not in (True, False):
                continue
            if v is False and f.weekday() == 6:
                continue  # domingo sin marcar: descanso, no falta
            db().add(Attendance(worker_id=w.id, fecha=f, estado="ASISTENCIA" if v else "FALTA", linea=w.linea,
                                observacion="Histórico del Excel de control de producción", user_id=user.id))
            res["cargadas"] += 1
    res["colaboradores_nuevos"] = nuevos
    db().flush()
    return res


# ------------------------------------------------------------------ histórico de movimientos
def movimientos(user, ws, tipo):
    res = _resumen(ws.title, f"Histórico de movimientos · {tipo}")
    filas = [list(r) for r in ws.iter_rows(values_only=True)]
    h, n = _cab(filas, "fecha")
    if h is None:
        _error(res, 0, "No se encontró la columna FECHA.")
        return res
    i_f = _idx(n, "fecha")
    i_cod = _pref(n, "codigo", "numero de articulo", "n. de producto")
    i_desc = _pref(n, "descripcion", "descrispcion", "pt y/o mp", "mp")
    i_lote, i_lin = _idx(n, "lote"), _pref(n, "linea / maquina", "linea")
    i_q = _pref(n, "cantidad - kg", "cantidad completada", "total - kg", "kg", "salida", "cantidad", "unid")
    i_um = _pref(n, "unid de medida", "um")
    desde, hoy = _desde(), date.today()
    ya = {c for c in db().execute(select(ProductionHistory.clave).where(ProductionHistory.tipo == tipo)).scalars()}
    for k, r in enumerate(filas[h + 1:], start=h + 2):
        if not any(c not in (None, "") for c in r):
            continue
        f = fecha_x(_val(r, i_f))
        if f is None:
            continue
        if not (desde <= f <= hoy):
            _error(res, k, f"fecha fuera de rango ({f:%d/%m/%Y})")
            continue
        datos = {}
        for j, c in enumerate(filas[h]):
            if c not in (None, "") and j < len(r) and r[j] not in (None, ""):
                v = r[j]
                datos[str(c).strip()[:40]] = v.isoformat() if isinstance(v, (date, datetime, time)) else v
        clave = f"{tipo}:" + hashlib.sha1(json.dumps(datos, sort_keys=True, default=str).encode()).hexdigest()[:40]
        if clave in ya:
            res["existentes"] += 1
            continue
        db().add(ProductionHistory(tipo=tipo, fecha=f, codigo=_txt(_val(r, i_cod))[:40], descripcion=_txt(_val(r, i_desc))[:250],
                                   lote=_txt(_val(r, i_lote))[:60], linea=_txt(_val(r, i_lin))[:40],
                                   cantidad=_num(_val(r, i_q)), um=_txt(_val(r, i_um))[:20], datos=datos, hoja=ws.title,
                                   fila=k, clave=clave, user_id=user.id))
        ya.add(clave)
        res["cargadas"] += 1
    db().flush()
    return res


# ------------------------------------------------------------------ el libro completo
def importar(user, path, nombre=""):
    if not (has_perm(user, "produccion.liquidar") or has_perm(user, "produccion.programar")):
        raise BusinessError("El histórico de producción lo carga Producción.")
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    por_prod = pe._productos()
    existentes = {(r.linea, r.fecha, r.hora_inicio, r.lote, r.of) for r in db().execute(select(ProductionReport)).scalars()}
    hojas = []
    for ws in wb.worksheets:
        t = pe._norm(ws.title)
        if t.startswith("programacion"):
            continue  # se carga al final con el planeamiento
        if t in LINEAS:
            linea, tipo = LINEAS[t]
            hojas.append(partes_linea(user, ws, t, linea, tipo, por_prod, existentes))
        elif t.startswith("asistencia"):
            hojas.append(asistencia(user, ws))
        elif t in HISTORICO:
            hojas.append(movimientos(user, ws, HISTORICO[t]))
        else:
            filas = [list(r) for r in ws.iter_rows(values_only=True, max_row=3)]
            nombres = [pe._norm(c) for f in filas for c in f]
            if "n. of" in nombres and "linea / maquina" in nombres:
                hojas.append(movimientos(user, ws, "OF_SAP"))
            else:
                hojas.append({"hoja": ws.title, "destino": "No se carga", "motivo": NO_SE_CARGAN.get(t, "pestaña de apoyo o "
                                                                                                        "sin un formato reconocido"),
                              "cargadas": 0, "existentes": 0, "errores": []})
    wb.close()
    try:
        r = pe.importar(user, "DIA", path, nombre)
        hojas.insert(0, {"hoja": "PROGRAMACION", "destino": "Planeamiento diario", "cargadas": r["creadas"] + r["actualizadas"],
                         "existentes": r["iguales"], "sin_producto": len(r["sin_producto"]), "errores": []})
    except BusinessError as e:
        hojas.insert(0, {"hoja": "PROGRAMACION", "destino": "Planeamiento diario", "cargadas": 0, "existentes": 0,
                         "errores": [{"fila": 0, "motivo": str(e)}]})
    res = {"archivo": nombre, "ts": now().isoformat(timespec="minutes"), "user": user.nombre, "hojas": hojas,
           "total": sum(h.get("cargadas", 0) for h in hojas)}
    from .core import set_param
    set_param("historico_produccion_ultima_carga", res)
    audit(user, "HISTORICO_PRODUCCION_EXCEL", "ProductionHistory", nombre[:60],
          {"hojas": [(h["hoja"], h.get("cargadas", 0)) for h in hojas]})
    return res
