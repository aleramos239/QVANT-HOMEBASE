import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The order panel's two safety cues (2026-09-28 safety pass), through the REAL orderpanel.js + tradeui.js under a small
   DOM shim with a fake desk (nothing opens a connection; nothing is sent here at all):
     - S1: the Send's red ring (its wrapper's `live` class) and LIVE tag follow HBTradeUI.liveCue -- the send path's
       own account set -- for the chart the panel follows, one-click on or off;
     - S5: a stale quote puts the stale tag (a clock and the age) in the spread's slot, the prices kept as they are. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const Cat = require('../../homebase/static/charts/catalog.js');

let active = null;
class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.parentNode = null; this.cls = new Set();
    this.attrs = {}; this.dataset = {}; this.style = { setProperty() {} }; this.listeners = {};
    this.hidden = false; this.title = ''; this.value = ''; this.disabled = false; this._text = ''; this.innerHTML = '';
  }
  set className(v) { this.cls = new Set(String(v || '').split(/\s+/).filter(Boolean)); }
  get className() { return [...this.cls].join(' '); }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => (typeof c === 'string' ? c : c.textContent)).join(''); }
  append(...nodes) { for (const n of nodes) { if (n == null) continue; if (typeof n === 'object') n.parentNode = this; this.children.push(n); } }
  appendChild(n) { this.append(n); return n; }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  get classList() {
    const s = this.cls;
    return { add: (...c) => c.forEach((x) => s.add(x)), remove: (...c) => c.forEach((x) => s.delete(x)), contains: (c) => s.has(c),
      toggle: (c, on) => { const want = on === undefined ? !s.has(c) : !!on; if (want) s.add(c); else s.delete(c); return want; } };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  focus() { active = this; }
  blur() { if (active === this) active = null; }
  contains(o) { for (let n = o; n; n = n.parentNode) if (n === this) return true; return false; }
  closest() { return null; }
  get offsetWidth() { return 0; }
  get options() { return this.children.filter((c) => c.tagName === 'OPTION'); }
}
const find = (root, pred) => { for (const c of root.children || []) { if (typeof c !== 'object') continue; if (pred(c)) return c; const r = find(c, pred); if (r) return r; } return null; };
const byClass = (root, cls) => find(root, (e) => e.cls.has(cls));

const acct = (id, label, env) => ({ id, label, env, connected: true, tradable: true, error: null, balance: 50000, realized_pnl: 0,
  positions: [], orders: [], fills: [], strategies: [] });
const NOW = 5_000_000;
const desk = {
  state: { enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
    accounts: [acct('sim041', 'SIM0000041', 'demo'), acct('live099', 'FAKELIVE099', 'live')], bot: { strategies: {} } },
  down: '', quotes: { NQ: { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: NOW - 1000 } },
  prefs: { oneClick: false, oneClickChart: true, oneClickPanel: true, qty: 1, slTicks: 0, tpTicks: 0 },
  toasts: [], sent: [],
  mode(ct) { return T.tradeMode(desk, ct); }, gate() { return T.deskGate(desk); },
  toast(tone, text) { desk.toasts.push(text); }, send(a, b) { desk.sent.push({ a, b }); return Promise.resolve(); },
  on() { return () => {}; }, setPrefs(p) { Object.assign(desk.prefs, p); },
};
const cell = { cfg: { root: 'NQ', trade: { accounts: ['sim041'] }, algo: null }, shown: { root: 'NQ' }, tick: 0.25, pv: 20, replay: null };
const page = {
  cells: () => [cell], cur: () => cell, clockMs: () => NOW, chartSettings() {},
  mk: (tag, cls, text) => { const e = new El(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; },
  openDialog: () => new El('div'), setDialogClose() {}, closeDialog() {}, deskUrl: () => '', dialogOpen: () => false,
};
global.window = { HBTrade: T, HBCatalog: Cat, HBDeskClient: desk, HBIcons: { clock: '<svg></svg>', chevron: '<svg></svg>' },
  HBChartMenu: { register() {} }, HBCharts: { cells: [cell], selected: 0 }, HBCell: { badgeEl: () => new El('span') } };
global.document = { getElementById: () => null, createElement: (t) => new El(t), get activeElement() { return active; } };
const realSetInterval = global.setInterval;
global.setInterval = () => 0;   // the panel's own 1 s repaint (set up in mount): the test paints by hand
require('../../homebase/static/charts/tradeui.js');
require('../../homebase/static/charts/orderpanel.js');
const UI = global.window.HBTradeUI, OP = global.window.HBOrderPanel;
UI.mount(page);
const box = new El('div');
OP.mount(page, box);
global.setInterval = realSetInterval;
OP.setVisible(true);

const wrap = () => byClass(box, 'op-sendwrap'), send = () => byClass(box, 'op-send');
const tag = () => find(send(), (e) => e.cls.has('tr-live'));
function arm(id) {
  const scratch = { cfg: { root: 'NQ', trade: { accounts: [] }, algo: null }, shown: { root: 'NQ' } };
  const first = UI.toggleAccount(scratch, id);
  if (first === 'arming') UI.toggleAccount(scratch, id);
}

test('S1 on the order panel: the ring + LIVE tag appear exactly while liveCue names a LIVE account, one-click on or off', () => {
  cell.cfg.trade = { accounts: ['sim041'] };
  OP.setRoot();
  assert.equal(wrap().cls.has('live'), false, 'DEMO: no ring');
  assert.equal(tag().hidden, true, 'DEMO: no tag');
  assert.match(send().textContent, /Buy 1 NQ MARKET/);

  cell.cfg.trade = { accounts: ['sim041', 'live099'] };   // ticked, but not armed this session
  OP.setRoot();
  assert.deepEqual(UI.liveCue(cell, 'NQ'), []);
  assert.equal(wrap().cls.has('live'), false, 'an unarmed LIVE account is not reached: no ring');

  arm('live099');
  cell.cfg.trade = { accounts: ['sim041', 'live099'] };
  for (const oneClickPanel of [true, false]) {
    desk.prefs.oneClickPanel = oneClickPanel;
    OP.setRoot();
    assert.deepEqual(UI.liveCue(cell, 'NQ'), ['live099']);
    assert.equal(wrap().cls.has('live'), true, `armed LIVE, one-click ${oneClickPanel ? 'on' : 'off'}: the ring`);
    assert.equal(tag().hidden, false, 'and the LIVE tag');
    assert.equal(wrap().title, 'LIVE — an order from here goes to real-money account FAKELIVE099');
    assert.match(send().textContent, /^LIVE Buy 1 NQ MARKET$/, 'the label keeps its text after the tag');
  }
  desk.prefs.oneClickPanel = true;

  cell.replay = { id: 'r' };                               // Bar Replay: the panel's send would be refused
  OP.setRoot();
  assert.equal(wrap().cls.has('live'), false);
  assert.equal(send().disabled, true);
  cell.replay = null;

  cell.cfg.trade = { accounts: ['sim041'] };               // LIVE taken off the chart
  OP.setRoot();
  assert.equal(wrap().cls.has('live'), false);
  assert.equal(tag().hidden, true);
});

test('S5 on the order panel: a stale quote shows the clock tag with its age in the spread\'s slot; fresh shows the spread', () => {
  cell.cfg.trade = { accounts: ['sim041'] };
  const spread = () => byClass(box, 'op-spread'), chip = () => byClass(box, 'hb-stale');
  desk.quotes.NQ = { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: NOW - 1000 };
  OP.setRoot();
  assert.equal(chip().hidden, true, 'fresh: no stale tag');
  assert.equal(spread().textContent, '1', 'fresh: the spread in ticks');
  assert.equal(byClass(box, 'op-tile').cls.has('stale'), false);

  desk.quotes.NQ = { ...desk.quotes.NQ, ts_ms: NOW - 42_000 };
  OP.setRoot();
  assert.equal(chip().hidden, false, 'stale: the tag shows');
  assert.equal(chip().textContent, '42s', 'with the age');
  assert.equal(spread().title, 'Stale: no trade for 42s — bid / ask are from the last trade');
  assert.equal(byClass(box, 'op-tile').cls.has('stale'), true, 'the tiles keep their dim');
  assert.equal(find(byClass(box, 'op-tile'), (e) => e.cls.has('op-tpx')).textContent, '30,000.00', 'the price itself stays plain');
  assert.equal(spread().textContent, '42s', "the spread's own text gives way to the tag (one slot)");

  desk.quotes.NQ = { ...desk.quotes.NQ, ts_ms: NOW - 3 * 60_000 };
  OP.setRoot();
  assert.equal(chip().textContent, '3m', 'the age keeps counting on each paint');

  desk.quotes.NQ = { ...desk.quotes.NQ, ts_ms: NOW - 500 };
  OP.setRoot();
  assert.equal(chip().hidden, true, 'fresh again: the tag goes');
  assert.equal(spread().textContent, '1');
});
