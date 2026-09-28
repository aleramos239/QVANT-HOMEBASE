import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* indicator-settings-dialog.js is the page's DOM-mounting half (like settings-dialog.js): it reads/writes
   `window`/`document` directly at load and call time. A small hand-written DOM shim -- just what the Inputs
   tab's "time" field actually touches (append/replaceChildren/className/textContent/setAttribute) -- lets it
   load and run for real under `node --test`, so the "don't re-clamp destructively on every keystroke, show an
   inline error, keep the last valid value" fix is caught by the suite, not only by a browser check. */
class FakeEl {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.style = {};
    this._class = '';
    this._text = '';
  }
  set className(v) { this._class = v || ''; }
  get className() { return this._class; }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { for (const n of nodes) { if (n == null) continue; n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { for (const c of this.children) c.parentNode = null; this.children = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener() {}
  removeEventListener() {}
  focus() {}
  querySelector() { return null; }
}

const require = createRequire(import.meta.url);
global.window = global.window || {};
global.window.HBCatalog = require('../../homebase/static/charts/catalog.js');
global.window.HBIcons = global.window.HBIcons || new Proxy({}, { get: () => '' });   // the Template button's chevron (merge with the presets wiring)
global.document = { createElement: (tag) => new FakeEl(tag), activeElement: null };
global.requestAnimationFrame = (fn) => { fn(); return 1; };
global.cancelAnimationFrame = () => {};
require('../../homebase/static/charts/indicator-settings-dialog.js');
const HBIndicatorSettings = global.window.HBIndicatorSettings;
const C = global.window.HBCatalog;

/* A minimal HBCell double: cfg.indicators + update() mirror what the dialog's preview()/commit()/revert() touch. */
function makeCell(inst) {
  const cfg = { indicators: [inst] };
  return { cfg, update: (patch) => { if (patch.indicators) cfg.indicators = patch.indicators; } };
}

function makeHost(cell, uid) {
  const commits = [];
  return { host: { cell, uid, closeMenu: () => {}, toggleMenu: () => {}, commit: (c) => commits.push(c), cancel: () => {} }, commits };
}

/* The time field is the 2nd field in VWAP's Inputs tab (anchor, customTime, band1On, ...): row index 1. */
function timeField(box) {
  const inputsPane = box.children[0].children[1];   // set-body -> set-pane (tabs hidden or not, pane is index 1)
  const row = inputsPane.children[1];                // customTime's .field row
  return { ctl: row.children[1], err: row.children[2] };
}

function openVwap(customTime = '02:00') {
  const inst = C.instance('vwap', { anchor: 'custom', customTime });
  const cell = makeCell(inst);
  const box = new FakeEl('div');
  const { host, commits } = makeHost(cell, inst.uid);
  const ctl = HBIndicatorSettings.mount(box, host);
  return { box, cell, inst, ctl, commits };
}

test('typing "9:30" (no leading zero, no padding) previews live once it parses -- no error, no revert to 02:00', () => {
  const { box, cell } = openVwap();
  const { ctl, err } = timeField(box);
  ctl.value = '9:30';
  ctl.oninput();
  assert.equal(err.hidden, true);
  assert.equal(cell.cfg.indicators[0].params.customTime, '09:30');
});

test('an incomplete value while typing never re-clamps to the factory default or errors', () => {
  const { box, cell, inst } = openVwap('16:00');
  const { ctl, err } = timeField(box);
  for (const partial of ['1', '16', '16:', '16:0']) {
    ctl.value = partial;
    ctl.oninput();
    assert.equal(err.hidden, true, partial);
    // still the last valid value on the chart -- never silently reverted to the factory default (02:00)
    assert.equal(cell.cfg.indicators[0].params.customTime, '16:00', partial);
  }
  assert.notEqual(inst.params.customTime, '02:00');
});

test('leaving the field (blur) on a bad value shows an inline error and keeps the last valid value, not 02:00', () => {
  const { box, cell } = openVwap('16:00');
  const { ctl, err } = timeField(box);
  ctl.value = 'lunchtime';
  ctl.oninput();               // never previewed (unparseable)
  ctl.onblur();                 // settle() on leaving the field
  assert.equal(err.hidden, false);
  assert.match(err.textContent, /HH:MM/);
  assert.equal(ctl.value, '16:00');                              // the input snaps back to the last valid value
  assert.equal(cell.cfg.indicators[0].params.customTime, '16:00'); // never the factory default (02:00)
});

test('Enter settles the field the same way blur does, and a later valid entry clears the error', () => {
  const { box, cell } = openVwap('16:00');
  const { ctl, err } = timeField(box);
  ctl.value = 'nope';
  ctl.onkeydown({ key: 'Enter', preventDefault: () => {} });
  assert.equal(err.hidden, false);
  ctl.value = '930';
  ctl.oninput();
  assert.equal(err.hidden, true);
  assert.equal(cell.cfg.indicators[0].params.customTime, '09:30');
});

test('Cancel (revert) puts the instance back to what it was when the dialog opened', () => {
  const { box, cell, ctl } = openVwap('16:00');
  const field = timeField(box);
  field.ctl.value = '09:30';
  field.ctl.oninput();
  assert.equal(cell.cfg.indicators[0].params.customTime, '09:30');
  ctl.revert();
  assert.equal(cell.cfg.indicators[0].params.customTime, '16:00');
});
