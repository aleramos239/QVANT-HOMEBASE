# fi--3nBHsNg - "I Used AI To Increase My Win-Rate (AI Daytrading Masterclass)"
Channel: Lil Fish | https://youtu.be/fi--3nBHsNg | 57 min | written from auto-captions (some words garbled)
Gist: A talk, not a strategy: myths about win rate, prop-firm vocabulary, how to widen one idea into many variants, why he prefers recent data, and a rule against copy-trading evals. No concrete entry or exit rule is given.
## 2. TESTABLE RULES (no strategy; only search dimensions and acceptance bars)
- Filters to add to a base idea: VWAP, EMA, RSI, ATR, volume, trend lines. VAGUE: no lengths or thresholds.
- Entry/exit levers: limit vs market vs timed entry, any bar size, take-profit and stop distance in points, and a time exit (enter, run a timer, exit when it ends). VAGUE: no durations.
- Time of day: Asia quiet, London a bit more, 08:30 ET news, 09:30 ET open, 14:00 ET Wednesday event, 14:30 speeches. VAGUE: no tested windows.
- Calendar expansion: weekday, month of year, scheduled news (e.g. weekly jobless claims at 08:30).
- His bar for a keeper: profit factor >= 1.5 with >= 100 trades inside a recent window; he runs 1.2-1.4 himself; a student reports a mechanical 1.9 (no proof). Wants >= 100 trades per sample.
## 3. CLAIMED RESULTS
- "20,000 strategies, 13 million trades in two weeks" (first said 17M, then corrected); some profitable ones go live "this week". Nothing shown.
- 10,000 = 50 core ideas x 200 variants (his explanation of the other video). His example of "5 news x 5 filters x 5 weekdays x 12 months x 20 timeframes = 100+" adds where it should multiply.
- Only claim with a number he used himself: PF 1.2-1.4 on live candidates. No sample sizes or periods.
## 4. SEARCH / PROMPT METHOD
- Pick a core idea, then expand: bar size, weekday, month, filters, news days. Run all, rank by profit factor, look at the per-year P&L curve, need >= 100 trades, favour recent months, then live test, then prop.
- Tools: Claude Code; a top model writes prompts, a cheaper coding model runs them (model names as in captions). No data source or cost model stated here.
## 5. OVERFITTING HANDLING
- None formal. Good: per-year curves, minimum trade counts, coin-flip talk on small samples. Bad: ranks on the whole window then chooses by the last 3 weeks' slope (regime chasing); says older data is mostly useless. No holdout, no multiple-testing view.
## 6. PROP-FIRM TACTICS
- Account size is really the max loss limit. Never use intraday trailing drawdown (open profit raises the floor: +75 then a -100 trade leaves less room than end-of-day). Consistency rules: ~50% eval (a $1,600 day moved a $3,000 target to $3,200), ~40% funded, 20% on instant-funded (needs ~6 equal winning days). Low win rate + home runs get blocked. Says negative reward:risk can win in props.
- Prop clustering: do not copy the same trades onto 12 accounts in a high-frequency system; run them separately so results approach the true pass rate. (Same expected passes; only the spread changes.)
- Order: strategy, backtest, read firm rules and adapt, live test, then risk money.
## 7. LOOK AT SCREEN
- Almost nothing is lost; he draws by hand. [36:22]-[37:24] per-year P&L chart story (2023-24 good, 2025 bad, 2026 good): strategy unnamed.
- [38:24]-[40:27] three candidate equity curves he compares by recent slope: names and stats missing.
- [30:11] a "core strategy" is named, the name is lost in the captions.
## 8. RED FLAGS
- No rules, no data, no evidence for the 13M-trade claim; recency chasing; arithmetic slips on consistency; "more history is worse" is only half true; heavy mentorship pitch; no cost model mentioned.
## 9. VERDICT
- SKIP as a source of strategies. Only ideas worth keeping: time exit as an exit type, a "still positive in the last 6 months" flag (information only, never the pick rule), consistency-rule check for firms that have one.
