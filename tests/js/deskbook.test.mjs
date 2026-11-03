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
import { HTML } from './deskpage.mjs';
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
  'paper-1': { label: 'Paper 1', env: 'paper' },
};
const STRATS = {
  nq930_1030: { cfg: { symbol: 'NQ', qty: 3, enabled: true, self_fire: true, kind: 'straddle' } },
  bars_test: { cfg: { symbol: 'NQ', qty: 1, enabled: true, self_fire: true, kind: 'bars' } },
  gc_pine: { cfg: { symbol: 'GC', qty: 1, enabled: true, self_fire: false, kind: 'straddle' } },
  shadowy: { cfg: { symbol: 'NQ', qty: 1, enabled: true, shadow: true, kind: 'bars' } },
};

function load({ armed = true, confirm = true, book = {}, strategies = STRATS, accounts = ACCOUNTS, reply = { ok: true }, machine = '' } = {}) {
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
    post: async (url, body) => { posts.push({ url, body }); return reply; },
    DeskLab: { refusalText: (r) => r.detail, bookedNext: () => false, bookedJoins: () => false },
    refresh: () => refreshes.push(true),
    machineWords: () => machine,        // core.js's one machine reader
    hbClock: (t) => t,                  // the page's clock helper: 24-hour, as these tests read it
  });
  vm.runInContext(LABEL + BLOCK + `
    globalThis.api = { pickAsg, editQty, removeAsg, acctShort, isDemoAcct, liveBookingNote,
      get ST() { return ST; }, get FREEZE() { return FREEZE; } };`, ctx);
  return { api: ctx.api, posts, toasts, confirms, refreshes, menus, qedit, answer: (v) => answer(v) };
}

// ---- + Assign ---------------------------------------------------------------------------------
test('booking a LIVE account asks first -- the strategy, the account, the size and what it means', async () => {
  const s = load({ book: { nq930_1030: [{ account: 'lucid-eval-1', qty: 1 }] } });
  await s.api.pickAsg('nq930_1030', '1234567885', 3);
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].title, 'Book NQ930_1030 on …885 LIVE, qty 3?');
  assert.match(s.confirms[0].body, /^It will trade real money at the next 9:30 fire\./);
  assert.equal(s.confirms[0].action, 'Book live');
  assert.equal(s.confirms[0].destructive, false, 'the neutral primary button -- never styled like Kill (review M2)');
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: 'lucid-eval-1', qty: 1 }, { account: '1234567885', qty: 3 }] } }]);
});

test('booking a PAPER account never asks and sends exactly what it always did', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 2 }] } });
  const p = s.api.pickAsg('nq930_1030', 'paper-1', 3);
  assert.equal(s.posts.length, 1, 'sent synchronously, no dialog in front of it');
  await p;
  assert.equal(s.confirms.length, 0);
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: '1234567885', qty: 2 }, { account: 'paper-1', qty: 3 }] } }]);
});

test('audit 2026-10-27: booking a demo-env account asks too -- a funded prop account is sent as env "demo"', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 2 }] } });
  await s.api.pickAsg('nq930_1030', 'lucid-eval-1', 3);
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].title, 'Book NQ930_1030 on Lucid Eval #1 LIVE, qty 3?');
});

test('Cancel on a live booking sends nothing (the page repaints)', async () => {
  const s = load({ confirm: false });
  await s.api.pickAsg('nq930_1030', '1234567885', 3);
  assert.equal(s.confirms.length, 1);
  assert.deepEqual(s.posts, []);
  assert.equal(s.refreshes.length, 1);
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
    /Right now NQ930_1030 is off and Desk OFF, so nothing is placed until that changes\./);
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
  assert.equal(s.confirms[0].title, 'Book NQ930_1030 on …885 LIVE, qty 3 → 5?');
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

test('lowering a live size, or any paper size change, never asks and sends as before -- on a blur too', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }, { account: 'paper-1', qty: 1 }] } });
  editSize(s, 'nq930_1030', '1234567885', 3, 1, 'blur');
  await tick();
  editSize(s, 'nq930_1030', 'paper-1', 1, 4, 'blur');
  await tick();
  assert.equal(s.confirms.length, 0);
  assert.equal(s.posts.length, 2);
  assert.deepEqual(plain(s.posts[0].body.assignments), [{ account: '1234567885', qty: 1 }, { account: 'paper-1', qty: 1 }]);
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

// ---- unbook (WP1.4) ---------------------------------------------------------------------------
const LAB = { lab_orb: { cfg: { symbol: 'NQ', kind: 'lab', enabled: true },
  lab: { rounds: [{ account: 'apex2941870000048', status: 'live', qty: 1, side: 'buy' }] } } };

test('unbooking a LIVE account never asks: it sends the book without it, as before', async () => {
  const s = load({ book: { nq930_1030: [{ account: '1234567885', qty: 3 }, { account: 'lucid-eval-1', qty: 1 }] } });
  s.api.removeAsg('nq930_1030', '1234567885');
  await tick();
  assert.equal(s.confirms.length, 0);
  assert.deepEqual(plain(s.posts), [{ url: '/api/book', body: { strategy: 'nq930_1030',
    assignments: [{ account: 'lucid-eval-1', qty: 1 }] } }]);
});

test("a Lab strategy's open trade refuses the unbook: the toast names the account and what it holds", async () => {
  const s = load({ strategies: LAB, reply: { ok: false, detail: 'Flatten it first.' },
    book: { lab_orb: [{ account: 'apex2941870000048', qty: 1 }] } });
  s.api.removeAsg('lab_orb', 'apex2941870000048');
  await tick();
  assert.equal(s.confirms.length, 0);
  assert.deepEqual(plain(s.posts[0].body), { strategy: 'lab_orb', assignments: [] });
  assert.deepEqual(s.toasts, ['APEX…048 holds 1 NQ for LAB_ORB: flatten it or wait for the exit first. It stays booked.']);
});

test("any other refusal of a Lab book is the Desk's own sentence, as before", async () => {
  const s = load({ strategies: LAB, reply: { ok: false, detail: 'Set the limits first.' }, book: { lab_orb: [] } });
  await s.api.pickAsg('lab_orb', 'lucid-eval-1', 1);
  await tick();
  assert.deepEqual(s.toasts, ['Set the limits first.']);
});

// ---- qty a → b and the machine (WP1.6) --------------------------------------------------------
test('the live booking dialog names the size change and the machine the orders go from', async () => {
  const s = load({ machine: 'on the SERVER · Chicago', book: { nq930_1030: [{ account: '1234567885', qty: 2 }] } });
  await s.api.pickAsg('nq930_1030', '1234567885', 4);
  assert.equal(s.confirms[0].title, 'Book NQ930_1030 on …885 LIVE, qty 2 → 4?');
  assert.match(s.confirms[0].body, / It runs on the SERVER · Chicago\.$/);
  const e = load({ machine: 'on this Mac', book: { nq930_1030: [{ account: '1234567885', qty: 3 }] } });
  editSize(e, 'nq930_1030', '1234567885', 3, 5);
  await tick();
  assert.match(e.confirms[0].body, / It runs on this Mac\.$/);
  const none = load();
  await none.api.pickAsg('nq930_1030', '1234567885', 3);
  assert.doesNotMatch(none.confirms[0].body, /It runs/, 'no machine known: no sentence');
});

// ---- per-account settings (task 5): other rows keep their new fields; a row with settings opens the sheet ---------
const SET_ROW = { account: 'paper-1', qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win', most: 10 };

test('per-account settings: pickAsg, editQty and removeAsg never drop another row\'s new fields', async () => {
  const book = { nq930_1030: [{ account: '1234567885', qty: 3 }, SET_ROW] };
  const p = load({ book });
  await p.api.pickAsg('nq930_1030', 'lucid-eval-1', 2);
  assert.deepEqual(plain(p.posts[0].body.assignments), [{ account: '1234567885', qty: 3 }, SET_ROW, { account: 'lucid-eval-1', qty: 2 }]);
  const e = load({ book });
  editSize(e, 'nq930_1030', '1234567885', 3, 2);
  await tick();
  assert.deepEqual(plain(e.posts[0].body.assignments), [{ account: '1234567885', qty: 2 }, SET_ROW]);
  const r = load({ book });
  r.api.removeAsg('nq930_1030', '1234567885');
  assert.deepEqual(plain(r.posts[0].body.assignments), [SET_ROW]);
});

test('per-account settings: editing the size inline keeps the same row\'s other fields', async () => {
  const row = { account: 'paper-1', qty: 4, stop_after: 'profit', most: 8 };
  const e = load({ book: { nq930_1030: [row] } });
  editSize(e, 'nq930_1030', 'paper-1', 4, 2);
  await tick();
  assert.deepEqual(plain(e.posts[0].body.assignments), [{ ...row, qty: 2 }]);
});

// acctRow itself (the block above the book): a Lab row with a size opens the sheet instead of the inline box
const ROW_BLOCK = HTML.slice(HTML.indexOf('const DAY_PNL_WORDS'), HTML.indexOf('/* ---- the book (assignments) ---- */'));
const ACCT_JS = readFileSync(new URL('../../homebase/static/desk/acctset.js', import.meta.url), 'utf8');
function rowPage() {
  const ctx = vm.createContext({ ST: { accounts: plain(ACCOUNTS) }, usd: (v) => '$' + v });
  const escDefs = HTML.slice(HTML.indexOf('const esc = (v) =>'), HTML.indexOf('async function chartPost('));
  vm.runInContext(escDefs + ACCT_JS + ROW_BLOCK + '\nglobalThis.acctRow = acctRow;', ctx);
  return ctx;
}

test('per-account settings: a Lab row with a size shows its words and opens nothing (extras dropped, owner 2026-11-02); one without keeps the inline box', () => {
  const c = rowPage();
  const sized = c.acctRow('paper-1', { qty: 1, strategy: 'lab_orb', row: SET_ROW });
  assert.doesNotMatch(sized, /openAcctSet|editQty|>Settings</);
  // one line each: the size and its tag never wrap inside themselves (final review minor 14)
  assert.match(sized, /<span class="strats" style="white-space:nowrap">\$500 risk<\/span><span class="mcap" style="white-space:nowrap">stops after a win<\/span>/);
  const legacy = c.acctRow('paper-1', { qty: 2, strategy: 'lab_orb', row: { account: 'paper-1', qty: 2 } });
  assert.match(legacy, /onclick="editQty\(event,'lab_orb',&quot;paper-1&quot;,2\)"/);
  assert.doesNotMatch(legacy, /Settings|openAcctSet/);
});

test('per-account settings: a built-in strategy\'s row is exactly as before -- no Settings button', () => {
  const c = rowPage();
  const html = c.acctRow('paper-1', { qty: 3, strategy: 'nq930_1030' });
  assert.match(html, /onclick="editQty\(event,'nq930_1030',&quot;paper-1&quot;,3\)">×3<\/span>/);
  assert.doesNotMatch(html, /Settings|openAcctSet/);
  assert.doesNotMatch(c.acctRow('paper-1', {}), /Settings/, 'the accounts popup row has none either');
});
