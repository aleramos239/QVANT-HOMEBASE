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

## As built (2026-10-13)

**One runner, three rule files.** LIVE, WR and PAYOUT are profiles of the same idea runner (`pipe_rules.PROFILES`).
`templates/pipeline_payout.json` is the LIVE file with the win-rate lane as a label on every card, which makes the eval odds
of ONE strategy a label: an idea is asked only for money after costs on the build days with enough trades, its code and price
checks, and money on its one read of the unseen days. The switch (`pipe_switch.py`, `bp.py pipe mode`, the Lab's Pipeline bar):
Off / Live / WR / Payout, one at a time or none.

**The lock** (the owner: "if its disabled, it cant be used by me or claude until i renable it"). The payout pipeline is disabled
unless `payout_enabled` is in the pipeline root. Disabled: it cannot be chosen, `bp.py pipe payout` runs nothing, the runner does
none of its work, the Lab page shows one Enable button. Only the Lab page's buttons post enable / disable; no chat tool reaches
them. It ships disabled.

| Module | What it does |
|---|---|
| `pay_rules.py`, `templates/payout.json` | Every number of the set: the slots, the pool's bar, the score (12 and 4 weeks, days in runs of 5, `max_bust` 50 %), size steps, day rule grid, rotation grid, proof (`keep` 50 %), firm rules, what follows a payout. |
| `pay_accounts.py` | `<root>/payout/accounts.json`: the Desk's funded accounts, size from the first balance, rule file by firm (`assumed` until the owner says), balance and peak from the Desk's daily record. |
| `pay_pool.py` | Members = ideas with a picked box whose trades are entered AND closed inside one slot (80 %, 200 trades, money after costs). Options = the pick and the middle box of each other target kind. An idea whose read FAILED is out (final). |
| `pay_score.py` | The walk past the first payout, from each account's balance, open losses counted, Apex's intraday floor on the friendly side; the group on the same drawn days. |
| `pay_build.py` | The search slot by slot, a size judged with its neighbours, the survival cap, what each member adds, reserves, the rotation rule kept only if it and its neighbours beat no rule; the group score, the "live is worse" row, the unseen-days score and PROVEN; `set.json`, `score.jsonl`, notices. `idle()` is the runner's call while its queue is idle. |
| `pay_rotate.py` | "In form" = a lookback-day equity high within the last days, read from the days before only. The evening read (`tonight.json`) and a notice when what trades changes. |
| Lab > Payout | The lock, the set by slot, tiles, the score at each build, tonight, accounts, caveats; Build, Send the stopped ideas round again (two presses), Disable. |
| `deploy/payout-review.md` | The AI step's instructions. NOT scheduled: the pipeline is disabled. |

**First build on real data (scratch copy, 2026-10-13):** 17 members, all but one in the New York slot, none for the evening.
$772 a week expected across the 7 accounts on the build days, $215 with worse fills, NOT PROVEN (a member has no read yet).
Most ideas stopped at stage 1 on the old single-strategy eval-odds line; `bp.py pipe payout requeue` sends them round again
under the payout rules once the owner switches it on.

## Not built

- The Desk does not trade a set by itself: a notice says what to switch and the owner switches (his word).
- Forward results after an idea's read: the evening rotation reads what is on file (build days, then the unseen read). Daily
  results need the set running in shadow on the Desk.
- A random-entry control for the set; Apex's 30 % open-loss rule and half size; the true intraday high (stores keep no trade high).
- The Mac mini move.

## Open, the owner's to decide

- **Apex bans automation on funded (PA) accounts.** `research/prop-portfolio/2026-10-01-l2/APEX300_RULES.md`
  row A1 (Apex's help centre, read 2026-10-01): AI, bots, algorithms and hands-off trading are prohibited;
  the penalty is closure and forfeiture. The same file: no orders on both sides (straddles), a stop at most
  5x the target, no opposite positions across accounts, the same size through a payout cycle, an open loss
  at most 30 % of the profit. Six of the seven real accounts are Apex. The set builder applies the both-sides and 5:1 rules to
  every Apex account and runs one set on all of them; nothing here places an order.
- Lucid's view of automation on funded accounts is not on file.
- The unseen days wear out: each locked set reads them once. Live and shadow results become the judge.
- Conti's method leans on end-of-day drawdown. With open losses counted, the no-edge ceiling was about 40 %.
