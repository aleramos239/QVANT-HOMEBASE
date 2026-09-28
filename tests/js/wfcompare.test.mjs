import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const M = '−';
const OFF = { key: 'offset_pts', label: 'Entry offset (pts)', type: 'float', default: 10, min: 0, max: 400, step: 0.25, choices: [] };
const SL = { key: 'sl_pts', label: 'Stop loss (pts)', type: 'float', default: 5, min: 0.25, max: 400, step: 0.25, choices: [] };
const STRAT = { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ', inputs: [OFF, SL] };
const ROWS = [{ key: 'offset_pts', text: '10, 12' }, { key: 'sl_pts', text: '5' }, { key: '', text: '' }];

const col = (n, over = {}) => ({
  test_months: n, ratio: `1:${n}`, n_steps: 48 - n, looks: 2 * (48 - n), n_months: 48 - n - (n === 3 ? 1 : 0),
  span: ['2021-02', n === 3 ? '2024-10' : '2024-12'], uncovered: n === 3 ? ['2024-11', '2024-12'] : [],
  stats: { net_profit: 1234.5 * (n === 2 ? -1 : 1), trades: 100 + n, win_rate: 51.25, profit_factor: n === 1 ? 999 : 1.4,
    avg_trade: n === 2 ? -12.2 : 12.2, max_drawdown: -2500, sharpe: 0.87, t_stat: 1.2, skipped_by_error: 0 },
  per_month: { net_profit: 25.5 * (n === 2 ? -1 : 1), trades: 2.1 },
  legs: { n: Math.ceil((48 - n) / n), no_pick: n === 1 ? 2 : 0, profitable: 10, pct_profitable: 21.28,
    first_select: '2021-01', last_select: n === 3 ? '2024-07' : '2024-11' },
  equity: { t_ms: [1, 2], equity: [10, 20], drawdown: [0, 0] },
  phases: Array.from({ length: n }, (_, p) => ({ phase: p, steps: 10, net_profit: 100 * (p + 1), trades: 5, sharpe: 0.5 + p })),
  phase_spread: { net_profit: { min: 100, max: 100 * n, mean: 50 * (n + 1), n }, sharpe: { min: 0.5, max: n - 0.5, mean: n / 2, n } },
  ...over });
const CMP = { compare: true, window: { start: '2021-01', end: '2024-12' }, n_cells: 2, looks: 276,
  scheme: { select_months: 1, step_months: 1, metric: 'net_profit', metric_label: 'Net $', min_trades: 5, tie_break: 'x' },
  schemes: [col(1), col(2), col(3)], note: 'OOS only' };

test('the compare mode rides the range pill: label, restore and run body', () => {
  assert.deepEqual(X.WF_MODES, [1, 2, 3, 'compare']);
  assert.equal(X.pillLabel({ id: 'research', wf: 'compare' }), '2021-2024 · WF compare');
  assert.equal(X.pillLabel({ id: 'research', wf: 2 }), '2021-2024 · WF 1:2');
  const f = X.restore({ ...X.defaults(STRAT), range: { id: 'research', start: '', end: '', wf: 'compare' } }, STRAT);
  assert.equal(f.range.wf, 'compare');
  assert.ok(X.isWalkforward(f) && X.isWfCompare(f));
  assert.ok(!X.isWfCompare({ ...f, range: { ...f.range, wf: 3 } }));
  assert.equal(X.restore({ ...f, range: { ...f.range, wf: 'nope' } }, STRAT).range.wf, null);
  // one job, same grid / window / Select-by / Min-trades as a single ratio -- never a test_months
  const axes = X.gridAxes(ROWS, STRAT).axes;
  const b = X.wfBody(f, axes, 'sharpe', 3), one = X.wfBody({ ...f, range: { ...f.range, wf: 1 } }, axes, 'sharpe', 3);
  assert.equal(b.compare, true);
  assert.ok(!('test_months' in b));
  const { compare, ...rest } = b, { test_months, ...restOne } = one;
  assert.deepEqual(rest, restOne);
  assert.equal(test_months, 1);
  assert.equal(compare, true);
});

test('wfModeOf / wfModeLabel: a job matches the pill by ratio or by compare', () => {
  assert.equal(X.wfModeOf({ test_months: 2 }), 2);
  assert.equal(X.wfModeOf({ compare: true, test_months: null }), 'compare');
  assert.equal(X.wfModeOf(null), null);
  assert.equal(X.wfModeLabel({ test_months: 3 }), '1:3');
  assert.equal(X.wfModeLabel({ compare: true }), '1:1 · 1:2 · 1:3 compare');
});

test('wfLooksText: a compare preview says the three schemes are summed', () => {
  assert.equal(X.wfLooksText(2, 138, true), '2 cells × 138 selection months (1:1 + 1:2 + 1:3) = 276 looks');
  assert.equal(X.wfLooksText(2, 45), '2 cells × 45 selection months = 90 looks');
});

test('wfCompareTable: one column per scheme, the dollar metrics of the stitched OOS only', () => {
  const v = X.wfCompareTable(CMP);
  assert.deepEqual(v.head.map((h) => [h.ratio, h.test_months]), [['1:1', 1], ['1:2', 2], ['1:3', 3]]);
  assert.deepEqual(v.rows.map((r) => r.label), ['Out-of-sample span', 'Net $', 'Net across start months (min – max · mean)',
    'Net / month', 'Trades', 'Win rate', 'Profit factor', 'Avg trade $', 'Max drawdown $', 'Sharpe',
    'Sharpe across start months (min – max · mean)', 'Steps (stitched legs)', '% of steps profitable',
    'Selection months (first → last)', 'Not tested out-of-sample']);
  const row = (k) => v.rows.find((r) => r.key === k).cells;
  assert.deepEqual(row('span').map((c) => c.text), ['2021-02 → 2024-12 · 47 months', '2021-02 → 2024-12 · 46 months',
    '2021-02 → 2024-10 · 44 months']);
  assert.equal(row('net')[0].text, '+$1,234.50');
  assert.equal(row('net')[0].tone, 'up');
  assert.equal(row('net')[1].text, `${M}$1,234.50`);
  assert.equal(row('net')[1].tone, 'down');
  assert.equal(row('trades')[2].text, '103');
  assert.equal(row('win_rate')[0].text, '51.3%');
  assert.equal(row('pf')[0].text, '∞');                       // no losing trade: the capped PF
  assert.equal(row('pf')[1].text, '1.40');
  assert.equal(row('avg_trade')[1].text, `${M}$12.20`);
  assert.equal(row('max_dd')[0].text, `${M}$2,500`);          // a drawdown reads negative
  assert.equal(row('max_dd')[0].tone, 'down');
  assert.equal(row('sharpe')[0].text, '0.87');
  assert.equal(row('legs')[0].text, '47 (2 no pick)');
  assert.equal(row('legs')[2].text, '15');
  assert.equal(row('legs_pct')[0].text, '21.3% (10 of 47)');
  assert.equal(row('selects')[2].text, '2021-01 → 2024-07');
  assert.equal(row('uncovered')[2].text, '2024-11, 2024-12');
  assert.equal(row('uncovered')[0].text, '—');
  // nothing in-sample has a row
  for (const r of v.rows) assert.ok(!/in-sample|selection \(IS\)/i.test(r.label.replace('out-of-sample', '')), r.label);
});

test('wfCompareCell: missing numbers read as dashes, never as zero', () => {
  const bare = { test_months: 2, ratio: '1:2', stats: {}, legs: {}, per_month: {}, span: null, uncovered: [] };
  for (const [k] of X.WF_COMPARE_ROWS) assert.equal(X.wfCompareCell(k, bare).text, '—', k);
});

test('wfCompareHead and the per-scheme colours', () => {
  assert.equal(X.wfCompareHead(CMP), '2021-01 → 2024-12 · Walk-forward 1:1 · 1:2 · 1:3 — one grid run, select on 1 month '
    + 'by Net $ (≥ 5 trades), stepping monthly · 2 cells · 276 looks counted');
  const c = X.wfCompareColors({ accent: '#2962FF', warn: '#F7A600' });
  assert.equal(c.length, 3);
  assert.equal(new Set(c).size, 3);
  assert.deepEqual(c.slice(0, 2), ['#2962FF', '#F7A600']);
});

test('the phase spread sits under the headline, and the warning says the start month moves it more', () => {
  const v = X.wfCompareTable(CMP), row = (k) => v.rows.find((r) => r.key === k).cells;
  assert.equal(row('net_phases')[0].text, '+$100 (one chain)');
  assert.equal(row('net_phases')[2].text, '+$100 – +$300 · mean +$200');
  assert.equal(row('sharpe_phases')[1].text, '0.50 – 1.50 · mean 1.00');
  assert.equal(X.wfComparePhaseLine(CMP), '');
  const warn = { ...CMP, phase_check: { gap_between_schemes: 150, widest_phase_spread: 480,
    warning: 'the start month moves these more than the ratio does' } };
  assert.equal(X.wfComparePhaseLine(warn), 'Phase check: the start month moves these more than the ratio does — '
    + 'the widest spread across start months is $480, the gap between the three headline nets $150');
  assert.equal(X.wfComparePhaseLine({ ...warn, phase_check: { ...warn.phase_check, warning: null } }), '');
});
