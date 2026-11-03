import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

/* Design package 5 (2026-10-27): one gear, one moon, one close glyph, a trash for removal, and plain words (Desk results,
   Last entry / Flat by, a verb on the dialog button, Color / Payout, "58%", durations one way). CSS and markup cannot be
   rendered here, so these read the real files. */
const require = createRequire(import.meta.url);
const STATIC = path.resolve(import.meta.dirname, '../../homebase/static');
const read = (f) => fs.readFileSync(path.join(STATIC, f), 'utf8');
const icon = (name) => new RegExp(`^  ${name}: svg\\('(.*)'\\),$`, 'm').exec(read('charts/icons.js'))[1];

/* The text of every string literal in a script (comments and code left out): the words a person can read. */
function strings(src) {
  const out = [];
  let i = 0, prev = '';
  while (i < src.length) {
    const c = src[i], n = src[i + 1];
    if (c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i++; continue; }
    if (c === '/' && n === '*') { i = src.indexOf('*/', i + 2); i = i < 0 ? src.length : i + 2; continue; }
    if (c === '"' || c === "'" || c === '`') {
      let j = i + 1;
      while (j < src.length && src[j] !== c) j += src[j] === '\\' ? 2 : 1;
      out.push(src.slice(i + 1, j)); i = j + 1; prev = 'x'; continue;
    }
    if (c === '/' && /[(,=:[!&|?{};]/.test(prev || ';')) {          // a regex literal
      let j = i + 1, cls = false;
      while (j < src.length && (src[j] !== '/' || cls)) { if (src[j] === '\\') j++; else if (src[j] === '[') cls = true; else if (src[j] === ']') cls = false; j++; }
      i = j + 1; prev = 'x'; continue;
    }
    if (!/\s/.test(c)) prev = c;
    i++;
  }
  return out;
}
const SCRIPTS = [...['charts', 'desk', 'apple'].flatMap((d) => fs.readdirSync(path.join(STATIC, d)).filter((f) => f.endsWith('.js')).map((f) => `${d}/${f}`)), 'desklab.js', 'desklabset.js'];

test('strings(): finds words in quotes and templates, skips comments and regexes', () => {
  assert.deepEqual(strings("a = 'x'; // 'no'\n/* \"no\" */ b = `y ${1}`; c = /['\"]/g; d = \"z\\\"q\";"), ['x', 'y ${1}', 'z\\"q']);
});

/* ---- icons ---- */

test('Settings is the gear on the plain Desk too (not the sliders), the same drawing as HBIcons.gear', () => {
  const btn = /<button[^>]*id="settingsBtn"[\s\S]*?<\/button>/.exec(read('index.html'))[0];
  for (const d of icon('gear').match(/d="[^"]+"/g)) assert.ok(btn.includes(d), d);
  assert.ok(btn.includes('<circle cx="12" cy="12" r="3"/>'));
  assert.ok(!btn.includes('M10 5H3'), 'the sliders icon is gone');
  assert.match(btn, /width="16" height="16"/, 'same 16 px box');
});

test('the Desk theme toggle draws the one moon (HBIcons.moon)', () => {
  const moon = /<svg class="ic-moon"[\s\S]*?<\/svg>/.exec(read('index.html'))[0];
  assert.ok(moon.includes(icon('moon').match(/d="[^"]+"/)[0]));
  assert.ok(!moon.includes('M20 14.5A7.5'), 'the second moon is gone');
});

test('the Lab group builder and A/B close with the icon close, in the same 28 x 28 button', () => {
  for (const f of ['charts/labmix.js', 'charts/labab.js']) {
    const src = read(f), btn = /<button class="hb-ib mix-x"[^>]*>[^<]*(?:<[^>]*>)?[^<]*<\/button>/.exec(src);
    assert.ok(btn, f);
    assert.ok(!src.includes('✕'), `${f}: no text close glyph`);
    assert.ok(btn[0].includes('window.HBIcons.x'), `${f}: the shared X icon`);
    assert.ok(btn[0].includes('aria-label="Close"') && btn[0].includes('title="Close (Esc)"'), f);
  }
  assert.match(read('hb.css'), /--hb-h-sm: 28px/);
  assert.match(read('hb.css'), /^\.hb-ib \{ flex: none; width: var\(--hb-h-sm\); height: var\(--hb-h-sm\)/m, '.hb-ib is the 28 x 28 hit area');
  assert.ok(!/\.mix-x[^{]*\{[^}]*(width|height)/.test(read('charts/lab.css')), '.mix-x does not resize it');
});

test('removing a saved login or a paper account wears the trash icon (one drawing, defined once in index.html)', () => {
  const html = read('index.html');
  const sym = /<symbol id="ic-trash"[^>]*>([\s\S]*?)<\/symbol>/.exec(html);
  assert.ok(sym, 'a trash symbol');
  for (const d of icon('trash').match(/d="[^"]+"/g)) assert.ok(sym[1].includes(d), d);
  const book = read('desk/book.js'), set = read('desk/settings.js');
  const login = /<button[^>]*delLogin[^>]*>([\s\S]*?)<\/button>/.exec(book), paper = /<button[^>]*paper-rm[\s\S]*?<\/button>/.exec(set);
  assert.ok(login && paper);
  assert.ok(login[1].includes('href="#ic-trash"'), 'forget login');
  assert.ok(paper[0].includes('href="#ic-trash"'), 'remove paper account');
  assert.ok(!login[1].includes('&times;') && !paper[0].includes('&times;'));
  assert.ok(login[0].includes('title="Forget this login"') && paper[0].includes('title="Remove this paper account"'), 'titles kept');
  assert.ok(paper[0].includes('data-paper-id=') && /querySelectorAll\(["']button\.paper-rm["']\)|button\.paper-rm/.test(set), 'the click hook is kept');
  assert.ok(!/class="x paper-rm"/.test(set), 'out of the Mac skin xmark-circle mask');
});

test('disclosure chevrons: closed points right, open points down (pinned; the legend fold and bottom panel are deliberate)', () => {
  assert.match(read('apple.css'), /\.sh-chev \{[^}]*rotate\(90deg\)/);
  assert.match(read('apple.css'), /\.sh\.shut \.sh-chev \{ transform: rotate\(0deg\)/);
  assert.match(read('charts/lab.css'), /button\.lb-sh\[aria-expanded="true"\] \.lb-chev \{ transform: rotate\(90deg\)/);
  assert.match(read('charts/cell.js'), /TradingView-style/, 'the legend fold follows TradingView: up while open');
});

/* ---- words ---- */

test('"Live results" is "Desk results"; a strategy with no trades says "No Desk trades yet."', () => {
  const apple = read('apple/desk.js'), strat = read('desk/strategy.js'), labd = read('desk/labdesk.js');
  assert.ok(!/Live results/.test(apple) && apple.includes("'Desk results'"));
  assert.equal((apple.match(/Desk results/g) || []).length, 2);
  assert.ok(!/No live trades/.test(apple + strat + labd), 'no "No live trades"');
  assert.ok(apple.includes('/No Desk trades/'));
  assert.ok(labd.includes('"no Desk trades yet"') && labd.includes('"no shadow trades yet"'), 'shadow keeps its own words');
});

test('the two daily limits are "Last entry" and "Flat by" on the Desk and in the Lab', () => {
  const html = read('index.html');
  assert.match(html, /<label for="llLast">Last entry<\/label>/);
  assert.match(html, /<label for="llFlat">Flat by<\/label>/);
  assert.ok(read('desk/labdesk.js').includes('last: "Last entry"'));
  const dl = read('desklab.js');
  // SAY_LAST keeps its old words: homebase/desk/labcfg.py says the same sentence and a Python test pins the two together
  assert.ok(dl.includes('{ k: "Last entry"') && dl.includes('["Last entry", l[3].v]') && dl.includes('["Flat by", l[4].v]'));
  const lab = read('charts/lab.js');
  assert.ok(lab.includes("time('entry_to', 'Last entry (NY)'") && lab.includes("time('flat_at', 'Flat by (NY)'"));
  assert.ok(read('charts/tester.js').includes("entry_to: 'Last entry (NY)'") && read('charts/tester.js').includes("flat_at: 'Flat by (NY)'"));
  for (const f of ['index.html', 'desklab.js', 'desk/labdesk.js', 'charts/lab.js', 'charts/tester.js']) {
    assert.ok(!/No new trade after|Trade until|Flat at \(NY\)/.test(read(f).replace(/\/\*[\s\S]*?\*\//g, '').replace(/var SAY_LAST = [^\n]*/, '')), f);
  }
});

test('settings dialogs name their verb: Save, not OK', () => {
  for (const f of ['charts/app.js', 'charts/settings-dialog.js', 'charts/indicator-settings-dialog.js', 'charts/testerui.js']) {
    assert.ok(!strings(read(f)).includes('OK'), `${f}: no OK button`);
  }
  for (const [f, n] of [['charts/app.js', 3], ['charts/settings-dialog.js', 2], ['charts/indicator-settings-dialog.js', 1], ['charts/testerui.js', 1]]) {
    assert.equal((read(f).match(/'btn btn-(?:primary|solid)', 'Save'/g) || []).length, n, f);
  }
});

test('US spelling and the real term in every word a person reads: Color, Payout (never colour, cheque)', () => {
  for (const f of SCRIPTS) {
    for (const s of strings(read(f))) {
      assert.ok(!/colour/i.test(s), `${f}: "${s.slice(0, 80)}"`);
      assert.ok(!/cheque/i.test(s.replace(/[\w.]*cheque\w*/g, '')), `${f}: "${s.slice(0, 80)}"`);   // the saved key funded_expected_cheque is not a word
    }
  }
  assert.ok(strings(read('charts/labab.js')).includes('Expected payout') && strings(read('desklab.js')).includes('Expected payout'));
  assert.ok(strings(read('charts/tester.js')).includes('Funded: expected payout'));
});

test('a win rate prints as 58% (whole, no space) in every Lab table and tile', () => {
  const AB = require('../../homebase/static/charts/labab.js'), L = require('../../homebase/static/charts/labcode.js');
  const T = require('../../homebase/static/charts/tester.js'), AM = require('../../homebase/static/charts/allmetrics.js');
  assert.equal(AB.fmt(58.3, 'pctv'), '58%');
  assert.equal(AB.fmt(0.584, 'pct'), '58%');
  assert.equal(L.plPct(0.584), '58%');
  assert.equal(T.wrate(58.3), '58%');
  assert.equal(T.wrate(null), '—');
  assert.equal(AM.format('wr', 54.17), '54%');
  assert.equal(AM.format('pct', 12.34), '12.3%', 'a return keeps its decimal');
  const mix = read('charts/labmix.js');
  assert.ok(mix.includes('`${Math.round(v * 100)}%`') && mix.includes('`${Math.round(v)}%`') && !/\} %`/.test(mix));
  const am = read('charts/allmetrics.js');
  for (const k of ['win_rate', 'breakeven_wr', 'long_wr', 'short_wr']) assert.match(am, new RegExp(`\\['${k}', '[^']+', 'wr'`), k);
  assert.ok(read('charts/lab.js').includes("['win_rate', 'wr']"));
});

test('durations read "3m 04s", "2h 05m", "5m ago": no spaced unit words', () => {
  const L = require('../../homebase/static/charts/labcode.js'), AM = require('../../homebase/static/charts/allmetrics.js');
  assert.deepEqual([[0, 30000], [0, 5 * 60000], [0, 3 * 3600000], [0, 2 * 86400000]].map(([a, b]) => L.ago(a, b)), ['30s ago', '5m ago', '3h ago', '2d ago']);
  assert.deepEqual([45, 90, 184, 9000, 12600].map((s) => AM.format('secs', s)), ['45s', '1m 30s', '3m 04s', '2h 30m', '3h 30m']);
  assert.equal(AM.format('secs', null), '—');
  const T = require('../../homebase/static/charts/tester.js');
  assert.deepEqual([45, 184, 9000].map(T.dur), ['45s', '3m 04s', '2h 30m'], 'the tester prints the same as the metrics table');
  assert.deepEqual([20, 150, 4800, 7380, 7200].map(T.etaText), ['<1m left', '~3m left', '~1h 20m left', '~2h 03m left', '~2h left']);
});

test('the compare table win-rate delta is whole percent, like its two sides', () => {
  const T = require('../../homebase/static/charts/tester.js');
  const row = (a, b) => T.compareRows({ summary: { all: { win_rate: a } } }, { summary: { all: { win_rate: b } } }).find((r) => r.key === 'wr');
  const r = row(50, 54.2);
  assert.deepEqual([r.a, r.b, r.delta], ['50%', '54%', '+4%']);
  assert.equal(row(54, 50).delta.replace(/[^\d]/g, ''), '4');
});

test('the Mac-skin inspector names the flat time "Flat by" like every other screen', () => {
  const d = read('apple/desk.js');
  assert.ok(d.includes("row('Flat by', ") && !d.includes("row('Flat', "));
});

test('the paper-account trash keeps its 18px-wide hit box and turns --neg on hover', () => {
  const s = read('desk/settings.js');
  assert.ok(/class="paper-rm"[^>]*padding:2px 4px/.test(s));
  assert.ok(/\.paper-rm:hover\s*\{\s*color:\s*var\(--neg\)/.test(read('index.html')));
});

test('an empty Desk archive says "No archived strategies yet."', () => {
  const src = read('desk/labdesk.js');
  assert.ok(src.includes('No archived strategies yet.') && !src.includes('Nothing is archived.'));
});
