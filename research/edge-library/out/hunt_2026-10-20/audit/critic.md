# Completeness critic: hunt 2026-10-20

Written 2026-10-20. Nothing was run: no build run, no walk-forward, no tester. I only read the files and re-counted from stored arrays
(`~/.homebase/taught/*/result.json`, `wf/result.json`, `cells.npz`, `wf/test_cells.npz`), using the hunt's own `gate.grade()` and
`stack.leg_trades()`. Scratch scripts are outside the repo.

## The answer first

| Question | Answer |
|---|---|
| Round 2 tonight? | **No.** Expect about 0.07 real new legs and about 0.2 lucky passes from 15 sheets. A pass would be about 3 to 1 luck. |
| Untried angles with a real prior that give 0.7+ a day? | **Almost none left.** The free-hours idea with the strongest published reason (late-day momentum) is already the repo's only T2a, and it is spent and capped at 0.43 a day. Four weak-to-medium angles remain (table in Q1). |
| Is 5-10 a day at +0.075R plausible on NQ? | **Not on file.** On build days, 0 of 51 taught sheets at 2+ a day reach +0.075R, even before out-of-sample. The best that held the walk-forward is about 1.6 a day at about +0.08R (one family, partly seen). |

---

## Q1. Angles with a real prior that were not tried, for 0.7+ a day in the hours the FVG leg leaves free

**First, a correction to the premise.** The FVG leg (`owner_fvg_oside_15_a1m3_nl_r1`, its walk-forward test-month trades) is in a trade only
**3-26 % of weekdays in any 10-minute slot**, with a median hold of 18 min (mean 28). It enters 10:00-14:59. That is about 44 minutes in a
trade per day out of 390. So clock time is not the bottleneck: about 75-80 % of 10:15-15:00 is free too. The bottleneck is edges.

**What the free clock hours (09:30-10:15 and 15:00-15:58) have already used up:**
- 09:30-10:15: the 09:30 candle at a tight stop is dead. The wide 09:30 straddle is T4 (40 % random drift). open_fvg failed tonight.
  onr_orb is 0.4 a day and partly spent. 1m/5m nyam maps are drift (random nyam pools are green too).
- 15:00-15:58: late-day momentum (published: Gao, Han, Li & Zhou 2018 JFE; Baltussen, Da, Lammers & Martens 2021 JFE, gamma hedging and
  leveraged-ETF rebalancing) **is** `nq_pm_day_move_1500`, the repo's only T2a. It is spent, makes one decision a day (0.43 a day), and
  its 15:30 entries lose. The noise band in the pm (Zarattini et al. 2024) failed unseen (`noise_pm_long_v2`), and both sides failed Gate 1
  tonight.
- Time-of-day / same-hour seasonality (Heston, Korajczyk & Sadka 2010) was tested 2026-10-15: every standout hour loses without its best
  5 % of trades, and NQ/ES flipped in 2025. Dead.

**Menu families that are still untested on NQ 15m mid/pm and not on the dead list.** Their priors are medium or weak:

| # | Family · bars · sessions · settings (menu) | Prior | Est. a day | What is on file |
|---|---|---|---|---|
| 1 | `displace` k 1.25 / 1.5 / 1.75, 15m, 10:00-15:00, filter `topen with_0930` (the session-level side gate in place of EMA20), candle far-extreme stop, 1R | Medium: an impulse with the opening auction's side. It is the same gate that makes fvg_oside work. WHAT_WORKS §7 #4 names it as "no direct sheet" | 0.5-0.8 | All-day k1.5 = 0.91 a day; its extra trades are worth about $0; its walk-forward failed tonight (blind -$408). The family's blind months were read twice (cl_am_disp15, cl_disp15_allday) |
| 2 | `liq` mode break, levels `on` / `pd`, 15m, mid + pm, both sides | Medium: stop-loss clusters beyond the overnight and prior-day highs/lows cascade once crossed (Osler 2003, 2005, FX) | 0.4-0.8 (unknown) | Only nyam 1m/5m maps ran (42 % / 21 % of boxes green; stopped by the old size gate, not a verdict) |
| 3 | `vol_spike_break` m 2 / 3 / 4, 15m, pm (+ mid), both sides, max 2 | Weak to medium: high volume with a range break means informed flow (Llorente et al. 2002). For index futures that paper predicts reversal more than continuation | 0.4-0.8 | pm 5m map 69 % green with 0 floor boxes (old size gate); nyam 40 % green |
| 4 | `win_break` follow, r_start/r_end 11:00-11:30 or 13:30-14:00 (each session's own opening range), 15m, both sides | Weak: practitioner only | 0.5-0.8 | `nq_or_mid_long` map 73 % green, but long only (drift) |

Not proposed because they are a fit, not a reason: widening `hunt_fv_pullback5_s30_midpm` (0.33 a day at $286) to all day, and lowering k on
the displacement (the k ladder is monotone: lower k means lower dollars).

**Outside the menu (needs data the repo lacks):** dealer gamma regime (options positioning), the NYSE closing-imbalance feed (15:50),
and bond-equity lead-lag. None can be built tonight.

## Q2. Base rate, and what a round 2 is worth

**Base rate (WHAT_WORKS §1.1 plus the walk-forwards on file):**

| Evidence at the time | Read later | Held |
|---|---|---|
| Beat 95 %+ of random on build (pipeline / blueprint) | 12 | 1 at the unseen random gate |
| Hand random 10/10 seeds | 3 | 0 |
| Taught lane, 100 % random | 5 | 1-2 (vault break at size; ORB at half) |
| By-hand pre-registered locks | 28 | 2 pass, 3 near |
| Old library v2 | 15 | 0 |
| Locked boxes on 18 fresh sessions | 9 | 0 |
| **Gate-1 passers walk-forwarded (31 WFs on file)** | 17 stores / 9 families | 4 stores / **1 family** (fvg_oside 3×1m-ATR, partly seen) |
| Tonight | 6 | 0 |

That is about 1 in 10 to 1 in 20 "held", and about 1 in 30 "held AND beat random unseen". WHAT_WORKS says 1 in 5 to 1 in 10. Tonight's
0 of 6 pulls that lower.

**Why Gate 2 cannot separate real from lucky:**
- About 11-12 of the 15 traded months are build months, so P6.1-P6.4 mostly restate the build result. Of the 9 Gate-1 families, P6
  passed in 2.
- The truly blind part is 2025-09, 2026-01 and 2026-05 (2026-09 is partial and often "stood aside"). That is about 63 weekdays.
- For a real +0.075R edge at a 1:1.5 shape (σ ≈ 1.24R a trade):
  - At 1 a day, P(blind > 0) ≈ 0.68. At 5 a day it is 0.86.
  - A null rule after costs gets about 0.42-0.45.
  - So the blind read moves the odds by only about 1.5×.
- To show +0.075R at 2σ you need about **1,100 out-of-sample trades**: about 3 years at 1.5 a day, or about 10 months at 5 a day.
- **All 31 walk-forwards on file read the same window** (2025-07-01 .. 2026-09-22). 2025-09 was traded by 15 of them, 2026-01 by 20 and
  2026-05 by 18. The Amendment A leg is the best of about 29 reads of those months.

**Expected value of a round 2 of 15 sheets:**

| Input | Value | Source |
|---|---|---|
| Gate-1 passes | about 2 (1-3) | tonight 3/19, all taught sheet-bars 51/299 = 17 %; leftover ideas are weaker |
| P(real given a Gate-1 pass) | about 0.06 (0.03-0.12) | pooled base rate above |
| P(Gate 2 pass given real) | about 0.55 | P6 ≈ 0.8 × blind ≈ 0.7 |
| P(Gate 2 pass given null) | about 0.11 | P6 ≈ 0.25 × blind ≈ 0.45 (on file: 1 of 9 families passed both) |
| **Expected real legs** | **about 0.07** (0.02-0.2) | 2 × 0.06 × 0.55 |
| **Expected lucky passes** | **about 0.21** (0.1-0.35) | 2 × 0.94 × 0.11 |
| P(real given a round-2 pass) | about 25 % | |
| Expected trades a day added | about 0.05 | the gap to 5 a day is about 3.4 |

**Verdict: no round 2 tonight.**
- Each new walk-forward spends the same 3 blind months again, and a pass would most likely be luck.
- Even a real leg adds about 1 a day.
- The only clean out-of-sample left is forward days from 2026-10-17 on.

## Q3. Is the target plausible?

The target is 5-10 a day at 43 % / 1:1.5:
- That is +0.075R a trade after costs.
- At a 20-pt stop ($400) it is about $30 a trade net, or $39-44 gross at $9-14 a round trip.
- Doubt about the cost model alone ($9 vs $14) is 0.0125R, a sixth of the edge.

**Build days (the optimistic view), every taught sheet's average** (R = average trade / |average loss|):

| Trades a day | Sheets | Average > $0 | R ≥ +0.075 | Pass Gate 1 |
|---|---|---|---|---|
| 1-2 | 55 | 36 | 14 (almost all fvg_oside) | 17 |
| 2-3 | 25 | 10 | **0** | 0 |
| 3-5 | 14 | 4 | **0** | 0 |
| 5+ | 12 | 1 | **0** | 0 |

The best at 2+ a day is `owner_vwap_pullback_c15` at 3.09 a day, $14, +0.064R, and it fails Gate 1. The pipeline agrees: at 3+ a day 7 % of
cells are profitable and 0 % reach the floor.

**The most trades a day held out of sample (house 3:1 walk-forward):**

| Rule | WF a day | WF avg | WF R | Blind | Note |
|---|---|---|---|---|---|
| **owner_fvg_oside_15_a1m3_nl_r1** (and its 3 siblings) | **1.58** | $75 | +0.09 | 99 trades, 1.52 a day, $66, +0.08R | The credible maximum. Partly seen (the family was read 3 times; best of about 29 reads). Its mid-candle sibling lost -$12.4k blind. The Desk port made $2-33 per NQ in the same months |
| owner_vwap_pullback_c15 | 2.93 | $40 | +0.12 | 62 trades in ONE month (2025-09), $33 | Contaminated: 448 of 510 trades are build months; picked from 155 versions; fails Gate 1 on build ($14). The `_fix` version fails P6.3 |
| owner_jj_mom_allday_50_76 | 5.33 | -$30 | -0.03 | -$72 a trade | The only 5+ a day rule walk-forwarded. It lost |

So the edge size (+0.08R) has been seen once, but only at 1.6 a day. Reaching 5 a day needs 3-4 more independent legs of that quality. The
repo has found at most one in about 300 taught sheets and about 550 pipeline ideas. **The target is not plausible with what is on file.**
The nearest honest plan:
- The one leg at about 1.6 a day, on forward shadow.
- A real conversation with the owner about frequency: 1.5-2 a day at about +0.08R, not 5-10.

---

Not checked: runs_test/, stages_old, the Lab/tester walk-forwards outside the taught lane, and whether `vwap_pullback_c15_fix` changed
entries or exits. R uses the average loss as the risk unit, which overstates R a little where losses are time exits rather than full stops.
