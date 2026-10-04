# pinbar on ES — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: A bar whose wick is most of its range and whose extreme sits at a key level (prior-day H / L / C, the overnight H / L, session VWAP) shows that orders resting at that level absorbed the push (R/SPEC 13: rejection), so the traders who pushed into it are trapped and price reverses away.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| pinbar-ES-tf30 · mid | 73 % of 96 | $6,565 | `wick0p75_atr1p5-r2` | 26 | $6,608 | 1.22 | 1.30 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pinbar-ES-tf30 · mid | adx_hi | 87 % | $6,351 | Y/Y/Y | `wick0p6_pct0p2-r2` | 40 | $6,428 | 1.71 | $4,664 | 84.0 % | n Y Y Y n | - |
| pinbar-ES-tf30 · mid | adx_lo | 54 % | $1,074 | n/n/n | `wick0p75_atr1p5-r3` | 19 | $1,074 | 0.25 | $1,255 | 3.5 % | n n Y n n | - |
| pinbar-ES-tf30 · mid | vol_hi | 68 % | $3,830 | Y/n/n | `wick0p6_pct0p2-r2` | 47 | $4,012 | 1.02 | $1,943 | 53.2 % | n Y Y n n | - |
| pinbar-ES-tf30 · mid | vol_lo | 76 % | $2,622 | Y/Y/n | `wick0p6_pts12-r1` | 54 | $2,622 | 0.65 | $80 | 22.0 % | n Y Y n n | - |
| pinbar-ES-tf30 · mid | news_only | 0 % | -$1,951 | n/n/n | `None` | 0 | $0 | 0.00 | n/a | n/a | n n n n n | - |
| pinbar-ES-tf30 · mid | news_never | 77 % | $6,565 | Y/Y/n | `wick0p75_atr1p5-r2` | 26 | $6,608 | 1.22 | $5,696 | 0.0 % | n Y Y n n | - |
| pinbar-ES-tf30 · mid | long | 48 % | -$98 | n/n/n | `wick0p75_atr3-r0` | 15 | $202 | 0.04 | $40 | 50.3 % | n n Y n n | - |
| pinbar-ES-tf30 · mid | short | 91 % | $6,248 | Y/Y/Y | `wick0p6_pts5-r3` | 46 | $6,241 | 1.88 | $1,819 | 85.3 % | n Y Y Y n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: RSI direction, inverse (Level 2 tools: NQ only); verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
