# VWAP trend pullback (`vwap_trend_pull`) on NQ — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: When price holds above a rising session VWAP, the day's buyers are in profit and dips get bought; the first candle against the trend gives a better price in the direction of the day's flow.
* Rules as run: N1 vwap_trend_pull: close above a rising 09:30 VWAP and up >= X % over 60 min, first down bar -> market long (mirror short); entries 10:30-15:30 ET, max 4 trades and stop after 2 losing trades per session instance. Author cell (information only): stop 80 pts, target 40 long / 50 short, NQ tf 15
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 11. Heat map passes at 60 / 70 / 80 % of variants positive: 7 / 5 / 4. Also beat the matched random control: 5. Also reach the best-of-random bar (= pass BUILD): 1.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_trend_pull-NQ-tf5 · pm | 96 | 92 % | $64,513 | Y/Y/Y | `x0p1_pts30-r2` | 899 | $64,434 | 2.70 | 2.02 | $51,072 | 99 % | none: passes BUILD |
| vwap_trend_pull-NQ-tf15 · pm | 94 | 88 % | $24,270 | Y/Y/Y | `x0p05_atr1p5-r2` | 493 | $24,133 | 0.93 | 2.02 | -$12,068 | 29 % | c1,bar |
| vwap_trend_pull-NQ-tf1 · pm | 96 | 81 % | $31,152 | Y/Y/Y | `x0p05_atr3-r1` | 1697 | $32,052 | 1.18 | 2.02 | $88,850 | 100 % | bar |
| vwap_trend_pull-NQ-tf1 · mid | 96 | 80 % | $20,745 | Y/Y/Y | `x0p05_pts20-r2` | 1522 | $20,617 | 0.92 | 2.02 | $38,359 | 100 % | bar |
| vwap_trend_pull-NQ-tf15 · nyam | 96 | 74 % | $8,892 | Y/Y/n | `x0p05_pct0p1-r0` | 221 | $9,046 | 0.50 | 2.02 | -$29,718 | 0 % | c1,bar |
| vwap_trend_pull-NQ-tf5 · mid | 96 | 62 % | $8,518 | Y/n/n | `x0p05_atr1p5-r1` | 1292 | $9,147 | 0.29 | 2.02 | $4,667 | 58 % | bar |
| vwap_trend_pull-NQ-tf5 · nyam | 96 | 61 % | $7,716 | Y/n/n | `x0p1_atr1p5-r1` | 430 | $7,130 | 0.36 | 2.02 | $9,023 | 73 % | bar |
| vwap_trend_pull-NQ-tf30 · pm | 93 | 59 % | $1,253 | n/n/n | `x0p1_pts20-r1` | 183 | $1,253 | 0.23 |  | | | heat map |
| vwap_trend_pull-NQ-tf1 · nyam | 96 | 58 % | $5,490 | n/n/n | `x0p05_atr1p5-r3` | 888 | $6,798 | 0.27 |  | | | heat map |
| vwap_trend_pull-NQ-tf15 · mid | 96 | 33 % | -$7,519 | n/n/n | `x0p05_pct0p2-r0` | 631 | $821 | 0.03 |  | | | heat map |
| vwap_trend_pull-NQ-tf30 · mid | 94 | 33 % | -$2,861 | n/n/n | `x0p2_pts45-r0` | 155 | $130 | 0.01 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 8 of 11 units; on active days only in 3 of 11; on all days in 7.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| vwap_trend_pull-NQ-tf5 · pm | 85 % / $27,296 | 97 % / $39,402 |
| vwap_trend_pull-NQ-tf15 · pm | 93 % / $21,592 | 54 % / $657 |
| vwap_trend_pull-NQ-tf1 · pm | 81 % / $24,849 | 64 % / $5,140 |
| vwap_trend_pull-NQ-tf1 · mid | 93 % / $30,882 | 25 % / -$5,276 |
| vwap_trend_pull-NQ-tf15 · nyam | 82 % / $7,376 | 66 % / $1,734 |
| vwap_trend_pull-NQ-tf5 · mid | 59 % / $6,876 | 57 % / $6,454 |
| vwap_trend_pull-NQ-tf5 · nyam | 54 % / $4,110 | 45 % / -$742 |
| vwap_trend_pull-NQ-tf30 · pm | 90 % / $4,356 | 26 % / -$2,905 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Author cells (information only: never in the heat map, never the member)
9 author cells: 6 positive, median $18,925, best $44,619, worst -$10,849. Highest t: `authon_x0p2_pts80-r0` in vwap_trend_pull-NQ-tf15 · pm: 354 trades, $44,619, t 2.53. All: `out/admit_r1/author_cells.csv`.

## 2024 (opened only for the units that passed every BUILD test; passing session only)
* vwap_trend_pull-NQ-tf5 · pm: 2024 heat map 61 % of 96 variants positive, median $2,406 -> PASSES. BUILD central variant `x0p1_pts30-r2` in 2024: -$14,421 (349 trades), lift over its random control -$21,792. Under 2 ticks + 250 ms: BUILD $64,434 -> $49,271; 2024 -$14,421 -> -$18,627. 42 of 96 variants are positive in both periods and under stress. **NOT ADMITTED**: the BUILD central variant is not positive in 2024 and no moved default is allowed (record: `members/_rejected/vwap_trend_pull_NQ_tf5_pm/`).
These units' 2024 is now spent: information only from here.

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
