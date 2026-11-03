/* ---- paper accounts (2026-09-27 Task 2b) ----
   Paper accounts live in the CHART service (:8852), not in this desk: its books fill on the live prices and never
   reach a broker. This page only asks it -- GET /api/paper/accounts, POST /api/paper/accounts/{create|remove}, the
   one set of chart-service routes that answers this page's origin (exact-origin CORS). Nothing here touches the
   desk's own API. Names are user text: always escaped before they reach innerHTML. */
const CHART = location.protocol + "//" + location.hostname + ":8852";
let PAPER = [], PAPER_BROKEN = "";
const PAPER_ID_RE = /^paper(?:-[1-9][0-9]{0,5})?$/;   // the chart service's id rule: nothing else is ever rendered
const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g,
  (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
/* A value as a JavaScript string literal inside an onclick="..." attribute: JSON makes it a string
   literal JS can't break out of, esc() keeps the HTML attribute intact (esc alone is not enough --
   the browser decodes &#39; back to ' before the JS runs). Account ids and names come from the
   broker, so every inline handler that carries one uses this. */
const jsArg = (v) => esc(JSON.stringify(String(v == null ? "" : v)));
async function chartPost(path, body) {
  try {
    const r = await fetch(CHART + path, {method: "POST", headers: {"Content-Type": "application/json"},
                                         body: JSON.stringify(body || {})});
    try { return await r.json(); } catch (_) { return {ok: false, detail: "HTTP " + r.status}; }
  } catch (_) { return {ok: false, detail: "the chart service (:8852) is not reachable"}; }
}
function wizPaper() {
  for (const i of [1, 2, 3, 4]) $("#wstep" + i).style.display = "none";
  $("#wstepP").style.display = "";
  $("#pErr").style.display = "none";
  $("#pName").value = ""; $("#pBal").value = "50000";
  $("#pName").focus();
}
async function addPaper() {
  const name = $("#pName").value.trim();
  const bal = Number(String($("#pBal").value).replace(/[$,\s]/g, ""));
  const err = (t) => { const e = $("#pErr"); e.textContent = t; e.style.display = ""; };
  if (!name) return err("Give it a name.");
  if (!(bal >= 1000 && bal <= 10000000)) return err("Starting balance: $1,000 to $10,000,000.");
  const btn = $("#pGo"); btn.disabled = true; btn.textContent = "Adding…";
  try {
    const r = await chartPost("/api/paper/accounts/create", {name, start_balance: bal});
    if (r.ok) { toast("Paper account " + r.account.label + " added — pick it in a chart's ⚙ → Trading.", 6000); closeConnect(); loadPaper(); }
    else err(r.detail || r.error || "refused");
  } finally { btn.disabled = false; btn.textContent = "Add paper account"; }
}
async function loadPaper() {
  try {
    const r = await fetch(CHART + "/api/paper/accounts");
    const d = await r.json().catch(() => ({}));
    // only rows with a valid paper id are kept: the id reaches a button's data attribute (fix round 1, M3)
    PAPER = r.ok ? (d.accounts || []).filter(a => a && PAPER_ID_RE.test(String(a.id))) : [];
    PAPER_BROKEN = r.ok ? String(d.broken || "") : "";
    renderPaper(r.ok ? "" : (d.detail || "chart service answered HTTP " + r.status));
  } catch (_) { PAPER = []; renderPaper("the chart service (:8852) is not reachable"); }
}
function paperRow(a) {
  const pnl = a.realized_pnl;
  return `<div class="acct paper-row" style="padding:7px 0">
    <span class="dot on" style="width:7px;height:7px"></span>
    <span class="nm" style="font-size:13px">${esc(a.label)}</span>
    <span class="pill paper" style="font-size:10px">PAPER</span>
    <span class="spacer"></span>
    <span class="kvi">${usd(a.balance)}</span>
    <span class="kvi ${pnl > 0 ? "pos" : pnl < 0 ? "neg" : ""}">${pnl > 0 ? "+" : ""}${usd(pnl)}</span>
    ${a.removable ? `<button class="paper-rm" style="border:none;background:none;color:var(--muted-foreground);cursor:pointer;padding:2px 4px;display:inline-flex"
      data-paper-id="${esc(a.id)}" title="Remove this paper account" aria-label="Remove this paper account"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="#ic-trash"/></svg></button>` : ""}
  </div>`;
}
function renderPaper(why) {
  const el = $("#paperList");
  if (!el) return;
  el.innerHTML = `<div class="slabel" style="margin-top:14px">PAPER ACCOUNTS</div>` +
    (PAPER_BROKEN ? `<div class="mcap" style="padding:6px 0;color:var(--destructive)">${esc(PAPER_BROKEN)}</div>` : "") +
    (PAPER.length ? PAPER.map(paperRow).join("")
      : `<div class="mcap" style="padding:10px 0">${esc(why || "none")}</div>`);
  // Remove is wired here, never through an inline handler: an id never becomes JavaScript source (fix round 1, M3)
  for (const b of el.querySelectorAll ? el.querySelectorAll("button.paper-rm") : []) {
    b.addEventListener("click", () => removePaper(b.dataset.paperId));
  }
}
async function removePaper(id) {
  const a = PAPER.find(x => x.id === id && PAPER_ID_RE.test(String(id)));
  if (!a) return;
  closeAccts();
  if (!await confirmDlg("Remove paper account " + a.label + "?",
      "Its history is archived, not deleted. Refused while it has an open position or working orders — flatten it first.",
      "Remove", true)) return;
  const r = await chartPost("/api/paper/accounts/remove", {account: id});
  toast(r.ok ? a.label + " removed — its history is archived." : "Refused — " + (r.detail || r.error || "unknown"), 6000);
  loadPaper();
}

/* ---- Settings (2026-09-27 desk-settings plan; fix round 1; 2026-09-28 master controls out) ----
   Moved here from the charts page, per the user's call. GET/PUT /api/settings and GET /api/status
   live in the CHART service (:8852) -- this page only asks it, over the same exact-origin CORS
   the paper-account routes above already use (charts/paperbook.py's DESK_ORIGINS, now shared by
   charts/server.py's /api/settings and /api/status too). No native dialogs: this page's own
   overlay/modal pattern. Two sections, CHART TRADING first, each with its OWN container
   (#settingsTrading / #settingsMarketData) so a rebuild of one never touches the other's nodes
   (GOTCHAS: never rebuild a container that might have focus -- patch in place). CHART TRADING is
   built ONCE and only ever patched in place (renderChartTrading): a click or keyboard focus in it
   survives every repaint from render()'s 2.5s ST refresh and loadChartStatus's own poll.
   Arm/Disarm/Kill left this dialog for the top bar (2026-09-28, "master controls" above); the
   section says where they went, so nobody hunts for them here. */
let tradingEls = null;   // built once into #settingsTrading; never rebuilt after that
function buildTrading() {
  if (tradingEls) return tradingEls;
  const root = $("#settingsTrading");
  if (!root) return null;
  root.innerHTML = `
    <div class="slabel">CHART TRADING</div>
    <p class="wnote" style="margin-top:0">Turn ON / OFF and Kill everything are in the top bar.</p>
    <div class="acct" style="padding:4px 0;gap:12px;flex-wrap:wrap">
      <button class="switch" id="ctSwitch" role="switch" aria-label="Chart trading" aria-checked="false"
        title="OFF — the chart page cannot trade"></button>
      <span class="nm" id="ctState" style="font-size:13px">Off</span>
    </div>
    <p class="wnote" id="ctAccts"></p>
    <p class="wnote">Checked on every chart order: at least 1 contract; at most 5 actions a second on an account; the account connected and on its own broker account; stops, targets and limits on the right side of the price; a bot's symbol is locked while the bot works.</p>
    <p class="wnote">Not limited: contracts per order or held, trades a day, the day-lock (those bind the bots only).</p>
    <p class="wnote">With it OFF, new orders are refused; cancel, flatten and protective exits still work.</p>`;
  tradingEls = {sw: $("#ctSwitch")};
  // The switch's handler -- wired here, not at page load (the id exists only once Settings has been opened).
  // The old hidden limit inputs are gone: no order path reads the per-order / per-position limits.
  $("#ctSwitch").onclick = () =>
    setChartTrading(!(ST && ST.chart_trading && ST.chart_trading.enabled));
  return tradingEls;
}

/* Chart trading (orders from the chart page; the desk decides) -- patched in place, and guarded
   for the (common) case Settings has never been opened yet: render() calls this on every 2.5s ST
   refresh whether or not the dialog is open, so it must never throw before buildTrading() has run
   once. */
function renderChartTrading(ct) {
  const sw = $("#ctSwitch");
  if (!sw || !ct) return;   // not yet built (Settings never opened), or no chart_trading in ST
  sw.setAttribute("aria-checked", String(!!ct.enabled));
  sw.title = ct.enabled ? "ON — the chart page can place real orders"
                        : "OFF — the chart page cannot trade";
  $("#ctState").textContent = ct.enabled ? "On — the chart page can place orders" : "Off";
  const on = Object.values((ST && ST.accounts) || {}).filter(a => a && a.connected).map(a => `${a.label} (${a.env})`);
  $("#ctAccts").textContent = (on.length ? "Connected broker accounts: " + on.join(" · ") + "." : "No broker account is connected.")
    + " Each chart uses the ones ticked on it.";
}
async function setChartTrading(enabled) {
  if (switchBounced("chartTrading")) return;         // a double-click is one flip
  const where = machineWords();                       // "on the SERVER · Chicago" / "on this Mac" / "" (unknown)
  if (needsConfirm("chartTrading", enabled) && !await confirmDlg("Turn chart trading ON?",
      `Chart pages${where ? " " + where : ""} can then place REAL orders on the accounts you tick there. The desk sets no size limit (a chart's order panel stops at 1000 contracts), no daily trade cap and no day-lock: those bind the bots only. A bot's symbol stays locked on its accounts while the bot is working. Kill turns it off.`,
      "Turn on", false)) { refresh(); return; }
  try {
    const r = await post("/api/chart-trading", {enabled});
    toast(r.ok ? (enabled ? "Chart trading is ON." : "Chart trading is OFF.")
               : "Refused — " + (r.detail || r.error || "unknown"), 5000);
  } catch (e) {
    toast("Couldn't reach the desk", 5000);
  }
  refresh();
}

const MD_CHOICES = [
  {value: "live", label: "Live"},
  {value: "demo", label: "Apex (demo)"},
];
let MD = null;            // {md, accounts} from GET /api/settings, once it answers
let MD_STAGED = null;     // the picked-but-not-yet-applied login
let MD_BUSY = false;      // an Apply PUT in flight
let MD_ERR = "";          // this dialog's own last Apply failure
let MD_FEED = null;       // GET /api/status from the CHART service (md_mismatch, switch_error)
let MD_REACHABLE = true;  // false: "Charts service not reachable from this page", Apply disabled
let MD_POLL = null;

async function chartGet(path) {
  try {
    const r = await fetch(CHART + path);
    if (!r.ok) return {ok: false, status: r.status};
    return {ok: true, data: await r.json()};
  } catch (_) { return {ok: false, status: 0}; }
}
function labelOfMd(v) { return (MD_CHOICES.find(c => c.value === v) || {label: v}).label; }


async function loadSettings() {
  const r = await chartGet("/api/settings");
  MD_REACHABLE = r.ok;
  if (r.ok) {
    MD = r.data;
    if (!MD_BUSY) MD_STAGED = MD.md;
  }
  renderMarketData();
}
async function loadChartStatus() {
  const r = await chartGet("/api/status");
  if (r.ok) MD_FEED = r.data;
  MD_REACHABLE = r.ok;   // M1: reflects the LATEST read, so a dead-then-revived service recovers
  if (r.ok && !MD_BUSY && !MD) { await loadSettings(); return; }   // M1: retry once it's back
  if (!MD_BUSY) renderMarketData();
}

/* MARKET DATA -- "Fill charts from": Apply stages the pick, then switches it; a busy state
   while it runs; the pick snaps back to whichever login is ACTUALLY in use on failure. Rebuilt
   only when its own inputs actually changed (mdSig), so a poll tick that changes nothing never
   touches its radios/Apply button either. */
function marketDataSection() {
  if (!MD_REACHABLE) {
    return `<div class="slabel">MARKET DATA</div>
      <p class="mcap warn">Charts service not reachable from this page.</p>`;
  }
  if (!MD) return `<div class="slabel">MARKET DATA</div><p class="mcap">loading…</p>`;
  const rows = MD_CHOICES.map((c) => {
    const acct = MD.accounts && MD.accounts[c.value];
    return `<button type="button" class="${MD_STAGED === c.value ? "sel" : ""}" data-md="${c.value}"
      aria-pressed="${MD_STAGED === c.value}" ${MD_BUSY || MD.pinned ? "disabled" : ""}>${esc(c.label)}${acct ? ` (${esc(acct)})` : ""}</button>`;
  }).join("");
  const notes = [];
  if (MD_FEED && MD_FEED.md_mismatch) notes.push(esc(MD_FEED.md_mismatch));
  if (MD_FEED && MD_FEED.switch_error && !MD_ERR && !MD_BUSY) {
    notes.push(`The last switch to ${esc(labelOfMd(MD_FEED.switch_error.to))} failed: ${esc(MD_FEED.switch_error.error)}`);
  }
  const applyDisabled = MD_BUSY || MD_STAGED === MD.md;
  const where = machineWords();   // the live login holds ONE seat: taking it here drops the other machine's live charts
  const seat = MD_STAGED === "live" && MD.md !== "live"
    ? `<p class="mcap warn">Apply takes the live data seat${where ? " " + esc(where) : ""}: the other machine's charts lose live data.</p>` : "";
  return `
    <div class="slabel">MARKET DATA</div>
    <p class="wnote" style="margin-top:0">Fill charts from</p>
    <div class="seg">${rows}</div>
    <p class="wnote">Only the live login carries Level 2 (depth, DOM ladder, heatmap).</p>
    ${MD.pinned ? `<p class="mcap warn">This machine's charts use the ${esc(labelOfMd(MD.pinned))} login only; it cannot be switched here.</p>`
      : `<p class="wnote">Refused while a bot is working, and at most one switch every 10 minutes.</p>`}
    ${MD_ERR ? `<p class="mcap warn" role="alert">${esc(MD_ERR)}</p>` : ""}
    ${notes.length ? `<p class="mcap warn">${notes.join(" ")}</p>` : ""}
    ${seat}
    <p class="wnote">Charts go blank for a few seconds while market data reconnects.</p>
    <div class="row-btns" style="margin-top:10px">
      <button class="btn btn-default btn-sm" id="mdApply" type="button"
        ${applyDisabled ? "disabled" : ""}>${MD_BUSY ? "Applying…" : "Apply"}</button>
    </div>`;
}

let mdSig = null;
function renderMarketData() {
  const root = $("#settingsMarketData");
  if (!root) return;
  const sig = JSON.stringify([MD_REACHABLE, MD, MD_STAGED, MD_BUSY, MD_ERR, MD_FEED, machineWords()]);
  if (sig === mdSig) return;   // nothing changed: leave the existing nodes (and any focus) alone
  mdSig = sig;
  root.innerHTML = marketDataSection();
  for (const b of root.querySelectorAll("button[data-md]")) {
    b.addEventListener("click", () => {
      const v = b.dataset.md; MD_STAGED = v; MD_ERR = ""; renderMarketData();
      root.querySelector(`button[data-md="${v}"]`)?.focus({ preventScroll: true });   // the re-render replaced the button: keep the keyboard on it
    });
  }
  const apply = $("#mdApply");
  if (apply) apply.onclick = applyMd;
}

/* The clock: one format for the Desk, the Charts and the Lab (hbclock.js keeps the choice with the chart service). */
function renderClock() {
  const root = $("#settingsClock");
  if (!root || typeof HBClock === "undefined" || root.dataset.f === HBClock.format) return;
  const f = root.dataset.f = HBClock.format;
  const had = root.contains(document.activeElement) && document.activeElement.dataset.clock;   // the rebuild replaces the focused button
  root.innerHTML = `<div class="slabel">CLOCK</div>
    <div class="seg">${[["12h", "12-hour · 3:55 PM"], ["24h", "24-hour · 15:55"]].map(([v, t]) =>
      `<button type="button" class="${v === f ? "sel" : ""}" data-clock="${v}" aria-pressed="${v === f}">${t}</button>`).join("")}</div>
    <p class="wnote">One clock for the Desk, the Charts and the Lab.</p>`;
  if (had) root.querySelector(`button[data-clock="${had}"]`)?.focus({ preventScroll: true });
  for (const b of root.querySelectorAll("button[data-clock]")) b.onclick = async () => {
    if (!await HBClock.set(b.dataset.clock)) toast("Changed on this page. The Charts and the Lab follow once the chart service answers.");
  };
}
function renderSettings() {
  renderClock();
  buildTrading();                                  // once; patched in place from then on
  renderChartTrading(ST && ST.chart_trading);      // the switch as the desk has it now
  renderMarketData();  // rebuilds only its own container, and only when its inputs changed
  renderBacktests(ST && ST.backtests);
}

async function applyMd() {
  if (MD_BUSY || !MD || MD_STAGED === MD.md) return;   // e.repeat / a stray second click: ignored
  const md = MD_STAGED;
  MD_BUSY = true; MD_ERR = ""; renderMarketData();
  let res;
  try {
    const r = await fetch(CHART + "/api/settings", {method: "PUT",
      headers: {"content-type": "application/json"}, body: JSON.stringify({md})});
    const data = await r.json().catch(() => ({}));
    let detail = data && data.detail;
    if (detail !== undefined && typeof detail !== "string") detail = JSON.stringify(detail);   // M3: a 422 array etc.
    res = r.ok ? {ok: true, settings: data} : {ok: false, error: detail || ("failed (" + r.status + ")")};
  } catch (_) { res = {ok: false, error: "the chart service (:8852) is not reachable"}; }
  MD_BUSY = false;
  if (res.ok) { MD = res.settings; MD_STAGED = MD.md; MD_ERR = ""; }
  else { MD_ERR = res.error; MD_STAGED = MD.md; }   // snap back to whichever login is ACTUALLY in use
  renderMarketData();
}

/* ---- Backtests (read-only): how many may run at once on this machine and how many run now ----
   From /api/status `backtests` (backtest/slots.py status). The cap is set by hand in ~/.homebase/tester_slots.json; the card
   has no field or button. The trading server says it never runs backtests (its ~/.homebase/no_backtests marker). */
function backtestWords(b) {
  if (b.off) return "This server never runs backtests. Run them on the Mac.";
  return `Up to ${b.cap} at once · ${b.running ? b.running + " running now" : "none running now"}` +
         (b.quiet ? " · paused for a quiet window" : "");
}
let BT_SIG = "";
function renderBacktests(b) {
  const root = $("#settingsBacktests");
  const sig = JSON.stringify(b);
  if (!root || sig === BT_SIG) return;
  BT_SIG = sig;
  root.innerHTML = !b ? "" : `<div class="slabel" style="margin-top:14px">BACKTESTS</div>
    <p class="wnote" style="margin-top:4px;color:var(--foreground)">${esc(backtestWords(b))}</p>` +
    (b.until ? `<p class="wnote">That limit is set by hand until ${esc(b.until.slice(0, 10))}; after it: ${b.then.desk} in desk hours, ${b.then.other} other times.</p>` : "");
}

/* ---- Health (read-only): the data watchdog, the tick archive, the pre-open check and a log tail ----
   GET /api/health (the files the tick job writes), GET /api/logs/<name> (the end of one service log, secrets masked; the
   name is a key the server knows, never a path) and GET /api/preopen-check. Nothing here changes anything: the one button
   asks the Mac's Desk to run its read-only pre-open check. Where a file is not on this machine (the server) the card says so. */
let HEALTH_SIG = "", HEALTH_BUSY = false, HEALTH_LOG = {name: "", text: ""}, HEALTH_LAST = null, HEALTH_POLL = null;
const etHM = (iso) => hbClock(new Date(iso).toLocaleTimeString("en-GB", {timeZone: "America/New_York", hour: "2-digit", minute: "2-digit"}));
function healthWords(m) {
  return {fine: "fine", closed: "closed", late: "late " + m.minutes + " min", silent: "silent " + m.minutes + " min",
          thin: "thin: " + m.share + "% of its ticks"}[m.state] || m.state;
}
const healthCounts = (o) => Object.entries(o).filter(([, v]) => v).map(([k, v]) => v + " " + k.replace(/_/g, " ")).join(" · ");
function healthTable(w, c) {
  const roots = [...new Set([...(w.available ? w.markets.map(m => m.root) : []), ...(c.available ? Object.keys(c.roots) : [])])];
  if (!roots.length) return "";
  const rows = roots.map(r => {
    const m = w.available && !w.stale && w.markets.find(x => x.root === r), n = c.available && c.roots[r];
    return `<tr><td style="padding:2px 12px 2px 0">${esc(r)}</td>
      <td style="padding:2px 12px 2px 0;${m && !["fine", "closed"].includes(m.state) ? "color:var(--destructive)" : ""}">${m ? esc(healthWords(m)) : "-"}</td>
      <td style="color:var(--muted-foreground)">${n ? esc(healthCounts(n)) : "-"}</td></tr>`;
  }).join("");
  return `<table style="font-size:12.5px;margin-top:8px"><tr style="color:var(--muted-foreground)"><td style="padding-right:12px">Market</td>
    <td style="padding-right:12px">Live feed</td><td>Tick archive (sessions)</td></tr>${rows}</table>`;
}
function healthPreopen() {
  const p = window.PREOPEN;
  if (p && p.available === false) return `<p class="mcap">Pre-open check: ${esc(p.reason)}</p>`;
  const rows = p && p.available && p.checks ? p.checks.filter(c => c.level !== "ok") : [];
  const said = !p || !p.available || p.at === null ? "Not run yet"
    : rows.length ? rows.length + " to look at" : "All clear";
  const old = p && p.available && p.at !== null && Date.now() - p.got > PREOPEN_FRESH_MS;   // the banner has dropped it by now
  const when = old ? ` (last run ${etHM(new Date(p.got).toISOString())} ET, old)` : "";
  return `<p class="wnote" style="margin-top:12px">Pre-open check: ${esc(said + when)}
      <button class="btn btn-outline btn-sm" type="button" onclick="runPreopen()" ${HEALTH_BUSY ? "disabled" : ""}>${HEALTH_BUSY ? "Running…" : "Run now"}</button></p>`
    + rows.map(c => `<p class="mcap${c.level === "bad" ? " warn" : ""}" style="margin-top:2px"><b>${esc(c.label)}</b> ${esc(c.detail)}</p>`).join("");
}
function renderHealth(h) {
  const root = $("#settingsHealth");
  if (!root) return;
  HEALTH_LAST = h;
  const w = (h && h.watch) || {available: false, reason: "Could not read it"}, c = (h && h.coverage) || {available: false, reason: "Could not read it"};
  const first = !w.available ? w.reason : w.stale ? `Not checked since ${etHM(w.at_utc)} ET: the tick job has not finished a run since. Last reading: ${w.line}`
    : w.line;
  const cov = !c.available ? c.reason : healthCounts(c.classes)
    + (c.lost_hours ? ` · ${c.lost_hours} h lost` : "") + ` (report ${etHM(c.at_utc)} ET)`;
  const logs = h && h.logs && h.logs.length ? `<p class="wnote" style="margin-top:12px">Logs
      <select class="hb-field" onchange="showLog(this.value)" aria-label="Log"><option value="">pick one</option>${h.logs.map(l =>
        `<option value="${esc(l.name)}"${l.name === HEALTH_LOG.name ? " selected" : ""}>${esc(l.label)}</option>`).join("")}</select></p>
      <pre id="hlLogText" style="font-size:10.5px;white-space:pre-wrap;max-height:200px;overflow:auto;margin:6px 0 0">${esc(HEALTH_LOG.text)}</pre>` : "";
  const html = `<div class="slabel" style="margin-top:14px">HEALTH</div>
    <p class="wnote" style="margin-top:4px;color:var(--foreground)">${esc(first)}</p>
    <p class="mcap">Tick archive: ${esc(cov)}</p>${healthTable(w, c)}${healthPreopen()}${logs}`;
  if (html === HEALTH_SIG) return;             // unchanged: keep the pick and the log where they are
  HEALTH_SIG = html;
  root.innerHTML = html;
}
async function loadHealth() {
  try {
    const r = await fetch("/api/health");
    renderHealth(r.ok ? await r.json() : null);
  } catch (_) { renderHealth(null); }
}
async function showLog(name) {
  if (!name) { HEALTH_LOG = {name: "", text: ""}; return renderHealth(HEALTH_LAST); }
  HEALTH_LOG = {name, text: "loading…"};
  const pre = $("#hlLogText");
  if (pre) pre.textContent = HEALTH_LOG.text;
  try {
    const r = await fetch("/api/logs/" + encodeURIComponent(name) + "?lines=200");
    const d = await r.json();
    HEALTH_LOG.text = d.available ? d.lines.join("\n") : d.reason || "Could not read it";
  } catch (_) { HEALTH_LOG.text = "Could not read it"; }
  const out = $("#hlLogText");
  if (out) { out.textContent = HEALTH_LOG.text; out.scrollTop = out.scrollHeight; }
  HEALTH_SIG = "";                             // the next repaint carries this text
}
async function runPreopen() {
  HEALTH_BUSY = true; renderHealth(HEALTH_LAST);
  await loadPreopen(true);
  HEALTH_BUSY = false; renderHealth(HEALTH_LAST);
}

/* ---- Server updates (read-only): which commit the Chicago server runs and why a ship waits ----
   GET /api/deploy-status reads the Mac's vpssync log; this card only shows it. It has no button: nothing here ships or
   restarts anything. On the server's own Desk the route answers available:false and the card says so. */
let DEPLOY_POLL = null, DEPLOY_SIG = "";
function deployWords(d) {        // the one line first, in simple words
  if (!d) return "Could not read it";
  if (d.available === false) return "Not on this machine";
  const mins = d.waiting_min;
  const waited = mins ? ` (for ${mins >= 60 ? Math.floor(mins / 60) + " h " + (mins % 60) + " min" : mins + " min"})` : "";
  return {shipped: "Server is up to date", waiting: "Waiting: " + d.reason + waited, failed: "Failed: " + d.reason,
          not_set_up: "Not set up here"}[d.state] || "Unknown: " + (d.reason || "no answer");
}
function renderDeploy(d) {
  const root = $("#settingsDeploy");
  if (!root) return;
  const sig = JSON.stringify(d);
  if (sig === DEPLOY_SIG) return;              // unchanged: keep the open log where it is
  DEPLOY_SIG = sig;
  const ok = d && d.available && d.state === "shipped";
  const row = (k, v) => `<tr><td style="padding:2px 12px 2px 0;color:var(--muted-foreground)">${k}</td><td>${esc(v)}</td></tr>`;
  const table = d && d.available && d.main ? `<table style="font-size:12.5px;margin-top:8px">
      ${row("This Mac's main", d.main.hash + " " + d.main.subject)}
      ${row("Server runs", d.server ? d.server.hash : "unknown (not in the log)")}
      ${row("Server is behind", d.ahead == null ? "unknown" : d.ahead + (d.ahead === 1 ? " commit" : " commits"))}
      ${row("Last try", d.last_attempt || "none yet")}</table>` : "";
  const log = d && d.log && d.log.length ? `<details style="margin-top:8px"><summary class="mcap" style="cursor:pointer">log</summary>
      <pre style="font-size:10.5px;white-space:pre-wrap;max-height:160px;overflow:auto;margin:6px 0 0">${esc(d.log.join("\n"))}</pre></details>` : "";
  root.innerHTML = `<div class="slabel" style="margin-top:14px">SERVER UPDATES</div>
    <p class="wnote" style="margin-top:4px;${ok ? "" : "color:var(--foreground)"}">${esc(deployWords(d))}</p>${table}${log}`;
}
async function loadDeploy() {
  try {
    const r = await fetch("/api/deploy-status");
    renderDeploy(r.ok ? await r.json() : null);
  } catch (_) { renderDeploy(null); }
}

function openSettings() {
  showOverlay("settingsOverlay");
  renderSettings();   // CHART TRADING shows right away -- it never waits on the chart service
  loadSettings();
  loadChartStatus();
  clearInterval(MD_POLL);
  MD_POLL = setInterval(loadChartStatus, 2500);
  loadDeploy();
  clearInterval(DEPLOY_POLL);
  DEPLOY_POLL = setInterval(loadDeploy, 60000);              // while Settings is open
  loadHealth();
  clearInterval(HEALTH_POLL);
  HEALTH_POLL = setInterval(loadHealth, 60000);
}
function closeSettings() {
  hideOverlay("settingsOverlay");
  clearInterval(MD_POLL);
  MD_POLL = null;
  clearInterval(DEPLOY_POLL);
  DEPLOY_POLL = null;
  clearInterval(HEALTH_POLL);
  HEALTH_POLL = null;
}
$("#settingsOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeSettings();
});

