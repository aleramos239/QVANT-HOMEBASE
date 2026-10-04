# ib on ES — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: The initial balance (09:30-10:30) is the first hour's accepted range and anchors the NY day: a break of it carries as the day's range extends, and a break that closes back inside has failed and reverts to the IB mid.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 3 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| ib-ES-tf30 · mid · mode=break | 75 % of 32 | $9,920 | `modebreak_pct0p1-r0` | 323 | $9,796 | 0.73 | 1.30 |
| ib-ES-tf1 · mid · mode=break | 66 % of 32 | $6,120 | `modebreak_pts8-r2` | 323 | $6,546 | 0.65 | 1.30 |
| ib-ES-tf30 · pm · mode=break | 62 % of 32 | $2,173 | `modebreak_atr1p5-r1` | 224 | $1,954 | 0.18 | 1.30 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ib-ES-tf30 · mid · mode=break | adx_hi | 81 % | $5,050 | Y/Y/Y | `modebreak_atr1p5-r2` | 136 | $5,218 | 0.41 | -$4,000 | 45.5 % | Y Y n n n | - |
| ib-ES-tf30 · mid · mode=break | adx_lo | 72 % | $4,888 | Y/Y/n | `modebreak_pts8-r1` | 175 | $5,112 | 0.95 | $6,662 | 58.2 % | Y Y Y n n | - |
| ib-ES-tf30 · mid · mode=break | vol_hi | 31 % | -$3,440 | n/n/n | `modebreak_atr1p5-r0` | 157 | $2,072 | 0.14 | -$13,397 | 9.6 % | Y n n n n | - |
| ib-ES-tf30 · mid · mode=break | vol_lo | 94 % | $14,304 | Y/Y/Y | `modebreak_atr1p5-r1` | 160 | $14,535 | 1.62 | $17,736 | 92.7 % | Y Y Y Y n | - |
| ib-ES-tf30 · mid · mode=break | news_only | 9 % | -$2,454 | n/n/n | `modebreak_pct0p1-r1` | 40 | $252 | 0.18 | $2,348 | 77.2 % | n n Y n n | - |
| ib-ES-tf30 · mid · mode=break | news_never | 75 % | $14,487 | Y/Y/n | `modebreak_pts12-r1` | 283 | $14,918 | 1.53 | $21,843 | 98.9 % | Y Y Y Y n | - |
| ib-ES-tf30 · mid · mode=break | long | 84 % | $11,911 | Y/Y/Y | `modebreak_pct0p2-r2` | 166 | $11,911 | 1.55 | -$2,260 | 23.2 % | Y Y n Y n | - |
| ib-ES-tf30 · mid · mode=break | short | 47 % | -$484 | n/n/n | `modebreak_pct0p2-r1` | 157 | $310 | 0.06 | -$5,161 | 2.2 % | Y n n n n | - |
| ib-ES-tf1 · mid · mode=break | adx_hi | 72 % | $3,944 | Y/Y/n | `modebreak_atr1p5-r3` | 136 | $3,956 | 0.72 | $2,528 | 82.3 % | Y Y Y n n | - |
| ib-ES-tf1 · mid · mode=break | adx_lo | 53 % | $512 | n/n/n | `modebreak_atr1p5-r0` | 175 | $375 | 0.04 | -$16,727 | 29.7 % | Y n n n n | - |
| ib-ES-tf1 · mid · mode=break | vol_hi | 28 % | -$3,734 | n/n/n | `modebreak_pts2p5-r0` | 157 | $2,497 | 0.34 | -$12,500 | 30.8 % | Y n n n n | - |
| ib-ES-tf1 · mid · mode=break | vol_lo | 88 % | $8,841 | Y/Y/Y | `modebreak_pts5-r3` | 160 | $9,160 | 1.54 | $8,788 | 98.7 % | Y Y Y Y n | - |
| ib-ES-tf1 · mid · mode=break | news_only | 16 % | -$1,535 | n/n/n | `modebreak_atr1p5-r3` | 40 | $190 | 0.06 | $1,846 | 51.1 % | n n Y n n | - |
| ib-ES-tf1 · mid · mode=break | news_never | 66 % | $8,437 | Y/n/n | `modebreak_atr3-r2` | 283 | $8,468 | 0.75 | $9,346 | 90.1 % | Y Y Y n n | - |
| ib-ES-tf1 · mid · mode=break | long | 78 % | $8,224 | Y/Y/n | `modebreak_pts8-r1` | 166 | $7,624 | 1.48 | -$7,433 | 1.8 % | Y Y n Y n | - |
| ib-ES-tf1 · mid · mode=break | short | 25 % | -$2,378 | n/n/n | `modebreak_pct0p2-r1` | 157 | $310 | 0.06 | -$9,298 | 0.5 % | Y n n n n | - |
| ib-ES-tf30 · pm · mode=break | adx_hi | 38 % | -$1,221 | n/n/n | `modebreak_pts12-r3` | 85 | $85 | 0.01 | -$5,897 | 30.3 % | n n n n n | - |
| ib-ES-tf30 · pm · mode=break | adx_lo | 53 % | $942 | n/n/n | `modebreak_pct0p1-r0` | 130 | $605 | 0.10 | -$4,885 | 30.9 % | Y n n n n | - |
| ib-ES-tf30 · pm · mode=break | vol_hi | 62 % | $1,652 | Y/n/n | `modebreak_atr1p5-r3` | 112 | $1,477 | 0.13 | -$14,098 | 29.0 % | Y Y n n n | - |
| ib-ES-tf30 · pm · mode=break | vol_lo | 56 % | $1,432 | n/n/n | `modebreak_pts2p5-r0` | 106 | $1,451 | 0.31 | -$1,129 | 66.8 % | Y n n n n | - |
| ib-ES-tf30 · pm · mode=break | news_only | 3 % | -$3,924 | n/n/n | `modebreak_pct0p1-r1` | 34 | $526 | 0.40 | $2,702 | 75.1 % | n n Y n n | - |
| ib-ES-tf30 · pm · mode=break | news_never | 78 % | $7,009 | Y/Y/n | `modebreak_pts8-r3` | 190 | $7,128 | 0.87 | $2,234 | 94.5 % | Y Y Y n n | - |
| ib-ES-tf30 · pm · mode=break | long | 34 % | -$834 | n/n/n | `modebreak_atr1p5-r2` | 118 | $53 | 0.01 | -$32,487 | 0.0 % | Y n n n n | - |
| ib-ES-tf30 · pm · mode=break | short | 69 % | $5,938 | Y/n/n | `modebreak_pts8-r3` | 106 | $6,976 | 1.04 | -$4,328 | 3.6 % | Y Y n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: RSI direction, inverse (Level 2 tools: NQ only); verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
