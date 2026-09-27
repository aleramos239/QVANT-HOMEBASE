/* Homebase Charts — pure helpers for the cross-market burst radar strip (Task 2): given the chart
   service's per-root current ratio (ticks-in-30s move vs its 60-min median, from BurstBook.now()
   via the /ws status message's `bursts.now`, or GET /api/bursts/now for the first paint), decide
   each chip's colour class and label, and the strip's fixed left-to-right order. No DOM, no browser
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

/* `now` = {root: ratio|null} (BurstBook.now(), the /ws status's `bursts.now` or GET /api/bursts/now), `order`
   = the service's roots in catalog order (GET /api/symbols) -> one chip per root of `now`, in a FIXED order
   (final review I2a): `order` first, then any root it does not list, alphabetically. Never sorted by ratio --
   a strip that reshuffles every 2 s turns a press into a click on another root; the colour shows the ratio. */
function radarChips(now, order) {
  const src = now && typeof now === 'object' ? now : {};
  const roots = Object.keys(src), known = Array.isArray(order) ? order : [];
  const rank = (r) => { const i = known.indexOf(r); return i < 0 ? known.length : i; };
  return roots
    .sort((a, b) => rank(a) - rank(b) || (a < b ? -1 : a > b ? 1 : 0))
    .map((root) => {
      const ratio = typeof src[root] === 'number' && Number.isFinite(src[root]) ? src[root] : null;
      return { root, ratio, cls: ratioClass(ratio), text: ratioText(ratio) };
    });
}

const api = { AMBER_AT, RED_AT, ratioClass, ratioText, radarChips };
if (typeof window !== 'undefined') window.HBRadar = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
