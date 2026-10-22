#!/usr/bin/env node
/* Pine parity: run a .pine script through the chart page's own Pine Worker (homebase/static/charts/pineworker.js,
   PineTS from ~/.homebase/pine/runtime) and line its plots up against a TradingView "Export chart data" CSV.

     node tools/pine/parity.mjs <script.pine> <tv.csv> [--root NQ] [--tol 1e-6] [--warmup N] [--bars homebase[=PATH]]

   The CSV: a header row with `time` (unix seconds, unix ms or ISO), open/high/low/close, `Volume` when the
   Volume indicator was on the chart, then one column per plot title. By default the bars are built from the
   CSV's own OHLCV, so a difference is the engine's, not the data's. `--bars homebase` runs the same script on
   Homebase bars instead: a JSON file [{ms, o, h, l, c, v}] (ms = the bar's epoch start) written by the Python
   harness, at PATH or <tv.csv minus .csv>.bars.json; a difference there is in the data.
   Prints one line per plot column: bars compared, largest absolute error, the first bar that differs. Warm-up
   bars and cells TradingView left empty are skipped. Exit 1 on a mismatch, 2 when the run itself failed.

   The runtime stays outside the repo (AGPL): HOMEBASE_PINE_DIR or ~/.homebase/pine. loadWorker() is also what
   tests/js/pineworker.test.mjs drives the Worker with. */
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

export const PINE_DIR = process.env.HOMEBASE_PINE_DIR || path.join(homedir(), '.homebase', 'pine');
export const WORKER_JS = fileURLToPath(new URL('../../homebase/static/charts/pineworker.js', import.meta.url));
const CONTRACT = { NQ: [0.25, 20], ES: [0.25, 50], RTY: [0.1, 50], YM: [1, 5], GC: [0.1, 100], SI: [0.005, 5000] };
const OHLCV = { time: 'time', open: 'o', high: 'h', low: 'l', close: 'c', volume: 'v' };

export function runtimeUmd() {   // the pinned browser build, resolved through the runtime's own npm tree
  const req = createRequire(path.join(PINE_DIR, 'runtime', 'package.json'));
  return path.join(path.dirname(req.resolve('pinets')), 'pinets.min.browser.js');   // next to the cjs build in dist/
}

/* The Worker in a bare vm context, as the page would host it: importScripts loads the runtime, postMessage
   lands in a queue. Timers are unref'd so a finished process exits while the stream still polls. */
export function loadWorker(umd = runtimeUmd(), worker = WORKER_JS) {
  const runtime = readFileSync(umd, 'utf8');
  const queue = [], waiters = [];
  const timer = (fn) => (cb, ms, ...a) => { const t = fn(cb, ms, ...a); if (t && t.unref) t.unref(); return t; };
  const box = { console, Intl, Date, Math, performance, structuredClone, queueMicrotask,
                setTimeout: timer(setTimeout), setInterval: timer(setInterval), clearTimeout, clearInterval,
                importScripts() { vm.runInContext(runtime, box, { filename: 'pinets.min.browser.js' }); },
                postMessage(m) { m = structuredClone(m); const w = waiters.shift(); if (w) w(m); else queue.push(m); } };
  box.self = box; box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(readFileSync(worker, 'utf8'), box, { filename: 'pineworker.js' });
  return {
    post(m) { box.onmessage({ data: m }); },
    next(timeoutMs = 60000) {
      return new Promise((res, rej) => {
        if (queue.length) return res(queue.shift());
        const t = setTimeout(() => rej(new Error('the Worker sent nothing in ' + timeoutMs + ' ms')), timeoutMs);
        waiters.push((m) => { clearTimeout(t); res(m); });
      });
    },
  };
}

function splitCsv(line) {
  const out = [];
  let cur = '', q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (q) { if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { out.push(cur); cur = ''; }
    else cur += ch;
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

function parseTime(s) {
  if (/^\d+(\.\d+)?$/.test(s)) { const n = +s; return n > 1e11 ? Math.round(n) : Math.round(n * 1000); }
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : null;
}

const num = (s) => { const v = s === '' || /^nan$/i.test(s) ? NaN : +s; return Number.isFinite(v) ? v : null; };

export function readTvCsv(text) {   // -> {rows: [{time, o, h, l, c, v, plots: {title: value|null}}], titles: [...]}
  const lines = text.replace(/^﻿/, '').split(/\r?\n/).filter((l) => l.trim());
  const head = splitCsv(lines[0]);
  const col = head.map((h) => OHLCV[h.toLowerCase()] || null);
  if (!col.includes('time')) throw new Error('the CSV has no time column');
  const titles = head.filter((h, i) => !col[i]);
  const rows = [];
  for (const line of lines.slice(1)) {
    const f = splitCsv(line), r = { plots: {} };
    head.forEach((h, i) => { if (col[i] === 'time') r.time = parseTime(f[i]); else if (col[i]) r[col[i]] = num(f[i]); else r.plots[h] = num(f[i]); });
    if (r.time != null) rows.push(r);
  }
  rows.sort((a, b) => a.time - b.time);
  return { rows, titles };
}

export function inferTfS(times) {   // the most common step between bars, in seconds
  const count = new Map();
  for (let i = 1; i < times.length; i++) { const d = times[i] - times[i - 1]; if (d > 0) count.set(d, (count.get(d) || 0) + 1); }
  let best = 0, n = 0;
  for (const [d, c] of count) if (c > n) { best = d; n = c; }
  return Math.round(best / 1000);
}

export function compare(expected, got, { tol = 1e-6, warmup = 0 } = {}) {
  // expected / got: Map time -> value|null. -> {n, maxErr, first: {time, tv, hb} | null, ok}
  let n = 0, maxErr = 0, first = null, i = 0;
  for (const [time, tv] of expected) {
    if (i++ < warmup || tv == null || !got.has(time)) continue;
    const hb = got.get(time);
    const err = hb == null ? Infinity : Math.abs(hb - tv);
    n++;
    if (err > maxErr) maxErr = err;
    if (err > tol && !first) first = { time, tv, hb };
  }
  return { n, maxErr, first, ok: !first };
}

function args(argv) {
  const a = { tol: 1e-6, warmup: 0, root: 'NQ', bars: null, pos: [] };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--tol') a.tol = +argv[++i];
    else if (k === '--warmup') a.warmup = +argv[++i];
    else if (k === '--root') a.root = String(argv[++i]).toUpperCase();
    else if (k === '--bars') a.bars = argv[++i];
    else a.pos.push(k);
  }
  return a;
}

async function main() {
  const a = args(process.argv.slice(2));
  if (a.pos.length !== 2) {
    console.error('usage: node tools/pine/parity.mjs <script.pine> <tv.csv> [--root NQ] [--tol 1e-6] [--warmup N] [--bars homebase[=PATH]]');
    return 2;
  }
  const [script, csv] = a.pos;
  const ct = CONTRACT[a.root];
  if (!ct) { console.error('unknown root ' + a.root); return 2; }
  const tv = readTvCsv(readFileSync(csv, 'utf8'));
  let bars;
  if (a.bars) {
    const m = /^homebase(?:=(.+))?$/.exec(a.bars);
    if (!m) { console.error('--bars takes homebase or homebase=PATH'); return 2; }
    const p = m[1] || csv.replace(/\.csv$/i, '') + '.bars.json';
    bars = JSON.parse(readFileSync(p, 'utf8')).map((b) => ({ ms: b.ms, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0 }));
    console.log('bars: Homebase, ' + bars.length + ' from ' + p);
  } else {
    bars = tv.rows.filter((r) => r.o != null && r.h != null && r.l != null && r.c != null)
      .map((r) => ({ ms: r.time, o: r.o, h: r.h, l: r.l, c: r.c, v: r.v || 0 }));
    console.log('bars: the CSV\'s own OHLCV, ' + bars.length + (tv.rows.some((r) => r.v != null) ? '' : ' (no Volume column: volume = 0)'));
  }
  if (bars.length < 2) { console.error('not enough bars'); return 2; }
  const tf_s = inferTfS(bars.map((b) => b.ms));
  console.log('timeframe: ' + tf_s + ' s, root ' + a.root + ', tol ' + a.tol + ', warmup ' + a.warmup);
  const w = loadWorker();
  w.post({ type: 'init', source: readFileSync(script, 'utf8'), root: a.root, tf_s, tick_size: ct[0], point_value: ct[1], bars, maxBars: 20000 });
  const r = await w.next();
  if (r.type !== 'result') { console.error('run failed: ' + r.message); return 2; }
  for (const s of r.warnings) console.log('warning: ' + s);
  const byTitle = new Map(Object.keys(r.plots).map((t) => [t.toLowerCase(), t]));
  let bad = false;
  for (const title of tv.titles) {
    const hb = byTitle.get(title.toLowerCase());
    const name = title.padEnd(24);
    if (!hb) { console.log(name + ' no such plot in the script (plots: ' + Object.keys(r.plots).join(', ') + ')'); continue; }
    const expected = new Map(tv.rows.map((row) => [row.time, row.plots[title]]));
    const got = new Map(r.plots[hb].map((p) => [p.time, p.value]));
    const c = compare(expected, got, a);
    const line = name + ' bars ' + String(c.n).padStart(6) + '  max abs err ' + c.maxErr.toExponential(2);
    if (c.ok) console.log(line + '  OK');
    else { bad = true; console.log(line + '  FIRST DIFF ' + new Date(c.first.time).toISOString() + ' tv=' + c.first.tv + ' hb=' + c.first.hb); }
  }
  return bad ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => process.exit(code), (e) => { console.error(e.stack || e); process.exit(2); });
}
