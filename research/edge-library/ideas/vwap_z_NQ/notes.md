# vwap_z on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: VWAP fade = mean reversion to fair price (EDGE_SPEC C): a close zth sigma away from session VWAP is stretched beyond what the session's own volume has accepted, so responsive traders lean against the extreme and late chasers are forced out as price returns toward VWAP.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 3 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| vwap_z-NQ-tf15 · eve | 80 % of 128 | $5,282 | `zth2p5_pts10-r3` | 144 | $5,254 | 1.18 | 2.02 |
| vwap_z-NQ-tf30 · mid | 74 % of 104 | $7,072 | `zth2_pts30-r3` | 99 | $6,914 | 0.69 | 2.02 |
| vwap_z-NQ-tf30 · london | 66 % of 125 | $1,203 | `zth3_pts30-r0` | 3 | $1,203 | 0.40 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_z-NQ-tf15 · eve | adx_hi | 43 % | -$335 | n/n/n | `zth2p5_pts10-r1` | 56 | $26 | 0.02 | $20 | 79.7 % | n n Y n n | - |
| vwap_z-NQ-tf15 · eve | adx_lo | 96 % | $10,012 | Y/Y/Y | `zth1p5_atr1p5-r1` | 593 | $10,183 | 0.87 | $14,196 | 38.3 % | Y Y Y n n | - |
| vwap_z-NQ-tf15 · eve | vol_hi | 69 % | $1,276 | Y/n/n | `zth2_pts10-r2` | 335 | $1,250 | 0.24 | $6,720 | 77.0 % | Y Y Y n n | - |
| vwap_z-NQ-tf15 · eve | vol_lo | 82 % | $6,942 | Y/Y/Y | `zth1p5_atr1p5-r2` | 480 | $7,205 | 0.50 | -$153 | 53.6 % | Y Y n n n | - |
| vwap_z-NQ-tf15 · eve | news_only | 62 % | $922 | Y/n/n | `zth3_pct0p2-r3` | 2 | $922 | 0.45 | $553 | 40.5 % | n Y Y n n | - |
| vwap_z-NQ-tf15 · eve | news_never | 74 % | $3,108 | Y/Y/n | `zth2p5_atr1p5-r2` | 116 | $3,106 | 0.41 | $8,080 | 17.4 % | Y Y Y n n | - |
| vwap_z-NQ-tf15 · eve | long | 73 % | $1,469 | Y/Y/n | `zth2_pts20-r2` | 288 | $1,368 | 0.14 | $46,426 | 100.0 % | Y Y Y n Y | - |
| vwap_z-NQ-tf15 · eve | short | 82 % | $3,158 | Y/Y/Y | `zth2_atr3-r2` | 194 | $3,199 | 0.16 | $66,371 | 100.0 % | Y Y Y n Y | - |
| vwap_z-NQ-tf30 · mid | adx_hi | 38 % | -$592 | n/n/n | `zth2p5_pct0p1-r3` | 7 | $87 | 0.06 | $117 | 50.2 % | n n Y n n | - |
| vwap_z-NQ-tf30 · mid | adx_lo | 80 % | $7,142 | Y/Y/Y | `zth2_pts30-r3` | 47 | $7,142 | 0.98 | $6,369 | 78.8 % | n Y Y n n | - |
| vwap_z-NQ-tf30 · mid | vol_hi | 71 % | $2,743 | Y/Y/n | `zth1p5_pct0p1-r2` | 153 | $2,743 | 0.55 | $7,771 | 98.9 % | Y Y Y n n | - |
| vwap_z-NQ-tf30 · mid | vol_lo | 69 % | $1,796 | Y/n/n | `zth2p5_pts45-r3` | 10 | $1,980 | 0.43 | $599 | 14.4 % | n Y Y n n | - |
| vwap_z-NQ-tf30 · mid | news_only | 15 % | -$1,458 | n/n/n | `zth2p5_pct0p1-r2` | 3 | $13 | 0.02 | -$52 | 38.9 % | n n n n n | - |
| vwap_z-NQ-tf30 · mid | news_never | 80 % | $9,930 | Y/Y/Y | `zth1p5_pts45-r1` | 226 | $9,231 | 0.71 | $17,197 | 69.7 % | Y Y Y n n | - |
| vwap_z-NQ-tf30 · mid | long | 22 % | -$1,118 | n/n/n | `zth2p5_atr1p5-r1` | 8 | $23 | 0.01 | $1,288 | 55.5 % | n n Y n n | - |
| vwap_z-NQ-tf30 · mid | short | 83 % | $6,128 | Y/Y/Y | `zth1p5_pts20-r3` | 161 | $6,331 | 0.71 | $36,470 | 100.0 % | Y Y Y n Y | - |
| vwap_z-NQ-tf30 · london | adx_hi | 53 % | $352 | n/n/n | `zth3_pct0p1-r3` | 2 | $352 | 0.37 | $710 | 33.1 % | n n Y n n | - |
| vwap_z-NQ-tf30 · london | adx_lo | 58 % | $1,077 | n/n/n | `zth1p5_pct0p1-r1` | 426 | $1,066 | 0.19 | $11,847 | 66.2 % | Y n Y n n | - |
| vwap_z-NQ-tf30 · london | vol_hi | 64 % | $1,801 | Y/n/n | `zth1p5_pts10-r3` | 426 | $1,801 | 0.25 | $4,925 | 90.3 % | Y Y Y n n | - |
| vwap_z-NQ-tf30 · london | vol_lo | 47 % | -$13 | n/n/n | `zth1p5_pts20-r2` | 353 | $113 | 0.01 | $13,938 | 20.5 % | Y n Y n n | - |
| vwap_z-NQ-tf30 · london | news_only | 29 % | -$1,718 | n/n/n | `zth1p5_atr1p5-r1` | 73 | $93 | 0.01 | $9,440 | 37.6 % | n n Y n n | - |
| vwap_z-NQ-tf30 · london | news_never | 69 % | $1,203 | Y/n/n | `zth3_pts30-r0` | 3 | $1,203 | 0.40 | $2,565 | 0.0 % | n Y Y n n | - |
| vwap_z-NQ-tf30 · london | long | 41 % | -$294 | n/n/n | `zth3_pct0p1-r1` | 2 | $22 | 0.04 | -$172 | 40.2 % | n n n n n | - |
| vwap_z-NQ-tf30 · london | short | 64 % | $1,306 | Y/n/n | `zth2p5_pts45-r2` | 37 | $1,302 | 0.16 | $19,048 | 100.0 % | n Y Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
