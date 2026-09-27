/* Homebase Charts — HBTradeUI: the confirm dialog ($ + RR 1:X preview), the trading actions (each sends
   through HBDeskClient, which owns toasts), the Buy/Sell limit/stop + Cancel all / Flatten / Reverse items in
   the chart's right-click menu (HBChartMenu.register('trading', …)), the desk's own state in the bottom
   status bar, and the model behind the chart gear's Trading tab (accounts, the LIVE arm, the algo binding).

   Trading is PER CHART, and the chart's ACCOUNTS are the switch (2026-09-27 accounts-per-chart plan, Task 1):
   each chart's cell config carries `trade: {accounts}` -- `trade.on` is retired -- and every order-sending
   path takes its accounts from the chart it was started from (the Buy/Sell block, a chart-menu item, a line's
   drag or ×, the order panel). Accounts are edited in that chart's ⚙ → Trading (settings-dialog.js, through
   accountRows / toggleAccount / pickAlgo below); the old #tbTrade toolbar menu is gone. The bottom panel's
   per-account Close/Cancel act on the named account only (accountGate).

   A chart's algo (2026-09-27 plan, Task 3): `cell.cfg.algo` is set through setCellAlgo; its Kill (botKill) goes
   through the same confirm and a guardedSend-shaped send on its OWN per-strategy lock (final review I3: a hung
   order never holds a Kill back), needs the LIVE arm for a LIVE account of the bot, and is offered
   whatever the chart's Trading switch says (it is the emergency stop, not trading).

   Safety (ruling S4/S5, and the 2026-09-27 review of Tasks 3-4):
     - every action re-reads its gate (the chart's mode from HBDesk.mode(that chart's trade), or the named
       account's gate) at the moment it actually sends, not at the moment the user clicked or the confirm dialog
       opened — the desk, the chart's accounts, its switch or a LIVE arm can all change while a dialog is open;
     - one action's send is in flight at a time (`withLock`): a second attempt while one is out is dropped, and
       the chart menu's Buy/Sell/Cancel/Flatten/Reverse items disappear from a fresh right-click while busy;
     - a LIVE account needs a second click within 3 s to tick (S5). A layout load drops LIVE accounts
       outright now (HBTrade.loadedTrade), and `liveConfirmed` still starts empty every load, so a LIVE
       account left on a chart by any other route is *shown* but does not count until re-armed this session.
   Browser only; the logic (prefs, inference, bodies, lines, confirm texts, toasts) lives in HBTrade. */
(() => {
'use strict';
const T = window.HBTrade;
const D = () => window.HBDeskClient;

let page = null;
let armLive = null;      // the account id mid-arm (first click), or null
let armTimer = 0;
const liveConfirmed = new Set();   // LIVE accounts armed THIS session (never persisted: ruling S5 + the review note)
let inFlight = false;    // one send at a time (review item 2; the 2026-09-27 review of Task 5 makes this a toast, not a silent drop)
const busySubs = new Set();   // notified synchronously on every inFlight flip, so the panel and the chart's lines grey out immediately
const tradeSubs = new Set();  // notified when a chart's trade config or a LIVE arm changes (the charts' overlays re-render)

/* ---- one chart's trade config and mode ---- */
/* The chart's {accounts}, sanitised; a missing chart has none (so it is view-only). */
function tradeOf(cell) { return T.cellTrade(cell && cell.cfg ? cell.cfg.trade : null); }
/* The root a chart is showing (the loaded one; its config's while nothing has loaded yet). */
function rootOfCell(cell) { return !cell ? null : cell.shown ? cell.shown.root : (cell.cfg && cell.cfg.root) || null; }
/* HBTrade.tradeMode on THIS chart's config, with this session's LIVE arms on top (HBTrade.armedMode), and
   T.replayGuard as the last word: a chart in Bar Replay (cell.replay, set by replayui.js) can never trade
   (2026-09-27 plan, Global Constraints) -- this is the one place every order-sending path's gate (cellGate,
   the chart menu, a line's drag/×, the Buy/Sell block) reads, so nothing needs its own replay check. */
function effectiveMode(cell) {
  return T.replayGuard(T.armedMode(D().mode(tradeOf(cell)), D().state, liveConfirmed), !!(cell && cell.replay));
}
/* A chart-started send path's gate: the chart's mode, the chart still on the page, and still showing the root
   the action was started for. Re-run at send time by guardedSend. */
function cellGate(cell, root) {
  const m = effectiveMode(cell);
  if (m.mode !== 'on') return m;
  if (!page || !page.cells().includes(cell)) return { mode: 'none', reason: 'That chart is gone — nothing sent', accounts: [] };
  if (rootOfCell(cell) !== root) return { mode: 'none', reason: 'This chart changed symbol — nothing sent', accounts: [] };
  return m;
}
/* The bottom panel's per-account gate: the desk up and on, and the named account armed if it is LIVE. */
function accountGate(account) {
  const g = D().gate();
  if (g) return g;
  if (!isArmedAccount(account)) {
    const st = D().state, a = st && (st.accounts || []).find((x) => x.id === account);
    return { mode: 'none', reason: T.unarmedLiveMessage(a || { id: account }), accounts: [] };
  }
  return { mode: 'on', reason: '', accounts: [account] };
}
/* The accounts whose lines this chart may drag / close: its effective accounts, none while it cannot trade. */
function editableIds(cell) { const m = effectiveMode(cell); return m.mode === 'on' ? m.accounts : []; }
/* The accounts whose execution markers this chart draws: its own accounts, minus an unarmed LIVE one
   (review item 5), whether or not its Trading is on. */
function fillIds(cell) { return T.armedTicked(D().state, tradeOf(cell).accounts, liveConfirmed); }
function onTradeChange(fn) { tradeSubs.add(fn); return () => tradeSubs.delete(fn); }
function notifyTrade() {
  for (const fn of [...tradeSubs]) { try { fn(); } catch (e) { console.error(e); } }
}
/* Set a chart's trade config (sanitised). The page saves it: an account-list change is a layout change (the
   layout reads Unsaved). `quiet`: the caller saves (the Settings dialog's live preview, which Cancel puts
   back and Ok commits; a template preview; the one-time migration). */
function setCellTrade(cell, next, { quiet = false } = {}) {
  if (!cell || !cell.cfg) return;
  const was = tradeOf(cell), now = T.cellTrade(next);
  cell.cfg.trade = now;
  if (!quiet && page && page.tradeChanged) page.tradeChanged(cell, JSON.stringify(was.accounts) !== JSON.stringify(now.accounts));
  notifyTrade();
}
/* Set a chart's algo (a desk strategy key, or null). An algo is part of the layout (Unsaved) unless `quiet` (the
   Settings dialog's live preview: saved on its Ok; a Cancel / rollback that restores it). */
function setCellAlgo(cell, algo, { quiet = false } = {}) {
  if (!cell || !cell.cfg) return;
  const was = T.cellAlgo(cell.cfg.algo), now = T.cellAlgo(algo);
  cell.cfg.algo = now;
  if (!quiet && was !== now && page && page.tradeChanged) page.tradeChanged(cell, true);
  notifyTrade();
}
/* A single account id, refused when it is an unarmed LIVE account (review item 5's per-account paths). Fails
   CLOSED when the id isn't found in desk state at all (M6): unrecognized is never treated as armed. */
function isArmedAccount(id) {
  const st = D().state, a = st && (st.accounts || []).find((x) => x.id === id);
  if (!a) return false;
  return a.env !== 'live' || liveConfirmed.has(id);
}
/* The first unarmed LIVE account among ids, or null -- for a single refusal toast naming it. */
function findUnarmed(ids) {
  const st = D().state, list = (st && st.accounts) || [];
  for (const id of ids) if (!isArmedAccount(id)) return list.find((x) => x.id === id) || { id };
  return null;
}
/* final review I3: the emergency Kill has its OWN lock, per strategy -- never the page-wide one above, so an order,
   modify or flatten hung on the desk (up to its 20 s timeout) can never hold a Kill back. It still needs its
   confirm, the LIVE arm (killGate) and the replay gate; a second Kill of the SAME strategy while one is in flight
   is refused (the desk is idempotent per client_id and serialises kills itself). */
const killing = new Set();   // strategy keys whose Kill is in flight
function killBusy(key) { return killing.has(key); }
function setKilling(key, v) {
  if (v) killing.add(key); else killing.delete(key);
  for (const fn of [...busySubs]) { try { fn(inFlight); } catch (e) { console.error(e); } }   // the badges repaint
}
function busy() { return inFlight; }
function onBusyChange(fn) { busySubs.add(fn); return () => busySubs.delete(fn); }
function setInFlight(v) {
  inFlight = v;
  for (const fn of [...busySubs]) { try { fn(v); } catch (e) { console.error(e); } }
}

/* One send (or one sequential batch of them, for a per-leg modify/cancel) at a time, its gate (a function: the
   chart's cellGate, or the panel's accountGate) re-checked right before it goes out. buildBody(m) returns a body object, an array of bodies (sent in order), or null/undefined
   to abort silently (a specific toast — mode reason, accounts-changed, price-moved — already covers the "why").
   A second attempt while one is in flight now toasts instead of dropping silently (review item 3). */
function guardedSend(action, gate, buildBody) {
  if (inFlight) { D().toast('err', 'Another action is in flight'); return; }
  setInFlight(true);
  Promise.resolve().then(() => {
    const m = gate();
    if (m.mode !== 'on') { D().toast('err', m.reason); return null; }
    const body = buildBody(m);
    if (body == null) return null;
    if (Array.isArray(body)) return body.reduce((p, one) => p.then(() => D().send(action, one)), Promise.resolve());
    return D().send(action, body);
  }).catch((e) => console.error(e)).finally(() => setInFlight(false));
}

/* ---- small helpers ---- */
function tickFor(root) {
  const cells = (page.cells && page.cells()) || [];
  const c = cells.find((x) => x.shown && x.shown.root === root);
  return c ? c.tick : 0;
}
function acctRows(ids) {
  const st = D().state, list = (st && st.accounts) || [];
  // an id the desk does not list gets env '?' -- never shown as DEMO (M1: fail closed, in the dialog too)
  return ids.map((id) => { const a = list.find((x) => x.id === id); return a ? { label: a.label, env: a.env } : { label: id, env: '?' }; });
}
function hasLive(rows) { return rows.some((a) => a.env === 'live'); }
function findOrder(account, order_id) {
  const st = D().state, a = st && (st.accounts || []).find((x) => x.id === account);
  const o = a && (a.orders || []).find((x) => String(x.order_id) === String(order_id));
  return { acct: a, order: o };
}

/* ---- the confirm dialog (the pattern app.js already uses) ---- */
function confirm({ title, rows = [], note = '', warn = '', each = '', live = false, action, tone = 'accent', oneClickBox = true }) {
  const Dc = D();
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => { if (done) return; done = true; resolve(ok); };
    const box = page.openDialog(title, 'confirm');
    page.setDialogClose(() => finish(false));            // ×, backdrop, Esc (through the app's onKey)
    const body = page.mk('div', 'cf-body');
    for (const r of rows) {
      const row = page.mk('div', 'cf-acct');
      // '?': an account the desk does not list (the Kill's rows, fix round 1 M1) -- never shown as DEMO
      const env = T.envChip(r.env);
      const cls = r.env === 'live' ? ' live' : r.env === 'paper' ? ' paper' : '';
      row.append(page.mk('span', '', r.label), page.mk('span', `env${cls}`, env));
      body.append(row);
    }
    if (note) body.append(page.mk('div', 'cf-note', note));
    if (warn) body.append(page.mk('div', 'cf-note cf-warn', warn));
    if (each) body.append(page.mk('div', 'cf-each', each));
    const one = page.mk('label', 'cf-one'), ck = page.mk('input');
    ck.type = 'checkbox';
    one.append(ck, page.mk('span', '', "Don't ask again (one-click trading)"));
    one.hidden = !oneClickBox;   // the Kill always asks: no one-click box there
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
    // review item 1 (CRITICAL): Enter confirms ONLY when focus is on the primary button, or on a non-button
    // element (the checkbox, an unfocusable row) -- never × (the dialog's own close button, inside `box`),
    // Cancel, or any other button. T.enterConfirms is the pure, Node-tested predicate.
    // I3: a HELD Enter (e.repeat) never confirms either -- picking a chart-menu item by keyboard opens this
    // dialog with focus already on `yes`, and the still-held key's auto-repeat must not also confirm it. The
    // repeat is still swallowed (preventDefault) so it can't leak into some other default action.
    box.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      if (T.enterConfirms(e.target, yes, e.repeat)) { e.preventDefault(); yes.click(); }
      else if (e.repeat) e.preventDefault();
    });
    foot.append(no, yes);
    box.append(body, one, foot);
    if (live) box.classList.add('live');
    yes.focus();
  });
}

/* ---- actions (the table in the brief) ---- */
/* `cell` is required: the order goes only to that chart's accounts (the order panel passes the chart selected at
   the moment of its click).
   The order panel (2026-09-27 order-panel plan, Task 3) also passes:
     - `exits: {sl, tp}`: explicit SL/TP prices (null = that side off), used INSTEAD of the all-charts tick
       defaults; frozen here with everything else, exactly like the M1 bracket;
     - `trigger`: a Stop Limit's trigger (`price` is then its limit);
     - `tif`: 'Day' | 'GTC' for a resting order (a Market order is Day only: none sent).
   Without them (the Buy/Sell block, the chart menu) the body is exactly what it always was. */
function placeOrder({ cell, root, side, type, price = null, qty, exits = undefined, trigger = null, tif = null }) {
  const g = () => cellGate(cell, root), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const tick = cell.tick, pv = cell.pv ?? null;
  const shown = gate.accounts;   // exactly what the dialog (or the one-click send) is about to show/act on (review item 2)
  const prefs = D().prefs;
  const explicit = exits != null;
  const px = type === 'Market' ? null : T.roundTick(price, tick);
  const trig = type === 'StopLimit' && trigger != null ? T.roundTick(trigger, tick) : null;
  const tf = type === 'Market' ? null : tif;   // a Market order is Day only
  if (type === 'StopLimit' && (!explicit || !Number.isFinite(trig) || !Number.isFinite(px))) {
    D().toast('err', 'A Stop Limit needs its trigger, limit and exits from the order panel'); return;
  }
  // M1: the reference price and the SL/TP it implies are frozen HERE (decision time: the preview, or the
  // one-click send itself) and reused verbatim at the actual send -- never recomputed from a quote that may
  // have moved since, so the confirm dialog and the send always carry the same bracket. A quote older than
  // 10 s (M4) counts as no quote, so no bracket, same as never having had one.
  const q0 = T.freshQuote(D().quotes[root], page.clockMs());
  const ref = type === 'Market' ? (q0 ? q0.last : null) : px;
  let sl, tp;
  if (explicit) {
    sl = exits.sl == null ? null : T.roundTick(exits.sl, tick);
    tp = exits.tp == null ? null : T.roundTick(exits.tp, tick);
    // N1 for explicit exits: a Market with an exit needs a fresh quote to measure it against
    if (type === 'Market' && (sl != null || tp != null) && !(q0 && q0.last != null)) {
      D().toast('err', "No recent price — can't attach your stop/target; try again");
      return;
    }
    // the exits' side, frozen with them: a Stop Limit's SL beyond its trigger, TP beyond its limit
    const bad = T.exitSideError(side, type === 'StopLimit' ? trig : ref, ref, sl, tp, type === 'StopLimit');
    if (bad) { D().toast('err', bad); return; }
  } else {
    // N1: a Market order that would attach a bracket (a nonzero SL/TP tick pref) needs a fresh quote to compute
    // it from -- refuse rather than send it naked, with one-click on or off. Not `guardedSend`'s buildBody: this
    // must stop the send before any confirm dialog even opens, not just before the network call.
    if (T.needsQuoteForBracket(type, prefs.slTicks, prefs.tpTicks) && !q0) {
      D().toast('err', "No recent price — can't attach your stop/target; try again");
      return;
    }
    ({ sl, tp } = T.bracket(side, ref, prefs, tick));
  }
  const build = (m) => {
    const resolved = T.resolveConfirmedAccounts(shown, m.accounts);
    if (!resolved.ok) { D().toast('err', 'Accounts changed — review and try again'); return null; }
    if (!resolved.accounts.length) { D().toast('err', 'No confirmed accounts left — nothing sent'); return null; }   // M9
    if (type !== 'Market') {   // review item 6/N2: re-check against the LAST KNOWN quote at any age, refusing outright with none
      // a Stop Limit's trigger is what must still be a stop (its limit rests beyond it)
      const msg = type === 'StopLimit' ? T.refuseIfMarketable(side, trig, D().quotes[root], 'Stop')
        : T.refuseIfMarketable(side, px, D().quotes[root], type);
      if (msg) { D().toast('err', msg); return null; }
    } else if (explicit && (sl != null || tp != null)) {
      // a Market's explicit exits were measured from the last trade at preview: the market must not have moved
      // through them since (the desk would refuse, or the stop would sit on the wrong side right after the fill)
      const q = D().quotes[root], last = q ? q.last : null;
      if (last == null || T.exitSideError(side, last, last, sl, tp)) { D().toast('err', 'Price moved through your stop/target — re-check the order'); return null; }
    }
    return T.orderBody({ clientId: T.clientId(), accounts: resolved.accounts, root, side, qty, type, price: px, sl, tp,
      trigger: trig, tif: tf });
  };
  if (D().prefs.oneClick) { guardedSend('order', g, build); return; }
  const preview = build(gate);
  // shown === gate.accounts here, so only the inferType re-check can abort a preview -- the market moved
  // between the chart-menu's right-click (where `type` was inferred) and picking the item just now.
  if (preview == null) return;
  const c = T.confirmOrder(preview, D().state, D().quotes[root], pv, tick);
  confirm({ title: c.title, rows: c.accounts.map((a) => ({ label: a.label, env: a.env })), note: c.bracket,
    warn: c.warn, each: c.each, live: c.live, action: side, tone: side === 'Sell' ? 'down' : 'accent' })
    .then((ok) => { if (ok) guardedSend('order', g, build); });
}

function symbolAction(cell, kind, root) {
  const g = () => cellGate(cell, root), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const shown = gate.accounts;
  const build = (m) => {
    const resolved = T.resolveConfirmedAccounts(shown, m.accounts);
    if (!resolved.ok) { D().toast('err', 'Accounts changed — review and try again'); return null; }
    if (!resolved.accounts.length) { D().toast('err', 'No confirmed accounts left — nothing sent'); return null; }   // M9
    return { client_id: T.clientId(), accounts: resolved.accounts, root };
  };
  if (D().prefs.oneClick && kind !== 'reverse') { guardedSend(kind, g, build); return; }   // Reverse always confirms (S4)
  const tick = cell.tick;
  const title = T.actionTitle(kind, { root }, tick);
  const verb = kind === 'flatten' ? 'Flatten' : kind === 'reverse' ? 'Reverse' : 'Cancel orders';
  const rows = acctRows(shown);
  confirm({ title, rows, action: verb, live: hasLive(rows) }).then((ok) => { if (ok) guardedSend(kind, g, build); });
}

/* A line may be moved / closed only from a chart whose effective accounts hold every one of its legs. */
const NOT_THIS_CHART = "That line isn't on this chart's trading accounts — view only";

function moveLine(cell, line, price, root, tick, { onCancel } = {}) {
  if (!T.canDrag(line)) { if (onCancel) onCancel(); return; }   // a Stop Limit can't be moved: cancel and place again
  const g = () => cellGate(cell, root), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); if (onCancel) onCancel(); return; }
  const accountIds = line.legs.map((l) => l.account);
  const unarmed = findUnarmed(accountIds);   // review item 5: refuse a LIVE leg that isn't armed this session
  if (unarmed) { D().toast('err', T.unarmedLiveMessage(unarmed)); if (onCancel) onCancel(); return; }
  if (line.editable === false || !T.legsWithin(line, gate.accounts)) { D().toast('err', NOT_THIS_CHART); if (onCancel) onCancel(); return; }
  const rounded = T.roundTick(price, tick);
  if (rounded === T.roundTick(line.price, tick)) { if (onCancel) onCancel(); return; }   // M8: a zero-tick move sends nothing
  if (line.type) {   // I1/N2: re-run against the LAST KNOWN quote at any age -- a Limit dragged through (or
                      // onto) the market must not silently fill; no quote at all refuses outright.
    const kind = /stop/i.test(line.type) ? 'Stop' : 'Limit';
    const msg = T.refuseIfMarketable(line.side, rounded, D().quotes[root], kind);
    if (msg) { D().toast('err', msg); if (onCancel) onCancel(); return; }
  }
  const build = (m) => {
    if (!T.legsWithin(line, m.accounts)) { D().toast('err', 'Accounts changed — review and try again'); return null; }
    return line.legs.map((leg) => ({ client_id: T.clientId(), account: leg.account, order_id: leg.order_id, price: rounded }));
  };
  if (D().prefs.oneClick) { guardedSend('modify', g, build); return; }
  const title = T.actionTitle('modify', { root, line, from: line.price, to: price }, tick);
  const rows = acctRows(accountIds);
  confirm({ title, rows, action: 'Move', live: hasLive(rows) })
    .then((ok) => { if (ok) guardedSend('modify', g, build); else if (onCancel) onCancel(); });
}

/* × on a line: flatten for a position, cancel for the rest (SL/TP/plain orders). */
function closeLine(cell, line, root, tick) {
  const g = () => cellGate(cell, root), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const isPosition = line.kind === 'position';
  const accounts = [...new Set(line.legs.map((l) => l.account))];
  const unarmed = findUnarmed(accounts);   // review item 5
  if (unarmed) { D().toast('err', T.unarmedLiveMessage(unarmed)); return; }
  if (line.editable === false || !T.legsWithin(line, gate.accounts)) { D().toast('err', NOT_THIS_CHART); return; }
  const action = isPosition ? 'flatten' : 'cancel';
  const build = (m) => {
    if (!T.legsWithin(line, m.accounts)) { D().toast('err', 'Accounts changed — review and try again'); return null; }
    return isPosition ? { client_id: T.clientId(), accounts, root }
      : line.legs.map((leg) => ({ client_id: T.clientId(), account: leg.account, order_id: leg.order_id }));
  };
  if (D().prefs.oneClick) { guardedSend(action, g, build); return; }
  const title = T.actionTitle(action, { root, line }, tick);
  const verb = isPosition ? 'Flatten' : (line.legs.length > 1 ? 'Cancel orders' : 'Cancel order');
  const rows = acctRows(accounts);
  confirm({ title, rows, action: verb, live: hasLive(rows) }).then((ok) => { if (ok) guardedSend(action, g, build); });
}

/* The bottom panel's Close / Cancel: the NAMED account only, never a chart's list; the LIVE-arm check stays. */
function flattenAccount(account, root) {
  const g = () => accountGate(account), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const build = () => ({ client_id: T.clientId(), accounts: [account], root });
  if (D().prefs.oneClick) { guardedSend('flatten', g, build); return; }
  const title = T.actionTitle('flatten', { root }, tickFor(root));
  const rows = acctRows([account]);
  confirm({ title, rows, action: 'Flatten', live: hasLive(rows) }).then((ok) => { if (ok) guardedSend('flatten', g, build); });
}

function cancelOrder(account, order_id) {
  const g = () => accountGate(account), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const build = () => ({ client_id: T.clientId(), account, order_id });
  if (D().prefs.oneClick) { guardedSend('cancel', g, build); return; }
  const { acct, order } = findOrder(account, order_id);
  const tick = order ? tickFor(T.rootOf(order.symbol)) : 0;
  const line = order ? { kind: 'order', side: order.side, type: order.type, qty: Number(order.qty) || 0,
    price: T.orderPrice(order), legs: [{ who: acct ? T.short(acct) : account }] } : null;
  const title = line ? T.actionTitle('cancel', { line }, tick) : 'Cancel order';
  const rows = acctRows([account]);
  confirm({ title, rows, action: 'Cancel order', live: hasLive(rows) }).then((ok) => { if (ok) guardedSend('cancel', g, build); });
}

/* ---- a chart's algo: the per-strategy Kill (POST bot-kill {client_id, strategy}) ---- */
/* The Kill's gate, re-run at send time: the desk reachable (NOT its chart-trading switch, NOT this chart's Trading:
   an emergency stop), the strategy still on the desk, the chart still on the page and still carrying that algo, and
   every LIVE account of the bot armed this session. `accounts`: the accounts the desk's kill acts on.
   A chart in Bar Replay never sends a real order (T.replayGuard's rule, 2026-09-27 bar-replay plan) and the
   replay branch never carved out an exception for the Kill, so it is refused there too: leave replay (or use
   the desk / another chart carrying the algo) to Kill. Checked here, so it is re-run at send time as well. */
function killGate(cell, key) {
  if (cell && cell.replay) return { mode: 'none', reason: 'Replay — leave replay to Kill this algo (nothing sent)', accounts: [] };
  const g = D().gate();
  if (g && g.mode === 'down') return g;
  const st = D().state, s = st && st.bot && st.bot.strategies ? st.bot.strategies[key] : null;
  if (!s) return { mode: 'none', reason: `${T.algoName(key)} is not on the desk — nothing sent`, accounts: [] };
  if (!page || !page.cells().includes(cell) || T.cellAlgo(cell.cfg && cell.cfg.algo) !== key) {
    return { mode: 'none', reason: 'That chart no longer carries this algo — nothing sent', accounts: [] };
  }
  const ids = T.algoAccounts(s), why = T.killBlock(st, ids, liveConfirmed);   // an unlisted account fails closed (M1)
  if (why) return { mode: 'none', reason: why, accounts: [] };
  return { mode: 'on', reason: '', accounts: ids };
}
/* Kill the chart's algo: always confirmed (never one-click), then one guarded send; one toast per account (a
   "check it" answer is a sticky warning, HBTrade.killToasts). */
function botKill(cell) {
  const key = T.cellAlgo(cell && cell.cfg && cell.cfg.algo);
  if (!key) return;
  if (killBusy(key)) { D().toast('err', `A Kill of ${T.algoName(key)} is already in flight`); return; }   // I3: never the page-wide lock
  const g = () => killGate(cell, key), gate = g();
  if (gate.mode !== 'on') { D().toast('err', gate.reason); return; }
  const shown = gate.accounts, c = T.killConfirm(key, D().state.bot.strategies[key], D().state);
  const build = (m) => {
    // the desk's kill acts on the strategy's own accounts: an account the dialog never listed aborts it
    if (!T.resolveConfirmedAccounts(shown, m.accounts).ok) { D().toast('err', 'Accounts changed — review and try again'); return null; }
    return { client_id: T.clientId(), strategy: key };
  };
  confirm({ title: c.title, rows: c.rows.map((r) => ({ label: r.label, env: r.env })), note: c.note, live: c.live,
    action: 'Kill', tone: 'down', oneClickBox: false })
    .then((ok) => { if (ok) killSend(key, g, build); });
}
/* guardedSend's shape for the Kill, on the Kill's own per-strategy lock (I3): the gate re-run at send time. */
function killSend(key, gate, buildBody) {
  if (killBusy(key)) { D().toast('err', `A Kill of ${T.algoName(key)} is already in flight`); return; }
  setKilling(key, true);
  Promise.resolve().then(() => {
    const m = gate();
    if (m.mode !== 'on') { D().toast('err', m.reason); return null; }
    const body = buildBody(m);
    return body == null ? null : D().send('bot-kill', body);
  }).catch((e) => console.error(e)).finally(() => setKilling(key, false));
}

/* ---- the chart's right-click menu: Buy/Sell limit/stop, Cancel all / Flatten / Reverse -- only on a chart whose
   own Trading can trade right now, and every item acts for THAT chart ---- */
function registerChartMenuTrading() {
  window.HBChartMenu.register('trading', (ctx) => {
    if (effectiveMode(ctx.cell).mode !== 'on' || busy()) return [];
    const Dk = D(), q = T.freshQuote(Dk.quotes[ctx.root], page.clockMs()), qty = Dk.prefs.qty, out = [];   // M4
    if (ctx.price != null) {
      const price = T.roundTick(ctx.price, ctx.tick);   // always tick-rounded before inferType (review item 2)
      for (const side of ['Buy', 'Sell']) {
        const type = T.inferType(side, price, q);
        if (type) out.push({ text: T.menuText(side, qty, price, type, ctx.tick),
          run: () => placeOrder({ cell: ctx.cell, root: ctx.root, side, type, price, qty }) });
      }
    }
    out.push({ text: `Cancel all orders (${ctx.root})`, run: () => symbolAction(ctx.cell, 'cancel-symbol', ctx.root) },
      { text: `Flatten ${ctx.root}`, run: () => symbolAction(ctx.cell, 'flatten', ctx.root) },
      { text: `Reverse ${ctx.root}`, run: () => symbolAction(ctx.cell, 'reverse', ctx.root) });
    return out;
  });
}

/* ---- the chart gear's Trading tab: ACCOUNTS + ALGO (2026-09-27 accounts-per-chart plan, Task 1) ----
   The dialog owns the DOM; this owns the rules -- the two-step LIVE arm, "unlisted fails closed", and the
   algo <-> accounts binding -- so nothing in the dialog can tick an account the desk would refuse. */
function setAccountTicked(cell, id, on, quiet) {
  const ids = new Set(tradeOf(cell).accounts);
  if (on) ids.add(id); else ids.delete(id);
  setCellTrade(cell, { accounts: [...ids] }, { quiet });
}
function clearArm() { if (armTimer) clearTimeout(armTimer); armTimer = 0; armLive = null; }
function startArm(id) {
  clearArm();
  armLive = id;
  armTimer = setTimeout(() => { if (armLive === id) { armLive = null; notifyTrade(); } }, 3000);
  notifyTrade();
}
/* The account mid-arm (its first LIVE click), or null: the row shows "Tick LIVE — real orders. Click again". */
function armPending() { return armLive; }
/* One chart's ACCOUNTS rows (HBTrade.accountPickRows): the desk's accounts, plus any on this chart's list the
   desk does not list (chip '?', never tradable). */
function accountRows(cell) {
  return T.accountPickRows(D().state, tradeOf(cell).accounts, liveConfirmed, rootOfCell(cell));
}
/* Ticking an account that belongs to an algo on this chart's instrument sets the chart's algo to it. */
function bindAlgoToAccount(cell, id, quiet) {
  const key = T.algoForAccount(D().state, rootOfCell(cell), id);
  if (key && T.cellAlgo(cell.cfg && cell.cfg.algo) !== key) setCellAlgo(cell, key, { quiet });
}
/* A click on one ACCOUNTS checkbox. The chart's own list decides what it means, never the checkbox's toggled
   value: an account already on the list (ticked, or a LIVE one not armed this session) is always REMOVED; one
   that is not is added -- a LIVE account only on its second click within 3 s (ruling S5), an account the desk
   does not list or cannot trade never (fail closed, M6). Returns what happened, for the dialog to paint:
   'removed' | 'ticked' | 'armed' | 'arming' | 'refused'. */
function toggleAccount(cell, id, { quiet = true } = {}) {
  if (!cell || !cell.cfg) return 'refused';
  const st = D().state, a = (st && (st.accounts || []).find((x) => x.id === id)) || null;
  if (tradeOf(cell).accounts.includes(id)) {
    if (armLive === id) clearArm();
    if (a && a.env === 'live') liveConfirmed.delete(id);   // re-ticking this session arms again
    setAccountTicked(cell, id, false, quiet);
    return 'removed';
  }
  if (!a || !a.tradable) { notifyTrade(); return 'refused'; }
  if (a.env === 'live' && !liveConfirmed.has(id)) {
    if (armLive !== id) { startArm(id); return 'arming'; }   // the first click: arm, but do not tick yet
    clearArm();
    liveConfirmed.add(id);                                   // the second click, within the window: armed for real
    setAccountTicked(cell, id, true, quiet);
    bindAlgoToAccount(cell, id, quiet);
    return 'armed';
  }
  if (armLive === id) clearArm();
  setAccountTicked(cell, id, true, quiet);
  bindAlgoToAccount(cell, id, quiet);
  return 'ticked';
}
/* The ALGO select: picking an algo also ticks the accounts it books on this chart's instrument -- never a LIVE
   one that is not already armed this session, and never one the desk does not list (HBTrade.algoTickAccounts).
   Clearing it to None leaves the accounts exactly as they are (watching an algo without trading it is
   unticking its accounts, not clearing the select). */
function pickAlgo(cell, key, { quiet = true } = {}) {
  if (!cell || !cell.cfg) return;
  const k = T.cellAlgo(key);
  setCellAlgo(cell, k, { quiet });
  if (!k) return;
  const add = T.algoTickAccounts(D().state, rootOfCell(cell), k, liveConfirmed);
  if (!add.length) return;
  const have = tradeOf(cell).accounts, next = [...new Set([...have, ...add])];
  if (next.length !== have.length) setCellTrade(cell, { accounts: next }, { quiet });
}

/* ---- the desk's own state, in the bottom status bar (it moved there with the deleted Trade button) ---- */
function paintDeskStatus() {
  const dot = document.getElementById('sbDeskDot'), text = document.getElementById('sbDeskText');
  const link = document.getElementById('sbDeskLink');
  if (!dot || !text || !link) return;
  const s = T.deskStatusText({ state: D().state, down: D().down });
  dot.className = 'sb-dot ' + s.dot;
  text.textContent = s.text;
  link.hidden = !s.link;
  if (s.link && page) link.href = page.deskUrl();
}

function mount(pg) {
  page = pg;
  paintDeskStatus();
  if (window.HBDeskClient) {
    window.HBDeskClient.on((why) => {
      // 'quote' / 'bot' / 'fill' alone never change the desk's own line; 'account' can (a balance is not in it,
      // but a list change is how a desk that just came up first shows), so the two that matter repaint it.
      if (why.has('state') || why.has('account')) paintDeskStatus();
    });
  }
  registerChartMenuTrading();
}

window.HBTradeUI = { mount, placeOrder, symbolAction, flattenAccount, cancelOrder, closeLine, moveLine, confirm, busy,
  onBusyChange, onTradeChange, effectiveMode, editableIds, fillIds, tradeOf, setCellTrade, setCellAlgo, botKill,
  killBusy, accountRows, toggleAccount, pickAlgo, armPending, paintDeskStatus };
})();
