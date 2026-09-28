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
  shared: { months: ['2021-02'], n_months: 44, span: ['2021-02', '2024-10'], per_month: { net_profit: 10 * n, trades: 2 },
    stats: { net_profit: 440 * n, trades: 90 + n, win_rate: 50, profit_factor: 1.2, avg_trade: 4.4, max_drawdown: -900,
      sharpe: 0.3 * n, skipped_by_error: 0 }, legs: { n: Math.ceil(44 / n), no_pick: 0, profitable: 5, pct_profitable: 50 },
    equity: { t_ms: [3], equity: [5], drawdown: [0] } },
  phases: Array.from({ length: n }, (_, p) => ({ phase: p, steps: 10, net_profit: 100 * (p + 1), trades: 5, sharpe: 0.5 + p })),
  phase_spread: { net_profit: { min: 100, max: 100 * n, mean: 50 * (n + 1), n }, sharpe: { min: 0.5, max: n - 0.5, mean: n / 2, n } },
  ...over });
const CMP = { compare: true, window: { start: '2021-01', end: '2024-12' }, n_cells: 2, looks: 282,
  looks_basis: { cells: 2, select_months: 47, choice_penalty: 3 },
  scheme: { select_months: 1, step_months: 1, metric: 'net_profit', metric_label: 'Net $', min_trades: 5, tie_break: 'x' },
  schemes: [col(1), col(2), col(3)], note: 'OOS only',
  shared_months: { months: [], n: 44, span: ['2021-02', '2024-10'] } };

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

test('wfLooksText: a compare preview is one search times the ×3 ratio choice', () => {
  assert.equal(X.wfLooksText(2, 47, 3), '2 cells × 47 selection months × 3 (choosing a ratio off the table) = 282 looks');
  assert.equal(X.wfLooksText(2, 45), '2 cells × 45 selection months = 90 looks');
});

test('wfCompareTable: one column per scheme, the dollar metrics of the stitched OOS only', () => {
  const v = X.wfCompareTable(CMP);
  assert.deepEqual(v.head.map((h) => [h.ratio, h.test_months]), [['1:1', 1], ['1:2', 2], ['1:3', 3]]);
  assert.deepEqual(v.rows.map((r) => r.label), ['Out-of-sample span', 'Net $', 'Net across start months (min – max · mean)',
    'Net / month', 'Trades', 'Win rate', 'Profit factor', 'Avg trade $', 'Max drawdown $', 'Sharpe',
    'Sharpe across start months (min – max · mean)', 'Steps (stitched legs)', '% of steps profitable',
    'Selection months (first → last)', 'Not tested out-of-sample', 'Strategy-error sessions']);
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
    + 'by Net $ (≥ 5 trades), stepping monthly · 282 looks counted (2 cells × 47 selection months × 3 for choosing a ratio)');
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

test('the shared-months view: identical months in every column, full-span-only rows left out', () => {
  const v = X.wfCompareTable(CMP, 'shared'), row = (k) => v.rows.find((r) => r.key === k);
  for (const k of ['net_phases', 'sharpe_phases', 'selects', 'uncovered']) assert.equal(row(k), undefined, k);
  assert.deepEqual(row('span').cells.map((c) => c.text), Array(3).fill('2021-02 → 2024-10 · 44 months'));
  assert.deepEqual(row('net').cells.map((c) => c.text), ['+$440', '+$880', '+$1,320']);
  assert.equal(row('trades').cells[0].text, '91');
  assert.equal(row('legs').cells[1].text, '22');
  assert.equal(row('legs_pct').cells[2].text, '50.0% (5 of 15)');
  // the full view is the default and keeps its own numbers
  assert.equal(X.wfCompareTable(CMP).rows.find((r) => r.key === 'net').cells[0].text, '+$1,234.50');
  assert.equal(X.wfSharedCaption(CMP), 'SHARED MONTHS · 2021-02 → 2024-10 · 44 months every scheme tests out-of-sample — the default view');
  assert.equal(X.wfSharedCaption({ shared_months: { months: [], n: 0, span: null } }),
    'SHARED MONTHS · none — the three chains test no month in common');
  // a column with no shared block reads as dashes, never zeros
  const bare = { ...CMP, schemes: [{ ...col(1), shared: null }] };
  assert.equal(X.wfCompareTable(bare, 'shared').rows.find((r) => r.key === 'net').cells[0].text, '—');
});

test('strategy-error sessions show per column, and a line names the schemes that have any', () => {
  const bad = { ...CMP, schemes: [col(1), col(2, { stats: { ...col(2).stats, skipped_by_error: 3 } }), col(3)] };
  const cells = X.wfCompareTable(bad).rows.find((r) => r.key === 'errors').cells;
  assert.deepEqual(cells.map((c) => [c.text, c.tone]), [['0', ''], ['3', 'down'], ['0', '']]);
  assert.equal(X.wfCompareErrLine(bad), 'Strategy-error sessions inside the stitched chains: 1:2 3');
  assert.equal(X.wfCompareErrLine(CMP), '');
  assert.ok(X.wfCompareTable(bad, 'shared').rows.some((r) => r.key === 'errors'));
});

test('wfSchemeProblem: a compare over a window too short for 1:3 is refused before Run', () => {
  const f = { ...X.defaults(STRAT), range: { id: 'custom', start: '2024-01-01', end: '2024-03-31', wf: 'compare' } };
  const short = { compare: true, runnable: false, window: { start: '2024-01-01', end: '2024-03-31' } };
  assert.equal(X.wfSchemeProblem(f, short), 'Window too short to compare 1:1 · 1:2 · 1:3 (1:3 needs 1 selection month + 3 test months)');
  assert.ok(X.wfSchemeProblem(f, short).startsWith('Window too short to compare 1:1 · 1:2 · 1:3'));
  assert.equal(X.wfSchemeProblem(f, { ...short, runnable: true }), null);
  assert.equal(X.wfSchemeProblem(f, null), null);                                   // not loaded yet
  assert.equal(X.wfSchemeProblem(f, { ...short, window: { start: '2021-01-01', end: '2024-12-31' } }), null);   // another window's answer
  assert.equal(X.wfSchemeProblem({ ...f, range: { ...f.range, wf: 3 } }, short), null);  // a single ratio: not this check
  assert.equal(X.wfSchemeProblem(f, { runnable: false, window: short.window }), null);  // a single-ratio scheme answer
});
