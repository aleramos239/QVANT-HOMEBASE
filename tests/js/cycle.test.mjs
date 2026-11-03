import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* Set up a team (the owner, 2026-11-02: "easy to set up impossible to get confused and mess it up"): a Desk group's page carries
   ONE card -- the accounts to tick, How, the size, Hold overnight per strategy, ONE Trading switch, ONE Save and a status line.
   The switch and Save both send the whole card to /api/setup; it asks first on start, stop, a LIVE size-up and a lost last account. */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const CODE = between('/* Set up a team (the owner, 2026-11-02', 'async function deleteGroup(');
const plain = (v) => JSON.parse(JSON.stringify(v));

const ACCTS = () => ({ a: { connected: true, env: 'live' }, b: { connected: true, env: 'live' } });
const ON = { on: true, next: 'a', accounts: ['a', 'b'], members: ['lab_x'], mode: 'cycle', risk_usd: 1000, max_minis: 17 };

function ctx({ cyc = null, enabled = false, armed = true, liveSet = ['a', 'b'], yes = true, reply, ticked = ['a'], risk = '1000', minis = '17',
               mode = null, assign = {}, hold = null, book = { lab_x: [{ account: 'a', qty: 1 }] }, members = ['lab_x', 'nq930'],
               accounts = ACCTS(), lab = {}, machine = 'server' } = {}) {
  const sent = [], toasts = [], asked = [], titles = [], refreshes = [];
  const els = { '.cyc-risk': { value: risk }, '.cyc-minis': { value: minis }, '.cyc-save': { innerHTML: '' }, ...(mode ? { '.cyc-mode': { value: mode } } : {}) };
  const boxes = Object.keys(accounts).map((acct) => ({ checked: ticked.includes(acct), dataset: { acct } }));
  const lists = {
    '.cyc-acct': boxes,
    '.cyc-assign': mode === 'split' ? Object.entries(assign).map(([m, v]) => ({ value: v, dataset: { m } })) : [],
    '.cyc-hold': hold ? Object.entries(hold).map(([m, v]) => ({ checked: v, dataset: { m } })) : [],
  };
  const c = vm.createContext({
    ST: { armed, strategies: { lab_x: { cfg: { kind: 'lab', enabled }, lab }, nq930: { cfg: { kind: 'straddle' } } }, accounts, book, groups: cyc ? { g1: cyc } : {} },
    DEMO: false, FREEZE: false,
    groupOf: (id) => (members ? { id, name: 'Apex', members } : null),
    labSafe: (f, d) => { try { return f(); } catch (_) { return d; } },
    cycleLastTurn: () => 'Last turn: A',
    DAY_PNL_WORDS: (p) => String(p),
    plural: (n, a, b) => `${n} ${n === 1 ? a : b}`,
    render() {},
    document: { querySelector: () => ({ querySelector: (sel) => els[sel] || null, querySelectorAll: (sel) => lists[sel] || [] }) },
    jsArg: (v) => JSON.stringify(v),
    acctShort: (id) => id.toUpperCase(),
    stratLabel: (n) => n,
    isDemoAcct: (a) => !liveSet.includes(a),
    isRealAcct: (a) => liveSet.includes(a),
    machineWords: () => ({ server: 'on the SERVER · Chicago', mac: 'on this Mac' })[machine] || '',
    switchBounced: () => false,
    confirmDlg: async (title, body) => { asked.push(body); titles.push(title); return yes; },
    post: async (url, body) => { sent.push(plain([url, body])); return reply || { ok: true }; },
    refresh: () => refreshes.push(1),
    toast: (m) => toasts.push(m),
    answerWhy: (r) => (r && r.ok ? '' : 'the desk refused it'),
  });
  vm.runInContext(ESC + CODE + '\nglobalThis.cycleHtml = cycleHtml; globalThis.saveCycle = saveCycle; globalThis.toggleTeam = toggleTeam;' +
    ' globalThis.cycleEdit = cycleEdit; globalThis.teamStatus = teamStatus; globalThis.draft = () => CYC_DRAFT;', c);
  return { c, sent, toasts, asked, titles, els, boxes, refreshes, html: () => c.cycleHtml({ id: 'g1', members }) };
}

test('a team with no strategy says what to do first', () => {
  const { c } = ctx({ members: ['nq930'] });
  assert.match(c.cycleHtml({ id: 'g1', members: ['nq930'] }), /Put this team's strategies in it first/);
});

test('the card: one Trading switch, every account a tick, How, the size, hold per strategy, a red line until it is set up', () => {
  const h = ctx().html();
  assert.match(h, /<h2>Set up<\/h2>/);
  assert.match(h, /<b>Trading<\/b> OFF/);
  assert.match(h, /aria-checked="false"[\s\S]*onclick="toggleTeam\(&quot;g1&quot;\)"|onclick="toggleTeam\("g1"\)"/);
  assert.equal((h.match(/class="cyc-acct"/g) || []).length, 2);
  assert.equal((h.match(/<option value="(cycle|share|split)"/g) || []).length, 3);
  assert.match(h, /class="cyc-hold" data-m="lab_x"/);
  assert.match(h, /<div class="mcap warn">Not ready: no account ticked: its strategies run in shadow · lab_x is still on A, outside this team · lab_x is OFF\.<\/div>/);
  assert.doesNotMatch(h, /Book every|Update the cycle|Account group/, 'no second button to keep things in step');
});

test('ON and set up: the switch is on and the line is green, naming the accounts, the way and the size', () => {
  const h = ctx({ cyc: ON, enabled: true }).html();
  assert.match(h, /<b>Trading<\/b> ON/);
  assert.match(h, /aria-checked="true"/);
  assert.match(h, /Last turn: A/);
  assert.match(h, /<div class="mcap pos">Ready: trades on A and B, take turns: one account a trade, \$1,000 a trade\.<\/div>/);
});

test('the status line says every reason it will not trade', () => {
  const accounts = ACCTS();
  accounts.a.connected = false;
  accounts.b.day = { locked: true };
  const { c } = ctx({ armed: false, accounts, enabled: true, lab: { state: 'stopped' }, book: {} });
  const st = c.teamStatus({ ...ON, mode: 'split', assign: {} }, ['lab_x']);
  assert.equal(st.ok, false);
  assert.equal(st.text, 'Not ready: the Desk is OFF · account A is offline · account B is stopped for today · lab_x has no account · lab_x is stopped for today');
  assert.match(c.teamStatus({ ...ON, members: [] }, ['lab_x']).text, /lab_x is not saved in the team yet/);
  c.ST.strategies.lab_x.lab = { state: 'runner_down' };
  assert.match(c.teamStatus(ON, ['lab_x']).text, /lab_x's runner is not running/);
});

test('the switch ON asks first, naming the LIVE accounts, the machine and the size, and sends the whole card', async () => {
  const { c, sent, asked, titles, toasts } = ctx({ ticked: ['a', 'b'], book: {} });
  await c.toggleTeam('g1');
  assert.equal(titles[0], 'Start trading?');
  assert.equal(asked[0], '1 strategy take turns across 2 accounts (2 LIVE) on the SERVER · Chicago. Each trade sized to lab_x $1,000 at risk, at most 17 full contracts.');
  assert.deepEqual(sent, [['/api/setup', { team: 'g1', name: 'Apex', members: ['lab_x'], accounts: ['a', 'b'], risk_usd: 1000, max_minis: 17, on: true }]]);
  assert.deepEqual(toasts, ['Trading ON.']);
});

test('a no at the question sends nothing', async () => {
  const { c, sent } = ctx({ yes: false });
  await c.toggleTeam('g1');
  assert.equal(sent.length, 0);
});

test('the switch OFF asks first and sends on: false; accounts and sizes stay', async () => {
  const { c, sent, titles, asked } = ctx({ cyc: ON, enabled: true, ticked: ['a', 'b'] });
  await c.toggleTeam('g1');
  assert.equal(titles[0], 'Stop trading?');
  assert.match(asked[0], /today is over for them .* Accounts and sizes stay for the next ON\./);
  assert.equal(sent[0][1].on, false);
  assert.deepEqual(sent[0][1].accounts, ['a', 'b']);
});

test('Save while ON: sizing up on LIVE asks, old → new; lowering saves at once', async () => {
  const up = ctx({ cyc: ON, enabled: true, ticked: ['a', 'b'], risk: '1500' });
  await up.c.saveCycle('g1');
  assert.equal(up.titles[0], 'Change the team?');
  assert.match(up.asked[0], /^Risk \$1,000 → \$1,500\. It is ON across 2 LIVE accounts on the SERVER · Chicago: the next trade uses this\.$/);
  assert.equal(up.sent[0][1].on, true);
  const down = ctx({ cyc: ON, enabled: true, ticked: ['a', 'b'], risk: '500' });
  await down.c.saveCycle('g1');
  assert.equal(down.asked.length, 0);
  assert.deepEqual(down.toasts, ['Saved.']);
});

test('Save: a DEMO-only team says DEMO, never LIVE', async () => {
  const { c, asked } = ctx({ liveSet: [], ticked: ['a', 'b'] });
  c.ST.accounts.a.env = c.ST.accounts.b.env = 'demo';
  await c.toggleTeam('g1');
  assert.doesNotMatch(asked[0], /LIVE/);
});

test('One account each: a picker per strategy; one left with no account while ON says today is over for it', async () => {
  const h = ctx({ cyc: { ...ON, mode: 'split', assign: { lab_x: 'b' } }, enabled: true }).html();
  assert.match(h, /class="cyc-assign" data-m="lab_x"/);
  assert.match(h, /<option value="b" selected>B<\/option>/);
  const t = ctx({ cyc: { ...ON, mode: 'split', assign: { lab_x: 'a' } }, enabled: true, ticked: ['b'], mode: 'split', assign: { lab_x: 'a' } });
  await t.c.saveCycle('g1');
  assert.match(t.asked[0], /lab_x loses the last account: today is over for it; trading again tomorrow\./);
  assert.deepEqual(t.sent[0][1].assign, {}, 'an unticked account takes its strategy with it');
});

test('hold overnight per strategy: shown in the Save, counted as a size-up, sent as hold', async () => {
  const t = ctx({ cyc: ON, enabled: true, ticked: ['a', 'b'], hold: { lab_x: true } });
  t.c.cycleEdit('g1');
  assert.match(t.els['.cyc-save'].innerHTML, /Save: lab_x holds overnight/);
  await t.c.saveCycle('g1');
  assert.match(t.asked[0], /lab_x holds overnight/);
  assert.deepEqual(t.sent[0][1].hold, { lab_x: true });
});

test('a typed value is a draft: the Save button reads old → new, a repaint keeps it, typing it back clears it', () => {
  const t = ctx({ cyc: ON, enabled: true, ticked: ['a', 'b'], risk: '1500' });
  t.c.cycleEdit('g1');
  assert.match(t.els['.cyc-save'].innerHTML, /Save: Risk \$1,000 → \$1,500/);
  assert.match(t.html(), /class="cyc-risk"[^>]*value="1500"/);
  t.els['.cyc-risk'].value = '1000';
  t.c.cycleEdit('g1');
  assert.equal(t.els['.cyc-save'].innerHTML, '');
  assert.equal(Object.keys(t.c.draft()).length, 0);
});

test('a refusal is said in words and the draft stays', async () => {
  const t = ctx({ cyc: ON, enabled: true, ticked: ['a', 'b'], risk: '500', reply: { detail: 'nope' } });
  t.c.cycleEdit('g1');
  await t.c.saveCycle('g1');
  assert.deepEqual(t.toasts, ['NOT saved — the desk refused it.']);
  assert.ok(t.c.draft().g1);
});

test('a strategy booked before it joined: the line names the accounts outside the team, and Save (nothing typed) takes it off', async () => {
  const t = ctx({ cyc: { ...ON, accounts: ['b'], next: 'b' }, enabled: true, ticked: ['b'], book: { lab_x: [{ account: 'a', qty: 1 }, { account: 'b', qty: 1 }] } });
  const h = t.html();
  assert.match(h, /Not ready: lab_x is still on A, outside this team\./);
  assert.match(h, /Save: lab_x off A</);
  await t.c.saveCycle('g1');
  assert.deepEqual(t.sent[0][1].accounts, ['b']);
  const fresh = ctx({ members: ['lab_x'] }).html();        // no team saved yet: Save adds it
  assert.match(fresh, /Save: \+ lab_x · lab_x off A</);
});

function mixed(over = {}) {
  const t = ctx({ cyc: { ...ON, members: ['lab_x', 'lab_y'] }, enabled: true, ticked: ['a', 'b'], members: ['lab_x', 'lab_y'], ...over });
  t.c.ST.strategies.lab_y = { cfg: { kind: 'lab', enabled: false }, lab: {} };
  return t;
}

test('Save on a mixed team (one ON, one OFF) sends on: null and says Saved; the switch still sends true or false', async () => {
  const t = mixed({ risk: '500' });
  await t.c.saveCycle('g1');
  assert.equal(t.sent[0][1].on, null);
  assert.deepEqual(t.toasts, ['Saved.']);
  const s = mixed();
  await s.c.toggleTeam('g1');
  assert.equal(s.sent[0][1].on, true);
});

test('Save sends Hold overnight only for a strategy whose box changed; the others keep each row\'s own', async () => {
  const book = { lab_x: [{ account: 'a', qty: 1, hold: true }, { account: 'b', qty: 1 }], lab_y: [] };
  const t = mixed({ book, hold: { lab_x: true, lab_y: true } });              // lab_x as it is; lab_y ticked
  await t.c.saveCycle('g1');
  assert.deepEqual(t.sent[0][1].hold, { lab_y: true });
  const u = mixed({ book, hold: { lab_x: true, lab_y: false } });             // nothing changed
  await u.c.saveCycle('g1');
  assert.deepEqual(u.sent[0][1].hold || {}, {});
});

test('a mixed team with an ON member on LIVE accounts asks before a size-up, though it sends on: null', async () => {
  const t = mixed({ risk: '1500' });
  await t.c.saveCycle('g1');
  assert.equal(t.titles[0], 'Change the team?');
  assert.match(t.asked[0], /It is ON across 2 LIVE accounts/);
  assert.equal(t.sent[0][1].on, null);
});
