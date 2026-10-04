# event straddle on GC — idea record (stage 3 = new-idea round 2, 2026-10-04)

* **Status: ADMITTED, FLAGGED (`straddle_tight_0830_GC_tf30_pre_evA`, `straddle_tight_1000_GC_tf30_nyam_evC`; checker: confirm or demote)** · deepen rounds used: 0 of 4
* Reason written first: a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way.
* What was done: no new strategy code. The stored BUILD trades of three straddle families that ran on EVERY day were split by an official release calendar (`engine/cache/events.csv`, never checked against prices): E1 tight straddle at 08:30, E2 ATR straddle at 08:30, E3 tight straddle at 10:00. Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims), B = the same without claims-only days, C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).
* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2024 was opened only for units that passed every BUILD test. 2025+ was never read.
* A unit passes BUILD only with all five: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and median positive · (c) more per trade than the same bracket on days without a release at that time · (d) t at or above the random-minute bar · (e) beats 99.67 % of 4,000 random same-size day subsets.

## The five units on BUILD
| unit | family · time · days | BUILD trades | variants positive | median variant | central variant | its net | t / bar | lift a trade vs non-event days | beats random day subsets | BUILD |
|---|---|---|---|---|---|---|---|---|---|---|
| E1-A-GC | straddle_tight_0830 · 08:30 · group A | 223 | 96 % of 27 | $10,598 | `offA_pts1p6-r1` | $10,598 | 4.55 / 1.63 | $67 | 100.0 % | **PASS** |
| E1-B-GC | straddle_tight_0830 · 08:30 · group B | 156 | 100 % of 27 | $8,066 | `offA_pts1p6-r1` | $8,066 | 4.18 / 1.63 | $71 | 100.0 % | **PASS** |
| E2-A-GC | straddle_t_0830 · 08:30 · group A | 223 | 63 % of 160 | $3,058 | `offatr0p5_atr3-r0` | $3,088 | 0.17 / 1.63 | $109 | 86.9 % | fail: d, e |
| E2-B-GC | straddle_t_0830 · 08:30 · group B | 156 | 65 % of 160 | $3,302 | `offatr0p25_pts3-r3` | $3,276 | 0.49 / 1.63 | $56 | 78.1 % | fail: d, e |
| E3-C-GC | straddle_tight_1000 · 10:00 · group C | 97 | 100 % of 27 | $8,202 | `offA_pts1p6-r1` | $8,202 | 6.10 / 1.63 | $115 | 100.0 % | **PASS** |

## What each release type did (central variant, BUILD; information only: too few trades per type)
* E1-A-GC `offA_pts1p6-r1`: jobs report (NFP) 26 trades $716 · CPI 26 trades $1,716 · PPI 27 trades $2,552 · retail sales 26 trades $1,416 · GDP 28 trades $1,718 · PCE 27 trades $572 · weekly jobless claims 118 trades $5,198 · no release at that time 339 trades -$6,556.
* E2-A-GC `offatr0p5_atr3-r0`: jobs report (NFP) 26 trades $526 · CPI 26 trades $5,506 · PPI 27 trades -$7,858 · retail sales 26 trades -$9,864 · GDP 28 trades $13,518 · PCE 27 trades -$368 · weekly jobless claims 118 trades $15,768 · no release at that time 342 trades -$32,488.
* E3-C-GC `offA_pts1p6-r1`: ISM manufacturing 27 trades $1,902 · ISM services 27 trades $2,562 · JOLTS 27 trades $2,232 · Michigan sentiment (prelim) 27 trades $2,562 · no release at that time 468 trades -$14,112.

## Fed decision at 14:00 ET (information only; 19 BUILD days, tight straddle armed at 13:59:59)
* 100 % of 27 variants positive, median $2,038; central variant `offA_pts1p6-r3`: 18 trades, $2,038, t 1.44. Too few trades for any test; never opened on 2024.

## 2024 (opened only for the units that passed every BUILD test; whole menu, same day filter, random-minute control run too)
* E1-A-GC (SECOND LOOK on 2024): 100 % of 27 variants positive, median $5,756 -> passes. BUILD central variant `offA_pts1p6-r1` in 2024: $5,496 (96 trades); random-minute control -$4,492. Under 2 ticks + 250 ms: BUILD $10,598 -> $6,358; 2024 $5,496 -> $4,126. Per year: 2021* $902 (27) · 2022 $4,660 (100) · 2023 $5,036 (96) · 2024 $5,496 (96) · combined $16,094 (319). Entry 5 ms after the trigger print: BUILD $1,278, 2024 $596. Admission: every test passes.
* E1-B-GC (SECOND LOOK on 2024): 96 % of 27 variants positive, median $4,088 -> passes. BUILD central variant `offA_pts1p6-r1` in 2024: $2,448 (68 trades); random-minute control -$3,245. Under 2 ticks + 250 ms: BUILD $8,066 -> $4,746; 2024 $2,448 -> $1,128. Per year: 2021* $644 (19) · 2022 $3,106 (71) · 2023 $4,316 (66) · 2024 $2,448 (68) · combined $10,514 (224). Entry 5 ms after the trigger print: BUILD $966, 2024 $88. Admission: every test passes (same variant as E1-A-GC on a subset of its days: recorded on that card, no folder of its own).
* E3-C-GC (first look): 100 % of 27 variants positive, median $3,396 -> passes. BUILD central variant `offA_pts1p6-r1` in 2024: $4,166 (46 trades); random-minute control -$1,152. Under 2 ticks + 250 ms: BUILD $8,202 -> $6,972; 2024 $4,166 -> $3,396. Per year: 2021* $552 (12) · 2022 $2,418 (43) · 2023 $5,232 (42) · 2024 $4,166 (46) · combined $12,368 (143). Entry 5 ms after the trigger print: BUILD $1,852, 2024 -$184 -> FILL-FRAGILE. Admission: every test passes.

## Left on the DONE checklist
* real (paper or small-size) fills on release days: the profit needs a fill on the trigger print; the standard 8-stop menu and the no-target exit for the tight straddle (it ran its own 3 stops x 3 targets); more random-minute seeds; deepen rounds (0 of 4 used); the sealed 2025+ exam.

Files here: `units.csv` (the five units with every test), `heatmap.csv` (every variant of every unit on its event days; 2024 rows only for opened units), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv` (per release type). Scripts and raw results: `out/events/`.
