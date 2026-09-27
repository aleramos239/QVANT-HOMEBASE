/* Homebase Charts — the paper (forward-test) strategies as the page sees them (2026-09-27 paper-forward-test
   plan, Task 2): never an order, never a desk call.
     - the static list, GET /api/paper/strategies (id, name, root, params) -- fetched once, cached, retried on
       failure only;
     - the live /ws {"type":"paper", ...} push, kept as the latest message per strategy id;
     - a strategy's past runs + stats, GET /api/paper/history?strategy=<id> -- cached like HBDeskClient.botHistory
       (60 s, or sooner on a new ET day or a changed `current` message).
   Browser only; the logic (the pill, lines, markers, stats text) lives in HBTrade. */
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

window.HBPaperClient = { strategies, state, on, onMessage, history };
})();
