# opening-range close break, one direction (`orb_confirm`) on GC — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The opening range is the first balance; a bar CLOSE outside it shows acceptance, and one direction per day never holds opposite positions (Apex rule).
* Rules as run: N3 orb_confirm: range = the first or_min minutes from 09:30; a bar closes above it -> market long (dir long) / below it -> market short (dir short); LONG-ONLY and SHORT-ONLY are separate MIRROR units; one trade per session instance. Author cell (information only): stop at the other side of the range, flat 15:30
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 18. Heat map passes at 60 / 70 / 80 % of variants positive: 2 / 0 / 0. Also beat the matched random control: 2. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orb_confirm-GC-tf5 · mid · dir=short | 95 | 64 % | $2,806 | Y/n/n | `dirshort_or_min15_atr1p5-r3` | 286 | $2,806 | 0.33 | 1.24 | $1,721 | 60 % | bar |
| orb_confirm-GC-tf15 · mid · dir=short | 92 | 62 % | $4,008 | Y/n/n | `dirshort_or_min15_pct0p2-r3` | 273 | $3,948 | 0.47 | 1.24 | $1,031 | 56 % | bar |
| orb_confirm-GC-tf1 · mid · dir=short | 96 | 59 % | $1,029 | n/n/n | `dirshort_or_min60_pts2-r0` | 219 | $894 | 0.15 |  | | | heat map |
| orb_confirm-GC-tf15 · pm · dir=long | 96 | 54 % | $360 | n/n/n | `dirlong_or_min30_pct0p2-r3` | 222 | $362 | 0.07 |  | | | heat map |
| orb_confirm-GC-tf1 · pm · dir=long | 96 | 51 % | $202 | n/n/n | `dirlong_or_min15_pts5-r2` | 278 | $158 | 0.02 |  | | | heat map |
| orb_confirm-GC-tf5 · pm · dir=long | 96 | 42 % | -$795 | n/n/n | `dirlong_or_min30_pts3-r2` | 234 | $4 | 0.00 |  | | | heat map |
| orb_confirm-GC-tf5 · mid · dir=long | 96 | 38 % | -$3,014 | n/n/n | `dirlong_or_min60_atr3-r1` | 210 | $270 | 0.03 |  | | | heat map |
| orb_confirm-GC-tf15 · nyam · dir=short | 93 | 37 % | -$2,142 | n/n/n | `dirshort_or_min60_atr3-r0` | 60 | $70 | 0.01 |  | | | heat map |
| orb_confirm-GC-tf15 · nyam · dir=long | 95 | 34 % | -$2,108 | n/n/n | `dirlong_or_min15_pts5-r1` | 251 | $36 | 0.00 |  | | | heat map |
| orb_confirm-GC-tf5 · nyam · dir=long | 96 | 33 % | -$3,050 | n/n/n | `dirlong_or_min30_pts2-r1` | 225 | $230 | 0.07 |  | | | heat map |
| orb_confirm-GC-tf1 · nyam · dir=short | 96 | 32 % | -$2,949 | n/n/n | `dirshort_or_min15_atr3-r2` | 335 | $210 | 0.02 |  | | | heat map |
| orb_confirm-GC-tf1 · pm · dir=short | 96 | 29 % | -$1,496 | n/n/n | `dirshort_or_min15_pts5-r0` | 284 | $134 | 0.02 |  | | | heat map |
| orb_confirm-GC-tf1 · mid · dir=long | 96 | 23 % | -$4,172 | n/n/n | `dirlong_or_min60_atr3-r0` | 222 | $172 | 0.02 |  | | | heat map |
| orb_confirm-GC-tf15 · mid · dir=long | 96 | 22 % | -$3,391 | n/n/n | `dirlong_or_min60_pts7-r2` | 197 | $222 | 0.03 |  | | | heat map |
| orb_confirm-GC-tf5 · pm · dir=short | 96 | 22 % | -$2,418 | n/n/n | `dirshort_or_min30_pts5-r2` | 245 | $50 | 0.01 |  | | | heat map |
| orb_confirm-GC-tf5 · nyam · dir=short | 95 | 21 % | -$3,432 | n/n/n | `dirshort_or_min30_pts3-r2` | 228 | $318 | 0.05 |  | | | heat map |
| orb_confirm-GC-tf1 · nyam · dir=long | 96 | 17 % | -$5,063 | n/n/n | `dirlong_or_min15_atr3-r2` | 352 | $452 | 0.05 |  | | | heat map |
| orb_confirm-GC-tf15 · pm · dir=short | 93 | 12 % | -$2,446 | n/n/n | `dirshort_or_min15_pct0p1-r0` | 262 | $122 | 0.02 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 5 of 18 units; on active days only in 5 of 18; on all days in 2.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| orb_confirm-GC-tf5 · mid · dir=short | 40 % / -$462 | 72 % / $3,398 |
| orb_confirm-GC-tf15 · mid · dir=short | 48 % / -$52 | 64 % / $2,386 |
| orb_confirm-GC-tf1 · mid · dir=short | 70 % / $1,672 | 51 % / $94 |
| orb_confirm-GC-tf15 · pm · dir=long | 0 % / -$1,872 | 78 % / $3,115 |
| orb_confirm-GC-tf1 · pm · dir=long | 15 % / -$1,297 | 68 % / $2,084 |
| orb_confirm-GC-tf5 · pm · dir=long | 1 % / -$1,868 | 59 % / $1,283 |
| orb_confirm-GC-tf5 · mid · dir=long | 40 % / -$1,552 | 57 % / $1,277 |
| orb_confirm-GC-tf15 · nyam · dir=short | 45 % / -$513 | 24 % / -$2,128 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Author cells (information only: never in the heat map, never the member)
54 author cells: 32 positive, median $759, best $11,212, worst -$11,932. Highest t: `authon_dirlong_or_min30_struct1p5-r0` in orb_confirm-GC-tf1 · pm · dir=long: 236 trades, $7,056, t 0.98. All: `out/admit_r1/author_cells.csv`.

## Left on the DONE checklist
* 30-minute bars; deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
