import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

/* The Lab (backtest.html, "Code" mode) handles strategy TEXT. It must never execute it, and it must never
   be able to put a strategy on the desk: it talks only to the chart service's tester routes. Source-text
   pins, same technique as backtest-isolation.test.mjs. */
const rd = (p) => readFileSync(new URL(`../../homebase/static/${p}`, import.meta.url), 'utf8');
const LAB = rd('charts/lab.js'), CODE = rd('charts/labcode.js'), HTML = rd('backtest.html');

test('the Lab never evaluates the script it shows', () => {
  for (const src of [LAB, CODE]) {
    assert.doesNotMatch(src, /\beval\s*\(/);
    assert.doesNotMatch(src, /new\s+Function\s*\(/);
    assert.doesNotMatch(src, /\bimport\s*\(/);
    assert.doesNotMatch(src, /document\.write|insertAdjacentHTML\([^)]*code/);
  }
});

test('the Lab only calls the tester routes: nothing of the desk, no order, no kill, no arm', () => {
  const urls = [...LAB.matchAll(/['"`](\/api\/[^'"`$?]*)/g)].map((m) => m[1]);
  assert.ok(urls.length >= 8, 'it does use the API');
  for (const u of urls) assert.match(u, /^\/api\/tester\//, `an API call outside the tester: ${u}`);
  assert.doesNotMatch(LAB, /:8850|\/api\/(arm|disarm|kill|orders?|trade|desk|strateg(y|ies)\/)/);
});

test('every piece of the script reaches the page escaped: the highlighter escapes before it wraps', () => {
  assert.match(CODE, /const esc = /);
  assert.equal((LAB.match(/hl\.innerHTML = C\.highlight\(/g) || []).length, 1, 'the one place the script becomes HTML');
});

test('backtest.html carries the Lab: page label, the four panel toggles and panes, and loads labcode before lab', () => {
  assert.match(HTML, /data-page="backtest" aria-current="page">Lab</);
  for (const k of ['lib', 'code', 'chart', 'res']) assert.match(HTML, new RegExp(`id="labPanels"[^]*data-panel="${k}"`), k);
  for (const id of ['labLib', 'labEd', 'labChart', 'labRes', 'labSplit']) assert.ok(HTML.includes(`id="${id}"`), id);
  // the chart shell lives inside the workspace, between the editor and the result
  const at = (t) => HTML.indexOf(t);
  assert.ok(at('id="labEd"') < at('id="labChart"') && at('id="labChart"') < at('class="toolbar"') && at('id="bpanel"') < at('id="labRes"'));
  assert.ok(HTML.indexOf('labcode.js') > 0 && HTML.indexOf('labcode.js') < HTML.indexOf('/lab.js'));
  assert.ok(HTML.indexOf('/tester.js') < HTML.indexOf('labcode.js'), 'the Lab reads HBTester');
});

test('the Lab chart is one chart with no tools: the rail, the symbol/indicator/layout buttons and the layout tabs are hidden', () => {
  const css = rd('charts/lab.css');
  assert.match(css, /\.lab-chart \.rail \{ display: none; \}/);
  assert.match(css, /\.lab-chart \.toolbar > :not\(#tbFavs\):not\(\.lab-nav\) \{ display: none !important; \}/);
  assert.match(css, /\.lab-page \.tabstrip, \.lab-page #tbSettings \{ display: none !important; \}/);
  assert.match(HTML, /id="labNav"[^]*data-nav="-1"[^]*id="labNavText"[^]*data-nav="1"/);
  // the trade stepper lives in the chart's own toolbar (the Mac skin restyles it there, it does not move it), and shows only with trades
  assert.ok(HTML.indexOf('class="toolbar"') < HTML.indexOf('id="labNav"') && HTML.indexOf('id="labNav"') < HTML.indexOf('id="tbFavs"'));
  assert.doesNotMatch(rd('apple/lab.js'), /labNav|hbLabTrades/);
  assert.doesNotMatch(rd('apple/lab.css'), /hbLabTrades/);
  assert.match(LAB, /nav\.hidden = !n;\n  if \(!n\) return;/, 'no finished run on the chart, or one without a trade: no stepper');
  assert.match(LAB, /function soloChart\(\)/);
  assert.match(LAB, /HBTesterLayer\.jump\(i, null, \{ contextMs: dayContext\(t\) \}\)/, 'a trade is framed inside its whole trading day');
  assert.match(LAB, /c\.update\(\{ indicators: \[\] \}\)/, 'the saved chart indicators are not part of the strategy');
});

test('the Arsenal view: with nothing open the welcome and the empty result step aside for one line of its own', () => {
  const css = rd('charts/lab.css');
  const panels = LAB.slice(LAB.indexOf('function applyPanels('), LAB.indexOf('function setPanel('));
  assert.match(panels, /root\.dataset\.view = S\.view;/, 'the page says which view is open; the style sheet does the rest');
  assert.match(css, /\.lab\[data-view="tk"\] \.lab-welcome > \* \{ display: none; \}/);
  assert.match(css, /\.lab\[data-view="tk"\] \.lab-welcome::before \{ content: "Pick a tool on the left to read its code\.";/);
  assert.match(css, /\.lab\[data-view="tk"\] \.rs-none \{ display: none; \}/);
  assert.match(LAB, /if \(!b\) \{ el\.innerHTML = '<div class="rs-empty rs-none">/, 'only the nothing-open result is hidden: a strategy\'s own empty states stay');
  assert.match(rd('apple/lab.css'), /html\.hb-apple #lab\[data-view="tk"\] #labEd \.lab-welcome > \* \{ display: none; \}/, 'the skin gives the welcome\'s parts a display of their own');
});

test('the other two pages call it Lab too, and the URL is still /backtest', () => {
  for (const f of ['index.html', 'charts.html']) assert.match(rd(f), /data-page="backtest">Lab</, f);
  assert.match(rd('charts/app.js'), /:8852\/backtest\$\{q\}/);
});

test('grouping only ever posts to the groups routes: it never saves, rewrites or deletes a strategy', () => {
  const g = LAB.slice(LAB.indexOf('/* ---- groups: the library in sections ----'), LAB.indexOf('/* ---- painting ---- */'));
  assert.ok(g.length > 1500, 'the groups block is there');
  assert.equal((g.match(/\bsend\(/g) || []).length, 1, 'one place sends');
  assert.match(g, /send\('POST', `\/api\/tester\/groups\$\{path\}`, body\)/);
  assert.doesNotMatch(g, /\/drafts|'PUT'|'DELETE'|\bsave\(|deleteDialog/);
});

test('against a chart service from before groups the list is the plain one it was: no sections, no row menus', () => {
  assert.match(LAB, /if \(g\.ok\) S\.groups = g\.json;\s*\n\s*else if \(g\.status\) \{[^\n]*\n\s*S\.groups = null;/);
  assert.match(LAB, /S\.groups \? C\.withDeskGroup\(C\.sections\(\[\.\.\.rows, \.\.\.builtins\], S\.groups\)\)\.map\(section\)\.join\(''\)\s*\n\s*: `\$\{rows\.map\(item\)\.join\(''\)\}<div class="lb-sh">Built-in<\/div>\$\{builtins\.map\(item\)\.join\(''\)\}`/);
  assert.match(LAB, /\$\{S\.groups \? '<hr><button data-pick="group">/, 'New group is offered only when there are groups to make');
});
