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
function runsOf(buy, sell, tick, stack) {
  const need = Math.max(2, Math.floor(stack) || 3), out = [];
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
function stackedRuns(fp, tick, ratio, stack) {
  const { buy, sell } = imbalances(fp, tick, ratio);
  return runsOf(buy, sell, tick, stack);
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
const solid = (b) => real(b) && !b.blank;   // blank slots carry the last close as every price: they never traded, so they cover nothing

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

/* The boxes of the `fvg` study (`key`, e.g. "fvg:0.25:14") among bars[0..upTo]: each run of bars on which one side's
   newest unfilled gap stays the same (uh / ul up, dh / dl down) is one box, from the gap's first bar (two real bars
   before the bar that confirmed it) to the last bar it was still open on. [{side: 1 | -1, from, to, top, bottom}]. */
function fvgBoxes(bars, key, upTo) {
  const n = Math.min(upTo, bars.length - 1), out = [];
  const back = (i, k) => { let j = i; while (k > 0 && j > 0) { j--; if (!bars[j].blank) k--; } return j; };
  for (const [side, hiPart, loPart] of [[1, 'uh', 'ul'], [-1, 'dh', 'dl']]) {
    let start = -1, last = -1, top = null, bottom = null;
    const shut = () => { if (start >= 0) out.push({ side, from: back(start, 2), to: last, top, bottom }); start = -1; };
    for (let i = 0; i <= n; i++) {
      const b = bars[i];
      if (!b || b.blank) continue;                       // a closed hour holds the gap, it does not end it
      const v = b.sv ? b.sv[key] : null, hi = v ? v[hiPart] : null, lo = v ? v[loPart] : null;
      if (hi == null || lo == null) { shut(); continue; }
      if (start >= 0 && (hi !== top || lo !== bottom)) shut();
      if (start < 0) { start = i; top = hi; bottom = lo; }
      last = i;
    }
    shut();
  }
  return out;
}

/* SMT divergences (the server's `smt` values, one on the bar a divergence first shows) among bars[i0..i1 + span]:
   the line each draws on the chart's own market, from the reference's extreme to the window's. `ago` / `aago` count
   real bars back from the bar that carries the value (a blank slot is no bar). [{i, from, to, y0, y1, dir, lead,
   live}], from / to bar indexes; one whose start is left of the first loaded bar is left out. */
function smtLines(bars, i0, i1, key, span = 60) {
  const out = [], back = (i, n) => {
    let j = i;
    while (n > 0 && j > 0) { j--; if (!bars[j].blank) n--; }
    return n > 0 ? -1 : j;
  };
  for (let i = Math.max(i0, 0); i <= Math.min(i1 + span, bars.length - 1); i++) {
    const b = bars[i], v = b && !b.blank && b.sv ? b.sv[key] : null;
    if (!v || !v.dir) continue;
    const to = back(i, v.ago || 0), from = back(i, v.aago || 0);
    if (to < 0 || from < 0 || from >= to) continue;
    out.push({ i, from, to, y0: v.apx, y1: v.px, dir: v.dir, lead: v.lead, live: !!v.live });
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

/* ---- Order-flow app rules (2026-10-21, ofapps.md). Each says which app's rule it follows and where it differs; none is vendor code. ---- */

/* Imbalance presets. ratio is a multiple (3.5 = ATAS 350%); cmp '>=' | '>'; zero: the other side is 0 -> 'one' (compare against 1) | 'skip';
   edge: no row beyond the bar's high / low -> 'one' | 'skip'. `homebase` is imbalances() above, row for row. */
const IMB = {
  homebase: { ratio: 3, cmp: '>=', zero: 'one', edge: 'one' },
  atas: { ratio: 1.5, cmp: '>', zero: 'skip', edge: 'skip' },
  exocharts: { ratio: 2.5, cmp: '>', zero: 'skip', edge: 'skip' },
  sierra: { ratio: 1, cmp: '>', zero: 'skip', edge: 'skip' },
};

/* Diagonal imbalances by a vendor's rule (ATAS, Exocharts, Sierra Numbers Bars; see IMB). opts: {tick (required), preset 'homebase', ratio, cmp,
   zero, edge (each overrides the preset), minVolume 0 (skip a pair whose two sides are both below it: Sierra), minDiff 0 (own side minus the other
   at least this: ATAS), stack 3 (rows in a row for runs, 0 = none)}. A gap row inside the bar counts as a zero row; "edge" is only beyond the bar's
   extremes. Differs: one comparison for both sides (Sierra's ask side is '>=' in its colour logic), no colour bands, one ratio level.
   -> {rows: [{price, bid, ask, buy, sell}] ascending, buy: Set(key), sell: Set(key), runs: stackedRuns-shaped}. */
function imbalancesV2(fp, opts = {}) {
  const buy = new Set(), sell = new Set(), tick = opts.tick;
  const o = { ...IMB.homebase, ...IMB[opts.preset] };
  for (const k of ['ratio', 'cmp', 'zero', 'edge']) if (opts[k] != null) o[k] = opts[k];
  if (!Array.isArray(fp) || !fp.length || !(o.ratio > 0) || !(tick > 0)) return { rows: [], buy, sell, runs: [] };
  const at = new Map(fp.map((r) => [key(r[0], tick), r])), minV = opts.minVolume || 0, minD = opts.minDiff || 0;
  let lo = Infinity, hi = -Infinity;
  for (const k of at.keys()) { if (k < lo) lo = k; if (k > hi) hi = k; }
  const flag = (own, nb, beyond, col) => {
    if (!(own > 0)) return false;
    const other = nb ? nb[col] : 0;
    if ((!nb && beyond ? o.edge : other === 0 ? o.zero : 'n') === 'skip') return false;
    if (own < minV && other < minV) return false;
    if (own - other < minD) return false;
    return o.cmp === '>' ? own > o.ratio * Math.max(other, 1) : own >= o.ratio * Math.max(other, 1);
  };
  const rows = [...fp].sort((a, b) => a[0] - b[0]).map(([price, bid, ask]) => {
    const k = key(price, tick);
    const b = flag(ask, at.get(k - 1), k - 1 < lo, 1), s = flag(bid, at.get(k + 1), k + 1 > hi, 2);
    if (b) buy.add(k);
    if (s) sell.add(k);
    return { price, bid, ask, buy: b, sell: s };
  });
  const st = opts.stack == null ? 3 : opts.stack;
  return { rows, buy, sell, runs: st > 0 ? runsOf(buy, sell, tick, st) : [] };
}

/* Value area + POC of `rows` [[price, volume]] ascending, `pct` 1-100. method 'homebase' = the server's profile_from (POC ties -> the lowest row, one
   row at a time toward the heavier neighbour, a tie -> the upper); 'sierra' = Sierra Chart (POC ties -> the row nearest the profile's middle, then the
   lower; a tie between the neighbours adds BOTH; stops once the share is reached); 'tv' = homebase's walk that stops BEFORE a row would take the area
   past the share (read from TradingView's wording, not run against it; POC ties -> lowest). Pass `tick` and sierra / tv count the empty prices between
   rows as zero rows. Differs: no "count 2 levels at a time". -> {poc, vah, val} | null. */
function valueAreaV2(rows, pct, method = 'homebase', tick) {
  if (!Array.isArray(rows) || !rows.length) return null;
  let g = rows;
  if (method !== 'homebase' && tick > 0) {
    const m = new Map(rows.map((r) => [key(r[0], tick), r])), a = key(rows[0][0], tick), z = key(rows[rows.length - 1][0], tick);
    g = [];
    for (let k = a; k <= z; k++) g.push(m.get(k) || [+(k * tick).toFixed(6), 0]);
  }
  let at = 0;
  if (method === 'sierra') {
    const mid = (g[0][0] + g[g.length - 1][0]) / 2;
    let best = -1, bd = Infinity;
    g.forEach((r, i) => {
      const d = Math.abs(r[0] - mid);
      if (r[1] > best || (r[1] === best && d < bd - 1e-9)) { best = r[1]; bd = d; at = i; }
    });
  } else g.forEach((r, i) => { if (r[1] > g[at][1]) at = i; });
  const total = g.reduce((t, r) => t + r[1], 0), want = (Math.min(100, Math.max(1, pct)) / 100) * total;
  let lo = at, hi = at, acc = g[at][1];
  while (acc < want && (lo > 0 || hi < g.length - 1)) {
    const up = hi < g.length - 1 ? g[hi + 1][1] : -1, dn = lo > 0 ? g[lo - 1][1] : -1;
    if (method === 'sierra' && up === dn) { hi++; lo--; acc += up + dn; continue; }
    const goUp = up >= dn, add = goUp ? up : dn;
    if (method === 'tv' && acc + add > want) break;
    if (goUp) hi++; else lo--;
    acc += add;
  }
  return { poc: g[at][0], vah: g[hi][0], val: g[lo][0] };
}

/* Naked POCs among bars[i0..i1] (Exocharts "naked POC", MotiveWave's naked POC): a bar's POC (its busiest 1-tick row, ties -> the lowest) that no
   LATER bar's range [low, high] has reached yet. Differs: "traded through" is read from the later bar's range, not its rows. Needs `fp`.
   `touched` true: the POCs a later bar did reach come too, each with `hit` = that first bar's index (null while naked), so the line can be drawn up
   to it. -> [{i, price, vol}] (touched: + hit). */
function nakedPocs(bars, i0 = 0, i1 = bars.length - 1, touched = false) {
  const out = [];
  for (let i = Math.max(i0, 0); i <= Math.min(i1, bars.length - 1); i++) {
    const b = bars[i];
    if (!solid(b) || !Array.isArray(b.fp) || !b.fp.length) continue;
    let poc = b.fp[0], best = poc[1] + poc[2];
    for (const r of b.fp) { const v = r[1] + r[2]; if (v > best || (v === best && r[0] < poc[0])) { poc = r; best = v; } }
    let hit = null;
    for (let j = i + 1; j < bars.length && hit == null; j++) if (solid(bars[j]) && bars[j].l <= poc[0] && poc[0] <= bars[j].h) hit = j;
    if (hit != null && !touched) continue;
    out.push(touched ? { i, price: poc[0], vol: best, hit } : { i, price: poc[0], vol: best });
  }
  return out;
}

const letterOf = (i) => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'[((i % 52) + 52) % 52];

/* TPO profile of `bars` (one session, ascending, each with `ms`, `h`, `l`, optional `fp`): sub-periods of `periodMin` minutes counted from the first
   bar get the letters A, B, ... (Sierra, MotiveWave, ATAS). mode 'range' marks every row from a period's low to its high (Sierra); 'traded' only the
   rows traded in it (MotiveWave; a bar without `fp` counts its range). rowTicks ticks to a row, price = the row's bottom. o: {tick (required), ib 2
   (sub-periods of the initial balance), va 70, method 'sierra' (valueAreaV2 on the TPO counts)}. Differs: no RTH / ETH split, no open / close marks.
   -> {periodMs, origin, periods, rows: [{price, per: [period index], n}] ascending, poc, vah, val, ib: {hi, lo} | null, singles: [price]} | null. */
function tpo(bars, periodMin, rowTicks, mode, o = {}) {
  const tick = o.tick, rt = Math.max(1, Math.floor(rowTicks) || 1), pm = Math.max(1, +periodMin || 30) * 60000;
  const list = (bars || []).filter((b) => solid(b) && Number.isFinite(b.ms));
  if (!(tick > 0) || !list.length) return null;
  const origin = list[0].ms, hit = new Map(), span = new Map();
  let periods = 0;
  const put = (kb, p) => { let s = hit.get(kb); if (!s) hit.set(kb, s = new Set()); s.add(p); };
  for (const b of list) {
    const p = Math.max(0, Math.floor((b.ms - origin) / pm));
    periods = Math.max(periods, p + 1);
    if (mode === 'traded' && Array.isArray(b.fp) && b.fp.length) { for (const r of b.fp) put(Math.floor(key(r[0], tick) / rt), p); continue; }
    const s = span.get(p) || { lo: Infinity, hi: -Infinity };
    s.lo = Math.min(s.lo, key(b.l, tick)); s.hi = Math.max(s.hi, key(b.h, tick)); span.set(p, s);
  }
  for (const [p, s] of span) for (let kb = Math.floor(s.lo / rt); kb <= Math.floor(s.hi / rt); kb++) put(kb, p);
  const rows = [...hit.keys()].sort((a, b) => a - b).map((kb) => {
    const per = [...hit.get(kb)].sort((a, b) => a - b);
    return { price: +(kb * rt * tick).toFixed(6), per, n: per.length };
  });
  const ibN = o.ib == null ? 2 : o.ib, inIb = rows.filter((r) => r.per[0] < ibN);
  const va = valueAreaV2(rows.map((r) => [r.price, r.n]), o.va || 70, o.method || 'sierra', tick * rt);
  return {
    periodMs: pm, origin, periods, rows, ...va,
    ib: inIb.length ? { hi: inIb[inIb.length - 1].price, lo: inIb[0].price } : null,
    singles: rows.filter((r) => r.n === 1).map((r) => r.price),
  };
}

/* Aggressor orders of one bar (the wire's `ag` rows [ts_ms, vwap, lo, hi, size, side, prints]) with min <= size (<= max when max > 0) and, for side
   'buy' / 'sell', only that aggressor (ATAS / MotiveWave "big trades" on the rebuilt order). A bar without `ag` gives []. -> [{t, price, lo, hi,
   size, side, n}] in the wire's order (time). */
function ordersOf(bar, min, max = 0, side = 'all') {
  const out = [], top = max > 0 ? max : Infinity;
  for (const r of (bar && bar.ag) || []) {
    if (!Array.isArray(r) || !(r[4] >= min) || r[4] > top) continue;
    if (side === 'buy' && !(r[5] > 0)) continue;
    if (side === 'sell' && !(r[5] < 0)) continue;
    out.push({ t: r[0], price: r[1], lo: r[2], hi: r[3], size: r[4], side: r[5], n: r[6] });
  }
  return out;
}

/* Bookmap's traded-volume clustering over time-ordered orders (ordersOf rows). mode 'none' keeps each; 'volume' (the dots rule: a cluster closes when
   the running volume reaches `thr`, its size is the whole multiple of `thr` and the remainder carries on); 'overshoot' (the bars rule: closes at
   `thr` or more with the whole volume, carry 0); 'price' (until the price changes); 'priceside' (until the price or the aggressor changes). The
   volume modes leave an unfinished remainder out. Differs: "Smart" mode is not public, so not built; price is the order's vwap.
   -> [{t, t1 (first / last order), price (size-weighted), lo, hi, size, buy, sell, side (the larger; a tie = buy), count, carry (volume modes)}]. */
function clusterOrders(list, mode, thr) {
  const out = [], rows = list || [];
  const join = (g, size, carry) => {
    let buy = 0, sell = 0, w = 0, tot = 0, lo = Infinity, hi = -Infinity;
    for (const o of g) { if (o.side > 0) buy += o.size; else sell += o.size; w += o.price * o.size; tot += o.size; lo = Math.min(lo, o.lo); hi = Math.max(hi, o.hi); }
    const c = { t: g[0].t, t1: g[g.length - 1].t, price: w / tot, lo, hi, size: size == null ? tot : size, buy, sell, side: buy >= sell ? 1 : -1, count: g.length };
    if (carry != null) c.carry = carry;
    return c;
  };
  if ((mode === 'volume' || mode === 'overshoot') && thr > 0) {
    let acc = 0, g = [];
    for (const o of rows) {
      g.push(o); acc += o.size;
      if (acc < thr) continue;
      const size = mode === 'volume' ? Math.floor(acc / thr) * thr : acc;
      out.push(join(g, size, acc - size));
      acc -= size; g = [];
    }
  } else if (mode === 'price' || mode === 'priceside') {
    let g = [];
    for (const o of rows) {
      const p = g[g.length - 1];
      if (p && (Math.abs(o.price - p.price) > 1e-9 || (mode === 'priceside' && o.side !== p.side))) { out.push(join(g)); g = []; }
      g.push(o);
    }
    if (g.length) out.push(join(g));
  } else for (const o of rows) out.push(join([o]));
  return out;
}

/* One bar's cluster statistics (ATAS Cluster Statistic, Bookmap footprint stats): delta, volume, trades (the sum of `fpn`, else `n`), the highest and
   lowest running delta inside the bar (`dmax`, `dmin`), delta / volume, duration = ms from this bar's start to `nextMs` (the next bar's; null when
   unknown). A field the bar lacks is null, never 0. */
function clusterStats(bar, nextMs) {
  const b = bar || {}, num = (v) => (Number.isFinite(v) ? v : null);
  const trades = Array.isArray(b.fpn) && b.fpn.length ? b.fpn.reduce((t, r) => t + r[1] + r[2], 0) : num(b.n);
  return {
    delta: num(b.d), volume: num(b.v), trades, maxDelta: num(b.dmax), minDelta: num(b.dmin),
    deltaPct: Number.isFinite(b.d) && b.v > 0 ? b.d / b.v : null,
    duration: Number.isFinite(nextMs) && Number.isFinite(b.ms) ? nextMs - b.ms : null,
  };
}

/* Delta Turnaround among bars[i0..i1] (ATAS, as its page words it): UP = two bearish bars, then a bullish bar with delta > 0 and a low at or below the
   bar before's low; DOWN = two bullish bars, then a bearish bar with delta < 0 and a high at or above the bar before's LOW (as written, likely a slip
   for its high); o.fix uses that bar's high. -> [{i, dir: 1 | -1, price (the bar's low for up, high for down), delta}]. */
function deltaTurnaround(bars, i0, i1, o = {}) {
  const out = [];
  for (let i = Math.max(i0, 2); i <= Math.min(i1, bars.length - 1); i++) {
    const a = bars[i - 2], p = bars[i - 1], b = bars[i];
    if (!solid(a) || !solid(p) || !solid(b) || !Number.isFinite(b.d)) continue;
    if (a.c < a.o && p.c < p.o && b.c > b.o && b.d > 0 && b.l <= p.l) out.push({ i, dir: 1, price: b.l, delta: b.d });
    else if (a.c > a.o && p.c > p.o && b.c < b.o && b.d < 0 && b.h >= (o.fix ? p.h : p.l)) out.push({ i, dir: -1, price: b.h, delta: b.d });
  }
  return out;
}

/* Delta Strength among bars[i0..i1] (ATAS): a bar whose closing delta is between o.min and o.max percent (defaults 80 and 100) of its own best delta
   (`dmax` when the delta is positive, `dmin` when negative) is marked. A bar without dmax / dmin is skipped. -> [{i, dir: 1 | -1, pct}]. */
function deltaStrength(bars, i0, i1, o = {}) {
  const lo = o.min == null ? 80 : o.min, hi = o.max == null ? 100 : o.max, out = [];
  for (let i = Math.max(i0, 0); i <= Math.min(i1, bars.length - 1); i++) {
    const b = bars[i];
    if (!solid(b) || !Number.isFinite(b.d) || b.d === 0) continue;
    const best = b.d > 0 ? b.dmax : b.dmin;
    if (!Number.isFinite(best) || best === 0) continue;
    const pct = 100 * b.d / best;
    if (pct >= lo && pct <= hi) out.push({ i, dir: b.d > 0 ? 1 : -1, pct });
  }
  return out;
}

/* Absorption among bars[i0..i1] (MotiveWave Volume Imprint): an imbalance whose price a bar's CLOSE then leaves by `ticks` ticks the other way, on the bar
   itself or the next `within` bars. Buy side: the bar's highest buy imbalance P, absorbed once a close is <= P - ticks; sell side: its lowest sell
   imbalance, once a close is >= P + ticks. One mark per bar and side. o: {tick (required), ticks 4, within 3, imb: imbalancesV2 opts}. Differs:
   `within` is ours (the page gives none). -> [{i, j (the confirming bar), dir (the way price turned: -1 down after buyers, 1 up after sellers), price}]. */
function mwAbsorptions(bars, i0, i1, o = {}) {
  const tick = o.tick, n = o.ticks == null ? 4 : o.ticks, w = o.within == null ? 3 : o.within, out = [];
  if (!(tick > 0)) return out;
  for (let i = Math.max(i0, 0); i <= Math.min(i1, bars.length - 1); i++) {
    const b = bars[i];
    if (!solid(b) || !Array.isArray(b.fp) || !b.fp.length) continue;
    const { rows } = imbalancesV2(b.fp, { stack: 0, ...o.imb, tick });
    const top = rows.filter((r) => r.buy).pop(), bot = rows.find((r) => r.sell);
    // tick keys, not float prices: 2000.3 - 4 * 0.1 is 1999.8999999999999, so a close of 1999.9 (exactly 4 ticks) would miss
    for (let j = i; j <= Math.min(i + w, bars.length - 1); j++) {
      const x = bars[j];
      if (!solid(x)) continue;
      if (top && key(top.price, tick) - key(x.c, tick) >= n) { out.push({ i, j, dir: -1, price: top.price }); break; }
    }
    for (let j = i; j <= Math.min(i + w, bars.length - 1); j++) {
      const x = bars[j];
      if (!solid(x)) continue;
      if (bot && key(x.c, tick) - key(bot.price, tick) >= n) { out.push({ i, j, dir: 1, price: bot.price }); break; }
    }
  }
  return out;
}

/* Sierra Numbers Bars text for one footprint row [price, sells at bid, buys at ask] beyond the three modes the Footprint always had. mode 'trades' (Bid x
   Ask of print counts; o.trades = the row's [price, sell prints, buy prints]), 'dom' (Dominant Side %: the larger side's share of the row, + when the
   ask leads, - when the bid leads, a tie +), 'price' (o.dec decimals), 'diag' (diagonal differences: left = Ask(P+1) - Bid(P), right = Ask(P) -
   Bid(P-1), 0 when that neighbour row does not exist; o.above / o.below = the neighbour rows). Differs: whole percents, no colour bands.
   -> {l, r} (two figures) | {c} (one) | {} (the row lacks what the mode needs). */
function rowText(mode, row, o = {}) {
  const [px, sv, bv] = row;
  if (mode === 'trades') return o.trades ? { l: String(o.trades[1]), r: String(o.trades[2]) } : {};
  if (mode === 'dom') { const t = sv + bv; return t > 0 ? { c: `${bv >= sv ? '+' : '-'}${Math.round(100 * Math.max(sv, bv) / t)}` } : {}; }
  if (mode === 'price') return { c: px.toFixed(o.dec == null ? 2 : o.dec) };
  if (mode === 'diag') return { l: String(o.above ? o.above[2] - sv : 0), r: String(o.below ? bv - o.below[1] : 0) };
  return {};
}

const api = { imbalances, stackedRuns, unfinished, bubbleRadius, markerSize, bubblesOf, sweepsOf, stopRuns, exhaustions, smtLines, fvgBoxes, valueArea,
  IMB, imbalancesV2, valueAreaV2, nakedPocs, letterOf, tpo, ordersOf, agOf: ordersOf, clusterOrders, clusterStats, deltaTurnaround, deltaStrength, mwAbsorptions, rowText };
if (typeof window !== 'undefined') window.HBFlowMath = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
