# value-area reclaim (`va_reclaim`) on ES — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: A poke outside yesterday's value area that fails traps the late side; they exit and price returns into value.
* Rules as run: N2 va_reclaim: price trades below yesterday's VAL (70 % value area of the 09:30-16:00 volume by price) by >= d_atr x ATR14, then a bar closes back above VAL -> market long (mirror short at VAH); one trade per side per session instance; no trade on a contract-roll day
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 28. Heat map passes at 60 / 70 / 80 % of variants positive: 1 / 0 / 0. Also beat the matched random control: 0. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| va_reclaim-ES-tf30 · nyam | 96 | 70 % | $3,295 | Y/n/n | `d_atr0_pts5-r0` | 184 | $3,314 | 0.27 | 1.30 | -$6,542 | 7 % | c1,bar |
| va_reclaim-ES-tf15 · nyam | 96 | 53 % | $624 | n/n/n | `d_atr0p25_pts8-r1` | 228 | $600 | 0.10 |  | | | heat map |
| va_reclaim-ES-tf30 · mid | 96 | 52 % | $369 | n/n/n | `d_atr0p25_pts8-r1` | 157 | $322 | 0.06 |  | | | heat map |
| va_reclaim-ES-tf15 · mid | 96 | 39 % | -$1,810 | n/n/n | `d_atr0p5_pts2p5-r0` | 157 | $422 | 0.05 |  | | | heat map |
| va_reclaim-ES-tf30 · pm | 94 | 37 % | -$2,193 | n/n/n | `d_atr0p5_pts5-r3` | 109 | $676 | 0.15 |  | | | heat map |
| va_reclaim-ES-tf5 · nyam | 96 | 23 % | -$7,853 | n/n/n | `d_atr0p25_pts12-r0` | 257 | $322 | 0.02 |  | | | heat map |
| va_reclaim-ES-tf30 · london | 96 | 21 % | -$8,482 | n/n/n | `d_atr0p25_pct0p2-r0` | 228 | $150 | 0.01 |  | | | heat map |
| va_reclaim-ES-tf1 · nyam | 96 | 20 % | -$7,594 | n/n/n | `d_atr0_pts8-r2` | 340 | $190 | 0.02 |  | | | heat map |
| va_reclaim-ES-tf1 · pm | 96 | 19 % | -$9,868 | n/n/n | `d_atr0p5_atr1p5-r0` | 225 | $250 | 0.02 |  | | | heat map |
| va_reclaim-ES-tf5 · pm | 96 | 19 % | -$8,390 | n/n/n | `d_atr0p25_pts12-r0` | 192 | $857 | 0.07 |  | | | heat map |
| va_reclaim-ES-tf5 · asia | 96 | 17 % | -$3,516 | n/n/n | `d_atr0p25_pts12-r3` | 127 | $104 | 0.01 |  | | | heat map |
| va_reclaim-ES-tf5 · mid | 96 | 17 % | -$6,669 | n/n/n | `d_atr0p5_pts8-r0` | 204 | $134 | 0.01 |  | | | heat map |
| va_reclaim-ES-tf1 · asia | 96 | 16 % | -$5,193 | n/n/n | `d_atr0_atr3-r0` | 158 | $6 | 0.00 |  | | | heat map |
| va_reclaim-ES-tf15 · asia | 96 | 15 % | -$5,230 | n/n/n | `d_atr0_pts12-r2` | 117 | $632 | 0.07 |  | | | heat map |
| va_reclaim-ES-tf15 · pre | 96 | 15 % | -$4,126 | n/n/n | `d_atr0_pts2p5-r0` | 142 | $144 | 0.02 |  | | | heat map |
| va_reclaim-ES-tf15 · pm | 96 | 14 % | -$7,479 | n/n/n | `d_atr0p5_pts2p5-r0` | 141 | $386 | 0.06 |  | | | heat map |
| va_reclaim-ES-tf30 · asia | 96 | 12 % | -$3,338 | n/n/n | `d_atr0p25_atr1p5-r0` | 55 | $755 | 0.07 |  | | | heat map |
| va_reclaim-ES-tf15 · london | 96 | 10 % | -$9,100 | n/n/n | `d_atr0_pts5-r0` | 278 | $2,500 | 0.16 |  | | | heat map |
| va_reclaim-ES-tf1 · mid | 96 | 10 % | -$8,075 | n/n/n | `d_atr0p5_pts8-r0` | 252 | $217 | 0.01 |  | | | heat map |
| va_reclaim-ES-tf5 · london | 96 | 8 % | -$8,659 | n/n/n | `d_atr0p5_atr1p5-r2` | 287 | $290 | 0.04 |  | | | heat map |
| va_reclaim-ES-tf1 · london | 96 | 7 % | -$10,473 | n/n/n | `d_atr0p25_pts2p5-r0` | 324 | $466 | 0.04 |  | | | heat map |
| va_reclaim-ES-tf1 · pre | 96 | 1 % | -$11,561 | n/n/n | `d_atr0_atr3-r1` | 181 | $976 | 0.17 |  | | | heat map |
| va_reclaim-ES-tf5 · pre | 96 | 1 % | -$7,984 | n/n/n | `d_atr0p25_atr3-r1` | 130 | $480 | 0.06 |  | | | heat map |
| va_reclaim-ES-tf15 · eve | 96 | 0 % | -$15,401 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-ES-tf1 · eve | 96 | 0 % | -$18,870 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-ES-tf30 · eve | 96 | 0 % | -$11,052 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-ES-tf30 · pre | 96 | 0 % | -$9,935 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-ES-tf5 · eve | 96 | 0 % | -$18,926 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 3 of 28 units; on active days only in 1 of 28; on all days in 1.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| va_reclaim-ES-tf30 · nyam | 75 % / $2,798 | 55 % / $719 |
| va_reclaim-ES-tf15 · nyam | 45 % / -$966 | 68 % / $1,436 |
| va_reclaim-ES-tf30 · mid | 47 % / -$275 | 24 % / -$2,000 |
| va_reclaim-ES-tf15 · mid | 34 % / -$1,768 | 22 % / -$1,922 |
| va_reclaim-ES-tf30 · pm | 88 % / $5,425 | 7 % / -$5,780 |
| va_reclaim-ES-tf5 · nyam | 35 % / -$1,941 | 8 % / -$5,676 |
| va_reclaim-ES-tf30 · london | 54 % / $566 | 0 % / -$10,513 |
| va_reclaim-ES-tf1 · nyam | 43 % / -$1,506 | 5 % / -$5,252 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* the delta-flip version (spec: only if this shows life); deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
