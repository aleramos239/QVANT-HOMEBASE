import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

/* Step B, task B6: a promoted Lab strategy that the Desk itself knows (desk id lab_<name>, kind "lab", a `lab` block in
   /api/status) -- the page's wiring, run for real in a vm sandbox (the deskbook / deskswitches technique) with the real
   desklab.js. The pure words are tested in desklab.test.mjs; here: one row never two, what each control sends, what each
   answer says, and that a repaint never touches the Limits dialog. */
const require = createRequire(import.meta.url);
const AV = require('../../homebase/static/algo-visibility.js');
const D = require('../../homebase/static/desklab.js');
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const SKIN = readFileSync(new URL('../../homebase/static/apple/desk.js', import.meta.url), 'utf8');
const SLICE = (a, b) => {
  const i = HTML.indexOf(a), j = HTML.indexOf(b, i + 1);
  assert.ok(i >= 0 && j > i, `${a} .. ${b}`);
  return HTML.slice(i, j);
};
const plain = (v) => JSON.parse(JSON.stringify(v));

const LIM = { max_trades_day: 2, max_qty: 1, max_risk_usd: 300, last_entry_et: '11:00', flat_et: '15:55' };
const MARK = ['abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789', '2026-10-09T18:03:00+00:00'];
const lab = (over = {}) => ({ name: 'nq_orb', mark: MARK, limits: LIM, state: 'waiting', why: null, trades_today: 0, mode_today: null,
  runner: { alive: true, age_s: 1 }, rounds: [], refused: [], read_only: false, ...over });
const deskStrat = (labOver = {}, cfgOver = {}) => ({ cfg: { symbol: 'NQ', qty: 1, label: 'NQ ORB', enabled: true, kind: 'lab', shadow: false, flat_et: '15:55', ...cfgOver },
  day_status: 'idle', killed: false, accounts: [], research: {}, live: null, lab: lab(labOver) });
const nq930 = () => ({ cfg: { symbol: 'NQ', qty: 3, label: 'nq930', enabled: true, kind: 'straddle', shadow: false, offset_pts: 5, sl_pts: 5, tp_pts: 15, flat_et: '15:55', cancel_et: '12:55', self_fire: true },
  day_status: 'idle', accounts: [], research: {}, live: null });
const ROW = (over = {}) => ({ name: 'nq_orb', label: 'NQ ORB', root: 'NQ', session_window: ['09:25', '16:00'], bar_minutes: 1, qty: 1, enabled: true,
  sha256: 'abcdef0123456789', promoted_utc: '2026-10-09T18:03:00+00:00', today: null, days: [],
  run: { id: 'r1', net: 5000, trades: 41, win_rate: 48.8, profit_factor: 1.31, max_drawdown: -2100 }, notes: [], ...over });
const ACCOUNTS = { a1: { label: 'Lucid Eval #1', env: 'demo', connected: true }, a2: { label: 'APEX2941870000048', env: 'live', connected: true } };

/* The whole Desk-views part of the page (sidebar, rows, strategy page, the Lab part) with a fake document around it. */
function load({ strategies = { nq930: nq930(), lab_nq_orb: deskStrat() }, book = {}, rows = [ROW()], view = { k: 'today' }, accounts = ACCOUNTS,
  answer = { ok: true }, confirm = true, readOk = true, demo = false } = {}) {
  const els = {}, posts = [], toasts = [], confirms = [], alerts = [], shown = [], hidden = [], refreshes = [];
  const el = (id) => (els[id] = els[id] || { id, innerHTML: '', textContent: '', value: '', hidden: false, disabled: false, attrs: {},
    setAttribute(k, v) { this.attrs[k] = String(v); }, classList: { contains: () => false } });
  const ctx = vm.createContext({
    console, DOUBLE_CLICK_MS: 400, DEMO: demo, CHART: 'http://x', DESK_STALE: false, window: { AlgoVisibility: AV },
    location: { hash: '', protocol: 'http:', hostname: 'x' }, history: { replaceState() {} }, document: { hidden: false, getElementById: () => null, querySelectorAll: () => [], addEventListener() {}, activeElement: null },
    $: (sel) => el(sel.replace(/^#/, '')), DeskLab: D,
    ST: { armed: true, et_now: '2026-10-10T10:00:00-0400', timer: { strategies: {} }, accounts: plain(accounts), book: plain(book), journal: [], strategies: plain(strategies) },
    toast: (t) => toasts.push(t), alertBar: (t) => alerts.push(t),
    confirmDlg: async (title, body, action, destructive) => { confirms.push(plain({ title, body, action, destructive })); return confirm; },
    post: async (url, body) => {
      posts.push(plain({ url, body }));
      if (answer instanceof Error) throw answer;
      return plain(typeof answer === 'function' ? answer(url, body) : answer);
    },
    showOverlay: (id) => shown.push(id), hideOverlay: (id) => hidden.push(id), closeAsgMenus() {},
    switchBounced: () => false, render() {}, loadDeskLab() {}, refresh: async () => { refreshes.push(1); },
    fetch: async () => ({ ok: false }), setView() {},
  });
  const code = SLICE('const esc = (v) =>', 'async function chartPost(') + SLICE('const stratLabel = ', 'const actStrat = ') + SLICE('const fmt = ', 'const usd = ') +
    'const usd = (v) => v == null ? "—" : (v < 0 ? "-$" : "$") + fmt(Math.abs(v));\n' +
    SLICE('const killText = ', 'function killFailures(') + SLICE('const actErr = ', 'const actFail = ') + SLICE('const STEP_OK = ', 'const REFUSED_WHY') +
    SLICE('const SWITCH_AT = {};', 'function cfDone(') +
    'function needsConfirm(kind, turningOn, opts) { return window.AlgoVisibility.switchNeedsConfirm(kind, turningOn, opts); }\n' +
    SLICE('/* ===== Desk views', 'function render() {') +
    SLICE('/* ---- account row (rendered inside strategy cards) ---- */', '/* ---- connect wizard ---- */') +
    SLICE('/* ---- strategy on/off + flatten ----', '/* ---- accounts popup ---- */') +
    `\nDESKLAB = { strategies: ${JSON.stringify(rows)}, runner: { alive: true } }; DESKLAB_OK = ${readOk};` +
    `\nVIEW = ${JSON.stringify(view)};` +
    '\nglobalThis.api = { renderSide, renderMain, labDeskView, stratView, stratState, stratDotCls, todayRow, specOf, setBook, pickAsg, liveBookingNote, toggleStrat,' +
    ' flattenStrat, openLabLimits, closeLabLimits, saveLabLimits, removeLabStrat, clearLabBlock, labRowsHtml, labOnDesk, todayLabRow, get LAB_LIM() { return LAB_LIM; }, get VIEW() { return VIEW; } };';
  vm.runInContext(code, ctx);
  return { ctx, api: ctx.api, els, el, posts, toasts, confirms, alerts, shown, hidden, refreshes,
    side: () => { ctx.api.renderSide(['nq930', 'lab_nq_orb'].filter((n) => ctx.ST.strategies[n]), 0, 0); return els.side.innerHTML; },
    view: (name = 'lab_nq_orb') => ctx.api.labDeskView(name, ctx.ST.strategies[name]) };
}

// ---- ONE ROW, NEVER TWO ------------------------------------------------------------------------------------------------
test('one row, never two: the chart service\'s row is skipped once the Desk knows lab_<name>', () => {
  const known = load();
  const s1 = known.side();
  assert.equal((s1.match(/setView\('strat',&quot;lab_nq_orb&quot;\)|setView\('strat','lab_nq_orb'\)/g) || []).length, 1, 'the Desk\'s own row');
  assert.equal((s1.match(/setView\('lab'/g) || []).length, 0, 'not the Step A row');
  known.ctx.api.renderMain(['nq930', 'lab_nq_orb'], 0);
  const list = known.els.stratList.innerHTML;
  assert.equal((list.match(/class="srow"/g) || []).length, 2, 'nq930 and the Lab strategy: one Today row each');
  assert.equal((list.match(/setView\('strat','lab_nq_orb'\)/g) || []).length, 2, 'one row (its click and its key)');
  assert.equal((list.match(/setView\('lab'/g) || []).length, 0);
});

test('one row, never two: until the Desk knows it, the Step A row draws it; the moment the Desk knows it, that row goes', () => {
  const t = load({ strategies: { nq930: nq930() } });
  assert.equal((t.side().match(/setView\('lab',&quot;nq_orb&quot;\)/g) || []).length, 1, 'Step A row while the Desk does not know it');
  t.ctx.api.renderMain(['nq930'], 0);
  assert.equal((t.els.stratList.innerHTML.match(/class="srow"/g) || []).length, 2, 'nq930 and the Step A row');
  assert.equal((t.els.stratList.innerHTML.match(/setView\('lab',&quot;nq_orb&quot;\)/g) || []).length, 2, 'the Step A row (its click and its key)');
  // the Desk starts to know it (the next status): both lists change in one repaint
  t.ctx.ST.strategies.lab_nq_orb = plain(deskStrat());
  const after = t.side();
  assert.equal((after.match(/setView\('lab'/g) || []).length, 0, 'the Step A row is gone');
  assert.equal((after.match(/lab_nq_orb/g) || []).length >= 1, true);
  t.ctx.api.renderMain(['nq930', 'lab_nq_orb'], 0);
  assert.equal((t.els.stratList.innerHTML.match(/setView\('lab'/g) || []).length, 0);
  assert.equal((t.els.stratList.innerHTML.match(/class="srow"/g) || []).length, 2, 'nq930 and the Desk\'s own row: still two rows in all');
  // and the chart service answering with nothing changes nothing on the Desk's own row
  const none = load({ rows: [] });
  assert.match(none.side(), /lab_nq_orb/);
});

test('the Strategies count in a folded sidebar does not count the same strategy twice', () => {
  const side = SLICE('function renderSide(', '/* ---- strategy detail ---- */');
  assert.match(side, /DESKLAB\.strategies\.filter\(w => !labOnDesk\(w\)\)\.length/);
});

test('the Desk\'s own page is shown for a #lab=<name> link or a Lab view once the Desk knows the strategy', () => {
  assert.match(HTML, /if \(VIEW\.k === "lab" && labSafe\(\(\) => DeskLab\.onDesk\(s\.strategies, \{name: VIEW\.name\}\), false\)\) VIEW = \{k: "strat", name: "lab_" \+ VIEW\.name\};/);
  // it sits before the check that sends an unknown strategy back to Today
  assert.ok(HTML.indexOf('VIEW = {k: "strat", name: "lab_" + VIEW.name}') < HTML.indexOf('if (VIEW.k === "strat" && !names.includes(VIEW.name)) VIEW = {k: "today"};'));
});

// ---- the row and the dot ---------------------------------------------------------------------------------------------
test('the Desk\'s row for a Lab strategy: the state word, the dot, the spec line and the Shadow tag', () => {
  const t = load();
  const { api } = t, s = t.ctx.ST.strategies.lab_nq_orb;
  assert.equal(api.stratState('lab_nq_orb', s), 'Waiting for the session');
  assert.equal(api.stratDotCls(s, ''), '');
  assert.equal(api.specOf(s.cfg, 'lab_nq_orb'), 'NQ · 09:25-16:00 ET · from the Lab');
  const row = api.todayRow('lab_nq_orb', s);
  assert.match(row, /<span class="tag" title="It writes down its orders\. Nothing is sent\.">Shadow<\/span>/, 'no account booked: the Shadow tag');
  assert.match(row, /toggleStrat\('lab_nq_orb', false\)/);
  const booked = load({ book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] } });
  assert.doesNotMatch(booked.api.todayRow('lab_nq_orb', booked.ctx.ST.strategies.lab_nq_orb), />Shadow</, 'an account booked: no tag');
  const gone = load({ rows: [] });
  assert.equal(gone.api.specOf(gone.ctx.ST.strategies.lab_nq_orb.cfg, 'lab_nq_orb'), 'NQ · from the Lab', 'the chart service not answering: the session is left out');
  // the Desk's own strategies are untouched
  assert.equal(api.stratState('nq930', t.ctx.ST.strategies.nq930), 'Watching');
  assert.equal(api.specOf(t.ctx.ST.strategies.nq930.cfg, 'nq930'), 'NQ · ±5 off · SL 5 / TP 15');
  assert.doesNotMatch(api.todayRow('nq930', t.ctx.ST.strategies.nq930), /Shadow/);
});

test('a Lab strategy\'s state is the server\'s word, whatever the Desk\'s own timers say', () => {
  for (const [state, why, word, dot] of [['working', null, 'Order working', 'live'], ['in_position', null, 'In position', 'live'], ['check', null, 'Check it', 'warn'],
    ['runner_down', null, 'Runner down', 'warn'], ['disarmed', null, 'Disarmed: written down only', 'warn'], ['stopped', 'off', 'Starts with the next session.', ''],
    ['stopped', 'Could not pick up where it left off.', 'Stopped: Could not pick up where it left off.', 'warn']]) {
    const t = load({ strategies: { lab_nq_orb: deskStrat({ state, why }) } });
    const s = t.ctx.ST.strategies.lab_nq_orb;
    assert.equal(t.api.stratState('lab_nq_orb', s), word, state);
    assert.equal(t.api.stratDotCls(s, word), dot, state);
  }
});

// ---- the strategy page ------------------------------------------------------------------------------------------------
test('the page: state, note, Limits, Today, Matched the backtest, Accounts, and the three actions -- no Test fire', () => {
  const t = load();
  const html = t.view();
  assert.match(html, /<b>Waiting for the session<\/b>/);
  assert.match(html, /From the Lab\. With no account it runs in shadow: it writes down its orders and nothing is sent\./);
  assert.match(html, /<h2>Limits<\/h2>/);
  for (const k of ['Trades a day', 'Most contracts per account', 'Most at risk per trade', 'No new trade after', 'Flat by']) assert.match(html, new RegExp(`<span class="h">${k}</span>`), k);
  assert.match(html, /<span class="t net">\$300<\/span>/);
  assert.match(html, /onclick="openLabLimits\(&quot;lab_nq_orb&quot;\)">Edit limits<\/button>/);
  assert.match(html, /<h2>Today, in shadow<\/h2>/);
  assert.match(html, /<h2>Matched the backtest<\/h2>/);
  assert.match(html, /<h2>Accounts<\/h2>/);
  assert.match(html, /flattenStrat\(&quot;lab_nq_orb&quot;\)" title="Flattens its positions and switches it off">Flatten &amp; turn off</);
  assert.match(html, /openDeskLabInLab\(&quot;nq_orb&quot;\)[^>]*>Open in the Lab</);
  assert.match(html, /removeLabStrat\(&quot;lab_nq_orb&quot;\)"[^>]*>Remove from Desk</);
  assert.doesNotMatch(html, /Test fire|testFire/);
  assert.doesNotMatch(html, /Accounts come with the Desk update/, 'the Step A caption is not on the Desk\'s page');
  assert.match(html, /class="figs"/, 'the figures stay in .figs: the skin moves them into its inspector');
  assert.match(html, /<div class="sd-actions">/);
});

test('with accounts: the other note, the account rows and the Desk\'s own + Assign menu', () => {
  const t = load({ book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] } });
  const html = t.view();
  assert.match(html, /From the Lab\. Its orders go to the accounts below\. Every entry carries a stop held at the broker\./);
  assert.match(html, /<h2>Today<\/h2>/);
  assert.match(html, /Lucid Eval #1/);
  assert.match(html, /<div class="amenu" id="amenu-lab_nq_orb" role="menu" hidden>/);
  assert.match(html, /onclick="toggleAsgMenu\(&quot;lab_nq_orb&quot;\)"/);
  assert.match(html, /onclick="pickAsg\(&quot;lab_nq_orb&quot;,&quot;a2&quot;,1\)"/, 'the Desk\'s own flow, with the strategy\'s size');
  assert.doesNotMatch(html, /pickAsg\(&quot;lab_nq_orb&quot;,&quot;a1&quot;/, 'an account already booked is not offered');
  assert.doesNotMatch(html, /Set the limits first/);
});

test('the picker is disabled with its caption until limits exist', () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ limits: null }) } });
  const html = t.view();
  assert.match(html, /<button class="btn btn-quiet noarrow btn-sm" disabled title="Set the limits first\. Then assign an account\.">\+ Assign an account<\/button><div class="mcap">Set the limits first\. Then assign an account\.<\/div>/);
  assert.doesNotMatch(html, /toggleAsgMenu|pickAsg|amenu/);
  assert.match(html, /<span class="t net">—<\/span>/, 'the limits rows show a dash');
  assert.match(html, /Edit limits/);
});

test('read_only: "Another Desk is running on this store." and Limits, the picker and Remove are disabled; the switch and Flatten are not', () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ read_only: true }) } });
  const html = t.view();
  assert.match(html, /<div class="sd-note">Another Desk is running on this store\.<\/div>/);
  assert.match(html, /openLabLimits\([^)]*\)" disabled>Edit limits/);
  assert.match(html, /removeLabStrat\([^)]*\)" disabled title/);
  assert.match(html, /disabled title="Another Desk is running on this store\.">\+ Assign an account/);
  assert.doesNotMatch(html, /toggleAsgMenu|pickAsg/);
  assert.match(html, /toggleStrat\(&quot;lab_nq_orb&quot;, false\)/, 'switching off is never refused');
  assert.doesNotMatch(html, /flattenStrat\([^)]*\)"[^>]*disabled/);
  // opening the dialog does nothing while another Desk owns the store
  t.api.openLabLimits('lab_nq_orb');
  assert.deepEqual(t.shown, []);
});

test('state "check": the page still offers Limits and Remove', () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ state: 'check', why: 'The Desk cannot read its limits.', limits: null }) } });
  const html = t.view();
  assert.match(html, /<b>Check it<\/b>/);
  assert.match(html, /openLabLimits\([^)]*\)">Edit limits/);
  assert.match(html, /removeLabStrat\([^)]*\)" title="Takes it off the Desk/);
  assert.doesNotMatch(html, /removeLabStrat\([^)]*\)" disabled/);
});

test('today\'s trades: a line each with the account, the net, and a failed entry\'s reason with the broker\'s words under it', () => {
  const rounds = [
    { account: 'a1', round: 1, status: 'done', side: 'Buy', qty: 1, entry_fill: 21000.25, exit_fill: 21010.5, exit_reason: 'tp', pnl: 205, why: null, carried: false, date: '2026-10-10' },
    { account: 'a2', round: 1, status: 'error', side: 'Sell', qty: 1, entry_fill: null, exit_fill: null, exit_reason: 'error', pnl: null, why: 'The Desk cannot check this order.', carried: false, date: '2026-10-10', detail: 'Insufficient margin' },
  ];
  const refused = [{ t: '09:31:02', text: 'The price is already past this entry.', account: 'a1' }, { t: '09:40:10', text: 'It is off.', account: null }];
  const t = load({ book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] }, strategies: { lab_nq_orb: deskStrat({ rounds, refused, mode_today: 'desk' }) } });
  const html = t.view();
  assert.match(html, /<span class="h">Lucid Eval #1 · Buy 1 · 21,000\.25 to 21,010\.50 · at the target<\/span><span class="t net">\+\$205<\/span>/);
  assert.match(html, /<span class="h warn">APEX…048 · Sell 1 · The Desk cannot check this order\.<\/span><\/div><div class="feed-row"><span class="h warn">The broker refused it: Insufficient margin<\/span>/);
  assert.match(html, /<span class="t">09:31:02<\/span><span class="h warn">The price is already past this entry\. \(Lucid Eval #1\)<\/span>/);
  assert.match(html, /<span class="t">09:40:10<\/span><span class="h warn">It is off\.<\/span>/);
  assert.doesNotMatch(html, /Clear/, 'no old trade, no Clear');
});

test('a carried row is shown apart from today\'s trades with its sentence and a Clear button; it is never in today\'s list', () => {
  const rounds = [
    { account: 'a1', round: 1, status: 'error', side: 'Buy', qty: 1, entry_fill: 21000, exit_fill: null, exit_reason: 'carried', pnl: null,
      why: "The Desk cannot check the last trade's orders.", carried: true, date: '2026-10-09' },
    { account: 'a1', round: 1, status: 'done', side: 'Sell', qty: 1, entry_fill: 21100, exit_fill: 21090, exit_reason: 'tp', pnl: 100, why: null, carried: false, date: '2026-10-10' },
  ];
  const t = load({ book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] }, strategies: { lab_nq_orb: deskStrat({ rounds, mode_today: 'desk' }) } });
  const html = t.view();
  const [todayPart, oldPart] = html.split('<h2>From an earlier day</h2>');
  assert.ok(oldPart, 'its own section');
  assert.match(oldPart, /Lucid Eval #1 · Buy 1 · Oct 9 · The Desk cannot check the last trade&#39;s orders\./);
  assert.match(oldPart, /onclick="clearLabBlock\(&quot;lab_nq_orb&quot;, &quot;a1&quot;\)"[^>]*>Clear<\/button>/);
  assert.doesNotMatch(todayPart, /Oct 9|last trade/, 'not in today\'s trades');
  assert.match(todayPart, /Sell 1/);
  assert.equal((html.match(/>Clear</g) || []).length, 1);
});

test('Clear posts {strategy, account} and shows the Desk\'s sentence', async () => {
  const t = load({ answer: { ok: true, cleared: [1] } });
  await t.api.clearLabBlock('lab_nq_orb', 'a1');
  assert.deepEqual(t.posts, [{ url: '/api/lab-clear', body: { strategy: 'lab_nq_orb', account: 'a1' } }]);
  assert.deepEqual(t.toasts, ['Cleared.']);
  assert.equal(t.refreshes.length, 1);
  const no = load({ answer: { detail: 'An old order of this trade is still working. Cancel it first.' } });
  await no.api.clearLabBlock('lab_nq_orb', 'a1');
  assert.deepEqual(no.toasts, ['An old order of this trade is still working. Cancel it first.'], 'the sentence as it came, no prefix');
  const down = load({ answer: new Error('network') });
  await down.api.clearLabBlock('lab_nq_orb', 'a1');
  assert.deepEqual(down.toasts, ['The Desk is not answering.']);
});

test('a hostile label, sentence and account name from the Desk cannot break out of the page', () => {
  const evil = '<img src=x onerror=alert(1)>';
  const rounds = [{ account: 'a1', round: 1, status: 'error', side: evil, qty: 1, why: evil, detail: evil, carried: false },
    { account: 'a1', round: 2, status: 'error', side: 'Buy', qty: 1, why: evil, carried: true, date: evil }];
  const t = load({ accounts: { a1: { label: evil, env: 'demo', connected: true } }, book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] },
    strategies: { lab_nq_orb: deskStrat({ rounds, refused: [{ t: evil, text: evil, account: 'a1' }], why: evil, state: 'stopped' }, { label: evil }) },
    rows: [ROW({ label: evil, root: evil, days: [{ date: evil, match: { ok: false, text: evil }, net: 1 }], today: { orders: [{ t: evil, text: evil }], trades: [] } })] });
  const html = t.view() + t.side();
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

// ---- the switch and the confirm ---------------------------------------------------------------------------------------
test('switching ON a Lab strategy with no account asks nothing and says it runs in shadow', async () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  await t.api.toggleStrat('lab_nq_orb', true);
  assert.deepEqual(t.confirms, [], 'shadow: nothing can trade');
  assert.deepEqual(t.posts, [{ url: '/api/strategy', body: { strategy: 'lab_nq_orb', enabled: true } }]);
  assert.deepEqual(t.toasts, ['NQ ORB is ON: it runs in shadow.']);
});

test('switching ON a Lab strategy with accounts asks first and says its orders go to its accounts', async () => {
  const t = load({ book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] }, strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  await t.api.toggleStrat('lab_nq_orb', true);
  assert.equal(t.confirms.length, 1);
  assert.equal(t.confirms[0].title, 'Turn ON NQ ORB?');
  assert.deepEqual(t.posts.map((p) => p.url), ['/api/strategy']);
  assert.deepEqual(t.toasts, ['NQ ORB is ON. Its orders go to its accounts.']);
  const no = load({ confirm: false, book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] }, strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  await no.api.toggleStrat('lab_nq_orb', true);
  assert.deepEqual(no.posts, [], 'Cancel sends nothing');
});

test('ON again the same day after an OFF: the toast reads "It starts with the next session." (ruling, B3 concern 2)', async () => {
  const t = load({ book: { lab_nq_orb: [{ account: 'a1', qty: 1 }] }, strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  // the Desk's next status, once the switch landed: ON and stopped for today by the switch
  t.ctx.refresh = async () => { t.ctx.ST.strategies.lab_nq_orb = plain(deskStrat({ state: 'stopped', why: 'off' })); };
  await t.api.toggleStrat('lab_nq_orb', true);
  assert.deepEqual(t.toasts, ['NQ ORB is ON. It starts with the next session.']);
  const states = load({ strategies: { lab_nq_orb: deskStrat({ state: 'stopped', why: 'off' }) } });
  assert.equal(states.api.stratState('lab_nq_orb', states.ctx.ST.strategies.lab_nq_orb), 'Starts with the next session.');
});

test('switching OFF says what happens to orders and an open position, and never asks', async () => {
  const t = load();
  await t.api.toggleStrat('lab_nq_orb', false);
  assert.deepEqual(t.confirms, []);
  assert.deepEqual(t.toasts, ['NQ ORB is OFF. Unfilled orders are cancelled. An open position keeps its stop and is closed at the flat time. It trades again from the next session.']);
});

test('a refused switch-on shows the Desk\'s own sentence; a switch-off that did not land is still the red alert', async () => {
  const on = load({ answer: { detail: 'The Lab record changed. Try again.' }, strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  await on.api.toggleStrat('lab_nq_orb', true);
  assert.deepEqual(on.toasts, ['The Lab record changed. Try again.']);
  const off = load({ answer: { detail: 'The Lab record changed. Try again.' } });
  await off.api.toggleStrat('lab_nq_orb', false);
  assert.equal(off.alerts.length, 1);
  assert.match(off.alerts[0], /NQ ORB NOT switched off/);
});

test('Flatten & turn off for a Lab strategy: its own confirm words, the existing route, and its plain steps are not failures', async () => {
  const t = load({ answer: { ok: true, enabled: false, results: { a1: ['cancel entry 7: ok', 'This trade had already ended.', 'nothing of its own is left to close'] } } });
  await t.api.flattenStrat('lab_nq_orb');
  assert.deepEqual(t.confirms, [{ title: 'Flatten NQ ORB?', body: 'Cancels its orders, closes its own position on every account, and switches it OFF. It trades again from the next session.', action: 'Flatten & turn off', destructive: true }]);
  assert.deepEqual(t.posts, [{ url: '/api/strategy-flatten', body: { strategy: 'lab_nq_orb' } }]);
  assert.deepEqual(t.alerts, []);
  assert.deepEqual(t.toasts, ['NQ ORB flattened and switched off.']);
  const bad = load({ answer: { ok: true, enabled: false, results: { a1: ['market Sell 1: refused'] } } });
  await bad.api.flattenStrat('lab_nq_orb');
  assert.equal(bad.alerts.length, 1, 'a real failure is still the red alert');
  const stuck = load({ answer: { ok: true, enabled: true, results: { a1: [] }, detail: 'Flattened. Could not switch it off: try the switch again.' } });
  await stuck.api.flattenStrat('lab_nq_orb');
  assert.deepEqual(stuck.toasts, ['Flattened. Could not switch it off: try the switch again.']);
});

test('a strategy that is not from the Lab flattens and switches with the words it always had', async () => {
  const t = load({ answer: { ok: true, enabled: false, results: { a1: ['market Sell 1: ok'] } } });
  await t.api.flattenStrat('nq930');
  assert.equal(t.confirms[0].title, 'Flatten NQ930?'.replace('NQ930', 'NQ930'));
  assert.equal(t.confirms[0].body, 'Cancels its resting entries, market-flattens its symbol on every account it acted on today, and switches the strategy OFF.');
  const s = load();
  await s.api.toggleStrat('nq930', true);
  assert.equal(s.confirms[0].body, 'It will run and execute on its assigned accounts from the next signal.');
  assert.deepEqual(s.toasts, ['NQ930 is ON.']);
  const off = load();
  await off.api.toggleStrat('nq930', false);
  assert.deepEqual(off.toasts, ['NQ930 is OFF — it ignores signals; open positions are untouched.']);
});

// ---- the book ---------------------------------------------------------------------------------------------------------
test('the book: a refusal of a Lab strategy is shown as the Desk\'s sentence, with no prefix; any other strategy keeps its prefix', async () => {
  const t = load({ answer: { detail: 'Set the limits first.' } });
  await t.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 1 }]);
  assert.deepEqual(t.toasts, ['Set the limits first.']);
  for (const sentence of ['Size is capped at 1 here.', 'Another strategy trades NQ on this account.', 'That is the same broker account as Lucid Eval #1.', 'Flatten it first.']) {
    const x = load({ answer: { detail: sentence } });
    await x.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 5 }]);
    assert.deepEqual(x.toasts, [sentence]);
  }
  const other = load({ answer: { detail: 'unknown account' } });
  await other.api.setBook('nq930', []);
  assert.deepEqual(other.toasts, ['Book update failed — unknown account']);
});

test('the book: an account added while the day runs in shadow says "Booked. It starts with the next session."', async () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ mode_today: 'shadow', state: 'shadow' }) } });
  await t.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 1 }]);
  assert.deepEqual(t.toasts, ['Booked. It starts with the next session.']);
  const quiet = load({ strategies: { lab_nq_orb: deskStrat({ mode_today: 'desk' }) } });
  await quiet.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 1 }]);
  assert.deepEqual(quiet.toasts, []);
});

test('booking a live account onto a Lab strategy: the Desk\'s own confirm, with the Lab note', async () => {
  const t = load();
  await t.api.pickAsg('lab_nq_orb', 'a2', 1);
  assert.equal(t.confirms.length, 1);
  assert.equal(t.confirms[0].title, 'Book NQ ORB on APEX…048 LIVE × 1?');
  assert.equal(t.confirms[0].body, 'It will trade real money on its next order. Every entry carries a stop held at the broker. Account APEX2941870000048.');
  assert.equal(t.confirms[0].action, 'Book live');
  assert.deepEqual(t.posts, [{ url: '/api/book', body: { strategy: 'lab_nq_orb', assignments: [{ account: 'a2', qty: 1 }] } }]);
  const demo = load();
  await demo.api.pickAsg('lab_nq_orb', 'a1', 1);
  assert.deepEqual(demo.confirms, [], 'a demo account books at once');
  assert.equal(demo.posts.length, 1);
  // the note of any other strategy is as it was
  assert.match(t.api.liveBookingNote('nq930', 'a2'), /^It will trade real money at the next 9:30 fire\./);
});

// ---- the Limits dialog -------------------------------------------------------------------------------------------------
test('the Limits dialog is static markup, built once; no template of the page writes it, so a repaint cannot wipe a field', () => {
  assert.equal((HTML.match(/id="labLimitsOverlay"/g) || []).length, 1);
  for (const id of ['llTitle', 'llTrades', 'llQty', 'llRisk', 'llLast', 'llFlat', 'llTradesErr', 'llQtyErr', 'llRiskErr', 'llLastErr', 'llFlatErr', 'llNote', 'llSave', 'llCancel']) {
    assert.equal((HTML.match(new RegExp(`id="${id}"`, 'g')) || []).length, 1, id);
  }
  const markup = HTML.slice(HTML.indexOf('<div class="overlay" id="labLimitsOverlay">'), HTML.indexOf('<div class="overlay" id="settingsOverlay">'));
  for (const w of ['Trades a day', 'Most contracts per account', 'Most at risk per trade', 'No new trade after', 'Flat by', 'Cancel', 'Save limits']) assert.ok(markup.includes(w), w);
  assert.match(markup, /role="dialog" aria-modal="true" tabindex="-1" inert aria-labelledby="llTitle"/);
  assert.match(markup, /id="llTrades"[^>]*data-autofocus/);
  // render() and the views never write its fields or markup
  const views = SLICE('/* ===== Desk views', 'function render() {');
  const body = views.slice(0, views.indexOf('/* ---- A Lab strategy the Desk itself knows')) + views.slice(views.indexOf('function renderMain('));
  assert.doesNotMatch(body, /llTrades|llSave|labLimitsOverlay/);
  const render = SLICE('function render() {', 'async function refresh() {');
  assert.doesNotMatch(render, /llTrades|labLimitsOverlay|openLabLimits/);
  // the fields are written only when it opens
  const writers = [...HTML.matchAll(/\$\("#" \+ id\)\.value = /g)].length;
  assert.equal(writers, 1);
});

test('opening the dialog fills the fields from the limits, names the strategy, and opens it through the page\'s one path', () => {
  const t = load();
  t.api.openLabLimits('lab_nq_orb');
  assert.deepEqual(t.shown, ['labLimitsOverlay']);
  assert.equal(t.els.llTitle.textContent, 'Limits for NQ ORB');
  assert.deepEqual(['llTrades', 'llQty', 'llRisk', 'llLast', 'llFlat'].map((id) => t.els[id].value), ['2', '1', '300', '11:00', '15:55']);
  assert.equal(t.els.llNote.hidden, true);
  const none = load({ strategies: { lab_nq_orb: deskStrat({ limits: null }) } });
  none.api.openLabLimits('lab_nq_orb');
  assert.deepEqual(['llTrades', 'llQty', 'llRisk', 'llLast', 'llFlat'].map((id) => none.els[id].value), ['', '1', '', '', '']);
  const unknown = load();
  unknown.api.openLabLimits('lab_nope');
  assert.deepEqual(unknown.shown, []);
});

const fill = (t, f) => { for (const [id, v] of Object.entries(f)) t.el(id).value = v; };

test('Save with a wrong field sends nothing and says, under that field, the table\'s sentence', async () => {
  const t = load();
  t.api.openLabLimits('lab_nq_orb');
  fill(t, { llTrades: '0', llQty: '11', llRisk: '0', llLast: '9:30', llFlat: '16:00' });
  await t.api.saveLabLimits();
  assert.deepEqual(t.posts, []);
  assert.equal(t.els.llTradesErr.textContent, 'Trades a day: a whole number from 1 to 20.');
  assert.equal(t.els.llQtyErr.textContent, 'Contracts: a whole number from 1 to 10.');
  assert.equal(t.els.llRiskErr.textContent, 'At risk per trade: a dollar amount above 0.');
  assert.equal(t.els.llLastErr.textContent, 'No new trade after: a time like 11:00, before the flat time.');
  assert.equal(t.els.llFlatErr.textContent, 'Flat by: a time like 15:55, no later than 15:55.');
  for (const id of ['llTradesErr', 'llQtyErr', 'llRiskErr', 'llLastErr', 'llFlatErr']) assert.equal(t.els[id].hidden, false, id);
  assert.equal(t.els.llTrades.attrs['aria-invalid'], 'true');
  // fixing them clears the sentences
  fill(t, { llTrades: '3', llQty: '2', llRisk: '250', llLast: '10:30', llFlat: '15:30' });
  await t.api.saveLabLimits();
  for (const id of ['llTradesErr', 'llQtyErr', 'llRiskErr', 'llLastErr', 'llFlatErr']) assert.equal(t.els[id].hidden, true, id);
});

test('Save posts exactly what the fields say to /api/lab-limits, by the strategy\'s desk id, and closes on success', async () => {
  const t = load({ answer: { ok: true, strategy: 'lab_nq_orb', limits: LIM } });
  t.api.openLabLimits('lab_nq_orb');
  fill(t, { llTrades: ' 3 ', llQty: '2', llRisk: '$1250.50', llLast: '10:30', llFlat: '15:30' });
  await t.api.saveLabLimits();
  assert.deepEqual(t.posts, [{ url: '/api/lab-limits', body: { strategy: 'lab_nq_orb', limits: { max_trades_day: 3, max_qty: 2, max_risk_usd: 1250.5, last_entry_et: '10:30', flat_et: '15:30' } } }]);
  assert.deepEqual(t.hidden, ['labLimitsOverlay']);
  assert.equal(t.refreshes.length, 1);
});

test('the Desk\'s own refusal is shown in the dialog as its sentence, with no prefix, and the dialog stays open', async () => {
  for (const sentence of ['Flatten it first.', 'Not 09:20-09:35 ET. Try again after 09:35.', 'An account is booked for more. Lower its size first.']) {
    const t = load({ answer: { detail: sentence } });
    t.api.openLabLimits('lab_nq_orb');
    await t.api.saveLabLimits();
    assert.equal(t.els.llNote.textContent, sentence);
    assert.equal(t.els.llNote.hidden, false);
    assert.deepEqual(t.hidden, []);
    assert.equal(t.els.llSave.disabled, false, 'it can be tried again');
  }
  const down = load({ answer: new Error('network') });
  down.api.openLabLimits('lab_nq_orb');
  await down.api.saveLabLimits();
  assert.equal(down.els.llNote.textContent, 'The Desk is not answering.');
});

test('the session start the checks use is the strategy\'s own, when the chart service knows it', async () => {
  const t = load({ rows: [ROW({ session_window: ['08:30', '16:00'] })] });
  t.api.openLabLimits('lab_nq_orb');
  fill(t, { llLast: '09:00' });
  await t.api.saveLabLimits();
  assert.equal(t.posts.length, 1, '09:00 is after its 08:30 start');
  const d = load();
  d.api.openLabLimits('lab_nq_orb');
  fill(d, { llLast: '09:00' });
  await d.api.saveLabLimits();
  assert.equal(d.posts.length, 0, 'before the default 09:25 start');
});

test('a second Save while one is out sends nothing more, and an answer that lands after the dialog closed writes nowhere', async () => {
  let release;
  const t = load({ answer: () => ({ ok: true }) });
  t.ctx.post = (url, body) => { t.posts.push({ url, body }); return new Promise((res) => { release = () => res({ detail: 'Flatten it first.' }); }); };
  t.api.openLabLimits('lab_nq_orb');
  const first = t.api.saveLabLimits();
  await t.api.saveLabLimits();
  assert.equal(t.posts.length, 1);
  assert.equal(t.els.llSave.disabled, true);
  t.api.closeLabLimits();
  release();
  await first;
  assert.equal(t.els.llNote.textContent, '', 'a closed dialog is not written to');
});

test('Enter in a field saves, a held key does not; Escape closes through the page\'s one path', () => {
  assert.match(HTML, /function labLimKey\(e\) \{ if \(e\.key === "Enter" && !e\.repeat\) \{ e\.preventDefault\(\); saveLabLimits\(\); \} \}/);
  assert.equal((HTML.match(/onkeydown="labLimKey\(event\)"/g) || []).length, 5);
  assert.match(HTML, /labLimitsOverlay: \(\) => closeLabLimits\(\)/);
});

// ---- Remove -----------------------------------------------------------------------------------------------------------
test('Remove asks, posts the desk id to /api/lab-remove, and goes to Today; a refusal is shown as the Desk\'s sentence', async () => {
  const t = load({ view: { k: 'strat', name: 'lab_nq_orb' } });
  await t.api.removeLabStrat('lab_nq_orb');
  assert.deepEqual(t.confirms, [{ title: 'Remove NQ ORB from the Desk?', body: 'Its history is kept.', action: 'Remove', destructive: false }]);
  assert.deepEqual(t.posts, [{ url: '/api/lab-remove', body: { strategy: 'lab_nq_orb' } }]);
  assert.match(t.toasts[0], /^NQ ORB is off the Desk\. Its history is kept/);
  assert.equal(t.api.VIEW.k, 'today');
  const no = load({ answer: { detail: 'Flatten it first.' } });
  await no.api.removeLabStrat('lab_nq_orb');
  assert.deepEqual(no.toasts, ['Flatten it first.']);
  const cancel = load({ confirm: false });
  await cancel.api.removeLabStrat('lab_nq_orb');
  assert.deepEqual(cancel.posts, []);
});

// ---- the rest of the page ---------------------------------------------------------------------------------------------
test('the Activity lines for the Lab\'s journal events are in the ACTIVITY map', () => {
  const act = SLICE('const ACTIVITY = {', 'function activityLine(');
  for (const k of ['lab_refused', 'lab_runner_down', 'lab_runner_back', 'lab_stopped', 'lab_flatten', 'lab_cancelled', 'lab_limits_set', 'lab_round', 'lab_settled',
    'lab_check', 'lab_carry', 'lab_carry_cleared', 'lab_exit_unconfirmed', 'lab_cancel_raced_fill', 'lab_open_without_cfg', 'lab_removed']) {
    assert.match(act, new RegExp(`${k}: labAct\\("${k}"\\)`), k);
    assert.equal(typeof D.activity[k], 'function', `${k} has its words`);
  }
});

test('the Activity page reads a Lab line through the page\'s own formatter', () => {
  const HELPERS = SLICE('const fmt = (v, d = 2)', '/* ---- theme ---- */') + SLICE('function acctShort(', 'function liveBookingNote(') + SLICE('const esc = (v) =>', 'async function chartPost(') +
    SLICE('const killText = ', 'async function doKill(');
  const ctx = vm.createContext({ console, DeskLab: D, ST: { accounts: { a1: { label: 'Lucid Eval #1', env: 'demo' } }, strategies: { lab_nq_orb: { cfg: { label: 'NQ ORB' } } } },
    $: () => ({ addEventListener() {}, setAttribute() {}, set innerHTML(v) {}, get innerHTML() { return ''; } }), window: { getSelection: () => '' } });
  vm.runInContext(HELPERS + SLICE('/* ---- readiness, as the page shows it (W4) ----', '/* ---- render ---- */') + '\nglobalThis.line = activityLine;', ctx);
  assert.deepEqual(plain(ctx.line({ event: 'lab_refused', strategy: 'lab_nq_orb', account: 'a1', text: 'It is off.' })), { text: 'NQ ORB order refused on Lucid Eval #1 — It is off.', tone: 'warn' });
  assert.deepEqual(plain(ctx.line({ event: 'lab_runner_down', strategy: 'lab_nq_orb' })), { text: 'NQ ORB: runner down', tone: 'neg' });
  assert.deepEqual(plain(ctx.line({ event: 'lab_stopped', strategy: 'lab_nq_orb', why: 'off' })), { text: 'NQ ORB stopped for today', tone: '' });
  // a desklab.js that did not load: the generic line, never a blank row
  const bare = vm.createContext({ console, ST: ctx.ST, $: ctx.$, window: { getSelection: () => '' } });
  vm.runInContext(HELPERS + SLICE('/* ---- readiness, as the page shows it (W4) ----', '/* ---- render ---- */') + '\nglobalThis.line = activityLine;', bare);
  assert.match(bare.line({ event: 'lab_refused', strategy: 'lab_nq_orb', account: 'a1', text: 'x' }).text, /^Lab refused/);
});

test('the skin\'s Setup card for a Lab strategy on the Desk reads the same helper, and the figures box says Backtest', () => {
  assert.match(SKIN, /deskSetupRows/);
  assert.match(SKIN, /cfg\.kind === 'lab'/);
  assert.match(SKIN, /'Backtest'/);
  assert.doesNotMatch(SKIN, /\bfetch\(|XMLHttpRequest|WebSocket/);
});

test('asset versions: desklab.js and the skin\'s manifest are bumped', () => {
  assert.match(HTML, /<script src="\/static\/desklab\.js\?v=2"><\/script>/);
  assert.doesNotMatch(HTML, /desklab\.js\?v=1/);
  const manifest = JSON.parse(readFileSync(new URL('../../homebase/static/apple/manifest.json', import.meta.url), 'utf8'));
  assert.equal(manifest.version >= 3, true);
});

test('Step A is as it was: the chart-service Lab block still never calls the Desk\'s own routes', () => {
  const block = HTML.slice(HTML.indexOf('/* ---- LAB STRATEGIES on the Desk'), HTML.indexOf('function setView('));
  assert.doesNotMatch(block.replace(/\/\*[\s\S]*?\*\//g, ''), /\/api\/(strategy|book|status|lab-)/);
});
