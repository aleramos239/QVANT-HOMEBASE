import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import vm from 'node:vm';

/* desklabset.js: the settings a Lab strategy declared adjustable, as READ-ONLY rows in the Desk's Setup panel (per-account
   settings, task 5: each account row is where size and the stops are edited now). Run against a tiny fake document. */
const require = createRequire(import.meta.url);

function fakeDoc() {
  const mk = (tag) => ({ tag, className: '', children: [], listeners: {}, style: {}, attrs: {}, hidden: false, textContent: '',
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
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
  { key: 'big_body', label: 'Big candle: body over (pts)', type: 'float', default: 25, min: 1, max: 500, step: 1 },
  { key: 'red_5m', label: 'Red-folder days', type: 'bool', default: false }];
const LAB = (over = {}) => ({ settings: SPEC, params: { open_min: '5', big_body: 25, red_5m: false }, read_only: false, ...over });
const walk = (n) => [n, ...n.children.flatMap(walk)];

test('a strategy with no settings gets no rows', () => {
  const { S } = load();
  assert.deepEqual(S.nodes('lab_x', { settings: [], params: {} }, false), []);
  assert.deepEqual(S.nodes('lab_x', null, false), []);
  assert.deepEqual(S.nodes('lab_x', { params: {} }, false), []);
});

test('one text row per setting: the label and the value in force, no input and no button', () => {
  const { S } = load();
  const rows = S.nodes('lab_x', LAB({ params: { open_min: '1', big_body: 40, red_5m: true } }), false);
  assert.equal(rows.length, 3);
  assert.deepEqual(rows.map((r) => [r.children[0].textContent, r.children[1].textContent]),
    [['Opening candle (minutes)', '1'], ['Big candle: body over (pts)', '40'], ['Red-folder days', 'On']]);
  for (const r of rows) {
    assert.equal(r.className, 'hb-row');
    assert.equal(r.children[0].className, 'hb-row-k');
    assert.equal(r.children[1].className, 'hb-row-v');
    assert.deepEqual(walk(r).filter((n) => ['input', 'select', 'button'].includes(n.tag)), []);
  }
});

test('a setting the Desk gave no value for shows its default; an off switch reads Off', () => {
  const { S } = load();
  const rows = S.nodes('lab_x', { settings: SPEC, params: {} }, false);
  assert.deepEqual(rows.map((r) => r.children[1].textContent), ['5', '25', 'Off']);
});

test('nothing here ever calls setLabSetting, read-only Desk or not', () => {
  let called = 0;
  const { S } = load({ setLabSetting: async () => { called++; return ''; } });
  for (const ro of [false, true]) {
    for (const r of S.nodes('lab_x', LAB({ read_only: ro }), ro)) for (const n of walk(r)) {
      assert.deepEqual(Object.keys(n.listeners), []);
    }
  }
  assert.equal(called, 0);
});

test('sig changes only when something the rows show changes', () => {
  const { S } = load();
  const a = S.sig(LAB());
  assert.equal(S.sig(LAB({ other: 1 })), a);
  assert.notEqual(S.sig(LAB({ params: { open_min: '1', big_body: 25, red_5m: false } })), a);
  assert.notEqual(S.sig(LAB({ read_only: true })), a);
});

test('3.2 the page\'s setLabSetting takes the extra `from` and sends the same body as before', async () => {
  const { HTML } = await import('./deskpage.mjs');   // the Desk page with its desk/*.js put back inline
  const fn = HTML.slice(HTML.indexOf('async function setLabSetting('), HTML.indexOf('/* Flatten & turn off believes only'));
  assert.ok(fn.length > 0 && fn.length < 2400, 'the page still has its setLabSetting');
  const posts = [];
  const ctx = vm.createContext({ posts, DEMO: false, ST: { strategies: {} }, stratLabel: (n) => n, refresh: () => {}, toast: () => {},
    answerWhy: () => 'x', killText: (t) => t, post: async (url, body) => { posts.push([url, body]); return { ok: true }; } });
  vm.runInContext(fn + '\nglobalThis.f = setLabSetting;', ctx);
  assert.equal(await ctx.f('lab_x', 'open_min', '1', { from: '5' }), '');
  assert.equal(await ctx.f('lab_x', 'open_min', '1'), '');
  assert.equal(JSON.stringify(posts[0]), JSON.stringify(['/api/lab-settings', { strategy: 'lab_x', settings: { open_min: '1' } }]));
  assert.equal(JSON.stringify(posts[1]), JSON.stringify(posts[0]), 'with or without `from`, the same request');
});
