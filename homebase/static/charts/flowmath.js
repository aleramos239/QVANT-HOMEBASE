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

/* Trade bubbles of one bar for the heatmap: rows [sec, price, size, side] with min <= size (<= max when max > 0) and,
   for side 'buy' / 'sell', only that aggressor (+1 lifted the offer, -1 hit the bid), as {t, price, size, side}
   (t = the middle of that second). A bar without `bub` (the chart did not ask for it) gives none. */
function bubblesOf(bar, min, max = 0, side = 'all') {
  const out = [], top = max > 0 ? max : Infinity;
  for (const r of (bar && bar.bub) || []) {
    if (!Array.isArray(r) || !(r[2] >= min) || r[2] > top) continue;
    if (side === 'buy' && !(r[3] > 0)) continue;
    if (side === 'sell' && !(r[3] < 0)) continue;
    out.push({ t: r[0] * 1000 + 500, price: r[1], size: r[2], side: r[3] });
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

const real = (b) => !!b && Number.isFinite(b.h) && Number.isFinite(b.l);   // a blank slot (a closed hour) has no prices

/* Stop runs among bars[i0..i1]: bar i trades through the highest high (or lowest low) of the `len` bars before it
   while sweeps (one aggressor walking several prices) that reach beyond that level add up to `min` contracts or
   more -- the burst that takes the stops resting there. Needs the bars' `sw` (the chart's flow data); a bar
   without it is never a run. [{i, from, side: 1 (up) | -1 (down), level, size, held}]: `from` the swing's bar,
   `held` = the bar closed beyond the level (false: it was pushed straight back, a trap). */
function stopRuns(bars, i0, i1, len, min) {
  const n = Math.max(2, Math.floor(len) || 20), out = [];
  for (let i = Math.max(i0, 1); i <= Math.min(i1, bars.length - 1); i++) {
    const b = bars[i];
    if (!real(b) || !Array.isArray(b.sw) || !b.sw.length) continue;
    let hi = -Infinity, lo = Infinity, hiAt = -1, loAt = -1;
    for (let j = Math.max(0, i - n); j < i; j++) {
      const x = bars[j];
      if (!real(x)) continue;
      if (x.h > hi) { hi = x.h; hiAt = j; }
      if (x.l < lo) { lo = x.l; loAt = j; }
    }
    if (hiAt < 0) continue;
    let up = 0, down = 0;
    for (const w of sweepsOf(b, 1)) {
      const top = Math.max(w.from, w.to), bottom = Math.min(w.from, w.to);
      if (w.side > 0 && top > hi) up += w.size;
      if (w.side < 0 && bottom < lo) down += w.size;
    }
    if (b.h > hi && up >= min) out.push({ i, from: hiAt, side: 1, level: hi, size: up, held: b.c > hi });
    if (b.l < lo && down >= min) out.push({ i, from: loAt, side: -1, level: lo, size: down, held: b.c < lo });
  }
  return out;
}

/* Exhaustion among bars[i0..i1]: bar `at` pushes to a new extreme of the `len` bars before it on a delta of `mult`
   x their average |delta| or more, the next `wait` bars make no new extreme, and the last of them closes back past
   the push bar's midpoint -- the aggression went nowhere and was given back. Only confirmed ones (all `wait` bars
   are in). [{i: the confirming bar, at: the push bar, dir: -1 (buyers spent: price turns down) | 1, level: the
   extreme, delta}]. */
function exhaustions(bars, i0, i1, len, mult, wait) {
  const n = Math.max(2, Math.floor(len) || 20), w = Math.max(1, Math.floor(wait) || 3), out = [];
  for (let at = Math.max(i0 - w, 1); at <= Math.min(i1 - w, bars.length - 1 - w); at++) {
    const b = bars[at];
    if (!real(b) || !Number.isFinite(b.d) || b.d === 0) continue;
    let hi = -Infinity, lo = Infinity, sum = 0, k = 0;
    for (let j = Math.max(0, at - n); j < at; j++) {
      const x = bars[j];
      if (!real(x) || !Number.isFinite(x.d)) continue;
      if (x.h > hi) hi = x.h;
      if (x.l < lo) lo = x.l;
      sum += Math.abs(x.d); k++;
    }
    if (k < Math.min(n, 5) || !(sum > 0) || Math.abs(b.d) < mult * (sum / k)) continue;
    const mid = (b.h + b.l) / 2, up = b.d > 0;
    if (up ? !(b.h >= hi) : !(b.l <= lo)) continue;
    let ok = true;
    for (let j = at + 1; j <= at + w && ok; j++) {
      const x = bars[j];
      if (!real(x) || (up ? x.h > b.h : x.l < b.l)) ok = false;
    }
    const last = bars[at + w];
    if (ok && (up ? last.c < mid : last.c > mid)) out.push({ i: at + w, at, dir: up ? -1 : 1, level: up ? b.h : b.l, delta: b.d });
  }
  return out;
}

/* The value area of a volume profile: `rows` [[price, volume]] sorted ascending, `poc` the busiest price, `pct` the
   share of the volume to cover (1-100). From the POC it takes the heavier of the next two rows above / below until
   the share is covered: {vah, val}. */
function valueArea(rows, poc, pct) {
  if (!Array.isArray(rows) || !rows.length) return null;
  let at = rows.findIndex((r) => r[0] === poc);
  if (at < 0) { let best = 0; rows.forEach((r, i) => { if (r[1] > rows[best][1]) best = i; }); at = best; }
  const total = rows.reduce((t, r) => t + r[1], 0), want = total * Math.min(100, Math.max(1, pct)) / 100;
  let lo = at, hi = at, got = rows[at][1];
  while (got < want && (lo > 0 || hi < rows.length - 1)) {
    const up = hi < rows.length - 1 ? rows[hi + 1][1] + (hi + 2 < rows.length ? rows[hi + 2][1] : 0) : -1;
    const dn = lo > 0 ? rows[lo - 1][1] + (lo - 2 >= 0 ? rows[lo - 2][1] : 0) : -1;
    if (up >= dn && up >= 0) { hi++; got += rows[hi][1]; if (got < want && hi < rows.length - 1) { hi++; got += rows[hi][1]; } }
    else if (dn >= 0) { lo--; got += rows[lo][1]; if (got < want && lo > 0) { lo--; got += rows[lo][1]; } }
    else break;
  }
  return { vah: rows[hi][0], val: rows[lo][0] };
}

const api = { imbalances, stackedRuns, unfinished, bubbleRadius, markerSize, bubblesOf, sweepsOf, stopRuns, exhaustions, valueArea };
if (typeof window !== 'undefined') window.HBFlowMath = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
