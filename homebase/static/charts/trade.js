/* Homebase Charts — trading from the chart, the pure half:
     - the viewer's trade preferences;
     - what the page may do right now;
     - Limit or Stop for a clicked price;
     - order bodies and client ids;
     - the position / order / bracket lines with their labels and dollars;
     - the confirm dialog's texts and the toasts;
     - the execution markers;
     - a chart's algo: its badge, BOT lines, markers, past runs and Kill;
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
   It is still parsed only so the page can migrate an old list onto one chart once (migrateTicked), then clear it.
   One-click is TWO switches (⚙ → Trading, ONE-CLICK TRADING; 2026-09-27): `oneClickChart` (the chart's Sell/qty/Buy
   block) and `oneClickPanel` (the order panel's Send), both default ON (the old single `oneClick` value is not carried
   over: it was stored OFF for nearly everyone, and the user wants these ON). `oneClick` itself stays the switch of every other
   path (a line's drag / ×, a position chip's exit drag, the chart menu, the bottom panel): the confirm's "Don't ask again".
   The SL/TP tick defaults are retired (no editor any more): always 0, whatever an old stored pref holds, so nothing
   invisible can attach a bracket. `qty` is the chart block's quantity box. */
function parsePrefs(text) {
  let o = null;
  try { o = JSON.parse(text); } catch (_) { o = null; }
  if (!isObj(o)) o = {};
  const ticked = idList(o.ticked);
  const sw = (v) => (typeof v === 'boolean' ? v : true);   // ON until the user turns it off (the old single pref is not migrated)
  return { ticked, oneClick: o.oneClick === true, oneClickChart: sw(o.oneClickChart), oneClickPanel: sw(o.oneClickPanel),
    qty: int(o.qty, 1, QTY_MAX, 1), slTicks: 0, tpTicks: 0 };
}
/* Which one-click switch a send surface reads: the chart block's, the order panel's, or (anything else) `oneClick`. */
const ONE_CLICK_KEYS = { chart: 'oneClickChart', panel: 'oneClickPanel' };
function oneClickKey(surface) { return ONE_CLICK_KEYS[surface] || 'oneClick'; }
const prefsText = (p) => JSON.stringify(parsePrefs(JSON.stringify(p)));

/* ---- names ---- */
/* "…047": the last 3 characters of an account's label (or id) -- except the PAPER account, whose short name is
   its label verbatim ("PAPER", never "…PER"): it is one virtual account, not one of a broker's numbered ones. */
const PAPER_SHORT_MAX = 14;   // Task 2b fix round 1 (M6): a user-given paper name is trimmed in chips / lines / toasts
function short(a) {
  const s = String((a && (a.label || a.id)) || '');
  if (a && a.env === 'paper') return s.length > PAPER_SHORT_MAX ? s.slice(0, PAPER_SHORT_MAX - 1) + '…' : s;
  return s.length > 3 ? '…' + s.slice(-3) : s;
}
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
/* A row the broker (or the paper book) says is not plainly Working: a pending entry's Suspended OSO leg, a
   PendingNew / PendingReplace. A row with no status at all is read as Working (older fixtures; the desk itself
   refuses exits on anything that is not exactly "Working"). */
function isPending(o) { return !!o && o.status != null && o.status !== 'Working'; }
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

/* ---- per-chart trading (2026-09-27 accounts-per-chart plan, Task 1) ----
   Each chart's cell config carries `trade: {accounts}` and `algo` (a desk strategy key, or null). The ACCOUNTS
   are the switch: a non-empty list means the chart is trade-ready, an empty one places no new entries (its
   lines stay manageable: lineAccounts). The old
   `trade.on` flag is RETIRED -- it is not read, not written, and an old layout's stored `on` is ignored.
   Every entry path takes its accounts from the chart it was started from. */
/* The cell config's trade, sanitised: accounts per idList. Always a fresh object, never an `on` key. */
function cellTrade(raw) {
  const o = isObj(raw) ? raw : {};
  return { accounts: idList(o.accounts) };
}
/* Which of `accounts` the desk says are LIVE; [] while the desk has said nothing (nothing can trade then
   anyway: deskGate is 'down'). An id the desk does not list is NOT live by this measure -- it is kept, shown
   '?' and fails closed everywhere else. */
function liveIds(accounts, state) {
  if (!state) return [];
  const list = accountsOf(state);
  return idList(accounts).filter((id) => { const a = list.find((x) => x.id === id); return !!a && a.env === 'live'; });
}
/* The UNVERIFIED marks (fix round 1, Critical 1). A load can only drop LIVE ids the desk has already named; while
   it has said nothing, the ids a load keeps are marked unverified on that chart (cfg.unverified), and only
   those are ever dropped later, when the desk answers. An id the user ticked (and armed) in the Trading tab
   never carries a mark, so no desk event can take it away. An id the desk still does not list stays marked:
   it cannot trade anyway, and if it turns up LIVE later it still drops.
   verifyLoaded: the marked ids checked against `state` -- LIVE ones dropped, listed non-LIVE ones cleared,
   unlisted ones kept marked. No state: nothing is decided (marks pruned to the chart's accounts only). */
function verifyLoaded(accounts, unverified, state) {
  const acc = idList(accounts), un = idList(unverified).filter((id) => acc.includes(id));
  if (!state) return { accounts: acc, droppedLive: [], unverified: un };
  const list = accountsOf(state), live = new Set(liveIds(un, state));
  return { accounts: acc.filter((id) => !live.has(id)), droppedLive: [...live],
    unverified: un.filter((id) => !list.some((x) => x.id === id)) };
}
/* A layout (or template, or last-session) load: DEMO and PAPER accounts come back, every LIVE one is DROPPED
   (Global Constraints: a live account must be re-ticked and re-armed in the session). Every kept id starts
   unverified, so `droppedLive` is what the desk could already name, and `unverified` what is left to check. */
function loadedTrade(raw, state = null) {
  const accounts = cellTrade(raw).accounts;
  return verifyLoaded(accounts, accounts, state);
}
/* Every chart config in the layout (visible and beyond the grid) through verifyLoaded, in place: the desk just
   answered. Returns the LIVE ids it dropped (the caller toasts once, only when there are any) and the indexes it
   changed (the caller repaints those charts). A chart whose marks are all cleared costs nothing next time, so a
   stream of account events drops nothing twice. */
function verifyCells(cfgs, state) {
  const out = { dropped: [], changed: [] };
  if (!Array.isArray(cfgs) || !state) return out;
  cfgs.forEach((c, i) => {
    if (!isObj(c) || !idList(c.unverified).length) return;
    const before = idList(c.unverified), v = verifyLoaded(cellTrade(c.trade).accounts, c.unverified, state);
    c.trade = { accounts: v.accounts };
    c.unverified = v.unverified;
    out.dropped.push(...v.droppedLive);
    // a chart whose marks changed at all can trade differently now (a verified DEMO id becomes usable)
    if (v.droppedLive.length || JSON.stringify(before) !== JSON.stringify(v.unverified)) out.changed.push(i);
  });
  out.dropped = [...new Set(out.dropped)];
  return out;
}
/* A chart's marks after its accounts change: a subset of `accounts`, plus `add` (a restore re-adding an id),
   minus `remove` (an id the user just ticked or unticked themselves). */
function nextUnverified(prev, accounts, { add = [], remove = [] } = {}) {
  const acc = idList(accounts), rm = new Set(remove);
  return idList([...idList(prev), ...idList(add)]).filter((id) => acc.includes(id) && !rm.has(id));
}
const CHECKING_ACCOUNTS = "Checking this chart's accounts with the desk…";
/* Minor 4: a chart's mode never includes an unverified id, so the frame between the desk's answer and
   verifyCells running can send nothing to one. A mode that is not 'on' passes through unchanged. */
function unverifiedMode(m, unverified) {
  const un = new Set(idList(unverified));
  if (!m || m.mode !== 'on' || !un.size) return m;
  const accounts = m.accounts.filter((id) => !un.has(id));
  if (accounts.length === m.accounts.length) return m;
  return accounts.length ? { mode: 'on', reason: '', accounts } : { mode: 'none', reason: CHECKING_ACCOUNTS, accounts: [] };
}
/* The one plain line a load shows when it dropped LIVE accounts; '' when it dropped none. */
function liveDroppedMessage(ids, state) {
  const list = idList(ids);
  if (!list.length) return '';
  const who = list.map((id) => { const a = accountsOf(state).find((x) => x.id === id); return (a && a.label) || id; });
  return list.length === 1
    ? `LIVE account ${who[0]} was not restored — tick and arm it again`
    : `LIVE accounts ${who.join(', ')} were not restored — tick and arm them again`;
}
/* The cell's algo: a desk strategy key (1-64 characters), or null. */
function cellAlgo(raw) { return typeof raw === 'string' && raw.length >= 1 && raw.length <= 64 ? raw : null; }
/* What a layout / template save writes for a chart: its account list and its algo -- never `on`. */
function tradeBits(cfg) {
  const c = isObj(cfg) ? cfg : {};
  return { trade: { accounts: cellTrade(c.trade).accounts }, algo: cellAlgo(c.algo) };
}
/* A stored template's trade / algo, as a load: only the keys the template has; LIVE accounts dropped (and
   reported in `droppedLive`, always present) exactly like a layout load. */
function templateTrade(tpl, state = null) {
  const t = isObj(tpl) ? tpl : {}, out = { droppedLive: [], unverified: [] };
  if ('trade' in t) {
    const l = loadedTrade(t.trade, state);
    out.trade = { accounts: l.accounts }; out.droppedLive = l.droppedLive; out.unverified = l.unverified;
  }
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
/* Charts kept in the layout beyond the visible grid (a smaller grid) are re-read exactly like a load: DEMO and
   PAPER accounts kept, every LIVE one dropped, so a chart that reappears when the grid grows again can never
   come back trading LIVE unarmed. Mutates `cells`; returns every LIVE id it dropped. */
function hiddenCellsLoaded(cells, n, state = null) {
  const dropped = [];
  if (!Array.isArray(cells)) return dropped;
  for (let i = Math.max(0, n); i < cells.length; i++) {
    if (!isObj(cells[i])) continue;
    const l = loadedTrade(cells[i].trade, state);
    cells[i].trade = { accounts: l.accounts };
    cells[i].unverified = l.unverified;
    dropped.push(...l.droppedLive);
  }
  return [...new Set(dropped)];
}
/* The one-time move of the old global ticked list: onto the SELECTED chart only, and only when that chart has no
   trade config of its own yet (an old layout's cell, or a fresh one). null: nothing to move. */
function migrateTicked(rawCell, ticked) {
  if (isObj(rawCell) && 'trade' in rawCell) return null;
  const accounts = idList(ticked);
  return accounts.length ? { accounts } : null;
}

/* ---- what the page may do (ruling S7), per chart ---- */
const NO_ACCOUNTS = "No accounts on this chart — pick one in the chart's ⚙ → Trading";
/* The desk-level half: down, or chart trading switched off on the desk; null when the desk is up and on. */
function deskGate(desk) {
  if (!desk || !desk.state) return { mode: 'down', reason: (desk && desk.down) || 'connecting to the desk', accounts: [] };
  if (!desk.state.enabled) return { mode: 'off', reason: 'Chart trading is off on the desk', accounts: [] };
  return null;
}
/* One chart's mode from its trade config: its ACCOUNTS are the switch, then the desk's rules. `accounts` is
   only ever a subset of THIS chart's accounts (the tradable ones). */
function tradeMode(desk, ct) {
  const t = cellTrade(ct);
  if (!t.accounts.length) return { mode: 'off', reason: NO_ACCOUNTS, accounts: [] };
  const gate = deskGate(desk);
  if (gate) return gate;
  const ticked = new Set(t.accounts);
  const accounts = accountsOf(desk.state).filter((a) => ticked.has(a.id) && a.tradable).map((a) => a.id);
  if (!accounts.length) return { mode: 'none', reason: 'No ticked account can trade right now', accounts };
  return { mode: 'on', reason: '', accounts };
}

/* ---- final whole-branch review (2026-09-27) ---- */
/* I2(b), SAFETY ruling: ANY symbol change on a chart CLEARS that chart's accounts (qty and SL/TP ticks are
   global, so an NQ chart moved to GC would otherwise trade GC at the NQ size on the next one-click). With the
   accounts as the switch (2026-09-27 accounts-per-chart plan) clearing them is what "switch it off" now means.
   `patch` is the change about to apply to `cfg`; null when it does not change the symbol. `cleared`: what was
   taken away -- the caller toasts SYMBOL_CHANGE_ACCOUNTS_CLEARED only when there really was something. */
const SYMBOL_CHANGE_ACCOUNTS_CLEARED = 'Accounts cleared — new instrument; pick them again in ⚙ → Trading';
function symbolChangeTrade(cfg, patch) {
  if (!isObj(cfg) || !isObj(patch) || !('root' in patch) || patch.root === cfg.root) return null;
  return { trade: { accounts: [] }, cleared: cellTrade(cfg.trade).accounts };
}

/* I1: a send button (the order panel's Send, the chart's Buy/Sell block) acts on a POINTER click, or on Enter /
   Space pressed on it -- never on a held key's auto-repeat, and never on the click event a keyboard makes
   (detail 0: keyboard activation is handled here instead, so it is counted once). Space sends on release (as a
   native button does), so a confirm dialog opens only after the key is up. `blur`: drop focus after a pointer
   click (the chart block), so a later Enter/Space -- or a menu closing and handing focus back -- cannot land
   on the button. `b` needs only addEventListener (and blur() when `blur`). */
function wireSend(b, send, { blur = false } = {}) {
  let spaceDown = false;
  b.addEventListener('click', (e) => { if (e.detail > 0) { if (blur) b.blur(); send(); } });
  b.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); if (!e.repeat) send(); }
    else if (e.key === ' ') { e.preventDefault(); if (!e.repeat) spaceDown = true; }
  });
  b.addEventListener('keyup', (e) => { if (e.key === ' ') { e.preventDefault(); if (spaceDown) { spaceDown = false; send(); } } });
  b.addEventListener('blur', () => { spaceDown = false; });
}

/* fast-paper: which of a surface's send buttons shows "sending" (pressed until its send resolves): the side of the one
   send in flight (HBTradeUI.sending() -- {surface, cell, side}, or null) when THIS surface started it -- the chart's
   Buy/Sell block ('chart': that chart's own block only, `cell`) or the order panel ('panel': whichever chart it
   follows now). null: none of its buttons (another surface's send, or none in flight). */
function sendingSide(sending, surface, cell) {
  if (!sending || sending.surface !== surface) return null;
  if (surface === 'chart' && sending.cell !== cell) return null;
  return sending.side === 'Buy' || sending.side === 'Sell' ? sending.side : null;
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
   chart's effective mode and its lines/markers, so a LIVE account never trades or draws until
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
    : { mode: 'none', reason: "Arm the LIVE account for this chart in the chart's ⚙ → Trading", accounts: [] };
}
/* A chart in replay can never trade (2026-09-27 bar-replay plan, Global Constraints): its Buy/Sell block,
   chart-menu trading items and draggable order lines are hidden for the duration. The chart KEEPS its
   accounts across a replay (they are the switch now, and replay must not throw them away): this guard alone
   is the refusal, from the instant replayui.js sets cell.replay. This is the last word on an otherwise-tradable mode
   -- HBTradeUI.effectiveMode runs every chart's mode through it, so nothing downstream (the block, the chart
   menu, a line's drag or ×) ever sees 'on' for a replaying chart. A mode that is not 'on' passes through
   unchanged: it is already refused for its own reason, and replay need not relabel it. */
/* Important 2 (fix round 1): a replay that ended WITHOUT the user choosing it (a reconnect, the server's own
   stop, an error, the chart destroyed) latches the chart until the user clicks "Resume live trading" on it --
   the practice block sat exactly where the real Buy/Sell block appears, so the next click must not be real. */
const REPLAY_ENDED = 'Replay ended — confirm to trade live again';
function replayHaltGuard(mode, halted) {
  return halted && mode && mode.mode === 'on' ? { mode: 'none', reason: REPLAY_ENDED, accounts: [] } : mode;
}
/* What a replay's end sets on the chart's config: `replayHalt` only for an end the user did not choose, and
   `replayConfirm` for ANY end -- the first real order afterwards always shows the confirm, one-click or not. */
function replayEndPatch(involuntary) { return { replayHalt: !!involuntary, replayConfirm: true }; }
/* Whether a chart-started send may skip the confirm dialog: that surface's one-click switch on (oneClickKey), and no
   replay end pending its confirm. */
function sendsWithoutConfirm(prefs, cfg, surface = null) {
  return !!(prefs && prefs[oneClickKey(surface)] === true) && !(isObj(cfg) && cfg.replayConfirm);
}
function replayGuard(mode, inReplay) {
  return inReplay && mode && mode.mode === 'on' ? { mode: 'none', reason: 'Replay — trading is off', accounts: [] } : mode;
}

/* Whether every leg of a line belongs to `accounts` (the desk's tradable accounts, lineAccounts): the only lines a
   chart may move or close. An empty or missing line never qualifies. */
function legsWithin(line, accounts) {
  const ok = new Set(accounts || []);
  return !!line && Array.isArray(line.legs) && line.legs.length > 0 && line.legs.every((l) => ok.has(l.account));
}
/* The accounts whose lines ANY chart may manage (drag, ×, a position chip's exit drag; 2026-09-27): every account the desk (or
   the paper book) lists as tradable, whatever the chart has ticked -- the ticked ones only decide where NEW entries
   go. An unlisted account is never in it (fail closed); a LIVE one still needs its arm at send time. */
function lineAccounts(state) { return accountsOf(state).filter((a) => a && a.tradable === true).map((a) => a.id); }
/* The chart's accounts as legend chips, "…047 DEMO": `active` when the account is in `activeIds` (the ones an order
   from this chart would go to right now); an account the desk does not list has no env. */
function accountChips(state, accounts, activeIds) {
  const act = new Set(activeIds || []), list = accountsOf(state);
  return idList(accounts).map((id) => {
    const a = list.find((x) => x.id === id), live = !!a && a.env === 'live', paper = !!a && a.env === 'paper';
    return { id, who: short(a || { id }), env: a ? envChip(a.env) : '', live, paper, active: act.has(id) };
  });
}

/* An account's env as its chip: LIVE (red), DEMO (grey), PAPER (the paper colour -- Task 2's virtual account), or
   '?' for an env the desk did not give (an account it does not list). */
const ENV_CHIPS = { live: 'LIVE', demo: 'DEMO', paper: 'PAPER' };
function envChip(env) { return ENV_CHIPS[String(env || '')] || '?'; }

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
  return `Arm LIVE account ${label} in the chart's ⚙ → Trading first`;
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
/* Typed numbers, strictly (fix round 1, review Minor 5): surrounding spaces are fine; commas, hex, exponents, signs
   and anything else are NaN -- never "0,5" read as 5. parseQty: whole contracts (digits only). parseUsd: digits
   with at most one decimal point. parseDecimal: the same for a price (a leading minus only when `neg`). */
function parseQty(s) { const t = String(s == null ? '' : s).trim(); return /^\d+$/.test(t) ? Number(t) : NaN; }
function parseUsd(s) { const t = String(s == null ? '' : s).trim(); return /^(\d+\.?\d*|\.\d+)$/.test(t) ? Number(t) : NaN; }
function parseDecimal(s, neg = false) {
  const t = String(s == null ? '' : s).trim();
  return (neg ? /^-?(\d+\.?\d*|\.\d+)$/ : /^(\d+\.?\d*|\.\d+)$/).test(t) ? Number(t) : NaN;
}
/* A price onto the tick grid, rounded toward `dir` (+1: up, -1: down); exact grid prices stay put. */
function roundTickDir(p, tick, dir) {
  if (!(tick > 0)) return p;
  const n = p / tick, k = dir > 0 ? Math.ceil(n - 1e-9) : Math.floor(n + 1e-9);
  return Number((k * tick).toFixed(Cat.decimals(tick)));
}
/* One exit (kind 'sl' | 'tp') of a side's order from `entry`, typed in `unit` ('usd' | 'ticks' | 'price'):
   {usd, ticks, price}. An SL sits below a Buy's entry (above a Sell's), a TP the other way. `ticks` is whole and
   >= 1, `price` tick-rounded, `usd` for the whole order's qty (null without a point value). Anything that can't make
   an exit (nothing typed, garbage, a price on the wrong side or AT the entry, no entry, a $ without a point value)
   -> null. `entry` is the order's price; a Market's last trade; a Stop Limit's trigger for its SL, limit for its TP.
   Fix round 1: an SL never ends up riskier than typed -- a $ SL floors to whole ticks (under one tick: null), an
   off-tick SL price rounds AWAY from the entry; a TP rounds to the nearest tick (a $ TP to at least 1 tick). */
function exitTriple({ unit, value, side, entry, tick, pv = null, kind, qty = 1 }) {
  const v = num(value), e = num(entry);
  if (!Number.isFinite(v) || !Number.isFinite(e) || !(tick > 0) || !['Buy', 'Sell'].includes(side)) return null;
  const dir = (side === 'Buy') === (kind === 'tp') ? 1 : -1;   // + : above the entry
  const perTick = pv != null && Number.isFinite(pv) && pv > 0 && qty > 0 ? tick * pv * qty : null;
  const sl = kind === 'sl';
  let ticks, onTick = null;
  if (unit === 'ticks') ticks = Math.round(v);
  else if (unit === 'usd') {
    if (perTick == null || !(v > 0)) return null;
    ticks = sl ? Math.floor(v / perTick + 1e-9) : Math.max(1, Math.round(v / perTick));
  } else if (unit === 'price') {
    onTick = sl ? roundTickDir(v, tick, dir) : roundTick(v, tick);   // an SL: away from the entry
    ticks = Math.round((dir * (onTick - e)) / tick);
  } else return null;
  if (!(ticks >= 1)) return null;
  const price = onTick != null ? onTick : roundTick(e + dir * ticks * tick, tick);
  return { usd: perTick == null ? null : Number((ticks * perTick).toFixed(2)), ticks, price };
}
/* The SL's distance for USD-risk sizing, in ticks, from the order's worst fill: a Stop Limit's LIMIT (it may fill
   anywhere up to it), otherwise its entry (a Market's last trade). `ref` is that price. */
function riskTicks(ref, sl, tick) {
  return ref == null || sl == null || !(tick > 0) ? 0 : Math.round(Math.abs(ref - sl) / tick);
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
  if (slPx != null && !Number.isFinite(slPx)) return bad('Enter the stop loss');
  if (tpPx != null && !Number.isFinite(tpPx)) return bad('Enter the take profit');
  // an off-tick SL rounds AWAY from the entry (fix round 1): below for a buy, above for a sell
  const S = slPx == null ? null : roundTickDir(slPx, tick, buy ? -1 : 1), TP = tpPx == null ? null : rt(tpPx);
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
    if (!(num(risk) > 0)) return bad('Enter the USD risk');
    if (S == null) return bad('USD risk needs a stop loss');
    if (!(pv > 0)) return bad('No point value for this chart yet');
    // sized from the WORST fill (fix round 1, review Important 1): a Stop Limit may fill anywhere up to its limit,
    // so its risk runs from the LIMIT to the SL -- the confirm's "risk (worst fill)"; Market / Limit / Stop: the entry
    n = qtyFromRisk(num(risk), riskTicks(tpRef, S, tick), tick, pv);
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
/* The send button: "Buy 2 NQ LIMIT" -- the ROOT, which is all the order body carries (the desk picks the contract);
   no number without a valid size. */
function sendLabel(side, qty, root, type) {
  return [side, qty >= 1 ? String(qty) : null, root, TYPE_WORDS[type] || String(type || '').toUpperCase()].filter(Boolean).join(' ');
}
/* ---- money ---- */
const sign = (v) => (v > 0 ? '+' : v < 0 ? MINUS : '');
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
   accounts whose lines may be managed from a chart -- lineAccounts, empty while the desk is down / off or the chart
   replays) marks which lines may be dragged / closed; an editable line and a read-only one are never merged
   together, so an action on a line can only reach editable accounts.
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
    // the PAPER account's lines are never merged with a desk account's (Task 2): they carry its tag and colour
    const paper = a.env === 'paper', ed = mine.has(a.id), pre = (ed ? 'e' : 'v') + (paper ? 'p' : ''), pp = paper ? { paper: true } : {};
    const who = short(a), pos = (a.positions || []).filter((p) => p.root === root && p.net);
    for (const p of pos) {
      const s = p.net > 0 ? 1 : -1;
      add(`${pre}|position|${s}|${p.avg_price}`, { kind: 'position', side: s > 0 ? 'Buy' : 'Sell', price: p.avg_price, editable: ed, ...pp },
        { account: a.id, who, qty: Math.abs(p.net), avg: p.avg_price, s, pv: p.point_value ?? null, symbol: p.symbol });
    }
    for (const o of a.orders || []) {
      const at = orderPrice(o);
      if (o.owner || at == null || rootOf(o.symbol) !== root) continue;
      const p = pos.find((x) => x.symbol === o.symbol);
      // a row that is not plainly Working (a pending entry's Suspended OSO leg, a PendingNew) is never the position's
      // own SL / TP -- it is drawn as the plain order it is (fix round 1, item 2; the desk refuses exits meanwhile)
      const pending = isPending(o);
      const exit = !pending && !!p && ((p.net > 0 && o.side === 'Sell') || (p.net < 0 && o.side === 'Buy'));
      const kind = !exit ? 'order' : /stop/i.test(o.type) ? 'sl' : /limit/i.test(o.type) ? 'tp' : 'order';
      const limit = o.type === 'StopLimit' ? o.price ?? null : undefined;   // drawn at the trigger, labelled with both
      add(`${pre}|${kind}|${o.side}|${o.type}|${at}${limit !== undefined ? `|${limit}` : ''}`,
        { kind, side: o.side, type: o.type, price: at, editable: ed, ...pp, ...(limit !== undefined ? { limit } : {}) },
        { account: a.id, who, qty: Number(o.qty) || 0, order_id: String(o.order_id),
          avg: p ? p.avg_price : null, s: p ? (p.net > 0 ? 1 : -1) : 0, pv: p ? p.point_value ?? null : null,
          ...(pending ? { pending: true, parent: o.parent_id != null ? String(o.parent_id) : null } : {}) });
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
/* Positions never move (ruling S11: dragging a position's chip draws a NEW exit, never modifies the position); a Stop
   Limit can't be moved (the desk refuses it): cancel and place again. */
function canDrag(g) { return g.kind !== 'position' && g.type !== 'StopLimit'; }
/* A position's chip is just side, size and P&L ("LONG 1 · −$20", 2026-09-27: the user's call), plus "· 2 accts" when it
   merges several accounts (review of d6bdb2e: its × / exit drag acts on every one of them, so that must show); the
   account names go in the chip's tooltip (lineTitle). Order / SL / TP lines still name theirs. */
function lineText(g, last) {
  if (g.kind === 'order') return [lineLabel(g), whoText(g)].join(' · ');
  if (g.kind === 'position') {
    const many = new Set(g.legs.map((l) => l.who)).size > 1;
    return [lineLabel(g), usd(linePnl(g, last)), many ? whoText(g) : null].filter(Boolean).join(' · ');
  }
  return [lineLabel(g), usd(linePnl(g, last)), whoText(g)].filter(Boolean).join(' · ');
}
/* The accounts a line holds, every one by name, for its chip's tooltip: "…041, …047". */
function lineTitle(g) { return [...new Set(((g && g.legs) || []).map((l) => l.who))].join(', '); }
const PAPER_COLOR = '#7E57C2';   // charts.css --paper (light); cell.js's palette carries the theme's own as P.paper
function lineColor(g, P) {
  if (g.paper) return P.paper || PAPER_COLOR;   // a PAPER line: the paper colour whatever its kind (its text says which)
  if (g.kind === 'position') return g.side === 'Buy' ? P.up : P.down;
  if (g.kind === 'sl') return P.down;
  if (g.kind === 'tp') return P.up;
  return g.side === 'Buy' ? P.accent : P.down;
}
const withPrice = (g, price) => ({ ...g, price });

/* ---- dragging a position's chip places an exit (2026-09-27, the desk's `exits` action) ----
   Pressing an editable position's chip (not its ×) and dragging it vertically draws a ghost exit line; which one is
   decided live by the pointer against the LAST TRADE (exitKindAt; review of d6bdb2e): for a long, below it is an SL
   (a stop), above it a TP (a limit) -- the order type the desk places -- so a winning long can also place a
   break-even / profit-locking stop above its entry; a short mirrored. Dropping it sends `exits` for the WHOLE position on each of its accounts (the desk / paper book
   makes it one OCO pair with an existing half). The position itself never moves (ruling S11).
   exitKinds says which exits may still be added: an SL while none of the position's accounts has a stop-type exit
   line in this root, a TP while none has a limit-type one (an existing SL / TP line is already draggable: move that);
   neither while any of those accounts has a pending order in this root (a Suspended bracket leg of an entry not filled
   yet, a PendingNew): the desk and the paper book refuse exits then (fix round 1, item 2). */
function exitKinds(g, groups) {
  if (!g || g.kind !== 'position' || g.editable !== true) return { sl: false, tp: false, pending: false };
  const mine = new Set(g.legs.map((l) => l.account));
  const any = (fn) => (groups || []).some((x) => x.legs.some((l) => mine.has(l.account) && fn(x, l)));
  if (any((x, l) => l.pending === true)) return { sl: false, tp: false, pending: true };
  return { sl: !any((x) => x.kind === 'sl'), tp: !any((x) => x.kind === 'tp'), pending: false };
}
/* The exit a drag of position `g` to `price` would place, against the last trade `last`: for a long an SL (stop) below
   it and a TP (limit) above it, mirrored for a short; null exactly at it (tick-grid epsilon), with no last trade, or
   for anything that isn't a position. Like exitDropError, the last known trade at any age counts (a quiet market's
   trade goes "stale" often: freshQuote's ruling); only no price at all refuses. */
function exitKindAt(g, price, last) {
  const ok = (v) => v != null && Number.isFinite(v);
  if (!g || g.kind !== 'position' || !ok(price) || !ok(last)) return null;
  const d = (price - last) * (g.side === 'Buy' ? 1 : -1);
  return Math.abs(d) < 1e-9 ? null : d > 0 ? 'tp' : 'sl';
}
/* Why a drop of that kind at that last trade can't go on (null = it can): the toast a refused drop shows. */
function exitRefusal(kinds, kind, last) {
  if (!kinds || kinds.pending) return 'This position has a pending order — exits wait until it fills or is cancelled';
  if (last == null || !Number.isFinite(last)) return "No recent price — can't place a stop or target";
  if (kind !== 'sl' && kind !== 'tp') return 'Drag above or below the price';
  if (kind === 'sl' && !kinds.sl) return 'This position already has a stop — drag the SL line to move it';
  if (kind === 'tp' && !kinds.tp) return 'This position already has a target — drag the TP line to move it';
  return null;
}
/* A press on a position chip is a drag only once the pointer has moved this many px vertically; less is a click,
   which does nothing. */
const EXIT_DRAG_PX = 4;
function pastClick(y0, y) { return Number.isFinite(y0) && Number.isFinite(y) && Math.abs(y - y0) >= EXIT_DRAG_PX; }
/* Why a line with pending (Suspended / held) bracket legs can't move to `price` (null = it can; review round 2, C). A
   pending leg is not live: it is checked against its PARENT entry order's price, never the last trade -- a stop on
   the losing side of the entry (a Stop Limit entry's trigger), a target on the winning side (its limit). A parent
   that can't be found in the account's orders, or has no price (a Market entry), refuses: fail closed. */
function pendingMoveError(line, price, state) {
  const legs = ((line && line.legs) || []).filter((l) => l.pending === true);
  const sl = /stop/i.test(String((line && line.type) || ''));
  for (const l of legs) {
    const a = accountsOf(state).find((x) => x.id === l.account);
    const p = a && l.parent != null ? (a.orders || []).find((o) => String(o.order_id) === String(l.parent)) : null;
    if (!p) return "Can't find this bracket's entry order — cancel it and place again";
    const ref = p.type === 'StopLimit' ? (sl ? p.stop_price ?? null : p.price ?? null) : p.type === 'Market' ? null : orderPrice(p);
    const s = p.side === 'Buy' ? 1 : p.side === 'Sell' ? -1 : 0;
    if (ref == null || !Number.isFinite(ref) || !s) return "This bracket's entry has no price to check against — cancel it and place again";
    if (sl && !(s * (ref - price) > 0)) return `A stop on a pending ${p.side.toLowerCase()} must stay ${s > 0 ? 'below' : 'above'} its entry (${px(ref)})`;
    if (!sl && !(s * (price - ref) > 0)) return `A target on a pending ${p.side.toLowerCase()} must stay ${s > 0 ? 'above' : 'below'} its entry (${px(ref)})`;
  }
  return null;
}
/* The ghost exit line a position-chip drag draws: the position's legs at `price`, labelled like a real SL / TP line
   ("SL 3 · −$600 · …047": the projected P&L of the whole position if it fills there). */
function exitGhost(g, kind, price) { return { ...g, key: `ghost|${kind}`, kind, type: kind === 'sl' ? 'Stop' : 'Limit', price }; }
/* Why an exit at `price` can't go on (null = it can): an SL beyond the last trade on the losing side, a TP beyond it on
   the winning side -- at or through it would be marketable. No last trade: refused (fail closed). */
function exitDropError(g, kind, price, last) {
  if (last == null || !Number.isFinite(last)) return "No recent price — can't place a stop or target";
  const long = g.side === 'Buy', what = kind === 'sl' ? 'stop loss' : 'target';
  const ok = kind === 'sl' ? (long ? price < last : price > last) : (long ? price > last : price < last);
  const where = (kind === 'sl') === long ? 'below' : 'above';
  return ok ? null : `A ${what} on a ${long ? 'long' : 'short'} must be ${where} the last price (${px(last)})`;
}
/* The position each account of a position line holds, signed (+long / −short): what the confirm shows ("Add SL 3"),
   frozen and sent as `expected_net` -- the desk and the paper book refuse if it changed, never resize (fix round 1,
   item 5). */
function expectedNet(g) {
  const out = {};
  for (const l of (g && g.legs) || []) out[l.account] = (out[l.account] || 0) + l.s * l.qty;
  return out;
}
/* The `exits` body: the position's accounts, one price (the other side stays whatever the desk has), and the
   position each account held when the confirm was shown. */
function exitsBody({ clientId, accounts, root, kind, price, expected }) {
  return { client_id: clientId, accounts: [...accounts], root, [kind === 'sl' ? 'sl_price' : 'tp_price']: price,
    expected_net: Object.fromEntries(accounts.map((a) => [a, expected[a]])) };
}
/* The confirm's title: "Add TP 3 @ 30,885.00 · …047". */
function exitsTitle(g, kind, price, tick) { return `Add ${kind.toUpperCase()} ${g.qty} @ ${Cat.fmtPrice(price, tick)} · ${whoText(g)}`; }

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
const VERB = { order: 'order accepted', modify: 'order moved', cancel: 'order cancelled', exits: 'exit placed', 'cancel-symbol': 'orders cancelled',
  flatten: 'flattened', reverse: 'reversed' };
function resultToasts(action, status, data, state) {
  if (action === 'bot-kill') return killToasts(status, data, state);
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

/* ---- execution arrows (2026-09-27): TradingView's, not series markers ----
   One small HORIZONTAL arrow per fill, just left of the bar that holds the fill, pointing right AT the fill price.
   Lightweight Charts' series markers only point up / down, so tradelines.js draws these itself (a canvas series
   primitive, repainted by the chart on every scroll / zoom) -- they never touch the shared markers map.
   `ids`: the chart's accounts (LIVE ones only once armed). Blue for a buy, red for a sell, on every account type
   (the PAPER account included: no tag, no colour of its own). `tip`: the hover text. */
function fillMarkers(state, root, ids, P, tick = 0.01) {
  const ticked = new Set(ids || []), out = [];
  for (const a of accountsOf(state)) {
    if (!ticked.has(a.id)) continue;
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      if (f.owner || rootOf(f.symbol) !== root || !Number.isFinite(ms) || !Number.isFinite(f.price)) continue;
      const buy = f.side === 'Buy';
      out.push({ id: `f${a.id}:${f.id}`, ms, price: f.price, side: buy ? 'Buy' : 'Sell', color: buy ? P.accent : P.down,
        tip: `${buy ? 'Buy' : 'Sell'} ${f.qty} @ ${Cat.fmtPrice(f.price, tick)} · ${short(a)}` });
    }
  }
  return out;
}
/* The arrow's outline in pixels for a bar centred at x (bar spacing `spacing`) and a fill at y: its tip sits just
   left of the candle body (half the body, ~0.4 of the spacing, plus a 2 px gap, capped so a wide zoom never pushes
   it far from its bar), a 5 px head 3.5 px either side of y and a 4 px shaft 1 px thick. `hover`: its middle. */
const ARROW = { head: 5, half: 3.5, shaft: 4, thick: 1, gap: 2, maxOff: 10 };
function execArrow(x, y, spacing) {
  const A = ARROW, tx = x - Math.min(A.maxOff, Math.max(0, spacing) * 0.4) - A.gap, hx = tx - A.head, sx = hx - A.shaft;
  return { tip: [tx, y], hover: [(tx + sx) / 2, y],
    pts: [[tx, y], [hx, y - A.half], [hx, y - A.thick], [sx, y - A.thick], [sx, y + A.thick], [hx, y + A.thick], [hx, y + A.half]] };
}

/* ---- the algo on a chart (2026-09-27 plan, Task 3) ----
   A chart's `algo` (a desk strategy key) draws that bot's run: a legend badge (name, state pill, today's P&L, Kill),
   its working orders as read-only BOT lines, its fills as markers, and its real past runs (GET bot-history) as
   markers with a tooltip. A chart without an algo draws none of it, even on the bot's root. */
const ALGO_NAMES = { nq930: 'NQ 9:30 Straddle', ym930: 'YM 9:30 Straddle', nq10am: 'NQ 10:00 Continuation',
  gc_nfpcpi: 'GC 8:30 NFP + CPI Straddle', 'paper:gc_nfpcpi': 'GC NFP/CPI (paper)' };
const GREY = '#9598A1';   // a past day it did not trade: TradingView's neutral grey
const CHECK_IT_TIP = 'Killed, but the desk could not account for its whole position: the stops were left working — '
  + 'verify the position at the broker';
const STATUS_WORDS = { skipped: 'Skipped', refused: 'Refused', no_fill: 'No fill', killed: 'Killed', error: 'Error', traded: 'Traded',
  no_data: 'No data', calendar_missing: 'No calendar' };
const EXIT_WORDS = { tp: 'TP', sl: 'SL', flat: 'Flat', other: 'Exit' };
const ET_PARTS = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric',
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });

function algoName(key) { return ALGO_NAMES[key] || String(key || ''); }
const whoOf = (state, id) => short(accountsOf(state).find((x) => x.id === id) || { id });
/* The strategy's accounts: its book's, then any it acted on today (the bot view's), de-duplicated. */
function algoAccounts(s) {
  return isObj(s) ? [...new Set([...Object.keys(isObj(s.book) ? s.book : {}), ...Object.keys(isObj(s.accounts) ? s.accounts : {})])] : [];
}
/* "NQ 9:30 Straddle · …047": the name and the last 3 of each booked account. */
function algoLabel(key, s, state) {
  const who = Object.keys((s && isObj(s.book) && s.book) || {}).map((id) => whoOf(state, id));
  return who.length ? `${algoName(key)} · ${who.join(', ')}` : algoName(key);
}
/* The Settings dialog's Algo select for a chart on `root`: None, then the desk's strategies on that root, then any
   paper strategy (Task 2's GET /api/paper/strategies, `paperList`) on that root, as "paper:<id>" -- its own `name`
   verbatim (e.g. "GC NFP/CPI (paper)"), never re-derived. The chart's current algo stays listed (by name) while
   NEITHER list has confirmed it yet, so the select can show it. */
function algoChoices(state, root, current = null, paperList = null) {
  const strats = (state && state.bot && isObj(state.bot.strategies) && state.bot.strategies) || {};
  const papers = (Array.isArray(paperList) ? paperList : []).filter((p) => isObj(p) && typeof p.id === 'string' && p.id);
  const out = [{ value: '', text: 'None' },
    ...Object.entries(strats).filter(([, s]) => isObj(s) && rootOf(s.symbol) === root)
      .map(([k, s]) => ({ value: k, text: algoLabel(k, s, state) })),
    ...papers.filter((p) => rootOf(p.root) === root).map((p) => ({ value: paperKey(p.id), text: p.name || algoName(paperKey(p.id)) }))];
  const cur = cellAlgo(current);   // fix round 1, M4: only while NEITHER list has confirmed it (unconfirmed), never a
                                   // confirmed other-root strategy
  const confirmedElsewhere = cur && (isObj(strats[cur]) || papers.some((p) => paperKey(p.id) === cur));
  if (cur && !confirmedElsewhere && !out.some((c) => c.value === cur)) out.push({ value: cur, text: algoName(cur) });
  return out;
}

/* ---- the chart's gear -> Trading tab (2026-09-27 accounts-per-chart plan, Task 1) ---- */
/* Which desk strategies on `root` book which accounts: [{key, name, accounts}], in the desk's own order. A
   strategy's BOOK is what "belongs to an algo" means -- not the accounts it happened to act on today. */
function algoBookings(state, root) {
  const strats = (state && state.bot && isObj(state.bot.strategies) && state.bot.strategies) || {};
  return Object.entries(strats)
    .filter(([, s]) => isObj(s) && rootOf(s.symbol) === root)
    .map(([key, s]) => ({ key, name: algoName(key), accounts: Object.keys(isObj(s.book) ? s.book : {}) }));
}
/* The algo on `root` that books `id`, or null: ticking that account sets the ALGO select to it. */
function algoForAccount(state, root, id) {
  const b = algoBookings(state, root).find((x) => x.accounts.includes(id));
  return b ? b.key : null;
}
/* The accounts `key` books on `root`; [] when it is not a desk strategy on this root (a paper algo books none). */
function accountsForAlgo(state, root, key) {
  const k = cellAlgo(key), b = k ? algoBookings(state, root).find((x) => x.key === k) : null;
  return b ? [...b.accounts] : [];
}
/* Which of an algo's booked accounts a PICK of it may tick: never a LIVE one that is not already armed this
   session (a LIVE account is only ever ticked through its own two-step arm) and never one the desk does not
   list (armedTicked fails closed on both). */
function algoTickAccounts(state, root, key, liveConfirmed) {
  const tradable = new Set(accountsOf(state).filter((a) => a.tradable).map((a) => a.id));   // Minor 5: as toggleAccount
  return armedTicked(state, accountsForAlgo(state, root, key), liveConfirmed).filter((id) => tradable.has(id));
}
/* The ACCOUNTS section's rows for one chart: every account the desk lists, then any on THIS chart's list the
   desk does not (chip '?', never tradable -- fail closed -- but always removable from the chart).
     tick: 'ticked' | 'off' | 'unarmed' (acctTick); disabled: the checkbox cannot be turned ON;
     note: "in NQ 9:30 Straddle" when an algo on this chart's instrument books it. */
function accountPickRows(state, accounts, liveConfirmed, root) {
  const on = idList(accounts), onSet = new Set(on), listed = accountsOf(state);
  const rows = listed.map((a) => {
    const tick = acctTick(a, on, liveConfirmed), algo = algoForAccount(state, root, a.id);
    return { id: a.id, label: a.label || a.id, env: a.env || '', chip: envChip(a.env), live: a.env === 'live',
      paper: a.env === 'paper', balance: money(a.balance), connected: !!a.connected, listed: true,
      tick, disabled: !a.tradable && tick === 'off', error: a.tradable ? '' : (a.error || 'not tradable'),
      algo, note: algo ? `in ${algoName(algo)}` : '' };
  });
  const seen = new Set(listed.map((a) => a.id));
  for (const id of on) {
    if (seen.has(id)) continue;
    rows.push({ id, label: id, env: '', chip: '?', live: false, paper: false, balance: '—', connected: false,
      listed: false, tick: 'ticked', disabled: false, error: "not on the desk's list — cannot trade", algo: null, note: '' });
  }
  return rows.filter((r) => r.listed || onSet.has(r.id));
}
/* The desk's own state for the bottom status bar (it left the deleted Trade button with it): a dot, the line,
   and whether to show the "Open the desk" link. */
function deskStatusText(desk, chartWhyText = '') {
  const gate = deskGate(desk);
  if (gate && gate.mode === 'down') return { dot: 'bad', text: `Desk unreachable — ${gate.reason}`, link: false };
  if (gate) return { dot: 'warn', text: 'Chart trading is off on the desk', link: true };
  const lim = (desk.state && desk.state.limits) || {};
  return { dot: 'ok', link: false,
    text: `Desk: connected · chart trading on · max ${lim.max_order_qty ?? '—'}/order, ${lim.max_position_qty ?? '—'}/position`
      + (chartWhyText ? ` · this chart: ${chartWhyText}` : '') };
}
/* Minor 6: the SELECTED chart's own short reason for the status bar ('' when it can trade). `mode` is its
   effective mode; the rest say why, most specific first. */
function chartWhy({ replay = false, halted = false, accounts = [], unverified = [], state = null, liveConfirmed = null, mode = null } = {}) {
  if (replay) return 'replay';
  if (halted) return 'replay ended — resume to trade';
  const acc = idList(accounts);
  if (!acc.length) return 'no accounts';
  if (!mode || mode.mode === 'on') return '';
  const armed = liveConfirmed instanceof Set ? liveConfirmed : new Set(liveConfirmed || []);
  const unarmed = accountsOf(state).filter((a) => acc.includes(a.id) && a.env === 'live' && !armed.has(a.id));
  if (unarmed.length) return `arm LIVE ${unarmed.map(short).join(', ')}`;
  if (idList(unverified).some((id) => acc.includes(id))) return 'checking accounts';
  const r = String(mode.reason || '');
  return r ? r[0].toLowerCase() + r.slice(1) : '';
}

const fmt1 = (v) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(1));
function gateText(t) { return t.gate === true ? `TREND ADX ${fmt1(t.adx)}` : t.gate === false ? `CHOP ADX ${fmt1(t.adx)}` : ''; }
/* The badge's state pill from the bot view: {state, text, tone, tip}. state is one of idle / armed / placing /
   in trade / done / skipped / killed / shadow, plus 'check it' (a killed run the desk could not fully account
   for: amber), 'off' (disabled on the desk) and 'error'. tone: idle | live | warn | err. */
function botPill(s) {
  const t = (s && isObj(s.timer) && s.timer) || {}, accts = Object.values((s && isObj(s.accounts) && s.accounts) || {});
  const pill = (state, tone, tip = '') => ({ state, text: state === 'check it' ? 'CHECK IT' : state, tone, tip });
  const gate = gateText(t);
  if (accts.some((a) => a && a.check_it)) return pill('check it', 'warn', CHECK_IT_TIP);
  if (s.killed || t.killed) return pill('killed', 'err', 'Killed from the chart: it does not fire again today');
  if (!s.enabled) return pill('off', 'idle', 'Disabled on the desk');
  if (s.shadow) return pill('shadow', 'idle', 'Shadow: its signals are journaled, never placed');
  const d = s.day_status;
  if (d === 'error' || t.stage === 'error') {
    const note = accts.map((a) => a && a.note).find(Boolean);
    return pill('error', 'err', t.error || note || 'The desk reported an error — see the desk');
  }
  if (d === 'live') return pill('in trade', 'live', 'In a position, its stop and target working');
  if (d === 'placing') return pill('placing', 'live', 'Sending its entry orders');
  if (d === 'placed') return pill('armed', 'live', 'Its entry orders are working, waiting for a fill');
  if (d === 'done') return pill('done', 'idle', 'Done for today');
  if (t.stage === 'skipped') return pill('skipped', 'idle', `Skipped today${gate ? ` — ${gate}` : ''}`);
  if (t.stage === 'missed') return pill('skipped', 'idle', 'Missed its window today');
  if (t.stage === 'staged') return pill('armed', 'live', `Staged: fires at the open${gate ? ` — ${gate}` : ''}`);
  return pill('idle', 'idle', gate);
}
/* Today's P&L across its accounts: realized, plus an open trade at `last`; null while nothing is known. */
function botToday(s, last, pv) {
  let sum = 0, any = false;
  for (const a of Object.values((s && isObj(s.accounts) && s.accounts) || {})) {
    if (!a) continue;
    if (a.pnl != null && Number.isFinite(a.pnl)) { sum += a.pnl; any = true; continue; }
    if (a.status === 'live' && a.entry_fill != null) {
      const v = pnl(a.entry_fill, last, a.entry_side === 'Buy' ? 1 : -1, Number(a.entry_qty ?? a.qty) || 0, pv);
      if (v == null) return null;
      sum += v; any = true;
    }
  }
  return any ? sum : null;
}

/* Its working orders as read-only lines: the orders the desk tags with its key (owner), plus any level the bot view
   says it is working that no listed order shows yet (the order list lags an ack). A leg on the entry side (or at
   the view's entry trigger before a fill) is an entry, "BOT BUY STP 10 @ …"; once in a position, the opposite
   side's Stop is its SL and its Limit its TP. Merged across accounts by kind + side + price, highest price first. */
function botLines(state, key, s, root, tick, P) {
  const m = new Map(), views = isObj(s.accounts) ? s.accounts : {};
  const put = (kind, side, type, price, qty) => {
    if (price == null || !Number.isFinite(price)) return;
    const id = `${kind}|${side}|${price}`;
    const g = m.get(id) || { key: `bot|${key}|${id}`, kind, side, type, price, qty: 0, editable: false, bot: true };
    g.qty += Number(qty) || 0;
    m.set(id, g);
  };
  const eps = tick > 0 ? tick / 2 : 1e-9, near = (a, b) => a != null && b != null && Math.abs(a - b) < eps;   // M6: a tick epsilon
  const kindOf = (st, side, type, price) => {
    const inTrade = !!(st && st.entry_side) && ['live', 'done', 'error'].includes(st.status);
    if (inTrade && side !== st.entry_side) return /limit/i.test(type) && !/stop/i.test(type) ? 'tp' : 'sl';
    if (st && ((side === 'Buy' && near(price, st.upper)) || (side === 'Sell' && near(price, st.lower)))) return 'entry';
    if (inTrade) return 'entry';
    return /limit/i.test(type) && !/stop/i.test(type) ? 'tp' : /stop/i.test(type) && (st && (st.upper != null || st.lower != null)) ? 'sl' : 'entry';
  };
  const ids = new Set(algoAccounts(s));
  for (const a of accountsOf(state)) ids.add(a.id);
  for (const id of ids) {
    const a = accountsOf(state).find((x) => x.id === id), st = views[id];
    const own = ((a && a.orders) || []).filter((o) => o.owner === key && rootOf(o.symbol) === root && orderPrice(o) != null);
    const seen = new Set();   // kind|side of this account's listed orders: the view never adds a second one (M6)
    for (const o of own) {
      const at = orderPrice(o), kind = kindOf(st, o.side, o.type, at);
      seen.add(`${kind}|${o.side}`);
      put(kind, o.side, o.type, at, o.qty);
    }
    if (!st) continue;
    // a level the bot view says it works, only when no order of that kind and side is listed for the account (the list
    // lags an ack) -- a working order at a slightly different price (a bracket move in flight) is the truth
    const add = (kind, side, type, price, qty) => { if (!seen.has(`${kind}|${side}`)) put(kind, side, type, price, qty); };
    if (st.status === 'placing' || st.status === 'placed') {
      add('entry', 'Buy', 'Stop', st.upper, st.qty); add('entry', 'Sell', 'Stop', st.lower, st.qty);
    }
    if (st.status === 'live' && st.entry_side) {
      const out = st.entry_side === 'Buy' ? 'Sell' : 'Buy', q = st.entry_qty ?? st.qty;
      add('sl', out, 'Stop', st.sl, q); add('tp', out, 'Limit', st.tp, q);
    }
  }
  return [...m.values()].sort((x, y) => y.price - x.price).map((g) => {
    const at = Cat.fmtPrice(g.price, tick);
    const text = g.kind === 'entry' ? `BOT ${g.side.toUpperCase()} ${abbr(g.type)} ${g.qty} @ ${at}` : `BOT ${g.kind.toUpperCase()} ${g.qty} @ ${at}`;
    const color = g.kind === 'sl' ? P.down : g.kind === 'tp' ? P.up : g.side === 'Buy' ? P.accent : P.down;
    return { ...g, text, color };
  });
}
/* Today's fills of the bot (owner = its key): the entry an arrow in the bot colour, the exit a circle with the P&L. */
function botMarkers(state, key, s, root, tick, P) {
  const out = [], views = isObj(s.accounts) ? s.accounts : {};
  for (const a of accountsOf(state)) {
    const st = views[a.id];
    for (const f of a.fills || []) {
      const ms = Date.parse(f.time);
      if (f.owner !== key || rootOf(f.symbol) !== root || !Number.isFinite(ms)) continue;
      const entry = !st || !st.entry_side || f.side === st.entry_side, buy = f.side === 'Buy';
      const v = !entry && st && st.pnl != null && Number.isFinite(st.pnl) ? st.pnl : null;
      const tip = `Today · ${short(a)} · ${f.side} ${f.qty} @ ${Cat.fmtPrice(f.price, tick)}${entry ? '' : ` (exit)${v != null ? ` · ${usd(v)}` : ''}`}`;
      out.push(entry
        ? { id: `b${a.id}:${f.id}`, account: a.id, ms, price: f.price, position: buy ? 'atPriceBottom' : 'atPriceTop', shape: buy ? 'arrowUp' : 'arrowDown', color: P.warn, text: '', tip }
        : { id: `b${a.id}:${f.id}`, account: a.id, ms, price: f.price, position: 'atPriceMiddle', shape: 'circle',
          color: v == null ? P.warn : v >= 0 ? P.up : P.down, text: v == null ? '' : usd(v), tip });
    }
  }
  return out.sort((x, y) => x.ms - y.ms);
}
/* Everything a chart draws for its algo, or null: no algo, no desk state, not on the desk, or another root. */
function algoOverlay(state, algo, root, tick, P, last = null, pv = null) {
  const key = cellAlgo(algo), strats = state && state.bot && isObj(state.bot.strategies) ? state.bot.strategies : null;
  const s = key && strats ? strats[key] : null;
  if (!isObj(s) || rootOf(s.symbol) !== root) return null;
  const markers = botMarkers(state, key, s, root, tick, P);
  return { key, name: algoName(key), label: algoLabel(key, s, state), gate: gateText(isObj(s.timer) ? s.timer : {}), pill: botPill(s),
    pnl: botToday(s, last, pv), accounts: algoAccounts(s), lines: botLines(state, key, s, root, tick, P), markers,
    liveAccounts: [...new Set(markers.map((m) => m.account))] };
}

/* ---- past runs (GET /api/desk/bot-history) ---- */
/* An ET wall-clock time on an ISO date as epoch ms (DST-aware); NaN for garbage. */
function etMs(date, hhmm) {
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(date || '')), t = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ''));
  if (!d || !t) return NaN;
  const want = Date.UTC(+d[1], +d[2] - 1, +d[3], +t[1], +t[2]);
  let ms = want + 5 * 3600e3;
  for (let i = 0; i < 2; i++) {
    const p = Object.fromEntries(ET_PARTS.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
    ms += want - Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
  }
  return ms;
}
/* The contracts a past run traded: from its P&L when that solves to a whole number (exact: bothistory computes the P&L
   from these very prices and qty); otherwise null -- never today's book size for a past day (fix round 1, M2). */
function runQty(run, pv) {
  const e = run.entry, x = run.exit, v = run.pnl_usd;
  if (e && x && e.price != null && x.price != null && v != null && pv > 0) {
    const per = (e.side === 'Buy' ? 1 : -1) * (x.price - e.price) * pv - 4;   // bothistory: net of $4 per contract round trip
    if (Math.abs(per) > 1e-9) {
      const q = v / per;
      if (q >= 0.5 && Math.abs(q - Math.round(q)) < 0.01) return Math.round(q);
    }
  }
  return null;
}
const reasonText = (r) => String(r).replace(/_/g, ' ');
/* "2026-09-24 · …047 · Buy 10 @ 30,120.25 → TP 30,135.25 · +$2,960"; a day it did not trade: "… · Skipped — gate chop". */
function runTip(run, who, tick, qty) {
  const head = `${run.date} · ${who}`, status = run.status, word = STATUS_WORDS[status] || String(status || '');
  const why = run.reason != null && run.reason !== '' ? ` — ${reasonText(run.reason)}` : '';
  const e = run.entry;
  if (!e) return `${head} · ${word}${why}`;
  let s = `${head} · ${e.side} ${qty != null ? `${qty} ` : ''}@ ${Cat.fmtPrice(e.price, tick)}`;
  const x = run.exit;
  if (x) s += ` → ${EXIT_WORDS[x.kind] || 'Exit'} ${Cat.fmtPrice(x.price, tick)} · ${run.pnl_usd != null ? usd(run.pnl_usd) : 'P&L unknown'}`;
  else s += ' · no exit';
  if (status && status !== 'traded') s += ` · ${String(word).toLowerCase()}${why}`;
  return s;
}
/* The past runs as markers ({ms, ..., tip} for HBDrawings.placeMarkers once `tip` is taken off): per traded run an
   entry arrow and an exit circle (green / red by its P&L, the bot colour when unknown); a day it did not trade a
   small grey square above the bar where it placed, else at the 09:30 ET open. Only markers in [from, to) are
   kept. `today`'s run of an account in `liveAccounts` (it has live bot fills today) is left to the live overlay;
   any other run of today is drawn from here (fix round 1). A run with no account covers every booked account. */
function pastRunMarkers(runs, { key, s, state, tick, pv, P, from, to, today, liveAccounts = [] }) {
  const out = [], book = (s && isObj(s.book) && s.book) || {}, live = new Set(liveAccounts || []);
  const everyone = Object.keys(book).map((id) => whoOf(state, id)).join(', ') || 'every account';
  const inRange = (ms) => Number.isFinite(ms) && ms >= from && ms < to;
  for (const run of Array.isArray(runs) ? runs : []) {
    if (!isObj(run) || typeof run.date !== 'string') continue;
    const acct = typeof run.account === 'string' ? run.account : null;
    if (run.date === today && acct && live.has(acct)) continue;
    const who = acct ? whoOf(state, acct) : everyone, id = `h${key}:${run.date}:${acct || '*'}`;
    const e = isObj(run.entry) ? run.entry : null, x = isObj(run.exit) ? run.exit : null;
    if (e && e.price != null && Number.isFinite(e.ts)) {
      const tip = runTip(run, who, tick, runQty(run, pv)), buy = e.side === 'Buy';
      if (inRange(e.ts)) {
        out.push({ id: `${id}:e`, ms: e.ts, price: e.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
          shape: buy ? 'arrowUp' : 'arrowDown', color: P.warn, text: '', tip });
      }
      if (x && x.price != null && inRange(x.ts)) {
        const v = run.pnl_usd;
        out.push({ id: `${id}:x`, ms: x.ts, price: x.price, position: 'atPriceMiddle', shape: 'circle',
          color: v == null ? P.warn : v >= 0 ? P.up : P.down, text: '', tip });
      }
      continue;
    }
    const leg = (Array.isArray(run.legs) ? run.legs : []).find((l) => l && Number.isFinite(l.ts));
    const ms = leg ? leg.ts : etMs(run.date, '09:30');
    if (inRange(ms)) out.push({ id: `${id}:f`, ms, position: 'aboveBar', shape: 'square', size: 0.5, color: GREY, text: '', tip: runTip(run, who, tick, null) });
  }
  return out.sort((a, b) => a.ms - b.ms);
}
/* The tip of the marker nearest (x, y) within r px, or null. points: [{x, y, tip}]. */
function nearestTip(points, x, y, r) {
  let best = null, bd = r * r;
  for (const p of points || []) {
    const d = (p.x - x) ** 2 + (p.y - y) ** 2;
    if (d <= bd) { bd = d; best = p; }
  }
  return best ? best.tip : null;
}
/* What a change on the bot view means for its history: a new exit fill, a skip, a kill -> fetch again. */
function historySig(s) {
  if (!isObj(s)) return '';
  const t = isObj(s.timer) ? s.timer : {};
  const accts = Object.entries(isObj(s.accounts) ? s.accounts : {}).map(([id, a]) => [id, a && a.status, a && a.exit_fill != null ? a.exit_fill : null]);
  return JSON.stringify([t.stage || null, !!s.killed, accts.sort((a, b) => (a[0] < b[0] ? -1 : 1))]);
}

/* ---- the paper (forward-test) algo on a chart (2026-09-27 paper-forward-test plan, Task 2) ----
   A chart's `algo` may instead name a PAPER strategy: "paper:<id>" (e.g. "paper:gc_nfpcpi"), never a desk one.
   It draws the same shape of overlay as a bot's (a legend badge, dashed read-only lines, markers, past runs) from
   the chart service's OWN state -- GET /api/paper/strategies (the static list), the /ws {"type":"paper", ...}
   push (`current`, the latest message per strategy id) and GET /api/paper/history (past runs + stats) -- never the
   desk's. It never sends an order, so it has no Kill and no accounts. */
const PAPER_PREFIX = 'paper:';
const PAPER_EVENT_TIME = '08:30';   // the strategy's fixed fire time (paper.py EVENT_TIME): for a day with no entry
function paperKey(id) { return `${PAPER_PREFIX}${id}`; }
function isPaperAlgo(key) { return typeof key === 'string' && key.startsWith(PAPER_PREFIX) && key.length > PAPER_PREFIX.length; }
function paperStrategyId(key) { return isPaperAlgo(key) ? key.slice(PAPER_PREFIX.length) : null; }
/* {id, root, params} entries (GET /api/paper/strategies) as an algoForRoot-shaped map, keyed "paper:<id>" -> {symbol:
   root}: merge this into the desk's own strategies map (never null) so HBTrade.algoForRoot confirms a paper algo's
   root exactly like a desk one, and clears it only once THIS list confirms a mismatch. */
function paperStrategiesMap(list) {
  const out = {};
  for (const p of Array.isArray(list) ? list : []) {
    if (isObj(p) && typeof p.id === 'string' && p.id && typeof p.root === 'string' && p.root) out[paperKey(p.id)] = { symbol: p.root };
  }
  return out;
}

/* The badge's state pill from the latest /ws paper message: state one of waiting / armed / "in trade" / done (a
   status of "error" always wins the tone, whatever state it arrived with). No message yet: waiting, no tip. */
function paperPill(msg) {
  const raw = msg && msg.state, state = raw === 'in_trade' ? 'in trade' : raw || 'waiting';
  const err = !!(msg && msg.status === 'error');
  const tone = err ? 'err' : state === 'armed' || state === 'in trade' ? 'live' : 'idle';
  return { state, text: state, tone, tip: paperTip(msg) };
}
function paperTip(msg) {
  if (!msg) return 'No paper run yet today';
  if (msg.status === 'error') return msg.error || 'The paper runner reported an error';
  if (msg.status === 'no_data') return `Feed gap — this run could not be trusted${msg.error ? ` (${msg.error})` : ''}`;
  if (msg.status === 'calendar_missing') return 'No calendar data for this date';
  if (msg.state === 'waiting') return 'Waiting for the event window to open';
  if (msg.state === 'armed') return 'Simulated stop entries placed, waiting for a fill';
  if (msg.state === 'in_trade') return 'In a simulated position';
  if (msg.status === 'no_fill') return 'No fill today';
  if (msg.status === 'traded') return 'Done for today';
  return '';
}
/* Today's paper P&L: the finished run's, else the open (provisional) mark while in a simulated position; null
   while neither is known yet. */
function paperToday(msg) {
  if (!msg) return null;
  if (msg.pnl_usd != null && Number.isFinite(msg.pnl_usd)) return msg.pnl_usd;
  if (msg.open_pnl_usd != null && Number.isFinite(msg.open_pnl_usd)) return msg.open_pnl_usd;
  return null;
}
/* "GC NFP/CPI (paper) · CPI": the strategy's name, plus today's event once the calendar has decided one. */
function paperLabel(name, msg) { return msg && msg.event ? `${name} · ${msg.event}` : name; }

/* One dashed, read-only paper line: an "entry" (a simulated stop order, still pending) or an "sl"/"tp" (once in a
   simulated position) -- the same shape as HBTrade.botLines' lines, so HBTradeLines can paint it the same way. */
function paperLine(kind, side, price, tick, P) {
  const at = Cat.fmtPrice(price, tick);
  const text = kind === 'entry' ? `PAPER ${side.toUpperCase()} STP @ ${at}` : `PAPER ${kind.toUpperCase()} @ ${at}`;
  const color = kind === 'sl' ? P.down : kind === 'tp' ? P.up : side === 'Buy' ? P.accent : P.down;
  return { key: `paper|${kind}|${side}|${price}`, kind, side, price, editable: false, paper: true, text, color };
}
/* The paper strategy's lines from its latest /ws message: both simulated stop entries while armed (no fill yet),
   or its SL/TP (the opposite side of its fill) once in a simulated position; none once done (its entry/exit are
   markers instead, like the bot's), and none while still waiting (no legs known yet). */
function paperLines(msg, tick, P) {
  if (!msg) return [];
  if (msg.state === 'armed' && Array.isArray(msg.legs)) {
    return msg.legs.filter((l) => isObj(l) && Number.isFinite(l.price) && (l.side === 'Buy' || l.side === 'Sell'))
      .map((l) => paperLine('entry', l.side, l.price, tick, P));
  }
  if (msg.state === 'in_trade' && isObj(msg.entry)) {
    const out = msg.entry.side === 'Buy' ? 'Sell' : 'Buy', lines = [];
    if (Number.isFinite(msg.entry.tp)) lines.push(paperLine('tp', out, msg.entry.tp, tick, P));
    if (Number.isFinite(msg.entry.sl)) lines.push(paperLine('sl', out, msg.entry.sl, tick, P));
    return lines;
  }
  return [];
}
/* Today's fill markers from the latest /ws message: the entry an arrow, the exit (once it has one) a circle with
   the P&L -- exactly like the bot's, tagged PAPER in the tooltip instead of an account. */
function paperMarkers(msg, tick, P) {
  if (!msg || !isObj(msg.entry) || msg.entry.price == null || !Number.isFinite(msg.entry.ts)) return [];
  const e = msg.entry, buy = e.side === 'Buy', id = `paper:${msg.date}`, out = [];
  out.push({ id: `${id}:e`, ms: e.ts, price: e.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
    shape: buy ? 'arrowUp' : 'arrowDown', color: P.warn, text: '', tip: `PAPER · ${e.side} @ ${Cat.fmtPrice(e.price, tick)}` });
  const x = msg.exit;
  if (isObj(x) && x.price != null && Number.isFinite(x.ts)) {
    const v = msg.pnl_usd;
    out.push({ id: `${id}:x`, ms: x.ts, price: x.price, position: 'atPriceMiddle', shape: 'circle',
      color: v == null ? P.warn : v >= 0 ? P.up : P.down, text: v == null ? '' : usd(v),
      tip: `PAPER · ${EXIT_WORDS[x.kind] || 'Exit'} @ ${Cat.fmtPrice(x.price, tick)}${v != null ? ` · ${usd(v)}` : ''}` });
  }
  return out;
}
/* Everything a chart draws for its paper algo, or null: not a paper algo, the strategy not (yet) listed, or
   another root. `paper` is {strategies: GET /api/paper/strategies' list, current: {id -> latest /ws message}}. */
function paperOverlay(paper, algo, root, tick, P) {
  const key = cellAlgo(algo);
  if (!isPaperAlgo(key)) return null;
  const id = paperStrategyId(key);
  const list = paper && Array.isArray(paper.strategies) ? paper.strategies : [];
  const strat = list.find((s) => isObj(s) && s.id === id);
  if (!strat || rootOf(strat.root) !== root) return null;
  const msg = paper && isObj(paper.current) ? paper.current[id] : null;
  const name = strat.name || algoName(key);
  return { key, id, name, label: paperLabel(name, msg), event: (msg && msg.event) || null, pill: paperPill(msg),
    pnl: paperToday(msg), lines: paperLines(msg, tick, P), markers: paperMarkers(msg, tick, P) };
}

/* ---- the paper strategy's past runs (GET /api/paper/history) ---- */
/* "2026-09-24 · PAPER CPI · Buy @ 30,120.25 → TP 30,135.25 · +$2,960"; a day with no entry: "… · PAPER · No fill". */
function paperRunTip(run, tick) {
  const status = run.status, word = STATUS_WORDS[status] || String(status || '');
  const head = `${run.date} · PAPER${run.event ? ` ${run.event}` : ''}`;
  const e = run.entry;
  if (!e) return `${head} · ${word}`;
  let s = `${head} · ${e.side} @ ${Cat.fmtPrice(e.price, tick)}`;
  const x = run.exit;
  if (x) s += ` → ${EXIT_WORDS[x.kind] || 'Exit'} ${Cat.fmtPrice(x.price, tick)} · ${run.pnl_usd != null ? usd(run.pnl_usd) : 'P&L unknown'}`;
  else s += ' · no exit';
  if (status && status !== 'traded') s += ` · ${String(word).toLowerCase()}`;
  return s;
}
/* Past paper runs as markers, exactly like HBTrade.pastRunMarkers but account-less: an entry arrow + exit circle
   per traded run, else a grey flag where it would have fired (08:30 ET, no legs carry a timestamp). Today's run is
   left to the live overlay (paperMarkers), like the bot's. Only markers in [from, to) are kept. */
function paperRunMarkers(runs, { tick, P, from, to, today }) {
  const out = [], inRange = (ms) => Number.isFinite(ms) && ms >= from && ms < to;
  for (const run of Array.isArray(runs) ? runs : []) {
    if (!isObj(run) || typeof run.date !== 'string' || run.date === today) continue;
    const id = `paperh:${run.date}`, tip = paperRunTip(run, tick);
    const e = isObj(run.entry) ? run.entry : null, x = isObj(run.exit) ? run.exit : null;
    if (e && e.price != null && Number.isFinite(e.ts)) {
      const buy = e.side === 'Buy';
      if (inRange(e.ts)) out.push({ id: `${id}:e`, ms: e.ts, price: e.price, position: buy ? 'atPriceBottom' : 'atPriceTop',
        shape: buy ? 'arrowUp' : 'arrowDown', color: P.warn, text: '', tip });
      if (x && x.price != null && inRange(x.ts)) {
        const v = run.pnl_usd;
        out.push({ id: `${id}:x`, ms: x.ts, price: x.price, position: 'atPriceMiddle', shape: 'circle',
          color: v == null ? P.warn : v >= 0 ? P.up : P.down, text: '', tip });
      }
      continue;
    }
    const ms = etMs(run.date, PAPER_EVENT_TIME);
    if (inRange(ms)) out.push({ id: `${id}:f`, ms, position: 'aboveBar', shape: 'square', size: 0.5, color: GREY, text: '', tip });
  }
  return out.sort((a, b) => a.ms - b.ms);
}

/* ---- the stats line under the badge: "Paper 3 · WR 67% · avg +$203 | Backtest 21–24: 76 · WR 68% · avg +$296" ---- */
const wrPct = (wr) => (wr == null || !Number.isFinite(wr) ? '—' : `${Math.round(wr)}%`);
/* "2021-2024" -> "21–24"; anything else (a window the server hasn't computed yet) verbatim. */
function shortWindow(w) {
  const m = /^(\d{4})-(\d{4})$/.exec(String(w || ''));
  return m ? `${m[1].slice(2)}–${m[2].slice(2)}` : String(w || '');
}
function paperSideText(label, s) {
  return isObj(s) ? `${label} ${s.n ?? 0} · WR ${wrPct(s.wr)} · avg ${usd(s.avg) ?? '—'}` : null;
}
/* {paper: {n, wr, avg, net}, backtest: {window, n, wr, avg, net} | null} (GET /api/paper/history's `stats`) -> the
   one-line text; '' with nothing to show. No backtest yet (still computing): the paper side alone. */
function paperStatsText(stats) {
  if (!isObj(stats)) return '';
  return [paperSideText('Paper', stats.paper), isObj(stats.backtest) ? paperSideText(`Backtest ${shortWindow(stats.backtest.window)}:`, stats.backtest) : null]
    .filter(Boolean).join(' | ');
}

/* ---- the Kill ---- */
/* The confirm: "Kill NQ 9:30 Straddle" over "Cancel its orders and flatten its NQ position on …047. The desk stays
   armed for other strategies." with its accounts (DEMO/LIVE). `accounts`: every account the desk's kill acts on. */
function killConfirm(key, s, state) {
  const ids = algoAccounts(s), list = accountsOf(state);
  // an account the desk does not list: '?' (fix round 1, M1) -- never shown as DEMO
  const rows = ids.map((id) => { const a = list.find((x) => x.id === id); return { id, label: a ? a.label : id, env: a ? a.env : '?' }; });
  const title = `Kill ${algoName(key)}`, who = ids.map((id) => whoOf(state, id)).join(', ');
  const rest = `cancel its orders and flatten its ${rootOf(s && s.symbol)} position on ${who}. The desk stays armed for other strategies.`;
  return { title, note: rest[0].toUpperCase() + rest.slice(1), text: `${title} — ${rest}`, rows, accounts: ids,
    live: rows.some((r) => r.env === 'live') };
}
/* Why the Kill may not go out now, or null: every account of the bot must be on the desk's list and every LIVE one
   armed this session. An account the desk does not list fails CLOSED (fix round 1, M1). */
function killBlock(state, ids, liveConfirmed) {
  const armed = liveConfirmed instanceof Set ? liveConfirmed : new Set(liveConfirmed || []), list = accountsOf(state);
  if (!ids || !ids.length) return 'This algo has no accounts on the desk — nothing sent';
  for (const id of ids) {
    const a = list.find((x) => x.id === id);
    if (!a) return `Account ${id} is not on the desk's list — nothing sent`;
    if (a.env === 'live' && !armed.has(id)) return unarmedLiveMessage(a);
  }
  return null;
}
/* The desk's answer never carries `sold` (engine._kill_one keeps only ok / acted / actions): a sale is its
   "market Sell 1: ok" action (fix round 1, I1). */
function killSold(actions) { return Array.isArray(actions) && actions.some((x) => /^market (Buy|Sell) \d+: ok$/.test(String(x))); }
/* One toast per account from POST bot-kill: a "check it" (the desk left the stops working) is a warning, never a
   success; a kill still waiting on the broker's acks is a warning too. */
function killToasts(status, data, state) {
  const label = (id) => { const a = accountsOf(state).find((x) => x.id === id); return a ? short(a) : id; };
  if (!isObj(data) || !isObj(data.results) || (!Object.keys(data.results).length && data.error)) {
    const d = data && (data.detail ?? data.error);
    return [{ tone: 'err', text: typeof d === 'string' && d ? d : `desk error (HTTP ${status})` }];
  }
  return Object.entries(data.results).map(([id, r]) => {
    const o = isObj(r) ? r : {}, acts = Array.isArray(o.actions) ? o.actions.map(String) : [];
    const check = acts.find((x) => /check it/i.test(x));
    if (check) return { tone: 'warn', text: `${label(id)} · CHECK IT — ${check.replace(/^check it\s*—\s*/i, '')}` };
    if (!o.ok) return { tone: 'err', text: `${label(id)} · kill failed — ${o.error || acts.join('; ') || 'refused'}` };
    if (o.pending) return { tone: 'warn', text: `${label(id)} · kill pending — ${o.note || 'waiting on the broker'}` };
    if (killSold(acts)) return { tone: 'ok', text: `${label(id)} · killed — position flattened` };
    if (o.acted) return { tone: 'ok', text: `${label(id)} · killed — its orders cancelled` };
    if (o.note) return { tone: 'ok', text: `${label(id)} · ${o.note}` };
    // the done path: only its leftover orders were cancelled (never a market order)
    return { tone: 'ok', text: `${label(id)} · killed — ${acts.length ? 'its leftover orders cancelled' : 'nothing was working'}` };
  });
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

/* ---- the PAPER account (2026-09-27 accounts/paper plan, Task 2) ----
   The chart service's own paper book (paperbook.py) is one more account the page trades exactly like a desk one.
   It joins the desk's state as the page sees it (withPaper), so every existing path -- modes, the LIVE-arm rules
   (it is never LIVE), lines, markers, the confirm dialog, the bottom panel -- treats it as an account; only the
   SEND is split (splitSend / routeSend): its part goes to POST /api/paper/{action} through HBPaperClient, never to
   the desk. It has no separate switch of its own: like any account it needs the desk's state (a desk that is down or
   has chart trading off stops PAPER too -- fail closed, one rule for every account). */
const PAPER_ID = 'paper';
/* Task 2b: the user makes more paper accounts -- "paper" (the built-in first one) or "paper-<n>". Never a colon, so a
   paper ACCOUNT id can never be read as a paper ALGO key ("paper:<strategy>", isPaperAlgo). */
const PAPER_ID_RE = /^paper(?:-[1-9][0-9]{0,5})?$/;
function isPaperId(id) { return typeof id === 'string' && PAPER_ID_RE.test(id); }
/* The desk's state with the paper accounts appended (an array, or one account); the state itself (null while the
   desk is down), untouched, when there is none. Only paper ids join, each once; never mutates an argument. */
function withPaper(state, paperAccts) {
  const list = (Array.isArray(paperAccts) ? paperAccts : [paperAccts])
    .filter((a, i, all) => isObj(a) && isPaperId(a.id) && all.findIndex((b) => isObj(b) && b.id === a.id) === i);
  if (!state || !list.length) return state;
  const desk = accountsOf(state).filter((a) => a && !isPaperId(a.id));   // the desk never lists one; never twice
  return { ...state, accounts: [...desk, ...list] };
}
/* One page action split by where each account lives: {desk, paper}, each a body or null. The same client_id goes to
   both (each side de-duplicates on its own). A Kill is the desk's alone; an unknown shape goes to the desk unchanged
   (it refuses what it does not know). */
function splitSend(action, body) {
  if (!isObj(body) || action === 'bot-kill') return { desk: isObj(body) ? body : null, paper: null };
  if (Array.isArray(body.accounts)) {
    const p = body.accounts.filter(isPaperId), d = body.accounts.filter((id) => !isPaperId(id));
    return { desk: d.length ? { ...body, accounts: d } : null, paper: p.length ? { ...body, accounts: p } : null };
  }
  if (isPaperId(body.account)) return { desk: null, paper: body };
  return { desk: body, paper: null };
}
/* Send one action through `send.desk(action, body)` and `send.paper(action, body)` by splitSend: a PAPER-only action
   never calls send.desk, a desk-only one never calls send.paper. Resolves when both parts have answered. */
function routeSend(action, body, send) {
  const parts = splitSend(action, body), out = [];
  if (parts.desk) out.push(Promise.resolve().then(() => send.desk(action, parts.desk)));
  if (parts.paper) out.push(Promise.resolve().then(() => send.paper(action, parts.paper)));
  return Promise.all(out);
}

const api = { PREFS_KEY, QUOTE_STALE_MS, BOT_NAMES, parsePrefs, prefsText, oneClickKey, short, rootOf, orderPrice, isPending, abbr, inferType, menuText,
  roundTick, bracket, orderBody, clientId, tradeMode, quoteView, usd, money, pnl, rrText, linesFor, linePnl, lineLabel,
  lineText, lineTitle, lineColor, canDrag, withPrice, exitKinds, exitKindAt, exitRefusal, EXIT_DRAG_PX, pastClick, pendingMoveError, exitGhost, exitDropError, expectedNet, exitsBody, exitsTitle, orderTitle, confirmOrder, actionTitle, resultToasts, fillText, fillMarkers, execArrow, botName, positionRows, orderRows, fillRows, accountRows, etTime, diffRows,
  algoName, algoLabel, algoChoices, algoAccounts, botPill, botToday, algoOverlay, etMs, pastRunMarkers, nearestTip, historySig,
  killConfirm, killToasts, killBlock, killSold,
  enterConfirms, wireSend, sendingSide, symbolChangeTrade, resolveConfirmedAccounts, armedTicked, unarmedLiveMessage, freshQuote,
  needsQuoteForBracket, refuseIfMarketable, cellTrade, loadedTrade, cellAlgo, tradeBits, templateTrade, algoForRoot,
  migrateTicked, deskGate, armedMode, replayGuard, legsWithin, lineAccounts, accountChips, acctTick, hiddenCellsLoaded,
  NO_ACCOUNTS, SYMBOL_CHANGE_ACCOUNTS_CLEARED, liveIds, liveDroppedMessage, envChip, algoBookings, algoForAccount,
  accountsForAlgo, algoTickAccounts, accountPickRows, deskStatusText,
  verifyLoaded, verifyCells, nextUnverified, unverifiedMode, CHECKING_ACCOUNTS, REPLAY_ENDED, replayHaltGuard,
  replayEndPatch, sendsWithoutConfirm, chartWhy,
  PANEL_QTY_MAX, GTC_WARN, exitTriple, qtyFromRisk, exitSideError, panelOrder, sendLabel,
  parseQty, parseUsd, parseDecimal, roundTickDir, riskTicks,
  paperKey, isPaperAlgo, paperStrategyId, paperStrategiesMap, paperPill, paperToday, paperLabel, paperLines,
  paperMarkers, paperOverlay, paperRunMarkers, paperStatsText, PAPER_ID, isPaperId, withPaper, splitSend, routeSend };
if (typeof window !== 'undefined') window.HBTrade = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
