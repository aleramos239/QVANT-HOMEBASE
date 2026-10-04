# straddle on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4 (+ the stage-1 book filter / book exit)
* Reason written first: At a session start new orders arrive and price leaves its pre-open balance in a directional burst; an OCO pair of stop entries around the last price rides whichever side breaks.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 7 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| straddle-NQ-tf15 · pm | 72 % of 96 | $12,945 | `off_atr0p5_pts20-r3` | 564 | $12,824 | 0.79 | 2.02 |
| straddle-NQ-tf30 · pm | 70 % of 96 | $7,704 | `off_atr1_pts30-r1` | 497 | $7,887 | 0.61 | 2.02 |
| straddle-NQ-tf15 · london | 83 % of 96 | $9,783 | `off_atr0p5_pts20-r3` | 568 | $9,828 | 0.58 | 2.02 |
| straddle-NQ-tf5 · pm | 67 % of 96 | $6,684 | `off_atr0p25_pct0p2-r1` | 564 | $6,474 | 0.49 | 2.02 |
| straddle-NQ-tf5 · london | 73 % of 96 | $8,146 | `off_atr0p5_pts20-r3` | 568 | $8,168 | 0.48 | 2.02 |
| straddle-NQ-tf30 · london | 77 % of 96 | $9,356 | `off_atr1_pts30-r2` | 568 | $9,398 | 0.46 | 2.02 |
| straddle-NQ-tf30 · nyam | 60 % of 96 | $7,680 | `off_atr0p5_atr1p5-r1` | 568 | $7,623 | 0.32 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| straddle-NQ-tf15 · pm | adx_hi | 66 % | $3,228 | Y/n/n | `off_atr0p25_pts10-r0` | 251 | $3,311 | 0.22 | $5,239 | 40.2 % | Y Y Y n n | - |
| straddle-NQ-tf15 · pm | adx_lo | 73 % | $8,968 | Y/Y/n | `off_atr0p25_pts10-r0` | 285 | $9,215 | 0.77 | -$10,656 | 61.0 % | Y Y n n n | - |
| straddle-NQ-tf15 · pm | vol_hi | 48 % | -$187 | n/n/n | `off_atr1_pts10-r3` | 255 | $550 | 0.10 | $8,879 | 32.4 % | Y n Y n n | - |
| straddle-NQ-tf15 · pm | vol_lo | 73 % | $11,428 | Y/Y/n | `off_atr0p25_pts20-r0` | 276 | $12,211 | 0.70 | -$13,125 | 81.5 % | Y Y n n n | - |
| straddle-NQ-tf15 · pm | news_only | 31 % | -$1,999 | n/n/n | `off_atr0p25_pts30-r1` | 71 | $121 | 0.02 | $2,878 | 70.9 % | n n Y n n | - |
| straddle-NQ-tf15 · pm | news_never | 73 % | $14,178 | Y/Y/n | `off_atr0p5_pts45-r3` | 493 | $14,153 | 0.56 | -$17,019 | 46.8 % | Y Y n n n | - |
| straddle-NQ-tf15 · pm | long | 83 % | $10,729 | Y/Y/Y | `off_atr0p25_pts10-r0` | 302 | $10,572 | 0.71 | $1,715 | 61.6 % | Y Y Y n n | - |
| straddle-NQ-tf15 · pm | short | 50 % | -$62 | n/n/n | `off_atr0p25_pct0p2-r0` | 262 | $392 | 0.02 | -$19,026 | 0.2 % | Y n n n n | - |
| straddle-NQ-tf30 · pm | adx_hi | 40 % | -$2,764 | n/n/n | `off_atr0p5_pts20-r2` | 251 | $671 | 0.08 | $12,578 | 63.4 % | Y n Y n n | - |
| straddle-NQ-tf30 · pm | adx_lo | 69 % | $8,853 | Y/n/n | `off_atr0p5_atr3-r3` | 284 | $9,134 | 0.33 | $16,225 | 37.2 % | Y Y Y n n | - |
| straddle-NQ-tf30 · pm | vol_hi | 45 % | -$921 | n/n/n | `off_atr0p25_pct0p1-r0` | 268 | $293 | 0.02 | -$8,954 | 41.4 % | Y n n n n | - |
| straddle-NQ-tf30 · pm | vol_lo | 66 % | $8,838 | Y/n/n | `off_atr0p25_atr3-r3` | 276 | $8,821 | 0.33 | $27,278 | 22.6 % | Y Y Y n n | - |
| straddle-NQ-tf30 · pm | news_only | 42 % | -$1,363 | n/n/n | `off_atr0p5_pts10-r2` | 71 | $236 | 0.10 | $1,605 | 71.3 % | n n Y n n | - |
| straddle-NQ-tf30 · pm | news_never | 64 % | $9,349 | Y/n/n | `off_atr1_pts30-r1` | 434 | $9,349 | 0.78 | $33,325 | 71.7 % | Y Y Y n n | - |
| straddle-NQ-tf30 · pm | long | 68 % | $5,857 | Y/n/n | `off_atr1_atr3-r3` | 267 | $5,847 | 0.24 | -$51,256 | 0.0 % | Y Y n n n | - |
| straddle-NQ-tf30 · pm | short | 55 % | $1,923 | n/n/n | `off_atr0p5_atr1p5-r1` | 273 | $1,923 | 0.09 | $2,710 | 65.3 % | Y n Y n n | - |
| straddle-NQ-tf15 · london | adx_hi | 83 % | $9,869 | Y/Y/Y | `off_atr0p5_pct0p1-r2` | 254 | $9,919 | 1.50 | $16,578 | 65.0 % | Y Y Y n n | - |
| straddle-NQ-tf15 · london | adx_lo | 71 % | $3,726 | Y/Y/n | `off_atr0p25_pts20-r0` | 286 | $3,461 | 0.13 | -$9,362 | 47.2 % | Y Y n n n | - |
| straddle-NQ-tf15 · london | vol_hi | 88 % | $9,011 | Y/Y/Y | `off_atr0p5_atr1p5-r1` | 271 | $8,916 | 0.95 | $11,882 | 88.3 % | Y Y Y n n | - |
| straddle-NQ-tf15 · london | vol_lo | 68 % | $4,362 | Y/n/n | `off_atr0p25_pct0p1-r1` | 277 | $4,432 | 0.95 | $11,897 | 49.2 % | Y Y Y n n | - |
| straddle-NQ-tf15 · london | news_only | 62 % | $2,126 | Y/n/n | `off_atr0p5_atr1p5-r1` | 71 | $2,111 | 0.55 | $7,354 | 68.2 % | n Y Y n n | - |
| straddle-NQ-tf15 · london | news_never | 80 % | $9,684 | Y/Y/Y | `off_atr1_pts20-r2` | 497 | $9,732 | 0.76 | $14,906 | 44.5 % | Y Y Y n n | - |
| straddle-NQ-tf15 · london | long | 94 % | $14,649 | Y/Y/Y | `off_atr0p25_pct0p1-r3` | 271 | $14,636 | 1.70 | $14,529 | 99.8 % | Y Y Y n Y | - |
| straddle-NQ-tf15 · london | short | 38 % | -$4,748 | n/n/n | `off_atr0p25_pts45-r2` | 297 | $327 | 0.01 | -$821 | 44.0 % | Y n n n n | - |
| straddle-NQ-tf5 · pm | adx_hi | 59 % | $3,336 | n/n/n | `off_atr1_pct0p2-r0` | 251 | $3,256 | 0.17 | -$6,426 | 37.4 % | Y n n n n | - |
| straddle-NQ-tf5 · pm | adx_lo | 58 % | $1,752 | n/n/n | `off_atr0p25_pct0p1-r2` | 285 | $1,945 | 0.29 | $5,899 | 59.7 % | Y n Y n n | - |
| straddle-NQ-tf5 · pm | vol_hi | 58 % | $1,366 | n/n/n | `off_atr0p25_pts30-r3` | 268 | $1,243 | 0.08 | $11,237 | 5.0 % | Y n Y n n | - |
| straddle-NQ-tf5 · pm | vol_lo | 58 % | $3,801 | n/n/n | `off_atr0p25_pct0p1-r3` | 276 | $3,136 | 0.39 | $4,277 | 60.7 % | Y n Y n n | - |
| straddle-NQ-tf5 · pm | news_only | 39 % | -$1,612 | n/n/n | `off_atr0p5_pts45-r2` | 71 | $11 | 0.00 | $1,381 | 49.1 % | n n Y n n | - |
| straddle-NQ-tf5 · pm | news_never | 64 % | $8,666 | Y/n/n | `off_atr0p5_atr1p5-r2` | 493 | $9,108 | 0.41 | -$5,046 | 82.4 % | Y Y n n n | - |
| straddle-NQ-tf5 · pm | long | 80 % | $9,508 | Y/Y/Y | `off_atr0p5_pts10-r0` | 305 | $9,725 | 0.66 | -$2,453 | 34.1 % | Y Y n n n | - |
| straddle-NQ-tf5 · pm | short | 40 % | -$3,180 | n/n/n | `off_atr0p25_pct0p1-r1` | 251 | $151 | 0.03 | $903 | 58.1 % | Y n Y n n | - |
| straddle-NQ-tf5 · london | adx_hi | 77 % | $9,026 | Y/Y/n | `off_atr1_pts45-r1` | 254 | $9,099 | 0.63 | $16,670 | 40.1 % | Y Y Y n n | - |
| straddle-NQ-tf5 · london | adx_lo | 83 % | $6,528 | Y/Y/Y | `off_atr0p5_pct0p1-r2` | 286 | $6,541 | 0.97 | $8,675 | 9.7 % | Y Y Y n n | - |
| straddle-NQ-tf5 · london | vol_hi | 76 % | $5,021 | Y/Y/n | `off_atr0p5_atr1p5-r1` | 271 | $5,051 | 0.88 | $8,854 | 69.4 % | Y Y Y n n | - |
| straddle-NQ-tf5 · london | vol_lo | 77 % | $7,157 | Y/Y/n | `off_atr0p5_pts10-r3` | 277 | $7,157 | 1.17 | $12,710 | 63.8 % | Y Y Y n n | - |
| straddle-NQ-tf5 · london | news_only | 67 % | $2,651 | Y/n/n | `off_atr0p5_atr1p5-r2` | 71 | $2,646 | 0.72 | $6,436 | 74.1 % | n Y Y n n | - |
| straddle-NQ-tf5 · london | news_never | 67 % | $4,490 | Y/n/n | `off_atr0p5_pts20-r0` | 497 | $4,177 | 0.14 | -$73,272 | 85.9 % | Y Y n n n | - |
| straddle-NQ-tf5 · london | long | 89 % | $11,532 | Y/Y/Y | `off_atr0p5_pct0p2-r1` | 269 | $11,584 | 1.26 | $6,814 | 85.0 % | Y Y Y n n | - |
| straddle-NQ-tf5 · london | short | 45 % | -$1,339 | n/n/n | `off_atr1_pts20-r1` | 308 | $363 | 0.05 | $4,999 | 84.4 % | Y n Y n n | - |
| straddle-NQ-tf30 · london | adx_hi | 65 % | $8,802 | Y/n/n | `off_atr0p5_pts45-r1` | 254 | $9,109 | 0.63 | $3,871 | 35.7 % | Y Y Y n n | - |
| straddle-NQ-tf30 · london | adx_lo | 75 % | $5,258 | Y/Y/n | `off_atr0p25_pts20-r1` | 286 | $5,241 | 0.77 | $17,459 | 4.3 % | Y Y Y n n | - |
| straddle-NQ-tf30 · london | vol_hi | 73 % | $8,784 | Y/Y/n | `off_atr0p25_pct0p2-r2` | 271 | $8,981 | 0.68 | $10,575 | 37.9 % | Y Y Y n n | - |
| straddle-NQ-tf30 · london | vol_lo | 68 % | $3,727 | Y/n/n | `off_atr1_pts20-r3` | 277 | $3,637 | 0.31 | $5,656 | 51.0 % | Y Y Y n n | - |
| straddle-NQ-tf30 · london | news_only | 46 % | -$636 | n/n/n | `off_atr0p5_pts30-r1` | 71 | $106 | 0.02 | $3,130 | 43.3 % | n n Y n n | - |
| straddle-NQ-tf30 · london | news_never | 82 % | $11,114 | Y/Y/Y | `off_atr0p25_pts30-r3` | 497 | $11,852 | 0.50 | -$576 | 69.3 % | Y Y n n n | - |
| straddle-NQ-tf30 · london | long | 94 % | $17,750 | Y/Y/Y | `off_atr0p25_pts45-r1` | 270 | $17,685 | 1.19 | $5,060 | 71.7 % | Y Y Y n n | - |
| straddle-NQ-tf30 · london | short | 18 % | -$8,276 | n/n/n | `off_atr0p5_pct0p1-r2` | 313 | $98 | 0.01 | $7,903 | 95.0 % | Y n Y n n | - |
| straddle-NQ-tf30 · nyam | adx_hi | 76 % | $9,619 | Y/Y/n | `off_atr0p25_pts30-r3` | 254 | $9,104 | 0.54 | $2,445 | 47.8 % | Y Y Y n n | - |
| straddle-NQ-tf30 · nyam | adx_lo | 53 % | $1,186 | n/n/n | `off_atr0p5_atr1p5-r1` | 286 | $1,176 | 0.07 | $13,092 | 32.4 % | Y n Y n n | - |
| straddle-NQ-tf30 · nyam | vol_hi | 43 % | -$2,236 | n/n/n | `off_atr1_pts30-r2` | 271 | $971 | 0.07 | $273 | 28.1 % | Y n Y n n | - |
| straddle-NQ-tf30 · nyam | vol_lo | 77 % | $12,507 | Y/Y/n | `off_atr0p5_pts20-r0` | 277 | $11,692 | 0.55 | -$25,465 | 51.4 % | Y Y n n n | - |
| straddle-NQ-tf30 · nyam | news_only | 17 % | -$4,516 | n/n/n | `off_atr0p5_pts30-r1` | 71 | $131 | 0.03 | -$596 | 37.5 % | n n n n n | - |
| straddle-NQ-tf30 · nyam | news_never | 72 % | $15,010 | Y/Y/n | `off_atr0p5_atr1p5-r1` | 497 | $13,947 | 0.63 | $27,111 | 81.1 % | Y Y Y n n | - |
| straddle-NQ-tf30 · nyam | long | 81 % | $14,362 | Y/Y/Y | `off_atr0p25_pct0p1-r2` | 323 | $14,518 | 1.97 | $31,818 | 100.0 % | Y Y Y n Y | - |
| straddle-NQ-tf30 · nyam | short | 41 % | -$4,004 | n/n/n | `off_atr1_pts30-r3` | 271 | $716 | 0.04 | -$54,199 | 0.0 % | Y n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
