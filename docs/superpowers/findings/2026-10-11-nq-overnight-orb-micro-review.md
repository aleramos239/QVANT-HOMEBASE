# Review: NQ OVERNIGHT ORB (micro), before any account (2026-10-11)

Frozen copy: `~/.homebase/desklab/nq_overnight_orb_micro.json` (draft `nq_overnight_orb_micro`, promoted 2026-10-11 from run
`20261011-004831-draft_nq_overnight_orb_micro-e639`). On the Desk: switched OFF, no account. Reads NQ, trades MNQ, sizes its own orders.
Backtest read: build days only (2021-09-22 to 2025-06-30). The unseen days (2025-07-01 on) are NOT read.

| # | Check | Result |
|---|---|---|
| 1 | Look-ahead | PASS |
| 2 | Repainting | PASS |
| 3 | Overfitting | NOT PROVEN |
| 4 | Sizing and risk | PASS for paper, WARNING for Lucid 50K |
| 5 | Live-readiness | PASS for paper, 5 items before a funded account |
| 6 | Funnel | PASS |

## 1. Look-ahead: PASS
One signal, walked end to end:
- Daily yardstick A: `ctx.daily` holds the daily bars BEFORE the trade date only (tester `runner.py`: `dailies[:bisect_left(daily_dates, d)]`; runner `host.daily_bars`: `x < d`). The last 100 of them, the same in the tester and live.
- Overnight range: 15-minute bars that START before 09:30 (`start_ns < open_ns`), all closed.
- Side of the day: the OPEN of the 09:30 bar, read when that bar has closed (09:45).
- Opening range: that same closed bar's high and low.
- Signal: `on_bar` gets a bar only at its close. ADX uses today's closed bars up to that one.
- Entry: a market order placed at that close; it fills on the first print after the placement delay. Stop and target are measured from the signal close and moved to the fill.

## 2. Repainting: PASS
Nothing is read from a bar that is still forming. Every decision is taken once, at a bar close; the day's side is fixed at 09:45.

## 3. Overfitting: NOT PROVEN
- The rule is the video's as taught (Conti, A0G14JYYVTk): stop 0.3 x A, target 3 x the stop, ADX above 20. None of it was tuned here.
- Two readings of "first entry" exist (10:00 and 10:30) and two risk amounts (1,000 and 1,250): four numbers were seen on the build days. Pick before the unseen days are read.
- 2025 is weak: 54 trades, +$2,570, profit factor 1.15 (2022-2024: 1.68 to 1.73).
- It has not been through the pipeline's gates; it came through the taught lane. Eval odds on LucidPro 50K within 30 days: 42 to 47 % plain, 27 to 31 % with the "live is worse" row.
- No out-of-sample read exists. Treat every number as in-sample.

## 4. Sizing and risk: PASS for paper, WARNING for Lucid 50K
- Size = risk / (stop points x $2), rounded down, 1 to 10 micros. In the backtest at $1,000: 2 to 8 micros, most often 4 to 6.
- Worst trade -$1,005; worst open loss $998. The stop does what it says.
- WARNING: one stop is half of a $2,000 trailing drawdown. Two stops in a row end the account. Worst losing streak in the backtest: -$4,606. This is an eval-odds bet, not an account that survives the whole history.
- When 1 micro alone risks more than the amount (a stop over 500 points at $1,000), it still trades 1 micro. Never met in the backtest (largest stop 238 points = $476).
- The size set on the account is the most the Desk sends. Set it to 10, or trades are cut down to it.
- Bracket: the stop and target go out with the entry and are held at the broker. They are MOVED to the fill afterwards (a modify). A modify that the broker refuses is the known weak spot (finding 2026-10-09): prove it on demo.

## 5. Live-readiness: PASS for paper
- Flat at 15:30, before Lucid's 16:10. PASS.
- Hold time: shortest 128 s, median 4 hours. No trade under 60 s. Not micro-scalping. PASS.
- One trade a day, one side. No hedging. PASS.
Before a funded or live account:
1. Its window starts at 00:00. A runner restart after midnight means that day runs in shadow only: no order on the account that day.
2. Settings can be changed only after 15:30 on weekdays, or at the weekend.
3. Stops are NQ levels sent to MNQ. The two prices can differ by a tick or two; the stop is moved to the MNQ fill, so the distance is right. Watch the first fills.
4. Half days (2026-11-27, 2026-12-24): the Desk's 15:30 flat is after the 13:15 close. Switch it off on those days until the half-day guard exists.
5. Never on the same account as nq930 (the Desk refuses it).
6. Fees: the backtest used $1.00 a micro round turn. Check it against the real fee of the account.

## 6. Funnel: PASS
380 trades in 44 months: about 8 a month (4 to 14).

## Verdict
Safe to run on a PAPER account, with the account's size set to 10. Not for a funded or live account until the unseen days are read once
(owner's word) and the demo step has shown the moved bracket on MNQ.
