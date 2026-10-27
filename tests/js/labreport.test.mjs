/* The Strategy Tester under the Lab's chart is a read-only "Report" (plan 4.6): on the Lab page (body.lab-page) testerui.js builds
   no Run, range pill, heat-map tab or Compare (labMode), and its starts refuse; lab.css also hides them, a second guard, keyed on
   the tab's data-tab that testerui.js sets. testerui.js's own functions run in a vm with a fake page. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const src = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');
const UI = src('charts/testerui.js'), CSS = src('charts/lab.css'), LAB = src('charts/lab.js');

const tabsOf = (labMode) => {
  const body = UI.slice(UI.indexOf('function refreshTabsBar'), UI.indexOf('\n}\n', UI.indexOf('function refreshTabsBar')) + 3);
  const el = (tag, cls = '', text = '') => ({ tag, className: cls, textContent: text, dataset: {}, attrs: {}, kids: [], setAttribute(k, v) { this.attrs[k] = v; },
    append(...k) { this.kids.push(...k); }, appendChild(k) { this.kids.push(k); } });
  const tabsEl = { kids: [], replaceChildren() { this.kids = []; }, appendChild(k) { this.kids.push(k); } };
  const c = vm.createContext({ labMode, tabsEl, compare: {}, innerTab: 'overview', hidden: false, rules: false, store: {},
    page: { mk: el }, document: { createTextNode: (t) => ({ text: t }) }, notify() {}, saveStore() {}, refreshContent() {} });
  const inner = /const INNER_TABS = [\s\S]*?\]\];/.exec(UI)[0];
  vm.runInContext(`${inner}\n${body}\nrefreshTabsBar();`, c);
  return JSON.parse(JSON.stringify(tabsEl.kids.filter((k) => k.tag === 'button').map((b) => b.dataset.tab)));
};
test('every tester tab carries its id as data-tab (the heat map and Compare too)', () => {
  assert.deepEqual(tabsOf(false), ['overview', 'summary', 'trades', 'properties', 'heatmap', 'compare']);
});

test('on the Lab page the Report builds no heat-map or Compare tab, no Run and no range pill; its starts refuse', () => {
  assert.deepEqual(tabsOf(true), ['overview', 'summary', 'trades', 'properties']);
  assert.match(UI, /const labMode = !!\(document\.body && document\.body\.classList\.contains\('lab-page'\)\);/);
  const fn = (name) => { const i = UI.indexOf(`function ${name}(`); return UI.slice(i, UI.indexOf('\n}\n', i) + 3); };
  const head = (labMode) => {
    const kids = [], mkBtn = (n) => () => ({ n });
    const c = vm.createContext({ labMode, headerEl: { replaceChildren() { kids.length = 0; }, appendChild(k) { kids.push(k.n); }, contains: () => false },
      document: { activeElement: null }, schemaFor: () => ({ name: 'S' }), strategyId: 's', openInputsDialog() {}, runStatus: null, wfInFlight: () => false,
      strategySelect: mkBtn('strategy'), iconBtn: mkBtn('gear'), rangePill: mkBtn('range'), runArea: mkBtn('run'), recentRunsBtn: mkBtn('recent'),
      costInput: mkBtn('cost'), COST_FIELDS: [['c', 'C', 0, 1, 1]], page: { mk: () => ({ n: 'err' }) }, syncRunState() {}, errEl: null });
    vm.runInContext(`${fn('refreshHeader')}\nrefreshHeader();`, c);
    return kids.join(' ');
  };
  assert.equal(head(false), 'strategy gear range cost run recent err');
  assert.equal(head(true), 'strategy gear cost recent err');
  for (const f of ['startRun', 'startGrid', 'startWf']) assert.match(fn(f), new RegExp(`^function ${f}\\(\\) \\{\\n  if \\(labMode\\) return;`), f);
  assert.match(fn('startCompare'), /^function startCompare\(ids\) \{\n  if \(labMode \|\| ids\.length !== 2\) return;/);
  assert.match(fn('recentRunRow'), /if \(!done \|\| labMode\) return b;/);
  assert.match(fn('fillRecentRunsMenu'), /if \(labMode\) \{ page\.placeMenu\(\); return; \}\n      const footer = compareFooter\(\);/);
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
