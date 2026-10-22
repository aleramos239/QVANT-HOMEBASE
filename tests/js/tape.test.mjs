import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const Tape = require('../../homebase/static/charts/tape.js');

const T0 = 1761053400000;   // 2025-10-21 09:30:00.000 ET
const row = (ms, px, size, side, id) => [T0 + ms, px, size, side, id];
const msg = (rows, i0, extra) => ({ type: 'tape', root: 'NQ', s: '2025-10-21', i0, rows, ...extra });

test('apply: the first message seeds the ring, the next appends only the rows past what was applied', () => {
  let st = Tape.apply(Tape.empty(), msg([row(0, 100, 1, 1, 1), row(1, 100, 2, 1, 2)], 0, { reset: true }));
  assert.equal(st.root, 'NQ');
  assert.equal(st.i0, 0);
  assert.equal(st.next, 2);
  assert.equal(st.rows.length, 2);
  // an overlapping message (its i0 is behind next): only the unseen tail lands
  const st2 = Tape.apply(st, msg([row(1, 100, 2, 1, 2), row(2, 101, 3, -1, 3)], 1));
  assert.equal(st2.rows.length, 3);
  assert.equal(st2.next, 3);
  assert.deepEqual(st2.rows[2], row(2, 101, 3, -1, 3));
  assert.equal(st.rows.length, 2, 'the previous state is not mutated');
  // a message fully behind next is a no-op (the same state back)
  assert.equal(Tape.apply(st2, msg([row(2, 101, 3, -1, 3)], 2)), st2);
});

test('apply: reset, another root or another session replaces the ring; i0 follows the message', () => {
  const st = Tape.apply(Tape.empty(), msg([row(0, 100, 1, 1, 1)], 0));
  const reset = Tape.apply(st, msg([row(5, 200, 7, -1, 9)], 40, { reset: true }));
  assert.equal(reset.rows.length, 1);
  assert.equal(reset.i0, 40);
  assert.equal(reset.next, 41);
  const other = Tape.apply(st, { ...msg([row(5, 200, 7, -1, 9)], 3), root: 'ES' });
  assert.equal(other.root, 'ES');
  assert.equal(other.rows.length, 1);
  const roll = Tape.apply(st, { ...msg([row(5, 200, 7, -1, 9)], 0), s: '2025-10-22' });
  assert.equal(roll.rows.length, 1);
});

test('apply: the ring keeps the newest RING rows and i0 moves with the ones dropped', () => {
  const rows = Array.from({ length: Tape.RING + 10 }, (_, k) => row(k, 100, 1, 1, k));
  const st = Tape.apply(Tape.empty(), msg(rows, 100, { reset: true }));
  assert.equal(st.rows.length, Tape.RING);
  assert.equal(st.i0, 110);
  assert.equal(st.next, 100 + rows.length);
  assert.equal(st.rows[0][4], 10);
});

test('orders: consecutive prints with the same ms and side are one order; a side flip inside the ms splits it', () => {
  const rows = [row(0, 100, 2, 1, 1), row(0, 100.25, 3, 1, 2), row(0, 100.5, 5, 1, 3),   // one buy sweeping 3 levels
    row(0, 100.25, 1, -1, 4),                                                             // a sell in the same ms
    row(0, 100.5, 4, 1, 5),                                                               // buy again: a new order
    row(1, 100.5, 1, 1, 6)];                                                              // next ms
  const o = Tape.orders(rows, 10);
  assert.equal(o.length, 4);
  assert.deepEqual(o[0], { t: T0, side: 1, size: 10, n: 3, lo: 100, hi: 100.5, vwap: (200 + 300.75 + 502.5) / 10, i0: 10 });
  assert.deepEqual(o[1], { t: T0, side: -1, size: 1, n: 1, lo: 100.25, hi: 100.25, vwap: 100.25, i0: 13 });
  assert.equal(o[2].i0, 14);
  assert.equal(o[3].t, T0 + 1);
});

test('orders: a run cut across two messages continues the previous last order (without mutating it)', () => {
  const a = Tape.orders([row(0, 100, 2, 1, 1), row(0, 100.25, 2, 1, 2)], 0);
  const last = a[a.length - 1];
  const b = Tape.orders([row(0, 100.5, 6, 1, 3), row(1, 100.5, 1, -1, 4)], 2, last);
  assert.equal(b.length, 2);
  assert.deepEqual(b[0], { t: T0, side: 1, size: 10, n: 3, lo: 100, hi: 100.5, vwap: (200 + 200.5 + 603) / 10, i0: 0 });
  assert.equal(last.size, 4, 'the previous order is left as it was');
  // not continued when the rows do not start exactly where the previous order ended, or the ms/side differ
  assert.equal(Tape.orders([row(0, 100.5, 6, 1, 3)], 3, last).length, 1);
  assert.equal(Tape.orders([row(0, 100.5, 6, 1, 3)], 3, last)[0].size, 6);
  assert.equal(Tape.orders([row(0, 100.5, 6, -1, 3)], 2, last)[0].size, 6);
});

test('prints: every row is its own order, in the same shape', () => {
  const p = Tape.prints([row(0, 100, 2, 1, 1), row(0, 100, 3, 1, 2)], 7);
  assert.equal(p.length, 2);
  assert.deepEqual(p[1], { t: T0, side: 1, size: 3, n: 1, lo: 100, hi: 100, vwap: 100, i0: 8 });
});

test('filter: size bounds and side; null bounds and side 0 keep everything', () => {
  const list = Tape.orders([row(0, 100, 2, 1, 1), row(1, 100, 30, -1, 2), row(2, 100, 300, 1, 3)], 0);
  assert.equal(Tape.filter(list, null, null, 0).length, 3);
  assert.deepEqual(Tape.filter(list, 10, null, 0).map((x) => x.size), [30, 300]);
  assert.deepEqual(Tape.filter(list, 10, 100, 0).map((x) => x.size), [30]);
  assert.deepEqual(Tape.filter(list, 0, null, 1).map((x) => x.size), [2, 300]);
  assert.deepEqual(Tape.filter(list, 0, null, -1).map((x) => x.size), [30]);
});

test('fmtTime: New York wall time to the millisecond', () => {
  assert.equal(Tape.fmtTime(T0 + 1234), '09:30:01.234');
  assert.equal(Tape.fmtTime(Date.UTC(2025, 0, 6, 14, 30, 0, 5)), '09:30:00.005');   // EST in January
  assert.equal(Tape.fmtTime(null), '');
});
