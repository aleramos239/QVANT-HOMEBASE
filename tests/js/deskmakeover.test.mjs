import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { HTML } from './deskpage.mjs';

/* Task 12: the sidebar sorts itself into Trading / Shadow / Off; a variant set is one row. */
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const CODE = between('function sideSections(', 'function renderSide(') +
  between('const sideFolded = ', 'function toggleSide(');

function load(st) {
  const ctx = vm.createContext({
    labSafe: (f, d) => { try { return f(); } catch (_) { return d; } }, labShadowNet: () => null,
    stratState: () => 'Ready', stratLabel: (n) => n.toUpperCase(), stratDotCls: (s) => s.cfg.enabled ? '' : 'off',
    todayPnl: () => null, readinessShown: (r) => r, SIDE_FOLD: {},
  });
  vm.runInContext(CODE + '\nglobalThis.api = { sideSections, sideFolded };', ctx);
  return ctx.api;
}
const S = (on, extra = {}) => ({ cfg: { enabled: on, kind: 'x' }, ...extra });
const ids = (rows) => [...rows].map((r) => r.id);

test('ON+booked, ON no account, OFF land in trading / shadow / off; A-Z by label', () => {
  const st = { strategies: { zeta: S(true), Alpha: S(true), shad: S(true), idle: S(false) }, book: { zeta: [{ account: 'a' }], Alpha: [{ account: 'a' }] } };
  const o = load(st).sideSections(Object.keys(st.strategies), st, [], []);
  assert.deepEqual(ids(o.trading), ['Alpha', 'zeta']);
  assert.deepEqual(ids(o.shadow), ['shad']);
  assert.deepEqual(ids(o.off), ['idle']);
});

test('a set is one row, its members none', () => {
  const st = { strategies: { lab_a_r1: S(true), lab_a_r2: S(false) }, book: { lab_a_r1: [{ account: 'a' }] } };
  const o = load(st).sideSections(Object.keys(st.strategies), st, [{ id: 'v1', name: 'A', members: ['lab_a_r1', 'lab_a_r2'] }], []);
  assert.deepEqual(ids(o.trading), ['v1']);
  assert.equal(o.trading[0].set, 'v1');
  assert.equal(o.shadow.length + o.off.length, 0);
});

test('a warn check marks the row; a live-but-OFF strategy stays in Trading', () => {
  const st = { strategies: { a: S(true), b: { ...S(false), day_status: 'live' } }, book: { a: [1], b: [1] }, readiness: { checks: [{ level: 'warn', strategy: 'a' }] } };
  const o = load(st).sideSections(['a', 'b'], st, [], []);
  assert.equal(o.trading.find((r) => r.id === 'a').warn, true);
  assert.equal(o.trading.find((r) => r.id === 'b').warn, false);
});

test('Off is folded with no stored fold; Teams empty says "None yet · add one"', () => {
  const { sideFolded } = load({});
  assert.equal(sideFolded('off'), true);
  assert.equal(sideFolded('trading'), false);
  assert.ok(HTML.includes('None yet · add one'));
});
