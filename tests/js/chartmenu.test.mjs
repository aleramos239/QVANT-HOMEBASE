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
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 3 drawings', 'Remove 1 indicator',
      'Hide all indicators', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 1 })).slice(4, 5), ['Remove 1 drawing']);
  assert.deepEqual(texts(reg.items({ ...CTX, nIndicators: 4 })).slice(4, 5), ['Remove 4 indicators']);
});

test('each built-in names its action; Reset shows ⌥R; Copy carries the plain price', () => {
  const list = fresh().items({ ...CTX, nDrawings: 2, nIndicators: 2 }).filter((x) => !x.sep);
  assert.deepEqual(list.map((x) => x.act), ['reset', 'copy', 'removeDrawings', 'removeIndicators', 'toggleIndicators', 'settings']);
  assert.deepEqual(list.map((x) => x.section), ['view', 'copy', 'remove', 'remove', 'remove', 'settings']);
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

test('Hide/Show all indicators: only when there are indicators, text flips with allIndicatorsHidden', () => {
  const reg = fresh();
  assert.deepEqual(texts(reg.items({ ...CTX, nIndicators: 3 })),
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 3 indicators', 'Hide all indicators', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, nIndicators: 3, allIndicatorsHidden: true })),
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 3 indicators', 'Show all indicators', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, nIndicators: 0, allIndicatorsHidden: true })), texts(reg.items(CTX)));
  const it = reg.items({ ...CTX, nIndicators: 1 }).find((x) => x.act === 'toggleIndicators');
  assert.equal(it.section, 'remove');
});

test('the legend fold map: readFolded sanitizes, toggleFolded flips one cell without touching the others', () => {
  assert.deepEqual(M.readFolded(null), {});
  assert.deepEqual(M.readFolded('not json'), {});
  assert.deepEqual(M.readFolded('[1,2,3]'), {});          // an array is not a map
  assert.deepEqual(M.readFolded('"just a string"'), {});
  assert.deepEqual(M.readFolded(JSON.stringify({ 0: true, 1: false, 2: 'yes', x: true })), { 0: true, x: true });
  assert.equal(M.isFolded({ 0: true }, 0), true);
  assert.equal(M.isFolded({ 0: true }, 1), false);
  assert.equal(M.isFolded(null, 0), false);
  assert.equal(M.isFolded({}, 0), false);

  let map = M.toggleFolded({}, 1);
  assert.deepEqual(map, { 1: true });
  assert.equal(M.isFolded(map, 1), true);
  assert.equal(M.isFolded(map, 0), false);
  map = M.toggleFolded(map, 0);
  assert.deepEqual(map, { 0: true, 1: true });   // toggling one cell leaves another already-folded one alone
  map = M.toggleFolded(map, 1);
  assert.deepEqual(map, { 0: true });            // toggled back off: the key is removed, not set to false
  const before = { 3: true };
  assert.notEqual(M.toggleFolded(before, 3), before);   // a new map, never mutated in place
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

/* W2 (2026-09-28): a popup menu never runs past the space it can show in -- the interval menu's Custom row sat below
   the window's bottom edge. fitMenu places it and caps its height (it scrolls inside) against `bounds`: the window, or
   the dialog it opened from. */
const WIN = (w, h) => ({ left: 0, top: 0, right: w, bottom: h });
const rect = (left, top, width, height) => ({ left, top, width, height, right: left + width, bottom: top + height });

test('W2 fitMenu: under its trigger when it fits, above only when that side has the room -- no cap either way', () => {
  const btn = rect(300, 38, 34, 34);
  assert.deepEqual(M.fitMenu({ r: btn, w: 200, h: 300, bounds: WIN(1280, 800) }),
    { left: 300, top: 76, maxHeight: null, originX: 17, originY: 0 });   // grown from the button's middle
  const foot = rect(250, 656, 110, 32);                          // a dialog footer's Template ▾ near the bottom
  const up = M.fitMenu({ r: foot, w: 240, h: 122, bounds: WIN(1280, 700) });
  assert.deepEqual([up.top, up.maxHeight, up.originY], [656 - 4 - 122, null, 122], 'above, grown from its bottom edge');
});

test('W2 fitMenu: too tall for either side -- the roomier side, its height capped to the window (it scrolls inside)', () => {
  const iv = rect(295, 38, 34, 34);                               // the interval menu's toolbar button
  for (const vh of [800, 600, 480]) {
    const p = M.fitMenu({ r: iv, w: 274, h: 900, bounds: WIN(1280, vh) });
    assert.equal(p.top, 76, 'still under its button');
    assert.equal(p.maxHeight, vh - 4 - 76, `capped to the room below at ${vh} px`);
    assert.equal(p.top + p.maxHeight, vh - 4, 'its bottom 4 px inside the window: the Custom row is reachable');
  }
  const low = rect(300, 500, 40, 30);                             // more room above: it goes up, capped there
  const p = M.fitMenu({ r: low, w: 200, h: 700, bounds: WIN(1280, 600) });
  assert.deepEqual([p.top, p.maxHeight, p.originY], [4, 500 - 4 - 4, 500 - 4 - 4], 'the room above: 4 px gap, 4 px margin');
});

test('W2 fitMenu: a context menu at the pointer and a rail flyout stay inside, capped when taller than the window', () => {
  const at = M.fitMenu({ mode: 'at', at: { x: 1250, y: 780 }, w: 240, h: 300, bounds: WIN(1280, 800) });
  assert.deepEqual([at.left, at.top, at.maxHeight], [1280 - 240 - 4, 800 - 300 - 4, null]);
  assert.deepEqual([at.originX, at.originY], [1250 - at.left, 780 - at.top], 'grows from the pointer');
  const tall = M.fitMenu({ mode: 'at', at: { x: 10, y: 300 }, w: 240, h: 1000, bounds: WIN(1280, 600) });
  assert.deepEqual([tall.top, tall.maxHeight], [4, 592]);
  const fly = M.fitMenu({ mode: 'right', r: rect(8, 560, 36, 36), w: 180, h: 90, bounds: WIN(1280, 600) });
  assert.deepEqual([fly.left, fly.top, fly.maxHeight], [8 + 36 + 8, 600 - 90 - 4, null]);
});

test('W2 fitMenu: inside a dialog (which clips its menus) the dialog is the bounds -- kept within it', () => {
  const dialog = { left: 230, top: 100, right: 1050, bottom: 700 };
  const swatch = rect(1000, 300, 28, 28);                          // a colour swatch near the dialog's right edge
  const p = M.fitMenu({ r: swatch, w: 252, h: 180, bounds: dialog });
  assert.equal(p.left, 1050 - 252 - 4, 'pulled left to stay inside the dialog');
  assert.ok(p.top + 180 <= 700 - 4 && p.top >= 100 + 4);
  const tpl = M.fitMenu({ r: rect(250, 656, 110, 32), w: 240, h: 600, bounds: dialog });
  assert.deepEqual([tpl.top, tpl.maxHeight], [100 + 4, 656 - 4 - (100 + 4)], 'too tall for the dialog: capped to its room above');
});
