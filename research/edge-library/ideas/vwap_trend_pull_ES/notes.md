# VWAP trend pullback (`vwap_trend_pull`) on ES — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: When price holds above a rising session VWAP, the day's buyers are in profit and dips get bought; the first candle against the trend gives a better price in the direction of the day's flow.
* Rules as run: N1 vwap_trend_pull: close above a rising 09:30 VWAP and up >= X % over 60 min, first down bar -> market long (mirror short); entries 10:30-15:30 ET, max 4 trades and stop after 2 losing trades per session instance. Author cell (information only): stop 80 pts, target 40 long / 50 short, NQ tf 15
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 11. Heat map passes at 60 / 70 / 80 % of variants positive: 3 / 1 / 0. Also beat the matched random control: 2. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vwap_trend_pull-ES-tf30 · pm | 90 | 70 % | $1,896 | Y/Y/n | `x0p05_pts12-r0` | 202 | $1,867 | 0.18 | 1.30 | $9,118 | 92 % | bar |
| vwap_trend_pull-ES-tf15 · nyam | 96 | 69 % | $3,654 | Y/n/n | `x0p1_pts5-r1` | 188 | $3,710 | 1.06 | 1.30 | $8,502 | 100 % | bar |
| vwap_trend_pull-ES-tf5 · pm | 96 | 60 % | $9,291 | Y/n/n | `x0p1_pts8-r0` | 683 | $9,330 | 0.52 | 1.30 | -$27,640 | 2 % | c1,bar |
| vwap_trend_pull-ES-tf15 · pm | 96 | 58 % | $1,574 | n/n/n | `x0p05_pct0p2-r2` | 511 | $1,894 | 0.16 |  | | | heat map |
| vwap_trend_pull-ES-tf1 · pm | 96 | 49 % | -$293 | n/n/n | `x0p05_pct0p2-r2` | 1053 | $588 | 0.03 |  | | | heat map |
| vwap_trend_pull-ES-tf1 · nyam | 96 | 38 % | -$7,787 | n/n/n | `x0p05_pct0p2-r3` | 715 | $465 | 0.02 |  | | | heat map |
| vwap_trend_pull-ES-tf5 · mid | 96 | 36 % | -$7,780 | n/n/n | `x0p2_atr3-r1` | 626 | $921 | 0.04 |  | | | heat map |
| vwap_trend_pull-ES-tf5 · nyam | 96 | 36 % | -$6,122 | n/n/n | `x0p05_atr3-r1` | 425 | $2,138 | 0.10 |  | | | heat map |
| vwap_trend_pull-ES-tf15 · mid | 96 | 19 % | -$9,548 | n/n/n | `x0p05_pts12-r3` | 586 | $6 | 0.00 |  | | | heat map |
| vwap_trend_pull-ES-tf1 · mid | 96 | 19 % | -$20,329 | n/n/n | `x0p1_pts12-r2` | 971 | $878 | 0.04 |  | | | heat map |
| vwap_trend_pull-ES-tf30 · mid | 91 | 14 % | -$5,337 | n/n/n | `x0p05_pts8-r0` | 246 | $16 | 0.00 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 7 of 11 units; on active days only in 0 of 11; on all days in 3.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| vwap_trend_pull-ES-tf30 · pm | 96 % / $4,184 | 12 % / -$2,670 |
| vwap_trend_pull-ES-tf15 · nyam | 78 % / $4,178 | 20 % / -$3,016 |
| vwap_trend_pull-ES-tf5 · pm | 78 % / $14,286 | 30 % / -$5,724 |
| vwap_trend_pull-ES-tf15 · pm | 84 % / $10,686 | 12 % / -$5,526 |
| vwap_trend_pull-ES-tf1 · pm | 65 % / $13,535 | 8 % / -$14,322 |
| vwap_trend_pull-ES-tf1 · nyam | 58 % / $3,741 | 4 % / -$13,207 |
| vwap_trend_pull-ES-tf5 · mid | 60 % / $6,879 | 6 % / -$16,684 |
| vwap_trend_pull-ES-tf5 · nyam | 56 % / $1,294 | 19 % / -$7,840 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
