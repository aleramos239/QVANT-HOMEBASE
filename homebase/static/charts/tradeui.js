/* Homebase Charts — HBTradeUI: the Trade toolbar menu (accounts, one-click, qty, SL/TP ticks), the confirm
   dialog ($ + RR 1:X preview), the trading actions (each sends through HBDeskClient, which owns toasts), and
   the Buy/Sell limit/stop + Cancel all / Flatten / Reverse items in the chart's right-click menu
   (HBChartMenu.register('trading', …)).

   Trading is PER CHART (2026-09-27 plan, Task 2): each chart's cell config carries `trade: {on, accounts}`, and
   every order-sending path takes its accounts from the chart it was started from (the Buy/Sell block, a chart-menu
   item, a line's drag or ×, the order panel). The Trade menu edits the SELECTED chart. The bottom panel's
   per-account Close/Cancel act on the named account only (accountGate).

   A chart's algo (2026-09-27 plan, Task 3): `cell.cfg.algo` is set through setCellAlgo; its Kill (botKill) goes
   through the same confirm + guardedSend path, needs the LIVE arm for a LIVE account of the bot, and is offered
   whatever the chart's Trading switch says (it is the emergency stop, not trading).

   Safety (ruling S4/S5, and the 2026-09-27 review of Tasks 3-4):
     - every action re-reads its gate (the chart's mode from HBDesk.mode(that chart's trade), or the named
       account's gate) at the moment it actually sends, not at the moment the user clicked or the confirm dialog
       opened — the desk, the chart's accounts, its switch or a LIVE arm can all change while a dialog is open;
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
let inFlight = false;    // one send at a time (review item 2; the 2026-09-27 review of Task 5 makes this a toast, not a silent drop)
const busySubs = new Set();   // notified synchronously on every inFlight flip, so the panel and the chart's lines grey out immediately
const tradeSubs = new Set();  // notified when a chart's trade config or a LIVE arm changes (the charts' overlays re-render)
let menuCell = null;          // the chart the open Trade menu was filled for

/* ---- one chart's trade config and mode ---- */
/* The chart's {on, accounts}, sanitised; a missing chart is off with no accounts. */
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
  updateTradeButton();
  refillIfOpen();
}
/* Set a chart's trade config (sanitised). The page saves it: an account-list change is a layout change (the
   layout reads Unsaved), the switch alone is not (a load always brings it back off). `quiet`: the caller saves
   (a template preview in the Settings dialog, the one-time migration). */
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
/* The page's selected chart changed: the toolbar dot and an open Trade menu follow it. */
function selectionChanged() { updateTradeButton(); refillIfOpen(); }
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
  return ids.map((id) => { const a = list.find((x) => x.id === id); return a ? { label: a.label, env: a.env } : { label: id, env: 'demo' }; });
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
      const env = r.env === 'live' ? 'LIVE' : r.env === '?' ? '?' : 'DEMO';
      row.append(page.mk('span', '', r.label), page.mk('span', `env${r.env === 'live' ? ' live' : ''}`, env));
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
     - `exits: {sl, tp}`: explicit SL/TP prices (null = that side off), used INSTEAD of the Trade menu's tick
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
  if (busy()) { D().toast('err', 'Another action is in flight'); return; }
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
    .then((ok) => { if (ok) guardedSend('bot-kill', g, build); });
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

/* ---- the Trade toolbar menu ---- */
function dotClass(mode) { return mode === 'on' ? 'ok' : mode === 'down' ? 'bad' : 'warn'; }
function updateTradeButton() {
  const btn = document.getElementById('tbTrade'), dot = document.getElementById('tbTradeDot');
  if (!btn || !dot) return;
  const m = effectiveMode(page && page.cur());   // the selected chart's
  dot.className = 'dot ' + dotClass(m.mode);
  btn.title = m.reason || 'Trade';
}

function envSpan(env) { return page.mk('span', 'env' + (env === 'live' ? ' live' : ''), String(env || '').toUpperCase()); }
function dotSpan(ok) { return page.mk('span', 'dot' + (ok ? ' ok' : ' bad')); }

/* Ticking a LIVE account needs a second click within 3 s (S5) -- including one already on a chart's list from a
   saved layout, since liveConfirmed starts empty every load (the review's "re-confirm on first use after
   reload"). The arm is per account for the session (unchanged); the tick is the chart's. */
function setAccountTicked(cell, id, on) {
  const t = tradeOf(cell), ids = new Set(t.accounts);
  if (on) ids.add(id); else ids.delete(id);
  setCellTrade(cell, { on: t.on, accounts: [...ids] });
}
function onTickChange(cell, a, cb) {
  if (!cell || cell !== page.cur()) { refillIfOpen(); return; }   // the menu edits the selected chart only
  // fix round 1: a LIVE account on this chart's list but not armed this session (it came back with a layout) is
  // shown ticked-but-not-armed; a click REMOVES it from the chart -- it never starts the arm flow (arming is a
  // separate action: tick it again afterwards). Decided from the chart's list, not the checkbox's toggled value.
  if (T.acctTick(a, tradeOf(cell).accounts, liveConfirmed) === 'unarmed') {
    if (armLive === a.id) { armLive = null; clearTimeout(armTimer); }
    setAccountTicked(cell, a.id, false);
    return;
  }
  const wantTick = cb.checked;
  if (wantTick && a.env === 'live' && !liveConfirmed.has(a.id)) {
    if (armLive === a.id) {   // the second click, within the window: arm it for real
      liveConfirmed.add(a.id);
      clearTimeout(armTimer); armLive = null;
      setAccountTicked(cell, a.id, true);
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
  setAccountTicked(cell, a.id, wantTick);
}

/* The checkbox for one row state: 'ticked', 'off', or 'unarmed' (indeterminate: on the chart's list, not armed).
   An account already on the list can always be removed, even while it is not tradable. */
function paintTick(cb, a, state) {
  cb.dataset.state = state;
  cb.disabled = !a.tradable && state === 'off';
  cb.checked = state === 'ticked';
  cb.indeterminate = state === 'unarmed';
  cb.title = state === 'unarmed' ? "On this chart's list but not armed this session — click to remove it" : '';
}
function acctRow(cell, a, t) {
  const id = `tm-acct-${a.id}`, row = page.mk('div', 'tm-row');
  const cb = page.mk('input'), state = T.acctTick(a, t.accounts, liveConfirmed);
  cb.type = 'checkbox'; cb.id = id; cb.dataset.tm = `acct:${a.id}`;
  paintTick(cb, a, state);
  cb.onchange = () => onTickChange(cell, a, cb);
  const lab = page.mk('label', 'tm-label');
  lab.htmlFor = id;
  if (armLive === a.id) {
    lab.appendChild(page.mk('span', 'tm-arm', 'Tick LIVE — real orders. Click again'));
  } else {
    lab.appendChild(page.mk('span', 'tm-name', a.label));
    if (state === 'unarmed') lab.appendChild(page.mk('span', 'tm-unarmed', 'LIVE · not armed'));
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

/* review item 4: a quote (up to 4/s) used to rebuild this whole menu, losing typed values and clicks. Nothing
   in the menu depends on a quote at all, so quote-only (and bot/fill) events now do nothing here; a genuine
   'account' event patches only that row's connection dot, balance and tradable state in place (keyed on
   data-tm="acct:<id>"), leaving the qty/SL/TP inputs, the one-click switch and any LIVE arm in progress alone.
   A row that has gone missing (the account list itself changed) falls back to a full fillMenu(). */
function patchAccountRows(m) {
  const st = D().state, t = tradeOf(menuCell);
  if (!st || menuCell !== page.cur()) return false;
  const accounts = st.accounts || [];
  if (m.querySelectorAll('.tm-row').length !== accounts.length) return false;
  for (const a of accounts) {
    const cb = m.querySelector(`[data-tm="acct:${a.id}"]`);
    const row = cb && cb.closest('.tm-row');
    if (!row) return false;
    const state = T.acctTick(a, t.accounts, liveConfirmed);
    if (cb.dataset.state !== state) return false;   // the row's label changes with its state: a full fill
    paintTick(cb, a, state);
    const bal = row.querySelector('.tm-bal');
    if (bal) bal.textContent = T.money(a.balance);
    const dot = row.querySelector('.dot');
    if (dot) dot.className = 'dot' + (a.connected ? ' ok' : ' bad');
    if (armLive !== a.id) {
      const lab = row.querySelector('.tm-label'), err = lab && lab.querySelector('.tm-err');
      if (!a.tradable && !err && lab) lab.appendChild(page.mk('span', 'tm-err', a.error || 'not tradable'));
      else if (a.tradable && err) err.remove();
      else if (err) err.textContent = a.error || 'not tradable';
    }
  }
  return true;
}

/* The header: "Trading on this chart — NQ · chart 2" and the chart's own Trading switch. */
function cellHeader(cell, t) {
  const head = page.mk('div', 'tm-head'), n = page.cells().indexOf(cell) + 1;
  const title = cell ? `Trading on this chart — ${rootOfCell(cell) || '—'} · chart ${n}` : 'Trading on this chart';
  head.appendChild(page.mk('span', 'tm-title', title));
  if (!cell) return head;
  const sw = page.mk('button', 'switch' + (t.on ? ' on' : ''));
  sw.type = 'button';
  sw.setAttribute('role', 'switch');
  sw.setAttribute('aria-checked', String(t.on));
  sw.setAttribute('aria-label', `Trading on chart ${n}`);
  sw.dataset.tm = 'cellon';
  // a chart in Bar Replay can never trade (Global Constraints): the switch cannot re-arm it while replaying
  sw.disabled = !!cell.replay;
  if (cell.replay) sw.title = 'This chart is in replay';
  sw.onclick = () => {
    if (cell !== page.cur() || cell.replay) { refillIfOpen(); return; }   // the menu edits the selected chart only
    const now = tradeOf(cell);
    setCellTrade(cell, { on: !now.on, accounts: now.accounts });
  };
  head.appendChild(sw);
  return head;
}

function fillMenu(m) {
  const key = focusKey(m);
  m.replaceChildren();
  const cell = page.cur() || null, t = tradeOf(cell);
  menuCell = cell;
  const st = D().state, prefs = D().prefs, gate = D().gate(), mode = effectiveMode(cell);   // review item 6: the armed/effective mode
  m.appendChild(cellHeader(cell, t));
  if (gate && gate.mode === 'down') {
    m.appendChild(page.mk('div', 'tm-status', `Desk unreachable — ${gate.reason}`));
  } else if (gate && gate.mode === 'off') {
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
    if (t.on && mode.mode !== 'on') m.appendChild(page.mk('div', 'tm-status tm-why', mode.reason));
  }
  for (const a of (st && st.accounts) || []) m.appendChild(acctRow(cell, a, t));
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
  if (window.HBDeskClient) {
    window.HBDeskClient.on((why) => {
      updateTradeButton();
      const m = document.querySelector('.menu-trade');
      if (!m) return;
      if (why.has('state') || why.has('prefs')) { fillMenu(m); return; }
      if (why.has('account') && !patchAccountRows(m)) fillMenu(m);
      // 'quote' / 'bot' / 'fill' alone: nothing in this menu depends on them (review item 4)
    });
  }
  registerChartMenuTrading();
}

window.HBTradeUI = { mount, placeOrder, symbolAction, flattenAccount, cancelOrder, closeLine, moveLine, confirm, busy,
  onBusyChange, onTradeChange, effectiveMode, editableIds, fillIds, tradeOf, setCellTrade, setCellAlgo, selectionChanged, botKill };
})();
