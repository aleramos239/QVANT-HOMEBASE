import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

/* The pure half of a Lab strategy on the Desk page (homebase/static/desklab.js): the sentences, the dot, the numbers.
   Escaping is the page's job (esc / jsArg): these helpers return plain text, and the page tests below pin that no
   network value reaches a template raw. */
const require = createRequire(import.meta.url);
const D = require('../../homebase/static/desklab.js');
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const SKIN = readFileSync(new URL('../../homebase/static/apple/desk.js', import.meta.url), 'utf8');

const ALIVE = { alive: true, seen_utc: '2026-10-09T14:00:00+00:00', prices: {} };
const row = (over = {}) => ({ name: 'nq_orb', label: 'NQ ORB', root: 'NQ', session_window: ['09:25', '16:00'], bar_minutes: 1, qty: 1, enabled: true,
  sha256: 'abcdef0123456789', promoted_utc: '2026-10-09T18:03:00+00:00', today: null, days: [],
  run: { id: 'r1', net: 5000, trades: 41, win_rate: 48.8, profit_factor: 1.31, max_drawdown: -2100 }, notes: [], ...over });
const day = (over = {}) => ({ date: '2026-10-09', state: 'waiting', why: null, orders: [], trades: [], net: 0, match: null, ...over });

test('stateText: switched off reads Off whatever else is true; then a runner that is not alive, then the day', () => {
  assert.equal(D.stateText(row(), null), 'Runner is not running');
  assert.equal(D.stateText(row(), { alive: false }), 'Runner is not running');
  assert.equal(D.stateText(row({ enabled: false, today: day({ state: 'running' }) }), { alive: false }), 'Off', 'a promoted strategy lands off: it does nothing, runner or not');
  assert.equal(D.stateText(row({ enabled: false, today: day({ state: 'running' }) }), ALIVE), 'Off');
  assert.equal(D.stateText(row({ enabled: false }), null), 'Off');
});

test('stateText: one sentence for each state of the day', () => {
  const at = (state, why = null) => D.stateText(row({ today: day({ state, why }) }), ALIVE);
  assert.equal(D.stateText(row({ today: null }), ALIVE), 'Waiting for the session', 'no day yet');
  assert.equal(at('waiting'), 'Waiting for the session');
  assert.equal(at('running'), 'Running in shadow');
  assert.equal(at('done'), 'Done for today');
  assert.equal(at('stopped', 'prices are late'), 'Stopped: prices are late');
  assert.equal(at('stopped'), 'Stopped');
  assert.equal(at('not_today'), 'Does not trade today');
  assert.equal(at('off'), 'Off');
  assert.equal(at('something_new'), 'Waiting for the session', 'a state this page does not know reads as waiting, never as running');
});

test('stateText: the why replaces "Running in shadow" while it runs (prices late)', () => {
  assert.equal(D.stateText(row({ today: day({ state: 'running', why: 'Prices are late.' }) }), ALIVE), 'Prices are late.');
  assert.equal(D.stateText(row({ today: day({ state: 'running', why: '' }) }), ALIVE), 'Running in shadow');
  assert.equal(D.stateText(row({ today: day({ state: 'waiting', why: 'x' }) }), ALIVE), 'Waiting for the session', 'only a running day shows its why');
});

test('dotClass: off, shadow or warn, in step with the words', () => {
  const at = (r, rn = ALIVE) => D.dotClass(r, rn);
  assert.equal(at(row()), 'shadow');
  assert.equal(at(row({ today: day({ state: 'running' }) })), 'shadow');
  assert.equal(at(row({ today: day({ state: 'done' }) })), 'shadow');
  assert.equal(at(row({ enabled: false })), 'off');
  assert.equal(at(row({ today: day({ state: 'off' }) })), 'off');
  assert.equal(at(row({ today: day({ state: 'not_today' }) })), 'off');
  assert.equal(at(row({ today: day({ state: 'stopped', why: 'x' }) })), 'warn');
  assert.equal(at(row({ today: day({ state: 'running', why: 'Prices are late.' }) })), 'warn');
  assert.equal(at(row(), null), 'warn');
  assert.equal(at(row(), { alive: false }), 'warn');
  assert.equal(at(row({ enabled: false }), { alive: false }), 'off', 'switched off: no warning for a runner it does not use');
});

test('todayNet: the day\'s would-be net, or null when there is no number', () => {
  assert.equal(D.todayNet(row()), null);
  assert.equal(D.todayNet(row({ today: day({ net: 120.5 }) })), 120.5);
  assert.equal(D.todayNet(row({ today: day({ net: 0 }) })), 0);
  assert.equal(D.todayNet(row({ today: day({ net: -75 }) })), -75);
  assert.equal(D.todayNet(row({ today: day({ net: null }) })), null);
  assert.equal(D.todayNet(row({ today: day({ net: 'x' }) })), null);
  assert.equal(D.todayNet(row({ today: day({ net: NaN }) })), null);
  assert.equal(D.todayNet(null), null);
});

test('usd: a real minus sign, whole dollars, a plus for a gain', () => {
  assert.equal(D.usd(120), '+$120');
  assert.equal(D.usd(-1234.4), '−$1,234');
  assert.equal(D.usd(0), '$0');
  assert.equal(D.usd(null), '—');
  assert.equal(D.usd(undefined), '—');
  assert.equal(D.usd('5'), '—', 'only a number is a number');
});

test('orderLine: the time and the words; a refused order says why after "Would be refused:"', () => {
  assert.deepEqual({ ...D.orderLine({ t: '09:30:01', text: 'Buy stop 1 at 21000.25', refused: null }) },
    { t: '09:30:01', text: 'Buy stop 1 at 21000.25', refused: false });
  assert.deepEqual({ ...D.orderLine({ t: '09:30:02', text: 'Sell stop 1 at 20990', refused: 'One position at a time.' }) },
    { t: '09:30:02', text: 'Sell stop 1 at 20990. Would be refused: One position at a time.', refused: true });
  assert.deepEqual({ ...D.orderLine({ t: '09:30:02', text: 'Sell stop 1 at 20990.', refused: 'Too late for a new trade today.' }) }.text,
    'Sell stop 1 at 20990. Would be refused: Too late for a new trade today.', 'no double full stop');
  assert.deepEqual({ ...D.orderLine({}) }, { t: '', text: '', refused: false });
  assert.deepEqual({ ...D.orderLine(null) }, { t: '', text: '', refused: false });
});

test('tradeLine: side, entry to exit, why it ended, and the net', () => {
  const t = { side: 'long', qty: 1, entry_t: '09:31:10', entry_px: 21000.25, exit_t: '09:44:02', exit_px: 21015.5, reason: 'target', net: 301.5 };
  assert.deepEqual({ ...D.tradeLine(t) }, { text: 'Long 1 · 09:31:10 21,000.25 to 09:44:02 21,015.50 · target', net: 301.5 });
  const s = D.tradeLine({ ...t, side: 'short', qty: 2, exit_t: null, exit_px: null, reason: null, net: null });
  assert.deepEqual({ ...s }, { text: 'Short 2 · 09:31:10 21,000.25', net: null }, 'still open: no exit yet');
  assert.deepEqual({ ...D.tradeLine(null) }, { text: '', net: null });
});

test('matchLine: the date, the match sentence (or "Not checked yet."), the net', () => {
  assert.deepEqual({ ...D.matchLine(day({ date: '2026-10-08', net: 80, match: { ok: true, text: 'Matched the backtest: 3 of 3 trades.' } })) },
    { date: '2026-10-08', text: 'Matched the backtest: 3 of 3 trades.', ok: true, net: 80 });
  assert.deepEqual({ ...D.matchLine(day({ date: '2026-10-07', net: -20, match: { ok: false, text: '1 trade differs.' } })) },
    { date: '2026-10-07', text: '1 trade differs.', ok: false, net: -20 });
  assert.deepEqual({ ...D.matchLine(day({ match: null })) }, { date: '2026-10-09', text: 'Not checked yet.', ok: null, net: 0 });
  assert.equal(D.matchLine(day({ match: { ok: null, text: '' } })).text, 'Not checked yet.');
  assert.equal(D.matchLine(day({ match: { ok: 'yes', text: 'x' } })).ok, null, 'only true or false is a verdict');
  assert.deepEqual({ ...D.matchLine(null) }, { date: '', text: 'Not checked yet.', ok: null, net: null });
});

test('specLine: market, session, bars, and where it came from', () => {
  assert.equal(D.specLine(row()), 'NQ · 09:25-16:00 ET · 1-minute bars · from the Lab');
  assert.equal(D.specLine(row({ bar_minutes: 5, session_window: ['9:30', '11:00'] })), 'NQ · 9:30-11:00 ET · 5-minute bars · from the Lab');
  assert.equal(D.specLine(row({ session_window: undefined, bar_minutes: undefined })), 'NQ · from the Lab', 'what the record does not carry is left out');
  assert.equal(D.specLine(row({ session_window: ['x', 'y'], bar_minutes: 0 })), 'NQ · from the Lab');
  assert.equal(D.specLine({}), 'from the Lab');
});

test('label: the name the Desk shows', () => {
  assert.equal(D.label(row()), 'NQ ORB');
  assert.equal(D.label(row({ label: '' })), 'nq_orb');
  assert.equal(D.label(row({ label: undefined })), 'nq_orb');
});

test('figures: the backtest numbers in the figs block\'s order', () => {
  assert.deepEqual(D.figures(row()).map((f) => [f.k, f.v]), [['Net', '+$5,000'], ['Win rate', '49%'], ['Trades', '41'], ['Profit factor', '1.31'], ['Deepest drawdown', '−$2,100']]);
  assert.deepEqual(D.figures(row({ run: {} })).map((f) => f.v), ['—', '—', '—', '—', '—']);
  assert.deepEqual(D.figures({}).map((f) => f.v), ['—', '—', '—', '—', '—']);
  assert.equal(D.figures(row({ run: { max_drawdown: 2100 } }))[4].v, '−$2,100', 'a drawdown is a loss whichever sign it came with');
  assert.equal(D.figures(row({ run: { max_drawdown: 0 } }))[4].v, '$0');
});

test('setupRows: what the skin\'s Setup card lists', () => {
  assert.deepEqual(D.setupRows(row()), [['Market', 'NQ'], ['Session', '09:25-16:00 ET'], ['Bars', '1 min'], ['Size', '1 contract'],
    ['Promoted', 'Oct 9, 2026'], ['Code', 'abcdef01'], ['Orders', 'None: shadow']]);
  assert.deepEqual(D.setupRows(row({ qty: 3, bar_minutes: 15, session_window: undefined, sha256: 'ab' })).map((r) => r.join('=')),
    ['Market=NQ', 'Session=—', 'Bars=15 min', 'Size=3 contracts', 'Promoted=Oct 9, 2026', 'Code=ab', 'Orders=None: shadow']);
  assert.deepEqual(D.setupRows({}).map((r) => r[1]), ['—', '—', '—', '—', '—', '—', 'None: shadow']);
  assert.equal(D.setupRows(row({ promoted_utc: 'not a date' }))[4][1], '—');
});

test('there is no "Allowed up to" control: a promoted strategy is on the Desk, off, and the owner turns it on', () => {
  for (const k of ['LEVELS', 'LEVELS_WHY', 'LEVEL_LOCKED']) assert.equal(k in D, false, k);
  for (const src of [HTML, SKIN, readFileSync(new URL('../../homebase/static/desklab.js', import.meta.url), 'utf8')]) {
    assert.doesNotMatch(src, /Allowed up to|labLevelsWhy|DeskLab\.LEVEL|Funded demo and Live unlock/);
  }
});

test('the words the page shows, exactly', () => {
  assert.equal(D.TAG_TITLE, 'It writes down its orders. Nothing is sent.');
  assert.equal(D.NET_TITLE, 'What it would have made today, after costs, 1 contract');
  assert.equal(D.switchTitle(true), 'ON: it runs in shadow');
  assert.equal(D.switchTitle(false), 'OFF: it does nothing');
  assert.equal(D.NOTE, 'From the Lab. Switched on, it runs on live prices in shadow: it writes down its orders and nothing is sent.');
  assert.equal(D.GONE, 'That strategy is not on the Desk any more. Promote it again from the Lab.');
  assert.equal(D.EMPTY_DAY, 'Nothing yet today.');
  assert.equal(D.ACCOUNTS_CAPTION, 'Accounts come with the Desk update. Until then it runs in shadow.');
  assert.deepEqual({ ...D.removeAsk('nq_orb') }, { title: 'Remove nq_orb from the Desk?', body: 'Its history is kept.' });
});

/* ---- the page (index.html): what it may call, and that nothing from the network reaches a template raw ---- */
const LABBLOCK = HTML.slice(HTML.indexOf('/* ---- LAB STRATEGIES on the Desk'), HTML.indexOf('function setView('));
const LABVIEW = HTML.slice(HTML.indexOf('/* ---- Lab strategies: rows and page.'), HTML.indexOf('function stratView('));

const code = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '');

test('the page asks the chart service for the Lab strategies and never the desk\'s own API about them', () => {
  assert.ok(LABBLOCK.length > 500 && LABVIEW.length > 500, 'the Lab section and its page are there');
  const urls = [...new Set([...code(LABBLOCK).matchAll(/["'`](\/api\/[^"'`$?]*)/g)].map((m) => m[1]))].sort();
  assert.deepEqual(urls, ['/api/tester/desklab', '/api/tester/desklab/onoff', '/api/tester/desklab/remove']);
  assert.doesNotMatch(code(LABBLOCK + LABVIEW), /\/api\/(strategy|book|status)|[^t]post\(/, 'the desk does not know a Lab strategy in this step');
  assert.doesNotMatch(code(LABVIEW), /flattenStrat|toggleStrat|testFire|pickAsg|toggleAsgMenu|openRes|openLive/);
});

test('no polling while the page is hidden', () => {
  assert.match(HTML, /setInterval\(\(\) => \{ if \(!document\.hidden\) loadDeskLab\(\); \}, 5000\)/);
  assert.match(HTML, /document\.addEventListener\("visibilitychange", \(\) => \{ if \(!document\.hidden\) loadDeskLab\(\); \}\)/);
  assert.match(LABBLOCK, /async function loadDeskLab\(\) \{\n  if \(DEMO \|\| document\.hidden\) return;/);
});

test('every template hole in the Lab rows and page is escaped, a flag the page made, or a piece built from escaped holes', () => {
  const holes = [...LABVIEW.matchAll(/\$\{([^}]*(?:\{[^}]*\}[^}]*)*)\}/g)].map((m) => m[1].trim());
  assert.ok(holes.length > 40, 'the page has template holes');
  // anything else is a new hole: look at it before adding it here
  const flags = new Set(['sel("lab", w.name)', 'sel("lab", w.name) ? "page" : "false"', 'on', '!on', 'go', 'sw', 'today', 'busy ? " disabled" : ""',
    'o.refused ? " warn" : ""', 'm.ok === false ? " warn" : ""', 'orders.join("")', 'trades.join("")',
    'net == null ? "" : esc(usdS(net))', 'esc(DeskLab.missingText(DESKLAB_OK))', 'DeskLab.figures(w).map(fig).join("")',
    'net != null ? ` · today would be ${esc(usdS(net))', 'days.length ? `<div class="agroup feed static">${days.join("")',
    'notes.length ? `<div class="sec"><h2>On an account the Desk would refuse:</h2><div class="agroup feed static">${notes.join("")']);
  const raw = holes.filter((h) => !/^(esc|jsArg)\(/.test(h) && !flags.has(h));
  assert.deepEqual(raw, [], 'a template hole that is not esc / jsArg / a known flag');
});

test('a handler inside the Lab markup carries a name only as a JS string literal (jsArg) or a flag', () => {
  const handlers = [...LABVIEW.matchAll(/on(?:click|keydown)="([^"]*)"/g)].map((m) => m[1]);
  assert.ok(handlers.length >= 8, 'the rows, the switches, the actions');
  for (const h of handlers) {
    const holes = [...h.matchAll(/\$\{([^}]*)\}/g)].map((m) => m[1]);
    for (const x of holes) assert.match(x, /^(jsArg\(w\.name\)|!on|go)$/, h);
  }
  assert.match(LABVIEW, /const go = `setView\('lab',\$\{jsArg\(w\.name\)\}\)`/);
});

test('a hostile name and sentence from the network cannot break out of the page', () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const bad = row({ name: 'nq_orb', label: hostile, root: hostile, today: day({ state: 'stopped', why: hostile,
    orders: [{ t: hostile, text: hostile, refused: hostile }], trades: [{ side: 'long', qty: 1, entry_t: hostile, entry_px: 1, exit_t: null, exit_px: null, reason: hostile, net: 1 }] }),
    days: [day({ match: { ok: false, text: hostile } })], notes: [hostile] });
  const ctx = vm.createContext({ DeskLab: D, DESKLAB: { strategies: [bad], runner: ALIVE }, DESKLAB_OK: true, DESKLAB_BUSY: '', shortDay: (s) => s,
    esc: (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    usdS: D.usd, fmt: (v) => String(v), ST: { accounts: {} } });
  vm.runInContext(`const jsArg = (v) => esc(JSON.stringify(String(v == null ? "" : v)));\n${LABVIEW}\nglobalThis.html = labView("nq_orb");`, ctx);
  assert.doesNotMatch(ctx.html, /<img/);
  assert.match(ctx.html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(ctx.html, /Would be refused: &lt;img/);
});

test('the skin treats a Lab page like a watched one, reads the same helpers, and still talks to nobody', () => {
  assert.match(SKIN, /VIEW\.k === 'lab'/);
  assert.match(SKIN, /DeskLab\.setupRows/);
  assert.match(SKIN, /'Backtest'/);
  assert.doesNotMatch(SKIN, /\bfetch\(|XMLHttpRequest|WebSocket/);
});

/* ---- the Lab's side: Promote to Desk (charts/lab.js) ---- */
const LAB = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');
const LABDESK = LAB.slice(LAB.indexOf('/* ---- Promote to Desk (2026-10-09) ----'), LAB.indexOf('function paintRes()'));

test('the Lab asks the Desk list, promotes and removes by name, and never on a timer', () => {
  assert.ok(LABDESK.length > 1500, 'the section is there');
  const urls = [...new Set([...LAB.matchAll(/['"`](\/api\/tester\/desklab[^'"`$?]*)/g)].map((m) => m[1]))].sort();
  assert.deepEqual(urls, ['/api/tester/desklab', '/api/tester/desklab/promote', '/api/tester/desklab/remove']);
  assert.match(LAB, /send\('POST', '\/api\/tester\/desklab\/promote', \{ name: b\.name, run_id: r\.rid \}\)/);
  assert.match(LAB, /send\('POST', '\/api\/tester\/desklab\/remove', \{ name \}\)/);
  assert.doesNotMatch(LABDESK, /setInterval|setTimeout/, 'asked when the list opens and after each action only: nothing polls, hidden or not');
  assert.doesNotMatch(LAB, /:8850/, 'the Desk is reached through the page switcher\'s own link');
});

test('the row is only for drafts, re-resolved at click time, and an unusable one still says why', () => {
  assert.match(LABDESK, /function deskGo\(\) \{\n  const b = buf\(\), st = deskState\(b\);\n  if \(!st \|\| st\.disabled \|\| S\.deskBusy\) return;/);
  assert.match(LABDESK, /if \(!b \|\| b\.kind !== 'draft'\) return null;/);
  assert.match(LABDESK, /title="\$\{esc\(st\.hint\)\}"\$\{st\.disabled \? ' aria-disabled="true"' : ''\}/);
  assert.match(LAB, /\$\{deskRows\(b\)\}<\/div>/, 'the fourth row of the last group of a finished run');
});

test('Promote is not gated by the hash, and a promoted draft is marked in the library', () => {
  assert.match(LAB, /hasRun: !!\(r && r\.bundle && r\.rid\)/, 'a finished run is open: that is all the row asks of the run (the hash never gates Promote)');
  assert.doesNotMatch(LAB, /r\.sha === sha|started\.sha/);
  assert.match(LAB, /desk: !!\(S\.desk && S\.desk\.has\(d\.name\)\)/);
  assert.match(LAB, /<i class="lb-desk" title="On the Desk page">On the Desk<\/i>/);
});

test('the Lab says what Promote does now: it lands on the Desk switched off, and the empty state no longer says nothing runs there', () => {
  assert.doesNotMatch(LAB, /Nothing here ever runs on the desk|On the Desk, in shadow|On the Desk: shadow/);
  assert.match(LAB, /<p>Backtest it on real tick data in a sandbox, see every trade on the chart, and promote it to the Desk when you like what you see\.<\/p>/);
});


/* ---- fix round 1 ---- */
test('missingText: Loading until a read finished, "not answering" after a failed one, "not on the Desk" only after a good one', () => {
  assert.equal(D.missingText(null), 'Loading…');
  assert.equal(D.missingText(undefined), 'Loading…');
  assert.equal(D.missingText(false), 'The chart service is not answering, so this strategy cannot be shown right now.');
  assert.equal(D.missingText(true), 'That strategy is not on the Desk any more. Promote it again from the Lab.');
});

test('the page reads the list\'s outcome: only a good read can say the strategy is gone', () => {
  assert.match(HTML, /let DESKLAB = \{strategies: \[\], runner: null\}, DESKLAB_OK = null,/);
  assert.match(LABBLOCK, /next = \{strategies: DESKLAB\.strategies, runner: null\}; ok = false;/);
  assert.match(LABBLOCK, /DESKLAB = next; DESKLAB_OK = ok;/);
  assert.doesNotMatch(LABVIEW, /DeskLab\.GONE/, 'the page never picks the sentence itself');
});

test('specLine and the Setup card: session and bars when the record carries them, both shapes', () => {
  assert.equal(D.specLine(row({ session_window: ['09:25', '16:00'], bar_minutes: 1 })), 'NQ · 09:25-16:00 ET · 1-minute bars · from the Lab');
  assert.equal(D.specLine(row({ bar_minutes: 0 })), 'NQ · 09:25-16:00 ET · from the Lab', 'bar_minutes 0 = no bars: that part is left out');
  assert.equal(D.specLine(row({ session_window: undefined, bar_minutes: undefined })), 'NQ · from the Lab');
  const rows = (r) => Object.fromEntries(D.setupRows(r));
  assert.deepEqual([rows(row()).Session, rows(row()).Bars], ['09:25-16:00 ET', '1 min']);
  assert.deepEqual([rows(row({ bar_minutes: 0 })).Session, rows(row({ bar_minutes: 0 })).Bars], ['09:25-16:00 ET', '—']);
  assert.deepEqual([rows(row({ session_window: undefined, bar_minutes: undefined })).Session, rows(row({ session_window: undefined, bar_minutes: undefined })).Bars], ['—', '—']);
});

/* the desk's own render path with the Lab part broken: the page still shows nq930 */
const SLICE = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
function renderCtx({ deskLab, view = { k: 'today' } } = {}) {
  const els = {};
  const $ = (sel) => (els[sel] = els[sel] || { innerHTML: '', hidden: false });
  const ST = { armed: true, et_now: '2026-10-09T10:00:00-0400', timer: { strategies: {} }, accounts: {}, journal: [],
    strategies: { nq930: { cfg: { symbol: 'NQ', kind: 'straddle', offset_pts: 5, sl_pts: 5, tp_pts: 15, enabled: true, shadow: false, cancel_et: '12:55', flat_et: '15:55' }, day_status: 'idle', accounts: [] } } };
  const ctx = vm.createContext({ $, ST, DEMO: false, CHART: 'http://x', DESK_STALE: false, FREEZE: false, document: { hidden: false }, closeAsgMenus() {}, switchBounced() { return false; },
    toast() {}, chartPost: async () => ({}), confirmDlg: async () => false, fetch: async () => ({ ok: false }), ...(deskLab ? { DeskLab: deskLab } : {}) });
  vm.runInContext(SLICE('const esc = (v) =>', 'async function chartPost(') + SLICE('const stratLabel = ', 'const actStrat = ') + SLICE('const fmt = ', 'const usd = ') +
    'const usd = (v) => v == null ? "—" : (v < 0 ? "-$" : "$") + fmt(Math.abs(v));\n' +
    SLICE('/* ===== Desk views', 'function render() {') +
    `\nVIEW = ${JSON.stringify(view)}; DESKLAB = { strategies: [${JSON.stringify(row())}], runner: { alive: true } }; DESKLAB_OK = true;` +
    '\nglobalThis.go = () => { renderSide(["nq930"], 0, 0); renderMain(["nq930"], 0); };', ctx);
  return { ctx, els };
}
const BROKEN = [['desklab.js did not load (no DeskLab at all)', undefined],
  ['every DeskLab helper throws', Object.fromEntries(Object.keys(D).map((k) => [k, () => { throw new Error('boom'); }]))]];

test('a Lab part that throws, or a desklab.js that did not load, leaves the desk\'s own rows as they were', () => {
  for (const [why, dl] of BROKEN) {
    const { ctx, els } = renderCtx({ deskLab: dl });
    assert.doesNotThrow(() => ctx.go(), why);
    assert.match(els['#side'].innerHTML, /setView\('strat','nq930'\)/, why);
    assert.doesNotMatch(els['#side'].innerHTML, /setView\('lab'/, why);
    assert.match(els['#stratList'].innerHTML, /setView\('strat','nq930'\)/, `${why}: the Today row`);
    assert.doesNotMatch(els['#stratList'].innerHTML, /setView\('lab'/, why);
    assert.match(els['#side'].innerHTML, /Strategies<\/span><i>|Strategies/, why);
  }
});

test('the same page with a working DeskLab shows the Lab row next to nq930 (the control for the test above)', () => {
  const { ctx, els } = renderCtx({ deskLab: D });
  ctx.go();
  assert.match(els['#side'].innerHTML, /setView\('strat','nq930'\)/);
  assert.match(els['#side'].innerHTML, /setView\('lab',&quot;nq_orb&quot;\)/);
  assert.match(els['#stratList'].innerHTML, /setView\('strat','nq930'\)/);
  assert.match(els['#stratList'].innerHTML, /setView\('lab',&quot;nq_orb&quot;\)/);
  assert.match(els['#stratList'].innerHTML, /class="rp mono dim"/, 'the would-be net is dim, like the sidebar\'s');
});

test('a Lab strategy\'s page that throws says so in one line, and the back link stays', () => {
  for (const [why, dl] of BROKEN) {
    const { ctx, els } = renderCtx({ deskLab: dl, view: { k: 'lab', name: 'nq_orb' } });
    assert.doesNotThrow(() => ctx.go(), why);
    assert.match(els['#viewStrat'].innerHTML, /The Lab strategies could not be shown\./, why);
    assert.match(els['#viewStrat'].innerHTML, /setView\('today'\)/, why);
    assert.match(els['#side'].innerHTML, /setView\('strat','nq930'\)/, why);
  }
});

test('the #lab=<name> link is used once, and a link opened while the Desk is open switches to it', () => {
  assert.match(LABBLOCK, /history\.replaceState\(null, "", location\.pathname \+ location\.search\)/);
  assert.match(LABBLOCK, /if \(n\) \{ VIEW = \{k: "lab", name: n\}; clearLabHash\(\); \}/);
  assert.match(HTML, /window\.addEventListener\("hashchange", \(\) => \{[^}]*clearLabHash\(\); setView\("lab", n\);/);
  // the name is read with the same shape the server accepts
  const ctx = vm.createContext({ location: { hash: '#lab=nq_orb' } });
  vm.runInContext(LABBLOCK.slice(LABBLOCK.indexOf('function labHashName'), LABBLOCK.indexOf('function clearLabHash')) + 'globalThis.h = labHashName;', ctx);
  assert.equal(ctx.h(), 'nq_orb');
  for (const bad of ['#lab=', '#lab=NQ', '#lab=a', '#lab=nq_orb&x=1', '#lab=../x', '#strategy=nq_orb', '']) {
    ctx.location.hash = bad;
    assert.equal(ctx.h(), '', bad);
  }
});

test('the Lab lists only read: no pointer cursor, an amount never wraps, and Accounts keeps its locked button with its caption', () => {
  assert.match(HTML, /\.feed\.static \.feed-row\{ cursor:default; \}/);
  assert.match(HTML, /\.feed\.static \.t\{ white-space:nowrap; \}/);
  assert.match(HTML, /\.feed\.static \.t\.net\{ flex:0 0 auto; margin-left:auto; \}/);
  assert.equal((LABVIEW.match(/agroup feed static/g) || []).length, 3, 'today, days, notes: all static');
  assert.doesNotMatch(LABVIEW, /agroup feed"/);
  assert.match(LABVIEW, /<button class="btn btn-quiet noarrow btn-sm" disabled title="\$\{esc\(DeskLab\.ACCOUNTS_CAPTION\)\}">\+ Assign an account<\/button>\s*<div class="mcap">\$\{esc\(DeskLab\.ACCOUNTS_CAPTION\)\}<\/div>/);
});

test('the Lab\'s Promote row ties its hint to a line under the group (aria-describedby), and the hint is read from the same state', () => {
  assert.match(LAB, /aria-describedby="deskHint" title="\$\{esc\(st\.hint\)\}"/);
  assert.match(LAB, /<div class="rs-take" id="deskHint">\$\{esc\(st\.hint\)\}<\/div>/);
  assert.match(LAB, /\$\{deskRows\(b\)\}<\/div>\$\{deskNote\(b\)\}`;/);
});
