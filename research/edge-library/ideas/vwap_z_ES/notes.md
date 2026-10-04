# vwap_z on ES — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: VWAP fade = mean reversion to fair price (EDGE_SPEC C): a close zth sigma away from session VWAP is stretched beyond what the session's own volume has accepted, so responsive traders lean against the extreme and late chasers are forced out as price returns toward VWAP.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 2 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| vwap_z-ES-tf30 · mid | 68 % of 125 | $892 | `zth2p5_pts8-r2` | 24 | $892 | 0.32 | 1.30 |
| vwap_z-ES-tf30 · asia | 67 % of 127 | $1,744 | `zth2p5_pts12-r0` | 39 | $1,744 | 0.15 | 1.30 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_z-ES-tf30 · mid | adx_hi | 52 % | $192 | n/n/n | `zth3_pct0p1-r2` | 2 | $192 | 0.30 | $416 | 70.5 % | n n Y n n | - |
| vwap_z-ES-tf30 · mid | adx_lo | 60 % | $388 | n/n/n | `zth3_pts8-r1` | 3 | $376 | 0.46 | $471 | 30.8 % | n n Y n n | - |
| vwap_z-ES-tf30 · mid | vol_hi | 76 % | $1,192 | Y/Y/n | `zth1p5_pct0p1-r1` | 152 | $1,192 | 0.44 | $8,460 | 99.9 % | Y Y Y n Y | - |
| vwap_z-ES-tf30 · mid | vol_lo | 40 % | -$520 | n/n/n | `zth3_atr1p5-r1` | 2 | $4 | 0.00 | -$8 | 40.0 % | n n n n n | - |
| vwap_z-ES-tf30 · mid | news_only | 24 % | -$938 | n/n/n | `zth1p5_pts12-r0` | 46 | $216 | 0.03 | -$17,297 | 46.0 % | n n n n n | - |
| vwap_z-ES-tf30 · mid | news_never | 70 % | $942 | Y/n/n | `zth3_pts12-r2` | 5 | $942 | 0.59 | $2,941 | 0.0 % | n Y Y n n | - |
| vwap_z-ES-tf30 · mid | long | 10 % | -$3,442 | n/n/n | `zth2p5_pts5-r3` | 11 | $106 | 0.07 | $147 | 32.6 % | n n Y n n | - |
| vwap_z-ES-tf30 · mid | short | 82 % | $2,686 | Y/Y/Y | `zth2p5_pct0p2-r3` | 13 | $2,686 | 0.91 | $5,021 | 100.0 % | n Y Y n Y | - |
| vwap_z-ES-tf30 · asia | adx_hi | 71 % | $1,847 | Y/Y/n | `zth2p5_pts12-r2` | 11 | $1,906 | 0.67 | $1,631 | 78.1 % | n Y Y n n | - |
| vwap_z-ES-tf30 · asia | adx_lo | 51 % | $205 | n/n/n | `zth3_pts5-r1` | 5 | $205 | 0.33 | $641 | 82.4 % | n n Y n n | - |
| vwap_z-ES-tf30 · asia | vol_hi | 68 % | $889 | Y/n/n | `zth2_pct0p1-r1` | 84 | $889 | 0.44 | $1,411 | 95.3 % | n Y Y n n | - |
| vwap_z-ES-tf30 · asia | vol_lo | 47 % | -$162 | n/n/n | `zth1p5_pct0p1-r2` | 206 | $38 | 0.01 | -$2,602 | 64.8 % | Y n n n n | - |
| vwap_z-ES-tf30 · asia | news_only | 46 % | -$100 | n/n/n | `zth2_pct0p1-r2` | 28 | $26 | 0.02 | $1,208 | 49.3 % | n n Y n n | - |
| vwap_z-ES-tf30 · asia | news_never | 61 % | $520 | Y/n/n | `zth2p5_pts2p5-r2` | 32 | $510 | 0.47 | $163 | 67.4 % | n Y Y n n | - |
| vwap_z-ES-tf30 · asia | long | 50 % | $34 | n/n/n | `zth3_atr1p5-r1` | 7 | $34 | 0.03 | $1,285 | 100.0 % | n n Y n Y | - |
| vwap_z-ES-tf30 · asia | short | 71 % | $1,101 | Y/Y/n | `zth1p5_pct0p1-r2` | 221 | $1,104 | 0.23 | $5,800 | 100.0 % | Y Y Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: RSI direction, inverse (Level 2 tools: NQ only); verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
