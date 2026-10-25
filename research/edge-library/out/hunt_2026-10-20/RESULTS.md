# Hunt 2026-10-20: results so far (5-10 trades a day at 43 %+ at 1:1.5, 3:1 block walk-forward)

Rules: PREREG.md (written before any run; amendments A and B before their reads). Grader: gate.py. Stacker: stack.py.
Apex: apex_stack.py. Runner: run_all.sh / one.sh. Logs: logs/. Sheets: research/edge-library/taught/hunt_*.json (rejected
ones in taught/hunt_rejected/), list and reasons in SHEETS.md. Stores: ~/.homebase/taught/<name>/.

## Looks
- Build-day runs: 19 hunt sheets (round 1). 1 re-run (cbreak, after the seal fix, identical trades).
- Walk-forwards read: 3 (round 1 survivors) + 3 (amendment B, past stores) = 6. wf-each on the 3 round-1 survivors (no new months).
- Luck baseline: with 6 walk-forwards and a 95 % random gate, ~0.3 passes expected by luck.

## Gate 1 (build days, average of the cells): 3 of 19 pass
| Sheet | a day | avg | win | need | Gate 1 |
|---|---|---|---|---|---|
| hunt_fv_cbreak15_ema1h_midpm | 1.83 | $66.6 | 45.7 % | 44.8 % | PASS |
| hunt_dm_hurst15_ny | 0.87 | $93.8 | 50.4 % | 50.1 % | PASS |
| hunt_pb_leg15_ema20 | 0.73 | $61.8 | 46.0 % | 45.8 % | PASS |
| hunt_fv_pullback5_s30_midpm | 0.33 | $286.5 | 59.0 % | 51.1 % | fails G3 (frequency) |
| the other 15 | 0.4-2.6 | -$28 to +$35 | | | fail G1 and / or G2 |

## Gate 2 (3:1 block walk-forward, each read once): 0 of 6 pass
| Rule | WF net | WF trades | blind months (2025-07+) | P6 | Gate 2 |
|---|---|---|---|---|---|
| hunt_fv_cbreak15_ema1h_midpm | -$8,101 | 314 | -$8,898 (37) | 1 of 4 | fail |
| hunt_dm_hurst15_ny | -$11,774 | 171 | -$9,483 (27) | 0 of 4 | fail |
| hunt_pb_leg15_ema20 | -$21,104 | 101 | -$2,853 (7) | 0 of 4 | fail |
| conti_long_x020 (B) | +$24,035 | 345 | -$2,651 (74) | | fail (blind) |
| conti_vault_break (B) | +$8,582 | 252 | -$5,019 (81) | | fail |
| cl_disp15_ema_allday_k1p5 (B) | +$9,983 | 168 | -$408 (27) | | fail |
wf-each (round 1): every cell alone loses its unseen months (cbreak -$13k to -$21k on 128; hurst -$7.5k to -$9.6k; leg -$1.3k to -$3.8k).

## The one leg on file that passes Gates 1 and 2 (amendment A)
owner_fvg_oside_15_a1m3_nl_r1: 1.74 a day (build), WF 380 trades +$28,525, blind 99 trades +$6,574, P6 4 of 4, beats 99.55 % of
random. Its family's unseen months were read 3 times before this hunt (partly seen). Stack of this leg alone: 1.58 a day on the
test months: short of the 5 a day the owner asked for.

## Code change made
engine/families/candle_sweep.py session_closes: a past session's tape opens with the build switch up to 2025-06-30 and the test
switch after (it was build-only, so any walk-forward of an `ema1h` sheet was refused); prior_closes now raises LookAheadError if
a "prior" session is not before today. Test: engine/tests/test_candle_sweep.py::test_past_session_seal_by_its_own_date. The
family's 123 tests pass; the cbreak build store re-run gave identical trades (1,733, $115,426).

## Audit corrections (2026-10-20 ~21:00 ET; audit/AUDIT.md, SKEPTIC_*.md, critic.md, JUDGE.md). No verdict changes.
1. The leg alone is **1.17-1.25 a day** over all 15 test months (stand-aside months counted), not 1.58. stack.py fixed (every test month).
2. The leg's family had **at least 8** walk-forward reads before tonight (4 on its own entries), ~12 counting fvg_odir and Desk ports;
   its 3x 1-min ATR stop and no-cap version were chosen after earlier reads. Discount its blind +$6,574 (99 trades, t 0.80) heavily.
3. The cbreak "re-run" re-graded the old store; the real proof of identical build trades is taught_wf's centre-cell check under the new code.
4. A second code change exists: blueprint/taught_wf.py (20:00 ET, uncommitted, NOT made by this hunt: another session). All 6 hunt
   walk-forwards ran under it.
5. 7 walk-forward attempts: cbreak's first crashed after writing its claim (no number seen).
6. conti_long_x020 also fails P6.2 (93.7 %); it passed Gate 1 only on the both-sides random check, its long-only check (P4.2s) is 0 %.
   gate.py fixed: a one-side rule must also pass P4.2s.
7. Amendment B broke its own exclusion rule: the displace family had already failed a walk-forward (cl_am_disp15_vwap_10to11).
8. 2026-09 runs only to 09-22.
9. The leg, fixed 1:1, every day since 2025-07 (NOT blind): +$68.7k on 469 trades, but **2026-05..08 = -$13,454 on 126 trades**,
   drawdown -$20,368; the walk-forward's own pick for 2026-10 is **stand aside**.
Also: candle930 (med_m; vol_m + sec) and orb_close with vwap read past tapes under the fixed build seal: cannot be walk-forwarded yet.

## Verdict
No new leg. The target (5-10 a day at +0.075R) is not on file: on build days none of the 51 taught sheets that trade 2+ a day
reaches it, and the one out-of-sample survivor gives ~1.2 a day at 1:1 and is in a drawdown. No round 2 tonight: every new
walk-forward reads the same 3 blind months (2025-09, 2026-01, 2026-05). Next new blind month: January 2027.
