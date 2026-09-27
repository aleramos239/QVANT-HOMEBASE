import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

function load() {
  globalThis.window = { HBDom: require('../../homebase/static/charts/dom.js'), HBCatalog: require('../../homebase/static/charts/catalog.js') };
  const path = require.resolve('../../homebase/static/charts/l2layer.js');
  delete require.cache[path];
  return require(path);
}

function fakeCell() {
  const lines = new Set();
  const candles = {
    createPriceLine: (o) => { const pl = { o, applyOptions: (x) => Object.assign(pl.o, x) }; lines.add(pl); return pl; },
    removePriceLine: (pl) => lines.delete(pl),
  };
  const cell = { cfg: { root: 'NQ', indicators: [{ uid: 'u1', id: 'bigorders', params: { multiple: 5 }, visible: true }] },
    shown: { root: 'NQ' }, chart: {}, candles, tick: 0.25, P: {}, rows: [] };
  return { cell, lines };
}

test('big-order lines: drawn off the live book, never on a Bar Replay chart (review I4)', () => {
  const L = load();
  const { cell, lines } = fakeCell();
  let ov = null;
  try {
    const t = Date.now();
    for (let i = 0; i < 20; i++) L.onDepth({ type: 'depth', root: 'NQ', ts: t - 20_000 + i * 1000, bids: [[100, 2], [99.75, 2]], offers: [[100.25, 2]] });
    L.onDepth({ type: 'depth', root: 'NQ', ts: t, bids: [[100, 50], [99.75, 2]], offers: [[100.25, 2]] });
    ov = L.overlay(cell);
    assert.equal(lines.size, 1);
    assert.equal([...lines][0].o.price, 100);
    L.onDepth({ type: 'depth', root: 'NQ', ts: t + 100, bids: [[100.0000000001, 50], [99.75, 2]], offers: [[100.25, 2]] });
    ov.paint();
    assert.equal(lines.size, 1);                            // the same line: keyed by tick index (review 7)
    cell.replay = { date: '2026-09-24', cursorMs: t - 86_400_000 };
    ov.paint();
    assert.equal(lines.size, 0);                            // a replaying chart shows another date
    cell.replay = null;
    ov.paint();
    assert.equal(lines.size, 1);
    L.onDisconnect();
    ov.paint();
    assert.equal(lines.size, 0);                            // the /ws dropped: no book, no lines
  } finally {
    if (ov) ov.destroy();
    delete globalThis.window;
  }
});
