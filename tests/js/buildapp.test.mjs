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

function run(args, running, { installed = false, late = false } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'hb-buildapp-')), bin = join(dir, 'bin'), home = join(dir, 'home');
  const app = join(home, 'Applications', 'HOMEBASE VPS.app');
  spawnSync('mkdir', ['-p', bin, home, ...(installed ? [app] : [])]);
  if (installed) writeFileSync(join(app, 'mark'), '');
  // "running" from the start, or (late) only once the build has compiled
  writeFileSync(join(bin, 'pgrep'), `#!/bin/sh\n[ "$1" = -x ] && [ "$2" = "$FAKE_RUNNING" ] && { [ -z "$FAKE_LATE" ] || [ -e "${join(dir, 'compiled')}" ]; }\n`);
  // without late the compiler stops the script (exit 9); with it, it "compiles" and the script goes on to install
  writeFileSync(join(bin, 'swiftc'), `#!/bin/sh\ntouch "${join(dir, 'compiled')}"\n[ -n "$FAKE_LATE" ] || exit 9\n` +
    'while [ $# -gt 0 ]; do [ "$1" = -o ] && touch "$2"; shift; done\n');
  writeFileSync(join(bin, 'codesign'), '#!/bin/sh\n');
  writeFileSync(join(bin, 'swift'), '#!/bin/sh\n');
  for (const f of ['pgrep', 'swiftc', 'codesign', 'swift']) chmodSync(join(bin, f), 0o755);
  const r = spawnSync('bash', [SCRIPT, ...args.map((a) => a.replace('$HOME', home))], { encoding: 'utf8', cwd: home,
    env: { ...process.env, HOME: home, TMPDIR: dir, PATH: `${bin}:${process.env.PATH}`, FAKE_RUNNING: running, FAKE_LATE: late ? '1' : '' } });
  return { code: r.status, err: r.stderr, compiled: existsSync(join(dir, 'compiled')), installed: existsSync(join(home, 'Applications')),
    kept: existsSync(join(app, 'mark')) };
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
  for (const [args, running] of [[['--vps'], 'Homebase'], [['--mac'], 'HomebaseVPS'], [['--vps', '--out', '$HOME/HB.app'], 'HomebaseVPS']]) {
    const r = run(args, running);
    assert.equal(r.compiled, true, `${args.join(' ')} with ${running} running: it reaches the build`);
    assert.equal(r.code, 9, 'the fake compiler stops it there');
  }
});

test('O: the installed app\'s path written another way (./, //, relative to HOME) is refused the same way', () => {
  for (const out of ['$HOME/Applications/./HOMEBASE VPS.app', '$HOME//Applications/HOMEBASE VPS.app', 'Applications/HOMEBASE VPS.app',
    '$HOME/Applications/../Applications/HOMEBASE VPS.app']) {
    for (const mode of ['--vps', '--mac']) {
      const r = run([mode, '--out', out], 'HomebaseVPS', { installed: true });
      assert.equal(r.code, 1, `${mode} --out ${out}`);
      assert.equal(r.err.trim(), 'HOMEBASE VPS is running: quit it first (nothing was changed).');
      assert.equal(r.compiled, false, `${mode} --out ${out}: it stops before the build`);
      assert.equal(r.kept, true);
    }
  }
});

test('O: this Mac\'s disk ignores case: the installed app\'s path in other case is the same app, refused the same way', (t) => {
  if (!existsSync(tmpdir().toUpperCase())) return t.skip('this disk minds case');
  for (const out of ['$HOME/Applications/homebase vps.app', '$HOME/applications/HOMEBASE VPS.app']) {
    for (const mode of ['--vps', '--mac']) {
      const r = run([mode, '--out', out], 'HomebaseVPS', { installed: true });
      assert.equal(r.code, 1, `${mode} --out ${out}`);
      assert.equal(r.err.trim(), 'HOMEBASE VPS is running: quit it first (nothing was changed).');
      assert.equal(r.compiled, false, `${mode} --out ${out}: it stops before the build`);
      assert.equal(r.kept, true);
    }
  }
});

test('O: an --out through a folder that does not exist yet (new/../) is refused, so it cannot reach the running app', () => {
  for (const mode of ['--vps', '--mac']) {
    const r = run([mode, '--out', '$HOME/Applications/nonexist/../HOMEBASE VPS.app'], 'HomebaseVPS', { installed: true });
    assert.equal(r.code, 2, mode);
    assert.equal(r.err.trim(), 'the --out folder does not exist: make it first (nothing was changed).');
    assert.equal(r.compiled, false, `${mode}: it stops before the build`);
    assert.equal(r.kept, true);
  }
});

test('O: an app started while the build runs is not replaced: the script checks again before it moves the app aside', () => {
  const r = run(['--vps'], 'HomebaseVPS', { installed: true, late: true });
  assert.equal(r.compiled, true, 'it got past the first check and built');
  assert.equal(r.code, 1);
  assert.equal(r.err.trim(), 'HOMEBASE VPS is running: quit it first (nothing was changed).');
  assert.equal(r.kept, true, 'the installed app is where it was');
  const ok = run(['--vps'], 'Homebase', { installed: true, late: true });      // the other app running: it installs
  assert.equal(ok.code, 0, ok.err);
  assert.equal(ok.kept, false, 'the new build replaced the old one');
});
