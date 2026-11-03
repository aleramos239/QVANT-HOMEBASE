/* ---- DESK GROUPS (2026-10-11): named sets of strategies that run together (an eval group, a funded group ...), kept by the chart
   service (GET /api/tester/deskgroups). A group trades only through its ACCOUNT CYCLE (cycleHtml below; the Desk's engine keeps it, and
   the chart service makes it follow every rename, move and delete, server side). Group ids are never reused. A
   strategy is in ONE group at most; the same code tried two ways (say for an eval and for a funded account) is two strategies, each
   in its own group. A group's combined results are its members' SAVED runs put together as one account's trades
   (GET /api/tester/deskgroups/results, asked only while a group's page is open). The words are DeskLab.groupPage. ---- */
let DESKGROUPS = {groups: [], ok: null}, DESKGROUPS_BUSY = false;       // ok: null = no read finished yet
let DESKGRES = {}, DESKGRES_BUSY = false;
const GROUP_ID = /^g\d{1,4}$/;
const groupOf = (id) => DESKGROUPS.groups.find(g => g.id === id) || null;
function takeGroups(list) {      // only well-formed groups are kept; a wrong shape is dropped, never thrown on
  return (Array.isArray(list) ? list : []).filter(g => g && typeof g === "object" && GROUP_ID.test(String(g.id)) && typeof g.name === "string")
    .map(g => ({id: g.id, name: g.name, kind: ["eval", "funded", "together"].includes(g.kind) ? g.kind : "together",
      members: (Array.isArray(g.members) ? g.members : []).filter(m => typeof m === "string")}));
}
async function loadDeskGroups() {
  if (DEMO || document.hidden || DESKGROUPS_BUSY) return;
  DESKGROUPS_BUSY = true;
  try {
    const r = await fetch(CHART + "/api/tester/deskgroups");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), next = takeGroups(j && j.groups);
    const changed = DESKGROUPS.ok !== true || JSON.stringify(next) !== JSON.stringify(DESKGROUPS.groups);
    DESKGROUPS = {groups: next, ok: true};
    if (changed && ST && !FREEZE) render();
    if (VIEW.k === "group") loadDeskGroupRes();
  } catch (_) { /* the chart service does not answer: keep what was shown */ }
  finally { DESKGROUPS_BUSY = false; }
}
async function loadDeskGroupRes() {
  if (DEMO || document.hidden || DESKGRES_BUSY || VIEW.k !== "group") return;
  DESKGRES_BUSY = true;
  try {
    const r = await fetch(CHART + "/api/tester/deskgroups/results");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), next = j && j.results && typeof j.results === "object" ? j.results : {};
    const changed = JSON.stringify(next) !== JSON.stringify(DESKGRES);
    DESKGRES = next;
    if (changed && ST && !FREEZE) render();
  } catch (_) { /* keep what was shown */ }
  finally { DESKGRES_BUSY = false; }
}
/* One change to the groups: create {name, kind} | rename {id, name} | kind {id, kind} | delete {id} | move {strategy, group|null}.
   The service answers with all the groups; a refusal says why in words and changes nothing. */
async function groupPost(action, body) {
  const r = await chartPost("/api/tester/deskgroups/" + action, body);
  if (r && r.ok === true && Array.isArray(r.groups)) {
    DESKGROUPS = {groups: takeGroups(r.groups), ok: true};
    if (VIEW.k === "group" && !groupOf(VIEW.name)) VIEW = {k: "today"};
    if (ST) render();
    renderGroupMgr(true);
    loadDeskGroupRes();
    return true;
  }
  if (!DEMO) toast(String((r && r.detail) || "The group could not be changed."), 6000);
  renderGroupMgr(true);          // put the controls back as they were
  return false;
}
/* A group's page (VIEW {k: "group", name: <id>}): its members' saved runs put together -- the unseen days first (curve), the build days
   beside them, the prop sim on LucidPro -- then the members and any left out of the sum, with why. Nothing here runs a backtest. */
const GROUP_FAULT = "The group could not be shown.";
function openGroupMember(id) {      // a member's own page: the Desk's if it holds it, else the Lab strategy's
  id = String(id);
  if (ST && ST.strategies && ST.strategies[id]) setView("strat", id);
  else if (id.indexOf("lab_") === 0) setView("lab", id.slice(4));
  else setView("today");
}
function groupView(id) {
  const g = groupOf(id);
  if (!g) return `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${esc(DeskLab.GROUP_MISSING)}</div>`;
  const p = DeskLab.groupPage(g, DESKGRES[g.id]);
  const cell = (x) => `<div class="v mono">${esc(x)}</div>`;
  const f = (k, vals, head) => `<div class="${head ? "f fh" : "f"}"><div class="k">${esc(k)}</div>${vals.map(cell).join("")}</div>`;
  const note = (t) => `<div class="labres-note">${esc(t)}</div>`;
  const two = (b) => !b.rows.length ? note(b.note) : b.head ? f("", b.head, true) + b.rows.map(r => f(r.k, "both" in r ? [r.build, r.unseen, r.both] : [r.build, r.unseen])).join("")
    : b.rows.map(r => f(r.k, [r.v])).join("");      // the full sample (Both) only: one column, no head (owner 2026-10-30)
  const three = (b) => b.head && b.head.length === 3 ? " three" : "";
  const days = p.days.rows.length ? p.days.rows.map(r => f(r.k, [r.v])).join("") : note(p.figs.note);
  const members = p.members.map(m => `<div class="feed-row" role="button" tabindex="0" onclick="openGroupMember(${jsArg(m.strategy)})"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openGroupMember(${jsArg(m.strategy)})}">
      <span class="h">${esc(m.label)}${m.state ? ` · <span class="dim">${esc(m.state)}</span>` : ""}</span>
      ${p.membersFull ? "" : `<span class="t dim">${esc(m.build)}</span>`}<span class="t net">${esc(p.membersFull ? m.full : m.unseen)}</span></div>`);
  const out = p.leftOut.map(x => `<div class="feed-row"><span class="h">${esc(x.label)}</span><span class="t dim">${esc(x.why)}</span></div>`);
  const curve = p.curve ? `<div class="sec"><h2>${esc(p.curve.title)}</h2>${eqPlot(p.curve.vals, p.curve.label, p.curve.total, p.curve.aria, p.curve.ends, p.curve.days, p.curve.notes, p.curve.build, p.curve.both)}</div>` : "";
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(p.title)}</h1><div class="sp mono">${esc(p.lead)}</div></div></div>
    <div class="sd-state"><b>${esc(p.kind)}</b> · ${esc(p.kindNote)}</div>
    <div class="sd-note">${esc(p.note)}</div>
    ${actBtn("g:" + g.id)}
    ${p.empty ? `<div class="eq-empty">${esc(DeskLab.EMPTY_GROUP)}</div>` : ""}
    ${curve}
    <div class="figs labres-prop${p.figs.full ? "" : " grp-figs"}${three(p.figs)}" data-h="${p.figs.full ? "Full sample" : "Combined, after costs"}">${two(p.figs)}</div>
    <div class="labres" data-for="${esc(g.id)}">
      ${p.figs.full ? "" : `<div class="sec"><h2>${esc(p.days.title)}</h2><div class="figs labres-unseen" data-h="${esc(p.days.title)}">${days}</div></div>`}
      <div class="sec"><h2>${esc(p.prop.title)}</h2><div class="figs labres-prop${three(p.prop)}" data-h="${esc(p.prop.title)}">${two(p.prop)}</div></div></div>
    ${members.length ? `<div class="sec"><h2>Strategies</h2><div class="agroup feed static">
      <div class="feed-row"><span class="h dim">Strategy</span>${p.membersFull ? `<span class="t dim">Full sample</span>` : `<span class="t dim">Build</span><span class="t dim">Unseen</span>`}</div>${members.join("")}</div></div>` : ""}
    ${out.length ? `<div class="sec"><h2>Left out of the sum</h2><div class="agroup feed static">${out.join("")}</div></div>` : ""}
    ${labSafe(() => cycleHtml(g), "")}
    ${labSafe(() => groupTodayHtml(g), "")}
    ${labSafe(() => deskChangesHtml("g:" + g.id), "")}
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="openGroupMgr()">Manage groups</button>
      <button class="btn btn-outline btn-sm" onclick="deleteGroup(${jsArg(g.id)})" title="The strategies stay on the Desk, in no group.">Delete group</button></div>`;
}
/* Set up a team (the owner, 2026-11-02: "easy to set up impossible to get confused and mess it up"). A team = this Desk group
   and its account group, always together. ONE card: the accounts to tick, how they share the trades, the size, Hold overnight
   per strategy, ONE Trading switch and ONE Save. Both send the whole card to POST /api/setup, which writes the account group,
   every strategy's accounts and ON / OFF in one go, checked whole first (a refusal writes nothing). A strategy in a team
   trades only the team's accounts; one that leaves the group loses them (the server does both). */
function cycleMembers(g) {
  return (g.members || []).filter(m => ST.strategies[m] && ST.strategies[m].cfg.kind === "lab");
}
/* What is typed or ticked but not saved is kept here, per team, so a repaint never wipes it. */
let CYC_DRAFT = {};
const cycNum = (s) => Number(String(s).replace(/[$,\s]/g, ""));   // "$1,500" -> 1500
// A member's dollars at risk in a team: its own amount (risk_by), else the team's (engine_groups.member_risk)
const cycRisk = (g, m) => Number(((g && g.risk_by) || {})[m]) || Number(g && g.risk_usd) || 0;
/* Three ways a team trades its accounts (owner, 2026-10-30); the hedge block covers its accounts in every one. */
const CYC_MODES = {cycle: "Take turns: one account a trade", share: "Every account takes every trade", split: "One account each"};
const cycMode = (g) => (g && CYC_MODES[g.mode]) ? g.mode : "cycle";
const cycUsd = (v) => Number.isFinite(v) ? "$" + v.toLocaleString("en-US") : "?";
const cycleEnvWord = (a) => !isDemoAcct(a) ? "LIVE" : ((((ST && ST.accounts) || {})[a] || {}).env === "paper" ? "PAPER" : "DEMO");
/* The word for accounts that are not paper (the ones a save asks about), as their tags say: LIVE if one is, else DEMO. */
const riskWord = (as) => as.some(a => cycleEnvWord(a) === "LIVE") ? "LIVE" : "DEMO";
const holdOf = (m) => ((ST.book || {})[m] || []).some(r => r.hold === true);
const teamOn = (mem) => mem.length > 0 && mem.every(m => ST.strategies[m].cfg.enabled === true);
/* The accounts each strategy ends on after a save (as routes/setup.team_books): the team's ticked ones, or (One account each) its own. */
const teamWant = (b, m) => (b.mode || "cycle") === "split" ? ((b.assign || {})[m] ? [b.assign[m]] : []) : b.accounts;
// accounts a member is booked on that the team does not give it (booked before it joined): a save takes them off
const teamStray = (b, m) => ((ST.book || {})[m] || []).map(r => r.account).filter(a => a in (ST.accounts || {}) && !teamWant(b, m).includes(a));
/* What a save would change, against what the desk has now (no team yet: the card's defaults, $1,000 and 17, no account).
   up: risk or Most goes up -- or risk goes to 0 ("each strategy's own size"), which may be bigger, so it counts as up. */
function cycleDiff(cyc, nw) {
  const old = cyc ? {risk: cyc.risk_usd, minis: cyc.max_minis, accounts: cyc.accounts || [], by: cyc.risk_by || {}, mode: cycMode(cyc), assign: cyc.assign || {}, members: cyc.members || []}
                  : {risk: 1000, minis: 17, accounts: [], by: {}, mode: "cycle", assign: {}, members: []};
  const mode = nw.mode || old.mode, assign = nw.assign || old.assign;     // no box sent: the desk's own stay
  const was = {risk_usd: old.risk, risk_by: old.by}, by = nw.risk_by || old.by;     // no boxes sent: the desk's own amounts stay
  // an account the Desk removed is not "gone" by a save: no tick can show it, and the save never sends it (cycleBody)
  const added = nw.accounts.filter(a => !old.accounts.includes(a)), gone = old.accounts.filter(a => a in ((ST && ST.accounts) || {}) && !nw.accounts.includes(a));
  const parts = [];
  for (const m of (nw.members || []).filter(m => !old.members.includes(m))) parts.push(`+ ${stratLabel(m)}`);
  if (nw.risk_usd !== old.risk) parts.push(`Risk ${cycUsd(old.risk)} → ${cycUsd(nw.risk_usd)}`);
  const own = [...new Set([...Object.keys(old.by), ...Object.keys(by)])].filter(m => (+old.by[m] || 0) !== (+by[m] || 0));
  for (const m of own) parts.push(`${stratLabel(m)} ${cycUsd(cycRisk(was, m))} → ${cycUsd(cycRisk(nw, m))}`);
  if (nw.max_minis !== old.minis) parts.push(`Most ${old.minis} → ${Number.isFinite(nw.max_minis) ? nw.max_minis : "?"}`);
  if (mode !== old.mode) parts.push(`${CYC_MODES[old.mode]} → ${CYC_MODES[mode]}`);
  const moved = [...new Set([...Object.keys(old.assign), ...Object.keys(assign)])].filter(m => (old.assign[m] || "") !== (assign[m] || ""));
  for (const m of moved) parts.push(`${stratLabel(m)} on ${old.assign[m] ? acctShort(old.assign[m]) : "no account"} → ${assign[m] ? acctShort(assign[m]) : "no account"}`);
  for (const a of added) parts.push("+" + acctShort(a));
  for (const a of gone) parts.push("−" + acctShort(a));
  for (const m of (nw.members || []).filter(m => !moved.includes(m))) {
    const off = teamStray({mode, assign, accounts: nw.accounts}, m).filter(a => !gone.includes(a));
    if (off.length) parts.push(`${stratLabel(m)} off ${off.map(acctShort).join(", ")}`);
  }
  const held = Object.entries(nw.hold || {}).filter(([m, h]) => h !== holdOf(m));
  for (const [m, h] of held) parts.push(`${stratLabel(m)} ${h ? "holds overnight" : "flat each night"}`);
  const members = [...new Set([...old.members, ...(nw.members || []), ...Object.keys(by)])];
  const up = !(nw.risk_usd <= old.risk) || (old.risk > 0 && nw.risk_usd === 0) || !(nw.max_minis <= old.minis)
    || members.some(m => !(cycRisk(nw, m) <= cycRisk(was, m)) || (cycRisk(was, m) > 0 && cycRisk(nw, m) === 0))
    || (mode === "share" && old.mode !== "share") || moved.some(m => assign[m]) || held.some(([, h]) => h);
  return {parts, up, liveIn: added.filter(isRealAcct)};
}
const cycByBody = (raw) => Object.fromEntries(Object.entries(raw || {}).filter(([, v]) => String(v).trim() !== "").map(([m, v]) => [m, cycNum(v)]));
const cycleDraftBody = (dr) => ({members: dr.members || [], risk_usd: cycNum(dr.risk), risk_by: cycByBody(dr.by), max_minis: Math.round(cycNum(dr.minis)),
                                 ...(dr.mode ? {mode: dr.mode} : {}), ...(dr.assign ? {assign: dr.assign} : {}), ...(dr.hold ? {hold: dr.hold} : {}),
                                 accounts: dr.accounts.filter(a => a in ((ST && ST.accounts) || {}))});   // as cycleBody reads the ticks
function cycleSaveHtml(id, cyc, nw) {
  const d = nw ? cycleDiff(cyc, nw) : {parts: []};
  return d.parts.length ? `<div class="sd-actions"><button class="btn btn-default btn-sm" onclick="FREEZE=false;saveCycle(${jsArg(id)})">Save: ${esc(d.parts.join(" · "))}</button></div>` : "";
}
/* A keystroke or a tick: keep it as the draft and show (or hide) the Save button in place -- the inputs are never redrawn. */
function cycleEdit(id) {
  const root = document.querySelector("#viewStrat");
  if (!root) return;
  const raw = (sel) => { const el = root.querySelector(sel); return el ? String(el.value) : ""; };
  const b = cycleBody(id), cyc = ((ST && ST.groups) || {})[id] || null;
  const by = Object.fromEntries([...root.querySelectorAll(".cyc-risk-m")].map(el => [el.dataset.m, String(el.value)]));
  if (cycleDiff(cyc, b).parts.length) CYC_DRAFT[id] = {risk: raw(".cyc-risk"), minis: raw(".cyc-minis"), accounts: b.accounts, by, members: b.members,
                                                       ...(b.mode ? {mode: b.mode} : {}), ...(b.assign ? {assign: b.assign} : {}), ...(b.hold ? {hold: b.hold} : {})};
  else delete CYC_DRAFT[id];
  const slot = root.querySelector(".cyc-save");
  if (slot) slot.innerHTML = cycleSaveHtml(id, cyc, b);
}
/* The status line under the card: green "Ready: ..." or red with every reason it will not trade, in words. */
function teamStatus(cyc, mem) {
  const accts = cyc && cyc.on ? (cyc.accounts || []).filter(a => a in (ST.accounts || {})) : [], bad = [];
  if (!ST.armed) bad.push("the Desk is OFF");
  if (!mem.length) bad.push("no strategy in this team yet (Manage groups)");
  else if (!accts.length) bad.push("no account ticked: its strategies run as practice");
  for (const a of accts) {
    const x = ST.accounts[a] || {};
    if (!x.connected) bad.push(`account ${acctShort(a)} is offline`);
    else if (x.day && x.day.locked) bad.push(`account ${acctShort(a)} is stopped for today`);
  }
  if (cyc && cycMode(cyc) === "split" && accts.length) mem.filter(m => !(cyc.assign || {})[m] && !((ST.book || {})[m] || []).length).forEach(m => bad.push(`${stratLabel(m)} has no account`));
  mem.filter(m => cyc && !(cyc.members || []).includes(m)).forEach(m => bad.push(`${stratLabel(m)} is not saved in the team yet`));
  mem.forEach(m => { const off = teamStray({mode: cycMode(cyc), assign: (cyc && cyc.assign) || {}, accounts: accts}, m);
    if (off.length) bad.push(`${stratLabel(m)} is still on ${off.map(acctShort).join(", ")}, outside this team`); });
  mem.filter(m => ST.strategies[m].cfg.enabled !== true).forEach(m => bad.push(`${stratLabel(m)} is OFF`));
  mem.filter(m => (ST.strategies[m].lab || {}).state === "stopped").forEach(m => bad.push(`${stratLabel(m)} is stopped for today`));
  mem.filter(m => (ST.strategies[m].lab || {}).state === "runner_down").forEach(m => bad.push(`${stratLabel(m)}'s runner is not running`));
  if (bad.length) return {ok: false, text: "Not ready: " + bad.join(" · ")};
  const risk = mem.some(m => cycRisk(cyc, m) > 0) ? (new Set(mem.map(m => cycRisk(cyc, m))).size === 1 ? cycUsd(cycRisk(cyc, mem[0])) + " a trade" : "each strategy's own $ a trade") : "each strategy's own size";
  return {ok: true, text: `Ready: trades on ${accts.map(acctShort).join(" and ")}, ${CYC_MODES[cycMode(cyc)].toLowerCase()}, ${risk}`};
}
function cycleHtml(g) {
  const cyc = ((ST && ST.groups) || {})[g.id] || null, mem = cycleMembers(g), dr = CYC_DRAFT[g.id] || null;
  if (!mem.length && !cyc) return `<div class="sec"><h2>Set up</h2><div class="mcap">Put this team's strategies in it first
    (Manage groups): then tick its accounts here and switch it on.</div></div>`;
  const on = teamOn(mem), some = !on && mem.some(m => ST.strategies[m].cfg.enabled === true);
  const chosen = new Set(dr ? dr.accounts : cyc ? cyc.accounts : []);
  const mode = (dr && dr.mode) || cycMode(cyc), assign = (dr && dr.assign) || (cyc && cyc.assign) || {}, hold = (dr && dr.hold) || {};
  const turn = cyc && cyc.on ? labSafe(() => cycleLastTurn(g), "") : "";
  const tagCls = {LIVE: "tag-live", PAPER: "tag-paper", DEMO: "tag"};
  const boxes = Object.keys(ST.accounts || {}).map(a => `<label class="feed-row" style="cursor:pointer">
      <span class="h"><input type="checkbox" class="cyc-acct" data-acct="${esc(a)}" ${chosen.has(a) ? "checked" : ""}
        onchange="cycleEdit(${jsArg(g.id)})"> ${esc(acctShort(a))} <span class="${tagCls[cycleEnvWord(a)]}">${cycleEnvWord(a)}</span>${ST.accounts[a].connected ? "" : ' <span class="neg">offline</span>'}</span>
      ${(p => p == null ? "" : `<span class="mono ${p > 0 ? "pos" : p < 0 ? "neg" : ""}" style="margin-left:auto" title="Today, 18:00 to 16:00 ET">${DAY_PNL_WORDS(p)}</span>`)(ST.accounts[a].day_pnl)}</label>`).join("");
  const pick = (m) => `<select class="cyc-assign" data-m="${esc(m)}" aria-label="${esc(stratLabel(m))} account" onfocus="FREEZE=true" onblur="FREEZE=false"
      onchange="cycleEdit(${jsArg(g.id)})"><option value="">no account</option>${[...chosen].map(a => `<option value="${esc(a)}"${assign[m] === a ? " selected" : ""}>${esc(acctShort(a))}</option>`).join("")}</select>`;
  const num = (cls, v, ph, extra) => `<input class="${cls}"${extra || ""} type="text" inputmode="decimal" autocomplete="off" value="${esc(String(v))}"
      placeholder="${ph}" style="width:72px;max-width:100%;text-align:right" onfocus="FREEZE=true" onblur="FREEZE=false" oninput="cycleEdit(${jsArg(g.id)})">`;
  const st = teamStatus(cyc, mem);
  return `<div class="sec"><h2>Set up</h2><div class="agroup feed static">
    <div class="feed-row"><span class="h"><b>Trading</b> ${on ? "ON" : some ? "ON for some" : "OFF"}</span>
      <button class="switch" role="switch" aria-label="Trading" aria-checked="${on}"
        title="${on ? "ON: every strategy of the team trades its accounts" : "OFF: no strategy of the team trades"}"
        onclick="toggleTeam(${jsArg(g.id)})"></button></div>
    ${turn ? `<div class="feed-row"><span class="h">${esc(turn)}</span></div>` : ""}
    ${boxes}
    <div class="feed-row"><span class="h">How</span><span class="t"><select class="cyc-mode" aria-label="How the team trades its accounts"
      onfocus="FREEZE=true" onblur="FREEZE=false" onchange="FREEZE=false;cycleEdit(${jsArg(g.id)});render()">${Object.entries(CYC_MODES).map(([k, w]) =>
      `<option value="${k}"${k === mode ? " selected" : ""}>${esc(w)}</option>`).join("")}</select></span></div>
    <div class="feed-row"><span class="h">Risk per trade ($)</span><span class="t">${num("cyc-risk", dr ? dr.risk : cyc ? cyc.risk_usd : 1000, "1000")}</span></div>
    <div class="feed-row"><span class="h">Most per trade (full contracts)</span><span class="t">${num("cyc-minis", dr ? dr.minis : cyc ? cyc.max_minis : 17, "17")}</span></div>
    ${mem.map(m => `<div class="feed-row"><span class="h">${esc(stratLabel(m))}</span><span class="t">${mode === "split" ? pick(m) + " " : ""}${num("cyc-risk-m",
      dr && dr.by && m in dr.by ? dr.by[m] : ((cyc && cyc.risk_by) || {})[m] || "", "same $", ` data-m="${esc(m)}" aria-label="${esc(stratLabel(m))} risk per trade"`)}
      <label title="Keeps a filled trade open past the day's flat time"><input type="checkbox" class="cyc-hold" data-m="${esc(m)}" ${(m in hold ? hold[m] : holdOf(m)) ? "checked" : ""}
        onchange="cycleEdit(${jsArg(g.id)})"> hold overnight</label></span></div>`).join("")}</div>
    <div class="cyc-save">${cycleSaveHtml(g.id, cyc, dr ? cycleDraftBody(dr) : {members: mem, risk_usd: cyc ? cyc.risk_usd : 1000, max_minis: cyc ? cyc.max_minis : 17,
      accounts: ((cyc && cyc.accounts) || []).filter(a => a in (ST.accounts || {}))})}</div>
    <div class="mcap ${st.ok ? "pos" : "warn"}">${esc(st.text)}.</div>
    <div class="mcap">${mode === "share" ? "Every trade goes to every ticked account."
      : mode === "split" ? "Each strategy trades only the account chosen beside it."
      : "One trade goes to one account, the next ticked one that is free."} A trade the opposite way to one open on
      another of these accounts is skipped. Risk 0 = each strategy's own size; a strategy's own $ (empty: the team's) sizes its
      trades instead. Its strategies trade only these accounts.</div></div>`;
}
function cycleCopies(members) {     // the strategies that, out of the team, would send each trade to several accounts at once
  return members.filter(m => ((ST.book || {})[m] || []).length > 1 && !((((ST.strategies || {})[m]) || {}).rotation || {}).on);
}
function cycleLive(members) {        // ", 3 of them LIVE" for the accounts these strategies are booked on
  const live = new Set(members.flatMap(m => ((ST.book || {})[m] || []).map(r => r.account)).filter(isRealAcct)).size;
  return live ? `, ${live} of them LIVE` : "";
}
/* The whole card as POST /api/setup reads a team. */
function cycleBody(id) {
  const g = groupOf(id), root = document.querySelector("#viewStrat");
  const val = (sel, d) => { const el = root && root.querySelector(sel); return el ? cycNum(el.value) : d; };
  const all = (sel) => [...(root ? root.querySelectorAll(sel) : [])];
  const byEls = all(".cyc-risk-m"), modeEl = root && root.querySelector(".cyc-mode"), asEls = all(".cyc-assign"), holdEls = all(".cyc-hold");
  const accounts = all(".cyc-acct").filter(b => b.checked).map(b => b.dataset.acct);
  return {team: id, name: g ? g.name : id, members: g ? cycleMembers(g) : [], accounts,
          risk_usd: val(".cyc-risk", 0), max_minis: Math.round(val(".cyc-minis", 17)),
          ...(byEls.length ? {risk_by: cycByBody(Object.fromEntries(byEls.map(el => [el.dataset.m, el.value])))} : {}),
          ...(modeEl ? {mode: modeEl.value} : {}),
          // an account unticked takes its strategy with it (the server refuses an account outside the team)
          ...(asEls.length ? {assign: Object.fromEntries(asEls.filter(el => accounts.includes(el.value)).map(el => [el.dataset.m, el.value]))} : {}),
          ...(holdEls.length ? {hold: Object.fromEntries(holdEls.map(el => [el.dataset.m, !!el.checked]))} : {})};
}
/* Save (on: as now) and the Trading switch (on: flipped) both send the whole card. It asks first when: the team goes ON;
   it goes OFF; it is ON on an account that is not paper (LIVE or DEMO) and the change sizes up or ticks one in; or a strategy
   loses its last account mid-day (its day ends; it trades again tomorrow). Lowering, unticking and paper-only changes save at once. */
async function saveCycle(id, on) {
  const g = groupOf(id), mem = g ? cycleMembers(g) : [], was = teamOn(mem);
  if (on === undefined) on = was;
  const body = {...cycleBody(id), on}, cyc = ((ST && ST.groups) || {})[id] || null, d = cycleDiff(cyc, body);
  const live = body.accounts.filter(isRealAcct), where = machineWords();
  const ends = body.members.filter(m => ((ST.book || {})[m] || []).length && !teamWant(body, m).length && ST.strategies[m].cfg.enabled);
  const endWords = ends.length ? ` ${ends.map(stratLabel).join(", ")} lose${ends.length === 1 ? "s" : ""} the last account: today is over for ${ends.length === 1 ? "it" : "them"}; trading again tomorrow.` : "";
  const how = {cycle: "take turns across", share: "trade every one of", split: "each trade their own one of"}[body.mode || cycMode(cyc)];
  const lv = live.length ? ` (${live.length} ${riskWord(live)})` : "";
  const sized = body.members.some(m => cycRisk(body, m) > 0) ? ` Each trade sized to ${body.members.map(m => `${stratLabel(m)} ${cycRisk(body, m) > 0 ? cycUsd(cycRisk(body, m)) : "its own size"}`).join(", ")} at risk, at most ${body.max_minis} full contracts.` : " Each at its own size.";
  let ask = null;
  if (on && !was) ask = ["Start trading?", `${plural(body.members.length, "strategy", "strategies")} ${how} ${plural(body.accounts.length, "account", "accounts")}${lv}${where ? " " + where : ""}.${sized}${endWords}`, "Start"];
  else if (!on && was) ask = ["Stop trading?", `${plural(body.members.length, "strategy", "strategies")} switched OFF: today is over for them (unfilled entries are cancelled). Accounts and sizes stay for the next ON.`, "Stop"];
  else if (ends.length || (on && live.length && (d.up || d.liveIn.length))) ask = ["Change the team?", `${d.parts.join(" · ")}.${d.liveIn.length ? ` ${riskWord(d.liveIn)} account${d.liveIn.length === 1 ? "" : "s"} ticked in: ${d.liveIn.map(acctShort).join(", ")}.` : ""}${endWords}${on && live.length ? ` It is ON across ${live.length} ${riskWord(live)} account${live.length === 1 ? "" : "s"}${where ? " " + where : ""}: the next trade uses this.` : ""}`, "Save"];
  if (ask && !await confirmDlg(ask[0], ask[1], ask[2], false)) { refresh(); return false; }
  let r, err = null;
  try { r = await post("/api/setup", body); } catch (e) { err = e || new Error("no answer"); }
  const why = DEMO ? null : answerWhy(r, err);
  if (why === "") delete CYC_DRAFT[id];   // saved: the card shows the desk's values again
  refresh();
  if (DEMO) return false;
  toast(why ? `NOT saved — ${why}.` : on !== was ? (on ? "Trading ON." : "Trading OFF.") : "Saved.", why ? 8000 : 4200);
  return !why;
}
const toggleTeam = (id) => { if (switchBounced("team:" + id)) return; const g = groupOf(id); return saveCycle(id, !teamOn(g ? cycleMembers(g) : [])); };
async function deleteGroup(id) {
  const g = groupOf(id);
  if (!g) return;
  const on = !!(((ST && ST.groups) || {})[id] || {}).on && cycleCopies(cycleMembers(g)).length > 0;
  if (!await confirmDlg(`Delete ${g.name}?`, on ? `Its account group stops too: ${cycleCopies(cycleMembers(g)).length} of its strategies then send each trade to EVERY account booked${cycleLive(cycleCopies(cycleMembers(g)))}. Its strategies stay on the Desk, in no group.`
                                             : "Its strategies stay on the Desk and go back under Strategies. Nothing is switched off.", "Delete", on)) return;
  if (await groupPost("delete", {id})) toast(`${g.name} is deleted. Its strategies are in no group.`);     // its cycle went first, server side
}

const hmin = (t) => { const m = /^(\d{1,2}):(\d\d)/.exec(String(t || "")); return m ? +m[1] * 60 + +m[2] : null; };
const etMin = (iso) => { const m = /T(\d\d):(\d\d)/.exec(String(iso || "")); return m ? +m[1] * 60 + +m[2] : null; };
const OPEN_MIN = 570;                                    // 09:30 ET, the cash open
const lenTxt = (m) => m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? " " + (m % 60) + " min" : ""}` : `${m} min`;
const usdS = (v) => v == null ? "—" : (v < 0 ? "−$" : v > 0 ? "+$" : "$") + fmt(Math.abs(v), 0);
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
/* The journal as the Today page and the sidebar read it: the Lab's named bookkeeping lines (DeskLab.HIDDEN_EVENTS: lab_event, lab_event_done, lab_added)
   are left out, so they never become the "Last event" time. Every other line is returned as it is. (The Activity list filters the same way.) */
/* A time of day as the app shows it: "HH:MM" or "HH:MM:SS" in, the owner's clock format out (hbclock.js; unchanged without it). */
const hbClock = (hms) => typeof HBClock !== "undefined" ? HBClock.text(hms) : hms;
const journalNews = (j) => journalShown(j).filter(r => !routineRow(r));      // "Last event": never a routine reconnect
const journalShown = (j) => (Array.isArray(j) ? j : []).filter(r => !(r && typeof r.event === "string" && r.event.indexOf("lab_") === 0 && typeof DeskLab !== "undefined" && DeskLab.hiddenEvent(r.event)));
const specOf = (c, name) => c.kind === "lab" ? labSafe(() => DeskLab.deskSpec(c, labRowOf(ST.strategies[name])), String(c.symbol || ""))
  : c.kind === "bars"
  ? `${c.symbol} · ${c.bar_minutes}m bars · ${c.rule}`
  : `${c.symbol} · ±${c.offset_pts} off · SL ${c.sl_pts} / TP ${c.tp_pts}`;

function todayPnl(s) {
  const d = String((ST && ST.et_now) || "").slice(0, 10);
  const rows = (s.accounts || []).filter(r => r && r.date === d && r.pnl != null);
  return rows.length ? rows.reduce((a, r) => a + r.pnl, 0) : null;
}
function stratState(name, s) {
  const c = s.cfg, st = s.day_status;
  if (c.kind === "lab") return labSafe(() => DeskLab.deskState(s, (ST.book && ST.book[name]) || []), "Check it");     // a promoted Lab strategy: the Desk's own words (lab.state / lab.why)
  if (!c.enabled) return "Off";
  if (st === "live") return "In position";
  if (st === "placed" || st === "placing") return "Orders working";
  if (st === "error") return "Needs a look";
  if (st === "done") return "Done today";
  const t = ST.timer && ST.timer.strategies && ST.timer.strategies[name];
  if (t && t.stage === "missed") return "Missed today";
  const now = etMin(ST.et_now), flat = hmin(c.flat_et) ?? 955;
  if (now != null && now >= flat) return "Idle";
  return now != null && now < OPEN_MIN ? "Ready" : "Watching";
}
const stratDotCls = (s, state, book) => s.cfg.kind === "lab" ? labSafe(() => DeskLab.deskDot(s, book), "warn")
  : !s.cfg.enabled ? "off" : s.cfg.shadow ? "shadow"
  : /Needs|Missed/.test(state) ? "warn" : (state === "In position" || state === "Orders working") ? "live" : "";

/* The day so far in money, LIVE apart from the rest: the sums of each account's closed P&L today (day.closed_net, which
   /api/status already sends). Closed trades only -- an open position's P&L is not in it, so it says so. The Mac's line
   names the machine (its accounts are not the server's). "" when no account says. */
function dayMoney() {
  const sums = {live: null, other: null}, kinds = new Set();
  for (const [id, a] of Object.entries((ST && ST.accounts) || {})) {
    const v = Number(a && a.day && a.day.closed_net);
    if (!a || !a.day || !Number.isFinite(v)) continue;
    const k = isDemoAcct(id) ? "other" : "live";
    sums[k] = (sums[k] || 0) + v;
    if (k === "other") kinds.add(a.env === "paper" ? "paper" : "demo");
  }
  const other = kinds.size === 2 ? "Demo + paper" : kinds.has("paper") ? "Paper" : "Demo";
  const parts = [sums.live != null ? `Live ${usdS(sums.live)}` : "", sums.other != null ? `${other} ${usdS(sums.other)}` : ""].filter(Boolean);
  if (!parts.length) return "";
  return `${deskMachine() === "mac" ? "This Mac: " : ""}${parts.join(" · ")} so far (strategies' closed trades).`;
}
/* the one sentence of the day -- two tones: what happens next, then what is armed */
function dayHeadline(names) {
  const strategies = Object.values(ST.strategies || {});
  // a Lab strategy with no account booked only runs in shadow: it is not "armed", and its times are never the day's
  const live = Object.entries(ST.strategies || {}).filter(([n, v]) => v.cfg.enabled && !v.cfg.shadow &&
    !(v.cfg.kind === "lab" && !((ST.book && ST.book[n]) || []).length)).map(([, v]) => v);
  const nonLab = strategies.filter(v => v.cfg.kind !== "lab");
  const n = live.length, now = etMin(ST.et_now);
  const dow = new Date(String(ST.et_now).slice(0, 10) + "T12:00:00Z").getUTCDay();
  const stale = DESK_STALE ? " Last known state." : "";
  if (!ST.armed) return ["Disarmed.", "Signals are journaled only. Nothing is sent to a broker." + stale];
  const onTxt = "Desk armed · " + plural(n, "strategy", "strategies") + " on." + stale;      // the desk is armed; strategies are on or off
  // Sunday from 18:00 ET the futures trade again: the Desk's day is the 9:30 session, so say when that is, not "closed"
  if (dow === 0 && now != null && now >= 18 * 60) return ["Futures are open. The Desk's day starts Monday at 9:30.", onTxt];
  if (dow === 0 || dow === 6) return ["Markets are closed.", onTxt];
  const flat = live.some(v => v.cfg.kind === "lab")      // a booked Lab strategy armed: the day ends at the latest armed flat time
    ? Math.max(...live.map(v => hmin(v.cfg.flat_et) ?? 955))
    : hmin((live[0] || nonLab[0] || strategies[0] || {cfg: {}}).cfg.flat_et) ?? 955;
  if (now == null) return ["Armed.", onTxt];
  if (now < OPEN_MIN) return [`Opens in ${lenTxt(OPEN_MIN - now)}.`, onTxt];
  if (now < flat) {
    const inPos = live.filter(v => v.day_status === "live").length;
    const working = live.filter(v => v.day_status === "placed" || v.day_status === "placing").length;
    const done = live.filter(v => v.day_status === "done").length;
    const l1 = inPos ? `${plural(inPos, "strategy", "strategies")} in a position.` : working ? "Orders are working." : "In session.";
    const money = dayMoney();
    return [l1, `${n} on · ${done} done today.` + (money ? " " + money : "") + stale];
  }
  const rows = strategies.map(todayPnl).filter(p => p != null);
  const tot = rows.reduce((a, p) => a + p, 0);
  return ["Session closed.", (rows.length ? `Today ${usdS(tot)}.` : "No trades today.") + stale];
}

/* The day bar's axis, in minutes ET: from the earliest window start to the latest window end (whole hours), with the
   9:30 open and the flat mark always on it; 9:00-16:00 when no window reads. A built-in's window is its fire time
   (9:30 when unsaid) to its flat time; a booked Lab strategy's is its record's session_window (an evening-before one,
   "-20:00", is left out: the bar is one day). */
function dayAxis(own, labs, flat) {
  const ws = own.map(v => [hmin(v.cfg.fire_et) ?? OPEN_MIN, hmin(v.cfg.flat_et) ?? 955]);
  for (const v of labs) {
    const w = labSafe(() => (labRowOf(v) || {}).session_window, null);
    if (Array.isArray(w) && w.length === 2 && !String(w[0]).startsWith("-")) ws.push([hmin(w[0]), hmin(w[1])]);
  }
  const ok = ws.filter(([a, b]) => a != null && b != null && b > a);
  if (!ok.length) return [540, 960];
  const lo = Math.floor(Math.min(OPEN_MIN, flat, ...ok.map(w => w[0])) / 60) * 60;
  const hi = Math.ceil(Math.max(OPEN_MIN, flat, ...ok.map(w => w[1])) / 60) * 60;
  return [lo, Math.max(hi, lo + 60)];
}
function dayTimeline(names) {
  const vis = new Set(names || Object.keys(ST.strategies || {}));      // only the strategies the page shows (an archived straddle is not)
  const strategies = Object.entries(ST.strategies || {}).filter(([n]) => vis.has(n)).map(([, v]) => v);
  const own = strategies.filter(v => v.cfg.kind !== "lab");      // a Lab strategy sets its own times: never the day bar's
  // when no Desk strategy is armed, a Lab strategy WITH an account booked is the bar's (its Flat mark only: it has no cancel time of its own)
  const armedOwn = own.find(v => v.cfg.enabled && !v.cfg.shadow);
  const labsOn = Object.entries(ST.strategies || {}).filter(([n, v]) => v.cfg.kind === "lab" && v.cfg.enabled && !v.cfg.shadow && ((ST.book && ST.book[n]) || []).length);
  const later = (a, b) => ((hmin(b.cfg.flat_et) ?? 955) > (hmin(a.cfg.flat_et) ?? 955) ? b : a);
  const labRef = armedOwn || !labsOn.length ? null : labsOn.map(([, v]) => v).reduce(later);
  const ref = (armedOwn || labRef || own[0] || strategies.find(v => v.cfg.enabled && !v.cfg.shadow) || strategies[0] || {cfg: {}}).cfg;
  // a booked Lab strategy armed: the bar's Flat mark is the latest armed flat time (with none, the reference's, as always)
  const flatEt = labsOn.length ? [armedOwn, ...own.filter(v => v.cfg.enabled && !v.cfg.shadow), ...labsOn.map(([, v]) => v)].filter(Boolean).reduce(later).cfg.flat_et : ref.flat_et;
  const cancel = hmin(ref.cancel_et) ?? 775, flat = hmin(flatEt) ?? 955;
  const [lo, hi] = dayAxis(own, labsOn.map(([, v]) => v), flat);
  const pct = (m) => Math.max(0, Math.min(100, (m - lo) / (hi - lo) * 100));
  const noCancel = !!labRef || !own.length;      // a Lab strategy has no cancel time of its own: only a built-in straddle draws one
  const oneMark = !noCancel && cancel === flat;      // the cancel and the flat time are one moment: one label, one tick
  const now = etMin(ST.et_now) ?? lo;
  const date = new Date(String(ST.et_now).slice(0, 10) + "T12:00:00Z")
    .toLocaleDateString("en-US", {weekday: "long", month: "long", day: "numeric", timeZone: "UTC"});
  const lab = (m, t, cls) => `<span class="${cls}" style="left:${pct(m).toFixed(2)}%">${esc(t)}</span>`;
  return `<div class="tl-head"><span><b>Today</b>${esc(date)}</span><span class="mono">${esc(hbClock(String(ST.et_now).slice(11, 16)))} ET</span></div>
    <div class="tl" role="img" aria-label="The trading day: open at 9:30, ${noCancel ? "" : `unfilled entries cancelled at ${esc(ref.cancel_et || "12:55")}, `}flat at ${esc(flatEt || "15:55")}">
      <div class="tl-track"><i class="tl-done" style="width:${pct(now).toFixed(2)}%"></i>${noCancel || oneMark ? "" : `<i class="tl-tick" style="left:${pct(cancel).toFixed(2)}%"></i>`}<i class="tl-tick" style="left:${pct(flat).toFixed(2)}%"></i><i class="tl-open" style="left:${pct(OPEN_MIN).toFixed(2)}%"></i><i class="tl-now" style="left:${pct(now).toFixed(2)}%"></i></div>
      <div class="tl-labels">${lab(OPEN_MIN, hbClock("9:30") + " Open", "tl-t strong at-start")}${noCancel || oneMark ? "" : lab(cancel, hbClock(ref.cancel_et || "12:55") + " Cancel unfilled", "tl-t")}${lab(flat, hbClock(flatEt || "15:55") + (oneMark ? " Cancel unfilled, flat" : " Flat"), "tl-t at-end")}</div>
    </div>`;
}

/* Today's journal for a few strategies (or a group), read from GET /api/journal at most once a minute -- not the /api/status
   tail, 60 lines for the whole desk, which would miss most of them. One slot a page part; a new query starts its slot afresh.
   Never in the demo or while the page is hidden. null until the first answer (the pieces that need it are then left out). */
const JREAD = {};
function journalToday(slot, q) {
  let c = JREAD[slot];
  if (!c || c.q !== q) c = JREAD[slot] = {q, at: 0, rows: null};
  // one read a minute, timed from its start; a read that hangs is cut off at 30 s, so it never holds a connection to the desk
  if (!DEMO && !document.hidden && Date.now() - c.at >= 60000) {
    const at = c.at = Date.now();
    fetch(q, {signal: AbortSignal.timeout(30000)}).then(r => r.ok ? r.json() : null).then(j => { if (j && JREAD[slot] === c && c.at === at) c.rows = Array.isArray(j.events) ? j.events : []; })
      .catch(() => {});
  }
  return c.rows;
}
const SIGNAL_EVENTS = new Set(["placed", "levels_placed", "dry_run", "shadow_signal", "signal_refused", "alert_refused", "lab_round", "lab_refused"]);
const jHm = (r) => hbClock(String((r && r.et) || "").slice(11, 16));
/* A strategy's last signal today ("10:41"), from the newest signal line that names it; "" when none is known. */
function lastSignal(name, rows) {
  const r = (rows || []).find(x => x && x.strategy === name && SIGNAL_EVENTS.has(x.event) && x.et);
  return r ? jHm(r) : "";
}
const todaySignals = () => journalToday("today", "/api/journal?" + new URLSearchParams({strategy: Object.keys((ST && ST.strategies) || {}).sort().join(","), limit: "2000"}));
/* A strategy's open trades now, from its own day rows (a Lab strategy: its rounds): [{side: "Long" | "Short", qty, account}]. */
function stratOpen(s) {
  const rows = s && s.cfg && s.cfg.kind === "lab" && s.lab && Array.isArray(s.lab.rounds) ? s.lab.rounds : (s && s.accounts) || [];
  return rows.filter(r => r && r.status === "live" && (r.side || r.entry_side)).map(r => ({
    side: /^(buy|long)/i.test(r.side || r.entry_side) ? "Long" : "Short", account: r.account,
    qty: Number(r.entry_qty) > 0 ? Number(r.entry_qty) - (Number(r.exit_qty) || 0) : Number(r.qty)})).filter(p => p.qty > 0);
}
function openText(s) {      // "Long 2" (both sides: "Long 1 · Short 1"); "" when flat
  const by = {};
  for (const p of stratOpen(s)) by[p.side] = (by[p.side] || 0) + p.qty;
  return ["Long", "Short"].filter(k => by[k]).map(k => `${k} ${by[k]}`).join(" · ");
}
/* LIVE when any booked account is live, PAPER when all are paper, else DEMO; nothing with no account. */
function bookEnvTag(name) {
  const accts = ((ST && ST.book && ST.book[name]) || []).map(r => r && r.account).filter(Boolean);
  if (!accts.length) return "";
  const w = accts.some(a => cycleEnvWord(a) === "LIVE") ? "LIVE" : accts.every(a => cycleEnvWord(a) === "PAPER") ? "PAPER" : "DEMO";
  const [cls, t] = {LIVE: ["tag-live", "Its orders go to a LIVE account: real money"], PAPER: ["tag-paper", "Paper accounts only: no money"],
                    DEMO: ["tag", "Demo accounts only: no money"]}[w];
  return `<span class="${cls}" title="${t}">${w}</span>`;
}
/* A group's page, live (WP1.19): today's lines of the group and its strategies (the Activity page's group read), each member
   on the Desk with its state, last signal, position and today, the group's P&L today, and the cycle's last turn. Anything
   with no data is left out, never shown as a guess. */
const groupJournal = (g) => journalToday("group", "/api/journal?" + new URLSearchParams({group: g.id, strategy: (g.members || []).join(","), limit: "2000"}));
function groupTodayHtml(g) {
  const live = (g.members || []).filter(m => ST.strategies && ST.strategies[m]);
  if (!live.length) return "";
  const rows = labSafe(() => groupJournal(g), null);
  const pnls = live.map(m => todayPnl(ST.strategies[m])).filter(p => p != null);
  const tot = pnls.length ? pnls.reduce((a, p) => a + p, 0) : null;
  const line = (m) => {
    const s = ST.strategies[m], p = todayPnl(s), sig = lastSignal(m, rows);
    const pos = stratOpen(s).map(x => `${x.side} ${x.qty} on ${acctShort(x.account)}`).join(", ");
    const bits = [sig ? "Last signal " + sig : "", pos].filter(Boolean).join(" · ");
    return `<div class="feed-row" role="button" tabindex="0" onclick="openGroupMember(${jsArg(m)})"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openGroupMember(${jsArg(m)})}">
      <span class="h">${esc(stratLabel(m))} · <span class="dim">${esc(stratState(m, s))}</span></span>
      <span class="t dim">${esc(bits)}</span><span class="t net${p < 0 ? " neg" : p > 0 ? " pos" : ""}">${p == null ? "" : esc(usdS(p))}</span></div>`;
  };
  return `<div class="sec"><h2>Today</h2>${tot == null ? "" : `<div class="sd-state">The group today: <b>${esc(usdS(tot))}</b></div>`}
    <div class="agroup feed static">${live.map(line).join("")}</div></div>`;
}
/* The cycle's last turn today: the newest trade one of its strategies opened on one of its accounts, or the newest turn it
   skipped. "" until the journal answers, or with no turn today. */
function cycleLastTurn(g) {
  const cyc = ((ST && ST.groups) || {})[g.id], rows = groupJournal(g);
  if (!cyc || !rows) return "";
  const r = rows.find(x => x && x.et && ((x.event === "lab_round" && (cyc.members || []).includes(x.strategy) && (cyc.accounts || []).includes(x.account))
    || ((x.event === "group_skipped" || x.event === "group_hedge_skipped") && x.group === g.id)));
  if (!r) return "";
  const t = `Last turn ${jHm(r)}: ${stratLabel(r.strategy)}`;
  return r.event === "lab_round" ? `${t} on ${acctShort(r.account)}`
    : `${t} was skipped. ${r.event === "group_hedge_skipped" ? "It was the opposite way to a trade open on another of these accounts." : String(r.reason || "")}`.trim();
}
function todayRow(name, s) {
  const c = s.cfg, state = stratState(name, s), p = todayPnl(s);
  const sig = labSafe(() => lastSignal(name, todaySignals()), "");
  const extra = [openText(s), sig ? "Last signal " + sig : ""].filter(Boolean);      // the position and the last signal: each only when known
  const sh = c.kind === "lab" ? labSafe(() => labShadowNet(name, s), null) : null;      // a Lab strategy with no account: what the day would have made
  const sw = `<button class="switch" role="switch" aria-label="${esc(stratLabel(name))} on or off" aria-checked="${c.enabled}"
    title="${c.kind === "lab" ? esc(labSafe(() => DeskLab.deskSwitchTitle(s, (ST.book && ST.book[name]) || []), "")) : c.enabled ? "ON — this strategy runs and executes" : "OFF — ignores all signals"}"
    onclick="event.stopPropagation();toggleStrat('${name}', ${!c.enabled})"></button>`;
  const go = `setView('strat','${name}')`;
  return `<div class="srow" role="button" tabindex="0" onclick="${go}"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();${go}}">
    <div><div class="n">${esc(stratLabel(name))}${c.shadow ? '<span class="tag" title="Signals are journaled only — nothing is placed, even when armed">Shadow</span>' : (c.kind === "lab" ? labSafe(() => labShadowTag(name, s), "") : "") + labSafe(() => bookEnvTag(name), "")}</div>
      <div class="sp mono">${esc([specOf(c, name), ...extra].join(" · "))}</div></div>
    <div class="rs">${esc(state)}</div>
    <div class="rp mono${sh ? " dim" : p < 0 ? " neg" : p > 0 ? " pos" : ""}"${sh ? ` title="${esc(sh.title)}"` : ""}>${usdS(sh ? sh.net : p)}</div>${sw}</div>`;
}

let ISSUE_LVL = "warn";      // the sidebar's Activity row reads it
/* One line under Readiness: how many accounts are connected. The things that need a look are the bulb's and the Readiness
   row's (openChecks); the last event is the sidebar's Activity row -- neither is repeated here. */
function todayFoot() {
  const accts = Object.values(ST.accounts || {}), up = accts.filter(a => a.connected).length;
  return `<button class="foot-b" onclick="openAccts()">${up} of ${accts.length} accounts connected <u>›</u></button>`;
}

