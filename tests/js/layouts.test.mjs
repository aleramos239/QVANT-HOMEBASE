import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/layouts.js');

// ---- orderNames: tab list ordering ----
test('orderNames keeps the stored order for names that still exist', () => {
  assert.deepEqual(L.orderNames(['a', 'b', 'c'], ['c', 'a', 'b']), ['c', 'a', 'b']);
});

test('orderNames drops stored-order entries for layouts that no longer exist', () => {
  assert.deepEqual(L.orderNames(['a', 'b'], ['x', 'a', 'y']), ['a', 'b']);
});

test('orderNames appends names missing from the stored order, sorted A-Z', () => {
  assert.deepEqual(L.orderNames(['b', 'a', 'c'], ['c']), ['c', 'a', 'b']);
});

test('orderNames with no stored order (first run) sorts everything A-Z', () => {
  assert.deepEqual(L.orderNames(['b', 'a'], null), ['a', 'b']);
  assert.deepEqual(L.orderNames(['b', 'a'], undefined), ['a', 'b']);
  assert.deepEqual(L.orderNames(['b', 'a'], []), ['a', 'b']);
});

test('orderNames with no layouts at all is empty regardless of stored order', () => {
  assert.deepEqual(L.orderNames([], ['a', 'b']), []);
});

// ---- isDirty: the dirty flag ----
test('isDirty is false for two bodies that serialize the same', () => {
  const saved = { grid: 4, cells: [{ root: 'NQ', spec: 'time:60', indicators: [] }] };
  const current = { grid: 4, cells: [{ root: 'NQ', spec: 'time:60', indicators: [] }] };
  assert.equal(L.isDirty(saved, current), false);
});

test('isDirty is true once a field differs anywhere in the body', () => {
  const saved = { grid: 4, cells: [{ root: 'NQ', spec: 'time:60', indicators: [] }] };
  const changedRoot = { grid: 4, cells: [{ root: 'ES', spec: 'time:60', indicators: [] }] };
  const changedGrid = { grid: 2, cells: [{ root: 'NQ', spec: 'time:60', indicators: [] }] };
  assert.equal(L.isDirty(saved, changedRoot), true);
  assert.equal(L.isDirty(saved, changedGrid), true);
});

test('isDirty treats a missing saved snapshot as dirty', () => {
  assert.equal(L.isDirty(null, { grid: 1, cells: [] }), true);
});

// ---- renameError: rename collisions ----
test('renameError refuses an empty or whitespace-only name', () => {
  assert.equal(L.renameError('', 'Main', ['Main', 'Other']), 'Name cannot be empty');
  assert.equal(L.renameError('   ', 'Main', ['Main', 'Other']), 'Name cannot be empty');
});

test('renameError refuses "." and ".." (they break the /api/layouts path route)', () => {
  assert.equal(L.renameError('.', 'Main', ['Main']), '“.” and “..” cannot be layout names');
  assert.equal(L.renameError('..', 'Main', ['Main']), '“.” and “..” cannot be layout names');
});

test('renameError refuses a name already used by ANOTHER tab', () => {
  assert.equal(L.renameError('Other', 'Main', ['Main', 'Other']), 'A layout named “Other” already exists');
});

test('renameError allows renaming a tab back to its own current name (a no-op, not a collision)', () => {
  assert.equal(L.renameError('Main', 'Main', ['Main', 'Other']), '');
});

test('renameError allows a fresh, unused name', () => {
  assert.equal(L.renameError('Fresh name', 'Main', ['Main', 'Other']), '');
});

test('renameError trims surrounding whitespace before checking', () => {
  assert.equal(L.renameError('  Other  ', 'Main', ['Main', 'Other']), 'A layout named “Other” already exists');
});

// ---- closeTab: closing the active tab ----
test('closeTab on a middle tab selects the tab that slid into its place', () => {
  assert.deepEqual(L.closeTab(['a', 'b', 'c'], 1), { order: ['a', 'c'], active: 1 });
});

test('closeTab on the last (rightmost) tab selects the new last tab', () => {
  assert.deepEqual(L.closeTab(['a', 'b', 'c'], 2), { order: ['a', 'b'], active: 1 });
});

test('closeTab on the first of two tabs selects the remaining one', () => {
  assert.deepEqual(L.closeTab(['a', 'b'], 0), { order: ['b'], active: 0 });
});

test('closeTab on the only tab leaves none active', () => {
  assert.deepEqual(L.closeTab(['a'], 0), { order: [], active: -1 });
});

// ---- uniqueName: default names for + and Duplicate ----
test('uniqueName returns the base name when it is free', () => {
  assert.equal(L.uniqueName('Layout', ['Other']), 'Layout');
});

test('uniqueName counts up past collisions', () => {
  assert.equal(L.uniqueName('Layout', ['Layout']), 'Layout 2');
  assert.equal(L.uniqueName('Layout', ['Layout', 'Layout 2']), 'Layout 3');
  assert.equal(L.uniqueName('Layout', ['Layout', 'Layout 2', 'Layout 3']), 'Layout 4');
});

// ---- moveTab: drag reorder ----
test('moveTab relocates a name to the given index', () => {
  assert.deepEqual(L.moveTab(['a', 'b', 'c'], 'a', 2), ['b', 'c', 'a']);
  assert.deepEqual(L.moveTab(['a', 'b', 'c'], 'c', 0), ['c', 'a', 'b']);
});

test('moveTab is a no-op for a name that is not in the order', () => {
  assert.deepEqual(L.moveTab(['a', 'b'], 'z', 0), ['a', 'b']);
});

test('moveTab clamps an out-of-range target index', () => {
  assert.deepEqual(L.moveTab(['a', 'b', 'c'], 'a', 99), ['b', 'c', 'a']);
  assert.deepEqual(L.moveTab(['a', 'b', 'c'], 'c', -5), ['c', 'a', 'b']);
});

// ---- closedNames: the + menu's "reopen a closed tab" list ----
test('closedNames lists saved layouts that are not open, A-Z', () => {
  assert.deepEqual(L.closedNames(['c', 'a', 'b'], ['b']), ['a', 'c']);
});

test('closedNames is empty once every saved layout is open', () => {
  assert.deepEqual(L.closedNames(['a', 'b'], ['a', 'b']), []);
  assert.deepEqual(L.closedNames(['a', 'b'], ['a', 'b', 'c']), []);   // an "open" name unknown to `names` is fine
});

test('closedNames with nothing saved is empty regardless of what is open', () => {
  assert.deepEqual(L.closedNames([], ['a']), []);
});

// ---- startTab: what the page opens on start ----
test('startTab: no remembered tab opens the first saved layout', () => {
  const saved = { A: {}, B: {} };
  assert.equal(L.startTab('', false, ['B', 'A'], saved), 'B');
  assert.equal(L.startTab('gone', false, ['A', 'B'], saved), 'A');   // remembered tab was deleted
});
test('startTab: keeps the screen when the remembered tab exists, there is unsaved work, or nothing is saved', () => {
  const saved = { A: {}, B: {} };
  assert.equal(L.startTab('B', false, ['A', 'B'], saved), null);
  assert.equal(L.startTab('', true, ['A', 'B'], saved), null);        // unsaved, unnamed work is the user's
  assert.equal(L.startTab('gone', true, ['A'], saved), null);
  assert.equal(L.startTab('', false, [], {}), null);
  assert.equal(L.startTab('', false, ['X'], saved), null);            // order names nothing saved
});
