import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* S5, the stale tag (2026-09-28 safety pass): a stale bid / ask is shown with a clock and its age beside it, not only
   dimmed with the reason in a hover. The tag never re-decides staleness: each surface hands in its own verdict (the
   chart's Buy/Sell block: quoteView's, 30 s; the order panel: freshQuote's, 10 s) and the quote's age. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');

test('S5: ageText -- whole units, rounded down; no trade time is a dash', () => {
  assert.equal(T.ageText(0), '0s');
  assert.equal(T.ageText(999), '0s');
  assert.equal(T.ageText(42_000), '42s');
  assert.equal(T.ageText(59_999), '59s');
  assert.equal(T.ageText(60_000), '1m');
  assert.equal(T.ageText(5 * 60_000 + 59_000), '5m');
  assert.equal(T.ageText(3_600_000), '1h');
  assert.equal(T.ageText(23 * 3_600_000 + 59 * 60_000), '23h');
  assert.equal(T.ageText(86_400_000 * 3 + 5), '3d');
  assert.equal(T.ageText(-5000), '0s', 'a trade stamped a hair in the future is not a negative age');
  assert.equal(T.ageText(null), '—');
  assert.equal(T.ageText(NaN), '—');
});

test('S5: staleTag -- nothing while fresh; the age and a plain reason while stale', () => {
  assert.deepEqual(T.staleTag(false, 42_000), { show: false, text: '', title: '' });
  assert.deepEqual(T.staleTag(true, 42_000),
    { show: true, text: '42s', title: 'Stale: no trade for 42s — bid / ask are from the last trade' });
  assert.deepEqual(T.staleTag(true, 125_000),
    { show: true, text: '2m', title: 'Stale: no trade for 2m — bid / ask are from the last trade' });
  assert.deepEqual(T.staleTag(true, null), { show: true, text: '—', title: 'Stale: no trade yet' });
});

test("S5: the chart's Buy/Sell block -- its tag follows quoteView's own 30 s verdict and age", () => {
  const now = 1_000_000;
  const q = (ageMs) => ({ bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: now - ageMs });
  const tagFor = (quote) => { const v = T.quoteView(quote, 0.25, now); return T.staleTag(v.stale, v.age); };
  assert.equal(tagFor(q(29_000)).show, false, '29 s old: fresh by the block\'s rule -- the spread shows');
  assert.equal(tagFor(q(30_000)).show, false, 'exactly 30 s is still fresh (quoteView: age > 30 s is stale)');
  assert.deepEqual([tagFor(q(30_001)).show, tagFor(q(30_001)).text], [true, '30s']);
  assert.deepEqual([tagFor(q(95_000)).show, tagFor(q(95_000)).text], [true, '1m']);
  assert.deepEqual([tagFor({ bid: 30000, ask: 30000.25 }).show, tagFor({ bid: 30000, ask: 30000.25 }).text], [true, '—'],
    'a quote with no trade time is stale with no age');
  assert.deepEqual([tagFor(null).show, tagFor(null).text], [true, '—'], 'no quote at all');
  // the prices stay whatever quoteView says -- the tag only adds, never re-labels them
  assert.equal(T.quoteView(q(95_000), 0.25, now).bid, '30,000.00');
});

test('S5: the order panel -- its tag follows freshQuote\'s own 10 s verdict, with the age since the last trade', () => {
  const now = 2_000_000, STALE_MS = 10_000;   // orderpanel.js's STALE_MS
  const panelTag = (quote) => T.staleTag(!T.freshQuote(quote, now, STALE_MS),
    quote && Number.isFinite(quote.ts_ms) ? now - quote.ts_ms : null);   // exactly orderpanel.js's paint()
  const q = (ageMs) => ({ bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: now - ageMs });
  assert.equal(panelTag(q(9_000)).show, false);
  assert.equal(panelTag(q(10_000)).show, false, 'exactly 10 s is fresh (freshQuote: <= maxAge)');
  assert.deepEqual([panelTag(q(10_500)).show, panelTag(q(10_500)).text], [true, '10s']);
  assert.deepEqual([panelTag(q(42_000)).show, panelTag(q(42_000)).text], [true, '42s']);
  assert.deepEqual([panelTag(q(7_200_000)).show, panelTag(q(7_200_000)).text], [true, '2h']);
  assert.deepEqual([panelTag(null).show, panelTag(null).text], [true, '—']);
});
