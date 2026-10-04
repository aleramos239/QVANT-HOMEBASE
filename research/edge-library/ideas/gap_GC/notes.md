# gap on GC — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: The 09:30 open away from the prior daily close leaves an overnight imbalance that the cash session must resolve: it is faded back to the prior close (fill) or followed in its direction (go).
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| gap-GC-tf15 · nyam · mode=go | 69 % of 32 | $3,195 | `modego_pts5-r1` | 415 | $3,180 | 0.32 | 1.24 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gap-GC-tf15 · nyam · mode=go | adx_hi | 94 % | $6,984 | Y/Y/Y | `modego_pts5-r2` | 224 | $7,374 | 0.76 | $7,506 | 82.0 % | Y Y Y n n | - |
| gap-GC-tf15 · nyam · mode=go | adx_lo | 12 % | -$4,169 | n/n/n | `modego_pts3-r0` | 181 | $106 | 0.01 | -$5,953 | 34.0 % | Y n n n n | - |
| gap-GC-tf15 · nyam · mode=go | vol_hi | 97 % | $6,893 | Y/Y/Y | `modego_pct0p1-r3` | 208 | $6,818 | 1.34 | $6,234 | 92.6 % | Y Y Y Y n | - |
| gap-GC-tf15 · nyam · mode=go | vol_lo | 12 % | -$4,682 | n/n/n | `modego_atr3-r2` | 203 | $2,038 | 0.17 | $16,562 | 41.1 % | Y n Y n n | - |
| gap-GC-tf15 · nyam · mode=go | news_only | 28 % | -$1,396 | n/n/n | `modego_atr3-r1` | 49 | $184 | 0.03 | $1,278 | 48.1 % | n n Y n n | - |
| gap-GC-tf15 · nyam · mode=go | news_never | 81 % | $5,421 | Y/Y/Y | `modego_atr1p5-r2` | 366 | $5,366 | 0.44 | $14,250 | 64.9 % | Y Y Y n n | - |
| gap-GC-tf15 · nyam · mode=go | long | 97 % | $7,241 | Y/Y/Y | `modego_atr1p5-r3` | 216 | $8,176 | 0.75 | $11,472 | 99.5 % | Y Y Y n Y | - |
| gap-GC-tf15 · nyam · mode=go | short | 9 % | -$4,176 | n/n/n | `modego_pts5-r0` | 199 | $924 | 0.09 | -$5,807 | 6.7 % | Y n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: RSI direction, inverse (Level 2 tools: NQ only); verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
