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
  assert.match(css, /\.hb-bar \.tabstrip, #tbSettings \{ display: none !important; \}/);
  assert.match(HTML, /id="labNav"[^]*data-nav="-1"[^]*id="labNavText"[^]*data-nav="1"/);
  assert.match(LAB, /function soloChart\(\)/);
  assert.match(LAB, /HBTesterLayer\.jump\(ti\)/);
});

test('the other two pages call it Lab too, and the URL is still /backtest', () => {
  for (const f of ['index.html', 'charts.html']) assert.match(rd(f), /data-page="backtest">Lab</, f);
  assert.match(rd('charts/app.js'), /:8852\/backtest\$\{q\}/);
});
