/* Homebase Charts — HBTradePure: the small set of trade.js helpers that are genuinely pure (no
   desk state, nothing that can send) and are shared with pages that never load trade.js itself —
   today Bar Replay's PracticeSim (SL/TP prefs parsing, bracket math) and the Strategy Tester
   (money formatting), both of which run on the Backtest page (2026-09-28 three-tabs plan): that
   page loads no trading module at all, trade.js included.

   trade.js requires this module and re-exports these exact names on its own `api`, unchanged —
   every existing trade.js caller (tradeui.js, tradelines.js, orderpanel.js) sees no difference.
   replayui.js / tester.js / testerui.js read `window.HBTrade || window.HBTradePure`: on Charts
   that still resolves to HBTrade (unchanged behaviour); on Backtest, HBTrade doesn't exist and it
   resolves here instead.

   `isObj`/`idList`/`int` below are tiny private duplicates of trade.js's own copies (parsePrefs
   needs them) — not shared, on purpose: trade.js uses them far more broadly than this file does,
   so sharing would pull in more coupling than the five names above are worth.

   No browser globals at load time: the Node tests load this file directly, exactly like
   catalog.js. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const Pos = need('HBPosition', './position.js');

const MINUS = '−';
const PREFS_KEY = 'hb_trade_prefs';
const QTY_MAX = 10000;   // a sanity clamp only: the desk's limits decide

const int = (v, lo, hi, dflt) => { const n = Math.round(Number(v)); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt; };
const isObj = (o) => !!o && typeof o === 'object' && !Array.isArray(o);
/* A list of account ids: strings of 1-64 characters, de-duplicated, at most 20 (a fresh array). */
function idList(v) {
  return Array.isArray(v) ? [...new Set(v.filter((x) => typeof x === 'string' && x.length >= 1 && x.length <= 64))].slice(0, 20) : [];
}

/* ---- preferences (per viewer: localStorage hb_trade_prefs) -- see trade.js's own docstring for
   the field-by-field rationale (PracticeSim and the real Buy/Sell block read the exact same
   stored prefs, by design: one SL/TP-ticks setting, not two). This is the parse alone. */
function parsePrefs(text) {
  let o = null;
  try { o = JSON.parse(text); } catch (_) { o = null; }
  if (!isObj(o)) o = {};
  const ticked = idList(o.ticked);
  const sw = (v) => (typeof v === 'boolean' ? v : true);
  return { ticked, oneClick: o.oneClick === true, oneClickChart: sw(o.oneClickChart), oneClickPanel: sw(o.oneClickPanel),
    qty: int(o.qty, 1, QTY_MAX, 1), slTicks: 0, tpTicks: 0 };
}
const prefsText = (p) => JSON.stringify(parsePrefs(JSON.stringify(p)));

function roundTick(p, tick) { return tick > 0 ? Number((Math.round(p / tick) * tick).toFixed(Cat.decimals(tick))) : p; }
/* SL/TP from the tick defaults (0 = off) around ref: the order's price, or the last trade for a Market order. */
function bracket(side, ref, prefs, tick) {
  if (ref == null || !(tick > 0)) return { sl: null, tp: null };
  const s = side === 'Buy' ? 1 : -1;
  return { sl: prefs.slTicks > 0 ? roundTick(ref - s * prefs.slTicks * tick, tick) : null,
    tp: prefs.tpTicks > 0 ? roundTick(ref + s * prefs.tpTicks * tick, tick) : null };
}

const sign = (v) => (v > 0 ? '+' : v < 0 ? MINUS : '');
function usd(v) { return v == null || !Number.isFinite(v) ? null : sign(Math.round(v * 100)) + Pos.fmtUsd(v); }
function money(v) { return v == null || !Number.isFinite(v) ? '—' : (Math.round(v * 100) < 0 ? MINUS : '') + Pos.fmtUsd(v); }

const api = { PREFS_KEY, parsePrefs, prefsText, bracket, roundTick, money, usd };
if (typeof window !== 'undefined') window.HBTradePure = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
