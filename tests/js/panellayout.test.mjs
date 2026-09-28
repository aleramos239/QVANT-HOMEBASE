import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/panellayout.js');

test('clampDockWidth holds the dock between its min and max', () => {
  assert.equal(L.clampDockWidth(320), 320);
  assert.equal(L.clampDockWidth(10), L.DOCK_W_MIN);
  assert.equal(L.clampDockWidth(9999), L.DOCK_W_MAX);
  assert.equal(L.clampDockWidth(NaN), L.DOCK_W_DEFAULT);
  assert.equal(L.clampDockWidth(undefined), L.DOCK_W_DEFAULT);
});

test('clampFloatRect keeps a floating panel fully on screen at its stored size', () => {
  const r = L.clampFloatRect({ x: 50, y: 50, w: 320, h: 480 }, 1600, 900);
  assert.deepEqual(r, { x: 50, y: 50, w: 320, h: 480 });
});

test('clampFloatRect pulls a panel back onto screen when x/y run past the far edge', () => {
  const r = L.clampFloatRect({ x: 1550, y: 850, w: 320, h: 480 }, 1600, 900);
  assert.equal(r.x, 1600 - 320);
  assert.equal(r.y, 900 - 480);
  assert.equal(r.w, 320);
  assert.equal(r.h, 480);
});

test('clampFloatRect never grows a panel to fill a tiny viewport, and never lets it go negative', () => {
  const r = L.clampFloatRect({ x: -40, y: -40, w: 320, h: 480 }, 200, 150);
  assert.equal(r.w, 200);   // the viewport itself, since it is smaller than FLOAT_W_MIN
  assert.equal(r.h, 150);
  assert.equal(r.x, 0);
  assert.equal(r.y, 0);
});

test('clampFloatRect enforces the minimum size on an under-sized stored rect', () => {
  const r = L.clampFloatRect({ x: 10, y: 10, w: 50, h: 50 }, 1600, 900);
  assert.equal(r.w, L.FLOAT_W_MIN);
  assert.equal(r.h, L.FLOAT_H_MIN);
});

test('clampFloatRect tolerates a missing/garbage rect entirely', () => {
  const r = L.clampFloatRect({}, 1600, 900);
  assert.equal(r.x, 0);
  assert.equal(r.y, 0);
  assert.equal(r.w, L.FLOAT_W_MIN);
  assert.equal(r.h, L.FLOAT_H_MIN);
});

test('normalizeOrder keeps the saved order for surviving ids, drops unknown ones, appends missing ones', () => {
  assert.deepEqual(L.normalizeOrder(['dom', 'order'], ['order', 'dom']), ['dom', 'order']);
  assert.deepEqual(L.normalizeOrder(['dom', 'ghost'], ['order', 'dom']), ['dom', 'order']);
  assert.deepEqual(L.normalizeOrder(['dom'], ['order', 'dom']), ['dom', 'order']);
  assert.deepEqual(L.normalizeOrder(null, ['order', 'dom']), ['order', 'dom']);
  assert.deepEqual(L.normalizeOrder(['order', 'order', 'dom'], ['order', 'dom']), ['order', 'dom']);
});

test('reorderList moves an id to a new index, clamping an out-of-range target', () => {
  assert.deepEqual(L.reorderList(['a', 'b', 'c'], 'c', 0), ['c', 'a', 'b']);
  assert.deepEqual(L.reorderList(['a', 'b', 'c'], 'a', 99), ['b', 'c', 'a']);
  assert.deepEqual(L.reorderList(['a', 'b'], 'a', 1), ['b', 'a']);
});

test('dockHeights splits evenly with nothing stored, and reuses stored fractions', () => {
  assert.deepEqual(L.dockHeights(['order'], {}), { order: 1 });
  const even = L.dockHeights(['order', 'dom'], {});
  assert.ok(Math.abs(even.order - 0.5) < 1e-9 && Math.abs(even.dom - 0.5) < 1e-9);
  const stored = L.dockHeights(['order', 'dom'], { order: 0.7, dom: 0.3 });
  assert.ok(Math.abs(stored.order - 0.7) < 1e-9 && Math.abs(stored.dom - 0.3) < 1e-9);
  assert.deepEqual(L.dockHeights([], {}), {});
});

test('dockHeights enforces the floor instead of letting a panel collapse to near-zero', () => {
  const out = L.dockHeights(['order', 'dom'], { order: 0.99, dom: 0.01 });
  assert.ok(out.dom >= L.DOCK_MIN_FRACTION - 1e-9);
  assert.ok(Math.abs(out.order + out.dom - 1) < 1e-9);
});

test('applySplitterDrag transfers height between the two adjacent panels and holds the floor', () => {
  const heights = { order: 0.5, dom: 0.5 };
  const grown = L.applySplitterDrag(['order', 'dom'], heights, 0, 0.2);
  assert.ok(Math.abs(grown.order - 0.7) < 1e-9);
  assert.ok(Math.abs(grown.dom - 0.3) < 1e-9);
  const floored = L.applySplitterDrag(['order', 'dom'], heights, 0, -10);
  assert.ok(floored.order >= L.DOCK_MIN_FRACTION - 1e-9);
  assert.ok(Math.abs(floored.order + floored.dom - 1) < 1e-9);
  assert.deepEqual(L.applySplitterDrag(['order'], heights, 0, 0.2), { ...heights });   // no j: unchanged
});

test('pixelsToFraction converts a drag delta to a height fraction, and is safe at zero height', () => {
  assert.equal(L.pixelsToFraction(100, 1000), 0.1);
  assert.equal(L.pixelsToFraction(100, 0), 0);
});

test('dockSlots stacks panels top-down from their fractions', () => {
  const slots = L.dockSlots(['order', 'dom'], { order: 0.25, dom: 0.75 }, 800);
  assert.deepEqual(slots, [{ id: 'order', top: 0, height: 200 }, { id: 'dom', top: 200, height: 600 }]);
});

test('pointInRect is a plain inclusive hit test', () => {
  const rect = { x: 10, y: 10, w: 100, h: 50 };
  assert.equal(L.pointInRect(10, 10, rect), true);
  assert.equal(L.pointInRect(110, 60, rect), true);
  assert.equal(L.pointInRect(9, 10, rect), false);
  assert.equal(L.pointInRect(111, 10, rect), false);
  assert.equal(L.pointInRect(0, 0, null), false);
});

test('sanitizeState degrades field-by-field instead of discarding the whole blob', () => {
  const d = L.defaultState();
  const out = L.sanitizeState({ dockWidth: 'nope', panels: { order: { open: true, x: 'bad' } } }, d);
  assert.equal(out.dockWidth, L.DOCK_W_DEFAULT);
  assert.equal(out.panels.order.open, true);
  assert.equal(out.panels.order.x, d.panels.order.x);      // fell back
  assert.equal(out.panels.order.docked, d.panels.order.docked);
  assert.deepEqual(out.panels.dom, d.panels.dom);          // untouched panel: pure default
  assert.deepEqual(out.dockOrder, d.dockOrder);
});

test('sanitizeState drops an unknown persisted panel id and never throws on garbage', () => {
  const d = L.defaultState();
  assert.deepEqual(Object.keys(L.sanitizeState({ panels: { ghost: { open: true } } }, d).panels), ['order', 'dom']);
  assert.deepEqual(L.sanitizeState(null, d), d);
  assert.deepEqual(L.sanitizeState('garbage', d), d);
  assert.deepEqual(L.sanitizeState(42, d), d);
});

test('sanitizeState only keeps positive finite stored dock heights', () => {
  const d = L.defaultState();
  const out = L.sanitizeState({ dockHeights: { order: 0.4, dom: -1, ghost: 0.6 } }, d);
  assert.deepEqual(out.dockHeights, { order: 0.4 });
});

test('parsePersisted never throws on invalid JSON and falls back to sanitized defaults', () => {
  const d = L.defaultState();
  assert.deepEqual(L.parsePersisted('{not json', d), d);
  assert.deepEqual(L.parsePersisted(null, d), d);
  const out = L.parsePersisted(JSON.stringify({ dockWidth: 400 }), d);
  assert.equal(out.dockWidth, 400);
});

test('defaultState shape has both known panels, closed, docked', () => {
  const d = L.defaultState();
  assert.deepEqual(Object.keys(d.panels).sort(), ['dom', 'order']);
  for (const id of L.IDS) {
    assert.equal(d.panels[id].open, false);
    assert.equal(d.panels[id].docked, true);
  }
});

/* ---- side-by-side docking (2026-09-27 panels-side plan) ---- */

test('defaultState starts stacked with no stored side widths', () => {
  const d = L.defaultState();
  assert.equal(d.dockOrientation, 'stack');
  assert.deepEqual(d.dockWidths, {});
});

test('normalizeOrientation only ever returns a known orientation', () => {
  assert.equal(L.normalizeOrientation('side'), 'side');
  assert.equal(L.normalizeOrientation('stack'), 'stack');
  assert.equal(L.normalizeOrientation('sideways'), 'stack');
  assert.equal(L.normalizeOrientation(undefined), 'stack');
  assert.equal(L.normalizeOrientation(null), 'stack');
});

test('dockDropZone hit-tests the outer edge bands as left/right and the rest as top/bottom', () => {
  const rect = { x: 100, y: 200, w: 200, h: 100 };   // edgeFraction default 0.3 -> bands at relX < .3 / > .7
  assert.equal(L.dockDropZone(120, 220, rect), 'left');     // relX .1
  assert.equal(L.dockDropZone(280, 220, rect), 'right');    // relX .9
  assert.equal(L.dockDropZone(200, 210, rect), 'top');      // relX .5, top half
  assert.equal(L.dockDropZone(200, 280, rect), 'bottom');   // relX .5, bottom half
});

test('dockDropZone boundary values fall to the non-edge side, and the midpoint falls to bottom', () => {
  const rect = { x: 0, y: 0, w: 100, h: 100 };
  assert.equal(L.dockDropZone(30, 10, rect), 'top');       // relX exactly .3 -> not "< .3", so not left
  assert.equal(L.dockDropZone(70, 10, rect), 'top');       // relX exactly .7 -> not "> .7", so not right
  assert.equal(L.dockDropZone(50, 50, rect), 'bottom');    // exactly the vertical midpoint: dy < h/2 is false at dy=50
});

test('dockDropZone returns null outside the rect, and for a degenerate rect', () => {
  const rect = { x: 0, y: 0, w: 100, h: 100 };
  assert.equal(L.dockDropZone(-1, 50, rect), null);
  assert.equal(L.dockDropZone(50, 101, rect), null);
  assert.equal(L.dockDropZone(50, 50, null), null);
  assert.equal(L.dockDropZone(50, 50, { x: 0, y: 0, w: 0, h: 100 }), null);
});

test('dockDropZone honors a custom edgeFraction', () => {
  const rect = { x: 0, y: 0, w: 100, h: 100 };   // relX = .15 throughout: inside a .1 band, outside a .3 one
  assert.equal(L.dockDropZone(15, 50, rect, 0.1), 'bottom');   // narrower band: no longer counts as an edge
  assert.equal(L.dockDropZone(15, 50, rect, 0.3), 'left');     // wider band: same point now IS the edge
});

test('clampSideWidths clamps each panel to its own min/max', () => {
  const out = L.clampSideWidths({ order: 50, dom: 9999 }, ['order', 'dom'], 10000);
  assert.equal(out.order, L.DOCK_W_MIN);
  assert.equal(out.dom, L.DOCK_W_MAX);
});

test('clampSideWidths defaults an unstored panel to DOCK_W_DEFAULT before clamping', () => {
  const out = L.clampSideWidths({}, ['order', 'dom'], 10000);
  assert.equal(out.order, L.DOCK_W_DEFAULT);
  assert.equal(out.dom, L.DOCK_W_DEFAULT);
});

test('clampSideWidths scales both down together when the pair would exceed the viewport budget', () => {
  const out = L.clampSideWidths({ order: 400, dom: 400 }, ['order', 'dom'], 700);
  assert.ok(Math.abs(out.order + out.dom - 700) < 1e-6);
  assert.ok(Math.abs(out.order - out.dom) < 1e-6);   // scaled proportionally, so an even split stays even
  assert.ok(out.order >= L.DOCK_W_MIN && out.dom >= L.DOCK_W_MIN);
});

test('clampSideWidths never shrinks a panel below DOCK_W_MIN even when the budget is impossibly small', () => {
  const out = L.clampSideWidths({ order: 300, dom: 300 }, ['order', 'dom'], 100);
  assert.equal(out.order, L.DOCK_W_MIN);
  assert.equal(out.dom, L.DOCK_W_MIN);
});

test('sideTotalWidth sums the two panels\' widths', () => {
  assert.equal(L.sideTotalWidth({ order: 300, dom: 260 }, ['order', 'dom']), 560);
  assert.equal(L.sideTotalWidth({}, []), 0);
});

test('applySideSplitDrag transfers px between the two panels and holds the DOCK_W_MIN floor', () => {
  const widths = { order: 320, dom: 320 };
  const grown = L.applySideSplitDrag(widths, ['order', 'dom'], 0, 40);
  assert.equal(grown.order, 360);
  assert.equal(grown.dom, 280);
  assert.equal(grown.order + grown.dom, 640);   // total unchanged, only the split moves
  const floored = L.applySideSplitDrag(widths, ['order', 'dom'], 0, -1000);
  assert.equal(floored.order, L.DOCK_W_MIN);
  assert.equal(floored.dom, 640 - L.DOCK_W_MIN);
  assert.deepEqual(L.applySideSplitDrag(widths, ['order'], 0, 40), { ...widths });   // no j: unchanged
});

test('applyGripDragSide grows/shrinks the leftmost (order[0]) panel only, clamped to its own min/max', () => {
  const grown = L.applyGripDragSide({ order: 320, dom: 320 }, ['order', 'dom'], 30);
  assert.equal(grown.order, 350);
  assert.equal(grown.dom, 320);   // untouched
  const flooredOut = L.applyGripDragSide({ order: 270, dom: 320 }, ['order', 'dom'], -1000);
  assert.equal(flooredOut.order, L.DOCK_W_MIN);
  assert.deepEqual(L.applyGripDragSide({}, [], 10), {});
});

test('sanitizeState degrades dockOrientation to stack on garbage, and only keeps positive finite dockWidths', () => {
  const d = L.defaultState();
  const out = L.sanitizeState({ dockOrientation: 'sideways', dockWidths: { order: 300, dom: -5, ghost: 200 } }, d);
  assert.equal(out.dockOrientation, 'stack');
  assert.deepEqual(out.dockWidths, { order: 300 });
});

test('sanitizeState keeps a valid persisted side orientation and its widths', () => {
  const d = L.defaultState();
  const out = L.sanitizeState({ dockOrientation: 'side', dockWidths: { order: 300, dom: 280 } }, d);
  assert.equal(out.dockOrientation, 'side');
  assert.deepEqual(out.dockWidths, { order: 300, dom: 280 });
});

test('parsePersisted with no stored dockOrientation (old saved state) falls back to stacked', () => {
  const d = L.defaultState();
  const out = L.parsePersisted(JSON.stringify({ dockWidth: 340, dockOrder: ['dom', 'order'] }), d);
  assert.equal(out.dockOrientation, 'stack');
  assert.deepEqual(out.dockOrder, ['dom', 'order']);
});

test('clampSideWidths: an uneven split lands exactly on the budget without dipping under the floor', () => {
  for (const [a, b, budget] of [[480, 260, 600], [480, 260, 521], [400, 300, 650]]) {
    const w = L.clampSideWidths({ order: a, dom: b }, ['order', 'dom'], budget);
    assert.ok(Math.abs(w.order + w.dom - budget) < 1e-6, `sum ${w.order + w.dom} vs ${budget}`);
    assert.ok(w.order >= L.DOCK_W_MIN - 1e-9 && w.dom >= L.DOCK_W_MIN - 1e-9);
  }
});
