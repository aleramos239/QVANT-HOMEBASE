# sweep_rev on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: Stop-run exhaustion at prior-day / overnight extremes (EDGE_SPEC C): price trading beyond the prior-day or overnight high / low fills the stops resting there, and a close back inside shows nobody followed through once they were filled, so the breakout traders are trapped and price reverts.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 3 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| sweep_rev-NQ-tf1 · eve | 84 % of 32 | $6,680 | `levelsboth_pts20-r3` | 130 | $6,180 | 0.75 | 2.02 |
| sweep_rev-NQ-tf30 · mid | 64 % of 96 | $2,564 | `levelspd_pts30-r2` | 134 | $2,549 | 0.26 | 2.02 |
| sweep_rev-NQ-tf30 · pre | 67 % of 96 | $2,484 | `levelsboth_pct0p1-r0` | 217 | $2,462 | 0.14 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sweep_rev-NQ-tf1 · eve | adx_hi | 84 % | $5,160 | Y/Y/Y | `levelsboth_pts45-r2` | 55 | $5,335 | 0.55 | $2,930 | 55.0 % | n Y Y n n | - |
| sweep_rev-NQ-tf1 · eve | adx_lo | 56 % | $960 | n/n/n | `levelsboth_atr1p5-r1` | 68 | $768 | 0.38 | $2,085 | 28.2 % | n n Y n n | - |
| sweep_rev-NQ-tf1 · eve | vol_hi | 81 % | $4,776 | Y/Y/Y | `levelsboth_pts10-r3` | 69 | $4,874 | 1.52 | $5,301 | 61.6 % | n Y Y n n | - |
| sweep_rev-NQ-tf1 · eve | vol_lo | 56 % | $1,490 | n/n/n | `levelsboth_atr1p5-r3` | 55 | $1,925 | 0.61 | -$201 | 12.3 % | n n n n n | - |
| sweep_rev-NQ-tf1 · eve | news_only | 34 % | -$226 | n/n/n | `levelsboth_atr1p5-r2` | 12 | $142 | 0.11 | -$176 | 47.3 % | n n n n n | - |
| sweep_rev-NQ-tf1 · eve | news_never | 88 % | $7,558 | Y/Y/Y | `levelsboth_pts10-r3` | 118 | $7,508 | 1.81 | $6,710 | 79.0 % | Y Y Y n n | - |
| sweep_rev-NQ-tf1 · eve | long | 84 % | $3,366 | Y/Y/Y | `levelsboth_atr1p5-r2` | 58 | $3,548 | 0.63 | $7,132 | 99.1 % | n Y Y n n | - |
| sweep_rev-NQ-tf1 · eve | short | 75 % | $1,682 | Y/Y/n | `levelsboth_atr1p5-r1` | 72 | $1,727 | 1.31 | $3,560 | 99.8 % | n Y Y n Y | - |
| sweep_rev-NQ-tf30 · mid | adx_hi | 55 % | $754 | n/n/n | `levelspd_pct0p2-r1` | 58 | $753 | 0.17 | $2,500 | 14.4 % | n n Y n n | - |
| sweep_rev-NQ-tf30 · mid | adx_lo | 60 % | $1,360 | Y/n/n | `levelsboth_pts30-r2` | 170 | $1,360 | 0.12 | $9,891 | 31.2 % | Y Y Y n n | - |
| sweep_rev-NQ-tf30 · mid | vol_hi | 69 % | $3,979 | Y/n/n | `levelspd_pct0p1-r2` | 64 | $3,979 | 1.19 | $6,408 | 76.0 % | n Y Y n n | - |
| sweep_rev-NQ-tf30 · mid | vol_lo | 56 % | $714 | n/n/n | `levelsboth_atr3-r0` | 129 | $789 | 0.03 | $7,984 | 33.2 % | Y n Y n n | - |
| sweep_rev-NQ-tf30 · mid | news_only | 60 % | $1,392 | Y/n/n | `levelspd_pts20-r0` | 20 | $1,375 | 0.28 | $5,434 | 86.5 % | n Y Y n n | - |
| sweep_rev-NQ-tf30 · mid | news_never | 52 % | $148 | n/n/n | `levelsboth_pts20-r3` | 278 | $148 | 0.01 | $38 | 19.2 % | Y n Y n n | - |
| sweep_rev-NQ-tf30 · mid | long | 52 % | $272 | n/n/n | `levelsboth_pts10-r1` | 175 | $250 | 0.09 | $6,845 | 100.0 % | Y n Y n Y | - |
| sweep_rev-NQ-tf30 · mid | short | 58 % | $1,114 | n/n/n | `levelspd_pts10-r3` | 64 | $1,114 | 0.38 | -$416 | 50.9 % | n n n n n | - |
| sweep_rev-NQ-tf30 · pre | adx_hi | 89 % | $4,427 | Y/Y/Y | `levelspd_pts30-r3` | 36 | $4,456 | 0.66 | $5,451 | 90.0 % | n Y Y n n | - |
| sweep_rev-NQ-tf30 · pre | adx_lo | 34 % | -$3,804 | n/n/n | `levelson_pts10-r1` | 72 | $1,097 | 0.60 | $2,184 | 56.0 % | n n Y n n | - |
| sweep_rev-NQ-tf30 · pre | vol_hi | 51 % | $114 | n/n/n | `levelspd_pts10-r0` | 41 | $96 | 0.02 | $6,045 | 30.0 % | n n Y n n | - |
| sweep_rev-NQ-tf30 · pre | vol_lo | 75 % | $3,310 | Y/Y/n | `levelspd_pct0p2-r1` | 44 | $3,149 | 0.84 | $4,731 | 65.9 % | n Y Y n n | - |
| sweep_rev-NQ-tf30 · pre | news_only | 59 % | $2,094 | n/n/n | `levelsboth_pts20-r3` | 41 | $2,151 | 0.45 | $5,358 | 68.8 % | n n Y n n | - |
| sweep_rev-NQ-tf30 · pre | news_never | 52 % | $512 | n/n/n | `levelsboth_pts20-r1` | 176 | $446 | 0.08 | $3,388 | 19.8 % | Y n Y n n | - |
| sweep_rev-NQ-tf30 · pre | long | 65 % | $2,339 | Y/n/n | `levelspd_pts10-r0` | 39 | $2,339 | 0.39 | -$8,422 | 0.0 % | n Y n n n | - |
| sweep_rev-NQ-tf30 · pre | short | 49 % | -$184 | n/n/n | `levelson_pct0p2-r2` | 86 | $76 | 0.01 | -$4,108 | 1.5 % | n n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
