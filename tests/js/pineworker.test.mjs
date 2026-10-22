import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { loadWorker, runtimeUmd, readTvCsv, inferTfS, compare } from '../../tools/pine/parity.mjs';

/* The Pine Worker runs in a bare vm the way the page hosts it (loadWorker shims importScripts / postMessage).
   The runtime lives outside the repo (AGPL): these tests skip where it is not installed. */
let UMD = null;
try { UMD = runtimeUmd(); } catch { UMD = null; }
const skip = UMD && existsSync(UMD) ? false : 'the Pine runtime is not installed (~/.homebase/pine/runtime)';

let seed = 7;
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const T0 = Date.UTC(2026, 9, 19, 13, 30);          // Mon 09:30 ET, 5-minute bars
function bars(n, fp = false) {
  const out = [];
  let px = 20000;
  for (let i = 0; i < n; i++) {
    const o = px, c = Math.round((o + (rnd() - 0.5) * 20) * 4) / 4;
    const h = Math.max(o, c) + 2, l = Math.min(o, c) - 2, v = 500 + Math.round(rnd() * 100);
    const b = { ms: T0 + i * 300000, o, h, l, c, v };
    if (fp) b.fp = [[l, 100 + i, 50], [h, 20, 180 + i]];     // [price, sells, buys]
    out.push(b);
    px = c;
  }
  return out;
}
const init = (source, b, extra = {}) => ({ type: 'init', source, root: 'NQ', tf_s: 300, tick_size: 0.25, point_value: 20, bars: b, ...extra });

function rsi(closes, len) {   // Wilder: SMA seed, then rma; na before len changes
  const out = new Array(closes.length).fill(null);
  let up = 0, dn = 0;
  for (let i = 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1], u = Math.max(d, 0), v = Math.max(-d, 0);
    if (i <= len) { up += u / len; dn += v / len; } else { up = (up * (len - 1) + u) / len; dn = (dn * (len - 1) + v) / len; }
    if (i >= len) out[i] = dn === 0 ? 100 : up === 0 ? 0 : 100 - 100 / (1 + up / dn);
  }
  return out;
}

const RSI = '//@version=6\nindicator("RSI twin", overlay=false)\nlen = input.int(14, "Length", minval=1)\nplot(ta.rsi(close, len), "rsi")\n';

test('a ta.rsi plot comes back for every bar and matches an independent RSI', { skip }, async () => {
  const w = loadWorker(UMD);
  const b = bars(300);
  w.post(init(RSI, b));
  const r = await w.next();
  assert.equal(r.type, 'result', r.message);
  assert.equal(r.full, true);
  assert.equal(r.kind, 'indicator');
  assert.equal(r.title, 'RSI twin');
  assert.equal(r.overlay, false);
  assert.equal(r.firstMs, T0);
  assert.deepEqual(r.inputsMeta.map((m) => [m.title || m.name, m.type, m.defval]), [['Length', 'int', 14]]);
  const got = r.plots.rsi;
  assert.equal(got.length, 300);
  assert.deepEqual(got.map((p) => p.time), b.map((x) => x.ms));
  const ref = rsi(b.map((x) => x.c), 14);
  for (let i = 0; i < 300; i++) {
    if (i < 14) assert.equal(got[i].value, null, 'bar ' + i + ' is na');
    else assert.ok(Math.abs(got[i].value - ref[i]) < 1e-9, 'bar ' + i + ': ' + got[i].value + ' vs ' + ref[i]);
  }
  assert.equal(r.plotsMeta.rsi.style, undefined);   // a plain plot() carries no style: a line
  assert.deepEqual(r.warnings, []);
  assert.equal(r.strategy, null);
});

test('an input override reaches the script', { skip }, async () => {
  const w = loadWorker(UMD);
  const b = bars(120);
  w.post(init(RSI, b, { inputs: { Length: 5 } }));
  const r = await w.next();
  assert.equal(r.type, 'result', r.message);
  const ref = rsi(b.map((x) => x.c), 5);
  assert.ok(Math.abs(r.plots.rsi[119].value - ref[119]) < 1e-9);
  assert.equal(r.plots.rsi[4].value, null);
});

test('request.footprint: a warning and na without fp, the bar delta with fp', { skip }, async () => {
  const src = '//@version=6\nindicator("fp")\nfp = request.footprint(1)\nplot(not na(fp) ? fp.delta() : na, "delta")\n';
  let w = loadWorker(UMD);
  w.post(init(src, bars(60)));
  let r = await w.next();
  assert.equal(r.type, 'result', r.message);
  assert.ok(r.plots.delta.every((p) => p.value === null));
  assert.ok(r.warnings.some((s) => /footprint/.test(s)), r.warnings.join(' | '));
  w = loadWorker(UMD);
  const b = bars(60, true);
  w.post(init(src, b));
  r = await w.next();
  assert.equal(r.type, 'result', r.message);
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(r.plots.delta.map((p) => p.value), b.map((x, i) => (50 + 180 + i) - (100 + i + 20)));
});

test('shapes, drawings, a strategy and another symbol\'s request.security', { skip }, async () => {
  const src = `//@version=6
strategy("s", overlay=true, margin_long=0, margin_short=0)
f = ta.ema(close, 5)
s = ta.ema(close, 20)
plot(f, "fast", color = f > s ? color.green : color.red)
plotshape(ta.crossover(f, s), "xup", shape.triangleup, location.belowbar, color=color.lime)
bgcolor(f > s ? color.new(color.green, 90) : na, title="bg")
es = request.security("ES1!", "5", close)
plot(es, "es")
h = request.security(syminfo.tickerid, "15", close)
plot(h, "htf")
if bar_index % 100 == 0
    box.new(bar_index, high, bar_index + 5, low)
    label.new(bar_index, high, "L")
if ta.crossover(f, s)
    strategy.entry("L", strategy.long)
if ta.crossunder(f, s)
    strategy.close("L")
`;
  const w = loadWorker(UMD);
  const b = bars(300);
  w.post(init(src, b));
  const r = await w.next();
  assert.equal(r.type, 'result', r.message);
  assert.equal(r.kind, 'strategy');
  assert.equal(r.overlay, true);
  assert.ok(r.plots.fast.some((p) => p.color === '#089981' || p.color === '#F23645'), 'per-bar colours ride on the points');
  assert.ok(r.shapes.length > 0 && r.shapes.every((s) => s.title === 'xup' && s.location === 'BelowBar'));
  assert.equal(r.plotsMeta.bg.style, 'background');
  assert.ok(r.plots.es.every((p) => p.value === null));
  assert.ok(r.warnings.some((s) => /ES1!/.test(s)), r.warnings.join(' | '));
  // 15-minute bars from the chart's own 5-minute bars (anchored at the session open, so bars 0-2, 3-5, ...):
  // a 15m close shows from the chart bar that closes it until the next one closes
  const htf = r.plots.htf.map((p) => p.value);
  assert.equal(htf[1], null);
  assert.equal(htf[2], b[2].c);
  assert.equal(htf[4], b[2].c);
  assert.equal(htf[5], b[5].c);
  assert.equal(htf[7], b[5].c);
  assert.equal(r.boxes.length, 3);
  assert.equal(r.labels.length, 3);
  assert.deepEqual(r.boxes.map((x) => [x.left, x.right]), [[0, 5], [100, 105], [200, 205]]);
  assert.ok(!('_deleted' in r.boxes[0]));
  assert.ok(r.strategy.closedtrades.length > 0);
  assert.ok(r.strategy.closedtrades.every((t) => t.entry_time && t.exit_time && !('_bracket_entry' in t)));
});

test('a compile error and a bad init answer with an error message', { skip }, async () => {
  const w = loadWorker(UMD);
  w.post(init('//@version=6\nindicator("b")\nplot(ta.rsi(close, )\n', bars(30)));
  const r = await w.next();
  assert.equal(r.type, 'error');
  assert.match(r.message, /transpile|Unexpected/);
  w.post({ type: 'init', source: RSI, root: 'NQ', tf_s: 0, tick_size: 0.25, point_value: 20, bars: bars(30) });
  assert.match((await w.next()).message, /time bars/);
});

test('bars after the last one run incrementally; a changed older bar is a full re-run', { skip }, async () => {
  const w = loadWorker(UMD);
  const all = bars(302);
  w.post(init(RSI, all.slice(0, 300)));
  assert.equal((await w.next()).full, true);
  w.post({ type: 'bars', bars: all.slice(300) });
  const r = await w.next();
  assert.equal(r.type, 'result', r.message);
  assert.equal(r.full, false);
  const ref = rsi(all.map((x) => x.c), 14);
  assert.deepEqual(r.plots.rsi.map((p) => p.time), [all[300].ms, all[301].ms]);
  assert.ok(Math.abs(r.plots.rsi[1].value - ref[301]) < 1e-9);
  const forming = { ...all[301], c: all[301].c + 3 };          // the last bar re-sent: re-executed, one point back
  w.post({ type: 'bars', bars: [forming] });
  const r1 = await w.next();
  assert.equal(r1.full, false);
  assert.deepEqual(r1.plots.rsi.map((p) => p.time), [forming.ms]);
  assert.ok(Math.abs(r1.plots.rsi[0].value - rsi(all.slice(0, 301).concat(forming).map((x) => x.c), 14)[301]) < 1e-9);
  const changed = { ...all[290], c: all[290].c + 10 };
  w.post({ type: 'bars', bars: [changed] });
  const r2 = await w.next();
  assert.equal(r2.full, true);
  assert.equal(r2.plots.rsi.length, 302);
  const ref2 = rsi(all.map((x, i) => (i === 290 ? changed.c : i === 301 ? forming.c : x.c)), 14);
  assert.ok(Math.abs(r2.plots.rsi[301].value - ref2[301]) < 1e-9);
});

test('parity helpers: the TradingView CSV reader, the timeframe guess and the comparison', () => {
  const csv = '﻿time,open,high,low,close,Volume,RSI\n1792416600,1,2,0.5,1.5,10,NaN\n1792416900,1,2,0.5,1.6,11,55.5\n"1792417200",1,2,0.5,1.7,,56\n';
  const tv = readTvCsv(csv);
  assert.deepEqual(tv.titles, ['RSI']);
  assert.deepEqual(tv.rows.map((r) => [r.time, r.c, r.v, r.plots.RSI]),
    [[1792416600000, 1.5, 10, null], [1792416900000, 1.6, 11, 55.5], [1792417200000, 1.7, null, 56]]);
  assert.equal(inferTfS(tv.rows.map((r) => r.time)), 300);
  assert.equal(readTvCsv('time,close\n2026-10-19T13:30:00Z,1\n').rows[0].time, Date.UTC(2026, 9, 19, 13, 30));
  const expected = new Map(tv.rows.map((r) => [r.time, r.plots.RSI]));
  const ok = compare(expected, new Map([[1792416900000, 55.5], [1792417200000, 56 + 1e-9]]), { tol: 1e-6 });
  assert.deepEqual([ok.n, ok.ok, ok.first], [2, true, null]);
  const bad = compare(expected, new Map([[1792416900000, 55.5], [1792417200000, 57]]), { tol: 1e-6 });
  assert.deepEqual([bad.n, bad.ok, bad.first], [2, false, { time: 1792417200000, tv: 56, hb: 57 }]);
  assert.equal(compare(expected, new Map(), { warmup: 0 }).n, 0);
});
