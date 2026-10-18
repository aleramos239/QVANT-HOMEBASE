import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* sounds.js (the owner, 2026-10-18) under a tiny shim: off until switched on; each fill sounds as what its order was
   (entry / take profit / stop, a PAPER leg's own role); a bot's fills are silent; settings kept in localStorage. */
function load() {
  const store = new Map(), played = [], deskFill = [], paperFill = [], deskOn = [];
  const state = { accounts: [
    { id: 'a', positions: [{ symbol: 'NQZ6', net: 2 }],
      orders: [{ order_id: 's', symbol: 'NQZ6', side: 'Sell', type: 'Stop' }, { order_id: 't', symbol: 'NQZ6', side: 'Sell', type: 'Limit' },
        { order_id: 'e', symbol: 'NQZ6', side: 'Buy', type: 'Limit' }] },
    { id: 'paper', positions: [], orders: [{ order_id: 'p', symbol: 'NQZ6', side: 'Sell', type: 'Limit', role: 'tp' }] },
  ] };
  const win = {
    HBTrade: {},
    HBDeskClient: { state, on: (fn) => deskOn.push(fn), onAnyFill: (fn) => deskFill.push(fn) },
    HBPaperClient: { onAnyFill: (fn) => paperFill.push(fn) },
  };
  const ctx = {
    window: win, localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    document: { readyState: 'complete', addEventListener() {} },
  };
  vm.runInNewContext(readFileSync(new URL('../../homebase/static/charts/sounds.js', import.meta.url), 'utf8'), ctx);
  const S = win.HBSounds;
  S.play = (name) => played.push(name);   // the event path calls play: no audio in a test
  return { S, played, store, desk: (fill) => deskFill.forEach((f) => f({ account: 'a', fill })), paper: (f) => paperFill.forEach((fn) => fn(f)) };
}

test('sounds: off by default, then each fill by what its order was', () => {
  const { S, played, store, desk, paper } = load();
  desk({ order_id: 's' });
  assert.deepEqual(played, [], 'off until switched on');
  S.set({ on: true, events: { sl: 'bell' } });
  assert.ok(JSON.parse(store.get('hb.sounds')).on, 'kept in this browser');
  desk({ order_id: 's' }); desk({ order_id: 't' }); desk({ order_id: 'e' }); desk({ order_id: 'unknown' });
  paper({ account: 'paper', order_id: 'p' });
  desk({ order_id: 's', owner: 'nq930' });
  assert.deepEqual(played, ['bell', 'chime', 'pop', 'pop', 'chime'], 'stop, TP, entry, a market entry, a PAPER TP leg; a bot fill silent');
  S.set({ events: { entry: 'off' } });
  desk({ order_id: 'e' });
  assert.equal(played.length, 5, 'an event set to Off');
  S.event('moved');
  assert.equal(played.at(-1), 'click');
});
