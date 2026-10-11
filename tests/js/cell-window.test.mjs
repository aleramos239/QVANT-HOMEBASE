import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The window: cell.showWindow() asks the server for the sessions ending at a time (the `older` request), and the
   answer becomes the chart's bars -- same interval, no live updates until the next history. Driven on a bare
   object, the seam being the bookkeeping, not the chart. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/scrollback.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
const P = Cell.prototype;

function bare(over = {}) {
  const sent = [];
  const c = { sent, id: 'c1', chart: {}, bars: [{ ms: 9e12 }], inflight: [], has: { fp: false, big: false, flow: false }, windowAt: null, winReq: null,
    back: new globalThis.HBScrollBack.ScrollBack(), sessions: [], keys: new Set(), host: { send: (m) => { sent.push(m); return true; }, onLoaded() {} },
    slotted: (b) => b, append(b) { this.bars.push(b); }, build() { this.built = (this.built || 0) + 1; }, message(t) { this.msg = t; },
    showWindow: P.showWindow, onWindow: P.onWindow, onOlder: P.onOlder, onUpdate: P.onUpdate, ...over };
  return c;
}
const ans = (before, over = {}) => ({ type: 'older', id: 'c1', before, bars: [{ ms: 100 }, { ms: 200 }], studies: { sma: [1, 2] }, sessions: [{ date: '2023-03-03' }], done: false, ...over });

test('showWindow sends the older request for the end time and resolves true when it lands', async () => {
  const c = bare();
  const p = c.showWindow(5000);
  assert.deepEqual(c.sent, [{ op: 'older', id: 'c1', before: 5000, fp: false, big: false, flow: false }]);
  c.onOlder(ans(5000));
  assert.equal(await p, true);
  assert.equal(c.windowAt, 5000);
  assert.deepEqual(c.bars.map((b) => b.ms), [100, 200]);
  assert.deepEqual(c.bars.map((b) => b.sv), [{ sma: 1 }, { sma: 2 }]);
  assert.equal(c.built, 1);
  assert.match(c.msg, /not live/);
  assert.equal(c.winReq, null);
});

test('an older answer for some other time is the ordinary scroll-back, not the window', async () => {
  const c = bare();
  c.showWindow(5000);
  c.onOlder(ans(4000));                       // no pending scroll-back request either: dropped, window still waits
  assert.equal(c.windowAt, null);
  assert.notEqual(c.winReq, null);
  c.winReq.resolve(false);                    // its retry timer must not keep the test process alive
});

test('a refused window resolves false and changes nothing', async () => {
  const c = bare();
  const p = c.showWindow(5000);
  c.onOlder({ type: 'older', id: 'c1', before: 5000, error: 'no such session' });
  assert.equal(await p, false);
  assert.equal(c.windowAt, null);
  assert.deepEqual(c.bars, [{ ms: 9e12 }]);
});

test('a window waits for a sub in flight before asking', async () => {
  const c = bare({ inflight: [{}] });
  c.showWindow(5000);
  assert.deepEqual(c.sent, []);
  c.winReq.resolve(false);                    // (the timer's retry is not waited for here)
  clearTimeout(c.winReq && c.winReq.timer);
});

test('live updates are ignored while a window is shown', () => {
  const c = bare({ windowAt: 5000, candles: { update() { throw new Error('drawn'); } }, lines: [] });
  assert.equal(c.onUpdate({ closed: [{ ms: 1 }], studies: {} }), undefined);
  assert.deepEqual(c.bars, [{ ms: 9e12 }]);
});
