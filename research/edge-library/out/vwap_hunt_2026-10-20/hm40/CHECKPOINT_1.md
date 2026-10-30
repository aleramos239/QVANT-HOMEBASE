# CHECKPOINT 1 -- step-back check-in (2026-10-21, written 14:40 ET; picks and test-month reads held since 09:12 by HOLD_PICKS)

**The one question: is the hunt getting closer to 5-10 honest trades a day? No.** 0 honest legs after 28 test-month reads. The 3
passes under the owner's Amendment J bar (win rate >= own break-even) add up to 2.0 trades a day, all from reads made in one hour,
and none survives the Monte Carlo. Today's pass rate (3 of 28 graded = 10.7 %; the last 3 reads were graded at 09:48 and all failed)
is BELOW the rate at which a no-edge box passes this bar (~18 % a read: the random line is weak), and a box with a real +$40-80 edge
passes only 32-42 % of the time: 3 passes where ~5 are expected by chance carry no evidence. The in-sample ranking does not carry to
the test months.

Numbers come from four read-only analysts on the files (scripts in the session scratchpad; the critic's re-derivation is at the end).
Test-month numbers below judge the METHOD only; none chooses or builds a rule.

## 2. The numbers

### a) Target zone (in-sample only; margin > 0, net after 2 extra ticks > 0, positive from 2024-10, > 50 % of its store's boxes positive)
| Trades a day | Versions | Stores | Ideas | Also pass C1-C9 |
|---|---|---|---|---|
| >= 1.0 | 1,391 | 23 | 12 | 202 (14 stores) |
| >= 0.5 | 2,398 | 34 | 15 | 291 |
| >= 0.35 | 2,876 | 36 | 16 | 340 |
Almost all NQ New York breakout / trend rules (ideas 6, 7, 2, 10, 17); median margins +1.2 to +4.9 points. Only 73 trade 5+ a day.
**But being in the zone did not predict a test-month pass: 1 of 15 zone picks passed, 2 of 10 non-zone picks.**

### b) Does picking carry over? (28 picks)
| Group | Picks | In-sample avg / margin | Test avg / margin | Shrink | Kept margin >= 0 |
|---|---|---|---|---|---|
| All | 28 | +$158 / +5.2 pts | -$74 / -2.1 pts | -$231 / -7.3 pts | 7 of 28 |
| Breakouts | 19 | +$175 / +5.5 | -$104 / -2.9 | -$279 / -8.4 | 3 of 19 |
| VWAP rules | 8 | +$121 / +4.6 | +$3 / +0.2 | -$118 / -4.4 | 4 of 8 |
Rank: in-sample avg vs test avg Spearman -0.27 (p 0.17); Pearson over all 28 +0.09 (p 0.63): **no carry-over** (breakouts alone
-0.55, p 0.016). Top half in-sample did no better on test (-$109 vs -$38 a trade). The first 25 graded picks lost $622,616 on their
test months (one contract), worse than random entries on the same months.

### c) Selection rules added after failures
| Picks written | n (graded) | Test margin | J passes |
|---|---|---|---|
| before C7 | 9 (9) | -4.28 | 0 |
| C7 only | 4 (4) | -5.21 | 0 |
| C7 + C8 | 6 (6) | -0.53 | 0 |
| C7 + C8 + C9 | 9 (6) | +0.35 | 3 |
Looks like help, but it is confounded (the later picks are different ideas: 10, 16, 17) and C7 / C9 were written after test-month
losses (CALENDAR.md was "found while checking why idea 7 lost on its test months"): against Amendment E's guard in spirit.

### d) Time and calendar
| Test months | Trades | Avg | Margin | Picks positive |
|---|---|---|---|---|
| Jan 2022 .. May 2024 (8 months) | 5,788 | +$20 | +0.7 | 15 of 28 |
| Sep 2024 .. May 2026 (6 months) | 4,083 | -$181 | -5.7 | 3 of 28 |
The unselected NQ New York average box made +$23.2 a trade on in-sample months from 2024-10 vs +$10.3 before (the picks' own +$171
is selected by C7, so it proves nothing). CALENDAR.md is MIXED, not a clean calendar effect: 8 of its 14 rows are lower in Jan/May/Sep,
6 higher; the pooled -$8.6 vs +$76.3 is driven by one store (the noise band, 3,564 of the 7,260 Jan/May/Sep trades). Calendar,
selection or chance: 6 late test months cannot tell them apart.

### e) Costs (versions trading 3+ a day, 3,131)
Average trade +$4.9 before costs, -$8.2 after (NQ costs $10.79 a trade, ES $21.32, GC $17.28). 43 % positive before costs, 20 % after.
Dead even before costs: ideas 3, 5, 8, 11, 16 (most), 17 night, 26 rv_fade. Costs eat it: 9, 16 emavwma, 2 at 1m, 6 at 5m night.
Edge after costs: 2 at 5m (+$13), 10 (+$8), 6 NY at 15m / donch / disp (+$5 to +$28). Before costs the best exit shapes make only
~+0.02 R a trade; costs take 0.09 R at a 0.5-ATR stop and 0.02 R at 2 ATR, so only WIDE stops survive (ATR x2, own x1-2, NQ 60 pts).

### f) Ideas scoreboard (in-sample average of all boxes; 100 of 120 stores; 16,880 versions; average +$9.3, 39.6 % positive)
| Status | Ideas |
|---|---|
| ALIVE | 17 volume breakout NQ (+$44, 53 %; 1 pass), 27 overnight-range ORB (+$88, 73 %; reads ungraded; NQ store SEEN) |
| ALIVE but never pickable (no version passes C1-C9) | 22 fvg_oside ES/GC (+$11, 73 %), 25 ORB-VWAP pullback ES/GC (+$12, 61 %) |
| WEAK (average > 0, picks failed) | 1, 2, 6, 7 (+$74, 0 of 5), 10, 12 (+$54, 0 of 3), 18, 20, 21 |
| DEAD | 5, 19, 23, 24, 26 (3 % of 1,440 positive), 31 |
| NOT TRIED ENOUGH | 11, 16 (one pick each waiting); 3, 4, 8, 15 negative so far (-$13.0 / -$5.1 / -$16.4 / -$2.6); 13 and 14 now complete and DEAD (-$9.4 / -$0.5); 9 fell to +$0.5 with more specs |

The hunt runner stopped at 11:43 (it went down with the session restart); 8 in-sample runs left, mostly ideas that read dead. Left off
pending the owner's decision.

### g) Honest score -- always next to the pass count
| Test-month reads | Graded | J passes | ...+3 over break-even | ...survive the Monte Carlo | Luck: no-edge passes expected |
|---|---|---|---|---|---|
| 28 | 28 | **3** (margins +2.7, +2.8, +1.5) | 0 | **0** | ~5.0 of 28 (LUCK.md's 1.4 understates it) |

Power of the bar (critic's run): a +$40-a-trade edge passes P1-P5 32 % of the time, +$80 42 %, no edge ~18 %. A pass raises the odds
of a real edge only about 2x.
Under Amendment J, P1 (win >= break-even) is the same test as net >= 0, so it adds nothing beyond P2. P3 (beat all 10 random seeds)
passes a no-edge box ~29 % of the time because each seed has 800-2,600 trades and sits tight: it is not a 95 % line.

### h) Goal math
| | Legs | Trades a day |
|---|---|---|
| Honest legs | 0 | 0 |
| J passes | 3 | 2.0 (0.49 + 0.46 + 1.05) |
To 5 a day: 5 more J legs (~47 more reads at 10.7 %, ~170 more stores); those 47 reads would bring ~8 lucky passes at the measured
no-edge rate (17.9 %): more luck than legs. The one-position stack of the passes (brief s7) was never run. Per hour of running: 2.0 trades a day in 12 hours, all from reads made 06:19-07:19 and counted after the 08:30 bar change.

### i) Test-month budget
Sep 2025 / Jan 2026 / May 2026 have been read ~241 / ~231 / ~231 times across all routes (this hunt 28; old taught walk-forwards 150;
blueprint test reads 32; others). And the 11 earlier test months (Jan 2022 .. May 2025) are not blind either: they sit inside the old
build days (2021-09-22 .. 2025-06-30) where ideas 1, 2, 6, 7, 9, 17 and 27 were first found. Only forward days from about 2026-10-15
are untouched. Shadow days are the only clean evidence left.

### j) In-sample leads across many rules
- Overnight side (09:30 open's third of the 01:00-09:30 range): with-side trades win +2.1 points more than against in 51 of 61 NQ
  stores (+1.5 without ORB ideas); keeps ~36 % of trades. Broadest filter lead on file; filters cannot run on the 3:1 route yet.
- Wide stops: own x2 at 2R is positive in 80 % of store-groups; own beats ATR at the same multiple in 70 % of 1,200 pairs.
- NQ 15m bars beat 5m (margin +1.41 vs +0.03; 15 of 17 pairs); 1m worst. NQ nyam and mid fine, pm weak; every night group loses.
- ES has NQ's edge before costs (+0.020 R vs +0.021 R) but costs turn it to -0.043 R. GC is negative before costs.

### k) Loose ends
- Brief's ideas 3, 4, 8, 9, 13, 14, 15: 20 specs still unrun, queued behind newer ideas; Amendment A's stage order was broken without an
  amendment (batch 3 ran before 14 stage-1 stores). Mostly harmless (6 of 7 look dead) except idea 9.
- Amendment C (batch 2) is only a comment in make_specs.py, not in PREREG_HM40.md. STATUS.md stale since 23:12.
- The shifted block layout question: never answered by the owner; withdrawn by me in Amendment G.
- Flipped: the +3 cushion (owner, Amendment J, after 25 reads); the overnight-side filter (lead at 23:51, shelved 07:43).
- Slips that touched a test month: idea 27's test numbers written in the vault LOG before its grade; Amendments E/F/G steered by test
  losses; the research workflow's judges knew outcomes ("0 of 21"); two failed oos jobs re-run against Amendment D (no read doubled).
- Idea 27 (2 reads) and idea 17 15m (1 read) are still ungraded (their random controls were pushed back by worse-fills jobs).

### l) Time audit (12 h)
Plumbing and notes ~4.3 h (36 %); the edge question ~6.3 h (52 %); the discarded old lane ~0.8 h. 28 of 100 in-sample runs led to a
pick; 34 only closed an idea; 38 changed nothing yet. ~22.7 of 31.4 logged job-hours produced no pick. Work that changed nothing: the
old lane, rv_fade (block + 10 stores), batch 3 (ES/GC, 0 chosen), ideas 19-20, idea 31.

## 3. Decision: ASK THE OWNER

On this path the goal is not getting closer, and the next step needs his word (it changes what counts as evidence or the goal itself).
Continuing the funnel (more stores -> picks -> reads) is expected to add lucky passes faster than real legs (h, g), on test months that
are spent (i). KEEP GOING unchanged is ruled out.

**Options for the owner** (the method changes either way; the critic, re-deriving the numbers, points the same way):
1. **One stack, judged once, forward (recommended).** Stop the one-pick-per-store test-month reads (28 coin flips that cannot tell edge
   from luck). Write ONE stack now from the in-sample zone only, by one rule for every idea: NQ New York, 15m bars, breakout / trend
   rules, wide stops (ATR x2 or own x1-2), 1.5-2R targets, most boxes positive, positive from 2024-10 -- 8-12 rules adding up to 5-10
   trades a day. Port them like the 3 shadow rules and judge the whole stack ONCE in shadow (no money) on days nobody has read, with the
   bar fixed before the first day. Honest catch: at ~$1,600 of swing a trade, even 3 months of 10 trades a day cannot prove a +$40-80
   edge; it shows a broken stack fast and a real one slowly.
2. **Accept what the numbers allow for now.** Keep the 3 Amendment-J rules in shadow (2.0 trades a day; SHADOW_BAR), drop the 5-10-a-day
   target until forward days say more. 0 honest legs exist; reaching 5 a day this way needs ~47+ more reads with ~8 lucky passes.
3. **Make the bar strict again, then decide.** Put back +3 and require the Monte Carlo per leg (money in 90 % of runs, positive with
   winners -15 %) and count luck at ~18 % a read. Under that bar 0 of 28 pass today; the 3 shadow rules would be labelled unproven.

**Expected result and the other way:** if the owner picks 1 or 2, I expect the first month of shadow to show the ports match the backtest
and the results to be noise-level (+/- a few thousand). If instead a rule clearly breaks (below SHADOW_BAR's stop line), it is switched
off; if all look fine, nothing is proven yet and the run continues to the pre-set read. Both outcomes lead to "keep the forward test
running", so no extra test-month run is queued now.

Until he answers: no new pick, no new test-month read (HOLD_PICKS stays). The queued in-sample runs of the brief's own ideas may finish
(they read no test month). The 3 shadow rules go ahead as he asked.

## 4. Lists

**Keep doing:** pre-register before any run; one read a store, every read logged; exact parity before a rule goes to the Desk (405/405,
325/325, 807/807 trades identical); independent skeptical reviews (they caught the 15:55 flatten bug and the oos quoting bug); cheap
in-sample-only studies across all stores (side study, exit shapes, costs) -- they taught more per hour than any read.

**Stop doing:** adding selection rules right after test failures; reading more test months at a 12 % pass rate against a ~17 % luck rate;
building a block before a cheap in-sample gross check (rv_fade: block + 10 stores, 0 chosen); ES / GC copies of NQ rules (costs eat ES,
GC negative before costs); night sessions (all lose); writing a test number anywhere before its grade.

**Try again (failed for a fixable reason):** the random line (P3) matched in trade count, so it is a real 95 % line; the overnight-side
filter as one gate written in advance for every idea (needs filters on the 3:1 route); idea 9 noise_long (5 chosen, 3 specs unrun);
idea 27 overnight-range ORB judged on forward months only (its test months are seen).

## Shadow bar
Written at 09:20 ET, before any shadow day: SHADOW_BAR.md (fidelity >= 90 % of days, a stop line at test average - 2 SE, one read at
26 weeks: net > 0 also at +1 tick, win rate >= own break-even). A pass there means "not contradicted", not "proven".
