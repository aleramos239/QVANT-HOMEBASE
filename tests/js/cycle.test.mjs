import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* Account cycle (the owner, 2026-10-25): a Desk group's page carries the cycle -- a switch, the accounts to tick, the risk
   per trade and the most per trade -- and, while on, "Next account: X". Turning it ON asks first, naming LIVE accounts. */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const CODE = between('/* Account cycle (the owner, 2026-10-25)', 'async function deleteGroup(');

function ctx({ cyc = null, live = false, yes = true, reply, ticked = ['a'], risk = '1000', minis = '17', book = { lab_x: [{ account: 'a', qty: 1 }] },
              group = { name: 'Apex', members: ['lab_x', 'nq930'] } } = {}) {
  const sent = [], toasts = [], asked = [];
  const el = (cls) => ({ value: cls === '.cyc-risk' ? risk : minis });
  const boxes = ['a', 'b'].map((acct) => ({ checked: ticked.includes(acct), dataset: { acct } }));
  const c = vm.createContext({
    ST: { strategies: { lab_x: { cfg: { kind: 'lab' } }, nq930: { cfg: { kind: 'straddle' } } },
          accounts: { a: {}, b: {} }, book, groups: cyc ? { g1: cyc } : {} },
    DEMO: false, FREEZE: false,
    groupOf: (id) => (group ? { id, ...group } : null),
    labSafe: (f, d) => { try { return f(); } catch (_) { return d; } },
    DeskLab: { refusalText: (r) => (r && r.detail) || 'refused' },
    document: { querySelector: () => ({ querySelector: el, querySelectorAll: () => boxes }) },
    jsArg: (v) => JSON.stringify(v),
    acctShort: (id) => id.toUpperCase(),
    stratLabel: (n) => n,
    isDemoAcct: () => !live,
    switchBounced: () => false,
    confirmDlg: async (title, body) => { asked.push(body); return yes; },
    post: async (url, body) => { sent.push([url, body]); return reply || { ok: true, ...body }; },
    refresh: () => {},
    toast: (m) => toasts.push(m),
    answerWhy: (r) => (r && r.ok ? '' : 'the desk refused it'),
  });
  vm.runInContext(ESC + CODE + '\nglobalThis.cycleHtml = cycleHtml; globalThis.setCycle = setCycle; globalThis.bookCycle = bookCycle; globalThis.syncCycle = syncCycle;', c);
  return { c, sent, toasts, asked };
}

test('off: a switch, every account to tick, no next account', () => {
  const { c } = ctx();
  const h = c.cycleHtml({ id: 'g1', members: ['lab_x', 'nq930'] });
  assert.match(h, /Account cycle/);
  assert.match(h, /aria-checked="false"/);
  assert.equal((h.match(/class="cyc-acct"/g) || []).length, 2);
  assert.doesNotMatch(h, /Next account/);
});

test('on: next account, ticked accounts, an account missing bookings is named', () => {
  const cyc = { on: true, next: 'b', accounts: ['a', 'b'], members: ['lab_x'], risk_usd: 1000, max_minis: 17 };
  const h = ctx({ cyc }).c.cycleHtml({ id: 'g1', members: ['lab_x'] });
  assert.match(h, /aria-checked="true"/);
  assert.match(h, /Next account: B/);
  assert.match(h, /B: 1 of 1 strategies not booked/);
});

test('turning it on asks first, naming live accounts, and sends the form', async () => {
  const { c, sent, asked } = ctx({ live: true, ticked: ['a', 'b'] });
  await c.setCycle('g1', true);
  assert.match(asked[0], /2 LIVE/);
  assert.match(asked[0], /\$1,000 at risk/);
  assert.deepEqual(JSON.parse(JSON.stringify(sent[0][1])), { id: 'g1', name: 'Apex', members: ['lab_x'], accounts: ['a', 'b'],
                                                              risk_usd: 1000, max_minis: 17, on: true });
});

test('a no at the question sends nothing', async () => {
  const { c, sent } = ctx({ yes: false });
  await c.setCycle('g1', true);
  assert.equal(sent.length, 0);
});

test('a refusal is said', async () => {
  const { c, toasts } = ctx({ reply: { detail: 'nope' } });
  await c.setCycle('g1', false);
  assert.match(toasts[0], /NOT changed/);
});

const ON = { on: true, next: 'a', accounts: ['a', 'b'], members: ['lab_x'], risk_usd: 1000, max_minis: 17 };

test('book-all is offered only while the cycle is on, and books the missing accounts at size 1', async () => {
  assert.match(ctx({ cyc: ON }).c.cycleHtml({ id: 'g1', members: ['lab_x'] }), /Book every strategy on these accounts/);
  assert.doesNotMatch(ctx({ cyc: { ...ON, on: false } }).c.cycleHtml({ id: 'g1', members: ['lab_x'] }), /Book every strategy/);
  const { c, sent, asked } = ctx({ cyc: ON });
  await c.bookCycle('g1');
  assert.match(asked[0], /ONE account/);
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), [['/api/book', { strategy: 'lab_x', assignments: [{ account: 'a', qty: 1 },
                                                                                                       { account: 'b', qty: 1 }] }]]);
  const off = ctx({ cyc: { ...ON, on: false } });
  await off.c.bookCycle('g1');
  assert.equal(off.sent.length, 0);
});

test('stopping the cycle asks first when a strategy is booked on several accounts', async () => {
  const book = { lab_x: [{ account: 'a', qty: 1 }, { account: 'b', qty: 1 }] };
  const { c, sent, asked } = ctx({ cyc: ON, book, live: true, yes: false });
  await c.setCycle('g1', false);
  assert.match(asked[0], /EVERY account/) && assert.match(asked[0], /2 of them LIVE/);
  assert.equal(sent.length, 0);
});

test('the cycle follows its group: new strategies, and gone with the group', async () => {
  const a = ctx({ cyc: ON, group: { name: 'Apex', members: ['lab_x', 'lab_y'] } });
  a.c.ST.strategies.lab_y = { cfg: { kind: 'lab' } };
  await a.c.syncCycle('g1');
  assert.deepEqual(JSON.parse(JSON.stringify(a.sent)), [['/api/groups', { id: 'g1', members: ['lab_x', 'lab_y'] }]]);
  const b = ctx({ cyc: ON, group: null });
  await b.c.syncCycle('g1');
  assert.deepEqual(b.sent[0][0], '/api/groups/delete');
  const e = ctx({ cyc: ON, group: { name: 'Apex', members: [] } });
  await e.c.syncCycle('g1');
  assert.deepEqual(JSON.parse(JSON.stringify(e.sent[0][1])), { id: 'g1', members: [], on: false });
  const same = ctx({ cyc: ON, group: { name: 'Apex', members: ['lab_x'] } });
  await same.c.syncCycle('g1');
  assert.equal(same.sent.length, 0);
});

test('an empty group still shows the card, saying what to do first', () => {
  const h = ctx({ group: { name: 'Apex', members: [] } }).c.cycleHtml({ id: 'g1', members: [] });
  assert.match(h, /Account cycle/);
  assert.match(h, /strategies in it first/);
});

test('moving a strategy into an ON cycle asks first; a no moves nothing', async () => {
  const MOVE = between('async function moveToGroup(', '$("#groupOverlay").addEventListener');
  const run = async (yes, cyc) => {
    const posts = [], asked = [];
    const c = vm.createContext({
      DESKGROUPS: { groups: [{ id: 'g4', name: 'apex 300k', members: [] }] }, ST: { groups: cyc ? { g4: cyc } : {}, book: {}, strategies: {} },
      confirmDlg: async (t) => { asked.push(t); return yes; }, groupPost: async (a, b) => { posts.push([a, b]); return true; },
      renderGroupMgr: () => {}, stratLabel: (n) => n, cycleCopies: () => [], cycleLive: () => '',
    });
    vm.runInContext(MOVE + '\nglobalThis.moveToGroup = moveToGroup;', c);
    await c.moveToGroup('lab_x', 'g4');
    return { posts, asked };
  };
  const on = { on: true, name: 'apex 300k', members: [], accounts: ['a', 'b'], risk_usd: 1000 };
  let r = await run(false, on);
  assert.match(r.asked[0], /Add lab_x to the apex 300k account cycle/) && assert.equal(r.posts.length, 0);
  r = await run(true, on);
  assert.deepEqual(JSON.parse(JSON.stringify(r.posts)), [['move', { strategy: 'lab_x', group: 'g4' }]]);
  r = await run(true, null);                                         // no cycle: no question
  assert.equal(r.asked.length, 0) && assert.equal(r.posts.length, 1);
});
