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
    d.trades.length ? "since " + d.trades[0].date : st.shadow ? "no shadow trades yet" : "no Desk trades yet";
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
function stratCal(deskId, lab, booked, extra, picker) {      // booked: Accounts first and picked; extra: the Matched-the-backtest line
  const key = deskId + "|" + lab;
  if (SCAL.key !== key) SCAL = {key, deskId, lab, shadow: !(deskId && booked), d: new Date(), day: "", data: null, at: 0, tok: 0};
  if (!SCAL.loading && Date.now() - SCAL.at > 60000) loadScal();         // its trades, read again each minute
  const v = calView(SCAL, "scalDay");
  const opts = booked ? [[false, "Accounts"], [true, "Shadow"]] : [[true, "Shadow"], [false, "Accounts"]];
  const seg = deskId ? `<div class="seg" role="group" aria-label="Which trades">` + opts.map(([sh, word]) =>
    `<button class="${SCAL.shadow === sh ? "sel" : ""}" aria-pressed="${SCAL.shadow === sh}" onclick="scalMode(${sh})">${word}</button>`).join("") + `</div>` : "";
  return `<div class="sec"><h2>Results</h2>${seg}${picker || ""}
    <div class="cal-head"><button class="cal-nav" onclick="scalStep(-1)" aria-label="Previous month">&lsaquo;</button>
      <span class="m" style="flex:1">${esc(v.month)}</span>
      <button class="cal-nav" onclick="scalStep(1)" aria-label="Next month">&rsaquo;</button></div>
    <div class="mcap" style="margin:0 0 8px">${esc(v.since)}</div>
    <div class="cal-grid">${v.grid}</div>
    <div class="cal-foot"><span>${esc(v.note)}</span><span class="tot">${esc(v.total)}</span></div>${extra || ""}${v.table}${v.trades}</div>`;
}
async function loadScal() {
  const s = SCAL, tok = ++s.tok, shadow = s.shadow;
  s.loading = true;
  let data = null;
  try {
    const r = await fetch(shadow ? CHART + "/api/tester/desklab/shadow?name=" + encodeURIComponent(s.lab)
                                 : "/api/strategy-live?strategy=" + encodeURIComponent(s.deskId));
    const j = r.ok ? await r.json() : null;
    data = j ? (shadow ? shadowData(j.days) : j) : null;
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
/* A Lab strategy's page, in the approved order (owner 2026-11-02, spec 4.3): title, sub-line and switch; the status line; the Set up
   card; Today; Results (one calendar, Accounts / Shadow, and how often it matched the backtest). Then Backtest, About and More, which
   the skin moves into the right panel. */
let MATCH_OPEN = "";      // the strategy whose "Matched the backtest" day list is open
function toggleMatchDays(name) { MATCH_OPEN = MATCH_OPEN === name ? "" : name; render(); }
const labSetOf = (name) => ((ST.variants && ST.variants.sets) || []).find(x => (x.members || []).includes(name)) || null;
/* A variant set is one page: the page of its first member on the Desk (the sidebar opens that one). soloVs(name) = the set whose page
   `name` is (members still on the Desk), else null; a later member's page points at it. */
function soloVs(name) {
  const v = labSetOf(name), ms = v ? v.members.filter(m => ST.strategies[m]) : [];
  return ms.length > 1 && ms[0] === name ? {...v, members: ms} : null;
}
const soloVarLabel = (m) => { const v = labSetOf(m); return v ? ((v.labels || {})[m] || stratLabel(m)) : ""; };
let SET_PICK = {};      // the variant whose Results and "Matched the backtest" a set's page shows (set id -> member)
const setPicked = (vs) => vs.members.includes(SET_PICK[vs.id]) ? SET_PICK[vs.id] : vs.members[0];
function setPickVariant(id, m) { SET_PICK[id] = m; render(); }
/* "Matched the backtest on 18 of 19 days ›": the days the daily match checked, and how many matched */
function matchSummary(days) {
  const seen = days.filter(m => m.ok !== null);
  return seen.length ? `Matched the backtest on ${seen.filter(m => m.ok === true).length} of ${plural(seen.length, "day", "days")}` : "Matched the backtest: " + DeskLab.NOT_CHECKED.toLowerCase();
}
/* one row per variant (one for a plain strategy): its saved run's net, trades and win rate */
function backtestRows(members, set) {
  const one = (m) => {
    const s = ST.strategies[m], lab = s && s.lab && s.lab.name, label = set && (set.labels || {})[m] ? set.labels[m] : stratLabel(m);
    let v = null;
    try { v = DeskLab.results(DESKRES[lab]).unseen; } catch (_) { v = null; }
    const get = (k) => { const r = v && v.rows.find(x => x.k === k); return r ? r.v : "—"; };
    if (!v || !v.rows.length) return `<div class="feed-row"><span class="h">${esc(label)}</span><span class="t dim">${esc(v ? v.note : DeskLab.NOT_CHECKED)}</span></div>`;
    return `<div class="feed-row" title="${esc(v.title)}"><span class="h">${esc(label)}</span><span class="t">${esc(get("Trades"))} trades</span><span class="t">${esc(get("Win rate"))} won</span><span class="t net">${esc(get("Net"))}</span></div>`;
  };
  return members.map(one).join("");
}
/* About: what it is, read only. A setting the Desk changed from its Lab default is shown, never edited here. */
function aboutRows(name, s, row) {
  const c = s.cfg || {}, lab = s.lab || {}, l = DeskLab.limitsRows(lab.limits), bars = row && row.bar_minutes;
  const win = row ? DeskLab.deskSpec({}, row).replace(/ ?·? ?from the Lab$/, "") : "";
  const mark = Array.isArray(lab.mark) ? lab.mark : [], p = lab.params || {};
  const since = (iso) => { const d = new Date(iso); return iso && !isNaN(d.getTime()) ? d.toLocaleDateString("en-US", {month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York"}) : "—"; };
  const changed = (Array.isArray(lab.settings) ? lab.settings : []).filter(x => x && typeof x.key === "string" && p[x.key] != null && x.default != null && String(p[x.key]) !== String(x.default))
    .map(x => [x.label || x.key, String(p[x.key])]);
  return [["Signal", [c.symbol, bars ? bars + "-minute bars" : ""].filter(Boolean).join(" · ") || "—"], ["Window", win || "—"],
    ["Trades a day", lab.auto === true ? "its own" : l[0].v], ["Flat by", lab.auto === true ? (c.flat_et || "—") : l[4].v],
    ["On the Desk since", since(mark[1])], ...changed];
}
function labDeskView(name, s) {
  const c = s.cfg, lab = s.lab || {}, nm = stratLabel(name), busy = DESKLAB_BUSY === name;
  const set = labSetOf(name), members = set ? set.members.filter(m => ST.strategies[m]) : [name], vs = soloVs(name);
  const on = vs ? members.some(m => ST.strategies[m].cfg.enabled === true) : c.enabled === true;      // a set is ON or OFF as one unit
  const book = (ST.book && ST.book[name]) || [], row = labRowOf(s);
  const ro = vs ? members.some(m => DeskLab.readOnly(ST.strategies[m])) : DeskLab.readOnly(s);
  const lock = vs ? members.map(m => DeskLab.accountsLock(ST.strategies[m])).find(l => l.locked) || DeskLab.accountsLock(s) : DeskLab.accountsLock(s), shadow = DeskLab.inShadow(s, book);
  const sw = `<button class="switch" role="switch" aria-label="${esc(vs ? vs.name : nm)} on or off" aria-checked="${on}"
    title="${esc(DeskLab.deskSwitchTitle(s, book, ST.accounts, deskMachine()))}"
    onclick="${vs ? `toggleSet(${jsArg(vs.id)}, ${!on})` : `toggleStrat(${jsArg(name)}, ${!on})`}"></button>`;      // on the Desk: always the Desk's path, booked or not
  const pm = vs ? setPicked(vs) : name, ps = ST.strategies[pm], prow = vs ? labRowOf(ps) : row;      // the variant Results and "Matched" show
  const sub = (members.length > 1 ? plural(members.length, "variant", "variants") + " · " : "") + (row ? DeskLab.deskSpec({}, row) : "from the Lab");
  const stateNote = DeskLab.stateNote(s), winNote = DeskLab.windowNote(s);          // its window runs past the flat time: a note, never a refusal
  const who = (a) => acctShort(a), tag = (m, text) => vs ? soloVarLabel(m) + " · " + text : text;      // a set's lines say which variant
  const trades = [], refused = [], shadowLines = [], old = [];
  for (const m of members) {      // a plain strategy is its own one member; a set lists every variant's day, each line its own (never a sum)
    const sm = ST.strategies[m], lm = sm.lab || {}, rm = m === name ? row : labRowOf(sm), split = DeskLab.splitRounds(lm.rounds), M = jsArg(m);
    trades.push(...split.today.map(r => ({r, x: DeskLab.roundLine(r, who(r.account))})).map(({r, x}) =>
      `<div class="feed-row"><span class="h${x.bad ? " warn" : ""}">${esc(tag(m, x.text))}</span>${x.net == null ? "" : `<span class="t net">${esc(usdS(x.net))}</span>`}${r.check === true ? `<button class="btn btn-outline btn-sm" onclick="clearLabBlock(${M}, ${jsArg(r.account)})"${labClearing(m, r.account) ? " disabled" : ""}>${esc(DeskLab.CLEAR)}</button>` : ""}</div>` +
      (x.detail ? `<div class="feed-row"><span class="h warn">${esc(x.detail)}</span></div>` : "")));
    refused.push(...(Array.isArray(lm.refused) ? lm.refused : []).map(x => DeskLab.refusedLine(x, x && x.account ? who(x.account) : "")).map(x =>
      `<div class="feed-row"><span class="t">${esc(x.t)}</span><span class="h warn">${esc(tag(m, x.text))}</span></div>` +
      (x.detail ? `<div class="feed-row"><span class="h warn">${esc(x.detail)}</span></div>` : "")));
    const t = (rm && rm.today) || {};            // what it writes down in shadow (the chart service's summary of the day)
    if (DeskLab.inShadow(sm, (ST.book && ST.book[m]) || [])) shadowLines.push(...(Array.isArray(t.orders) ? t.orders : []).map(DeskLab.orderLine).map(o =>
        `<div class="feed-row"><span class="t">${esc(o.t)}</span><span class="h${o.refused ? " warn" : ""}">${esc(tag(m, o.text))}</span></div>`),
      ...(Array.isArray(t.trades) ? t.trades : []).map(DeskLab.tradeLine).map(x =>
        `<div class="feed-row"><span class="h">${esc(tag(m, x.text))}</span><span class="t net">${esc(usdS(x.net))}</span></div>`));
    old.push(...split.old.map(r => ({r, x: DeskLab.roundLine(r, who(r.account))})).map(({r, x}) =>
      `<div class="feed-row"><span class="h warn">${esc(tag(m, x.text))}</span>
        <button class="btn btn-outline btn-sm" onclick="clearLabBlock(${M}, ${jsArg(r.account)})"${labClearing(m, r.account) ? " disabled" : ""} title="${esc(x.text)}">${esc(DeskLab.CLEAR)}</button></div>`));
  }
  const todayAll = [...trades, ...shadowLines, ...refused];
  const today = todayAll.length ? `<div class="agroup feed static">${todayAll.join("")}</div>` : `<div class="eq-empty">${esc(DeskLab.EMPTY_DAY)}</div>`;
  const isDay = (d) => /^\d{4}-\d\d-\d\d$/.test(String(d));
  const days = (prow && Array.isArray(prow.days) ? prow.days : []).map(DeskLab.matchLine);
  const dayRows = days.map(m =>
    `<div class="feed-row"><span class="t">${esc(isDay(m.date) ? shortDay(m.date) : m.date)}</span><span class="h${m.ok === false ? " warn" : ""}">${esc(m.text)}</span>${m.rebuilt ? '<span class="t dim">rebuilt</span>' : ""}<span class="t net">${esc(usdS(m.net))}</span></div>`);
  const match = !prow ? "" : days.length
    ? `<button class="btn btn-quiet btn-sm act-link" aria-expanded="${MATCH_OPEN === pm}" onclick="toggleMatchDays(${jsArg(pm)})">${esc(matchSummary(days))} ›</button>${MATCH_OPEN === pm ? `<div class="agroup feed static">${dayRows.join("")}</div>` : ""}`
    : `<div class="mcap">${esc(matchSummary(days))}</div>`;
  const picker = !vs ? "" : `<div class="seg" role="group" aria-label="Which variant">${vs.members.map(m =>
    `<button class="${m === pm ? "sel" : ""}" aria-pressed="${m === pm}" onclick="setPickVariant(${jsArg(vs.id)}, ${jsArg(m)})">${esc(soloVarLabel(m))}</button>`).join("")}</div>`;
  const about = labSafe(() => aboutRows(name, s, row), []).map(([k, v]) => `<div class="feed-row"><span class="t">${esc(k)}</span><span class="h">${esc(v)}</span></div>`).join("");
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(vs ? vs.name : nm)}</h1><div class="sp mono">${esc(sub)}</div></div>${sw}</div>
    <div class="sd-status">${labSafe(() => statusLineHtml(name), "")}</div>
    ${stateNote ? `<div class="sd-note">${esc(stateNote)}</div>` : ""}
    ${ro ? `<div class="sd-note">${esc(DeskLab.OTHER_DESK)}</div>` : ""}
    ${labSafe(() => soloSetupHtml(name, s, ro, lock), "")}
    <div class="sec"><h2>${shadow ? "Today, in shadow" : "Today"}</h2>${today}${actBtn("s:" + name)}</div>
    ${old.length ? `<div class="sec"><h2>${esc(DeskLab.OLD_TITLE)}</h2><div class="agroup feed static">${old.join("")}</div></div>` : ""}
    ${(ps.lab || {}).name ? stratCal(pm, ps.lab.name, members.some(m => ((ST.book && ST.book[m]) || []).length > 0), match, picker) : ""}
    ${labSafe(() => deskChangesHtml("s:" + name), "")}
    <div class="sec sd-backtest"><h2>Backtest</h2><div class="agroup feed static">${labSafe(() => backtestRows(members, set), "")}</div></div>
    <div class="sec sd-about"><h2>About</h2><div class="agroup feed static">${about}</div>${winNote ? `<div class="mcap warn">${esc(winNote)}</div>` : ""}
      ${lab.auto === true ? "" : `<div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="openLabLimits(${jsArg(name)})"${ro ? " disabled" : ""}>${esc(DeskLab.EDIT_LIMITS)}</button></div>`}</div>
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="flattenStrat(${jsArg(name)})" title="Flattens its positions and switches it off">Flatten &amp; turn off</button>
      ${deskMachine() === "server" ? "" : `<button class="btn btn-outline btn-sm" onclick="openDeskLabInLab(${jsArg(lab.name || "")})" title="The Lab page, on this strategy's 3:1 out-of-sample">Open in the Lab</button>`}
      ${vs ? `<button class="btn btn-outline btn-sm" onclick="splitSet(${jsArg(vs.id)})" title="The variants become separate strategies again. No booking changes.">Split into separate strategies</button>` : ""}
      <button class="btn btn-outline btn-sm" onclick="renameLabStrat(${jsArg(name)})"${busy || ro ? " disabled" : ""} title="Change the name the Desk shows for it.">Rename</button>
      <button class="btn btn-outline btn-sm" onclick="archiveLabStrat(${jsArg(lab.name || "")}, ${jsArg(name)})"${busy || ro || !lab.name ? " disabled" : ""} title="Off the Desk, switched off, its accounts off, and kept. Restore it from Archive any time.">Archive</button>
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
function openLabLimits(name, fill) {      // fill: other limits to show (Changes' Put back: the old ones), else the ones set
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s || !s.lab || DeskLab.readOnly(s)) return;
  LAB_LIM = {name, tok: ++LAB_TOK};
  $("#llTitle").textContent = DeskLab.limitsTitle(stratLabel(name));
  const f = DeskLab.limitsFields(fill || s.lab.limits);
  for (const [k, id] of LAB_LIM_FIELDS) { $("#" + id).value = f[k]; $("#" + id).oninput = labLimSaveText; }
  labLimSaveText();
  labLimErrors({});
  const note = $("#llNote"); note.textContent = ""; note.hidden = true;
  $("#llSave").disabled = LAB_SAVING;
  showOverlay("labLimitsOverlay");
}
/* The Save button lists what changes, old → new, as the fields read now ("Save: Trades a day 2 → 3"); plain "Save limits" when
   nothing changes or none were set. */
const LAB_LIM_WORDS = {trades: "Trades a day", qty: "Contracts", risk: "At risk", last: "Last entry", flat: "Flat by"};
function labLimSaveText() {
  const s = ST && ST.strategies && ST.strategies[LAB_LIM.name], old = s && s.lab && s.lab.limits;
  const was = DeskLab.limitsFields(old), show = (k, v) => v === "" ? "none" : k === "risk" ? "$" + v.replace(/^\$/, "") : v;
  // a number field is the same number however it is written (300.00, $300); a time or a blank compares as text
  const num = (v) => v === "" ? NaN : Number(v.replace(/^\$/, "")), same = (k, v) => v === was[k] || (k !== "last" && k !== "flat" && num(v) === num(was[k]));
  const ch = old ? LAB_LIM_FIELDS.map(([k, id]) => [k, String($("#" + id).value).trim()]).filter(([k, v]) => !same(k, v))
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
/* Rename, Duplicate and the mini / micro switch (2026-10-28, owner). The Desk does the work (POST /api/lab-identity, /api/lab-duplicate) and answers a
   refusal with its own sentence. */
async function labIdentityPost(name, url, body) {
  if (DESKLAB_BUSY) return null;
  DESKLAB_BUSY = name; if (ST) render();
  let r, err = null;
  try { r = await post(url, {strategy: name, ...body}); } catch (e) { err = e || new Error("no answer"); }
  DESKLAB_BUSY = "";
  const ok = !err && r && r.ok === true;
  if (!ok) toast(DeskLab.refusalText(r, err), 7000);
  await refresh();
  loadDeskLab();
  return ok ? r : null;
}
async function renameLabStrat(name) {
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s || DESKLAB_BUSY) return;
  const ask = DeskLab.renameAsk(stratLabel(name));
  const label = await confirmDlg(ask.title, ask.body, "Rename", false, stratLabel(name));
  if (typeof label !== "string" || !label || label === stratLabel(name)) return;
  const r = await labIdentityPost(name, "/api/lab-identity", {label});
  if (r) toast(`Renamed to ${r.label}.`);
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
  if (!name || !lab || DESKLAB_BUSY) return;
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
  if (!name || DESKLAB_BUSY) return;
  const label = deskId ? stratLabel(deskId) : name;
  if (!await confirmDlg(`Archive ${label}?`, "It comes off the Desk, switched off, and its accounts come off. Its history is kept. Restore it from Archive any time.", "Archive", false)) return;
  DESKLAB_BUSY = name; if (ST) render();
  const {r, err} = await archiveSteps(name, deskId);
  DESKLAB_BUSY = "";
  if (!err && r && r.ok === true) {
    if ((VIEW.k === "strat" && VIEW.name === deskId) || (VIEW.k === "lab" && VIEW.name === name)) VIEW = {k: "archive"};
    toast(`${label} is archived. Restore it from Archive any time.`);
  } else toast(`Could not archive ${label}: ${DeskLab.refusalText(r, err)}`, 7000);
  if (deskId) await refresh();
  loadDeskLab();
}
async function archiveSteps(name, deskId) {      // the three steps for one strategy -> {r, err}; no confirm, no repaint
  let r = await chartPost("/api/tester/desklab/archive", {name}), err = null;
  if (r && r.ok === true) {
    if (deskId) { try { r = await post("/api/lab-remove", {strategy: deskId}); } catch (e) { err = e || new Error("no answer"); } }
    else r = await chartPost("/api/tester/desklab/remove", {name});
  }
  if (!err && r && r.ok === true) r = await chartPost("/api/tester/desklab/filed", {name});
  return {r, err};
}
/* DELETE from the Archive (the owner, 2026-10-22: "fully delete and remove them"): the archived copy, the strategy's history and its Lab
   draft (the draft goes to the drafts' trash). Real trades stay in the account history. A built-in is the Desk's own: no Delete. */
async function deleteArchived(name) {
  if (DESKLAB_BUSY) return;
  const w = (DESKLAB.archived || []).find(x => x.name === name), label = w ? DeskLab.label(w) : name;
  if (!await confirmDlg(`Delete ${label} for good?`, "It is wiped from the Archive and the Lab. Its shadow calendar and day records are deleted for good. Real trades stay in the account history.", "Delete", true)) return;
  DESKLAB_BUSY = name; if (ST) render();
  const r = await deleteHistory(name, true);
  DESKLAB_BUSY = "";
  toast(r && r.ok === true ? `${label} is deleted.` : `Could not delete ${label}: ${DeskLab.refusalText(r, null)}`, 7000);
  await loadDeskLab();
}
async function restoreArchived(name) {
  if (DESKLAB_BUSY) return;
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
/* The archived built-ins the sidebar hides: only one that cannot trade (OFF, no account, nothing happening today). */
function shelvedBuiltins() {
  return archivedBuiltins().filter(n => {
    const s = ST && ST.strategies && ST.strategies[n];
    return !(s && (s.cfg.enabled || ((ST.book && ST.book[n]) || []).length || ["placing", "placed", "live", "error"].includes(s.day_status)));
  });
}
async function archiveBuiltin(name) {
  const s = ST && ST.strategies && ST.strategies[name];
  if (!s || DESKLAB_BUSY) return;
  const N = stratLabel(name), book = (ST.book && ST.book[name]) || [];
  if (book.length) return toast(`${N} has accounts assigned. Take them off first.`, 7000);
  if (["placing", "placed", "live", "error"].includes(s.day_status)) return toast(`${N} cannot be archived now: it has orders or a position today.`, 7000);
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
  if (DESKLAB_BUSY) return;
  DESKLAB_BUSY = name; if (ST) render();
  const r = await chartPost("/api/tester/desklab/restore_builtin", {name});
  DESKLAB_BUSY = "";
  toast(r && r.ok === true ? `${stratLabel(name)} is back on the Desk, switched off.` : `Could not restore ${stratLabel(name)}: ${(r && r.detail) || "no answer"}`, 7000);
  await loadDeskLab();
  refresh();
}
function archiveView() {
  const row = (w) => {
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
  };
  const all = DESKLAB.archived || [];
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">Archive</h1><div class="sp">Off the Desk and switched off. Restore puts one back, switched off, with no account.</div></div></div>
    ${all.length ? `<div class="sec"><div class="agroup feed static">${all.map(row).join("")}</div></div>` : `<div class="sec"><div class="eq-empty">No archived strategies yet.</div></div>`}`;
}
/* Clear an old trade the Desk no longer owns: the Desk does it only when the account is flat and no old order is working, and says why not. */
const LAB_CLEARING = new Map();      // "strategy@account" -> Infinity while a clear is out, then when it was answered ok
const labClearing = (name, account) => { const t = LAB_CLEARING.get(name + "@" + account); return t !== undefined && (t === Infinity || Date.now() - t < 3000); };
async function clearLabBlock(name, account) {
  const key = name + "@" + account;
  if (labClearing(name, account)) return;      // one click is one clear; a double click is not two
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
    const l2h = esc(l2).replace(/([Tt]oday )([−+]?\$[\d,]+)/, (m, a, b) => `${a}<span class="amt${b[0] === "+" ? " pos" : ""}">${b}</span>`);
    $("#dayTitle").innerHTML = `${esc(l1)}<br><span title="The day's money counts closed trades only; an open position is not in it.">${l2h}</span>`;
    renderNeedsLook();
    $("#dayTl").innerHTML = dayTimeline(names);
    // an OFF strategy is not listed here (the sidebar's Off section holds it)
    $("#stratList").innerHTML = names.filter(n => sideKind(ST.strategies[n], (ST.book || {})[n] || []) !== "off").map(n => todayRow(n, ST.strategies[n])).join("")
      + labRowsHtml(w => w.enabled === true ? todayLabRow(w) : "")
      || `<div class="feed-empty" style="padding:28px 26px">No strategy is ON. Open one in the sidebar to switch it on.</div>`;
    $("#todayFoot").innerHTML = todayFoot(issues);
  } else if (VIEW.k === "strat") $("#viewStrat").innerHTML = stratView(VIEW.name);
  else if (VIEW.k === "lab") $("#viewStrat").innerHTML = labSafe(() => labView(VIEW.name), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${LAB_FAULT}</div>`);
  else if (VIEW.k === "group") $("#viewStrat").innerHTML = labSafe(() => groupView(VIEW.name), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${GROUP_FAULT}</div>`);
  else if (VIEW.k === "archive") $("#viewStrat").innerHTML = labSafe(() => archiveView(), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${LAB_FAULT}</div>`);
}

/* Set up a strategy on its own (the owner, 2026-11-02): the same card as a team's, smaller -- the accounts to tick, contracts,
   Take turns, Hold overnight and one Save (POST /api/setup: its accounts and Take turns in one go, checked whole first). ON / OFF is
   the page's own switch. A strategy in a team is set up on the team's page (the server refuses a solo save for it). */
let SOLO_DRAFT = {}, SOLO_FORMS = {}, SOLO_GEAR = {}, SOLO_PICK = {};      // the ticks/turns/hold being edited; each account's gear form the owner touched; open sheets
const soloTeam = (name) => teams().find(g => g.members.includes(name)) || null;
function soloNow(name) {      // what the desk has now, in the card's terms (a set: every variant's accounts, and which variant each is on)
  const vs = soloVs(name), ms = vs ? vs.members : [name], s = ST.strategies[name], pick = {};
  const book = ms.flatMap(m => ((ST.book || {})[m] || []).filter(r => r.account in (ST.accounts || {})).map(r => { pick[r.account] = pick[r.account] || m; return r; }));
  const now = {accounts: [...new Set(book.map(r => r.account))], qty: +(book[0] || {}).qty || +s.cfg.qty || 1, turns: ms.some(m => !!((ST.strategies[m].rotation || {}).on)), hold: book.some(r => r.hold === true)};
  return vs ? {...now, pick} : now;
}
/* the variant an account is on: the one the owner picked in its gear, else the one it is booked on, else the set's first (a plain strategy: itself) */
function soloMember(name, a) {
  const vs = soloVs(name);
  if (!vs) return name;
  const p = (SOLO_PICK[name] || {})[a];
  return vs.members.includes(p) ? p : vs.members.find(m => bookRowOf(m, a)) || name;
}
const bookRowOf = (m, a) => ((ST.book || {})[m] || []).find(r => r.account === a) || null;
const soloWords = (m, text) => soloVarLabel(m) ? soloVarLabel(m) + " · " + text : text;      // a set's row says its variant first
const soloLab = (name) => (ST.strategies[name] || {}).lab || {};
const soloContracts = (name) => soloLab(name).contracts || [];
const soloOwnWords = (name) => { const p = Number((soloLab(name).params || {}).risk); return p > 0 ? AcctSet.ownWords(p) : "its own size"; };
const soloBookRow = (name, a) => bookRowOf(soloMember(name, a), a);
/* the gear form an account opens with: its row as booked, the strategy's first contract and that contract's Most when it has none */
function soloForm0(name, a) {
  const m = soloMember(name, a), lab = soloLab(m), row = soloBookRow(name, a) || {account: a, qty: 1}, f = AcctSet.formOf(row);      // a new row is 1 contract (the server)
  const contract = row.contract || soloContracts(m)[0], most = f.most != null ? f.most : (lab.most_default_by || {})[contract];
  return {contract, size: f.size === "own" && lab.own_size !== true ? "contracts" : f.size, qty: f.qty, risk_usd: f.risk_usd, most: most == null ? "" : most};
}
const soloForm = (name, a) => (SOLO_FORMS[name] || {})[a] || soloForm0(name, a);
const soloKey = (f) => JSON.stringify([f.contract, f.size, f.size === "contracts" ? String(f.qty) : "", f.size === "risk" ? String(f.risk_usd) : "", f.size === "own" ? "" : String(f.most)]);
/* what /api/setup gets for a row the owner changed in the gear ("own" clears the size) */
function soloEntry(f) {
  const n = (v) => { const x = Math.round(cycNum(v)); return Number.isFinite(x) && String(v).trim() !== "" ? x : null; }, e = {contract: f.contract};
  if (f.size === "own") return {...e, size: null, most: null, risk_usd: null};
  return {...e, size: f.size, ...(f.size === "risk" ? {risk_usd: n(f.risk_usd)} : {qty: n(f.qty) == null ? null : Math.max(1, n(f.qty))}), most: n(f.most)};
}
/* a changed row whose chosen size box is empty, not whole or below 1: Save says so and sends nothing (the server keeps the old count) */
function soloBad(name, b) {
  for (const a of Object.keys(b.settings || {})) {
    const f = soloForm(name, a);
    if (f.size === "contracts" && !(/^\s*\d+\s*$/.test(String(f.qty)) && +f.qty >= 1)) return "Contracts: a whole number above 0.";
    if (f.size === "risk" && !(cycNum(f.risk_usd) > 0)) return "$ risk: a number above 0.";
  }
  return "";
}
function soloMake(name, accounts, turns, hold) {      // settings[account] only for ticked rows the owner changed in the gear
  const settings = {};
  for (const a of accounts) { const f = (SOLO_FORMS[name] || {})[a]; if (f && soloKey(f) !== soloKey(soloForm0(name, a))) settings[a] = soloEntry(f); }
  const vs = soloVs(name);
  return vs ? {set: vs.id, strategy: name, accounts, pick: Object.fromEntries(accounts.map(a => [a, soloMember(name, a)])), turns, hold, settings}
    : {strategy: name, accounts, turns, hold, settings};      // no qty: a booked row keeps its own, a new one is 1
}
const soloMem = (b, a) => b.pick ? b.pick[a] : b.strategy;      // the strategy an account of this body runs
function soloBody(name) {
  const root = document.querySelector("#viewStrat"), q = (sel) => root && root.querySelector(sel), now = soloNow(name);
  const accounts = [...(root ? root.querySelectorAll(".solo-acct") : [])].filter(b => b.checked).map(b => b.dataset.acct);
  return soloMake(name, accounts, q(".solo-turns") ? q(".solo-turns").checked : now.turns, q(".solo-hold") ? q(".solo-hold").checked : now.hold);
}
const soloEntryWords = (m, e) => soloWords(m, e.size == null ? soloOwnWords(m) : AcctSet.words({...e, qty: e.qty || 1}, undefined, true));
function soloDiff(now, b) {
  const added = (a) => {      // a ticked-in account with the size it will be saved with
    const m = soloMem(b, a), e = (b.settings || {})[a], lab = soloLab(m), c = soloContracts(m)[0];
    return `+${acctShort(a)} (${e ? soloEntryWords(m, e) : soloWords(m, lab.own_size === true ? soloOwnWords(m) : AcctSet.words({qty: 1, contract: c}))})`;
  };
  const moved = (a) => now.pick && b.pick && now.pick[a] && b.pick[a] !== now.pick[a];      // an account booked on one variant, picked on another
  const parts = [...b.accounts.filter(a => !now.accounts.includes(a)).map(added),
                 ...now.accounts.filter(a => !b.accounts.includes(a)).map(a => "−" + acctShort(a)),
                 ...b.accounts.filter(a => now.accounts.includes(a) && moved(a)).map(a => `${acctShort(a)} → ${soloVarLabel(b.pick[a])}`),
                 ...Object.entries(b.settings || {}).filter(([a]) => now.accounts.includes(a) && !moved(a)).map(([a, e]) => `${acctShort(a)} ${soloEntryWords(soloMem(b, a), e)}`)];
  if (b.turns !== now.turns) parts.push(b.turns ? "take turns" : "every account");
  if (b.hold !== now.hold) parts.push(b.hold ? "holds overnight" : "flat each night");
  const vs = b.set && soloVs(b.strategy);      // a Save writes the set's state to every member: say which it switches
  if (vs && parts.length && vs.members.some(m => ST.strategies[m].cfg.enabled === true))
    parts.push(...vs.members.filter(m => ST.strategies[m].cfg.enabled !== true).map(m => "turns on " + soloVarLabel(m)));
  return parts;
}
const soloSaveHtml = (name, parts) => parts.length ? `<div class="sd-actions"><button class="btn btn-default btn-sm" onclick="FREEZE=false;saveSolo(${jsArg(name)})">Save: ${esc(parts.join(" · "))}</button></div>` : "";
function soloEdit(name) {
  const root = document.querySelector("#viewStrat");
  if (!root) return;
  const b = soloBody(name), parts = soloDiff(soloNow(name), b);
  if (parts.length) SOLO_DRAFT[name] = {accounts: b.accounts, turns: b.turns, hold: b.hold};
  else { delete SOLO_DRAFT[name]; delete SOLO_PICK[name]; }
  const slot = root.querySelector(".solo-save");
  if (slot) slot.innerHTML = soloSaveHtml(name, parts);
  for (const el of root.querySelectorAll(".solo-words")) if (b.accounts.includes(el.dataset.acct)) el.textContent = soloRowWords(name, b, el.dataset.acct);      // in place while typing
}
function soloPaint(name) {      // the card again from the draft (ticks, gear): never while a number is being typed in
  const card = document.querySelector("#viewStrat") && document.querySelector("#viewStrat").querySelector(".solo-card");
  if (card) card.innerHTML = soloCardHtml(name, ST.strategies[name], soloNow(name));
}
function soloTick(name) {
  const root = document.querySelector("#viewStrat"), f = SOLO_FORMS[name];
  if (root) for (const b of root.querySelectorAll(".solo-acct")) if (!b.checked) { if (f) delete f[b.dataset.acct]; if (SOLO_PICK[name]) delete SOLO_PICK[name][b.dataset.acct]; }      // unticked: its gear form and variant go
  soloEdit(name); soloPaint(name);
}
function soloGear(name, a) {
  const g = SOLO_GEAR[name] = SOLO_GEAR[name] || {};
  if (g[a]) delete g[a]; else g[a] = true;
  soloPaint(name);
}
/* one field of an account's gear form: contract (back to 1 contract, that contract's Most), size, or a typed number (no repaint) */
function soloSet(name, a, k, v, typing) {
  const f = (SOLO_FORMS[name] = SOLO_FORMS[name] || {}), cur = soloForm(name, a);
  f[a] = k === "contract" ? (v === cur.contract ? cur : AcctSet.switchContract(cur, v, soloLab(soloMember(name, a)).most_default_by || {})) : {...cur, [k]: v};
  soloEdit(name);
  if (!typing) soloPaint(name);
}
function soloPick(name, a, m) {      // the gear's Variant: the account runs another variant; its size form starts over from that variant's row
  if (soloMember(name, a) === m) return;
  (SOLO_PICK[name] = SOLO_PICK[name] || {})[a] = m;
  if (SOLO_FORMS[name]) delete SOLO_FORMS[name][a];
  soloEdit(name); soloPaint(name);
}
const soloSeg = (label, opts, cur, fn) => `<div class="seg" role="group" aria-label="${esc(label)}">${opts.map(([v, t]) =>
  `<button type="button" class="${v === cur ? "sel" : ""}" aria-pressed="${v === cur}" onclick="${fn(v)}">${esc(t)}</button>`).join("")}</div>`;
function soloSheet(name, a) {      // the gear's sheet under the row (a set: Variant first)
  const m = soloMember(name, a), vs = soloVs(name), f = soloForm(name, a), cs = soloContracts(m), lab = soloLab(m), N = jsArg(name), A = jsArg(a);
  const num = (k, v, label) => `<input type="text" inputmode="numeric" autocomplete="off" aria-label="${esc(label)}" value="${esc(String(v))}" style="width:72px;text-align:right"
    onfocus="FREEZE=true" onblur="FREEZE=false" oninput="soloSet(${N},${A},'${k}',this.value,true)">`;
  const row = (h, body) => `<div class="feed-row"><span class="h">${esc(h)}</span><span class="t">${body}</span></div>`;
  const sizes = [...(lab.own_size === true ? [["own", "Its own"]] : []), ["contracts", "Contracts"], ["risk", "$ risk"]];
  return `<div class="solo-sheet">
    ${vs ? row("Variant", soloSeg("Variant", vs.members.map(x => [x, soloVarLabel(x)]), m, x => `soloPick(${N},${A},${jsArg(x)})`)) : ""}
    ${cs.length > 1 ? row("Contract", soloSeg("Contract", cs.map(c => [c, c]), f.contract, c => `soloSet(${N},${A},'contract','${c}')`)) : ""}
    ${row("Size", soloSeg("Size", sizes, f.size, v => `soloSet(${N},${A},'size','${v}')`) + (f.size === "own" ? "" : " " + (f.size === "risk" ? num("risk_usd", f.risk_usd, "$ risk a trade") : num("qty", f.qty, "Contracts"))))}
    ${f.size === "own" ? "" : row("Most contracts", num("most", f.most, "Most contracts"))}</div>`;
}
function soloRowWords(name, b, a) {      // a ticked row's summary: the gear's change, else the row as booked
  const m = soloMem(b, a);
  if (b.settings[a]) return soloEntryWords(m, b.settings[a]);
  const r = soloBookRow(name, a);
  return !r ? soloWords(m, "") .replace(/ · $/, "") : soloWords(m, !r.size && soloLab(m).own_size === true ? soloOwnWords(m) : AcctSet.words(r, undefined, true));
}
function soloCardHtml(name, s, now) {
  const accts = ST.accounts || {}, dr = SOLO_DRAFT[name] || null, chosen = new Set(dr ? dr.accounts : now.accounts), off = ` onchange="soloTick(${jsArg(name)})"`;
  const gear = SOLO_GEAR[name] || {}, b = soloMake(name, [...chosen], dr ? dr.turns : now.turns, dr ? dr.hold : now.hold);
  const words = (a) => chosen.has(a) ? soloRowWords(name, b, a) : "";
  const rows = Object.keys(accts).map(a => `<div class="solo-row"><div class="feed-row">
      <label class="h" style="cursor:pointer"><input type="checkbox" class="solo-acct" data-acct="${esc(a)}" ${chosen.has(a) ? "checked" : ""}${off}> ${esc(acctShort(a))}
        ${ACCT_TAG_HTML[acctTag(a)]}${accts[a].connected ? "" : ' <span class="neg">offline</span>'}</label>
      <span class="mcap solo-words" data-acct="${esc(a)}">${esc(words(a))}</span>
      ${(p => p == null ? "" : `<span class="mono ${p > 0 ? "pos" : p < 0 ? "neg" : ""}" style="margin-left:auto" title="Today, 18:00 to 16:00 ET">${DAY_PNL_WORDS(p)}</span>`)(accts[a].day_pnl)}
      ${chosen.has(a) ? `<button type="button" class="btn btn-outline btn-sm" aria-label="Settings for ${esc(acctShort(a))}" aria-expanded="${!!gear[a]}" onclick="soloGear(${jsArg(name)},${jsArg(a)})">⚙</button>` : ""}</div>
      ${chosen.has(a) && gear[a] ? soloSheet(name, a) : ""}</div>`).join("");
  return `<div class="agroup feed static">${rows}
    ${chosen.size > 1 ? `<label class="feed-row" style="cursor:pointer" title="Each trade goes to ONE account, the next free one"><span class="h"><input type="checkbox" class="solo-turns" ${b.turns ? "checked" : ""}${off}> Take turns: one account a trade</span></label>` : ""}
    <label class="feed-row" style="cursor:pointer" title="Keeps a filled trade open past the day's flat time"><span class="h"><input type="checkbox" class="solo-hold" ${b.hold ? "checked" : ""}${off}> Hold overnight</span></label></div>
    <div class="solo-save">${dr ? soloSaveHtml(name, soloDiff(now, b)) : ""}</div>${chosen.size ? "" : `<div class="mcap">No account ticked: it runs in shadow.</div>`}`;
}
function soloSetupHtml(name, s, ro, lock) {
  const team = soloTeam(name), mine = labSetOf(name), first = mine && mine.members.filter(m => ST.strategies[m])[0];
  if (first && first !== name) return `<div class="sec"><h2>Set up</h2><div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="setView('strat',${jsArg(first)})">In set ${esc(mine.name)} → open</button></div></div>`;
  if (team) return `<div class="sec"><h2>Set up</h2><div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="setView('group',${jsArg(team.id)})">In team ${esc(team.name)} → open</button></div></div>`;
  // no verdict here: the page's one status line (statusLine) says whether it trades; the card only says why it cannot be edited
  const accts = ST.accounts || {}, now = soloNow(name);
  if (!Object.keys(accts).length) return `<div class="sec"><h2>Set up</h2><div class="mcap">Add an account to run this strategy.</div></div>`;
  if (ro || lock.locked) return `<div class="sec"><h2>Set up</h2><div class="mcap">${esc(lock.caption || DeskLab.OTHER_DESK)}</div></div>`;
  return `<div class="sec"><h2>Set up</h2><div class="solo-card">${soloCardHtml(name, s, now)}</div></div>`;
}
/* A set's switch: the whole set, one call (/api/setup with the accounts and picks as booked; OFF stops and disables every member).
   ON asks once, over every member it turns on and the non-paper accounts they run. */
async function toggleSet(id, on) {
  const vs = ((ST.variants && ST.variants.sets) || []).find(x => x.id === id), first = vs && soloVs(vs.members[0]);
  if (!first || switchBounced("set:" + id)) return;
  const now = soloNow(first.members[0]), N = first.name;
  const turning = first.members.filter(m => ST.strategies[m].cfg.enabled !== true);
  const real = turning.map(m => [m, now.accounts.filter(a => now.pick[a] === m && isRealAcct(a))]).filter(([, a]) => a.length);
  if (on && real.length && !await confirmDlg(`Turn ON ${N}?`, real.map(([m, a]) => `${soloVarLabel(m)}: ${riskWord(a)} account${a.length === 1 ? "" : "s"} ${a.map(acctShort).join(", ")}.`).join(" ") +
      " It will run and execute on its assigned accounts from the next signal.", "Turn on", false)) { refresh(); return; }
  let r, err = null;
  try { r = await post("/api/setup", {set: id, accounts: now.accounts, pick: now.pick, settings: {}, turns: now.turns, hold: null, on}); } catch (e) { err = e || new Error("no answer"); }
  const w = answerWhy(r, err);
  refresh();
  if (w && !on) alertBar(`${N} NOT switched off — ${w}. It may still trade: switch it off again, or Kill.`);      // the safe side: stays on screen
  else toast(w ? `${N} NOT switched on — ${w}.` : `${N} is ${on ? "ON." : "OFF."}`, w ? 8000 : 4200);
}
/* Asks first when (ON, on any account that is not paper -- LIVE or DEMO, as its tag says): one is ticked in; a row's gear can
   send more (AcctSet.needsAsk: NQ instead of MNQ, bigger size, Most up); it stops taking turns; or it loses its last account
   while ON (today is over for it; it trades again tomorrow). */
async function saveSolo(name) {
  const s = ST.strategies[name], vs = soloVs(name), now = soloNow(name), b = soloBody(name), N = vs ? vs.name : stratLabel(name);
  const bad = soloBad(name, b);
  if (bad) { toast(`${N} NOT saved — ${bad}`, 8000); return; }
  const on = vs ? vs.members.some(m => ST.strategies[m].cfg.enabled === true) : s.cfg.enabled === true;      // a set keeps what trades trading
  const parts = soloDiff(now, b), liveIn = b.accounts.filter(a => !now.accounts.includes(a) && isRealAcct(a)), live = b.accounts.filter(isRealAcct);
  const orderOf = (m) => { const mb = soloLab(m).most_default_by || {}; return [...soloContracts(m)].sort((x, y) => (mb[y] || 0) - (mb[x] || 0)); };      // the micro first
  const moved = (a) => !!(now.pick && now.pick[a] && b.pick[a] !== now.pick[a]);
  const why = [];
  if (on && liveIn.length) why.push(`${riskWord(liveIn)} account${liveIn.length === 1 ? "" : "s"} ticked in: ${liveIn.map(acctShort).join(", ")}.`);
  for (const [a, e] of Object.entries(b.settings)) {
    if (on && moved(a) && isRealAcct(a)) { why.push(`${acctShort(a)}: ${soloEntryWords(b.pick[a], e)}.`); continue; }
    const r = soloBookRow(name, a);
    if (!on || !r || liveIn.includes(a) || moved(a)) continue;
    const next = {account: a, qty: e.qty || r.qty || 1, contract: e.contract, ...(e.size ? {size: e.size, most: e.most} : {}), ...(e.size === "risk" ? {risk_usd: e.risk_usd} : {})};
    if (AcctSet.needsAsk({...r, contract: r.contract || orderOf(soloMem(b, a))[0]}, next, isRealAcct(a), orderOf(soloMem(b, a)))) why.push(`${acctShort(a)}: ${soloEntryWords(soloMem(b, a), e)}.`);
  }
  for (const a of b.accounts) if (on && moved(a) && isRealAcct(a) && !(b.settings[a])) why.push(`${acctShort(a)} moves to ${soloVarLabel(b.pick[a])}.`);
  if (on && !b.turns && now.turns && live.length && b.accounts.length > 1) why.push(`Each trade then goes to all ${b.accounts.length} accounts, ${riskWord(live)} ones included.`);
  if (vs && on) for (const m of vs.members.filter(m => ST.strategies[m].cfg.enabled !== true)) {      // switched ON by this Save
    const a = b.accounts.filter(x => b.pick[x] === m && isRealAcct(x));
    if (a.length) why.push(`${soloVarLabel(m)} turns on: ${riskWord(a)} account${a.length === 1 ? "" : "s"} ${a.map(acctShort).join(", ")}.`);
  }
  if (on && now.accounts.length && !b.accounts.length) why.push("It loses its last account: today is over for it; it trades again tomorrow.");
  if (why.length && !await confirmDlg(`Change ${N}?`, `${parts.join(" · ")}. ${why.join(" ")}${machineWords() ? " It runs " + machineWords() + "." : ""}`, "Save", false)) { refresh(); return; }
  let r, err = null;
  const {strategy: _s, ...sent} = b;      // the set body names the set, not a strategy
  const hold = b.hold === now.hold ? null : b.hold;      // Hold overnight only when this Save changed the box; else each row keeps its own
  try { r = await post("/api/setup", {...(vs ? sent : b), hold, on}); } catch (e) { err = e || new Error("no answer"); }
  const w = answerWhy(r, err);
  if (w === "") { delete SOLO_DRAFT[name]; delete SOLO_FORMS[name]; delete SOLO_PICK[name]; }
  refresh();
  toast(w ? `${N} NOT saved — ${w}.` : `${N} saved.`, w ? 8000 : 4200);
}

function render() {
  const s = ST;
  $("#clock").textContent = hbClock(String(s.et_now).slice(11, 19)) + " ET";
  renderMaster();
  renderMachineChip();
  renderChartTrading(s.chart_trading);
  if ($("#settingsOverlay").classList.contains("open")) renderSettings();

  // readiness: the bulb and the toolbar word here; the list itself is Today's "Needs a look" (renderNeedsLook, with renderMain)
  const r = readinessShown(s.readiness, s);   // a "no signal" that could not have fired reads as info (W4)
  renderBulb(r);
  const probs = r ? r.checks.filter(c => c.level === "bad" || c.level === "warn") : [];

  const shelved = shelvedBuiltins();       // an archived built-in lives in Archive, unless it can trade
  const names = Object.keys(s.strategies).filter(n => !shelved.includes(n))
    .sort((a, b) => (s.strategies[b].cfg.enabled ? 1 : 0) - (s.strategies[a].cfg.enabled ? 1 : 0));   // switched-on first
  if (VIEW.k === "lab" && labSafe(() => DeskLab.onDesk(s.strategies, {name: VIEW.name}), false)) VIEW = {k: "strat", name: "lab_" + VIEW.name};   // the Desk knows it now: its own page
  if (VIEW.k === "strat" && !names.includes(VIEW.name)) VIEW = {k: "today"};
  if (VIEW.k === "group" && !groupOf(VIEW.name)) VIEW = {k: "today"};      // a group removed (here or elsewhere)
  ISSUE_LVL = probs.some(c => c.level === "bad") ? "bad" : "warn";
  renderSide(names, probs.length);
  renderMain(names, probs.length);
  // the views were rebuilt: an + Assign menu that lived in them is gone -- so is its hold on updates
  if (ASG_OPEN && !document.contains(ASG_OPEN.menu)) {
    ASG_OPEN = null;
    if (!document.getElementById("qedit")) FREEZE = false;
  }
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
      renderMaster(); renderNeedsLook();
    }
    return;
  }
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
    renderMaster(); renderNeedsLook(); renderStatusLine();
    if ($("#settingsOverlay").classList.contains("open")) renderSettings();
  }
}
