# Y8gUPDVnDgw: If I Had to Make $500 by Tomorrow, I'd Use This Trading Strategy

## 1. SOURCE
- Title: "If I Had to Make $500 by Tomorrow, I'd Use This Trading Strategy"
- Channel: JadeCap. Length 7:07. Uploaded 2026-10-02. URL: https://youtu.be/Y8gUPDVnDgw
- Gist: three steps (pick the price target, wait for a failed break of a swing or an outside bar, enter on a 5 or 15 minute chart), shown on three trades from one week.
- Written from auto-captions. The market is never named. The "$500" of the title is never spoken.
- Words used below: SFP = swing failure pattern (price goes past an old swing high or low, then closes back). FVG = fair value gap. PDH / PDL = previous day's high / low.

## 2. EVERY IDEA AND STRATEGY
1. The three-step frame [0:00] [6:06]
   - Step 1: pick the "draw on liquidity" = the old high or low that price should reach next. He looks for liquidity (old highs and lows) or inefficiency (gaps).
   - Step 2: wait for an entry signal: an SFP or an outside bar.
   - Step 3: enter on an execution chart, 5m or 15m [3:02].
   - Market: VAGUE (not named). Time window: New York session, example at the 09:30 open [3:02]. Stop: beyond the SFP high or low [4:04]. Target: the draw [4:04]. Max trades a day: VAGUE.
2. SFP definition [2:01]
   - Bearish: an old swing high, price trades above it, then closes back below it. Bullish is the mirror.
   - For a bullish SFP he prefers the candle to close up (a bullish candle) [4:04].
   - Which swing counts: VAGUE (picked by eye; he says a second swing high would also do [3:02]).
3. Daily outside bar as the bias signal [0:00] to [1:01]
   - Outside bar = takes out the prior bar's high and its low.
   - Bearish case shown: the daily bar went above an old high and closed back inside the range. He leans bearish for the days after.
   - He says the two candles hide a change of structure that shows on a lower timeframe.
   - Exact close rule: VAGUE. Stop and target: none (bias only).
4. Sell only in "premium" and inside a higher-timeframe gap [1:01] to [2:01]
   - After the old high was taken, price fell to a gap, then came back up to about 50% of the outside bar.
   - On the 4h chart price is inside a bearish 4h FVG and in the upper half of the range (Fibonacci drawn from range high to range low).
   - Range anchors: VAGUE (by eye). Which gap: VAGUE.
5. Trade A: short at the 09:30 open [3:02] to [4:04]
   - Market: VAGUE. Bars: 5m. Time: New York session, at the 09:30 open.
   - Setup: bias bearish (idea 3). Target = the low inside the daily range (the draw). In the New York session price trades above the previous 4h candle's high into the bearish 4h FVG.
   - Trigger: a 5m SFP at the 09:30 open, with a 5m bearish outside bar beside it.
   - Entry price: VAGUE (he only points at the chart).
   - Stop: above the high that made the SFP. Target: the draw (the daily low). No reward to risk number given.
   - Filters: ideas 3 and 4. Max trades a day: VAGUE.
6. Outside bar as an entry signal on the 5m chart [3:02] [6:06]
   - Step 2 is said as "SFP or outside bar", so the outside bar is offered as a second trigger.
   - Rules for entering on it alone: VAGUE (only shown next to an SFP). Stop and target: VAGUE.
7. Trade B: swing long from a weekly level [4:04] to [5:04]
   - Market: VAGUE. Bars: 4h for entry, weekly for the idea. Held for days (not a day trade).
   - Setup: the previous week closed bullish. This week price dropped into a weekly level (a deep pullback). Target = the previous week's high.
   - Trigger: a 4h bullish SFP (took a low, closed back above, bullish candle).
   - Entry: buy when price trades back down inside the wick of that SFP candle.
   - Stop: just below the SFP low. Target: previous weekly high.
   - He notes price came very close to the stop and chopped for a long time; a bullish outside bar came later. "Could manage it": VAGUE.
8. Wick entry technique [5:04]
   - Enter inside the wick of the SFP candle (not at its close). Reason given: a real SFP low should not be taken again.
   - How deep into the wick: VAGUE.
9. Trade C: short after the previous weekly high and a previous quarterly high are taken [5:04] to [6:06]
   - Setup: the previous weekly high is taken. A new quarter has just started and price is above a previous quarterly high.
   - Trigger: an SFP at that high. Bar size: VAGUE. Price trades up into an FVG ahead of the open first.
   - Stop: above the SFP high. Target: the nearest previous daily low (he calls it the easy one).
   - Result: only "there we go"; shown, not said.
10. Weekly open gap plus SFP [2:01]
   - The week opened with a gap down, traded lower, then gave another SFP on the lower timeframe. Used as more proof of the bearish lean.
   - No entry, stop or target given: VAGUE.
11. "A couple of different execution methods" [3:02]
   - Promised for the end of the video. Never given. He sends viewers to a free masterclass instead [6:06].

## 3. NEAREST PIPELINE FIT
1. Frame: no single rule. See idea 5 for the testable form.
2. SFP: `sweep_rev` (prior-day or overnight high / low, close back inside) or `liq` in sweep mode (swing, equal, Asia, London levels). Session nyam. Both sides.
   - Cannot do: his hand-picked "old swing high". The pipeline uses its own fixed swing definition.
3. Daily outside bar bias: nothing fits. The only trend filters are hourly or 15-minute trend. No daily-bar pattern filter exists.
   - Stand-in: hourly trend "with" on.
4. Premium zone: filter "dear half of the latest swing range" for shorts, "cheap half" for longs. This exists.
   - Cannot do: a 4h FVG as a zone (fvg is an entry rule on 1m / 5m bars, not a filter). Cannot do: 50% of a daily outside bar.
5. Trade A: `sweep_rev`, 5m, nyam, both sides (judge both). Levels to try: prior-day high / low and overnight high / low. Second try: `liq` sweep with swing and London levels.
   - Filters: premium / discount on; hourly trend with on; displacement optional.
   - Stop to try: 20, 30, 45 NQ points or 1.5 x ATR. Target: 2 or 3 x stop, or none.
   - Cannot do: stop at the SFP wick, target at the daily low, the daily outside bar bias, the 4h FVG zone, "previous 4h candle high" as a level.
6. 5m outside bar entry: nothing fits. Nearest is `pinbar` at a key level, which is a different candle. Missing: an outside / engulfing bar entry rule.
7. Trade B: does not fit. Needs 4h bars, weekly levels and a hold over several days.
   - Loose intraday copy only: `liq` sweep of the 5-day low, long only, 5m. That is a different trade.
8. Wick entry: not on the list. No setting for a limit order inside the sweep candle's wick.
9. Trade C: `liq` sweep of the 5-day high (stand-in for the weekly high), short only, nyam, 5m.
   - Cannot do: quarterly high as a level, target at a previous daily low, the multi-day hold.
10. Weekly gap: nothing fits. `gap` is the 09:30 open against the prior close, every day, not the weekly open.
11. Nothing to fit.

## 4. CLAIMED RESULTS
- [0:00] "Profits like this, this and this": screen only, no numbers spoken.
- [0:00] 15 years of trading.
- [6:06] Personal record of 2.5 million dollars "using this exact system". No proof shown in the words.
- Three winning examples from one week, replayed after the fact. No win rate, no trade count, no losing trade.

## 5. RISK AND SIZING RULES
- Stop goes beyond the high or low that made the SFP [4:04] [5:04] [6:06].
- Target is a chart level (the draw), not a fixed multiple.
- No size, no dollar risk, no daily loss limit, no max trades given.

## 6. LOOK AT SCREEN
- [0:00] to [1:01] the daily outside bar and the old high it took.
- [1:01] to [2:01] the weekly gap, the 50% line of the outside bar, the draw (he draws an eye or a magnet).
- [2:01] the 4h bearish FVG and the Fibonacci range.
- [3:02] to [4:04] the 5m chart at 09:30: which swing high, where the short is placed.
- [4:04] to [5:04] the weekly level and the 4h SFP wick where he buys.
- [6:06] the quarterly chart and the last short.

## 7. RED FLAGS
- Sales funnel: free masterclass, "spots are limited" [6:06].
- Title promise ($500 by tomorrow) is never addressed.
- All three examples are hindsight replays from one week; all win.
- Swings, ranges and gaps are picked by eye. Bias comes from daily, weekly and quarterly charts read by hand.
- Two of three trades are multi-day holds on 4h bars: not day trades.
- The promised "execution methods" are held back for the paid funnel.

## 8. VERDICT
- Shortest and vaguest of the four. Only Trade A is a day trade, and it is the same SFP reversal as in TLEaD163obc and tFKOaF4HMcg.
- New here: the wick entry (idea 8) and the outside bar as a trigger (idea 6). Neither can be run in the pipeline today.
