/* Homebase Lab -- HBReal: the six real-or-luck lines and the verdict (the owner's law, 2026-10-25).
   lines(s, tries) is a line-by-line copy of research blueprint/real.py check(): the same constants, the same words, the same
   Python number formatting (half-to-even, "-0", "2.0"). Its input is real.py's own: {is: rows, lock, oos}. It is pinned by
   tests/js/fixtures/real_parity.json, which tools/real_parity_fixture.py writes from real.check() itself -- run it again when
   real.py changes. verdict() is the Lab's REAL / LUCK / FAKE / NOT YET rule (the same one the fixture script holds).
   fromLab(res) maps a saved 3:1 walk-forward result (walkforward.fixed_result) to that input: t is the result's own saved t_stat,
   never worked out here; the years come from the in-sample block rows (each block sits inside one year); worse fills is not run
   in the Lab, so the Lab alone never says REAL.
   No DOM, no fetch: tests/js/reallines.test.mjs runs it headless. lab.js prints it. */
(function () {
'use strict';

const MIN_TRADES_IS = 200, MIN_TRADES_OOS = 60;
const MIN_YEARS_GREEN = 2 / 3, MAX_BEST_YEAR = 0.5;
const MIN_BOXES_PROFIT = 0.6;
const T_BAR = 2.0, T_PER_TRY = 0.25;

/* Python's number formatting, for the words to match real.py's to the letter */
function evenInt(v) {                     // round half to even: Python's rule on an exact tie
  const f = Math.floor(v), d = v - f;
  return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1;
}
function f0(v, commas) {                  // f"{v:.0f}" / f"{v:,.0f}"
  const n = evenInt(Math.abs(v)), neg = v < 0 || Object.is(v, -0);
  return (neg ? '-' : '') + (commas ? String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',') : String(n));
}
const pct0 = (v) => `${f0(v * 100)}%`;    // f"{v:.0%}" (Python multiplies by 100 first)
const g = (v) => String(Number(v.toPrecision(6)));   // f"{v:g}" (shortcut: no exponent form, reached only past ~4 million tries)
function round2(v) {                      // str(round(v, 2))
  const r = Number.isInteger(v * 8) && (v * 8) % 2 !== 0 ? evenInt(v * 100) / 100 : Number(v.toFixed(2));   // an exact tie is k/8, k odd
  return Number.isInteger(r) ? `${r < 0 || Object.is(r, -0) ? '-' : ''}${Math.abs(r)}.0` : String(r);
}
const py = (v) => (v == null ? 'None' : String(v));

const line = (name, ok, said) => ({ line: name, ok, said });

/* real.check(s, tries) */
function lines(s, tries = 1) {
  const rows = s.is, lock = s.lock, oos = s.oos, out = [];
  const prof = rows.filter((r) => r.net != null).map((r) => r.net > 0), up = prof.filter(Boolean).length;
  out.push(line('boxes', prof.length ? up / prof.length >= MIN_BOXES_PROFIT : null,
    `${up} of ${prof.length} boxes made money in-sample (need ${pct0(MIN_BOXES_PROFIT)}): the average of the boxes, not the best`));
  const box = rows.find((r) => lock && r.box === lock.box);
  if (!box) return out.concat([line('picked box', null, 'not picked yet: the owner picks a box, then the other lines are read')]);
  const bar = T_BAR + T_PER_TRY * (Math.max(tries, 1) - 1);
  out.push(line('trades', box.trades >= MIN_TRADES_IS, `${box.trades} in-sample trades (need ${MIN_TRADES_IS}+)`));
  out.push(line('luck', box.t_stat != null && box.t_stat >= bar && box.net > 0,
    `t ${box.t_stat == null ? 'None' : round2(box.t_stat)} in-sample (need ${g(bar)}+ after ${tries} ${tries === 1 ? 'try' : 'tries'}), net ${f0(box.net, true)}`
    + (box.beats_random != null ? `, beats ${pct0(box.beats_random)} of random entries` : '')));
  const yn = box.years_n, yg = box.years_green, sh = box.best_year_share;
  out.push(line('years', !!yn && yg / yn >= MIN_YEARS_GREEN && sh != null && sh <= MAX_BEST_YEAR,
    `${py(yg)} of ${py(yn)} years green` + (sh == null ? '' : `, best year ${pct0(sh)} of the net`) + ` (need ${pct0(MIN_YEARS_GREEN)} green, no year over ${pct0(MAX_BEST_YEAR)})`));
  const w = box.worse_fills_net;
  out.push(line('worse fills', w == null ? null : w > 0, w == null ? 'worse-fills run not on file' : `net ${f0(w, true)} with worse fills (need above 0)`));
  if (oos == null || oos.state) return out.concat([line('test months', null, 'not run: only when the owner says so')]);
  const x = oos.record;
  out.push(line('test months', x.net > 0 && box.net > 0 && x.trades >= MIN_TRADES_OOS,
    `${x.trades} trades (need ${MIN_TRADES_OOS}+), net ${f0(x.net, true)} (need above 0, same direction as in-sample ${f0(box.net, true)})`));
  return out;
}

const NEXT = { boxes: 'the in-sample table', 'picked box': 'your pick', luck: 'the luck test', 'worse fills': 'worse fills', 'test months': 'the test months' };
/* REAL / LUCK / FAKE / NOT YET and why. FAKE: the test months ran and lost, or went the other way from in-sample. LUCK: any other
   line failed (the first, named). NOT YET: nothing failed but a line is not run (the first is the next step); a tries count that
   may be cut short (`cut`) never lets the luck line pass. REAL: all six pass. */
function verdict(ls, s, cut = false) {
  const box = s.is.find((r) => s.lock && r.box === s.lock.box), by = Object.fromEntries(ls.map((x) => [x.line, x]));
  if (box && s.oos != null && !s.oos.state && !(s.oos.record.net > 0 && box.net > 0)) return { word: 'FAKE', why: by['test months'].said };
  const bad = ls.find((x) => x.ok === false);
  if (bad) return { word: 'LUCK', why: bad.said };
  for (const x of ls) {
    if (x.ok == null || (cut && x.line === 'luck')) return { word: 'NOT YET', why: `next, ${x.ok && cut ? 'a full count of tries' : NEXT[x.line]}` };
  }
  return { word: 'REAL', why: 'all six lines pass' };
}

/* A saved fixed walk-forward result -> real.py's input. Years: the box's in-sample blocks that traded, summed by year. */
function years(blocks) {
  const by = new Map();
  for (const b of blocks || []) if (b && b.trades > 0 && b.is && b.is[0]) { const y = String(b.is[0]).slice(0, 4); by.set(y, (by.get(y) || 0) + (b.net || 0)); }
  const v = [...by.values()], sum = v.reduce((a, x) => a + x, 0);
  return { years_n: v.length, years_green: v.filter((x) => x > 0).length, best_year_share: v.length && sum > 0 ? Math.max(...v) / sum : null };
}
function fromLab(res) {
  const r = res || {}, o = r.oos;
  return {
    is: (r.cells || []).map((c) => ({ box: c.i, net: c.is ? c.is.net ?? null : null, trades: c.is ? c.is.trades : 0, t_stat: c.is && c.is.t_stat != null ? c.is.t_stat : null,
      ...years(c.blocks), worse_fills_net: null, beats_random: null })),
    lock: r.lock ? { box: r.lock.cell } : null,
    oos: !o ? null : o.state === 'done' && o.record ? { record: { net: o.record.net || 0, trades: o.record.trades || 0 } } : { state: o.state || 'none' },
  };
}
/* The luck bar for a tries count, in words. `cut`: the count may be short (a full page of saved runs). */
function barText(tries, cut) {
  const n = Math.max(tries, 1), bar = T_BAR + T_PER_TRY * (n - 1);
  return `Luck test: needs ${g(bar)} or more (${n === 1 ? 'the first try' : `${T_BAR.toFixed(1)}, plus ${T_PER_TRY} for each of the ${n - 1} ${n === 2 ? 'try' : 'tries'} after the first`})`
    + (cut ? ` · tries ${n}+, count incomplete` : '');
}
/* The Lab's read of a saved result: the lines, with the two things the Lab cannot know said plainly (never looser than real.py):
   worse fills is not run here; a t that is not saved leaves the luck line not read, unless the box lost (then it fails anyway). */
function labRead(res, tries, cut) {
  const s = fromLab(res), ls = lines(s, tries), box = s.is.find((r) => s.lock && r.box === s.lock.box);
  for (const x of ls) {
    if (x.line === 'worse fills' && x.ok == null) x.said = 'not run in the Lab';
    if (x.line === 'luck' && box && box.t_stat == null && box.net > 0) { x.ok = null; x.said = 'not read: the t-statistic is not saved in the Lab'; }
  }
  return { lines: ls, verdict: verdict(ls, s, cut), up: s.is.filter((r) => r.net != null && r.net > 0).length, n: s.is.filter((r) => r.net != null).length };
}

const api = { MIN_TRADES_IS, MIN_TRADES_OOS, MIN_YEARS_GREEN, MAX_BEST_YEAR, MIN_BOXES_PROFIT, T_BAR, T_PER_TRY,
  lines, verdict, fromLab, years, barText, labRead, pyFmt: { f0, pct0, g, round2 } };
if (typeof window !== 'undefined') window.HBReal = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
