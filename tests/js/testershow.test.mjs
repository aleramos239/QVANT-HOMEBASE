import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/testerlayer.js');
const X = require('../../homebase/static/charts/tester.js');
const T = require('../../homebase/static/charts/trade.js');
const src = (f) => readFileSync(new URL(`../../homebase/static/charts/${f}`, import.meta.url), 'utf8');

const chart = (root, o = {}) => ({ root, replay: false, tradeReady: false, ...o });

test('showPlan: the selected chart already on the run\'s root is used as is', () => {
  assert.deepEqual(L.showPlan([chart('ES'), chart('NQ'), chart('NQ')], 2, 'NQ'), { index: 2, switchRoot: false });
});

test('showPlan: another chart on the root beats switching the selected one', () => {
  assert.deepEqual(L.showPlan([chart('ES'), chart('NQ')], 0, 'NQ'), { index: 1, switchRoot: false });
});

test('showPlan: a replaying chart is never touched, even on the right root', () => {
  const plan = L.showPlan([chart('NQ', { replay: true }), chart('ES')], 0, 'NQ');
  assert.deepEqual(plan, { index: 1, switchRoot: true });
});

test('showPlan: a trade-ready chart keeps its instrument; a free one switches (the selected one first)', () => {
  const charts = [chart('ES', { tradeReady: true }), chart('YM'), chart('GC')];
  assert.deepEqual(L.showPlan(charts, 0, 'NQ'), { index: 1, switchRoot: true });
  assert.deepEqual(L.showPlan(charts, 2, 'NQ'), { index: 2, switchRoot: true });
});

test('showPlan: a trade-ready chart ALREADY on the root is fine to show on (nothing about it changes)', () => {
  assert.deepEqual(L.showPlan([chart('NQ', { tradeReady: true })], 0, 'NQ'), { index: 0, switchRoot: false });
});

test('showPlan: every chart replaying or trade-ready -> nothing is touched, and the page says why', () => {
  const plan = L.showPlan([chart('ES', { tradeReady: true }), chart('NQ', { replay: true })], 0, 'NQ');
  assert.equal(plan.index, -1);
  assert.match(plan.reason, /never changes instrument/);
  assert.equal(L.showPlan([], 0, 'NQ').index, -1);
});

test('focusTrade: trade_index, date (first on/after, else the last), time_ms, none', () => {
  const trades = [{ date: '2024-03-05', exit_ms: 100 }, { date: '2024-03-07', exit_ms: 300 }, { date: '2024-03-09', exit_ms: 500 }];
  assert.equal(L.focusTrade(trades, { trade_index: 2 }), 2);
  assert.equal(L.focusTrade(trades, { trade_index: 3 }), null);
  assert.equal(L.focusTrade(trades, { date: '2024-03-06' }), 1);
  assert.equal(L.focusTrade(trades, { date: '2024-03-05' }), 0);
  assert.equal(L.focusTrade(trades, { date: '2025-01-01' }), 2);
  assert.equal(L.focusTrade(trades, { time_ms: 301 }), 2);
  assert.equal(L.focusTrade(trades, { time_ms: 0 }), 0);
  assert.equal(L.focusTrade(trades, null), null);
  assert.equal(L.focusTrade([], { trade_index: 0 }), null);
});

test('chartFacts: accounts or an algo make a chart trade-ready; no HBTradeUI fails closed', () => {
  const cell = (cfg, extra = {}) => ({ cfg: { root: 'NQ', ...cfg }, ...extra });
  globalThis.window = undefined;
  assert.equal(L.chartFacts(cell({})).tradeReady, true);                     // nobody to ask: trade-ready
  globalThis.window = { HBTradeUI: { tradeOf: (c) => T.cellTrade(c.cfg.trade) } };
  try {
    assert.deepEqual(L.chartFacts(cell({ trade: { accounts: [] } })), { root: 'NQ', replay: false, tradeReady: false });
    assert.equal(L.chartFacts(cell({ trade: { accounts: ['D1'] } })).tradeReady, true);
    assert.equal(L.chartFacts(cell({ algo: 'nq930' })).tradeReady, true);
    assert.equal(L.chartFacts(cell({}, { replay: { date: 'x' }, shown: { root: 'ES' } })).replay, true);
    assert.equal(L.chartFacts(cell({}, { shown: { root: 'ES' } })).root, 'ES');
  } finally { delete globalThis.window; }
});

test('strategyLabel: drafts say DRAFT, a broken one says it does not load', () => {
  assert.equal(X.strategyLabel({ id: 'nq930', name: 'NQ 9:30 Straddle' }), 'NQ 9:30 Straddle');
  assert.equal(X.strategyLabel({ id: 'draft_x', name: 'My ORB', draft: true }), 'DRAFT · My ORB');
  assert.equal(X.strategyLabel({ id: 'draft_y', name: 'y', draft: true, error: 'boom' }), 'DRAFT · y (does not load)');
});

test('the page routes /ws tester_show to HBTesterUI.show, and the handler plans through showPlan', () => {
  assert.match(src('app.js'), /m\.type === 'tester_show'\) \{ window\.HBTesterUI\.show\(m\); return; \}/);
  const ui = src('testerui.js');
  assert.match(ui, /show: showFromClaude/);
  const body = ui.slice(ui.indexOf('async function showFromClaude'), ui.indexOf('/* ================', ui.indexOf('async function showFromClaude')));
  assert.match(body, /L\.showPlan\(cells\.map\(L\.chartFacts\)/);
  assert.match(body, /busyNow\(\)/);                       // refused while this page has its own job in flight
  assert.match(body, /await L\.jump\(i, cell\)/);          // focus goes through jump on the PLANNED chart
  assert.doesNotMatch(body, /\/api\/(?!tester\/)/);        // it only ever reads tester routes
});

test('the algo picker is built from the desk state and the paper list only -- never the tester catalog', () => {
  const choices = T.algoChoices({ bot: { strategies: { nq930: { symbol: 'NQZ6' } } } }, 'NQ', null,
    [{ id: 'gc_nfpcpi', root: 'GC', name: 'GC paper' }]);
  assert.deepEqual(choices.map((c) => c.value), ['', 'nq930']);
  assert.doesNotMatch(src('trade.js'), /api\/tester|draft/i);
  assert.doesNotMatch(src('settings-dialog.js'), /api\/tester|draft_/i);
});
