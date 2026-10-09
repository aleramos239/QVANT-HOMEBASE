# tFKOaF4HMcg: My Updated Trading Strategy (2026)

## 1. SOURCE
- Title: "My Updated Trading Strategy (2026)"
- Channel: JadeCap. Length 16:37. Uploaded 2026-08-05. URL: https://youtu.be/tFKOaF4HMcg
- Gist: the "daily sweep model": bias from the higher timeframe, wait for a sweep of an old high or low that closes back (SFP), enter on that close with the stop past the wick, exit at a level or by time.
- Written from auto-captions. The market is never named; example prices of 27,400 to 30,100 look like NQ (our guess).
- Words used below: SFP = swing failure pattern. PDH / PDL = previous day's high / low. HH / HL / LH / LL = higher high, higher low, lower high, lower low.

## 2. EVERY IDEA AND STRATEGY
1. The "daily sweep model" [2:02] to [3:02]
   - One setup only. Price runs a previous high or low (previous week, previous day or previous session), fails to hold beyond it, and he trades the reversal back through the range to a liquidity level.
   - Bias from the higher timeframe, entry on the lower one.
   - Market: VAGUE. Max trades a day: VAGUE (one setup, repeated daily).
2. Timeframe pairs [3:02]
   - Swing: weekly bias, 4h entry. Short-term (may hold overnight): daily bias, 1h entry. Day trader or scalper: 4h or 1h bias, 15m and 5m entry.
   - He says the model works on every timeframe; only speed and trade count change.
3. Step 1: trend or range [4:04]
   - Up = HL and HH. Down = LL and LH. Range or unclear = watch the edges of the range, maybe no trade.
4. Two-pass read of the higher timeframe [4:04] to [6:06]
   - Pass 1: zoom out, read the sequence of highs and lows.
   - Pass 2: compare the last candle with the one before. HL and HH = bullish. LH and LL = bearish. Outside bar = strong confirmation ("closed a specific way": VAGUE). Inside bar = indecision.
   - Write the bias down before looking for entries.
5. Bias picks the side [6:06]
   - Bullish: only look for a sweep of a low. Bearish: only a sweep of a high. No bias: no trade.
6. Mark levels to the scale of the trade [6:06]
   - Swing: previous weekly high / low plus highs and lows inside last week.
   - Day trade: PDH / PDL plus intraday highs and lows (session highs / lows).
   - Scalp: daily levels plus previous session highs / lows.
   - Outer extremes = main targets. Inner levels = where to look for the sweep.
7. Swing point definition [7:06]
   - Three candles. Swing high: the middle candle's high is above the highs on both sides. Swing low: the mirror.
8. SFP definition [7:06]
   - Price runs above the swing high, then a candle closes back below it. Mirror for lows.
   - Story given: shorts are stopped out and breakout buyers are trapped.
9. Entry and stop [8:06]
   - No extra entry model, no indicator. Enter on the close of the candle that makes the SFP.
   - Stop above or below the wick of that candle. Price back through the wick = trade idea dead.
10. Exit A: time-based [8:06] to [9:06]
   - London entry: manage before the New York open. New York open or AM entry: manage or exit around or before lunch.
   - Reason: volume drops and trends stall where sessions meet. Exact clock times: VAGUE. "Manage" (close or tighten): VAGUE.
11. Exit B: liquidity-based [9:06]
   - Target the previous daily high or low (the next pool of resting orders).
12. Example long [9:06] to [12:06]
   - Bias: daily chart bullish (yesterday made a higher low and higher high than the day before).
   - Level: the last intraday swing low inside yesterday's range. Bullish, so no swing highs are marked.
   - Trigger: after the market opens, a candle raids that swing low and closes back above it.
   - Entry: long on that close, 1 contract. Stop 27,455.25 (below the low). Target 27,918.50 = PDH. He says about 1.3 to 1.
   - Our arithmetic: entry near 27,657, stop about 200 points.
   - Entry bar size: VAGUE (not said; looks like the 1h pair). Target hit.
13. Example short on the 1h chart [12:06] to [13:07]
   - Bias: 1h structure of lower highs and lower lows.
   - Levels: the intraday swing highs, marked before the AM session. Target: a far low.
   - Trigger: price runs a swing high. First hour: no close back below, so no entry. Next hour: closes back below, so enter.
   - Entry: short on that 1h close, 2 contracts. Stop 30,096 (above the SFP wick). Target 29,330.75. He picks the far low out of three possible lows.
14. Partial and break-even [13:07] to [14:08]
   - With 2 contracts: close one at the first intraday low, trail the stop on the other to break-even, hold for PDL.
   - He also warns the trade sat in drawdown first.
15. Live trade: 1h trend plus a 5m SFP in the afternoon [14:08] to [15:08]
   - Bias: each 1h candle makes a lower low and lower high than the one before.
   - Trigger: inside the next 1h candle, a 5m SFP of a 5m swing high (price goes above, a 5m candle closes below).
   - Entry: short on a small retracement after that 5m close (not at the close).
   - Stop: above a nearby 5m swing point, not above the SFP wick. He says he should have used the wick.
   - Exit: stop trailed hard at about 3R; the target was not reached; stopped out on the trailed stop for about 3R.
   - Time: "leading up into the afternoon". Exact time: VAGUE.
16. Expected win rate about 50% [1:01]
   - He says an edge that works about half the time is enough. No reward to risk floor stated with it.
17. One setup, and watch it for a month first [1:01] to [2:02] [15:08]
   - A strategy must refuse trades; too many tools means there is always a trade. Mark levels and watch for at least a month before trading. Process points, not entry rules.

## 3. NEAREST PIPELINE FIT
1. Model: `sweep_rev` (prior-day and overnight high / low, close back inside) and `liq` in sweep mode (Asia, London, swing, equal, 5-day levels). 5m bars, session nyam, both sides.
2. Timeframe pairs: only the day-trader pair fits (1h bias as the "hourly trend" filter, 5m entry). Weekly / 4h and daily / 1h pairs cannot be run.
3. Trend or range: filter "hourly trend with". No range detector on the list; "low volatility" is a loose stand-in.
4. Two-pass read: nothing fits pass 2 (last candle vs the one before, outside bar, inside bar). Stand-in: hourly or 15-minute trend with.
5. Side by bias: `sweep_rev` or `liq` sweep with "hourly trend with" on, so longs come only after a swept low in an uptrend. This fits.
6. Levels: `liq` has prior-day, overnight, Asia, London, 5-day, swing and equal highs / lows. Fits. The 5-day level stands in for weekly.
   - Cannot do: "all intraday swing highs inside yesterday's range" as he draws them.
7. Swing point: the pipeline's swing level uses its own, much wider, definition. A 3-candle swing is not a setting on the list. Check before testing.
8. SFP: `sweep_rev` / `liq` sweep. Fits.
9. Entry on the close: fits `sweep_rev` as described (close back inside, then reverse).
   - Cannot do: stop at the wick. Try 20, 30, 45 NQ points and 1.5 x ATR as stand-ins.
10. Time exit: cannot do. No time exits. The only clock rule is flat by 15:58.
   - Loose stand-in: run the idea in nyam with a target of 1 or 2 x stop.
11. Level target: cannot do. Try targets of 1, 2 and 3 x stop, and no target.
12. Example long: `liq` sweep of a swing low (also prior-day low and overnight low with `sweep_rev`), long only, nyam, 5m, filter hourly trend with.
   - Stop 45 NQ points or 3 x ATR; target 1 x stop (his was about 1.3 x).
   - Cannot do: a 200 point stop, the daily two-candle bias, target at PDH, a 1h entry bar.
13. Example short: same as 12, short side, swing / prior-day / overnight highs.
   - Cannot do: the 1h close-back wait (bars are 1m or 5m), target at a far low, 2 contracts with a partial.
14. Partial and break-even: cannot do. Neither exists.
15. Live trade: `liq` sweep of a swing high / low on 5m, sessions mid and pm, both sides, filter hourly trend with. Target 3 x stop; stop 10 or 20 NQ points.
   - Cannot do: entry on a retracement after the close, stop at a nearby swing point, trailing stop.
16. Not a rule.
17. Not a rule.

## 4. CLAIMED RESULTS
- [0:00] "Wins like this, this and this": screen only.
- [12:06] Example long: target at PDH hit, about 1.3 to 1. Replay.
- [14:08] Example short: first target and then PDL hit. Replay.
- [15:08] Live trade: about 3R on the day, out on a trailed stop.
- [16:09] Student results "like this, this and this": screen only.
- [1:01] He says the edge wins about 50% of the time, maybe less or more. No count, no test.
- No losing trade shown.

## 5. RISK AND SIZING RULES
- Stop above or below the wick of the SFP candle; price back through it kills the idea [8:06].
- No bias, no trade [6:06].
- 1 contract in the long example; 2 contracts in the short example so one can be taken off early [11:06] [13:07].
- After the first target: one contract off, stop on the rest to break-even [14:08].
- Live trade: stop trailed at about 3R [15:08].
- No dollar risk, no account size, no daily loss limit, no max trades given.

## 6. LOOK AT SCREEN
- [4:04] to [6:06] slides for trend, range and the last-candle comparison.
- [7:06] the three-candle swing drawing and the SFP drawing.
- [9:06] to [11:06] the daily chart read, and which intraday swing low he marks (he says no other low draws his eye).
- [11:06] to [12:06] the SFP candle, entry, stop and target lines; the chart's bar size.
- [12:06] to [14:08] the 1h short: the highs marked, the hour with no close back, the three candidate lows.
- [14:08] to [15:08] the live trade: 1h candles on the right, the 5m swing high, his entry and both stop moves.

## 7. RED FLAGS
- Ends with a pitch for a paid mentorship, "five spots" [16:09].
- Called "new" and "updated", but it is the same SFP reversal as his February video (wZ4ea0VJnrw) with the 5m FVG step removed.
- Replay examples are winners picked after the fact; levels are chosen by eye.
- Example stop of about 200 NQ points for a 1.3 to 1 target: too big for a 50K prop account.
- In the live trade he breaks his own rules (entry not on the close, stop not at the wick) and the result depends on a trailing stop.
- Says a 50% win rate is enough, while the shown long pays only 1.3 to 1. Thin if true.
- Exits are a choice between time and level, made by feel.

## 8. VERDICT
- The cleanest statement of the rule: bias, sweep of an old high or low, enter on the close back, stop past the wick. Repeats TLEaD163obc (same model, less bias detail) and the core of Y8gUPDVnDgw and wZ4ea0VJnrw.
- Testable as `sweep_rev` / `liq` sweep on NQ with the hourly trend filter. Wick stops, level targets, time exits, partials and trailing cannot be run.
