import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const N = require('../../homebase/static/charts/news.js');

const item = (o) => ({ id: 'i1', source: 'financialjuice', t_ms: 1_700_000_000_000, seen_ms: 1_700_000_000_500,
  title: 'Fed holds rates', url: 'https://x', tags: [], ...o });

/* ---- ET formatting ---- */
test('etTime: 24h America/New_York, HH:MM by default, HH:MM:SS with seconds', () => {
  // 2024-01-10T14:30:05Z = 09:30:05 ET (EST, UTC-5)
  const ms = Date.parse('2024-01-10T14:30:05Z');
  assert.equal(N.etTime(ms), '09:30');
  assert.equal(N.etTime(ms, true), '09:30:05');
});
test('etTime: a summer date lands on EDT (UTC-4), never thrown on a bad ms', () => {
  const ms = Date.parse('2024-07-10T13:30:00Z');   // EDT: 09:30
  assert.equal(N.etTime(ms), '09:30');
  assert.equal(N.etTime(NaN), '—');
  assert.equal(N.etTime(undefined), '—');
});

/* ---- merge / dedupe by id ---- */
test('mergeItems: dedupes by id, newest first, a later copy of the same id wins', () => {
  const a = [item({ id: '1', t_ms: 100 }), item({ id: '2', t_ms: 200 })];
  const b = [item({ id: '2', t_ms: 200, title: 'updated' }), item({ id: '3', t_ms: 300 })];
  const merged = N.mergeItems(a, b);
  assert.deepEqual(merged.map((x) => x.id), ['3', '2', '1']);
  assert.equal(merged.find((x) => x.id === '2').title, 'updated');
});
test('mergeItems: caps at the given limit, keeping the newest', () => {
  const a = [item({ id: '1', t_ms: 100 }), item({ id: '2', t_ms: 200 }), item({ id: '3', t_ms: 300 })];
  const merged = N.mergeItems(a, [], 2);
  assert.deepEqual(merged.map((x) => x.id), ['3', '2']);
});
test('mergeItems: never mutates its inputs; missing/empty inputs are safe', () => {
  const a = [item({ id: '1', t_ms: 100 })];
  const snapshot = JSON.stringify(a);
  N.mergeItems(a, [item({ id: '2', t_ms: 200 })]);
  assert.equal(JSON.stringify(a), snapshot);
  assert.deepEqual(N.mergeItems(null, null), []);
  assert.deepEqual(N.mergeItems(undefined, [item({ id: '1' })]).map((x) => x.id), ['1']);
});
test('mergeItems: default cap is 500', () => {
  const many = Array.from({ length: 600 }, (_, i) => item({ id: String(i), t_ms: i }));
  assert.equal(N.mergeItems([], many).length, 500);
});

/* ---- filters ---- */
test('matchesFilter: no filter (or empty arrays) matches everything', () => {
  assert.equal(N.matchesFilter(item(), null), true);
  assert.equal(N.matchesFilter(item(), {}), true);
  assert.equal(N.matchesFilter(item(), { sources: [], tags: [] }), true);
});
test('matchesFilter: sources is case-insensitive and exclusive', () => {
  assert.equal(N.matchesFilter(item({ source: 'truth' }), { sources: ['TRUTH'] }), true);
  assert.equal(N.matchesFilter(item({ source: 'truth' }), { sources: ['financialjuice'] }), false);
});
test('matchesFilter: tags need at least one overlap, case-insensitive', () => {
  const it = item({ tags: ['war', 'oil'] });
  assert.equal(N.matchesFilter(it, { tags: ['OIL'] }), true);
  assert.equal(N.matchesFilter(it, { tags: ['fed'] }), false);
  assert.equal(N.matchesFilter(item({ tags: [] }), { tags: ['war'] }), false);
});
test('matchesFilter: sources AND tags both apply when both given', () => {
  const it = item({ source: 'truth', tags: ['trump'] });
  assert.equal(N.matchesFilter(it, { sources: ['truth'], tags: ['trump'] }), true);
  assert.equal(N.matchesFilter(it, { sources: ['financialjuice'], tags: ['trump'] }), false);
});
test('filterItems: filters a list, null-safe', () => {
  const items = [item({ id: '1', source: 'truth' }), item({ id: '2', source: 'financialjuice' })];
  assert.deepEqual(N.filterItems(items, { sources: ['truth'] }).map((x) => x.id), ['1']);
  assert.deepEqual(N.filterItems(null, {}), []);
});
test('availableSources / availableTags: sorted, de-duplicated', () => {
  const items = [item({ source: 'truth', tags: ['war', 'fed'] }), item({ source: 'financialjuice', tags: ['fed'] })];
  assert.deepEqual(N.availableSources(items), ['financialjuice', 'truth']);
  assert.deepEqual(N.availableTags(items), ['fed', 'war']);
});

/* ---- Trump / breaking ---- */
test('isTrump: every truth item, or any item the tagger already caught "trump" on', () => {
  assert.equal(N.isTrump(item({ source: 'truth', tags: [] })), true);
  assert.equal(N.isTrump(item({ source: 'financialjuice', tags: ['trump'] })), true);
  assert.equal(N.isTrump(item({ source: 'financialjuice', tags: ['war'] })), false);
  assert.equal(N.isTrump(null), false);
});
test('isBreaking: true while now is within flashMs of seen_ms, false before/after/at the edge', () => {
  const it = item({ seen_ms: 1000 });
  assert.equal(N.isBreaking(it, 1000, 3000), true);
  assert.equal(N.isBreaking(it, 3999, 3000), true);
  assert.equal(N.isBreaking(it, 4000, 3000), false);   // exactly at the flash window's edge: no longer breaking
  assert.equal(N.isBreaking(it, 999, 3000), false);    // a backfilled item's seen_ms after "now": never breaking
});

/* ---- burst <-> headline link mapping ---- */
const burst = (o) => ({ root: 'GC', t_ms: 1_700_000_000_000, dir: 'up', move_ticks: 12, ratio: 4.2,
  from_px: 2000, to_px: 2003, near_news: [], ...o });

test('burstKey: root + t_ms (bursts carry no id of their own)', () => {
  assert.equal(N.burstKey(burst({ root: 'GC', t_ms: 5 })), 'GC:5');
});
test('mergeBursts: upserts by burstKey (a burst_update replaces near_news in place), newest first', () => {
  const a = [burst({ t_ms: 100, near_news: [] })];
  const b = [burst({ t_ms: 100, near_news: [item({ id: 'n1' })] }), burst({ t_ms: 200, root: 'NQ' })];
  const merged = N.mergeBursts(a, b);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].root, 'NQ');
  assert.equal(merged[1].near_news.length, 1);
});
test('nearNews: within +/- windowMs by t_ms OR seen_ms, earliest first', () => {
  const items = [
    item({ id: 'far', t_ms: 0, seen_ms: 0 }),
    item({ id: 'by-t', t_ms: 1_000_000 + 100_000, seen_ms: 0 }),
    item({ id: 'by-seen', t_ms: 0, seen_ms: 1_000_000 - 50_000 }),
  ];
  const near = N.nearNews(1_000_000, items, 180_000);
  assert.deepEqual(near.map((x) => x.id), ['by-seen', 'by-t']);
});
test('nearNews: exactly at the window edge counts (bursts.py uses <=)', () => {
  const items = [item({ id: 'edge', t_ms: 1_000_000 + 180_000, seen_ms: 0 })];
  assert.deepEqual(N.nearNews(1_000_000, items, 180_000).map((x) => x.id), ['edge']);
  assert.deepEqual(N.nearNews(1_000_000, [item({ id: 'past-edge', t_ms: 1_000_000 + 180_001, seen_ms: 0 })], 180_000), []);
});
test('burstsNear: the reverse lookup, earliest first', () => {
  const bursts = [burst({ t_ms: 1_000_000, root: 'GC' }), burst({ t_ms: 5_000_000, root: 'NQ' })];
  const near = N.burstsNear(item({ t_ms: 1_050_000, seen_ms: 1_050_000 }), bursts, 180_000);
  assert.deepEqual(near.map((b) => b.root), ['GC']);
});
test('burstLinkedNews: prefers the burst\'s own near_news; falls back to nearNews over the page\'s items', () => {
  const withLinks = burst({ near_news: [item({ id: 'a' })] });
  assert.deepEqual(N.burstLinkedNews(withLinks, [item({ id: 'b' })]).map((x) => x.id), ['a']);
  const noLinks = burst({ near_news: [], t_ms: 1_000_000 });
  const fallback = N.burstLinkedNews(noLinks, [item({ id: 'b', t_ms: 1_000_000, seen_ms: 1_000_000 })]);
  assert.deepEqual(fallback.map((x) => x.id), ['b']);
});
test('burstTip / headlineTip: include the ratio/direction and the ET time, never throw', () => {
  const tip = N.burstTip(burst({ near_news: [item({ title: 'CPI hot' })] }), []);
  assert.match(tip, /4\.2x/);
  assert.match(tip, /UP/);
  assert.match(tip, /CPI hot/);
  assert.match(N.headlineTip(item({ tags: ['war'] })), /\[war\]/);
});

/* ---- markers ---- */
test('headlineMarkers: only items in [fromMs, toMs), most recent `cap` kept, tip carried for hover', () => {
  const items = [item({ id: '1', t_ms: 100 }), item({ id: '2', t_ms: 200 }), item({ id: '3', t_ms: 900 })];
  const out = N.headlineMarkers(items, { fromMs: 0, toMs: 500, cap: 1 });
  assert.deepEqual(out.map((m) => m.id), ['news:2']);
  assert.equal(out[0].ms, 200);
  assert.equal(typeof out[0].tip, 'string');
});
test('headlineMarkers: colours a Trump item and a still-breaking item differently from a plain one', () => {
  const now = 1_000_000;
  const [plain] = N.headlineMarkers([item({ id: '1', t_ms: 0, seen_ms: -10_000 })], { fromMs: -1, toMs: 1, nowMs: now });
  const [trump] = N.headlineMarkers([item({ id: '2', source: 'truth', t_ms: 0, seen_ms: -10_000 })], { fromMs: -1, toMs: 1, nowMs: now });
  const [breaking] = N.headlineMarkers([item({ id: '3', t_ms: 0, seen_ms: now - 100 })], { fromMs: -1, toMs: 1, nowMs: now });
  assert.notEqual(plain.color, trump.color);
  assert.notEqual(plain.color, breaking.color);
  assert.notEqual(trump.color, breaking.color);
});
test('burstMarkers: only the given root, in range; direction picks the position and up/down colour', () => {
  const bursts = [burst({ root: 'GC', t_ms: 100, dir: 'up' }), burst({ root: 'NQ', t_ms: 150, dir: 'down' }),
    burst({ root: 'GC', t_ms: 900, dir: 'down' })];
  const out = N.burstMarkers(bursts, { root: 'GC', fromMs: 0, toMs: 500 }, []);
  assert.deepEqual(out.map((m) => m.id), ['burst:GC:100']);
  assert.equal(out[0].position, 'belowBar');
  assert.equal(out[0].text, '⚡');
});

test('chartNews: the "News on chart" setting — bursts-with-news by default, all, or off', () => {
  const items = [{ id: 'h1', t_ms: 1_000_000, title: 'Fed', source: 'fj' }];
  const withNews = { root: 'NQ', t_ms: 1_000_000, dir: 'up', ratio: 4, move_ticks: 12, near_news: [items[0]] };
  const bare = { root: 'NQ', t_ms: 9_000_000_000, dir: 'down', ratio: 3, move_ticks: 8, near_news: [] };
  const d = N.chartNews(undefined, [withNews, bare], items);
  assert.equal(d.headlines, false);
  assert.deepEqual(d.bursts, [withNews]);
  assert.deepEqual(N.chartNews('junk', [withNews, bare], items), d, 'unknown -> the default');
  const all = N.chartNews('all', [withNews, bare], items);
  assert.equal(all.headlines, true);
  assert.deepEqual(all.bursts, [withNews, bare]);
  assert.deepEqual(N.chartNews('off', [withNews, bare], items), { headlines: false, bursts: [] });
});
