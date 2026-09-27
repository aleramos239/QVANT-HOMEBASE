import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const F = require('../../homebase/static/charts/fillquality.js');

const run = (o) => ({ date: '2026-09-22', account: 'sim041', legs: [{ side: 'Buy', price: 30900, ts: 1 }], ...o });

test('tickValue: known root = tick size x point value; unknown root = null', () => {
  assert.equal(F.tickValue('NQ'), 0.25 * 20);
  assert.equal(F.tickValue('YM'), 1.0 * 5);
  assert.equal(F.tickValue('GC'), 0.10 * 100);
  assert.equal(F.tickValue('nq'), 0.25 * 20);           // case-insensitive, like rootOf elsewhere
  assert.equal(F.tickValue('ZZ'), null);
  assert.equal(F.tickValue(null), null);
});

test('isLiveRun: a run needs at least one leg; a day-level skip/refuse/kill row (no legs) is not one', () => {
  assert.equal(F.isLiveRun(run()), true);
  assert.equal(F.isLiveRun({ date: '2026-09-22', account: null, status: 'skipped', legs: [] }), false);
  assert.equal(F.isLiveRun({ date: '2026-09-22', account: null, legs: [] }), false);
  assert.equal(F.isLiveRun(null), false);
  assert.equal(F.isLiveRun({ legs: 'nope' }), false);
});

test('fillQualityRows: filters out non-live rows, keeps entry/SL slip in ticks and $, gap-through only on an SL exit', () => {
  const runs = [
    run({ date: '2026-09-22', account: 'sim041', latency_ms: 340, entry: { side: 'Buy', price: 30901, slip_ticks: 4 },
      exit: { price: 30880, kind: 'sl', slip_ticks: 2, gap_through: false } }),
    { date: '2026-09-21', account: null, status: 'skipped', legs: [] },          // dropped: not a live run
    run({ date: '2026-09-19', account: 'sim047', latency_ms: 120, entry: { side: 'Sell', price: 30895, slip_ticks: -1 },
      exit: { price: 30920, kind: 'tp' } }),                                     // a TP exit: no SL slip/gap
  ];
  const rows = F.fillQualityRows(runs, 'NQ');
  assert.equal(rows.length, 2);
  const tv = 0.25 * 20;   // NQ tick value = $5
  assert.deepEqual(rows[0], { date: '2026-09-22', account: 'sim041', latencyMs: 340,
    entryTicks: 4, entryUsd: 4 * tv, slTicks: 2, slUsd: 2 * tv, gapThrough: false });
  assert.deepEqual(rows[1], { date: '2026-09-19', account: 'sim047', latencyMs: 120,
    entryTicks: -1, entryUsd: -1 * tv, slTicks: null, slUsd: null, gapThrough: null });
});

test('fillQualityRows: nulls in the source (missing latency, unmatched entry, unknown root) stay null, never 0 or NaN', () => {
  const runs = [run({ date: '2026-09-22', latency_ms: null, entry: { side: 'Buy', price: 30901, slip_ticks: null } })];
  const rows = F.fillQualityRows(runs, 'ZZ');   // unknown root: every *Usd stays null even with real ticks
  assert.deepEqual(rows[0], { date: '2026-09-22', account: 'sim041', latencyMs: null,
    entryTicks: null, entryUsd: null, slTicks: null, slUsd: null, gapThrough: null });
});

test('fillQualityRows: sorted newest first by date; a strategy-wide row (account null) sorts after its own accounts on the same date', () => {
  const runs = [
    run({ date: '2026-09-18', account: 'sim041' }),
    run({ date: '2026-09-20', account: 'sim047' }),
    run({ date: '2026-09-20', account: null }),
    run({ date: '2026-09-20', account: 'sim041' }),
  ];
  const rows = F.fillQualityRows(runs, 'NQ');
  assert.deepEqual(rows.map((r) => [r.date, r.account]),
    [['2026-09-20', 'sim041'], ['2026-09-20', 'sim047'], ['2026-09-20', null], ['2026-09-18', 'sim041']]);
});

test('median: odd and even counts, nulls ignored, empty -> null (never 0)', () => {
  assert.equal(F.median([1, 3, 2]), 2);
  assert.equal(F.median([1, 2, 3, 4]), 2.5);
  assert.equal(F.median([null, 5, null, 1]), 3);
  assert.equal(F.median([]), null);
  assert.equal(F.median([null, null]), null);
});

test('mean: nulls ignored (never dragged toward 0), empty -> null', () => {
  assert.equal(F.mean([2, 4, 6]), 4);
  assert.equal(F.mean([null, 2, null, 4]), 3);
  assert.equal(F.mean([]), null);
  assert.equal(F.mean([null]), null);
});

test('fillQualitySummary: averages/median only over rows that answer that field; n = every live run shown', () => {
  const rows = F.fillQualityRows([
    run({ date: '2026-09-22', latency_ms: 300, entry: { side: 'Buy', price: 1, slip_ticks: 4 },
      exit: { price: 1, kind: 'sl', slip_ticks: 2, gap_through: true } }),
    run({ date: '2026-09-21', latency_ms: 500, entry: { side: 'Buy', price: 1, slip_ticks: 2 },
      exit: { price: 1, kind: 'tp' } }),                                          // no SL slip this run
    run({ date: '2026-09-20', latency_ms: null, entry: { side: 'Buy', price: 1, slip_ticks: null } }),
  ], 'NQ');
  const s = F.fillQualitySummary(rows);
  const tv = 0.25 * 20;
  assert.equal(s.n, 3);
  assert.equal(s.avgEntryTicks, (4 + 2) / 2);              // the null-slip row excluded
  assert.equal(s.avgEntryUsd, ((4 + 2) / 2) * tv);
  assert.equal(s.avgSlTicks, 2);                            // only one row has an SL exit at all
  assert.equal(s.avgSlUsd, 2 * tv);
  assert.equal(s.medianLatencyMs, 400);                     // the null-latency row excluded
});

test('fillQualitySummary: no rows -> n 0 and every average null (never 0/NaN, so the UI can show "—")', () => {
  const s = F.fillQualitySummary([]);
  assert.deepEqual(s, { n: 0, avgEntryTicks: null, avgEntryUsd: null, avgSlTicks: null, avgSlUsd: null, medianLatencyMs: null });
});
