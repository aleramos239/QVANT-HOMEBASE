# The payout pipeline (design, 2026-10-13)

Owner's words: "set algorithms running and trading on my prop firm accounts getting me payouts", "an AI loop
that is constantly testing and building the portfolio 24/7", "mostly tune and rotate a small set how he
describes" (Matteo Conti, video uE-9nuKxkjI), "a strategy for each session and they will all work together".

## What it is

A third pipeline beside LIVE PIPELINE and WR PIPELINE. Those two ask "is this one idea real?" and stop an
idea at its first failed line. This one asks "which set of strategies should run on my accounts now?" and
never finishes: it keeps tuning, scoring and rotating a small set.

One switch in the Lab chooses which pipeline works: Off, Live, WR or Payout. One at a time, or none.

## The owner's decisions

| Topic | Decision |
|---|---|
| Goal | The maximum payout every week from the funded accounts, scored as ONE group. Some accounts may blow as long as the group ends in profit. |
| Accounts | 1 Lucid funded (LTF...0012) and the Apex 300K Legacy funded accounts (the Desk shows six: ...0021 to ...0026). No new purchases for now. |
| Drawdown | Open losses count on every account. |
| Approach | Tune and rotate a small set (Conti), not a hunt for new ideas. |
| Slots | One strategy a session: 20:00-00:00, 02:00-09:25, 09:30-16:00 ET. Flat before the next slot. |
| Judging | A strategy alone gets a light check (it drifts up after costs, enough trades, its worst open loss fits) and "what it adds to the set". The full scoring is on the set. |
| Main score | Expected payout a week across the accounts, over 12 weeks, with 4 weeks beside it. |
| Proof | Build days, then ONE read of the unseen days on the locked set, then real accounts. |
| Rotation | A fixed rule in code each evening (on while at a new equity high). A notice in Homebase; the owner switches. No action = the old set keeps running. |
| The AI | Reads results, writes what worked, picks the next tests. Never touches an account or the unseen days. |
| Markets, size, news | Every market, any size the firm allows, trade through releases; a news-day strategy is welcome. |
| Day rule | "Always trade" against "stop after a set gain or loss": whichever scores better, with its neighbours. |
| Evals | Later: the same pipeline with another score (pass within N days). Buying evals and asking for payouts stay with the owner. |
| Machines | Built and proven on the laptop. Live trading moves to the Mac mini when a set is ready. No VPS for now. |

Defaults taken where he did not answer (his to change): a Desk fault mid-session flattens that account and
leaves a notice; a group brake (pause everything after a set weekly loss) with the number left open; a short
daily note in Homebase; the long middle slot is tested with one strategy and with two.

## What is already there (found 2026-10-13)

| Piece | Where | State |
|---|---|---|
| Prop walks with open losses (eval, first payout) | `blueprint/propodds.py`, `homebase/backtest/propsim` | Works. First payout only, from a flat start. |
| Apex 300K Legacy funded, many payouts, start states, compliance checks, "five accounts" | `research/prop-portfolio/2026-10-01-l2/apex300.py` | Research code, not wired to the pipeline. |
| Portfolio builder (book strategies, unseen days) | `blueprint/pipe_portfolio.py` | Works. Bar = 60 % eval in 5 days, 75 % max payout in 14. |
| The mix on the build days | `blueprint/pipe_mix.py` | A proposal in code. |
| The refiner (one change a round) | `blueprint/pipe_refine.py` | New today. |
| Profiles LIVE and WR, a profile bar in the Lab | `blueprint/pipe_rules.py`, `lab.js` | Live. |
| Rule files | `homebase/backtest/propsim/rules/` | Lucid Flex / Pro 50K confirmed. Apex Legacy 300K (Apex's own pages) not confirmed by the owner. |

## What is new

1. **The switch**: Off / Live / WR / Payout. One works, or none.
2. **The group score**: every real account from where it stands today, many payouts, 12 weeks, the same
   drawn days for all of them, days drawn in runs (streaks stay together).
3. **The pool and the slots**: every idea that drifts up after costs on the build days, filed under the
   session its trades fall in.
4. **The tuner**: for each pool member, its stored boxes (stop, target), size and day rule, ranked by what
   the member adds to the set. A setting counts only with its neighbours.
5. **The rotation rule and the evening notice.**
6. **The Payout page in the Lab**: the set by slot, the score over time, the notices.
7. **The AI step**: a scheduled Claude task that reads the results and files the next tests.

## Build order

| Step | What | Done when |
|---|---|---|
| 1 | The switch | The Lab bar shows four choices; choosing one stops the others; tests pass. |
| 2 | Group score, Lucid funded first | One command scores a set on the Lucid account over 12 weeks with many payouts. |
| 3 | Pool, slots, tuner | The runner fills the three slots from the stored build-day boxes and writes the best set. |
| 4 | Rotation rule and notice | The rule is backtested on the build days; a changed set leaves a notice. |
| 5 | The Payout page | The set, the score over time and the notices show in the Lab. |
| 6 | Apex 300K in the group score | Needs each trade's high in the pipeline's stores, and the owner's decision below. |
| 7 | The AI step, then the Mac mini | The task runs a few times a day; Homebase runs on the mini. |

## Open, the owner's to decide

- **Apex bans automation on funded (PA) accounts.** `research/prop-portfolio/2026-10-01-l2/APEX300_RULES.md`
  row A1 (Apex's help centre, read 2026-10-01): AI, bots, algorithms and hands-off trading are prohibited;
  the penalty is closure and forfeiture. The same file: no orders on both sides (straddles), a stop at most
  5x the target, no opposite positions across accounts, the same size through a payout cycle, an open loss
  at most 30 % of the profit. Six of the seven real accounts are Apex. Nothing in steps 1-5 touches them.
- Lucid's view of automation on funded accounts is not on file.
- The unseen days wear out: each locked set reads them once. Live and shadow results become the judge.
- Conti's method leans on end-of-day drawdown. With open losses counted, the no-edge ceiling was about 40 %.
