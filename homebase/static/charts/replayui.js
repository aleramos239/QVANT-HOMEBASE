/* Homebase Charts — HBReplayUI: Bar Replay's browser half. The pure protocol AND the practice fill-law
   simulator live in replay.js; this file is the DOM/wiring half -- the toolbar button, the "pick a start"
   cursor, the floating control bar, the dimming overlay, the REPLAY pill, and (Task 2) the PRACTICE Buy/Sell
   block, its lines and its P&L strip -- one more `page.overlays` entry, built and torn down with the chart
   exactly like HBTradeLines' (tradelines.js), plus the ws message routing app.js hands it.

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

function clearSession(cell) {
  savePracticeSession(cell, sessions.get(cell));
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
   follows makes app.js resubscribe live). Otherwise: update the session and let the live Overlay (if the
   chart still has one built) redraw. The chart's accounts are left alone: cell.replay is the refusal. */
function onState(cell, msg) {
  const parsed = R.parseState(msg);
  if (!parsed || !cell) return;
  if (parsed.stopped) { clearSession(cell); return; }
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
  if (msg.op === 'replay_start') { sessions.delete(cell); cell.replay = null; refreshOverlays(cell); }
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
  savePracticeSession(cell, s);
  try { cell.host.send(R.stopOp(cell.id)); } catch (_) { /* the connection is already gone */ }
  sessions.delete(cell);
  cell.replay = null;
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
    clearSession(cell);
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
    clearSession(cell);
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
    // task-1-review.md (Minor): swallow the click outright, on or off a bar -- while armed, nothing else on
    // this chart (a drawing tool, a future click-based control under the pointer) should ever see it.
    e.preventDefault();
    e.stopPropagation();
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
    const jumpErr = mk('span', 'rb-err', 'HH:MM (ET)');   // task-1-review.md (Minor): shown on a bad jump time
    jumpErr.hidden = true;
    jumpErr.setAttribute('role', 'alert');
    jumpRow.append(jumpInput, jumpErr);
    jumpBtn.onclick = () => {
      jumpRow.classList.toggle('open');
      if (jumpRow.classList.contains('open')) { jumpInput.value = ''; jumpErr.hidden = true; jumpInput.focus(); }
    };
    jumpInput.onkeydown = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); jumpRow.classList.remove('open'); return; }
      if (e.key !== 'Enter') return;
      const to = jumpInput.value.trim();
      if (!JUMP_RE.test(to)) { jumpErr.hidden = false; return; }
      jumpErr.hidden = true;
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
    this.buildPractice(s);
    this.refresh(s);
  }

  /* ---- Task 2: the PRACTICE Buy/Sell block, its lines, and the P&L strip -- built only once s.sim exists
     (onState() creates it once cell.tick/cell.pv are known for this session's date). No desk reference. ---- */
  buildPractice(s) {
    if (!s.sim) return;
    const cell = this.cell;
    const block = mk('div', 'lg-trade');
    const tag = mk('span', 'pr-tag', 'PRACTICE');
    const sellBtn = mk('button', 'tr-sell'), sellPx = mk('span', 'tr-px', '—');
    sellBtn.type = 'button';
    sellBtn.append(sellPx, mk('span', 'tr-lbl', 'SELL'));
    sellBtn.onclick = () => placePractice(cell, 'Sell', 'Market', null);
    const mid = mk('div', 'tr-mid'), qty = mk('input');
    qty.type = 'number'; qty.min = '1'; qty.step = '1'; qty.className = 'tr-qty'; qty.value = String(s.qty || 1);
    qty.setAttribute('aria-label', 'Practice quantity');
    qty.onchange = () => {
      const n = Math.max(1, Math.round(Number(qty.value)) || 1);
      qty.value = String(n);
      const sess = sessions.get(cell); if (sess) sess.qty = n;
    };
    mid.appendChild(qty);
    const buyBtn = mk('button', 'tr-buy'), buyPx = mk('span', 'tr-px', '—');
    buyBtn.type = 'button';
    buyBtn.append(buyPx, mk('span', 'tr-lbl', 'BUY'));
    buyBtn.onclick = () => placePractice(cell, 'Buy', 'Market', null);
    block.append(tag, sellBtn, mid, buyBtn);
    cell.el.querySelector('.lg-tradeslot').appendChild(block);
    this.prBlock = block; this.prQty = qty; this.prSellPx = sellPx; this.prBuyPx = buyPx;

    this.prPnl = mk('div', 'replay-pnl');
    cell.el.appendChild(this.prPnl);

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
    this.prBlock.querySelectorAll('.tr-buy, .tr-sell').forEach((b) => { b.disabled = busy; });
    const n = s.sim.tradeCount();
    this.prPnl.textContent = `Practice — Open ${T.usd(s.sim.openPnl(last)) ?? '$0'} · Realized `
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

  destroyPractice() {
    if (this.prDragging && this.prEndDrag) this.prEndDrag();
    if (this.prBlock) this.prBlock.remove();
    if (this.prPnl) this.prPnl.remove();
    if (this.prLayer) this.prLayer.remove();
    if (this.prItems) { for (const it of this.prItems.values()) { try { this.cell.candles.removePriceLine(it.line); } catch (_) { /* chart already gone */ } } }
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
    try { this.cell.candles.detachPrimitive(this.hook); } catch (_) { /* the chart is already being removed */ }
    if (this.pill) this.pill.remove();
    if (this.dim) this.dim.remove();
    if (this.bar) this.bar.remove();
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
  btn.onclick = () => {
    const cell = page.cur();
    if (cell) page.toggleMenu(btn, () => fillMenu(page.openMenu(btn, 'menu-replay'), cell));
  };
}

window.HBReplayUI = { mount, overlay: (cell, pg) => new Overlay(cell, pg), onState, onError, onBarUpdate,
  cellDestroyed, onReconnect, togglePlay, step, disarmPick, guardSymbolChange };
})();
