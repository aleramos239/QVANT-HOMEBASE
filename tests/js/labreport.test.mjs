/* The Strategy Tester under the Lab's chart is a read-only "Report" (plan 4.6): its own Run, the range pill, the heat-map tab and
   Compare (the tab, and the Recent runs menu's checkboxes) are hidden by lab.css, keyed on the tab's data-tab that testerui.js
   sets. testerui.js's own refreshTabsBar runs in a vm with a fake page. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const src = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');
const UI = src('charts/testerui.js'), CSS = src('charts/lab.css'), LAB = src('charts/lab.js');

test('every tester tab carries its id as data-tab (the heat map and Compare too)', () => {
  const body = UI.slice(UI.indexOf('function refreshTabsBar'), UI.indexOf('\n}\n', UI.indexOf('function refreshTabsBar')) + 3);
  const el = (tag, cls = '', text = '') => ({ tag, className: cls, textContent: text, dataset: {}, attrs: {}, kids: [], setAttribute(k, v) { this.attrs[k] = v; },
    append(...k) { this.kids.push(...k); }, appendChild(k) { this.kids.push(k); } });
  const tabsEl = { kids: [], replaceChildren() { this.kids = []; }, appendChild(k) { this.kids.push(k); } };
  const c = vm.createContext({ tabsEl, compare: {}, innerTab: 'overview', hidden: false, rules: false, store: {},
    page: { mk: el }, document: { createTextNode: (t) => ({ text: t }) }, notify() {}, saveStore() {}, refreshContent() {} });
  const inner = /const INNER_TABS = [\s\S]*?\]\];/.exec(UI)[0];
  vm.runInContext(`${inner}\n${body}\nrefreshTabsBar();`, c);
  const tabs = tabsEl.kids.filter((k) => k.tag === 'button').map((b) => b.dataset.tab);
  assert.deepEqual(JSON.parse(JSON.stringify(tabs)), ['overview', 'summary', 'trades', 'properties', 'heatmap', 'compare']);
});

test('lab.css hides the tester\'s Run, range pill, heat-map tab and Compare in the Report only; the rest stays', () => {
  const rule = CSS.slice(CSS.indexOf('/* The Strategy Tester under the chart is a read-only Report'));
  for (const sel of ['.lab[data-report="1"] .bpanel .tst-run-area', '.lab[data-report="1"] .bpanel .tst-range',
    '.lab[data-report="1"] .bpanel .tst-tab[data-tab="heatmap"]', '.lab[data-report="1"] .bpanel .tst-tab[data-tab="compare"]',
    '.lab-page .menu-tester-runs .tst-cmp-cb', '.lab-page .menu-tester-runs .tst-cmp-footer']) assert.ok(rule.includes(sel), sel);
  assert.match(rule, /\{ display: none !important; \}/);
  // the trades and metrics tabs are never hidden
  assert.doesNotMatch(CSS, /data-tab="(overview|summary|trades|properties)"/);
  // the tester's markup: its run area and range pill carry the classes the rules use
  assert.match(UI, /page\.mk\('span', 'tst-run-area'\)/);
  assert.match(UI, /page\.mk\('button', 'tst-btn tst-range'\)/);
  assert.match(UI, /'menu-tester-runs'/);
  assert.match(src('backtest.html'), /<body class="lab-page">/);
});

test('the Lab calls it "Report"', () => {
  assert.match(LAB, /'Hide the report' : 'Report'/);
  assert.doesNotMatch(LAB, /'Full report'/);
});
