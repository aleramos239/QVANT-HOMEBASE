import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

/* Size per symbol + saved order templates (owner D6, 2026-10-28): FORM-FILL ONLY. The pure half (HBTrade) and the
   desk client's store, the real files. Off (the default) must be today's behaviour to the byte. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const SRC = readFileSync(new URL('../../homebase/static/charts/deskclient.js', import.meta.url), 'utf8');
const SPRING = readFileSync(new URL('../../homebase/static/charts/spring.js', import.meta.url), 'utf8');

const prefs = (qty) => T.parsePrefs(JSON.stringify({ qty }));
const accts = [
  { id: 'p1', env: 'paper', tradable: true }, { id: 'p2', env: 'paper', tradable: true },
  { id: 'd1', env: 'demo', tradable: true }, { id: 'l1', env: 'live', tradable: true }, { id: 'x1', env: 'demo', tradable: false },
];

test('parseQuick: off by default, garbage -> defaults, qty and templates validated', () => {
  const dflt = { on: false, qtyBy: {}, templates: [] };
  for (const bad of [null, 'garbage', '[1]', '{"on":"yes"}']) assert.deepEqual(T.parseQuick(bad), dflt);
  const q = T.parseQuick(JSON.stringify({ on: true, qtyBy: { NQ: 3.6, gc: 2, ES: 0, YM: 'x', CL: 99999 }, templates: [
    { name: ' A ', qty: 2, sl: 20, tp: 40.4, accounts: ['p1', 'p1', 5] }, { name: '', qty: 1 }, { name: 'B', qty: 0 }, 'x',
    { name: 'A', qty: 9 }, { name: 'C', qty: 1, sl: -5, tp: 'z' }] }));
  assert.equal(q.on, true);
  assert.deepEqual(q.qtyBy, { NQ: 4 }, 'whole contracts in range (an out-of-range one is dropped), upper-case roots only');
  assert.deepEqual(q.templates, [{ name: 'A', qty: 2, sl: 20, tp: 40, accounts: ['p1'] }, { name: 'C', qty: 1, sl: 0, tp: 0, accounts: [] }]);
  assert.equal(T.parseQuick(JSON.stringify({ templates: Array.from({ length: 9 }, (_, i) => ({ name: `t${i}`, qty: 1 })) })).templates.length, 5);
});

test('qtyFor: OFF is the global qty whatever else is stored; ON is that symbol\'s own, 1 when it has none', () => {
  const off = T.parseQuick(JSON.stringify({ on: false, qtyBy: { NQ: 7 } }));
  assert.equal(T.qtyFor(prefs(3), off, 'NQ'), 3);
  assert.equal(T.qtyFor(prefs(3), undefined, 'NQ'), 3, 'a desk with no quick store at all');
  const on = T.parseQuick(JSON.stringify({ on: true, qtyBy: { NQ: 7, GC: 2 } }));
  assert.deepEqual(['NQ', 'GC', 'ES', null].map((r) => T.qtyFor(prefs(3), on, r)), [7, 2, 1, 1]);
});

test('saveTemplate / removeTemplate: same name replaces, a sixth is refused, nothing else changes', () => {
  let q = T.parseQuick(null);
  for (let i = 0; i < 5; i++) { const r = T.saveTemplate(q, { name: `t${i}`, qty: i + 1, sl: 0, tp: 0, accounts: [] }); assert.equal(r.error, undefined); q = r.quick; }
  assert.equal(T.saveTemplate(q, { name: 'six', qty: 1, sl: 0, tp: 0, accounts: [] }).error, 'Five templates are saved: delete one first');
  const r = T.saveTemplate(q, { name: 't2', qty: 9, sl: 4, tp: 8, accounts: ['p1'] });
  assert.equal(r.quick.templates.length, 5);
  assert.deepEqual(r.quick.templates[2], { name: 't2', qty: 9, sl: 4, tp: 8, accounts: ['p1'] });
  assert.equal(T.removeTemplate(r.quick, 't0').templates.length, 4);
  assert.equal(r.quick.on, false);
});

test('templatePlan: ticks only desk-listed non-LIVE accounts, unticks the rest (LIVE too), never ticks LIVE', () => {
  const state = { accounts: accts };
  assert.deepEqual(T.templatePlan({ accounts: [] }, ['l1'], state), { add: [], remove: [], live: [] }, 'no accounts saved: leave the chart alone');
  const tpl = { accounts: ['p1', 'p2', 'l1', 'x1', 'gone'] };
  assert.deepEqual(T.templatePlan(tpl, ['p1', 'd1', 'l1'], state), { add: ['p2'], remove: ['d1', 'l1'], live: ['l1'] },
    'p2 added; d1 and the LIVE one on the chart come off; LIVE in the template is only reported; unlisted / not tradable skipped');
});

test('templateName: plain words, root first', () => {
  assert.equal(T.templateName({ root: 'NQ', qty: 2, sl: 20, tp: 40, accounts: ['a', 'b'] }), 'NQ · 2 lots · 20/40 · 2 accts');
  assert.equal(T.templateName({ root: 'GC', qty: 1, sl: 0, tp: 0, accounts: [] }), 'GC · 1 lot');
  assert.equal(T.templateName({ root: 'GC', qty: 1, sl: 12, tp: 0, accounts: ['a'] }), 'GC · 1 lot · 12/– · 1 acct');
});

class El { constructor() { this.children = []; this.style = {}; this.className = ''; this.textContent = ''; }
  setAttribute() {} removeAttribute() {} addEventListener() {} removeEventListener() {} append() {} prepend() {} remove() {} }
function load(stored = {}) {
  const store = { ...stored }, writes = [];
  const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; writes.push(k); } };
  const window = { HBTrade: T, HBIcons: {} };
  const ctx = vm.createContext({ window, console, localStorage, setTimeout: () => 0, requestAnimationFrame: () => 0,
    document: { getElementById: () => null, createElement: () => new El() }, fetch: () => new Promise(() => {}) });
  vm.runInContext(SPRING, ctx);
  vm.runInContext(SRC, ctx);
  return { D: window.HBDeskClient, store, writes };
}

test('desk client OFF: setQty writes the global qty exactly like setPrefs did and never touches the quick store', () => {
  const a = load(), b = load();
  a.D.setQty('NQ', 4);
  b.D.setPrefs({ qty: 4 });
  assert.equal(a.store.hb_trade_prefs, b.store.hb_trade_prefs, 'byte for byte the stored prefs of today');
  assert.deepEqual(a.writes, ['hb_trade_prefs']);
  assert.equal('hb_trade_quick' in a.store, false);
  assert.equal(a.D.qtyFor('NQ'), 4);
  assert.equal(a.D.qtyFor('GC'), 4, 'one qty for every symbol, as before');
  assert.equal(JSON.stringify(a.D.prefs), JSON.stringify(b.D.prefs), 'the prefs object has no new field');
});

test('desk client ON: each symbol keeps its own qty (remembered across a reload); turning it off goes back to the global one', () => {
  const a = load();
  a.D.setQuick({ on: true });
  a.D.setQty('NQ', 3); a.D.setQty('GC', 1); a.D.setQty('NQ', 2);
  assert.deepEqual([a.D.qtyFor('NQ'), a.D.qtyFor('GC'), a.D.qtyFor('ES')], [2, 1, 1]);
  const again = load({ hb_trade_quick: a.store.hb_trade_quick, hb_trade_prefs: a.store.hb_trade_prefs });
  assert.deepEqual([again.D.qtyFor('NQ'), again.D.qtyFor('GC')], [2, 1]);
  again.D.setQuick({ on: false });
  assert.equal(again.D.qtyFor('GC'), again.D.prefs.qty, 'off: the one global qty (the last one typed)');
  assert.equal(again.D.quick.qtyBy.NQ, 2, 'what was remembered is kept for when it is switched on again');
});
