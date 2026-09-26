/* Homebase Charts — the economic calendar on the charts (ForexFactory's "folders"). Pure: which events a
   chart shows (its Events settings), where their flags go (events at one time, or closer than a flag, share
   one), what a flag's tooltip and the status bar say. No browser globals at load time: the Node tests load
   this file directly. */
(function () {
'use strict';
const S = (typeof window !== 'undefined' && window.HBSettings) || (typeof require === 'function' ? require('./settings.js') : null);
const COLORS = Object.freeze({ High: '#F23645', Medium: '#FF9800', Low: '#F7C600', Holiday: '#9598A1', 'Non-Economic': '#9598A1' });
const RANK = { High: 3, Medium: 2, Low: 1, Holiday: 0, 'Non-Economic': 0 };
const FLAG = 10;   // px: a flag's diameter

/* The events a chart shows: its impact checkboxes (Holiday also covers Non-Economic) and currencies (any case). */
function shown(events, s) {
  const on = { High: s.evHigh, Medium: s.evMedium, Low: s.evLow, Holiday: s.evHoliday, 'Non-Economic': s.evHoliday };
  const cc = new Set((s.evCountries || []).map((c) => String(c).toUpperCase()));
  return (events || []).filter((e) => on[e.impact] && cc.has(String(e.country).toUpperCase()));
}

/* The flags along the time axis, left to right: [{x, t_ms, events, color, line}]. Events at one time share a
   flag, and a flag closer than FLAG px to the previous one joins it (zoomed out). color: the highest impact's;
   line: a High event is in it. xOf(t_ms) -> px | null (null: no place on this chart); off-pane flags go. */
function layout(events, xOf, width) {
  const pts = [];
  for (const e of events) {
    const x = xOf(e.t_ms);
    if (x == null || x < -FLAG / 2 || x > width + FLAG / 2) continue;
    pts.push({ x, e });
  }
  pts.sort((a, b) => a.x - b.x || a.e.t_ms - b.e.t_ms);
  const out = [];
  for (const { x, e } of pts) {
    const g = out[out.length - 1];
    if (g && (e.t_ms === g.t_ms || x - g.x < FLAG)) g.events.push(e);
    else out.push({ x, t_ms: e.t_ms, events: [e] });
  }
  for (const g of out) {
    const top = g.events.reduce((a, b) => ((RANK[b.impact] || 0) > (RANK[a.impact] || 0) ? b : a));
    g.color = COLORS[top.impact] || COLORS.Holiday;
    g.line = g.events.some((e) => e.impact === 'High');
  }
  return out;
}

/* Events within [from, to] (t_ms) out of `events` -- SORTED ascending by t_ms (shown()'s filter keeps the
   calendar's own order, and the calendar is always time-sorted): a binary search for the range's ends,
   O(log n), never a scan of every stored event. The calendar accumulates weeks without bound, so a chart
   asking for its own (small) visible time range must not pay for the whole history on every redraw. from or
   to null: no bound (every event, as before). */
function visibleSlice(events, from, to) {
  if (!events || !events.length || from == null || to == null) return events || [];
  const bound = (t, strict) => {   // first index with t_ms > t (strict) or >= t (not strict)
    let lo = 0, hi = events.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (strict ? events[mid].t_ms <= t : events[mid].t_ms < t) lo = mid + 1; else hi = mid;
    }
    return lo;
  };
  return events.slice(bound(from, false), bound(to, true));
}

/* The flag under a pane point (the flags' centres sit at y): within FLAG / 2 + 2 px. */
function flagAt(flags, pt, y) {
  for (const g of flags) if (Math.hypot(pt.x - g.x, pt.y - y) <= FLAG / 2 + 2) return g;
  return null;
}

const hhmm = (t, tz) => new Date(S.wallSeconds(t, tz) * 1000).toISOString().slice(11, 16);

/* "08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%": the time in the chart's zone (a TIMEZONES value). */
function tipLine(e, tz) {
  return [`${hhmm(e.t_ms, tz)} ${e.title}`, e.country, e.impact, e.forecast ? `forecast ${e.forecast}` : '',
    e.previous ? `prev ${e.previous}` : ''].filter(Boolean).join(' · ');
}
function tipLines(flag, tz) { return flag.events.map((e) => tipLine(e, tz)); }

/* "59m" · "2h 14m" · "1d 3h": the time left, rounded up to the minute (never "0m"). */
function fmtIn(ms) {
  const m = Math.max(1, Math.ceil(ms / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

/* The status bar: the next event among `events` (a chart's shown ones), "Next USD: CPI m/m 08:30 (in 2h 14m)"
   in ET, with its impact's colour; null when none is left within 7 days (the feed holds this week only). */
function nextText(events, nowMs) {
  const next = (events || []).filter((e) => e.t_ms > nowMs && e.t_ms - nowMs <= 7 * 86400000)
    .sort((a, b) => a.t_ms - b.t_ms || (RANK[b.impact] || 0) - (RANK[a.impact] || 0))[0];
  if (!next) return null;
  return { text: `Next ${next.country}: ${next.title} ${hhmm(next.t_ms, 'exchange')} (in ${fmtIn(next.t_ms - nowMs)})`,
    color: COLORS[next.impact] || COLORS.Holiday };
}

const api = { COLORS, FLAG, shown, layout, visibleSlice, flagAt, tipLine, tipLines, fmtIn, nextText };
if (typeof window !== 'undefined') window.HBEvents = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
