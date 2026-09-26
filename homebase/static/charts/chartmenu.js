/* Homebase Charts — the chart's context menu (TradingView's right-click menu), pure: which items a chart's menu
   shows, in which order, with dividers; the extension point other builds add items through; the items of an
   indicator's own menu; arrow-key stepping. The page (app.js) renders the items and runs them. No browser
   globals at load time: the Node tests load this file directly.

   An item is {text, sub?, act, …} (a built-in: the page runs MENU_ACTS[act]) or {text, sub?, run(ctx)} (an
   extension's: the page calls run). ctx is the page's {cell, root, price, tick, nDrawings, nIndicators}; price
   is tick-rounded, or null when the pointer is off the price scale. This file reads only price, tick, nDrawings
   and nIndicators.

   The chart-trading build adds its Buy/Sell items without editing this file:
     HBChartMenu.register('trading', (ctx) => [{ text: 'Buy 1 NQ @ 30,878.00 limit', run(ctx) { … } }]);

   The chart menu's own "Chart template ›" row (spec §8) is not one of these built-ins: it needs a network
   fetch and its own submenu, so app.js renders and drives it directly, next to the Settings… item. */
(function () {
'use strict';
const Cat = (typeof window !== 'undefined' && window.HBCatalog) || (typeof require === 'function' ? require('./catalog.js') : null);

/* The menu's sections, top to bottom, with a divider between two that have items. 'trading' stays empty until
   the chart-trading build registers its items. */
const SECTIONS = ['view', 'copy', 'trading', 'remove', 'settings'];
const SEP = Object.freeze({ sep: true });

function roundTick(p, tick) { return tick > 0 ? +(Math.round(p / tick) * tick).toFixed(Cat.decimals(tick)) : p; }
/* What Copy price puts on the clipboard: the plain number, e.g. 30878.00 (it pastes into any number field). */
function copyText(price, tick) { return roundTick(price, tick).toFixed(Cat.decimals(tick)); }
/* The menu row: Copy price 30,878.00. */
function copyLabel(price, tick) { return `Copy price ${Cat.fmtPrice(roundTick(price, tick), tick)}`; }
function count(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }
/* The armed Remove-drawings row: the rail's Remove-all text. */
function armText(n, root) { return `Click again to remove ${count(n, 'drawing')} on ${root}`; }

/* A registry of item providers per section. register() returns its own unregister. */
function createRegistry() {
  const fns = Object.fromEntries(SECTIONS.map((s) => [s, []]));
  function register(section, itemsFn) {
    if (!SECTIONS.includes(section)) throw new Error(`unknown chart menu section: ${section}`);
    if (typeof itemsFn !== 'function') throw new TypeError('HBChartMenu.register: itemsFn must be a function');
    const entry = { fn: itemsFn };   // its own object: one function registered twice is two entries
    fns[section].push(entry);
    return () => { const i = fns[section].indexOf(entry); if (i >= 0) fns[section].splice(i, 1); };
  }
  function items(ctx) {
    const out = [];
    for (const s of SECTIONS) {
      const got = [];
      for (const { fn } of fns[s]) {
        let list;
        try { list = fn(ctx); } catch (_) { continue; }   // a broken extension never takes the menu down
        for (const it of Array.isArray(list) ? list : []) {
          const ok = it && typeof it === 'object' && typeof it.text === 'string' && it.text
            && (typeof it.run === 'function' || typeof it.act === 'string');
          if (ok) got.push({ ...it, section: s });
        }
      }
      if (got.length) { if (out.length) out.push(SEP); out.push(...got); }
    }
    return out;
  }
  return { register, items };
}

/* The built-in items (spec §7), registered like any extension. */
function builtins(reg) {
  reg.register('view', () => [{ act: 'reset', text: 'Reset chart view', sub: '⌥R' }]);
  reg.register('copy', (ctx) => (ctx.price == null || !Number.isFinite(ctx.price) ? []
    : [{ act: 'copy', text: copyLabel(ctx.price, ctx.tick), copy: copyText(ctx.price, ctx.tick) }]));
  reg.register('remove', (ctx) => [
    ...(ctx.nDrawings > 0 ? [{ act: 'removeDrawings', text: `Remove ${count(ctx.nDrawings, 'drawing')}` }] : []),
    ...(ctx.nIndicators > 0 ? [{ act: 'removeIndicators', text: `Remove ${count(ctx.nIndicators, 'indicator')}` }] : [])]);
  reg.register('settings', () => [{ act: 'settings', text: 'Settings…' }]);
  return reg;
}

/* An indicator's own menu (its legend ⋯, or a right-click in its pane): move it to the other placement, then
   Remove. An indicator that cannot move gets Remove only. */
function paneItems(inst) {
  const where = Cat.placement(inst), out = [];
  if (where === 'own') out.push({ act: 'move', pane: 'main', text: 'Move to main chart' });
  if (where === 'main') out.push({ act: 'move', pane: 'own', text: 'Move to new pane below' });
  out.push({ act: 'remove', text: 'Remove' });
  return out;
}

/* The item the arrow keys go to from item i of n (-1: none focused yet); ↓/↑ wrap, Home/End jump. */
function step(i, n, key) {
  if (n <= 0) return -1;
  if (key === 'Home') return 0;
  if (key === 'End') return n - 1;
  if (key === 'ArrowDown') return i < 0 ? 0 : (i + 1) % n;
  if (key === 'ArrowUp') return i < 0 ? n - 1 : (i - 1 + n) % n;
  return i;
}

const main = builtins(createRegistry());   // the page's menu
const api = { SECTIONS, createRegistry, builtins, register: main.register, items: main.items, paneItems, copyText,
  copyLabel, armText, step };
if (typeof window !== 'undefined') window.HBChartMenu = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
