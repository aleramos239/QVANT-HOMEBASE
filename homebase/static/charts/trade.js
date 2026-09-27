/* Homebase Charts — trading from the chart, the pure half:
     - the viewer's trade preferences;
     - what the page may do right now;
     - Limit or Stop for a clicked price;
     - order bodies and client ids;
     - the position / order / bracket lines with their labels and dollars;
     - the confirm dialog's texts and the toasts;
     - the execution markers;
     - the live strategies' badge / lines / markers;
     - the bottom panel's table rows.
   It reads the desk's state exactly as the desk's snapshot shapes it (homebase/trading.py
   ChartDesk.snapshot). No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const Pos = need('HBPosition', './position.js');

const MINUS = '−';
const PREFS_KEY = 'hb_trade_prefs';
const QTY_MAX = 10000;          // a sanity clamp only: the desk's limits decide
const QUOTE_STALE_MS = 30000;   // the desk's QUOTE_MAX_AGE_S: an older quote is shown greyed
const BOT_NAMES = { nq930: '9:30 bot', ym930: '9:30 bot', nq10am: '10am bot' };
const ET = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' });

const int = (v, lo, hi, dflt) => { const n = Math.round(Number(v)); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt; };
const accountsOf = (state) => (state && state.accounts) || [];

/* A list of account ids: strings of 1-64 characters, de-duplicated, at most 20 (a fresh array). */
function idList(v) {
  return Array.isArray(v) ? [...new Set(v.filter((x) => typeof x === 'string' && x.length >= 1 && x.length <= 64))].slice(0, 20) : [];
}
const isObj = (o) => !!o && typeof o === 'object' && !Array.isArray(o);

/* ---- preferences (per viewer: localStorage hb_trade_prefs) ----
   `ticked` is the RETIRED global account list: nothing routes orders from it any more (2026-09-27 plan, Task 2).
   It is still parsed only so the page can migrate an old list onto one chart once (migrateTicked), then clear it. */
function parsePrefs(text) {
  let o = null;
  try { o = JSON.parse(text); } catch (_) { o = null; }
  if (!isObj(o)) o = {};
  const ticked = idList(o.ticked);
  return { ticked, oneClick: o.oneClick === true, qty: int(o.qty, 1, QTY_MAX, 1),
    slTicks: int(o.slTicks, 0, QTY_MAX, 0), tpTicks: int(o.tpTicks, 0, QTY_MAX, 0) };
}
const prefsText = (p) => JSON.stringify(parsePrefs(JSON.stringify(p)));

/* ---- names ---- */
/* "…047": the last 3 characters of an account's label (or id). */
function short(a) { const s = String((a && (a.label || a.id)) || ''); return s.length > 3 ? '…' + s.slice(-3) : s; }
/* NQZ6 -> NQ · MNQH27 -> MNQ · NQ -> NQ: a month code + 1-2 digit year stripped. */
function rootOf(symbol) {
  const s = String(symbol || '').toUpperCase(), m = /^([A-Z0-9]+?)[FGHJKMNQUVXZ]\d{1,2}$/.exec(s);
  return m ? m[1] : s;
}
function botName(key) { return BOT_NAMES[key] || key; }
function etTime(ms) { return Number.isFinite(ms) ? ET.format(new Date(ms)) : '—'; }
function px(v) { return v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 }); }

/* ---- orders ---- */
/* A Limit's price, a Stop's (StopLimit's) trigger. */
function orderPrice(o) {
  if (/stop/i.test(String(o.type || ''))) return o.stop_price ?? o.price ?? null;
  return o.price ?? o.stop_price ?? null;
}
const ABBR = { Limit: 'LMT', Stop: 'STP', StopLimit: 'STP LMT', Market: 'MKT', TrailingStop: 'TRAIL' };
const abbr = (t) => ABBR[t] || String(t || '').toUpperCase();

/* The clicked (or dragged-to) price's marketability: a buy AT OR ABOVE the ask is a Stop (marketable), strictly
   below it a Limit (passive); a sell AT OR BELOW the bid is a Stop, strictly above it a Limit. No ask/bid: the
   last trade; no quote at all: null (no order items). The touch itself counts as marketable (>= / <=,
   re-review Minor 1): a TP dragged exactly onto the price is refused the same as one dragged through it, since
   a limit order resting right at the touch fills essentially immediately. */
function inferType(side, price, q) {
  if (!q || price == null) return null;
  if (side === 'Buy') { const a = q.ask ?? q.last; return a == null ? null : price >= a ? 'Stop' : 'Limit'; }
  const b = q.bid ?? q.last;
  return b == null ? null : price <= b ? 'Stop' : 'Limit';
}
function menuText(side, qty, price, type, tick) { return `${side} ${qty} @ ${Cat.fmtPrice(price, tick)} ${type}`; }
function roundTick(p, tick) { return tick > 0 ? Number((Math.round(p / tick) * tick).toFixed(Cat.decimals(tick))) : p; }

/* SL/TP from the tick defaults (0 = off) around ref: the order's price, or the last trade for a Market order. */
function bracket(side, ref, prefs, tick) {
  if (ref == null || !(tick > 0)) return { sl: null, tp: null };
  const s = side === 'Buy' ? 1 : -1;
  return { sl: prefs.slTicks > 0 ? roundTick(ref - s * prefs.slTicks * tick, tick) : null,
    tp: prefs.tpTicks > 0 ? roundTick(ref + s * prefs.tpTicks * tick, tick) : null };
}
/* A Stop Limit's `price` is its limit and `trigger` its trigger (sent only with a Stop Limit). `tif` (Day | GTC) is
   sent only when given: the desk defaults to Day. */
function orderBody({ clientId, accounts, root, side, qty, type, price = null, sl = null, tp = null, trigger = null, tif = null }) {
  const b = { client_id: clientId, accounts: [...accounts], root, side, qty, type };
  if (type !== 'Market') b.price = price;
  if (type === 'StopLimit') b.trigger_price = trigger;
  if (sl != null) b.sl_price = sl;
  if (tp != null) b.tp_price = tp;
  if (tif != null) b.tif = tif;
  return b;
}
let seq = 0;
/* One per user action (the desk de-duplicates on it: a retry of the same action reuses it). */
function clientId(now = Date.now()) { seq = (seq + 1) % 1e6; return `c${now.toString(36)}-${seq.toString(36)}-${Math.random().toString(36).slice(2, 8)}`; }

/* ---- per-chart trading (2026-09-27 plan, Task 2) ----
   Each chart's cell config carries `trade: {on, accounts}` (default off, no accounts) and `algo` (a desk strategy
   key, or null). Every order-sending path takes its accounts from the chart it was started from. */
/* The cell config's trade, sanitised: `on` only for a real true; accounts per idList. Always a fresh object. */
function cellTrade(raw) {
  const o = isObj(raw) ? raw : {};
  return { on: o.on === true, accounts: idList(o.accounts) };
}
/* A layout (or template, or last-session) load: the accounts come back, Trading NEVER does. */
function loadedTrade(raw) { return { on: false, accounts: cellTrade(raw).accounts }; }
/* The cell's algo: a desk strategy key (1-64 characters), or null. */
function cellAlgo(raw) { return typeof raw === 'string' && raw.length >= 1 && raw.length <= 64 ? raw : null; }
/* What a layout / template save writes for a chart: its account list and its algo -- never `on`. */
function tradeBits(cfg) {
  const c = isObj(cfg) ? cfg : {};
  return { trade: { accounts: cellTrade(c.trade).accounts }, algo: cellAlgo(c.algo) };
}
/* A stored template's trade / algo, as a load: only the keys the template has; trade forced off. */
function templateTrade(tpl) {
  const t = isObj(tpl) ? tpl : {}, out = {};
  if ('trade' in t) out.trade = loadedTrade(t.trade);
  if ('algo' in t) out.algo = cellAlgo(t.algo);
  return out;
}
/* A chart moved to `root` (or a template's algo applied to it): the algo is cleared only when the desk CONFIRMS it
   trades another symbol. One the desk can't speak to (no state yet, not listed, no symbol) is kept -- fix round 1:
   a desk that hasn't answered must not silently drop a chart's algo from the next layout save. */
function algoForRoot(algo, root, strategies) {
  const a = cellAlgo(algo);
  if (!a) return null;
  const s = isObj(strategies) ? strategies[a] : null;
  if (!isObj(s) || typeof s.symbol !== 'string' || !s.symbol) return a;
  return rootOf(s.symbol) === root ? a : null;
}
/* Charts kept in the layout beyond the visible grid (a smaller grid): Trading switched off, accounts kept, so a chart
   that reappears when the grid grows again never comes back already trading (fix round 1). Mutates `cells`. */
function hiddenCellsOff(cells, n) {
  if (!Array.isArray(cells)) return;
  for (let i = Math.max(0, n); i < cells.length; i++) if (isObj(cells[i])) cells[i].trade = loadedTrade(cells[i].trade);
}
/* The one-time move of the old global ticked list: onto the SELECTED chart only, and only when that chart has no
   trade config of its own yet (an old layout's cell, or a fresh one). Trading stays off. null: nothing to move. */
function migrateTicked(rawCell, ticked) {
  if (isObj(rawCell) && 'trade' in rawCell) return null;
  const accounts = idList(ticked);
  return accounts.length ? { on: false, accounts } : null;
}

/* ---- what the page may do (ruling S7), per chart ---- */
/* The desk-level half: down, or chart trading switched off on the desk; null when the desk is up and on. */
function deskGate(desk) {
  if (!desk || !desk.state) return { mode: 'down', reason: (desk && desk.down) || 'connecting to the desk', accounts: [] };
  if (!desk.state.enabled) return { mode: 'off', reason: 'Chart trading is off on the desk', accounts: [] };
  return null;
}
/* One chart's mode from its trade config: its switch, then its accounts, then the desk's rules. `accounts` is
   only ever a subset of THIS chart's accounts (the tradable ones). */
function tradeMode(desk, ct) {
  const t = cellTrade(ct);
  if (!t.on) return { mode: 'off', reason: 'Trading is off on this chart', accounts: [] };
  if (!t.accounts.length) return { mode: 'none', reason: 'Pick accounts for this chart in the Trade menu', accounts: [] };
  const gate = deskGate(desk);
  if (gate) return gate;
  const ticked = new Set(t.accounts);
  const accounts = accountsOf(desk.state).filter((a) => ticked.has(a.id) && a.tradable).map((a) => a.id);
  if (!accounts.length) return { mode: 'none', reason: 'No ticked account can trade right now', accounts };
  return { mode: 'on', reason: '', accounts };
}

/* ---- safety review (2026-09-27 review of Task 5, and its follow-up review of Tasks 5+6) ---- */
/* Enter in the confirm dialog: confirms only when focus is on the primary button, or on a non-button element
   (the checkbox, an unfocusable row) -- never on ×, Cancel, or any other button, and never a held key
   (`repeat`: I3 -- a key auto-repeating from picking a menu item by keyboard must not also confirm the dialog
   it just opened). `target`/`primary` need only `tagName` (any real DOM element qualifies). */
function enterConfirms(target, primary, repeat) {
  if (repeat) return false;
  if (!target) return false;
  if (target === primary) return true;
  return target.tagName !== 'BUTTON';
}

/* A quote older than maxAgeMs (default 10 s) counts as no quote for DISPLAY and for which chart-menu Buy/Sell
   items exist (M4). Ruling (2026-09-27 re-review): `ts_ms` is the last TRADE time, so a quiet market goes
   "stale" by this measure often -- fine for greying the block or hiding a menu item, but too eager to also
   gate a REFUSAL check. A refusal (can this Limit/Stop/bracket actually be trusted not to fill at once) always
   uses the last known quote at ANY age instead (see refuseIfMarketable); only "no quote ever" refuses there. */
function freshQuote(q, nowMs, maxAgeMs = 10000) {
  if (!q || !Number.isFinite(q.ts_ms) || !Number.isFinite(nowMs)) return null;
  return nowMs - q.ts_ms <= maxAgeMs ? q : null;
}

/* N1: a Market order whose prefs would attach a bracket (a nonzero SL or TP tick default) needs a quote to
   compute it from -- without one, sending anyway would place a naked market order the user never asked for. */
function needsQuoteForBracket(type, slTicks, tpTicks) {
  return type === 'Market' && (slTicks > 0 || tpTicks > 0);
}

/* N2/I1: whether a re-priced or new Limit/Stop order should be refused for having drifted (or landed) on the
   wrong side of the market, using the LAST KNOWN quote at any age -- freshness only gates display and menu
   items (see freshQuote), never this check. No quote at all is refused outright, since "no quote" means "can't
   verify," not "assume it's fine." Returns the toast text to show, or null when the send may proceed. */
function refuseIfMarketable(side, price, quote, expectedKind) {
  if (!quote) return "No price yet — can't check the move";
  const fresh = inferType(side, price, quote);
  if (fresh && fresh !== expectedKind) return 'Price moved through your level — re-check the order';
  return null;
}

/* A send must go only to the accounts the confirm dialog actually showed, intersected with the fresh
   effective set at send time -- never to an account the dialog never listed. `ok: false` (the fresh set would
   ADD an account beyond what was shown) means abort entirely; a fresh set that only shrank sends to the
   surviving intersection. */
function resolveConfirmedAccounts(shown, fresh) {
  const shownSet = new Set(shown), freshSet = new Set(fresh);
  if (fresh.some((id) => !shownSet.has(id))) return { ok: false, accounts: [] };
  return { ok: true, accounts: shown.filter((id) => freshSet.has(id)) };
}

/* Ticked accounts minus any LIVE account not armed this session (ruling S5's second click) -- shared by the
   Trade menu's effective mode and the chart's lines/markers, so a LIVE account never trades or draws until
   armed. `liveConfirmed` is a Set (or array) of account ids armed this session. No state at all (the desk
   hasn't loaded yet) passes `ticked` through unchanged, since there is nothing to check against; but once
   `state` exists, an id it does not recognize fails CLOSED (M6) -- dropped, never assumed armed. */
function armedTicked(state, ticked, liveConfirmed) {
  if (!state) return ticked;
  const confirmed = liveConfirmed instanceof Set ? liveConfirmed : new Set(liveConfirmed || []);
  const accounts = accountsOf(state);
  return ticked.filter((id) => {
    const a = accounts.find((x) => x.id === id);
    if (!a) return false;
    return a.env !== 'live' || confirmed.has(id);
  });
}
/* A chart's mode with this session's LIVE arms applied (armedTicked): an unarmed LIVE account drops out; with none
   left the chart cannot trade. A mode that is not 'on' passes through unchanged (the same object). */
function armedMode(m, state, liveConfirmed) {
  if (!m || m.mode !== 'on') return m;
  const accounts = armedTicked(state, m.accounts, liveConfirmed);
  if (accounts.length === m.accounts.length) return m;
  return accounts.length ? { mode: 'on', reason: '', accounts }
    : { mode: 'none', reason: 'Arm the LIVE account for this chart in the Trade menu', accounts: [] };
}
/* Whether every leg of a line belongs to `accounts` (a chart's effective accounts): the only lines a chart may
   move or close. An empty or missing line never qualifies. */
function legsWithin(line, accounts) {
  const ok = new Set(accounts || []);
  return !!line && Array.isArray(line.legs) && line.legs.length > 0 && line.legs.every((l) => ok.has(l.account));
}
/* The chart's accounts as legend chips, "…047 DEMO": `active` when the account is in `activeIds` (the ones an order
   from this chart would go to right now); an account the desk does not list has no env. */
function accountChips(state, accounts, activeIds) {
  const act = new Set(activeIds || []), list = accountsOf(state);
  return idList(accounts).map((id) => {
    const a = list.find((x) => x.id === id), live = !!a && a.env === 'live';
    return { id, who: short(a || { id }), env: a ? (live ? 'LIVE' : 'DEMO') : '', live, active: act.has(id) };
  });
}

/* A Trade-menu row's state for one chart: 'ticked', 'off', or 'unarmed' -- a LIVE account on the chart's list that
   is not armed this session (it came back with a layout): shown ticked-but-not-armed, and a click removes it. */
function acctTick(account, accounts, liveConfirmed) {
  const armed = liveConfirmed instanceof Set ? liveConfirmed : new Set(liveConfirmed || []);
  if (!account || !(accounts || []).includes(account.id)) return 'off';
  return account.env === 'live' && !armed.has(account.id) ? 'unarmed' : 'ticked';
}

/* The refusal toast for an unarmed LIVE account (per-account paths: flatten, cancel, drag, ×). */
function unarmedLiveMessage(account) {
  const label = (account && (account.label || account.id)) || 'account';
  return `Arm LIVE account ${label} in the Trade menu first`;
}

/* The Buy/Sell block's texts: bid / ask (the last trade when one side is missing), the spread in ticks, stale when
   the quote's trade is over 30 s old against nowMs (the replay clock in a replay). */
function quoteView(q, tick, nowMs) {
  if (!q || (q.bid == null && q.ask == null && q.last == null)) return { bid: '—', ask: '—', spread: '', stale: true, age: null };
  const bid = q.bid ?? q.last, ask = q.ask ?? q.last, age = Number.isFinite(q.ts_ms) ? nowMs - q.ts_ms : null;
  const n = tick > 0 && q.bid != null && q.ask != null ? Math.round((q.ask - q.bid) / tick) : null;
  return { bid: Cat.fmtPrice(bid, tick), ask: Cat.fmtPrice(ask, tick), spread: n == null ? '' : String(n),
    stale: age == null || age > QUOTE_STALE_MS, age };
}

/* ---- the order panel (2026-09-27 order-panel plan, Task 3) ---- */
const PANEL_TYPES = ['Market', 'Limit', 'Stop', 'StopLimit'];
const PANEL_QTY_MAX = 10;           // the panel's own cap per order (the desk's limits still decide)
const STOPLIMIT_MAX_TICKS = 100;    // the desk's: a Stop Limit's limit at most this far from its trigger
const num = (v) => (v == null || v === '' ? NaN : Number(v));
/* One exit (kind 'sl' | 'tp') of a side's order from `entry`, typed in `unit` ('usd' | 'ticks' | 'price'):
   {usd, ticks, price}. An SL sits below a Buy's entry (above a Sell's), a TP the other way. `ticks` is whole and
   >= 1, `price` tick-rounded, `usd` for the whole order's qty (null without a point value). Anything that can't make
   an exit (nothing typed, garbage, a price on the wrong side or AT the entry, no entry, a $ without a point value)
   -> null. `entry` is the order's price; a Market's last trade; a Stop Limit's trigger for its SL, limit for its TP. */
function exitTriple({ unit, value, side, entry, tick, pv = null, kind, qty = 1 }) {
  const v = num(value), e = num(entry);
  if (!Number.isFinite(v) || !Number.isFinite(e) || !(tick > 0) || !['Buy', 'Sell'].includes(side)) return null;
  const dir = (side === 'Buy') === (kind === 'tp') ? 1 : -1;   // + : above the entry
  const perTick = pv != null && Number.isFinite(pv) && pv > 0 && qty > 0 ? tick * pv * qty : null;
  let ticks;
  if (unit === 'ticks') ticks = Math.round(v);
  else if (unit === 'usd') {
    if (perTick == null || !(v > 0)) return null;
    ticks = Math.max(1, Math.round(v / perTick));
  } else if (unit === 'price') ticks = Math.round((dir * (roundTick(v, tick) - e)) / tick);
  else return null;
  if (!(ticks >= 1)) return null;
  const price = unit === 'price' ? roundTick(v, tick) : roundTick(e + dir * ticks * tick, tick);
  return { usd: perTick == null ? null : Number((ticks * perTick).toFixed(2)), ticks, price };
}
/* Contracts for a USD risk at an SL `slTicks` away: floored (never over the risk); 0 when under one contract. */
function qtyFromRisk(usd, slTicks, tick, pv) {
  const per = slTicks * tick * pv;
  if (!(usd > 0) || !(per > 0) || !Number.isFinite(per)) return 0;
  return Math.max(0, Math.floor(usd / per + 1e-9));
}
/* The exits' side against their references: an SL beyond slRef (a Stop Limit's trigger), a TP beyond tpRef (its
   limit; `stopLimit` names them so). The error text, or null. Also re-run at send time against the latest quote
   for a Market order. */
function exitSideError(side, slRef, tpRef, sl, tp, stopLimit = false) {
  const s = side === 'Buy' ? 1 : -1;
  if (sl != null && !(s * (slRef - sl) > 0)) {
    return `Stop loss must be ${s > 0 ? 'below' : 'above'} the ${stopLimit ? 'trigger' : 'entry'}`;
  }
  if (tp != null && !(s * (tp - tpRef) > 0)) {
    return `Take profit must be ${s > 0 ? 'above' : 'below'} the ${stopLimit ? 'limit' : 'entry'}`;
  }
  return null;
}
/* The panel's order, validated: {ok: false, error} or {ok: true, side, type, qty, price, trigger, sl, tp, tif} with
   every price tick-rounded, `price` null for a Market (a Stop Limit's limit otherwise), `trigger` only for a Stop
   Limit, `tif` null for a Market (Day only: none sent). `quote` is the last known one at ANY age (the side checks,
   like refuseIfMarketable); a Market with an exit needs it fresh (<= 10 s at nowMs, like needsQuoteForBracket).
   `risk` (USD) replaces `qty`: contracts = qtyFromRisk over the SL's distance (needs the SL and a point value). */
function panelOrder({ side, type, qty, price = null, trigger = null, sl = null, tp = null, tif = 'Day', risk = null,
  quote, nowMs, tick, pv = null, qtyMax = PANEL_QTY_MAX }) {
  const bad = (error) => ({ ok: false, error });
  if (side !== 'Buy' && side !== 'Sell') return bad('Pick Buy or Sell');
  if (!PANEL_TYPES.includes(type)) return bad('Pick an order type');
  if (!(tick > 0)) return bad('No tick size for this chart yet');
  const q = quote && (quote.bid != null || quote.ask != null || quote.last != null) ? quote : null;
  if (!q) return bad("No price yet — can't check the order");
  const buy = side === 'Buy', word = buy ? 'buy' : 'sell', rt = (v) => roundTick(v, tick);
  const px = type === 'Market' ? null : num(price), trig = type === 'StopLimit' ? num(trigger) : null;
  const slPx = sl == null ? null : num(sl), tpPx = tp == null ? null : num(tp);
  if (slPx != null && !Number.isFinite(slPx)) return bad('Enter the stop loss');
  if (tpPx != null && !Number.isFinite(tpPx)) return bad('Enter the take profit');
  let P = null, TR = null;
  if (type === 'Limit' || type === 'Stop') {
    if (!Number.isFinite(px)) return bad('Enter a price');
    P = rt(px);
    if (inferType(side, P, q) !== type) {
      return bad(type === 'Limit' ? `A ${word} limit must be ${buy ? 'below the ask' : 'above the bid'}`
        : `A ${word} stop must be ${buy ? 'above' : 'below'} the market`);
    }
    if (type === 'Stop' && q.last != null && !(buy ? P > q.last : P < q.last)) {
      return bad(`A ${word} stop must be ${buy ? 'above' : 'below'} the last price`);
    }
  } else if (type === 'StopLimit') {
    if (!Number.isFinite(trig)) return bad('Enter a trigger price');
    if (!Number.isFinite(px)) return bad('Enter a limit price');
    TR = rt(trig); P = rt(px);
    if (inferType(side, TR, q) !== 'Stop' || (q.last != null && !(buy ? TR > q.last : TR < q.last))) {
      return bad(`A ${word} stop limit's trigger must be ${buy ? 'above' : 'below'} the market`);
    }
    if (buy ? P < TR : P > TR) return bad(`A ${word} stop limit's limit must be at or ${buy ? 'above' : 'below'} its trigger`);
    if (Math.round(Math.abs(P - TR) / tick) > STOPLIMIT_MAX_TICKS) return bad(`The limit must be within ${STOPLIMIT_MAX_TICKS} ticks of the trigger`);
  }
  const S = slPx == null ? null : rt(slPx), TP = tpPx == null ? null : rt(tpPx);
  let slRef = P, tpRef = P;
  if (type === 'Market') {
    if ((S != null || TP != null || risk != null) && !freshQuote(q, nowMs)) return bad("No recent price — can't attach your stop/target");
    slRef = tpRef = q.last ?? null;
    if ((S != null || TP != null) && slRef == null) return bad("No last trade — can't attach your stop/target");
  } else if (type === 'StopLimit') slRef = TR;
  const side2 = exitSideError(side, slRef, tpRef, S, TP, type === 'StopLimit');
  if (side2) return bad(side2);
  let n = qty;
  if (risk != null) {
    if (S == null) return bad('USD risk needs a stop loss');
    if (!(pv > 0)) return bad('No point value for this chart yet');
    n = qtyFromRisk(num(risk), Math.round(Math.abs(slRef - S) / tick), tick, pv);
    if (n < 1) return bad(`$${num(risk) || 0} risk is under one contract at this stop`);
  }
  if (!Number.isInteger(n) || n < 1 || n > qtyMax) return bad(`Quantity must be 1–${qtyMax}${risk != null ? ` (this risk is ${n} contracts)` : ''}`);
  let T2 = null;
  if (type !== 'Market') {
    if (tif !== 'Day' && tif !== 'GTC') return bad('Time in force: Day or GTC');
    T2 = tif;
  }
  return { ok: true, side, type, qty: n, price: P, trigger: TR, sl: S, tp: TP, tif: T2 };
}
const TYPE_WORDS = { Market: 'MARKET', Limit: 'LIMIT', Stop: 'STOP', StopLimit: 'STOP LIMIT' };
/* The send button: "Buy 1 NQZ6 MARKET" (no number without a valid size). */
function sendLabel(side, qty, contract, type) {
  return [side, qty >= 1 ? String(qty) : null, contract, TYPE_WORDS[type] || String(type || '').toUpperCase()].filter(Boolean).join(' ');
}
/* The front-month contract for a root, for display: one the desk holds or works in it, else the chart history's
   latest session's, else the root itself. */
function contractOf(state, root, sessions) {
  for (const a of accountsOf(state)) {
    for (const x of [...(a.positions || []), ...(a.orders || [])]) if (x.symbol && rootOf(x.symbol) === root) return x.symbol;
  }
  const withC = (Array.isArray(sessions) ? sessions : []).filter((s) => s && s.contract && rootOf(s.contract) === root);
  if (withC.length) return withC.reduce((a, b) => (String(b.date) > String(a.date) ? b : a)).contract;
  return root;
}

/* ---- money ---- */
const sign =(v) => (v > 0 ? '+' : v < 0 ? MINUS : '');
/* "+$450" · "−$1,212.50" · "$0"; null when unknown. */
function usd(v) { return v == null || !Number.isFinite(v) ? null : sign(Math.round(v * 100)) + Pos.fmtUsd(v); }
/* Unsigned unless negative: "$50,000" · "−$3"; "—" when unknown. */
function money(v) { return v == null || !Number.isFinite(v) ? '—' : (Math.round(v * 100) < 0 ? MINUS : '') + Pos.fmtUsd(v); }
/* qty contracts from `from` to `to`, s = 1 long / −1 short; null without a point value or a price. */
function pnl(from, to, s, qty, pv) { return pv == null || from == null || to == null ? null : (to - from) * s * qty * pv; }
function rrText(risk, reward) { return risk > 0 && reward > 0 ? `1:${Number((reward / risk).toFixed(2))}` : null; }

/* ---- lines (ruling S8) ---- */
/* Positions (merged by side + average price), SL/TP legs (an order opposite to the account's position in that
   contract: a stop type is SL, a limit is TP) and plain working orders, merged by kind + side + type + price, for
   EVERY account in `root` (Task 2: a chart never loses sight of a position). `editable` (an array or Set: the
   chart's effective accounts, empty when its Trading is off) marks which lines may be dragged / closed; an editable
   line and a view-only one are never merged together, so an action on a line can only reach editable accounts.
   A bot's own orders (owner set) are drawn by the bot overlay instead. */
function linesFor(state, root, editable) {
  if (!state) return [];
  const mine = new Set(editable || []), groups = new Map();
  const add = (key, base, leg) => {
    let g = groups.get(key);
    if (!g) { g = { key, ...base, qty: 0, legs: [] }; groups.set(key, g); }
    g.qty += leg.qty;
    g.legs.push(leg);
  };
  for (const a of accountsOf(state)) {
    const ed = mine.has(a.id), pre = ed ? 'e' : 'v';
    const who = short(a), pos = (a.positions || []).filter((p) => p.root === root && p.net);
    for (const p of pos) {
      const s = p.net > 0 ? 1 : -1;
      add(`${pre}|position|${s}|${p.avg_price}`, { kind: 'position', side: s > 0 ? 'Buy' : 'Sell', price: p.avg_price, editable: ed },
        { account: a.id, who, qty: Math.abs(p.net), avg: p.avg_price, s, pv: p.point_value ?? null, symbol: p.symbol });
    }
    for (const o of a.orders || []) {
      const at = orderPrice(o);
      if (o.owner || at == null || rootOf(o.symbol) !== root) continue;
      const p = pos.find((x) => x.symbol === o.symbol);
      const exit = !!p && ((p.net > 0 && o.side === 'Sell') || (p.net < 0 && o.side === 'Buy'));
      const kind = !exit ? 'order' : /stop/i.test(o.type) ? 'sl' : /limit/i.test(o.type) ? 'tp' : 'order';
      const limit = o.type === 'StopLimit' ? o.price ?? null : undefined;   // drawn at the trigger, labelled with both
      add(`${pre}|${kind}|${o.side}|${o.type}|${at}${limit !== undefined ? `|${limit}` : ''}`,
        { kind, side: o.side, type: o.type, price: at, editable: ed, ...(limit !== undefined ? { limit } : {}) },
        { account: a.id, who, qty: Number(o.qty) || 0, order_id: String(o.order_id),
          avg: p ? p.avg_price : null, s: p ? (p.net > 0 ? 1 : -1) : 0, pv: p ? p.point_value ?? null : null });
    }
  }
  return [...groups.values()];
}
/* A position's open P&L at the last trade; an SL/TP's P&L if it fills at its price; null for plain orders or
   when a point value / price is unknown. */
function linePnl(g, last) {
  if (g.kind === 'order') return null;
  let sum = 0;
  for (const l of g.legs) {
    const v = pnl(l.avg, g.kind === 'position' ? last : g.price, l.s, l.qty, l.pv);
    if (v == null) return null;
    sum += v;
  }
  return sum;
}
function whoText(g) { const w = [...new Set(g.legs.map((l) => l.who))]; return w.length === 1 ? w[0] : `${w.length} accts`; }
function lineLabel(g) {
  if (g.kind === 'position') return `${g.side === 'Buy' ? 'LONG' : 'SHORT'} ${g.qty}`;
  if (g.kind === 'sl' || g.kind === 'tp') return `${g.kind.toUpperCase()} ${g.qty}`;
  if (g.type === 'StopLimit') return `${g.side.toUpperCase()} STP LMT ${px(g.limit)} (trig ${px(g.price)}) ${g.qty}`;
  return `${g.side.toUpperCase()} ${abbr(g.type)} ${g.qty}`;
}
/* Positions never drag (ruling S11); a Stop Limit can't be moved (the desk refuses it): cancel and place again. */
function canDrag(g) { return g.kind !== 'position' && g.type !== 'StopLimit'; }
function lineText(g, last) {
  const view = g.editable === false ? 'view only' : null;
  if (g.kind === 'order') return [lineLabel(g), whoText(g), view].filter(Boolean).join(' · ');
  return [lineLabel(g), usd(linePnl(g, last)), whoText(g), view].filter(Boolean).join(' · ');
}
function lineColor(g, P) {
  if (g.kind === 'position') return g.side === 'Buy' ? P.up : P.down;
  if (g.kind === 'sl') return P.down;
  if (g.kind === 'tp') return P.up;
  return g.side === 'Buy' ? P.accent : P.down;
}
const withPrice = (g, price) => ({ ...g, price });

/* ---- confirm dialog ---- */
const TYPE_NAMES = { StopLimit: 'Stop Limit' };
const GTC_WARN = "GTC stays working overnight — if it's still working at 09:28 the 9:30 bot skips this account";
function orderTitle(b, tick) {
  const what = b.type === 'Market' ? 'at market' : `${TYPE_NAMES[b.type] || b.type} @ ${Cat.fmtPrice(b.price, tick)}`;
  const trig = b.type === 'StopLimit' ? ` (trigger ${Cat.fmtPrice(b.trigger_price, tick)})` : '';
  return `${b.side} ${b.qty} ${b.root} ${what}${trig}${b.tif ? ` · ${b.tif}` : ''}`;
}
function confirmOrder(b, state, quote, pv, tick) {
  const accts = accountsOf(state).filter((a) => b.accounts.includes(a.id));
  const ref = b.type === 'Market' ? (quote ? quote.last ?? null : null) : b.price, s = b.side === 'Buy' ? 1 : -1;
  const risk = b.sl_price != null ? pnl(ref, b.sl_price, s, b.qty, pv) : null;
  const reward = b.tp_price != null ? pnl(ref, b.tp_price, s, b.qty, pv) : null;
  const bits = [];
  // a Stop Limit's risk is measured from its limit: the worst fill (it may fill better, at the trigger)
  const riskLabel = b.type === 'StopLimit' ? 'risk (worst fill) ' : '';
  if (b.sl_price != null) bits.push(`SL ${Cat.fmtPrice(b.sl_price, tick)}${risk != null ? ` ${riskLabel}${usd(risk)}` : ''}`);
  if (b.tp_price != null) bits.push(`TP ${Cat.fmtPrice(b.tp_price, tick)}${reward != null ? ` ${usd(reward)}` : ''}`);
  const rr = ref != null && b.sl_price != null && b.tp_price != null ? rrText(Math.abs(ref - b.sl_price), Math.abs(b.tp_price - ref)) : null;
  if (rr) bits.push(`RR ${rr}`);
  return { title: orderTitle(b, tick), accounts: accts.map((a) => ({ id: a.id, label: a.label, env: a.env })),
    bracket: bits.join(' · '), each: accts.length > 1 ? `each of ${accts.length} accounts` : '', live: accts.some((a) => a.env === 'live'),
    warn: b.tif === 'GTC' ? GTC_WARN : '' };
}
function actionTitle(kind, { root, line, from, to }, tick) {
  switch (kind) {
    case 'flatten': return line ? `Flatten ${root} · ${whoText(line)}` : `Flatten ${root}`;
    case 'cancel-symbol': return `Cancel all ${root} orders`;
    case 'reverse': return `Reverse ${root}`;
    case 'cancel': return `Cancel ${lineLabel(line)} @ ${Cat.fmtPrice(line.price, tick)} · ${whoText(line)}`;
    case 'modify': return `Move ${lineLabel(line)} ${Cat.fmtPrice(from, tick)} → ${Cat.fmtPrice(to, tick)}`;
    default: return kind;
  }
}

/* ---- toasts (ruling S3) ---- */
const VERB = { order: 'order accepted', modify: 'order moved', cancel: 'order cancelled', 'cancel-symbol': 'orders cancelled',
  flatten: 'flattened', reverse: 'reversed' };
function resultToasts(action, status, data, state) {
  const label = (id) => { const a = accountsOf(state).find((x) => x.id === id); return a ? short(a) : id; };
  if (!data || typeof data !== 'object' || !data.results) {
    const d = data && (data.detail ?? data.error);
    return [{ tone: 'err', text: typeof d === 'string' && d ? d : `desk error (HTTP ${status})` }];
  }
  return Object.entries(data.results).map(([id, r]) => (r && r.ok
    ? { tone: 'ok', text: `${label(id)} · ${VERB[action] || 'done'}` }
    : { tone: 'err', text: `${label(id)} · ${(r && r.error) || 'refused'}` }));
}
function fillText(ev, state, tick) {
  const f = ev.fill, a = accountsOf(state).find((x) => x.id === ev.account);
  return `Filled ${f.qty} @ ${Cat.fmtPrice(f.price, tick || 0.01)} · ${a ? short(a) : ev.account}`;
}

/* ---- markers ({ms, …} for HBDrawings.placeMarkers) ---- */
/* `ids`: the chart's accounts (LIVE ones only once armed). */
function fillMarkers(state, root, ids, P) {
  const ticked = new Set(ids || []), out = [];
  for (const a of accountsOf(state)) {
    if (!ticked.has(a.id)) continue;
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      if (f.owner || rootOf(f.symbol) !== root || !Number.isFinite(ms)) continue;
      const buy = f.side === 'Buy';
      out.push({ id: `f${a.id}:${f.id}`, ms, price: f.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
        shape: buy ? 'arrowUp' : 'arrowDown', color: buy ? P.accent : P.down, text: '' });
    }
  }
  return out;
}

/* ---- live strategies (ruling S12) ---- */
const fmt1 = (v) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(1));
function botStatus(s) {
  const t = s.timer || {}, accts = Object.values(s.accounts || {});
  let st;
  if (!s.enabled) st = 'off';
  else if (s.day_status === 'done') {
    const known = accts.filter((a) => a.pnl != null);
    st = known.length ? `done ${usd(known.reduce((x, a) => x + a.pnl, 0))}` : 'done';
  } else if (s.day_status && s.day_status !== 'idle') st = s.day_status;
  else st = t.stage || 'idle';
  return s.shadow ? `${st} · shadow` : st;
}
function botBadge(key, s) {
  const t = s.timer || {};
  const gate = t.gate === true ? `TREND ADX ${fmt1(t.adx)}` : t.gate === false ? `CHOP ADX ${fmt1(t.adx)}` : null;
  const tone = s.day_status === 'error' || t.stage === 'error' ? 'err'
    : ['placing', 'placed', 'live'].includes(s.day_status) ? 'live' : 'idle';
  return { text: [botName(key), s.enabled ? gate : null, botStatus(s)].filter(Boolean).join(' · '), tone };
}
function botLines(key, s, tick) {
  const pre = s.kind === 'straddle' ? '9:30' : botName(key), m = new Map();
  const put = (kind, price, label, qty) => {
    if (price == null) return;
    const id = `${kind}|${price}`, g = m.get(id) || { key: `bot|${key}|${id}`, kind, price, label, qty: 0 };
    g.qty += Number(qty) || 0;
    m.set(id, g);
  };
  for (const a of Object.values(s.accounts || {})) {
    if (a.status === 'placing' || a.status === 'placed') { put('entry', a.upper, 'BUY STOP', a.qty); put('entry', a.lower, 'SELL STOP', a.qty); }
    if (a.status === 'live') { put('sl', a.sl, 'SL', a.entry_qty ?? a.qty); put('tp', a.tp, 'TP', a.entry_qty ?? a.qty); }
  }
  return [...m.values()].map((g) => ({ ...g, text: `${pre} ${g.label} ${g.qty} @ ${Cat.fmtPrice(g.price, tick)}` }));
}
function botMarkers(key, s, state, P) {
  const out = [];
  for (const a of accountsOf(state)) {
    const st = (s.accounts || {})[a.id];
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      if (f.owner !== key || !Number.isFinite(ms)) continue;
      const entry = !st || !st.entry_side || f.side === st.entry_side, buy = f.side === 'Buy';
      out.push({ id: `b${a.id}:${f.id}`, ms, price: f.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
        shape: buy ? 'arrowUp' : 'arrowDown', color: P.warn, text: entry ? '' : (st && st.pnl != null ? usd(st.pnl) : '') });
    }
  }
  return out;
}
function botsFor(state, root, tick, P) {
  const strats = (state && state.bot && state.bot.strategies) || {};
  return Object.entries(strats).filter(([, s]) => rootOf(s.symbol) === root)
    .map(([key, s]) => ({ key, badge: botBadge(key, s), lines: s.enabled ? botLines(key, s, tick) : [], markers: botMarkers(key, s, state, P) }));
}

/* ---- the bottom panel's rows (every account: ruling S6) ---- */
function openPnl(p, quotes) { const q = quotes[p.root]; return pnl(p.avg_price, q ? q.last : null, p.net > 0 ? 1 : -1, Math.abs(p.net), p.point_value ?? null); }
const tone = (v) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
function positionRows(state, quotes) {
  const out = [];
  for (const a of accountsOf(state)) {
    for (const p of a.positions || []) {
      if (!p.net) continue;
      const v = openPnl(p, quotes), q = quotes[p.root];
      out.push({ key: `${a.id}:${p.symbol}`, account: a.id, who: a.label, env: a.env, symbol: p.symbol, root: p.root,
        side: p.net > 0 ? 'Long' : 'Short', qty: Math.abs(p.net), avg: px(p.avg_price), last: px(q ? q.last : null),
        pnl: usd(v) ?? '—', tone: tone(v) });
    }
  }
  return out;
}
function orderRows(state) {
  const out = [];
  for (const a of accountsOf(state)) {
    for (const o of a.orders || []) {
      out.push({ key: `${a.id}:${o.order_id}`, account: a.id, who: a.label, symbol: o.symbol, side: o.side, type: o.type,
        qty: Number(o.qty) || 0, price: px(orderPrice(o)), status: o.status || '', owner: o.owner ? botName(o.owner) : '',
        order_id: String(o.order_id), cancellable: !o.owner });
    }
  }
  return out;
}
function fillRows(state) {
  const out = [];
  for (const a of accountsOf(state)) {
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      out.push({ key: `${a.id}:${f.id}`, ms, time: etTime(ms), who: a.label, symbol: f.symbol, side: f.side, qty: f.qty,
        price: px(f.price), owner: f.owner ? botName(f.owner) : '' });
    }
  }
  return out.sort((x, y) => (y.ms || 0) - (x.ms || 0));
}

/* ---- keyed-row diffing (panel.js): across a rebuild, which of the previously-rendered row keys should be added
   or removed, so a row whose key is unchanged keeps its own DOM node (its button, its focus) even while its
   other cells update in place. Pure: prevKeys is the caller's own list of what it rendered last (any order);
   rows is the fresh list, in the order they should render; keyOf reads a row's key. */
function diffRows(prevKeys, rows, keyOf) {
  const keys = rows.map(keyOf), prevSet = new Set(prevKeys), nextSet = new Set(keys);
  return { keys, add: keys.filter((k) => !prevSet.has(k)), remove: prevKeys.filter((k) => !nextSet.has(k)) };
}
function accountRows(state, quotes) {
  return accountsOf(state).map((a) => {
    const opens = (a.positions || []).filter((p) => p.net).map((p) => openPnl(p, quotes));
    const open = opens.some((v) => v == null) ? null : opens.reduce((x, v) => x + v, 0);
    return { id: a.id, who: a.label, env: a.env, connected: !!a.connected, broker: a.broker_account || '—',
      balance: money(a.balance), realized: money(a.realized_pnl), open: opens.length ? (usd(open) ?? '—') : '$0',
      openTone: tone(open), strategies: [...new Set((a.strategies || []).map(botName))].join(', '),
      status: a.tradable ? 'Ready' : (a.error || (a.connected ? 'Not tradable' : 'Disconnected')) };
  });
}

const api = { PREFS_KEY, QUOTE_STALE_MS, BOT_NAMES, parsePrefs, prefsText, short, rootOf, orderPrice, abbr, inferType, menuText,
  roundTick, bracket, orderBody, clientId, tradeMode, quoteView, usd, money, pnl, rrText, linesFor, linePnl, lineLabel,
  lineText, lineColor, canDrag, withPrice, orderTitle, confirmOrder, actionTitle, resultToasts, fillText, fillMarkers, botName,
  botsFor, positionRows, orderRows, fillRows, accountRows, etTime, diffRows,
  enterConfirms, resolveConfirmedAccounts, armedTicked, unarmedLiveMessage, freshQuote,
  needsQuoteForBracket, refuseIfMarketable, cellTrade, loadedTrade, cellAlgo, tradeBits, templateTrade, algoForRoot,
  migrateTicked, deskGate, armedMode, legsWithin, accountChips, acctTick, hiddenCellsOff,
  PANEL_QTY_MAX, exitTriple, qtyFromRisk, exitSideError, panelOrder, sendLabel, contractOf };
if (typeof window !== 'undefined') window.HBTrade = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
