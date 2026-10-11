/* One clock format for the whole app (owner 2026-10-10: "make it all the same and have in settings to be able to go
   from normal to military"). '12h' reads 9:30 AM, '24h' reads 09:30. Every page prints a time of day through
   HBClock.text, so the Desk, the Charts and the Lab never disagree.
   The choice is kept by the chart service (GET / PUT /api/settings, `clock`), which all three pages reach, and
   remembered in this page's own storage so the first paint is already right. */
(function () {
  'use strict';
  const KEY = 'hb_clock', FORMATS = ['12h', '24h'];
  let fmt = FORMATS[0], base = null;
  try { const v = localStorage.getItem(KEY); if (FORMATS.includes(v)) fmt = v; } catch (_) { /* storage off */ }
  const subs = new Set();

  function apply(v) {
    if (!FORMATS.includes(v) || v === fmt) return;
    fmt = v;
    try { localStorage.setItem(KEY, v); } catch (_) { /* storage off */ }
    subs.forEach((fn) => { try { fn(v); } catch (_) { /* one listener's fault is its own */ } });
  }

  /* "HH:MM" or "HH:MM:SS" on a 24-hour clock (with or without the leading zero) -> the same time in the chosen
     format. Anything that is not such a time comes back as it was. */
  function text(hms, as) {
    const m = /^(\d{1,2}):(\d{2})(:\d{2})?$/.exec(String(hms == null ? '' : hms));
    if (!m || (as || fmt) !== '12h') return hms;
    const h = Number(m[1]);
    return `${h % 12 || 12}:${m[2]}${m[3] || ''} ${h < 12 ? 'AM' : 'PM'}`;
  }

  /* Every 24-hour time inside a longer line ("2026-10-09 09:31:05", "08:20-15:55 ET") in the chosen format. */
  function within(line, as) {
    if ((as || fmt) !== '12h') return line;
    return String(line == null ? '' : line).replace(/(^|[^\d:])([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(?![\d:])/g,
      (_all, lead, h, mm, ss) => lead + text(`${h}:${mm}${ss || ''}`, '12h'));
  }

  /* Read the kept choice. `chartBase` is '' on the chart service's own pages and its origin on the Desk page. */
  async function load(chartBase) {
    base = chartBase == null ? '' : chartBase;
    try {
      const r = await fetch(base + '/api/settings', { cache: 'no-store' });
      if (r.ok) apply((await r.json()).clock);
    } catch (_) { /* the chart service is not answering: the remembered choice stands */ }
  }

  /* Change it: this page at once, then the kept choice (so the other pages follow). -> whether it was kept. */
  async function set(v) {
    if (!FORMATS.includes(v)) return false;
    apply(v);
    if (base == null) return true;
    try {
      const r = await fetch(base + '/api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ clock: v }) });
      return r.ok;
    } catch (_) { return false; }
  }

  window.HBClock = { FORMATS, get format() { return fmt; }, text, within, load, set, on(fn) { subs.add(fn); return () => subs.delete(fn); } };
  document.addEventListener('visibilitychange', () => { if (!document.hidden && base != null) load(base); });
})();
