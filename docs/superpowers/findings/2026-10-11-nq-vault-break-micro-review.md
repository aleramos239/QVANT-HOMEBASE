# Review: NQ VAULT BREAK (micro), before any account (2026-10-11)

Frozen copy: `~/.homebase/desklab/nq_vault_break_micro.json` (draft `nq_vault_break_micro`, promoted 2026-10-11 from run
`20261011-110128-draft_nq_vault_break_micro-f414`). On the Desk: switched OFF, no account. Reads NQ, trades MNQ, 7 micros a trade.
Backtest read: build days only (2021-09-22 to 2025-06-30). The unseen days are NOT read.

| # | Check | Result |
|---|---|---|
| 1 | Look-ahead | PASS |
| 2 | Repainting | PASS |
| 3 | Overfitting | NOT PROVEN, one fragile point |
| 4 | Sizing and risk | PASS for paper, WARNING for Lucid 50K |
| 5 | Live-readiness | PASS for paper |
| 6 | Funnel | PASS |

## 1. Look-ahead: PASS
A = daily bars BEFORE the trade date only. The noise line is set from the 01:00 bar's open and never moves. The VWAP uses closed 1-minute
bars. The decision is taken at a 30-minute clock time from the last closed 1-minute bar; the order fills on the first print after it.

## 2. Repainting: PASS
Every decision is taken once, at a clock time, from closed bars.

## 3. Overfitting: NOT PROVEN
- The rule is the video's as taught; he says the 30 %, the cap of 3 and the dollar exits were optimised in sample. Our run matches his report
  (average win $717 / loss $1,190 at 1 NQ against his $740 / $1,205; win rate 66.8 % against 67.7 %). All 9 neighbour cells make money.
- FRAGILE: the first trade of a day makes nothing (375 trades, average $0). The profit is the 2nd and 3rd trade (244 at $121, 147 at $88, at
  7 micros), mostly re-entries after a target was hit. With 1 trade a day the strategy is flat; with 2 it makes two thirds of the profit.
- First entry at 11:30 instead of 11:00: $37 a trade instead of $55, and 2024 turns negative. He does not say which.
- 2024 is weak in every reading ($1,712 on 222 trades as promoted).

## 4. Sizing and risk: WARNING for Lucid 50K
- 7 micros: one stop $1,050, one target $560. Worst trade -$1,071, worst day -$2,124 (two stops). 19 of 375 trading days hold 2 or more stops.
- Two stops on one day end a $2,000 drawdown at 7 micros. This is an eval-odds bet: 33 % in 30 days at 7 or 10 micros (stress 18 % / 22 %).
- The size set on the account is the most the Desk sends: set it to 10.

## 5. Live-readiness: PASS for paper
- Flat 15:30. Median hold 48 minutes; 4 trades under 60 seconds (shortest 30 s). Not micro-scalping. Long only, one position at a time.
- Its window starts at 01:00: a runner restart after 01:00 means that day runs in shadow only. Settings change only after 15:30 or at weekends.
- Same open items as the first micro strategy: the MNQ bracket and its move to the fill are not yet seen on a real order; half days.
- Never on the same account as nq930 or the overnight ORB (one strategy per market per account).

## 6. Funnel: PASS
766 trades in 44 months: about 17 a month, on 375 of 941 days.

## Verdict
Safe to run on a PAPER account. Not for a funded or live account before the unseen days are read once (owner's word).
