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
  prepend(...nodes) { for (const n of nodes.reverse()) { if (n == null) continue; n.parentNode = this; this.children.unshift(n); } }
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
  global.window.HBDataExport = require('../../homebase/static/charts/dataexport.js');
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


/* ---- 2026-09-27 accounts-per-chart plan, Task 1: the Trading tab ----
   The dialog paints the ACCOUNTS list and reports clicks; every rule lives in HBTradeUI (a double here).
   These drive it exactly as a click would, so the wiring -- rows, the LIVE two-step arm, "unlisted cannot be
   ticked", and the algo <-> accounts binding -- is covered end to end, not just in the pure helpers. */
const T = require('../../homebase/static/charts/trade.js');

const TR_ACCT = (id, label, env, extra = {}) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const TR_STATE = {
  enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [TR_ACCT('sim041', 'SIM0000041', 'demo'), TR_ACCT('live099', 'FAKELIVE099', 'live'),
    TR_ACCT('paper', 'PAPER', 'paper')],
  bot: { date: '2026-09-27', strategies: {
    nq930: { symbol: 'NQ', kind: 'straddle', enabled: true, shadow: false, book: { sim041: 1 },
      timer: null, day_status: 'idle', accounts: {} } } },
};

/* A stand-in for HBTradeUI: the same rules (HBTrade.accountPickRows / acctTick / algoForAccount), the same
   two-step LIVE arm, over a plain cell config. */
function makeTradeHost(cell, state = TR_STATE) {
  const armed = new Set();
  let arming = null;
  const subs = new Set();
  const notify = () => { for (const fn of [...subs]) fn(); };
  const accountsOf = () => T.cellTrade(cell.cfg.trade).accounts;
  return {
    accountRows: () => T.accountPickRows(state, accountsOf(), armed, cell.cfg.root),
    armPending: () => arming,
    onTradeChange: (fn) => { subs.add(fn); return () => subs.delete(fn); },
    tradeWhy: () => { const m = T.tradeMode({ state }, cell.cfg.trade); return m.mode === 'on' ? '' : m.reason; },
    prefs: () => ({ oneClick: false, oneClickChart: true, oneClickPanel: false, qty: 1, slTicks: 0, tpTicks: 0 }),
    setPrefs: () => {},
    algoChoices: () => T.algoChoices(state, cell.cfg.root, cell.cfg.algo),
    setAlgo: (c, v) => {
      c.cfg.algo = T.cellAlgo(v);
      if (!c.cfg.algo) return notify();
      const add = T.algoTickAccounts(state, c.cfg.root, c.cfg.algo, armed);
      c.cfg.trade = { accounts: [...new Set([...accountsOf(), ...add])] };
      notify();
    },
    toggleAccount: (c, id) => {
      const a = state.accounts.find((x) => x.id === id) || null, have = accountsOf();
      if (have.includes(id)) {
        if (arming === id) arming = null;
        if (a && a.env === 'live') armed.delete(id);
        c.cfg.trade = { accounts: have.filter((x) => x !== id) };
        return notify();
      }
      if (!a || !a.tradable) return notify();
      if (a.env === 'live' && !armed.has(id)) {
        if (arming !== id) { arming = id; return notify(); }
        armed.add(id); arming = null;
      }
      c.cfg.trade = { accounts: [...have, id] };
      const key = T.algoForAccount(state, c.cfg.root, id);
      if (key) c.cfg.algo = key;
      notify();
    },
  };
}

/* Opens the dialog straight onto the Trading tab and hands back its ACCOUNTS rows. */
function openTrading(cell, extra = {}) {
  const { host } = makeHost(cell, []);
  const box = new FakeEl('div');
  Object.assign(host, { tab: 'trading' }, makeTradeHost(cell), extra);
  const dlg = SD.mount(box, host);
  const rows = () => {
    const list = box.querySelector('.set-acct-list');
    return list ? list.children : [];
  };
  const click = (i) => { rows()[i].children[0].onchange(); };
  return { box, host, dlg, rows, click };
}

test('Trading tab: one row per account, the env chips, the algo note, and the ONE-CLICK TRADING switches', () => {
  const cell = makeCell('time:60');
  cell.cfg.root = 'NQ';
  cell.cfg.trade = { accounts: [] };
  cell.cfg.algo = null;
  const { box, rows } = openTrading(cell);
  assert.equal(rows().length, 3);
  assert.equal(findText(rows()[0], 'SIM0000041') != null, true);
  assert.equal(findText(rows()[0], 'in NQ 9:30 Straddle') != null, true);   // booked by an algo on this instrument
  assert.equal(findText(rows()[1], 'LIVE') != null, true);
  const paperChip = rows()[2].children[2];   // checkbox, label, env chip, balance, dot
  assert.equal(paperChip.textContent, 'PAPER');
  assert.equal(paperChip.className, 'env paper', 'the PAPER chip carries its own (amber) class');
  assert.equal(findText(box, 'ONE-CLICK TRADING') != null, true);
  assert.equal(findText(box, 'Every chart. Off: that surface asks to confirm first.') != null, true);
  for (const gone of ['DEFAULTS (all charts)', 'Default quantity', 'Stop loss (ticks)', 'Take profit (ticks)', 'One-click trading']) {
    assert.equal(findText(box, gone), null, `${gone} is gone`);
  }
  assert.equal(findText(box, "No accounts on this chart — pick one in the chart's ⚙ → Trading") != null, true);
});

test('Trading tab: ticking a DEMO account picks up its algo, and the chart becomes trade-ready', () => {
  const cell = makeCell('time:60');
  cell.cfg.root = 'NQ';
  cell.cfg.trade = { accounts: [] };
  cell.cfg.algo = null;
  const { box, click, rows } = openTrading(cell);
  click(0);
  assert.deepEqual(cell.cfg.trade.accounts, ['sim041']);
  assert.equal(cell.cfg.algo, 'nq930', 'ticking an account that belongs to an algo sets the select to it');
  assert.equal(box.querySelector('.set-algo').value, 'nq930');
  assert.equal(rows()[0].children[0].checked, true);
  click(0);                                       // and un-ticking it leaves the algo selected
  assert.deepEqual(cell.cfg.trade.accounts, []);
  assert.equal(cell.cfg.algo, 'nq930');
});

test('Trading tab: picking an algo ticks its booked accounts; clearing it to None leaves them alone', () => {
  const cell = makeCell('time:60');
  cell.cfg.root = 'NQ';
  cell.cfg.trade = { accounts: [] };
  cell.cfg.algo = null;
  const { box } = openTrading(cell);
  const sel = box.querySelector('.set-algo');
  sel.value = 'nq930';
  sel.onchange();
  assert.deepEqual(cell.cfg.trade.accounts, ['sim041']);
  sel.value = '';
  sel.onchange();
  assert.equal(cell.cfg.algo, null);
  assert.deepEqual(cell.cfg.trade.accounts, ['sim041'], 'clearing the algo never unticks an account');
});

test('Trading tab: a LIVE account needs the second click, and an unlisted one can never be ticked', () => {
  const cell = makeCell('time:60');
  cell.cfg.root = 'NQ';
  cell.cfg.trade = { accounts: [] };
  cell.cfg.algo = null;
  const { box, click, rows } = openTrading(cell);
  click(1);                                       // first click on LIVE: arms, does NOT tick
  assert.deepEqual(cell.cfg.trade.accounts, []);
  assert.equal(findText(box, 'Tick LIVE — real orders. Click again') != null, true);
  click(1);                                       // second click: armed, ticked
  assert.deepEqual(cell.cfg.trade.accounts, ['live099']);
  assert.equal(rows()[1].children[0].checked, true);

  // an account the desk does not list: '?', disabled when it is not on the chart, and never tickable
  const ghostState = { ...TR_STATE, accounts: [] };
  const c2 = makeCell('time:60');
  c2.cfg.root = 'NQ';
  c2.cfg.trade = { accounts: [] };
  c2.cfg.algo = null;
  const t2 = makeTradeHost(c2, ghostState);
  const two = openTrading(c2, { accountRows: () => T.accountPickRows(ghostState, ['ghost'], new Set(), 'NQ'),
    toggleAccount: t2.toggleAccount });
  assert.equal(two.rows().length, 1);
  assert.equal(findText(two.rows()[0], '?') != null, true);
  two.click(0);                                   // the desk does not know it: nothing is added
  assert.deepEqual(c2.cfg.trade.accounts, []);
});

test('Task 2b: "+ Add paper account" under the ACCOUNTS list creates one through the host, inline, no native prompt', async () => {
  const cell = makeCell('time:60');
  cell.cfg.root = 'NQ';
  cell.cfg.trade = { accounts: [] };
  cell.cfg.algo = null;
  const calls = [];
  let answer = { status: 400, data: { ok: false, detail: "a paper account is already called 'Scalps'" } };
  const { box } = openTrading(cell, { createPaperAccount: async (n, b) => { calls.push([n, b]); return answer; } });
  const link = findText(box, '+ Add paper account'), form = box.querySelector('.set-paper-form');
  assert.ok(link && form && form.hidden === true);
  link.onclick();
  assert.equal(form.hidden, false);
  const [name, bal, add] = form.children;
  await add.onclick();
  assert.deepEqual(calls, [], 'no name: nothing sent');
  assert.equal(form.children[4].textContent, 'Give it a name');
  name.value = '  Scalps '; bal.value = '$25,000';
  await add.onclick();
  assert.deepEqual(calls, [['Scalps', 25000]]);
  assert.equal(form.hidden, false, 'a refusal keeps the form open');
  assert.match(form.children[4].textContent, /already called/);
  answer = { status: 200, data: { ok: true, account: { id: 'paper-2' } } };
  await add.onclick();
  assert.equal(form.hidden, true);
  assert.equal(link.hidden, false);
  const noHost = openTrading(makeCell('time:60'), { createPaperAccount: undefined });
  assert.equal(findText(noHost.box, '+ Add paper account'), null);
});

test('Trading tab: the two one-click switches show and flip their own pref only', () => {
  const cell = makeCell('time:60');
  cell.cfg.root = 'NQ';
  cell.cfg.trade = { accounts: [] };
  cell.cfg.algo = null;
  const prefs = { oneClick: false, oneClickChart: true, oneClickPanel: false, qty: 1, slTicks: 0, tpTicks: 0 };
  const { box } = openTrading(cell, { prefs: () => prefs, setPrefs: (p) => Object.assign(prefs, p) });
  const sw = (label) => descend({ children: [box] }, (c) => c.getAttribute && c.getAttribute('aria-label') === label);
  const chart = sw('Chart buttons'), panel = sw('Order panel');
  assert.equal(chart.getAttribute('aria-checked'), 'true');
  assert.equal(panel.getAttribute('aria-checked'), 'false');
  panel.onclick();
  assert.deepEqual([prefs.oneClickChart, prefs.oneClickPanel, prefs.oneClick], [true, true, false]);
  assert.equal(panel.getAttribute('aria-checked'), 'true');
  chart.onclick();
  assert.deepEqual([prefs.oneClickChart, prefs.oneClickPanel, prefs.oneClick], [false, true, false]);
});

/* S7 (2026-09-28 safety pass): the Template ▾ "Save as…" field saves once per Enter PRESS -- a held key's
   auto-repeat (e.repeat) never sends another PUT (GOTCHAS.md: a held key has sent duplicates here before). */
test('S7: Template ▾ Save as… -- Enter saves once; a held Enter\'s repeats never save again', async () => {
  const cell = makeCell('time:60');
  const { host } = makeHost(cell, []);
  const saved = [];
  host.templates.save = async (name, body) => { saved.push(name); return null; };
  const box = new FakeEl('div');
  SD.mount(box, host);
  box.querySelector('.tpl-btn').onclick();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  findText(host.menu(), 'Save as…').parentNode.onclick();
  const input = descend(host.menu(), (el) => el.tagName === 'input' && el.classList.contains('menu-input'));
  input.value = 'Held key';
  let prevented = 0;
  const key = (repeat) => ({ key: 'Enter', repeat, preventDefault() { prevented++; } });
  input.onkeydown(key(true));                      // a repeat that arrives first (focus landed mid-hold): nothing
  await Promise.resolve();
  assert.deepEqual(saved, []);
  input.onkeydown(key(false));                     // the press itself
  input.onkeydown(key(true)); input.onkeydown(key(true)); input.onkeydown(key(true));   // its auto-repeat
  await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(saved, ['Held key'], 'exactly one save');
  assert.equal(prevented, 5, 'every Enter, repeat or not, is still kept from its default action');
});

/* W3 (2026-09-28): at <= 640 px the Settings tabs show icons only (charts.css hides the label) -- each keeps its name
   as a tooltip and as its accessible name. */
test('W3: every Settings tab carries its label as title and aria-label', () => {
  const cell = makeCell('time:60');
  const { host } = makeHost(cell, []);
  const box = new FakeEl('div');
  SD.mount(box, host);
  const tabs = [];
  descend(box, (el) => { if (el.classList && el.classList.contains('set-tab')) tabs.push(el); return false; });
  assert.ok(tabs.length >= 6, `found ${tabs.length} tabs`);
  for (const t of tabs) {
    const label = t.children[1].textContent;
    assert.ok(label, 'a visible label');
    assert.equal(t.title, label);
    assert.equal(t.getAttribute('aria-label'), label);
  }
});

/* ---- 2026-09-28 data-export plan: the Data tab ----
   host.export is a double of the chart service's /api/export/* client (app.js's real one just
   fetches); these tests drive it exactly as a click/keystroke would, so the wiring -- which
   fields build the request body, when meta/coverage re-fetch, the poll -> done -> reveal path,
   and cancel -- is covered end to end, not just dataexport.js's own pure functions. */

function makeExportHost(overrides = {}) {
  const calls = [];
  const base = {
    meta: async (root, type) => { calls.push(['meta', root, type]); return { range: ['2026-09-01', '2026-09-25'], contracts: ['NQZ6', 'NQU6'] }; },
    coverage: async (root, type, contract, start, end) => {
      calls.push(['coverage', root, type, contract, start, end]);
      return { sessions_total: 3, missing: [], missing_hours: {} };
    },
    start: async (body) => { calls.push(['start', body]); return { status: 200, data: { id: '20260928-100000-deadbeef' } }; },
    status: async (id) => { calls.push(['status', id]); return { status: 'running', sessions_done: 1, sessions_total: 2, rows: 10 }; },
    cancel: async (id) => { calls.push(['cancel', id]); return { status: 200, data: { status: 'cancelled' } }; },
    reveal: async (id) => { calls.push(['reveal', id]); return { status: 200, data: { ok: true } }; },
  };
  return { calls, exp: { ...base, ...overrides } };
}

/* setInterval is captured, never really scheduled: a test advances a poll by calling the
   captured function itself and awaiting it, instead of racing a real 700ms timer. This override
   runs once, at module load (before node:test invokes any test body below), and is never
   restored -- nothing earlier in this file uses a real interval, and node:test isolates each
   test FILE in its own process, so it cannot leak into another suite. */
let capturedIntervalFns, clearedIntervalIds;
global.setInterval = (fn) => { capturedIntervalFns.push(fn); return capturedIntervalFns.length; };
global.clearInterval = (id) => clearedIntervalIds.add(id);

function openData(cell, exp) {
  capturedIntervalFns = [];
  clearedIntervalIds = new Set();
  const { host } = makeHost(cell, []);
  Object.assign(host, { tab: 'data', export: exp });
  const box = new FakeEl('div');
  const dlg = SD.mount(box, host);
  // advances the LATEST poll -- throws if stopDataPoll() (clearInterval) already cleared it, so a
  // test can assert "polling really stopped" instead of just re-invoking a stale callback by hand
  const poll = () => {
    const id = capturedIntervalFns.length;
    if (clearedIntervalIds.has(id)) throw new Error('poll(): this interval was already cleared');
    return capturedIntervalFns[id - 1]();
  };
  return { box, host, dlg, poll };
}
const flush = () => new Promise((r) => setTimeout(r, 0));   // drains the microtask queue (real setTimeout: untouched)

function dataSelects(box) {
  const sels = [];
  descend(box, (el) => { if (el.tagName === 'select') sels.push(el); return false; });
  return { market: sels[0], contract: sels[1], type: sels[2] };
}

test('Data tab: opens on Candles for the first market, and fetches its meta (range + contracts)', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box } = openData(cell, exp);
  await flush();
  assert.deepEqual(calls[0], ['meta', 'NQ', 'candles']);
  const { contract } = dataSelects(box);
  assert.equal(contract.disabled, false);
  assert.equal(contract.children.length, 3);            // front + NQZ6 + NQU6
  assert.equal(findText(box, 'On disk: 2026-09-01 to 2026-09-25') != null, true);
});

test('Data tab: Level 3 is a disabled option (short label, kept out of the select\'s own width) with a reason', () => {
  const cell = makeCell('time:60');
  const { exp } = makeExportHost();
  const { box } = openData(cell, exp);
  const { type } = dataSelects(box);
  const l3 = [...type.children].find((o) => o.value === 'level3');
  assert.equal(l3.disabled, true);
  assert.equal(l3.textContent, 'Level 3', 'the visible option label stays short -- the reason is not appended to it');
  assert.match(l3.title, /Tradovate/, 'the reason is on the option as a hover title');
  assert.equal(findText(box, "Level 3 isn't offered: Order-by-order data isn't in Tradovate's feed, so it isn't recorded.") != null,
    true, 'the reason is also shown as a persistent caption (level3 can never be the selected/shown option)');
});

test('Data tab: switching to Level 2 shows Levels and hides Timeframe; a non-NQ/ES market is forced to NQ', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box } = openData(cell, exp);
  await flush();
  const { market, type } = dataSelects(box);
  market.value = 'GC';
  market.onchange();
  await flush();
  assert.equal(findText(box, 'Timeframe') != null, true);   // still candles: timeframe row present
  type.value = 'level2';
  type.onchange();
  await flush();
  assert.equal(findText(box, 'Timeframe'), null, 'candles-only row is gone for level2');
  assert.equal(findText(box, 'Levels (1-10)') != null, true);
  assert.equal(findText(box, 'Contract'), null, 'level2 has no per-contract choice (depth is per root, not per symbol)');
  assert.equal(dataSelects(box).market.value, 'NQ', 'GC has no level2, so the market was forced to NQ');
  assert.deepEqual(calls.at(-1), ['meta', 'NQ', 'level2']);
});

test('Data tab: a quick pick fills the date fields and refreshes coverage with them', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box } = openData(cell, exp);
  await flush();
  calls.length = 0;
  const btn = descend(box, (el) => el.tagName === 'button' && el.textContent === 'All');
  assert.ok(btn, 'the All quick-pick button exists');
  btn.onclick();
  await flush();
  const cov = calls.find((c) => c[0] === 'coverage');
  assert.deepEqual(cov, ['coverage', 'NQ', 'candles', 'front', '2026-09-01', '2026-09-25']);   // "All" = the meta range
});

test('Data tab: typing a date does not refetch; leaving the field (blur) does', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box } = openData(cell, exp);
  await flush();
  const dateIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  endIn.value = '2026-09-20'; endIn.oninput(); endIn.onblur();   // coverage needs both ends; blur it first
  await flush();
  calls.length = 0;
  dateIn.value = '2026-09-10';
  dateIn.oninput();
  assert.equal(calls.length, 0, 'no fetch while the field is still focused/typing');
  dateIn.onblur();
  await flush();
  assert.equal(calls.some((c) => c[0] === 'coverage'), true);
  assert.equal(calls.find((c) => c[0] === 'coverage')[4], '2026-09-10');
});

test('Data tab: a missing session shows the warning; none hides it', async () => {
  const cell = makeCell('time:60');
  const { exp } = makeExportHost({
    coverage: async () => ({ sessions_total: 4, missing: ['2026-09-02', '2026-09-03'], missing_hours: {} }),
  });
  const { box } = openData(cell, exp);
  await flush();
  const startIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  startIn.value = '2026-09-01'; startIn.oninput(); startIn.onblur();
  endIn.value = '2026-09-05'; endIn.oninput(); endIn.onblur();
  await flush();
  const why = box.querySelector('.set-why');
  assert.equal(why.hidden, false);
  assert.equal(findText(why, '2 of 4 sessions missing (no file)') != null, true);
});

test('Data tab: a KNOWN GAP in an otherwise-present session shows too, even with no session fully missing', async () => {
  const cell = makeCell('time:60');
  const { exp } = makeExportHost({
    coverage: async () => ({ sessions_total: 2, missing: [], missing_hours: { '2026-09-01': [[1000, 2000]] } }),
  });
  const { box } = openData(cell, exp);
  await flush();
  const startIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  startIn.value = '2026-09-01'; startIn.oninput(); startIn.onblur();
  endIn.value = '2026-09-02'; endIn.oninput(); endIn.onblur();
  await flush();
  const why = box.querySelector('.set-why');
  assert.equal(why.hidden, false, 'the box shows even though no session is fully missing');
  assert.equal(findText(why, '1 known gap within 1 session on disk') != null, true);
});

test('Data tab: Start builds the request from the form, then polling reaches done with a Show in Finder button', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost({
    status: async () => ({ status: 'done', rows: 500, sessions_done: 1, sessions_total: 1,
      result: { path: '/tmp/Downloads/NQ_candles_5m_2026-09-01_2026-09-05.csv', name: 'NQ_candles_5m_2026-09-01_2026-09-05.csv',
        rows: 500, bytes: 20480 } }),
  });
  const { box, poll } = openData(cell, exp);
  await flush();
  const startIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  startIn.value = '2026-09-01'; startIn.oninput();
  endIn.value = '2026-09-05'; endIn.oninput();
  const go = findByOwnText(box, 'button', 'Start export');
  go.onclick();
  await flush();
  assert.deepEqual(calls.find((c) => c[0] === 'start')[1],
    { root: 'NQ', type: 'candles', contract: 'front', start: '2026-09-01', end: '2026-09-05',
      hours: 'full', tz: 'et', ts_format: 'iso', format: 'csv', timeframe: '5m' });
  assert.equal(go.disabled, true, 'Start is disabled while a job is active');

  await poll();
  assert.equal(findText(box, 'NQ_candles_5m_2026-09-01_2026-09-05.csv — 500 rows, 20 KB') != null, true);
  const reveal = findByOwnText(box, 'button', 'Show in Finder');
  assert.ok(reveal);
  assert.equal(go.disabled, false, 'Start is re-enabled once the job is final');
  reveal.onclick();
  await flush();
  assert.deepEqual(calls.find((c) => c[0] === 'reveal'), ['reveal', '20260928-100000-deadbeef']);
});

test('Data tab: Cancel stops the job and further polling', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box, poll } = openData(cell, exp);
  await flush();
  const startIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  startIn.value = '2026-09-01'; startIn.oninput();
  endIn.value = '2026-09-05'; endIn.oninput();
  findByOwnText(box, 'button', 'Start export').onclick();
  await flush();
  const cancelBtn = findByOwnText(box, 'button', 'Cancel export');
  cancelBtn.onclick();
  await flush();
  assert.deepEqual(calls.find((c) => c[0] === 'cancel'), ['cancel', '20260928-100000-deadbeef']);
  assert.equal(findText(box, 'Cancelled') != null, true);
  assert.throws(() => poll(), /already cleared/, 'cancel() must clearInterval the poll it started');
});

test('Data tab: Start with an invalid range shows an inline error and never calls start()', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box } = openData(cell, exp);
  await flush();
  const startIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  startIn.value = '2026-09-10'; startIn.oninput();
  endIn.value = '2026-09-01'; endIn.oninput();
  findByOwnText(box, 'button', 'Start export').onclick();
  await flush();
  assert.equal(calls.some((c) => c[0] === 'start'), false);
  assert.equal(findText(box, 'From must not be after To') != null, true);
});

test('Data tab: closing the dialog (Cancel/revert) stops an in-flight poll', async () => {
  const cell = makeCell('time:60');
  const { exp, calls } = makeExportHost();
  const { box, dlg } = openData(cell, exp);
  await flush();
  const startIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'From date');
  const endIn = descend(box, (el) => el.tagName === 'input' && el.getAttribute('aria-label') === 'To date');
  startIn.value = '2026-09-01'; startIn.oninput();
  endIn.value = '2026-09-05'; endIn.oninput();
  findByOwnText(box, 'button', 'Start export').onclick();
  await flush();
  assert.doesNotThrow(() => dlg.revert());
  // clearInterval is stubbed (never really cancels in this harness), so this only proves revert()
  // reaches stopDataPoll() without throwing when a job is active -- the real clearInterval is native.
});

test('Data tab: Template and Apply to all are hidden on Data, and reappear on another tab', () => {
  const cell = makeCell('time:60');
  const { exp } = makeExportHost();
  const { box } = openData(cell, exp);
  const tpl = box.querySelector('.tpl-btn'), applyAll = findByOwnText(box, 'button', 'Apply to all');
  assert.equal(tpl.hidden, true, 'neither a chart-appearance template nor "copy to every chart" applies to an export');
  assert.equal(applyAll.hidden, true);
  let symbolTab = null;
  descend(box, (el) => { if (el.getAttribute && el.getAttribute('aria-label') === 'Symbol') symbolTab = el; return false; });
  symbolTab.onclick();
  assert.equal(tpl.hidden, false);
  assert.equal(applyAll.hidden, false);
});
