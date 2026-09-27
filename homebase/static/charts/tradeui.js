/* Homebase Charts — HBTradeUI: the Trade toolbar menu (accounts, one-click, qty, SL/TP ticks), the confirm
   dialog ($ + RR 1:X preview), the trading actions (each sends through HBDeskClient, which owns toasts), and
   the Buy/Sell limit/stop + Cancel all / Flatten / Reverse items in the chart's right-click menu
   (HBChartMenu.register('trading', …)).

   Safety (ruling S4/S5, and the 2026-09-27 review of Tasks 3-4):
     - every action re-reads HBDesk.mode() and the ticked accounts at the moment it actually sends, not at the
       moment the user clicked or the confirm dialog opened — the desk, the ticked set or a LIVE arm can all
       change while a dialog is open;
     - one action's send is in flight at a time (`withLock`): a second attempt while one is out is dropped, and
       the chart menu's Buy/Sell/Cancel/Flatten/Reverse items disappear from a fresh right-click while busy;
     - a LIVE account needs a second click within 3 s to tick (S5) — including a LIVE tick already sitting in
       localStorage from a previous session: `liveConfirmed` starts empty every load, so a restored LIVE tick
       is *shown* but does not count until it is re-armed this session.
   Browser only; the logic (prefs, inference, bodies, lines, confirm texts, toasts) lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;
const D = () => window.HBDeskClient;

let page = null;
let armLive = null;      // the account id mid-arm (first click), or null
let armTimer = 0;
const liveConfirmed = new Set();   // LIVE accounts armed THIS session (never persisted: ruling S5 + the review note)
let inFlight = false;    // one send at a time (review item 2)

/* ---- mode, gated by this session's LIVE arms on top of HBTrade.tradeMode ---- */
function effectiveMode() {
  const m = D().mode();
  if (m.mode !== 'on') return m;
  const st = D().state;
  const accounts = m.accounts.filter((id) => {
    const a = (st.accounts || []).find((x) => x.id === id);
    return !a || a.env !== 'live' || liveConfirmed.has(id);
  });
  if (accounts.length === m.accounts.length) return m;
  return accounts.length ? { mode: 'on', reason: '', accounts }
    : { mode: 'none', reason: 'Tick an account in the Trade menu', accounts: [] };
}
function busy() { return inFlight; }

/* One send (or one sequential batch of them, for a per-leg modify/cancel) at a time, mode re-checked right
   before it goes out. buildBody(m) returns a body object, an array of bodies (sent in order), or null/undefined
   to abort silently (the mode reason toast already covers the "why"). */
function guardedSend(action, buildBody) {
  if (inFlight) return;
  inFlight = true;
  Promise.resolve().then(() => {
    const m = effectiveMode();
    if (m.mode !== 'on') { D().toast('err', m.reason); return null; }
    const body = buildBody(m);
    if (body == null) return null;
    if (Array.isArray(body)) return body.reduce((p, one) => p.then(() => D().send(action, one)), Promise.resolve());
    return D().send(action, body);
  }).catch((e) => console.error(e)).finally(() => { inFlight = false; });
}

/* ---- small helpers ---- */
function tickFor(root) {
  const cells = (page.cells && page.cells()) || [];
  const c = cells.find((x) => x.shown && x.shown.root === root);
  return c ? c.tick : 0;
}
function acctRows(ids) {
  const st = D().state, list = (st && st.accounts) || [];
  return ids.map((id) => { const a = list.find((x) => x.id === id); return a ? { label: a.label, env: a.env } : { label: id, env: 'demo' }; });
}
function findOrder(account, order_id) {
  const st = D().state, a = st && (st.accounts || []).find((x) => x.id === account);
  const o = a && (a.orders || []).find((x) => String(x.order_id) === String(order_id));
  return { acct: a, order: o };
}

/* ---- the confirm dialog (the pattern app.js already uses) ---- */
function confirm({ title, rows = [], note = '', each = '', live = false, action, tone = 'accent' }) {
  const Dc = D();
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => { if (done) return; done = true; resolve(ok); };
    const box = page.openDialog(title, 'confirm');
    page.setDialogClose(() => finish(false));            // ×, backdrop, Esc (through the app's onKey)
    const body = page.mk('div', 'cf-body');
    for (const r of rows) {
      const row = page.mk('div', 'cf-acct');
      row.append(page.mk('span', '', r.label), page.mk('span', `env${r.env === 'live' ? ' live' : ''}`, r.env === 'live' ? 'LIVE' : 'DEMO'));
      body.append(row);
    }
    if (note) body.append(page.mk('div', 'cf-note', note));
    if (each) body.append(page.mk('div', 'cf-each', each));
    const one = page.mk('label', 'cf-one'), ck = page.mk('input');
    ck.type = 'checkbox';
    one.append(ck, page.mk('span', '', "Don't ask again (one-click trading)"));
    const foot = page.mk('div', 'dlg-foot'), no = page.mk('button', 'btn', 'Cancel'), yes = page.mk('button', `btn primary ${tone}`, action);
    no.type = yes.type = 'button';
    no.onclick = () => page.closeDialog();                 // onClose -> finish(false)
    yes.onclick = () => {
      if (yes.disabled) return;                            // a double click never fires this twice (review item 2)
      yes.disabled = true; no.disabled = true;
      if (ck.checked) Dc.setPrefs({ oneClick: true });
      page.setDialogClose(null);
      page.closeDialog();
      finish(true);
    };
    box.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target !== no && e.target.type !== 'checkbox') { e.preventDefault(); yes.click(); } });
    foot.append(no, yes);
    box.append(body, one, foot);
    if (live) box.classList.add('live');
    yes.focus();
  });
}

/* ---- actions (the table in the brief) ---- */
function placeOrder({ cell, root, side, type, price = null, qty }) {
  const gate = effectiveMode();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const tick = cell ? cell.tick : tickFor(root), pv = cell ? cell.pv : null;
  const build = (m) => {
    const prefs = D().prefs, q = D().quotes[root];
    const px = type === 'Market' ? null : T.roundTick(price, tick);
    const ref = type === 'Market' ? (q ? q.last : null) : px;
    const { sl, tp } = T.bracket(side, ref, prefs, tick);
    return T.orderBody({ clientId: T.clientId(), accounts: m.accounts, root, side, qty, type, price: px, sl, tp });
  };
  if (D().prefs.oneClick) { guardedSend('order', build); return; }
  const preview = build(gate);
  const c = T.confirmOrder(preview, D().state, D().quotes[root], pv, tick);
  confirm({ title: c.title, rows: c.accounts.map((a) => ({ label: a.label, env: a.env })), note: c.bracket,
    each: c.each, live: c.live, action: side, tone: side === 'Sell' ? 'down' : 'accent' })
    .then((ok) => { if (ok) guardedSend('order', build); });
}

function symbolAction(kind, root) {
  const gate = effectiveMode();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const build = (m) => ({ client_id: T.clientId(), accounts: m.accounts, root });
  if (D().prefs.oneClick && kind !== 'reverse') { guardedSend(kind, build); return; }   // Reverse always confirms (S4)
  const tick = tickFor(root);
  const title = T.actionTitle(kind, { root }, tick);
  const verb = kind === 'flatten' ? 'Flatten' : kind === 'reverse' ? 'Reverse' : 'Cancel orders';
  confirm({ title, rows: acctRows(gate.accounts), action: verb }).then((ok) => { if (ok) guardedSend(kind, build); });
}

function moveLine(line, price, root, tick, { onCancel } = {}) {
  const gate = effectiveMode();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); if (onCancel) onCancel(); return; }
  const build = () => line.legs.map((leg) => ({ client_id: T.clientId(), account: leg.account, order_id: leg.order_id, price: T.roundTick(price, tick) }));
  if (D().prefs.oneClick) { guardedSend('modify', build); return; }
  const title = T.actionTitle('modify', { root, line, from: line.price, to: price }, tick);
  confirm({ title, rows: acctRows(line.legs.map((l) => l.account)), action: 'Move' })
    .then((ok) => { if (ok) guardedSend('modify', build); else if (onCancel) onCancel(); });
}

/* × on a line: flatten for a position, cancel for the rest (SL/TP/plain orders). */
function closeLine(line, root, tick) {
  const gate = effectiveMode();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const isPosition = line.kind === 'position';
  const accounts = [...new Set(line.legs.map((l) => l.account))];
  const action = isPosition ? 'flatten' : 'cancel';
  const build = () => (isPosition ? { client_id: T.clientId(), accounts, root }
    : line.legs.map((leg) => ({ client_id: T.clientId(), account: leg.account, order_id: leg.order_id })));
  if (D().prefs.oneClick) { guardedSend(action, build); return; }
  const title = T.actionTitle(action, { root, line }, tick);
  const verb = isPosition ? 'Flatten' : (line.legs.length > 1 ? 'Cancel orders' : 'Cancel order');
  confirm({ title, rows: acctRows(accounts), action: verb }).then((ok) => { if (ok) guardedSend(action, build); });
}

function flattenAccount(account, root) {
  const gate = effectiveMode();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const build = () => ({ client_id: T.clientId(), accounts: [account], root });
  if (D().prefs.oneClick) { guardedSend('flatten', build); return; }
  const title = T.actionTitle('flatten', { root }, tickFor(root));
  confirm({ title, rows: acctRows([account]), action: 'Flatten' }).then((ok) => { if (ok) guardedSend('flatten', build); });
}

function cancelOrder(account, order_id) {
  const gate = effectiveMode();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const build = () => ({ client_id: T.clientId(), account, order_id });
  if (D().prefs.oneClick) { guardedSend('cancel', build); return; }
  const { acct, order } = findOrder(account, order_id);
  const tick = order ? tickFor(T.rootOf(order.symbol)) : 0;
  const line = order ? { kind: 'order', side: order.side, type: order.type, qty: Number(order.qty) || 0,
    price: T.orderPrice(order), legs: [{ who: acct ? T.short(acct) : account }] } : null;
  const title = line ? T.actionTitle('cancel', { line }, tick) : 'Cancel order';
  confirm({ title, rows: acctRows([account]), action: 'Cancel order' }).then((ok) => { if (ok) guardedSend('cancel', build); });
}

/* ---- the chart's right-click menu: Buy/Sell limit/stop, Cancel all / Flatten / Reverse ---- */
function registerChartMenuTrading() {
  window.HBChartMenu.register('trading', (ctx) => {
    if (effectiveMode().mode !== 'on' || busy()) return [];
    const Dk = D(), q = Dk.quotes[ctx.root], qty = Dk.prefs.qty, out = [];
    if (ctx.price != null) {
      const price = T.roundTick(ctx.price, ctx.tick);   // always tick-rounded before inferType (review item 2)
      for (const side of ['Buy', 'Sell']) {
        const type = T.inferType(side, price, q);
        if (type) out.push({ text: T.menuText(side, qty, price, type, ctx.tick),
          run: () => placeOrder({ cell: ctx.cell, root: ctx.root, side, type, price, qty }) });
      }
    }
    out.push({ text: `Cancel all orders (${ctx.root})`, run: () => symbolAction('cancel-symbol', ctx.root) },
      { text: `Flatten ${ctx.root}`, run: () => symbolAction('flatten', ctx.root) },
      { text: `Reverse ${ctx.root}`, run: () => symbolAction('reverse', ctx.root) });
    return out;
  });
}

/* ---- the Trade toolbar menu ---- */
function dotClass(mode) { return mode === 'on' ? 'ok' : mode === 'down' ? 'bad' : 'warn'; }
function updateTradeButton() {
  const btn = document.getElementById('tbTrade'), dot = document.getElementById('tbTradeDot');
  if (!btn || !dot) return;
  const m = effectiveMode();
  dot.className = 'dot ' + dotClass(m.mode);
  btn.title = m.reason || 'Trade';
}

function envSpan(env) { return page.mk('span', 'env' + (env === 'live' ? ' live' : ''), String(env || '').toUpperCase()); }
function dotSpan(ok) { return page.mk('span', 'dot' + (ok ? ' ok' : ' bad')); }

/* Ticking a LIVE account needs a second click within 3 s (S5) -- including one already ticked in localStorage
   from a previous session, since liveConfirmed starts empty every load (the review's "re-confirm on first use
   after reload"). */
function onTickChange(a, cb) {
  const prefs = D().prefs, wantTick = cb.checked;
  if (wantTick && a.env === 'live' && !liveConfirmed.has(a.id)) {
    if (armLive === a.id) {   // the second click, within the window: arm it for real
      liveConfirmed.add(a.id);
      clearTimeout(armTimer); armLive = null;
      const ticked = new Set(prefs.ticked); ticked.add(a.id);
      D().setPrefs({ ticked: [...ticked] });
    } else {                  // the first click: arm, but do not tick yet
      cb.checked = false;
      armLive = a.id;
      clearTimeout(armTimer);
      armTimer = setTimeout(() => { if (armLive === a.id) { armLive = null; refillIfOpen(); } }, 3000);
    }
    refillIfOpen();
    return;
  }
  if (armLive === a.id) { armLive = null; clearTimeout(armTimer); }
  if (!wantTick && a.env === 'live') liveConfirmed.delete(a.id);   // re-ticking this session arms again
  const ticked = new Set(prefs.ticked);
  if (wantTick) ticked.add(a.id); else ticked.delete(a.id);
  D().setPrefs({ ticked: [...ticked] });
}

function acctRow(a, prefs) {
  const id = `tm-acct-${a.id}`, row = page.mk('div', 'tm-row');
  const cb = page.mk('input');
  cb.type = 'checkbox'; cb.id = id; cb.dataset.tm = `acct:${a.id}`;
  cb.disabled = !a.tradable;
  cb.checked = prefs.ticked.includes(a.id) && (a.env !== 'live' || liveConfirmed.has(a.id));
  cb.onchange = () => onTickChange(a, cb);
  const lab = page.mk('label', 'tm-label');
  lab.htmlFor = id;
  if (armLive === a.id) {
    lab.appendChild(page.mk('span', 'tm-arm', 'Tick LIVE — real orders. Click again'));
  } else {
    lab.appendChild(page.mk('span', 'tm-name', a.label));
    if (!a.tradable) lab.appendChild(page.mk('span', 'tm-err', a.error || 'not tradable'));
  }
  row.append(cb, lab, envSpan(a.env), page.mk('span', 'tm-bal', T.money(a.balance)), dotSpan(a.connected));
  return row;
}

function numPref(label, key, value, min, max, note) {
  const row = page.mk('div', 'tm-pref'), id = `tm-${key}`, lab = page.mk('label', '', label);
  lab.htmlFor = id;
  const inp = page.mk('input');
  inp.type = 'number'; inp.id = id; inp.min = String(min); inp.max = String(max); inp.value = String(value);
  inp.dataset.tm = key;
  inp.onchange = () => {
    const n = Math.round(Number(inp.value)), patch = {};
    patch[key] = Number.isFinite(n) ? n : value;
    D().setPrefs(patch);
  };
  const right = page.mk('span', '');
  right.append(inp);
  if (note) right.append(page.mk('span', 'tm-note', ' ' + note));
  row.append(lab, right);
  return row;
}

/* Which control had focus, so a re-fill (a desk event, or arming a LIVE tick) does not steal it. */
function focusKey(m) {
  const el = document.activeElement;
  return (m.contains(el) && el.dataset && el.dataset.tm) || null;
}
function restoreFocus(m, key) {
  if (!key) return;
  const el = [...m.querySelectorAll('[data-tm]')].find((x) => x.dataset.tm === key);
  if (el) el.focus();
}

function fillMenu(m) {
  const key = focusKey(m);
  m.replaceChildren();
  const st = D().state, prefs = D().prefs, mode = D().mode();
  m.appendChild(page.mk('div', 'menu-h', 'CHART TRADING'));
  if (mode.mode === 'down') {
    m.appendChild(page.mk('div', 'tm-status', `Desk unreachable — ${mode.reason}`));
  } else if (mode.mode === 'off') {
    const row = page.mk('div', 'tm-status');
    row.append(document.createTextNode('Chart trading is off on the desk'));
    const a = document.createElement('a');
    a.href = page.deskUrl(); a.target = '_blank'; a.rel = 'noopener';
    a.append(page.icon('extLink'), document.createTextNode('Open the desk'));
    row.append(a);
    m.appendChild(row);
  } else {
    const lim = (st && st.limits) || {};
    m.appendChild(page.mk('div', 'tm-status', `Max ${lim.max_order_qty ?? '—'} per order · ${lim.max_position_qty ?? '—'} per position`));
  }
  for (const a of (st && st.accounts) || []) m.appendChild(acctRow(a, prefs));
  m.appendChild(page.mk('div', 'menu-sep'));
  const oc = page.mk('div', 'tm-pref'), lab = page.mk('label', '', 'One-click trading');
  const sw = page.mk('button', 'switch' + (prefs.oneClick ? ' on' : ''));
  sw.type = 'button';
  sw.setAttribute('role', 'switch');
  sw.setAttribute('aria-checked', String(prefs.oneClick));
  sw.dataset.tm = 'oneclick';
  sw.onclick = () => { D().setPrefs({ oneClick: !D().prefs.oneClick }); refillIfOpen(); };
  oc.append(lab, sw);
  m.appendChild(oc);
  const maxQty = (st && st.limits && st.limits.max_order_qty) || 10000;
  m.append(numPref('Default quantity', 'qty', prefs.qty, 1, maxQty),
    numPref('Stop loss (ticks)', 'slTicks', prefs.slTicks, 0, 10000, '0 = off'),
    numPref('Take profit (ticks)', 'tpTicks', prefs.tpTicks, 0, 10000, '0 = off'));
  restoreFocus(m, key);
}

function refillIfOpen() {
  const m = document.querySelector('.menu-trade');
  if (m) fillMenu(m);
}

function mount(pg) {
  page = pg;
  const btn = document.getElementById('tbTrade');
  if (btn) btn.onclick = () => page.toggleMenu(btn, () => fillMenu(page.openMenu(btn, 'menu-trade')));
  updateTradeButton();
  if (window.HBDeskClient) window.HBDeskClient.on(() => { updateTradeButton(); refillIfOpen(); });
  registerChartMenuTrading();
}

window.HBTradeUI = { mount, placeOrder, symbolAction, flattenAccount, cancelOrder, closeLine, moveLine, confirm, busy };
})();
