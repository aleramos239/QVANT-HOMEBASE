import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';

/* c-30 (2026-10-27): when the Desk link or the chart service drops, the chart's lines stay drawn from the last state,
   greyed and tagged "not live", read-only; they come back live with the next state. Display only: the tradelines.js
   methods lifted and run on stand-ins, the real HBTrade. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const SRC = readFileSync(new URL('../../homebase/static/charts/tradelines.js', import.meta.url), 'utf8');
const method = (name) => {
  const i = SRC.indexOf(`\n  ${name}(`);
  assert.ok(i >= 0, `defines ${name}`);
  return SRC.slice(i + 1, SRC.indexOf('\n  }\n', i) + 4);
};
const fakeEl = (tagName) => ({ tagName, className: '', textContent: '', title: '', hidden: false, disabled: false, children: [], style: { setProperty() {} },
  classList: { on: new Set(), toggle(c, v) { if (v) this.on.add(c); else this.on.delete(c); }, contains(c) { return this.on.has(c); } },
  append(...k) { this.children.push(...k); }, setAttribute() {}, remove() {} });

const acct = { id: 'sim041', label: 'SIM0000041', env: 'demo', tradable: true,
  positions: [{ symbol: 'NQZ6', root: 'NQ', net: 1, avg_price: 30000 }],
  orders: [{ order_id: '7', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, stop_price: 29980, status: 'Working' }] };
const state = { enabled: true, accounts: [acct] };

function overlay(Dc) {
  const made = [], zones = [], P = { up: 'U', down: 'D', accent: 'A', text2: 'G' };
  const ctx = vm.createContext({ T, window: { HBDeskClient: { quotes: {}, notWorking: () => new Set(), ...Dc },
    HBTradeUI: { busy: () => false, flatBusy: () => false, tradeOf: () => ({ accounts: ['sim041'] }), editableIds: () => ['sim041'] } },
    document: { createElement: fakeEl } });
  vm.runInContext(`globalThis.O = { ${method('paintLines')}, ${method('buildChip')}, ${method('wireChip')}, ${method('paint')} };`, ctx);
  const ov = { root: 'NQ', items: new Map(), dragging: null, named: false, layer: { appendChild() {} },
    cell: { tick: 0.25, P, candles: { createPriceLine: (o) => { const l = { o, applyOptions: (x) => Object.assign(l.o, x) }; made.push(l); return l; }, removePriceLine() {} } },
    zones: { set: (z) => zones.push(z) }, sync() {} };
  for (const k of ['paintLines', 'buildChip', 'wireChip', 'paint']) ov[k] = ctx.O[k].bind(ov);
  return { ov, made, zones, items: ov.items };
}

test('c-30: live -- the lines are as before: editable, own colour, no "not live"', () => {
  const { ov, items, zones } = overlay({ state, stale: null, heldState: null });
  ov.paintLines({ mode: 'on' });
  const sl = [...items.values()].find((i) => i.g.kind === 'sl');
  assert.equal(sl.g.editable, true);
  assert.doesNotMatch(sl.chip.text.textContent, /not live/);
  assert.equal(zones.at(-1).length, 1, 'the SL zone');
});

test('c-30: the Desk link is down -- the held lines stay, grey, "not live", read-only, no zones', () => {
  const { ov, items, made, zones } = overlay({ state: null, stale: 'desk', heldState: state });
  ov.paintLines({ mode: 'down' });
  assert.equal(items.size, 2, 'the position and its stop are still drawn');
  for (const it of items.values()) {
    assert.equal(it.g.editable, false, 'nothing can be moved or closed from a held line');
    assert.equal(it.chip.classList.contains('view'), true);
    assert.equal(it.chip.btn.hidden, true, 'no ×');
    assert.equal(it.chip.be.hidden, true, 'no BE+1');
    assert.equal(it.chip.text.onpointerdown, null, 'no drag');
    assert.match(it.chip.text.textContent, / · not live$/);
    assert.equal(it.chip.classList.contains('gone'), true, 'greyed like a line the desk says is not working');
    assert.match(it.chip.title, /not live/i);
  }
  assert.ok(made.every((l) => l.o.color === 'G'), 'grey on the chart');
  assert.equal(zones.at(-1).length, 0);
});

test('c-30: the chart service socket is down with the state still held by the page -- same marks, editability untouched', () => {
  const { ov, items } = overlay({ state, stale: 'service', heldState: null });
  ov.paintLines({ mode: 'on' });
  const sl = [...items.values()].find((i) => i.g.kind === 'sl');
  assert.match(sl.chip.text.textContent, / · not live$/);
  assert.equal(sl.g.editable, true, 'the display only changes how it looks');
});

test('c-30: the PAPER book lives in the chart service -- while only the Desk is down its lines are not marked', () => {
  const paperState = { enabled: true, accounts: [acct, { ...acct, id: 'paper', env: 'paper', label: 'PAPER' }] };
  const { ov, items } = overlay({ state: null, stale: 'desk', heldState: paperState });
  ov.paintLines({ mode: 'down' });
  const marks = [...items.values()].map((i) => [!!i.g.paper, /not live/.test(i.chip.text.textContent)]);
  assert.ok(marks.some(([p]) => p) && marks.filter(([p]) => !p).length === 2);
  assert.ok(marks.every(([p, nl]) => nl === !p), JSON.stringify(marks));
});

test('c-30: lineColor greys a stale line', () => {
  assert.equal(T.lineColor({ kind: 'sl', stale: true }, { down: 'D', text2: 'G' }), 'G');
  assert.equal(T.lineColor({ kind: 'sl' }, { down: 'D', text2: 'G' }), 'D');
});

test('c-31: a page reload starts with no state and no held lines -- nothing is drawn until the desk\'s first full state', () => {
  const D = (() => {
    const win = { HBTrade: T, HBIcons: { x: '' } };
    vm.runInNewContext(readFileSync(new URL('../../homebase/static/charts/deskclient.js', import.meta.url), 'utf8'),
      { window: win, localStorage: { getItem: () => null, setItem() {} }, requestAnimationFrame: () => 0, setTimeout: () => 0, console,
        document: { getElementById: () => null } });
    return win.HBDeskClient;
  })();
  assert.equal(D.state, null);
  assert.equal(D.heldState, null);
  assert.equal(D.stale, null);
  assert.deepEqual(T.linesFor(D.state, 'NQ', []), []);
  D.onMessage({ type: 'desk', event: 'state', data: state });
  assert.equal(T.linesFor(D.state, 'NQ', ['sim041']).length, 2, 'the lines are rebuilt from the state alone');
});
