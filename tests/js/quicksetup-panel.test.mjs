import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The order panel's size per symbol and saved templates (owner D6, 2026-10-28), through the REAL orderpanel.js +
   tradeui.js under a small DOM shim and a fake desk (nothing opens a connection). A template only FILLS the form: the
   tests check that nothing is sent by it, that LIVE is never ticked by it, and that with the quick setup off the
   panel's qty, its send and its page are what they were. */
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
    accounts: [acct('sim041', 'SIM0000041', 'demo'), acct('sim042', 'SIM0000042', 'demo'), acct('pap1', 'PAPER1', 'paper'), acct('live099', 'FAKELIVE099', 'live')], bot: { strategies: {} } },
  down: '', quotes: { NQ: { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: NOW - 1000 }, GC: { bid: 2400, ask: 2400.1, last: 2400.1, ts_ms: NOW - 1000 } },
  prefs: { oneClick: false, oneClickChart: true, oneClickPanel: true, qty: 1, slTicks: 0, tpTicks: 0 },
  quick: T.parseQuick(null),
  toasts: [], sent: [],
  mode(ct) { return T.tradeMode(desk, ct); }, gate() { return T.deskGate(desk); },
  toast(tone, text) { desk.toasts.push(text); }, send(a, b) { desk.sent.push({ a, b }); return Promise.resolve(); },
  on() { return () => {}; }, setPrefs(p) { Object.assign(desk.prefs, p); },
  setQuick(p) { desk.quick = T.parseQuick(JSON.stringify({ ...desk.quick, ...p })); },
  setQty(root, n) { if (desk.quick.on) desk.setQuick({ qtyBy: { ...desk.quick.qtyBy, [root]: n } }); desk.setPrefs({ qty: n }); },
};
const cell = { cfg: { root: 'NQ', trade: { accounts: ['sim041'] }, algo: null }, shown: { root: 'NQ' }, tick: 0.25, pv: 20, replay: null };
const page = {
  cells: () => [cell], cur: () => cell, clockMs: () => NOW, chartSettings() {},
  mk: (tag, cls, text) => { const e = new El(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; },
  openDialog: () => new El('div'), setDialogClose() {}, closeDialog() {}, deskUrl: () => '', dialogOpen: () => false,
};
global.window = { HBTrade: T, HBCatalog: Cat, HBDeskClient: desk, HBIcons: { clock: '<svg></svg>', chevron: '<svg></svg>' },
  HBChartMenu: { register() {} }, HBCharts: { cells: [cell], selected: 0 }, HBCell: { badgeEl: () => new El('span') } };
global.document = { getElementById: () => null, createElement: (t) => new El(t), get activeElement() { return active; }, dispatchEvent: () => true };
global.Event = class { constructor(t) { this.type = t; } };   // the preview's look tells the desk's own lines
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


const send = () => byClass(box, 'op-send');
const swOf = (label) => find(box, (e) => e.attrs.role === 'switch' && e.attrs['aria-label'] === label);
const tplSel = () => find(box, (e) => e.attrs['aria-label'] === 'Saved order templates');
const tplBox = () => { let n = tplSel(); while (n && !n.cls.has('op-tpl')) n = n.parentNode; return n; };
const typeInto = (el, v) => { el.value = v; for (const fn of el.listeners.input || []) fn(); };
const setRoot = (root) => { cell.cfg.root = root; cell.shown = { root }; cell.tick = root === 'GC' ? 0.1 : 0.25; cell.pv = root === 'GC' ? 100 : 20; OP.setRoot(); };
const qtyBox = () => find(box, (e) => e.cls.has('op-field') && e.children.some((c) => c.textContent === 'Units')).children.find((c) => c.tagName === 'INPUT');

test('D6 OFF (the default): no template box, one qty for every symbol, the send label and the sent order as before', async () => {
  setRoot('NQ');
  assert.equal(tplBox().hidden, true, 'the template box stays hidden');
  desk.setQty('NQ', 3);
  OP.setRoot();
  assert.equal(qtyBox().value, '3');
  assert.match(send().textContent, /Buy 3 NQ MARKET/);
  setRoot('GC');
  assert.equal(qtyBox().value, '3', 'off: the same qty on another symbol, exactly as before');
  assert.match(send().textContent, /Buy 3 GC MARKET/);
  setRoot('NQ');
  send().listeners.click[0]({ detail: 1 });
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(desk.sent.map((s) => [s.a, s.b.qty, s.b.root, s.b.accounts]), [['order', 3, 'NQ', ['sim041']]]);
});

test('D6 ON: the form takes the new symbol\'s own qty; a template fills the form, ticks no LIVE and sends nothing', async () => {
  desk.sent.length = 0;
  desk.setQuick({ on: true });
  setRoot('NQ');
  assert.equal(tplBox().hidden, false);
  assert.equal(qtyBox().value, '1', 'on, nothing saved for NQ yet: 1, not the global 3');
  desk.setQty('NQ', 2);
  OP.setRoot();
  assert.equal(qtyBox().value, '2');
  setRoot('GC');
  assert.equal(qtyBox().value, '1', 'GC never shows NQ\'s 2');
  setRoot('NQ');
  assert.equal(qtyBox().value, '2', 'and NQ gets its own back');

  // save: qty 2, stop 20, target 40; the chart has a DEMO and a LIVE (not armed) account -> LIVE is never saved
  cell.cfg.trade = { accounts: ['sim041', 'live099'] };
  swOf('Stop loss').onclick(); typeInto(find(box, (e) => e.attrs['aria-label'] === 'Stop loss value'), '20');
  swOf('Take profit').onclick(); typeInto(find(box, (e) => e.attrs['aria-label'] === 'Take profit value'), '40');
  const save = find(box, (e) => e.tagName === 'BUTTON' && e.textContent === 'Save this order');
  save.onclick();
  OP.setRoot();   // (the real desk client repaints the panel itself on a prefs event)
  assert.deepEqual(desk.quick.templates, [{ name: 'NQ · 2 lots · 20/40 · 1 acct', qty: 2, sl: 20, tp: 40, accounts: ['sim041'] }]);
  assert.deepEqual(tplSel().options.map((o) => o.textContent), ['Pick a template…', 'NQ · 2 lots · 20/40 · 1 acct']);

  // apply on another chart state: a different account set and an empty form
  swOf('Stop loss').onclick(); swOf('Take profit').onclick();
  desk.setQty('NQ', 5);
  cell.cfg.trade = { accounts: ['sim042', 'live099'] };
  tplSel().value = 'NQ · 2 lots · 20/40 · 1 acct';
  tplSel().onchange();
  assert.equal(qtyBox().value, '2');
  assert.equal(desk.prefs.qty, 2, 'the chart\'s own size box follows');
  assert.equal(find(box, (e) => e.attrs['aria-label'] === 'Stop loss value').value, '20');
  assert.equal(find(box, (e) => e.attrs['aria-label'] === 'Take profit value').value, '40');
  assert.deepEqual(cell.cfg.trade.accounts, ['sim041'], 'the set replaces the chart\'s: sim042 and the LIVE one came off');
  assert.deepEqual(desk.sent, [], 'filling the form sends nothing');

  // a set that names a LIVE account: it is not ticked, the viewer is told
  desk.setQuick({ templates: [...desk.quick.templates, { name: 'paper+live', qty: 1, sl: 0, tp: 0, accounts: ['pap1', 'live099'] }] });
  OP.setRoot();
  tplSel().value = 'paper+live';
  tplSel().onchange();
  assert.deepEqual(cell.cfg.trade.accounts, ['pap1']);
  assert.match(desk.toasts[desk.toasts.length - 1], /live099 is LIVE\. Tick it yourself/);
  assert.deepEqual(desk.sent, []);

  // five at most
  for (let i = 0; i < 3; i++) desk.setQuick(T.saveTemplate(desk.quick, { name: `t${i}`, qty: 1, sl: 0, tp: 0, accounts: [] }).quick);
  assert.equal(desk.quick.templates.length, 5);
  save.onclick();
  assert.equal(desk.toasts[desk.toasts.length - 1], 'Five templates are saved: delete one first');
  desk.setQuick({ on: false });
  OP.setRoot();
  assert.equal(tplBox().hidden, true, 'off again: the box goes');
});
