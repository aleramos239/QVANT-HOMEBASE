// Task 11 (Desk makeover): teams on the page come from the Desk (ST.groups); new, rename, move and delete go through /api/setup and /api/groups/delete.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

const read = (f) => readFileSync(new URL('../../homebase/static/desk/' + f, import.meta.url), 'utf8');
const slice = (s, a, b) => s.slice(s.indexOf(a), s.indexOf(b));
const POPUPS = read('popups.js'), GROUPS = read('groups.js');

function load({ answer = { ok: true }, confirm = true, enabled = false, accounts = ['x1'] } = {}) {
  const confirms = [];
  const posts = [], toasts = [], els = {};
  const el = (id) => (els[id] = els[id] || { value: '', textContent: '', innerHTML: '', focus() {}, classList: { contains: () => true } });
  const ctx = vm.createContext({
    console, VIEW: { k: 'today' }, document: { activeElement: null },
    $: (sel) => el(sel.replace(/^#/, '')),
    esc: (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    jsArg: (v) => JSON.stringify(String(v)), toast: (t) => toasts.push(t), confirmDlg: async (t) => { confirms.push(t); return confirm; },
    post: async (url, body) => { posts.push([url, JSON.parse(JSON.stringify(body))]); return typeof answer === 'function' ? answer(url, body) : answer; },
    answerWhy: (r) => (r && r.ok === true ? '' : `the desk refused it: ${r && r.detail}`),
    refresh: async () => {}, archivedBuiltins: () => [], labSafe: (f, d) => { try { return f(); } catch (_) { return d; } },
    stratLabel: (n) => n, labOnDesk: () => false, DESKLAB: { strategies: [] }, DeskLab: { NO_GROUP: 'No team' },
    cycleCopies: () => [], isRealAcct: (a) => a === 'real', cycleLive: () => '', showOverlay() {}, hideOverlay() {},
    ST: { strategies: { a: { cfg: { kind: 'lab', enabled } }, b: { cfg: { kind: 'lab', enabled: false } } }, groups: {
      g1: { name: 'Apex', members: ['a'], accounts, mode: 'share', risk_usd: 500, max_minis: 4, on: true },
      g2: { name: 'Lucid', members: [], accounts: [], mode: 'cycle', on: false } } },
  });
  vm.runInContext(slice(GROUPS, 'const teams =', 'async function loadDeskGroupRes') + slice(GROUPS, 'function cycleMembers', 'let CYC_DRAFT') + slice(GROUPS, 'const teamOn', 'const teamWant') + slice(GROUPS, 'const teamBody', "/* A group's page") +
    slice(POPUPS, 'function renderGroupMgr', '$("#groupOverlay").addEventListener'), ctx);
  return { ctx, confirms, posts, toasts, els, run: (code) => vm.runInContext(code, ctx) };
}

test('teams() reads only ST.groups', () => {
  const t = load();
  assert.deepEqual(JSON.parse(JSON.stringify(t.run('teams()'))), [{ id: 'g1', name: 'Apex', members: ['a'] }, { id: 'g2', name: 'Lucid', members: [] }]);
  assert.equal(t.run('groupOf("g9")'), null);
});

test('a new team posts one /api/setup with team "" and an empty body', async () => {
  const t = load();
  await t.run('addGroup("Apex")');
  assert.deepEqual(t.posts, [['/api/setup', { team: '', name: 'Apex', members: [], accounts: [], mode: 'cycle', on: false }]]);
});

test('rename sends the team\'s whole body; move adds to the new team in one call', async () => {
  const t = load();
  await t.run('renameGroup("g1", " Apex 2 ")');
  assert.deepEqual(t.posts[0], ['/api/setup', { team: 'g1', name: 'Apex 2', members: ['a'], accounts: ['x1'], mode: 'share', risk_usd: 500, max_minis: 4, on: false }]);
  t.posts.length = 0;
  await t.run('moveToGroup("b", "g2")');
  assert.deepEqual(t.posts, [['/api/setup', { team: 'g2', name: 'Lucid', members: ['b'], accounts: [], mode: 'cycle', on: false }]]);
  t.posts.length = 0;
  await t.run('moveToGroup("a", "")');
  assert.deepEqual(t.posts, [['/api/setup', { team: 'g1', name: 'Apex', members: [], accounts: ['x1'], mode: 'share', risk_usd: 500, max_minis: 4, on: false }]]);
});

test('delete goes to the Desk; a refusal shows the Desk\'s words and changes nothing here', async () => {
  const t = load();
  await t.run('teamDelete("g2")');
  assert.deepEqual(t.posts, [['/api/groups/delete', { id: 'g2' }]]);
  const r = load({ answer: { detail: 'It is in the set X.' } });
  assert.equal(await r.run('moveToGroup("b", "g2")'), undefined);
  assert.match(r.toasts[0], /It is in the set X\./);
  assert.deepEqual(JSON.parse(JSON.stringify(r.ctx.ST.groups.g2.members)), []);
});

test('the team manager has no kind, no family column, no orphans block', () => {
  const t = load();
  t.run('renderGroupMgr(true)');
  const html = t.els.groupList.innerHTML;
  assert.match(html, /Apex/);
  assert.doesNotMatch(html, /kind|family|Remove|orphan|no group/i);
  assert.doesNotMatch(POPUPS, /removeOrphanCycle/);
});

test('rename posts on from the members\' Trading state, never the team\'s own on', async () => {
  const off = load();                       // g1.on is true on the Desk (it has strategies and accounts), its member is OFF
  await off.run('renameGroup("g1", "Apex 2")');
  assert.equal(off.posts[0][1].on, false);
  const on = load({ enabled: true });
  await on.run('renameGroup("g1", "Apex 2")');
  assert.equal(on.posts[0][1].on, true);
});

test('a move into an ON team with a real account asks first; no posts when the owner says no', async () => {
  const no = load({ enabled: true, accounts: ['real'], confirm: false });
  await no.run('moveToGroup("b", "g1")');
  assert.deepEqual(no.confirms, ['Start trading?']);
  assert.deepEqual(no.posts, []);
  const yes = load({ enabled: true, accounts: ['real'] });
  await yes.run('moveToGroup("b", "g1")');
  assert.equal(yes.posts.length, 1);
  const off = load({ accounts: ['real'] });  // team OFF: no ask
  await off.run('moveToGroup("b", "g1")');
  assert.deepEqual(off.confirms, []);
  assert.equal(off.posts[0][1].on, false);
});

test('a mixed team (one ON, one OFF): rename and move post on: null, so nobody is switched', async () => {
  const t = load({ enabled: true });
  t.run('ST.groups.g1.members = ["a", "b"]');                 // a ON, b OFF
  await t.run('renameGroup("g1", "Apex 2")');
  assert.equal(t.posts[0][1].on, null);
  t.posts.length = 0;
  await t.run('moveToGroup("a", "")');
  assert.equal(t.posts[0][1].on, null);
});
