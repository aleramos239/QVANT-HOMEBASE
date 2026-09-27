import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) Settings dialog block (2026-09-27
   desk-settings plan + arm/kill follow-up + fix round 1), run for real in a sandbox -- the same
   technique as deskpaper.test.mjs: slice the inline block out of the page and run it in a vm
   context with a minimal fake DOM/fetch/confirm. Covers, per the fix-round review:
     I1 -- TRADING is built ONCE and only ever patched in place: #tradeKillBtn (and any focus on
       it) is the SAME node across renderSettings()/loadChartStatus() repaints, never replaced.
       MARKET DATA lives in its own container and is skipped when nothing in it changed.
     I2 -- ST == null renders "Desk status unknown", no Arm/Disarm toggle, Kill still present.
     I3 -- DEMO guards applyMd/loadSettings/loadChartStatus: never touches fetch, same toast
       post() uses.
     I4 -- covered in the Python/HTML grep, not here (no JS surface).
   Plus the original TRADING/MARKET DATA coverage (status line, caption, escaping, Apply
   stage/apply/failure-snapback). */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
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
// else (#tradingPill, #tradeArmBtn, #ctSwitch, #mdApply, ...) is only "in the DOM" once some
// container's innerHTML has actually been built with it, exactly like the real page: $("#ctSwitch")
// must return null before Settings has ever been opened, so a stray top-level `.onclick = ...`
// on it would throw here just like it would in a real browser.
const STATIC_IDS = new Set(['settingsOverlay', 'settingsBody', 'settingsTrading', 'settingsMarketData']);

function load({ armed = false, confirm = true, demo = false, fetchAnswers = {}, putAnswers = {} } = {}) {
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
    document: doc,
    $: (sel) => {
      const id = sel.replace(/^#/, '');
      return builtIds.has(id) ? el(id) : null;   // realistic: null before that id is ever built
    },
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
      if (a instanceof Promise) return a;   // the test controls exactly when this resolves
      return { ok: a.ok !== false, status: a.status || 200, json: async () => a.body || {} };
    },
  });
  vm.runInContext(BLOCK + `
    globalThis.api = {
      openSettings, closeSettings, renderSettings, updateTrading, renderMarketData,
      doArm, doDisarm, doKill, applyMd, loadSettings, loadChartStatus,
      renderChartTrading, setChartTrading,
      get ST() { return ST; }, set ST(v) { ST = v; },
      get MD() { return MD; }, get MD_STAGED() { return MD_STAGED; },
      get MD_REACHABLE() { return MD_REACHABLE; },
    };`, ctx);
  return { api: ctx.api, els, doc, fetched, posts, toasts, confirms, refreshes, listeners };
}

// ---- I1: TRADING is built once and patched in place -------------------------------------------
test('TRADING and MARKET DATA render into their own, separate containers', () => {
  const { api, els } = load();
  api.renderSettings();
  assert.match(els.settingsTrading.innerHTML, /TRADING/);
  assert.match(els.settingsMarketData.innerHTML, /MARKET DATA/);
  assert.doesNotMatch(els.settingsTrading.innerHTML, /MARKET DATA/);
  assert.doesNotMatch(els.settingsMarketData.innerHTML, /TRADING/);
});

test('#tradeKillBtn is the SAME node across renderSettings() repaints -- it is never rebuilt', () => {
  const { api, els } = load({ armed: false });
  api.renderSettings();
  const first = els.tradeKillBtn;
  assert.ok(first, 'built once');
  api.renderSettings();
  api.renderSettings();
  assert.equal(els.tradeKillBtn, first, 'renderSettings() must patch TRADING in place, never rebuild it');
});

test('#tradeKillBtn survives loadChartStatus() -- the poll that used to force a full rebuild', async () => {
  const { api, els } = load({
    armed: true,
    fetchAnswers: { [`${CHART}/api/status`]: { body: { md: 'demo', armed: true } } },
  });
  api.renderSettings();
  const first = els.tradeKillBtn;
  await api.loadChartStatus();
  assert.equal(els.tradeKillBtn, first, 'a MARKET DATA-only poll must never touch the TRADING node');
  assert.equal(els.tradeKillBtn.onclick, api.doKill);
});

test('TRADING patches the status line/pill/toggle in place when ST changes, without rebuilding', () => {
  const { api, els } = load({ armed: false });
  api.renderSettings();
  const killNode = els.tradeKillBtn, toggleNode = els.tradeArmBtn;
  assert.match(els.tradingText.textContent, /Disarmed/);
  assert.match(els.tradeArmBtn.textContent, /Arm/);

  api.ST = { armed: true };
  api.updateTrading();
  assert.equal(els.tradeKillBtn, killNode);
  assert.equal(els.tradeArmBtn, toggleNode, 'the toggle button itself is patched, not replaced');
  assert.match(els.tradingText.textContent, /ARMED — signals place real orders/);
  assert.match(els.tradeArmBtn.textContent, /Disarm/);
});

test('MARKET DATA is rebuilt only when its own inputs changed (a no-op poll leaves its nodes alone)', async () => {
  const { api, els } = load({
    fetchAnswers: { [`${CHART}/api/settings`]: { body: { md: 'demo', accounts: { live: null, demo: null } } } },
  });
  api.openSettings();
  await tick();
  const applyNode = els.mdApply;
  assert.ok(applyNode);
  await api.loadChartStatus();   // GET /api/status answers with no new data -> same signature
  assert.equal(els.mdApply, applyNode, 'nothing changed: MARKET DATA must not be rebuilt');
});

test('the Kill caption is rendered verbatim, and the toggle button label follows the armed state', () => {
  const { api, els } = load();
  api.renderSettings();
  assert.match(els.settingsTrading.innerHTML, /Cancels every working order and flattens every\s+position on every connected account, then disarms\./);
  assert.match(els.settingsTrading.innerHTML, />Kill everything</);
  assert.match(els.tradeArmBtn.textContent, /Arm/);
  api.ST = { armed: true };
  api.updateTrading();
  assert.match(els.tradeArmBtn.textContent, /Disarm/);
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

test('clicking the pill or the gear (openSettings) never calls post', () => {
  const { api, posts } = load();
  api.openSettings();
  assert.deepEqual(posts, []);
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
  assert.match(els.settingsTrading.innerHTML, /TRADING/);
  assert.match(els.settingsMarketData.innerHTML, /Charts service not reachable from this page\./);
  await els.tradeArmBtn.onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(posts)), [{ url: '/api/arm', body: { armed: false } }]);
});

// ---- I2: an unknown desk state never asserts "Disarmed" ---------------------------------------
test('I2: ST == null shows "Desk status unknown", hides the Arm/Disarm toggle, and keeps Kill present', () => {
  const { api, els } = load({ armed: null });
  api.renderSettings();
  assert.match(els.tradingText.textContent, /Desk status unknown — connecting…/);
  assert.equal(els.tradingToggleRow.style.display, 'none');
  assert.ok(els.tradeKillBtn, 'Kill is still built and present when the desk state is unknown');
  assert.equal(els.tradeKillBtn.onclick, api.doKill);
});

test('I2: going from unknown to a known armed state reveals the toggle again', () => {
  const { api, els } = load({ armed: null });
  api.renderSettings();
  assert.equal(els.tradingToggleRow.style.display, 'none');
  api.ST = { armed: false };
  api.updateTrading();
  assert.equal(els.tradingToggleRow.style.display, '');
  assert.match(els.tradeArmBtn.textContent, /Arm/);
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

test('Chart trading sits below Arm/Disarm and above Kill, under its own sub-heading', () => {
  const { api, els } = load();
  api.renderSettings();
  const html = els.settingsTrading.innerHTML;
  const armRow = html.indexOf('id="tradeArmBtn"');
  const heading = html.indexOf('Chart trading');
  const ctRow = html.indexOf('id="ctSwitch"');
  const killRow = html.indexOf('id="tradeKillBtn"');
  assert.ok(armRow < heading && heading < ctRow && ctRow < killRow, 'Arm/Disarm < "Chart trading" < ctSwitch < Kill');
});

test('once built, renderChartTrading patches the switch/state/limits in place -- never rebuilding', () => {
  const { api, els } = load();
  api.renderSettings();   // builds TRADING, including the chart-trading controls
  const switchNode = els.ctSwitch, saveNode = els.ctSave;
  api.renderChartTrading({ enabled: true, max_order_qty: 7, max_position_qty: 14 });
  assert.equal(els.ctSwitch.getAttribute('aria-checked'), 'true');
  assert.equal(els.ctState.textContent, 'On — the chart page can place orders');
  assert.equal(els.ctMaxOrder.value, 7);
  assert.equal(els.ctMaxPos.value, 14);
  // the SAME nodes, never replaced
  assert.equal(els.ctSwitch, switchNode);
  assert.equal(els.ctSave, saveNode);
});

test('renderChartTrading never overwrites a limit input the user is actively typing in', () => {
  const { api, els, doc } = load();
  api.renderSettings();
  api.renderChartTrading({ enabled: false, max_order_qty: 1, max_position_qty: 2 });   // first paint: populates the fake els
  doc.activeElement = els.ctMaxOrder;   // the user has focus in "Max per order"
  els.ctMaxOrder.value = '99';          // mid-edit, not yet saved
  api.renderChartTrading({ enabled: false, max_order_qty: 10, max_position_qty: 20 });
  assert.equal(els.ctMaxOrder.value, '99', 'a focused input is never clobbered by a repaint');
  assert.equal(els.ctMaxPos.value, 20, 'an unfocused input still gets patched');
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

test('Save limits POSTs the two number inputs\' parsed values, same endpoint as before', async () => {
  const { api, els, posts } = load();
  api.renderSettings();
  api.renderChartTrading({ enabled: false, max_order_qty: 1, max_position_qty: 2 });   // populates the fake els
  els.ctMaxOrder.value = '15';
  els.ctMaxPos.value = '30';
  assert.ok(els.ctSave.onclick);
  await els.ctSave.onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(posts)),
    [{ url: '/api/chart-trading', body: { max_order_qty: 15, max_position_qty: 30 } }]);
});
