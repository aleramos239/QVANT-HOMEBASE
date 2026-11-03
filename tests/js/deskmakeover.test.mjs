import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { HTML } from './deskpage.mjs';

/* Task 12: the sidebar sorts itself into Trading / Shadow / Off; a variant set is one row. */
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const CODE = between('function sideKind(', 'function renderSide(') + between('function setDayPnl(', 'let COMBINE = null;') +
  between('const sideFolded = ', 'function toggleSide(');

function load(st) {
  const ctx = vm.createContext({
    labSafe: (f, d) => { try { return f(); } catch (_) { return d; } }, labShadowNet: () => null,
    stratState: () => 'Ready', stratLabel: (n) => n.toUpperCase(), stratDotCls: (s) => s.cfg.enabled ? '' : 'off',
    todayPnl: () => null, readinessShown: (r) => r, SIDE_FOLD: {},
  });
  vm.runInContext(CODE + '\nglobalThis.api = { sideSections, sideFolded, setDayPnl };', ctx);
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

/* Task 15: the strategy page's status line -- its state in words, or red with every reason. */
const SL = between('function setDayPnl(', 'let COMBINE = null;') + between('function sideKind(', '/* A strategy page') + between('const STATUS_STALE', 'function statusLineHtml(') +
  'const fmt = (v) => String(v);\n' + HTML.slice(HTML.indexOf('const usdS = '), HTML.indexOf('\n', HTML.indexOf('const plural = '))) + '\n';
function sl(net = {}) {
  const ctx = vm.createContext({ labSafe: (f, d) => { try { return f(); } catch (_) { return d; } },
    labShadowNet: (id) => net[id] == null ? null : { net: net[id] }, todayPnl: (s) => s.pnl ?? null });
  vm.runInContext(SL + '\nglobalThis.api = { statusLine };', ctx);
  return ctx.api.statusLine;
}
const ST15 = { strategies: { t: { cfg: { enabled: true }, pnl: 412 }, sh: { cfg: { enabled: true } }, off: { cfg: { enabled: false } } },
  book: { t: [{ account: 'a1' }, { account: 'a2' }] } };
const DESK_OFF = { label: 'Desk', detail: 'OFF.', level: 'bad', fix: 'turn_on' };
const fixOf = (r) => ({ text: r.text, fix: r.fix });

test('statusLine: a ready trading strategy says its accounts and today, exact', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(sl()('t', [{ label: 'x', detail: 'fine', level: 'ok', strategy: 't' }], ST15, false))),
    { level: 'ok', text: 'Ready · trades on 2 accounts · today +$412', reasons: [] });
  assert.equal(sl({ sh: 80 })('sh', [], ST15, false).text, 'Shadow · no account · would be +$80 today');
  assert.deepEqual(JSON.parse(JSON.stringify(sl()('off', [], ST15, false))), { level: 'off', text: 'OFF', reasons: [] });
});

test('statusLine: an offline booked account is bad with a Reconnect reason', () => {
  const L = sl()('t', [{ label: 'pp', detail: '..a1 is offline.', level: 'bad', strategy: 't', account: 'a1', fix: 'reconnect' }], ST15, false);
  assert.equal(L.level, 'bad');
  assert.deepEqual(JSON.parse(JSON.stringify(L.reasons.map(fixOf))), [{ text: 'pp: ..a1 is offline.', fix: 'reconnect' }]);
  assert.equal(L.reasons[0].account, 'a1', 'Reconnect knows which account');
});

test('statusLine: the Desk OFF line is on every strategy; another strategy\'s or an account-only check is not', () => {
  const checks = [DESK_OFF, { label: 'pp', detail: 'x', level: 'bad', strategy: 'sh' }, { label: 'acct', detail: 'y', level: 'bad', account: 'a9' },
    { label: 'Power', detail: 'z', level: 'info' }];
  for (const id of ['t', 'sh', 'off']) {
    const L = sl()(id, checks, ST15, false);
    assert.equal(L.level, 'bad', id);
    assert.ok(L.reasons.some((r) => r.text === 'Desk: OFF.'), id);
    assert.ok(!L.reasons.some((r) => r.text.startsWith('acct') || r.text.startsWith('Power')), id);
  }
  assert.equal(sl()('t', checks, ST15, false).reasons.length, 1, 'the sh check stays on sh');
});

test('statusLine: a warn limits line turns it red with Set limits; an info evening line keeps shadow and is listed', () => {
  const w = sl()('t', [{ label: 'Limits', detail: 'none set.', level: 'warn', strategy: 't', fix: 'limits' }], ST15, false);
  assert.equal(w.level, 'warn');
  assert.equal(w.reasons[0].fix, 'limits');
  const i = sl()('sh', [{ label: 'Window', detail: 'runs in the evening.', level: 'info', strategy: 'sh' }], ST15, false);
  assert.equal(i.level, 'shadow');
  assert.deepEqual([...i.reasons].map((r) => r.text), ['Window: runs in the evening.']);
});

test('statusLine: stale is stale, never ok, and says so', () => {
  const L = sl()('t', [], ST15, true);
  assert.equal(L.level, 'stale');
  assert.equal(L.text, 'The Desk is not answering: last known state.');
});

/* Task 16: variant sets. A set's money is its accounts' P&L, never the variants' shadow dollars; Combine is blocked while two members share an account. */
test('setDayPnl is the members\' ACCOUNT P&L only, each account once; shadow dollars never count', () => {
  const { setDayPnl } = load({});
  const accounts = { a1: { day_pnl: 100 }, a2: { day_pnl: -30 }, a3: { day_pnl: 999 } };
  const book = { m1: [{ account: 'a1' }, { account: 'a2' }], m2: [{ account: 'a1' }], other: [{ account: 'a3' }] };
  assert.equal(setDayPnl({ members: ['m1', 'm2'] }, accounts, book), 70);
  assert.equal(setDayPnl({ members: ['m1', 'm2'], shadow: 5000 }, {}, book), null);
  assert.equal(setDayPnl({ members: ['m1'] }, { a1: { day_pnl: null } }, { m1: [{ account: 'a1' }] }), null);
});

test('the sidebar row of a set shows the accounts\' P&L, not the sum of its members\' shadow', () => {
  const st = { strategies: { lab_a_r1: S(true), lab_a_r2: S(true) }, accounts: { x: { day_pnl: 40 } }, book: { lab_a_r1: [{ account: 'x' }] } };
  const o = load(st).sideSections(Object.keys(st.strategies), st, [{ id: 'v1', name: 'A', members: ['lab_a_r1', 'lab_a_r2'] }], []);
  assert.equal(o.trading[0].pnl, 40);
});

test('Combine is blocked while two members share an account, naming it; free otherwise', () => {
  const ctx = vm.createContext({});
  vm.runInContext(between('function combineBlock(', 'let COMBINE = null;') + '\nglobalThis.combineBlock = combineBlock;', ctx);
  const labels = { m1: '1R', m2: '2R' };
  assert.equal(ctx.combineBlock(['m1', 'm2'], labels, { m1: [{ account: 'a1' }], m2: [{ account: 'a1' }] }), '..a1 has both 1R and 2R: untick one first.');
  assert.equal(ctx.combineBlock(['m1', 'm2'], labels, { m1: [{ account: 'a1' }], m2: [{ account: 'a2' }] }), '');
});

test('statusLine of a set: Trading when any member trades, red for a bad check on any member, money from accounts', () => {
  const st = { strategies: { m1: { cfg: { enabled: false } }, m2: { cfg: { enabled: true } } }, book: { m2: [{ account: 'a1' }] }, accounts: { a1: { day_pnl: 55 } } };
  const f = sl({ m1: 9999, m2: 9999 });
  assert.equal(f(['m1', 'm2'], [], st, false).text, 'Ready · trades on 1 account · today +$55');
  const L = f(['m1', 'm2'], [{ label: 'pp', detail: 'bad thing', level: 'bad', strategy: 'm2' }, { label: 'q', detail: 'other', level: 'bad', strategy: 'zz' }], st, false);
  assert.equal(L.level, 'bad');
  assert.deepEqual(JSON.parse(JSON.stringify(L.reasons.map((r) => r.text))), ['m2 · pp: bad thing']);
  assert.equal(f(['m1', 'm2'], [], { ...st, book: {} }, false).text, 'Shadow · no account · would be +$9,999 today'.replace('9,999', '9999'));
});

test('statusLine: with the Desk OFF a booked strategy is Not ready, saying the Desk is OFF; shadow and OFF are as they were', () => {
  const st = { ...ST15, armed: false };
  assert.deepEqual(JSON.parse(JSON.stringify(sl()('t', [], st, false))), { level: 'warn', text: 'Not ready · trades on 2 accounts · today +$412',
    reasons: [{ text: 'Desk is OFF: signals are written down only.', fix: '', account: '' }] });
  assert.deepEqual(JSON.parse(JSON.stringify(sl({ sh: 80 })('sh', [], st, false))), { level: 'shadow', text: 'Shadow · no account · would be +$80 today', reasons: [] });
  assert.deepEqual(JSON.parse(JSON.stringify(sl()('off', [], st, false))), { level: 'off', text: 'OFF', reasons: [] });
  assert.equal(sl()('t', [], { ...ST15, armed: true }, false).text, 'Ready · trades on 2 accounts · today +$412');
});
