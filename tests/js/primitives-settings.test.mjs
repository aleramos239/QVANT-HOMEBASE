import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/* Settings of the footprint, profile, Economic calendar and News headlines indicators (flowdefs.js `settings`):
   default byte identity against the files as they stood before (git HEAD while this change is uncommitted; once it is
   committed that baseline is the new code too, so the pinned literals below are what keeps the defaults honest), then each
   colour and each param, then missing / junk values. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
const root = fileURLToPath(new URL('../../', import.meta.url));
const dir = 'homebase/static/charts/';
require('../../homebase/static/charts/settings.js');
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/flowmath.js');
const C = globalThis.HBCatalog;
const N = require('../../homebase/static/charts/news.js');

/* primitives.js + events.js loaded into their own `window`, from the working tree or from git HEAD. */
function load(ref) {
  const win = Object.create(globalThis);
  const src = (f) => (ref === 'HEAD' ? execFileSync('git', ['show', `HEAD:${dir}${f}`], { cwd: root, encoding: 'utf8', maxBuffer: 1 << 26 }) : readFileSync(root + dir + f, 'utf8'));
  for (const f of ['events.js', 'primitives.js']) new Function('window', 'require', 'module', src(f))(win, require, undefined);
  return win;
}
const NEW = load('work'), OLD = load('HEAD');

const P = { up: '#UP', down: '#DOWN', text2: '#T2', poc: '#POC', va: '#VA', vaIn: '#VAIN', fpBg: '#BG', fpText: '#TX', bg: '#PBG' };
const SET = ['strokeStyle', 'fillStyle', 'lineWidth', 'font', 'textAlign', 'textBaseline', 'globalAlpha'];
function recorder() {
  const log = [], ctx = {};
  for (const m of ['beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'fillRect', 'strokeRect', 'closePath', 'fillText', 'setLineDash', 'arc']) ctx[m] = (...a) => { log.push([m, ...a]); };
  ctx.measureText = () => ({ width: 10 });
  for (const k of SET) Object.defineProperty(ctx, k, { set: (v) => { log.push([`set ${k}`, v]); }, get: () => undefined });
  const target = { useMediaCoordinateSpace: (cb) => cb({ context: ctx, mediaSize: { width: 800, height: 600 } }) };
  return { log, target };
}
const chart = { timeScale: () => ({ logicalToCoordinate: (i) => 100 * i + 50, getVisibleLogicalRange: () => ({ from: 0, to: 2 }), width: () => 800 }) };
const series = { priceToCoordinate: (px) => 1000 - px * 80 };      // 20 px per 0.25 tick
const TICK = 0.25;
const FP = [[100.0, 1, 0], [100.25, 1, 4], [100.5, 1, 4], [100.75, 1, 4], [101.0, 1, 4], [101.25, 9, 1], [101.5, 5, 1]];
const BARS = [{ c: 100.5, fp: FP, fpn: FP, d: 3 }, { c: 100.5, fp: FP, fpn: FP, d: -4 }, { c: 100.5, fp: FP, fpn: FP, d: 0 }];

function footprintLog(win, ex, ratio = 3) {
  const f = new win.HBLayers.Footprint(P), { log, target } = recorder();
  f.chart = chart; f.series = series; f.set(BARS, true, ratio, TICK, ex);
  f.draw(target);
  return log;
}
const FULL = { stack: 2, unfinished: true, deltaNum: true, rows: 1, vbars: true, poc: true };
const DEFAULTS = { fontMax: 11, fontMin: 8, barFill: 86, minBarPx: 56, minRowPx: 9, autoRowPx: 11, pocWidth: 1, stackWidth: 2, edgeWidth: 3, fontFamily: 'mono' };
const MODES = ['both', 'delta', 'total', 'dom', 'diag', 'trades', 'none'];

test('footprint defaults: every mode draws byte-identically to before, with no settings and with every default spelled out', () => {
  for (const mode of MODES) {
    const base = { ...FULL, text: mode === 'none' ? undefined : mode, numbers: mode === 'none' ? 'none' : undefined };
    const old = footprintLog(OLD, base);
    assert.ok(old.length > 50, mode);
    assert.deepEqual(footprintLog(NEW, base), old, `${mode} bare`);
    assert.deepEqual(footprintLog(NEW, { ...base, ...DEFAULTS, colors: {} }), old, `${mode} defaults`);
    assert.deepEqual(footprintLog(NEW, { ...base, colors: { buy: undefined, sell: undefined } }), old, `${mode} unstyled colours`);
  }
  const l = footprintLog(NEW, { ...FULL, text: 'both' });
  assert.ok(l.some((e) => e[0] === 'set font' && e[1] === '11px ui-monospace, SFMono-Regular, Menlo, monospace'));   // pinned literals
  assert.ok(l.some((e) => e[0] === 'set strokeStyle' && e[1] === '#POC') && l.some((e) => e[0] === 'set lineWidth' && e[1] === 2));
});

test('footprint: missing or junk settings fall back to today', () => {
  const old = footprintLog(OLD, { ...FULL, text: 'both' });
  const junk = { fontMax: 'big', fontMin: null, barFill: NaN, minBarPx: undefined, minRowPx: {}, autoRowPx: 'x', pocWidth: Infinity, stackWidth: '2', edgeWidth: [], fontFamily: 7, colors: null };
  assert.deepEqual(footprintLog(NEW, { ...FULL, text: 'both', ...junk }), old);
});

const has = (log, name, v) => log.some((e) => e[0] === name && e[1] === v);
const FULLB = { ...FULL, text: 'both' };

test('footprint colours: buy and sell drive imbalance numbers, the bracket and the edge tick; delta colours the delta modes and the number under the bar', () => {
  const colors = { buy: '#B1', sell: '#S1', deltaPos: '#DP', deltaNeg: '#DN', poc: '#PC' };
  const both = footprintLog(NEW, { ...FULLB, colors });
  assert.ok(has(both, 'set fillStyle', '#B1') && has(both, 'set fillStyle', '#S1'));            // imbalance numbers
  assert.ok(has(both, 'set strokeStyle', '#B1') && has(both, 'set strokeStyle', '#S1'));        // brackets
  assert.ok(has(both, 'set strokeStyle', '#PC') && !has(both, 'set strokeStyle', '#POC'));       // POC box
  assert.ok(has(both, 'set fillStyle', '#DP') && has(both, 'set fillStyle', '#DN'));             // delta under the bar
  assert.ok(!has(both, 'set fillStyle', '#UP') && !has(both, 'set fillStyle', '#DOWN'));
  const delta = footprintLog(NEW, { ...FULL, text: 'delta', colors });
  assert.ok(has(delta, 'set fillStyle', '#DP') && has(delta, 'set fillStyle', '#DN'));
  assert.ok(!has(delta, 'set fillStyle', '#B1'));                                                // delta mode is not an imbalance colour
  const dom = footprintLog(NEW, { ...FULL, text: 'dom', colors });
  assert.ok(has(dom, 'set fillStyle', '#DP') || has(dom, 'set fillStyle', '#DN'));
  const total = footprintLog(NEW, { ...FULL, text: 'total', colors });
  assert.ok(has(total, 'set fillStyle', '#B1'));
  const edge = footprintLog(NEW, { numbers: 'none', vbars: false, colors });
  assert.ok(has(edge, 'set fillStyle', '#B1'));
  assert.ok(!footprintLog(OLD, { ...FULLB, colors }).some((e) => e[1] === '#B1'));              // the old code ignores them
});

test('footprint params: font sizes and family, bar fill, widths', () => {
  const d = footprintLog(NEW, FULLB);
  assert.ok(has(footprintLog(NEW, { ...FULLB, fontMax: 9 }), 'set font', '9px ui-monospace, SFMono-Regular, Menlo, monospace'));
  assert.ok(has(footprintLog(NEW, { ...FULLB, fontMin: 6, fontMax: 6 }), 'set font', '6px ui-monospace, SFMono-Regular, Menlo, monospace'));
  assert.ok(has(footprintLog(NEW, { ...FULLB, fontFamily: 'sans' }), 'set font', '11px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif'));
  const wide = footprintLog(NEW, { ...FULLB, barFill: 100 }), vb = (l) => l.find((e) => e[0] === 'fillRect');
  assert.equal(vb(d)[1], 50 - 100 * 0.86 / 2);                                                  // x - w / 2 of the volume bar
  assert.equal(vb(wide)[1], 50 - 100 / 2);
  assert.ok(has(footprintLog(NEW, { ...FULLB, pocWidth: 3 }), 'set lineWidth', 3));
  assert.ok(has(footprintLog(NEW, { ...FULLB, stackWidth: 5 }), 'set lineWidth', 5));
  const e1 = footprintLog(NEW, { numbers: 'none', vbars: false, edgeWidth: 6 }).find((e) => e[0] === 'fillRect');
  assert.equal(e1[3], 6);
  assert.equal(footprintLog(OLD, { numbers: 'none', vbars: false }).find((e) => e[0] === 'fillRect')[3], 3);
  assert.notDeepEqual(wide, d);
});

test('footprint readable(): minBarPx, minRowPx and autoRowPx move the thresholds', () => {
  const fp = (win, ex) => { const f = new win.HBLayers.Footprint(P); f.chart = chart; f.series = series; f.set(BARS, true, 3, TICK, ex); return f; };
  assert.equal(fp(NEW, {}).readable(), true);                         // spacing is 100 px
  assert.equal(fp(NEW, { minBarPx: 101 }).readable(), false);
  assert.equal(fp(NEW, { minBarPx: 100 }).readable(), true);
  assert.equal(fp(OLD, { minBarPx: 101 }).readable(), true);          // the old code had no such setting
  assert.equal(fp(NEW, { rows: 1 }).readable(), true);                // a row is 20 px
  assert.equal(fp(NEW, { rows: 1, minRowPx: 21 }).readable(), false);
  assert.equal(fp(NEW, {}).rowTicks(), 1);                            // Auto: 20 px a tick, 11 px wanted -> 1 tick
  assert.equal(fp(NEW, { autoRowPx: 21 }).rowTicks(), 2);
  assert.equal(fp(NEW, { autoRowPx: 40 }).rowTicks(), 2);
  assert.equal(fp(NEW, { autoRowPx: 41 }).rowTicks(), 4);
  assert.equal(fp(OLD, { autoRowPx: 41 }).rowTicks(), 1);
});

/* ---- profile ---- */
const PROF = { poc: 100.5, vah: 101, val: 100, rows: [[100, 5], [100.25, 8], [100.5, 12], [100.75, 7], [101, 4], [101.25, 2]],
  prev: { poc: 100.25, vah: 100.75, val: 100, rows: [[100, 3], [100.25, 9], [100.5, 6], [100.75, 4], [101, 1]] } };
function profileLog(win, ex) {
  const p = new win.HBLayers.Profile(P), { log, target } = recorder();
  p.series = series; p.set(PROF, TICK, ex); p.draw(target);
  return log;
}
const PBASE = { prior: true, lines: true, naked: true, width: 18 };
const PDEF = { ghostOpacity: 45, lineWidth: 1, labels: true, fontSize: 10, highlightPoc: true, colors: {} };

test('profile defaults: identical to before, bare or with every default spelled out', () => {
  for (const extra of [{}, { naked: false }, { side: 'left' }, { prior: false }, { lines: false }]) {
    const ex = { ...PBASE, ...extra }, old = profileLog(OLD, ex);
    assert.ok(old.length > 20);
    assert.deepEqual(profileLog(NEW, ex), old);
    assert.deepEqual(profileLog(NEW, { ...ex, ...PDEF }), old);
  }
  const l = profileLog(NEW, PBASE);
  assert.ok(has(l, 'set globalAlpha', 0.45) && has(l, 'set font', '10px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif'));
  assert.ok(has(l, 'set fillStyle', '#VAIN') && has(l, 'set strokeStyle', '#T2') && has(l, 'set strokeStyle', '#POC'));
});

test('profile: junk settings fall back to today', () => {
  const old = profileLog(OLD, PBASE);
  assert.deepEqual(profileLog(NEW, { ...PBASE, ghostOpacity: 'x', lineWidth: NaN, fontSize: null, labels: undefined, highlightPoc: undefined, colors: null }), old);
});

test('profile colours: bars, value area, POC, ghost, prior lines and prior POC line', () => {
  const colors = { body: '#C-BODY', va: '#C-VA', poc: '#C-POC', ghost: '#C-GHOST', priorVaLines: '#C-VAL', priorPoc: '#C-PPOC' };
  const l = profileLog(NEW, { ...PBASE, colors });
  for (const k of ['#C-BODY', '#C-VA', '#C-POC', '#C-GHOST']) assert.ok(has(l, 'set fillStyle', k), k);
  assert.ok(has(l, 'set strokeStyle', '#C-VAL') && has(l, 'set strokeStyle', '#C-PPOC'));
  assert.ok(!has(l, 'set fillStyle', '#VA') && !has(l, 'set fillStyle', '#VAIN') && !has(l, 'set strokeStyle', '#T2'));
  const dashed = l.findIndex((e) => e[0] === 'setLineDash' && e[1].length === 2);
  assert.ok(has(l.slice(0, dashed), 'set strokeStyle', '#C-PPOC'));                              // the dashed line is the prior POC
});

test('profile params: ghost opacity, line width, labels, label size, POC highlight', () => {
  assert.ok(has(profileLog(NEW, { ...PBASE, ghostOpacity: 80 }), 'set globalAlpha', 0.8));
  assert.ok(has(profileLog(NEW, { ...PBASE, lineWidth: 3 }), 'set lineWidth', 3));
  assert.equal(profileLog(NEW, { ...PBASE, labels: false }).filter((e) => e[0] === 'fillText').length, 0);
  assert.equal(profileLog(NEW, PBASE).filter((e) => e[0] === 'fillText').length, 3);
  assert.ok(has(profileLog(NEW, { ...PBASE, fontSize: 13 }), 'set font', '13px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif'));
  const off = profileLog(NEW, { ...PBASE, lines: false, highlightPoc: false });
  assert.ok(!has(off, 'set fillStyle', '#POC'));
  assert.ok(has(profileLog(NEW, { ...PBASE, lines: false }), 'set fillStyle', '#POC'));
});

/* ---- Economic calendar ---- */
const EV = [{ t_ms: 1000, impact: 'High', country: 'USD', title: 'A' }, { t_ms: 2000, impact: 'Medium', country: 'USD', title: 'B' },
  { t_ms: 3000, impact: 'Low', country: 'USD', title: 'C' }, { t_ms: 4000, impact: 'Holiday', country: 'USD', title: 'D' }];
function flagLog(win, inst, extra = {}) {
  const f = new win.HBLayers.EventFlags(P, () => ({ events: EV, xOf: (t) => t / 10, lines: true, lineStyle: 'dotted', lineWidth: 1, from: null, to: null, inst, ...extra }));
  f.chart = chart; f.updateAllViews();
  const a = recorder(), b = recorder();
  f._views[0].renderer().draw(a.target); f._views[1].renderer().draw(b.target);
  return { lines: a.log, flags: b.log, layer: f };
}
const evInst = (params, style) => ({ id: 'events', visible: true, params, ...(style ? { style } : {}) });

test('calendar defaults: identical to before with no instance, a bare instance or every default spelled out', () => {
  const old = flagLog(OLD, undefined);
  assert.ok(old.flags.length > 8 && old.lines.length > 4);
  for (const inst of [undefined, evInst({}), evInst({ flagSize: 10, lineLow: false, showFlags: true }), evInst({ flagSize: 'x', showFlags: 3 })]) {
    const n = flagLog(NEW, inst);
    assert.deepEqual([n.lines, n.flags], [old.lines, old.flags]);
    assert.deepEqual(n.layer.flags.map((g) => [g.x, g.color, g.line]), old.layer.flags.map((g) => [g.x, g.color, g.line]));
  }
  assert.ok(has(old.flags, 'set fillStyle', '#F23645') && has(old.flags, 'set strokeStyle', '#PBG'));
});

test('calendar colours: each folder, the holiday colour and the outline', () => {
  const style = { high: { color: '#010101', alpha: 100 }, medium: { color: '#020202', alpha: 50 }, low: { color: '#030303' }, holiday: { color: '#040404' }, outline: { color: '#050505' } };
  const n = flagLog(NEW, evInst({ lineLow: true }, style));
  for (const k of ['#010101', 'rgba(2,2,2,0.5)', '#030303', '#040404']) assert.ok(has(n.flags, 'set fillStyle', k), k);
  assert.ok(has(n.flags, 'set strokeStyle', '#050505') && !has(n.flags, 'set strokeStyle', '#PBG'));
  assert.ok(has(n.lines, 'set strokeStyle', '#010101') && has(n.lines, 'set strokeStyle', 'rgba(2,2,2,0.5)'));
  assert.ok(!has(flagLog(OLD, evInst({}, style)).flags, 'set fillStyle', '#010101'));
});

test('calendar params: flag size (drawing, merging, hover), low-impact lines, flags on/off', () => {
  const arcs = (l) => l.filter((e) => e[0] === 'arc');
  assert.equal(arcs(flagLog(OLD, undefined).flags)[0][3], 5);
  assert.equal(arcs(flagLog(NEW, evInst({ flagSize: 16 })).flags)[0][3], 8);
  // with x = t / 100 the events are 10 px apart: a 50 px flag merges them all, a 10 px one none
  assert.equal(flagLog(NEW, evInst({ flagSize: 10 })).layer.flags.length, 4);
  assert.equal(flagLog(NEW, evInst({ flagSize: 50 }), { xOf: (t) => t / 100 }).layer.flags.length, 1);
  assert.equal(flagLog(NEW, evInst({ flagSize: 10 }), { xOf: (t) => t / 100 }).layer.flags.length, 4);
  const big = flagLog(NEW, evInst({ flagSize: 20 })).layer, g = big.flags[0];
  assert.equal(NEW.HBEvents.flagAt(big.flags, { x: g.x, y: 0 + 9 }, 0), g);   // 9 px off a 20 px flag still hits
  assert.equal(OLD.HBEvents.flagAt(flagLog(OLD, undefined).layer.flags, { x: g.x, y: 9 }, 0), null);
  const moveTos = (l) => l.filter((e) => e[0] === 'moveTo').length;
  assert.equal(moveTos(flagLog(NEW, evInst({ lineLow: true })).lines), moveTos(flagLog(NEW, evInst({})).lines) + 1);
  const off = flagLog(NEW, evInst({ showFlags: false }));
  assert.deepEqual(off.flags, []);
  assert.equal(off.lines.length, flagLog(NEW, evInst({})).lines.length);                   // the lines stay
  assert.equal(NEW.HBEvents.flagAt(off.layer.flags, { x: 100, y: 0 }, 0), null);
});

test('calendar: nextText takes the folder colours; none given = today', () => {
  const ev = [{ t_ms: 5000, impact: 'High', country: 'USD', title: 'X' }];
  assert.equal(OLD.HBEvents.nextText(ev, 0).color, '#F23645');
  assert.equal(NEW.HBEvents.nextText(ev, 0).color, '#F23645');
  const lk = NEW.HBEvents.look(evInst({}, { high: { color: '#0A0A0A' } }), C.styleColor);
  assert.equal(NEW.HBEvents.nextText(ev, 0, lk.colors).color, '#0A0A0A');
});

/* ---- News headlines ---- */
const item = (o) => ({ id: 'a', source: 'financialjuice', t_ms: 1000, seen_ms: 1000, title: 't', tags: [], ...o });
const ITEMS = [item({ id: 'a' }), item({ id: 'b', t_ms: 2000, source: 'truth' }), item({ id: 'c', t_ms: 3000, seen_ms: 99999 })];
const BURSTS = [{ root: 'NQ', t_ms: 1500, dir: 'up', move_ticks: 10, ratio: 3, near_news: [] }, { root: 'NQ', t_ms: 2500, dir: 'down', move_ticks: 8, ratio: 2, near_news: [] }];
const hInst = (params, style) => ({ id: 'headlines', visible: true, params, ...(style ? { style } : {}) });
const HOPT = { fromMs: 0, toMs: 1e6, nowMs: 100000 };      // 'c' was seen 1 s ago: breaking

test('headlines defaults: markers identical with no instance, a bare instance or every default spelled out', () => {
  const base = N.headlineMarkers(ITEMS, HOPT), bursts = N.burstMarkers(BURSTS, { root: 'NQ', fromMs: 0, toMs: 1e6 }, ITEMS);
  assert.deepEqual(base.map((m) => [m.size, m.color]), [[0.35, '#F7A600'], [0.35, '#7E57C2'], [0.35, '#787B86']].map((x) => x));
  for (const inst of [hInst({}), hInst({ dotSize: 0.35, boltSize: 0.6, boltText: true, trumpHighlight: true, flash: true, maxDots: 300 }), hInst({ dotSize: 'x', maxDots: NaN })]) {
    const lk = N.look(inst, C.styleColor);
    assert.deepEqual(N.headlineMarkers(ITEMS, { ...HOPT, lk }), base);
    assert.deepEqual(N.burstMarkers(BURSTS, { root: 'NQ', fromMs: 0, toMs: 1e6, lk }, ITEMS), bursts);
  }
  assert.deepEqual(bursts.map((m) => [m.size, m.color, m.text]), [[0.6, '#F23645', '⚡'], [0.6, '#089981', '⚡']]);
});

test('headlines colours: dot, Trump, breaking flash and the two burst colours', () => {
  const lk = N.look(hInst({}, { headline: { color: '#111111' }, trump: { color: '#222222' }, breaking: { color: '#333333', alpha: 50 },
    burstUp: { color: '#444444' }, burstDown: { color: '#555555' } }), C.styleColor);
  assert.deepEqual(N.headlineMarkers(ITEMS, { ...HOPT, lk }).map((m) => m.color), ['rgba(51,51,51,0.5)', '#222222', '#111111']);
  assert.deepEqual(N.burstMarkers(BURSTS, { root: 'NQ', fromMs: 0, toMs: 1e6, lk }, ITEMS).map((m) => m.color), ['#555555', '#444444']);
});

test('headlines params: dot size, bolt size and symbol, Trump colouring, flash, dot cap', () => {
  const m = (params) => N.headlineMarkers(ITEMS, { ...HOPT, lk: N.look(hInst(params), C.styleColor) });
  assert.deepEqual(m({ dotSize: 0.9 }).map((x) => x.size), [0.9, 0.9, 0.9]);
  assert.deepEqual(m({ trumpHighlight: false }).map((x) => x.color), ['#F7A600', '#787B86', '#787B86']);
  assert.deepEqual(m({ flash: false }).map((x) => x.color), ['#787B86', '#7E57C2', '#787B86']);
  assert.equal(m({ maxDots: 2 }).length, 2);
  const b = (params) => N.burstMarkers(BURSTS, { root: 'NQ', fromMs: 0, toMs: 1e6, lk: N.look(hInst(params), C.styleColor) }, ITEMS);
  assert.deepEqual(b({ boltSize: 1.4 }).map((x) => x.size), [1.4, 1.4]);
  assert.deepEqual(b({ boltText: false }).map((x) => x.text), ['', '']);
});
