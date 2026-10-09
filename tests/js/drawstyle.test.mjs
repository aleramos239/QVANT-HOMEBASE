import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const S = require('../../homebase/static/charts/drawstyle.js');

test('every drawing type has a default style with exactly its own fields', () => {
  for (const type of ['trend', 'hline']) {
    const d = S.normalize(type, {});
    assert.deepEqual(Object.keys(d).sort(), [...S.FIELDS[type]].sort());
    assert.deepEqual(d, S.DEFAULTS[type]);
  }
  // rect's fillColor has no built-in default (unset = follow the theme's own accentSoft): the
  // review finding this fixes is exactly that a fixed default here was wrong in dark theme
  const rect = S.normalize('rect', {});
  assert.deepEqual(Object.keys(rect).sort(), S.FIELDS.rect.filter((k) => k !== 'fillColor').sort());
  assert.deepEqual(rect, S.DEFAULTS.rect);
  assert.equal('fillColor' in S.DEFAULTS.rect, false);
  assert.deepEqual(S.normalize('long', {}), {});
  assert.deepEqual(S.normalize('short', { width: 3 }), {});   // long/short take no style fields at all
});

test('normalize falls back to the default field-by-field, never throws on junk', () => {
  assert.equal(S.normalize('trend', null).width, 2);
  assert.equal(S.normalize('trend', 'nope').width, 2);
  assert.equal(S.normalize('trend', { width: 0 }).width, 2);          // out of range -> default
  assert.equal(S.normalize('trend', { width: 3 }).width, 3);          // in range -> kept
  assert.equal(S.normalize('trend', { width: 2.5 }).width, 2);        // not an integer -> default
  assert.equal(S.normalize('trend', { lineStyle: 'wavy' }).lineStyle, 'solid');
  assert.equal(S.normalize('trend', { lineStyle: 'dotted' }).lineStyle, 'dotted');
  assert.equal(S.normalize('trend', { bold: 'yes' }).bold, false);
  assert.equal(S.normalize('trend', { bold: true }).bold, true);
  assert.equal(S.normalize('trend', { fontSize: 9 }).fontSize, 12);
  assert.equal(S.normalize('trend', { fontSize: 28 }).fontSize, 28);
  assert.equal(S.normalize('trend', { text: 'x'.repeat(201) }).text, '');
  assert.equal(S.normalize('trend', { text: 'x'.repeat(200) }).text, 'x'.repeat(200));
  // a field that DOES exist on the object but is junk for this type is simply not among the keys returned
  assert.equal('junk' in S.normalize('trend', { junk: 1 }), false);
});

test('labelPos is validated against the type\'s own vocabulary', () => {
  assert.equal(S.normalize('trend', { labelPos: 'top' }).labelPos, 'above');       // rect's word, not a line's
  assert.equal(S.normalize('trend', { labelPos: 'below' }).labelPos, 'below');
  assert.equal(S.normalize('rect', { labelPos: 'above' }).labelPos, 'top');        // a line's word, not rect's
  assert.equal(S.normalize('rect', { labelPos: 'bottom' }).labelPos, 'bottom');
  assert.deepEqual(S.LABEL_POS.trend, ['above', 'below', 'middle']);
  assert.deepEqual(S.LABEL_POS.rect, ['top', 'middle', 'bottom']);
});

test('trend/hline take no fillColor; rect takes no extendLeft/extendRight/axisLabel', () => {
  assert.equal('fillColor' in S.normalize('trend', { fillColor: '#000000' }), false);
  assert.equal('fillColor' in S.normalize('hline', { fillColor: '#000000' }), false);
  assert.equal('extendLeft' in S.normalize('rect', { extendLeft: true }), false);
  assert.equal('axisLabel' in S.normalize('rect', { axisLabel: true }), false);
  assert.equal('axisLabel' in S.normalize('trend', { axisLabel: true }), false);
});

test('isColor accepts #RRGGBB and rgba(r,g,b,a), refuses everything else', () => {
  for (const ok of ['#2962FF', '#000000', 'rgba(0,0,0,0)', 'rgba(255,255,255,1)', 'rgba(1,2,3,.5)', 'rgba(1,2,3,0.5)']) {
    assert.equal(S.isColor(ok), true, ok);
  }
  for (const bad of ['red', '#12345', '#GGGGGG', 'rgba(256,0,0,1)', 'rgba(0,0,0,1.5)', 'rgba(0,0,0)', '', null, 7]) {
    assert.equal(S.isColor(bad), false, String(bad));
  }
});

test('textColor falls back to the default on a bad colour; a bad fillColor drops the key (follows the theme)', () => {
  assert.equal('fillColor' in S.normalize('rect', { fillColor: 'green' }), false);
  assert.equal('fillColor' in S.normalize('rect', {}), false);
  assert.equal(S.normalize('trend', { textColor: 'green' }).textColor, S.DEFAULTS.trend.textColor);
  assert.equal(S.normalize('rect', { fillColor: 'rgba(0,150,0,.3)' }).fillColor, 'rgba(0,150,0,.3)');
});

test('starting() merges a preset over the built-in default, still normalized', () => {
  assert.deepEqual(S.starting('trend', null), S.DEFAULTS.trend);
  assert.equal(S.starting('trend', { width: 4 }).width, 4);
  assert.equal(S.starting('trend', { width: 4 }).lineStyle, S.DEFAULTS.trend.lineStyle);   // untouched fields stay default
  assert.equal(S.starting('trend', { width: 99 }).width, S.DEFAULTS.trend.width);          // an invalid preset field is dropped
  assert.equal(S.starting('trend', { junk: 1 }).width, S.DEFAULTS.trend.width);
  assert.deepEqual(S.starting('long', { width: 4 }), {});
});

test('dashFor: solid/dashed/dotted map to canvas dash arrays, anything else is solid', () => {
  assert.deepEqual(S.dashFor({ lineStyle: 'solid' }), []);
  assert.deepEqual(S.dashFor({ lineStyle: 'dashed' }), [6, 4]);
  assert.deepEqual(S.dashFor({ lineStyle: 'dotted' }), [1, 3]);
  assert.deepEqual(S.dashFor({}), []);
  assert.deepEqual(S.dashFor(null), []);
});

test('labelAnchor: hline centres on the pane, above/below/middle the line', () => {
  const hs = [[50, 200]];   // hline's one handle: [x, y]
  assert.deepEqual(S.labelAnchor('hline', hs, 'middle', 400), { x: 200, y: 200, baseline: 'middle', align: 'center' });
  const above = S.labelAnchor('hline', hs, 'above', 400);
  assert.equal(above.baseline, 'bottom');
  assert.ok(above.y < 200);
  const below = S.labelAnchor('hline', hs, 'below', 400);
  assert.equal(below.baseline, 'top');
  assert.ok(below.y > 200);
});

test('labelAnchor: trend anchors at the segment\'s midpoint', () => {
  const hs = [[0, 100], [100, 200]];
  const mid = S.labelAnchor('trend', hs, 'middle', 400);
  assert.deepEqual(mid, { x: 50, y: 150, baseline: 'middle' });
  assert.ok(S.labelAnchor('trend', hs, 'above', 400).y < 150);
  assert.ok(S.labelAnchor('trend', hs, 'below', 400).y > 150);
});

test('labelAnchor: rect anchors inside the box, top/middle/bottom', () => {
  const hs = [[10, 20], [110, 80], [10, 80], [110, 20]];   // handlePoints() order: [x0,y0],[x1,y1],[x0,y1],[x1,y0]
  const top = S.labelAnchor('rect', hs, 'top', 400);
  const mid = S.labelAnchor('rect', hs, 'middle', 400);
  const bot = S.labelAnchor('rect', hs, 'bottom', 400);
  assert.equal(top.x, 60); assert.equal(mid.x, 60); assert.equal(bot.x, 60);
  assert.ok(top.y > 20 && top.y < mid.y);
  assert.ok(bot.y < 80 && bot.y > mid.y);
  assert.deepEqual(mid, { x: 60, y: 50, baseline: 'middle' });
});

test('labelAnchor is null with no handle points', () => {
  assert.equal(S.labelAnchor('trend', null, 'above', 400), null);
  assert.equal(S.labelAnchor('trend', [], 'above', 400), null);
});

test('hline\'s default style renders exactly like an old, unstyled drawing (solid, width 1, axis label on)', () => {
  // labelAlign 'center' (2026-10-09) is where an old line's label always sat: the look is unchanged
  assert.deepEqual(S.DEFAULTS.hline, { width: 1, lineStyle: 'solid', axisLabel: true, text: '', fontSize: 12,
    textColor: '#2962FF', bold: false, labelPos: 'above', labelAlign: 'center' });
});

test('extendLine: no extension is a no-op', () => {
  assert.deepEqual(S.extendLine(10, 20, 30, 40, 400, false, false), [10, 20, 30, 40]);
});

test('extendLine: extends to the pane edges along the same slope, whichever endpoint is on which side', () => {
  // y = 2x + 0 through (10,20) and (30,60)
  assert.deepEqual(S.extendLine(10, 20, 30, 60, 400, true, false), [0, 0, 30, 60]);
  assert.deepEqual(S.extendLine(10, 20, 30, 60, 400, false, true), [10, 20, 400, 800]);
  assert.deepEqual(S.extendLine(10, 20, 30, 60, 400, true, true), [0, 0, 400, 800]);
  // stored right-to-left: extending "left"/"right" still means screen left/right
  assert.deepEqual(S.extendLine(30, 60, 10, 20, 400, true, false), [30, 60, 0, 0]);
  assert.deepEqual(S.extendLine(30, 60, 10, 20, 400, false, true), [400, 800, 10, 20]);
});

test('extendLine: a vertical segment cannot extend left/right', () => {
  assert.deepEqual(S.extendLine(50, 10, 50, 90, 400, true, true), [50, 10, 50, 90]);
});

test('toolbarAnchor: centred above the drawing\'s own bounding box', () => {
  assert.deepEqual(S.toolbarAnchor([[10, 20], [110, 80]]), { cx: 60, top: 20 });
  assert.deepEqual(S.toolbarAnchor([[10, 20], [110, 80], [10, 80], [110, 20]]), { cx: 60, top: 20 });
  assert.deepEqual(S.toolbarAnchor([[50, 30]]), { cx: 50, top: 30 });   // hline's one handle
  assert.equal(S.toolbarAnchor(null), null);
  assert.equal(S.toolbarAnchor([]), null);
});

test('shouldStartRuler: only the cursor tool + Shift', () => {
  assert.equal(S.shouldStartRuler('cursor', true), true);
  assert.equal(S.shouldStartRuler('cursor', false), false);
  assert.equal(S.shouldStartRuler('trend', true), false);
  assert.equal(S.shouldStartRuler('measure', true), false);
});

test('snapEndpointPrice: Shift takes the other endpoint\'s price, else the pointer\'s own', () => {
  assert.equal(S.snapEndpointPrice(100, 105, true), 100);
  assert.equal(S.snapEndpointPrice(100, 105, false), 105);
  assert.equal(S.snapEndpointPrice(100, 100, true), 100);
});

/* ---- 2026-10-09: ray, extended line, vertical line, Fib retracement; more settings; per-interval visibility ---- */
test('the new tools take exactly their own fields, and an old drawing keeps its look', () => {
  assert.deepEqual(Object.keys(S.FIELDS), ['trend', 'ray', 'xline', 'hline', 'vline', 'rect', 'fib', 'long', 'short']);
  assert.ok(!S.FIELDS.ray.includes('extendLeft') && !S.FIELDS.xline.includes('extendRight'), 'a ray and an extended line extend by what they are');
  for (const t of ['trend', 'ray', 'xline']) assert.ok(S.FIELDS[t].includes('priceLabel') && S.FIELDS[t].includes('stats'), t);
  // an old trend line / rectangle saved before these settings existed: every new switch is off
  const oldTrend = S.normalize('trend', { width: 2, lineStyle: 'solid' });
  assert.equal(oldTrend.priceLabel, false);
  assert.equal(oldTrend.stats, false);
  const oldRect = S.normalize('rect', { width: 1 });
  assert.deepEqual([oldRect.border, oldRect.midline, oldRect.quarters, oldRect.extendRight, oldRect.priceLabels], [true, false, false, false, false]);
  assert.equal(oldRect.midStyle, 'dashed');
  assert.ok(!('fillColor' in oldRect), 'still follows the theme');
  assert.equal(S.normalize('hline', {}).labelAlign, 'center');
  assert.equal(S.normalize('hline', { labelAlign: 'sideways' }).labelAlign, 'center');
  assert.equal(S.normalize('vline', {}).timeLabel, true);
  assert.deepEqual(S.normalize('long', { width: 3 }), {});
  assert.equal(S.isValidField('rect', 'midStyle', 'wavy'), false);
  assert.equal(S.isValidField('trend', 'stats', 1), false);
});

test('lineEnds: a trend line by its switches, a ray past its second point, an extended line both ways', () => {
  assert.deepEqual(S.lineEnds('trend', 10, 10, 20, 20, 100, 80, {}), [10, 10, 20, 20]);
  assert.deepEqual(S.lineEnds('trend', 10, 10, 20, 20, 100, 80, { extendRight: true }), [10, 10, 100, 100]);
  assert.deepEqual(S.lineEnds('ray', 10, 10, 20, 20, 100, 80, {}), [10, 10, 100, 100], 'drawn left to right: runs on to the right edge');
  assert.deepEqual(S.lineEnds('ray', 20, 20, 10, 10, 100, 80, {}), [20, 20, 0, 0], 'drawn right to left: runs on to the left edge');
  assert.deepEqual(S.lineEnds('xline', 10, 10, 20, 20, 100, 80, {}), [0, 0, 100, 100]);
  assert.deepEqual(S.lineEnds('ray', 10, 10, 10, 30, 100, 80, {}), [10, 10, 10, 80], 'straight down: to the bottom of the pane');
  assert.deepEqual(S.lineEnds('ray', 10, 30, 10, 10, 100, 80, {}), [10, 30, 10, 0], 'straight up: to the top');
  assert.deepEqual(S.lineEnds('xline', 10, 10, 10, 30, 100, 80, {}), [10, 0, 10, 80]);
  assert.deepEqual(S.lineEnds('ray', 10, 10, 10, 10, 100, 80, {}), [10, 10, 10, 10], 'one point: nothing to run on from');
  assert.deepEqual(S.lineEnds('rect', 1, 2, 3, 4, 100, 80, {}), [1, 2, 3, 4]);
});

test('Fib retracement: 0 on the second point, 1 on the first; levels are checked, copied and sorted', () => {
  assert.equal(S.fibPrice(100, 200, 0, false), 200);
  assert.equal(S.fibPrice(100, 200, 1, false), 100);
  assert.equal(S.fibPrice(100, 200, 0.5, false), 150);
  assert.ok(Math.abs(S.fibPrice(100, 200, 0.618, false) - 138.2) < 1e-9, 'a 61.8% pullback of an up move');
  assert.equal(S.fibPrice(100, 200, 0, true), 100, 'reversed: 0 on the first point');
  assert.ok(Math.abs(S.fibPrice(100, 200, 1.618, false) - 38.2) < 1e-9, 'an extension past the first point');
  const d = S.normalize('fib', {});
  assert.deepEqual(d.levels.map((l) => l.v), [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618]);
  assert.deepEqual(S.fibLevels(d).map((l) => l.v), [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1], '1.618 is there but off');
  assert.notEqual(d.levels, S.DEFAULTS.fib.levels, 'its own copy');
  assert.notEqual(d.levels[0], S.DEFAULTS.fib.levels[0]);
  const mine = S.normalize('fib', { levels: [{ v: 0.705, on: true, color: '#112233', junk: 1 }, { v: 0, on: true }] });
  assert.deepEqual(mine.levels, [{ v: 0, on: true, color: '#787B86' }, { v: 0.705, on: true, color: '#112233' }], 'sorted, a missing colour filled, junk dropped');
  for (const bad of [[], [{ v: 'x', on: true }], [{ v: 0.5 }], [{ v: 99, on: true }], [{ v: 0.5, on: true, color: 'red' }], Array(17).fill({ v: 0.5, on: true })]) {
    assert.deepEqual(S.normalize('fib', { levels: bad }).levels.map((l) => l.v), [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618], JSON.stringify(bad).slice(0, 40));
  }
  assert.equal(S.fibText(0.618), '0.618');
  assert.equal(S.fibText(1), '1');
  assert.equal(S.fibText(0.5), '0.5');
});

test('which intervals a drawing shows on: a range in bar seconds; tick, volume and range charts show everything', () => {
  assert.equal(S.shownOn(null, 'time:60'), true, 'no rule: everywhere');
  assert.equal(S.shownOn({ min: 300, max: 3600 }, 'time:60'), false, '1m is under 5m');
  assert.equal(S.shownOn({ min: 300, max: 3600 }, 'time:300'), true);
  assert.equal(S.shownOn({ min: 300, max: 3600 }, 'time:3600'), true);
  assert.equal(S.shownOn({ min: 300, max: 3600 }, 'time:14400'), false);
  assert.equal(S.shownOn({ min: 3600, max: null }, 'time:86400'), true, 'this interval and higher');
  assert.equal(S.shownOn({ min: null, max: 300 }, 'time:900'), false, 'this interval and lower');
  assert.equal(S.shownOn({ min: 300, max: 3600 }, 'tick:500'), true);
  assert.equal(S.shownOn({ min: 300, max: 3600 }, 'range:10'), true);
  assert.deepEqual(S.normalizeVis({ min: 60, max: 300 }), { min: 60, max: 300 });
  assert.equal(S.normalizeVis({ min: 300, max: 60 }), null, 'upside down: no rule');
  assert.equal(S.normalizeVis({ min: null, max: null }), null);
  assert.equal(S.normalizeVis({ min: 0.5 }), null);
  assert.equal(S.normalizeVis('x'), null);
  assert.equal(S.shownOn({ min: 300, max: 60 }, 'time:60'), true, 'a rule that does not read hides nothing');
});

test('labelAnchor: a horizontal line label left / centre / right; a vertical line label beside it; a ray like a trend line', () => {
  const hs = [[50, 200]];
  assert.deepEqual(S.labelAnchor('hline', hs, 'above', 400, 'left'), { x: 8, y: 192, baseline: 'bottom', align: 'left' });
  assert.deepEqual(S.labelAnchor('hline', hs, 'above', 400, 'right'), { x: 392, y: 192, baseline: 'bottom', align: 'right' });
  assert.deepEqual(S.labelAnchor('vline', [[120, 150]], 'top', 400, 'center', 300), { x: 128, y: 8, baseline: 'top', align: 'left' });
  assert.deepEqual(S.labelAnchor('vline', [[120, 150]], 'middle', 400, 'center', 300), { x: 128, y: 150, baseline: 'middle', align: 'left' });
  assert.equal(S.labelAnchor('vline', [[120, 150]], 'bottom', 400, 'center', 300).baseline, 'bottom');
  const seg = [[0, 0], [100, 50]];
  assert.deepEqual(S.labelAnchor('ray', seg, 'middle', 400), S.labelAnchor('trend', seg, 'middle', 400));
  assert.deepEqual(S.labelAnchor('xline', seg, 'above', 400), S.labelAnchor('trend', seg, 'above', 400));
});
