import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

/* settings-dialog.js (and icons.js) are the page's DOM-mounting half: unlike the pure model
   (settings.js, catalog.js), they read/write `window` directly at load time and have no
   `module.exports` fallback, so they only ever ran inside a browser check before this test. A
   small hand-written DOM/window shim -- just the handful of element APIs the dialog actually
   calls (append, classList, querySelector, replaceChildren/replaceWith/remove, focus) -- lets it
   load and run for real under `node --test`, so the Settings Cancel/Ok regression (fix wave item
   2) is caught by the suite instead of only by a browser check. */

class FakeEl {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.style = {};
    this._class = '';
    this._text = '';
    this.isConnected = true;   // the dialog checks this after an await; the shim never truly detaches
  }
  set className(v) { this._class = v || ''; }
  get className() { return this._class; }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...nodes) { for (const n of nodes) { if (n == null) continue; n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { for (const c of this.children) c.parentNode = null; this.children = []; this.append(...nodes); }
  replaceWith(node) {
    if (!this.parentNode) return;
    const i = this.parentNode.children.indexOf(this);
    if (i >= 0) { this.parentNode.children[i] = node; node.parentNode = this.parentNode; }
    this.parentNode = null;
  }
  remove() {
    if (this.parentNode) { const i = this.parentNode.children.indexOf(this); if (i >= 0) this.parentNode.children.splice(i, 1); }
    this.parentNode = null;
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener() {}
  removeEventListener() {}
  focus() { ACTIVE.el = this; }
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
  contains(other) { for (let n = other; n; n = n.parentNode) if (n === this) return true; return false; }
  querySelector(sel) {
    for (const one of sel.split(',').map((s) => s.trim())) {
      const wanted = one.replace(/^\./, '').split('.');
      const hit = descend(this, (el) => el.classList && wanted.every((w) => el.classList.contains(w)));
      if (hit) return hit;
    }
    return null;
  }
}
function descend(el, pred) {
  for (const c of el.children) { if (pred(c)) return c; const r = descend(c, pred); if (r) return r; }
  return null;
}
/* An element whose OWN textContent (not a descendant's) is exactly `text` -- Ok/Cancel/Apply-to-all
   set theirs directly (mk(tag, cls, text)), with no nested span. */
function findByOwnText(el, tag, text) {
  return descend({ children: [el] }, (c) => c.tagName === tag && c.textContent === text);
}
/* An element (any tag) whose own textContent is exactly `text` -- a template row's name lives in a
   nested <span>, so this is used instead of findByOwnText to locate it. */
function findText(el, text) {
  return descend({ children: [el] }, (c) => c.textContent === text);
}

const ACTIVE = { el: null };

function loadDialog() {
  global.window = global.window || {};   // a dedicated object, not an alias for `global` itself
  global.window.HBSettings = require('../../homebase/static/charts/settings.js');
  delete require.cache[require.resolve('../../homebase/static/charts/icons.js')];
  require('../../homebase/static/charts/icons.js');
  global.document = { createElement: (tag) => new FakeEl(tag), get activeElement() { return ACTIVE.el; } };
  global.requestAnimationFrame = (fn) => { fn(); return 1; };
  global.cancelAnimationFrame = () => {};
  delete require.cache[require.resolve('../../homebase/static/charts/settings-dialog.js')];
  require('../../homebase/static/charts/settings-dialog.js');
  return global.window.HBSettingsDialog;
}
const SD = loadDialog();

/* A minimal HBCell double: settings()/cfg mirror the real cell closely enough for the dialog's
   snapshot/compare/patch logic (it never reaches into Lightweight Charts). */
function makeCell(spec) {
  const state = { settings: {}, cfg: { indicators: [], spec } };
  return {
    cfg: state.cfg,
    settings: () => state.settings,
    setSettings: (o) => { state.settings = o; },
    update: (patch) => { Object.assign(state.cfg, patch); },
  };
}

function makeHost(cell, others) {
  let lastMenu = null;
  const commits = [];
  let dlgRef;
  const host = {
    cell,
    cells: () => [cell, ...others],
    toggleMenu: (anchor, cls, fill) => { lastMenu = new FakeEl('div'); fill(lastMenu); },
    closeMenu: () => {},
    placeMenu: () => {},
    commit: (changed) => commits.push(changed),
    cancel: () => dlgRef.revert(),
    templates: {
      list: () => Promise.resolve({ 'Wide 5m': { settings: {}, spec: 'time:300' } }),
      save: async () => null,
      remove: async () => null,
    },
    countries: () => [],
    menu: () => lastMenu,
  };
  return { host, commits, setDlg: (d) => { dlgRef = d; } };
}

/* Drives the Template menu exactly as a click would: opens it, waits for the (async) template
   list to load, and clicks the saved template's row -- the same path a user takes to apply a
   template with a stored interval onto the selected chart. */
async function applySavedTemplate(box, host, name) {
  box.querySelector('.tpl-btn').onclick();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();   // let host.templates.list() resolve
  const nameSpan = findText(host.menu(), name);
  nameSpan.parentNode.onclick();   // the row's "pick" button
}

test('Settings Cancel after applying a template with an interval restores the original spec (and settings)', async () => {
  const cell = makeCell('time:60');
  const other = makeCell('time:120');
  const { host, setDlg } = makeHost(cell, [other]);
  const box = new FakeEl('div');
  const dlg = SD.mount(box, host);
  setDlg(dlg);

  await applySavedTemplate(box, host, 'Wide 5m');
  assert.equal(cell.cfg.spec, 'time:300');            // the template's interval previewed on the selected chart
  assert.equal(other.cfg.spec, 'time:120');           // template Apply (not "Apply to all") touches only this chart

  host.cancel();                                       // Cancel / × / Esc / backdrop all route through host.cancel()
  assert.equal(cell.cfg.spec, 'time:60', 'Cancel must restore the interval a template changed');
  assert.deepEqual(cell.settings(), {});               // and the settings the template touched
  assert.equal(other.cfg.spec, 'time:120');            // untouched throughout
});

test('Ok after a template-changed interval marks the layout Unsaved (the changed check counts spec)', async () => {
  const cell = makeCell('time:60');
  const { host, commits } = makeHost(cell, []);
  const box = new FakeEl('div');
  SD.mount(box, host);

  await applySavedTemplate(box, host, 'Wide 5m');
  assert.equal(cell.cfg.spec, 'time:300');

  const ok = findByOwnText(box, 'button', 'Ok');
  ok.onclick();
  assert.deepEqual(commits, [true], 'a spec-only change must still report changed=true to host.commit');
});

test('Ok with no changes at all (settings, indicators or spec) reports changed=false', () => {
  const cell = makeCell('time:60');
  const { host, commits } = makeHost(cell, []);
  const box = new FakeEl('div');
  SD.mount(box, host);

  const ok = findByOwnText(box, 'button', 'Ok');
  ok.onclick();
  assert.deepEqual(commits, [false]);
});
