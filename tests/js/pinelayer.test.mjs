import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const P = require('../../homebase/static/charts/pinelayer.js');

const T = 1_790_000_000_000, M = 60_000;
const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test('parseColor: hex, hex with alpha, rgba; na draws nothing, a colour left out takes the default', () => {
  assert.equal(P.parseColor('#2962FF'), 'rgba(41,98,255,1)');
  assert.equal(P.parseColor('#2962FF33'), 'rgba(41,98,255,0.2)');
  assert.equal(P.parseColor('#f00'), 'rgba(255,0,0,1)');
  assert.equal(P.parseColor('#f008'), 'rgba(255,0,0,0.533)');
  assert.equal(P.parseColor('rgba(10, 20, 30, 0.5)'), 'rgba(10,20,30,0.5)');
  assert.equal(P.parseColor('rgb(10,20,30)'), 'rgba(10,20,30,1)');
  assert.equal(P.parseColor('rgba(1,2,3,7)'), 'rgba(1,2,3,1)');                 // alpha clamped
  assert.equal(P.parseColor(null, '#000'), null);                                // na stays na
  assert.equal(P.parseColor(undefined), null);
  assert.equal(P.parseColor('', 'rgba(0,0,0,1)'), 'rgba(0,0,0,1)');             // left out: Pine's own colour
  assert.equal(P.parseColor('', undefined), null);
  assert.equal(P.parseColor('not a colour', 'x'), 'x');
});

test('textPx: Pine sizes and plain numbers', () => {
  assert.deepEqual(['auto', 'tiny', 'small', 'normal', 'large', 'huge'].map(P.textPx), [12, 8, 10, 12, 16, 24]);
  assert.equal(P.textPx(14), 14);
  assert.equal(P.textPx('size.wat'), 12);
  assert.equal(P.textPx(undefined), 12);
  assert.deepEqual([P.dashOf('style_dashed'), P.dashOf('style_dotted'), P.dashOf('style_solid'), P.dashOf(undefined)], [[6, 4], [2, 3], [], []]);
});

test('newest keeps the last 500 of a list; outside skips what is wholly past the pane', () => {
  const a = Array.from({ length: 700 }, (_, i) => i);
  const n = P.newest(a);
  assert.equal(n.length, 500);
  assert.equal(n[0], 200);
  assert.equal(n[499], 699);
  assert.equal(P.newest([1, 2, 3]).length, 3);
  assert.equal(P.newest(a, 2).join(), '698,699');
  assert.equal(P.outside(-200, -100, 1000), true);
  assert.equal(P.outside(1100, 1200, 1000), true);
  assert.equal(P.outside(-200, 10, 1000), false);                                // reaches the pane
  assert.equal(P.outside(-30, 1030, 1000), false);                               // inside the margin
});

test('baseIndex: the chart bar bar_index 0 is, also before the first bar', () => {
  const bars = Array.from({ length: 5 }, (_, i) => ({ ms: T + i * M }));
  assert.equal(P.baseIndex(bars, T + 2 * M, M), 2);
  assert.equal(P.baseIndex(bars, T + 2 * M + 1, M), 2);                          // inside a bar: that bar
  assert.equal(P.baseIndex(bars, T, M), 0);
  assert.equal(P.baseIndex(bars, T + 9 * M, M), 4);                              // past the last: the last
  assert.equal(P.baseIndex(bars, T - 3 * M, M), -3);                             // before them all: counted back
  assert.equal(P.baseIndex(bars, T - 3 * M, 0), 0);                              // not time bars: no way to count
});

const frame = (extra = {}) => ({ bars: Array.from({ length: 10 }, (_, i) => ({ ms: T + i * M })), barMs: M, end: T + 10 * M, base: 2, ...extra });

test('logicalOf: bar_index counts from the base bar (a future one runs past the last bar), bar_time sits on the bar', () => {
  const f = frame();
  assert.equal(P.logicalOf(0, 'bi', f), 2);
  assert.equal(P.logicalOf(5, undefined, f), 7);
  assert.equal(P.logicalOf(12, 'bi', f), 14);                                    // past the last bar
  assert.equal(P.logicalOf(-1, 'bi', f), 1);
  near(P.logicalOf(T + 3 * M, 'bt', f), 3);                                      // a bar's open time = its centre
  near(P.logicalOf(T + 3 * M + M / 2, 'bt', f), 3.5);
  near(P.logicalOf(T + 12 * M, 'bar_time', f), 12);                              // time bars step on past the last bar
  assert.equal(P.logicalOf(null, 'bi', f), null);                                // na
  assert.equal(P.logicalOf(NaN, 'bt', f), null);
});

test('extendSpan: pushes a segment along its slope to the pane edges; a vertical one stays; the ends keep their order', () => {
  const E = P.EDGE;
  assert.deepEqual(P.extendSpan(100, 50, 200, 50, 0, 0, 1000), [100, 50, 200, 50]);
  assert.deepEqual(P.extendSpan(100, 50, 200, 50, 0, 1, 1000), [100, 50, 1000 + E, 50]);
  assert.deepEqual(P.extendSpan(100, 50, 200, 50, 1, 0, 1000), [-E, 50, 200, 50]);
  assert.deepEqual(P.extendSpan(100, 50, 200, 50, 1, 1, 1000), [-E, 50, 1000 + E, 50]);
  const s = P.extendSpan(100, 0, 200, 100, 0, 1, 1000);                          // slope 1
  assert.deepEqual(s, [100, 0, 1000 + E, 900 + E]);
  const r = P.extendSpan(200, 100, 100, 0, 0, 1, 1000);                          // same segment, ends swapped: "right" is still its right end
  assert.deepEqual(r, [1000 + E, 900 + E, 100, 0]);
  assert.deepEqual(P.extendSpan(100, 0, 100, 80, 1, 1, 1000), [100, 0, 100, 80]);
  assert.deepEqual(P.extendSpan(100, 0, 2000, 80, 0, 1, 1000), [100, 0, 2000, 80]); // already past the edge
});

test('lineSeg: a line object in pixels with its extend; na or a missing end gives null', () => {
  const f = frame({ XI: (i) => i * 100 + 50, Y: (p) => (200 - p) * 4 });
  const s = P.lineSeg({ x1: 0, y1: 100, x2: 1, y2: 100, xloc: 'bi', extend: 'r' }, f, 1000);
  assert.deepEqual(s.a, [250, 400, 350, 400]);
  assert.deepEqual(s.s, [250, 400, 1000 + P.EDGE, 400]);
  const t = P.lineSeg({ x1: T + 3 * M, y1: 100, x2: T + 5 * M, y2: 101, xloc: 'bt', extend: 'none' }, f, 1000);
  assert.deepEqual(t.a, [350, 400, 550, 396]);
  assert.equal(P.lineSeg({ x1: 0, y1: null, x2: 1, y2: 100, xloc: 'bi', extend: 'none' }, f, 1000), null);
  assert.equal(P.lineSeg({ x1: 0, y1: 100, x2: null, y2: 100, xloc: 'bi', extend: 'none' }, f, 1000), null);
});

test('fillQuad: the area between two segments over the x range they share', () => {
  assert.deepEqual(P.fillQuad([0, 0, 100, 0], [0, 50, 100, 50]), [[0, 0], [100, 0], [100, 50], [0, 50]]);
  assert.deepEqual(P.fillQuad([0, 0, 100, 0], [50, 10, 200, 10]), [[50, 0], [100, 0], [100, 10], [50, 10]]);
  assert.equal(P.fillQuad([0, 0, 40, 0], [50, 10, 200, 10]), null);              // no x in common
  assert.deepEqual(P.fillQuad([100, 0, 0, 0], [0, 50, 100, 50])[0], [0, 0]);     // either direction
});

test('labelRect and placeText: the bubble sits by its style, the text by its alignment', () => {
  assert.deepEqual(P.labelRect('style_label_down', 100, 200, 20, 10), { x: 90, y: 184, w: 20, h: 10, point: 'down' });
  assert.deepEqual(P.labelRect('style_label_up', 100, 200, 20, 10), { x: 90, y: 206, w: 20, h: 10, point: 'up' });
  assert.deepEqual(P.labelRect('style_label_left', 100, 200, 20, 10), { x: 106, y: 195, w: 20, h: 10, point: 'left' });
  assert.deepEqual(P.labelRect('style_label_right', 100, 200, 20, 10), { x: 74, y: 195, w: 20, h: 10, point: 'right' });
  assert.deepEqual(P.labelRect('style_label_lower_left', 100, 200, 20, 10), { x: 100, y: 190, w: 20, h: 10, point: null });
  assert.deepEqual(P.labelRect('style_label_upper_right', 100, 200, 20, 10), { x: 80, y: 200, w: 20, h: 10, point: null });
  assert.deepEqual(P.labelRect('style_label_center', 100, 200, 20, 10), { x: 90, y: 195, w: 20, h: 10, point: null });
  assert.equal(P.labelRect('style_nonsense', 100, 200, 20, 10).point, 'down');   // unknown: the default style
  const r = { x: 0, y: 0, w: 100, h: 50 };
  assert.deepEqual(P.placeText('left', 'top', r, 12), { x: 4, top: 4 });
  assert.deepEqual(P.placeText('right', 'bottom', r, 12), { x: 96, top: 34 });
  assert.deepEqual(P.placeText('center', 'center', r, 10), { x: 50, top: 20 });
  assert.deepEqual(P.placeText(undefined, undefined, r, 10), { x: 50, top: 20 });
});

const w6 = (s) => s.length * 6;
const cell = (text, extra = {}) => ({ text, text_size: 'normal', ...extra });

test('tableLayout: columns and rows as big as their cells, in the table\'s corner', () => {
  const t = { position: 'top_left', columns: 2, rows: 1, cells: [[cell('A'), cell('BB')]] };
  const L = P.tableLayout(t, w6, 1000, 800);
  assert.deepEqual([L.x, L.y, L.w, L.h], [4, 4, 34, 23]);                        // 6+8 and 12+8 wide, 12*1.25+8 high
  assert.deepEqual(L.cells.map((c) => [c.x, c.y, c.w, c.h]), [[4, 4, 14, 23], [18, 4, 20, 23]]);
  const at = (position) => { const r = P.tableLayout({ ...t, position }, w6, 1000, 800); return [r.x, r.y]; };
  assert.deepEqual(at('top_right'), [962, 4]);
  assert.deepEqual(at('top_center'), [483, 4]);
  assert.deepEqual(at('middle_left'), [4, 388.5]);
  assert.deepEqual(at('middle_center'), [483, 388.5]);
  assert.deepEqual(at('bottom_left'), [4, 773]);
  assert.deepEqual(at('bottom_right'), [962, 773]);
  assert.deepEqual(at(undefined), [962, 4]);                                      // Pine's default corner
});

test('tableLayout: the widest cell of a column wins, multi-line text is taller, a cell\'s own width and height are percents of the pane', () => {
  const t = { position: 'top_left', columns: 2, rows: 2, cells: [
    [cell('a'), cell('x\ny')],
    [cell('long text'), null]] };
  const L = P.tableLayout(t, w6, 1000, 800);
  assert.equal(L.cells.length, 3);                                                 // an empty cell is skipped
  assert.deepEqual([L.w, L.h], [62 + 14, 38 + 23]);                                // 'long text' 62 wide; two lines 2*15+8 high
});

test('tableLayout: merged cells span their columns and widen the last one when their text needs more; nothing to lay out gives null', () => {
  const t = { position: 'top_left', columns: 2, rows: 2, merges: [{ startCol: 0, startRow: 0, endCol: 1, endRow: 0 }],
    cells: [[cell('Title'), cell('covered')], [cell('A'), cell('BB')]] };
  const L = P.tableLayout(t, w6, 1000, 800);
  assert.deepEqual(L.cells.map((c) => [c.cell.text, c.x, c.y, c.w, c.h]),
    [['Title', 4, 4, 38, 23], ['A', 4, 27, 14, 23], ['BB', 18, 27, 24, 23]]);      // 'Title' 38 wide > 14 + 20: the last column gets +4
  assert.equal(P.tableLayout({ columns: 0, rows: 3, cells: [] }, w6, 1000, 800), null);
  assert.equal(P.tableLayout({ columns: 2, rows: 2 }, w6, 1000, 800).cells.length, 0);
  const own = P.tableLayout({ columns: 1, rows: 1, position: 'top_left', cells: [[cell('x', { width: 10, height: 5 })]] }, w6, 1000, 800);
  assert.deepEqual([own.w, own.h], [100, 40]);
});

test('bgRuns: bars of one colour make one stripe, a gap or a new colour starts the next', () => {
  const bars = Array.from({ length: 8 }, (_, i) => ({ ms: i }));
  const col = { 1: 'r', 2: 'r', 3: 'g', 5: 'g', 6: 'g' };
  const XI = (i) => i * 100 + 50;
  assert.deepEqual(P.bgRuns(bars, 0, 7, (b) => col[b.ms], XI, 50), [
    { x0: 100, x1: 300, c: 'r' }, { x0: 300, x1: 400, c: 'g' }, { x0: 500, x1: 700, c: 'g' }]);
  assert.deepEqual(P.bgRuns(bars, 2, 3, (b) => col[b.ms], XI, 50), [{ x0: 200, x1: 300, c: 'r' }, { x0: 300, x1: 400, c: 'g' }]);
  assert.deepEqual(P.bgRuns(bars, 0, 7, () => undefined, XI, 50), []);
  assert.deepEqual(P.bgRuns(bars, 0, 3, (b) => 'r', (i) => (i === 2 ? null : i * 100), 50).length, 2);   // a bar with no x splits the run
});

/* ------------------------------------------------------------ the layer against a recording canvas */

class Ctx {
  constructor() { this.ops = []; this.fillStyle = ''; this.strokeStyle = ''; this.lineWidth = 1; this.dash = []; this.font = ''; }
  rec(op, ...a) { this.ops.push({ op, a, fill: this.fillStyle, stroke: this.strokeStyle, lw: this.lineWidth, dash: this.dash, font: this.font }); }
  setLineDash(d) { this.dash = d; }
  measureText(s) { return { width: String(s).length * 6 }; }
  fillRect(...a) { this.rec('fillRect', ...a); }
  strokeRect(...a) { this.rec('strokeRect', ...a); }
  fillText(...a) { this.rec('fillText', ...a); }
  roundRect(...a) { this.rec('roundRect', ...a); }
  beginPath() { this.rec('beginPath'); }
  closePath() { this.rec('closePath'); }
  moveTo(...a) { this.rec('moveTo', ...a); }
  lineTo(...a) { this.rec('lineTo', ...a); }
  quadraticCurveTo(...a) { this.rec('quadraticCurveTo', ...a); }
  arc(...a) { this.rec('arc', ...a); }
  rect(...a) { this.rec('rect', ...a); }
  fill() { this.rec('fill'); }
  stroke() { this.rec('stroke'); }
  of(op) { return this.ops.filter((o) => o.op === op); }
}

function load() {
  const path = require.resolve('../../homebase/static/charts/pinelayer.js');
  class Layer {
    constructor(P0) { this.P = P0; }
    attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
    detached() { this.chart = this.series = null; }
    paneViews() { return this._views; }
    redraw() { if (this.requestUpdate) this.requestUpdate(); }
    spacing() { const ts = this.chart.timeScale(); return ts.logicalToCoordinate(1) - ts.logicalToCoordinate(0); }
  }
  globalThis.window = { HBLayers: { Layer } };
  delete require.cache[path];
  return require(path);
}

/* 10 one-minute bars 100 px apart (bar i centred on 100i + 50); price p is y = (200 - p) * 4; bar i spans 100+i .. 110+i. */
function rig() {
  const H = load();
  const host = { bars: Array.from({ length: 10 }, (_, i) => ({ ms: T + i * M, l: 100 + i, h: 110 + i })), barMs: () => M };
  const ts = { getVisibleLogicalRange: () => ({ from: 0, to: 10 }), logicalToCoordinate: (i) => i * 100 + 50 };
  const series = { priceToCoordinate: (p) => (200 - p) * 4 };
  const layer = new H.PineLayer({}, host);
  let redraws = 0;
  layer.attached({ chart: { timeScale: () => ts }, series, requestUpdate: () => { redraws++; } });
  const views = layer.paneViews();
  const draw = (view) => {
    const ctx = new Ctx();
    views[view].renderer().draw({ useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 1000, height: 800 } }) });
    return ctx;
  };
  return { H, host, layer, views, ts, draw, redraws: () => redraws };
}
const unload = () => { delete globalThis.window; };

test('the layer: two views, stripes behind the candles and the drawings on top; update asks for a redraw', () => {
  const { layer, views, redraws } = rig();
  try {
    assert.equal(views.length, 2);
    assert.deepEqual(views.map((v) => v.zOrder()), ['bottom', 'top']);
    layer.update({ firstMs: T, boxes: [] });
    assert.equal(redraws(), 1);
    layer.update(null);
    assert.equal(redraws(), 1);
  } finally { unload(); }
});

test('the layer draws nothing before a result, without a chart, or when there is nothing to draw', () => {
  const { layer, draw, host } = rig();
  try {
    assert.equal(draw(1).ops.length, 0);                                          // no result yet
    layer.update({ firstMs: T, full: true, boxes: [], lines: [] });
    assert.equal(draw(1).ops.length, 0);                                          // empty lists
    layer.update({ firstMs: T, full: true, lines: [{ x1: 0, y1: 100, x2: 1, y2: 100, xloc: 'bi', extend: 'none', color: '#FF0000', style: 'style_solid', width: 1 }] });
    assert.ok(draw(1).ops.length > 0);
    host.bars = [];
    assert.equal(draw(1).ops.length, 0);                                          // no bars
    host.bars = [{ ms: T, l: 1, h: 2 }];
    layer.detached();
    assert.equal(draw(1).ops.length, 0);                                          // detached
    assert.equal(draw(0).ops.length, 0);
  } finally { unload(); }
});

test('boxes: bar_index from the run\'s first bar, Pine colours, border, text; extend reaches the pane edge; far ones are culled', () => {
  const { layer, draw } = rig();
  try {
    layer.update({ firstMs: T + 2 * M, full: true, boxes: [
      { left: 1, right: 3, top: 110, bottom: 100, xloc: 'bi', extend: 'none', border_color: '#FF0000', border_style: 'style_dashed', border_width: 2,
        bgcolor: '#2962FF33', text: 'Zone', text_color: '#00FF00', text_size: 'normal', text_halign: 'center', text_valign: 'center' },
      { left: 0, right: 1, top: 120, bottom: 119, xloc: 'bi', extend: 'right', border_color: '', border_width: 0, bgcolor: '#2962ff', text: '' },
      { left: 400, right: 410, top: 110, bottom: 100, xloc: 'bi', extend: 'none', bgcolor: '#2962ff' },      // 2 bars + 400 columns away
      { left: 1, right: 3, top: null, bottom: 100, xloc: 'bi', bgcolor: '#2962ff' }] });                    // na price
    const c = draw(1);
    const fills = c.of('fillRect');
    assert.equal(fills.length, 2);
    assert.deepEqual(fills[0].a, [350, 360, 200, 40]);                             // bars 3..5, price 110..100
    assert.equal(fills[0].fill, 'rgba(41,98,255,0.2)');
    assert.deepEqual(fills[1].a, [250, 320, 1000 + P.EDGE - 250, 4]);              // extended right to the pane edge
    const border = c.of('strokeRect');
    assert.equal(border.length, 1);                                                // the second box has no border width
    assert.deepEqual(border[0].a, [350, 360, 200, 40]);
    assert.equal(border[0].stroke, 'rgba(255,0,0,1)');
    assert.equal(border[0].lw, 2);
    assert.deepEqual(border[0].dash, [6, 4]);
    const txt = c.of('fillText');
    assert.equal(txt.length, 1);
    assert.equal(txt[0].a[0], 'Zone');
    assert.equal(txt[0].fill, 'rgba(0,255,0,1)');
    assert.equal(txt[0].a[1], 450);                                                // centred in the box
  } finally { unload(); }
});

test('lines: a bar_time line lands on its bars, extend both runs to both edges, arrows and styles', () => {
  const { layer, draw } = rig();
  try {
    layer.update({ firstMs: T, full: true, lines: [
      { x1: T + 3 * M, y1: 100, x2: T + 5 * M, y2: 101, xloc: 'bt', extend: 'none', color: '#FF0000', style: 'style_dotted', width: 3 },
      { x1: 1, y1: 105, x2: 2, y2: 105, xloc: 'bi', extend: 'both', color: '', style: 'style_arrow_right', width: 1 },
      { x1: 1, y1: null, x2: 2, y2: 105, xloc: 'bi', extend: 'none', color: '#FF0000' },                     // na: skipped
      { x1: 1, y1: 105, x2: 2, y2: 105, xloc: 'bi', extend: 'none', color: null }] });                      // color na: skipped
    const c = draw(1);
    const strokes = c.of('stroke');
    assert.equal(strokes.length, 2);
    assert.deepEqual(c.of('moveTo')[0].a, [350, 400]);
    assert.deepEqual(c.of('lineTo')[0].a, [550, 396]);
    assert.equal(strokes[0].stroke, 'rgba(255,0,0,1)');
    assert.equal(strokes[0].lw, 3);
    assert.deepEqual(strokes[0].dash, [2, 3]);
    assert.deepEqual(c.of('moveTo')[1].a, [-P.EDGE, 380]);                         // both: from the left edge ...
    assert.deepEqual(c.of('lineTo')[1].a, [1000 + P.EDGE, 380]);                   // ... to the right one
    assert.equal(strokes[1].stroke, '#2962FF');                                    // no colour: Pine blue
    assert.equal(c.of('fill').length, 1);                                          // the one arrow head (style_arrow_right)
    assert.deepEqual(c.of('moveTo')[2].a, [250, 380]);                             // ... on the line's second point
  } finally { unload(); }
});

test('labels: bubble by style with its pointer, text in Pine\'s colours, abovebar / belowbar on the bar\'s high / low, shapes', () => {
  const { layer, draw } = rig();
  try {
    layer.update({ firstMs: T, full: true, labels: [
      { x: 3, y: 105, text: 'Hi', xloc: 'bi', yloc: 'pr', color: '#FF0000', style: 'style_label_down', textcolor: '', size: 'normal', textalign: 'center' },
      { x: 3, y: 0, text: 'Top', xloc: 'bi', yloc: 'ab', color: '#00FF00', style: 'style_label_up', textcolor: '#000000', size: 'normal', textalign: 'center' },
      { x: 3, y: 0, text: '', xloc: 'bi', yloc: 'bl', color: '#0000FF', style: 'style_circle', textcolor: '', size: 'normal' },
      { x: 4, y: 105, text: 'plain', xloc: 'bi', yloc: 'pr', color: '', style: 'style_none', textcolor: '#112233', size: 'small', textalign: 'center' },
      { x: 3, y: null, text: 'na', xloc: 'bi', yloc: 'pr', style: 'style_label_down' }] });
    const c = draw(1);
    const bubbles = c.of('roundRect');
    assert.equal(bubbles.length, 2);
    assert.deepEqual(bubbles[0].a, [340, (200 - 105) * 4 - 6 - 23, 20, 23, 3]);   // 'Hi' = 12 + 8 wide, 23 high, over the point (350, 380)
    assert.equal(bubbles[0].fill, 'rgba(255,0,0,1)');
    assert.deepEqual(bubbles[1].a, [350 - (18 + 8) / 2, (200 - 113) * 4 + 6, 26, 23, 3]);   // bar 3's high is 113
    const texts = c.of('fillText');
    assert.deepEqual(texts.map((t) => t.a[0]), ['Hi', 'Top', 'plain']);
    assert.equal(texts[0].fill, '#FFFFFF');                                         // no textcolor: white
    assert.equal(texts[1].fill, 'rgba(0,0,0,1)');
    assert.equal(texts[2].fill, 'rgba(17,34,51,1)');
    assert.match(texts[2].font, /^10px /);                                         // size.small
    const arcs = c.of('arc');
    assert.equal(arcs.length, 1);
    assert.deepEqual(arcs[0].a.slice(0, 2), [350, (200 - 103) * 4]);               // belowbar: bar 3's low is 103
    assert.equal(arcs[0].fill, 'rgba(0,0,255,1)');
    assert.equal(c.of('fill').length, 5);                                          // 2 bubbles + their 2 pointers + the circle
  } finally { unload(); }
});

test('linefills and polylines', () => {
  const { layer, draw } = rig();
  try {
    const l1 = { x1: 0, y1: 110, x2: 4, y2: 110, xloc: 'bi', extend: 'none', color: '#FF0000' };
    const l2 = { x1: 0, y1: 100, x2: 4, y2: 100, xloc: 'bi', extend: 'none', color: '#FF0000' };
    layer.update({ firstMs: T, full: true,
      linefills: [{ line1: l1, line2: l2, color: '#FF000033' }, { line1: l1, line2: { ...l2, x1: 50, x2: 60 }, color: '#FF000033' }],
      polylines: [
        { points: [{ index: 1, price: 100 }, { index: 2, price: 110 }, { index: 3, price: 100 }], curved: false, closed: true, xloc: 'bi',
          line_color: '#0000FF', fill_color: '#0000FF22', line_style: 'style_solid', line_width: 2 },
        { points: [{ time: T + 1 * M, price: 100 }, { time: T + 2 * M, price: 110 }, { time: T + 3 * M, price: 100 }], curved: true, closed: false, xloc: 'bt',
          line_color: '#00FF00', fill_color: '', line_style: 'style_solid', line_width: 1 }] });
    const c = draw(1);
    const fills = c.ops.filter((o) => o.op === 'fill');
    assert.equal(fills[0].fill, 'rgba(255,0,0,0.2)');                              // the linefill; the second one shares no x
    assert.deepEqual(c.ops.filter((o) => o.op === 'moveTo' || o.op === 'lineTo').slice(0, 4).map((o) => o.a),
      [[50, 360], [450, 360], [450, 400], [50, 400]]);
    assert.equal(fills.filter((f) => f.fill === 'rgba(255,0,0,0.2)').length, 1);
    assert.equal(fills.filter((f) => f.fill === 'rgba(0,0,255,0.133)').length, 1);   // the closed polyline's fill
    assert.equal(c.of('quadraticCurveTo').length, 1);                              // the curved one bends at its middle point
    assert.deepEqual(c.of('quadraticCurveTo')[0].a, [250, 360, 300, 380]);
    assert.equal(c.of('stroke').filter((s) => s.stroke === 'rgba(0,255,0,1)').length, 1);
    assert.equal(c.of('stroke').filter((s) => s.stroke === 'rgba(0,0,255,1)').length, 1);
  } finally { unload(); }
});

test('tables: drawn in their corner with cell backgrounds and text; a later table in a corner replaces the earlier', () => {
  const { layer, draw } = rig();
  try {
    const table = (position, text) => ({ position, columns: 2, rows: 1, bgcolor: '#222222', frame_color: '#FFFFFF', frame_width: 1, border_color: '#888888', border_width: 1,
      cells: [[{ text, text_size: 'normal', text_color: '', bgcolor: '#FF0000', text_halign: 'center', text_valign: 'center' },
        { text: 'BB', text_size: 'normal', text_color: '#00FF00', bgcolor: '', text_halign: 'right', text_valign: 'center' }]] });
    layer.update({ firstMs: T, full: true, tables: [table('top_left', 'old'), table('bottom_right', 'A'), table('top_left', 'A')] });
    const c = draw(1);
    assert.equal(layer.o.tables.length, 2);
    assert.deepEqual(c.of('fillText').map((t) => t.a[0]), ['A', 'BB', 'A', 'BB']);
    const rects = c.of('fillRect');
    assert.deepEqual(rects[0].a, [4, 4, 34, 23]);                                  // the whole table, top left
    assert.equal(rects[0].fill, 'rgba(34,34,34,1)');
    assert.deepEqual(rects[1].a, [4, 4, 14, 23]);                                  // the first cell's own background
    assert.equal(rects[1].fill, 'rgba(255,0,0,1)');
    assert.equal(c.of('fillText')[0].fill, '#000000');                                // no text_color: black
    assert.equal(c.of('fillText')[1].fill, 'rgba(0,255,0,1)');
    assert.equal(c.of('fillText')[1].a[1], 38 - 4);                                // right-aligned inside its cell
    assert.deepEqual(c.of('strokeRect').filter((s) => s.stroke === 'rgba(255,255,255,1)')[0].a, [4, 4, 34, 23]);
    const bottom = rects.find((r) => r.a[0] === 962);
    assert.deepEqual(bottom.a, [962, 773, 34, 23]);
  } finally { unload(); }
});

test('bgcolor stripes: runs of bars drawn full height; a partial result merges by bar and an off bar clears its stripe', () => {
  const { layer, draw } = rig();
  try {
    const pt = (i, color) => ({ time: T + i * M, value: null, ...(color ? { color } : {}) });
    layer.update({ firstMs: T, full: true, plotsMeta: { bg: { style: 'background' }, rsi: { style: 'line' } },
      plots: { bg: [pt(3, '#FF000033'), pt(4, '#FF000033'), pt(5), pt(6, '#FF000033')], rsi: [{ time: T, value: 50 }] } });
    let r = draw(0).of('fillRect');
    assert.deepEqual(r.map((o) => o.a), [[300, 0, 200, 800], [600, 0, 100, 800]]);
    assert.equal(r[0].fill, 'rgba(255,0,0,0.2)');
    assert.equal(draw(1).ops.length, 0);                                           // stripes are not on the top view
    layer.update({ firstMs: T, full: false, plotsMeta: { bg: { style: 'background' } }, plots: { bg: [pt(4), pt(7, '#00FF0033')] } });
    r = draw(0).of('fillRect');
    assert.deepEqual(r.map((o) => o.a), [[300, 0, 100, 800], [600, 0, 100, 800], [700, 0, 100, 800]]);
    assert.deepEqual(r.map((o) => o.fill), ['rgba(255,0,0,0.2)', 'rgba(255,0,0,0.2)', 'rgba(0,255,0,0.2)']);
    layer.update({ firstMs: T, full: true, plotsMeta: { bg: { style: 'background' } }, plots: { bg: [pt(1, '#0000FF33')] } });
    assert.deepEqual(draw(0).of('fillRect').map((o) => o.a), [[100, 0, 100, 800]]);   // a full result starts again
    layer.update({ firstMs: T, full: true, plotsMeta: {}, plots: {} });
    assert.equal(draw(0).ops.length, 0);
  } finally { unload(); }
});

test('the 500 cap: only the newest 500 of a kind are kept and drawn', () => {
  const { layer, draw } = rig();
  try {
    const lines = Array.from({ length: 700 }, (_, i) => ({ x1: 0, y1: 100 + (i % 10), x2: 1, y2: 100 + (i % 10), xloc: 'bi', extend: 'none', color: '#FF0000', width: 1 + (i < 200 ? 4 : 0) }));
    layer.update({ firstMs: T, full: true, lines });
    assert.equal(layer.o.lines.length, 500);
    assert.equal(layer.o.lines[0], lines[200]);
    assert.equal(draw(1).of('stroke').length, 500);
    assert.ok(draw(1).of('stroke').every((s) => s.lw === 1));                       // none of the 200 oldest
  } finally { unload(); }
});

test('the view is the culling window: a drawing wholly past the pane is skipped, one reaching into it is drawn', () => {
  const { layer, draw } = rig();
  try {
    const line = (x1, x2) => ({ x1, y1: 105, x2, y2: 105, xloc: 'bi', extend: 'none', color: '#FF0000', width: 1 });
    layer.update({ firstMs: T, full: true, lines: [line(30, 40), line(8, 40), line(-40, -30), line(-40, 1)] });
    assert.deepEqual(draw(1).of('moveTo').map((m) => m.a[0]), [850, -3950]);
  } finally { unload(); }
});
