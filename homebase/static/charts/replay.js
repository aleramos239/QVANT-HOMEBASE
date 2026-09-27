/* Homebase Charts — Bar Replay, the pure half (2026-09-27 plan, Task 1): the server's replay_state message
   normalised, the cursor formatted as an ET date + time, the start field's validation window, the speed
   menu's labels, and the three ws op builders (`replay_start` / `replay_ctl` / `replay_stop`). The exact
   message shapes are the protocol's (homebase/charts/barreplay.py) -- see its module docstring. No browser
   globals at load time: the Node tests load this file directly. replayui.js (impure: the toolbar button, the
   floating control bar, the dimming overlay) is the only caller in the browser. */
(function () {
'use strict';

const FIRST_DATE = '2021-09-22';       // the archive's first session (barreplay.py FIRST_DATE)
const SPEEDS = [1, 2, 5, 10, 30, 60, 'bar'];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

const isObj = (v) => v != null && typeof v === 'object';

/* The server's `replay_state` (or the `stopped` one sent on replay_stop), normalised for the UI: {id, date,
   cursorMs, speed, playing, done, stopped}. null for anything that is not an object -- the caller ignores it. */
function parseState(msg) {
  if (!isObj(msg)) return null;
  return {
    id: typeof msg.id === 'string' ? msg.id : (msg.id == null ? '' : String(msg.id)),
    date: typeof msg.date === 'string' ? msg.date : '',
    cursorMs: Number.isFinite(msg.cursor_ms) ? msg.cursor_ms : 0,
    speed: SPEEDS.includes(msg.speed) ? msg.speed : 1,
    playing: msg.playing === true,
    done: msg.done === true,
    stopped: msg.stopped === true,
  };
}

const CURSOR_FMT = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });

/* replay_state's cursor_ms (epoch ms) as "YYYY-MM-DD HH:MM:SS ET" -- the floating control bar's clock. '' for
   anything that is not a finite instant. */
function fmtCursor(ms) {
  if (!Number.isFinite(ms)) return '';
  const p = {};
  for (const x of CURSOR_FMT.formatToParts(new Date(ms))) p[x.type] = x.value;
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second} ET`;
}

/* The start field: date is an archived session (FIRST_DATE to before `today`, both "YYYY-MM-DD" -- plain
   string comparison sorts correctly since the format is fixed-width), time is "HH:MM" in range. Matches the
   server's own check (barreplay.py _parse_start / _at) closely enough to catch a bad field before it goes
   over the wire; the server still re-checks (a session can be missing even inside the window). */
function validStart(date, time, today) {
  if (typeof date !== 'string' || typeof time !== 'string' || typeof today !== 'string') return false;
  if (!DATE_RE.test(date) || !TIME_RE.test(time)) return false;
  return date >= FIRST_DATE && date < today;
}

/* The speed menu's label: "1×" .. "60×", "Bar". */
function speedLabel(s) { return s === 'bar' ? 'Bar' : `${s}×`; }

/* ---- ws op builders (protocol: homebase/charts/barreplay.py) ---- */
/* Starting a replay always begins at speed "bar" (paused, one bar at a time): the floating bar's speed menu
   changes it afterwards through ctlOp('speed', ...). */
function startOp(id, date, startEt) {
  return { op: 'replay_start', id: String(id), date, start_et: startEt, speed: 'bar' };
}
function ctlOp(id, action, extra) {
  return { op: 'replay_ctl', id: String(id), action, ...(extra || {}) };
}
function stopOp(id) {
  return { op: 'replay_stop', id: String(id) };
}

const api = { FIRST_DATE, SPEEDS, parseState, fmtCursor, validStart, speedLabel, startOp, ctlOp, stopOp };
if (typeof window !== 'undefined') window.HBReplay = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
