# rsi2 on ES — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: A 2-bar RSI below th (above 100-th) is a short-term exhaustion that snaps back; fade it at the close.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| rsi2-ES-tf30 · eve | 84 % of 96 | $18,853 | `th5_pct0p2-r3` | 416 | $18,736 | 1.21 | 1.30 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rsi2-ES-tf30 · eve | adx_hi | 49 % | -$113 | n/n/n | `th5_pct0p1-r3` | 202 | $54 | 0.01 | -$5,997 | 29.6 % | Y n n n n | - |
| rsi2-ES-tf30 · eve | adx_lo | 86 % | $21,830 | Y/Y/Y | `th5_atr1p5-r3` | 227 | $21,942 | 1.94 | $15,461 | 81.0 % | Y Y Y Y n | - |
| rsi2-ES-tf30 · eve | vol_hi | 85 % | $15,914 | Y/Y/Y | `th5_atr1p5-r2` | 202 | $15,417 | 1.36 | $19,282 | 68.5 % | Y Y Y Y n | - |
| rsi2-ES-tf30 · eve | vol_lo | 75 % | $5,416 | Y/Y/n | `th5_atr3-r0` | 176 | $5,434 | 0.32 | -$6,314 | 17.8 % | Y Y n n n | - |
| rsi2-ES-tf30 · eve | news_only | 86 % | $5,324 | Y/Y/Y | `th5_atr3-r1` | 44 | $5,312 | 0.91 | $8,256 | 52.1 % | n Y Y n n | - |
| rsi2-ES-tf30 · eve | news_never | 81 % | $12,679 | Y/Y/Y | `th5_atr1p5-r0` | 372 | $12,687 | 0.57 | -$786 | 12.8 % | Y Y n n n | - |
| rsi2-ES-tf30 · eve | long | 70 % | $8,621 | Y/n/n | `th10_pts5-r2` | 380 | $8,530 | 1.18 | $37,424 | 100.0 % | Y Y Y n Y | - |
| rsi2-ES-tf30 · eve | short | 71 % | $7,506 | Y/Y/n | `th5_atr1p5-r3` | 213 | $7,860 | 0.69 | $29,247 | 100.0 % | Y Y Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: RSI direction, inverse (Level 2 tools: NQ only); verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
