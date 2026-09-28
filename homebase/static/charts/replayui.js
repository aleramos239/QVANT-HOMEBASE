/* Homebase Charts — HBReplayUI: Bar Replay's browser half. The pure protocol AND the practice fill-law
   simulator live in replay.js; this file is the DOM/wiring half -- the toolbar button, the "pick a start"
   cursor, the floating control bar, the dimming overlay, the REPLAY pill, (Task 2) the PRACTICE Buy/Sell
   block, its lines and its P&L strip, and (2026-09-27 ui-controls-and-select-bar plan) Select bar -- one more
   `page.overlays` entry, built and torn down with the chart exactly like HBTradeLines' (tradelines.js), plus
   the ws message routing app.js hands it.

   State: a WeakMap `sessions`, keyed by the Cell instance (stable for its lifetime; a grid rebuild drops the
   whole Cell, so nothing to clean up there beyond telling the server -- see cellDestroyed). A session survives
   the chart being torn down and rebuilt (an indicator change, a time-zone change, a replay `jump`'s fresh
   history): only its `ov` (the live Overlay instance's DOM) is recreated; `date`/`cursorMs`/`speed`/`playing`/
   `done`/`sim`/`feed`/`qty`/`lastPrice` persist and seed the new one.

   Safety (2026-09-27 plan, Global Constraints -- binding): a chart in replay can never send a real order.
   `cell.replay` (cell.js) is the one flag every REAL trading path reads: HBTradeUI.effectiveMode runs it
   through T.replayGuard, which hides the real Buy/Sell block, drops the chart-menu's real trading items and
   makes every real line view-only (no drag, no ×) for that cell. doStart() sets `cell.replay` and
   force-refreshes the chart's overlays BEFORE the server even answers, so there is no gap. It does NOT touch
   the chart's accounts (2026-09-27 accounts-per-chart plan: the accounts ARE the switch, and a replay must
   not throw them away) -- replayGuard alone is what refuses a real order here. The PRACTICE path (Task 2: PracticeSim, its block, lines and menu items below) is a wholly separate
   simulation that never touches the desk at all -- see replay.js's own isolation note and
   tests/js/replay.test.mjs's isolation test, which reads this file's source text for exactly that. */
(() => {
'use strict';
const R = window.HBReplay;

const sessions = new WeakMap();   // Cell -> {pending, ov, date, cursorMs, speed, playing, done}
let page = null;
let armed = null;      // {cell, cleanup()}: "pick a start" mode is on, or null
let selArmed = null;   // {cell, cleanup()}: Select bar (Task 2) is armed on an already-replaying chart, or null
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

/* A practice line's chip suffix: " @ 20,010.25" for anything with a real price, "MKT" for a still-pending
   market entry (its order carries price: null -- it fills at the next print, so there is nothing to show yet),
   nothing for a position (its own text already says "Long 1" etc). */
function practiceChipSuffix(g, tick) {
  if (g.kind === 'position') return '';
  return g.price == null ? ' MKT' : ` @ ${window.HBCatalog.fmtPrice(g.price, tick)}`;
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
  // Select bar ▾'s "Select date…" and "First available date" rows call this while ALREADY replaying --
  // overwriting `sessions` below would otherwise drop that old session's practice trades on the floor
  // (fix round 2, Important 1). Same save every other end-of-session path already makes (clearSession,
  // cellDestroyed), and the same shape of note resetPracticeForRewind gives a rewind past an open position.
  const wasReplaying = !!cell.replay;
  if (wasReplaying) savePracticeSession(cell, sessions.get(cell));
  // set BEFORE the send: effectiveMode reads cell.replay synchronously, so the block/menu/lines are hidden
  // from this instant, not from whenever replay_state happens to arrive (safety: never a gap).
  cell.replay = { date, cursorMs: 0, speed: 'bar', playing: false, done: false };
  // the session carries the same fields (not just `pending`): the `history` answer rebuilds the chart -- and
  // this cell's Overlay with it -- before any replay_state ever arrives, and its first render reads these.
  // sim/feed/lastPrice: Task 2, filled in once by onState() (cell.tick/cell.pv are not known until the
  // history for THIS date has loaded); qty: the practice block's own quantity field, 1 by default.
  sessions.set(cell, { pending: true, ov: null, sim: null, feed: null, lastPrice: null,
    qty: 1, ...cell.replay });
  // M3 (final review): cell.replay is set ABOVE, before the send, so T.replayGuard refuses every real order
  // from this instant -- an exit, a reconnect or a `stopped` before the first replay_state cannot open a gap.
  refreshOverlays(cell);
  cell.host.send(R.startOp(cell.id, date, time));
  if (wasReplaying) cell.note('Practice book reset — new replay session started');
}

/* localStorage.getItem/setItem, each its own try/catch (Global Constraints): the finished practice session
   (if it ever placed a trade) under hb.practice, capped at the last 200. Called from every path that ends a
   session -- clearSession() (exit, symbol/interval change, a dropped connection) and cellDestroyed() (a grid
   rebuild) -- so nothing depends on the user reaching the × specifically. */
function savePracticeSession(cell, s) {
  if (!s || !s.sim || !s.sim.trades.length) return;
  try {
    const root = (cell.shown && cell.shown.root) || cell.cfg.root;
    const session = R.practiceSession(s.date, root, s.sim);
    let existing = null;
    try { existing = JSON.parse(localStorage.getItem(R.PRACTICE_KEY) || 'null'); } catch (_) { existing = null; }
    localStorage.setItem(R.PRACTICE_KEY, JSON.stringify(R.pushPracticeSession(existing, session)));
  } catch (_) { /* storage off: the session just is not logged */ }
}

/* Every end of a session comes through here, saying whether the USER chose it (fix round 1, Important 2): an end
   they did not choose latches the chart until "Resume live trading", and any end makes the next real order
   confirm (HBTradeUI.replayEnded) -- the practice block sat exactly where the real Buy/Sell block reappears. */
/* The user's own Exit (the replay bar's ×): the `stopped` that answers it is theirs, so it ends the session with
   no latch -- only the confirm on the next real order. */
function exitReplay(cell) {
  const s = sessions.get(cell);
  if (s) s.userExit = true;
  cell.host.send(R.stopOp(cell.id));
}
function clearSession(cell, involuntary) {
  if (selArmed && selArmed.cell === cell) disarmSelectBar();
  savePracticeSession(cell, sessions.get(cell));
  sessions.delete(cell);
  cell.replay = null;
  window.HBTradeUI.replayEnded(cell, involuntary);
  refreshOverlays(cell);
}

/* The socket reopened (app.js's connect(), ws.onopen): every cell resubscribes live regardless, and whatever
   replay sessions existed on the OLD connection are gone with it (the server has no record of this one at
   all). Drop our own bookkeeping for them too -- purely local, nothing to send -- so a chart that was mid
   "pending" (replay_start sent, no answer before the drop) does not stay locked out of trading forever. */
function onReconnect(cells) { for (const c of cells) if (sessions.has(c)) clearSession(c, true); }

/* replay_state (parsed by replay.js): `stopped` ends the session locally too (the server's own `reset` that
   follows makes app.js resubscribe live). Otherwise: update the session and let the live Overlay (if the
   chart still has one built) redraw. The chart's accounts are left alone: cell.replay is the refusal. */
function onState(cell, msg) {
  const parsed = R.parseState(msg);
  if (!parsed || !cell) return;
  // `stopped` is the user's own Exit only when this page sent it (the × marks the session); otherwise the
  // server ended it (end of data, a crashed stream, its own reset): involuntary
  if (parsed.stopped) { const was = sessions.get(cell); clearSession(cell, !(was && was.userExit)); return; }
  let s = sessions.get(cell);
  if (!s) { s = { pending: false, ov: null, sim: null, feed: null, lastPrice: null, qty: 1 }; sessions.set(cell, s); }
  s.pending = false;
  s.date = parsed.date; s.cursorMs = parsed.cursorMs; s.speed = parsed.speed; s.playing = parsed.playing; s.done = parsed.done;
  cell.replay = { date: s.date, cursorMs: s.cursorMs, speed: s.speed, playing: s.playing, done: s.done };
  // Task 2: the practice simulator, created once THIS date's history has loaded (cell.tick/cell.pv are only
  // known from here on) -- cell.pv is the single source of truth (homebase/contracts.py, via the server's
  // history payload); R.pointValue() only covers the gap on the off chance it is not set yet.
  if (!s.sim) {
    const root = (cell.shown && cell.shown.root) || cell.cfg.root;
    const pv = cell.pv != null ? cell.pv : R.pointValue(root);
    if (cell.tick > 0 && pv != null) {
      s.sim = new R.PracticeSim(cell.tick, pv);
      s.feed = new R.BarFeed(s.sim);
      const last = cell.bars.length ? cell.bars[cell.bars.length - 1] : null;
      if (last) s.lastPrice = last.c;
    }
  }
  if (s.ov) s.ov.refresh(s);
}

/* replay_error: replay_start refused -> back to live (never entered replay at all); any other op refused
   (replay_ctl on a bad jump time, or the pump reporting a crashed stream just before it stops) -> just show
   the server's text as-is (Global Constraints) and leave the session as it is; the stop path (if any) answers
   its own replay_state{stopped:true}. */
function onError(cell, msg) {
  if (!cell || !msg) return;
  if (msg.op === 'replay_start') {
    sessions.delete(cell); cell.replay = null;
    window.HBTradeUI.replayEnded(cell, true);   // an error end is never the user's choice
    refreshOverlays(cell);
  }
  if (typeof msg.error === 'string') cell.note(msg.error);
}

/* ---- Task 2: practice trading -- feeding the simulator, placing orders, no desk anywhere in this path ---- */
/* Every `update` message for a replaying cell (app.js's ws.onmessage), tagged `replay: true` by the server but
   otherwise the SAME shape cell.onUpdate() already reads: `closed` (bars finished since the last message) and
   `live` (the currently forming one). Historical bars from the initial `history` are never fed -- a user could
   not have traded against ticks that already happened before the practice block existed for this session. */
function onBarUpdate(cell, m) {
  const s = sessions.get(cell);
  if (!s || !s.feed) return;
  for (const b of m.closed || []) s.feed.closedBar(b, b.ms);
  if (m.live) { s.feed.liveBar(m.live, m.live.ms); s.lastPrice = m.live.c; }
  else if (m.closed && m.closed.length) s.lastPrice = m.closed[m.closed.length - 1].c;
  if (s.ov) s.ov.refreshPractice(s);
}

/* The SAME global SL/TP-tick prefs real trading uses (hb_trade_prefs) -- HBTrade.parsePrefs/PREFS_KEY are pure
   (no desk reference: isolation), the desk client just wraps this exact read/write for its own purposes. */
function readPrefs() {
  const T = window.HBTrade;
  try { return T.parsePrefs(localStorage.getItem(T.PREFS_KEY)); } catch (_) { return T.parsePrefs(null); }
}

/* A practice Market (price: null) / Limit / Stop entry, from the block or the chart menu. `side`: 'Buy'/'Sell'. */
function placePractice(cell, side, kind, price) {
  const s = sessions.get(cell);
  if (!s || !s.sim) return;
  const ref = kind === 'Market' ? s.lastPrice : price;
  if (ref == null) return;   // no price yet to size a bracket from (or to fill a limit/stop against)
  const { sl, tp } = window.HBTrade.bracket(side, ref, readPrefs(), cell.tick);
  const o = s.sim.enter(side === 'Buy' ? 1 : -1, kind.toLowerCase(), kind === 'Market' ? null : price, s.qty || 1, sl, tp);
  if (o && s.ov) s.ov.refreshPractice(s);
}
function flattenPractice(cell) {
  const s = sessions.get(cell);
  if (!s || !s.sim || !s.sim.position) return;
  s.sim.flatten();
  if (s.ov) s.ov.refreshPractice(s);
}

/* The chart's right-click menu: Practice Buy/Sell Limit/Stop at the clicked price, only on a replaying cell
   with its own practice simulator up (this covers Task 2's "available from... the chart menu"; the block
   covers Market). Registered once (mount()), like tradeui.js's own 'trading' section -- the two never collide:
   HBTradeUI's items already return [] for a replaying cell (effectiveMode -> T.replayGuard), and these return
   [] for anything else. */
function registerPracticeMenu() {
  window.HBChartMenu.register('trading', (ctx) => {
    const cell = ctx.cell, s = sessions.get(cell);
    if (!cell.replay || !s || !s.sim || ctx.price == null) return [];
    const T = window.HBTrade, q = { last: s.lastPrice, bid: s.lastPrice, ask: s.lastPrice }, qty = s.qty || 1;
    const price = T.roundTick(ctx.price, ctx.tick), out = [];
    // task-2-review.md Minor 3: grey these out the same way the block's own Buy/Sell disable (PracticeSim.enter
    // would refuse them anyway) instead of leaving a silent no-op click.
    const busy = !!s.sim.position || s.sim.orders.some((o) => o.role === 'entry');
    for (const side of ['Buy', 'Sell']) {
      const type = T.inferType(side, price, q);
      if (type) out.push({ text: `Practice: ${T.menuText(side, qty, price, type, ctx.tick)}`,
        disabled: busy, run: () => placePractice(cell, side, type, price) });
    }
    if (s.sim.position) out.push({ text: 'Practice: Flatten', run: () => flattenPractice(cell) });
    return out;
  });
}

/* A cell is about to be destroyed (a grid/layout rebuild): tell the server so its slot frees immediately
   rather than waiting for the whole connection to drop. Best effort -- the socket may already be closed. */
function cellDestroyed(cell) {
  const s = sessions.get(cell);
  if (!s) return;
  if (selArmed && selArmed.cell === cell) disarmSelectBar();
  savePracticeSession(cell, s);
  try { cell.host.send(R.stopOp(cell.id)); } catch (_) { /* the connection is already gone */ }
  sessions.delete(cell);
  cell.replay = null;
  // held by grid position (HBTradeUI.replayDestroyed): a layout load rebuilds from new configs, so a flag on this
  // cell's config alone would be lost; buildGrid re-applies it to the chart that takes this position
  window.HBTradeUI.replayDestroyed(cell);
}

/* A symbol or interval change on a replaying chart (cell.js's update() guard): the server auto-stops a
   replaying chart's stream the moment a plain `sub` arrives for it, so there is nothing to send here --
   only the local bookkeeping needs clearing before the patch that was on hold goes through for real.

   task-1-review.md (Important): page.openDialog() always closes whatever dialog is already open first (its
   own onClose fires before ours ever shows) -- stacking our confirm on top of an open Settings dialog would
   silently fire that dialog's own Cancel/revert before "Leave replay?" is even answered, discarding whatever
   else was unsaved in it. Rather than teach every other dialog to suspend its own onClose while ours is up,
   a change arriving while a dialog is ALREADY open is never asked about a second time: replay just ends
   (the same way it would if the user had answered "Leave replay" here) and a status-bar note says so. */
function guardSymbolChange(cell, patch) {
  if (!page) return;
  if (page.dialogOpen && page.dialogOpen()) {
    clearSession(cell, false);   // the user changed the symbol/interval themselves (and that clears the accounts)
    cell.update(patch);
    if (page.sbNote) page.sbNote('Replay ended — symbol/interval changed');
    return;
  }
  const box = page.openDialog('Leave replay?', 'small');
  box.appendChild(mk('div', 'dlg-text', "Changing the symbol or interval ends this chart's replay."));
  const foot = mk('div', 'dlg-foot'), no = mk('button', 'btn btn-ghost', 'Cancel'), yes = mk('button', 'btn btn-primary', 'Leave replay');
  no.type = 'button'; yes.type = 'button';
  no.onclick = () => page.closeDialog();
  yes.onclick = () => {
    page.setDialogClose(null);
    page.closeDialog();
    clearSession(cell, false);
    cell.update(patch);
  };
  // M1 (final review): the Enter that picked the new symbol / interval opened this dialog; its auto-repeat must
  // not natively click a button here (a held key never answers it), and the default focus is Cancel
  box.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.repeat) e.preventDefault(); });
  foot.append(no, yes);
  box.appendChild(foot);
  no.focus();
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

/* ---- "pick a start": click a point on the selected chart; its bar's ET date + time is the start ----
   The resolution itself (clientX -> a chart-local x -> coordinateToLogical -> the bar) is pure past the DOM
   read, so it lives in replay.js (clampLogical/barAt) -- Select-bar below shares this exact function rather
   than re-resolving its own pick, and also gets `i` back (the resolved bar index) to place its own visual
   marker at the bar's own coordinate, not the raw mouse position. */
function pickBar(cell, clientX) {
  if (!cell.chart || !cell.bars.length) return null;
  const r = cell.box.getBoundingClientRect(), x = clientX - r.left, axisW = cell.chart.priceScale('right').width();
  if (x < 0 || x > cell.box.clientWidth - axisW) return null;   // the price axis: not a pick
  const logical = cell.chart.timeScale().coordinateToLogical(x);
  const i = R.clampLogical(logical, cell.bars.length);
  if (i == null) return null;
  const picked = R.barAt(cell.bars, i);
  return picked && { ...picked, i };
}

/* Bar Replay (2026-09-27 TV-parity plan, Task 1): clicking the toolbar button enters replay with Select bar
   ALREADY ACTIVE -- the vertical blue cutoff line follows the mouse with the future dimmed, exactly like an
   already-replaying chart's own Select-bar (armPointerPick, shared below); a click picks the start bar and
   begins the session (doStart). A small floating bar (buildPreBar) sits under the mouse the whole time so the
   other three ways to start (Select date…, Select random bar, First available date -- fillSelectMenu) are one
   click away without first having to enter a session. Esc: nothing has been picked yet at this point (no
   session exists), so it always fully exits -- matches TV, and there is no "prior cursor" to fall back to. */
function armPick(cell) {
  const mini = buildPreBar(cell);
  const state = armPointerPick(cell, mini.selectBtn, (picked) => doStart(cell, picked.date, picked.time), () => disarmPick());
  armed = { cell, cleanup: () => { state.cleanup(); mini.remove(); } };
}
/* Idempotent: app.js's closeMenu() calls this unconditionally on every close, armed or not. */
function disarmPick() { if (armed) { armed.cleanup(); armed = null; } }

/* The pre-session mini control bar: shown only while armPick's picker is up (no session yet, so the full
   floating control bar -- Overlay.build(), further down -- does not exist to host it). Just "Select bar ▾"
   (fillSelectMenu's own four ways in, reused verbatim from the in-session control bar) and an ×, matching
   how little of TradingView's own bar is meaningful before a start bar is even chosen. */
function buildPreBar(cell) {
  const bar = mk('div', 'replay-bar');
  const selectBtn = mk('button', 'rb-select', 'Select bar');
  selectBtn.type = 'button';
  selectBtn.title = 'Select bar';
  selectBtn.prepend(icon('selectBar'));
  selectBtn.appendChild(icon('chevron'));
  selectBtn.onclick = () => page.toggleMenu(selectBtn, () => fillSelectMenu(page.openMenu(selectBtn, 'menu-replay-select'), cell, selectBtn));
  const xBtn = iconBtn('x', 'Cancel');
  xBtn.onclick = () => disarmPick();
  bar.append(selectBtn, xBtn);
  cell.el.appendChild(bar);
  return { selectBtn, remove: () => bar.remove() };
}

/* Select bar ▾'s four ways in -- TradingView's own dropdown, and the SAME menu whether nothing has started yet
   (buildPreBar's button) or a session is already running (the control bar's own button, Overlay.build()):
     - Select bar: (re-)arm the click-to-pick crosshair -- armPick (cold) or armSelectBar (already replaying).
     - Select date…: the pre-existing typed date/time + calendar popover (fillMenu) -- doStart() either starts
       fresh or, mid-session, restarts at the new date/time (TV's own "select date" behaviour).
     - Select random bar: a uniformly random bar of whatever is on screen right now (this session's own bars
       while replaying -- same-day jump; the live chart's own bars otherwise -- a fresh start there).
     - First available date: the archive's very first session (R.FIRST_DATE), at its own open.
   `anchor`: the button this menu is hanging off of, reused for the "Select date…" popover's own anchor. */
function fillSelectMenu(m, cell, anchor) {
  const row = (name, label, run) => {
    const b = mk('button', 'menu-i', label);
    b.type = 'button';
    b.prepend(icon(name));
    b.onclick = () => { page.closeMenu(); run(); };
    m.appendChild(b);
  };
  row('selectBar', 'Select bar', () => { if (cell.replay) armSelectBar(cell, cell.__rbSelectBtn || null); else armPick(cell); });
  row('calendar', 'Select date…', () => fillMenu(page.openMenu(anchor, 'menu-replay'), cell));
  row('dice', 'Select random bar', () => selectRandomBar(cell));
  row('history', 'First available date', () => doStart(cell, R.FIRST_DATE, '09:30'));
}

/* Select random bar: a uniformly random index of whatever `cell.bars` holds right now (R.randomBarIndex is
   the pure bounds check; Math.random() itself never crosses into replay.js -- isolation is about the desk,
   not about randomness, so this is fine here). Mid-session it is a jump, exactly like a manual Select-bar
   click on that same random bar (R.selectBarPlan's own same-day guard and the position-rewind reset both
   still apply); otherwise it is a fresh start at that bar's own date/time. */
function selectRandomBar(cell) {
  if (!cell.bars || !cell.bars.length) return;
  const i = R.randomBarIndex(cell.bars.length);
  const picked = i == null ? null : R.barAt(cell.bars, i);
  if (!picked) return;
  if (!cell.replay) { doStart(cell, picked.date, picked.time); return; }
  const s = sessions.get(cell);
  if (!s) return;
  const plan = R.selectBarPlan(cell.id, s.date, s.cursorMs, picked);
  if (!plan) { cell.note("Select random bar: only within this replay's own session"); return; }
  if (plan.backward && s.sim && s.sim.position) resetPracticeForRewind(cell, s);
  cell.host.send(plan.op);
}

/* Back one bar: the LAST bar the chart shows is always the cursor's own (pickBar/armSelectBar's convention);
   R.backOnePick resolves the one before it. A jump to it (the same primitive the HH:MM box and Select-bar
   already use) is the only backward primitive barreplay.py has -- there is no true "undo one step", so this
   shares jump's own minute granularity (a sub-minute bar can land back on the SAME minute); omitted (the
   button disables, Overlay.refresh()) rather than faked whenever fewer than two bars exist to step between. */
function backOneBar(cell) {
  const s = sessions.get(cell);
  if (!s || !cell.bars) return;
  const picked = R.backOnePick(cell.bars);
  if (!picked || picked.date !== s.date) return;
  if (s.sim && s.sim.position) resetPracticeForRewind(cell, s);
  cell.host.send(R.ctlOp(cell.id, 'jump', { to_et: picked.time }));
}

/* "Jump to real-time": TradingView's own name for leaving replay and returning to the live feed. The engine
   has exactly one way back to live (barreplay.py's replay_stop, answered by a `reset` the page resubscribes
   live from) -- there is no partial/live-preview state to jump into instead, so this is exitReplay under TV's
   own name and icon, sitting where TV puts it, rather than inventing a third, fake, in-between mode. */
function jumpToRealtime(cell) { exitReplay(cell); }

/* ---- Task 2 (2026-09-27 ui-controls-and-select-bar plan): "Select bar" -- click the exact bar on an
   ALREADY-replaying chart to jump the cursor there, TradingView's own Select bar. Armed from the floating
   control bar's own button (Overlay.build(), below), not from the Replay popover's own armPick() -- the two
   are mutually exclusive on a chart (each disarms the other on entry) but otherwise independent: armPick
   starts a NEW replay from a stopped chart; this jumps an ALREADY-replaying one via replay_ctl's existing
   `jump` -- the SAME op fillMenu's typed date/time (Select bar ▾'s "Select date…") and Select random bar
   send, just resolved by clicking a bar instead.

   Safety: picking is read-only navigation -- the only send here is `plan.op` (a replay_ctl jump); nothing
   here ever touches cell.replay's own on/off, an order, or T.replayGuard's choke point. */

/* One picking chart at a time (mirrors `armed` above): re-arming the SAME cell's button (or a different
   cell's) always starts from a clean slate. */
function disarmSelectBar() { if (selArmed) { selArmed.cleanup(); selArmed = null; } }

/* Reset the practice book after a rewind past an open position -- "a position cannot survive a rewind past
   its own entry" (the brief's own words): a fresh PracticeSim/BarFeed, same tick/pv/costs the session was
   built with (PracticeSim's own defaults, matching how onState() first created it), and a one-line note on
   the chart's legend so it is visible, not just silently true. */
function resetPracticeForRewind(cell, s) {
  if (!s.sim) return;
  s.sim = new R.PracticeSim(s.sim.tick, s.sim.pv);
  s.feed = new R.BarFeed(s.sim);
  cell.note('Practice book reset — rewound past the open position');
  if (s.ov) s.ov.refreshPractice(s);
}

/* The click that commits a pick: R.selectBarPlan decides whether it is reachable at all (same calendar day
   as the one actually replaying -- jump only ever moves within it) and, if so, whether it counts as a
   backward jump. A refused pick (the wrong day, e.g. scroll-back context before the replay's own start)
   leaves picking armed and just says so, exactly like the jump box's own bad-time error does; a good pick
   always disarms, backward or forward. */
function commitSelectBar(cell, picked) {
  const s = sessions.get(cell);
  if (!s) { disarmSelectBar(); return; }
  const plan = R.selectBarPlan(cell.id, s.date, s.cursorMs, picked);
  if (!plan) { cell.note("Select bar: only within this replay's own session"); return; }
  disarmSelectBar();
  if (plan.backward && s.sim && s.sim.position) resetPracticeForRewind(cell, s);
  cell.host.send(plan.op);
}

/* The vertical marker + bar highlight + ET label, all plain DOM appended to cell.el (exactly where
   replay-dim/replay-bar already live -- .panel .chart is `inset: 0`, so a coordinate straight off
   chart.timeScale()/priceScale() needs no further offset). Positioned on every pointermove; hidden over the
   price axis or once nothing resolves. Shared by BOTH picking modes (2026-09-27 TV-parity plan): a cold start
   (armPick, above -- no session yet, `commit` calls doStart) and an already-replaying chart's own Select-bar
   re-pick (armSelectBar, below -- `commit` calls commitSelectBar). `btn` (nullable) gets the '.active' class
   for as long as this stays armed -- the pre-session mini bar's own Select-bar button, or the in-session
   control bar's, or none at all (a fresh armPick has no persistent button of its own to mark). `onEscape` is
   the one thing that differs between the two modes: which module-level `armed`/`selArmed` var Esc clears
   (task-1-review.md Minor: "swallow the click outright" -- e.preventDefault/stopPropagation -- applies to
   BOTH modes exactly alike, since neither should ever let a drawing tool or a future click-based control see
   a picking click). Returns {cleanup} for the caller to fold into its own armed-state bookkeeping (armPick
   also owns a mini bar to tear down; armSelectBar owns nothing extra). */
function armPointerPick(cell, btn, commit, onEscape) {
  disarmPick();
  disarmSelectBar();   // the two picking modes are mutually exclusive on a chart
  if (btn) btn.classList.add('active');
  cell.box.classList.add('replay-pick-on');
  const line = mk('div', 'replay-pick-line');
  const band = mk('div', 'replay-pick-band');
  const label = mk('div', 'replay-pick-label');
  cell.el.append(band, line, label);

  const hide = () => { line.hidden = band.hidden = label.hidden = true; };
  hide();

  const spacing = () => {
    if (!cell.chart) return 6;
    const ts = cell.chart.timeScale(), a = ts.logicalToCoordinate(0), b = ts.logicalToCoordinate(1);
    return (a == null || b == null) ? 6 : Math.abs(b - a);
  };

  /* Resolves + draws in one pass; returns the resolved pick (or null, already hidden) for the click handler. */
  const place = (clientX, clientY) => {
    const picked = pickBar(cell, clientX);
    if (!picked || !cell.chart) { hide(); return null; }
    const cx = cell.chart.timeScale().logicalToCoordinate(picked.i);
    if (cx == null) { hide(); return null; }
    const w = Math.max(1, spacing() * 0.8);
    line.style.left = `${Math.round(cx)}px`;
    band.style.left = `${Math.round(cx - w / 2)}px`;
    band.style.width = `${Math.round(w)}px`;
    line.hidden = band.hidden = false;
    label.textContent = R.fmtPickLabel(picked.date, picked.time);
    label.hidden = false;
    const r = cell.box.getBoundingClientRect(), lx = clientX - r.left, ly = clientY - r.top;
    label.style.left = `${Math.max(2, Math.min(cell.box.clientWidth - label.offsetWidth - 2, lx + 10))}px`;
    label.style.top = `${Math.max(2, ly - 24)}px`;
    return picked;
  };

  const onMove = (e) => place(e.clientX, e.clientY);
  const onLeave = () => hide();
  const onClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const picked = place(e.clientX, e.clientY);
    if (picked) commit(picked);
  };
  const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onEscape(); } };

  cell.box.addEventListener('pointermove', onMove);
  cell.box.addEventListener('pointerleave', onLeave);
  cell.box.addEventListener('click', onClick, true);
  window.addEventListener('keydown', onKey, true);

  return { cleanup: () => {
    if (btn) btn.classList.remove('active');
    cell.box.classList.remove('replay-pick-on');
    cell.box.removeEventListener('pointermove', onMove);
    cell.box.removeEventListener('pointerleave', onLeave);
    cell.box.removeEventListener('click', onClick, true);
    window.removeEventListener('keydown', onKey, true);
    line.remove(); band.remove(); label.remove();
  } };
}

function armSelectBar(cell, btn) {
  selArmed = { cell, ...armPointerPick(cell, btn, (picked) => commitSelectBar(cell, picked), () => disarmSelectBar()) };
}

/* ---- the toolbar button's popover: a date and a time (typed, or picked from the calendar and the quick
   times), or just click the chart. Plain text fields, never <input type="date"> (it fires change on the first
   year digit); the typing help and the messages are replay.js' pure typeDate/tidyDate/startError. ---- */
const QUICK_TIMES = ['08:30', '09:30', '10:00', '15:00'];
function field(label, iconName, placeholder, value) {
  const wrap = mk('label', 'rp-field'), box = mk('span', 'ctl-wrap'), inp = mk('input', 'ctl-in');
  inp.type = 'text'; inp.placeholder = placeholder; inp.value = value;
  inp.autocomplete = 'off'; inp.spellcheck = false; inp.inputMode = 'numeric';
  inp.setAttribute('aria-label', label);
  box.append(icon(iconName), inp);
  wrap.append(mk('span', 'rp-lab', label), box);
  return { wrap, inp };
}
function fillMenu(m, cell) {
  m.classList.add('replay-menu');
  m.appendChild(mk('div', 'menu-h', 'Bar Replay'));
  const today = todayEt(), X = window.HBTester;
  const d = field('Date', 'calendar', 'YYYY-MM-DD', lastPick.date), t = field('Time (ET)', 'clock', 'HH:MM', lastPick.time);
  const fields = mk('div', 'rp-fields');
  fields.append(d.wrap, t.wrap);
  const err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const go = mk('button', 'btn btn-primary', 'Start');
  go.type = 'button';
  let month = (R.tidyDate(lastPick.date) || '').slice(0, 7);
  if (!/^\d{4}-\d{2}$/.test(month)) month = today.slice(0, 7);
  const cal = mk('div', 'tst-cal'), quick = mk('div', 'rp-quick');

  const showErr = (e) => {
    d.inp.removeAttribute('aria-invalid'); t.inp.removeAttribute('aria-invalid');
    err.hidden = !e;
    err.textContent = e ? e.msg : '';
    if (e) (e.field === 'date' ? d.inp : t.inp).setAttribute('aria-invalid', 'true');
  };
  // typing help only when the caret is at the end and a character was added, so editing mid-text and
  // deleting behave exactly as typed
  const assist = (inp, fn) => (e) => {
    if (!e.inputType || !e.inputType.startsWith('insert') || inp.selectionStart !== inp.value.length) return;
    const v = fn(inp.value);
    if (v !== inp.value) inp.value = v;
  };
  d.inp.addEventListener('input', (e) => { assist(d.inp, R.typeDate)(e); if (!err.hidden) showErr(null); syncCal(); });
  t.inp.addEventListener('input', (e) => { assist(t.inp, R.typeTime)(e); if (!err.hidden) showErr(null); drawQuick(); });
  d.inp.addEventListener('blur', () => { d.inp.value = R.tidyDate(d.inp.value); syncCal(); });
  t.inp.addEventListener('blur', () => { t.inp.value = R.tidyTime(t.inp.value); drawQuick(); });

  function syncCal() {
    const v = R.tidyDate(d.inp.value);
    if (/^\d{4}-\d{2}-\d{2}$/.test(v) && v.slice(0, 7) !== month) month = v.slice(0, 7);
    drawCal();
  }
  function drawCal() {
    if (!X) return;
    const g = X.monthGrid(month), picked = R.tidyDate(d.inp.value);
    const head = mk('div', 'tst-cal-head'), prev = mk('button', 'tst-cal-nav'), next = mk('button', 'tst-cal-nav');
    prev.type = next.type = 'button';
    prev.append(icon('chevronLeft')); next.append(icon('chevronRight'));
    prev.setAttribute('aria-label', 'Previous month'); next.setAttribute('aria-label', 'Next month');
    prev.onclick = () => { month = X.shiftMonth(month, -1); drawCal(); };
    next.onclick = () => { month = X.shiftMonth(month, 1); drawCal(); };
    prev.disabled = month <= R.FIRST_DATE.slice(0, 7);
    next.disabled = month >= today.slice(0, 7);
    head.append(prev, mk('span', 'tst-cal-t', g.label), next);
    const grid = mk('div', 'tst-cal-grid');
    for (const w of g.dow) grid.appendChild(mk('span', 'tst-cal-dow', w));
    for (const wk of g.weeks) {
      for (const c of wk) {
        const b = mk('button', 'tst-cal-d' + (c.outside ? ' out' : '') + (c.iso === picked ? ' sel' : '')
          + (c.iso === today ? ' today' : ''), String(c.day));
        b.type = 'button';
        b.disabled = !R.dayOpen(c.iso, today);
        b.setAttribute('aria-label', X.prettyDate(c.iso));
        b.onclick = () => { d.inp.value = c.iso; showErr(null); syncCal(); t.inp.focus(); t.inp.select(); };
        grid.appendChild(b);
      }
    }
    cal.replaceChildren(head, grid);
  }
  function drawQuick() {
    const cur = R.tidyTime(t.inp.value);
    quick.replaceChildren(mk('span', 'rp-quick-l', 'Quick'));
    for (const q of QUICK_TIMES) {
      const b = mk('button', 'rp-chip' + (q === cur ? ' on' : ''), q);
      b.type = 'button';
      b.onclick = () => { t.inp.value = q; showErr(null); drawQuick(); };
      quick.appendChild(b);
    }
  }
  const submit = () => {
    d.inp.value = R.tidyDate(d.inp.value); t.inp.value = R.tidyTime(t.inp.value);
    const date = d.inp.value, time = t.inp.value, e = R.startError(date, time, today);
    if (e || !R.validStart(date, time, today)) {
      showErr(e || { field: 'date', msg: `Date: ${R.FIRST_DATE} to yesterday` });
      (e && e.field === 'time' ? t.inp : d.inp).focus();
      return;
    }
    page.closeMenu();
    doStart(cell, date, time);
  };
  go.onclick = submit;
  const onEnter = (e) => { if (e.key === 'Enter') submit(); };
  d.inp.onkeydown = onEnter;
  t.inp.onkeydown = onEnter;
  const foot = mk('div', 'rp-foot');
  foot.append(mk('div', 'menu-hint', 'or click a point on the selected chart'), go);
  m.append(fields, cal, quick, err, foot);
  drawCal(); drawQuick();
  // no armPick() here (2026-09-27 TV-parity plan): Select bar ▾'s "Select date…" is reached from a state
  // that is already armed (the pre-session mini bar) or already replaying (the control bar) -- this popover
  // is purely the typed path, and does not itself arm chart-click picking.
  d.inp.focus();
  d.inp.select();
}

/* ---- the floating control bar + dimming overlay + REPLAY pill: one page.overlays entry, per chart ---- */
class Hook {   // a primitive that draws nothing, called before every redraw of the price pane (tradelines.js')
  constructor(fn) { this.fn = fn; this.raf = 0; }
  updateAllViews() { if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.fn(); }); }
  paneViews() { return []; }
  detached() { cancelAnimationFrame(this.raf); this.raf = 0; }
}

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

  /* 2026-09-27 TV-parity plan: one TradingView-style control bar -- Select bar ▾ | back/play/forward | Speed ▾
     | the clock | Jump to real-time / × | the merged PRACTICE block (buildPractice, once s.sim exists) --
     dividers (.rb-div) between each group, exactly TV's own rhythm. No separate HH:MM jump box any more
     (Select bar ▾'s own "Select date…" replaces it) and no separate Select-bar icon button (folded into the
     same dropdown) -- both are now fillSelectMenu, shared with the pre-session mini bar (buildPreBar). */
  build(s) {
    const cell = this.cell;
    this.pill = mk('span', 'replay-pill', 'REPLAY');
    cell.el.querySelector('.lg-title').appendChild(this.pill);

    this.dim = mk('div', 'replay-dim');
    cell.el.appendChild(this.dim);

    const bar = mk('div', 'replay-bar');

    const selectBtn = mk('button', 'rb-select', 'Select bar');
    selectBtn.type = 'button';
    selectBtn.title = 'Select bar';
    selectBtn.prepend(icon('selectBar'));
    selectBtn.appendChild(icon('chevron'));
    selectBtn.onclick = () => this.page.toggleMenu(selectBtn, () => fillSelectMenu(this.page.openMenu(selectBtn, 'menu-replay-select'), cell, selectBtn));
    cell.__rbSelectBtn = selectBtn;   // fillSelectMenu's own "Select bar" row re-arms through THIS button

    const backBtn = iconBtn('skipBack', 'Back one bar');
    backBtn.onclick = () => backOneBar(cell);
    const playBtn = iconBtn('play', 'Play');
    playBtn.onclick = () => togglePlay(cell);
    const fwdBtn = iconBtn('skipForward', 'Forward one bar');
    fwdBtn.onclick = () => step(cell);

    const speedBtn = mk('button', 'rb-speed', R.speedLabel(s.speed));
    speedBtn.type = 'button';
    speedBtn.title = 'Speed';
    speedBtn.appendChild(icon('chevron'));
    speedBtn.onclick = () => this.page.toggleMenu(speedBtn, () => this.fillSpeed(this.page.openMenu(speedBtn, 'menu-speed')));

    const time = mk('span', 'rb-time');

    const realtimeBtn = iconBtn('chevronsRight', 'Jump to real-time');
    realtimeBtn.onclick = () => jumpToRealtime(cell);
    const exitBtn = iconBtn('x', 'Exit replay');
    exitBtn.onclick = () => exitReplay(cell);

    bar.append(selectBtn, mk('span', 'rb-div'), backBtn, playBtn, fwdBtn, mk('span', 'rb-div'),
      speedBtn, mk('span', 'rb-div'), time, mk('span', 'rb-div'), realtimeBtn, exitBtn);
    cell.el.appendChild(bar);
    this.bar = bar;
    this.els = { playBtn, backBtn, speedBtn, time };
    s.ov = this;
    this.buildPractice(s);
    this.refresh(s);
  }

  /* ---- Task 2: the PRACTICE Buy/Sell block, its lines, and the P&L strip -- built only once s.sim exists
     (onState() creates it once cell.tick/cell.pv are known for this session's date). No desk reference. ---- */
  /* Task 1 (2026-09-27 TV-parity plan): the PRACTICE Buy/Sell/Flatten block, the qty box and the P&L strip are
     now appended into THIS Overlay's own control bar (this.bar) instead of the chart's legend corner -- one
     merged bar, like TradingView's own replay toolbar. The lines/chips (a separate absolutely-positioned
     layer, unchanged) still live on cell.el since they track price coordinates, not the bar. */
  buildPractice(s) {
    if (!s.sim || this.prBlock) return;
    const cell = this.cell;
    this.bar.append(mk('span', 'rb-div'), mk('span', 'pr-tag', 'PRACTICE'));
    const sellBtn = mk('button', 'rb-side rb-sell'), sellPx = mk('span', 'tr-px', '—');
    sellBtn.type = 'button';
    sellBtn.title = 'Practice: sell at the market';
    sellBtn.append(mk('span', 'tr-lbl', 'SELL'), sellPx);
    sellBtn.onclick = () => placePractice(cell, 'Sell', 'Market', null);
    const qty = mk('input');
    qty.type = 'number'; qty.min = '1'; qty.step = '1'; qty.className = 'rb-qty'; qty.value = String(s.qty || 1);
    qty.setAttribute('aria-label', 'Practice quantity');
    qty.onchange = () => {
      const n = Math.max(1, Math.round(Number(qty.value)) || 1);
      qty.value = String(n);
      const sess = sessions.get(cell); if (sess) sess.qty = n;
    };
    const buyBtn = mk('button', 'rb-side rb-buy'), buyPx = mk('span', 'tr-px', '—');
    buyBtn.type = 'button';
    buyBtn.title = 'Practice: buy at the market';
    buyBtn.append(mk('span', 'tr-lbl', 'BUY'), buyPx);
    buyBtn.onclick = () => placePractice(cell, 'Buy', 'Market', null);
    const flattenBtn = mk('button', 'rb-flatten', 'Flatten');
    flattenBtn.type = 'button';
    flattenBtn.title = 'Practice: close the open position';
    flattenBtn.onclick = () => flattenPractice(cell);
    const pnl = mk('span', 'rb-pnl');
    this.bar.append(sellBtn, qty, buyBtn, flattenBtn, pnl);
    this.prBlock = sellBtn;   // a truthy marker: "the practice block exists" (existing call sites check this)
    this.prQty = qty; this.prSellPx = sellPx; this.prBuyPx = buyPx;
    this.prSellBtn = sellBtn; this.prBuyBtn = buyBtn; this.prFlattenBtn = flattenBtn; this.prPnl = pnl;

    this.prLayer = mk('div', 'tl-layer');
    cell.el.appendChild(this.prLayer);
    this.prItems = new Map();
    this.prDragging = null;
    this.refreshPractice(s);
  }

  /* Called on every replay_state and every bar update (onBarUpdate -> s.ov.refreshPractice) -- the block's
     price, the P&L strip and the lines all follow the last trade as it streams in. */
  refreshPractice(s) {
    if (this.dead || !this.prBlock || !s.sim) return;
    const T = window.HBTrade, Cat = window.HBCatalog, tick = this.cell.tick, last = s.lastPrice;
    const text = last == null ? '—' : Cat.fmtPrice(last, tick);
    this.prSellPx.textContent = text;
    this.prBuyPx.textContent = text;
    // enter() itself refuses a second entry/position (PracticeSim.enter); disabling the buttons here just
    // makes that visible instead of a silent no-op click.
    const busy = !!s.sim.position || s.sim.orders.some((o) => o.role === 'entry');
    this.prSellBtn.disabled = busy;
    this.prBuyBtn.disabled = busy;
    this.prFlattenBtn.disabled = !s.sim.position;
    const n = s.sim.tradeCount();
    this.prPnl.textContent = `Open ${T.usd(s.sim.openPnl(last)) ?? '$0'} · Realized `
      + `${T.usd(s.sim.realizedPnl()) ?? '$0'} · ${n} trade${n === 1 ? '' : 's'}`;
    this.refreshPracticeLines(s);
  }

  practiceColor(g) {
    if (g.kind === 'position') return g.side > 0 ? '#089981' : '#F23645';
    if (g.kind === 'sl') return '#F23645';
    if (g.kind === 'tp') return '#089981';
    return '#F7A600';   // a plain working entry: amber, matching the PRACTICE tag
  }

  buildPracticeChip() {
    const chip = mk('div', 'tl-chip');
    chip.text = mk('span', 'tl-text');
    chip.btn = mk('button', 'tl-x');
    chip.btn.type = 'button';
    chip.btn.setAttribute('aria-label', 'Cancel');
    chip.btn.textContent = '×';
    chip.append(chip.text, chip.btn);
    return chip;
  }

  /* The practice position (if any, view only -- ruling S11's real-trading convention applies here too: a
     position is never draggable) and every working order (draggable by its chip text, × to cancel) --
     Task 2's "Lines: the practice position, orders and SL/TP lines can be dragged; the practice order lines
     have ×." Mirrors tradelines.js's paintLines/buildChip/sync, driven by s.sim instead of the desk. */
  refreshPracticeLines(s) {
    const cell = this.cell, sim = s.sim, seen = new Set(), groups = [];
    if (sim.position) {
      const p = sim.position;
      groups.push({ key: 'pos', kind: 'position', side: p.side, price: p.entryPrice, id: null,
        text: `${p.side > 0 ? 'Long' : 'Short'} ${p.qty}`, editable: false });
    }
    for (const o of sim.orders) {
      if (o.price == null) continue;   // a market order (entry or flatten) rests at no price -- nothing to draw
      const label = o.role === 'sl' ? 'SL' : o.role === 'tp' ? 'TP' : (o.side > 0 ? 'Buy' : 'Sell');
      groups.push({ key: `o${o.id}`, kind: o.role, side: o.side, price: o.price, id: o.id,
        text: `${label} ${o.qty}`, editable: o.role !== 'flat' });
    }
    for (const g of groups) {
      seen.add(g.key);
      if (this.prDragging === g.key) continue;
      let it = this.prItems.get(g.key);
      if (!it) {
        const line = cell.candles.createPriceLine({ price: g.price, color: this.practiceColor(g), lineWidth: 1,
          lineStyle: g.kind === 'position' ? 0 : 2, axisLabelVisible: true, title: '' });
        const chip = this.buildPracticeChip();
        it = { g, line, chip };
        this.prItems.set(g.key, it);
        this.prLayer.appendChild(chip);
      } else {
        it.g = g;
        it.line.applyOptions({ price: g.price, color: this.practiceColor(g) });
      }
      const draggable = g.editable && g.kind !== 'position' && g.price != null;   // a market entry has no price to drag
      it.chip.classList.toggle('drag', draggable);
      it.chip.classList.toggle('view', !draggable);
      it.chip.text.onpointerdown = draggable ? (e) => this.startPracticeDrag(e, g.key) : null;
      it.chip.btn.hidden = !draggable;
      it.chip.btn.onclick = draggable ? () => { sim.cancel(g.id); this.refreshPractice(s); } : null;
      it.chip.text.textContent = g.text + practiceChipSuffix(g, cell.tick);
      it.chip.style.setProperty('--c', this.practiceColor(g));
    }
    for (const [key, it] of [...this.prItems]) {
      if (seen.has(key) || this.prDragging === key) continue;
      cell.candles.removePriceLine(it.line);
      it.chip.remove();
      this.prItems.delete(key);
    }
    this.syncPracticeChips();
  }

  syncPracticeChips() {
    const c = this.cell;
    if (!c.chart || !this.prItems) return;
    const paneH = c.chart.panes()[0].getHeight(), right = c.chart.priceScale('right').width() + 6;
    for (const it of this.prItems.values()) {
      const y = c.candles.priceToCoordinate(it.g.price);
      const off = y == null || y < 0 || y > paneH;
      it.chip.hidden = off;
      if (!off) { it.chip.style.right = `${right}px`; it.chip.style.transform = `translateY(${Math.round(y) - 11}px)`; }
    }
  }

  /* Dragging a working order's chip re-prices it directly (practice: no confirm dialog, no desk send) --
     mirrors tradelines.js's startDrag exactly for the pointer-capture / cancel-on-lost-capture mechanics. */
  startPracticeDrag(e, key) {
    if (e.button !== 0) return;
    if (this.prDragging && this.prEndDrag) this.prEndDrag();
    e.preventDefault(); e.stopPropagation();
    const cell = this.cell, it = this.prItems.get(key), grip = e.currentTarget, from = it.g.price;
    const top = cell.box.getBoundingClientRect().top;
    let price = from, outside = false;
    grip.setPointerCapture(e.pointerId);
    this.prDragging = key;
    const move = (ev) => {
      if (ev.buttons === 0) { lost(); return; }
      const paneH = cell.chart ? cell.chart.panes()[0].getHeight() : 0, y = ev.clientY - top;
      outside = y < 0 || y > paneH;
      if (outside) { this.syncPracticeChips(); return; }
      const raw = cell.candles.coordinateToPrice(y);
      if (raw == null) return;
      price = window.HBDrawings.roundToTick(raw, cell.tick);
      it.g = { ...it.g, price };
      it.line.applyOptions({ price });
      it.chip.text.textContent = it.g.text + ` @ ${window.HBCatalog.fmtPrice(price, cell.tick)}`;   // always a real price mid-drag
      this.syncPracticeChips();
    };
    const end = (commit) => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', lost);
      grip.removeEventListener('lostpointercapture', lost);
      window.removeEventListener('blur', lost);
      this.prDragging = null; this.prEndDrag = null;
      const s = sessions.get(this.cell);
      const changed = window.HBDrawings.roundToTick(price, cell.tick) !== window.HBDrawings.roundToTick(from, cell.tick);
      if (commit && !outside && changed && s && s.sim) {
        const o = s.sim.orders.find((x) => x.id === it.g.id);
        if (o) o.price = window.HBReplay.toTick(price, cell.tick);
      }
      if (s) this.refreshPractice(s);
    };
    const up = () => end(true), lost = () => end(false);
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', lost);
    grip.addEventListener('lostpointercapture', lost);
    window.addEventListener('blur', lost);
    this.prEndDrag = () => end(false);
  }

  /* this.bar (removed wholesale by destroy() just before this runs) carries every practice DOM element now
     (Task 1: merged into the same control bar) -- only the price-line layer and its drag state are its own
     to clean up here. */
  destroyPractice() {
    if (this.prDragging && this.prEndDrag) this.prEndDrag();
    if (this.prLayer) this.prLayer.remove();
    if (this.prItems) { for (const it of this.prItems.values()) { try { this.cell.candles.removePriceLine(it.line); } catch (_) { /* chart already gone */ } } }
  }

  /* TV-style Speed menu (2026-09-27 TV-parity plan): R.SPEED_MENU is SPEEDS TV-ordered (fastest first, "Bar"
     last) -- the SAME engine speeds, just presented the way TradingView's own dropdown lists them. */
  fillSpeed(m) {
    for (const sp of R.SPEED_MENU) {
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
    // "Back one bar" (Task 1): nothing to step back to with fewer than two bars -- disabled, never faked.
    this.els.backBtn.disabled = !this.cell.bars || this.cell.bars.length < 2;
    this.els.speedBtn.replaceChildren(document.createTextNode(R.speedLabel(s.speed)), icon('chevron'));
    // the clock honours the chart's own Time format (HBSettings.clockText via cell.R.timeFormat), like every
    // other time this page prints -- compact, TradingView-style ("Sep 25 '26  09:14 ET" / "...  9:14 AM ET").
    const compact = R.fmtCursorCompact(s.cursorMs), S = window.HBSettings;
    const hm = compact ? (S ? S.clockText(compact.hm, this.cell.R ? this.cell.R.timeFormat : '24h') : compact.hm) : '';
    this.els.time.replaceChildren(mk('span', 'rb-time-d', compact ? compact.date : ''),
      document.createTextNode(compact ? `${hm} ET${s.done ? ' · done' : ''}` : ''));
    this.reposition(s);
    // the practice sim (Task 2) is created by onState() once cell.tick/cell.pv are known, which can be AFTER
    // this Overlay's own build() already ran without it (build() -> onState() -> refresh(), same first pass).
    if (s.sim && !this.prBlock) this.buildPractice(s);
    else if (this.prBlock) this.refreshPractice(s);
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

  onBars() { this.reposition(); this.syncPracticeChips(); }

  destroy() {
    this.dead = true;
    if (selArmed && selArmed.cell === this.cell) disarmSelectBar();   // this Overlay's own button is going away
    try { this.cell.candles.detachPrimitive(this.hook); } catch (_) { /* the chart is already being removed */ }
    if (this.pill) this.pill.remove();
    if (this.dim) this.dim.remove();
    if (this.bar) this.bar.remove();
    delete this.cell.__rbSelectBtn;   // this Overlay's own Select-bar button is gone with the bar above
    this.destroyPractice();
    const s = sessions.get(this.cell);
    if (s && s.ov === this) s.ov = null;
  }
}

/* ---- mount (app.js's init(), like HBTradeUI's) ---- */
function mount(pg) {
  page = pg;
  registerPracticeMenu();
  const btn = document.getElementById('tbReplay');
  if (!btn) return;
  // 2026-09-27 TV-parity plan, Task 1: clicking Bar Replay enters with Select bar already active (armPick),
  // not the old date/time popover first -- matches TradingView's own toolbar button. A second click while
  // already armed disarms (a plain toggle, like every other toolbar button here); a click while a chart is
  // ALREADY replaying does nothing new -- re-picking from there is the control bar's own Select bar ▾.
  btn.onclick = () => {
    if (armed) { disarmPick(); return; }
    const cell = page.cur();
    if (cell && !cell.replay) armPick(cell);
  };
}

window.HBReplayUI = { mount, overlay: (cell, pg) => new Overlay(cell, pg), onState, onError, onBarUpdate,
  cellDestroyed, onReconnect, togglePlay, step, disarmPick, guardSymbolChange, exitReplay, doStart };
})();
