# event entries on ES — idea record (stage 4, 2026-10-04)

* **Status: OPEN** · deepen rounds used: 0 of 4 · no member saved · 2024 not opened
* Reason written first: a scheduled US data release reprices the market in one burst; the question is only HOW to get in without a tight two-sided bracket (which needs a fill at the stop price and can fill on both sides).
* Two entries, run on EVERY day at the clock time, judged on release days (`engine/cache/events.csv`, never checked against prices): **W** = the same two-sided bracket placed farther away (2.5 / 4 / 5 / 8 points each side, stop 0.5 / 1 / 1.5 x that, target 1:1 / 1:2 / 1:3, armed 1 s before, unfilled orders cancelled after 5 min; 36 variants) · **D** = no bracket: at the release time + X (0.25, 0.5, 1, 2, 5, 15 or 60 s) ONE market order in the direction the price has moved since the last print before the release (no move = no trade); 8 stops x 4 targets = 32 exits; 224 variants.
* Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims) · B = the same without claims-only days · C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).
* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2025+ was never read.
* A unit passes BUILD only with ALL of: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and the median positive · (c) more per trade than the same entry on days without a release at that time · (d) t at or above the unchanged random-entry bar · (e) beats 99.72 % of 4,000 random same-size day subsets · (5 s) the central variant still makes money after its WINNERS held under 5 seconds are taken out (losses kept). The central variant is the one closest to the median, never the best.

## The six units on BUILD
| unit | family · days | trades | variants positive (pass at 60 / 70 / 80 %) | median variant | central variant | its net | t / bar | more per trade than on non-release days | beats random day subsets | net / from trades under 5 s / without fast winners | median hold | BUILD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-A-ES | straddle_wide_0830 · group A | 114 | 53 % of 36 (no / no / no) | $182 | `offD_offx1-r1` (bracket 8 pts each side, stop 8 pts, target 1:1) | $94 | 0.02 / 2.00 | -$16 | 34.3 % | $94 / $2,209 / -$7,034 | 70 s | fail: b, c, d, e, 5s |
| W-B-ES | straddle_wide_0830 · group B | 154 | 81 % of 36 (yes / yes / yes) | $2,195 | `offA_offx1p5-r1` (bracket 2.5 pts each side, stop 3.75 pts, target 1:1) | $2,296 | 0.96 / 2.00 | $34 | 97.5 % | $2,296 / $5,910 / -$8,714 | 3 s | fail: d, e, 5s |
| W-C-ES | straddle_wide_1000 · group C | 96 | 50 % of 36 (no / no / no) | -$282 | `offA_offx1-r1` (bracket 2.5 pts each side, stop 2.5 pts, target 1:1) | $816 | 0.64 / 2.00 | $37 | 99.2 % | $816 / $338 / -$2,814 | 4 s | fail: b, d, e, 5s |
| D-A-ES | event_dir_0830 · group A | 146 | 21 % of 224 (no / no / no) | -$6,444 | `x0p25_pts2p5-r0` | $178 | 0.02 / 2.00 | $14 | 55.7 % | $178 / -$8,266 / $178 | 11 s | fail: b, d, e |
| D-B-ES | event_dir_0830 · group B | 148 | 14 % of 224 (no / no / no) | -$7,074 | `x5_atr1p5-r2` | $470 | 0.05 / 2.00 | $80 | 75.1 % | $470 / -$1,372 / -$5,106 | 712 s | fail: b, d, e, 5s |
| D-C-ES | event_dir_1000 · group C | 93 | 54 % of 224 (no / no / no) | $243 | `x5_pct0p1-r0` | $190 | 0.03 / 2.00 | $16 | 60.4 % | $190 / -$3,680 / $190 | 121 s | fail: b, d, e |

Test (a) passes everywhere. Control of the run (information): the central variant against the same entry with a random direction (D) or at a random minute (W), 2 seeds, same days: W-A-ES $94 vs -$4,356 · W-B-ES $2,296 vs -$4,706 · W-C-ES $816 vs -$2,546 · D-A-ES $178 vs $3,435 · D-B-ES $470 vs -$9,567 · D-C-ES $190 vs -$1,922.

## Per year, central variant (trades), 2021* = Sep-Dec only
* W-A-ES `offD_offx1-r1` (bracket 8 pts each side, stop 8 pts, target 1:1): 2021* $355 (5) · 2022 $2,181 (61) · 2023 -$2,442 (48) · combined $94 (114).
* W-B-ES `offA_offx1p5-r1` (bracket 2.5 pts each side, stop 3.75 pts, target 1:1): 2021* -$1,510 (15) · 2022 $4,300 (72) · 2023 -$493 (67) · combined $2,296 (154).
* W-C-ES `offA_offx1-r1` (bracket 2.5 pts each side, stop 2.5 pts, target 1:1): 2021* $531 (11) · 2022 $216 (43) · 2023 $70 (42) · combined $816 (96).
* D-A-ES `x0p25_pts2p5-r0`: 2021* -$427 (13) · 2022 $5,352 (65) · 2023 -$4,747 (68) · combined $178 (146).
* D-B-ES `x5_atr1p5-r2`: 2021* $602 (15) · 2022 $9,094 (67) · 2023 -$9,226 (66) · combined $470 (148).
* D-C-ES `x5_pct0p1-r0`: 2021* -$2,428 (10) · 2022 $1,107 (42) · 2023 $1,511 (41) · combined $190 (93).

## How late can the market order go in? (D, per wait X; release days only; information, the judged unit is all 7 waits together)
| unit | wait X | trades | exits positive (of 32) | median exit net | median without fast winners | per trade: release days vs days without a release | same entry with a RANDOM direction: median net (2 seeds) | exits that beat it |
|---|---|---|---|---|---|---|---|---|
| D-A-ES | 0.25 s | 146 | 9 % | -$7,009 | -$9,866 | -$48 vs -$75 | -$4,353 | 31 % |
| D-A-ES | 0.5 s | 167 | 25 % | -$5,299 | -$10,200 | -$32 vs -$52 | -$5,134 | 50 % |
| D-A-ES | 1 s | 191 | 9 % | -$8,802 | -$12,788 | -$46 vs -$16 | -$4,258 | 9 % |
| D-A-ES | 2 s | 204 | 34 % | -$5,622 | -$10,727 | -$28 vs -$33 | -$4,857 | 38 % |
| D-A-ES | 5 s | 209 | 44 % | -$405 | -$7,518 | -$2 vs -$12 | -$5,580 | 84 % |
| D-A-ES | 15 s | 215 | 12 % | -$6,548 | -$8,258 | -$30 vs $7 | -$7,957 | 66 % |
| D-A-ES | 60 s | 220 | 9 % | -$7,892 | -$9,222 | -$36 vs -$31 | -$5,768 | 28 % |
| D-B-ES | 0.25 s | 103 | 0 % | -$11,212 | -$13,787 | -$109 vs -$75 | -$2,712 | 16 % |
| D-B-ES | 0.5 s | 113 | 0 % | -$11,502 | -$13,275 | -$102 vs -$52 | -$2,683 | 3 % |
| D-B-ES | 1 s | 131 | 0 % | -$11,799 | -$15,876 | -$90 vs -$16 | -$2,483 | 3 % |
| D-B-ES | 2 s | 140 | 25 % | -$6,685 | -$10,778 | -$48 vs -$33 | -$2,151 | 31 % |
| D-B-ES | 5 s | 148 | 62 % | $1,370 | -$4,498 | $9 vs -$12 | -$3,417 | 91 % |
| D-B-ES | 15 s | 151 | 0 % | -$6,660 | -$8,267 | -$44 vs $7 | -$5,588 | 59 % |
| D-B-ES | 60 s | 156 | 9 % | -$5,774 | -$6,689 | -$37 vs -$31 | -$4,352 | 31 % |
| D-C-ES | 0.25 s | 87 | 66 % | $1,333 | $452 | $15 vs -$27 | $1,627 | 66 % |
| D-C-ES | 0.5 s | 91 | 47 % | -$89 | -$1,687 | -$1 vs -$24 | $1,155 | 50 % |
| D-C-ES | 1 s | 93 | 44 % | -$166 | -$316 | -$2 vs -$37 | $156 | 47 % |
| D-C-ES | 2 s | 91 | 78 % | $4,630 | $4,630 | $51 vs -$31 | $2,567 | 66 % |
| D-C-ES | 5 s | 93 | 53 % | $66 | -$434 | $1 vs -$7 | $797 | 53 % |
| D-C-ES | 15 s | 95 | 56 % | $339 | $339 | $4 vs -$30 | -$364 | 84 % |
| D-C-ES | 60 s | 95 | 34 % | -$1,842 | -$1,918 | -$19 vs -$6 | -$1,271 | 53 % |

## What each release type did (central variant, BUILD; information only: too few trades per type)
* W-A-ES `offD_offx1-r1`: jobs report 25 trades $800 · CPI 26 trades $3,608 · PPI 19 trades $212 · retail sales 11 trades -$4,594 · GDP 12 trades -$123 · PCE 16 trades -$2,602 · weekly claims 37 trades -$786 · no release at that time 15 trades $252.
* W-B-ES `offA_offx1p5-r1`: jobs report 26 trades $2,058 · CPI 27 trades $2,630 · PPI 26 trades $896 · retail sales 26 trades -$266 · GDP 27 trades -$1,246 · PCE 26 trades -$1,042 · weekly claims 111 trades -$4,819 · no release at that time 212 trades -$4,110.
* W-C-ES `offA_offx1-r1`: ISM manufacturing 27 trades -$433 · ISM services 27 trades $117 · JOLTS 26 trades -$279 · Michigan sentiment 26 trades $1,034 · no release at that time 447 trades -$12,588.
* D-A-ES `x0p25_pts2p5-r0`: jobs report 16 trades -$776 · CPI 19 trades -$326 · PPI 18 trades -$897 · retail sales 20 trades -$2,830 · GDP 18 trades $2,140 · PCE 13 trades -$1,840 · weekly claims 77 trades $6,930 · no release at that time 146 trades -$1,796.
* D-B-ES `x5_atr1p5-r2`: jobs report 25 trades -$3,012 · CPI 27 trades $8,754 · PPI 26 trades -$2,666 · retail sales 26 trades -$4,429 · GDP 24 trades -$1,184 · PCE 24 trades $1,016 · weekly claims 106 trades -$574 · no release at that time 245 trades -$18,918.
* D-C-ES `x5_pct0p1-r0`: ISM manufacturing 27 trades -$1,896 · ISM services 26 trades -$5,004 · JOLTS 25 trades $1,850 · Michigan sentiment 25 trades $4,038 · no release at that time 423 trades -$6,067.

## 2024
* No unit passed every BUILD test: 2024 was NOT opened for this market (no 2024 run exists for these families; `out/entries/pick_reads.csv` holds no row). No card, no fill probe, no late-cancel probe.

## Left on the DONE checklist
* W ran its own 3 stops x 3 targets (not the 8-stop menu, no no-target exit); only 2 control seeds; bar size does not apply (clock-time entries); deepen rounds (0 of 4 used); the table-level re-judge of EDGE_SPEC "ADMISSION v2" (written 11:15 ET, after this stage was briefed); verdict.

Files here: `units.csv` (the six units with every test), `heatmap.csv` (every variant of every unit on its release days, with the 5-second columns), `per_x.csv` (D per wait), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv`. Scripts and raw results: `out/entries/`.
