# opening-range close break, one direction (`orb_confirm`) on ES — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The opening range is the first balance; a bar CLOSE outside it shows acceptance, and one direction per day never holds opposite positions (Apex rule).
* Rules as run: N3 orb_confirm: range = the first or_min minutes from 09:30; a bar closes above it -> market long (dir long) / below it -> market short (dir short); LONG-ONLY and SHORT-ONLY are separate MIRROR units; one trade per session instance. Author cell (information only): stop at the other side of the range, flat 15:30
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 18. Heat map passes at 60 / 70 / 80 % of variants positive: 4 / 1 / 1. Also beat the matched random control: 4. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orb_confirm-ES-tf5 · pm · dir=long | 96 | 83 % | $9,845 | Y/Y/Y | `dirlong_or_min30_atr1p5-r0` | 306 | $10,414 | 0.78 | 1.30 | $614 | 50 % | bar |
| orb_confirm-ES-tf15 · pm · dir=long | 96 | 69 % | $4,387 | Y/n/n | `dirlong_or_min15_pts2p5-r0` | 303 | $4,288 | 0.64 | 1.30 | $1,261 | 58 % | bar |
| orb_confirm-ES-tf15 · mid · dir=long | 96 | 68 % | $9,120 | Y/n/n | `dirlong_or_min30_pts8-r2` | 273 | $9,183 | 0.99 | 1.30 | $2,941 | 65 % | bar |
| orb_confirm-ES-tf1 · pm · dir=long | 96 | 60 % | $2,939 | Y/n/n | `dirlong_or_min30_pct0p1-r3` | 322 | $2,824 | 0.43 | 1.30 | $10,326 | 99 % | bar |
| orb_confirm-ES-tf5 · mid · dir=long | 96 | 59 % | $4,929 | n/n/n | `dirlong_or_min30_pts8-r0` | 293 | $5,140 | 0.36 |  | | | heat map |
| orb_confirm-ES-tf15 · pm · dir=short | 96 | 57 % | $4,595 | n/n/n | `dirshort_or_min15_pct0p2-r3` | 277 | $4,104 | 0.38 |  | | | heat map |
| orb_confirm-ES-tf1 · mid · dir=long | 96 | 56 % | $2,951 | n/n/n | `dirlong_or_min15_pts2p5-r0` | 330 | $2,905 | 0.27 |  | | | heat map |
| orb_confirm-ES-tf15 · nyam · dir=long | 95 | 52 % | $353 | n/n/n | `dirlong_or_min60_atr1p5-r0` | 68 | $353 | 0.04 |  | | | heat map |
| orb_confirm-ES-tf5 · nyam · dir=long | 96 | 51 % | $190 | n/n/n | `dirlong_or_min60_atr1p5-r0` | 112 | $302 | 0.03 |  | | | heat map |
| orb_confirm-ES-tf1 · nyam · dir=long | 96 | 47 % | -$862 | n/n/n | `dirlong_or_min60_atr3-r3` | 146 | $16 | 0.00 |  | | | heat map |
| orb_confirm-ES-tf5 · pm · dir=short | 96 | 40 % | -$3,072 | n/n/n | `dirshort_or_min30_atr3-r2` | 283 | $430 | 0.03 |  | | | heat map |
| orb_confirm-ES-tf1 · pm · dir=short | 96 | 39 % | -$4,333 | n/n/n | `dirshort_or_min60_pts5-r0` | 263 | $810 | 0.08 |  | | | heat map |
| orb_confirm-ES-tf15 · nyam · dir=short | 96 | 36 % | -$2,529 | n/n/n | `dirshort_or_min30_pts12-r3` | 205 | $255 | 0.02 |  | | | heat map |
| orb_confirm-ES-tf15 · mid · dir=short | 96 | 34 % | -$4,902 | n/n/n | `dirshort_or_min15_atr1p5-r1` | 292 | $344 | 0.03 |  | | | heat map |
| orb_confirm-ES-tf5 · mid · dir=short | 96 | 30 % | -$3,828 | n/n/n | `dirshort_or_min60_pct0p2-r1` | 244 | $74 | 0.01 |  | | | heat map |
| orb_confirm-ES-tf5 · nyam · dir=short | 96 | 18 % | -$8,112 | n/n/n | `dirshort_or_min30_pts12-r3` | 243 | $216 | 0.01 |  | | | heat map |
| orb_confirm-ES-tf1 · mid · dir=short | 96 | 12 % | -$9,391 | n/n/n | `dirshort_or_min30_atr3-r3` | 298 | $46 | 0.00 |  | | | heat map |
| orb_confirm-ES-tf1 · nyam · dir=short | 96 | 9 % | -$11,386 | n/n/n | `dirshort_or_min30_pts12-r0` | 287 | $40 | 0.00 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 10 of 18 units; on active days only in 3 of 18; on all days in 4.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| orb_confirm-ES-tf5 · pm · dir=long | 67 % / $4,563 | 92 % / $5,537 |
| orb_confirm-ES-tf15 · pm · dir=long | 74 % / $2,600 | 73 % / $2,517 |
| orb_confirm-ES-tf15 · mid · dir=long | 75 % / $12,915 | 10 % / -$3,633 |
| orb_confirm-ES-tf1 · pm · dir=long | 53 % / $381 | 68 % / $2,057 |
| orb_confirm-ES-tf5 · mid · dir=long | 74 % / $10,719 | 17 % / -$4,552 |
| orb_confirm-ES-tf15 · pm · dir=short | 64 % / $4,569 | 53 % / $346 |
| orb_confirm-ES-tf1 · mid · dir=long | 67 % / $5,110 | 30 % / -$1,941 |
| orb_confirm-ES-tf15 · nyam · dir=long | 71 % / $3,269 | 19 % / -$3,510 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Author cells (information only: never in the heat map, never the member)
54 author cells: 46 positive, median $12,392, best $30,343, worst -$11,736. Highest t: `authon_dirlong_or_min15_struct1p5-r0` in orb_confirm-ES-tf5 · pm · dir=long: 308 trades, $30,343, t 2.09. All: `out/admit_r1/author_cells.csv`.

## Left on the DONE checklist
* 30-minute bars; deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
