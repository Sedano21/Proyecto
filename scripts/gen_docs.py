"""Genera docs/06_MODELO_DATOS.md y docs/07_PERFILES_PERMISOS_ALERTAS.md desde el código (fuente única).
Uso: python scripts/gen_docs.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import catalogs as C  # noqa: E402
from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402


def modelo():
    out = ["# Modelo de datos (generado desde `app/models.py`)\n",
           "Motor por defecto: SQLite (prototipo). Portable a PostgreSQL / SQL Server mediante `DATABASE_URL` (SQLAlchemy 2).",
           "Las tablas se crean al iniciar la aplicación (`create_all`). Para producción se recomienda incorporar migraciones (Alembic).\n"]
    for t in Base.metadata.sorted_tables:
        cls = next((m.class_ for m in Base.registry.mappers if m.local_table is t), None)
        doc = (cls.__doc__ or "").strip().replace("\n", " ") if cls else ""
        out.append(f"## `{t.name}`\n\n{doc}\n")
        out.append("| Columna | Tipo | Nulo | Clave / referencia |\n|---|---|---|---|")
        for c in t.columns:
            ref = ", ".join(f"→ {fk.target_fullname}" for fk in c.foreign_keys)
            pk = "PK" if c.primary_key else ""
            out.append(f"| {c.name} | {c.type} | {'sí' if c.nullable else 'no'} | {' '.join(x for x in (pk, ref) if x)} |")
        uq = [cn for cn in t.constraints if cn.__class__.__name__ == "UniqueConstraint"]
        for u in uq:
            out.append(f"\nRestricción única: ({', '.join(c.name for c in u.columns)})")
        out.append("")
    return "\n".join(out)


def perfiles():
    roles = {r[0]: r for r in C.ROLES}
    perms = {p[0]: p for p in C.PERMISSIONS}
    out = ["# Perfiles, permisos y alertas (generado desde `app/catalogs.py`)\n",
           "Origen: **D** = definido expresamente en la documentación; **P** = propuesto (derivado del alcance por área, IF §3), "
           "requiere validación; **PEND** = pendiente. Todo es editable en *Usuarios y permisos* y *Configurar alertas* y queda auditado.\n",
           "## Roles\n", "| Código | Rol | Área | Fuente | Observación |\n|---|---|---|---|---|"]
    for code, nombre, area, fuente, obs in C.ROLES:
        out.append(f"| {code} | {nombre} | {area} | {fuente} | {obs} |")
    out += ["\n## Permisos (separación consulta / edición / aprobación / administración, IF §19)\n",
            "| Permiso | Descripción | Módulo | Tipo |\n|---|---|---|---|"]
    for code, nombre, mod, tipo in C.PERMISSIONS:
        out.append(f"| {code} | {nombre} | {mod} | {tipo} |")
    out += ["\n## Permisos por rol\n"]
    for role, lst in C.ROLE_PERMISSIONS.items():
        seen = {}
        for p, o, f in lst:
            if p in seen and seen[p][0] == "DEFINIDO":
                continue
            seen[p] = (o, f)
        if role in ("GERENCIA_GENERAL", "SISTEMAS"):
            out.append(f"### {roles[role][1]}\n\nTodos los permisos ({len(seen)}) — D: {lst[0][2]}. "
                       "Las aprobaciones no se omiten; quedan auditadas (decisión pendiente IF §15).\n")
            continue
        out.append(f"### {roles[role][1]}\n")
        for p, (o, f) in sorted(seen.items()):
            out.append(f"- `{p}` – {perms[p][1]} (**{'D' if o == 'DEFINIDO' else 'P'}**; {f})")
        out.append("")
    out += ["## Tipos de alerta\n",
            "Canales: panel del módulo y correo (si hay SMTP). Ciclo: Nueva → Asignada → En atención → Cerrada (motivo y acción obligatorios). "
            "Gerencia General ve todo y elige qué recibe por correo; Gerencia de Operaciones ve las áreas de su ámbito (parámetro).\n",
            "| Código | Alerta | Área / grupo | Prioridad | Destinatarios (roles) | Origen dest. | Correo | Condición | Fuente |",
            "|---|---|---|---|---|---|---|---|---|"]
    for code, nombre, area, grupo, prio, rls, origen, fuente, cond, correo in C.ALERT_TYPES:
        out.append(f"| {code} | {nombre} | {area} / {grupo} | {prio} | {', '.join(rls)} | {origen} | {'sí' if correo else 'no'} | {cond} | {fuente} |")
    out += ["\n## Tipos de incidencia (IF §12.3)\n"] + [f"- {c}: {n}" for c, n in C.INCIDENT_TYPES]
    out += ["\n## Parámetros configurables (IF §16)\n", "| Parámetro | Valor inicial | Estado | Descripción | Fuente |\n|---|---|---|---|---|"]
    for key, val, tipo, grupo, desc, estado, fuente in C.PARAMS:
        out.append(f"| {key} | `{val}` | {estado} | {desc} | {fuente} |")
    out += ["\nValores de demostración aplicados por `seed_demo` (estado DEMO): `cortes_preparacion` = 09:00/13:00/16:00, "
            "`dias_vencimiento_proximo` = 30. Plantilla de fases de importación: DEMO.\n"]
    out += ["## Almacenes iniciales\n", "| SAP | Nombre | Uso | Prioridad | Fuente | Observación |\n|---|---|---|---|---|---|"]
    for code, nombre, uso, prio, res, fuente, obs in C.WAREHOUSES:
        out.append(f"| {code} | {nombre} | {uso} | {prio} | {fuente} | {obs} |")
    out += ["\n## Plazos de reposición (IF §7, días naturales)\n", "| Categoría | Mín | Máx | Meses | Descripción |\n|---|---|---|---|---|"]
    for cat, a, b, m1, m2, d in C.LEAD_TIMES:
        out.append(f"| {cat} | {a} | {b} | {f'{m1}-{m2}' if m1 else 'todo el año'} | {d} |")
    return "\n".join(out)


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    open(os.path.join(ROOT, "docs", "06_MODELO_DATOS.md"), "w").write(modelo())
    open(os.path.join(ROOT, "docs", "07_PERFILES_PERMISOS_ALERTAS.md"), "w").write(perfiles())
    print("ok")
