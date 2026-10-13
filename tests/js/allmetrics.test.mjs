import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const A = createRequire(import.meta.url)('../../homebase/static/charts/allmetrics.js');
const T = (date, net, side = 'long') => ({ date, net, side, qty: 1, commission: 2, mfe_usd: Math.max(net, 0), mae_usd: Math.min(net, 0), seconds: 60, bars: 1 });
const trades = [T('2024-03-01', 100), T('2024-03-02', -50), T('2024-03-03', 100, 'short'), T('2025-07-02', -100), T('2025-07-03', 30)];

test('build and unseen are a date cut of the same trades', () => {
  assert.equal(A.pick(trades, 'build').length, 3);
  assert.equal(A.pick(trades, 'unseen').length, 2);
  assert.equal(A.pick(trades, 'all', '2025').length, 2);
  assert.equal(A.pick(trades, 'all', '', 'short').length, 1);
});
test('core numbers', () => {
  const m = A.compute(A.pick(trades, 'build'), 50000);
  assert.equal(m.net, 150); assert.equal(m.trades, 3); assert.equal(m.wins, 2);
  assert.ok(Math.abs(m.win_rate - 66.666) < 0.01); assert.equal(m.profit_factor, 4);
  assert.equal(m.max_dd, -50); assert.equal(m.max_loss_streak, 1); assert.equal(m.long_n, 2); assert.equal(m.short_n, 1);
});
test('empty set and every id present', () => {
  const m = A.compute([], 1000);
  assert.equal(m.trades, 0);
  for (const id of A.ALL_IDS) assert.ok(id in A.compute(trades, 1000), id);
});
test('yearly rows', () => {
  const y = A.yearly(trades, 50000);
  assert.deepEqual(y.map((r) => r.year), ['2024', '2025']);
  assert.equal(y[1].net, -70);
});
