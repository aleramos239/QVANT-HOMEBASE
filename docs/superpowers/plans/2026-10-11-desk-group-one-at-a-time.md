# A group of Lab strategies on one account, one trade at a time (2026-10-11)

Branch `feat/desk-group-one-at-a-time`. Not merged, nothing enabled, no account booked.

## Why

The sizing study of 2026-10-11 (vault finding `2026-10-11-desk-group-sizing-eval-half-in-30-days-bar-needs-30-strategies`) showed the Desk's
strategies pass a LucidPro 50K eval more often as a group than alone. The Desk refused a second strategy in the same market on an account.

## What was chosen, and what was not

**Chosen: the group shares the account ONE TRADE AT A TIME, first come.** A member whose entry arrives while another member's trade is open (or
its entry is working, or its orders are not checked yet) sits that trade out.

**Not built: several positions of one contract open together.** `Engine.on_fill` books a fill on the opposite side in a symbol as the live
round's exit, by symbol and side; the flatten, the carried-block check and "Clear" read the account's NET position in the symbol. With two rounds
open together every one of those would need the other round's expected position, and an exit fill without an order id could not be attributed.
That is a rewrite of the reviewed Lab section for no gain: on the stored runs, sizes tuned on the build days for each rule give

| LucidPro 50K no daily limit, plain row | eval in 30 days (build / unseen) | max payout in 20 days (build / unseen) |
|---|---|---|
| all positions together | 55 % / 46 % | 25 % / 19 % |
| one trade at a time | 62 % / 54 % | 28 % / 25 % |

One at a time is better because the members that lose together (the New York trend cluster) no longer hold positions together.

## The change

| File | What |
|---|---|
| `homebase/engine.py` `_lab_market_taken` | another LAB strategy in the SAME symbol no longer takes the market; everything else as before |
| `homebase/engine.py` `_lab_slot_busy`, `_lab_sits_out` | the broker account is busy while another member has a round there today that is placing, placed or live; that is not clean (orders not read terminal, "check it", a carried block); or that went in and was never SEEN out (a Kill). A Lab round whose strategy is no longer in the config holds it too. Two desk entries pinned to one broker account are one account. Sentence `LAB_SLOT_BUSY`. `_lab_open_round` re-asks it with no await before a round is opened, so two entries at once send one order |
| `homebase/engine.py` `flatten_today` | the global Kill sells a shared account's net in a contract ONCE: a member's round that is over and checked is left out when another member's round is open, or when a member's run already sold it in this pass. One Lab strategy alone: as before |
| `homebase/labdesk.py` `set_book` | two Lab strategies in the same symbol may be booked on one account |
| `homebase/labdesk.py` `_enter` | an entry EVERY account skipped for the group's turn is not counted as "untaken" (two untaken stop a strategy for the day) |
| `homebase/labrun/host.py` `_count` | ... nor toward the runner's three-refused-in-a-row stop |
| `homebase/labrun/door.py` | the sentence `SLOT_BUSY` |

## What the independent review found (all fixed, each with a test that fails without the fix)

1. The global Kill sold the account's position once per member state (a lagging position read = sold twice). Fixed in `flatten_today`.
2. After a restart, a member whose record did not load no longer held the account. Fixed: an orphaned Lab round holds it.
3. Kill one member, and its late fill could be booked as another member's exit. Fixed: a round that went in and was never seen out holds the account for the rest of the day.
4. Two desk entries on one broker account were two accounts to the group (true on main as well). Fixed for the group (`broker_key`).
5. One busy account hid every other account's refusal from the "untaken" count. Fixed: only an entry every account skipped is left out.
6. The sentence said "open" for a trade that needed a check. Reworded: "... is open or not checked yet."

## What stays as it was

- Before every entry the Desk reads the account's position in the contract: not flat, or not readable, and the account sits out.
- A micro and its full contract on one account (MNQ with NQ): refused. A Lab strategy next to a timer strategy (nq930, gc_nfp) in its market: refused.
- One strategy's Kill, Flatten and flat time act on its own round only; the account-wide emergency stays account-wide.
- A skipped trade uses no round, so it does not count against the strategy's trades a day at the Desk.

## Risks, said plainly

1. **A stuck member holds the whole group off that account** (a round that reads "check it", a carried block, a killed member whose position was open). Fail closed, and on purpose. After a Kill of one member that had a position, the group is off that account until the next day.
2. **A resting entry holds the account.** A member that leaves a stop entry working for hours keeps the others out. None of the six micro drafts does (all enter at the market).
3. **A late or duplicate fill push** that arrives after a round is over, while another member has since entered, would be booked by `on_fill` as that member's exit when it is on the other side. The same hazard exists today between two rounds of ONE strategy (a new round needs every order of the last read terminal first); a group does not shorten that wait.
4. **The daily match line** ("Matched the backtest") compares a strategy's day with the tester's. A day on which the strategy sat a trade out will read as a difference. Not changed.
5. **A strategy may count a skipped entry as one of its own trades of the day** (each draft's own code). The sizing study treated a skipped trade as gone, which is the same or more careful.
6. **Not proven on a real fill:** everything in `lab-micro-exec-and-own-size` still stands (MNQ contract lookup at the broker, the moved bracket on MNQ).

## The drafts (in `~/.homebase/strategies`, for the owner to promote)

Each micro twin is its original with `exec_root = "MNQ"`, `own_size = True` and a `micros` setting (1-10). Build days 2021-09-22 to 2025-06-30,
same entries, exits, sides and prices as the original, to the cent per micro:

| draft | default size | trades (original = twin) | twin net |
|---|---|---|---|
| `nq_overnight_orb_micro_v2` (risk menu 300 / 400 / 500 / 750 / 1000 / 1250) | $400 a trade | 380 = 380 (at $1,000: $77,932 = $77,932) | $27,050 |
| `nq_0300_candle_body_micro` | 4 | 522 = 522 | $20,362 |
| `nq_supertrend_nyam_short_micro` | 10 | 290 = 290 | $30,635 |
| `nq_donch_first_nyam_micro` | 1 | 905 = 905 | $16,309 |
| `nq_noise_gx_pm_long_micro` | 2 | 442 = 442 | $14,529 |
| `nq_noise_gx_mid_long_micro` (not in the one-at-a-time group; kept as a spare) | 2 | 703 = 703 | $14,567 |

The group of five at those sizes, one trade at a time, from the twins' own runs (build days): 2,002 trades, +$121k, PF 1.55, every year up,
eval in 30 days 62 %, max payout in 30 days 48 %.

## To go live (the owner's steps, not done)

Merge to main (main's checkout holds another session's uncommitted edit of `flatten_today` in `engine.py`, the per-account Flatten: it will conflict with this branch's change there and must be merged by hand, keeping both; that per-account Flatten also books rounds done at once, which the "never seen out" rule already covers), Desk restart behind the usual gates
(`desk_status` first, never 09:20-09:35 ET), runner restart, promote the five drafts, `strategy-review` on each frozen copy, then book all five on
ONE paper account with each account size at or above the draft's `micros`.
