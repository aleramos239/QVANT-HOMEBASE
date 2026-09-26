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
