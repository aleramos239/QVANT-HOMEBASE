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
