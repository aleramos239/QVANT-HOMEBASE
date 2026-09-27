/* Homebase Charts — the chart service's paper side as the page sees it. NEVER a desk call: nothing in this file
   names the desk or its client, and every request goes to /api/paper/* (tests/js/paperclient.test.mjs pins it).
   The paper (forward-test) strategies (2026-09-27 paper-forward-test plan, Task 2):
     - the static list, GET /api/paper/strategies (id, name, root, params) -- fetched once, cached, retried on
       failure only;
     - the live /ws {"type":"paper", ...} push, kept as the latest message per strategy id;
     - a strategy's past runs + stats, GET /api/paper/history?strategy=<id> -- cached like the desk client's
       bot history (60 s, or sooner on a new ET day or a changed `current` message).
   The paper ACCOUNTS (2026-09-27 accounts/paper plan, Task 2; several since Task 2b), the service's own paper
   books (paperbook.py):
     - the /ws {"type":"paperbook", accounts, limits} push, kept as the latest account views (accounts());
     - createAccount(name, startBalance): POST /api/paper/accounts/create -> {status, data};
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
const PAPER_ID_RE = /^paper(?:-[1-9][0-9]{0,5})?$/;   // HBTrade.isPaperId's rule (this file loads on its own)
const book = { accounts: [], limits: null };
const fillSubs = new Set();
const ours = new Set();   // "<account>:<order id>" this page placed: their fills are announced (onFill)
let seenFills = null;     // "<account>:<fill id>" of the last push (null: none yet -- the first announces nothing)
/* The paper accounts in the desk's account shape ([] before the service has sent any). */
function accounts() { return book.accounts; }
function limits() { return book.limits; }
function onFill(fn) { fillSubs.add(fn); return () => fillSubs.delete(fn); }
/* A /ws {"type":"paperbook", accounts, limits} push: the latest views; announces fills of our own orders it adds
   ({...fill, account}). Anything that is not a paper account is dropped. */
function onBook(m) {
  const list = (m && Array.isArray(m.accounts) ? m.accounts : [])
    .filter((a) => a && typeof a === 'object' && typeof a.id === 'string' && PAPER_ID_RE.test(a.id));
  const fresh = [], seen = new Set();
  for (const a of list) {
    for (const f of Array.isArray(a.fills) ? a.fills : []) {
      if (!f) continue;
      const k = `${a.id}:${f.id}`;
      seen.add(k);
      if (seenFills && !seenFills.has(k) && ours.has(`${a.id}:${f.order_id}`)) fresh.push({ ...f, account: a.id });
    }
  }
  seenFills = seen;
  book.accounts = list;
  book.limits = (m && m.limits) || null;
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
  if (data && data.results) for (const [id, r] of Object.entries(data.results)) if (r && r.ok && r.order_id) ours.add(`${id}:${r.order_id}`);
  return { status, data };
}
/* Task 2b: a new paper account -> {status, data} (data.account on success, data.detail on a refusal). */
async function createAccount(name, startBalance) {
  let status = 0, data = null;
  try {
    const r = await fetch('/api/paper/accounts/create', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name, start_balance: startBalance }) });
    status = r.status;
    try { data = await r.json(); } catch (_) { data = null; }
  } catch (_) { data = { detail: 'chart service unreachable' }; }
  return { status, data };
}

window.HBPaperClient = { strategies, state, on, onMessage, history, accounts, limits, onBook, onFill, send, createAccount };
})();
