# open fade (`open_fade`) on NQ — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The first burst after the open often overshoots while opening orders clear; when it stalls, price reverts toward the pre-open price.
* Rules as run: N5 open_fade: ref = the 09:29 close; once price is >= k x ATR30 away from ref and a bar closes back toward ref beyond the prior bar's opposite extreme -> market toward ref; 09:30-11:00 (nyam), max 3 trades. Author cell (information only): target = the ref price
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 2. Heat map passes at 60 / 70 / 80 % of variants positive: 0 / 0 / 0. Also beat the matched random control: 0. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| open_fade-NQ-tf5 · nyam | 96 | 39 % | -$7,042 | n/n/n | `k0p5_atr1p5-r1` | 712 | $2,072 | 0.09 |  | | | heat map |
| open_fade-NQ-tf1 · nyam | 96 | 31 % | -$17,492 | n/n/n | `k1p5_atr3-r3` | 1043 | $48 | 0.00 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 0 of 2 units; on active days only in 0 of 2; on all days in 0.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| open_fade-NQ-tf5 · nyam | 46 % / -$1,740 | 31 % / -$3,472 |
| open_fade-NQ-tf1 · nyam | 35 % / -$7,618 | 40 % / -$4,528 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Author cells (information only: never in the heat map, never the member)
48 author cells: 18 positive, median -$3,520, best $14,727, worst -$49,388. Highest t: `authon_k1_pct0p2-r0` in open_fade-NQ-tf5 · nyam: 676 trades, $13,501, t 0.66. All: `out/admit_r1/author_cells.csv`.

## Left on the DONE checklist
* 15- and 30-minute bars; deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
