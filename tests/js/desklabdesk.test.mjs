import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
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
const BOOKED0 = { lab_nq_orb: [{ account: 'a1', qty: 1 }] };
const ACCOUNTS = { a1: { label: 'Lucid Eval #1', env: 'demo', connected: true }, a2: { label: 'APEX2941870000048', env: 'live', connected: true } };

/* The whole Desk-views part of the page (sidebar, rows, strategy page, the Lab part) with a fake document around it. */
function load({ strategies = { nq930: nq930(), lab_nq_orb: deskStrat() }, book = {}, rows = [ROW()], view = { k: 'today' }, accounts = ACCOUNTS,
  answer = { ok: true }, confirm = true, readOk = true, demo = false, deskLab = D, journal = [] } = {}) {
  const els = {}, posts = [], toasts = [], confirms = [], alerts = [], shown = [], hidden = [], refreshes = [];
  const el = (id) => (els[id] = els[id] || { id, innerHTML: '', textContent: '', value: '', hidden: false, disabled: false, attrs: {},
    setAttribute(k, v) { this.attrs[k] = String(v); }, classList: { contains: () => false } });
  const ctx = vm.createContext({
    console, DOUBLE_CLICK_MS: 400, DEMO: demo, CHART: 'http://x', DESK_STALE: false, window: { AlgoVisibility: AV },
    location: { hash: '', protocol: 'http:', hostname: 'x' }, history: { replaceState() {} }, document: { hidden: false, getElementById: () => null, querySelectorAll: () => [], addEventListener() {}, activeElement: null },
    $: (sel) => el(sel.replace(/^#/, '')), ...(deskLab ? { DeskLab: deskLab } : {}),
    ST: { armed: true, et_now: '2026-10-10T10:00:00-0400', timer: { strategies: {} }, accounts: plain(accounts), book: plain(book), journal: plain(journal), strategies: plain(strategies) },
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
    SLICE('const labAct = ', 'let FEED_ROWS') +
    SLICE('/* ===== Desk views', 'function render() {') +
    SLICE('/* ---- account row (rendered inside strategy cards) ---- */', '/* ---- connect wizard ---- */') +
    SLICE('/* ---- strategy on/off + flatten ----', '/* ---- accounts popup ---- */') +
    `\nDESKLAB = { strategies: ${JSON.stringify(rows)}, runner: { alive: true } }; DESKLAB_OK = ${readOk};` +
    `\nVIEW = ${JSON.stringify(view)};` +
    '\nglobalThis.api = { renderSide, renderMain, labDeskView, stratView, stratState, stratDotCls, todayRow, specOf, setBook, pickAsg, liveBookingNote, toggleStrat,' +
    ' flattenStrat, dayHeadline, dayTimeline, journalShown, todayFoot, openLabLimits, closeLabLimits, saveLabLimits, removeLabStrat, clearLabBlock, labRowsHtml, labOnDesk, todayLabRow, get LAB_LIM() { return LAB_LIM; }, get VIEW() { return VIEW; } };';
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

test('read_only: "Another copy of the Desk is using the Lab strategies." and Limits, the picker and Remove are disabled; the switch and Flatten are not', () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ read_only: true }) } });
  const html = t.view();
  assert.match(html, /<div class="sd-note">Another copy of the Desk is using the Lab strategies\.<\/div>/);
  assert.match(html, /openLabLimits\([^)]*\)" disabled>Edit limits/);
  assert.match(html, /removeLabStrat\([^)]*\)" disabled title/);
  assert.match(html, /disabled title="Another copy of the Desk is using the Lab strategies\.">\+ Assign an account/);
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
  const t = load({ book: BOOKED0 });
  await t.api.toggleStrat('lab_nq_orb', false);
  assert.deepEqual(t.confirms, []);
  assert.deepEqual(t.toasts, ['NQ ORB is OFF. Unfilled orders are cancelled. An open position keeps its stop and is closed at the flat time. It trades again from the next session.']);
});

test('a refused switch-on shows the Desk\'s own sentence; a switch-off that did not land is still the red alert', async () => {
  const on = load({ answer: { detail: 'This strategy was promoted again. Try again.' }, strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  await on.api.toggleStrat('lab_nq_orb', true);
  assert.deepEqual(on.toasts, ['This strategy was promoted again. Try again.']);
  const off = load({ answer: { detail: 'This strategy was promoted again. Try again.' } });
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
  const desk = load({ strategies: { lab_nq_orb: deskStrat({ mode_today: 'desk' }) } });      // final wave: a day through the Desk
  await desk.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 1 }]);
  assert.deepEqual(desk.toasts, ['Booked. It joins at the next trade.']);
  const quiet = load({ strategies: { lab_nq_orb: deskStrat({ mode_today: null }) } });         // the session has not begun
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
  assert.equal(t.els.llRiskErr.textContent, 'At risk per trade: a dollar amount above 0, like 300 or 300.50.');
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

test('final wave I1: a window that runs past the flat time -- the Desk\'s note under the Limits panel, small and warn; none without it', () => {
  const say = "Its window runs to 16:00 but the Desk closes at 15:55. A trade still open then is closed 5 minutes before the test's, so that day will not match.";
  const html = load({ strategies: { lab_nq_orb: deskStrat({ note: say }) }, book: BOOKED0 }).view();
  assert.ok(html.includes(`<div class="mcap warn">${say.replace("'", '&#39;')}</div>`), 'the note as the Desk sends it, escaped');
  const at = html.indexOf('<h2>Limits</h2>');
  assert.ok(at >= 0 && html.indexOf('mcap warn', at) > at && html.indexOf('mcap warn', at) < html.indexOf('<h2>Today', at), 'inside the Limits panel');
  const none = load({ strategies: { lab_nq_orb: deskStrat() }, book: BOOKED0 }).view();
  assert.doesNotMatch(none, /Desk closes at/);
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
  assert.deepEqual(t.confirms, [{ title: 'Remove NQ ORB from the Desk?', body: 'Its history is kept. Its accounts come off.', action: 'Remove', destructive: false }]);
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
  assert.equal(bare.line({ event: 'lab_refused', strategy: 'lab_nq_orb', account: 'a1', text: 'x' }).text, "Something happened to a Lab strategy: see the Activity log.", 'never a raw name');
});

test('the skin\'s Setup card for a Lab strategy on the Desk reads the same helper, and the figures box says Backtest', () => {
  assert.match(SKIN, /deskSetupRows/);
  assert.match(SKIN, /cfg\.kind === 'lab'/);
  assert.match(SKIN, /'Backtest'/);
  assert.doesNotMatch(SKIN, /\bfetch\(|XMLHttpRequest|WebSocket/);
});

test('asset versions: desklab.js and the skin\'s manifest are bumped', () => {
  assert.match(HTML, /<script src="\/static\/desklab\.js\?v=5"><\/script>/);
  assert.doesNotMatch(HTML, /desklab\.js\?v=[1234]\b/);
  const manifest = JSON.parse(readFileSync(new URL('../../homebase/static/apple/manifest.json', import.meta.url), 'utf8'));
  assert.equal(manifest.version >= 3, true);
});

test('Step A is as it was: the chart-service Lab block still never calls the Desk\'s own routes', () => {
  const block = HTML.slice(HTML.indexOf('/* ---- LAB STRATEGIES on the Desk'), HTML.indexOf('function setView('));
  assert.doesNotMatch(block.replace(/\/\*[\s\S]*?\*\//g, ''), /\/api\/(strategy|book|status|lab-)/);
});

/* ======================================================================================================================
   Task B6, fix round 1 (the page review): each test below failed on 165c236f.
   ====================================================================================================================== */
const BOOKED = { lab_nq_orb: [{ account: 'a1', qty: 1 }] };
const txt = (h) => h.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

test('I2 the broker\'s words come from the refused row, under its reason', () => {
  const refused = [{ t: '09:31:02', text: 'The Desk cannot check this order.', account: 'a1', detail: 'Insufficient margin' },
    { t: '09:32:00', text: 'It is off.', account: null }];
  const t = load({ book: BOOKED, strategies: { lab_nq_orb: deskStrat({ refused, mode_today: 'desk' }) } });
  const html = t.view();
  assert.match(html, /<span class="t">09:31:02<\/span><span class="h warn">The Desk cannot check this order\. \(Lucid Eval #1\)<\/span><\/div><div class="feed-row"><span class="h warn">The broker refused it: Insufficient margin<\/span><\/div>/);
  assert.equal((html.match(/The broker refused it/g) || []).length, 1, 'only the row that carries a detail');
  const evil = load({ book: BOOKED, strategies: { lab_nq_orb: deskStrat({ refused: [{ t: '1', text: 'x', account: 'a1', detail: '<img src=x onerror=1>' }] }) } }).view();
  assert.doesNotMatch(evil, /<img/);
});

test('I1 a trade the Desk says to check shows its sentence with the warn mark, and the dot goes warn', () => {
  const rounds = [{ account: 'a1', round: 1, status: 'live', side: 'Sell', qty: 1, entry_fill: 21020, exit_fill: null, exit_reason: null, pnl: null,
    why: 'Check it: the close order was not confirmed. Its stop is still working.', carried: false, date: '2026-10-10' }];
  const t = load({ book: BOOKED, strategies: { nq930: nq930(), lab_nq_orb: deskStrat({ state: 'in_position', rounds, mode_today: 'desk' }) } });
  assert.match(t.view(), /<span class="h warn">Lucid Eval #1 · Sell 1 · in at 21,020\.00 · In position · Check it: the close order was not confirmed\. Its stop is still working\.<\/span>/);
  assert.match(t.side(), /<i class="sd warn"><\/i><span class="it"><b>NQ ORB/);
});

test('I3 "Check it" has the server\'s sentence under it', () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ state: 'check', why: 'The Desk cannot read its limits.', limits: null }) } });
  const html = t.view();
  assert.match(html, /<b>Check it<\/b><\/div>\s*<div class="sd-note">The Desk cannot read its limits\.<\/div>/);
  const none = load({ strategies: { lab_nq_orb: deskStrat({ state: 'waiting' }) } }).view();
  assert.doesNotMatch(none, /sd-state"><b>[^<]*<\/b><\/div>\s*<div class="sd-note">The Desk/);
});

test('R1 a dead runner reads "Runner is not running" on the row, the page and the dot; an open trade stays as the server sends it', () => {
  const dead = load({ strategies: { lab_nq_orb: deskStrat({ state: 'waiting', runner: { alive: false, age_s: 90 } }) } });
  assert.match(dead.view(), /<b>Runner is not running<\/b>/);
  assert.equal(dead.api.stratState('lab_nq_orb', dead.ctx.ST.strategies.lab_nq_orb), 'Runner is not running');
  assert.equal(dead.api.stratDotCls(dead.ctx.ST.strategies.lab_nq_orb, ''), 'warn');
  const trade = load({ strategies: { lab_nq_orb: deskStrat({ state: 'in_position', runner: { alive: false, age_s: 90 } }) } });
  assert.match(trade.view(), /<b>In position<\/b>/);
});

test('I4 Flatten & turn off: a close order already out is a plain line, never the red alert', async () => {
  const t = load({ answer: { ok: true, enabled: false, results: { a1: ['the close order is out: waiting for its fill'] } } });
  await t.api.flattenStrat('lab_nq_orb');
  assert.deepEqual(t.alerts, []);
  assert.deepEqual(t.toasts, ['Its close order is already out.']);
  const real = load({ answer: { ok: true, enabled: false, results: { a1: ['the close order is out: waiting for its fill'], a2: ['market Sell 1: refused'] } } });
  await real.api.flattenStrat('lab_nq_orb');
  assert.equal(real.alerts.length, 1, 'a real failure on another account is still the alert');
  const noround = load({ answer: { ok: true, enabled: false, results: { a1: ['the round ended while the close was sent (tp)', 'check it — x'] } } });
  await noround.api.flattenStrat('lab_nq_orb');
  assert.doesNotMatch(noround.alerts.join(' '), /\bround\b/i);
});

test('I4 the Activity page reads a Lab flatten\'s plain steps as plain, for a Lab strategy only', () => {
  const HELPERS = SLICE('const fmt = (v, d = 2)', '/* ---- theme ---- */') + SLICE('function acctShort(', 'function liveBookingNote(') + SLICE('const esc = (v) =>', 'async function chartPost(') +
    SLICE('const killText = ', 'async function doKill(');
  const ctx = vm.createContext({ console, DeskLab: D, ST: { accounts: { a1: { label: 'Lucid Eval #1', env: 'demo' } }, strategies: { lab_nq_orb: { cfg: { label: 'NQ ORB', kind: 'lab' } }, nq930: { cfg: { label: 'nq930', kind: 'straddle' } } } },
    $: () => ({ addEventListener() {}, setAttribute() {}, set innerHTML(v) {}, get innerHTML() { return ''; } }), window: { getSelection: () => '' } });
  vm.runInContext(HELPERS + SLICE('/* ---- readiness, as the page shows it (W4) ----', '/* ---- render ---- */') + '\nglobalThis.line = activityLine;', ctx);
  const plainOne = { event: 'manual_flatten', strategy: 'lab_nq_orb', results: { a1: ['This trade had already ended.', 'cancel entry 7: ok'] } };
  assert.deepEqual(plain(ctx.line(plainOne)), { text: 'NQ ORB flattened on 1 account', tone: '' });
  assert.deepEqual(plain(ctx.line({ event: 'clock_flat', strategy: 'lab_nq_orb', account: 'a1', actions: ['nothing of its own is left to close', 'market Sell 1: ok'] })), { text: 'NQ ORB flattened on Lucid Eval #1 at the end-of-day time', tone: '' });
  assert.equal(ctx.line({ event: 'manual_flatten', strategy: 'lab_nq_orb', results: { a1: ['the close order is out: waiting for its fill'] } }).tone, '');
  // another strategy keeps its reading: the same step is a check there
  assert.equal(ctx.line({ event: 'manual_flatten', strategy: 'nq930', results: { a1: ['This trade had already ended.'] } }).tone, 'neg');
});

test('I6 with desklab.js missing, a Lab strategy never blanks nq930\'s rows', () => {
  const t = load({ deskLab: null, strategies: { nq930: nq930(), lab_nq_orb: deskStrat({ state: 'waiting' }) } });
  assert.doesNotThrow(() => t.ctx.api.renderMain(['nq930', 'lab_nq_orb'], 0));
  assert.match(t.els.stratList.innerHTML, /toggleStrat\('nq930', false\)/, 'nq930\'s Today row is there');
  assert.doesNotThrow(() => t.side());
  assert.match(t.side(), /setView\('strat','nq930'\)/);
  assert.doesNotThrow(() => t.api.todayRow('lab_nq_orb', t.ctx.ST.strategies.lab_nq_orb));
  assert.doesNotThrow(() => t.api.stratView('lab_nq_orb'));
  assert.match(t.api.stratView('lab_nq_orb'), /could not be shown/);
});

test('I6 every DeskLab call in index.html and the skin is inside a guard that leaves a non-Lab row alone', () => {
  const calls = [...HTML.matchAll(/DeskLab\.\w+/g)].map((m) => m.index);
  assert.ok(calls.length > 40);
  // the shared functions that a non-Lab strategy goes through: no DeskLab call outside labSafe or a kind-lab branch
  const shared = ['function todayRow(', 'function renderSide(', 'function stratView(', 'const specOf', 'function stratState(', 'const stratDotCls', 'function dayHeadline(', 'function dayTimeline('];
  for (const name of shared) {
    const i = HTML.indexOf(name);
    assert.ok(i >= 0, name);
    const body = HTML.slice(i, HTML.indexOf('\n}\n', i) + 3 > i + 3 ? HTML.indexOf('\n}\n', i) + 3 : i + 2000);
    for (const m of body.matchAll(/DeskLab\.\w+/g)) {
      const before = body.slice(Math.max(0, m.index - 220), m.index);
      assert.match(before, /labSafe\(|kind === "lab"/, `${name}: ${m[0]} must sit inside labSafe or a kind-lab branch`);
    }
  }
});

test('I7 / N2 the feed and the "Last event" time leave out only the Lab\'s named bookkeeping; every other Lab event shows', () => {
  const journal = [
    { ts: 3, et: '2026-10-10T10:00:03-0400', event: 'lab_event_done', strategy: 'lab_nq_orb' },
    { ts: 2, et: '2026-10-10T10:00:02-0400', event: 'lab_event', strategy: 'lab_nq_orb' },
    { ts: 2, et: '2026-10-10T10:00:01-0400', event: 'lab_added', strategy: 'lab_nq_orb' },
    { ts: 2, et: '2026-10-10T09:59:30-0400', event: 'lab_store_owned' },
    { ts: 1, et: '2026-10-10T09:59:00-0400', event: 'strategy_toggled', strategy: 'nq930', enabled: true },
    { ts: 0, et: '2026-10-10T09:58:00-0400', event: 'lab_refused', strategy: 'lab_nq_orb', text: 'It is off.' },
    { ts: 0, et: '2026-10-10T09:57:00-0400', event: 'lab_something_new' }];
  const t = load({ journal });
  const shown = t.api.journalShown(t.ctx.ST.journal);
  assert.deepEqual(shown.map((r) => r.event), ['lab_added', 'lab_store_owned', 'strategy_toggled', 'lab_refused', 'lab_something_new']);
  assert.match(t.side(), /Last event 10:00/);           // final wave: a strategy arriving on the Desk is a line
  assert.match(t.api.todayFoot(0), /Last event 10:00/);
  // a journal with no Lab line is returned as it is
  const none = [{ event: 'armed_toggled' }, null, 'x'];
  assert.deepEqual(plain(t.api.journalShown(none)), plain(none));
  assert.equal((HTML.match(/DeskLab\.hiddenEvent\(r\.event\)/g) || []).length, 2, 'the Activity list and the Last-event time use one rule');
  // desklab.js missing: nothing is hidden and nothing throws
  const bare = load({ deskLab: null, journal });
  assert.equal(bare.api.journalShown(bare.ctx.ST.journal).length, 7);
});

const PYDIR = new URL('../../homebase/', import.meta.url);
function pyFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const u = new URL(e.name + (e.isDirectory() ? '/' : ''), dir);
    if (e.isDirectory()) { if (!['static', '__pycache__', '.state', 'node_modules'].includes(e.name)) out.push(...pyFiles(u)); } else if (e.name.endsWith('.py')) out.push(u);
  }
  return out;
}
const JOURNALED = [...new Set(pyFiles(PYDIR).flatMap((u) => [...readFileSync(u, 'utf8').matchAll(/(?:journal|_journal|_note)\(\s*(?:cfg,\s*)?["'](lab_[a-z_]+)["']/g)].map((m) => m[1])))].sort();

test('N2 every Lab event the Desk journals is either named as hidden bookkeeping or has a plain line', () => {
  assert.ok(JOURNALED.length >= 30, `the source walk found ${JOURNALED.length} names`);
  for (const must of ['lab_refused', 'lab_stopped', 'lab_event', 'lab_unbooked', 'lab_unreadable', 'lab_key_error', 'lab_start_error']) assert.ok(JOURNALED.includes(must), must);
  const act = SLICE('const ACTIVITY = {', 'function activityLine(');
  for (const ev of JOURNALED) {
    const hidden = D.hiddenEvent(ev);
    const line = new RegExp(`${ev}: labAct\\("${ev}"\\)`).test(act) && typeof D.activity[ev] === 'function';
    assert.ok(hidden !== line, `${ev}: ${hidden ? 'hidden AND has a line' : 'neither hidden nor has a line'}`);
  }
  // the hide list is explicit and small, and every name in it is bookkeeping the owner has no use for
  assert.deepEqual(D.HIDDEN_EVENTS.slice().sort(), ['lab_event', 'lab_event_done']);
});

test('N2 each Lab event reaches the real Activity feed as a plain line; an event the page does not know shows a plain fallback', () => {
  const HELPERS = SLICE('const fmt = (v, d = 2)', '/* ---- theme ---- */') + SLICE('function acctShort(', 'function liveBookingNote(') + SLICE('const esc = (v) =>', 'async function chartPost(') +
    SLICE('const killText = ', 'async function doKill(');
  const mkctx = (deskLab) => {
    const ctx = vm.createContext({ console, ...(deskLab ? { DeskLab: deskLab } : {}), ST: { accounts: { a1: { label: 'Lucid Eval #1', env: 'demo' }, a2: { label: 'Apex 2', env: 'demo' } }, strategies: { lab_nq_orb: { cfg: { label: 'NQ ORB', kind: 'lab' } } } },
      $: () => ({ addEventListener() {}, setAttribute() {}, set innerHTML(v) {}, get innerHTML() { return ''; } }), window: { getSelection: () => '' } });
    vm.runInContext(HELPERS + SLICE('/* ---- readiness, as the page shows it (W4) ----', '/* ---- render ---- */') + '\nglobalThis.line = activityLine; globalThis.render1 = renderActivity;', ctx);
    return ctx;
  };
  const ctx = mkctx(D);
  const sample = { strategy: 'lab_nq_orb', account: 'a1', accounts: ['a1', 'a2'], error: 'boom', text: 'It is off.', reason: 'x', why: 'y', date: '2026-10-09', on: true, results: { a1: { ok: true } }, limits: LIM, qty: 1, round: 1, key: 'k', store: '/x' };
  for (const ev of JOURNALED.filter((e) => !D.hiddenEvent(e))) {
    const got = plain(ctx.line({ event: ev, ...sample }));
    assert.ok(got.text.length > 8, ev);
    assert.doesNotMatch(got.text, /_|boom|\/x/, `${ev}: no raw name, no raw error text: ${got.text}`);
    assert.doesNotMatch(got.text, /\b(round|rounds|sidecar|intent|overlay|carried)\b/i, ev);
  }
  assert.equal(ctx.line({ event: 'lab_unbooked', ...sample }).text, 'The Desk took Lucid Eval #1, Apex 2 off NQ ORB.');
  assert.deepEqual(plain(ctx.line({ event: 'lab_key_error', error: 'x' })), { text: 'The Desk could not set up its link to the Lab runner. Lab strategies cannot send orders. Check it.', tone: 'neg' });
  assert.deepEqual(plain(ctx.line({ event: 'lab_zzz_new' })), { text: "Something happened to a Lab strategy: see the Activity log.", tone: 'warn' });
  const bare = mkctx(null);
  assert.deepEqual(plain(bare.line({ event: 'lab_refused', strategy: 'lab_nq_orb', text: 'x' })), { text: "Something happened to a Lab strategy: see the Activity log.", tone: 'warn' }, 'desklab.js missing: still a plain line, never a raw name');
});

test('c4 the Today headline and the day bar are what they were when a Lab strategy only runs in shadow', () => {
  const mk = (strategies, book) => load({ strategies, book });
  const off = { nq930: { ...nq930(), cfg: { ...nq930().cfg, enabled: false } } };
  const withLab = { ...off, lab_nq_orb: deskStrat({ state: 'shadow' }, { flat_et: '11:30', cancel_et: '11:30' }) };
  const a = mk(off, {}), b = mk(withLab, {});
  const friday = (...xs) => xs.forEach((x) => { x.ctx.ST.et_now = '2026-10-09T12:00:00-0400'; });
  friday(a, b);
  assert.deepEqual(plain(b.api.dayHeadline([])), plain(a.api.dayHeadline([])), 'a Lab strategy with no account is not "armed"');
  assert.equal(b.api.dayTimeline(), a.api.dayTimeline(), 'and its times are never the bar\'s');
  // nq930 and gc_nfp ON: the count is theirs
  const two = { nq930: nq930(), gc_nfp: { ...nq930(), cfg: { ...nq930().cfg, label: 'gc' } } };
  const c = mk(two, {}), d = mk({ ...two, lab_nq_orb: deskStrat({ state: 'shadow' }) }, {});
  friday(c, d);
  assert.deepEqual(plain(d.api.dayHeadline([])), plain(c.api.dayHeadline([])));
  // with an account booked it is armed like any other
  const e = mk({ ...two, lab_nq_orb: deskStrat({ state: 'waiting' }) }, BOOKED);
  friday(e);
  assert.match(e.api.dayHeadline([])[1], /^3 armed/);
  assert.match(c.api.dayHeadline([])[1], /^2 armed/);
});

test('m1 the switch\'s tooltip says where the orders go, on the page and on the Today row', () => {
  const none = load();
  assert.match(none.view(), /aria-checked="true"\s*title="ON: it runs in shadow"/);
  assert.match(none.api.todayRow('lab_nq_orb', none.ctx.ST.strategies.lab_nq_orb), /title="ON: it runs in shadow"/);
  const booked = load({ book: BOOKED });
  assert.match(booked.view(), /title="ON: its orders go to its accounts"/);
  assert.match(booked.api.todayRow('lab_nq_orb', booked.ctx.ST.strategies.lab_nq_orb), /title="ON: its orders go to its accounts"/);
  const off = load({ strategies: { lab_nq_orb: deskStrat({ state: 'off' }, { enabled: false }) } });
  assert.match(off.api.todayRow('lab_nq_orb', off.ctx.ST.strategies.lab_nq_orb), /title="OFF: it does nothing"/);
  // another strategy's tooltip is as it was
  assert.match(none.api.todayRow('nq930', none.ctx.ST.strategies.nq930), /title="ON — this strategy runs and executes"/);
});

test('m2 switching OFF with no account booked says Step A\'s short sentence', async () => {
  const t = load();
  await t.api.toggleStrat('lab_nq_orb', false);
  assert.deepEqual(t.toasts, ['NQ ORB is OFF: it does nothing.']);
  const booked = load({ book: BOOKED });
  await booked.api.toggleStrat('lab_nq_orb', false);
  assert.match(booked.toasts[0], /It trades again from the next session\.$/);
});

test('m4 under read_only the size edit and the unassign x of a booked account are disabled', () => {
  const t = load({ book: BOOKED, strategies: { lab_nq_orb: deskStrat({ read_only: true }) } });
  const html = t.view();
  assert.doesNotMatch(html, /editQty/);
  assert.match(html, /<button class="x" disabled style=/);
  assert.doesNotMatch(html, /onclick="removeAsg/);
  assert.match(html, /<span class="strats">×1<\/span>/);
  const ok = load({ book: BOOKED }).view();
  assert.match(ok, /onclick="editQty\(event,'lab_nq_orb'/);
  assert.match(ok, /onclick="removeAsg\('lab_nq_orb'/);
});

test('m5 a save that is out stays out across a close and a re-open: no second POST, and its answer does not close the new dialog', async () => {
  const t = load();
  let release;
  t.ctx.post = (url, body) => { t.posts.push(plain({ url, body })); return new Promise((res) => { release = () => res({ ok: true }); }); };
  t.api.openLabLimits('lab_nq_orb');
  const first = t.api.saveLabLimits();
  t.api.closeLabLimits();
  t.api.openLabLimits('lab_nq_orb');
  assert.equal(t.els.llSave.disabled, true, 'the save is still out');
  await t.api.saveLabLimits();
  assert.equal(t.posts.length, 1, 'no second POST');
  t.hidden.length = 0;
  release();
  await first;
  assert.deepEqual(t.hidden, [], 'the first answer does not close the re-opened dialog');
  assert.equal(t.els.llSave.disabled, false);
  assert.equal(t.refreshes.length >= 1, true, 'but the new limits are read');
});

test('m6 Save when the strategy has left the Desk says so and closes', async () => {
  const t = load();
  t.api.openLabLimits('lab_nq_orb');
  delete t.ctx.ST.strategies.lab_nq_orb;
  await t.api.saveLabLimits();
  assert.deepEqual(t.posts, []);
  assert.deepEqual(t.toasts, ['That strategy is not on the Desk.']);
  assert.deepEqual(t.hidden, ['labLimitsOverlay']);
});

test('m7 with the chart service down the session start is unknown: a valid early time is posted and the Desk judges', async () => {
  const t = load({ rows: [] });
  t.api.openLabLimits('lab_nq_orb');
  t.el('llLast').value = '08:45';
  await t.api.saveLabLimits();
  assert.equal(t.posts.length, 1);
  assert.equal(t.posts[0].body.limits.last_entry_et, '08:45');
});

test('I5 through the page: a comma in the risk field sends nothing and says the field\'s sentence', async () => {
  const t = load();
  t.api.openLabLimits('lab_nq_orb');
  t.el('llRisk').value = '300,5';
  await t.api.saveLabLimits();
  assert.deepEqual(t.posts, []);
  assert.equal(t.els.llRiskErr.textContent, 'At risk per trade: a dollar amount above 0, like 300 or 300.50.');
});

test('m10 a flatten with a failed step and a switch that did not turn off says what the answer says', async () => {
  const t = load({ answer: { ok: true, enabled: true, results: { a1: ['market Sell 1: refused'] }, detail: 'Flattened. Could not switch it off: try the switch again.' } });
  await t.api.flattenStrat('lab_nq_orb');
  assert.equal(t.alerts.length, 1);
  assert.doesNotMatch(t.alerts[0], /It is switched OFF/);
  assert.match(t.alerts[0], /It could not be switched off: try the switch again\./);
  const off = load({ answer: { ok: true, enabled: false, results: { a1: ['market Sell 1: refused'] } } });
  await off.api.flattenStrat('lab_nq_orb');
  assert.match(off.alerts[0], /It is switched OFF; flatten what is left at the broker now\./);
});

test('m13 the Remove confirm says its accounts come off', async () => {
  const t = load();
  await t.api.removeLabStrat('lab_nq_orb');
  assert.equal(t.confirms[0].body, 'Its history is kept. Its accounts come off.');
});

test('m14 in shadow the Today row, the sidebar and the page show what the day would have made, as Step A did', () => {
  const row = ROW({ today: { date: '2026-10-10', state: 'running', why: null, orders: [], trades: [], net: 120 } });
  const t = load({ rows: [row] });
  const s = t.ctx.ST.strategies.lab_nq_orb;
  const today = t.api.todayRow('lab_nq_orb', s);
  assert.match(today, /<div class="rp mono dim" title="What it would have made today, after costs, 1 contract">\+\$120<\/div>/);
  assert.match(t.side(), /<span class="ir mono dim">\+\$120<\/span>/);
  assert.match(t.view(), /<b>Waiting for the session<\/b> · today would be \+\$120/);
  const booked = load({ rows: [row], book: BOOKED });
  assert.doesNotMatch(booked.api.todayRow('lab_nq_orb', booked.ctx.ST.strategies.lab_nq_orb), /would have made/);
  assert.doesNotMatch(booked.view(), /today would be/);
  const none = load({ rows: [ROW()] });
  assert.doesNotMatch(none.side(), /\+\$120/);
});

test('m16 the warn caption has its colour in the Mac skin, and the skin version is bumped', () => {
  const css = readFileSync(new URL('../../homebase/static/apple/desk.css', import.meta.url), 'utf8');
  assert.match(css, /html\.hb-apple \.mcap\.warn \{ color: var\(--a-red-text\); \}/);
  const manifest = JSON.parse(readFileSync(new URL('../../homebase/static/apple/manifest.json', import.meta.url), 'utf8'));
  assert.equal(manifest.version >= 4, true);
});

test('m17 a second click on Clear while the first is out, or just answered, sends nothing more', async () => {
  const t = load({ answer: { ok: true, cleared: [1] } });
  const a = t.api.clearLabBlock('lab_nq_orb', 'a1');
  const b = t.api.clearLabBlock('lab_nq_orb', 'a1');
  await Promise.all([a, b]);
  await t.api.clearLabBlock('lab_nq_orb', 'a1');
  assert.equal(t.posts.length, 1);
  await t.api.clearLabBlock('lab_nq_orb', 'a2');
  assert.equal(t.posts.length, 2, 'another account is its own row');
  const no = load({ answer: { detail: 'This account has no block to clear.' } });
  await no.api.clearLabBlock('lab_nq_orb', 'a1');
  await no.api.clearLabBlock('lab_nq_orb', 'a1');
  assert.equal(no.posts.length, 2, 'a refusal changes nothing: it can be tried again');
  const rounds = [{ account: 'a1', round: 1, status: 'error', side: 'Buy', qty: 1, why: 'x', carried: true, date: '2026-10-09' }];
  const v = load({ strategies: { lab_nq_orb: deskStrat({ rounds }) }, book: BOOKED, answer: { ok: true } });
  assert.doesNotMatch(v.view(), /clearLabBlock[^>]*disabled/);
  await v.api.clearLabBlock('lab_nq_orb', 'a1');
  assert.match(v.view(), /clearLabBlock\(&quot;lab_nq_orb&quot;, &quot;a1&quot;\)" disabled/);
});

test('the Remove busy guard and a carried row per account: Clear carries the row\'s own account', () => {
  const rounds = [{ account: 'a1', round: 1, status: 'error', why: 'x', carried: true, date: '2026-10-09' }, { account: 'a2', round: 1, status: 'error', why: 'y', carried: true, date: '2026-10-09' }];
  const html = load({ strategies: { lab_nq_orb: deskStrat({ rounds }) }, book: { lab_nq_orb: [{ account: 'a1', qty: 1 }, { account: 'a2', qty: 1 }] } }).view();
  assert.match(html, /clearLabBlock\(&quot;lab_nq_orb&quot;, &quot;a1&quot;\)/);
  assert.match(html, /clearLabBlock\(&quot;lab_nq_orb&quot;, &quot;a2&quot;\)/);
});

test('fix 2: a Lab strategy with an account booked is on the day bar with its Flat mark only; one with none stays off; the headline agrees', () => {
  const offOwn = { nq930: { ...nq930(), cfg: { ...nq930().cfg, enabled: false } } };
  const booked = load({ strategies: { ...offOwn, lab_nq_orb: deskStrat({ state: 'waiting' }, { flat_et: '11:30', cancel_et: '11:30' }) }, book: BOOKED });
  booked.ctx.ST.et_now = '2026-10-09T12:00:00-0400';
  const bar = booked.api.dayTimeline();
  assert.match(bar, /11:30 Flat/);
  assert.doesNotMatch(bar, /Cancel unfilled/, 'the Lab strategy has no cancel time of its own');
  assert.match(bar, /flat at 11:30/);
  assert.equal((bar.match(/class="tl-tick"/g) || []).length, 1, 'one tick: the flat time');
  assert.match(booked.api.dayHeadline([])[0], /^Session closed\./, 'the headline reads the same strategy: 12:00 is after its 11:30');
  const shadow = load({ strategies: { ...offOwn, lab_nq_orb: deskStrat({ state: 'shadow' }, { flat_et: '11:30', cancel_et: '11:30' }) } });
  shadow.ctx.ST.et_now = '2026-10-09T12:00:00-0400';
  assert.match(shadow.api.dayTimeline(), /12:55 Cancel unfilled/, 'no account: the bar is the Desk\'s own strategy\'s');
  assert.equal(shadow.api.dayHeadline([])[0], 'In session.');
  // an own strategy ON keeps the bar, booked Lab strategy or not
  const own = load({ strategies: { nq930: nq930(), lab_nq_orb: deskStrat({ state: 'waiting' }, { flat_et: '11:30', cancel_et: '11:30' }) }, book: BOOKED });
  own.ctx.ST.et_now = '2026-10-09T12:00:00-0400';
  assert.match(own.api.dayTimeline(), /12:55 Cancel unfilled/);
  assert.match(own.api.dayTimeline(), /15:55 Flat/);
});

test('fix 3: the risk field has the placeholder 300', () => {
  assert.match(HTML, /<input id="llRisk"[^>]*placeholder="300"/);
});

const two = (a, b) => ({ nq930: { ...nq930(), cfg: { ...nq930().cfg, ...a } }, gc_nfp: { ...nq930(), cfg: { ...nq930().cfg, label: 'gc', ...b } } });
const at13 = (t) => { t.ctx.ST.et_now = '2026-10-09T13:00:00-0400'; return t; };

test('fix 4a c4 with two own strategies: the session\'s end is the first ARMED one\'s, not the first listed', () => {
  // A (first) is OFF with flat 12:00; B is ON with flat 15:55: at 13:00 the day is still in session
  const t = at13(load({ strategies: two({ enabled: false, flat_et: '12:00' }, { flat_et: '15:55' }) }));
  assert.equal(t.api.dayHeadline([])[0], 'In session.');
  // A ON with flat 12:00 first: its end is the day's
  const u = at13(load({ strategies: two({ flat_et: '12:00' }, { flat_et: '15:55' }) }));
  assert.equal(u.api.dayHeadline([])[0], 'Session closed.');
});

test('fix 4b c4 with two own strategies: the bar is the first ARMED one\'s times', () => {
  const t = load({ strategies: two({ enabled: false, cancel_et: '11:00', flat_et: '12:00' }, { cancel_et: '13:15', flat_et: '15:30' }) });
  const bar = t.api.dayTimeline();
  assert.match(bar, /13:15 Cancel unfilled/);
  assert.match(bar, /15:30 Flat/);
  const u = load({ strategies: two({ cancel_et: '11:00', flat_et: '12:00' }, { cancel_et: '13:15', flat_et: '15:30' }) });
  assert.match(u.api.dayTimeline(), /11:00 Cancel unfilled/);
});

test('fix 4c the busy flag of the Limits dialog is reset by every kind of answer', async () => {
  for (const answer of [new Error('network'), { detail: 'Flatten it first.' }, {}]) {
    const t = load({ answer });
    t.api.openLabLimits('lab_nq_orb');
    await t.api.saveLabLimits();
    assert.equal(t.els.llSave.disabled, false, JSON.stringify(String(answer)));
    await t.api.saveLabLimits();
    assert.equal(t.posts.length, 2, 'the next Save goes out');
  }
});

test('fix 4d "account not connected" in a flatten answer is still the red alert', async () => {
  const t = load({ answer: { ok: true, enabled: false, results: { a1: ['account not connected'] } } });
  await t.api.flattenStrat('lab_nq_orb');
  assert.equal(t.alerts.length, 1);
  assert.match(t.alerts[0], /account not connected/);
  assert.deepEqual(t.toasts, []);
});

test('final wave G1: the strategy page shows "Runner down" and the sentence when the runner is not connected to the Desk', () => {
  const say = 'The runner is not connected to the Desk.';
  const t = load({ strategies: { lab_nq_orb: deskStrat({ state: 'runner_down', why: say }) }, book: BOOKED0 });
  const html = t.view();
  assert.ok(html.includes('<b>Runner down</b>'), html);
  assert.ok(html.includes(`<div class="sd-note">${say}</div>`), html);
  assert.ok(!html.includes('Waiting for the session'));
});

test('final wave B6: an account added while the day trades through the Desk says it joins at the next trade', async () => {
  const t = load({ strategies: { lab_nq_orb: deskStrat({ mode_today: 'desk' }) }, book: BOOKED0 });
  await t.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 1 }, { account: 'a2', qty: 1 }]);
  assert.deepEqual(t.toasts, ['Booked. It joins at the next trade.']);
  const s = load({ strategies: { lab_nq_orb: deskStrat({ mode_today: 'shadow' }) }, book: BOOKED0 });
  await s.api.setBook('lab_nq_orb', [{ account: 'a1', qty: 1 }, { account: 'a2', qty: 1 }]);
  assert.deepEqual(s.toasts, ['Booked. It starts with the next session.']);
});

test('final wave B6: the flatten alert believes the Desk\'s `check` list, also when every step reads plain', async () => {
  const t = load({ answer: { ok: true, enabled: false, results: { a1: ['This trade had already ended.'] }, check: ['a1'] } });
  await t.api.flattenStrat('lab_nq_orb');
  assert.equal(t.alerts.length, 1);
  assert.match(t.alerts[0], /^NQ ORB flatten — CHECK IT on Lucid Eval #1 — /);
  assert.match(t.alerts[0], /flatten what is left at the broker now\.$/);
  assert.deepEqual(t.toasts, []);
  const ok = load({ answer: { ok: true, enabled: false, results: { a1: ['This trade had already ended.'] } } });
  await ok.api.flattenStrat('lab_nq_orb');
  assert.deepEqual(ok.alerts, []);
  assert.deepEqual(ok.toasts, ['NQ ORB flattened and switched off.']);
  const both = load({ answer: { ok: true, enabled: false, results: { a1: ['market Sell 1: refused'], a2: ['This trade had already ended.'] }, check: ['a2'] } });
  await both.api.flattenStrat('lab_nq_orb');
  assert.equal(both.alerts.length, 1);
  assert.match(both.alerts[0], /FLATTEN FAILED on Lucid Eval #1/, 'a failed step still alerts, with its words');
  assert.match(both.alerts[0], /CHECK IT on APEX/, 'and the account the Desk says to check');
});

test('final wave B6: with two Lab strategies booked, the day ends at the latest flat time, on the bar and in the headline', () => {
  const offOwn = { nq930: { ...nq930(), cfg: { ...nq930().cfg, enabled: false } } };
  const strategies = { ...offOwn, lab_a: deskStrat({ state: 'waiting' }, { label: 'A', flat_et: '11:30', cancel_et: '11:30' }),
    lab_b: deskStrat({ state: 'waiting' }, { label: 'B', flat_et: '14:00', cancel_et: '14:00' }) };
  const t = load({ strategies, book: { lab_a: [{ account: 'a1', qty: 1 }], lab_b: [{ account: 'a2', qty: 1 }] } });
  t.ctx.ST.et_now = '2026-10-09T12:00:00-0400';
  assert.match(t.api.dayTimeline(), /14:00 Flat/);
  assert.equal(t.api.dayHeadline([])[0], 'In session.');
  // gc_nfp-like own strategy ON until 10:00 and a booked Lab strategy until 14:00: the day is the Lab one's
  const g = load({ strategies: { gc: { ...nq930(), cfg: { ...nq930().cfg, cancel_et: '10:00', flat_et: '10:00' } }, lab_b: strategies.lab_b }, book: { lab_b: [{ account: 'a2', qty: 1 }] } });
  g.ctx.ST.et_now = '2026-10-09T12:00:00-0400';
  assert.equal(g.api.dayHeadline([])[0], 'In session.');
  assert.match(g.api.dayTimeline(), /14:00 Flat/);
  // no Lab strategy armed: the bar and the headline are what they were
  const n = load({ strategies: { gc: g.ctx.ST.strategies.gc, lab_b: strategies.lab_b } });
  n.ctx.ST.et_now = '2026-10-09T12:00:00-0400';
  assert.equal(n.api.dayHeadline([])[0], 'Session closed.');
});

test('final wave B6 (rehearsal o1): a cancel time equal to the flat time is one label', () => {
  const t = load({ strategies: { nq930: { ...nq930(), cfg: { ...nq930().cfg, cancel_et: '15:55', flat_et: '15:55' } } } });
  const bar = t.api.dayTimeline();
  assert.match(bar, />15:55 Cancel unfilled, flat</);
  assert.doesNotMatch(bar, />15:55 Flat</);
  assert.doesNotMatch(bar, />15:55 Cancel unfilled</);
  const u = load({ strategies: { nq930: nq930() } }).api.dayTimeline();      // the usual 12:55 / 15:55: two labels
  assert.match(u, />12:55 Cancel unfilled</);
  assert.match(u, />15:55 Flat</);
});
