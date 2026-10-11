/* Homebase Charts — HBBookEvents: the book's order-level history drawn on the price pane.
   Three indicators share one overlay and one source (HBBookStore's episodes):
     - "bigorders" (history on): each resting level that cleared `multiple` x the median and stood `minSeconds`, as
       a horizontal segment from where it appeared to where it ended, with a cap that says how it ended: traded =
       filled square, pulled = hollow circle, faded = none. A level still standing is the live line l2layer.js
       already draws (with its size label on the axis), so only ended ones are drawn here: they survive a reload;
     - "absorb": a marker where heavy volume traded into a level that held (the tracker's flag), by the side that
       absorbed (a bid absorbing sellers is green);
     - "pulled": a cross where a big resting order was withdrawn as price came toward it.
   The top half is pure and Node-tested; the overlay (bottom) is browser only, built per chart like every
   host.overlays() entry. Bar Replay: nothing is fetched past the replay cursor, and an episode is shown as the
   cursor saw it (one that ended later is still open, a flag raised later is not yet there). */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Store = need('HBBookStore', './bookstore.js');

const PAINT_MS = 250;
const ASK_EVERY = 8;        // paint ticks between two asks of the store (2 s): a refused chunk is retried when its back-off ends

/* ---------------------------------------------------------------- pure */

/* Episodes -> the segments to draw. now: the right edge for a level still standing. An episode's `r` is its
   PEAK ratio against the trailing median, so `multiple` filters the same way the live gauge's threshold does. */
function segments(eps, { multiple = 5, minSeconds = 5, now = Infinity } = {}) {
  const out = [];
  for (const e of eps || []) {
    if (!e || !(e.r >= multiple)) continue;
    const t1 = e.t1 == null ? now : e.t1;
    if (!(t1 - e.t0 >= minSeconds * 1000)) continue;
    out.push({ id: e.id, side: e.s, price: e.p, t0: e.t0, t1, open: e.t1 == null, size: e.pk, end: e.end, traded: e.tr });
  }
  return out;
}

/* Absorption flags: [{id, t, price, side}] where side = 'up' (a bid absorbed sellers) or 'down' (an offer absorbed
   buyers). minSeconds: the level had stood at least this long when it was flagged. */
function absorptions(eps, { multiple = 4, minSeconds = 5 } = {}) {
  const out = [];
  for (const e of eps || []) {
    if (!e || e.ab == null || !(e.r >= multiple) || !(e.ab - e.t0 >= minSeconds * 1000)) continue;
    out.push({ id: e.id, t: e.ab, price: e.p, side: e.s === 'b' ? 'up' : 'down', traded: e.tr });
  }
  return out;
}

/* Pulled liquidity: [{id, t, price, side}] at the moment the order was withdrawn. side 'b' / 'a' = which side's. */
function pulls(eps, { multiple = 5, minSeconds = 5 } = {}) {
  const out = [];
  for (const e of eps || []) {
    if (!e || e.end !== 'pulled' || e.t1 == null || !(e.r >= multiple) || !(e.t1 - e.t0 >= minSeconds * 1000)) continue;
    out.push({ id: e.id, t: e.t1, price: e.p, side: e.s });
  }
  return out;
}

/* The episodes as they stood at `now` (Bar Replay: the store may hold a chunk that runs past the cursor). One that
   began later is dropped; one that ended later is still open (the server masks the same way at a request's `to`);
   a flag raised later is not set yet. Rows that need no change are returned as they are. */
function clipAt(eps, now) {
  const out = [];
  for (const e of eps || []) {
    if (!e || !(e.t0 <= now)) continue;
    const late = e.t1 != null && e.t1 > now, flag = e.ab != null && e.ab > now;
    out.push(late || flag ? { ...e, t1: late ? null : e.t1, end: late ? 'open' : e.end, ab: flag ? null : e.ab } : e);
  }
  return out;
}

/* The span to ask the store for: the visible window up to `limit` (now live; the replay cursor in a replay, null
   when that is unknown). null when there is nothing to ask. */
function askSpan(from, to, limit) {
  if (!Number.isFinite(from) || !Number.isFinite(to) || !Number.isFinite(limit)) return null;
  const end = Math.min(to, limit);
  return end > from ? [from, end] : null;
}

const api = { PAINT_MS, segments, absorptions, pulls, clipAt, askSpan };

/* ---------------------------------------------------------------- browser */

if (typeof window !== 'undefined' && window.HBLayers && window.HBLiquidity && Store) {
  const { logicalAt } = window.HBLiquidity;

  class EventLayer extends window.HBLayers.Layer {
    constructor(P, ov) { super(P); this.ov = ov; }
    z() { return 'top'; }
    draw(target) { this.ov.draw(target); }
  }

  const inst = (cell, id) => (cell.cfg.indicators || []).find((x) => x.id === id && x.visible !== false) || null;
  const cursorOf = (cell) => (cell.replay && Number.isFinite(cell.replay.cursorMs) ? cell.replay.cursorMs : null);

  class Overlay {
    constructor(cell) {
      this.cell = cell;
      this.dead = false;
      this.dirty = true;
      this.n = 0;
      this.root = this.rootNow();
      this.layer = new EventLayer(cell.P || {}, this);
      if (cell.candles) cell.candles.attachPrimitive(this.layer);
      this.live = this.hist = false;     // what changed in the store since the last paint
      this.off = Store.onChange((root, kind) => {
        if (root !== this.rootNow()) return;
        this.dirty = true;
        if (kind === 'history') { this.hist = true; this.ask(); } else this.live = true;   // a landed chunk: the next one
      });
      this.onRange = () => { this.dirty = true; this.ask(); };
      if (cell.chart) cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
      this.timer = setInterval(() => {
        if (this.dead || !this.on()) return;
        if (++this.n % ASK_EVERY === 0) this.ask();
        // the book series (cell.js point()): every bar once after fetched history (many chunks landing inside one
        // tick are one setData), else the newest only. A replay chart ignores the live feed.
        if (this.hist || (this.live && !this.cell.replay)) {
          if (this.cell.refreshBookSeries) this.cell.refreshBookSeries(this.hist);
          this.hist = this.live = false;
        }
        if (this.dirty) { this.dirty = false; this.layer.redraw(); }
      }, PAINT_MS);
      this.ask();
    }

    rootNow() { return this.cell.shown ? this.cell.shown.root : this.cell.cfg.root; }

    /* Anything of ours on the chart: the three marker indicators, or a series computed from the book (a key
       that starts with "bk:", flowdefs.js). */
    on() {
      const c = this.cell;
      if (this.dead || !c.chart || !c.bars || !c.bars.length) return false;
      if (inst(c, 'bigorders') || inst(c, 'absorb') || inst(c, 'pulled')) return true;
      return (c.cfg.indicators || []).some((x) => x.visible !== false && String(window.HBCatalog.serverKey(x) || '').startsWith('bk:'));
    }

    window() {
      const c = this.cell, bars = c.bars, ts = c.chart.timeScale(), vr = ts.getVisibleLogicalRange();
      if (!bars.length || !vr) return null;
      const barMs = c.isTime() ? c.barMs() : 0, last = bars[bars.length - 1].ms;
      const end = barMs ? last + barMs : last;
      const i0 = Math.max(0, Math.floor(vr.from)), i1 = Math.min(bars.length - 1, Math.ceil(vr.to));
      return { bars, barMs, end, from: bars[i0].ms, to: i1 >= bars.length - 1 ? end : bars[i1 + 1].ms };
    }

    /* Ask the store for the visible span (it fetches only what it does not hold, in aligned chunks, one per call,
       and backs a refused chunk off). Bar Replay: only up to the cursor, and nothing until it is known. */
    ask() {
      if (!this.on()) return;
      this.root = this.rootNow();
      const w = this.window();
      if (!w) return;
      const span = askSpan(w.from, w.to, this.cell.replay ? cursorOf(this.cell) : Date.now());
      if (span) Store.ensure(this.root, span[0], span[1]);
    }

    draw(target) {
      if (!this.on()) return;
      this.root = this.rootNow();
      const w = this.window();
      if (!w) return;
      const cell = this.cell, P = cell.P || {}, series = cell.candles, ts = cell.chart.timeScale();
      const replay = !!cell.replay, cursor = cursorOf(cell);
      const now = replay ? (cursor == null ? w.end : Math.min(cursor, w.end)) : Math.min(Date.now(), Math.max(w.end, w.bars[w.bars.length - 1].ms));
      const raw = Store.episodes(this.root, w.from - 3_600_000, Math.min(w.to, now));
      const eps = replay ? clipAt(raw, now) : raw.filter((e) => e.t0 <= now);
      const xs = new Map();
      const X = (t) => {
        let x = xs.get(t);
        if (x === undefined) { x = window.HBDrawings.xOfLogical(logicalAt(w.bars, t, w.barMs, w.end), (i) => ts.logicalToCoordinate(i)); xs.set(t, x); }
        return x;
      };
      const big = inst(cell, 'bigorders'), ab = inst(cell, 'absorb'), pu = inst(cell, 'pulled');
      target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
        if (big && big.params.history !== false) {
          const segs = segments(eps, { multiple: big.params.multiple, minSeconds: big.params.minSeconds, now });
          for (const s of segs) {
            if (s.open && !replay) continue;      // standing: the live line (l2layer). A replay has no live book.
            const x0 = X(s.t0), x1 = X(s.t1), y = series.priceToCoordinate(s.price);
            if (x0 == null || x1 == null || y == null || x1 < 0 || x0 > mediaSize.width) continue;
            const col = s.side === 'b' ? (P.accent || '#2962FF') : (P.down || '#F23645');
            ctx.strokeStyle = col; ctx.globalAlpha = s.open ? 0.9 : 0.6; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
            ctx.globalAlpha = 1;
            if (!s.open && s.end === 'traded') { ctx.fillStyle = col; ctx.fillRect(x1 - 2.5, y - 2.5, 5, 5); }
            else if (!s.open && s.end === 'pulled') { ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x1, y, 3.5, 0, Math.PI * 2); ctx.stroke(); }
          }
        }
        if (ab) {
          for (const a of absorptions(eps, { multiple: ab.params.multiple, minSeconds: ab.params.minSeconds })) {
            const x = X(a.t), y = series.priceToCoordinate(a.price);
            if (x == null || y == null || x < 0 || x > mediaSize.width) continue;
            ctx.fillStyle = a.side === 'up' ? (P.up || '#089981') : (P.down || '#F23645');
            ctx.beginPath();
            if (a.side === 'up') { ctx.moveTo(x, y - 7); ctx.lineTo(x - 5, y + 3); ctx.lineTo(x + 5, y + 3); }
            else { ctx.moveTo(x, y + 7); ctx.lineTo(x - 5, y - 3); ctx.lineTo(x + 5, y - 3); }
            ctx.closePath(); ctx.fill();
          }
        }
        if (pu) {
          ctx.lineWidth = 1.5;
          for (const p of pulls(eps, { multiple: pu.params.multiple, minSeconds: pu.params.minSeconds })) {
            const x = X(p.t), y = series.priceToCoordinate(p.price);
            if (x == null || y == null || x < 0 || x > mediaSize.width) continue;
            ctx.strokeStyle = p.side === 'b' ? (P.accent || '#2962FF') : (P.down || '#F23645');
            ctx.beginPath(); ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x + 4, y - 4); ctx.lineTo(x - 4, y + 4); ctx.stroke();
          }
        }
      });
    }

    onBars() { this.dirty = true; this.ask(); }

    destroy() {
      this.dead = true;
      clearInterval(this.timer);
      if (this.off) this.off();
      const cell = this.cell;
      try { if (cell.chart) cell.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange); } catch (_) { /* chart gone */ }
      try { if (cell.candles) cell.candles.detachPrimitive(this.layer); } catch (_) { /* series gone */ }
    }
  }

  api.overlay = (cell) => new Overlay(cell);
  window.HBBookEvents = api;
}
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
