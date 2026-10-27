/* ---- A Lab strategy the Desk itself knows (Step B, task B6) ----
   Desk id lab_<name>, kind "lab", with a `lab` block in /api/status (limits, state, today's trades, refusals). Its row, switch, account
   picker and "Book live" confirm are the Desk's own, as for any strategy; this adds the Limits dialog, today's trades and refusals, a
   Clear for an old trade the Desk no longer owns, and Remove. Every word comes from desklab.js; every network value goes through esc / jsArg.
   The Limits dialog is static markup (#labLimitsOverlay) that render() never rebuilds: a repaint cannot wipe a field being typed in. */
const labIs = (name) => !!(ST && ST.strategies && ST.strategies[name] && ST.strategies[name].cfg && ST.strategies[name].cfg.kind === "lab");
/* The chart service's row for it (the backtest, "Matched the backtest"); null while that service does not answer. */
const labRowOf = (s) => labSafe(() => { const n = s && s.lab && s.lab.name; return DESKLAB.strategies.find(w => w && w.name === n) || null; }, null);
function labShadowTag(name, s) {       // the "Shadow" tag of a Lab strategy with no account booked
  const book = (ST && ST.book && ST.book[name]) || [];
  return book.length ? "" : `<span class="tag" title="${esc(DeskLab.TAG_TITLE)}">Shadow</span>`;
}
/* What the day would have made, for a Lab strategy with no account (the chart service's summary of its shadow day): as Step A showed it. */
function labShadowNet(name, s) {
  if (((ST && ST.book && ST.book[name]) || []).length) return null;
  const row = labRowOf(s), net = row ? DeskLab.todayNet(row) : null;
  return net == null ? null : {net, title: DeskLab.netTitle(row)};
}
/* One month of a strategy's calendar (st: {d, data, day, shadow}): the pieces both the Live pop-up and the strategy page's
   open calendar draw. pick: the function a shadow day's click calls. */
function calView(st, pick) {
  const out = {};
  const d = st.data || {days: {}, trades: [], table: []};
  const y = st.d.getFullYear(), m = st.d.getMonth();
  const month = y + "-" + String(m + 1).padStart(2, "0");
  out.month = st.d.toLocaleString("en-US", {month: "long", year: "numeric"});
  out.since = !st.data ? "loading…" :
    d.trades.length ? "since " + d.trades[0].date : st.shadow ? "no shadow trades yet" : "no live trades yet";
  let html = ["S", "M", "T", "W", "T", "F", "S"].map(x => `<div class="dow">${x}</div>`).join("");
  const first = new Date(y, m, 1), n = new Date(y, m + 1, 0).getDate();
  for (let i = 0; i < first.getDay(); i++) html += `<div class="cal-cell blank"></div>`;
  let mnet = 0, mtr = 0;
  for (let day = 1; day <= n; day++) {
    const key = month + "-" + String(day).padStart(2, "0"), v = d.days[key];
    if (v) { mnet += v.net; mtr += v.trades; }
    const cls = (v ? (v.net > 0 ? " up" : v.net < 0 ? " down" : "") : "") + (st.shadow && v ? " pick" : "") + (st.day === key ? " on" : "");
    const act = st.shadow && v ? ` role="button" tabindex="0" aria-pressed="${st.day === key}" aria-label="${key}: ${v.trades} trade${v.trades > 1 ? "s" : ""}, ${usd(v.net)}"` +
      ` onclick="${pick}('${key}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();${pick}('${key}')}"` : "";
    html += `<div class="cal-cell${cls}"${act}>${day}` +
      (v ? `<span class="pnl">${usd(v.net)}</span>` : "") + `</div>`;
  }
  out.grid = html;
  out.total = mtr ? "Month " + usd(mnet) : "";
  out.note = mtr ? `${mtr} trade${mtr > 1 ? "s" : ""} · ` + (st.shadow ? "would-be, after costs · pick a day for its trades" : "est. net after fees")
    : (st.data ? "no trades this month" : "");

  let last = "";
  out.table = d.table.length
    ? `<div class="rtable" style="margin-top:14px">` + d.table.map(([sec, k, v]) =>
        (sec !== last ? ((last = sec), `<div class="slabel2">${sec.toUpperCase()}</div>`) : "") +
        `<div class="rrow"><span class="k">${k}</span><span class="v">${v}</span></div>`).join("") +
      `</div><div class="mcap" style="margin-top:8px">${d.fee_note || ""}` +
      (d.unknown_exits ? ` · ⚠ ${d.unknown_exits} trade(s) closed while disconnected — P&L not in these totals` : "") +
      `</div>`
    : "";

  if (st.shadow) {
    const list = d.trades.filter(t => st.day ? t.date === st.day : t.date.slice(0, 7) === month);
    out.trades = list.length
      ? `<div class="slabel2" style="margin-top:14px">${st.day ? "TRADES · " + esc(st.day) : "TRADES · THIS MONTH"} · would-be fills, nothing sent</div>` +
        list.slice().reverse().map(t =>
          `<div class="rrow"><span class="k">${esc(t.date)} ${esc(t.time ? hbClock(t.time.slice(0, 5)) : "")} · ${esc(t.side || "?")} ${esc(String(t.entry))} → ${esc(String(t.exit))} · ${esc(String(t.reason).toUpperCase())}</span>` +
          `<span class="v ${t.net > 0 ? "pos" : t.net < 0 ? "neg" : ""}" style="white-space:nowrap">${usd(t.net)}</span></div>`).join("")
      : "";
    return out;
  }
  out.trades = d.trades.length
    ? `<div class="slabel2" style="margin-top:14px">TRADES · slippage in ticks (entry / exit)</div>` +
      d.trades.slice().reverse().map(t =>
        `<div class="rrow"><span class="k">${t.date} · ${t.side || "?"} ${t.entry} → ${t.exit} · ${String(t.reason).toUpperCase()}</span>` +
        `<span class="v ${t.net > 0 ? "pos" : t.net < 0 ? "neg" : ""}">${usd(t.net)}` +
        ` <span style="color:var(--muted-foreground)">${fmtTicks(t.entry_slip_ticks)} / ${fmtTicks(t.exit_slip_ticks)}</span></span></div>`
      ).join("")
    : "";
  return out;
}
/* The calendar of a Lab strategy page, always open (the owner, 2026-10-20): its SHADOW trades (the chart service's
   GET /api/tester/desklab/shadow: would-be fills, a booked day's shadow copy included) or, on the Desk, its LIVE ones
   (/api/strategy-live), a month at a time. Its state lives here, so a repaint keeps the month and the day picked. */
let SCAL = {key: ""};
function stratCal(deskId, lab) {
  const key = deskId + "|" + lab;
  if (SCAL.key !== key) SCAL = {key, deskId, lab, shadow: true, d: new Date(), day: "", data: null, at: 0, tok: 0};
  if (!SCAL.loading && Date.now() - SCAL.at > 60000) loadScal();         // its trades, read again each minute
  const v = calView(SCAL, "scalDay");
  const seg = deskId ? `<div class="seg" role="group" aria-label="Which trades">` + [[true, "Shadow"], [false, "Live"]].map(([sh, word]) =>
    `<button class="${SCAL.shadow === sh ? "sel" : ""}" aria-pressed="${SCAL.shadow === sh}" onclick="scalMode(${sh})">${word}</button>`).join("") + `</div>` : "";
  return `<div class="sec"><h2>Calendar</h2>${seg}
    <div class="cal-head"><button class="cal-nav" onclick="scalStep(-1)" aria-label="Previous month">&lsaquo;</button>
      <span class="m" style="flex:1">${esc(v.month)}</span>
      <button class="cal-nav" onclick="scalStep(1)" aria-label="Next month">&rsaquo;</button></div>
    <div class="mcap" style="margin:0 0 8px">${esc(v.since)}</div>
    <div class="cal-grid">${v.grid}</div>
    <div class="cal-foot"><span>${esc(v.note)}</span><span class="tot">${esc(v.total)}</span></div>${v.table}${v.trades}</div>`;
}
async function loadScal() {
  const s = SCAL, tok = ++s.tok, shadow = s.shadow;
  s.loading = true;
  let data = null;
  try {
    const r = await fetch(shadow ? CHART + "/api/tester/desklab/shadow?name=" + encodeURIComponent(s.lab)
                                 : "/api/strategy-live?strategy=" + encodeURIComponent(s.deskId));
    data = r.ok ? (shadow ? shadowData((await r.json()).days) : await r.json()) : null;
  } catch (_) { data = null; }
  if (SCAL !== s || s.tok !== tok) return;                             // another strategy, or the other switch, since
  s.loading = false; s.at = Date.now();
  s.data = data || {days: {}, trades: [], table: [], error: true};
  try { render(); } catch (_) { /* no page to draw on */ }
}
function scalStep(n) { SCAL.d = new Date(SCAL.d.getFullYear(), SCAL.d.getMonth() + n, 1); SCAL.day = ""; render(); }
function scalDay(key) { SCAL.day = SCAL.day === key ? "" : key; render(); }
function scalMode(shadow) {
  if (SCAL.shadow === shadow) return;
  SCAL.shadow = shadow; SCAL.day = ""; SCAL.data = null;
  loadScal();
  render();
}
function shadowData(days) {
  const out = {days: {}, trades: [], table: []};
  for (const d of Array.isArray(days) ? days : []) {
    const tr = Array.isArray(d.trades) ? d.trades : [];
    if (!tr.length) continue;
    out.days[d.date] = {net: tr.reduce((a, t) => a + (+t.net || 0), 0), trades: tr.length};
    for (const t of tr) out.trades.push({date: d.date, time: t.entry_t || "", side: t.side, entry: t.entry_px, exit: t.exit_px, reason: t.reason || "", net: +t.net || 0});
  }
  return out;
}
function labDeskView(name, s) {
  const c = s.cfg, lab = s.lab || {}, on = c.enabled === true, p = todayPnl(s), nm = stratLabel(name), busy = DESKLAB_BUSY === name;
  const accts = ST.accounts || {}, book = (ST.book && ST.book[name]) || [], row = labRowOf(s);
  const ro = DeskLab.readOnly(s), lock = DeskLab.accountsLock(s), shadow = DeskLab.inShadow(s, book);
  const sw = `<button class="switch" role="switch" aria-label="${esc(nm)} on or off" aria-checked="${on}"
    title="${esc(DeskLab.deskSwitchTitle(s, book, ST.accounts, deskMachine()))}"
    onclick="toggleStrat(${jsArg(name)}, ${!on})"></button>`;
  const sh = labShadowNet(name, s), stateNote = DeskLab.stateNote(s);
  const fig = (f) => `<div class="f"><div class="k">${esc(f.k)}</div><div class="v mono">${esc(f.v)}</div></div>`;
  const limits = DeskLab.limitsRows(lab.limits).map(x => `<div class="feed-row"><span class="h">${esc(x.k)}</span><span class="t net">${esc(x.v)}</span></div>`).join("");
  const winNote = DeskLab.windowNote(s);          // its window runs past the flat time: a note, never a refusal
  const split = DeskLab.splitRounds(lab.rounds), who = (a) => acctShort(a);
  const trades = split.today.map(r => DeskLab.roundLine(r, who(r.account))).map(x =>
    `<div class="feed-row"><span class="h${x.bad ? " warn" : ""}">${esc(x.text)}</span>${x.net == null ? "" : `<span class="t net">${esc(usdS(x.net))}</span>`}</div>` +
    (x.detail ? `<div class="feed-row"><span class="h warn">${esc(x.detail)}</span></div>` : ""));
  const refused = (Array.isArray(lab.refused) ? lab.refused : []).map(x => DeskLab.refusedLine(x, x && x.account ? who(x.account) : "")).map(x =>
    `<div class="feed-row"><span class="t">${esc(x.t)}</span><span class="h warn">${esc(x.text)}</span></div>` +
    (x.detail ? `<div class="feed-row"><span class="h warn">${esc(x.detail)}</span></div>` : ""));
  const t = (row && row.today) || {};            // what it writes down in shadow (the chart service's summary of the day)
  const shadowLines = shadow ? [...(Array.isArray(t.orders) ? t.orders : []).map(DeskLab.orderLine).map(o =>
      `<div class="feed-row"><span class="t">${esc(o.t)}</span><span class="h${o.refused ? " warn" : ""}">${esc(o.text)}</span></div>`),
    ...(Array.isArray(t.trades) ? t.trades : []).map(DeskLab.tradeLine).map(x =>
      `<div class="feed-row"><span class="h">${esc(x.text)}</span><span class="t net">${esc(usdS(x.net))}</span></div>`)] : [];
  const todayAll = [...trades, ...shadowLines, ...refused];
  const today = todayAll.length ? `<div class="agroup feed static">${todayAll.join("")}</div>` : `<div class="eq-empty">${esc(DeskLab.EMPTY_DAY)}</div>`;
  const old = split.old.map(r => ({r, x: DeskLab.roundLine(r, who(r.account))})).map(({r, x}) =>
    `<div class="feed-row"><span class="h warn">${esc(x.text)}</span>
      <button class="btn btn-outline btn-sm" onclick="clearLabBlock(${jsArg(name)}, ${jsArg(r.account)})"${labClearing(name, r.account) ? " disabled" : ""} title="${esc(x.text)}">${esc(DeskLab.CLEAR)}</button></div>`);
  const isDay = (d) => /^\d{4}-\d\d-\d\d$/.test(String(d));
  const days = (row && Array.isArray(row.days) ? row.days : []).map(DeskLab.matchLine).map(m =>
    `<div class="feed-row"><span class="t">${esc(isDay(m.date) ? shortDay(m.date) : m.date)}</span><span class="h${m.ok === false ? " warn" : ""}">${esc(m.text)}</span>${m.rebuilt ? '<span class="t dim">rebuilt</span>' : ""}<span class="t net">${esc(usdS(m.net))}</span></div>`);
  const rows = book.map(a => acctRow(a.account, {qty: a.qty, strategy: name, locked: ro})).join("");
  const free = Object.keys(accts).filter(id => !book.some(a => a.account === id));
  const cap = ro ? "" : lock.caption;
  const addForm = !Object.keys(accts).length ? `<div class="mcap">Add an account to run this strategy.</div>`
    : lock.locked ? `<button class="btn btn-quiet noarrow btn-sm" disabled title="${esc(lock.caption)}">+ Assign an account</button>${cap ? `<div class="mcap">${esc(cap)}</div>` : ""}`
    : free.length ? `<div style="position:relative;display:inline-block;margin-top:10px">
        <button class="btn btn-quiet noarrow btn-sm" onclick="toggleAsgMenu(${jsArg(name)})" aria-haspopup="menu">+ Assign an account</button>
        <div class="amenu" id="amenu-${esc(name)}" role="menu" hidden>` +
        free.map(id => `<button class="mi2" role="menuitem" onclick="pickAsg(${jsArg(name)},${jsArg(id)},${+c.qty || 1})">${esc(accts[id].label || id)}</button>`).join("") + `</div></div>` : "";
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(nm)}</h1><div class="sp mono">${esc(specOf(c, name))}</div></div>${sw}</div>
    <div class="sd-state"><b>${esc(DeskLab.deskState(s, book))}</b>${sh ? ` · today would be ${esc(usdS(sh.net))}` : p != null ? ` · today ${esc(usdS(p))}` : ""}</div>
    ${stateNote ? `<div class="sd-note">${esc(stateNote)}</div>` : ""}
    <div class="sd-note">${esc(DeskLab.deskNote(book.length > 0))}</div>
    ${ro ? `<div class="sd-note">${esc(DeskLab.OTHER_DESK)}</div>` : ""}
    ${lab.auto === true ? "" : `<div class="sec"><h2>Limits</h2><div class="agroup feed static">${limits}</div>${winNote ? `<div class="mcap warn">${esc(winNote)}</div>` : ""}
      <button class="btn btn-outline btn-sm" onclick="openLabLimits(${jsArg(name)})"${ro ? " disabled" : ""}>${esc(DeskLab.EDIT_LIMITS)}</button></div>`}
    <div class="sec"><h2>${shadow ? "Today, in shadow" : "Today"}</h2>${today}${actBtn("s:" + name)}</div>${lab.name ? stratCal(name, lab.name) : ""}
    ${old.length ? `<div class="sec"><h2>${esc(DeskLab.OLD_TITLE)}</h2><div class="agroup feed static">${old.join("")}</div></div>` : ""}
    ${row ? `<div class="sec"><h2>Matched the backtest</h2>${days.length ? `<div class="agroup feed static">${days.join("")}</div>` : `<div class="eq-empty">${esc(DeskLab.NOT_CHECKED)}</div>`}</div>
    ${labCurveHtml(row.name)}${labResHtml(row.name, name)}` : ""}
    <div class="sec"><h2>Accounts</h2>${rows ? `<div class="agroup">${rows}</div>` : ""}${ro ? "" : rotationHtml(name)}${addForm}</div>
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="flattenStrat(${jsArg(name)})" title="Flattens its positions and switches it off">Flatten &amp; turn off</button>
      ${deskMachine() === "server" ? "" : `<button class="btn btn-outline btn-sm" onclick="openDeskLabInLab(${jsArg(lab.name || "")})" title="The Lab page, on this strategy's 3:1 out-of-sample">Open in the Lab</button>`}
      <button class="btn btn-outline btn-sm" onclick="archiveLabStrat(${jsArg(lab.name || "")}, ${jsArg(name)})"${busy || ro || !lab.name ? " disabled" : ""} title="Off the Desk, switched off, its accounts off, and kept. Restore it from Archive any time.">Archive</button>
      <button class="btn btn-outline btn-sm" onclick="removeLabStrat(${jsArg(name)})"${busy || ro ? " disabled" : ""} title="Takes it off the Desk. Its history is kept.">Remove from Desk</button>
      <button class="btn btn-outline btn-sm" onclick="deleteLabStrat(${jsArg(name)}, ${jsArg(lab.name || "")})"${busy || ro || !lab.name ? " disabled" : ""} title="Takes it off the Desk and deletes its shadow and day history for good. Its Lab draft stays.">Delete</button></div>`;
}
/* The Limits dialog: filled when it opens, never while it is open. Save posts exactly what the fields say, after the same checks the Desk makes. */
let LAB_LIM = {name: "", tok: 0};       // the open dialog: whose, and which opening of it (a token per open)
let LAB_TOK = 0, LAB_SAVING = false;     // a save that is out stays out across a close and a re-open
const LAB_LIM_FIELDS = [["trades", "llTrades"], ["qty", "llQty"], ["risk", "llRisk"], ["last", "llLast"], ["flat", "llFlat"]];
function labLimErrors(errors) {
  for (const [k, id] of LAB_LIM_FIELDS) {
    const e = $("#" + id + "Err"), msg = errors && errors[k] ? errors[k] : "";
    e.textContent = msg; e.hidden = !msg;
    $("#" + id).setAttribute("aria-invalid", msg ? "true" : "false");
  }
}
function labLimKey(e) { if (e.key === "Enter" && !e.repeat) { e.preventDefault(); saveLabLimits(); } }      // Enter saves; a held key does not
function openLabLimits(name) {
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s || !s.lab || DeskLab.readOnly(s)) return;
  LAB_LIM = {name, tok: ++LAB_TOK};
  $("#llTitle").textContent = DeskLab.limitsTitle(stratLabel(name));
  const f = DeskLab.limitsFields(s.lab.limits);
  for (const [k, id] of LAB_LIM_FIELDS) { $("#" + id).value = f[k]; $("#" + id).oninput = labLimSaveText; }
  labLimSaveText();
  labLimErrors({});
  const note = $("#llNote"); note.textContent = ""; note.hidden = true;
  $("#llSave").disabled = LAB_SAVING;
  showOverlay("labLimitsOverlay");
}
/* The Save button lists what changes, old → new, as the fields read now ("Save: Trades a day 2 → 3"); plain "Save limits" when
   nothing changes or none were set. */
const LAB_LIM_WORDS = {trades: "Trades a day", qty: "Contracts", risk: "At risk", last: "No new trade after", flat: "Flat by"};
function labLimSaveText() {
  const s = ST && ST.strategies && ST.strategies[LAB_LIM.name], old = s && s.lab && s.lab.limits;
  const was = DeskLab.limitsFields(old), show = (k, v) => v === "" ? "none" : k === "risk" ? "$" + v.replace(/^\$/, "") : v;
  const ch = old ? LAB_LIM_FIELDS.map(([k, id]) => [k, String($("#" + id).value).trim()]).filter(([k, v]) => v !== was[k])
    .map(([k, v]) => `${LAB_LIM_WORDS[k]} ${show(k, was[k])} → ${show(k, v)}`) : [];
  $("#llSave").textContent = ch.length ? "Save: " + ch.join(" · ") : DeskLab.SAVE_LIMITS;
  return ch;
}
/* A limit loosened (a higher number, a later time) or removed. Tightening never asks. */
const labLimLooser = (old, body) => !!old && ["max_trades_day", "max_qty", "max_risk_usd", "last_entry_et", "flat_et"]
  .some(k => old[k] != null && (body[k] == null || body[k] > old[k]));
function closeLabLimits() {
  hideOverlay("labLimitsOverlay");
  LAB_LIM = {name: "", tok: 0};
}
async function saveLabLimits() {
  const name = LAB_LIM.name, tok = LAB_LIM.tok;
  if (!name || LAB_SAVING) return;
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s) { toast(DeskLab.NOT_ON_DESK, 5000); closeLabLimits(); return; }      // it has left the Desk since the dialog opened
  const row = labRowOf(s), w = row && Array.isArray(row.session_window) ? row.session_window[0] : "";      // unknown while the chart service is down: the Desk judges that part
  const got = DeskLab.checkLimits(Object.fromEntries(LAB_LIM_FIELDS.map(([k, id]) => [k, $("#" + id).value])), w);
  labLimErrors(got.errors);
  const note = $("#llNote"); note.textContent = ""; note.hidden = true;
  if (!got.body) return;                  // nothing is sent until every field reads
  LAB_SAVING = true; $("#llSave").disabled = true;
  const live = liveBooked(name);          // loosening a limit while it is ON with a LIVE account asks first
  if (live && labLimLooser(s.lab && s.lab.limits, got.body)) {
    const yes = await confirmDlg(`Loosen the limits of ${stratLabel(name)}?`, labLimSaveText().join(" · ") + ". " + liveWords(stratLabel(name), live),
      DeskLab.SAVE_LIMITS, false);
    if (!yes || LAB_LIM.tok !== tok) { LAB_SAVING = false; if (LAB_LIM.name) $("#llSave").disabled = false; return; }
  }
  let r, err = null;
  try { r = await post("/api/lab-limits", {strategy: name, limits: got.body}); } catch (e) { err = e || new Error("no answer"); }
  LAB_SAVING = false;
  const ok = !err && r && r.ok === true;
  if (LAB_LIM.tok !== tok) {              // closed, or opened again, while the Desk answered: that dialog is not this answer's to close or write to
    if (LAB_LIM.name) $("#llSave").disabled = false;
    if (ok) refresh();
    return;
  }
  $("#llSave").disabled = false;
  if (ok) { closeLabLimits(); refresh(); return; }
  note.textContent = DeskLab.refusalText(r, err); note.hidden = false;      // the Desk's own sentence, no prefix
}
/* Remove from the Desk: its accounts come off, its limits go, its history stays. Refused while a trade is open ("Flatten it first."). */
async function removeLabStrat(name) {
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s || DESKLAB_BUSY || DEMO) return;
  const ask = DeskLab.removeAskDesk(stratLabel(name));
  if (!await confirmDlg(ask.title, ask.body, "Remove", false)) return;
  DESKLAB_BUSY = name; if (ST) render();
  let r, err = null;
  try { r = await post("/api/lab-remove", {strategy: name}); } catch (e) { err = e || new Error("no answer"); }
  DESKLAB_BUSY = "";
  if (!err && r && r.ok === true) {
    if (VIEW.k === "strat" && VIEW.name === name) VIEW = {k: "today"};
    toast(`${stratLabel(name)} is off the Desk. Its history is kept; promote it again from the Lab any time.`);
  } else toast(DeskLab.refusalText(r, err), 7000);
  await refresh();
  loadDeskLab();
}
/* The chart service's delete of an off-the-Desk strategy's history (draft: its Lab draft too). The runner needs a few seconds to let
   a strategy go, so it is tried again while it says so. */
async function deleteHistory(lab, draft) {
  let r;
  for (let i = 0; i < 10; i++) {
    r = await chartPost("/api/tester/desklab/delete", draft ? {name: lab, draft: true} : {name: lab});
    if (!(r && r.ok === false && /letting it go/.test(String(r.detail || "")))) break;
    await new Promise(res => setTimeout(res, 2000));
  }
  return r;
}
/* DELETE (the owner, 2026-10-20: "not only remove them, also delete them"): the Desk's own Remove (its "Flatten it first.",
   its accounts coming off), then the chart service deletes its history -- shadow days, day records, its journal. The runner
   needs a few seconds to let it go, so that step is tried again while it says so. Real trades stay in the account history;
   the Lab draft stays in the Lab. */
async function deleteLabStrat(name, lab) {
  if (!name || !lab || DESKLAB_BUSY || DEMO) return;
  const N = stratLabel(name);
  if (!await confirmDlg(`Delete ${N}?`, "It comes off the Desk and its accounts come off. Its shadow calendar and day records are deleted for good. Real trades stay in the account history, and its Lab draft stays in the Lab.", "Delete", true)) return;
  DESKLAB_BUSY = name; if (ST) render();
  let r, err = null, removed = false;
  try { r = await post("/api/lab-remove", {strategy: name}); } catch (e) { err = e || new Error("no answer"); }
  if (!err && r && r.ok === true) {
    removed = true;
    r = await deleteHistory(lab);
  }
  DESKLAB_BUSY = "";
  if (removed && VIEW.k === "strat" && VIEW.name === name) VIEW = {k: "today"};
  if (!err && r && r.ok === true) toast(`${N} is deleted.`);
  else if (removed) toast(`${N} is off the Desk, but its history was not deleted: ${DeskLab.refusalText(r, err)}`, 8000);
  else toast(`Could not delete ${N}: ${DeskLab.refusalText(r, err)}`, 7000);
  await refresh();
  loadDeskLab();
}
/* ARCHIVE (the owner, 2026-10-18): off the Desk, switched off, kept; Restore puts it back. Three steps: the chart service keeps a copy,
   then the Desk's own Remove takes it off (refused while a trade is open: "Flatten it first."; its accounts come off), then its Lab
   draft is filed under the "Archive" group. deskId: its Desk id when the Desk holds it (lab_<name>), else the chart service removes it. */
async function archiveLabStrat(name, deskId) {
  if (!name || DESKLAB_BUSY || DEMO) return;
  const label = deskId ? stratLabel(deskId) : name;
  if (!await confirmDlg(`Archive ${label}?`, "It comes off the Desk, switched off, and its accounts come off. Its history is kept. Restore it from Archive any time.", "Archive", false)) return;
  DESKLAB_BUSY = name; if (ST) render();
  let r = await chartPost("/api/tester/desklab/archive", {name}), err = null;
  if (r && r.ok === true) {
    if (deskId) { try { r = await post("/api/lab-remove", {strategy: deskId}); } catch (e) { err = e || new Error("no answer"); } }
    else r = await chartPost("/api/tester/desklab/remove", {name});
  }
  if (!err && r && r.ok === true) r = await chartPost("/api/tester/desklab/filed", {name});
  DESKLAB_BUSY = "";
  if (!err && r && r.ok === true) {
    if ((VIEW.k === "strat" && VIEW.name === deskId) || (VIEW.k === "lab" && VIEW.name === name)) VIEW = {k: "archive"};
    toast(`${label} is archived. Restore it from Archive any time.`);
  } else toast(`Could not archive ${label}: ${DeskLab.refusalText(r, err)}`, 7000);
  if (deskId) await refresh();
  loadDeskLab();
}
/* DELETE from the Archive (the owner, 2026-10-22: "fully delete and remove them"): the archived copy, the strategy's history and its Lab
   draft (the draft goes to the drafts' trash). Real trades stay in the account history. A built-in is the Desk's own: no Delete. */
async function deleteArchived(name) {
  if (DESKLAB_BUSY || DEMO) return;
  const w = (DESKLAB.archived || []).find(x => x.name === name), label = w ? DeskLab.label(w) : name;
  if (!await confirmDlg(`Delete ${label} for good?`, "It is wiped from the Archive and the Lab. Its shadow calendar and day records are deleted for good. Real trades stay in the account history.", "Delete", true)) return;
  DESKLAB_BUSY = name; if (ST) render();
  const r = await deleteHistory(name, true);
  DESKLAB_BUSY = "";
  toast(r && r.ok === true ? `${label} is deleted.` : `Could not delete ${label}: ${DeskLab.refusalText(r, null)}`, 7000);
  await loadDeskLab();
}
async function restoreArchived(name) {
  if (DESKLAB_BUSY || DEMO) return;
  const w = (DESKLAB.archived || []).find(x => x.name === name), label = w ? DeskLab.label(w) : name;
  DESKLAB_BUSY = name; if (ST) render();
  const r = await chartPost("/api/tester/desklab/restore", {name});
  DESKLAB_BUSY = "";
  if (r && r.ok === true) toast(`${label} is back on the Desk, switched off, with no account.`);
  else toast(`Could not restore ${label}: ${(r && r.detail) || "no answer"}`, 7000);
  await loadDeskLab();
  refresh();
}
/* A built-in (nq930, gc_nfp) is the Desk's own: it cannot leave the Desk's config, so Archive switches it off here and notes it on the
   chart service, and the page hides it. Refused while an account is assigned or it has anything open today (the hide rule). Restore shows it
   again, switched off. */
function archivedBuiltins() { return (DESKLAB.archived || []).filter(w => w && w.builtin === true).map(w => w.name); }
async function archiveBuiltin(name) {
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s || DESKLAB_BUSY || DEMO) return;
  const N = stratLabel(name), book = (ST.book && ST.book[name]) || [], info = hideInfo(name);
  if (book.length) return toast(`${N} has accounts assigned. Take them off first.`, 7000);
  if (info.locked) return toast(`${N} cannot be archived now: ${info.reason}.`, 7000);
  if (!await confirmDlg(`Archive ${N}?`, "It is switched off and comes off the Desk's list. Its settings and history stay. Restore it from Archive any time.", "Archive", false)) return;
  DESKLAB_BUSY = name; if (ST) render();
  let r = {ok: true}, err = null;
  if (s.cfg.enabled) { try { r = await post("/api/strategy", {strategy: name, enabled: false}); } catch (e) { err = e || new Error("no answer"); } }
  const why = s.cfg.enabled ? answerWhy(r, err) : "";
  if (!why) r = await chartPost("/api/tester/desklab/archive_builtin", {name});
  DESKLAB_BUSY = "";
  if (!why && r && r.ok === true) {
    if (VIEW.k === "strat" && VIEW.name === name) VIEW = {k: "archive"};
    toast(`${N} is switched off and archived. Restore it from Archive any time.`);
  } else toast(`Could not archive ${N}: ${why || (r && r.detail) || "no answer"}`, 7000);
  await loadDeskLab();
  refresh();
}
async function restoreBuiltin(name) {
  if (DESKLAB_BUSY || DEMO) return;
  DESKLAB_BUSY = name; if (ST) render();
  const r = await chartPost("/api/tester/desklab/restore_builtin", {name});
  DESKLAB_BUSY = "";
  toast(r && r.ok === true ? `${stratLabel(name)} is back on the Desk, switched off.` : `Could not restore ${stratLabel(name)}: ${(r && r.detail) || "no answer"}`, 7000);
  await loadDeskLab();
  refresh();
}
function archiveView() {
  const rows = (DESKLAB.archived || []).map(w => {
    if (w.builtin === true) {
      const day = String(w.archived_utc || "").slice(0, 10);
      return `<div class="feed-row"><span class="h"><b>${esc(stratLabel(w.name))}</b> · the Desk's own${day ? " · archived " + esc(shortDay(day)) : ""}</span>
        <button class="btn btn-outline btn-sm" onclick="restoreBuiltin(${jsArg(w.name)})"${DESKLAB_BUSY ? " disabled" : ""} title="Back on the Desk's list, switched off">Restore</button></div>`;
    }
    const f = DeskLab.figures(w), day = String(w.archived_utc || "").slice(0, 10), busy = DESKLAB_BUSY === w.name;
    return `<div class="feed-row"><span class="h"><b>${esc(DeskLab.label(w))}</b> · ${esc(w.root || "")}${day ? " · archived " + esc(shortDay(day)) : ""}<br>
      <small class="dim">${f.map(x => esc(x.k + " " + x.v)).join(" · ")}</small></span>
      <button class="btn btn-outline btn-sm" onclick="restoreArchived(${jsArg(w.name)})"${busy || DESKLAB_BUSY ? " disabled" : ""} title="Back on the Desk, switched off, with no account">Restore</button>
      <button class="btn btn-outline btn-sm" onclick="deleteArchived(${jsArg(w.name)})"${busy || DESKLAB_BUSY ? " disabled" : ""} title="Deletes it for good: its history and its Lab draft">Delete</button></div>`;
  }).join("");
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">Archive</h1><div class="sp">Off the Desk and switched off. Restore puts one back, switched off, with no account.</div></div></div>
    <div class="sec">${rows ? `<div class="agroup feed static">${rows}</div>` : `<div class="eq-empty">Nothing is archived.</div>`}</div>`;
}
/* Clear an old trade the Desk no longer owns: the Desk does it only when the account is flat and no old order is working, and says why not. */
const LAB_CLEARING = new Map();      // "strategy@account" -> Infinity while a clear is out, then when it was answered ok
const labClearing = (name, account) => { const t = LAB_CLEARING.get(name + "@" + account); return t !== undefined && (t === Infinity || Date.now() - t < 3000); };
async function clearLabBlock(name, account) {
  const key = name + "@" + account;
  if (labClearing(name, account) || DEMO) return;      // one click is one clear; a double click is not two
  LAB_CLEARING.set(key, Infinity);
  let r, err = null;
  try { r = await post("/api/lab-clear", {strategy: name, account}); } catch (e) { err = e || new Error("no answer"); }
  const ok = !err && r && r.ok === true;
  if (ok) LAB_CLEARING.set(key, Date.now()); else LAB_CLEARING.delete(key);      // a refusal changes nothing: it can be tried again
  toast(ok ? DeskLab.CLEARED : DeskLab.refusalText(r, err), 7000);
  refresh();
}

function renderMain(names, issues) {
  $("#viewToday").hidden = VIEW.k !== "today";
  $("#viewStrat").hidden = VIEW.k !== "strat" && VIEW.k !== "lab" && VIEW.k !== "group" && VIEW.k !== "archive";
  $("#viewActivity").hidden = VIEW.k !== "activity";
  if (VIEW.k === "today") {
    const [l1, l2] = dayHeadline(names);
    const l2h = esc(l2).replace(/(Today )([−+]?\$[\d,]+)/, (m, a, b) => `${a}<span class="amt${b[0] === "+" ? " pos" : ""}">${b}</span>`);
    $("#dayTitle").innerHTML = `${esc(l1)}<br><span>${l2h}</span>`;
    $("#dayTl").innerHTML = dayTimeline(names);
    $("#stratList").innerHTML = names.map(n => todayRow(n, ST.strategies[n])).join("") + labRowsHtml(todayLabRow)
      || `<div class="feed-empty" style="padding:28px 26px">No strategies are showing. Use Manage algos to bring one back.</div>`;
    $("#todayFoot").innerHTML = todayFoot(issues);
  } else if (VIEW.k === "strat") $("#viewStrat").innerHTML = stratView(VIEW.name);
  else if (VIEW.k === "lab") $("#viewStrat").innerHTML = labSafe(() => labView(VIEW.name), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${LAB_FAULT}</div>`);
  else if (VIEW.k === "group") $("#viewStrat").innerHTML = labSafe(() => groupView(VIEW.name), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${GROUP_FAULT}</div>`);
  else if (VIEW.k === "archive") $("#viewStrat").innerHTML = labSafe(() => archiveView(), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${LAB_FAULT}</div>`);
}

function render() {
  const s = ST;
  $("#clock").textContent = hbClock(String(s.et_now).slice(11, 19)) + " ET";
  renderMaster();
  renderChartTrading(s.chart_trading);
  if ($("#settingsOverlay").classList.contains("open")) renderSettings();

  // readiness: silent when fine, loud when not; dismissable — but a
  // dismissed strip returns the moment the SET of problems changes
  const r = readinessShown(s.readiness, s);   // a "no signal" that could not have fired reads as info (W4)
  renderBulb(r);
  const strip = $("#readyStrip");
  const probs = r ? r.checks.filter(c => c.level === "bad" || c.level === "warn") : [];
  const sig = JSON.stringify(probs.map(c => c.label + "|" + c.detail));
  let dismissed = "";
  try { dismissed = localStorage.getItem("hb_ready_dismiss") || ""; } catch (_) {}
  window.READY_SIG = sig;
  if (r && !r.ready && sig !== dismissed) {
    strip.style.display = "";
    strip.innerHTML = `<span class="headline">Not ready</span>` +
      probs.map(c => `<span class="ri ${c.level}">
        <span class="rd ${c.level}"></span><b>${esc(c.label)}</b> ${esc(String(c.detail).slice(0, 70))}${String(c.detail).length > 70 ? "…" : ""}</span>`).join("") +
      `<span class="spacer"></span>` +
      (Object.values(s.accounts || {}).some(a => !a.connected)
        ? `<button class="btn btn-outline btn-sm" onclick="reconnectAcct('')"
             title="Rebuild every broker connection">Reconnect</button>` : "") +
      `<button class="x" style="border:none;background:none;color:var(--muted-foreground);cursor:pointer;font-size:15px;padding:0 2px"
         title="Dismiss — reappears if the problems change"
         onclick="dismissReady()">&times;</button>`;
  } else strip.style.display = "none";

  const shelved = archivedBuiltins();       // archived built-ins hide by the same rule as Manage algos: one that can trade or holds anything shows
  const algoVis = window.AlgoVisibility
    ? window.AlgoVisibility.computeVisibility(s.strategies, s.book, HIDDEN_ALGOS.concat(shelved), s.accounts)
    : Object.keys(s.strategies).map(n => ({name: n, visible: true}));
  const visibleNames = new Set(algoVis.filter(a => a.visible).map(a => a.name));
  const names = Object.keys(s.strategies).filter(n => visibleNames.has(n))
    .sort((a, b) => (s.strategies[b].cfg.enabled ? 1 : 0) - (s.strategies[a].cfg.enabled ? 1 : 0));   // switched-on first
  if (VIEW.k === "lab" && labSafe(() => DeskLab.onDesk(s.strategies, {name: VIEW.name}), false)) VIEW = {k: "strat", name: "lab_" + VIEW.name};   // the Desk knows it now: its own page
  if (VIEW.k === "strat" && !names.includes(VIEW.name)) VIEW = {k: "today"};
  if (VIEW.k === "group" && DESKGROUPS.ok === true && !groupOf(VIEW.name)) VIEW = {k: "today"};      // a group removed (here or elsewhere)
  ISSUE_LVL = probs.some(c => c.level === "bad") ? "bad" : "warn";
  renderSide(names, algoVis.filter(a => !a.visible && !shelved.includes(a.name)).length, probs.length);
  renderMain(names, probs.length);
  // the views were rebuilt: an + Assign menu that lived in them is gone -- so is its hold on updates
  if (ASG_OPEN && !document.contains(ASG_OPEN.menu)) {
    ASG_OPEN = null;
    if (!document.getElementById("qedit")) FREEZE = false;
  }
  if ($("#algoOverlay").classList.contains("open")) renderAlgoMgr();
  if ($("#acctOverlay").classList.contains("open")) tickAccts();         // its read-only cells, in place
  renderGroupMgr();

  fillActWho();
  renderActivity(actRows(s.journal));
  if (VIEW.k === "activity") loadActivity(false);
  renderNotices(s.notices);
}

$("#noticeStrip").addEventListener("click", (e) => {
  if (e.target.closest(".x")) return;           // the × dismisses; everything else expands
  e.currentTarget.classList.toggle("open");
});

/* An open + Assign menu or size edit holds updates (FREEZE) so a repaint never wipes it -- but the
   top bar must not keep asserting a state nothing is checking: after FREEZE_STALE_MS without a
   fresh status, the pill goes stale ("· stale", dashed) until the next refresh after the menu or
   edit closes. No extra request is made for it. */
const FREEZE_STALE_MS = 5000;
let LAST_FRESH = Date.now();      // when ST last came from the desk
async function refresh() {
  if (FREEZE) {                   // don't wipe an open menu or qty edit
    if (!DESK_STALE && Date.now() - LAST_FRESH > FREEZE_STALE_MS) {
      DESK_STALE = true; STALE_WHY = "updates pause while a menu or a size edit is open";
      renderMaster();
    }
    return;
  }
  if (DEMO) { ST = demoStatus(); DESK_STALE = false; LAST_FRESH = Date.now(); render(); return; }
  /* Only a real status replaces ST (second review): an HTTP error with a JSON body (the write
     guard's 403) or a body without a boolean `armed` used to become ST -- and the pill then read
     DISARMED, a state nobody reported. Anything else keeps the last-known state, marked stale. */
  let refused = "";
  try {
    const res = await fetch("/api/status");
    let d = null;
    try { d = await res.json(); } catch (_) { d = null; }
    if (!res.ok) refused = `the desk answered HTTP ${res.status}` + (d && d.error ? ": " + String(d.error).slice(0, 80) : "");
    else if (!d || typeof d !== "object" || typeof d.armed !== "boolean") refused = "the desk's status was unreadable";
    if (refused) throw new Error(refused);
    ST = d; DESK_STALE = false; STALE_WHY = ""; LAST_FRESH = Date.now();
    // (second review) a menu or size edit that opened while this was in flight is never wiped: the
    // cards wait for the next refresh after it closes -- repainting them removed an open + Assign
    // menu (leaving updates paused with no menu on screen) and an open size edit (whose blur then
    // wrote the half-typed size). The top bar is its own, so it still gets the fresh state.
    if (FREEZE) renderMaster(); else render();
  }
  catch {
    DESK_STALE = true;   // ST is now the last-known state, not current -- the top bar shows it as stale
    STALE_WHY = refused || "the desk is not answering";
    $("#clock").textContent = refused ? "status error" : "server unreachable";
    renderMaster();
    if ($("#settingsOverlay").classList.contains("open")) renderSettings();
  }
}

