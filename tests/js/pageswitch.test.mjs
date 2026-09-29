/* The in-page switcher (Desk / Charts / Backtest) on the charts and backtest pages: three plain links, the
   current page marked, the hrefs built by app.js from location.hostname with the page's own ?v. The Mac app has
   no native switcher any more, so these links are the only way to change page. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const rd = (p) => readFileSync(new URL(`../../homebase/static/${p}`, import.meta.url), 'utf8');
const APP = rd('charts/app.js');

for (const [file, cur] of [['charts.html', 'charts'], ['backtest.html', 'backtest']]) {
  test(`${file}: the switcher is Desk · Charts · Backtest with ${cur} current`, () => {
    const html = rd(file);
    const nav = html.slice(html.indexOf('<nav class="pgsw"'), html.indexOf('</nav>'));
    assert.deepEqual([...nav.matchAll(/data-page="(\w+)"/g)].map((m) => m[1]), ['desk', 'charts', 'backtest']);
    assert.equal([...nav.matchAll(/aria-current="page"/g)].length, 1);
    assert.match(nav, new RegExp(`data-page="${cur}" aria-current="page"`));
    assert.doesNotMatch(html, /tbDesk/);
    assert.doesNotMatch(html, /\?v=31/, 'every asset is bumped');
    assert.match(html, /charts\.css\?v=32/);
  });
}

test('app.js builds the three URLs from location.hostname, carrying the stylesheet\'s ?v', () => {
  const fn = APP.slice(APP.indexOf('function initPageSwitcher'), APP.indexOf('async function init()'));
  assert.match(fn, /location\.hostname/);
  assert.match(fn, /:8850\//);
  assert.match(fn, /:8852\/\$\{q\}/);
  assert.match(fn, /:8852\/backtest\$\{q\}/);
  assert.match(fn, /charts\.css/);
  assert.doesNotMatch(APP, /#tbDesk/);
  assert.ok(APP.indexOf('initPageSwitcher();') > APP.indexOf('async function init()'), 'init() calls it');
});
