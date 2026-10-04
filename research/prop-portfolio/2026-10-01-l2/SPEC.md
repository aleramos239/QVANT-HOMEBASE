# NQ Level-2 prop portfolio: build spec (shared by every agent) — 2026-10-01

Root `L = ~/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/`. Previous pilot (reuse its code, do not
edit it): `R = ~/ramos-quant-homebase/research/prop-portfolio/2026-09-29/` (read `R/SPEC.md`, `R/progress.md`,
`R/FUNDED_RULES.md`). Repo `~/ramos-quant-homebase`. Learnings: `~/Obsidian/Vault/30-Projects/Onyx-Trading/
prop-pilot-learnings.md`, burned-data ledger `.../Onyx-Trading/burned-data-ledger.md` (grep it: OFB, delta, 930).

## House rules (every agent)
* NEVER touch the live desk (port 8850), `homebase/` code, or `~/.homebase`. Read-only on R. Never commit.
  Never place/cancel orders. Write only under L (and the scratchpad).
* Python: `~/ONYX TRADING/.venv/bin/python` (numpy, pandas, pyarrow). `/usr/bin/python3` has numpy+pandas, no
  pyarrow. R's evalcore/funded run under either.
* OFFLINE COMPUTE WINDOWS: no heavy job (multiprocessing, searches, MC) runs 09:18–09:36 ET weekdays, and on
  Fri 2026-10-02 also 08:15–08:50 ET (live NFP trade). Check the ET clock before each batch and between batches;
  sleep until the window ends. ≤ 8 worker processes.
* The tester (8852) is NOT used for L2 work (it has no book data). If an agent needs a tester run it goes through
  `R/hb.py` only (the single job submitter) — avoid unless the spec says so.
* Holdout `2025-01-01 → 2026-07-08` is SEALED: no agent reads any L2/tick/flow row dated ≥ 2025-01-01 unless the
  orchestrator says "holdout". Loaders enforce it (`allow_holdout=False` default → raise).
* "less is more": 1 trigger + ≤ 2 filters per config, ≤ 2 family params.

## Data (NQ only)
| layer | path | span | notes |
|---|---|---|---|
| OFB ladder snapshots | `~/Downloads/Desktop - Alejandro’s MacBook Pro/OFB_data/globex/nqv0_*.depth.bin` | 2017-06-01 → 2026-07-08 | 1/min, 64 lv/side main file; each side = best-first near book (~42 lv) THEN unordered far-cluster slots. Reader: `~/ONYX TRADING/onyx/lab/ofb.py` `DepthReader` (its BASE path is stale: pass paths). |
| OFB hist (64 slots) | same dir `*.hist.bin` | same | vendor features (size_imb, pulled, iceberg, qdepl, cum_delta…) — RESEARCH TIER ONLY (not reproducible live). |
| OFB bars | same dir `*.bars.csv` | same | ET wall clock, UpVol/DownVol are TICK-RULE (ledger: do not use as aggressor delta). |
| ticks + prev-minute OFB | `~/futures_derived/ofb_tick/NQ/YYYY/MM/date.parquet` (`~/ONYX TRADING/research/ofb_tick.py load_session`) | 2021-09-22 → 2026-09-22 | every print; prev_* = last COMPLETED minute (lag applied). Execution tape. |
| own flow | `~/futures_derived/flow_1m/NQ.parquet`, `flow_tape/NQ/...` (`research/flow.py` in ONYX) | 2021-09 → 2026-09 | tick-rule delta, sweeps, big prints — reproducible live from the desk tick feed. |
| desk live book | `~/futures_depth/NQ/2026/*.depth.jsonl.gz` | 2026-09-25 → | Tradovate DOM, 10 lv/side, ≤ 4 lines/s. 6 days: for live-parity design only. |

**Deployable tier (selection allowed):** features computable live by the desk = (a) book features from the TOP 10
NEAR-BOOK levels per side of a snapshot sampled once per minute (drop OFB far-cluster slots), expressed RELATIVE to
the best price (level index / tick distance, sizes) — never absolute prices (OFB nqv0 rolls ~1 day earlier than our
tape; also skip book signals on roll day and the day before); (b) tick-flow features from our own flow layer.
**Research tier:** OFB hist vendor slots — may be reported as "would-help-if-we-had-it", never promoted.

**Timestamp law:** a feature stamped for minute M is usable only for decisions at ≥ the END of minute M (verify the
depth.bin stamp convention from data — start-of-minute vs end — with evidence, e.g. best bid/ask vs the tick tape
around the stamp; document in `L/DATA.md`). Decision at a minute boundary → execution on the first print AFTER it.

## Firms / accounts (score every config under all; Apex flagged UNCONFIRMED where rules are unconfirmed)
Eval: `lucid` (Flex 50K), `lucidpro` (+$1,200 soft DLL), `lucidpro_nodll`, `apex` (Legacy 50K), `apex_eod` — rule files
`homebase/backtest/propsim/rules/*.json`, semantics exactly as R/evalcore.py.
Funded: Flex, Flex+DLL, Pro DLL, Pro noDLL, Apex 50K PA (R/funded.py, R/FUNDED_RULES.md) + NEW `apex300_pa`
(Apex Legacy 300K PA — the user OWNS FIVE of these and wants something to run on them). Its rules must be
researched (Apex help centre; defuddle) and written to `L/APEX300_RULES.md` + a funded.py-compatible params module:
trailing threshold (intraday incl. open P&L), max contracts and the half-size rule until the safety net, 30% MAE
(negative P&L) rule, 5:1 stop/target, one-direction (no working orders both sides → straddles/OCO entry brackets
NON-COMPLIANT), consistency 30%, min trading days, payout min/max per request, split. Flag every value you could not
confirm. Model from a fresh PA (balance = 300,000) AND a sensitivity at +$3,000 / +$7,600 cushion (the user's
current balances are unknown).
Breach models: eod / realized / intraday as in R. PRIMARY: Lucid = realized (as before) but ALWAYS show intraday
and use intraday robustness as the tie-break; Apex eval/PA = intraday (Apex is real-time).

## Baseline to beat (current approved picks; re-score them on EXACTLY the L2 windows from existing bundles)
Flex eval straddle-tf30#10 nyam · Pro noDLL eval straddle-tf30#9 nyam · Flex funded straddle-tf30#32 pm ·
Pro noDLL funded orb-tf5#10 mid · Pro DLL funded donchian-tf15 pm · Apex PA donchian-tf15 nyam (see R/out/*summary*).
Lucid Pro DLL eval and Apex eval had NO passing pick (bar = the 60% criterion).

## Families (PRE-REGISTERED; default params ARE the screen; signals at minute boundaries only)
Common inputs as R/SPEC.md (tf 1|5|15 decision cadence, sess asia|london|nyam|mid|pm|all split offline, dir,
stop_mode atr|pts|struct, stop_val, tgt_r, trail_atr, exit_bars, max_tr ≤ 3, no entries last 5 min of session).
Book (deployable):
* B1 `bimb_follow` — top-N imbalance I=(ΣB−ΣA)/(ΣB+ΣA), N∈{3,10}; z vs trailing 60 min; z ≥ k → follow heavier side.
* B2 `bimb_fade` — same trigger, fade.
* B3 `thin_side` — one side's top-10 depth falls ≥ x% vs its trailing-15-min median → enter TOWARD the thin side.
* B4 `wall_bounce` — a level ≥ m × median level size within 10 levels, price within 2 ticks → limit fade at it, stop beyond.
* B5 `wall_break` — a wall standing ≥ 2 snapshots is gone and price traded through it → follow (stop entry).
* B6 `depth_regime` — FILTER only: total top-10 depth vs its 20-day same-time-of-day median (thin book = vol regime).
Flow (deployable):
* F1 `delta_follow` — minute |delta| in trailing top decile and bar closes with it → follow.
* F2 `absorption` — top-decile |delta| minute with |price change| ≤ 0.25 ATR → fade the aggressor.
* F3 `cvd_div` — new session high/low without a new session cum-delta extreme → fade.
* F4 `sweep_follow` — sweep order ≥ X contracts over ≥ 3 levels → follow.
Session open (single-direction ⇒ Apex-compliant):
* O1 `open_dir` — at 03:00 / 09:30 / 11:05 / 13:30 pick the side from the pre-open book imbalance (+ optional pre-open
  flow) and enter ONE side (market or stop at ± off_atr), exits as straddle family. NOTE ledger: the 9:30 delta-only
  direction family was REFUTED (2026-09-23); a delta-only variant is a revisit and must be labelled so.
Gates on approved strategies (G): apply B/F features at each approved trade's entry (last completed minute before
entry_ms) to the EXISTING in-sample tester trade lists: G1 skip if book opposes the side, G2 trade only thin-book
days (B6), G3 size ×{0.5,1,1.5} by the feature tercile. Gates count as screening configs.
Controls (mandatory): C1 day-matched random entries with the same exit profile (as R); C2 FEATURE-SHUFFLE null —
the same family with its L2 feature series replaced by the same time-of-day series from a random other session
(tests whether book information adds anything beyond timing/structure). Promotion needs lift > 0 vs BOTH.

## Execution (offline tick sim `L/l2sim.py`, on the ofb_tick tape)
Pessimistic, matching the tester: market = first print after decision + 1 tick slip; stop entry fills at trigger +
1 tick; limit fills only on a trade THROUGH by 1 tick; SL = stop ∓ 1 tick slip; TP limit trade-through; a print that
hits both SL and TP → SL; commission $4.00 RT per NQ; qty 1 NQ, resized offline (R conventions). Output trades in
the R trades.json schema (date, side, qty, entry/exit price, exit_reason, gross, commission, net, mae/mfe usd+pts,
entry_ms, exit_ms) so R/evalcore + R/funded consume them unchanged. VALIDATION GATE: replay ≥ 3 approved tester
strategies (straddle-tf30#10 nyam, orb-tf5#10 mid, donchian-tf15 pm) in-sample and match the tester bundles
(trade-level ≥ 95% identical entries/exits, total net within 2%) — no screening before this passes.

## Caps (hard, never relaxed): screening runs ≤ 400 (a run = family × tf × dir default, all sessions, + controls;
gates count 1 each), grid cells ≤ 3,000, walk-forwards ≤ 15. Track in `L/ledger.csv` and `L/progress.md`.

## Pipeline
0 Build+verify (data layer, sim, Apex 300K rules, evalcore/funded adapters) → A screen (+C1,C2) → B tune grids +
rules search per firm (R/search_rules conventions incl. day_take/target_take/day_lock/day_stop/max_day_tr) + funded
search → C offline walk-forward (quarterly, trailing-12m selection, OOS lift vs controls) → D freeze manifest
(sha256: configs, code, inputs) → E holdout 2025-01-01→2026-07-08 ONCE + early-sample check 2017-06-01→2021-09-21
on OFB 1m bars (bar-fill pessimistic; pre-registered, once) → F report (HTML+PDF) + vault learnings.
In-sample = 2021-09-22 → 2024-12-31.

## Promotion criteria (never relaxed)
Eval: holdout P(pass ≤ 5d) ≥ 0.60 (primary model) AND ≥ the approved pick on the same window AND lift > 0 vs C1 and C2.
Funded: holdout E[$ to trader in 40 trading days] > approved pick on the same window, P(bust before 1st payout) not
worse by > 5 pp, lift > 0 vs controls. Apex: compliance mandatory (one direction, stop ≤ 5×target, MAE rule).
Deployable tier only. If nothing beats the approved pick, say so plainly and keep the approved pick.

## Build findings that OVERRIDE the text above (2026-10-01 21:20 ET; reports in out/build_reports/)
* Timestamp: a depth/hist row stamped M = the book ~59.0–59.98 s into M (END of minute). usable_at = M + 60 s. Margin is as
  thin as 0.02 s in some months → the holdout build must run a per-month phase check; live must sample at/before M+59.0 s.
* Roll: OFB nqv0 rolls AFTER our tape (not before). book_ok=False on roll day −1, 0, +1, and the first evening hours of +2
  still carry the old contract (needs a per-minute mismatch flag before stage E).
* Sim gate PASSED: l2sim reproduces the tester bundles 100% (7 picks, 88 grid cells). Use `ctx.feat` / `ctx.feat_window`
  only (never read l2data directly from a family). Template in l2sim.py; reference families in l2ref.py.
* Scoring: score.py (file/list/bundle sources → R numbers bit-identical). Pro noDLL eval baseline = straddle-tf30#10 nyam
  (R manifest; #9 ties). apex300_pa via apex300.py (`apex300.flags`, `apex300.GRID`, start states fresh/plus3000/plus7600).
* APEX (see APEX300_RULES.md): $7,500 intraday trail, locks at +$7,600 → threshold $300,100; 35 minis, half until EOD balance
  > $307,600; MAE limit = 30% of start-of-day profit, min $2,250 (the binding size constraint); stop ≤ 5× target; one direction;
  8 days / 5 ≥ $50 / 30% consistency; payouts min $500, max $3,500 (1–5); 100% of first $25k.
  ACCOUNT-LEVEL: (1) Apex PROHIBITS automated/algorithmic trading on PA accounts (closure + forfeiture) — user decision before
  any deployment; research continues, picks for apex300 must be simple enough to execute by hand / semi-manually and are labelled so;
  (2) no opposite positions across the user's Apex accounts → the five PAs must share ONE direction per moment (model the five as
  copies of one account, or same-direction strategies only); (3) consistency base unconfirmed → report BOTH readings, select on
  the conservative one (profit since last payout); (4) half size = 170 micros (conservative).
* Desk DOM recordings have multi-hour outages on 2 of 4 days and run ~30% thinner than OFB → prefer ratios/z-scores, never
  thresholds in contracts; live parity cannot be proven until an overlapping OFB pull exists (follow-up for the user).
* B4/B5 wall price: take the absolute best from ofb_tick prev_best_bid/ask (tape-coordinates), not the tape close.

## Stage A screen — pre-registered defaults (2026-10-01 23:00 ET; written BEFORE any family was run)
Common (as R template defaults unless stated): stop_mode atr, stop_val 1.5, tgt_r 2.0, trail_atr 0, exit_bars 0, max_tr 3,
dir both, sess all (split offline). ATR = Wilder ATR(14) on tf bars. Screen cadence tf ∈ {1, 5}.
* B1 bimb_follow / B2 bimb_fade: imb10, z-score over the trailing 60 usable minutes, trigger |z| ≥ 2.0 at a tf-bar close.
  Param 2: N ∈ {10 (default), 3}.
* B3 thin_side: one side's b10_rel15/a10_rel15 ≤ 0.60 while the other side's ≥ 0.90 → enter toward the thin side.
* B4 wall_bounce: wall = max level size ≥ 5 × median level size, ≤ 10 levels from best, price within 2 ticks of it at the
  decision → limit entry 1 tick in front of the wall, stop 4 ticks beyond it (floor 0.25 ATR), tgt_r 2.0. strict_limit=True.
* B5 wall_break: a wall (same definition) seen on ≥ 2 consecutive snapshots is gone and the last price is beyond its price
  → stop entry 1 tick beyond in the break direction, struct stop = wall price ∓ 4 ticks (floor 0.25 ATR).
* F1 delta_follow: tf-bar |delta| ≥ 90th percentile of the trailing 60 tf bars and the bar closes in the delta's direction → follow.
* F2 absorption: same |delta| trigger and |close − open| ≤ 0.25 ATR → fade the delta's direction.
* F3 cvd_div: tf-bar close makes a new session high (low) while session cum-delta is below (above) its session extreme → fade.
* F4 sweep_follow: sweep volume in the tf bar ≥ 95th percentile of the trailing 60 tf bars (and > 0) → follow the sweep side.
* O1 open_dir: opens 03:00, 09:30, 11:05, 13:30 ET; side from `src` ∈ {book: sign of mean imb10 over the last 5 usable minutes;
  flow: sign of Σdelta over the last 15 minutes (REVISIT of a refuted family — label); both: only when they agree};
  entry = stop at ± 0.25 ATR30 in the chosen direction (cancel after 60 min), stop 3 ATR30, no target, flat at session end,
  max 1 trade per session. tf fixed (decision at the open).
* B6 depth_regime (filter `f_depth` off|thin|thick, default off): thin = depth10_rel20d ≤ 0.8, thick ≥ 1.2. In the screen it
  is tested ONLY as gate G2 on the approved picks, and later (stage B) as an optional filter on shortlisted families.
* Gates on the 6 approved picks (in-sample tester trade lists; feature = last usable row before entry_ms):
  G1 skip if sign(imb10 5-min mean) opposes the trade side; G2 trade only thin days (f_depth thin at entry);
  G3 size ×1.5 / ×1 / ×0.5 by tercile of |imb10 z| aligned with the side (terciles from the trailing 250 sessions only).
* Controls: C1 day-matched random (R pools via score.py); C2 feature-shuffle null, 2 seeds per real run.
* Firms scored: lucid, lucidpro, lucidpro_nodll, apex, apex_eod + funded flex, flex_dll, pro_dll, pro_nodll, apex50_pa,
  apex300_pa (fresh; conservative consistency) + apex300 EVAL ($20,000 target, $7,500 intraday trail, 35 minis, 7 min days →
  report P(pass ≤ 10 / 20 days); the 5-day criterion cannot apply to it).
* Run cap accounting: each real run 1, each C2 seed 1, each gate 1. No default may be changed after its first run.

## USER FACTS 2026-10-02 07:20 ET — OVERRIDE everything above
* LUCID'S DRAWDOWN COUNTS OPEN LOSSES. PRIMARY breach model for EVERY firm (Lucid Flex / Pro / Pro noDLL, eval and funded,
  and Apex) = `intraday`. `realized` / `eod` are reported only as side columns. All selection, shortlists, lifts and the
  promotion criteria use intraday. The approved picks from the 2026-09-29 pilot are no longer a valid bar under intraday
  (they collapse: 2% / 20% pass; $17 / $0 funded) → the bar per account type = the best intraday-model pick of the old
  pilot (being re-ranked in ../2026-10-02-intraday) and the optimised zero-edge null (~0.40 Pro, ~0.31 Flex).
* Data is final: OFB history only (ends 2026-07-08; no live OFB, no fresh pull, nothing can be bought). Live = Tradovate
  Level 2 (10 levels) + ticks. Deployable tier stays exactly as defined; vendor slots and far clusters are never promoted.
* User approved (2026-10-02): raise the run cap (new caps: signal-study tests unlimited but every claim must beat the
  best-of-all-nulls; full strategy runs ≤ 2,000; grid cells ≤ 10,000; walk-forwards ≤ 40); three periods (build
  2021-09-22→2023-12-31, pick 2024, exam 2025-01-01→2026-07-08); more strategy ideas; L2 as FILTERS and EXITS on the
  strategies already tested in the old pilot (its 1,283 configs / bundles), not only as the base signal; smarter
  combinations (signal search separate from rules search; combine survivors with low loss-day overlap).

## APPROACH CHANGE (user-approved 2026-10-02 ~07:50 ET): EDGE LIBRARY → STACKS
Goal is no longer "one best strategy per account". It is: (1) build a LIBRARY of strategies with a real edge and tight
stops; (2) build each account's STACK from library members whose losing days overlap least, under the intraday rule.
* Library dir: `~/ramos-quant-homebase/research/edge-library/` — one folder per member: spec (family, inputs, session,
  instrument), trades (1 contract, R schema), daily series (net, worst open loss, time in market), evidence card.
* Admission (all on build 2021-09-22→2023-12-31 + pick 2024; never on the exam): net > 0 after costs in BOTH periods;
  beats its own shuffled/random nulls and the best-of-all-nulls bar for its search batch; still > 0 with 2 ticks + 250 ms;
  per-trade open-loss risk small enough to size inside $2,000; ≥ 100 trades. A member too weak to run alone is still admitted.
* Sources: the old pilot's 1,283 configs re-searched with tight stops; L2 families; L2 as filter / exit on old configs;
  new signal-study survivors; existing live algos (nq930, gc_nfp as event members). Other markets for non-L2 members only
  if the user approves (pending question).
* Stack builder: ≤ 4 members per account, equal-risk sizing (no optimised weights), chosen on the pick year by lowest
  loss-day overlap + combined open-loss fit; scored per account type (eval: P(pass) at 5/10/20/40 days + bust; funded:
  E$ to trader, bust). Exam 2025-01-01→2026-07-08 ONCE on the frozen stacks. Speed-vs-odds table always shown.
* USER 2026-10-02 ~08:00 ET: ES and GC are approved for NON-Level-2 library members (Level 2 stays NQ only).
  ES: reuse the ES pilot (../2026-09-30-es: bundles, tuning) re-searched with tight stops under intraday. GC: new tester
  screen through R/hb.py (the only job submitter; quiet windows apply). Old-pilot hindsight (2025-26, 1 NQ, raw): straddle-tf30
  nyam +116k..+237k and pm +60k..+94k (uncapped), donchian-tf15 mid positive 5/6; donchian pm and first_bar_mom nyam FAILED.
  The daily take caps destroyed the straddles' edge; candidates enter the library uncapped at micro size.
* USER 2026-10-02 08:40 ET — "the simple the better when it comes to overfitting, the edge must make sense": library
  admission ALSO needs (a) a one-sentence rationale written BEFORE the test (who is on the other side / what flow it rides /
  why it persists), (b) a complexity count (rules + free parameters) — ties go to the simpler member, (c) the effect must
  hold across neighbouring thresholds and not live in a single session/threshold without a reason. Hypothesis-first, no blind grids.
