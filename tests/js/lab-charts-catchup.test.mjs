import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

/* Design package 1, "Lab and Charts catch up" (2026-10-27): the Mac skin's rules reach what it missed. CSS cannot be rendered in a test, so
   these read the real stylesheets and check the rule, its value and that it outranks the plain rule it must beat. Presentation only: no
   font, size, colour value or corner is changed by anything here, and the order path is not touched. */
const require = createRequire(import.meta.url);
const STATIC = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../homebase/static');
const read = (p) => readFileSync(path.join(STATIC, p), 'utf8');
const LAB = read('apple/lab.css'), CHARTS = read('apple/charts.css'), PLAIN_LAB = read('charts/lab.css'), PLAIN_CHARTS = read('charts/charts.css');

/* every rule of a stylesheet as {sels, decls}: comments stripped, @media entered, @keyframes / @font-face skipped; a selector list is split at top-level commas */
function rules(css) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const out = [];
  (function walk(s) {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open < 0) break;
      let depth = 1, j = open + 1;
      while (j < s.length && depth) { if (s[j] === '{') depth++; else if (s[j] === '}') depth--; j++; }
      const head = s.slice(i, open).trim(), body = s.slice(open + 1, j - 1);
      if (/^@(media|supports|container|layer)\b/.test(head)) walk(body);
      else if (!head.startsWith('@')) {
        const sels = []; let d = 0, cur = '';
        for (const ch of head) { if (ch === '(') d++; if (ch === ')') d--; if (ch === ',' && !d) { sels.push(cur.trim()); cur = ''; } else cur += ch; }
        sels.push(cur.trim());
        const decls = {};
        for (const m of body.matchAll(/([a-z-]+)\s*:\s*([^;]+?)\s*(?:;|$)/g)) decls[m[1]] = m[2].replace(/\s*!important$/, '');
        out.push({ sels, decls });
      }
      i = j;
    }
  })(css);
  return out;
}
/* the declarations a selector gets in one sheet, later rules over earlier ones (same selector only) */
function decl(css, sel) {
  const got = {};
  for (const r of rules(css)) if (r.sels.includes(sel)) Object.assign(got, r.decls);
  return got;
}
/* (ids, classes + attributes + pseudo-classes, elements + pseudo-elements) of one selector */
function spec(sel) {
  let a = 0, b = 0, c = 0;
  sel = sel.replace(/:where\([^)]*\)/g, '').replace(/:not\(([^)]*)\)/g, ' $1 ');
  sel = sel.replace(/::[a-z-]+/g, () => { c++; return ''; });
  sel = sel.replace(/#[\w-]+/g, () => { a++; return ''; }).replace(/\[[^\]]*\]/g, () => { b++; return ''; })
    .replace(/\.[\w-]+/g, () => { b++; return ''; }).replace(/:[a-z-]+(\([^)]*\))?/g, () => { b++; return ''; });
  c += (sel.match(/(^|[\s>+~])[a-z][\w-]*/g) || []).length;
  return [a, b, c];
}
const beats = (x, y) => { const p = spec(x), q = spec(y); for (let i = 0; i < 3; i++) if (p[i] !== q[i]) return p[i] > q[i]; return false; };
const has = (css, sel) => rules(css).some((r) => r.sels.includes(sel));

/* ---------------------------------------------------------------------------------------------------------- (1) loss ink, gain green */
const LOSS_GAIN = [
  // [the skin's selector, the plain selector it must outrank, tone]
  ['html.hb-apple #labRes #wfRes .rs-kv b.down', '#labRes #wfRes .rs-kv b.down', 'loss'],
  ['html.hb-apple #labRes #wfRes .rs-kv b.up', '#labRes #wfRes .rs-kv b.up', 'gain'],
  ['html.hb-apple #labRes #wfRes .down', '#wfRes .down', 'loss'],
  ['html.hb-apple #labRes #wfRes .up', '#wfRes .up', 'gain'],
  ['html.hb-apple .rl-years .down', '.rl-years .down', 'loss'],
  ['html.hb-apple .rl-years .up', '.rl-years .up', 'gain'],
  ['html.hb-apple .am-t td.dn', '.am-t td.dn', 'loss'],
  ['html.hb-apple .am-t td.up', '.am-t td.up', 'gain'],
  ['html.hb-apple .mix .dn', '.mix .dn', 'loss'],
  ['html.hb-apple .mix .up', '.mix .up', 'gain'],
];
test('Lab tables: a loss is ink and a gain is the Mac green, over the plain red and teal', () => {
  for (const [mac, plain, tone] of LOSS_GAIN) {
    assert.equal(decl(LAB, mac).color, tone === 'loss' ? 'var(--a-label)' : 'var(--a-green)', `${mac}`);
    assert.ok(has(PLAIN_LAB, plain), `${plain}: the plain rule this answers is gone, update the list`);
    assert.ok(beats(mac, plain), `${mac} must outrank ${plain}`);
  }
});

test('Lab tables: the real errors and the heat-map tints keep their colours', () => {
  const sels = rules(LAB).flatMap((r) => r.sels).join(' | ');
  assert.ok(!/heat-c/.test(sels), 'the heat-map cell tints are data, left alone');
  assert.ok(!/mix-err|rl-line\.fail/.test(sels), 'a real error and a failed real-or-luck line stay red');
});

test('every cell the skin turns to ink prints its own minus sign', () => {
  const Tr = require('../../homebase/static/charts/tradepure.js'), AM = require('../../homebase/static/charts/allmetrics.js');
  const AB = require('../../homebase/static/charts/labab.js');
  assert.equal(AM.format('usd', -250), '−$250', 'Adjust metrics');
  assert.equal(Tr.usd(-250), '−$250', 'per-year row (X.signed) and the walk-forward');
  assert.equal(Tr.money(-250), '−$250');
  assert.equal(AB.delta(1000, 400, 'money', 1).text, '−$600', 'A/B delta');
  const LABJS = read('charts/lab.js'), MIX = read('charts/labmix.js');
  assert.match(LABJS, /const money0 = \(v\) => `\$\{v > 0 \? '\+' : v < 0 \? MINUS : ''\}\$/, 'the walk-forward rows print through money0');
  assert.match(MIX, /const money = \(v\) => \(v == null \? '—' : `\$\{v < 0 \? '−' : ''\}\$/, 'group tiles and members');
  assert.match(read('charts/tester.js'), /const signed = \(v\) => Tr\.usd\(v\)/, 'X.signed');
});

test('Charts bottom panel: the Short side is ink and Long the Mac green; the status cell keeps its red', () => {
  assert.equal(decl(CHARTS, 'html.hb-apple .bp-table td.up:not(.num)').color, 'var(--a-green)');
  assert.equal(decl(CHARTS, 'html.hb-apple .bp-table td.down:not(.num):not(:last-child)').color, 'var(--a-label)');
  assert.ok(beats('html.hb-apple .bp-table td.up:not(.num)', '.up'));
  // the account table's status ("Not connected") is the row's last cell and a real error: not in the rule
  const PANEL = read('charts/panel.js');
  assert.match(PANEL, /td\(tr, r\.status, r\.status === 'Ready' \? '' : 'down'\)/);
  assert.match(PANEL, /td\(tr, r\.side, r\.side === 'Long' \? 'up' : 'down'\)/, 'the fix is CSS: panel.js still tags the cell');
});

/* ---------------------------------------------------------------------------------------------------------- (2) Lab sheets */
test('Lab sheets (group builder, A/B, Adjust metrics): one 20 px edge and the other Lab tables\' 10 px cells', () => {
  assert.equal(decl(LAB, 'html.hb-apple .mix-head').padding, '14px 20px');
  assert.equal(decl(LAB, 'html.hb-apple .mix-out').padding, '14px 20px 24px');
  assert.equal(decl(LAB, 'html.hb-apple .ab-picks').padding, '10px 20px');
  // Adjust metrics already sits on 20 (head 20 20 0, body 0 20 20): the plain rules the skin must not break
  assert.match(PLAIN_LAB, /\.am-head \{[^}]*padding: 20px 20px 0/);
  assert.match(PLAIN_LAB, /\.am-body \{[^}]*padding: 0 20px 20px/);
  for (const t of ['.am-t', '.mix-t']) {
    assert.equal(decl(LAB, `html.hb-apple ${t} th`).padding, '4px 10px', `${t} header cells`);
    assert.equal(decl(LAB, `html.hb-apple ${t} td`).padding, '4px 10px', `${t} cells`);
    assert.equal(decl(LAB, `html.hb-apple ${t} th:first-child`)['padding-left'], '0', `${t} first cell sits on the edge`);
    assert.equal(decl(LAB, `html.hb-apple ${t} th:last-child`)['padding-right'], '0', `${t} last cell sits on the edge`);
  }
  assert.ok(beats('html.hb-apple .am-t td', '.am-t td'));
  assert.ok(beats('html.hb-apple .mix-t td', '.mix-t td'));
});

/* ---------------------------------------------------------------------------------------------------------- (3) bottom panel, Charts = Lab */
test('bottom panel: the same bar, header, rows and edge in Charts and in the Lab', () => {
  const cBar = decl(CHARTS, 'html.hb-apple #bpanel .bp-bar'), lBar = decl(LAB, 'html.hb-apple #lab .bp-bar'), lTabs = decl(LAB, 'html.hb-apple #lab .tst-tabs');
  assert.equal(cBar.height, '36px'); assert.equal(lBar.height, '36px'); assert.equal(lTabs.height, '36px');
  assert.equal(decl(CHARTS, 'html.hb-apple #bpanel').height, '37px', 'the closed panel is its 1px hairline plus the 36px bar');
  assert.equal(cBar.padding, '0 12px 0 14px');
  assert.equal(lBar.padding, cBar.padding, 'same bar insets');
  assert.equal(lTabs.padding, cBar.padding, 'same tab-row insets');
  assert.equal(decl(CHARTS, 'html.hb-apple .bp-table th').height, '24px');
  assert.equal(decl(CHARTS, 'html.hb-apple .bp-table td').height, '24px');
  assert.equal(decl(LAB, 'html.hb-apple #lab .bp-table th').height, '24px');
  assert.equal(decl(LAB, 'html.hb-apple #lab .bp-table td').height, '24px');
  // the edge: Charts' tables start 20 in; the Lab's report content is 20 in and its tables sit on that edge, not 20 + 10
  assert.equal(decl(CHARTS, 'html.hb-apple .bp-table td:first-child')['padding-left'], '20px');
  assert.equal(decl(LAB, 'html.hb-apple #lab .tst-content').padding, '14px 20px');
  assert.equal(decl(LAB, 'html.hb-apple #lab .tst-content .bp-table th:first-child')['padding-left'], '0');
  assert.equal(decl(LAB, 'html.hb-apple #lab .tst-content .bp-table td:first-child')['padding-left'], '0');
  assert.equal(decl(LAB, 'html.hb-apple #lab .tst-content .bp-table th:last-child')['padding-right'], '0');
  assert.equal(decl(LAB, 'html.hb-apple #lab .tst-content .bp-table td:last-child')['padding-right'], '0');
  assert.equal(decl(LAB, 'html.hb-apple #lab .bp-empty').padding, '20px');
});

/* ---------------------------------------------------------------------------------------------------------- (4) Charts dialog gutters */
test('Charts dialogs: Settings, Indicator settings and Drawing style share a 20 px gutter and a 16 px bottom', () => {
  assert.equal(decl(CHARTS, 'html.hb-apple .set-pane').padding, '4px 20px 16px');
  for (const d of ['drawstyle', 'indicator-settings']) {
    const mac = `html.hb-apple .dialog.${d} .set-pane`, plain = `.dialog.${d} .set-pane`;
    assert.equal(decl(CHARTS, mac).padding, '4px 20px 16px', d);
    assert.ok(has(PLAIN_CHARTS, plain), `${plain} is the per-dialog rule that beat the Mac rule`);
    assert.ok(beats(mac, plain), `${mac} must outrank ${plain}`);
  }
});

/* ---------------------------------------------------------------------------------------------------------- (5) the group builder card */
test('group builder card: the same solid sheet as the other Lab dialogs', () => {
  assert.equal(decl(LAB, 'html.hb-apple .mix').background, 'var(--a-scrim)');
  const card = decl(LAB, 'html.hb-apple .mix-in');
  assert.equal(card.background, 'var(--a-window)');
  assert.equal(card['box-shadow'], 'var(--a-sheet-shadow)');
  assert.equal(card['backdrop-filter'], 'none');
  assert.equal(card['-webkit-backdrop-filter'], 'none');
  assert.equal(card['border-radius'], undefined, 'the corner is the owner\'s: left as it is');
  const dlg = decl(LAB, 'html.hb-apple .lab-dlg');
  assert.equal(dlg.background, card.background); assert.equal(dlg['box-shadow'], card['box-shadow']);
  assert.ok(beats('html.hb-apple .mix', '.mix') && beats('html.hb-apple .mix-in', '.mix-in'));
});

/* ---------------------------------------------------------------------------------------------------------- (9) "Test days" */
test('the "Test days" badge in the Recent runs menu is a neutral chip, not the red LIVE class', () => {
  const src = read('charts/testerui.js');
  const line = src.split('\n').find((l) => l.includes("'Test days'") && l.includes('r.holdout'));
  assert.ok(line, 'the Recent runs "Test days" line');
  assert.ok(!/env live|'env\b/.test(line), 'no env / live class');
  assert.match(line, /page\.mk\('span', 'tst-badge', 'Test days'\)/);
  assert.ok(has(PLAIN_CHARTS, '.tst-badge'), 'the chip class exists');
  assert.equal(decl(PLAIN_CHARTS, '.tst-badge').color, 'var(--text-2)');
});

/* ---------------------------------------------------------------------------------------------------------- (17) --text2 */
test('no stylesheet uses the undefined --text2 token: the six rules point at --text-2', () => {
  const GUIDE = read('charts/guide.css');
  for (const [name, css] of [['guide.css', GUIDE], ['charts.css', PLAIN_CHARTS], ['lab.css', PLAIN_LAB]]) assert.ok(!/var\(--text2\b/.test(css), `${name} still uses --text2`);
  for (const sel of ['.lg-note', '.dlg-help', '.guide-now', '.guide-h', '.guide-watch']) assert.equal(decl(GUIDE, sel).color, 'var(--text-2)', sel);
  assert.equal(decl(PLAIN_CHARTS, '.lg-tst .lg-vals').color, 'var(--text-2)');
  assert.match(PLAIN_CHARTS, /--text-2:/, 'the real token is defined');
});

/* ---------------------------------------------------------------------------------------------------------- cache pins */
test('cache pins follow the edited files', () => {
  const man = JSON.parse(read('apple/manifest.json'));
  assert.equal(man.version, 48, 'apple/lab.css and apple/charts.css changed');
  assert.match(read('charts.html'), /charts\/charts\.css\?v=65"/);
  assert.match(read('backtest.html'), /charts\/charts\.css\?v=56"/);
  assert.match(read('charts.html'), /charts\/guide\.css\?v=6"/);
  assert.match(read('backtest.html'), /charts\/guide\.css\?v=6"/);
  assert.match(read('backtest.html'), /charts\/testerui\.js\?v=43"/);
});
