import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const SB = require('../../homebase/static/charts/scrollback.js');

test('the view\'s left edge within 50 bars of the first bar asks once; nothing more until the answer', () => {
  const s = new SB.ScrollBack();
  assert.equal(SB.EDGE, 50);
  assert.equal(s.want({ from: 51, to: 200 }, 1000), null);
  const req = s.want({ from: 50, to: 200 }, 1000);
  assert.deepEqual(req, { before: 1000 });
  s.sent(req);
  assert.equal(s.want({ from: -10, to: 100 }, 1000), null);            // pending: no second request
  assert.equal(s.take({ before: 999, bars: [] }), false);               // not the one pending: stale
  assert.equal(s.want({ from: -10, to: 100 }, 1000), null);            // still pending
  assert.equal(s.take({ before: 1000, bars: [{}], done: false }), true);
  assert.deepEqual(s.want({ from: 3, to: 100 }, 500), { before: 500 }); // free again
});

test('the archive\'s start ends the requests until a new history; a failure waits 10 s', () => {
  let now = 0;
  const s = new SB.ScrollBack({ now: () => now });
  s.sent({ before: 1000 });
  assert.equal(s.take({ before: 1000, bars: [], done: true }), true);
  assert.equal(s.done, true);
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  s.reset();
  assert.deepEqual(s.want({ from: 0, to: 10 }, 1000), { before: 1000 });
  s.sent({ before: 1000 });
  assert.equal(s.take({ before: 1000, error: 'disk' }), false);
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  now = SB.RETRY_MS - 1;
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  now = SB.RETRY_MS;
  assert.deepEqual(s.want({ from: 0, to: 10 }, 1000), { before: 1000 });
  assert.equal(s.want(null, 1000), null);
  assert.equal(s.want({ from: 0, to: 10 }, undefined), null);
});

test('a "busy" answer clears pending (never stuck) and retries after 2 s, sooner than an ordinary failure', () => {
  let now = 0;
  const s = new SB.ScrollBack({ now: () => now });
  const req = s.want({ from: 0, to: 10 }, 1000);
  s.sent(req);
  assert.equal(s.take({ before: 1000, error: 'busy' }), false);
  assert.equal(s.pending, null);                                        // cleared, not left stuck
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);                 // still cooling down
  now = SB.BUSY_RETRY_MS - 1;
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  now = SB.BUSY_RETRY_MS;
  assert.equal(SB.BUSY_RETRY_MS < SB.RETRY_MS, true);
  assert.deepEqual(s.want({ from: 0, to: 10 }, 1000), { before: 1000 }); // free again, well before a plain failure would be
});

test('a pending request with no answer at all for 30 s is given up on, so scroll-back never deadlocks', () => {
  let now = 0;
  const s = new SB.ScrollBack({ now: () => now });
  const req = s.want({ from: 0, to: 10 }, 1000);
  s.sent(req);
  now = SB.PENDING_TIMEOUT_MS - 1;
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);                 // still within the window: held
  now = SB.PENDING_TIMEOUT_MS;
  assert.deepEqual(s.want({ from: 0, to: 10 }, 1000), { before: 1000 }); // no answer ever came: free to ask again
  s.sent({ before: 1000 });
  now += SB.PENDING_TIMEOUT_MS - 1;
  assert.equal(s.take({ before: 1000, bars: [], done: true }), true);    // a late answer still lands if it beats the timeout
});

test('prepend: the older bars in front with their study values; the chart\'s first bars take the repair', () => {
  const mine = [{ ms: 300, sv: { ema: 1, vwap: 9 } }, { ms: 400, sv: { ema: 2, vwap: 9 } }, { ms: 500, sv: { ema: 3 } }];
  const m = { bars: [{ ms: 100 }, { ms: 200 }], studies: { ema: [0.1, 0.2], vwap: [5, 6] }, repair: { ema: [1.5, 2.5] } };
  const all = SB.prepend(mine, m);
  assert.deepEqual(all.map((b) => b.ms), [100, 200, 300, 400, 500]);
  assert.deepEqual(all.map((b) => b.sv.ema), [0.1, 0.2, 1.5, 2.5, 3]);
  assert.deepEqual(all.map((b) => b.sv.vwap), [5, 6, 9, 9, undefined]);
  assert.equal(all[2], mine[0]);                                        // the chart's bar objects are kept
});

test('session labels: the older ones in front, one per date', () => {
  const got = SB.mergeSessions([{ date: '2026-09-18' }, { date: '2026-09-21', approx: true }],
    [{ date: '2026-09-21' }, { date: '2026-09-22' }]);
  assert.deepEqual(got.map((s) => s.date), ['2026-09-18', '2026-09-21', '2026-09-22']);
  assert.equal(got[1].approx, undefined);                               // the chart's own label wins
});

// ---- Fix round 1: the 200,000-bar client memory cap ----
test('the bar cap: an older chunk that would overflow it is cropped to fit, and capped becomes true', () => {
  assert.equal(SB.CAP, 200000);
  const mine = Array.from({ length: 199998 }, (_, i) => ({ ms: 1000 + i }));
  const m = { bars: [{ ms: 100 }, { ms: 200 }, { ms: 300 }], studies: { ema: [1, 2, 3] } };
  const a = SB.capPrepend(mine, m);
  assert.equal(a.bars.length, 200000);                                  // never over the cap
  assert.equal(a.capped, true);
  assert.deepEqual(a.bars.slice(0, 2).map((b) => b.ms), [200, 300]);    // cropped to the chunk's newest end
  assert.deepEqual(a.bars.slice(0, 2).map((b) => b.sv.ema), [2, 3]);    // studies cropped along with it
  assert.equal(a.bars[2], mine[0]);                                     // the chart's own bars: never touched
});

test('the bar cap: room for the whole chunk leaves capped false', () => {
  const mine = Array.from({ length: 100 }, (_, i) => ({ ms: i }));
  const a = SB.capPrepend(mine, { bars: [{ ms: -1 }], studies: {} });
  assert.equal(a.capped, false);
  assert.equal(a.bars.length, 101);
});

test('the bar cap: already at the cap refuses outright, no eviction', () => {
  const mine = Array.from({ length: 200000 }, (_, i) => ({ ms: i }));
  const a = SB.capPrepend(mine, { bars: [{ ms: -1 }], studies: {} });
  assert.equal(a.capped, true);
  assert.equal(a.bars, mine);                                           // untouched: nothing added, nothing dropped
});
