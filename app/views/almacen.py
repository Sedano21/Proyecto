"""Vistas de Almacén: stock y estados, cargas de archivos, conteos, traslados y reempaques."""
import os
import uuid
from datetime import date, datetime

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from ..catalogs import REPACK_TYPES
from ..db import db
from ..models import (Customer, PhysicalCount, Product, RepackRequest, StockLot, Transfer, UploadBatch, UploadRow, Warehouse)
from ..services import inventory as isvc
from ..services import repack as rsvc
from ..services import transfers as tsvc
from ..services import uploads as usvc
from ..services.core import BusinessError
from ..services.stock import (BLOQUEADOS, ESTADOS_FISICOS, ESTADOS_LABEL, base_qty, change_lot_state, free_qty, product_stock_summary,
                              reserved_qty)
from .common import act, f_date, f_float, fail, login_required, paginate, perm_required

bp = Blueprint("alm", __name__, url_prefix="/almacen")


@bp.route("/lotes")
@perm_required("stock.ver")
def lot_review():
    """V21: lotes y sus variantes por puntos (cada nueva producción del mismo número), con las anomalías a corregir en SAP
    (comas, variantes con las mismas fechas, variantes sin fechas, caracteres no válidos). Exportable a Excel."""
    from ..services import lotes
    q = (request.args.get("q") or "").strip()
    tipo = request.args.get("tipo") or ""
    grupo = []
    if q:
        b = lotes.base(q)
        filas = db().execute(select(StockLot).where(StockLot.lote.like(f"{b}%"), StockLot.cantidad > 0)
                             .order_by(StockLot.product_code, StockLot.lote)).scalars()
        grupo = [l for l in filas if lotes.base(l.lote) == b]
    anom = lotes.anomalias()
    tipos = {}
    for a in anom:
        tipos[a["tipo"]] = tipos.get(a["tipo"], 0) + 1
    if tipo:
        anom = [a for a in anom if a["tipo"] == tipo]
    if request.args.get("salida") == "xlsx":
        import io
        from flask import send_file
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Lotes a corregir"
        ws.append(["Tipo", "Artículo", "Lote(s) en SAP", "Almacén", "Qué corregir"])
        for a in anom:
            ws.append([a["tipo"], a["producto"], a["lote"], a["almacen"], a["detalle"]])
        for col, w in zip("ABCDE", (30, 14, 40, 10, 70)):
            ws.column_dimensions[col].width = w
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return send_file(out, as_attachment=True, download_name=f"lotes_a_corregir_{date.today():%Y%m%d}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return render_template("lotes.html", q=q, grupo=grupo, anomalias=paginate(anom, 50), tipos=tipos, tipo=tipo,
                           lotes=lotes)


@bp.route("/stock")
@perm_required("stock.ver")
def stock():
    q = (request.args.get("q") or "").strip().upper()
    wh = request.args.get("almacen") or ""
    est = request.args.get("estado") or ""
    from ..services.stock import enabled_warehouses
    stmt = select(StockLot).where(StockLot.cantidad > 0, StockLot.warehouse_code.in_(enabled_warehouses()))
    if q:
        # V20: también por lote; «000863FA» encuentra todas sus variantes (000863FA., 000863FA..)
        stmt = stmt.join(Product).where((StockLot.product_code.like(f"%{q}%")) | (Product.descripcion.like(f"%{q}%"))
                                        | StockLot.lote.like(f"%{q.rstrip('.,')}%") | StockLot.ubicacion.like(f"%{q}%"))
    if wh:
        stmt = stmt.where(StockLot.warehouse_code == wh)
    if est:
        stmt = stmt.where(StockLot.estado == est)
    lots = paginate(stmt.order_by(StockLot.product_code, StockLot.fecha_venc), 50)  # V19: solo la página pedida
    codes = sorted({l.product_code for l in lots})
    resumen = {c: product_stock_summary(c) for c in codes[:300]}
    whs = list(db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True)).order_by(Warehouse.prioridad, Warehouse.code)).scalars())
    productos = list(db().execute(select(Product).where(Product.code.in_(select(StockLot.product_code).where(StockLot.cantidad > 0)))
                                  .order_by(Product.code)).scalars())
    return render_template("stock.html", lots=lots, resumen=resumen, q=q, wh=wh, est=est, whs=whs, estados=ESTADOS_FISICOS,
                           labels=ESTADOS_LABEL, reserved=reserved_qty, free=free_qty, base=base_qty, productos=productos,
                           blocked=BLOQUEADOS, ubicaciones=__import__("app.services.v30", fromlist=["x"]).ubicaciones_usadas(),
                           clientes=(list(db().execute(select(Customer).where(Customer.es_prospecto.is_(False))
                                                       .order_by(Customer.nombre)).scalars())
                                     if "lote.reglas_clientes" in g.perms else []))


@bp.route("/lote/<int:lid>/estado", methods=["POST"])
@perm_required("stock.cambiar_estado", "calidad.liberar")
def lot_state(lid):
    lot = db().get(StockLot, lid) or abort(404)
    nuevo = request.form.get("estado")
    if nuevo == "DISPONIBLE" and "calidad.liberar" not in g.perms and lot.estado in ("PENDIENTE_REVISION", "NO_UTILIZABLE",
                                                                                   "EN_FUMIGACION"):
        return fail("La liberación a Disponible la realiza Calidad.", request.referrer or url_for("alm.stock"))
    from ..services import lotes_v70  # V70: total o parcial (cantidad y ubicación)
    f = request.form
    return act(lambda: lotes_v70.cambiar_estado(g.user, lot, nuevo, f.get("motivo", ""), f.get("alcance", "TOTAL"),
                                                f.get("cantidad"), f.get("ubicacion", "")),
               f"Lote {lot.lote} actualizado.", request.referrer or url_for("alm.stock"))


@bp.route("/lote/<int:lid>/clientes", methods=["POST"])
@perm_required("lote.reglas_clientes")
def lot_customers(lid):
    """V70: Calidad define que el lote solo se despache a ciertos clientes o que se bloquee para ciertos clientes."""
    from ..services import lotes_v70
    lot = db().get(StockLot, lid) or abort(404)
    f = request.form
    ids = [] if f.get("accion") == "quitar" else f.getlist("cliente_id")
    return act(lambda: lotes_v70.restringir_clientes(g.user, lot, f.get("modo"), ids, f.get("motivo", "")),
               lambda r: f"Lote {lot.lote}: " + ("regla de clientes guardada." if r else "regla de clientes quitada."),
               request.referrer or url_for("alm.stock"))


# ------------------------------- cargas ------------------------------------
@bp.route("/cargas")
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar", "precios.editar", "costos.cargar", "clientes.canal", "distribucion.documentos")
def uploads():
    """Cada área ve solo sus cargas (observaciones al demo v0.5): ?area=Almacén / Comercial / Producción / Configuración."""
    area = request.args.get("area", "")
    propios = usvc.specs_for(g.user, area or None)
    tipos = set(propios) if area else set(usvc.specs_for(g.user))
    rows = [r for r in db().execute(select(UploadBatch).order_by(UploadBatch.id.desc()).limit(400)).scalars() if r.tipo in tipos]
    return render_template("uploads.html", rows=paginate(rows), specs=usvc.SPECS, propios=propios, area=area,
                           areas=[a for a in usvc.AREAS if usvc.specs_for(g.user, a)])


@bp.route("/cargas/nueva", methods=["GET", "POST"])
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar", "precios.editar", "costos.cargar", "clientes.canal", "distribucion.documentos")
def upload_new():
    disponibles = usvc.specs_for(g.user)
    tipo = request.values.get("tipo") or next(iter(disponibles), "STOCK")
    if tipo not in disponibles:
        abort(403)
    if request.method == "POST":
        f = request.files.get("archivo")
        if not f or not f.filename:
            return fail("Seleccione un archivo.", url_for("alm.upload_new", tipo=tipo))
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".xlsx", ".xlsm", ".pdf"):
            return fail("Se aceptan archivos Excel (.xlsx, .xlsm) o PDF.", url_for("alm.upload_new", tipo=tipo))
        path = os.path.join(current_app.config["UPLOAD_DIR"], f"carga_{uuid.uuid4().hex[:10]}{ext}")
        f.save(path)
        holder = {}

        def _do():
            holder["b"] = usvc.create_batch(g.user, tipo, path, os.path.basename(f.filename), request.form.get("hoja") or None)
            return holder["b"]
        resp = act(_do, lambda b: f"Archivo leído: {len(b.rows)} filas. Revise errores y advertencias antes de autorizar.",
                   url_for("alm.uploads"))
        if "b" in holder and holder["b"].id:
            return redirect(url_for("alm.upload_detail", bid=holder["b"].id))
        return resp
    area = usvc.SPECS[tipo].get("area")
    return render_template("upload_new.html", tipo=tipo, specs=usvc.specs_for(g.user, area))


@bp.route("/cargas/<int:bid>")
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar", "precios.editar", "costos.cargar", "clientes.canal", "distribucion.documentos")
def upload_detail(bid):
    b = db().get(UploadBatch, bid) or abort(404)
    filtro = request.args.get("filtro", "problemas")
    rows = b.rows
    if filtro == "problemas":
        rows = [r for r in rows if r.errores or r.advertencias or r.excluida or r.editada]
    # V19: resumen por tipo de aviso (p. ej. «Lote con puntos o comas al final»: 298) y filtro por ese tipo
    from collections import Counter

    def _tipo(m):
        return m.split(":")[0].split("'")[0].strip()
    tipos = Counter(_tipo(m) for r in rows for m in (r.errores or []) + (r.advertencias or []))
    aviso = request.args.get("aviso", "")
    if aviso:
        rows = [r for r in rows if any(_tipo(m) == aviso for m in (r.errores or []) + (r.advertencias or []))]
    return render_template("upload_detail.html", bt=b, rows=paginate(rows, 50), filtro=filtro, spec=usvc.SPECS[b.tipo],
                           tipos=tipos.most_common(), aviso=aviso)


@bp.route("/cargas/<int:bid>/fila/<int:rid>", methods=["POST"])
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar", "precios.editar", "costos.cargar", "clientes.canal", "distribucion.documentos")
def upload_row(bid, rid):
    b = db().get(UploadBatch, bid) or abort(404)
    r = db().get(UploadRow, rid) or abort(404)
    if r.batch_id != b.id:
        abort(404)
    accion = request.form.get("accion")
    if accion == "excluir":
        fn = lambda: usvc.exclude_row(b, r, g.user, request.form.get("motivo", ""))  # noqa: E731
    elif accion == "incluir":  # V30: incluir tal como viene, con motivo (excluida o con observaciones)
        fn = lambda: usvc.include_row(b, r, g.user, request.form.get("motivo", ""))  # noqa: E731
    else:
        nuevos = {k[2:]: v for k, v in request.form.items() if k.startswith("c_")}
        fn = lambda: usvc.edit_row(b, r, g.user, nuevos)  # noqa: E731
    return act(fn, "Fila actualizada y carga revalidada.", url_for("alm.upload_detail", bid=bid) + f"#f{r.id}")


@bp.route("/cargas/<int:bid>/<accion>", methods=["POST"])
@perm_required("stock.cargar", "produccion.bom_cargar", "ov.importar", "produccion.liquidar", "config.editar", "precios.editar", "costos.cargar", "clientes.canal", "distribucion.documentos")
def upload_action(bid, accion):
    b = db().get(UploadBatch, bid) or abort(404)
    if accion == "confirmar":
        opciones = {k: v for k, v in request.form.items() if k not in ("_csrf",)}
        return act(lambda: usvc.confirm(b, g.user, opciones), lambda r: f"Carga autorizada e incorporada: {r}",
                   url_for("alm.upload_detail", bid=bid))
    if accion == "descartar":
        return act(lambda: usvc.discard(b, g.user), "Carga descartada.", url_for("alm.uploads"))
    if accion == "excluir_errores":
        return act(lambda: usvc.exclude_errors(b, g.user, request.form.get("motivo", "")),
                   lambda n: f"{n} fila(s) con error excluidas. Ya puede autorizar la carga.", url_for("alm.upload_detail", bid=bid))
    abort(404)


# ------------------------------- conteos -----------------------------------
@bp.route("/conteos", methods=["GET", "POST"])
@perm_required("stock.conteo")
def counts():
    if request.method == "POST":
        holder = {}

        def _do():
            f = request.form
            base = db().get(PhysicalCount, int(f["base_id"])) if f.get("base_id") else None
            codigos = [x for x in f.get("lista", "").replace(",", "\n").splitlines() if x.strip()]
            holder["c"] = isvc.open_count(g.user, f.get("warehouse_code") or (base.warehouse_code if base else ""),
                                          f.get("prefijo", "").strip().upper(), f.get("observacion", ""), base, codigos or None,
                                          por_producto=f.get("por_producto") == "1")
        resp = act(_do, "Conteo abierto.", url_for("alm.counts"))
        if "c" in holder and holder["c"].id:
            return redirect(url_for("alm.count_detail", cid=holder["c"].id))
        return resp
    rows = list(db().execute(select(PhysicalCount).order_by(PhysicalCount.id.desc())).scalars())
    whs = list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars())
    return render_template("counts.html", rows=paginate(rows), whs=whs)


@bp.route("/conteos/<int:cid>", methods=["GET", "POST"])
@perm_required("stock.conteo", "conteo.validar")
def count_detail(cid):
    c = db().get(PhysicalCount, cid) or abort(404)
    back = url_for("alm.count_detail", cid=cid)
    if request.method == "POST" and request.form.get("accion") == "agregar":  # V17: producto por producto
        return act(lambda: isvc.add_products(c, g.user, request.form.getlist("producto"), request.form.get("lote", "").strip()),
                   lambda n: f"{n} línea(s) agregada(s): registre lo contado.", back)
    if request.method == "POST" and request.form.get("accion") in ("validar", "devolver"):  # V17: Jefe de Logística
        return act(lambda: isvc.validate_count(c, g.user, request.form["accion"] == "validar", request.form.get("comentario", "")),
                   "Conteo validado: se actualizó el sistema." if request.form["accion"] == "validar" else
                   "Conteo devuelto para revisar.", back)
    if request.method == "POST":
        vals = {}
        for line in c.lines:
            vals[str(line.id)] = {"conteo": request.form.get(f"conteo_{line.id}"),
                                  "peso_unitario": request.form.get(f"peso_{line.id}"),
                                  "comentario": request.form.get(f"com_{line.id}", "")}
            if f"rec_{line.id}" in request.form:
                vals[str(line.id)]["recuento"] = request.form.get(f"rec_{line.id}")
        def _do():
            isvc.save_lines(c, g.user, vals)
            if request.form.get("cerrar") == "1":
                return isvc.close_count(c, g.user)
        return act(_do, lambda r: "Conteo enviado al Jefe de Logística para su validación." if r is not None else "Conteo guardado.",
                   url_for("alm.count_detail", cid=cid))
    from ..models import Product
    prods = list(db().execute(select(Product).order_by(Product.code)).scalars()) if c.estado == "ABIERTO" else []
    return render_template("count_detail.html", c=c, recontar=isvc.needs_recount, prods=prods,
                           puede_validar=isvc.can_validate(g.user))


# ------------------------------- traslados ---------------------------------
@bp.route("/traslados")
@perm_required("traslados.ver")
def transfers():
    return render_template("transfers.html", rows=paginate(select(Transfer).order_by(Transfer.id.desc())))


@bp.route("/traslados/<int:tid>")
@perm_required("traslados.ver")
def transfer_detail(tid):
    """Formato de la (pre)solicitud de traslado para revisarla antes de decidir (observaciones al demo v0.6)."""
    from ..models import User
    t = db().get(Transfer, tid) or abort(404)
    sol = db().get(User, t.solicitado_por) if t.solicitado_por else None
    aut = db().get(User, t.autorizado_por) if t.autorizado_por else None
    return render_template("transfer_detail.html", t=t, sol=sol, aut=aut, libre=tsvc.transferable_qty(t.lot))


@bp.route("/traslados/<int:tid>/<accion>", methods=["POST"])
@perm_required("traslados.ver")
def transfer_action(tid, accion):
    t = db().get(Transfer, tid) or abort(404)
    def _llegada():
        raw = (request.form.get("llegada") or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            raise BusinessError(f"Fecha y hora inválidas: {raw}")
    fns = {
        "autorizar": lambda: tsvc.authorize(t, g.user, True, request.form.get("observacion", ""), _llegada()),
        "llegada": lambda: tsvc.set_arrival(t, g.user, _llegada()),
        "rechazar": lambda: tsvc.authorize(t, g.user, False, request.form.get("observacion", "")),
        "salida": lambda: tsvc.ship(t, g.user),
        "recibir": lambda: tsvc.receive(t, g.user, f_float("cantidad_recibida", True), request.form.get("observacion", "")),
    }
    if accion not in fns:
        abort(404)
    return act(fns[accion], "Traslado actualizado.", url_for("alm.transfers"))


# ------------------------------- reempaque ---------------------------------
@bp.route("/reempaques", methods=["GET", "POST"])
@perm_required("reempaque.ver")
def repacks():
    if request.method == "POST" and request.form.get("accion") == "excel":
        def _x():
            import os
            from flask import current_app
            arch = request.files.get("archivo")
            if not arch or not arch.filename.lower().endswith((".xlsx", ".xlsm")):
                raise BusinessError("Suba la solicitud de reempaque en Excel (.xlsx).")
            up = current_app.config["UPLOAD_DIR"]
            os.makedirs(up, exist_ok=True)
            path = os.path.join(up, f"reempaque_{os.urandom(4).hex()}.xlsx")
            arch.save(path)
            return rsvc.import_requests(g.user, path)
        return act(_x, lambda r: f"{len(r[0])} solicitud(es) enviadas a Calidad." + (f" Errores: {' | '.join(r[1][:5])}" if r[1] else ""),
                   url_for("alm.repacks"))
    if request.method == "POST":
        return act(lambda: rsvc.request(g.user, request.form.get("tipo"), request.form.get("lot_id"), f_float("cantidad", True),
                                        (request.form.get("producto_destino") or "").strip().upper() or None, None, None,
                                        request.form.get("motivo", "")),
                   "Solicitud de reempaque enviada a Calidad.", url_for("alm.repacks"))
    rows = list(db().execute(select(RepackRequest).order_by(RepackRequest.id.desc())).scalars())
    # V70: por cliente, fecha de despacho y OV
    a = request.args
    cli = (a.get("cliente") or "").strip().upper()
    ovq = (a.get("ov") or "").strip().upper()
    fd, fh = f_date("desde"), f_date("hasta")
    if cli:
        rows = [r for r in rows if r.order and cli in (r.order.customer.nombre or "").upper()]
    if ovq:
        rows = [r for r in rows if r.order and ovq in (r.order.numero or "").upper()]
    if fd:
        rows = [r for r in rows if r.order and r.order.fecha_compromiso >= fd]
    if fh:
        rows = [r for r in rows if r.order and r.order.fecha_compromiso <= fh]
    vista = a.get("vista", "")
    grupos = []
    if vista == "ov":
        por = {}
        for r in rows:
            k = r.order.id if r.order else 0
            por.setdefault(k, {"order": r.order, "rows": []})["rows"].append(r)
        grupos = sorted(por.values(), key=lambda x: (x["order"].fecha_compromiso if x["order"] else date.max))
    lots = list(db().execute(select(StockLot).where(StockLot.cantidad > 0, StockLot.estado.in_(["DISPONIBLE", "PENDIENTE_REVISION"]),
                                                    StockLot.product_code.like("P%")).order_by(StockLot.product_code)).scalars())
    prods = list(db().execute(select(Product).where(Product.tipo == "PT").order_by(Product.code)).scalars())
    return render_template("repacks.html", rows=paginate(rows), lots=lots, prods=prods, tipos=REPACK_TYPES, free=free_qty,
                           vista=vista, grupos=grupos, f=a)


@bp.route("/reempaques/<int:rid>", methods=["GET", "POST"])
@perm_required("reempaque.ver")
def repack_detail(rid):
    r = db().get(RepackRequest, rid) or abort(404)
    if request.method == "POST":
        acc = request.form.get("accion")
        fns = {
            "aprobar_pre": lambda: rsvc.approve_presolicitud(r, g.user, True, request.form.get("comentario", "")),
            "desestimar_pre": lambda: rsvc.approve_presolicitud(r, g.user, False, request.form.get("comentario", "")),
            "aprobar": lambda: rsvc.evaluate(r, g.user, True, request.form.get("resultado", "")),
            "desaprobar": lambda: rsvc.evaluate(r, g.user, False, request.form.get("resultado", "")),
            "iniciar": lambda: rsvc.start(r, g.user),
            "finalizar": lambda: rsvc.finish(r, g.user, request.form.get("lote_resultante", "").strip(),
                                             f_float("cantidad_resultante", True), f_date("nueva_fecha_fab"), f_date("nueva_fecha_venc")),
        }
        if acc not in fns:
            abort(404)
        return act(fns[acc], "Reempaque actualizado.", url_for("alm.repack_detail", rid=rid))
    return render_template("repack_detail.html", r=r, tipos={c: (n, d) for c, n, d in REPACK_TYPES})


# ---------------- programación del picking por persona (obs. demo v0.6) ----------------
def _picking_access():
    return any(p in g.perms for p in ("preparacion.registrar", "picking.asignar", "tareas.ejecutar"))


@bp.route("/picking")
@perm_required("preparacion.registrar", "picking.asignar", "tareas.ejecutar")
def picking_schedule():
    from datetime import date, timedelta
    from ..services import picking as pk
    vista = request.args.get("vista", "dia")
    try:
        ref = date.fromisoformat(request.args.get("fecha") or date.today().isoformat())
    except ValueError:
        ref = date.today()
    desde = ref if vista == "dia" else ref - timedelta(days=ref.weekday())
    hasta = ref if vista == "dia" else desde + timedelta(days=6)
    if vista == "semana" and request.args.get("desde") and request.args.get("hasta"):  # V17: rango de fechas elegido
        try:
            desde, hasta = date.fromisoformat(request.args["desde"]), date.fromisoformat(request.args["hasta"])
        except ValueError:
            pass
        if hasta < desde:
            desde, hasta = hasta, desde
        hasta = min(hasta, desde + timedelta(days=62))
    asigna = "picking.asignar" in g.perms
    wh = request.args.get("almacen") or ""
    rows = pk.schedule(g.user, desde, hasta, wh or None, solo_mios=not asigna)
    clientes = sorted({t.order.customer for t in rows if t.order.customer}, key=lambda c: c.nombre)
    cli = request.args.get("cliente", "")
    if cli.isdigit():  # filtro opcional por cliente
        rows = [t for t in rows if t.order.customer_id == int(cli)]
    grupos = {}
    for t in rows:  # programación organizada por cliente
        grupos.setdefault(t.order.customer, []).append(t)
    personal = {w: pk.staff(w) for w in sorted({t.warehouse_code for t in rows} | ({wh} if wh else set()))}
    return render_template("picking_schedule.html", rows=rows, vista=vista, ref=ref, desde=desde, hasta=hasta, asigna=asigna,
                           clientes=clientes, cliente=cli, grupos=sorted(grupos.items(), key=lambda kv: kv[0].nombre if kv[0] else ""),
                           usuarios=pk.users_by_id(), almacen=wh, personal=personal,
                           almacenes=list(db().execute(select(Warehouse).order_by(Warehouse.prioridad)).scalars()),
                           timedelta=timedelta)


@bp.route("/picking/<int:tid>", methods=["GET", "POST"])
@perm_required("preparacion.registrar", "picking.asignar", "tareas.ejecutar")
def picking_task(tid):
    from ..models import PickingTask
    from ..services import picking as pk
    from ..services.distribution import save_upload
    t = db().get(PickingTask, tid) or abort(404)
    if "picking.asignar" not in g.perms and g.user.id not in (t.asignados or []):
        abort(403)
    if request.method == "POST":
        f = request.form
        acc = f.get("accion")
        up = current_app.config["UPLOAD_DIR"]
        fn = {
            # V17: filas «+» (persona y si reporta en el sistema)
            "asignar": lambda: pk.assign(t, g.user, f.getlist("persona") if f.getlist("persona") else
                                         (f.getlist("grupo") if f.get("modo") == "grupo" else f.getlist("user_id")),
                                         f_date("fecha"), f.get("comentario", ""),
                                         [p for p, r in zip(f.getlist("persona"), f.getlist("reporta")) if r == "1"]),
            "iniciar": lambda: pk.start(t, g.user, save_upload(request.files.get("foto"), up, f"picking{t.id}_ini")),
            # obs. demo v0.7: el auxiliar solo llena «Despachado und»; lote, fechas y bultos salen del stock reservado
            "registrar": lambda: pk.record(t, g.user, f.get("line_id"), f_float("cantidad", True), f.get("lote", ""),
                                           bultos=f_float("bultos")),  # V18: los bultos los completa quien hace el picking
            "cambiar_lote": lambda: pk.change_lot(t, g.user, f.get("reservation_id"), f.get("lot_id"), f_float("cantidad"),
                                                  f.get("motivo", ""), f.get("observacion", "")),
            "agregar_lote": lambda: pk.add_lot(t, g.user, f.get("line_id"), f.get("lot_id"), f_float("cantidad"),
                                               f.get("observacion", "")),
            "listo": lambda: pk.finish(t, g.user, save_upload(request.files.get("foto"), up, f"picking{t.id}_fin"),
                                       f.get("observacion", "")),
            # V18: la validación de la planificación también desde esta misma pantalla
            "validar_plan": lambda: __import__("app.services.orders", fromlist=["x"]).validate_picking_plan(t.order, g.user),
        }.get(acc) or abort(400)
        destino = url_for("alm.picking_task", tid=tid) + ("#formato" if acc in ("iniciar", "registrar", "cambiar_lote", "agregar_lote") else "")
        msg = {"iniciar": "Picking iniciado: complete el formato de control de despacho.", "cambiar_lote": "Lote cambiado: formato y stock actualizados.",
               "agregar_lote": "Lote adicional agregado: complete lo picado de ese lote.",
               "asignar": "Asignación guardada."}.get(acc, "Picking actualizado.")
        return act(fn, msg, destino)
    from ..models import PickingRecord
    from ..services.stock import line_reserved
    recs = list(db().execute(select(PickingRecord).where(PickingRecord.task_id == t.id).order_by(PickingRecord.id)).scalars())
    from collections import Counter
    from ..services.stock import free_qty
    plan = pk.schedule(g.user, t.fecha, t.fecha, t.warehouse_code) if "picking.asignar" in g.perms else []
    carga = Counter(i for x in plan for i in (x.asignados or []))
    return render_template("picking_task.html", t=t, o=t.order, usuarios=pk.users_by_id(), personal=pk.staff(t.warehouse_code),
                           recs=recs, line_reserved=line_reserved, plan=plan, carga=carga, motivos=pk.MOTIVOS_CAMBIO_LOTE,
                           opciones_lote=lambda l: pk.lot_options(t, l, todos=True), free=free_qty,
                           falta_reservar=lambda l: pk.falta_reservar(t, l),
                           etiquetas=__import__("app.services.etiquetas", fromlist=["x"]).para_orden(t.order))


@bp.route("/picking/cliente/<int:cid>/<fecha>/<almacen>", methods=["GET", "POST"])
@perm_required("preparacion.registrar", "picking.asignar", "tareas.ejecutar")
def picking_customer(cid, fecha, almacen):
    """V43: un solo picking para todas las OV de un cliente con el mismo despacho (fecha y almacén)."""
    from datetime import date as _date
    from ..models import Customer
    from ..services import picking as pk
    from ..services import picking_cliente as pc
    from ..services.distribution import save_upload
    try:
        dia = _date.fromisoformat(fecha)
    except ValueError:
        abort(404)
    cli = db().get(Customer, cid) or abort(404)
    ts = pc.tareas(cid, dia, almacen)
    if not ts:
        abort(404)
    asigna = "picking.asignar" in g.perms
    if not asigna and not any(g.user.id in (t.asignados or []) for t in ts):
        abort(403)
    back = url_for("alm.picking_customer", cid=cid, fecha=fecha, almacen=almacen)
    if request.method == "POST":
        f = request.form
        up = current_app.config["UPLOAD_DIR"]
        acc = f.get("accion")
        fn = {
            "validar_plan": lambda: pc.validar_plan(g.user, ts),
            "asignar": lambda: pc.asignar(g.user, ts, f.getlist("persona"), None, f.get("comentario", ""),
                                          f.getlist("reporta")),
            "iniciar": lambda: pc.iniciar(g.user, ts, save_upload(request.files.get("foto"), up, f"pickcli{cid}_ini")),
            "registrar": lambda: pc.registrar(g.user, ts, f.get("producto", ""), f.get("lote", ""), f_float("cantidad", True),
                                              f_float("bultos")),
            "listo": lambda: pc.finalizar(g.user, ts, save_upload(request.files.get("foto"), up, f"pickcli{cid}_fin"),
                                          f.get("observacion", "")),
        }.get(acc) or abort(400)
        msg = {"validar_plan": "Planificación validada para todas las OV.", "asignar": "Asignación guardada para todas las OV.", "iniciar": "Picking iniciado para todas las OV.",
               "registrar": "Registrado y repartido entre las OV.", "listo": "Todas las OV listas para el despacho."}[acc]
        return act(fn, msg, back + ("#lista" if acc in ("iniciar", "registrar") else ""))
    filas = pc.consolidado(ts)
    from ..services.orders import prep_progress
    return render_template("picking_cliente.html", cli=cli, dia=dia, almacen=almacen, ts=ts, filas=filas,
                           res=pc.resumen(ts), asigna=asigna, personal=pk.staff(almacen), usuarios=pk.users_by_id(),
                           avance={t.id: prep_progress(t.order) for t in ts})


@bp.route("/picking/formato")
@perm_required("preparacion.registrar", "picking.asignar", "tareas.ejecutar")
def picking_format():
    """Formato 'Seguimiento de control de despacho de producto terminado' generado por el sistema."""
    from datetime import date
    from ..models import PickingTask
    from ..services import picking as pk
    tid = request.args.get("tid")
    if tid:
        t = db().get(PickingTask, int(tid)) or abort(404)
        tareas = [t]
        fecha = t.fecha
    else:
        try:
            fecha = date.fromisoformat(request.args.get("fecha") or date.today().isoformat())
        except ValueError:
            fecha = date.today()
        tareas = pk.schedule(g.user, fecha, fecha, request.args.get("almacen") or None,
                             solo_mios="picking.asignar" not in g.perms)
    usuarios = pk.users_by_id()
    encargados = sorted({usuarios[i].nombre for t in tareas for i in (t.asignados or []) if i in usuarios})
    return render_template("picking_format.html", filas=pk.format_rows(tareas), fecha=fecha, encargados=encargados, tareas=tareas,
                           almacenes=sorted({t.warehouse_code for t in tareas}), generado=datetime.now())


# ------------------- ingresos a almacén (ronda UX 24-oct-2026, sección 5) -------------------
@bp.route("/ingresos")
@perm_required("ingresos.ver")
def entries():
    """Ingresos de producto a almacén (liquidaciones de PT recibidas o por recibir) con su estado y motivo de observación."""
    from datetime import date, timedelta
    from ..models import Liquidation
    from .common import f_date
    desde = f_date("desde") or date.today() - timedelta(days=15)
    q = select(Liquidation).where(Liquidation.fecha >= desde).order_by(Liquidation.fecha.desc(), Liquidation.id.desc())
    estado = request.args.get("estado", "")
    rows = [l for l in db().execute(q.limit(300)).scalars() if not estado or l.estado == estado]
    return render_template("entries.html", rows=paginate(rows), desde=desde, estado=estado,
                           estados=["REGISTRADA", "BLOQUEADA", "RECIBIDA_COMPLETA", "RECIBIDA_FALTANTE", "RECIBIDA_SOBRANTE"])


# ------------------- conexión SAP Service Layer (ronda 26-oct-2026) -------------------
@bp.route("/cargas/sap", methods=["GET", "POST"])
@perm_required("stock.cargar", "ov.importar", "config.editar", "produccion.liquidar", "distribucion.documentos")
def sap_sync():
    """Traer datos de SAP (solo lectura) y pasarlos por el flujo de cargas: validación, revisión y autorización."""
    from flask import current_app
    from ..services import sap_sl
    from ..services.uploads import SPECS
    if request.method == "POST":
        if request.form.get("accion") == "probar":
            return act(lambda: sap_sl.test_connection(), lambda r: f"Conexión con SAP correcta (versión {r['version'] or '-'}).",
                       url_for("alm.sap_sync"))
        tipo = request.form.get("tipo", "")
        if tipo == "FACTURAS":
            if "facturas.cargar" not in g.perms:
                abort(403)
        elif tipo == "SERVICIOS":
            if not g.perms & {"ov.importar", "produccion.liquidar", "distribucion.ver", "ov.ver"}:
                abort(403)
        elif tipo == "ORDENES":  # V29: órdenes de venta y de servicio del periodo (demanda)
            if not g.perms & {"ov.importar", "ov.ver", "demanda.analisis", "dashboard.ver"}:
                abort(403)
        elif tipo == "ACTUALIZAR":  # V31: «Actualizar con SAP» desde la barra superior
            if not g.perms & {"ov.ver", "ov.importar", "stock.ver", "distribucion.ver", "produccion.ver", "facturas.cargar"}:
                abort(403)
        elif tipo == "RESERVAS":  # V30: facturas de reserva sin entrega
            if not g.perms & {"facturas_reserva.ver", "facturas_reserva.aprobar"}:
                abort(403)
        elif tipo == "BALANCE_OF":  # V29: balance de peso de las órdenes de fabricación
            if not g.perms & {"produccion.ver", "produccion.liquidar"}:
                abort(403)
        elif tipo not in sap_sl.TIPOS_SAP or SPECS[tipo]["perm"] not in g.perms:
            abort(403)
        # 10-nov-2026: se trae en segundo plano; la pantalla se actualiza sola y muestra la carga al terminar
        app_obj = current_app._get_current_object()
        volver = request.form.get("volver", "")
        volver = volver if volver.startswith("/") and not volver.startswith("//") else url_for("alm.sap_sync")
        nombre = sap_sl.TIPOS_SAP.get(tipo) or sap_sl.EXTRAS.get(tipo, tipo)
        from ..services import sap_vigia
        if tipo == "ACTUALIZAR" and sap_vigia.vivo():  # V32: lo atiende el vigilante de SAP en segundos
            if sap_sl.job_state("ACTUALIZAR").get("estado") == "EN_CURSO":
                return act(lambda: None, "Ya se está actualizando con SAP; en unos segundos se ve el resultado.", volver)
            return act(lambda: sap_vigia.pedir_actualizacion(g.user),
                       "Actualizando con SAP: se trae solo lo que cambió; en unos segundos se ve el resultado.", volver)
        return act(lambda: sap_sl.sync_background(app_obj, tipo, g.user, current_app.config["UPLOAD_DIR"]),
                   f"Trayendo {nombre.lower()} de SAP… puede tardar unos minutos; esta página se actualiza sola.", volver)
    tipos = [(t, n) for t, n in sap_sl.TIPOS_SAP.items() if SPECS[t]["perm"] in g.perms]
    ult = {t: db().execute(select(UploadBatch).where(UploadBatch.archivo.like(f"SAP_SL_{t}_%"))
                           .order_by(UploadBatch.id.desc())).scalars().first() for t, _ in tipos}
    cfg = sap_sl.config()
    from ..models import SalesOrder
    ovs = list(db().execute(select(SalesOrder).where(SalesOrder.origen == "MODULO", SalesOrder.estado != "BORRADOR")
                            .order_by(SalesOrder.id.desc()).limit(500)).scalars())
    trabajos = {t: sap_sl.job_state(t) for t, _ in tipos}
    if "facturas.cargar" in g.perms:
        trabajos["FACTURAS"] = sap_sl.job_state("FACTURAS")
    return render_template("sap_sync.html", tipos=tipos, ult=ult, configurado=sap_sl.configured(), trabajos=trabajos,
                           en_curso=any(j.get("estado") == "EN_CURSO" for j in trabajos.values()),
                           ver_facturas="facturas.cargar" in g.perms,
                           url=cfg["url"], empresa=cfg["company"], estado=sap_sl.connection_state(),
                           cola=[o for o in ovs if sap_sl.pending_action(o)],
                           conflictos=[o for o in ovs if (o.sap_envio or {}).get("conflicto")])


@bp.route("/conteos/<int:cid>/excel")
@perm_required("stock.conteo", "stock.ver")
def count_excel(cid):
    """V15: diferencias del conteo físico para que SAP registre el ajuste (recuento de inventario)."""
    import io
    from flask import send_file
    from openpyxl import Workbook
    from openpyxl.styles import Font
    c = db().get(PhysicalCount, cid) or abort(404)
    wb = Workbook()
    ws = wb.active
    ws.title = f"Conteo {c.id}"
    ws.append([f"Conteo físico #{c.id} · almacén {c.warehouse_code} · {c.fecha:%d/%m/%Y} · {c.estado}"])
    ws.append(["Almacén", "Código", "Descripción", "Lote", "Cantidad SAP", "Conteo físico", "Recuento", "Diferencia",
               "Ajuste en SAP", "Comentario"])
    for c2 in ws[2]:
        c2.font = Font(bold=True)
    for ln in sorted(c.lines, key=lambda x: (x.product_code, x.lote)):
        fis = ln.fisico if ln.fisico is not None else None
        dif = round((fis or 0) - (ln.sap or 0), 4) if fis is not None else None
        p = db().get(Product, ln.product_code)
        ws.append([c.warehouse_code, ln.product_code, p.descripcion if p else "", ln.lote, ln.sap, fis, ln.recuento, dif,
                   ("Entrada" if dif and dif > 0 else "Salida" if dif and dif < 0 else "") if dif is not None else "sin contar",
                   ln.comentario])
    ws.freeze_panes = "A3"
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return send_file(out, as_attachment=True, download_name=f"conteo_{c.id}_{c.warehouse_code}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/cargas/sap/despachos")
@perm_required("ov.ver", "distribucion.ver", "stock.cargar", "ov.importar")
def sap_dispatch_check():
    """V26: OV abiertas de SAP frente a sus guías de SAP: despachos completos, incompletos o sin despacho."""
    from flask import Response
    from ..services import despachos_sap as ds
    clase = request.args.get("clase", "VENTA")
    clase = clase if clase in ("VENTA", "SERVICIO", "TODAS") else "VENTA"
    # V31: con el historial de SAP (desde julio) se ven las órdenes abiertas y cerradas, por mes
    from ..services import sap_v31
    mes = request.args.get("mes", "")
    situacion = request.args.get("sit", "ABIERTAS")
    situacion = situacion if situacion in ("ABIERTAS", "CERRADAS", "TODAS") else "ABIERTAS"
    if sap_v31.tiene_historial():
        from .common import _rango_lista
        f_desde, f_hasta, _orden = _rango_lista()  # V33: un solo filtro de fechas (emisión): desde/hasta o mes
        res = ds.conciliar_historial(mes if len(mes) == 7 else "", None if clase == "TODAS" else clase, situacion,
                                     f_desde, f_hasta)
    else:
        res = ds.conciliar(clase=None if clase == "TODAS" else clase)
    if request.args.get("salida") == "xlsx":
        return Response(ds.excel(res), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=ov_vs_guias_sap.xlsx"})
    estado = request.args.get("estado", "")
    filas = [f for f in res["filas"] if not estado or f["estado"] == estado or (estado == "ALERTA" and f["alertas"])]
    por_cliente = []
    if request.args.get("vista") == "cliente":  # V43: primero los clientes; al entrar, sus órdenes
        from collections import Counter, defaultdict
        gr = defaultdict(list)
        for f in filas:
            gr[f["cliente"] or "(sin cliente)"].append(f)
        por_cliente = sorted(({"cliente": c, "n": len(fs), "estados": Counter(f["estado"] for f in fs),
                               "alertas": sum(1 for f in fs if f["alertas"])} for c, fs in gr.items()),
                             key=lambda x: (-x["estados"].get("PARCIAL", 0) - x["estados"].get("SIN_DESPACHO", 0), x["cliente"]))
    from .common import paginate
    filas = paginate(filas)  # V32: listas largas con paginador
    from ..services import sap_sl
    job = sap_sl.job_state("SERVICIOS")
    from ..services.core import param
    return render_template("sap_despachos.html", res=res, filas=filas, estado=estado, job=job, clase=clase,
                           vista=request.args.get("vista", ""), por_cliente=por_cliente,
                           mes=mes, sit=situacion, meses=ds.meses_historial(), job_hist=sap_sl.job_state("ORDENES"),
                           series_servicio=param("sap_series_orden_servicio", []) or [],
                           configurado=sap_sl.configured())


# ------------------------------------------------------------------ V66: marcha blanca de almacén
@bp.route("/consolidado")
@perm_required("almacen.consolidado")
def consolidated():
    """Consolidado del picking por sede, fecha, cliente, producto y almacén (como la tabla dinámica de Almacén), en
    pantalla, PDF y Excel."""
    import io
    from flask import send_file
    from ..models import Customer
    from ..services import almacen_v66 as av
    a = request.args
    d = av.consolidado(f_date("desde"), f_date("hasta"), a.get("cliente") or None, a.get("producto", ""),
                       a.get("almacen", ""), a.get("sede", ""), a.get("agrupar", "cliente"))
    fmt = a.get("formato", "")
    if fmt in ("pdf", "xlsx"):
        cols, filas = av.tabla_pdf(d)
        titulo = f"Consolidado del picking {d['desde']:%d/%m/%Y} – {d['hasta']:%d/%m/%Y}"
        if fmt == "pdf":
            from ..services import pdfreport
            data = pdfreport.table_pdf(titulo, cols, filas, [f"{d['n_ovs']} OV · {d['kg']:,.2f} kg por preparar. "
                                                             f"Agrupado por {d['agrupar']}."])
            return send_file(io.BytesIO(data), as_attachment=True, download_name="consolidado_picking.pdf",
                             mimetype="application/pdf")
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Consolidado"
        ws.append(cols)
        for f in filas:
            ws.append(f)
        buf = io.BytesIO()
        wb.save(buf)
        return send_file(io.BytesIO(buf.getvalue()), as_attachment=True, download_name="consolidado_picking.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    clientes = list(db().execute(select(Customer).order_by(Customer.nombre)).scalars())
    almacenes = list(db().execute(select(Warehouse).where(Warehouse.habilitado.is_(True)).order_by(Warehouse.code)).scalars())
    return render_template("v66_consolidado.html", d=d, f=a, clientes=clientes, almacenes=almacenes)


@bp.route("/pedidos-ultima-hora", methods=["GET", "POST"])
@perm_required("almacen.validar_ov_tardia")
def late_orders():
    from ..models import SalesOrder
    from ..services import almacen_v66 as av
    if request.method == "POST":
        o = db().get(SalesOrder, int(request.form.get("oid") or 0)) or abort(404)
        aprobar = request.form.get("aprobar") == "1"
        return act(lambda: av.validar(g.user, o, aprobar, request.form.get("comentario", "")),
                   "Pedido validado: ya se puede preparar." if aprobar else "Pedido observado: se avisó a Comercial.",
                   url_for("alm.late_orders"))
    return render_template("v66_ultima_hora.html", rows=av.por_validar())


# ------------------------------------------------------------------ V70: semáforo de inventarios y rotación
@bp.route("/semaforo")
@login_required
def stock_light():
    """Semáforo de inventarios por familia y producto: lo ven todos los perfiles."""
    from ..services import semaforo as sem
    a = request.args
    d = sem.semaforo(familia=a.get("familia", ""), q=(a.get("q") or "").strip(), tipo=a.get("tipo", ""))
    estado = a.get("estado", "")
    filas = [f for f in d["filas"] if not estado or f["estado"] == estado]
    if a.get("formato") == "xlsx":
        import io
        from flask import send_file
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Semaforo"
        ws.append(["Estado", "Familia", "Código", "Descripción", "Tipo", "UM", "Stock", "OV abiertas", "OV vencidas", "Llegadas",
                   "Saldo", "Venta mensual", "Stock de seguridad", "Plazo días", "Cobertura días", "Sin stock el", "Próx. llegada",
                   "Compra/producción mínima", "Saldo kg"])
        for f in filas:
            ws.append([sem.NOMBRE[f["estado"]], f["familia"], f["code"], f["descripcion"], f["tipo"], f["um"], f["stock"], f["ov"],
                       f["ov_vencidas"], f["llegadas"], f["saldo"], f["venta_mes"], f["seguridad"], f["plazo_dias"],
                       f["cobertura_dias"], f["sin_stock"], f["proxima_llegada"], f["compra_minima"], f["kg"]["saldo"]])
        buf = io.BytesIO()
        wb.save(buf)
        return send_file(io.BytesIO(buf.getvalue()), as_attachment=True, download_name=f"semaforo_{date.today():%Y%m%d}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return render_template("v70_semaforo.html", d=d, filas=paginate(filas, 60), f=a, nombre=sem.NOMBRE)


@bp.route("/rotacion-analisis")
@perm_required("stock.ver", "rotacion.ver", "tablero.empresa", "demanda.ver")
def rotation_analysis():
    """Cómo ha rotado una familia: venta mensual vs el año anterior, picos, presentaciones preferidas, clientes
    habituales y ocasionales, y el stock de seguridad que debería tener."""
    from ..services import charts
    from ..services import semaforo as sem
    a = request.args
    d = sem.rotacion(a.get("familia", ""), code=(a.get("code") or "").strip().upper())
    etiquetas = [m[5:] + "/" + m[2:4] for m in d["meses"]]
    graf = charts.columns(etiquetas, [("Últimos 12 meses (kg)", d["serie"]), ("Año anterior (kg)", d["serie_ant"])], "kg",
                          title="Venta mensual en kg")
    return render_template("v70_rotacion.html", d=d, graf=graf, f=a)


@bp.route("/indicadores")
@perm_required("almacen.indicadores")
def indicators():
    """V70: indicadores de pedidos y operación de Almacén (Líder, Asistente, Supervisor y Coordinador)."""
    from ..services import indicadores_almacen as ia
    return render_template("v70_indicadores.html", d=ia.tablero())


@bp.route("/carga", methods=["GET", "POST"])
@perm_required("picking.asignar", "distribucion.carga", "distribucion.ver", "distribucion.entrega", "tareas.ejecutar",
               "distribucion.programar")
def loading():
    """V70: aviso de carga. El chofer avisa que la unidad está lista (limpia y dentro del almacén 1560 o 1524); al
    almacén que corresponde le llega la alerta; Almacén responde a quién asignó el traslado y la carga y sube las
    fotos del antes y el después y el video."""
    from ..models import Route, User
    from ..services import carga_v70 as cv
    from ..services.distribution import save_evidences
    if request.method == "POST":
        f = request.form
        r = db().get(Route, int(f.get("rid") or 0)) or abort(404)
        acc = f.get("accion")
        back = url_for("alm.loading") + f"#ruta{r.id}"
        if acc == "lista":
            return act(lambda: cv.unidad_lista(g.user, r, f.get("limpia") == "1", f.get("ubicacion"), f.get("otra", ""),
                                               f.get("nota", "")),
                       "Aviso enviado: Almacén recibió la alerta para trasladar y cargar.", back)
        if acc == "responder":
            return act(lambda: cv.responder(g.user, r, f.getlist("asignados"), f.get("nota", "")),
                       "Respuesta enviada al chofer: traslado y carga iniciados.", back)
        if acc == "evidencia":
            def _ev():
                arch = save_evidences(request.files.getlist("archivos"), current_app.config["UPLOAD_DIR"],
                                      f"carga{r.id}_{f.get('etapa', '')}", videos=True, maximo=10)
                return cv.subir_evidencia(g.user, r, f.get("etapa"), arch, f.get("nota", ""))
            return act(_ev, "Evidencia de la carga guardada.", back)
        abort(400)
    rutas = cv.de_hoy()
    personal = list(db().execute(select(User).where(User.activo.is_(True)).order_by(User.nombre)).scalars())
    personal = [u for u in personal if u.role_code in ("AUX_ALMACEN", "MONTACARGUISTA", "LIDER_ALMACEN", "ASIST_ALMACEN",
                                                       "SUPERV_ALMACEN", "AUX_DESPACHO")]
    return render_template("v70_carga.html", rutas=rutas, personal=personal, cv=cv, etapas=cv.ETAPAS,
                           es_chofer=lambda r: r.driver is not None and r.driver.user_id == g.user.id)


@bp.route("/fuera-horario", methods=["GET", "POST"])
@perm_required("ov.aprobar_fuera_horario", "ov.decision_gg", "ov.crear", "ov.modificar", "almacen.validar_ov_tardia",
               "almacen.indicadores")
def out_of_hours():
    """V70: OV ingresadas fuera del horario: solicitud de Comercial, aprobación del Jefe de Operaciones, elevación a
    Gerencia General y lista para Almacén."""
    from ..models import SalesOrder
    from ..services import fuera_horario as fh
    if request.method == "POST":
        f = request.form
        o = db().get(SalesOrder, int(f.get("oid") or 0)) or abort(404)
        acc = f.get("accion")
        c = f.get("comentario", "")
        back = url_for("alm.out_of_hours")
        fns = {"solicitar": lambda: fh.solicitar(g.user, o, c),
               "aprobar": lambda: fh.decidir_jo(g.user, o, True, c), "desestimar": lambda: fh.decidir_jo(g.user, o, False, c),
               "elevar": lambda: fh.elevar(g.user, o, c),
               "aprobar_gg": lambda: fh.decidir_gg(g.user, o, True, c), "rechazar_gg": lambda: fh.decidir_gg(g.user, o, False, c)}
        if acc not in fns:
            abort(400)
        return act(fns[acc], f"OV {o.numero}: listo.", back)
    return render_template("v70_fuera_horario.html", d=fh.listado(), nombre=fh.NOMBRE)
