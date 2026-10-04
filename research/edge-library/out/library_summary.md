# Edge library — admission summary (2026-10-04)

Plain words; dollars are 1 contract after costs unless said otherwise. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only), PICK = 2024.
**BUILD and PICK were both used to choose, so neither is proof. Forward (paper) trading is still needed. 2025+ (EXAM) was not read.**

## 1. What was tested
* 32 families, 279 runs, 33,984 menu variants (8 stops x 4 targets x each family setting) on NQ, ES, GC; 18,112 random / shuffled control variants.
* 1,623 judged units (family x bar size or clock time x session x market; long/short, break/fade, fill/go judged apart): NQ 528 + 81 Level-2 filter/exit variants, ES 507, GC 507.
* Heat map passes on BUILD (>= 60 % of variants positive, median positive): 213 units (NQ 128, ES 26, GC 20, Level-2 variants 39).
* Also beat matched random entries AND the best-of-random bar: **5 units**. Only these had 2024 opened (`out/admit/pick_reads.csv`).
* 2024 heat map passes for 3 of the 5. After stress and the trade-count rule: **2 admitted (1 clean, 1 flagged)**. The rest: `out/near_misses.md`.

## 2. Verdict by family and market (BUILD): units passing at 60 / 70 / 80 % of variants positive, of units judged
| family | NQ | ES | GC |
|---|---|---|---|
| bimb_follow_d1 | 1 / 1 / 0 of 7 | — | — |
| donchian | 6 / 5 / 4 of 27 | 3 / 2 / 0 of 27 | 2 / 0 / 0 of 27 |
| ema_pullback | 11 / 7 / 4 of 23 | 0 / 0 / 0 of 23 | 0 / 0 / 0 of 23 |
| ema_ribbon | 6 / 5 / 3 of 27 | 4 / 1 / 1 of 27 | 3 / 1 / 0 of 27 |
| first_bar_mom | 10 / 6 / 3 of 20 | 5 / 3 / 1 of 20 | 4 / 1 / 0 of 20 |
| flow_exhaust | 5 / 4 / 1 of 14 | — | — |
| gap | 4 / 2 / 0 of 8 | 0 / 0 / 0 of 8 | 3 / 2 / 0 of 8 |
| ib | 12 / 9 / 8 of 24 | 6 / 4 / 1 of 24 | 0 / 0 / 0 of 24 |
| lon_break | 4 / 4 / 1 of 4 | 0 / 0 / 0 of 4 | 0 / 0 / 0 of 4 |
| mid_fade | 0 / 0 / 0 of 4 | 0 / 0 / 0 of 4 | 0 / 0 / 0 of 4 |
| orb | 8 / 8 / 1 of 24 | 0 / 0 / 0 of 24 | 0 / 0 / 0 of 24 |
| pinbar | 2 / 0 / 0 of 28 | 1 / 1 / 0 of 28 | 0 / 0 / 0 of 28 |
| rsi2 | 3 / 3 / 2 of 28 | 1 / 1 / 1 of 28 | 0 / 0 / 0 of 28 |
| squeeze | 4 / 3 / 1 of 28 | 0 / 0 / 0 of 28 | 1 / 0 / 0 of 28 |
| straddle | 9 / 5 / 2 of 20 | 0 / 0 / 0 of 20 | 0 / 0 / 0 of 20 |
| straddle_t (9 clock times) | 4 / 2 / 2 of 9 | 0 / 0 / 0 of 9 | 0 / 0 / 0 of 9 |
| supertrend | 9 / 7 / 4 of 27 | 4 / 1 / 0 of 27 | 2 / 1 / 1 of 27 |
| sweep_rev | 6 / 4 / 3 of 28 | 0 / 0 / 0 of 28 | 1 / 0 / 0 of 28 |
| tema_slope | 6 / 4 / 3 of 27 | 0 / 0 / 0 of 27 | 0 / 0 / 0 of 27 |
| tod_drift | 4 / 3 / 0 of 52 | 0 / 0 / 0 of 52 | 0 / 0 / 0 of 52 |
| vwap_band | 5 / 4 / 2 of 26 | 0 / 0 / 0 of 26 | 1 / 1 / 0 of 26 |
| vwap_ema_x | 0 / 0 / 0 of 21 | 0 / 0 / 0 of 21 | 1 / 0 / 0 of 21 |
| vwap_flip | 4 / 4 / 1 of 26 | 0 / 0 / 0 of 26 | 2 / 1 / 0 of 26 |
| vwap_z | 5 / 3 / 1 of 26 | 2 / 0 / 0 of 26 | 0 / 0 / 0 of 26 |

By session (same counts): **eve** NQ 19/19/13 of 63, ES 3/1/1, GC 0/0/0; **asia** NQ 4/2/1 of 58, ES 2/0/0, GC 1/0/0; **london** NQ 9/4/1 of 74, ES 0/0/0, GC 0/0/0; **pre** NQ 21/16/5 of 71, ES 0/0/0, GC 4/3/0; **nyam** NQ 30/20/5 of 92, ES 2/1/1, GC 6/2/0; **mid** NQ 17/10/8 of 87, ES 9/4/0, GC 6/2/1; **pm** NQ 28/22/13 of 83, ES 10/7/2, GC 3/0/0.
A heat-map pass alone is weak on NQ: random entries pass it too (section 7). mid_fade and vwap_ema_x pass nowhere that counts.

## 3. Admitted members (NQ only; both families are a SECOND look for the EXAM: their old favourites already saw 2025-26)
| member (default variant) | 2021* | 2022 | 2023 | 2024 | combined | trades | win | PF | max drawdown | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| orb_NQ_tf1_pre (`or_min5_atr1p5-r2`) | -$840 | $9,878 | $7,324 | $12,437 | $28,799 | 819 | 41 % | 1.32 | $3,300 | 1.89 |
| donchian_NQ_tf30_nyam (`n10_pct0p2-r2`) | $6,093 | $27,595 | -$4,700 | $16,974 | $45,962 | 647 | 38 % | 1.18 | $10,150 | 1.06 |

**orb_NQ_tf1_pre — ADMITTED.** Reason written first: the first minutes of a session set a range; a break of either side traps the other side and carries. In practice: range of 08:25-08:30 ET, stop orders on both sides (76 % of entries fall in the 08:30 minute = US data time), stop 1.5 x one-minute ATR (about 8 points), target 2 x the stop, about one trade a day (0.99), median hold 2 minutes. Complexity 3.
* Heat map: BUILD 72 % of 96 variants positive (median $16,118); 2024 64 % (median $5,254). Surviving set: 49 variants positive in both periods and under stress.
* Lift over matched random entries: +$26,479 on BUILD, +$17,612 in 2024; beats 100 % of 200 random draws in both. BUILD t 2.32 against a bar of 2.02.
* Stress (2 ticks + 250 ms): BUILD $16,362 -> $8,462; 2024 $12,437 -> $6,572. Half the profit goes: the average trade is only $35 (7 ticks).
* Worst open loss on one trade: $1,110 per contract = $112 per micro -> at most 17 micros inside $2,000 (43 at the 99th percentile). At about $1,000 risk a trade: $118,252 combined, Sharpe 1.51.
* Cautions: 145 trades (18 %) open and close within 2 seconds and earn $18,020 of the $28,799 (63 %): data-release spikes, where simulated fills are least trustworthy. 2021* is negative; shorts earn $22,352; the pre-market session cannot be run in the Strategy Tester.

**donchian_NQ_tf30_nyam — ADMITTED, FLAGGED (weak; the checker should confirm or demote it).** Reason written first: a close beyond the recent range traps the other side (trend continuation). In practice: at the 10:00 or 10:30 close of a 30-minute bar beyond the prior 10-bar channel, enter with it; stop 0.20 % of price (about 30 points), target 2 x; 0.78 trades a day. Complexity 3.
* Heat map: BUILD 95 % of 64 variants positive (median $28,875); 2024 90 % (median $11,147). Surviving set: 43 variants.
* FLAG 1: the BUILD central variant (`n10_pts20-r2`, t 2.19 against a bar of 2.02) loses $2,113 in 2024 under stress, so the default moved to the nearest surviving variant, whose own BUILD t is 1.65: below the bar. The library's own admission check on that variant says REJECT; it is admitted only by the rule this stage wrote down before any number was opened.
* FLAG 2: random entries with the same exits in the same session also made money (+$20,204 BUILD, +$10,998 in 2024). The signal adds $8,784 and $5,976 and beats only 86 % and 76 % of random draws: most of this profit is the NQ morning itself, not the breakout.
* FLAG 3: all the profit is from shorts (+$47,084; longs -$1,122) and 2023 lost $4,700.
* Stress: BUILD $28,988 -> $15,855; 2024 $16,974 -> $9,364. Worst open loss on one trade $890 per contract = $90 per micro -> at most 22 micros inside $2,000. At about $1,000 risk a trade: $67,408 combined, Sharpe 0.96.

## 4. Straddle at a clock time (BUILD): share of the 160 variants positive · median variant net
| time ET | NQ | ES | GC |
|---|---|---|---|
| 18:00 | 84 % · $13,127 · PASS 60/70/80 | 45 % · -$1,816 | 15 % · -$7,971 |
| 20:00 | 11 % · -$15,859 | 0 % · -$29,848 | 33 % · -$4,166 |
| 00:00 (weak reason) | 43 % · -$1,454 | 7 % · -$9,662 | 36 % · -$3,287 |
| 02:00 | 36 % · -$4,483 | 5 % · -$17,123 | 2 % · -$18,707 |
| 03:00 | 69 % · $8,584 · PASS 60 | 6 % · -$17,611 | 5 % · -$15,231 |
| 08:30 | 92 % · $35,920 · PASS 60/70/80 | 36 % · -$6,378 | 39 % · -$2,478 |
| 09:30 | 54 % · $5,420 | 28 % · -$12,434 | 14 % · -$8,748 |
| 11:05 (weak reason) | 60 % · $5,598 · PASS 60 | 29 % · -$12,910 | 20 % · -$5,510 |
| 13:30 | 56 % · $2,124 | 42 % · -$2,165 | 16 % · -$8,282 |
NQ passes the heat map at 18:00, 03:00, 08:30 (and 11:05 at exactly 60 %), but no time beats the same straddle fired at a random minute by enough (central t 0.56 / 0.89 / 1.67 against a bar of 2.62; 11:05 loses to random minutes by $40,188). ES and GC: no time passes. None admitted; NQ 08:30 and 18:00 go to the DEEPEN round.

## 5. VWAP-EMA cross (user's idea, weak prior)
63 units (21 per market). None passes on NQ or ES. One passes the heat map on GC (15-minute bars, midday: 67 % positive, median $1,856) but it loses to random entries by $2,291 (beats 25 % of draws) and its t is 0.44. Typical share of positive variants: NQ 40 %, ES 14 %, GC 15 %. No edge found; it goes to the DEEPEN round, not the library.

## 6. What Level 2 added (NQ)
* As a strategy: book-imbalance follow passes the heat map in 1 of 7 sessions and flow exhaustion in 5 of 14, but no central variant beats the random or shuffled-book bars (best t 1.88 against 2.02 and 2.65) and two lose to the shuffled book.
* As a filter or exit on breakouts that passed BUILD (27 unit-sessions each), against the same strategy without it on the same days, median change per variant: -$11,683 (skip when the book opposes; keeps 40 % of trades), -$10,445 (trade only into a thin book; keeps 16 %), -$8,835 (exit on a book flip). The change was positive in 0, 1 and 0 of 27, and in 0 of 81 did it beat the shuffled-book version (the real book beat the shuffled one in 37-47 % of variants). Only two shuffles per unit: a thin null.
* The shuffled-book versions passed the heat map more often (79 of 130) than the real ones (39 of 81). At the trade's moment the book added nothing and removed profit.

## 7. Multiple-testing honesty
* 1,623 units were judged. Random controls judged by the same heat-map rule pass on NQ in 6 of 56 cases (random entries) and 5 of 18 (random-minute straddles); on ES and GC in 0 of 56 and 0 of 18. So about 58 of NQ's 128 heat-map passes are what random entries alone would give.
* Second gate (central variant above the 95th percentile of the best random variant): 0 of 168 random units pass both gates; 5 of 1,623 real units do (0.3 %). 168 nulls cannot rule out a chance rate that small, so the BUILD gate alone is not proof. 2024 removed 2 of the 5 and the trade-count rule 1 more.
* The units are not independent: orb on 15- and 30-minute bars is the same trades in 72 of 96 variants; the pre-market orb and the 08:30 straddle (92 % of variants positive on NQ, t 1.67, below its bar) are one idea tested twice; orb pre passes the heat map on all four bar sizes and donchian morning on three, but only one bar size of each clears the bar.
* Both members exist on NQ only: orb pre is negative on ES and GC (16-41 % of variants positive) and the donchian morning does not pass there (ES 30-minute: 59 %).
* Bookkeeping: 33,984 candidate variants of the 40,000 cap (unchanged). The 2024 and stress re-runs (1,144 variants) re-test variants already counted and are booked as control cells; 12 member runs of the 2,000 cap. The orchestrator may re-book them.

## 8. Loss-day overlap of the two members (default variants)
| share of the row's losing days that are also losing days of -> | orb_NQ_tf1_pre | donchian_NQ_tf30_nyam |
|---|---|---|
| orb_NQ_tf1_pre (loses on 55 % of 2024 days) | - | 38 % in 2024 · 40 % over 2021-24 |
| donchian_NQ_tf30_nyam (loses on 37 % of 2024 days) | 57 % in 2024 · 58 % over 2021-24 | - |
Each overlap equals the other member's ordinary losing-day rate: losing days do not cluster. Daily net correlation -0.07.

## 9. Open risks
1. One clean member is not a library. donchian_NQ_tf30_nyam is admitted on a pre-written rule but fails the library's own check on its default variant; treat it as a near miss until the checker rules.
2. orb_NQ_tf1_pre lives on a 7-tick average trade, and 63 % of its profit is made inside 2 seconds in the 08:30 data minute; live fills decide it. Paper-trade it before any account uses it.
3. Evening, pre-market and "hold to 15:58" runs have no Strategy Tester equivalent; their proof is the engine's own tests.
4. 208 units pass the BUILD heat map without admission; their 2024 is unread and clean for the DEEPEN round (`out/near_misses.md`).

## CHECKER CORRECTIONS (2026-10-04, out/check_admit/) — these override the text above
1. donchian_NQ_tf30_nyam is DEMOTED (members/_demoted/). The library has ONE member: orb_NQ_tf1_pre.
2. Level 2 vs shuffled book: "0 of 81" is wrong. Only 65 of 81 unit-sessions had a shuffle; the real book beat the shuffled
   one in >= 60 % of variants in 20 of 65. Against the SAME strategy without Level 2 the result stands: the filters lowered
   the median variant (-$11,682 / -$10,444 / -$8,835; positive in 0 / 1 / 0 of 27).
3. Real vs shuffled heat-map pass rate is a tie (39 of 65 vs 79 of 130).
4. donchian random-draw figures at 4,000 draws: 81 % (lift $7,806) BUILD, 73 % (lift $5,506) 2024.
5. first_bar_mom GC pm 2024: 49 % positive cell by cell (63.9 % only after merging identical trade lists). Rejected anyway.
6. Ledger: 576 PICK + 248 stress candidate cells re-booked -> 34,808 of 40,000 used.
