# value-area reclaim (`va_reclaim`) on GC — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: A poke outside yesterday's value area that fails traps the late side; they exit and price returns into value.
* Rules as run: N2 va_reclaim: price trades below yesterday's VAL (70 % value area of the 09:30-16:00 volume by price) by >= d_atr x ATR14, then a bar closes back above VAL -> market long (mirror short at VAH); one trade per side per session instance; no trade on a contract-roll day
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 28. Heat map passes at 60 / 70 / 80 % of variants positive: 0 / 0 / 0. Also beat the matched random control: 0. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| va_reclaim-GC-tf30 · pre | 96 | 43 % | -$978 | n/n/n | `d_atr0p5_atr1p5-r2` | 111 | $26 | 0.00 |  | | | heat map |
| va_reclaim-GC-tf15 · nyam | 96 | 40 % | -$1,767 | n/n/n | `d_atr0p5_pts5-r2` | 166 | $86 | 0.01 |  | | | heat map |
| va_reclaim-GC-tf1 · nyam | 96 | 40 % | -$1,846 | n/n/n | `d_atr0p5_atr1p5-r1` | 307 | $152 | 0.05 |  | | | heat map |
| va_reclaim-GC-tf5 · nyam | 96 | 40 % | -$2,009 | n/n/n | `d_atr0_pts3-r1` | 288 | $258 | 0.05 |  | | | heat map |
| va_reclaim-GC-tf1 · asia | 96 | 28 % | -$2,180 | n/n/n | `d_atr0p5_pts5-r3` | 274 | $14 | 0.00 |  | | | heat map |
| va_reclaim-GC-tf1 · london | 96 | 24 % | -$2,957 | n/n/n | `d_atr0p5_pts3-r2` | 372 | $32 | 0.00 |  | | | heat map |
| va_reclaim-GC-tf30 · asia | 96 | 22 % | -$2,316 | n/n/n | `d_atr0p5_pts5-r1` | 98 | $118 | 0.02 |  | | | heat map |
| va_reclaim-GC-tf5 · asia | 96 | 22 % | -$2,840 | n/n/n | `d_atr0p25_pts2-r2` | 265 | $10 | 0.00 |  | | | heat map |
| va_reclaim-GC-tf30 · nyam | 96 | 19 % | -$4,145 | n/n/n | `d_atr0_pts3-r3` | 163 | $78 | 0.01 |  | | | heat map |
| va_reclaim-GC-tf1 · pre | 96 | 16 % | -$4,836 | n/n/n | `d_atr0_atr3-r1` | 289 | $484 | 0.08 |  | | | heat map |
| va_reclaim-GC-tf15 · asia | 96 | 14 % | -$4,376 | n/n/n | `d_atr0p25_pts7-r1` | 201 | $1,286 | 0.13 |  | | | heat map |
| va_reclaim-GC-tf30 · pm | 80 | 12 % | -$2,159 | n/n/n | `d_atr0_pct0p1-r0` | 86 | $6 | 0.00 |  | | | heat map |
| va_reclaim-GC-tf5 · pre | 96 | 12 % | -$8,474 | n/n/n | `d_atr0_pct0p1-r2` | 249 | $184 | 0.04 |  | | | heat map |
| va_reclaim-GC-tf5 · london | 96 | 9 % | -$7,872 | n/n/n | `d_atr0p25_pct0p1-r0` | 334 | $824 | 0.07 |  | | | heat map |
| va_reclaim-GC-tf15 · pm | 94 | 9 % | -$2,765 | n/n/n | `d_atr0p25_pts7-r0` | 87 | $162 | 0.04 |  | | | heat map |
| va_reclaim-GC-tf15 · pre | 96 | 5 % | -$6,247 | n/n/n | `d_atr0_pct0p2-r3` | 204 | $104 | 0.01 |  | | | heat map |
| va_reclaim-GC-tf30 · eve | 96 | 5 % | -$9,668 | n/n/n | `d_atr0p25_atr1p5-r3` | 272 | $1,832 | 0.20 |  | | | heat map |
| va_reclaim-GC-tf5 · pm | 96 | 3 % | -$5,202 | n/n/n | `d_atr0p25_pts7-r3` | 109 | $924 | 0.17 |  | | | heat map |
| va_reclaim-GC-tf15 · london | 96 | 1 % | -$14,034 | n/n/n | `d_atr0_atr3-r0` | 323 | $2,978 | 0.15 |  | | | heat map |
| va_reclaim-GC-tf15 · eve | 96 | 0 % | -$18,610 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf15 · mid | 96 | 0 % | -$10,884 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf1 · eve | 96 | 0 % | -$18,898 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf1 · mid | 96 | 0 % | -$13,830 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf1 · pm | 96 | 0 % | -$7,178 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf30 · london | 96 | 0 % | -$15,636 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf30 · mid | 93 | 0 % | -$8,644 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf5 · eve | 96 | 0 % | -$16,896 | n/n/n | none | | | |  | | | heat map |
| va_reclaim-GC-tf5 · mid | 96 | 0 % | -$17,084 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 1 of 28 units; on active days only in 2 of 28; on all days in 0.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| va_reclaim-GC-tf30 · pre | 53 % / $77 | 41 % / -$593 |
| va_reclaim-GC-tf15 · nyam | 28 % / -$1,976 | 51 % / $110 |
| va_reclaim-GC-tf1 · nyam | 60 % / $1,638 | 28 % / -$2,616 |
| va_reclaim-GC-tf5 · nyam | 42 % / -$1,411 | 44 % / -$736 |
| va_reclaim-GC-tf1 · asia | 39 % / -$1,312 | 31 % / -$1,455 |
| va_reclaim-GC-tf1 · london | 30 % / -$2,351 | 45 % / -$1,273 |
| va_reclaim-GC-tf30 · asia | 5 % / -$3,400 | 53 % / $153 |
| va_reclaim-GC-tf5 · asia | 35 % / -$1,355 | 34 % / -$1,040 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* the delta-flip version (spec: only if this shows life); deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
