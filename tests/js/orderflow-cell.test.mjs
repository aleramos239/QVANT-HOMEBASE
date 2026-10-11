import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The order-flow additions to cell.js, driven through Cell.prototype on a bare object (as cell-point.test.mjs does):
   the book series computed from HBBookStore ("bk:" keys), the markers of a study drawn as markers (ddiv), the
   Big-prints marker size, and the naked prior POC. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/flowdefs.js');
require('../../homebase/static/charts/flowmath.js');
require('../../homebase/static/charts/bookstore.js');
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
const C = globalThis.HBCatalog, S = globalThis.HBBookStore;

const T0 = 1_790_000_000_000;
const row = (i, imb10, b10, a10, micro) => [T0 + i * 1000, b10, a10, 0, 0, imb10, micro, 1];
beforeEach(() => S.clear());

const stub = (more = {}) => Object.assign(Object.create(Cell.prototype), {
  P: { up: '#0f0', down: '#f00', upA: 'upA', downA: 'downA' }, shown: { root: 'NQ', spec: 'time:60' },
  cfg: { root: 'NQ', spec: 'time:60', indicators: [] }, bars: [], ...more });
const line = (id, part = 'main') => ({ gen: C.TA_BY_ID[id].lines.find((l) => l.part === part), src: C.serverKey({ id, params: C.clampParams(id, {}) }) });

test('a book series is the mean of the samples inside the bar, written into bar.sv for the legend', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 60000, samples: [row(0, 0.2, 10, 30, 100), row(1, 0.4, 20, 30, 102), row(61, 0.9, 0, 0, 0)], episodes: [] });
  const c = stub(), b = { tt: 7, ms: T0, sv: {} };
  const l = line('bkimb');
  assert.equal(l.src, 'bk:imb10');
  const p = c.point(l, b);
  assert.equal(p.time, 7);
  assert.ok(Math.abs(p.value - 0.3) < 1e-9);                     // the sample of the next minute is not in this bar
  assert.ok(Math.abs(b.sv['bk:imb10'] - 0.3) < 1e-9);            // what the legend and the crosshair read
  assert.equal(p.color, 'upA');                                  // a histogram coloured by sign
});

test('the depth pane has a bid and an ask line from one value object', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 60000, samples: [row(0, 0, 10, 30, 100), row(1, 0, 20, 50, 100)], episodes: [] });
  const c = stub(), b = { tt: 1, ms: T0, sv: {} };
  assert.equal(c.point(line('bkdepth', 'b10'), b).value, 15);
  assert.equal(c.point(line('bkdepth', 'a10'), b).value, 40);
  assert.deepEqual(b.sv['bk:depth'], { b10: 15, a10: 40 });
});

test('a bar the store holds nothing for is a gap, not a zero; a missing store or shown root is a gap too', () => {
  const c = stub(), b = { tt: 1, ms: T0, sv: {} };
  assert.deepEqual(c.point(line('bkimb'), b), { time: 1 });
  assert.deepEqual(stub({ shown: null }).point(line('bkimb'), { tt: 1, ms: T0, sv: {} }), { time: 1 });
  assert.deepEqual(c.point(line('bkimb'), { tt: 1, ms: T0 }), { time: 1 });     // no sv at all
});

test('a tick chart ends a bar where the next one starts, the last one now', () => {
  const c = stub({ cfg: { root: 'NQ', spec: 'tick:500', indicators: [] }, shown: { root: 'NQ', spec: 'tick:500' },
    bars: [{ ms: T0 }, { ms: T0 + 5000 }, { ms: T0 + 9000 }] });
  assert.equal(c.bookEnd(c.bars[0]), T0 + 5000);
  assert.equal(c.bookEnd(c.bars[1]), T0 + 9000);
  assert.ok(Math.abs(c.bookEnd(c.bars[2]) - Date.now()) < 1000);
});

test('Bar Replay: a bar never ends past the replay cursor, so the book series holds no sample from after it', () => {
  S.applyHistory('NQ', { t0: T0, t1: T0 + 120000, samples: [row(0, 0.2, 10, 30, 100), row(30, 0.4, 20, 30, 102), row(45, 0.9, 0, 0, 0)], episodes: [] });
  const c = stub({ replay: { cursorMs: T0 + 40000 } }), b = { tt: 7, ms: T0, sv: {} };
  assert.equal(c.bookEnd(b), T0 + 40000);                         // the bar runs to T0 + 60 s, the cursor is at 40 s
  assert.ok(Math.abs(c.point(line('bkimb'), b).value - 0.3) < 1e-9);   // the sample at 45 s is not in it
  assert.equal(stub({ replay: { cursorMs: T0 + 90000 } }).bookEnd(b), T0 + 60000);   // a cursor beyond the bar changes nothing
  assert.equal(stub({ replay: { cursorMs: null } }).bookEnd(b), T0 + 60000);          // an unknown cursor: not capped
  const t = stub({ cfg: { root: 'NQ', spec: 'tick:500', indicators: [] }, shown: { root: 'NQ', spec: 'tick:500' },
    bars: [{ ms: T0 }, { ms: T0 + 5000 }], replay: { cursorMs: T0 + 7000 } });
  assert.equal(t.bookEnd(t.bars[1]), T0 + 7000);                  // the last tick bar: the cursor, not now
});

test('a "fixed" histogram keeps its own colour (tape speed), the others take it from the sign', () => {
  const c = stub(), b = { tt: 1, sv: { 'tspeed:200': { rate: 12, burst: 30, hot: null } } };
  const src = 'tspeed:200';
  assert.deepEqual(c.point({ gen: C.TA_BY_ID.tspeed.lines.find((l) => l.part === 'rate'), src }, b), { time: 1, value: 12 });
  assert.deepEqual(c.point({ gen: C.TA_BY_ID.tspeed.lines.find((l) => l.part === 'hot'), src }, b), { time: 1 });
  assert.deepEqual(c.point({ gen: C.TA_BY_ID.tspeed.lines.find((l) => l.part === 'burst'), src }, b), { time: 1, value: 30 });
});

test('delta divergence: a marker on the swing bar, `ago` real bars before the confirming one, blanks not counted', () => {
  const bars = [0, 1, 2, 3, 4, 5].map((i) => ({ tt: 100 + i, ms: i, sv: {} }));
  bars[4].blank = true;                            // a known hole between the swing and the confirming bar
  bars[5].sv['ddiv:2'] = { dir: -1, ago: 2, px: 101 };
  const inst = { uid: 'u', id: 'ddiv', params: { length: 2 }, visible: true };
  const c = stub({ bars, cfg: { root: 'NQ', spec: 'time:60', indicators: [inst] } });
  assert.deepEqual(c.studyMarks(), [{ time: 102, position: 'aboveBar', color: '#f00', shape: 'arrowDown', text: 'Δ', size: 1 }]);
  inst.visible = false;
  assert.deepEqual(c.studyMarks(), []);
  bars[5].sv['ddiv:2'] = { dir: 1, ago: 2, px: 99 };
  inst.visible = true;
  assert.deepEqual(c.studyMarks().map((m) => [m.position, m.shape, m.color]), [['belowBar', 'arrowUp', '#0f0']]);
});

test('delta divergence: a swing left of the first loaded bar gets no marker (never one on bar 0)', () => {
  const bars = [0, 1, 2, 3].map((i) => ({ tt: 100 + i, ms: i, sv: {} }));
  bars[1].sv['ddiv:5'] = { dir: -1, ago: 5, px: 101 };           // the swing was 5 bars back: before bar 0
  bars[3].sv['ddiv:5'] = { dir: 1, ago: 3, px: 99 };             // this one is exactly bar 0
  const inst = { uid: 'u', id: 'ddiv', params: { length: 5 }, visible: true };
  const c = stub({ bars, cfg: { root: 'NQ', spec: 'time:60', indicators: [inst] } });
  assert.deepEqual(c.studyMarks().map((m) => [m.time, m.position]), [[100, 'belowBar']]);
});

test('the prior POC is naked until the session trades back through it', () => {
  const bars = [{ s: 'A', l: 90, h: 100 }, { s: 'B', l: 101, h: 105 }, { s: 'B', l: 104, h: 108 }];
  const c = stub({ bars, profile: { poc: 100, prev: { poc: 100, rows: [[100, 5]] } } });
  assert.equal(c.priorNaked(), true);              // session B (the last) has not touched 100; session A's bar is not counted
  bars.push({ s: 'B', l: 99, h: 103 });
  assert.equal(c.priorNaked(), false);
  assert.equal(stub({ bars, profile: { poc: 1 } }).priorNaked(), false);          // no prior session
});

test('book keys never go to the server; the server studies do', () => {
  const list = [{ id: 'bkimb', params: { levels: '5' } }, { id: 'bkdepth', params: {} }, { id: 'bkmicro', params: {} },
    { id: 'tspeed', params: { length: 100 } }, { id: 'ddiv', params: { length: 3 } }, { id: 'rsi', params: { length: 14 } }];
  assert.deepEqual(C.serverKeys(list), ['tspeed:100', 'ddiv:3', 'rsi:14']);
  assert.equal(C.serverKey(list[0]), 'bk:imb5');
});

test('a page that does not load the book store (the Backtest tab) draws the book series as gaps and never throws', () => {
  const saved = globalThis.HBBookStore;
  try {
    delete globalThis.HBBookStore;
    const b = { tt: 1, ms: T0, sv: {} };
    assert.deepEqual(stub().point(line('bkimb'), b), { time: 1 });
    assert.deepEqual(b.sv, {});
  } finally { globalThis.HBBookStore = saved; }
});

/* A live `update` message through the real onUpdate: a recorder stands in for the chart, the series and the markers plugin. */
function liveCell(indicators) {
  const rec = { markers: [] };
  globalThis.HBDrawings = { placeMarkers: (bars, extra) => extra };
  const c = stub({
    cfg: { root: 'NQ', spec: 'time:60', indicators }, chart: {}, inflight: [], windowAt: null, devel: false, replay: null, dc: null,
    R: { timezone: 'exchange' }, lines: [], ov: [], alt: null, hover: null, extMarkers: {}, realT: new Map(), tick: 0.25,
    bars: [{ tt: 1_790_000_000, ms: 1_790_000_000_000, o: 1, h: 2, l: 0, c: 1, v: 1, d: 0, sv: {} }],
    candles: { update() {} }, markers: { setMarkers: (m) => rec.markers.push(m) },
    syncLastColor() {}, drawLevels() {}, syncFootprint() {}, syncProfile() {}, legend() {},
  });
  return { c, rec };
}
const closedBar = (ms, over = {}) => ({ ms, t: ms / 1000, o: 1, h: 2, l: 0, c: 1, v: 1, d: 0, ...over });

test('a live update carrying a delta-divergence value redraws the markers; one without it (and no big print) does not', () => {
  const inst = { uid: 'u', id: 'ddiv', params: { length: 5 }, visible: true };
  const { c, rec } = liveCell([inst]);
  c.bars.length = 0;
  for (let i = 0; i < 8; i++) c.bars.push({ tt: 100 + i, ms: i * 60000, o: 1, h: 2, l: 0, c: 1, v: 1, d: 0, sv: {} });
  const k = 'ddiv:5';
  c.onUpdate({ closed: [closedBar(8 * 60000)], live: null, studies: { [k]: { closed: [{ dir: 1, ago: 5, px: 99 }], live: null } } });
  assert.equal(rec.markers.length, 1);
  assert.deepEqual(rec.markers[0].map((m) => [m.time, m.position, m.shape, m.color]), [[c.bars[3].tt, 'belowBar', 'arrowUp', '#0f0']]);
  c.onUpdate({ closed: [closedBar(9 * 60000)], live: null, studies: { [k]: { closed: [null], live: null } } });
  assert.equal(rec.markers.length, 1);             // no ddiv value, no big print: the markers are left alone
  inst.visible = false;
  c.onUpdate({ closed: [closedBar(10 * 60000)], live: null, studies: { [k]: { closed: [{ dir: -1, ago: 5, px: 99 }], live: null } } });
  assert.equal(rec.markers.length, 1);             // a hidden study draws nothing
});

test('a big print still redraws the markers on an update (the existing trigger is kept)', () => {
  const { c, rec } = liveCell([{ uid: 'u', id: 'bigprints', params: { min: 1 }, visible: true }]);
  c.onUpdate({ closed: [closedBar(60000, { big: [[0, 0, 5, 1]] })], live: null, studies: {} });
  assert.equal(rec.markers.length, 1);
  assert.equal(rec.markers[0].length, 1);
});
