/* Homebase Charts — pure helpers for the "Fill quality" bottom-panel tab (Task 3, page half; the
   desk half lives in homebase/bothistory.py and is out of scope here). GET /api/desk/bot-history
   (HBDeskClient.botHistory, cached) now carries per run: fire_ms, placed_ms, latency_ms, and per
   filled leg entry.slip_ticks / exit.slip_ticks / exit.gap_through -- null wherever a run cannot
   answer (a skip, a missing leg, an unmatched fill). Positive slip always means worse for us.

   This module turns those raw runs into the tab's rows and its summary line, and converts a tick
   count to dollars per contract via the root's tick value (tick size x point value). No DOM, no
   browser globals: the Node tests load this file directly; panel.js builds the table and wires the
   strategy selector against HBDeskClient. */
(function () {
'use strict';
// Looked up lazily (not cached at load time): in the page, script tag order should not matter
// here, and in Node, require() only resolves once this module is asked to run.
function replay() { return (typeof window !== 'undefined' && window.HBReplay) || (typeof require === 'function' ? require('./replay.js') : null); }

// root -> minimum price increment (homebase/contracts.py's _SPECS; the same 8 roots replay.js's
// own POINT_VALUE fallback covers, verified there for the practice feature). Only used to turn a
// slip in TICKS into a dollar figure when no chart happens to be open on that root already.
const TICK_SIZE = { NQ: 0.25, ES: 0.25, YM: 1.0, RTY: 0.10, GC: 0.10, SI: 0.005, CL: 0.01, BTC: 5.0 };

/* USD value of one tick, one contract, for `root` -- null if either half is unknown. */
function tickValue(root) {
  const ts = TICK_SIZE[String(root || '').toUpperCase()];
  const R = replay(), pv = R ? R.pointValue(root) : null;
  return (ts == null || pv == null) ? null : ts * pv;
}

/* A "live run": the bot actually placed (it has at least one leg), as opposed to a day-level fact
   with no account (a gate-chop skip, a refused signal, a pre-fire kill) -- those carry no fire/
   latency/slip and do not belong in a fill-quality row. */
function isLiveRun(run) {
  return !!(run && Array.isArray(run.legs) && run.legs.length > 0);
}

function num(v) { return typeof v === 'number' && Number.isFinite(v) ? v : null; }

/* One live run -> one display row. `tv` is that run's root's tick value (tickValue(root)), passed
   in rather than looked up per row so a caller pricing many runs on the same root does it once. */
function fillQualityRow(run, tv) {
  const entryTicks = run.entry ? num(run.entry.slip_ticks) : null;
  const isSl = !!(run.exit && run.exit.kind === 'sl');
  const slTicks = isSl ? num(run.exit.slip_ticks) : null;
  const gapThrough = isSl && typeof run.exit.gap_through === 'boolean' ? run.exit.gap_through : null;
  return {
    date: run.date, account: typeof run.account === 'string' ? run.account : null,
    latencyMs: num(run.latency_ms),
    entryTicks, entryUsd: entryTicks != null && tv != null ? entryTicks * tv : null,
    slTicks, slUsd: slTicks != null && tv != null ? slTicks * tv : null,
    gapThrough,
  };
}

/* Every live run in `runs` (HBDeskClient.botHistory's .data.runs, or []) as display rows, newest
   first (by date, then account -- a strategy-wide row, account null, sorts after its own accounts'
   rows on the same date). `root` prices the ticks into dollars (tickValue(root)); unknown -> every
   *Usd field is null, never a wrong number. */
function fillQualityRows(runs, root) {
  const tv = tickValue(root);
  return (Array.isArray(runs) ? runs : [])
    .filter(isLiveRun)
    .map((r) => fillQualityRow(r, tv))
    .sort((a, b) => {
      if (a.date !== b.date) return a.date < b.date ? 1 : -1;
      if (a.account === b.account) return 0;
      if (a.account == null) return 1;
      if (b.account == null) return -1;
      return a.account < b.account ? -1 : 1;
    });
}

/* The middle value of the non-null numbers in `nums` (even count: the mean of the two middle
   values); null on an empty list -- never 0, which would read as a real, fast latency. */
function median(nums) {
  const xs = nums.filter((v) => v != null).slice().sort((a, b) => a - b);
  if (!xs.length) return null;
  const mid = xs.length >> 1;
  return xs.length % 2 ? xs[mid] : (xs[mid - 1] + xs[mid]) / 2;
}

/* The mean of the non-null numbers in `nums`; null on an empty list (never 0). */
function mean(nums) {
  const xs = nums.filter((v) => v != null);
  return xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : null;
}

/* The tab's summary row: average entry slip and average SL slip (each in ticks and in $ per
   contract), the median fire-to-ack latency, and n = the number of live runs shown. Every average
   is taken over only the rows that actually answer that field -- a run with no SL exit (a TP, a
   flatten) never drags the SL average toward 0. */
function fillQualitySummary(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return {
    n: list.length,
    avgEntryTicks: mean(list.map((r) => r.entryTicks)),
    avgEntryUsd: mean(list.map((r) => r.entryUsd)),
    avgSlTicks: mean(list.map((r) => r.slTicks)),
    avgSlUsd: mean(list.map((r) => r.slUsd)),
    medianLatencyMs: median(list.map((r) => r.latencyMs)),
  };
}

const api = { TICK_SIZE, tickValue, isLiveRun, fillQualityRows, fillQualitySummary, median, mean };
if (typeof window !== 'undefined') window.HBFillQuality = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
