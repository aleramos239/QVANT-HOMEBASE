import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* desk/acctset.js: the account settings sheet (per-account settings, task 5). The pure helpers first, then the sheet's
   open and save run for real against a tiny fake page. */
const CODE = readFileSync(new URL('../../homebase/static/desk/acctset.js', import.meta.url), 'utf8');
const plain = (v) => JSON.parse(JSON.stringify(v));

function load({ accounts, strategies, groups = {}, book = {}, confirm = true, replies = {} } = {}) {
  const posts = [], confirms = [], toasts = [], shown = [], hidden = [], refreshes = [];
  const els = {};
  const $ = (sel) => (els[sel] = els[sel] || { value: '', hidden: false, textContent: '', disabled: false, setAttribute() {}, focus() {}, querySelector: () => null });
  const ctx = vm.createContext({
    console,
    ST: { accounts: accounts || { live1: { label: 'APEX1', env: 'live', day: { day_lock: 0, day_loss: 0 } }, paper1: { label: 'Paper', env: 'paper', day: { day_lock: 500, day_loss: 300 } } },
      strategies: strategies || { lab_x: { cfg: { kind: 'lab' }, lab: { most_default: 20 } } }, groups, book },
    $, usd: (v) => '$' + v, acctShort: (a) => a, stratLabel: (n) => n,
    isRealAcct: (id) => id !== 'paper1', liveBookingNote: () => 'LIVE NOTE',
    confirmDlg: async (...a) => { confirms.push(a); return confirm; },
    post: async (url, body) => { posts.push({ url, body: plain(body) }); return replies[url] || { ok: true }; },
    toast: (t) => toasts.push(t), refresh: async () => { refreshes.push(1); },
    showOverlay: (id) => shown.push(id), hideOverlay: (id) => hidden.push(id),
    esc: (s) => String(s), bookMachine: () => '', DeskLab: { refusalText: (r) => r.detail },
  });
  vm.runInContext(CODE + '\nglobalThis.api = { AcctSet, openAcctSet, saveAcctSet, closeAcctSet, toggleAcctMost, acctSetSize, paintAcctSet };', ctx);
  return { api: ctx.api, ctx, els, posts, confirms, toasts, shown, hidden, refreshes, $ };
}
const A = load().api.AcctSet;

test('label: xN for contracts, $X risk for risk', () => {
  assert.equal(A.label({ qty: 3 }), '×3');
  assert.equal(A.label({ qty: 3, size: 'contracts' }), '×3');
  assert.equal(A.label({ qty: 1, size: 'risk', risk_usd: 500 }), '$500 risk');
});

test('tag: the stop-after words, nothing for never', () => {
  assert.equal(A.tag({ stop_after: 'win' }), 'stops after a win');
  assert.equal(A.tag({ stop_after: 'profit' }), 'stops in profit');
  assert.equal(A.tag({ qty: 1 }), '');
  assert.equal(A.tag({ stop_after: 'none' }), '');
});

test('rowFrom: drops most when removed and stop_after when never; risk keeps a whole qty', () => {
  const prev = { account: 'a', qty: 2, size: 'contracts', stop_after: 'win', most: 20 };
  const r = A.rowFrom({ size: 'contracts', qty: 4, stop_after: 'none', most: null }, prev);
  assert.deepEqual(plain(r), { account: 'a', qty: 4, size: 'contracts' });
  assert.ok(!('most' in r) && !('stop_after' in r));
  const k = A.rowFrom({ size: 'risk', risk_usd: 750, qty: 9, stop_after: 'profit', most: 12 }, prev);
  assert.deepEqual(plain(k), { account: 'a', qty: 2, size: 'risk', risk_usd: 750, stop_after: 'profit', most: 12 });   // qty stays the row's own
  const legacy = A.rowFrom({ size: 'risk', risk_usd: 100, stop_after: 'none', most: null }, { account: 'b' });
  assert.equal(legacy.qty, 1, 'a row with no qty falls back to 1');
});

test('needsAsk: a LIVE raise or a switch to risk asks; lower, same, or a non-live account never', () => {
  const c3 = { account: 'a', qty: 3, size: 'contracts' }, r500 = { account: 'a', qty: 1, size: 'risk', risk_usd: 500 };
  assert.equal(A.needsAsk(c3, { ...c3, qty: 4 }, true), true);
  assert.equal(A.needsAsk(c3, { ...c3, qty: 2 }, true), false);
  assert.equal(A.needsAsk(c3, { ...c3, stop_after: 'win' }, true), false);
  assert.equal(A.needsAsk(c3, r500, true), true, 'switched to risk');
  assert.equal(A.needsAsk(r500, { ...r500, risk_usd: 600 }, true), true);
  assert.equal(A.needsAsk(r500, { ...r500, risk_usd: 400 }, true), false);
  assert.equal(A.needsAsk(c3, { ...c3, qty: 9 }, false), false);
  assert.equal(A.needsAsk(c3, r500, false), false);
  assert.equal(A.needsAsk({ account: 'a', qty: 1 }, { account: 'a', qty: 2 }, true), true, 'a legacy row reads as contracts');
});

test('withRow replaces one account\'s row and keeps every other row as it is', () => {
  const other = { account: 'b', qty: 1, size: 'risk', risk_usd: 250, stop_after: 'win', most: 5 };
  const out = A.withRow([{ account: 'a', qty: 1 }, other], { account: 'a', qty: 2, size: 'contracts' });
  assert.deepEqual(plain(out), [{ account: 'a', qty: 2, size: 'contracts' }, plain(other)]);
  assert.deepEqual(plain(A.withRow([other], { account: 'c', qty: 1 })).map((r) => r.account), ['b', 'c'], 'a new account is added');
});

test('formOf: a legacy row opens as "own" with no Most box; a set row opens as it is', () => {
  assert.deepEqual(plain(A.formOf({ account: 'a', qty: 3 })), { size: 'own', qty: 3, risk_usd: '', stop_after: 'none', most: null, hold: false });
  assert.deepEqual(plain(A.formOf({ account: 'a', qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win' })),
    { size: 'risk', qty: 1, risk_usd: 500, stop_after: 'win', most: null, hold: false });
});

test('rowFrom "own": {account, qty, stop_after?} only, never size or most', () => {
  const r = A.rowFrom({ size: 'own', qty: 4, stop_after: 'win', most: 20 }, { account: 'a', qty: 3 });
  assert.deepEqual(plain(r), { account: 'a', qty: 4, stop_after: 'win' });
});

test('needsAsk: a LIVE plain row given a size asks; a plain qty raise asks; Most up or removed on a risk row asks, on contracts not', () => {
  const legacy = { account: 'a', qty: 2 }, r = { account: 'a', qty: 1, size: 'risk', risk_usd: 500, most: 20 };
  const c = { account: 'a', qty: 2, size: 'contracts', most: 20 };
  assert.equal(A.needsAsk(legacy, { ...legacy, stop_after: 'win' }, true), false);
  assert.equal(A.needsAsk(legacy, { ...legacy, qty: 3 }, true), true);
  assert.equal(A.needsAsk(legacy, { ...c }, true), true, 'legacy switched to Contracts');
  assert.equal(A.needsAsk(legacy, { ...c }, false), false);
  assert.equal(A.needsAsk(r, { ...r, most: 40 }, true), true);
  assert.equal(A.needsAsk(r, { account: 'a', qty: 1, size: 'risk', risk_usd: 500 }, true), true, 'Most removed');
  assert.equal(A.needsAsk(r, { ...r, most: 10 }, true), false);
  assert.equal(A.needsAsk(c, { ...c, most: 40 }, true), false, 'a contracts row needs no ask for Most');
});

// ---- the sheet -------------------------------------------------------------------------------------------
const fill = (t, o) => { for (const [k, v] of Object.entries(o)) t.$('#' + k).value = v; };

test('open: a Lab row fills the fields; a cycle with risk shows the note', () => {
  const t = load({ book: { lab_x: [{ account: 'live1', qty: 3 }] },
    groups: { g1: { on: true, members: ['lab_x'], risk_usd: 1000 } } });
  t.api.openAcctSet('lab_x', 'live1');
  assert.deepEqual(t.shown, ['acctSetOverlay']);
  assert.equal(t.$('#asQty').value, '3');
  assert.equal(t.$('#asSize').value, 'own');
  assert.equal(t.$('#asCycle').hidden, false);
  assert.match(t.$('#asCycle').textContent, /The account group sizes this strategy while it is on/);
  const off = load({ book: { lab_x: [{ account: 'live1', qty: 3 }] } });
  off.api.openAcctSet('lab_x', 'live1');
  assert.equal(off.$('#asCycle').hidden, true);
});

test('save on a LIVE account: a raise asks first with the live note, then posts the whole book', async () => {
  const other = { account: 'paper1', qty: 1, size: 'risk', risk_usd: 250 };
  const t = load({ book: { lab_x: [{ account: 'live1', qty: 3, size: 'contracts' }, other] } });
  t.api.openAcctSet('lab_x', 'live1');
  fill(t, { asQty: '5' });
  await t.api.saveAcctSet();
  assert.equal(t.confirms.length, 1);
  assert.match(t.confirms[0][1], /LIVE NOTE/);
  assert.equal(t.confirms[0][2], 'Book live');
  assert.deepEqual(t.posts, [{ url: '/api/book', body: { strategy: 'lab_x', assignments: [
    { account: 'live1', qty: 5, size: 'contracts' }, plain(other)] } }]);
  assert.deepEqual(t.hidden, ['acctSetOverlay']);
});

test('a legacy row with only Stop after changed posts a row with no size and no most', async () => {
  const t = load({ book: { lab_x: [{ account: 'paper1', qty: 2 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  assert.equal(t.$('#asSize').value, 'own');
  assert.equal(t.$('#asMostW').hidden, true);
  fill(t, { asStop: 'win' });
  await t.api.saveAcctSet();
  assert.deepEqual(t.posts, [{ url: '/api/book', body: { strategy: 'lab_x', assignments: [{ account: 'paper1', qty: 2, stop_after: 'win' }] } }]);
});

test('a legacy LIVE row switched to Contracts asks, and gets size and Most at the default', async () => {
  const t = load({ book: { lab_x: [{ account: 'live1', qty: 2 }] } });
  t.api.openAcctSet('lab_x', 'live1');
  fill(t, { asSize: 'contracts' });
  t.api.acctSetSize();
  assert.equal(t.$('#asMostW').hidden, false);
  assert.equal(t.$('#asMost').value, '20');
  await t.api.saveAcctSet();
  assert.equal(t.confirms.length, 1);
  assert.deepEqual(t.posts[0].body.assignments, [{ account: 'live1', qty: 2, size: 'contracts', most: 20 }]);
});

test('a LIVE risk row asks when Most is raised or removed', async () => {
  const row = { account: 'live1', qty: 1, size: 'risk', risk_usd: 500, most: 20 };
  const up = load({ book: { lab_x: [row] } });
  up.api.openAcctSet('lab_x', 'live1');
  fill(up, { asMost: '40' });
  await up.api.saveAcctSet();
  assert.equal(up.confirms.length, 1);
  const off = load({ book: { lab_x: [row] } });
  off.api.openAcctSet('lab_x', 'live1');
  off.api.toggleAcctMost();
  await off.api.saveAcctSet();
  assert.equal(off.confirms.length, 1);
  assert.ok(!('most' in off.posts[0].body.assignments[0]));
});

test('the "own" option is offered only for a size-less row, and the backstop words follow the contract', () => {
  const t = load({ book: { lab_x: [{ account: 'paper1', qty: 3 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  assert.equal(t.$('#asOwn').hidden, false);
  assert.equal(t.$('#asOwn').textContent, "The strategy's own (×3)");
  assert.match(t.$('#asMostOff').textContent, /100 micros/);
  const sized = load({ book: { lab_x: [{ account: 'paper1', qty: 3, size: 'contracts' }] } });
  sized.api.openAcctSet('lab_x', 'paper1');
  assert.equal(sized.$('#asOwn').hidden, true);
  assert.equal(sized.$('#asOwn').disabled, true);
  const mini = load({ strategies: { lab_x: { cfg: { kind: 'lab' }, lab: { most_default: 2 } } }, book: { lab_x: [{ account: 'paper1', qty: 1 }] } });
  mini.api.openAcctSet('lab_x', 'paper1');
  assert.match(mini.$('#asMostOff').textContent, /10 minis/);
});

test('save: Cancel on the live ask sends nothing; a paper account never asks', async () => {
  const t = load({ confirm: false, book: { lab_x: [{ account: 'live1', qty: 3, size: 'contracts' }] } });
  t.api.openAcctSet('lab_x', 'live1');
  fill(t, { asSize: 'risk', asRisk: '500' });
  await t.api.saveAcctSet();
  assert.equal(t.confirms.length, 1);
  assert.deepEqual(t.posts, []);
  const p = load({ book: { lab_x: [{ account: 'paper1', qty: 3, size: 'contracts' }] } });
  p.api.openAcctSet('lab_x', 'paper1');
  fill(p, { asSize: 'risk', asRisk: '500' });
  await p.api.saveAcctSet();
  assert.equal(p.confirms.length, 0);
  assert.equal(p.posts[0].body.assignments[0].risk_usd, 500);
});

test('save: only a changed account lock is posted, and an unchanged row is not', async () => {
  const t = load({ book: { lab_x: [{ account: 'paper1', qty: 2, size: 'contracts', most: 20 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  fill(t, { asLoss: '400' });                       // the take stays 500
  await t.api.saveAcctSet();
  assert.deepEqual(t.posts, [{ url: '/api/account-day-lock', body: { account: 'paper1', day_loss: 400 } }]);
});

test('save: a legacy row saved unchanged posts nothing; a bad risk is refused on the sheet', async () => {
  const t = load({ book: { lab_x: [{ account: 'paper1', qty: 2 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  await t.api.saveAcctSet();
  assert.deepEqual(t.posts, []);
  t.hidden.length = 0;
  t.api.openAcctSet('lab_x', 'paper1');
  fill(t, { asSize: 'risk', asRisk: '0' });
  await t.api.saveAcctSet();
  assert.deepEqual(t.posts, [], 'risk 0 is not sent');
  assert.equal(t.$('#asNote').hidden, false);
  assert.deepEqual(t.hidden, []);
});

test('Remove takes the Most box off the row; + Add puts it back at the strategy\'s default', async () => {
  const t = load({ book: { lab_x: [{ account: 'paper1', qty: 2, size: 'contracts', most: 7 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  assert.equal(t.$('#asMost').value, '7');
  t.api.toggleAcctMost();
  assert.equal(t.$('#asMostBtn').textContent, '+ Add');
  await t.api.saveAcctSet();
  assert.ok(!('most' in t.posts[0].body.assignments[0]));
  t.api.openAcctSet('lab_x', 'paper1');
  t.api.toggleAcctMost();       // off, then on again
  t.api.toggleAcctMost();
  assert.equal(t.$('#asMost').value, '20');
  assert.equal(t.$('#asMostBtn').textContent, 'Remove');
});

test('save: a refused book shows the Desk\'s sentence and keeps the sheet open', async () => {
  const t = load({ replies: { '/api/book': { ok: false, detail: 'No.' } }, book: { lab_x: [{ account: 'paper1', qty: 2, size: 'contracts' }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  fill(t, { asQty: '3' });
  await t.api.saveAcctSet();
  assert.equal(t.$('#asNote').textContent, 'No.');
  assert.deepEqual(t.hidden, []);
});

test('the sheet is static markup with every field the code reads, closes with Esc, and render() never touches it', async () => {
  const { HTML } = await import('./deskpage.mjs');
  const markup = HTML.slice(HTML.indexOf('<div class="overlay" id="acctSetOverlay">'), HTML.indexOf('<div class="overlay" id="settingsOverlay">'));
  for (const id of ['asTitle', 'asCycle', 'asSize', 'asQtyF', 'asQty', 'asRiskF', 'asRisk', 'asMostW', 'asOwn', 'asMostF', 'asMost', 'asMostOff', 'asMostBtn',
    'asStop', 'asTake', 'asLoss', 'asNote', 'asSave']) assert.match(markup, new RegExp(`id="${id}"`), id);
  for (const w of ['This strategy on this account', 'Whole account — every strategy on it', 'Profit lock', 'Loss lock', 'Most contracts',
    'Stop after', 'Never', 'A win', 'In profit', 'role="dialog" aria-modal="true"']) assert.ok(markup.includes(w), w);
  assert.equal((HTML.match(/id="acctSetOverlay"/g) || []).length, 1);
  assert.ok(HTML.includes('acctSetOverlay: () => closeAcctSet()'));
  const render = HTML.slice(HTML.indexOf('function render() {'), HTML.indexOf('async function refresh() {'));
  assert.doesNotMatch(render, /acctSetOverlay|asSave|openAcctSet/);
});

// ---- final fixes (final-review.md) -----------------------------------------------------------------------
test('words: label, then Most when asked, then the stop-after tag', () => {
  assert.equal(A.words({ qty: 3 }), '×3');
  assert.equal(A.words({ qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win', most: 4 }), '$500 risk, stops after a win');
  assert.equal(A.words({ qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win', most: 4 }, true), '$500 risk, most 4, stops after a win');
  assert.equal(A.words({ qty: 2, stop_after: 'profit' }, true), '×2, stops in profit');
});

test('the loss lock is capped at 100000 like the profit lock (minor 1)', async () => {
  const t = load({ book: { lab_x: [{ account: 'paper1', qty: 2 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  fill(t, { asLoss: '100001' });
  await t.api.saveAcctSet();
  assert.deepEqual(t.posts, []);
  assert.equal(t.$('#asNote').textContent, 'The loss lock is a dollar amount from 0 (off) to 100000.');
  fill(t, { asLoss: '100000' });
  await t.api.saveAcctSet();
  assert.deepEqual(t.posts, [{ url: '/api/account-day-lock', body: { account: 'paper1', day_loss: 100000 } }]);
});

test('a status with no most_default gives the backend\'s own fallback, 2, never 20 (minor 15)', () => {
  const t = load({ strategies: { lab_x: { cfg: { kind: 'lab' }, lab: {} } }, book: { lab_x: [{ account: 'paper1', qty: 1 }] } });
  t.api.openAcctSet('lab_x', 'paper1');
  fill(t, { asSize: 'contracts' });
  t.api.acctSetSize();
  assert.equal(t.$('#asMost').value, '2');
});

test('Most contracts has an accessible name (minor 12)', async () => {
  const { HTML } = await import('./deskpage.mjs');
  assert.ok(HTML.includes('<label for="asMost">Most contracts</label>'));
});
