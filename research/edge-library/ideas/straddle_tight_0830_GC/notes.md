# tight straddle at 08:30 ET (`straddle_tight_0830`) on GC — idea record (stage 2b = new-idea round 1, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).
* Rules as run: N7 straddle_tight 08:30 ET: OCO stop entries at last price +/- off points (A / B / C: NQ 3 / 5 / 8, ES 0.75 / 1.25 / 2, GC 0.6 / 1 / 1.6), placed at 08:29:59, unfilled legs cancelled 5 min later, entries until 09:30; own exits: stop NQ 5 / 8 / 10 pts (ES 1.25 / 2 / 2.5, GC 1 / 1.6 / 2) x target 1:1 / 1:2 / 1:3; null = the same bracket at random minutes (shift_seed). Second chance of the old NQ 09:30 straddle. CARD: the bracket is live within a second of the event -> the 2 ticks + 250 ms stress is the real gate
* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.
* Units judged: 1. Heat map passes at 60 / 70 / 80 % of variants positive: 1 / 1 / 1. Also beat the matched random control: 1. Also reach the best-of-random bar (= pass BUILD): 1.

## Every unit on BUILD (sorted by the share of variants positive)
| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| straddle_tight_0830-GC-tf30 · pre | 27 | 85 % | $5,004 | Y/Y/Y | `offC_pts2-r1` | 434 | $5,004 | 1.17 | 0.63 | $11,552 | n/a | none: passes BUILD |

Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.

## Quiet / active days (information only, not a test)
Heat map on quiet days only (prior-day range at or below its 20-day median) passes in 1 of 1 units; on active days only in 1 of 1; on all days in 1.
| unit | quiet: variants positive / median | active: variants positive / median |
|---|---|---|
| straddle_tight_0830-GC-tf30 · pre | 81 % / $1,906 | 81 % / $2,094 |
(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)

## 2024 (opened only for the units that passed every BUILD test; passing session only)
* straddle_tight_0830-GC-tf30 · pre: 2024 heat map 70 % of 27 variants positive, median $1,970 -> PASSES. BUILD central variant `offC_pts2-r1` in 2024: -$1,180 (210 trades), lift over its random control $3,066. Under 2 ticks + 250 ms: BUILD $5,004 -> $1,384; 2024 -$1,180 -> -$3,510. 2 of 27 variants are positive in both periods and under stress. **NOT ADMITTED**: the BUILD central variant is not positive in 2024 and no moved default is allowed (record: `members/_rejected/straddle_tight_0830_GC_tf30_pre/`).
These units' 2024 is now spent: information only from here.

## Left on the DONE checklist
* the standard 8-stop menu and the no-target exit (it ran its own 3 stops x 3 targets); more random-minute seeds (thin bar); deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, inverse, time exit (Level 2 tools: NQ only); verdict

Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, 1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).
