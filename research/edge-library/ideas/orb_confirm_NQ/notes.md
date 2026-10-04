# opening-range close break, one direction (`orb_confirm`) on NQ — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The opening range is the first balance; a bar CLOSE outside it shows acceptance, and one direction per day never holds opposite positions (Apex rule).
* Rules as run: N3 orb_confirm: range = the first or_min minutes from 09:30; a bar closes above it -> market long (dir long) / below it -> market short (dir short); LONG-ONLY and SHORT-ONLY are separate MIRROR units; one trade per session instance. Author cell (information only): stop at the other side of the range, flat 15:30
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 18. Heat map passes at 60 / 70 / 80 % of variants positive: 9 / 7 / 5. Also beat the matched random control: 6. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orb_confirm-NQ-tf1 · mid · dir=long | 96 | 97 % | $18,534 | Y/Y/Y | `dirlong_or_min15_pts20-r3` | 316 | $18,296 | 1.42 | 2.02 | $14,983 | 92 % | bar |
| orb_confirm-NQ-tf15 · mid · dir=long | 96 | 91 % | $17,768 | Y/Y/Y | `dirlong_or_min30_pts30-r1` | 270 | $17,810 | 1.81 | 2.02 | $25,625 | 100 % | bar |
| orb_confirm-NQ-tf15 · pm · dir=long | 96 | 88 % | $26,486 | Y/Y/Y | `dirlong_or_min15_pct0p2-r0` | 301 | $26,696 | 1.57 | 2.02 | -$2,874 | 42 % | c1,bar |
| orb_confirm-NQ-tf5 · mid · dir=long | 96 | 83 % | $21,206 | Y/Y/Y | `dirlong_or_min15_pct0p2-r2` | 310 | $21,215 | 1.51 | 2.02 | $18,235 | 94 % | bar |
| orb_confirm-NQ-tf5 · pm · dir=long | 96 | 83 % | $18,857 | Y/Y/Y | `dirlong_or_min15_pct0p1-r0` | 310 | $19,130 | 1.12 | 2.02 | -$970 | 46 % | c1,bar |
| orb_confirm-NQ-tf5 · nyam · dir=long | 96 | 77 % | $6,236 | Y/Y/n | `dirlong_or_min30_pct0p1-r3` | 236 | $6,351 | 0.83 | 2.02 | $10,642 | 92 % | bar |
| orb_confirm-NQ-tf1 · pm · dir=long | 96 | 73 % | $8,573 | Y/Y/n | `dirlong_or_min15_pts30-r1` | 320 | $8,645 | 0.83 | 2.02 | $14,187 | 92 % | bar |
| orb_confirm-NQ-tf15 · nyam · dir=long | 95 | 68 % | $2,538 | Y/n/n | `dirlong_or_min60_pts30-r1` | 73 | $2,538 | 0.49 | 2.02 | $8,457 | 98 % | bar |
| orb_confirm-NQ-tf15 · nyam · dir=short | 96 | 67 % | $9,084 | Y/n/n | `dirshort_or_min30_pts10-r0` | 192 | $9,047 | 0.57 | 2.02 | -$20,080 | 2 % | c1,bar |
| orb_confirm-NQ-tf1 · nyam · dir=long | 96 | 51 % | $546 | n/n/n | `dirlong_or_min15_atr1p5-r0` | 348 | $893 | 0.03 |  | | | heat map |
| orb_confirm-NQ-tf15 · pm · dir=short | 96 | 49 % | -$532 | n/n/n | `dirshort_or_min60_pts10-r0` | 227 | $122 | 0.01 |  | | | heat map |
| orb_confirm-NQ-tf5 · mid · dir=short | 96 | 49 % | -$224 | n/n/n | `dirshort_or_min60_pts20-r0` | 229 | $1,174 | 0.07 |  | | | heat map |
| orb_confirm-NQ-tf15 · mid · dir=short | 96 | 46 % | -$1,689 | n/n/n | `dirshort_or_min15_pct0p1-r2` | 268 | $328 | 0.05 |  | | | heat map |
| orb_confirm-NQ-tf1 · mid · dir=short | 96 | 45 % | -$1,303 | n/n/n | `dirshort_or_min15_pct0p2-r2` | 299 | $29 | 0.00 |  | | | heat map |
| orb_confirm-NQ-tf5 · nyam · dir=short | 96 | 38 % | -$5,256 | n/n/n | `dirshort_or_min15_atr1p5-r3` | 303 | $418 | 0.02 |  | | | heat map |
| orb_confirm-NQ-tf5 · pm · dir=short | 96 | 38 % | -$4,149 | n/n/n | `dirshort_or_min60_pts45-r3` | 241 | $146 | 0.01 |  | | | heat map |
| orb_confirm-NQ-tf1 · pm · dir=short | 96 | 34 % | -$3,652 | n/n/n | `dirshort_or_min60_atr3-r1` | 253 | $108 | 0.01 |  | | | heat map |
| orb_confirm-NQ-tf1 · nyam · dir=short | 96 | 32 % | -$3,396 | n/n/n | `dirshort_or_min60_pts45-r0` | 156 | $16 | 0.00 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 14 of 18 units; on active days only in 5 of 18; on all days in 9.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| orb_confirm-NQ-tf1 · mid · dir=long | 100 % / $21,126 | 42 % / -$1,615 |
| orb_confirm-NQ-tf15 · mid · dir=long | 94 % / $9,632 | 76 % / $4,046 |
| orb_confirm-NQ-tf15 · pm · dir=long | 83 % / $11,732 | 92 % / $11,880 |
| orb_confirm-NQ-tf5 · mid · dir=long | 97 % / $23,030 | 44 % / -$938 |
| orb_confirm-NQ-tf5 · pm · dir=long | 93 % / $11,430 | 77 % / $8,380 |
| orb_confirm-NQ-tf5 · nyam · dir=long | 66 % / $3,321 | 65 % / $3,433 |
| orb_confirm-NQ-tf1 · pm · dir=long | 91 % / $7,105 | 56 % / $1,537 |
| orb_confirm-NQ-tf15 · nyam · dir=long | 39 % / -$1,448 | 66 % / $3,156 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Author cells (information only: never in the heat map, never the member)
54 author cells: 49 positive, median $43,835, best $83,592, worst -$4,847. Highest t: `authon_dirlong_or_min60_struct1p5-r0` in orb_confirm-NQ-tf15 · pm · dir=long: 243 trades, $65,788, t 3.23. All: `out/admit_r1/author_cells.csv`.

## Left on the DONE checklist
* 30-minute bars; deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
