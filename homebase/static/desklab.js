/* Pure helpers for a Lab strategy on the Desk page (2026-10-09): the sentences, the dot and the numbers of a promoted
 * strategy, read from what the chart service answers (GET /api/tester/desklab).
 *
 * Display only. A promoted strategy lands switched OFF; switched on it runs in SHADOW: the runner writes down its orders
 * and nothing is sent, and nothing here talks to the desk. These functions return plain TEXT; the page escapes it (esc / jsArg) where it builds markup.
 *
 * `row` = one strategy of that answer (the record without its code, plus `today` and `days`); `runner` = {alive, ...}.
 * What the record does not carry (the session, the bar size) is left out of a line, never made up.
 *
 * Loads as a plain <script> on the desk page (window.DeskLab) and as a CommonJS module under `node --test`.
 */
(function (root, factory) {
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  }
  if (root) {
    root.DeskLab = mod;
  }
})(typeof self !== "undefined" ? self : (typeof global !== "undefined" ? global : null), function () {
  "use strict";

  var MINUS = "−";
  var DASH = "—";
  var TIME_RE = /^\d{1,2}:\d\d$/;

  var TAG_TITLE = "It writes down its orders. Nothing is sent.";
  var NET_WORDS = "What it would have made today, after costs";
  var REBUILT = "rebuilt from today's prices";
  var NOTE = "From the Lab. Switched on, it runs on live prices in shadow: it writes down its orders and nothing is sent.";
  var GONE = "That strategy is not on the Desk any more. Promote it again from the Lab.";
  var EMPTY_DAY = "Nothing yet today.";
  var NOT_ANSWERING = "The chart service is not answering, so this strategy cannot be shown right now.";
  var NOT_CHECKED = "Not checked yet.";
  var ACCOUNTS_CAPTION = "Accounts come with the Desk update. Until then it runs in shadow.";

  function num(v) {
    return typeof v === "number" && isFinite(v) ? v : null;
  }
  function text(v) {
    return typeof v === "string" ? v : "";
  }
  function dollars(abs) {
    return "$" + abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }
  // +$120 / −$120 / $0 : whole dollars, a real minus sign (the page's usdS), "—" for no number
  function usd(v) {
    v = num(v);
    if (v === null) return DASH;
    var r = Math.round(Math.abs(v));
    return r === 0 ? "$0" : (v < 0 ? MINUS : "+") + dollars(r);
  }
  // a loss or nothing, never a gain: a drawdown is a loss whichever sign it came with
  function loss(v) {
    v = num(v);
    if (v === null) return DASH;
    var r = Math.round(Math.abs(v));
    return r === 0 ? "$0" : MINUS + dollars(r);
  }
  function price(v) {
    v = num(v);
    return v === null ? "" : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function label(row) {
    var r = row || {};
    return text(r.label) || text(r.name);
  }

  function alive(runner) {
    return !!runner && runner.alive === true;
  }
  function dayOf(row) {
    var t = row && row.today;
    return t && typeof t === "object" ? t : null;
  }

  // The one line of state. Order: the switch (off does nothing, runner or not), then the runner, then the day.
  function stateText(row, runner) {
    if (!row || row.enabled !== true) return "Off";
    if (!alive(runner)) return "Runner is not running";
    var t = dayOf(row), why = t ? text(t.why) : "";
    switch (t && t.state) {
      case "running": return why || "Running in shadow";
      case "done": return "Done for today";
      case "stopped": return why ? "Stopped: " + why : "Stopped";
      case "not_today": return "Does not trade today";
      case "off": return "Off";
      default: return "Waiting for the session";
    }
  }

  // The sidebar dot, in step with the words: off / shadow / warn.
  function dotClass(row, runner) {
    if (!row || row.enabled !== true) return "off";
    if (!alive(runner)) return "warn";
    var t = dayOf(row), state = t && t.state;
    if (state === "off" || state === "not_today") return "off";
    if (state === "stopped") return "warn";
    if (state === "running" && text(t.why)) return "warn";
    return "shadow";
  }

  // What today would have made, after costs, at the size it was promoted with: a number or null.
  function todayNet(row) {
    var t = dayOf(row);
    return t ? num(t.net) : null;
  }
  // The tooltip of that number: "..., after costs, 2 contracts" (the record's size; left out when it has none).
  function netTitle(row) {
    var q = num(row && row.qty);
    return q !== null && q >= 1 ? NET_WORDS + ", " + q + (q === 1 ? " contract" : " contracts") : NET_WORDS;
  }
  // A day made by catch-up (promoted or switched on mid-session, or a runner that started again) says so beside its
  // state, while it runs or is done: "Running in shadow · rebuilt from today's prices". "" otherwise.
  function rebuiltNote(row, runner) {
    var t = dayOf(row);
    if (!t || t.rebuilt !== true || !row || row.enabled !== true || !alive(runner)) return "";
    return t.state === "running" || t.state === "done" ? REBUILT : "";
  }

  // One would-be order of the day: its time and its words, marked the way the page marks a shadow signal ("would ...":
  // nothing was sent) -- the runner's words with "would" in front; a refused one says why after "Would be refused:".
  function orderLine(o) {
    var r = o && typeof o === "object" ? o : {};
    var said = text(r.text), why = text(r.refused);
    said = said ? "would " + said.charAt(0).toLowerCase() + said.slice(1) : "";
    return {
      t: text(r.t),
      text: why ? said.replace(/\.+$/, "") + ". Would be refused: " + why : said,
      refused: !!why,
    };
  }

  // One would-be trade of the day: side and size, entry to exit, how it ended; and its net.
  function tradeLine(t) {
    var r = t && typeof t === "object" ? t : null;
    if (!r) return { text: "", net: null };
    var side = text(r.side), px = price(r.entry_px), xpx = price(r.exit_px);
    var head = (side ? side.charAt(0).toUpperCase() + side.slice(1) : "") + (num(r.qty) !== null ? " " + r.qty : "");
    var enter = [text(r.entry_t), px].filter(Boolean).join(" ");
    var leave = [text(r.exit_t), xpx].filter(Boolean).join(" ");
    var parts = [head.trim(), enter && leave ? enter + " to " + leave : enter, leave ? text(r.reason) : ""].filter(Boolean);
    return { text: parts.join(" · "), net: num(r.net) };
  }

  // One day of "Matched the backtest": the date, the daily match's sentence, what the day would have made, and whether
  // the day was rebuilt by catch-up. A past day comes cut to {date, state, why, net, match, rebuilt}: no more is read.
  function matchLine(day) {
    var d = day && typeof day === "object" ? day : {};
    var m = d.match && typeof d.match === "object" ? d.match : null;
    return {
      date: text(d.date),
      text: (m && text(m.text)) || NOT_CHECKED,
      ok: m && typeof m.ok === "boolean" ? m.ok : null,
      net: num(d.net),
      rebuilt: d.rebuilt === true,
    };
  }

  function sessionText(row) {
    var w = row && row.session_window;
    return Array.isArray(w) && w.length === 2 && TIME_RE.test(w[0]) && TIME_RE.test(w[1]) ? w[0] + "-" + w[1] + " ET" : "";
  }
  function barMinutes(row) {
    var n = row && row.bar_minutes;
    return typeof n === "number" && isFinite(n) && n > 0 && Math.floor(n) === n ? n : 0;
  }

  // "NQ · 09:25-16:00 ET · 1-minute bars · from the Lab"
  function specLine(row) {
    var r = row || {}, bars = barMinutes(r);
    return [text(r.root), sessionText(r), bars ? bars + "-minute bars" : "", "from the Lab"].filter(Boolean).join(" · ");
  }

  // The backtest it was promoted on, as the page's figures: [{k, v}].
  function figures(row) {
    var run = (row && row.run) || {};
    var wr = num(run.win_rate), pf = num(run.profit_factor), n = num(run.trades);
    return [
      { k: "Net", v: usd(run.net) },
      { k: "Win rate", v: wr === null ? DASH : Math.round(wr) + "%" },
      { k: "Trades", v: n === null ? DASH : String(n) },
      { k: "Profit factor", v: pf === null ? DASH : pf.toFixed(2) },
      { k: "Deepest drawdown", v: loss(run.max_drawdown) },
    ];
  }

  function promotedText(row) {
    var d = new Date(row && row.promoted_utc);
    if (isNaN(d.getTime())) return DASH;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" });
  }

  // The skin's Setup card: [[name, value], ...]
  function setupRows(row) {
    var r = row || {}, bars = barMinutes(r), q = num(r.qty), sha = text(r.sha256);
    return [
      ["Market", text(r.root) || DASH],
      ["Session", sessionText(r) || DASH],
      ["Bars", bars ? bars + " min" : DASH],
      ["Size", q === null ? DASH : q + (q === 1 ? " contract" : " contracts")],
      ["Promoted", promotedText(r)],
      ["Code", sha ? sha.slice(0, 8) : DASH],
      ["Orders", "None: shadow"],
    ];
  }

  // What a strategy's page says when it has no row to show. `read` = how the last read of the list went:
  // null = none finished yet, false = it failed, true = it worked (so the name really is not on the Desk).
  function missingText(read) {
    if (read === true) return GONE;
    if (read === false) return NOT_ANSWERING;
    return "Loading\u2026";
  }
  function switchTitle(on) {
    return on ? "ON: it runs in shadow" : "OFF: it does nothing";
  }
  // the confirm dialog's two lines: "Remove <name> from the Desk? Its history is kept."
  function removeAsk(name) {
    return { title: "Remove " + name + " from the Desk?", body: "Its history is kept." };
  }


  /* ====================================================================================================================
   * Step B (task B6): a promoted strategy that the Desk itself knows. Its desk id is lab_<name>, its kind is "lab", and
   * /api/status gives it a `lab` block: {name, mark, limits, state, why, trades_today, mode_today, runner, rounds,
   * refused, read_only}. `s` below is one entry of /api/status `strategies` (cfg, day_status, accounts, lab); `book` is
   * its rows of ST.book ([{account, qty}]); `row` is the chart service's row for it (DESKLAB), or null when that
   * service does not answer. The words are the design's table (section E), exactly. All of it returns plain TEXT.
   * ==================================================================================================================== */
  var PREFIX = "lab_";
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  var STATE_WORDS = {
    off: "Off", shadow: "Running in shadow", waiting: "Waiting for the session", watching: "Watching", working: "Order working",
    in_position: "In position", done: "Done for today", runner_down: "Runner down", check: "Check it",
    disarmed: "Disarmed: written down only",
  };
  var NEXT_SESSION = "Starts with the next session.";
  var STOPPED_TODAY = "Stopped for today.";            // the Desk's own sentence for a stop that has no other cause
  var QUIET_STOPS = ["", "off", STOPPED_TODAY];         // a stop that only means "not any more today": ON, it starts with the next session
  var OTHER_DESK = "Another Desk is running on this store.";
  var LIMITS_CAPTION = "Set the limits first. Then assign an account.";
  var NOTE_SHADOW = "From the Lab. With no account it runs in shadow: it writes down its orders and nothing is sent.";
  var NOTE_ACCOUNTS = "From the Lab. Its orders go to the accounts below. Every entry carries a stop held at the broker.";
  var EDIT_LIMITS = "Edit limits";
  var SAVE_LIMITS = "Save limits";
  var CANCEL = "Cancel";
  var OLD_TITLE = "From an earlier day";
  var CLEAR = "Clear";
  var CLEARED = "Cleared.";
  var BOOKED_NEXT = "Booked. It starts with the next session.";
  var LIVE_NOTE = "It will trade real money on its next order. Every entry carries a stop held at the broker.";
  var NOT_ANSWERING_DESK = "The Desk is not answering.";
  var BROKER_REFUSED = "The broker refused it: ";
  var SAY_TRADES = "Trades a day: a whole number from 1 to 20.";
  var SAY_QTY = "Contracts: a whole number from 1 to 10.";
  var SAY_RISK = "At risk per trade: a dollar amount above 0.";
  var SAY_LAST = "No new trade after: a time like 11:00, before the flat time.";
  var SAY_FLAT = "Flat by: a time like 15:55, no later than 15:55.";
  var FLAT_LATEST = "15:55";
  var DEFAULT_START = "09:25";                         // the Strategy's own default session start
  var HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

  function deskId(name) {
    return PREFIX + name;
  }
  function isObj(v) {
    return !!v && typeof v === "object";
  }
  // ONE ROW, NEVER TWO: true when the Desk's own strategies hold lab_<name> for this chart-service row.
  function onDesk(strategies, w) {
    return isObj(strategies) && isObj(w) && typeof w.name === "string" && w.name !== "" &&
      Object.prototype.hasOwnProperty.call(strategies, PREFIX + w.name);
  }
  function blockOf(s) {
    return s && isObj(s.lab) ? s.lab : null;
  }
  function stopQuiet(lab) {
    return QUIET_STOPS.indexOf(text(lab && lab.why).trim()) >= 0;
  }
  // ON and stopped for today by nothing but the switch: it trades again from the next session (ruling, B3 concern 2).
  function startsNext(s) {
    var lab = blockOf(s);
    return !!lab && lab.state === "stopped" && !!s.cfg && s.cfg.enabled === true && stopQuiet(lab);
  }
  // The one line of state, from lab.state / lab.why exactly as the server sends them.
  function deskState(s) {
    var lab = blockOf(s);
    if (!lab) return STATE_WORDS.check;
    if (lab.state === "stopped") {
      if (startsNext(s)) return NEXT_SESSION;
      var why = text(lab.why).trim();
      return why ? "Stopped: " + why : "Stopped";
    }
    if (Object.prototype.hasOwnProperty.call(STATE_WORDS, lab.state)) return STATE_WORDS[lab.state];
    return text(lab.why).trim() || STATE_WORDS.check;   // a state the table has no word for: the server's own sentence
  }
  // The sidebar dot, in step with the words: off / shadow / live / warn, or "" for a plain ON.
  function deskDot(s) {
    var lab = blockOf(s);
    if (!lab) return "warn";
    switch (lab.state) {
      case "off": return "off";
      case "shadow": return "shadow";
      case "waiting": case "watching": case "done": return "";
      case "working": case "in_position": return "live";
      case "stopped": return startsNext(s) ? "" : "warn";
      default: return "warn";
    }
  }
  function readOnly(s) {
    var lab = blockOf(s);
    return !!lab && lab.read_only === true;
  }
  // The account picker: locked until limits exist, and while another Desk owns the store. Fail closed with no block.
  function accountsLock(s) {
    var lab = blockOf(s);
    if (!lab) return { locked: true, caption: LIMITS_CAPTION };
    if (lab.read_only === true) return { locked: true, caption: OTHER_DESK };
    if (!isObj(lab.limits)) return { locked: true, caption: LIMITS_CAPTION };
    return { locked: false, caption: "" };
  }
  function deskNote(hasAccounts) {
    return hasAccounts ? NOTE_ACCOUNTS : NOTE_SHADOW;
  }
  // Does today's day run in shadow? The server's word for the day when it has one (an account assigned after the
  // session began leaves the day in shadow), else whether any account is booked.
  function inShadow(s, book) {
    var lab = blockOf(s), mode = lab ? lab.mode_today : null;
    if (mode === "shadow") return true;
    if (mode === "desk") return false;
    return !(Array.isArray(book) && book.length > 0);
  }

  // ---- limits
  function limitsRows(limits) {
    var l = isObj(limits) ? limits : {};
    var trades = num(l.max_trades_day), qty = num(l.max_qty), risk = num(l.max_risk_usd);
    return [
      { k: "Trades a day", v: trades === null ? DASH : String(trades) },
      { k: "Most contracts per account", v: qty === null ? DASH : String(qty) },
      { k: "Most at risk per trade", v: risk === null ? DASH : dollars(Math.round(risk)) },
      { k: "No new trade after", v: HHMM.test(text(l.last_entry_et)) ? l.last_entry_et + " ET" : DASH },
      { k: "Flat by", v: HHMM.test(text(l.flat_et)) ? l.flat_et + " ET" : DASH },
    ];
  }
  // What the dialog shows when it opens: the limits as set, or empty fields (one contract is the default).
  function limitsFields(limits) {
    var l = isObj(limits) ? limits : null;
    if (!l) return { trades: "", qty: "1", risk: "", last: "", flat: "" };
    var show = function (v) { return num(v) === null ? "" : String(v); };
    return { trades: show(l.max_trades_day), qty: show(l.max_qty), risk: show(l.max_risk_usd), last: text(l.last_entry_et), flat: text(l.flat_et) };
  }
  function whole(v, lo, hi) {
    var t = text(v).trim();
    if (!/^\d+$/.test(t)) return null;
    var n = parseInt(t, 10);
    return n >= lo && n <= hi ? n : null;
  }
  // The same checks the Desk makes (labcfg.parse_limits), with its sentences, one per field. `start` = the strategy's
  // session start ("HH:MM"); the Desk is the judge when it differs. -> {errors: {trades?, qty?, risk?, last?, flat?}, body | null}.
  // The body is exactly what the fields say: nothing is rounded, padded or filled in.
  function checkLimits(fields, start) {
    var f = isObj(fields) ? fields : {}, errors = {}, body = {};
    var trades = whole(f.trades, 1, 20), qty = whole(f.qty, 1, 10);
    if (trades === null) errors.trades = SAY_TRADES; else body.max_trades_day = trades;
    if (qty === null) errors.qty = SAY_QTY; else body.max_qty = qty;
    var rt = text(f.risk).trim().replace(/^\$/, "").replace(/,/g, ""), risk = null;
    if (/^\d+(\.\d+)?$/.test(rt)) {
      risk = Number(rt);
      if (!(isFinite(risk) && risk > 0 && risk <= 1e9)) risk = null;
    }
    if (risk === null) errors.risk = SAY_RISK; else body.max_risk_usd = risk;
    var last = text(f.last).trim(), flat = text(f.flat).trim();
    if (!HHMM.test(last)) errors.last = SAY_LAST; else body.last_entry_et = last;
    if (!HHMM.test(flat) || flat > FLAT_LATEST) errors.flat = SAY_FLAT; else body.flat_et = flat;
    if (!errors.last && !errors.flat) {
      var from = HHMM.test(text(start)) ? start : DEFAULT_START;
      if (!(from <= last && last < flat)) errors.last = SAY_LAST;
    }
    return { errors: errors, body: Object.keys(errors).length ? null : body };
  }
  function limitsTitle(label) {
    return "Limits for " + label;
  }

  // ---- what a refused request says: the Desk's own sentence, no prefix
  function refusalText(r, err) {
    var said = !err && isObj(r) ? (typeof r.detail === "string" ? r.detail : typeof r.error === "string" ? r.error : "") : "";
    said = said.trim();
    return said ? said.slice(0, 200) : NOT_ANSWERING_DESK;
  }

  // ---- today's trades, old blocks, refusals
  function shortDate(iso) {
    var m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(text(iso));
    var mo = m ? parseInt(m[2], 10) : 0;
    return m && mo >= 1 && mo <= 12 ? MONTHS[mo - 1] + " " + parseInt(m[3], 10) : "";
  }
  var EXIT_WORDS = {
    tp: "at the target", sl: "at the stop", flat: "closed at the flat time", manual_flat: "flattened by hand", stopped: "stopped",
    kill: "killed", killed: "killed", cancelled: "cancelled",
  };
  function exitWord(reason) {
    var r = text(reason);
    return EXIT_WORDS[r] || r.replace(/_/g, " ");
  }
  // One trade of the day. A row of lab.rounds: {account, round, status, side, qty, entry_fill, exit_fill, exit_reason, pnl,
  // why[, carried, date, detail]}. `who` = the account's short name. detail = the broker's words, under a failed entry.
  function roundLine(r, who) {
    if (!isObj(r)) return { text: "", net: null, bad: false, detail: "", carried: false };
    var carried = r.carried === true, why = text(r.why).trim(), status = text(r.status);
    var side = text(r.side) || text(r.entry_side), q = num(r.qty);
    var head = (side + (q !== null ? " " + q : "")).trim();
    var inPx = price(r.entry_fill), outPx = price(r.exit_fill);
    var parts = [text(who), head], bad = false, net = null, detail = "";
    if (carried) {
      parts.push(shortDate(r.date), why);
      bad = true;
    } else if (status === "error") {
      parts.push(why || STATE_WORDS.check);
      bad = true;
      var d = text(r.detail).trim();
      if (d) detail = d.indexOf(BROKER_REFUSED) === 0 ? d : BROKER_REFUSED + d;
    } else if (status === "done") {
      parts.push(inPx && outPx ? inPx + " to " + outPx : inPx ? "in at " + inPx : "", exitWord(r.exit_reason));
      net = num(r.pnl);
    } else if (status === "live") {
      parts.push(inPx ? "in at " + inPx : "", STATE_WORDS.in_position);
    } else if (status === "placed" || status === "placing") {
      parts.push(STATE_WORDS.working);
    } else {
      parts.push(status.replace(/_/g, " "));
    }
    return { text: parts.filter(Boolean).join(" · "), net: net, bad: bad, detail: detail, carried: carried };
  }
  // Today's trades and the blocks carried from an earlier day, apart: an old trade is never counted in today's.
  function splitRounds(rows) {
    var out = { today: [], old: [] };
    (Array.isArray(rows) ? rows : []).forEach(function (r) {
      if (!isObj(r)) return;
      (r.carried === true ? out.old : out.today).push(r);
    });
    return out;
  }
  function refusedLine(x, who) {
    var r = isObj(x) ? x : {}, said = text(r.text);
    return { t: text(r.t), text: said && who ? said + " (" + who + ")" : said };
  }

  // ---- the sentences of the switch, the flatten and the book
  function switchOnAccounts(n) { return n + " is ON. Its orders go to its accounts."; }
  function switchOnShadow(n) { return n + " is ON: it runs in shadow."; }
  function switchOnNext(n) { return n + " is ON. It starts with the next session."; }
  function switchOff(n) { return n + " is OFF. Unfilled orders are cancelled. An open position keeps its stop and is closed at the flat time. It trades again from the next session."; }
  // The toast after a switch-on: stopped for today first (the ruling), then with accounts, then shadow.
  function switchOnToast(n, s, book) {
    if (s && startsNext(s)) return switchOnNext(n);
    return Array.isArray(book) && book.length > 0 ? switchOnAccounts(n) : switchOnShadow(n);
  }
  // An account added while today's day runs in shadow: "Booked. It starts with the next session." (ruling, Q3)
  function bookedNext(s, before, after) {
    var lab = blockOf(s);
    return !!lab && lab.mode_today === "shadow" && !!s.cfg && s.cfg.enabled === true &&
      Array.isArray(before) && Array.isArray(after) && after.length > before.length;
  }
  function flattenAsk(n) {
    return { title: "Flatten " + n + "?", body: "Cancels its orders, closes its own position on every account, and switches it OFF. It trades again from the next session.", action: "Flatten & turn off" };
  }
  // A Lab flatten also answers with plain steps that are not failures ("This trade had already ended.", "nothing of its
  // own is left to close"): they are taken out before the page reads the rest for failures.
  var FLATTEN_PLAIN = ["This trade had already ended.", "nothing of its own is left to close"];
  function flattenSteps(results) {
    if (!isObj(results)) return results;
    var out = {};
    Object.keys(results).forEach(function (a) {
      var steps = results[a];
      out[a] = Array.isArray(steps) ? steps.filter(function (x) { return FLATTEN_PLAIN.indexOf(String(x).trim()) < 0; }) : steps;
    });
    return out;
  }

  // ---- the Desk strategy's line under its name and its Setup card
  function deskSpec(c, row) {
    var sess = row ? sessionText(row) : "";
    return [text(c && c.symbol), sess, "from the Lab"].filter(Boolean).join(" · ");
  }
  function deskSetupRows(s, row, book) {
    var lab = blockOf(s);
    if (!lab) return [];
    var c = s.cfg || {}, l = limitsRows(lab.limits), bars = row ? barMinutes(row) : 0;
    var mark = Array.isArray(lab.mark) ? lab.mark : [], sha = text(mark[0]);
    return [
      ["Instrument", text(c.symbol) || DASH],
      ["Session", (row && sessionText(row)) || DASH],
      ["Bars", bars ? bars + " min" : DASH],
      ["Trades a day", l[0].v],
      ["Most contracts", l[1].v],
      ["Most at risk", l[2].v],
      ["No new trade after", l[3].v],
      ["Flat", l[4].v],
      ["Promoted", mark[1] ? promotedText({ promoted_utc: mark[1] }) : DASH],
      ["Code", sha ? sha.slice(0, 8) : DASH],
      ["Orders", inShadow(s, book) ? "Shadow" : "Through the Desk"],
    ];
  }

  // ---- the Activity lines of the journal's lab_* events: (record, strategy's name, " on <account>") -> [text, tone?]
  function plur(n, a, b) { return n + " " + (n === 1 ? a : b); }
  function clip(v) { return text(v).slice(0, 160); }
  var activity = {
    lab_refused: function (r, who, on) { return [who + " order refused" + on + " — " + clip(r.text), "warn"]; },
    lab_runner_down: function (r, who) { return [who + ": runner down", "neg"]; },
    lab_runner_back: function (r, who) { return [who + ": runner back"]; },
    lab_stopped: function (r, who) {
      var why = text(r.why).trim();
      return QUIET_STOPS.indexOf(why) >= 0 ? [who + " stopped for today"] : [who + " stopped for today — " + clip(why), "warn"];
    },
    lab_flatten: function (r, who) {
      var res = isObj(r.results) ? Object.keys(r.results).map(function (k) { return r.results[k]; }) : [];
      if (!res.length) return [who + " flatten — nothing was open"];
      var n = res.length, bad = res.some(function (x) { return !x || x.ok === false; });
      return bad ? [who + " flatten — check it on " + plur(n, "account", "accounts"), "neg"] : [who + " flattened on " + plur(n, "account", "accounts")];
    },
    lab_cancelled: function (r, who, on) {
      return num(r.part) ? [who + " entry cancelled" + on + " — part of it had filled", "warn"] : [who + " entry cancelled" + on];
    },
    lab_limits_set: function (r, who) {
      var l = r.limits;
      if (!isObj(l)) return [who + " limits set"];
      var t = num(l.max_trades_day), q = num(l.max_qty), k = num(l.max_risk_usd);
      return [who + " limits set: " + plur(t, "trade", "trades") + " a day, up to " + plur(q, "contract", "contracts") + ", " +
        dollars(Math.round(k)) + " at risk, no new trade after " + text(l.last_entry_et) + ", flat by " + text(l.flat_et)];
    },
    lab_round: function (r, who, on) {
      var q = num(r.qty), n = num(r.round);
      return [who + " trade" + (n !== null ? " " + n : "") + " started" + on + (q !== null ? " (" + plur(q, "contract", "contracts") + ")" : "")];
    },
    lab_settled: function (r, who, on) { return [who + ": every order of the last trade has ended" + on]; },
    lab_check: function (r, who, on) { return [who + " needs a check" + on + " — " + clip(r.reason), "neg"]; },
    lab_carry: function (r, who, on) { return [who + ": a trade from " + text(r.date) + " is still unchecked" + on, "warn"]; },
    lab_carry_cleared: function (r, who, on) { return [who + ": the old trade from " + text(r.date) + " was cleared" + on]; },
    lab_exit_unconfirmed: function (r, who, on) { return [who + ": the close was not confirmed" + on + ". Its stop is still working.", "neg"]; },
    lab_cancel_raced_fill: function (r, who, on) { return [who + ": an entry filled as it was cancelled" + on, "warn"]; },
    lab_open_without_cfg: function (r, who, on) { return [who + " has a trade open but is not on this Desk. Check it.", "neg"]; },
    lab_removed: function (r, who) { return [who + " taken off the Desk"]; },
  };

  return {
    TAG_TITLE: TAG_TITLE, NOTE: NOTE, GONE: GONE, EMPTY_DAY: EMPTY_DAY, NOT_CHECKED: NOT_CHECKED,
    ACCOUNTS_CAPTION: ACCOUNTS_CAPTION, NOT_ANSWERING: NOT_ANSWERING,
    usd: usd, label: label, stateText: stateText, dotClass: dotClass, todayNet: todayNet, netTitle: netTitle,
    rebuiltNote: rebuiltNote, orderLine: orderLine,
    tradeLine: tradeLine, matchLine: matchLine, specLine: specLine, figures: figures, setupRows: setupRows,
    missingText: missingText, switchTitle: switchTitle, removeAsk: removeAsk,
    // Step B: the strategy the Desk itself knows
    deskId: deskId, onDesk: onDesk, deskState: deskState, deskDot: deskDot, startsNext: startsNext, readOnly: readOnly,
    accountsLock: accountsLock, deskNote: deskNote, inShadow: inShadow, limitsRows: limitsRows, limitsFields: limitsFields,
    checkLimits: checkLimits, limitsTitle: limitsTitle, refusalText: refusalText, roundLine: roundLine, splitRounds: splitRounds,
    refusedLine: refusedLine, switchOnAccounts: switchOnAccounts, switchOnShadow: switchOnShadow, switchOnNext: switchOnNext,
    switchOff: switchOff, switchOnToast: switchOnToast, bookedNext: bookedNext, flattenAsk: flattenAsk, flattenSteps: flattenSteps, deskSpec: deskSpec,
    deskSetupRows: deskSetupRows, activity: activity,
    OTHER_DESK: OTHER_DESK, LIMITS_CAPTION: LIMITS_CAPTION, EDIT_LIMITS: EDIT_LIMITS, SAVE_LIMITS: SAVE_LIMITS, CANCEL: CANCEL,
    OLD_TITLE: OLD_TITLE, CLEAR: CLEAR, CLEARED: CLEARED, BOOKED_NEXT: BOOKED_NEXT, LIVE_NOTE: LIVE_NOTE,
  };
});
