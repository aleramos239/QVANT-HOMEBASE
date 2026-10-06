# Strategy blueprint — from an idea to something worth running

**HOUSE LAW since 2026-10-05 (owner: "lets lock this into the app … i want all strategies or strategy buildings to go off this").**
Version 1.0. Every strategy that is built, tested, optimized or judged — in the research engine or in the Homebase tester, by a
person or by an assistant in any chat — follows section 2. It replaces the admission rules, the periods and the round count of
`EDGE_SPEC.md` (see its "ADMISSION v3"). Changing a line here needs the owner's word.
Not yet built to match: `judge.py` still scores the old rules (v2), and the Homebase tester's default dates are still 2021-2024.
Until they are updated, the requirements of section 2 are checked by hand and a v2 verdict is not a blueprint verdict.
Evidence: `out/blueprint/gate_backtest.md`, `protocol_gates.md`, `mc_gates.md`, `funnel.md`, `course_review.md`,
`out/v2_summary.md`, `out/oos_summary.md`, `out/overfit8/OVERFIT_CHECK.md`. Dollars are 1 contract after costs.

## 1. The phases at a glance

> **A good backtest is a lead, not proof. Proof is passing days the strategy has never seen.**

| Phase | Days used | What it answers | Passing it gives |
|---|---|---|---|
| 0. Idea card | none | Why should it make money, and who loses? | Permission to test |
| 1. Code check | build days only | Does the code do what the card says? | Numbers that can be trusted |
| 2. Build | 22 Sep 2021 → 30 Jun 2025 (45 months, 75 %) | Is there anything here at all? | **LEAD** — approved for the out-of-sample test |
| 3. Freeze | – | – | Nothing may change after this |
| 4. Out-of-sample test | 1 Jul 2025 → latest complete session, Sep 2026 (15 months, 25 %), one read | Does it hold on days it has never seen? | **PROVEN ON HISTORY** — approved for a real eval |
| 5. Before the eval is bought | the test-period trades | Is the account worth buying? | The eval, with its attempts and fee budget |
| 6. The eval | live | Do real fills and results match the test? | **PROVEN LIVE** |

## 2. Written requirements for each phase

A phase is passed only when **every** line is true. Variants = the standard exit table (8 stops × 4 targets) × the 3-4 values of
the idea's main setting. Random tables = the same exits, session and days with random entries: 4,000 draws from 10 seeds.
Reshuffled runs = 1,000 Monte Carlo histories: whole days drawn with replacement, the same days for every variant.

### Phase 0 — Idea card (written before any run)
| # | Requirement |
|---|---|
| 0.1 | The reason, in one sentence: why it should make money and who is on the losing side |
| 0.2 | The rule: one entry trigger, at most 2 filters, exits from the standard table only |
| 0.3 | Its home: market, session and bar size (or "all" when the reason does not single one out) |
| 0.4 | Where else it should work (its neighbors), and one place it should NOT work |
| 0.5 | The main setting and its 3-4 values |
| 0.6 | Whether it trades both sides or one side only, and why |

### Phase 1 — Code check (on build days only; never on the test period)
| # | Requirement |
|---|---|
| 1.1 | Every trade is entered inside the stated session window |
| 1.2 | One position at a time, and every trade is flat by 15:58 ET (13:13 on half days) |
| 1.3 | The number of trades is what the rule implies (for example, never more than the stated maximum per day) |
| 1.4 | With a stop and a target on, winners pay about the target and losers cost about the stop, in dollars; exceptions are listed |
| 1.5 | 10 trades are looked at on the chart (the first 5 and 5 at random): entry and exit sit where the rule says. *(10 is my number; the course gives none)* |
| 1.6 | After any change to the code, the earlier trade list is reproduced exactly before a new run counts |

### Phase 2 — Build, 22 Sep 2021 → 30 Jun 2025. Approved for the out-of-sample test when all of these are true
| # | Requirement | The number |
|---|---|---|
| 2.1 | Most settings make money | more than 60 % of variants profitable |
| 2.2 | The average trade is big enough (net of all variants ÷ their trades) | NQ $70 · ES $75 · gold $140 or more |
| 2.3 | It beats random entries with the same stops and targets | above 95 % of random tables in round 1; 97.5 %, 98.3 %, 98.75 %, 99 % in rounds 2, 3, 4, 5 |
| 2.4 | Enough trades (average variant) | 200 or more |
| 2.5 | Its neighbors agree: the same idea on the next bar sizes and in the other sessions it should fit | half or more of those tables profitable |
| 2.6 | Long and short each make money on their own (an idea that is one-sided by its card is judged on that side) | both above $0 |
| 2.7 | A filter is kept only if it wins alone: the plain version plus that one filter beats the plain version | higher average trade, and that round's random bar |
| 2.8 | Monte Carlo: it still meets 2.1 and 2.2 in most reshuffled runs | 75 % of the runs or more |
| 2.9 | Rounds | at most 5, each with its reason written before the run |

First look, not a pass line: the entry alone with a plain time exit (no stop, no target) against random entries. It is the same
question as 2.3 without the exits, so it is shown on the card and 2.3 decides.
Not passed after round 5 → shelved, with notes on what was tried.

### Phase 3 — Freeze (before the test period is touched)
| # | Requirement |
|---|---|
| 3.1 | Saved: the rule, the variant list, the default variant (the middle survivor, never the best), the control and the costs |
| 3.2 | From here nothing changes. A change is a new version: back to phase 2, and its earlier unseen read is marked as used |

### Phase 4 — Out-of-sample test, 1 Jul 2025 → Sep 2026, one read. Approved for a real eval when all of these are true
| # | Requirement | The number |
|---|---|---|
| 4.1 | Both parts make money on their own: Jul-Dec 2025 and Jan-Sep 2026 | average variant above $0 in each |
| 4.2 | The whole test: the average and the middle variant make money | both above $0 |
| 4.3 | The average trade is still big enough | NQ $70 · ES $75 · gold $140 or more |
| 4.4 | It still beats random entries | above 95 % of random tables |
| 4.5 | It still makes money with worse fills | 2 ticks + 250 ms (+ 100 ms late cancel for two-sided brackets) |
| 4.6 | It still makes money without its 3 best days | above $0 |
| 4.7 | Monte Carlo: it makes money in almost all reshuffled runs of the test period | 90 % of the runs or more (the course's line) |

Not passed → NOT PROVEN. It is not re-tuned and re-tested on this period.

### Phase 5 — Before the eval is bought (prop simulator, on the test-period trades, for the account in question)
| # | Requirement | The number |
|---|---|---|
| 5.1 | Both phases are run: passing the eval, and getting paid on the funded account, each at its own best size from the pre-set size steps | – |
| 5.2 | Both are read on a "live is worse" row, not on the plain backtest | win rate -5 points and winners -15 % *(the course's middle case; my pick)* |
| 5.3 | The odds are good enough to buy | The owner's bar of 2026-10-03, until he changes it: eval pass within 10 trading days 60 % or more; maximum payout within 20 trading days 75 % or more |
| 5.4 | Written on the eval card before the first eval: how many attempts, and the total fee budget | set by the owner for each strategy |

### Phase 6 — The eval
| # | Requirement | The number |
|---|---|---|
| 6.1 | Live equals the test, every day of the eval: each live trade matches the tester's replay of that day. A mismatch is a bug: it is fixed before the count goes on | same entry time, same exit reason |
| 6.2 | Stage A, the first days at 1 micro: fills are close to the test | average entry slip 2 ticks or less; no missed or rejected order |
| 6.3 | Stage A is passed after 5 clean trades *(my number)*; then the size goes to the simulator's size | – |
| 6.4 | Stage B, at size, read after 10, 20, 30 and 40 trades: drawdown against the Monte Carlo table of its own history | under the 75th percentile: carry on · at the 75th: cut size · at the 95th: pause and review |
| 6.5 | Stage B: after 40 trades the average trade holds up | at least half of history; otherwise pause and review |
| 6.6 | A pause is a review, not a deletion: has this happened in the test history, can it be explained, is it inside normal behaviour | three yes: resume · otherwise: retire |
| 6.7 | During the eval only the size may change, never the rule | – |
| 6.8 | A bust inside the drawdown table does not retire the strategy; running out of the attempts in 5.4 does | – |

## 3. What the stored tables say (run 2026-10-05, build years only, nothing sealed was opened)

Each gate was applied to 22 Sep 2021 - 2022 and scored on 2023, then the other way round. 1,875 tables.
"After" = the average variant made money in the other period.

| Gate in the first period | Tables passing | Profitable after | The other way round |
|---|---|---|---|
| No gate | 1,875 | 27 % | 28 % |
| **Heat map: over 60 % of variants profitable** | 315 | **48 %** | 47 % |
| Heat map: over 80 % | 100 | 48 % | 56 % |
| Over 60 % and Sharpe 1 or more | 125 | 50 % | 55 % |
| Over 60 % and half the idea's other tables also pass | 71 | 52 % | 62 % |
| **Over 60 % and average trade at the cost floor** | 82 | **66 %** | **71 %** (58 tables) |
| … and still both in 75 % of reshuffled runs (Monte Carlo) | 23 | 61 % | 88 % (8 tables) |
| Over 60 % and profitable in 95 % of reshuffled runs | 50 | 42 % | 53 % |
| Worst tenth of all tables by Sharpe | 188 | 7 % | 6 % |

**Dry run of the whole build checklist** on the stored tables (22 Sep 2021 - 2023; `funnel.md`):

| Line, each on top of the ones before | Tables left | Ideas left |
|---|---|---|
| All stored tables | 1,875 | 65 |
| 2.1 Over 60 % of variants profitable | 249 | 42 |
| 2.2 Average trade at the cost floor | 56 | 20 |
| 2.4 On pace for 200 trades | 28 | 11 |
| 2.6 Long and short each make money | 28 | 11 |
| 2.5 Half the neighbors profitable | 18 | 7 |
| 2.3 Beats 95 % of random tables | 6 | 3 |
| 2.8 Monte Carlo, 75 % of runs | 3 | **1** |

The one idea left is the midday range break on NQ (5, 15 and 30-minute bars). **It lost money the next year (2024), and lost to
random entries.** The three tables the Monte Carlo line removed: two failed 2024 as well, one (first-bar momentum NQ 15-minute)
lasted until 2026.

The old judge on real unseen years (already on file):

| Passed | Tables | Result on the next unseen year |
|---|---|---|
| Sep 2021 - 2023, including "beats 95 % of random tables" | 49 (non-event) | 2024: 43 % profitable; **8 (16 %) passed all three tests** |
| Sep 2021 - 2024 (the 15 saved) | 15 | 2025: 5 passed all three |
| Sep 2021 - 2025 | 5 | 2026: none passed |

In plain words:
1. **A majority-green heat map is a coin flip for the next year** (48 %). Greener is not safer. A high Sharpe is not either.
2. **The size of the average trade is the one build number that helped** (66 % and 71 %).
3. **Monte Carlo on the build did not change the hit rate** (about 68 % with it and without it). It makes the list much shorter.
4. **The whole build checklist leaves one idea out of 65, and that one failed the next year.** The checklist is strict; it is not
   proof. Only the unseen test decides.
5. **A good-looking table with no edge passes one unseen year about 1 time in 5** (13 of 69).

## 4. Where the course uses Monte Carlo

| When | What he reads | In this blueprint |
|---|---|---|
| Right after the first backtest (lesson 8) | 1,000+ reshuffled runs: the worst drawdown, and the share of losing runs (at most 10 %) | 2.8 |
| After each improvement (lesson 9) | The same run again, compared with the version before | 2.8, every round |
| On the build and on the test, separately (lesson 9 notebook) | The chance the edge is zero or less: under 5 % on the build is good, under 10 % on the test is the least | 4.7 |
| For size and for the live stop rule (lessons 9 and 3) | Drawdown percentiles after 10 / 20 / 30 / 40 trades | 5.1, 6.4 |
| For the prop account (lesson 10) | Odds of passing the eval and of getting paid, by size | 5.1-5.3 |

## 5. Why each rule is there

| Rule | Why |
|---|---|
| 1.1-1.6 Code check | Course, lessons 6-7: his own first runs were wrong on entry time, trade count and weekend holds. The rest of the blueprint guards against luck, not against a wrong test |
| 2.1 60 % green | A floor against one lucky setting. Not evidence of an edge (48 %) |
| 2.2 and 4.3 Cost floor | Course, lesson 8. The only build number that moved the odds. His floor is before costs; this one is after costs, so it is stricter |
| 2.3 and 4.4 Random entries | A rising, volatile market pays most exit tables. Only this separates the entry from the market |
| 2.4 200 trades | Owner, 2026-10-05, from the course's validation sheet. It shuts out ideas that trade about once a week (the release-day brackets had 141) |
| 2.5 Neighbors | The owner's rule: an effect in one session or one setting without a reason is rejected |
| 2.6 Both sides | Owner, 2026-10-05. Course, lesson 8: the short side erased about 35 % of the long side's profit |
| 2.7 Filter wins alone | Course, extra lesson: two-of-three filters gave the best number and was still rejected, because two of the three failed alone |
| 2.8 and 4.7 Monte Carlo | Owner, 2026-10-05, and the course. On the stored tables it did not raise the hit rate; it is kept as the owner's choice |
| 2.9 Five rounds, rising bar | Owner, 2026-10-05. The bar rises to pay for the extra tries |
| The 75 / 25 split | Owner, 2026-10-05: "75/25, like the course". Anything tuned on a day can no longer be tested on it |
| 4.1 Both parts | Owner: both must make money. It stops one good stretch from hiding a dead one |
| 5.1-5.2 Payout phase, worse row | Course, lesson 10: his example passed the eval 48 % of the time and qualified for a payout 14 % |
| 5.4 and 6.8 Attempts and budget | Course, lesson 10: at eval size 37-44 % of runs bust; a retry is expected (48 → 73 → 86 → 93 % over four tries) |
| 6.1 Live equals test | Course: the slip and drawdown lines only mean something if the live strategy is the tested one |
| 6.2-6.3 One micro first | Course, lesson 10. A tiny size cannot pass (3 micros: 0.7 %), so it only checks the plumbing |
| 6.4-6.6 75th / 95th, pause not delete | Course, lesson 3: the rule he states |

## 6. The splits considered

| Split | Build | Test |
|---|---|---|
| **Chosen: 75 / 25, like the course** | 22 Sep 2021 → Jun 2025, 45 months | Jul 2025 → Sep 2026, 15 months |
| 65 / 35 | Sep 2021 → 2024, 39 months | 2025 + 2026, 21 months |
| 80 / 20 | Sep 2021 → Sep 2025, 48 months | Oct 2025 → Sep 2026, 12 months |

A shorter test means a pass says less; one unseen year alone was passed by luck about 1 time in 5. Lines 4.1 to 4.7 and the eval
are what stand against that. To build in stages: tune on the first part of the build, look at the rest of it, tune once more, freeze.

## 7. What "optimize" means here (owner: stops and targets, and filters)

| What | Where it is tuned | Guard |
|---|---|---|
| Stops and targets | On build, the whole exit table is run; nothing is picked by hand. At the end, for each account, the stop and target are chosen from the surviving set (variants profitable on build, on the test and under worse fills) with the prop simulator | The strategy is judged on the average of all variants. The default is the middle survivor, never the best |
| Filters | On build only, one per round, reason first | 2.7: it must win alone. At most 2 in the final rule |
| The entry rule | On build only, as a round. A different trigger is a new idea | Counted |
| Size, daily stop, daily goal | In phase 5, with the prop simulator, from pre-set size steps | Changes the account odds, not the edge |

## 8. The Institutional Protocol — what is taken and what is not

Full list with lesson and line: `out/blueprint/course_review.md`.

Taken: one-sentence hypothesis (0.1) · check behaviour before results (phase 1) · cost floor (2.2, 4.3) · a consistent cluster, never
the best row (2.1, 3.1) · long and short read apart (2.6) · a filter must win alone (2.7) · Monte Carlo after the backtest and after
each change (2.8) · one split, 75 / 25, never overlapping · the chance the edge is zero, under 10 % on the test (4.7) · payout
phase, "live is worse" cases and retries (5.1, 5.2, 5.4) · live equals test (6.1) · one micro in the first days (6.2-6.3) · drawdown
percentiles, cut at the 75th and pause at the 95th, pause is not delete (6.4-6.6) · no manual interference (6.7).

Not taken: 5-10 years to build on (only 5 years are on disk; older history is parked) · choosing settings on all years up to today ·
building to the pass shape (small target, 60 % wins: his own example built that way failed the payout test) · idea-card line "when
it should lose" and the freeze list for indicators and order types (offered, not picked).

## 9. Honest odds

On the stored tables this blueprint ends where the current rules ended: nothing proven. Its build checklist leaves one idea in 65,
and that idea failed the next year. No testing formula creates an edge. It can only make a pass mean something and a fail cheap.
What raises the chance that something real comes out:
- **Ideas with a cause** (a scheduled event, a forced flow, a known loser on the other side) and a built-in control.
- **A big average trade.** Thin edges were the ones that died.
- **Real fills early** for anything fast. When more than half the profit sits in trades of 5 seconds or less, history cannot settle
  it: the card says FILL BET and 6.2 decides.

## 10. Still worth doing

a. **Idea intake before the next batch:** a short list of ideas with a cause, each with its card. The course's method: a paper, its
   claim in one sentence, the simplest tradable version.
b. **The 12 markets never tested** (YM, RTY, SI, HG, ZN, CL, NG, 6E, 6J, 6B, BTC, MBT) as neighbors (2.5), not as proof.
c. **Older history — parked (owner: not now).** Every archive on this Mac starts Aug-Sep 2021.

## 11. The owner's answers (2026-10-05) and what gets done on a yes

| Question | Answer | Where it sits |
|---|---|---|
| When does a strategy first trade a real eval? | when it is tested and passes the out-of-sample test | Phases 4-6; no paper wait |
| What does "optimize" cover? | Stops and targets, and filters | Section 7 |
| How long is an idea worked? | "lets do 5 rounds with a reason" | 2.9 |
| Two unseen tests or one? | "isn't it the same thing" | One: phase 4 |
| The split? | first "2024 in sample", then "75/25, like the course" | Phases 2 and 4, section 6 |
| The eight additions from the course? | "i like 8" | Phases 1, 2, 5, 6 |
| How specific? | "specific written requirements for each phase" | Section 2 |
| Entry alone and "beats random": the same? | "isnt 1 and 4 the same" | One pass line (2.3); the entry alone is a first look |
| Trades | "lets do 200" · "200 for everything" | 2.4 |
| Sides | "both long and short must be profitable" | 2.6 |
| The two test periods | "combine them but both must make money" | 4.1 |
| Monte Carlo | after the heat map it must still meet the requirements; and on the test too ("thinking of 2") | 2.8, 4.7 |
| More from the course | "Filter must win alone", "Live equals test" | 2.7, 6.1 |
| Older price history? | Not now | 10c |

| Make it law | "lets lock this into the app … if i type in a new chat to build or test an idea it will go based off this" | This file · `EDGE_SPEC.md` ADMISSION v3 · the `strategy-blueprint` skill · `CLAUDE.md` |

Never confirmed by the owner, so they stand as defaults: 5.3 (his 2026-10-03 bar) and 5.4 (set per strategy).

Done on 2026-10-05: `EDGE_SPEC.md` "ADMISSION v3", the vault rule note, the `strategy-blueprint` skill and `CLAUDE.md`, so that a
new chat follows this file. Still to build, in this order (each needs the owner's go-ahead):
1. The Homebase tester: build and test dates as the default ranges, the connector's instructions, and a checklist that reads
   section 2 off a heat map.
2. `judge.py`: build = 22 Sep 2021 - 30 Jun 2025 · lines 2.1 to 2.9 · the out-of-sample test on Jul 2025 - Sep 2026 as one read with
   lines 4.1 to 4.7 · labels on the cards. Locked by tests.
3. The code check as a tool: the assertions of phase 1 run on every new block or idea.
4. An eval card per strategy, filled from the desk journal: replay match, slip, the drawdown table, the average trade.
5. Then the waiting idea batch (`ideas/specs/r3_*.json`), each idea with its card first.

The 8 not-proven strategies have used up their history (every period is a second look), so they stay NOT PROVEN.
Only new unseen days or real fills on paper can change that.

## 12. Limits of the evidence
- The gate tests had 15 months to gate on, and the dry run 27, not 45.
- Tables of one idea share trades, so the counts overstate how much independent evidence there is.
- The pool held few or no real edges. The tests show how often a table with no edge passes each gate, not how well a gate finds a real one.
- The Monte Carlo result rests on 23 and 8 tables; the cost-floor result on 82 and 58.
- 2026 results were not used to set any line here.
- For a new idea Jul 2025 - Sep 2026 is unseen. For a close relative of the 15 saved strategies it is a second look and says less.
- The numbers marked "my number" or "my pick" (1.5, 5.2, 6.3) have no evidence behind them yet.
