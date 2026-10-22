/* Homebase Charts — HBPineLayer: what a Pine script draws besides its lines, one canvas primitive on the price pane
   (the pineworker.js result's boxes, lines, labels, linefills, polylines, tables, and the bgcolor() stripes).
     - boxes, lines, linefills and polylines: x is a bar_index (0 = the run's first bar, result.firstMs) or, with
       xloc.bar_time, a time; both become the chart's logical index, so a future bar_index runs past the last bar;
       `extend` pushes a line or a box to the pane's edge;
     - labels: Pine's bubble styles (pointer or corner on the point), the shape styles and text only; yloc abovebar /
       belowbar sit on the bar's high / low;
     - tables: the pane's nine corners, cells with their own text, size and background;
     - bgcolor stripes: behind the candles, one rectangle per run of same-coloured bars.
   Colours are taken as the worker gives them ('#RRGGBB', '#RRGGBBAA', rgba()); `na` (null) draws nothing and a colour the
   script left out gets Pine's own default. At most 500 objects of a kind are kept (the newest), and an object wholly
   outside the pane is skipped. The page owns the layer: `new PineLayer(P, cell)`, cell.candles.attachPrimitive(layer),
   layer.update(result) on every worker result. The pure half has no browser globals at load time: the Node tests load
   this file directly. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const D = need('HBDrawings', './drawings.js');         // xOfLogical
const LQ = need('HBLiquidity', './liquidity.js');       // logicalAt

const MAX_OBJECTS = 500;       // Pine's own cap per kind: the newest are kept
const KINDS = ['boxes', 'lines', 'labels', 'linefills', 'polylines'];
const EDGE = 50;               // px past the pane an object may reach before it is skipped
const PAD = 4;                 // px between a text and the edge of its box, bubble or cell
const GAP = 6;                 // px a label's pointer is long
const BLUE = '#2962FF';        // Pine's colour for a line, label or box left without one
const FONT = '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
const TEXT_PX = { auto: 12, tiny: 8, small: 10, normal: 12, large: 16, huge: 24 };
const EXTEND = { l: [1, 0], left: [1, 0], r: [0, 1], right: [0, 1], b: [1, 1], both: [1, 1] };
const LABEL_AT = {             // a label style -> its bubble's top-left from the point (x, y), and the side its pointer leaves from
  style_label_down: (x, y, w, h) => [x - w / 2, y - h - GAP, 'down'],
  style_label_up: (x, y, w, h) => [x - w / 2, y + GAP, 'up'],
  style_label_left: (x, y, w, h) => [x + GAP, y - h / 2, 'left'],
  style_label_right: (x, y, w, h) => [x - w - GAP, y - h / 2, 'right'],
  style_label_lower_left: (x, y, w, h) => [x, y - h, null],
  style_label_lower_right: (x, y, w, h) => [x - w, y - h, null],
  style_label_upper_left: (x, y, w, h) => [x, y, null],
  style_label_upper_right: (x, y, w, h) => [x - w, y, null],
  style_label_center: (x, y, w, h) => [x - w / 2, y - h / 2, null]
};
const SHAPES = {               // the shape styles as polygons in units of the marker radius; arrows have their tip on (0, 0)
  square: [[-1, -1], [1, -1], [1, 1], [-1, 1]],
  diamond: [[0, -1], [1, 0], [0, 1], [-1, 0]],
  triangleup: [[0, -1], [1, 1], [-1, 1]],
  triangledown: [[0, 1], [1, -1], [-1, -1]],
  flag: [[-1, -1], [1, -0.35], [-0.6, 0.1], [-0.6, 1], [-1, 1]],
  arrowup: [[0, 0], [1, 1], [0.4, 1], [0.4, 2.4], [-0.4, 2.4], [-0.4, 1], [-1, 1]],
  arrowdown: [[0, 0], [1, -1], [0.4, -1], [0.4, -2.4], [-0.4, -2.4], [-0.4, -1], [-1, -1]]
};
const CROSSES = { cross: [[-1, 0, 1, 0], [0, -1, 0, 1]], xcross: [[-1, -1, 1, 1], [-1, 1, 1, -1]] };

/* ---------------------------------------------------------------- pure */

const rgba = (r, g, b, a) => `rgba(${r},${g},${b},${+Math.max(0, Math.min(1, a)).toFixed(3)})`;

/* A Pine colour as a CSS one. null is `na` (draw nothing); '' is a colour the script left out (`dflt`, Pine's own). */
function parseColor(c, dflt = null) {
  if (c == null) return null;
  const s = String(c).trim();
  if (!s) return dflt;
  let m = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(s);
  if (m) {
    const h = m[1].length < 6 ? m[1].replace(/./g, '$&$&') : m[1], n = parseInt(h.slice(0, 6), 16);
    return rgba((n >> 16) & 255, (n >> 8) & 255, n & 255, h.length === 8 ? parseInt(h.slice(6), 16) / 255 : 1);
  }
  m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i.exec(s);
  return m ? rgba(+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]) : dflt;
}

/* A Pine size (size.small ... or a number of points) as a font size in px. */
const textPx = (s) => (typeof s === 'number' && s > 0 ? s : TEXT_PX[s] || TEXT_PX.normal);

const dashOf = (style) => (/dashed/.test(style) ? [6, 4] : /dotted/.test(style) ? [2, 3] : []);

/* The newest `n` of a list the worker built oldest first. */
const newest = (list, n = MAX_OBJECTS) => (list.length > n ? list.slice(list.length - n) : list);

/* Wholly beyond a pane `size` px long (the span a..b, in either order). */
const outside = (a, b, size) => Math.max(a, b) < -EDGE || Math.min(a, b) > size + EDGE;

/* The chart bar bar_index 0 is: the last bar starting at or before the run's first bar (before them all: counted back). */
function baseIndex(bars, firstMs, barMs) {
  let a = 0, b = bars.length;
  while (a < b) { const m = (a + b) >> 1; if (bars[m].ms <= firstMs) a = m + 1; else b = m; }
  if (a > 0) return a - 1;
  return barMs > 0 ? -Math.round((bars[0].ms - firstMs) / barMs) : 0;
}

/* A Pine x as a chart logical index (bar i's centre = i): a bar_index counts from `f.base`, a bar_time sits between bars. */
function logicalOf(v, xloc, f) {
  if (!Number.isFinite(v)) return null;
  if (xloc !== 'bt' && xloc !== 'bar_time') return f.base + v;
  const L = LQ.logicalAt(f.bars, v, f.barMs, f.end);      // logicalAt puts a bar's start at i - 0.5
  return L == null ? null : L + 0.5;
}
const xOf = (v, xloc, f) => D.xOfLogical(logicalOf(v, xloc, f), f.XI);
const yOf = (p, f) => (Number.isFinite(p) ? f.Y(p) : null);

/* A segment (pixel ends) pushed out along its slope: `left` from its leftmost end, `right` from its rightmost, to `w` px
   and `EDGE` beyond. A vertical one has no slope to follow. The ends stay in the caller's order. */
function extendSpan(x1, y1, x2, y2, left, right, w) {
  if (x1 === x2 || (!left && !right)) return [x1, y1, x2, y2];
  const m = (y2 - y1) / (x2 - x1), yAt = (x) => y1 + m * (x - x1), flip = x1 > x2;
  let [ax, ay, bx, by] = flip ? [x2, y2, x1, y1] : [x1, y1, x2, y2];
  if (left && ax > -EDGE) { ax = -EDGE; ay = yAt(ax); }
  if (right && bx < w + EDGE) { bx = w + EDGE; by = yAt(bx); }
  return flip ? [bx, by, ax, ay] : [ax, ay, bx, by];
}

/* A line object as {a: its two points, s: the same pushed out by its extend}, in pixels, or null when it can't be placed. */
function lineSeg(l, f, w) {
  const x1 = xOf(l.x1, l.xloc, f), x2 = xOf(l.x2, l.xloc, f), y1 = yOf(l.y1, f), y2 = yOf(l.y2, f);
  if (x1 == null || x2 == null || y1 == null || y2 == null) return null;
  const [left, right] = EXTEND[l.extend] || [0, 0];
  return { a: [x1, y1, x2, y2], s: extendSpan(x1, y1, x2, y2, left, right, w) };
}

/* The area between two segments over the x range they share, as 4 corners, or null when they share none. */
function fillQuad(s, t) {
  const lo = Math.max(Math.min(s[0], s[2]), Math.min(t[0], t[2])), hi = Math.min(Math.max(s[0], s[2]), Math.max(t[0], t[2]));
  if (!(hi > lo)) return null;
  const at = (u, x) => u[1] + (u[3] - u[1]) * (x - u[0]) / (u[2] - u[0]);
  return [[lo, at(s, lo)], [hi, at(s, hi)], [hi, at(t, hi)], [lo, at(t, lo)]];
}

/* A label bubble of w x h for its style at the point (x, y): {x, y} its top-left, `point` the side its pointer leaves from. */
function labelRect(style, x, y, w, h) {
  const [rx, ry, point] = (LABEL_AT[style] || LABEL_AT.style_label_down)(x, y, w, h);
  return { x: rx, y: ry, w, h, point };
}

/* Where text of a height `th` starts in a rect, and the x it is aligned on. */
function placeText(ha, va, r, th, pad = PAD) {
  return { x: ha === 'left' ? r.x + pad : ha === 'right' ? r.x + r.w - pad : r.x + r.w / 2,
           top: va === 'top' ? r.y + pad : va === 'bottom' ? r.y + r.h - pad - th : r.y + (r.h - th) / 2 };
}

const lineH = (px) => px * 1.25;

/* A table's pixel layout in a pane W x H: columns as wide and rows as high as their widest / tallest cell (a cell's own
   width / height is a percent of the pane), the table in its corner, and each cell's rect (a merge's origin spans it).
   `measure(text, px)` is the width of a line of text. t.cells is rows of columns, null where no cell was set. */
function tableLayout(t, measure, W, H) {
  const nc = t.columns | 0, nr = t.rows | 0;
  if (!(nc > 0 && nr > 0)) return null;
  const at = (c, r) => (t.cells && t.cells[r] && t.cells[r][c]) || null, covered = new Set(), span = new Map();
  for (const m of t.merges || []) {
    span.set(m.startCol + ',' + m.startRow, m);
    for (let r = m.startRow; r <= m.endRow; r++) for (let c = m.startCol; c <= m.endCol; c++) covered.add(c + ',' + r);
  }
  const sizeOf = (cell) => {
    const px = textPx(cell.text_size), lines = String(cell.text ?? '').split('\n');
    return [cell.width > 0 ? W * cell.width / 100 : Math.max(...lines.map((s) => measure(s, px))) + 2 * PAD,
      cell.height > 0 ? H * cell.height / 100 : lines.length * lineH(px) + 2 * PAD];
  };
  const cw = new Array(nc).fill(0), rh = new Array(nr).fill(0), merged = [];
  for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
    const cell = at(c, r), m = span.get(c + ',' + r);
    if (!cell || (covered.has(c + ',' + r) && !m)) continue;
    const [w, h] = sizeOf(cell);
    if (m) merged.push([m, w, h]);
    if (!m || m.endCol === c) cw[c] = Math.max(cw[c], w);      // a merged cell sizes only the lines it sits in alone
    if (!m || m.endRow === r) rh[r] = Math.max(rh[r], h);
  }
  const sum = (a, from, to) => a.slice(from, to).reduce((s, v) => s + v, 0);
  for (const [m, w, h] of merged) {                            // ... and widens its last column / row when its text needs more
    if (m.endCol > m.startCol) cw[m.endCol] += Math.max(0, w - sum(cw, m.startCol, m.endCol + 1));
    if (m.endRow > m.startRow) rh[m.endRow] += Math.max(0, h - sum(rh, m.startRow, m.endRow + 1));
  }
  const w = sum(cw, 0, nc), h = sum(rh, 0, nr);
  const [v, ha] = String(t.position || 'top_right').split('_');
  const x0 = ha === 'left' ? PAD : ha === 'center' ? (W - w) / 2 : W - w - PAD;
  const y0 = v === 'bottom' ? H - h - PAD : v === 'middle' ? (H - h) / 2 : PAD;
  const cells = [];
  for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
    const cell = at(c, r), key = c + ',' + r, m = span.get(key);
    if (!cell || (covered.has(key) && !m)) continue;
    const c2 = m ? m.endCol + 1 : c + 1, r2 = m ? m.endRow + 1 : r + 1;
    cells.push({ cell, x: x0 + sum(cw, 0, c), y: y0 + sum(rh, 0, r), w: sum(cw, c, c2), h: sum(rh, r, r2) });
  }
  return { x: x0, y: y0, w, h, cells };
}

/* The bgcolor stripes in bars i0..i1: runs of same-coloured bars as {x0, x1, c}. colorOf(bar) is a CSS colour or undefined;
   XI(i) is a bar's centre; each bar owns `half` px either side of it. */
function bgRuns(bars, i0, i1, colorOf, XI, half) {
  const runs = [];
  let run = null;
  for (let i = i0; i <= i1; i++) {
    const c = colorOf(bars[i]), x = XI(i);
    if (c && x != null && run && run.c === c) run.x1 = x + half;
    else if (c && x != null) runs.push(run = { x0: x - half, x1: x + half, c });
    else run = null;
  }
  return runs;
}

const api = { MAX_OBJECTS, EDGE, parseColor, textPx, dashOf, newest, outside, baseIndex, logicalOf, extendSpan, lineSeg, fillQuad,
  labelRect, placeText, tableLayout, bgRuns };

/* ---------------------------------------------------------------- browser */

if (typeof window !== 'undefined' && window.HBLayers) {
  /* Text in a rect, lines stacked and aligned as Pine says. */
  function paintText(ctx, text, px, color, ha, va, r) {
    const lines = String(text).split('\n'), lh = lineH(px), p = placeText(ha, va, r, lines.length * lh);
    ctx.font = `${px}px ${FONT}`; ctx.fillStyle = color; ctx.textBaseline = 'middle';
    ctx.textAlign = ha === 'left' || ha === 'right' ? ha : 'center';
    lines.forEach((s, i) => ctx.fillText(s, p.x, p.top + (i + 0.5) * lh));
  }

  function polygon(ctx, pts) {
    ctx.beginPath();
    pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
  }

  function paintBox(ctx, b, f, W, H) {
    const xa = xOf(b.left, b.xloc, f), xb = xOf(b.right, b.xloc, f), ya = yOf(b.top, f), yb = yOf(b.bottom, f);
    if (xa == null || xb == null || ya == null || yb == null) return;
    const [left, right] = EXTEND[b.extend] || [0, 0];
    const x0 = left ? -EDGE : Math.min(xa, xb), x1 = right ? W + EDGE : Math.max(xa, xb), y0 = Math.min(ya, yb), h = Math.abs(yb - ya);
    if (outside(x0, x1, W) || outside(y0, y0 + h, H)) return;
    const fill = parseColor(b.bgcolor, BLUE), line = parseColor(b.border_color, BLUE), tc = parseColor(b.text_color, '#000000');
    if (fill) { ctx.fillStyle = fill; ctx.fillRect(x0, y0, x1 - x0, h); }
    if (line && b.border_width > 0) {
      ctx.strokeStyle = line; ctx.lineWidth = b.border_width; ctx.setLineDash(dashOf(b.border_style));
      ctx.strokeRect(x0, y0, x1 - x0, h); ctx.setLineDash([]);
    }
    if (b.text && tc) paintText(ctx, b.text, textPx(b.text_size), tc, b.text_halign, b.text_valign, { x: x0, y: y0, w: x1 - x0, h });
  }

  function arrowHead(ctx, fx, fy, tx, ty, w) {      // a triangle on (tx, ty) pointing along the way from (fx, fy)
    const a = Math.atan2(ty - fy, tx - fx), s = 4 + 2 * w;
    ctx.beginPath(); ctx.moveTo(tx, ty);
    ctx.lineTo(tx - s * Math.cos(a - 0.45), ty - s * Math.sin(a - 0.45));
    ctx.lineTo(tx - s * Math.cos(a + 0.45), ty - s * Math.sin(a + 0.45));
    ctx.closePath(); ctx.fill();
  }

  function paintLine(ctx, l, f, W, H) {
    const color = parseColor(l.color, BLUE), p = color && lineSeg(l, f, W);
    if (!p || outside(p.s[0], p.s[2], W) || outside(p.s[1], p.s[3], H)) return;
    const w = Math.max(1, +l.width || 1);
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = w; ctx.setLineDash(dashOf(l.style));
    ctx.beginPath(); ctx.moveTo(p.s[0], p.s[1]); ctx.lineTo(p.s[2], p.s[3]); ctx.stroke();
    ctx.setLineDash([]);
    if (/arrow_(left|both)/.test(l.style)) arrowHead(ctx, p.a[2], p.a[3], p.a[0], p.a[1], w);      // "left" is the first point
    if (/arrow_(right|both)/.test(l.style)) arrowHead(ctx, p.a[0], p.a[1], p.a[2], p.a[3], w);
  }

  function paintLinefill(ctx, lf, f, W) {
    const color = parseColor(lf.color, BLUE), a = lf.line1 && lineSeg(lf.line1, f, W), b = lf.line2 && lineSeg(lf.line2, f, W);
    const q = color && a && b && fillQuad(a.s, b.s);
    if (!q) return;
    ctx.fillStyle = color; polygon(ctx, q); ctx.fill();
  }

  function paintPolyline(ctx, p, f, W, H) {
    const pts = [];
    for (const q of p.points || []) {
      const bt = p.xloc === 'bt' ? q.time != null : q.index == null;      // a point says whether it was given an index or a time
      const x = xOf(bt ? q.time : q.index, bt ? 'bt' : 'bi', f), y = yOf(q.price, f);
      if (x == null || y == null) return;
      pts.push([x, y]);
    }
    if (pts.length < 2) return;
    const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
    if (outside(Math.min(...xs), Math.max(...xs), W) || outside(Math.min(...ys), Math.max(...ys), H)) return;
    const trace = () => {
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      if (p.curved && pts.length > 2) {      // each point a control point, the curve through the midpoints between them
        for (let i = 1; i < pts.length - 1; i++) ctx.quadraticCurveTo(pts[i][0], pts[i][1], (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2);
        ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      } else for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    };
    const fill = parseColor(p.fill_color), line = parseColor(p.line_color, BLUE);
    if (fill) { trace(); ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); }
    if (line) {
      trace(); if (p.closed) ctx.closePath();
      ctx.strokeStyle = line; ctx.lineWidth = Math.max(1, +p.line_width || 1); ctx.setLineDash(dashOf(p.line_style)); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  /* The y a label hangs on: its price, or the bar's high (abovebar) / low (belowbar). */
  function labelY(l, f) {
    if (l.yloc !== 'ab' && l.yloc !== 'bl') return yOf(l.y, f);
    const L = logicalOf(l.x, l.xloc, f), bar = L == null ? null : f.bars[Math.round(L)];
    return yOf(bar ? (l.yloc === 'ab' ? bar.h : bar.l) : l.y, f);
  }

  function paintLabel(ctx, l, f, W, H) {
    const x = xOf(l.x, l.xloc, f), y = labelY(l, f);
    if (x == null || y == null || outside(x, x, W) || outside(y, y, H)) return;
    const px = textPx(l.size), text = String(l.text ?? ''), bg = parseColor(l.color, BLUE), tc = parseColor(l.textcolor, '#FFFFFF');
    const kind = String(l.style || 'style_label_down').replace('style_', '');
    ctx.font = `${px}px ${FONT}`;
    const lines = text.split('\n'), w = Math.max(0, ...lines.map((s) => ctx.measureText(s).width)) + 2 * PAD, h = lines.length * lineH(px) + 2 * PAD;
    if (SHAPES[kind] || CROSSES[kind] || kind === 'circle') {         // a marker on the point, the text beside it
      const r = Math.max(3, px * 0.45), up = kind === 'arrowdown' || kind === 'triangledown';
      if (bg) {
        ctx.fillStyle = bg; ctx.strokeStyle = bg; ctx.lineWidth = 2;
        if (kind === 'circle') { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); }
        else if (CROSSES[kind]) { ctx.beginPath(); for (const [a, b, c, d] of CROSSES[kind]) { ctx.moveTo(x + a * r, y + b * r); ctx.lineTo(x + c * r, y + d * r); } ctx.stroke(); }
        else { polygon(ctx, SHAPES[kind].map(([a, b]) => [x + a * r, y + b * r])); ctx.fill(); }
      }
      if (text && tc) {
        const reach = kind.startsWith('arrow') ? 2.4 * r : r;
        paintText(ctx, text, px, tc, l.textalign, 'top', { x: x - w / 2, y: up ? y - reach - 2 - h : y + reach + 2, w, h });
      }
      return;
    }
    if (kind === 'none') { if (text && tc) paintText(ctx, text, px, tc, l.textalign, 'center', { x: x - w / 2, y: y - h / 2, w, h }); return; }
    const r = labelRect(l.style, x, y, w, h);
    if (outside(r.x, r.x + w, W) || outside(r.y, r.y + h, H)) return;
    if (bg) {
      ctx.fillStyle = bg; ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(r.x, r.y, w, h, 3); else ctx.rect(r.x, r.y, w, h);
      ctx.fill();
      if (r.point) {                         // the pointer: a small triangle from the bubble's edge to the point
        const cx = r.x + w / 2, cy = r.y + h / 2;
        polygon(ctx, r.point === 'down' ? [[cx - 4, r.y + h - 1], [cx + 4, r.y + h - 1], [x, y]]
          : r.point === 'up' ? [[cx - 4, r.y + 1], [cx + 4, r.y + 1], [x, y]]
          : r.point === 'left' ? [[r.x + 1, cy - 4], [r.x + 1, cy + 4], [x, y]] : [[r.x + w - 1, cy - 4], [r.x + w - 1, cy + 4], [x, y]]);
        ctx.fill();
      }
    }
    if (text && tc) paintText(ctx, text, px, tc, l.textalign, 'center', r);
  }

  function paintTable(ctx, t, W, H) {
    const L = tableLayout(t, (s, px) => { ctx.font = `${px}px ${FONT}`; return ctx.measureText(s).width; }, W, H);
    if (!L) return;
    const bg = parseColor(t.bgcolor), frame = parseColor(t.frame_color), border = parseColor(t.border_color);
    if (bg) { ctx.fillStyle = bg; ctx.fillRect(L.x, L.y, L.w, L.h); }
    for (const c of L.cells) {
      const cb = parseColor(c.cell.bgcolor), tc = parseColor(c.cell.text_color, '#000000');
      if (cb) { ctx.fillStyle = cb; ctx.fillRect(c.x, c.y, c.w, c.h); }
      if (border && t.border_width > 0) { ctx.strokeStyle = border; ctx.lineWidth = t.border_width; ctx.strokeRect(c.x, c.y, c.w, c.h); }
      if (c.cell.text && tc) paintText(ctx, c.cell.text, textPx(c.cell.text_size), tc, c.cell.text_halign, c.cell.text_valign, c);
    }
    if (frame && t.frame_width > 0) { ctx.strokeStyle = frame; ctx.lineWidth = t.frame_width; ctx.strokeRect(L.x, L.y, L.w, L.h); }
  }

  class PineLayer extends window.HBLayers.Layer {
    /* `host` is the chart's cell: its bars, and barMs() (0 on a chart that is not time bars). */
    constructor(P, host) {
      super(P);
      this.host = host;
      this.firstMs = null;           // ms of bar_index 0
      this.o = { boxes: [], lines: [], labels: [], linefills: [], polylines: [], tables: [] };
      this.bg = new Map();           // plot title -> Map(bar ms -> CSS colour) of a bgcolor() plot
      this._views = [
        { zOrder: () => 'bottom', renderer: () => ({ draw: (t) => this.drawBg(t) }) },
        { zOrder: () => 'top', renderer: () => ({ draw: (t) => this.draw(t) }) }];
    }

    /* A worker result: the drawing lists are replaced whole; the bgcolor points of a partial result (full: false) are merged by bar. */
    update(r) {
      if (!r) return;
      if (r.firstMs != null) this.firstMs = r.firstMs;
      for (const k of KINDS) this.o[k] = newest(r[k] || []);
      const byPosition = new Map();
      for (const t of r.tables || []) byPosition.set(t.position, t);     // a later table in a corner replaces the earlier
      this.o.tables = [...byPosition.values()];
      if (r.full !== false) this.bg = new Map();
      for (const title in r.plotsMeta || {}) {
        if (r.plotsMeta[title].style !== 'background') continue;
        const m = this.bg.get(title) || new Map();
        for (const p of (r.plots && r.plots[title]) || []) { const c = parseColor(p.color); if (c) m.set(p.time, c); else m.delete(p.time); }
        this.bg.set(title, m);
      }
      this.redraw();
    }

    /* Everything a draw needs from the chart's current view, or null when there is nothing to draw on. */
    frame() {
      const bars = this.host.bars, ts = this.chart && this.chart.timeScale();
      if (!ts || !this.series || this.firstMs == null || !bars || !bars.length) return null;
      const vr = ts.getVisibleLogicalRange();
      if (!vr) return null;
      const n = bars.length, barMs = this.host.barMs();
      return { bars, barMs, end: bars[n - 1].ms + barMs, base: baseIndex(bars, this.firstMs, barMs),
        i0: Math.max(0, Math.floor(vr.from) - 1), i1: Math.min(n - 1, Math.ceil(vr.to) + 1),
        XI: (i) => ts.logicalToCoordinate(i), Y: (p) => this.series.priceToCoordinate(p), spacing: this.spacing() };
    }

    drawBg(target) {
      if (!this.bg.size) return;
      const f = this.frame();
      if (!f) return;
      target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
        for (const m of this.bg.values()) {
          for (const r of bgRuns(f.bars, f.i0, f.i1, (b) => m.get(b.ms), f.XI, f.spacing / 2)) {
            ctx.fillStyle = r.c; ctx.fillRect(r.x0, 0, r.x1 - r.x0, mediaSize.height);
          }
        }
      });
    }

    draw(target) {
      const o = this.o, f = this.frame();
      if (!f || !Object.values(o).some((l) => l.length)) return;
      target.useMediaCoordinateSpace(({ context: ctx, mediaSize: { width: W, height: H } }) => {
        for (const b of o.boxes) paintBox(ctx, b, f, W, H);
        for (const lf of o.linefills) paintLinefill(ctx, lf, f, W);
        for (const p of o.polylines) paintPolyline(ctx, p, f, W, H);
        for (const l of o.lines) paintLine(ctx, l, f, W, H);
        for (const l of o.labels) paintLabel(ctx, l, f, W, H);
        for (const t of o.tables) paintTable(ctx, t, W, H);
      });
    }
  }

  api.PineLayer = PineLayer;
  window.HBPineLayer = api;
}
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
