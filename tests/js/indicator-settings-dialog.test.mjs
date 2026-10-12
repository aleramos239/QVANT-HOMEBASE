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
global.requestAnimationFrame = (fn) => { fn(); return 0; };   // runs at once; 0 so preview() is never left "pending"
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

/* The first line's time box is the first HH:MM input in VWAP's Inputs tab (its lines editor); its error line sits beside it. */
function walk(el, fn) { fn(el); for (const c of el.children) walk(c, fn); }
function find(el, pred) { const out = []; walk(el, (n) => { if (pred(n)) out.push(n); }); return out; }
function timeField(box) {
  const item = find(box, (n) => n._class === 'vl-item')[0];
  return { ctl: find(item, (n) => /\bsw-hex\b/.test(n._class))[0], err: find(item, (n) => n._class === 'dlg-err')[0] };
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

/* 2026-10-12: a choice is a dropdown (a row of pills overflowed the card); a VWAP holds several lines in ONE
   indicator, each its own anchor and colour. */
function pane(box) { return box.children[0].children[1]; }

test('a choice is a <select> with every option, set to the current value', () => {
  const inst = C.instance('footprint');
  const cell = makeCell(inst);
  const box = new FakeEl('div');
  HBIndicatorSettings.mount(box, makeHost(cell, inst.uid).host);
  const sel = find(pane(box), (n) => n.tagName === 'select' && n.attrs['aria-label'] === 'Numbers in each row')[0];
  assert.ok(sel, 'the numbers choice is a dropdown');
  assert.deepEqual(sel.children.map((o) => o.value), ['both', 'delta', 'total', 'none']);
  assert.equal(sel.value, 'both');
  assert.equal(find(pane(box), (n) => /\bseg\b/.test(n.className)).length, 0, 'no pill row left');
});

test('VWAP: the first line is a row with an anchor dropdown, a time box only for Custom time and a colour', () => {
  const { box } = openVwap();
  const row = find(pane(box), (n) => n._class === 'vl-row');
  assert.equal(row.length, 1);
  const sel = find(row[0], (n) => n.tagName === 'select')[0];
  assert.deepEqual(sel.children.map((o) => o.value), ['eth', 'rth', 'custom', 'week', 'month']);
  assert.equal(sel.value, 'custom');
  assert.equal(find(row[0], (n) => /\bsw-hex\b/.test(n._class)).length, 1);
  sel.value = 'rth';
  sel.onchange();
  const again = find(pane(box), (n) => n._class === 'vl-row')[0];
  assert.equal(find(again, (n) => /\bsw-hex\b/.test(n._class)).length, 0, 'no time box for RTH');
});

test('"+ Add line" puts a second line in the same VWAP: its own anchor and colour, no new indicator', () => {
  const { box, cell } = openVwap();
  const add = find(pane(box), (n) => n.tagName === 'button' && /Add line/.test(n.textContent))[0];
  add.onclick();
  assert.equal(cell.cfg.indicators.length, 1, 'still one indicator');
  const more = cell.cfg.indicators[0].params.more;
  assert.equal(more.length, 1);
  assert.equal(more[0].anchor, 'custom');
  assert.equal(more[0].customTime, '09:30');
  assert.ok(more[0].color);
  assert.deepEqual(C.serverKeys(cell.cfg.indicators), ['vwap:t0200', 'vwap:t0930']);
});

test('a second line follows its own anchor; Cancel takes it away again', () => {
  const { box, cell, ctl } = openVwap('16:00');
  find(pane(box), (n) => n.tagName === 'button' && /Add line/.test(n.textContent))[0].onclick();
  const rows = find(pane(box), (n) => n._class === 'vl-row');
  assert.equal(rows.length, 2);
  const sel = find(rows[1], (n) => n.tagName === 'select')[0];
  sel.value = 'eth';
  sel.onchange();
  assert.deepEqual(C.serverKeys(cell.cfg.indicators), ['vwap:t1600', 'vwap']);
  ctl.revert();
  assert.equal(cell.cfg.indicators[0].params.more, undefined);
});

test('the first line colour recolours it and its three bands', () => {
  const inst = C.instance('vwap', { anchor: 'rth' });
  const cell = makeCell(inst);
  const box = new FakeEl('div');
  let fill = null;
  const host = { cell, uid: inst.uid, closeMenu: () => {}, toggleMenu: (a, cls, f) => { fill = f; }, commit() {}, cancel() {} };
  HBIndicatorSettings.mount(box, host);
  find(pane(box), (n) => n.tagName === 'button' && n._class === 'swatch')[0].onclick();
  const m = new FakeEl('div');
  fill(m);
  const cells = find(m, (n) => n._class === 'sw-cell');
  cells[1].onclick();
  const want = cells[1].style.background, st = cell.cfg.indicators[0].style;
  assert.ok(want);
  for (const k of ['main', 'band1', 'band2', 'band3']) assert.equal(st[k].color, want);
});
