import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Known holes on the chart (cell.js + primitives.js). The server sends each session's holes from the tick
   job's coverage report as [startMs, endMs, kind] -- lost (grey), filling (amber), thin (a light tint over
   bars built from an incomplete tape). A lost / filling hole gets an empty slot per bar it swallowed, so it
   is as wide on the axis as the time it covers. Both files are browser-only: loaded under minimal stubs,
   driven through Cell.prototype on a bare object and through the layer with a recording canvas. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
require('../../homebase/static/charts/primitives.js');
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/drawings.js');
require('../../homebase/static/charts/scrollback.js');
require('../../homebase/static/charts/cell.js');
const { Cell, holesOf, withBlanks, bandsOf, MIN_GAP_S } = globalThis.HBCell;
const { Gaps } = globalThis.HBLayers;

const MIN = 60000, T0 = Date.UTC(2026, 8, 25, 13, 30);          // 09:30 ET: a bar's ms; its t is ET wall seconds
const bar = (k, c = 100) => ({ ms: T0 + k * MIN, t: (T0 - 4 * 3600000) / 1000 + k * 60, s: '2026-09-25',
  o: c, h: c + 1, l: c - 1, c, v: 5, d: 1, n: 2 });
const mins = (list) => list.map((k) => bar(k, 100 + k));

test('holesOf: every session\'s holes as one list in time order; a hole with no length is left out', () => {
  const sessions = [{ date: 'b', holes: [[50, 60, 'thin'], [70, 70, 'lost']] }, { date: 'a' }, { date: 'c', holes: [[10, 20, 'lost']] }];
  assert.deepEqual(holesOf(sessions), [[10, 20, 'lost'], [50, 60, 'thin']]);
  assert.deepEqual(holesOf(undefined), []);
});

test('a lost hole gets one empty slot per bar it swallowed: as wide as the time it covers', () => {
  const bars = mins([0, 1, 2, 10, 11]);                           // nothing 09:33-09:39
  const hole = [T0 + 3 * MIN, T0 + 10 * MIN, 'lost'];
  const out = withBlanks(bars, [hole], MIN);
  assert.deepEqual(out.map((b) => (b.ms - T0) / MIN), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
  assert.deepEqual(out.map((b) => b.blank || ''), ['', '', '', 'lost', 'lost', 'lost', 'lost', 'lost', 'lost', 'lost', '', '']);
  const slot = out[3];
  assert.deepEqual([slot.o, slot.h, slot.l, slot.c, slot.v, slot.d], [102, 102, 102, 102, 0, 0]);   // the last close, no volume
  assert.equal(slot.t, bars[2].t + 60);                           // its axis time follows on from the bar before
  assert.equal(slot.s, '2026-09-25');
  assert.deepEqual(slot.sv, {});
  assert.equal(out[2], bars[2]);                                  // the real bars are the same objects
});

test('time without bars that is NOT a known hole stays compressed (a quiet stretch, the 17:00 hour, a weekend)', () => {
  const bars = mins([0, 1, 30, 31]);
  assert.equal(withBlanks(bars, [], MIN), bars);                  // nothing known: the very same array
  assert.equal(withBlanks(bars, [[T0 + 40 * MIN, T0 + 50 * MIN, 'lost']], MIN), bars);     // a hole elsewhere
  const part = withBlanks(bars, [[T0 + 10 * MIN, T0 + 13 * MIN, 'filling']], MIN);         // only the hole's own minutes
  assert.deepEqual(part.map((b) => (b.ms - T0) / MIN), [0, 1, 10, 11, 12, 30, 31]);
  assert.deepEqual(part.filter((b) => b.blank).map((b) => b.blank), ['filling', 'filling', 'filling']);
});

test('a thin hole adds no slot (its bars are there); a 5-minute chart gets a slot per 5 minutes; the slots are capped', () => {
  const bars = mins([0, 1, 2, 10, 11]);
  assert.equal(withBlanks(bars, [[T0 + 3 * MIN, T0 + 10 * MIN, 'thin']], MIN), bars);
  const five = [bar(0), bar(5), bar(30)];
  const out = withBlanks(five, [[T0 + 10 * MIN, T0 + 30 * MIN, 'lost']], 5 * MIN);
  assert.deepEqual(out.map((b) => (b.ms - T0) / MIN), [0, 5, 10, 15, 20, 25, 30]);
  assert.equal(withBlanks(bars, [[T0 + 3 * MIN, T0 + 10 * MIN, 'lost']], MIN, 4).filter((b) => b.blank).length, 4);
  assert.equal(withBlanks(bars, [[T0 + 3 * MIN, T0 + 10 * MIN, 'lost']], 0), bars);         // not a time chart: no slots
});

test('two holes between the same two bars, and a hole that reaches past the next bar', () => {
  const bars = mins([0, 20]);
  const out = withBlanks(bars, [[T0 + 2 * MIN, T0 + 4 * MIN, 'lost'], [T0 + 10 * MIN, T0 + 12 * MIN, 'filling']], MIN);
  assert.deepEqual(out.map((b) => [(b.ms - T0) / MIN, b.blank || '']), [[0, ''], [2, 'lost'], [3, 'lost'], [10, 'filling'], [11, 'filling'], [20, '']]);
  const over = withBlanks(mins([0, 5, 6]), [[T0 + 2 * MIN, T0 + 9 * MIN, 'lost']], MIN);    // the chart has bars inside it
  assert.deepEqual(over.map((b) => (b.ms - T0) / MIN), [0, 2, 3, 4, 5, 6]);
});

test('bandsOf: a run of empty slots is one band of its kind; the bars inside a thin hole are one light band', () => {
  const bars = withBlanks(mins([0, 1, 2, 10, 11, 12, 13]), [[T0 + 3 * MIN, T0 + 10 * MIN, 'lost']], MIN);
  const holes = [[T0 + 3 * MIN, T0 + 10 * MIN, 'lost'], [T0 + 11 * MIN, T0 + 13 * MIN, 'thin']];
  assert.deepEqual(bandsOf(bars, holes), [[3, 9, 'lost'], [11, 12, 'thin']]);
  assert.deepEqual(bandsOf(mins([0, 1]), []), []);
});

/* ---- the cell ---- */
const HIST = { type: 'history', id: 'c1', root: 'NQ', spec: 'time:60', tick_size: 0.25, studies: { vwap: [] } };
function cell(spec = 'time:60') {
  const c = Object.create(Cell.prototype);
  return Object.assign(c, { id: 'c1', cfg: { root: 'NQ', spec, indicators: [] }, sent: [], set: null,
    host: { send: (m) => { c.sent.push(m); return true; }, changed() {}, onLoaded() {} },
    inflight: [], has: { fp: false, big: false }, replay: null, chart: null, shown: null, keys: new Set(), ov: [],
    bars: [], realT: new Map(), loadWaiters: [], noteOn: false, capped: false, reaching: null, hover: null, lines: [],
    R: { timezone: 'exchange', prevClose: false, prevDay: 'hidden', lastLine: true, lastLineColor: null }, P: {}, sessions: [], refLines: {},
    back: { reset() {}, done: false, take: () => true },
    gaps: { set(idx, bands) { c.set = { idx, bands }; } }, start: { set() {} }, lg: { badge: {} },
    title() {}, message() {}, viewNow: () => null, build() { c.chart = c.fakeChart; c.drawGaps(); },
    fakeChart: { timeScale: () => ({ getVisibleLogicalRange: () => ({ from: 0, to: 5 }), setVisibleLogicalRange(r) { c.view = r; } }) },
    candles: { setData(d) { c.candleSet = d; } }, drawMarkers() {}, syncFootprint() {}, syncEth() {}, legend() {} });
}

test('a history with a lost hole: the chart holds the empty slots, draws nothing in them and shades one band', () => {
  const c = cell(), bars = mins([0, 1, 2, 10, 11]);
  c.inflight.push({ cfg: {}, view: null, has: { fp: false, big: false } });
  c.onHistory({ ...HIST, bars, studies: { vwap: [1, 2, 3, 4, 5] },
    sessions: [{ date: '2026-09-25', gaps: [], holes: [[T0 + 3 * MIN, T0 + 10 * MIN, 'lost']] }] });
  assert.equal(c.bars.length, 12);
  assert.deepEqual(c.bars.map((b) => b.sv.vwap), [1, 2, 3, ...Array(7).fill(undefined), 4, 5]);   // each real bar keeps its own study value
  assert.deepEqual(c.set, { idx: [], bands: [[3, 9, 'lost']] });
  assert.deepEqual(c.candle(c.bars[4], c.bars[3]), { time: c.bars[4].tt });           // whitespace: no candle
  assert.deepEqual(c.point({ src: '__vol' }, c.bars[4]), { time: c.bars[4].tt });     // nor a volume bar, nor a study point
  assert.deepEqual(c.point({ src: 'vwap', part: null }, c.bars[4]), { time: c.bars[4].tt });
  assert.equal(c.candle(c.bars[10], c.bars[9]).open, 110);                            // the bar after the hole: itself
  assert.ok(c.bars.every((b, i) => i === 0 || b.tt > c.bars[i - 1].tt));              // one rising axis
});

test('a tick chart has no time axis to widen: the hole is one "no data" mark between the two bars around it', () => {
  const c = cell('tick:500'), bars = mins([0, 1, 2, 10, 11]);
  c.inflight.push({ cfg: {}, view: null, has: { fp: false, big: false } });
  c.onHistory({ ...HIST, spec: 'tick:500', bars, studies: {},
    sessions: [{ date: '2026-09-25', gaps: [], holes: [[T0 + 3 * MIN, T0 + 10 * MIN, 'lost'], [T0 + 10 * MIN, T0 + 12 * MIN, 'thin']] }] });
  assert.equal(c.bars.length, 5);
  assert.deepEqual(c.set, { idx: [2], bands: [[3, 4, 'thin']] });
});

test('a recording gap shorter than 5 seconds is not marked; a longer one is, unless a known hole follows it', () => {
  assert.equal(MIN_GAP_S, 5);
  const c = cell(), s0 = bar(0).t;
  c.shown = { root: 'NQ', spec: 'time:60' };
  c.bars = mins([0, 1, 2, 3, 4]).map((b, i) => ({ ...b, tt: i }));
  c.sessions = [{ date: '2026-09-25', gaps: [[s0 + 62, s0 + 65], [s0 + 130, s0 + 190]] }];   // the 09:10 swap's 3 s; a 60 s outage
  c.drawGaps();
  assert.deepEqual(c.set.idx, [2]);
  c.bars[3].blank = 'lost';                                       // the outage is a known hole: its own band says so
  c.drawGaps();
  assert.deepEqual(c.set, { idx: [], bands: [[3, 3, 'lost']] });
});

test('older sessions scrolled in: their holes get their slots, the view shifts by every slot added in front', () => {
  const c = cell();
  c.inflight.push({ cfg: {}, view: null, has: { fp: false, big: false } });
  c.onHistory({ ...HIST, bars: mins([100, 101, 102, 110]), studies: {},
    sessions: [{ date: '2026-09-25', gaps: [], holes: [[T0 + 103 * MIN, T0 + 110 * MIN, 'filling']] }] });
  assert.equal(c.bars.length, 11);
  c.hover = 4;
  c.onOlder({ before: c.bars[0].ms, bars: mins([0, 1, 50]).map((b) => ({ ...b, s: '2026-09-24' })), studies: {}, repair: {},
    sessions: [{ date: '2026-09-24', gaps: [], holes: [[T0 + 2 * MIN, T0 + 5 * MIN, 'lost'], [T0 + 98 * MIN, T0 + 100 * MIN, 'lost']] }] });
  // 3 older bars + 3 slots inside the older session + 2 at the join (before the chart's own first bar)
  assert.deepEqual(c.bars.map((b) => [(b.ms - T0) / MIN, b.blank || '']).slice(0, 9),
    [[0, ''], [1, ''], [2, 'lost'], [3, 'lost'], [4, 'lost'], [50, ''], [98, 'lost'], [99, 'lost'], [100, '']]);
  assert.equal(c.bars.length, 19);
  assert.deepEqual(c.view, { from: 8, to: 13 });
  assert.equal(c.hover, 12);
  assert.deepEqual(c.set.bands, [[2, 4, 'lost'], [6, 7, 'lost'], [11, 17, 'filling']]);
  assert.equal(c.candleSet.length, 19);
});

test('the studies repaired across the join land on the chart\'s own first BARS, never on an empty slot', () => {
  const c = cell();
  c.inflight.push({ cfg: {}, view: null, has: { fp: false, big: false } });
  c.onHistory({ ...HIST, bars: mins([100, 105, 106]), studies: { vwap: [1, 2, 3] },
    sessions: [{ date: '2026-09-25', gaps: [], holes: [[T0 + 101 * MIN, T0 + 105 * MIN, 'lost']] }] });
  assert.deepEqual(c.bars.map((b) => b.blank || b.sv.vwap), [1, 'lost', 'lost', 'lost', 'lost', 2, 3]);
  c.onOlder({ before: c.bars[0].ms, bars: mins([98, 99]), studies: { vwap: [7, 8] }, repair: { vwap: [9, 10] }, sessions: [] });
  assert.deepEqual(c.bars.map((b) => b.blank || b.sv.vwap), [7, 8, 9, 'lost', 'lost', 'lost', 'lost', 10, 3]);
  assert.deepEqual(c.view, { from: 2, to: 7 });
});

test('today\'s thin hours come with the status: a light band over the bars they hold, redrawn only when they change', () => {
  const c = cell();
  c.inflight.push({ cfg: {}, view: null, has: { fp: false, big: false } });
  c.onHistory({ ...HIST, bars: mins([0, 1, 2, 3, 4, 5]), studies: {}, sessions: [{ date: '2026-09-25', gaps: [] }] });
  let draws = 0;
  const set = c.gaps.set;
  c.gaps.set = (idx, bands) => { draws++; set(idx, bands); };
  const nq = [[T0 + 2 * MIN, T0 + 4 * MIN, 'thin'], [T0 + 9 * MIN, T0 + 10 * MIN, 'filling']];
  c.setToday({ NQ: nq, ES: [[T0, T0 + MIN, 'thin']] });
  assert.deepEqual(c.set.bands, [[2, 3, 'thin']]);     // its own root's; an hour with no bar at all has nothing to tint
  c.setToday({ NQ: nq.map((h) => [...h]) });           // the same reading, 2 s later
  assert.equal(draws, 1);
  c.setToday(undefined);                               // the socket dropped, or the reading is older than the tape: unknown
  assert.deepEqual([draws, c.set.bands], [2, []]);
  c.setToday(null);
  assert.equal(draws, 2);
});

test('today\'s reading before the first history is kept for the build, not drawn on a chart that is not there', () => {
  const c = cell();
  c.setToday({ NQ: [[T0 + MIN, T0 + 3 * MIN, 'thin']] });
  assert.equal(c.set, null);
  c.inflight.push({ cfg: {}, view: null, has: { fp: false, big: false } });
  c.onHistory({ ...HIST, bars: mins([0, 1, 2, 3]), studies: {},
    sessions: [{ date: '2026-09-24', gaps: [], holes: [[T0 - 60 * MIN, T0 - 50 * MIN, 'thin']] }] });
  assert.deepEqual(c.set.bands, [[1, 2, 'thin']]);
});

/* ---- the layer ---- */
function drawn(layer, width = 400) {
  const ops = [];
  const ctx = { set fillStyle(v) { this._f = v; }, get fillStyle() { return this._f; }, font: '', textAlign: '',
    fillRect(x, y, w, h) { ops.push(['rect', this._f, x, w]); }, fillText(t, x) { ops.push(['text', t, x]); },
    measureText: (t) => ({ width: t.length * 6 }) };
  layer.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width, height: 300 } }) });
  return ops;
}
const P = { gap: 'GREY', gapFill: 'AMBER', gapThin: 'TINT', text2: 'TEXT' };
const chart = (spacing) => ({ timeScale: () => ({ logicalToCoordinate: (i) => i * spacing }) });

test('the layer: a band is as wide as its slots; grey lost, amber filling, a light tint thin; the mark stays one bar wide', () => {
  const g = new Gaps(P);
  g.attached({ chart: chart(10), series: {}, requestUpdate() {} });
  g.set([1], [[3, 9, 'lost'], [12, 20, 'filling'], [22, 23, 'thin']]);
  const ops = drawn(g);
  assert.deepEqual(ops.filter((o) => o[0] === 'rect'), [
    ['rect', 'GREY', 25, 70],          // slots 3..9 at 10 px: from half a bar before the first to half after the last
    ['rect', 'AMBER', 115, 90], ['rect', 'TINT', 215, 20],
    ['rect', 'GREY', 10, 10]]);        // the recording-gap mark between bars 1 and 2, as before
  assert.deepEqual(ops.filter((o) => o[0] === 'text'), [['text', 'no data', 60], ['text', 'filling', 160], ['text', 'no data', 15]]);
});

test('the layer: a band too narrow for its words has none; one off the screen is not drawn; no bands, no work', () => {
  const g = new Gaps(P);
  g.attached({ chart: chart(4), series: {}, requestUpdate() {} });
  g.set([], [[3, 9, 'filling'], [200, 300, 'lost']]);
  assert.deepEqual(drawn(g), [['rect', 'AMBER', 10, 28]]);
  g.set([], []);
  assert.deepEqual(drawn(g), []);
  assert.deepEqual(new Gaps(P).idx, []);
});
