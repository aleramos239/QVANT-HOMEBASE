# Video notes: l6iq0ljhxIo - JJ Simon week 13 recap (fair price, all sessions)
Title: "How I Made Money Trading Prop Firms On A Bad Week (Week 13)" | https://www.youtube.com/watch?v=l6iq0ljhxIo | 31:10 | captions read in full + chart frames
Same trader and same fair-price rule as BLvsYJ4sqn8 (read that first). Week of Sun Sep 13 -> Fri Sep 18 2026, NQ 1m, TradingView. Losing week for the rule; FOMC and Thursday saved it.

## New rules (not in BLvsYJ4sqn8)
Sizing / entries
- Continuation size from the opening candle BODY: body < 25 pts -> stop 25 / target 38. Body > 25 (e.g. 29) -> stop 50 / target 76.
- Weak opening candle (wicks both ways, barely breaks, "unbiased") -> take the continuation on the 2nd candle.
- Stop is a fixed number of points (12.5, 25, 50 as the account needs), never at a swing or a candle.
- Funded: enter at candle close. Evals: mid-candle is fine.
Definitions
- Swing high = a candle whose high is above the candle on each side (3-bar). Swing low the same, mirrored. Break of structure = a close past it.
- Displacement must be the opposite color ("a green displacing a red"): body bigger than that red's body AND close above its wick. Check zoomed in: a close that only touches the wick is NOT displacement.
- Two or three candles together can count as displacement / break, but that is weak; he says don't take the 3-candle one.
- Only skip the displacement rule when price is so close to fair that waiting leaves too few points (his eval, needing 26: entered before the close). Not part of the rule.
Layering
- Continuation: "keep shorting until the original unfair move is done", one per candle.
- Reversion: add on every new displacement / break while the first trade is in profit. Never add in drawdown. Don't add at the same level as the first entry.
- Evals: the next one goes in once the previous is halfway to target.
Sessions
- 09:30 open is fair for New York, same pair (continuation + reversions). After 11:00: only with the trend, or stop.
- 14:00 session: he trades it only if accounts are left. Trade with the bias; continuation on the 2nd candle is fine.
- News (08:30, FOMC 14:00): fair = the pre-news price (where price was just before the release). Continuation of news only on a huge candle. Reversions to the pre-news price are "the strongest". Use a 5s / 15s chart to catch the end of the news move (optional).
- Huge Sunday gap: the higher-time-frame bias = fill the gap; a continuation toward the gap is fine.
Fair price
- After a move away + break of structure, re-draw fair at the new consolidation (top / middle / bottom). His own mistake on Monday: kept shorting back to the open 4 times.
- The 18:00 open is fair "~98% of the time". After FOMC (Wed) 18:00 opened 207 pts below the pre-FOMC price: not enough volume in 17:00-18:00 to gap that far, so it opened unfairly. He kept trading back toward the pre-FOMC price, not to 18:00.
- He may trade back to the previous session's fair price when a strong break of structure + gap + bias line up (Monday 09:30). He says it is discretionary.
- Pre-open trades are OK but you must handle the open. He holds through the open when confident (he says you can check the order-book imbalance).
Other
- ~15% of days don't revert (Friday). Sessions before FOMC can be dead (Tue night: never 20 pts away).
- Money: judge by payouts vs eval spend and the expected value of funded accounts, not P&L; cap a bad day near -$10k vs +$20k winning days.

## Every example
| Session | What happened |
|---|---|
| Sun Sep 13 18:00 | ~300-pt gap above, green candle. Continuation long OK (toward gap), 76/50 -> L. Reversion shorts to 18:00: tiny displacement, displacement + break, adds, big break -> W. |
| Sun 20:00 | Green -> continuation long 38 (exit / flip the short). Asia moved away -> Asia fair. Reversion (first displacement, 30 pts) W. Overnight 250-pt gap-fill long on a funded L. |
| Mon Sep 14 09:30 | Red candle -> continuation short 25/38 (body < 25). Bias long (18:00 + Asia opens above, gap above). Failed to go short + strong break long -> long back toward 18:00. 2 shorts at the Asia-open wick L. Fair re-drawn to the consolidation; break-of-structure trade back to it. |
| Mon 14:00 | Bias short; green candle rejecting longs -> continuation short on the 2nd candle. Roll day, no gap. |
| Mon 18:00 | Continuation short -> breakeven (no unfair move). 18:00 fair. |
| Mon 20:00 | Small green, breaks structure -> long back to 18:00, stopped by a hair. Re-entry: displacement right after, 40 pts -> W. Reversion to Asia too close. |
| Tue Sep 15 09:30 | Weak first candle -> continuation short on the 2nd candle. Reversions: none valid (no close above the wick), then displacement entry L; weak 3-candle one (he took it, says don't); first displacement + break (wick taller than both neighbors) L; one more L. After 11 wait for trend. ~7 trades. |
| Tue 18:00 / 20:00 | Never 20 pts from the open -> 0 trades. |
| Wed Sep 16 08:30 news | Pre-news line. No continuation (candle not huge). Should have reverted twice to pre-news (didn't). |
| Wed 09:30 | Huge green toward pre-news, body 29 -> 76/50; he went breakeven (no unfair move). Thought the open fair, short L. Volume took it back to pre-news -> pre-news fair. Reversions to pre-news: 3 displacements + a break, fixed 12.5 / 25 stops. |
| Wed 14:00 FOMC | Wick rejects longs, closes short = continuation short, body 20 -> 25/38 W. Reversion on displacement (2 candles combined), 114-pt move: 3 funded ($7k, $10k live) + 8 evals. Next displacement L. +$20k day. |
| Wed 18:00 | 18:00 opened unfairly 207 pts under pre-FOMC: kept trading long toward pre-FOMC, funded +$8k. 20:00 continuation long L; fair dragged down to the Asia consolidation. |
| Thu Sep 17 | Fair = Asia consolidation. Pre-open spike up -> short on a break before 09:30, held through the open (+$14.2k live). Open candle body 0.5 -> 25/38; huge 2nd candle -> short every candle until the move ended. Then longs back to the open on displacements / breaks (+$10k). |
| Fri Sep 18 | No reversion (one of the 15%). Continuations after an unbiased open; a weaker one after a break: don't (unfair move never came). Reversion longs to the open: displacement, break, adds; all L. Thought yesterday's 09:30 = 18:00 price was fair, stopped buying, then it rallied. |
