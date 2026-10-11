# Strategy review: NQ 03:00 Candle Body (Lab draft `nq_0300_candle_body`)

Reviewed 2026-10-11 on the draft's source (`~/.homebase/strategies/nq_0300_candle_body.py`) and its build-day run
`20261011-110728-draft_nq_0300_candle_body-7c67` (qty 1, $4 + 1 tick, 2021-09-22 to 2025-06-30). Scope: promote to the Desk OFF / shadow, no account.

**The rule:** at the close of the 5-minute candle that opens 03:00 ET (03:05:00), go with its direction if its body is at least `body_r` of
its range; market entry, stop `stop_pts`, target `rr` x stop, both re-priced to the fill; one trade a day; flat 09:35 ET (before the cash open).
Defaults: body 0.4, stop 30 pts, 3R. Setup-panel settings: `body_r` 0.4 / 0.5 / 0.6, `stop_pts` 20 / 30 / 45, `rr` 2 / 3 (all tested boxes).

## 1. Look-ahead bias: PASS
Signal read in `on_bar` on the bar whose `end_ns` is exactly session start + 5 minutes; uses that bar's o/h/l/c, all closed. The order is a market
order after the close. No daily bar, no indicator, no later bar. Chain: `share = |c - o| / (h - l)` -> side by `c > o` -> `ctx.market(...)`.

## 2. Repainting: PASS (N/A for Pine)
A closed 5-minute bar does not change. Nothing plotted feeds a later decision.

## 3. Overfitting smell tests: WARN
- Three settings and no filter: within the "fewer rules" bar.
- The default is the best of about 48 stop x target cells x 5 bodies x 3 flat times on the build days (and a 02:00 window that failed first).
  Picked on the first 75 % of the build days; held on the last 25 % (39-41 % eval odds), then **one read of the test days
  (2025-07-01 .. 2026-09-22, 191 trades): +$22.1k at one mini, PF 1.26, eval 39.8 % / 30 d at 17 micros, stress 20 %**. A manual-lane read
  (no card / lock / lines 4.1-4.9; controls tilted by the time stop): it cannot prove the rule, and the test days are now used up.
- Lumpy: 2022 ~$0 (win 27 %); on the test days two quarters (2026-Q1 +$26.7k, 2026-Q3 +$19.5k at 17 micros) carry it, 2026-Q2 and 2025-Q3 lose.

## 4. Position sizing and risk: WARN
- 30 pts = $600 per mini + costs (worst trade -$649 at one mini). The eval odds exist only where ONE 3R win passes ($3,000): 2 minis
  (~20 micros, $1,200 a stop) -> 37 %; one mini or fewer is slow (10 micros 35 % in 30 d, median day 8). Two stops ($2,400) bust a $2,000 trailing limit.
  Bust ~60 %; "live is worse" row ~20 %. The Desk's own-size cap is 10 micros, so the 17-micro size of the research box is reached only
  with 2 minis on the account.
- The bracket is re-priced from the fill (`move_brackets_to_fill`): the stop is sent or moved after the fill, not in the entry's body (open
  Desk item for EVERY Lab strategy; paper and shadow are fine, demo step before funded / live).
- A 03:05 market entry is in London's thin hours: wider slippage than the tester's 1 tick is possible.

## 5. Live-readiness (Lucid): PASS
- Flat 09:35 ET, well before Lucid's 16:10.
- Holds: shortest 12 s (2025-04-09, a stop), then 23 s, 55 s; most 5 minutes to 6.5 h. None under 5 s.
- One trade a day, one market, no hedging. It cannot share an account with another strategy on the full NQ market (nq_0830_candle_body trades NQ from 08:35).

## 6. Funnel sanity: PASS
522 trades in 944 sessions (about 11 a month).

## Parity with the research box (body 0.4, pts 30, 3R, flat 09:35)
2021-2024: identical to the dollar (141 / 140 / 125 / 144 trades; 2021 +$1,751, 2022 +$1,500, 2023 +$24,910, 2024 +$18,569). 2025 (to June):
Lab 72 trades +$7,307 vs research 70 trades +$8,525 (two extra Lab trades). Net: Lab $54,037 / PF 1.26 vs research $55,255 / PF 1.27.

## Verdict
**Safe to run on sim / shadow (promote OFF, no account).** Before an account: the owner's size (2 minis = the tested ~20 micros; never over what two stops
can cost against the $2,000 limit). Before funded or live: the demo step on stop-only bracket bodies, live prices that are real-time, and a
decision about the thin-hours slippage (a paper month at 03:05 would show it).
