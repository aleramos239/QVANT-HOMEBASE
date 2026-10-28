import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Package 9 (exit safety and flatten, owner D8-D10): FLATTEN ACCOUNT / CANCEL ALL from the Charts page behind the
   `accountActions` switch (off = today's page), the "stop being replaced" label, the refused-drag snap-back, the
   unknown-result warning and the stranded split leg. The REAL trade.js / tradeui.js under a small window shim:
   every "send" lands in the fake desk's `sent` list, nothing opens a connection. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');

const acct = (id, label, env, extra = {}) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const pos = (symbol, root, net) => ({ symbol, net, avg_price: 30000, root, point_value: 20 });
const STOP = { order_id: '88', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 2, price: null, stop_price: 29990, owner: null, status: 'Working' };
const LIM = { order_id: '89', symbol: 'ESZ6', side: 'Buy', type: 'Limit', qty: 1, price: 5000, stop_price: null, owner: null, status: 'Working' };
const BOTS = { ...STOP, order_id: '90', owner: 'nq930' };
const mkState = () => ({
  enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [acct('sim041', 'SIM0000041', 'demo', { positions: [pos('NQZ6', 'NQ', 2), pos('ESZ6', 'ES', -1)], orders: [STOP, LIM] }),
    acct('live099', 'FAKELIVE099', 'live', { positions: [pos('NQZ6', 'NQ', 1)], orders: [STOP] }),
    acct('flat1', 'FLAT1', 'demo')],
  bot: { date: '2026-09-27', strategies: {} },
});

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
  state: mkState(), down: '', quotes: { NQ: { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: 0 } },
  prefs: { oneClick: true, oneClickChart: true, oneClickPanel: true, qty: 1, slTicks: 0, tpTicks: 0, accountActions: false },
  sent: [], toasts: [], toastEls: [], dismissed: [], subs: new Set(), answer: () => undefined,
  mode(ct) { return T.tradeMode(desk, ct); },
  gate() { return T.deskGate(desk); },
  toast(tone, text) { const e = new El('div'); e.tone = tone; e.textContent = text; e.append(new El('span')); desk.toasts.push(text); desk.toastEls.push(e); return e; },
  dismiss(el) { desk.dismissed.push(el); },
  send(action, body) { desk.sent.push({ action, body }); return Promise.resolve(desk.answer(action, body)); },
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
const CM = require('../../homebase/static/charts/chartmenu.js');
global.window = { HBTrade: T, HBDeskClient: desk, HBIcons: {}, HBChartMenu: CM.builtins(CM.createRegistry()) };
global.document = { getElementById: () => null, createElement: (t) => new El(t), activeElement: null };
require('../../homebase/static/charts/tradeui.js');
const UI = global.window.HBTradeUI;
UI.mount(page);

const paperSent = [];
global.window.HBPaperClient = { send(a, b) { paperSent.push({ action: a, body: b }); return Promise.resolve({ status: 200, data: { results: { paper: { ok: true } } } }); } };
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };
function reset(extra = {}) {
  desk.sent.length = 0; desk.toasts.length = 0; desk.toastEls.length = 0; desk.dismissed.length = 0; dialogs.length = 0; paperSent.length = 0;
  desk.state = mkState(); desk.down = ''; desk.answer = () => undefined;
  Object.assign(desk.prefs, { oneClick: true, accountActions: false, ...extra });
}
function chart(accounts = []) {
  const c = { cfg: { root: 'NQ', trade: { accounts }, algo: null }, shown: { root: 'NQ' }, tick: 0.25, pv: 20, replay: null, ov: [], bars: [],
    note() {}, host: { send() {} } };
  cells = [c];
  return c;
}
const clickPrimary = (label) => {
  const box = dialogs[dialogs.length - 1].box, foot = box.children.find((x) => x.className === 'dlg-foot');
  foot.children.find((b) => b.textContent === label).onclick();
};
const noteText = () => dialogs[dialogs.length - 1].box.children[0].children.map((x) => x.textContent);

/* ---- the switch ---- */
test('the switch defaults OFF and only a literal true turns it on', () => {
  assert.equal(T.parsePrefs(null).accountActions, false);
  assert.equal(T.parsePrefs('{"accountActions":"yes"}').accountActions, false);
  assert.equal(T.parsePrefs('{"accountActions":true}').accountActions, true);
});

test('OFF: FLATTEN ACCOUNT and CANCEL ALL do nothing at all -- no dialog, no send, no toast', async () => {
  reset();
  UI.flattenWholeAccount('sim041');
  UI.cancelAllOrders('sim041');
  await flush();
  assert.equal(dialogs.length + desk.sent.length + paperSent.length + desk.toasts.length, 0);
});

test('OFF: the existing per-symbol Close and per-order Cancel send exactly what they always did', async () => {
  reset();
  UI.flattenAccount('sim041', 'NQ');
  await flush();
  UI.cancelOrder('sim041', '88');
  await flush();
  assert.deepEqual(desk.sent.map((s) => [s.action, Object.keys(s.body).sort()]),
    [['flatten', ['accounts', 'client_id', 'root']], ['cancel', ['account', 'client_id', 'order_id']]]);
  assert.deepEqual(desk.sent[0].body.accounts, ['sim041']);
  assert.equal(dialogs.length, 0, 'one-click: no dialog, as before');
});

/* ---- FLATTEN ACCOUNT ---- */
test('FLATTEN ACCOUNT: always one confirm (one-click or not), then the existing flatten once per symbol held', async () => {
  reset({ accountActions: true, oneClick: true });
  UI.flattenWholeAccount('sim041');
  await flush();
  assert.equal(desk.sent.length, 0, 'nothing goes out before the confirm, even with one-click on');
  assert.equal(dialogs.length, 1);
  assert.match(dialogs[0].title, /Flatten/);
  assert.ok(/NQ/.test(dialogs[0].title) && /ES/.test(dialogs[0].title), 'the title names every symbol');
  assert.equal(dialogs[0].box.children.find((x) => x.className === 'cf-one').hidden, true, 'no "don\'t ask again" box');
  clickPrimary('Flatten account');
  await flush();
  assert.deepEqual(desk.sent.map((s) => [s.action, s.body.accounts, s.body.root]), [['flatten', ['sim041'], 'NQ'], ['flatten', ['sim041'], 'ES']]);
  assert.notEqual(desk.sent[0].body.client_id, desk.sent[1].body.client_id);
  assert.equal(desk.sent.filter((s) => s.action !== 'flatten').length, 0, 'never a cancel-all, never another action');
});

test('FLATTEN ACCOUNT: a Cancel in the dialog sends nothing; an account with no position says so', async () => {
  reset({ accountActions: true });
  UI.flattenWholeAccount('sim041');
  const foot = dialogs[0].box.children.find((x) => x.className === 'dlg-foot');
  foot.children.find((b) => b.textContent === 'Cancel').onclick();
  UI.flattenWholeAccount('flat1');
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(desk.toasts.at(-1), `${T.short(desk.state.accounts[2])} has no open position — nothing sent`);
  assert.equal(dialogs.length, 1, 'no dialog for a flat account');
});

test('FLATTEN ACCOUNT: a LIVE account needs this session\'s arm, exactly as the per-symbol Close', async () => {
  reset({ accountActions: true });
  UI.flattenWholeAccount('live099');
  await flush();
  assert.equal(dialogs.length + desk.sent.length, 0);
  assert.equal(desk.toasts.length, 1);
  assert.equal(desk.toasts[0], T.unarmedLiveMessage(desk.state.accounts[1]));
});

test('FLATTEN ACCOUNT: still works with chart trading off, refused with the desk down', async () => {
  reset({ accountActions: true });
  desk.state.enabled = false;
  UI.flattenWholeAccount('sim041');
  clickPrimary('Flatten account');
  await flush();
  assert.equal(desk.sent.length, 2);
  reset({ accountActions: true });
  desk.down = 'desk down'; desk.state = null;
  UI.flattenWholeAccount('sim041');
  await flush();
  assert.equal(dialogs.length + desk.sent.length, 0);
});

test('FLATTEN ACCOUNT: a PAPER account goes to the paper book, never the desk', async () => {
  reset({ accountActions: true });
  desk.state = T.withPaper(desk.state, acct('paper', 'PAPER', 'paper', { positions: [pos('NQZ6', 'NQ', 2)] }));
  UI.flattenWholeAccount('paper');
  clickPrimary('Flatten account');
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.deepEqual(paperSent.map((s) => [s.action, s.body.accounts, s.body.root]), [['flatten', ['paper'], 'NQ']]);
});

test('FLATTEN ACCOUNT: a refused symbol (bot placing) does not stop the other symbol', async () => {
  reset({ accountActions: true });
  desk.answer = (a, b) => (b.root === 'NQ' ? { results: { sim041: { ok: false, refused: true, error: 'NQZ6 on SIM belongs to the nq930 bot right now (placing) — use Kill in an emergency' } } }
    : { results: { sim041: { ok: true } } });
  UI.flattenWholeAccount('sim041');
  clickPrimary('Flatten account');
  await flush();
  assert.equal(desk.sent.length, 2, 'the refusal of the first symbol does not stop the second');
});

/* ---- CANCEL ALL ---- */
test('CANCEL ALL: one confirm that says the stops go too, then ONE cancel-all naming that account only', async () => {
  reset({ accountActions: true, oneClick: true });
  UI.cancelAllOrders('sim041');
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 1);
  assert.match(dialogs[0].title, /Cancel all orders/);
  assert.ok(noteText().some((t) => /stop/i.test(t) && /position/i.test(t)), 'it warns that protective stops/targets are cancelled');
  clickPrimary('Cancel all orders');
  await flush();
  assert.equal(desk.sent.length, 1);
  assert.equal(desk.sent[0].action, 'cancel-all');
  assert.deepEqual(Object.keys(desk.sent[0].body).sort(), ['account', 'client_id']);
  assert.equal(desk.sent[0].body.account, 'sim041');
});

test('CANCEL ALL: LIVE needs the arm; no working order says so; the desk down refuses', async () => {
  reset({ accountActions: true });
  UI.cancelAllOrders('live099');
  UI.cancelAllOrders('flat1');
  await flush();
  assert.equal(dialogs.length + desk.sent.length, 0);
  assert.deepEqual(desk.toasts, [T.unarmedLiveMessage(desk.state.accounts[1]), `${T.short(desk.state.accounts[2])} has no working orders — nothing sent`]);
  reset({ accountActions: true });
  desk.down = 'desk down'; desk.state = null;
  UI.cancelAllOrders('sim041');
  assert.equal(dialogs.length + desk.sent.length, 0);
});

test('CANCEL ALL: a PAPER account uses the paper book\'s own cancel-symbol per symbol, never the desk', async () => {
  reset({ accountActions: true });
  desk.state = T.withPaper(desk.state, acct('paper', 'PAPER', 'paper', { orders: [STOP, LIM] }));
  UI.cancelAllOrders('paper');
  clickPrimary('Cancel all orders');
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.deepEqual(paperSent.map((s) => [s.action, s.body.accounts, s.body.root]), [['cancel-symbol', ['paper'], 'NQ'], ['cancel-symbol', ['paper'], 'ES']]);
});

test('CANCEL ALL never builds a flatten and FLATTEN ACCOUNT never builds a cancel-all', async () => {
  reset({ accountActions: true });
  UI.cancelAllOrders('sim041'); clickPrimary('Cancel all orders'); await flush();
  UI.flattenWholeAccount('sim041'); clickPrimary('Flatten account'); await flush();
  assert.deepEqual(desk.sent.map((s) => s.action), ['cancel-all', 'flatten', 'flatten']);
});

test('answers: the new action reads "orders cancelled" and a refusal shows the desk\'s words', () => {
  assert.deepEqual(T.resultToasts('cancel-all', 200, { results: { sim041: { ok: true, cancelled: 2 } } }, mkState()),
    [{ tone: 'ok', text: `${T.short(mkState().accounts[0])} · orders cancelled` }]);
  assert.equal(T.resultToasts('cancel-all', 200, { results: { sim041: { ok: false, error: 'x' } } }, mkState())[0].tone, 'err');
});

/* ---- D10: the label while the missing half is added ---- */
test('exitReplacing: the exit side already working on that root, or null', () => {
  const st = mkState();
  assert.equal(T.exitReplacing(st, ['sim041'], 'NQ', 'Buy'), 'stop');
  assert.equal(T.exitReplacing(st, ['sim041'], 'ES', 'Sell'), 'target');
  assert.equal(T.exitReplacing(st, ['sim041'], 'NQ', 'Sell'), null, 'a short\'s exit is a Buy: the Sell stop is not it');
  assert.equal(T.exitReplacing(st, ['flat1'], 'NQ', 'Buy'), null);
});

test('adding the missing half: a "stop being replaced" label shows for the gap and goes when the answer lands', async () => {
  reset({ oneClick: true });
  let release;
  desk.answer = () => new Promise((r) => { release = r; });
  const c = chart([]);
  const groups = T.linesFor(desk.state, 'NQ', UI.editableIds(c));
  const long = groups.find((g) => g.kind === 'position' && g.legs[0].account === 'sim041');
  UI.addExit(c, long, 'tp', 30010, 'NQ', 0.25);
  await flush();
  const label = desk.toastEls.find((e) => e.tone === 'warn');
  assert.ok(label && /stop being replaced/i.test(label.textContent), 'visible while the pair is being placed');
  assert.deepEqual(desk.dismissed, []);
  release({ results: { sim041: { ok: true } } });
  await flush();
  assert.deepEqual(desk.dismissed, [label]);
  assert.equal(desk.sent[0].action, 'exits');
});

test('adding the first exit to a bare position shows no label, and the exits body is unchanged', async () => {
  reset({ oneClick: true });
  desk.state.accounts[0].orders = []; desk.state.accounts[1].orders = [];   // the position line groups both accounts holding NQ
  const c = chart([]);
  const long = T.linesFor(desk.state, 'NQ', UI.editableIds(c)).find((g) => g.kind === 'position' && g.legs[0].account === 'sim041');
  UI.addExit(c, long, 'sl', 29990, 'NQ', 0.25);
  await flush();
  assert.deepEqual(desk.toastEls.filter((e) => e.tone === 'warn').map((e) => e.textContent), []);
  assert.deepEqual(desk.sent[0].body, { client_id: desk.sent[0].body.client_id, accounts: ['sim041', 'live099'], root: 'NQ', sl_price: 29990, expected_net: { sim041: 2, live099: 1 } });
});

/* ---- c-18: a refused drag snaps back ---- */
test('a refused modify calls onCancel (the line goes back); an accepted one does not', async () => {
  reset({ oneClick: true });
  const c = chart([]);
  const stop = T.linesFor(desk.state, 'NQ', UI.editableIds(c)).find((g) => g.kind === 'sl');
  desk.answer = () => ({ results: { sim041: { ok: false, error: 'order 88 is not working on SIM' } } });
  let back = 0;
  UI.moveLine(c, stop, 29980, 'NQ', 0.25, { onCancel: () => back++ });
  await flush();
  assert.equal(back, 1);
  desk.answer = () => ({ results: { sim041: { ok: true } } });
  UI.moveLine(c, stop, 29985, 'NQ', 0.25, { onCancel: () => back++ });
  await flush();
  assert.equal(back, 1, 'an accepted move is not snapped back');
  desk.answer = () => undefined;                                   // no readable answer at all: also back
  UI.moveLine(c, stop, 29975, 'NQ', 0.25, { onCancel: () => back++ });
  await flush();
  assert.equal(back, 2);
});

/* ---- c-43: an unknown result ---- */
test('resultToasts: a timeout / unreachable answer adds a "check positions" warning; a plain refusal does not', () => {
  const st = mkState();
  for (const s of [0, 502, 504]) {
    const t = T.resultToasts('order', s, { detail: 'x' }, st);
    assert.equal(t[0].tone, 'err');
    assert.equal(t[1].tone, 'warn');
    assert.match(t[1].text, /result unknown, check positions/i);
  }
  for (const s of [400, 403, 503]) assert.equal(T.resultToasts('order', s, { detail: 'x' }, st).length, 1);
  assert.equal(T.resultToasts('order', 200, { results: { sim041: { ok: true } } }, st).length, 1);
});

/* ---- c-28: the second leg of a split ---- */
test('splitStranded: accounts whose leg 1 went in and leg 2 did not', () => {
  const ok = { results: { a: { ok: true }, b: { ok: true } } };
  assert.deepEqual(T.splitStranded([[ok], [{ results: { a: { ok: true }, b: { ok: false } } }]]), ['b']);
  assert.deepEqual(T.splitStranded([[ok], [undefined]]), ['a', 'b']);
  assert.deepEqual(T.splitStranded([[ok], [ok]]), []);
  assert.deepEqual(T.splitStranded([[{ results: { a: { ok: false } } }], [{ results: { a: { ok: false } } }]]), []);
  assert.deepEqual(T.splitStranded([[ok]]), []);
});

test('a refused second split leg gives a sticky warning naming the account', async () => {
  reset({ oneClick: true });
  let n = 0;
  desk.answer = () => (++n === 1 ? { results: { sim041: { ok: true, order_id: '1' } } } : { results: { sim041: { ok: false, error: 'refused' } } });
  const c = chart(['sim041']);
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Limit', price: 29990, qty: 2, surface: 'panel', exits: { sl: 29980, tp: 30010 },
    tif: 'Day', split: { qty: 1, tp: 30005 } });
  await flush();
  assert.equal(desk.sent.length, 2);
  const w = desk.toastEls.find((e) => e.tone === 'warn');
  assert.ok(w && /leg 1 is open, leg 2 was refused/i.test(w.textContent) && /SIM0000041/.test(w.textContent));
});

test('a split order whose two legs both go in gives no warning; a plain order gives none', async () => {
  reset({ oneClick: true });
  desk.answer = () => ({ results: { sim041: { ok: true, order_id: '1' } } });
  const c = chart(['sim041']);
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Limit', price: 29990, qty: 2, surface: 'panel', exits: { sl: 29980, tp: 30010 },
    tif: 'Day', split: { qty: 1, tp: 30005 } });
  await flush();
  assert.equal(desk.toastEls.filter((e) => e.tone === 'warn').length, 0);
});

/* ---- the panel: buttons only with the switch on (panel.js has no DOM harness; its source is read) ---- */
import { readFileSync } from 'node:fs';
test('panel.js: the Accounts table gets the two buttons only when accountActions is on, and they call the two guarded actions', () => {
  const src = readFileSync(new URL('../../homebase/static/charts/panel.js', import.meta.url), 'utf8');
  assert.match(src, /const act = !!\(d\.prefs\.accountActions && window\.HBTradeUI && window\.HBTradeUI\.flattenWholeAccount\);/);
  assert.match(src, /syncTable\(target, act \? ACCOUNT_ACT_HEAD : ACCOUNT_HEAD, rows, \(r\) => r\.id, act \? buildAccountActRow : buildAccountRow, updateAccountRow\);/);
  assert.match(src, /actionTd\(tr, 'Flatten account', \(\) => window\.HBTradeUI\.flattenWholeAccount\(r\.id\), true\);/);
  assert.match(src, /actionTd\(tr, 'Cancel all', \(\) => window\.HBTradeUI\.cancelAllOrders\(r\.id\)\);/);
});
