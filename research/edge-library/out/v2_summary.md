# Admission v2 — summary (2026-10-04): every stored unit re-judged on the AVERAGE of all its variants
Plain words; dollars are 1 contract after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read. No eval or payout odds (library first).
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
## 1. Result
* 1,916 units judged (stage 1: 1,623 · new-idea round 1: 258 · event straddles: 15 · stage-4 entries: 18 · the two stage-2a day-filter sides opened on 2024). **14 units pass all six tests and are saved = 7 ideas** (`out/v2_members.md`).
* **Luck check: 1 of 168 random-entry tables passes the same six tests (0.6 %). At that rate about 11 of the 1,881 non-event units would pass by luck; 8 did (NQ: 7 of 695 real vs 1 of 56 random). The 8 non-event members are NOT shown to be more than luck: treat them as leads.** The 6 event members beat two controls each by wide margins, but no placebo exists for day filters and their fills are the open risk.
* The v1 member `orb_NQ_tf1_pre` fails v2 on BUILD (members/_v1_only/). The three v1 event members stay (cards refreshed, new defaults).
## 2. Counts per test
| store | units | (1) | (1)+(3) | (1)+(2)+(3) = opened on 2024 | (4) | (4)+(5) | (4)+(5)+(6) | all six, saved |
|---|---|---|---|---|---|---|---|---|
| stage 1 (incl. 81 Level 2 variants) | 1,623 | 209 | 194 | 38 | 14 | 8 | 7 | 7 |
| new-idea round 1 | 258 | 43 | 37 | 11 | 7 | 3 | 1 | 1 |
| event straddles | 15 | 12 | 12 | 8 | 8 | 8 | 6 | 6 |
| stage-4 event entries | 18 | 7 | 6 | 0 | 0 | 0 | 0 | 0 |
| stage-2a day-filter sides | 2 | 2 | 1 | 0 | 0 | 0 | 0 | 0 |
| **all** | **1,916** | **273** | **250** | **57** | **29** | **19** | **14** | **14** |

Tests: BUILD (1) 60 % of variants profitable and the average variant profitable · (2) real edge at table level · (3) trade minimum on the average variant. 2024: (4) average and median variant profitable · (5) average still beats random · (6) average profitable under 2 ticks + 250 ms (+ 100 ms late cancel of the other bracket side). Test (2) was drawn for the 398 units with a positive average and at least 50 % of variants profitable: 77 pass it. BUILD passers by market: NQ 39, ES 12, GC 6. Every member has a surviving set and 141+ trades.
## 3. How "beats random" was built (tests 2 and 5; every control that applies must pass; BUILD needs lift > 0 and 95 % of replicates beaten, 2024 lift > 0)
* **Bar-based units — random entries (C1).** Pool on disk: 2 random seeds per market x bar size, same exits, same session. 200 replicates. One replicate = one random TABLE: each variant gets as many random trades as it has on each day (the day-and-session matching of `library.c1_draws`), and all variants of the table use the SAME random entries, so the replicates keep the table's own co-movement. Independent draws per variant would make the spread of the replicates about 5 times too narrow (4.4-5.1 times in four tables checked).
* **Time-fired units — random minute / random direction.** 2 seeds on disk = 2 real replicates (THIN, said on the card). 200 replicates = day-by-day mixes of the two seeds.
* **Level 2 variants (81).** Shuffled book (2 seeds, THIN; 16 of 81 have no shuffle on disk = fail) PLUS the same strategy without the option (net per trade) PLUS C1. One passes BUILD (donchian thin-book, NQ 30-min morning) and fails 2024 against both.
* **Day-filter units (events, stage 4, the two stage-2a sides).** Net per trade of the filtered table must beat the unfiltered table and 95 % of 4,000 random same-size day subsets, AND the unit must beat its random-minute / random-direction / random-entry control on the same days.
## 4. Placebo (the whole procedure on random-entry stores)
168 random units (3 markets x 4 bar sizes x 7 sessions x 2 seeds; one seed is the "strategy", the other its control): 6 pass (1), 3 pass BUILD (all NQ), 1 passes 2024 and stress = **1 of 168 passes all six** (NQ 1-min evening, seed 2). ES and GC: 0 of 112. Its control is one seed, so the count is if anything too high; 168 units cannot pin a rate this small (0.6 %, range about 0-3 %).
## 5. Members — the AVERAGE variant (variants: judged / saved in the surviving set; lift = table average minus the random table average, BUILD / 2024)
| idea · unit | market | session | bar | variants | trades | 2021* | 2022 | 2023 | 2024 | win | PF | max DD | <= 5 s | lift BUILD / 2024 | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 08:30 burst · `straddle_t_0830_NQ_tf30_pre` | NQ | pre | 30 | 160 / 67 | 763 | -$2,667 | $37,863 | $8,469 | $7,328 | 34 % | 1.15 | $25,074 | 4 % | $29,479 / $11,284 | 2nd look 2024, thin |
| 08:30 burst · `straddle_tight_0830_NQ_tf30_pre` | NQ | pre | 30 | 27 / 19 | 766 | -$230 | $4,051 | $5,915 | $5,548 | 43 % | 1.21 | $3,464 | 35 % | $16,617 / $9,354 | 2nd look 2024, thin, burst fills |
| 08:30 burst, release days · `..._NQ_tf30_pre_evA` | NQ | pre | 30 | 27 / 24 | 320 | $380 | $4,411 | $5,294 | $3,937 | 49 % | 1.49 | $1,932 | 67 % | $13,240 / $5,414 | 2nd look 2024, thin, burst fills, FAST |
| 08:30 burst, tier-1 days · `..._NQ_tf30_pre_evB` | NQ | pre | 30 | 27 / 20 | 225 | $554 | $5,350 | $3,241 | $3,272 | 52 % | 1.63 | $1,673 | 77 % | $11,069 / $4,453 | 2nd look 2024, thin, burst fills, FAST |
| 08:30 burst, release days · `straddle_tight_0830_GC_tf30_pre_evA` | GC | pre | 30 | 27 / 24 | 317 | $404 | $4,645 | $5,135 | $5,910 | 50 % | 1.58 | $2,426 | 52 % | $15,003 / $9,590 | 2nd look 2024, thin, burst fills, FAST |
| 08:30 burst, tier-1 days · `..._GC_tf30_pre_evB` | GC | pre | 30 | 27 / 22 | 223 | $384 | $3,693 | $4,622 | $4,414 | 52 % | 1.69 | $2,025 | 64 % | $12,094 / $6,607 | 2nd look 2024, thin, burst fills, FAST |
| 10:00 release days · `straddle_tight_1000_NQ_tf30_nyam_evC` | NQ | nyam | 30 | 27 / 26 | 141 | -$279 | $2,075 | $2,304 | $3,242 | 49 % | 1.61 | $1,740 | 56 % | $6,905 / $3,495 | thin, burst fills, FAST |
| 10:00 release days · `straddle_tight_1000_GC_tf30_nyam_evC` | GC | nyam | 30 | 27 / 25 | 142 | $392 | $3,143 | $4,675 | $4,309 | 58 % | 2.23 | $1,273 | 47 % | $9,603 / $4,711 | 2nd look 2024, thin, burst fills |
| first-bar momentum · `first_bar_mom_NQ_tf30_mid` | NQ | mid | 30 | 96 / 43 | 413 | $5,291 | $8,201 | $876 | $11,239 | 38 % | 1.15 | $16,291 | 0 % | $16,248 / $8,314 | 2025-26 PENALTY |
| first-bar momentum · `first_bar_mom_NQ_tf15_mid` | NQ | mid | 15 | 96 / 39 | 305 | $8,025 | $11,082 | -$2,185 | $3,985 | 38 % | 1.16 | $15,056 | 0 % | $16,766 / $3,087 | 2025-26 PENALTY; 2024: only 50 % of variants positive |
| first-bar momentum · `first_bar_mom_ES_tf15_mid` | ES | mid | 15 | 95 / 25 | 306 | $921 | $5,619 | -$1,908 | $2,681 | 37 % | 1.09 | $10,270 | 0 % | $7,252 / $3,250 | 2025-26 PENALTY; stress leaves $436 in 2024 |
| opening range break · `orb_NQ_tf15_pre` | NQ | pre | 15 | 96 / 50 | 725 | -$468 | $17,005 | $6,170 | $10,886 | 33 % | 1.11 | $22,228 | 2 % | $18,981 / $4,382 | EXAM 2nd look; 1 / 5 / 30-min fail (2); burst fills |
| 18:00 bracket · `straddle_t_1800_NQ_tf30_eve` | NQ | eve | 30 | 160 / 61 | 647 | $3,352 | $13,856 | -$1,450 | $12,460 | 32 % | 1.10 | $23,301 | 1 % | $44,921 / $142 | thin |
| TEMA slope turn · `tema_slope_NQ_tf30_eve` | NQ | eve | 30 | 96 / 51 | 480 | -$3,296 | $1,542 | $21,726 | $11,967 | 33 % | 1.17 | $20,204 | 0 % | $16,123 / $1,988 | WEAK reason, EXAM 2nd look |

Trades, win, PF, max DD = BUILD + 2024 combined. "<= 5 s" = share of gross profit from trades held under 5 s (Lucid's limit is 50 % per ACCOUNT; not a gate). Event rows also beat non-release days per trade: BUILD +$27 to +$95, 2024 +$17 to +$97 (NQ evA / evB beat only 89 % / 91 % of random day subsets in 2024). The default variant (middle survivor by BUILD net; an even count takes the lower middle) is on each card and usually earns more than the average: read the average.
## 6. Earlier members and near-misses
* **In:** tight 08:30 bracket NQ on all days (demoted under v1) · the ATR 08:30 and 18:00 brackets NQ (stage-1 near-misses) · 08:30 release days NQ (evA) and tier-1 gold (evB) · 10:00 release days NQ · first-bar momentum midday NQ 15 / 30-min and ES 15-min · orb NQ 15-min pre-market · TEMA slope NQ evening.
* **Midday range break (ib): not in.** NQ 5 / 15 / 30-min and ES 30-min pass BUILD (NQ: 100 % of variants positive, average $44-52k) and fail 2024: 22-34 % of variants positive, average -$2,830 to -$5,321, and random entries did better.
* **Channel breakouts (donchian): not in.** NQ 30-min morning fails (2) by a hair (beats 93.5 % of random tables, needs 95). NQ 5-min morning on quiet days beats all days but loses to random entries on the same days (-$5,703). Afternoon: NQ 15-min passes BUILD and (4) (69 % positive, $4,382) but random entries earned $9,114 more in 2024; NQ 30-min, ES 5 / 30-min lose 2024.
* **VWAP pullback: not in.** NQ 5-min and 1-min afternoon pass BUILD and (4) (61-62 % positive, $3,203 / $2,020) but fail (5): random entries with the same exits earned $10,605 / $21,119 more in 2024. ES 30-min loses 2024.
* **Wide bracket (stage 4): not in.** On NQ 08:30 every variant is positive and it beats random minutes ($12,697-$13,411), but release days beat only 70 % (all releases) and 90 % (tier-1) of random day subsets per trade. The market-order entry fails (1) nearly everywhere; gold 10:00 passes the day test but a random direction earns more.
* **The 20 closest stage-1 near-misses** (first 20 of `out/near_misses.md` B): 1 in (first-bar momentum ES 15-min midday), 9 pass BUILD and fail 2024, 9 fail (2), 1 fails (3).
* **orb NQ 1-min pre-market (v1 member): out.** Table average $19,279 vs $18,754 for random 1-minute entries (beats 54 %): with no target, random entries held through 08:30 earned more ($66,766 vs $49,283); with a target orb is ahead by $6,528.
## 7. Closest misses (one test failed)
BUILD: 193 units fail only (2), 22 of them between 90 and 95 % (donchian NQ 30-min morning 93.5 %, vwap_z NQ 30-min midday 94.5 %, orb_confirm NQ 15-min midday long 90.5 %, wide bracket NQ tier-1 90.1 %); 10 fail only (1) (donchian ES 30-min morning 59.4 %); 8 fail only (3) (pinbar ES 30-min midday: 65 trades). 2024: ema_pullback NQ 1-min morning (75 % positive, $20,655, but $454 below random) · vol_spike_break NQ 30-min afternoon and ema_pullback NQ 15-min midday (stress: -$507 / -$2,636) · tight 08:30 bracket gold on all days, ES tier-1 days, ES 10:00 days (stress: -$1,785 / -$160 / -$799) · tema_slope NQ 30-min midday and ema_pullback NQ 15-min evening (average -$873 / -$80). Full list: `out/v2/closest.csv`.
## 8. Deviations and judgement calls
1. Test (2) is a conjunction of every control on disk for the unit (stricter than one control). The table draws are a coupled version of `library.c1_draws` written for v2 (two single variants checked: mean -$8,921 / -$11,381 vs the library's -$8,975 / -$10,569).
2. The C1 pool is 2 seeds: its own luck is not in the 200 draws. With a stop and no target, random NQ entries earned $6k to $100k on BUILD depending on session and bar size (stop-and-hold in a trending market), so a table's average leans on its no-target variants. orb pre-market: the orb table is the same at 1 and 15 minutes ($49,283 / $51,440 with no target), but random 1-minute entries are already in before 08:30 and earned $66,766, random 15-minute entries $22,259: that is why 1-min fails and 15-min passes.
3. Test (3) on BUILD = BUILD trades scaled to BUILD + 2024 at the same daily rate >= 100, then the real count. 8 units pass (1) and (2) and fail only this; three are within 7 trades (va_reclaim NQ 30-min Asia 96.9, vol_spike_break GC 30-min midday 94.0, pinbar ES 30-min midday 93.6). Their 2024 stays unread. The day-filter units that the older "BUILD trades + 2024 days" count would let through fail (2) anyway.
4. "60 %" is read as 60 % or more (library convention). Two BUILD passers sit at exactly 60 %; both fail 2024.
5. The placebo's control is one seed (the unit's own seed cannot be its control). No placebo for day filters. No 1 / 5 / 25 ms fill probe for the new defaults.
6. Penalty and WEAK families are saved with their flags, as v2 says (v1 refused penalty units). "The 20" = the first 20 rows of near_misses.md section B.
7. 57 units have now had 2024 opened; the 43 that failed are information only from here, including units DEEPEN ROUND 2 names (ib midday, vwap_trend_pull, vol_spike_break, orb_confirm afternoon).

Ledger: +5,162 candidate cells (3,601 on 2024, 1,561 stress) -> 49,286 in ledger.csv, 50,110 with the 824 on paper, of 80,000. +2,786 control cells; +56 member runs (132 of 2,000). 2024 reads: `out/v2/pick_reads.csv` (118 rows).
Records: `members/<14 folders>/` · `members/_v1_only/` · `out/v2_members.md` · `IDEAS.md` · `out/v2/` (v2.py = method, judge_build.py, plan_pick.py, run_v2.py, judge_pick.py, admit_v2.py, placebo.py, report_tables.py, build_units.csv, pick_units.json, final.json, members.json, placebo.csv, closest.csv) · stores `runs_v2/`.
