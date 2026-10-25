# Video notes: BLvsYJ4sqn8 - NQ evening "fair price" (18:00 and 20:00 sessions)
Title: "The ONE Setup That Made Me $400,000 in 90 Days (6 & 8PM Session, Step by Step)" | https://www.youtube.com/watch?v=BLvsYJ4sqn8 | 30:34 | captions: auto, read in full
Same trader as UVKVSWKFlvo. Claim: $400,000 of payouts in 90 days. Evidence: one month replayed by eye, he says it is too small and his real win rate is lower.
## Rule (NQ, 1-minute chart, 18:00 to 21:30 ET)
Fair price = the 18:00 open (the market is shut 17:00-18:00).
- 18:00: ONE trade with the opening candle, in the first 5 minutes (green buy, red sell). Skip it if it runs away from an unfilled gap or against the morning's direction.
  Then fade back to the 18:00 price when price is 30+ points away and a strong candle (body bigger than the last body, closes past its wick; better, a break of structure) points back.
- 20:00 (Asia open): same pair. If the 20:00 move goes toward 18:00, 18:00 stays fair ("best setup"); if it goes away, the 20:00 open becomes fair.
- 25 stop / 38 target, 1 to 1.5. Opening move not coming: breakeven. Flat before 20:00. Last fade 21:30 (then only with the trend).
- 15% of days never come back; some weeks do not move at all.
## Where it sits in the library (2026-10-10)
- Session `eve` exists. Continuation = `first_bar_mom` / `orb` on eve (`nq_orb_eve` stopped at stage 1: 10 of 144 boxes at $70).
- Fade to the 18:00 price: no entry rule for it (open_fade is nyam only); nearest is `vwap_z` / `vwap_band` on eve, whose VWAP starts at 18:00.
- NOT in the exit table: target = the fair price; the fair-price switch at 20:00.

## Full re-watch 2026-10-19 (transcript + chart frames, every example)
Chart: NQ1! 1-minute, FX Replay (Aug 18 -> Sep 1 2026), then TradingView (Sep 7 -> 15 2026). Size: 1 NQ ($20/pt): stop 25 pts = $500, target 38 pts = $750 (read off the order labels).

### Rules as taught
1. Fair price = the 18:00 open (market shut 17:00-18:00). Draw a line there.
2. 18:00 continuation: ONE trade with the 1m opening candle (green buy, red sell), market, ASAP. Only inside the first 5 min ("if it doesn't happen within 5 minutes it's not happening").
   Skip it when: (a) it trades AWAY from an unfilled gap (gap = 18:00 open vs the 16:59 close), (b) it goes against the higher-time-frame bias = where that morning's 09:30 open is (above = long bias), (c) wick rejects that side / fails to break structure = weaker. Too many things against = no trade.
   If the unfair move "is clearly not happening" -> stop to breakeven (by eye, no fixed rule).
3. Reversion: after price moves away from fair price, enter back toward it on
   - displacement: candle body > previous candle body AND close beyond the previous candle's wick (long: close > prev high), or
   - break of structure (close past the last swing). When structure is nearby, WAIT for the break -- displacement alone is "weak". Never buy one green candle in a downtrend.
   - Distance: entry must be >= 30 pts from fair price, else "too close", skip.
   - Target is FIXED 38 pts, not the fair-price line ("static performs better for prop rules"). Stop 25.
   - Re-entries allowed: he takes 2nd and 3rd attempts after a loss.
4. 20:00 (Asia open): an 18:00 trade still open -> exit at breakeven/market just before 20:00. Then same pair: ONE continuation with the 20:00 opening candle + reversions.
5. Fair-price switch at 20:00: the first 20:00 move goes TOWARD 18:00 -> 18:00 stays fair. Goes AWAY -> the 20:00 open becomes fair, revert to it instead.
   He also re-draws fair price by eye (a consolidation, a failed move) when the market clearly ignores it.
6. Best setup ("A+"): 20:00 continuation pointing back to the 18:00 open = continuation + reversion together. He sizes up / adds on these.
7. Stop new trades at 21:30. After 21:30 only with the trend (break of structure, not displacement).
8. Expect ~15% of days with no reversion; some weeks (first week of Sept) never move 20 pts -- nothing to trade.
9. News between 18:00 and 20:00 changes fair price (ignored in the replay).

### Every example (C = continuation, R = reversion, BE = breakeven, W/L)
| Day | 18:00 | 20:00 | Fair after 20:00 |
|---|---|---|---|
| Tue Aug 18 | no C (gap + green candle + 09:30 above); R long W; R long (30.75 pts) exited at 20:00 -$280 | C short W (red, broke structure 3x); R long L; R long W; R short L; R short W | 20:00 (moved away) |
| Wed Aug 19 | C long W (green, no gap); R short on BOS L; fair re-drawn to consolidation | C short L (barely); R long on weak BOS W (two too close skipped) | 20:00 |
| Thu Aug 20 | C short W (red, wick, small gap below); R long W | C long W (toward 18:00); reversions all too close | 18:00 |
| Sun Aug 23 | C short W; R long (weak BOS) W | C short A+ (huge red back to 18:00) W; R long L | 18:00 |
| Mon Aug 24 | weak C long L (green, gap filled, 09:30 bias long); R short L; demo long kept through 20:00 = mistake | should have BE'd and taken C short (W); R long W | 20:00 |
| Tue Aug 25 | C long -> BE; R entry -> BE at 20:00 | C short L; R long to 18:00 L; one-way day, no reversion | -- |
| Wed Aug 26 | big gap up: no C long; short on structure break (fill gap) | huge red: short to 18:00 W, added 2 more W; gap filled -> R long to 18:00 W x2 | 18:00 |
| Thu Aug 27 | C short -> BE; R: 26 pts = too close | 19:59 long (C of Asia + R to 18:00) W | 18:00 |
| Fri Aug 28 | C short L (barely); R L | 20:00 green; trend switch -> R long A+ W | unclear |
| Aug 30 / 31 (no volume) | C short -> BE x2 | C short L; then nothing within 20 pts | -- |
| Mon Sep 7 | C optional (wicks both ways); R L, R W | red but no move -> 18:00 fair; late R W | 18:00 |
| Tue Sep 8 | C short L; rest too close | -- | -- |
| Wed Sep 9 | C short missed by 0.5 -> BE | red wicked 18:00 (14 pts, too close); R L, R L, R W | 18:00 |
| Thu Sep 10 | C long -> BE; R long L; re-entry | huge green = C + R to 18:00 A+ W | 18:00 |
| Sun Sep 13 | big gap: no C; R to 18:00 W x2 | C long W; R (31 pts) to 20:00 W | 20:00 |
| Mon Sep 14 (roll, no gap) | C short -> BE | R long L (no volume); re-entry W | -- |
| Tue Sep 15 | no trade: never > 20 pts from open | -- | -- |
He says himself: one month is no sample, real win rate is lower at 1.5R, "slightly winning".

## Rulebook in plain words (2026-10-19)
Setup: NQ 1m, 18:00-21:30 ET. Stop 25, target 38 ($500 / $750 on 1 NQ). Two trade types: continuation (with the open), reversion (back to fair price).
Idea: market shut 17:00-18:00, so the 18:00 open is fair. Price far from fair comes back. Open volume pushes price toward the true fair price.

18:00
- Line at the 18:00 open = fair price.
- ONE continuation with the first 1m candle (green buy, red sell), at once, only in the first 5 min.
- Skip it if: it goes away from an unfilled gap (16:59 close vs 18:00 open); against the morning bias (09:30 open above = only buy, below = only sell); a wick rejects that side; the candle fails to break the last swing. Too many against = no trade.
- Move not coming = stop to breakeven (by eye).

Reversions
- Price must be 30+ pts from the fair line, else skip ("too close").
- Signal back toward the line: displacement (body > previous body AND close past the previous wick) or break of structure (close past the last swing).
- Swing nearby = wait for the break. Never buy one green candle in a downtrend (or sell one red in an uptrend).
- Target fixed 38, not the line. 2nd / 3rd try allowed after a loss. Small accounts may take "too close" trades for 10-16 pts.

Before 20:00: an 18:00 trade still open = get out (breakeven or market).

20:00 (Asia)
- ONE continuation with the first 8 PM candle.
- Fair price: first move TOWARD 18:00 = 18:00 stays; NO move = 18:00 stays; AWAY + breaks structure = 20:00 open becomes fair (drop the 18:00 line); sits on the open = unclear, skip.
- Then reversions to the fair line, same rules.
- A+ trade: 20:00 candle pointing back to the 18:00 line (continuation + reversion). Size up, add.

Stop: no new trades after 21:30; after that only with the trend, break of structure only.
Moving the line by hand: price ignores it (runs hard the wrong way) -> move it, e.g. to a consolidation. If the 18:00 open keeps running, true fair may be elsewhere -> bias matters most. News 18:00-20:00 changes fair price.
Expect: ~15% of days never come back; some weeks never move 20 pts = no trades. Sundays same. Roll day = no gap. His words: one month proves nothing, real win rate lower, "slightly winning".
Risk: 25/38 is video only; size per account and firm. Eval 50% consistency rule caps a win near $1.5k.
