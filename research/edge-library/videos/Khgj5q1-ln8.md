# Khgj5q1-ln8 - "My Signature Orderflow Model"
Channel: Fabervaale ENG | https://youtu.be/Khgj5q1-ln8 | 12 min | written from auto-captions (the indicator is heard as "deep effort" and "Nasdaq effort"; "IVB" = his first-30-minute breakout; "deep trades / deep charts" = the platform that sells it)
Gist: a closed indicator that draws boxes where little aggressive volume moved price a long way in one direction ("effort vs result"). He trades the first return to an untouched box, only in the direction of the day's bias. The formula is not given. Product demo.
## 2. THE IDEA
Reason [1:00-5:13]: volume = effort, price change = result. Much volume and no progress at a level = someone is absorbing, a turn is likely. Little volume and much progress, or equal buy and sell aggression where one side gets nowhere = the other side has stopped defending, so the next visit to that area should hold.
Who loses: the side that hit the market hard there and got no movement; they are stuck and must exit against themselves.
Rule as said [6:45-11:22], NQ, New York session:
1. Bias for the day from the volume profile ("profile framing") or from the first-30-minute range break. Take boxes on that side only.
2. The indicator prints a box (buy-side or sell-side). Overlapping boxes count as a stronger area.
3. Enter when price comes back to a box that has not been touched yet ("virgin"). If price leaves and never returns, no trade ("unfulfilled").
4. Stop on the far side of the box.
5. Target: he counts winners at 3 x risk; in practice half off earlier and a runner. A box of the opposite colour ahead = take profit there [5:43-6:14].
6. If price breaks the first-30-minute range against the bias, stop taking that side until a new confirmation. No trades late in the evening.
VAGUE: the box formula (volume measure, price move, lookback, bar size), box height, entry at the near edge or the middle, how long a box stays valid, cut-off time, how the profile bias is set.
## 3. CLAIMED RESULTS
One week of NQ examples, counted by hand on screen [8:16-9:18]: +3R, -1R, -1R, +3R = +4R on the first day, with at least three boxes that never filled; the next day one filled trade at about 1:3; a third day one stop and several misses. "Extensive quantitative validation" is said at [0:00], not shown. No trade list, costs, win rate or sample size.
## 4. DATA NEEDED
Aggressor-side volume per bar (or per price inside the bar) and price bars. We have bar delta, sweep and big-order volume for NQ / ES / GC. The exact indicator cannot be rebuilt from the audio.
## 5. FITS THE TESTER
NO as said (hidden formula, stop at the box edge instead of the standard table).
Nearest thing on our list, PARTLY: `fvg` (a three-bar gap is a zone left by a fast one-way move; mode touch or mid = a limit on the first return; new_gap stop = keep the first zone) on NQ 1- or 5-minute bars, nyam, with `delta with` or `cumdelta with` as the flow filter and `htf60 with` or `vwap with` as the day-bias filter; target column 3 x stop is in the standard table. This is close to fvg_delta_nq, which failed round 1 on 2026-10-06, and the fvg_regime_* ideas already on file.
A small new entry rule that would test his actual claim: "easy-move zone" = a bar whose range per unit of volume is in the top 10% of the last 100 bars, closes in the outer quarter of its range, with net aggressive volume on the same side; the zone is that bar's body; first return to the zone's near edge = limit entry in the bar's direction, once per zone. Day bias from `htf60 with` or the side of the 09:30-10:00 range. Exits from the standard table.
## 6. REPEATS FROM THE 2026-10-03 BATCH
- "Effort without result = absorption, then the trapped side pays" = the reason behind idea 2 there (PL7LKUsCgIQ, failed second push).
- "Bias first, flow only times the entry" = the same note and our own Level 2 finding.
- The 09:30-10:00 breakout as the bias = idea 3 there (yW6c0K8uGvw) and StaphlRH8NQ in this batch.
## 7. LOOK AT SCREEN
- [3:09]-[4:41] effort / result drawings: what counts as "same effort, one side absorbed".
- [6:45]-[9:18] the first two example days: box height against the stop, where exactly he counts the entry, how many boxes print per session, how many never fill.
- [9:49]-[10:51] the losing day and the range break that switches the bias off.
- [10:51]-[11:22] boxes he did not trade (out of hours, against bias): shows how many boxes exist in total.
## 8. RED FLAGS
Closed indicator sold on his platform; he is on the platform's research team. Winners counted at 3R by hand, misses not counted, shorts skipped in hindsight "because the bias was long". The bias rule is discretionary. One week, one market.
## 9. VERDICT
SKIP as said. The reason is sound enough to earn one test of our own version later ("easy-move zone", first return), but it needs a new entry rule, and the nearest existing one (fvg + delta) has already failed a round.
