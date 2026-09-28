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
  assert.deepEqual(S.labelAnchor('hline', hs, 'middle', 400), { x: 200, y: 200, baseline: 'middle' });
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
  assert.deepEqual(S.DEFAULTS.hline, { width: 1, lineStyle: 'solid', axisLabel: true, text: '', fontSize: 12,
    textColor: '#2962FF', bold: false, labelPos: 'above' });
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
