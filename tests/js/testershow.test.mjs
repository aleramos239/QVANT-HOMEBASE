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

const CLICK = { avoidSelected: false };

test('showPlan (Claude): never the selected chart -- the order panel follows it', () => {
  assert.deepEqual(L.showPlan([chart('NQ'), chart('NQ')], 0, 'NQ'), { index: 1, switchRoot: false });
  assert.deepEqual(L.showPlan([chart('NQ'), chart('ES')], 0, 'NQ'), { index: 1, switchRoot: true });
  assert.equal(L.showPlan([chart('NQ')], 0, 'NQ').index, -1);
});

test('showPlan: a free chart already on the root beats switching one', () => {
  assert.deepEqual(L.showPlan([chart('ES'), chart('YM'), chart('NQ')], 0, 'NQ'), { index: 2, switchRoot: false });
  assert.deepEqual(L.showPlan([chart('ES'), chart('NQ')], 0, 'NQ', CLICK), { index: 1, switchRoot: false });
});

test('showPlan: a trade-ready chart is NEVER taken over, even on the run\'s own root', () => {
  // the only NQ chart has accounts: a free ES chart switches instead; that NQ chart is never re-intervalled
  assert.deepEqual(L.showPlan([chart('ES'), chart('NQ', { tradeReady: true }), chart('YM')], 0, 'NQ'),
    { index: 2, switchRoot: true });
  assert.deepEqual(L.showPlan([chart('NQ', { tradeReady: true }), chart('YM')], 0, 'NQ', CLICK),
    { index: 1, switchRoot: true });
  assert.equal(L.showPlan([chart('NQ', { tradeReady: true })], 0, 'NQ', CLICK).index, -1);
});

test('showPlan: a replaying chart is never touched', () => {
  assert.deepEqual(L.showPlan([chart('ES'), chart('NQ', { replay: true }), chart('GC')], 0, 'NQ'),
    { index: 2, switchRoot: true });
});

test('showPlan (a click in List of trades): the selected chart may be used when it is free', () => {
  assert.deepEqual(L.showPlan([chart('NQ'), chart('NQ')], 0, 'NQ', CLICK), { index: 0, switchRoot: false });
  assert.deepEqual(L.showPlan([chart('ES'), chart('YM')], 1, 'NQ', CLICK), { index: 1, switchRoot: true });
});

test('showPlan: nothing eligible -> nothing is touched, and the page says why', () => {
  const plan = L.showPlan([chart('ES', { tradeReady: true }), chart('NQ', { replay: true })], 0, 'NQ');
  assert.equal(plan.index, -1);
  assert.match(plan.reason, /never taken over/);
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

/* Opus review fix (three-tabs): the Backtest tab has no HBTradeUI at all, ever -- not "hasn't
   answered yet" like a fresh Charts-tab connection -- so failing closed there (every chart reads
   trade-ready) left showPlan with nowhere to land: show_on_chart and a List-of-trades click could
   never find a chart to use. Every chart on Backtest must read tradeReady: false, unconditionally,
   even one with accounts/an algo saved in its config from before it moved there. */
test('chartFacts: on the Backtest tab every chart is tradeReady: false, never fails closed', () => {
  const cell = (cfg, extra = {}) => ({ cfg: { root: 'NQ', ...cfg }, ...extra });
  globalThis.window = { HB_PAGE: 'backtest' };   // no HBTradeUI at all on this page
  try {
    assert.equal(L.chartFacts(cell({})).tradeReady, false);
    assert.equal(L.chartFacts(cell({ trade: { accounts: ['D1'] } })).tradeReady, false);
    assert.equal(L.chartFacts(cell({ algo: 'nq930' })).tradeReady, false);
  } finally { delete globalThis.window; }
});

test('strategyLabel: drafts say DRAFT, a broken one says it does not load', () => {
  assert.equal(X.strategyLabel({ id: 'nq930', name: 'NQ 9:30 Straddle' }), 'NQ 9:30 Straddle');
  assert.equal(X.strategyLabel({ id: 'draft_x', name: 'My ORB', draft: true }), 'DRAFT · My ORB');
  assert.equal(X.strategyLabel({ id: 'draft_y', name: 'y', draft: true, error: 'boom' }), 'DRAFT · y (does not load)');
});

test('the page routes /ws tester_show to HBTesterUI.show, and the handler plans through showPlan', () => {
  // 2026-09-28 three-tabs plan: optional-chained (HBTesterUI never loads on the Charts tab any more)
  assert.match(src('app.js'), /m\.type === 'tester_show'\) \{ window\.HBTesterUI\?\.show\(m\); return; \}/);
  const ui = src('testerui.js');
  assert.match(ui, /show: showFromClaude/);
  const body = ui.slice(ui.indexOf('async function showFromClaude'), ui.indexOf('/* ================', ui.indexOf('async function showFromClaude')));
  assert.match(body, /L\.showPlan\(cells\.map\(L\.chartFacts\), cells\.indexOf\(page\.cur\(\)\), want, \{ avoidSelected \}\)/);
  assert.match(body, /const avoidSelected = L\.claudeAvoidsSelected\(\)/);
  assert.match(body, /busyNow\(\)/);                               // refused while this page has its own job
  assert.match(body, /await L\.jump\(i, cell, \{ select: false, avoidSelected \}\)/);   // the planned chart, selection untouched
  assert.doesNotMatch(body, /page\.select\(/);                     // never moves the selection (order panel target)
  assert.match(body, /if \(panelOk\) window\.HBPanel\.show\('tester'\)/); // no panel swap while a chart has accounts
  assert.doesNotMatch(body, /\/api\/(?!tester\/)/);
});

test('a click in List of trades plans through showPlan too, and never touches a trade-ready chart', () => {
  const tl = src('testerlayer.js');
  const jump = tl.slice(tl.indexOf('async function runJump('), tl.indexOf('/* ====='));
  assert.match(tl, /runJump\(\{ U: window\.HBTesterUI, page: PAGE, tester: window\.HBTester, cat: window\.HBCatalog, chartFacts \}, i, target, opts\)/);
  assert.match(jump, /showPlan\(cells\.map\(env\.chartFacts\), cells\.indexOf\(page\.cur\(\)\), root, \{ avoidSelected \}\)/);
  assert.match(jump, /avoidSelected = false/);                                  // a click may use the selected chart
  assert.match(jump, /if \(env\.chartFacts\(cell\)\.tradeReady\) \{ page\.sbNote/);
  assert.ok(jump.indexOf('tradeReady') < jump.indexOf('cell.update('));   // checked before anything changes
});

test('the algo picker is built from the desk state and the paper list only -- never the tester catalog', () => {
  const choices = T.algoChoices({ bot: { strategies: { nq930: { symbol: 'NQZ6' } } } }, 'NQ', null,
    [{ id: 'gc_nfpcpi', root: 'GC', name: 'GC paper' }]);
  assert.deepEqual(choices.map((c) => c.value), ['', 'nq930']);
  assert.doesNotMatch(src('trade.js'), /api\/tester|draft/i);
  assert.doesNotMatch(src('settings-dialog.js'), /api\/tester|draft_/i);
});

test('claudeAvoidsSelected: the selected chart is off limits on the Charts tab (the order panel follows it) but free on Backtest', () => {
  const was = globalThis.window;
  try {
    globalThis.window = { HB_PAGE: 'backtest' };
    assert.equal(L.claudeAvoidsSelected(), false);
    globalThis.window = {};
    assert.equal(L.claudeAvoidsSelected(), true);
  } finally { if (was === undefined) delete globalThis.window; else globalThis.window = was; }
  // a one-chart layout: with the selected chart free, Claude's show has somewhere to land
  assert.equal(L.showPlan([{ root: 'NQ', replay: false, tradeReady: false }], 0, 'NQ', { avoidSelected: false }).index, 0);
  assert.equal(L.showPlan([{ root: 'NQ', replay: false, tradeReady: false }], 0, 'NQ', { avoidSelected: true }).index, -1);
});
