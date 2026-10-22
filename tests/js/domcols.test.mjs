import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Which columns the Level 2 ladder shows, through the REAL domui.js + dom.js under a small DOM shim: with nothing
   saved the default follows the panel's width (all eight columns clipped to '1…' at the 320px dock, review
   2026-10-22); a list the user chose in the Columns menu is shown as chosen, at any width. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;

class El {
  constructor() { this.children = []; this.cls = new Set(); this.dataset = {}; this.hidden = false; this._text = ''; }
  set className(v) { this.cls = new Set(String(v || '').split(/\s+/).filter(Boolean)); }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { this.children.push(...nodes.filter((n) => n != null)); }
  appendChild(n) { this.children.push(n); return n; }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  get classList() { return { add: (c) => this.cls.add(c), toggle: (c, on) => { if (on) this.cls.add(c); else this.cls.delete(c); } }; }
  get style() { return (this._style = this._style || {}); }
  setAttribute(k) { if (k === 'style') this.styleWrites = (this.styleWrites || 0) + 1; }
  addEventListener() {}
  focus() {}
}
const all = (root, cls, out = []) => {
  for (const c of root.children) { if (!(c instanceof El)) continue; if (c.cls.has(cls)) out.push(c); all(c, cls, out); }
  return out;
};
const page = { mk: (tag, cls, text) => { const e = new El(); e.className = cls; if (text != null) e.textContent = text; return e; },
  icon: () => new El(),
  // the Columns menu: toggleMenu builds it at once, menuItem keeps its label and click for the test to press
  toggleMenu: (btn, build) => build(),
  openMenu: () => new El(),
  menuItem: (label, _hint, onclick) => { const e = new El(); e.label = label; e.click = onclick; return e; },
  closeMenu() {} };

require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/dom.js');
globalThis.HBTrade = { linesFor: () => [], lineLabel: () => '' };
globalThis.HBDeskClient = { quotes: { NQ: { last: 100 } }, state: {} };
globalThis.HBCharts = { cells: [{ shown: { root: 'NQ' }, tick: 0.25, has: { fp: false, big: false }, bars: [{ t: 34200 }], needFootprint() {} }], selected: 0 };
const DOMUI = require.resolve('../../homebase/static/charts/domui.js');

/* A fresh ladder (domui.js keeps its state at module level): `saved` is what localStorage holds, if anything.
   fit(width) is the panel being laid out at that width -- the ResizeObserver callback, run by hand. */
function ladder(saved) {
  globalThis.localStorage = { getItem: () => saved ?? null, setItem(k, v) { this.written = v; } };
  let observed = null;
  globalThis.ResizeObserver = class { constructor(fn) { this.fn = fn; } observe(el) { observed = { fn: this.fn, el }; } };
  const realSetInterval = globalThis.setInterval;
  let tick = null;
  globalThis.setInterval = (fn) => { tick = fn; return 0; };
  delete require.cache[DOMUI];
  require(DOMUI);
  const el = new El();
  globalThis.HBDomUI.mount(el, page);
  globalThis.setInterval = realSetInterval;
  globalThis.HBDomUI.setVisible(true);
  globalThis.HBDomUI.onDepth({ type: 'depth', root: 'NQ', ts: 1, bids: [[99.75, 5]], offers: [[100.25, 7]] });
  tick();                                                  // paints the ladder: its row cells exist
  return {
    shown: () => Object.keys(Object.fromEntries(['psb', 'sold', 'bid', 'price', 'ask', 'bought', 'psa', 'vol']
      .map((id) => [id, all(el, `dom-${id}`)[0].hidden]).filter(([, hidden]) => !hidden))),
    fit(width) { el.children[0].clientWidth = width; if (observed) observed.fn(); },
    gridWrites: () => el.children[0].styleWrites || 0,     // how often the grid template was rewritten
    pick(label) {                                          // the Columns button, then one item of its menu
      const menu = new El();
      page.openMenu = () => menu;
      all(el, 'dom-recentre')[0].onclick();
      menu.children.find((m) => m.label === label).click();
    },
    written: () => globalThis.localStorage.written,
  };
}

test('nothing saved, the 320px dock: the old four columns, so no value or header is clipped', () => {
  const l = ladder(null);
  l.fit(314);
  assert.deepEqual(l.shown(), ['bid', 'price', 'ask', 'vol']);
});

test('nothing saved: a wider panel brings the rest back, a narrower one takes them away again', () => {
  const l = ladder(null);
  l.fit(474);
  assert.deepEqual(l.shown(), ['psb', 'sold', 'bid', 'price', 'ask', 'bought', 'psa', 'vol']);
  l.fit(400);
  assert.deepEqual(l.shown(), ['sold', 'bid', 'price', 'ask', 'bought', 'vol']);
  l.fit(300);
  assert.deepEqual(l.shown(), ['bid', 'price', 'ask', 'vol']);
});

test('a panel with no width yet (hidden: 0) keeps the columns it has', () => {
  const l = ladder(null);
  l.fit(474);
  l.fit(0);
  assert.equal(l.shown().length, 8);
});

test('a saved choice is shown as chosen at any width', () => {
  const l = ladder('["sold","bought","psb","psa"]');
  l.fit(314);
  assert.deepEqual(l.shown(), ['psb', 'sold', 'bid', 'price', 'ask', 'bought', 'psa']);
  const v = ladder('["vol"]');
  v.fit(2000);
  assert.deepEqual(v.shown(), ['bid', 'price', 'ask', 'vol']);
});

test('a choice made in the Columns menu is saved and survives the panel being resized', () => {
  const l = ladder(null);
  l.fit(474);
  l.pick('Vol');                                           // every column but Vol
  assert.equal(l.written(), '["psb","sold","bid","price","ask","bought","psa"]');
  assert.deepEqual(l.shown(), ['psb', 'sold', 'bid', 'price', 'ask', 'bought', 'psa']);
  l.fit(314);                                              // the width default would be the old four columns
  assert.deepEqual(l.shown(), ['psb', 'sold', 'bid', 'price', 'ask', 'bought', 'psa']);
  l.fit(2000);
  assert.deepEqual(l.shown(), ['psb', 'sold', 'bid', 'price', 'ask', 'bought', 'psa']);
});

test('a resize inside the same bracket rewrites nothing: the observer fires on every frame of a drag', () => {
  const l = ladder(null);
  l.fit(300);
  const n = l.gridWrites();
  for (let w = 301; w <= 369; w += 4) l.fit(w);            // still the old four columns
  assert.equal(l.gridWrites(), n);
  l.fit(400);                                              // a new bracket: one rewrite
  assert.equal(l.gridWrites(), n + 1);
  l.fit(410);
  assert.equal(l.gridWrites(), n + 1);
});
