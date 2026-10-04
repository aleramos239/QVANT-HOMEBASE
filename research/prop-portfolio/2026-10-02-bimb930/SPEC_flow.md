# flow930 — NQ 09:30 trade-volume direction, 1:2 bracket (pre-registered 2026-10-02, BEFORE any run)

User idea (2026-10-02): "enter in the direction of which direction has more volume." Same account / bracket / window / controls
as SPEC.md (Apex Legacy 300K PA, 2 NQ, stop 25 / target 50, flat at 15:58 ET, 2021-09..2024-12 only, 2025+ sealed).

## Plain-words reason (written before testing)
If aggressive buyers (market buys lifting the offer) have traded more contracts than aggressive sellers just before the
cash open, demand is pressing and the open should lift; if sellers dominate, it should fall. Follow the heavier side.

## Rule (one trigger, zero tunable parameters)
- Window: the 15 minutes before the open (09:15..09:29 ET minutes, usable at 09:30:00): the same window the earlier pilot
  used for its pre-registered flow definition (families/opendir.py FLOW_MIN = 15, FLOW_VALID = 8) so the window is NOT picked here.
- `f_delta` = buy aggressor volume - sell aggressor volume per minute (tick-rule, own tape). Sum over the 15 rows
  (a minute without a print adds 0; fewer than 8 finite minutes = no trade).
- Sum > 0 -> market LONG at 09:30:00; sum < 0 -> market SHORT; sum == 0 -> no trade.
- Stop 25 pts, target 50 pts (re-priced from the fill), 1 trade per day, held to stop / target or flat at 15:58 ET.
- 1 NQ in the simulator, scored at 2 NQ; tester cost law. Same days for the always-long / always-short controls.

## Controls and verdict (same as SPEC.md)
- always-long / always-short on the same days; 20 C2 nulls (`f_delta` taken from a random other day, same time of day).
- Informative ONLY IF: (1) real win rate >= the 95th percentile of the 20 nulls (at most 1 of 20 at or above it);
  (2) real net > 0 at 2 NQ after costs; (3) real win rate above the null mean in >= 3 of the 4 calendar years.
One run, no retune. A changed window or threshold is a NEW test.
Prior art: the 9:30 delta-direction family was refuted on 2026-09-23 (ledger NQ|1m|930_delta_direction); the pilot's
open_dir_flow (stop entries, 3 ATR stop, no target) was a lead only (t +0.1).
