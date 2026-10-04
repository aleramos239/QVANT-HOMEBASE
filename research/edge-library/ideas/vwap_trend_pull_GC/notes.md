# VWAP trend pullback (`vwap_trend_pull`) on GC — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: When price holds above a rising session VWAP, the day's buyers are in profit and dips get bought; the first candle against the trend gives a better price in the direction of the day's flow.
* Rules as run: N1 vwap_trend_pull: close above a rising 09:30 VWAP and up >= X % over 60 min, first down bar -> market long (mirror short); entries 10:30-15:30 ET, max 4 trades and stop after 2 losing trades per session instance. Author cell (information only): stop 80 pts, target 40 long / 50 short, NQ tf 15
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 11. Heat map passes at 60 / 70 / 80 % of variants positive: 2 / 1 / 0. Also beat the matched random control: 1. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_trend_pull-GC-tf15 · nyam | 96 | 75 % | $4,950 | Y/Y/n | `x0p1_atr3-r1` | 175 | $4,900 | 0.53 | 1.24 | $20,263 | 100 % | bar |
| vwap_trend_pull-GC-tf5 · nyam | 96 | 70 % | $3,774 | Y/n/n | `x0p05_pts3-r3` | 417 | $3,852 | 0.40 | 1.24 | -$6,200 | 23 % | c1,bar |
| vwap_trend_pull-GC-tf15 · mid | 96 | 46 % | -$304 | n/n/n | `x0p2_pts3-r0` | 218 | $18 | 0.00 |  | | | heat map |
| vwap_trend_pull-GC-tf5 · mid | 96 | 45 % | -$2,338 | n/n/n | `x0p1_pts3-r3` | 761 | $156 | 0.01 |  | | | heat map |
| vwap_trend_pull-GC-tf1 · mid | 96 | 33 % | -$11,037 | n/n/n | `x0p1_pts3-r3` | 930 | $10 | 0.00 |  | | | heat map |
| vwap_trend_pull-GC-tf1 · pm | 96 | 28 % | -$8,969 | n/n/n | `x0p2_pct0p2-r1` | 423 | $268 | 0.04 |  | | | heat map |
| vwap_trend_pull-GC-tf30 · mid | 93 | 17 % | -$2,714 | n/n/n | `x0p05_pts2-r3` | 222 | $42 | 0.01 |  | | | heat map |
| vwap_trend_pull-GC-tf1 · nyam | 96 | 5 % | -$12,173 | n/n/n | `x0p1_atr3-r0` | 599 | $74 | 0.01 |  | | | heat map |
| vwap_trend_pull-GC-tf15 · pm | 84 | 4 % | -$3,749 | n/n/n | `x0p2_pts5-r2` | 88 | $8 | 0.00 |  | | | heat map |
| vwap_trend_pull-GC-tf30 · pm | 63 | 0 % | -$3,168 | n/n/n | none | | | |  | | | heat map |
| vwap_trend_pull-GC-tf5 · pm | 96 | 0 % | -$11,183 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 1 of 11 units; on active days only in 2 of 11; on all days in 2.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| vwap_trend_pull-GC-tf15 · nyam | 20 % / -$1,780 | 89 % / $8,412 |
| vwap_trend_pull-GC-tf5 · nyam | 88 % / $3,231 | 45 % / -$2,440 |
| vwap_trend_pull-GC-tf15 · mid | 19 % / -$3,401 | 75 % / $3,708 |
| vwap_trend_pull-GC-tf5 · mid | 56 % / $928 | 44 % / -$2,228 |
| vwap_trend_pull-GC-tf1 · mid | 18 % / -$5,419 | 41 % / -$2,845 |
| vwap_trend_pull-GC-tf1 · pm | 27 % / -$4,690 | 29 % / -$5,638 |
| vwap_trend_pull-GC-tf30 · mid | 2 % / -$2,313 | 53 % / $52 |
| vwap_trend_pull-GC-tf1 · nyam | 34 % / -$1,925 | 9 % / -$9,353 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
