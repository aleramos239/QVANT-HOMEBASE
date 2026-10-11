/* Homebase Charts — HBFlowMath: the footprint's extra marks as pure functions of one bar's rows, so they are Node-tested.
   fp = [[price, sellAtBid, buyAtAsk], ...] (any order), tick = the market's tick size. Nothing here touches the DOM. */
(function () {
'use strict';

const key = (px, tick) => Math.round(px / tick);

/* Diagonal imbalances at `ratio`:1, the rule the Footprint layer already draws: buys at P against sells one tick
   below, sells at P against buys one tick above. Returns {buy: Set(key), sell: Set(key)}. ratio <= 0: none. */
function imbalances(fp, tick, ratio) {
  const buy = new Set(), sell = new Set();
  if (!(ratio > 0) || !Array.isArray(fp) || !fp.length) return { buy, sell };
  const at = new Map(fp.map((r) => [key(r[0], tick), r]));
  for (const [px, sv, bv] of fp) {
    const k = key(px, tick), below = at.get(k - 1), above = at.get(k + 1);
    if (bv > 0 && bv >= ratio * Math.max(below ? below[1] : 0, 1)) buy.add(k);
    if (sv > 0 && sv >= ratio * Math.max(above ? above[2] : 0, 1)) sell.add(k);
  }
  return { buy, sell };
}

/* Runs of `stack` or more price rows IN A ROW (no empty row between) that all carry the same side's imbalance:
   [{side: 'buy'|'sell', from: price, to: price, n}], from < to, ascending. */
function stackedRuns(fp, tick, ratio, stack) {
  const need = Math.max(2, Math.floor(stack) || 3), out = [];
  const { buy, sell } = imbalances(fp, tick, ratio);
  for (const [side, set] of [['buy', buy], ['sell', sell]]) {
    const ks = [...set].sort((a, b) => a - b);
    let s = 0;
    for (let i = 1; i <= ks.length; i++) {
      if (i < ks.length && ks[i] === ks[i - 1] + 1) continue;
      const n = i - s;
      if (n >= need) out.push({ side, from: ks[s] * tick, to: ks[i - 1] * tick, n });
      s = i;
    }
  }
  return out.sort((a, b) => a.from - b.from || (a.side < b.side ? -1 : 1));
}

/* Unfinished auction: the bar's top row traded on BOTH sides (the auction did not end with only one side left),
   and the same at the bottom row. A one-sided extreme is finished. {high: bool, low: bool, hi: price, lo: price}. */
function unfinished(fp) {
  if (!Array.isArray(fp) || !fp.length) return { high: false, low: false, hi: null, lo: null };
  let hi = fp[0], lo = fp[0];
  for (const r of fp) { if (r[0] > hi[0]) hi = r; if (r[0] < lo[0]) lo = r; }
  return { high: hi[1] > 0 && hi[2] > 0, low: lo[1] > 0 && lo[2] > 0, hi: hi[0], lo: lo[0] };
}

/* Bubble radius in px for `size` contracts: the area follows the size between `min` and `max` contracts. */
function bubbleRadius(size, min, max, rMin = 3, rMax = 14) {
  if (!(size > 0)) return 0;
  const lo = Math.max(1, min), hi = Math.max(lo + 1, max);
  const t = Math.min(1, Math.max(0, (size - lo) / (hi - lo)));
  return rMin + (rMax - rMin) * Math.sqrt(t);
}

/* A series marker's `size` (Lightweight Charts: 0.5 .. 3) for a print of `size` contracts when the chart scales big
   prints by size: 0.6 at `min`, 2.2 at 8 x `min` and beyond. Off (scale false): 0.6, as always. */
function markerSize(size, min, scale) {
  if (!scale || !(size > 0) || !(min > 0)) return 0.6;
  const t = Math.min(1, Math.max(0, Math.log2(size / min) / 3));
  return Math.round((0.6 + 1.6 * t) * 100) / 100;
}

/* Trade bubbles of one bar for the heatmap: rows [sec, price, size, side] with size >= min, as {t, price, size, side}
   (t = the middle of that second). A bar without `bub` (the chart did not ask for it) gives none. */
function bubblesOf(bar, min) {
  const out = [];
  for (const r of (bar && bar.bub) || []) {
    if (Array.isArray(r) && r[2] >= min) out.push({ t: r[0] * 1000 + 500, price: r[1], size: r[2], side: r[3] });
  }
  return out;
}

/* Sweeps of one bar: rows [ts_ms, from, to, size, side] with size >= min, as {t, from, to, size, side}. */
function sweepsOf(bar, min) {
  const out = [];
  for (const r of (bar && bar.sw) || []) {
    if (Array.isArray(r) && r[3] >= min) out.push({ t: r[0], from: r[1], to: r[2], size: r[3], side: r[4] });
  }
  return out;
}

const api = { imbalances, stackedRuns, unfinished, bubbleRadius, markerSize, bubblesOf, sweepsOf };
if (typeof window !== 'undefined') window.HBFlowMath = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
