# event entries on GC — idea record (stage 4, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4 · no member saved · 2024 not opened
* Reason written first: a scheduled US data release reprices the market in one burst; the question is only HOW to get in without a tight two-sided bracket (which needs a fill at the stop price and can fill on both sides).
* Two entries, run on EVERY day at the clock time, judged on release days (`engine/cache/events.csv`, never checked against prices): **W** = the same two-sided bracket placed farther away (2 / 3 / 4 / 6 points each side, stop 0.5 / 1 / 1.5 x that, target 1:1 / 1:2 / 1:3, armed 1 s before, unfilled orders cancelled after 5 min; 36 variants) · **D** = no bracket: at the release time + X (0.25, 0.5, 1, 2, 5, 15 or 60 s) ONE market order in the direction the price has moved since the last print before the release (no move = no trade); 8 stops x 4 targets = 32 exits; 224 variants.
* Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims) · B = the same without claims-only days · C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).
* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2025+ was never read.
* A unit passes BUILD only with ALL of: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and the median positive · (c) more per trade than the same entry on days without a release at that time · (d) t at or above the unchanged random-entry bar · (e) beats 99.72 % of 4,000 random same-size day subsets · (5 s) the central variant still makes money after its WINNERS held under 5 seconds are taken out (losses kept). The central variant is the one closest to the median, never the best.

## The six units on BUILD
| unit | family · days | trades | variants positive (pass at 60 / 70 / 80 %) | median variant | central variant | its net | t / bar | more per trade than on non-release days | beats random day subsets | net / from trades under 5 s / without fast winners | median hold | BUILD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-A-GC | straddle_wide_0830 · group A | 175 | 61 % of 36 (yes / no / no) | $715 | `offB_offx1p5-r3` (bracket 3 pts each side, stop 4.5 pts, target 1:3) | $790 | 0.08 / 1.63 | $17 | 55.7 % | $790 / -$1,968 / -$1,902 | 1030 s | fail: d, e, 5s |
| W-B-GC | straddle_wide_0830 · group B | 132 | 53 % of 36 (no / no / no) | $307 | `offB_offx0p5-r1` (bracket 3 pts each side, stop 1.5 pts, target 1:1) | $512 | 0.27 / 1.63 | $13 | 86.3 % | $512 / $2,342 / -$7,664 | 1 s | fail: b, d, e, 5s |
| W-C-GC | straddle_wide_1000 · group C | 58 | 67 % of 36 (yes / no / no) | $1,933 | `offC_offx1-r2` (bracket 4 pts each side, stop 4 pts, target 1:2) | $1,978 | 0.45 / 1.63 | $51 | 65.6 % | $1,978 / $0 / $1,978 | 1249 s | fail: d, e |
| D-A-GC | event_dir_0830 · group A | 207 | 8 % of 224 (no / no / no) | -$7,667 | `x2_pct0p1-r1` | $102 | 0.04 / 1.63 | $4 | 60.2 % | $102 / -$2 / -$7,580 | 8 s | fail: b, d, e, 5s |
| D-B-GC | event_dir_0830 · group B | 155 | 5 % of 224 (no / no / no) | -$7,046 | `x60_pct0p1-r0` | $20 | 0.00 / 1.63 | $21 | 48.5 % | $20 / -$582 / $20 | 211 s | fail: b, d, e |
| D-C-GC | event_dir_1000 · group C | 96 | 78 % of 224 (yes / yes / no) | $3,103 | `x2_pts7-r2` | $3,096 | 0.38 / 1.63 | $64 | 77.6 % | $3,096 / $0 / $3,096 | 9057 s | fail: d, e |

Test (a) passes everywhere. Control of the run (information): the central variant against the same entry with a random direction (D) or at a random minute (W), 2 seeds, same days: W-A-GC $790 vs -$379 · W-B-GC $512 vs -$1,679 · W-C-GC $1,978 vs $987 · D-A-GC $102 vs -$5,338 · D-B-GC $20 vs -$3,545 · D-C-GC $3,096 vs $12,376.

## Per year, central variant (trades), 2021* = Sep-Dec only
* W-A-GC `offB_offx1p5-r3` (bracket 3 pts each side, stop 4.5 pts, target 1:3): 2021* $666 (16) · 2022 $3,414 (74) · 2023 -$3,290 (85) · combined $790 (175).
* W-B-GC `offB_offx0p5-r1` (bracket 3 pts each side, stop 1.5 pts, target 1:1): 2021* $28 (13) · 2022 -$872 (58) · 2023 $1,356 (61) · combined $512 (132).
* W-C-GC `offC_offx1-r2` (bracket 4 pts each side, stop 4 pts, target 1:2): 2021* -$1,242 (3) · 2022 $2,818 (23) · 2023 $402 (32) · combined $1,978 (58).
* D-A-GC `x2_pct0p1-r1`: 2021* $726 (21) · 2022 -$1,402 (93) · 2023 $778 (93) · combined $102 (207).
* D-B-GC `x60_pct0p1-r0`: 2021* $74 (19) · 2022 -$8,200 (70) · 2023 $8,146 (66) · combined $20 (155).
* D-C-GC `x2_pts7-r2`: 2021* -$3,928 (12) · 2022 $2,118 (43) · 2023 $4,906 (41) · combined $3,096 (96).

## How late can the market order go in? (D, per wait X; release days only; information, the judged unit is all 7 waits together)
| unit | wait X | trades | exits positive (of 32) | median exit net | median without fast winners | per trade: release days vs days without a release | same entry with a RANDOM direction: median net (2 seeds) | exits that beat it |
|---|---|---|---|---|---|---|---|---|
| D-A-GC | 0.25 s | 133 | 0 % | -$11,812 | -$15,620 | -$89 vs $8 | -$3,297 | 0 % |
| D-A-GC | 0.5 s | 151 | 0 % | -$8,374 | -$13,126 | -$55 vs $43 | -$5,404 | 12 % |
| D-A-GC | 1 s | 178 | 3 % | -$16,657 | -$19,238 | -$94 vs $2 | -$11,134 | 31 % |
| D-A-GC | 2 s | 207 | 12 % | -$8,198 | -$9,919 | -$40 vs -$10 | -$10,578 | 62 % |
| D-A-GC | 5 s | 218 | 0 % | -$11,007 | -$11,367 | -$50 vs -$35 | -$8,774 | 28 % |
| D-A-GC | 15 s | 222 | 6 % | -$4,753 | -$4,753 | -$21 vs -$36 | -$5,660 | 53 % |
| D-A-GC | 60 s | 219 | 38 % | -$1,366 | -$2,198 | -$6 vs -$33 | -$1,481 | 50 % |
| D-B-GC | 0.25 s | 90 | 0 % | -$5,265 | -$9,703 | -$58 vs $8 | -$4,220 | 28 % |
| D-B-GC | 0.5 s | 108 | 3 % | -$4,227 | -$9,705 | -$39 vs $43 | -$5,262 | 56 % |
| D-B-GC | 1 s | 126 | 12 % | -$5,789 | -$10,811 | -$46 vs $2 | -$10,989 | 81 % |
| D-B-GC | 2 s | 147 | 19 % | -$5,933 | -$6,741 | -$40 vs -$10 | -$9,153 | 81 % |
| D-B-GC | 5 s | 153 | 0 % | -$14,322 | -$14,322 | -$94 vs -$35 | -$9,757 | 19 % |
| D-B-GC | 15 s | 155 | 0 % | -$7,975 | -$7,975 | -$51 vs -$36 | -$6,982 | 41 % |
| D-B-GC | 60 s | 155 | 3 % | -$6,315 | -$6,315 | -$41 vs -$33 | -$2,670 | 19 % |
| D-C-GC | 0.25 s | 89 | 59 % | $764 | $383 | $9 vs $37 | $3,214 | 22 % |
| D-C-GC | 0.5 s | 91 | 78 % | $3,541 | $3,480 | $39 vs -$41 | $7,436 | 25 % |
| D-C-GC | 1 s | 93 | 84 % | $3,058 | $2,620 | $33 vs -$45 | $6,003 | 47 % |
| D-C-GC | 2 s | 96 | 78 % | $1,226 | $1,226 | $13 vs -$36 | $5,611 | 16 % |
| D-C-GC | 5 s | 96 | 50 % | $101 | -$195 | $1 vs -$20 | $5,841 | 6 % |
| D-C-GC | 15 s | 96 | 94 % | $7,241 | $7,241 | $75 vs -$32 | $9,151 | 47 % |
| D-C-GC | 60 s | 95 | 100 % | $9,190 | $9,190 | $97 vs -$25 | $6,370 | 69 % |

## What each release type did (central variant, BUILD; information only: too few trades per type)
* W-A-GC `offB_offx1p5-r3`: jobs report 25 trades $3,490 · CPI 25 trades $12,920 · PPI 22 trades -$10,208 · retail sales 23 trades -$10,282 · GDP 23 trades $4,238 · PCE 18 trades -$3,342 · weekly claims 84 trades $5,234 · no release at that time 66 trades -$854.
* W-B-GC `offB_offx0p5-r1`: jobs report 25 trades $1,410 · CPI 25 trades $850 · PPI 22 trades -$608 · retail sales 23 trades -$1,482 · GDP 23 trades $868 · PCE 18 trades -$562 · weekly claims 84 trades -$236 · no release at that time 66 trades -$634.
* W-C-GC `offC_offx1-r2`: ISM manufacturing 18 trades -$822 · ISM services 17 trades $1,432 · JOLTS 20 trades $1,400 · Michigan sentiment 13 trades -$2,962 · no release at that time 48 trades -$802.
* D-A-GC `x2_pct0p1-r1`: jobs report 25 trades $570 · CPI 26 trades $466 · PPI 25 trades -$410 · retail sales 26 trades -$264 · GDP 27 trades -$128 · PCE 22 trades $122 · weekly claims 109 trades -$666 · no release at that time 274 trades -$1,046.
* D-B-GC `x60_pct0p1-r0`: jobs report 26 trades $2,466 · CPI 26 trades -$914 · PPI 27 trades -$5,408 · retail sales 26 trades $1,106 · GDP 27 trades $4,992 · PCE 27 trades -$3,048 · weekly claims 115 trades $14,820 · no release at that time 326 trades -$6,684.
* D-C-GC `x2_pts7-r2`: ISM manufacturing 27 trades $1,212 · ISM services 27 trades -$68 · JOLTS 27 trades -$1,468 · Michigan sentiment 26 trades $2,386 · no release at that time 397 trades -$12,758.

## 2024
* No unit passed every BUILD test: 2024 was NOT opened for this market (no 2024 run exists for these families; `out/entries/pick_reads.csv` holds no row). No card, no fill probe, no late-cancel probe.

## Left on the DONE checklist
* W ran its own 3 stops x 3 targets (not the 8-stop menu, no no-target exit); only 2 control seeds; bar size does not apply (clock-time entries); deepen rounds (0 of 4 used); the table-level re-judge of EDGE_SPEC "ADMISSION v2" (written 11:15 ET, after this stage was briefed); verdict.

Files here: `units.csv` (the six units with every test), `heatmap.csv` (every variant of every unit on its release days, with the 5-second columns), `per_x.csv` (D per wait), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv`. Scripts and raw results: `out/entries/`.
