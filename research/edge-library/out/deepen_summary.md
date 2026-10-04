# Deepen round 1 on stored trades — summary (stage 2a, 2026-10-04)

Plain words; dollars are 1 contract after costs. BUILD = 22 Sep 2021 to end 2023. 2024 was opened for three sides only (section 4; the third by the orchestrator's ruling). 2025+ was never read.

## 1. What was tested
* 58 units (NQ 48, ES 7, GC 3; 16 families): near-misses that pass the heat map and beat random entries but miss the best-of-random bar. None is WEAK, penalised or already read on 2024.
* Each unit was split 8 ways on its own stored trades = **464 side tables** (plus 58 unsplit baselines, 464 placebo tables, 8 information tables for the member, 2 exact re-run tables, 3 tables on 2024).
* The 8 sides: daily ADX(14) at or above 25 / below 25 · prior-day range above / not above its 20-day median · news days only / never (CPI, jobs report, Fed decision) · long only / short only.
* No look-ahead: ADX and the range median use daily bars up to the day before (`out/deepen/test_labels.py`: a day's label does not move when its own bar is changed; passes on NQ, ES, GC).

## 2. How many sides passed each test (of 464)
| test | real units | placebo (random entries) |
|---|---|---|
| (a) at least 100 trades on BUILD | 307 | 402 |
| (b) heat map: 60 % of variants positive, median positive | 295 | 53 |
| (c) central variant beats matched random entries, same split | 306 | 205 |
| (d) central variant's t reaches the best-of-random bar | 23 | 2 |
| (e) beats 99.4 % of 4,000 random draws | 38 | 23 |
| **all five** | **3** | **0** |

## 3. How many would pass by luck
* Placebo = the same 8-side procedure on random-entry stores (29 market x bar size x session combinations, 2 seeds = 58 placebo units, 464 sides): **0 pass**.
* 0 of 464 means the luck rate is below about 0.65 %, so up to about 3 lucky passes among the 464 real sides cannot be ruled out. We found 3.
* Test (e) is sound for the day splits (1 of 348 placebo sides passes it). For long / short it is weak: 22 of 116 placebo sides pass it, because the two random seeds on disk hold about 2 same-side trades per day and the "random" draws barely differ. For the one long side that went further, (e) was redone against 30 fresh long-only random seeds.

## 4. Sides that passed BUILD, and what 2024 said
| side | BUILD | 2024 (whole menu, same split) | result |
|---|---|---|---|
| donchian NQ 5-min, NY morning, **quiet days only** (`n20_atr1p5-r1`) | 81 % of 128 variants positive; 580 trades, $34,460 (2021* -$5,794 · 2022 $32,849 · 2023 $7,405), t 2.07 vs bar 2.02, lift $26,602 | table passes: 82 % positive, median $18,324. But this variant lost $4,715 (260 trades) and lost to random entries by $13,746 | **not admitted** |
| rsi2 NQ 30-min, evening, **long only** (`th5_pts20-r2`, exact re-run) | 84 % of 96 positive; 255 trades, $19,745 (2021* $5,332 · 2022 $12,717 · 2023 $1,696), t 2.09 vs 2.02 | table fails: 19 % positive, median -$8,224 (this variant $341, 111 trades) | **not admitted** |
| straddle at 08:30 NQ, **news days only** (`offatr0p25_pct0p1-r2`; opened by the orchestrator's ruling: 71 BUILD trades, the 100 count BUILD + 2024) | 91 % of 160 positive; 71 trades, $12,951 (2021* -$46 · 2022 $7,896 · 2023 $5,101), t 3.59 vs bar 2.62 | table passes at 60 % only: 63.8 % positive, median $1,448. But this variant lost $1,129 (31 trades; 102 trades in all); under stress -$2,349 | **not admitted** |
| squeeze NQ 30-min, afternoon, long only | passed on stored trades; the exact long-only re-run fails (central variant 21 trades, t 0.88) | not opened | **not admitted** |

Donchian detail: 84 of 128 variants are positive in both periods and under 2 ticks + 250 ms (saved: `members/_rejected/donchian_NQ_tf5_nyam_vol_lo/surviving_set.csv`). The BUILD central variant is not one of them. The rule-chosen replacement (`n60_pts10-r0`) has a BUILD t of 1.65, below the bar, and loses to random entries in both periods; the same case was demoted in stage 1. Only 17 of the 84 beat random entries with the same exits on the same days in both periods: on quiet days the NQ morning itself paid, not the breakout. At about $1,000 risk the BUILD central variant made $28,412 on BUILD; worst open loss $184 per micro (10 micros inside $2,000). Straddle detail: 86 of 160 variants survive both periods and stress (saved: `members/_rejected/straddle_t_0830_NQ_tf30_pre_news_only/`), but not the BUILD central variant, and the ruling allows no replacement. Stress on BUILD: $12,951 -> $11,476. It is the same idea as the member (08:30 burst), whose own news-day profit also faded in 2024.

## 5. Admitted
**None**, after three sides were opened on 2024. The library still has one member (orb_NQ_tf1_pre).

## 6. Closest misses (test failed)
1. donchian NQ 5-min morning, quiet days — passed BUILD and the 2024 table; failed admission (its central variant is negative on 2024).
2. rsi2 NQ 30-min evening, long only — passed BUILD; failed the 2024 heat map.
3. straddle at 08:30 NQ, news days only — passed BUILD (once the 100 trades count BUILD + 2024: 102) and the 2024 table; failed admission (its central variant lost $1,129 in 2024).
4. vwap_flip NQ 5-min pre-market, quiet days — fails only (e): beats 97.8 % (needs 99.4 %); t 2.24 vs 2.02, $22,031.
5. ib break ES 30-min midday, non-news days — fails only (e): 98.9 %; t 1.53 vs 1.30, $14,918. (Next: ib break ES 1-min midday quiet days 98.7 %; vwap_flip NQ 15-min afternoon quiet days 98.7 %.)

## 7. Member orb_NQ_tf1_pre — where its edge sits (information only; default variant, BUILD + 2024, 819 trades, $28,799)
* News days: 102 trades, $13,022 ($128 a trade; CPI $8,364, jobs report $3,527, Fed days $452). Other days: 717 trades, $15,777 ($22 a trade).
* By year, news / other: 2021* $494 / -$1,334 · 2022 $8,601 / $1,277 · 2023 $3,071 / $4,253 · 2024 $856 / $11,581. The news-day edge was strong in 2022 and almost gone in 2024.
* Short: 422 trades, $22,352 (t 3.7). Long: 397 trades, $6,447 (t 1.1). Trend days (ADX 25+) $18,726 vs $10,870; quiet vs active days about equal ($14,751 vs $14,403).

## 8. Honest open risks and deviations from the written rules
1. No new member. Three units (donchian NQ 5-min morning, rsi2 NQ 30-min evening, straddle at 08:30 NQ) have now spent their 2024: information only from here.
2. Test (a) was first counted on BUILD alone (stricter than the library's BUILD + 2024). The orchestrator ruled it counts BUILD + 2024 and had 2024 opened for the 08:30 straddle on news days; its random-minute control was not run on 2024 (the ruling asked for the menu only).
3. News dates are not in the engine (score.py / timed.py hold none). Used `research/prop-portfolio/2026-09-29/news_days.csv` (ForexFactory export): 12 CPI + 12 jobs reports + 8 Fed decisions a year 2021-2024, checked date by date; all three kept.
4. Daily bars start on 22 Sep 2021, so the first 28 sessions (ADX) and 20 sessions (range median) are in neither side. On a contract roll day the price gap is not counted as a move.
5. Long / short splits of stored trades are approximate (one position at a time, capped entries); squeeze shows they can flatter. Day splits are exact (every day is simulated on its own, flat by 15:58). The same-side random control is also tilted: a fade buys after a drop, when random longs lose. Do not trust a long / short side without an exact re-run and a better control.
6. A moved default was not admitted, following the checker's stage-1 precedent (the rule text itself does not say so). The reason for the quiet-day filter was written after BUILD was seen.
7. "Quiet day" is 6 of the 17 day-split sides that pass at least four of the five tests, and it shows in the member's own BUILD table (85 % of variants positive on quiet days vs 40 % on active days). It is a lead, not a result: the one case opened on 2024 turned out to be the market's drift.

Ledger: +962 candidate cells (192 exact long-only BUILD re-runs, 384 on 2024, 386 stress) = 35,770 of 40,000; +188 control cells; +12 member runs. 2024 reads: `out/deepen/pick_reads.csv`. Records: `IDEAS.md` (113 ideas: 1 admitted, 112 open, 0 shelved) · `ideas/<family>_<market>/` (23 folders) · `members/_rejected/` · `out/deepen/` (scripts, sides.csv, placebo.csv).
