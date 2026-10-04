# TtEKw8SKVKk - "How I Prompt AI to Backtest a Trading Strategy (Live Client Call)"
Channel: Lil Fish | https://youtu.be/TtEKw8SKVKk | 35 min | written from auto-captions (some words garbled)
Gist: He builds one long prompt live for a student's hidden NQ 5-minute strategy, lets Claude Code make ~500 variants, and reads the dashboard. The student's rules are never revealed.
## 2. TESTABLE RULES
- The student's strategy: NQ, 5-minute bars, rules private. VAGUE: everything (trigger, stop, target, filters).
- Dimensions asked for: entry windows 09:00-10:00 ET and 10:00-11:00 ET, plus all other hours; all bar sizes; month and year seasonality; days with big volume events; filters volume, ATR, VWAP, EMA, trend lines, "liquidity"; high-impact news days; weekday. VAGUE: no parameters.
- What the hidden strategy showed (not transferable): only the NY session profitable; Wed-Fri positive, Mon-Tue not; entries by hour 900 at 09h, 1,200 at 10h, 23 at 11h (he calls the 11h edge misleading).
- Event-day overlay claims: FOMC good, OPEC and maybe CPI to avoid, "election" 100% win rate (tiny sample, he laughs).
## 3. CLAIMED RESULTS
- ~2,000 trades (later "2,200"); by year: 2023 large loss, 2024 and 2025 large gains, 2026 modest.
- Best variant: profit factor 1.21 on ~1,300 trades ("pretty good", worth a live test). Number of variants in the table not stated (asked for 500).
- Months: Nov-Dec best; worst said as Aug-Oct and also Mar-Apr (caption or slip). March 2020 very bad, May 2026 very good. Tariff crash and COVID shown as bad events.
- Evidence: dashboard and a 33-page PDF shown on screen, run was done off camera while he was at the gym; nothing audited.
## 4. SEARCH / PROMPT METHOD (short)
- Prompt order: deliverable and format (PDF + HTML dashboard); context (strategy, NQ, 5m); data (TradingView MCP bridge first, then free Databento futures, then free NQ CFD when bars run out; a last source is garbled); questions from his own experience; "make ~500 variants on your own"; P&L curve for each; persona "quant testing expert, user is a beginner, do not ask me anything"; "think deeply".
- Advice: leave out context that could make the model refuse (e.g. willingness to breach prop rules). Wants hundreds of trades per test. Costs and fills never mentioned; no code review. Run was so heavy it shut down his Mac Mini.
## 5. OVERFITTING HANDLING
- None formal. Spots the 23-trade hour. Reads per-year curves to see decay. Then proposes trading only Nov-Dec and Wed-Fri from the same full-sample table (data mining). No holdout, no multiple-testing view over 500 variants; live testing is the only out-of-sample step.
## 6. PROP-FIRM TACTICS
- Almost none: wants max losing streaks tested for prop use; suggests skipping Mon-Tue, Aug-Oct and OPEC/CPI days. No drawdown or sizing simulation shown.
## 7. LOOK AT SCREEN
- [4:02] 33-page variant PDF and HTML dashboard layout.
- [25:22] header stats (trades, net P&L, expectancy, year by year) and entry-hour table.
- [27:26] ranked variant list with win rate, PF, trades: top and bottom rows and the variant definitions missing.
- [28:27] session heat table ("around the clock") and month-by-year seasonality grid.
- [29:27] event-of-day table (FOMC, OPEC, CPI, election, tariffs) with counts.
## 8. RED FLAGS
- Hidden strategy, so nothing to replicate; single unaudited run; seasonality cut from ~2,000 trades; "do not ask me" hides assumption errors; CFD data; election 100% shows tiny samples treated as signals; showcase to sell mentorship.
## 9. VERDICT
- SKIP for strategies. Only borrow: per-year equity curve per variant and a trade-count column beside every hour/weekday table (we already do the grid and heat map).
