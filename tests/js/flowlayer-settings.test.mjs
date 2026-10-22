import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const require = createRequire(import.meta.url);
const DIR = new URL('../../homebase/static/charts/', import.meta.url).pathname;
const REPO = new URL('../../', import.meta.url).pathname;
const C = require(DIR + 'catalog.js');
const SET = require(DIR + 'flowdefs.js').settings;
const T0 = 1_700_000_000_000, BAR = 15 * 60_000;

/* Settings of the canvas-drawn order-flow layers (flowlayer.js, flowmath.js, indstatus.js): the Style tab's colours and the extra Inputs.
   The pre-change files come from git (HEAD) and are loaded beside the new ones: with no style and every setting at its default (or missing, or junk)
   the canvas calls must be the same, call for call. */
const OLD = {
  layer: execFileSync('git', ['show', 'e29a6928:homebase/static/charts/flowlayer.js'], { cwd: REPO, encoding: 'utf8' }),
  math: execFileSync('git', ['show', 'e29a6928:homebase/static/charts/flowmath.js'], { cwd: REPO, encoding: 'utf8' }),
};
const NEW = { layer: readFileSync(DIR + 'flowlayer.js', 'utf8'), math: readFileSync(DIR + 'flowmath.js', 'utf8') };
const loadMath = (src) => { const m = { exports: {} }; new Function('module', src)(m); return m.exports; };
const MATH = { old: loadMath(OLD.math), now: loadMath(NEW.math) };

/* A recording canvas: every method call and every property set, in order. */
function recorder() {
  const log = [], t = {};
  const ctx = new Proxy(t, {
    get: (o, k) => (k in o ? o[k] : (...a) => { log.push([String(k), ...a]); }),
    set: (o, k, v) => { o[k] = v; log.push(['set', String(k), v]); return true; },
  });
  return { ctx, log };
}

/* One flow overlay on a stub chart: bar i at x = i * step, price p at y = 1000 - 40 p. */
function rig(which, indicators, bars, { step = 50, P } = {}) {
  class Layer { constructor(p) { this.P = p; } redraw() {} }
  const win = { HBLayers: { Layer }, HBLiquidity: require(DIR + 'liquidity.js'), HBDrawings: require(DIR + 'drawings.js'), HBFlowMath: MATH[which], HBCatalog: C };
  new Function('window', (which === 'old' ? OLD : NEW).layer)(win);
  const n = bars.length;
  const cell = {
    cfg: { root: 'NQ', indicators }, P: P || PAL, tick: 0.25, bars, isTime: () => true, barMs: () => BAR,
    chart: { timeScale: () => ({ getVisibleLogicalRange: () => ({ from: 0, to: n - 1 }), logicalToCoordinate: (i) => i * step,
      subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} }) },
    candles: { attachPrimitive() {}, detachPrimitive() {}, priceToCoordinate: (p) => 1000 - p * 40 },
  };
  return { o: win.HBFlowLayer.overlay(cell), cell };
}
const PAL = { up: '#089981', down: '#F23645', poc: '#F7A600', text: '#0F0F0F', text2: '#787B86', bg: '#FFFFFF', vaIn: 'rgba(41,98,255,.28)' };
const LAYER = { heatmap: 'bub', bigprints: 'swp', stoprun: 'run', exhaust: 'run', smt: 'run', fvg: 'fvg', bigtrades: 'ord', npoc: 'npoc', tpo: 'tpo', cstat: 'stat',
  dturn: 'mark', dstr: 'mark', mwabs: 'mark' };

/* The default Inputs of an indicator, and the same without the keys this change added (what a chart saved before holds). */
const defs = (id) => Object.fromEntries(C.CATALOG.find((d) => d.id === id).params.map((q) => [q.key, q.def]));
const NEWKEYS = (id) => new Set(((SET[id] && SET[id].params) || []).map((q) => q.key));
const OLDKEYS = { heatmap: ['map', 'bubbles', 'bubbleMin', 'bubbleMax', 'bubbleSide', 'contrast', 'palette'] };
const oldParams = (id) => {
  const d = defs(id), keep = OLDKEYS[id];
  return Object.fromEntries(Object.entries(d).filter(([k]) => (keep ? keep.includes(k) : !NEWKEYS(id).has(k) || k === 'labels' || k === 'size')));
};
const ON = { heatmap: { bubbles: true, bubbleMin: 5 }, bigprints: { sweeps: true, min: 10 }, bigtrades: { min: 10 }, stoprun: { length: 5, minSize: 10 },
  exhaust: { length: 8, multiple: 2, wait: 2 }, smt: { window: 2, reference: 4 }, fvg: {}, dstr: { min: 60 }, mwabs: { ticks: 2, within: 3 } };

/* A deterministic busy tape: every kind of mark appears somewhere in it. */
function tape(n = 40) {
  let s = 12345;
  const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  const bars = [];
  let px = 100;
  for (let i = 0; i < n; i++) {
    const o = px, mv = (rnd() - 0.5) * 3, c = Math.round((o + mv) * 4) / 4;
    const h = Math.max(o, c) + Math.round(rnd() * 3) / 4, l = Math.min(o, c) - Math.round(rnd() * 3) / 4;
    const d = Math.round((c - o) * 40 + (rnd() - 0.5) * 30), ms = T0 + i * BAR;
    const fp = [];
    for (let p = l; p <= h + 1e-9; p += 0.25) fp.push([Math.round(p * 4) / 4, Math.round(rnd() * 20 + (p < c ? 12 : 0)), Math.round(rnd() * 20 + (p > o ? 12 : 0))]);
    const b = { ms, s: 'a', o, h, l, c, v: 200 + i, d, n: 50 + i, dmax: Math.abs(d) + 5 + Math.round(rnd() * 10) * (d >= 0 ? 1 : 0), dmin: -Math.abs(d) - 5, fp };
    b.dmin = d < 0 ? d - Math.round(rnd() * 5) : -Math.round(rnd() * 20);
    b.dmax = d > 0 ? d + Math.round(rnd() * 5) : Math.round(rnd() * 20);
    b.bub = [[ms / 1000 + 10, Math.round((l + rnd()) * 4) / 4, 5 + Math.round(rnd() * 120), rnd() < 0.5 ? 1 : -1], [ms / 1000 + 20, h, 40, 1], [ms / 1000 + 30, l, 400, -1]];
    b.ag = [[ms + 1000, c, c, c, 12 + Math.round(rnd() * 90), rnd() < 0.5 ? 1 : -1, 3], [ms + 2000, c, c, c, 150, 1, 4], [ms + 3000, l, l, l, 60, -1, 2]];
    b.sw = [[ms + 5000, l, h + 1, 40 + Math.round(rnd() * 200), 1], [ms + 6000, h, l - 1, 25 + Math.round(rnd() * 200), -1], [ms + 7000, c, c + 0.5, 8, 1]];
    b.big = [[ms + 100, c, 30, 1]];
    b.sv = { 'smt:2:4': i % 6 === 5 ? { dir: i % 12 === 5 ? -1 : 1, ago: 1, px: h, aago: 4, apx: h - 1, lead: i % 4 === 1 ? 1 : -1, live: i % 3 === 0 } : null,
      'fvg:0.25:14': i >= 3 && i < 20 ? { uh: 101 + (i > 12 ? 1 : 0), ul: 100.5, dh: null, dl: null } : (i >= 25 ? { uh: null, ul: null, dh: 99, dl: 98 } : null) };
    bars.push(b);
    px = c;
  }
  // an exhaustion: a huge up-push to a new high on a big delta, then 2 bars going nowhere, the last closing under the push bar's middle
  for (let i = 18; i < 30; i++) Object.assign(bars[i], { o: 100, c: 100, h: 101, l: 99, d: i % 2 ? 10 : -10, dmax: 12, dmin: -12 });
  const at = 30;
  Object.assign(bars[at], { o: 100, c: 105, h: 105.5, l: 99.5, d: 900 });
  for (let k = 1; k <= 2; k++) Object.assign(bars[at + k], { o: 104, h: 105, l: 102, c: k === 2 ? 102 : 104.5, d: 3 });
  // a delta turnaround: two bearish bars, then a bullish one with delta > 0 and a lower low
  Object.assign(bars[10], { o: 103, c: 102, h: 103.5, l: 101.5 }); Object.assign(bars[11], { o: 102, c: 101, h: 102.5, l: 100.5 });
  Object.assign(bars[12], { o: 101, c: 102, h: 102.5, l: 100, d: 40, dmax: 44, dmin: -3 });
  Object.assign(bars[13], { o: 102, c: 103, h: 103.5, l: 101.5 }); Object.assign(bars[14], { o: 103, c: 104, h: 104.5, l: 102.5 });
  Object.assign(bars[15], { o: 104, c: 103, h: 104.5, l: 102, d: -25, dmax: 2, dmin: -26 });
  return bars;
}
const BARS = tape();

function draw(which, id, params, { style, extra, bars = BARS, step, P, pre } = {}) {
  const ind = { id, visible: true, params, ...(style ? { style } : {}) };
  const r = rig(which, [...(extra || []), ind], bars, { step, P });
  const out = [];
  try {
    r.o.sync();
    if (pre) pre(r);
    const layer = r.o[LAYER[id]] || r.o.bub;
    const { ctx, log } = recorder();
    layer.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 2000, height: 500 } }) });
    out.push(...log);
    out.z = layer.z();
  } finally { r.o.destroy(); }
  return out;
}
const same = (id, params, opts) => ({ old: draw('old', id, params, opts), now: draw('now', id, params, opts) });
const calls = (log, name) => log.filter((c) => c[0] === name);
const sets = (log, key) => log.filter((c) => c[0] === 'set' && c[1] === key).map((c) => c[2]);
const style = (key, color, alpha) => ({ [key]: alpha == null ? { color } : { color, alpha } });
const rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;

const IDS = Object.keys(LAYER);

// ------------------------------------------------------------------ (a) default byte identity

test('default: every layer makes the same canvas calls as before, with the defaults, with the new keys missing, and with junk', () => {
  for (const id of IDS) {
    const base = { ...ON[id] };
    const sets_ = [
      ['defaults', { ...defs(id), ...base }],
      ['old keys only', { ...oldParams(id), ...base }],
      ['junk', { ...Object.fromEntries([...NEWKEYS(id)].map((k) => [k, k.startsWith('show') ? 'x' : 'abc'])), ...oldParams(id), ...base }],
    ];
    for (const [what, params] of sets_) {
      const { old, now } = same(id, params);
      assert.ok(old.length > 0, `${id}: the scenario draws something`);
      assert.deepEqual(now, old, `${id} (${what})`);
    }
  }
});

test('default: the scenario really reaches the marks (so the identity above is not about empty logs)', () => {
  const n = (id, name) => calls(draw('now', id, { ...defs(id), ...ON[id] }), name).length;
  assert.ok(n('heatmap', 'arc') > 5);
  assert.ok(n('bigprints', 'closePath') > 5);
  assert.ok(n('bigtrades', 'arc') > 5 && n('bigtrades', 'fillText') > 0);
  assert.ok(n('stoprun', 'closePath') > 0);
  assert.ok(n('exhaust', 'closePath') > 0);
  assert.ok(n('smt', 'arc') > 0 && n('smt', 'fillText') > 0);
  assert.ok(n('fvg', 'fillRect') > 0 && n('fvg', 'strokeRect') > 0);
  assert.ok(n('npoc', 'stroke') > 0);
  assert.ok(n('tpo', 'fillText') > 0 && n('tpo', 'strokeRect') > 0);
  assert.ok(n('cstat', 'fillText') > 7);
  assert.ok(n('dturn', 'fill') > 0 && n('dstr', 'stroke') > 0 && n('mwabs', 'arc') > 0);
});

test('default: the unchanged numbers still come out of flowmath (marker size, stop runs, exhaustion, turnaround)', () => {
  const O = MATH.old, N = MATH.now;
  assert.equal(Math.log2(8), 3);
  for (const size of [1, 9, 10, 11, 14, 19.5, 20, 33, 79.9, 80, 81, 9999]) for (const min of [1, 10, 25]) for (const scale of [true, false]) {
    assert.equal(N.markerSize(size, min, scale), O.markerSize(size, min, scale), `${size}/${min}/${scale}`);
    assert.equal(N.markerSize(size, min, scale, {}), O.markerSize(size, min, scale));
    assert.equal(N.markerSize(size, min, scale, { markerMin: 0.6, markerMax: 2.2, fullAt: 8 }), O.markerSize(size, min, scale));
    assert.equal(N.markerSize(size, min, scale, { markerMin: 'x', markerMax: null, fullAt: NaN }), O.markerSize(size, min, scale));
  }
  assert.deepEqual(N.stopRuns(BARS, 0, 39, 5, 10), O.stopRuns(BARS, 0, 39, 5, 10));
  assert.deepEqual(N.exhaustions(BARS, 0, 39, 8, 2, 2), O.exhaustions(BARS, 0, 39, 8, 2, 2));
  assert.deepEqual(N.deltaTurnaround(BARS, 0, 39, {}), O.deltaTurnaround(BARS, 0, 39, {}));
  assert.deepEqual(N.deltaTurnaround(BARS, 0, 39, { fix: true, run: 2 }), O.deltaTurnaround(BARS, 0, 39, { fix: true }));
  assert.ok(O.deltaTurnaround(BARS, 0, 39, {}).length > 0 && O.stopRuns(BARS, 0, 39, 5, 10).length > 0 && O.exhaustions(BARS, 0, 39, 8, 2, 2).length > 0);
});

// ------------------------------------------------------------------ marker size (the signature cell.js calls)

test('markerSize(size, min, scale, o): markerMin / markerMax / fullAt', () => {
  const M = MATH.now;
  assert.equal(M.markerSize(10, 10, true, { markerMin: 1 }), 1);                           // at the minimum: the smallest marker
  assert.equal(M.markerSize(80, 10, true, { markerMin: 1, markerMax: 3 }), 3);            // at 8x: the largest
  assert.equal(M.markerSize(20, 10, true, { markerMin: 1, markerMax: 3 }), 1.67);         // one third of the way (log2 2 / 3)
  assert.equal(M.markerSize(40, 10, true, { fullAt: 4 }), 2.2);                           // the biggest marker at 4x now
  assert.equal(M.markerSize(20, 10, true, { fullAt: 4 }), 1.4);
  assert.equal(M.markerSize(80, 10, true, { markerMin: 1, markerMax: 3, fullAt: 16 }), 2.5);
  assert.equal(M.markerSize(500, 10, false, { markerMin: 1.5 }), 1.5);                    // scale off: the smallest marker for every print
  assert.equal(M.markerSize(80, 10, true, { markerMin: 2, markerMax: 1 }), 2);            // a max under the min does not shrink them
  assert.equal(MATH.old.markerSize(20, 10, true, { markerMin: 1 }), 1.13, 'the old function ignores the options');
});

// ------------------------------------------------------------------ heatmap bubbles

test('heatmap bubbles: colours, radius, full size, outline width, size label, front', () => {
  const P = { ...defs('heatmap'), bubbles: true, bubbleMin: 5 };
  const base = draw('now', 'heatmap', P);
  assert.deepEqual([...new Set(sets(base, 'fillStyle'))].sort(), ['rgba(242,54,69,.45)', 'rgba(8,153,129,.45)']);
  const st = draw('now', 'heatmap', P, { style: { ...style('buyFill', '#112233', 60), ...style('sellFill', '#445566'), ...style('buyOutline', '#778899', 80), ...style('sellOutline', '#AABBCC') } });
  assert.deepEqual([...new Set(sets(st, 'fillStyle'))].sort(), ['#445566', 'rgba(17,34,51,0.6)']);
  assert.deepEqual([...new Set(sets(st, 'strokeStyle'))].sort(), ['#AABBCC', 'rgba(119,136,153,0.8)']);
  const r = (log) => calls(log, 'arc').map((c) => c[3]);
  assert.ok(Math.min(...r(base)) >= 3 && Math.max(...r(base)) <= 14);
  const big = draw('now', 'heatmap', { ...P, bubbleRadiusMin: 6, bubbleRadiusMax: 30 });
  assert.ok(Math.min(...r(big)) >= 6 && Math.max(...r(big)) > 14 && Math.max(...r(big)) <= 30);
  const full = draw('now', 'heatmap', { ...P, bubbleFullSize: 60 });
  assert.notDeepEqual(r(full), r(base));                                                    // the size that gets the biggest circle moved
  assert.deepEqual(r(draw('now', 'heatmap', { ...P, bubbleFullSize: 60, bubbleMax: 500 })), r(draw('now', 'heatmap', { ...P, bubbleMax: 500 })));   // 'up to' wins when set
  const thick = draw('now', 'heatmap', { ...P, bubbleLineWidth: 3 });
  assert.deepEqual([...new Set(sets(thick, 'lineWidth'))], [3]);
  const none = draw('now', 'heatmap', { ...P, bubbleLineWidth: 0 });
  assert.equal(calls(none, 'stroke').length, 0);
  assert.equal(calls(none, 'fill').length, calls(base, 'fill').length);
  assert.equal(calls(base, 'fillText').length, 0);
  const lab = draw('now', 'heatmap', { ...P, bubbleLabels: true });
  assert.ok(calls(lab, 'fillText').length > 0);
  assert.equal(draw('now', 'heatmap', P).z, 'bottom');
  assert.equal(draw('now', 'heatmap', { ...P, bubbleFront: true }).z, 'top');
  assert.equal(draw('now', 'heatmap', { ...P, bubbleFront: 'yes' }).z, 'bottom');           // junk: the default
  assert.notDeepEqual(draw('old', 'heatmap', { ...P, bubbleRadiusMax: 30, bubbleLineWidth: 0, bubbleFront: true }), draw('now', 'heatmap', { ...P, bubbleRadiusMax: 30, bubbleLineWidth: 0 }));
});

// ------------------------------------------------------------------ big prints: the sweeps

test('big prints sweeps: minimum, width, arrow size, dash, colours', () => {
  const P = { ...defs('bigprints'), sweeps: true, min: 100 };
  const base = draw('now', 'bigprints', P);
  const n = (log) => calls(log, 'closePath').length;
  assert.ok(n(base) > 0);
  assert.ok(n(draw('now', 'bigprints', { ...P, sweepMin: 20 })) > n(base));                  // a lower minimum for sweeps only
  assert.ok(n(draw('now', 'bigprints', { ...P, sweepMin: 150 })) < n(base));
  assert.equal(n(draw('now', 'bigprints', { ...P, sweepMin: 0 })), n(base));                 // 0 = the same as Minimum size
  assert.deepEqual(sets(draw('now', 'bigprints', { ...P, sweepWidth: 5 }), 'lineWidth'), [5]);
  assert.deepEqual(sets(base, 'lineWidth'), [2]);
  const wide = draw('now', 'bigprints', { ...P, sweepArrow: 2 });
  const tip = (log) => { const m = calls(log, 'moveTo'); return m.filter((_, i) => i % 2 === 1).map((c) => c[2]); };
  assert.ok(Math.abs(tip(base)[0] - tip(wide)[0]) > 5);                                       // the chevron's tip moved twice as far
  assert.equal(calls(base, 'setLineDash').length, 0);
  const dashed = draw('now', 'bigprints', { ...P, sweepDash: 'dashed' });
  assert.deepEqual(calls(dashed, 'setLineDash').map((c) => c[1]), [[4, 3], []]);
  assert.deepEqual(calls(draw('now', 'bigprints', { ...P, sweepDash: 'dotted' }), 'setLineDash').map((c) => c[1]), [[1, 2], []]);
  assert.deepEqual([...new Set(sets(base, 'strokeStyle'))].sort(), ['#089981', '#F23645']);
  const st = draw('now', 'bigprints', P, { style: { ...style('buy', '#112233', 50), ...style('sell', '#445566') } });
  assert.deepEqual([...new Set(sets(st, 'strokeStyle'))].sort(), ['#445566', 'rgba(17,34,51,0.5)']);
  assert.deepEqual([...new Set(sets(st, 'fillStyle'))].sort(), ['#445566', 'rgba(17,34,51,0.5)']);
});

test('big prints sweeps: arrow geometry scales from the tip', () => {
  const bars = [{ ms: T0, s: 'a', o: 100, h: 101, l: 99, c: 100, v: 1, d: 0 }, { ms: T0 + BAR, s: 'a', o: 100, h: 101, l: 99, c: 100, v: 1, d: 0, sw: [[T0 + BAR + 1000, 99.5, 100.5, 60, 1]] }];
  const P = { ...defs('bigprints'), sweeps: true, min: 10 };
  const geo = (extra) => calls(draw('now', 'bigprints', { ...P, ...extra }, { bars }), 'lineTo').slice(1).map((c) => [c[1], c[2]]);
  const [l1, r1] = geo({}), [l2, r2] = geo({ sweepArrow: 2 });
  assert.equal(r1[0] - l1[0], 8); assert.ok(Math.abs(r2[0] - l2[0] - 16) < 1e-9);
  const tipY = 1000 - 100.5 * 40, m = (extra) => calls(draw('now', 'bigprints', { ...P, ...extra }, { bars }), 'moveTo')[1][2];
  assert.equal(m({}), tipY - 6); assert.equal(m({ sweepArrow: 2 }), tipY - 12);
});

// ------------------------------------------------------------------ big trades

test('big trades: colours, radius, full size, outline, size label, font, front', () => {
  const P = { ...defs('bigtrades'), min: 10 };
  const base = draw('now', 'bigtrades', P);
  const r = (log) => calls(log, 'arc').map((c) => c[3]);
  assert.deepEqual([...new Set(sets(base, 'fillStyle').filter((c) => c.startsWith('rgba')))].sort(), ['rgba(242,54,69,.45)', 'rgba(8,153,129,.45)']);
  const st = draw('now', 'bigtrades', P, { style: { ...style('buyFill', '#112233', 30), ...style('sellFill', '#445566', 70), ...style('buyOutline', '#778899'), ...style('sellOutline', '#AABBCC', 40) } });
  assert.deepEqual([...new Set(sets(st, 'strokeStyle'))].sort(), ['#778899', 'rgba(170,187,204,0.4)']);
  assert.deepEqual([...new Set(sets(st, 'fillStyle').filter((c) => c.startsWith('rgba')))].sort(), ['rgba(17,34,51,0.3)', 'rgba(68,85,102,0.7)']);
  const big = draw('now', 'bigtrades', { ...P, radiusMin: 5, radiusMax: 40 });
  assert.ok(Math.min(...r(big)) >= 5 && Math.max(...r(big)) > 14);
  assert.notDeepEqual(r(draw('now', 'bigtrades', { ...P, fullSize: 80 })), r(base));
  assert.deepEqual(r(draw('now', 'bigtrades', { ...P, fullSize: 80, max: 500 })), r(draw('now', 'bigtrades', { ...P, max: 500 })));
  assert.deepEqual([...new Set(sets(draw('now', 'bigtrades', { ...P, lineWidth: 4 }), 'lineWidth'))], [4]);
  const none = draw('now', 'bigtrades', { ...P, lineWidth: 0 });
  assert.equal(calls(none, 'stroke').length, 0);
  assert.ok(calls(base, 'stroke').length > 0);
  assert.ok(calls(base, 'fillText').length > 0);
  assert.equal(calls(draw('now', 'bigtrades', { ...P, labels: false }), 'fillText').length, 0);
  assert.equal(calls(draw('now', 'bigtrades', { ...P, labelMinR: 30 }), 'fillText').length, 0);
  assert.ok(calls(draw('now', 'bigtrades', { ...P, labelMinR: 4 }), 'fillText').length > calls(base, 'fillText').length);
  assert.deepEqual(sets(base, 'font'), ['10px -apple-system, BlinkMacSystemFont, sans-serif']);
  assert.deepEqual(sets(draw('now', 'bigtrades', { ...P, fontSize: 14 }), 'font'), ['14px -apple-system, BlinkMacSystemFont, sans-serif']);
  assert.equal(base.z, 'bottom');
  assert.equal(draw('now', 'bigtrades', { ...P, front: true }).z, 'top');
});

// ------------------------------------------------------------------ cluster statistics

test('cluster statistics: rows, sizes, thresholds, decimals, position, colours, and the legend hint', () => {
  const P = defs('cstat');
  const base = draw('now', 'cstat', P);
  const rows = (log) => calls(log, 'fillText').length;
  const per = (log) => calls(log, 'fillText').filter((c) => c[2] === 4 && c[1] !== undefined).length;
  assert.equal(per(base), 7);
  assert.equal(per(draw('now', 'cstat', { ...P, showVolume: false, showSeconds: false })), 5);
  const two = draw('now', 'cstat', { ...P, showDelta: false, showVolume: false, showTrades: false, showDeltaPct: false, showMaxDelta: false });
  assert.deepEqual(calls(two, 'fillText').slice(0, 2).map((c) => c[1]), ['Min delta', 'Seconds']);
  assert.equal(calls(two, 'fillRect')[0][4], 12 * 2 + 4);                                    // the strip shrinks with the rows
  assert.equal(draw('now', 'cstat', { ...P, showDelta: false, showVolume: false, showTrades: false, showDeltaPct: false, showMaxDelta: false, showMinDelta: false, showSeconds: false }).length, 0);
  assert.ok(rows(base) > rows(two));
  const tall = draw('now', 'cstat', { ...P, rowH: 20 });
  assert.deepEqual(calls(tall, 'fillRect')[0].slice(2, 5), [500 - 20 * 7 - 4, 2000, 20 * 7 + 4]);
  assert.deepEqual(calls(base, 'fillRect')[0].slice(2, 5), [500 - 12 * 7 - 4, 2000, 12 * 7 + 4]);
  assert.ok(rows(draw('now', 'cstat', { ...P, labelW: 120 })) < rows(base));                // more bars sit under a wider label column
  assert.ok(rows(draw('now', 'cstat', { ...P, labelW: 20 })) > rows(base));
  assert.equal(draw('now', 'cstat', P, { step: 30 }).length, 0);                             // 30 px a bar: hidden under the default 34
  assert.ok(draw('now', 'cstat', { ...P, minBarPx: 20 }, { step: 30 }).length > 0);
  assert.equal(draw('now', 'cstat', { ...P, minBarPx: 60 }).length, 0);
  assert.deepEqual(sets(draw('now', 'cstat', { ...P, fontSize: 13 }), 'font'), ['13px -apple-system, BlinkMacSystemFont, sans-serif']);
  assert.ok(calls(base, 'fillText').some((c) => /^-?\d+\.\d%$/.test(c[1])));
  assert.ok(calls(draw('now', 'cstat', { ...P, pctDecimals: 2 }), 'fillText').some((c) => /^-?\d+\.\d\d%$/.test(c[1])));
  assert.ok(calls(draw('now', 'cstat', { ...P, pctDecimals: 0 }), 'fillText').some((c) => /^-?\d+%$/.test(c[1])));
  const tens = (log) => calls(log, 'fillText').filter((c) => c[1].endsWith('k')).length;
  assert.equal(tens(base), 0);
  assert.ok(tens(draw('now', 'cstat', { ...P, kFrom: 100 })) > 0);                           // the volumes are 200 and up
  assert.equal(calls(draw('now', 'cstat', { ...P, place: 'top' }), 'fillRect')[0][2], 0);
  assert.equal(calls(draw('now', 'cstat', { ...P, place: 'nope' }), 'fillRect')[0][2], 500 - 88);
  const st = draw('now', 'cstat', P, { style: { ...style('pos', '#112233', 50), ...style('neg', '#445566') } });
  const cols = new Set(sets(st, 'fillStyle'));
  assert.ok(cols.has('rgba(17,34,51,0.5)') && cols.has('#445566'));
  assert.ok(!cols.has('#089981') && !cols.has('#F23645'));
  // indstatus.js: the "zoom in" note follows the same setting
  const S = require(DIR + 'indstatus.js');
  const f = (spacing) => ({ bars: BARS, i0: 0, i1: 10, spacing });
  assert.equal(S.of({ id: 'cstat', params: {} }, f(30)).text, 'Zoom in to see the stats');
  assert.equal(S.of({ id: 'cstat', params: { minBarPx: 20 } }, f(30)), null);
  assert.equal(S.of({ id: 'cstat', params: { minBarPx: 60 } }, f(50)).text, 'Zoom in to see the stats');
  assert.equal(S.of({ id: 'cstat', params: { minBarPx: 'x' } }, f(30)).text, 'Zoom in to see the stats');
});

// ------------------------------------------------------------------ delta turnaround, delta strength

test('delta arrows: colours, size, fill, distance, outline width, and the turnaround run', () => {
  for (const [id, gap0, filled0] of [['dturn', 3, true], ['dstr', 17, false]]) {
    const P = { ...defs(id), ...ON[id] };
    const base = draw('now', id, P);
    const tipsY = (log) => calls(log, 'moveTo').map((c) => c[2]);
    const wid = (log) => calls(log, 'lineTo')[0][1] - calls(log, 'lineTo')[1][1];
    assert.equal(wid(base), -10);                                                              // 5 px each side at size 1 (right corner minus left)
    assert.equal(wid(draw('now', id, { ...P, size: '1.5' })), -15);
    assert.equal(wid(draw('now', id, { ...P, size: '0.7' })), -7);
    assert.equal(wid(draw('now', id, { ...P, size: 'junk' })), -10);
    assert.equal(calls(base, filled0 ? 'fill' : 'stroke').length > 0, true);
    const flipped = draw('now', id, { ...P, filled: !filled0 });
    assert.equal(calls(flipped, filled0 ? 'stroke' : 'fill').length > 0 && calls(flipped, filled0 ? 'fill' : 'stroke').length === 0, true);
    const moved = tipsY(draw('now', id, { ...P, gap: gap0 + 10 }));
    assert.equal(moved[0] - tipsY(base)[0] === 10 || moved[0] - tipsY(base)[0] === -10, true);
    assert.deepEqual([...new Set(sets(draw('now', id, { ...P, lineWidth: 3 }), 'lineWidth'))], [3]);
    assert.deepEqual([...new Set(sets(base, 'lineWidth'))], [1.5]);
    const st = draw('now', id, P, { style: { ...style('up', '#112233', 50), ...style('down', '#445566') } });
    assert.ok(!sets(st, 'strokeStyle').includes('#089981') && !sets(st, 'strokeStyle').includes('#F23645'));
    assert.ok(sets(st, 'strokeStyle').every((c) => c === 'rgba(17,34,51,0.5)' || c === '#445566'));
  }
  // the turnaround run: bars 10 and 11 are two bearish bars before 12; with one required bar the bullish bar 14 after bar 13 (bullish) doesn't count, with 3 bars needed bar 12 doesn't
  const n = (run) => MATH.now.deltaTurnaround(BARS, 0, 39, { run }).map((r) => r.i);
  assert.ok(n(2).includes(12));
  assert.ok(!n(3).includes(12));
  assert.deepEqual(MATH.now.deltaTurnaround(BARS, 0, 39, { run: 'abc' }), MATH.now.deltaTurnaround(BARS, 0, 39, {}));
  const r1 = draw('now', 'dturn', { ...defs('dturn'), run: 1 }), r2 = draw('now', 'dturn', defs('dturn')), r3 = draw('now', 'dturn', { ...defs('dturn'), run: 3 });
  assert.notEqual(calls(r1, 'fill').length, calls(r2, 'fill').length);
  assert.ok(calls(r3, 'fill').length < calls(r2, 'fill').length);
  // a real bar is needed in every slot of the run
  const gap = BARS.map((b, i) => (i === 10 ? { ...b, blank: true } : b));
  assert.ok(!MATH.now.deltaTurnaround(gap, 0, 39, { run: 2 }).some((r) => r.i === 12));
});

// ------------------------------------------------------------------ absorption (tape)

test('absorption (tape): colours, width, tail, dot, dash, and the imbalance settings', () => {
  const P = { ...defs('mwabs'), ...ON.mwabs };
  const base = draw('now', 'mwabs', P);
  assert.ok(calls(base, 'arc').length > 0);
  assert.deepEqual([...new Set(sets(base, 'lineWidth'))], [1.5]);
  assert.deepEqual([...new Set(sets(draw('now', 'mwabs', { ...P, lineWidth: 3 }), 'lineWidth'))], [3]);
  const mv = (log) => calls(log, 'moveTo').map((c) => c[1]);
  const tail = (log) => calls(log, 'lineTo').map((c, i) => c[1] - mv(log)[i]);
  assert.ok(draw('now', 'mwabs', { ...P, tail: 20 }) && mv(base)[0] - mv(draw('now', 'mwabs', { ...P, tail: 20 }))[0] === 14);
  void tail;
  assert.equal(calls(draw('now', 'mwabs', { ...P, dot: false }), 'arc').length, 0);
  assert.ok(calls(draw('now', 'mwabs', { ...P, dotR: 6 }), 'arc').every((c) => c[3] === 6));
  assert.ok(calls(base, 'arc').every((c) => c[3] === 3));
  assert.equal(calls(base, 'setLineDash').length, 0);
  assert.ok(calls(draw('now', 'mwabs', { ...P, dash: 'dashed' }), 'setLineDash').length > 0);
  const st = draw('now', 'mwabs', P, { style: { ...style('up', '#112233', 50), ...style('down', '#445566') } });
  assert.ok(sets(st, 'strokeStyle').every((c) => c === 'rgba(17,34,51,0.5)' || c === '#445566'));
  const lines = (log) => calls(log, 'arc').length;
  const n0 = lines(base);
  assert.ok(lines(draw('now', 'mwabs', { ...P, ratio: 12 })) < n0);                          // a much stricter ratio leaves fewer
  assert.ok(lines(draw('now', 'mwabs', { ...P, ratio: 12 })) >= 0);
  assert.ok(lines(draw('now', 'mwabs', { ...P, minvol: 1000 })) === 0);                      // both sides under 1000 contracts everywhere
  assert.ok(lines(draw('now', 'mwabs', { ...P, mindiff: 1000 })) === 0);
  assert.ok(lines(draw('now', 'mwabs', { ...P, minvol: 5 })) <= n0);
  // zero / edge: 'skip' drops pairs against an empty row / the bar's end rows
  const fp = [[99.75, 0, 4], [100, 0, 9]];                                                    // 100: buyers over an empty bid below (the zero rule); 99.75: the bar's end row (the edge rule)
  const bars = [{ ms: T0, s: 'a', o: 100, h: 100, l: 99.75, c: 100, v: 1, d: 0, fp }, { ms: T0 + BAR, s: 'a', o: 99, h: 99, l: 99, c: 99, v: 1, d: 0 }];
  const a = (extra) => calls(draw('now', 'mwabs', { ...defs('mwabs'), ticks: 4, within: 1, ...extra }, { bars }), 'arc').length;
  assert.equal(a({}), 1);
  assert.equal(a({ zero: 'skip' }), 0);
  const fp2 = [[100, 0, 9]];
  const bars2 = [{ ...bars[0], fp: fp2, l: 100 }, bars[1]];
  const b = (extra) => calls(draw('now', 'mwabs', { ...defs('mwabs'), ticks: 4, within: 1, ...extra }, { bars: bars2 }), 'arc').length;
  assert.equal(b({}), 1);
  assert.equal(b({ edge: 'skip' }), 0);
  assert.equal(b({ minvol: 10 }), 0);
  assert.equal(b({ mindiff: 10 }), 0);
  assert.equal(b({ ratio: 100 }), 0);
  assert.equal(b({ ratio: 1 }), 1);
  // the Inputs these five add did not exist in the catalog entry before
  for (const k of ['ratio', 'zero', 'edge', 'minvol', 'mindiff']) assert.ok(C.CATALOG.find((d) => d.id === 'mwabs').params.some((q) => q.key === k));
});

// ------------------------------------------------------------------ stop runs

test('stop runs: colours, line width / dash / on-off, show, cross, font, arrow distance, sweep minimum', () => {
  const P = { ...defs('stoprun'), ...ON.stoprun };
  const base = draw('now', 'stoprun', P);
  const nArrows = (log) => calls(log, 'closePath').length;
  assert.ok(nArrows(base) > 2);
  assert.deepEqual(calls(base, 'setLineDash').slice(0, 2).map((c) => c[1]), [[3, 3], []]);
  assert.deepEqual(calls(draw('now', 'stoprun', { ...P, dash: 'solid' }), 'setLineDash')[0][1], []);
  assert.deepEqual(calls(draw('now', 'stoprun', { ...P, dash: 'dotted' }), 'setLineDash')[0][1], [1, 2]);
  assert.deepEqual(sets(draw('now', 'stoprun', { ...P, lineWidth: 3 }), 'lineWidth').slice(0, 2), [3, 1]);   // the level line is 3 wide, the arrow outline stays 1
  const noLine = draw('now', 'stoprun', { ...P, levelLine: false });
  assert.equal(calls(noLine, 'lineTo').length, nArrows(noLine) * 2);                        // the arrows' two corners only
  assert.ok(calls(base, 'lineTo').length > calls(noLine, 'lineTo').length);
  const held = (log) => calls(log, 'fillText').filter((c) => !c[1].includes('✕')).length;
  const trap = (log) => calls(log, 'fillText').filter((c) => c[1].includes('✕')).length;
  assert.ok(held(base) > 0 && trap(base) > 0, 'the scene has both a held run and a trap');
  const h = draw('now', 'stoprun', { ...P, show: 'held' }), t = draw('now', 'stoprun', { ...P, show: 'trap' });
  assert.equal(trap(h), 0); assert.equal(held(h), held(base));
  assert.equal(held(t), 0); assert.equal(trap(t), trap(base));
  const nc = draw('now', 'stoprun', { ...P, trapMark: false });
  assert.equal(trap(nc), 0); assert.equal(calls(nc, 'fillText').length, calls(base, 'fillText').length);
  assert.deepEqual(sets(base, 'font'), ['11px -apple-system, BlinkMacSystemFont, sans-serif']);
  assert.deepEqual(sets(draw('now', 'stoprun', { ...P, fontSize: 15 }), 'font').slice(-1), ['15px -apple-system, BlinkMacSystemFont, sans-serif']);
  const tipOf = (log) => calls(log, 'moveTo').filter((_, i) => i % 2 === 1).map((c) => c[2]);
  const g0 = tipOf(base), g1 = tipOf(draw('now', 'stoprun', { ...P, arrowGap: 10 }));
  assert.ok(g0.every((y, i) => Math.abs(y - g1[i]) === 6));
  assert.ok(nArrows(draw('now', 'stoprun', { ...P, sweepMin: 300 })) < nArrows(base));      // the sweeps that make up a burst must each be this big
  const st = draw('now', 'stoprun', P, { style: { ...style('up', '#112233', 50), ...style('down', '#445566') } });
  assert.ok(sets(st, 'strokeStyle').every((c) => c === 'rgba(17,34,51,0.5)' || c === '#445566'));
  assert.ok(sets(st, 'fillStyle').every((c) => c === 'rgba(17,34,51,0.5)' || c === '#445566'));
  assert.ok(MATH.now.stopRuns(BARS, 0, 39, 5, 10, 300).length < MATH.now.stopRuns(BARS, 0, 39, 5, 10).length);
});

// ------------------------------------------------------------------ exhaustion

test('exhaustion: colours, cap width / reach, arrow, font, giveback', () => {
  const P = { ...defs('exhaust'), ...ON.exhaust };
  const base = draw('now', 'exhaust', P);
  assert.equal(calls(base, 'closePath').length, 1);
  assert.deepEqual(sets(base, 'lineWidth'), [2]);
  assert.deepEqual(sets(draw('now', 'exhaust', { ...P, capWidth: 5 }), 'lineWidth'), [5]);
  const cap = (log) => [calls(log, 'moveTo')[0][1], calls(log, 'lineTo')[0][1]];
  const [a0, b0] = cap(base), [a1, b1] = cap(draw('now', 'exhaust', { ...P, capHalf: 16 }));
  assert.deepEqual([a0 - a1, b1 - b0], [10, 10]);
  const noArrow = draw('now', 'exhaust', { ...P, arrow: false });
  assert.equal(calls(noArrow, 'closePath').length, 0); assert.equal(calls(noArrow, 'fill').length, 0);
  assert.equal(calls(noArrow, 'fillText').length, 1);
  assert.deepEqual(sets(draw('now', 'exhaust', { ...P, fontSize: 14 }), 'font').slice(-1), ['14px -apple-system, BlinkMacSystemFont, sans-serif']);
  const st = draw('now', 'exhaust', P, { style: { ...style('up', '#112233', 50), ...style('down', '#445566', 80) } });
  assert.ok(sets(st, 'strokeStyle').includes('rgba(68,85,102,0.8)') && !sets(st, 'strokeStyle').includes('#F23645'));
  // giveback: the push bar spans 99.5-105.5 (mid 102.5); the last bar closes at 102.5, which is not "past" the middle
  const n = (g) => MATH.now.exhaustions(BARS, 0, 39, 8, 2, 2, g).length;
  assert.equal(n(50), MATH.old.exhaustions(BARS, 0, 39, 8, 2, 2).length);
  assert.equal(n(50), 1);
  assert.equal(n(40), 1);                                                                     // 40 % back = 103.1: 102 is below it
  assert.equal(n(75), 0);                                                                     // 75 % back = 101: 102 has not got there
  assert.equal(n(100), 0);
  assert.equal(n('x'), n(50));
});

// ------------------------------------------------------------------ naked POCs

test('naked POCs: colour, only untouched, look back, width, dash', () => {
  const P = defs('npoc');
  const base = draw('now', 'npoc', P);
  const strokes = (log) => calls(log, 'stroke').length;
  assert.ok(strokes(base) > 5);
  assert.deepEqual(sets(base, 'strokeStyle'), ['#F7A600']);
  assert.deepEqual(sets(draw('now', 'npoc', P, { style: style('line', '#112233', 50) }), 'strokeStyle'), ['rgba(17,34,51,0.5)']);
  assert.deepEqual(sets(base, 'lineWidth'), [1]); assert.deepEqual(sets(draw('now', 'npoc', { ...P, width: 3 }), 'lineWidth'), [3]);
  assert.deepEqual(calls(base, 'setLineDash')[0][1], [4, 3]);
  assert.deepEqual(calls(draw('now', 'npoc', { ...P, dash: 'solid' }), 'setLineDash')[0][1], []);
  assert.deepEqual(calls(draw('now', 'npoc', { ...P, dash: 'dotted' }), 'setLineDash')[0][1], [1, 2]);
  const only = draw('now', 'npoc', { ...P, nakedOnly: true });
  assert.ok(strokes(only) < strokes(base) && strokes(only) > 0);
  assert.ok(calls(only, 'lineTo').every((c) => c[1] === 2000));                               // every line left runs to the right edge
  assert.ok(calls(base, 'lineTo').some((c) => c[1] !== 2000));
  // look back: the view starts at bar 25 (the pane shows the last 15 bars), a POC at bar 5 is 20 bars to the left
  const r = rig('now', [{ id: 'npoc', visible: true, params: { ...P, lookback: 50 } }], BARS);
  r.cell.chart.timeScale = () => ({ getVisibleLogicalRange: () => ({ from: 26, to: 39 }), logicalToCoordinate: (i) => (i - 26) * 50, subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} });
  r.o.sync();
  const run = (lookback) => { r.cell.cfg.indicators[0].params.lookback = lookback; const { ctx, log } = recorder(); r.o.npoc.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 2000, height: 500 } }) }); return strokes(log); };
  const near = run(1), far = run(500);
  r.o.destroy();
  assert.ok(far > near);
});

// ------------------------------------------------------------------ TPO

test('TPO: colours, blocks opacity, letter size, POC / value area / single-print switches', () => {
  const P = defs('tpo');
  const base = draw('now', 'tpo', P);
  const fills = (log) => sets(log, 'fillStyle');
  assert.ok(fills(base).includes('rgba(41,98,255,.28)'));
  assert.deepEqual(sets(base, 'font'), ['10px -apple-system, BlinkMacSystemFont, sans-serif']);
  assert.deepEqual(sets(draw('now', 'tpo', { ...P, fontSize: 12 }), 'font'), ['12px -apple-system, BlinkMacSystemFont, sans-serif']);
  assert.equal(calls(base, 'strokeRect').length, 1);
  assert.equal(calls(draw('now', 'tpo', { ...P, showPoc: false }), 'strokeRect').length, 0);
  const va = (log) => calls(log, 'fillRect').length;
  assert.ok(va(base) > 0);
  assert.equal(va(draw('now', 'tpo', { ...P, showVa: false })), 0);                          // letters: the only rects are the value area's
  const st = draw('now', 'tpo', P, { style: { ...style('va', '#112233', 40), ...style('poc', '#445566'), ...style('ib', '#778899', 50), ...style('single', '#AABBCC') } });
  assert.ok(fills(st).includes('rgba(17,34,51,0.4)') && !fills(st).includes('rgba(41,98,255,.28)'));
  assert.ok(sets(st, 'strokeStyle').includes('#445566') && sets(st, 'strokeStyle').includes('rgba(119,136,153,0.5)'));
  assert.ok(!sets(st, 'strokeStyle').includes('#F7A600'));
  // single prints: a row only one letter touched takes the "single" colour unless the switch is off
  const single = (log) => fills(log).filter((c) => c === '#AABBCC').length;
  assert.ok(single(st) > 0);
  const off = draw('now', 'tpo', { ...P, markSingles: false }, { style: style('single', '#AABBCC') });
  assert.equal(single(off), 0);
  assert.notDeepEqual(fills(off), fills(draw('now', 'tpo', P, { style: style('single', '#AABBCC') })));
  // blocks: the opacity of the wash
  const bl = draw('now', 'tpo', { ...P, style: 'blocks' }), bl2 = draw('now', 'tpo', { ...P, style: 'blocks', blocksOpacity: 80 });
  assert.ok(fills(bl).some((c) => /0\.45\)$/.test(c)) && !fills(bl).some((c) => /0\.8\)$/.test(c)));
  assert.ok(fills(bl2).some((c) => /0\.8\)$/.test(c)) && !fills(bl2).some((c) => /0\.45\)$/.test(c)));
  assert.equal(45 / 100, 0.45);
});

// ------------------------------------------------------------------ fair value gaps

test('fair value gaps: border on/off, border width, extend open gaps to the right edge', () => {
  const P = defs('fvg');
  const base = draw('now', 'fvg', P);
  const n = calls(base, 'fillRect').length;
  assert.ok(n > 1 && calls(base, 'strokeRect').length === n);
  const nb = draw('now', 'fvg', { ...P, border: false });
  assert.equal(calls(nb, 'strokeRect').length, 0); assert.equal(calls(nb, 'fillRect').length, n);
  assert.deepEqual([...new Set(sets(base, 'lineWidth'))], [1]);
  assert.deepEqual([...new Set(sets(draw('now', 'fvg', { ...P, borderWidth: 3 }), 'lineWidth'))], [3]);
  const right = (log) => calls(log, 'fillRect').map((c) => c[1] + c[3]);
  const ex = draw('now', 'fvg', { ...P, extend: true });
  assert.equal(Math.max(...right(base)) < 2000, true);
  assert.equal(Math.max(...right(ex)), 2000);                                                 // the gap still open on the newest bar runs to the edge
  assert.equal(right(ex).filter((x) => x === 2000).length, 1);
  assert.deepEqual(right(base).filter((x, i) => right(ex)[i] !== x).length, 1);              // only that one moved
});

// ------------------------------------------------------------------ SMT

test('SMT lines: colours, width, line on/off, dot size, label font', () => {
  const P = { ...defs('smt'), ...ON.smt };
  const base = draw('now', 'smt', P);
  assert.ok(calls(base, 'arc').length > 0);
  assert.deepEqual([...new Set(sets(base, 'lineWidth'))], [1.5]);
  assert.deepEqual([...new Set(sets(draw('now', 'smt', { ...P, lineWidth: 4 }), 'lineWidth'))], [4]);
  const nl = draw('now', 'smt', { ...P, showLine: false });
  assert.equal(calls(nl, 'stroke').length, 0); assert.equal(calls(nl, 'arc').length, calls(base, 'arc').length);
  assert.ok(calls(base, 'arc').every((c) => c[3] === 2.5));
  assert.ok(calls(draw('now', 'smt', { ...P, dotRadius: 5 }), 'arc').every((c) => c[3] === 5));
  assert.equal(calls(draw('now', 'smt', { ...P, dotRadius: 0 }), 'arc').length, 0);
  assert.deepEqual(sets(draw('now', 'smt', { ...P, fontSize: 14 }), 'font').slice(-1), ['14px -apple-system, BlinkMacSystemFont, sans-serif']);
  const st = draw('now', 'smt', P, { style: { ...style('up', '#112233', 50), ...style('down', '#445566') } });
  assert.ok(sets(st, 'strokeStyle').every((c) => c === 'rgba(17,34,51,0.5)' || c === '#445566'));
});

test('one block\'s font does not leak into the next (stop runs, SMT and exhaustion share one pass)', () => {
  const sr = { id: 'stoprun', visible: true, params: { ...defs('stoprun'), ...ON.stoprun, fontSize: 15 } };
  const sm = { id: 'smt', visible: true, params: { ...defs('smt'), ...ON.smt } };
  const ex = { id: 'exhaust', visible: true, params: { ...defs('exhaust'), ...ON.exhaust, fontSize: 9 } };
  const r = rig('now', [sr, sm, ex], BARS);
  r.o.sync();
  const { ctx, log } = recorder();
  r.o.run.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 2000, height: 500 } }) });
  r.o.destroy();
  assert.deepEqual(sets(log, 'font').map((f) => parseInt(f)), [11, 15, 11, 9]);               // the base, stop runs, SMT back at 11, exhaustion
});

// ------------------------------------------------------------------ junk / missing

test('junk and missing settings fall back to the old drawing; the colour of an instance without a style is the old one', () => {
  const all = {};
  for (const id of IDS) all[id] = { ...defs(id), ...ON[id] };
  const junk = (id) => Object.fromEntries(Object.entries(all[id]).map(([k, v]) => [k, k in (OLDKEYS.heatmap && id === 'heatmap' ? Object.fromEntries(OLDKEYS.heatmap.map((x) => [x, 1])) : {}) || !NEWKEYS(id).has(k) ? v : (typeof v === 'boolean' ? 'maybe' : Array.isArray(v) ? v : 'zzz')]));
  for (const id of IDS) {
    const { old, now } = same(id, junk(id), { style: { unrelated: { color: 'nope' } } });
    assert.deepEqual(now, old, id);
  }
  // a broken style entry (no colour string) is the old colour
  const { old, now } = same('bigtrades', { ...defs('bigtrades'), min: 10 }, { style: { buyFill: { alpha: 50 }, sellOutline: { color: 5 } } });
  assert.deepEqual(now, old);
});
