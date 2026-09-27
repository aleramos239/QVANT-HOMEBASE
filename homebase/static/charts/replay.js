/* Homebase Charts — Bar Replay, the pure half. No browser globals at load time: the Node tests load this file
   directly. replayui.js (impure: the toolbar button, the floating control bar, the dimming overlay, the
   PRACTICE block and lines) is the only caller in the browser.

   Task 1 (2026-09-27 plan): the server's replay_state message normalised, the cursor formatted as an ET date +
   time, the start field's validation window, the speed menu's labels, and the three ws op builders
   (`replay_start` / `replay_ctl` / `replay_stop`). The exact message shapes are the protocol's
   (homebase/charts/barreplay.py) -- see its module docstring.

   Task 2: practice trading -- "the simulator". The trigger/fill primitives (toTick, tickCmp, firstAtOrAbove/
   Below, triggerIndex, fillPrice) are a direct port of homebase/backtest/engine.py's tick fill law (its own
   module docstring, and the cited line numbers below); PracticeSim is the order/position/trade bookkeeping
   around them (engine.py's _Sim, simplified to one position at a time -- a practice block, not a strategy
   runner); BarFeed turns the replay stream's bars into the print segments PracticeSim.feed() wants, since this
   layer only ever sees OHLC bars, never raw ticks (see BarFeed's own comment for the exact approximation and
   where it is exact instead of approximate). NEVER reference the desk client, its REST API, or an HBTradeUI
   send function from this file (Global Constraints, isolation) -- tests/js/replay.test.mjs asserts it by
   reading this file's own source text, and replayui.js's. */
(function () {
'use strict';

const FIRST_DATE = '2021-09-22';       // the archive's first session (barreplay.py FIRST_DATE)
const SPEEDS = [1, 2, 5, 10, 30, 60, 'bar'];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

const isObj = (v) => v != null && typeof v === 'object';

/* The server's `replay_state` (or the `stopped` one sent on replay_stop), normalised for the UI: {id, date,
   cursorMs, speed, playing, done, stopped}. null for anything that is not an object -- the caller ignores it. */
function parseState(msg) {
  if (!isObj(msg)) return null;
  return {
    id: typeof msg.id === 'string' ? msg.id : (msg.id == null ? '' : String(msg.id)),
    date: typeof msg.date === 'string' ? msg.date : '',
    cursorMs: Number.isFinite(msg.cursor_ms) ? msg.cursor_ms : 0,
    speed: SPEEDS.includes(msg.speed) ? msg.speed : 1,
    playing: msg.playing === true,
    done: msg.done === true,
    stopped: msg.stopped === true,
  };
}

const CURSOR_FMT = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });

/* replay_state's cursor_ms (epoch ms) as "YYYY-MM-DD HH:MM:SS ET" -- the floating control bar's clock. '' for
   anything that is not a finite instant. */
function fmtCursor(ms) {
  if (!Number.isFinite(ms)) return '';
  const p = {};
  for (const x of CURSOR_FMT.formatToParts(new Date(ms))) p[x.type] = x.value;
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second} ET`;
}

/* The start field: date is an archived session (FIRST_DATE to before `today`, both "YYYY-MM-DD" -- plain
   string comparison sorts correctly since the format is fixed-width), time is "HH:MM" in range. Matches the
   server's own check (barreplay.py _parse_start / _at) closely enough to catch a bad field before it goes
   over the wire; the server still re-checks (a session can be missing even inside the window). */
function validStart(date, time, today) {
  if (typeof date !== 'string' || typeof time !== 'string' || typeof today !== 'string') return false;
  if (!DATE_RE.test(date) || !TIME_RE.test(time)) return false;
  return date >= FIRST_DATE && date < today;
}

/* The speed menu's label: "1×" .. "60×", "Bar". */
function speedLabel(s) { return s === 'bar' ? 'Bar' : `${s}×`; }

/* ---- ws op builders (protocol: homebase/charts/barreplay.py) ---- */
/* Starting a replay always begins at speed "bar" (paused, one bar at a time): the floating bar's speed menu
   changes it afterwards through ctlOp('speed', ...). */
function startOp(id, date, startEt) {
  return { op: 'replay_start', id: String(id), date, start_et: startEt, speed: 'bar' };
}
function ctlOp(id, action, extra) {
  return { op: 'replay_ctl', id: String(id), action, ...(extra || {}) };
}
function stopOp(id) {
  return { op: 'replay_stop', id: String(id) };
}

/* ================================================================================================
   Task 2: practice trading -- the fill law (homebase/backtest/engine.py) and the practice simulator.
   ================================================================================================ */

const DEFAULT_COSTS = { commissionRt: 4.0, slippageTicks: 1.0 };   // engine.py:96-98 Costs' own defaults

/* engine.py:52-53 to_tick. (Python's round() is banker's-rounding; Math.round here is round-half-up -- the
   two differ only exactly at a x.5 boundary, which a real price essentially never lands on, so this is not
   replicated; every OTHER case, including the float-noise case tick_cmp exists for, matches exactly.) */
function toTick(px, tick) {
  const snapped = Math.round(px / tick) * tick;
  return Math.round(snapped * 1e6) / 1e6;
}

/* engine.py:56-66 tick_cmp: -1/0/1, tolerant of float64 noise on a non-power-of-two tick grid (eps = tick*1e-6). */
function tickCmp(a, b, tick) {
  const eps = tick * 1e-6;
  if (a > b + eps) return 1;
  if (a < b - eps) return -1;
  return 0;
}

/* engine.py:69-79 first_at_or_above, unchunked: `px` here is a short print segment (a bar's worth), never a
   whole session's tape, so the CHUNK prefilter that makes engine.py's version fast at scale buys nothing. */
function firstAtOrAbove(px, level, tick) {
  for (let i = 0; i < px.length; i++) if (tickCmp(px[i], level, tick) >= 0) return i;
  return px.length;
}
/* engine.py:82-92 first_at_or_below. */
function firstAtOrBelow(px, level, tick) {
  for (let i = 0; i < px.length; i++) if (tickCmp(px[i], level, tick) <= 0) return i;
  return px.length;
}

/* engine.py:277-286 _Sim._trigger: the index in `px` (oldest print first) where order `o` {side: +1/-1, kind:
   'market'|'stop'|'limit', price} fires, or px.length if it does not fire in this segment at all. A stop
   fires ON TOUCH; a limit needs ONE TICK OF PENETRATION past its price (never a bare touch). */
function triggerIndex(o, px, tick) {
  if (o.kind === 'market') return 0;
  if (o.kind === 'stop') {
    return o.side > 0 ? firstAtOrAbove(px, o.price, tick) : firstAtOrBelow(px, o.price, tick);
  }
  const lvl = o.side > 0 ? toTick(o.price - tick, tick) : toTick(o.price + tick, tick);
  return o.side > 0 ? firstAtOrBelow(px, lvl, tick) : firstAtOrAbove(px, lvl, tick);
}

/* engine.py:288-295 _Sim._fill_price: a limit fills AT its own price (no slip -- it never trades through
   itself); a stop fills at the WORSE of (its trigger, the actual print) plus slip, so a gap through the level
   costs the gap, never the trigger price; a market fills at the print, plus slip. `slip` is already in price
   units (costs.slippageTicks * tick), matching engine.py's own `self.slip`. */
function fillPrice(o, printPx, tick, slip) {
  if (o.kind === 'limit') return o.price;
  if (o.kind === 'stop') {
    const raw = o.side > 0 ? Math.max(o.price, printPx) + slip : Math.min(o.price, printPx) - slip;
    return toTick(raw, tick);
  }
  return toTick(printPx + o.side * slip, tick);
}

function round2(x) { const r = Math.round(x * 100) / 100; return r === 0 ? 0 : r; }

/* PracticeSim: one chart's practice book -- engine.py's _Sim (dataclasses Order/Position/Trade, methods new_
   order/advance/_fill/_close), simplified to ONE position at a time (a practice Buy/Sell block, not a strategy
   runner: there is never more than one pending entry or open position to manage). No desk reference anywhere
   in this class (Global Constraints) -- `tick`/`pv`/`costs` are plain numbers the caller supplies (replayui.js
   reads `pv` from the chart's own `cell.pv`, falling back to pointValue() below). */
class PracticeSim {
  constructor(tick, pv, costs) {
    this.tick = tick;
    this.pv = pv;
    const c = costs || DEFAULT_COSTS;
    this.slip = (Number.isFinite(c.slippageTicks) ? c.slippageTicks : DEFAULT_COSTS.slippageTicks) * tick;   // engine.py:253
    this.commRt = Number.isFinite(c.commissionRt) ? c.commissionRt : DEFAULT_COSTS.commissionRt;               // engine.py:254
    this.orders = [];       // working, in creation order (engine.py:258)
    this.position = null;   // engine.py's `positions` list, here at most one
    this.trades = [];       // closed trades this session (engine.py's res.trades)
    this._ids = 0;
  }

  _nextId() { return ++this._ids; }

  /* A new working order: side +1 buy / -1 sell, kind 'market'|'limit'|'stop', price (trigger/limit; null for
     market), role 'entry'|'sl'|'tp'. Not itself gated on `enter()`'s flat/no-pending-entry rule, so sl/tp
     (created internally by _fill) always go through even though an entry is technically "pending" then. */
  order(side, kind, price, qty, role) {
    const o = { id: this._nextId(), side, kind, price: price == null ? null : toTick(price, this.tick), qty, role };
    this.orders.push(o);
    return o;
  }

  cancel(id) {
    const i = this.orders.findIndex((o) => o.id === id);
    if (i < 0) return false;
    this.orders.splice(i, 1);
    return true;
  }

  /* A new entry (Market/Limit/Stop from the practice block or the chart menu): refused (null) while a
     position is open or another entry is still working -- one thing at a time, like the real block. `sl`/`tp`
     are absolute prices (or null/undefined for none), computed by the caller -- typically HBTrade.bracket on
     the global SL/TP-tick prefs, from the same reference price real trading would use. */
  enter(side, kind, price, qty, sl, tp) {
    if (this.position || this.orders.some((o) => o.role === 'entry')) return null;
    const o = this.order(side, kind, price, qty, 'entry');
    o._sl = sl == null ? null : sl;
    o._tp = tp == null ? null : tp;
    return o;
  }

  /* Close the open position at the market -- the line's ×, or a manual Flatten. Fills like any other market
     order on the next feed(). null if flat. */
  flatten() {
    if (!this.position) return null;
    const pos = this.position;
    if (pos.sl) this.cancel(pos.sl.id);
    if (pos.tp) this.cancel(pos.tp.id);
    return this.order(-pos.side, 'market', null, pos.qty, 'flat');
  }

  /* engine.py:297-312 _Sim.advance: process one segment of prints (oldest first, e.g. from barPrints()/
     BarFeed below), filling whatever triggers, earliest print first -- another order can still trigger on
     that SAME print index once the first is out of the way. `ms`: the segment's timestamp, stamped on any
     resulting trade (bar-granular, since this layer has no per-print times -- see BarFeed). */
  feed(prices, ms) {
    if (!prices || !prices.length) return;
    let i = 0;
    while (this.orders.length && i < prices.length) {
      let bestK = prices.length, best = null;
      for (const o of this.orders) {
        const k = i + triggerIndex(o, prices.slice(i), this.tick);
        if (k < bestK) { bestK = k; best = o; }
      }
      if (best === null || bestK >= prices.length) break;
      this._fill(best, prices[bestK], ms);
      i = bestK;
    }
  }

  /* engine.py:314-345 _Sim._fill (role 'entry'): opens the position and, from the fill, creates its SL/TP as
     plain stop/limit orders on the OPPOSITE side (engine.py:338-344) -- exactly the same primitives above then
     apply to them too, so an SL fills on touch and a TP needs its own 1-tick penetration, like any other
     stop/limit. role 'sl'/'tp'/'flat': engine.py:318-319,347-351 -- close the position, and cancel whichever
     of its sl/tp did NOT just fire (a no-op if it's the one that did, since it is already removed above). */
  _fill(o, printPx, ms) {
    const fill = fillPrice(o, printPx, this.tick, this.slip);
    this.cancel(o.id);
    if (o.role !== 'entry') { this._close(fill, ms, o.role); return; }
    this.position = { side: o.side, qty: o.qty, entryPrice: fill, entryMs: ms, sl: null, tp: null };
    if (o._sl != null) this.position.sl = this.order(-o.side, 'stop', o._sl, o.qty, 'sl');
    if (o._tp != null) this.position.tp = this.order(-o.side, 'limit', o._tp, o.qty, 'tp');
  }

  /* engine.py:347-369 _close (mae/mfe/bars/seconds dropped: not shown anywhere in the practice P&L strip). */
  _close(fill, ms, reason) {
    const pos = this.position;
    if (pos.sl) this.cancel(pos.sl.id);
    if (pos.tp) this.cancel(pos.tp.id);
    this.position = null;
    const gross = pos.side * (fill - pos.entryPrice) * this.pv * pos.qty;         // engine.py:357
    const commission = this.commRt * pos.qty;                                    // engine.py:358
    this.trades.push({ side: pos.side > 0 ? 'long' : 'short', qty: pos.qty, entryPrice: pos.entryPrice,
      entryMs: pos.entryMs, exitPrice: fill, exitMs: ms, exitReason: reason,
      gross: round2(gross), commission: round2(commission), net: round2(gross - commission) });
  }

  /* Unrealised P&L of the open position at `lastPrice` (0 while flat or with no price yet). */
  openPnl(lastPrice) {
    if (!this.position || lastPrice == null) return 0;
    return round2(this.position.side * (lastPrice - this.position.entryPrice) * this.pv * this.position.qty);
  }
  /* Realised P&L: the sum of every closed trade's net, this session. */
  realizedPnl() { return round2(this.trades.reduce((acc, t) => acc + t.net, 0)); }
  tradeCount() { return this.trades.length; }
}

/* A closed OHLC bar as an ordered path of representative prints -- OUR OWN convention (engine.py has no
   equivalent: it always has the real tape), for feeding PracticeSim.feed() when the replay stream is
   bar-shaped rather than raw ticks. Common backtesting convention when only OHLC is known: a bar that closed
   at or above its open is assumed to have dipped to its low before rallying to its high; one that closed below
   is assumed to have rallied to its high before falling to its low. EXACT, not approximate, on a tick-replay
   chart (spec `tick:N`): there every bar IS one real print (o===h===l===c), and this collapses to that single
   value. */
function barPrints(bar) {
  const { o, h, l, c } = bar;
  if (o === h && h === l && l === c) return [o];
  return c >= o ? [o, l, h, c] : [o, h, l, c];
}

/* BarFeed: turns the replay stream's bar updates (homebase/charts/server.py's `update` message: `closed[]`
   bars, then the current `live` one, both flagged `replay: true`) into the print segments PracticeSim.feed()
   wants.
     - closedBar(): a finished bar is fed once, in full (barPrints()), then the live tracker resets for the
       NEXT bar's own open.
     - liveBar(): the FORMING bar arrives again and again as it grows (its h/l/c are cumulative, from the same
       bar's start). Feeding the WHOLE bar's path again on every update would re-present an extreme that was
       already fed on a PRIOR update as if it were happening NOW -- an order placed in between could then fire
       on a price the market touched before that order even existed. So only the genuinely NEW high/low (if
       any) since the last update are fed, chained from the last update's close (not the bar's own open) --
       ordered the same dip-then-rally / rally-then-dip way as barPrints(), using this update's own close to
       decide which. Exact on a tick-replay chart, where every "bar" is one real print and there is never a
       new high AND a new low in the same update. */
class BarFeed {
  constructor(sim) { this.sim = sim; this.liveBase = null; }

  closedBar(bar, ms) {
    this.sim.feed(barPrints(bar), ms);
    this.liveBase = null;
  }

  liveBar(bar, ms) {
    const fresh = this.liveBase == null;
    const base = fresh ? { h: -Infinity, l: Infinity, c: bar.o } : this.liveBase;
    const newHigh = bar.h > base.h ? bar.h : null;
    const newLow = bar.l < base.l ? bar.l : null;
    const upFirst = bar.c >= base.c;
    const exts = (upFirst ? [newLow, newHigh] : [newHigh, newLow]).filter((x) => x != null);
    const path = fresh ? [bar.o, ...exts] : exts;
    if (!path.length || path[path.length - 1] !== bar.c) path.push(bar.c);
    this.sim.feed(path, ms);
    this.liveBase = { h: Math.max(base.h, bar.h), l: Math.min(base.l, bar.l), c: bar.c };
  }
}

/* USD per 1.00 price move, per contract -- homebase/contracts.py's _SPECS, verified here for the roots the
   practice feature is checked against. The chart's own `cell.pv` (from the server's `history`/`point_value`,
   itself computed from contracts.py) is the single source of truth and is preferred whenever it is known;
   this is only the fallback for the rare gap before a chart's first history arrives. */
const POINT_VALUE = { NQ: 20, ES: 50, YM: 5, RTY: 50, GC: 100, SI: 5000, CL: 1000, BTC: 5 };
function pointValue(root) {
  const v = POINT_VALUE[String(root || '').toUpperCase()];
  return v == null ? null : v;
}

/* ---- the practice session log (localStorage key hb.practice; replayui.js does the actual try/catch'd
   localStorage.getItem/setItem -- Global Constraints: "localStorage only through try/catch") ---- */
const PRACTICE_KEY = 'hb.practice';
const PRACTICE_MAX = 200;

/* What a finished practice session writes: {date, root, trades[], net} (the brief's own shape). */
function practiceSession(date, root, sim) {
  return { date, root, trades: sim.trades.slice(), net: sim.realizedPnl() };
}

/* The next value to store under hb.practice: `existing` (whatever localStorage.getItem parsed to) with
   `session` appended, capped at PRACTICE_MAX -- the OLDEST sessions drop first. A non-array `existing` (unset,
   corrupt, or foreign) starts fresh rather than throwing. */
function pushPracticeSession(existing, session) {
  const list = Array.isArray(existing) ? existing.slice() : [];
  list.push(session);
  return list.length > PRACTICE_MAX ? list.slice(list.length - PRACTICE_MAX) : list;
}

const api = { FIRST_DATE, SPEEDS, parseState, fmtCursor, validStart, speedLabel, startOp, ctlOp, stopOp,
  DEFAULT_COSTS, toTick, tickCmp, firstAtOrAbove, firstAtOrBelow, triggerIndex, fillPrice, PracticeSim,
  barPrints, BarFeed, POINT_VALUE, pointValue, PRACTICE_KEY, PRACTICE_MAX, practiceSession, pushPracticeSession };
if (typeof window !== 'undefined') window.HBReplay = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
