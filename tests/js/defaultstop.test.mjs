import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';

/* Chart review package 3 (2026-10-28, owner D3: "tag now, auto available but OFF"):
     (a) a NAKED tag on the chart's Buy/Sell block while the click would send no stop (display only);
     (b) an optional default stop in ticks per symbol, OFF until set in Settings > Trading.
   With the setting off, every pref, order body and page below is exactly what it was. */
const require = createRequire(import.meta.url);
const rd = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');
const T = require('../../homebase/static/charts/trade.js');
const TP = require('../../homebase/static/charts/tradepure.js');
const R = require('../../homebase/static/charts/replay.js');

/* ---------- prefs: the setting is invisible until set ---------- */
test('prefs: no defStop key at all until a symbol has one; garbage and zero are dropped', () => {
  assert.equal('defStop' in TP.parsePrefs(null), false, 'off: the prefs object is the one it always was');
  assert.equal('defStop' in TP.parsePrefs(JSON.stringify({ defStop: { NQ: 0, ES: -3, GC: 'x', '': 5 } })), false);
  assert.equal('defStop' in TP.parsePrefs(JSON.stringify({ defStop: [20] })), false);
  const p = TP.parsePrefs(JSON.stringify({ defStop: { NQ: 20.4, ES: 8, CL: 99999 } }));
  assert.deepEqual(p.defStop, { NQ: 20, ES: 8, CL: 10000 }, 'whole ticks, clamped');
  assert.deepEqual([p.slTicks, p.tpTicks], [0, 0], 'the retired SL/TP tick defaults stay retired');
  assert.equal(TP.prefsText(p), TP.prefsText(TP.parsePrefs(TP.prefsText(p))), 'survives its own save and load');
  assert.deepEqual(TP.parsePrefs(JSON.stringify({ ...p, defStop: { ...p.defStop, NQ: 0 } })).defStop, { ES: 8, CL: 10000 }, 'a 0 clears the symbol');
});

test('defaultStopTicks: the symbol\'s ticks, 0 (off) for anything else', () => {
  assert.equal(T.defaultStopTicks({ defStop: { NQ: 20 } }, 'NQ'), 20);
  assert.equal(T.defaultStopTicks({ defStop: { NQ: 20 } }, 'ES'), 0);
  assert.equal(T.defaultStopTicks({}, 'NQ'), 0);
  assert.equal(T.defaultStopTicks(undefined, 'NQ'), 0);
  assert.equal(T.defaultStopTicks({ defStop: { NQ: 20 } }, null), 0);
});

/* ---------- the send: placeOrder with the real tradeui.js ---------- */
const acct = (id, label, env) => ({ id, label, env, connected: true, tradable: true, error: null, balance: 50000, realized_pnl: 0,
  positions: [], orders: [], fills: [], strategies: [] });
const STATE = { enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [acct('sim041', 'SIM0000041', 'demo')], bot: { date: '2026-09-27', strategies: {} } };
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
  prefs: { oneClick: true, oneClickChart: true, oneClickPanel: true, qty: 1, slTicks: 0, tpTicks: 0 },
  sent: [], toasts: [],
  mode(ct) { return T.tradeMode(desk, ct); }, gate() { return T.deskGate(desk); },
  toast(tone, text) { desk.toasts.push(text); },
  send(action, body) { desk.sent.push({ action, body }); return Promise.resolve(); },
  on() { return () => {}; }, setPrefs(p) { Object.assign(desk.prefs, p); },
};
const dialogs = [];
let cells = [];
const page = {
  cells: () => cells, cur: () => cells[0], clockMs: () => 1000,
  mk: (tag, cls, text) => { const e = new El(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; },
  openDialog: (title) => { const box = new El('div'); dialogs.push({ title, box }); return box; },
  setDialogClose() {}, closeDialog() {}, deskUrl: () => '', dialogOpen: () => false,
};
const CM = require('../../homebase/static/charts/chartmenu.js');
global.window = { HBTrade: T, HBReplay: R, HBDeskClient: desk, HBIcons: {}, HBChartMenu: CM.builtins(CM.createRegistry()) };
global.document = { getElementById: () => null, createElement: (t) => new El(t), activeElement: null };
require('../../homebase/static/charts/tradeui.js');
const UI = global.window.HBTradeUI;
UI.mount(page);
const flush = () => new Promise((r) => setImmediate(r));
const cellOf = (root = 'NQ') => (cells = [{ cfg: { root, trade: { accounts: ['sim041'] }, algo: null }, shown: { root }, tick: 0.25, pv: 20,
  replay: null, ov: [], bars: [], note() {}, host: { send() {} } }])[0];
const reset = () => { desk.sent.length = 0; desk.toasts.length = 0; dialogs.length = 0; delete desk.prefs.defStop; };

test('OFF: a chart click sends exactly today\'s body -- a plain market order, no stop, no target', async () => {
  reset();
  UI.placeOrder({ cell: cellOf(), root: 'NQ', side: 'Buy', type: 'Market', qty: 2, surface: 'chart' });
  await flush();
  assert.equal(desk.sent.length, 1);
  const { client_id, ...body } = desk.sent[0].body;
  assert.ok(client_id);
  assert.deepEqual(body, { accounts: ['sim041'], root: 'NQ', side: 'Buy', qty: 2, type: 'Market' });
  assert.deepEqual(dialogs, [], 'and the confirm path is the one it was (one-click on: none)');
});

test('ON for NQ: the same send carries a stop N ticks from the last price (Buy below, Sell above), no target', async () => {
  reset();
  desk.prefs.defStop = { NQ: 20 };
  const c = cellOf();
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface: 'chart' });
  await flush();   // one send at a time: the first must resolve
  UI.placeOrder({ cell: c, root: 'NQ', side: 'Sell', type: 'Market', qty: 1, surface: 'chart' });
  await flush();
  const [buy, sell] = desk.sent.map((s) => s.body);
  assert.equal(buy.sl_price, 29995.25);
  assert.equal(sell.sl_price, 30005.25);
  assert.equal('tp_price' in buy, false);
  assert.equal(desk.sent[0].action, 'order', 'the same guarded send');
});

test('ON for NQ only: another symbol still goes out naked, and the confirm still opens when one-click is off', async () => {
  reset();
  desk.prefs.defStop = { NQ: 20 };
  desk.quotes.ES = { bid: 5000, ask: 5000.25, last: 5000.25, ts_ms: 0 };
  UI.placeOrder({ cell: cellOf('ES'), root: 'ES', side: 'Buy', type: 'Market', qty: 1, surface: 'chart' });
  await flush();
  assert.equal('sl_price' in desk.sent[0].body, false, 'ES has no default stop');
  desk.prefs.oneClickChart = false;
  UI.placeOrder({ cell: cellOf(), root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface: 'chart' });
  await flush();
  assert.equal(desk.sent.length, 1, 'nothing sent before the confirm');
  assert.equal(dialogs.length, 1, 'the existing confirm opened');
  desk.prefs.oneClickChart = true;
});

test('ON with no recent price: refused with the existing words, never sent naked', async () => {
  reset();
  desk.prefs.defStop = { NQ: 20 };
  const was = desk.quotes.NQ;
  desk.quotes.NQ = { ...was, ts_ms: -60_000 };   // 61 s old at clockMs 1000
  UI.placeOrder({ cell: cellOf(), root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface: 'chart' });
  await flush();
  assert.deepEqual(desk.sent, []);
  assert.deepEqual(desk.toasts, ["No recent price — can't attach your stop/target; try again"]);
  desk.quotes.NQ = was;
});

test('ON: an order that brings its own exits (the order panel) is not touched', async () => {
  reset();
  desk.prefs.defStop = { NQ: 20 };
  UI.placeOrder({ cell: cellOf(), root: 'NQ', side: 'Buy', type: 'Market', qty: 1, surface: 'panel', exits: { sl: null, tp: null } });
  await flush();
  assert.equal('sl_price' in desk.sent[0].body, false, 'the panel decided: no stop');
});

/* ---------- the NAKED tag on the block (tradelines.js paintBlock, lifted and run) ---------- */
const TL_SRC = rd('charts/tradelines.js');
const lift = (src, name) => { const m = new RegExp(`^(async )?function ${name}\\(`, 'm').exec(src); return src.slice(m.index, src.indexOf('\n}\n', m.index) + 2); };
const method = (name) => { const i = TL_SRC.indexOf(`\n  ${name}(`); assert.ok(i >= 0); return TL_SRC.slice(i + 1, TL_SRC.indexOf('\n  }\n', i) + 4); };
const fakeEl = (tagName) => ({ tagName, className: '', textContent: '', title: '', hidden: false, disabled: false, children: [],
  classList: { on: new Set(), toggle(c, v) { if (v) this.on.add(c); else this.on.delete(c); }, contains(c) { return this.on.has(c); } },
  append(...k) { this.children.push(...k); }, replaceChildren(...k) { this.children = k; }, blur() {} });
function block(prefs) {
  const w = { HBDeskClient: { state: STATE, prefs: { qty: 1, ...prefs }, gate: () => null },
    HBTradeUI: { tradeOf: () => ({ accounts: ['sim041'] }), liveCue: () => [], busy: () => false, flatBusy: () => false, sending: () => null } };
  const ctx = vm.createContext({ window: w, T, document: { createElement: fakeEl, activeElement: null } });
  vm.runInContext(`${lift(TL_SRC, 'mk')} globalThis.O = { ${method('paintBlock')} };`, ctx);
  const ov = { cell: { cfg: {}, replay: false }, root: 'NQ', block: fakeEl('div'), qty: fakeEl('input'), sellBtn: fakeEl('button'),
    buyBtn: fakeEl('button'), flatBtn: fakeEl('button'), sellSub: fakeEl('span'), buySub: fakeEl('span'), sellLive: fakeEl('span'),
    buyLive: fakeEl('span'), naked: fakeEl('span') };
  ov.paintBlock = ctx.O.paintBlock.bind(ov);
  ov.paintBlock({ mode: 'on', accounts: ['sim041'] });
  return ov;
}

test('NAKED tag: shown while no stop goes with the click, gone when the symbol has a default stop; display only', () => {
  const off = block({});
  assert.equal(off.naked.hidden, false);
  assert.equal(off.buyBtn.disabled, false, 'it never blocks a click');
  assert.equal(block({ defStop: { ES: 10 } }).naked.hidden, false, 'a default for ANOTHER symbol does not count');
  assert.equal(block({ defStop: { NQ: 20 } }).naked.hidden, true, 'a stop goes with it: no tag');
});

test('the NAKED tag is built once in the block, after the buttons, and styled without moving the block', () => {
  assert.match(TL_SRC, /this\.naked = mk\('span', 'tr-naked', 'NAKED'\)/);
  assert.match(rd('charts/charts.css'), /\.tr-naked \{[^}]*position: absolute/);
});
