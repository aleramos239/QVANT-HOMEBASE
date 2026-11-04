# Strategy review: draft_nq_930_against_on (NQ 9:30 stop against the overnight move, 1-min cancel, 22 / 10.25)

File: `~/.homebase/strategies/nq_930_against_on.py`. Heading to Apex 300K group g4, in FVG side 0.75R's place on PAAPEX...26 at $2,000 risk.
Rule: 09:30:00 price vs the 18:00 ET open; up overnight = one sell stop 5 pts below, down = one buy stop 5 pts above. Stop 22,
target 10.25. Unfilled at 09:31:00 = cancelled (owner, 2026-11-01). Flat 15:55. One trade a day.

Parity: in-sample run `20261101-231818-...-4c7e` = 714 trades, identical (date, side, entry, exit) to the research run c968's
trades that filled within 1 minute. Latest fill 0.99 min after 09:30.

## 1. Look-ahead: PASS
The overnight open is the first 1-minute bar's open (known at 18:00). The anchor is the last print before 09:30:00. Nothing reads
a later price.
Live concern: if the runner starts or restarts after 18:00 without replaying the evening, `on_open` becomes the first bar it sees
and the side can be wrong. The Lab runner's catch-up replay must cover from 18:00; check the hosted state on the first day.

## 2. Repainting: N/A
Tick-driven stop order, no indicator.

## 3. Overfitting: FAIL (thin edge, picked after the test months were seen)
- Three numbers (offset 5, stop 22, target 10.25) are the owner's, not tuned.
- The side (against) was picked after all four sides' test months were read. The 1-minute cancel was picked after seeing fill
  time vs result on in-sample AND test months. No blind months are left.
- The edge is about 0.65 pts a trade before commission (in-sample 0.50, test months 1.11). Full-sample t is under 1 at every size.
  The real-or-luck t >= 2 line fails.

## 4. Sizing and risk: CONCERN (costs)
- $2,000 risk at 22 pts = 45 MNQ. Apex per-trade limit is $2,250: OK, but a 9:30 stop fill can slip several points.
- Apex costs (MNQ $1.04, NQ $3.98 a round turn), per trade, full sample (956 trades):

| Size | Avg pts | Net | t | +1 tick worse |
|---|---|---|---|---|
| 45 MNQ | +0.13 | +$11.4k | 0.28 | -$10.1k |
| 4 NQ | +0.45 | +$34.7k | 0.94 | +$15.6k |

  In-sample alone, 45 MNQ is -$1.4k (breakeven). Micro commission eats most of the edge; minis cost a third as much per point.
- Brackets go with the entry (stop_entry with sl/tp, `move_brackets_to_fill`).

## 5. Live-readiness: PASS with notes
- Flat 15:55, before Apex's cut-off.
- The group's hedge block covers g4: if ORB (...24) or another member holds the opposite side at 09:30, this trade is skipped.
  The backtest does not model that.
- Holds are minutes, not seconds: no microscalp issue.

## 6. Funnel: PASS
About 714 trades over 939 in-sample sessions (~3.8 a week).

**Verdict:** the code is safe to run. The money case is thin. On micros at Apex commission it is breakeven in-sample and loses at
one tick worse; on 4 NQ minis it holds a small edge. Owner to choose the size before it goes on ...26.

## Addendum: offset 3 (owner, 2026-11-01)
Full sample (walk-forward ab06, test months read once): 1,046 trades, 71.4% full target; 4 NQ +$62.8k (t 1.65), +1 tick +$41.9k;
45 MNQ +$40.4k. Test months alone 70.6%, 4 NQ +$10.2k. Years 2022-2024 are each slightly negative (3 of 6 green), so the
4-of-6-years line fails. The Desk copy still defaults to offset 5.

## Addendum: on the Desk at 17 NQ (owner, 2026-11-01: "17 minis anyway")
Trades NQ minis (exec_root removed: $68 a round turn at 17 vs $177 for 170 MNQ). In-sample at 17 NQ, $3.98: +$223k, max drawdown
-$168k. Owner overrode concern 4 knowingly: Apex open-loss cap $2,250 is crossed on 55 % of trades; one stop-out is about the
account's whole $7,500 trailing drawdown.
