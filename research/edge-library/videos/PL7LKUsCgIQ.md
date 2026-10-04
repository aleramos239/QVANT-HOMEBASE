# Robbins Cup winner: value-trend pullback with footprint trigger
1. Channel: IQCapital. URL: https://youtu.be/PL7LKUsCgIQ (58 min). Guest: Chris Creamer (captions; spelling unsure), age 26, July micro-futures Robbins World Cup winner (claimed +100%).
Gist: mostly discretionary trend-pullback. Higher-timeframe value trend picks the side, a "discount" zone picks the place, a failed second push on 5-min footprint candles picks the moment. About half the talk is psychology. Timestamps are +/- 1 min.

## 2. THE STRATEGY, STEP BY STEP
Reason: when one side pushes hard at an edge and price does not move, those traders are trapped; to get out they trade the other way, which speeds the move. In negative-gamma days dealer hedging adds to it [06:04-08:07, 21:17].
Market/time: MNQ (he reads MNQ flow, not NQ) [37:28]. Charts 1h, 15m, 5m, sometimes 1m. Only the first ~90 min after the NY open ("hour and a half", no exact clock) [05:04, 38:28]. 0-2 trades a day.
Step 1 context, set before the open: 1h/4h structure, is value area rising (higher highs/lows, each day's value higher), falling, or flat [08:07-09:07]. VAGUE: how many sessions, how value is measured, what he does on flat days.
Also naive GEX from QQQ/NDX options: positive gamma = dampened, failed breakouts; negative = bigger, faster moves; marks call wall, put wall, gamma flip [09:07-15:12]. Used as a day-type read only. VAGUE: no rule changes by regime.
Step 2 location: trade with the trend only. Long only in "discount" = below the prior profile's value area low; short in "premium" above it [14:11-17:15] (short side is implied, never drawn).
Zone = fib of swing low to swing high, levels 0.705 / 0.788 / 0.886; zone must sit outside value area; price must first form a swing point or sweep; trading beyond 0.886 = no trade [25:19-27:21]. Likes areas crossed fast (low-volume node) [16:14].
Step 3 trigger on 5-min footprint candles (bid x ask volume, delta at each price):
 a) absorption: long wick into discount, most volume (POC) and negative delta sitting at the wick extreme, bar closes back up [18:16-19:16]. He says absorption alone is not a reversal signal [28:22].
 b) next bar: sellers push down again, fail at a higher low, buyers flip it up with ask-side imbalances of 400%+ (indicator bolds them) [20:16-22:17, 29:23-30:24]. He waits for this second failure, then enters long [30:24].
 VAGUE: exact entry price/bar (flip-bar close? break of prior high?), how many imbalance cells count, whether delta must turn positive, how far the second push may go.
Stop: just past the extreme sellers failed at [22:17]. VAGUE: low of first bar or of second failure; buffer not given.
Target: next swing high (sometimes POC or call wall); clustered orders on the book at round numbers/swings seen as magnets [22:17, 33:24]. Realised typically 1.5-2R [32:25]; examples drawn 1.5R up to maybe 6R.
Management: first want buyers back inside value area; if they stall below it, go break-even or cut [22:17-23:18]. Then trail behind aggression while footprint shows effort making progress [24:18]. VAGUE: trail distance.
Filters: 5-min MNQ volume must stay above 20,000 contracts, else lunch-type grind, no trade [37:28]. Skips when news is close [43:31, vague]. Hard stop time ~90 min after open; done for the day after 2 losses in a row [46:34-48:34].

## 3. CLAIMED RESULTS
+100% in July in the micro championship [00:00, 04:00]. Start capital, drawdown, trade count not given.
Win rate 60-65%, profit factor about 1.8, 1.5-2R typical, "floats" and "fluctuates" [32:25]. 0-2 trades/day.
Evidence: none shown (no equity curve, trade list or statement), whiteboard drawings only.
Arithmetic check: 60-65% wins at 1.5R implies PF about 2.25-2.8, not 1.8, so average win is below 1.5R or losers/scratches are bigger than 1R. Unexplained.

## 4. DATA NEEDED
- Direction/context (value rising or falling, prior value area low/POC): volume-at-price per session from our tick or 1-min data. We have it.
- Swings, fib zone, Asia/London range, prior-day levels: price bars only.
- Absorption (volume and delta at the wick of a 5-min bar): buy/sell volume per price inside the bar (footprint). Rebuild from ticks if aggressor side is stored; confirm in ofb_tick. Bar-level delta alone is a weaker proxy.
- 400% imbalance: ask vs bid volume at adjacent price levels, same footprint.
- Volume filter: 20,000 is MNQ. NQ volume is lower; use a percentile of the session's own 5-min volume instead.
- GEX: needs QQQ/NDX options open interest. We do not have it. Skip, or replace with a realised-volatility regime.
- Order book: only for the "clustered orders as targets" idea; our 2.25 pts is too shallow. Not needed.

## 5. RISK + SIZING
No contracts or risk per trade stated. Says he is "extremely aggressive" in evals [36:28]. Argues a 50K account with $2,000 drawdown and $3,000 target equals 1.5R, so 1.5R trades suffice [33:26]. This mixes account target/drawdown with per-trade R; loose.
Loss limits are behavioural: 2 losses then stop, fixed cut-off time, 0-2 trades. Ends by ~11:00 ET, so flat by 4pm is automatic. Break-even moves and trailing help when open losses count. A stop beyond a wick extreme may be wide: size by stop distance.

## 6. TESTING-METHOD IDEAS
He gives no test method; only practice on replay (ATAS, DeepCharts) [39:28].
Add layers one at a time, keep a layer only if it wins out of sample: (1) price bars only: value-up day, pullback below prior VAL, second failed push; (2) add bar delta/absorption; (3) add 400% imbalance; (4) add volume filter. Matches our fewer-rules rule.
Compare with shuffled nulls: same days and window, random entry times, same stop/target.
Check whether the fib zone matters: 0.705-0.886 against other depths. If no difference, drop it.
Per year, then combined; count trades early, a 4-layer rule may give too few trades.

## 7. LOOK AT SCREEN
[18:16] footprint candle drawing: where POC and negative delta sit and what "all volume at the wick" means.
[20:16] absorption bar then second push: how far down it goes, which bar he enters on.
[22:17] stop and target lines: below first low or second low?
[23:18] management drawing: break-even point and value area re-entry line.
[25:19] fib drawing: which swing points, how the zone sits against value area.
[30:24] real footprint with bold 400% numbers: which cells compared, how many needed.

## 8. RED FLAGS
Discretionary by his own admission (edge cases, "not cookie-cutter") [35:27]. Results claimed, not shown; one contest month, high-variance format. Stats do not add up. Six stacked layers (structure, GEX, value area, fib, footprint, volume) with no test of any layer; fib levels are folklore. The order-flow part may add nothing over price (second failed push is a price pattern): untested. Naive GEX is a retail-platform guess. Sponsor ad for a $9 prop challenge at [31:24]. No short example.

## 9. VERDICT
Maybe. Worth testing a stripped, our-own version: long on a value-rising day, 09:30-11:00 ET, after price dips below prior value area low, enter on a failed second push (higher low) with positive delta on the flip bar; stop under first low; target prior swing high or 1.5R; skip if volume is low. Direction comes from the day's trend, flow only times it, which fits our finding. Skip GEX.
