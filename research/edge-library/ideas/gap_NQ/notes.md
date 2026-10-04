# gap on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: The 09:30 open away from the prior daily close leaves an overnight imbalance that the cash session must resolve: it is faded back to the prior close (fill) or followed in its direction (go).
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| gap-NQ-tf30 · nyam · mode=go | 62 % of 32 | $1,488 | `modego_pts10-r3` | 396 | $1,561 | 0.22 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gap-NQ-tf30 · nyam · mode=go | adx_hi | 25 % | -$5,170 | n/n/n | `modego_pct0p1-r3` | 190 | $405 | 0.06 | $672 | 60.7 % | Y n Y n n | - |
| gap-NQ-tf30 · nyam · mode=go | adx_lo | 84 % | $5,256 | Y/Y/Y | `modego_pts20-r1` | 196 | $5,146 | 0.91 | $6,161 | 64.8 % | Y Y Y n n | - |
| gap-NQ-tf30 · nyam · mode=go | vol_hi | 41 % | -$2,798 | n/n/n | `modego_pts10-r1` | 202 | $2,242 | 0.78 | $2,780 | 15.6 % | Y n Y n n | - |
| gap-NQ-tf30 · nyam · mode=go | vol_lo | 66 % | $1,785 | Y/n/n | `modego_pts30-r2` | 190 | $1,725 | 0.15 | -$14,029 | 59.6 % | Y Y n n n | - |
| gap-NQ-tf30 · nyam · mode=go | news_only | 38 % | -$1,142 | n/n/n | `modego_pts10-r2` | 51 | $206 | 0.10 | $3,457 | 36.5 % | n n Y n n | - |
| gap-NQ-tf30 · nyam · mode=go | news_never | 66 % | $2,890 | Y/n/n | `modego_pts10-r3` | 345 | $2,585 | 0.39 | $6,571 | 68.2 % | Y Y Y n n | - |
| gap-NQ-tf30 · nyam · mode=go | long | 38 % | -$2,728 | n/n/n | `modego_pts45-r3` | 190 | $195 | 0.01 | -$39,864 | 0.0 % | Y n n n n | - |
| gap-NQ-tf30 · nyam · mode=go | short | 66 % | $4,358 | Y/n/n | `modego_pts30-r3` | 206 | $4,191 | 0.28 | -$11,827 | 2.6 % | Y Y n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
