/* Homebase Charts — drawing tools. The pure half: geometry that maps a
   drawing's (time, price) points through the chart's bars to pixels (so a
   drawing stays on its times across timeframes, like TradingView), hit
   tests, tick rounding, the measure text, and the per-symbol store that
   keeps drawings on the server.

   The browser half, below the store: the canvas primitive that draws one
   chart's drawings, and the pointer controller that places, selects,
   moves and deletes them. No browser globals at load time (only inside
   functions that run in the page): the Node tests load this file directly. */
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

/* Do two versions of a drawing sit on exactly the same points? */
function samePoints(a, b) {
  return a.points.length === b.points.length && a.points.every((q, i) => q.t === b.points[i].t && q.p === b.points[i].p);
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

/* ---------------- browser half: canvas primitive + pointer controller ---------------- */
const MOVE_PX = 4;   // a press that moves less than this is a click, not a drag (placing, moving, reshaping)

/* Draws one chart's trend lines and rectangles, the drawing being placed,
   the selected drawing's handles and the measure box, as a series
   primitive on the candles (so only in the price pane). Horizontal lines
   are native price lines kept by the controller, so their price tag sits
   on the axis; this layer only draws a selected one's handle. */
class Primitive {
  constructor(ctl) {
    this.ctl = ctl;
    this.views = [{ zOrder: () => 'top', renderer: () => ({ draw: (target) => this.draw(target) }) }];
  }
  attached({ requestUpdate }) { this.requestUpdate = requestUpdate; }
  detached() { this.requestUpdate = null; }
  updateAllViews() {}
  paneViews() { return this.views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }
  draw(target) {
    const c = this.ctl, geo = c.geo();
    if (!geo) return;
    const P = c.cell.P;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (const d of c.items()) if (d.type !== 'hline') drawShape(ctx, d, geo, P);
      if (c.place) drawShape(ctx, c.place, geo, P);
      const sel = c.selectedDrawing(), hs = sel && handlePoints(sel, geo);
      if (hs) {
        ctx.fillStyle = P.handleFill;
        ctx.strokeStyle = sel.color || P.accent;
        ctx.lineWidth = 1.5;
        for (const [x, y] of hs) { ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
      }
      if (c.measure) drawMeasure(ctx, c.measure, geo, P, c.ctx(), mediaSize);
    });
  }
}

function drawShape(ctx, d, geo, P) {
  const hs = handlePoints(d, geo);
  if (!hs) return;
  const [[x0, y0], [x1, y1]] = hs;
  ctx.strokeStyle = d.color || P.accent;
  if (d.type === 'trend') {
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    return;
  }
  const x = Math.min(x0, x1), y = Math.min(y0, y1), w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
  ctx.fillStyle = P.accentSoft;
  ctx.fillRect(x, y, w, h);
  ctx.lineWidth = 1;
  ctx.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, Math.round(w), Math.round(h));
}

function drawMeasure(ctx, m, geo, P, mctx, size) {
  const x0 = geo.x(m.a.t), x1 = geo.x(m.b.t), y0 = geo.y(m.a.p), y1 = geo.y(m.b.p);
  if (x0 == null || x1 == null || y0 == null || y1 == null) return;
  const up = m.b.p >= m.a.p, col = up ? P.accent : P.down;
  const left = Math.min(x0, x1), top = Math.min(y0, y1), w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
  ctx.fillStyle = up ? P.accentSoft : P.downSoft;
  ctx.fillRect(left, top, w, h);
  ctx.strokeStyle = col;
  ctx.lineWidth = 1;
  const mx = Math.round(left + w / 2) + 0.5, my = Math.round(top + h / 2) + 0.5;
  ctx.beginPath(); ctx.moveTo(mx, y0); ctx.lineTo(mx, y1); ctx.moveTo(x0, my); ctx.lineTo(x1, my); ctx.stroke();
  const lines = measureLabel(m.a, m.b, mctx);
  ctx.font = `12px ${window.HBCell.FONT}`;
  const bw = Math.max(...lines.map((t) => ctx.measureText(t).width)) + 16, bh = 38;
  const bx = Math.max(2, Math.min(left + w / 2 - bw / 2, size.width - bw - 2));
  const by = Math.max(2, Math.min(up ? top - bh - 6 : top + h + 6, size.height - bh - 2));
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 4); ctx.fill();
  ctx.fillStyle = P.onAccent;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(lines[0], bx + bw / 2, by + 11);
  ctx.fillText(lines[1], bx + bw / 2, by + 27);
}

/* One chart's drawing interaction. The tool comes from the page's rail
   (host.tool()); drawings live in the page's per-symbol store
   (host.drawings), so every chart of the symbol shows the same ones. */
class Controller {
  constructor(cell, host) {
    this.cell = cell; this.host = host; this.root = cell.shown.root; this.box = cell.box;
    this.sel = null;       // id of the selected drawing
    this.place = null;     // a trend line / rectangle being placed: {type, points}
    this.measure = null;   // {a, b, done}
    this.mode = null;      // placing: 'drag' (button held since the first point) | 'click' (waiting for the 2nd click)
    this.downAt = null;    // pane point of the press that started placing
    this.drag = null;      // moving / reshaping: {orig, part, index, from, down, moving, cur}
    this.owned = false;    // this gesture switched the chart's panning off
    this.hlines = new Map();   // drawing id -> its price line
    this.prim = new Primitive(this);
    cell.candles.attachPrimitive(this.prim);
    this.on = { down: (e) => this.onDown(e), move: (e) => this.onMove(e), up: (e) => this.onUp(e),
      hover: (e) => this.onHover(e), leave: () => this.setCursor(null), lost: () => this.abort() };
    this.box.addEventListener('pointerdown', this.on.down, true);
    this.box.addEventListener('pointermove', this.on.hover);
    this.box.addEventListener('pointerleave', this.on.leave);
    window.addEventListener('pointermove', this.on.move, true);
    window.addEventListener('pointerup', this.on.up, true);
    window.addEventListener('pointercancel', this.on.lost, true);
    window.addEventListener('blur', this.on.lost);   // the window's own blur: not capture, so element blurs never reach it
    this.off = host.drawings.subscribe(this.root, () => this.refresh());
    host.drawings.ensure(this.root);
    this.refresh();
    this.toolChanged();
  }

  destroy() {   // before the chart is removed (it takes its price lines and primitives with it)
    this.box.removeEventListener('pointerdown', this.on.down, true);
    this.box.removeEventListener('pointermove', this.on.hover);
    this.box.removeEventListener('pointerleave', this.on.leave);
    window.removeEventListener('pointermove', this.on.move, true);
    window.removeEventListener('pointerup', this.on.up, true);
    window.removeEventListener('pointercancel', this.on.lost, true);
    window.removeEventListener('blur', this.on.lost);
    this.off();
    this.release();
    delete this.cell.el.dataset.cursor;
    this.hlines.clear();
  }

  /* The symbol's drawings, with one being dragged shown where it is now. */
  items() {
    const list = this.host.drawings.list(this.root), cur = this.drag && this.drag.cur;
    return cur ? list.map((d) => (d.id === cur.id ? cur : d)) : list;
  }
  selectedDrawing() { return this.sel ? this.items().find((d) => d.id === this.sel) || null : null; }
  ctx() {
    const c = this.cell, ts = c.chart.timeScale();
    return { bars: c.bars, isTime: c.isTime(), barMs: c.barMs(), tick: c.tick, coord: (i) => ts.logicalToCoordinate(i) };
  }
  geo() {
    const c = this.cell;
    if (!c.chart || !c.bars.length) return null;
    const ctx = this.ctx();
    return { x: (t) => timeToX(t, ctx), y: (p) => c.candles.priceToCoordinate(p), w: this.paneW() };
  }
  paneW() { return this.box.clientWidth - this.cell.chart.priceScale('right').width(); }
  paneH() { return this.cell.chart.panes()[0].getHeight(); }
  local(e) { const r = this.box.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  inPane(pt) { return pt.x >= 0 && pt.x < this.paneW() && pt.y >= 0 && pt.y < this.paneH(); }

  /* The bar-snapped time and tick-rounded price under a pane point. */
  at(pt) {
    const c = this.cell, L = c.chart.timeScale().coordinateToLogical(pt.x), p = c.candles.coordinateToPrice(pt.y);
    if (L == null || p == null || !c.bars.length) return null;
    return { t: snapTime(L, c.bars, c.isTime(), c.barMs()), p: roundToTick(p, c.tick), L };
  }

  setCursor(kind) {
    const k = kind || (this.host.tool() === 'cursor' ? null : 'crosshair');
    if (k) this.cell.el.dataset.cursor = k; else delete this.cell.el.dataset.cursor;
  }

  /* Price lines for the horizontal lines; a canvas redraw for the rest. */
  refresh() {
    if (!this.cell.candles) return;
    const P = this.cell.P, seen = new Set();
    for (const d of this.items()) {
      if (d.type !== 'hline') continue;
      seen.add(d.id);
      const opts = { price: d.points[0].p, color: d.color || P.accent, lineWidth: d.id === this.sel ? 2 : 1,
        lineStyle: window.LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: '' };
      const line = this.hlines.get(d.id);
      if (line) line.applyOptions(opts); else this.hlines.set(d.id, this.cell.candles.createPriceLine(opts));
    }
    for (const [id, line] of this.hlines) {
      if (!seen.has(id)) { this.cell.candles.removePriceLine(line); this.hlines.delete(id); }
    }
    if (this.sel && !this.selectedDrawing()) this.sel = null;
    this.prim.redraw();
  }

  /* This gesture is ours. Lightweight Charts 5.2.1 listens to mouse events
     only: preventDefault() on pointerdown suppresses the mousedown/move/up it
     would pan with; panning and zooming also stay off until release(). */
  own(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!this.owned) { this.owned = true; this.cell.chart.applyOptions({ handleScroll: false, handleScale: false }); }
  }
  release() {
    if (!this.owned) return;
    this.owned = false;
    if (this.cell.chart) this.cell.chart.applyOptions({ handleScroll: true, handleScale: true });
  }

  onDown(e) {
    // left button only, and not Ctrl+press: on macOS that is a right-click, and its context menu takes the mouse-up
    if (e.button !== 0 || e.ctrlKey || !this.cell.chart) return;
    const pt = this.local(e), tool = this.host.tool();
    if (this.measure && this.measure.done) { this.measure = null; this.prim.redraw(); }
    if (!this.inPane(pt)) return;
    if (tool !== 'cursor') {
      const at = this.at(pt);
      if (!at) return;
      this.own(e);
      if (this.mode === 'click') { this.finish(at); return; }
      if (tool === 'hline') { this.commit({ type: 'hline', points: [{ p: at.p }] }); return; }
      const start = { t: at.t, p: at.p };
      if (tool === 'measure') this.measure = { a: start, b: start, done: false };
      else this.place = { type: tool, points: [start, start] };
      this.mode = 'drag';
      this.downAt = pt;
      this.prim.redraw();
      return;
    }
    const geo = this.geo();
    if (!geo) return;
    const sel = this.selectedDrawing();
    let d = null, hit = sel ? hitTest(sel, pt, geo) : null;
    if (hit && hit.part === 'handle') d = sel;
    else {
      hit = null;
      const all = this.items();
      for (let i = all.length - 1; i >= 0 && !d; i--) { const h = hitTest(all[i], pt, geo); if (h) { d = all[i]; hit = h; } }
    }
    if (!d) { if (this.sel) { this.sel = null; this.refresh(); } return; }   // empty chart: deselect, let it pan
    this.own(e);
    this.sel = d.id;
    this.drag = { orig: d, part: hit.part, index: hit.index, from: this.at(pt), down: pt, moving: false, cur: null };
    this.setCursor('grabbing');
    this.refresh();
  }

  onMove(e) {
    if (!this.cell.chart) return;
    if (this.held() && !(e.buttons & 1)) { this.abort(); return; }   // the button is up, but its release never reached us
    if (this.place || (this.measure && !this.measure.done)) {
      const at = this.at(this.local(e));
      if (!at) return;
      const end = { t: at.t, p: at.p };
      if (this.place) this.place = { ...this.place, points: [this.place.points[0], end] };
      else this.measure = { ...this.measure, b: end };
      this.prim.redraw();
      return;
    }
    if (!this.drag || !this.drag.from) return;
    const pt = this.local(e), { orig, part, index, from, down } = this.drag;
    // a press that has not left the press point by MOVE_PX is a click (select): a jitter never moves a drawing
    if (!this.drag.moving && Math.hypot(pt.x - down.x, pt.y - down.y) < MOVE_PX) return;
    this.drag.moving = true;
    const at = this.at(pt);
    if (!at) return;
    this.drag.cur = part === 'handle' ? setPoint(orig, index, at.t, at.p)
      : moveDrawing(orig, Math.round(at.L) - Math.round(from.L), at.p - from.p, this.cell.tick, this.ctx());
    this.refresh();
  }

  onUp(e) {
    if (!this.cell.chart) return;
    if (this.place || (this.measure && !this.measure.done)) {
      if (this.mode !== 'drag') return;
      const pt = this.local(e);
      if (Math.hypot(pt.x - this.downAt.x, pt.y - this.downAt.y) < MOVE_PX) { this.mode = 'click'; this.release(); return; }
      const at = this.at(pt);
      if (at) this.finish(at);
      return;
    }
    if (!this.drag) return;
    const { orig, cur } = this.drag;
    this.drag = null;
    this.release();
    this.setCursor(null);
    // saved only when a point really moved: a drag that ends where it started PUTs nothing
    if (cur && !samePoints(orig, cur)) this.host.drawings.replace(this.root, cur); else this.refresh();
  }

  finish(at) {
    const end = { t: at.t, p: at.p };
    this.mode = null;
    this.downAt = null;
    this.release();
    if (this.measure && !this.measure.done) {
      this.measure = { ...this.measure, b: end, done: true };
      this.prim.redraw();
      this.host.toolDone();
      return;
    }
    const d = { ...this.place, points: [this.place.points[0], end] };
    this.place = null;
    const [a, b] = d.points;
    if (a.t === b.t && a.p === b.p) { this.prim.redraw(); this.host.toolDone(); return; }   // nothing to draw
    this.commit(d);
  }

  commit(d) {
    const full = { id: newId(), ...d, color: '#2962FF' };
    this.sel = full.id;
    this.release();
    this.host.drawings.add(this.root, full);   // every chart of this symbol refreshes
    this.host.toolDone();
  }

  toolChanged() {
    if (this.place || (this.measure && !this.measure.done)) {
      this.place = null; this.measure = null; this.mode = null; this.downAt = null;
      this.release();
      this.prim.redraw();
    }
    this.setCursor(null);
  }

  /* A gesture that needs the button held: moving / reshaping a drawing, or a placement or measure being
     dragged out (one waiting for its 2nd click is not). */
  held() { return !!this.drag || this.mode === 'drag'; }

  /* Undo a held gesture: a moved drawing goes back (and stays selected), a placement or measure being dragged
     out is dropped (the tool stays); panning and zoom come back on. Esc, and a release that never reaches us:
     a move with the button up, pointercancel, or the window losing focus (a context menu, another app). */
  abort() {
    if (!this.held()) return false;
    if (this.drag) this.drag = null;
    else { this.place = null; this.measure = null; this.mode = null; this.downAt = null; }
    this.release();
    this.setCursor(null);
    this.refresh();
    return true;
  }

  escape() {
    if (this.abort()) return true;
    if (this.place || this.measure) {   // a placement waiting for its 2nd click, or a finished measure
      this.place = null; this.measure = null; this.mode = null; this.downAt = null;
      this.release();
      this.prim.redraw();
      return true;
    }
    if (this.sel) { this.sel = null; this.refresh(); return true; }
    return false;
  }

  deleteSelected() {
    if (!this.sel) return false;
    const id = this.sel;
    this.sel = null;
    this.host.drawings.remove(this.root, id);
    return true;
  }

  onHover(e) {
    if (this.drag || this.place || e.buttons || this.host.tool() !== 'cursor' || !this.cell.chart) return;
    const pt = this.local(e), geo = this.geo();
    const over = !!geo && this.inPane(pt) && this.items().some((d) => hitTest(d, pt, geo));
    this.setCursor(over ? 'move' : null);
  }
}

const api = { barIndexAt, logicalOf, xOfLogical, timeToX, snapTime, roundToTick, distToSegment, handlePoints, hitTest,
  setPoint, shiftTime, moveDrawing, samePoints, fmtDuration, measureLabel, newId, Store, Primitive, Controller, HANDLE_TOL,
  LINE_TOL };
if (typeof window !== 'undefined') window.HBDrawings = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
