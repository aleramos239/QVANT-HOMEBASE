# volume-spike breakout (`vol_spike_break`) on GC — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: A break of the recent range on unusually high volume has real participation behind it; breaks on normal volume are more often noise.
* Rules as run: N6 vol_spike_break: a bar closes beyond the high / low of the 20 bars before it with volume >= m x their median volume -> market in that direction; max 2 trades per session instance
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 23. Heat map passes at 60 / 70 / 80 % of variants positive: 1 / 1 / 1. Also beat the matched random control: 1. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vol_spike_break-GC-tf30 · mid | 87 | 90 % | $3,158 | Y/Y/Y | `m2_atr3-r1` | 93 | $3,158 | 0.50 | 1.24 | $8,134 | 99 % | bar |
| vol_spike_break-GC-tf15 · pre | 96 | 59 % | $4,111 | n/n/n | `m4_pts2-r0` | 243 | $4,118 | 0.39 |  | | | heat map |
| vol_spike_break-GC-tf30 · nyam | 96 | 57 % | $1,097 | n/n/n | `m2_pts2-r3` | 104 | $1,074 | 0.29 |  | | | heat map |
| vol_spike_break-GC-tf5 · pm | 96 | 57 % | $1,307 | n/n/n | `m3_pts2-r2` | 136 | $1,176 | 0.40 |  | | | heat map |
| vol_spike_break-GC-tf15 · pm | 92 | 54 % | $82 | n/n/n | `m3_pts2-r1` | 30 | $80 | 0.07 |  | | | heat map |
| vol_spike_break-GC-tf5 · nyam | 96 | 49 % | -$408 | n/n/n | `m4_pct0p2-r0` | 113 | $98 | 0.01 |  | | | heat map |
| vol_spike_break-GC-tf5 · pre | 96 | 47 % | -$485 | n/n/n | `m4_pct0p2-r1` | 326 | $396 | 0.06 |  | | | heat map |
| vol_spike_break-GC-tf5 · asia | 96 | 34 % | -$2,673 | n/n/n | `m2_pct0p1-r2` | 461 | $156 | 0.03 |  | | | heat map |
| vol_spike_break-GC-tf15 · eve | 96 | 29 % | -$856 | n/n/n | `m2_pts5-r3` | 39 | $34 | 0.01 |  | | | heat map |
| vol_spike_break-GC-tf1 · mid | 96 | 29 % | -$8,183 | n/n/n | `m4_pts3-r3` | 454 | $44 | 0.00 |  | | | heat map |
| vol_spike_break-GC-tf1 · asia | 96 | 28 % | -$22,089 | n/n/n | `m3_pct0p2-r2` | 724 | $294 | 0.02 |  | | | heat map |
| vol_spike_break-GC-tf1 · nyam | 96 | 27 % | -$8,211 | n/n/n | `m3_pts7-r0` | 560 | $590 | 0.03 |  | | | heat map |
| vol_spike_break-GC-tf15 · mid | 87 | 26 % | -$430 | n/n/n | `m2_pct0p2-r2` | 56 | $16 | 0.00 |  | | | heat map |
| vol_spike_break-GC-tf30 · pm | 83 | 20 % | -$956 | n/n/n | `m2_pct0p2-r2` | 44 | $94 | 0.03 |  | | | heat map |
| vol_spike_break-GC-tf1 · pre | 96 | 18 % | -$18,580 | n/n/n | `m4_pts3-r0` | 410 | $2,160 | 0.13 |  | | | heat map |
| vol_spike_break-GC-tf15 · nyam | 96 | 17 % | -$4,431 | n/n/n | `m2_pct0p2-r0` | 298 | $208 | 0.02 |  | | | heat map |
| vol_spike_break-GC-tf15 · london | 96 | 1 % | -$11,748 | n/n/n | `m4_pts7-r2` | 61 | $566 | 0.08 |  | | | heat map |
| vol_spike_break-GC-tf1 · eve | 96 | 1 % | -$32,573 | n/n/n | `m3_pts7-r1` | 719 | $6,734 | 0.36 |  | | | heat map |
| vol_spike_break-GC-tf1 · london | 96 | 0 % | -$29,117 | n/n/n | none | | | |  | | | heat map |
| vol_spike_break-GC-tf1 · pm | 96 | 0 % | -$19,133 | n/n/n | none | | | |  | | | heat map |
| vol_spike_break-GC-tf5 · eve | 96 | 0 % | -$17,815 | n/n/n | none | | | |  | | | heat map |
| vol_spike_break-GC-tf5 · london | 96 | 0 % | -$32,449 | n/n/n | none | | | |  | | | heat map |
| vol_spike_break-GC-tf5 · mid | 95 | 0 % | -$3,862 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 6 of 23 units; on active days only in 6 of 23; on all days in 1.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| vol_spike_break-GC-tf30 · mid | 74 % / $1,388 | 81 % / $1,506 |
| vol_spike_break-GC-tf15 · pre | 66 % / $3,339 | 72 % / $1,724 |
| vol_spike_break-GC-tf30 · nyam | 12 % / -$1,981 | 70 % / $1,979 |
| vol_spike_break-GC-tf5 · pm | 62 % / $731 | 56 % / $539 |
| vol_spike_break-GC-tf15 · pm | 63 % / $312 | 73 % / $708 |
| vol_spike_break-GC-tf5 · nyam | 49 % / -$110 | 38 % / -$1,306 |
| vol_spike_break-GC-tf5 · pre | 46 % / -$328 | 38 % / -$1,967 |
| vol_spike_break-GC-tf5 · asia | 59 % / $888 | 16 % / -$2,957 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
