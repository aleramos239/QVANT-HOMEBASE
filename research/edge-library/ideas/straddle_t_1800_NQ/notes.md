# straddle_t_1800 on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4 (+ the stage-1 book filter / book exit)
* Reason written first: At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (18:00 ET: Globex reopen).
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| straddle_t_1800-NQ-tf30 · eve | 84 % of 160 | $13,127 | `offatr0p5_atr1p5-r2` | 508 | $13,133 | 0.56 | 2.62 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| straddle_t_1800-NQ-tf30 · eve | adx_hi | 92 % | $16,012 | Y/Y/Y | `offatr1_pts20-r2` | 149 | $16,044 | 2.19 | $18,995 | 99.2 % | Y Y Y n n | - |
| straddle_t_1800-NQ-tf30 · eve | adx_lo | 38 % | -$2,335 | n/n/n | `offatr0p5_pts10-r3` | 258 | $218 | 0.04 | $13,808 | 34.3 % | Y n Y n n | - |
| straddle_t_1800-NQ-tf30 · eve | vol_hi | 69 % | $4,054 | Y/n/n | `offatr1_pts10-r2` | 174 | $3,789 | 0.97 | $8,194 | 78.8 % | Y Y Y n n | - |
| straddle_t_1800-NQ-tf30 · eve | vol_lo | 72 % | $8,511 | Y/Y/n | `offatr0p5_pts30-r3` | 246 | $8,346 | 0.50 | $37,854 | 51.7 % | Y Y Y n n | - |
| straddle_t_1800-NQ-tf30 · eve | news_only | 56 % | $1,045 | n/n/n | `offatr0p25_atr1p5-r1` | 69 | $1,124 | 0.17 | $7,697 | 35.0 % | n n Y n n | - |
| straddle_t_1800-NQ-tf30 · eve | news_never | 83 % | $9,177 | Y/Y/Y | `offatr0p25_atr1p5-r3` | 487 | $9,327 | 0.33 | $24,026 | 11.8 % | Y Y Y n n | - |
| straddle_t_1800-NQ-tf30 · eve | long | 83 % | $8,273 | Y/Y/Y | `offatr0p25_pts30-r1` | 291 | $8,241 | 0.80 | $19,164 | 100.0 % | Y Y Y n Y | - |
| straddle_t_1800-NQ-tf30 · eve | short | 61 % | $3,938 | Y/n/n | `offptsA_pts30-r2` | 248 | $4,093 | 0.30 | $24,260 | 100.0 % | Y Y Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
