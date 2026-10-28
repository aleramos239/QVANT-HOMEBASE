/* HBStatus.of: why an indicator shows nothing, in a few plain words. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const DIR = new URL('../../homebase/static/charts/', import.meta.url).pathname;
const S = require(DIR + 'indstatus.js');
const M = require(DIR + 'flowmath.js');
const E = require(DIR + 'bookevents.js');

const bar = (i, extra = {}) => ({ ms: i * 60000, o: 100, h: 101, l: 99, c: 100, v: 10, d: 0, big: [], sw: [], ...extra });
const inst = (id, params = {}, extra = {}) => ({ id, uid: id, params, ...extra });
const facts = (bars, extra = {}) => ({ bars, i0: 0, i1: bars.length - 1, readable: true, M, E, ...extra });

test('footprint: too zoomed out says so and offers the zoom; readable with data says nothing', () => {
  const bars = [bar(0, { fp: [[100, 1, 2]] })];
  assert.deepEqual(S.of(inst('footprint'), facts(bars, { readable: false })), { text: 'Too small to read: zoom in', tone: 'warn', act: 'zoom' });
  assert.equal(S.of(inst('footprint'), facts(bars)), null);
  assert.match(S.of(inst('footprint'), facts([bar(0)])).text, /No trade detail/);
});

test('big prints: counts the ones at or above the minimum in view; none says which setting to lower', () => {
  const bars = [bar(0, { big: [[1, 100, 30, 1], [2, 100, 5, 1]] }), bar(1, { big: [[3, 100, 60, -1]] })];
  assert.deepEqual(S.of(inst('bigprints', { min: 25 }), facts(bars)), { text: '2 marks in view', tone: 'info' });
  const none = S.of(inst('bigprints', { min: 500 }), facts(bars));
  assert.equal(none.tone, 'warn');
  assert.match(none.text, /None in view\. Lower "Minimum size" \(now 500\)/);
  const one = S.of(inst('bigprints', { min: 50 }), facts(bars));
  assert.equal(one.text, '1 mark in view');
});

test('book indicators: no book for the span, or still loading, is said plainly', () => {
  const bars = [bar(0)];
  assert.match(S.of(inst('bkimb'), facts(bars, { book: { rows: 0, covered: false, live: false } })).text, /loading, or none was recorded/);
  assert.match(S.of(inst('absorb', { multiple: 4, minSeconds: 5 }), facts(bars, { book: { rows: 500, covered: false, live: true } })).text, /No Level 2 book was recorded/);
  assert.equal(S.of(inst('bkimb'), facts(bars, { book: { rows: 500, covered: true, live: true } })), null);
  assert.match(S.of(inst('imbalance'), facts(bars, { book: { rows: 500, covered: true, live: false } })).text, /live Level 2 book/);
  assert.equal(S.of(inst('imbalance'), facts(bars, { book: { rows: 500, covered: true, live: true } })), null);
});

test('book events: counted from the episodes in view with the instance settings', () => {
  const bars = [bar(0)];
  const eps = [{ id: 'a', s: 'b', p: 100, t0: 0, t1: 20000, r: 6, pk: 50, tr: 40, ab: 12000, end: 'traded' }];
  const book = { rows: 10, covered: true, live: true };
  assert.equal(S.of(inst('absorb', { multiple: 4, minSeconds: 5 }), facts(bars, { book, episodes: eps })).text, '1 mark in view');
  assert.match(S.of(inst('absorb', { multiple: 10, minSeconds: 5 }), facts(bars, { book, episodes: eps })).text, /None in view/);
});

test('a hidden indicator and an indicator with nothing to say stay quiet', () => {
  assert.equal(S.of(inst('footprint', {}, { visible: false }), facts([bar(0)], { readable: false })), null);
  assert.equal(S.of(inst('rsi', { length: 14 }), facts([bar(0)])), null);
  assert.equal(S.of(inst('rsi'), null), null);
});

test('book indicators: when older history was refused, the note names that, not the setting', () => {
  const bars = [bar(0)];
  const paused = { rows: 400, covered: true, live: true, full: false, refused: { status: 503, detail: 'paused for the 9:30 window' } };
  const a = S.of(inst('bigorders', { multiple: 5, minSeconds: 5 }), facts(bars, { book: paused, episodes: [] }));
  assert.equal(a.tone, 'warn');
  assert.match(a.text, /Older Level 2 is paused for the 9:30 window/);
  assert.doesNotMatch(a.text, /Lower/);
  assert.match(S.of(inst('absorb', { multiple: 4, minSeconds: 5 }), facts(bars, { book: paused, episodes: [] })).text, /paused for the 9:30 window/);
  assert.equal(S.of(inst('heatmap'), facts(bars, { book: paused })), null, 'the heatmap reads the depth history, not the book store');
  // the whole view is covered: the refusal (of some older chunk) changes nothing
  const full = { ...paused, full: true };
  assert.match(S.of(inst('bigorders', { multiple: 5, minSeconds: 5 }), facts(bars, { book: full, episodes: [] })).text, /None in view\. Lower "Multiple"/);
  assert.match(S.of(inst('absorb', {}), facts(bars, { book: { ...paused, refused: { status: 503, detail: 'busy: one window at a time' } }, episodes: [] })).text, /Loading older Level 2/);
  assert.match(S.of(inst('pulled', {}), facts(bars, { book: { ...paused, refused: { status: 0, detail: '' } }, episodes: [] })).text, /could not load/);
});

test('smt: needs NQ or ES on a time chart, otherwise counts the divergences in view', () => {
  const k = 'smt:6:36', i = inst('smt', { window: 6, reference: 36 });
  const bars = [bar(0, { sv: { [k]: { dir: -1, ago: 0 } } }), bar(1, { sv: {} }), bar(2, { sv: { [k]: { dir: 1, ago: 0 } } })];
  assert.match(S.of(i, facts(bars, { root: 'GC' })).text, /no partner/);
  assert.match(S.of(i, facts(bars, { root: 'NQ', time: false })).text, /time chart/);
  assert.deepEqual(S.of(i, facts(bars, { root: 'NQ', time: true })), { text: '2 divergences in view', tone: 'info' });
  assert.deepEqual(S.of(i, facts([bar(0, { sv: {} })], { root: 'ES' })), { text: 'None in view', tone: 'info' });
});

test('fvg: counts the boxes in view', () => {
  const K = 'fvg:0.25:14';
  const bars = Array.from({ length: 6 }, (_, i) => bar(i));
  assert.equal(S.of(inst('fvg', { min: 0.25, length: 14 }), facts(bars)).text, 'No open gap in view');
  for (const i of [2, 3]) bars[i].sv = { [K]: { uh: 102, ul: 100, dh: null, dl: null } };
  assert.equal(S.of(inst('fvg', { min: 0.25, length: 14 }), facts(bars)).text, '1 gap in view');
});

/* 2026-10-21 order-flow apps: a bar loaded before the wire carried their field says so; big trades count like big prints. */
test('order-flow apps: no bar in view carries the field they read -> a plain warning; one bar that does -> nothing to say', () => {
  const old = [bar(0), bar(1)];
  assert.equal(S.of(inst('bigtrades', { min: 25 }), facts(old)).text, 'No order detail for these bars');
  assert.equal(S.of(inst('npoc'), facts(old)).text, 'No trade detail for these bars');
  assert.equal(S.of(inst('mwabs'), facts(old)).text, 'No trade detail for these bars');
  assert.equal(S.of(inst('dstr'), facts(old)).text, 'No delta highs and lows for these bars');
  assert.equal(S.of(inst('npoc'), facts([bar(0), bar(1, { fp: [] })])), null, 'an empty footprint array is a bar that carries it');
  assert.equal(S.of(inst('dstr'), facts([bar(0, { dmax: 0, dmin: 0 })])), null);
  assert.equal(S.of(inst('bigtrades', {}, { visible: false }), facts(old)), null);
  assert.equal(S.of(inst('cstat'), facts(old)), null, 'its strip shows blanks for what a bar lacks');
});

test('big trades: counts the bubbles in view the way the layer draws them; none says which setting to lower', () => {
  const ag = (size, side, t = 1) => [T(t), 100, 100, 100, size, side, 1];
  const T = (t) => 1_790_000_000_000 + t;
  const bars = [bar(0, { ag: [ag(30, 1), ag(10, -1, 2)] }), bar(1, { ag: [ag(60, -1, 3)] })];
  assert.deepEqual(S.of(inst('bigtrades', { min: 25, max: 0, side: 'all', cluster: 'none', thr: 100 }), facts(bars)), { text: '2 marks in view', tone: 'info' });
  assert.equal(S.of(inst('bigtrades', { min: 25, max: 50, side: 'all', cluster: 'none', thr: 100 }), facts(bars)).text, '1 mark in view', 'max drops the 60');
  assert.equal(S.of(inst('bigtrades', { min: 5, max: 0, side: 'sell', cluster: 'none', thr: 100 }), facts(bars)).text, '2 marks in view', 'sellers only');
  assert.equal(S.of(inst('bigtrades', { min: 5, max: 0, side: 'all', cluster: 'none', thr: 100 }), facts(bars)).text, '3 marks in view');
  assert.equal(S.of(inst('bigtrades', { min: 5, max: 0, side: 'all', cluster: 'price', thr: 100 }), facts(bars)).text, '2 marks in view', 'same price in a bar: one bubble a bar');
  const none = S.of(inst('bigtrades', { min: 500, max: 0, side: 'all', cluster: 'none', thr: 100 }), facts(bars));
  assert.equal(none.tone, 'warn');
  assert.match(none.text, /None in view\. Lower "Minimum size" \(now 500\)/);
});

test('footprint: the prints-per-row text needs bars that carry the print counts', () => {
  const rows = [[100, 1, 2]];
  assert.equal(S.of(inst('footprint', { text: 'trades' }), facts([bar(0, { fp: rows })])).text, 'No print counts for these bars');
  assert.equal(S.of(inst('footprint', { text: 'trades' }), facts([bar(0, { fp: rows, fpn: [[100, 1, 1]] })])), null);
  assert.equal(S.of(inst('footprint', { text: '' }), facts([bar(0, { fp: rows })])), null);
});

test('pine: an error is the note (first line, the whole text on hover); running says so; warnings are counted; a clean script says nothing', () => {
  const pine = (state) => S.of(inst('pine', {}, { uid: 'p1' }), facts([bar(0)], { pine: { p1: state } }));
  assert.deepEqual(pine({ error: 'Syntax error at line 3\nunexpected token', notes: [], running: false }),
    { text: 'Syntax error at line 3', tone: 'warn', title: 'Syntax error at line 3\nunexpected token' });
  const long = pine({ error: 'x'.repeat(200), notes: [] });
  assert.equal(long.text.length, 70);
  assert.match(long.text, /…$/);
  assert.equal(long.title.length, 200);
  assert.deepEqual(pine({ error: 'Pine needs a time chart', notes: [], running: true }), { text: 'Pine needs a time chart', tone: 'warn', title: 'Pine needs a time chart' }, 'an error beats running');
  assert.deepEqual(pine({ error: null, notes: [], running: true }), { text: 'Running…', tone: 'info' });
  assert.deepEqual(pine({ error: null, notes: ['ta.foo is not supported'], running: false }), { text: 'ta.foo is not supported', tone: 'warn', title: 'ta.foo is not supported' });
  assert.deepEqual(pine({ error: null, notes: ['a', 'b', 'c'], running: false }), { text: 'a (+2 more)', tone: 'warn', title: 'a\nb\nc' });
  assert.equal(pine({ error: null, notes: [], running: false }), null);
  assert.equal(pine(undefined), null, 'no fact for this row: nothing to say');
  assert.equal(S.of(inst('pine', {}, { uid: 'p1' }), facts([bar(0)])), null, 'a page that gathers no Pine facts');
  assert.equal(S.of(inst('pine', {}, { uid: 'p1', visible: false }), facts([bar(0)], { pine: { p1: { error: 'x', notes: [] } } })), null, 'a hidden row stays quiet');
});

/* 2026-10-22 indicator cleanup (P3): the legend notes follow what the layers really draw. */
const ep = (s, extra = {}) => ({ id: s + extra.t0, s, p: 100, t0: 0, t1: 20000, r: 6, pk: 50, tr: 40, ab: 12000, end: 'traded', ...extra });
const live = { rows: 10, covered: true, live: true };

test('bigorders without "Keep ended orders": no ended-order count and no book warning (only the live line draws)', () => {
  const bars = [bar(0)];
  assert.equal(S.of(inst('bigorders', { multiple: 5, minSeconds: 5, history: false }), facts(bars, { book: { rows: 0, covered: false, live: false }, episodes: [] })), null);
  assert.match(S.of(inst('bigorders', { multiple: 5, minSeconds: 5, history: true }), facts(bars, { book: live, episodes: [] })).text, /None in view/);
});

test('absorb / pulled / iceberg counts respect the Side filter', () => {
  const bars = [bar(0)];
  const eps = [ep('b', { ab: 12000 }), ep('a', { t0: 1, ab: 12000 })];
  const text = (id, side, extra = {}) => S.of(inst(id, { multiple: 4, minSeconds: 5, minTraded: 1, side, ...extra }), facts(bars, { book: live, episodes: eps })).text;
  assert.equal(text('absorb', 'all'), '2 marks in view');
  assert.equal(text('absorb', 'up'), '1 mark in view');
  assert.match(text('absorb', 'down', { multiple: 100 }), /None in view/);
  const pulls = [ep('b', { end: 'pulled', t1: 20000 }), ep('a', { t0: 1, end: 'pulled', t1: 20000 })];
  const pt = (side) => S.of(inst('pulled', { multiple: 4, minSeconds: 5, side }), facts(bars, { book: live, episodes: pulls })).text;
  assert.equal(pt('all'), '2 marks in view');
  assert.equal(pt('down'), '1 mark in view');
  const ice = [ep('b', { rl: 3, tr: 200 }), ep('a', { t0: 1, rl: 3, tr: 200 })];
  const it = (side) => S.of(inst('iceberg', { multiple: 3, minTraded: 1, side }), facts(bars, { book: live, episodes: ice })).text;
  assert.equal(it('all'), '2 marks in view');
  assert.equal(it('up'), '1 mark in view');
});

test('heatmap: its own note (zoomed out past the depth limit), never the book-store warnings; bubbles-only says nothing', () => {
  const day = 24 * 3600 * 1000, wide = [{ ...bar(0), ms: 0 }, { ...bar(1), ms: 4 * day }];
  assert.equal(S.of(inst('heatmap'), facts(wide, { barMs: 3600000, book: { rows: 0, covered: false, live: false } })).text, 'Zoomed out too far: the heatmap shows up to 72 hours');
  assert.equal(S.of(inst('heatmap', { map: false }), facts(wide, { barMs: 3600000 })), null);
  assert.equal(S.of(inst('heatmap'), facts([bar(0), bar(1)], { barMs: 60000, book: { rows: 0, covered: false, live: false } })), null);
});

test('stoprun: bars without sweep data are said so, not reported as "none found"; exhaust is untouched', () => {
  const old = [{ ...bar(0), sw: undefined }, { ...bar(1), sw: undefined }];
  assert.equal(S.of(inst('stoprun', { length: 20, minSize: 50 }), facts(old)).text, 'No sweep detail for these bars');
  assert.match(S.of(inst('stoprun', { length: 20, minSize: 50 }), facts([bar(0), bar(1)])).text, /None in view/);
  assert.match(S.of(inst('exhaust', { length: 20, multiple: 2, wait: 3 }), facts(old)).text, /None in view/);
});

test('notes: headlines bolts outside the burst markets, the bar-length limit, cstat zoom, only the first instance draws', () => {
  const h = inst('headlines', { show: 'bursts' });
  assert.match(S.of(h, facts([bar(0)], { root: 'CL' })).text, /No bolts on this market/);
  assert.equal(S.of(h, facts([bar(0)], { root: 'NQ' })), null);
  assert.equal(S.of(inst('headlines', { show: 'all' }), facts([bar(0)], { root: 'CL' })), null, 'every headline still draws its dot');
  const k = 'topen:570';
  const hour = 3600000, withVal = [bar(0, { sv: { [k]: 100 } })];
  assert.match(S.of(inst('topen', { time: '09:30' }), facts([bar(0)], { barMs: hour })).text, /5 minutes or less/);
  assert.equal(S.of(inst('topen', { time: '09:30' }), facts(withVal, { barMs: hour })), null, 'a bar that carries the value: it works');
  assert.equal(S.of(inst('topen', { time: '09:30' }), facts([bar(0)], { barMs: 60000 })), null);
  assert.equal(S.of(inst('cstat'), facts([bar(0)], { spacing: 20 })).text, 'Zoom in to see the stats');
  assert.equal(S.of(inst('cstat'), facts([bar(0)], { spacing: 40 })), null);
  const a = { id: 'fvg', uid: 'a', params: { min: 0.25, length: 14 } }, b = { id: 'fvg', uid: 'b', params: { min: 0.25, length: 14 } };
  assert.match(S.of(b, facts([bar(0)], { indicators: [a, b] })).text, /Only the first gap indicator/);
  assert.equal(S.of(a, facts([bar(0)], { indicators: [a, b] })).text, 'No open gap in view');
  assert.equal(S.of(b, facts([bar(0)], { indicators: [{ ...a, visible: false }, b] })).text, 'No open gap in view', 'a hidden first one does not count');
});

test('opening range: bars longer than the window are said plainly, even when a value draws', () => {
  const sv = { 'orb:5': 100, 'orb:15': 100 };
  const bars = [bar(0, { sv }), bar(1, { sv })];
  const t = S.of(inst('orb', { minutes: 5, start: '09:30' }), facts(bars, { barMs: 15 * 60000 }));
  assert.equal(t.tone, 'warn');
  assert.match(t.text, /longer than the 5 minutes/);
  assert.equal(S.of(inst('orb', { minutes: 15, start: '09:30' }), facts(bars, { barMs: 15 * 60000 })), null, 'a bar as long as the window is fine');
  assert.equal(S.of(inst('orb', { minutes: 5, start: '09:30' }), facts(bars, { barMs: 60000 })), null);
});
