# The stack's shadow bar (Amendment K; written 2026-10-21 ~16:45 ET, BEFORE any port, promotion or shadow day of the stack)

The stack = the 8 rules of STACK.md (20 Lab drafts: one per New York session instance), all in SHADOW on the VPS Desk, no money.
It is judged ONCE, as a whole (the owner: "judge the whole stack once in shadow on new days"). The per-rule numbers are shown, never judged.

## What the in-sample months say to expect (the 8 picked versions, NY sessions, 883 in-sample days)
| Trades a day | Average trade | Per-trade spread (sd) | Trades in 26 weeks (~130 sessions) |
|---|---|---|---|
| 9.0 | +$204 | $2,347 | ~1,170 |
In-sample numbers have NOT carried to test months in this hunt (CHECKPOINT_1 (b)): expect much less than +$204.

## The bar
1. **Day 1 of the stack** = the first session on which all 20 drafts are switched on in shadow. The read date = 26 weeks later.
   (Added 2026-10-21 18:15 ET, before any stack day exists: the 20 are switched on after today's close, on the MAC runner (the
   owner's choice: the VPS has no memory to spare). Day 1 = 2026-10-22, the first live session; the read = 2027-04-22. A replay of
   2026-10-21 that the runner may make at switch-on is shown, not counted.)
2. **Fidelity (each draft):** on >= 90 % of its shadow days the Desk's "Matched the backtest" holds (every shadow trade = the Lab backtest
   of the frozen code). A draft below 90 % after 4 weeks: its days do not count until the copy is fixed (said in the read).
3. **Stop (checked once a month, from 100 stack trades on):** the stack's average trade after costs is 2 standard errors below zero
   (t <= -2; at 100 / 300 / 600 / 1,100 trades: below -$469 / -$271 / -$192 / -$142 a trade) -> the stack is switched off, failed.
4. **Pass, read ONCE at 26 weeks:** at least 300 stack trades AND the stack's average trade after costs, with one more tick a side, is at
   least 1 standard error above zero (t >= 1; at ~1,100 trades about +$71 a trade) AND its win rate >= the break-even of its own
   realized reward-to-risk. Anything else: failed.
5. Shown with the read, not judged: each rule's numbers; the stack under the owner's account rule (one position per account, 5
   accounts: a signal skipped only when 5 are open); the stack's worst drawdown; the 3 Amendment-J shadow rules (SHADOW_BAR.md) apart.

## What a pass would and would not mean (said now)
At ~1,100 trades (one standard error = $71; the extra tick ~$10 a trade), a stack with no edge passes (4) about 13 % of the time; a
true +$50 a trade about 33 %; +$100 about 61 %; +$200 about 95 %. A pass is real evidence only for an edge of +$100 a trade or more;
a fail does not rule out a small edge.

## Stack B (Amendment L; written 2026-10-21 evening, BEFORE any port or forward day of stack B)
Stack B = 2 rules (4 Lab drafts nq_sb_*), in shadow on the Mac runner, judged ONCE on its own; the same rules as stack A's bar:
- Day 1 = the first session with all 4 drafts switched on in shadow (expected 2026-10-23); the read = 26 weeks later.
- Fidelity >= 90 % of each draft's checked days, judged from 4 weeks on. Stop (monthly, from 100 trades): t <= -2.
- Pass at the read: >= 150 trades AND the average trade after costs and one more tick a side is >= 1 standard error above zero (t >= 1)
  AND win rate >= its realized break-even. In-sample: 2.42 a day (~315 trades in 26 weeks), +$107 a trade; at that many trades one
  standard error is ~$87, so no edge passes ~13 %, a true +$107 ~54 %, +$200 ~89 %. A fail does not rule out a small edge.
- Day 1 of stack B = 2026-10-23 (all 4 on from its 18:00 session; on 10-21 at 22:09 the 3 evening-window drafts were too late for 10-22,
  the pullback draft's 10-22 day is shown, not counted). The read = 2027-04-23.

## Day tags (forward tests of in-sample leads; free: no copy changes; each read ONCE at the stacks' read dates)
| Tag | Rule (from the day's own prints, known by 09:30) | In-sample verdict | Forward bar |
|---|---|---|---|
| middle | the 09:30 open in the middle third of the 01:00-09:30 range | weak (Amendment M: 76 % all, 56 % second half) | Amendment M |
| flat open | the 09:30 open within the flat third of the signed gap vs the prior 16:00 close (cut points -0.105 / +0.163 of the 20-day daily range, frozen from the in-sample days; Note N) | weak: holds 80 % / 79 % by half but 1 of 6 features tried (~1-in-5 by chance), by year only 2022 and 2024 | PASS = over all shadow trades, other-day avg minus flat-day avg >= 1 SE (t >= 1) AND other-day avg > 0 AND flat days hold >= 20 % of trades |

(Added 2026-10-21 23:40 ET, before day 1: the flat-open tag is computed by `stack_report.py` (section 6) from the tape store with the frozen cut points above; checked against the study's own gap numbers on 30 recent days: all 25 comparable days agree, the other 5 are holidays / a missing prior close.)
