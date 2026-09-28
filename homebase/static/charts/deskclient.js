/* Homebase Charts — the desk as the page sees it:
     - the latest state and quotes from the chart service's /ws ({"type": "desk"} and
       {"type": "quote"} messages);
     - the viewer's trade preferences;
     - the actions sent to POST /api/desk/{action};
     - a bot's past runs (GET /api/desk/bot-history), cached per strategy;
     - the toasts.
   Browser only; the logic lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;
const M = window.HBSpring;   // the feel pass (2026-09-28): toast()'s own materialize()/dematerialize()
const TOAST_MS = { ok: 5000, err: 10000, warn: 0 }, TOAST_MAX = 5;   // 0: a warning ("check it") stays until dismissed
const HISTORY_TTL = 60000, HISTORY_RETRY = { 503: 30000, other: 60000 };
const desk = { state: null, down: 'connecting to the desk', quotes: {}, prefs: loadPrefs() };
const subs = new Set();
const ours = new Set();   // order ids this page placed: their fills get a toast (ruling S3)
// fast-paper: a market order can fill before its POST's answer names it -- a fill of an order not (yet) ours waits
// here (the last UNCLAIMED_MAX, oldest first) for send() to claim it: one toast when the answer lands, never two
const UNCLAIMED_MAX = 50;
const unclaimed = [];
const CLAIMS = ['order', 'flatten', 'reverse'];   // answers naming an order this page just SENT: only they claim
let queued = null;

function loadPrefs() { try { return T.parsePrefs(localStorage.getItem(T.PREFS_KEY)); } catch (_) { return T.parsePrefs(null); } }
function setPrefs(patch) {
  desk.prefs = T.parsePrefs(JSON.stringify({ ...desk.prefs, ...patch }));
  try { localStorage.setItem(T.PREFS_KEY, T.prefsText(desk.prefs)); } catch (_) { /* storage off: this session only */ }
  emit('prefs');
}
function on(fn) { subs.add(fn); return () => subs.delete(fn); }
/* Coalesced to one call per frame: a burst of account events redraws once. */
function emit(why) {
  if (queued) { queued.add(why); return; }
  queued = new Set([why]);
  requestAnimationFrame(() => {
    const w = queued;
    queued = null;
    for (const fn of [...subs]) { try { fn(w); } catch (e) { console.error(e); } }
  });
}

function onMessage(m) {
  if (m.type === 'quote') {
    desk.quotes[m.root] = { bid: m.bid, ask: m.ask, last: m.last, ts_ms: m.ts_ms };
    emit('quote');
    return;
  }
  if (m.down !== undefined) { desk.state = null; desk.down = m.down; emit('state'); return; }
  const d = m.data;
  if (m.event === 'state') { desk.state = d; desk.down = null; }
  else if (!desk.state) return;
  else if (m.event === 'account') {
    const list = desk.state.accounts || (desk.state.accounts = []), i = list.findIndex((a) => a.id === d.id);
    if (i >= 0) list[i] = d; else list.push(d);
  } else if (m.event === 'bot') desk.state.bot = d;
  else if (m.event === 'fill') {
    if (d && d.fill) {
      if (ours.has(String(d.fill.order_id))) fillToast(d);
      else if (unclaimed.push(d) > UNCLAIMED_MAX) unclaimed.shift();
    }
  } else return;   // result: this page's own answers come back on its POST (ruling S3)
  emit(m.event);
}
function fillToast(d) { toast('ok', T.fillText(d, desk.state, tickFor(T.rootOf(d.fill.symbol)))); }
/* An order this page placed: its fills get a toast from now on -- and at once any that landed before its answer. */
function claim(id) {
  ours.add(id);
  for (let i = 0; i < unclaimed.length;) {
    if (String(unclaimed[i].fill.order_id) === id) fillToast(unclaimed.splice(i, 1)[0]);
    else i++;
  }
}
function tickFor(root) {
  const c = (window.HBCharts ? window.HBCharts.cells : []).find((x) => x.shown && x.shown.root === root);
  return c ? c.tick : 0;
}

async function send(action, body) {
  let status = 0, data = null;
  try {
    const r = await fetch(`/api/desk/${action}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    status = r.status;
    try { data = await r.json(); } catch (_) { data = null; }
  } catch (_) { data = { detail: 'chart service unreachable' }; }
  // a modify / cancel answer names an order that already existed -- maybe another page's, with fills of its own
  // held here: from now on it is ours (as before), but it never claims what was held
  if (data && data.results) for (const r of Object.values(data.results)) {
    if (!r || !r.ok || !r.order_id) continue;
    if (CLAIMS.includes(action)) claim(String(r.order_id)); else ours.add(String(r.order_id));
  }
  for (const t of T.resultToasts(action, status, data, desk.state)) toast(t.tone, t.text);
  return data;
}

/* ---- a bot's past runs: cached 60 s per strategy; fetched again on a new (ET) day, or as soon as the bot view shows
   an exit fill, a skip or a kill (HBTrade.historySig). The desk answers 503 from 09:29:00 to 09:30:30 ET (no journal
   read near the fire): kept what we had, asked again 30 s later. A fetch that lands emits 'history'. ---- */
const hist = new Map();   // strategy -> {data, at, day, sig, busy, retryAt}
const etDay = (ms) => new Date(ms).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
function stratView(name) {
  const b = desk.state && desk.state.bot;
  return b && b.strategies ? b.strategies[name] : null;
}
/* {strategy, symbol, runs} or null (not fetched yet); starts a fetch when the cached copy is due. */
function botHistory(name) {
  if (typeof name !== 'string' || !name) return null;
  let e = hist.get(name);
  if (!e) { e = { data: null, at: 0, day: '', sig: '', busy: false, retryAt: 0 }; hist.set(name, e); }
  const now = Date.now(), day = etDay(now), sig = T.historySig(stratView(name));
  const due = !e.at || now - e.at >= HISTORY_TTL || e.day !== day || e.sig !== sig;
  if (due && !e.busy && !(e.retryAt > now) && desk.state) fetchHistory(name, e, day, sig);
  return e.data;
}
async function fetchHistory(name, e, day, sig) {
  e.busy = true;
  let status = 0, data = null;
  try {
    const r = await fetch(`/api/desk/bot-history?strategy=${encodeURIComponent(name)}`);
    status = r.status;
    try { data = await r.json(); } catch (_) { data = null; }
  } catch (_) { status = 0; }
  e.busy = false;
  if (status === 200 && data && Array.isArray(data.runs)) {
    Object.assign(e, { data, at: Date.now(), day, sig, retryAt: 0 });
    emit('history');
  } else {
    e.retryAt = Date.now() + (HISTORY_RETRY[status] || HISTORY_RETRY.other);
  }
}

function toast(tone, text) {
  const root = document.getElementById('toastRoot');
  if (!root) return;
  const el = document.createElement('div'), msg = document.createElement('span'), x = document.createElement('button');
  el.className = `toast ${tone}`;
  el.setAttribute('role', tone === 'ok' ? 'status' : 'alert');
  msg.textContent = text;
  x.type = 'button'; x.className = 'toast-x'; x.setAttribute('aria-label', 'Dismiss');
  x.innerHTML = window.HBIcons.x;   // our own static SVG string
  x.onclick = () => M.dematerialize(el, () => el.remove());
  el.append(msg, x);
  root.prepend(el);
  M.materialize(el, 'right top');   // the toasts column is pinned top-right (charts.css .toasts)
  // Eviction now animates out (dematerialize), so a removal is no longer synchronous the way `.remove()` was
  // -- re-checking `root.children.length` in a `while` here would spin forever (it never shrinks within this
  // same tick). Decide every victim from ONE snapshot instead: oldest-first, a "check it" warning only once
  // nothing else is left to take its place -- same rule as before, just computed all at once, not spun in a
  // loop over a count that dematerialize will only actually shrink later.
  const excess = root.children.length - TOAST_MAX;
  if (excess > 0) {
    const oldestFirst = [...root.children].reverse();
    const victims = [...oldestFirst.filter((n) => !n.classList.contains('warn')), ...oldestFirst.filter((n) => n.classList.contains('warn'))]
      .slice(0, excess);
    for (const v of victims) M.dematerialize(v, () => v.remove());
  }
  const ms = TOAST_MS[tone] ?? 6000;
  if (ms > 0) setTimeout(() => M.dematerialize(el, () => el.remove()), ms);
}

/* The desk's state as the page sees it: the paper accounts (the chart service's own paper books, HBPaperClient)
   appended to the desk's accounts (2026-09-27 accounts/paper plan, Task 2) -- null while the desk is down. `send`
   below stays the desk's alone: HBTradeUI splits a PAPER part off to HBPaperClient before anything reaches it. */
function merged() { return T.withPaper(desk.state, window.HBPaperClient ? window.HBPaperClient.accounts() : []); }

window.HBDeskClient = {
  get state() { return merged(); }, get down() { return desk.down; }, quotes: desk.quotes,
  get prefs() { return desk.prefs; }, setPrefs, on, onMessage, send, toast, botHistory,
  mode: (cellTrade) => T.tradeMode({ state: merged(), down: desk.down }, cellTrade),   // ONE chart's mode, from its own {accounts}
  gate: () => T.deskGate(desk),                        // the desk-level half alone (null: up and on)
  bookChanged: () => emit('account'),                  // the PAPER account changed (app.js, on a /ws paperbook push)
};
})();
