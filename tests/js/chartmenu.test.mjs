import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const M = require('../../homebase/static/charts/chartmenu.js');

const texts = (list) => list.map((x) => (x.sep ? '—' : x.text));
const CTX = { price: 30878, tick: 0.25, nDrawings: 0, nIndicators: 0 };
const fresh = () => M.builtins(M.createRegistry());
const noop = () => {};

test('no drawings and no indicators: Reset, Copy price, Settings, each in its own section', () => {
  assert.deepEqual(M.SECTIONS, ['view', 'copy', 'trading', 'remove', 'settings']);
  assert.deepEqual(texts(fresh().items(CTX)), ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Settings…']);
});

test('Remove N drawings / Remove N indicators only when N > 0, drawings first, singular for one', () => {
  const reg = fresh();
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 3, nIndicators: 1 })),
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 3 drawings', 'Remove 1 indicator', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 1 })).slice(4, 5), ['Remove 1 drawing']);
  assert.deepEqual(texts(reg.items({ ...CTX, nIndicators: 4 })).slice(4, 5), ['Remove 4 indicators']);
});

test('each built-in names its action; Reset shows ⌥R; Copy carries the plain price', () => {
  const list = fresh().items({ ...CTX, nDrawings: 2, nIndicators: 2 }).filter((x) => !x.sep);
  assert.deepEqual(list.map((x) => x.act), ['reset', 'copy', 'removeDrawings', 'removeIndicators', 'settings']);
  assert.deepEqual(list.map((x) => x.section), ['view', 'copy', 'remove', 'remove', 'settings']);
  assert.equal(list[0].sub, '⌥R');
  assert.equal(list[1].copy, '30878.00');
});

test('Copy price is tick-rounded; no price (the pointer off the scale) = no Copy item and no stray divider', () => {
  const reg = fresh();
  const at = reg.items({ ...CTX, price: 30878.13 }).find((x) => x.act === 'copy');
  assert.equal(at.text, 'Copy price 30,878.25');
  assert.equal(at.copy, '30878.25');
  assert.deepEqual(texts(reg.items({ ...CTX, price: null })), ['Reset chart view', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, price: NaN })), ['Reset chart view', '—', 'Settings…']);
  assert.equal(M.copyText(2650.34, 0.1), '2650.3');
  assert.equal(M.copyLabel(2650.34, 0.1), 'Copy price 2,650.3');
});

test('the extension point: a trading section between Copy and Remove, dividers around it, ctx passed in', () => {
  const reg = fresh();
  let seen = null;
  const off = reg.register('trading', (ctx) => {
    seen = ctx;
    return [{ text: `Buy 1 NQ @ ${ctx.price} limit`, run: noop }, { text: 'Sell 1 NQ @ stop', run: noop }];
  });
  const ctx = { ...CTX, nDrawings: 2 };
  const list = reg.items(ctx);
  assert.deepEqual(texts(list), ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Buy 1 NQ @ 30878 limit',
    'Sell 1 NQ @ stop', '—', 'Remove 2 drawings', '—', 'Settings…']);
  assert.equal(seen, ctx);
  assert.equal(list[4].section, 'trading');
  assert.equal(typeof list[4].run, 'function');
  off();
  assert.deepEqual(texts(reg.items(ctx)),
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 2 drawings', '—', 'Settings…']);
  off();   // a second call is harmless
});

test('registrations keep their order in a section; an extension comes after the built-ins of its section', () => {
  const reg = fresh();
  reg.register('trading', () => [{ text: 'A', run: noop }]);
  reg.register('trading', () => [{ text: 'B', run: noop }]);
  reg.register('remove', () => [{ text: 'Remove alerts', run: noop }]);
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 1 })), ['Reset chart view', '—', 'Copy price 30,878.00', '—',
    'A', 'B', '—', 'Remove 1 drawing', 'Remove alerts', '—', 'Settings…']);
});

test('unknown sections and non-functions are refused; a throwing or junk extension is skipped', () => {
  const reg = fresh();
  assert.throws(() => reg.register('orders', () => []), /unknown chart menu section: orders/);
  assert.throws(() => reg.register('trading', 5), TypeError);
  reg.register('trading', () => { throw new Error('broken'); });
  reg.register('trading', () => [null, 'junk', { text: '', run: noop }, { text: 'no action' }]);
  reg.register('trading', () => 'not a list');
  assert.deepEqual(texts(reg.items(CTX)), texts(fresh().items(CTX)));
});

test('the page-wide HBChartMenu has the built-ins and the same extension point', () => {
  assert.deepEqual(texts(M.items(CTX)), texts(fresh().items(CTX)));
  const off = M.register('trading', () => [{ text: 'Buy', run: noop }]);
  assert.ok(texts(M.items(CTX)).includes('Buy'));
  off();
  assert.ok(!texts(M.items(CTX)).includes('Buy'));
});

test('the indicator menu: move to the other placement, then Remove; Remove only for what cannot move', () => {
  assert.deepEqual(M.paneItems({ id: 'delta', pane: 'own' }),
    [{ act: 'move', pane: 'main', text: 'Move to main chart' }, { act: 'remove', text: 'Remove' }]);
  assert.deepEqual(M.paneItems({ id: 'cumdelta', pane: 'main' }),
    [{ act: 'move', pane: 'own', text: 'Move to new pane below' }, { act: 'remove', text: 'Remove' }]);
  assert.deepEqual(M.paneItems({ id: 'volume' }).map((x) => x.text), ['Move to new pane below', 'Remove']);
  assert.deepEqual(M.paneItems({ id: 'ema', params: { length: 9 } }), [{ act: 'remove', text: 'Remove' }]);
});

test('the armed Remove-drawings text is the rail\'s', () => {
  assert.equal(M.armText(3, 'NQ'), 'Click again to remove 3 drawings on NQ');
  assert.equal(M.armText(1, 'ES'), 'Click again to remove 1 drawing on ES');
});

test('arrow keys walk the items and wrap; Home/End jump; nothing to walk = -1', () => {
  assert.equal(M.step(-1, 3, 'ArrowDown'), 0);
  assert.equal(M.step(0, 3, 'ArrowDown'), 1);
  assert.equal(M.step(2, 3, 'ArrowDown'), 0);
  assert.equal(M.step(-1, 3, 'ArrowUp'), 2);
  assert.equal(M.step(0, 3, 'ArrowUp'), 2);
  assert.equal(M.step(1, 3, 'Home'), 0);
  assert.equal(M.step(1, 3, 'End'), 2);
  assert.equal(M.step(1, 3, 'Tab'), 1);
  assert.equal(M.step(-1, 0, 'ArrowDown'), -1);
});
