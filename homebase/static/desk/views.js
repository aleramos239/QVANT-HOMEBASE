/* ---- render ---- */
/* A strategy's day status as a pill -- its own look, never the ARMED red or the LIVE tag (S4):
   "live" (a position is open) reads "in position", "placed" (entries resting) "orders working".
   The desk's own word stays in the tooltip. */
const STATUS_PILL = {idle: "pill idle", placing: "pill", placed: "pill", live: "pill inpos",
                     done: "pill idle", error: "pill lost"};
const STATUS_TEXT = {placed: "orders working", live: "in position"};
const dayPill = (st) => `<span class="${STATUS_PILL[st] || "pill idle"}" title="Today: ${st}">${STATUS_TEXT[st] || st}</span>`;

/* ===== Desk views (design/apple-pass): Today · Strategy · Activity =============================
   Presentation of what the desk already reports. Every control below calls the handler the old
   cards called (toggleStrat, flattenStrat, testFire, openRes / openLive, toggleAsgMenu,
   acctRow ...) -- nothing about arming, killing or booking changed. The day, the states and the
   numbers are all read from the status the desk sends. */
let VIEW = {k: "today"};
try {
  const v = JSON.parse(localStorage.getItem("hb_view") || "null");
  if (v && ["today", "strat", "activity", "lab", "group", "archive"].includes(v.k)) VIEW = v;
} catch (_) {}
let SIDE_ALL = false;
/* The sidebar's sections fold (2026-10-09): a header with a chevron hides its rows; what is folded is remembered per browser. */
const SIDE_FOLD_KEY = "hb_side_fold";
let SIDE_FOLD = (() => { try { const v = JSON.parse(localStorage.getItem(SIDE_FOLD_KEY) || "{}"); return v && typeof v === "object" ? v : {}; } catch (_) { return {}; } })();
const sideFolded = (k) => k in SIDE_FOLD ? !!SIDE_FOLD[k] : k === "off";      // Off starts folded; old keys (strat, cyc, f:*) are never read
function toggleSide(k) {
  SIDE_FOLD[k] = !sideFolded(k);
  try { localStorage.setItem(SIDE_FOLD_KEY, JSON.stringify(SIDE_FOLD)); } catch (_) { /* stays for this page */ }
  render();
}
/* ---- LAB STRATEGIES on the Desk (2026-10-09, Step A): drafts promoted from the Lab. Records kept by the chart service
   (:8852, GET /api/tester/desklab). A promoted one lands switched OFF; switched on, the runner hosts it in SHADOW -- it
   writes down its orders and nothing is sent -- and writes a summary of the day. This page only reads them, and switches or removes one by name. The desk
   itself does not know a Lab strategy yet: nothing here calls its /api/strategy, /api/book or /api/strategy-flatten.
   The words and numbers come from desklab.js (DeskLab). */
let DESKLAB = {strategies: [], archived: [], runner: null}, DESKLAB_OK = null, DESKLAB_BUSY = "";   // DESKLAB_OK: null = no read finished yet, false = the last one failed
const DESKLAB_NAME = /^[a-z][a-z0-9_]{1,39}$/;
/* The Lab's "On the Desk" link is /#lab=<name>. It is used once: the address is cleared, so a reload does not open it again. */
function labHashName() {
  try { const m = /^#lab=([a-z][a-z0-9_]{1,39})$/.exec(location.hash); return m ? m[1] : ""; } catch (_) { return ""; }
}
function clearLabHash() {
  try { history.replaceState(null, "", location.pathname + location.search); } catch (_) {}
}
try {
  const n = labHashName();
  if (n) { VIEW = {k: "lab", name: n}; clearLabHash(); }
} catch (_) {}
/* A fault in anything Lab never reaches the desk's own rows: a Lab row or page that throws (or a desklab.js that did not load) is left out. */
function labSafe(make, fallback) {
  try { return make(); } catch (_) { return fallback; }
}
const LAB_FAULT = "The Lab strategies could not be shown.";
/* ONE ROW, NEVER TWO: a chart-service row whose "lab_" + name the Desk itself holds is drawn by the Desk's own rows; until the Desk knows it
   (the Lab side off, or just promoted) this row and labView still draw it, unchanged. */
const labOnDesk = (w) => labSafe(() => DeskLab.onDesk(ST && ST.strategies, w), true);
const labRowsHtml = (rowOf) => labSafe(() => DESKLAB.strategies.filter(w => !labOnDesk(w)).map(w => labSafe(() => rowOf(w), "")).join(""), "");
/* The research beside a Lab strategy: its saved run on the unseen days and the prop sim of its runs (chart service, GET
   /api/tester/desklab/results). Saved runs only: asking runs nothing and reads no test day. The first answer of a service
   takes a few seconds (it scores each run once), so one ask is out at a time; what was shown stays when one fails. */
let DESKRES = {}, DESKRES_BUSY = false;
async function loadDeskRes() {
  if (document.hidden || DESKRES_BUSY) return;
  DESKRES_BUSY = true;
  try {
    const r = await fetch(CHART + "/api/tester/desklab/results");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), next = j && j.results && typeof j.results === "object" ? j.results : {};
    const changed = JSON.stringify(next) !== JSON.stringify(DESKRES);
    DESKRES = next;
    if (changed && ST && !FREEZE) render();
  } catch (_) { /* the chart service does not answer: keep what was shown */ }
  finally { DESKRES_BUSY = false; }
}
async function loadDeskLab() {
  if (document.hidden) return;
  let next, ok = true;
  try {
    const r = await fetch(CHART + "/api/tester/desklab");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    next = {strategies: (Array.isArray(j.strategies) ? j.strategies : []).filter(w => w && DESKLAB_NAME.test(String(w.name))),
            archived: (Array.isArray(j.archived) ? j.archived : []).filter(w => w && DESKLAB_NAME.test(String(w.name))),
            runner: j.runner && typeof j.runner === "object" ? {alive: j.runner.alive === true} : null};
  } catch (_) {
    // the chart service does not answer: its runner is not reachable either, so no strategy is shown as running
    next = {strategies: DESKLAB.strategies, archived: DESKLAB.archived, runner: null}; ok = false;
  }
  const key = (d) => JSON.stringify(d);
  const changed = DESKLAB_OK !== ok || key(next) !== key(DESKLAB);
  DESKLAB = next; DESKLAB_OK = ok;
  if (changed && ST && !FREEZE) render();
}
async function setDeskLab(name, on) {
  if (switchBounced("lab:" + name) || DESKLAB_BUSY) return;      // a double-click is one flip
  DESKLAB_BUSY = name;
  const r = await chartPost("/api/tester/desklab/onoff", {name, on});
  DESKLAB_BUSY = "";
  if (r && r.ok === true && typeof r.enabled === "boolean") {
    const w = DESKLAB.strategies.find(x => x.name === name);
    if (w) w.enabled = r.enabled;
    toast(`${name} ${r.enabled ? "is ON: it runs in shadow." : "is OFF: it does nothing."}`);
  } else toast(`Could not switch ${name}: ${(r && r.detail) || "no answer"}`, 7000);
  if (ST) render();
  loadDeskLab();
}
function deskLabRun(name) {               // the id of its saved run on the unseen days, or null
  const u = DESKRES[name] && DESKRES[name].unseen;
  return u && typeof u.id === "string" ? u.id : null;
}
async function openDeskLabInLab(name) {      // the Lab page, on this strategy -- on "3:1 out-of-sample" with its walk-forward loaded
  // The Mac app turns this link into a tab switch and drops the #strategy part, so the chart service is told first:
  // the Lab page takes the ask when it is shown (in a browser the link itself carries it).
  const res = DESKRES[name], wf = res && res.walkforward === true ? deskLabRun(name) : null;
  await chartPost("/api/tester/desklab/open", wf ? {name, wf} : {name});
  location.href = location.protocol + "//" + location.hostname + ":8852/backtest?v=33#strategy=" + encodeURIComponent(name);
}
/* A built-in Desk strategy (nq930, gc_nfp) has no Lab copy: the tester holds a twin of it (DESKRES[name].twin, read from the chart service),
   so "Open in the Lab" opens that twin, built-in. */
async function openBuiltinInLab(name, withRun) {
  const twin = DESKRES[name] && DESKRES[name].twin;
  if (typeof twin !== "string" || !twin) return;
  const run = withRun ? deskLabRun(name) : null;
  await chartPost("/api/tester/desklab/open", run ? {name: twin, builtin: true, run} : {name: twin, builtin: true});
  location.href = location.protocol + "//" + location.hostname + ":8852/backtest?v=33#builtin=" + encodeURIComponent(twin);
}
/* "Activity ›" on a strategy's or a group's page (openActivity: the Activity page, filtered to it, the last 7 days). */
const actBtn = (who) => `<button class="btn btn-quiet btn-sm act-link" onclick="openActivity(${jsArg(who)})"
  title="Every trade, skip and order of the last 7 days: which account and when">Activity ›</button>`;
function setView(k, name) {
  closeAsgMenus(false);
  VIEW = k === "strat" || k === "lab" || k === "group" ? {k, name} : {k};
  try { localStorage.setItem("hb_view", JSON.stringify(VIEW)); } catch (_) {}
  if (ST) render();
  if (k === "group") loadDeskGroupRes();
  const m = document.querySelector(".app-main");
  if (m) m.scrollTop = 0;
}

