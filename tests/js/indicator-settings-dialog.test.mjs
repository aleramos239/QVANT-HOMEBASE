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

/* 2026-10-21: the footprint's new options reuse the dropdown and number rows; the row text's first choice is the empty one ("as before"). */
test('footprint: the new options are dropdowns and number boxes at today\'s values, and a pick reaches the chart', () => {
  const inst = C.instance('footprint');
  const cell = makeCell(inst);
  const box = new FakeEl('div');
  HBIndicatorSettings.mount(box, makeHost(cell, inst.uid).host);
  const sel = (label) => find(pane(box), (n) => n.tagName === 'select' && n.attrs['aria-label'] === label)[0];
  const text = sel('What each row shows (overrides the numbers above)'), imb = sel('Imbalance rule');
  assert.equal(text.value, '', 'the empty choice is selected: the Numbers setting still decides');
  assert.deepEqual(imb.children.map((o) => o.value), ['homebase', 'atas', 'exocharts', 'sierra']);
  assert.equal(imb.value, 'homebase');
  text.value = 'trades'; text.onchange();
  imb.value = 'atas'; imb.onchange();
  assert.deepEqual([cell.cfg.indicators[0].params.text, cell.cfg.indicators[0].params.imb], ['trades', 'atas']);
  const nums = find(pane(box), (n) => n.tagName === 'input' && n.type === 'number').length;
  assert.ok(nums >= 3, 'the ratio, the stack and the two new minimums are number boxes');
});

/* ---- Pine: the script picker and the script's own inputs ---- */
const later = () => new Promise((r) => setTimeout(r, 0));
const LIST = [{ name: 'a.pine', title: 'Alpha', kind: 'indicator', version: 5 }, { name: 'b.pine', title: null, kind: 'strategy', version: 5 }];
const META = { inputs: [
  { id: 'in_0', varId: 'len', title: 'Length', type: 'int', defval: 14, minval: 1, maxval: 100, step: 2 },
  { id: 'in_1', varId: 'mult', title: 'Mult', type: 'float', defval: 1.5 },
  { id: 'in_2', title: 'Flag', type: 'bool', defval: true },
  { id: 'in_3', title: 'Kind', type: 'string', defval: 'EMA', options: ['SMA', 'EMA'] },
  { id: 'in_4', title: 'Label', type: 'string', defval: 'x' },
  { id: 'in_5', title: 'Col', type: 'color', defval: '#F23645FF' },
  { id: 'in_6', title: 'Step', type: 'int', defval: 2, options: [1, 2, 3] }], title: 'A', error: null, running: false };
function openPine(params = { script: 'a.pine' }, meta = META) {
  const inst = C.instance('pine', params);
  const cell = makeCell(inst);
  cell.meta = meta;
  cell.pineMeta = () => cell.meta;
  const box = new FakeEl('div');
  const { host, commits } = makeHost(cell, inst.uid);
  const ctl = HBIndicatorSettings.mount(box, host);
  return { box, cell, inst, ctl, commits, params: () => cell.cfg.indicators[0].params };
}
const fieldOf = (box, label) => find(box, (n) => n._class === 'field').find((f) => f.children[0] && f.children[0]._text === label);
const inputOf = (box, label) => fieldOf(box, label).children[1];

test('pine: the Script row lists the server\'s scripts (name and title) and keeps a saved name whose file is gone; a pick reaches the chart', async () => {
  global.window.fetch = async () => ({ ok: true, json: async () => LIST });
  const { box, params } = openPine({ script: 'gone.pine', inputs: { Length: 20 } });
  await later();
  const sel = inputOf(box, 'Script');
  assert.deepEqual(sel.children.map((o) => [o.value, o._text]), [['', 'Choose a script'], ['a.pine', 'a.pine - Alpha'], ['b.pine', 'b.pine'], ['gone.pine', 'gone.pine']]);
  assert.equal(sel.value, 'gone.pine');
  sel.value = 'a.pine';
  sel.onchange();
  assert.equal(params().script, 'a.pine');
  assert.ok(!('inputs' in params()), 'the old script\'s inputs mean nothing to the new one');
});

test('pine: a list that cannot load, or is empty, is said in plain words', async () => {
  global.window.fetch = async () => ({ ok: false });
  let o = openPine({});
  await later();
  assert.equal(find(o.box, (n) => n._class === 'dlg-err').some((e) => e._text === 'Could not load the script list' && e.hidden === false), true);
  global.window.fetch = async () => ({ ok: true, json: async () => [] });
  o = openPine({});
  await later();
  assert.equal(find(o.box, (n) => n._class === 'dlg-err').some((e) => /No Pine scripts/.test(e._text)), true);
  global.window.fetch = undefined;
  assert.doesNotThrow(() => openPine({}));
});

test('pine: one row per input of the script, each as the kind of control its type needs', async () => {
  global.window.fetch = async () => ({ ok: true, json: async () => LIST });
  const { box } = openPine();
  const len = inputOf(box, 'Length'), mult = inputOf(box, 'Mult'), flag = inputOf(box, 'Flag'), kind = inputOf(box, 'Kind');
  assert.deepEqual([len.type, len.min, len.max, len.step, len.value], ['number', '1', '100', '2', '14']);
  assert.deepEqual([mult.type, mult.step, mult.value], ['number', 'any', '1.5']);
  assert.deepEqual([flag.type, flag.checked], ['checkbox', true]);
  assert.deepEqual([kind.tagName, kind.children.map((o) => o.value), kind.value], ['select', ['SMA', 'EMA'], 'EMA']);
  assert.equal(inputOf(box, 'Label').type, 'text');
  assert.deepEqual([inputOf(box, 'Col').type, inputOf(box, 'Col').value], ['color', '#F23645']);
  assert.deepEqual(inputOf(box, 'Step').children.map((o) => o.value), ['1', '2', '3']);
});

test('pine: a changed input is stored by its variable name (its title when none shares it, else its id) and reaches the chart; put back to the script\'s own value it is dropped, and the last one takes the key with it', () => {
  const { box, params } = openPine();
  const len = inputOf(box, 'Length');
  len.value = '30';
  len.oninput();
  assert.deepEqual(params().inputs, { len: 30 });
  const flag = inputOf(box, 'Flag');
  flag.checked = false;
  flag.onchange();
  const kind = inputOf(box, 'Kind');
  kind.value = 'SMA';
  kind.onchange();
  const step = inputOf(box, 'Step');
  step.value = '3';
  step.onchange();
  inputOf(box, 'Mult').value = '2.25';
  inputOf(box, 'Mult').oninput();
  inputOf(box, 'Label').value = 'hello';
  inputOf(box, 'Label').oninput();
  inputOf(box, 'Col').value = '#00ff00';
  inputOf(box, 'Col').oninput();
  assert.deepEqual(params().inputs, { len: 30, Flag: false, Kind: 'SMA', Step: 3, mult: 2.25, Label: 'hello', Col: '#00ff00' }, 'a number option stays a number');
  len.value = '14'; len.oninput();
  assert.ok(!('len' in params().inputs));
  len.value = ''; len.oninput();
  assert.ok(!('len' in params().inputs), 'an empty box is not a value');
  flag.checked = true; flag.onchange();
  kind.value = 'EMA'; kind.onchange();
  step.value = '2'; step.onchange();
  inputOf(box, 'Mult').value = '1.5'; inputOf(box, 'Mult').oninput();
  inputOf(box, 'Label').value = 'x'; inputOf(box, 'Label').oninput();
  assert.deepEqual(params().inputs, { Col: '#00ff00' }, 'everything put back is gone');
  inputOf(box, 'Col').value = '#F23645'; inputOf(box, 'Col').oninput();
  assert.deepEqual(Object.keys(params().inputs), ['Col'], 'a colour can only be picked, not put back: it stays');
});

/* Two inputs of one title (the same "Length" under two groups): two rows, two keys. */
const TWIN = { inputs: [
  { id: 'in_0', varId: 'a', title: 'Length', type: 'int', defval: 3, group: 'Fast' },
  { id: 'in_1', varId: 'b', title: 'Length', type: 'int', defval: 10, group: 'Slow' }], title: 'T', error: null, running: false };
const rowsOf = (box, label) => find(box, (n) => n._class === 'field').filter((f) => f.children[0] && f.children[0]._text === label).map((f) => f.children[1]);
const type = (ctl, v) => { ctl.value = String(v); ctl.oninput(); };

test('pine: two inputs with one title are two rows with their own keys; setting one leaves the other (and its default) alone', () => {
  const { box, params } = openPine({ script: 'a.pine' }, TWIN);
  const [fast, slow] = rowsOf(box, 'Length');
  assert.deepEqual([fast.value, slow.value], ['3', '10']);
  type(fast, 5);
  assert.deepEqual(params().inputs, { a: 5 });
  assert.equal(slow.value, '10', 'the other row still reads its own default');
  type(slow, 20);
  assert.deepEqual(params().inputs, { a: 5, b: 20 });
  type(slow, 10);
  assert.deepEqual(params().inputs, { a: 5 }, 'the second put back to its default takes only its own key');
  type(fast, 3);
  assert.ok(!('inputs' in params()));
});

/* input.price is a float and input.time a whole number of ms: both are numbers to the script, never the text a text box gives. */
const PRICE_TIME = { inputs: [
  { id: 'in_0', varId: 'lvl', title: 'Level', type: 'price', defval: 100 },
  { id: 'in_1', varId: 'when', title: 'When', type: 'time', defval: 1577944800000 }], title: 'PT', error: null, running: false };

test('pine: a price input is a number box saved as a float, a time input one saved as whole ms; put back to the default each is dropped', () => {
  const { box, params } = openPine({ script: 'a.pine' }, PRICE_TIME);
  const lvl = inputOf(box, 'Level'), when = inputOf(box, 'When');
  assert.deepEqual([lvl.type, lvl.step, lvl.value, when.type, when.step, when.value], ['number', 'any', '100', 'number', '1', '1577944800000']);
  type(lvl, 105.25);
  type(when, 1800000000000.4);
  assert.deepEqual(params().inputs, { lvl: 105.25, when: 1800000000000 });
  assert.deepEqual(Object.values(params().inputs).map((v) => typeof v), ['number', 'number']);
  type(lvl, '');
  assert.deepEqual(params().inputs, { lvl: 105.25, when: 1800000000000 }, 'an empty box is not a value');
  type(lvl, 100);
  type(when, 1577944800000);
  assert.ok(!('inputs' in params()));
});

test('pine: an old save keyed by title keeps working; its value moves to the input\'s own key and the title key goes', () => {
  const { box, params } = openPine({ script: 'a.pine', inputs: { Length: 20, Mult: 2, Gone: 1 } });
  assert.equal(inputOf(box, 'Length').value, '20', 'read by title');
  assert.equal(inputOf(box, 'Mult').value, '2');
  inputOf(box, 'Flag').checked = false;
  inputOf(box, 'Flag').onchange();
  assert.deepEqual(params().inputs, { len: 20, mult: 2, Gone: 1, Flag: false }, 'a title of no input of this script is left as it was');
  type(inputOf(box, 'Length'), 14);
  assert.ok(!('len' in params().inputs) && !('Length' in params().inputs), 'put back to the default: gone for good');
  const twin = openPine({ script: 'a.pine', inputs: { Length: 7 } }, TWIN);
  const [fast, slow] = rowsOf(twin.box, 'Length');
  assert.deepEqual([fast.value, slow.value], ['7', '7'], 'both rows showed it before, both keep it');
  type(fast, 5);
  assert.deepEqual(twin.params().inputs, { a: 5, b: 7 });
});

test('pine: a save stays on its input when the script gains an input before it (no varId: the title is the key, not the position)', () => {
  const { box, params, cell } = openPine({ script: 'a.pine' });
  inputOf(box, 'Flag').checked = false;
  inputOf(box, 'Flag').onchange();
  assert.deepEqual(params().inputs, { Flag: false });
  const grown = { ...META, inputs: [{ id: 'in_0', title: 'Fresh', type: 'bool', defval: true }, ...META.inputs.map((x) => ({ ...x, id: 'in_' + (+x.id.slice(3) + 1) }))] };
  cell.meta = grown;
  cell.onPineMeta('p');
  assert.equal(inputOf(box, 'Flag').checked, false, 'still on Flag');
  assert.equal(inputOf(box, 'Fresh').checked, true, 'the new first input reads its own default');
  assert.deepEqual(params().inputs, { Flag: false });
  const clash = { inputs: [{ id: 'in_0', title: 'in_1', type: 'int', defval: 1 }, { id: 'in_1', title: 'Other', type: 'int', defval: 2 }], title: 'C', error: null, running: false };
  const o = openPine({ script: 'a.pine' }, clash);
  type(inputOf(o.box, 'in_1'), 5);
  assert.deepEqual(o.params().inputs, { in_0: 5 }, 'a title that is another input\'s id is not used as a key');
});

test('pine: the inputs block is drawn again when the script\'s inputs or error change, not on each run (a number being typed keeps its box)', () => {
  const o = openPine();
  const first = find(o.box, (n) => n._class === 'pine-inputs')[0].children.slice();
  assert.equal(first.length, 7);
  o.cell.onPineMeta('p');
  assert.deepEqual(find(o.box, (n) => n._class === 'pine-inputs')[0].children, first, 'same inputs: the same rows');
  o.cell.meta = { ...META, error: 'line 3: oops' };
  o.cell.onPineMeta('p');
  const wrap = find(o.box, (n) => n._class === 'pine-inputs')[0];
  assert.equal(wrap.children[0]._text, 'line 3: oops');
  assert.equal(wrap.children[0].attrs.role, 'alert');
  o.cell.meta = { inputs: [{ id: 'in_0', title: 'Only', type: 'int', defval: 1 }], title: 'B', error: null, running: false };
  o.cell.onPineMeta('p');
  assert.deepEqual(wrap.children.map((r) => r.children[0]._text), ['Only']);
  o.cell.meta = null;
  o.cell.onPineMeta('p');
  assert.deepEqual(wrap.children, []);
});

test('pine: Cancel and OK let go of the cell\'s hook; a cell with no Pine support (no pineMeta) opens an empty block', () => {
  const a = openPine();
  assert.equal(typeof a.cell.onPineMeta, 'function');
  a.ctl.revert();
  assert.equal(a.cell.onPineMeta, null);
  const inst = C.instance('pine', { script: 'a.pine' });
  const cell = makeCell(inst);
  const box = new FakeEl('div');
  const { host } = makeHost(cell, inst.uid);
  HBIndicatorSettings.mount(box, host);
  assert.deepEqual(find(box, (n) => n._class === 'pine-inputs')[0].children, []);
});
