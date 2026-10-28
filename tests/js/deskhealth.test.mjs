import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* The Desk's Health card (static/desk/settings.js) and the pre-open check in the readiness banner (static/desk/topbar.js):
   read-only (they only GET /api/health, /api/logs/<name>, /api/preopen-check), every value escaped, a note where the data is
   not on this machine, and the banner shows a pre-open warn/bad row only while the result is fresh. Run in a sandbox. */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const CARD = between('/* ---- Health (read-only)', '/* ---- Server updates (read-only)');
const BANNER = between('const FIRE_AT', "/* ---- the desk's notices ----");        // readinessShown and the pre-open rows
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function load({ answers = {}, demo = false, ST = {}, win = {} } = {}) {
  const els = { settingsHealth: { innerHTML: '' }, hlLogText: { textContent: '', scrollTop: 0, scrollHeight: 9 } }, fetched = [];
  const ctx = vm.createContext({
    DEMO: demo, esc, ST, hbClock: (t) => t, window: win, Date,
    $: (s) => els[s.replace(/^#/, '')] || null,
    fetch: async (url, opts) => {
      fetched.push({ url, opts });
      const a = Object.entries(answers).find(([k]) => url.startsWith(k));
      if (!a || a[1] instanceof Error) throw a ? a[1] : new Error('no answer');
      return { ok: a[1].ok !== false, json: async () => a[1].body };
    },
  });
  vm.runInContext(BANNER + CARD + `globalThis.api = { readinessShown, preopenChecks, preopenWindow, loadPreopen, healthWords, renderHealth,
    loadHealth, showLog, runPreopen };`, ctx);
  return { api: ctx.api, els, fetched, win };
}
const watch = { available: true, at_utc: '2026-10-27T21:16:56+00:00', stale: false, line: 'GC is 5 min late', refused: 1, leaving: 2,
  markets: [{ root: 'NQ', state: 'fine' }, { root: 'ES', state: 'closed' }, { root: 'GC', state: 'late', minutes: 5 },
            { root: 'SI', state: 'silent', minutes: 10 }, { root: 'YM', state: 'thin', share: 40 }] };
const cover = { available: true, at_utc: '2026-10-27T17:17:00+00:00', classes: { whole: 2, filling: 1, lost: 1 }, lost_hours: 70,
  roots: { NQ: { whole: 1, filling: 1 }, ES: { whole: 1, lost: 1 } } };
const health = { watch, coverage: cover, logs: [{ name: 'service', label: 'Desk', size: 5 }, { name: 'ticks', label: 'Tick job', size: 9 }] };

test('the pre-open banner rows: only warn and bad, fresh, named', () => {
  const p = { available: true, age_s: 0, checks: [{ level: 'ok', label: 'power', detail: 'plugged in' },
    { level: 'warn', label: 'ticks NQ', detail: 'thin <b>' }, { level: 'bad', label: 'clock', detail: 'off' }] };
  const { api, win } = load();
  assert.deepEqual([...api.preopenChecks()], []);                       // none yet
  win.PREOPEN = { ...p, got: Date.now() };
  assert.deepEqual(api.preopenChecks().map((c) => [c.level, c.label]), [['warn', 'Pre-open: ticks NQ'], ['bad', 'Pre-open: clock']]);
  win.PREOPEN = { ...p, got: Date.now() - 16 * 60 * 1000 };             // older than 15 minutes: not now
  assert.deepEqual([...api.preopenChecks()], []);
  win.PREOPEN = { available: false, reason: 'x', got: Date.now() };
  assert.deepEqual([...api.preopenChecks()], []);
});

test('readinessShown folds them in, and the page is Not ready on a bad one', () => {
  const { api, win } = load();
  const r = { ready: true, checks: [{ level: 'ok', label: 'Power', detail: 'on power' }] };
  assert.equal(api.readinessShown(r, { strategies: {}, book: {} }), r);          // nothing to add: the same object
  win.PREOPEN = { available: true, got: Date.now(), checks: [{ level: 'warn', label: 'ticks NQ', detail: 'thin' }] };
  let s = api.readinessShown(r, { strategies: {}, book: {} });
  assert.equal(s.checks.length, 2);
  assert.equal(s.ready, true);
  win.PREOPEN.checks.push({ level: 'bad', label: 'clock', detail: 'off' });
  s = api.readinessShown(r, { strategies: {}, book: {} });
  assert.equal(s.ready, false);
  assert.equal(r.checks.length, 1);                                               // the desk's own list is not touched
});

test('the pre-open window: weekdays 07:45-09:00 ET', () => {
  const { api } = load();
  assert.equal(api.preopenWindow('2026-10-27T07:45:00'), true);       // a Tuesday
  assert.equal(api.preopenWindow('2026-10-27T08:59:59'), true);
  assert.equal(api.preopenWindow('2026-10-27T09:00:00'), false);      // never in the minutes before the open
  assert.equal(api.preopenWindow('2026-10-27T07:44:00'), false);
  assert.equal(api.preopenWindow('2026-10-31T08:00:00'), false);      // a Saturday
  assert.equal(api.preopenWindow(undefined), false);
});

test('loadPreopen reads GET only, keeps the answer with its age; run asks for a run', async () => {
  const body = { available: true, age_s: 60, checks: [] };
  const { api, fetched, win } = load({ answers: { '/api/preopen-check': { body } } });
  await api.loadPreopen(false);
  await api.loadPreopen(true);
  assert.deepEqual(fetched.map((f) => f.url), ['/api/preopen-check', '/api/preopen-check?run=1']);
  assert.ok(fetched.every((f) => !f.opts || !f.opts.method));
  assert.ok(Math.abs(win.PREOPEN.got - (Date.now() - 60000)) < 2000);
  const off = load({ answers: { '/api/preopen-check': new Error('down') } });
  await off.api.loadPreopen(false);                                   // an unreachable desk: no throw, nothing changes
  assert.equal(off.win.PREOPEN, undefined);
  const demo = load({ demo: true });
  await demo.api.loadPreopen(true);
  assert.equal(demo.fetched.length, 0);
});

test('the card: the answer first, one row per market, archive counts, escaped', () => {
  const { api, els } = load();
  api.renderHealth({ ...health, watch: { ...watch, line: 'GC <i>late</i>' } });
  const h = els.settingsHealth.innerHTML;
  assert.match(h, /HEALTH/);
  assert.match(h, /GC &lt;i&gt;late&lt;\/i&gt;/);
  for (const w of ['fine', 'closed', 'late 5 min', 'silent 10 min', 'thin: 40% of its ticks']) assert.match(h, new RegExp(w));
  assert.match(h, /1 whole · 1 filling/);
  assert.match(h, /1 whole · 1 lost/);
  assert.match(h, /70 h lost/);
  assert.match(h, /<option value="service">Desk<\/option>/);
  assert.doesNotMatch(h, /<i>late/);
});

test('the card says plainly what is not on this machine, and a stale check is not shown as current', () => {
  const { api, els } = load();
  api.renderHealth({ watch: { available: false, reason: 'No data check on this machine' },
                     coverage: { available: false, reason: 'No tick coverage report on this machine' }, logs: [] });
  assert.match(els.settingsHealth.innerHTML, /No data check on this machine/);
  assert.match(els.settingsHealth.innerHTML, /No tick coverage report on this machine/);
  assert.doesNotMatch(els.settingsHealth.innerHTML, /<table|<select/);
  api.renderHealth({ ...health, watch: { ...watch, stale: true } });
  assert.match(els.settingsHealth.innerHTML, /Not checked since 17:16 ET/);
});

test('the pre-open part of the card: run button, rows, a note off the Mac', () => {
  const { api, els, win } = load();
  api.renderHealth(health);
  assert.match(els.settingsHealth.innerHTML, /Not run yet/);
  assert.match(els.settingsHealth.innerHTML, /onclick="runPreopen\(\)"/);
  win.PREOPEN = { available: true, got: Date.now(), checks: [{ level: 'warn', label: 'ticks NQ', detail: 'thin <b>' }] };
  api.renderHealth(health);
  assert.match(els.settingsHealth.innerHTML, /ticks NQ/);
  assert.match(els.settingsHealth.innerHTML, /thin &lt;b&gt;/);
  win.PREOPEN = { available: false, reason: 'Not on this machine: the pre-open check reads the Mac', got: Date.now() };
  api.renderHealth(health);
  assert.match(els.settingsHealth.innerHTML, /Not on this machine: the pre-open check/);
  assert.doesNotMatch(els.settingsHealth.innerHTML, /runPreopen/);
});

test('a log tail: name quoted into the URL, lines set as text, a note for a log that is not here', async () => {
  const { api, els, fetched } = load({ answers: { '/api/logs/service': { body: { available: true, lines: ['a <b>', 'c'] } },
                                                  '/api/logs/charts': { body: { available: false, reason: 'No such log on this machine' } } } });
  await api.showLog('service');
  assert.equal(fetched[0].url, '/api/logs/service?lines=200');
  assert.equal(els.hlLogText.textContent, 'a <b>\nc');
  await api.showLog('charts');
  assert.equal(els.hlLogText.textContent, 'No such log on this machine');
  await api.showLog('../config');
  assert.equal(fetched[2].url, '/api/logs/..%2Fconfig?lines=200');                // the server refuses it: a key, never a path
});

test('loadHealth is GET only and draws a note when the desk does not answer', async () => {
  const { api, els, fetched } = load({ answers: { '/api/health': { body: health } } });
  await api.loadHealth();
  assert.equal(fetched[0].url, '/api/health');
  assert.match(els.settingsHealth.innerHTML, /GC is 5 min late/);
  const bad = load({ answers: { '/api/health': new Error('down') } });
  await bad.api.loadHealth();
  assert.match(bad.els.settingsHealth.innerHTML, /Could not read it/);
  const demo = load({ demo: true });
  await demo.api.loadHealth();
  assert.equal(demo.fetched.length, 0);
});
