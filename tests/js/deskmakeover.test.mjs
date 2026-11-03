import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { HTML } from './deskpage.mjs';

/* Task 12: the sidebar sorts itself into Trading / Shadow / Off; a variant set is one row. */
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const CODE = between('function sideKind(', 'function renderSide(') +
  between('const sideFolded = ', 'function toggleSide(');

function load(st) {
  const ctx = vm.createContext({
    labSafe: (f, d) => { try { return f(); } catch (_) { return d; } }, labShadowNet: () => null,
    stratState: () => 'Ready', stratLabel: (n) => n.toUpperCase(), stratDotCls: (s) => s.cfg.enabled ? '' : 'off',
    todayPnl: () => null, readinessShown: (r) => r, SIDE_FOLD: {},
  });
  vm.runInContext(CODE + '\nglobalThis.api = { sideSections, sideFolded };', ctx);
  return ctx.api;
}
const S = (on, extra = {}) => ({ cfg: { enabled: on, kind: 'x' }, ...extra });
const ids = (rows) => [...rows].map((r) => r.id);

test('ON+booked, ON no account, OFF land in trading / shadow / off; A-Z by label', () => {
  const st = { strategies: { zeta: S(true), Alpha: S(true), shad: S(true), idle: S(false) }, book: { zeta: [{ account: 'a' }], Alpha: [{ account: 'a' }] } };
  const o = load(st).sideSections(Object.keys(st.strategies), st, [], []);
  assert.deepEqual(ids(o.trading), ['Alpha', 'zeta']);
  assert.deepEqual(ids(o.shadow), ['shad']);
  assert.deepEqual(ids(o.off), ['idle']);
});

test('a set is one row, its members none', () => {
  const st = { strategies: { lab_a_r1: S(true), lab_a_r2: S(false) }, book: { lab_a_r1: [{ account: 'a' }] } };
  const o = load(st).sideSections(Object.keys(st.strategies), st, [{ id: 'v1', name: 'A', members: ['lab_a_r1', 'lab_a_r2'] }], []);
  assert.deepEqual(ids(o.trading), ['v1']);
  assert.equal(o.trading[0].set, 'v1');
  assert.equal(o.shadow.length + o.off.length, 0);
});

test('a warn check marks the row; a live-but-OFF strategy stays in Trading', () => {
  const st = { strategies: { a: S(true), b: { ...S(false), day_status: 'live' } }, book: { a: [1], b: [1] }, readiness: { checks: [{ level: 'warn', strategy: 'a' }] } };
  const o = load(st).sideSections(['a', 'b'], st, [], []);
  assert.equal(o.trading.find((r) => r.id === 'a').warn, true);
  assert.equal(o.trading.find((r) => r.id === 'b').warn, false);
});

test('Off is folded with no stored fold; Teams empty says "None yet · add one"', () => {
  const { sideFolded } = load({});
  assert.equal(sideFolded('off'), true);
  assert.equal(sideFolded('trading'), false);
  assert.ok(HTML.includes('None yet · add one'));
});

/* Task 13: Needs a look is the one readiness list; the shield and the toolbar word go to it. */
const LOOK = between('const LOOK_FIX', 'function renderNeedsLook(') + 'function chkKey(c) { return c.label + "|" + c.detail; }';
function looks() {
  const ctx = vm.createContext({ esc: (v) => String(v).replace(/</g, '&lt;'), jsArg: (v) => JSON.stringify(String(v == null ? '' : v)) });
  vm.runInContext(LOOK + '\nglobalThis.api = { lookRows, needsLookHtml, LOOK_FIX, LOOK_STALE };', ctx);
  return ctx.api;
}
const CHECKS = [
  { level: 'ok', label: 'Feed', detail: 'flowing' }, { level: 'info', label: 'Power', detail: 'on power' },
  { level: 'warn', label: 'nq_orb', detail: 'no account', strategy: 'nq_orb', fix: 'turn_on' },
  { level: 'bad', label: 'Acct 1', detail: 'offline', account: 'a1', fix: 'reconnect' }];

test('lookRows keeps the warn and bad checks, "label: detail", with their fix', () => {
  const rows = [...looks().lookRows(CHECKS, false)];
  assert.deepEqual(rows.map((r) => [r.text, r.fix, r.strategy, r.account]),
    [['nq_orb: no account', 'turn_on', 'nq_orb', undefined], ['Acct 1: offline', 'reconnect', undefined, 'a1']]);
});
test('nothing to look at says Ready; a stale state never does', () => {
  const k = looks();
  assert.deepEqual([...k.lookRows([], false)], []);
  assert.match(k.needsLookHtml([]), /Ready: nothing needs a look/);
  const stale = [...k.lookRows(CHECKS.slice(0, 2), true)];
  assert.equal(stale.length, 1);
  assert.equal(stale[0].text, 'The Desk is not answering: this is the last known state.');
  assert.doesNotMatch(k.needsLookHtml(stale), /Ready: nothing/);
  assert.match(k.needsLookHtml([...k.lookRows(CHECKS, false)]), /Needs a look · 2/);
});
test('fix buttons carry the five words; Turn on opens a page, it switches nothing', () => {
  assert.deepEqual({ ...looks().LOOK_FIX }, { reconnect: 'Reconnect', open: 'Open', turn_on: 'Turn on', limits: 'Set limits', team: 'Open team' });
  const fn = between('function lookFix(', 'function openChecks(');
  assert.doesNotMatch(fn, /toggleStrat|setDeskLab|post\(/, 'no click on this list switches anything ON');
});
test('the shield goes to Today and the list; the old strip, banner and System checks dialog are gone', () => {
  assert.match(between('function openChecks(', '/* ---- dismissing a notice'), /setView\("today"\)[\s\S]*scrollIntoView/);
  for (const gone of ['id="readyStrip"', 'id="checksOverlay"', 'function dismissReady(', 'function renderChecks(']) assert.ok(!HTML.includes(gone), gone);
  assert.ok(HTML.includes('id="needsLook"'));
});
test('a Today row\'s switch: a Desk strategy goes through toggleStrat, a Lab one with no account through setDeskLab', () => {
  assert.match(between('function todayRow(', 'let ISSUE_LVL'), /toggleStrat\('\$\{name\}'/);
  assert.doesNotMatch(between('function todayRow(', 'let ISSUE_LVL'), /setDeskLab/);
  assert.match(between('function todayLabRow(', 'function labView('), /setDeskLab/);
});
