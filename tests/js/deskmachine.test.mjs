import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* WP1.18: the Desk page's ONE machine reader (desk/core.js): the native shell's window.HB_MACHINE, else /api/status `machine`
   (ST), read at call time. Confirm texts name the machine with machineWords(); unknown says nothing, never "this Mac".
   The button half (no Open in the Lab / Show on chart on the server) is in desklabdesk.test.mjs. */
import { HTML } from './deskpage.mjs';
const BLOCK = HTML.slice(HTML.indexOf('/* ---- which machine this Desk runs on'), HTML.indexOf('/* ---- algo manager'));

function load(hb, ST) {
  const ctx = vm.createContext({ window: hb === undefined ? {} : { HB_MACHINE: hb }, ST });
  vm.runInContext(BLOCK + '\nglobalThis.api = { deskMachine, machineWords };', ctx);
  return ctx;
}

test('server: "on the SERVER · Chicago"; mac: "on this Mac"; missing or anything else: no words', () => {
  assert.ok(BLOCK.length > 100, 'the block is in the page');
  assert.equal(load('server', null).api.machineWords(), 'on the SERVER · Chicago');
  assert.equal(load(undefined, { machine: 'server' }).api.machineWords(), 'on the SERVER · Chicago');
  assert.equal(load('mac', null).api.machineWords(), 'on this Mac');
  assert.equal(load(undefined, { machine: 'mac' }).api.machineWords(), 'on this Mac');
  for (const [hb, st] of [[undefined, null], [undefined, {}], [null, { machine: null }], ['vps', null], [undefined, { machine: 'localhost' }]]) {
    const c = load(hb, st);
    assert.equal(c.api.machineWords(), '', `${hb} / ${JSON.stringify(st)}`);
  }
  assert.equal(load(undefined, null).api.deskMachine(), null, 'unknown is null');
});

test('the shell\'s value wins over the status; the status is read at call time (each /api/status poll)', () => {
  assert.equal(load('mac', { machine: 'server' }).api.deskMachine(), 'mac');
  const c = load(undefined, null);
  assert.equal(c.api.deskMachine(), null);
  vm.runInContext('ST = { machine: "server" };', c);
  assert.equal(c.api.deskMachine(), 'server');
  c.window.HB_MACHINE = 'mac';
  assert.equal(c.api.machineWords(), 'on this Mac');
});

test('no guess from the address: the reader never looks at location or the hostname', () => {
  assert.doesNotMatch(BLOCK.replace(/\/\*[\s\S]*?\*\//g, ''), /location|hostname|127\.0\.0\.1|localhost/);
});
