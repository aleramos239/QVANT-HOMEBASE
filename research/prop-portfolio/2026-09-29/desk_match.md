# Desk vs tester: do the desk versions make the research's trades? (Thu 2026-10-01 evening)
Branch feat/nq-prop-algos-daily-rules, worktree .../worktrees/wf_6efdccad-5c5-6, fix commit da4f215 (on top of fc560e1). Not merged, desk untouched.
Range 2021-09-22 -> 2026-09-30. Reference = the frozen tester trades the research used: in-sample cells straddle-tf30#10 / #32 and orb-tf5#10
(grids 20260930-001526-..-67c2, 20260929-231930-..-5276) + the holdout runs 224006 / 224650 / 224226, cut to nyam / pm / mid by entry time.
Desk side = the branch's tester strategies (same levels.py / atrbars.py / dayrules.py code the desk fires) run at 4 NQ (pm also 2 and 3 NQ) through
homebase.backtest.runner with the branch code, own scratch base dir, 3 workers max, after-hours. Scripts + numbers: desk_match/ (compare2.py, tickfed.py, rules_equiv.py).

## Result: after one fix, entries and stops are identical on every trade; exits identical except 11 touch-only days
| strategy (desk name) | trades compared | entry / fill / stop identical | exits identical (no-take days) | take days: desk exit = fill +/- take pts | touch-only days |
| nyam straddle, Flex, take $1,500 (nq_nyam_flex) | 1,253 | 1,253 | 195 | 1,054 (19.0 pts) | 4 |
| nyam straddle, Pro, first-day target $3,000 (nq_nyam_pro) | 1,253 | 1,253 | 355 | 898 (37.75 pts) | 0 |
| 11:05 ORB, take $1,000 (nq_orb_pro) | 1,244 (+9 half days skipped by design) | 1,244 | 161 | 1,080 (12.75 pts) | 3 |
| pm straddle, take $600 (nq_pm_flex), 4 / 3 / 2 NQ | 1,044 each | 1,044 each | 113 / 151 / 222 | 927 / 891 / 819 (7.75 / 10.25 / 15.25 pts) | 4 / 2 / 3 |
"Identical" = side, entry time to the ms, trigger, fill, stop price, and (no-take days) exit time, price, reason and dollars (gross = 4 x the 1-NQ frozen gross).
Every no-take-day exit equals the frozen exit; every take-day exit is at fill +/- the take points (net = pts x $80 - $16 at 4 NQ). Same set of traded days both sides.

## Mismatches found, causes, fixes
1. FOUND + FIXED: straddle stop price one tick (0.25 pt, $20 at 4 NQ) off the research on 326 of 1,253 nyam trades and 173 of 1,044 pm trades (ORB: none).
   Cause: the research set the stop at tick(raw trigger -/+ 3 ATR) and the tester then moved it by (fill - raw trigger). A straddle's raw trigger (anchor +/- 0.25 or 1.0 ATR)
   is off the tick grid, so after rounding the buy and sell legs' stop distances differ from tick(3 ATR) and from each other by up to a tick. The desk used tick(3 ATR) for both legs.
   Fix (levels.py leg_stop, Geometry.sl_sell_pts, engine places / moves / grades the sell leg with its own distance, tester strategy likewise). New tests: a 20,000-draw
   check of leg_stop against the tester's own to_tick steps, and an engine test for unequal legs. Full suite 2,549 passed (was 2,546). Re-run: 0 entry mismatches.
2. BY DESIGN (not fixed): 11 touch-only days (nyam Flex 4, ORB 3, pm 4 NQ 4 + 3 NQ 2 + 2 NQ 3). Price reached EXACTLY the take limit and no further. The research rule books these as wins
   (MFE net = $1,504 / $1,004 / $604 at 4 NQ = exactly the limit); the tester's limit fill needs one tick of penetration, so the tester run kept the trade (stop -$3.5k to -$13.7k, or flat-time exit).
   The desk acts on a touch (take watcher, 2 s grace, then market-flatten), so live these days should look like the research. The tester cannot show that. Cost in the desk-run totals vs the research rule: about -$43k nyam Flex, over 4.9 years.
3. BY DESIGN: 9 ORB half days (11-26-21, 11-25-22, 7-3-23, 11-24-23, 7-3-24, 11-29-24, 12-24-24, 7-3-25, 12-24-25): the desk skips (flat 13:30 is after the 13:15 close); the research traded them. pm already has no trade then.
4. BY DESIGN: take-day dollars. Research books a take as X minus 1 tick per micro ($20 at 4 NQ -> $1,480 for $1,500); the desk limit nets pts x $80 - $16 = $1,504 (+$24; 3 NQ +$18; 2 NQ +$12; Pro target +$4).
   So the research's take-day income is $24 lower per take day than a limit fill. Net of items 2 and 4, desk-run totals (4 NQ, $): nyam Flex 254k vs research rule 272k; ORB 71.0k vs 70.0k; pm 4 NQ -5.6k vs -5.7k.

## Extra checks (all clean)
- Live-path geometry: for EVERY traded-or-armed day (1,253 / 1,244 / 1,244) I fed the day's raw prints one by one into TickBars.add_tick (how the desk's market-data socket feeds it), up to the fire,
  then ran compute_geometry. Buy/sell stop, planned stops, anchor or opening range, and ATR equal the tester's day levels on all days (0 differences). This covers the 00:00-ET ATR restart and the 19 / 27 / 133-bar counts.
- Take / stop exit times: re-scanned the raw tape for each tp / sl exit (first print through the limit + 1 tick, or through the stop): matches the tester's exit reason and time on every tp / sl exit (0 differences); the rest are flat-time exits, covered by the identical-exit count.
- Daily-rule math vs evalcore: target_take level (dayrules.take_level vs evalcore.take_level) 200,000 random cases, 0 differences; day_take / day_lock (DayBook) vs _walk_day on 56,242 random multi-trade days, same trades taken on all; take_points is the first tick that nets >= X for qty 1-4 x 7 values of X;
  size tiers (<$1,000 2 NQ, <$2,000 3 NQ, else 4) as spec.
- day_lock is inert with one trade a day, so only the random-day check above exercises it.

## What this does NOT prove
Broker-fed bars (quote pushes + 1-minute history, ~3 minutes of history gap) and real fills; the engine's account-level standing for target_take on Flex (the tester only models Pro's first-day $3,000);
the 2 s watcher on a real touch. Run on paper first (the level_atr_parity journal line audits the live ATR).
