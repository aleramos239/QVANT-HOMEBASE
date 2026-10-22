import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

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

test('the Time header sits over the left-aligned timestamps; the number headers stay right-aligned', () => {
  const [cols] = all(el, 'tape-cols');
  const [time, ...rest] = cols.children;
  assert.equal(time._text, 'Time');
  assert.ok(time.cls.has('tape-time'), 'the header takes the timestamps\' own left-aligned class');
  assert.ok(rest.every((h) => !h.cls.has('tape-time')));
  assert.ok(all(el, 'tape-row')[0].children[0].cls.has('tape-time'));
});

/* Layout cannot be measured under node, so tape.css's numbers are pinned instead (review 2026-10-22; measured in
   headless Chrome with the real CSS: Time "09:30:08.083" 78.7px of text, Price "25000.25" 60, Size "1.23K" 35,
   the Prints / Lvls headers 40.4 / 26.8, every cell 8px of padding, the rows 10px each side). */
const CSS = readFileSync(new URL('../../homebase/static/charts/tape.css', import.meta.url), 'utf8');
const floorsOf = (rule) => [...rule.matchAll(/minmax\((\d+)px/g)].map((m) => Number(m[1]));
const gridOf = (sel) => { const m = CSS.match(new RegExp(sel + '\\s*\\{[^}]*grid-template-columns:\\s*([^;]+);')); assert.ok(m, sel); return m[1]; };

test('tape.css: every column floor holds its widest text, so a cell does not ellipsise', () => {
  const full = floorsOf(gridOf('\\.tape-cols, \\.tape-row'));
  assert.equal(full.length, 5);
  assert.ok(full[0] >= 87, `Time floor ${full[0]} must hold "09:30:08.083" with its padding (87px)`);
  assert.ok(full[1] >= 68, 'Price');
  assert.ok(full[2] >= 43, 'Size: "1.23K"');
  assert.ok(full[3] >= 49, 'Prints header');
  assert.ok(full[4] >= 35, 'Lvls header');
  assert.ok(floorsOf(gridOf('\\.tape-wrap\\.raw \\.tape-cols, \\.tape-wrap\\.raw \\.tape-row'))[0] >= 87, 'Time floor in Raw');
  const narrow = CSS.match(/@container \(max-width: (\d+)px\)\s*\{[^@]*?grid-template-columns:\s*([^;]+);[^@]*?display: none/);
  assert.ok(narrow, 'a narrow panel drops Prints and Lvls');
  assert.ok(floorsOf(narrow[2])[0] >= 87, 'Time floor in the narrow Orders layout');
  // below this width the five floors plus the rows' 2 x 10px padding do not fit: that is where the container query must start
  assert.ok(Number(narrow[1]) >= full.reduce((a, b) => a + b, 0) + 20, 'the narrow layout must start before the five columns run out of room');
  assert.match(CSS, /\.tape-wrap \{[^}]*container-type: inline-size/);
});

test('tape.css: the min-size input gives way before the Side select at the 260px minimum', () => {
  assert.match(CSS, /\.tape-head \.op-in\.tape-min \{[^}]*min-width: 0/);
});

test('tape.css: the narrow layout tightens the head, so the min-size input keeps 5 digits at the 260 minimum', () => {
  // measured: the head needs 14px more than the 254px panel has, and every px the buttons and gaps give back is the input's
  const narrow = CSS.match(/@container \(max-width: \d+px\)\s*\{([^@]*?)\n\}/)[1];
  assert.match(narrow, /\.tape-head \{ gap: 6px; \}/);
  assert.match(narrow, /\.tape-head \.seg button \{ padding: 0 8px; \}/);
  assert.match(CSS, /\.tape-head \{[^}]*gap: 8px/, 'the wide layout keeps its 8px gaps');
  assert.match(CSS, /\.tape-head \.seg button \{[^}]*padding: 0 10px/, 'and its 10px buttons');
});

/* The Size track holds 5 characters. fmtCompact's two decimals run to 7 from 10,000 on and would ellipsise into a
   number that reads wrong ("123.4..." for 123,460), so the tape trims them. Last in the file: it replaces the rows. */
test('the Size cell never runs past the 5 characters its track holds, and stays true to the size', () => {
  const sizeOf = (v) => {
    globalThis.HBTapeUI.onMessage({ type: 'tape', root: 'NQ', s: '2025-10-21', i0: 0, reset: true, rows: [[T0, 100, v, 1, 0]] });
    tick();
    return all(el, 'tape-row')[0].children[2]._text;
  };
  assert.deepEqual([1, 950, 1234, 9994].map(sizeOf), ['1', '950', '1.23K', '9.99K'], 'what fmtCompact already fits is left as it is');
  assert.deepEqual([9996, 10000, 12345, 99949, 99950, 123456, 999499, 999500].map(sizeOf),
    ['10.0K', '10.0K', '12.3K', '99.9K', '100K', '123K', '999K', '1000K']);
  assert.deepEqual([999995, 1234567].map(sizeOf), ['1.00M', '1.23M'], 'a million is no order: fmtCompact says it as it always did');
  for (let v = 1; v < 999995; v += v < 100 ? 1 : Math.ceil(v / 97)) {
    const s = sizeOf(v), back = Number(s.replace('K', '')) * (s.endsWith('K') ? 1000 : 1);
    assert.ok(s.length <= 5, `${v} -> "${s}" is wider than its track`);
    assert.ok(Math.abs(back - v) <= v * 0.006, `${v} -> "${s}" is not the size`);
  }
});
