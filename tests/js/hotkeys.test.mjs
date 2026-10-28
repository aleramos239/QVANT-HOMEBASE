import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

/* Chart hotkeys (2026-10-28, owner D2): OFF and EMPTY until the owner records each key in Settings > Trading > Keys.
   The only trading keys are Flatten and Cancel-all for the focused chart's own symbol; they call the same function the
   FLAT button / right-click menu call, so the confirm and the LIVE arm are the same. Never a Buy or Sell key.
   The REAL trade.js / tradeui.js / replayui.js run under the same small shim tradeui.test.mjs uses. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const R = require('../../homebase/static/charts/replay.js');

const mem = {};
global.localStorage = { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = String(v); }, removeItem: (k) => { delete mem[k]; } };

const acct = (id, label, env) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [] });
const STATE = { enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [acct('sim041', 'SIM0000041', 'demo'), acct('live099', 'FAKELIVE099', 'live')], bot: { date: '2026-09-27', strategies: {} } };
class El {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.listeners = {}; this.className = ''; this.textContent = ''; }
  append(...n) { this.children.push(...n); }
  appendChild(n) { this.children.push(n); return n; }
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); }
  get classList() { return { add: () => {}, toggle: () => {}, contains: () => false }; }
  focus() {}
  blur() {}
}
const desk = {
  state: STATE, down: '', quotes: { NQ: { bid: 30000, ask: 30000.25, last: 30000.25, ts_ms: 0 } },
  prefs: { oneClick: true, oneClickChart: true, qty: 1, slTicks: 0, tpTicks: 0 },
  sent: [], toasts: [], subs: new Set(),
  mode(ct) { return T.tradeMode(desk, ct); }, gate() { return T.deskGate(desk); },
  toast(tone, text) { desk.toasts.push(text); },
  send(action, body) { desk.sent.push({ action, body }); return Promise.resolve(); },
  on(fn) { desk.subs.add(fn); return () => desk.subs.delete(fn); }, setPrefs(p) { Object.assign(desk.prefs, p); },
};
const dialogs = [];
let cells = [];
const page = {
  cells: () => cells, cur: () => cells[0], clockMs: () => 1000,
  mk: (tag, cls, text) => { const e = new El(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; },
  openDialog: (title) => { const box = new El('div'); dialogs.push({ title, box }); return box; },
  setDialogClose() {}, closeDialog() {}, deskUrl: () => 'http://127.0.0.1:8850/', dialogOpen: () => false,
};
const CM = require('../../homebase/static/charts/chartmenu.js');
global.window = { HBTrade: T, HBReplay: R, HBDeskClient: desk, HBIcons: {}, HBChartMenu: CM.builtins(CM.createRegistry()) };
global.document = { getElementById: () => null, createElement: (t) => new El(t), activeElement: null };
require('../../homebase/static/charts/tradeui.js');
require('../../homebase/static/charts/replayui.js');
const UI = global.window.HBTradeUI, RUI = global.window.HBReplayUI;
UI.mount(page);
/* app.js's onKey, line for line: the action the saved keys give this key, then the trading or the replay half */
const fire = (e, c) => {
  const hk = T.hotkeyAction(e, T.loadHotkeys());
  return !!(hk && c && (hk.startsWith('replay-') ? c.replay && RUI.hotkey(c, hk) : UI.hotkey(c, hk)));
};

const sentToHost = [];
function chart(accounts = ['sim041'], extra = {}) {
  const c = { cfg: { root: 'NQ', trade: { accounts }, algo: null, ...extra }, shown: { root: 'NQ' }, id: 'c1', tick: 0.25, pv: 20,
    replay: null, ov: [], bars: [], note() {}, host: { send: (m) => sentToHost.push(m) } };
  cells = [c];
  return c;
}
const flush = () => new Promise((r) => setImmediate(r));
function reset() {
  desk.sent.length = 0; desk.toasts.length = 0; dialogs.length = 0; sentToHost.length = 0; desk.prefs.oneClick = true; desk.prefs.oneClickChart = true;
  for (const k of Object.keys(mem)) delete mem[k];
}
const key = (code, mods = {}, extra = {}) => ({ code, key: code.replace(/^Key/, '').toLowerCase(), ctrlKey: false, altKey: false, metaKey: false,
  shiftKey: false, repeat: false, ...mods, ...extra });
const setKeys = (on, map) => localStorage.setItem(T.HOTKEYS_KEY, JSON.stringify({ on, map }));
const FLAT = key('KeyF', { ctrlKey: true, shiftKey: true });
const CANCEL = key('KeyX', { ctrlKey: true, shiftKey: true });

test('OFF by default: no key set, nothing on any key, the page and the order path are untouched', async () => {
  reset();
  assert.deepEqual(T.loadHotkeys(), { on: false, map: {} });
  const c = chart();
  for (const e of [FLAT, CANCEL, key('KeyF'), key('Space'), key('ArrowRight'), key('KeyB', { ctrlKey: true })]) {
    assert.equal(fire(e, c), false);
  }
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 0);
  assert.equal(desk.toasts.length, 0);
  assert.equal(sentToHost.length, 0);
});

test('switch off wins over a saved key; a key set but the master switch off sends nothing', async () => {
  reset();
  setKeys(false, { flatten: 'Ctrl+Shift+KeyF' });
  const c = chart();
  assert.equal(fire(FLAT, c), false);
  await flush();
  assert.equal(desk.sent.length, 0);
});

test('junk or hostile storage reads as OFF and empty', () => {
  for (const raw of ['', 'nope', '[]', '{"on":"yes"}', '{"on":true,"map":"x"}', 'null']) {
    localStorage.setItem(T.HOTKEYS_KEY, raw);
    const k = T.loadHotkeys();
    assert.equal(k.on === true && Object.keys(k.map).length > 0, false, raw);
  }
  setKeys(true, { buy: 'Ctrl+KeyB', sell: 'Ctrl+KeyS', flatten: 'KeyF', 'cancel-symbol': 'Ctrl+KeyZ' });
  assert.deepEqual(T.loadHotkeys(), { on: true, map: {} }, 'no Buy or Sell key, no bare letter, no reserved chord is ever kept');
});

test('there is no Buy or Sell action to bind', () => {
  assert.deepEqual(T.HOTKEY_ACTIONS.map((a) => a[0]).sort(),
    ['cancel-symbol', 'flatten', 'replay-back', 'replay-faster', 'replay-flatten', 'replay-slower']);
  for (const [id] of T.HOTKEY_ACTIONS) assert.doesNotMatch(id, /buy|sell|order|reverse/i);
});

test('chordOf: needs Ctrl, Alt or Cmd; a bare letter, Shift alone or a modifier key alone is no chord', () => {
  assert.equal(T.chordOf(key('KeyF', { ctrlKey: true, shiftKey: true })), 'Ctrl+Shift+KeyF');
  assert.equal(T.chordOf(key('Digit4', { metaKey: true })), 'Meta+Digit4');
  assert.equal(T.chordOf(key('KeyF')), null);
  assert.equal(T.chordOf(key('KeyF', { shiftKey: true })), null);
  assert.equal(T.chordOf(key('ControlLeft', { ctrlKey: true })), null);
  assert.equal(T.chordOf(key('ShiftLeft', { ctrlKey: true, shiftKey: true })), null);
});

test('hotkeyAssignError: reserved chords, a chord already used and a bare key are refused', () => {
  assert.match(T.hotkeyAssignError({}, 'flatten', null), /Ctrl|Alt|Cmd/);
  assert.match(T.hotkeyAssignError({}, 'flatten', 'Ctrl+KeyZ'), /already/i);       // undo
  assert.match(T.hotkeyAssignError({}, 'flatten', 'Meta+KeyC'), /already/i);       // copy
  assert.match(T.hotkeyAssignError({}, 'flatten', 'Alt+KeyR'), /already/i);        // reset view
  assert.match(T.hotkeyAssignError({}, 'flatten', 'Alt+KeyT'), /already/i);        // a drawing tool
  assert.match(T.hotkeyAssignError({ 'cancel-symbol': 'Ctrl+Shift+KeyF' }, 'flatten', 'Ctrl+Shift+KeyF'), /already/i);
  assert.equal(T.hotkeyAssignError({ flatten: 'Ctrl+Shift+KeyF' }, 'flatten', 'Ctrl+Shift+KeyF'), '');   // the same action again is fine
  assert.equal(T.hotkeyAssignError({}, 'flatten', 'Ctrl+Shift+KeyF'), '');
  assert.match(T.hotkeyAssignError({}, 'buy', 'Ctrl+Shift+KeyB'), /no such/i);
});

test('hotkeyAction: matches the exact chord only, never a held-down repeat, never mid-composition', () => {
  const keys = { on: true, map: { flatten: 'Ctrl+Shift+KeyF', 'cancel-symbol': 'Ctrl+Shift+KeyX' } };
  assert.equal(T.hotkeyAction(FLAT, keys), 'flatten');
  assert.equal(T.hotkeyAction(CANCEL, keys), 'cancel-symbol');
  assert.equal(T.hotkeyAction(key('KeyF', { ctrlKey: true }), keys), null);
  assert.equal(T.hotkeyAction({ ...FLAT, repeat: true }, keys), null);
  assert.equal(T.hotkeyAction({ ...FLAT, isComposing: true }, keys), null);
  assert.equal(T.hotkeyAction(FLAT, { on: false, map: keys.map }), null);
});

test('Flatten key: the same send as the FLAT button, one-click on', async () => {
  reset();
  const c = chart();
  UI.symbolAction(c, 'flatten', 'NQ');                  // what the FLAT button calls
  await flush();
  const button = desk.sent.splice(0);
  setKeys(true, { flatten: 'Ctrl+Shift+KeyF' });
  assert.equal(fire(FLAT, c), true);
  await flush();
  assert.equal(button.length, 1);
  assert.equal(desk.sent.length, 1);
  assert.equal(desk.sent[0].action, 'flatten');
  const strip = ({ client_id, ...rest }) => rest;
  assert.deepEqual(strip(desk.sent[0].body), strip(button[0].body));
  assert.deepEqual(desk.sent[0].body.accounts, ['sim041']);
  assert.equal(desk.sent[0].body.root, 'NQ');
});

test('Cancel-all key: the right-click menu\'s cancel-symbol for this chart\'s symbol', async () => {
  reset();
  const c = chart();
  setKeys(true, { 'cancel-symbol': 'Ctrl+Shift+KeyX' });
  assert.equal(fire(CANCEL, c), true);
  await flush();
  assert.equal(desk.sent.length, 1);
  assert.equal(desk.sent[0].action, 'cancel-symbol');
  assert.deepEqual(desk.sent[0].body.accounts, ['sim041']);
});

test('one-click OFF: the key opens the same confirm and sends nothing until it is accepted', async () => {
  reset();
  desk.prefs.oneClick = false; desk.prefs.oneClickChart = false;
  const c = chart();
  setKeys(true, { flatten: 'Ctrl+Shift+KeyF' });
  fire(FLAT, c);
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 1);
  const foot = dialogs[0].box.children.find((x) => x.className === 'dlg-foot');
  foot.children.find((b) => b.textContent === 'Flatten').onclick();
  await flush();
  assert.equal(desk.sent.length, 1);
});

test('a LIVE account that is not armed is refused exactly as for the button', async () => {
  reset();
  const c = chart(['live099']);
  setKeys(true, { flatten: 'Ctrl+Shift+KeyF' });
  fire(FLAT, c);
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(desk.toasts.length, 1);
});

test('a chart that is gone, a chart with no accounts, a symbol that changed: nothing sent', async () => {
  reset();
  setKeys(true, { flatten: 'Ctrl+Shift+KeyF' });
  const gone = chart(); cells = [];
  fire(FLAT, gone);
  const none = chart([]);
  fire(FLAT, none);
  const moved = chart(); moved.shown.root = 'ES'; moved.cfg.root = 'NQ';
  fire(FLAT, moved);
  assert.equal(fire(FLAT, null), false);
  await flush();
  assert.equal(desk.sent.length, 0);
});

test('the key acts on the chart it is given: another chart\'s accounts are never reached', async () => {
  reset();
  setKeys(true, { flatten: 'Ctrl+Shift+KeyF' });
  const a = chart(['sim041']);
  const b = { ...chart(['sim041']), shown: { root: 'ES' }, cfg: { root: 'ES', trade: { accounts: [] }, algo: null } };
  cells = [a, b];
  fire(FLAT, b);   // b has no accounts
  await flush();
  assert.equal(desk.sent.length, 0);
  fire(FLAT, a);
  await flush();
  assert.equal(desk.sent.length, 1);
  assert.equal(desk.sent[0].body.root, 'NQ');
});

test('a chart in replay: the trading keys are refused, nothing reaches the desk', async () => {
  reset();
  setKeys(true, { flatten: 'Ctrl+Shift+KeyF', 'cancel-symbol': 'Ctrl+Shift+KeyX' });
  const c = chart();
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 1, playing: true });
  fire(FLAT, c); fire(CANCEL, c);
  await flush();
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 0);
});

test('replay keys: only on a replaying chart, only replay controls, never the desk', async () => {
  reset();
  setKeys(true, { 'replay-faster': 'Alt+Shift+KeyU', 'replay-slower': 'Alt+Shift+KeyD', 'replay-flatten': 'Alt+Shift+KeyF' });
  const faster = key('KeyU', { altKey: true, shiftKey: true }), slower = key('KeyD', { altKey: true, shiftKey: true });
  const c = chart();
  assert.equal(fire(faster, c), false, 'a live chart: the replay key does nothing');
  assert.equal(sentToHost.length, 0);
  RUI.onState(c, { id: 'c1', date: '2026-09-24', cursor_ms: 0, speed: 5, playing: false });
  assert.equal(fire(faster, c), true);
  assert.equal(fire(slower, c), true);
  assert.deepEqual(sentToHost.map((m) => m.speed), [10, 2]);
  assert.equal(fire(key('KeyF', { altKey: true, shiftKey: true }), c), true);   // no practice position: a no-op
  assert.equal(desk.sent.length, 0);
  assert.equal(dialogs.length, 0);
});

test('app.js: the hotkey runs after the text-box and menu checks, and the pins moved with the files', () => {
  const rd = (p) => readFileSync(new URL(`../../homebase/static/${p}`, import.meta.url), 'utf8');
  const app = rd('charts/app.js');
  const textBox = app.indexOf("e.target.closest('input, textarea, select, [contenteditable=\"true\"]')");
  const call = app.indexOf("window.HBTradeUI?.hotkey(c, hk)");
  assert.ok(textBox > 0 && call > textBox, 'no key reaches the order path from a text box');
  assert.match(app.slice(call - 260, call), /hk && c && !menuEl && !hotkeyBox/);
  assert.match(app.slice(call - 400, call), /hk\.startsWith\('replay-'\) \? c\.replay && window\.HBReplayUI\?\.hotkey\(c, hk\)/);
});
