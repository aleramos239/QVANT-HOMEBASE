/* Homebase Charts — the chart service's paper side as the page sees it. NEVER a desk call: nothing in this file
   names the desk or its client, and every request goes to /api/paper/* (tests/js/paperclient.test.mjs pins it).
   The paper (forward-test) strategies (2026-09-27 paper-forward-test plan, Task 2):
     - the static list, GET /api/paper/strategies (id, name, root, params) -- fetched once, cached, retried on
       failure only;
     - the live /ws {"type":"paper", ...} push, kept as the latest message per strategy id;
     - a strategy's past runs + stats, GET /api/paper/history?strategy=<id> -- cached like the desk client's
       bot history (60 s, or sooner on a new ET day or a changed `current` message).
   The PAPER account (2026-09-27 accounts/paper plan, Task 2), the service's own paper book (paperbook.py):
     - the /ws {"type":"paperbook", account, limits} push, kept as the latest account view (account());
     - send(action, body): POST /api/paper/{action} for order | modify | cancel | cancel-symbol | flatten | reverse
       only -> {status, data}; the caller (HBTradeUI) routes a send here by HBTrade.routeSend and owns the toasts;
     - onFill(fn): a new fill of an order this page placed (like the desk's fill toast rule).
   Browser only; the logic (the pill, lines, markers, stats text, the split) lives in HBTrade. */
(() => {
'use strict';
const HISTORY_TTL = 60000, HISTORY_RETRY = { 503: 30000, other: 60000 };
const STRATS_RETRY_MS = 30000;

const data = { strategies: [], current: {} };
const subs = new Set();
let stratsBusy = false, stratsRetryAt = 0;
const hist = new Map();   // strategy id -> {data, at, day, sig, busy, retryAt}

function on(fn) { subs.add(fn); return () => subs.delete(fn); }
function emit() { for (const fn of [...subs]) { try { fn(); } catch (e) { console.error(e); } } }

/* The static list: fetched once and cached forever (it never changes at runtime); a failure retries in 30 s. */
function strategies() {
  if (!data.strategies.length && !stratsBusy && Date.now() >= stratsRetryAt) fetchStrategies();
  return data.strategies;
}
async function fetchStrategies() {
  stratsBusy = true;
  try {
    const r = await fetch('/api/paper/strategies');
    if (r.ok) {
      const list = await r.json();
      if (Array.isArray(list) && list.length) { data.strategies = list; emit(); }
    }
  } catch (_) { /* retried below */ }
  stratsBusy = false;
  if (!data.strategies.length) stratsRetryAt = Date.now() + STRATS_RETRY_MS;
}

/* A /ws {"type":"paper", strategy, ...} push: kept as the latest message for that strategy id. */
function onMessage(m) {
  if (!m || typeof m.strategy !== 'string' || !m.strategy) return;
  data.current = { ...data.current, [m.strategy]: m };
  emit();
}

/* {strategies, current}, exactly HBTrade.paperOverlay's `paper` shape. */
function state() { return { strategies: strategies(), current: data.current }; }

const etDay = (ms) => new Date(ms).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
/* {runs, stats} or null (not fetched yet); starts a fetch when the cached copy is due -- a new ET day, or the
   latest /ws message for this strategy changed since the last fetch (a new finished run, most likely). */
function history(id) {
  if (typeof id !== 'string' || !id) return null;
  let e = hist.get(id);
  if (!e) { e = { data: null, at: 0, day: '', sig: '', busy: false, retryAt: 0 }; hist.set(id, e); }
  const now = Date.now(), day = etDay(now), sig = JSON.stringify(data.current[id] || null);
  const due = !e.at || now - e.at >= HISTORY_TTL || e.day !== day || e.sig !== sig;
  if (due && !e.busy && !(e.retryAt > now)) fetchHistory(id, e, day, sig);
  return e.data;
}
async function fetchHistory(id, e, day, sig) {
  e.busy = true;
  let status = 0, body = null;
  try {
    const r = await fetch(`/api/paper/history?strategy=${encodeURIComponent(id)}`);
    status = r.status;
    try { body = await r.json(); } catch (_) { body = null; }
  } catch (_) { status = 0; }
  e.busy = false;
  if (status === 200 && body && Array.isArray(body.runs)) {
    Object.assign(e, { data: body, at: Date.now(), day, sig, retryAt: 0 });
    emit();
  } else {
    e.retryAt = Date.now() + (HISTORY_RETRY[status] || HISTORY_RETRY.other);
  }
}

/* ---- the PAPER account ---- */
const BOOK_ACTIONS = ['order', 'modify', 'cancel', 'cancel-symbol', 'flatten', 'reverse'];
const book = { account: null, limits: null };
const fillSubs = new Set();
const ours = new Set();   // paper order ids this page placed: their fills are announced (onFill)
let seenFills = null;     // fill ids of the last view (null: none yet -- the first view announces nothing)
/* The PAPER account in the desk's account shape, or null before the service has sent one. */
function account() { return book.account; }
function limits() { return book.limits; }
function onFill(fn) { fillSubs.add(fn); return () => fillSubs.delete(fn); }
/* A /ws {"type":"paperbook", account, limits} push: the latest view; announces fills of our own orders it adds. */
function onBook(m) {
  const a = m && m.account;
  if (!a || typeof a !== 'object' || a.id !== 'paper') return;
  const list = Array.isArray(a.fills) ? a.fills : [], fresh = [];
  if (seenFills) for (const f of list) if (f && !seenFills.has(String(f.id)) && ours.has(String(f.order_id))) fresh.push(f);
  seenFills = new Set(list.map((f) => String(f && f.id)));
  book.account = a;
  book.limits = m.limits || null;
  for (const f of fresh) for (const fn of [...fillSubs]) { try { fn(f); } catch (e) { console.error(e); } }
}
/* POST /api/paper/{action} -> {status, data}; anything but the six book actions (a Kill) is refused here, unsent. */
async function send(action, body) {
  if (!BOOK_ACTIONS.includes(action)) return { status: 0, data: { detail: `PAPER has no ${action}` } };
  let status = 0, data = null;
  try {
    const r = await fetch(`/api/paper/${action}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    status = r.status;
    try { data = await r.json(); } catch (_) { data = null; }
  } catch (_) { data = { detail: 'chart service unreachable' }; }
  if (data && data.results) for (const r of Object.values(data.results)) if (r && r.ok && r.order_id) ours.add(String(r.order_id));
  return { status, data };
}

window.HBPaperClient = { strategies, state, on, onMessage, history, account, limits, onBook, onFill, send };
})();
