# vwap_flip on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: A close crossing session VWAP that then holds the new side for `hold` more bars means control of the session's fair price has changed sides (R/SPEC 12: a trend change), and the side that is now offside must exit into the move.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 3 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| vwap_flip-NQ-tf15 · pm | 86 % of 94 | $22,396 | `hold1_pts10-r0` | 703 | $22,118 | 1.26 | 2.02 |
| vwap_flip-NQ-tf15 · pre | 73 % of 64 | $18,166 | `hold1_pts30-r2` | 312 | $16,402 | 1.07 | 2.02 |
| vwap_flip-NQ-tf5 · pre | 74 % of 96 | $15,004 | `hold1_atr3-r1` | 523 | $15,313 | 0.67 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_flip-NQ-tf15 · pm | adx_hi | 79 % | $3,960 | Y/Y/n | `hold1_pct0p1-r2` | 328 | $3,963 | 0.56 | $17,344 | 90.1 % | Y Y Y n n | - |
| vwap_flip-NQ-tf15 · pm | adx_lo | 80 % | $14,568 | Y/Y/n | `hold2_pts30-r2` | 231 | $14,656 | 1.36 | $19,051 | 66.9 % | Y Y Y n n | - |
| vwap_flip-NQ-tf15 · pm | vol_hi | 53 % | $838 | n/n/n | `hold1_atr3-r2` | 226 | $911 | 0.04 | -$15,529 | 12.6 % | Y n n n n | - |
| vwap_flip-NQ-tf15 · pm | vol_lo | 89 % | $16,432 | Y/Y/Y | `hold2_pts30-r1` | 227 | $16,432 | 2.04 | $20,427 | 98.7 % | Y Y Y Y n | - |
| vwap_flip-NQ-tf15 · pm | news_only | 53 % | $395 | n/n/n | `hold2_pts10-r1` | 60 | $395 | 0.25 | $1,394 | 89.1 % | n n Y n n | - |
| vwap_flip-NQ-tf15 · pm | news_never | 82 % | $19,805 | Y/Y/Y | `hold3_pct0p2-r3` | 295 | $19,805 | 1.69 | $10,094 | 74.3 % | Y Y Y n n | - |
| vwap_flip-NQ-tf15 · pm | long | 89 % | $10,026 | Y/Y/Y | `hold3_atr1p5-r0` | 208 | $9,963 | 0.78 | -$125,119 | 0.0 % | Y Y n n n | - |
| vwap_flip-NQ-tf15 · pm | short | 76 % | $9,097 | Y/Y/n | `hold1_atr3-r0` | 222 | $9,097 | 0.40 | -$57,902 | 0.0 % | Y Y n n n | - |
| vwap_flip-NQ-tf15 · pre | adx_hi | 75 % | $8,569 | Y/Y/n | `hold2_atr1p5-r1` | 74 | $8,639 | 1.23 | $7,489 | 61.6 % | n Y Y n n | - |
| vwap_flip-NQ-tf15 · pre | adx_lo | 75 % | $10,708 | Y/Y/n | `hold1_atr3-r1` | 153 | $11,568 | 0.66 | $19,240 | 67.2 % | Y Y Y n n | - |
| vwap_flip-NQ-tf15 · pre | vol_hi | 48 % | -$412 | n/n/n | `hold2_pts20-r3` | 66 | $291 | 0.05 | -$1,632 | 16.9 % | n n n n n | - |
| vwap_flip-NQ-tf15 · pre | vol_lo | 83 % | $18,602 | Y/Y/Y | `hold1_atr1p5-r3` | 162 | $17,867 | 1.15 | $13,763 | 49.6 % | Y Y Y n n | - |
| vwap_flip-NQ-tf15 · pre | news_only | 56 % | $1,520 | n/n/n | `hold1_pct0p2-r3` | 40 | $1,720 | 0.27 | -$789 | 38.1 % | n n n n n | - |
| vwap_flip-NQ-tf15 · pre | news_never | 72 % | $11,722 | Y/Y/n | `hold2_atr1p5-r1` | 125 | $11,970 | 1.51 | $13,853 | 61.4 % | Y Y Y n n | - |
| vwap_flip-NQ-tf15 · pre | long | 67 % | $9,234 | Y/n/n | `hold1_atr1p5-r1` | 159 | $9,164 | 0.94 | -$17,087 | 0.0 % | Y Y n n n | - |
| vwap_flip-NQ-tf15 · pre | short | 75 % | $7,648 | Y/Y/n | `hold1_atr1p5-r3` | 153 | $7,333 | 0.45 | -$53,041 | 0.0 % | Y Y n n n | - |
| vwap_flip-NQ-tf5 · pre | adx_hi | 60 % | $1,098 | Y/n/n | `hold2_pts30-r3` | 242 | $1,132 | 0.07 | -$2,352 | 21.9 % | Y Y n n n | - |
| vwap_flip-NQ-tf5 · pre | adx_lo | 79 % | $16,932 | Y/Y/n | `hold1_atr1p5-r2` | 327 | $16,912 | 1.32 | $20,035 | 98.3 % | Y Y Y n n | - |
| vwap_flip-NQ-tf5 · pre | vol_hi | 47 % | -$1,526 | n/n/n | `hold2_pts10-r3` | 277 | $2 | 0.00 | $4,193 | 50.0 % | Y n Y n n | - |
| vwap_flip-NQ-tf5 · pre | vol_lo | 85 % | $22,100 | Y/Y/Y | `hold2_pts20-r2` | 276 | $22,031 | 2.24 | $26,335 | 97.8 % | Y Y Y Y n | - |
| vwap_flip-NQ-tf5 · pre | news_only | 79 % | $6,676 | Y/Y/n | `hold2_atr3-r3` | 57 | $6,632 | 0.38 | -$3,908 | 75.0 % | n Y n n n | - |
| vwap_flip-NQ-tf5 · pre | news_never | 56 % | $3,112 | n/n/n | `hold2_pts30-r2` | 461 | $2,576 | 0.14 | $4,734 | 18.7 % | Y n Y n n | - |
| vwap_flip-NQ-tf5 · pre | long | 74 % | $10,530 | Y/Y/n | `hold2_atr1p5-r2` | 280 | $10,835 | 0.85 | -$23,497 | 0.1 % | Y Y n n n | - |
| vwap_flip-NQ-tf5 · pre | short | 67 % | $3,782 | Y/n/n | `hold3_atr1p5-r3` | 235 | $4,415 | 0.33 | -$45,482 | 0.0 % | Y Y n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
