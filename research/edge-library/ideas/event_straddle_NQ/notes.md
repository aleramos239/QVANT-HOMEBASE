# event straddle on NQ — idea record (stage 3 = new-idea round 2, 2026-10-04)

* **Status: ADMITTED, FLAGGED (`straddle_tight_0830_NQ_tf30_pre_evB`; checker: confirm or demote)** · deepen rounds used: 0 of 4
* Reason written first: a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way.
* What was done: no new strategy code. The stored BUILD trades of three straddle families that ran on EVERY day were split by an official release calendar (`engine/cache/events.csv`, never checked against prices): E1 tight straddle at 08:30, E2 ATR straddle at 08:30, E3 tight straddle at 10:00. Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims), B = the same without claims-only days, C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).
* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2024 was opened only for units that passed every BUILD test. 2025+ was never read.
* A unit passes BUILD only with all five: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and median positive · (c) more per trade than the same bracket on days without a release at that time · (d) t at or above the random-minute bar · (e) beats 99.67 % of 4,000 random same-size day subsets.

## The five units on BUILD
| unit | family · time · days | BUILD trades | variants positive | median variant | central variant | its net | t / bar | lift a trade vs non-event days | beats random day subsets | BUILD |
|---|---|---|---|---|---|---|---|---|---|---|
| E1-A-NQ | straddle_tight_0830 · 08:30 · group A | 225 | 100 % of 27 | $10,305 | `offB_pts8-r2` | $10,305 | 2.77 / 2.56 | $45 | 98.6 % | fail: e |
| E1-B-NQ | straddle_tight_0830 · 08:30 · group B | 157 | 100 % of 27 | $9,047 | `offB_pts5-r3` | $9,047 | 3.35 / 2.56 | $62 | 99.9 % | **PASS** |
| E2-A-NQ | straddle_t_0830 · 08:30 · group A | 225 | 79 % of 160 | $8,378 | `offatr0p25_atr3-r0` | $8,320 | 0.18 / 2.56 | -$177 | 23.6 % | fail: c, d, e |
| E2-B-NQ | straddle_t_0830 · 08:30 · group B | 157 | 74 % of 160 | $5,252 | `offatr0p5_pts30-r1` | $5,267 | 0.68 / 2.56 | $12 | 60.0 % | fail: d, e |
| E3-C-NQ | straddle_tight_1000 · 10:00 · group C | 95 | 96 % of 27 | $3,215 | `offA_pts5-r3` | $3,215 | 1.67 / 2.56 | $34 | 94.3 % | fail: d, e |

## What each release type did (central variant, BUILD; information only: too few trades per type)
* E1-A-NQ `offB_pts8-r2`: jobs report (NFP) 25 trades $2,360 · CPI 27 trades $2,582 · PPI 27 trades $3,537 · retail sales 27 trades $1,732 · GDP 28 trades -$402 · PCE 27 trades $1,167 · weekly jobless claims 119 trades $1,204 · no release at that time 324 trades $379.
* E2-A-NQ `offatr0p25_atr3-r0`: jobs report (NFP) 25 trades -$14,375 · CPI 27 trades $3,382 · PPI 27 trades -$4,938 · retail sales 27 trades -$7,333 · GDP 28 trades $5,348 · PCE 27 trades $11,817 · weekly jobless claims 119 trades $26,694 · no release at that time 343 trades $73,453.
* E3-C-NQ `offA_pts5-r3`: ISM manufacturing 26 trades $276 · ISM services 26 trades $786 · JOLTS 27 trades -$188 · Michigan sentiment (prelim) 27 trades $1,467 · no release at that time 473 trades $38.

## Fed decision at 14:00 ET (information only; 19 BUILD days, tight straddle armed at 13:59:59)
* 100 % of 27 variants positive, median $2,248; central variant `offC_pts8-r2`: 18 trades, $2,248, t 2.15. Too few trades for any test; never opened on 2024.

## 2024 (opened only for the units that passed every BUILD test; whole menu, same day filter, random-minute control run too)
* E1-B-NQ (SECOND LOOK on 2024): 81 % of 27 variants positive, median $2,838 -> passes. BUILD central variant `offB_pts5-r3` in 2024: $2,383 (68 trades); random-minute control -$1,658. Under 2 ticks + 250 ms: BUILD $9,047 -> $8,637; 2024 $2,383 -> $173. Per year: 2021* $1,124 (19) · 2022 $5,961 (71) · 2023 $1,962 (67) · 2024 $2,383 (68) · combined $11,430 (225). Entry 5 ms after the trigger print: BUILD $5,122, 2024 $473. Admission: every test passes.

## Left on the DONE checklist
* real (paper or small-size) fills on release days: the profit needs a fill on the trigger print; the standard 8-stop menu and the no-target exit for the tight straddle (it ran its own 3 stops x 3 targets); more random-minute seeds; deepen rounds (0 of 4 used); the sealed 2025+ exam.

Files here: `units.csv` (the five units with every test), `heatmap.csv` (every variant of every unit on its event days; 2024 rows only for opened units), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv` (per release type). Scripts and raw results: `out/events/`.
