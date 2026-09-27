import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const M = '−';
const OFF = { key: 'offset_pts', label: 'Entry offset (pts)', type: 'float', default: 10, min: 0, max: 400, step: 0.25, choices: [] };
const SL = { key: 'sl_pts', label: 'Stop loss (pts)', type: 'float', default: 5, min: 0.25, max: 400, step: 0.25, choices: [] };
const GATE = { key: 'adx_gate', label: 'ADX(14) trend gate', type: 'bool', default: false, min: null, max: null, step: null, choices: [] };
const STRAT = { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ', inputs: [OFF, SL, GATE] };
const ROWS = [{ key: 'offset_pts', text: '10, 12' }, { key: 'sl_pts', text: '5' }, { key: '', text: '' }];

test('wfBody: the grid body plus metric and min_trades, never a range or a holdout', () => {
  const f = { ...X.defaults(STRAT), holdout: { on: true, reason: 'x' }, range: { kind: 'custom', start: '2025-01-01', end: '2025-06-30' } };
  const b = X.wfBody(f, X.gridAxes(ROWS, STRAT).axes, 'sharpe', 3);
  assert.deepEqual(b.axes, [{ key: 'offset_pts', values: [10, 12] }, { key: 'sl_pts', values: [5] }]);
  assert.equal(b.metric, 'sharpe');
  assert.equal(b.min_trades, 3);
  assert.deepEqual(b.inputs, { adx_gate: false });
  assert.ok(!('range' in b) && !('holdout' in b));
});

test('wfProblems: the grid rules plus a whole min-trades of 1 to 1000', () => {
  const f = X.defaults(STRAT);
  assert.equal(X.wfProblems(f, STRAT, ROWS, 5), null);
  assert.equal(X.wfProblems(f, STRAT, ROWS, 0), 'Min trades: a whole number 1 to 1000');
  assert.equal(X.wfProblems(f, STRAT, ROWS, 2.5), 'Min trades: a whole number 1 to 1000');
  assert.equal(X.wfProblems(f, STRAT, ROWS, NaN), 'Min trades: a whole number 1 to 1000');
  assert.equal(X.wfProblems(f, STRAT, [{ key: '', text: '' }, ROWS[1], ROWS[2]], 5), 'Pick a parameter for Rows and Columns');
  assert.deepEqual(X.WF_METRICS.map((m) => m[0]), ['net_profit', 'sharpe', 'profit_factor', 't_stat']);
});

test('wfLooksText: cells x the 45 selection months of 2021-2024', () => {
  assert.equal(X.WF_STEPS, 45);
  assert.equal(X.wfLooksText(2), '2 cells × 45 selection months = 90 looks');
  assert.equal(X.wfLooksText(60), '60 cells × 45 selection months = 2,700 looks');
  assert.equal(X.wfLooksText(1), '1 cell × 45 selection months = 45 looks');
});

test('etaText rounds to what a person reads', () => {
  assert.equal(X.etaText(null), '');
  assert.equal(X.etaText(20), '<1 min left');
  assert.equal(X.etaText(150), '~3 min left');
  assert.equal(X.etaText(4800), '~1 h 20 min left');
  assert.equal(X.etaText(7200), '~2 h left');
});

test('wfProgress: every state, progress fraction, ETA and the 9:30 pause', () => {
  assert.deepEqual(X.wfProgress({ status: 'queued', done: 0, total: 4, progress: 0, eta_s: null }),
    { text: 'Queued · 0 / 4 cells', frac: null, final: false });
  assert.equal(X.wfProgress({ status: 'queued', done: 0, total: 4, progress: 0, paused: 'paused for the 9:30 window' }).text,
    'Queued · 0 / 4 cells · paused for the 9:30 window');
  assert.deepEqual(X.wfProgress({ status: 'running', done: 1, total: 4, progress: 0.375, eta_s: 150 }),
    { text: 'Running · 1 / 4 cells · 38% · ~3 min left', frac: 0.375, final: false });
  assert.deepEqual(X.wfProgress({ status: 'selecting', done: 4, total: 4, progress: 1 }),
    { text: 'Selecting and stitching…', frac: null, final: false });
  assert.deepEqual(X.wfProgress({ status: 'done', done: 4, total: 4, looks_added: 180 }),
    { text: 'Done · 4 cells · 180 looks counted', frac: 1, final: true });
  assert.equal(X.wfProgress({ status: 'cancelled', done: 1, total: 4 }).text, 'Cancelled · 1 / 4 cells · no looks counted');
  assert.equal(X.wfProgress({ status: 'error', done: 4, total: 4, error: '1 of 4 cells did not finish' }).text,
    'Failed · 1 of 4 cells did not finish');
  assert.equal(X.wfProgress({ status: 'error', done: 4, total: 4, error: 'x' }).final, true);
  assert.deepEqual(X.wfProgress({ status: 'cancelled', done: 1, total: 4, error: 'lost contact', lost: true }),
    { text: 'Lost contact · it keeps running on the server', frac: null, final: true });
});

const STATS = (net, n, extra = {}) => ({ net_profit: net, trades: n, win_rate: 60, profit_factor: 1.5, sharpe: 1.2345,
  max_drawdown: -250, avg_trade: n ? net / n : null, t_stat: 1.1, skipped_by_error: 0, ...extra });
const RESULT = {
  scheme: { metric: 'net_profit', metric_label: 'Net $', min_trades: 5, select_months: 1, test_months: 3, step_months: 1,
    tie_break: 'best metric → more trades → lowest cell index', stitch: 'steps 0, 3, 6, …' },
  n_cells: 2, n_steps: 3, looks: 6,
  steps: [
    { k: 0, select: '2022-01', test: ['2022-02', '2022-04'], cell: 0, params: { offset_pts: 10, sl_pts: 5 }, is: STATS(500, 5),
      oos: STATS(-480, 7), stitched: true, changed: null },
    { k: 1, select: '2022-02', test: ['2022-03', '2022-05'], cell: 1, params: { offset_pts: 12, sl_pts: 5 }, is: STATS(250, 5),
      oos: STATS(-60, 3), stitched: false, changed: true },
    { k: 2, select: '2022-03', test: ['2022-04', '2022-06'], cell: null, params: null, is: null, oos: null, stitched: false, changed: null }],
  stitched: { stats: STATS(-480, 7, { max_drawdown: -500 }), equity: { t_ms: [], equity: [], drawdown: [] },
    months: ['2022-02', '2022-03', '2022-04'], legs: [0] },
  phases: [{ phase: 0, steps: 1, net_profit: -480, trades: 7, sharpe: -1 }, { phase: 1, steps: 1, net_profit: -60, trades: 3, sharpe: -2 },
    { phase: 2, steps: 1, net_profit: 0, trades: 0, sharpe: 0 }],
  stability: { changes: 1, pairs: 1, distinct: 2, no_pick: 1, top: { cell: 0, count: 1 } },
  skipped_by_error: 0,
};
const AXES = [{ key: 'offset_pts', label: 'Entry offset (pts)', values: [10, 12] }, { key: 'sl_pts', label: 'Stop loss (pts)', values: [5] }];

test('wfTiles: the stitched OOS stats in dollars plus Sharpe', () => {
  const t = X.wfTiles(RESULT);
  assert.deepEqual(t.map((x) => x.label), ['Stitched OOS net', 'Max drawdown', 'Win rate', 'Profit factor', 'Sharpe', 'Trades']);
  assert.equal(t[0].value, `${M}$480`);
  assert.equal(t[0].tone, 'down');
  assert.equal(t[0].sub, '2022-02 → 2022-04');
  assert.equal(t[1].value, `${M}$500`);
  assert.equal(t[4].value, '1.23');
  assert.equal(t[5].value, '7');
});

test('wfStepRows: one row per monthly step, dollars and Sharpe both sides, the chain and changes marked', () => {
  const rows = X.wfStepRows(RESULT, AXES);
  assert.equal(rows.length, 3);
  assert.deepEqual(rows[0].cells, ['2022-01', '2022-02 → 2022-04', 'Entry offset (pts) 10 · Stop loss (pts) 5',
    '+$500', '5', '1.23', `${M}$480`, '7', '60.0%', '1.50', '1.23', `${M}$250`]);
  assert.equal(rows[0].stitched, true);
  assert.equal(rows[0].isTone, 'up');
  assert.equal(rows[0].oosTone, 'down');
  assert.equal(rows[1].changed, true);
  assert.equal(rows[1].stitched, false);
  assert.deepEqual(rows[2].cells.slice(0, 3), ['2022-03', '2022-04 → 2022-06', 'no pick (no cell with ≥ 5 trades)']);
  assert.deepEqual(rows[2].cells.slice(3), ['—', '—', '—', '—', '—', '—', '—', '—', '—']);
  assert.deepEqual(X.WF_STEP_HEADERS, ['Select', 'Test', 'Chosen params', 'IS net', 'IS trades', 'IS Sharpe',
    'OOS net', 'OOS trades', 'OOS win %', 'OOS PF', 'OOS Sharpe', 'OOS max DD']);
});

test('wfStability and wfPhases say how often the pick moved and how much the chain phase matters', () => {
  assert.equal(X.wfStability(RESULT), 'Params changed 1 of 1 consecutive picks · 2 distinct cells · 1 month with no pick');
  assert.equal(X.wfStability({ ...RESULT, stability: { changes: 0, pairs: 0, distinct: 0, no_pick: 3, top: null } }),
    'Params changed 0 of 0 consecutive picks · 0 distinct cells · 3 months with no pick');
  assert.equal(X.wfPhases(RESULT), `Chain phase check (same picks, chain started 1 or 2 months later): phase 1 ${M}$60 · phase 2 $0`);
  assert.equal(X.wfScheme(RESULT), 'Select on 1 month by Net $ (≥ 5 trades), test the next 3, stepping monthly · 3 steps · stitched: steps 0, 3, 6, …');
});
