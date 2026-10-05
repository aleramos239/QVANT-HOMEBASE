# event entries on NQ — idea record (stage 4, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4 · no member saved · 2024 not opened
* Reason written first: a scheduled US data release reprices the market in one burst; the question is only HOW to get in without a tight two-sided bracket (which needs a fill at the stop price and can fill on both sides).
* Two entries, run on EVERY day at the clock time, judged on release days (`engine/cache/events.csv`, never checked against prices): **W** = the same two-sided bracket placed farther away (10 / 15 / 20 / 30 points each side, stop 0.5 / 1 / 1.5 x that, target 1:1 / 1:2 / 1:3, armed 1 s before, unfilled orders cancelled after 5 min; 36 variants) · **D** = no bracket: at the release time + X (0.25, 0.5, 1, 2, 5, 15 or 60 s) ONE market order in the direction the price has moved since the last print before the release (no move = no trade); 8 stops x 4 targets = 32 exits; 224 variants.
* Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims) · B = the same without claims-only days · C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).
* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2025+ was never read.
* A unit passes BUILD only with ALL of: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and the median positive · (c) more per trade than the same entry on days without a release at that time · (d) t at or above the unchanged random-entry bar · (e) beats 99.72 % of 4,000 random same-size day subsets · (5 s) the central variant still makes money after its WINNERS held under 5 seconds are taken out (losses kept). The central variant is the one closest to the median, never the best.

## The six units on BUILD
| unit | family · days | trades | variants positive (pass at 60 / 70 / 80 %) | median variant | central variant | its net | t / bar | more per trade than on non-release days | beats random day subsets | net / from trades under 5 s / without fast winners | median hold | BUILD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-A-NQ | straddle_wide_0830 · group A | 132 | 100 % of 36 (yes / yes / yes) | $8,517 | `offD_offx0p5-r3` (bracket 30 pts each side, stop 15 pts, target 1:3) | $8,937 | 1.33 / 2.56 | $124 | 76.8 % | $8,937 / -$2,922 / $1,769 | 19 s | fail: d, e |
| W-B-NQ | straddle_wide_0830 · group B | 150 | 100 % of 36 (yes / yes / yes) | $9,548 | `offB_offx0p5-r2` (bracket 15 pts each side, stop 7.5 pts, target 1:2) | $9,535 | 3.23 / 2.56 | $50 | 99.4 % | $9,535 / $7,687 / -$7,041 | 1 s | fail: e, 5s |
| W-C-NQ | straddle_wide_1000 · group C | 95 | 67 % of 36 (yes / no / no) | $1,338 | `offA_offx0p5-r2` (bracket 10 pts each side, stop 5 pts, target 1:2) | $1,480 | 0.95 / 2.56 | $24 | 93.2 % | $1,480 / $804 / -$4,988 | 0 s | fail: d, e, 5s |
| D-A-NQ | event_dir_0830 · group A | 220 | 22 % of 224 (no / no / no) | -$7,454 | `x5_pts10-r1` | $60 | 0.02 / 2.56 | $5 | 61.4 % | $60 / $4,791 / -$15,424 | 3 s | fail: b, d, e, 5s |
| D-B-NQ | event_dir_0830 · group B | 108 | 19 % of 224 (no / no / no) | -$6,353 | `x0p25_atr1p5-r2` | $138 | 0.01 / 2.56 | $105 | 75.7 % | $138 / -$6,145 / -$2,930 | 1352 s | fail: b, d, e, 5s |
| D-C-NQ | event_dir_1000 · group C | 90 | 46 % of 224 (no / no / no) | -$366 | `x0p25_pts30-r0` | $90 | 0.01 / 2.56 | -$128 | 26.3 % | $90 / -$2,441 / $90 | 547 s | fail: b, c, d, e |

Test (a) passes everywhere. Control of the run (information): the central variant against the same entry with a random direction (D) or at a random minute (W), 2 seeds, same days: W-A-NQ $8,937 vs -$1,071 · W-B-NQ $9,535 vs -$1,196 · W-C-NQ $1,480 vs -$1,150 · D-A-NQ $60 vs -$3,272 · D-B-NQ $138 vs $1,553 · D-C-NQ $90 vs $10,278.

## Per year, central variant (trades), 2021* = Sep-Dec only
* W-A-NQ `offD_offx0p5-r3` (bracket 30 pts each side, stop 15 pts, target 1:3): 2021* $2,966 (6) · 2022 $4,900 (65) · 2023 $1,071 (61) · combined $8,937 (132).
* W-B-NQ `offB_offx0p5-r2` (bracket 15 pts each side, stop 7.5 pts, target 1:2): 2021* -$141 (14) · 2022 $7,541 (71) · 2023 $2,135 (65) · combined $9,535 (150).
* W-C-NQ `offA_offx0p5-r2` (bracket 10 pts each side, stop 5 pts, target 1:2): 2021* $626 (11) · 2022 $607 (42) · 2023 $247 (42) · combined $1,480 (95).
* D-A-NQ `x5_pts10-r1`: 2021* -$599 (26) · 2022 $1,452 (97) · 2023 -$793 (97) · combined $60 (220).
* D-B-NQ `x0p25_atr1p5-r2`: 2021* -$4,822 (13) · 2022 $7,119 (54) · 2023 -$2,159 (41) · combined $138 (108).
* D-C-NQ `x0p25_pts30-r0`: 2021* -$3,765 (10) · 2022 $2,504 (39) · 2023 $1,351 (41) · combined $90 (90).

## How late can the market order go in? (D, per wait X; release days only; information, the judged unit is all 7 waits together)
| unit | wait X | trades | exits positive (of 32) | median exit net | median without fast winners | per trade: release days vs days without a release | same entry with a RANDOM direction: median net (2 seeds) | exits that beat it |
|---|---|---|---|---|---|---|---|---|
| D-A-NQ | 0.25 s | 154 | 31 % | -$4,456 | -$9,058 | -$29 vs -$24 | $6,060 | 3 % |
| D-A-NQ | 0.5 s | 187 | 19 % | -$16,513 | -$23,196 | -$88 vs $3 | $6,216 | 0 % |
| D-A-NQ | 1 s | 206 | 3 % | -$19,512 | -$24,742 | -$95 vs $31 | $2,352 | 0 % |
| D-A-NQ | 2 s | 216 | 3 % | -$13,099 | -$23,188 | -$61 vs $3 | -$29 | 6 % |
| D-A-NQ | 5 s | 220 | 53 % | $502 | -$10,531 | $2 vs -$5 | $1,939 | 34 % |
| D-A-NQ | 15 s | 223 | 25 % | -$3,367 | -$7,510 | -$15 vs $105 | $1,358 | 25 % |
| D-A-NQ | 60 s | 225 | 19 % | -$7,690 | -$8,206 | -$34 vs -$9 | $5,982 | 3 % |
| D-B-NQ | 0.25 s | 108 | 31 % | -$2,742 | -$6,062 | -$25 vs -$24 | $3,729 | 12 % |
| D-B-NQ | 0.5 s | 131 | 0 % | -$15,742 | -$20,886 | -$120 vs $3 | $3,824 | 0 % |
| D-B-NQ | 1 s | 144 | 3 % | -$13,901 | -$22,232 | -$97 vs $31 | $4,023 | 0 % |
| D-B-NQ | 2 s | 153 | 16 % | -$5,582 | -$16,536 | -$36 vs $3 | $1,760 | 19 % |
| D-B-NQ | 5 s | 154 | 41 % | -$628 | -$12,150 | -$4 vs -$5 | $1,526 | 31 % |
| D-B-NQ | 15 s | 156 | 25 % | -$3,874 | -$8,263 | -$25 vs $105 | $2,860 | 31 % |
| D-B-NQ | 60 s | 157 | 16 % | -$7,193 | -$7,861 | -$46 vs -$9 | $3,906 | 9 % |
| D-C-NQ | 0.25 s | 90 | 31 % | -$1,660 | -$4,004 | -$18 vs $10 | $3,416 | 9 % |
| D-C-NQ | 0.5 s | 92 | 31 % | -$1,006 | -$3,890 | -$11 vs -$3 | $3,237 | 16 % |
| D-C-NQ | 1 s | 95 | 9 % | -$7,342 | -$7,614 | -$77 vs -$32 | $362 | 9 % |
| D-C-NQ | 2 s | 94 | 81 % | $5,942 | $5,942 | $63 vs -$17 | $299 | 84 % |
| D-C-NQ | 5 s | 94 | 66 % | $2,096 | $1,574 | $22 vs -$17 | $144 | 66 % |
| D-C-NQ | 15 s | 95 | 84 % | $3,830 | $3,705 | $40 vs -$30 | $111 | 84 % |
| D-C-NQ | 60 s | 94 | 19 % | -$2,374 | -$3,134 | -$25 vs -$20 | -$1,086 | 44 % |

## What each release type did (central variant, BUILD; information only: too few trades per type)
* W-A-NQ `offD_offx0p5-r3`: jobs report 23 trades $8,313 · CPI 27 trades $5,887 · PPI 19 trades $1,279 · retail sales 15 trades -$4,695 · GDP 15 trades -$2,275 · PCE 18 trades -$3,347 · weekly claims 50 trades -$45 · no release at that time 19 trades -$1,076.
* W-B-NQ `offB_offx0p5-r2`: jobs report 25 trades $2,320 · CPI 27 trades $3,187 · PPI 26 trades $2,506 · retail sales 26 trades -$149 · GDP 25 trades -$385 · PCE 25 trades $2,320 · weekly claims 101 trades -$1,469 · no release at that time 105 trades $1,455.
* W-C-NQ `offA_offx0p5-r2`: ISM manufacturing 26 trades $696 · ISM services 26 trades -$114 · JOLTS 27 trades $302 · Michigan sentiment 27 trades $1,497 · no release at that time 461 trades -$4,069.
* D-A-NQ `x5_pts10-r1`: jobs report 24 trades $1,679 · CPI 27 trades $407 · PPI 26 trades $971 · retail sales 27 trades -$458 · GDP 28 trades -$1,902 · PCE 26 trades $571 · weekly claims 116 trades -$1,779 · no release at that time 311 trades -$1,509.
* D-B-NQ `x0p25_atr1p5-r2`: jobs report 12 trades -$2,408 · CPI 16 trades $5,171 · PPI 21 trades $2,746 · retail sales 24 trades -$3,186 · GDP 21 trades -$2,709 · PCE 17 trades $357 · weekly claims 86 trades -$11,369 · no release at that time 240 trades -$24,865.
* D-C-NQ `x0p25_pts30-r0`: ISM manufacturing 22 trades -$9,043 · ISM services 25 trades -$4,965 · JOLTS 25 trades -$490 · Michigan sentiment 27 trades $9,107 · no release at that time 454 trades $58,519.

## 2024
* No unit passed every BUILD test: 2024 was NOT opened for this market (no 2024 run exists for these families; `out/entries/pick_reads.csv` holds no row). No card, no fill probe, no late-cancel probe.

## Left on the DONE checklist
* W ran its own 3 stops x 3 targets (not the 8-stop menu, no no-target exit); only 2 control seeds; bar size does not apply (clock-time entries); deepen rounds (0 of 4 used); the table-level re-judge of EDGE_SPEC "ADMISSION v2" (written 11:15 ET, after this stage was briefed); verdict.

Files here: `units.csv` (the six units with every test), `heatmap.csv` (every variant of every unit on its release days, with the 5-second columns), `per_x.csv` (D per wait), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv`. Scripts and raw results: `out/entries/`.
