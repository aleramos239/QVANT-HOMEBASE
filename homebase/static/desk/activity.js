/* ---- activity log (W4): what happened, in plain words ----
   One sentence per journal row -- "Connected APEX…048 (login)", "Chart-trading limits set to
   50 / 100", "NQ930 bought 3 @ 30,726.50 on …049" -- instead of `event key=value`. The raw line
   stays one step away: the row's tooltip, a click on the row, or Raw in the section head for
   every row. An event this table doesn't know still reads as words, and a row it can't read
   falls back to them too -- never blank, never a crash. Text is escaped (it is the broker's own
   words, sometimes). tone: "neg" a failure that needs eyes, "warn" a refusal or skip, "pos" /
   "neg" a closed trade's P&L, "" plain. */
const fmtPx = (v) => v == null || v === "" || !isFinite(v) ? "—" : Number(v).toLocaleString("en-US",
  Number.isInteger(Number(v)) ? {} : {minimumFractionDigits: 2, maximumFractionDigits: 6});
/* A strategy's name as the desk shows it: its cfg.label when it has one (gc_nfp -> GC_NFP/CPI), else its id.
   Display only: every API, the book and the journal keep the id. */
const stratLabel = (n) => {
  const s = ((typeof ST !== "undefined" && ST && ST.strategies) || {})[n];
  return String((s && s.cfg && s.cfg.label) || n || "").toUpperCase();
};
const actStrat = (r) => stratLabel(r.strategy);
const actOn = (r) => r.account ? " on " + acctShort(r.account) : "";
const actErr = (e) => (typeof e === "string" ? e : JSON.stringify(e == null ? "" : e)).slice(0, 160);
const actFail = (r) => r.ok ? "" : " — FAILED: " + actErr(r.error);
/* A flatten or cancel reports its steps as text -- "market Sell 3: ok", "cancel 123: ok" -- and a
   failure in the same list: "market Sell 3: <error>", "not flat — stop/target left working",
   "position unreadable (…) — stop/target left working", "cancel [entry] 123: <error>", "… — check
   it" (engine.py). Read them; never assume the benign case (review M3). A step counts as done only
   when it matches one of the engine's own OK forms; anything else -- an error that runs over several
   lines, a step this page doesn't know -- is a failure or CHECK IT (second review). A result that
   is not a list of steps cannot be read, so it says so. */
const STEP_OK = [/^market (Buy|Sell) \d+: ok$/, /^cancel (entry )?\S+: ok$/, /^the account is already flat$/,
                 /^already killed — nothing to do$/];
function stepFailures(steps) {
  const f = {flatten: [], cancel: [], check: []};
  if (!Array.isArray(steps)) { f.check.push("its result is unreadable"); return f; }
  for (const raw of steps) {
    const s = String(raw).trim();
    if (STEP_OK.some(re => re.test(s))) continue;
    const one = s.replace(/\s+/g, " ");               // an error over several lines reads as one
    let m;
    if ((m = /^market (Buy|Sell) (\d+): ([\s\S]*)$/.exec(s))) f.flatten.push(`market ${m[1]} ${m[2]} refused: ${m[3].replace(/\s+/g, " ")}`);
    else if (/^(not flat|position unreadable)/.test(s)) f.flatten.push(one);
    else if ((m = /^cancel (?:entry )?(\S+): ([\s\S]*)$/.exec(s))) f.cancel.push(`order ${m[1]}: ${m[2].replace(/\s+/g, " ")}`);
    else f.check.push(one);                           // "check it", "status unknown", or a step it doesn't know
  }
  return f;
}
function failText(f, where) {
  return [["flatten", "FLATTEN FAILED"], ["cancel", "CANCEL FAILED"], ["check", "CHECK IT"]]
    .filter(([k]) => f[k].length).map(([k, what]) => `${what}${where} — ${f[k].map(actErr).join("; ")}`).join(" · ");
}
const REFUSED_WHY = {unknown_or_disabled: "it is off", not_a_straddle: "it runs off the price feed, not alerts",
  killed: "it was killed today", already_traded: "it already acted today", outside_window: "outside its time window",
  bad_prices: "the prices were unreadable", inverted_prices: "upper was below lower",
  bad_spread: "the spread did not match its offset", no_assignments: "no accounts are booked",
  all_accounts_skipped: "every booked account holds a manual position or order",
  bad_signal: "the signal was incomplete", levels_wrong_side: "its stop/target were on the wrong side"};
const EXIT_AT = {tp: " at the target", sl: " at the stop"};
function actWould(r) {
  if (r.upper != null || r.lower != null)
    return `Buy stop ${fmtPx(r.upper)} / Sell stop ${fmtPx(r.lower)} × ${r.qty}`;
  return `${r.side} ${r.qty} ${r.entry || ""}${r.entry_price != null ? " @ " + fmtPx(r.entry_price) : ""}` +
    ` · SL ${fmtPx(r.sl)} · TP ${fmtPx(r.tp)}`;
}
const labAct = (k) => (r) => DeskLab.activity[k](r, actStrat(r), actOn(r), acctShort);      // the Lab's journal lines: the words are in desklab.js
const ACTIVITY = {
  armed_toggled: (r) => [r.armed ? "Desk ARMED — signals place real orders" : "Desk disarmed — signals are journaled only"],
  kill_switch: (r) => {
    const n = Object.keys(r.results || {}).length, bad = killFailures(r.results);   // the account-wide sweep is the truth
    return bad.length ? [`Kill everything — FAILED on ${bad.join(" · ")}; desk disarmed`, "neg"]
      : [`Kill everything — ${n} account${n === 1 ? "" : "s"} cancelled and flattened, desk disarmed`, "warn"];
  },
  chart_trading_set: (r, prev) => {
    if (r.cause) return [`Chart trading switched OFF by ${r.cause === "kill" ? "Kill everything" : r.cause}`, "warn"];
    const lim = `${r.max_order_qty} / ${r.max_position_qty}`;
    const flip = !!prev && prev.enabled !== undefined && !!prev.enabled !== !!r.enabled;
    const limits = !!prev && prev.max_order_qty != null &&
      (prev.max_order_qty !== r.max_order_qty || prev.max_position_qty !== r.max_position_qty);
    if (flip && !limits) return [`Chart trading turned ${r.enabled ? "ON" : "OFF"}`];
    if (limits && !flip) return [`Chart-trading limits set to ${lim}`];
    return [`Chart trading ${r.enabled ? "ON" : "OFF"} · limits ${lim}`];
  },
  broker_connected: (r) => [`Connected ${acctShort(r.account)}${r.mode ? ` (${r.mode})` : ""}`],
  reconnect_fell_back_to_login: (r) => [`${acctShort(r.account)}: reconnect failed, logging in again — ${actErr(r.error)}`, "warn"],
  reconcile_error: (r) => [`${acctShort(r.account)}: couldn't re-check its orders after connecting — ${actErr(r.error)}`, "neg"],
  manual_reconnect: (r) => {
    const res = Object.entries(r.results || {}), bad = res.filter(([, v]) => !(v && v.ok));
    return [`Reconnect: ${res.length - bad.length} of ${res.length} reconnected` +
      (bad.length ? ` · failed: ${bad.map(([k]) => acctShort(k)).join(", ")}` : ""), bad.length ? "neg" : ""];
  },
  account_added: (r) => [`Added account ${acctShort(r.account)}${r.live ? " — LIVE" : " (demo)"}`],
  account_removed: (r) => [`Removed account ${acctShort(r.account)}`],
  book_updated: (r) => {
    const a = Array.isArray(r.assignments) ? r.assignments : [];
    return [a.length ? `${actStrat(r)} booked on ` + a.map(x => `${acctShort(x.account)} ×${x.qty}`).join(", ")
                     : `${actStrat(r)} unbooked from every account`];
  },
  strategy_toggled: (r) => [`${actStrat(r)} switched ${r.enabled ? "ON" : "OFF"}${r.cause === "manual_flatten" ? " (Flatten & turn off)" : ""}`],
  lab_refused: labAct("lab_refused"), lab_runner_down: labAct("lab_runner_down"), lab_runner_back: labAct("lab_runner_back"),
  lab_stopped: labAct("lab_stopped"), lab_flatten: labAct("lab_flatten"), lab_cancelled: labAct("lab_cancelled"),
  lab_limits_set: labAct("lab_limits_set"), lab_settings_set: labAct("lab_settings_set"), lab_round: labAct("lab_round"), lab_settled: labAct("lab_settled"),
  lab_check: labAct("lab_check"), lab_carry: labAct("lab_carry"), lab_carry_cleared: labAct("lab_carry_cleared"),
  lab_exit_unconfirmed: labAct("lab_exit_unconfirmed"), lab_cancel_raced_fill: labAct("lab_cancel_raced_fill"), lab_open_without_cfg: labAct("lab_open_without_cfg"),
  lab_removed: labAct("lab_removed"), lab_event_error: labAct("lab_event_error"), lab_intake_error: labAct("lab_intake_error"),
  lab_save_error: labAct("lab_save_error"), lab_carry_fill: labAct("lab_carry_fill"), lab_sidecar_replaced: labAct("lab_sidecar_replaced"),
  lab_unbooked: labAct("lab_unbooked"), lab_unreadable: labAct("lab_unreadable"), lab_restore_error: labAct("lab_restore_error"),
  lab_start_error: labAct("lab_start_error"), lab_key_error: labAct("lab_key_error"), lab_store_error: labAct("lab_store_error"),
  lab_view_error: labAct("lab_view_error"), lab_refresh_error: labAct("lab_refresh_error"), lab_foreign_key: labAct("lab_foreign_key"),
  lab_store_busy: labAct("lab_store_busy"), lab_store_owned: labAct("lab_store_owned"), lab_side: labAct("lab_side"),
  lab_added: labAct("lab_added"),
  timer_gate: (r) => r.gate === true ? [`${actStrat(r)} gate open — trend day (ADX ${fmt(r.adx, 1)})`]
    : r.gate === false ? [`${actStrat(r)} gate closed — chop day (ADX ${fmt(r.adx, 1)}), no trade today`]
    : [`${actStrat(r)} gate unknown — only ${r.bars} daily bars, it will not fire`, "warn"],
  timer_fired: (r) => r.result
    ? [`${actStrat(r)} fired at ${fireHM(r.strategy)} — anchor ${fmtPx(r.anchor)}${r.note ? " · " + actErr(r.note) : ""}`]
    : [`${actStrat(r)} fired at ${fireHM(r.strategy)} — anchor ${fmtPx(r.anchor)} — refused: ${actErr(r.note)}`, "warn"],
  timer_skipped: (r) => r.reason === "gate_chop" ? [`${actStrat(r)} skipped today — chop (ADX ${fmt(r.adx, 1)})`]
    : r.reason === "killed" ? [`${actStrat(r)} skipped — killed today`]
    : r.reason === "manual_position" ? [`${actStrat(r)} skips ${acctShort(r.account)} today — it holds a manual position (${r.net > 0 ? "+" : ""}${r.net})`, "warn"]
    : r.reason === "manual_order" ? [`${actStrat(r)} skips ${acctShort(r.account)} today — a manual order is working`, "warn"]
    : [`${actStrat(r)} skipped — ${actErr(r.reason)}`, "warn"],
  timer_missed: (r) => [`${actStrat(r)} missed today's window (it closed at ${r.window_end})`, "warn"],
  timer_deferred: (r) => [`${actStrat(r)} timer stood down — it already acted today (${r.status})`],
  timer_error: (r) => [`${actStrat(r)} timer error — ${actErr(r.error)}`, "neg"],
  timer_loop_error: (r) => [`Timer error — ${actErr(r.error)}`, "neg"],
  prestage_rtt: (r) => [`${actStrat(r)} staged for the ${fireHM(r.strategy)} fire`],
  prestage_check_failed: (r) => [`${actStrat(r)} pre-open check failed${actOn(r)} — ${actErr(r.error)}`, "warn"],
  morning_readiness: (r) => r.ready ? ["Morning check: ready to trade"]
    : [`Morning check: NOT ready — ${(r.problems || []).map(actErr).join(" · ")}`, "neg"],
  alert_refused: (r) => [`${actStrat(r)} signal refused — ${REFUSED_WHY[r.reason] || actErr(r.reason)}`, "warn"],
  signal_refused: (r) => [`${actStrat(r)} signal refused — ${REFUSED_WHY[r.reason] || actErr(r.reason)}`, "warn"],
  dry_run: (r) => [`${actStrat(r)} dry run${actOn(r)}: would place ${actWould(r)}`],
  shadow_signal: (r) => [`${actStrat(r)} shadow signal${actOn(r)}: would place ${actWould(r)}`],
  placed: (r) => [`${actStrat(r)} placed${actOn(r)}: ${actWould(r)}${r.place_ms != null ? ` (${r.place_ms} ms)` : ""}`],
  place_failed: (r) => [`${actStrat(r)} order REJECTED${actOn(r)}${r.leg ? ` — ${r.leg} leg` : ""} — ${actErr(r.error)}`, "neg"],
  fill_matched_by_side: (r) => [`${actStrat(r)} fill${actOn(r)} matched by side (it came without an order id)`],
  entry_fill: (r) => [`${actStrat(r)} ${r.side === "Sell" ? "sold" : "bought"}${r.qty_filled != null ? " " + r.qty_filled : ""} @ ${fmtPx(r.fill)}${actOn(r)}` +
      (r.fill_vs_anchor ? ` (${r.fill_vs_anchor > 0 ? "+" : ""}${r.fill_vs_anchor} vs trigger)` : "") +
      (r.sibling_cancelled === false ? ` — the other side was NOT cancelled: ${actErr(r.sibling_error)}` : ""),
    r.sibling_cancelled === false ? "neg" : ""],
  brackets_moved: (r) => r.moved === true ? [`${actStrat(r)} stop/target moved to the fill${actOn(r)}: SL ${fmtPx(r.sl)} · TP ${fmtPx(r.tp)}`]
    : r.moved === false ? [`${actStrat(r)} couldn't move stop/target${actOn(r)} — ${actErr(r.error)} (the trigger levels still protect it)`, "warn"]
    : [`${actStrat(r)} stop/target stay${actOn(r)} — ${actErr(r.moved)}`],
  both_filled_emergency: (r) => {
    const t = failText(stepFailures(r.actions), "");
    return [`${actStrat(r)}: BOTH sides filled${actOn(r)} — emergency flatten ${t ? "· " + t : "done"}`, "neg"];
  },
  exit_fill: (r) => [`${actStrat(r)} exited${actOn(r)}${EXIT_AT[r.reason] || ""} @ ${fmtPx(r.fill)}` +
      (r.pnl != null ? `, ${r.pnl > 0 ? "+" : ""}${usd(r.pnl)}` : ""), r.pnl > 0 ? "pos" : r.pnl < 0 ? "neg" : ""],
  sibling_cancel_retry: (r) => r.ok === false
    ? [`${actStrat(r)}: CANCEL FAILED${actOn(r)} — the other entry is still working: ${actErr(r.error)}`, "neg"]
    : [`${actStrat(r)} re-cancelled the other side${actOn(r)}`],
  fill_recovered_on_reconnect: (r) => [`${actStrat(r)} entry (${r.side}) found${actOn(r)} after reconnecting`, "warn"],
  entry_found_by_check: (r) => [`${actStrat(r)} entry (${r.side}) found${actOn(r)} by the order check — its fill message was missed`, "warn"],
  exit_recovered_on_reconnect: (r) => [`${actStrat(r)}${actOn(r)} closed while disconnected — found on reconnect`, "warn"],
  cancelled_unfilled: (r) => [`${actStrat(r)}${actOn(r)}: no fill by the cancel time — entries cancelled`],
  cancel_raced_fill: (r) => [`${actStrat(r)}${actOn(r)}: filled as the entries were cancelled — now in position (${r.net})`, "warn"],
  clock_flat: (r) => {
    const t = failText(stepFailures(r.actions), "");
    return [`${actStrat(r)} flattened${actOn(r)} at the end-of-day time${t ? " · " + t : ""}`, t ? "neg" : ""];
  },
  clock_flat_failed: (r) => [`${actStrat(r)} end-of-day FLATTEN FAILED${actOn(r)} — ` +
    (failText(stepFailures(r.actions), "").replace(/^FLATTEN FAILED — /, "") || "check it"), "neg"],
  killed_run_needs_check: (r) => [`${actStrat(r)}${actOn(r)} needs a check — killed, but still ${r.status} at ${r.at}`, "neg"],
  killed_run_entries_cancelled: (r) => {
    const t = failText(stepFailures(r.actions), "");
    return t ? [`${actStrat(r)}${actOn(r)}: the killed run's entries — ${t}`, "neg"]
             : [`${actStrat(r)}${actOn(r)}: the killed run's entries were cancelled`];
  },
  strategy_kill_requested: (r) => [`${actStrat(r)} kill requested${r.source === "chart" ? " from the chart" : ""}`, "warn"],
  strategy_killed: (r) => {
    const bad = Object.entries(r.results || {}).filter(([, x]) => !x || x.ok === false)
      .map(([a, x]) => `${acctShort(a)}: ` + (failText(stepFailures((x && x.actions) || []), "") || actErr((x && x.error) || "needs a check")));
    return bad.length ? [`${actStrat(r)} killed for today — CHECK ${bad.join(" · ")}`, "neg"]
                      : [`${actStrat(r)} killed for today`, "warn"];
  },
  strategy_kill_check: (r) => [`${actStrat(r)} kill${actOn(r)} needs a check — ${actErr(r.reason)}`, "neg"],
  strategy_killed_after_ack: (r) => {
    const t = failText(stepFailures(r.actions || []), "");
    return (r.ok === false || t)
      ? [`${actStrat(r)} kill${actOn(r)}, once its orders were acknowledged — ${t || "needs a check"}`, "neg"]
      : [`${actStrat(r)} kill finished${actOn(r)} once its orders were acknowledged`];
  },
  strategy_kill_failed: (r) => [`${actStrat(r)} kill FAILED${actOn(r)} — ${actErr(r.error)}`, "neg"],
  account_flatten: (r) => {
    const bad = killFailures({[r.account]: r.results});
    return bad.length ? [`Flatten FAILED on ${bad.join(" · ")}`, "neg"] : [`${acctShort(r.account)}: orders cancelled and positions flattened`];
  },
  routine_reconnects: (r) => [`Routine reconnect · ${r.accounts} account${r.accounts === 1 ? "" : "s"}` + (r.times > 1 ? ` · ${r.times} times since ${hbClock(String(r.since).slice(11, 16))}` : "")],
  manual_flatten: (r) => {
    if (r.source === "chart") return r.ok ? [`Chart: flattened ${r.contract || ""}${actOn(r)}`]
      : [`Chart: FLATTEN FAILED${actOn(r)}${r.contract ? ` (${r.contract})` : ""} — ${actErr(r.error)}`, "neg"];
    const res = Object.entries(r.results || {});
    const bad = res.map(([a, steps]) => failText(stepFailures(steps), " on " + acctShort(a))).filter(Boolean);
    if (bad.length) return [`${actStrat(r)} flatten — ${bad.join(" · ")}`, "neg"];
    return [res.length ? `${actStrat(r)} flattened on ${res.length} account${res.length === 1 ? "" : "s"}`
                       : `${actStrat(r)} flatten — nothing of its was open today`];
  },
  manual_order: (r) => [`Chart order${actOn(r)}: ${r.side} ${r.qty} ${r.contract || r.root || ""} ${r.type || ""}` +
      (r.price != null ? ` @ ${fmtPx(r.price)}` : r.trigger != null ? ` @ ${fmtPx(r.trigger)}` : "") +
      (r.ok ? "" : " — REFUSED: " + actErr(r.error)), r.ok ? "" : "neg"],
  manual_modify: (r) => [`Chart: order moved to ${fmtPx(r.price)}${actOn(r)}${r.contract ? ` (${r.contract})` : ""}${actFail(r)}`, r.ok ? "" : "neg"],
  manual_cancel: (r) => r.ok
    ? [`Chart: ${r.scope === "symbol" ? `cancelled every ${r.contract || ""} order` : "cancelled an order"}${actOn(r)}`]
    : [`Chart: CANCEL FAILED${actOn(r)}${r.contract ? ` (${r.contract})` : ""} — ${actErr(r.error)}`, "neg"],
  manual_exits: (r) => [`Chart: exits set${actOn(r)}${r.contract ? " " + r.contract : ""} — ` +
      [r.sl != null ? "SL " + fmtPx(r.sl) : "", r.tp != null ? "TP " + fmtPx(r.tp) : ""].filter(Boolean).join(" · ") + actFail(r),
    r.ok ? "" : "neg"],
  manual_reverse: (r) => [`Chart: reverse ${r.contract || ""}${actOn(r)} — ${r.step === "flatten" ? "flattened" : `opened ${r.side} ${r.qty}`}${actFail(r)}`,
    r.ok ? "" : "neg"],
  manual_refused: (r) => [`Chart ${r.action || "action"} refused${actOn(r)} — ${actErr(r.reason)}`, "warn"],
  manual_error: (r) => [`Chart ${r.action || "action"} error${actOn(r)} — ${actErr(r.error)}`, "neg"],
  feed_started: (r) => [`Price feed started${Array.isArray(r.watching) && r.watching.length ? " — " + r.watching.join(", ") : ""}`],
  feed_stopped: (r) => [`Price feed stopped — ${actErr(r.reason)}`],
  feed_error: (r) => [`Price feed error${r.strategy ? ` (${actStrat(r)})` : ""} — ${actErr(r.error)}${r.penalized ? " — rate-limited, retrying in 5 min" : ""}`, "neg"],
  feed_loop_error: (r) => [`Price feed error — ${actErr(r.error)}`, "neg"],
  rule_error: (r) => [`${actStrat(r)} rule error — ${actErr(r.error)}`, "neg"],
  clock_error: (r) => [`Clock error — ${actErr(r.error)}`, "neg"],
  desk_key_error: (r) => [`Desk key problem — ${actErr(r.error)}`, "neg"],
  selftest_order: (r) => [`Self-test order${actOn(r)}${r.placed ? (r.placed.ok ? " — placed and cancelled" : " — refused: " + actErr(r.placed.error)) : ""}`,
    r.placed && !r.placed.ok ? "warn" : ""],
  selftest_order_rest: (r) => [`Self-test order${actOn(r)} (REST) — HTTP ${r.http_status}`],
  group_set: (r) => [`${actCycle(r)} ${r.on ? "ON" : "OFF"} — ${(r.members || []).length} strategies on ` +
      `${(r.accounts || []).map(acctShort).join(", ") || "no accounts"}${r.risk_usd ? ` · $${fmt(r.risk_usd, 0)} a trade` : ""}`],
  group_deleted: (r) => [`${actCycle(r)} removed`],
  group_hedge_skipped: (r) => [`${actStrat(r)} skipped a ${actSides(r.sides)} — a ${actSides(r.open)} is open on another account of ` +
      `${actCycle(r).toLowerCase()} (no hedging)`, "warn"],
  group_skipped: (r) => {
    const why = Object.entries(r.accounts || {}).map(([a, w]) => `${acctShort(a)}: ${actErr(w)}`);
    return [`${actStrat(r)} skipped — ${actErr(r.reason)}${why.length ? " (" + why.join(" · ") + ")" : ""}`, "warn"];
  },
  group_save_failed: (r) => [`${actCycle(r)}: the next account could not be saved — ${actErr(r.error)}`, "neg"],
};
/* "Account cycle "apex 300k"": the journal line's own name, else the Desk group's, else its id. */
function actCycle(r) {
  const g = typeof DESKGROUPS !== "undefined" ? DESKGROUPS.groups.find(x => x.id === r.group) : null;
  return `Account cycle "${r.name || (g && g.name) || r.group}"`;
}
const actSides = (s) => (Array.isArray(s) ? s : []).map(x => x === "Buy" ? "long" : x === "Sell" ? "short" : String(x)).join(" and ") || "trade";
/* A Lab strategy's flatten answers with plain steps that are not failures ("This trade had already ended."): read them as plain, for a Lab strategy only. */
for (const k of ["manual_flatten", "clock_flat", "clock_flat_failed"]) {
  const f = ACTIVITY[k];
  ACTIVITY[k] = (r, prev) => f(r && (((ST && ST.strategies) || {})[r.strategy] || {cfg: {}}).cfg.kind === "lab" ? DeskLab.plainRecord(r) : r, prev);
}
function activityLine(r, prev) {
  const f = ACTIVITY[r.event];
  if (f) {
    try {
      const [text, tone] = f(r, prev);
      if (text) return {text, tone: tone || ""};
    } catch (_) { /* a row this formatter can't read falls back to plain words below */ }
  }
  if (String(r.event).indexOf("lab_") === 0) return {text: "Something happened to a Lab strategy. Check it.", tone: "warn"};      // a Lab event with no words of its own: never a raw name
  const what = String(r.event || "event").replace(/_/g, " ");
  return {text: what.charAt(0).toUpperCase() + what.slice(1) + (r.strategy ? " — " + actStrat(r) : "") + actOn(r),
          tone: /error|fail/.test(String(r.event)) ? "neg" : ""};
}
function activityRaw(r) {
  const {ts, et, event, ...rest} = r;
  return [event, ...Object.entries(rest).map(([k, v]) =>
    `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)].join("  ");
}
/* A routine reconnect -- the desk rebuilding a broker connection on the token it already holds, about hourly, every account in
   turn -- is not news: a run of them reads as ONE line (Raw shows each), and "Last event" never points at one. */
const routineRow = (r) => !!r && r.event === "broker_connected" && r.mode === "reconnect";
function foldRoutine(rows) {
  const out = [];
  for (let i = 0; i < rows.length; i++) {
    if (!routineRow(rows[i])) { out.push(rows[i]); continue; }
    let j = i;
    while (j + 1 < rows.length && routineRow(rows[j + 1])) j++;
    const run = rows.slice(i, j + 1), secs = (r) => Date.parse(r.et) / 1000;      // newest first
    const times = 1 + run.filter((r, k) => k > 0 && secs(run[k - 1]) - secs(r) > 120).length;
    out.push({event: "routine_reconnects", ts: run[0].ts, et: run[0].et, since: run[run.length - 1].et,
              accounts: new Set(run.map(r => r.account)).size, times, rows: run});
    i = j;
  }
  return out;
}
let FEED_ROWS = [], FEED_SIG = null, FEED_RAW = false;
const FEED_OPEN = new Set();   // rows opened to their raw line, by ts|et|event|account
function renderActivity(journal) {
  FEED_ROWS = (Array.isArray(journal) ? journal : []).filter(r => r && typeof r === "object" &&
    !(typeof r.event === "string" && r.event.indexOf("lab_") === 0 && typeof DeskLab !== "undefined" && DeskLab.hiddenEvent(r.event)));      // the Lab's named bookkeeping (DeskLab.HIDDEN_EVENTS) shows nothing; every other Lab event shows
  const sig = JSON.stringify([FEED_ROWS, FEED_RAW, [...FEED_OPEN], ACT_WHO, ACT_DAYS, ACT_ROWS === null]);
  if (sig === FEED_SIG) return;           // nothing changed: leave the rows (and a hovered tooltip) alone
  FEED_SIG = sig;
  let day = "";
  $("#feed").innerHTML = (FEED_RAW ? FEED_ROWS : foldRoutine(FEED_ROWS)).map((r) => {
    const prev = r.event === "chart_trading_set" ? FEED_ROWS.slice(FEED_ROWS.indexOf(r) + 1).find(o => o.event === r.event) : null;
    const {text, tone} = activityLine(r, prev);
    const raw = r.rows ? r.rows.map(o => String(o.et || "").slice(11, 19) + "  " + activityRaw(o)).join("\n") : activityRaw(r), key = `${r.ts}|${r.et}|${r.event}|${r.account || ""}`, open = FEED_RAW || FEED_OPEN.has(key);
    const d = String(r.et || "").slice(0, 10), head = ACT_DAYS > 1 && d !== day ? `<div class="feed-day">${esc(actDay(d))}</div>` : "";
    day = d;
    return head + `<div class="feed-row${open ? " open" : ""}" data-k="${esc(key)}" title="${esc(raw)}">` +
      `<span class="t">${esc(hbClock(String(r.et || "").slice(11, 19)))}</span>` +
      `<span class="h${tone ? " " + tone : ""}">${esc(text)}</span>` +
      (open ? `<span class="raw">${esc(raw)}</span>` : "") + `</div>`;
  }).join("") || `<div class="feed-empty">${!actFiltered() ? "Waiting for events…" : ACT_ROWS ? "Nothing in this period." : "Loading…"}</div>`;
}
const actDay = (d) => { try { return new Date(d + "T12:00:00Z").toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric", timeZone: "UTC"}); } catch (_) { return d; } };
/* Activity for one strategy or one group, or for more than today (owner 2026-10-26: "see which strategy copied on which account
   and when"): the Desk's journal for those days (GET /api/journal, strategy/group/days), read again every 15 s while the page is
   open. Everything, today, stays the status poll's own tail. A group shows its strategies' lines and its account cycle's. */
let ACT_WHO = "", ACT_DAYS = 1, ACT_ROWS = null, ACT_BUSY = false, ACT_AT = 0;
const actFiltered = () => ACT_WHO !== "" || ACT_DAYS > 1;
const actRows = (tail) => actFiltered() ? (ACT_ROWS || []) : tail;
function actQuery() {
  const p = new URLSearchParams({days: String(ACT_DAYS), limit: "2000"});
  if (ACT_WHO.startsWith("g:")) {
    const id = ACT_WHO.slice(2), g = groupOf(id);
    p.set("group", id);
    p.set("strategy", (g ? g.members : []).join(","));
  } else if (ACT_WHO.startsWith("s:")) p.set("strategy", ACT_WHO.slice(2));
  return "/api/journal?" + p;
}
async function loadActivity(force) {
  if (!actFiltered() || DEMO || ACT_BUSY || (!force && Date.now() - ACT_AT < 15000)) return;
  ACT_BUSY = true;
  const q = actQuery();
  try {
    const r = await fetch(q);
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    if (q !== actQuery()) return;          // the picks changed while it read: the next read is theirs
    ACT_ROWS = Array.isArray(j && j.events) ? j.events : [];
    ACT_AT = Date.now();
    renderActivity(ACT_ROWS);
  } catch (_) { /* the Desk does not answer: keep what is shown */ }
  finally { ACT_BUSY = false; }
}
/* The Show menu: every Desk group, then every strategy on the Desk (rebuilt only when that list changes, never while it is open). */
function fillActWho() {
  const sel = $("#actWho");
  if (!sel || document.activeElement === sel) return;
  const groups = typeof DESKGROUPS !== "undefined" ? DESKGROUPS.groups : [];
  const strats = Object.keys((ST && ST.strategies) || {}).sort((a, b) => stratLabel(a).localeCompare(stratLabel(b)));
  const opts = [["", "Everything"]].concat(groups.map(g => ["g:" + g.id, "Group: " + g.name]), strats.map(n => ["s:" + n, stratLabel(n)]));
  if (ACT_WHO && !opts.some(([v]) => v === ACT_WHO)) opts.push([ACT_WHO, ACT_WHO.slice(2)]);
  const sig = JSON.stringify(opts);
  if (sel._sig !== sig) {
    sel._sig = sig;
    sel.innerHTML = opts.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join("");
  }
  sel.value = ACT_WHO;
}
function setActivity(who, days) {
  ACT_WHO = who; ACT_DAYS = days; ACT_ROWS = null; ACT_AT = 0;
  fillActWho();
  const d = $("#actDays");
  if (d) d.value = String(days);
  renderActivity(actRows([]));
  if (actFiltered()) loadActivity(true); else if (ST) render();
}
/* "Activity ›" on a strategy's or a group's page: its lines of the last 7 days. */
function openActivity(who) {
  setActivity(who, 7);
  setView("activity");
}
$("#actWho")?.addEventListener("change", (e) => setActivity(e.target.value, ACT_DAYS));
$("#actDays")?.addEventListener("change", (e) => setActivity(ACT_WHO, Math.max(1, parseInt(e.target.value, 10) || 1)));
$("#feed").addEventListener("click", (e) => {
  const row = e.target && e.target.closest && e.target.closest(".feed-row");
  if (!row || FEED_RAW) return;
  const sel = window.getSelection && window.getSelection();
  if (sel && String(sel) !== "") return;   // selecting text to copy is not a click to open
  const k = row.getAttribute("data-k");
  if (FEED_OPEN.has(k)) FEED_OPEN.delete(k); else FEED_OPEN.add(k);
  renderActivity(FEED_ROWS);
});
$("#feedRawBtn").addEventListener("click", () => {
  FEED_RAW = !FEED_RAW;
  $("#feedRawBtn").setAttribute("aria-pressed", String(FEED_RAW));
  renderActivity(FEED_ROWS);
});

