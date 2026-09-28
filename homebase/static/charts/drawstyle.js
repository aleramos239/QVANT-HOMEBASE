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
/* Where the optional text label sits: trend / hline are relative to the line, rect is inside the
   box (spec: "above/below/middle" for lines, "inside top/middle/bottom" for a rectangle). */
const LABEL_POS = { trend: ['above', 'below', 'middle'], hline: ['above', 'below', 'middle'], rect: ['top', 'middle', 'bottom'] };
const MAX_TEXT = 200;
/* Exactly the style fields each drawing type takes (check_style in server.py mirrors this list);
   long/short keep their existing look (colour, via the drawing's own top-level `color`) and take
   no style object of their own. */
const FIELDS = {
  trend: ['width', 'lineStyle', 'extendLeft', 'extendRight', 'text', 'fontSize', 'textColor', 'bold', 'labelPos'],
  hline: ['width', 'lineStyle', 'axisLabel', 'text', 'fontSize', 'textColor', 'bold', 'labelPos'],
  rect: ['width', 'lineStyle', 'fillColor', 'text', 'fontSize', 'textColor', 'bold', 'labelPos'],
  long: [], short: [],
};
const DEFAULTS = {
  trend: { width: 2, lineStyle: 'solid', extendLeft: false, extendRight: false, text: '', fontSize: 12,
    textColor: '#2962FF', bold: false, labelPos: 'above' },
  // width 1 / solid / axisLabel on is today's look (the hline price line, unstyled) -- an old
  // drawing with no `style` at all must render exactly as it did before this plan
  hline: { width: 1, lineStyle: 'solid', axisLabel: true, text: '', fontSize: 12,
    textColor: '#2962FF', bold: false, labelPos: 'above' },
  rect: { width: 1, lineStyle: 'solid', fillColor: 'rgba(41,98,255,0.10)', text: '', fontSize: 12,
    textColor: '#2962FF', bold: false, labelPos: 'top' },
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

function isValidField(type, key, v) {
  switch (key) {
    case 'width': return Number.isInteger(v) && v >= 1 && v <= 4;
    case 'lineStyle': return LINE_STYLES.includes(v);
    case 'extendLeft': case 'extendRight': case 'axisLabel': case 'bold': return typeof v === 'boolean';
    case 'fillColor': case 'textColor': return isColor(v);
    case 'text': return typeof v === 'string' && v.length <= MAX_TEXT;
    case 'fontSize': return Number.isInteger(v) && v >= 10 && v <= 28;
    case 'labelPos': return (LABEL_POS[type] || []).includes(v);
    default: return false;
  }
}

/* A drawing type's style with exactly the fields it takes, each valid or falling back to that
   type's default: unknown keys dropped, a type with no style fields (long/short) always {}. Never
   throws -- this is what the page previews; the server is still the final word on save. */
function normalize(type, style) {
  const allowed = FIELDS[isDrawingType(type) ? type : ''] || [], def = DEFAULTS[type] || {};
  const src = style && typeof style === 'object' ? style : {}, out = {};
  for (const key of allowed) out[key] = isValidField(type, key, src[key]) ? src[key] : def[key];
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

/* Where a text label sits, in pixels, given the drawing's already-computed handle points (as
   handlePoints() in drawings.js returns them) and the pane's width (hline centres on the pane,
   like the measure box does). Returns {x, y, baseline: 'top'|'middle'|'bottom'} -- the caller sets
   textAlign itself (always 'center' here). Null when there is nothing to anchor to. */
function labelAnchor(type, hs, pos, paneWidth) {
  if (!hs || !hs.length) return null;
  const GAP = 8;
  if (type === 'hline') {
    const y = hs[0][1], x = paneWidth / 2;
    if (pos === 'below') return { x, y: y + GAP, baseline: 'top' };
    if (pos === 'middle') return { x, y, baseline: 'middle' };
    return { x, y: y - GAP, baseline: 'bottom' };
  }
  if (type === 'trend') {
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

const api = { LINE_STYLES, LABEL_POS, FIELDS, DEFAULTS, MAX_TEXT, isColor, isValidField, normalize, starting,
  dashFor, extendLine, labelAnchor, toolbarAnchor, shouldStartRuler, snapEndpointPrice };
if (typeof window !== 'undefined') window.HBDrawStyle = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
