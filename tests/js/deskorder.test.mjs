import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The Desk's static/desk/*.js files are classic scripts: one global scope, run one by one in their index.html order.
   At load time a file may only use what an EARLIER file declared -- a function from a later file is a ReferenceError in the
   browser and the rest of that file never runs. One inline script hid that by hoisting until the split (2026-10-26), and
   deskpage.mjs / desk_page_util.py still join the files into one script, so this is the test that runs them APART: each
   file its own vm script, in order, one context, every browser global a do-nothing stub. It fails on a file that throws
   at load (a let/const declared twice, a TDZ read) or on a load-time lookup of a name that only a later file declares. */
const STATIC = new URL('../../homebase/static/', import.meta.url);
const FILES = [...readFileSync(new URL('index.html', STATIC), 'utf8')
  .matchAll(/<script src="\/static\/(desk\/[\w-]+\.js)\?v=\d+"><\/script>/g)].map((m) => m[1]);

function runApart(sources) {                                   // [[name, code], ...] -> {errors, later}
  const BUILTIN = new Set(vm.runInNewContext('Object.getOwnPropertyNames(globalThis)'));
  const stub = new Proxy(function () {}, {
    get(t, k) { if (k === Symbol.toPrimitive) return () => ''; if (k === Symbol.iterator) return [][Symbol.iterator]; return stub; },
    apply() { return stub; }, construct() { return stub; }, set() { return true; } });
  const target = {};                                           // the context's own builtins do not show through the proxy
  for (const n of BUILTIN) if (n !== 'globalThis' && n in globalThis) target[n] = globalThis[n];
  let cur = -1, strict = false; const looked = new Map();      // undeclared name -> first file that used it at load
  const note = (k) => { if (cur >= 0 && !looked.has(k)) looked.set(k, cur); };
  const ctx = vm.createContext(new Proxy(target, {
    has(t, k) { if (k in t || typeof k !== 'string') return k in t; if (BUILTIN.has(k) || strict) return false; note(k); return true; },
    get(t, k) { if (k in t) return t[k]; if (typeof k !== 'string' || BUILTIN.has(k) || strict) return undefined; note(k); return stub; },
  }));
  const errors = [];
  sources.forEach(([name, code], i) => {
    cur = i;
    try { vm.runInContext(code, ctx, { filename: name }); } catch (e) { errors.push(`${name}: ${e && e.name}: ${e && e.message}`); }
  });
  cur = -1; strict = true;                                     // now only what the files declared resolves
  const later = [...looked].filter(([n]) => /^[A-Za-z_$][\w$]*$/.test(n) && vm.runInContext(`typeof ${n}`, ctx) !== 'undefined')
    .map(([n, i]) => `${sources[i][0]} uses ${n} at load, a later file declares it`);
  return { errors, later };
}

test('the desk files run apart, in page order, with no load-time throw and no name from a later file', () => {
  assert.equal(FILES.length, 13, FILES.join(' '));
  const r = runApart(FILES.map((f) => [f, readFileSync(new URL(f, STATIC), 'utf8')]));
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.later, []);
});

test('the check itself catches a later function, a later const and a double let', () => {
  assert.deepEqual(runApart([['a', 'const x = laterFn(1);'], ['b', 'function laterFn() { return 1; }']]).later,
    ['a uses laterFn at load, a later file declares it']);
  assert.deepEqual(runApart([['a', 'const y = LATER + 1;'], ['b', 'const LATER = 2;']]).later,
    ['a uses LATER at load, a later file declares it']);
  assert.match(runApart([['a', 'let z = 1;'], ['b', 'let z = 2;']]).errors.join(), /already been declared/);
  assert.deepEqual(runApart([['a', 'function f() { return g(); }'], ['b', 'function g() {}'], ['c', 'f();']]), { errors: [], later: [] });
});
