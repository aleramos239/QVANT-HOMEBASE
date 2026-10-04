# orb on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: ADMITTED (member orb_NQ_tf1_pre; its other units stay open)** · deepen rounds used: 1 of 4 (+ the stage-1 book filter / book exit)
* Reason written first: Opening range = the first balance of the session: the first or_min minutes set the range the rest of the session resolves, so a break of either side traps the other side and carries.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 5 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| orb-NQ-tf30 · nyam | 74 % of 96 | $8,756 | `or_min15_pts10-r1` | 564 | $8,809 | 1.84 | 2.02 |
| orb-NQ-tf5 · pre | 77 % of 96 | $16,580 | `or_min5_pts20-r2` | 567 | $16,677 | 1.20 | 2.02 |
| orb-NQ-tf5 · nyam | 71 % of 96 | $7,324 | `or_min30_pts20-r1` | 522 | $7,797 | 0.85 | 2.02 |
| orb-NQ-tf15 · pre | 78 % of 96 | $17,217 | `or_min5_pts45-r1` | 567 | $16,902 | 0.78 | 2.02 |
| orb-NQ-tf1 · nyam | 71 % of 96 | $6,708 | `or_min15_pts20-r2` | 564 | $6,564 | 0.48 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orb-NQ-tf30 · nyam | adx_hi | 80 % | $9,012 | Y/Y/Y | `or_min5_pct0p1-r0` | 254 | $8,709 | 0.39 | -$9,686 | 57.9 % | Y Y n n n | - |
| orb-NQ-tf30 · nyam | adx_lo | 51 % | $1,506 | n/n/n | `or_min15_pts10-r1` | 284 | $1,779 | 0.52 | $10,747 | 13.9 % | Y n Y n n | - |
| orb-NQ-tf30 · nyam | vol_hi | 35 % | -$7,189 | n/n/n | `or_min30_pts20-r2` | 254 | $874 | 0.10 | $4,242 | 15.6 % | Y n Y n n | - |
| orb-NQ-tf30 · nyam | vol_lo | 82 % | $15,990 | Y/Y/Y | `or_min15_pts10-r0` | 275 | $16,135 | 0.94 | -$13,375 | 55.0 % | Y Y n n n | - |
| orb-NQ-tf30 · nyam | news_only | 60 % | $2,458 | Y/n/n | `or_min15_pts30-r3` | 71 | $2,411 | 0.27 | -$18,957 | 66.7 % | n Y n n n | - |
| orb-NQ-tf30 · nyam | news_never | 70 % | $5,540 | Y/n/n | `or_min30_pts20-r2` | 458 | $5,398 | 0.44 | $701 | 6.0 % | Y Y Y n n | - |
| orb-NQ-tf30 · nyam | long | 65 % | $5,323 | Y/n/n | `or_min15_pts10-r3` | 301 | $5,446 | 0.86 | $18,920 | 100.0 % | Y Y Y n Y | - |
| orb-NQ-tf30 · nyam | short | 65 % | $7,572 | Y/n/n | `or_min5_atr3-r2` | 281 | $7,536 | 0.17 | $39,467 | 100.0 % | Y Y Y n Y | - |
| orb-NQ-tf5 · pre | adx_hi | 71 % | $7,276 | Y/Y/n | `or_min5_pts20-r2` | 253 | $7,248 | 0.78 | $8,131 | 54.2 % | Y Y Y n n | - |
| orb-NQ-tf5 · pre | adx_lo | 75 % | $10,248 | Y/Y/n | `or_min5_pct0p2-r2` | 286 | $10,006 | 0.75 | $7,808 | 35.9 % | Y Y Y n n | - |
| orb-NQ-tf5 · pre | vol_hi | 41 % | -$1,338 | n/n/n | `or_min5_pts10-r0` | 270 | $635 | 0.04 | -$8,763 | 3.8 % | Y n n n n | - |
| orb-NQ-tf5 · pre | vol_lo | 91 % | $20,241 | Y/Y/Y | `or_min15_atr3-r2` | 254 | $19,949 | 1.02 | $10,670 | 83.5 % | Y Y Y n n | - |
| orb-NQ-tf5 · pre | news_only | 55 % | $1,258 | n/n/n | `or_min15_atr3-r1` | 58 | $993 | 0.09 | -$9,852 | 59.7 % | n n n n n | - |
| orb-NQ-tf5 · pre | news_never | 74 % | $10,340 | Y/Y/n | `or_min5_pts10-r2` | 496 | $10,291 | 1.57 | $17,143 | 0.0 % | Y Y Y n n | - |
| orb-NQ-tf5 · pre | long | 67 % | $3,898 | Y/n/n | `or_min5_pts20-r3` | 268 | $3,848 | 0.33 | $1,269 | 60.5 % | Y Y Y n n | - |
| orb-NQ-tf5 · pre | short | 77 % | $11,063 | Y/Y/n | `or_min15_atr3-r3` | 273 | $10,903 | 0.40 | -$52,901 | 0.0 % | Y Y n n n | - |
| orb-NQ-tf5 · nyam | adx_hi | 81 % | $7,986 | Y/Y/Y | `or_min15_pts10-r2` | 254 | $7,939 | 1.68 | $13,529 | 93.8 % | Y Y Y n n | - |
| orb-NQ-tf5 · nyam | adx_lo | 48 % | -$1,335 | n/n/n | `or_min30_pts30-r1` | 263 | $1,233 | 0.13 | -$1,775 | 33.1 % | Y n n n n | - |
| orb-NQ-tf5 · nyam | vol_hi | 34 % | -$8,159 | n/n/n | `or_min30_pts20-r2` | 254 | $874 | 0.10 | $11,818 | 16.2 % | Y n Y n n | - |
| orb-NQ-tf5 · nyam | vol_lo | 81 % | $15,830 | Y/Y/Y | `or_min5_pct0p1-r0` | 277 | $15,817 | 0.83 | -$26,693 | 68.8 % | Y Y n n n | - |
| orb-NQ-tf5 · nyam | news_only | 62 % | $2,458 | Y/n/n | `or_min15_pts30-r3` | 71 | $2,411 | 0.27 | -$2,097 | 67.4 % | n Y n n n | - |
| orb-NQ-tf5 · nyam | news_never | 66 % | $4,630 | Y/n/n | `or_min15_pts10-r3` | 493 | $4,718 | 0.59 | $22,364 | 20.0 % | Y Y Y n n | - |
| orb-NQ-tf5 · nyam | long | 64 % | $5,026 | Y/n/n | `or_min5_atr1p5-r1` | 287 | $5,077 | 0.52 | $4,980 | 72.6 % | Y Y Y n n | - |
| orb-NQ-tf5 · nyam | short | 61 % | $5,503 | Y/n/n | `or_min15_atr3-r2` | 263 | $5,673 | 0.18 | -$88,293 | 0.0 % | Y Y n n n | - |
| orb-NQ-tf15 · pre | adx_hi | 68 % | $7,340 | Y/n/n | `or_min5_pts30-r1` | 253 | $7,303 | 0.76 | $2,255 | 38.5 % | Y Y Y n n | - |
| orb-NQ-tf15 · pre | adx_lo | 77 % | $13,504 | Y/Y/n | `or_min15_pct0p2-r2` | 260 | $12,660 | 0.99 | $20,665 | 71.2 % | Y Y Y n n | - |
| orb-NQ-tf15 · pre | vol_hi | 38 % | -$4,444 | n/n/n | `or_min5_pts10-r0` | 270 | $635 | 0.04 | $9,812 | 3.6 % | Y n Y n n | - |
| orb-NQ-tf15 · pre | vol_lo | 92 % | $22,002 | Y/Y/Y | `or_min15_pts45-r1` | 254 | $22,159 | 1.55 | $24,342 | 92.6 % | Y Y Y n n | - |
| orb-NQ-tf15 · pre | news_only | 51 % | $46 | n/n/n | `or_min15_pct0p1-r3` | 58 | $33 | 0.01 | $2,343 | 52.2 % | n n Y n n | - |
| orb-NQ-tf15 · pre | news_never | 78 % | $13,092 | Y/Y/n | `or_min5_atr1p5-r1` | 496 | $13,216 | 0.88 | $13,757 | 0.1 % | Y Y Y n n | - |
| orb-NQ-tf15 · pre | long | 72 % | $5,177 | Y/Y/n | `or_min30_pts10-r0` | 202 | $4,782 | 0.33 | -$52,402 | 0.0 % | Y Y n n n | - |
| orb-NQ-tf15 · pre | short | 76 % | $11,161 | Y/Y/n | `or_min5_atr3-r3` | 299 | $11,099 | 0.31 | -$22,878 | 2.0 % | Y Y n n n | - |
| orb-NQ-tf1 · nyam | adx_hi | 81 % | $7,146 | Y/Y/Y | `or_min15_atr1p5-r1` | 254 | $7,084 | 0.81 | $11,135 | 87.3 % | Y Y Y n n | - |
| orb-NQ-tf1 · nyam | adx_lo | 46 % | -$1,746 | n/n/n | `or_min30_pts30-r1` | 263 | $1,233 | 0.13 | $5,303 | 32.3 % | Y n Y n n | - |
| orb-NQ-tf1 · nyam | vol_hi | 35 % | -$6,226 | n/n/n | `or_min30_atr3-r0` | 254 | $424 | 0.01 | -$37,764 | 2.7 % | Y n n n n | - |
| orb-NQ-tf1 · nyam | vol_lo | 79 % | $13,546 | Y/Y/n | `or_min30_atr1p5-r2` | 249 | $13,399 | 1.21 | $20,222 | 92.4 % | Y Y Y n n | - |
| orb-NQ-tf1 · nyam | news_only | 67 % | $3,306 | Y/n/n | `or_min5_pts30-r3` | 71 | $3,641 | 0.40 | $5,749 | 66.6 % | n Y Y n n | - |
| orb-NQ-tf1 · nyam | news_never | 60 % | $3,340 | Y/n/n | `or_min30_pts10-r3` | 458 | $3,123 | 0.41 | $13,421 | 23.2 % | Y Y Y n n | - |
| orb-NQ-tf1 · nyam | long | 58 % | $3,041 | n/n/n | `or_min5_pts10-r0` | 287 | $3,177 | 0.19 | -$106,452 | 0.0 % | Y n n n n | - |
| orb-NQ-tf1 · nyam | short | 62 % | $6,135 | Y/n/n | `or_min15_pts30-r3` | 263 | $5,863 | 0.35 | -$79,875 | 0.0 % | Y Y n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Member orb_NQ_tf1_pre — the same splits, INFORMATION ONLY (nothing here changes the member)
Default variant `or_min5_atr1p5-r2`, BUILD + 2024, 1 contract after costs (819 trades, $28,799):
| side | trades | net | 2021* | 2022 | 2023 | 2024 | avg trade | t |
|---|---|---|---|---|---|---|---|---|
| adx_hi | 346 | $18,726 | $322 | $7,055 | $3,441 | $7,908 | $54 | 3.14 |
| adx_lo | 445 | $10,870 | -$365 | $2,823 | $3,883 | $4,529 | $24 | 1.87 |
| vol_hi | 403 | $14,403 | $660 | $3,018 | $3,672 | $7,053 | $36 | 2.22 |
| vol_lo | 396 | $14,751 | -$1,145 | $6,860 | $3,652 | $5,384 | $37 | 2.8 |
| news_only | 102 | $13,022 | $494 | $8,601 | $3,071 | $856 | $128 | 3.43 |
| news_never | 717 | $15,777 | -$1,334 | $1,277 | $4,253 | $11,581 | $22 | 2.12 |
| long | 397 | $6,447 | -$385 | $938 | $975 | $4,919 | $16 | 1.11 |
| short | 422 | $22,352 | -$455 | $8,940 | $6,349 | $7,518 | $53 | 3.7 |

Its whole BUILD heat map by side (96 variants; each side has its own central variant):
| side | variants positive | median | central variant | trades | net | t |
|---|---|---|---|---|---|---|
| all | 72 % | $16,118 | `or_min5_atr1p5-r2` | 567 | $16,362 | 2.32 |
| adx_hi | 70 % | $7,472 | `or_min5_pct0p1-r3` | 253 | $7,568 | 0.94 |
| adx_lo | 68 % | $7,121 | `or_min5_atr3-r3` | 286 | $7,441 | 0.65 |
| vol_hi | 40 % | -$2,866 | `or_min5_pts10-r0` | 270 | $635 | 0.04 |
| vol_lo | 85 % | $20,290 | `or_min5_atr3-r2` | 277 | $20,047 | 2.13 |
| news_only | 52 % | $190 | `or_min15_pct0p2-r3` | 58 | $58 | 0.01 |
| news_never | 71 % | $8,314 | `or_min5_atr1p5-r1` | 496 | $8,396 | 1.97 |
| long | 65 % | $2,742 | `or_min5_pts10-r1` | 268 | $2,823 | 0.84 |
| short | 72 % | $11,044 | `or_min5_pct0p1-r1` | 299 | $10,864 | 2.27 |
News days (CPI 39 trades $8,364; jobs report 37 trades $3,527; Fed days 27 trades $452) are 12 % of the trades and 45 % of the profit, but in 2024 they gave only $856 of $12,437. Shorts earn $22,352, longs $6,447. Long / short here is a split of stored trades (approximate).

## Left on the DONE checklist
* deepen tools: flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
