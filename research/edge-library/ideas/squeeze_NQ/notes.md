# squeeze on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: Compression precedes expansion: after a volatility squeeze the positions built inside the narrow range are forced out on its release, and the move that starts is followed.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 4 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| squeeze-NQ-tf5 · pre | 68 % of 96 | $4,928 | `sq_typebbkc_pts20-r1` | 92 | $5,027 | 1.31 | 2.02 |
| squeeze-NQ-tf15 · nyam | 76 % of 96 | $3,767 | `sq_typebbkc_pct0p2-r1` | 58 | $3,753 | 0.89 | 2.02 |
| squeeze-NQ-tf30 · pm | 88 % of 90 | $6,738 | `sq_typenr7_pts20-r2` | 371 | $6,661 | 0.63 | 2.02 |
| squeeze-NQ-tf30 · pre | 70 % of 64 | $1,502 | `sq_typenr7_pts30-r3` | 41 | $1,476 | 0.21 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| squeeze-NQ-tf5 · pre | adx_hi | 50 % | -$26 | n/n/n | `sq_typeinside_pct0p1-r1` | 331 | $176 | 0.03 | $6,864 | 25.2 % | Y n Y n n | - |
| squeeze-NQ-tf5 · pre | adx_lo | 70 % | $4,648 | Y/n/n | `sq_typebbkc_pts30-r1` | 40 | $4,550 | 1.20 | $5,688 | 82.9 % | n Y Y n n | - |
| squeeze-NQ-tf5 · pre | vol_hi | 65 % | $2,446 | Y/n/n | `sq_typebbkc_pts10-r2` | 46 | $2,481 | 1.21 | $1,166 | 66.3 % | n Y Y n n | - |
| squeeze-NQ-tf5 · pre | vol_lo | 59 % | $1,852 | n/n/n | `sq_typebbkc_atr1p5-r1` | 44 | $1,789 | 0.65 | $4,691 | 7.2 % | n n Y n n | - |
| squeeze-NQ-tf5 · pre | news_only | 52 % | $394 | n/n/n | `sq_typebbkc_pts10-r2` | 12 | $517 | 0.48 | $474 | 49.9 % | n n Y n n | - |
| squeeze-NQ-tf5 · pre | news_never | 69 % | $4,826 | Y/n/n | `sq_typebbkc_pts45-r2` | 78 | $4,828 | 0.42 | -$2,896 | 65.2 % | n Y n n n | - |
| squeeze-NQ-tf5 · pre | long | 54 % | $512 | n/n/n | `sq_typeinside_atr3-r2` | 244 | $464 | 0.02 | -$15,580 | 7.4 % | Y n n n n | - |
| squeeze-NQ-tf5 · pre | short | 80 % | $5,786 | Y/Y/Y | `sq_typebbkc_pts45-r2` | 47 | $5,962 | 0.65 | -$14,932 | 0.0 % | n Y n n n | - |
| squeeze-NQ-tf15 · nyam | adx_hi | 60 % | $722 | Y/n/n | `sq_typenr7_pts20-r2` | 10 | $725 | 0.37 | $128 | 84.9 % | n Y Y n n | - |
| squeeze-NQ-tf15 · nyam | adx_lo | 74 % | $3,103 | Y/Y/n | `sq_typenr7_pts10-r0` | 8 | $3,103 | 0.91 | $3,064 | 87.2 % | n Y Y n n | - |
| squeeze-NQ-tf15 · nyam | vol_hi | 45 % | -$92 | n/n/n | `sq_typenr7_atr1p5-r3` | 8 | $43 | 0.01 | -$1,100 | 49.8 % | n n n n n | - |
| squeeze-NQ-tf15 · nyam | vol_lo | 89 % | $6,772 | Y/Y/Y | `sq_typeinside_atr3-r1` | 117 | $6,872 | 0.35 | $12,581 | 91.1 % | Y Y Y n n | - |
| squeeze-NQ-tf15 · nyam | news_only | 33 % | -$490 | n/n/n | `sq_typebbkc_pct0p1-r2` | 8 | $58 | 0.05 | $228 | 64.5 % | n n Y n n | - |
| squeeze-NQ-tf15 · nyam | news_never | 83 % | $4,561 | Y/Y/Y | `sq_typeinside_pct0p1-r3` | 221 | $4,561 | 0.62 | $9,233 | 17.0 % | Y Y Y n n | - |
| squeeze-NQ-tf15 · nyam | long | 72 % | $1,125 | Y/Y/n | `sq_typenr7_pts30-r2` | 10 | $1,125 | 0.38 | $3,930 | 100.0 % | n Y Y n Y | - |
| squeeze-NQ-tf15 · nyam | short | 68 % | $3,122 | Y/n/n | `sq_typenr7_pts30-r0` | 9 | $3,124 | 0.44 | $2,531 | 67.2 % | n Y Y n n | - |
| squeeze-NQ-tf30 · pm | adx_hi | 62 % | $894 | Y/n/n | `sq_typebbkc_atr1p5-r0` | 12 | $967 | 0.34 | -$709 | 15.4 % | n Y n n n | - |
| squeeze-NQ-tf30 · pm | adx_lo | 71 % | $5,008 | Y/Y/n | `sq_typebbkc_pct0p2-r3` | 25 | $5,010 | 1.32 | $4,091 | 56.8 % | n Y Y n n | - |
| squeeze-NQ-tf30 · pm | vol_hi | 61 % | $1,156 | Y/n/n | `sq_typebbkc_pts20-r0` | 21 | $1,156 | 0.33 | $4,406 | 28.4 % | n Y Y n n | - |
| squeeze-NQ-tf30 · pm | vol_lo | 86 % | $6,336 | Y/Y/Y | `sq_typebbkc_pct0p2-r0` | 17 | $6,327 | 1.04 | $4,408 | 74.4 % | n Y Y n n | - |
| squeeze-NQ-tf30 · pm | news_only | 49 % | -$14 | n/n/n | `sq_typeinside_pts30-r1` | 21 | $51 | 0.02 | -$856 | 31.5 % | n n n n n | - |
| squeeze-NQ-tf30 · pm | news_never | 80 % | $8,390 | Y/Y/Y | `sq_typebbkc_atr1p5-r0` | 33 | $8,653 | 1.22 | $8,782 | 11.0 % | n Y Y n n | - |
| squeeze-NQ-tf30 · pm | long | 86 % | $6,724 | Y/Y/Y | `sq_typenr7_pts10-r1` | 220 | $6,660 | 2.25 | $6,396 | 100.0 % | Y Y Y Y Y | PASS on BUILD |
| squeeze-NQ-tf30 · pm | short | 51 % | $367 | n/n/n | `sq_typebbkc_pts30-r0` | 17 | $437 | 0.13 | -$4,323 | 0.8 % | n n n n n | - |
| squeeze-NQ-tf30 · pre | adx_hi | 34 % | -$1,360 | n/n/n | `sq_typeinside_atr3-r1` | 37 | $92 | 0.01 | -$22,821 | 15.3 % | n n n n n | - |
| squeeze-NQ-tf30 · pre | adx_lo | 94 % | $2,820 | Y/Y/Y | `sq_typenr7_pts20-r3` | 12 | $3,112 | 1.09 | $1,857 | 77.6 % | n Y Y n n | - |
| squeeze-NQ-tf30 · pre | vol_hi | 66 % | $1,314 | Y/n/n | `sq_typenr7_pts20-r0` | 19 | $1,339 | 0.15 | -$2,221 | 40.0 % | n Y n n n | - |
| squeeze-NQ-tf30 · pre | vol_lo | 75 % | $1,716 | Y/Y/n | `sq_typenr7_pct0p2-r0` | 20 | $1,695 | 0.24 | -$389 | 56.8 % | n Y n n n | - |
| squeeze-NQ-tf30 · pre | news_only | 40 % | -$174 | n/n/n | `sq_typenr7_atr1p5-r2` | 7 | $12 | 0.00 | -$1,112 | 68.7 % | n n n n n | - |
| squeeze-NQ-tf30 · pre | news_never | 70 % | $1,702 | Y/Y/n | `sq_typeinside_pts20-r2` | 72 | $1,867 | 0.38 | -$2,707 | 36.1 % | n Y n n n | - |
| squeeze-NQ-tf30 · pre | long | 67 % | $1,198 | Y/n/n | `sq_typeinside_pts10-r1` | 41 | $1,116 | 0.86 | -$358 | 8.0 % | n Y n n n | - |
| squeeze-NQ-tf30 · pre | short | 53 % | $340 | n/n/n | `sq_typenr7_pct0p1-r1` | 24 | $334 | 0.23 | -$3,437 | 0.0 % | n n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* `squeeze-NQ-tf30 · pm` long: exact re-run with dir = long on BUILD: 79 % of variants positive, central `sq_typebbkc_pct0p1-r0` 21 trades, $5,196, t 0.88 (bar 2.02), lift $852 -> FAILS BUILD (the stored-trade split had flattered it).

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
