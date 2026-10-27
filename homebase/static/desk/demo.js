/* ---- PREVIEW MODE (?demo=1): sample data, clearly labeled, never real ---- */
function demoStatus() {
  if (!document.getElementById("demoBanner")) {
    const b = document.createElement("div");
    b.id = "demoBanner";
    b.style.cssText = "position:sticky;top:0;z-index:60;background:var(--primary);" +
      "color:var(--primary-foreground);font-size:12px;letter-spacing:.08em;" +
      "text-align:center;padding:6px 0;font-weight:600";
    b.innerHTML = 'PREVIEW MODE — SAMPLE DATA, NOTHING IS REAL &nbsp;·&nbsp; ' +
      '<a href="/" style="color:inherit">exit</a>';
    document.body.prepend(b);
  }
  const A = (label, env, bal, pnl, pos, extra) => ({label, env, connected: true,
    account: label, balance: bal, realized_pnl: pnl,
    open_positions: pos || [], working_orders: 0, ...extra});
  const research_es = {source: "sample data — walk-forward 2023-2025",
    rows: {trades: "210", WR: "44.3%", PF: "1.61", t: "3.21",
           "avg/trade": "$58", maxDD: "−$2,140"},
    caveat: "sample numbers for preview only"};
  const st = (acct, status, extra) => ({strategy: "x", account: acct,
    date: "2026-09-16", qty: 3, status, ...extra});
  return {
    armed: true,
    chart_trading: {enabled: false, max_order_qty: 10, max_position_qty: 20},
    et_now: "2026-09-16T11:42:07-04:00",
    readiness: {ready: true, checks: [
      {level: "ok", label: "Lucid Funded", detail: "connected"},
      {level: "ok", label: "Lucid Eval #1", detail: "connected"},
      {level: "ok", label: "Lucid Eval #2", detail: "connected"},
      {level: "ok", label: "Apex Eval", detail: "connected"},
      {level: "ok", label: "nq930", detail: "done"},
      {level: "ok", label: "ym930", detail: "live"},
      {level: "info", label: "Mode", detail: "ARMED — signals place real orders"}]},
    timer: {date: "2026-09-16", strategies: {
      nq930: {stage: "fired", gate: true, adx: 27.9, anchor: 24618.25},
      es_vwap: {stage: "skipped", gate: false, adx: 14.2, anchor: null}}},
    accounts: {
      "lucid-funded": A("Lucid Funded", "live", 53970.40, 620.00,
                        [{symbol: "NQZ6", net: 3}]),
      "lucid-eval-1": A("Lucid Eval #1", "demo", 51840.20, 310.00),
      "lucid-eval-2": A("Lucid Eval #2", "demo", 49122.60, -180.00),
      "apex-eval":    A("Apex Eval 150K", "demo", 151730.00, 95.50),
      "sandbox":      A("Tradovate Sandbox", "demo", 98450.00, 0.00),
    },
    book: {
      nq930: [{account: "lucid-funded", qty: 3}, {account: "lucid-eval-1", qty: 2},
              {account: "sandbox", qty: 1}],
      ym930: [{account: "apex-eval", qty: 2}, {account: "lucid-eval-2", qty: 1}],
      es_vwap: [{account: "sandbox", qty: 1}],
    },
    strategies: {
      nq930: {cfg: {symbol: "NQ", qty: 3, offset_pts: 10, sl_pts: 5, tp_pts: 15,
                    cancel_et: "12:55", flat_et: "15:55", enabled: true,
                    gated: true, self_fire: true},
        research: {source: "one-shot sealed-year OOS exam · 2025-07-08→2026-07-07 · TV 15s",
          rows: {trades: "167", WR: "47.3%", PF: "2.34", t: "5.04",
                 "avg/trade/mini": "$79.0", "maxDD/mini": "−$1,135",
                 "green months": "10/10"},
          caveat: "does not cover live fill quality — the edge is 2–4 ticks deep"},
        live: {trades: 41, win_rate: 51.2, net: 9840.50, avg_trade: 240.01,
               avg_slip_pts: 0.31, days: 38},
        day_status: "done",
        accounts: [
          st("lucid-funded", "done", {upper_px: 24628.25, lower_px: 24608.25,
            entry_side: "Buy", entry_anchor: 24628.25, entry_fill: 24628.50,
            exit_reason: "tp", exit_fill: 24643.25, pnl: 885.00}),
          st("lucid-eval-1", "done", {qty: 2, upper_px: 24628.25, lower_px: 24608.25,
            entry_side: "Buy", entry_anchor: 24628.25, entry_fill: 24628.75,
            exit_reason: "tp", exit_fill: 24643.25, pnl: 580.00}),
          st("sandbox", "done", {qty: 1, upper_px: 24628.25, lower_px: 24608.25,
            entry_side: "Buy", entry_anchor: 24628.25, entry_fill: 24628.25,
            exit_reason: "tp", exit_fill: 24643.25, pnl: 300.00})]},
      ym930: {cfg: {symbol: "YM", qty: 1, offset_pts: 20, sl_pts: 5, tp_pts: 15,
                    cancel_et: "12:55", flat_et: "15:55", enabled: true,
                    gated: false, self_fire: true},
        research: {source: "one-shot OOS exam · 2025-01-07→2026-09-10 · TV 15s",
          rows: {trades: "434", WR: "50.7%", PF: "1.76", t: "5.76",
                 "avg/trade": "$14.51", maxDD: "−$316", "green months": "19/21"},
          caveat: "modeled friction is already 56% of the $25 risk — thin book"},
        live: {trades: 18, win_rate: 55.6, net: 312.50, avg_trade: 17.36,
               avg_slip_pts: 0.9, days: 17},
        day_status: "live",
        accounts: [
          st("apex-eval", "live", {qty: 2, upper_px: 46120, lower_px: 46080,
            entry_side: "Sell", entry_anchor: 46080, entry_fill: 46079}),
          st("lucid-eval-2", "live", {qty: 1, upper_px: 46120, lower_px: 46080,
            entry_side: "Sell", entry_anchor: 46080, entry_fill: 46078})]},
      es_vwap: {cfg: {symbol: "ES", qty: 1, offset_pts: 6, sl_pts: 3, tp_pts: 9,
                      cancel_et: "12:55", flat_et: "15:55", enabled: true,
                      gated: true, self_fire: true},
        research: research_es,
        live: {trades: 12, win_rate: 41.7, net: -410.00, avg_trade: -34.17,
               avg_slip_pts: 0.4, days: 12},
        day_status: "idle", accounts: []},
      gc_open: {cfg: {symbol: "GC", qty: 1, offset_pts: 4, sl_pts: 2, tp_pts: 6,
                      cancel_et: "12:55", flat_et: "15:55", enabled: false,
                      gated: true, self_fire: false},
        research: {source: "sample data — candidate, unvalidated",
          rows: {trades: "96", WR: "49%", PF: "1.38", t: "1.9"},
          caveat: "sample numbers for preview only"},
        live: null, day_status: "idle", accounts: []},
    },
    journal: [
      {et: "2026-09-16T11:31:02", event: "exit_fill", strategy: "nq930",
       account: "lucid-funded", reason: "tp", fill: 24643.25, pnl: 885.0},
      {et: "2026-09-16T11:31:02", event: "exit_fill", strategy: "nq930",
       account: "lucid-eval-1", reason: "tp", fill: 24643.25, pnl: 580.0},
      {et: "2026-09-16T09:31:18", event: "entry_fill", strategy: "ym930",
       account: "apex-eval", side: "Sell", fill: 46079, anchor: 46080,
       fill_vs_anchor: -1.0},
      {et: "2026-09-16T09:30:01", event: "entry_fill", strategy: "nq930",
       account: "lucid-funded", side: "Buy", fill: 24628.5, anchor: 24628.25,
       fill_vs_anchor: 0.25},
      {et: "2026-09-16T09:30:00", event: "timer_fired", strategy: "nq930",
       anchor: 24618.25, result: true},
      {et: "2026-09-16T09:30:00", event: "placed", strategy: "nq930",
       account: "lucid-funded", source: "timer", upper: 24628.25,
       lower: 24608.25, qty: 3},
      {et: "2026-09-16T09:25:00", event: "morning_readiness", ready: true,
       problems: []},
      {et: "2026-09-16T09:20:04", event: "timer_gate", strategy: "nq930",
       gate: true, adx: 27.9, bars: 119},
    ],
  };
}

/* Chart trading (orders from the chart page; the desk decides) lives in Settings' CHART TRADING
   section -- see buildTrading()/renderChartTrading() there. A Kill switches it off, so it has to
   live somewhere the user can always turn it back on. Arm/Disarm/Kill are in the top bar. */

async function testFire(name) {
  const r = await post("/api/test-alert", {strategy: name});
  toast(testFireWords(r), 8000); refresh();
}
/* {sent:{upper, lower}, result:{ok, accounts}} or a refusal ({ok:false, reason} / a 404's {detail}) -> one sentence */
function testFireWords(r) {
  const res = (r && r.result) || r || {}, s = (r && r.sent) || {}, n = res.accounts;
  if (!res.ok) return `Dry run refused: ${res.reason || res.detail || "no answer"}.`;
  return `Dry run: it would have sent a buy stop at ${fmtPx(s.upper)} and a sell stop at ${fmtPx(s.lower)}` +
    `${typeof n === "number" ? ` on ${n} account${n === 1 ? "" : "s"}` : ""}. Nothing was sent.`;
}

