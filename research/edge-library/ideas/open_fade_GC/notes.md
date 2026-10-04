# open fade (`open_fade`) on GC — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The first burst after the open often overshoots while opening orders clear; when it stalls, price reverts toward the pre-open price.
* Rules as run: N5 open_fade: ref = the 09:29 close; once price is >= k x ATR30 away from ref and a bar closes back toward ref beyond the prior bar's opposite extreme -> market toward ref; 09:30-11:00 (nyam), max 3 trades. Author cell (information only): target = the ref price
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 2. Heat map passes at 60 / 70 / 80 % of variants positive: 0 / 0 / 0. Also beat the matched random control: 0. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| open_fade-GC-tf5 · nyam | 96 | 4 % | -$11,566 | n/n/n | `k0p5_atr1p5-r0` | 531 | $616 | 0.04 |  | | | heat map |
| open_fade-GC-tf1 · nyam | 96 | 0 % | -$27,980 | n/n/n | none | | | |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 0 of 2 units; on active days only in 0 of 2; on all days in 0.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| open_fade-GC-tf5 · nyam | 51 % / $310 | 0 % / -$9,381 |
| open_fade-GC-tf1 · nyam | 20 % / -$9,910 | 1 % / -$14,149 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Author cells (information only: never in the heat map, never the member)
48 author cells: 0 positive, median -$21,787, best -$13,312, worst -$47,742. Highest t: `authon_k1p5_atr3-r0` in open_fade-GC-tf5 · nyam: 355 trades, -$13,590, t -1.30. All: `out/admit_r1/author_cells.csv`.

## Left on the DONE checklist
* 15- and 30-minute bars; deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
