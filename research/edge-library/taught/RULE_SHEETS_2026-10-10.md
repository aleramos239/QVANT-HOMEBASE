# Rule sheets: what each video teaches, side by side with what the engine would run

Written 2026-10-10 for the owner to CHECK BEFORE ANYTHING RUNS. Nothing here has been run as taught. Every sheet has three parts:
**Taught** (the video's own rule, with time marks), **Would run** (the engine's version, exact numbers), **Not the video** (every difference).
A sheet that cannot be run honestly says so and names the missing piece. If a line of "Taught" is wrong, tell me the number and the sheet changes.

The earlier tests of these videos used the pipeline's fixed table of stops and targets and a 144-box map. These sheets replace that.

---

## 1. Matteo Conti, "Drift VWAP pullback" (video `wm4A6qo0g3I`, IQCapital interview, 44 min)

**Taught** (notes `videos/wm4A6qo0g3I.md` section 2)
- NQ. Trend read on 15-minute bars; entry by market order at the next bar's open. VWAP anchored at the 09:30 ET cash open.
- LONG trend = all three true: close above VWAP; VWAP higher than 15 minutes ago; price up at least 0.1 % over the last hour (4 bars of 15 minutes). SHORT = the mirror.
- No trades 09:30-10:30; no new trades after 15:30; flat everything at 15:55.
- Trigger: long = the first red candle once the trend is true; short = the first green candle.
- Exits: LONG stop 80 points, target 40 points. SHORT stop 80 points, target 50 points.
- One position at a time; at most 4 trades a day; stop for the day after 2 losses.
- Said to be tuned in sample: the 0.1 % and the 4-trade cap.

**Would run**: family `vwap_trend_pull`, `x` 0.1, `max_loss` 2, bars 5 and 15 (he loads both; which is the trigger is unclear), sessions nyam / mid / pm.
Two sheets, because the targets differ: long only, stop 80 / target 40 (target = 0.5 x stop); short only, stop 80 / target 50 (0.625 x stop). `max_tr` 4. Flat at 15:58 (the engine's flat time).

**Not the video**
- Caps are counted per SESSION pass (nyam, mid, pm are separate instances): up to 4 trades and 2 losses in EACH session, not per day. The helper reports whether one pass can cover 10:30-15:30.
- Flat time 15:58, not 15:55.
- His result was "about 65 % wins, avg win $866, avg loss $1,300" on the video's own sample; ours is a re-test, not a copy.
- The bar the trigger candle is read on is not stated in the video; both 5 and 15 are run and shown.

**Can it run now?** Yes, with exact exits. (This is the closest of all to what was tested before, and it was still tested on the standard table's nearest stops, not 80 / 40.)

---

## 2. JJ Simon, "My $1,300,000 strategy" (video `UVKVSWKFlvo`, 10 min)

**Taught**
- NQ, New York morning. "Fair price" = the last price before the 09:30 open (the pre-open price).
- TRADE 1, continuation [1:00-2:30]: in the first 10-15 minutes go with the opening burst: the second 1-minute candle clearly breaks the pre-open candles and closes beyond all of them -> enter in that direction. Stop 25 points, target 38 points. If that candle is more than 25 points: half size, stop 50, target 76.
- TRADE 2, reversion [2:30-3:30, 5:40-7:40]: after the burst, the first 1-minute break of structure back toward the pre-open price (a candle that breaks the last swing with no wick on its far side) -> enter toward the pre-open price. Stop 25, target 38 ("always 25 and 38"). After a loss, take the next break of structure.
- Done at 11:00. On a red-news morning (08:30) use the pre-NEWS price; move to breakeven before 09:30.

**Would run (two sheets)**
- Continuation: NO ENGINE RULE. `first_bar_mom` trades the FIRST bar of the session when its range is at least k x ATR, at its close; his entry is the break of the second candle beyond the pre-open candles. Needs a new small rule: "the first 1-minute bar after 09:30 whose close is beyond the high (low) of every 1-minute bar from 09:25 to 09:30" (needs his definition of "pre-open candles": how many minutes before 09:30).
- Reversion: `open_fade` (reference = the 09:29 close; once price is at least k x ATR30 away and a bar closes back toward the reference beyond the prior bar's opposite extreme -> market toward it; 09:30-11:00; max 3 trades). k is the "size of the unfair move": he gives none. Would run k at the smallest the family takes (0.05) and 0.25, bar 1, session nyam, stop 25 / target 38, max_tr 3.

**Not the video**
- Continuation: the half-size / 50-76 rule on candles over 25 points is not expressible (one stop for the cell). The sheet would run 25 / 38 only and list the over-25 days separately.
- Reversion: his "break of structure" has no ATR threshold; `open_fade` does (k). His re-entry after a loss is `max_tr` 3. News-day and holiday rules are not run.
- Targets as taught are fixed points (38), not "back to the pre-open price" (he says the price is often 100+ points away; the target is 38).

**Can it run now?** Reversion: yes, with the caveats (k). Continuation: after one small rule is built.

---

## 3. Trader Drysdale, "VWAP wave: fade the value area extremes" (video `Z2uJRbkb2pA`, 16 min)

**Taught**
- ES / NQ micros. Session VWAP with a one-standard-deviation band ("the value area").
- ONLY on a range day: price is INSIDE the bands and rotating. A trend day (price outside the bands, accepted) = no trade.
- Setup [4:00-5:40]: price touches the upper (lower) band and REJECTS: a long wick, a close back inside. Enter against the touch. Stop a few points beyond the wick (8 points on ES in his example). Target the VWAP (10-16 ES points): 1 : 1 to 2 : 1.
- Rules [6:40-10:30]: no trades in the first 15 minutes; stop after two losses in a row; one setup a day while learning; no trades 30 minutes around big news; a trade that has not reached the VWAP in 60 minutes is closed.

**Would run**: NO ENGINE RULE FOR IT. `vwap_band` takes a close back inside the band after a close outside (the band 1.0 version was queued on 2026-10-09); `vwap_z` takes any bar beyond z sigma. Neither has: the range-day condition, the wick, the structure stop (wick end), the target at the VWAP.

**Not the video** (if run with `vwap_band` 1.0 anyway)
- Range-day condition: absent (trades every day, the trend days that lose).
- Trigger: a close back inside, not a rejection wick.
- Stop: a fixed distance (not the wick end). Target: a multiple of the stop (not the VWAP). Time stop: expressible (`exit_bars` 60 minutes), the rest is not.

**Can it run now?** No. Needs: (a) a rule that fades a rejection wick at a +/- 1 band when price has been inside the bands for the session so far; (b) a target at the VWAP (the engine's exits are multiples of the stop; a level target needs a new exit kind: owner's word).

---

## 4. Vince (Apex), Titans Of Tomorrow interview (video `Yg7bTCdoLCQ`, 66 min)

**Taught**
- NQ (and ES). Two plays a day: the first-hour range ("IB") and yesterday's value area.
- IB play [11:30-12:10, 29:30-30:40]: high and low of the first hour (09:30-10:30). The FIRST return to either edge is faded with a resting LIMIT order. Stop 50 ticks (= 12.5 points on NQ). "A 10-point wick is a great trade." Target at first a fixed 50 ticks (1 : 1); now he trails through his levels.
- Value area play [10:00-11:30]: yesterday's value area (70 % of the volume). The day OPENS outside it, price moves into it, a 5-minute candle sits (is "established") inside -> trade to the other side of the value area ("80 % rule", Dalton). Open inside the value area = no trade. Stop 50 ticks.
- Day rules [38:00-40:00, 56:00-58:00]: three trades a day win or lose; $1,000 down an account and he is done; no afternoon trades (96 % of his afternoon trades lost).
- His own numbers (90 % and 80 %) are quoted rules of thumb; he has never backtested anything.

**Would run (two sheets)**
- IB first touch: family `ib_touch` (built 2026-10-10), `ib_min` 60, bar 5 (he enters on 5-minute bars), sessions nyam and mid, stop 12.5 points, target 12.5 points (1 : 1), `max_tr` 2 (the family's maximum: one per edge).
- Value area: family `va_reclaim` (price trades below yesterday's value-area low by d x ATR, then a bar closes back above it; mirror at the high), `d_atr` 0 (smallest), stop 12.5 points, target = 2 x the stop (25 points) as the nearest fixed target to "the far side".

**Not the video**
- IB: `max_tr` is 2 (he takes 3); the afternoon is cut only at the session end of `mid` (13:30), not at noon; the tick-through fill rule (a limit fills one tick through, a touch to the tick does not fill); his target after the early days is a trail, not 1 : 1.
- Value area: his entry requires an OPEN outside the value area and a candle INSIDE it; `va_reclaim` requires a trade beyond the edge by `d_atr` x ATR and a close back. His target is the far side of the value area, not a fixed number.

**Can it run now?** IB: yes. Value area: only roughly; the exact rule needs "open outside the value area, first 5-minute close inside, target the far edge" (a level target: owner's word).

---

## 5. Casper, "The Best FVG Trading Strategy" (video `WEhmadJArQo`, 10 min)

**Taught**
- Mark the high and low of the first candle after 09:30.
- DAY TRADE [5:00-7:50]: first 15-minute candle (09:30-09:45). On the 5-minute chart a fair value gap forms through it. LIMIT order at the gap. Stop at the first candle of the gap's three-candle pattern. Target a fixed 2 : 1.
- SCALP [1:00-4:40]: first 5-minute candle (09:30-09:35). On the 1-minute chart a gap forms through it. Wait for price to come back into the gap AND for that candle to be engulfed, then enter. Stop one tick beyond the lowest point traded in the gap. Target 3 : 1.
- His one-month test: scalp 70 % wins and $10,950; day trade 81 % wins over 16 trades and $15,400. (16 trades: not evidence.)

**Would run**
- DAY TRADE: family `open_fvg` (built 2026-10-10), `oc_min` 15, bar 5, session nyam, `min_gap` 0.1, structure stop (bar 1's far extreme), target 2 x the stop, `max_tr` 1.
- SCALP: not run. Needs the engulfing-retest step.

**Not the video**
- The limit may fill much later than the gap (it rests until five minutes before the session ends; he sits and waits too, but states "35 minutes").
- "First candle of the gap pattern" = bar 1 of the three bars: the family passes bar 1's far extreme; the same thing by the reading of his picture, but this is my reading, say if wrong.
- `min_gap` 0.1 x ATR is mine (he gives no size).

**Can it run now?** Day trade: yes, once the structure-stop option is in the lane. Scalp: no.

---

## 6. Max Options Trading, "Everything you need to know about ORB" (video `SunW-hRFGzY`, 57 min; also `ZM2HluuMYoA`)

**Taught**
- Opening range = high and low (wicks included) of the 09:30-09:45 candle, plus the midpoint. No pre-market bias.
- BREAK [22:00-27:30]: a 15-minute candle CLOSES outside the range -> drop to the 1-2 minute chart; a "print through" continuation candle with lower highs behind it (for shorts) = entry. Stop at the range edge (14 points in his example) or behind the last swing (30 points). Target: not fixed; he trails and takes profit "when it is a lot of money", often 2 : 1 or more; one good trade and log off.
- FAILED BREAK [31:00-33:30]: a break that fails and closes back inside is traded to the middle line and the other edge.
- The same range at 18:00, 20:00 and 03:00 ET opens.

**Would run**: family `orb_confirm` (a close beyond the range of `or_min` minutes -> market with it; one trade a session), `or_min` 15, bar 15 (the 15-minute close is the signal; there is no 1-2 minute "print through" step), session nyam, structure stop (the range's other edge), target 2 x the stop, long and short as separate sheets.

**Not the video**
- The 1-2 minute continuation candle is not run: entry is at the 15-minute close, later and at a worse price than his.
- His stop is the nearer of the range edge or the swing; the family's structure stop is the far edge of the range.
- His target is a trail and gut feel; the sheet runs a fixed 2 x the stop, and 1 x and 3 x as neighbours.
- Failed-break trading and the other opens are other sheets (the 18:00 one, `nq_orb_eve`, was queued last night on the standard table).

**Can it run now?** Roughly: the entry and stop yes (once the structure-stop option is in the lane); the 1-minute confirmation and the trail, no.

---

## What this says about the earlier "already tested" statements

Only sheet 1 (Conti) and sheet 4's first half (Vince's IB first touch, built last night) can be run close to the video today. Sheets 2, 3 and 6 are partly or wholly not expressible, and sheet 5 needs a structure stop the earlier standard table did not give. So the earlier verdicts on these videos are verdicts on rough cousins, not on the strategies as taught.
