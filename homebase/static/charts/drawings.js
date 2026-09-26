/* Homebase Charts — drawing tools. This half is pure: geometry that maps a
   drawing's (time, price) points through the chart's bars to pixels (so a
   drawing stays on its times across timeframes, like TradingView), hit
   tests, tick rounding, the measure text, and the per-symbol store that
   keeps drawings on the server. No browser globals at load time: the Node
   tests load this file directly. The canvas primitive and the pointer
   controller come after it (Task 6). */
(function () {
'use strict';
const Cat = (typeof window !== 'undefined' && window.HBCatalog) || (typeof require === 'function' ? require('./catalog.js') : null);
const HANDLE_TOL = 6;   // px: a handle this close is grabbed
const LINE_TOL = 5;     // px: a line this close is hit

/* The index of the last bar starting at or before t (bars ascending by ms), else -1. */
function barIndexAt(bars, t) {
  let lo = 0, hi = bars.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].ms <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

/* Time t as a fractional bar index. Between two bars it is interpolated by
   time; before the first / after the last bar, time bars extrapolate by
   their length and other bar types (tick, volume, range) clamp. */
function logicalOf(bars, t, isTime, barMs) {
  const n = bars.length;
  if (!n) return null;
  const i = barIndexAt(bars, t), ext = isTime && barMs > 0;
  if (i < 0) return ext ? (t - bars[0].ms) / barMs : 0;
  if (i === n - 1) return ext ? n - 1 + (t - bars[n - 1].ms) / barMs : n - 1;
  return i + (t - bars[i].ms) / (bars[i + 1].ms - bars[i].ms);
}

/* The x of a fractional logical from the two INTEGER bar coordinates around
   it: Lightweight Charts v5 answers 0 for a fractional logical. */
function xOfLogical(L, coord) {
  if (L == null || !Number.isFinite(L)) return null;
  const i = Math.floor(L), f = L - i, a = coord(i);
  if (a == null) return null;
  if (f === 0) return a;
  const b = coord(i + 1);
  return b == null ? a : a + f * (b - a);
}

function timeToX(t, ctx) { return xOfLogical(logicalOf(ctx.bars, t, ctx.isTime, ctx.barMs), ctx.coord); }

/* The start time of the bar nearest logical L; beyond the loaded bars, time
   bars step by their length and other bar types clamp to the first/last bar. */
function snapTime(L, bars, isTime, barMs) {
  const n = bars.length, i = Math.round(L);
  if (i < 0) return isTime && barMs > 0 ? bars[0].ms + i * barMs : bars[0].ms;
  if (i > n - 1) return isTime && barMs > 0 ? bars[n - 1].ms + (i - (n - 1)) * barMs : bars[n - 1].ms;
  return bars[i].ms;
}

function roundToTick(p, tick) {
  if (!(tick > 0)) return p;
  return +(Math.round(p / tick) * tick).toFixed(Cat.decimals(tick));
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const u = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - (ax + u * dx), py - (ay + u * dy));
}

/* Pixel positions [[x, y], ...] of drawing d's handles, or null when a point
   cannot be placed: trend 0/1 = its points; rect 0 (t0,p0), 1 (t1,p1),
   2 (t0,p1), 3 (t1,p0); hline 0 = the middle of the pane. */
function handlePoints(d, geo) {
  const P = d.points;
  if (d.type === 'hline') {
    const y = geo.y(P[0].p);
    return y == null ? null : [[geo.w / 2, y]];
  }
  const x0 = geo.x(P[0].t), x1 = geo.x(P[1].t), y0 = geo.y(P[0].p), y1 = geo.y(P[1].p);
  if (x0 == null || x1 == null || y0 == null || y1 == null) return null;
  return d.type === 'rect' ? [[x0, y0], [x1, y1], [x0, y1], [x1, y0]] : [[x0, y0], [x1, y1]];
}

/* What of drawing d is under pt: a handle (by index), the body, or nothing. */
function hitTest(d, pt, geo) {
  const hs = handlePoints(d, geo);
  if (!hs) return null;
  for (let i = 0; i < hs.length; i++) {
    if (Math.hypot(pt.x - hs[i][0], pt.y - hs[i][1]) <= HANDLE_TOL) return { part: 'handle', index: i };
  }
  if (d.type === 'hline') return Math.abs(pt.y - hs[0][1]) <= LINE_TOL ? { part: 'body' } : null;
  const [[x0, y0], [x1, y1]] = hs;
  if (d.type === 'trend') return distToSegment(pt.x, pt.y, x0, y0, x1, y1) <= LINE_TOL ? { part: 'body' } : null;
  const inside = pt.x >= Math.min(x0, x1) - LINE_TOL && pt.x <= Math.max(x0, x1) + LINE_TOL
    && pt.y >= Math.min(y0, y1) - LINE_TOL && pt.y <= Math.max(y0, y1) + LINE_TOL;
  return inside ? { part: 'body' } : null;
}

/* d with handle k moved to (t, p); a rectangle's side corners (2, 3) take
   their time from one stored point and their price from the other. */
function setPoint(d, k, t, p) {
  if (d.type === 'hline') return { ...d, points: [{ p }] };
  const [a, b] = d.points;
  let points;
  if (d.type === 'rect') {
    points = [[{ t, p }, b], [a, { t, p }], [{ t, p: a.p }, { t: b.t, p }], [{ t: a.t, p }, { t, p: b.p }]][k];
  } else points = k === 0 ? [{ t, p }, b] : [a, { t, p }];
  return { ...d, points };
}

/* t moved by whole bars; a zero move keeps t exactly (a price-only drag must
   not snap a point that sits between this chart's bars). */
function shiftTime(t, dBars, ctx) {
  if (!dBars) return t;
  const L = logicalOf(ctx.bars, t, ctx.isTime, ctx.barMs);
  return L == null ? t : snapTime(Math.round(L) + dBars, ctx.bars, ctx.isTime, ctx.barMs);
}

function moveDrawing(d, dBars, dPrice, tick, ctx) {
  return { ...d, points: d.points.map((q) => (d.type === 'hline'
    ? { p: roundToTick(q.p + dPrice, tick) }
    : { t: shiftTime(q.t, dBars, ctx), p: roundToTick(q.p + dPrice, tick) })) };
}

function fmtDuration(ms) {
  const s = Math.round(Math.abs(ms) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

/* The measure tool's two lines, e.g. "+12.50 (+0.04%) · 50 ticks" / "8 bars · 8m". */
function measureLabel(a, b, ctx) {
  const diff = b.p - a.p, pct = a.p ? diff / a.p * 100 : 0, sign = diff > 0 ? '+' : diff < 0 ? '-' : '';
  const ticks = Math.round(Math.abs(diff) / ctx.tick);
  const La = logicalOf(ctx.bars, a.t, ctx.isTime, ctx.barMs), Lb = logicalOf(ctx.bars, b.t, ctx.isTime, ctx.barMs);
  const n = La == null || Lb == null ? 0 : Math.abs(Math.round(Lb) - Math.round(La));
  return [`${sign}${Cat.fmtPrice(Math.abs(diff), ctx.tick)} (${sign}${Math.abs(pct).toFixed(2)}%) · ${ticks} tick${ticks === 1 ? '' : 's'}`,
    `${n} bar${n === 1 ? '' : 's'} · ${fmtDuration(b.t - a.t)}`];
}

let seq = 0;
function newId() { return 'd' + Date.now().toString(36) + (seq++).toString(36) + Math.random().toString(36).slice(2, 6); }

/* Drawings per symbol, shared by every chart of that symbol, saved to the
   server as the symbol's whole list, debounced. */
class Store {
  constructor({ fetchFn, delay = 300, onError = () => {} } = {}) {
    this.fetch = fetchFn || ((...a) => fetch(...a));
    this.delay = delay;
    this.onError = onError;
    this.roots = new Map();
  }

  st(root) {
    let s = this.roots.get(root);
    if (!s) { s = { list: [], loaded: false, loading: null, timer: null, subs: new Set() }; this.roots.set(root, s); }
    return s;
  }

  url(root) { return `/api/drawings/${encodeURIComponent(root)}`; }

  list(root) { return this.st(root).list; }

  subscribe(root, fn) { const s = this.st(root); s.subs.add(fn); return () => s.subs.delete(fn); }

  emit(root) { for (const fn of [...this.st(root).subs]) fn(); }

  /* Load the symbol's saved drawings once. Resolves true when loaded, false
     when the load failed (reported; the next ensure() tries again). */
  ensure(root) {
    const s = this.st(root);
    if (s.loaded) return Promise.resolve(true);
    if (!s.loading) s.loading = this.load(root).finally(() => { s.loading = null; });
    return s.loading;
  }

  async load(root) {
    const s = this.st(root);
    try {
      const r = await this.fetch(this.url(root));
      if (!r.ok) throw new Error(`load failed (${r.status})`);
      const saved = await r.json(), mine = new Set(s.list.map((d) => d.id));
      s.list = [...(Array.isArray(saved) ? saved : []).filter((d) => d && !mine.has(d.id)), ...s.list];
      s.loaded = true;
      this.emit(root);
      return true;
    } catch (e) {
      this.onError(root, e && e.message ? e.message : String(e));
      return false;
    }
  }

  add(root, d) { this.set(root, [...this.list(root), d]); }
  replace(root, d) { this.set(root, this.list(root).map((x) => (x.id === d.id ? d : x))); }
  remove(root, id) { this.set(root, this.list(root).filter((x) => x.id !== id)); }
  clear(root) { this.set(root, []); }

  set(root, list) {
    const s = this.st(root);
    s.list = list;
    this.emit(root);
    clearTimeout(s.timer);
    s.timer = setTimeout(() => { s.timer = null; this.save(root); }, this.delay);
  }

  async save(root) {
    if (!(await this.ensure(root))) return;   // never overwrite drawings we could not read
    try {
      const r = await this.fetch(this.url(root), { method: 'PUT', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(this.list(root)) });
      if (!r.ok) {
        let detail = '';
        try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
        throw new Error(`save failed (${r.status})${detail ? ': ' + detail : ''}`);
      }
    } catch (e) {
      this.onError(root, e && e.message ? e.message : String(e));
    }
  }
}

const api = { barIndexAt, logicalOf, xOfLogical, timeToX, snapTime, roundToTick, distToSegment, handlePoints, hitTest,
  setPoint, shiftTime, moveDrawing, fmtDuration, measureLabel, newId, Store, HANDLE_TOL, LINE_TOL };
if (typeof window !== 'undefined') window.HBDrawings = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
