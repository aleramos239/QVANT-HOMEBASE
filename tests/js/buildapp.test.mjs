import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, chmodSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/* O: deploy/macapp/build_app_apple.sh refuses to replace an installed app while it runs: the Mac app (Homebase) and the VPS app
   (HomebaseVPS) alike. Run with a temp HOME, a fake pgrep (which app "runs" is the test's FAKE_RUNNING) and a fake swiftc that
   only leaves a mark: nothing is ever built or installed, and the real apps are never looked at. */
const SCRIPT = new URL('../../deploy/macapp/build_app_apple.sh', import.meta.url).pathname;

function run(args, running) {
  const dir = mkdtempSync(join(tmpdir(), 'hb-buildapp-')), bin = join(dir, 'bin'), home = join(dir, 'home');
  spawnSync('mkdir', ['-p', bin, home]);
  writeFileSync(join(bin, 'pgrep'), '#!/bin/sh\n[ "$1" = -x ] && [ "$2" = "$FAKE_RUNNING" ]\n');
  writeFileSync(join(bin, 'swiftc'), `#!/bin/sh\ntouch "${join(dir, 'compiled')}"\nexit 9\n`);
  for (const f of ['pgrep', 'swiftc']) chmodSync(join(bin, f), 0o755);
  const r = spawnSync('bash', [SCRIPT, ...args], { encoding: 'utf8',
    env: { ...process.env, HOME: home, TMPDIR: dir, PATH: `${bin}:${process.env.PATH}`, FAKE_RUNNING: running } });
  return { code: r.status, err: r.stderr, compiled: existsSync(join(dir, 'compiled')), installed: existsSync(join(home, 'Applications')) };
}

test('O: --vps refuses while HOMEBASE VPS runs, as --mac refuses while Homebase runs; nothing is built', () => {
  const vps = run(['--vps'], 'HomebaseVPS');
  assert.equal(vps.code, 1);
  assert.equal(vps.err.trim(), 'HOMEBASE VPS is running: quit it first (nothing was changed).');
  assert.equal(vps.compiled, false, 'it stops before the build');
  assert.equal(vps.installed, false);
  const mac = run(['--mac'], 'Homebase');
  assert.equal(mac.code, 1);
  assert.equal(mac.err.trim(), 'Homebase is running: quit it first (nothing was changed).');
  assert.equal(mac.compiled, false);
});

test('O: the other app running, or a test build elsewhere (--out), does not stop the build', () => {
  for (const [args, running] of [[['--vps'], 'Homebase'], [['--mac'], 'HomebaseVPS'], [['--vps', '--out', '/tmp/hb-o-test/HB.app'], 'HomebaseVPS']]) {
    const r = run(args, running);
    assert.equal(r.compiled, true, `${args.join(' ')} with ${running} running: it reaches the build`);
    assert.equal(r.code, 9, 'the fake compiler stops it there');
  }
});
