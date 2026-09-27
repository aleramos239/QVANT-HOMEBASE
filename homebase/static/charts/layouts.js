/* Homebase Charts — pure helpers for the layout tab strip (2026-09-27 accounts-paper-layouts-appsettings
   plan, Task 3): ordering saved-layout names against a stored tab order, the unsaved dot, rename
   collisions, picking the next active tab when one closes, default names for + and Duplicate, and
   drag reorder. No DOM and no browser globals -- the Node tests load this file directly, exactly like
   catalog.js. app.js owns everything stateful (the fetches, the DOM, localStorage); this file only
   decides, given plain data, what the strip should show. */
(function () {
'use strict';

/* The tab strip's display order: `order` (the server's stored tab order — may be stale, e.g. a
   renamed or deleted layout, or missing entirely on a first run) reduced to the layouts in `names`
   that still exist, in that order; anything in `names` that `order` doesn't mention (a layout saved
   from another viewer, or before any order was ever stored) is appended, sorted A->Z so new tabs land
   somewhere stable instead of wherever the server happened to list them. */
function orderNames(names, order) {
  const known = new Set(names);
  const kept = (Array.isArray(order) ? order : []).filter((n) => known.has(n));
  const seen = new Set(kept);
  const rest = names.filter((n) => !seen.has(n)).sort((a, b) => a.localeCompare(b));
  return [...kept, ...rest];
}

/* Has the active tab drifted from what the server holds for it? `saved` is the body last written (or
   loaded) for this tab, `current` is the body built fresh from the charts on screen right now (same
   shape both times: app.js's layoutBody()) -- a missing snapshot (never saved, or not loaded yet)
   always reads dirty, so a save is never skipped by mistake. */
function isDirty(saved, current) {
  if (!saved) return true;
  return JSON.stringify(saved) !== JSON.stringify(current);
}

/* Renaming `oldName` to the trimmed `newName`: '' when it is fine, else why not. "." and ".." are
   refused because the browser resolves /api/layouts/. and /.. as path steps before the PUT/DELETE
   ever reaches the server (see server.py's {name:path} routes) -- the same rule the old "Save layout
   as..." box enforced. Renaming a tab to its own current name is a no-op, not a collision. */
function renameError(newName, oldName, names) {
  const n = String(newName == null ? '' : newName).trim();
  if (!n) return 'Name cannot be empty';
  if (n === '.' || n === '..') return '“.” and “..” cannot be layout names';
  if (n !== oldName && names.includes(n)) return `A layout named “${n}” already exists`;
  return '';
}

/* + and Duplicate: the first name of the form "base", "base 2", "base 3", ... not already taken. */
function uniqueName(base, names) {
  const have = new Set(names);
  if (!have.has(base)) return base;
  for (let i = 2; ; i++) {
    const n = `${base} ${i}`;
    if (!have.has(n)) return n;
  }
}

/* Closing the tab at `index`: the order without it, and the index that should become active -- the
   tab now sitting where the closed one was (the one that was to its right), or the new last tab if
   the closed one was rightmost, or -1 once none are left. Meaningless (and unused by the caller)
   unless `index` was the active tab. */
function closeTab(order, index) {
  const next = order.filter((_, i) => i !== index);
  const active = next.length ? Math.min(index, next.length - 1) : -1;
  return { order: next, active };
}

/* Drag reorder: `name` moved to sit at `toIndex` in `order` (both already known-names-only). A name
   not in `order` is left untouched -- the drop target vanished mid-drag (renamed/closed elsewhere). */
function moveTab(order, name, toIndex) {
  if (!order.includes(name)) return order;
  const rest = order.filter((n) => n !== name);
  const at = Math.max(0, Math.min(toIndex, rest.length));
  rest.splice(at, 0, name);
  return rest;
}

/* The + menu's "reopen" list: every saved layout in `names` that isn't currently an open tab (`open`),
   A->Z. Closing a tab (see app.js's closeTab) never deletes the layout, so it always stays findable
   here until someone explicitly deletes it. */
function closedNames(names, open) {
  const isOpen = new Set(open);
  return names.filter((n) => !isOpen.has(n)).sort((a, b) => a.localeCompare(b));
}

/* Which saved layout to open when the page starts, or null to keep what is on screen. A start with no
   remembered tab (a fresh window, cleared storage) or whose remembered tab no longer exists opens the FIRST
   tab rather than a blank chart -- but never over unsaved work (`dirty`), which is the user's. */
function startTab(name, dirty, order, saved) {
  if (dirty || !Array.isArray(order) || !order.length || !saved) return null;
  if (name && Object.prototype.hasOwnProperty.call(saved, name)) return null;
  return order.find((n) => Object.prototype.hasOwnProperty.call(saved, n)) || null;
}

const api = { startTab, orderNames, isDirty, renameError, uniqueName, closeTab, moveTab, closedNames };
if (typeof window !== 'undefined') window.HBLayouts = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
