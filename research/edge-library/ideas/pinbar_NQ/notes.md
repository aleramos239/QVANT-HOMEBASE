# pinbar on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: A bar whose wick is most of its range and whose extreme sits at a key level (prior-day H / L / C, the overnight H / L, session VWAP) shows that orders resting at that level absorbed the push (R/SPEC 13: rejection), so the traders who pushed into it are trapped and price reverses away.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| pinbar-NQ-tf5 · london | 67 % of 96 | $6,312 | `wick0p6_pct0p2-r3` | 539 | $6,204 | 0.28 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pinbar-NQ-tf5 · london | adx_hi | 39 % | -$4,034 | n/n/n | `wick0p75_pct0p2-r3` | 105 | $410 | 0.04 | -$14,230 | 26.1 % | Y n n n n | - |
| pinbar-NQ-tf5 · london | adx_lo | 85 % | $8,704 | Y/Y/Y | `wick0p6_atr3-r1` | 279 | $7,974 | 0.68 | $11,149 | 98.3 % | Y Y Y n n | - |
| pinbar-NQ-tf5 · london | vol_hi | 74 % | $3,726 | Y/Y/n | `wick0p75_pts45-r1` | 101 | $3,806 | 0.42 | $1,506 | 26.4 % | Y Y Y n n | - |
| pinbar-NQ-tf5 · london | vol_lo | 49 % | -$702 | n/n/n | `wick0p75_pct0p1-r1` | 119 | $399 | 0.13 | $2,621 | 45.7 % | Y n Y n n | - |
| pinbar-NQ-tf5 · london | news_only | 16 % | -$3,218 | n/n/n | `wick0p75_pts10-r2` | 34 | $129 | 0.08 | $1,164 | 54.2 % | n n Y n n | - |
| pinbar-NQ-tf5 · london | news_never | 72 % | $9,130 | Y/Y/n | `wick0p667_atr1p5-r2` | 364 | $9,339 | 0.83 | $10,569 | 98.8 % | Y Y Y n n | - |
| pinbar-NQ-tf5 · london | long | 64 % | $1,490 | Y/n/n | `wick0p6_pts20-r3` | 298 | $1,608 | 0.13 | -$21,670 | 0.2 % | Y Y n n n | - |
| pinbar-NQ-tf5 · london | short | 58 % | $3,018 | n/n/n | `wick0p6_pts30-r3` | 256 | $2,731 | 0.16 | -$14,446 | 4.0 % | Y n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
