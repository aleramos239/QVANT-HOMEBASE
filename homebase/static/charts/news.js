/* Homebase Charts — HBNews: the pure half of the news panel, headline markers and burst markers
   (2026-09-27 plan, Task 4; spec docs/superpowers/specs/2026-09-27-charts-news-design.md Part B).

   Backend shapes (homebase/charts/news.py, bursts.py, server.py):
     - a news item: {id, source: "financialjuice"|"truth", t_ms, seen_ms, title, url, tags: [...]}, pushed live
       as {"type": "news", ...item} and read back from GET /api/news (newest first, capped at 500).
     - a burst: {root, t_ms, dir: "up"|"down", move_ticks, ratio, from_px, to_px, near_news: [items]}, pushed as
       {"type": "burst", ...} when it fires and {"type": "burst_update", ...} when a late headline attaches to it
       (near_news updated in place; root+t_ms is the record's identity -- bursts carry no id of their own).

   No browser globals at load time: the Node tests load this file directly (window.HBNews when run on the page,
   like every other pure module here -- catalog.js, events.js, radar.js, trade.js, fillquality.js). */
(function () {
'use strict';

const SOURCE_LABELS = Object.freeze({ financialjuice: 'FinancialJuice', truth: 'Truth Social' });
const ITEMS_CAP = 500;            // "Items are capped at 500 in memory" (spec)
const FLASH_MS = 3000;            // "A new item flashes for 3 s as breaking" (spec)
const LINK_MS = 3 * 60_000;       // news<->burst window, mirrors bursts.py's NEWS_LINK_MS (+/- 3 minutes)
const MARKERS_CAP = 300;          // headline markers per chart, "capped per visible range" (spec)
const BURSTS_CAP = 200;

const ET_TIME = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23',
  hour: '2-digit', minute: '2-digit' });
const ET_TIME_SEC = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23',
  hour: '2-digit', minute: '2-digit', second: '2-digit' });

function sourceLabel(source) { return SOURCE_LABELS[source] || String(source || ''); }

/* Every Truth Social post is a Trump post; any other source is one only if the tagger already caught "trump"
   in its title (news.py's tag() does exactly this -- trust the backend's tags rather than re-scanning text). */
function isTrump(item) {
  return !!item && (item.source === 'truth' || (Array.isArray(item.tags) && item.tags.includes('trump')));
}

/* "08:31" / "08:31:05" ET, 24h. "-" for anything unparseable -- a bad ms must never throw on the page. */
function etTime(ms, withSeconds = false) {
  return Number.isFinite(ms) ? (withSeconds ? ET_TIME_SEC : ET_TIME).format(new Date(ms)) : '—';
}

/* ---- the panel's item store: merge/dedupe by id, newest first, capped ---- */

/* `existing` and `incoming` merged by id (a later copy of the same id -- e.g. a GET /api/news backfill landing
   after the live ws item -- overwrites the earlier one, but the shapes are identical in practice), newest
   first by t_ms, capped at `cap`. Never mutates either input array. */
function mergeItems(existing, incoming, cap = ITEMS_CAP) {
  const byId = new Map();
  for (const it of existing || []) if (it && it.id != null) byId.set(it.id, it);
  for (const it of incoming || []) if (it && it.id != null) byId.set(it.id, it);
  return [...byId.values()].sort((a, b) => b.t_ms - a.t_ms).slice(0, cap);
}

/* filter: {sources: [...] | null, tags: [...] | null} (any case; empty/absent = no restriction on that axis). */
function matchesFilter(item, filter) {
  if (!item) return false;
  const f = filter || {};
  if (f.sources && f.sources.length) {
    const want = new Set(f.sources.map((s) => String(s).toLowerCase()));
    if (!want.has(String(item.source).toLowerCase())) return false;
  }
  if (f.tags && f.tags.length) {
    const want = new Set(f.tags.map((t) => String(t).toLowerCase()));
    const have = new Set((item.tags || []).map((t) => String(t).toLowerCase()));
    if (![...want].some((t) => have.has(t))) return false;
  }
  return true;
}
function filterItems(items, filter) { return (items || []).filter((it) => matchesFilter(it, filter)); }

/* The sources / tags actually present, for building the filter chip bar -- sorted, de-duplicated. */
function availableSources(items) { return [...new Set((items || []).map((it) => it.source))].sort(); }
function availableTags(items) {
  return [...new Set((items || []).flatMap((it) => it.tags || []))].sort();
}

/* An item still counts as "breaking" (the 3 s flash) while nowMs is within flashMs of when WE saw it --
   seen_ms, never t_ms (a bad feed's pubDate can be stale; seen_ms is when this service actually polled it,
   news.py's own ordering key). A backfilled item (GET /api/news on page load) has a seen_ms already in the
   past, so it correctly never flashes. */
function isBreaking(item, nowMs, flashMs = FLASH_MS) {
  return !!item && Number.isFinite(item.seen_ms) && Number.isFinite(nowMs) && nowMs - item.seen_ms < flashMs
    && nowMs - item.seen_ms >= 0;
}

/* ---- bursts: keyed by root+t_ms (they carry no id of their own) ---- */

function burstKey(b) { return `${b.root}:${b.t_ms}`; }

/* `incoming` upserts onto `existing` by burstKey (a burst_update replaces its burst's near_news in place),
   newest first, capped. Mirrors mergeItems' shape for the same reasons. */
function mergeBursts(existing, incoming, cap = BURSTS_CAP) {
  const byKey = new Map();
  for (const b of existing || []) if (b) byKey.set(burstKey(b), b);
  for (const b of incoming || []) if (b) byKey.set(burstKey(b), b);
  return [...byKey.values()].sort((a, b) => b.t_ms - a.t_ms).slice(0, cap);
}

/* Is `item` within +/- windowMs of tMs, by t_ms OR seen_ms -- the exact rule bursts.py's `_near` uses (a
   slow-to-publish item that broke close to the burst still counts). */
function _near(tMs, item, windowMs) {
  return Math.abs(item.t_ms - tMs) <= windowMs || Math.abs(item.seen_ms - tMs) <= windowMs;
}

/* News items near a given time (a burst's t_ms), earliest first -- the client-side mirror of bursts.py's
   near_news(), used as a fallback display when a burst record's own near_news is empty (e.g. a headline that
   the currently-loaded /api/news page/ws stream has but arrived before this page ever saw the burst_update). */
function nearNews(tMs, items, windowMs = LINK_MS) {
  return (items || []).filter((it) => _near(tMs, it, windowMs)).sort((a, b) => a.t_ms - b.t_ms);
}

/* The reverse lookup: which bursts are linked to a given headline (for a small badge on the headline row),
   earliest first. */
function burstsNear(item, bursts, windowMs = LINK_MS) {
  if (!item) return [];
  return (bursts || []).filter((b) => _near(b.t_ms, item, windowMs)).sort((a, b) => a.t_ms - b.t_ms);
}

/* The headlines a burst tooltip should show: its own near_news if the backend already linked any, else our
   own nearNews() over whatever headlines this page currently holds. */
function burstLinkedNews(burst, items) {
  if (burst && Array.isArray(burst.near_news) && burst.near_news.length) return burst.near_news;
  return burst ? nearNews(burst.t_ms, items) : [];
}

/* "4.2x . UP 12.0 ticks . 2 headlines" plus one line per linked headline, for the ⚡ marker's tooltip. */
function burstTip(burst, items) {
  const linked = burstLinkedNews(burst, items);
  const head = `${burst.ratio.toFixed(1)}x · ${burst.dir === 'up' ? 'UP' : 'DOWN'} `
    + `${burst.move_ticks.toFixed(1)} ticks · ${etTime(burst.t_ms)} ET`;
  const lines = linked.map((it) => `${etTime(it.t_ms)} ${sourceLabel(it.source)} — ${it.title}`);
  return [head, ...lines].join('\n');
}

/* "08:31 FinancialJuice: Fed cuts rates 25bps [war, fed]" for the headline marker's hover tooltip. */
function headlineTip(item) {
  const tags = (item.tags || []).length ? ` [${item.tags.join(', ')}]` : '';
  return `${etTime(item.t_ms)} ${sourceLabel(item.source)}: ${item.title}${tags}`;
}

/* ---- markers, for cell.setExtraMarkers via HBDrawings.placeMarkers ----
   Each record carries {ms, ...} for placeMarkers plus a `tip` field the caller strips before handing the list
   to setExtraMarkers (tradelines.js's own convention: the tooltip text stays with the overlay, matched back to
   a drawn marker by its own crosshair-hit test -- never sent to Lightweight Charts itself). */

const TRUMP_COLOR = '#7E57C2';     // --paper: distinct from every trade/bot marker colour already in use
const NEWS_COLOR = '#787B86';      // --text-2: a quiet grey tick, not a trade signal
const BREAKING_COLOR = '#F7A600';  // --warn: the "just landed" 3 s flash

/* Headline ticks within [fromMs, toMs), most recent `cap` kept (a chart with months of loaded bars must not
   try to draw hundreds of ticks it can't legibly show). `nowMs` decides which are still "breaking". */
function headlineMarkers(items, { fromMs, toMs, cap = MARKERS_CAP, nowMs = Date.now(), flashMs = FLASH_MS } = {}) {
  const inRange = (items || []).filter((it) => it.t_ms >= fromMs && it.t_ms < toMs);
  inRange.sort((a, b) => b.t_ms - a.t_ms);
  return inRange.slice(0, cap).map((it) => ({
    id: `news:${it.id}`, ms: it.t_ms, position: 'aboveBar', shape: 'circle',
    size: 0.35, color: isBreaking(it, nowMs, flashMs) ? BREAKING_COLOR : isTrump(it) ? TRUMP_COLOR : NEWS_COLOR,
    text: '', tip: headlineTip(it),
  }));
}

/* A burst chart shows only bursts of ITS root, in range. Bursts are rare (a 120 s refractory per root), so no
   aggressive cap is needed -- `cap` is only a defensive ceiling. */
function burstMarkers(bursts, { root, fromMs, toMs, cap = BURSTS_CAP, upColor = '#089981', downColor = '#F23645' } = {}, items) {
  const inRange = (bursts || []).filter((b) => b.root === root && b.t_ms >= fromMs && b.t_ms < toMs);
  inRange.sort((a, b) => b.t_ms - a.t_ms);
  return inRange.slice(0, cap).map((b) => ({
    id: `burst:${burstKey(b)}`, ms: b.t_ms, position: b.dir === 'up' ? 'belowBar' : 'aboveBar',
    shape: 'circle', size: 0.6, color: b.dir === 'up' ? upColor : downColor, text: '⚡',
    tip: burstTip(b, items),
  }));
}

const api = {
  SOURCE_LABELS, ITEMS_CAP, FLASH_MS, LINK_MS, MARKERS_CAP, BURSTS_CAP,
  sourceLabel, isTrump, etTime,
  mergeItems, matchesFilter, filterItems, availableSources, availableTags, isBreaking,
  burstKey, mergeBursts, nearNews, burstsNear, burstLinkedNews, burstTip, headlineTip,
  headlineMarkers, burstMarkers,
};
if (typeof window !== 'undefined') window.HBNews = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
