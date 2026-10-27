import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

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

test('D: Connect a LIVE account names the machine with machineWords(); unknown says nothing; demo asks nothing', async () => {
  const FN = HTML.slice(HTML.indexOf('async function wizNext1() {'), HTML.indexOf('function closeConnect() {'));
  const run = async (hb, env = 'live') => {
    const asked = [], steps = [];
    const ctx = vm.createContext({ window: hb === undefined ? {} : { HB_MACHINE: hb }, ST: null, WIZ: { env },
      confirmDlg: async (title, body) => { asked.push([title, body]); return true; }, wizGoto: (n) => steps.push(n) });
    vm.runInContext(BLOCK + FN + '\nglobalThis.api = { wizNext1 };', ctx);
    await ctx.api.wizNext1();
    return { asked, steps };
  };
  for (const [hb, where] of [['server', 'on the SERVER · Chicago'], ['mac', 'on this Mac']]) {
    const { asked, steps } = await run(hb);
    assert.equal(asked[0][0], 'Connect a LIVE account?');
    assert.match(asked[0][1], new RegExp(`^This account trades real money ${where}\\. Adding it does not start trading`));
    assert.deepEqual(steps, [2]);
  }
  const none = await run(undefined);
  assert.match(none.asked[0][1], /^This account trades real money\. Adding it/, 'unknown: no machine words, never a guess');
  assert.deepEqual((await run('server', 'demo')).asked, [], 'a demo login still asks nothing');
});

test('N: the plain top bar has a machine chip: Server · Chicago or This Mac, hidden while unknown; the Mac skin never shows it', () => {
  const chipOf = (hb, ST) => {
    const el = { hidden: false, textContent: 'x', className: '', title: '' };
    const ctx = vm.createContext({ window: hb === undefined ? {} : { HB_MACHINE: hb }, ST, $: (sel) => sel === '#machineChip' ? el : null });
    vm.runInContext(BLOCK + '\nrenderMachineChip();', ctx);
    return el;
  };
  const server = chipOf(undefined, { machine: 'server' });
  assert.deepEqual([server.hidden, server.textContent, server.className], [false, 'Server · Chicago', 'pill machine-server']);
  assert.equal(server.title, 'This Desk runs on the SERVER · Chicago');
  const mac = chipOf('mac', { machine: 'server' });
  assert.deepEqual([mac.hidden, mac.textContent, mac.className], [false, 'This Mac', 'pill idle'], 'the shell wins, as deskMachine');
  for (const [hb, st] of [[undefined, null], [undefined, {}], ['vps', null]]) {
    const c = chipOf(hb, st);
    assert.deepEqual([c.hidden, c.textContent], [true, ''], `unknown says nothing: ${hb} / ${JSON.stringify(st)}`);
  }
  // it sits in the plain header, which the Mac skin hides (and its CSS hides before the script runs): never two machine words
  const head = HTML.slice(HTML.indexOf('<header class="inset-topbar hb-bar">'), HTML.indexOf('</header>'));
  assert.match(head, /<span class="pill idle" id="machineChip" hidden><\/span>/);
  assert.match(HTML, /#machineChip\[hidden\]\{ display:none; \}/, '.pill is inline-flex: hidden needs its own rule');
  assert.match(HTML, /renderMaster\(\);\n  renderMachineChip\(\);/, 'drawn on every render');
  const skin = readFileSync(new URL('../../homebase/static/apple/desk.js', import.meta.url), 'utf8');
  assert.doesNotMatch(skin, /machineChip/);
  assert.match(skin, /const old = \$\('\.inset-topbar'\);\n\s*if \(old\) old\.hidden = true;/);
  assert.match(readFileSync(new URL('../../homebase/static/apple/desk.css', import.meta.url), 'utf8'), /html\.hb-apple \.inset-topbar \{ display: none; \}/);
});
