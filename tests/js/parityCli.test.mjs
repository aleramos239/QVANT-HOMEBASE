import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readTvCsv, runtimeUmd } from '../../tools/pine/parity.mjs';

/* tools/pine/parity.mjs as a command line: the exit code is the verdict (0 parity, 1 a mismatch, 2 the run itself failed
   or compared nothing). Runs that reach the Pine Worker skip where the runtime (outside the repo, AGPL) is not installed. */
const CLI = fileURLToPath(new URL('../../tools/pine/parity.mjs', import.meta.url));
let UMD = null;
try { UMD = runtimeUmd(); } catch { UMD = null; }
const noRuntime = UMD && existsSync(UMD) ? false : 'the Pine runtime is not installed (~/.homebase/pine/runtime)';

const dir = mkdtempSync(path.join(tmpdir(), 'parity-cli-'));
const T0 = 1760880600;                                   // 2025-10-19 13:30Z, 5-minute bars
const rows = (n) => Array.from({ length: n }, (_, i) => ({ t: T0 + i * 300, c: 100 + i }));
function csv(name, extraTitle, cell) {
  const head = ['time', 'open', 'high', 'low', 'close', ...(extraTitle ? [extraTitle] : [])].join(',');
  const body = rows(30).map((r, i) => [r.t, r.c, r.c + 1, r.c - 1, r.c, ...(extraTitle ? [cell(r, i)] : [])].join(','));
  const p = path.join(dir, name);
  writeFileSync(p, [head, ...body].join('\n') + '\n');
  return p;
}
const pine = path.join(dir, 's.pine');
writeFileSync(pine, '//@version=6\nindicator("s")\nplot(close, "Closing")\n');
const run = (...a) => spawnSync(process.execPath, [CLI, ...a], { encoding: 'utf8', env: { ...process.env, NODE_OPTIONS: '' } });
const same = (r) => r.c;
const base = () => readFileSync(csv('ok.csv', 'Closing', same), 'utf8');

test('a --tol that is not a number is refused, not read as NaN (which passes every cell)', () => {
  const t = csv('tol.csv', 'Closing', (r) => r.c + 1);          // off by 1 on every bar
  for (const bad of [['--tol', '1e-6x'], ['--tol', 'abc'], ['--tol', '-1'], ['--tol', '0x10'], ['--tol=abc'], ['--tol='],
                     ['--warmup', 'abc'], ['--warmup', '1.5'], ['--warmup', '-2'], ['--warmup', '0x10'], ['--warmup=0b11']]) {
    const r = run(pine, t, ...bad);
    assert.equal(r.status, 2, bad.join(' ') + '\n' + r.stdout + r.stderr);
    assert.match(r.stderr, /--(tol|warmup) must be/, bad.join(' '));         // the flag was read, not left for the usage line
  }
});

test('--flag=value reads like --flag value', { skip: noRuntime }, () => {
  const t = csv('eq.csv', 'Closing', (r) => r.c + 1);           // off by 1 on every bar
  assert.equal(run(pine, t, '--tol=1').status, 0);
  assert.equal(run(pine, t, '--tol', '1').status, 0);
  assert.equal(run(pine, t, '--tol=0.5').status, 1);
  assert.match(run(pine, t, '--warmup=2').stdout, /warmup 2/);
  assert.match(run(pine, t, '--root=NQ', '--tol=1').stdout, /root NQ/);
});

test('a value flag with no value is refused', () => {
  const t = csv('novalue.csv', 'Closing', same);
  for (const flag of ['--tol', '--warmup', '--root', '--bars']) {
    const r = run(pine, t, flag);
    assert.equal(r.status, 2, flag + '\n' + r.stdout + r.stderr);
    assert.match(r.stderr, new RegExp(flag));
  }
});

test('a time without a zone is UTC, as tools/tvparity reads it, whatever the machine zone', () => {
  const code = `import { readTvCsv } from ${JSON.stringify(new URL('../../tools/pine/parity.mjs', import.meta.url).href)};
    const r = readTvCsv('time,open,high,low,close\\n2025-10-08T22:00:00,1,2,0,1\\n2025-10-08T22:00:00Z,1,2,0,1\\n2025-10-08T18:00:00-04:00,1,2,0,1\\n2025-10-08 22:00:00 UTC,1,2,0,1\\n10/08/2025 22:00,1,2,0,1\\n2025-10-09T03:00:00+05,1,2,0,1\\n2025-10-08 18:00:00-04,1,2,0,1\\n2025-10-08T18:00-04,1,2,0,1\\n');
    console.log(JSON.stringify(r.rows.map((x) => x.time)));`;
  for (const tz of ['America/Chicago', 'UTC', 'Asia/Tokyo']) {
    const r = spawnSync(process.execPath, ['--input-type=module', '-e', code], { encoding: 'utf8', env: { ...process.env, TZ: tz } });
    assert.equal(r.status, 0, tz + r.stderr);
    assert.deepEqual(JSON.parse(r.stdout), Array(8).fill(1759960800000), tz);
  }
});

test('a column that matches the script and agrees exits 0, and a title of another indicator on the chart is only printed', { skip: noRuntime }, () => {
  const t = csv('ok.csv', 'Closing', same);
  const r = run(pine, t);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /Closing\s+bars\s+30\s+max abs err 0\.00e\+0\s+OK/);
  const two = path.join(dir, 'two.csv');
  const lines = base().split('\n').filter(Boolean);
  writeFileSync(two, lines.map((l, i) => l + ',' + (i === 0 ? 'tv|ema:20|' : '5')).join('\n') + '\n');
  const r2 = run(pine, two);
  assert.equal(r2.status, 0, r2.stdout + r2.stderr);
  assert.match(r2.stdout, /tv\|ema:20\|\s+no such plot in the script/);
});

test('a mismatch exits 1', { skip: noRuntime }, () => {
  const r = run(pine, csv('diff.csv', 'Closing', (x) => x.c + 1));
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stdout, /FIRST DIFF/);
});

test('nothing compared is not a pass: no title in common, no plot columns, all-empty cells', { skip: noRuntime }, () => {
  for (const [name, title, cell] of [['none1.csv', 'tv|ema:20|', same], ['none2.csv', null, null], ['none3.csv', 'Closing', () => '']]) {
    const r = run(pine, csv(name, title, cell));
    assert.equal(r.status, 2, name + '\n' + r.stdout + r.stderr);
    assert.match(r.stdout + r.stderr, /compared|NOTHING/i, name);
  }
});

test('a column with no aligned cell reads NOTHING COMPARED, not OK, beside a column that did compare', { skip: noRuntime }, () => {
  const pine2 = path.join(dir, 's2.pine');
  writeFileSync(pine2, '//@version=6\nindicator("s2")\nplot(close, "Closing")\nplot(open, "Other")\n');
  const two = path.join(dir, 'half.csv');
  const lines = base().split('\n').filter(Boolean);
  writeFileSync(two, lines.map((l, i) => l + ',' + (i === 0 ? 'Other' : '')).join('\n') + '\n');   // Other: every cell empty
  const r = run(pine2, two);
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stdout, /Closing\s+bars\s+30.*OK/);
  assert.match(r.stdout, /Other\s+NOTHING COMPARED/);
});

test('--bars homebase reads the {ms,o,h,l,c,v} file that tools.tvparity run files next to the export', { skip: noRuntime }, () => {
  const t = csv('hb.csv', 'Closing', same);
  const bars = (shift) => JSON.stringify(rows(30).map((r) => ({ ms: r.t * 1000, o: r.c, h: r.c + 1, l: r.c - 1, c: r.c + shift, v: 5 })));
  writeFileSync(path.join(dir, 'hb.bars.json'), bars(0));                  // the default place: <csv minus .csv>.bars.json
  const ok = run(pine, t, '--bars', 'homebase');
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
  assert.match(ok.stdout, /bars: Homebase, 30 from .*hb\.bars\.json/);
  writeFileSync(path.join(dir, 'other.json'), bars(1));                    // Homebase's data differs from TradingView's
  const bad = run(pine, t, '--bars', 'homebase=' + path.join(dir, 'other.json'));
  assert.equal(bad.status, 1, bad.stdout + bad.stderr);
  assert.match(bad.stdout, /FIRST DIFF/);
});

test('layout B: with no Volume column the bar volume is the tv|vol| plot, which is still compared as a plot', () => {
  const layoutB = 'time,open,high,low,close,tv|probe|P2,tv|vol|\n1760880600,1,2,0,1,1,40\n1760880900,1,2,0,1,1,\n';
  const b = readTvCsv(layoutB);
  assert.deepEqual(b.rows.map((r) => r.v), [40, null]);
  assert.deepEqual(b.titles, ['tv|probe|P2', 'tv|vol|']);
  assert.deepEqual(b.rows.map((r) => r.plots['tv|vol|']), [40, null]);
  // a Volume column wins, as in tools/tvparity.load_tv_csv
  assert.deepEqual(readTvCsv(layoutB.replace('time,', 'time,Volume,').replace(/\n(\d+),/g, '\n$1,7,')).rows.map((r) => r.v), [7, 7]);
  assert.equal(readTvCsv('time,open,high,low,close\n1760880600,1,2,0,1\n').rows[0].v, undefined);
});

test('layout B: a script that plots volume and ta.vwap agrees with an export that has tv|vol| and no Volume column (exit 0)', { skip: noRuntime }, () => {
  const vol = (i) => 10 + (i * 7) % 13;
  const lines = ['time,open,high,low,close,tv|probe|P2,tv|vol|,tv|vwap|vwap'];
  let pv = 0, v = 0;
  rows(30).forEach((r, i) => {
    pv += (r.c + 1 + r.c - 1 + r.c) / 3 * vol(i); v += vol(i);
    lines.push([r.t, r.c, r.c + 1, r.c - 1, r.c, 1, vol(i), pv / v].join(','));
  });
  const b = path.join(dir, 'layoutB.csv');
  writeFileSync(b, lines.join('\n') + '\n');
  const vp = path.join(dir, 'v.pine');
  writeFileSync(vp, '//@version=6\nindicator("v")\nplot(volume, "tv|vol|")\nplot(ta.vwap(hlc3), "tv|vwap|vwap")\n');
  const r = run(vp, b);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.doesNotMatch(r.stdout, /no Volume column/);
  assert.match(r.stdout, /tv\|vol\|\s+bars\s+30\s+max abs err 0\.00e\+0\s+OK/);
  assert.match(r.stdout, /tv\|vwap\|vwap\s+bars\s+30\s+max abs err \d\.\d\de-\d+\s+OK/);
  // and with neither a Volume column nor tv|vol| the note stays: the script ran on volume 0
  assert.match(run(pine, csv('novol.csv', 'Closing', same)).stdout, /no Volume column: volume = 0/);
});
