# WHAT WORKS: the one map for the designer (Homebase inventory, 2026-10-20)

**Lens:** final merge. This file merges the three syntheses (synth_evidence_ranking.md, synth_combinations.md, synth_frequency_simplicity.md) with every correction that critique.md proves. Each correction was checked against the 10 inventory JSONs (all 613 items read), CLAUDE_NOTES.md, NEW_RUNS.md (including Batch 3) and these CSVs: tester_walkforwards.csv, taught.csv, taught_centre_winners.csv, pipeline_maps.csv and random_baseline.csv.

**Units.** Dollars are NQ at 1 contract after costs. A **µ** marks 1 MNQ micro: 1 NQ ≈ 10 µ plus about $6 per trade, which is the cheaper NQ commission per contract.

**Days.**
- Build days: 2021-09-22..2025-06-30 (945-948 sessions).
- Unseen days: 2025-07-01 onward.
- The old library ran on its own split, not this one: BUILD 2021-09..2023, PICK 2024, CHECK 2025, EXAM 2026.

**Floor.** $70 a trade on NQ, $75 on ES, $140 on GC, on 200+ trades.

**Honest number.** The owner's law: judge the average, never the best cell.

| Route | The honest number is |
|---|---|
| Pipeline / blueprint map | the average variant |
| Taught sheet | the cell together with its target neighbours ("avg of 3") |
| By-hand lock | the locked cell |

A best box is never the honest number.

**Tiers**

| Tier | Meaning |
|---|---|
| T1 | Passed an unseen read AND beat at least 95 % of random tables |
| T2a | Passed an unseen read (net > 0) AND its own pre-registered bar |
| T2b | Unseen net > 0, but failed its own bar, its map average or its random line, or the read was not blind |
| T3a | Build days only, beats at least 95 % of random, at the floor on the honest number |
| T3b | Build days only, beats at least 95 % of random, below the floor |
| T4 | Build days only, at the floor on the honest number, random gate not run or below 95 % |
| T5 | Green on build days but below the floor, or at the floor only in a best cell |

**House law (2026-10-18/19).** Only the 3:1 BLOCK walk-forward counts as out-of-sample. Every single unseen read below is the retired form, and none of them is house OOS. No OOS was run for this file, by the owner's order.

---

## 0. The answer first

1. **Nothing in the store passes the house law.** The law needs a blind 3:1 block walk-forward, beating at least 95 % of random, and the $70 floor on the honest number.
   - **nq_noise_gx_mid_long** is the only rule that ever passed an unseen read and the random gate, and that was under the retired single read.
   - Its honest build number fails the floor: the map's average variant is $39.
   - Its block walk-forward beats only 89.5 % of random.
2. **The best SIMPLE leads are build-days only (T3a), both on 15-minute NQ bars:**

   | Lead | Rule | Build result | OOS status |
   |---|---|---|---|
   | **Open-side FVG** | limit at the newest 15m FVG on the side of the 09:30 open; middle-candle stop; 1R; 2 a day | 1.07-1.48 trades a day at $98-121 a trade, 10 of 10 lines | the family's unseen months are spent (read 3 times) |
   | **15m displacement follow** | body at least 1.5×ATR; stop at the candle's far extreme; 1R; 10:00-11:00 | 0.60 a day at $177 (k 1.5) | fully blind |

   - **Both fail on ES and on GC (Batch 3).** The vault says every NQ build edge that lost on ES or GC was later noise on unseen days. Treat this as a red flag, not as a building block.
3. **Only one rule clears 1 trade a day at the floor on build days by itself: the open-side FVG.**
   - The only measured 2-a-day result is a stack: open-side FVG plus the all-day displacement, one position at a time.
   - The stack makes 2.24 a day, $112 a trade, PF 1.22, Sharpe 1.71, and every build year is positive.
   - But the all-day displacement leg's extra trades are worth about $0, and a stack is two triggers.
4. **The standard exit table cannot build either lead yet.**
   - Both need a structure stop: the middle candle, or the far extreme of the displacement candle. Only the taught route has that.
   - On standard geometry the same entries sit under the floor:

     | Entry | Standard-geometry version | Avg trade |
     |---|---|---|
     | open-side FVG | 3× 1-minute ATR stop | $59 |
     | displacement | pipeline 5m map | $54 |
     | displacement | Lab ATR stops | about $0 |

   - No fixed-point (30/45-point) open-side FVG sheet exists. That is the first build to make.
5. **What keeps working, in every store:** NQ only. Go WITH the move, in the NY cash session. A wide stop of 30-110 points (or 3× ATR, or a 15m candle). A target of about 35-40 points or more, or none.
6. **What never works:** fades (one rare exception), London, Asia, the evening, ES and GC bar rules, stops of 20 points or less, high-win-rate 0.5R shapes, order flow and Level-2 direction, and day filters (6 of 6 failed their hold-out read).

---

## 1. Evidence-ranked list of every rule that works (T1..T4)

### 1.1 What each tier has been worth so far (calibration)

| Evidence held at the time | Later read | How many held | Source |
|---|---|---|---|
| Beat at least 95 % of random on build (pipeline P4.2 / blueprint 2.3) | 12 read unseen | 1 passed the unseen random gate. 4 with build random of 99.8-100 % lost or went flat: ib_break_nyam_wl, noise_pm_long_v2, range_break_halfhour, 0830_news_straddle | pipeline_cards; blueprint #30 |
| Beat all random seeds by hand: 09:31 candle 10/10 seeds, VWAP band go 10/10, VWAP band fade 20/20 | 3 | 0 | vault_findings_a #63; vault_findings_b #10, #50 |
| Taught lane, beat random 100 % on build | 5 | Vault break held at size ($54 µ vs $55). ORB e1000 held at half. fvg_odir kept 2/3, then failed its walk-forward. Candle break and Conti both-sided failed. | taught_lane |
| Pipeline single reads that asked only "box > $0" | 22 | 9 "passed"; 1 at the random gate. Luck alone gives up to 7.4 passes. | vault_findings_b #76 |
| By-hand pre-registered locks, 2026-10-12..19 | 28 rules | 2 pass, 3 near, 22 fail, 1 invalid | vault_findings_b counted summary |
| Old library v2 saved (build + 2024 + random + stress) | 15 | 0 real, 8 not proven, 7 overfit | old_library |
| Heat map more than 60 % green | Next year | 48 % profitable (the base rate is 27 %); adding the $70 floor gives 66-71 % | blueprint gate study |
| 9 locked boxes read on 18 fresh sessions | 9 | 0 beat 95 % of random | manual_lane #44 |
| Largest build average variant (nq_vwap_pull_pm, +$48.5k) | 1 | Worst unseen read in the store: -$82 a trade, beats 0.08 % of random | pipeline_maps #23 |

**Read:** T3 and T4 are leads, not evidence. A build-day pass (even with t around 3, 5 of 5 years up and a random control beaten) has held unseen about 1 time in 5 to 1 time in 10.

### 1.2 T1: unseen read + at least 95 % random

**Under the house law: NONE.**

Under the retired single read only:

**1. nq_noise_gx_mid_long** (pipeline_cards #0, pipeline_maps #0, lab_desk #0, vault_project_notes #0, vault_findings_a #44)

| Field | Value |
|---|---|
| Market / session / bar / side | NQ, midday 11:00-13:30, 1m, long only |
| Entry | 1m close above (01:00 open + 0.3 × daily ATR14) AND above the VWAP from 01:00 |
| Stop / target | 30 pt / 3R (90 pt), flat at session end, up to 3 a day |
| Trades a day | 0.74 |
| Build | box $116 on 698 trades, PF 1.29, win 34 %; map average variant **$39** (85 % of cells green, 44 floor boxes) |
| Unseen | single read: box 263 trades, $149, PF 1.37; average variant $88; beats 99.98 % of random tables. Desk read: 276 trades, $118, PF 1.30 |
| Why only retired-T1 | See below |
| Status | spent |

Why it is only retired-T1:
- **Floor:** the map average of $39 fails line 2.2.
- **Random pools:** the 99.98 % used both-sided random pools for a long-only rule in a rising year. No same-side pool exists.
- **Walk-forward:** the block 3:1 walk-forward made $24,427 on 262 trades but beat only 89.5 % of random, so it fails P6.2.
- **Fresh sessions:** 18 fresh sessions lost -$3,731 (beats 24 %).
- **Code drift:** four build re-runs with identical inputs gave +$77k, +$62k, +$25k and -$5.7k.
- **Rule text conflicts:** the anchor is 18:00 or 01:00, the window ends 13:24 or 15:30, and the exit is session end or the day.
- **Unseen beat build ($88 vs $39):** the same sign-flip pattern as the 20:00 candle.
- **Side:** long-only, against the owner's "both long and short".

### 1.3 T2a: unseen pass + its own pre-registered bar

**2. nq_pm_day_move_1500** (vault_findings_b #27, lab_desk #5)
- **Rule:** NQ, decide at 15:00 on 1m, both sides. Follow (last print − prior close) when abs(move) ≥ 0.5 × prior range.
- **Exits:** stop 2 × ATR(5m), target 0.75R, 1 a day, flat 15:58.
- **Frequency:** 0.43 a day.
- **Build:** $88 on 406 trades, PF 1.28, win 62 %.
- **Unseen:** 138 trades, $72, PF 1.20; with 2 ticks +$6.2k. Desk read: 140 trades, $71.
- **Caveats:**
  - It passed bar B only. Bar A (65 % win, frequency) failed.
  - The random gate was never run.
  - Its twin pm_1500_all lost on longs and in H2-2025.
  - 15:30 entries lose. ES PF is 1.04.
  - Spent.

**3. nq_pdsweep_vwap_lowrange (T2a\*)** (vault_findings_b #37, lab_desk #4)
- **Rule:** NQ 09:30-15:55, 5m, both sides. Fade a 5m close back inside after price traded through the prior session's high or low.
- **Filters:** price on the VWAP side, and a quiet prior day.
- **Exits:** stop 2 × ATR(5m), target 0.5R or 0.75R, at most 2 a day.
- **Frequency:** 0.19 a day.
- **Build:** $101 / $152 on 176 trades, PF 1.37 / 1.44, win 74 % / 65 %.
- **Unseen (pre-registered):** 61 trades, $170 / $221, PF 1.45 / 1.47.
- **Caveats:**
  - Under 200 trades.
  - 2 filters.
  - About 215 family looks.
  - The random gate was not printed.
  - It is the only fade that held.
  - Spent.

**4. gc_nfp_cpi 08:30 straddle (T2a\*)** (vault_findings_a #16, vault_project_notes #52)
- **Rule:** GC on NFP and CPI days only. OCO ±2 points, stop 3, target 6.
- **Frequency:** 0.08 a day.
- **In-sample:** $300 on 77 trades, PF 3.8, win 68 %.
- **OOS:** one shot, 39 trades, $299, win 69 %.
- **Caveats:**
  - 95 % of the profit comes from holds of 5 seconds or less, which fails the owner's no-scalping rule.
  - It is a post-hoc subset of about 1,290 looks.
  - Its OOS window overlaps today's build days by 6 months.
  - It is GC only.
  - Spent.

### 1.4 T2b: unseen net > 0 but failed its own bar, its map average or its random line, or not blind

| # | Rule (source) | Market / session / bar / side · exits | Trades a day | Build | Unseen | Why only T2b |
|---|---|---|---|---|---|---|
| 5 | **conti_vault_break** (taught_lane #2, lab_desk #8) | NQ 11:00-15:30, 30m, long; close above 01:00 open + 0.3 × ATR15 and above VWAP(01:00); 75 pt stop / 40 pt target (0.53R); 3 a day | 0.81 | $85 on 766 trades, PF 1.21, win 67 %; 9-cell average $84; beats random and random longs 100 % (control covers 09:30-11:00 only) | Desk: 305 trades at 7 µ, $54 (about $77 per NQ), PF 1.18, t 1.35 | Long-only. Same signal as #1 (correlation 0.65-0.71). Not pre-registered. The "skip first trade" split flipped. |
| 6 | **conti_onr_orb e1000** (taught_lane #1, lab_desk #2) | NQ 10:00-15:30, 15m, one side a day (09:30 open in the top or bottom third of the 01:00-09:30 range); 15m close beyond the 09:30-09:45 range; ADX > 20; stop 30 % of ATR15 (about 109 pt); 3R; flat 15:30 | 0.40 | $409 on 380 trades, PF 1.54; average of 3 targets $383 | Desk micros at $1k risk: 120 trades, $93 vs $205 build at that size. A second read gave 123 trades, $125, PF 1.4 | Kept about half. Two reads disagree. The random control covers 09:30-11:00 only. 62-69 % of exits are the 15:30 clock; the 3R target is hit 3-4 % of the time. |
| 7 | **nq_0300_candle_body** (manual_lane #9-10, vault_findings_a #58, lab_desk #3) | NQ London, 03:00 5m candle, body ≥ 0.4 of range, follow at its close; 30 pt / 3R; flat 09:35 | 0.55 | $90-104 on 520 trades, PF 1.25, win 34 % | Manual read: 191 trades, $116, PF 1.26. Desk: 204 trades, $81. One-cell block walk-forward: build months $146, unseen months 53 trades at $237. A 2025-03..09 walk-forward lost -$4,325 on 40 unseen trades | No random control (the pool has no time stop). 2023 is 46-75 % of build profit. The long side carries (body 0.7: +$31.8k long / -$4.4k short). The standard-table card is $6. |
| 8 | **fvg_oside 3× 1-min-ATR, no cap** (taught_lane #20-21) | NQ 09:30-15:00, 15m, both sides by the 09:30 open; limit at the newest FVG edge; stop 3 × ATR14 of 1m bars (about 33 pt); 0.75R / 1R | 1.75 | $59 on 1,661 / 1,652 trades, PF 1.22 / 1.19 | The walk-forward's unseen part: +$7.2k on 100 trades (0.75R), +$6.6k on 99 (1R) | The walk-forward stitches about 11 build months. The test months had been read before (1-a-day sibling). Build is under the floor. The Desk port's walk-forward made +$349 µ on 127 trades and +$26 µ on 126 trades in the same months (about $2-33 per NQ). Max stop 516 pt. |
| 9 | **nq_am_fvg15_gap** (vault_findings_b #65, lab_desk #13) | NQ 09:30-12:55, 15m, both; limit at the newest gap edge, no side gate; stop 2 × ATR(5m) (median about 82 pt); 0.75R; max 4 | 1.37 | about $73 per NQ ($6.7 µ), PF 1.16 | 401 trades (1.23 a day), about $95 per NQ ($8.95 µ), PF 1.16 | Failed PF 1.20 and its second half (-$1.5k); 2026 PF 0.98. About +0.04R: an 82-pt stop makes $95 a thin edge. |
| 10 | **nq_am_daymove_quiet** (vault_findings_b #53) | NQ 09:30-12:55, follow the day's move with a quiet-day filter; 2 × ATR / 0.75R | 0.97 | about $130 per NQ, t 3.76 | 309 trades (0.95 a day), about $87 per NQ, PF 1.14 | Failed PF, longs, first half. It is a day filter. |
| 11 | **nq_pm_1500_all** (vault_findings_b #56) | the 15:00 follow, threshold 0.25 × ADR from the 09:30 open, no filter | 0.6 | about $100 per NQ (2024 PF 0.86) | 188 trades, about $89 per NQ, PF 1.22 | Contaminated by #2's read. Longs and H1 lost. |
| 12 | **nq_0830_candle_0925** (vault_findings_b #58) | 08:30 5m candle body ≥ 0.7, follow, 2 × ATR / 0.75R, flat 09:25 | 0.24 | about $70 per NQ | 76 trades, about $119 per NQ, PF 1.41 | Failed months and Monte Carlo by half a point. The same entries with 30 pt / 3R exits read flat ($8, PF 1.02). Mostly short. |
| 13 | **owner_candle_break_15_nyam_nocap** (taught_lane #31, vault_findings_b #93-95, lab_desk #24) | NQ, decisions 09:45-10:45, 15m, both; close beyond the previous candle's wick; candle stop; 0.5R; no cap | 2.28 | $50 on 2,158 trades, PF 1.12, win 69 %, 100 % random | Pre-registered read FAILED: 684 trades, $25, PF 1.039 | See the walk-forward note below the table. |
| 14 | **owner_fvg_odir_15_nl_new** (taught_lane #26, vault_project_notes #20) | NQ 10:00-15:00, 15m; side = 09:30-10:00 direction; newest FVG; middle-candle stop; 1R | 1.24 | $78, PF 1.24 | Single read: 367 trades, $49.5, PF 1.11 (about $7 at $500 risk) | The family's 48-version walk-forward FAILED (-$1,644, PF 0.98). The owner closed it. |
| 15 | **GC 10:00 release bracket evC** (old_library #6, manual_lane #33) | GC 10:00 release days; tight OCO 0.6 / 1.6 / 1.6 | about 0.15 | library average variant $69 (GC floor $140) | 2025 +$2,226, 2026 +$522 (-$661 under 2 ticks) | Its 2025 "unseen" year is half build days. The random gate used random minutes and day subsets. The edge is fading: $111 → $94 → $49 → $16. 89 % of profit in holds ≤ 5 s. Not a main earner. |
| 16 | **Book boxes: supertrend_nyam_short; donch_first_nyam / _slow** (pipeline_cards #1-3) | NQ nyam 5m/15m; 45/45 pt; 30 pt or 0.2 %, no target | 0.3-0.96 | boxes $106-194, but map averages $3 / $32 / $42 | boxes +$18k to +$55k, but map averages $13 / -$27 / $17; random 84.6 / 18.5 / 60.3 % | Judge the average: one lucky island. Donch loses $104-111k without its best 5 % of trades. |
| 17 | **nq_noise_gx_pm_long / _t3** 5m (pipeline_cards #25-26) | NQ pm, 5m, long; 45 pt / 2-3R | 0.43-0.47 | map $38-55 | map $11 / $22; random 69 / 77 % | Sign held; size and random gate did not. |
| 18 | **owner_jj_cont_15m** (taught_lane #17, vault_findings_b #108) | NQ 09:45 follow of the first 15m bar's colour; 25/38 (50/76 on bodies over 25 pt); 1 a day | 0.99 | $70, PF 1.15, random 92.6 % | Walk-forward: 175 trades, $89. Blind months: 34 trades, -$726 | Fails random. 111 versions were screened. |

Notes on #13 (owner_candle_break_15_nyam_nocap):
- 12-cell block walk-forward: 650 trades, $71.5.
- Its build months made $31.8 a trade. Its 120 unseen trades made $247 a trade.
- Two months carry 86 % of the walk-forward (2024-09 +$19.6k, 2026-01 +$20.2k).
- The locked fixed cell lost -$2,411 on 84 test-month trades.
- Trade 2 of the day went from +$100 on build to -$103 unseen.
- ES and GC lose 26 of 26 cells.

Weak T2b, treat as dead:
- **20:00 candle:** +$10.0k on 73 trades unseen, but its build cells were 12-42 % green. The sign flipped, and the pipeline walk-forward of the same form beat 21.9 % of random.
- **FVG-fade seat B (overnight):** one pre-blueprint exam, +$10.3k.
- **Old library, one good unseen year each:** GC evB, first_bar_mom NQ 15m mid, donchian NQ 30m nyam, 18:00 straddle. Their 2025 year is half build days, and none held two years.

Positive unseen but failed their own bars (effectively failures):
- nq_gap_fade_0930: PF 1.10, H2-2025 -$8.2k
- nq_ldn_drift_long: PF 1.08
- nq_pm_1500_quiet: PF 1.15
- nq_am_vwap_pullback: PF 1.06
- nq_am_vwpb_plain: PF 1.06
- nq_0830_straddle: $7
- nq_range_break_halfhour: box $3, average -$28

Regime artefacts, never credit:
- nq930 tight straddle: lost on all 17 build cells, won on all 16 unseen cells.
- nq930_regime: 0 of 60 build cells green, 53 of 60 unseen.

### 1.5 T3a: build days only, at least 95 % random, at the floor on the honest number

| # | Rule (source) | Session / bar / side | Stop / target / cap / filter | Trades a day | Avg $ (cell / honest) | PF | Win | Random | Lines and flags | Unseen status |
|---|---|---|---|---|---|---|---|---|---|---|
| 19 | **displace_ema15_1r_10to11_k1p5** (taught_lane #5) | 10:00-11:00, 15m, both | Body ≥ 1.5 × ATR14, enter at the close in its direction; candle far-extreme stop; 1R; 1 a day; EMA20 side | 0.60 | $177 / avg of 3: **$135** (0.75R $88, 1.25R $140) | 1.26 | 56 % | 100 % | 10/10 lines; Sharpe 1.25; DD $18.9k; long $43k / short $57k; years 21* +12k / 22 +32k / 23 +4k / 24 +46k / 25* +6k | **fully blind** |
| 20 | **displace_ema15_1r_10to11_k2p0** (taught_lane #3) | same | k 2.0 | 0.36 | $219 / avg of 3: **$166** | 1.31 | 56 % | 99.8 % | 10/10; DD $15.0k; short $69k / long $5k (shorts carry; 2025* +$37k) | fully blind |
| 21 | displace_vwma15_1r_10to11 k1.5 / k2.0 (taught_lane #4, #6) | same | VWMA side in place of EMA20 | 0.63 / 0.38 | $158 / $186 | 1.23 / 1.26 | 55 % | 99.9 / 99.6 % | 10/10 and 8/10 lines | fully blind |
| 22 | **cl_fvg_oside_15_mid_r1_t2_gap0p1** (NEW_RUNS) | 09:30-15:00, 15m, both, side of the 09:30 open | Limit at the newest FVG near edge; gap ≥ 0.1 ATR; middle-candle stop (median about 38 pt); 1R; 2 a day | 1.34 | $108 / avg of 3: **$94** | 1.30 | n/a | 100 % | 10/10; Sharpe 2.07; 78 % of months won; DD $15.1k; $ a trade by year 204 / 173 / **-3** / 74 / 231 | spent |
| 23 | cl_fvg_oside_15_mid_r1_t2 (gap 0) / _gap0p25 (NEW_RUNS) | same | gap 0 / 0.25 ATR | 1.48 / 1.07 | $98 ($90) / $121 ($103) | 1.29 / 1.30 | n/a | 100 % | 10/10 both; Sharpe 2.03 / 1.80. The gap knob is **monotone**: 0 / 0.1 / 0.25 ATR give $98 / $108 / $121 a trade; the 3-value average is about $109 | spent |
| 24 | owner_fvg_oside_15_mid_r1 / cl_ _t3 / _nl (taught_lane #18, NEW_RUNS) | same | cap 1 / 3 / none | 0.94 / 1.64 / 1.66 | $99 ($92) / $87 ($79) / $86 ($80) | 1.27 / 1.25 / 1.25 | 54 % | 100 % | Cap 1: 2023 -$7k; without its best 5 % of trades -$8.3k | spent |
| 25 | owner_fvg_oside_15_mid_r075 (taught_lane #19) | same | 0.75R | 0.94 | $81 | 1.25 | 61 % | 100 % | 9/10; 2023 -$12k | spent |
| 26 | **conti_onr_orb_e1030** (taught_lane #0) | 10:30-15:30, 15m, one side a day | As #6 | 0.38 | $484 / avg of 3: $458 | 1.76 | 58 % | 100 % (control 09:30-11:00 only) | 10/10; every year positive (2022 +$62k, 2023 +$33k, 2024 +$63k); shorts carry | Shares trades with e1000, which was read: partly spent |
| 27 | fvg_regime_vollow_nq (blueprint #11, lab_desk #34) | nyam, 5m, both | Newest-FVG limit; low-volatility days; **"open" session-sized stop table, not the standard table** | 0.38 | $144 (average of 239 boxes) | 1.18 | 50 % | 99.28 % on un-restamped pools | All 8 build lines; Monte Carlo 87 %; ES neighbour loses. On the standard table the same entry is $15-20 | blind; no lock, no code check |

### 1.6 T3b: beats random on build, under the floor on the honest number

| Rule (source) | Trades a day | Honest $ (cell or box) | Why T3b |
|---|---|---|---|
| **cl_disp15_ema_allday_k1p5** (NEW_RUNS) | 0.91 | $117 cell / $90 avg of 3; 99.8 % | Widening 10:00-11:00 to 10:00-15:00 adds about 291 trades worth about $0. PF 1.17 (< 1.2). DD $28.9k (about $2.9k at 1 µ, over $2k). 8/10 lines. The NEW_RUNS stack used this leg. |
| **nq_displace_nyam_a5** (pipeline_cards #16, pipeline_maps #25) | 0.91-0.99 | map average **$54.5** (79 % green, 42 floor boxes); box k1, 20 pt, no target $157, 97.9 % | Win 15 %. -$129k without its best 5 % of trades. ES and GC lose. Blind: stopped by a flexind.py change. |
| **nq_noise_gx_mid_long_slow** a15 / a30 (pipeline_cards #17, pipeline_maps #10-11) | 0.33 / 0.32 | map averages **$41 / $41.5**; 30m box $283, 97.4 % | Not stronger than the 1m on the average. The only card whose ES and GC neighbour maps were both profitable. Blind for these bars. |
| **owner_pm_first_bar_15** (taught_lane #35) | 0.98 | $40 centre; 9-cell average **$43**; the 37.5 / 37.5 corner is $74 | Long-only in effect (+$38.3k long / -$0.9k short). Same-side random never run. Old library first_bar_mom NQ 15m pm beat random 50.5 % (lift -$24). PF 1.15. |
| demo_range_break_nq (blueprint #0) | 0.88 | $54; 96.2 % | Monte Carlo 23 % |
| cl_fvg_oside_15_mid_r05_t2 (the owner's 0.5R) | 1.52 | $54 ($49); win 70 % | Half the 1R money |
| owner_candle_sweep_15_ema50_nyam_1tr (taught_lane #32) | 0.62 | $43; 97.7 % at 1 try | About the 18th version (luck bar about 99.7 %). Desk test -$10.7 µ. |
| es_or_long (pipeline_cards #18) | 0.27 | $57 (ES floor $75); 97.4 % | The only ES card past stage 1 |
| owner_vwap_pullback_c15 (taught_lane #37) | 3.07 | $16 | Its "walk-forward pass" ($40, 100 % random) stitches mostly build months, and it was picked from 155 screened versions. Unseen part +$2.0k on 62 trades. |
| conti_day_long / conti_long_ml3 (taught_lane #29-30) | 2.0 | $62-64 | Beats random 100 % but random LONGS 0 %: pure drift. Really T5. |

### 1.7 T4: build only, at the floor on the honest number, random not run or below 95 %

| Rule (source) | Session / bar / side · exits | Trades a day | Honest $ | Flag |
|---|---|---|---|---|
| nq_onr_break_a15 (pipeline_maps #1, pipeline_cards #20) | nyam 15m both; overnight-third day side + ADX; standard table | 0.29 | map average **$144** (95.8 % green, 87 floor boxes) | **Code check FAILED**: 15,696 of 54,720 trades were outside the window. Untrusted until rerun. Same idea as #6 / #26. |
| owner_jj_cont_15m_big (taught_lane #16) | 09:45 first-15m-bar follow when the body is over 25 pt; 50 / 76 | 0.61 | $128 | Random 92.9 %; picked after 111+ versions |
| nq_fvg15_bounce_late_nyam_a15 (pipeline_maps #34) | 10:00-11:00 15m FVG ≥ 0.25 ATR, limit at the near edge; standard table | 0.16-0.23 | map average **$110** | Thin: 216 trades in the best box |
| nq_orb_f_level_clear (blueprint #39) | nyam 5m ORB only when no level lies within 1 ATR | 0.24 | $89 (87.5 % of boxes) | Monte Carlo 70.3 %; random never run |
| fvg_latest_nq / fvg_regime_mom (blueprint #4, #6) | nyam 5m newest-gap limit, **"open" stop table** | 0.73-0.76 | $92 | Monte Carlo 63.8 %. On the standard table $15-20 (nq_fvg_latest_a5 / c5). |
| fvg_regime_trendag (blueprint #9) | same, trend-against days | 0.20 | $99 | 184 trades; shorts -$1.5M over boxes = long drift |
| cl_disp15_ema_allday_k1p75 / _k2p0 (NEW_RUNS) | 10:00-15:00 displacement | 0.67 / 0.48 | $133 ($97) / $154 ($117) | 6/10 and 7/10 lines; random not run. The k ladder 1.0 / 1.25 / 1.5 / 1.75 / 2.0 gives **$19 / $55 / $117 / $133 / $154**: monotone |
| displace_ema15_1r_k2p0, 09:30-11:00 (taught_lane #10) | 15m | 0.59 | $103 | Random 94.4 %; 7/10 lines |
| nq_donch_first_nyam_slow_a30 (pipeline_maps #20) | nyam 30m both; standard table | 0.34 | map average $75 | Its 5m and 15m siblings failed or were weak unseen |
| nq_supertrend_nyam_short_slow_a30 (pipeline_maps #37) | nyam 30m short | 0.20 | $72 | 0 boxes reach 200 trades |
| VWAP persistence N=20 (vault_project_notes #35) | RTH 1m both; exit when the other side holds 20 closes | 2.2 | $81 (t 1.82, 4/4 years) | All 78 bracket versions lose. The VWAP family (2021-26) is burned, so it cannot be tested clean. |
| nq930 wide straddle grid (lab_desk #31, vault_findings_a #36-37) | 09:30 OCO ±15; stops 50-150 pt / targets up to 3R | 1.0 | wide-stop cells average **$70.3** (o15/s50/r3 $122 was picked after seeing the map) | Random median +$47k (about 40 % of the result is free). Monte Carlo 50 %. DD at 1 µ $2.8-8.1k. Family test days spent. |
| candle930 round 2, 5m, onr stop (vault_findings_b #87) | 09:30 5m candle follow; stop at the far side of the 00:00-09:30 range (about 98 pt); 1R | 1.0 | $110 (average of 20 variants, 18/20 green) | t 1.06; long +$48.1k / short +$4.1k; no drift control. The plain 09:30 follow's unseen days were read and failed. |

### 1.8 Demoted to T5 or contaminated (the critique proved these)

- **judas K0.25:** $123 is the owner's cell; the 56-cell average is $56.
- **nq_930_straddle_o15_s50_r3:** $122 was picked after seeing the map. Its honest number is the wide-cell average above.
- **fair-price fade, round 4, K3:** $73 is one green cell of 30+ looks in a dead family.
- **nq930_bigprint_side_sl30_tp90:** $126, but its in-sample months included test-day months. It is 1 green bracket of 5, about 40 cells (corrected p about 0.1), and 2026 is red.
- **owner_pm_first_bar 37.5 / 37.5:** $74 is a corner; the 9-cell average is $43.

**T5 counts:**
- Taught lane: 97 of 236 centre cells green.
- Pipeline: 242 maps with a positive average variant, but only 7 clear both 2.1 and 2.2.
- Blueprint: 15 ideas pass 2.1 and fail 2.2.

**Notable T5 rules (honest $):**

| Rule | Avg trade | Trades a day |
|---|---|---|
| nq_ib_break_mid_a5 | $53 | 0.43-0.56 |
| nq_open_gap_mid_a5 | $47 | 0.24 |
| nq_pm_follow_long_a5 | $42 | 0.52 |
| nq_orb_base | $38 | 0.97 |
| nq_vwap_pull_mid_long_a5 | $38 | 0.61 |
| nq_noise_pm_long_a5 | $38 | 0.32 |
| nq_ny_or_retest | $38 | 0.26-0.62 |
| nq_ny_vwap_band_go | $30-36 | 0.76 |
| nq_ny_or_close | $24 | 0.79 |
| nq_vwap_pullback_a5 (mid, both) | $21 | 2.05 |
| tm_break_only | $22 | 1.91 |
| owner_jj_mom_allday_50_76 | $25 | 4.7 |
| nq_0930_candle_body15_15m | $39 | 0.77 |
| NQ 10:00 30m candle continuation | $40 | 0.53 |

### 1.9 Blind vs spent (for when the owner orders the walk-forward)

| Candidate | Unseen months |
|---|---|
| 15m displacement with an EMA20 / VWMA gate (36 taught sheets, 111 Lab cells, 13 cl_ runs) | **fully blind** |
| nq_displace_nyam (5m, no target) | **fully blind** |
| nq_noise_gx_mid_long_slow 15m / 30m | blind for these bars, but its 1m sibling read the same months |
| fvg_regime_vollow_nq, nq_onr_break_a15 (after the fix), nq_fvg15_bounce_late, nq_orb_f_level_clear, nq_donch_first_nyam_slow_a30, owner_pm_first_bar_15, nq_ib_break_mid_a5, nq_open_gap_mid_a5, nq_pm_follow_long_a5 | blind |
| conti_onr_orb_e1030 | partly spent (the e1000 sibling was read twice) |
| **fvg_oside, every stop and cap** | **spent**: read 3 times (1-a-day sibling walk-forward, lane no-cap walk-forward, Desk walk-forward) |
| fvg_odir, noise band 1m (all sessions), vault break, 03:00 / 08:30 / 18:00 / 20:00 candles, 09:30 candle (15 s / 30 s / 1m / 5m), candle break / sweep, nq930 straddle family, VWAP families (2021-26 burned), gap fade, day-move / quiet / gap locks, pd sweep, GC event family, the 22 pipeline single reads | spent |

For spent families, the only clean OOS left is forward days from 2026-10-17 on. The 18 sessions from 2026-09-23 to 10-16 are already used.

### 1.10 What has NO evidence

- **House-law pass.** No rule passes the house law (blind block 3:1 walk-forward + at least 95 % random + the floor).
- **1+ a day held unseen at the floor.** No rule trades 1+ a day, passed a clean unseen read, AND met its PF bar at the floor.
  - nq_am_fvg15_gap kept about $95 per NQ at 1.23 a day unseen, but failed PF 1.20 and its second half.
- **Standard-geometry version of either leader.**
  - There is no fixed-point (30/45 pt) open-side FVG sheet.
  - There is no standard-table 15m displacement at 1R that clears the floor: the Lab's ATR / cand / c15 stops are about $0.
- **Cross-market.** No leader survives on ES or GC.
  - No ES, GC (bar-based), YM, RTY or CL edge exists.
  - The only cross-market "carry" is nq_noise_gx_mid_long_slow's ES and GC neighbour maps (build only).
- **Sessions.** No London, Asia or evening edge, except one 03:00 candle box (no random control).
- **Short-only.** No short-only edge, beyond one supertrend box on a flat map.
- **High win rate.** Nothing reaches 65 % or more with a target of 0.75R or more at 1 a day or more (0 of 7,221 configurations). Every 70 % box is the 0.5R geometry.
- **Filters out of sample.** No filter carried out of sample:
  - Quiet-day, gap-day, release-day, VWAP side, EMA, ADX / RVOL / RSI / ATR regime and candle size all failed or are untested unseen.
  - Low volatility on the newest FVG and "level clear" on the ORB are build-only.
- **Direction signals.** No order-flow, Level-2, delta, absorption or chart-indicator direction signal works (52-indicator study: only the 15-min opening range continues, and only by a few ticks).
- **Portfolio.** No proven portfolio. Mixes are build-day arithmetic, or re-scores of runs already read.
- **Monthly pick.** No sign that the walk-forward's monthly pick adds anything. The candle break's pick changed 13 of 14 times and a fixed cell did as well; eve_2000 picked a different cell in all 15 blocks.
- **Same-side random.** No same-side random control exists for any long-only rule in the pipeline.

---

## 2. The graveyard (do not re-test)

### 2.1 Families that fail everywhere

| Family | Stores and counts | Verdict |
|---|---|---|
| VWAP fades and touches (vwap_z, band fade, 3-sigma, Rother touch, VWAP tap, VWMA15 limit at VWAP) | Pipeline: vwap_z 0 of 8 maps (mean -$24.6k), vwap_band 2 of 15 (-$25.0k). 3-sigma fade 0/24 cells. ATR-stop band fade locked, then unseen -$110 a trade (10 µ), worse than all 10 random controls. Rother 18/18 tables -$22..-$35 on NQ, 18/18 on ES. VWAP tap 42 cells, 0 real. VWMA15 limit 48 in-sample cells; 2 OOS shots both negative. | Dead: the session VWAP is crossed, not defended |
| VWAP crosses / flips | vwap_flip refuted at any friction (gross +$6.8 vs $26-30 friction). vwap_ema_x 0 of 63 library units. NY vwap_cross $19, reclaim $15. London / Asia reclaim -$9 / -$14. | Dead. Exception: the persistence exit, which is untestable clean (T4) |
| VWAP trend pullback / Conti drift (every form) | Library pm $57k build, then 2024 $10-21k below random. Pipeline 0 of 7 cards (pm both -$82 unseen; mid long flat). Conti both-sided unseen -$19 on 999 trades. AM pullback quiet / plain unseen PF 1.06. Evening slope PF 0.68. Long-only $61-64 = drift (random longs 0 %). | Dead |
| Fades of the open / OR / gaps | NY OR fade 2.6 % of boxes, -$37. open_fade 0 of 6 units, 0 of 4 maps. 09:30 burst fade 0/24. orfail 26/27 lose. Two gap-fade locks failed unseen. | Dead |
| Fair-price / JJ fades | jj_fair 25/38 -$44 on 2,025 trades, beats 1 % of random. 30 fade versions -$22..-$68. Fading every bar = 38.2 % (the base rate). Evening 27/27 cells lose. eve_fair 0/288 boxes. | Dead |
| disp_oside (fade the open's side on a displacement) | 52 of 52 sheets lose | Dead |
| Candle sweep fade | 23 of 29 sheets lose. 17,371 trades over 7 sessions: -$309k. 7 pipeline cards stop at stage 1. Only nyam + 1h EMA50 is positive ($26-43), and that was picked post hoc. | Dead outside one post-hoc slice |
| Liquidity sweeps (except pdsweep) | liq 0/10 cards. NY 0-1 of 24 boxes; London 1-5 of 24. Thin-hour sweep -$56. sweep_rev pre unseen -$38. The evening Asia sweep was a LOOK-AHEAD; honest $39 fails. | Dead |
| Value area | va_reclaim 0 of 84 library units. Two pipeline unseen reads fail (-$35, -$62). Bruni VA break -$74 / -$102. Open-outside-value fade t 0.5. | Dead |
| FVG bounce with NO side / regime gate | 41,000 pullbacks: 65 % at 0.5R, 49 % at 1R = random. Pipeline fvg 0/19 cards. nq_fvg_pullback 28,880 trades, -$2.5. fvg_trend_fade 12 of 14 test cells negative. 5m and 30m fvg_oside / odir lose. | Dead as a bounce; see 2.3 |
| Mean-reversion indicators | rsi2 (ES evening 84 % → 5 % in 2024), ibs 0/27, rsi 1-2/27, pinbar $5, squeeze 88 % → 20 %, ib_touch -$44..-$107 | Dead |
| Weak-reason trend tools | tema_slope (overfit), ema_pullback (7 units fail 2024), ema_ribbon 0/5, hurst_ac_break -$81 (the filters subtract $103 a trade), supertrend map averages about $0 | Dead |
| TIGHT clock brackets (stops ≤ 25 pt) | 09:30 5-10 pt on ticks -$8,152 (PF 0.88). YM -$9,996. 18:00 reopen 0/60 NQ and 0/60 GC. NQ 08:30 release brackets died in 2025 (0/27, 6/27, 8/27 variants). 18:00 / 03:00 / 11:05 no better than a random minute. CL refuted. | Dead (wide 09:30 straddle is T4; see 2.3) |
| Event chase (market order after a release) | 5-22 % of 224 variants positive (buys the top). GC 08:31 candle 36/36 cells lose. | Dead |
| Order flow / Level 2 / tape direction | Pre-open delta picks the better leg 50.5 %. Big order 0/28. Book imbalance 12 tests at break-even. L2 pilot 0/14 beat shuffled nulls. Absorption argmax OOS -$1,083 (t -0.02). 29 entry-time features with abs(corr) ≤ 0.045, AUC 0.49. L2 filters 0-1 of 27 positive. | Dead: "Level 2 says when, not which way" |
| Chart indicators as direction | 52-indicator study: every edge within ±0.5 tick, except the 15-min opening range (+1.3..+8 ticks) | Dead as signals |
| Zones (premium / discount, OTE, fib pocket) | 8 definitions within ±2 SE of 50 %; trade grids -0.03..-0.19R | Dead |
| 09:30 first-candle direction at a tight (candle) stop | candle930 0/40 cells at 1:1. 15 s candle 12/12 lose. 09:31 15 s candle (t 2.75 build) failed unseen, -$13.6k. 09:30 long held to 11:00: -$78 a trade. | Dead |
| Overnight drift / fade | London drift long PF 1.08 unseen. Following the overnight move PF 0.71-0.82. Fading it, unseen PF 0.87. | Dead |
| Look-ahead casualties | nq_asia_liq_sweep (88.8 % win, PF 4.5 = read the future range). Δ divergence mark (hindsight). The owner's marked FVG pullbacks (hindsight). | Void |

### 2.2 Dimensions that fail everywhere

| Dimension | Evidence |
|---|---|
| **ES, GC bar rules, YM, RTY, CL** | ES: 121 maps, mean 24 % green, 1 of 83 distinct maps passes 60 %, none reaches $75. GC: 117 maps, **0 floor boxes in 16,848 cells**. Taught: ES 0/24, GC 0/6. Candle break on ES / GC: 26/26 lose. **Both current leaders fail on ES and GC (Batch 3).** Exceptions: GC release brackets (scalp, T2a\* / T2b). |
| **London 02:00-09:25, Asia, evening** | Pipeline London 0 of 15 maps (0 floor boxes in 2,160 cells); Asia 0 of 7. 200+-trade cells: London 10 %, Asia 26 %, evening 32 % green. 12 London blueprint cards fail round 1. 18:00 candle unseen -$21.5k. About 135 evening variants, none lockable. Exception: the 03:00 candle (T2b). |
| **Pre-market outside the 08:30 first seconds** | 08:30 range break 1.4 % of boxes; pre ORB release 12 %; pre straddle release 13 % |
| **Fixed stops ≤ 20 pt, wick / 1-5m candle stops** | pts10: 21 % green / 1 % at floor; pts20: 37 % / 4 %. Wick stops rank 7.0 of 9. 09:31 candle 25-33 pt stop -$49k..-$85k vs 100 pt +$190k. fvg_odir stops under 20 pt: -$30 unseen. disp_oside candle stops: 1 % positive. 1× 1m-ATR on 15m FVGs: $1. |
| **Short-only NQ** | 31 % of cells green, median -$12. pm short 0/8, mid short 0/10. noise nyam short unseen -$22. Conti short unseen -$59. |
| **Buying frequency by widening a window** | Displacement k1.0: 10:00-11:00 $90 → 10:00-15:00 $19. JJ momentum all day: 4.7 a day, $25 (walk-forward fail); 11.7 a day, $4. |
| **Day filters** (quiet / gap / release-day) | Lifted build days, then failed 6 of 6 hold-out reads |
| **Side filters on breakouts** (VWAP, EMA50) | ORB $38 → $31 / $30. 08:30 break +$15.2k → -$2.7k / -$40.7k |
| **Daily caps, breakeven, trailing** | Take caps destroyed straddle edges. Breakeven: JJ wins went 39 % → 27 %. Trail collapses pdsweep. Noise midday BE + trail: -$5.7k vs plain +$77k. |
| **0.5R "70 % win" designs** | Random entries win 64-66 % at 0.5R. All 4 picked 0.5R / 70 % boxes went flat or negative unseen. |

### 2.3 Looks dead in one store, but is not settled (do not bury on status)

- **Stage-1 stops.** 154 of the pipeline's 175 stage-1 stops were the retired 40 %-eval-odds SIZE gate, not "no edge". 41 stage-1 near misses had 60 % or more of their boxes green. Use floor boxes and the average variant.
- **FVG entries are not dead once a side gate, a narrow window or a wide stop is added:**
  - fvg_oside: $98-121 (T3a)
  - nq_fvg15_bounce_late: $110 (T4)
  - nq_am_fvg15_gap (no side gate, 2 × ATR(5m) stop): about $95 per NQ unseen (T2b)
  - fvg_latest: $92, but only on the "open" stop table
- **Wide clock straddles.** 09:30 wide cells average $70.3 (T4). straddle-tf30 nyam / pm were raw-positive in both periods (vault_project_notes #51). Only tight brackets are dead.
- **tod_drift.** The prop-pilot walk-forward tod_drift-5m-mid made +$19.7k; the old library's pm long was 26 % green in 2024. Unsettled.
- **Candles as taught vs the standard table.**
  - open_candle / win_candle / orb_close are "0 of n" in the pipeline's standard table.
  - As taught (30 pt / 3R held to the clock), the 03:00 candle held unseen.
  - The verdict depends on the exit table.

---

## 3. Combination lessons by axis

Base: pipeline NQ heat-map cells with 200+ trades.
- CLAUDE_NOTES A: 48,805 cells in 363 maps.
- synth_combinations: 42,517 "plain" cells in 318 maps. The two agree within 4 points on every axis.
- Taught lane: 206 NQ centre cells.
- Read "lift" against random_baseline.csv.

### 3.1 Entry type

| Entry | Pipeline share profitable / at floor / median $ | Taught centre cells profitable |
|---|---|---|
| Continuation (break / follow / cross) | 0.47 / 0.110 / -$3 | 0.70 (17 at floor) |
| With-trend pullback (limit) | 0.42 / 0.093 / -$5 | 0.77 |
| Bracket / clock | 0.30 / 0.027 / -$10 | n/a |
| Fade | **0.24 / 0.031 / -$16** | **0.09** (0 at floor) |

**Same trigger, opposite direction** (the cleanest controls in the store):

| Pair | Follow | Fade |
|---|---|---|
| nq_displace_nyam | 78.5 % of boxes, $54.5 | 4.2 %, -$49.9 |
| NY OR | close $24 | fade -$37 |
| 15m candle | break $50 | sweep -$10..-$36 |
| Open side | open-side FVG $98 | disp_oside 52/52 lose |

### 3.2 Session

| Session | Share profitable / at floor / median trades a day (CLAUDE_NOTES) | Random-pool lift | Unseen survivors |
|---|---|---|---|
| pm 13:30-16:00 | 0.50 / 0.11 / 0.87 | **3.5-5.5×** (random pm 5m: 8-13 % green, 0 floor boxes) | 15:00 day move (T2a); noise pm long (sign only) |
| mid 11:00-13:30 | 0.45 / 0.11 / 0.92 | **2.2-2.6×** (random mid 5m: 15-18 %, 2-4 boxes) | noise midday (retired T1); vault break (T2b) |
| nyam 09:30-11:00 | 0.43 / 0.10 / 0.93 | **none on 1m/5m** (random nyam 5m: c1 30 % / 22 boxes, c1o 51 % / 101); lift on 15m/30m | onr_orb (T2b); everything 1m/5m failed (range_break -$28, ib_break -$33, orb_rvol -$73, value_reclaim ×2) |
| pre 08:30 | 0.44 / 0.10 / 0.55 | weak (the release burst) | GC NFP / CPI only |
| eve | 0.32 / 0.02 / 1.0 | weak | none (20:00 = sign flip) |
| asia | 0.26 / 0.01 / 1.2 | share only | none |
| london | **0.10 / 0.00** / 1.5 | none | 03:00 candle only |

**Read:**
- A green NY-morning 1m/5m map is the market's own drift.
- Midday, afternoon and 15m/30m bars are where real maps beat random by a wide margin.
- Every taught-lane winner sits between 09:30 and 15:30.

### 3.3 Bar size (corrected: the evidence is within each family, not pooled)

**Pooled numbers mislead:**
- Pipeline share profitable / at floor: 30m 0.77 / 0.31 (only 3-4 maps); 15m 0.44 / 0.17; **5m 0.49 / 0.13**; 1m 0.36 / 0.06. On the pooled share, 15m is not better than 5m.
- The taught-lane split (15m 73 % vs 5m 25 % vs 1m 14 %) is confounded by family: losing fade sheets dominate 1m and 5m.

**Within-family evidence (the real read):**

| Family | 15m | Other bars |
|---|---|---|
| fvg_oside | $98 | 30m -$9 (1/10 lines); 5m $14-19 at best, "loses every target" per vault_project_notes #21 (a conflict) |
| Displacement (all day, k1.5) | $117 | 5m -$15 (1/10); Lab: tf15 median $22 µ, tf3 $11 µ, tf1 $0.7 µ, tf5 -$2 µ |
| Candle sweep (EMA50) | $43 | 30m $51; 5m -$31 |
| noise_gx_mid_long (map averages) | $41 | 1m $39, 5m $32, 30m $41.5. Bar size does NOT lift the average. |
| value_reclaim | n/a | 5m 89.6 % green; 1m 44 % |
| gap fill | n/a | 1m 95.8 % green; 5m 21 % |

**Rule:** a result that lives on one bar size is fragile. Both current leaders live on 15m only.

### 3.4 Side

| Side | Share profitable / at floor / median $ |
|---|---|
| Long | **0.60 / 0.16 / +$8** |
| Both | 0.37 / 0.08 / -$9 |
| Short | 0.31 / 0.07 / -$12 |

- Mid and pm long: 0.59 / 0.62 profitable, vs short 0.29 / 0.24.
- Long-only build passes must be discounted for drift. The 2021-25 build days rose, and Conti long beat random longs 0 %.
- **Short-only failed every unseen read** (noise nyam short -$22, Conti short -$59).
- **With a day-context side gate, shorts contribute on build.** Taught short vs long net: displacement +$739k vs +$250k; fvg_oside +$466k vs +$343k; onr_orb +$203k vs +$126k.
  - Read this as DIRECTION ONLY: the sums add overlapping neighbour cells.
  - The displacement short share sits in 2022 and 2025-H1 (k2: 2025* +$37k).
- Owner rule: "both long and short must be profitable". That excludes the noise band, the vault break, owner_pm_first_bar_15 (short -$0.9k) and the 03:00 candle (body 0.7: short -$4.4k).

### 3.5 Stop

| Stop | Share profitable / at floor / median $ (CLAUDE_NOTES A) |
|---|---|
| atr3 | **0.55 / 0.26 / +$8** |
| pts45 | 0.56 / 0.18 / +$7 |
| pts30 | 0.50 / 0.08 / $0 |
| pct0.2 | 0.50 / 0.09 / $0 |
| atr1.5 | 0.42 / 0.11 / -$6 |
| pts20 | 0.37 / 0.04 / -$7 |
| pct0.1 | 0.31 / 0.02 / -$9 |
| pts10 | **0.21 / 0.01 / -$11** |

**Within family, the stop width decides the sign:**
- fvg_oside at 1R: 1× / 2× / 2.5× / 3× 1m-ATR / middle candle = $1 / $39 / $53 / $60 / $99.
- 09:31 candle: stop 100 / 50 / 33 / 25 pt = +$67k / +$108k / -$49k / -$85k.
- fvg_odir: stops under 20 pt -$1.8 build / -$30 unseen; 20 pt or more +$107 / +$66.
- 29,009 boxes: a 10-pt stop is 0 % at the floor; a 45-pt stop is 21 %.

**Structure is only width:**
- A wick stop is a tight stop (rank 7.0 of 9).
- A range-side stop vs a fixed stop of the same size wins 55 % (a coin flip).
- In the Lab, the displacement's far-extreme stop (cand2) has a median of $14.5 µ vs about $0 for ATR / cand / c15. The candle-range size matters.

### 3.6 Target (corrected: the rule is about POINTS, not R)

| Target | Share profitable / at floor / median $ / median win |
|---|---|
| None | **0.68 / 0.29 / +$29 / 20 %** |
| 3R | 0.50 / 0.13 / -$1 / 27 % |
| 2R | 0.44 / 0.09 / -$5 / 34 % |
| 1R | 0.35 / 0.04 / -$8 / 50 % |
| 0.75R | 0.32 / 0.03 / -$9 / 57 % |
| 0.5R | 0.28 / 0.01 / -$10 / 66 % |

- **No target is where random also earns** (drift). The random gate decides. No-target winners are fat-tailed: donch -$111k and displace -$129k without their best 5 % of trades.
- **Small R loses because it comes with a small stop.** The unseen holders used 0.53R (vault break: 75 / 40 pt), 0.5-0.75R (pdsweep, 2× ATR5m) and 0.75R (pm_day_move, fvg_oside walk-forward).
- **The floor fixes the target in points.** At 1R and 55 % wins, a $70 average needs about a 40-pt stop and target at $9 round trip (about 42 pt at $14). At 0.75R / 61 %: 44 / 58 pt. At 0.5R / 69 %: 56 / 113 pt.
- **Taught, structure stops:** 1R is the peak.
  - Displacement k1.5: 0.75R $88 / 1R $177 / 1.25R $140 (1R beats 0.75R in 12/12 pairs).
  - fvg_oside: 0.5R $52-54 < 0.75R $81 < 1R $99 > 1.25R $95.
  - Candle break at $500 risk: 1R $36.8 vs 0.5R $15.5.
- Win rate is exit geometry, not edge: random entries win 64-66 % at 0.5R; 1,521 of the 1,550 boxes with 68 %+ wins are 0.5R boxes.

### 3.7 Filters

**Trade-removing momentum, volume or level filters lift build numbers:**
- ORB $38 → level clear $89, rvol $50, ADX $49, tape speed $45
- newest FVG $92 → low volatility $144
- open-side FVG: gap 0 → 0.1 → 0.25 ATR = $98 → $108 → $121 (monotone, 10/10 lines each)

None was read unseen.

**Side and direction filters hurt:**
- ORB EMA50 side $30, VWAP side $31
- FVG trend-with $70 (vs $92)
- delta-with $26 (vs $32)
- 08:30 break with the 16:00 VWAP side -$2.7k / -$40.7k (vs +$15.2k)
- Hurst + autocorr -$81 (vs +$22)

**Day filters** (quiet, gap, release-day) failed 6 of 6 hold-out reads. **Regime splits** (ADX / RVOL / RSI / ATR) on the straddle: 48 of 48 build cells negative.

**Simplicity ladder:**

| Rung | FIT PF | CHECK PF |
|---|---|---|
| R0 (entry only) | 0.96 | 0.97 |
| R1 (+1 lever) | 1.06 | 0.99 |
| R2 (+2 levers) | 1.32 | 0.96 |

Three filtered round-2 locks collapsed out of sample: PF 1.27 → 0.74, 1.42 → 0.68, 1.22 → 0.81.

**The one gate that recurs among winners** is a day-context SIDE gate built into the trigger:
- side of the 09:30 open (fvg_oside)
- overnight-range third (onr_orb)
- VWAP from 01:00 (noise band / vault break)

The 09:30-10:00 direction gate (fvg_odir) failed its walk-forward.

**EMA20 on the 15m displacement:**
- All day at k1.5: +$15 a trade and +13 points of months won ($102 → $117; 57 → 70 %).
- At 10:00-11:00 in the Lab it adds nothing: use_ema=1 $26.3 µ on 569 trades vs use_ema=0 $25.6 µ on 612.
- EMA50 barely fires (157 trades, 4/10 lines).
- It is a rolling indicator the owner has not cleared ("only real indicators").

### 3.8 Market

- **NQ only.** ES plain cells: 0.22 profitable, 165 floor cells in 12,800. GC: 0.19 profitable, **0 floor cells**.
- **Red flag, not a building block.** Every NQ build edge later tested unseen that also lost on ES / GC / YM failed: 09:31 candle, candle break, FVG trend fade, AM VWAP pullback, orb_rvol (vault_findings_b pattern).
- **The leaders fail ES and GC:**

  | Leader | ES | GC |
  |---|---|---|
  | open-side FVG | $4 (4/10 lines) | -$19 (1/10) |
  | displacement | -$27 (1/10) | $1 (3/10) |

- The only idea whose ES and GC neighbour maps were both profitable is the noise band (nq_noise_gx_mid_long_slow). That is also the family of the one retired-T1 pass.

---

## 4. Frequency: what reaches 1-2+ a day, and what it costs

### 4.1 What frequency costs (pipeline, 46,113 distinct NQ cells with 200+ trades; synth_frequency_simplicity §3)

| Trades a day | Profitable | At floor | Median $ | With a target, at floor |
|---|---|---|---|---|
| < 0.5 | 50 % | 16.4 % | $0 | 11.9 % |
| 0.5-0.8 | 51 % | 13.8 % | +$1 | 8.9 % |
| 0.8-1.0 | 43 % | 6.7 % | -$5 | 2.4 % |
| 1.0-1.2 | 41 % | 5.6 % | -$6 | 2.6 % |
| 1.2-1.5 | 36 % | 3.3 % | -$7 | 1.3 % |
| 1.5-2 | 29 % | 2.1 % | -$11 | 0.7 % |
| 2-3 | 16 % | 0.5 % | -$12 | **0.0 %** |
| > 3 | 7 % | 0 % | -$13 | 0 % |

**Cells at 0.9 a day or more with an avg of $70 or more:** 1,155 cells in 126 maps / 90 ideas, almost all NO-target.
- Top stop × target: atr3-none 156, pts45-none 142, pts30-none 122.
- At 1.5 a day or more: 107 floor cells, mostly 1m nyam no-target (channel_fast, fvg_latest, vwap_cross: $78-96).
- But random 1m nyam pools reach p95 $48 and best $109: that is mostly drift.

### 4.2 Everything at about 1 a day or more, ranked by honest number

| Rule | Trades a day | Avg $ | Tier | Note |
|---|---|---|---|---|
| **fvg_oside middle candle, gap ≥ 0.25, cap 2** | 1.07 | $121 ($103 avg of 3) | T3a | spent |
| **fvg_oside middle candle, gap ≥ 0.1, cap 2** | 1.34 | $108 ($94) | T3a | spent |
| **fvg_oside middle candle, cap 2** | 1.48 | $98 ($90) | T3a | spent |
| fvg_oside middle candle, cap 3 / none | 1.64 / 1.66 | $87 / $86 | T3a | trade 3 is worth about -$11 |
| **Stack: fvg_oside gap 0.1 cap 2 + displacement all-day k1.5 (one at a time)** | 2.24 | $112, PF 1.22, Sharpe 1.71, net / daily DD 8.0, 72 % of months, every year positive (2023 +$10.9k), daily corr 0.40 | T3 (build) | the displacement leg's extra trades are worth about $0; 2 triggers |
| VWAP persistence N=20 | 2.2 | $81 | T4 | family burned |
| candle930 5m onr stop 1R | 1.0 | $110 | T4 | long drift, t 1.06 |
| nq930 wide straddle | 1.0 | $70.3 | T4 | about 40 % random drift |
| nq_am_fvg15_gap | 1.37 | about $73 per NQ build / about $95 unseen | T2b | PF 1.16 |
| nq_am_daymove_quiet | 0.97 | about $130 / about $87 unseen | T2b | PF 1.14; day filter |
| nq_displace_nyam 5m | 0.91-0.99 | map $54 / box $157 | T3b | fat tail |
| cl_disp15 all day k1.5 | 0.91 | $117 ($90) | T3b | PF 1.17; added trades about $0 |
| owner_jj_cont_15m | 0.99 | $70 | T4 / T2b | random 92.6 %; blind -$726 |
| owner_pm_first_bar_15 | 0.98 | $40 (9-cell $43) | T3b | long-only; old library: no beat over random |
| fvg_oside 3× ATR, no cap | 1.75 | $59 | T2b | under floor |
| owner_fvg_odir_15_nl_new | 1.24 | $78 | T2b | family walk-forward failed: closed |
| conti_day_long | 2.0 | $62 | T5 | drift |
| owner_candle_break_15 nocap | 2.28 | $50 | T2b | failed its read |
| conti_day_both | 2.96 | $47 | — | unseen -$19 |
| owner_jj_mom_allday_50_76 | 4.72 | $25 | — | walk-forward -$30 |
| owner_vwap_pullback_c15 | 3.07 | $16 | T3b | |

### 4.3 Honest routes to 1-2+ a day (and their price)

**A. Lift the cap only while the extra trade is still positive.**
- fvg_oside, middle candle 1R:

  | Cap | Trades | Avg |
  |---|---|---|
  | 1 | 887 | $99 |
  | 2 | 1,400 | $98 |
  | 3 | 1,557 | $87 |
  | none | 1,575 | $86 |

  Trade 2 adds about 513 trades worth about +$96 each. Trade 3 adds about 157 trades worth about -$11 each (from rounded averages). **Cap at 2.**
- Counter-case: on the candle break, trade 2 was +$100 on build and **-$103 unseen**.
- **Before choosing a cap, pre-register the trade-number split by year on build days.** That split is not stored for fvg_oside.

**B. Make the trigger stricter; never widen the window.**
- Displacement k 1.0 / 1.5 / 2.0: $90 / $177 / $219 at 10:00-11:00, vs $19 / $117 / $154 at 10:00-15:00.
- The added trades are worth about -$48 / $0 / -$33.

**C. Raise the size threshold for dollars, accept fewer trades.**
- fvg_oside gap 0 / 0.1 / 0.25: 1.48 / 1.34 / 1.07 a day at $98 / $108 / $121.
- Displacement k ladder: $19 → $154 as trades fall from 1.71 to 0.48 a day.

**D. Stack 2-3 one-trigger rules in different hours, one position at a time.**
- The one measured stack: 2.24 a day, $112 (the stack row in 4.2).
- Re-run it with the 10:00-11:00 displacement. Expected about 1.9 a day (1.34 + 0.60), but overlap and holding time are unmeasured.
- Cousins add about 0: the vault break and the noise midday correlate 0.65-0.71.
- The near-miss mix of 7 (in-sample): months won 72 % vs 50-65 % alone, Sharpe 1.59 vs about 1, daily correlation 0.23.

**E. A second session.** Only where the session stands alone on build days.
- The 13:45 first-bar follow is long-only, and the old library shows first_bar_mom did not beat random. It has no floor evidence.
- London, Asia and the evening add 0 floor cells at 0.8 a day or more.

### 4.4 Frequency traps (do not use)

- **Tighter stops.** 10 pt: 1 % of cells at the floor.
- **0.5R targets.** 0 of 7,221 configurations reach 65 % at 1 a day or more.
- **1m bars.** 1m cells at 1.2 a day or more: 1.4 % at the floor.
- **VWAP limit fades.** Rother: 4.3 a day, -$24.
- **1m FVG pullbacks.** 30 a day, -$2.5.
- **Morning no-target 1m cells.** These are drift.
- **The 3:1 walk-forward also needs frequency.** 1-a-day rules reached only 175-185 walk-forward trades and failed P6.4 (200). A rule needs about 1 a day or more on build to pass later.

### 4.5 Cost-model warning

The routes disagree on the cost of a round trip:
- NEW_RUNS and the taught lane: $4 RT + 1 tick, about $9.
- The pipeline's random entries lose $13-14.5 a trade, which equals its cost.
- The stop studies use $14 RT.

If the taught engine really costs about $14, every "cost room" figure falls by about a third, and the 1R floor needs about 42 pt, not 40. The fvg_oside cap 2 survives +2 ticks ($88) in synth_frequency_simplicity's arithmetic. The thin rules do not:

| Rule | Dies at costs × |
|---|---|
| pm_first_bar | 5.4 |
| jj_mom | 3.8 |
| vwap_pullback_c15 | 2.8 |

---

## 5. The owner's standing rules for a build (quoted from the vault)

### 5.1 Simplicity

| Rule | Source |
|---|---|
| "less is more when it comes to strategies and how many filters or rules": one trigger, a stop, a target, a session exit, max trades; at most 1-2 filters, and only if they beat the plain version out of sample | feedback-fewer-rules, 2026-09-30 |
| "remember the simple the better when it comes to overfitting, the edge must make sense": write the reason in plain words BEFORE testing; between two similar candidates, the simpler wins | edge-must-make-sense, 2026-10-02 |
| "i want to only keep real solid indicators with real indications": anchored to a true swing, a session level, a traded price or a book fact; remove rather than tune | feedback-only-real-indicators, 2026-10-12 |
| Every tested strategy must draw its own indicators on the chart | feedback-strategies-must-draw-their-indicators |
| Test a video AS TAUGHT. "Optimize" means stops, targets and filters, never the entry rule or the size. Allow 5 counted rounds, each with a written reason: "some strategies need a bit more looking into before just testing it once and automatically saying its a flop" | feedback-rules-as-taught-and-mix; explore-before-dropping |

### 5.2 How to judge

| Rule | Source |
|---|---|
| "judge the average of all variants, never the best cell"; "a table where over 60 % of the variants (cells) are profitable"; the pick is the MIDDLE passing box | strategy-blueprint; feedback-metrics-per-year-then-combined |
| "both long and short must be profitable"; "200 for everything" (trades); "75/25 like the course" | strategy-blueprint-owner-answers |
| "we could have a good strategy under our nose and lose it because we picked the wrong box"; "build what ever we need and dont have ... so we dont have to worry about missing a strategy under our nose" | strategy-pipeline, 2026-10-09 |

**Pass bars:**
- Average trade at least NQ $70 / ES $75 / GC $140 after costs.
- Beats 95 % of random-entry tables (97.5-99 % on tries 2-5).
- 200+ trades.
- PF ≥ 1.2.
- Net / worst DD ≥ 3.
- Sharpe ≥ 1: "i really like sharpe ... just like a sharpe on just 1".
- DD at 1 micro under $2,000.
- Monte Carlo: 75 % of 1,000 reshuffles.
- Test average at least half of the build average.

Source: strategy-blueprint and owner-answers point 13.

**One pipeline (2026-10-18):**
- "keep it to just overall metrics of the strategy ... then from there we can work on how we modify the risk or strategy to trade an eval or funded".
- Stop rule: win rate must be at least the breakeven of the REALIZED R:R + 3 points.
- Tags: Live / Live+Prop (Sharpe ≥ 1, 60 % of months won).
- "if one account gets blown that's fine as long as overall we are profitable".

**Report format:**
- Dollars, "1:X" notation.
- Per year THEN combined.
- Sharpe and realized R:R.
- "flat by 4pm".

### 5.3 Frequency and win rate

- "at least 1 trade/day, win rate 50 % minimum, all sessions fine" (2026-09-21)
- "just try to enforce the high trade frequency minimum once a day" (2026-10-13)
- "its okay if its below 1:1 ... higher winrate is better"
- The latest goal (2026-10-19): "lets follow the $1000 plan and perfectly execute it"; "find me the strategy/algos that fit the $1000 plan".
  - The plan is 40 % wins at 1:1.5 with very high frequency. That is break-even before sizing, and the jj_fair test of it FAILED.

### 5.4 Out-of-sample

- "dont touch the OOS, while we keep running new variants only run on OOS when i tell you" (2026-09-23)
- "dont run on out of sample days, until i say"
- OOS = the 3:1 BLOCK walk-forward over all data, on every route:
  - Blocks: Jan-Mar pick → Apr trade, and so on.
  - The pipeline's own pick. Never a single read.
  - "i thought it would just be jan-march in sample the april oos... i dont want to use rolling" (2026-10-18).
  - Rolling only on his word.
- Build days 2021-09-22..2025-06-30 are the window for the idea card, the heat map, the proof and the lock.
- Use the blueprint_* tools. Never write one-off test code for a strategy.

### 5.5 What he refuses or parks

- No payout pipeline unless he enables it.
- No "dead" verdicts: shelve with notes.
- No long reports: "simple minimal words".
- No reliance on scalping: profit from holds of 5 s or less must stay at or under 50 %.
- No AI touching an account.

### 5.6 What these rules exclude among the current leads

| Rule | Rules out |
|---|---|
| Both sides profitable | noise band, vault break, owner_pm_first_bar_15 (short -$0.9k), 03:00 candle (body 0.7 short -$4.4k) |
| 200+ trades | pdsweep (176), 03:00 body 0.7 (189), 20:00 candle (189); fvg15_bounce_late is borderline (216) |
| PF ≥ 1.2 | cl_disp15 all-day k1.5 (1.17), displacement 10-11 k1.0 (1.14), fvg_oside 3× ATR 1R (1.19), jj_cont_15m and pm_first_bar (1.15), am_fvg15_gap (1.16), conti_long (1.14), candle break (1.12) |
| DD at 1 µ < $2,000 | cl_disp15 all-day k1.5 (about $2.9k), displacement 10-11 k1.0 ($2.7k); fvg_oside middle candle and displacement 10-11 k1.5 are borderline ($1.8-1.9k) |
| No scalping | GC release brackets (89-95 % of profit in holds ≤ 5 s) |
| Only real indicators | EMA20 / VWMA20 (displacement), ADX > 20 (onr_orb), 1h EMA50 (sweep) are rolling indicators he has not cleared. The 09:30 open, the 01:00 open, the overnight range and the prior-session high / low are session levels and qualify. |
| Standard stop / target geometry | both leaders (structure stops; see Q1) |

---

## 6. Open questions the designer must settle (or ask the owner) before building

1. **Stops.**
   - Does "standard stop/target geometry" allow a structure stop (middle candle; displacement candle far extreme)?
   - If not, neither leader clears $70. The build starts from a NEW fixed-point (30/45 pt) open-side FVG sheet, of which none exists, or the 3× 1m-ATR version ($59).
2. **NQ-only.** Both leaders fail on ES and GC, and the vault says that failure came before every later unseen failure. Is the cross-market line a gate, or a flag?
3. **The honest number for a taught sheet.**
   - Is it the cell, the average of 3 targets, or the full 3×3 sheet?
     - Displacement k1.5: $177 cell vs $135 average of 3.
     - fvg_oside: $99 vs $92.
   - Is the floor judged in dollars at 1 NQ (which favours 80-pt stops at PF 1.14-1.16), or with PF ≥ 1.2 and an R floor too?
4. **The random control.**
   - Structure-stop rules have no matched random control (the fvg_odir walk-forward had P6.2 n/a).
   - Same-side random was never run for long-heavy rules (pm_first_bar is null; the noise band used both-sided pools).
   - The Conti sheets' control covers 09:30-11:00 only.
5. **How to read the block walk-forward when it comes.**
   - About 11 of its 15 traded months are build months the rule was designed on.
   - Pre-register the verdict on the post-2025-07 months only? That is about 4 months: 100-170 trades at 1-2 a day.
   - Which block alignment? The candle-break and fvg_oside walk-forwards traded Jan / May / Sep. The 03:00 walk-forwards traded Apr / Aug / Dec, from 2021-01-01, before the build start.
6. **Spent families.** For spent families (fvg_oside, the noise band, the vault break, onr_orb e1000, the candles, the candle break, nq930, VWAP), are forward days from 2026-10-17 the only OOS left?
7. **Engine and cost.**
   - $9 or about $14 a round trip?
   - The routes disagree on the same rule:
     - displacement: taught $177 vs Lab $263 per NQ
     - fvg_oside test months: lane about $60-67 vs Desk $2-33 per NQ
     - onr_orb: $93 vs $125 on the same window
8. **Freeze the code.** Store the code sha in every run. Re-run on one frozen version before ranking anything:
   - noise midday (+$77k to -$5.7k with identical inputs)
   - displacement Lab ($9,884 vs $8,177)
   - 09:30 candle close (+$43.4k vs +$18.0k at qty 4)
9. **Limit entries.** fvg_oside needs limit entries, which the Desk cannot book (7 orders refused). Build limit orders, or test a market-at-close entry on build days first?
10. **Long-only rules.** Does "both long and short must be profitable" rule out the noise band, the vault break and the 13:45 first bar? Or is a long-only rule allowed if it beats a same-side random control?
11. **Rolling gates.**
    - Do EMA20, VWMA and ADX count as "real indicators"?
    - If not, the displacement keeps its k-only form: no-gate all-day k1.5 is $102, 7/10 lines, 57 % of months.
    - The 09:30-open side is a session-level alternative gate. Untested on the displacement.
12. **One rule or a stack?**
    - Does "one entry trigger" allow stacking 2-3 one-trigger rules to reach 1-2 a day?
    - If yes, re-run the NEW_RUNS stack with the 10:00-11:00 displacement, not the all-day k1.5. Check overlap and holding time.
13. **The daily cap.**
    - Run the trade-number split (trade 1 vs 2 vs 3, by year) on build days before picking a cap.
    - The fvg_oside "trade 2 ≈ +$96, trade 3 ≈ -$11" comes from rounded averages.
    - The candle break's trade 2 flipped unseen.
14. **The gap knob.** min_gap 0 / 0.1 / 0.25 trades frequency for dollars: 1.48 / 1.34 / 1.07 a day at $98 / $108 / $121. Pick by the owner's frequency rule before any OOS, and judge the three as a set (about $109).
15. **2023.** Every fvg_oside version loses in 2023 (-$1k to -$12k) and lives on 2022 and 2025-H1. Does "metrics per year" accept a losing build year?
16. **The luck count.** The side-of-open gate won and the 09:30-10:00 direction gate failed its walk-forward. Was "open side" chosen after seeing fvg_odir? Count that look, plus about 41 fvg_oside and 36+ displacement sheets, in the luck bar.
17. **Units in the round-2 locks.** Re-run nq_am_fvg15_gap and nq_am_daymove_quiet at 1 NQ on build days before calling them fee-level. Should their 2 × ATR(5m) stops (median about 82 pt) be capped in points?
18. **Which noise band?** Settle the anchor (18:00 vs 01:00), the window (to 13:24, 13:30 or 15:30) and the exit (session end vs 15:58) before any rebuild.
19. **nq_onr_break_a15.** Fix the window bug (15,696 of 54,720 trades outside nyam) and rerun. It is the biggest standard-table map in the store ($144 average variant) and the standard-geometry twin of onr_orb.
20. **Unread stores.** Every limit above is understated by these:
    - runs_test/ (70 stores of per-idea random controls and unseen tables)
    - stages_old (183 older judgings of 161 ideas)
    - runs_old_code_6d21 and runs_old_hash
    - book_before snapshots and portfolios/
    - out/judge/year_reads.csv
    - the stop-study and candle930 scratch outputs
    - the JJ batch-6 walk-forward (pending)
    - about 60 Lab scripts whose runs were pruned on 10-17

---

## 7. The short list: most promising SIMPLE directions for the designer

All of these are build days only. Each is one trigger with at most one filter. The 3:1 block walk-forward waits for the owner's word. Ranked by fit to the owner's goal: simple, 1-2+ trades a day, evidence.

| # | Direction (entry · session · bar · side · stop · target · ≤1 filter) | Trades a day | Avg $ in the stores | Tier | The one risk |
|---|---|---|---|---|---|
| 1 | **Open-side 15m FVG:** limit at the near edge of the newest 15m FVG, long above the 09:30 open / short below · 09:30-15:00, flat 15:55 · 15m · both · middle-candle stop (about 38 pt) · 1R · cap 2, one at a time · filter: gap ≥ 0.1 ATR | 1.34 (1.48 with no gap filter) | $108 cell / $94 avg of 3 (no filter: $98 / $90); PF 1.30; Sharpe 2.07; 10/10 | T3a | The structure stop is taught-route only. The family's unseen months are spent (3 reads). It fails on ES / GC / 5m / 30m. |
| 2 | **Open-side 15m FVG on the standard table:** same entry · fixed 30 / 45 pt stop (also atr3) · 1R, plus none / 3R for the map · cap 2 · no filter | expect 1.3-1.7 | **no evidence**. The nearest is the 3× 1m-ATR stop (about 33 pt): $59 at 1.75 a day | none (build it first) | It may land under the floor, as the ATR proxy did. |
| 3 | **15m displacement follow, morning:** a 15m candle with body ≥ 1.5 × ATR14, enter at its close in its direction · 10:00-11:00 · 15m · both · stop at the candle's far extreme · 1R · 1 a day · filter: EMA20 side (optional) | 0.60 (k 2.0: 0.36) | $177 cell / $135 avg of 3 (k 2.0: $219 / $166); PF 1.26; 100 % random; 10/10 | T3a, fully blind | Under 1 a day alone. EMA20 is a rolling indicator, and the Lab shows it adds nothing at 10-11. Code drift ($177 taught vs $263 Lab). |
| 4 | **15m displacement with the 09:30-open side as the gate** (replaces EMA20 with a session level) · 10:00-11:00 (or all day at k ≥ 1.5) · 15m · both · candle far-extreme stop · 1R | 0.6-1.0 | **no direct sheet**. Indirect: displacement WITH the open's side wins more, AGAINST loses (43 % at 1R; vault_findings_b #97). All day with no gate, k1.5: $102, 7/10 lines | none | Untested. It may only re-find the EMA20 trades. |
| 5 | **Stack #1 + #3, one position at a time** (two one-trigger rules in different hours) | about 1.9 expected (as run with the all-day displacement: 2.24) | as run: $112, PF 1.22, Sharpe 1.71, every build year positive (2023 +$10.9k), daily corr 0.40 | T3 (build) | The measured stack used the all-day displacement, whose extra trades are worth about $0. The owner may read a stack as two triggers. |
| 6 | **Overnight-third side + 15m opening-range close:** the 09:30 open in the top / bottom third of the 01:00-09:30 range picks the day's side; a 15m close beyond the 09:30-09:45 range on that side · 10:00 (or 10:30)-15:30 · 15m · one side a day · stop 30 % of ATR15 (about 109 pt) · 3R / flat 15:30 · filter: ADX > 20 as taught (drop it to stay at 1 filter?) | 0.38-0.40 | $409 / $484 (avg of 3: $383 / $458); PF 1.54 / 1.76 | T2b (e1000: kept half unseen) / T3a (e1030) | 0.4 a day. The random control covers 09:30-11:00 only. Its standard-table twin nq_onr_break_a15 ($144 average, 0.29 a day) needs the window-bug fix. |
| 7 | **15:00 day-move follow:** at 15:00 follow (last − prior close) when abs(move) ≥ 0.5 × prior range · 15:00, flat 15:58 · 1m decision · both · 2 × ATR(5m) stop · 0.75R · 1 a day | 0.43 | build $88, PF 1.28 → unseen $72, PF 1.20 (138 trades) | T2a | 0.43 a day. No random gate. Its twin lost longs and H2-2025. |
| 8 | **Midday noise-band long:** a 1m close above the 01:00 open + 0.3 × daily ATR14 AND above the VWAP from 01:00 · 11:00-13:30 · 1m · long · 30 pt · 3R · ≤ 3 a day | 0.74 | box $116; **map average $39**; unseen box $149 / average $88 | T1 (retired read only) | Long-only (owner: both sides). The map average fails the floor. Block walk-forward 89.5 %. Code drift. |
| 9 | **5m displacement follow, no target:** the first 5m bar of the morning with body ≥ k × ATR (k 1-2) · nyam, hold to the close · 5m · both · 20 pt or 0.2 % stop · no target | 0.91-0.99 | map average $54.5; box $157; 97.9 % random (try 2) | T3b, fully blind | Fat tail: 15 % wins, -$129k without its best 5 % of trades. ES and GC lose. |
| 10 | **09:30 5m candle follow with a wide stop:** at the 09:35 close go with the candle · nyam, flat 15:58 · 5m · both · stop at the far side of the 00:00-09:30 range (about 98 pt) · 1R | 1.0 | $110 (average of 20 variants, 18/20 green); t 1.06 | T4 | Long drift (+$48.1k long / +$4.1k short). No drift control. The 09:30-candle family's unseen days are already read (failed). |
| 11 | **Late-morning 15m FVG touch:** limit at the near edge of a 15m FVG ≥ 0.25 ATR · 10:00-11:00 · 15m · both · standard table (atr3 / pts45) · 3R or none | 0.16-0.23 | map average $110 (67 % green, 22 floor boxes) | T4 | Thin (216 trades in the best box); far under the frequency bar. |
| 12 | **09:30 wide straddle:** OCO ±15 pt at the 09:30 print · flat 15:55 · tick / 1m · both · 50-150 pt stop · 3R | 1.0 | wide-stop cells average $70.3 (picked o15 / s50 / r3: $122) | T4 | About 40 % of the result is random drift (random median +$47k). Monte Carlo 50 %. DD at 1 µ $2.8-8.1k. Family test days spent. |

**Reading the list:**
- Only #1, #2 and #5 can meet "1-2 trades a day" by themselves or as a pair.
- #3 and #4 are the only fully blind leads at the floor.
- Everything at 0.2-0.5 a day (#6, #7, #11) can only be a stack member.

**Before any OOS, run on build days:**
- #2: the standard-geometry open-side FVG.
- #4: the session-level gate on the displacement.
- The stack with the 10:00-11:00 displacement leg.
- The trade-number split by year.
- A same-side random control for every long-heavy rule.

---

## 8. Corrections applied (what this map changed vs the three syntheses)

1. **NEW_RUNS Batch 3 added.** The gap knob is monotone; the k ladder is monotone; EMA50 barely fires; both leaders fail ES and GC; the stack was already run. synth_frequency_simplicity's "no stack has been run" is false.
2. **NQ-only demoted** from "building block #1" to a red flag (vault_findings_b pattern; pipeline_maps #25 line 2.5).
3. **fvg_oside 3× ATR and owner_vwap_pullback_c15 taken out of T1.** A walk-forward that stitches about 11 build months is not an unseen read. fvg_oside 3× ATR → T2b. vwap_pullback_c15 → T3b / T5 with a contaminated walk-forward.
4. **GC 10:00 evC and gc_nfp_cpi** → T2b / T2a\*. Half their OOS is build days, they are scalps (89-95 % of profit in holds ≤ 5 s), and evC sits under the GC floor.
5. **nq_noise_gx_mid_long is "T1 under the retired single read only".** Its map average is $39, its random pools are both-sided, its block walk-forward beats 89.5 %, and its build number drifts with the code.
6. **T2a narrowed** to pm_day_move_1500, pdsweep\* and gc_nfp_cpi\*. Vault break, onr_orb e1000 and the 03:00 candle → T2b.
7. **Best-box rows moved to the map average:** nq_displace_nyam $54 (T3b); noise_gx_mid_long_slow $40-41 (T3b; not stronger than the 1m).
8. **cl_disp15 all-day k1.5 → T3b.** Its added trades are worth about $0; PF 1.17; DD about $2.9k at 1 µ.
9. **fvg_oside is "spent", not "partly spent".** The Desk port and the lane disagree on the test months (1R: about $2-8 per NQ vs about $67).
10. **nq930_bigprint is contaminated** (its in-sample months included test months).
11. **judas, o15 / s50 / r3, fair-price K3 and the pm_first_bar corner → T5** (honest averages $56, $70.3, n/a, $43).
12. **Micro-unit slips fixed.** nq_am_fvg15_gap and the round-2 locks kept about $87-119 per NQ unseen, but failed PF and halves. They are not "$7 fee-level". "The side gate is the whole FVG edge" holds in R (+0.04R → +0.13R), not in dollars (+$30).
13. **"Never ≤ 0.5R" replaced by a points rule.** A target of about 35-40 pt or more with a wide stop works; the vault break (0.53R), pdsweep (0.5-0.75R) and pm_day_move (0.75R) held unseen.
14. **The "15-minute bar" claim is restated within each family.** Pooled, 15m (0.43-0.44) is below 5m (0.49).
15. **Families with green neighbours moved out of "dead":** FVG with a side gate, wide clock straddles, tod_drift, VWAP persistence (untestable clean).
16. **Shorts with a side gate are read as direction only** (overlapping cells; concentrated in 2022 and 2025-H1).
17. **Three cautions added:** the cost-model mismatch ($9 vs $14 RT), the noise-band rule-text conflict, and the old library's "2025 unseen" being half build days.
18. **The owner's rules applied as filters on the list:** both sides, 200 trades, PF 1.2, DD at 1 µ, no scalping, only real indicators, standard geometry.
19. **First-bar follow (synth_frequency_simplicity Sketch 2 / 3) has no floor evidence.** The 9-cell average is $43, the old library beat random 31-50 %, and the 09:45 leg's blind months lost.

*Not checked here:* stages_old, runs_test/ and the pruned Lab runs (the inventory never read them). The micro-to-NQ conversions are ×10 plus about $6, not re-runs. Whether the taught engine costs $9 or $14 a round trip was not settled from code.
