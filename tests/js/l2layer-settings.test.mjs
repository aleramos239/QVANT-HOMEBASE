/* Indicator settings wiring for the Level 2 / book overlays: bigorders, imbalance, absorb, pulled, iceberg
   (l2layer.js, bookevents.js, dom.js) and the heatmap's liquidity map (liquidity.js). The pre-change files come from
   `git show HEAD:` and run side by side with the working tree: with no Style and every param at its default the canvas
   calls (and price-line options) must be identical. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const CH = ROOT + 'homebase/static/charts/';
const Defs = require(CH + 'flowdefs.js');
const Dom = require(CH + 'dom.js');

function loadNew(name) { const p = CH + name; delete require.cache[p]; return require(p); }
function loadOld(name) {
  const src = execFileSync('git', ['show', `e29a6928:homebase/static/charts/${name}`], { cwd: ROOT, encoding: 'utf8' });
  const module = { exports: {} };
  new Function('require', 'module', 'exports', src)((p) => require(p.startsWith('.') ? CH + p : p), module, module.exports);
  return module.exports;
}
/* every param of `id` at its flowdefs default (what a new instance holds) */
const defaults = (id) => Object.fromEntries(Defs.settings[id].params.map((p) => [p.key, p.def]));
const style = (o) => Object.fromEntries(Object.entries(o).map(([k, [color, alpha = 100]]) => [k, { color, alpha }]));

/* a canvas context that records every call and every property set */
function rec() {
  const log = [], t = {};
  const ctx = new Proxy(t, {
    get: (_, k) => (k in t ? t[k] : (...a) => { log.push([k, ...a]); }),
    set: (_, k, v) => { t[k] = v; log.push(['=', k, v]); return true; },
  });
  return { ctx, log };
}
const sets = (log, k) => log.filter((c) => c[0] === '=' && c[1] === k).map((c) => c[2]);
const calls = (log, k) => log.filter((c) => c[0] === k);

/* ------------------------------------------------------------------ bookevents.js */

const T0 = 1_790_000_000_000, BAR = 60_000;
const ep = (o) => ({ id: 'x', s: 'b', p: 100, t0: T0 + BAR, t1: T0 + 3 * BAR, pk: 300, r: 6, tr: 0, end: 'faded', ab: null, d0: 5, ...o });
const EPS = [
  ep({ id: 'big1', p: 50, end: 'traded', pk: 300 }),
  ep({ id: 'big2', p: 60, s: 'a', end: 'pulled', pk: 40, r: 7 }),
  ep({ id: 'big3', p: 55, pk: 500, r: 8 }),
  ep({ id: 'ab1', p: 80, ab: T0 + 2 * BAR, tr: 700, r: 8, end: 'traded' }),
  ep({ id: 'ab2', p: 85, s: 'a', ab: T0 + 2 * BAR, tr: 400, r: 8, end: 'traded' }),
  ep({ id: 'pl2', p: 65, end: 'pulled', pk: 800, r: 9 }),
  ep({ id: 'ice1', p: 90, t1: null, end: 'open', pk: 10, r: 0, tr: 60, rl: 3 }),
  ep({ id: 'ice2', p: 95, s: 'a', t1: T0 + 6 * BAR, end: 'ice', pk: 12, r: 0, tr: 40, rl: 2 }),
  ep({ id: 'ice3', p: 97, t1: T0 + 6 * BAR, end: 'ice', pk: 10, r: 0, tr: 90, rl: 5 }),
];

function bookRig(which, indicators) {
  const S = require(CH + 'bookstore.js');
  S.clear();
  class Layer { constructor(P) { this.P = P; } redraw() {} }
  globalThis.window = { HBBookStore: { ...S, ensure() {} }, HBLayers: { Layer }, HBLiquidity: loadNew('liquidity.js'),
    HBDrawings: require(CH + 'drawings.js'), HBCatalog: require(CH + 'catalog.js') };
  const M = which === 'old' ? loadOld('bookevents.js') : loadNew('bookevents.js');
  S.applyHistory('NQ', { t0: T0, t1: T0 + 10 * BAR, samples: [], episodes: EPS });
  const range = { from: 0, to: 9 };
  const cell = {
    cfg: { root: 'NQ', indicators }, shown: { root: 'NQ' }, P: {}, replay: null,
    bars: Array.from({ length: 10 }, (_, i) => ({ ms: T0 + i * BAR })), isTime: () => true, barMs: () => BAR,
    chart: { timeScale: () => ({ getVisibleLogicalRange: () => range, logicalToCoordinate: (i) => i * 100,
      subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} }) },
    candles: { attachPrimitive() {}, detachPrimitive() {}, priceToCoordinate: (p) => p },
  };
  const { ctx, log } = rec();
  const target = { useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 2000, height: 500 } }) };
  const o = M.overlay(cell);
  try { o.layer.draw(target); } finally { o.destroy(); delete globalThis.window; }
  return log;
}
const ind = (over = {}) => {
  const mk = (id, base, extra = {}) => ({ id, uid: id, visible: true, params: { ...base, ...(over[id] || {}) }, ...(over[id + '_style'] ? { style: over[id + '_style'] } : {}), ...extra });
  return [mk('bigorders', { multiple: 5, minSeconds: 5, history: true, width: 2, ...defaults('bigorders') }),
    mk('absorb', { multiple: 4, minSeconds: 5, side: 'all', labels: true, size: 1, ...defaults('absorb') }),
    mk('iceberg', { multiple: 3, minTraded: 30, side: 'all', labels: true, size: 1, ...defaults('iceberg') }),
    mk('pulled', { multiple: 5, minSeconds: 5, side: 'all', labels: true, size: 1, ...defaults('pulled') })];
};
const legacy = () => [
  { id: 'bigorders', visible: true, params: { multiple: 5, minSeconds: 5, history: true, width: 2 } },
  { id: 'absorb', visible: true, params: { multiple: 4, minSeconds: 5, side: 'all', labels: true, size: 1 } },
  { id: 'iceberg', visible: true, params: { multiple: 3, minTraded: 30, side: 'all', labels: true, size: 1 } },
  { id: 'pulled', visible: true, params: { multiple: 5, minSeconds: 5, side: 'all', labels: true, size: 1 } }];
const draw = (over) => bookRig('new', ind(over));
const drawOnly = (id, over) => bookRig('new', ind(over).filter((x) => x.id === id));

test('bookevents: default output is byte-identical to HEAD (all defaults, and an instance saved before the settings)', () => {
  for (const make of [() => ind(), legacy]) {
    const old = bookRig('old', make()), now = bookRig('new', make());
    assert.ok(calls(old, 'fillRect').length >= 1 && calls(old, 'arc').length >= 3 && calls(old, 'fillText').length >= 6, 'the scene draws something of each kind');
    assert.deepEqual(now, old);
  }
});

test('bookevents: junk or missing settings fall back to the old behaviour', () => {
  const base = bookRig('old', ind());
  for (const junk of [null, 'abc', NaN, '']) {
    const over = { bigorders: { endedOpacity: junk, minSize: junk }, absorb: { minTraded: junk, labelSize: junk },
      iceberg: { reloads: junk, endedOpacity: junk, width: junk, labelSize: junk }, pulled: { minSize: junk, labelSize: junk } };
    assert.deepEqual(draw(over), base, `junk ${String(junk)}`);
  }
});

test('bigorders: Style bid / ask colours paint the ended segments and caps', () => {
  const st = style({ bid: ['#112233'], ask: ['#445566', 50] });
  const log = drawOnly('bigorders', { bigorders_style: st });
  const col = sets(log, 'strokeStyle');
  assert.ok(col.includes('#112233') && col.includes('rgba(68,85,102,0.5)'));
  assert.ok(!col.includes('#2962FF') && !col.includes('#F23645'));
  assert.ok(sets(log, 'fillStyle').includes('#112233'));                       // the traded square
});

test('bigorders: endedOpacity, caps, minSize', () => {
  assert.ok(sets(draw({ bigorders: { endedOpacity: 30 } }), 'globalAlpha').includes(0.3));
  assert.ok(!sets(draw({ bigorders: { endedOpacity: 30 } }), 'globalAlpha').includes(0.6));
  assert.ok(sets(bookRig('new', ind()), 'globalAlpha').includes(0.6));
  const off = drawOnly('bigorders', { bigorders: { caps: false } });
  assert.equal(calls(off, 'fillRect').length, 0);
  assert.equal(calls(off, 'arc').length, 0);
  const all = drawOnly('bigorders', {});
  assert.equal(calls(all, 'fillRect').length, 3);        // big1, ab1, ab2 ended as traded
  assert.ok(calls(all, 'arc').length >= 1);
  // minSize: big1 300, big2 40, big3 500 -> only big3 (p 55) is left among the segments (every segment is a moveTo at its price)
  const only = drawOnly('bigorders', { bigorders: { minSize: 400 } });
  const prices = (log) => calls(log, 'moveTo').map((c) => c[2]);
  assert.ok(prices(all).includes(50) && prices(all).includes(60));
  assert.ok(prices(only).includes(55) && !prices(only).includes(50) && !prices(only).includes(60));
});

test('bigorders: the existing width still sets the ended segments', () => {
  assert.ok(sets(draw({ bigorders: { width: 4 } }), 'lineWidth').includes(4));
});

test('absorb: Style up / down, minTraded, labelSize', () => {
  const st = style({ up: ['#0A0B0C'], down: ['#0D0E0F', 40] });
  const col = sets(draw({ absorb_style: st }), 'strokeStyle');
  assert.ok(col.includes('#0A0B0C') && col.includes('rgba(13,14,15,0.4)'));
  const all = calls(draw({}), 'fillText').filter((c) => c[1] === 'A').length;
  assert.equal(all, 2);
  const few = draw({ absorb: { minTraded: 500 } });
  assert.equal(calls(few, 'fillText').filter((c) => c[1] === 'A').length, 1);          // ab1 traded 700, ab2 400
  assert.ok(calls(few, 'fillText').some((c) => c[1] === '700') && !calls(few, 'fillText').some((c) => c[1] === '400'));
  const big = sets(draw({ absorb: { labelSize: 15 } }), 'font');
  assert.ok(big.some((f) => f.startsWith('15px ')));
  assert.ok(sets(draw({}), 'font').some((f) => f.startsWith('10px ')));
});

test('pulled: Style bid / ask, minSize, labelSize', () => {
  const st = style({ bid: ['#0A0B0C'], ask: ['#0D0E0F'] });
  const col = sets(draw({ pulled_style: st }), 'strokeStyle');
  assert.ok(col.includes('#0A0B0C') && col.includes('#0D0E0F'));
  const labels = (log) => calls(log, 'fillText').map((c) => c[1]);
  assert.ok(labels(draw({})).includes('40') && labels(draw({})).includes('800'));
  const big = draw({ pulled: { minSize: 100 } });
  assert.ok(labels(big).includes('800') && !labels(big).includes('40'));
  assert.ok(sets(draw({ pulled: { labelSize: 17 } }), 'font').some((f) => f.startsWith('17px ')));
});

test('iceberg: Style up / down, reloads, endedOpacity, width, labelSize', () => {
  const st = style({ up: ['#0A0B0C'], down: ['#0D0E0F'] });
  const col = sets(draw({ iceberg_style: st }), 'strokeStyle');
  assert.ok(col.includes('#0A0B0C') && col.includes('#0D0E0F'));
  const labels = (log) => calls(log, 'fillText').map((c) => c[1]).filter((t) => t.startsWith('×'));
  assert.equal(labels(draw({})).length, 3);
  assert.equal(labels(draw({ iceberg: { reloads: 4 } })).length, 1);                  // only ice3 (rl 5)
  assert.equal(labels(draw({ iceberg: { reloads: 2 } })).length, 3);
  const a = sets(draw({ iceberg: { endedOpacity: 40 } }), 'globalAlpha');
  assert.ok(a.includes(0.4) && !a.includes(0.7) && a.includes(1));
  assert.ok(sets(draw({}), 'globalAlpha').includes(0.7));
  assert.ok(sets(draw({ iceberg: { width: 6 } }), 'lineWidth').includes(6));
  assert.ok(sets(draw({}), 'lineWidth').includes(3));
  assert.ok(sets(draw({ iceberg: { labelSize: 12 } }), 'font').some((f) => f.startsWith('12px ')));
});

test('bookevents pure filters: segments / absorptions / pulls / icebergs take the new limits and default to none', () => {
  const E = loadNew('bookevents.js');
  assert.deepEqual(E.segments(EPS, { multiple: 5, minSeconds: 5, minSize: 400 }).map((s) => s.id), ['big3', 'pl2']);
  assert.deepEqual(E.absorptions(EPS, { minTraded: 500 }).map((s) => s.id), ['ab1']);
  assert.deepEqual(E.pulls(EPS, { minSize: 100 }).map((s) => s.id), ['pl2']);
  assert.deepEqual(E.icebergs(EPS, { multiple: 3, minTraded: 30, reloads: 4 }).map((s) => s.id), ['ice3']);
  assert.equal(E.icebergs(EPS, { multiple: 3, minTraded: 30 }).length, 3);
});

/* ------------------------------------------------------------------ dom.js */

test('dom.bigLevels: cap per side, default 8, junk = default', () => {
  const rows = Array.from({ length: 12 }, (_, i) => [100 - i * 0.25, 50]);
  const o = { multiple: 5, median: 2, now: 1000, tick: 0.25 };
  assert.equal(Dom.bigLevels({ ts: 1000, bids: rows, offers: [] }, null, o).bids.length, 8);
  assert.equal(Dom.bigLevels({ ts: 1000, bids: rows, offers: [] }, null, { ...o, cap: 3 }).bids.length, 3);
  assert.equal(Dom.bigLevels({ ts: 1000, bids: rows, offers: [] }, null, { ...o, cap: 12 }).bids.length, 12);
  for (const junk of [0, -1, NaN, undefined, null]) assert.equal(Dom.bigLevels({ ts: 1000, bids: rows, offers: [] }, null, { ...o, cap: junk }).bids.length, 8);
});

/* ------------------------------------------------------------------ l2layer.js */

class El {
  constructor() { this.style = {}; this.className = ''; this.children = []; this.parentNode = null; this.textContent = ''; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  append(...cs) { cs.forEach((c) => this.appendChild(c)); }
  contains(c) { return this.children.includes(c); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((x) => x !== this); this.parentNode = null; }
}

function l2(which, indicators, feed) {
  globalThis.window = { HBDom: Dom, HBCatalog: require(CH + 'catalog.js') };
  globalThis.document = { createElement: () => new El() };
  const L = which === 'old' ? loadOld('l2layer.js') : loadNew('l2layer.js');
  L.onDisconnect();
  const lines = new Set();
  const candles = {
    createPriceLine: (o) => { const pl = { o: { ...o }, applyOptions: (x) => Object.assign(pl.o, x) }; lines.add(pl); return pl; },
    removePriceLine: (pl) => lines.delete(pl),
  };
  const rowEl = new El();
  const cell = { cfg: { root: 'NQ', indicators }, shown: { root: 'NQ' }, chart: {}, candles, tick: 0.25, P: {},
    rows: indicators.filter((x) => x.id === 'imbalance').map((inst) => ({ inst, row: rowEl })) };
  const out = { L, cell, lines, rowEl };
  try {
    feed(out);
  } finally { out.lines = new Set(lines); if (out.ov) out.ov.destroy(); delete globalThis.window; delete globalThis.document; }
  return out;
}
const t1 = Date.now();
const smallBook = (ts, n = 12) => ({ type: 'depth', root: 'NQ', ts, bids: Array.from({ length: n }, (_, i) => [100 - i * 0.25, 2]), offers: Array.from({ length: n }, (_, i) => [100.25 + i * 0.25, 2]) });
const bigBook = (ts, n = 12) => ({ type: 'depth', root: 'NQ', ts, bids: Array.from({ length: n }, (_, i) => [100 - i * 0.25, 50]), offers: [[100.25, 2]] });
function feedBig(o, then) {
  for (let i = 0; i < 20; i++) o.L.onDepth(smallBook(t1 - 20_000 + i * 1000));
  o.L.onDepth(bigBook(t1));
  o.ov = o.L.overlay(o.cell);
  if (then) then(o);
}
const bo = (over = {}, extra = {}) => [{ uid: 'b', id: 'bigorders', visible: true, params: { multiple: 5, minSeconds: 5, history: true, width: 2, ...defaults('bigorders'), ...over }, ...extra }];
const opts = (r) => [...r.lines].map((pl) => pl.o).sort((a, b) => b.price - a.price);

test('l2layer: live bigorders lines are byte-identical to HEAD at defaults (and for an instance saved before)', () => {
  const legacyInst = [{ uid: 'b', id: 'bigorders', visible: true, params: { multiple: 5 } }];
  for (const make of [() => bo(), () => legacyInst]) {
    const old = l2('old', make(), (o) => feedBig(o)), now = l2('new', make(), (o) => feedBig(o));
    assert.equal(opts(old).length, 8);
    assert.deepEqual(opts(now), opts(old));
  }
});

test('l2layer: liveLines off draws no standing lines', () => {
  const r = l2('new', bo({ liveLines: false }), (o) => feedBig(o));
  assert.equal(r.lines.size, 0);
});

test('l2layer: liveWidth, liveDash, labels reach the price lines, also on the next paint', () => {
  const r = l2('new', bo({ liveWidth: 3, liveDash: '2', labels: false }), (o) => feedBig(o, (x) => x.ov.paint()));
  for (const o of opts(r)) {
    assert.equal(o.lineWidth, 3); assert.equal(o.lineStyle, 2); assert.equal(o.axisLabelVisible, false); assert.equal(o.title, '');
  }
  const d = l2('new', bo(), (o) => feedBig(o, (x) => x.ov.paint()));
  for (const o of opts(d)) { assert.equal(o.lineWidth, 1); assert.equal(o.lineStyle, 0); assert.equal(o.axisLabelVisible, true); assert.match(o.title, / @ /); }
  // a setting changed on a line that already exists reaches it (applyOptions)
  const c = l2('new', bo(), (o) => feedBig(o, (x) => {
    x.cell.cfg.indicators[0].params.liveWidth = 4; x.cell.cfg.indicators[0].params.liveDash = '1'; x.ov.paint();
  }));
  for (const o of opts(c)) { assert.equal(o.lineWidth, 4); assert.equal(o.lineStyle, 1); }
  const junk = l2('new', bo({ liveWidth: 'x', liveDash: '9' }), (o) => feedBig(o));
  for (const o of opts(junk)) { assert.equal(o.lineWidth, 1); assert.equal(o.lineStyle, 0); }
});

test('l2layer: maxLines and minSize limit the live lines', () => {
  assert.equal(l2('new', bo({ maxLines: 3 }), (o) => feedBig(o)).lines.size, 3);
  const mixed = (o) => {
    for (let i = 0; i < 20; i++) o.L.onDepth(smallBook(t1 - 20_000 + i * 1000));
    o.L.onDepth({ type: 'depth', root: 'NQ', ts: t1, bids: [[100, 50], [99.75, 80], [99.5, 120]], offers: [[100.25, 2]] });
    o.ov = o.L.overlay(o.cell);
  };
  assert.equal(l2('new', bo(), mixed).lines.size, 3);
  assert.equal(l2('new', bo({ minSize: 100 }), mixed).lines.size, 1);
});

test('l2layer: fade keeps a level that left the book longer', () => {
  const run = (fade) => l2('new', bo({ fade }), (o) => {
    for (let i = 0; i < 20; i++) o.L.onDepth(smallBook(t1 - 20_000 + i * 1000));
    o.L.onDepth({ type: 'depth', root: 'NQ', ts: t1, bids: [[100, 50]], offers: [[100.25, 2]] });
    o.ov = o.L.overlay(o.cell);
    o.L.onDepth(smallBook(t1 + 6000));              // the big level is gone 6 s later
    o.ov.paint();
  }).lines.size;
  assert.equal(run(5), 0);                          // the default 5 s has run out
  assert.equal(run(10), 1);
});

test('l2layer: Style bid / ask colour the live lines (opacity kept, fade still applies)', () => {
  const r = l2('new', bo({}, { style: style({ bid: ['#112233'], ask: ['#445566'] }) }), (o) => feedBig(o));
  for (const o of opts(r)) assert.equal(o.color, 'rgba(17,34,51,1)');
  const half = l2('new', bo({}, { style: style({ bid: ['#112233', 50] }) }), (o) => feedBig(o));
  for (const o of opts(half)) assert.equal(o.color, 'rgba(17,34,51,0.5)');
  assert.equal(opts(l2('new', bo(), (o) => feedBig(o)))[0].color, 'rgba(41,98,255,1)');
});

function imbRig(params, st) {
  const book = { type: 'depth', root: 'NQ', ts: t1, bids: [[100, 90], ...Array.from({ length: 9 }, (_, i) => [99.75 - i * 0.25, 1])],
    offers: Array.from({ length: 10 }, (_, i) => [100.25 + i * 0.25, 10]) };
  const inds = [{ uid: 'i', id: 'imbalance', visible: true, params: { ...defaults('imbalance'), ...params }, ...(st ? { style: st } : {}) }];
  let badge = null;
  const r = (which) => l2(which, inds, (o) => { o.L.onDepth(book); o.ov = o.L.overlay(o.cell); badge = o.rowEl.children[0]; badge = { wrap: badge, bar: badge.children[0].children[0], barWrap: badge.children[0], pct: badge.children[1] }; });
  return { r, get badge() { return badge; } };
}

test('l2layer: imbalance gauge is identical to HEAD at defaults', () => {
  const k = imbRig({});
  k.r('old'); const a = JSON.stringify([k.badge.pct.textContent, k.badge.pct.className, k.badge.bar.className, k.badge.bar.style.width]);
  k.r('new'); const b = JSON.stringify([k.badge.pct.textContent, k.badge.pct.className, k.badge.bar.className, k.badge.bar.style.width]);
  assert.equal(b, a);
  assert.equal(k.badge.pct.style.color || '', ''); assert.equal(k.badge.bar.style.background || '', '');
  assert.ok(!k.badge.barWrap.style.display && !k.badge.pct.style.display);
});

test('l2layer: imbalance levels, bar, number and Style colours', () => {
  const pct = (params, st) => { const k = imbRig(params, st); k.r('new'); return k.badge; };
  const ten = pct({}).pct.textContent, one = pct({ levels: '1' }).pct.textContent, five = pct({ levels: '5' }).pct.textContent;
  assert.notEqual(ten, one); assert.notEqual(ten, five); assert.equal(one, '+80%');                          // top level: 90 against 10
  assert.equal(pct({ levels: '7' }).pct.textContent, ten);                                                  // junk = 10
  assert.equal(pct({ bar: false }).barWrap.style.display, 'none');
  assert.equal(pct({ number: false }).pct.style.display, 'none');
  const st = style({ bid: ['#112233'], ask: ['#445566'] });
  const ask = pct({}, st);                                   // top 10: 99 against 100, ask-heavy
  assert.equal(ask.pct.style.color, '#445566'); assert.equal(ask.bar.style.background, '#445566');
  const bid = pct({ levels: '1' }, st);
  assert.equal(bid.pct.style.color, '#112233'); assert.equal(bid.bar.style.background, '#112233');
});

/* ------------------------------------------------------------------ liquidity.js */

test('liquidity.level: columnPx widens the column; the default stays 2', () => {
  const L = loadNew('liquidity.js'), Lo = loadOld('liquidity.js');
  assert.deepEqual(L.level(10 * 60_000, 1200), Lo.level(10 * 60_000, 1200));
  assert.deepEqual(L.level(10 * 60_000, 1200, 2), L.level(10 * 60_000, 1200));
  assert.equal(L.level(10 * 60_000, 1200, 2).dt, 1000);
  assert.equal(L.level(10 * 60_000, 1200, 8).dt, 4000);
  assert.equal(L.level(10 * 60_000, 1200, 1).dt, 1000);
  for (const junk of [0, -3, NaN, null]) assert.deepEqual(L.level(10 * 60_000, 1200, junk), L.level(10 * 60_000, 1200));
});

function heat(which, params, feed) {
  const D = require(CH + 'drawings.js');
  let redraws = 0;
  class Layer { constructor(P) { this.P = P; } redraw() { redraws++; } }
  globalThis.window = { HBLayers: { Layer }, HBDrawings: D, HBCatalog: require(CH + 'catalog.js') };
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  const H = which === 'old' ? loadOld('liquidity.js') : loadNew('liquidity.js');
  const now = Date.now(), M = 60_000, T = Math.floor(now / M) * M - 9 * M;
  const ts = { getVisibleLogicalRange: () => ({ from: 0, to: 10 }), width: () => 1000, logicalToCoordinate: (i) => i * 100 + 50,
    subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} };
  const candles = { attachPrimitive() {}, detachPrimitive() {}, priceToCoordinate: (p) => (200 - p) * 4, coordinateToPrice: (y) => 200 - y / 4 };
  const heatInst = { id: 'heatmap', visible: true, ...(params ? { params } : {}) };
  const cell = { cfg: { root: 'NQ', indicators: [heatInst] }, shown: null, chart: { timeScale: () => ts }, candles,
    bars: Array.from({ length: 10 }, (_, i) => ({ ms: T + i * M })), isTime: () => true, barMs: () => M, tick: 0.25, P: {} };
  H.onDepth({ type: 'depth', root: 'NQ', ts: now - 20_000, bids: [[100, 5]], offers: [[100.25, 50]] });
  H.onDepth({ type: 'depth', root: 'NQ', ts: now - 19_000, bids: [[100, 5]], offers: [[100.25, 50], [100.5, 500]] });
  const ov = H.overlay(cell);
  const ops = [];
  const ctx = { set fillStyle(v) { ops.push(['fill', v]); }, set globalAlpha(v) { ops.push(['alpha', v]); }, beginPath() {}, fill() {}, rect: (...a) => ops.push(['rect', ...a]) };
  const target = { useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 800 } }) };
  try { return feed({ ov, ops, target, heatInst, redraws: () => redraws, H }); } finally {
    ov.destroy(); delete globalThis.window; delete globalThis.fetch;
  }
}
const heatOps = (which, params) => heat(which, params, ({ ov, ops, target }) => { ov.draw(target); return ops.slice(); });

test('heatmap map: default output is byte-identical to HEAD (no params, and every default)', () => {
  for (const p of [undefined, {}, { palette: 'fire', contrast: 'normal', ...defaults('heatmap') }]) {
    const old = heatOps('old', p), now = heatOps('new', p);
    assert.ok(old.filter((o) => o[0] === 'rect').length >= 3);
    assert.deepEqual(now, old);
  }
});

test('heatmap map: opacity, cutoff, fullAt change the picture; junk falls back', () => {
  const base = heatOps('new', {}), rects = (o) => new Set(o.filter((x) => x[0] === 'rect').map((x) => x[2])).size;   // one row per price
  assert.equal(base.filter((o) => o[0] === 'alpha').length, 0);
  assert.deepEqual(heatOps('new', { opacity: 40 }).filter((o) => o[0] === 'alpha'), [['alpha', 0.4]]);
  assert.equal(rects(heatOps('new', { opacity: 40 })), rects(base));
  // sizes 5, 50, 500 on a log scale: 0.29, 0.63, 1.0 of the biggest
  assert.equal(rects(base), 3);
  assert.equal(rects(heatOps('new', { cutoff: 50 })), 2);
  assert.equal(rects(heatOps('new', { cutoff: 90 })), 1);
  const fills = (o) => o.filter((x) => x[0] === 'fill').map((x) => x[1]);
  assert.notDeepEqual(fills(heatOps('new', { fullAt: 100000 })), fills(base));            // far above the data: everything paler
  assert.notDeepEqual(fills(heatOps('new', { fullAt: 20 })), fills(base));
  assert.equal(new Set(fills(heatOps('new', { fullAt: 4 }))).size, 1);                    // everything over the scale: one colour
  assert.equal(rects(heatOps('new', { fullAt: 20 })), rects(base));                       // cutoff 0 hides nothing
  for (const junk of [null, 'abc', NaN, '']) assert.deepEqual(heatOps('new', { opacity: junk, cutoff: junk, fullAt: junk, columnPx: junk }), base);
});

test('heatmap map: columnPx sets the column level; a change repaints and asks at the new level', () => {
  const r = heat('new', {}, ({ ov, heatInst, redraws }) => {
    ov.tick(); ov.tick();
    const dt = (p) => { heatInst.params = p; return ov.view().lv.dt; };
    const at = redraws();
    ov.tick();
    assert.equal(redraws(), at, 'nothing changed: no repaint');
    const a = dt({}), b = dt({ columnPx: 8 });
    assert.ok(b > a, `${b} > ${a}`);
    ov.tick();
    assert.equal(redraws(), at + 1, 'a changed setting repaints at once');
    heatInst.params = { opacity: 50 }; ov.tick();
    assert.equal(redraws(), at + 2);
    return true;
  });
  assert.ok(r);
});
