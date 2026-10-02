import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/testerlayer.js');

const BARS = [
  { ms: 1000, tt: 1000, s: '2024-01-02' },
  { ms: 2000, tt: 2000, s: '2024-01-02' },
  { ms: 3000, tt: 3000, s: '2024-01-03' },
  { ms: 4000, tt: 4000, s: '2024-01-03' },
];

test('tradesInRange: keeps a trade whose entry or exit overlaps the loaded window, drops the rest', () => {
  const trades = [
    { entry_ms: 500, exit_ms: 900 },     // entirely before the first bar: dropped
    { entry_ms: 500, exit_ms: 1500 },    // exit lands inside: kept
    { entry_ms: 2500, exit_ms: 3500 },   // fully inside: kept
    { entry_ms: 3900, exit_ms: 4200 },   // entry before the coverage end (barMs 1000 -> end 5000): kept
    { entry_ms: 5000, exit_ms: 6000 },   // entirely past the coverage end: dropped
  ];
  const kept = X.tradesInRange(trades, BARS, 1000);
  assert.deepEqual(kept.map((e) => e.t.entry_ms), [500, 2500, 3900]);
  assert.deepEqual(kept.map((e) => e.i), [1, 2, 3], 'each comes back with its index in the run (the selection speaks in run indices)');
});

test('tradesInRange: a non-time chart (barMs 0) never bounds the far end', () => {
  const trades = [{ entry_ms: 999999, exit_ms: 1000000 }];
  assert.deepEqual(X.tradesInRange(trades, BARS, 0), [{ t: trades[0], i: 0 }]);
});

test('tradesInRange: no bars loaded -> nothing, whatever the trades are', () => {
  assert.deepEqual(X.tradesInRange([{ entry_ms: 1, exit_ms: 2 }], [], 1000), []);
  assert.deepEqual(X.tradesInRange([{ entry_ms: 1, exit_ms: 2 }], null, 1000), []);
});

test('sessionIndex: each session date -> its first and last bar index, in one pass', () => {
  const m = X.sessionIndex(BARS);
  assert.deepEqual(m.get('2024-01-02'), [0, 1]);
  assert.deepEqual(m.get('2024-01-03'), [2, 3]);
  assert.equal(m.get('2024-01-09'), undefined);
  assert.equal(X.sessionIndex([]).size, 0);
  assert.equal(X.sessionIndex(null).size, 0);
});

test('plotPoints: maps [t_ms, v] to the covering bar\'s tt, drops a point before the first bar, keeps the last value per tt', () => {
  const pts = [[500, 1], [1000, 2], [1500, 3], [2000, 4], [2000, 5]];
  // 500 -> before bar 0: dropped. 1000 and 1500 both cover bar 0 (tt 1000): the later (1500 -> 3) wins.
  // 2000 and 2000 both cover bar 1 (tt 2000): the later (5) wins.
  assert.deepEqual(X.plotPoints(pts, BARS), [{ time: 1000, value: 3 }, { time: 2000, value: 5 }]);
});

test('plotPoints: a point past the last bar still lands on it (no upper bound, unlike a marker)', () => {
  assert.deepEqual(X.plotPoints([[9999, 7]], BARS), [{ time: 4000, value: 7 }]);
});

test('plotPoints: no bars -> []', () => {
  assert.deepEqual(X.plotPoints([[1, 2]], []), []);
  assert.deepEqual(X.plotPoints([[1, 2]], null), []);
});

/* ---------------------------------------------------------------- rule geometry (2026-09-27)
   The strategy records every level it PLACED, so the page must read a session at a glance:
   style by role (never by parsing the name beyond the side), label each line at its right-hand
   end, stack labels that collide, and hide them when the session is too narrow to carry text. */

const P = { up: '#089981', down: '#F23645', accent: '#2962FF', text2: '#787B86' };
const h = (name, role, price = 1) => ({ name, price, role, date: '2024-01-02' });

test('hlineStyle: role picks the colour — entry takes its own side, sl red, tp green, anchor/level neutral', () => {
  assert.equal(X.hlineStyle(h('Long entry +5', 'entry'), P).color, P.accent);
  assert.equal(X.hlineStyle(h('Short entry −5', 'entry'), P).color, P.down);
  assert.equal(X.hlineStyle(h('Long SL', 'sl'), P).color, P.down);
  assert.equal(X.hlineStyle(h('Long TP', 'tp'), P).color, P.up);
  assert.equal(X.hlineStyle(h('anchor · NFP', 'anchor'), P).color, P.text2);
  assert.equal(X.hlineStyle(h('stop', 'level'), P).color, P.text2);
  assert.equal(X.hlineStyle(h('legacy', undefined), P).color, P.text2);   // a record from before roles
});

test('hlineStyle: the anchor is solid, a live level dashed, a planned / unfilled one dimmer and finer', () => {
  assert.deepEqual(X.hlineStyle(h('anchor', 'anchor'), P).dash, []);
  const live = X.hlineStyle(h('Long SL', 'sl'), P);
  const planned = X.hlineStyle(h('Long SL (planned)', 'sl'), P);
  const gone = X.hlineStyle(h('Short SL (not filled)', 'sl'), P);
  assert.equal(live.alpha, 1);
  assert.equal(planned.alpha < 1 && gone.alpha === planned.alpha, true);
  assert.deepEqual(planned.dash, gone.dash);
  // "more finely dashed": shorter ink, longer gap than the live counterpart
  assert.equal(planned.dash[0] < live.dash[0] && planned.dash[1] > live.dash[1], true);
  assert.equal(planned.color, live.color);          // dimmed by alpha, not by a different colour
});

test('hlineLabel: the name and the price, as the tester shows every price (the hover text)', () => {
  assert.equal(X.hlineLabel(h('Long entry +5', 'entry', 30925)), 'Long entry +5 · 30,925.00');
  assert.equal(X.hlineLabel(h('Short SL (not filled)', 'sl', 2050.4)), 'Short SL (not filled) · 2,050.40');
});

test('stackLabels: labels that do not collide keep their own y', () => {
  assert.deepEqual(X.stackLabels([{ y: 10, t: 'a' }, { y: 50, t: 'b' }], 12, 0, 100).map((r) => r.y), [10, 50]);
});

test('stackLabels: colliding labels are pushed apart by one row, in price order', () => {
  const rows = [{ y: 16, t: 'c' }, { y: 10, t: 'a' }, { y: 14, t: 'b' }];
  assert.deepEqual(X.stackLabels(rows, 12, 0, 500), [{ y: 10, t: 'a' }, { y: 22, t: 'b' }, { y: 34, t: 'c' }]);
  assert.deepEqual(rows.map((r) => r.y), [16, 10, 14]);        // pure: the input is untouched
});

test('stackLabels: a stack that runs past the pane is pushed back up, keeping its spacing', () => {
  assert.deepEqual(X.stackLabels([{ y: 95 }, { y: 96 }, { y: 97 }], 12, 0, 100).map((r) => r.y), [76, 88, 100]);
  assert.deepEqual(X.stackLabels([{ y: -5 }], 12, 0, 100).map((r) => r.y), [0]);
});

test('stackLabels: nothing in, nothing out', () => {
  assert.deepEqual(X.stackLabels([], 12, 0, 100), []);
  assert.deepEqual(X.stackLabels(null, 12, 0, 100), []);
});

test('labelsFit: a session narrower than the minimum draws its lines but no text', () => {
  assert.equal(X.labelsFit(100, 100 + X.LABEL_MIN_PX), true);
  assert.equal(X.labelsFit(100, 100 + X.LABEL_MIN_PX - 1), false);
  assert.equal(X.labelsFit(null, 200), false);
});

test('hlineTip: hover text names the level, its price and the session it belongs to', () => {
  assert.equal(X.hlineTip(h('Long TP', 'tp', 30925)), 'Long TP · 30,925.00\n2024-01-02');
});

/* ---------------------------------------------------------------- drawing a run (2026-09-29) */

test('levelText: compact -- no price, no "entry", no planned / not-filled mark; the hover keeps the rest', () => {
  assert.equal(X.levelText(h('Long entry +10', 'entry')), 'Long +10');
  assert.equal(X.levelText(h('Short entry −10 (not filled)', 'entry')), 'Short −10');
  assert.equal(X.levelText(h('Long SL (planned)', 'sl')), 'Long SL');
  assert.equal(X.levelText(h('anchor · NFP', 'anchor')), 'Anchor · NFP');
  assert.equal(X.levelText(h('stop', 'level')), 'Stop');
});

test('hlineTip: a level with a stamp also says the window it was drawn over (ET)', () => {
  const t = Date.UTC(2024, 0, 2, 14, 30), e = Date.UTC(2024, 0, 2, 21, 0);      // 09:30 and 16:00 ET
  assert.equal(X.hlineTip({ ...h('Long TP', 'tp', 30925), t_ms: t, end_ms: e }), 'Long TP · 30,925.00\n2024-01-02 · from 09:30:00 to 16:00:00 ET');
});

test('placeLabels: live labels stack apart; a dimmed one is kept only where it fits and never pushes anything', () => {
  const rows = [{ y: 50, id: 'a' }, { y: 52, id: 'b' }, { y: 51, id: 'planned', dim: true }, { y: 90, id: 'far', dim: true }];
  const out = X.placeLabels(rows, 12, 0, 200);
  assert.deepEqual(out.map((r) => r.id).sort(), ['a', 'b', 'far']);          // 'planned' would sit on a / b: dropped
  const live = out.filter((r) => !r.dim).sort((a, b) => a.y - b.y);
  assert.equal(live[1].y - live[0].y >= 12, true);
  assert.equal(out.find((r) => r.id === 'far').y, 90);
  assert.deepEqual(X.placeLabels([], 12, 0, 100), []);
});

test('dedupeLevels: the same words at the same price in one session are one level (the later record wins)', () => {
  const a = h('Long SL (planned)', 'sl', 100), b = h('Long SL', 'sl', 100), c = h('Long SL', 'sl', 101.25);
  assert.deepEqual(X.dedupeLevels([a, b, c]), [b, c]);
  assert.equal(X.dedupeLevels([h('x', 'level'), { ...h('x', 'level'), date: '2024-01-03' }]).length, 2);
});

test('plotPane: a series near the candles\' price is a price-pane line; a gate reading or an oscillator gets a sub-pane', () => {
  const bars = [{ c: 30000 }, { c: 30100 }, { c: 29900 }];
  assert.equal(X.plotPane([[1, 30050], [2, 29980]], bars), 'price');       // an average of price
  assert.equal(X.plotPane([[1, 12.07], [2, 18.4]], bars), 'sub');          // ADX
  assert.equal(X.plotPane([[1, 0.75], [2, 0.75]], bars), 'sub');           // a 0..1 gate
  assert.equal(X.plotPane([[1, 5]], []), 'sub');                           // nothing to compare with: the safe pane
  assert.equal(X.plotPane([], bars), 'sub');
});

test('isConstant: a threshold that never moves is a guide line', () => {
  assert.equal(X.isConstant([[1, 20], [2, 20]]), true);
  assert.equal(X.isConstant([[1, 20], [2, 21]]), false);
  assert.equal(X.isConstant([]), false);
});

test('valueAt: a sparse series reads its last value at or before the crosshair', () => {
  const d = [{ time: 10, value: 1 }, { time: 20, value: 2 }, { time: 30, value: 3 }];
  assert.equal(X.valueAt(d, 5), null);
  assert.equal(X.valueAt(d, 10), 1);
  assert.equal(X.valueAt(d, 25), 2);
  assert.equal(X.valueAt(d, 99), 3);
  assert.equal(X.valueAt([], 1), null);
});

test('boxGeometry: entry and exit x, the y of entry / exit / TP / SL; a same-bar trade keeps a visible width', () => {
  const t = { entry_ms: 100, exit_ms: 100, entry_price: 50, exit_price: 60, tp: 60, sl: 45 };
  const g = X.boxGeometry(t, (ms) => ms / 10, (p) => 1000 - p);
  assert.deepEqual(g, { x0: 10, x1: 10 + X.MIN_BOX_W, ey: 950, xy: 940, ty: 940, sy: 955 });
  assert.equal(X.boxGeometry({ ...t, tp: null }, (ms) => ms, (p) => p).ty, null);
  assert.equal(X.boxGeometry(t, () => null, (p) => p), null);              // no x for the entry / exit
  assert.equal(X.boxGeometry(t, (ms) => ms, () => null), null);            // no y for the entry
});

test('fillSides: a long buys then sells, a short the other way -- the live chart\'s blue buy / red sell', () => {
  assert.deepEqual(X.fillSides({ side: 'long' }), { entry: 'buy', exit: 'sell' });
  assert.deepEqual(X.fillSides({ side: 'short' }), { entry: 'sell', exit: 'buy' });
});

test('thinLabels: overlapping labels lose to the higher priority; separate ones all stay', () => {
  const a = { x: 0, y: 0, w: 40, h: 12, prio: 1, id: 'a' }, b = { x: 20, y: 4, w: 40, h: 12, prio: 2, id: 'b' };
  const c = { x: 100, y: 0, w: 40, h: 12, prio: 1, id: 'c' };
  assert.deepEqual(X.thinLabels([a, b, c]).map((r) => r.id).sort(), ['b', 'c']);
  assert.deepEqual(X.thinLabels([a, c]).map((r) => r.id).sort(), ['a', 'c']);
  assert.deepEqual(X.thinLabels([]), []);
});

test('tradeTip: number, side, times, the three levels, how it ended and the P&L', () => {
  const f = { price: (v) => v.toFixed(2), et: (ms) => new Date(ms).toISOString().replace('T', ' ').slice(0, 19), usd: (v) => `$${v}` };
  const t = { side: 'long', entry_ms: Date.UTC(2026, 8, 21, 13, 30, 0), exit_ms: Date.UTC(2026, 8, 21, 13, 30, 24), entry_price: 30231.75,
    exit_price: 30246.75, sl: 30226.75, tp: 30246.75, exit_reason: 'tp', net: 296 };
  assert.equal(X.tradeTip(t, 5, f), '#6 Long · 2026-09-21 13:30:00 → 13:30:24 ET\nEntry 30231.75 · SL 30226.75 · TP 30246.75\nExit 30246.75 (TP) · $296');
});

/* ---------------------------------------------------------------- jumping to a trade and staying there */

const T0 = { entry_ms: 5000, exit_ms: 6000, date: '2026-09-21' };
/* a chart that is only as truthful as the test makes it: `view` is what the time scale would report */
function fakeCell(over = {}) {
  const c = { chart: { timeScale: () => ({ getVisibleLogicalRange: () => c.view }) }, bars: [{ ms: 1000 }, { ms: 5000 }, { ms: 9000 }],
    view: { from: 2, to: 9 }, box: { addEventListener() {}, removeEventListener() {} }, focused: 0, reached: 0,
    async reach() { c.reached++; return true; }, focusRange() { c.focused++; c.view = { from: 0, to: 2 }; return true; }, ...over };
  return c;
}
const noWait = () => Promise.resolve();

test('viewShows: the visible window holds the bar the trade entered on', () => {
  assert.equal(X.viewShows(fakeCell({ view: { from: 0, to: 2 } }), T0), true);
  assert.equal(X.viewShows(fakeCell({ view: { from: 2, to: 9 } }), T0), false);
  assert.equal(X.viewShows(fakeCell({ view: null }), T0), false);
  assert.equal(X.viewShows(fakeCell({ chart: null }), T0), false);
});

test('settleFocus: a view that is already on the trade is left alone', async () => {
  const c = fakeCell({ view: { from: 0, to: 2 } });
  assert.equal(await X.settleFocus(c, T0, { wait: noWait }), true);
  assert.equal(c.focused, 0);
});

test('settleFocus: a view pulled away (a late history answer re-fits it) is brought back', async () => {
  const c = fakeCell();                                    // starts elsewhere
  assert.equal(await X.settleFocus(c, T0, { wait: noWait }), true);
  assert.equal(c.focused, 1);
  assert.equal(c.reached, 1);                              // it re-reaches the history first, then focuses
});

test('settleFocus: gives up after its tries when the view will not stay', async () => {
  const c = fakeCell({ focusRange() { c.focused++; return true; } });     // focusing never sticks
  assert.equal(await X.settleFocus(c, T0, { wait: noWait, tries: 3 }), false);
  assert.equal(c.focused, 3);
});

test('settleFocus: a newer jump, or a destroyed chart, ends it quietly', async () => {
  const c = fakeCell();
  assert.equal(await X.settleFocus(c, T0, { wait: noWait, isCurrent: () => false }), false);
  assert.equal(c.focused, 0);
  const d = fakeCell({ reach: async () => false });
  assert.equal(await X.settleFocus(d, T0, { wait: noWait }), false);      // the history can no longer be reached
});

test('settleFocus: the viewer touching the chart ends it -- it never fights a drag', async () => {
  let fire;
  const c = fakeCell({ box: { addEventListener: (e, f) => { if (e === 'pointerdown') fire = f; }, removeEventListener() {} } });
  const done = X.settleFocus(c, T0, { wait: async () => { fire(); } });
  assert.equal(await done, false);
  assert.equal(c.focused, 0);
});

/* the page around a jump: two cells, the selected one first */
function fakeEnv(cells, over = {}) {
  const notes = [];
  const U = { bundle: { run: { strategy: { root: 'NQ' } }, trades: [T0] }, selected: null, select(i) { U.selected = i; } };
  const page = { cells: () => cells, cur: () => cells[0], sbNote: (n) => notes.push(n), select() {}, clockMs: () => Date.UTC(2026, 8, 29) };
  return { notes, U, page, tester: { reachSpec: (s) => s }, cat: { specLabel: (s) => s }, wait: noWait,
    chartFacts: (c) => ({ root: (c.shown || c.cfg).root, replay: !!c.replay, tradeReady: false }), ...over };
}
const nqCell = (over = {}) => fakeCell({ cfg: { root: 'NQ', spec: 'time:60' }, shown: { root: 'NQ' }, whenLoaded: () => Promise.resolve(true), update() {}, ...over });

test('runJump (Claude\'s show): reaches back to the trade, focuses it, and stays until the view holds', async () => {
  const a = nqCell(), b = nqCell();
  const env = fakeEnv([a, b]);
  await X.runJump(env, 0, b, { select: false, avoidSelected: true });
  assert.equal(b.reached >= 1 && b.focused >= 1, true);
  assert.equal(a.focused, 0);
  assert.equal(env.U.selected, 0);
});

test('runJump: the view being reset by a late answer is repaired -- the reported "never scrolls to the trade"', async () => {
  const b = nqCell({ view: { from: 2, to: 9 } });
  let calls = 0;
  b.focusRange = () => { calls++; b.view = calls === 1 ? { from: 0, to: 2 } : { from: 0, to: 2 }; if (calls === 1) setTimeout(() => { b.view = { from: 2, to: 9 }; }, 0); return true; };
  const env = fakeEnv([nqCell(), b], { wait: () => new Promise((r) => setTimeout(r, 5)) });
  await X.runJump(env, 0, b, { select: false, avoidSelected: true });
  assert.equal(calls, 2, 'focused once, saw the view pulled off it, focused again');
  assert.equal(X.viewShows(b, T0), true);
});

test('runJump: a load that never answers does not hang the jump for good', async () => {
  const b = nqCell({ cfg: { root: 'ES', spec: 'time:60' }, shown: { root: 'ES' }, whenLoaded: () => new Promise(() => {}) });
  const env = fakeEnv([nqCell(), b], { wait: () => new Promise((r) => setTimeout(r, 5)) });
  await X.runJump(env, 0, b, { select: false });
  assert.equal(b.reached >= 1, true, 'it went on to reach the trade after the wait');
});

test('runJump: a chart destroyed mid-jump (a grid rebuild) is re-planned once onto the chart that replaced it', async () => {
  const a = nqCell(), old = nqCell(), fresh = nqCell();
  const cells = [a, old];
  const env = fakeEnv(cells);
  old.reach = async () => { cells.splice(1, 1, fresh); return true; };      // the grid is rebuilt while it loads
  await X.runJump(env, 0, old, { select: false, avoidSelected: true });
  assert.equal(fresh.focused >= 1, true);
});

test('runJump: never touches a replaying chart or one with accounts', async () => {
  const b = nqCell({ replay: true }), env = fakeEnv([nqCell(), b]);
  await X.runJump(env, 0, b, { select: false });
  assert.equal(b.reached, 0);
  assert.match(env.notes.at(-1), /replaying/);
});

/* ---------------------------------------------------------------- a trade in its context (the Lab) */

test('focusTradeView: no context is the tight zoom every caller always got', () => {
  const calls = [], c = fakeCell({ focusRange(a, b) { calls.push([a, b]); return true; } });
  X.focusTradeView(c, T0);
  X.focusTradeView(c, T0, 0);
  assert.deepEqual(calls, [[5000, 6000], [5000, 6000]]);
});

test('focusTradeView: with context the window widens both ways, never before the first bar held', () => {
  const calls = [], c = fakeCell({ focusRange(a, b) { calls.push([a, b]); return true; } });
  X.focusTradeView(c, T0, 2000);
  X.focusTradeView(c, T0, 60000);                 // would start before bars[0].ms = 1000
  assert.deepEqual(calls, [[3000, 8000], [1000, 66000]]);
  const empty = fakeCell({ bars: [], focusRange(a, b) { calls.push([a, b]); return false; } });
  assert.equal(X.focusTradeView(empty, T0, 2000), false);
});

test('settleFocus with context reaches back for the history before the entry and re-frames with it', async () => {
  const reached = [], framed = [];
  const c = fakeCell({ async reach(ms) { reached.push(ms); return true; }, focusRange(a, b) { framed.push([a, b]); c.view = { from: 0, to: 2 }; return true; } });
  assert.equal(await X.settleFocus(c, T0, { wait: noWait, contextMs: 2000 }), true);
  assert.deepEqual(reached, [3000]);
  assert.deepEqual(framed, [[3000, 8000]]);
});

test('settleFocus with context still holds the trade when the history before it cannot load', async () => {
  const reached = [];
  const c = fakeCell({ async reach(ms) { reached.push(ms); return ms >= 5000; }, focusRange() { c.view = { from: 0, to: 2 }; return true; } });
  assert.equal(await X.settleFocus(c, T0, { wait: noWait, contextMs: 2000 }), true);
  assert.deepEqual(reached, [3000, 5000]);
});

test('focusTradeView: {before, after} frames a trade from the session\'s open to its close', () => {
  const calls = [], c = fakeCell({ focusRange(a, b) { calls.push([a, b]); return true; } });
  X.focusTradeView(c, T0, { before: 1500, after: 9000 });
  X.focusTradeView(c, T0, { before: 0, after: 0 });
  X.focusTradeView(c, T0, { before: -5, after: 'x' });
  assert.deepEqual(calls, [[3500, 15000], [5000, 6000], [5000, 6000]]);
  assert.deepEqual(X.contextOf(2000), { before: 2000, after: 2000 });
  assert.deepEqual(X.contextOf(null), { before: 0, after: 0 });
});

test('focusTradeView: on a real chart the window asked for is the frame itself (no second helping of padding)', () => {
  const set = [];
  const c = fakeCell({ focusRange() { throw new Error('focusRange would pad the window again'); } });
  c.bars = Array.from({ length: 100 }, (_, k) => ({ ms: 1000 * k }));
  c.chart = { timeScale: () => ({ getVisibleLogicalRange: () => c.view, setVisibleLogicalRange: (r) => set.push(r) }) };
  assert.equal(X.focusTradeView(c, { entry_ms: 50000, exit_ms: 52000 }, { before: 20000, after: 30000 }), true);
  assert.deepEqual(set, [{ from: 28, to: 84 }]);
});
