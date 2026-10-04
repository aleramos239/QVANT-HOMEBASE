# volume-spike breakout (`vol_spike_break`) on NQ — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: A break of the recent range on unusually high volume has real participation behind it; breaks on normal volume are more often noise.
* Rules as run: N6 vol_spike_break: a bar closes beyond the high / low of the 20 bars before it with volume >= m x their median volume -> market in that direction; max 2 trades per session instance
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 23. Heat map passes at 60 / 70 / 80 % of variants positive: 7 / 5 / 4. Also beat the matched random control: 7. Also reach the best-of-random bar (= pass BUILD): 1.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vol_spike_break-NQ-tf30 · nyam | 32 | 100 % | $22,770 | Y/Y/Y | `m2_pts30-r2` | 193 | $23,348 | 1.90 | 2.02 | $4,655 | 74 % | bar |
| vol_spike_break-NQ-tf30 · pm | 91 | 89 % | $18,134 | Y/Y/Y | `m4_pct0p2-r2` | 49 | $18,134 | 3.18 | 2.02 | $19,038 | 100 % | none: passes BUILD |
| vol_spike_break-NQ-tf5 · mid | 94 | 85 % | $4,526 | Y/Y/Y | `m3_pts30-r3` | 15 | $4,550 | 1.08 | 2.02 | $2,524 | 80 % | bar |
| vol_spike_break-NQ-tf5 · pm | 96 | 82 % | $8,540 | Y/Y/Y | `m3_pct0p2-r3` | 87 | $8,587 | 0.99 | 2.02 | $11,453 | 94 % | bar |
| vol_spike_break-NQ-tf15 · pm | 96 | 76 % | $3,047 | Y/Y/n | `m2_pct0p2-r1` | 54 | $3,079 | 0.76 | 2.02 | $7,029 | 98 % | bar |
| vol_spike_break-NQ-tf15 · nyam | 64 | 69 % | $21,786 | Y/n/n | `m2_pts20-r3` | 621 | $22,426 | 1.25 | 2.02 | $3,684 | 64 % | bar |
| vol_spike_break-NQ-tf1 · mid | 96 | 68 % | $4,276 | Y/n/n | `m3_pts10-r3` | 495 | $4,435 | 0.56 | 2.02 | $14,533 | 100 % | bar |
| vol_spike_break-NQ-tf1 · pre | 96 | 57 % | $3,668 | n/n/n | `m3_pct0p2-r2` | 511 | $3,996 | 0.22 |  | | | heat map |
| vol_spike_break-NQ-tf5 · pre | 96 | 53 % | $526 | n/n/n | `m4_pts20-r0` | 193 | $538 | 0.03 |  | | | heat map |
| vol_spike_break-NQ-tf5 · london | 96 | 49 % | -$422 | n/n/n | `m3_pts20-r1` | 644 | $359 | 0.04 |  | | | heat map |
| vol_spike_break-NQ-tf15 · pre | 96 | 48 % | -$746 | n/n/n | `m4_pct0p2-r3` | 127 | $392 | 0.04 |  | | | heat map |
| vol_spike_break-NQ-tf15 · eve | 94 | 44 % | -$86 | n/n/n | `m2_atr3-r3` | 20 | $235 | 0.03 |  | | | heat map |
| vol_spike_break-NQ-tf5 · nyam | 96 | 42 % | -$5,824 | n/n/n | `m4_pts45-r1` | 718 | $253 | 0.01 |  | | | heat map |
| vol_spike_break-NQ-tf30 · mid | 93 | 41 % | -$4,220 | n/n/n | `m2_pts30-r3` | 289 | $74 | 0.00 |  | | | heat map |
| vol_spike_break-NQ-tf1 · nyam | 96 | 41 % | -$6,134 | n/n/n | `m2_pct0p1-r2` | 1067 | $342 | 0.03 |  | | | heat map |
| vol_spike_break-NQ-tf15 · mid | 93 | 37 % | -$2,751 | n/n/n | `m2_pts30-r0` | 241 | $626 | 0.03 |  | | | heat map |
| vol_spike_break-NQ-tf15 · london | 96 | 32 % | -$1,876 | n/n/n | `m3_atr1p5-r3` | 73 | $63 | 0.01 |  | | | heat map |
| vol_spike_break-NQ-tf5 · asia | 96 | 31 % | -$5,452 | n/n/n | `m4_pts30-r3` | 153 | $533 | 0.04 |  | | | heat map |
| vol_spike_break-NQ-tf1 · london | 96 | 28 % | -$4,622 | n/n/n | `m2_pct0p1-r1` | 1134 | $244 | 0.03 |  | | | heat map |
| vol_spike_break-NQ-tf1 · pm | 96 | 27 % | -$6,681 | n/n/n | `m4_pts10-r2` | 277 | $587 | 0.12 |  | | | heat map |
| vol_spike_break-NQ-tf1 · asia | 96 | 24 % | -$16,632 | n/n/n | `m2_pct0p2-r3` | 756 | $401 | 0.02 |  | | | heat map |
| vol_spike_break-NQ-tf5 · eve | 96 | 8 % | -$18,066 | n/n/n | `m4_pts10-r3` | 265 | $840 | 0.14 |  | | | heat map |
| vol_spike_break-NQ-tf1 · eve | 96 | 4 % | -$28,150 | n/n/n | `m4_pct0p2-r2` | 849 | $684 | 0.03 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 15 of 23 units; on active days only in 5 of 23; on all days in 7.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| vol_spike_break-NQ-tf30 · nyam | 84 % / $14,327 | 90 % / $5,355 |
| vol_spike_break-NQ-tf30 · pm | 74 % / $7,486 | 93 % / $7,608 |
| vol_spike_break-NQ-tf5 · mid | 82 % / $2,368 | 78 % / $969 |
| vol_spike_break-NQ-tf5 · pm | 83 % / $7,401 | 68 % / $1,701 |
| vol_spike_break-NQ-tf15 · pm | 78 % / $1,987 | 59 % / $706 |
| vol_spike_break-NQ-tf15 · nyam | 73 % / $25,449 | 44 % / -$1,618 |
| vol_spike_break-NQ-tf1 · mid | 81 % / $5,782 | 47 % / -$626 |
| vol_spike_break-NQ-tf1 · pre | 94 % / $19,714 | 4 % / -$12,031 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## 2024 (opened only for the units that passed every BUILD test; passing session only)
* vol_spike_break-NQ-tf30 · pm: 2024 heat map 53 % of 96 variants positive, median $799 -> FAILS. BUILD central variant `m4_pct0p2-r2` in 2024: -$1,252 (28 trades), lift over its random control -$329. **NOT ADMITTED**: the 2024 heat map fails.
These units' 2024 is now spent: information only from here.

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
