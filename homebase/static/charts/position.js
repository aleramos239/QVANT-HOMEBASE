/* Homebase Charts — the Long / Short position tool (TradingView's risk/reward
   planner). This half is pure: a box's geometry and handles, the handles'
   clamps, the label texts, and how the planned trade played out on the
   chart's bars. The canvas drawing (drawPosition, at the end of the file)
   runs in the page only. No browser globals at load time: the Node tests
   load this file directly.

   A position is {id, type: 'long'|'short', points: [entry, target, stop], qty, color?}:
     entry  = {t: t0, p}   t0 = the box's left edge (a bar start, epoch ms)
     target = {t: t1, p}   t1 = the box's right edge (target and stop share it)
     stop   = {t: t1, p}
   long: stop < entry < target · short: target < entry < stop · every gap at least 1 tick. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const D = need('HBDrawings', './drawings.js');

const WIDTH_BARS = 20;       // a new box reaches 20 bars to the right
const RISK_PANE = 0.08;      // a new box's risk: the price distance of 8% of the price pane's height ...
const MIN_RISK_TICKS = 4;    // ... and at least 4 ticks
const QTY_MAX = 10000;
const MINUS = '−';      // the labels' minus sign, as in the spec: −25.00, −$500

const isPosition = (d) => !!d && (d.type === 'long' || d.type === 'short');

/* A new box's risk: `span` (the price distance of 8% of the pane's height) on the tick grid, at least 4 ticks. */
function risk(span, tick) {
  return D.roundToTick(Math.max(MIN_RISK_TICKS * tick, Math.abs(span)), tick);
}

/* A new box at (t0, entry) reaching to t1: the stop one risk R away and the target two (RR 1:2); a short is
   mirrored. Quantity 1. */
function create(type, t0, t1, entry, R, tick) {
  const dir = type === 'short' ? -1 : 1, r = (p) => D.roundToTick(p, tick);
  return { type, points: [{ t: t0, p: r(entry) }, { t: t1, p: r(entry + dir * 2 * R) }, { t: t1, p: r(entry - dir * R) }],
    qty: 1 };
}

/* The handles [[x, y] x 4]: 0 (t0, entry), 1 (t0, target), 2 (t0, stop), 3 (t1, entry); null when a point
   cannot be placed. geo = {x: (t) => px | null, y: (p) => px | null}. */
function handles(d, geo) {
  const [E, T, S] = d.points, x0 = geo.x(E.t), x1 = geo.x(T.t), yE = geo.y(E.p), yT = geo.y(T.p), yS = geo.y(S.p);
  if ([x0, x1, yE, yT, yS].some((v) => v == null)) return null;
  return [[x0, yE], [x0, yT], [x0, yS], [x1, yE]];
}

/* A handle (by index) first, then anywhere inside the box (t0 to t1, target to stop). */
function hitTest(d, pt, geo) {
  const hs = handles(d, geo);
  if (!hs) return null;
  for (let i = 0; i < hs.length; i++) {
    if (Math.hypot(pt.x - hs[i][0], pt.y - hs[i][1]) <= D.HANDLE_TOL) return { part: 'handle', index: i };
  }
  const [[x0], [, yT], [, yS], [x1]] = hs, tol = D.LINE_TOL;
  const inside = pt.x >= Math.min(x0, x1) - tol && pt.x <= Math.max(x0, x1) + tol
    && pt.y >= Math.min(yT, yS) - tol && pt.y <= Math.max(yT, yS) + tol;
  return inside ? { part: 'body' } : null;
}

/* d with handle k dragged to (t, p), clamped so the box stays a valid trade:
   0 moves t0 and the entry (the entry at least a tick inside (stop, target); t0 at least a bar before t1);
   1 moves the target (at least a tick beyond the entry); 2 the stop (at least a tick beyond the entry, on the
   risk side); 3 moves t1 (at least a bar after t0). ctx = {bars, isTime, barMs, tick}. */
function setHandle(d, k, t, p, ctx) {
  const tick = ctx.tick, long = d.type === 'long', r = (x) => D.roundToTick(x, tick);
  const L = (x) => D.logicalOf(ctx.bars, x, ctx.isTime, ctx.barMs);
  let [E, T, S] = d.points;
  if (k === 0) {
    const lo = long ? S.p + tick : T.p + tick, hi = long ? T.p - tick : S.p - tick;
    const t0 = L(t) != null && L(t) > L(T.t) - 1 ? D.shiftTime(T.t, -1, ctx) : t;
    E = { t: t0, p: r(Math.min(hi, Math.max(lo, p))) };
  } else if (k === 1) {
    T = { t: T.t, p: r(long ? Math.max(p, E.p + tick) : Math.min(p, E.p - tick)) };
  } else if (k === 2) {
    S = { t: S.t, p: r(long ? Math.min(p, E.p - tick) : Math.max(p, E.p + tick)) };
  } else if (k === 3) {
    const t1 = L(t) != null && L(t) < L(E.t) + 1 ? D.shiftTime(E.t, 1, ctx) : t;
    T = { t: t1, p: T.p };
    S = { t: t1, p: S.p };
  }
  return { ...d, points: [E, T, S] };
}

const sign = (v) => (v > 0 ? '+' : v < 0 ? MINUS : '');

/* "$1,000" · "$15.63": whole dollars show no cents. */
function fmtUsd(v) {
  const cents = Math.round(Math.abs(v) * 100), whole = cents % 100 === 0;
  return '$' + (cents / 100).toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 });
}

/* A P&L for a price move `move` in the trade's favour: dollars (x point value x qty) when the point value is
   known, else the move in points (one contract): "+$1,000" · "−$500" · "$0" · "+50.00". */
function fmtPnl(move, pv, qty, tick) {
  if (pv == null) {
    const m = D.roundToTick(move, tick);
    return sign(m) + Cat.fmtPrice(Math.abs(m), tick);
  }
  const usd = move * pv * qty;
  return sign(Math.round(usd * 100)) + fmtUsd(usd);
}

/* "1:2" · "1:1.5": reward ÷ risk, at most 2 decimals, trailing zeros trimmed. */
function rr(d) {
  const [E, T, S] = d.points, loss = Math.abs(E.p - S.p);
  return `1:${loss > 0 ? Number((Math.abs(T.p - E.p) / loss).toFixed(2)) : '—'}`;
}

/* The box's texts: the target and stop labels ("Target 30,950.00 · +50.00 (0.16%) · 200 ticks · +$1,000")
   and the centre label's first line ("RR 1:2 · Qty 1"). The target is a gain and the stop a loss, for a short
   as for a long. The "· $…" part needs the point value (pv). */
function labels(d, pv, tick) {
  const [E, T, S] = d.points, qty = d.qty || 1;
  const part = (name, px, gain) => {
    const dist = Math.abs(D.roundToTick(px - E.p, tick)), s = gain ? '+' : MINUS, n = Math.round(dist / tick);
    const pct = E.p ? (dist / Math.abs(E.p) * 100).toFixed(2) : '0.00';
    const bits = [`${name} ${Cat.fmtPrice(px, tick)}`, `${s}${Cat.fmtPrice(dist, tick)} (${pct}%)`, `${n} tick${n === 1 ? '' : 's'}`];
    if (pv != null) bits.push(s + fmtUsd(dist * pv * qty));
    return bits.join(' · ');
  };
  return { target: part('Target', T.p, true), stop: part('Stop', S.p, false),
    center: `RR ${rr(d)} · Qty ${qty.toLocaleString('en-US')}` };
}

/* How the planned trade played out on the chart's bars ([{ms, o, h, l, c}] ascending), honest about what bars
   cannot tell. Entered on the first bar from the one holding t0 whose range holds the entry (none up to t1:
   'none'). An entry bar that also reaches the target or stop, or a later bar reaching both, is 'ambiguous'.
   Else the first later bar (up to t1) reaching one closes it ('closed', with the path from the entry bar to
   the exit bar); with no exit, 'open' at the last close when t1 is at or after the last bar, else 'expired'
   ("Open at end") at the close of the last bar at or before t1. */
function outcome(d, bars, pv, tick) {
  const [E, T, S] = d.points, long = d.type === 'long', dir = long ? 1 : -1, qty = d.qty || 1, n = bars.length;
  const none = { kind: 'none', text: 'Not entered', path: null };
  if (!n) return none;
  const from = Math.max(0, D.barIndexAt(bars, E.t)), to = D.barIndexAt(bars, T.t);
  let ie = -1;
  for (let i = from; i <= to; i++) if (bars[i].l <= E.p && E.p <= bars[i].h) { ie = i; break; }
  if (ie < 0) return none;
  const hitT = (b) => (long ? b.h >= T.p : b.l <= T.p), hitS = (b) => (long ? b.l <= S.p : b.h >= S.p);
  const eb = bars[ie];
  if (hitT(eb) || hitS(eb)) return { kind: 'ambiguous', text: 'Entry bar touched stop/target', path: null };
  for (let i = ie + 1; i <= to; i++) {
    const b = bars[i], t = hitT(b), s = hitS(b);
    if (t && s) return { kind: 'ambiguous', text: 'Stop and target in one bar', path: null };
    if (t || s) {
      const px = t ? T.p : S.p;
      return { kind: 'closed', text: `Closed ${fmtPnl((px - E.p) * dir, pv, qty, tick)}`,
        path: { a: { t: eb.ms, p: E.p }, b: { t: b.ms, p: px } } };
    }
  }
  if (T.t >= bars[n - 1].ms) return { kind: 'open', text: `Open ${fmtPnl((bars[n - 1].c - E.p) * dir, pv, qty, tick)}`, path: null };
  return { kind: 'expired', text: `Open at end ${fmtPnl((bars[to].c - E.p) * dir, pv, qty, tick)}`, path: null };
}

/* '' when (entry, target, stop, qty) make a valid box of this type, else why not (the dialog shows it). */
function validate(type, entry, target, stop, qty, tick) {
  if (![entry, target, stop].every(Number.isFinite)) return 'Entry, target and stop are prices';
  if (!Number.isInteger(qty) || qty < 1 || qty > QTY_MAX) return `Qty is a whole number from 1 to ${QTY_MAX.toLocaleString('en-US')}`;
  const above = (a, b) => D.roundToTick(b - a, tick) >= tick;   // b at least a tick above a
  if (type === 'long' && !(above(stop, entry) && above(entry, target))) return 'A long needs stop < entry < target, at least 1 tick apart';
  if (type === 'short' && !(above(target, entry) && above(entry, stop))) return 'A short needs target < entry < stop, at least 1 tick apart';
  return '';
}

const api = { WIDTH_BARS, RISK_PANE, MIN_RISK_TICKS, QTY_MAX, MINUS, isPosition, risk, create, handles, hitTest,
  setHandle, fmtUsd, fmtPnl, rr, labels, outcome, validate };
if (typeof window !== 'undefined') window.HBPosition = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
