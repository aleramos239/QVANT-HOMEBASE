# VWAP hunt on hm40 + the fixed 3:1 blocks: pre-registration (written before any run on this route)

**The owner, 2026-10-20 ~23:20 ET (verbatim, the `--owner-said` of every in-sample run below):**
"Yes: redo the VWAP hunt on hm40 and the fixed 3:1 blocks once feat/hm40-fixed-wf is merged. In-sample table and selection first,
out-of-sample only for the picked boxes on my word."

The goal and the pass bar are the brief's (`~/Obsidian/Vault/30-Projects/Onyx-Trading/prompt-vwap-5-10-a-day-3to1-blocks.md`):
VWAP rules on NQ that, stacked one position at a time, give 5-10 trades a day at a win rate >= break-even of their realized
reward-to-risk + 3 points (43 % at 1:1.5). The route and the months are the owner's new law (spec
`docs/superpowers/specs/2026-10-20-heatmap-40-and-fixed-box-walkforward-design.md`). Where they differ, the new law wins.
Nothing below changes after a result is seen. Amendments are added at the end, with their time, BEFORE the read they govern.

## 0. What happened before (the old lane, paused)
The first run of this hunt (PREREG.md in the parent folder) used main's old taught lane: 9 cells a sheet, fixed-point stops. It was
paused at 23:05 ET after 35 of 143 jobs because the owner wants hm40. Those stores stay on file and are NOT used here. Their
`taught wf` computed the test months of 26 stores (stored, never read). The fresh months were not looked at by anyone.

## 1. The route (after feat/hm40-fixed-wf is merged into main; nothing runs before)
- One spec per idea x bar size x session group (run_idea's format, `exits: hm40`). The list: `make_specs.py` -> `specs/` (74).
- Each spec: `bp.py wf run specs/<name>.json --owner-said="<the owner's words above>"` = every box (the idea's 3 setting values x
  the 40 hm40 cells; 20 cells for a family with no stop of its own) on the 3:1 IN-SAMPLE months only, plus its worse-fills stores
  and the shared 10-seed random-entry pool. The test months are not run, not stored, not read.
- Then `bp.py wf show <name>` (the in-sample table). Machine: 4 runs at once outside desk hours, 2 on weekdays 08:00-16:15 ET, none
  started 09:15-09:40.
- Checked against the branch's own spec check (hmwf._spec) before the merge: 51 of 74 pass. The other 23 (jj_fair, avwap_*) name
  families that only main holds; they are checked again after the merge, and a spec the check refuses is said, not changed silently.

## 2. Months (wfmonths.py, not re-derived)
Blocks: Oct-Dec 2021 -> Jan 2022, Feb-Apr -> May, Jun-Aug -> Sep, ... The data's complete sessions end 2026-09-22, so Sep 2026 is
not a whole month: **14 blocks**, 42 in-sample months (Oct 2021 .. Apr 2026, every month but Jan / May / Sep), 14 out-of-sample
months (Jan / May / Sep 2022-2025, Jan and May 2026). Jun-Aug 2026 is a trailing part-block: in no block. The fresh test months
(never inside any build): **Sep 2025, Jan 2026, May 2026**.

## 3. The ideas (74 specs; main setting = 3 values; the 40 cells are the exits)
| Idea | Family: main setting (values), fixed | Bars | Groups |
|---|---|---|---|
| 1 VWAP pullback (owner's rule, no 09:45 continuation) | jj_fair: vwap_slope 15 / 30 / 60; mom, fair vwap, pullback on, wick off | 1, 5, 15 | NY |
| 2 VWAP trend pullback | vwap_trend_pull: x 0.05 / 0.1 / 0.2; max_loss 2 | 1, 5, 15 | NY |
| 3 VWAP flip | vwap_flip: hold 1 / 2 / 3; anchor rth | 1, 5, 15 NY; 5 night | NY, night |
| 4 EMA x VWAP | vwap_ema_x: n 9 / 21 / 50; anchor rth | 1, 5, 15 NY; 5 night | NY, night |
| 5 limit at VWAP, first touch | vwap_touch: away 20 / 40 / 60 pts; anchor us (NY), london (London), day (Asia) | 1, 5, 15 NY; 5 | NY, LDN, Asia |
| 6 VWAP side gate (vwap_dev >= 0, with) | fvg min_gap 0.1 / 0.25 / 0.5; displace k 1 / 1.5 / 2; candle_sweep break back range / body / far; donchian n 10 / 20 / 40 | 5, 15 NY; 5 night | NY, night |
| 7 ORB on the VWAP side | win_break r_end 09:45 / 10:00 / 10:30 (+gate); orb_confirm or 15 / 30 / 60 long, short (+gate) | 1, 5, 15; 5 | NY |
| 8 fades | vwap_band 1.5 / 2 / 2.5 sigma; vwap_z 1.5 / 2 / 2.5 | 1, 5, 15 NY; 5 night | NY, night |
| 9 band break | ind_signal vwap_dev follow lvl 1 / 1.5 / 2; noise_band k 0.2 / 0.3 / 0.4 long, short | 1, 5, 15 NY; 5 night; noise 5 | NY, night |
| 10 trend regime | ADX(14) >= 20 / 25 / 30 on vwap_flip, vwap_ema_x, vwap_touch, vwap_trend_pull | 5 | NY |
| 11 two anchors agree | avwap_flip rth + also globex: hold 1 / 2 / 3; avwap_touch rth + also globex: away 20 / 40 / 60 pts | 1, 5, 15; 5 | NY |
| 12 first pullback after the ORB break | orb_vwap_pb: or 15 / 30 / 60 | 1, 5, 15 | NY |
| 13 reclaim with volume | avwap_flip rth, hold 1: vol_m 1 / 1.5 / 2 | 1, 5, 15 | NY |
| 14 London VWAP side into NY | avwap_flip rth + also london: hold 1 / 2 / 3 | 5, 15 | NY |
| 15 longer lines | avwap_touch line globex / week / pdvwap (5, 15 NY; 5 London + Asia); avwap_touch pdh / pdl / onh (5 NY); avwap_flip line globex / week / pdvwap (5, 15); avwap_flip rth + also week: hold 1 / 2 / 3 (5, 15) | | NY, LDN+Asia |
NY = nyam + mid + pm; night = asia + london + eve (read as two groups: LDN = london, ON = asia + eve); caps 3 a pass (vwap_trend_pull
4, jj_fair 20 a day, win_break / orb_confirm / orb_vwap_pb / noise_band 1). Every reason is in the spec (`reason`).
Not built: a VWAP side gate for ANY entry (the open layer); the 18:00-anchor "two anchors" as a gate on other families.

## 4. A version and the selection, in-sample months only (SELECTION_HM40.md, written before any test month is run)
VERSION = one spec x one box (value x cell) x one session group of the spec. On its IS months:
- C1 win rate >= break-even of its realized reward-to-risk + 3 points;
- C2 net > 0, and > 0 with one extra tick a side ($10 a trade); the lane's worse-fills net is shown beside it;
- C3 beats the lane's random-entry pool (10 seeds, the ATR cell of the box's multiplier and target, the group's sessions): every seed
  (= the 95 % line at 10 seeds);
- C4 at least 0.66 trades a day (IS sessions): the rate that gives 200 trades on the ~290 OOS sessions;
- C5 the IS months from 2025-07 on (2025-07, 08, 10, 11, 12, 2026-02, 03, 04) net > 0;
- C6 its idea's average box (the mean of every box x group's average trade) > 0.
SELECTION_HM40.md: the in-sample table (top rows of every spec + the chosen versions), my recommendation of ONE box per spec where one
is chosen (the lane allows one pick per idea store), and which of them stack (different ideas / hours). Then I STOP. The owner picks
(`bp.py wf pick`) and says which boxes to run; only those run on the test months (`bp.py wf oos --owner-said=...`).

## 5. The pass bar on the test months (picked boxes only)
P1 win >= break-even + 3 points; P2 net > 0 and > 0 at +1 tick a side; P3 beats random entries on the same months and exits (the
lane's test-month read has no random control: the random entries of the box's exit cell on those months are part of the same read,
asked of the owner with the pick); P4 >= 200 test-month trades; P5 the fresh months (Sep 2025, Jan 2026, May 2026) net > 0; P6 (the
idea's average version) is judged on the in-sample months only (C6), since no other box's test months are run.
Stack: the passing boxes, one position at a time, every test month; >= 5 a day and P1, P2, P5 on the stacked trades.
Luck: N = boxes whose test months were read; ~5 % of N pass a 95 % random line by luck.

## Amendment A (2026-10-21 ~00:05 ET, before any result of this route exists)
The owner's answers of 2026-10-20 ~23:40-23:55 ET (vault `vwap-hunt-standing-word-2026-10-20`), binding from here:
- **Goal widened:** a PORTFOLIO, 5 trades a day minimum, aim 10+, higher win rate better; keep working (new ideas, new blocks, new
  variants) until it exists. Ideas: anything that passes (VWAP first; crosses, EMA / VWMA, volume, RVOL ...). Markets NQ + ES + GC, any
  hour (the legs will be automated).
- **Positions:** one per account, 5 accounts: up to 5 open at once; a signal is skipped only when all 5 are busy (the stack rule).
- **Per leg:** P4 = 100+ test-month trades (not 200); the PORTFOLIO needs 200+. Random line 95 % per leg, the luck count shown.
  "Valid" = the test-month pass (no drawdown or account bar). Old legs whose test months were read before: OUT, except the owner's
  VWAP pullback (idea 1, kept, labelled seen). A rule = its entries (family + settings + market + bar); new settings / bar / market /
  gate = a new rule.
- **Test months:** standing word -- "for now you can manually and discretionally pick the box and continue, i give you permission or
  freedom to continue without me, so yes standing word you pick by the written rule log every read and report when finished". I pick
  ONE box a store by section 4's rule (in-sample only) and run its test months (`bp.py wf pick`, `bp.py wf oos --owner-said=<those
  words>`); every read is in the one-read log and in LUCK.md.
- **Exits:** hm60 (the owner: add fixed-point stops) = hm40 + 15 / 25 / 40 / 60 NQ points (ES 4 / 6 / 10 / 15, GC 2.5 / 4 / 6.5 / 10)
  x the 5 targets: 60 cells (40 without the rule's own stop) x 3 setting values. Built and merged (main cb56bc82, with the hm40 merge).
- **Screening:** the first in-sample pass runs without the worse-fills stores (`--no-worse`, half the compute); a box is picked only
  after its store's worse fills are added (a second `wf run` without --no-worse does only that work) and its worse-fills net > 0.
- **Stages (in-sample only decides what runs next; no test month is opened to decide):** 1 = every idea at 5m NY; 2 = 15m NY;
  3 = 1m NY; 4 = night / London / Asia; 5 = ES and GC versions of the families with an idea average > 0 in-sample, and the new blocks
  (xflow ma_x, rvol_break; research ideas in RESEARCH_IDEAS.md that are new rules and build from the menu), each pre-registered here
  in an amendment before it runs.

## Amendment B (2026-10-21 ~00:10 ET, before any result of this route exists): the pick
- A version = store x box x session group. Chosen = C1-C6 of section 4 on the in-sample months, with: C2's extra tick = the market's tick
  value x 2 a trade (NQ $10, ES $25, GC $20); C3 = the box beats every one of the pool's 10 random seeds on the group's sessions (the
  lane's `beats_random` restricted to the group); a one-side spec must also beat the pool's random entries OF ITS SIDE (the pool's
  trades of that side only). C4 = 0.66 a day is kept for ranking only: the owner's per-leg bar is 100 test trades, so C4 becomes
  >= 0.35 a day (100 trades on the ~290 test sessions).
- THE PICK of a store (one a store, the lane's rule) = the MIDDLE of its chosen versions by in-sample average trade (the house's
  pipe_stages rule: never the best), after its worse-fills store is added and that box's worse-fills net is > 0 (else the next one
  toward the middle). A store with no chosen version is not picked. Picks are listed in PICKS.md BEFORE the test months are run.

## Amendment D (2026-10-21 ~01:25 ET, before any pick or test-month read): the review of the pick / grade scripts (29 agents)
- A version counts its WHOLE session group (a one-instance family listed as `nyam` trades mid and pm: those trades were being dropped).
- The fallback after a middle pick that fails worse fills goes LOWER first, then higher (pipe_stages._outward).
- The months are pinned for the whole hunt: HOMEBASE_WF_LAST=2026-05 (14 blocks; a data refresh cannot add a 15th block mid-hunt), and a
  store already run keeps its own in-sample days (lane commit 010e5f3b).
- Locks and test-month claims say who: "claude: the owner's standing word of 2026-10-20 (PREREG_HM40 s4 / Amendment B rule)".
- A failed job is never restarted; a test-month read is "done" only when its trades or its claim are on file; a claimed read that stopped
  counts as read and failed. A store already locked to another box is not read. Idea 1 is labelled "seen" (its fresh months are not fresh).
- C4 on the unrounded rate. A store whose random pool is not written yet is not read.
- The ledger cap: 120,000 -> 400,000 cells (the owner: "i dont care how many tries it takes, how many strategies run"); the luck count
  (LUCK.md) stays the guard against luck.

## Amendment E (2026-10-21 ~03:35 ET, before any further pick; 6 picks graded, all failed)
The 6 graded picks (ideas 2 and 7) made money on the 2022-23 test months and lost nearly every test month from 2024-09 on -- the
regime change the vault already recorded before this hunt ("each made money before mid-2025 and lost after"). C5 (net > 0 on the
in-sample months from 2025-07) did not stop them. From now on a version is chosen only if it also passes
- **C7: on its in-sample months from 2024-10 on (the blocks Oct-Dec 2024 .. Feb-Apr 2026, 15 months) alone: win rate >= break-even + 3
  points (row P3.15) and average trade > 0.**
The rule is from that prior knowledge, not from these 6 reads' numbers. Picks already locked stand as read. Guard against forking
paths: NO new rule is built because a test-month result suggested it (e.g. "fade the opening-range break because following it lost on
the test months"): those months are spent for that question; such an idea could only be judged on months nobody has read (from
2026-10 on).

## Amendment F (2026-10-21 ~03:50 ET, before any further pick)
- **C8: the version's net is > 0 in at least 9 of the 14 in-sample blocks AND the block t-statistic (mean / its standard error over the
  14 blocks) is >= 2.** Reason (not tuned on any test result): with wide stops a few big months carry an in-sample average, and the trades
  of one day are one bet, so per-trade statistics overstate the evidence; the blocks are the honest unit.
- CALENDAR.md: the blocks always test on Jan / May / Sep, the months where breakout / trend rules on NQ were weakest on the build days.
  Reported to the owner; the layout is his (not changed).
- **Batch 3 (make_specs.py --batch-f):** VWAP pullback (jj_fair) on ES and GC; fvg_oside, first_bar_mom, vwap_touch and orb_vwap_pb on ES
  and GC; first_bar_mom on NQ 5m (every session). New markets / bar sizes = new rules; the reasons are in the specs.

## Amendment G (2026-10-21 ~04:25 ET, before any further pick; 16 graded, 0 passed)
- **C9: the version is net positive in at least 8 of the 9 in-sample calendar months (Feb, Mar, Apr, Jun, Jul, Aug, Oct, Nov, Dec, each
  pooled over the years).** Reason: CALENDAR.md (old build-day stores, read long ago): breakout / trend rules lost in exactly the calendar
  months the blocks test; a rule that pays only in some calendar months is not picked. Not tuned on these 16 reads.
- The 18 reads so far stand (LUCK.md). The owner was asked whether trend rules should get a shifted layout; my own note since: a shifted
  layout cannot be a clean test any more (its test months are in-sample months here and were read), so the standard blocks stay.

## Amendment H (2026-10-21 ~06:45 ET, before any result of this idea; 21 graded, 0 passed)
- **Idea 26: rv_fade, a new block (engine/families/relval.py, tests engine/tests/test_relval.py).** At each tf close: the own market's
  1-minute move over the last `look` minutes that its partner (NQ <-> ES) does not explain (beta-adjusted running gap, its z); z >= k ->
  short the leader, z <= -k -> long the laggard. Market entry, no structure level (the hm60 ATR / fixed-point stops), hold_to day.
- Why (prior knowledge, not any result of this route): the vault note high-freq-1perday-edge-NQ-only (2026-06-25, another project and
  data): ES/NQ ratio reversion was the one robust high-frequency mechanism on ES (~1.8 a day, every year positive) when every
  single-market momentum and fade rule on ES failed. It is a different mechanism class from every idea 1-25 (one market's own price).
- Main setting k = 1.5 / 2.0 / 2.5 (look 60 fixed); one neighbour spec with look = 30 / 60 / 120 (k 2.0). NQ and ES; 1, 5 and 15-minute
  bars in New York (nyam + mid + pm, 4 entries a session), 5-minute bars at night (asia + london + eve).
- What was seen before this note: a smoke run on 8 in-sample days (2023-03-01 .. 03-10, nyam, 5m): trade COUNTS and the long share only
  (11-31 trades per k); no net, win rate or average was printed or read.
- Selection C1-C9, the pick and the pass bar are unchanged. The mirror (follow the leader) is NOT run: one hypothesis, fewer tries.

## Amendment I (2026-10-21 ~07:29 ET, before any result of these rules in this route)
A read-only research workflow (8 agents: vault, literature, blocks, in-sample table -> a designer -> 3 judges: prior, feasibility, risk;
no agent ran a backtest or opened a test-month file of this hunt) proposed 13 candidates; 8 were kept by 2 of 3 judges. Taken, with the
judges' fixes:
- **Idea 27: onr_orb** (the 09:30 open's third of the 01:00-09:30 range sets the day's side; an opening-range break that way on an ADX
  day; earliest 10:30, k 0.3, ov_from 01:00), 15m, nyam. Main **adx_min 10 / 15 / 20** (25 would give < 100 test trades). NQ and ES.
  The NQ store is labelled **SEEN (proxy)**: its 10:00 twin (an older route) was read on 2025-07 .. 2026-10, so the test months Sep 2025,
  Jan 2026, May 2026 are not blind for this rule; its pass is also reported on the 12 test months Jan 2022 .. May 2025 alone. The ES store
  is a twin of the same rule, never tuned on ES. The rule flattens at 15:30 itself (as taught).
- **Idea 31: rvol_break on ES and GC**, 15m, NY (n 20), main **m 1.0 / 1.25 / 1.5** (the NQ 15m store of idea 17 was the broadest
  in-sample pocket; m 2+ trades too little). Counted in LUCK as the same mechanism as idea 17 (its 5th and 6th stores).
- Left out (and why): GC onr_orb (the code reads the 09:30 equity open, not gold's own), NQ / ES day_move and the quiet-day sweep fade
  (new blocks; NQ versions seen), ES fvg_oside 30m and GC jj_fair 15m (rescue forks of stores that failed in-sample), NQ 15m two-anchor
  touch, ES orb_confirm long, NQ rvol_break 30m (risk judge: no clean months).

## Amendment J (2026-10-21 ~08:30 ET): the owner drops the +3-point cushion, for now
The owner's words (2026-10-21, after the near-miss table): "lets remove the +3 point above be requirement for now, lets still continue with
them, yeah if its plus 3 the better but i want to continue on these, still let the strategies pass after and lets just decide what to do
with them at the end".
- **P1 and C1 (and C7's win-rate part):** win rate >= the break-even of the version's own realized reward-to-risk (cushion 0, was +3
  points). Every row and grade shows the MARGIN (win rate - break-even, in points) and whether it is >= +3 ("+3", the better ones).
- The other bars are unchanged: P2 net > 0 and > 0 at +1 tick a side, P3 the random line on the test months, P4 >= 100 test trades,
  P5 the fresh months (2025-09, 2026-01, 2026-05) > 0, C6 the idea average > 0; C2-C5, C8, C9 at selection.
- **The 25 grades already written are re-graded on this bar** (the reads are the same; no test month is run again). Stores with no chosen
  version under the old C1 are looked at again; a store already picked keeps its pick (one read a store).
- The shared house config (pipe_gates / edge.wr_cushion) is not changed: only this hunt's reader (hmread.edge) and grader use 0.
- The owner decides what to do with the passes at the end.

## Amendment K (2026-10-21 16:52 ET, after CHECKPOINT_1, BEFORE the rule below is run): one stack, judged forward
The owner's words: "Option 1: stop the test-month reads. Write one stack of 8-12 NQ New York rules from the in-sample zone by one
rule, port them, and judge the whole stack once in shadow on new days."
- **No more test-month reads in this hunt.** HOLD_PICKS stays for good; the runner stays off.
- **THE ONE RULE** (in-sample months only, the pinned 14 blocks, the Amendment-J reader hmread.read_store / chosen):
  - S1 universe: the hunt's stores with market NQ, bars 5 or 15, whose spec trades the New York sessions; their versions of group NY.
  - S2 the idea is not dead: the idea's average trade over all its in-sample versions > 0.
  - S3 breadth: more than 50 % of the store's NY boxes have an in-sample average trade > 0.
  - S4 wide exits only: stop ATR x2, own x1 / x1.5 / x2, or 60 NQ points; target 1.5R or 2R (CHECKPOINT_1 (j): the only exit
    shapes that clear costs broadly, in-sample).
  - S5 the version passes C1-C9 as they stand (C1 = win rate >= its break-even, Amendment J) and its worse-fills net > 0 where the
    store's worse fills are on file (else C2's net after 2 extra ticks a trade > 0 stands for it).
  - S6 the store's pick: the middle of its S4+S5 versions by in-sample average trade (the lower middle; never the best).
  - S7 one store per idea x family: the one with the larger S3 share (a tie: the 15m store).
  - S8 the stack: the stores in order of S3 share (descending; a tie: more in-sample trades a day first), added one by one until there
    are at least 8 rules AND their in-sample trades a day add up to at least 5; at most 12 rules; stop early at 10 a day once there
    are 8. Fewer than 8 qualify: all of them, and the shortfall is said.
- Not used in any way: test-month numbers, grades, LUCK, the SEEN labels (a forward test does not care what was read before).
- The 3 Amendment-J rules already in shadow stay as they are; if the rule picks one of their exact store + box, that copy is the leg.
- Ports: one Lab draft per New York session instance, exact parity with the engine on the in-sample months before promotion.
  A limit-entry rule can be shadowed but not booked (noted on it). No money.
- The stack's shadow bar is written before its first shadow day (STACK_BAR.md) and the stack is judged ONCE, as a whole.

## Amendment L (2026-10-21 20:08 ET, before any port or forward day of these rules): stack B
The owner's words: "Yes: pre-register stack B as drafted (2 VWAP rules), port the 4 copies with exact parity, and run them in shadow on
the Mac." The rule is STACKB_DRAFT.md section 2, as written there:
- **B1-B7** = Amendment K's S1-S7 (their output: the 5 stores of stack.json "rest").
- **B8:** the pick's in-sample daily net (NY sessions, 883 days, $0 on a no-trade day) correlates with stack A's (its 8 picks summed)
  at <= 0.475 (Pearson; the median over A's members of each one's correlation with the other 7). Said plainly: the cap was set with
  the 5 correlations on screen (0.27 / 0.30 / 0.56 / 0.61 / 0.73); any cap from 0.30 to 0.55 picks the same 2.
- **B9:** lowest correlation first; at most 12 rules; stop at 10 a day; under 5 a day: all of them, the shortfall stated.
- **Result (in-sample): 2 rules, 2.42 trades a day, +$107 a trade, correlation 0.34 with A** -- short of 5 a day, said here:
  B-1 vh_i11_touch_gx_5_ny box away160_pts60-r2 (avwap_touch: the 09:30 VWAP with the Globex VWAP on the side, limit entry,
  shadow-only; nyam / mid / pm: 3 drafts); B-2 vh_i1_pb_5_ny box vwap_slope60_pts60-r2 (jj_fair, one instance to 15:00, max_tr 20).
- The engine file of B-2 (engine/families/jj_fair.py) is not in git (someone else's work, not committed by me). Frozen as the port's
  reference: hm40/frozen/jj_fair.py, sha256 04addad41583c9357bd00fcc8fa976ba4aa0b3ba5fc0841d7d9492fa5707207f (= the store's code stamp 04addad41583c935).
- Judged on its own, ONCE, by STACK_BAR.md's section "Stack B". Not used: test months, grades, LUCK, SEEN labels. No money.

## Amendment M (2026-10-21 20:12 ET, before the check below is run and before any shadow day): the middle-third skip
The owner's words: "Yes: restart testing on the in-sample months, starting with the middle-third skip as one written filter checked on
every rule; anything good goes to shadow."
- **THE FILTER (one definition, every rule):** a trade date is a MIDDLE day when the 09:30 ET open (the open of the first 1-minute bar
  from 09:30, at most 5 minutes late; else not a middle day) lies in the middle third of the 01:00-09:30 ET range of that date's
  1-minute bars (onr_orb's read_bias: lo + third <= open <= lo + 2 x third; a flat range = not middle). The skip = no entry on a middle day.
- **Where it came from (said plainly):** found 2026-10-21 in the in-sample months while drafting stack B (STACKB_DRAFT.md s5, onr_side_study):
  the average box of 61 NQ stores made +$1.5 a trade on middle days vs +$27.3 on other days (48 of 61 stores; ~30 % of trades). So an
  in-sample re-check CANNOT prove it; it can only show whether it holds across time and rules. The proof is forward.
- **In-sample check (mid3_check.py, every NQ New York store on file, every box, the hunt's reader; run once, results as they come):**
  per store the share of trades on middle days and the average trade on middle vs other days; the same split by halves (2021-10..2023-12
  vs 2024-01..2026-04) and by year. EXPECTED, written now: it holds (other > middle) in >= 70 % of stores in BOTH halves and in >= 4 of
  the 5 full years. If it holds only in one half or only in some years: a weak lead, reported, not used. Either way nothing is re-picked:
  stack A and B stay as they are (no re-tuning on the same months).
- **Forward test (the only proof), FREE: no new copy.** The skip removes whole days, so its forward record = the shadow trades of
  stack A, stack B and the 3 J rules split by day tag (STACK_REPORT.md tags every shadow day middle / other from the day's own prints).
  Read at the stacks' own read dates (2027-04-22; B 26 weeks after its day 1), ONCE: PASS = over all shadow trades, the average trade on
  OTHER days minus the average on MIDDLE days is >= 1 standard error of that difference (t >= 1) AND the other-day average is > 0 AND
  middle days hold >= 20 % of the trades. Then and only then the skip is written into the Desk copies (a new promotion, a new bar).
  Not read before that date; not used to switch anything on or off meanwhile.

## Note N (2026-10-21 20:14 ET, before it runs): the day-type study (exploratory, in-sample, nothing picked from it)
The owner (restart testing on the in-sample months). A read-only study across every NQ New York store, like the side and middle-third
studies: a few DAY features known before or at 09:30 (the overnight range vs the 20-day ATR; the 09:30 open's gap vs yesterday's close;
the 01:00-09:30 range's position; the 18:00-09:30 drift's sign and size), each cut in thirds, and the average box of every store on
each third, by halves. EXPECTED (written now): every feature that holds in >= 70 % of stores in BOTH halves is a lead; one that holds in
one half only is noise. A lead is NOT applied to any stack in-sample (no re-picking). It becomes a day tag in STACK_REPORT.md with its own
written forward bar (as Amendment M) and is read once at the stacks' read dates. Found-in-sample leads prove nothing in-sample.

## Amendment O (2026-10-21 22:29 ET, before any of these runs): batch 4 -- every untried family, and two new blocks
The owner's words: "i want you to keep building and testing, build more strategies, keep going".
- **Batch 4a (no code): every bar-based NQ family of the engine not yet run in this hunt**, except those that rest orders on both sides at
  once (ib break, lon_break, orb, win_bracket, straddle, ib_n, squeeze's inside / nr7: banned) and those without three values of one main
  setting (disp_oside, ema_ribbon, mid_fade, hurst_ac_break, gap, ib). NQ, 15-minute bars (5-minute too for the candle / bar-shape rules),
  New York sessions (a family's own session where fixed), hm60 exits, max_tr 3, dir both (vwap_adx long only). Main = the library's own
  variant axis, 3 values. A spec the toolkit refuses is dropped and listed.
- **Batch 4b (new blocks, built with tests, committed on their own):** (1) the gate kind "onr_side" in the open layer (families/_flex.py +
  flexind.py): an entry only on the side the 09:30 open's third of the 01:00-09:30 range gives (onr_orb.read_bias; middle third: no entry)
  -- the +1.4-point in-sample lead of onr_side_study, as ONE gate every gated family can take; (2) the family "day_move": at `at` (15:00),
  if the 09:30-`at` move is >= k x the 20-day daily range, market with the move, held to the day's flat (the late-day momentum of
  Gao-Han-Li-Zhou 2018; the research workflow's idea 28, never built). Specs: the 8 stack-A families x gate onr_side (with), 15m NY;
  day_move NQ 5m pm, k 0.15 / 0.25 / 0.35.
- **Judged (in-sample) by the same S1-S8 of Amendment K, over all stores on file, after batch 4 is complete:** the stack rule is re-run as
  "stack C" = what S8 adds beyond stacks A and B (a store already in A or B is not re-picked), with B8's correlation cap vs A + B. What
  qualifies is ported with exact parity and goes to shadow with its own bar (STACK_BAR.md). EXPECTED: a few of the 25 families reach S3's
  breadth (> 50 % of boxes positive); the onr_side gate lifts the gated versions' win rate by ~1-2 points and cuts trades to ~40 %.
- No test month, no grade, no LUCK read for any of this. HOLD_PICKS stays.
