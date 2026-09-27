import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

/* appsettings.js (Task 4, 2026-09-27 accounts-paper-layouts-appsettings plan; MARKET DATA
   reworked in Fix round 1) is a DOM-mounting module like settings-dialog.js: it reads/writes
   `window` at load time and has no `module.exports` fallback. Same small hand-written DOM/window
   shim as settings-dialog.test.mjs (just the element APIs this dialog actually calls), so it
   loads and runs for real under `node --test` instead of only ever running inside a browser
   check. */

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
function hasClass(c, cls) { return c.className && c.className.split(' ').includes(cls); }

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
   flight. */
function makeHost({ initial = { md: 'demo', accounts: { live: null, demo: null } } } = {}) {
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
function apply(box) {
  return findAll(box, (c) => c.tagName === 'BUTTON' && hasClass(c, 'btn-primary'))[0];
}
function warnRow(box) {
  return findAll(box, (c) => hasClass(c, 'set-why'))
    .find((c) => /blank/.test(c.textContent));
}
function errRow(box) {
  return findAll(box, (c) => hasClass(c, 'set-why'))
    .find((c) => !/blank/.test(c.textContent));
}

test('mounts two MD radios, the warning line and Apply; radios and Apply stay disabled until getSettings answers', () => {
  const { host } = makeHost();
  host.getSettings = () => new Promise(() => {});   // never resolves in this test
  const box = new FakeEl('div');
  AS.mount(box, host);
  const rs = radios(box);
  assert.equal(rs.length, 2);
  assert.deepEqual(rs.map((r) => r.value).sort(), ['demo', 'live']);
  assert.ok(rs.every((r) => r.disabled), 'no current setting yet: nothing is pickable');
  assert.ok(apply(box).disabled);
  assert.match(warnRow(box).textContent, /blank/);
});

test('the current login is checked and Apply is disabled once getSettings resolves (nothing staged yet)', async () => {
  const { host } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();
  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'demo').checked, true);
  assert.equal(rs.find((r) => r.value === 'live').checked, false);
  assert.ok(rs.every((r) => !r.disabled));
  assert.ok(apply(box).disabled, 'staged === current: nothing to apply yet');
});

test('picking a radio only STAGES it -- no PUT, Apply becomes enabled', async () => {
  const { host, putCalls } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  const live = radios(box).find((r) => r.value === 'live');
  live.onchange();
  assert.deepEqual(putCalls, [], 'a radio pick alone must never PUT');
  assert.equal(live.checked, true);
  assert.equal(radios(box).find((r) => r.value === 'demo').checked, false);
  assert.ok(!apply(box).disabled, 'a staged change makes Apply available');
});

test('re-picking the login already active disables Apply again', async () => {
  const { host } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  radios(box).find((r) => r.value === 'live').onchange();
  assert.ok(!apply(box).disabled);
  radios(box).find((r) => r.value === 'demo').onchange();
  assert.ok(apply(box).disabled, 'staged is back to the active login: nothing to apply');
});

test('Apply PUTs the staged login, disables Apply/radios and shows a busy label while in flight', async () => {
  const { host, putCalls, setNextPut } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  let resolvePut;
  setNextPut(new Promise((res) => { resolvePut = res; }));
  radios(box).find((r) => r.value === 'live').onchange();
  apply(box).onclick();
  assert.deepEqual(putCalls, [{ md: 'live' }]);
  assert.ok(apply(box).disabled, 'busy: a second click must not fire a second PUT');
  assert.equal(apply(box).textContent, 'Applying…');
  assert.ok(radios(box).every((r) => r.disabled), 'radios are also disabled while a switch is in flight');

  resolvePut({ ok: true, settings: { md: 'live', accounts: { live: null, demo: null } } });
  await Promise.resolve(); await Promise.resolve();
  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'live').checked, true);
  assert.equal(rs.find((r) => r.value === 'demo').checked, false);
  assert.ok(rs.every((r) => !r.disabled));
  assert.equal(apply(box).textContent, 'Apply');
  assert.ok(apply(box).disabled, 'now on "live": staged === current again');
});

test('a held Enter/Space (repeated clicks while busy) never fires a second PUT', async () => {
  const { host, putCalls, setNextPut } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  setNextPut(new Promise(() => {}));   // never resolves in this test
  radios(box).find((r) => r.value === 'live').onchange();
  apply(box).onclick();
  apply(box).onclick();   // a second "click" (e.g. keyboard auto-repeat) while busy
  apply(box).onclick();
  assert.equal(putCalls.length, 1);
});

test('a refused switch (09:20-09:35 / bot working / failed re-login) shows inline and snaps the radio back', async () => {
  const { host, setNextPut } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  setNextPut(Promise.resolve({ ok: false, error: 'Not while the 9:30 bot is working — try after 09:35.' }));
  radios(box).find((r) => r.value === 'live').onchange();
  apply(box).onclick();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();

  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'demo').checked, true, 'the old (still active) login snaps back');
  assert.equal(rs.find((r) => r.value === 'live').checked, false);
  assert.ok(rs.every((r) => !r.disabled), 'a resolved PUT (even a refusal) must re-enable the radios');
  assert.ok(apply(box).disabled, 'staged snapped back to current: nothing left to apply');
  const err = errRow(box);
  assert.equal(err.hidden, false);
  assert.match(err.textContent, /09:35/);
});

test('a status update for a login switched elsewhere repaints the radios without a new GET, but only while idle', async () => {
  const { host, fireStatus } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  fireStatus({ md: 'live' });
  const rs = radios(box);
  assert.equal(rs.find((r) => r.value === 'live').checked, true);
  assert.equal(rs.find((r) => r.value === 'demo').checked, false);
  assert.ok(apply(box).disabled);
});

test('a status tick that arrives WHILE this dialog is applying its own switch does not clobber it', async () => {
  const { host, setNextPut, fireStatus } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  let resolvePut;
  setNextPut(new Promise((res) => { resolvePut = res; }));
  radios(box).find((r) => r.value === 'live').onchange();
  apply(box).onclick();
  fireStatus({ md: 'demo' });   // a stale status tick from before the switch landed
  assert.ok(radios(box).every((r) => r.disabled), 'still busy: the stale tick must not re-enable anything');

  resolvePut({ ok: true, settings: { md: 'live', accounts: { live: null, demo: null } } });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(radios(box).find((r) => r.value === 'live').checked, true);
});

test('the account label from GET /api/settings shows next to each login', async () => {
  const { host } = makeHost({ initial: { md: 'demo', accounts: { live: '···885', demo: null } } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();
  const liveRow = findAll(box, (c) => hasClass(c, 'set-name'))
    .find((c) => c.children.some((k) => k.textContent === 'Live'));
  assert.ok(liveRow.children.some((k) => k.textContent === '(···885)'));
});

test('the appearance switch calls host.toggleTheme and reflects host.isDark()', () => {
  const { host } = makeHost();
  const box = new FakeEl('div');
  AS.mount(box, host);
  const sw = descend(box, (c) => c.tagName === 'BUTTON' && hasClass(c, 'switch'));
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
  const { host, setNextPut } = makeHost({ initial: { md: 'demo', accounts: { live: null, demo: null } } });
  const box = new FakeEl('div');
  const ctl = AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();

  let resolvePut;
  setNextPut(new Promise((res) => { resolvePut = res; }));
  radios(box).find((r) => r.value === 'live').onchange();
  apply(box).onclick();
  ctl.stop();                          // the dialog closes while the PUT is still in flight
  resolvePut({ ok: true, settings: { md: 'live', accounts: { live: null, demo: null } } });
  await Promise.resolve(); await Promise.resolve();
  // radios stay exactly as they were left (disabled, mid-flight) -- no crash, no late repaint
  assert.ok(radios(box).every((r) => r.disabled));
});

/* Fix round 2, re-review M-f: what /api/status says about the feed shows in the dialog too. */
function stateRow(box) {
  return findAll(box, (c) => hasClass(c, 'set-why')).filter((c) => !/blank/.test(c.textContent))[1];
}

test('a failed switch recorded in status (another tab, before this dialog opened) shows on open', async () => {
  const { host } = makeHost();
  host.status = () => ({ md: 'demo', switch_error: { to: 'live', error: 'no valid live md token on disk', at: 1 } });
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();
  const row = stateRow(box);
  assert.equal(row.hidden, false);
  assert.match(row.textContent, /last switch to Live failed: no valid live md token/);
});

test('a status tick carrying md_mismatch shows it, and a clean tick clears it', async () => {
  const { host, fireStatus } = makeHost();
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();
  fireStatus({ md: 'demo', md_mismatch: 'set to the demo login, but it has no valid md token: charts come from live' });
  assert.match(stateRow(box).textContent, /charts come from live/);
  fireStatus({ md: 'demo', md_mismatch: null, switch_error: null });
  assert.equal(stateRow(box).hidden, true);
});

test("this dialog's own failed Apply is not repeated by the status line", async () => {
  const { host, setNextPut, fireStatus } = makeHost();
  const box = new FakeEl('div');
  AS.mount(box, host);
  await Promise.resolve(); await Promise.resolve();
  setNextPut(Promise.resolve({ ok: false, error: 'no live token' }));
  radios(box).find((r) => r.value === 'live').onchange();
  await apply(box).onclick();
  fireStatus({ md: 'demo', switch_error: { to: 'live', error: 'no live token', at: 1 } });
  assert.match(errRow(box).textContent, /no live token/);
  assert.equal(stateRow(box).hidden, true);
});
