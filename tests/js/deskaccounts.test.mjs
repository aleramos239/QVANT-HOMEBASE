import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* WP1.8: the Accounts popup. Every row says LIVE / DEMO / PAPER and "in a trade N · M working"; while it is open each tick writes
   its read-only cells in place -- the rows keep the order they opened in, and a row being typed in is never redrawn. "Reconnect
   all" shows while an account is offline and calls the one-account reconnect for each. */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const CODE = between('const esc = (v) =>', 'async function chartPost(') +
  between('/* ---- account row (rendered inside strategy cards) ---- */', '/* ---- the book (assignments) ---- */') +
  between("/* ---- the account's day take (the group's) ----", '/* ---- accounts popup ---- */') +
  between('function openAccts(focus) {', 'function closeAccts()');

const ACCTS = () => ({
  a1: { label: 'APEX001', env: 'live', connected: true, balance: 50000, realized_pnl: 0, open_positions: [{ symbol: 'NQZ6', net: 1 }], working_orders: 2, day: {} },
  a2: { label: 'Demo 2', env: 'demo', connected: true, balance: 25000, realized_pnl: 10, open_positions: [], working_orders: 0, day: {} },
  a3: { label: 'Paper 3', env: 'paper', connected: false, balance: 1000, realized_pnl: -5, open_positions: [], working_orders: 0, day: {} },
});

/* a small stand-in for the popup's DOM: each row its data-ro cells, its Flatten button and its day-take field */
function fakeRows(html) {
  const ids = [...html.matchAll(/<div class="acct[^"]*" data-acct="([^"]*)"/g)].map((m) => m[1]);
  return ids.map((id) => {
    const cells = {}, input = { tag: 'input' }, flat = { disabled: false };
    return { id, cells, input, flat, getAttribute: () => id, contains: (el) => el === input,
      querySelector: (sel) => sel === '[data-flat]' ? flat : (cells[/data-ro="(\w+)"/.exec(sel)[1]] ||= {}) };
  });
}
function load(accounts = ACCTS()) {
  const els = { acctCount: { textContent: '' }, acctList2: { innerHTML: '' } }, calls = [];
  const ctx = vm.createContext({
    ST: { accounts, book: { nq930: [{ account: 'a1', qty: 2 }] } }, document: { activeElement: null },
    $: (sel) => els[sel.replace(/^#/, '').split(' ')[0]], usd: (v) => v == null ? '—' : (v < 0 ? '-$' : '$') + Math.abs(v),
    renderPaper() {}, loadPaper() {}, showOverlay() {}, reconnectAcct: async (id) => { calls.push(id); },
  });
  vm.runInContext(CODE + '\nglobalThis.api = { openAccts, tickAccts, reconnectOffline };', ctx);
  return { ctx, els, calls };
}

test('every row says LIVE, DEMO or PAPER and what it holds right now', () => {
  const t = load();
  t.ctx.api.openAccts();
  const html = t.els.acctList2.innerHTML;
  assert.match(html, /class="tag-live"[^>]*>LIVE</);
  assert.match(html, /class="tag"[^>]*>DEMO</);
  assert.match(html, /class="tag-paper"[^>]*>PAPER</);
  assert.match(html, /data-ro="trade">in a trade 1 · 2 working</);
  assert.equal((html.match(/data-ro="trade"><\/span>/g) || []).length, 2, 'nothing held: no words');
});

test('the popup keeps its row order and a focused input across two ticks; the other rows read the new numbers', () => {
  const t = load();
  t.ctx.api.openAccts();
  const first = t.els.acctList2.innerHTML, rows = fakeRows(first);
  assert.deepEqual(rows.map((r) => r.id), ['a1', 'a2', 'a3']);
  const rc = { innerHTML: '' };
  t.els.acctList2.querySelectorAll = () => rows;
  t.els.acctList2.querySelector = () => rc;
  t.ctx.document.activeElement = rows[1].input;               // the owner is typing a day take on a2
  for (const bal of [51000, 52000]) {                          // two ticks; the desk lists the accounts in another order now
    const a = ACCTS();
    a.a1.balance = bal; a.a2.balance = bal; a.a1.open_positions = []; a.a3.connected = true;
    t.ctx.ST.accounts = { a3: a.a3, a2: a.a2, a1: a.a1 };
    t.ctx.api.tickAccts();
  }
  assert.equal(t.els.acctList2.innerHTML, first, 'no row was rebuilt or moved');
  assert.equal(rows[0].cells.bal.textContent, '$52000');
  assert.equal(rows[0].cells.trade.textContent, '2 working');
  assert.equal(rows[0].cells.strats.textContent, 'nq930 ×2');
  assert.deepEqual(rows[1].cells, {}, 'the row being typed in is left alone');
  assert.equal(rows[2].cells.dot.className, 'dot on');
  assert.equal(rows[2].flat.disabled, false, 'Flatten follows the connection');
  assert.equal(rc.innerHTML, '', 'nothing offline now: no Reconnect all');
});

test('Reconnect all shows while an account is offline and reconnects each offline one with the one-account call', async () => {
  const t = load();
  t.ctx.api.openAccts();
  assert.match(t.els.acctList2.innerHTML, /onclick="reconnectOffline\(\)"[^>]*>Reconnect all \(1 offline\)</);
  await t.ctx.api.reconnectOffline();
  assert.deepEqual(t.calls, ['a3']);
  const all = ACCTS(); all.a3.connected = true;
  const on = load(all);
  on.ctx.api.openAccts();
  assert.doesNotMatch(on.els.acctList2.innerHTML, /Reconnect all/);
});

test('I: a double click on Reconnect all runs the loop once, and a later click runs it again', async () => {
  const t = load();
  const open = [];
  t.ctx.reconnectAcct = (id) => { t.calls.push(id); return new Promise((r) => open.push(r)); };
  const first = t.ctx.api.reconnectOffline(), second = t.ctx.api.reconnectOffline();
  open.forEach((r) => r()); await first; await second;
  assert.deepEqual(t.calls, ['a3'], 'one loop, not two');
  t.ctx.reconnectAcct = async (id) => { t.calls.push(id); };
  await t.ctx.api.reconnectOffline();
  assert.deepEqual(t.calls, ['a3', 'a3'], 'the guard is let go once the loop ends');
  t.ctx.reconnectAcct = async () => { throw new Error('down'); };
  await assert.rejects(t.ctx.api.reconnectOffline());
  t.ctx.reconnectAcct = async (id) => { t.calls.push(id); };
  await t.ctx.api.reconnectOffline();
  assert.equal(t.calls.length, 3, 'and after a loop that failed');
});

test('P: a row whose account the Desk removed leaves the open popup on the next tick', () => {
  const t = load();
  t.ctx.api.openAccts();
  const rows = fakeRows(t.els.acctList2.innerHTML), removed = [];
  for (const r of rows) r.remove = () => removed.push(r.id);
  t.els.acctList2.querySelectorAll = () => rows;
  t.els.acctList2.querySelector = () => ({ innerHTML: '' });
  const a = ACCTS(); delete a.a2;
  t.ctx.ST.accounts = a;
  t.ctx.api.tickAccts();
  assert.deepEqual(removed, ['a2']);
  assert.equal(rows[0].cells.bal.textContent, '$50000', 'the others still tick');
});
