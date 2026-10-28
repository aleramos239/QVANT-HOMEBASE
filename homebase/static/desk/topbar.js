/* ---- master controls (top bar): ARMED/DISARMED, Arm/Disarm, Kill everything ----
   2026-09-28 (Apple-design audit S2): out of Settings and into the top bar -- always visible, no
   dialog to open, nothing to scroll past. The three handlers are UNCHANGED: the same confirmDlg,
   the same POSTs to the desk's own /api/arm and /api/kill (Arm confirms, Disarm is immediate,
   Kill keeps its confirm). They talk only to the desk itself (ST, refreshed every 2.5 s) -- never
   the CHART service. The nodes are static markup, never rebuilt, so a press, a hold or keyboard
   focus on them survives every repaint. ST == null (the desk not heard from yet): no Arm/Disarm --
   fail closed, never assert a state it doesn't know -- but Kill is always offered (only the desk can
   carry it out; if it doesn't answer, the page says so -- flatten at the broker). While refresh() is
   failing, the last-known state is marked stale (DESK_STALE). */
/* Arm / Disarm believe only the desk's answer (second review): {ok: true, armed: <what was asked>}.
   Anything else -- a refusal (the write guard's 403), a dropped connection, an unreadable answer, a
   desk that says the other thing -- is said. A Disarm that didn't land is the red alert: signals may
   still place real orders. A failed Arm leaves the desk on the safe side, so a toast says it. */
async function setArmed(want) {
  let r, err = null;
  try { r = await post("/api/arm", {armed: want}); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  if (DEMO) return;                        // preview mode: post() already said nothing is sent
  if (!err && r && r.ok === true && r.armed === want) {
    const where = machineWords();
    toast(want ? `Armed${where ? " " + where : ""} — signals now place real orders.` : `Disarmed${where ? " " + where : ""} — dry-run journaling only.`);
    return;
  }
  const why = err ? (err.name === "SyntaxError" ? "the desk's answer was unreadable"
                                               : `the desk didn't answer (${killText(err.message || String(err))})`)
    : !r || typeof r !== "object" ? "the desk's answer was unreadable"
    : r.ok !== true ? `the desk refused it: ${killText(r.error || r.detail)}`
    : `the desk says it is ${r.armed ? "still ARMED" : "disarmed"}`;
  if (want) toast(`NOT armed — ${why}.`, 8000);
  else alertBar(`Disarm NOT confirmed — ${why}. The desk may still be ARMED: press Kill, or disarm again.`);
}
/* "on the SERVER · Chicago, 3 LIVE accounts": which machine a master control acts on, and how many LIVE accounts it reaches
   (isDemoAcct: an unknown account counts as LIVE). Words only -- when Arm / Kill ask does not change. */
function masterReach(ids) {
  try {                                   // never in Kill's way: a words problem leaves the words out, the confirm still runs
    const where = machineWords(), n = ST ? new Set(ids().filter(a => !isDemoAcct(a))).size : null;
    return [where, n == null ? "" : `${n} LIVE account${n === 1 ? "" : "s"}`].filter(Boolean).join(", ");
  } catch (_) { return ""; }
}
/* The Arm/Disarm button is a switch too: a double-click is one flip (switchBounced). Without it, a
   double-clicked Disarm re-paints as Arm under the second click and pops "Arm the desk?". */
async function doArm() {
  if (switchBounced("desk")) return;
  const reach = masterReach(() => Object.values(ST.book || {}).flat().map(r => r && r.account).filter(Boolean));
  if (!await confirmDlg("Arm the desk?",
      `Signals will place REAL bracketed orders on every account assigned in the book${reach ? ` (${reach})` : ""}.`,
      "Arm", false)) return;
  await setArmed(true);
}
async function doDisarm() {
  if (switchBounced("desk")) return;
  await setArmed(false);
}
/* A Kill that did not go through is never silent (review M1): a refusal (e.g. the write guard's
   403 / 415), an unreadable answer, no answer, or an account whose cancel or flatten failed -> a
   red alert that stays until dismissed and says to flatten at the broker. A clean Kill says what it
   did, in words. The call itself is unchanged: POST /api/kill, after the same confirm.

   A Kill in flight is never silent either (second review): "Kill sent — waiting for the desk…" the
   moment it goes out, and no answer within KILL_WAIT_MS escalates to the red alert -- the request
   keeps waiting, and a late answer still reports (a late success takes that alert down). While one
   is in flight, a second hold sends nothing ("Kill already running"), for up to KILL_BUSY_MS: a
   dead connection must not lock Kill out for good. A network failure can come AFTER the request
   reached the desk (which disarms first), so it never says "NOT sent" -- only a desk that answered
   with a refusal certainly did not get it. */
const KILL_WAIT_MS = 6000;
const KILL_BUSY_MS = 30000;
const KILL_SLOW_TEXT = `Kill NOT confirmed — the desk hasn't answered in ${KILL_WAIT_MS / 1000} s. ` +
  "Check the broker and flatten there now.";
let KILL_AT = 0;                 // when the Kill in flight went out; 0: none
const killInFlight = () => KILL_AT > 0 && Date.now() - KILL_AT < KILL_BUSY_MS;
const killText = (v) => (v == null || v === "" ? "no reason given"
  : typeof v === "string" ? v : JSON.stringify(v)).slice(0, 200);
/* Why a desk write did not land, in words -- or "" when the desk answered {ok: true}. A network
   error can come after the desk got the request, so it never claims the write was not sent. */
function answerWhy(r, err) {
  if (err) return err.name === "SyntaxError" ? "the desk's answer was unreadable"
                                             : `the desk didn't answer (${killText(err.message || String(err))})`;
  if (!r || typeof r !== "object") return "the desk's answer was unreadable";
  return r.ok === true ? "" : `the desk refused it: ${killText(r.error || r.detail)}`;
}
function killFailures(results) {
  return Object.entries(results || {}).map(([aid, v]) => {
    const why = [];
    for (const [call, what] of [["flatten_all", "FLATTEN FAILED"], ["cancel_all", "CANCEL FAILED"]]) {
      const x = v && v[call];
      if (!x || x.ok !== true) why.push(`${what}: ${killText(x && x.error)}`);
    }
    return why.length ? `${acctShort(aid)} (${why.join("; ")})` : "";
  }).filter(Boolean);
}
function killReport(r, lateSecs) {
  const late = lateSecs ? ` (the desk answered after ${lateSecs} s)` : "";
  toastHide();
  if (!r || typeof r !== "object")
    return alertBar(`Kill NOT confirmed — the desk's answer was unreadable${late}. Check every account and flatten at the broker now.`);
  if (r.ok !== true)
    return alertBar(`Kill NOT sent — the desk refused it: ${killText(r.error || r.detail)}. Flatten at the broker now.`);
  if (!r.results || typeof r.results !== "object")
    return alertBar(`Kill NOT confirmed — the desk said ok but sent no account results${late}. Check every account and flatten at the broker now.`);
  const bad = killFailures(r.results), n = Object.keys(r.results).length;
  if (bad.length) return alertBar(`Kill FAILED on ${bad.join(" · ")}. Flatten ${bad.length === 1 ? "it" : "them"} at the broker now.`);
  // its "hasn't answered" is no longer true -- but only take down THAT alert, never another failure's
  if (lateSecs && $("#alertText").textContent === KILL_SLOW_TEXT) $("#alertBar").hidden = true;
  toast((n ? `Kill sent — orders cancelled and positions flattened on ${n} account${n === 1 ? "" : "s"}; the desk is disarmed.`
           : "Kill sent — the desk is disarmed (no connected account to flatten).") + late, 6000);
}
/* One account, flat: every working order on it cancelled and every position on it closed. The desk stays
   armed and the strategies stay on; what they had working on this account today is over for today. */
async function flattenAcct(id) {
  const N = acctShort(id);
  if (!await confirmDlg("Flatten " + N + "?",
      "Cancels every working order and market-flattens every position on this account only. The desk stays armed and your strategies stay on. Anything they had working on this account today is over for today.",
      "Flatten account", true)) return;
  let r, err = null;
  try { r = await post("/api/account-flatten", {account: id}); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  if (DEMO) return;
  const why = answerWhy(r, err);
  if (why) return alertBar(`${N} flatten NOT confirmed — ${why}. Check its positions at the broker now.`);
  const bad = r.results && typeof r.results === "object" ? killFailures(r.results) : [`${N} (the desk sent no result)`];
  if (bad.length) return alertBar(`Flatten FAILED on ${bad.join(" · ")}. Flatten it at the broker now.`);
  toast(`${N}: orders cancelled and positions flattened.`);
}
const killRunning = () => toast(`Kill already running — sent ${Math.round((Date.now() - KILL_AT) / 1000)} s ago; ` +
  "waiting for the desk. Nothing more sent.");
async function doKill() {
  if (killInFlight()) return killRunning();
  const reach = masterReach(() => Object.entries(ST.accounts || {}).filter(([, a]) => a && a.connected).map(([id]) => id));
  if (!await confirmDlg("Kill everything?",
      `Cancels every working order and market-flattens every position on EVERY connected account${reach ? ` (${reach})` : ""}, then disarms.`,
      "Kill", true)) { toast("Kill cancelled — nothing sent."); return; }
  if (killInFlight()) return killRunning();
  if (DEMO) { await post("/api/kill"); refresh(); return; }   // preview mode: post() says nothing is sent
  const at = KILL_AT = Date.now();
  let slow = false;
  toast("Kill sent — waiting for the desk…", KILL_BUSY_MS);
  const timer = setTimeout(() => {
    if (KILL_AT !== at) return;
    slow = true;
    toastHide();
    alertBar(KILL_SLOW_TEXT);
  }, KILL_WAIT_MS);
  let r, err = null;
  try { r = await post("/api/kill"); } catch (e) { err = e || new Error("no answer"); }
  clearTimeout(timer);
  if (KILL_AT === at) KILL_AT = 0;
  if (err && err.name !== "SyntaxError") {
    toastHide();
    alertBar(`Kill NOT confirmed — the desk didn't answer (${killText(err.message || String(err))}). ` +
             "Check the broker / flatten there now.");
  } else killReport(err ? null : r, slow ? Math.round((Date.now() - at) / 1000) : 0);   // SyntaxError: unreadable
  refresh();
}

function renderMaster() {
  const pill = $("#statusPill"), arm = $("#armBtn");
  if (!pill || !arm) return;
  if (ST == null) {
    pill.className = "pill idle";
    pill.textContent = DESK_STALE ? "desk unreachable" : "connecting…";
    pill.title = "Desk status unknown — Arm/Disarm show once the desk answers. Kill is still offered, " +
      "but only the desk can carry it out: if it does not answer, flatten at the broker.";
    arm.classList.add("gone");          // fail closed: no Arm/Disarm while the state is unknown --
    arm.disabled = true;                // hidden by visibility, its space kept, so nothing moves Kill
    arm.setAttribute("aria-hidden", "true");
    arm.onclick = null;
    return;
  }
  const armed = !!ST.armed;
  pill.className = (armed ? "pill armed" : "pill idle") + (DESK_STALE ? " stale" : "");
  pill.textContent = (armed ? "ARMED" : "DISARMED") + (DESK_STALE ? " · stale" : "");
  pill.title = (armed ? "ARMED — signals place REAL orders; SL/TP ride broker-side"
                      : "Disarmed — signals are validated and journaled only") +
    (DESK_STALE ? `. Last known state — ${STALE_WHY || "the desk is not answering"}.` : "");
  arm.classList.remove("gone");
  arm.disabled = false;
  arm.removeAttribute("aria-hidden");
  arm.textContent = armed ? "Disarm" : "Arm";
  arm.title = armed ? "Disarm: signals are journaled only" : "Arm: signals place real orders (asks first)";
  arm.onclick = armed ? doDisarm : doArm;
}

/* Press-and-hold: fire() runs once, only after `btn` has been held HOLD_MS without a break -- the
   primary pointer button, or Space/Enter while it has focus. Letting go early, dragging off it,
   pointercancel, the buttons going missing, a context menu, the window losing focus or the page
   hiding all cancel (GOTCHAS: an owned gesture must never stick). A key's auto-repeat (e.repeat)
   never starts, restarts or fires a hold, and a hold that fired needs a fresh press to fire again
   (GOTCHAS: a held key has sent duplicate orders here before). The ring is CSS (.holding fills it
   over --hold-ms); the timer is the truth. onCancel runs when a started hold is let go early.
   A click with no pointer and no key behind it (e.detail 0: VoiceOver / Switch Control, which
   cannot hold) goes straight to fire() -- which for Kill is still its confirm dialog. */
const HOLD_MS = 1000;
function holdToFire(btn, fire, onCancel) {
  let timer = null, by = null;          // by: "pointer", or the key that started the running hold
  btn.style.setProperty("--hold-ms", HOLD_MS + "ms");
  const start = (how) => {
    if (timer) return;
    by = how;
    btn.classList.add("holding");
    timer = setTimeout(() => {
      timer = null; by = null;
      btn.classList.remove("holding");
      fire();
    }, HOLD_MS);
  };
  const cancel = () => {
    if (!timer) return;
    clearTimeout(timer); timer = null; by = null;
    btn.classList.remove("holding");
    if (onCancel) onCancel();
  };
  const holdKey = (e) => e.key === " " || e.key === "Enter";
  btn.addEventListener("pointerdown", (e) => { if (e.button === 0 && e.isPrimary !== false) start("pointer"); });
  btn.addEventListener("pointerup", () => { if (by === "pointer") cancel(); });
  btn.addEventListener("pointerleave", () => { if (by === "pointer") cancel(); });
  btn.addEventListener("pointercancel", cancel);
  btn.addEventListener("pointermove", (e) => { if (by === "pointer" && e.buttons === 0) cancel(); });
  btn.addEventListener("contextmenu", (e) => { e.preventDefault(); cancel(); });
  btn.addEventListener("keydown", (e) => {
    if (!holdKey(e)) return;
    e.preventDefault();                 // never the button's own click (Enter) nor a page scroll (Space)
    if (!e.repeat) start(e.key);        // an auto-repeat never starts, restarts or fires a hold
  });
  btn.addEventListener("keyup", (e) => { if (holdKey(e) && by === e.key) cancel(); });
  btn.addEventListener("click", (e) => { if (e.detail === 0 && !timer) fire(); });
  btn.addEventListener("blur", cancel);
  window.addEventListener("blur", cancel);
  document.addEventListener("visibilitychange", () => { if (document.hidden) cancel(); });
  return {cancel, get holding() { return timer !== null; }};
}
holdToFire($("#killBtn"), doKill,
  () => toast("Kill not sent — press and hold for a second to kill everything."));

/* ---- the bulb ---- */
const CHK_COLOR = {ok: "var(--pos)", info: "var(--muted-foreground)", warn: "var(--warn, oklch(0.7 0.16 70))",
                   bad: "var(--neg)"};   // theme tokens, never hex (W6)
function bulbLevel(r) {
  if (!r) return null;
  if (r.checks.some(c => c.level === "bad")) return "bad";
  if (r.checks.some(c => c.level === "warn")) return "warn";
  return "ok";
}
function renderBulb(r) {
  const b = $("#bulb");
  const lvl = bulbLevel(r);
  b.className = "bulb" + (lvl ? " " + lvl : "");
  const probs = r ? r.checks.filter(c => c.level === "bad" || c.level === "warn") : [];
  b.title = !lvl ? "connecting…" : lvl === "ok" ? "All good — ready to trade"
    : probs.map(c => c.label + ": " + c.detail).join("\n");
  if ($("#checksOverlay").classList.contains("open")) renderChecks();
}
function renderChecks() {
  const r = ST && readinessShown(ST.readiness, ST);
  if (!r) return;
  const lvl = bulbLevel(r);
  $("#bulbBig").className = "bulb" + (lvl ? " " + lvl : "");
  $("#checksTitle").textContent = lvl === "ok" ? "All good — ready to trade"
    : lvl === "warn" ? "Attention" : "Not ready";
  $("#checksList").innerHTML = r.checks.map(c => `
    <div class="chk"><span class="dot" style="background:${CHK_COLOR[c.level] || CHK_COLOR.info}"></span>
      <span class="lbl">${esc(c.label)}</span><span class="det">${esc(c.detail)}</span></div>`).join("");
}
function openChecks() { renderChecks(); showOverlay("checksOverlay"); }
function closeChecks() { hideOverlay("checksOverlay"); }
$("#checksOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeChecks();
});

/* ---- readiness, as the page shows it (W4) ----
   The desk's readiness flags an enabled straddle still idle once its accept window has passed:
   "no signal arrived" (red), or "no signal today" (amber) for a gated one. For a strategy that
   could not have fired today that is a false alarm, so the check is shown as info (grey: out of
   the Not-ready strip, never turning the bulb) with the reason instead -- nothing is dropped:
     - it is not booked on any account;
     - today's fire refused it for having no accounts booked, or for being off;
     - it was switched on only after today's 9:30 fire (its switch's last flip before 9:30 was
       OFF, or -- none in view -- its first flip after 9:30 was ON);
     - it was added after the fire: the timer first saw it after its window (timer_missed) on a
       day the desk did fire at 9:30, with the journal in view reaching back past 9:30.
   The only evidence is the desk's own journal tail (ST.journal, newest first). When that cannot
   show the strategy was out of today's fire, the alarm stands -- fail toward showing. */
const FIRE_AT = "09:30:00";
const IN_THE_FIRE = /^(timer_(fired|gate|skipped|error|deferred)|prestage_)/;
function outOfTodaysFire(name, st) {
  if (!((st.book || {})[name] || []).length) return "not booked on any account — nothing could fire";
  const journal = Array.isArray(st.journal) ? st.journal.filter(r => r && typeof r === "object") : [];
  const today = String(st.et_now || "").slice(0, 10);
  const rows = journal.filter(r => String(r.et || "").slice(0, 10) === today).reverse();   // oldest first
  const at = (r) => String(r.et).slice(11, 19);
  const mine = rows.filter(r => r.strategy === name);
  if (mine.some(r => r.event === "alert_refused" && r.source !== "test" && at(r) >= "09:29:00" &&
                     (r.reason === "no_assignments" || r.reason === "unknown_or_disabled")))
    return "was not booked (or was off) at today's 9:30 fire — nothing was due today";
  const flips = mine.filter(r => r.event === "strategy_toggled");
  const before = flips.filter(r => at(r) <= FIRE_AT), after = flips.filter(r => at(r) > FIRE_AT);
  if (before.length ? before[before.length - 1].enabled === false : (after.length > 0 && after[0].enabled === true))
    return "switched on after today's 9:30 fire — its first run is the next trading day";
  const oldest = String((journal[journal.length - 1] || {}).et || "");
  if (oldest && oldest < today + "T" + FIRE_AT &&
      mine.some(r => r.event === "timer_missed") && !mine.some(r => IN_THE_FIRE.test(r.event)) &&
      rows.some(r => r.event === "timer_fired" && r.strategy !== name))
    return "added after today's 9:30 fire — its first run is the next trading day";
  return "";
}
function readinessShown(r, st) {
  if (!r || !Array.isArray(r.checks) || !st) return r;
  const extra = preopenChecks();
  let changed = false;
  const checks = r.checks.map(c => {
    if (!c || (c.level !== "bad" && c.level !== "warn") || !/^no signal/.test(String(c.detail || ""))
        || !((st.strategies || {})[c.label])) return c;
    const why = outOfTodaysFire(c.label, st);
    if (!why) return c;
    changed = true;
    return {...c, level: "info", detail: why};
  });
  if (!changed && !extra.length) return r;
  const all = checks.concat(extra);
  return {...r, checks: all, ready: !all.some(c => c && c.level === "bad")};
}

/* ---- the pre-open check, in the same list ----
   GET /api/preopen-check is tools/preopen_check.py (read-only: thin candles, depth behind the clock, load, clock, power) as
   the Mac's Desk last ran it. Only its warn and bad rows join the list, as "Pre-open: <name>", and only while the result is
   under 15 minutes old; nothing else about the page's readiness changes. A plain read never starts a run: the page asks for
   one every 5 minutes on weekdays 07:45-09:00 ET (never the minutes before the open), and Settings > Health has a button.
   Where it cannot run (the server) the route says so once and the page stops asking. */
const PREOPEN_FRESH_MS = 15 * 60 * 1000;
function preopenChecks() {
  const p = window.PREOPEN;
  if (!p || !p.available || !Array.isArray(p.checks) || Date.now() - p.got > PREOPEN_FRESH_MS) return [];
  return p.checks.filter(c => c && (c.level === "warn" || c.level === "bad"))
    .map(c => ({level: c.level, label: "Pre-open: " + c.label, detail: c.detail}));
}
function preopenWindow(et) {
  const m = /^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d)/.exec(String(et || ""));
  if (!m) return false;
  const day = new Date(m[1] + "T12:00:00Z").getUTCDay(), min = +m[2] * 60 + +m[3];
  return day >= 1 && day <= 5 && min >= 465 && min < 540;
}
async function loadPreopen(run) {
  if (DEMO) return;
  try {
    const r = await fetch("/api/preopen-check" + (run ? "?run=1" : ""));
    if (!r.ok) return;
    const p = await r.json();
    window.PREOPEN = {...p, got: Date.now() - (p.age_s || 0) * 1000};
  } catch (_) {}
}
function preopenTick() {
  const p = window.PREOPEN;
  if (document.hidden || !preopenWindow(ST && ST.et_now) || (p && p.available === false)) return;
  loadPreopen(!p || !p.available || Date.now() - p.got > 240000);
}

/* ---- the desk's notices ----
   status.notices: one-liners the desk writes for this page, newest first -- e.g. "…049 is no longer
   on your Apex login — removed from the desk". An older desk sends none (absent or not a list:
   nothing shows). Each notice shows once: dismissing marks the ones on screen seen (kept per viewer,
   in this browser), and a seen notice never comes back. Text is escaped. */
let NOTICES_SEEN = new Set();
try { NOTICES_SEEN = new Set(JSON.parse(localStorage.getItem("hb_notices_seen") || "[]")); } catch (_) {}
const noticeKey = (n) => `${n.et || ""}|${n.text}`;
function renderNotices(list) {
  const el = $("#noticeStrip");
  if (!el) return;
  const fresh = (Array.isArray(list) ? list : [])
    .filter(n => n && typeof n.text === "string" && n.text && !NOTICES_SEEN.has(noticeKey(n)));
  const sig = JSON.stringify(fresh.map(noticeKey));
  if (el._sig === sig) return;               // unchanged: leave the nodes alone
  el._sig = sig;
  el.hidden = !fresh.length;
  if (!fresh.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="list">` + fresh.map(n =>
      `<div><span class="t">${esc(hbClock(String(n.et || "").slice(11, 16)))}</span>${esc(n.text)}</div>`).join("") +
    `</div><button type="button" class="x" title="Dismiss — these won't show again" aria-label="Dismiss notices">&times;</button>`;
  el.querySelector("button.x").addEventListener("click", () => {
    for (const n of fresh) NOTICES_SEEN.add(noticeKey(n));
    try { localStorage.setItem("hb_notices_seen", JSON.stringify([...NOTICES_SEEN].slice(-200))); } catch (_) {}
    el.hidden = true; el.innerHTML = ""; el._sig = "[]";
  });
}

