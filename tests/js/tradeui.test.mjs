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

/* fix round 3 (coordinator review of feat/replay-tv): Select bar ▾'s "Select date…" and "First available
   date" both call doStart() while a session is ALREADY running -- it must save that old session's practice
   trades (savePracticeSession) before overwriting `sessions`, exactly like every other end-of-session path
   (clearSession, cellDestroyed) already does, and say so with the same shape of note resetPracticeForRewind
   gives a rewind past an open position. */
test('doStart, called mid-session, notes the reset (Select date… / First available date overwriting a session)', () => {
  reset();
  const c = chart(['sim041']);
  const notes = [];
  c.note = (m) => notes.push(m);
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1 });   // session A is running
  assert.equal(c.replay.date, '2026-09-24');
  RUI.doStart(c, '2026-09-20', '09:30');                                     // Select date… / First available date
  assert.equal(c.replay.date, '2026-09-20', 'the session is overwritten, not merged, exactly as before');
  assert.ok(notes.some((n) => n.includes('Practice book reset')),
    'the same "Practice book reset" shape of note the rewind-past-a-position path gives');
});

test('doStart: starting fresh (nothing was replaying yet) never shows the reset note', () => {
  reset();
  const c = chart(['sim041']);
  const notes = [];
  c.note = (m) => notes.push(m);
  assert.equal(c.replay, null);
  RUI.doStart(c, '2026-09-20', '09:30');
  assert.equal(c.replay.date, '2026-09-20');
  assert.deepEqual(notes, []);
});

/* ---- fix round 2 (task-1-rereview.md): the replay-end latch survives ANY grid rebuild ----
   app.js's buildGrid destroys every cell (HBReplayUI.cellDestroyed) and then builds new ones -- from a NEW layout
   object when it is a layout load (or a layout-tab switch), so a flag on the old cell config would be thrown
   away. The latch is held by grid POSITION at page level and re-applied by HBTradeUI.gridRebuilt. These drive
   exactly the order buildGrid runs them in: cellDestroyed over the old cells, then gridRebuilt over the new. */
function rebuild(newCells) {
  for (const old of cells) RUI.cellDestroyed(old);   // buildGrid's first loop, while `cells` is still the old grid
  cells = newCells;
  UI.gridRebuilt(cells);                             // buildGrid, once the new cells exist
}
const practicing = (accounts) => {
  const c = chart(accounts);
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1, playing: true });
  return c;
};
const fresh = () => ({ cfg: { root: 'NQ', trade: { accounts: ['sim041'] }, algo: null }, shown: { root: 'NQ' }, tick: 0.25,
  pv: 20, replay: null, ov: [], bars: [], note() {}, host: { send() {} } });

test('fix round 2: practicing, then a layout load -- the rebuilt chart sends nothing and opens no dialog until Resume', async () => {
  reset();
  practicing(['sim041']);
  const next = fresh();                    // loadLayout: a brand-new config object from the saved layout
  rebuild([next]);
  assert.deepEqual(UI.effectiveMode(next), { mode: 'none', reason: T.REPLAY_ENDED, accounts: [] });
  UI.placeOrder({ cell: next, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });   // one-click is on
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 0);
  UI.resumeLive(next);
  UI.placeOrder({ cell: next, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });
  await flush();
  assert.equal(desk.sent.length, 0, 'after Resume the first order still confirms');
  assert.equal(dialogs.length, 1);
  clickPrimary('Buy');
  await flush();
  assert.equal(desk.sent.length, 1);
});

test('fix round 2: the same through a grid-size change -- the latch lands on whatever chart now sits at that position', () => {
  reset();
  const a = fresh(), b = practicing(['sim041']);
  cells = [a, b];                           // chart 2 (position 1) is the one practicing
  const na = fresh(), nb = fresh(), nc = fresh(), nd = fresh();
  rebuild([na, nb, nc, nd]);                // 2 -> 4 charts
  assert.equal(UI.effectiveMode(na).mode, 'on');
  assert.equal(UI.effectiveMode(nb).reason, T.REPLAY_ENDED);
  assert.equal(UI.effectiveMode(nc).mode, 'on');
  rebuild([fresh(), fresh()]);              // the entry was consumed: the next rebuild latches nothing new
  assert.equal(UI.effectiveMode(cells[1]).mode, 'on');
});

test('fix round 2: a grid that SHRINKS past the practicing chart drops the entry cleanly', () => {
  reset();
  const a = fresh(), b = practicing(['sim041']);
  cells = [a, b];
  const only = fresh();
  rebuild([only]);                          // 2 -> 1: position 1 no longer exists
  assert.equal(UI.effectiveMode(only).mode, 'on');
  const later = [fresh(), fresh()];
  rebuild(later);                           // growing back later must not resurrect it
  assert.equal(UI.effectiveMode(later[1]).mode, 'on');
});

test('fix round 2: app.js buildGrid re-applies the latch after building, for every caller', async () => {
  const { readFileSync } = await import('node:fs');
  const src = readFileSync(new URL('../../homebase/static/charts/app.js', import.meta.url), 'utf8');
  const body = src.slice(src.indexOf('function buildGrid()'), src.indexOf('function select('));
  const destroyed = body.indexOf('HBReplayUI.cellDestroyed'), rebuilt = body.indexOf('HBTradeUI.gridRebuilt(cells)');
  assert.ok(destroyed >= 0 && rebuilt > destroyed, 'buildGrid: cellDestroyed over the old cells, then gridRebuilt(cells) over the new');
  assert.ok(body.indexOf('new Cell(') < rebuilt, 'gridRebuilt runs once the new cells exist');
});

/* ---- release/4: the latch through a LAYOUT-TAB switch, driven through app.js's OWN code ----
   feat/layout-tabs' switchTab rebuilds the grid; the release merge routes it (and add / reopen / close / duplicate
   / delete) through loadLayout -> buildGrid -> HBTradeUI.gridRebuilt. app.js is a browser IIFE, so this lifts
   the REAL switchTab, loadLayout and buildGrid source out of it and runs them in a vm context against the real
   tradeui.js / replayui.js / layouts.js; only the DOM, the Cell class and the network are stubbed. */
test('release/4: practicing in replay, then a layout-TAB switch -- the next one-click sends nothing and opens no dialog', async () => {
  const { readFileSync } = await import('node:fs');
  const vm = await import('node:vm');
  const src = readFileSync(new URL('../../homebase/static/charts/app.js', import.meta.url), 'utf8');
  const lift = (name) => {
    const m = new RegExp(`^(async )?function ${name}\\(`, 'm').exec(src);
    assert.ok(m, `app.js defines ${name}`);
    return src.slice(m.index, src.indexOf('\n}\n', m.index) + 2);
  };
  const L = require('../../homebase/static/charts/layouts.js');
  reset();
  const saved = (accounts) => ({ grid: 1, cells: [{ root: 'NQ', spec: '1m', indicators: [], trade: { accounts } }] });
  class Cell {
    constructor(slot, cfg, host) {
      Object.assign(this, { cfg, host: { send() {}, id: host.id }, shown: { root: cfg.root }, tick: 0.25, pv: 20, replay: null,
        ov: [], bars: [], destroyed: false });
    }
    note() {}
    destroy() { this.destroyed = true; }
    applyFold() {}
    setSelected() {}
  }
  const el = () => ({ style: {}, dataset: {}, replaceChildren() {}, appendChild() {} });
  const ctx = vm.createContext({
    window: global.window, T, Cell, GRIDS: { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] }, $: () => el(), mk: () => el(),
    closeHotkeyBox() {}, deskState: () => STATE, starter: () => ({ root: 'NQ', spec: '1m', indicators: [], trade: { accounts: [] } }),
    hostFor: (id) => ({ id }), legendFolded: () => false, select() {}, saveLast() {}, dropLiveAccounts() {}, renderTabs() {},
    renderToolbar() {}, sbNote(t) { throw new Error('sbNote: ' + t); },
    // readLayout's safety half (HBTrade.loadedTrade) is pinned elsewhere; here: a NEW config object per load
    readLayout: (v) => ({ grid: v.grid, cells: v.cells.map((c) => ({ ...c, trade: { accounts: [...c.trade.accounts] }, algo: null })) }),
    layoutBody: () => ({ grid: ctx.layout.grid, cells: ctx.layout.cells.map(({ root, spec, indicators, trade }) => ({ root, spec, indicators, trade })) }),
    putLayout: async () => '',
  });
  vm.runInContext(`
    let layout = { grid: 1, cells: [], name: 'A', dirty: false }, cells = [], selected = 0, nextId = 1, tabSnapshot = null;
    let layoutsCache = {};
    ${lift('buildGrid')}
    ${lift('loadLayout')}
    ${lift('switchTab')}
    globalThis.api = { buildGrid, loadLayout, switchTab, get cells() { return cells; }, get layout() { return layout; },
      setCache(c) { layoutsCache = c; } };
  `, ctx);
  ctx.window.HBLayouts = L;
  const api = ctx.api;
  Object.defineProperty(ctx, 'layout', { get: () => api.layout });
  page.cells = () => api.cells;            // the page's own view of the grid, as app.js's page object has it
  try {
    api.setCache({ A: saved(['sim041']), B: saved(['sim041']) });
    api.loadLayout('A', saved(['sim041']));            // tab A on screen: one chart, a DEMO account ticked
    const before = api.cells[0];
    RUI.onState(before, { id: before.host.id, date: '2026-09-24', cursor_ms: 0, speed: 1, playing: true });
    assert.ok(before.replay, 'tab A\'s chart is practicing in Bar Replay');
    await api.switchTab('B');                          // the layout-tab click
    const after = api.cells[0];
    assert.notEqual(after, before, 'the switch rebuilt the grid');
    assert.equal(before.destroyed, true);
    assert.equal(after.replay, null, 'the new chart is not in replay: only the latch can stop it');
    assert.deepEqual(UI.effectiveMode(after), { mode: 'none', reason: T.REPLAY_ENDED, accounts: [] });
    UI.placeOrder({ cell: after, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });   // one-click is on
    await flush();
    assert.equal(desk.prefs.oneClick, true);
    assert.equal(desk.sent.length, 0, 'nothing reaches the desk');
    assert.equal(dialogs.length, 0, 'and no confirm dialog opens');
  } finally {
    page.cells = () => cells;
  }
});

/* Every layout-tab path that replaces the charts on screen must do it through loadLayout -> buildGrid (the only
   place gridRebuilt runs): no tab path builds cells, swaps `layout`, or rebuilds the grid by itself. */
test('release/4: every layout-tab path rebuilds only through loadLayout -> buildGrid', async () => {
  const { readFileSync } = await import('node:fs');
  const src = readFileSync(new URL('../../homebase/static/charts/app.js', import.meta.url), 'utf8');
  const body = (name) => {
    const m = new RegExp(`^(async )?function ${name}\\(`, 'm').exec(src);
    assert.ok(m, `app.js defines ${name}`);
    return src.slice(m.index, src.indexOf('\n}\n', m.index) + 2);
  };
  const lb = body('loadLayout');
  assert.ok(lb.indexOf('buildGrid()') > lb.indexOf('layout = '), 'loadLayout swaps the layout, then builds the grid');
  assert.match(body('switchTab'), /loadLayout\(name, saved\)/);
  assert.match(body('reopenTab'), /switchTab\(name\)/);
  for (const name of ['switchTab', 'addTab', 'duplicateTab', 'renameTab', 'closeTab', 'deleteLayoutTab', 'reopenTab',
    'addTabMenu', 'tabContextMenu', 'renderTabs', 'loadTabs']) {
    const b = body(name);
    assert.doesNotMatch(b, /new Cell\(|\bcells = |\blayout = |#grid|replaceChildren\(\.\.\.cells/, `${name} never rebuilds the grid itself`);
  }
  // the only places that construct charts or assign the grid are buildGrid itself
  const outside = src.replace(body('buildGrid'), '');
  assert.doesNotMatch(outside, /new Cell\(/);
  assert.doesNotMatch(outside, /^\s*cells = /m);
});

/* ---- the PAPER account through the REAL send path (2026-09-27 accounts/paper plan, Task 2) ---- */
test('PAPER: the real send path routes the paper part to the paper client only; a Bar Replay chart sends to neither', async () => {
  reset();
  const paperSent = [];
  const paperAcct = acct('paper', 'PAPER', 'paper', {
    positions: [{ symbol: 'NQZ6', net: 2, avg_price: 30000, root: 'NQ', point_value: 20 }],
    orders: [{ order_id: '5', symbol: 'NQZ6', side: 'Sell', type: 'Limit', qty: 2, price: 30010, stop_price: null, owner: null }] });
  const was = desk.state;
  desk.state = T.withPaper(STATE, paperAcct);
  global.window.HBPaperClient = {
    send(action, body) { paperSent.push({ action, body }); return Promise.resolve({ status: 200, data: { results: { paper: { ok: true, order_id: '9' } } } }); },
  };
  try {
    const mixed = chart(['sim041', 'paper']);
    UI.placeOrder({ cell: mixed, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });   // one-click on
    await flush(); await flush();
    assert.deepEqual(desk.sent.map((s) => s.body.accounts), [['sim041']], 'the desk never sees PAPER');
    assert.deepEqual(paperSent.map((s) => [s.action, s.body.accounts]), [['order', ['paper']]]);
    assert.equal(desk.sent[0].body.client_id, paperSent[0].body.client_id);
    assert.ok(desk.toasts.includes('PAPER · order accepted'));

    reset(); paperSent.length = 0;
    const paperOnly = chart(['paper']);
    UI.symbolAction(paperOnly, 'flatten', 'NQ');
    await flush(); await flush();                            // one action in flight at a time (the page-wide lock)
    const line = T.linesFor(desk.state, 'NQ', ['paper']).find((g) => g.kind === 'tp');
    UI.closeLine(paperOnly, line, 'NQ', 0.25);
    await flush(); await flush();
    UI.flattenAccount('paper', 'NQ');                        // the bottom panel's per-account Close
    await flush(); await flush();
    assert.equal(desk.sent.length, 0, 'a PAPER-only chart makes no desk call at all');
    assert.deepEqual(paperSent.map((s) => s.action), ['flatten', 'cancel', 'flatten']);
    assert.deepEqual(paperSent[1].body, { client_id: paperSent[1].body.client_id, account: 'paper', order_id: '5' });

    reset(); paperSent.length = 0;
    RUI.onState(paperOnly, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1, playing: true });   // Bar Replay
    UI.placeOrder({ cell: paperOnly, root: 'NQ', side: 'Buy', type: 'Market', qty: 1 });
    UI.symbolAction(paperOnly, 'flatten', 'NQ');
    await flush();
    assert.equal(paperSent.length + desk.sent.length, 0, 'a replaying chart never reaches the paper book either');
    assert.deepEqual(desk.toasts, ['Replay — trading is off', 'Replay — trading is off']);
  } finally {
    desk.state = was;
    delete global.window.HBPaperClient;
  }
});

test('one-click per surface: the chart block and the order panel read their own switch, the menu reads oneClick', async () => {
  reset();
  const c = chart(['sim041']);
  Object.assign(desk.prefs, { oneClick: false, oneClickChart: true, oneClickPanel: false });
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface: 'chart' });
  await flush();
  assert.equal(dialogs.length, 0);
  assert.equal(desk.sent.length, 1, 'the chart block sends at once');
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface: 'panel' });
  await flush();
  assert.equal(dialogs.length, 1, 'the order panel asks first');
  assert.equal(desk.sent.length, 1);
  clickPrimary('Buy');
  await flush();
  assert.equal(desk.sent.length, 2);
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Sell', type: 'Market', qty: 1 });   // the chart menu: oneClick (off)
  await flush();
  assert.equal(dialogs.length, 2);
  Object.assign(desk.prefs, { oneClickChart: undefined, oneClickPanel: undefined });
});

test('no more "view only": a chart manages ANY tradable account\'s lines; the arm, replay and unlisted rules still hold', async () => {
  reset();
  const c = chart([]);                                        // nothing ticked on this chart
  assert.deepEqual(UI.editableIds(c), ['sim041'], 'an unarmed LIVE account manages nothing (fix round 1, item 3)');
  const line = (account, extra = {}) => ({ key: 'k', kind: 'order', side: 'Buy', type: 'Limit', price: 29990, qty: 1,
    editable: true, legs: [{ account, who: '…', qty: 1, order_id: '77' }], ...extra });
  UI.closeLine(c, line('sim041'), 'NQ', 0.25);                 // oneClick on: sends at once
  await flush();
  assert.deepEqual(desk.sent.map((s) => [s.action, s.body.account, s.body.order_id]), [['cancel', 'sim041', '77']]);
  UI.moveLine(c, line('sim041'), 29980, 'NQ', 0.25);
  await flush();
  assert.deepEqual(desk.sent[1].body, { client_id: desk.sent[1].body.client_id, account: 'sim041', order_id: '77', price: 29980 });
  UI.closeLine(c, line('live099'), 'NQ', 0.25);                // LIVE, not armed this session
  await flush();
  assert.equal(desk.sent.length, 2);
  assert.match(desk.toasts.at(-1), /LIVE/);
  UI.closeLine(c, line('ghost'), 'NQ', 0.25);                  // an account the desk does not list
  await flush();
  assert.equal(desk.sent.length, 2);
  c.replay = { id: 'r' };                                     // a replaying chart manages nothing
  assert.deepEqual(UI.editableIds(c), []);
  UI.closeLine(c, line('sim041'), 'NQ', 0.25);
  await flush();
  assert.equal(desk.sent.length, 2);
  assert.equal(desk.toasts.at(-1), 'Replay — trading is off');
});

test('addExit: the dropped SL / TP goes out as `exits` for the whole position, frozen, split desk / paper', async () => {
  reset();
  const paperSent = [];
  const pos = (net) => [{ symbol: 'NQZ6', net, avg_price: 30000, root: 'NQ', point_value: 20 }];
  const was = desk.state;
  desk.state = T.withPaper({ ...STATE, accounts: [acct('sim041', 'SIM0000041', 'demo', { positions: pos(2) }), STATE.accounts[1]] },
    acct('paper', 'PAPER', 'paper', { positions: pos(2) }));
  global.window.HBPaperClient = {
    send(action, body) { paperSent.push({ action, body }); return Promise.resolve({ status: 200, data: { results: { paper: { ok: true } } } }); },
  };
  try {
    const c = chart([]);                                           // nothing ticked: lines are still manageable
    const groups = T.linesFor(desk.state, 'NQ', UI.editableIds(c));
    const long = groups.find((g) => g.kind === 'position' && !g.paper), paper = groups.find((g) => g.kind === 'position' && g.paper);
    assert.deepEqual(T.exitHandles(long, groups), { sl: true, tp: true });
    desk.prefs.oneClick = false;                                   // the confirm shows first
    UI.addExit(c, long, 'tp', 30010.1, 'NQ', 0.25);
    assert.equal(dialogs.length, 1);
    assert.equal(dialogs[0].title, 'Add TP 2 @ 30,010.00 · …041');
    const warn = dialogs[0].box.children[0].children.find((x) => x.className === 'cf-note cf-warn');
    assert.equal(warn && warn.textContent, T.GTC_WARN, 'exits stay GTC: the confirm says so (item 8)');
    desk.quotes.NQ = { ...desk.quotes.NQ, last: 30001 };           // the market moves (still below the TP): unchanged body
    clickPrimary('Add target');
    await flush(); await flush();
    assert.equal(desk.sent.length, 1);
    assert.deepEqual(desk.sent[0], { action: 'exits', body: { client_id: desk.sent[0].body.client_id, accounts: ['sim041'], root: 'NQ',
      tp_price: 30010, expected_net: { sim041: 2 } } }, 'the size the confirm showed rides along (item 5)');

    desk.prefs.oneClick = true;                                    // one-click: straight to the paper book, never the desk
    UI.addExit(c, paper, 'sl', 29990, 'NQ', 0.25);
    await flush(); await flush();
    assert.equal(desk.sent.length, 1);
    assert.deepEqual(paperSent.map((s) => [s.action, s.body.accounts, s.body.sl_price, s.body.expected_net]),
      [['exits', ['paper'], 29990, { paper: 2 }]]);

    let cancelled = 0;
    UI.addExit(c, long, 'sl', 30002, 'NQ', 0.25, { onCancel: () => cancelled++ });   // above the last trade: marketable
    await flush();
    assert.equal(cancelled, 1);
    assert.equal(desk.toasts.at(-1), 'A stop loss on a long must be below the last price (30,001.00)');
    assert.equal(desk.sent.length + paperSent.length, 2, 'nothing sent');

    desk.prefs.oneClick = false;                                   // moved through the level while the dialog was open
    UI.addExit(c, long, 'sl', 29995, 'NQ', 0.25);
    desk.quotes.NQ = { ...desk.quotes.NQ, last: 29994 };
    clickPrimary('Add stop');
    await flush(); await flush();
    assert.equal(desk.toasts.at(-1), 'Price moved through your stop/target — nothing sent');
    assert.equal(desk.sent.length, 1);

    c.replay = { id: 'r' };                                        // a replaying chart places nothing
    UI.addExit(c, long, 'sl', 29990, 'NQ', 0.25);
    await flush();
    assert.equal(desk.toasts.at(-1), 'Replay — trading is off');
    assert.equal(desk.sent.length + paperSent.length, 2);
  } finally {
    desk.state = was;
    desk.quotes.NQ = { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: 0 };
    delete global.window.HBPaperClient;
  }
});

test('addExit: an unarmed LIVE position and a non-position line are refused before any dialog', async () => {
  reset();
  const was = desk.state;
  desk.state = { ...STATE, accounts: [acct('live099', 'FAKELIVE099', 'live', {
    positions: [{ symbol: 'NQZ6', net: -1, avg_price: 30000, root: 'NQ', point_value: 20 }] })] };
  try {
    const c = chart([]);
    const short = T.linesFor(desk.state, 'NQ', UI.editableIds(c)).find((g) => g.kind === 'position');
    UI.addExit(c, short, 'tp', 29990, 'NQ', 0.25);
    await flush();
    assert.equal(dialogs.length, 0);
    assert.match(desk.toasts.at(-1), /LIVE/);
    UI.addExit(c, { ...short, kind: 'order' }, 'tp', 29990, 'NQ', 0.25);
    assert.equal(desk.sent.length, 0);
  } finally {
    desk.state = was;
  }
});

test('fix round 1, item 3: a LIVE account disarmed while a line action\'s confirm is open gets nothing', async () => {
  reset();
  const pos = [{ symbol: 'NQZ6', net: 1, avg_price: 30000, root: 'NQ', point_value: 20 }];
  const order = { order_id: '88', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, price: null, stop_price: 29990,
    owner: null, status: 'Working' };
  const was = desk.state;
  desk.state = { ...STATE, accounts: [STATE.accounts[0], acct('live099', 'FAKELIVE099', 'live', { positions: pos, orders: [order] })] };
  try {
    const c = chart([]);
    UI.toggleAccount(c, 'live099'); UI.toggleAccount(c, 'live099');   // armed (and ticked) this session
    assert.deepEqual(UI.editableIds(c), ['sim041', 'live099']);
    desk.prefs.oneClick = false;
    const lines = T.linesFor(desk.state, 'NQ', UI.editableIds(c));
    const posLine = lines.find((g) => g.kind === 'position'), sl = lines.find((g) => g.kind === 'sl');
    // three line actions, each confirmed only after the LIVE account was unticked (which disarms it)
    for (const start of [() => UI.closeLine(c, sl, 'NQ', 0.25), () => UI.moveLine(c, sl, 29980, 'NQ', 0.25),
      () => UI.addExit(c, posLine, 'tp', 30010, 'NQ', 0.25)]) {
      start();
      assert.equal(dialogs.length, 1, 'the confirm is open');
      UI.toggleAccount(c, 'live099');                                  // untick -> disarmed
      assert.deepEqual(UI.editableIds(c), ['sim041']);
      clickPrimary(dialogs[0].box.children.find((x) => x.className === 'dlg-foot').children[1].textContent);
      await flush(); await flush();
      assert.equal(desk.sent.length, 0, 'nothing reaches the disarmed LIVE account');
      assert.equal(desk.toasts.at(-1), 'Accounts changed — review and try again');
      dialogs.length = 0;
      UI.toggleAccount(c, 'live099'); UI.toggleAccount(c, 'live099');   // re-arm for the next action
    }
  } finally {
    desk.state = was;
  }
});

test('fix round 1, item 5: the size the confirm showed is frozen -- a position that grows meanwhile is not resized here', async () => {
  reset();
  const was = desk.state;
  const withNet = (net) => ({ ...STATE, accounts: [acct('sim041', 'SIM0000041', 'demo', {
    positions: [{ symbol: 'NQZ6', net, avg_price: 30000, root: 'NQ', point_value: 20 }] })] });
  desk.state = withNet(2);
  try {
    const c = chart([]);
    const line = T.linesFor(desk.state, 'NQ', UI.editableIds(c)).find((g) => g.kind === 'position');
    desk.prefs.oneClick = false;
    UI.addExit(c, line, 'sl', 29990, 'NQ', 0.25);
    assert.equal(dialogs[0].title, 'Add SL 2 @ 29,990.00 · …041');
    desk.state = withNet(3);                                    // it grew while the dialog was open
    clickPrimary('Add stop');
    await flush(); await flush();
    assert.deepEqual(desk.sent[0].body.expected_net, { sim041: 2 }, 'what was shown: the desk refuses the mismatch');
  } finally {
    desk.state = was;
  }
});

test('review round 2, C: moveLine checks a pending leg against its entry, not the market, and refuses an unknown entry', async () => {
  reset();
  const was = desk.state;
  desk.state = { ...STATE, accounts: [acct('sim041', 'SIM0000041', 'demo', { orders: [
    { order_id: '80', symbol: 'NQZ6', side: 'Buy', type: 'Limit', qty: 1, price: 29990, stop_price: null, owner: null, status: 'Working' },
    { order_id: '81', symbol: 'NQZ6', side: 'Sell', type: 'Limit', qty: 1, price: 29995, stop_price: null, owner: null, status: 'Suspended', parent_id: '80' },
    { order_id: '82', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, price: null, stop_price: 29980, owner: null, status: 'Suspended' }] })] };
  try {
    const c = chart([]);
    const lines = T.linesFor(desk.state, 'NQ', UI.editableIds(c));
    const tp = lines.find((g) => g.legs.some((l) => l.order_id === '81')), orphan = lines.find((g) => g.legs.some((l) => l.order_id === '82'));
    UI.moveLine(c, tp, 29996, 'NQ', 0.25);        // a Sell Limit below the market (30,000.25): fine for a pending TP
    await flush();
    assert.deepEqual(desk.sent.map((s) => [s.action, s.body.order_id, s.body.price]), [['modify', '81', 29996]]);
    UI.moveLine(c, tp, 29985, 'NQ', 0.25);        // below its entry 29,990: refused
    await flush();
    assert.equal(desk.toasts.at(-1), 'A target on a pending buy must stay above its entry (29,990.00)');
    UI.moveLine(c, orphan, 29975, 'NQ', 0.25);
    await flush();
    assert.equal(desk.toasts.at(-1), "Can't find this bracket's entry order — cancel it and place again");
    assert.equal(desk.sent.length, 1);
  } finally {
    desk.state = was;
  }
});
