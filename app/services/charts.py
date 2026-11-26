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
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{escape(_corto(v)) if vmax - vmin >= 4 else _fmt(v, 1)}</text>')
    # V43: se muestran tantas etiquetas como quepan sin encimarse (según su largo); la última solo si no choca
    largo = max(len(str(lb)) for lb in labels) * 6.2 + 10
    caben = max(int(w / largo), 1)
    paso = max(1, -(-len(labels) // caben))
    for i, lb in enumerate(labels):
        if i % paso == 0 or (i == len(labels) - 1 and (i % paso) * w / n >= largo):
            ancla = "start" if i == 0 else ("end" if i == len(labels) - 1 else "middle")  # V43: sin cortar en los bordes
            out.append(f'<text x="{x(i):.1f}" y="{height - 8}" class="ax" text-anchor="{ancla}">{escape(str(lb))}</text>')
    for si, (name, pts) in enumerate(series):
        c = SERIES[si]
        validos = [(i, v) for i, (_, v) in enumerate(pts) if v is not None]  # V76: series con semanas sin dato
        d = " ".join(f"{'M' if k == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for k, (i, v) in enumerate(validos))
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


def _corto(v):
    """V43: número compacto para rótulos sobre columnas (1 234 567 → 1,2 M; 147 632 → 148 k; 0,5 → 0,5)."""
    if v is None:
        return ""
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:.1f} M".replace(".", ",")
    if a >= 10_000:
        return f"{v / 1000:.0f} k"
    if a >= 1000:
        return f"{v / 1000:.1f} k".replace(".", ",")
    return f"{v:.0f}" if a >= 10 or float(v).is_integer() else f"{v:.1f}".replace(".", ",")


def columns(labels, series, unit="", width=640, height=240, title="", colors=None):
    """Columnas verticales agrupadas: labels [str], series [(nombre, [valores])].
    V43: nada se encima. El valor va sobre la columna solo si cabe (número compacto, sin ceros); si no cabe, queda en
    el tooltip y en la tabla. Las etiquetas del eje se espacian o se inclinan según el ancho, y la leyenda va debajo."""
    if not labels or not series:
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    pal = colors or SERIES
    vals_all = [v or 0 for _, vals in series for v in vals]
    if not any(vals_all):
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    vmax = _nice_max(max(vals_all + [1]))
    n = len(labels)
    L, R = 46, 8
    gw = (width - L - R) / n
    bw = min(34, max((gw - 10) / len(series), 3))
    largo = max(len(str(lb)) for lb in labels)
    inclinar = largo * 6.2 > gw - 4
    B = (int(min(largo, 16) * 4.2) + 22) if inclinar else 30
    T = 18
    leyenda = len(series) > 1
    height = max(height, 150 + B)
    ph = height - T - B
    minimo = min(int(n * len(series) * 9 + L + R), 1100)  # en pantallas angostas se desplaza en lugar de apretarse
    out = [f'<div class="chart-scroll"><svg class="chart" viewBox="0 0 {width} {height}" style="min-width:{minimo}px" '
           f'role="img" aria-label="{escape(title or "Gráfico de columnas")}">']
    for k in range(5):  # eje y con cuadrícula tenue (la escala no depende de los rótulos sobre las columnas)
        v = vmax * k / 4
        yy = T + ph - v / vmax * ph
        out.append(f'<line x1="{L}" x2="{width - R}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>'
                   f'<text x="{L - 6}" y="{yy + 4:.1f}" class="ax" text-anchor="end">{escape(_corto(v))}</text>')
    paso = 1
    if inclinar:
        paso = max(1, int(14 / max(gw, 1)) + 1) if gw < 14 else 1
    for i, lb in enumerate(labels):
        x0 = L + i * gw + (gw - bw * len(series)) / 2
        for j, (nombre, vals) in enumerate(series):
            v = vals[i] or 0
            h = max(v / vmax * ph, 1 if v else 0)
            x = x0 + j * bw
            out.append(f'<rect x="{x:.1f}" y="{T + ph - h:.1f}" width="{max(bw - 2, 2):.1f}" height="{h:.1f}" rx="3" '
                       f'fill="{pal[j % len(pal)]}"><title>{escape(str(lb))} · {escape(nombre)}: {_fmt(v, 2)} {escape(unit)}'
                       f'</title></rect>')
            txt = _corto(v)
            if v and len(txt) * 6.2 <= bw + 2:
                out.append(f'<text x="{x + (bw - 2) / 2:.1f}" y="{T + ph - h - 4:.1f}" class="val" text-anchor="middle">'
                           f'{escape(txt)}</text>')
        if i % paso:
            continue
        lbl = str(lb) if len(str(lb)) <= 16 else str(lb)[:15] + "…"
        cx = L + i * gw + gw / 2 + (4 if inclinar else 0)
        if inclinar:
            out.append(f'<text x="{cx:.1f}" y="{T + ph + 12}" class="ax" text-anchor="end" '
                       f'transform="rotate(-40 {cx:.1f} {T + ph + 12})">{escape(lbl)}</text>')
        else:
            out.append(f'<text x="{cx:.1f}" y="{T + ph + 16}" class="ax" text-anchor="middle">{escape(lbl)}</text>')
    out.append("</svg></div>")
    if leyenda:
        out.append('<div class="legend">' + "".join(f'<span><i style="background:{pal[j % len(pal)]}"></i>{escape(nm)}</span>'
                                                    for j, (nm, _) in enumerate(series)) + "</div>")
    out.append('<p class="small muted chart-nota">Pase el cursor (o toque) una columna para ver su valor exacto.</p>'
               if any(v and len(_corto(v)) * 6.2 > bw + 2 for v in vals_all) else "")
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


def donut_parts(items, etiqueta="Total", size=170, max_items=8):
    """V23: anillo por partes [(nombre, valor)] con el total al centro y leyenda con % (tablero del embudo)."""
    import math
    items = [(n, v) for n, v in items if v][:max_items]
    total = sum(v for _, v in items)
    if not total:
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    r, c = 58, size / 2
    largo = 2 * math.pi * r
    out = [f'<div class="donut-parts"><svg class="chart donut" viewBox="0 0 {size} {size}" width="{size}" role="img" '
           f'aria-label="{escape(etiqueta)}: {_fmt(total, 0)}">']
    acum = 0.0
    for i, (n, v) in enumerate(items):
        seg = largo * v / total
        out.append(f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{SERIES[i % len(SERIES)]}" stroke-width="20" '
                   f'stroke-dasharray="{seg:.2f} {largo:.2f}" stroke-dashoffset="{-acum:.2f}" transform="rotate(-90 {c} {c})">'
                   f'<title>{escape(str(n))}: {_fmt(v, 0)} ({100 * v / total:.0f} %)</title></circle>')
        acum += seg
    out.append(f'<text x="{c}" y="{c + 4}" text-anchor="middle" class="donut-v">{_fmt(total, 0)}</text>'
               f'<text x="{c}" y="{c + 22}" text-anchor="middle" class="ax">{escape(etiqueta)}</text></svg><ul class="legend-v">')
    for i, (n, v) in enumerate(items):
        out.append(f'<li><i style="background:{SERIES[i % len(SERIES)]}"></i>{escape(str(n))} <b>{_fmt(v, 0)}</b> '
                   f'<span class="muted">{100 * v / total:.0f} %</span></li>')
    out.append("</ul></div>")
    return Markup("".join(out))


def funnel_shape(stages, width=360):
    """V23: embudo dibujado (trapecios) [(nombre, n)], como el tablero de prospectos."""
    stages = [(n, v) for n, v in stages]
    if not stages or not any(v for _, v in stages):
        return Markup('<p class="muted small">Sin datos para el periodo.</p>')
    alto = 34
    h = alto * len(stages) + 10
    out = [f'<svg class="chart" viewBox="0 0 {width} {h}" role="img" aria-label="Embudo">']
    for i, (n, v) in enumerate(stages):
        w1 = width * (1 - 0.7 * i / len(stages))
        w2 = width * (1 - 0.7 * (i + 1) / len(stages))
        y = 5 + i * alto
        x1, x2 = (width - w1) / 2, (width - w2) / 2
        out.append(f'<polygon points="{x1:.1f},{y} {x1 + w1:.1f},{y} {x2 + w2:.1f},{y + alto - 3} {x2:.1f},{y + alto - 3}" '
                   f'fill="{SERIES[i % len(SERIES)]}"><title>{escape(str(n))}: {v}</title></polygon>'
                   f'<text x="{width / 2}" y="{y + alto / 2 + 2}" text-anchor="middle" fill="#fff" font-size="12" '
                   f'font-weight="700">{escape(str(n))}: {v}</text>')
    out.append("</svg>")
    return Markup("".join(out))
