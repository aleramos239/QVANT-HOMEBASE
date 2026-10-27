/* ---- research details popup ---- */
function equitySvg(points, w = 560, h = 190) {
  const vals = points.map(p => p[1]);
  const min = Math.min(0, ...vals), max = Math.max(0, ...vals);
  const X = i => 4 + (i / (points.length - 1)) * (w - 8);
  const Y = v => h - 10 - ((v - min) / ((max - min) || 1)) * (h - 20);
  const path = points.map((p, i) =>
    (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(p[1]).toFixed(1)).join("");
  const fin = vals[vals.length - 1];
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block">
    <line x1="0" x2="${w}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--border)"/>
    <path d="${path}" fill="none" stroke="var(--foreground)" stroke-width="1.4"/>
    <text x="${w - 4}" y="${Math.max(12, Y(fin) - 6)}" text-anchor="end"
      fill="var(--${fin >= 0 ? "pos" : "neg"})"
      style="font:600 12px var(--font-mono)">${usd(fin)}</text></svg>`;
}
let RESCHART = null;
function cssColor(v) {
  // resolve var() -> oklch -> plain rgb (the chart's parser needs rgb)
  const el = document.createElement("span");
  el.style.color = `var(${v})`;
  document.body.appendChild(el);
  const c = getComputedStyle(el).color;
  el.remove();
  const cv = document.createElement("canvas");
  cv.width = cv.height = 1;
  const ctx = cv.getContext("2d");
  ctx.fillStyle = c;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}
function lwTime(t) {
  return typeof t === "string" ? t : !t ? "" :
    `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;
}
function renderEquityChart(points) {
  const box = $("#resChart");
  if (RESCHART) { try { RESCHART.remove(); } catch (_) {} RESCHART = null; }
  if (!window.LightweightCharts) { box.innerHTML = equitySvg(points); return; }
  box.innerHTML = `<div id="resLw" style="height:280px"></div>
    <div id="resTip" style="font-family:var(--font-mono);font-size:12px;height:18px;
      margin-top:4px;color:var(--foreground)"></div>`;
  const fg = cssColor("--foreground"), mut = cssColor("--muted-foreground"),
    grid = cssColor("--border");
  const fill = fg.replace("rgb", "rgba").replace(")", ", 0.07)");
  const chart = LightweightCharts.createChart(document.getElementById("resLw"), {
    layout: {background: {type: "solid", color: "transparent"}, textColor: mut,
             fontFamily: getComputedStyle(document.body).fontFamily, fontSize: 11,
             attributionLogo: false},
    grid: {vertLines: {color: grid}, horzLines: {color: grid}},
    rightPriceScale: {visible: false},
    leftPriceScale: {visible: true, borderColor: grid},
    timeScale: {borderColor: grid},
    autoSize: true,
  });
  const series = chart.addAreaSeries({
    priceScaleId: "left",
    lineColor: fg, lineWidth: 2,
    topColor: fill, bottomColor: "rgba(0,0,0,0)",
    priceFormat: {type: "custom", minMove: 1,
                  formatter: (v) => (v < 0 ? "-$" : "$") +
                    Math.abs(Math.round(v)).toLocaleString("en-US")},
  });
  const seen = new Set();
  series.setData(points.filter(([d]) =>
    seen.has(d) ? false : seen.add(d)).map(([d, v]) => ({time: d, value: v})));
  chart.timeScale().fitContent();
  const tip = document.getElementById("resTip");
  chart.subscribeCrosshairMove((p) => {
    const d = p && p.seriesData && p.seriesData.get(series);
    tip.textContent = d ? `${lwTime(p.time)}   ·   ${usd(d.value)}` : "";
  });
  RESCHART = chart;
}
async function openRes(name) {
  const s = (ST.strategies || {})[name] || {};
  const r = s.research || {};
  $("#resName").textContent = stratLabel(name);
  $("#resSource").textContent = r.source || "";
  $("#resChart").innerHTML = `<div class="mcap">loading curve…</div>`;
  $("#resChartCap").textContent = "";
  showOverlay("resOverlay");
  { const m = document.querySelector("#resOverlay .modal"); if (m) m.scrollTop = 0; }   // each profile opens at its curve
  try {
    const d = await (await fetch("/api/research-equity?strategy=" +
                                 encodeURIComponent(name))).json();
    if (d.points && d.points.length > 1) {
      renderEquityChart(d.points);
      $("#resChartCap").textContent = (d.label || "") +
        (d.note ? " — " + d.note : "") +
        "  ·  chart: TradingView Lightweight Charts™";
    } else {
      $("#resChart").innerHTML =
        `<div class="mcap">no equity curve on file — attach the exam export to add one</div>`;
    }
    if (d.table && d.table.length) {
      let last = "";
      $("#resTable").innerHTML = `<div class="rtable">` +
        d.table.map(([sec, k, v]) =>
          (sec !== last ? ((last = sec),
            `<div class="slabel2">${sec.toUpperCase()}</div>`) : "") +
          `<div class="rrow"><span class="k">${k}</span><span class="v">${v}</span></div>`
        ).join("") + `</div>` +
        (d.table_note ? `<div class="mcap" style="margin-top:8px">${d.table_note}</div>` : "");
    } else $("#resTable").innerHTML = "";
    let mcHtml = "";
    if (d.mc_table && d.mc_table.length) {
      let last = "";
      mcHtml += `<div class="slabel2" style="font-size:11.5px">MONTE CARLO — 10,000 RESAMPLES OF THE TRADE LIST</div>
        <div class="r3 r3h"><span class="k"></span><span>median run</span><span>5–95% of runs</span></div>` +
        d.mc_table.map(([sec, k, med, band]) =>
          (sec !== last ? ((last = sec),
            `<div class="slabel2">${sec.toUpperCase()}</div>`) : "") +
          `<div class="r3"><span class="k">${k}</span><span class="v">${med}</span><span class="v b">${band || "—"}</span></div>`
        ).join("") +
        (d.mc_note ? `<div class="mcap" style="margin-top:8px">${d.mc_note}</div>` : "");
    }
    if (d.prop_table && d.prop_table.length) {
      mcHtml += `<div class="slabel2" style="font-size:11.5px;margin-top:16px">${d.prop_title || "PROP SIM — ACCOUNT LIFECYCLE ON THIS LEDGER"}</div>
        <div class="rtable" style="columns:2">` +
        d.prop_table.map(([k, v]) =>
          `<div class="rrow"><span class="k">${k}</span><span class="v">${v}</span></div>`
        ).join("") + `</div>` +
        (d.prop_note ? `<div class="mcap" style="margin-top:8px">${d.prop_note}</div>` : "");
    }
    $("#resMc").innerHTML = mcHtml
      ? `<div style="border-top:2px solid var(--border);margin-top:16px;padding-top:12px">${mcHtml}</div>`
      : "";
  } catch (_) {
    $("#resChart").innerHTML = `<div class="mcap">curve unavailable</div>`;
  }
}
function closeRes() { hideOverlay("resOverlay"); }
$("#resOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeRes();
});

function dismissReady() {
  try { localStorage.setItem("hb_ready_dismiss", window.READY_SIG || ""); } catch (_) {}
  $("#readyStrip").style.display = "none";
}

/* ---- reconnect ---- */
async function reconnectAcct(id) {
  toast("Reconnecting" + (id ? " " + id : " all accounts") + "…", 8000);
  const r = await post("/api/accounts/reconnect", id ? {account: id} : {});
  const res = (r && r.results) || {};
  const bad = Object.entries(res).filter(([, v]) => !v.ok);
  if (r && r.ok) {
    const modes = [...new Set(Object.values(res).map(v => v.mode))].join(", ");
    toast("Reconnected (" + modes + ").");
  } else if (bad.length) {
    toast("Reconnect failed — " + bad.map(([k, v]) => k + ": " + v.error).join(" · "), 9000);
  }
  refresh();
}

/* ---- strategy on/off + flatten ----
   The on/off switch follows the desk's one confirm policy (S6, the chart-trading switch's
   pattern): turning a strategy ON asks -- it trades from its next signal; turning it OFF never
   asks -- it only makes things safer, and it never touches an open position (the toast says so;
   Flatten does that). A SHADOW strategy never places an order, so switching it on asks nothing
   either. Same POST /api/strategy either way. */
async function toggleStrat(name, enabled) {
  if (switchBounced("strategy:" + name)) return;    // a double-click is one flip
  const c = ((((ST && ST.strategies) || {})[name]) || {}).cfg || {};
  const lab = c.kind === "lab";       // a promoted Lab strategy: with no account booked it only runs in shadow, which asks nothing
  if (needsConfirm("strategy", enabled, {shadow: !!c.shadow || (lab && !((ST.book && ST.book[name]) || []).length)}) && !await confirmDlg(
      "Turn ON " + stratLabel(name) + "?",
      "It will run and execute on its assigned accounts from the next signal.",
      "Turn on", false)) { refresh(); return; }
  const N = stratLabel(name);
  let r, err = null;
  try { r = await post("/api/strategy", {strategy: name, enabled}); } catch (e) { err = e || new Error("no answer"); }
  if (lab) await refresh(); else refresh();     // a Lab strategy's toast reads the state the Desk answers with
  if (DEMO) return;                        // preview mode: post() already said nothing is sent
  const why = answerWhy(r, err);
  if (!why) toast(lab ? (enabled ? DeskLab.switchOnToast(N, ST.strategies[name], (ST.book && ST.book[name]) || []) : DeskLab.switchOffToast(N, (ST.book && ST.book[name]) || []))
    : N + (enabled ? " is ON." : " is OFF — it ignores signals; open positions are untouched."));
  else if (enabled) toast(lab ? DeskLab.refusalText(r, err) : `${N} NOT switched on — ${why}.`, 8000);          // the safe side
  else alertBar(`${N} NOT switched off — ${why}. It may still trade: switch it off again, or Kill.`);
}
/* A straddle's target as 1:rr of its stop (nq930). The desk refuses 09:20-09:35 ET and while the strategy has
   orders or a position today. Returns "" when it landed, else the reason in words (the Desk skin shows it
   under the field). */
async function setStratRr(name, rr, slPts) {      // rr null + slPts: change the stop only, the RR stays
  const N = stratLabel(name);
  let r, err = null;
  const body = {strategy: name};
  if (rr != null) body.rr = rr;
  if (slPts != null) body.sl_pts = slPts;
  try { r = await post("/api/strategy-rr", body); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  if (DEMO) return "";
  if (err) return answerWhy(null, err);
  if (r && r.ok === true) { toast(`${N}: stop ${r.sl_pts} pts, target 1:${r.rr} (${r.tp_pts} pts).`); return ""; }
  return killText(r && (r.detail || r.error)) || "the desk's answer was unreadable";
}
/* One adjustable setting of a Lab strategy (the Setup panel's controls, desklabset.js): "" when it was saved, else the sentence
   saying why not. It takes effect from the strategy's next session. */
async function setLabSetting(name, key, value) {
  const N = stratLabel(name);
  let r, err = null;
  try { r = await post("/api/lab-settings", {strategy: name, settings: {[key]: value}}); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  if (DEMO) return "";
  if (err) return answerWhy(null, err);
  if (r && r.ok === true) { toast(r.changed === false ? `${N}: nothing changed.` : `${N} setting saved. It applies from its next session.`); return ""; }
  return killText(r && (r.detail || r.error)) || "the desk's answer was unreadable";
}
/* Flatten & turn off believes only what the desk reports (second review): it answers ok:true
   whatever happened to the flatten itself, with each account's steps in `results` -- read them
   (stepFailures). A failed flatten, a refusal or a dropped / unreadable answer is the red alert:
   a position may still be open. */
async function flattenStrat(name) {
  const lab = (((ST && ST.strategies) || {})[name] || {cfg: {}}).cfg.kind === "lab", ask = lab ? DeskLab.flattenAsk(stratLabel(name)) : null;     // a Lab strategy flattens only its own trade
  if (!await (lab ? confirmDlg(ask.title, ask.body, ask.action, true) : confirmDlg("Flatten " + stratLabel(name) + "?",
      "Cancels its resting entries, market-flattens its symbol on every account it acted on today, and switches the strategy OFF.",
      "Flatten & turn off", true))) return;
  const N = stratLabel(name);
  let r, err = null;
  try { r = await post("/api/strategy-flatten", {strategy: name}); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  if (DEMO) return;
  const why = answerWhy(r, err);
  if (why) return alertBar(`${N} flatten NOT confirmed — ${why}. Check its positions at the broker now.`);
  const res = r.results && typeof r.results === "object" ? (lab ? DeskLab.flattenSteps(r.results) : r.results) : null;
  if (!res) return alertBar(`${N} flatten NOT confirmed — the desk sent no account results. Check its positions at the broker now.`);
  const chk = lab && Array.isArray(r.check) ? r.check.map(String) : [];      // a Lab flatten: the Desk names the accounts a person must look at
  const bad = Object.entries(res).map(([a, steps]) => {
    const f = stepFailures(steps);
    if (chk.includes(a) && !f.flatten.length && !f.cancel.length && !f.check.length) f.check.push("its close is not confirmed");
    return failText(f, " on " + acctShort(a));
  }).filter(Boolean);
  if (bad.length) return alertBar(`${N} flatten — ${bad.join(" · ")}. ` + (lab && r.enabled !== false ? DeskLab.NOT_OFF + " Flatten what is left at the broker now."
    : "It is switched OFF; flatten what is left at the broker now."));
  if (lab && typeof r.detail === "string" && r.detail) return toast(r.detail, 8000);     // flattened, but the switch did not turn off: the Desk's sentence
  if (lab && DeskLab.closeOut(r.results)) return toast(DeskLab.CLOSE_OUT, 8000);        // its own close order was already out: nothing more was sent
  toast(`${N} flattened and switched off.`);
}

/* ---- the account's day take (the group's) ----
   Closed net P&L of the day, in dollars: once a trade of ANY strategy booked here closes with the day at or above it, no new
   entry is taken on the account for the rest of the day (open trades run to their stop / target). 0 turns it off. */
function dayTakeBox(id, a) {
  const d = (a && a.day) || {}, v = Number(d.day_lock) || 0;
  const state = d.locked ? ` <span class="neg" title="No new entry on this account for the rest of the day">stopped for the day (${usd(d.closed_net)})</span>`
    : (v ? ` <span class="mcap" title="The day's closed P&amp;L so far">${usd(d.closed_net || 0)} of ${usd(v)}</span>` : "");
  return `<span class="mcap" title="Closed profit that ends the day for this account: no new entry after it, for any strategy. 0 = off">Day take $</span>
    <input type="number" min="0" max="100000" step="50" value="${v}" style="width:72px" aria-label="Day take, dollars"
      onkeydown="if(event.key==='Enter')setDayTake(${jsArg(id)}, this.value)"><button class="btn btn-outline btn-sm"
      onclick="setDayTake(${jsArg(id)}, this.previousElementSibling.value)">Set</button>${state}`;
}
async function setDayTake(id, raw) {
  const v = Number(raw);
  if (raw === "" || !Number.isFinite(v) || v < 0 || v > 100000) return toast("The day take is a dollar amount from 0 (off) to 100000.", 5000);
  const r = await post("/api/account-day-lock", {account: id, day_lock: v});
  if (r && r.ok) toast(r.locked ? "Day take set. This account is stopped for the day." : (v ? "Day take set: " + usd(v) + "." : "Day take off."), 4000);
  else toast((r && r.detail) || "Could not set the day take.", 5000);
  await refresh();
  if ($("#acctOverlay").classList.contains("open")) openAccts(id);   // the popup shows the new take at once
}

/* ---- accounts popup ---- */
function openAccts(focus) {
  const accts = (ST && ST.accounts) || {};
  const ids = Object.keys(accts);
  $("#acctCount").textContent = ids.length ? ids.length + " connected login" +
    (ids.length > 1 ? "s" : "") : "";
  const runningOn = (id) => Object.entries((ST && ST.book) || {})
    .filter(([, rows]) => (rows || []).some(a => a.account === id))
    .map(([n, rows]) => n + " ×" + rows.find(a => a.account === id).qty)
    .join(" · ");
  $("#acctList2").innerHTML = ids.length
    ? ids.map(id => {
        const running = runningOn(id);
        // replacer FUNCTIONS, never strings: a replacement string reads $&, $`, $$ … specially, and an
        // account id is the broker's text -- "$`" in one used to splice the row into itself (second review)
        return acctRow(id, {}).replace('<div class="acct">', () => `<div class="acct${id === focus ? " acct-focus" : ""}">`)
          .replace('<span class="spacer"></span>',
          () => `<span class="strats">${esc(running || "no strategy assigned")}</span><span class="spacer"></span>`)
          .replace("</div>", () => `${dayTakeBox(id, accts[id])}<button class="btn btn-outline btn-sm" onclick="flattenAcct(${jsArg(id)})"${accts[id].connected ? "" : " disabled"}
            title="Cancel every working order and close every position on this account">Flatten</button>
            <button class="btn btn-outline btn-sm" onclick="reconnectAcct(${jsArg(id)})"
            title="Rebuild this account's broker connection">Reconnect</button>
            <button class="x" style="border:none;background:none;color:var(--muted-foreground);cursor:pointer;font-size:14px"
            onclick="removeAcct(${jsArg(id)})" title="Remove this account">&times;</button></div>`);
      }).join("")
    : `<div class="mcap" style="padding:14px 0">no accounts yet — add one to start</div>`;
  renderPaper();
  loadPaper();
  showOverlay("acctOverlay");
  const at = $("#acctList2 .acct-focus");
  if (at && at.scrollIntoView) at.scrollIntoView({block: "nearest"});
}
function closeAccts() { hideOverlay("acctOverlay"); }
async function removeAcct(id) {
  closeAccts();
  if (!await confirmDlg("Remove " + id + "?",
      "Unassigns it from every strategy and drops it from the pool. Refused if it holds an open position.",
      "Remove", true)) return;
  const r = await post("/api/accounts/remove", {account: id});
  toast(r.ok ? id + " removed." : "Refused — " + (r.detail || "unknown"), 5000);
  refresh();
}
$("#acctOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeAccts();
});

/* ---- algo manager popup: choose which algos show on the home page ---- */
function renderAlgoMgr() {
  if (!ST || !window.AlgoVisibility) return;
  const shelved = archivedBuiltins();       // an archived built-in lives in Archive, not here (unless it can trade or holds anything)
  const rows = window.AlgoVisibility.computeVisibility(ST.strategies, ST.book, HIDDEN_ALGOS, ST.accounts)
    .filter(a => a.locked || !shelved.includes(a.name));
  $("#algoCount").textContent = rows.length + " algo" + (rows.length === 1 ? "" : "s");
  $("#algoList").innerHTML = rows.length
    ? rows.map(a => {
        const statusPill = dayPill(a.day_status);
        const onPill = a.enabled
          ? `<span class="pill on" title="Switched on">ON</span>` : `<span class="pill idle" title="Switched off">OFF</span>`;
        const note = a.locked
          ? `<span class="mcap" style="margin:2px 0 0">${a.lockReason}</span>` : "";
        return `<div class="acct" style="padding:9px 0;align-items:flex-start">
          <div style="display:flex;flex-direction:column;gap:2px;min-width:0">
            <div style="display:flex;align-items:center;gap:8px">
              <span class="nm" style="font-size:13px">${esc(stratLabel(a.name))}</span>
              <span class="hint" style="font-size:11.5px">${a.symbol}</span>
              ${onPill}${statusPill}
            </div>
            ${note}
          </div>
          <span class="spacer"></span>
          <label class="hint" style="display:flex;align-items:center;gap:6px;cursor:${a.locked ? "default" : "pointer"};font-size:12px"
            title="${a.locked ? a.lockReason : "Show on home page"}">
            Show on home page
            <button class="switch" role="switch" aria-label="Show ${esc(stratLabel(a.name))} on the home page" aria-checked="${a.visible}" ${a.locked ? "disabled" : ""}
              onclick="toggleAlgoHidden('${a.name}', ${a.visible})"></button>
          </label>
        </div>`;
      }).join("")
    : `<div class="mcap" style="padding:14px 0">no algos configured yet</div>`;
}
function openAlgoMgr() { renderAlgoMgr(); showOverlay("algoOverlay"); }
function closeAlgoMgr() { hideOverlay("algoOverlay"); }

/* ---- group manager popup: add, rename and delete groups, and say which group each strategy is in (no type picker since
   2026-10-18: a new group is "together"). Every change is one write to the chart service (groupPost) and a repaint from its
   answer; nothing here touches a strategy or an account. ---- */
function renderGroupMgr(force) {
  const ov = $("#groupOverlay");
  if (!ov || !ST || !ov.classList.contains("open")) return;
  const a = document.activeElement;
  if (!force && a && ov.contains(a) && a.matches("#groupList input, #groupList select")) return;      // never wipe a field being used
  const groups = DESKGROUPS.groups;
  $("#groupCount").textContent = groups.length + " group" + (groups.length === 1 ? "" : "s");
  const known = [];                    // every strategy a group may take: [id, label]
  const shelved = archivedBuiltins();       // an archived built-in is not offered (one already in a group still shows)
  for (const n of Object.keys(ST.strategies || {})) if (!shelved.includes(n)) known.push([n, stratLabel(n)]);
  for (const w of labSafe(() => DESKLAB.strategies.filter(x => !labOnDesk(x)), [])) known.push(["lab_" + w.name, labSafe(() => DeskLab.label(w), w.name)]);
  const have = new Set(known.map(k => k[0]));
  for (const g of groups) for (const id of g.members) if (!have.has(id)) { have.add(id); known.push([id, id + " (not on the Desk any more)"]); }
  const glist = groups.map(g => `<div class="acct" style="padding:8px 0;gap:8px;align-items:center">
      <input class="grp-sel" value="${esc(g.name)}" maxlength="40" spellcheck="false" aria-label="Name of ${esc(g.name)}" style="flex:1;min-width:0;max-width:none"
        onchange="renameGroup(${jsArg(g.id)}, this.value)">
      <span class="hint" style="font-size:11.5px;white-space:nowrap">${g.members.length} in it</span>
      <button class="btn btn-outline btn-sm" onclick="deleteGroup(${jsArg(g.id)})">Delete</button></div>`).join("");
  const slist = known.map(([id, label]) => {
    const cur = groups.find(g => g.members.includes(id));
    return `<div class="acct" style="padding:7px 0;gap:8px;align-items:center">
      <span class="nm" style="font-size:13px;flex:1;min-width:0">${esc(label)}</span>
      <select class="grp-sel" aria-label="Group of ${esc(label)}" onchange="moveToGroup(${jsArg(id)}, this.value)">
        <option value="">${esc(DeskLab.NO_GROUP)}</option>${groups.map(g => `<option value="${esc(g.id)}"${cur && cur.id === g.id ? " selected" : ""}>${esc(g.name)}</option>`).join("")}
      </select></div>`;
  }).join("");
  // an account cycle whose Desk group is gone (a delete from before the chart service kept them in step): shown, so it can be removed
  const orphans = DESKGROUPS.ok === true ? Object.entries((ST && ST.groups) || {}).filter(([id]) => !groupOf(id)) : [];
  const olist = orphans.map(([id, c]) => `<div class="acct" style="padding:8px 0;gap:8px;align-items:center">
      <span class="nm" style="font-size:13px;flex:1;min-width:0">${esc(c.name)} · account cycle ${c.on ? "<b>ON</b>" : "off"}, no group</span>
      <button class="btn btn-outline btn-sm" onclick="removeOrphanCycle(${jsArg(id)})">Remove</button></div>`).join("");
  $("#groupList").innerHTML = (olist ? `<div class="mcap warn" style="margin:8px 0 2px">Account cycles with no group</div>${olist}` : "")
    + (groups.length ? `<div class="mcap" style="margin:8px 0 2px">Groups</div>${glist}` : "")
    + (known.length ? `<div class="mcap" style="margin:12px 0 2px">Strategies</div>${slist}` : `<div class="mcap" style="padding:14px 0">No strategies on the Desk yet.</div>`);
}
function openGroupMgr() { renderGroupMgr(true); showOverlay("groupOverlay"); renderGroupMgr(true); }
async function removeOrphanCycle(id) {
  const c = ((ST && ST.groups) || {})[id];
  if (!c || !await confirmDlg(`Remove the ${c.name} account cycle?`, c.on ? `It is ON with no group. Its strategies then trade their own booked accounts again${cycleLive(c.members || [])}.`
      : "It has no group and is off.", "Remove", !!c.on)) return;
  let r, err = null;
  try { r = await post("/api/groups/delete", {id}); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  const why = DEMO ? "" : answerWhy(r, err);
  toast(why ? `Account cycle NOT removed — ${why}.` : `${c.name} account cycle removed.`, why ? 8000 : 4200);
}
function closeGroupMgr() { hideOverlay("groupOverlay"); }
async function addGroup() {
  const name = $("#groupNewName").value.trim();
  if (!name) { toast("Give the group a name."); $("#groupNewName").focus(); return; }
  if (await groupPost("create", {name})) {
    $("#groupNewName").value = "";
    toast(`${name} is added. Pick its strategies below.`);
  }
}
const renameGroup = (id, name) => groupPost("rename", {id, name: String(name).trim()});
async function moveToGroup(strategy, group) {
  const old = DESKGROUPS.groups.find(g => g.members.includes(strategy)), oc = old ? ((ST && ST.groups) || {})[old.id] : null;
  if (oc && oc.on && oc.members.includes(strategy) && cycleCopies([strategy]).length && !await confirmDlg(
      `Take ${stratLabel(strategy)} out of the account cycle?`,
      `Its next trade goes to EVERY account it is booked on${cycleLive([strategy])}, not one at a time.`, "Take it out", true)) {
    renderGroupMgr(true);
    return;
  }
  const nc = group ? ((ST && ST.groups) || {})[group] : null;
  if (nc && nc.on && !(nc.members || []).includes(strategy) && !await confirmDlg(
      `Add ${stratLabel(strategy)} to the ${nc.name} account cycle?`,
      `Its trades then go to ONE account at a time of ${nc.accounts.length}${nc.risk_usd > 0 ? `, each sized to $${Number(nc.risk_usd).toLocaleString("en-US")} at risk` : ""}.`,
      "Add it", false)) {
    renderGroupMgr(true);
    return;
  }
  await groupPost("move", {strategy, group: group || null});      // the chart service makes the cycle follow, server side
}
$("#groupOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeGroupMgr();
});
/* "Show on home page" never asks, either way, under the desk's one confirm policy (S6):
   hiding a card is display only and changes nothing that trades -- switchNeedsConfirm(
   "visibility", ...) is false both ways -- and a card that could trade is locked visible. */
function toggleAlgoHidden(name, currentlyVisible) {
  if (!window.AlgoVisibility) return;
  // currentlyVisible -> user wants to hide it; already-hidden -> unhide.
  // withHidden() itself also refuses to hide a locked algo, so a stale
  // click on a supposedly-disabled control can't sneak one past the rule.
  const rows = window.AlgoVisibility.computeVisibility(ST.strategies, ST.book, HIDDEN_ALGOS, ST.accounts);
  const row = rows.find(r => r.name === name);
  const locked = !!(row && row.locked);
  HIDDEN_ALGOS = window.AlgoVisibility.withHidden(HIDDEN_ALGOS, name, currentlyVisible, locked);
  window.AlgoVisibility.saveHidden(HIDDEN_ALGOS);
  renderAlgoMgr();
  render();
}
$("#algoOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeAlgoMgr();
});

/* ---- strategy LIVE popup: calendar + metrics + trade log ---- */
let LIVE = {name: "", d: new Date(), data: null};
async function openLive(name) {
  LIVE.name = name; LIVE.d = new Date(); LIVE.data = null; LIVE.shadow = false; LIVE.day = "";
  $("#liveName").textContent = stratLabel(name) + " · LIVE";
  showOverlay("liveOverlay");
  renderLive();
  try {
    const r = await fetch("/api/strategy-live?strategy=" + encodeURIComponent(name));
    LIVE.data = r.ok ? await r.json() : {days: {}, trades: [], table: [], error: true};
  } catch (_) { LIVE.data = {days: {}, trades: [], table: [], error: true}; }
  renderLive();
}
function liveStep(n) { LIVE.d.setMonth(LIVE.d.getMonth() + n); LIVE.day = ""; renderLive(); }
function liveDay(key) { LIVE.day = LIVE.day === key ? "" : key; renderLive(); }
function closeLive() { hideOverlay("liveOverlay"); }
$("#liveOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeLive();
});
function fmtTicks(x) { return x == null ? "—" : (x > 0 ? "+" : "") + Number(x).toFixed(1); }
function renderLive() {
  const v = calView(LIVE, "liveDay");
  $("#liveMonth").textContent = v.month;
  $("#liveSince").textContent = v.since;
  $("#liveGrid").innerHTML = v.grid;
  $("#liveTotal").textContent = v.total;
  $("#liveNote").textContent = v.note;
  $("#liveTable").innerHTML = v.table;
  $("#liveTrades").innerHTML = v.trades;
}

/* ---- P&L calendar ---- */
let CAL = {account: "", d: new Date()};
function openCal(account) {
  CAL.account = account; CAL.d = new Date();
  showOverlay("calOverlay"); loadCal();
}
function closeCal() { hideOverlay("calOverlay"); }
function calStep(n) { CAL.d.setMonth(CAL.d.getMonth() + n); loadCal(); }
$("#calOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeCal();
});
async function loadCal() {
  const y = CAL.d.getFullYear(), m = CAL.d.getMonth();
  const month = y + "-" + String(m + 1).padStart(2, "0");
  const d = await (await fetch(`/api/calendar?month=${month}&account=${encodeURIComponent(CAL.account)}`)).json();
  $("#calAcct").textContent = d.account || CAL.account;
  $("#calMonth").textContent = CAL.d.toLocaleString("en-US", {month: "long", year: "numeric"});
  const grid = $("#calGrid");
  let html = ["S", "M", "T", "W", "T", "F", "S"].map(x => `<div class="dow">${x}</div>`).join("");
  const first = new Date(y, m, 1), days = new Date(y, m + 1, 0).getDate();
  for (let i = 0; i < first.getDay(); i++) html += `<div class="cal-cell blank"></div>`;
  for (let day = 1; day <= days; day++) {
    const key = month + "-" + String(day).padStart(2, "0");
    const pnl = d.days[key];
    const cls = pnl > 0 ? " up" : pnl < 0 ? " down" : "";
    html += `<div class="cal-cell${cls}">${day}` +
      (pnl != null ? `<span class="pnl">${usd(pnl)}</span>` : "") + `</div>`;
  }
  grid.innerHTML = html;
  $("#calTotal").textContent = Object.keys(d.days).length ? "Month " + usd(d.total) : "";
  $("#calNote").textContent = Object.keys(d.days).length ? "" :
    (d.history_since ? "no closed days this month yet" :
     "history starts today — equity snapshots began when the app first ran");
}

