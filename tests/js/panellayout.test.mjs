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
