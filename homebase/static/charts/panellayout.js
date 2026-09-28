/* Homebase Charts — HBPanelLayout: the pure layout math behind the floating/dockable Order and DOM panels
   (2026-09-27 panels plan). Clamping, dock stacking/height math, the dock drop-zone hit test, and persisted-
   state parsing/validation all live here so they can be unit-tested on Node, with no DOM. The DOM wiring
   (drag, drop, resize handles, the dock column, the float layer) lives in panelshell.js; that file is the only
   caller of this one. No browser globals at load time — Node tests load it directly (dom.js's own pattern). */
(function () {
'use strict';

const IDS = ['order', 'dom'];
const DOCK_W_MIN = 260, DOCK_W_MAX = 480, DOCK_W_DEFAULT = 320;
const FLOAT_W_MIN = 260, FLOAT_H_MIN = 220;
const DOCK_MIN_FRACTION = 0.15;   // a docked panel never collapses under 15% of the stack's height

function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
function num(v, fallback) { return Number.isFinite(v) ? v : fallback; }

function clampDockWidth(w, min = DOCK_W_MIN, max = DOCK_W_MAX) {
  return clamp(num(w, DOCK_W_DEFAULT), min, max);
}

/* A floating panel's rect, kept fully inside the viewport and never smaller than the minimum. The size is
   clamped first (never bigger than the viewport itself, even when that is smaller than the stated minimum --
   a tiny window beats an unusably-clamped one), then the position is clamped so every edge stays on screen. */
function clampFloatRect(rect, viewportW, viewportH, minW = FLOAT_W_MIN, minH = FLOAT_H_MIN) {
  const vw = Math.max(1, num(viewportW, minW)), vh = Math.max(1, num(viewportH, minH));
  const r = rect && typeof rect === 'object' ? rect : {};
  const w = clamp(num(r.w, minW), Math.min(minW, vw), vw);
  const h = clamp(num(r.h, minH), Math.min(minH, vh), vh);
  const x = clamp(num(r.x, 0), 0, Math.max(0, vw - w));
  const y = clamp(num(r.y, 0), 0, Math.max(0, vh - h));
  return { x, y, w, h };
}

/* A persisted dockOrder might name a panel that no longer exists, or drop one that does. Known ids always
   come back; the saved relative order is kept for the ones that survive; unknown ids are discarded; any
   missing id is appended in its default (IDS) order. */
function normalizeOrder(order, knownIds) {
  const known = Array.isArray(knownIds) ? knownIds : IDS;
  const seen = new Set(), out = [];
  for (const id of Array.isArray(order) ? order : []) {
    if (known.includes(id) && !seen.has(id)) { out.push(id); seen.add(id); }
  }
  for (const id of known) if (!seen.has(id)) out.push(id);
  return out;
}

/* Pull `id` out of `list` and reinsert it at `toIndex` (clamped to the list's new bounds). Used both for
   reordering two docked panels and for docking a floated one at a specific slot. */
function reorderList(list, id, toIndex) {
  const arr = (Array.isArray(list) ? list : []).filter((x) => x !== id);
  const i = clamp(Math.round(num(toIndex, arr.length)), 0, arr.length);
  arr.splice(i, 0, id);
  return arr;
}

/* Per-id height FRACTIONS (sum to 1) for the ids currently docked+open, in `order`. Reuses a stored fraction
   for an id that still has one; a lone panel always gets the whole stack; with nothing stored, the stack
   splits evenly. A floor (DOCK_MIN_FRACTION, or 1/n when the stack is small) is enforced with one relaxation
   pass -- always enough for the 2-panel case this page actually has, and correct for a larger n too. */
function dockHeights(order, stored) {
  const ids = Array.isArray(order) ? order : [];
  const n = ids.length;
  if (n === 0) return {};
  if (n === 1) return { [ids[0]]: 1 };
  const src = stored && typeof stored === 'object' ? stored : {};
  let raw = ids.map((id) => (Number.isFinite(src[id]) && src[id] > 0 ? src[id] : 1 / n));
  let total = raw.reduce((a, b) => a + b, 0) || 1;
  raw = raw.map((v) => v / total);
  const floor = Math.min(DOCK_MIN_FRACTION, 1 / n);
  for (let iter = 0; iter < n; iter++) {
    const under = raw.map((v) => v < floor - 1e-9);
    if (!under.some(Boolean)) break;
    const deficit = raw.reduce((s, v, i) => s + (under[i] ? floor - v : 0), 0);
    const donors = raw.reduce((s, v, i) => s + (under[i] ? 0 : v), 0) || 1;
    raw = raw.map((v, i) => (under[i] ? floor : v - (v / donors) * deficit));
  }
  const out = {};
  ids.forEach((id, i) => { out[id] = raw[i]; });
  return out;
}

/* Dragging the splitter between the panel at `splitterIndex` and the next one: moves `deltaFraction` from one
   to the other, each held to at least the floor so neither panel can be dragged to nothing. */
function applySplitterDrag(order, heights, splitterIndex, deltaFraction) {
  const ids = Array.isArray(order) ? order : [];
  const i = splitterIndex, j = splitterIndex + 1;
  if (i < 0 || j >= ids.length || !Number.isFinite(deltaFraction)) return { ...heights };
  const a = ids[i], b = ids[j];
  const floor = Math.min(DOCK_MIN_FRACTION, 1 / ids.length);
  const pairSum = num(heights[a], 0) + num(heights[b], 0);
  const na = clamp(num(heights[a], 0) + deltaFraction, floor, Math.max(floor, pairSum - floor));
  const nb = pairSum - na;
  return { ...heights, [a]: na, [b]: nb };
}
function pixelsToFraction(deltaPx, containerPx) {
  return containerPx > 0 ? num(deltaPx, 0) / containerPx : 0;
}

/* The dock's stacking slots in px, top-down, from its height fractions -- the "dock stacking" math the UI
   turns into flex-basis / top offsets. Pure and independent of how the caller actually paints it. */
function dockSlots(order, heights, containerH) {
  const ids = Array.isArray(order) ? order : [];
  let top = 0;
  const out = [];
  for (const id of ids) {
    const height = Math.max(0, num(heights[id], 0) * Math.max(0, num(containerH, 0)));
    out.push({ id, top, height });
    top += height;
  }
  return out;
}

function pointInRect(px, py, rect) {
  if (!rect) return false;
  return px >= rect.x && px <= rect.x + rect.w && py >= rect.y && py <= rect.y + rect.h;
}

/* ---- side-by-side docking (2026-09-27 panels-side plan): two docked panels can sit stacked (top/bottom,
   the original layout) or side by side (left/right) instead. Orientation is a per-dock flag, not per-panel --
   with only 2 panel ids it always describes the relationship between the pair. ---- */
const ORIENTATIONS = ['stack', 'side'];
function normalizeOrientation(o) { return o === 'side' ? 'side' : 'stack'; }

/* Which drop zone a pointer at (px, py) is over, relative to the OTHER docked panel's rect: the outer
   `edgeFraction` of the width is a left/right band (-> side by side), the rest splits top/bottom by the
   vertical midpoint (-> stacked). Boundary values (exactly at the edge band or the midpoint) fall to the
   non-edge / top side -- `<` and `>`, never `<=`/`>=`, so a hit test at the exact fraction is deterministic
   and documented rather than fragile. Returns null outside the rect or for a degenerate (zero-size) one. */
function dockDropZone(px, py, rect, edgeFraction = 0.3) {
  if (!rect || !(rect.w > 0) || !(rect.h > 0) || !pointInRect(px, py, rect)) return null;
  const relX = (px - rect.x) / rect.w;
  if (relX < edgeFraction) return 'left';
  if (relX > 1 - edgeFraction) return 'right';
  return (py - rect.y) < rect.h / 2 ? 'top' : 'bottom';
}

/* Per-id pixel widths for a side-by-side pair, clamped to [DOCK_W_MIN, DOCK_W_MAX] each and, when their sum
   would exceed `maxTotalW` (the viewport minus the rail and the grid's own minimum), scaled down together --
   never below DOCK_W_MIN, even if that means the clamped total still exceeds a too-small viewport (a tiny
   window beats an unusably-clamped one, same tradeoff as clampFloatRect). */
function clampSideWidths(widths, order, maxTotalW) {
  const ids = Array.isArray(order) ? order : [];
  const n = ids.length;
  if (n === 0) return {};
  const src = widths && typeof widths === 'object' ? widths : {};
  let w = ids.map((id) => clampDockWidth(src[id], DOCK_W_MIN, DOCK_W_MAX));
  const total = w.reduce((a, b) => a + b, 0);
  const budget = Math.max(DOCK_W_MIN * n, num(maxTotalW, Infinity));
  if (total > budget) {
    // take the excess only from what each panel has above DOCK_W_MIN, in proportion: the sum lands exactly on
    // the budget (budget >= DOCK_W_MIN * n, so the surplus always covers it) and no panel dips under the floor
    // (a plain scale-then-floor overshot the budget on an uneven split -- review of 3b6d3b1)
    const excess = total - budget, surplus = w.map((v) => v - DOCK_W_MIN), room = surplus.reduce((a, b) => a + b, 0);
    if (room > 0) w = w.map((v, i) => v - excess * (surplus[i] / room));
  }
  const out = {};
  ids.forEach((id, i) => { out[id] = w[i]; });
  return out;
}
function sideTotalWidth(widths, order) {
  return (Array.isArray(order) ? order : []).reduce((s, id) => s + num(widths[id], 0), 0);
}
/* Dragging the vertical splitter between two side-by-side panels: moves `deltaPx` from one to the other,
   each held to at least DOCK_W_MIN so neither panel can be dragged to nothing. Total width is unchanged. */
function applySideSplitDrag(widths, order, splitterIndex, deltaPx) {
  const ids = Array.isArray(order) ? order : [];
  const i = splitterIndex, j = splitterIndex + 1;
  if (i < 0 || j >= ids.length || !Number.isFinite(deltaPx)) return { ...widths };
  const a = ids[i], b = ids[j];
  const pairSum = num(widths[a], DOCK_W_MIN) + num(widths[b], DOCK_W_MIN);
  const na = clamp(num(widths[a], DOCK_W_MIN) + deltaPx, DOCK_W_MIN, Math.max(DOCK_W_MIN, pairSum - DOCK_W_MIN));
  const nb = pairSum - na;
  return { ...widths, [a]: na, [b]: nb };
}
/* The dock's own width grip, in side-by-side mode, grows/shrinks the panel nearest the grip (the dock's
   leftmost panel, order[0]) rather than the whole stack proportionally -- simplest mental model, and the
   grip already lives at the dock's left edge, right against that panel. */
function applyGripDragSide(widths, order, deltaPx) {
  const ids = Array.isArray(order) ? order : [];
  if (!ids.length) return { ...widths };
  const id0 = ids[0];
  return { ...widths, [id0]: clampDockWidth(num(widths[id0], DOCK_W_DEFAULT) + deltaPx, DOCK_W_MIN, DOCK_W_MAX) };
}

/* ---- persisted state: default shape, and a defensive parse of whatever localStorage handed back ---- */
function defaultState() {
  return {
    dockWidth: DOCK_W_DEFAULT,
    dockOrder: [...IDS],
    dockHeights: {},
    dockOrientation: 'stack',   // 'stack' (top/bottom, the original layout) | 'side' (left/right)
    dockWidths: {},             // per-id px width, side-by-side only; empty = DOCK_W_DEFAULT each
    panels: {
      order: { open: false, docked: true, x: 96, y: 96, w: 320, h: 480 },
      dom: { open: false, docked: true, x: 440, y: 96, w: 320, h: 480 },
    },
  };
}
function sanitizePanel(p, d) {
  const src = p && typeof p === 'object' ? p : {};
  return {
    open: typeof src.open === 'boolean' ? src.open : d.open,
    docked: typeof src.docked === 'boolean' ? src.docked : d.docked,
    x: num(src.x, d.x), y: num(src.y, d.y),
    w: num(src.w, d.w), h: num(src.h, d.h),
  };
}
/* Never throws: an unreadable blob (wrong type, missing fields, a stale shape from an older build) degrades
   field-by-field to the default rather than discarding the whole thing, and a panel id that no longer exists
   is dropped. */
function sanitizeState(raw, defaults) {
  const d = defaults || defaultState();
  const knownIds = Object.keys(d.panels);
  const src = raw && typeof raw === 'object' ? raw : {};
  const panels = {};
  for (const id of knownIds) panels[id] = sanitizePanel(src.panels && src.panels[id], d.panels[id]);
  const dockHeightsStored = {};
  const sh = src.dockHeights && typeof src.dockHeights === 'object' ? src.dockHeights : {};
  for (const id of knownIds) if (Number.isFinite(sh[id]) && sh[id] > 0) dockHeightsStored[id] = sh[id];
  const dockWidthsStored = {};
  const sw = src.dockWidths && typeof src.dockWidths === 'object' ? src.dockWidths : {};
  for (const id of knownIds) if (Number.isFinite(sw[id]) && sw[id] > 0) dockWidthsStored[id] = sw[id];
  return {
    dockWidth: clampDockWidth(src.dockWidth, DOCK_W_MIN, DOCK_W_MAX),
    dockOrder: normalizeOrder(src.dockOrder, knownIds),
    dockHeights: dockHeightsStored,
    dockOrientation: normalizeOrientation(src.dockOrientation),   // anything old/garbage -> 'stack'
    dockWidths: dockWidthsStored,
    panels,
  };
}
/* try/catch lives here so every caller (panelshell.js) gets the same never-throws guarantee, matching the
   rest of the page's `localStorage.getItem(...) || 'null'` convention (orderpanel.js, panel.js). */
function parsePersisted(json, defaults) {
  let parsed = null;
  try { parsed = JSON.parse(json || 'null'); } catch (_) { parsed = null; }
  return sanitizeState(parsed, defaults);
}

const api = {
  IDS, DOCK_W_MIN, DOCK_W_MAX, DOCK_W_DEFAULT, FLOAT_W_MIN, FLOAT_H_MIN, DOCK_MIN_FRACTION, ORIENTATIONS,
  clamp, clampDockWidth, clampFloatRect, normalizeOrder, reorderList, dockHeights, applySplitterDrag,
  pixelsToFraction, dockSlots, pointInRect, defaultState, sanitizeState, parsePersisted,
  normalizeOrientation, dockDropZone, clampSideWidths, sideTotalWidth, applySideSplitDrag, applyGripDragSide,
};
if (typeof window !== 'undefined') window.HBPanelLayout = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
