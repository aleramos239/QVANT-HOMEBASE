import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The connect wizard's accounts step (homebase/static/index.html, :8850), run for real in a vm sandbox:
   every account under the login gets a checkbox plus Select all; accounts already on the desk show as
   added and can't be ticked; one "Add N accounts" button posts the ticked ones to /api/accounts/add-many;
   the answer is shown per account in plain words; a refusal is shown, not lost; every broker-supplied
   string is escaped and reaches its handler through jsArg. Nothing is sent anywhere. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const STEP = between('/* The accounts step:', '$("#connectOverlay").addEventListener("click"');
const ESC = between('const esc = (v)', 'async function chartPost');
const HOSTILE = `E"V'<img src=x onerror=alert(1)>\\`;

function load({ answer = { ok: true, results: [] }, open = true, accounts } = {}) {
  const els = {}, posts = [], toasts = [], steps = [], listeners = { checked: [] };
  const el = (id) => (els[id] ||= { innerHTML: '', textContent: '', value: '', style: {}, disabled: false,
    checked: false, indeterminate: false, focused: 0, focus() { this.focused++; },
    classList: { contains: (c) => c === 'open' && open } });
  const ctx = vm.createContext({
    console, Set, ST: { accounts: {} }, $: (sel) => el(sel.replace(/^#/, '')),
    document: { querySelectorAll: () => [] },
    toast: (t) => toasts.push(t), refresh() {},
    post: async (url, body) => { posts.push({ url, body }); return typeof answer === 'function' ? answer(body) : answer; },
    wizGoto: (n) => steps.push(n),
    WIZ: null,
  });
  vm.runInContext(ESC + '\n' + STEP + `
    WIZ = {saved: null, key: 'tv:live:apex', accounts: [], picks: new Set(), env: 'live', busy: false};
    globalThis.api = { WIZ, renderAcctList, wizTick, wizAll, wizCount, addSelected, wizResult, jsArg };`, ctx);
  ctx.api.WIZ.accounts = accounts || [
    { name: 'APEX-1', active: true, on_desk: false }, { name: 'APEX-2', active: true, on_desk: true },
    { name: HOSTILE, active: false, on_desk: false }, { name: 'APEX-4', active: true, on_desk: false }];
  return { api: ctx.api, els, posts, toasts, steps };
}

test('every account under the login gets a checkbox; those already on the desk are disabled and say so', () => {
  const s = load();
  s.api.renderAcctList();
  const html = s.els.acctList.innerHTML;
  assert.equal((html.match(/<input type="checkbox"/g) || []).length, 5, 'Select all + four accounts');
  const rows = html.split('<label class="copt').slice(2);                 // [all-row, ...accounts]
  assert.match(rows[1], /disabled/); assert.match(rows[1], /already added/);
  assert.doesNotMatch(rows[0], /disabled/);
  assert.match(rows[2], /inactive/);
  assert.equal(s.els.cUse.disabled, true); assert.equal(s.els.cUse.textContent, 'Add accounts');
});

test('broker text is escaped, and reaches its handler as one exact string literal (jsArg)', () => {
  const s = load();
  s.api.renderAcctList();
  const html = s.els.acctList.innerHTML;
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  const on = [...html.matchAll(/onchange="(wizTick\([^"]*\))"/g)].map((m) => m[1]);
  assert.equal(on.length, 4);
  // the handler text, decoded as the browser would, calls wizTick with the hostile name intact
  const calls = [];
  const decoded = on[2].replace(/&(quot|#39|lt|gt|amp);/g, (_, e) => ({ quot: '"', '#39': "'", lt: '<', gt: '>', amp: '&' }[e]))
    .replace('this.checked', 'true');
  vm.runInContext(decoded, vm.createContext({ wizTick: (n, on) => calls.push([n, on]) }));
  assert.deepEqual(calls, [[HOSTILE, true]]);
});

test('Select all ticks every addable account only; the button counts them; a partial pick is indeterminate', () => {
  const s = load();
  s.api.renderAcctList();
  s.api.wizAll(true);
  assert.deepEqual([...s.api.WIZ.picks].sort(), ['APEX-1', 'APEX-4', HOSTILE].sort());
  assert.equal(s.els.cUse.textContent, 'Add 3 accounts'); assert.equal(s.els.cUse.disabled, false);
  assert.equal(s.els.wAll.checked, true); assert.equal(s.els.wAll.indeterminate, false);
  s.api.wizTick('APEX-4', false); s.api.wizTick(HOSTILE, false);
  assert.equal(s.els.cUse.textContent, 'Add 1 account');
  assert.equal(s.els.wAll.checked, false); assert.equal(s.els.wAll.indeterminate, true);
  s.api.wizAll(false);
  assert.equal(s.els.cUse.disabled, true); assert.equal(s.els.wAll.indeterminate, false);
});

test('with nothing left to add, Select all is disabled and the button stays off', () => {
  const s = load({ accounts: [{ name: 'A', on_desk: true }, { name: 'B', on_desk: true }] });
  s.api.renderAcctList();
  assert.match(s.els.acctList.innerHTML.split('<label class="copt').slice(1)[0], /disabled/);
  assert.equal(s.els.cUse.disabled, true);
});

test('Add N accounts posts only the ticked, addable names in one request, then shows each account in plain words', async () => {
  const s = load({ answer: { ok: false, added: 2, exists: 0, failed: 1, results: [
    { name: 'APEX-1', status: 'added', connected: true },
    { name: HOSTILE, status: 'added', connected: false, error: 'socket <b>down</b>' },
    { name: 'APEX-4', status: 'failed', error: 'not tried — the connection failed' },
    { name: 'APEX-5', status: 'added', connected: true, mode: 'login' },
    { name: 'APEX-6', status: 'failed', error: 'not on this login' }] } });
  s.api.renderAcctList();
  s.api.wizAll(true);
  s.api.WIZ.picks.add('APEX-2');                                       // an on-desk one can never ride along
  await s.api.addSelected();
  assert.equal(s.posts.length, 1);
  assert.equal(s.posts[0].url, '/api/accounts/add-many');
  assert.deepEqual({ ...s.posts[0].body, accounts: [...s.posts[0].body.accounts].sort() },
    { key: 'tv:live:apex', accounts: ['APEX-1', 'APEX-4', HOSTILE].sort() });
  assert.deepEqual(s.steps, [4]);
  assert.equal(s.els.wresTitle.textContent, 'Added 3 accounts');
  assert.match(s.els.wresSub.textContent, /None of them is booked/); assert.match(s.els.wresSub.textContent, /LIVE/);
  const html = s.els.wresList.innerHTML;
  assert.match(html, /Added and connected\./);
  assert.match(html, /Added, but not connected yet: socket &lt;b&gt;down&lt;\/b&gt;/);
  assert.match(html, /Not tried: the connection failed\. Add it again later\./);
  assert.match(html, /Added and connected — it had to log in again\./);
  assert.match(html, /Not added: not on this login/);
  assert.doesNotMatch(html, /<b>|<img/);
  assert.equal(s.els.wDone.focused, 1, 'focus moves to the result');
  assert.equal(s.api.WIZ.busy, false);
});

test('a refusal is shown in words, not lost; a duplicate click while it runs sends one request', async () => {
  const s = load({ answer: { detail: "refused: accounts aren't added 09:20-09:35 ET" } });
  s.api.renderAcctList(); s.api.wizAll(true);
  const a = s.api.addSelected(), b = s.api.addSelected();
  await Promise.all([a, b]);
  assert.equal(s.posts.length, 1);
  assert.equal(s.els.wresTitle.textContent, 'Nothing was added');
  assert.match(s.els.wresSub.textContent, /09:20-09:35/);
  assert.equal(s.els.wresList.innerHTML, '');
});

test('closed with Esc while it ran: the answer arrives as a toast instead of a hidden step', async () => {
  const s = load({ open: false, answer: { ok: true, results: [{ name: 'APEX-1', status: 'added', connected: true }] } });
  s.api.renderAcctList(); s.api.wizAll(true);
  await s.api.addSelected();
  assert.deepEqual(s.steps, []);
  assert.deepEqual(s.toasts, ['Added 1 account']);
});
