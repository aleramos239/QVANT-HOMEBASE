import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const E = require('../../homebase/static/charts/bookevents.js');

const ep = (o) => ({ id: 'x', s: 'b', p: 100, t0: 0, t1: 20_000, pk: 300, r: 6, tr: 0, end: 'faded', ab: null, d0: 5, ...o });

test('segments: ratio and age filters; an open level runs to now', () => {
  const eps = [ep({ id: 'a' }), ep({ id: 'low', r: 3 }), ep({ id: 'short', t1: 2000 }), ep({ id: 'open', t1: null })];
  const s = E.segments(eps, { multiple: 5, minSeconds: 5, now: 60_000 });
  assert.deepEqual(s.map((x) => x.id), ['a', 'open']);
  assert.equal(s[1].t1, 60_000);
  assert.equal(s[1].open, true);
  assert.deepEqual(E.segments(eps, { multiple: 2, minSeconds: 1, now: 60_000 }).map((x) => x.id), ['a', 'low', 'short', 'open']);
});

test('segments: a malformed row is skipped, never throws', () => {
  assert.deepEqual(E.segments([null, {}, ep({ r: NaN })], { multiple: 5, minSeconds: 5 }), []);
  assert.deepEqual(E.segments(undefined), []);
});

test('absorptions: only flagged levels, the bid absorbing is "up"', () => {
  const eps = [ep({ id: 'b', ab: 12_000, r: 8, tr: 700 }), ep({ id: 'a', s: 'a', ab: 15_000, r: 8 }), ep({ id: 'none', ab: null, r: 9 }),
    ep({ id: 'early', ab: 1000, r: 9 })];
  const a = E.absorptions(eps, { multiple: 4, minSeconds: 5 });
  assert.deepEqual(a.map((x) => [x.id, x.side, x.t]), [['b', 'up', 12_000], ['a', 'down', 15_000]]);
});

test('pulls: only ended-as-pulled levels, at the end time', () => {
  const eps = [ep({ id: 'p', end: 'pulled', t1: 30_000 }), ep({ id: 't', end: 'traded' }), ep({ id: 'o', end: 'pulled', t1: null })];
  assert.deepEqual(E.pulls(eps, { multiple: 5, minSeconds: 5 }).map((x) => [x.id, x.t, x.side]), [['p', 30_000, 'b']]);
});

/* ---- clipAt / askSpan: what Bar Replay relies on ---- */

test('clipAt: an episode that began after the cursor is gone, one that ended after it is still open, a late flag is unset', () => {
  const eps = [ep({ id: 'ok', t0: 0, t1: 5000 }), ep({ id: 'later', t0: 11_000, t1: 12_000 }),
    ep({ id: 'ends', t0: 0, t1: 20_000, end: 'traded', ab: 18_000 }), ep({ id: 'flag', t0: 0, t1: 5000, ab: 15_000 })];
  const out = E.clipAt(eps, 10_000);
  assert.deepEqual(out.map((x) => x.id), ['ok', 'ends', 'flag']);
  assert.equal(out[0], eps[0]);                                       // untouched rows are returned as they are
  assert.deepEqual([out[1].t1, out[1].end, out[1].ab], [null, 'open', null]);
  assert.deepEqual([out[2].t1, out[2].ab], [5000, null]);
  assert.equal(eps[1].t0, 11_000); assert.equal(eps[2].t1, 20_000);     // the store's copy is not mutated
  assert.deepEqual(E.clipAt(undefined, 1), []);
});

test('askSpan: never past the limit, nothing for an unknown limit or an empty span', () => {
  assert.deepEqual(E.askSpan(100, 900, 5000), [100, 900]);
  assert.deepEqual(E.askSpan(100, 900, 500), [100, 500]);
  assert.equal(E.askSpan(100, 900, 100), null);
  assert.equal(E.askSpan(100, 900, null), null);
  assert.equal(E.askSpan(-Infinity, 900, 5000), null);
  assert.equal(E.askSpan(100, NaN, 5000), null);
});

test('askSpan: a zoomed-out view asks only for the newest 48 h before its end', () => {
  const DAY = 86_400_000, end = T0 + 10 * 60_000;
  const span = E.askSpan(end - 69 * DAY, end, Date.now());
  assert.deepEqual(span, [end - 48 * 3_600_000, end]);
  const S = require('../../homebase/static/charts/bookstore.js');
  S.clear();
  assert.ok(S.missing('NQ', span[0], span[1], end).length <= Math.ceil(48 / 5) + 1);    // at most 11 chunks of 5 h
  assert.deepEqual(E.askSpan(end - DAY, end, Date.now()), [end - DAY, end]);            // a day: untouched
  assert.deepEqual(E.askSpan(end - 69 * DAY, end + 5 * DAY, end), [end - 48 * 3_600_000, end]);   // measured from the limit
});

/* ---- the overlay, on a fake chart (the browser half of the module) ---- */

const T0 = 1_790_000_000_000;      // well in the past, so Date.now() is always after the bars
const BAR = 60_000;

function rig({ replay = null, indicators, n = 10, bar = BAR, t0 = T0 } = {}) {
  const S = require('../../homebase/static/charts/bookstore.js');
  S.clear();
  const calls = { ensure: [], refresh: [], attach: 0, detach: 0 };
  const store = { ...S, ensure: (root, from, to) => { calls.ensure.push([root, from, to]); } };
  class Layer { constructor(P) { this.P = P; this.redraws = 0; } redraw() { this.redraws++; } }
  globalThis.window = {
    HBBookStore: store, HBLayers: { Layer }, HBLiquidity: require('../../homebase/static/charts/liquidity.js'),
    HBDrawings: require('../../homebase/static/charts/drawings.js'), HBCatalog: { serverKey: (x) => x.key || x.id },
  };
  const path = require.resolve('../../homebase/static/charts/bookevents.js');
  delete require.cache[path];
  const M = require(path);
  const range = { from: 0, to: n - 1 };
  const cell = {
    cfg: { root: 'NQ', indicators: indicators || [
      { id: 'bigorders', visible: true, params: { multiple: 5, minSeconds: 5, history: true } },
      { id: 'absorb', visible: true, params: { multiple: 4, minSeconds: 5 } }] },
    shown: { root: 'NQ' }, P: {}, replay,
    bars: Array.from({ length: n }, (_, i) => ({ ms: t0 + i * bar })),
    isTime: () => true, barMs: () => bar,
    chart: { timeScale: () => ({ getVisibleLogicalRange: () => range, logicalToCoordinate: (i) => i * 100,
      subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} }) },
    candles: { attachPrimitive() { calls.attach++; }, detachPrimitive() { calls.detach++; }, priceToCoordinate: (p) => p },
    refreshBookSeries: (all) => calls.refresh.push(all),
  };
  const ctx = { log: [], strokeStyle: '', fillStyle: '', globalAlpha: 1, lineWidth: 1 };
  for (const k of ['beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'fillRect', 'arc', 'closePath']) ctx[k] = (...a) => ctx.log.push([k, ...a]);
  const target = { useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 2000, height: 500 } }) };
  return { M, S, cell, calls, ctx, target };
}
const xOf = (ms) => ((ms - T0) / BAR) * 100 + 0;     // logicalAt: i - 0.5 + frac, coordinate i*100 -> -50 + ...
const X = (ms) => xOf(ms) - 50;

test('overlay: ended levels are drawn with their cap, a standing one is left to the live line', () => {
  const r = rig();
  r.S.applyHistory('NQ', { t0: T0, t1: T0 + 10 * BAR, samples: [], episodes: [
    ep({ id: 'sq', p: 50, t0: T0 + 60_000, t1: T0 + 180_000, end: 'traded' }),
    ep({ id: 'ring', p: 60, s: 'a', t0: T0 + 60_000, t1: T0 + 180_000, end: 'pulled' }),
    ep({ id: 'standing', p: 70, t0: T0 + 60_000, t1: null, end: 'open' })] });
  const o = r.M.overlay(r.cell);
  o.layer.draw(r.target);
  const k = (n) => r.ctx.log.filter((c) => c[0] === n);
  assert.equal(k('lineTo').length, 2);                                 // sq and ring, not the standing one
  assert.deepEqual(k('moveTo').map((c) => c[2]).sort(), [50, 60]);
  assert.equal(k('fillRect').length, 1);                               // traded = filled square
  assert.equal(k('arc').length, 1);                                    // pulled = hollow circle
  assert.ok(Math.abs(k('lineTo')[0][1] - X(T0 + 180_000)) < 1e-6);
  o.destroy();
  assert.equal(r.calls.detach, 1);
});

test('overlay: the visible span is asked of the store, up to now', () => {
  const r = rig();
  const o = r.M.overlay(r.cell);
  assert.equal(r.calls.ensure.length, 1);
  assert.deepEqual(r.calls.ensure[0], ['NQ', T0, T0 + 10 * BAR]);
  o.destroy();
});

test('overlay: 100k one-minute bars in view ask for the newest 48 h only', () => {
  const t0 = T0 - 70 * 86_400_000, end = t0 + 100_000 * 60_000;     // 69 days ending 1 day before T0 (a past)
  const r = rig({ n: 100_000, bar: 60_000, t0 });
  const o = r.M.overlay(r.cell);
  assert.equal(r.calls.ensure.length, 1);
  assert.deepEqual(r.calls.ensure[0], ['NQ', end - 48 * 3_600_000, end]);
  assert.ok(r.S.missing('NQ', r.calls.ensure[0][1], r.calls.ensure[0][2], end).length <= 11);
  o.destroy();
});

test('overlay, Bar Replay: nothing is asked past the cursor and an episode is drawn as the cursor saw it', () => {
  const cursor = T0 + 4 * BAR;
  const r = rig({ replay: { cursorMs: cursor } });
  r.S.applyHistory('NQ', { t0: T0, t1: T0 + 10 * BAR, samples: [], episodes: [
    ep({ id: 'cut', p: 50, t0: T0 + BAR, t1: T0 + 8 * BAR, end: 'traded', ab: T0 + 6 * BAR, r: 9 }),
    ep({ id: 'future', p: 60, t0: T0 + 6 * BAR, t1: T0 + 8 * BAR, end: 'pulled' }),
    ep({ id: 'done', p: 70, t0: T0 + BAR, t1: T0 + 3 * BAR, end: 'traded' })] });
  const o = r.M.overlay(r.cell);
  assert.deepEqual(r.calls.ensure, [['NQ', T0, cursor]]);              // never past the cursor
  o.layer.draw(r.target);
  const k = (n) => r.ctx.log.filter((c) => c[0] === n);
  assert.ok(k('lineTo').every((c) => c[1] <= X(cursor) + 1e-6));       // nothing right of the cursor
  assert.equal(k('moveTo').filter((c) => c[2] === 60).length, 0);      // 'future' began after it
  assert.equal(k('moveTo').filter((c) => c[2] === 50).length, 1);      // 'cut' is still open at the cursor: a segment to it
  assert.equal(k('fillRect').length, 1);                               // only 'done' has ended (a square); 'cut' has no cap yet
  assert.equal(k('closePath').length, 0);                              // and its absorption flag (after the cursor) is not set
  o.destroy();
});

test('overlay, Bar Replay: an unknown cursor asks for nothing', () => {
  const r = rig({ replay: { cursorMs: null } });
  const o = r.M.overlay(r.cell);
  o.onBars();
  assert.deepEqual(r.calls.ensure, []);
  o.destroy();
});

test('overlay: history landing is one series refresh per paint tick, and asks for the next chunk', async (t) => {
  t.mock.timers.enable({ apis: ['setInterval'] });
  const r = rig({ indicators: [{ id: 'bkimb', key: 'bk:imb10', visible: true, params: {} }] });
  const o = r.M.overlay(r.cell);
  assert.equal(r.calls.ensure.length, 1);
  for (let i = 0; i < 3; i++) r.S.applyHistory('NQ', { t0: T0 + i * 1000, t1: T0 + i * 1000 + 1000, samples: [], episodes: [] });
  assert.equal(r.calls.ensure.length, 4);                              // each landed chunk asks again (one chunk per ensure)
  r.S.applyHistory('ES', { t0: T0, t1: T0 + 1000, samples: [], episodes: [] });
  assert.equal(r.calls.ensure.length, 4);                              // another root is not ours
  t.mock.timers.tick(250);
  assert.deepEqual(r.calls.refresh, [true]);                           // three landings, one setData
  t.mock.timers.tick(250);
  assert.deepEqual(r.calls.refresh, [true]);                           // nothing changed: nothing refreshed
  r.S.applyLive({ root: 'NQ', samples: [[T0 + 5000, 1, 1, 0, 0, 0, 100, 1]], episodes: [] });
  t.mock.timers.tick(250);
  assert.deepEqual(r.calls.refresh, [true, false]);                    // a live second: the newest bar only
  o.destroy();
  t.mock.timers.tick(1000);
  assert.deepEqual(r.calls.refresh, [true, false]);                    // a destroyed overlay stays silent
});

test('overlay: nothing of ours on the chart, nothing asked and nothing drawn', () => {
  const r = rig({ indicators: [{ id: 'rsi', visible: true, params: {} }] });
  const o = r.M.overlay(r.cell);
  o.layer.draw(r.target);
  assert.deepEqual(r.calls.ensure, []);
  assert.equal(r.ctx.log.length, 0);
  o.destroy();
});

test('flow layer: bubbles of the heatmap and sweeps of the big prints, each only while its option is on', () => {
  const r = rig({ indicators: [{ id: 'heatmap', visible: true, params: { bubbles: true, bubbleMin: 10 } },
    { id: 'bigprints', visible: true, params: { min: 50, sweeps: true } }] });
  globalThis.window.HBFlowMath = require('../../homebase/static/charts/flowmath.js');
  const path = require.resolve('../../homebase/static/charts/flowlayer.js');
  delete require.cache[path];
  require(path);
  r.cell.bars[2].bub = [[Math.floor((T0 + 2 * BAR) / 1000) + 10, 80, 25, 1], [Math.floor((T0 + 2 * BAR) / 1000) + 11, 81, 5, -1]];
  r.cell.bars[2].sw = [[T0 + 2 * BAR + 500, 80, 82, 60, 1], [T0 + 2 * BAR + 900, 80, 79, 20, -1]];
  const o = globalThis.window.HBFlowLayer.overlay(r.cell);
  const count = (n) => r.ctx.log.filter((c) => c[0] === n).length;
  o.bub.draw(r.target);
  assert.equal(count('arc'), 1);                                    // 25 >= 10 drawn, 5 is below the minimum
  o.swp.draw(r.target);
  assert.equal(count('lineTo') >= 1, true);                         // one sweep of >= 50 contracts, with its chevron
  assert.equal(r.ctx.log.filter((c) => c[0] === 'closePath').length, 1);
  r.cell.cfg.indicators.forEach((x) => { x.params.bubbles = false; x.params.sweeps = false; });
  r.ctx.log.length = 0;
  o.bub.draw(r.target); o.swp.draw(r.target);
  assert.equal(r.ctx.log.length, 0);
  o.destroy();
  assert.equal(r.calls.detach, 2);
});

test.after(() => { delete globalThis.window; });
