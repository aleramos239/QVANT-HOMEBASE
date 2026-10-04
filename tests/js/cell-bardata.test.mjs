import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* A chart asks for its bars' footprint and big prints only when something draws them (cell.js need()), and
   loads them when that something is switched on later. cell.js is browser-only: loaded under minimal stubs
   (as cell-destroy.test.mjs does), with the real catalog, and driven through Cell.prototype on a bare object
   -- the seam is what it sends and when it resubscribes, not the chart. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;

const ind = (id, more = {}) => ({ uid: id, id, params: {}, ...more });
const BAR = { t: 60, ms: 60000, s: '2026-09-24', o: 1, h: 1, l: 1, c: 1, v: 1, d: 1, n: 1 };
const HIST = { type: 'history', id: 'c1', root: 'NQ', spec: 'time:60', tick_size: 0.25, bars: [{ ...BAR }], studies: {}, sessions: [] };

function cell(indicators) {
  const c = Object.create(Cell.prototype);
  return Object.assign(c, { id: 'c1', cfg: { root: 'NQ', spec: 'time:60', indicators }, sent: [], drawn: 0, built: 0,
    host: { send: (m) => { c.sent.push(m); return true; }, changed() {}, onLoaded() {} },
    inflight: [], has: { fp: false, big: false }, wantFp: false, replay: null, chart: null, shown: null, keys: new Set(),
    bars: [], realT: new Map(), loadWaiters: [], noteOn: false, capped: false, reaching: null, R: { timezone: 'exchange' },
    back: { reset() {}, want: (r, ms) => ({ before: ms }), sent() {} },
    title() {}, message() {}, viewNow: () => null, restyle() { c.drawn++; }, build() { c.built++; c.chart = {}; } });
}
/* The chart as the server answered its first sub. */
function loaded(indicators) {
  const c = cell(indicators);
  c.subscribe();
  c.onHistory({ ...HIST });
  c.sent.length = 0;
  return c;
}
const subs = (c) => c.sent.filter((m) => m.op === 'sub').map((m) => ({ fp: m.fp, big: m.big }));

test('a chart asks for the footprint and the big prints only with an indicator that draws them', () => {
  const ask = (list) => { const c = cell(list); c.subscribe(); return subs(c); };
  assert.deepEqual(ask([ind('volume'), ind('vwap'), ind('levels')]), [{ fp: false, big: false }]);
  assert.deepEqual(ask([ind('volume'), ind('footprint')]), [{ fp: true, big: false }]);
  assert.deepEqual(ask([ind('bigprints')]), [{ fp: false, big: true }]);
  assert.deepEqual(ask([ind('footprint'), ind('bigprints')]), [{ fp: true, big: true }]);
  // a hidden instance still counts: the legend's eye shows it again at once, with no reload (setVisible)
  assert.deepEqual(ask([ind('footprint', { visible: false }), ind('bigprints', { visible: false })]), [{ fp: true, big: true }]);
});

test('Footprint switched on later: the chart reloads with the data, it is never drawn from bars that lack it', () => {
  const c = loaded([ind('volume')]);
  assert.deepEqual(c.has, { fp: false, big: false });
  c.update({ indicators: [ind('volume'), ind('footprint')] });
  assert.deepEqual(subs(c), [{ fp: true, big: false }]);
  assert.equal(c.drawn, 0);                        // not restyle(): the bars on screen have no footprint
  c.onHistory({ ...HIST });
  assert.deepEqual(c.has, { fp: true, big: false });
  c.update({ indicators: [ind('volume'), ind('footprint'), ind('bigprints')] });   // and Big prints after it
  assert.deepEqual(subs(c), [{ fp: true, big: false }, { fp: true, big: true }]);
  assert.equal(c.drawn, 0);
  c.onHistory({ ...HIST });
  assert.deepEqual(c.has, { fp: true, big: true });
});

test('with the data already on the chart an indicator change is still drawn in place, with no reload', () => {
  const c = loaded([ind('volume'), ind('footprint'), ind('bigprints')]);
  c.update({ indicators: [ind('volume')] });                                        // both removed ...
  c.update({ indicators: [ind('volume'), ind('footprint'), ind('bigprints')] });    // ... and put back
  assert.deepEqual(c.sent, []);
  assert.equal(c.drawn, 2);
  const plain = loaded([ind('volume')]);
  plain.update({ indicators: [ind('volume'), ind('delta')] });                      // needs neither
  assert.deepEqual(plain.sent, []);
  assert.equal(plain.drawn, 1);
});

test('scroll-back asks for what the history on screen carries', () => {
  const c = loaded([ind('volume')]);
  c.askOlder({ from: 0, to: 1 });
  assert.deepEqual(c.sent, [{ op: 'older', id: 'c1', before: 60000, fp: false, big: false }]);
  const f = loaded([ind('footprint'), ind('bigprints')]);
  f.askOlder({ from: 0, to: 1 });
  assert.deepEqual(f.sent, [{ op: 'older', id: 'c1', before: 60000, fp: true, big: true }]);
});

test('the Level 2 ladder asks a chart for its footprint once, and the chart keeps asking for it afterwards', () => {
  const c = loaded([ind('volume')]);
  c.needFootprint();
  c.needFootprint();                               // the ladder calls at every paint
  assert.deepEqual(subs(c), [{ fp: true, big: false }]);
  c.onHistory({ ...HIST });
  assert.equal(c.has.fp, true);
  c.subscribe(true);                               // a later reload (a reset, a reconnect) still carries it
  assert.deepEqual(subs(c), [{ fp: true, big: false }, { fp: true, big: false }]);
  const f = loaded([ind('footprint')]);            // already on the chart: nothing to load
  f.needFootprint();
  assert.deepEqual(f.sent, []);
  const p = cell([ind('volume'), ind('footprint')]);
  p.subscribe();                                   // the sub in flight already asks for it
  p.needFootprint();
  assert.equal(p.sent.length, 1);
});

test('a refused footprint reload is not sent again at the next paint', () => {
  const c = loaded([ind('volume')]);
  c.needFootprint();
  c.onError('boom');
  c.needFootprint();
  assert.equal(subs(c).length, 1);
});

test('in a replay the ladder never sends a sub (it would end the replay); the replay history carries both', () => {
  const c = loaded([ind('volume')]);
  c.replay = { date: '2026-09-24' };
  c.needFootprint();
  assert.deepEqual(c.sent, []);
  c.onHistory({ ...HIST, replay: true });          // no sub of ours in flight: the replay's own history
  assert.deepEqual(c.has, { fp: true, big: true });
  c.replay = null;                                 // a refused or finished replay: the ladder asks now
  c.has = { fp: false, big: false };
  c.needFootprint();
  assert.deepEqual(subs(c), [{ fp: true, big: false }]);
});
