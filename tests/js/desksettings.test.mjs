import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const AV = require('../../homebase/static/algo-visibility.js');   // the desk's one confirm policy (S6)

/* The desk page's (homebase/static/index.html, :8850) Settings dialog block (2026-09-27
   desk-settings plan + fix round 1; Arm/Disarm/Kill moved to the top bar 2026-09-28 -- their
   tests are in deskmaster.test.mjs), run for real in a sandbox -- the same technique as
   deskpaper.test.mjs: slice the inline block out of the page and run it in a vm context with a
   minimal fake DOM/fetch/confirm. Covers, per the fix-round review:
     I1 -- CHART TRADING is built ONCE and only ever patched in place: #ctSwitch (and
       any focus on it) are the SAME nodes across renderSettings()/loadChartStatus() repaints,
       never replaced. MARKET DATA lives in its own container and is skipped when nothing in it
       changed.
     I2 -- ST == null: CHART TRADING still builds (nothing asserted), no throw.
     I3 -- DEMO guards applyMd/loadSettings/loadChartStatus: never touches fetch, same toast
       post() uses.
     I4 -- covered in the Python/HTML grep, not here (no JS surface).
   Plus the original MARKET DATA coverage (escaping, Apply stage/apply/failure-snapback). */
import { HTML } from './deskpage.mjs';
const BLOCK = HTML.slice(
  HTML.indexOf('/* ---- Settings (2026-09-27 desk-settings plan'),
  HTML.indexOf('/* ---- research details popup'));

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const CHART = 'http://127.0.0.1:8852';

async function tick(n = 12) { for (let i = 0; i < n; i++) await Promise.resolve(); }

// Ids that exist in the static HTML from page load (the overlay's own containers) -- everything
// else (#ctSwitch, #mdApply, ...) is only "in the DOM" once some
// container's innerHTML has actually been built with it, exactly like the real page: $("#ctSwitch")
// must return null before Settings has ever been opened, so a stray top-level `.onclick = ...`
// on it would throw here just like it would in a real browser.
const STATIC_IDS = new Set(['settingsOverlay', 'settingsBody', 'settingsTrading', 'settingsMarketData']);

const WHERE = { server: 'on the SERVER · Chicago', mac: 'on this Mac' };   // core.js machineWords()
function load({ armed = false, confirm = true, demo = false, fetchAnswers = {}, putAnswers = {}, machine = null } = {}) {
  const els = {}, fetched = [], posts = [], toasts = [], confirms = [], refreshes = [];
  const listeners = {}, builtIds = new Set(STATIC_IDS);
  const doc = { activeElement: null };
  const el = (id) => (els[id] ||= {
    _html: '',
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      this._html = v;
      const re = /id="([^"]+)"/g;
      let m;
      while ((m = re.exec(v))) builtIds.add(m[1]);
    },
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
    querySelector() { return null; },   // the re-focus after a press: nothing to focus in this shim
    onclick: null,
    style: {},
    className: '',
    textContent: '',
    value: '',
    title: '',
    _attrs: {},
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return this._attrs[k]; },
    addEventListener() {},   // #settingsOverlay's click-outside-to-close listener: never exercised here
  });
  const ctx = vm.createContext({
    console,
    ST: armed == null ? null : { armed },
    DESK_STALE: false,
    DEMO: demo,
    machineWords: () => WHERE[machine] || '',
    document: doc,
    $: (sel) => {
      const id = sel.replace(/^#/, '');
      return builtIds.has(id) ? el(id) : null;   // realistic: null before that id is ever built
    },
    CHART,
    esc,
    toast: (t) => toasts.push(t),
    confirmDlg: async (title, body, action, destructive) => { confirms.push({ title, body, action, destructive }); return confirm; },
    needsConfirm: (kind, on, opts) => AV.switchNeedsConfirm(kind, on, opts),
    switchBounced: () => false,   // the double-click guard (tested in deskswitches)
    showOverlay: (id) => el(id).classList.add('open'),      // the page's one open/close path (W7)
    hideOverlay: (id) => el(id).classList.remove('open'),
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
      if (a instanceof Promise) return a;   // the test controls exactly when this resolves
      return { ok: a.ok !== false, status: a.status || 200, json: async () => a.body || {} };
    },
  });
  vm.runInContext(BLOCK + `
    globalThis.api = {
      openSettings, closeSettings, renderSettings, renderMarketData,
      applyMd, loadSettings, loadChartStatus,
      renderChartTrading, setChartTrading,
      get ST() { return ST; }, set ST(v) { ST = v; },
      get MD() { return MD; }, get MD_STAGED() { return MD_STAGED; },
      get MD_REACHABLE() { return MD_REACHABLE; },
    };`, ctx);
  return { api: ctx.api, els, doc, fetched, posts, toasts, confirms, refreshes, listeners };
}

// ---- I1: CHART TRADING is built once and patched in place ------------------------------------
test('CHART TRADING and MARKET DATA render into their own, separate containers', () => {
  const { api, els } = load();
  api.renderSettings();
  assert.match(els.settingsTrading.innerHTML, /CHART TRADING/);
  assert.match(els.settingsMarketData.innerHTML, /MARKET DATA/);
  assert.doesNotMatch(els.settingsTrading.innerHTML, /MARKET DATA/);
  assert.doesNotMatch(els.settingsMarketData.innerHTML, /CHART TRADING/);
});

test('#ctSwitch is the SAME node across renderSettings() repaints -- never rebuilt', () => {
  const { api, els } = load({ armed: false });
  api.renderSettings();
  const sw = els.ctSwitch, html = els.settingsTrading.innerHTML;
  assert.ok(sw, 'built once');
  api.renderSettings();
  api.renderSettings();
  assert.equal(els.ctSwitch, sw, 'renderSettings() must patch CHART TRADING in place, never rebuild it');
  assert.equal(els.settingsTrading.innerHTML, html);
});

test('1.1: CHART TRADING has no limit inputs and no Save limits any more (no order path reads them)', () => {
  const { api, els } = load();
  api.renderSettings();
  assert.doesNotMatch(els.settingsTrading.innerHTML, /ctMaxOrder|ctMaxPos|ctSave|Save limits|Max per order/);
  assert.doesNotMatch(BLOCK, /max_order_qty|max_position_qty|Limits saved/);
});

test('#ctSwitch survives loadChartStatus() -- a MARKET DATA-only poll never touches CHART TRADING', async () => {
  const { api, els } = load({
    armed: true,
    fetchAnswers: { [`${CHART}/api/status`]: { body: { md: 'demo', armed: true } } },
  });
  api.renderSettings();
  const sw = els.ctSwitch, html = els.settingsTrading.innerHTML;
  await api.loadChartStatus();
  assert.equal(els.ctSwitch, sw);
  assert.equal(els.settingsTrading.innerHTML, html);
});

test('opening Settings paints the chart-trading switch from ST at once, not on the next 2.5 s refresh', () => {
  const { api, els } = load();
  api.ST = { armed: false, chart_trading: { enabled: true, max_order_qty: 7, max_position_qty: 14 } };
  api.openSettings();
  assert.equal(els.ctSwitch.getAttribute('aria-checked'), 'true');
});

test('Settings holds no Arm / Disarm / Kill any more -- it says they are in the top bar (one place for them)', () => {
  const { api, els } = load();
  api.renderSettings();
  const html = els.settingsTrading.innerHTML;
  assert.match(html, /Arm, Disarm and Kill everything are in the top bar\./);
  assert.doesNotMatch(html, /tradeKillBtn|tradeArmBtn|tradingPill|>Kill everything</);
  assert.doesNotMatch(BLOCK, /post\("\/api\/(arm|kill)"/, 'the Settings block never arms, disarms or kills');
});

test('CHART TRADING never calls fetch -- it only talks to the desk (post/refresh), never the CHART service', async () => {
  const { api, els, fetched } = load({ armed: false });
  api.ST = { armed: false, chart_trading: { enabled: false, max_order_qty: 10, max_position_qty: 20 } };
  api.renderSettings();
  await els.ctSwitch.onclick();
  assert.deepEqual(fetched, []);
});

test('CHART TRADING renders and its switch keeps working even when the chart service is unreachable', async () => {
  const { api, els, posts } = load({
    armed: true,
    fetchAnswers: { [`${CHART}/api/settings`]: new Error('refused'), [`${CHART}/api/status`]: new Error('refused') },
  });
  api.ST = { armed: true, chart_trading: { enabled: true, max_order_qty: 10, max_position_qty: 20 } };
  api.openSettings();
  await tick();
  assert.match(els.settingsTrading.innerHTML, /CHART TRADING/);
  assert.match(els.settingsMarketData.innerHTML, /Charts service not reachable from this page\./);
  await els.ctSwitch.onclick();   // ON -> OFF: the safe direction, no confirm
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/chart-trading', body: { enabled: false } }]);
});

// ---- I2: an unknown desk state never throws and asserts nothing -------------------------------
test('I2: ST == null still builds CHART TRADING, leaves the switch as built, and never throws', () => {
  const { api, els } = load({ armed: null });
  assert.doesNotThrow(() => api.renderSettings());
  assert.ok(els.ctSwitch);
  assert.equal(els.ctSwitch.getAttribute('aria-checked'), undefined, 'no state painted from an unknown desk');
});

// ---- I3: preview mode never touches the CHART service ------------------------------------------
test('I3: applyMd in DEMO toasts the preview message and never calls fetch', async () => {
  const { api, fetched, toasts } = load({ demo: true });
  await api.applyMd();
  assert.deepEqual(fetched, []);
  assert.deepEqual(toasts, ['Preview mode — sample data, controls disabled.']);
});

test('I3: loadSettings in DEMO toasts and never calls fetch; MARKET DATA reads unreachable', async () => {
  const { api, els, fetched, toasts } = load({ demo: true });
  await api.loadSettings();
  assert.deepEqual(fetched, []);
  assert.deepEqual(toasts, ['Preview mode — sample data, controls disabled.']);
  assert.match(els.settingsMarketData.innerHTML, /Charts service not reachable from this page\./);
});

test('I3: loadChartStatus in DEMO toasts and never calls fetch', async () => {
  const { api, fetched, toasts } = load({ demo: true });
  await api.loadChartStatus();
  assert.deepEqual(fetched, []);
  assert.deepEqual(toasts, ['Preview mode — sample data, controls disabled.']);
});

test('I3: openSettings in DEMO never reaches the chart service', async () => {
  const { api, fetched } = load({ demo: true });
  api.openSettings();
  await tick();
  assert.deepEqual(fetched, []);
});

// ---- MARKET DATA: escaping, Apply stage/apply/failure-snapback, busy guard --------------------
test('MARKET DATA: account labels and error text from the server are escaped', async () => {
  const { api, els } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: '<b>x</b>', demo: null } } } },
  });
  api.openSettings();
  await tick();
  const html = els.settingsMarketData.innerHTML;
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
  assert.match(els.settingsMarketData.innerHTML, /09:35/);
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

test('a non-string PUT error detail (e.g. a 422 array) is stringified, never "[object Object]"', async () => {
  const { api, els, listeners } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } } },
    putAnswers: { [`${CHART}/api/settings`]: { ok: false, status: 422, body: { detail: [{ msg: 'bad md' }] } } },
  });
  api.openSettings();
  await tick();
  listeners.live[listeners.live.length - 1]();
  await els.mdApply.onclick();
  assert.doesNotMatch(els.settingsMarketData.innerHTML, /\[object Object\]/);
  assert.match(els.settingsMarketData.innerHTML, /bad md/);
});

test('repeated Apply clicks while busy send only ONE PUT', async () => {
  const { api, els, listeners, fetched } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } } },
    putAnswers: { [`${CHART}/api/settings`]: { body: { md: 'live', accounts: { live: null, demo: null } } } },
  });
  api.openSettings();
  await tick();
  listeners.live[listeners.live.length - 1]();
  const p1 = els.mdApply.onclick();
  const p2 = els.mdApply.onclick();   // MD_BUSY is already true (or about to be): this must be a no-op
  await Promise.all([p1, p2]);
  const puts = fetched.filter((f) => (f.opts && f.opts.method) === 'PUT');
  assert.equal(puts.length, 1);
});

test('a status tick that arrives mid-Apply does not clobber MARKET DATA\'s busy state', async () => {
  let resolvePut;
  const deferred = new Promise((res) => { resolvePut = res; });
  const { api, els, listeners } = load({
    fetchAnswers: {
      [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } },
      [`${CHART}/api/status`]: { body: { md: 'demo' } },
    },
    putAnswers: { [`${CHART}/api/settings`]: deferred },
  });
  api.openSettings();
  await tick();
  listeners.live[listeners.live.length - 1]();
  const applying = els.mdApply.onclick();
  await tick();   // let applyMd reach the (still pending) PUT
  assert.match(els.settingsMarketData.innerHTML, /Applying…/);

  await api.loadChartStatus();   // a stale status tick while the PUT is still in flight
  assert.match(els.settingsMarketData.innerHTML, /Applying…/, 'the mid-flight PUT must still be busy');

  resolvePut({ ok: true, status: 200, json: async () => ({ md: 'live', accounts: { live: null, demo: null } }) });
  await applying;
  assert.doesNotMatch(els.settingsMarketData.innerHTML, /Applying…/);
});

// ---- Chart trading, moved into TRADING (below Arm/Disarm, above Kill) -------------------------
test('renderChartTrading is a safe no-op while the dialog has never been opened (Settings closed)', () => {
  const { api } = load();   // buildTrading() has never run: #ctSwitch etc. do not exist yet
  assert.doesNotThrow(() => api.renderChartTrading({ enabled: true, max_order_qty: 5, max_position_qty: 10 }));
  assert.doesNotThrow(() => api.renderChartTrading(null));
});

test('once built, renderChartTrading patches the switch/state in place -- never rebuilding', () => {
  const { api, els } = load();
  api.renderSettings();   // builds TRADING, including the chart-trading controls
  const switchNode = els.ctSwitch;
  api.renderChartTrading({ enabled: true, max_order_qty: 7, max_position_qty: 14 });
  assert.equal(els.ctSwitch.getAttribute('aria-checked'), 'true');
  assert.equal(els.ctState.textContent, 'On — the chart page can place orders');
  assert.equal(els.ctSwitch, switchNode, 'the SAME node, never replaced');
});

test('the chart-trading switch calls setChartTrading, which confirms before turning ON', async () => {
  const { api, els, confirms, posts } = load();
  api.renderSettings();
  api.ST = { armed: false, chart_trading: { enabled: false, max_order_qty: 10, max_position_qty: 20 } };
  assert.ok(els.ctSwitch.onclick, 'the switch is wired once TRADING is built');
  await els.ctSwitch.onclick();
  assert.equal(confirms.length, 1);
  assert.match(confirms[0].title, /Turn chart trading ON/);
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/chart-trading', body: { enabled: true } }]);
});

test('the chart-trading switch never asks when turning OFF -- the safer direction (S6)', async () => {
  const { api, els, confirms, posts } = load();
  api.renderSettings();
  api.ST = { armed: false, chart_trading: { enabled: true, max_order_qty: 10, max_position_qty: 20 } };
  await els.ctSwitch.onclick();
  assert.equal(confirms.length, 0);
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/chart-trading', body: { enabled: false } }]);
});

test('1.1: the ON confirm names the machine and says what the desk really limits (no desk size limit, no daily cap, no day-lock)', async () => {
  for (const [machine, where] of [['server', /^Chart pages on the SERVER · Chicago can then place REAL orders on the accounts you tick there\. /],
                                  ['mac', /^Chart pages on this Mac can then place REAL orders on the accounts you tick there\. /],
                                  [null, /^Chart pages can then place REAL orders on the accounts you tick there\. /]]) {
    const { api, els, confirms, posts } = load({ machine });
    api.renderSettings();
    api.ST = { armed: false, chart_trading: { enabled: false, max_order_qty: 10, max_position_qty: 20 } };
    await els.ctSwitch.onclick();
    assert.equal(confirms.length, 1, 'ON still asks');
    assert.match(confirms[0].body, where);
    assert.match(confirms[0].body, /The desk sets no size limit \(a chart's order panel stops at 1000 contracts\), no daily trade cap and no day-lock: those bind the bots only\./);
    assert.doesNotMatch(confirms[0].body, /No size limit\.|at most|per order|per position|undefined|LIVE accounts/, 'it trades ticked demo and paper accounts too');
    assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/chart-trading', body: { enabled: true } }], 'same body as before');
  }
});

test('the 1000 contracts the confirm names is the chart order panel\'s own ceiling', () => {
  const trade = readFileSync(new URL('../../homebase/static/charts/trade.js', import.meta.url), 'utf8');
  assert.match(trade, /const PANEL_QTY_MAX = 1000;/);
});

test('CHART TRADING shows, read only, what a chart order is and is not checked against (the desk code today)', () => {
  const { api, els } = load();
  api.renderSettings();
  const html = els.settingsTrading.innerHTML;
  assert.match(html, /Checked on every chart order: at least 1 contract; at most 5 actions a second on an account; the account connected and on its own broker account; stops, targets and limits on the right side of the price; a bot's symbol is locked while the bot works\./);
  assert.match(html, /Not limited: contracts per order or held, trades a day, the day-lock \(those bind the bots only\)\./);
  assert.match(html, /With it OFF, new orders are refused; cancel, flatten and protective exits still work\./);
  assert.doesNotMatch(html, /<input|ctSave|Save limits/, 'display only: no edit field');
});

test('CHART TRADING lists the connected accounts from the desk status, read only', () => {
  const { api, els } = load();
  api.ST = { armed: false, chart_trading: { enabled: true },
             accounts: { a: { label: 'Apex 1', env: 'demo', connected: true }, b: { label: 'Gone', env: 'live', connected: false },
                         c: { label: 'Lucid', env: 'live', connected: true } } };
  api.renderSettings();
  assert.equal(els.ctAccts.textContent, 'Connected broker accounts: Apex 1 (demo) · Lucid (live). Each chart uses the ones ticked on it.');
  api.ST = { armed: false, chart_trading: { enabled: true }, accounts: {} };
  api.renderSettings();
  assert.equal(els.ctAccts.textContent, 'No broker account is connected. Each chart uses the ones ticked on it.');
});

test('MARKET DATA: a machine pinned to one login says so, and the other login cannot be picked', async () => {
  const { api, els } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', pinned: 'demo', accounts: { live: null, demo: null } } } },
  });
  api.openSettings();
  await tick();
  const html = els.settingsMarketData.innerHTML;
  assert.match(html, /This machine's charts use the Apex \(demo\) login only; it cannot be switched here\./);
  assert.ok((html.match(/disabled/g) || []).length >= 3, 'both login buttons and Apply are disabled');
});

test('MARKET DATA: not pinned, no pinned note, and the switch rules are stated', async () => {
  const { api, els } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', pinned: null, accounts: { live: null, demo: null } } } },
  });
  api.openSettings();
  await tick();
  const html = els.settingsMarketData.innerHTML;
  assert.doesNotMatch(html, /login only/);
  assert.match(html, /Refused while a bot is working, and at most one switch every 10 minutes\./);
});

test('1.1: cancelling the ON confirm posts nothing', async () => {
  const { api, els, posts, refreshes } = load({ confirm: false, machine: 'server' });
  api.renderSettings();
  api.ST = { armed: false, chart_trading: { enabled: false } };
  await els.ctSwitch.onclick();
  assert.deepEqual(posts, []);
  assert.equal(refreshes.length, 1);
});

test('1.7: staging Live says the other machine\'s charts lose live data; Apply still asks nothing', async () => {
  const { api, els, listeners, confirms, fetched } = load({
    machine: 'server',
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } } },
    putAnswers: { [`${CHART}/api/settings`]: { body: { md: 'live', accounts: { live: null, demo: null } } } },
  });
  api.openSettings();
  await tick();
  assert.doesNotMatch(els.settingsMarketData.innerHTML, /live data seat/, 'nothing staged: no note');
  listeners.live[listeners.live.length - 1]();
  assert.match(els.settingsMarketData.innerHTML, /Apply takes the live data seat on the SERVER · Chicago: the other machine's charts lose live data\./);
  await els.mdApply.onclick();
  assert.equal(confirms.length, 0, 'when it asks does not change: it never did');
  const puts = fetched.filter((f) => (f.opts && f.opts.method) === 'PUT');
  assert.deepEqual(puts.map((p) => JSON.parse(p.opts.body)), [{ md: 'live' }]);
  assert.doesNotMatch(els.settingsMarketData.innerHTML, /live data seat/, 'live in use: no note');
});
