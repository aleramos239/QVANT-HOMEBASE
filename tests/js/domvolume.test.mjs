import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The Level 2 ladder's Vol column through the REAL domui.js + dom.js under a small DOM shim: it sums the
   selected chart's footprint, and a chart only carries that when something asks for it (cell.js need()).
   So the ladder asks the chart (needFootprint) and shows the column only once the chart's history carries
   it -- never a sum of the few bars a live update happened to bring. */
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
  get classList() { return { toggle: (c, on) => { if (on) this.cls.add(c); else this.cls.delete(c); } }; }
  setAttribute() {}
  addEventListener() {}
  focus() {}
}
const all = (root, cls, out = []) => {
  for (const c of root.children) { if (!(c instanceof El)) continue; if (c.cls.has(cls)) out.push(c); all(c, cls, out); }
  return out;
};
const page = { mk: (tag, cls, text) => { const e = new El(); e.className = cls; if (text != null) e.textContent = text; return e; },
  icon: () => new El() };

require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/dom.js');
globalThis.HBTrade = { linesFor: () => [], lineLabel: () => '' };
globalThis.HBDeskClient = { quotes: { NQ: { last: 100 } }, state: {} };
require('../../homebase/static/charts/domui.js');

const bar = (fp) => ({ t: 34200, ...(fp ? { fp } : {}) });
const cell = { shown: { root: 'NQ' }, tick: 0.25, has: { fp: false, big: false }, asked: 0,
  bars: [bar(), bar(), bar([[100, 3, 4]])],        // the history came without; a live update brought the last bar's
  needFootprint() { this.asked++; } };
globalThis.HBCharts = { cells: [cell], selected: 0 };

const el = new El(), realSetInterval = globalThis.setInterval;
let tick = null;                                   // the ladder's paint timer, run by hand
globalThis.setInterval = (fn) => { tick = fn; return 0; };
globalThis.HBDomUI.mount(el, page);
globalThis.setInterval = realSetInterval;
globalThis.HBDomUI.setVisible(true);
globalThis.HBDomUI.onDepth({ type: 'depth', root: 'NQ', ts: 1, bids: [[99.75, 5]], offers: [[100.25, 7]] });
const vols = () => all(el, 'dom-vol').map((e) => e.textContent).filter(Boolean);

test('the ladder asks the chart for its footprint and leaves Vol blank until the chart carries it', () => {
  tick();
  assert.equal(all(el, 'dom-row').length, 41);     // the ladder did paint
  assert.equal(cell.asked, 1);
  assert.deepEqual(vols(), []);                    // not "7" from the one bar that has a footprint
});

test('once the reloaded history carries the footprint the column shows the session volume', () => {
  cell.has = { fp: true, big: false };
  cell.bars = [bar([[100, 10, 20]]), bar([[100, 1, 1], [100.25, 0, 5]]), bar([[100, 3, 4]])];
  globalThis.HBDomUI.onDepth({ type: 'depth', root: 'NQ', ts: 2, bids: [[99.75, 5]], offers: [[100.25, 7]] });
  tick();
  assert.deepEqual(vols().sort(), ['39', '5']);
});
