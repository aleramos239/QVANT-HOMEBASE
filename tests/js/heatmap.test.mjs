import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const M = '−';
const OFF = { key: 'offset_pts', label: 'Entry offset (pts)', type: 'float', default: 10, min: 0, max: 400, step: 0.25, choices: [] };
const SL = { key: 'sl_pts', label: 'Stop loss (pts)', type: 'float', default: 5, min: 0.25, max: 400, step: 0.25, choices: [] };
const GATE = { key: 'adx_gate', label: 'ADX(14) trend gate', type: 'bool', default: false, min: null, max: null, step: null, choices: [] };
const MODE = { key: 'mode', label: 'Mode', type: 'choice', default: 'a', min: null, max: null, step: null, choices: ['a', 'b'] };
const N = { key: 'n', label: 'Bars', type: 'int', default: 3, min: 1, max: 9, step: 1, choices: [] };
const STRAT = { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ', inputs: [OFF, SL, GATE, MODE, N] };

test('parseValues: lists, inclusive ranges, bools, choices, and every refusal', () => {
  assert.deepEqual(X.parseValues('5, 10,15', OFF), { values: [5, 10, 15] });
  assert.deepEqual(X.parseValues('5:20:5', OFF), { values: [5, 10, 15, 20] });
  assert.deepEqual(X.parseValues('0.25:1:0.25', OFF), { values: [0.25, 0.5, 0.75, 1] });   // no float drift
  assert.deepEqual(X.parseValues('1, 3:5:1', N), { values: [1, 3, 4, 5] });
  assert.deepEqual(X.parseValues('on, off', GATE), { values: [true, false] });
  assert.deepEqual(X.parseValues('true false', GATE), { values: [true, false] });
  assert.deepEqual(X.parseValues('b,a', MODE), { values: ['b', 'a'] });
  assert.equal(X.parseValues('  ', OFF).error, 'Entry offset (pts): enter values');
  assert.equal(X.parseValues('5, x', OFF).error, 'Entry offset (pts): "x" is not a number');
  assert.equal(X.parseValues('5, 500', OFF).error, 'Entry offset (pts): 0 to 400');
  assert.equal(X.parseValues('2.5', N).error, 'Bars: a whole number');
  assert.equal(X.parseValues('5, 5.0', OFF).error, 'Entry offset (pts): 5 twice');
  assert.equal(X.parseValues('20:5:5', OFF).error, 'Entry offset (pts): a range is start:end:step with start ≤ end and step > 0');
  assert.equal(X.parseValues('5:20:0', OFF).error, 'Entry offset (pts): a range is start:end:step with start ≤ end and step > 0');
  assert.equal(X.parseValues('0:400:0.25', OFF, 60).error, 'Entry offset (pts): more than 60 values');
  assert.equal(X.parseValues('0:400:0.25', OFF, 400).error, 'Entry offset (pts): more than 400 values');
  assert.equal(X.parseValues('0:99:1', OFF, 400).values.length, 100);        // a raised cap lets it through
  assert.equal(X.parseValues('maybe', GATE).error, 'ADX(14) trend gate: on or off');
  assert.equal(X.parseValues('c', MODE).error, 'Mode: one of a, b');
});

test('gridAxes / gridProblems: 2 or 3 distinct parameters, the cell cap, the base inputs and costs', () => {
  const f = X.defaults(STRAT);
  const two = [{ key: 'offset_pts', text: '5:15:5' }, { key: 'sl_pts', text: '4, 6' }, { key: '', text: '' }];
  assert.deepEqual(X.gridAxes(two, STRAT), { axes: [{ key: 'offset_pts', values: [5, 10, 15] }, { key: 'sl_pts', values: [4, 6] }] });
  assert.equal(X.gridCount(X.gridAxes(two, STRAT).axes), 6);
  assert.equal(X.gridProblems(f, STRAT, two), null);
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: '5' }, { key: '', text: '' }, { key: '', text: '' }]),
    'Pick a parameter for Rows and Columns');
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: '5' }, { key: 'offset_pts', text: '6' }, { key: '', text: '' }]),
    'Entry offset (pts) is picked twice');
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: '1:10:1' }, { key: 'sl_pts', text: '1:7:1' }, { key: '', text: '' }]),
    '70 cells: this grid is capped at 60 (raise Max cells, up to 400)');
  // ... and raising Max cells is exactly what lets it run
  assert.equal(X.gridProblems({ ...f, max_cells: 100 }, STRAT,
    [{ key: 'offset_pts', text: '1:10:1' }, { key: 'sl_pts', text: '1:7:1' }, { key: '', text: '' }]), null);
  assert.equal(X.gridProblems({ ...f, max_cells: 401 }, STRAT, two), 'Max cells: a whole number 1 to 400');
  assert.equal(X.gridProblems({ ...f, max_cells: 0 }, STRAT, two), 'Max cells: a whole number 1 to 400');
  assert.equal(X.gridProblems({ ...f, max_cells: 12.5 }, STRAT, two), 'Max cells: a whole number 1 to 400');
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: '1:10:1' }, { key: 'sl_pts', text: '1:6:1' }, { key: 'n', text: '1' }]), null);
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: 'x' }, { key: 'sl_pts', text: '1' }, { key: '', text: '' }]),
    'Entry offset (pts): "x" is not a number');
  // a varied input's own form value never blocks the grid; the other inputs and the costs still must be valid
  assert.equal(X.gridProblems({ ...f, inputs: { ...f.inputs, offset_pts: 999 } }, STRAT, two), null);
  assert.equal(X.gridProblems({ ...f, inputs: { ...f.inputs, n: 99 } }, STRAT, two), 'Bars: 1 to 9');
  assert.equal(X.gridProblems({ ...f, qty: 0 }, STRAT, two), 'Qty: 1 to 100');
});

test('an axis in from/to/steps mode: evenly spaced, rounded to the parameter\'s own step', () => {
  assert.deepEqual(X.stepValues(5, 20, 4, OFF), { values: [5, 10, 15, 20] });
  assert.deepEqual(X.stepValues(5, 20, 1, OFF), { values: [5] });              // steps = 1 is just `from`
  assert.deepEqual(X.stepValues(5, 20, 2, OFF), { values: [5, 20] });
  assert.deepEqual(X.stepValues(0, 1, 5, OFF), { values: [0, 0.25, 0.5, 0.75, 1] });
  // rounded to the parameter's step (0.25): the raw thirds land on the grid
  assert.deepEqual(X.stepValues(0, 1, 4, OFF), { values: [0, 0.25, 0.75, 1] });
  // an int parameter rounds to whole numbers, and a collision is dropped, not refused
  assert.deepEqual(X.stepValues(1, 3, 5, N), { values: [1, 2, 3] });
  assert.equal(X.stepValues('', 20, 4, OFF).error, 'Entry offset (pts): from and to are numbers');
  assert.equal(X.stepValues(5, 'x', 4, OFF).error, 'Entry offset (pts): from and to are numbers');
  assert.equal(X.stepValues(5, 20, 0, OFF).error, 'Entry offset (pts): steps is a whole number 1 to 400');
  assert.equal(X.stepValues(5, 20, 2.5, OFF).error, 'Entry offset (pts): steps is a whole number 1 to 400');
  assert.equal(X.stepValues(20, 5, 4, OFF).error, 'Entry offset (pts): to must be above from');
  assert.equal(X.stepValues(5, 500, 4, OFF).error, 'Entry offset (pts): 0 to 400');
  // the same row read through gridAxes
  const rows = [{ key: 'offset_pts', mode: 'range', from: 5, to: 20, steps: 4 }, { key: 'sl_pts', text: '4, 6' }, { key: '', text: '' }];
  assert.deepEqual(X.gridAxes(rows, STRAT, 60),
    { axes: [{ key: 'offset_pts', values: [5, 10, 15, 20] }, { key: 'sl_pts', values: [4, 6] }] });
});

test('the Max cells warning only speaks above 60, and uses a measured per-cell time when there is one', () => {
  assert.equal(X.cellsWarning(60, 12), '');
  assert.equal(X.cellsWarning(61, null),
    '61 cells — above 60 a grid can run for hours; only 2 cells run at a time');
  assert.equal(X.cellsWarning(120, 30), '120 cells ≈ 30m 0s at 30s a cell, 2 at a time');
  assert.equal(X.cellsWarning(400, 0), '400 cells — above 60 a grid can run for hours; only 2 cells run at a time');
});

test('gridBody: the range picker\'s window and the cell cap, varied inputs left to the axes', () => {
  const f = { ...X.defaults(STRAT), range: { id: 'custom', start: '2024-01-01', end: '2025-06-01', wf: null }, qty: 2 };
  const b = X.gridBody(f, [{ key: 'offset_pts', values: [5, 10] }, { key: 'sl_pts', values: [4] }]);
  assert.deepEqual(b, { strategy: 'nq930', inputs: { adx_gate: false, mode: 'a', n: 3 },
    axes: [{ key: 'offset_pts', values: [5, 10] }, { key: 'sl_pts', values: [4] }],
    range: { kind: 'custom', start: '2024-01-01', end: '2025-06-01' },
    qty: 2, commission: 4, slippage_ticks: 1, max_cells: 60, prop_rules: 'lucid-flex-50k@2026-09-27' });
  assert.equal('holdout' in b, false);
  // the default preset still sends {kind:'research'} verbatim
  assert.deepEqual(X.gridBody(X.defaults(STRAT), [{ key: 'offset_pts', values: [5] }, { key: 'sl_pts', values: [4] }]).range,
    { kind: 'research' });
});

test('looksText: the looks counter line, verbatim', () => {
  assert.equal(X.looksText(184), 'looks this strategy: 184 — expect ~9 lucky cells at 5%');
  assert.equal(X.looksText(0), 'looks this strategy: 0 — expect ~0 lucky cells at 5%');
  assert.equal(X.looksText(30), 'looks this strategy: 30 — expect ~2 lucky cells at 5%');
  assert.equal(X.looksText(null), 'looks this strategy: 0 — expect ~0 lucky cells at 5%');
});

const AX2 = [{ key: 'offset_pts', label: 'Entry offset (pts)', type: 'float', values: [5, 10] },
  { key: 'sl_pts', label: 'Stop loss (pts)', type: 'float', values: [4, 6, 8] }];
const cellsFor = (axes) => {
  const out = []; let i = 0;
  const walk = (k, coords) => {
    if (k === axes.length) { out.push({ i: i++, coords, params: {}, status: 'queued' }); return; }
    axes[k].values.forEach((_, j) => walk(k + 1, [...coords, j]));
  };
  walk(0, []);
  return out;
};

test('heatPanels: rows = 1st parameter, columns = 2nd, one panel per value of a 3rd', () => {
  const two = X.heatPanels({ axes: AX2, cells: cellsFor(AX2) });
  assert.equal(two.length, 1);
  assert.deepEqual(two[0], { title: null, rowLabel: 'Entry offset (pts)', colLabel: 'Stop loss (pts)',
    rows: ['5', '10'], cols: ['4', '6', '8'], cells: [[0, 1, 2], [3, 4, 5]] });
  const AX3 = [...AX2, { key: 'adx_gate', label: 'ADX(14) trend gate', type: 'bool', values: [false, true] }];
  const three = X.heatPanels({ axes: AX3, cells: cellsFor(AX3) });
  assert.deepEqual(three.map((p) => p.title), ['ADX(14) trend gate = off', 'ADX(14) trend gate = on']);
  assert.deepEqual(three[0].cells, [[0, 2, 4], [6, 8, 10]]);
  assert.deepEqual(three[1].cells, [[1, 3, 5], [7, 9, 11]]);
});

test('heatLevel: colour by net $ against the grid-wide largest |net|', () => {
  assert.deepEqual(X.heatLevel(1000, 1000), { tone: 'up', alpha: 0.7 });
  assert.deepEqual(X.heatLevel(-500, 1000), { tone: 'down', alpha: 0.4 });
  assert.deepEqual(X.heatLevel(0, 1000), { tone: '', alpha: 0 });
  assert.deepEqual(X.heatLevel(null, 1000), { tone: '', alpha: 0 });
  assert.deepEqual(X.heatLevel(50, 0), { tone: '', alpha: 0 });
  const g = { cells: [{ status: 'done', summary: { net_profit: -300 } }, { status: 'done', summary: { net_profit: 200 } },
    { status: 'queued' }] };
  assert.equal(X.heatMaxAbs(g), 300);
});

test('cellView: net $ with Sharpe when done, a state word otherwise, and a crashed strategy is never a quiet cell', () => {
  const done = X.cellView({ status: 'done', summary: { net_profit: 1234.5, sharpe: 1.234, trades: 10, win_rate: 60,
    profit_factor: 1.5, max_drawdown: -400, t_stat: 2.1, skipped_by_error: 0 } });
  assert.equal(done.net, '+$1,234.50');
  assert.equal(done.sharpe, 'Sharpe 1.23');
  assert.equal(done.tone, 'up');
  assert.equal(done.state, 'done');
  assert.match(done.title, /10 trades · WR 60\.0% · PF 1\.50 · t 2\.10 · max DD −\$400/);
  const loss = X.cellView({ status: 'done', summary: { net_profit: -50, sharpe: -0.5, trades: 2, skipped_by_error: 3 } });
  assert.equal(loss.net, `${M}$50`);
  assert.equal(loss.sharpe, `Sharpe ${M}0.50`);
  assert.equal(loss.warn, '3 strategy errors');
  assert.deepEqual([X.cellView({ status: 'queued' }).net, X.cellView({ status: 'running' }).net,
    X.cellView({ status: 'error', error: 'boom' }).net, X.cellView({ status: 'cancelled' }).net], ['·', '…', 'error', '—']);
  assert.equal(X.cellView({ status: 'error', error: 'boom' }).title, 'boom');
});

test('gridProgress and valueLabel', () => {
  assert.equal(X.gridProgress({ status: 'queued', done: 0, total: 6 }).text, 'Queued · 0 / 6 cells');
  assert.deepEqual(X.gridProgress({ status: 'running', done: 3, total: 6 }), { text: 'Running · 3 / 6 cells', frac: 0.5, final: false });
  assert.equal(X.gridProgress({ status: 'done', done: 6, total: 6 }).final, true);
  assert.equal(X.gridProgress({ status: 'cancelled', done: 2, total: 6, error: 'interrupted (the chart service restarted)' }).text,
    'Cancelled · 2 / 6 cells · interrupted (the chart service restarted)');
  assert.equal(X.valueLabel(true), 'on');
  assert.equal(X.valueLabel(12.5), '12.5');
  assert.equal(X.valueLabel('b'), 'b');
});

test('the 9:30 QUIET window: a queued run or grid reads "paused for the 9:30 window"', () => {
  assert.equal(X.progress({ status: 'queued', paused: 'paused for the 9:30 window' }).text, 'Queued · paused for the 9:30 window');
  assert.equal(X.progress({ status: 'queued' }).text, 'Queued…');
  assert.equal(X.gridProgress({ status: 'queued', done: 0, total: 4, paused: 'paused for the 9:30 window' }).text,
    'Queued · 0 / 4 cells · paused for the 9:30 window');
  assert.equal(X.gridProgress({ status: 'running', done: 2, total: 4, paused: 'paused for the 9:30 window' }).text,
    'Running · 2 / 4 cells · paused for the 9:30 window');
});

test('review #7: Rows and Columns are both required; Panels is optional and never shifts into their place', () => {
  const f = X.defaults(STRAT);
  const none = { key: '', text: '' };
  assert.equal(X.gridProblems(f, STRAT, [none, { key: 'offset_pts', text: '5' }, { key: 'sl_pts', text: '4' }]),
    'Pick a parameter for Rows and Columns');
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: '5' }, none, { key: 'sl_pts', text: '4' }]),
    'Pick a parameter for Rows and Columns');
  assert.equal(X.gridProblems(f, STRAT, [{ key: 'offset_pts', text: '5' }, none, none]), 'Pick a parameter for Rows and Columns');
  assert.deepEqual(X.gridAxes([{ key: 'offset_pts', text: '5' }, { key: 'sl_pts', text: '4' }, none], STRAT).axes.map((a) => a.key),
    ['offset_pts', 'sl_pts']);
});

test('looksLine: a counter the server could not read is said so, never shown as 0', () => {
  assert.equal(X.looksLine(184, ''), 'looks this strategy: 184 — expect ~9 lucky cells at 5%');
  assert.equal(X.looksLine(null, 'the looks counter x is unreadable'), 'looks counter unreadable: the looks counter x is unreadable');
});
