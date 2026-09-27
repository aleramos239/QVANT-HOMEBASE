import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) Settings dialog block (2026-09-27
   desk-settings plan + arm/kill follow-up), run for real in a sandbox -- the same technique as
   deskpaper.test.mjs: slice the inline block out of the page and run it in a vm context with a
   minimal fake DOM/fetch/confirm. Covers:
     TRADING (first section) -- the armed/disarmed status line, the Kill caption verbatim,
       Arm/Disarm/Kill wired to the SAME confirmDlg and POSTs the old top-bar buttons used, and
       that it never touches the CHART service (fetch), so it keeps working when MARKET DATA
       (second section) can't reach :8852;
     MARKET DATA -- "Charts service not running" when unreachable, server text escaped, Apply
       staging/switching and the failure snap-back. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const BLOCK = HTML.slice(
  HTML.indexOf('/* ---- Settings (2026-09-27 desk-settings plan)'),
  HTML.indexOf('/* ---- research details popup'));

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const CHART = 'http://127.0.0.1:8852';
async function tick(n = 12) { for (let i = 0; i < n; i++) await Promise.resolve(); }

function load({ armed = false, confirm = true, fetchAnswers = {}, putAnswers = {} } = {}) {
  const els = {}, fetched = [], posts = [], toasts = [], confirms = [], refreshes = [];
  const listeners = {};
  const el = (id) => (els[id] ||= {
    innerHTML: '',
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    querySelectorAll(_sel) {
      // only ever called for "button[data-md]" against this element's own just-set innerHTML
      const out = [];
      const re = /data-md="([^"]+)"/g;
      let m;
      while ((m = re.exec(this.innerHTML))) {
        const value = m[1];
        out.push({ dataset: { md: value }, addEventListener(_t, fn) { (listeners[value] ||= []).push(fn); } });
      }
      return out;
    },
    onclick: null,
    addEventListener() {},   // #settingsOverlay's click-outside-to-close listener: never exercised here
  });
  const ctx = vm.createContext({
    console,
    ST: armed == null ? null : { armed },
    $: (sel) => el(sel.replace(/^#/, '')),
    CHART,
    esc,
    toast: (t) => toasts.push(t),
    confirmDlg: async (title, body, action, destructive) => { confirms.push({ title, body, action, destructive }); return confirm; },
    post: async (url, body) => { posts.push({ url, body }); return { ok: true }; },
    refresh: () => refreshes.push(true),
    setInterval: () => 0,
    clearInterval: () => {},
    fetch: async (url, opts) => {
      fetched.push({ url, opts });
      const method = (opts && opts.method) || 'GET';
      const table = method === 'PUT' ? putAnswers : fetchAnswers;
      const a = table[url];
      if (a === undefined) return { ok: true, status: 200, json: async () => ({}) };
      if (a instanceof Error) throw a;
      return { ok: a.ok !== false, status: a.status || 200, json: async () => a.body || {} };
    },
  });
  vm.runInContext(BLOCK + `
    globalThis.api = {
      openSettings, closeSettings, renderSettings, tradingSection, marketDataSection,
      doArm, doDisarm, doKill, applyMd,
      get ST() { return ST; }, set ST(v) { ST = v; },
      get MD() { return MD; }, get MD_STAGED() { return MD_STAGED; },
      get SETTINGS_SECTIONS() { return SETTINGS_SECTIONS; },
    };`, ctx);
  return { api: ctx.api, els, fetched, posts, toasts, confirms, refreshes, listeners };
}

test('TRADING is the first section, MARKET DATA the second', () => {
  const { api } = load();
  assert.deepEqual(Array.from(api.SETTINGS_SECTIONS, (fn) => fn.name), ['tradingSection', 'marketDataSection']);
});

test('the status line reads ARMED when armed, Disarmed when not', () => {
  assert.match(load({ armed: true }).api.tradingSection(), /ARMED — signals place real orders/);
  assert.match(load({ armed: false }).api.tradingSection(), /Disarmed — signals are journaled only/);
});

test('the Kill caption is rendered verbatim, and the toggle button label follows the armed state', () => {
  const html = load().api.tradingSection();
  assert.match(html, /Cancels every working order and flattens every\s+position on every connected account, then disarms\./);
  assert.match(html, />Kill everything</);
  assert.match(load({ armed: false }).api.tradingSection(), />\s*Arm</);
  assert.match(load({ armed: true }).api.tradingSection(), />\s*Disarm</);
});

test('clicking the toggle while disarmed calls doArm -- the SAME confirmDlg and POST the old Arm button used', async () => {
  const { api, els, confirms, posts, refreshes, toasts } = load({ armed: false });
  api.renderSettings();
  assert.ok(els.tradeArmBtn.onclick, 'the Arm/Disarm toggle is wired');
  await els.tradeArmBtn.onclick();
  assert.equal(confirms.length, 1);
  assert.equal(confirms[0].title, 'Arm the desk?');
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/arm', body: { armed: true } }]);
  assert.equal(refreshes.length, 1);
  assert.match(toasts[0], /Armed/);
});

test('clicking the toggle while armed calls doDisarm directly (no confirm), same POST as the old Disarm button', async () => {
  const { api, els, confirms, posts, refreshes } = load({ armed: true });
  api.renderSettings();
  await els.tradeArmBtn.onclick();
  assert.equal(confirms.length, 0, 'Disarm never confirms, same as the old top-bar button');
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/arm', body: { armed: false } }]);
  assert.equal(refreshes.length, 1);
});

test('a declined confirm on Arm never POSTs', async () => {
  const { api, els, posts } = load({ armed: false, confirm: false });
  api.renderSettings();
  await els.tradeArmBtn.onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), []);
});

test('Kill everything uses the SAME confirm + POST /api/kill as the old top-bar button', async () => {
  const { api, els, confirms, posts, refreshes, toasts } = load();
  api.renderSettings();
  await els.tradeKillBtn.onclick();
  assert.equal(confirms.length, 1);
  assert.equal(confirms[0].title, 'Kill everything?');
  assert.equal(confirms[0].destructive, true);
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/kill' }]);
  assert.equal(refreshes.length, 1);
  assert.match(toasts[toasts.length - 1], /Kill:/);
});

test('TRADING never calls fetch -- it only talks to the desk (post/refresh), never the CHART service', async () => {
  const { api, els, fetched } = load({ armed: false });
  api.renderSettings();
  await els.tradeArmBtn.onclick();
  await els.tradeKillBtn.onclick();
  assert.deepEqual(fetched, []);
});

test('TRADING renders and its buttons keep working even when the chart service is unreachable', async () => {
  const { api, els, posts } = load({
    armed: true,
    fetchAnswers: { [`${CHART}/api/settings`]: new Error('refused'), [`${CHART}/api/status`]: new Error('refused') },
  });
  api.openSettings();
  await tick();
  assert.match(els.settingsBody.innerHTML, /TRADING/);
  assert.match(els.settingsBody.innerHTML, /Charts service not running\./);
  await els.tradeArmBtn.onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/arm', body: { armed: false } }]);
});

test('MARKET DATA: account labels and error text from the server are escaped', async () => {
  const { api, els } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: '<b>x</b>', demo: null } } } },
  });
  api.openSettings();
  await tick();
  const html = els.settingsBody.innerHTML;
  assert.ok(html.includes('&lt;b&gt;x&lt;/b&gt;'));
  assert.ok(!html.includes('<b>x</b>'));
});

test('Apply stages the pick (no PUT yet), then a refused switch snaps it back and shows the server detail verbatim', async () => {
  const { api, els, listeners, fetched } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } } },
    putAnswers: { [`${CHART}/api/settings`]: { ok: false, status: 423, body: { detail: 'Not while the 9:30 bot is working — try after 09:35.' } } },
  });
  api.openSettings();
  await tick();
  assert.equal(api.MD.md, 'demo');
  assert.equal(api.MD_STAGED, 'demo');

  listeners.live[listeners.live.length - 1]();   // pick "live": stages only, no PUT
  assert.equal(api.MD_STAGED, 'live');
  assert.equal(fetched.filter((f) => (f.opts && f.opts.method) === 'PUT').length, 0);

  await els.mdApply.onclick();
  assert.equal(api.MD_STAGED, 'demo', 'a refused switch snaps back to whichever login is ACTUALLY in use');
  assert.match(els.settingsBody.innerHTML, /09:35/);
});

test('Apply succeeds: MD and the staged pick both move to the new login', async () => {
  const { api, els, listeners } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } } },
    putAnswers: { [`${CHART}/api/settings`]: { body: { md: 'live', accounts: { live: null, demo: null } } } },
  });
  api.openSettings();
  await tick();
  listeners.live[listeners.live.length - 1]();
  await els.mdApply.onclick();
  assert.equal(api.MD.md, 'live');
  assert.equal(api.MD_STAGED, 'live');
});
