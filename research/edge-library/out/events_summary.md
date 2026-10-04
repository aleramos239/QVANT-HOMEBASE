# Event straddles — summary (stage 3 = new-idea round 2, 2026-10-04)
Plain words; dollars are 1 contract after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only), PICK = 2024. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Real (paper or small-size) fills on release days are still needed.**
## 1. What was tested
* No new strategy code: the stored BUILD trades of three straddle families that ran on every day, split by an official release calendar. 15 units = E1 tight straddle 08:30 x {A every 08:30 release day, B tier-1 only (no claims-only days)} · E2 ATR straddle 08:30 x {A, B} · E3 tight straddle 10:00 x {C every 10:00 release day} x NQ, ES, GC. Result in one line: the tight straddle earns more on release days in every market; the wide ATR straddle (E2) does not.
* Calendar (`engine/cache/events.csv`): trusted, nothing dropped. Checked without prices: no weekend date; 12 a year for each monthly release, 52 claims, 8 Fed decisions; jobs report / CPI / Fed dates equal the old file (40 / 40 / 27). JOLTS and PCE have a few months with two releases and the next with none (release timing); 6 claims moved to Wednesday in holiday weeks. Event sessions BUILD / 2024: A 227 / 96, B 159 / 68, C 97 / 46.
## 2. The 15 units on BUILD (a unit passes only with all five tests; test (a), 100 trades reachable with 2024, passes everywhere)
| unit | BUILD trades | variants positive | central variant net | t vs bar | per trade: event days vs days without a release | beats random day subsets (needs 99.67 %) | result |
|---|---|---|---|---|---|---|---|
| E1-A NQ | 225 | 100 % of 27 | $10,305 | 2.77 vs 2.56 | $46 vs $1 | 98.6 % | fail (e) |
| E1-A ES | 226 | 48 % | $759 | 0.22 vs 2.00 | $3 vs -$26 | 93.0 % | fail (b, d, e) |
| **E1-A GC** | 223 | 96 % | $10,598 | 4.55 vs 1.63 | $48 vs -$19 | 100 % | **pass** |
| **E1-B NQ** | 157 | 100 % | $9,047 | 3.35 vs 2.56 | $58 vs -$5 | 99.9 % | **pass** |
| E1-B ES | 158 | 85 % | $2,118 | 1.09 vs 2.00 | $13 vs -$31 | 99.95 % | fail (d) |
| **E1-B GC** | 156 | 100 % | $8,066 | 4.18 vs 1.63 | $52 vs -$19 | 100 % | **pass** |
| E2-A NQ | 225 | 79 % of 160 | $8,320 | 0.18 vs 2.56 | $37 vs $214 | 23.7 % | fail (c, d, e) |
| E2-A ES | 226 | 31 % | $196 | 0.07 vs 2.00 | $1 vs -$30 | 97.8 % | fail (b, d, e) |
| E2-A GC | 223 | 63 % | $3,088 | 0.17 vs 1.63 | $14 vs -$95 | 86.9 % | fail (d, e) |
| E2-B NQ | 157 | 74 % | $5,267 | 0.68 vs 2.56 | $34 vs $22 | 60.0 % | fail (d, e) |
| E2-B ES | 155 | 38 % | $68 | 0.02 vs 2.00 | $0 vs -$29 | 96.1 % | fail (b, d, e) |
| E2-B GC | 156 | 65 % | $3,276 | 0.49 vs 1.63 | $21 vs -$35 | 78.1 % | fail (d, e) |
| E3-C NQ | 95 | 96 % of 27 | $3,215 | 1.67 vs 2.56 | $34 vs $0 | 94.3 % | fail (d, e) |
| E3-C ES | 97 | 81 % | $1,450 | 0.94 vs 2.00 | $15 vs -$39 | 99.98 % | fail (d) |
| **E3-C GC** | 97 | 100 % | $8,202 | 6.10 vs 1.63 | $85 vs -$30 | 100 % | **pass** |
## 3. The four passers on 2024 (whole menu, same day filter, random-minute control run too)
| unit (BUILD central variant) | 2024 table | this variant in 2024 | same bracket at a random minute | stress 2 ticks + 250 ms, BUILD / 2024 | look |
|---|---|---|---|---|---|
| E1-A GC `offA_pts1p6-r1` | 100 % of 27 positive, median $5,756 | $5,496 (96 trades) | -$4,492 | $6,358 / $4,126 | SECOND |
| E1-B NQ `offB_pts5-r3` | 81 %, median $2,838 | $2,383 (68) | -$1,659 | $8,637 / $173 | SECOND |
| E1-B GC `offA_pts1p6-r1` | 96 %, median $4,088 | $2,448 (68) | -$3,245 | $4,746 / $1,128 | SECOND |
| E3-C GC `offA_pts1p6-r1` | 100 %, median $3,396 | $4,166 (46) | -$1,152 | $6,972 / $3,396 | first |
## 4. Admitted: three members, ALL FLAGGED (checker: confirm or demote). All four units pass every test of `library.admission` (unchanged) with the BUILD central variant.
| member | per year (trades) | combined | at about $1,000 risk: combined / worst open loss on a trade | max micros inside $2,000 |
|---|---|---|---|---|
| `straddle_tight_0830_GC_tf30_pre_evA` gold, 08:30 release days: bracket 0.6 pts, stop 1.6, target 1.6 | 2021* $902 (27) · 2022 $4,660 (100) · 2023 $5,036 (96) · 2024 $5,496 (96) | $16,094 (319) | $87,916 / $1,488 | 83 |
| `straddle_tight_0830_NQ_tf30_pre_evB` NQ, tier-1 days: bracket 5 pts, stop 5, target 15 | 2021* $1,124 (19) · 2022 $5,961 (71) · 2023 $1,962 (67) · 2024 $2,383 (68) | $11,430 (225) | $100,800 / $5,100 | 39 |
| `straddle_tight_1000_GC_tf30_nyam_evC` gold, 10:00 release days: bracket 0.6 pts, stop 1.6, target 1.6 | 2021* $552 (12) · 2022 $2,418 (43) · 2023 $5,232 (42) · 2024 $4,166 (46) | $12,368 (143) | $71,362 / $1,178 | 105 |
* E1-B GC is the same variant on a subset of E1-A GC's days: one strategy, recorded on the evA card, no folder of its own (rule fixed before the admission results). The NQ member is the variant the checker demoted on all days, now on tier-1 days only: t 3.35 clears the unchanged bar (1.98 on all days), but 2024 survives the stress by $173 and it is the SAME 08:30 idea as orb_NQ_tf1_pre (same side on 77 % of shared days).
* Speed: most of the profit is trades that open AND close inside 2 seconds (gold 08:30 $13,746 of $16,094; NQ $9,904 of $11,430; gold 10:00 $10,406 of $12,368, median trade 0.3 s).
## 5. Fill realism (information, not a gate): entry filled 1 / 5 / 25 ms after the trigger print, never better than the stop price
| | BUILD: engine -> 1 ms / 5 ms / 25 ms | 2024: engine -> 1 ms / 5 ms / 25 ms | flag |
|---|---|---|---|
| gold 08:30 (evA) | $10,598 -> -$1,382 / $1,278 / $1,758 | $5,496 -> $426 / $596 / -$1,524 | not fragile at 5 ms, but about 90 % of the profit goes |
| NQ 08:30 tier-1 (evB) | $9,047 -> $4,977 / $5,122 / $3,237 | $2,383 -> $1,173 / $473 / -$1,157 | not fragile at 5 ms |
| gold 10:00 (evC) | $8,202 -> $1,652 / $1,852 / -$88 | $4,166 -> -$1,004 / -$184 / -$1,424 | **FILL-FRAGILE** |
| orb_NQ_tf1_pre (member) | $16,362 -> $7,947 / $7,842 / $5,387 | $12,437 -> $8,417 / $6,117 / $2,862 | not fragile; about half the profit goes |

Real fills (desk journal): NQ 09:30 straddle, 10 fills: adverse slip mean 0.6 pt, median 0.375, worst 1.75 · gold jobs report 2026-10-02, 1 fill: 0.0 · YM 09:30, 2 fills: 4 and 5 pts. Real fills sit near the engine's base fill plus about one tick, far better than the 1 ms probe; the 2-tick stress is the nearest test to that and all three members pass it. There is still no real fill at an NQ 08:30 or a gold 10:00 release.
## 6. Information only
* Release types, gold 08:30 (BUILD, trades / net): jobs report 26 / $716 · CPI 26 / $1,716 · PPI 27 / $2,552 · retail 26 / $1,416 · GDP 28 / $1,718 · PCE 27 / $572 · claims 118 / $5,198 · days without a release 339 / -$6,556.
* NQ 08:30 (central variant of E1-A NQ): jobs report 25 / $2,360 · CPI 27 / $2,582 · PPI 27 / $3,537 · retail 27 / $1,732 · GDP 28 / -$402 · PCE 27 / $1,167 · claims 119 / $1,204 · no release 324 / $379.
* Gold 10:00: ISM manufacturing 27 / $1,902 · ISM services 27 / $2,562 · JOLTS 27 / $2,232 · Michigan 27 / $2,562 · no release 468 / -$14,112. Fed decision 14:00 (19 BUILD days, tight straddle armed at 13:59:59; never opened on 2024): NQ 18 trades $2,248 (t 2.15, 100 % of variants positive) · ES $703 · GC $2,038.
* Odds alone (open losses count; bar 60 % eval / 75 % funded): nobody is near the bar. Eval pass within 10 days at about $1,000 risk (cut to the contract limit), engine fills -> 5 ms fills, in the order gold 08:30 / NQ / gold 10:00 / orb: Lucid Flex 3 / 7 / 0 / 26 % -> 1 / 4 / 0 / 20 % · Lucid Pro 3 / 7 / 0 / 33 % -> 1 / 4 / 0 / 26 % · Pro without daily limit 3 / 7 / 0 / 31 % -> 1 / 4 / 0 / 25 % · Apex 50K 14 / 30 / 1 / 34 % -> 6 / 22 / 0 / 31 % (largest size inside the drawdown: gold 08:30 36 %, gold 10:00 36 %). Starting the eval the day before a tier-1 release moves it by -7 to +6 points (mostly +1 to +4). Funded maximum payout within 20 days: 0 to 14 % for the event members, 11 to 25 % for orb. Full table: `out/events/odds.json` and the cards.
## 7. Deviations and open risks
1. The profit of all three members is the simulator's fill inside the burst. The written rule makes the fill probe information, not a gate; a checker may well rule otherwise, first of all for gold 10:00.
2. Three of four passing units are a SECOND LOOK on 2024 (the tight 08:30 straddle on NQ and GC was read on all days in stage 2b). The 15 units are not independent (B is inside A; the markets share the burst); no placebo split was run (not in the written section): tests (d) and (e) are the luck guards.
3. Bars as written: NQ 2.56 and GC 1.63 are the checker's pooled random-minute bars, ES 2.00 the stage-1 file. With the stage-1 file's own NQ 2.62 / GC 1.64 no verdict changes.
4. Choices fixed before any number: non-event days = days with no calendar release at that clock time (for group B too); group C read literally also holds the two days PCE came out at 10:00 (1 on BUILD, 1 in 2024); "reachable" = BUILD trades + 2024 event days. Odds: the scoring engine is built for NQ, so gold prices were scaled by 5 (dollars unchanged) and gold's own calendar used; one fixed size, no day rules. The Fed 14:00 run used the existing tight-straddle class with a new clock time on 19 days only.

Ledger: +110 candidate variants (27 on 2024, 2 stress, 81 Fed 14:00 information) -> 43,388 of 50,000; +54 control variants; +8 member runs. 2024 reads: `out/events/pick_reads.csv`. Records: `members/<3 folders>/` · `ideas/event_straddle_{NQ,ES,GC}/` · `IDEAS.md` · `out/events/` (scripts, build_units.csv, per_type.csv, pick_judgement.json, admission.json, fill_probe.json, odds.json, fomc_1400.json).
