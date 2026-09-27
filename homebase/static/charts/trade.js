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

/* ---- preferences (per viewer: localStorage hb_trade_prefs) ---- */
function parsePrefs(text) {
  let o = null;
  try { o = JSON.parse(text); } catch (_) { o = null; }
  if (!o || typeof o !== 'object' || Array.isArray(o)) o = {};
  const ticked = Array.isArray(o.ticked)
    ? [...new Set(o.ticked.filter((x) => typeof x === 'string' && x.length >= 1 && x.length <= 64))].slice(0, 20) : [];
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
function orderBody({ clientId, accounts, root, side, qty, type, price = null, sl = null, tp = null }) {
  const b = { client_id: clientId, accounts: [...accounts], root, side, qty, type };
  if (type !== 'Market') b.price = price;
  if (sl != null) b.sl_price = sl;
  if (tp != null) b.tp_price = tp;
  return b;
}
let seq = 0;
/* One per user action (the desk de-duplicates on it: a retry of the same action reuses it). */
function clientId(now = Date.now()) { seq = (seq + 1) % 1e6; return `c${now.toString(36)}-${seq.toString(36)}-${Math.random().toString(36).slice(2, 8)}`; }

/* ---- what the page may do (ruling S7) ---- */
function tradeMode(desk, prefs) {
  if (!desk || !desk.state) return { mode: 'down', reason: (desk && desk.down) || 'connecting to the desk', accounts: [] };
  const st = desk.state;
  if (!st.enabled) return { mode: 'off', reason: 'Chart trading is off on the desk', accounts: [] };
  const ticked = new Set(prefs.ticked);
  const accounts = accountsOf(st).filter((a) => ticked.has(a.id) && a.tradable).map((a) => a.id);
  if (!accounts.length) return { mode: 'none', reason: ticked.size ? 'No ticked account can trade right now' : 'Tick an account in the Trade menu', accounts };
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
   the ticked accounts in `root`. A bot's own orders (owner set) are drawn by the bot overlay instead. */
function linesFor(state, root, prefs) {
  if (!state) return [];
  const ticked = new Set(prefs.ticked), groups = new Map();
  const add = (key, base, leg) => {
    let g = groups.get(key);
    if (!g) { g = { key, ...base, qty: 0, legs: [] }; groups.set(key, g); }
    g.qty += leg.qty;
    g.legs.push(leg);
  };
  for (const a of accountsOf(state)) {
    if (!ticked.has(a.id)) continue;
    const who = short(a), pos = (a.positions || []).filter((p) => p.root === root && p.net);
    for (const p of pos) {
      const s = p.net > 0 ? 1 : -1;
      add(`position|${s}|${p.avg_price}`, { kind: 'position', side: s > 0 ? 'Buy' : 'Sell', price: p.avg_price },
        { account: a.id, who, qty: Math.abs(p.net), avg: p.avg_price, s, pv: p.point_value ?? null, symbol: p.symbol });
    }
    for (const o of a.orders || []) {
      const at = orderPrice(o);
      if (o.owner || at == null || rootOf(o.symbol) !== root) continue;
      const p = pos.find((x) => x.symbol === o.symbol);
      const exit = !!p && ((p.net > 0 && o.side === 'Sell') || (p.net < 0 && o.side === 'Buy'));
      const kind = !exit ? 'order' : /stop/i.test(o.type) ? 'sl' : /limit/i.test(o.type) ? 'tp' : 'order';
      add(`${kind}|${o.side}|${o.type}|${at}`, { kind, side: o.side, type: o.type, price: at },
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
  return `${g.side.toUpperCase()} ${abbr(g.type)} ${g.qty}`;
}
function lineText(g, last) {
  if (g.kind === 'order') return `${lineLabel(g)} · ${whoText(g)}`;
  return [lineLabel(g), usd(linePnl(g, last)), whoText(g)].filter(Boolean).join(' · ');
}
function lineColor(g, P) {
  if (g.kind === 'position') return g.side === 'Buy' ? P.up : P.down;
  if (g.kind === 'sl') return P.down;
  if (g.kind === 'tp') return P.up;
  return g.side === 'Buy' ? P.accent : P.down;
}
const withPrice = (g, price) => ({ ...g, price });

/* ---- confirm dialog ---- */
function orderTitle(b, tick) {
  return `${b.side} ${b.qty} ${b.root} ${b.type === 'Market' ? 'at market' : `${b.type} @ ${Cat.fmtPrice(b.price, tick)}`}`;
}
function confirmOrder(b, state, quote, pv, tick) {
  const accts = accountsOf(state).filter((a) => b.accounts.includes(a.id));
  const ref = b.type === 'Market' ? (quote ? quote.last ?? null : null) : b.price, s = b.side === 'Buy' ? 1 : -1;
  const risk = b.sl_price != null ? pnl(ref, b.sl_price, s, b.qty, pv) : null;
  const reward = b.tp_price != null ? pnl(ref, b.tp_price, s, b.qty, pv) : null;
  const bits = [];
  if (b.sl_price != null) bits.push(`SL ${Cat.fmtPrice(b.sl_price, tick)}${risk != null ? ` ${usd(risk)}` : ''}`);
  if (b.tp_price != null) bits.push(`TP ${Cat.fmtPrice(b.tp_price, tick)}${reward != null ? ` ${usd(reward)}` : ''}`);
  const rr = ref != null && b.sl_price != null && b.tp_price != null ? rrText(Math.abs(ref - b.sl_price), Math.abs(b.tp_price - ref)) : null;
  if (rr) bits.push(`RR ${rr}`);
  return { title: orderTitle(b, tick), accounts: accts.map((a) => ({ id: a.id, label: a.label, env: a.env })),
    bracket: bits.join(' · '), each: accts.length > 1 ? `each of ${accts.length} accounts` : '', live: accts.some((a) => a.env === 'live') };
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
function fillMarkers(state, root, prefs, P) {
  const ticked = new Set(prefs.ticked), out = [];
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
  lineText, lineColor, withPrice, orderTitle, confirmOrder, actionTitle, resultToasts, fillText, fillMarkers, botName,
  botsFor, positionRows, orderRows, fillRows, accountRows, etTime, diffRows,
  enterConfirms, resolveConfirmedAccounts, armedTicked, unarmedLiveMessage, freshQuote,
  needsQuoteForBracket, refuseIfMarketable };
if (typeof window !== 'undefined') window.HBTrade = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
