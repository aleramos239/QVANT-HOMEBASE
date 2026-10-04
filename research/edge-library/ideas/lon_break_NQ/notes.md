# lon_break on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: NY resolves the London range: the London (03:00-08:25) high and low bound the overnight inventory, and the NY open's order flow breaks one side and carries.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 2 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| lon_break-NQ-tf1 · nyam | 81 % of 32 | $9,898 | `min_rng_atr0_pts20-r3` | 548 | $10,073 | 0.61 | 2.02 |
| lon_break-NQ-tf5 · nyam | 75 % of 64 | $10,007 | `min_rng_atr0_pts20-r3` | 548 | $10,073 | 0.61 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lon_break-NQ-tf1 · nyam | adx_hi | 72 % | $6,532 | Y/Y/n | `min_rng_atr0_pts20-r3` | 244 | $6,059 | 0.54 | $8,541 | 48.1 % | Y Y Y n n | - |
| lon_break-NQ-tf1 · nyam | adx_lo | 69 % | $3,556 | Y/n/n | `min_rng_atr0_pts10-r2` | 278 | $4,123 | 0.84 | $8,446 | 14.6 % | Y Y Y n n | - |
| lon_break-NQ-tf1 · nyam | vol_hi | 34 % | -$2,854 | n/n/n | `min_rng_atr0_pts30-r1` | 261 | $91 | 0.01 | $1,406 | 12.9 % | Y n Y n n | - |
| lon_break-NQ-tf1 · nyam | vol_lo | 100 % | $14,362 | Y/Y/Y | `min_rng_atr0_pts20-r3` | 269 | $13,529 | 1.13 | $14,721 | 83.1 % | Y Y Y n n | - |
| lon_break-NQ-tf1 · nyam | news_only | 16 % | -$7,679 | n/n/n | `min_rng_atr0_pts10-r1` | 71 | $941 | 0.55 | $2,177 | 52.2 % | n n Y n n | - |
| lon_break-NQ-tf1 · nyam | news_never | 94 % | $12,912 | Y/Y/Y | `min_rng_atr0_atr3-r1` | 477 | $12,717 | 1.31 | $34,772 | 99.5 % | Y Y Y n Y | - |
| lon_break-NQ-tf1 · nyam | long | 91 % | $9,098 | Y/Y/Y | `min_rng_atr0_pts10-r2` | 293 | $9,473 | 1.86 | -$1,984 | 29.5 % | Y Y n n n | - |
| lon_break-NQ-tf1 · nyam | short | 56 % | $405 | n/n/n | `min_rng_atr0_atr1p5-r3` | 255 | $240 | 0.03 | -$7,787 | 15.2 % | Y n n n n | - |
| lon_break-NQ-tf5 · nyam | adx_hi | 69 % | $7,237 | Y/n/n | `min_rng_atr2_atr3-r3` | 242 | $7,147 | 0.26 | -$63,391 | 69.4 % | Y Y n n n | - |
| lon_break-NQ-tf5 · nyam | adx_lo | 72 % | $4,453 | Y/Y/n | `min_rng_atr0_pts20-r2` | 278 | $4,338 | 0.45 | $16,422 | 23.6 % | Y Y Y n n | - |
| lon_break-NQ-tf5 · nyam | vol_hi | 36 % | -$3,067 | n/n/n | `min_rng_atr0_pts30-r1` | 261 | $91 | 0.01 | $7,258 | 12.7 % | Y n Y n n | - |
| lon_break-NQ-tf5 · nyam | vol_lo | 97 % | $17,500 | Y/Y/Y | `min_rng_atr0_pts30-r1` | 269 | $16,884 | 1.72 | $12,855 | 86.6 % | Y Y Y n n | - |
| lon_break-NQ-tf5 · nyam | news_only | 20 % | -$8,759 | n/n/n | `min_rng_atr2_pct0p1-r1` | 64 | $134 | 0.06 | $105 | 31.6 % | n n Y n n | - |
| lon_break-NQ-tf5 · nyam | news_never | 88 % | $14,950 | Y/Y/Y | `min_rng_atr0_pts30-r1` | 477 | $13,107 | 1.00 | $13,805 | 69.4 % | Y Y Y n n | - |
| lon_break-NQ-tf5 · nyam | long | 86 % | $9,490 | Y/Y/Y | `min_rng_atr0_pts10-r2` | 293 | $9,473 | 1.86 | $14,573 | 100.0 % | Y Y Y n Y | - |
| lon_break-NQ-tf5 · nyam | short | 61 % | $1,283 | Y/n/n | `min_rng_atr0_pts45-r1` | 255 | $1,210 | 0.08 | -$5,959 | 27.1 % | Y Y n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
