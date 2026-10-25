# Hunt 2026-10-20: 5-10 trades a day at 43 %+ at 1:1.5 (pre-registered before any run)

Owner, 2026-10-20 ~19:00 ET: "start hunting for a strategy with 5-10 trades a day at 43%+ win rate at 1:1.5 after costs,
checked on the 3:1 walk-forward". Goal: 5 Apex Legacy 300K PAs, taking turns, one trade open at a time.

Written BEFORE any sheet of this hunt is run. Nothing below changes after a result is seen.

## The route
Taught lane only (`bp.py taught check / run / wf`), sheets named `hunt_*` in `research/edge-library/taught/`.
Engine costs and fills ($4 a round turn, 1 tick slippage, tick replay, 1 NQ). Build days 2021-09-22 .. 2025-06-30.

## Sheet rules (every hunt sheet)
- Centre target = 1.5 x the stop (`target_r` 1.5, or target_pts = 1.5 x stop_pts). The lane adds the neighbours.
- One direction at a time: no family that rests orders on both sides (ib, ib_n, ib_touch, lon_break, orb, squeeze, straddle).
- Stops wider than 20 NQ points on average (fixed stops >= 20 pts); no scalping (no rule whose edge is holds of seconds).
- At most 1 trigger + 2 filters. A reason it should pay ("who loses") in `source.title`.
- `control: random`.

## Gate 1: build days (each sheet), read on the AVERAGE of its cells (the honest number), never the best cell
- G1 win rate >= breakeven of the average's realized reward-to-risk + 3 points
  (breakeven = 1 / (1 + avg_win / |avg_loss|); this is row P3.15 = 43 % at 1:1.5).
- G2 average trade > $0 after costs AND the centre's P4.2 (beats random entries) PASS.
- G3 at least 0.5 trades a day (>= 474 trades on 948 sessions).
- Label only: build years positive (years_average).

## Gate 2: the 3:1 block walk-forward (`bp.py taught wf`), Gate-1 survivors only, each read once
- P6.1 net > 0, P6.2 beats random, P6.3 (P3.15 on the stitched months), P6.4 trades: all PASS.
- AND the test months from 2025-07 on (the only truly blind months) net > 0.

## Gate 3: the stack (Gate-2 survivors), one position open at a time (first signal wins, a signal while a trade is open is skipped)
- Built ONLY from the legs' own walk-forward test-month trades (exit = entry + dur_s).
- Need >= 5 trades a day on the test months, P3.15 on the stacked trades, test-month net > 0, blind months (2025-07+) net > 0.
- Then the Apex Legacy 300K PA simulator (apex300.py, fresh), five accounts taking turns.

## Looks (multiple testing)
Every sheet run and every walk-forward read is counted in RESULTS.md. With N walk-forwards and a 95 % random gate,
about N x 5 % pass by luck alone: said next to the result.

## Amendment A (2026-10-20 19:25 ET, before any hunt sheet has a result)
Existing stores graded by gate.py (24 with a walk-forward on file): only the fvg_oside 15m family passes Gate 1 + Gate 2
(four versions of the same entries). ONE of them joins the stack as an eligible leg, chosen now: `owner_fvg_oside_15_a1m3_nl_r1`
(1:1, struct stop 3 x 1-min ATR, 1.74 a day). Its months are partly seen (the family was read 3 times): said with every result.
`owner_vwap_pullback_c15` passes the walk-forward but fails Gate 1 on build days (40.3 % vs need 40.9 %): NOT eligible.

## Round 1 result (2026-10-20 20:25 ET)
19 sheets run. Gate 1: 3 pass (hunt_fv_cbreak15_ema1h_midpm, hunt_dm_hurst15_ny, hunt_pb_leg15_ema20). Gate 2: all 3 FAIL
(-$8,101 / -$11,774 / -$21,104; blind months -$8,898 / -$9,483 / -$2,853). wf-each: every cell alone loses its unseen months.
Looks so far: 19 build runs + 3 walk-forwards (cbreak's needed a seal fix in candle_sweep.session_closes first: past sessions
open by their own date; build-day trades identical before / after: 1,733 trades, $115,426; test added).

## Amendment B (2026-10-20 20:35 ET, before reading them)
Past taught stores that pass Gate 1 by gate.py, never walk-forwarded, NOT of a family whose walk-forward already failed or that
the owner closed (fvg_odir), NOT of the fvg_oside family (its leg is already in): `conti_long_x020` (5m, long, 1.77 a day),
`conti_vault_break` (30m, long, 0.82), `cl_disp15_ema_allday_k1p5` (15m, 0.91). Each gets ONE walk-forward under Gate 2.
Their build days were seen in earlier sessions (no new build look). Note: conti_vault_break had the retired single unseen read
(Desk / manual), so its unseen months are not blind: said with its result.
