/* Homebase Charts — HBTape: the Time & Sales panel, the pure half (2026-10-21 tape plan). The ring of raw
   prints the ws stream fills, the aggressor orders rebuilt from it, the size/side filter and the ET clock.
   The wire (tapelive.py): {"type":"tape", root, s, i0, rows: [[ts_ms, price, size, side, id], ...], reset?}
   where i0 is the index of rows[0] in the session's tape and side is the Tick's own +1 buy / -1 sell.
   An order is a run of consecutive prints with the same ts_ms and the same side: the rule bars.py uses for
   `ords` and the sweeps, same row order, so the panel agrees with the chart. The DOM rendering lives in
   tapeui.js; this file has no browser globals at load time so the Node tests load it directly. */
(function () {
'use strict';

const RING = 5000;   // prints kept; about two minutes of a busy ES open

function empty() { return { root: null, s: null, i0: 0, next: 0, rows: [] }; }

/* A message into the ring: a reset (or another root / session) replaces it, otherwise only the rows past
   what was already applied are appended, and the oldest fall off the front. Never mutates `state`. */
function apply(state, msg) {
  const st = state && Array.isArray(state.rows) ? state : empty();
  const rows = Array.isArray(msg && msg.rows) ? msg.rows : [];
  const i0 = Number.isFinite(msg && msg.i0) ? msg.i0 : 0;
  const fresh = !!msg.reset || msg.root !== st.root || msg.s !== st.s;
  let all, base;
  if (fresh) { all = rows; base = i0; }
  else {
    const skip = Math.max(0, st.next - i0);
    if (skip >= rows.length) return st;
    all = st.rows.concat(rows.slice(skip));
    base = st.i0;
  }
  if (all.length > RING) { base += all.length - RING; all = all.slice(all.length - RING); }
  return { root: msg.root, s: msg.s, i0: base, next: i0 + rows.length, rows: all };
}

function order(r, i) {
  return { t: r[0], side: r[3], size: r[2], n: 1, lo: r[1], hi: r[1], vwap: r[1], i0: i };
}
function join(o, r) {
  const size = o.size + r[2];
  o.vwap = (o.vwap * o.size + r[1] * r[2]) / size;
  o.size = size;
  o.n += 1;
  if (r[1] < o.lo) o.lo = r[1];
  if (r[1] > o.hi) o.hi = r[1];
}
/* The orders in `rows` (whose first row sits at session index i0). `prev`, the last order of the previous
   call, is continued when the first run is its own run cut across two messages: same ms, same side, and it
   ends exactly where these rows start. The continued order is a new object; prev is left alone. */
function orders(rows, i0, prev) {
  const base = Number.isFinite(i0) ? i0 : 0;
  const out = [];
  let o = null;
  if (prev && rows.length && prev.i0 + prev.n === base && prev.t === rows[0][0] && prev.side === rows[0][3]) {
    o = { ...prev };
    out.push(o);
  }
  rows.forEach((r, k) => {
    if (o && o.t === r[0] && o.side === r[3]) join(o, r);
    else { o = order(r, base + k); out.push(o); }
  });
  return out;
}
/* Every print as an order of its own (the Raw view), so one list shape feeds the panel in both modes. */
function prints(rows, i0) {
  const base = Number.isFinite(i0) ? i0 : 0;
  return rows.map((r, k) => order(r, base + k));
}
/* size in [min, max] (a null / non-finite bound is no bound) and the side (+1 / -1; 0 or null = both). */
function filter(list, min, max, side) {
  const lo = Number.isFinite(min) ? min : -Infinity, hi = Number.isFinite(max) ? max : Infinity;
  const s = side > 0 ? 1 : side < 0 ? -1 : 0;
  return list.filter((x) => x.size >= lo && x.size <= hi && (!s || Math.sign(x.side) === s));
}

/* "09:30:01.234": New York wall time to the millisecond (the page's own ET clocks are Intl too, app.js). */
const ET_MS = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit',
  second: '2-digit', fractionalSecondDigits: 3, hourCycle: 'h23' });
function fmtTime(ts) { return Number.isFinite(ts) ? ET_MS.format(new Date(ts)) : ''; }

const api = { RING, empty, apply, orders, prints, filter, fmtTime };
if (typeof window !== 'undefined') window.HBTape = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
