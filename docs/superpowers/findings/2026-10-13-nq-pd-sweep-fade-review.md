# Strategy review: NQ Prior-Day Sweep Fade (`nq_pd_sweep_fade`) — 2026-10-13

File: `~/.homebase/strategies/nq_pd_sweep_fade.py` (Desk record `~/.homebase/desklab/nq_pd_sweep_fade.json`, OFF / shadow, no account).
Evidence read (no new backtests): build run `20261013-222727-...-81cd` (176 trades), unseen run `20261013-222830-...-abc4` (61 trades).

## 1. Look-ahead bias — PASS
- Signal is read only when five 1-minute bars of a 5-minute bucket have closed (`on_bar`, lines 94-102); entry is a market order after that close.
- VWAP (lines 91-103) uses bars up to and including the closed bar; ATR (`_atr`, lines 66-83) uses closed buckets only.
- Levels come from `ctx.daily[-1]` (prior tape session, finished by 08:15); the quiet filter compares it with the 20 sessions before it (lines 60-64). Nothing from today's session leaks in.
- Not provable from the file alone: that the LIVE `ctx.daily` row matches the tester's row. The shadow day on the Desk is the check.

## 2. Repainting — N/A
Python, acts on closed bars only; no Pine, no `request.security`.

## 3. Overfitting smell — WARN
- Tuned on build days: 2 ATR stop, target 0.5 / 0.75, VWAP side, quiet-day filter, 5-minute bar, level band 0 (about 5 choices).
- Two filters (inside the house "fewer rules" limit). ONE unseen read passed (n 61). The rule family had about 215 looks, so luck is not ruled out; win-rate error is about ±11 points at n 61.
- The 0.75 target was not the default; its unseen read is the same read (neighbour, not separately pre-registered).

## 4. Sizing and risk — FAIL (for 1 NQ), PASS at micro size
- Stop is 2 x ATR, so it is not capped in dollars. Unseen: median stop 66 pts (about $1,320 at 1 NQ), p90 124 pts, max 165 pts; worst loser -$3,304 (2026-02-17), then -$3,084 and -$1,969. Build: worst -$1,914.
- A single worst loser at 1 NQ is larger than the Lucid 50K drawdown ($2,000). The record carries `qty 1` on root NQ: it must be MNQ (about $330 worst) or an own-size rule before any account.
- Brackets: `ctx.market(..., sl=, tp=)` with `move_brackets_to_fill = True` re-prices the stop and target after the fill (a modify). Same mechanism the other Lab strategies use, but a disconnect between fill and modify leaves a position with the first prices. Confirm on a paper fill.
- Parity gap: the Desk record has `auto_limits.max_trades_day = 1`; the unseen run had one day with 2 trades (2026-02-11, second trade +$1,511). On the Desk that second trade is skipped.

## 5. Live-readiness (Lucid) — PASS
- Flat 15:55 ET (before the 16:10 cut): yes; 3 of 237 trades ended on the 15:55 time exit (2 build, 1 unseen), none later.
- Micro-scalp rule (under 5 s and over 50 % of profit): build had 1 trade under 5 s (3 s); unseen 0; shortest unseen hold 29 s. Winners under 60 s are 10 % (build) and 16 % (unseen) of profit. Not triggered.
- Multi-account hedging: N/A (one rule, one account).

## 6. Funnel sanity — PASS
Build 176 trades in 48 months (3.7 a month); unseen 61 in about 15 months (4 a month). About 0.9 a week, 35-41 % of weeks with no trade.

## Verdict
Safe to run on sim in shadow as it is. Before ANY account: (1) size it in micros or give it an own-size rule (a 1 NQ loser can reach $3.3k), (2) confirm the bracket re-price on one paper fill, (3) decide whether the 1-trade-a-day limit stays (it skips 1 of 61 unseen trades). Not run: new backtests (skill boundary).
