## 1. SOURCE
Title: 3x Trading WORLD CHAMPION Reveals the "Low-Effort" Strategy That Won the Robbins Cup (Live On Chart) | Channel: IQCapital (a prop firm: the end card sells $9 challenges) | 103 min | uploaded 2026-10-02
URL: https://youtu.be/nlLGlVJGrtw
Guest: Gianluca Bruni, 23. Robbins World Cup: Q4 2025 +58 %, Q2 2026 +104 %, Q3 2026 leading at +254 % (the host's words).
Read: the full auto-captions, every minute (2026-10-10), plus six frames (chart, analytics screen, prop sim). Captions are garbled in places: "50inut" = 15-minute, "week" = wick, "wheel rate" = win rate. The size ladder below the 4/5 score is the worst-garbled part.
Gist: a validation lecture (in sample / out of sample, expectancy not win rate, regimes, autocorrelation), then ONE strategy: with a trending session, wait for price to come back into the PREVIOUS session's value area, then enter the close that breaks above its high on LOW volume. Stop at the candle's low, target 1:2, 15-minute bars. Half of the claimed profit is said to come from sizing.

## 2. EVERY IDEA AND STRATEGY
1. Validation [10:00-22:00]: build on one period, test on a period the market has not seen, do not change a rule after the test. Expectancy and Sharpe may move 20-25 % (normal); a 30 % drop = warning, over 50 % = fail ("I tested it"). Good Sharpe above 1.5, 1.4 still fine, below 1 not good. Count how many variants were tried (probability of backtest overfitting). Split the history in 10 chunks and check each. Re-check every 100 trades.
2. Win rate is a scam [22:55-24:30]: judge by expectancy (R per $ risked). His own number: 0.2 R.
3. Regimes [25:00-29:50]: ATR(14) percentile over 200 bars: 0-25 low, 26-50 medium, 51-75 high, 76-100 extreme. Split every result by regime. His strategy works best in "high" (his words; the example named high).
4. Autocorrelation of the strategy's own trades [30:40-46:00]: wins and losses cluster; scale 0-2 none, 3-5 basic, 6-8 strong, 9-10 probably overfit; his own = 7.9. Computed as conditional win rate (after a loss / after a win) against the plain win rate. His claim: after a win the next trade wins 52.5 %; the best trade is the win after a loss streak; the one right after a loss is the weakest (he still takes it small). Re-validate with 100 trades.
5. Regime freshness [46:00-49:45]: a Bayesian online change-point "regime age" 0-100 (TradingView free indicator): 0-30 fresh, 31-60 mature, 61-100 old. His strategy likes fresh.
6. Price efficiency = low effort, big result [49:45-54:20]: a candle that takes out the previous candle's high (its highest wick) while its volume is below the 20-period average or falling.
7. THE ENTRY (long; he only draws the long) [60:00-79:00, 15-minute bars, same bar size for analysis and entry]:
   a. Trend day: the session's developing volume-profile value area sits higher than the previous session's.
   b. Market structure low = the closest VALID down candle before the breakout (valid = body larger than its longest wick). If price trades below it, the setup is dead (he says the trigger then has negative expectancy).
   c. Price comes back into the previous session's value area (a touch is enough).
   d. Trigger candle: closes above the previous session's VAH by at least 6 NQ points (0.6 on forex), its high takes out the previous candle's high, and its volume is below the 20-average or falling.
   e. Enter at that close, stop at the low of the trigger candle, target 1:2 (he tried 1:1 to 1:5, "1:2 best").
   f. More trades on the same two conditions until price reaches the market structure high; the last target is that high. No continuation if the VAH-break trade was not taken. A reduced RR is fine near the high.
   g. No trade when news (NFP, CPI) sits at the trigger: it tested worse on news days.
8. Meta label [54:20-59:40]: five yes / no points: best regime, best autocorrelation position (the win after a loss streak), fresh regime, reducing volume / low effort, New York session. Risk by score: 5 = half Kelly, 4 = quarter Kelly, then smaller (garbled; one-sixth at the low end), 1 of 5 still traded very small.
9. Monte Carlo [97:30-98:20]: 10,000 shuffles, 41 lose money.
10. Prop use [90:30-95:00]: his strategy "is built for the championship, not for prop"; in prop the number of trades matters more than expectancy.

## 3. NEAREST PIPELINE FIT
- NOTHING FITS AS TAUGHT. No entry rule in blueprint_blocks breaks the PREVIOUS session's VAH on a close with a low-volume engulf. Missing pieces: (i) VAH break with a 6-point buffer after price came back inside the old value area, (ii) a "volume below its 20-average" gate on the trigger bar (the filter list has rvol / volume, but a card names no filter), (iii) the valid-candle structure low as an invalidation, (iv) the exit at the move's structure high, (v) size by a 5-point score, (vi) the loss-streak state of the strategy's own trades, (vii) 15-minute bars: the pipeline runs 1 and 5 only, and he says a different bar size breaks it.
- On file, different: `va_reclaim` (below yesterday's VAL, then a close back above: a reclaim, not a break). Cards nq_value_reclaim_mid, nq_value_reclaim_nyam_long (reached the unseen days: -$8,458), es_value_reclaim_nyam, gc_value_reclaim_nyam all stopped. Same card cannot be added twice.
- On file, the opposite idea: `vol_spike_break` (break on HIGH volume): nq_vol_break, nq_vol_break_pm, gc_vol_break_london all stopped at P1.3. His claim is the reverse (low volume is better): that contrast is testable once the piece is built.
- BUILT 2026-10-11 as family `va_break` (engine/families/vabreak.py) and run through the taught lane, 5 and 15 minutes: see section 8. Nothing was added to the queue.

## 4. CLAIMED RESULTS
- 147 R in two years on NQ, expectancy 0.2 R (last 60 trades 0.17), a Sharpe-type ratio 2.2 (last 60: 2.05), autocorrelation "7.9, 100 % sure". 0.2 R at 1:2 means a 40 % win rate (0.4 x 2 - 0.6 = 0.2): consistent.
- Prop sim on his firm's rules, 200 evaluations: pass about 40 % (best 92 of 200, worst 71 of 200); 200 funded accounts, one payout each: about $600k in the worst case. Costs are "an approximation". Not Lucid, not our bar.
- Monte Carlo: 41 of 10,000 shuffles lose money.
- "Positive expectancy over the last three years" (his words, no split shown on screen).

## 8. VERDICT
- RESULT 2026-10-11 (taught lane, build days, as taught, long, untuned): 5 min -$74 a trade on 240 trades (PF 0.77, eval odds 16 %); 15 min -$102 on 159 trades (PF 0.79, eval odds 23 %); the neighbours lose too; random long entries beat it. Rule sheet taught/RULE_SHEET_nlLGlVJGrtw_2026-10-11.md; finding 2026-10-11-bruni-value-area-break-low-effort-loses.
- A claim, not a result: the numbers come from his own tool and his own tuned choices (15 min, 6 points, 1:2, ATR 14 / 200, the 50 % cut-off, "I tested it" each time), with no count of how many variants he tried: exactly what the luck count in the pipeline tracks.
- Half of the profit is the sizing. By his own numbers (40 % win, 1:2) full Kelly is 10 % of the account per trade and half Kelly 5 %: a championship bet, not a prop-account size. The pipeline judges the plain row at one size, so that half cannot be tested there.
- The entry alone is a fair, simple continuation idea (value-area break, low-effort candle, 1:2) and cheap to try: one new family (`va_break`: prior-session VAH close-break, buffer, trigger bar takes out the previous high, volume at or below its 20-average, stop at the trigger bar's low). Open question for the owner: which session's value area (09:30-16:00 as `va_reclaim` uses, or the full Globex day) and whether 5 minutes may stand in for 15.
- Related on file: [[conti-three-rules-plain]] (also volume-profile and ATR framing), the heat-map-is-a-coin-flip finding (a count of variants matters).
