import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const R = require('../../homebase/static/charts/replay.js');

test('parseState: the server\'s replay_state, normalised; garbage in is null', () => {
  assert.deepEqual(R.parseState({ type: 'replay_state', id: 'c1', date: '2024-03-08', cursor_ms: 1000, speed: 5,
    playing: true, done: false }), { id: 'c1', date: '2024-03-08', cursorMs: 1000, speed: 5, playing: true, done: false, stopped: false });
  assert.deepEqual(R.parseState({ id: 'c1', date: '2024-03-08', cursor_ms: 1, speed: 'bar', playing: false, done: true, stopped: true }),
    { id: 'c1', date: '2024-03-08', cursorMs: 1, speed: 'bar', playing: false, done: true, stopped: true });
  assert.equal(R.parseState(null), null);
  assert.equal(R.parseState('nope'), null);
  // a garbage speed defaults to 1 rather than propagating something the UI cannot label
  assert.equal(R.parseState({ id: 'c1', date: '2024-03-08', cursor_ms: 1, speed: 99, playing: false, done: false }).speed, 1);
  // a non-string id/date/non-finite cursor all fall back to safe defaults, never throwing
  assert.deepEqual(R.parseState({}), { id: '', date: '', cursorMs: 0, speed: 1, playing: false, done: false, stopped: false });
});

test('fmtCursor: cursor_ms as an ET date + time (2024-03-08 is EST, UTC-5)', () => {
  // 2024-03-08 14:31:05 UTC = 09:31:05 EST
  const ms = Date.UTC(2024, 2, 8, 14, 31, 5);
  assert.equal(R.fmtCursor(ms), '2024-03-08 09:31:05 ET');
  // 2024-07-08 13:31:05 UTC = 09:31:05 EDT (daylight saving)
  const dst = Date.UTC(2024, 6, 8, 13, 31, 5);
  assert.equal(R.fmtCursor(dst), '2024-07-08 09:31:05 ET');
  assert.equal(R.fmtCursor(null), '');
  assert.equal(R.fmtCursor(NaN), '');
});

test('validStart: the archive window (2021-09-22 to yesterday), HH:MM only', () => {
  assert.equal(R.validStart('2024-03-08', '09:30', '2024-03-09'), true);
  assert.equal(R.validStart('2021-09-22', '00:00', '2024-03-09'), true);   // the archive's first session
  assert.equal(R.validStart('2021-09-21', '09:30', '2024-03-09'), false);  // before the archive
  assert.equal(R.validStart('2024-03-09', '09:30', '2024-03-09'), false);  // today is not a completed session
  assert.equal(R.validStart('2024-03-10', '09:30', '2024-03-09'), false);  // after today
  assert.equal(R.validStart('2024-03-08', '24:00', '2024-03-09'), false);  // hour out of range
  assert.equal(R.validStart('2024-03-08', '09:60', '2024-03-09'), false);  // minute out of range
  assert.equal(R.validStart('2024-03-08', '9:30', '2024-03-09'), false);   // must be zero-padded
  assert.equal(R.validStart('03/08/2024', '09:30', '2024-03-09'), false);
  assert.equal(R.validStart(null, '09:30', '2024-03-09'), false);
  assert.equal(R.validStart('2024-03-08', null, '2024-03-09'), false);
});

test('speedLabel: 1x .. 60x, and Bar', () => {
  assert.equal(R.speedLabel(1), '1×');
  assert.equal(R.speedLabel(2), '2×');
  assert.equal(R.speedLabel(60), '60×');
  assert.equal(R.speedLabel('bar'), 'Bar');
});

test('startOp: always speed "bar" (the floating bar\'s speed menu changes it after)', () => {
  assert.deepEqual(R.startOp('c1', '2024-03-08', '09:30'), { op: 'replay_start', id: 'c1', date: '2024-03-08', start_et: '09:30', speed: 'bar' });
  assert.deepEqual(R.startOp(2, '2024-03-08', '09:30'), { op: 'replay_start', id: '2', date: '2024-03-08', start_et: '09:30', speed: 'bar' });
});

test('ctlOp: play / pause / step take no extra fields; speed / jump carry theirs', () => {
  assert.deepEqual(R.ctlOp('c1', 'play'), { op: 'replay_ctl', id: 'c1', action: 'play' });
  assert.deepEqual(R.ctlOp('c1', 'pause'), { op: 'replay_ctl', id: 'c1', action: 'pause' });
  assert.deepEqual(R.ctlOp('c1', 'step'), { op: 'replay_ctl', id: 'c1', action: 'step' });
  assert.deepEqual(R.ctlOp('c1', 'speed', { speed: 5 }), { op: 'replay_ctl', id: 'c1', action: 'speed', speed: 5 });
  assert.deepEqual(R.ctlOp('c1', 'jump', { to_et: '10:00' }), { op: 'replay_ctl', id: 'c1', action: 'jump', to_et: '10:00' });
});

test('stopOp', () => {
  assert.deepEqual(R.stopOp('c1'), { op: 'replay_stop', id: 'c1' });
});

test('SPEEDS / FIRST_DATE are exported for the UI\'s speed menu and date field', () => {
  assert.deepEqual(R.SPEEDS, [1, 2, 5, 10, 30, 60, 'bar']);
  assert.equal(R.FIRST_DATE, '2021-09-22');
});
