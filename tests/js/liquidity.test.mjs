import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/liquidity.js');

const T0 = 1_790_000_000_000;

test('gridCells: /api/depth/history grid -> one cell per [t_idx, price_idx, size], clipped at endMs', () => {
  const grid = { t0: T0, dt_ms: 1000, tick: 0.25, prices: [99.75, 100.5], cells: [[0, 1, 5], [0, 0, 2], [2, 3, 7]] };
  assert.deepEqual(L.gridCells(grid), [
    { t0: T0, t1: T0 + 1000, price: 100, size: 5 },
    { t0: T0, t1: T0 + 1000, price: 99.75, size: 2 },
    { t0: T0 + 2000, t1: T0 + 3000, price: 100.5, size: 7 },
  ]);
  assert.deepEqual(L.gridCells(grid, T0 + 2500).map((c) => c.t1), [T0 + 1000, T0 + 1000, T0 + 2500]);
  assert.deepEqual(L.gridCells(grid, T0 + 2000).length, 2);                        // a column past the cut goes
  const gc = { t0: T0, dt_ms: 1000, tick: 0.1, prices: [1999.9, 2000.2], cells: [[0, 3, 1]] };
  assert.equal(L.gridCells(gc)[0].price, 2000.2);                                  // no float drift off the tick
  for (const bad of [null, {}, { t0: T0, dt_ms: 0, tick: 0.25, prices: [1, 2], cells: [[0, 0, 1]] },
    { t0: T0, dt_ms: 1000, tick: 0.25, prices: null, cells: [] },
    { t0: T0, dt_ms: 1000, tick: 0.25, prices: [1, 2], cells: [[0, 0, 0], 'x', [0, 'a', 1]] }]) {
    assert.deepEqual(L.gridCells(bad), []);
  }
});

test('intensity: log scale over the window max, 0..1', () => {
  assert.equal(L.intensity(100, 100), 1);
  assert.equal(L.intensity(0, 100), 0);
  assert.ok(Math.abs(L.intensity(9, 99) - Math.log1p(9) / Math.log1p(99)) < 1e-12);
  assert.ok(L.intensity(10, 1000) > 10 / 1000 * 4);                                 // log: small sizes still show
  assert.equal(L.intensity(500, 100), 1);                                           // clamped
  assert.equal(L.intensity(5, 0), 0);
});

test('windowMax: the largest size among cells overlapping the visible time and price window', () => {
  const cells = [
    { t0: 0, t1: 10, price: 100, size: 50 },
    { t0: 10, t1: 20, price: 100, size: 20 },
    { t0: 10, t1: 20, price: 200, size: 900 },     // outside the visible prices
    { t0: 30, t1: 40, price: 100, size: 700 },     // outside the visible time
  ];
  assert.equal(L.windowMax(cells, 5, 25, 90, 110), 50);
  assert.equal(L.windowMax(cells, 12, 25, 90, 110), 20);
  assert.equal(L.windowMax(cells, 12, 25, 90, 300), 900);
  assert.equal(L.windowMax(cells, 100, 200, 0, 1e9), 0);
  assert.equal(L.windowMax(cells, 5, 25, 110, 90), 50);                             // lo/hi either order
});

test('LiveBuffer: one book a second, bounded by 2 h and by count, a lost book leaves a gap', () => {
  const b = new L.LiveBuffer();
  assert.equal(b.maxMs, 2 * 3600 * 1000);
  b.push(T0, [[100, 1]], [[100.25, 2]]);
  b.push(T0 + 400, [[100, 3]], [[100.25, 4]]);                                      // same second: replaced
  assert.equal(b.length, 1);
  assert.deepEqual(b.levels(0), [[100, 3], [100.25, 4]]);
  b.push(T0 - 5000, [[1, 1]], []);                                                   // older than the last: dropped
  assert.equal(b.length, 1);
  b.push(T0 + 1000, [[100, 5], ['x', 1], [101, NaN]], []);                           // malformed levels skipped
  assert.deepEqual(b.levels(1), [[100, 5]]);
  for (let i = 2; i < 3 * 3600; i++) b.push(T0 + i * 1000, [[100, i]], []);
  assert.ok(b.length <= 2 * 3600 + 1);
  assert.ok(b.oldest() >= b.latest() - b.maxMs);
  const small = new L.LiveBuffer(60_000, 10);
  for (let i = 0; i < 50; i++) small.push(T0 + i * 1000, [[100, 1]], []);
  assert.equal(small.length, 10);                                                    // the count cap
  small.gap(T0 + 50_000);
  assert.equal(small.latest(), T0 + 50_000);
  assert.deepEqual(small.levels(small.length - 1), []);
  small.clear();
  assert.equal(small.length, 0);
  assert.equal(small.oldest(), null);
});

test('liveGrid: the same grid as the server -- the book in force at each column end, held at most HOLD_MS', () => {
  const b = new L.LiveBuffer();
  b.push(T0, [[100, 5], [99.75, 2]], [[100.25, 7]]);
  b.push(T0 + 1500, [[100, 9]], [[100.25, 1], [100.5, 3]]);
  const g = L.liveGrid(b, T0, T0 + 4000, 1000, 0.25);
  assert.equal(g.t0, T0);
  assert.equal(g.dt_ms, 1000);
  assert.deepEqual(g.prices, [99.75, 100.5]);
  const col = (c) => Object.fromEntries(L.gridCells(g).filter((x) => x.t0 === T0 + c * 1000).map((x) => [x.price, x.size]));
  assert.deepEqual(col(0), { 100: 5, 99.75: 2, 100.25: 7 });
  assert.deepEqual(col(1), { 100: 9, 100.25: 1, 100.5: 3 });
  assert.deepEqual(col(3), col(1));
  const far = L.liveGrid(b, T0, T0 + 10 * 60_000, 60_000, 0.25);
  assert.deepEqual([...new Set(far.cells.map((c) => c[0]))], [0, 1, 2, 3, 4]);       // 5 min of hold, then blank
  const empty = L.liveGrid(new L.LiveBuffer(), T0, T0 + 4000, 1000, 0.25);
  assert.deepEqual(empty.cells, []);
  assert.equal(empty.prices, null);
});

test('level + chunkStarts: column width from the view, history in aligned chunks, none zoomed too far out', () => {
  const a = L.level(10 * 60_000, 1200);            // 10 min over 1200 px: 1 s columns
  assert.equal(a.dt, 1000);
  assert.equal(a.chunk, L.CHUNK_COLS * 1000);
  const b = L.level(6 * 3600_000, 1200);           // 6 h: 36 s wanted -> 64 s
  assert.equal(b.dt, 64_000);
  assert.equal(L.level(L.MAX_VIEW_MS + 1, 1200), null);
  assert.ok(L.level(L.MAX_VIEW_MS, 100).chunk <= L.MAX_VIEW_MS);                      // one request never over the cap
  assert.deepEqual(L.chunkStarts(1000, 2500, 1000), [1000, 2000]);
  assert.deepEqual(L.chunkStarts(1500, 3000, 1000), [1000, 2000]);
  assert.deepEqual(L.chunkStarts(3000, 3000, 1000), []);
});

test('ChunkCache: least recently used goes first, bounded', () => {
  const c = new L.ChunkCache(2);
  c.set('a', 1); c.set('b', 2);
  assert.equal(c.get('a'), 1);                     // a is now the most recent
  c.set('c', 3);
  assert.equal(c.get('b'), undefined);
  assert.equal(c.get('a'), 1);
  assert.equal(c.size, 2);
});

test('logicalAt / timeAt: bar i spans logical [i - .5, i + .5); time bars extrapolate, others clamp', () => {
  const bars = [{ ms: 0 }, { ms: 60_000 }, { ms: 180_000 }];
  assert.equal(L.logicalAt(bars, 0, 60_000), -0.5);
  assert.equal(L.logicalAt(bars, 30_000, 60_000), 0);
  assert.equal(L.logicalAt(bars, 120_000, 60_000), 1);                               // bar 1 runs to bar 2
  assert.equal(L.logicalAt(bars, 210_000, 60_000), 2);                               // the last bar: barMs
  assert.equal(L.logicalAt(bars, 300_000, 60_000), 3.5);                             // extrapolated
  assert.equal(L.logicalAt(bars, -60_000, 60_000), -1.5);
  assert.equal(L.logicalAt(bars, 200_000, 0, 220_000), 2);                           // tick bars: last runs to endMs
  assert.equal(L.logicalAt(bars, 999_000, 0, 220_000), 2.5);                         // clamped
  assert.equal(L.logicalAt(bars, -5, 0, 220_000), -0.5);
  assert.equal(L.logicalAt([], 5, 60_000), null);
  for (const t of [0, 30_000, 120_000, 210_000, 300_000, -60_000]) assert.equal(L.timeAt(bars, L.logicalAt(bars, t, 60_000), 60_000), t);
  assert.equal(L.timeAt(bars, 2, 0, 220_000), 200_000);
});

test('ramp: the palette stops by intensity, as rgba', () => {
  const stops = L.parseStops(['rgba(41, 98, 255, .1)', 'rgba(247,166,0,0.5)', '#F23645']);
  assert.deepEqual(stops, [[41, 98, 255, 0.1], [247, 166, 0, 0.5], [242, 54, 69, 1]]);
  assert.equal(L.ramp(0, stops), 'rgba(41,98,255,0.1)');
  assert.equal(L.ramp(1, stops), 'rgba(242,54,69,1)');
  assert.equal(L.ramp(0.5, stops), 'rgba(247,166,0,0.5)');
  assert.equal(L.ramp(0.25, stops), 'rgba(144,132,128,0.3)');
  assert.equal(L.ramp(7, stops), L.ramp(1, stops));
});

test('the overlay (fake chart): history asked for the part older than the live buffer, both drawn behind the candles', async () => {
  const path = require.resolve('../../homebase/static/charts/liquidity.js');
  const D = require('../../homebase/static/charts/drawings.js');
  const calls = [], attached = [];
  class Layer { constructor(P) { this.P = P; } redraw() {} }
  globalThis.window = { HBLayers: { Layer }, HBDrawings: D };
  const now = Date.now(), M = 60_000, T = Math.floor(now / M) * M - 9 * M;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    const from = +new URL(url, 'http://x').searchParams.get('from_ms');
    // one cell a minute after the first bar, whatever chunk was asked
    const c = Math.floor((T + M - from) / 1000);
    return { ok: true, status: 200, json: async () => ({ t0: from, dt_ms: 1000, tick: 0.25, prices: [100, 100], cells: [[c, 0, 40]] }) };
  };
  delete require.cache[path];
  const H = require(path);
  let ov = null;
  try {
    const ts = { getVisibleLogicalRange: () => ({ from: 0, to: 10 }),   // a right offset past the last bar
      width: () => 1000, logicalToCoordinate: (i) => i * 100 + 50,
      subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} };
    const candles = { attachPrimitive: (l) => attached.push(l), detachPrimitive: (l) => attached.splice(attached.indexOf(l), 1),
      priceToCoordinate: (p) => (200 - p) * 4, coordinateToPrice: (y) => 200 - y / 4 };
    const cell = { cfg: { root: 'NQ', indicators: [{ id: 'heatmap', visible: true }] }, shown: null,
      chart: { timeScale: () => ts }, candles, bars: Array.from({ length: 10 }, (_, i) => ({ ms: T + i * M })),
      isTime: () => true, barMs: () => M, tick: 0.25, P: {} };
    H.onDepth({ type: 'depth', root: 'NQ', ts: now - 20_000, bids: [[100, 5]], offers: [[100.25, 9]] });
    ov = H.overlay(cell);
    assert.equal(attached.length, 1);
    assert.equal(attached[0].z(), 'bottom');                                   // behind the candles
    assert.equal(calls.length, 1);                                             // one request in flight
    for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 0));   // ... then the rest, one by one
    const asked = calls.length;
    assert.ok(asked >= 1 && asked <= 3, `${asked} chunks`);                    // aligned chunks over the view
    for (const u of calls) assert.match(u, /^\/api\/depth\/history\?root=NQ&from_ms=\d+&to_ms=\d+&cols=300$/);
    assert.ok(calls.every((u) => +new URL(u, 'http://x').searchParams.get('to_ms') <= Date.now()));   // never past now
    const ops = [];
    const ctx = { set fillStyle(v) { ops.push(['fill', v]); }, beginPath() {}, fill() {}, rect: (...a) => ops.push(['rect', ...a]) };
    const target = { useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 800 } }) };
    ov.draw(target);
    const rects = ops.filter((o) => o[0] === 'rect');
    assert.ok(rects.some((r) => r[2] === (200 - 100) * 4 - 0.5), 'the history cell at 100');
    assert.ok(rects.some((r) => r[2] === (200 - 100.25) * 4 - 0.5), 'the live cell at 100.25');
    assert.ok(rects.every((r) => r[1] + r[3] <= ts.logicalToCoordinate(9) + 50 + 1e-9), 'nothing past the last bar');
    assert.ok(ops.filter((o) => o[0] === 'fill').every((o) => /^rgba\(/.test(o[1])));
    ov.ask();                                                                     // cached: nothing asked again
    assert.equal(calls.length, asked);
    cell.cfg.indicators = [];
    ops.length = 0;
    ov.draw(target);
    assert.equal(ops.length, 0);                                                  // off: draws nothing
    ov.destroy();
    assert.equal(attached.length, 0);
  } finally {
    if (ov) ov.destroy();
    delete globalThis.window;
    delete globalThis.fetch;
  }
});

/* ---- review fix round 1 ---- */
test('beforeCursor: a replay drops every column ending past its cursor (a column shows its end-of-column book)', () => {
  const cells = [{ t0: 0, t1: 10, price: 1, size: 1 }, { t0: 10, t1: 20, price: 1, size: 1 }, { t0: 20, t1: 30, price: 1, size: 1 }];
  assert.deepEqual(L.beforeCursor(cells, 20).map((c) => c.t0), [0, 10]);
  assert.deepEqual(L.beforeCursor(cells, 19).map((c) => c.t0), [0]);
  assert.deepEqual(L.beforeCursor(cells, -1), []);
});

test('retryAfter: busy retries soon, a paused window waits, anything else backs off', () => {
  assert.equal(L.retryAfter(503, 'busy — try again in a moment'), 2000);
  assert.equal(L.retryAfter(503, 'paused for the 9:30 window'), 60_000);
  assert.equal(L.retryAfter(503, 'paused for the 8:30 data release'), 60_000);
  assert.equal(L.retryAfter(500, null), 30_000);
  assert.equal(L.retryAfter(0, null), 30_000);
});

function fakeChart(T, M, bars = 10) {
  const attached = [];
  const ts = { getVisibleLogicalRange: () => ({ from: 0, to: bars }), width: () => 1000, logicalToCoordinate: (i) => i * 100 + 50,
    subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} };
  const candles = { attachPrimitive: (l) => attached.push(l), detachPrimitive: (l) => attached.splice(attached.indexOf(l), 1),
    priceToCoordinate: (p) => (200 - p) * 4, coordinateToPrice: (y) => 200 - y / 4 };
  const cell = { cfg: { root: 'NQ', indicators: [{ id: 'heatmap', visible: true }] }, shown: null,
    chart: { timeScale: () => ts }, candles, bars: Array.from({ length: bars }, (_, i) => ({ ms: T + i * M })),
    isTime: () => true, barMs: () => M, tick: 0.25, P: {} };
  const ops = [];
  const ctx = { set fillStyle(v) { ops.push(['fill', v]); }, beginPath() {}, fill() {}, rect: (...a) => ops.push(['rect', ...a]) };
  const target = { useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 800 } }) };
  return { cell, ts, attached, ops, target };
}

function loadBrowser(fetchImpl) {
  const path = require.resolve('../../homebase/static/charts/liquidity.js');
  class Layer { constructor(P) { this.P = P; } redraw() {} }
  globalThis.window = { HBLayers: { Layer }, HBDrawings: require('../../homebase/static/charts/drawings.js') };
  globalThis.fetch = fetchImpl;
  delete require.cache[path];
  return require(path);
}

test('the overlay: one history request in flight per chart, the next asked when it lands', async () => {
  const now = Date.now(), M = 3_600_000, T = Math.floor(now / M) * M - 60 * M;   // 60 h of hourly bars
  const pending = [];
  const H = loadBrowser((url) => new Promise((resolve) => pending.push({ url: String(url), resolve })));
  let ov = null;
  try {
    const { cell } = fakeChart(T, M, 60);
    ov = H.overlay(cell);
    assert.equal(pending.length, 1);                                   // several chunks wanted, one asked
    ov.ask();
    assert.equal(pending.length, 1);
    pending[0].resolve({ ok: true, status: 200, json: async () => ({ t0: 0, dt_ms: 1000, tick: 0.25, prices: null, cells: [] }) });
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(pending.length, 2);                                   // the next chunk, once the first landed
    assert.notEqual(pending[1].url, pending[0].url);
  } finally {
    if (ov) ov.destroy();
    delete globalThis.window; delete globalThis.fetch;
  }
});

test('the overlay on a Bar Replay cell: no live book, history only up to the cursor', async () => {
  const now = Date.now(), M = 60_000, T = Math.floor(now / M) * M - 30 * M;
  const calls = [];
  const H = loadBrowser(async (url) => {
    calls.push(String(url));
    const from = +new URL(url, 'http://x').searchParams.get('from_ms');
    // a cell a minute after bar 0, and one straddling the cursor (bar 5 + 30 s)
    return { ok: true, status: 200, json: async () => ({ t0: from, dt_ms: 60_000, tick: 0.25, prices: [100, 101],
      cells: [[Math.round((T + M - from) / 60_000), 0, 40], [Math.round((T + 5 * M - from) / 60_000), 4, 40]] }) };
  });
  let ov = null;
  try {
    H.onDepth({ type: 'depth', root: 'NQ', ts: now - 5000, bids: [[150, 5]], offers: [[150.25, 9]] });
    const { cell, ops, target } = fakeChart(T, M, 30);
    const cursor = T + 5 * M + 30_000;
    cell.replay = { date: '2026-09-24', cursorMs: cursor };
    cell.bars = cell.bars.slice(0, 6);                                 // replay shows bars up to the cursor
    ov = H.overlay(cell);
    for (let i = 0; i < 5 && calls.length < 3; i++) { await new Promise((r) => setTimeout(r, 0)); ov.ask(); }
    assert.ok(calls.length >= 1);
    for (const u of calls) assert.ok(+new URL(u, 'http://x').searchParams.get('to_ms') <= cursor, u);
    ov.draw(target);
    const ys = new Set(ops.filter((o) => o[0] === 'rect').map((o) => o[2] + 0.5));
    assert.ok(ys.has((200 - 100) * 4), 'the history column before the cursor');
    assert.ok(!ys.has((200 - 101) * 4), 'the column ending past the cursor is dropped');
    assert.ok(!ys.has((200 - 150) * 4) && !ys.has((200 - 150.25) * 4), 'never the live book');
  } finally {
    if (ov) ov.destroy();
    delete globalThis.window; delete globalThis.fetch;
  }
});

test('onDisconnect: the live buffers get a gap, so the last book is not held over the outage', () => {
  const H = loadBrowser(async () => ({ ok: false, status: 500 }));
  try {
    H.onDepth({ type: 'depth', root: 'ES', ts: Date.now() - 2000, bids: [[1, 1]], offers: [] });
    H.onDisconnect();
    const b = H.liveBuffer('ES');
    assert.deepEqual(b.levels(b.length - 1), []);
  } finally {
    delete globalThis.window; delete globalThis.fetch;
  }
});
