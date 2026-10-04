# event straddle on ES — idea record (stage 3 = new-idea round 2, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4
* Reason written first: a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way.
* What was done: no new strategy code. The stored BUILD trades of three straddle families that ran on EVERY day were split by an official release calendar (`engine/cache/events.csv`, never checked against prices): E1 tight straddle at 08:30, E2 ATR straddle at 08:30, E3 tight straddle at 10:00. Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims), B = the same without claims-only days, C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).
* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2024 was opened only for units that passed every BUILD test. 2025+ was never read.
* A unit passes BUILD only with all five: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and median positive · (c) more per trade than the same bracket on days without a release at that time · (d) t at or above the random-minute bar · (e) beats 99.67 % of 4,000 random same-size day subsets.

## The five units on BUILD
| unit | family · time · days | BUILD trades | variants positive | median variant | central variant | its net | t / bar | lift a trade vs non-event days | beats random day subsets | BUILD |
|---|---|---|---|---|---|---|---|---|---|---|
| E1-A-ES | straddle_tight_0830 · 08:30 · group A | 226 | 48 % of 27 | -$179 | `offA_pts2p5-r3` | $758 | 0.22 / 2.00 | $29 | 93.0 % | fail: b, d, e |
| E1-B-ES | straddle_tight_0830 · 08:30 · group B | 158 | 85 % of 27 | $2,118 | `offA_pts2-r2` | $2,118 | 1.09 / 2.00 | $45 | 100.0 % | fail: d |
| E2-A-ES | straddle_t_0830 · 08:30 · group A | 226 | 31 % of 160 | -$3,229 | `offatr0p25_pts2p5-r2` | $196 | 0.07 / 2.00 | $31 | 97.8 % | fail: b, d, e |
| E2-B-ES | straddle_t_0830 · 08:30 · group B | 155 | 38 % of 160 | -$2,494 | `offptsB_pts2p5-r3` | $68 | 0.02 / 2.00 | $29 | 96.0 % | fail: b, d, e |
| E3-C-ES | straddle_tight_1000 · 10:00 · group C | 97 | 81 % of 27 | $1,450 | `offC_pts2-r2` | $1,450 | 0.94 / 2.00 | $54 | 100.0 % | fail: d |

## What each release type did (central variant, BUILD; information only: too few trades per type)
* E1-A-ES `offA_pts2p5-r3`: jobs report (NFP) 26 trades $884 · CPI 27 trades $3,342 · PPI 27 trades $792 · retail sales 27 trades $792 · GDP 28 trades -$887 · PCE 27 trades -$746 · weekly jobless claims 119 trades -$3,514 · no release at that time 341 trades -$8,789.
* E2-A-ES `offatr0p25_pts2p5-r2`: jobs report (NFP) 26 trades $1,334 · CPI 27 trades $2,442 · PPI 27 trades $1,967 · retail sales 27 trades $442 · GDP 28 trades -$1,637 · PCE 27 trades -$333 · weekly jobless claims 119 trades -$4,114 · no release at that time 345 trades -$10,455.
* E3-C-ES `offC_pts2-r2`: ISM manufacturing 27 trades -$670 · ISM services 27 trades -$358 · JOLTS 27 trades -$33 · Michigan sentiment (prelim) 27 trades $2,154 · no release at that time 463 trades -$18,014.

## Fed decision at 14:00 ET (information only; 19 BUILD days, tight straddle armed at 13:59:59)
* 89 % of 27 variants positive, median $703; central variant `offA_pts2-r2`: 18 trades, $703, t 1.03. Too few trades for any test; never opened on 2024.

## 2024 (opened only for the units that passed every BUILD test; whole menu, same day filter, random-minute control run too)
* No unit passed BUILD: 2024 was not opened for this market.

## Left on the DONE checklist
* real (paper or small-size) fills on release days: the profit needs a fill on the trigger print; the standard 8-stop menu and the no-target exit for the tight straddle (it ran its own 3 stops x 3 targets); more random-minute seeds; deepen rounds (0 of 4 used); the sealed 2025+ exam.

Files here: `units.csv` (the five units with every test), `heatmap.csv` (every variant of every unit on its event days; 2024 rows only for opened units), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv` (per release type). Scripts and raw results: `out/events/`.
