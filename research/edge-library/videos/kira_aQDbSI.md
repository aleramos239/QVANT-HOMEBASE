# kira_aQDbSI - "I Backtested 10,000 Strategies PART 2 - AI made them profitable without overfit (5 million trades)"
Channel: Lil Fish | https://youtu.be/kira_aQDbSI | 27 min | uploaded 2026-10-08 | written from auto-captions, read in full 2026-10-09 (some words garbled)
Gist: Follow-up to XLMG6-SATRk. He takes six of the losing retail families and adds rules one at a time until the backtest wins, then checks each step on later data. Half the video is a drawing that explains overfitting. No rule is spoken with its numbers; the specs are on screen only.
## 2. TESTABLE RULES (family names only; every setting is missing)
- "Five plus Supertrend" (name garbled) [10:12-13:17]: baseline 4,888 trades 2019-2026, about -0.112R a trade. Step 1 a fixed-point stop: about 3,600 trades, +0.011R. Step 2 a tighter time window: 803 trades, about 8 times the expectancy. Steps 3-5: 400, 300, 358 trades, +0.248R, under one trade a week. VAGUE: market, bar size, Supertrend settings, the stop in points, the window, rules 3-5.
- Opening range breakout [14:18-16:19]: about 1,000 trades at 4.8 a week; after 4 added rules about 300 trades in 7 years, 62% winners, +1.16R (his number). VAGUE: every rule added.
- Liquidity sweep then reclaim ("fractal model", his own) [16:19]: after 3 steps about 300 trades in 7 years, "+271R" (caption; maybe +0.271R). VAGUE: rules.
- VWAP sigma reversion, volume-spike breakout (1,700 trades to 333), "F6 Supertrend flip" (3,152 trades to 314) [16:19-17:22]: same pattern, 90% of trades cut. VAGUE: rules.
- Blocks we hold for these: supertrend, orb, liq sweep, vwap_band / vwap_z, vol_spike_break. Read before in the pipeline: orb, liq sweep, vwap_z + vwap_band, vol_spike_break (all stopped at stage 1). Not read before: supertrend.
## 3. CLAIMED RESULTS
- Six families turned from losing to winning in backtest by adding 3 to 6 rules each. The trade count falls by 70-90% each time.
- "28 or 29% of the NASDAQ fixes" also hold on the S&P 500 [18:22]. 36 of the 10,000 beat the random-entry list (caption unclear).
- Payouts: "four payouts in two weeks", three funded accounts passed in a week, trades placed by Claude [25:28-26:28]. He shows certificates on screen; no ledger, no count of failed evals.
## 4. SEARCH / PROMPT METHOD
- Take the best families from the first search, ask the model what the losing trades have in common, add one rule, re-run, repeat.
- Order of rules he shows most: a fixed-point stop first, then a tighter time window, then filters.
## 5. OVERFITTING HANDLING
- Build 2019-2024, check 2025-2026 [20:24]. Each added rule is kept only if the later period still holds. His finding: rule 5 and 6 looked better in the build and worse later; about 3 rules predicted best.
- He admits the winners of 10,000 may be noise and says to slice and re-test them.
- Weak points: the later period is looked at after every step (it is used to pick the rule count, so it is not unseen); no count of how many rules were tried; no random-entry control on the fixed versions.
## 6. PROP-FIRM TACTICS
- Says most retail families pass an eval 0-1% of the time with an intraday trailing drawdown.
- Low trade count is fine: about one trade a week per strategy; run several.
## 7. LOOK AT SCREEN
- [10:12]-[13:17] the Supertrend steps: the rule added at each step and its numbers.
- [14:18]-[16:19] the opening range breakout steps.
- [16:19]-[17:22] the other four families.
- [18:22] the question-and-answer page (other bar sizes, NQ fix on ES).
## 8. RED FLAGS
- No rule can be rebuilt from the audio. CFD data in part 1. The "test" years guide the choice. Sells a mentorship. "Claude trades my accounts" with no record shown.
## 9. VERDICT
- Method agrees with ours (few rules, build then one later period); ours is stricter (the later days are read once).
- One thing to run: the Supertrend flip, the only family here the pipeline had not read. Added 2026-10-09: nq_supertrend_nyam_long, nq_supertrend_nyam_short (see section 10).
## 10. PIPELINE VERDICT (2026-10-09, build days)
- nq_supertrend_nyam_long: stopped at stage 1. 5-minute map: 61.11 % of boxes profitable (passes), but only 12 boxes at the $70 floor with 200 trades (need 25). 1-minute map: 36.11 %, 2 boxes.
- nq_supertrend_nyam_short: stopped at stage 1. 5-minute map: 46.53 % of boxes profitable, 17 boxes at the floor. 1-minute map: 19.44 %, 0 boxes.
- Session (nyam) and values (mult 2 / 3 / 4) were our choice: the video gives none.
