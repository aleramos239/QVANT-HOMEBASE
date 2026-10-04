# vwap_band on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: VWAP fade = mean reversion to fair price (EDGE_SPEC C): a close beyond session VWAP +/- band sigma followed by a close back inside is a failed extension, so the traders who chased it must exit and their orders carry price back toward VWAP.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 4 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| vwap_band-NQ-tf30 · london | 75 % of 126 | $3,088 | `band2p5_pct0p1-r2` | 52 | $3,082 | 1.02 | 2.02 |
| vwap_band-NQ-tf30 · eve | 73 % of 123 | $3,592 | `band1p5_pct0p1-r1` | 637 | $3,592 | 0.51 | 2.02 |
| vwap_band-NQ-tf5 · eve | 83 % of 128 | $8,260 | `band2_pts20-r2` | 860 | $8,260 | 0.49 | 2.02 |
| vwap_band-NQ-tf30 · mid | 68 % of 104 | $1,667 | `band2_pts45-r2` | 48 | $1,723 | 0.22 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_band-NQ-tf30 · london | adx_hi | 50 % | -$168 | n/n/n | `band3_pct0p1-r1` | 2 | $67 | 0.13 | $87 | 34.1 % | n n Y n n | - |
| vwap_band-NQ-tf30 · london | adx_lo | 75 % | $3,095 | Y/Y/n | `band2_pct0p1-r2` | 105 | $3,095 | 0.74 | $6,552 | 53.7 % | Y Y Y n n | - |
| vwap_band-NQ-tf30 · london | vol_hi | 67 % | $1,938 | Y/n/n | `band1p5_pct0p2-r3` | 244 | $2,024 | 0.14 | $9,892 | 48.4 % | Y Y Y n n | - |
| vwap_band-NQ-tf30 · london | vol_lo | 63 % | $782 | Y/n/n | `band3_pct0p2-r3` | 2 | $782 | 0.42 | $1,247 | 65.2 % | n Y Y n n | - |
| vwap_band-NQ-tf30 · london | news_only | 36 % | -$1,414 | n/n/n | `band1p5_pct0p2-r2` | 62 | $12 | 0.00 | $4,379 | 48.4 % | n n Y n n | - |
| vwap_band-NQ-tf30 · london | news_never | 81 % | $3,585 | Y/Y/Y | `band1p5_pct0p1-r1` | 482 | $3,587 | 0.58 | $13,452 | 88.5 % | Y Y Y n n | - |
| vwap_band-NQ-tf30 · london | long | 52 % | $187 | n/n/n | `band3_atr3-r0` | 2 | $187 | 0.03 | $4,605 | 100.0 % | n n Y n Y | - |
| vwap_band-NQ-tf30 · london | short | 79 % | $5,704 | Y/Y/n | `band2_pct0p1-r2` | 119 | $5,704 | 1.27 | $16,034 | 100.0 % | Y Y Y n Y | - |
| vwap_band-NQ-tf30 · eve | adx_hi | 65 % | $2,081 | Y/n/n | `band2p5_pts45-r0` | 16 | $2,081 | 0.25 | -$3,875 | 33.3 % | n Y n n n | - |
| vwap_band-NQ-tf30 · eve | adx_lo | 74 % | $2,486 | Y/Y/n | `band2_pts45-r0` | 121 | $2,486 | 0.10 | $26,726 | 29.3 % | Y Y Y n n | - |
| vwap_band-NQ-tf30 · eve | vol_hi | 45 % | -$227 | n/n/n | `band2_pct0p1-r3` | 124 | $244 | 0.04 | -$10,702 | 22.1 % | Y n n n n | - |
| vwap_band-NQ-tf30 · eve | vol_lo | 83 % | $5,584 | Y/Y/Y | `band2_pts20-r3` | 104 | $5,584 | 0.75 | $13,012 | 64.5 % | Y Y Y n n | - |
| vwap_band-NQ-tf30 · eve | news_only | 35 % | -$1,184 | n/n/n | `band2p5_pct0p2-r1` | 6 | $31 | 0.02 | -$15 | 51.5 % | n n n n n | - |
| vwap_band-NQ-tf30 · eve | news_never | 76 % | $4,085 | Y/Y/n | `band2p5_atr1p5-r0` | 45 | $4,085 | 0.30 | $6,787 | 70.0 % | n Y Y n n | - |
| vwap_band-NQ-tf30 · eve | long | 53 % | $281 | n/n/n | `band3_pct0p1-r1` | 1 | $281 | 0.00 | $575 | 100.0 % | n n Y n Y | - |
| vwap_band-NQ-tf30 · eve | short | 82 % | $4,343 | Y/Y/Y | `band2_pts30-r0` | 103 | $4,343 | 0.22 | $44,832 | 100.0 % | Y Y Y n Y | - |
| vwap_band-NQ-tf5 · eve | adx_hi | 67 % | $3,078 | Y/n/n | `band2_atr1p5-r2` | 442 | $3,062 | 0.26 | $26 | 25.2 % | Y Y Y n n | - |
| vwap_band-NQ-tf5 · eve | adx_lo | 83 % | $6,672 | Y/Y/Y | `band1p5_pct0p1-r1` | 750 | $6,790 | 0.90 | $14,694 | 95.3 % | Y Y Y n n | - |
| vwap_band-NQ-tf5 · eve | vol_hi | 80 % | $4,262 | Y/Y/n | `band2p5_atr3-r3` | 148 | $4,268 | 0.27 | $15,339 | 43.1 % | Y Y Y n n | - |
| vwap_band-NQ-tf5 · eve | vol_lo | 77 % | $3,818 | Y/Y/n | `band3_pts20-r2` | 26 | $3,826 | 1.22 | $7,994 | 81.9 % | n Y Y n n | - |
| vwap_band-NQ-tf5 · eve | news_only | 40 % | -$1,574 | n/n/n | `band3_atr1p5-r3` | 11 | $296 | 0.15 | $1,915 | 21.5 % | n n Y n n | - |
| vwap_band-NQ-tf5 · eve | news_never | 88 % | $9,800 | Y/Y/Y | `band2p5_pts45-r1` | 263 | $9,948 | 0.68 | $15,963 | 56.5 % | Y Y Y n n | - |
| vwap_band-NQ-tf5 · eve | long | 79 % | $5,229 | Y/Y/n | `band3_atr1p5-r2` | 33 | $5,288 | 1.60 | $2,696 | 88.0 % | n Y Y n n | - |
| vwap_band-NQ-tf5 · eve | short | 74 % | $3,672 | Y/Y/n | `band2_pct0p1-r3` | 450 | $3,865 | 0.37 | $61,010 | 100.0 % | Y Y Y n Y | - |
| vwap_band-NQ-tf30 · mid | adx_hi | 10 % | -$2,212 | n/n/n | `band2_pts10-r0` | 26 | $111 | 0.02 | $528 | 12.2 % | n n Y n n | - |
| vwap_band-NQ-tf30 · mid | adx_lo | 83 % | $5,360 | Y/Y/Y | `band1p5_pct0p2-r1` | 55 | $5,360 | 1.32 | $5,538 | 94.2 % | n Y Y n n | - |
| vwap_band-NQ-tf30 · mid | vol_hi | 87 % | $2,983 | Y/Y/Y | `band2p5_pts30-r3` | 3 | $2,983 | 1.24 | $1,651 | 55.6 % | n Y Y n n | - |
| vwap_band-NQ-tf30 · mid | vol_lo | 40 % | -$429 | n/n/n | `band2p5_pct0p1-r1` | 6 | $111 | 0.15 | $663 | 49.6 % | n n Y n n | - |
| vwap_band-NQ-tf30 · mid | news_only | 47 % | -$216 | n/n/n | `band1p5_atr3-r2` | 17 | $307 | 0.02 | $3,159 | 51.1 % | n n Y n n | - |
| vwap_band-NQ-tf30 · mid | news_never | 73 % | $3,006 | Y/Y/n | `band2_pts20-r3` | 41 | $3,006 | 0.64 | $1,152 | 66.5 % | n Y Y n n | - |
| vwap_band-NQ-tf30 · mid | long | 33 % | -$1,376 | n/n/n | `band2_pts45-r3` | 24 | $179 | 0.03 | $12,843 | 100.0 % | n n Y n Y | - |
| vwap_band-NQ-tf30 · mid | short | 83 % | $3,724 | Y/Y/Y | `band2_atr1p5-r1` | 24 | $3,724 | 0.50 | $7,240 | 100.0 % | n Y Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
