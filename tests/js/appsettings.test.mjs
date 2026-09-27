import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

/* appsettings.js (Task 4, 2026-09-27 accounts-paper-layouts-appsettings plan) is a DOM-mounting
   module like settings-dialog.js: it reads/writes `window` at load time and has no
   `module.exports` fallback. Same small hand-written DOM/window shim as settings-dialog.test.mjs
   (just the element APIs this dialog actually calls), so it loads and runs for real under
   `node --test` instead of only ever running inside a browser check. */

class FakeEl {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this._class = '';
    this._text = '';
    this.hidden = false;
    this.type = '';
    this.checked = false;
    this.disabled = false;
    this.value = '';
    this.name = '';
    this.onclick = null;
    this.onchange = null;
  }
  set className(v) { this._class = v || ''; }
  get className() { return this._class; }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { for (const n of nodes) { if (n == null) continue; n.parentNode = this; this.children.push(n); } }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener() {}
  removeEventListener() {}
  focus() {}
  get classList() {
    const self = this;
    const tokens = () => self._class.split(/\s+/).filter(Boolean);
    return {
      add: (c) => { const s = new Set(tokens()); s.add(c); self._class = [...s].join(' '); },
      toggle: (c, on) => {
        const s = new Set(tokens());
        const want = on === undefined ? !s.has(c) : on;
        if (want) s.add(c); else s.delete(c);
        self._class = [...s].join(' ');
        return want;
      },
      contains: (c) => tokens().includes(c),
    };
  }
}

function descend(el, pred) {
  for (const c of el.children) { if (pred(c)) return c; const r = descend(c, pred); if (r) return r; }
  return null;
}
function findAll(el, pred) {
  const out = [];
  (function walk(e) { for (const c of e.children) { if (pred(c)) out.push(c); walk(c); } })(el);
  return out;
}
function findByOwnText(el, tag, text) {
  return descend({ children: [el] }, (c) => c.tagName === tag.toUpperCase() && c.textContent === text);
}

function loadDialog() {
  global.window = global.window || {};   // a dedicated object, not an alias for `global` itself
  global.document = { createElement: (tag) => new FakeEl(tag) };
  delete require.cache[require.resolve('../../homebase/static/charts/appsettings.js')];
  require('../../homebase/static/charts/appsettings.js');
  return global.window.HBAppSettings;
}
const AS = loadDialog();

/* A host double: getSettings/putSettings are driven explicitly per test (resolve/reject at will)
   rather than auto-resolving, so tests can assert the busy/disabled state WHILE a PUT is in
   flight -- the whole point of the "a second PUT while one is in flight is refused" contract. */
function makeHost({ initial = { md: 'demo' } } = {}) {
  let dark = false;
  const statusFns = new Set();
  const putCalls = [];
  let closed = false;
  const host = {
    getSettings: () => Promise.resolve(initial),
    putSettings: (patch) => { putCalls.push(patch); return host._nextPut; },
    status: () => null,
    onStatus: (fn) => { statusFns.add(fn); return () => statusFns.delete(fn); },
    isDark: () => dark,
    toggleTheme: () => { dark = !dark; },
    close: () => { closed = true; },
  };
  return {
    host, putCalls,
    setNextPut: (p) => { host._nextPut = p; },
    fireStatus: (s) => { for (const fn of statusFns) fn(s); },
    isClosed: () => closed,
    statusFnCount: () => statusFns.size,
  };
}

function radios(box) {
  return findAll(box, (c) => c.tagName === 'INPUT' && c.type === 'radio');
}

test('mounts two MD radios and the theme switch; radios stay disabled until getSettings answers', () => {
  const { host } = makeHost();
  host.getSettings = () => new Promise(() => {});   // never resolves in this test
  const box = new FakeEl('div');
  AS.mount(box, host);
  const rs = radios(box);
  assert.equal(rs.length, 2);
  assert.deepEqual(rs.map((r) => r.value).sort(), ['demo', 'live']);
  assert.ok(rs.every((r) => r.disabled), 'no current setting yet: nothing is pickable');
});

test('the current login is checked once getSettings resolves', async () => {
  const { host } = makeHost({ initial: { md: 'demo' } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();
  const rs = radios(box);
  const demo = rs.find((r) => r.value === 'demo'), live = rs.find((r) => r.value === 'live');
  assert.equal(demo.checked, true);
  assert.equal(live.checked, false);
  assert.ok(rs.every((r) => !r.disabled));
});

test('picking a login PUTs it, disables the radios while in flight, and reflects the result on success', async () => {
  const { host, putCalls, setNextPut } = makeHost({ initial: { md: 'demo' } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  let resolvePut;
  setNextPut(new Promise((res) => { resolvePut = res; }));
  const live = radios(box).find((r) => r.value === 'live');
  live.onchange();
  assert.deepEqual(putCalls, [{ md: 'live' }]);
  assert.ok(radios(box).every((r) => r.disabled), 'busy: a second pick must not fire a second PUT');

  resolvePut({ ok: true, settings: { md: 'live' } });
  await Promise.resolve(); await Promise.resolve();
  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'live').checked, true);
  assert.equal(rs.find((r) => r.value === 'demo').checked, false);
  assert.ok(rs.every((r) => !r.disabled));
});

test('a refused switch (09:20-09:35 / bot placing / failed re-login) shows inline and leaves the old login checked', async () => {
  const { host, setNextPut } = makeHost({ initial: { md: 'demo' } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  setNextPut(Promise.resolve({ ok: false, error: 'Not while the 9:30 bot is working — try after 09:35.' }));
  const live = radios(box).find((r) => r.value === 'live');
  live.onchange();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();

  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'demo').checked, true, 'the old (still active) login stays checked');
  assert.equal(rs.find((r) => r.value === 'live').checked, false);
  assert.ok(rs.every((r) => !r.disabled), 'a resolved PUT (even a refusal) must re-enable the radios');
  const err = descend(box, (c) => c.className.split(' ').includes('set-why'));
  assert.equal(err.hidden, false);
  assert.match(err.textContent, /09:35/);
});

test('a status update for a login switched elsewhere repaints the radios without a new GET', async () => {
  const { host, fireStatus } = makeHost({ initial: { md: 'demo' } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  fireStatus({ md: 'live' });
  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'live').checked, true);
  assert.equal(rs.find((r) => r.value === 'demo').checked, false);
});

test('the appearance switch calls host.toggleTheme and reflects host.isDark()', () => {
  const { host } = makeHost();
  const box = new FakeEl('div');
  AS.mount(box, host);
  const sw = descend(box, (c) => c.tagName === 'BUTTON' && c.className.split(' ').includes('switch'));
  assert.equal(sw.classList.contains('on'), false);
  sw.onclick();
  assert.equal(host.isDark(), true);
  assert.equal(sw.classList.contains('on'), true);
});

test('Close calls host.close(); stop() unsubscribes the status listener', async () => {
  const { host, isClosed, statusFnCount } = makeHost();
  const box = new FakeEl('div');
  const ctl = AS.mount(box, host);
  assert.equal(statusFnCount(), 1);
  const close = findByOwnText(box, 'button', 'Close');
  close.onclick();
  assert.equal(isClosed(), true);
  ctl.stop();
  assert.equal(statusFnCount(), 0);
});

test('a PUT that resolves after the dialog already closed is ignored (no repaint on a dead dialog)', async () => {
  const { host, setNextPut } = makeHost({ initial: { md: 'demo' } });
  const box = new FakeEl('div');
  const ctl = AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  let resolvePut;
  setNextPut(new Promise((res) => { resolvePut = res; }));
  radios(box).find((r) => r.value === 'live').onchange();
  ctl.stop();                          // the dialog closes while the PUT is still in flight
  resolvePut({ ok: true, settings: { md: 'live' } });
  await Promise.resolve(); await Promise.resolve();
  // radios stay exactly as they were left (disabled, mid-flight) -- no crash, no late repaint
  assert.ok(radios(box).every((r) => r.disabled));
});
