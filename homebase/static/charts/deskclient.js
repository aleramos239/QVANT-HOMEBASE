/* Homebase Charts — the desk as the page sees it:
     - the latest state and quotes from the chart service's /ws ({"type": "desk"} and
       {"type": "quote"} messages);
     - the viewer's trade preferences;
     - the actions sent to POST /api/desk/{action};
     - the toasts.
   Browser only; the logic lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;
const TOAST_MS = { ok: 5000, err: 10000 }, TOAST_MAX = 5;
const desk = { state: null, down: 'connecting to the desk', quotes: {}, prefs: loadPrefs() };
const subs = new Set();
const ours = new Set();   // order ids this page placed: their fills get a toast (ruling S3)
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
    if (d && d.fill && ours.has(String(d.fill.order_id))) toast('ok', T.fillText(d, desk.state, tickFor(T.rootOf(d.fill.symbol))));
  } else return;   // result: this page's own answers come back on its POST (ruling S3)
  emit(m.event);
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
  if (data && data.results) for (const r of Object.values(data.results)) if (r && r.ok && r.order_id) ours.add(String(r.order_id));
  for (const t of T.resultToasts(action, status, data, desk.state)) toast(t.tone, t.text);
  return data;
}

function toast(tone, text) {
  const root = document.getElementById('toastRoot');
  if (!root) return;
  const el = document.createElement('div'), msg = document.createElement('span'), x = document.createElement('button');
  el.className = `toast ${tone}`;
  el.setAttribute('role', tone === 'err' ? 'alert' : 'status');
  msg.textContent = text;
  x.type = 'button'; x.className = 'toast-x'; x.setAttribute('aria-label', 'Dismiss');
  x.innerHTML = window.HBIcons.x;   // our own static SVG string
  x.onclick = () => el.remove();
  el.append(msg, x);
  root.prepend(el);
  while (root.children.length > TOAST_MAX) root.lastChild.remove();
  setTimeout(() => el.remove(), TOAST_MS[tone] || 6000);
}

window.HBDeskClient = {
  get state() { return desk.state; }, get down() { return desk.down; }, quotes: desk.quotes,
  get prefs() { return desk.prefs; }, setPrefs, on, onMessage, send, toast,
  mode: () => T.tradeMode(desk, desk.prefs),
};
})();
