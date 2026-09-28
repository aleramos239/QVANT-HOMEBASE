import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* S1, the LIVE cue (2026-09-28 safety pass): the red ring + LIVE tag on the chart's Buy/Sell block and the order
   panel's Send read HBTradeUI.liveCue(cell, root). This loads the REAL tradeui.js (the page's send path) under a small
   window/document shim with a fake desk -- like tradeui.test.mjs, in its own process so no LIVE arm leaks in from
   another file -- and checks, case by case, that the cue names EXACTLY the LIVE accounts the next order actually goes
   to: the one-click send's body, or (one-click off) the confirm dialog's rows and the send after it. Nothing here opens
   a connection: every "send" lands in the fake desk's `sent` list (or the fake paper client's). */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');

const acct = (id, label, env, extra = {}) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const BASE = {
  enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [acct('sim041', 'SIM0000041', 'demo'), acct('live099', 'FAKELIVE099', 'live'), acct('live100', 'FAKELIVE100', 'live')],
  bot: { date: '2026-09-28', strategies: {} },
};

class El {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.listeners = {}; this.className = ''; this.textContent = ''; this.cls = new Set(); }
  append(...n) { this.children.push(...n); }
  appendChild(n) { this.children.push(n); return n; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  get classList() { const s = this.cls; return { add: (c) => s.add(c), toggle: (c, on) => (on ?? !s.has(c)) ? s.add(c) : s.delete(c), contains: (c) => s.has(c) }; }
  focus() {}
  blur() {}
}

const desk = {
  state: BASE, down: '', quotes: { NQ: { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: 0 } },
  prefs: { oneClick: true, oneClickChart: true, oneClickPanel: true, qty: 1, slTicks: 0, tpTicks: 0 },
  sent: [], toasts: [],
  mode(ct) { return T.tradeMode(desk, ct); },
  gate() { return T.deskGate(desk); },
  toast(tone, text) { desk.toasts.push(text); },
  send(action, body) { desk.sent.push({ action, body }); return Promise.resolve(); },
  on() { return () => {}; },
  setPrefs(p) { Object.assign(desk.prefs, p); },
};
const paperSent = [];
const dialogs = [];
let cells = [];
const page = {
  cells: () => cells, cur: () => cells[0], clockMs: () => 1000,
  mk: (tag, cls, text) => { const e = new El(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; },
  openDialog: (title) => { const box = new El('div'); dialogs.push({ title, box }); return box; },
  setDialogClose() {}, closeDialog() {}, deskUrl: () => 'http://127.0.0.1:8850/', dialogOpen: () => false,
};
global.window = { HBTrade: T, HBDeskClient: desk, HBIcons: {}, HBChartMenu: { register() {} },
  HBPaperClient: { send(action, body) { paperSent.push({ action, body }); return Promise.resolve({ status: 200, data: { results: {} } }); } } };
global.document = { getElementById: () => null, createElement: (t) => new El(t), activeElement: null };
require('../../homebase/static/charts/tradeui.js');
const UI = global.window.HBTradeUI;
UI.mount(page);

const flush = () => new Promise((r) => setImmediate(r));
function chart(accounts = [], extra = {}) {
  const c = { cfg: { root: 'NQ', trade: { accounts }, algo: null, ...extra }, shown: { root: 'NQ' }, tick: 0.25, pv: 20,
    replay: null, ov: [], bars: [], note() {}, host: { send() {} } };
  cells = [c];
  return c;
}
function reset() { desk.sent.length = 0; desk.toasts.length = 0; paperSent.length = 0; dialogs.length = 0; }
/* Arm a LIVE account the way the Trading tab does (two clicks within 3 s) on a scratch chart, then take it off that
   chart again only by the chart's own list -- toggleAccount's REMOVE also disarms, so a scratch chart is used and
   dropped: the arm (session-wide) stays. */
function arm(id) {
  const scratch = chart([]), first = UI.toggleAccount(scratch, id);
  if (first === 'arming') assert.equal(UI.toggleAccount(scratch, id), 'armed');
  else assert.equal(first, 'ticked', 'already armed earlier this session');
}
const ENV = { sim041: 'demo', live099: 'live', live100: 'live', paper: 'paper' };   // fixed: desk.state may be null below
const liveOf = (ids) => ids.filter((id) => ENV[id] === 'live');
/* Every account the next Buy from `c` actually reaches, desk and paper parts together. */
function sentAccounts() { return [...desk.sent.flatMap((s) => s.body.accounts || []), ...paperSent.flatMap((s) => s.body.accounts || [])]; }

/* The heart of S1: for one chart, the cue before the click equals the LIVE accounts of what the click then sends --
   with one-click on (sent at once) and with it off (the confirm's rows, then its Buy). The cue is read with both
   switch settings and must not change between them. */
async function cueMatchesSend(c, surface) {
  const key = T.oneClickKey(surface);
  desk.prefs[key] = true;
  const cueOn = UI.liveCue(c, 'NQ');
  desk.prefs[key] = false;
  const cueOff = UI.liveCue(c, 'NQ');
  assert.deepEqual(cueOn, cueOff, 'the one-click switch never changes the cue');

  reset();
  desk.prefs[key] = true;
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface });
  await flush(); await flush();
  assert.equal(dialogs.length, 0);
  assert.deepEqual(liveOf(sentAccounts()), cueOn, 'one-click: the cue names exactly the LIVE accounts sent to');
  const oneClickSent = sentAccounts();

  reset();
  desk.prefs[key] = false;
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface });
  if (dialogs.length) {   // the chart can send: the confirm is up (a refused chart toasts instead, nothing to click)
    const box = dialogs[0].box;
    assert.equal(box.classList.contains('live'), cueOn.length > 0, "the confirm's own LIVE ring agrees with the cue");
    box.children.find((x) => x.className === 'dlg-foot').children.find((b) => b.textContent === 'Buy').onclick();
    await flush(); await flush();
  }
  assert.deepEqual(liveOf(sentAccounts()), cueOn, 'confirm first: the cue names exactly the LIVE accounts sent to');
  assert.deepEqual(sentAccounts(), oneClickSent, 'the same accounts either way');
  desk.prefs[key] = true;
  return { cue: cueOn, sent: oneClickSent };
}

test('S1: DEMO only, PAPER only, or no accounts -- no LIVE cue, and nothing LIVE is sent', async () => {
  const was = desk.state;
  desk.state = T.withPaper(BASE, acct('paper', 'PAPER', 'paper'));
  try {
    for (const surface of ['chart', 'panel']) {
      assert.deepEqual(await cueMatchesSend(chart(['sim041']), surface), { cue: [], sent: ['sim041'] });
      assert.deepEqual(await cueMatchesSend(chart(['paper']), surface), { cue: [], sent: ['paper'] });
      assert.deepEqual(await cueMatchesSend(chart(['sim041', 'paper']), surface), { cue: [], sent: ['sim041', 'paper'] });
      assert.deepEqual(await cueMatchesSend(chart([]), surface), { cue: [], sent: [] });
    }
  } finally { desk.state = was; }
});

test('S1: a LIVE account ticked but not armed this session is not reached -- and not cued', async () => {
  const c = chart(['sim041', 'live099']);   // e.g. put back by some route other than the Trading tab's arm
  assert.deepEqual(UI.effectiveMode(c).accounts, ['sim041']);
  assert.deepEqual(await cueMatchesSend(c, 'chart'), { cue: [], sent: ['sim041'] });
  assert.deepEqual(await cueMatchesSend(c, 'panel'), { cue: [], sent: ['sim041'] });
});

test('S1: an armed LIVE account is cued exactly while the send reaches it -- alone, with DEMO, with PAPER, two LIVE', async () => {
  arm('live099');
  const was = desk.state;
  desk.state = T.withPaper(BASE, acct('paper', 'PAPER', 'paper'));
  try {
    for (const surface of ['chart', 'panel']) {
      assert.deepEqual(await cueMatchesSend(chart(['live099']), surface), { cue: ['live099'], sent: ['live099'] });
      assert.deepEqual(await cueMatchesSend(chart(['sim041', 'live099']), surface), { cue: ['live099'], sent: ['sim041', 'live099'] });
      assert.deepEqual(await cueMatchesSend(chart(['paper', 'live099']), surface), { cue: ['live099'], sent: ['live099', 'paper'] });
      assert.deepEqual(await cueMatchesSend(chart(['live099', 'live100']), surface), { cue: ['live099'], sent: ['live099'] },
        'live100 is ticked but not armed: neither reached nor cued');
    }
    arm('live100');
    assert.deepEqual(await cueMatchesSend(chart(['live099', 'live100']), 'chart'), { cue: ['live099', 'live100'], sent: ['live099', 'live100'] });
    assert.deepEqual(await cueMatchesSend(chart(['sim041', 'live100']), 'panel'), { cue: ['live100'], sent: ['sim041', 'live100'] });
  } finally { desk.state = was; }
});

test('S1: the cue goes the moment the send could no longer reach LIVE -- disarm, desk down / off, replay, not tradable', async () => {
  arm('live099');
  const c = chart(['sim041', 'live099']);
  assert.deepEqual(UI.liveCue(c, 'NQ'), ['live099']);

  const was = desk.state;
  desk.state = { ...BASE, enabled: false };                   // chart trading switched off on the desk
  assert.deepEqual(await cueMatchesSend(c, 'chart'), { cue: [], sent: [] });
  desk.state = null; desk.down = 'desk unreachable';          // the desk down
  assert.deepEqual(await cueMatchesSend(c, 'panel'), { cue: [], sent: [] });
  desk.state = { ...BASE, accounts: BASE.accounts.map((a) => (a.id === 'live099' ? { ...a, tradable: false } : a)) };
  assert.deepEqual(await cueMatchesSend(c, 'chart'), { cue: [], sent: ['sim041'] }, 'a LIVE account the desk says cannot trade is not reached');
  desk.state = was; desk.down = '';

  c.replay = { id: 'r' };                                     // Bar Replay: never a real order
  assert.deepEqual(await cueMatchesSend(c, 'chart'), { cue: [], sent: [] });
  c.replay = null;
  c.cfg.replayHalt = true;                                    // a replay that ended on its own: latched
  assert.deepEqual(await cueMatchesSend(c, 'chart'), { cue: [], sent: [] });
  c.cfg.replayHalt = false;
  assert.deepEqual(UI.liveCue(c, 'NQ'), ['live099']);
  assert.deepEqual(UI.liveCue(c, 'ES'), [], 'a surface painted for another symbol: that send is refused, no cue');
  cells = [];                                                 // the chart is gone from the page
  assert.deepEqual(UI.liveCue(c, 'NQ'), []);
  cells = [c];

  assert.equal(UI.toggleAccount(c, 'live099'), 'removed');    // unticking it disarms it too
  assert.deepEqual(await cueMatchesSend(c, 'panel'), { cue: [], sent: ['sim041'] });
});

test('S1: the pure half -- liveSendIds reads only an "on" mode, liveCueTitle names the accounts', () => {
  const st = BASE;
  assert.deepEqual(T.liveSendIds({ mode: 'on', reason: '', accounts: ['sim041', 'live099'] }, st), ['live099']);
  assert.deepEqual(T.liveSendIds({ mode: 'none', reason: 'x', accounts: ['live099'] }, st), [], 'a refused send reaches nothing');
  assert.deepEqual(T.liveSendIds({ mode: 'on', reason: '', accounts: ['ghost'] }, st), [], 'an unlisted id is never LIVE');
  assert.deepEqual(T.liveSendIds(null, st), []);
  assert.deepEqual(T.liveSendIds({ mode: 'on', reason: '', accounts: ['live099'] }, null), []);
  assert.equal(T.liveCueTitle(['live099'], st), 'LIVE — an order from here goes to real-money account FAKELIVE099');
  assert.equal(T.liveCueTitle(['live099', 'live100'], st), 'LIVE — an order from here goes to real-money accounts FAKELIVE099, FAKELIVE100');
  assert.equal(T.liveCueTitle([], st), '');
});
