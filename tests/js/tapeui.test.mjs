import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The Time & Sales panel's markup through the REAL tapeui.js under a small DOM shim: what a screen reader gets.
   The row container is a list, so every row in it is a list item; the Orders / Raw buttons are toggles, so each
   says which one is pressed (review 2026-10-22). */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;

class El {
  constructor() { this.children = []; this.cls = new Set(); this.attrs = {}; this.hidden = false; this._text = ''; }
  set className(v) { this.cls = new Set(String(v || '').split(/\s+/).filter(Boolean)); }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { this.children.push(...nodes.filter((n) => n != null)); }
  appendChild(n) { this.children.push(n); return n; }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  get classList() { return { toggle: (c, on) => { if (on) this.cls.add(c); else this.cls.delete(c); }, contains: (c) => this.cls.has(c) }; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
}
globalThis.Option = class extends El { constructor(label, value) { super(); this.textContent = label; this.value = value; } };
const all = (root, cls, out = []) => {
  for (const c of root.children) { if (!(c instanceof El)) continue; if (c.cls.has(cls)) out.push(c); all(c, cls, out); }
  return out;
};
const page = { mk: (tag, cls, text) => { const e = new El(); e.className = cls; if (text != null) e.textContent = text; return e; },
  send: () => true };

require('../../homebase/static/charts/catalog.js');
globalThis.HBTape = require('../../homebase/static/charts/tape.js');
require('../../homebase/static/charts/tapeui.js');

const cell = { shown: { root: 'NQ' }, tick: 0.25 };
globalThis.HBCharts = { cells: [cell], selected: 0 };

const el = new El(), realSetInterval = globalThis.setInterval;
let tick = null;                                   // the panel's paint timer, run by hand
globalThis.setInterval = (fn) => { tick = fn; return 0; };
globalThis.HBTapeUI.mount(el, page);
globalThis.setInterval = realSetInterval;
const [rows] = all(el, 'tape-rows');
rows.clientHeight = 54;                            // three rows fit
globalThis.HBTapeUI.setVisible(true);
tick();                                            // resolves the selected chart's root; a message for another is dropped
const T0 = 1761053400000;
globalThis.HBTapeUI.onMessage({ type: 'tape', root: 'NQ', s: '2025-10-21', i0: 0, reset: true,
  rows: [[T0, 100, 1, 1, 1], [T0 + 1000, 100.25, 2, -1, 2]] });
tick();

test('the tape rows are list items inside the list', () => {
  assert.equal(rows.getAttribute('role'), 'list');
  const items = all(el, 'tape-row');
  assert.equal(items.length, 3);
  assert.ok(items.every((r) => r.getAttribute('role') === 'listitem'));
});

test('the Orders / Raw buttons say which one is pressed, and follow a click', () => {
  const [orders, raw] = all(el, 'seg')[0].children;
  assert.equal(orders.getAttribute('aria-pressed'), 'true');
  assert.equal(raw.getAttribute('aria-pressed'), 'false');
  raw.onclick();
  assert.equal(orders.getAttribute('aria-pressed'), 'false');
  assert.equal(raw.getAttribute('aria-pressed'), 'true');
  assert.ok(raw.cls.has('on') && !orders.cls.has('on'));
});
