  (function(){   // page switcher: plain links built from the host (the Mac app turns a click into a tab switch)
    var sw = document.getElementById('pgSw'); if (!sw) return;
    var base = location.protocol + '//' + location.hostname, V = '?v=33';
    var u = { desk: base + ':8850/', charts: base + ':8852/' + V, backtest: base + ':8852/backtest' + V };
    Array.prototype.forEach.call(sw.querySelectorAll('a[data-page]'), function(a){
      a.href = u[a.getAttribute('data-page')];
      if (a.getAttribute('aria-current') === 'page') a.addEventListener('click', function(e){ e.preventDefault(); });
    });
  })();
const $ = (s) => document.querySelector(s);
let ST = null;
let DESK_STALE = false;   // true while refresh() is failing: ST is the last-known state, not current
let STALE_WHY = "";       // why it is stale, for the pill's tooltip

/* ---- which machine this Desk runs on: ONE value, read at call time -- the native shell's window.HB_MACHINE, else
   /api/status `machine` (ST). Unknown: null and no words. Never guessed from the address: the server's Desk can show as
   localhost (server-window.sh, an ssh -L forward). apple/desk.js machineWord reads the same two, in the same order.
   On 'server' the pages draw no "Open in the Lab" / "Show on chart": the Lab and Charts live on the Mac (owner, 2026-10-26). */
function deskMachine() { return window.HB_MACHINE ?? (ST && ST.machine) ?? null; }
function machineWords() {
  const m = deskMachine();
  return m === "server" ? "on the SERVER · Chicago" : m === "mac" ? "on this Mac" : "";
}
/* The plain top bar's chip says the same; hidden while unknown. The Mac skin hides that bar and shows its own word. */
function renderMachineChip() {
  const m = deskMachine(), el = $("#machineChip");
  if (!el) return;
  el.hidden = m !== "server" && m !== "mac";
  el.textContent = m === "server" ? "Server · Chicago" : m === "mac" ? "This Mac" : "";
  el.className = "pill " + (m === "server" ? "machine-server" : "idle");
  el.title = el.hidden ? "" : "This Desk runs " + machineWords();
}

function toast(msg, ms = 4200) {
  const t = $("#toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
}
function toastHide() {
  const t = $("#toast");
  clearTimeout(t._h); t.classList.remove("show");
}
/* A money-critical failure -- a Kill that did not go through: red, solid, and it stays until the
   user dismisses it (a routine toast never replaces it). */
function alertBar(msg) {
  const b = $("#alertBar");
  $("#alertText").textContent = msg;
  b.hidden = false;
}
$("#alertX").onclick = () => { $("#alertBar").hidden = true; };
async function post(url, body) {
  const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                              body: JSON.stringify(body || {})});
  return r.json();
}
const fmt = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("en-US",
  {minimumFractionDigits: d, maximumFractionDigits: d});
const usd = (v) => v == null ? "—" : (v < 0 ? "-$" : "$") + fmt(Math.abs(v));

/* ---- theme ---- */
$("#themeToggle").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("hb_theme", next); } catch (_) {}
};

/* ---- overlays: one open/close path for every dialog and the + Assign menu (W7) ----
   Every .modal is role="dialog" aria-modal="true" in the markup. showOverlay remembers what had
   focus (the trigger) and moves focus in: the dialog's [data-autofocus] control -- the confirm's
   Cancel, the safe default -- or else the dialog itself. hideOverlay gives focus back to the
   trigger, or to its twin (same onclick) when a 2.5 s re-render has replaced it. Esc closes the
   topmost dialog exactly like its Cancel / × (one layer per press: a held Esc's auto-repeat is
   ignored), and Tab stays inside it. Page-wide, a held Enter/Space never activates a control
   through auto-repeat (GOTCHAS: a held key has sent duplicate orders here before) -- which
   matters more now that focus lands inside a dialog while the key that opened it may still be
   down. The + Assign menu gets Esc, focus in and back, and the arrow keys. Nothing here sends. */
const OVERLAYS = [];   // the open dialogs, topmost last: {el, trigger}
const OVERLAY_CLOSE = {confirmOverlay: () => cfDone(false), labLimitsOverlay: () => closeLabLimits(), settingsOverlay: () => closeSettings(),
  connectOverlay: () => closeConnect(), resOverlay: () => closeRes(), acctOverlay: () => closeAccts(),
  groupOverlay: () => closeGroupMgr(),
  calOverlay: () => closeCal()};
const FOCUSABLE = "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), " +
  "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";
/* Glass pass: a dialog is live the moment it opens (never inert, visible at once -- the motion never
   gates a button), and inert the moment it starts closing: while it fades out nothing in it can be
   focused, pressed or reached by a held key. It grows out of what opened it and shrinks back into
   it (transform-origin at the trigger: the focused control, else what the pointer last pressed). */
let LAST_PRESS = null, LAST_PRESS_AT = 0;
document.addEventListener("pointerdown", (e) => {
  LAST_PRESS = e.target && e.target.closest ? e.target.closest("button, a, [onclick]") : null;
  LAST_PRESS_AT = Date.now();
}, true);
function openedFrom() {
  const a = document.activeElement;
  if (a && a !== document.body && a.getBoundingClientRect) return a;
  return LAST_PRESS && Date.now() - LAST_PRESS_AT < 2000 && document.contains(LAST_PRESS) ? LAST_PRESS : null;
}
function growFrom(box, from) {
  if (!box.style) return;
  if (!from || !from.getBoundingClientRect) { box.style.transformOrigin = ""; return; }   // centre
  const r = from.getBoundingClientRect();
  box.style.transformOrigin = `${Math.round(r.left + r.width / 2 - box.offsetLeft)}px ` +
    `${Math.round(r.top + r.height / 2 - box.offsetTop)}px`;
}
/* A double-click's second half must never act on a dialog it didn't mean to touch. It lands where
   the first half landed -- and a dialog that the first half OPENED can have its primary button
   right there (at narrow widths "Turn on", "Flatten & turn off" and "Book live" sit under the
   switch / button / menu item that opened them), while a dialog that the first half CLOSED leaves
   the page beneath exposed. So for DOUBLE_CLICK_MS after any dialog opens or starts closing, a
   repeat click (detail >= 2) is dropped before it reaches anything. A single, deliberate click
   (detail 1) always goes through at once. */
const DOUBLE_CLICK_MS = 400;
let OVERLAY_OPENED_AT = -Infinity, OVERLAY_CLOSED_AT = -Infinity;
const secondHalf = (e) => e.detail >= 2 && Date.now() - Math.max(OVERLAY_OPENED_AT, OVERLAY_CLOSED_AT) < DOUBLE_CLICK_MS;
/* A pointer click whose press began BEFORE the dialog it lands in opened is not an answer to that
   dialog (second review): a touch hold on Kill ends with the finger lifting over the confirm that
   the hold itself just opened, and the browser's click for that lift would cancel it -- or, over a
   button, answer it. Keyboard clicks (detail 0) are never touched: they have no press. */
const staleGesture = (e) => {
  if (!(e.detail > 0) || !e.target || !e.target.closest) return false;
  const ov = e.target.closest(".overlay.open");
  return !!ov && LAST_PRESS_AT < (ov._openedAt || 0);
};
document.addEventListener("click", (e) => {
  if (secondHalf(e) || staleGesture(e)) { e.preventDefault(); e.stopPropagation(); }
}, true);
// its press must not move focus either (it would pull focus off the dialog's Cancel onto the page)
document.addEventListener("mousedown", (e) => { if (secondHalf(e)) e.preventDefault(); }, true);
function showOverlay(id) {
  const el = $("#" + id);
  if (!el) return;
  OVERLAY_OPENED_AT = Date.now();
  const box = el.querySelector(".modal") || el;
  const fresh = !OVERLAYS.some(o => o.el === el);
  if (fresh) { OVERLAYS.push({el, trigger: document.activeElement}); el._openedAt = Date.now(); }
  document.body.classList.add("dialog-open");                 // the red alert steps under its scrim
  box.removeAttribute("inert");                              // live at once
  if (fresh) growFrom(box, openedFrom());
  el.classList.add("open");
  if (box.contains(document.activeElement)) return;          // already inside (a re-open)
  const first = box.querySelector("[data-autofocus]") || box;
  if (typeof first.focus === "function") first.focus();
}
function hideOverlay(id) {
  const el = $("#" + id);
  if (!el) return;
  OVERLAY_CLOSED_AT = Date.now();
  (el.querySelector(".modal") || el).setAttribute("inert", "");   // inert the moment it starts closing
  el.classList.remove("open");
  const i = OVERLAYS.findIndex(o => o.el === el);
  if (i < 0) return;
  const {trigger} = OVERLAYS.splice(i, 1)[0];
  if (!OVERLAYS.length) document.body.classList.remove("dialog-open");
  const at = document.activeElement;
  if (!at || at === document.body || el.contains(at)) restoreFocus(trigger);   // never steal it
}
function restoreFocus(t) {
  if (!t || t === document.body) return;
  let el = t;
  if (!document.contains(el)) {                              // replaced by a re-render: its twin
    const oc = t.getAttribute && t.getAttribute("onclick");
    el = oc ? [...document.querySelectorAll("[onclick]")].find(x => x.getAttribute("onclick") === oc) : null;
  }
  if (el && typeof el.focus === "function") el.focus();
}
function trapTab(e, overlay) {
  const box = overlay.querySelector(".modal") || overlay;
  const f = [...box.querySelectorAll(FOCUSABLE)].filter(x => x.offsetParent !== null);
  const at = document.activeElement;
  if (!f.length) { e.preventDefault(); box.focus(); return; }
  const first = f[0], last = f[f.length - 1];
  if (!box.contains(at) || at === box) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
  else if (e.shiftKey && at === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
}
const ACTIVATES = "button, a[href], [role='button'], [role='menuitem']";
document.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.repeat) {
    if (e.target && e.target.closest && e.target.closest(ACTIVATES)) e.preventDefault();
    return;                                                  // a held key never re-activates a control
  }
  const top = OVERLAYS.length ? OVERLAYS[OVERLAYS.length - 1] : null;
  if (e.key === "Escape") {
    if (e.repeat) { e.preventDefault(); return; }            // one layer per press
    if (top) { e.preventDefault(); (OVERLAY_CLOSE[top.el.id] || (() => hideOverlay(top.el.id)))(); }
    return;
  }
  if (e.key === "Tab" && top) { trapTab(e, top.el); return; }
}, true);   // capture: ahead of any control's own key handling

/* ---- confirmation popup (every consequential action asks here; Kill is also a hold first) ---- */
let CONFIRM_CB = null;
function confirmDlg(title, body, action, destructive, text) {      // text (a string): also asks for one line, and resolves to it ("" or false = cancelled)
  return new Promise((res) => {
    $("#cfTitle").textContent = title;
    $("#cfBody").textContent = body;
    const inp = $("#cfInput");
    inp.hidden = typeof text !== "string"; inp.value = typeof text === "string" ? text : "";
    const b = $("#cfGo");
    b.textContent = action || "Confirm";
    b.className = "btn " + (destructive ? "btn-destructive" : "btn-default");
    CONFIRM_CB = res;
    showOverlay("confirmOverlay");   // focus lands on Cancel, the safe default (on the field when it asks for one)
    if (!inp.hidden) setTimeout(() => { inp.focus(); inp.select(); }, 50);
  });
}
/* The desk's ONE confirm policy for every switch (S6): ask only when a flip turns ON something that can place
   orders; never when it makes things safer (OFF, Disarm) or when a shadow strategy has nothing to trade. */
function needsConfirm(kind, turningOn, opts) {
  return !!turningOn && !(kind === "strategy" && opts && opts.shadow);
}
/* A double-click on a switch is one flip, never two (review): a second click on the same switch
   within DOUBLE_CLICK_MS is ignored -- so a double-clicked ON strategy turns OFF once (OFF never
   asks) and never pops a "Turn ON?" right after, and a double-clicked OFF one asks once. */
const SWITCH_AT = {};
function switchBounced(key) {
  const now = Date.now(), last = SWITCH_AT[key] === undefined ? -Infinity : SWITCH_AT[key];
  SWITCH_AT[key] = now;
  return now - last < DOUBLE_CLICK_MS;
}
function cfDone(v) {
  const inp = $("#cfInput");
  if (v === true && !inp.hidden) v = inp.value.trim();
  inp.hidden = true;
  hideOverlay("confirmOverlay");
  const cb = CONFIRM_CB; CONFIRM_CB = null;
  if (cb) cb(v);
}
$("#confirmOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) cfDone(false);
});

