import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) book block -- + Assign (pickAsg) and the
   inline size edit (editQty) -- run for real in a vm sandbox (the deskpaper / desksettings
   technique). 2026-09-28, Apple-design audit S3: booking a LIVE account onto a strategy asks
   first, with the page's own confirm dialog; a demo account books at once, exactly as before;
   Cancel sends nothing. Raising a live booking's size asks too -- only from Enter: a blur reverts
   it without a dialog (review M2); lowering it never asks. "Book live" is never Kill's red. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const BLOCK = HTML.slice(
  HTML.indexOf('/* ---- the book (assignments) ---- */'),
  HTML.indexOf('/* ---- connect wizard ---- */'));
// the page's own name helper (a strategy's label, else its id), defined above this block
const LABEL = HTML.slice(HTML.indexOf('const stratLabel = '), HTML.indexOf('const actStrat = '));

async function tick(n = 12) { for (let i = 0; i < n; i++) await Promise.resolve(); }
const plain = (v) => JSON.parse(JSON.stringify(v));

const ACCOUNTS = {
  '1234567885': { label: '1234567885', env: 'live' },
  apex2941870000048: { label: 'APEX2941870000048', env: 'live' },
  'lucid-eval-1': { label: 'Lucid Eval #1', env: 'demo' },
};
const STRATS = {
  nq930_1030: { cfg: { symbol: 'NQ', qty: 3, enabled: true, self_fire: true, kind: 'straddle' } },
  bars_test: { cfg: { symbol: 'NQ', qty: 1, enabled: true, self_fire: true, kind: 'bars' } },
  gc_pine: { cfg: { symbol: 'GC', qty: 1, enabled: true, self_fire: false, kind: 'straddle' } },
  shadowy: { cfg: { symbol: 'NQ', qty: 1, enabled: true, shadow: true, kind: 'bars' } },
};

function load({ armed = true, confirm = true, book = {}, strategies = STRATS, accounts = ACCOUNTS } = {}) {
  const posts = [], toasts = [], confirms = [], refreshes = [];
  let answer;   // a pending confirm the test can resolve later (confirm === 'later')
  const menus = [{ hidden: false }];
  const qedit = { value: '', listeners: {}, focus() {}, select() {}, blur() { for (const f of this.listeners.blur || []) f(); },
    addEventListener(t, f) { (this.listeners[t] ||= []).push(f); } };
  const ctx = vm.createContext({
    console,
    ST: { armed, accounts: plain(accounts), book: plain(book), strategies: plain(strategies) },
    $: (sel) => (sel === '#qedit' ? qedit : null),
    document: { addEventListener() {}, querySelectorAll: (sel) => (sel === '.amenu' ? menus : []), getElementById: () => null },
    toast: (t) => toasts.push(t),
    confirmDlg: (title, body, action, destructive) => {
      confirms.push({ title, body, action, destructive });
      return confirm === 'later' ? new Promise((res) => { answer = res; }) : Promise.resolve(confirm);
    },
    post: async (url, body) => { posts.push({ url, body }); return { ok: true }; },
    refresh: () => refreshes.push(true),
  });
  vm.runInContext(LABEL + BLOCK + `
    globalThis.api = { pickAsg, editQty, acctShort, isDemoAcct, liveBookingNote,
      get ST() { return ST; }, get FREEZE() { return FREEZE; } };`, ctx);
  return { api: ctx.api, posts, toasts, confirms, refreshes, menus, qedit, answer: (v) => answer(v) };
}

// ---- + Assign ---------------------------------------------------------------------------------
test('booking a LIVE account asks first -- the strategy, the account, the size and what it means', async () => {
  const s = load({ book: { nq930_1030: [{ account: 'lucid-eval-1', qty: 1 }] } });
  await s.api.pickAsg('nq930_1030', '1234567885', 3);
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].title, 'Book NQ930_1030 on …885 LIVE × 3?');
  assert.match(s.confirms[0].body, /^It will trade real money at the next 9:30 fire\./);
  assert.equal(s.confirms[0].action, 'Book live');
  assert.equal(s.confirms[0].destructive, false, 'the neutral primary button -- never styled like Kill (review M2)');
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: 'lucid-eval-1', qty: 1 }, { account: '1234567885', qty: 3 }] } }]);
});

test('booking a DEMO account never asks and sends exactly what it always did', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 2 }] } });
  const p = s.api.pickAsg('nq930_1030', 'lucid-eval-1', 3);
  assert.equal(s.posts.length, 1, 'sent synchronously, no dialog in front of it');
  await p;
  assert.equal(s.confirms.length, 0);
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: '1234567885', qty: 2 }, { account: 'lucid-eval-1', qty: 3 }] } }]);
});

test('Cancel on a live booking sends nothing (the menu closes and the page repaints)', async () => {
  const s = load({ confirm: false });
  await s.api.pickAsg('nq930_1030', '1234567885', 3);
  assert.equal(s.confirms.length, 1);
  assert.deepEqual(s.posts, []);
  assert.equal(s.refreshes.length, 1);
  assert.equal(s.menus[0].hidden, true);
  assert.equal(s.api.FREEZE, false);
});

test('an account the desk does not list is treated as LIVE: it asks (fail closed)', async () => {
  const s = load({ confirm: false });
  await s.api.pickAsg('nq930_1030', 'ghost-777', 1);
  assert.equal(s.confirms.length, 1);
  assert.match(s.confirms[0].body, /not in the desk's list/);
  assert.deepEqual(s.posts, []);
});

test('the rest of the book is read after the answer -- a row removed meanwhile is never written back', async () => {
  const s = load({ confirm: 'later', book: { nq930_1030: [{ account: 'lucid-eval-1', qty: 1 }, { account: 'apex2941870000048', qty: 2 }] } });
  const p = s.api.pickAsg('nq930_1030', '1234567885', 3);
  await tick();
  s.api.ST.book.nq930_1030 = [{ account: 'lucid-eval-1', qty: 1 }];   // another window unbooked APEX…048
  s.answer(true);
  await p;
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: 'lucid-eval-1', qty: 1 }, { account: '1234567885', qty: 3 }] } }]);
});

test('the dialog says when nothing trades yet, and names the moment it will', () => {
  const off = load({ armed: false, strategies: { ...STRATS, nq930_1030: { cfg: { ...STRATS.nq930_1030.cfg, enabled: false } } } });
  assert.match(off.api.liveBookingNote('nq930_1030', '1234567885'),
    /Right now NQ930_1030 is off and the desk is disarmed, so nothing is placed until that changes\./);
  const s = load();
  assert.match(s.api.liveBookingNote('bars_test', '1234567885'), /on its next signal/);
  assert.match(s.api.liveBookingNote('gc_pine', '1234567885'), /on its next signal/);
  assert.match(s.api.liveBookingNote('shadowy', '1234567885'), /SHADOW strategy/);
  assert.match(s.api.liveBookingNote('nq930_1030', 'apex2941870000048'), /Account APEX2941870000048\./,
    'a shortened name is spelled out in full in the body');
});

test('acctShort: a long numbered name shortens like the chart page, a plain label stays whole', () => {
  const s = load({ accounts: { ...ACCOUNTS, pa: { label: 'PAAPEX2941870000021', env: 'live' },
    sand: { label: 'Tradovate Sandbox', env: 'demo' } } });
  assert.equal(s.api.acctShort('1234567885'), '…885');
  assert.equal(s.api.acctShort('apex2941870000048'), 'APEX…048');
  assert.equal(s.api.acctShort('pa'), 'PAAPEX…021');
  assert.equal(s.api.acctShort('lucid-eval-1'), 'Lucid Eval #1');
  assert.equal(s.api.acctShort('sand'), 'Tradovate Sandbox');
  assert.equal(s.api.acctShort('not-listed'), 'not-listed');
});

// ---- the size edit ------------------------------------------------------------------------------
function editSize(s, strategy, account, from, to, how = 'enter') {
  const span = { outerHTML: '' };
  s.api.editQty({ stopPropagation() {}, currentTarget: span }, strategy, account, from);
  s.qedit.value = String(to);
  if (how === 'enter') {
    const e = { key: 'Enter', repeat: false, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    for (const f of s.qedit.listeners.keydown || []) f(e);
    s.enterEvent = e;
  } else s.qedit.blur();
}

test('raising a LIVE booking\'s size with Enter asks first; the new size is what gets sent', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 5);
  await tick();
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].title, 'Book NQ930_1030 on …885 LIVE × 5 (now × 3)?');
  assert.equal(s.confirms[0].destructive, false);
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: '1234567885', qty: 5 }] } }]);
});

test('Enter never lands on the confirm it opens: its default action is stopped first (review M4)', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 5);
  assert.equal(s.enterEvent.defaultPrevented, true,
    "otherwise the Enter keypress reaches the dialog's focused Cancel and answers it");
  assert.equal(s.confirms.length, 1);
  const rep = { key: 'Enter', repeat: true, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  for (const f of s.qedit.listeners.keydown) f(rep);
  assert.equal(rep.defaultPrevented, true);
  await tick();
  assert.equal(s.confirms.length, 1, 'a held Enter asks once');
  assert.equal(s.posts.length, 1);
});

test('Cancel on a live size raise sends nothing', async () => {
  const s = load({ confirm: false, book: { nq930_1030: [{ account: '1234567885', qty: 3 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 5);
  await tick();
  assert.equal(s.confirms.length, 1);
  assert.deepEqual(s.posts, []);
});

test('a blur on a live raise never opens a dialog: it reverts, says so, and sends nothing (review M2)', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 5, 'blur');   // e.g. the pointer went down on Kill
  await tick();
  assert.equal(s.confirms.length, 0, 'no "Book … LIVE" dialog under the pointer');
  assert.deepEqual(s.posts, []);
  assert.equal(s.refreshes.length, 1, 'the old size is painted back');
  assert.deepEqual(s.toasts, ['NQ930_1030 on …885 stays × 3 — press Enter to raise a LIVE booking.']);
  assert.equal(s.api.FREEZE, false);
});

test('lowering a live size, or any demo size change, never asks and sends as before -- on a blur too', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }, { account: 'lucid-eval-1', qty: 1 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 1, 'blur');
  await tick();
  editSize(s, 'nq930_1030', 'lucid-eval-1', 1, 4, 'blur');
  await tick();
  assert.equal(s.confirms.length, 0);
  assert.equal(s.posts.length, 2);
  assert.deepEqual(plain(s.posts[0].body.assignments), [{ account: '1234567885', qty: 1 }, { account: 'lucid-eval-1', qty: 1 }]);
});

test('one commit per edit: the blur that follows Enter never sends twice, asks twice or reverts', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 5);
  s.qedit.blur();                      // focus moves into the dialog
  await tick();
  assert.equal(s.toasts.length, 0, 'no "stays" toast: the Enter commit owns this edit');
  assert.equal(s.confirms.length, 1);
  assert.equal(s.posts.length, 1);
});
