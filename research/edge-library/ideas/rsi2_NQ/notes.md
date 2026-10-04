# rsi2 on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: A 2-bar RSI below th (above 100-th) is a short-term exhaustion that snaps back; fade it at the close.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 2 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| rsi2-NQ-tf30 · eve | 99 % of 96 | $44,214 | `th5_pts30-r3` | 436 | $42,786 | 1.88 | 2.02 |
| rsi2-NQ-tf15 · asia | 78 % of 96 | $14,437 | `th15_pts20-r2` | 867 | $13,782 | 0.81 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rsi2-NQ-tf30 · eve | adx_hi | 94 % | $26,052 | Y/Y/Y | `th5_pts45-r1` | 191 | $25,981 | 2.11 | $1,900 | 88.7 % | Y Y Y Y n | - |
| rsi2-NQ-tf30 · eve | adx_lo | 96 % | $22,209 | Y/Y/Y | `th5_pts45-r2` | 189 | $22,094 | 1.23 | -$3,764 | 51.4 % | Y Y n n n | - |
| rsi2-NQ-tf30 · eve | vol_hi | 82 % | $17,032 | Y/Y/Y | `th10_pts30-r2` | 304 | $16,974 | 1.12 | -$6,951 | 26.3 % | Y Y n n n | - |
| rsi2-NQ-tf30 · eve | vol_lo | 100 % | $26,888 | Y/Y/Y | `th5_pct0p2-r3` | 210 | $26,835 | 1.81 | -$3,234 | 49.5 % | Y Y n n n | - |
| rsi2-NQ-tf30 · eve | news_only | 90 % | $7,434 | Y/Y/Y | `th5_pts30-r1` | 55 | $7,460 | 1.70 | $2,420 | 81.2 % | n Y Y n n | - |
| rsi2-NQ-tf30 · eve | news_never | 97 % | $37,048 | Y/Y/Y | `th10_pct0p2-r2` | 570 | $37,485 | 1.95 | -$11,662 | 32.1 % | Y Y n n n | - |
| rsi2-NQ-tf30 · eve | long | 90 % | $20,935 | Y/Y/Y | `th5_pts20-r2` | 248 | $21,403 | 2.29 | $35,223 | 100.0 % | Y Y Y Y Y | PASS on BUILD |
| rsi2-NQ-tf30 · eve | short | 98 % | $19,895 | Y/Y/Y | `th10_pts20-r3` | 348 | $19,708 | 1.45 | $53,871 | 100.0 % | Y Y Y n Y | - |
| rsi2-NQ-tf15 · asia | adx_hi | 78 % | $9,277 | Y/Y/n | `th5_pct0p2-r1` | 238 | $9,253 | 1.08 | $17,327 | 83.8 % | Y Y Y n n | - |
| rsi2-NQ-tf15 · asia | adx_lo | 49 % | -$936 | n/n/n | `th10_pct0p1-r2` | 440 | $5 | 0.00 | -$27,212 | 48.2 % | Y n n n n | - |
| rsi2-NQ-tf15 · asia | vol_hi | 77 % | $10,124 | Y/Y/n | `th10_pct0p2-r1` | 359 | $10,039 | 0.96 | $13,701 | 76.5 % | Y Y Y n n | - |
| rsi2-NQ-tf15 · asia | vol_lo | 57 % | $1,292 | n/n/n | `th5_atr1p5-r1` | 301 | $1,431 | 0.21 | $819 | 32.1 % | Y n Y n n | - |
| rsi2-NQ-tf15 · asia | news_only | 61 % | $2,275 | Y/n/n | `th5_atr1p5-r0` | 72 | $2,352 | 0.19 | -$940 | 53.1 % | n Y n n n | - |
| rsi2-NQ-tf15 · asia | news_never | 77 % | $11,118 | Y/Y/n | `th10_atr1p5-r2` | 719 | $10,329 | 0.59 | -$12,563 | 72.9 % | Y Y n n n | - |
| rsi2-NQ-tf15 · asia | long | 82 % | $14,780 | Y/Y/Y | `th5_pct0p2-r2` | 243 | $14,883 | 1.19 | $42,636 | 100.0 % | Y Y Y n Y | - |
| rsi2-NQ-tf15 · asia | short | 46 % | -$630 | n/n/n | `th10_atr1p5-r1` | 442 | $322 | 0.03 | $38,209 | 100.0 % | Y n Y n Y | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* `rsi2-NQ-tf30 · eve` long: exact re-run with dir = long on BUILD: 84 % of variants positive, central `th5_pts20-r2` 255 trades, $19,745, t 2.09 (bar 2.02), lift $35,512, beats 100.0 % of 4,000 draws from a 30-seed long-only random pool -> PASSES BUILD.
* `rsi2-NQ-tf30 · eve` long: 2024 opened (whole menu, same split): 19 % of variants positive, median -$8,224 -> the 2024 table FAILS. The BUILD central variant `th5_pts20-r2` made $341 in 2024 (111 trades; lift over random entries $15,219).

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
