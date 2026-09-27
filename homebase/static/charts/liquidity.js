/* Homebase Charts — HBLiquidity: the liquidity heatmap (2026-09-27 charts-l2-news-ui plan, Task 3), the
   "heatmap" indicator under Order flow. Resting size per price over time, drawn behind the candles: one cell
   per (time column, price), coloured by size on a log scale normalised to what is on screen.
   Two sources, one grid format ({t0, dt_ms, tick, prices: [lo, hi], cells: [[t_idx, price_idx, size], ...]},
   depthgrid.py's):
     - live: the last 2 h of depth messages ({"type":"depth", root, ts, bids, offers}, the same /ws message
       app.js already hands to the ladder and HBL2Layer), kept per root in a LiveBuffer -- one book a second,
       bounded by time and by count;
     - history: GET /api/depth/history for whatever part of the view is older than the live buffer, asked in
       aligned chunks (debounced on scroll/zoom), cached per chunk (LRU), never while zoomed out past 3 days.
   A column shows the book in force at its end, held at most HOLD_MS (a recording gap stays blank). Nothing is
   drawn past the last bar (a Bar Replay chart never sees ahead). The top half of this file is pure and
   Node-tested; the overlay and its canvas layer (bottom) are browser only. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');

const BIN_MS = 1000;                  // the live buffer keeps one book a second; the finest column
const HOLD_MS = 300_000;              // a book is held this long past its time, never longer
const LIVE_MS = 2 * 3600 * 1000;      // the live buffer's span
const LIVE_MAX = LIVE_MS / BIN_MS + 60;   // ... and its hard count cap (a clock jump never grows it)
const CHUNK_COLS = 300;               // history is asked in chunks of this many columns
const MAX_LEVEL = 9;                  // columns at most 2^9 s wide: a chunk (300 x 512 s) stays under the server's 72 h
const MAX_VIEW_MS = 72 * 3600 * 1000; // zoomed out further than this, no heatmap
const PX_PER_COL = 2;

/* ---------------------------------------------------------------- pure */

function snapPrice(idx, tick) { return Number((idx * tick).toFixed(Cat.decimals(tick))); }

/* A grid -> [{t0, t1, price, size}], columns starting at/after endMs dropped and the rest clipped to it. A
   malformed grid or cell is nothing, never a phantom. */
function gridCells(grid, endMs) {
  const g = grid || {}, out = [];
  if (!Number.isFinite(g.t0) || !(g.dt_ms > 0) || !(g.tick > 0) || !Array.isArray(g.prices)
      || !Number.isFinite(g.prices[0]) || !Array.isArray(g.cells)) return out;
  const lo = Math.round(g.prices[0] / g.tick);
  for (const c of g.cells) {
    if (!Array.isArray(c) || !Number.isFinite(c[0]) || !Number.isFinite(c[1]) || !(c[2] > 0)) continue;
    const t0 = g.t0 + c[0] * g.dt_ms;
    let t1 = t0 + g.dt_ms;
    if (endMs != null) { if (t0 >= endMs) continue; t1 = Math.min(t1, endMs); }
    out.push({ t0, t1, price: snapPrice(lo + c[1], g.tick), size: c[2] });
  }
  return out;
}

/* 0..1 on a log scale: a 10-lot still shows beside a 1,000-lot. */
function intensity(size, max) {
  if (!(size > 0) || !(max > 0)) return 0;
  return Math.min(1, Math.log1p(size) / Math.log1p(max));
}

/* The largest size among the cells overlapping [from, to) and the prices lo..hi: the normalisation. */
function windowMax(cells, from, to, lo, hi) {
  const a = Math.min(lo, hi), b = Math.max(lo, hi);
  let m = 0;
  for (const c of cells) if (c.t1 > from && c.t0 < to && c.price >= a && c.price <= b && c.size > m) m = c.size;
  return m;
}

/* The last `maxMs` of books for one root, one per BIN_MS (a later book in the same second replaces it),
   oldest first, at most maxSnaps. Each book is a flat Float64Array [p0, s0, p1, s1, ...]. */
class LiveBuffer {
  constructor(maxMs = LIVE_MS, maxSnaps = LIVE_MAX) { this.maxMs = maxMs; this.maxSnaps = maxSnaps; this.clear(); }
  clear() { this.t = []; this.lv = []; this.version = (this.version || 0) + 1; }
  get length() { return this.t.length; }
  oldest() { return this.t.length ? this.t[0] : null; }
  latest() { return this.t.length ? this.t[this.t.length - 1] : null; }
  levels(i) { const a = this.lv[i], out = []; for (let k = 0; k < a.length; k += 2) out.push([a[k], a[k + 1]]); return out; }
  push(t, bids, offers) {
    if (!Number.isFinite(t)) return;
    const flat = [];
    for (const side of [bids, offers]) {
      for (const r of Array.isArray(side) ? side : []) {
        if (Array.isArray(r) && Number.isFinite(r[0]) && Number.isFinite(r[1]) && r[1] > 0) flat.push(r[0], r[1]);
      }
    }
    this._put(t, new Float64Array(flat));
  }
  /* The book went (the md socket dropped): an empty book from t on, so the last one is not held over it. */
  gap(t) { if (Number.isFinite(t)) this._put(t, new Float64Array(0)); }
  _put(t, lv) {
    const n = this.t.length;
    if (n) {
      const last = this.t[n - 1];
      if (t < last) return;
      if (Math.floor(t / BIN_MS) === Math.floor(last / BIN_MS)) { this.t.pop(); this.lv.pop(); }
    }
    this.t.push(t); this.lv.push(lv);
    let drop = 0;
    while (drop < this.t.length && (this.t.length - drop > this.maxSnaps || this.t[drop] < t - this.maxMs)) drop++;
    if (drop) { this.t.splice(0, drop); this.lv.splice(0, drop); }
    this.version++;
  }
  /* The index of the last book strictly before `end`, or -1. */
  before(end) {
    let a = 0, b = this.t.length;
    while (a < b) { const m = (a + b) >> 1; if (this.t[m] < end) a = m + 1; else b = m; }
    return a - 1;
  }
}

/* The live buffer as a grid over [from, to) in columns of dt: the server's rule (depthgrid.py) exactly. */
function liveGrid(buf, from, to, dt, tick) {
  const cols = [], n = to > from && dt > 0 ? Math.ceil((to - from) / dt) : 0;
  let lo = Infinity, hi = -Infinity;
  for (let c = 0; c < n; c++) {
    const end = Math.min(from + (c + 1) * dt, to), i = buf.before(end);
    if (i < 0 || end - buf.t[i] > HOLD_MS) continue;
    const a = buf.lv[i];
    for (let k = 0; k < a.length; k += 2) {
      const p = Math.round(a[k] / tick);
      cols.push([c, p, a[k + 1]]);
      if (p < lo) lo = p;
      if (p > hi) hi = p;
    }
  }
  if (!cols.length) return { t0: from, dt_ms: dt, tick, prices: null, cells: [] };
  for (const c of cols) c[1] -= lo;
  return { t0: from, dt_ms: dt, tick, prices: [snapPrice(lo, tick), snapPrice(hi, tick)], cells: cols };
}

/* The column width for a view of spanMs over widthPx (about PX_PER_COL px a column, a power-of-two number of
   seconds so zooming reuses chunks), and the history chunk it is asked in; null past MAX_VIEW_MS. */
function level(spanMs, widthPx) {
  if (!(spanMs > 0) || spanMs > MAX_VIEW_MS) return null;
  const want = spanMs / Math.max(1, (widthPx || 0) / PX_PER_COL);
  const k = Math.max(0, Math.min(MAX_LEVEL, Math.ceil(Math.log2(want / BIN_MS) - 1e-9)));
  const dt = BIN_MS * 2 ** k;
  return { dt, chunk: dt * CHUNK_COLS };
}

function chunkStarts(from, to, chunk) {
  const out = [];
  for (let s = Math.floor(from / chunk) * chunk; s < to; s += chunk) out.push(s);
  return out;
}

class ChunkCache {
  constructor(max = 48) { this.max = max; this.m = new Map(); }
  get size() { return this.m.size; }
  get(k) { if (!this.m.has(k)) return undefined; const v = this.m.get(k); this.m.delete(k); this.m.set(k, v); return v; }
  set(k, v) { this.m.delete(k); this.m.set(k, v); while (this.m.size > this.max) this.m.delete(this.m.keys().next().value); }
}

/* Time <-> fractional logical, bar i spanning [i - .5, i + .5) from its start to the next bar's. Time bars
   extrapolate by barMs; other bar types (barMs 0) clamp, their last bar running to endMs. */
function lastIndexAtOrBefore(bars, t) {
  let a = 0, b = bars.length;
  while (a < b) { const m = (a + b) >> 1; if (bars[m].ms <= t) a = m + 1; else b = m; }
  return a - 1;
}
function logicalAt(bars, t, barMs, endMs) {
  const n = bars.length;
  if (!n) return null;
  const time = barMs > 0, i = lastIndexAtOrBefore(bars, t);
  if (i < 0) return time ? -0.5 + (t - bars[0].ms) / barMs : -0.5;
  if (i < n - 1) return i - 0.5 + (t - bars[i].ms) / (bars[i + 1].ms - bars[i].ms);
  if (time) return n - 1.5 + (t - bars[i].ms) / barMs;
  const dur = endMs - bars[i].ms;
  return dur > 0 ? Math.min(n - 0.5, n - 1.5 + (t - bars[i].ms) / dur) : n - 0.5;
}
function timeAt(bars, L, barMs, endMs) {
  const n = bars.length;
  if (!n || !Number.isFinite(L)) return null;
  const time = barMs > 0, i = Math.floor(L + 0.5), f = L + 0.5 - i;
  if (i < 0) return time ? bars[0].ms + (L + 0.5) * barMs : bars[0].ms;
  if (i < n - 1) return bars[i].ms + f * (bars[i + 1].ms - bars[i].ms);
  const last = bars[n - 1].ms, g = L - (n - 1) + 0.5;
  return time ? last + g * barMs : last + Math.min(1, g) * Math.max(0, endMs - last);
}

/* Palette tokens ('rgba(r, g, b, a)' or '#RRGGBB') -> [[r, g, b, a], ...]; ramp(v) interpolates them. */
function parseStops(list) {
  return list.map((s) => {
    const str = String(s).trim();
    if (str[0] === '#') {
      const n = parseInt(str.slice(1, 7), 16) || 0;
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
    }
    const m = str.match(/[\d.]+/g) || [];
    return [+m[0] || 0, +m[1] || 0, +m[2] || 0, m[3] == null ? 1 : +m[3]];
  });
}
function ramp(v, stops) {
  const x = Math.max(0, Math.min(1, v || 0)), seg = x * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(seg)), f = seg - i, a = stops[i], b = stops[i + 1];
  const c = (k) => a[k] + (b[k] - a[k]) * f;
  return `rgba(${Math.round(c(0))},${Math.round(c(1))},${Math.round(c(2))},${Math.round(c(3) * 1000) / 1000})`;
}

const api = { BIN_MS, HOLD_MS, LIVE_MS, LIVE_MAX, CHUNK_COLS, MAX_VIEW_MS, gridCells, intensity, windowMax,
  LiveBuffer, liveGrid, level, chunkStarts, ChunkCache, logicalAt, timeAt, parseStops, ramp };

/* ---------------------------------------------------------------- browser */

if (typeof window !== 'undefined' && window.HBLayers) {
  const DEBOUNCE_MS = 250;        // a scroll/zoom settles this long before history is asked
  const PAINT_MS = 500;           // live books repaint the heatmap at most twice a second
  const REFRESH_MS = 5 * 60_000;  // a cached chunk that ends short of what is now needed is asked again, at most this often
  const RETRY_MS = { 503: 60_000, other: 30_000 };
  const BUCKETS = 24;             // colour steps: one fill per step, not per cell

  const live = new Map();         // root -> LiveBuffer
  const cache = new ChunkCache(32); // `${root}|${dt}|${start}` -> {upTo, at, cells}
  const pending = new Set();
  const blocked = new Map();      // key -> retry-not-before (ms)
  const overlays = new Set();

  /* The same entry point as HBDomUI.onDepth / HBL2Layer.onDepth (app.js's ws routing). */
  const onDepth = (m) => {
    if (!m || typeof m.root !== 'string') return;
    let b = live.get(m.root);
    if (m.ts == null) {
      if (b && b.length) b.gap(Math.max(Date.now(), b.latest() + 1));
    } else {
      if (!b) { b = new LiveBuffer(); live.set(m.root, b); }
      b.push(m.ts, m.bids, m.offers);
    }
    for (const ov of overlays) if (ov.root === m.root) ov.dirty = true;
  };

  const markRoot = (root) => { for (const ov of overlays) if (ov.root === root) ov.redraw(); };

  async function fetchChunk(root, key, from, to) {
    pending.add(key);
    let status = 0;
    try {
      const q = new URLSearchParams({ root, from_ms: String(from), to_ms: String(to), cols: String(CHUNK_COLS) });
      const r = await fetch('/api/depth/history?' + q);
      status = r.status;
      if (r.ok) { cache.set(key, { upTo: to, at: Date.now(), cells: gridCells(await r.json()) }); blocked.delete(key); }
      else blocked.set(key, Date.now() + (RETRY_MS[status] || RETRY_MS.other));
    } catch (_) {
      blocked.set(key, Date.now() + RETRY_MS.other);
    } finally {
      pending.delete(key);
    }
    markRoot(root);
  }

  class HeatLayer extends window.HBLayers.Layer {
    constructor(P, ov) { super(P); this.ov = ov; }
    z() { return 'bottom'; }
    draw(target) { this.ov.draw(target); }
  }

  const findOn = (cell) => (cell.cfg.indicators || []).some((x) => x.id === 'heatmap' && x.visible !== false);

  class Overlay {
    constructor(cell) {
      this.cell = cell;
      this.root = cell.shown ? cell.shown.root : cell.cfg.root;
      this.dirty = false;
      this.dead = false;
      this.liveMemo = null;
      const P = cell.P || {};
      this.stops = parseStops([P.heatLo || 'rgba(41,98,255,.06)', P.heatMid || 'rgba(247,166,0,.45)', P.heatHi || 'rgba(242,54,69,.85)']);
      this.fills = Array.from({ length: BUCKETS }, (_, b) => ramp((b + 1) / BUCKETS, this.stops));
      this.layer = new HeatLayer(P, this);
      if (cell.candles) cell.candles.attachPrimitive(this.layer);
      this.onRange = () => { clearTimeout(this.deb); this.deb = setTimeout(() => this.ask(), DEBOUNCE_MS); };
      if (cell.chart) cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
      this.wasOn = false;
      this.timer = setInterval(() => this.tick(), PAINT_MS);
      overlays.add(this);
      this.ask();
    }

    /* The paint clock: live books repaint; the indicator switched on (no rebuild) asks its history at once. */
    tick() {
      if (this.dead) return;
      const on = this.on();
      if (on !== this.wasOn) { this.wasOn = on; if (on) this.ask(); this.dirty = true; }
      if (this.dirty) { this.dirty = false; this.redraw(); }
    }

    on() { return !this.dead && !!this.cell.chart && findOn(this.cell) && this.cell.bars && this.cell.bars.length > 0; }
    redraw() { if (!this.dead) this.layer.redraw(); }

    /* What the chart shows now: the visible time window, the column level, the drawing end (never past the
       last bar), where the live buffer takes over. */
    view() {
      const cell = this.cell, bars = cell.bars, n = bars.length, ts = cell.chart.timeScale();
      const vr = ts.getVisibleLogicalRange();
      if (!vr || !n) return null;
      this.root = cell.shown ? cell.shown.root : cell.cfg.root;
      const barMs = cell.isTime() ? cell.barMs() : 0, buf = cell.replay ? null : live.get(this.root);
      const lastMs = bars[n - 1].ms;
      const end = barMs ? lastMs + barMs : (cell.replay ? lastMs : Math.max(lastMs, (buf && buf.latest()) || lastMs));
      const from = timeAt(bars, vr.from, barMs, end), to = Math.min(timeAt(bars, vr.to, barMs, end), end);
      const lv = level(to - from, ts.width());
      if (!lv || !(to > from)) return null;
      const oldest = buf && buf.length ? buf.oldest() : null;
      const cut = oldest == null ? Infinity : Math.floor(oldest / lv.dt) * lv.dt;
      return { bars, barMs, end, from, to, lv, buf, cut };
    }

    /* History for the part of the view older than the live buffer: every chunk not cached (or cached short of
       what is now needed), not in flight, not backing off. */
    ask() {
      if (!this.on()) return;
      const v = this.view();
      if (!v) return;
      const now = Date.now(), upto = Math.min(v.to, v.cut, now);
      for (const s of chunkStarts(v.from, upto, v.lv.chunk)) {
        const key = `${this.root}|${v.lv.dt}|${s}`, need = Math.min(s + v.lv.chunk, upto);
        const have = cache.get(key);
        const until = blocked.get(key);
        if (until > now || pending.has(key)) continue;
        if (until) blocked.delete(key);
        if (have && (have.upTo >= need || now - have.at < REFRESH_MS)) continue;
        fetchChunk(this.root, key, s, Math.min(s + v.lv.chunk, now));
      }
      this.redraw();
    }

    /* The cells to draw: cached history chunks up to the live cut, then the live buffer's own grid. */
    cells(v) {
      const out = [];
      for (const s of chunkStarts(v.from, Math.min(v.to, v.cut), v.lv.chunk)) {
        const have = cache.get(`${this.root}|${v.lv.dt}|${s}`);
        if (!have) continue;
        for (const c of have.cells) {
          if (c.t0 >= v.cut || c.t0 >= v.end) continue;
          const t1 = Math.min(c.t1, v.cut, v.end);
          out.push(t1 === c.t1 ? c : { ...c, t1 });
        }
      }
      if (v.buf && v.cut < v.to) {
        // up to now (the latest book is not held into the future), never past the last bar
        const from = Math.max(v.cut, Math.floor(v.from / v.lv.dt) * v.lv.dt);
        const to = Math.min(v.end, Math.max(v.buf.latest() + 1, Math.ceil(Date.now() / BIN_MS) * BIN_MS));
        const key = `${v.buf.version}|${from}|${to}|${v.lv.dt}`;
        if (!this.liveMemo || this.liveMemo.key !== key) {
          this.liveMemo = { key, cells: to > from ? gridCells(liveGrid(v.buf, from, to, v.lv.dt, this.cell.tick || 0.25), to) : [] };
        }
        for (const c of this.liveMemo.cells) if (c.t0 < v.to) out.push(c);
      }
      return out;
    }

    draw(target) {
      if (!this.on()) return;
      const v = this.view();
      if (!v) return;
      const cells = this.cells(v);
      if (!cells.length) return;
      const series = this.cell.candles, ts = this.cell.chart.timeScale(), tick = this.cell.tick || 0.25;
      const coord = (i) => ts.logicalToCoordinate(i), xs = new Map();
      const X = (t) => {
        let x = xs.get(t);
        if (x === undefined) { x = window.HBDrawings.xOfLogical(logicalAt(v.bars, t, v.barMs, v.end), coord); xs.set(t, x); }
        return x;
      };
      target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
        const pTop = series.coordinateToPrice(0), pBot = series.coordinateToPrice(mediaSize.height);
        if (pTop == null || pBot == null) return;
        const max = windowMax(cells, v.from, v.to, pBot, pTop);
        if (!max) return;
        const rows = Array.from({ length: BUCKETS }, () => []);
        for (const c of cells) {
          const x0 = X(c.t0), x1 = X(c.t1), y = series.priceToCoordinate(c.price);
          if (x0 == null || x1 == null || y == null || x1 < 0 || x0 > mediaSize.width) continue;
          const b = Math.min(BUCKETS - 1, Math.floor(intensity(c.size, max) * BUCKETS));
          rows[b].push(x0, y, x1);
        }
        const y0 = series.priceToCoordinate(cells[0].price), y1 = series.priceToCoordinate(cells[0].price + tick);
        const h = Math.max(1, y0 == null || y1 == null ? 1 : Math.abs(y0 - y1));
        for (let b = 0; b < BUCKETS; b++) {
          const r = rows[b];
          if (!r.length) continue;
          ctx.fillStyle = this.fills[b];
          ctx.beginPath();
          for (let k = 0; k < r.length; k += 3) ctx.rect(r[k], r[k + 1] - h / 2, Math.max(1, r[k + 2] - r[k]), h);
          ctx.fill();
        }
      });
    }

    /* A new bar moves the drawing end (and a new session may need history). */
    onBars() { this.dirty = true; }

    destroy() {
      this.dead = true;
      clearInterval(this.timer);
      clearTimeout(this.deb);
      overlays.delete(this);
      const cell = this.cell;
      try { if (cell.chart) cell.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange); } catch (_) { /* chart gone */ }
      try { if (cell.candles) cell.candles.detachPrimitive(this.layer); } catch (_) { /* series gone */ }
    }
  }

  api.onDepth = onDepth;
  api.overlay = (cell) => new Overlay(cell);
  window.HBLiquidity = api;
}
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
