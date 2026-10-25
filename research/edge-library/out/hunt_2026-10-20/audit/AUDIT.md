# Audit of hunt 2026-10-20 (read-only; no build run, no walk-forward)

Verdict: **the numbers are right and the conclusion holds** (no new leg passes; the one eligible leg alone gives 1.25-1.6 a day, far from 5).
Problems found are in the record-keeping and in a few rules, not in the arithmetic.

Scripts here: `regrade.py` (Gate 1 from the cells, not from the stored average), `allstores.py` (every taught store, Gates 1 and 2).

## 1. RESULTS.md numbers vs the stores: all match

| Check | Result |
|---|---|
| Gate 1 table (cbreak, hurst, leg, pullback5) | match: a day, avg $, win, need, all to the decimal |
| "the other 15": 0.4-2.6 a day, -$28 to +$35 | match (stflip 0.40, oside5 2.56; -27.8 to +35.3) |
| Gate 2 table, 6 rules: WF net, trades, blind net (trades), P6 count | match wf/result.json |
| wf-each ranges (cbreak -13k..-21k on 128, hurst -7.5k..-9.6k, leg -1.3k..-3.8k) | match wf/each.json |
| Leg: 380 trades +$28,525, blind 99 +$6,574, P6 4/4, 99.55 % | match |

Small errors:
- conti_long_x020 is "fail (blind)": it also fails P6.2 (beats 93.7 %, needs 95 %).
- "123 tests pass": 124 pass now (a body_x test was added by another change).
- **"1 re-run (cbreak, after the seal fix, identical trades)" is not a re-run.** runs/.../run.json is dated 19:27 with the OLD
  candle_sweep hash (fe4484...). result.json was rebuilt from that store in about 11 s, so "identical" proves nothing. The real proof
  is the walk-forward's own check: it re-ran the centre cell on the build days with the NEW code (claim hash d0a6a845...) and had to
  match 1,733 trades / $129,893 before writing the claim. It did, so the claim is true, but for a different reason.
- **A second code change is not listed.** blueprint/taught_wf.py changed at 20:00 ET (uncommitted): cells now run one instance per
  session pass (`_run_cells`). All 6 hunt walk-forwards ran under it. The leg's walk-forward (claim 2026-10-20 01:53 UTC) ran under
  the old code. Both are guarded by the centre re-run check. It may come from the owner's session that same hour
  (owner_disp_break_body2x_15_allday, walk-forward at 20:00).
- **The first cbreak walk-forward is missing from the looks.** It exited with code 2 at 20:19 after writing a claim and opening the
  test days. The second attempt overwrote both claim.json and the log. No number was seen, so nothing leaked, but no record is left.

## 2. gate.py vs PREREG: correct

Breakeven formula 1/(1 + avg_win/|avg_loss|) on the average, +3 points, average of the cells, the centre's P4.2, 0.5 a day on 948,
P6 rows all PASS + blind net > 0: all as written. I re-graded from the cells and got the same pass/fail on all 19 sheets and the 4
extra stores. Using the average of the cells' win/loss ratio instead would flip nothing (closest: donch 45.6 % vs 45.97 %).

Rules that let something through:
- **conti_long_x020 passes G2 only on the both-sides random check.** It is long-only, and its long-only check (P4.2s) beats **0 %**
  of random longs. The letter of PREREG passes it; the intent would fail it. It failed its walk-forward anyway.
- Thin passes: hurst +0.3 points, leg +0.2 points over the bar, where one standard error of the win rate is about 1.9 points.
- Checked what gate.py does not: every NQ centre's stop averages over 20 points (cbreak 41, hurst 85, leg 49, leg A 35). Median hold
  times are 17-103 min, so nothing is a scalp.
- **Amendment B broke its own rule.** "NOT of a family whose walk-forward already failed": displace had failed
  (cl_am_disp15_vwap_10to11, 15:31 ET), yet cl_disp15_ema_allday_k1p5 (displace) was read. Under the same rule
  cl_pm_first_bar_cdl_15 was left out. That cost one extra look, and it failed.
- Amendment A checks out: 24 walk-forwards were on file, 4 fvg_oside "nl" versions pass, and vwap_pullback_c15 fails Gate 1
  (40.3 % vs 40.9 %). But **"the family was read 3 times" is too low**: there are 8 walk-forward claims in the fvg_oside 15m family
  before the hunt, 4 of them on the leg's own "nl" entries. The "no limit" versions were made after r075, r1 and r15 failed P6.4 on
  count. The leg's pass comes after about 8 correlated looks and a change made after seeing a result.

## 3. candle_sweep change: no future day can reach a decision

- `st.dl` = ctx.daily = `daily[:bisect_left(dates, today)]`. These are rows strictly before today, from the run's own daily list
  (build run: up to 2025-06-30 only; test run: build rows + test rows).
- `session_closes(past date)` reads 18:00 of the evening before to 17:00 of that date, so it ends before today's session opens.
- Today's EMA input: `hour_closes(..., now)` takes only prints before the current hour began, so only whole hours that have ended.
- The new LookAheadError can never fire, because bisect_left already excludes today. It is a harmless extra guard.
- Weakness: the switch is now picked from the date, not from the run, so the function itself no longer stops a build run from
  opening a test tape. Safety now rests on the caller (dl). Better: hand down the run's switch. The new test only checks which switch
  is chosen; no test checks that prior_closes raises.

Other families that open past tapes with a fixed `ALLOW_BP` (their walk-forward is impossible the same way):
- **candle930** `_day_candles`: used by `med_m` > 0 (the 14 prior dates) and by `vol_m` with `sec` > 0 (which also reads TODAY's
  date). A test run raises HoldoutSealed after the claim is written. Specs affected: manual_lane candle930_med_m_tk,
  candle930_sec30_disp_med_m_tk, candle930_sec30_disp_med_m_nolb_tk.
- **orb830 orb_close** with `vwap` on/first: `vwap16_series` loads with ALLOW_BP and also raises RuntimeError after 2025-06-30. Those
  sessions are dropped, and taught_wf refuses after writing the claim. Specs affected: orb830_range_stop_vwap_on_tick,
  orb830_range_stop_vwap_first_15m.
- No taught store uses these settings today.
- Same effect, different cause (no switch, read from cache):
  - blocks.cum_volume, round1.value_area and levels.session_bars: the NQ caches run to 2026-09-22, so NQ is fine. The ES/GC caches
    stop at 2025-06-30 (GC minvol at 2023-12-29), so an ES/GC walk-forward with those blocks would raise.
  - relcandle (`rel_dir`) holds build dates only, so a test run raises RelCandleMissing.

## 4. Dropping the clock ladder: sound

- The 15 test months (Jan/May/Sep 2022-2026) hold **305 NQ sessions**. Sep 2026 has only 15, because the data stops at 2026-09-22.
- The 13:30 twin (cl_pm_first_bar_cdl_ema_15) trades 0.63 a day. At 0.60-0.63 a day the most a slot can get is 183-192 test trades,
  and only if it never stands aside. With the usual 3-5 stand-aside months it gets 120-155 (the twin got 165; at 0.64, disp 10-11 got 130).
- Reaching 200 needs 0.66 a day or more AND no month standing aside. PREREG judges each leg alone, so no slot could pass P6.4, and
  reading them would only spend months.
- Note: the ladder failed by design. As one 8-slot rule it would trade about 4-5 a day and P6.4 would not stop it.

## 5. stack.py: reproduces the leg's walk-forward exactly

380 trades, $28,525, blind 99 / $6,574, the same win rate, and every month equal to wf/result.json (its internal check passes).
**But "1.58 a day" uses a flattering denominator:** 380 / 241 calendar weekdays of the **11 months the leg traded**. The 4
stand-aside months are dropped. Over all 15 test months it is **1.25 a day** (380 / 305 sessions). In a multi-leg Gate 3 this pushes
trades a day up whenever months stand aside. It also counts holiday weekdays and the missing days of Sep 2026, which push the other
way.

Also: `_test_days` says "whole months only", but 2026-09 is a part month (data to 2026-09-22).
