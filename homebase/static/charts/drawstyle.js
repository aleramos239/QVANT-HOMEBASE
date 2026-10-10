/* Homebase Charts — a drawing's visual style (2026-09-27 draw-tools plan): per-type defaults, a
   normalize that drops or falls back on anything the server's own check_style (server.py) would
   refuse (so what the page previews is always what it can save), canvas dash patterns, where a
   text label anchors on a line or a rectangle, and the two Shift gestures' pure decisions (Shift
   starts the ruler with the cursor tool; Shift snaps a trend line's moving endpoint to the other
   endpoint's price). Pure: no browser globals at load time (the Node tests load this file
   directly), and no dependency on drawings.js (drawings.js depends on this one). */
(function () {
'use strict';

const LINE_STYLES = ['solid', 'dashed', 'dotted'];
/* The straight two-point lines: a trend line stops at its points (unless it is told to extend), a
   ray runs on past its second point, an extended line runs on both ways. */
const LINE_TYPES = ['trend', 'ray', 'xline'];
const isLine = (t) => LINE_TYPES.includes(t);
/* Where the optional text label sits: lines are relative to the line, a rectangle is inside the
   box (spec: "above/below/middle" for lines, "inside top/middle/bottom" for a rectangle), a
   vertical line beside it at the top / middle / bottom of the pane. */
const LINE_POS = ['above', 'below', 'middle'], BOX_POS = ['top', 'middle', 'bottom'];
const LABEL_POS = { trend: LINE_POS, ray: LINE_POS, xline: LINE_POS, hline: LINE_POS, rect: BOX_POS, vline: BOX_POS };
const LABEL_ALIGN = ['left', 'center', 'right'];      // a horizontal line's label, along the line
const MAX_TEXT = 200;
const MAX_FIB_LEVELS = 16, FIB_MIN = -10, FIB_MAX = 10;
const TEXT = ['text', 'fontSize', 'textColor', 'bold', 'labelPos'];
/* Exactly the style fields each drawing type takes (check_style in server.py mirrors this list);
   long/short keep their existing look (colour, via the drawing's own top-level `color`) and take
   no style object of their own. */
const FIELDS = {
  trend: ['width', 'lineStyle', 'extendLeft', 'extendRight', ...TEXT, 'priceLabel', 'stats'],
  ray: ['width', 'lineStyle', ...TEXT, 'priceLabel', 'stats'],
  xline: ['width', 'lineStyle', ...TEXT, 'priceLabel', 'stats'],
  hline: ['width', 'lineStyle', 'axisLabel', ...TEXT, 'labelAlign'],
  vline: ['width', 'lineStyle', ...TEXT, 'timeLabel'],
  rect: ['width', 'lineStyle', 'fillColor', ...TEXT, 'border', 'midline', 'quarters', 'midStyle', 'extendRight', 'priceLabels'],
  fib: ['width', 'lineStyle', 'extendLeft', 'extendRight', 'levels', 'showLevels', 'showPrices', 'fill', 'reverse', 'fontSize'],
  long: [], short: [],
};
/* The Fibonacci levels a fresh retracement carries: {v: the ratio, on: drawn, color}. 0 sits on the
   SECOND point (where the drag ended) and 1 on the first, so the levels count the pullback. */
const FIB_LEVELS = [[0, '#787B86'], [0.236, '#F23645'], [0.382, '#FF9800'], [0.5, '#4CAF50'], [0.618, '#089981'],
  [0.786, '#00BCD4'], [1, '#787B86'], [1.618, '#2962FF']].map(([v, color]) => ({ v, on: v !== 1.618, color }));
const LINE_DEF = { width: 2, lineStyle: 'solid', text: '', fontSize: 12, textColor: '#2962FF', bold: false, labelPos: 'above',
  priceLabel: false, stats: false };
const DEFAULTS = {
  trend: { ...LINE_DEF, extendLeft: false, extendRight: false },
  ray: { ...LINE_DEF },
  xline: { ...LINE_DEF },
  // width 1 / solid / axisLabel on is today's look (the hline price line, unstyled) -- an old
  // drawing with no `style` at all must render exactly as it did before this plan
  hline: { width: 1, lineStyle: 'solid', axisLabel: true, text: '', fontSize: 12,
    textColor: '#2962FF', bold: false, labelPos: 'above', labelAlign: 'center' },
  vline: { width: 1, lineStyle: 'solid', text: '', fontSize: 12, textColor: '#2962FF', bold: false, labelPos: 'top', timeLabel: true },
  // no fillColor here on purpose: unset means "follow the theme" (P.accentSoft -- .10 light,
  // .20 dark), exactly like an old rect drawn before this plan. A fixed default would have been
  // wrong in dark theme (review finding): normalize() below omits the key entirely rather than
  // filling in one theme's value.
  rect: { width: 1, lineStyle: 'solid', text: '', fontSize: 12, textColor: '#2962FF', bold: false, labelPos: 'top',
    border: true, midline: false, quarters: false, midStyle: 'dashed', extendRight: false, priceLabels: false },
  fib: { width: 1, lineStyle: 'solid', extendLeft: false, extendRight: false, levels: FIB_LEVELS, showLevels: true, showPrices: true,
    fill: true, reverse: false, fontSize: 11 },
  long: {}, short: {},
};
/* Canvas dash patterns (ctx.setLineDash), keyed the same as lineStyle. */
const DASH = { solid: [], dashed: [6, 4], dotted: [1, 3] };

const isDrawingType = (t) => Object.prototype.hasOwnProperty.call(FIELDS, t);

/* '#RRGGBB' or 'rgba(r,g,b,a)' with r/g/b <= 255 and a in [0,1] -- the same shape server.py's
   check_drawings / check_style accepts (2026-09-27 draw-tools plan widened `color` to allow
   opacity, the same way). */
const HEX = /^#[0-9A-Fa-f]{6}$/;
const RGBA = /^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0|1|0?\.\d+)\s*\)$/;
function isColor(v) {
  if (typeof v !== 'string') return false;
  if (HEX.test(v)) return true;
  const m = RGBA.exec(v);
  return !!m && +m[1] <= 255 && +m[2] <= 255 && +m[3] <= 255;
}

function isValidLevel(l) {
  return !!l && typeof l === 'object' && typeof l.v === 'number' && Number.isFinite(l.v) && l.v >= FIB_MIN && l.v <= FIB_MAX
    && typeof l.on === 'boolean' && (l.color === undefined || isColor(l.color));
}
function isValidField(type, key, v) {
  switch (key) {
    case 'width': return Number.isInteger(v) && v >= 1 && v <= 4;
    case 'lineStyle': case 'midStyle': return LINE_STYLES.includes(v);
    case 'extendLeft': case 'extendRight': case 'axisLabel': case 'bold': case 'priceLabel': case 'stats': case 'timeLabel':
    case 'border': case 'midline': case 'quarters': case 'priceLabels': case 'showLevels': case 'showPrices': case 'fill': case 'reverse':
      return typeof v === 'boolean';
    case 'fillColor': case 'textColor': return isColor(v);
    case 'text': return typeof v === 'string' && v.length <= MAX_TEXT;
    case 'fontSize': return Number.isInteger(v) && v >= 10 && v <= 28;
    case 'labelPos': return (LABEL_POS[type] || []).includes(v);
    case 'labelAlign': return LABEL_ALIGN.includes(v);
    case 'levels': return Array.isArray(v) && v.length >= 1 && v.length <= MAX_FIB_LEVELS && v.every(isValidLevel);
    default: return false;
  }
}

/* A drawing type's style with exactly the fields it takes, each valid or falling back to that
   type's default: unknown keys dropped, a type with no style fields (long/short) always {}. Never
   throws -- this is what the page previews; the server is still the final word on save. */
function normalize(type, style) {
  const allowed = FIELDS[isDrawingType(type) ? type : ''] || [], def = DEFAULTS[type] || {};
  const src = style && typeof style === 'object' ? style : {}, out = {};
  for (const key of allowed) {
    if (isValidField(type, key, src[key])) { out[key] = src[key]; continue; }
    // fillColor has no built-in default (unset = "follow the theme", see DEFAULTS.rect above): an
    // invalid/absent value drops the key entirely rather than filling in one theme's colour, and
    // this PUTs cleanly too (check_style in server.py only looks at a `style.fillColor` that is
    // actually present).
    if (key === 'fillColor' && def[key] == null) continue;
    out[key] = def[key];
  }
  // a retracement's levels: its own copies, ascending, each {v, on, color} and nothing else
  if (out.levels) out.levels = out.levels.map((l) => ({ v: l.v, on: l.on, color: isColor(l.color) ? l.color : '#787B86' })).sort((a, b) => a.v - b.v);
  return out;
}

/* A fresh drawing's starting style: `preset` (e.g. a saved "default" template's payload) merged
   over the type's built-in default, still normalized (so a stale/edited preset can never carry a
   field the type doesn't take, or an out-of-range one, onto a new drawing). */
function starting(type, preset) {
  return normalize(type, { ...DEFAULTS[type], ...(preset && typeof preset === 'object' ? preset : {}) });
}

function dashFor(style) { return DASH[(style && style.lineStyle) || 'solid'] || DASH.solid; }

/* A trend line's two pixel endpoints [x0,y0,x1,y1], stretched to the pane's screen edges (x = 0,
   x = paneW) on the left and/or right (style.extendLeft / extendRight) along the same slope.
   "Left"/"right" are screen directions, not which of the two stored points is which -- a line
   drawn right-to-left still extends left off its leftmost pixel. A vertical segment (x0 === x1)
   has no left/right to extend into and is returned unchanged. */
function extendLine(x0, y0, x1, y1, paneW, left, right) {
  if ((!left && !right) || x0 === x1) return [x0, y0, x1, y1];
  const m = (y1 - y0) / (x1 - x0), atX = (fromX, fromY, toX) => fromY + m * (toX - fromX);
  const flip = x0 > x1;
  let [lx, ly, rx, ry] = flip ? [x1, y1, x0, y0] : [x0, y0, x1, y1];
  if (left) { ly = atX(lx, ly, 0); lx = 0; }
  if (right) { ry = atX(rx, ry, paneW); rx = paneW; }
  return flip ? [rx, ry, lx, ly] : [lx, ly, rx, ry];
}

/* The two pixel ends of a straight line as it is DRAWN: a trend line as extendLine above (its two
   switches); a ray runs on from its SECOND point, away from the first, to the pane's edge; an
   extended line runs to the edge both ways. A vertical one (x0 === x1) runs to the top / bottom of
   the pane (paneH) instead, the way it points. */
function lineEnds(type, x0, y0, x1, y1, paneW, paneH, style) {
  if (type === 'trend') return extendLine(x0, y0, x1, y1, paneW, !!(style && style.extendLeft), !!(style && style.extendRight));
  if (type !== 'ray' && type !== 'xline') return [x0, y0, x1, y1];
  if (x0 === x1) {
    if (y0 === y1) return [x0, y0, x1, y1];
    const down = y1 > y0, far = down ? paneH : 0, near = down ? 0 : paneH;
    return [x0, type === 'xline' ? near : y0, x1, far];
  }
  const right = x1 > x0;
  return type === 'xline' ? extendLine(x0, y0, x1, y1, paneW, true, true) : extendLine(x0, y0, x1, y1, paneW, !right, right);   // a ray: only its far side
}

/* A retracement level's price: 0 on the second point (b), 1 on the first (a); `reverse` swaps them. */
function fibPrice(a, b, v, reverse) { return reverse ? a + (b - a) * v : b + (a - b) * v; }
/* The levels that are drawn, ascending by ratio. */
function fibLevels(style) { return ((style && style.levels) || []).filter((l) => l.on); }
/* "0.618" / "1" / "1.618": a ratio as the chart writes it. */
function fibText(v) { return String(Math.round(v * 1000) / 1000); }

/* ---- which intervals a drawing shows on (2026-10-09) ----
   d.vis = {min, max}: bar lengths in SECONDS, either may be null (no bound). A chart whose bars are
   not time bars (tick, volume, range) shows every drawing: it has no interval to compare. */
const VIS_MAX_S = 31 * 86400;
function normalizeVis(v) {
  if (!v || typeof v !== 'object') return null;
  const ok = (x) => Number.isInteger(x) && x >= 1 && x <= VIS_MAX_S;
  const min = ok(v.min) ? v.min : null, max = ok(v.max) ? v.max : null;
  if (min == null && max == null) return null;
  if (min != null && max != null && min > max) return null;
  return { min, max };
}
function shownOn(vis, spec) {
  const v = normalizeVis(vis), m = /^time:(\d+)$/.exec(String(spec));
  if (!v || !m) return true;
  const n = +m[1];
  return (v.min == null || n >= v.min) && (v.max == null || n <= v.max);
}

/* Where a text label sits, in pixels, given the drawing's already-computed handle points (as
   handlePoints() in drawings.js returns them) and the pane's width (hline centres on the pane,
   like the measure box does). Returns {x, y, baseline: 'top'|'middle'|'bottom'} -- the caller sets
   textAlign itself (always 'center' here). Null when there is nothing to anchor to. */
function labelAnchor(type, hs, pos, paneWidth, align = 'center', paneHeight = 0) {
  if (!hs || !hs.length) return null;
  const GAP = 8;
  if (type === 'hline') {
    // along the line: left / centre / right of the pane (`align`, also the text's own alignment)
    const y = hs[0][1], x = align === 'left' ? GAP : align === 'right' ? paneWidth - GAP : paneWidth / 2;
    if (pos === 'below') return { x, y: y + GAP, baseline: 'top', align };
    if (pos === 'middle') return { x, y, baseline: 'middle', align };
    return { x, y: y - GAP, baseline: 'bottom', align };
  }
  if (type === 'vline') {
    // beside the line, to its right, at the top / middle / bottom of the pane
    const x = hs[0][0] + GAP;
    if (pos === 'bottom') return { x, y: paneHeight - GAP - 14, baseline: 'bottom', align: 'left' };
    if (pos === 'middle') return { x, y: paneHeight / 2, baseline: 'middle', align: 'left' };
    return { x, y: GAP, baseline: 'top', align: 'left' };
  }
  if (isLine(type)) {
    const [[x0, y0], [x1, y1]] = hs, mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
    if (pos === 'below') return { x: mx, y: my + GAP, baseline: 'top' };
    if (pos === 'middle') return { x: mx, y: my, baseline: 'middle' };
    return { x: mx, y: my - GAP, baseline: 'bottom' };
  }
  if (type === 'rect') {
    const [[x0, y0], [x1, y1]] = hs, left = Math.min(x0, x1), right = Math.max(x0, x1);
    const top = Math.min(y0, y1), bot = Math.max(y0, y1), cx = (left + right) / 2;
    if (pos === 'bottom') return { x: cx, y: bot - GAP, baseline: 'bottom' };
    if (pos === 'middle') return { x: cx, y: (top + bot) / 2, baseline: 'middle' };
    return { x: cx, y: top + GAP, baseline: 'top' };
  }
  return null;
}

/* The floating per-drawing toolbar's anchor, in pixels: centred above the drawing's own handle
   points (their bounding box), the same box a selection's handle dots are drawn in. Null with no
   handle points (the drawing is off the loaded bars). */
function toolbarAnchor(hs) {
  if (!hs || !hs.length) return null;
  const xs = hs.map((p) => p[0]), ys = hs.map((p) => p[1]);
  return { cx: (Math.min(...xs) + Math.max(...xs)) / 2, top: Math.min(...ys) };
}

/* ---- Shift gestures (pure decisions; drawings.js's Controller applies them) ---- */
/* Shift + press-drag with the cursor tool starts the ruler (the measure tool's own behaviour),
   instead of panning or moving a drawing. */
function shouldStartRuler(tool, shiftKey) { return tool === 'cursor' && !!shiftKey; }

/* While placing a trend line, or dragging one of its endpoints: Shift held makes the moving
   point's price exactly the other endpoint's price (perfectly horizontal); Shift released
   mid-drag goes back to the pointer's own price on the very next move. */
function snapEndpointPrice(otherPrice, proposedPrice, shiftHeld) { return shiftHeld ? otherPrice : proposedPrice; }

const api = { LINE_STYLES, LINE_TYPES, isLine, LABEL_POS, LABEL_ALIGN, FIELDS, DEFAULTS, FIB_LEVELS, MAX_FIB_LEVELS, MAX_TEXT, VIS_MAX_S,
  isColor, isValidField, normalize, starting, dashFor, extendLine, lineEnds, fibPrice, fibLevels, fibText, normalizeVis, shownOn,
  labelAnchor, toolbarAnchor, shouldStartRuler, snapEndpointPrice };
if (typeof window !== 'undefined') window.HBDrawStyle = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
