"""Gráficos SVG en línea para informes (sin librerías externas: la instalación es local, sin depender de internet).

Paleta categórica fija (orden constante; el color sigue a la serie, no al rango). Marcas finas: líneas de 2 px,
barras con extremo redondeado y separación de 2 px, cuadrícula tenue. Cada punto/barra lleva un tooltip (<title>) y
cada gráfico va acompañado de su tabla de datos en la plantilla.
"""
from html import escape

from markupsafe import Markup

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def _fmt(v, dec=1):
    if v is None:
        return "-"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:,.{dec}f}".replace(",", " ")


def _nice_max(m):
    if m <= 0:
        return 1
    import math
    e = 10 ** math.floor(math.log10(m))
    for k in (1, 2, 2.5, 5, 10):
        if m <= k * e:
            return k * e
    return 10 * e


def line(series, unit="", height=220, width=640, title=""):
    """series: [(nombre, [(etiqueta, valor), ...]), ...] con las mismas etiquetas en el mismo orden."""
    series = [(n, pts) for n, pts in series if pts][:8]
    if not series:
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    labels = [l for l, _ in series[0][1]]
    vals = [v for _, pts in series for _, v in pts if v is not None]
    if not any(vals):  # una línea plana en cero no informa nada: se dice que no hay datos
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    vmax = _nice_max(max(vals) if vals else 1)
    vmin = min(0, min(vals) if vals else 0)
    L, R, T, B = 48, 12, 12, 28
    w, h = width - L - R, height - T - B
    n = max(len(labels) - 1, 1)

    def x(i):
        return L + w * i / n

    def y(v):
        return T + h - (v - vmin) / (vmax - vmin or 1) * h
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title or "Gráfico de líneas")}">']
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4
        out.append(f'<line x1="{L}" x2="{width - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{_fmt(v, 0 if vmax - vmin >= 4 else 1)}</text>')
    paso = max(1, len(labels) // 8)
    for i, lb in enumerate(labels):
        if i % paso == 0 or i == len(labels) - 1:
            out.append(f'<text x="{x(i):.1f}" y="{height - 8}" class="ax" text-anchor="middle">{escape(str(lb))}</text>')
    for si, (name, pts) in enumerate(series):
        c = SERIES[si]
        d = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(pts) if v is not None)
        out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>')
        for i, (lb, v) in enumerate(pts):
            if v is None:
                continue
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{c}" stroke="var(--panel,#fff)" stroke-width="2">'
                       f'<title>{escape(name)} · {escape(str(lb))}: {_fmt(v, 2)} {escape(unit)}</title></circle>')
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="10" fill="transparent"><title>{escape(name)} · '
                       f'{escape(str(lb))}: {_fmt(v, 2)} {escape(unit)}</title></circle>')
    out.append("</svg>")
    if len(series) > 1:
        out.append('<div class="legend">' + "".join(f'<span><i style="background:{SERIES[i]}"></i>{escape(n)}</span>'
                                                    for i, (n, _) in enumerate(series)) + "</div>")
    return Markup("".join(out))


def bars(items, unit="", width=640, title="", color=0, max_items=15):
    """Barras horizontales ordenadas: items [(etiqueta, valor)]. Etiqueta y valor directos en cada barra."""
    items = [(l, v) for l, v in items if v is not None][:max_items]
    if not items:
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    vmax = max(abs(v) for _, v in items) or 1
    rh, gap, L, R = 22, 2, 170, 70
    height = len(items) * (rh + gap) + 4
    w = width - L - R
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title or "Gráfico de barras")}">']
    for i, (lb, v) in enumerate(items):
        yy = 2 + i * (rh + gap)
        bw = max(abs(v) / vmax * w, 2)
        lbl = str(lb) if len(str(lb)) <= 26 else str(lb)[:25] + "…"
        out.append(f'<text x="{L - 6}" y="{yy + rh / 2 + 4}" class="ax" text-anchor="end">{escape(lbl)}</text>'
                   f'<rect x="{L}" y="{yy}" width="{bw:.1f}" height="{rh}" rx="4" fill="{SERIES[color % 8] if v >= 0 else SERIES[7]}">'
                   f'<title>{escape(str(lb))}: {_fmt(v, 2)} {escape(unit)}</title></rect>'
                   f'<text x="{L + bw + 4:.1f}" y="{yy + rh / 2 + 4}" class="val">{_fmt(v)}{escape(unit[:3] if unit == "%" else "")}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def kpi(valor, etiqueta, sub="", unidad=""):
    return Markup(f'<div class="kpi"><b>{_fmt(valor) if isinstance(valor, (int, float)) else escape(str(valor))}'
                  f'{escape(unidad)}</b><span>{escape(etiqueta)}</span>{f"<small>{escape(sub)}</small>" if sub else ""}</div>')


def columns(labels, series, unit="", width=640, height=240, title="", colors=None):
    """Columnas verticales agrupadas: labels [str], series [(nombre, [valores])]. Valor sobre cada columna y leyenda."""
    if not labels or not series:
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    pal = colors or SERIES
    vmax = _nice_max(max([v or 0 for _, vals in series for v in vals] + [1]))
    T, B, L, R = 22, 46, 8, 8
    ph = height - T - B
    gw = (width - L - R) / len(labels)
    bw = min(34, (gw - 12) / len(series))
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title or "Gráfico de columnas")}">',
           f'<line x1="{L}" x2="{width - R}" y1="{T + ph}" y2="{T + ph}" class="grid"/>']
    for i, lb in enumerate(labels):
        x0 = L + i * gw + (gw - bw * len(series)) / 2
        for j, (nombre, vals) in enumerate(series):
            v = vals[i] or 0
            h = max(v / vmax * ph, 1 if v else 0)
            x = x0 + j * bw
            out.append(f'<rect x="{x:.1f}" y="{T + ph - h:.1f}" width="{bw - 3:.1f}" height="{h:.1f}" rx="3" fill="{pal[j % len(pal)]}">'
                       f'<title>{escape(str(lb))} · {escape(nombre)}: {_fmt(v, 2)} {escape(unit)}</title></rect>'
                       f'<text x="{x + (bw - 3) / 2:.1f}" y="{T + ph - h - 4:.1f}" class="val" text-anchor="middle">{_fmt(v)}</text>')
        lbl = str(lb) if len(str(lb)) <= 14 else str(lb)[:13] + "…"
        out.append(f'<text x="{L + i * gw + gw / 2:.1f}" y="{T + ph + 16}" class="ax" text-anchor="middle">{escape(lbl)}</text>')
    if len(series) > 1:
        x = L
        for j, (nombre, _) in enumerate(series):
            out.append(f'<rect x="{x}" y="{height - 14}" width="10" height="10" rx="2" fill="{pal[j % len(pal)]}"/>'
                       f'<text x="{x + 14}" y="{height - 5}" class="ax">{escape(nombre)}</text>')
            x += 18 + 8 * len(nombre)
    out.append("</svg>")
    return Markup("".join(out))


def donut(pct, etiqueta="", size=150, colors=None):
    """Anillo con el porcentaje al centro (p. ej. asistencia general)."""
    if pct is None:
        return Markup('<p class="muted small">Sin datos.</p>')
    import math
    pal = colors or SERIES
    r, c = 52, size / 2
    largo = 2 * math.pi * r
    hecho = largo * max(min(pct, 100), 0) / 100
    return Markup(f'<svg class="chart donut" viewBox="0 0 {size} {size}" width="{size}" role="img" aria-label="{escape(etiqueta)} {pct}%">'
                  f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{pal[1]}" stroke-opacity=".25" stroke-width="16"/>'
                  f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{pal[0]}" stroke-width="16" stroke-dasharray="{hecho:.1f} {largo:.1f}"'
                  f' transform="rotate(-90 {c} {c})"/><text x="{c}" y="{c + 2}" text-anchor="middle" class="donut-v">{pct:g}%</text>'
                  f'<text x="{c}" y="{c + 20}" text-anchor="middle" class="ax">{escape(etiqueta)}</text></svg>')
