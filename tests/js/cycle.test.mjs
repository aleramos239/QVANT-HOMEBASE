import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* Account group (the owner, 2026-10-25): a Desk group's page carries the cycle -- a switch, the accounts to tick, the risk
   per trade and the most per trade -- and, while on, "Next account: X". Turning it ON asks first, naming LIVE accounts. */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const CODE = between('/* Account group (the owner, 2026-10-25)', 'async function deleteGroup(');

function ctx({ cyc = null, live = false, liveSet = null, yes = true, reply, ticked = ['a'], risk = '1000', minis = '17', book = { lab_x: [{ account: 'a', qty: 1 }] },
              group = { name: 'Apex', members: ['lab_x', 'nq930'] }, accounts = { a: {}, b: {} }, machine = 'server' } = {}) {
  const sent = [], toasts = [], asked = [], titles = [], refreshes = [];
  const els = { '.cyc-risk': { value: risk }, '.cyc-minis': { value: minis }, '.cyc-save': { innerHTML: '' } };
  const el = (cls) => els[cls] || null;
  const boxes = ['a', 'b'].map((acct) => ({ checked: ticked.includes(acct), dataset: { acct } }));
  const c = vm.createContext({
    ST: { strategies: { lab_x: { cfg: { kind: 'lab' } }, nq930: { cfg: { kind: 'straddle' } } },
          accounts, book, groups: cyc ? { g1: cyc } : {} },
    DEMO: false, FREEZE: false,
    groupOf: (id) => (group ? { id, ...group } : null),
    labSafe: (f, d) => { try { return f(); } catch (_) { return d; } },
    DeskLab: { refusalText: (r) => (r && r.detail) || 'refused' },
    document: { querySelector: () => ({ querySelector: el, querySelectorAll: (sel) => (sel === '.cyc-acct' ? boxes : []) }) },
    jsArg: (v) => JSON.stringify(v),
    acctShort: (id) => id.toUpperCase(),
    stratLabel: (n) => n,
    isDemoAcct: (a) => (liveSet ? !liveSet.includes(a) : !live),
    isRealAcct: (a) => (liveSet ? liveSet.includes(a) : live),
    machineWords: () => ({ server: 'on the SERVER · Chicago', mac: 'on this Mac' })[machine] || '',
    switchBounced: () => false,
    confirmDlg: async (title, body) => { asked.push(body); titles.push(title); return yes; },
    post: async (url, body) => { sent.push([url, body]); return reply || { ok: true, ...body }; },
    refresh: () => refreshes.push(1),
    toast: (m) => toasts.push(m),
    answerWhy: (r) => (r && r.ok ? '' : 'the desk refused it'),
  });
  vm.runInContext(ESC + CODE + '\nglobalThis.cycleHtml = cycleHtml; globalThis.setCycle = setCycle; globalThis.bookCycle = bookCycle; globalThis.syncCycle = syncCycle;' +
    ' globalThis.saveCycle = saveCycle; globalThis.cycleEdit = cycleEdit; globalThis.draft = () => CYC_DRAFT;', c);
  return { c, sent, toasts, asked, titles, els, boxes, refreshes };
}

test('off: a switch, every account to tick, no next account', () => {
  const { c } = ctx();
  const h = c.cycleHtml({ id: 'g1', members: ['lab_x', 'nq930'] });
  assert.match(h, /Account group/);
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
  assert.match(h, /Account group/);
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
  assert.match(r.asked[0], /Add lab_x to the apex 300k account group/) && assert.equal(r.posts.length, 0);
  r = await run(true, on);
  assert.deepEqual(JSON.parse(JSON.stringify(r.posts)), [['move', { strategy: 'lab_x', group: 'g4' }]]);
  r = await run(true, null);                                         // no cycle: no question
  assert.equal(r.asked.length, 0) && assert.equal(r.posts.length, 1);
});

// ---- WP1.2: one Save button (old → new); asks only when an ON cycle on a LIVE account sizes up or ticks a LIVE account in ----
const G = { id: 'g1', members: ['lab_x'] };
const LIVE_ON = { on: true, next: 'a', accounts: ['a'], members: ['lab_x'], risk_usd: 1000, max_minis: 17 };
const OLD_BODY = (risk, minis, accounts) => `{"id":"g1","name":"Apex","members":["lab_x"],"accounts":${JSON.stringify(accounts)},"risk_usd":${risk},"max_minis":${minis}}`;

test('1.2: risk, Most and the ticks no longer save by themselves; each tick says LIVE / DEMO / PAPER', () => {
  const { c } = ctx({ cyc: LIVE_ON, liveSet: ['a'], accounts: { a: { env: 'live' }, b: { env: 'demo' }, p: { env: 'paper' } } });
  const h = c.cycleHtml(G);
  assert.doesNotMatch(h, /onchange="[^"]*saveCycle|onblur="[^"]*saveCycle/, 'no save on change or blur');
  assert.equal((h.match(/oninput="cycleEdit\(&quot;g1&quot;\)"/g) || []).length, 3);   // risk, Most, lab_x's own risk
  assert.equal((h.match(/onchange="cycleEdit\(&quot;g1&quot;\)"/g) || []).length, 3);
  assert.match(h, /A <span class="tag-live">LIVE<\/span>/);
  assert.match(h, /B <span class="tag">DEMO<\/span>/);
  assert.match(h, /P <span class="tag-paper">PAPER<\/span>/);
  assert.match(h, /onfocus="FREEZE=true" onblur="FREEZE=false"/, 'typing still holds the 2.5 s repaint');
  assert.doesNotMatch(h, /Save:/, 'nothing changed: no Save button');
});

test('1.2: the Save button appears only when a value differs, reading old → new', () => {
  const { c, els, boxes } = ctx({ cyc: LIVE_ON, risk: '1,500', minis: '20', ticked: ['a', 'b'] });
  c.cycleEdit('g1');
  assert.equal(els['.cyc-save'].innerHTML.match(/>Save: (.*)<\/button>/)[1], 'Risk $1,000 → $1,500 · Most 17 → 20 · +B');
  assert.match(els['.cyc-save'].innerHTML, /onclick="FREEZE=false;saveCycle\(&quot;g1&quot;\)"/);
  els['.cyc-risk'].value = '1000'; els['.cyc-minis'].value = '17'; boxes[1].checked = false;   // typed back to what the desk has
  c.cycleEdit('g1');
  assert.equal(els['.cyc-save'].innerHTML, '', 'no difference: no button');
  assert.equal(c.draft().g1, undefined);
});

test('1.2: a half-typed value survives a repaint, and the Save button comes back with it', () => {
  const { c } = ctx({ cyc: LIVE_ON, risk: '15', ticked: ['a'] });
  c.cycleEdit('g1');
  const h = c.cycleHtml(G);                                  // the next 2.5 s render rebuilds the card
  assert.match(h, /class="cyc-risk"[^>]*value="15"/);
  assert.match(h, /Save: Risk \$1,000 → \$15</);
});

test('1.2: an ON cycle on a LIVE account asks for risk $1,000 → $1,500, naming LIVE, the machine and old → new; the body is the old one byte for byte', async () => {
  const { c, sent, asked, titles } = ctx({ cyc: LIVE_ON, live: true, risk: '1,500', ticked: ['a'] });
  await c.saveCycle('g1');
  assert.equal(asked.length, 1);
  assert.match(titles[0], /LIVE/);
  assert.match(asked[0], /Risk \$1,000 → \$1,500/);
  assert.match(asked[0], /1 LIVE account on the SERVER · Chicago/);
  assert.equal(sent.length, 1);
  assert.equal(sent[0][0], '/api/groups');
  assert.equal(JSON.stringify(sent[0][1]), OLD_BODY(1500, 17, ['a']));
});

test('1.2: a no at the question sends nothing and keeps what was typed', async () => {
  const { c, sent } = ctx({ cyc: LIVE_ON, live: true, risk: '1500', yes: false });
  c.cycleEdit('g1');
  await c.saveCycle('g1');
  assert.equal(sent.length, 0);
  assert.equal(c.draft().g1.risk, '1500');
});

test('1.2: lowering risk $1,500 → $1,000, lowering Most and unticking save at once, no question', async () => {
  for (const [risk, minis, ticked] of [['1000', '17', ['a', 'b']], ['1500', '10', ['a', 'b']], ['1500', '17', ['a']]]) {
    const cyc = { ...LIVE_ON, accounts: ['a', 'b'], risk_usd: 1500 };
    const { c, sent, asked } = ctx({ cyc, live: true, risk, minis, ticked });
    await c.saveCycle('g1');
    assert.equal(asked.length, 0, `${risk}/${minis}/${ticked}`);
    assert.equal(JSON.stringify(sent[0][1]), OLD_BODY(+risk, +minis, ticked));
  }
});

test('1.2: no question when the cycle is OFF, or ON on demo/paper accounts only', async () => {
  for (const o of [{ cyc: { ...LIVE_ON, on: false }, live: true }, { cyc: LIVE_ON, live: false }]) {
    const { c, sent, asked } = ctx({ ...o, risk: '5000', minis: '30', ticked: ['a', 'b'] });
    await c.saveCycle('g1');
    assert.equal(asked.length, 0);
    assert.equal(JSON.stringify(sent[0][1]), OLD_BODY(5000, 30, ['a', 'b']));
  }
});

test('1.2: Most up asks; a LIVE account ticked in asks; a demo account ticked in does not', async () => {
  let r = ctx({ cyc: LIVE_ON, live: true, minis: '20' });
  await r.c.saveCycle('g1');
  assert.match(r.asked[0], /Most 17 → 20/);
  r = ctx({ cyc: LIVE_ON, liveSet: ['a', 'b'], ticked: ['a', 'b'] });
  await r.c.saveCycle('g1');
  assert.match(r.asked[0], /LIVE account ticked in: B/);
  r = ctx({ cyc: LIVE_ON, liveSet: ['a'], ticked: ['a', 'b'] });
  await r.c.saveCycle('g1');
  assert.equal(r.asked.length, 0);
  assert.equal(r.sent.length, 1);
});

test('1.2: risk to 0 (each strategy\'s own size) counts as going up', async () => {
  const { c, asked } = ctx({ cyc: LIVE_ON, live: true, risk: '0' });
  await c.saveCycle('g1');
  assert.match(asked[0], /Risk \$1,000 → \$0/);
});

test('1.2: a saved change clears the draft; a refused one keeps it', async () => {
  const ok = ctx({ cyc: { ...LIVE_ON, on: false }, risk: '1200' });
  ok.c.cycleEdit('g1');
  await ok.c.saveCycle('g1');
  assert.equal(ok.c.draft().g1, undefined);
  const no = ctx({ cyc: { ...LIVE_ON, on: false }, risk: '1200', reply: { ok: false, detail: 'nope' } });
  no.c.cycleEdit('g1');
  await no.c.saveCycle('g1');
  assert.equal(no.c.draft().g1.risk, '1200');
  assert.match(no.toasts[0], /NOT changed/);
});

test('1.2: the switch keeps its own questions; saveCycle never adds one on ON/OFF', async () => {
  const { c, asked, sent } = ctx({ cyc: LIVE_ON, live: true });
  await c.setCycle('g1', false);                          // OFF: no copies booked -> no question at all
  assert.equal(asked.length, 0);
  assert.equal(JSON.stringify(sent[0][1]), OLD_BODY(1000, 17, ['a']).replace(/}$/, ',"on":false}'));
});

test('1.2: OFF with a draft sends the desk\'s own values, not the draft, and keeps the draft', async () => {
  const { c, asked, sent } = ctx({ cyc: LIVE_ON, live: true, risk: '5000', minis: '40', ticked: ['a', 'b'] });
  c.cycleEdit('g1');
  await c.setCycle('g1', false);
  assert.equal(asked.length, 0);
  assert.equal(JSON.stringify(sent[0][1]), OLD_BODY(1000, 17, ['a']).replace(/}$/, ',"on":false}'));
  assert.equal(c.draft().g1.risk, '5000');
});

test('1.2: ON with a draft (Most 17 → 40) sends nothing and says Save first; the draft stays', async () => {
  const { c, asked, sent, toasts } = ctx({ cyc: { ...LIVE_ON, on: false }, live: true, minis: '40' });
  c.cycleEdit('g1');
  await c.setCycle('g1', true);
  assert.equal(sent.length, 0);
  assert.equal(asked.length, 0);
  assert.match(toasts[0], /Save or undo your changes first/);
  assert.equal(c.draft().g1.minis, '40');
});

test('1.2: a new cycle\'s Start question names Most too', async () => {
  const { c, asked, sent } = ctx({ live: true, minis: '40' });
  await c.setCycle('g1', true);
  assert.match(asked[0], /\$1,000 at risk, at most 40 full contracts/);
  assert.equal(sent[0][1].max_minis, 40);
});

test('1.2: a cycle still holding an account the Desk removed switches OFF and ON with the page\'s ticks, never the removed one', async () => {
  const STALE = { ...LIVE_ON, accounts: ['a', 'gone'] };              // removing an account never takes it out of a cycle
  const BODY = (on) => OLD_BODY(1000, 17, ['a']).replace(/}$/, `,"on":${on}}`);
  for (const on of [false, true]) {
    const { c, sent, toasts } = ctx({ cyc: { ...STALE, on: !on }, ticked: ['a'] });
    await c.setCycle('g1', on);
    assert.equal(JSON.stringify(sent[0][1]), BODY(on), `switch ${on ? 'ON' : 'OFF'}`);
    assert.doesNotMatch(toasts.join(' '), /Save or undo/);
  }
  const d = ctx({ cyc: STALE, risk: '5000', ticked: ['a'] });         // OFF with a draft: the desk's values, the removed one left out
  d.c.cycleEdit('g1');
  await d.c.setCycle('g1', false);
  assert.equal(JSON.stringify(d.sent[0][1]), BODY(false));
  const n = ctx({ cyc: { ...STALE, on: false }, risk: '5000', ticked: ['a'] });   // ON with a draft: Save first, and the Save is there
  n.c.cycleEdit('g1');
  await n.c.setCycle('g1', true);
  assert.equal(n.sent.length, 0);
  assert.match(n.toasts[0], /Save or undo/);
  assert.match(n.c.cycleHtml(G), /Save: Risk \$1,000 → \$5,000/);
});

test('A: an account the saved cycle lists but the Desk removed is never "gone" in the Save diff: typing a field back leaves no draft', async () => {
  const STALE = { ...LIVE_ON, accounts: ['a', 'gone'] };
  const { c, els, sent } = ctx({ cyc: STALE, risk: '1500', ticked: ['a'] });
  c.cycleEdit('g1');
  assert.equal(els['.cyc-save'].innerHTML.match(/>Save: (.*)<\/button>/)[1], 'Risk $1,000 → $1,500', 'no "−GONE" beside the real change');
  els['.cyc-risk'].value = '1000';                                    // typed back to what the desk has
  c.cycleEdit('g1');
  assert.equal(els['.cyc-save'].innerHTML, '', 'no Save button left');
  assert.equal(c.draft().g1, undefined, 'no draft left');
  els['.cyc-risk'].value = '1500';
  await c.saveCycle('g1');                                            // pressing Save: the same body as before
  assert.equal(JSON.stringify(sent[0][1]), OLD_BODY(1500, 17, ['a']));
});

test('book-all keeps every booked row\'s own settings: size, risk, stop after, Most (final review I-1)', async () => {
  const set = { account: 'a', qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win', most: 4 };
  const { c, sent } = ctx({ cyc: ON, book: { lab_x: [set] } });
  await c.bookCycle('g1');
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), [['/api/book', { strategy: 'lab_x', assignments: [set, { account: 'b', qty: 1 }] }]]);
});

/* Per-strategy risk (owner, 2026-10-30): each strategy of the cycle has its own risk box; empty = the cycle's risk. */
test('a strategy\'s own risk: a box per strategy, shown when set, sent in risk_by', async () => {
  const cyc = { on: false, accounts: ['a'], members: ['lab_x'], risk_usd: 2000, risk_by: { lab_x: 1500 }, max_minis: 17 };
  const t = ctx({ cyc, risk: '2000', ticked: ['a'] });
  const h = t.c.cycleHtml({ id: 'g1', members: ['lab_x', 'nq930'] });
  assert.match(h, /class="cyc-risk-m" data-m="lab_x"/);
  assert.match(h, /value="1500"/);
  assert.equal((h.match(/cyc-risk-m/g) || []).length, 1);          // Lab strategies only
  const box = { value: '2500', dataset: { m: 'lab_x' } };
  t.c.document.querySelector = () => ({ querySelector: (cls) => t.els[cls] || null,
    querySelectorAll: (sel) => (sel === '.cyc-risk-m' ? [box] : sel === '.cyc-acct' ? t.boxes : []) });
  t.c.cycleEdit('g1');
  assert.match(t.els['.cyc-save'].innerHTML, /lab_x \$1,500 → \$2,500/);
  await t.c.saveCycle('g1');
  assert.deepEqual(JSON.parse(JSON.stringify(t.sent.at(-1)[1].risk_by)), { lab_x: 2500 });
  box.value = '';                                                    // emptied: back to the cycle's risk
  t.c.cycleEdit('g1');
  assert.match(t.els['.cyc-save'].innerHTML, /lab_x \$1,500 → \$2,000/);
});

// ---- modes (owner, 2026-10-30): take turns, every account, or one strategy per account -------------------------------
test('modes: the card picks a mode; one-per-account shows an account box per strategy from the ticked accounts', () => {
  const split = { ...LIVE_ON, accounts: ['a', 'b'], mode: 'split', assign: { lab_x: 'b' }, next: null };
  const h = ctx({ cyc: split, ticked: ['a', 'b'] }).c.cycleHtml(G);
  assert.match(h, /<option value="split" selected>One strategy per account<\/option>/);
  assert.match(h, /class="cyc-assign" data-m="lab_x"[\s\S]*?<option value="b" selected>B<\/option>/);
  assert.match(h, /lab_x is not booked on B/);
  assert.match(h, /Book each strategy on its account/);
  const cyc = ctx({ cyc: LIVE_ON }).c.cycleHtml(G);
  assert.match(cyc, /<option value="cycle" selected>/);
  assert.doesNotMatch(cyc, /cyc-assign/, 'take turns: no account per strategy');
});

test('modes: a changed mode and account read old → new on Save and go in the body', async () => {
  const t = ctx({ cyc: { ...LIVE_ON, accounts: ['a', 'b'] }, ticked: ['a', 'b'] });
  t.els['.cyc-mode'] = { value: 'split' };
  const sel = { value: 'b', dataset: { m: 'lab_x' } };
  t.c.document.querySelector = () => ({ querySelector: (cls) => t.els[cls] || null,
    querySelectorAll: (s) => (s === '.cyc-acct' ? t.boxes : s === '.cyc-assign' ? [sel] : []) });
  t.c.cycleEdit('g1');
  assert.equal(t.els['.cyc-save'].innerHTML.match(/>Save: (.*)<\/button>/)[1],
    'Take turns: one account a trade → One strategy per account · lab_x on no account → B');
  await t.c.saveCycle('g1');
  const b = JSON.parse(JSON.stringify(t.sent.at(-1)[1]));
  assert.equal(b.mode, 'split');
  assert.deepEqual(b.assign, { lab_x: 'b' });
});

test('modes: going to every account counts as sizing up on a LIVE cycle (asks first)', async () => {
  const t = ctx({ cyc: LIVE_ON, live: true });
  t.els['.cyc-mode'] = { value: 'share' };
  await t.c.saveCycle('g1');
  assert.equal(t.asked.length, 1);
  assert.match(t.asked[0], /Every account takes every trade/);
});

test('modes: in one-per-account, book only each strategy\'s own account', async () => {
  const t = ctx({ cyc: { ...LIVE_ON, accounts: ['a', 'b'], mode: 'split', assign: { lab_x: 'b' } }, book: { lab_x: [] } });
  await t.c.bookCycle('g1');
  assert.deepEqual(JSON.parse(JSON.stringify(t.sent.map(x => x[1]))), [{ strategy: 'lab_x', assignments: [{ account: 'b', qty: 1 }] }]);
});

test('modes: one-per-account shows one row per account with its strategy, size and booking; the heading follows the mode', () => {
  const split = { ...LIVE_ON, accounts: ['a', 'b'], mode: 'split', assign: { lab_x: 'b' }, risk_by: { lab_x: 2000 }, next: null };
  const h = ctx({ cyc: split, ticked: ['a', 'b'] }).c.cycleHtml(G);
  assert.match(h, /<h2>One strategy per account<\/h2>/);
  assert.match(h, /A[\s\S]*?no strategy[\s\S]*?B[\s\S]*?<b>lab_x<\/b> · \$2,000 a trade · <span class="neg">not booked<\/span>/);
  assert.match(ctx({ cyc: LIVE_ON }).c.cycleHtml(G), /<h2>Account cycle<\/h2>/);
});
