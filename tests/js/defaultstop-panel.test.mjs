import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Chart review package 3 (2026-10-28, owner D3): the order panel's SL starts from the symbol's default stop (Settings >
   Trading), and is exactly what it was while that is off. Real orderpanel.js + tradeui.js under a small DOM shim. */
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


const swOf = (label) => find(box, (e) => e.attrs.role === 'switch' && e.attrs['aria-label'] === label);
const valOf = (label) => find(box, (e) => e.attrs['aria-label'] === label);

test('OFF: the stop starts off and empty, exactly as before', () => {
  OP.setRoot();
  assert.equal(swOf('Stop loss').attrs['aria-checked'], 'false');
  assert.equal(valOf('Stop loss value').value, '');
});

test('ON for NQ: the stop starts on at that many ticks; turning it off again clears it; a symbol with none starts off', () => {
  desk.prefs.defStop = { NQ: 20 };
  OP.setRoot();
  assert.equal(swOf('Stop loss').attrs['aria-checked'], 'true');
  assert.equal(valOf('Stop loss value').value, '20');
  assert.equal(byClass(box, 'op-reason').textContent, '', 'a fresh quote: the order may go');
  desk.prefs.defStop = { ES: 8 };
  OP.setRoot();
  assert.equal(swOf('Stop loss').attrs['aria-checked'], 'false', 'NQ has no default now');
  assert.equal(valOf('Stop loss value').value, '');
  delete desk.prefs.defStop;
  OP.setRoot();
  assert.equal(swOf('Stop loss').attrs['aria-checked'], 'false');
});
