import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* tradeui.js and replayui.js are browser-only IIFEs (no module.exports): this loads the REAL files under a small
   window/document shim with a fake desk client, so the money-path rules of the 2026-09-27 accounts-per-chart
   plan (Task 1, fix round 1) are exercised through the code the page runs -- effectiveMode, toggleAccount,
   placeOrder's one-click / confirm choice, and replayui's session ends -- not re-implemented in a test double.
   Nothing here opens a connection: every "send" lands in the fake desk's `sent` list. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const R = require('../../homebase/static/charts/replay.js');

const acct = (id, label, env, extra = {}) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const STATE = {
  enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [acct('sim041', 'SIM0000041', 'demo'), acct('live099', 'FAKELIVE099', 'live')],
  bot: { date: '2026-09-27', strategies: {} },
};

/* The smallest element that confirm() and the replay overlay touch. */
class El {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.listeners = {}; this.className = ''; this.textContent = ''; }
  append(...n) { this.children.push(...n); }
  appendChild(n) { this.children.push(n); return n; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  get classList() { return { add: () => {}, toggle: () => {}, contains: () => false }; }
  focus() {}
  blur() {}
}

const desk = {
  state: STATE, down: '', quotes: { NQ: { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: 0 } },
  prefs: { oneClick: true, qty: 1, slTicks: 0, tpTicks: 0 },
  sent: [], toasts: [], subs: new Set(),
  mode(ct) { return T.tradeMode(desk, ct); },
  gate() { return T.deskGate(desk); },
  toast(tone, text) { desk.toasts.push(text); },
  send(action, body) { desk.sent.push({ action, body }); return Promise.resolve(); },
  on(fn) { desk.subs.add(fn); return () => desk.subs.delete(fn); },
  setPrefs(p) { Object.assign(desk.prefs, p); },
};

const dialogs = [];
let cells = [];
const page = {
  cells: () => cells, cur: () => cells[0], clockMs: () => 1000,
  mk: (tag, cls, text) => { const e = new El(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; },
  openDialog: (title) => { const box = new El('div'); dialogs.push({ title, box }); return box; },
  setDialogClose() {}, closeDialog() {}, deskUrl: () => 'http://127.0.0.1:8850/', dialogOpen: () => false,
};

global.window = { HBTrade: T, HBReplay: R, HBDeskClient: desk, HBIcons: {}, HBChartMenu: { register() {} } };
global.document = { getElementById: () => null, createElement: (t) => new El(t), activeElement: null };
require('../../homebase/static/charts/tradeui.js');
require('../../homebase/static/charts/replayui.js');
const UI = global.window.HBTradeUI, RUI = global.window.HBReplayUI;
UI.mount(page);

function chart(accounts = [], extra = {}) {
  const c = { cfg: { root: 'NQ', trade: { accounts }, algo: null, ...extra }, shown: { root: 'NQ' }, tick: 0.25, pv: 20,
    replay: null, ov: [], bars: [], note() {}, host: { send() {} } };
  cells = [c];
  return c;
}
const flush = () => new Promise((r) => setImmediate(r));
function reset() { desk.sent.length = 0; desk.toasts.length = 0; dialogs.length = 0; desk.prefs.oneClick = true; }
/* The confirm dialog's primary button (its label is the action: Buy / Sell / Flatten ...). */
function clickPrimary(label) {
  const box = dialogs[dialogs.length - 1].box, foot = box.children.find((x) => x.className === 'dlg-foot');
  foot.children.find((b) => b.textContent === label).onclick();
}

test('Critical 1: a LIVE account armed + ticked in the Trading tab carries no mark and survives every desk event', async () => {
  reset();
  const c = chart();
  assert.equal(UI.toggleAccount(c, 'live099'), 'arming');   // first click arms only
  assert.deepEqual(c.cfg.trade.accounts, []);
  assert.equal(UI.toggleAccount(c, 'live099'), 'armed');    // second click ticks
  assert.deepEqual(c.cfg.unverified, []);
  for (let i = 0; i < 100; i++) assert.deepEqual(T.verifyCells([c.cfg], STATE), { dropped: [], changed: [] });   // balance ticks
  assert.deepEqual(c.cfg.trade.accounts, ['live099']);
  assert.deepEqual(UI.effectiveMode(c), { mode: 'on', reason: '', accounts: ['live099'] });
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });
  await flush();
  assert.equal(desk.sent.length, 1);
  assert.deepEqual(desk.sent[0].body.accounts, ['live099']);
  UI.toggleAccount(c, 'live099');   // untick (and disarm) for the next tests
});

test('Critical 1 + Minor 4: an id a load restored is refused by the mode itself until the desk vouches, then dropped once', async () => {
  reset();
  const armedElsewhere = chart();
  UI.toggleAccount(armedElsewhere, 'live099'); UI.toggleAccount(armedElsewhere, 'live099');   // armed earlier this session
  const c = chart(['sim041', 'live099'], { unverified: ['sim041', 'live099'] });                // a load while the desk was down
  assert.deepEqual(UI.effectiveMode(c), { mode: 'none', reason: T.CHECKING_ACCOUNTS, accounts: [] });
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });
  await flush();
  assert.equal(desk.sent.length, 0, 'nothing reaches an unverified id, even one armed earlier in the session');
  const v = T.verifyCells([c.cfg], STATE);
  assert.deepEqual(v.dropped, ['live099']);
  assert.deepEqual(c.cfg.trade.accounts, ['sim041']);
  assert.deepEqual(UI.effectiveMode(c), { mode: 'on', reason: '', accounts: ['sim041'] });
  assert.deepEqual(T.verifyCells([c.cfg], STATE).dropped, [], 'the drop (and its toast) happens once');
  UI.toggleAccount(armedElsewhere, 'live099');
});

test('Important 2: a reconnect mid-practice latches the chart -- nothing sends until "Resume live trading"', async () => {
  reset();
  const c = chart(['sim041']);
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1, playing: true });   // a replay is running
  assert.equal(UI.effectiveMode(c).reason, 'Replay — trading is off');
  RUI.onReconnect([c]);                                     // the socket dropped and came back
  assert.equal(c.replay, null);
  assert.deepEqual(UI.effectiveMode(c), { mode: 'none', reason: T.REPLAY_ENDED, accounts: [] });
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });   // the "practice" click, one-click on
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 0);
  assert.deepEqual(desk.toasts, [T.REPLAY_ENDED]);
  UI.resumeLive(c);                                          // the legend's explicit acknowledgement
  assert.equal(UI.effectiveMode(c).mode, 'on');
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });
  await flush();
  assert.equal(desk.sent.length, 0, 'even after Resume, the first order confirms although one-click is on');
  assert.equal(dialogs.length, 1);
  clickPrimary('Buy');
  await flush();
  assert.equal(desk.sent.length, 1);
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });   // back to one-click
  await flush();
  assert.equal(desk.sent.length, 2);
  assert.equal(dialogs.length, 1);
});

test('Important 2: a server `stopped` the user did not ask for latches; the user\'s own Exit only forces the confirm', async () => {
  reset();
  const c = chart(['sim041']);
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1 });
  RUI.onState(c, { id: 'c1', stopped: true });              // end of data / a crashed stream
  assert.equal(UI.effectiveMode(c).reason, T.REPLAY_ENDED);
  UI.resumeLive(c);
  c.cfg.replayConfirm = false;

  // the user's own Exit: the overlay marks the session, then the server answers `stopped`
  const d = chart(['sim041']);
  RUI.onState(d, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1 });
  RUI.exitReplay(d);                                        // what the replay bar's × runs
  RUI.onState(d, { id: 'c1', stopped: true });
  assert.equal(UI.effectiveMode(d).mode, 'on', 'the user chose to leave: no latch');
  UI.placeOrder({ cell: d, root: 'NQ', side: 'Sell', type: 'Market', qty: 1 });
  await flush();
  assert.equal(desk.sent.length, 0, 'but the first real order after any replay always confirms');
  assert.equal(dialogs.length, 1);
});

test('Important 2: a destroyed chart and a refused replay_start latch too', () => {
  reset();
  const c = chart(['sim041']);
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1 });
  RUI.cellDestroyed(c);
  assert.equal(UI.effectiveMode(c).reason, T.REPLAY_ENDED);
  const d = chart(['sim041']);
  d.replay = { date: '2026-09-24' };
  RUI.onError(d, { op: 'replay_start', error: 'no data' });
  assert.equal(UI.effectiveMode(d).reason, T.REPLAY_ENDED);
});
