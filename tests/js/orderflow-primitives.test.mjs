import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The footprint extras and the profile's prior session, drawn through a recording canvas context: which strokes
   and texts land where. The geometry (stack runs, unfinished auctions) is HBFlowMath's, tested in flowmath.test. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/flowmath.js');
require('../../homebase/static/charts/primitives.js');
const { Footprint, Profile } = globalThis.HBLayers;

const P = { up: 'UP', down: 'DOWN', text2: 'T2', poc: 'POC', va: 'VA', vaIn: 'VAIN', fpBg: 'BG', fpText: 'TX' };
const recorder = () => {
  const log = [], ctx = {};
  for (const m of ['beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'fillRect', 'strokeRect', 'closePath', 'fillText', 'setLineDash', 'arc']) {
    ctx[m] = (...a) => { log.push([m, ...a]); };
  }
  ctx.measureText = () => ({ width: 10 });
  for (const k of ['strokeStyle', 'fillStyle', 'lineWidth']) {
    Object.defineProperty(ctx, k, { set: (v) => { log.push([`set ${k}`, v]); }, get: () => undefined });
  }
  return { ctx, log };
};
const series = { priceToCoordinate: (px) => 1000 - px * 4 };          // a price row is 1 px per 0.25 -> 1 px/tick; y falls with price
const TICK = 0.25;
// buys at 100.25 .. 101.00 each >= 3x the sells one tick below -> a buy stack of 4 rows; both sides traded at the top row only
const FP = [[100.0, 1, 0], [100.25, 1, 4], [100.5, 1, 4], [100.75, 1, 4], [101.0, 1, 4], [101.25, 1, 1]];

function footprint(ex, ratio = 3) {
  const f = new Footprint(P);
  f.series = series; f.tick = TICK; f.ratio = ratio; f.ex = ex;
  return f;
}

test('a stack of buy imbalances gets a bracket on the ask side; a run too short gets none', () => {
  const { ctx, log } = recorder();
  footprint({ stack: 4 }).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  const strokes = log.filter((l) => l[0] === 'moveTo');
  assert.equal(strokes.length, 1);
  assert.equal(strokes[0][1], 200 + 20 + 3);                           // right of the cell: the ask side
  assert.ok(log.some((l) => l[0] === 'set strokeStyle' && l[1] === 'UP'));
  const two = recorder();
  footprint({ stack: 5 }).extras(two.ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.equal(two.log.filter((l) => l[0] === 'moveTo').length, 0);
});

test('stacked imbalances need the imbalance ratio on; off draws nothing', () => {
  const { ctx, log } = recorder();
  footprint({ stack: 4 }, 0).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.equal(log.filter((l) => l[0] === 'moveTo').length, 0);
});

test('unfinished auctions: a triangle on a high or low row where both sides traded, none on a one-sided extreme', () => {
  const { ctx, log } = recorder();
  footprint({ unfinished: true }).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.equal(log.filter((l) => l[0] === 'fill').length, 1);          // the top row 101.25 traded both ways; 100.00 had no buyers
  const none = recorder();
  footprint({ unfinished: true }).extras(none.ctx, { fp: [[100, 5, 0], [101, 0, 5]], d: 0 }, 200, 40, 10);
  assert.equal(none.log.filter((l) => l[0] === 'fill').length, 0);
});

test('the delta number sits under the bar in the side colour', () => {
  const { ctx, log } = recorder();
  footprint({ deltaNum: true }).extras(ctx, { fp: FP, d: -12 }, 200, 40, 10);
  const t = log.find((l) => l[0] === 'fillText');
  assert.equal(t[1], '-12');
  assert.equal(t[2], 200);
  assert.ok(t[3] > series.priceToCoordinate(100.0));                   // below the lowest row
  assert.ok(log.some((l) => l[0] === 'set fillStyle' && l[1] === 'DOWN'));
});

test('no extras option: nothing is drawn', () => {
  const { ctx, log } = recorder();
  footprint({}).extras(ctx, { fp: FP, d: 3 }, 200, 40, 10);
  assert.deepEqual(log, []);
});

test('the profile draws the prior session as a ghost and its lines, the POC dashed while it is naked', () => {
  const p = new Profile(P);
  p.series = series; p.tick = TICK;
  p.p = { poc: 100, vah: 101, val: 99, rows: [[100, 10], [101, 4]], prev: { poc: 98, vah: 99, val: 97, rows: [[98, 8], [99, 3]] } };
  const run = (ex) => {
    const { ctx, log } = recorder();
    p.ex = ex;
    p.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 600 } }) });
    return log;
  };
  const rects = (log) => log.filter((l) => l[0] === 'fillRect');
  assert.equal(rects(run({})).length, 2);                              // the current profile only
  const ghost = run({ prior: true });
  assert.equal(rects(ghost).length, 4);
  assert.ok(rects(ghost)[2][1] < 1000 - 0.18 * 1000);                  // left of the current one
  const lines = run({ lines: true, naked: true });
  assert.equal(lines.filter((l) => l[0] === 'fillText').map((l) => l[1]).join(), 'pVAH,pVAL,pPOC');
  assert.ok(lines.some((l) => l[0] === 'setLineDash' && l[1].length === 2));    // the naked POC is dashed
  const touched = run({ lines: true, naked: false });
  assert.ok(!touched.some((l) => l[0] === 'setLineDash' && l[1].length === 2));
});

test('a profile with no prior session draws the current one and nothing else', () => {
  const p = new Profile(P);
  p.series = series; p.tick = TICK;
  p.p = { poc: 100, vah: 101, val: 99, rows: [[100, 10]] };
  p.ex = { prior: true, lines: true, naked: true };
  const { ctx, log } = recorder();
  p.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 600 } }) });
  assert.equal(log.filter((l) => l[0] === 'fillRect').length, 1);
  assert.equal(log.filter((l) => l[0] === 'fillText').length, 0);
});

test('zoomed out (the footprint is not readable) the extras are not drawn either', () => {
  const f = footprint({ stack: 4, unfinished: true, deltaNum: true });
  f.on = true; f.bars = [{ fp: FP, d: 3, c: 100 }];
  f.chart = { timeScale: () => ({ logicalToCoordinate: (i) => i * 10 }) };     // 10 px a bar: below the 56 px the cells need
  let drew = false;
  f.draw({ useMediaCoordinateSpace: () => { drew = true; } });
  assert.equal(drew, false);
});

/* ---- wave 2: what a row shows (`text`), the vendor imbalance rules (`imb`), the profile's value-area `method` ---- */

const series12 = { priceToCoordinate: (px) => 1000 - px * 48 };       // a tick is 12 px: readable at rows: 1
function drawFp(ex, bars, ratio = 3) {
  const f = new Footprint(P);
  f.series = series12; f.tick = TICK; f.ratio = ratio; f.ex = { rows: 1, ...ex }; f.on = true; f.bars = bars;
  f.chart = { timeScale: () => ({ logicalToCoordinate: (i) => i * 100 + 50, getVisibleLogicalRange: () => ({ from: 0, to: bars.length - 1 }) }) };
  const { ctx, log } = recorder();
  f.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 600 } }) });
  return log;
}
// every drawn text with the fill it was drawn in
const texts = (log) => { let fill; const out = []; for (const l of log) { if (l[0] === 'set fillStyle') fill = l[1]; if (l[0] === 'fillText') out.push([l[1], fill]); } return out; };
const ROWS = [[100, 2, 3], [100.25, 0, 6]];
const BAR = { c: 100, fp: ROWS, fpn: [[100, 1, 2], [100.25, 0, 4]] };

test('footprint text: unset is today\'s `numbers` mode; bidask / volume are its both / total; text wins over numbers', () => {
  const base = drawFp({}, [BAR]);
  assert.deepEqual(texts(base), [['2', 'TX'], ['3', 'UP'], ['0', 'TX'], ['6', 'UP']]);
  assert.deepEqual(drawFp({ text: 'bidask' }, [BAR]), base);
  assert.deepEqual(drawFp({ imb: 'homebase', zero: 'one', edge: 'one', minvol: 0, mindiff: 0 }, [BAR]), base);
  assert.deepEqual(drawFp({ text: 'volume' }, [BAR]), drawFp({ numbers: 'total' }, [BAR]));
  assert.deepEqual(drawFp({ text: 'delta', numbers: 'total' }, [BAR]), drawFp({ numbers: 'delta' }, [BAR]));
});

test('footprint text: trades, dominant side %, price, diagonal differences', () => {
  assert.deepEqual(texts(drawFp({ text: 'trades' }, [BAR])).map((t) => t[0]), ['1', '2', '0', '4']);
  assert.deepEqual(texts(drawFp({ text: 'trades' }, [{ c: 100, fp: ROWS }])), []);               // no fpn on the bar: no data, nothing drawn
  assert.deepEqual(texts(drawFp({ text: 'dom' }, [BAR])), [['+60', 'UP'], ['+100', 'UP']]);
  assert.deepEqual(texts(drawFp({ text: 'price' }, [BAR])).map((t) => t[0]), ['100.00', '100.25']);
  // left = Ask(P+1) - Bid(P), right = Ask(P) - Bid(P-1); 0 where that neighbour row does not exist
  assert.deepEqual(texts(drawFp({ text: 'diag' }, [BAR])).map((t) => t[0]), ['4', '0', '0', '4']);
});

test('footprint imb: a vendor rule changes the flagged rows; its stacked runs follow it', () => {
  const atas = texts(drawFp({ imb: 'atas' }, [BAR], 3.5));
  assert.deepEqual(atas, [['2', 'TX'], ['3', 'TX'], ['0', 'TX'], ['6', 'TX']]);                  // 6 is not GREATER than 3.5 x 2, and 100 has no row below
  assert.deepEqual(texts(drawFp({ imb: 'atas' }, [BAR]))[3], ['6', 'UP']);                        // ratio left on its default 3: ATAS brings its own 1.5, and 6 > 1.5 x 2
  const three = { c: 100, fp: [[100, 1, 3], [100.25, 1, 3], [100.5, 1, 3]] };                   // asks exactly 3x the bid below
  const stack = (ex, ratio) => { const { ctx, log } = recorder(); footprint(ex, ratio).extras(ctx, three, 200, 40, 10); return log.filter((l) => l[0] === 'moveTo').length; };
  assert.equal(stack({ stack: 3 }), 1);
  assert.equal(stack({ stack: 3, imb: 'atas' }, 3.5), 0);
  assert.equal(stack({ stack: 2, imb: 'atas' }), 1);                                              // default ratio: ATAS's 1.5 flags a 3x ask (two rows, the bottom edge is skipped)
  assert.equal(stack({ stack: 3, imb: 'atas', ratio: 2 }, 3.5), 0);                              // ratio is the footprint's own, not ex.ratio
  const four = [...three.fp, [100.75, 1, 3]];                                                    // sierra skips the bottom row (nothing below it): 3 left in a row
  assert.equal(footprint({ stack: 3, imb: 'sierra' }, 2).imb(four, TICK).runs.length, 1);
  assert.equal(footprint({ stack: 3, imb: 'sierra' }, 2).imb(three.fp, TICK).runs.length, 0);
  assert.equal(footprint({}).imb(three.fp, TICK), null);                                         // today's rule: draw keeps its own code
  assert.equal(footprint({ imb: 'atas' }, 0).imb(three.fp, TICK).rows.length, 0);                // ratio off stays off
});

test('profile method: sierra / tv use that app\'s POC rule; homebase and unset keep the server\'s', () => {
  const p = new Profile(P);
  p.series = series; p.tick = 1;
  p.p = { poc: 99, vah: 101, val: 99, rows: [[99, 9], [100, 5], [101, 9], [102, 5], [103, 9]] };
  const run = (ex) => {
    const { ctx, log } = recorder();
    p.ex = ex;
    p.draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 600 } }) });
    let fill; const out = [];
    for (const l of log) { if (l[0] === 'set fillStyle') fill = l[1]; if (l[0] === 'fillRect') out.push([fill, l[2]]); }
    return out;
  };
  const pocY = (r) => r.find((x) => x[0] === 'POC')[1];
  assert.equal(pocY(run({})), series.priceToCoordinate(99) - 1.75);
  assert.deepEqual(run({ method: 'homebase' }), run({}));
  assert.equal(pocY(run({ method: 'sierra' })), series.priceToCoordinate(101) - 1.75);          // nearest the middle of the profile
  assert.equal(pocY(run({ method: 'tv' })), series.priceToCoordinate(99) - 1.75);               // tv: the lowest of the tie
});
