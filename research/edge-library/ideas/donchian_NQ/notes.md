# donchian on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4 (+ the stage-1 book filter / book exit)
* Reason written first: Trend continuation: a close beyond the prior n-bar channel traps the other side, whose stops feed a continuation move.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 2 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| donchian-NQ-tf15 · nyam | 77 % of 96 | $21,535 | `n20_pts20-r3` | 667 | $21,262 | 1.15 | 2.02 |
| donchian-NQ-tf5 · nyam | 62 % of 128 | $7,038 | `n10_pts30-r1` | 1399 | $7,239 | 0.32 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| donchian-NQ-tf15 · nyam | adx_hi | 58 % | $2,203 | n/n/n | `n10_pct0p2-r2` | 342 | $2,192 | 0.15 | -$14,035 | 36.1 % | Y n n n n | - |
| donchian-NQ-tf15 · nyam | adx_lo | 77 % | $15,657 | Y/Y/n | `n20_atr1p5-r3` | 271 | $15,626 | 0.63 | -$14,254 | 31.8 % | Y Y n n n | - |
| donchian-NQ-tf15 · nyam | vol_hi | 56 % | $834 | n/n/n | `n20_pts10-r1` | 376 | $661 | 0.17 | $5,241 | 63.8 % | Y n Y n n | - |
| donchian-NQ-tf15 · nyam | vol_lo | 78 % | $17,710 | Y/Y/n | `n20_pct0p2-r2` | 329 | $17,759 | 1.23 | $517 | 88.1 % | Y Y Y n n | - |
| donchian-NQ-tf15 · nyam | news_only | 17 % | -$3,602 | n/n/n | `n10_pts30-r3` | 63 | $68 | 0.01 | -$15,534 | 37.5 % | n n n n n | - |
| donchian-NQ-tf15 · nyam | news_never | 82 % | $23,918 | Y/Y/Y | `n20_pts45-r2` | 494 | $23,474 | 0.83 | -$2,180 | 53.4 % | Y Y n n n | - |
| donchian-NQ-tf15 · nyam | long | 83 % | $10,530 | Y/Y/Y | `n40_pts20-r0` | 135 | $10,600 | 0.84 | -$53,579 | 0.0 % | Y Y n n n | - |
| donchian-NQ-tf15 · nyam | short | 67 % | $9,584 | Y/n/n | `n40_pts10-r0` | 154 | $9,579 | 0.64 | -$44,362 | 0.0 % | Y Y n n n | - |
| donchian-NQ-tf5 · nyam | adx_hi | 18 % | -$17,864 | n/n/n | `n20_pts10-r0` | 478 | $1,368 | 0.06 | -$18,996 | 15.1 % | Y n n n n | - |
| donchian-NQ-tf5 · nyam | adx_lo | 91 % | $25,097 | Y/Y/Y | `n40_pts30-r2` | 445 | $25,070 | 1.37 | -$11,508 | 98.9 % | Y Y n n n | - |
| donchian-NQ-tf5 · nyam | vol_hi | 7 % | -$20,412 | n/n/n | `n20_pct0p2-r0` | 409 | $139 | 0.00 | -$52,225 | 6.6 % | Y n n n n | - |
| donchian-NQ-tf5 · nyam | vol_lo | 81 % | $35,030 | Y/Y/Y | `n20_atr1p5-r1` | 580 | $34,460 | 2.07 | $26,602 | 100.0 % | Y Y Y Y Y | PASS on BUILD |
| donchian-NQ-tf5 · nyam | news_only | 9 % | -$6,490 | n/n/n | `n40_pct0p2-r0` | 71 | $636 | 0.05 | -$4,392 | 33.6 % | n n n n n | - |
| donchian-NQ-tf5 · nyam | news_never | 68 % | $15,033 | Y/n/n | `n60_pts30-r3` | 686 | $14,946 | 0.55 | -$44,404 | 77.9 % | Y Y n n n | - |
| donchian-NQ-tf5 · nyam | long | 67 % | $6,026 | Y/n/n | `n60_pts20-r1` | 549 | $5,619 | 0.60 | -$14,652 | 0.3 % | Y Y n n n | - |
| donchian-NQ-tf5 · nyam | short | 55 % | $1,890 | n/n/n | `n20_atr1p5-r1` | 584 | $1,874 | 0.10 | -$57,667 | 0.0 % | Y n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* `donchian-NQ-tf5 · nyam` vol_lo: 2024 opened (whole menu, same split): 82 % of variants positive, median $18,324 -> the 2024 table PASSES. The BUILD central variant `n20_atr1p5-r1` made -$4,715 in 2024 (260 trades; lift over random entries -$13,746).
* Admission: 84 of 128 variants are positive in both periods and under 2 ticks + 250 ms (`members/_rejected/donchian_NQ_tf5_nyam_vol_lo/surviving_set.csv`), but the BUILD central variant is not one of them. The rule-chosen replacement `n60_pts10-r0` fails library.admission (beats_c1_build, beats_c1_pick, above_best_of_nulls_build). **NOT ADMITTED**. Only 17 of the 84 surviving variants beat random entries with the same exits on the same days in both periods (`out/deepen/surviving_donchian_vs_random.csv`): on quiet days the NQ morning itself paid, not the breakout.

## Left on the DONE checklist
* deepen tools: flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
