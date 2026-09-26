/* Homebase Charts — scroll-back (TradingView's): drag a chart toward its first loaded bar and the next chunk
   of older sessions loads from the server's tick archive. Pure: the request guard (one request at a time,
   none once the archive's start is on the chart, a pause after a failure) and the merge of an answer into
   the chart's bars. No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const EDGE = 50;          // bars: the view's left edge this close to the first loaded bar asks for more
const RETRY_MS = 10000;   // after a failed answer, no new request for this long

class ScrollBack {
  constructor({ edge = EDGE, retryMs = RETRY_MS, now = () => Date.now() } = {}) {
    this.edge = edge; this.retryMs = retryMs; this.now = now;
    this.reset();
  }

  /* A new history on the chart: nothing pending, the archive's start not known. */
  reset() { this.pending = null; this.done = false; this.retryAt = 0; }

  /* The request for this visible logical range (the first loaded bar is logical 0): {before: firstMs} when
     the left edge is within `edge` bars of it and nothing holds it back, else null. The caller sends it and
     then calls sent(). */
  want(range, firstMs) {
    if (!range || firstMs == null || this.pending || this.done || this.now() < this.retryAt) return null;
    return range.from <= this.edge ? { before: firstMs } : null;
  }

  sent(req) { this.pending = req; }

  /* An answer: true when it answers the pending request and is to be applied (bars, or the archive's
     start); false when stale (a reload came between) or failed (then a pause before asking again). */
  take(m) {
    if (!this.pending || !m || m.before !== this.pending.before) return false;
    this.pending = null;
    if (m.error) { this.retryAt = this.now() + this.retryMs; return false; }
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

const api = { ScrollBack, prepend, mergeSessions, EDGE, RETRY_MS };
if (typeof window !== 'undefined') window.HBScrollBack = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
