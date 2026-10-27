import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* Audit 2026-10-27 (repair pass): funded PA/LTF prop accounts are live=False, so /api/status sends them as env "demo".
   The desk page's confirms (booking, size raise, cycle) key on isRealAcct: only a paper account may skip them. */
const src = readFileSync(new URL('../../homebase/static/desk/book.js', import.meta.url), 'utf8');
const fn = src.slice(src.indexOf('function isRealAcct('), src.indexOf('/* "APEX'));
const run = (accounts) => { const c = vm.createContext({ ST: { accounts } }); vm.runInContext(fn, c); return c.isRealAcct; };

test('a demo-env (funded) account gets the LIVE confirms; only paper skips them', () => {
  const is = run({ funded: { env: 'demo' }, real: { env: 'live' }, sim: { env: 'paper' } });
  assert.equal(is('funded'), true);
  assert.equal(is('real'), true);
  assert.equal(is('sim'), false);
  assert.equal(is('unknown'), true, 'an account the desk does not list counts as real money');
});
