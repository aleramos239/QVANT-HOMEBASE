# volume-spike breakout (`vol_spike_break`) on ES — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: A break of the recent range on unusually high volume has real participation behind it; breaks on normal volume are more often noise.
* Rules as run: N6 vol_spike_break: a bar closes beyond the high / low of the 20 bars before it with volume >= m x their median volume -> market in that direction; max 2 trades per session instance
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 23. Heat map passes at 60 / 70 / 80 % of variants positive: 3 / 3 / 2. Also beat the matched random control: 2. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vol_spike_break-ES-tf15 · pm | 95 | 92 % | $4,520 | Y/Y/Y | `m4_pts12-r0` | 20 | $4,520 | 0.93 | 1.30 | -$4,765 | 17 % | c1,bar |
| vol_spike_break-ES-tf5 · mid | 95 | 92 % | $3,004 | Y/Y/Y | `m3_atr1p5-r0` | 27 | $3,004 | 0.71 | 1.30 | $3,795 | 90 % | bar |
| vol_spike_break-ES-tf30 · pm | 93 | 80 % | $9,042 | Y/Y/n | `m3_atr3-r1` | 102 | $9,042 | 0.78 | 1.30 | $10,374 | 92 % | bar |
| vol_spike_break-ES-tf1 · mid | 96 | 59 % | $2,884 | n/n/n | `m3_pct0p2-r1` | 451 | $2,821 | 0.31 |  | | | heat map |
| vol_spike_break-ES-tf30 · nyam | 32 | 59 % | $4,875 | n/n/n | `m2_pts12-r1` | 189 | $3,632 | 0.44 |  | | | heat map |
| vol_spike_break-ES-tf5 · pm | 96 | 50 % | -$154 | n/n/n | `m2_atr1p5-r2` | 371 | $228 | 0.02 |  | | | heat map |
| vol_spike_break-ES-tf15 · mid | 96 | 49 % | -$761 | n/n/n | `m4_pts5-r1` | 176 | $246 | 0.07 |  | | | heat map |
| vol_spike_break-ES-tf15 · eve | 95 | 48 % | -$41 | n/n/n | `m3_pct0p1-r3` | 7 | $10 | 0.01 |  | | | heat map |
| vol_spike_break-ES-tf15 · nyam | 88 | 45 % | -$2,113 | n/n/n | `m4_pts12-r3` | 455 | $42 | 0.00 |  | | | heat map |
| vol_spike_break-ES-tf5 · nyam | 96 | 41 % | -$9,490 | n/n/n | `m3_pct0p2-r3` | 565 | $65 | 0.00 |  | | | heat map |
| vol_spike_break-ES-tf30 · mid | 85 | 32 % | -$4,226 | n/n/n | `m4_pts12-r2` | 238 | $60 | 0.01 |  | | | heat map |
| vol_spike_break-ES-tf1 · nyam | 96 | 25 % | -$13,490 | n/n/n | `m4_pts8-r2` | 587 | $827 | 0.06 |  | | | heat map |
| vol_spike_break-ES-tf15 · pre | 96 | 19 % | -$6,397 | n/n/n | `m2_pts5-r0` | 259 | $76 | 0.01 |  | | | heat map |
| vol_spike_break-ES-tf1 · pm | 96 | 14 % | -$6,790 | n/n/n | `m4_pct0p2-r2` | 297 | $274 | 0.03 |  | | | heat map |
| vol_spike_break-ES-tf5 · asia | 96 | 12 % | -$12,124 | n/n/n | `m3_atr1p5-r0` | 299 | $366 | 0.02 |  | | | heat map |
| vol_spike_break-ES-tf1 · asia | 96 | 3 % | -$34,028 | n/n/n | `m2_pts12-r3` | 636 | $12,806 | 0.50 |  | | | heat map |
| vol_spike_break-ES-tf1 · london | 96 | 3 % | -$35,023 | n/n/n | `m2_pts12-r1` | 954 | $896 | 0.05 |  | | | heat map |
| vol_spike_break-ES-tf1 · pre | 96 | 2 % | -$18,540 | n/n/n | `m4_atr3-r0` | 304 | $1,859 | 0.09 |  | | | heat map |
| vol_spike_break-ES-tf5 · london | 96 | 2 % | -$19,057 | n/n/n | `m2_pts12-r0` | 697 | $2,512 | 0.08 |  | | | heat map |
| vol_spike_break-ES-tf5 · pre | 96 | 1 % | -$12,828 | n/n/n | `m2_pts5-r0` | 375 | $2,988 | 0.17 |  | | | heat map |
| vol_spike_break-ES-tf15 · london | 96 | 0 % | -$8,222 | n/n/n | none | | | |  | | | heat map |
| vol_spike_break-ES-tf1 · eve | 96 | 0 % | -$45,231 | n/n/n | none | | | |  | | | heat map |
| vol_spike_break-ES-tf5 · eve | 96 | 0 % | -$23,937 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 7 of 23 units; on active days only in 3 of 23; on all days in 3.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| vol_spike_break-ES-tf15 · pm | 75 % / $2,898 | 80 % / $1,302 |
| vol_spike_break-ES-tf5 · mid | 91 % / $3,873 | 31 % / -$417 |
| vol_spike_break-ES-tf30 · pm | 82 % / $7,376 | 62 % / $708 |
| vol_spike_break-ES-tf1 · mid | 58 % / $1,197 | 50 % / -$2 |
| vol_spike_break-ES-tf30 · nyam | 69 % / $8,606 | 35 % / -$2,624 |
| vol_spike_break-ES-tf5 · pm | 65 % / $1,327 | 41 % / -$718 |
| vol_spike_break-ES-tf15 · mid | 81 % / $5,012 | 23 % / -$3,536 |
| vol_spike_break-ES-tf15 · eve | 11 % / -$1,394 | 84 % / $1,002 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
