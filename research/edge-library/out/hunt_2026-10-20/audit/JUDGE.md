# Judge: hunt 2026-10-20 (5-10 trades a day at 43 %+ at 1:1.5)

Read-only. No build run, no walk-forward. Three reviewers (AUDIT.md, SKEPTIC_owner_fvg_oside_15_a1m3_nl_r1.md, critic.md) weighed,
and the points they disagree on checked against the stores myself.

## The answer

| Question | Answer |
|---|---|
| (a) RESULTS.md numbers and verdicts right? | **Yes.** Every number matches the stores. 0 of 19 new sheets and 0 of 6 walk-forwards pass. Nine fixes to the record are listed below. None of them changes a verdict. |
| (b) FVG leg real enough to trade? | **No, not with money now.** Keep it on paper (forward shadow). The house walk-forward's own pick for October 2026 is **stand aside**. |
| (c) Round 2 tonight? | **No.** Any new walk-forward reads the same 3 blind months again. Do the four things under (c) instead. |

## (a) What RESULTS.md needs to fix (numbers and verdicts stand)

| # | RESULTS.md says | Correct |
|---|---|---|
| 1 | Leg alone: 1.58 a day | **1.25 a day** over all 15 test months (380 trades / 305 sessions). 1.58 leaves out the 4 months it stood aside. stack.py's denominator needs the same fix. |
| 2 | Family "read 3 times" | **At least 8** walk-forward reads in the fvg_oside 15m family (4 of them on this leg's own entries), and **about 12** if you count the fvg_odir unseen read (87 % the same trades), the 48-version odir walk-forward and the Desk-port walk-forwards. The 3x 1-min ATR stop and the no-limit version were both chosen after the first of these reads. |
| 3 | cbreak re-run gave identical trades | Not a re-run. The store was re-graded from the old trades (run.json 19:27, old hash). The real proof is the walk-forward's centre-cell check under the new code (hash d0a6a845), which passed. |
| 4 | One code change | Two. `blueprint/taught_wf.py` also changed (20:00 ET, uncommitted). All 6 hunt walk-forwards ran under it. |
| 5 | 6 walk-forwards | **7 attempts.** cbreak's first attempt crashed after writing its claim. No number was seen. |
| 6 | conti_long_x020 fails "(blind)" | It also fails P6.2 (beats 93.7 % of random, needs 95 %). It passed Gate 1 only on the both-sides random check. Its long-only check beats 0 %: a hole in gate.py. |
| 7 | Amendment B | It broke its own rule: displace had already failed a walk-forward, yet cl_disp15_ema_allday_k1p5 was read. That cost one extra look, and it failed. |
| 8 | Test months are whole months | 2026-09 runs only to 09-22 (15 sessions). |
| 9 | 123 tests pass | 124 now (another change added one). |

## (b) The FVG leg (owner_fvg_oside_15_a1m3_nl_r1)

It passes the pre-registered gates on paper. As proof, it is weak. I checked these numbers myself from `wf/test_cells.npz`:

| Check | Number |
|---|---|
| Blind months (2025-09, 2026-01, 2026-05) | +$6,574 on 99 trades, $66 a trade, **t 0.80** (luck can do this about 1 time in 5) |
| Blind, without its best 5 trades | **-$956** |
| Fixed 1:1 on the same months (no monthly target switch) | about $26 a trade. May 2026 is -$1.4k at 1:1 and +$3.7k at 0.75. |
| Every day since 2025-07, fixed 1:1 (not blind) | +$68.7k on 469 trades, but Oct + Nov 2025 make half of it |
| **Last 4 whole months (2026-05 .. 08)** | **-$13,454** on 126 trades. Drawdown **-$20,368** (2026-05-18 .. 09-09) |
| Walk-forward pick for **2026-10** | **stand aside** (no cell passes Jul-Sep) |
| 1 NQ at an Apex 300K PA | breaks it: drawdown above $7,500, and 4.4 % of recent stops are wider than the $2,250 open-loss limit |

Fair reading: there may be a small edge. The first look at these months (10-19, a near-twin) made $50 a trade, a third less than
on build days. But after about 12 reads and picks made on the same months, count the blind +$6.6k as roughly $0 to $1.6k.
It is also 1.25 a day at 1:1, far from the 5-10 a day at 1:1.5 the owner asked for.

**How, if and when it trades (the owner's call):**
1. Now: **paper only.** It already runs in shadow on the VPS (`nq_fvg_oside_15_*`). Forward days are the only clean test left.
2. Start money only when **both** hold: the monthly pick no longer says stand aside (next check Nov 1), **and** about 2 months
   (about 60 trades) of forward paper trades are not negative.
3. Then: **by hand** (Apex bans automation on PAs). **ONE PA, 2 MNQ micros.** At 2 micros every stop ever seen fits under the
   $2,250 open-loss limit (the worst, 516 pts, = $2,064), and the recent $20.4k drawdown is about $4.1k. **Do not copy it to all 5 PAs**:
   with the edge removed, copying busts 82 % of accounts, and if the rule dies all five die together.
4. The rule as traded: 15m bars. Side = above or below the 09:30 open. A limit at the near edge of the newest gap on that side,
   moved to each newer gap. Stop 3 x the 1-min ATR(14), target 1:1. Entries 10:15-15:00, and cancel at 15:00. No cap on trades.
   Use the month's target from the walk-forward pick.

Honest size of the prize: at 2 micros with a $8-26 edge per NQ, about $600-1,600 a year. It is a paid test, not an income.

## (c) No round 2 tonight. Instead:

Why not:
- All 31 walk-forwards on file read the same blind months: 2025-09, 2026-01 and 2026-05, about 63 weekdays.
- A round 2 of about 15 sheets gives about 0.07 real legs and about 0.2 lucky passes (critic). A pass would be about 3 to 1 luck.
- Each untried idea left gives about 0.4-0.8 a day. The gap to 5 a day is about 3.75.
- Clock time is not the problem: the leg is in a trade only about 44 min a day. Edges are.
- On build days, none of the 51 taught sheets that trade 2+ a day reaches +0.075R. The target is not on file.

What to do instead:
1. **Keep the leg on paper**, as in (b).
2. **Fix the record**: RESULTS.md items 1-9 above. Also make gate.py use the one-side random check for one-side rules, and make
   stack.py divide by every test-month session.
3. **Talk to the owner about the target.** What has held out of sample is about 1.25-1.6 a day at about +0.08R, one family, partly
   seen. 5-10 a day at 43 % / 1:1.5 is not there.
4. **The next new blind month is January 2027** (pick Oct-Dec, trade Jan). Until it is in, research on build days only. The critic's
   four angles are the only ones left with a reason: displace with the 09:30-open side gate, the `liq` break on overnight /
   prior-day levels, `vol_spike_break` in the pm, `win_break` on each session's own opening range. Walk-forward them only once
   Jan 2027 is in.

For later (auditor): candle930 (`med_m`, `vol_m` + `sec`) and orb830 `orb_close` with `vwap` open past tapes under the fixed build
seal, so those settings cannot be walk-forwarded yet.

Not checked by me: the critic's base-rate counts (51 sheets, 31 walk-forwards) and the Apex simulator numbers. I took them from
their notes. No Apex run was done at 2 micros.
