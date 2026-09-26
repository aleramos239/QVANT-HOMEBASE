/* Homebase Charts — scroll-back (TradingView's): drag a chart toward its first loaded bar and the next chunk
   of older sessions loads from the server's tick archive. Pure: the request guard (one request at a time,
   none once the archive's start is on the chart, a pause after a failure) and the merge of an answer into
   the chart's bars. No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const EDGE = 50;          // bars: the view's left edge this close to the first loaded bar asks for more
const RETRY_MS = 10000;   // after a failed answer, no new request for this long
const BUSY_RETRY_MS = 2000;      // after a "busy" answer (the server was already building a chunk), retry sooner
const PENDING_TIMEOUT_MS = 30000; // a request with no answer at all for this long is given up on, not held forever
const CAP = 200000;       // bars per chart, total: past it, scroll-back stops asking for more (no eviction)

class ScrollBack {
  constructor({ edge = EDGE, retryMs = RETRY_MS, busyRetryMs = BUSY_RETRY_MS,
                pendingTimeoutMs = PENDING_TIMEOUT_MS, now = () => Date.now() } = {}) {
    this.edge = edge; this.retryMs = retryMs; this.busyRetryMs = busyRetryMs;
    this.pendingTimeoutMs = pendingTimeoutMs; this.now = now;
    this.reset();
  }

  /* A new history on the chart: nothing pending, the archive's start not known. */
  reset() { this.pending = null; this.pendingAt = 0; this.done = false; this.retryAt = 0; }

  /* The request for this visible logical range (the first loaded bar is logical 0): {before: firstMs} when
     the left edge is within `edge` bars of it and nothing holds it back, else null. The caller sends it and
     then calls sent(). A pending request that never got an answer (dropped connection, a server that never
     replied) is given up on after `pendingTimeoutMs`, so the chart is not stuck waiting on it forever. */
  want(range, firstMs) {
    if (this.pending && this.now() - this.pendingAt >= this.pendingTimeoutMs) this.pending = null;
    if (!range || firstMs == null || this.pending || this.done || this.now() < this.retryAt) return null;
    return range.from <= this.edge ? { before: firstMs } : null;
  }

  sent(req) { this.pending = req; this.pendingAt = this.now(); }

  /* An answer: true when it answers the pending request and is to be applied (bars, or the archive's
     start); false when stale (a reload came between) or failed (then a pause before asking again). Cleared
     on ANY answer -- including an error -- so a "busy" (the server was already building the previous
     chunk) never leaves the request stuck pending; "busy" retries sooner than an ordinary failure. */
  take(m) {
    if (!this.pending || !m || m.before !== this.pending.before) return false;
    this.pending = null;
    if (m.error) { this.retryAt = this.now() + (m.error === 'busy' ? this.busyRetryMs : this.retryMs); return false; }
    if (m.done) this.done = true;
    return true;
  }
}

/* The chart's bars with an older chunk in front: each older bar gets its study values (sv) from m.studies,
   and the chart's own first bars take m.repair's (the studies re-run across the join). The bar objects are
   reused. */
function prepend(bars, m) {
  const older = (m.bars || []).map((b, i) => {
    b.sv = {};
    for (const k in (m.studies || {})) b.sv[k] = m.studies[k][i];
    return b;
  });
  for (const k in (m.repair || {})) {
    m.repair[k].forEach((v, i) => { const b = bars[i]; if (b) { b.sv = b.sv || {}; b.sv[k] = v; } });
  }
  return older.concat(bars);
}

/* Session labels (gaps, approx. flow) for an older chunk in front of the chart's, one per date (the chart's
   own label wins). */
function mergeSessions(older, sessions) {
  const have = new Set((sessions || []).map((s) => s.date));
  return (older || []).filter((s) => !have.has(s.date)).concat(sessions || []);
}

/* prepend(), never letting the chart grow past `cap` bars total. No eviction: the chart's own bars are never
   dropped, only an older chunk that would overflow the cap is cropped to its newest end (still the bars
   immediately before the chart's own — the crop just leaves out the ones further back). capped: true once
   the cap has been reached (whether by this call or an earlier one already at the limit) — the caller stops
   asking for more and shows "History limit reached" instead of "Start of data". */
function capPrepend(bars, m, cap = CAP) {
  const room = cap - bars.length;
  if (room <= 0) return { bars, capped: true };
  const raw = m.bars || [];
  if (raw.length <= room) return { bars: prepend(bars, m), capped: false };
  const studies = {};
  for (const k in (m.studies || {})) studies[k] = m.studies[k].slice(raw.length - room);
  const cropped = { ...m, bars: raw.slice(raw.length - room), studies };
  return { bars: prepend(bars, cropped), capped: true };
}

const api = { ScrollBack, prepend, mergeSessions, capPrepend, EDGE, RETRY_MS, BUSY_RETRY_MS, PENDING_TIMEOUT_MS, CAP };
if (typeof window !== 'undefined') window.HBScrollBack = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
