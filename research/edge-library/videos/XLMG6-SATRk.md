# XLMG6-SATRk - "I Backtested 10,000 Strategies - Here is the Most Profitable (5 million trades)"
Channel: Lil Fish | https://youtu.be/XLMG6-SATRk | 30 min | written from auto-captions (some words garbled)
Gist: AI-run grid of ~10,000 retail-style variants (50 families) on 7 years of free CFD data. Nearly all lose after commissions, so he argues for keeping a human in the loop. The title is click-bait against the content.
## 2. TESTABLE RULES (no full rule set is spoken; specs were on screen only)
- Volume-spike breakout, "most likely to pass" variant: high win rate, low reward:risk, 27 trades in 7 yrs (~0.07/week), max 2 entries/day, skip Wednesday and Friday, flat daily. VAGUE: market, volume multiple, lookback, breakout reference, entry/stop/target, session, bar size.
- Volume-spike breakout, "most total R" variant: ~14% win rate, ~8-9R average winner. VAGUE: every parameter.
- "#121 New York window sweep": only near the NY open, ~1 trade per 3 weeks. VAGUE: all rules. He says both "losing the last 2 years" and "profitable 2024-26" (contradiction or caption error).
- His own old model (liquidity sweep then reclaim): zero profitable variants, median trade about -0.175 (units not said, likely R). VAGUE: rules.
- Factor findings, aggregate only, no numbers: stop type: fixed-distance best (marginal) > fixed time exit (hold ~80 candles, he also says 80 minutes, then close) > structure/wick stop. Entry: stop, confirm, market alike; limit worst. Bar size: bigger = more winners (he favours 30-60 min). Session: NY AM best; London and Asia worst (caption order unclear). Market: Nasdaq best. Cost: round-trip commission under ~3% of stop size wins most often.
## 3. CLAIMED RESULTS
- 5.6M trades (title says 5M); "10,000" and "10,500" strategies both used; 7 yrs CFD data; commissions included.
- Mean cumulative R per variant is negative in all 50 families. Only 60 of 10,000 (0.6%) have >50% chance to pass a 50K eval; most are under 2%.
- 80-100% win-rate variants still lose. A 31R average winner at 7% win rate exists but cannot pass.
- Top total R = volume-spike breakout (0% pass). Top pass chance = a volume-spike breakout with only 27 trades (he calls it unreliable).
- Random control: one random-entry strategy (~150 trades) beat 99% of the variants.
- Evidence: dashboard on screen; audio only gives the headline numbers, no tables.
## 4. SEARCH / PROMPT METHOD
- Asked Claude Code (one night) for the top ~50 retail families, each expanded to ~200 variants over market, bar size, session, stop type, exit type, entry type, max trades/day, weekday skip, daily flat.
- Per variant: trades, win rate, avg R, net R/trade, total R, trades/week, per-year P&L, P(pass 50K), random-control rank. Data: free CFD. Commissions yes; slippage/spread never mentioned.
## 5. OVERFITTING HANDLING
- No holdout, walk-forward or multiple-testing correction mentioned. Only: random control, per-year view, "27 trades = unreliable". Talk of a "hot streak 2024-26" is picking by recent years.
## 6. PROP-FIRM TACTICS
- Ranks by P(pass 50K). Says low win rate + big winners fail consistency rules (50% eval, 20% instant-funded) and daily loss limits; time exits make big wins/losses that clash with them. Claims he passes with "hardly any edge" using eval-cost vs payout maths (his own tool, no proof). Keeps a human deciding on alerts.
## 7. LOOK AT SCREEN
- [5:12]-[9:15] factor charts (cost/stop, market, bar size, session, stop type): need the share of variants profitable per bucket.
- [10:16] table of the 50 families and their mean R: family names and ranking missing.
- [12:19]-[13:20] distribution of P(pass 50K) across variants.
- [19:34]-[20:34] volume-spike breakout spec pages: all parameters (entry, stop, target, session, flat, max trades).
- [21:35] #121 NY window sweep spec and random-control page.
## 8. RED FLAGS
- Click-bait title; CFD not futures (spread/session differ); fill model, slippage, intrabar order never shown; family list hidden; "human discretion is an asset" does not follow (cost drag plus a random baseline explain it); 27 trades in 7 yrs is "2-3 a year" in audio (really ~4); sells a mentorship.
## 9. VERDICT
- MAYBE, cheaply: add a pure time exit (hold N bars, hard stop only) to our exit grid; log cost-to-stop ratio per variant; run a volume-spike breakout family on NQ NY AM with our own grid and nulls. Do not copy any of his families.
