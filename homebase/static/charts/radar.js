/* Homebase Charts — pure helpers for the cross-market burst radar strip (Task 2): given the chart
   service's per-root current ratio (ticks-in-30s move vs its 60-min median, from BurstBook.now()
   via the /ws status message's `bursts.now`, or GET /api/bursts/now for the first paint), decide
   each chip's colour class and label, and the strip's left-to-right order. No DOM, no browser
   globals: the Node tests load this file directly. app.js builds the chip elements, wires the
   click-to-applySymbol behaviour and the collapse/localStorage state. */
(function () {
'use strict';

const AMBER_AT = 2, RED_AT = 4;

/* grey below 2x, amber 2-4x, red >= 4x. A root with no ratio yet (still warming up, `ratio_now()`
   None) is grey too -- "no data" is not a "quiet market" colour choice, so it never gets mistaken
   for a real sub-2x reading. */
function ratioClass(ratio) {
  if (typeof ratio !== 'number' || !Number.isFinite(ratio)) return 'grey';
  if (ratio >= RED_AT) return 'red';
  if (ratio >= AMBER_AT) return 'amber';
  return 'grey';
}

/* "4.2×", or '—' before that root has warmed up (ratio null/not a number). */
function ratioText(ratio) {
  return (typeof ratio === 'number' && Number.isFinite(ratio)) ? `${ratio.toFixed(1)}×` : '—';
}

/* `now` = {root: ratio|null} (BurstBook.now(), the /ws status's `bursts.now` or GET /api/bursts/now)
   -> chips sorted by ratio descending; a root with no ratio yet sorts last, alphabetically among
   themselves so the strip does not reshuffle those every 2 s while several roots sit at "--". */
function radarChips(now) {
  const roots = Object.keys(now && typeof now === 'object' ? now : {});
  return roots
    .map((root) => ({ root, ratio: typeof now[root] === 'number' && Number.isFinite(now[root]) ? now[root] : null }))
    .sort((a, b) => {
      if (a.ratio == null && b.ratio == null) return a.root < b.root ? -1 : a.root > b.root ? 1 : 0;
      if (a.ratio == null) return 1;
      if (b.ratio == null) return -1;
      return b.ratio - a.ratio;
    })
    .map((c) => ({ ...c, cls: ratioClass(c.ratio), text: ratioText(c.ratio) }));
}

const api = { AMBER_AT, RED_AT, ratioClass, ratioText, radarChips };
if (typeof window !== 'undefined') window.HBRadar = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
