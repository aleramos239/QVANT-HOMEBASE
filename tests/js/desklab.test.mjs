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

test('orderLine: the time and "would ..." (shadow: nothing was sent); a refused order says why after "Would be refused:"', () => {
  assert.deepEqual({ ...D.orderLine({ t: '10:10:00', text: 'Sell at market, stop 22,014.25, target 21,954.25', refused: null }) },
    { t: '10:10:00', text: 'would sell at market, stop 22,014.25, target 21,954.25', refused: false });
  assert.deepEqual({ ...D.orderLine({ t: '09:30:01', text: 'Buy stop 1 at 21000.25', refused: null }) },
    { t: '09:30:01', text: 'would buy stop 1 at 21000.25', refused: false });
  for (const [said, shown] of [['Link the pair: one cancels the other', 'would link the pair: one cancels the other'],
    ['Cancel', 'would cancel'], ['Flatten (time)', 'would flatten (time)']]) {
    assert.equal(D.orderLine({ t: '09:30:00', text: said, refused: null }).text, shown);
  }
  assert.deepEqual({ ...D.orderLine({ t: '09:30:02', text: 'Sell stop 1 at 20990', refused: 'One position at a time.' }) },
    { t: '09:30:02', text: 'would sell stop 1 at 20990. Would be refused: One position at a time.', refused: true });
  assert.deepEqual({ ...D.orderLine({ t: '09:30:02', text: 'Sell stop 1 at 20990.', refused: 'Too late for a new trade today.' }) }.text,
    'would sell stop 1 at 20990. Would be refused: Too late for a new trade today.', 'no double full stop');
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
    { date: '2026-10-08', text: 'Matched the backtest: 3 of 3 trades.', ok: true, net: 80, rebuilt: false });
  assert.deepEqual({ ...D.matchLine(day({ date: '2026-10-07', net: -20, match: { ok: false, text: '1 trade differs.' } })) },
    { date: '2026-10-07', text: '1 trade differs.', ok: false, net: -20, rebuilt: false });
  assert.deepEqual({ ...D.matchLine(day({ match: null })) }, { date: '2026-10-09', text: 'Not checked yet.', ok: null, net: 0, rebuilt: false });
  assert.equal(D.matchLine(day({ rebuilt: true })).rebuilt, true, 'a day rebuilt by catch-up says so');
  assert.equal(D.matchLine(day({ rebuilt: 'yes' })).rebuilt, false, 'only true is true');
  // the list of past days is cut to these fields by the chart service: nothing else of a past day is read
  assert.deepEqual({ ...D.matchLine({ date: '2026-10-08', state: 'done', why: null, net: 80, match: { ok: true, text: 'x' }, rebuilt: true }) },
    { date: '2026-10-08', text: 'x', ok: true, net: 80, rebuilt: true });
  assert.equal(D.matchLine(day({ match: { ok: null, text: '' } })).text, 'Not checked yet.');
  assert.equal(D.matchLine(day({ match: { ok: 'yes', text: 'x' } })).ok, null, 'only true or false is a verdict');
  assert.deepEqual({ ...D.matchLine(null) }, { date: '', text: 'Not checked yet.', ok: null, net: null, rebuilt: false });
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

test('rebuiltNote: a day made by catch-up says so beside its state, while it runs or is done', () => {
  const at = (over, rn = ALIVE, on = true) => D.rebuiltNote(row({ enabled: on, today: day(over) }), rn);
  assert.equal(at({ state: 'running', rebuilt: true }), "rebuilt from today's prices");
  assert.equal(at({ state: 'done', rebuilt: true }), "rebuilt from today's prices");
  assert.equal(at({ state: 'running' }), '');
  assert.equal(at({ state: 'running', rebuilt: 1 }), '', 'only true is true');
  assert.equal(at({ state: 'waiting', rebuilt: true }), '');
  assert.equal(at({ state: 'stopped', rebuilt: true }), '');
  assert.equal(at({ state: 'running', rebuilt: true }, { alive: false }), '', 'the state line says the runner is not running');
  assert.equal(at({ state: 'running', rebuilt: true }, ALIVE, false), '', 'off');
  assert.equal(D.rebuiltNote(row(), ALIVE), '');
  assert.equal(D.rebuiltNote(null, null), '');
});

test('the words the page shows, exactly', () => {
  assert.equal(D.TAG_TITLE, 'It writes down its orders. Nothing is sent.');
  assert.equal(D.netTitle(row()), 'What it would have made today, after costs, 1 contract');
  assert.equal(D.netTitle(row({ qty: 2 })), 'What it would have made today, after costs, 2 contracts', 'the size it was promoted with');
  assert.equal(D.netTitle(row({ qty: undefined })), 'What it would have made today, after costs');
  assert.equal(D.netTitle(row({ qty: 0 })), 'What it would have made today, after costs');
  assert.equal(D.netTitle(null), 'What it would have made today, after costs');
  assert.equal('NET_TITLE' in D, false);
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
    'm.rebuilt ? \'<span class="t dim">rebuilt</span>\' : ""', 'rebuilt ? ` · ${esc(rebuilt)',
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

test('the page: "Today, in shadow", the size in the net\'s tooltip, and "rebuilt" by a day and in the state line', () => {
  assert.match(LABVIEW, /<div class="sec"><h2>Today, in shadow<\/h2>\$\{today\}<\/div>/);
  assert.doesNotMatch(LABVIEW, /<h2>Today<\/h2>/);
  assert.match(LABVIEW, /title="\$\{esc\(DeskLab\.netTitle\(w\)\)\}"/);
  assert.doesNotMatch(HTML, /DeskLab\.NET_TITLE/);
  const r = row({ qty: 2, today: day({ state: 'running', rebuilt: true, net: 50,
    orders: [{ t: '10:10:00', text: 'Sell at market, stop 22,014.25, target 21,954.25', refused: null }] }),
    days: [{ date: '2026-10-09', state: 'running', why: null, net: 50, match: null, rebuilt: true },
      { date: '2026-10-08', state: 'done', why: null, net: 80, match: { ok: true, text: 'Matched the backtest: 1 of 1 trade.' }, rebuilt: false }] });
  const ctx = vm.createContext({ DeskLab: D, DESKLAB: { strategies: [r], runner: ALIVE }, DESKLAB_OK: true, DESKLAB_BUSY: '', shortDay: (s) => s,
    esc: (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    usdS: D.usd, fmt: (v) => String(v), ST: { accounts: {} } });
  vm.runInContext(`const jsArg = (v) => esc(JSON.stringify(String(v == null ? "" : v)));\n${LABVIEW}\nglobalThis.html = labView("nq_orb"); globalThis.rowHtml = todayLabRow(DESKLAB.strategies[0]);`, ctx);
  assert.match(ctx.html, /<span class="t">10:10:00<\/span><span class="h">would sell at market, stop 22,014\.25, target 21,954\.25<\/span>/);
  assert.match(ctx.html, /<b>Running in shadow<\/b> · rebuilt from today&#39;s prices · today would be \+\$50/);
  assert.equal((ctx.html.match(/<span class="t dim">rebuilt<\/span>/g) || []).length, 1, 'beside the rebuilt day only');
  assert.match(ctx.html, /2026-10-09<\/span><span class="h">Not checked yet\.<\/span><span class="t dim">rebuilt<\/span>/);
  assert.match(ctx.rowHtml, /title="What it would have made today, after costs, 2 contracts"/);
});

test('removeDeskLab renders only once the desk\'s status is in, like its neighbours', async () => {
  const fn = LABBLOCK.slice(LABBLOCK.indexOf('async function removeDeskLab'), LABBLOCK.indexOf('function openDeskLabInLab'));
  assert.equal((fn.match(/render\(\)/g) || []).length, 2);
  assert.equal((fn.match(/if \(ST\) render\(\)/g) || []).length, 2, 'never a bare render()');
  const run = async (ST) => {
    let renders = 0;
    const ctx = vm.createContext({ ST, DEMO: false, FREEZE: false, CHART: '', VIEW: { k: 'lab', name: 'nq_orb' }, DeskLab: D, document: { hidden: true },
      location: { hash: '' }, history: { replaceState() {} }, switchBounced: () => false, toast() {}, confirmDlg: async () => true,
      chartPost: async () => ({ ok: true }), render() { if (!ST) throw new Error('render() with no status'); renders += 1; } });
    vm.runInContext(`${LABBLOCK}\nDESKLAB = { strategies: [{ name: 'nq_orb' }], runner: null };\nglobalThis.go = () => removeDeskLab('nq_orb'); globalThis.left = () => DESKLAB.strategies.length;`, ctx);
    await ctx.go();
    return [renders, ctx.left()];
  };
  assert.deepEqual(await run(null), [0, 0], 'no status yet: it is removed and nothing renders (or throws)');
  assert.deepEqual(await run({ strategies: {} }), [2, 0]);
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

/* ======================================================================================================================
   Step B, task B6: a promoted Lab strategy that the Desk itself knows (desk id lab_<name>, kind "lab", a `lab` block in
   /api/status). The pure half: the state words, the dot, the limits rows and their checks, the round and refused lines, the
   sentences. The words are the design's table (section E), exactly.
   ====================================================================================================================== */
const MARK = ['abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789', '2026-10-09T18:03:00+00:00'];
const LIM = { max_trades_day: 2, max_qty: 1, max_risk_usd: 300, last_entry_et: '11:00', flat_et: '15:55' };
const labBlock = (over = {}) => ({ name: 'nq_orb', mark: MARK, limits: LIM, state: 'waiting', why: null, trades_today: 0, mode_today: null,
  runner: { alive: true, age_s: 1.2 }, rounds: [], refused: [], read_only: false, ...over });
const deskStrat = (labOver = {}, cfgOver = {}) => ({ cfg: { symbol: 'NQ', kind: 'lab', label: 'NQ ORB', enabled: true, qty: 1, shadow: false, ...cfgOver },
  day_status: 'idle', killed: false, accounts: [], lab: labBlock(labOver) });

test('onDesk: a chart-service row is skipped when the Desk knows lab_<name> (one row, never two)', () => {
  assert.equal(D.deskId('nq_orb'), 'lab_nq_orb');
  assert.equal(D.onDesk({ lab_nq_orb: {} }, row()), true);
  assert.equal(D.onDesk({ nq930: {}, lab_other: {} }, row()), false);
  assert.equal(D.onDesk({}, row()), false);
  assert.equal(D.onDesk(null, row()), false);
  assert.equal(D.onDesk(undefined, row()), false);
  assert.equal(D.onDesk({ lab_nq_orb: {} }, null), false);
  assert.equal(D.onDesk({ lab_nq_orb: {} }, { label: 'x' }), false, 'a row with no name is never skipped');
  assert.equal(D.onDesk({ nq_orb: {} }, row()), false, 'the plain name is not the desk id');
  assert.equal(D.onDesk({ constructor: 1 }, { name: 'constructor' }), false, 'inherited keys do not count');
});

test('deskState: one word for each state the server sends, from the design\'s table', () => {
  const at = (state, why = null, cfg = {}) => D.deskState(deskStrat({ state, why }, cfg));
  assert.equal(at('off', null, { enabled: false }), 'Off');
  assert.equal(at('shadow'), 'Running in shadow');
  assert.equal(at('waiting'), 'Waiting for the session');
  assert.equal(at('watching'), 'Watching');
  assert.equal(at('working'), 'Order working');
  assert.equal(at('in_position'), 'In position');
  assert.equal(at('done'), 'Done for today');
  assert.equal(at('runner_down'), 'Runner down');
  assert.equal(at('check'), 'Check it');
  assert.equal(at('disarmed'), 'Disarmed: written down only');
});

test('deskState: stopped. A real cause reads "Stopped: <why>"; ON and stopped for today by the switch reads "Starts with the next session."', () => {
  const at = (why, cfg = {}) => D.deskState(deskStrat({ state: 'stopped', why }, cfg));
  assert.equal(at('Could not pick up where it left off.'), 'Stopped: Could not pick up where it left off.');
  assert.equal(at('Killed today.'), 'Stopped: Killed today.');
  assert.equal(at('The strategy raised an error.'), 'Stopped: The strategy raised an error.');
  assert.equal(at('off'), 'Starts with the next session.', 'never "Stopped: off"');
  assert.equal(at('Stopped for today.'), 'Starts with the next session.', 'never "Stopped: Stopped for today."');
  assert.equal(at(''), 'Starts with the next session.');
  assert.equal(at(null), 'Starts with the next session.');
  assert.doesNotMatch(at('off'), /Stopped/);
  assert.equal(D.startsNext(deskStrat({ state: 'stopped', why: 'off' })), true);
  assert.equal(D.startsNext(deskStrat({ state: 'stopped', why: 'Killed today.' })), false);
  assert.equal(D.startsNext(deskStrat({ state: 'waiting' })), false);
});

test('deskState: a state the table has no word for shows the server\'s own sentence; with none, "Check it"; no lab block is "Check it"', () => {
  assert.equal(D.deskState(deskStrat({ state: 'something_new', why: 'The server said this.' })), 'The server said this.');
  assert.equal(D.deskState(deskStrat({ state: 'something_new', why: null })), 'Check it');
  assert.equal(D.deskState(deskStrat({ state: undefined })), 'Check it');
  assert.equal(D.deskState({ cfg: { kind: 'lab' } }), 'Check it');
  assert.equal(D.deskState(null), 'Check it');
});

test('deskDot: off / shadow / live / warn, in step with the words', () => {
  const at = (state, why = null) => D.deskDot(deskStrat({ state, why }));
  assert.equal(at('off'), 'off');
  assert.equal(at('shadow'), 'shadow');
  assert.equal(at('waiting'), '');
  assert.equal(at('watching'), '');
  assert.equal(at('done'), '');
  assert.equal(at('working'), 'live');
  assert.equal(at('in_position'), 'live');
  assert.equal(at('stopped', 'off'), '', 'nothing is wrong: it starts with the next session');
  assert.equal(at('stopped', 'Could not pick up where it left off.'), 'warn');
  for (const s of ['runner_down', 'check', 'disarmed', 'something_new']) assert.equal(at(s), 'warn', s);
  assert.equal(D.deskDot(null), 'warn');
});

test('read_only: "Another Desk is running on this store." shows from the field; the picker and Limits are locked then', () => {
  assert.equal(D.OTHER_DESK, 'Another Desk is running on this store.');
  assert.equal(D.readOnly(deskStrat({ read_only: true })), true);
  assert.equal(D.readOnly(deskStrat({ read_only: false })), false);
  assert.equal(D.readOnly(deskStrat({ read_only: 1 })), false, 'only true is true');
  assert.equal(D.readOnly(null), false);
});

test('the picker is locked with the caption until limits exist, and when another Desk owns the store', () => {
  assert.equal(D.LIMITS_CAPTION, 'Set the limits first. Then assign an account.');
  assert.deepEqual({ ...D.accountsLock(deskStrat({ limits: null })) }, { locked: true, caption: 'Set the limits first. Then assign an account.' });
  assert.deepEqual({ ...D.accountsLock(deskStrat()) }, { locked: false, caption: '' });
  assert.deepEqual({ ...D.accountsLock(deskStrat({ read_only: true })) }, { locked: true, caption: 'Another Desk is running on this store.' });
  assert.deepEqual({ ...D.accountsLock(deskStrat({ read_only: true, limits: null })) }, { locked: true, caption: 'Another Desk is running on this store.' });
  assert.equal(D.accountsLock(deskStrat({ state: 'check', limits: null })).locked, true, 'check it, no limits: still locked');
  assert.equal(D.accountsLock(null).locked, true, 'fail closed');
});

test('the notes: with no account, and with accounts', () => {
  assert.equal(D.deskNote(false), 'From the Lab. With no account it runs in shadow: it writes down its orders and nothing is sent.');
  assert.equal(D.deskNote(true), 'From the Lab. Its orders go to the accounts below. Every entry carries a stop held at the broker.');
});

test('inShadow: the day\'s mode when the server says, else no book rows', () => {
  assert.equal(D.inShadow(deskStrat({ mode_today: 'shadow' }), [{ account: 'a', qty: 1 }]), true, 'assigned mid-session: the day began in shadow');
  assert.equal(D.inShadow(deskStrat({ mode_today: 'desk' }), []), false);
  assert.equal(D.inShadow(deskStrat({ mode_today: null }), []), true);
  assert.equal(D.inShadow(deskStrat({ mode_today: null }), undefined), true);
  assert.equal(D.inShadow(deskStrat({ mode_today: null }), [{ account: 'a', qty: 1 }]), false);
});

test('limitsRows: the five rows with the table\'s words; a dash for limits not set', () => {
  assert.deepEqual(D.limitsRows(LIM).map((r) => `${r.k}=${r.v}`), ['Trades a day=2', 'Most contracts per account=1', 'Most at risk per trade=$300',
    'No new trade after=11:00 ET', 'Flat by=15:55 ET']);
  assert.deepEqual(D.limitsRows({ ...LIM, max_risk_usd: 1250.5 })[2].v, '$1,251');
  assert.deepEqual(D.limitsRows(null).map((r) => r.v), ['—', '—', '—', '—', '—']);
  assert.deepEqual(D.limitsRows(undefined).map((r) => r.v), ['—', '—', '—', '—', '—']);
  assert.deepEqual(D.limitsRows({}).map((r) => r.v), ['—', '—', '—', '—', '—']);
});

test('limitsFields: what the dialog shows when it opens', () => {
  assert.deepEqual({ ...D.limitsFields(LIM) }, { trades: '2', qty: '1', risk: '300', last: '11:00', flat: '15:55' });
  assert.deepEqual({ ...D.limitsFields({ ...LIM, max_risk_usd: 312.5 }) }, { trades: '2', qty: '1', risk: '312.5', last: '11:00', flat: '15:55' });
  assert.deepEqual({ ...D.limitsFields(null) }, { trades: '', qty: '1', risk: '', last: '', flat: '' }, 'default 1 contract (ruling Q1)');
});

const F = (over = {}) => ({ trades: '2', qty: '1', risk: '300', last: '11:00', flat: '15:55', ...over });

test('checkLimits: good fields give the body that is posted, exactly what the fields say', () => {
  const got = D.checkLimits(F());
  assert.deepEqual({ ...got.errors }, {});
  assert.deepEqual({ ...got.body }, LIM);
  assert.deepEqual({ ...D.checkLimits(F({ trades: ' 20 ', qty: '10', risk: '$1,250.50', last: '09:30', flat: '09:31' })).body },
    { max_trades_day: 20, max_qty: 10, max_risk_usd: 1250.5, last_entry_et: '09:30', flat_et: '09:31' });
});

test('checkLimits: "Trades a day: a whole number from 1 to 20."', () => {
  const say = 'Trades a day: a whole number from 1 to 20.';
  for (const bad of ['', '0', '21', '-1', '1.5', 'two', '1e1', ' ', '2 trades']) {
    const got = D.checkLimits(F({ trades: bad }));
    assert.equal(got.errors.trades, say, JSON.stringify(bad));
    assert.equal(got.body, null);
  }
  assert.equal(D.checkLimits(F({ trades: '1' })).errors.trades, undefined);
  assert.equal(D.checkLimits(F({ trades: '20' })).errors.trades, undefined);
});

test('checkLimits: "Contracts: a whole number from 1 to 10."', () => {
  const say = 'Contracts: a whole number from 1 to 10.';
  for (const bad of ['', '0', '11', '-2', '2.5', 'x']) assert.equal(D.checkLimits(F({ qty: bad })).errors.qty, say, JSON.stringify(bad));
  assert.equal(D.checkLimits(F({ qty: '10' })).errors.qty, undefined);
  assert.equal(D.checkLimits(F({ qty: '1' })).errors.qty, undefined);
});

test('checkLimits: "At risk per trade: a dollar amount above 0."', () => {
  const say = 'At risk per trade: a dollar amount above 0.';
  for (const bad of ['', '0', '0.00', '-5', 'lots', '1e3', '$', '12abc', '1000000001', 'Infinity']) {
    assert.equal(D.checkLimits(F({ risk: bad })).errors.risk, say, JSON.stringify(bad));
  }
  for (const good of ['0.01', '300', '$300', '1,250.5', '1000000000']) assert.equal(D.checkLimits(F({ risk: good })).errors.risk, undefined, good);
});

test('checkLimits: "No new trade after: a time like 11:00, before the flat time."', () => {
  const say = 'No new trade after: a time like 11:00, before the flat time.';
  for (const bad of ['', '9:30', '24:00', '11:60', '11', '11:0', 'noon', '11:00 ET', '11:00:00']) assert.equal(D.checkLimits(F({ last: bad })).errors.last, say, JSON.stringify(bad));
  assert.equal(D.checkLimits(F({ last: '15:55' })).errors.last, say, 'not before the flat time');
  assert.equal(D.checkLimits(F({ last: '16:00', flat: '15:55' })).errors.last, say);
  assert.equal(D.checkLimits(F({ last: '09:24' }), '09:25').errors.last, say, 'before the session starts');
  assert.equal(D.checkLimits(F({ last: '09:25' }), '09:25').errors.last, undefined, 'at the start is allowed');
  assert.equal(D.checkLimits(F({ last: '09:24' })).errors.last, say, 'the default session start is 09:25');
  assert.equal(D.checkLimits(F({ last: '09:00' }), '08:30').errors.last, undefined, 'the strategy\'s own start');
  assert.equal(D.checkLimits(F({ last: '15:54' })).errors.last, undefined);
});

test('checkLimits: "Flat by: a time like 15:55, no later than 15:55."', () => {
  const say = 'Flat by: a time like 15:55, no later than 15:55.';
  for (const bad of ['', '3:55', '15:56', '16:00', '25:00', 'close', '15:55 ET']) assert.equal(D.checkLimits(F({ flat: bad })).errors.flat, say, JSON.stringify(bad));
  assert.equal(D.checkLimits(F({ flat: '15:55' })).errors.flat, undefined);
  assert.equal(D.checkLimits(F({ flat: '12:00', last: '11:00' })).errors.flat, undefined);
});

test('checkLimits: every wrong field is said at once, one sentence each, and nothing is posted', () => {
  const got = D.checkLimits({ trades: '0', qty: '0', risk: '0', last: 'x', flat: 'y' });
  assert.deepEqual(Object.keys(got.errors).sort(), ['flat', 'last', 'qty', 'risk', 'trades']);
  assert.equal(got.body, null);
  assert.deepEqual({ ...D.checkLimits(null).errors }.trades, 'Trades a day: a whole number from 1 to 20.');
});

test('the limits dialog\'s words', () => {
  assert.equal(D.limitsTitle('NQ ORB'), 'Limits for NQ ORB');
  assert.equal(D.EDIT_LIMITS, 'Edit limits');
  assert.equal(D.SAVE_LIMITS, 'Save limits');
  assert.equal(D.CANCEL, 'Cancel');
});

test('refusalText: the server\'s own sentence, with no prefix; a plain one when there is none', () => {
  assert.equal(D.refusalText({ detail: 'Flatten it first.' }), 'Flatten it first.');
  assert.equal(D.refusalText({ detail: 'Not 09:20-09:35 ET. Try again after 09:35.' }), 'Not 09:20-09:35 ET. Try again after 09:35.');
  assert.equal(D.refusalText({ error: 'write guard said no' }), 'write guard said no');
  assert.equal(D.refusalText({ detail: ['a list'] }), 'The Desk is not answering.');
  assert.equal(D.refusalText({}), 'The Desk is not answering.');
  assert.equal(D.refusalText(null), 'The Desk is not answering.');
  assert.equal(D.refusalText(null, new Error('x')), 'The Desk is not answering.');
  assert.equal(D.refusalText({ detail: '   ' }), 'The Desk is not answering.');
  assert.equal(D.refusalText({ detail: 'x'.repeat(500) }).length, 200);
});

test('roundLine: a trade of today, one line, with the account; a failed entry shows its reason and the broker\'s words', () => {
  const r = (over = {}) => ({ account: 'a1', round: 1, status: 'done', side: 'Buy', qty: 2, entry_fill: 21000.25, exit_fill: 21010.5, exit_reason: 'tp', pnl: 205, why: null, carried: false, date: '2026-10-10', ...over });
  assert.deepEqual({ ...D.roundLine(r(), 'APEX…048') }, { text: 'APEX…048 · Buy 2 · 21,000.25 to 21,010.50 · at the target', net: 205, bad: false, detail: '', carried: false });
  assert.equal(D.roundLine(r({ exit_reason: 'sl', pnl: -150 }), 'A').text, 'A · Buy 2 · 21,000.25 to 21,010.50 · at the stop');
  assert.equal(D.roundLine(r({ exit_reason: 'sl', pnl: -150 }), 'A').net, -150);
  assert.equal(D.roundLine(r({ exit_reason: 'flat' }), 'A').text, 'A · Buy 2 · 21,000.25 to 21,010.50 · closed at the flat time');
  assert.equal(D.roundLine(r({ exit_reason: 'manual_flat' }), 'A').text, 'A · Buy 2 · 21,000.25 to 21,010.50 · flattened by hand');
  assert.equal(D.roundLine(r({ exit_reason: 'odd_new_reason' }), 'A').text, 'A · Buy 2 · 21,000.25 to 21,010.50 · odd new reason', 'an unknown reason is shown plainly, never hidden');
  assert.equal(D.roundLine(r({ status: 'live', exit_fill: null, exit_reason: null, pnl: null }), 'A').text, 'A · Buy 2 · in at 21,000.25 · In position');
  assert.equal(D.roundLine(r({ status: 'placed', entry_fill: null, exit_fill: null, exit_reason: null, pnl: null }), 'A').text, 'A · Buy 2 · Order working');
  assert.equal(D.roundLine(r({ status: 'placing', entry_fill: null, exit_fill: null, exit_reason: null, pnl: null }), 'A').text, 'A · Buy 2 · Order working');
  assert.equal(D.roundLine(r({ status: 'live', exit_fill: null, pnl: null, exit_reason: null }), 'A').net, null);
  const failed = D.roundLine(r({ status: 'error', entry_fill: null, exit_fill: null, exit_reason: 'error', pnl: null, why: 'The Desk cannot check this order.', detail: 'Insufficient margin' }), 'A');
  assert.equal(failed.text, 'A · Buy 2 · The Desk cannot check this order.');
  assert.equal(failed.bad, true);
  assert.equal(failed.detail, 'The broker refused it: Insufficient margin');
  assert.equal(D.roundLine(r({ status: 'error', why: 'x', detail: 'The broker refused it: Insufficient margin' }), 'A').detail, 'The broker refused it: Insufficient margin', 'the prefix is never doubled');
  assert.equal(D.roundLine(r({ status: 'error', why: 'The Desk cannot check this order.' }), 'A').detail, '', 'no detail on the row: none shown');
  assert.equal(D.roundLine(r({ status: 'error', why: null }), 'A').text, 'A · Buy 2 · Check it', 'a failed entry with no sentence still says so');
  assert.equal(D.roundLine(r({ side: 'Sell', qty: 1 }), '').text, 'Sell 1 · 21,000.25 to 21,010.50 · at the target', 'no account label: none shown');
  assert.equal(D.roundLine(null, 'A').text, '', 'not a row');
});

test('roundLine: a block carried from an earlier day is its own thing, with the row\'s sentence and its day', () => {
  const c = D.roundLine({ account: 'a1', round: 1, status: 'error', side: 'Buy', qty: 1, entry_fill: 21000, exit_fill: null, exit_reason: 'carried', pnl: null,
    why: "The Desk cannot check the last trade's orders.", carried: true, date: '2026-10-09' }, 'APEX…048');
  assert.equal(c.carried, true);
  assert.equal(c.bad, true);
  assert.match(c.text, /^APEX…048 · /);
  assert.match(c.text, /The Desk cannot check the last trade's orders\.$/);
  assert.match(c.text, /Oct 9/);
  assert.equal(c.net, null, 'an old trade has no number of today');
  assert.equal(D.roundLine({ account: 'a', carried: true, date: 'junk', why: 'x' }, '').text, 'x');
});

test('splitRounds: today\'s trades and the old blocks are apart; an old trade is never counted in today\'s', () => {
  const rows = [{ account: 'a1', carried: true, date: '2026-10-09' }, { account: 'a1', carried: false }, { account: 'a2', carried: false }, null, 'junk'];
  const got = D.splitRounds(rows);
  assert.equal(got.today.length, 2);
  assert.equal(got.old.length, 1);
  assert.equal(got.old[0].account, 'a1');
  assert.deepEqual({ ...D.splitRounds(undefined) }, { today: [], old: [] });
  assert.equal(D.OLD_TITLE, 'From an earlier day');
  assert.equal(D.CLEAR, 'Clear');
});

test('refusedLine: the time and the server\'s sentence, with the account when it names one', () => {
  assert.deepEqual({ ...D.refusedLine({ t: '09:31:02', text: 'The price is already past this entry.', account: 'a1' }, 'APEX…048') },
    { t: '09:31:02', text: 'The price is already past this entry. (APEX…048)' });
  assert.deepEqual({ ...D.refusedLine({ t: '09:31:02', text: 'It is off.', account: null }, '') }, { t: '09:31:02', text: 'It is off.' });
  assert.deepEqual({ ...D.refusedLine(null, '') }, { t: '', text: '' });
});

test('the switch and flatten sentences, exactly', () => {
  assert.equal(D.switchOnAccounts('NQ ORB'), 'NQ ORB is ON. Its orders go to its accounts.');
  assert.equal(D.switchOnShadow('NQ ORB'), 'NQ ORB is ON: it runs in shadow.');
  assert.equal(D.switchOnNext('NQ ORB'), 'NQ ORB is ON. It starts with the next session.');
  assert.equal(D.switchOff('NQ ORB'), 'NQ ORB is OFF. Unfilled orders are cancelled. An open position keeps its stop and is closed at the flat time.');
  assert.deepEqual({ ...D.flattenAsk('NQ ORB') }, { title: 'Flatten NQ ORB?', body: 'Cancels its orders, closes its own position on every account, and switches it OFF.', action: 'Flatten & turn off' });
  assert.equal(D.BOOKED_NEXT, 'Booked. It starts with the next session.');
  assert.equal(D.LIVE_NOTE, 'It will trade real money on its next order. Every entry carries a stop held at the broker.');
  assert.equal(D.CLEARED, 'Cleared.');
});

test('switchOnToast picks the sentence: stopped for today first, then with accounts, then shadow', () => {
  const s = (l) => deskStrat(l);
  assert.equal(D.switchOnToast('N', s({ state: 'stopped', why: 'off' }), [{ account: 'a', qty: 1 }]), 'N is ON. It starts with the next session.');
  assert.equal(D.switchOnToast('N', s({ state: 'waiting' }), [{ account: 'a', qty: 1 }]), 'N is ON. Its orders go to its accounts.');
  assert.equal(D.switchOnToast('N', s({ state: 'shadow' }), []), 'N is ON: it runs in shadow.');
  assert.equal(D.switchOnToast('N', s({ state: 'stopped', why: 'Killed today.' }), [{ account: 'a', qty: 1 }]), 'N is ON. Its orders go to its accounts.', 'a real cause is not "next session"');
  assert.equal(D.switchOnToast('N', null, []), 'N is ON: it runs in shadow.');
});

test('flattenSteps: a Lab flatten\'s own plain steps are not failures', () => {
  const got = D.flattenSteps({ a1: ['cancel entry 7: ok', 'This trade had already ended.', 'nothing of its own is left to close', 'market Sell 1: ok'], a2: ['market Sell 1: refused'] });
  assert.deepEqual({ ...got }, { a1: ['cancel entry 7: ok', 'market Sell 1: ok'], a2: ['market Sell 1: refused'] });
  assert.deepEqual({ ...D.flattenSteps({ a: ['the account is already flat', 'check it — x; nothing sold; stops left working'] }) }, { a: ['the account is already flat', 'check it — x; nothing sold; stops left working'] });
  assert.equal(D.flattenSteps(null), null);
  assert.deepEqual(D.flattenSteps({ a: 'not a list' }), { a: 'not a list' });
});

test('deskSpec: market, the session when the Lab row knows it, and where it came from', () => {
  assert.equal(D.deskSpec({ symbol: 'NQ' }, row()), 'NQ · 09:25-16:00 ET · from the Lab');
  assert.equal(D.deskSpec({ symbol: 'NQ' }, null), 'NQ · from the Lab');
  assert.equal(D.deskSpec({ symbol: 'NQ' }, row({ session_window: undefined })), 'NQ · from the Lab');
  assert.equal(D.deskSpec({}, null), 'from the Lab');
});

test('deskSetupRows: the Setup card of a Lab strategy on the Desk, in the brief\'s order and words', () => {
  const rows = D.deskSetupRows(deskStrat({ mode_today: null }), row(), []);
  assert.deepEqual(rows.map((r) => r[0]), ['Instrument', 'Session', 'Bars', 'Trades a day', 'Most contracts', 'Most at risk', 'No new trade after', 'Flat', 'Promoted', 'Code', 'Orders']);
  assert.deepEqual(rows.map((r) => r[1]), ['NQ', '09:25-16:00 ET', '1 min', '2', '1', '$300', '11:00 ET', '15:55 ET', 'Oct 9, 2026', 'abcdef01', 'Shadow']);
  const t = (s, book) => Object.fromEntries(D.deskSetupRows(s, row(), book)).Orders;
  assert.equal(t(deskStrat({ mode_today: 'desk' }), []), 'Through the Desk');
  assert.equal(t(deskStrat({ mode_today: 'shadow' }), [{ account: 'a', qty: 1 }]), 'Shadow');
  assert.equal(t(deskStrat({ mode_today: null }), [{ account: 'a', qty: 1 }]), 'Through the Desk');
  const bare = Object.fromEntries(D.deskSetupRows(deskStrat({ limits: null, mark: null }), null, []));
  assert.deepEqual([bare.Session, bare.Bars, bare['Trades a day'], bare['Most contracts'], bare['Most at risk'], bare['No new trade after'], bare.Flat, bare.Promoted, bare.Code],
    ['—', '—', '—', '—', '—', '—', '—', '—', '—']);
  assert.deepEqual(D.deskSetupRows(null, null, []), []);
});

test('the activity lines of the Lab\'s journal events, in simple words', () => {
  const A = D.activity;
  assert.deepEqual(A.lab_refused({ text: 'The price is already past this entry.', account: 'a1' }, 'NQ ORB', ' on APEX…048'), ['NQ ORB order refused on APEX…048 — The price is already past this entry.', 'warn']);
  assert.deepEqual(A.lab_refused({ text: 'It is off.' }, 'NQ ORB', ''), ['NQ ORB order refused — It is off.', 'warn']);
  assert.deepEqual(A.lab_runner_down({}, 'NQ ORB', ''), ['NQ ORB: runner down', 'neg']);
  assert.deepEqual(A.lab_runner_back({}, 'NQ ORB', ''), ['NQ ORB: runner back']);
  assert.deepEqual(A.lab_stopped({ why: 'off' }, 'NQ ORB', ''), ['NQ ORB stopped for today']);
  assert.deepEqual(A.lab_stopped({ why: 'Stopped for today.' }, 'NQ ORB', ''), ['NQ ORB stopped for today']);
  assert.deepEqual(A.lab_stopped({ why: 'The strategy raised an error.' }, 'NQ ORB', ''), ['NQ ORB stopped for today — The strategy raised an error.', 'warn']);
  assert.deepEqual(A.lab_flatten({ results: { a1: { ok: true, actions: ['market Sell 1: ok'] } } }, 'NQ ORB', ''), ['NQ ORB flattened on 1 account']);
  assert.deepEqual(A.lab_flatten({ results: { a1: { ok: true }, a2: { ok: true } } }, 'NQ ORB', ''), ['NQ ORB flattened on 2 accounts']);
  assert.deepEqual(A.lab_flatten({ results: { a1: { ok: false, actions: ['check it — x'] } } }, 'NQ ORB', ''), ['NQ ORB flatten — check it on 1 account', 'neg']);
  assert.deepEqual(A.lab_flatten({ results: {} }, 'NQ ORB', ''), ['NQ ORB flatten — nothing was open']);
  assert.deepEqual(A.lab_cancelled({ ended: true }, 'NQ ORB', ' on APEX…048'), ['NQ ORB entry cancelled on APEX…048']);
  assert.deepEqual(A.lab_cancelled({ ended: false, part: 1 }, 'NQ ORB', ' on A'), ['NQ ORB entry cancelled on A — part of it had filled', 'warn']);
  assert.deepEqual(A.lab_round({ round: 2, qty: 1 }, 'NQ ORB', ' on A'), ['NQ ORB trade 2 started on A (1 contract)']);
  assert.deepEqual(A.lab_settled({}, 'NQ ORB', ' on A'), ['NQ ORB: every order of the last trade has ended on A']);
  assert.deepEqual(A.lab_limits_set({ limits: LIM }, 'NQ ORB', ''), ['NQ ORB limits set: 2 trades a day, up to 1 contract, $300 at risk, no new trade after 11:00, flat by 15:55']);
  assert.deepEqual(A.lab_limits_set({ limits: { ...LIM, max_trades_day: 1, max_qty: 3 } }, 'NQ ORB', '')[0], 'NQ ORB limits set: 1 trade a day, up to 3 contracts, $300 at risk, no new trade after 11:00, flat by 15:55');
  assert.deepEqual(A.lab_limits_set({}, 'NQ ORB', ''), ['NQ ORB limits set']);
  assert.deepEqual(A.lab_check({ reason: 'x' }, 'NQ ORB', ' on A'), ['NQ ORB needs a check on A — x', 'neg']);
  assert.deepEqual(A.lab_carry({ date: '2026-10-09' }, 'NQ ORB', ' on A'), ['NQ ORB: a trade from 2026-10-09 is still unchecked on A', 'warn']);
  assert.deepEqual(A.lab_carry_cleared({ date: '2026-10-09', why: 'by hand' }, 'NQ ORB', ' on A'), ['NQ ORB: the old trade from 2026-10-09 was cleared on A']);
  assert.deepEqual(A.lab_exit_unconfirmed({}, 'NQ ORB', ' on A'), ['NQ ORB: the close was not confirmed on A. Its stop is still working.', 'neg']);
  assert.deepEqual(A.lab_cancel_raced_fill({}, 'NQ ORB', ' on A'), ['NQ ORB: an entry filled as it was cancelled on A', 'warn']);
  assert.deepEqual(A.lab_open_without_cfg({}, 'NQ ORB', ' on A'), ['NQ ORB has a trade open but is not on this Desk. Check it.', 'neg']);
  assert.deepEqual(A.lab_removed({}, 'NQ ORB', ''), ['NQ ORB taken off the Desk']);
});

test('bookedNext: an account added while the day runs in shadow starts with the next session', () => {
  const one = [{ account: 'a1', qty: 1 }], two = [{ account: 'a1', qty: 1 }, { account: 'a2', qty: 1 }];
  assert.equal(D.bookedNext(deskStrat({ mode_today: 'shadow' }), [], one), true);
  assert.equal(D.bookedNext(deskStrat({ mode_today: 'shadow' }), one, two), true);
  assert.equal(D.bookedNext(deskStrat({ mode_today: 'shadow' }), two, one), false, 'taking one off');
  assert.equal(D.bookedNext(deskStrat({ mode_today: 'shadow' }), one, one), false, 'a size change');
  assert.equal(D.bookedNext(deskStrat({ mode_today: 'desk' }), [], one), false);
  assert.equal(D.bookedNext(deskStrat({ mode_today: null }), [], one), false, 'the session has not begun: nothing to wait for');
  assert.equal(D.bookedNext(deskStrat({ mode_today: 'shadow' }, { enabled: false }), [], one), false, 'switched off: it starts when it is switched on');
  assert.equal(D.bookedNext(null, [], one), false);
});
