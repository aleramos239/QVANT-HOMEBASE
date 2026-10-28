/* Package 4, Lab and layout polish (2026-10-27): the in-sample table reads like a table (numbers right, the first two columns
   stay put, the six lines above the 120 rows), icons instead of text glyphs, the Lab toast and its menus and sheets move like
   the Charts ones, the delta chip carries its sign, and the Code and Chart toggles carry words. Source-text tests against
   main, plus a vm run of the table builder. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const RL = require('../../homebase/static/charts/reallines.js');
const rd = (p) => readFileSync(new URL(`../../homebase/${p}`, import.meta.url), 'utf8');
const LAB = rd('static/charts/lab.js'), LABCSS = rd('static/charts/lab.css'), MAC = rd('static/apple/lab.css');
const MACJS = rd('static/apple/lab.js');
/* the rule text for a selector, up to its closing brace (first match) */
const rule = (css, sel) => { const i = css.indexOf(sel); assert.ok(i >= 0, `rule ${sel}`); return css.slice(i, css.indexOf('}', i) + 1); };

/* the table builder, run for real over a 120-box result */
const IS = (net) => ({ win_rate: 50, breakeven: 45, wr_minus_be: 5, trades: 200, per_week: 1.5, avg_trade: net / 200, avg_r: 0.1, net, pf: 1.2,
  sharpe: 0.9, max_dd: -2500, months_pos: 60, months_wr60: 20, worst_month_wr: 30, long_net: net / 2, short_net: net / 2, skipped_by_error: 0 });
const AXES = [{ key: 'ctl.stop', label: 'Stop', values: ['atr:0.5'], value_labels: ['ATR x0.5'] },
  { key: 'ctl.target_rr', label: 'Target (x stop)', values: Array.from({ length: 120 }, (_, i) => i), value_labels: Array.from({ length: 120 }, (_, i) => String(i)) }];
const cells120 = Array.from({ length: 120 }, (_, i) => ({ i, params: { 'ctl.stop': 'atr:0.5', 'ctl.target_rr': i }, is: IS(i < 90 ? 1000 + i : -500), blocks: [] }));
const RES = { scheme: 'fixed', step_months: 4, rolling: false, stitch: 's', window: { start: '2021-10', end: '2026-08' }, months: ['2021-10'],
  blocks: [{ i: 0, is: ['2021-10'] }], n_cells: 120, looks: 120, cells: cells120, lock: null };
const esc = (t) => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const ICONS = new Proxy({}, { get: (_, k) => `<svg class="ic" data-ic="${String(k)}"></svg>` });
function ctx() {
  const a = LAB.indexOf('const curSid'), b = LAB.indexOf('\n}\n', LAB.indexOf('function wfFixedHtml')) + 3;
  const c = vm.createContext({ X, RL, S: { tries: {} }, buf: () => null, formOf: () => null, esc, IC: ICONS, MINUS: '−',
    OOS_SAID: '', wfMon: (m) => m, metaOf: () => ({}), triesOf: () => null });
  vm.runInContext(`${LAB.slice(a, b)}\nglobalThis.wfFixedHtml = wfFixedHtml; globalThis.realRead = realRead;`, c);
  return c;
}

test('in-sample table: the six lines and the count sit above the 120 rows, and the verdict still reads all 120', () => {
  const c = ctx();
  const h = c.wfFixedHtml({ result: RES, sort: null }, { axes: AXES, strategy: 'draft_x' });
  const at = (s) => { const i = h.indexOf(s); assert.ok(i >= 0, s); return i; };
  assert.ok(at('boxes made money') < at('Real or luck'), 'count, then the six lines');
  assert.ok(at('Real or luck') < at('rl-verdict'));
  assert.ok(at('rl-verdict') < at('<table class="heat-tbl wf-steps wf-fixed wf-is"'), 'the lines are above the table');
  assert.ok(at('<table class="heat-tbl wf-steps wf-fixed wf-is"') < at('Test months'));
  const body = h.slice(at('<tbody>'), at('</tbody>'));
  assert.equal((body.match(/<tr[ >]/g) || []).length, 120, 'all 120 rows are still drawn');
  const r = c.realRead(RES, 'draft_x');
  assert.equal(r.n, 120);
  assert.equal(r.up, 90);                                   // the average of ALL boxes, never a top slice
  assert.match(h, /90 of 120 boxes made money \(75%\)/);
});

test('in-sample table: the order in the source is per year, count, six lines, then the heading and the table', () => {
  const b = LAB.indexOf('function wfFixedHtml'), w = LAB.slice(b, LAB.indexOf('\n}\n', b));
  const at = (s) => { const i = w.indexOf(s); assert.ok(i >= 0, s); return i; };
  assert.ok(at('${perYearHtml(yc') < at('boxes made money'));
  assert.ok(at('boxes made money') < at('${realHtml(rd, sid)}'));
  assert.ok(at('${realHtml(rd, sid)}') < at('In-sample table ·'));
  assert.ok(at('In-sample table ·') < at('wf-steps wf-fixed wf-is'));
  assert.ok(at('wf-steps wf-fixed wf-is') < at('<div class="rs-gh">Test months</div>'));
});

test('in-sample table: numbers right-aligned, the Pick and Box columns sticky, opaque so nothing shows through', () => {
  for (const [css, name] of [[LABCSS, 'lab.css']]) {
    const all = css.slice(css.indexOf('.wf-is'));
    assert.match(all, /\.wf-is td:nth-child\(n\+3\)[^{]*\{[^}]*text-align: right/, `${name}: numeric cells right`);
    assert.match(all, /\.wf-is th:nth-child\(n\+3\)[^{]*\{[^}]*text-align: right/, `${name}: numeric heads right`);
    assert.match(all, /\.wf-is[^{]*:nth-child\(1\)[^{]*\{[^}]*position: sticky;[^}]*left: 0/, `${name}: Pick sticks at the left edge`);
    assert.match(all, /\.wf-is[^{]*:nth-child\(2\)[^{]*\{[^}]*position: sticky;[^}]*left: \d+px/, `${name}: Box sticks beside it`);
    assert.match(all, /\.wf-is[^{]*:nth-child\(-n\+2\)[^{]*\{[^}]*background: var\(--/, `${name}: sticky cells are opaque`);
  }
  assert.match(MAC, /\.wf-is[^{]*:nth-child\(-n\+2\)[^{]*\{[^}]*background: var\(--a-/, 'the glass inspector gets an opaque Mac colour');
  assert.ok(!/wf-is/.test(rule(LABCSS, '.wf-fixed {')), 'the one-row test-months table is not sticky');
});

test('sort arrows and check marks in the Lab are SVG icons, not text glyphs', () => {
  const c = ctx();
  const h = c.wfFixedHtml({ result: RES, sort: { key: 'net', dir: -1 } }, { axes: AXES, strategy: 'draft_x' });
  assert.ok(!/[↑↓]/.test(h), 'no text arrows in the table head');
  assert.match(h, /wf-arrow[^>]*>\s*<svg class="ic" data-ic="chevron"/, 'down arrow is the chevron');
  const up = c.wfFixedHtml({ result: RES, sort: { key: 'net', dir: 1 } }, { axes: AXES, strategy: 'draft_x' });
  assert.match(up, /wf-arrow[^>]*>\s*<svg class="ic" data-ic="chevronUp"/);
  assert.ok(!/<small>✓<\/small>/.test(LAB), 'menu check marks');
  assert.ok(!/c\.ok \? '✓' : '○'/.test(LAB), 'checklist marks');
  assert.match(LAB, /IC\.check/);
  assert.match(rule(LABCSS, '.wf-arrow'), /width: \d+px/, 'a fixed-width slot, so the head does not jump');
  assert.match(MAC, /\.lab-menu button\.row small svg \{ display: none/, 'the Mac mask check is not drawn twice');
  const t = rd('static/charts/testerui.js');
  assert.ok(!/' ▲' : ' ▼'/.test(t), 'trades table sort glyphs');
  assert.match(t, /sort-th/);
});

test('the Lab toast is the Charts toast: #toastRoot, .toast.err, springs in and out, no inline black box', () => {
  const a = LAB.indexOf('function toast'), t = LAB.slice(a, LAB.indexOf('\n}\n', a));
  assert.ok(!/cssText|#1d1d1f|labToast/.test(t), 'no inline style');
  assert.match(t, /toastRoot/);
  assert.match(t, /toast err/);
  assert.match(t, /enter\(el, 'right top'\)/);
  assert.match(t, /leave\(el\)/);
  assert.match(t, /'role', 'alert'/);
  assert.match(MAC, /\.lab-page \.toast\.err[^{]*\{[^}]*inset 3px 0 0 var\(--a-red\)/, 'the Charts red bar');
});

test('Lab menus and sheets use the shared open and close motion', () => {
  const a = LAB.indexOf('function leave('), b = LAB.indexOf('function menu(', a), s = LAB.slice(a, LAB.indexOf('\n}\n', b));
  assert.match(s, /SP\.dematerialize\(/);
  assert.match(s, /SP\.materialize\(/);
  assert.match(LAB, /leave\(overlay, instant\)[\s\S]*enter\(overlay\); enter\(d\)/);
  assert.match(LAB, /leave\(menuEl, instant\)[\s\S]*enter\(menuEl,/);
  assert.ok(!/animation: lab-pop|animation: lab-in/.test(rule(LABCSS, '.lab-menu {') + rule(LABCSS, '.lab-ov {') + rule(LABCSS, '.lab-dlg {')), 'old keyframes off the three');
  assert.ok(!/@keyframes lab-pop/.test(LABCSS));
  assert.match(LABCSS, /\[data-motion\]\.lab-menu|\.lab-menu\[data-motion\]/);
  assert.match(LABCSS, /\.lab-dlg\[data-motion\]|\[data-motion\]\.lab-dlg/);
  assert.match(LABCSS, /@media \(prefers-reduced-motion: reduce\)[\s\S]*lab-menu\[data-motion\]/, 'reduced motion fades only');
  assert.ok(!/animation: none/.test(rule(MAC, 'html.hb-apple .lab-menu {') + rule(MAC, 'html.hb-apple .lab-ov {') + rule(MAC, 'html.hb-apple .lab-dlg {')));
});

test('delta chip prints its sign instead of an arrow glyph', () => {
  const i = LAB.indexOf('rs-delta'), d = LAB.slice(i - 400, i + 400);
  assert.ok(!/[▲▼]/.test(LAB), 'no triangle glyphs left in lab.js');
  assert.match(LAB, /pctv > 0 \? '\+' : pctv < 0 \? MINUS : ''/);
  assert.ok(d.length > 0);
});

test('Code and Chart toggles carry words wide, and the icon alone when narrow', () => {
  assert.match(MACJS, /hb-text/);
  assert.match(MACJS, /hb-tb-word/);
  assert.match(MACJS, /Code/);
  assert.match(MACJS, /Chart/);
  assert.match(MAC, /\.hb-tb-word \{ display: none/);
  assert.match(MAC, /@media \(min-width: 1280px\)[\s\S]*\.hb-tb-word \{ display: inline/);
});

test('one shared switcher fit: shell.js measures, one CSS rule keyed on hb-c-tight, no media ladders', () => {
  const SH = rd('static/apple/shell.js'), CH = rd('static/apple/charts.js'), SYS = rd('static/apple/system.css');
  assert.match(SH, /hb-c-tight/);
  assert.match(SH, /sw\.offsetWidth \/ 2 : 0\) \+ 12/);
  assert.match(SH, /fit/);
  assert.ok(!/function fit/.test(CH), 'charts.js uses the shared one');
  assert.match(SYS, /html\.hb-apple\.hb-c-tight \.hb-tb-c/);
  assert.ok(!/max-width:\s*1100px\)\s*\{\s*html\.hb-apple \.hb-tb-c/.test(SYS));
  assert.ok(!/1740px|1640px/.test(rd('static/apple/desk.css')), 'no Desk ladder');
  assert.ok(!/max-width: ?1300px\)[^{]*\{[^}]*hb-tb-c/.test(MAC), 'no Lab ladder');
  assert.ok(!/hb-c-tight/.test(rd('static/apple/charts.css')), 'the Charts-only rule moved to system.css');
});
