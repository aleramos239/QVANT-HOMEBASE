# Strategy blueprint — from an idea to something worth running

**HOUSE LAW since 2026-10-05 (owner: "lets lock this into the app … i want all strategies or strategy buildings to go off this").**
Version 1.1 (2026-10-06: the owner's changes after the blueprint was held against the course line by line; section 11 lists
them and what was built for them). Every strategy that is built, tested, optimized or judged — in the research engine or in the Homebase tester, by a
person or by an assistant in any chat — follows section 2. It replaces the admission rules, the periods and the round count of
`EDGE_SPEC.md` (see its "ADMISSION v3"). Changing a line here needs the owner's word.
Built on 2026-10-06 (night): the toolkit `bp.py` runs every phase (`bp.py --help`; plan and decisions in
`out/blueprint/toolkit_plan.md`), and the Homebase connector offers it to every chat as nine `blueprint_*` tools that save each
idea in the app (`~/.homebase/ideas`, a Lab draft, a tester run, a Lab group per status). The tester's default dates are the build
days. `judge.py` still scores the OLD rules (v2) for the old stores: a v2 verdict is not a blueprint verdict.
Evidence: `out/blueprint/gate_backtest.md`, `protocol_gates.md`, `mc_gates.md`, `funnel.md`, `course_review.md`,
`out/v2_summary.md`, `out/oos_summary.md`, `out/overfit8/OVERFIT_CHECK.md`. Dollars are 1 contract after costs.

## 1. The phases at a glance

> **A good backtest is a lead, not proof. Proof is passing days the strategy has never seen.**

| Phase | Days used | What it answers | Passing it gives |
|---|---|---|---|
| 0. Idea card | none | Why should it make money, and who loses? | Permission to test |
| 1. Code check | build days only | Does the code do what the card says? | Numbers that can be trusted |
| 2. Build | 22 Sep 2021 → 30 Jun 2025 (45 months, 75 %) | Is there anything here at all? | **LEAD** — approved for the out-of-sample test |
| 3. Pick and freeze | build days only | Is the one variant that would be traded good enough on its own? | Nothing may change after this |
| 4. Out-of-sample test | 1 Jul 2025 → latest complete session, Sep 2026 (15 months, 25 %), one read | Does it hold on days it has never seen? | **PROVEN ON HISTORY** — approved for a real eval |
| 5. Before the eval is bought | the test-period trades | Is the account worth buying, for one strategy and for the portfolio? | The eval, with its attempts and fee budget |
| 6. The eval | live | Do real fills and results match the test? | **PROVEN LIVE** |

## 2. Written requirements for each phase

A phase is passed only when **every** line is true. Variants = the standard exit table (8 stops × 6 targets) × the 3-4 values of
the idea's main setting. Random tables = the same exits, session and days with random entries: 4,000 draws from 10 seeds.
Reshuffled runs = 1,000 Monte Carlo histories: whole days drawn with replacement, the same days for every variant.
The 6 targets: none, and 0.5, 0.75, 1, 2 and 3 × the stop: 48 cells, every cell counted like the others. The two small targets are
the owner's decision of 2026-10-06 (the course's prop lesson); in a table they sit behind the 32 cells of the old library.
Two levels (owner, 2026-10-06; the course reads its numbers on the one setting it trades): the lines of phase 2 are read on the
WHOLE TABLE (the heat map: is the idea real?), the lines 3.3 to 3.7 and 4.9 on the ONE variant that would be traded, the default
variant of line 3.1 (is this strategy good enough?).

### Phase 0 — Idea card (written before any run)
| # | Requirement |
|---|---|
| 0.1 | The reason, in one sentence: why it should make money and who is on the losing side |
| 0.2 | The rule: one entry trigger, at most 2 filters, exits from the standard table only |
| 0.3 | Its home: market, session and bar size (or "all" when the reason does not single one out) |
| 0.4 | Where else it should work (its neighbors), and one place it should NOT work |
| 0.5 | The main setting and its 3-4 values |
| 0.6 | Whether it trades both sides or one side only, and why |
| 0.7 | When it should lose: one stretch or kind of market in which the idea must lose money. A build without that loss is a red flag, and no filter is added only to erase it |

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
Shown on the card, never a pass line: Sharpe of the table, the win rate next to the break-even win rate of its stop and target,
the equity curve (the course gives no number for the last two).

### Phase 3 — Pick and freeze (on build days; before the test period is touched)
| # | Requirement |
|---|---|
| 3.1 | Saved: the rule, the variant list, the default variant (the middle survivor, never the best), the control and the costs |
| 3.2 | From here nothing changes. A change is a new version: back to phase 2, and its earlier unseen read is marked as used |

The variant that would be traded, the default variant of line 3.1, is read ON ITS OWN on the build days before the freeze is
written. The freeze is refused unless every one of these is true:
| # | Requirement | The number |
|---|---|---|
| 3.3 | The default variant has a healthy profit factor (its winning trades ÷ its losing trades, in dollars) | 1.2 or more |
| 3.4 | Its profit is large against its worst drawdown (its net ÷ its worst drawdown on closed days) | 3 or more |
| 3.5 | Its Sharpe is high enough (its result on every session day, per year) *(the owner's line; the course has none)* | 1 or more |
| 3.6 | Its worst drawdown fits the account at the smallest size: at 1 micro it stays under the drawdown limit of LucidPro 50K | under 2000 dollars |
| 3.7 | Monte Carlo on the default variant alone: it makes money in almost all reshuffled runs of the build days | 90 % of the runs or more (the course's line) |

Not passed → back to phase 2 as a new round when one is left (it counts), otherwise shelved.

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
| 4.8 | The test looks like the build: the average trade (the reading of 4.3) holds against the build's own average trade of line 2.2 | at least half of the build's |
| 4.9 | The default variant still has a healthy profit factor on the test days | 1.2 or more |

Not passed → NOT PROVEN. It is not re-tuned and re-tested on this period.

### Phase 5 — Before the eval is bought (prop simulator, on the test-period trades, for the account in question)
One strategy is read on lines 5.1, 5.2, 5.4 and 5.5. The portfolio, several proven strategies on one account with their days
drawn together, is read on lines 5.2, 5.3, 5.6 and 5.7 (owner, 2026-10-06: the 60 % and 75 % bars are the portfolio's).
Line 5.5 has no day limit: a run goes on for 250 trading days (the app's own horizon); a run still open then is neither a pass nor
a bust. A portfolio is read with each member's default variant, every member at the same size, on the test days they share.
| # | Requirement | The number |
|---|---|---|
| 5.1 | Both phases are run: passing the eval, and getting paid on the funded account, each at its own best size from the pre-set size steps | – |
| 5.2 | Both are read on a "live is worse" row, not on the plain backtest | win rate -5 points and winners -15 % *(the course's middle case; my pick)* |
| 5.3 | Portfolio: the odds are good enough to buy | The owner's bar of 2026-10-03, until he changes it: eval pass within 10 trading days 60 % or more; maximum payout within 20 trading days 75 % or more |
| 5.4 | Written on the eval card before the first eval: how many attempts, and the total fee budget | set by the owner for each strategy |
| 5.5 | One strategy: it is more likely to pass its eval than to bust it, and more likely to be paid than to bust the funded account *(my numbers)* | eval: a pass before a bust 50 % or more; funded: a first payout before a bust 50 % or more |
| 5.6 | Portfolio: every strategy in it has passed the out-of-sample test on its own, and no two of them are the same idea on the same market | – |
| 5.7 | Portfolio: a strategy is added only when it raises the portfolio's eval odds; one that lowers them stays out | – |

### Phase 6 — The eval
| # | Requirement | The number |
|---|---|---|
| 6.1 | Live equals the test, every day of the eval: each live trade matches the tester's replay of that day. A mismatch is a bug: it is fixed before the count goes on | same entry time, same exit reason |
| 6.2 | Stage A, the first days at 1 micro: fills are close to the test | average entry slip 2 ticks or less; no missed or rejected order |
| 6.3 | Stage A is passed after 5 clean trades *(my number)*; then the size goes to the simulator's size | – |
| 6.4 | Stage B, at size, read after 10, 20, 30 and 40 trades: drawdown against the Monte Carlo table of its own history | under the 75th percentile: carry on · at the 75th: cut size · at the 95th: the hard alarm (line 6.9) |
| 6.5 | Stage B: after 40 trades the average trade holds up | at least half of history; otherwise the soft alarm (line 6.6) |
| 6.6 | The soft alarm is a review, not a switch-off by itself: has this happened in the test history, can it be explained, is it inside normal behaviour | three yes: carry on · otherwise: stop until it recovers (line 6.9) |
| 6.7 | During the eval only the size may change, never the rule | – |
| 6.8 | A bust inside the drawdown table does not retire the strategy; running out of the attempts in 5.4 does | – |
| 6.9 | The hard alarm: the strategy is switched off, and no review turns it back on. A stop is not a deletion: it comes back when the tester's replay of the days since shows it has recovered | last 5 months positive · last 12 months positive · last 3 months above its long-run pace |

Optional (owner, 2026-10-06; the course, lesson 3): one week on paper before the eval, to check orders and fills. It may be
skipped, because stage A (lines 6.2 and 6.3) checks the same with 1 micro.

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

**Version 1.1, dry run of the new lines (2026-10-06; the same 1,875 stored tables, 22 Sep 2021 - 2023, nothing later opened).**
Read on each table's middle variant, without worse fills (the stored tables have none):

| New line | Tables it keeps, of the 56 that pass 2.1 and 2.2 | Of the 3 that pass every old line |
|---|---|---|
| 3.3 Profit factor 1.2 | 36 | 3 |
| 3.4 Profit ÷ worst drawdown 3 | 15 | 3 |
| 3.5 Sharpe 1 | 18 (nearly the same tables as 3.4) | 3 |
| 3.6 Drawdown at 1 micro under $2,000 | 56 | 3 |
| 3.7 Money in 90 % of reshuffled runs | 24 | 3 |

The new lines remove nothing at the end: still 3 tables, 1 idea. Line 2.8 is the stricter Monte Carlo: every table that passes it
also makes money in 90 % of the runs (13 of 13, read on the average variant). Nothing here says the new lines pick better; they are the course's reading of
one strategy, and the owner's.

## 4. Where the course uses Monte Carlo

| When | What he reads | In this blueprint |
|---|---|---|
| Right after the first backtest (lesson 8) | 1,000+ reshuffled runs: the worst drawdown, and the share of losing runs (at most 10 %) | 3.7, on the one variant that is traded, as he reads it. 2.8 is ours: the whole table, a harder question |
| After each improvement (lesson 9) | The same run again, compared with the version before | 2.8, every round; 3.7 before the freeze |
| On the build and on the test, separately (lesson 9 notebook) | The chance the edge is zero or less: under 5 % on the build is good, under 10 % on the test is the least | 3.7 on the build (at most 10 % losing runs: the owner's pick of his two numbers), 4.7 on the test |
| For size and for the live stop rule (lessons 9 and 3) | Drawdown percentiles after 10 / 20 / 30 / 40 trades | 5.1, 6.4 |
| For the prop account (lesson 10) | Odds of passing the eval and of getting paid, by size | 5.1-5.3 |

## 5. Why each rule is there

| Rule | Why |
|---|---|
| 0.7 When it should lose | Owner, 2026-10-06. Course, extra lesson: a drawdown the idea's reason implies is the premium, a backtest without it is a red flag, and a filter that only erases it is overfitting |
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
| 3.3-3.7 The one variant | Owner, 2026-10-06. The course reads profit factor, drawdown and Monte Carlo on the one setting it trades; the heat map only says the idea is real. Sharpe (3.5) is the owner's own line |
| The 75 / 25 split | Owner: 75 / 25, "so we have at least one full year for OOS" (2026-10-06). The course says 80 / 20, and not as a hard rule. Anything tuned on a day can no longer be tested on it |
| 4.1 Both parts | Owner: both must make money. It stops one good stretch from hiding a dead one |
| 4.8 Half of the build | Owner, 2026-10-06. Course, lesson 9: build and test are put side by side, and a large fall is the sign of overfitting. "Half" is my number |
| 4.9 Profit factor on the test | The course's floor of 1.2, read where it counts |
| 5.1-5.2 Payout phase, worse row | Course, lesson 10: his example passed the eval 48 % of the time and qualified for a payout 14 % |
| 5.4 and 6.8 Attempts and budget | Course, lesson 10: at eval size 37-44 % of runs bust; a retry is expected (48 → 73 → 86 → 93 % over four tries) |
| 5.3, 5.5-5.7 One strategy and the portfolio | Owner, 2026-10-06: the 60 % and 75 % bars are for several algos together; one strategy only has to be more likely to pass than to bust. Course, lesson 3: no stacking of the same logic on one market, watch the combined drawdown |
| 6.1 Live equals test | Course: the slip and drawdown lines only mean something if the live strategy is the tested one |
| 6.2-6.3 One micro first | Course, lesson 10. A tiny size cannot pass (3 micros: 0.7 %), so it only checks the plumbing |
| 6.4-6.6, 6.9 The two alarms | Course, lesson 3 (owner, 2026-10-06: "lets use his rule"): a hard stop at the 95th percentile that only a recovery ends, and a soft review with three questions when results run under pace |

## 6. The splits considered

| Split | Build | Test |
|---|---|---|
| **Chosen: 75 / 25** (the owner's; the course says 80 / 20) | 22 Sep 2021 → Jun 2025, 45 months | Jul 2025 → Sep 2026, 15 months |
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

Taken: one-sentence hypothesis (0.1) · when it should lose (0.7) · check behaviour before results (phase 1) · cost floor (2.2, 4.3)
· a consistent cluster, never the best row (2.1, 3.1) · long and short read apart (2.6) · a filter must win alone (2.7) · Monte Carlo
after the backtest and after each change (2.8, 3.7) · his numbers on the one setting that is traded: profit factor, profit against
the worst drawdown, the drawdown at one micro against the account (3.3, 3.4, 3.6) · one split, never overlapping · build next to
test (4.8) · the chance the edge is zero, under 10 % on the test (4.7) · payout phase, "live is worse" cases and retries (5.1, 5.2,
5.4) · several strategies: no doubles, each one must help (5.6, 5.7) · live equals test (6.1) · one micro in the first days (6.2-6.3)
· drawdown percentiles: cut at the 75th, the hard stop at the 95th that only a recovery ends, the soft review (6.4-6.6, 6.9) · no
manual interference (6.7) · his small targets, 0.5 and 0.75 × the stop (in the exit table).

Not taken: 5-10 years to build on (only 5 years are on disk; older history is parked) · choosing settings on all years up to today ·
the 80 / 20 split (owner: 75 / 25, for a full year of test) · designing an idea to the pass shape (60 % wins; his own example built
that way failed the payout test) · a week on paper as a must (optional: stage A checks the same) · the data step as a line of its
own (one tick vendor; not answered) · the freeze list for indicators and order types (offered, not picked).
Ours, not the course's: random entries (2.3), neighbors (2.5), the rising bar (2.9), worse fills (4.5), Sharpe (3.5).

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
| A look at the test days before the lock? | 2026-10-06: "Warn, then run if I say yes" | The EARLY LOOK: `bp.py test <name> --confirm --early-look` (`/test <name> oos`). It is labelled EARLY LOOK, uses the test days up for that idea and its relatives, and can never prove it |
| Quick commands | 2026-10-06: one command, "IS" for in-sample | The skill `test`: `/test <name> <is, oos, heatmap, mc, odds, status, all>` |

| The blueprint held against the course, line by line (2026-10-06) | "lets update the blueprint" | Version 1.1: lines 0.7, 3.3-3.7, 4.8, 4.9, 5.5-5.7, 6.9; 5.3, 6.4-6.6 reworded |
| The 95th percentile | "yeah lets use his rule" | 6.4, 6.9: the hard alarm; "sounds good add the soft alarm": 6.5, 6.6 |
| Small targets | "lets add 1:0.5, 0.75 for the RR heatmap" · counted "like every other box" | Section 2: the table is 8 stops × 6 targets |
| A week on paper | "lets add but make optional" | The note under phase 6 |
| The split | "i like the 75/25 so we have at least one full year for OOS" | Stays; the label "like the course" is gone |
| Monte Carlo on the build | "we should go by both" | 2.8 on the table, 3.7 on the default variant |
| Build next to test | "i like it" ($300 on build: $150 or more on the test) | 4.8 |
| When it should lose · profit factor and profit ÷ drawdown | "yeah lets add this" · "lets do it" | 0.7 · 3.3, 3.4, 4.9 |
| The drawdown bar's account | "lets use lucid pro" | 3.6 |
| Sharpe | "i really like sharpe … maybe just like a sharpe on just 1" | 3.5, his line |
| Eval and payout bars | the 60 % / 75 % bars are the portfolio's; one strategy: 50 % and 50 % ("yeah i like it") | 5.3, 5.5-5.7 |
| Where the numbers are read | the heat map stays; "we pick the box which is the median" | Section 2, the two levels |

Never confirmed by the owner, so they stand as defaults: 5.4 (set per strategy). Not answered: the data step of the course.

Done on 2026-10-05 and 2026-10-06: `EDGE_SPEC.md` "ADMISSION v3", the vault rule note, the `strategy-blueprint` skill and
`CLAUDE.md`; the tester's dates; the toolkit (`bp.py`: blocks, card, code-check, build, lock, test, sim, eval-card, status) and
its nine connector tools; the 12 random-entry control pools on the build days (`runs_bp/`).
Still to build:
1. The tester's own late-fill fields. (Built 2026-10-06: the toolkit in the Lab -- the sidebar's "Blueprint" list shows the ideas on file and
   every tool in phase order; a tool opens as a sheet with its inputs, Run and its answer. The chart service lists and runs THE
   SAME tools every chat has, `GET /api/tester/blueprint` and `POST /api/tester/blueprint/run`; it shows after one restart of
   the chart service.)
2. Runnable tester drafts: version 1 saves an idea as a RECORD in the Lab (card, settings, verdict), not as code the tester runs.
   Needed before line 6.1 can be checked against a tester replay.
3. What version 1 refuses: a home of "all", exits of its own and clock-time ideas. The evening session (18:00 the evening before the trade date,
   held to 15:58 of the trade date) and the family `va_reclaim` run under the blueprint since 2026-10-07 (owner's request).
   Two filters at once are built (owner's request, 2026-10-07; line 0.2 keeps its limit of 2): a card that names two filters runs the plain table,
   each filter alone and BOTH on; line 2.7 then asks each filter to beat the plain table AND the pair to beat the plain table and each filter alone
   (the course's lesson: a pair that wins while one of its two fails alone is rejected). Level 2 filters (NQ only) can be BUILT but not locked or tested (added 2026-10-06; the vendor's
   Level 2 history ends 2026-07-08 and the test days' table is not built: the owner decides how their test range ends).
   Added 2026-10-06 at the owner's request (`bp.py blocks` lists them): the entry trigger `fvg` (fair value gap), the four DELTA
   filter blocks (`delta`, `cumdelta`, `sweep`, `bigorder`: NQ, ES and GC, from the tick order flow; their test range ends where the
   flow file ends), the Level 2 filter blocks (`book`, `depth`, `ahead`, `wall`, `stack`) and, batch 1 of the price-and-trend blocks
   (`ema20`, `ema50`, `trend`, `vwap`, `avwap`, `vwma`, `channel`, `adx`, `rvol` and the strong RSI sides of `momentum`), and batch 2: the
   liquidity levels (`engine/levels.py`: prior day, overnight, Asia, early London 02:00-05:00, London, the evening before 20:00-24:00,
   5 days, the swing high / low: 50 5-minute bars each side, the latest one not yet traded beyond, read at the session's first decision, and on NQ the equal highs / lows: two such swings within 10 points, the second not beyond the first),
   the entry trigger `liq` (sweep or break of a level) and the filter blocks `level` (near / clear) and `swept` (with / against). Their definitions are the docstring of
   `engine/families/blocks.py` and `engine/families/fvg.py`. Batch 3 (first-guess definitions the owner reviews one by one, `engine/zones.py`): the
   filter blocks `pdz` (premium / discount), `ote` (62-79 % retracement zone), `htf15` / `htf60` (15- and 60-minute EMA trend) and `smt` (NQ against ES
   divergence; NQ and ES only).
4. Then the waiting idea batch (`ideas/specs/r3_*.json`), each idea with its card first.

Version 1.1, built on 2026-10-06 (toolkit and app, locked by tests):
- the card's line 0.7 (`loses_when`, also in the connector's card tool);
- the exit table of 48 cells (`engine/families/blocks.py` `menu_blueprint`: the 32 cells of the old library, then the 8 stops × the
  targets 0.5 and 0.75). A store that holds the old 32 is not run again: its missing cells are run and joined to it
  (`blueprint/runner.py` `_grown`, `_join`), which is how the 12 random-entry pools got theirs. The freeze refuses a home table
  that does not hold the whole table;
- lines 3.3-3.7 read on the default variant before the freeze, which is refused when one is not met; the lock keeps them and the
  build's average trade; lines 4.8 and 4.9 in the one read;
- phase 5: `bp.py sim` judges ONE strategy on line 5.5 (a walk without a day limit goes on for 250 trading days, the app's own
  horizon; line 5.3 is said for it, not judged), and `bp.py portfolio <name> <name> ... --account=ID` (connector:
  `blueprint_portfolio`) reads several proven ideas on one account on lines 5.2, 5.3, 5.6 and 5.7: each member's default variant,
  every member at the same size step, on the session days of the test period they share, in one ledger;
- phase 6: the two alarms on the eval card, and line 6.9 READ when the tester's replay of the days since the stop is sent with the
  fills (`replay_since_stop`); the app's idea store asks for 4.1-4.9 and 6.1-6.9.
Still open after version 1.1:
5. The two ideas built on the 32-cell table (`demo_range_break_nq`, `fvg_delta_nq`): their next build round runs the 16 missing
   cells and joins them; until then the freeze refuses them. Their cards have no line 0.7 yet: written again first.
6. Line 6.9 needs the tester's replay as an input: the tester cannot run a blueprint idea by itself yet (item 2 above).

The 8 not-proven strategies have used up their history (every period is a second look), so they stay NOT PROVEN.
Only new unseen days or real fills on paper can change that.

## 12. Limits of the evidence
- The gate tests had 15 months to gate on, and the dry run 27, not 45.
- Tables of one idea share trades, so the counts overstate how much independent evidence there is.
- The pool held few or no real edges. The tests show how often a table with no edge passes each gate, not how well a gate finds a real one.
- The Monte Carlo result rests on 23 and 8 tables; the cost-floor result on 82 and 58.
- 2026 results were not used to set any line here.
- For a new idea Jul 2025 - Sep 2026 is unseen. For a close relative of the 15 saved strategies it is a second look and says less.
- The numbers marked "my number" or "my pick" (1.5, 4.8, 5.2, 5.5, 6.3) have no evidence behind them yet.
- The lines of version 1.1 were dry-run on the stored middle variant of 27 months, without worse fills. They removed nothing
  after the old lines, so nothing says they pick better. More lines mean fewer survivors, not better ones.
