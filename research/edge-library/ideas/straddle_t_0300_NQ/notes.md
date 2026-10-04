# straddle_t_0300 on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4 (+ the stage-1 book filter / book exit)
* Reason written first: At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (03:00 ET: Europe cash open; SECOND LOOK at 2025-26, it is the old pilot's straddle-tf30 london).
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| straddle_t_0300-NQ-tf30 · london | 69 % of 160 | $8,584 | `offptsA_pct0p1-r2` | 564 | $8,564 | 0.89 | 2.62 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| straddle_t_0300-NQ-tf30 · london | adx_hi | 65 % | $7,151 | Y/n/n | `offptsA_pts20-r1` | 251 | $7,546 | 1.18 | $9,840 | 69.4 % | Y Y Y n n | - |
| straddle_t_0300-NQ-tf30 · london | adx_lo | 64 % | $2,858 | Y/n/n | `offptsA_pts10-r3` | 285 | $2,880 | 0.47 | $934 | 30.6 % | Y Y Y n n | - |
| straddle_t_0300-NQ-tf30 · london | vol_hi | 77 % | $8,613 | Y/Y/n | `offatr0p5_pct0p1-r2` | 271 | $8,586 | 1.28 | $5,850 | 77.5 % | Y Y Y n n | - |
| straddle_t_0300-NQ-tf30 · london | vol_lo | 58 % | $1,364 | n/n/n | `offatr0p5_pct0p1-r2` | 276 | $1,431 | 0.21 | $12,110 | 22.6 % | Y n Y n n | - |
| straddle_t_0300-NQ-tf30 · london | news_only | 41 % | -$1,612 | n/n/n | `offatr0p5_pts30-r1` | 71 | $106 | 0.02 | $1,778 | 43.5 % | n n Y n n | - |
| straddle_t_0300-NQ-tf30 · london | news_never | 74 % | $9,586 | Y/Y/n | `offatr0p5_atr3-r3` | 496 | $9,416 | 0.19 | $42,758 | 58.6 % | Y Y Y n n | - |
| straddle_t_0300-NQ-tf30 · london | long | 88 % | $13,620 | Y/Y/Y | `offptsB_pts10-r0` | 235 | $13,675 | 0.82 | $13,985 | 85.6 % | Y Y Y n n | - |
| straddle_t_0300-NQ-tf30 · london | short | 24 % | -$7,124 | n/n/n | `offptsB_pts30-r1` | 255 | $110 | 0.01 | $8,185 | 82.3 % | Y n Y n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
