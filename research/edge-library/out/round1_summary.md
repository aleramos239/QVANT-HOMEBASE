# New-idea round 1 — summary (stage 2b, 2026-10-04)
Plain words; dollars are 1 contract after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only), PICK = 2024. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Forward (paper) trading is still needed.**

## 1. What was tested
* 7 new ideas (N1-N7, reasons written first), 63 runs, 7,068 variants (201 of them author cells: information only) on NQ, ES, GC; 2,214 own random-control variants + the 12 random-entry pools.
* 258 judged units (86 per market: idea x bar size or clock time x session; orb_confirm long-only and short-only judged apart).
## 2. Counts per gate
258 judged on BUILD -> 43 pass the heat map (at least 60 % of variants positive, median positive; 27 at 70 %, 19 at 80 %) -> 34 also beat their matched random control -> 4 also have the central variant's t above the best-of-random bar (= pass BUILD) -> 4 opened on 2024 (whole menu + control; `out/admit_r1/pick_reads.csv`) -> 3 pass the 2024 heat map -> 1 has its BUILD central variant positive in 2024 (no moved default) -> 1 is positive under 2 ticks + 250 ms with at least 100 trades and fits $2,000 -> **1 admitted, FLAGGED**.
## 3. Heat-map passes by idea (BUILD): units passing at 60 / 70 / 80 %, of units judged
| idea | NQ | ES | GC |
|---|---|---|---|
| N1 vwap_trend_pull | 7 / 5 / 4 of 11 | 3 / 1 / 0 of 11 | 2 / 1 / 0 of 11 |
| N2 va_reclaim | 2 / 1 / 0 of 28 | 1 / 0 / 0 of 28 | 0 / 0 / 0 of 28 |
| N3 orb_confirm (one direction) | 9 / 7 / 5 of 18 | 4 / 1 / 1 of 18 | 2 / 0 / 0 of 18 |
| N4 late_mom | 0 of 1 (31 % positive) | 0 of 1 (6 %) | 0 of 1 (7 %) |
| N5 open_fade | 0 of 2 | 0 of 2 | 0 of 2 |
| N6 vol_spike_break | 7 / 5 / 4 of 23 | 3 / 3 / 2 of 23 | 1 / 1 / 1 of 23 |
| N7 straddle_tight 08:30 | 1 / 1 / 1 of 1 (100 %) | 0 of 1 (4 %) | 1 / 1 / 1 of 1 (85 %) |
| N7 straddle_tight 09:30 / 10:00 | 0 of 1 (0 %) / 0 of 1 (52 %) | 0 / 0 | 0 / 0 |

## 4. The four units that passed BUILD, and what 2024 said
| unit (BUILD central variant) | BUILD | 2024 (whole menu) | result |
|---|---|---|---|
| vwap_trend_pull NQ 5-min, afternoon (`x0p1_pts30-r2`) | 92 % of 96 positive; 899 trades, $64,434, t 2.70 vs bar 2.02, lift over random $51,072 | table passes at 60 % only (61 %, median $2,406); this variant lost $14,421 (349 trades) and lost to random entries by $21,792 | **not admitted** |
| vol_spike_break NQ 30-min, afternoon (`m4_pct0p2-r2`) | 89 % of 91 positive; 49 trades, $18,134, t 3.18 vs 2.02, lift $19,038 | table fails: 53 %, median $799; this variant lost $1,252 (28 trades; 77 in all) | **not admitted** |
| straddle_tight 08:30 GC (`offC_pts2-r1`) | 85 % of 27 positive; 434 trades, $5,004, t 1.17 vs thin bar 0.63, lift $11,552 | table passes (70 %, median $1,970); this variant lost $1,180 (210 trades) | **not admitted** |
| straddle_tight 08:30 NQ (`offB_pts5-r3`) | 100 % of 27 positive; 549 trades, $8,954, t 1.98 vs thin bar 0.84, lift over random minutes $14,733 | table passes (81 %, median $6,005); this variant made $4,869 (244 trades), lift $10,578 | **admitted, FLAGGED** |

## 5. Admitted: straddle_tight_0830_NQ_tf30_pre — FLAGGED (checker: confirm or demote)
Rule: at 08:29:59 ET a buy stop 5 points above and a sell stop 5 points below the price (one cancels the other, unfilled after 5 min is cancelled); stop 5 points, target 15 points; about one trade a day.
* Per year: 2021* $862 · 2022 $4,412 · 2023 $3,680 · 2024 $4,869 · combined $13,823; 793 trades, win 32 %, PF 1.22, max drawdown $2,971, Sharpe 1.39.
* Stress (2 ticks + 250 ms): BUILD $8,954 -> $6,619; 2024 $4,869 -> $769. Surviving set: 19 of 27 variants.
* Worst open loss on one trade $51 per micro -> at most 39 micros inside $2,000 (95 at the 99th percentile). At about $1,000 of risk (100 micros): $90,650 combined, Sharpe 0.91, but one trade had a $5,100 open loss.
* FLAG 1: the bar it cleared is thin (8 random replicates on NQ). With stage 1's random-minute straddles pooled in the bar is 2.56, and NQ's random-entry bar is 2.02: its t of 1.98 fails both.
* FLAG 2: it is the same idea as orb_NQ_tf1_pre (same side on 80 % of shared days, daily correlation 0.41): one strategy for a stack, not two. 2024 for this idea had already been seen through that member.
* FLAG 3: trades that open and close inside 2 seconds of the data release earn $13,352, as much as the whole net; 2024 survives the stress by $769 only.

## 6. Closest misses (test failed)
1. vwap_trend_pull NQ 5-min afternoon — passed BUILD and the 2024 table; its central variant lost in 2024 (42 of 96 variants survive both periods and stress: `members/_rejected/`).
2. straddle_tight 08:30 GC — passed BUILD (thin bar) and the 2024 table; its central variant lost in 2024.
3. vol_spike_break NQ 30-min afternoon — passed BUILD; failed the 2024 heat map (53 %).
4. vol_spike_break NQ 30-min morning — fails only the bar: t 1.90 vs 2.02 (100 % of 32 variants positive, lift $4,655).
5. orb_confirm NQ 15-min midday, long only — fails only the bar: t 1.81 vs 2.02 (91 % positive, lift $25,625, beats 99.5 % of random draws).
## 7. Information only (not tests)
* Quiet vs active days (prior-day range below / above its 20-day median): the heat map passes on quiet days alone in 84 of 258 units, on active days alone in 44, on all days in 43; the quiet side has the higher share in 161 of 258 (median share positive 46 % vs 22 %). The four BUILD passers show no quiet tilt. Stage 2a's caution stands: on NQ quiet days the market itself drifted up.
* Author cells (315): N1 (NQ 15-min, stop 80 points): afternoon 3 of 3 positive ($36,465 to $44,619, t up to 2.53), midday 3 of 3, morning 0 of 3. N3 (stop at the other side of the range, flat 15:30): NQ long 27 of 27 positive (median $60,715, best t 3.23), NQ short 22 of 27, ES long 26 of 27, GC 32 of 54. N5 (target = the pre-open price): ES 0 of 48, GC 0 of 48, NQ 18 of 48 (median -$3,520).
## 8. Multiple-testing honesty
* 258 units judged; 4 passed BUILD (1.6 %). Random units judged by the same two gates: 0 of 192 pass (random entries: NQ 6 of 56 pass the heat map, ES and GC 0 of 56 each; round-1 random-minute / random-direction units: 0 of 24). 0 of 192 cannot rule out a luck rate near 1.6 %, i.e. about 4 lucky passes among 258: we found 4, and 2024 removed 3 of them.
* The units are not independent: the survivor repeats the member's 08:30 idea, and vwap_trend_pull passes the afternoon heat map on 1-, 5- and 15-minute bars while only one clears the bar.
## 9. Member odds alone (about $1,000 of risk, open losses count; bar 60 % eval / 75 % funded) — `out/member_odds.md`
No member reaches the bar on any account. orb_NQ_tf1_pre: P(pass eval within 10 days) 26 % Lucid Flex, 32 % Pro, 31 % Pro without daily limit, 34 % Apex 50K; P(maximum payout within 20 days) 23 / 25 / 24 / 11 %, Apex 300K PA 17 %. The flagged member: 21 / 21 / 21 / 32 % and 8 / 24 / 23 / 11 %, Apex 300K PA 24 %. Both use two-sided brackets, which Apex does not allow.

## 10. Deviations from the written rules and open risks
1. Bar of the time-fired ideas (N4, N7): taken from round 1's own random stores per market (8 replicates, thin), as written in `out/admit_r1/judge_build.py` before any number was opened. Both 08:30 straddles pass only this thin bar. The checker should rule on the flagged member.
2. orb_confirm long-only / short-only units were compared with two-sided random entries (stage 1's convention): a tilted control.
3. Member odds: the engine sizes a member with one fixed number of micros (the median $1,000-risk size, cut to the contract limit) and has a 5-day eval window built in; the 10-day figure uses its own day walk and race on a 10-day window.
4. Not shelved: every round-1 idea has 0 of 4 deepen rounds used, so all stay OPEN (`IDEAS.md`: 2 admitted, 138 open). Three units have now spent their 2024.
Ledger: +440 candidate variants (246 on 2024, 194 stress) -> 43,278 of 50,000 (ledger.csv 42,454 + 824 on paper); +236 control variants; +4 member runs.
Records: `out/admit_r1/` (scripts, build_units.csv, pick_reads.csv, quiet_active.csv, author_cells.csv) · `members/straddle_tight_0830_NQ_tf30_pre/` · `members/_rejected/` · `ideas/<idea>_<market>/` (27 folders).

## CHECKER CORRECTION (2026-10-04, out/check_r1/) — overrides the text above
straddle_tight_0830_NQ_tf30_pre is DEMOTED (members/_demoted/): it fails the unchanged stage-1 bar (t 1.98 vs 2.56) and its profit
needs a fill on the trigger print (1 ms later: 2024 $4,869 -> $729). Round 1 admits NOTHING; the library has ONE member (orb_NQ_tf1_pre).
The member odds inherit the same optimistic burst fills: orb_NQ_tf1_pre has NOT yet had the fill-after-trigger probe.
