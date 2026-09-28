import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) Settings dialog block (2026-09-27
   desk-settings plan + fix round 1; Arm/Disarm/Kill moved to the top bar 2026-09-28 -- their
   tests are in deskmaster.test.mjs), run for real in a sandbox -- the same technique as
   deskpaper.test.mjs: slice the inline block out of the page and run it in a vm context with a
   minimal fake DOM/fetch/confirm. Covers, per the fix-round review:
     I1 -- CHART TRADING is built ONCE and only ever patched in place: #ctSwitch / #ctSave (and
       any focus on them) are the SAME nodes across renderSettings()/loadChartStatus() repaints,
       never replaced. MARKET DATA lives in its own container and is skipped when nothing in it
       changed.
     I2 -- ST == null: CHART TRADING still builds (nothing asserted), no throw.
     I3 -- DEMO guards applyMd/loadSettings/loadChartStatus: never touches fetch, same toast
       post() uses.
     I4 -- covered in the Python/HTML grep, not here (no JS surface).
   Plus the original MARKET DATA coverage (escaping, Apply stage/apply/failure-snapback). */
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
// else (#ctSwitch, #ctSave, #mdApply, ...) is only "in the DOM" once some
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

test('#ctSwitch / #ctSave are the SAME nodes across renderSettings() repaints -- never rebuilt', () => {
  const { api, els } = load({ armed: false });
  api.renderSettings();
  const sw = els.ctSwitch, save = els.ctSave;
  assert.ok(sw && save, 'built once');
  api.renderSettings();
  api.renderSettings();
  assert.equal(els.ctSwitch, sw, 'renderSettings() must patch CHART TRADING in place, never rebuild it');
  assert.equal(els.ctSave, save);
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

test('opening Settings paints the chart-trading switch and limits from ST at once, not on the next 2.5 s refresh', () => {
  const { api, els } = load();
  api.ST = { armed: false, chart_trading: { enabled: true, max_order_qty: 7, max_position_qty: 14 } };
  api.openSettings();
  assert.equal(els.ctSwitch.getAttribute('aria-checked'), 'true');
  assert.equal(els.ctMaxOrder.value, 7);
  assert.equal(els.ctMaxPos.value, 14);
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
  await els.ctSave.onclick();
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
