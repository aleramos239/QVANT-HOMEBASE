import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const S = require('../../homebase/static/charts/bookstore.js');
const T0 = 1_790_000_000_000;
const row = (i, imb = 0.1, micro = 100) => [T0 + i * 1000, 20, 30, imb, imb, imb, micro, 1];
beforeEach(() => S.clear());

test('meanAt averages a column over [a, b), ignoring nulls, null when empty', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 5000, samples: [row(0, 0.2), row(1, 0.4), row(2, 0.6, null), row(3, 0.8)], episodes: [] });
  assert.ok(Math.abs(S.meanAt('NQ', T0, T0 + 3000, 'imb10') - 0.4) < 1e-9);
  assert.equal(S.meanAt('NQ', T0, T0 + 4000, 'micro'), 100);
  assert.equal(S.meanAt('NQ', T0 + 9000, T0 + 12000, 'imb10'), null);
  assert.equal(S.meanAt('ES', T0, T0 + 4000, 'imb10'), null);
  assert.equal(S.meanAt('NQ', T0 + 3000, T0, 'imb10'), null);
});

test('rows merge by t: later copy wins, order kept, out-of-order batches fine', () => {
  S.applyLive({ root: 'NQ', samples: [row(5, 0.5), row(6, 0.6)] });
  S.applyHistory('NQ', { t0: T0, t1: T0 + 7000, samples: [row(0, 0.1), row(5, 0.9)], episodes: [] });
  assert.equal(S.rowCount('NQ'), 3);
  assert.equal(S.meanAt('NQ', T0 + 5000, T0 + 6000, 'imb10'), 0.9);
});

test('episodes upsert by id and overlap queries include open ones', () => {
  S.applyLive({ root: 'NQ', samples: [], episodes: [{ id: 'b1_1', s: 'b', p: 100, t0: T0, t1: null, pk: 20, r: 5, tr: 0, end: 'open', ab: null, d0: 1 }] });
  assert.equal(S.episodes('NQ', T0 + 10_000, T0 + 20_000).length, 1);
  S.applyLive({ root: 'NQ', samples: [], episodes: [{ id: 'b1_1', s: 'b', p: 100, t0: T0, t1: T0 + 5000, pk: 20, r: 5, tr: 30, end: 'traded', ab: null, d0: 1 }] });
  const e = S.episodes('NQ', T0 + 10_000, T0 + 20_000);
  assert.equal(e.length, 0);                                   // ended before the window
  assert.equal(S.episodes('NQ', T0, T0 + 20_000)[0].end, 'traded');
});

test('missing: aligned chunks not covered, clipped to now; covered ones are not asked again', () => {
  const C = S.CHUNK_MS, base = Math.floor(T0 / C) * C, now = base + C + 600_000;
  assert.deepEqual(S.missing('NQ', base, base + 2 * C, now), [[base, base + C], [base + C, now]]);
  S.applyHistory('NQ', { t0: base, t1: base + C, samples: [], episodes: [] });
  assert.deepEqual(S.missing('NQ', base, base + 2 * C, now), [[base + C, now]]);
});

test('change listeners fire once per applied message and can be removed', () => {
  let n = 0;
  const off = S.onChange(() => { n++; });
  S.applyLive({ root: 'NQ', samples: [row(0)] });
  S.applyHistory('NQ', { t0: T0, t1: T0 + 1000, samples: [], episodes: [] });
  off();
  S.applyLive({ root: 'NQ', samples: [row(1)] });
  assert.equal(n, 2);
});

test('junk input is dropped, never thrown', () => {
  S.applyLive(null); S.applyLive({}); S.applyHistory('NQ', null);
  S.applyLive({ root: 'NQ', samples: ['x', [NaN], null], episodes: [null, { id: 3 }] });
  assert.equal(S.rowCount('NQ'), 0);
});

test('onChange tells history from live', () => {
  const seen = [];
  const off = S.onChange((root, kind) => seen.push([root, kind]));
  S.applyHistory('NQ', { t0: T0, t1: T0 + 3000, samples: [row(0)], episodes: [] });
  S.applyLive({ root: 'NQ', samples: [row(5)], episodes: [] });
  off();
  S.applyLive({ root: 'NQ', samples: [row(6)], episodes: [] });
  assert.deepEqual(seen, [['NQ', 'history'], ['NQ', 'live']]);
});

test('retryAfter: busy clears in seconds, a paused window in a minute, anything else in half a minute', () => {
  assert.equal(S.retryAfter(503, 'busy — try again in a moment'), 2000);
  assert.equal(S.retryAfter(503, 'chart history is paused 09:20-09:35 ET'), 60_000);
  assert.equal(S.retryAfter(503, null), 60_000);
  assert.equal(S.retryAfter(404, 'unknown root'), 30_000);
  assert.equal(S.retryAfter(0, null), 30_000);
});
