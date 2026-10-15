import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* Owner 2026-10-10: one clock for the whole app (static/hbclock.js), a Flatten per account on the Desk, routine
   reconnects folded into one Activity line (and never "the last event"), and an equity curve of straight steps
   with a scale. The page's own code runs in a vm sandbox, as in deskactivity / deskescape. */
const read = (p) => readFileSync(new URL('../../homebase/static/' + p, import.meta.url), 'utf8');
const HTML = read('index.html'), CLOCK = read('hbclock.js');
const between = (a, b) => { const i = HTML.indexOf(a), j = HTML.indexOf(b, i); assert.ok(i >= 0 && j > i, `${a} .. ${b}`); return HTML.slice(i, j); };

function clock({ stored = null, served = null } = {}) {
  const store = new Map(stored ? [['hb_clock', stored]] : []), calls = [], doc = { hidden: false, listeners: {}, addEventListener(t, f) { this.listeners[t] = f; } };
  const ctx = vm.createContext({
    window: {}, document: doc,
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    fetch: async (url, opt = {}) => {
      calls.push({ url, method: opt.method || 'GET', body: opt.body ? JSON.parse(opt.body) : null });
      if (opt.method === 'PUT') { served = JSON.parse(opt.body).clock; return { ok: true, json: async () => ({ clock: served }) }; }
      return { ok: true, json: async () => ({ md: 'live', clock: served }) };
    },
  });
  vm.runInContext(CLOCK, ctx);
  return { C: ctx.window.HBClock, calls, store, doc };
}

test('the clock: 12-hour until told otherwise, and a 24-hour time reads the same moment either way', () => {
  const { C } = clock();
  assert.equal(C.format, '12h');
  assert.deepEqual(['09:30', '9:30', '00:05:09', '12:00', '15:55', '23:59:59'].map((t) => C.text(t)),
    ['9:30 AM', '9:30 AM', '12:05:09 AM', '12:00 PM', '3:55 PM', '11:59:59 PM']);
  assert.equal(C.text('15:55', '24h'), '15:55', 'military is the time as the desk keeps it');
  assert.equal(C.text('soon'), 'soon');
  assert.equal(C.text(null), null);
  assert.equal(C.within('2026-10-09 16:05:00'), '2026-10-09 4:05:00 PM', 'a date is never read as a time');
  assert.equal(C.within('08:20-15:55 ET'), '8:20 AM-3:55 PM ET');
  assert.equal(C.within('08:20-15:55 ET', '24h'), '08:20-15:55 ET');
});

test('the clock: the kept choice wins over the remembered one, a change is kept, and listeners hear it once', async () => {
  const { C, calls, store } = clock({ stored: '12h', served: '24h' });
  const heard = [];
  C.on((f) => heard.push(f));
  await C.load('http://desk-host:8852');
  assert.equal(C.format, '24h');
  assert.equal(store.get('hb_clock'), '24h');
  assert.equal(await C.set('24h'), true);
  assert.equal(await C.set('12h'), true);
  assert.equal(await C.set('13h'), false);
  assert.deepEqual(heard, ['24h', '12h'], 'no call for a choice that did not change');
  assert.deepEqual(calls.filter((c) => c.method === 'PUT').map((c) => [c.url, c.body]),
    [['http://desk-host:8852/api/settings', { clock: '24h' }], ['http://desk-host:8852/api/settings', { clock: '12h' }]]);
});

test('the clock: a chart service that is down changes nothing, and before load() nothing is asked of it', async () => {
  const { C, calls } = clock({ stored: '24h' });
  assert.equal(C.format, '24h');
  assert.equal(await C.set('12h'), true);
  assert.equal(calls.length, 0, 'preview mode never reaches :8852');
});

test('every page loads the clock before its own code, and the charts take their time format from it', () => {
  for (const page of ['index.html', 'charts.html', 'backtest.html']) assert.match(read(page), /<script src="\/static\/hbclock\.js\?v=\d+"><\/script>/, page);
  assert.match(read('charts/settings.js'), /if \(typeof HBClock !== 'undefined'\) n\.timeFormat = HBClock\.format;/);
  assert.match(HTML, /if \(!DEMO\) HBClock\.load\(CHART\);/);
});

// ---- Activity -----------------------------------------------------------------------------------
function fold(rows) {
  const ctx = vm.createContext({});
  vm.runInContext(between('const routineRow = ', 'let FEED_ROWS = ') + '\nglobalThis.api = { routineRow, foldRoutine };', ctx);
  return JSON.parse(JSON.stringify(ctx.api.foldRoutine(rows)));
}
const rc = (hms, account, mode = 'reconnect') => ({ ts: 1, et: `2026-10-10T${hms}-04:00`, event: 'broker_connected', account, mode });

test('a run of routine reconnects is one Activity line; a login, or anything else, still shows and splits the run', () => {
  const news = { ts: 2, et: '2026-10-10T13:01:40-04:00', event: 'strategy_toggled', strategy: 'nq930' };
  const out = fold([rc('16:55:10', 'a'), rc('16:55:09', 'b'), rc('15:45:00', 'a'), rc('15:44:54', 'b'), news, rc('12:14:52', 'a'), rc('12:14:47', 'c', 'login')]);
  assert.deepEqual(out.map((r) => r.event), ['routine_reconnects', 'strategy_toggled', 'routine_reconnects', 'broker_connected']);
  assert.deepEqual([out[0].accounts, out[0].times, out[0].et.slice(11, 19), out[0].since.slice(11, 19), out[0].rows.length], [2, 2, '16:55:10', '15:44:54', 4]);
  assert.deepEqual([out[2].accounts, out[2].times], [1, 1]);
  assert.equal(out[3].mode, 'login', 'a fresh login is news');
});

test('"Last event" never points at a routine reconnect, and Raw still lists every one of them', () => {
  assert.match(HTML, /const journalNews = \(j\) => journalShown\(j\)\.filter\(r => !routineRow\(r\)\);/);
  assert.equal((HTML.match(/journalNews\(ST\.journal\)\[0\]/g) || []).length, 2, 'the sidebar row and the Today foot');
  assert.doesNotMatch(HTML, /journalShown\(ST\.journal\)\[0\]/);
  assert.match(HTML, /\(FEED_RAW \? FEED_ROWS : foldRoutine\(FEED_ROWS\)\)\.map\(/);
});

// ---- Flatten, per account -------------------------------------------------------------------------
test('the Accounts dialog offers Flatten on every row: off for an account that is not connected, the exact id sent', () => {
  const block = between('function openAccts(focus) {', 'function closeAccts()');
  assert.match(block, /onclick="flattenAcct\(\$\{jsArg\(id\)\}\)"\$\{accts\[id\]\.connected \? "" : " disabled"\}/);
  assert.match(HTML, /onclick="openAccts\(\$\{jsArg\(id\)\}\)"/, 'a sidebar account opens the dialog on its own row');
  const f = between('async function flattenAcct(id) {', 'const killRunning = ');
  assert.match(f, /confirmDlg\("Flatten " \+ N \+ "\?"[^]*"Flatten account", true\)\) return;/, 'it asks first, as a destructive action');
  assert.match(f, /post\("\/api\/account-flatten", \{account: id\}\)/);
});

function flatten({ answer, confirm = true }) {
  const said = { toasts: [], alerts: [], posts: [] };
  const ctx = vm.createContext({
    DEMO: false, ST: { accounts: { a1: { label: 'A1' } } },
    confirmDlg: async () => confirm, refresh() {}, acctShort: (id) => id.toUpperCase(),
    toast: (t) => said.toasts.push(t), alertBar: (t) => said.alerts.push(t), toastHide() {},
    post: async (url, body) => { said.posts.push([url, JSON.parse(JSON.stringify(body))]); if (answer instanceof Error) throw answer; return answer; },   // a plain copy: the page's object is another realm's
    $: () => ({ textContent: '' }),
  });
  vm.runInContext(between('const killText = ', 'const killRunning = ') + '\nglobalThis.flattenAcct = flattenAcct;', ctx);
  return { run: () => ctx.flattenAcct('a1'), said };
}
const OK = { ok: true, error: null };

test('Flatten on an account: nothing is sent on Cancel; a clean answer is one quiet line; any failure is a loud one', async () => {
  let t = flatten({ answer: null, confirm: false });
  await t.run();
  assert.deepEqual(t.said, { toasts: [], alerts: [], posts: [] });

  t = flatten({ answer: { ok: true, account: 'a1', results: { a1: { cancel_all: OK, flatten_all: OK } }, strategies: {} } });
  await t.run();
  assert.deepEqual(t.said.posts, [['/api/account-flatten', { account: 'a1' }]]);
  assert.deepEqual(t.said.toasts, ['A1: orders cancelled and positions flattened.']);
  assert.deepEqual(t.said.alerts, []);

  t = flatten({ answer: { ok: true, results: { a1: { cancel_all: OK, flatten_all: { ok: false, error: 'rejected' } } } } });
  await t.run();
  assert.match(t.said.alerts[0], /^Flatten FAILED on A1 \(FLATTEN FAILED: rejected\)\. Flatten it at the broker now\.$/);
  assert.deepEqual(t.said.toasts, []);

  t = flatten({ answer: { ok: true } });                      // "ok" with no result is not a flatten
  await t.run();
  assert.match(t.said.alerts[0], /Flatten FAILED on A1 \(the desk sent no result\)/);

  t = flatten({ answer: new Error('Failed to fetch') });
  await t.run();
  assert.match(t.said.alerts[0], /^A1 flatten NOT confirmed — the desk didn't answer/);
});

// ---- the equity curve -----------------------------------------------------------------------------
test('the equity curve is straight steps with a dollar scale and its two dates -- never a smoothed line', () => {
  const ctx = vm.createContext({ esc: (v) => String(v), usdS: (v) => (v < 0 ? '−$' : '+$') + Math.abs(Math.round(v)), fmt: (v) => String(v) });
  vm.runInContext(between('function eqPlot(vals, label, total, aria, ends, days, notes) {', 'const shortDay = ') + '\nglobalThis.eqPlot = eqPlot;', ctx);
  const html = ctx.eqPlot([-300, -824, 400, 1995, 1914], 'After fees since Sep 17', 1914, 'curve', ['Sep 17', 'Oct 9']);
  const d = / class="eq-line" d="([^"]+)"/.exec(html)[1];
  assert.doesNotMatch(d, /C /, 'no curve commands');
  assert.equal((d.match(/ H /g) || []).length, 4, 'a flat run to each next day');
  assert.equal((d.match(/ V /g) || []).length, 4, 'then straight to its close');
  assert.deepEqual([...html.matchAll(/class="eq-y"[^>]*>([^<]+)</g)].map((m) => m[1]), ['$1995', '$0', '−$824']);
  assert.match(html, /<div class="eq-x"><span>Sep 17<\/span><span>Oct 9<\/span><\/div>/);
  assert.match(html, /class="eq-zero"/, 'the zero line is drawn where the curve crosses it');
  const up = ctx.eqPlot([100, 250, 400], 'x', 400, 'curve');
  assert.deepEqual([...up.matchAll(/class="eq-y"[^>]*>([^<]+)</g)].map((m) => m[1]), ['$400', '$200', '$0'], 'all above zero: top, halfway, zero');
  assert.doesNotMatch(up, /eq-x/, 'no dates given, none shown');
});

test('an equity curve given its days shows dates along the bottom and carries the data its hover reads', () => {
  const ctx = vm.createContext({ esc: (v) => String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;'), usdS: (v) => (v < 0 ? '−$' : '+$') + Math.abs(Math.round(v)), fmt: (v) => String(v) });
  vm.runInContext(between('function eqPlot(vals, label, total, aria, ends, days, notes) {', 'const shortDay = ') + '\nglobalThis.eqPlot = eqPlot;', ctx);
  const short = ['2026-09-17', '2026-09-18', '2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-28', '2026-09-29', '2026-09-30'];
  const h = ctx.eqPlot([10, 20, 5, 30, 40, 35, 50, 60, 55, 70], 'x', 70, 'curve', ['Sep 17', 'Sep 30'], short, short.map((_, i) => `${i + 1} trades`));
  assert.match(h, /class="eq-x eq-xt"/);
  const labels = [...h.matchAll(/<span style="left:[^"]+">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.ok(labels.length >= 4 && labels[0] === 'Sep 17' && labels[labels.length - 1] === 'Sep 30', 'a short run: day labels, first and last included: ' + labels);
  const data = JSON.parse(/data-eq="([^"]+)"/.exec(h)[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
  assert.deepEqual([data.d.length, data.v.length, data.y.length, data.n[2]], [10, 10, 10, '3 trades']);
  const long = Array.from({ length: 300 }, (_, i) => new Date(Date.UTC(2025, 6, 1) + i * 864e5 * 1.4).toISOString().slice(0, 10));
  const l = ctx.eqPlot(long.map((_, i) => i * 10), 'x', 2990, 'curve', ['a', 'b'], long);
  const ml = [...l.matchAll(/<span style="left:[^"]+">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.ok(ml.length >= 4 && ml.length <= 10 && /^Jul 2025$/.test(ml[0]), 'a long run: months, the year on the first and on each January: ' + ml);
  const bad = ctx.eqPlot([1, 2, 3], 'x', 3, 'curve', ['a', 'b'], ['2026-01-01', 'junk', '2026-01-03']);
  assert.doesNotMatch(bad, /data-eq|eq-xt/, 'a day that is not a date: the plain two-date axis, no hover');
});

test('the strategy page says what each profit figure is: before fees, the fees, after fees -- and that an account row is the whole account', () => {
  const view = between('function stratView(name) {', '/* ---- A Lab strategy the Desk itself knows');
  assert.match(view, /fig\("Before fees", usdS\(sum\("gross"\)\)/);
  assert.match(view, /fig\("Fees \(est\.\)", usdS\(sum\("net"\) - sum\("gross"\)\)/);
  assert.match(view, /fig\("After fees", usdS\(sum\("net"\)\)/);
  assert.doesNotMatch(view, /fig\("Gross"/);
  assert.match(view, /are the whole account: every strategy and every manual trade on it, not this strategy alone\./);
});
