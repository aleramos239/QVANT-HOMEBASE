import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) paper-account block (2026-09-27 Task 2b), run for real in a
   sandbox: the rows, the Remove confirm, the create call -- every request goes to the CHART service (:8852), never
   the desk's own API, and a user-given name is always escaped. Nothing is sent anywhere: fetch is recorded. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const BLOCK = HTML.slice(HTML.indexOf('/* ---- paper accounts (2026-09-27 Task 2b)'),
  HTML.indexOf('/* ---- Settings (2026-09-27 desk-settings plan)'));

function load({ confirm = true, answers = {} } = {}) {
  const els = {}, fetched = [], toasts = [], confirms = [];
  const el = (id) => (els[id] ||= { innerHTML: '', value: '', textContent: '', style: {}, disabled: false, focus() {} });
  const ctx = vm.createContext({
    location: { protocol: 'http:', hostname: 'localhost' }, DEMO: false, console,
    $: (sel) => el(sel.replace(/^#/, '')),
    toast: (t) => toasts.push(t),
    confirmDlg: async (title, body, action, destructive) => { confirms.push({ title, body, action, destructive }); return confirm; },
    closeAccts() {}, closeConnect() {},
    usd: (v) => '$' + v,
    fetch: async (url, opts) => {
      fetched.push({ url, opts });
      const a = answers[url] || { ok: true, accounts: [] };
      return { ok: true, status: 200, json: async () => a };
    },
  });
  vm.runInContext(BLOCK + '\nglobalThis.api = { loadPaper, removePaper, addPaper, wizPaper, esc, get PAPER() { return PAPER; } };', ctx);
  return { api: ctx.api, els, fetched, toasts, confirms };
}

const LIST = { ok: true, accounts: [
  { id: 'paper', label: 'PAPER', env: 'paper', balance: 50000, realized_pnl: 0, removable: false },
  { id: 'paper-2', label: '<img src=x onerror=alert(1)>', env: 'paper', balance: 25000, realized_pnl: -12.5, removable: true }] };

test('the accounts popup lists every paper account with its PAPER chip and balance; names are escaped', async () => {
  const { api, els, fetched } = load({ answers: { 'http://localhost:8852/api/paper/accounts': LIST } });
  await api.loadPaper();
  assert.equal(fetched[0].url, 'http://localhost:8852/api/paper/accounts');
  const html = els.paperList.innerHTML;
  assert.equal((html.match(/class="acct paper-row"/g) || []).length, 2);
  assert.equal((html.match(/>PAPER<\/span>/g) || []).length, 2 + 1);           // two chips + the built-in's name
  assert.match(html, /\$25000/);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.equal((html.match(/data-paper-id="paper-2"/g) || []).length, 1, 'only a user-made account has a Remove');
  assert.doesNotMatch(html, /onclick=/, 'no inline handler carries an id');
});

test('a row whose id is not a paper id is never rendered (a hostile answer cannot reach a button)', async () => {
  const evil = { ok: true, accounts: [{ id: "x');alert(1)//", label: 'e', balance: 1, realized_pnl: 0, removable: true },
    { id: 'paper-4', label: 'ok', balance: 1, realized_pnl: 0, removable: true }], broken: 'registry unreadable' };
  const { api, els } = load({ answers: { 'http://localhost:8852/api/paper/accounts': evil } });
  await api.loadPaper();
  assert.deepEqual(api.PAPER.map((a) => a.id), ['paper-4']);
  assert.doesNotMatch(els.paperList.innerHTML, /alert/);
  assert.match(els.paperList.innerHTML, /registry unreadable/);
});

test('Remove asks through the in-page confirm, then posts to the chart service', async () => {
  const s = load({ answers: { 'http://localhost:8852/api/paper/accounts': LIST } });
  await s.api.loadPaper();
  await s.api.removePaper('paper-2');
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].destructive, true);
  assert.match(s.confirms[0].body, /flatten it first/);
  const post = s.fetched.find((f) => f.opts && f.opts.method === 'POST');
  assert.equal(post.url, 'http://localhost:8852/api/paper/accounts/remove');
  assert.deepEqual(JSON.parse(post.opts.body), { account: 'paper-2' });
  const no = load({ confirm: false, answers: { 'http://localhost:8852/api/paper/accounts': LIST } });
  await no.api.loadPaper();
  await no.api.removePaper('paper-2');
  assert.equal(no.fetched.filter((f) => f.opts && f.opts.method === 'POST').length, 0, 'Cancel sends nothing');
});

test('Add paper account posts a name and a starting balance to the chart service, never the desk', async () => {
  const s = load({ answers: { 'http://localhost:8852/api/paper/accounts/create': { ok: true, account: { id: 'paper-3', label: 'Swing' } } } });
  s.api.wizPaper();
  s.els.pName.value = ''; await s.api.addPaper();
  assert.equal(s.fetched.length, 0);
  assert.match(s.els.pErr.textContent, /name/);
  s.els.pName.value = ' Swing '; s.els.pBal.value = '$30,000';
  await s.api.addPaper();
  const post = s.fetched[0];
  assert.equal(post.url, 'http://localhost:8852/api/paper/accounts/create');
  assert.deepEqual(JSON.parse(post.opts.body), { name: 'Swing', start_balance: 30000 });
  assert.ok(s.toasts.some((t) => t.includes('Swing')));
  for (const f of s.fetched) assert.ok(f.url.startsWith('http://localhost:8852/api/paper/'), f.url);
});

test('the desk page\'s paper code never calls the desk\'s own API, and uses no native dialog', () => {
  assert.doesNotMatch(BLOCK, /post\("\/api\//);
  assert.doesNotMatch(BLOCK, /fetch\("\/api/);
  assert.doesNotMatch(BLOCK, /\b(alert|prompt|confirm)\(/);
  assert.match(HTML, /id="optPaper" onclick="wizPaper\(\)"/);
  assert.match(HTML, /<div id="paperList"><\/div>/);
});
