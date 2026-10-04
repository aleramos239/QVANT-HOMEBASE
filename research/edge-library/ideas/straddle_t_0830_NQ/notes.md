# straddle_t_0830 on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4 (+ the stage-1 book filter / book exit)
* Reason written first: At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (08:30 ET: US data).
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 1 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| straddle_t_0830-NQ-tf30 · pre | 92 % of 160 | $35,920 | `offatr1_pct0p2-r3` | 433 | $35,088 | 1.67 | 2.62 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| straddle_t_0830-NQ-tf30 · pre | adx_hi | 94 % | $17,586 | Y/Y/Y | `offatr0p25_atr1p5-r3` | 254 | $17,514 | 0.61 | $19,090 | 44.8 % | Y Y Y n n | - |
| straddle_t_0830-NQ-tf30 · pre | adx_lo | 92 % | $17,072 | Y/Y/Y | `offatr0p25_atr3-r3` | 286 | $16,941 | 0.43 | -$50 | 21.2 % | Y Y n n n | - |
| straddle_t_0830-NQ-tf30 · pre | vol_hi | 58 % | $1,456 | n/n/n | `offatr0p5_pct0p1-r0` | 271 | $1,516 | 0.07 | $9,133 | 0.6 % | Y n Y n n | - |
| straddle_t_0830-NQ-tf30 · pre | vol_lo | 96 % | $36,624 | Y/Y/Y | `offatr0p25_atr1p5-r3` | 277 | $37,297 | 1.56 | $21,390 | 74.9 % | Y Y Y n n | - |
| straddle_t_0830-NQ-tf30 · pre | news_only | 91 % | $13,006 | Y/Y/Y | `offatr0p25_pct0p1-r2` | 71 | $12,951 | 3.59 | $16,332 | 100.0 % | n Y Y Y Y | - |
| straddle_t_0830-NQ-tf30 · pre | news_never | 82 % | $20,423 | Y/Y/Y | `offatr0p5_atr3-r1` | 496 | $20,301 | 0.50 | $34,632 | 56.5 % | Y Y Y n n | - |
| straddle_t_0830-NQ-tf30 · pre | long | 89 % | $18,646 | Y/Y/Y | `offatr0p5_atr1p5-r2` | 256 | $18,681 | 0.86 | $5,368 | 95.3 % | Y Y Y n n | - |
| straddle_t_0830-NQ-tf30 · pre | short | 85 % | $15,811 | Y/Y/Y | `offatr0p25_pts10-r3` | 306 | $15,851 | 2.38 | $18,342 | 100.0 % | Y Y Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* `news_only` passed b, c, d and e on BUILD (t 3.59 against a bar of 2.62; beats 99.98 % of random day subsets) with 71 trades. The analyst had counted the 100 trades on BUILD alone; the ORCHESTRATOR RULED (2026-10-04) that the rule counts BUILD + 2024 and that 2024 be opened.
* 2024 opened (whole menu, news days only): 63.7 % of 160 variants positive, median $1,448 -> the table PASSES (at 60 % only). Trades BUILD + 2024 of the central variant: 102.
* The BUILD central variant `offatr0p25_pct0p1-r2` per year: 2021* -$46 (9 trades) · 2022 $7,896 (31 trades) · 2023 $5,101 (31 trades) · 2024 -$1,129 (31 trades) · combined $11,822 (102 trades). Under 2 ticks + 250 ms: BUILD $11,476, 2024 -$2,349.
* 86 of 160 variants are positive in both periods and under stress (`members/_rejected/straddle_t_0830_NQ_tf30_pre_news_only/surviving_set.csv`), but the central variant is not one of them and the ruling allows no replacement. **NOT ADMITTED**: the central variant loses money in 2024. The random-minute control was not run on 2024.
* It is the SAME IDEA as the member orb_NQ_tf1_pre (a straddle of the 08:30 data burst); the member's own news-day profit also faded in 2024 ($856).

## Left on the DONE checklist
* deepen tools: flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
