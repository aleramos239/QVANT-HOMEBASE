# value-area reclaim (`va_reclaim`) on NQ — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: A poke outside yesterday's value area that fails traps the late side; they exit and price returns into value.
* Rules as run: N2 va_reclaim: price trades below yesterday's VAL (70 % value area of the 09:30-16:00 volume by price) by >= d_atr x ATR14, then a bar closes back above VAL -> market long (mirror short at VAH); one trade per side per session instance; no trade on a contract-roll day
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 28. Heat map passes at 60 / 70 / 80 % of variants positive: 2 / 1 / 0. Also beat the matched random control: 2. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| va_reclaim-NQ-tf30 · nyam | 96 | 71 % | $8,640 | Y/Y/n | `d_atr0_pts45-r1` | 205 | $8,590 | 0.66 | 2.02 | $4,003 | 72 % | bar |
| va_reclaim-NQ-tf30 · asia | 96 | 62 % | $1,946 | Y/n/n | `d_atr0p5_pts20-r2` | 48 | $2,043 | 0.50 | 2.02 | $4,006 | 91 % | bar |
| va_reclaim-NQ-tf15 · nyam | 96 | 59 % | $6,030 | n/n/n | `d_atr0_atr3-r1` | 267 | $6,957 | 0.23 |  | | | heat map |
| va_reclaim-NQ-tf5 · nyam | 96 | 58 % | $5,089 | n/n/n | `d_atr0_atr1p5-r3` | 327 | $5,307 | 0.21 |  | | | heat map |
| va_reclaim-NQ-tf5 · pre | 96 | 58 % | $696 | n/n/n | `d_atr0p25_pts20-r1` | 143 | $778 | 0.16 |  | | | heat map |
| va_reclaim-NQ-tf30 · pm | 91 | 47 % | -$198 | n/n/n | `d_atr0p25_pct0p1-r3` | 124 | $14 | 0.00 |  | | | heat map |
| va_reclaim-NQ-tf15 · pre | 96 | 47 % | -$358 | n/n/n | `d_atr0p25_pts10-r0` | 125 | $120 | 0.01 |  | | | heat map |
| va_reclaim-NQ-tf30 · pre | 96 | 47 % | -$1,571 | n/n/n | `d_atr0_atr3-r1` | 135 | $50 | 0.00 |  | | | heat map |
| va_reclaim-NQ-tf15 · mid | 96 | 44 % | -$790 | n/n/n | `d_atr0p25_pct0p1-r2` | 178 | $113 | 0.02 |  | | | heat map |
| va_reclaim-NQ-tf1 · mid | 96 | 40 % | -$2,641 | n/n/n | `d_atr0p5_pct0p1-r2` | 244 | $134 | 0.02 |  | | | heat map |
| va_reclaim-NQ-tf1 · nyam | 96 | 40 % | -$5,688 | n/n/n | `d_atr0_pts45-r3` | 347 | $1,662 | 0.06 |  | | | heat map |
| va_reclaim-NQ-tf1 · eve | 96 | 32 % | -$3,382 | n/n/n | `d_atr0p25_pts10-r2` | 241 | $286 | 0.06 |  | | | heat map |
| va_reclaim-NQ-tf15 · asia | 96 | 30 % | -$3,114 | n/n/n | `d_atr0p25_pts10-r3` | 115 | $35 | 0.01 |  | | | heat map |
| va_reclaim-NQ-tf15 · pm | 93 | 25 % | -$5,523 | n/n/n | `d_atr0p5_pts20-r1` | 131 | $371 | 0.08 |  | | | heat map |
| va_reclaim-NQ-tf5 · asia | 96 | 24 % | -$9,118 | n/n/n | `d_atr0_pts45-r0` | 165 | $3,340 | 0.11 |  | | | heat map |
| va_reclaim-NQ-tf30 · eve | 96 | 20 % | -$3,458 | n/n/n | `d_atr0p25_pct0p2-r2` | 144 | $364 | 0.04 |  | | | heat map |
| va_reclaim-NQ-tf1 · asia | 96 | 19 % | -$10,602 | n/n/n | `d_atr0p5_pts30-r0` | 180 | $2,245 | 0.09 |  | | | heat map |
| va_reclaim-NQ-tf30 · mid | 96 | 18 % | -$7,182 | n/n/n | `d_atr0_pts45-r1` | 172 | $27 | 0.00 |  | | | heat map |
| va_reclaim-NQ-tf5 · mid | 96 | 18 % | -$6,258 | n/n/n | `d_atr0p5_pct0p2-r1` | 206 | $61 | 0.01 |  | | | heat map |
| va_reclaim-NQ-tf5 · eve | 96 | 17 % | -$5,410 | n/n/n | `d_atr0p5_pts10-r1` | 199 | $79 | 0.03 |  | | | heat map |
| va_reclaim-NQ-tf15 · eve | 96 | 11 % | -$7,232 | n/n/n | `d_atr0p25_pts20-r2` | 185 | $145 | 0.02 |  | | | heat map |
| va_reclaim-NQ-tf5 · pm | 96 | 7 % | -$9,090 | n/n/n | `d_atr0p25_pct0p1-r1` | 202 | $237 | 0.06 |  | | | heat map |
| va_reclaim-NQ-tf1 · pre | 96 | 4 % | -$7,448 | n/n/n | `d_atr0p5_atr3-r2` | 171 | $891 | 0.07 |  | | | heat map |
| va_reclaim-NQ-tf1 · pm | 96 | 3 % | -$9,670 | n/n/n | `d_atr0_pct0p1-r1` | 249 | $979 | 0.22 |  | | | heat map |
| va_reclaim-NQ-tf30 · london | 96 | 3 % | -$15,156 | n/n/n | `d_atr0p25_pts20-r2` | 231 | $566 | 0.06 |  | | | heat map |
| va_reclaim-NQ-tf15 · london | 96 | 2 % | -$18,642 | n/n/n | `d_atr0p25_pts10-r3` | 272 | $992 | 0.17 |  | | | heat map |
| va_reclaim-NQ-tf1 · london | 96 | 2 % | -$15,700 | n/n/n | `d_atr0p25_pts20-r2` | 331 | $646 | 0.06 |  | | | heat map |
| va_reclaim-NQ-tf5 · london | 96 | 0 % | -$26,544 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 4 of 28 units; on active days only in 7 of 28; on all days in 2.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| va_reclaim-NQ-tf30 · nyam | 60 % / $5,504 | 67 % / $3,590 |
| va_reclaim-NQ-tf30 · asia | 50 % / $16 | 66 % / $1,800 |
| va_reclaim-NQ-tf15 · nyam | 57 % / $6,428 | 78 % / $3,160 |
| va_reclaim-NQ-tf5 · nyam | 44 % / -$1,289 | 72 % / $7,690 |
| va_reclaim-NQ-tf5 · pre | 50 % / -$76 | 72 % / $1,563 |
| va_reclaim-NQ-tf30 · pm | 43 % / -$512 | 68 % / $916 |
| va_reclaim-NQ-tf15 · pre | 55 % / $796 | 47 % / -$656 |
| va_reclaim-NQ-tf30 · pre | 50 % / -$139 | 51 % / $100 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* the delta-flip version (spec: only if this shows life); deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
