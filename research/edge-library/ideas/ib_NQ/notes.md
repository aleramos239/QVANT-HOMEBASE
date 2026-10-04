# ib on NQ — idea record (stage 2a = deepen round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 1 of 4
* Reason written first: The initial balance (09:30-10:30) is the first hour's accepted range and anchors the NY day: a break of it carries as the day's range extends, and a break that closes back inside has failed and reverts to the IB mid.
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units touched: 8 near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).

## The units before any split
| unit | variants positive | median variant | central variant | trades | net | t | bar |
|---|---|---|---|---|---|---|---|
| ib-NQ-tf5 · mid · mode=break | 100 % of 32 | $32,445 | `modebreak_atr1p5-r1` | 310 | $33,010 | 1.99 | 2.02 |
| ib-NQ-tf15 · mid · mode=break | 100 % of 32 | $32,875 | `modebreak_pct0p1-r0` | 310 | $31,880 | 1.62 | 2.02 |
| ib-NQ-tf30 · mid · mode=break | 100 % of 32 | $32,875 | `modebreak_pct0p1-r0` | 310 | $31,880 | 1.62 | 2.02 |
| ib-NQ-tf15 · pm · mode=break | 81 % of 32 | $16,008 | `modebreak_pts30-r2` | 218 | $16,118 | 1.40 | 2.02 |
| ib-NQ-tf30 · pm · mode=break | 81 % of 32 | $15,656 | `modebreak_pts30-r3` | 218 | $15,413 | 1.13 | 2.02 |
| ib-NQ-tf5 · pm · mode=break | 81 % of 32 | $14,968 | `modebreak_atr1p5-r2` | 218 | $14,523 | 1.01 | 2.02 |
| ib-NQ-tf15 · nyam · mode=break | 62 % of 32 | $4,644 | `modebreak_pts10-r2` | 346 | $2,611 | 0.48 | 2.02 |
| ib-NQ-tf30 · nyam · mode=break | 62 % of 32 | $4,644 | `modebreak_pts10-r2` | 346 | $2,611 | 0.48 | 2.02 |

## The 8 sides (each one a filter on the unit's own stored BUILD trades)
Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).
| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ib-NQ-tf5 · mid · mode=break | adx_hi | 100 % | $28,600 | Y/Y/Y | `modebreak_pts30-r3` | 148 | $26,753 | 2.02 | $10,921 | 92.8 % | Y Y Y Y n | - |
| ib-NQ-tf5 · mid · mode=break | adx_lo | 47 % | -$670 | n/n/n | `modebreak_pts30-r3` | 145 | $140 | 0.01 | -$2,570 | 7.3 % | Y n n n n | - |
| ib-NQ-tf5 · mid · mode=break | vol_hi | 91 % | $5,447 | Y/Y/Y | `modebreak_pts30-r3` | 147 | $5,482 | 0.44 | -$5,537 | 14.0 % | Y Y n n n | - |
| ib-NQ-tf5 · mid · mode=break | vol_lo | 100 % | $27,523 | Y/Y/Y | `modebreak_pts20-r0` | 153 | $28,648 | 1.68 | $981 | 86.4 % | Y Y Y n n | - |
| ib-NQ-tf5 · mid · mode=break | news_only | 31 % | -$2,792 | n/n/n | `modebreak_atr1p5-r1` | 46 | $376 | 0.05 | $2,667 | 21.4 % | n n Y n n | - |
| ib-NQ-tf5 · mid · mode=break | news_never | 97 % | $35,752 | Y/Y/Y | `modebreak_pts20-r0` | 264 | $36,804 | 1.84 | -$28,378 | 91.5 % | Y Y n n n | - |
| ib-NQ-tf5 · mid · mode=break | long | 100 % | $22,199 | Y/Y/Y | `modebreak_atr1p5-r1` | 164 | $21,999 | 1.84 | -$21,695 | 0.3 % | Y Y n n n | - |
| ib-NQ-tf5 · mid · mode=break | short | 78 % | $10,131 | Y/Y/n | `modebreak_atr1p5-r1` | 146 | $11,011 | 0.96 | -$17,148 | 1.0 % | Y Y n n n | - |
| ib-NQ-tf15 · mid · mode=break | adx_hi | 100 % | $28,600 | Y/Y/Y | `modebreak_pts30-r3` | 148 | $26,753 | 2.02 | $13,344 | 92.5 % | Y Y Y Y n | - |
| ib-NQ-tf15 · mid · mode=break | adx_lo | 59 % | $2,352 | n/n/n | `modebreak_atr1p5-r1` | 145 | $1,365 | 0.10 | $8,308 | 0.9 % | Y n Y n n | - |
| ib-NQ-tf15 · mid · mode=break | vol_hi | 94 % | $5,920 | Y/Y/Y | `modebreak_pts30-r3` | 147 | $5,482 | 0.44 | -$2,493 | 14.0 % | Y Y n n n | - |
| ib-NQ-tf15 · mid · mode=break | vol_lo | 100 % | $27,523 | Y/Y/Y | `modebreak_pts20-r0` | 153 | $28,648 | 1.68 | $5,844 | 85.7 % | Y Y Y n n | - |
| ib-NQ-tf15 · mid · mode=break | news_only | 28 % | -$2,792 | n/n/n | `modebreak_pts20-r3` | 46 | $426 | 0.09 | $4,050 | 26.0 % | n n Y n n | - |
| ib-NQ-tf15 · mid · mode=break | news_never | 97 % | $41,062 | Y/Y/Y | `modebreak_pts20-r0` | 264 | $36,804 | 1.84 | -$78 | 91.6 % | Y Y n n n | - |
| ib-NQ-tf15 · mid · mode=break | long | 100 % | $23,016 | Y/Y/Y | `modebreak_pts20-r0` | 164 | $22,399 | 1.40 | -$34,447 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf15 · mid · mode=break | short | 78 % | $13,231 | Y/Y/n | `modebreak_atr1p5-r1` | 146 | $17,211 | 1.21 | -$5,664 | 20.9 % | Y Y n n n | - |
| ib-NQ-tf30 · mid · mode=break | adx_hi | 100 % | $28,600 | Y/Y/Y | `modebreak_pts30-r3` | 148 | $26,753 | 2.02 | $15,043 | 93.3 % | Y Y Y Y n | - |
| ib-NQ-tf30 · mid · mode=break | adx_lo | 58 % | $3,340 | n/n/n | `modebreak_pts20-r0` | 145 | $3,340 | 0.25 | -$10,052 | 15.2 % | Y n n n n | - |
| ib-NQ-tf30 · mid · mode=break | vol_hi | 94 % | $5,920 | Y/Y/Y | `modebreak_pts30-r3` | 147 | $5,482 | 0.44 | -$7,837 | 13.2 % | Y Y n n n | - |
| ib-NQ-tf30 · mid · mode=break | vol_lo | 100 % | $27,523 | Y/Y/Y | `modebreak_pts20-r0` | 153 | $28,648 | 1.68 | $21,303 | 86.8 % | Y Y Y n n | - |
| ib-NQ-tf30 · mid · mode=break | news_only | 29 % | -$2,764 | n/n/n | `modebreak_pts20-r3` | 46 | $426 | 0.09 | $123 | 25.4 % | n n Y n n | - |
| ib-NQ-tf30 · mid · mode=break | news_never | 97 % | $41,062 | Y/Y/Y | `modebreak_pts20-r0` | 264 | $36,804 | 1.84 | $7,720 | 91.9 % | Y Y Y n n | - |
| ib-NQ-tf30 · mid · mode=break | long | 100 % | $23,016 | Y/Y/Y | `modebreak_pts20-r0` | 164 | $22,399 | 1.40 | -$20,904 | 0.1 % | Y Y n n n | - |
| ib-NQ-tf30 · mid · mode=break | short | 78 % | $13,644 | Y/Y/n | `modebreak_pts20-r3` | 146 | $9,251 | 1.04 | -$4,830 | 20.7 % | Y Y n n n | - |
| ib-NQ-tf15 · pm · mode=break | adx_hi | 34 % | -$2,214 | n/n/n | `modebreak_pts20-r1` | 93 | $108 | 0.03 | $1,559 | 51.6 % | n n Y n n | - |
| ib-NQ-tf15 · pm · mode=break | adx_lo | 91 % | $13,660 | Y/Y/Y | `modebreak_atr1p5-r1` | 117 | $13,132 | 1.27 | $10,068 | 82.2 % | Y Y Y n n | - |
| ib-NQ-tf15 · pm · mode=break | vol_hi | 22 % | -$5,110 | n/n/n | `modebreak_pct0p1-r0` | 105 | $65 | 0.01 | -$4,150 | 10.2 % | Y n n n n | - |
| ib-NQ-tf15 · pm · mode=break | vol_lo | 100 % | $16,632 | Y/Y/Y | `modebreak_pts30-r2` | 105 | $16,430 | 2.07 | $10,036 | 94.5 % | Y Y Y Y n | - |
| ib-NQ-tf15 · pm · mode=break | news_only | 22 % | -$1,108 | n/n/n | `modebreak_pts20-r1` | 35 | $550 | 0.23 | $2,440 | 63.0 % | n n Y n n | - |
| ib-NQ-tf15 · pm · mode=break | news_never | 84 % | $15,550 | Y/Y/Y | `modebreak_pts30-r2` | 183 | $13,873 | 1.33 | $6,929 | 53.4 % | Y Y Y n n | - |
| ib-NQ-tf15 · pm · mode=break | long | 75 % | $2,832 | Y/Y/n | `modebreak_atr1p5-r2` | 112 | $2,907 | 0.21 | -$52,807 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf15 · pm · mode=break | short | 81 % | $11,164 | Y/Y/Y | `modebreak_pct0p1-r0` | 106 | $11,601 | 1.15 | -$11,364 | 1.6 % | Y Y n n n | - |
| ib-NQ-tf30 · pm · mode=break | adx_hi | 34 % | -$2,554 | n/n/n | `modebreak_pts20-r1` | 93 | $108 | 0.03 | $985 | 54.9 % | n n Y n n | - |
| ib-NQ-tf30 · pm · mode=break | adx_lo | 91 % | $14,280 | Y/Y/Y | `modebreak_pct0p1-r0` | 117 | $14,372 | 1.11 | $6,476 | 55.7 % | Y Y Y n n | - |
| ib-NQ-tf30 · pm · mode=break | vol_hi | 23 % | -$5,025 | n/n/n | `modebreak_pct0p1-r0` | 105 | $65 | 0.01 | -$12,247 | 10.8 % | Y n n n n | - |
| ib-NQ-tf30 · pm · mode=break | vol_lo | 100 % | $17,285 | Y/Y/Y | `modebreak_pts20-r0` | 105 | $17,735 | 1.36 | $8,463 | 80.8 % | Y Y Y n n | - |
| ib-NQ-tf30 · pm · mode=break | news_only | 19 % | -$1,665 | n/n/n | `modebreak_pts20-r1` | 35 | $550 | 0.23 | $2,598 | 64.4 % | n n Y n n | - |
| ib-NQ-tf30 · pm · mode=break | news_never | 84 % | $15,550 | Y/Y/Y | `modebreak_pts30-r2` | 183 | $13,873 | 1.33 | $17,019 | 53.9 % | Y Y Y n n | - |
| ib-NQ-tf30 · pm · mode=break | long | 75 % | $3,302 | Y/Y/n | `modebreak_atr3-r1` | 112 | $2,997 | 0.18 | -$47,804 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf30 · pm · mode=break | short | 81 % | $11,521 | Y/Y/Y | `modebreak_atr3-r1` | 106 | $11,441 | 0.65 | -$24,421 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf5 · pm · mode=break | adx_hi | 44 % | -$812 | n/n/n | `modebreak_pts20-r1` | 93 | $108 | 0.03 | $1,882 | 54.3 % | n n Y n n | - |
| ib-NQ-tf5 · pm · mode=break | adx_lo | 91 % | $10,347 | Y/Y/Y | `modebreak_atr1p5-r2` | 117 | $10,572 | 1.12 | $6,141 | 68.1 % | Y Y Y n n | - |
| ib-NQ-tf5 · pm · mode=break | vol_hi | 28 % | -$3,998 | n/n/n | `modebreak_pct0p1-r0` | 105 | $65 | 0.01 | -$8,822 | 10.6 % | Y n n n n | - |
| ib-NQ-tf5 · pm · mode=break | vol_lo | 100 % | $14,940 | Y/Y/Y | `modebreak_atr1p5-r3` | 105 | $14,750 | 1.57 | $6,915 | 80.7 % | Y Y Y n n | - |
| ib-NQ-tf5 · pm · mode=break | news_only | 25 % | -$995 | n/n/n | `modebreak_atr1p5-r1` | 35 | $85 | 0.02 | $3,105 | 50.3 % | n n Y n n | - |
| ib-NQ-tf5 · pm · mode=break | news_never | 84 % | $12,330 | Y/Y/Y | `modebreak_pts10-r0` | 183 | $11,438 | 0.78 | -$9,058 | 96.9 % | Y Y n n n | - |
| ib-NQ-tf5 · pm · mode=break | long | 69 % | $2,664 | Y/n/n | `modebreak_pts45-r2` | 112 | $2,757 | 0.26 | -$38,620 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf5 · pm · mode=break | short | 81 % | $10,341 | Y/Y/Y | `modebreak_atr1p5-r2` | 106 | $9,956 | 1.01 | -$24,484 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf15 · nyam · mode=break | adx_hi | 22 % | -$5,932 | n/n/n | `modebreak_pct0p1-r3` | 148 | $613 | 0.10 | $5,333 | 42.4 % | Y n Y n n | - |
| ib-NQ-tf15 · nyam · mode=break | adx_lo | 88 % | $16,355 | Y/Y/Y | `modebreak_atr1p5-r3` | 180 | $17,455 | 0.83 | -$12,683 | 75.1 % | Y Y n n n | - |
| ib-NQ-tf15 · nyam · mode=break | vol_hi | 28 % | -$4,704 | n/n/n | `modebreak_pct0p1-r1` | 168 | $58 | 0.02 | $2,264 | 75.6 % | Y n Y n n | - |
| ib-NQ-tf15 · nyam · mode=break | vol_lo | 78 % | $9,368 | Y/Y/n | `modebreak_pts30-r2` | 166 | $9,716 | 0.87 | -$2,428 | 89.7 % | Y Y n n n | - |
| ib-NQ-tf15 · nyam · mode=break | news_only | 23 % | -$2,664 | n/n/n | `modebreak_pts45-r3` | 36 | $16 | 0.00 | -$6,208 | 43.5 % | n n n n n | - |
| ib-NQ-tf15 · nyam · mode=break | news_never | 72 % | $4,902 | Y/Y/n | `modebreak_pct0p1-r0` | 310 | $5,805 | 0.31 | -$66,681 | 33.9 % | Y Y n n n | - |
| ib-NQ-tf15 · nyam · mode=break | long | 97 % | $14,245 | Y/Y/Y | `modebreak_pts45-r2` | 165 | $14,245 | 0.91 | -$88,051 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf15 · nyam · mode=break | short | 25 % | -$4,229 | n/n/n | `modebreak_atr1p5-r2` | 181 | $1,861 | 0.09 | -$91,408 | 0.0 % | Y n n n n | - |
| ib-NQ-tf30 · nyam · mode=break | adx_hi | 34 % | -$4,912 | n/n/n | `modebreak_pct0p1-r3` | 148 | $613 | 0.10 | $5,033 | 41.9 % | Y n Y n n | - |
| ib-NQ-tf30 · nyam · mode=break | adx_lo | 88 % | $17,568 | Y/Y/Y | `modebreak_pts20-r3` | 180 | $17,510 | 1.76 | -$1,204 | 95.3 % | Y Y n n n | - |
| ib-NQ-tf30 · nyam · mode=break | vol_hi | 41 % | -$2,164 | n/n/n | `modebreak_pct0p1-r1` | 168 | $58 | 0.02 | $2,221 | 75.4 % | Y n Y n n | - |
| ib-NQ-tf30 · nyam · mode=break | vol_lo | 78 % | $9,368 | Y/Y/n | `modebreak_pts30-r2` | 166 | $9,716 | 0.87 | -$5,298 | 89.4 % | Y Y n n n | - |
| ib-NQ-tf30 · nyam · mode=break | news_only | 23 % | -$2,664 | n/n/n | `modebreak_pts45-r3` | 36 | $16 | 0.00 | $596 | 43.2 % | n n Y n n | - |
| ib-NQ-tf30 · nyam · mode=break | news_never | 72 % | $4,902 | Y/Y/n | `modebreak_pct0p1-r0` | 310 | $5,805 | 0.31 | -$31,273 | 34.4 % | Y Y n n n | - |
| ib-NQ-tf30 · nyam · mode=break | long | 97 % | $13,400 | Y/Y/Y | `modebreak_atr1p5-r1` | 165 | $13,400 | 0.83 | -$38,378 | 0.0 % | Y Y n n n | - |
| ib-NQ-tf30 · nyam · mode=break | short | 28 % | -$4,229 | n/n/n | `modebreak_pts10-r0` | 181 | $5,371 | 0.36 | -$75,302 | 0.0 % | Y n n n n | - |

Sides: `adx_hi` = only days whose prior-day daily ADX(14) is 25 or more (a trending market); `adx_lo` = only days whose prior-day daily ADX(14) is below 25 (no clear trend); `vol_hi` = only days after a daily range above its own 20-day median (an active market); `vol_lo` = only days after a daily range at or below its own 20-day median (a quiet market); `news_only` = only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision; `news_never` = never on days with a CPI or jobs (NFP) release or a Fed (FOMC) decision; `long` = long trades only; `short` = short trades only.
Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact re-run with the family's own `dir` input.

## What happened to sides that passed BUILD
* None passed all of (a)-(e). 2024 stays unread for these units.

## Left on the DONE checklist
* deepen tools: book filter at the trade, book exit, flow+book AGREE marker, RSI direction, inverse; verdict

Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).
