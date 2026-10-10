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
  var NET_TITLE = "What it would have made today, after costs, 1 contract";
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

  // What today would have made, after costs, 1 contract: a number or null.
  function todayNet(row) {
    var t = dayOf(row);
    return t ? num(t.net) : null;
  }

  // One would-be order of the day: its time and its words; a refused one says why after "Would be refused:".
  function orderLine(o) {
    var r = o && typeof o === "object" ? o : {};
    var said = text(r.text), why = text(r.refused);
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

  // One day of "Matched the backtest": the date, the daily match's sentence, what the day would have made.
  function matchLine(day) {
    var d = day && typeof day === "object" ? day : {};
    var m = d.match && typeof d.match === "object" ? d.match : null;
    return {
      date: text(d.date),
      text: (m && text(m.text)) || NOT_CHECKED,
      ok: m && typeof m.ok === "boolean" ? m.ok : null,
      net: num(d.net),
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

  return {
    TAG_TITLE: TAG_TITLE, NET_TITLE: NET_TITLE, NOTE: NOTE, GONE: GONE, EMPTY_DAY: EMPTY_DAY, NOT_CHECKED: NOT_CHECKED,
    ACCOUNTS_CAPTION: ACCOUNTS_CAPTION, NOT_ANSWERING: NOT_ANSWERING,
    usd: usd, label: label, stateText: stateText, dotClass: dotClass, todayNet: todayNet, orderLine: orderLine,
    tradeLine: tradeLine, matchLine: matchLine, specLine: specLine, figures: figures, setupRows: setupRows,
    missingText: missingText, switchTitle: switchTitle, removeAsk: removeAsk,
  };
});
