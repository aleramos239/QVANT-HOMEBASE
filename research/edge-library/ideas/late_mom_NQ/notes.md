# late-day momentum (15:30) (`late_mom`) on NQ — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The day's early move predicts the last half hour (hedgers and late traders push the same way into the close; documented in the academic literature).
* Rules as run: N4 late_mom: at 15:30 ET market in the direction of sign(P_signal - prior close), P_signal = the last 1-minute close before sig (10:00 / 12:00 / 15:30), only if |move| >= thr %; flat 15:58; one trade a day; no trade on a contract-roll day or an equity half day; null (shift_seed) = the same trade with a random direction
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 1. Heat map passes at 60 / 70 / 80 % of variants positive: 0 / 0 / 0. Also beat the matched random control: 0. Also reach the best-of-random bar (= pass BUILD): 0.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| late_mom-NQ-tf30 · pm | 249 | 31 % | -$6,276 | n/n/n | `sig1200_thr0p25_pct0p2-r3` | 449 | $264 | 0.02 |  | | | heat map |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 0 of 1 units; on active days only in 0 of 1; on all days in 0.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| late_mom-NQ-tf30 · pm | 37 % / -$1,601 | 33 % / -$2,664 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## Left on the DONE checklist
* deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
