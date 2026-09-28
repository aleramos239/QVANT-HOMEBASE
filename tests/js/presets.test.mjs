import { test } from 'node:test';
import assert from 'node:assert/strict';

/* presets.js is browser-only (fetch, DOM), like settings-dialog.js: no module.exports fallback.
   A small window shim (just document.createElement's handful of element APIs the file actually
   calls) lets it load under `node --test`, so its pure logic -- name validation, how a saved
   preset map turns into the menu's sorted rows -- is covered without a real browser. The DOM
   menu-builder itself (menu()) mirrors settings-dialog.js' own already-tested templateMenu almost
   exactly and is exercised through its client (list/save/remove) below rather than reimplemented
   here. */
class FakeEl {
  constructor(tag) { this.tagName = tag; this.children = []; this.parentNode = null; this._class = ''; this._text = ''; this.attrs = {}; this.style = {}; this.isConnected = true; }
  set className(v) { this._class = v || ''; }
  get className() { return this._class; }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { for (const n of nodes) { if (n == null) continue; n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { for (const c of this.children) c.parentNode = null; this.children = []; this.append(...nodes); }
  replaceWith(node) { if (!this.parentNode) return; const i = this.parentNode.children.indexOf(this); if (i >= 0) { this.parentNode.children[i] = node; node.parentNode = this.parentNode; } this.parentNode = null; }
  remove() { if (this.parentNode) { const i = this.parentNode.children.indexOf(this); if (i >= 0) this.parentNode.children.splice(i, 1); } this.parentNode = null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener() {}
  removeEventListener() {}
  focus() {}
  querySelector() { return null; }
  get classList() { return { add() {}, toggle() {}, contains() { return false; } }; }
}

function withDom(fn) {
  const hadWindow = globalThis.window, hadDoc = globalThis.document;
  globalThis.document = { createElement: (tag) => new FakeEl(tag) };
  globalThis.window = { HBIcons: { x: '<svg></svg>' }, document: globalThis.document };
  try { return fn(); }
  finally {
    if (hadWindow === undefined) delete globalThis.window; else globalThis.window = hadWindow;
    if (hadDoc === undefined) delete globalThis.document; else globalThis.document = hadDoc;
  }
}

function load() {
  delete require.cache[require.resolve('../../homebase/static/charts/presets.js')];
  require('../../homebase/static/charts/presets.js');
  return globalThis.window.HBPresets;
}
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

test('presetNameError: the same rule as check_preset_name in presets.py', () => {
  const P = withDom(load);
  assert.equal(P.presetNameError('My preset'), '');
  assert.equal(P.presetNameError('x'.repeat(40)), '');
  assert.equal(P.presetNameError('__default__'), '');   // a name like any other here
  assert.notEqual(P.presetNameError(''), '');
  assert.notEqual(P.presetNameError('x'.repeat(41)), '');
  assert.notEqual(P.presetNameError('a/b'), '');
  assert.notEqual(P.presetNameError('a\\b'), '');
  assert.notEqual(P.presetNameError('a..b'), '');
  assert.notEqual(P.presetNameError('.'), '');
  assert.notEqual(P.presetNameError('tab\there'), '');
  assert.notEqual(P.presetNameError(7), '');
  assert.notEqual(P.presetNameError(null), '');
});

test('sortedEntries: A-Z, __default__ left out (the menu shows it via Apply/Save as default)', () => {
  const P = withDom(load);
  const all = { Bold: { width: 3 }, __default__: { width: 2 }, aardvark: { width: 1 }, Zebra: {} };
  assert.deepEqual(P.sortedEntries(all), [['aardvark', { width: 1 }], ['Bold', { width: 3 }], ['Zebra', {}]]);
  assert.deepEqual(P.sortedEntries({}), []);
  assert.deepEqual(P.sortedEntries(null), []);
  assert.deepEqual(P.sortedEntries(undefined), []);
});

test('DEFAULT_NAME is "__default__", matching presets.py', () => {
  const P = withDom(load);
  assert.equal(P.DEFAULT_NAME, '__default__');
});

function fakeFetch(handler) {
  const calls = [];
  const f = async (url, opts = {}) => {
    const method = opts.method || 'GET';
    calls.push({ url, method, body: opts.body ? JSON.parse(opts.body) : undefined });
    const r = handler(url, method, opts) || { status: 200, body: { ok: true } };
    return { ok: r.status < 400, status: r.status, json: async () => r.body };
  };
  f.calls = calls;
  return f;
}

test('client(kind).list/save/remove hit /api/presets/<kind>[/<name>], URL-encoding the kind and name', async () => {
  const P = withDom(load);
  const f = fakeFetch((url, method) => {
    if (method === 'GET') return { status: 200, body: { A: { width: 1 } } };
    return { status: 200, body: { ok: true } };
  });
  const c = P.client('drawing:trend', f);
  assert.deepEqual(await c.list(), { A: { width: 1 } });
  assert.equal(f.calls[0].url, '/api/presets/drawing%3Atrend');
  assert.equal(await c.save('My preset', { width: 2 }), '');
  assert.equal(f.calls[1].url, '/api/presets/drawing%3Atrend/My%20preset');
  assert.equal(f.calls[1].method, 'PUT');
  assert.deepEqual(f.calls[1].body, { width: 2 });
  assert.equal(await c.remove('My preset'), '');
  assert.equal(f.calls[2].method, 'DELETE');
});

test('client(kind).save/remove report a failed write with the server\'s detail', async () => {
  const P = withDom(load);
  const f = fakeFetch(() => ({ status: 400, body: { detail: 'style.junk does not apply to a trend' } }));
  const c = P.client('drawing:trend', f);
  assert.equal(await c.save('A', {}), 'save failed (400): style.junk does not apply to a trend');
  assert.equal(await c.remove('A'), 'delete failed (400): style.junk does not apply to a trend');
});

test('client(kind).list returns null on a network error or a non-OK response', async () => {
  const P = withDom(load);
  const err = P.client('drawing:trend', async () => { throw new Error('offline'); });
  assert.equal(await err.list(), null);
  const bad = P.client('drawing:trend', fakeFetch(() => ({ status: 500, body: {} })));
  assert.equal(await bad.list(), null);
});

/* menu()'s three built-in actions (Save as.../Save as default/Apply default) are covered end to end by
   settings-dialog.test.mjs' own templateMenu (near-identical shape); this covers only what this file adds
   on top for the indicator dialog -- an `extra` list of plain menu rows (its "Reset to factory settings",
   nothing to do with the store) rendered after "Apply default" and before the saved-preset list, each one
   closing the menu and firing its own onclick, same as the built-in rows do. */
test('menu(): an `extra` row renders after Apply default, closes the menu and fires its own onclick', () => {
  const P = withDom(load);
  withDom(() => {
    let fill = null;
    const host = { toggleMenu(anchor, cls, f) { fill = f; }, closeMenu() { host.closed = true; }, placeMenu() {} };
    let resetCalled = false;
    P.menu(host, new FakeEl('button'), {
      kind: 'indicator:ema',
      current: () => ({ params: {}, style: null }),
      apply() {},
      extra: [{ label: 'Reset to factory settings', onclick: () => { resetCalled = true; } }],
    });
    const m = new FakeEl('div');
    fill(m);
    const rows = m.children.filter((c) => c.tagName === 'button').map((b) => b.children[0] && b.children[0].textContent);
    assert.deepEqual(rows, ['Save as…', 'Save as default', 'Apply default', 'Reset to factory settings']);
    const resetBtn = m.children.find((c) => c.tagName === 'button' && c.children[0] && c.children[0].textContent === 'Reset to factory settings');
    resetBtn.onclick();
    assert.equal(resetCalled, true);
    assert.equal(host.closed, true);
  });
});

test('menu(): no `extra` option (the drawing tools\' own call) renders only the three built-in rows', () => {
  const P = withDom(load);
  withDom(() => {
    let fill = null;
    const host = { toggleMenu(anchor, cls, f) { fill = f; }, closeMenu() {}, placeMenu() {} };
    P.menu(host, new FakeEl('button'), { kind: 'drawing:trend', current: () => ({}), apply() {} });
    const m = new FakeEl('div');
    fill(m);
    const rows = m.children.filter((c) => c.tagName === 'button').map((b) => b.children[0] && b.children[0].textContent);
    assert.deepEqual(rows, ['Save as…', 'Save as default', 'Apply default']);
  });
});
