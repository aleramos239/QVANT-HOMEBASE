# wZ4ea0VJnrw: The Only Trading Strategy I'd Use If I Had To Start Over

## 1. SOURCE
- Title: "The Only Trading Strategy I'd Use If I Had To Start Over"
- Channel: JadeCap. Length 10:56. Uploaded 2026-02-28. URL: https://youtu.be/wZ4ea0VJnrw
- Gist: mark hourly swing lows (or highs), wait for the 09:30 open to sweep one and the hourly candle to close back (SFP), then enter on a 5-minute fair value gap with a 2R target.
- Written from auto-captions. The market is never named ("any asset"); example prices near 25,000 look like NQ (our guess). Captions write "rated" for "raided".
- Words used below: SFP = swing failure pattern. FVG = fair value gap (3 bars). PDH = previous day's high.

## 2. EVERY IDEA AND STRATEGY
1. Step 1: mark the hourly swing points [0:00] to [1:02]
   - Bullish day: mark all 1h swing lows before the session (yesterday, and the day before if needed). Bearish day: mark all 1h swing highs.
   - Takes 5 to 10 minutes; can be done on several markets.
   - Market: "any asset, any timeframe" (VAGUE). His pair: 1h as the higher timeframe.
   - How the day's bias is set: VAGUE here (see idea 6). What makes a 1h swing point: not defined in this video.
2. Step 2: hourly SFP at the equity open [1:02] to [3:02] [5:02]
   - Wait for the New York equity open (09:30). One of the marked swing lows is raided and the 1h candle closes back above it. Mirror for shorts.
   - In both examples it is the 1h candle that closes at 10:00.
   - No raid, no trade [5:02].
   - Story given: shorts who chased the open are trapped; early longs were stopped out.
3. Skip SFPs made before the open [2:02] [6:03]
   - An SFP printed pre-market (example near 08:00) is not traded. He waits for session time because of the 09:30 "manipulation".
4. Step 3: enter on a 5-minute FVG [5:02]
   - After the 1h SFP, drop to 5m. Find a bullish 5m FVG (longs).
   - Entry: long as price trades back into the 5m FVG. Edge or middle of the gap: VAGUE.
   - Stop: below candle 2 of the FVG (the big middle candle). Target: 2 to 1 (2R).
   - Mirror for shorts with a bearish FVG and swing highs.
   - Bars: 1h setup, 5m entry. Time window: from the 09:30 open; example entries near 09:57 and 10:20. Latest entry time: VAGUE.
   - Max trades a day: VAGUE. A second FVG later is offered as a second chance if the first was missed [8:04].
5. Which swing low to use [7:03]
   - The one price is trading at right at the equity open. Ignore the lower one. Trade what is in front of you.
6. Bias carries over from a strong day [6:03] to [7:03]
   - Monday was strongly bullish, so on Tuesday he assumes more of the same: only swing lows, and he skips a bearish SFP.
   - Stay on that side until the higher timeframe says otherwise. "Strong": VAGUE (no number).
7. A higher-timeframe target must exist [6:03]
   - He claims any SFP in the expected direction should work if the context is right and there is a higher-timeframe target.
   - Levels he names as targets in example 1: the Asian range high and PDH [5:02]. The spoken target is still 2R.
8. Example 1: 2026-02-09 [1:02] to [6:03]
   - Bullish bias (reason not given). 1h swing lows from the prior day marked. The 1h candle closing at 10:00 raids a low and closes back above.
   - 5m: an SFP at the 09:30 open, then a bullish 5m FVG. Long into the FVG, stop below FVG candle 2, target 2R. Target hit some time after 10:25.
   - His real trade was different: at 09:55 he told his group the hourly SFP was coming and was long minutes later (before the 1h close). He cut the stop to 25,091 (a previous swing point), trailed it again after an FVG held, took 50% off near 10:55, then closed the rest.
9. Example 2: 2026-01-27 [6:03] to [9:05]
   - Monday bullish, so longs only. A pre-market SFP is skipped. The 1h candle closing at 10:00 is a bullish SFP at the swing low price is at.
   - 5m FVG retest, long near 10:20, target 2R.
   - Target hit near 19:10, about 9 hours later, after the evening re-open.
10. Prop-firm close workaround [8:04] to [9:05]
   - Firms force a close at 16:00 or 17:00. Re-enter at the re-open at the same price if there was no big gap.
   - In example 2 the market rose between 16:00 and 18:00, so the re-entry would have missed it; the day trade ends near break-even or a small gain.
11. Process rule [9:05] to [10:05]
   - Trade 09:30 to the close every day the same way. Grade the day on following the plan, not on the result.

## 3. NEAREST PIPELINE FIT
1 and 2. Hourly swing sweep at the open: `liq` in sweep mode with the swing high / low level, session nyam, 5m bars, both sides.
   - The pipeline's swing level uses its own definition, not "every 1h swing low of the last two days". Check before testing. Prior-day low and overnight low (`sweep_rev`) are the stand-ins.
   - Cannot do: the 1h candle close-back at 10:00 (bars are 1m or 5m).
3. Skip pre-open: run the idea in session nyam only. Fits.
4. 5m FVG entry: `fvg`, 5m bars, session nyam, both sides (judge both).
   - Main setting to try: limit at the edge, limit at the middle, and market.
   - Filters: "liquidity swept on the other side earlier today" on (this is the sweep step); "hourly trend with" on (the bias); "near a liquidity level" as a second variant.
   - Target: 2 x stop. Fits exactly.
   - Stop to try: 10, 20, 30 NQ points and 1.5 x ATR.
   - Cannot do: stop below FVG candle 2; "the sweep must be of a 1h swing low and the 1h candle must close back"; the second-chance FVG as a re-entry rule (unless the card allows two trades).
5. Which low: filter "near a liquidity level" at entry time is the nearest. No "level price is at when the session opens" setting.
6. Bias from yesterday: filter "hourly trend with". No "yesterday was a strong up day" filter. Missing.
7. Target must exist: nothing fits. No filter for "untouched high above".
8. Example 1: as 4. His real management (stop to a swing point, trailing, 50% off) cannot be done.
9. Example 2: as 4. The trade needs a hold past 15:58 to win. The pipeline would close it flat at 15:58.
10. Re-entry at 18:00: cannot do. No overnight holds.
11. Not a rule.

## 4. CLAIMED RESULTS
- [0:00] [2:02] A 2.5 million dollar prop payout at Apex in under 90 days, called a world record, "using this strategy". No proof in the words.
- [0:00] 14 years trading, hundreds of strategies tested. [10:05] says he struggled for 10 years first.
- [6:03] Example 1 (2026-02-09): 2R target hit; chat messages shown as proof he took it.
- [8:04] Example 2 (2026-01-27): 2R target hit about 9 hours later, after the evening re-open.
- [6:03] Claim that any SFP with the right context "should pan out". No count, no win rate, no losing example.

## 5. RISK AND SIZING RULES
- Stop below candle 2 of the 5m FVG for longs (above for shorts) [5:02].
- Fixed target of 2R [5:02] [8:04].
- No raid, no trade [5:02]. Trade only at session time, not pre-market [2:02].
- His own management: tighten the stop to the last swing point, trail after an FVG holds, take 50% off, then close [6:03].
- Prop accounts: flat by the firm's cut-off; optional re-entry at the re-open [8:04].
- No size, no dollar risk, no daily loss limit, no max trades given.

## 6. LOOK AT SCREEN
- [1:02] which 1h swing lows are marked on 2026-02-09, and one extra "hourly swing point here".
- [2:02] to [3:02] the pre-open SFP he skips and the 10:00 candle he takes.
- [5:02] the 5m chart: the 09:30 SFP, the FVG box, entry, stop under candle 2, the 2R target.
- [6:03] the chat log with times (09:55, the stop at 25,091, the trim near 10:55).
- [6:03] to [8:04] the 2026-01-27 chart: two swing lows, the 10:00 SFP, the 5m FVG and a second FVG.
- [8:04] to [9:05] the 16:00 to 18:00 gap and the 19:10 target hit.

## 7. RED FLAGS
- Apex affiliate code (80% off) in the middle of the video [2:02]; paid mentorship pitch at the end [10:05].
- Two hand-picked winning examples. One of them wins only after the session he says he trades.
- His real trade in example 1 went in before the 1h candle closed and was managed with trailing and partials: not the rules he teaches.
- Bias ("bullish on this day", "Monday was strong") is asserted, not defined.
- The 2.5 million dollar record is used as proof, but no trade list or statistics are given.
- "Works on any asset and any timeframe" with no test.
- Swing points are picked by eye; no definition in this video.

## 8. VERDICT
- The only one of the four with a fixed entry, stop and target (5m FVG, stop under candle 2, 2R) and a fixed clock (09:30 to about 10:30): the best fit for the pipeline, as `fvg` with the swept-liquidity filter.
- Same core as the other three (bias, sweep, SFP). The August video (tFKOaF4HMcg) drops the FVG step and enters on the SFP close.
