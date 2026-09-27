/* Homebase Charts — the collapsible bottom panel shared by trading and the Strategy Tester
   (ruling S15). This task wires the shell (collapse/resize/persistence) and the four trading
   tabs: Positions / Orders / Fills / Accounts, built from HBTrade's row functions against
   HBDeskClient's state. The Strategy Tester tab is added later (Task 9) through `addTab`.
   Browser only. */
(() => {
'use strict';
const T = window.HBTrade;
const STATE_KEY = 'hb_panel';
const DEFAULT_H = 260, MIN_H = 120;

const elPanel = document.getElementById('bpanel');
const elResize = document.getElementById('bpResize');
const elTabs = document.getElementById('bpTabs');
const elToggle = document.getElementById('bpToggle');
const elBody = document.getElementById('bpBody');

let page = null;
const tabs = [];             // [{id, label, render(el), onShow, onHide, btn}]
let activeId = null;
let isOpen = false;
let height = DEFAULT_H;

/* ---- persistence ({open, h, tab} in localStorage hb_panel; every access is its own try/catch) ---- */
function loadState() {
  try {
    const v = JSON.parse(localStorage.getItem(STATE_KEY) || 'null');
    return (v && typeof v === 'object') ? v : null;
  } catch (_) { return null; }
}
function saveState() {
  try { localStorage.setItem(STATE_KEY, JSON.stringify({ open: isOpen, h: height, tab: activeId })); } catch (_) { /* storage off: this session only */ }
}

/* ---- small DOM helpers (every cell by textContent) ---- */
function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
function emptyDiv(text) { const e = el('div', 'bp-empty'); e.textContent = text; return e; }
function downDiv(reason) { return emptyDiv(`Desk unreachable — ${reason || 'unknown reason'}`); }
function td(tr, text, cls) { const c = el('td', cls); c.textContent = text == null ? '' : String(text); tr.appendChild(c); return c; }
function envSpan(env) { const s = el('span', 'env' + (env === 'live' ? ' live' : '')); s.textContent = String(env || '').toUpperCase(); return s; }
function accountTd(tr, who, env) {
  const c = el('td');
  c.appendChild(document.createTextNode(who == null ? '' : String(who)));
  if (env) { c.appendChild(document.createTextNode(' ')); c.appendChild(envSpan(env)); }
  tr.appendChild(c);
}
function dotTd(tr, ok) { const c = el('td'), s = el('span', 'dot' + (ok ? ' ok' : ' bad')); c.appendChild(s); tr.appendChild(c); }
function actionTd(tr, label, onClick) {
  const c = el('td'), b = el('button', 'bp-act');
  b.type = 'button'; b.textContent = label; b.onclick = onClick;
  c.appendChild(b);
  tr.appendChild(c);
}
function table(headers, rows, buildRow) {
  const t = el('table', 'bp-table'), thead = el('thead'), htr = el('tr'), tbody = el('tbody');
  for (const h of headers) { const th = el('th', h.cls); th.textContent = h.text; htr.appendChild(th); }
  thead.appendChild(htr);
  for (const r of rows) { const tr = el('tr'); buildRow(tr, r); tbody.appendChild(tr); }
  t.append(thead, tbody);
  return t;
}

/* ---- the four trading tabs ---- */
const D = () => window.HBDeskClient;

function renderPositions(target) {
  const d = D();
  if (!d.state) { target.appendChild(downDiv(d.down)); return; }
  const rows = T.positionRows(d.state, d.quotes);
  if (!rows.length) { target.appendChild(emptyDiv('No open positions')); return; }
  target.appendChild(table(
    [{ text: 'Account' }, { text: 'Symbol' }, { text: 'Side' }, { text: 'Qty', cls: 'num' }, { text: 'Avg price', cls: 'num' },
      { text: 'Last', cls: 'num' }, { text: 'Open P&L', cls: 'num' }, { text: '' }],
    rows,
    (tr, r) => {
      accountTd(tr, r.who, r.env);
      td(tr, r.symbol);
      td(tr, r.side, r.side === 'Long' ? 'up' : 'down');
      td(tr, r.qty, 'num');
      td(tr, r.avg, 'num');
      td(tr, r.last, 'num');
      td(tr, r.pnl, 'num ' + (r.tone || ''));
      actionTd(tr, 'Close', () => { window.HBTradeUI && window.HBTradeUI.flattenAccount(r.account, r.root); });
    },
  ));
}

function renderOrders(target) {
  const d = D();
  if (!d.state) { target.appendChild(downDiv(d.down)); return; }
  const rows = T.orderRows(d.state);
  if (!rows.length) { target.appendChild(emptyDiv('No working orders')); return; }
  target.appendChild(table(
    [{ text: 'Account' }, { text: 'Symbol' }, { text: 'Side' }, { text: 'Type' }, { text: 'Qty', cls: 'num' },
      { text: 'Price', cls: 'num' }, { text: 'Status' }, { text: 'Owner' }, { text: '' }],
    rows,
    (tr, r) => {
      td(tr, r.who);
      td(tr, r.symbol);
      td(tr, r.side);
      td(tr, r.type);
      td(tr, r.qty, 'num');
      td(tr, r.price, 'num');
      td(tr, r.status);
      td(tr, r.owner);
      if (r.cancellable) actionTd(tr, 'Cancel', () => { window.HBTradeUI && window.HBTradeUI.cancelOrder(r.account, r.order_id); });
      else td(tr, '');
    },
  ));
}

function renderFills(target) {
  const d = D();
  if (!d.state) { target.appendChild(downDiv(d.down)); return; }
  const rows = T.fillRows(d.state);
  if (!rows.length) { target.appendChild(emptyDiv('No fills today')); return; }
  target.appendChild(table(
    [{ text: 'Time (ET)' }, { text: 'Account' }, { text: 'Symbol' }, { text: 'Side' }, { text: 'Qty', cls: 'num' },
      { text: 'Price', cls: 'num' }, { text: 'Owner' }],
    rows,
    (tr, r) => {
      td(tr, r.time);
      td(tr, r.who);
      td(tr, r.symbol);
      td(tr, r.side);
      td(tr, r.qty, 'num');
      td(tr, r.price, 'num');
      td(tr, r.owner);
    },
  ));
}

function renderAccounts(target) {
  const d = D();
  if (!d.state) { target.appendChild(downDiv(d.down)); return; }
  const rows = T.accountRows(d.state, d.quotes);
  if (!rows.length) { target.appendChild(emptyDiv('No accounts on the desk')); return; }
  target.appendChild(table(
    [{ text: 'Account' }, { text: 'Env' }, { text: 'Connected' }, { text: 'Broker account' }, { text: 'Balance', cls: 'num' },
      { text: 'Realized P&L', cls: 'num' }, { text: 'Open P&L', cls: 'num' }, { text: 'Strategies' }, { text: 'Status' }],
    rows,
    (tr, r) => {
      td(tr, r.who);
      const c = el('td');
      c.appendChild(envSpan(r.env));
      tr.appendChild(c);
      dotTd(tr, r.connected);
      td(tr, r.broker);
      td(tr, r.balance, 'num');
      td(tr, r.realized, 'num');
      td(tr, r.open, 'num ' + (r.openTone || ''));
      td(tr, r.strategies);
      td(tr, r.status, r.status === 'Ready' ? '' : 'down');
    },
  ));
}

/* ---- the panel shell ---- */
function renderTabsBar() { for (const t of tabs) t.btn.setAttribute('aria-selected', String(t.id === activeId)); }

function renderActive() {
  const t = tabs.find((x) => x.id === activeId);
  elBody.replaceChildren();
  if (!t) return;
  try { t.render(elBody); } catch (e) { console.error(e); }
  if (t.onShow) { try { t.onShow(); } catch (e) { console.error(e); } }
}

function applyHeight(h) {
  height = Math.max(MIN_H, Math.min(0.7 * window.innerHeight, h));
  elPanel.style.setProperty('--bp-h', `${height}px`);
}

function setOpen(v) {
  isOpen = v;
  elPanel.classList.toggle('open', isOpen);
  const label = isOpen ? 'Close the panel' : 'Open the panel';
  elToggle.setAttribute('aria-label', label);
  elToggle.title = label;
  if (isOpen) renderActive();
  else {
    const t = tabs.find((x) => x.id === activeId);
    if (t && t.onHide) { try { t.onHide(); } catch (e) { console.error(e); } }
    elBody.replaceChildren();
  }
  saveState();
}

function activateAndShow(id) {
  const t = tabs.find((x) => x.id === id);
  if (!t) return;
  if (activeId !== id) {
    const prev = tabs.find((x) => x.id === activeId);
    activeId = id;
    renderTabsBar();
    if (isOpen && prev && prev.onHide) { try { prev.onHide(); } catch (e) { console.error(e); } }
  }
  if (!isOpen) setOpen(true);
  else renderActive();
  saveState();
}

/* Clicking a tab: the active tab (open) collapses the panel; any other tab (or a closed panel) opens it. */
function clickTab(id) {
  if (isOpen && activeId === id) { setOpen(false); return; }
  activateAndShow(id);
}

function addTab({ id, label, render, onShow, onHide }) {
  if (!id || tabs.some((t) => t.id === id)) return;
  const btn = el('button', 'bp-tab');
  btn.type = 'button';
  btn.id = `bpTab-${id}`;
  btn.setAttribute('role', 'tab');
  btn.setAttribute('aria-selected', 'false');
  btn.textContent = label;
  btn.onclick = () => clickTab(id);
  elTabs.appendChild(btn);
  tabs.push({ id, label, render, onShow, onHide, btn });
  if (!activeId) activeId = id;   // the first tab added is the default
  renderTabsBar();
}

function show(id) { activateAndShow(id); }
function isShowing(id) { return isOpen && activeId === id; }
function refresh(id) {
  if (id == null) { if (isOpen) renderActive(); return; }
  if (isShowing(id)) renderActive();
}

function wireResize() {
  let dragging = false;
  elResize.addEventListener('pointerdown', (e) => {
    dragging = true;
    try { elResize.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    e.preventDefault();
  });
  elResize.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    applyHeight(window.innerHeight - e.clientY - 30);   // 30 = the status bar
  });
  const release = (e) => {
    if (!dragging) return;
    dragging = false;
    try { elResize.releasePointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    saveState();
  };
  elResize.addEventListener('pointerup', release);
  elResize.addEventListener('pointercancel', release);
  elResize.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp') { e.preventDefault(); applyHeight(height + 16); saveState(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); applyHeight(height - 16); saveState(); }
  });
}

function mount(pg) {
  page = pg;
  const saved = loadState();
  applyHeight(saved && Number.isFinite(saved.h) ? saved.h : DEFAULT_H);
  if (saved && typeof saved.tab === 'string' && tabs.some((t) => t.id === saved.tab)) activeId = saved.tab;
  renderTabsBar();
  isOpen = !!(saved && saved.open === true);
  elPanel.classList.toggle('open', isOpen);
  const label = isOpen ? 'Close the panel' : 'Open the panel';
  elToggle.setAttribute('aria-label', label);
  elToggle.title = label;
  if (isOpen) renderActive();
  elToggle.onclick = () => setOpen(!isOpen);
  wireResize();
  if (window.HBDeskClient) window.HBDeskClient.on(() => refresh());
}

/* The built-in tabs (every account: ruling S6). Registered immediately -- addTab only needs the
   static DOM, not `page` -- so later modules (Task 9's Strategy Tester) can add theirs the same
   way, in script order, before app.js calls mount(). */
addTab({ id: 'positions', label: 'Positions', render: renderPositions });
addTab({ id: 'orders', label: 'Orders', render: renderOrders });
addTab({ id: 'fills', label: 'Fills', render: renderFills });
addTab({ id: 'accounts', label: 'Accounts', render: renderAccounts });

window.HBPanel = { mount, addTab, show, refresh, isShowing };
})();
