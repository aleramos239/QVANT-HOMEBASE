/* Homebase Charts — HBReplayUI: Bar Replay's browser half (2026-09-27 plan, Task 1). The pure protocol lives in
   replay.js; this file is the toolbar button, the "pick a start" cursor, the floating control bar, the
   dimming overlay and the REPLAY pill -- one more `page.overlays` entry, built and torn down with the chart
   exactly like HBTradeLines' (tradelines.js), plus the ws message routing app.js hands it.

   State: a WeakMap `sessions`, keyed by the Cell instance (stable for its lifetime; a grid rebuild drops the
   whole Cell, so nothing to clean up there beyond telling the server -- see cellDestroyed). A session survives
   the chart being torn down and rebuilt (an indicator change, a time-zone change, a replay `jump`'s fresh
   history): only its `ov` (the live Overlay instance's DOM) is recreated; `date`/`cursorMs`/`speed`/`playing`/
   `done` persist and seed the new one.

   Safety (2026-09-27 plan, Global Constraints -- binding): a chart in replay can never send a real order.
   `cell.replay` (cell.js) is the one flag every trading path reads: HBTradeUI.effectiveMode runs it through
   T.replayGuard, which hides the Buy/Sell block, drops the chart-menu's trading items and makes every line
   view-only (no drag, no ×) for that cell. doStart() sets `cell.replay` and force-refreshes the chart's
   overlays BEFORE the server even answers, so there is no gap; onState() forces the cell's own trade.on off
   the first time a replay actually starts, and it is never turned back on by this module. */
(() => {
'use strict';
const R = window.HBReplay;

const sessions = new WeakMap();   // Cell -> {pending, forcedTrade, ov, date, cursorMs, speed, playing, done}
let page = null;
let armed = null;                 // {cell, cleanup()}: "pick a start" mode is on, or null
let lastPick = { date: '', time: '09:30' };   // remembered for this viewer's next open only, never persisted

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function icon(name) { const s = mk('span', 'icw'); s.innerHTML = window.HBIcons[name] || ''; return s; }
function iconBtn(name, title) {
  const b = mk('button', 'ib');
  b.type = 'button';
  b.title = title;
  b.setAttribute('aria-label', title);
  b.appendChild(icon(name));
  return b;
}

/* Today as an ET "YYYY-MM-DD": the start field's upper bound (today itself is refused server-side as "not a
   completed session"; en-CA gives year-month-day order directly). */
const TODAY_FMT = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' });
function todayEt() { return TODAY_FMT.format(new Date()); }

/* ---- entering / leaving a session ---- */
/* Force every one of this cell's overlays (its trade block among them) to re-render right now, off the usual
   bar-update cadence -- so hiding real trading never waits on the next quote or bar. */
function refreshOverlays(cell) { for (const o of cell.ov) if (o.onBars) o.onBars(); }

function doStart(cell, date, time) {
  if (!cell || !cell.host) return;
  if (!R.validStart(date, time, todayEt())) { cell.note(`date: ${R.FIRST_DATE} to yesterday, time HH:MM (ET)`); return; }
  disarmPick();
  lastPick = { date, time };
  // set BEFORE the send: effectiveMode reads cell.replay synchronously, so the block/menu/lines are hidden
  // from this instant, not from whenever replay_state happens to arrive (safety: never a gap).
  cell.replay = { date, cursorMs: 0, speed: 'bar', playing: false, done: false };
  // the session carries the same fields (not just `pending`): the `history` answer rebuilds the chart -- and
  // this cell's Overlay with it -- before any replay_state ever arrives, and its first render reads these.
  sessions.set(cell, { pending: true, forcedTrade: false, ov: null, ...cell.replay });
  refreshOverlays(cell);
  cell.host.send(R.startOp(cell.id, date, time));
}

function clearSession(cell) {
  sessions.delete(cell);
  cell.replay = null;
  refreshOverlays(cell);
}

/* The socket reopened (app.js's connect(), ws.onopen): every cell resubscribes live regardless, and whatever
   replay sessions existed on the OLD connection are gone with it (the server has no record of this one at
   all). Drop our own bookkeeping for them too -- purely local, nothing to send -- so a chart that was mid
   "pending" (replay_start sent, no answer before the drop) does not stay locked out of trading forever. */
function onReconnect(cells) { for (const c of cells) if (sessions.has(c)) clearSession(c); }

/* replay_state (parsed by replay.js): `stopped` ends the session locally too (the server's own `reset` that
   follows makes app.js resubscribe live). Otherwise: update the session, force trade.on off the first time
   (never back on), and let the live Overlay (if the chart still has one built) redraw. */
function onState(cell, msg) {
  const parsed = R.parseState(msg);
  if (!parsed || !cell) return;
  if (parsed.stopped) { clearSession(cell); return; }
  let s = sessions.get(cell);
  if (!s) { s = { pending: false, forcedTrade: false, ov: null }; sessions.set(cell, s); }
  s.pending = false;
  s.date = parsed.date; s.cursorMs = parsed.cursorMs; s.speed = parsed.speed; s.playing = parsed.playing; s.done = parsed.done;
  cell.replay = { date: s.date, cursorMs: s.cursorMs, speed: s.speed, playing: s.playing, done: s.done };
  if (!s.forcedTrade) {
    s.forcedTrade = true;
    if (cell.cfg.trade && cell.cfg.trade.on) window.HBTradeUI.setCellTrade(cell, { on: false, accounts: cell.cfg.trade.accounts });
  }
  if (s.ov) s.ov.refresh(s);
}

/* replay_error: replay_start refused -> back to live (never entered replay at all); any other op refused
   (replay_ctl on a bad jump time, or the pump reporting a crashed stream just before it stops) -> just show
   the server's text as-is (Global Constraints) and leave the session as it is; the stop path (if any) answers
   its own replay_state{stopped:true}. */
function onError(cell, msg) {
  if (!cell || !msg) return;
  if (msg.op === 'replay_start') { sessions.delete(cell); cell.replay = null; refreshOverlays(cell); }
  if (typeof msg.error === 'string') cell.note(msg.error);
}

/* A cell is about to be destroyed (a grid/layout rebuild): tell the server so its slot frees immediately
   rather than waiting for the whole connection to drop. Best effort -- the socket may already be closed. */
function cellDestroyed(cell) {
  if (!sessions.has(cell)) return;
  try { cell.host.send(R.stopOp(cell.id)); } catch (_) { /* the connection is already gone */ }
  sessions.delete(cell);
  cell.replay = null;
}

/* A symbol or interval change on a replaying chart (cell.js's update() guard): the server auto-stops a
   replaying chart's stream the moment a plain `sub` arrives for it, so there is nothing to send here --
   only the local bookkeeping needs clearing before the patch that was on hold goes through for real. */
function guardSymbolChange(cell, patch) {
  if (!page) return;
  const box = page.openDialog('Leave replay?', 'small');
  box.appendChild(mk('div', 'dlg-text', "Changing the symbol or interval ends this chart's replay."));
  const foot = mk('div', 'dlg-foot'), no = mk('button', 'btn btn-ghost', 'Cancel'), yes = mk('button', 'btn btn-primary', 'Leave replay');
  no.type = 'button'; yes.type = 'button';
  no.onclick = () => page.closeDialog();
  yes.onclick = () => {
    page.setDialogClose(null);
    page.closeDialog();
    clearSession(cell);
    cell.update(patch);
  };
  foot.append(no, yes);
  box.appendChild(foot);
  yes.focus();
}

/* ---- keyboard (app.js's onKey; Space/→ only while the cell is selected and no input is focused) ---- */
function togglePlay(cell) {
  const s = cell && sessions.get(cell);
  if (!s || s.done) return;
  cell.host.send(R.ctlOp(cell.id, s.playing ? 'pause' : 'play'));
}
function step(cell) {
  if (!cell || !sessions.has(cell)) return;
  cell.host.send(R.ctlOp(cell.id, 'step'));
}

/* ---- "pick a start": click a point on the selected chart; its bar's ET date + time is the start ---- */
function pickBar(cell, clientX) {
  if (!cell.chart || !cell.bars.length) return null;
  const r = cell.box.getBoundingClientRect(), x = clientX - r.left, axisW = cell.chart.priceScale('right').width();
  if (x < 0 || x > cell.box.clientWidth - axisW) return null;   // the price axis: not a pick
  const logical = cell.chart.timeScale().coordinateToLogical(x);
  if (logical == null) return null;
  const i = Math.max(0, Math.min(cell.bars.length - 1, Math.round(logical)));
  const b = cell.bars[i];
  if (!b || typeof b.s !== 'string' || !Number.isFinite(b.t)) return null;
  // b.t is already an ET wall-clock second (cell.js's doc comment); b.s is that bar's session date -- exactly
  // what _at() on the server wants, regardless of this chart's own display time zone or bar kind.
  const secs = ((Math.floor(b.t) % 86400) + 86400) % 86400;
  const hh = String(Math.floor(secs / 3600)).padStart(2, '0'), mm = String(Math.floor(secs / 60) % 60).padStart(2, '0');
  return { date: b.s, time: `${hh}:${mm}` };
}

function armPick(cell) {
  disarmPick();
  const box = cell.box;
  box.classList.add('replay-arm');
  const onClick = (e) => {
    const picked = pickBar(cell, e.clientX);
    if (!picked) return;
    if (page) page.closeMenu();   // also disarms (see disarmPick's call site in app.js's closeMenu)
    doStart(cell, picked.date, picked.time);
  };
  box.addEventListener('click', onClick, true);
  armed = { cell, cleanup: () => { box.classList.remove('replay-arm'); box.removeEventListener('click', onClick, true); } };
}
/* Idempotent: app.js's closeMenu() calls this unconditionally on every close, armed or not. */
function disarmPick() { if (armed) { armed.cleanup(); armed = null; } }

/* ---- the toolbar button's popover: type a date + time, or just click the chart ---- */
function fillMenu(m, cell) {
  m.classList.add('replay-menu');
  m.appendChild(mk('div', 'menu-h', 'Bar Replay'));
  const row = mk('div', 'menu-custom');
  const dateInput = mk('input', 'menu-input'), timeInput = mk('input', 'menu-input'), go = mk('button', 'btn btn-primary', 'Start');
  dateInput.type = 'text'; dateInput.placeholder = 'YYYY-MM-DD'; dateInput.value = lastPick.date;
  dateInput.setAttribute('aria-label', 'Start date (ET)');
  timeInput.type = 'text'; timeInput.placeholder = 'HH:MM'; timeInput.value = lastPick.time;
  timeInput.setAttribute('aria-label', 'Start time (ET)');
  go.type = 'button';
  const err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const submit = () => {
    const date = dateInput.value.trim(), time = timeInput.value.trim();
    if (!R.validStart(date, time, todayEt())) {
      err.textContent = `date: ${R.FIRST_DATE} to yesterday, time HH:MM (ET)`;
      err.hidden = false;
      return;
    }
    page.closeMenu();
    doStart(cell, date, time);
  };
  go.onclick = submit;
  const onEnter = (e) => { if (e.key === 'Enter') submit(); };
  dateInput.onkeydown = onEnter;
  timeInput.onkeydown = onEnter;
  row.append(dateInput, timeInput, go);
  m.append(row, err, mk('div', 'menu-hint', 'or click a point on the selected chart'));
  armPick(cell);
  dateInput.focus();
}

/* ---- the floating control bar + dimming overlay + REPLAY pill: one page.overlays entry, per chart ---- */
class Hook {   // a primitive that draws nothing, called before every redraw of the price pane (tradelines.js')
  constructor(fn) { this.fn = fn; this.raf = 0; }
  updateAllViews() { if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.fn(); }); }
  paneViews() { return []; }
  detached() { cancelAnimationFrame(this.raf); this.raf = 0; }
}

const JUMP_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

class Overlay {
  constructor(cell, pg) {
    this.cell = cell; this.page = pg; this.dead = false; this.els = null; this.pill = null; this.dim = null; this.bar = null;
    // tradelines.js's Hook: LWC calls updateAllViews() on every redraw of the price pane (scroll, zoom,
    // autoscale, resize) -- the same one mechanism repositions the dimming overlay on all of those.
    this.hook = new Hook(() => this.reposition());
    cell.candles.attachPrimitive(this.hook);   // built only from Cell.build(), after makeChart(): chart/candles exist
    const s = sessions.get(cell);
    if (s) this.build(s);
  }

  build(s) {
    this.pill = mk('span', 'replay-pill', 'REPLAY');
    this.cell.el.querySelector('.lg-title').appendChild(this.pill);

    this.dim = mk('div', 'replay-dim');
    this.cell.el.appendChild(this.dim);

    const bar = mk('div', 'replay-bar');
    const jumpBtn = iconBtn('skipBack', 'Jump to…');
    const jumpRow = mk('span', 'rb-jump');
    const jumpInput = mk('input');
    jumpInput.type = 'text'; jumpInput.placeholder = 'HH:MM'; jumpInput.setAttribute('aria-label', 'Jump to time (ET)');
    jumpRow.appendChild(jumpInput);
    jumpBtn.onclick = () => {
      jumpRow.classList.toggle('open');
      if (jumpRow.classList.contains('open')) { jumpInput.value = ''; jumpInput.focus(); }
    };
    jumpInput.onkeydown = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); jumpRow.classList.remove('open'); return; }
      if (e.key !== 'Enter') return;
      const to = jumpInput.value.trim();
      if (!JUMP_RE.test(to)) return;
      jumpRow.classList.remove('open');
      this.cell.host.send(R.ctlOp(this.cell.id, 'jump', { to_et: to }));
    };

    const playBtn = iconBtn('play', 'Play');
    playBtn.onclick = () => togglePlay(this.cell);
    const stepBtn = iconBtn('skipForward', 'Step one bar');
    stepBtn.onclick = () => step(this.cell);

    const speedBtn = mk('button', 'rb-speed', R.speedLabel(s.speed));
    speedBtn.type = 'button';
    speedBtn.onclick = () => this.page.toggleMenu(speedBtn, () => this.fillSpeed(this.page.openMenu(speedBtn, 'menu-speed')));

    const time = mk('span', 'rb-time');
    const exitBtn = iconBtn('x', 'Exit replay');
    exitBtn.onclick = () => this.cell.host.send(R.stopOp(this.cell.id));

    bar.append(jumpBtn, jumpRow, playBtn, stepBtn, speedBtn, time, exitBtn);
    this.cell.el.appendChild(bar);
    this.bar = bar;
    this.els = { playBtn, speedBtn, time };
    s.ov = this;
    this.refresh(s);
  }

  fillSpeed(m) {
    for (const sp of R.SPEEDS) {
      const b = mk('button', 'menu-i', R.speedLabel(sp));
      b.type = 'button';
      b.onclick = () => { this.page.closeMenu(); this.cell.host.send(R.ctlOp(this.cell.id, 'speed', { speed: sp })); };
      m.appendChild(b);
    }
  }

  /* Called from onState() on every replay_state -- up to once a second even with no new bar, so the clock and
     the play/pause/speed controls never lag behind the server's own idea of them. */
  refresh(s) {
    if (this.dead || !this.els) return;
    this.els.playBtn.replaceChildren(icon(s.playing ? 'pause' : 'play'));
    this.els.playBtn.title = s.done ? 'Replay finished' : (s.playing ? 'Pause' : 'Play');
    this.els.playBtn.setAttribute('aria-label', this.els.playBtn.title);
    this.els.playBtn.disabled = !!s.done;
    this.els.speedBtn.textContent = R.speedLabel(s.speed);
    this.els.time.textContent = R.fmtCursor(s.cursorMs) + (s.done ? ' · done' : '');
    this.reposition(s);
  }

  /* The dimming overlay: everything right of the cursor (the last/forming bar IS the cursor -- replay feeds
     ticks into the chart's own hub exactly like live, so cell.bars[len-1] is always at r.cursor_ms). */
  reposition(s = sessions.get(this.cell)) {
    if (this.dead || !this.dim) return;
    const cell = this.cell;
    if (!cell.chart || !cell.bars.length || !s) { this.dim.style.display = 'none'; return; }
    const paneW = cell.box.clientWidth - cell.chart.priceScale('right').width();   // cell.js's onMenu(): the plot area
    if (paneW <= 0) { this.dim.style.display = 'none'; return; }
    let x = cell.chart.timeScale().logicalToCoordinate(cell.bars.length - 0.5);
    if (x == null) { this.dim.style.display = 'none'; return; }
    x = Math.max(0, x);
    if (x >= paneW) { this.dim.style.display = 'none'; return; }
    this.dim.style.display = 'block';
    this.dim.style.left = `${x}px`;
    this.dim.style.width = `${paneW - x}px`;
  }

  onBars() { this.reposition(); }

  destroy() {
    this.dead = true;
    try { this.cell.candles.detachPrimitive(this.hook); } catch (_) { /* the chart is already being removed */ }
    if (this.pill) this.pill.remove();
    if (this.dim) this.dim.remove();
    if (this.bar) this.bar.remove();
    const s = sessions.get(this.cell);
    if (s && s.ov === this) s.ov = null;
  }
}

/* ---- mount (app.js's init(), like HBTradeUI's) ---- */
function mount(pg) {
  page = pg;
  const btn = document.getElementById('tbReplay');
  if (!btn) return;
  btn.onclick = () => {
    const cell = page.cur();
    if (cell) page.toggleMenu(btn, () => fillMenu(page.openMenu(btn, 'menu-replay'), cell));
  };
}

window.HBReplayUI = { mount, overlay: (cell, pg) => new Overlay(cell, pg), onState, onError, cellDestroyed,
  onReconnect, togglePlay, step, disarmPick, guardSymbolChange };
})();
