import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const M = '−';
const STRAT = { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ', inputs: [
  { key: 'offset_pts', label: 'Entry offset (pts)', type: 'float', default: 10, min: 0, max: 400, step: 0.25, choices: [] },
  { key: 'adx_gate', label: 'ADX(14) trend gate', type: 'bool', default: false, min: null, max: null, step: null, choices: [] },
  { key: 'mode', label: 'Mode', type: 'choice', default: 'a', min: null, max: null, step: null, choices: ['a', 'b'] },
  { key: 'n', label: 'Bars', type: 'int', default: 3, min: 1, max: 9, step: 1, choices: [] }] };
const COL = { net_profit: 12345.5, net_profit_pct: 24.691, gross_profit: 30000, gross_loss: -17654.5, commission_paid: 96,
  max_drawdown: -4210, max_drawdown_pct: -8.42, max_runup: 15000, profit_factor: 1.8765, trades: 24, wins: 13, losses: 11,
  win_rate: 54.17, avg_trade: 514.4, avg_win: 2307.69, avg_loss: -1604.95, rr: 1.4379, rr_label: '1:1.44', largest_win: 5000,
  largest_loss: -2500, avg_seconds_in_trade: 192, avg_bars_in_trade: 3.2, max_consec_losses: 4, sharpe: 1.234, sortino: 2.1,
  sharpe_traded_days: 3.3, t_stat: 2.346, expectancy: 514.4, days: 24 };
const RUN = { strategy: { id: 'nq930', name: 'NQ 9:30 straddle', root: 'NQ' }, inputs: { offset_pts: 12, adx_gate: true, mode: 'b', n: 2 },
  range: { kind: 'custom', start: '2023-01-01', end: '2025-02-01', label: '2023-01-01 → 2025-02-01', holdout: true },
  qty: 2, commission: 4, slippage_ticks: 1, capital: 50000, holdout: true, holdout_reason: 'final check', prop_rules: 'lucid-flex-50k@2026-08',
  engine: 'x', fill_law: 'tick replay',
  coverage: { sessions: 520, used: 517, skipped: [{ date: '2023-03-01', reason: 'missing 13:00–15:00 ET' }], skipped_by_reason: {},
    no_trade: [], skipped_by_error: 2, skipped_by_data: 1 },
  report: { summary: { all: COL, long: COL, short: COL }, by_year: [], by_month: [], skipped_by_error: 2, sharpe_basis: 'weekday grid' } };

test('form defaults from the schema; restore keeps only valid values', () => {
  const f = X.defaults(STRAT);
  assert.deepEqual(f, { strategy: 'nq930', inputs: { offset_pts: 10, adx_gate: false, mode: 'a', n: 3 },
    range: { kind: 'research', start: '', end: '' }, qty: 1, commission: 4, slippage_ticks: 1,
    prop_rules: 'lucid-flex-50k@2026-08', holdout: { on: false, reason: '' } });
  const r = X.restore({ ...f, inputs: { offset_pts: 11, adx_gate: 'yes', ghost: 1, n: 2.5 }, qty: 3 }, STRAT);
  assert.deepEqual(r.inputs, { offset_pts: 11, adx_gate: false, mode: 'a', n: 3 });
  assert.equal(r.qty, 3);
  assert.equal(X.restore({ strategy: 'other' }, STRAT).strategy, 'nq930');
});

test('C1: the Holdout switch is never persisted or restored -- `on` is always false coming out of restore, the reason text alone survives', () => {
  const saved = { ...X.defaults(STRAT), holdout: { on: true, reason: 'last time' } };
  const r = X.restore(saved, STRAT);
  assert.equal(r.holdout.on, false);
  assert.equal(r.holdout.reason, 'last time');   // the reason is a convenience prefill, not a standing approval
});

test('holdout: which ranges reach 2025, and the refusals the page shows before sending', () => {
  const f = X.defaults(STRAT);
  assert.equal(X.reachesHoldout({ kind: 'research' }), false);
  assert.equal(X.reachesHoldout({ kind: 'custom', start: '2023-01-01', end: '2024-12-31' }), false);
  assert.equal(X.reachesHoldout({ kind: 'custom', start: '2023-01-01', end: '2025-01-01' }), true);
  assert.equal(X.reachesHoldout({ kind: 'is_months', start: '', end: '2025-03-01' }), true);
  assert.equal(X.problems(f, STRAT), null);
  assert.equal(X.problems({ ...f, range: { kind: 'custom', start: '2023-01-01', end: '' } }, STRAT), 'A custom range needs a start and an end date');
  assert.equal(X.problems({ ...f, range: { kind: 'custom', start: '2024-01-01', end: '2023-01-01' } }, STRAT), 'The start date is after the end date');
  const hold = { ...f, range: { kind: 'custom', start: '2024-06-01', end: '2025-06-01' } };
  assert.equal(X.problems(hold, STRAT), 'This range reaches 2025 or later (holdout data): turn on Holdout and give a one-line reason');
  assert.equal(X.problems({ ...hold, holdout: { on: true, reason: '  ' } }, STRAT), 'This range reaches 2025 or later (holdout data): turn on Holdout and give a one-line reason');
  assert.equal(X.problems({ ...hold, holdout: { on: true, reason: 'a\nb' } }, STRAT), 'The holdout reason is one line of at most 200 characters');
  assert.equal(X.problems({ ...hold, holdout: { on: true, reason: 'final check' } }, STRAT), null);
  assert.equal(X.problems({ ...f, inputs: { ...f.inputs, offset_pts: 401 } }, STRAT), 'Entry offset (pts): 0 to 400');
  assert.equal(X.problems({ ...f, inputs: { ...f.inputs, n: 2.5 } }, STRAT), 'Bars: a whole number');
  assert.equal(X.problems({ ...f, qty: 0 }, STRAT), 'Qty: 1 to 100');
});

test('the request body: holdout only when the range reaches it; key and run label', () => {
  const f = X.defaults(STRAT);
  assert.deepEqual(X.body({ ...f, holdout: { on: true, reason: 'x' } }), { strategy: 'nq930', inputs: f.inputs, range: { kind: 'research' },
    qty: 1, commission: 4, slippage_ticks: 1, prop_rules: 'lucid-flex-50k@2026-08' });
  const h = { ...f, range: { kind: 'custom', start: '2024-06-01', end: '2025-06-01' }, holdout: { on: true, reason: ' final check ' } };
  assert.deepEqual(X.body(h).holdout, { reason: 'final check' });
  assert.deepEqual(X.body(h).range, { kind: 'custom', start: '2024-06-01', end: '2025-06-01' });
  assert.deepEqual(X.body({ ...f, range: { kind: 'is_months', start: '', end: '2023-12-31' } }).range, { kind: 'is_months', end: '2023-12-31' });
  assert.equal(X.runLabel(f, null), 'Run');
  assert.equal(X.runLabel(f, X.key(f)), 'Run');
  assert.equal(X.runLabel({ ...f, qty: 2 }, X.key(f)), 'Update report');
});

test('a loaded run fills the form back; C1: a holdout run comes back with the switch OFF (the reason is still prefilled)', () => {
  const f = X.fromRun(RUN, STRAT);
  assert.deepEqual(f.inputs, { offset_pts: 12, adx_gate: true, mode: 'b', n: 2 });
  assert.deepEqual(f.range, { kind: 'custom', start: '2023-01-01', end: '2025-02-01' });
  assert.deepEqual(f.holdout, { on: false, reason: 'final check' });
  assert.equal(f.qty, 2);
});

test('progress text and fraction', () => {
  assert.deepEqual(X.progress({ status: 'queued' }), { text: 'Queued…', frac: null, final: false });
  assert.deepEqual(X.progress({ status: 'running', phase: 'building cache', done: 120, total: 1004 }),
    { text: 'Building the tick cache · 120 / 1,004 sessions', frac: 120 / 1004, final: false });
  assert.equal(X.progress({ status: 'running', phase: 'run', done: 5, total: 10 }).text, 'Running · 5 / 10 sessions');
  assert.equal(X.progress({ status: 'running', phase: 'prop sim', done: 10, total: 10 }).text, 'Prop sim…');
  assert.deepEqual(X.progress({ status: 'error', error: 'boom' }), { text: 'Failed: boom', frac: null, final: true });
  assert.equal(X.progress({ status: 'done' }).final, true);
});

test('Overview tiles, badges and the prop block', () => {
  assert.deepEqual(X.tiles(RUN).map((t) => [t.label, t.value, t.sub]), [
    ['Net P&L', '+$12,345.50', '+24.69%'], ['Max drawdown', `${M}$4,210`, `${M}8.42%`], ['Win rate', '54.2%', '13/24'],
    ['Profit factor', '1.88', ''], ['Sharpe', '1.23', 'weekday grid'], ['Avg trade', '+$514.40', ''], ['Avg win : loss', 'RR 1:1.44', ''],
    ['t-stat', '2.35', '']]);
  assert.deepEqual(X.badges(RUN).map((b) => [b.text, b.tone]), [['Tick replay', 'info'], ['517 of 520 sessions', 'warn'],
    ['2 strategy errors', 'err'], ['Includes holdout', 'err']]);
  const prop = { rules: { name: 'Apex 50K', confirmed: false, label: 'Apex 50K · unconfirmed rules' }, caveat: 'c',
    headline: { eval_pass_p: 0.4312, eval_pass_ci: [0.424, 0.438], bust_p: 0.31, median_days_to_pass: 17.5, funded_expected_cheque: 1648.2 } };
  assert.deepEqual(X.propView(prop).tiles.map((t) => [t.label, t.value, t.sub]), [['Eval pass', '43.1%', '95% CI 42.4–43.8%'],
    ['Bust', '31.0%', ''], ['Median days to pass', '18', ''], ['Funded: expected cheque', '$1,648.20', '']]);
  assert.equal(X.propView(prop).unconfirmed, true);
  assert.deepEqual(X.propView({ error: 'bad file', rules: { name: 'x', confirmed: true } }), { message: 'Prop eval failed: bad file', rules: { name: 'x', confirmed: true }, unconfirmed: false });
  assert.deepEqual(X.propView(null), { message: 'No prop-eval result in this run', rules: null, unconfirmed: false });
});

test('performance summary rows (All / Long / Short, dollars, RR 1:X, Sharpe)', () => {
  const rows = X.summaryRows(RUN.report.summary);
  assert.deepEqual(rows[0], { label: 'Net profit', all: '+$12,345.50 (+24.69%)', long: '+$12,345.50 (+24.69%)', short: '+$12,345.50 (+24.69%)' });
  const by = Object.fromEntries(rows.map((r) => [r.label, r.all]));
  assert.equal(by['Ratio avg win / avg loss'], 'RR 1:1.44');
  assert.equal(by['Sharpe ratio'], '1.23');
  assert.equal(by['Avg time in trade'], '3m 12s');
  assert.equal(by['Gross loss'], `${M}$17,654.50`);
  assert.equal(by['Commission paid'], '$96');
});

// mae_usd/mfe_usd are magnitudes from the engine, always >= 0 (engine.py: `max(0.0, ...)`; its own test
// asserts 45.0, never -45.0) -- the review's I2 fix corrected a fixture that had them negative.
const TRADES = [
  { date: '2024-01-02', side: 'long', qty: 1, entry_ms: Date.parse('2024-01-02T14:30:01Z'), entry_price: 16900.25, exit_ms: Date.parse('2024-01-02T14:31:00Z'),
    exit_price: 16915.25, exit_reason: 'tp', sl: 16895.25, tp: 16915.25, net: 296, mae_usd: 40, mfe_usd: 300, seconds: 59 },
  { date: '2024-01-03', side: 'short', qty: 1, entry_ms: Date.parse('2024-01-03T14:30:02Z'), entry_price: 16800, exit_ms: Date.parse('2024-01-03T14:35:00Z'),
    exit_price: 16805, exit_reason: 'sl', sl: 16805, tp: 16785, net: -104, mae_usd: 100, mfe_usd: 20, seconds: 298 }];

test('trades: sort, cells, chart marks', () => {
  assert.deepEqual(X.sortTrades(TRADES, 'net', -1), [0, 1]);
  assert.deepEqual(X.sortTrades(TRADES, 'net', 1), [1, 0]);
  assert.deepEqual(X.sortTrades(TRADES, 'n', 1), [0, 1]);
  assert.deepEqual(X.tradeCells(TRADES[1], 1, 0.25), ['2', 'Short', '2024-01-03 09:30:02', '16,800.00', '2024-01-03 09:35:00', '16,805.00',
    'SL', '1', `${M}$104`, `${M}$100`, '+$20', '4m 58s']);
  const P = { accent: 'A', down: 'D', up: 'U' };
  assert.deepEqual(X.tradeMarks(TRADES, P)[3], { id: 'tx1', ms: TRADES[1].exit_ms, price: 16805, position: 'atPriceMiddle', shape: 'circle',
    color: 'D', text: `${M}$104`, size: 0.6 });
  assert.equal(X.tradeMarks(TRADES, P)[2].shape, 'arrowDown');
});

test('I2: MAE always reads as a loss (the engine only ever hands it a >= 0 magnitude); MFE keeps its "+"', () => {
  assert.equal(X.tradeCells(TRADES[0], 0, 0.25)[9], `${M}$40`);    // mae_usd: 40 -> a loss, not a gain
  assert.equal(X.tradeCells(TRADES[0], 0, 0.25)[10], '+$300');     // mfe_usd is favorable: the "+" is correct
  assert.equal(X.tradeCells({ ...TRADES[0], mae_usd: 0 }, 0, 0.25)[9], '$0');   // no adverse excursion at all
});

test('I4: toneOf(0) is neutral, never "down" -- a $0-net trade must not hand the page an empty class to add', () => {
  assert.equal(X.toneOf(0), '');
  assert.equal(X.toneOf(50), 'up');
  assert.equal(X.toneOf(-50), 'down');
});

test('M5: the ∞ cap applies only where num() is asked for it (Profit factor / RR), not every magnitude', () => {
  assert.equal(X.num(5000), '5000.00');           // uncapped by default: t-stat, Sharpe, avg bars in trade, ...
  assert.equal(X.num(5000, 2, true), '∞');        // Profit factor / RR opt in explicitly
  assert.equal(X.num(998.4, 1, true), '998.4');
  const big = { ...COL, profit_factor: 5000, avg_bars_in_trade: 1000, sharpe: 1200, t_stat: 1500 };
  const tiles = Object.fromEntries(X.tiles({ ...RUN, report: { ...RUN.report, summary: { all: big, long: big, short: big } } })
    .map((t) => [t.label, t.value]));
  assert.equal(tiles['Profit factor'], '∞');
  assert.equal(tiles['Sharpe'], '1200.00');       // NOT ∞: a plain magnitude, not a ratio that can blow up
  const rows = Object.fromEntries(X.summaryRows({ all: big, long: big, short: big }).map((r) => [r.label, r.all]));
  assert.equal(rows['Profit factor'], '∞');
  assert.equal(rows['Avg bars in trade'], '1000.0');   // a >16.6h trade in 1-min bars: no longer misread as ∞
  assert.equal(rows['Sharpe ratio'], '1200.00');
});

test('inputError is exported (testerui.js\'s inputs-dialog validation reuses it instead of a local copy)', () => {
  const inp = STRAT.inputs[0];   // offset_pts: float, 0..400
  assert.equal(X.inputError(inp, 401), 'Entry offset (pts): 0 to 400');
  assert.equal(X.inputError(inp, 12), null);
});

test('equity series: strictly increasing seconds', () => {
  assert.deepEqual(X.equitySeries({ t_ms: [1000, 1500, 5000], equity: [1, 2, 3], drawdown: [0, 0, -1] }), {
    equity: [{ time: 1, value: 1 }, { time: 2, value: 2 }, { time: 5, value: 3 }],
    drawdown: [{ time: 1, value: 0 }, { time: 2, value: 0 }, { time: 5, value: -1 }] });
});

test('reachSpec: keep the interval when the history fits under the cap, else the finest that does', () => {
  const now = Date.parse('2026-09-26T12:00:00Z');
  // sessions = ceil(days * 5/7) + 2; bars/session = ceil(82800 / seconds); fits when sessions * bars <= 180,000
  assert.equal(X.reachSpec('time:60', now - 20 * 86400000, now), 'time:60');                        // 17 x 1380 = 23,460
  assert.equal(X.reachSpec('time:60', Date.parse('2025-06-01T13:30:00Z'), now), 'time:300');       // 347 x 276 = 95,772
  assert.equal(X.reachSpec('time:60', Date.parse('2024-03-01T14:30:00Z'), now), 'time:900');       // 673 x 276 = 185,748 > cap; x 92 fits
  assert.equal(X.reachSpec('time:60', Date.parse('2021-10-01T14:30:00Z'), now), 'time:900');       // 1,303 x 92 = 119,876
  assert.equal(X.reachSpec('tick:1000', now - 86400000, now), 'time:300');
  assert.equal(X.reachSpec('time:3600', Date.parse('2021-10-01T14:30:00Z'), now), 'time:3600');
});
