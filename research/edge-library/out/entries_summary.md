# Event entries — summary (stage 4, 2026-10-04)
Plain words; dollars are 1 contract after costs. BUILD = 22 Sep 2021 to end 2023. **2024 was NOT opened for any unit; 2025+ was never read.** No eval or payout odds were computed (library first).
**Result: none of the 18 units passes BUILD. No member is saved.** The closest is the wide bracket on NQ on tier-1 08:30 days, and it lives on trades shorter than 5 seconds.
## 1. What was tested
* Same reason as the event straddles (a scheduled release reprices the market in one burst); only the way in changes. Both entries ran on EVERY day; release days come from the official calendar (`engine/cache/events.csv`), the other days are the control.
* **W, wide bracket**: buy stop above and sell stop below, placed 1 s before, farther away than the tight straddle (NQ 10 / 15 / 20 / 30 points, ES 2.5 / 4 / 5 / 8, GC 2 / 3 / 4 / 6), stop 0.5 / 1 / 1.5 x that distance, target 1:1 / 1:2 / 1:3, unfilled orders cancelled after 5 minutes. 36 variants.
* **D, one market order**: no bracket. At the release time + X (0.25, 0.5, 1, 2, 5, 15, 60 s) buy if price is above the last print before the release, sell if below, nothing if unchanged. 8 stops x 4 targets. 224 variants.
* Days: A = every 08:30 release day · B = tier-1 only (no claims-only days) · C = every 10:00 release day. Markets NQ, ES, GC. 2 entries x 3 day groups x 3 markets = 18 units.
* A unit passes only with ALL of: (a) 100 trades reachable · (b) 60 % of variants positive and median positive · (c) more per trade than on days without a release · (d) t at or above the random-entry bar (NQ 2.56, ES 2.00, GC 1.63) · (e) beats 99.72 % of 4,000 random day subsets · (5 s) the central variant still earns after its winners held under 5 seconds are removed. The central variant is the one nearest the median, never the best.
## 2. The 18 units on BUILD (test (a) passes everywhere)
| unit | trades | variants positive (60 / 70 / 80 %) | t vs bar | more per trade than non-release days | beats random day subsets | net / from trades under 5 s / without fast winners | median hold | result |
|---|---|---|---|---|---|---|---|---|
| W-A-NQ | 132 | 100 % of 36 (yes/yes/yes) | 1.33 vs 2.56 | $124 | 76.8 % | $8,937 / -$2,922 / $1,769 | 19 s | fail (d, e) |
| W-A-ES | 114 | 53 % of 36 (no/no/no) | 0.02 vs 2.00 | -$16 | 34.3 % | $94 / $2,209 / -$7,034 | 70 s | fail (b, c, d, e, 5s) |
| W-A-GC | 175 | 61 % of 36 (yes/no/no) | 0.08 vs 1.63 | $17 | 55.7 % | $790 / -$1,968 / -$1,902 | 1030 s | fail (d, e, 5s) |
| W-B-NQ | 150 | 100 % of 36 (yes/yes/yes) | 3.23 vs 2.56 | $50 | 99.4 % | $9,535 / $7,687 / -$7,041 | 1 s | fail (e, 5s) |
| W-B-ES | 154 | 81 % of 36 (yes/yes/yes) | 0.96 vs 2.00 | $34 | 97.5 % | $2,296 / $5,910 / -$8,714 | 3 s | fail (d, e, 5s) |
| W-B-GC | 132 | 53 % of 36 (no/no/no) | 0.27 vs 1.63 | $13 | 86.3 % | $512 / $2,342 / -$7,664 | 1 s | fail (b, d, e, 5s) |
| W-C-NQ | 95 | 67 % of 36 (yes/no/no) | 0.95 vs 2.56 | $24 | 93.2 % | $1,480 / $804 / -$4,988 | 0 s | fail (d, e, 5s) |
| W-C-ES | 96 | 50 % of 36 (no/no/no) | 0.64 vs 2.00 | $37 | 99.2 % | $816 / $338 / -$2,814 | 4 s | fail (b, d, e, 5s) |
| W-C-GC | 58 | 67 % of 36 (yes/no/no) | 0.45 vs 1.63 | $51 | 65.6 % | $1,978 / $0 / $1,978 | 1249 s | fail (d, e) |
| D-A-NQ | 220 | 22 % of 224 (no/no/no) | 0.02 vs 2.56 | $5 | 61.4 % | $60 / $4,791 / -$15,424 | 3 s | fail (b, d, e, 5s) |
| D-A-ES | 146 | 21 % of 224 (no/no/no) | 0.02 vs 2.00 | $14 | 55.7 % | $178 / -$8,266 / $178 | 11 s | fail (b, d, e) |
| D-A-GC | 207 | 8 % of 224 (no/no/no) | 0.04 vs 1.63 | $4 | 60.2 % | $102 / -$2 / -$7,580 | 8 s | fail (b, d, e, 5s) |
| D-B-NQ | 108 | 19 % of 224 (no/no/no) | 0.01 vs 2.56 | $105 | 75.7 % | $138 / -$6,145 / -$2,930 | 1352 s | fail (b, d, e, 5s) |
| D-B-ES | 148 | 14 % of 224 (no/no/no) | 0.05 vs 2.00 | $80 | 75.1 % | $470 / -$1,372 / -$5,106 | 712 s | fail (b, d, e, 5s) |
| D-B-GC | 155 | 5 % of 224 (no/no/no) | 0.00 vs 1.63 | $21 | 48.5 % | $20 / -$582 / $20 | 211 s | fail (b, d, e) |
| D-C-NQ | 90 | 46 % of 224 (no/no/no) | 0.01 vs 2.56 | -$128 | 26.3 % | $90 / -$2,441 / $90 | 547 s | fail (b, c, d, e) |
| D-C-ES | 93 | 54 % of 224 (no/no/no) | 0.03 vs 2.00 | $16 | 60.4 % | $190 / -$3,680 / $190 | 121 s | fail (b, d, e) |
| D-C-GC | 96 | 78 % of 224 (yes/yes/no) | 0.38 vs 1.63 | $64 | 77.6 % | $3,096 / $0 / $3,096 | 9057 s | fail (d, e) |
* W works on NQ at 08:30 as a table (every one of the 36 variants is positive in both day groups) but not strongly enough on its central variant: on all release days t is 1.33; on tier-1 days t is 3.23 but it beats only 99.4 % of random day subsets (needs 99.72 %) and 73 % of its gross profit is winners closed inside 5 seconds.
* D does not work at 08:30 in any market: 5 to 22 % of variants positive, median variant -$6,400 to -$7,700. Chasing the first move with a market order buys the top of the burst.
## 3. How late can the market order go in and still have an edge? (D per wait X; information only, the judged unit is all waits together)
Each box: share of the 32 exits positive · median exit net · the same median without winners held under 5 s.
| wait X | NQ 08:30 (A) | GC 08:30 (A) | NQ 10:00 (C) | ES 10:00 (C) | GC 10:00 (C) |
|---|---|---|---|---|---|
| 0.25 s | 31 % · -$4,456 · -$9,058 | 0 % · -$11,812 · -$15,620 | 31 % · -$1,660 · -$4,004 | 66 % · $1,333 · $452 | 59 % · $764 · $383 |
| 0.5 s | 19 % · -$16,513 · -$23,196 | 0 % · -$8,374 · -$13,126 | 31 % · -$1,006 · -$3,890 | 47 % · -$89 · -$1,687 | 78 % · $3,541 · $3,480 |
| 1 s | 3 % · -$19,512 · -$24,742 | 3 % · -$16,657 · -$19,238 | 9 % · -$7,342 · -$7,614 | 44 % · -$166 · -$316 | 84 % · $3,058 · $2,620 |
| 2 s | 3 % · -$13,099 · -$23,188 | 12 % · -$8,198 · -$9,919 | 81 % · $5,942 · $5,942 | 78 % · $4,630 · $4,630 | 78 % · $1,226 · $1,226 |
| 5 s | 53 % · $502 · -$10,531 | 0 % · -$11,007 · -$11,367 | 66 % · $2,096 · $1,574 | 53 % · $66 · -$434 | 50 % · $101 · -$195 |
| 15 s | 25 % · -$3,367 · -$7,510 | 6 % · -$4,753 · -$4,753 | 84 % · $3,830 · $3,705 | 56 % · $339 · $339 | 94 % · $7,241 · $7,241 |
| 60 s | 19 % · -$7,690 · -$8,206 | 38 % · -$1,366 · -$2,198 | 19 % · -$2,374 · -$3,134 | 34 % · -$1,842 · -$1,918 | 100 % · $9,190 · $9,190 |
* 08:30: no wait works, in any market. NQ is worst at 0.5 to 2 s (3 to 19 % of exits positive, -$60 to -$95 a trade): the order goes in at the top of the burst. Only 5 s is near flat (53 %, median $502) and that is fast winners: without them -$10,531. Gold has no wait above 38 %. On NQ the same entry with a random direction did better at every wait; on gold both lose.
* 10:00: NQ at 2 / 5 / 15 s is positive in 81 / 66 / 84 % of exits and beats the random direction ($299 / $144 / $111 median); 1 s and 60 s lose. Gold at 15 s and 60 s is 94 / 100 % positive, but the random direction earned about the same ($9,151 / $6,370 median, 2 seeds): it is the day, not the direction. About 95 trades per box, 63 boxes looked at, no luck test is written for them: a lead, not a finding.
## 4. 2024, members, fill realism
* No unit passed BUILD, so 2024 stayed closed (`out/entries/pick_reads.csv` has a header and no row; no 2024 run of these families exists). **Admitted members: none.** No card, so the 1 / 5 / 25 ms fill probe and the 100 ms late-cancel probe were not run (the section asks for them on admitted cards).
## 5. The four closest misses (BUILD only)
1. **W-B-NQ** `offB_offx0p5-r2` (bracket 15 points each side, stop 7.5, target 1:2; tier-1 08:30 days): 150 trades, $9,535, t 3.23 (bar 2.56), all 36 variants positive, +$50 a trade over non-release days. Per year 2021* -$141 (14) · 2022 $7,541 (71) · 2023 $2,135 (65). Fails (e) 99.35 % vs 99.72 % and the 5-second gate: $16,576 of its winners close inside 5 s (73 % of gross profit); without them -$7,041. Median hold 1 s. Would be a SECOND LOOK on 2024.
2. **W-A-NQ** `offD_offx0p5-r3` (bracket 30 points, stop 15, target 1:3; every 08:30 release day): 132 trades, $8,937, all 36 variants positive, passes the 5-second gate ($1,769 without fast winners, median hold 19 s). Fails (d) t 1.33 and (e) 76.8 %. 2021* $2,966 (6) · 2022 $4,900 (65) · 2023 $1,071 (61); the jobs report and CPI carry it ($14,200), retail sales, GDP and PCE lose.
3. **D-C-GC** (gold, market order after a 10:00 release): 78 % of 224 variants positive, median $3,103; central `x2_pts7-r2` 96 trades, $3,096, t 0.38, 77.6 %; no trade under 5 s. The random-direction control earned more ($12,376) on the same days.
4. **W-C-GC** `offC_offx1-r2` (bracket 4 points, stop 4, target 1:2; 10:00 days): 58 trades, $1,978, 67 % of variants positive, t 0.45, 65.6 %; no trade under 5 s. (Next: W-B-ES, 81 % positive, t 0.96, 97.5 %, fails the 5-second gate too.)
## 6. Choices, deviations, open points
1. The rules changed while this stage ran: EDGE_SPEC got "CORRECTION AND ADMISSION v2" at about 11:15 ET (the 5-second rule becomes an account-level share, not a gate; tables are judged on their average). This stage was judged as briefed (old gate, central variant). No unit fails ONLY the 5-second gate, so "none passes" does not hang on it. For the v2 re-judge: `fast_profit_share` (winners under 5 s / all winners) is in `out/entries/build_units.csv`; tables worth a look there are W-A-NQ, W-B-NQ, W-B-ES, D-C-GC.
2. Fixed before any number: "held under 5 s" = exit minus entry under 5,000 ms (the stores keep whole seconds, so median holds are whole seconds); non-release days = no calendar row at that clock time (for group B too); "reachable" = BUILD trades + 2024 release days; bars as in stage 3 (2.5608 / 2.001 / 1.6279); per-wait "without fast winners" = the median over the 32 exits.
3. One column was added after the first print-out, as information only: the random-direction control per wait. No verdict uses it.
4. The 18 units are not independent (B is inside A; the markets share the burst) and each store has only 2 control seeds. W ran 3 stops x 3 targets, not the 8-stop menu. Central variants of failing D tables are the smallest positive cell (the median is negative), so their hold times mean little.
Ledger: nothing new to book (0 runs, 0 variants; this stage only filtered stored BUILD trades): 44,124 in `ledger.csv`, 44,948 with the 824 on paper, of 50,000. Records: `ideas/event_entries_{NQ,ES,GC}/` (notes + 5 CSVs each) · `IDEAS.md` (3 lines, OPEN) · `out/entries/` (judge4_build.py, write_records4.py, build_units.csv / .json, per_x.csv, per_type.csv, pick_reads.csv).
