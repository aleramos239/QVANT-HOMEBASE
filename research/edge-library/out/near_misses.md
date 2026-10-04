# Near misses — units that pass the BUILD heat map but were not admitted (2026-10-04)

BUILD = 22 Sep 2021 to end 2023, 1 contract, after costs. A unit = family x bar size (or clock time) x session x market.
Heat-map rule: at least 60 % of the menu variants positive and the median variant positive.
213 units pass the heat map; 5 also pass every BUILD control; the other 208 are listed here and in `out/admit/near_misses.csv` (all columns). Their 2024 was NOT opened, so it is still clean for the DEEPEN round.

## A. Units whose 2024 was opened and that were not admitted

| unit | BUILD: variants positive / median | 2024: variants positive / median | why not admitted |
|---|---|---|---|
| donchian-ES-tf30 pm | 74 % / $17,300 | 27 % / -$2,224 | 2024 heat map fails — carries the 2025-26 failure penalty |
| donchian-NQ-tf30 pm | 87 % / $29,642 | 44 % / -$564 | 2024 heat map fails — carries the 2025-26 failure penalty |
| first_bar_mom-GC-tf5 pm | 61 % / $1,362 | 64 % / $461 | too few trades (15 in BUILD + 2024; 100 needed) — carries the 2025-26 failure penalty |

The afternoon channel breakout (donchian pm), whose old favourite failed on 2025-26, passes BUILD on NQ and ES and fails 2024 on both: the penalty was deserved.

## B. Units that fail ONE test only (77): the central variant does not beat the best-of-random bar

They beat their matched random entries (lift > 0) but the central variant's t is below what the best of a random menu reaches (95th percentile). `t gap` = central t minus the bar; the closest are first. `beats` = share of 200 random draws the central variant beats.

| unit | variants positive | median net | central variant | trades | t | bar | t gap | lift over random | beats |
|---|---|---|---|---|---|---|---|---|---|
| supertrend-GC-tf30 mid | 93 % | $1,638 | `pts2-r1` | 43 | 1.25 | 1.24 | +0.01 | $3,167 | 100 % |
| ib-NQ-tf5 mid mode=break | 100 % | $32,445 | `modebreak_atr1p5-r1` | 310 | 1.99 | 2.02 | -0.02 | $35,138 | 100 % |
| pinbar-ES-tf30 mid | 73 % | $6,565 | `wick0p75_atr1p5-r2` | 26 | 1.22 | 1.30 | -0.08 | $5,945 | 96 % |
| rsi2-ES-tf30 eve | 84 % | $18,853 | `th5_pct0p2-r3` | 416 | 1.21 | 1.30 | -0.08 | $15,511 | 96 % |
| rsi2-NQ-tf30 eve | 99 % | $44,214 | `th5_pts30-r3` | 436 | 1.88 | 2.02 | -0.14 | $176 | 49 % |
| orb-NQ-tf30 nyam | 74 % | $8,756 | `or_min15_pts10-r1` | 564 | 1.84 | 2.02 | -0.18 | $19,413 | 100 % |
| ib-NQ-tf30 mid mode=break | 100 % | $32,875 | `modebreak_pct0p1-r0` | 310 | 1.62 | 2.02 | -0.39 | $18,177 | 92 % |
| ib-NQ-tf15 mid mode=break | 100 % | $32,875 | `modebreak_pct0p1-r0` | 310 | 1.62 | 2.02 | -0.39 | $9,568 | 80 % |
| donchian-NQ-tf15 pm | 86 % | $24,610 | `n10_pts30-r1` | 770 | 1.55 | 2.02 | -0.46 | $50,045 | 100 % |
| first_bar_mom-ES-tf15 pm | 95 % | $4,612 | `k1_pct0p1-r3` | 194 | 0.80 | 1.30 | -0.50 | $13,063 | 100 % |
| ib-ES-tf30 mid mode=break | 75 % | $9,920 | `modebreak_pct0p1-r0` | 323 | 0.73 | 1.30 | -0.57 | $6,705 | 78 % |
| first_bar_mom-ES-tf5 mid | 67 % | $2,160 | `k1p5_pct0p1-r3` | 61 | 0.71 | 1.30 | -0.59 | $2,406 | 88 % |
| ib-NQ-tf15 pm mode=break | 81 % | $16,008 | `modebreak_pts30-r2` | 218 | 1.40 | 2.02 | -0.62 | $12,058 | 90 % |
| first_bar_mom-ES-tf15 mid | 68 % | $2,562 | `k1p5_pct0p1-r2` | 150 | 0.66 | 1.30 | -0.64 | $10,854 | 100 % |
| ib-ES-tf1 mid mode=break | 66 % | $6,120 | `modebreak_pts8-r2` | 323 | 0.65 | 1.30 | -0.65 | $7,077 | 79 % |
| squeeze-NQ-tf5 pre | 68 % | $4,928 | `sq_typebbkc_pts20-r1` | 92 | 1.31 | 2.02 | -0.71 | $8,289 | 98 % |
| donchian-ES-tf5 pm | 68 % | $11,989 | `n10_pts8-r0` | 930 | 0.59 | 1.30 | -0.71 | $10,792 | 76 % |
| vwap_flip-NQ-tf15 pm | 86 % | $22,396 | `hold1_pts10-r0` | 703 | 1.26 | 2.02 | -0.76 | $30,884 | 100 % |
| orb-NQ-tf5 pre | 77 % | $16,580 | `or_min5_pts20-r2` | 567 | 1.20 | 2.02 | -0.81 | $20,711 | 99 % |
| vwap_z-NQ-tf15 eve | 80 % | $5,282 | `zth2p5_pts10-r3` | 144 | 1.18 | 2.02 | -0.84 | $6,696 | 96 % |
| donchian-NQ-tf15 nyam | 77 % | $21,535 | `n20_pts20-r3` | 667 | 1.15 | 2.02 | -0.87 | $3,468 | 64 % |
| ib-NQ-tf30 pm mode=break | 81 % | $15,656 | `modebreak_pts30-r3` | 218 | 1.13 | 2.02 | -0.89 | $5,462 | 68 % |
| gap-GC-tf15 nyam mode=go | 69 % | $3,195 | `modego_pts5-r1` | 415 | 0.32 | 1.24 | -0.92 | $13,538 | 96 % |
| first_bar_mom-GC-tf15 mid | 71 % | $2,660 | `k1_pts5-r3` | 220 | 0.31 | 1.24 | -0.93 | $3,974 | 78 % |
| straddle_t_0830-NQ-tf30 pre | 92 % | $35,920 | `offatr1_pct0p2-r3` | 433 | 1.67 | 2.62 | -0.95 | $24,915 | n/a |
| vwap_flip-NQ-tf15 pre | 73 % | $18,166 | `hold1_pts30-r2` | 312 | 1.07 | 2.02 | -0.95 | $10,224 | 79 % |
| donchian-NQ-tf5 pm | 84 % | $31,252 | `n10_pts20-r0` | 1080 | 1.05 | 2.02 | -0.97 | $22,822 | 89 % |
| vwap_z-ES-tf30 mid | 68 % | $892 | `zth2p5_pts8-r2` | 24 | 0.32 | 1.30 | -0.98 | $563 | 60 % |
| squeeze-GC-tf5 nyam | 61 % | $2,607 | `sq_typeinside_atr1p5-r1` | 780 | 0.26 | 1.24 | -0.98 | $19,904 | 100 % |
| first_bar_mom-NQ-tf5 mid | 92 % | $12,805 | `k1_pct0p2-r2` | 236 | 1.03 | 2.02 | -0.99 | $12,741 | 88 % |
| vwap_band-NQ-tf30 london | 75 % | $3,088 | `band2p5_pct0p1-r2` | 52 | 1.02 | 2.02 | -0.99 | $3,193 | 92 % |
| ib-NQ-tf5 pm mode=break | 81 % | $14,968 | `modebreak_atr1p5-r2` | 218 | 1.01 | 2.02 | -1.01 | $11,538 | 80 % |
| first_bar_mom-GC-tf30 mid | 60 % | $906 | `k1p5_pct0p2-r2` | 93 | 0.20 | 1.24 | -1.04 | $9,733 | 100 % |
| first_bar_mom-NQ-tf15 mid | 93 % | $11,828 | `k1_pts30-r1` | 432 | 0.93 | 2.02 | -1.09 | $25,606 | 99 % |
| vwap_band-GC-tf15 pre | 71 % | $866 | `band2_atr3-r0` | 31 | 0.14 | 1.24 | -1.10 | $2,531 | 77 % |
| first_bar_mom-GC-tf30 pm | 68 % | $700 | `k1_atr3-r3` | 84 | 0.12 | 1.24 | -1.12 | $1,957 | 70 % |
| ib-ES-tf30 pm mode=break | 62 % | $2,173 | `modebreak_atr1p5-r1` | 224 | 0.18 | 1.30 | -1.12 | $668 | 55 % |
| squeeze-NQ-tf15 nyam | 76 % | $3,767 | `sq_typebbkc_pct0p2-r1` | 58 | 0.89 | 2.02 | -1.13 | $3,915 | 90 % |
| vwap_z-ES-tf30 asia | 67 % | $1,744 | `zth2p5_pts12-r0` | 39 | 0.15 | 1.30 | -1.15 | $2,695 | 72 % |
| first_bar_mom-NQ-tf15 pm | 96 % | $4,686 | `k1_pts20-r1` | 170 | 0.86 | 2.02 | -1.15 | $6,647 | 89 % |
| first_bar_mom-ES-tf5 pm | 75 % | $1,549 | `k1_pts12-r3` | 205 | 0.14 | 1.30 | -1.16 | $687 | 51 % |
| orb-NQ-tf5 nyam | 71 % | $7,324 | `or_min30_pts20-r1` | 522 | 0.85 | 2.02 | -1.17 | $16,536 | 97 % |
| first_bar_mom-NQ-tf5 pre | 79 % | $5,148 | `k1_pts10-r3` | 275 | 0.84 | 2.02 | -1.17 | $4,236 | 79 % |
| rsi2-NQ-tf15 asia | 78 % | $14,437 | `th15_pts20-r2` | 867 | 0.81 | 2.02 | -1.20 | $4,189 | 68 % |
| straddle-NQ-tf15 pm | 72 % | $12,945 | `off_atr0p5_pts20-r3` | 564 | 0.79 | 2.02 | -1.22 | $20,875 | 98 % |
| orb-NQ-tf15 pre | 78 % | $17,217 | `or_min5_pts45-r1` | 567 | 0.78 | 2.02 | -1.23 | $15,458 | 84 % |
| sweep_rev-NQ-tf1 eve | 84 % | $6,680 | `levelsboth_pts20-r3` | 130 | 0.75 | 2.02 | -1.27 | $12,627 | 98 % |
| first_bar_mom-NQ-tf30 pre | 76 % | $5,310 | `k1p5_pts20-r2` | 148 | 0.70 | 2.02 | -1.32 | $7,186 | 96 % |
| vwap_z-NQ-tf30 mid | 74 % | $7,072 | `zth2_pts30-r3` | 99 | 0.69 | 2.02 | -1.33 | $7,672 | 85 % |
| vwap_flip-NQ-tf5 pre | 74 % | $15,004 | `hold1_atr3-r1` | 523 | 0.67 | 2.02 | -1.34 | $16,262 | 84 % |
| first_bar_mom-NQ-tf30 mid | 66 % | $5,784 | `k1_pts20-r1` | 495 | 0.67 | 2.02 | -1.34 | $12,113 | 94 % |
| squeeze-NQ-tf30 pm | 88 % | $6,738 | `sq_typenr7_pts20-r2` | 371 | 0.63 | 2.02 | -1.38 | $26,224 | 100 % |
| straddle-NQ-tf30 pm | 70 % | $7,704 | `off_atr1_pts30-r1` | 497 | 0.61 | 2.02 | -1.41 | $33,406 | 100 % |
| first_bar_mom-NQ-tf5 pm | 79 % | $3,152 | `k1p5_pts45-r1` | 35 | 0.61 | 2.02 | -1.41 | $3,813 | 82 % |
| lon_break-NQ-tf1 nyam | 81 % | $9,898 | `min_rng_atr0_pts20-r3` | 548 | 0.61 | 2.02 | -1.41 | $16,632 | 92 % |
| lon_break-NQ-tf5 nyam | 75 % | $10,007 | `min_rng_atr0_pts20-r3` | 548 | 0.61 | 2.02 | -1.41 | $10,403 | 74 % |
| straddle-NQ-tf15 london | 83 % | $9,783 | `off_atr0p5_pts20-r3` | 568 | 0.58 | 2.02 | -1.43 | $7,440 | 68 % |
| vwap_band-NQ-tf30 eve | 73 % | $3,592 | `band1p5_pct0p1-r1` | 637 | 0.51 | 2.02 | -1.51 | $11,322 | 98 % |
| straddle-NQ-tf5 pm | 67 % | $6,684 | `off_atr0p25_pct0p2-r1` | 564 | 0.49 | 2.02 | -1.52 | $14,277 | 91 % |
| vwap_band-NQ-tf5 eve | 83 % | $8,260 | `band2_pts20-r2` | 860 | 0.49 | 2.02 | -1.53 | $5,699 | 66 % |
| straddle-NQ-tf5 london | 73 % | $8,146 | `off_atr0p5_pts20-r3` | 568 | 0.48 | 2.02 | -1.53 | $10,587 | 76 % |
| ib-NQ-tf30 nyam mode=break | 62 % | $4,644 | `modebreak_pts10-r2` | 346 | 0.48 | 2.02 | -1.53 | $12,642 | 100 % |
| ib-NQ-tf15 nyam mode=break | 62 % | $4,644 | `modebreak_pts10-r2` | 346 | 0.48 | 2.02 | -1.53 | $11,264 | 100 % |
| orb-NQ-tf1 nyam | 71 % | $6,708 | `or_min15_pts20-r2` | 564 | 0.48 | 2.02 | -1.53 | $16,801 | 88 % |
| straddle-NQ-tf30 london | 77 % | $9,356 | `off_atr1_pts30-r2` | 568 | 0.46 | 2.02 | -1.56 | $3,786 | 58 % |
| vwap_z-NQ-tf30 london | 66 % | $1,203 | `zth3_pts30-r0` | 3 | 0.40 | 2.02 | -1.62 | $2,290 | 100 % |
| first_bar_mom-NQ-tf5 london | 69 % | $4,676 | `k1_pts20-r2` | 554 | 0.34 | 2.02 | -1.68 | $13,584 | 88 % |
| donchian-NQ-tf5 nyam | 62 % | $7,038 | `n10_pts30-r1` | 1399 | 0.32 | 2.02 | -1.69 | $404 | 55 % |
| straddle-NQ-tf30 nyam | 60 % | $7,680 | `off_atr0p5_atr1p5-r1` | 568 | 0.32 | 2.02 | -1.70 | $24,973 | 92 % |
| straddle_t_0300-NQ-tf30 london | 69 % | $8,584 | `offptsA_pct0p1-r2` | 564 | 0.89 | 2.62 | -1.72 | $14,130 | n/a |
| pinbar-NQ-tf5 london | 67 % | $6,312 | `wick0p6_pct0p2-r3` | 539 | 0.28 | 2.02 | -1.74 | $3,790 | 58 % |
| sweep_rev-NQ-tf30 mid | 64 % | $2,564 | `levelspd_pts30-r2` | 134 | 0.26 | 2.02 | -1.76 | $5,825 | 78 % |
| gap-NQ-tf30 nyam mode=go | 62 % | $1,488 | `modego_pts10-r3` | 396 | 0.22 | 2.02 | -1.80 | $10,224 | 99 % |
| vwap_band-NQ-tf30 mid | 68 % | $1,667 | `band2_pts45-r2` | 48 | 0.22 | 2.02 | -1.80 | $541 | 52 % |
| squeeze-NQ-tf30 pre | 70 % | $1,502 | `sq_typenr7_pts30-r3` | 41 | 0.21 | 2.02 | -1.80 | $765 | 60 % |
| sweep_rev-NQ-tf30 pre | 67 % | $2,484 | `levelsboth_pct0p1-r0` | 217 | 0.14 | 2.02 | -1.88 | $7,215 | 79 % |
| straddle_t_1800-NQ-tf30 eve | 84 % | $13,127 | `offatr0p5_atr1p5-r2` | 508 | 0.56 | 2.62 | -2.05 | $52,443 | n/a |

## C. Units that fail two or more tests (131)

| failed tests | units | of which NQ / ES / GC | Level-2 variants |
|---|---|---|---|
| below the best-of-random bar; weak rationale needs t >= 3 | 33 | 24 / 6 / 3 | 0 |
| below the shuffled-book bar; below the best-of-random bar | 15 | 0 / 0 / 0 | 15 |
| below the shuffled-book bar; below the best-of-random bar; weak rationale needs t >= 3 | 5 | 4 / 0 / 0 | 1 |
| loses to matched random entries; below the best-of-random bar | 36 | 24 / 5 / 7 | 0 |
| loses to matched random entries; below the best-of-random bar; weak rationale needs t >= 3 | 16 | 12 / 2 / 2 | 0 |
| loses to matched random entries; below the shuffled-book bar; below the best-of-random bar | 3 | 0 / 0 / 0 | 3 |
| loses to matched random entries; loses to the shuffled book; below the shuffled-book bar; below the best-of-random bar | 9 | 0 / 0 / 0 | 9 |
| loses to matched random entries; loses to the shuffled book; below the shuffled-book bar; below the best-of-random bar; weak rationale needs t >= 3 | 1 | 1 / 0 / 0 | 0 |
| loses to the shuffled book; below the shuffled-book bar; below the best-of-random bar | 10 | 0 / 0 / 0 | 10 |
| loses to the shuffled book; below the shuffled-book bar; below the best-of-random bar; weak rationale needs t >= 3 | 1 | 1 / 0 / 0 | 0 |
| loses to the same straddle at a random minute; below the best-of-random bar; weak rationale needs t >= 3 | 1 | 1 / 0 / 0 | 0 |
| loses to the same straddle at a random minute; below the shuffled-book bar; below the best-of-random bar; weak rationale needs t >= 3 | 1 | 0 / 0 / 0 | 1 |

Read with care: on NQ about 1 in 9 heat maps of RANDOM entries also passes the heat-map rule (6 of 56), and 5 of 18 random-minute straddles do. A heat-map pass on NQ alone is weak evidence; on ES and GC no random heat map passed (0 of 56 each).
