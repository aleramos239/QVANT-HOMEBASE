import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const DE = require('../../homebase/static/charts/dataexport.js');

/* ---- quickRange ---- */

test('quickRange "last5" counts back 5 WEEKDAYS for a classic root, crossing a weekend', () => {
  const today = new Date('2026-09-29T12:00:00Z');           // a Tuesday
  const { start, end } = DE.quickRange('last5', today, false, null);
  assert.equal(end, '2026-09-29');
  // Tue 29, Mon 28, Fri 25, Thu 24, Wed 23 -- 5 weekdays back, skipping Sat 26 / Sun 27
  assert.equal(start, '2026-09-23');
});

test('quickRange "last5" counts every calendar day for a 24/7 root', () => {
  const today = new Date('2026-09-29T12:00:00Z');
  const { start } = DE.quickRange('last5', today, true, null);
  assert.equal(start, '2026-09-25');
});

test('quickRange "month" starts on the 1st of the current month', () => {
  const { start, end } = DE.quickRange('month', new Date('2026-09-15T00:00:00Z'), false, null);
  assert.equal(start, '2026-09-01');
  assert.equal(end, '2026-09-15');
});

test('quickRange "3months" starts on the 1st, two months back (a year boundary included)', () => {
  assert.equal(DE.quickRange('3months', new Date('2026-09-15T00:00:00Z'), false, null).start, '2026-07-01');
  assert.equal(DE.quickRange('3months', new Date('2026-02-10T00:00:00Z'), false, null).start, '2025-12-01');
});

test('quickRange "all" uses the market\'s own available range, or today with none yet', () => {
  const today = new Date('2026-09-15T00:00:00Z');
  assert.deepEqual(DE.quickRange('all', today, false, ['2021-09-22', '2026-09-14']),
    { start: '2021-09-22', end: '2026-09-14' });
  assert.deepEqual(DE.quickRange('all', today, false, null), { start: '2026-09-15', end: '2026-09-15' });
});

test('quickRange returns null for an unknown pick', () => {
  assert.equal(DE.quickRange('bogus', new Date(), false, null), null);
});

/* ---- buildRequest ---- */

const GOOD_CANDLES = { root: 'NQ', type: 'candles', timeframe: '5m', start: '2026-09-01', end: '2026-09-05' };

test('buildRequest fills defaults (contract front, full hours, ET, iso, csv)', () => {
  const { body, error } = DE.buildRequest(GOOD_CANDLES);
  assert.equal(error, undefined);
  assert.deepEqual(body, { root: 'NQ', type: 'candles', contract: 'front', start: '2026-09-01',
    end: '2026-09-05', hours: 'full', tz: 'et', ts_format: 'iso', format: 'csv', timeframe: '5m' });
});

test('buildRequest passes through an explicit contract, rth, utc, epoch and gz', () => {
  const { body } = DE.buildRequest({ ...GOOD_CANDLES, contract: 'NQZ6', hours: 'rth', tz: 'utc',
    ts_format: 'epoch', format: 'gz' });
  assert.equal(body.contract, 'NQZ6');
  assert.equal(body.hours, 'rth');
  assert.equal(body.tz, 'utc');
  assert.equal(body.ts_format, 'epoch');
  assert.equal(body.format, 'gz');
});

test('buildRequest requires a market, a data type, and a date range', () => {
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, root: '' }).error, /market/);
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, type: '' }).error, /data type/);
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, start: '' }).error, /date range/);
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, end: '' }).error, /date range/);
});

test('buildRequest refuses level 3 (disabled) and an end before start', () => {
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, type: 'level3' }).error, /data type/);
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, start: '2026-09-10', end: '2026-09-01' }).error, /From must not be after To/);
});

test('buildRequest requires a timeframe for candles only', () => {
  assert.match(DE.buildRequest({ ...GOOD_CANDLES, timeframe: '' }).error, /timeframe/);
  const ticks = DE.buildRequest({ root: 'NQ', type: 'ticks', start: '2026-09-01', end: '2026-09-01' });
  assert.equal(ticks.error, undefined);
  assert.equal(ticks.body.timeframe, undefined);
});

test('buildRequest validates levels 1-10 for level2 only', () => {
  const base = { root: 'NQ', type: 'level2', start: '2026-09-01', end: '2026-09-01' };
  assert.match(DE.buildRequest({ ...base, levels: 0 }).error, /Levels/);
  assert.match(DE.buildRequest({ ...base, levels: 11 }).error, /Levels/);
  assert.match(DE.buildRequest({ ...base, levels: 'abc' }).error, /Levels/);
  assert.equal(DE.buildRequest({ ...base, levels: 5 }).body.levels, 5);
  assert.equal(DE.buildRequest(GOOD_CANDLES).body.levels, undefined);   // never sent for a type that ignores it
});

/* ---- previewName ---- */

test('previewName matches export.py\'s output_name() naming', () => {
  assert.equal(DE.previewName({ root: 'NQ', type: 'candles', timeframe: '5m', start: '2026-09-01',
    end: '2026-09-02', format: 'csv' }), 'NQ_candles_5m_2026-09-01_2026-09-02.csv');
  assert.equal(DE.previewName({ root: 'NQ', type: 'ticks', start: '2026-09-01', end: '2026-09-02',
    format: 'gz' }), 'NQ_ticks_2026-09-01_2026-09-02.csv.gz');
  assert.equal(DE.previewName(null), '');
});

/* ---- fmtInt / fmtBytes ---- */

test('fmtInt adds thousands separators', () => {
  assert.equal(DE.fmtInt(1234567), '1,234,567');
  assert.equal(DE.fmtInt(0), '0');
  assert.equal(DE.fmtInt(undefined), '0');
});

test('fmtBytes scales to the smallest readable unit', () => {
  assert.equal(DE.fmtBytes(512), '512 B');
  assert.equal(DE.fmtBytes(2048), '2 KB');
  assert.equal(DE.fmtBytes(1536), '1.5 KB');
  assert.equal(DE.fmtBytes(5 * 1024 * 1024), '5 MB');
  assert.equal(DE.fmtBytes(1536 * 1024 * 1024), '1.5 GB');
});

/* ---- progress ---- */

test('progress renders queued/running/done/error/cancelled the way tester.js\'s own shape expects', () => {
  assert.deepEqual(DE.progress(null), { text: '', frac: null, final: false });
  assert.deepEqual(DE.progress({ status: 'queued' }), { text: 'Queued…', frac: null, final: false });
  assert.deepEqual(DE.progress({ status: 'running', sessions_done: 2, sessions_total: 8, rows: 500 }),
    { text: 'Exporting · 2 / 8 sessions, 500 rows', frac: 0.25, final: false });
  assert.deepEqual(DE.progress({ status: 'running', sessions_total: 0 }),
    { text: 'Exporting · starting…', frac: null, final: false });
  assert.deepEqual(DE.progress({ status: 'done', rows: 12345 }), { text: 'Done · 12,345 rows', frac: 1, final: true });
  assert.deepEqual(DE.progress({ status: 'error', error: 'disk full' }),
    { text: 'Failed: disk full', frac: null, final: true });
  assert.deepEqual(DE.progress({ status: 'cancelled' }), { text: 'Cancelled', frac: null, final: true });
});

/* ---- missingSummary ---- */

test('missingSummary reports a count, singular/plural, or nothing when complete', () => {
  assert.equal(DE.missingSummary(null), '');
  assert.equal(DE.missingSummary({ sessions_total: 5, missing: [] }), '');
  assert.equal(DE.missingSummary({ sessions_total: 5, missing: ['2026-09-01'] }), '1 of 5 sessions missing (no file)');
  assert.equal(DE.missingSummary({ sessions_total: 1, missing: ['2026-09-01'] }), '1 of 1 session missing (no file)');
});

test('gapsSummary counts known gaps (a live recording\'s own sidecar) across the sessions that have them', () => {
  assert.equal(DE.gapsSummary(null), '');
  assert.equal(DE.gapsSummary({ missing_hours: {} }), '');
  assert.equal(DE.gapsSummary({ missing_hours: { '2026-09-24': [[1, 2]] } }),
    '1 known gap within 1 session on disk');
  assert.equal(DE.gapsSummary({ missing_hours: { '2026-09-24': [[1, 2], [3, 4]], '2026-09-25': [[5, 6]] } }),
    '3 known gaps within 2 sessions on disk');
});

/* ---- TYPES table ---- */

test('TYPES: level3 is disabled with a reason; level2 needs levels and is depth-only', () => {
  assert.equal(DE.TYPE_OF.level3.disabled, true);
  assert.match(DE.TYPE_OF.level3.reason, /Tradovate/);
  assert.equal(DE.TYPE_OF.level2.needsLevels, true);
  assert.equal(DE.TYPE_OF.level2.depthOnly, true);
  assert.equal(DE.TYPE_OF.candles.needsTimeframe, true);
});

test('refreshView: idle says nothing; running names the step; done reads the coverage; failures show red', () => {
  const steps = [{ key: 'broker', label: 'Fetch missing ticks from the broker', state: 'running', note: '' },
    { key: 'massive', label: 'Fill the older holes from Massive', state: 'waiting', note: '' }];
  assert.deepEqual(DE.refreshView(null), { text: '', busy: false, tone: '' });
  assert.deepEqual(DE.refreshView({ status: 'idle' }), { text: '', busy: false, tone: '' });
  assert.deepEqual(DE.refreshView({ status: 'running', step: 'massive', steps }),
    { text: 'Step 2 of 2: Fill the older holes from Massive…', busy: true, tone: '' });
  // a skipped step is not counted: the run is one step long
  const one = [{ ...steps[0], state: 'done' }, { ...steps[1], state: 'skipped', note: 'Massive credentials are not set for this service' }];
  assert.equal(DE.refreshView({ status: 'running', step: 'broker', steps: one }).text,
    'Step 1 of 1: Fetch missing ticks from the broker…');
  const done = DE.refreshView({ status: 'done', steps: one, coverage: { sessions: 180, complete: 170, missing: 2, partial: 3 } });
  assert.equal(done.text, '170 of 180 recent sessions complete, 2 missing, 3 with holes · Fill the older holes from Massive skipped (Massive credentials are not set for this service)');
  assert.equal(DE.refreshView({ status: 'done', steps: [] }).text, 'Done');
  assert.deepEqual(DE.refreshView({ status: 'error', note: 'Fetch failed (exit 1)' }), { text: 'Failed: Fetch failed (exit 1)', busy: false, tone: 'err' });
  assert.equal(DE.refreshView({ status: 'cancelled' }).text, 'Cancelled');
});

test('the Data tab offers exactly the six roots', () => {
  assert.deepEqual(DE.ROOTS, ['NQ', 'ES', 'YM', 'RTY', 'GC', 'SI']);
});
