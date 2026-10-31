# VWAP hunt 2026-10-20: pre-registration (written before any run of this hunt)

Owner's brief: `~/Obsidian/Vault/30-Projects/Onyx-Trading/prompt-vwap-5-10-a-day-3to1-blocks.md` (binding). Goal: VWAP rules on NQ that,
stacked one position at a time, give 5-10 trades a day at >= 43 % win at 1:1.5 after costs (or win >= break-even of the realized
reward-to-risk + 3 points). Report only: no Desk, no trading, no prop sims.

Written 2026-10-20 ~21:15 ET. Nothing below changes after a result is seen. Amendments, if any, are added at the end with their time
and BEFORE the read they govern.

## 1. The route
Taught lane only. Every sheet: `bp.py taught check` (all 123 pass) -> `bp.py taught run` (build days; the printed numbers are NOT read)
-> `bp.py taught wf` ONCE (stores every cell's test-day trades in wf/test_cells.npz; its output goes to logs/ unread) -> after
SELECTION.md: `bp.py taught wf-each` (the lane's own per-cell "always" read, used to check my month totals). Engine costs and fills
($4 a round turn, 1 tick slippage, tick replay, 1 NQ). Sheets `taught/vwap_*.json`, written by `make_sheets.py` from one table.
Runner: `runq.py` (4 runs at once outside desk hours, 2 on weekdays 08:00-16:15 ET, 3 workers each).

## 2. Months
- Blocks (house law): pick on 3 months, trade the next 1, from 2021-10. OUT-OF-SAMPLE (OOS) = Jan / May / Sep 2022 .. Sep 2026 (15
  months; Sep 2026 runs to 09-22). IN-SAMPLE (IS) = every other whole month 2021-10 .. 2026-08 (2021-09 is a part month: out).
- Build side (to 2025-06-30) from runs/<name>-NQ-tf*/cells.npz; test side (2025-07-01 on) from wf/test_cells.npz.
- FRESH months (never inside any build): 2025-09, 2026-01, 2026-05, 2026-09 (to 09-22). Reported on their own.
- Test-day trades carry no session code: the group is read off the entry clock (ET): ON = 18:00-03:00, LDN = 03:00-09:30,
  NY = 09:30-18:00. Checked against the stored session codes on the build days (mislabel rate reported).

## 3. What a version is
VERSION = one sheet x one exit cell (the taught cell and its neighbours: stop x {0.75, 1, 1.25} x target x {0.75, 1, 1.25}, or a
structure stop's target x {0.75, 1, 1.25}) x one SESSION GROUP the sheet trades: NY (nyam + mid + pm), LDN (london), ON (asia + eve).
Every version trades every month: no pick, nothing stands aside. Stops: s25 = 25 / 37.5, s40 = 40 / 60 (its 0.75 x 0.75 cell is the
30 / 45 stop of the brief, exactly 1.5R), struct = the family's own level at 1.5R. 1-minute sheets: NY passes only (machine time).

### 3a. New sheets (123), by idea
| Idea | Sheets (family, setting) | Bars | Groups | Stops |
|---|---|---|---|---|
| 1 VWAP pullback (owner's rule, no 09:45 continuation) | jj_fair mom / vwap / pullback / slope 30, wick off | 1, 5, 15 | NY | s25, s40 (its struct = 25 pts = s25) |
| 2 VWAP trend pullback | vwap_trend_pull x 0.1, max_loss 2 | 1, 5, 15 | NY | s25, s40 |
| 3 VWAP flip | vwap_flip anchor rth hold 2 (1, 5, 15); anchor session hold 2 (5, 15) | | NY (+LDN, ON on 5 / 15) | s25, s40 |
| 4 EMA x VWAP | vwap_ema_x rth n21 (1, 5, 15); session n21 (5, 15); rth n9, rth n50 (5) | | NY (+LDN, ON on 5 / 15) | s25, s40 |
| 5 limit AT VWAP, first touch | vwap_touch us away 40 pts (1, 5, 15); london 40 (5, 15); day 40 (5, 15); us 20 pts (5) | | NY (+LDN; +ON for day) | s25, s40 |
| 6 VWAP side gate (vwap_dev >= 0 with) | fvg touch gap 0.1; displace k 1.5; candle_sweep break; donchian 20 | 5, 15 | NY, LDN, ON | s25, s40, struct |
| 7 ORB on the VWAP side | win_break 09:30-10:00 close break (1, 5, 15); orb_confirm 30 long / short (5) | | NY | s25, s40, struct |
| 8 Fades | vwap_band 2 sigma; vwap_z 2 sigma | 1, 5, 15 | NY (+LDN, ON on 5 / 15) | s25, s40 |
| 9 Band BREAK | ind_signal vwap_dev follow 1 sigma (1, 5, 15), 2 sigma (5, 15); noise_band rth 0.3 (5) | | NY (+LDN, ON) | s25, s40 |
| 10 Slope / trend regime | gate ADX(14) >= 25 on vwap_flip rth, vwap_ema_x rth21, vwap_touch us40, vwap_trend_pull | 5 | as the family | s25, s40 |
Caps: 3 a pass (vwap_trend_pull 4, its own; jj_fair 20 a day, one instance; win_break / orb_confirm / noise_band 1). Exact list:
`make_sheets.py` (printed in SHEETS.txt).

### 3b. VWAP stores already on file (NQ), each its own versions, "partly seen" (their build days were read before)
- Walk-forward on file (no run): owner_vwap_pullback_25_38, owner_vwap_pullback_50_76, owner_vwap_pullback_c15 (its pullback trades
  carry a ~3-point stop by the jj_fair bug fixed 2026-10-20: reported, flagged), owner_vwap_pullback_c15_fix, owner_vwap_pb_near10_c15
  (all idea 1), cl_am_disp15_vwap_10to11 (idea 6).
- Walk-forward to run once (`taught wf`): hunt_pb_jj_vwap15 (1), hunt_dm_vwflip15_rth_midpm (3), hunt_pb_vwaptouch_us40 (5),
  hunt_fv_fvg15_vwap_p30, hunt_fv_ifvg5_vwap, hunt_fv_oside5_a1m3_vwap, displace_vwap_1r_{k1p0,k1p5,k2p0} and _10to11_*,
  cl_fx_disp15_vwap_10to11_{long,short}, ddiv_n1_vwap_with_15_15 (6), hunt_dm_noise15_ny (9), conti_vwap_adx, _tp10, _tp15, _tp20 (10).
  A store the lane refuses (code changed since its run) is dropped and said.
- Left out: ES / GC stores (rother_vwap_* ES, hunt_mx_*): the goal is NQ trades.

### 3c. Not buildable from the menu (listed for the owner, NOT built; a new block = ask first)
- 11 two anchors agree (18:00 session VWAP and 09:30 VWAP): the engine has no 18:00-anchored VWAP gate (vwap_dev reads the PASS VWAP).
- 12 first pullback to VWAP after an opening-range break: no block holds "after an ORB break" + "VWAP touch".
- 13 VWAP reclaim with volume: the taught lane takes no menu filters (`filter: None`), so `rvol high` cannot be added.
- 14 London VWAP side as a New York filter: no gate on the 03:00 VWAP (only vwap_touch anchor london, run in 3a idea 5).
- 15 yesterday's closing VWAP, VWAP anchored at prior-day / overnight high-low, weekly VWAP side: new blocks.
- `avwap with` / `vwap with` filters: not in the taught lane; the gate `vwap_dev >= 0, with` stands for "vwap with" (pass VWAP).
- orb_close's own `vwap` and candle930 `med_m` / `vol_m + sec`: the trap (fixed build seal): not used.

## 4. Selection on IN-SAMPLE months only (SELECTION.md, written before any OOS number is opened)
A version is CHOSEN when, on its IS months:
- C1 win rate >= break-even of its realized reward-to-risk (avg win / |avg loss|) + 3 points;
- C2 net > 0, and still > 0 with one extra tick a side ($10 a trade off);
- C3 beats >= 95 % of the lane's random-entry tables on the build-side IS months (stored control pools, same exit cell, day- and
  pass-matched, summed over the group's passes; a one-side sheet also against random entries of its own side, P4.2s);
- C4 at least 0.66 trades a day (IS sessions) -- the rate that gives 200 trades on the ~305 OOS sessions;
- C5 the IS months from 2025-07 on (test side: 2025-07, 08, 10, 11, 12, 2026-02, 03, 04, 06, 07, 08) net > 0;
- C6 its idea's average version (mean of the versions' average trade) on IS > 0.
Ranked by (win - need), then average trade. Only CHOSEN versions can pass; a version that is not chosen and would pass on OOS is
reported as "not chosen: does not count".

## 5. The pass bar on OUT-OF-SAMPLE months (every OOS month traded, 1 NQ after costs)
P1 win >= break-even of realized R:R + 3 points. P2 net > 0 and > 0 at +1 tick a side. P3 beats >= 95 % of random tables on the same
months and exits (one-side: also its own side). P4 >= 200 trades. P5 fresh months (2025-09, 2026-01, 2026-05, 2026-09) net > 0.
P6 its idea's average version > 0 on OOS. Plus CHOSEN on IS.
The per-version OOS read has NO random control in the lane (wf-each has none; taught wf runs random entries on the test days but does
not keep them). P3 is therefore built by `randctl.py` (this folder): the lane's own random entries (l2ref.Random, the store's control
seeds, exit cells and passes) run on the test days, and the build-side pools from the stored controls; drawn with judge.c1_cell
exactly as pipe_wf.against_random, one month at a time. It is run (lazily) only for versions that are chosen and pass P1, P2, P4,
P5, P6, and the same for every such version.

## 6. Stack
Passing versions, preferably from different ideas and hours, merged one position at a time (first signal wins; a signal while a trade
is open is skipped), every OOS month traded. Needs >= 5 trades a day on the OOS sessions and P1, P2, P5 on the stacked trades.

## 7. Luck
N_read = every version whose OOS was read. N_chosen = the chosen versions (only they can pass). Expected lucky passes of the random
line: 5 % of each. Fresh-month reads: 31 walk-forwards before last night's hunt + 6 last night + every `taught wf` of this hunt.

## 8. Order of runs (queue.txt)
Existing stores' walk-forwards first (short), then ideas 1, 2, 5, 3, 6, 7, 9, 4, 10, 8 (the brief's leads first, fades last).

## Amendment A (2026-10-20 ~22:45 ET, before any sheet below has run; no out-of-sample number of this hunt has been seen)
The owner (22:20 ET): "if you need build new blocks, just make sure to save and add them so we dont need to rebuild them". Section 3c's
ideas 11-15 are now built as engine blocks in ONE new module, `engine/families/avwap.py` (auto-registered; tests
`engine/tests/test_avwap.py`, 27 pass; no hashed file of any other family edited, so nothing already run is re-stamped):
- lines: rth 09:30, london 03:00, midnight 00:00, globex 18:00 the evening before, week (Sunday 18:00), pdvwap (yesterday's
  09:30-16:00 closing VWAP, a fixed level), pdh / pdl (anchored at yesterday's 09:30-16:00 high / low minute), onh / onl (anchored at
  the overnight 18:00-09:30 high / low minute, New York only). Past tapes open by their own date (the 2026-10-20 seal fix).
- `avwap_touch` (vwap_touch's rule on any line), `avwap_flip` (vwap_flip's rule on any line; `vol_m` = the crossing bar's volume vs
  the 14-day median of the same clock window), `orb_vwap_pb` (the first pullback to the 09:30 VWAP after a close beyond the 09:30
  range; structure stop = the range's other edge); `also` = a second line the close must agree with.
- Still NOT built: a VWAP side GATE for any other entry (the open layer `_flex.py` is stamped into the flex families queued in this
  hunt; editing it mid-hunt would re-stamp them). Ideas 11 / 14 / 15c are run as `also` on the VWAP families instead.

The 63 new sheets (`make_sheets.py --amend-a`, list in SHEETS_A.txt; all pass `taught check`), versions as section 3:
| Idea | Sheets | Bars | Groups | Stops |
|---|---|---|---|---|
| 11 two anchors agree | avwap_flip rth + also globex (hold 2); avwap_touch rth + also globex (away 40 pts) | 1, 5, 15; touch 5 | NY | s25, s40 |
| 12 first pullback to VWAP after an ORB break | orb_vwap_pb or 30 (1, 5, 15); or 15, or 60 (5) | | NY | s25, s40, struct |
| 13 reclaim with volume | avwap_flip rth, hold 1, vol_m 1.0 | 1, 5, 15 | NY | s25, s40 |
| 14 London VWAP side into NY | avwap_flip rth + also london (hold 2) | 5, 15 | NY | s25, s40 |
| 15 new lines | avwap_touch pdvwap (5, 15), pdh, pdl (5), onh, onl (5, NY), week (5), globex (5, 15); avwap_flip pdvwap (5, 15), globex (5, 15), rth + also week (5, 15) | | NY + LDN + Asia (ON) where the line exists | s25, s40 |
They join the same selection (section 4: their ideas' averages included) and the same pass bar. SELECTION.md waits for them.
Order: after the 143 jobs of queue.txt (queue_a.txt), and only after the adversarial review of avwap.py (a code fix before any run;
any fix after a run = a new sheet name, said here).
Review of avwap.py (2026-10-20 ~23:10 ET, 11-agent adversarial workflow: 3 lenses, each claim checked by a skeptic), BEFORE any
Amendment A sheet ran. Fixed: (1) after a holiday a tape starts 30 h back: globex / onh / onl and the week's first evening now start
at 18:00 the evening before (pdh / pdl and a holiday session inside the week keep every minute since their anchor); (2) avwap_flip
resets its side at every session start, as vwap_flip (no change under hold_to = day); (3) the orb_vwap_pb structure-stop test now
asserts the trade's stop (`sl`), plus a short case. 30 tests pass. Not fixed (lane code, after the hunt): taught._plan probes a
family's passes with its DEFAULT settings, so a sheet could name a pass its line never trades (an empty pass, no error); none of the
63 sheets does (each names only passes where its line exists).
