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
  assert.deepEqual(S.missing('NQ', base, base + 2 * C, now), [[base + C, now], [base, base + C]]);   // newest first
  S.applyHistory('NQ', { t0: base, t1: base + C, samples: [], episodes: [] });
  assert.deepEqual(S.missing('NQ', base, base + 2 * C, now), [[base + C, now]]);
});

test('the row cap is two days of 1 Hz rows and evicts the oldest first', () => {
  assert.equal(S.MAX_ROWS, 2 * 86_400);
  const n = S.MAX_ROWS + 25, rows = [];
  for (let i = 0; i < n; i++) rows.push(row(i, 0.5));
  S.applyHistory('NQ', { t0: T0, t1: T0 + n * 1000, samples: rows.slice(0, 1000), episodes: [] });
  S.applyLive({ root: 'NQ', samples: rows.slice(1000) });
  assert.equal(S.rowCount('NQ'), S.MAX_ROWS);
  assert.equal(S.meanAt('NQ', T0, T0 + 25_000, 'imb10'), null);                    // the 25 oldest are gone
  assert.equal(S.meanAt('NQ', T0 + 25_000, T0 + 26_000, 'imb10'), 0.5);            // the next one is the oldest kept
  assert.equal(S.meanAt('NQ', T0 + (n - 1) * 1000, T0 + n * 1000, 'imb10'), 0.5);  // the newest is kept
});

test('live cover runs through quiet seconds: a message after a 2 s silence extends the span, a reset starts a new one', () => {
  S.applyLive({ root: 'NQ', reset: true, samples: [row(0), row(1), row(2)] });
  S.applyLive({ root: 'NQ', samples: [row(5)] });                                  // seconds 3 and 4 had no book line
  S.applyLive({ root: 'NQ', samples: [row(6), row(7)] });
  const cov = (r) => S.covered(r);
  assert.deepEqual(cov('NQ'), [[T0, T0 + 8000]]);
  assert.deepEqual(S.missing('NQ', T0, T0 + 8000, T0 + 8000), []);                 // so the history is not asked for it
  S.applyLive({ root: 'ES', reset: true, samples: [row(0)] });
  S.applyLive({ root: 'ES', samples: [row(600)] });                                // ten minutes on: not continuous
  assert.deepEqual(cov('ES'), [[T0, T0 + 1000], [T0 + 600_000, T0 + 601_000]]);
  S.applyLive({ root: 'ES', reset: true, samples: [row(601)] });                   // a reset: never joined to the old end
  assert.deepEqual(cov('ES'), [[T0, T0 + 1000], [T0 + 600_000, T0 + 602_000]]);
  S.applyLive({ root: 'ES', reset: true, samples: [row(604)] });
  assert.deepEqual(cov('ES').slice(-2), [[T0 + 600_000, T0 + 602_000], [T0 + 604_000, T0 + 605_000]]);
});

test('an empty reset greeting ends the live span: the next message never joins the one before the restart', () => {
  S.applyLive({ root: 'GC', reset: true, samples: [row(0), row(1)] });
  S.applyLive({ root: 'GC', reset: true, samples: [] });                            // the service restarted, the book is still empty
  S.applyLive({ root: 'GC', samples: [row(30)] });                                  // 28 s on: under GAP_OK_MS, still not joined
  assert.deepEqual(S.covered('GC'), [[T0, T0 + 2000], [T0 + 30_000, T0 + 31_000]]);
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

const ep = (over) => ({ id: 'b1_7', s: 'b', p: 100, t0: T0, t1: null, pk: 20, r: 5, tr: 0, end: 'open', ab: null, d0: 1, ...over });
const closed = ep({ t1: T0 + 9000, tr: 30, end: 'traded' });
const masked = ep();                                           // what an older chunk's `to` makes of the same episode

test('episodes: a closed copy survives an older chunk fetched second (open copy never replaces closed)', () => {
  S.applyHistory('NQ', { t0: T0 + 5000, t1: T0 + 20_000, samples: [], episodes: [closed] });   // the newer chunk first
  S.applyHistory('NQ', { t0: T0 - 5000, t1: T0 + 5000, samples: [], episodes: [masked] });     // then the older one
  const e = S.episodes('NQ', T0, T0 + 60_000);
  assert.equal(e.length, 1);
  assert.equal(e[0].t1, T0 + 9000);
  assert.equal(e[0].end, 'traded');
  assert.equal(S.episodes('NQ', T0 + 30_000, T0 + 60_000).length, 0);   // so it does not overlap every later window
});

test('episodes: the other fetch order ends closed too; a later live open update replaces an open copy', () => {
  S.applyHistory('NQ', { t0: T0 - 5000, t1: T0 + 5000, samples: [], episodes: [masked] });
  S.applyHistory('NQ', { t0: T0 + 5000, t1: T0 + 20_000, samples: [], episodes: [closed] });
  assert.equal(S.episodes('NQ', T0, T0 + 60_000)[0].end, 'traded');
  S.clear();
  S.applyLive({ root: 'NQ', samples: [], episodes: [ep({ pk: 20 })] });
  S.applyLive({ root: 'NQ', samples: [], episodes: [ep({ pk: 55, r: 9 })] });
  const e = S.episodes('NQ', T0, T0 + 1000);
  assert.equal(e.length, 1);
  assert.equal(e[0].pk, 55);
  assert.equal(e[0].end, 'open');
});

test('episodes: between two open copies the one with the absorption flag wins, then the larger traded size', () => {
  const live = ep({ pk: 40, tr: 90, ab: T0 + 6000 });                // the live copy: flagged, sent once
  const stale = ep({ pk: 40, tr: 70, ab: null });                    // a cached history copy, up to 20 s old
  S.applyLive({ root: 'NQ', samples: [], episodes: [live] });
  S.applyHistory('NQ', { t0: T0, t1: T0 + 20_000, samples: [], episodes: [stale] });
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].ab, T0 + 6000);
  S.clear();
  S.applyHistory('NQ', { t0: T0, t1: T0 + 20_000, samples: [], episodes: [stale] });
  S.applyLive({ root: 'NQ', samples: [], episodes: [live] });         // the flagged one still replaces the stale one
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].ab, T0 + 6000);
  S.clear();
  S.applyLive({ root: 'NQ', samples: [], episodes: [ep({ tr: 90 })] });
  S.applyHistory('NQ', { t0: T0, t1: T0 + 20_000, samples: [], episodes: [ep({ tr: 50 })] });
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].tr, 90);           // neither flagged: the larger traded size stays
  S.applyLive({ root: 'NQ', samples: [], episodes: [ep({ tr: 120 })] });
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].tr, 120);
  S.applyLive({ root: 'NQ', samples: [], episodes: [closed] });       // a closed copy still beats any open one
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].end, 'traded');
});

test('episodes: a closed live copy replaces an open one; between closed copies the larger t1 stays', () => {
  S.applyLive({ root: 'NQ', samples: [], episodes: [masked] });
  S.applyLive({ root: 'NQ', samples: [], episodes: [closed] });
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].end, 'traded');
  S.applyLive({ root: 'NQ', samples: [], episodes: [ep({ t1: T0 + 4000, end: 'pulled' })] });   // an earlier close: ignored
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].t1, T0 + 9000);
  S.applyLive({ root: 'NQ', samples: [], episodes: [ep({ t1: T0 + 12_000, end: 'traded', tr: 40 })] });
  assert.equal(S.episodes('NQ', T0, T0 + 1000)[0].t1, T0 + 12_000);
});

test('rows: a batch repeating the newest t replaces that row in place (order and count kept)', () => {
  const rows = []; for (let i = 0; i < 300; i++) rows.push(row(i, 0.1));
  S.applyLive({ root: 'NQ', samples: rows });
  assert.equal(S.rowCount('NQ'), 300);
  S.applyLive({ root: 'NQ', samples: [row(299, 0.7)] });                       // the same second again, new values
  assert.equal(S.rowCount('NQ'), 300);
  assert.equal(S.meanAt('NQ', T0 + 299_000, T0 + 300_000, 'imb10'), 0.7);
  S.applyLive({ root: 'NQ', samples: [row(299, 0.8), row(300, 0.3), row(300, 0.4), row(301, 0.5)] });   // dup inside a batch
  assert.equal(S.rowCount('NQ'), 302);
  assert.equal(S.meanAt('NQ', T0 + 299_000, T0 + 300_000, 'imb10'), 0.8);
  assert.equal(S.meanAt('NQ', T0 + 300_000, T0 + 301_000, 'imb10'), 0.4);      // the later copy wins
  assert.equal(S.meanAt('NQ', T0 + 298_000, T0 + 299_000, 'imb10'), 0.1);      // earlier rows untouched
  assert.ok(Math.abs(S.meanAt('NQ', T0 + 298_000, T0 + 302_000, 'imb10') - (0.1 + 0.8 + 0.4 + 0.5) / 4) < 1e-9);
});

/* ---- ensure (the browser half): a fresh copy of the module with a fake window and fetch ---- */
function browserStore() {
  const path = require.resolve('../../homebase/static/charts/bookstore.js');
  const had = Object.prototype.hasOwnProperty.call(globalThis, 'window');
  globalThis.window = {};
  delete require.cache[path];
  const B = require(path);
  if (!had) delete globalThis.window;
  delete require.cache[path];
  return B;
}
const CHUNK = 5 * 3600 * 1000;
const A = Math.floor(T0 / CHUNK) * CHUNK;          // an aligned chunk start

test('ensure: a 200 answer that stops short of its chunk is asked once, not again for 30 s, even when a landing handler asks at once', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: A + 8 * 3600 * 1000 });   // the chunk [A, A+5h) is wholly in the past
  const B = browserStore();
  const asked = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const q = new URL(url, 'http://x').searchParams;
    asked.push([Number(q.get('from_ms')), Number(q.get('to_ms'))]);
    return { ok: true, status: 200, json: async () => ({ t0: Number(q.get('from_ms')), t1: Number(q.get('from_ms')) + 1000, samples: [], episodes: [] }) };
  };
  t.after(() => { globalThis.fetch = realFetch; });
  let landings = 0;
  B.onChange((root, kind) => { if (kind === 'history' && ++landings < 50) B.ensure('NQ', A, A + CHUNK); });   // the overlay's handler
  await B.ensure('NQ', A, A + CHUNK);
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(asked, [[A, A + CHUNK]]);                     // once: the handler's immediate re-ask found it held off
  await B.ensure('NQ', A, A + CHUNK);
  t.mock.timers.tick(29_000);
  await B.ensure('NQ', A, A + CHUNK);
  assert.equal(asked.length, 1);                                 // still inside the 30 s
  t.mock.timers.tick(2000);
  await B.ensure('NQ', A, A + CHUNK);
  assert.equal(asked.length, 2);                                 // and then once more, not a loop
});

test('ensure: an answer that covers its chunk is not held off and not asked again', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: A + 12 * 3600 * 1000 });
  const B = browserStore();
  const asked = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const q = new URL(url, 'http://x').searchParams, a = Number(q.get('from_ms')), b = Number(q.get('to_ms'));
    asked.push([a, b]);
    return { ok: true, status: 200, json: async () => ({ t0: a, t1: b, samples: [], episodes: [] }) };
  };
  t.after(() => { globalThis.fetch = realFetch; });
  await B.ensure('NQ', A, A + 2 * CHUNK);
  await B.ensure('NQ', A, A + 2 * CHUNK);                        // the next chunk: one per call
  await B.ensure('NQ', A, A + 2 * CHUNK);
  assert.deepEqual(asked, [[A + CHUNK, A + 2 * CHUNK], [A, A + CHUNK]]);                  // the newest chunk first
});
