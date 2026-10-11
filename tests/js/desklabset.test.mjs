import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* desklabset.js: the settings a Lab strategy declared adjustable, as controls in the Desk's Setup panel. Run against a
   tiny fake document: ONE persistent set of nodes per strategy, what the page shows, what a save sends, and that a field
   being typed in is never overwritten by a repaint. */
const require = createRequire(import.meta.url);

function fakeDoc() {
  const mk = (tag) => ({ tag, className: '', children: [], listeners: {}, style: {}, attrs: {}, hidden: false, disabled: false, value: '',
    textContent: '', appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); } });
  return { activeElement: null, createElement: mk };
}
function load({ setLabSetting } = {}) {
  const doc = fakeDoc();
  const root = { document: doc, setLabSetting };
  new Function('window', require('node:fs').readFileSync(new URL('../../homebase/static/desklabset.js', import.meta.url), 'utf8')
    .replace('typeof window !== "undefined" ? window : this', 'window'))(root);
  return { S: root.DeskLabSet, doc, root };
}
const SPEC = [{ key: 'open_min', label: 'Opening candle (minutes)', type: 'choice', default: '5', choices: ['1', '5'] },
  { key: 'big_body', label: 'Big candle: body over (pts)', type: 'float', default: 25, min: 1, max: 500, step: 1 }];
const LAB = (over = {}) => ({ settings: SPEC, params: { open_min: '5', big_body: 25 }, read_only: false, ...over });
const fire = (n, type, ev = {}) => Promise.all((n.listeners[type] || []).map((f) => f(ev)));

test('a strategy with no settings gets no rows', () => {
  const { S } = load();
  assert.deepEqual(S.nodes('lab_x', { settings: [], params: {} }, false), []);
  assert.deepEqual(S.nodes('lab_x', null, false), []);
  assert.deepEqual(S.nodes('lab_x', { params: {} }, false), []);
});

test('one row per setting plus a hidden message line, the values in force', () => {
  const { S } = load();
  const rows = S.nodes('lab_x', LAB({ params: { open_min: '1', big_body: 40 } }), false);
  assert.equal(rows.length, 3);
  const [r1, r2, msg] = rows;
  assert.equal(r1.children[0].textContent, 'Opening candle (minutes)');
  assert.equal(r1.children[1].tag, 'select');
  assert.deepEqual(r1.children[1].children.map((o) => o.value), ['1', '5']);
  assert.equal(r1.children[1].value, '1');
  assert.equal(r2.children[1].tag, 'input');
  assert.equal(r2.children[1].type, 'number');
  assert.equal(r2.children[1].value, '40');
  assert.deepEqual([r2.children[1].min, r2.children[1].max, r2.children[1].step], ['1', '500', '1']);
  assert.equal(msg.hidden, true);
});

test('the same nodes come back on every call and a repaint follows the Desk unless a field is being typed in', () => {
  const { S, doc } = load();
  const a = S.nodes('lab_x', LAB(), false);
  const b = S.nodes('lab_x', LAB({ params: { open_min: '1', big_body: 25 } }), false);
  assert.equal(a[0], b[0]);
  assert.equal(b[0].children[1].value, '1');                           // follows the Desk's value
  doc.activeElement = b[1].children[1];                                // the owner has the cursor in it
  S.nodes('lab_x', LAB({ params: { open_min: '1', big_body: 99 } }), false);
  assert.equal(b[1].children[1].value, '25');                          // not overwritten under the hand
  // a different spec list (promoted again with other settings) builds new rows
  const c = S.nodes('lab_x', LAB({ settings: [SPEC[0]] }), false);
  assert.notEqual(c[0], a[0]);
  assert.equal(c.length, 2);
});

test('a save sends the one setting through the page and shows the refusal', async () => {
  const calls = [];
  let answer = '';
  const { S } = load({ setLabSetting: async (n, k, v) => { calls.push([n, k, v]); return answer; } });
  const rows = S.nodes('lab_x', LAB(), false);
  const [r1, r2, msg] = rows;
  r1.children[1].value = '1';
  await fire(r1.children[1], 'change');
  await fire(r1.children[2], 'click');
  assert.deepEqual(calls, [['lab_x', 'open_min', '1']]);
  assert.equal(msg.hidden, true);
  r2.children[1].value = '30';
  answer = 'Not while it is in session. Change it before 09:25 or after 15:55 ET.';
  await fire(r2.children[1], 'keydown', { key: 'Enter' });
  assert.deepEqual(calls[1], ['lab_x', 'big_body', 30]);              // a number goes as a number
  assert.equal(msg.hidden, false);
  assert.match(msg.textContent, /Not while it is in session/);
  assert.equal(r2.children[2].disabled, false);                        // the button is back
});

test('a number field that is not a number is never sent', async () => {
  const calls = [];
  const { S } = load({ setLabSetting: async (...a) => { calls.push(a); return ''; } });
  const rows = S.nodes('lab_x', LAB(), false);
  rows[1].children[1].value = 'abc';
  await fire(rows[1].children[2], 'click');
  assert.deepEqual(calls, []);
  assert.equal(rows[2].hidden, false);
  assert.match(rows[2].textContent, /a number/);
});

test('a read-only Desk disables the controls', () => {
  const { S } = load();
  const rows = S.nodes('lab_x', LAB({ read_only: true }), true);
  assert.equal(rows[0].children[1].disabled, true);
  assert.equal(rows[0].children[2].disabled, true);
  const again = S.nodes('lab_x', LAB(), false);
  assert.equal(again[0].children[1].disabled, false);
});

test('sig changes only when something the controls show changes', () => {
  const { S } = load();
  const a = S.sig(LAB());
  assert.equal(S.sig(LAB({ other: 1 })), a);
  assert.notEqual(S.sig(LAB({ params: { open_min: '1', big_body: 25 } })), a);
  assert.notEqual(S.sig(LAB({ read_only: true })), a);
});

test('an on/off setting is an On / Off menu that sends a real boolean', async () => {
  const calls = [];
  const { S } = load({ setLabSetting: async (n, k, v) => { calls.push([n, k, v]); return ''; } });
  const spec = [{ key: 'red_5m', label: 'Red-folder days: 5-minute candle', type: 'bool', default: false }];
  const rows = S.nodes('lab_x', { settings: spec, params: { red_5m: false }, read_only: false }, false);
  const sel = rows[0].children[1];
  assert.equal(sel.tag, 'select');
  assert.deepEqual(sel.children.map((o) => [o.value, o.textContent]), [['true', 'On'], ['false', 'Off']]);
  assert.equal(sel.value, 'false');
  sel.value = 'true';
  await fire(sel, 'change');
  await fire(rows[0].children[2], 'click');
  assert.deepEqual(calls, [['lab_x', 'red_5m', true]]);
  const on = S.nodes('lab_x', { settings: spec, params: { red_5m: true }, read_only: false }, false);
  assert.equal(on[0].children[1].value, 'true');                       // follows the Desk's value
});
