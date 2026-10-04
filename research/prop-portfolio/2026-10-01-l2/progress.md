# NQ Level-2 prop portfolio — progress (read me first on resume)

Brief (user, 2026-10-01 ~19:40 ET): "build a separate portfolio ... same thing with level 2 data"; "the best for each
eval and funded"; "i currently have 5 300k legacy apex fundeds so i want to run something on them"; build on NQ;
"maybe also create new strategies around the new data". Spec: SPEC.md (pre-registered families, caps, holdout).

## Decisions
- NQ only (L2 history = OFB 1/min ladders 2017-06 → 2026-07-08; no ES/GC/SI book history).
- Deployable tier = top-10 near-book snapshot features (relative to best) + own tick-flow; OFB vendor slots = research tier.
- Holdout 2025-01-01 → 2026-07-08, sealed, once. Early-sample 2017-06 → 2021-09-21 check, once, after freeze.
- Apex 300K PA modelled from a fresh account + cushion sensitivity (desk shows no balances).

## Stage log
- [~] 0 Build done (wf_e879c410-3c7; 4 builds + data/sim/rules verified; network drop killed fix:sim, fix:rules, verify:score). Sim gate 100%. Continuation = workflow 1b.
- 2026-10-01 21:42 ET: desk now shows the five 300K PAs (PAAPEX ...0022-0026) at $300,000 each = FRESH start state is the
  real one (plus3000 / plus7600 stay as sensitivities). PAAPEX ...0021 is a 50K PA.
- Workflow 1b (wf_59918ad4-0ca): fixes sim/rules/data + verify score + recheck — running.
- [x] 0 Build + verify DONE 2026-10-01 23:00 ET (wf_e879c410-3c7 + wf_59918ad4-0ca): data / sim / rules / score all re-checked ok
  (342 tests; sim gate 100%; score 8,919 values identical to R; look-ahead guard closed). Minors left: one_direction evidence in
  l2sim rows, resolve_start idempotence, test scratch dirs, phase_check overnight + holdout enforcement, c1 pool pin at freeze.
  Stress (2 ticks + 250 ms) hurts orb/donchian picks a lot (orb all-sessions +16k → −17k).
  Apex Legacy 300K EVAL is purchasable: $20,000 target, $7,500 trail, 35 minis, 7 min days, $797/mo ($79.70 coupon), PA fee $55–300.
- [~] A Screen: workflow 2 (harden → families → screen runs → analysis). Defaults pre-registered in SPEC "Stage A screen".
- 2026-10-02 00:00 ET, workflow 2 "harden" DONE (infra owner; report in the workflow log): l2sim rows carry one-direction EVIDENCE
  (`oco`, `both_sides`, result `both_sides_sessions`) and apex300 / score PROVE one direction from it (declared-only = UNCHECKED);
  5:1 gate without tolerance / fail-open edges; `resolve_start` idempotent; Template filter `f_depth` (B6; default off, sim gate
  re-run 100% identical); look-ahead bound raises; first session keeps its evening lookback; `phase_check` + overnight bucket (all
  40 in-sample months pass) persisted in cache/phase_guard.json and ENFORCED by l2sim (1 s guard on failed months; holdout months
  must be in the file); score refuses subset sim runs without `calendar=`; firm `apex300_eval` (P(pass <= 10 / 20 d), bust).
  NEW: `families/` (registry + README contract), `screen.py` (run | status | plan | stress | smoke; ledger.csv, runs/<key>/, cap 400).
  Suite: see the report. Next: family authors add `families/<group>.py`; then `python screen.py run`.
- 2026-10-02 00:27 ET, gates G1-G3 READY, NOT RUN (gates author): `gates.py` (list gates on the 6 approved trade lists; definitions
  pre-registered in FAMILIES.md "Gates G1 / G2 / G3" at 00:08 ET before the code existed) + `tests/test_fam_gates.py` (34 tests).
  To run (screen runner): `python gates.py run` -> 54 `gate` ledger rows (6 picks x 3 gates x (real + 2 permutation nulls)),
  bundles `runs/gate_<pick>_<G>[-perms<seed>]/`; one process, seconds. Score through `gates.cell(pick, gate, slot)`: a G3 bundle
  is HALF-UNIT rows -> half the pick's micros, check `walk.cap_ok`, `max_day_tr = 0` cells only. Only a 10-day smoke was run
  (counts only, nothing written under L).
- 2026-10-02 01:10 ET, walls B4 / B5 verifier fixes, BEFORE any screen run (walls author; FAMILIES.md "Walls — addendum"; no P&L
  looked at): B4 `wall_bounce` now rests its limit in the 1-tick case too (SPEC line "within 2 ticks"; `Template._lim` refused a
  limit AT the last print, so only "exactly 2 ticks" traded) — no default changed, `families/walls.py` sha256 6746591efd106572….
  Reading rules fixed in advance: C2 for B4 / B5 is UNINFORMATIVE = NOT PASSED when a null seed has < 0.5 x the real trades
  (B5's null is degenerate: re-anchoring kills wall persistence); the 1 s guard line (`latency_ms=1085`) is mandatory for a walls
  candidate; Stage E asserts no in-session row is masked by `ofb_mismatch` alone; B4 / B5 are labelled NOT hand-executable (no
  Apex 300K PA candidate). OPEN for the orchestrator before `screen.py run`: B4 with the last print AT the wall (0 ticks) stays
  no-signal. New `tests/test_fam_walls_real.py` (10 real in-sample days, one process, 14 s).
- 2026-10-02 01:15 ET, gates G1-G3 FIXED after verification, still NOT RUN (gates fixer; FAMILIES.md "Gates — addendum"). This
  note REPLACES the scoring line of the 00:27 note. Gate decisions are unchanged (identical signals / verdicts on the smoke days).
  (1) MAJOR: a G3 bundle is no longer scored as half-unit rows at half micros (R's day walk mis-handles the copies); it is scored
  as a PORTFOLIO OF ITS SIZE TIERS (`runs/gate_<pick>_G3/x0.5|x1|x1.5/`, micros u / 2u / 3u) through `gates.cell` ->
  `gates.score_cell` / `gates.lift_cell`; the G3 directory has no trades.json (score.py refuses the half-unit rows). Every cell is
  valid (max_day_tr = 1 too). All six Lucid cells are over the 40-micro cap at the pick's size (refused unless over_cap=True):
  the compliant G3 cell is `unit=13` (13 / 26 / 39). G3 has no C1 control yet (needs per-tier draws). (2) the null's count matching
  moves judged trades only; (3) snapshot-phase guard wired into `gates.signals`; (4) run.json counts: `guard_check` (verdicts that
  change with the clock 1 s earlier), `entry_timing`; `python gates.py guard` = the 1 s robustness re-run (stage `gate_guard`, not
  counted, only for screened gates); (5) slot `apex300_pa` (donchian #1, the 300K PA bar); (6) ledger row before bundle, missing
  bundle rebuilt. To run (screen runner): `python gates.py run` (54 `gate` rows, one process, seconds). 52 tests, 73 mutants killed.
- 2026-10-02 01:38 ET, Stage A SCREEN + GATES RUN (screen runner; no input changed, no scoring, no selection). Suite before and
  after: 799 passed, 1 skipped (by design: F3 has no percentile case); every registered family passed the 1-vs-8-worker identity,
  none excluded; `families/walls.py` sha256 6746591e… as pre-registered. `screen.py run`: 75 runs (14 names × tfs = 25 real + 50 C2),
  229 s on 8 workers, 0 errors. `gates.py run`: 54 rows (18 real + 36 permutation nulls), 10 s, one process. Restart check: 0 to run.
  Every screen run: 825 sessions, 820 used (the 5 coverage-hole days of SIM_VALIDATION), `skipped_by_error` 0, `unrealistic_winners`
  0 (B4 is the only limit family; `strict_limit`), `both_sides_sessions` 0, no exec guard, no row dated after 2024-12-31.
  Book mask: 39 of 825 sessions (4.7%) are fully `book_ok` False (roll −1 / 0 / +1), 50 (6.1%) have ≥ 1 masked R-session minute,
  5.0% of R-session rows; families that read `book_ok` have 0 trades on the 39 days (781 traded days max); `open_dir_flow` (no
  book column) trades them (133 trades). Counts table + per-run detail: `out/screen_sanity.json`, `ledger.csv`.
  READ BEFORE ANY LIFT (counts only): C2 null trade count vs real — `wall_break` 0.06–0.12× (UNINFORMATIVE = NOT PASSED by the walls
  addendum rule), `absorption` 2.4× / 3.5×, `cvd_div` 1.9× / 1.3×, `delta_follow-tf5` 0.74×, all others 0.94–1.07×. `max_tr` 3 is
  hit in 88–100% of traded day-sessions at tf 1 for B1 / B2 / F1 / F4 (the trade count there is the cap, not the trigger).
  Gates: `guard_check` (verdicts that change with the clock 1 s earlier) is large on the donchian picks (G1 581 / 620, G2 420 / 430,
  G3 1,909 / 2,068 of 3,571 / 3,852) and small on straddle / ORB (8–270). B4's 0-tick case stayed no-signal (as registered).
  NOT run: `screen.py stress`, `gates.py guard` (not counted; for shortlisted configs only).
- 2026-10-02 12:00 ET, Stage A ANALYSIS DONE (screen analyst). Command line `screen_analyze.py` (score | nullc1 | gates | stress | report | status), code in
  `screen_analysis.py` (the module NAME screen_analyze is R's: R/wf_offline etc. import it lazily and L is first on sys.path, so `import screen_analyze`
  is handed to R's file; tests/test_screen_analyze.py, 12 tests). Rules in the docstring, written before any scored number was read; what changed later
  is listed there and in section 6 of the summary. PRIMARY MODEL = INTRADAY FOR EVERY ACCOUNT (SPEC 'USER FACTS 07:20 ET', written mid-run): the seven
  Lucid accounts were scored twice (first pass realized-primary = side columns `realized_pick_*`; second pass intraday-primary = cache `<firm>@intraday`).
  Outputs: `out/screen_summary.md` (120 lines), `out/screen_table.csv` (1,500 rows = 125 configs x 12 accounts; also net_build / net_pick2024 / stop size
  columns for the edge library), `out/screen_stats.csv`, `out/screen_gates.csv`, `out/screen_shortlist.csv`; caches `out/screen_analyze_cache/` (7,125 rule
  searches + 4,746 null C1 lifts), `out/screen_stress.json`, `out/screen_gates.json`, `out/screen_baseline.json`. Stress: 12 family x tf under l2sim.STRESS
  (ledger stage `stress`, NOT counted: screening runs still 129). No 2025+ row read, nothing tuned, 0 scoring errors. Suite 811 passed, 1 skipped.
  RESULT: no L2 family carries usable information. 11 of 14 families are no better than their shuffled book, the two wall families are worse (wall_break C2
  uninformative = not passed). open_dir_flow (REVISIT) passes the pre-declared family rule only narrowly (8 of 40 cells above null p95, chance needs 5; whole
  edge +7.8k at 1 NQ, t +0.1, all of it from the mid session): a lead to re-test, not a finding. 515 of 1,406 scored cells have lift > 0 vs C1 and C2 (37%;
  the shuffled nulls show C1 lift > 0 in ~77% of their own cells, so C1 > 0 alone is not evidence); 104 cells (7.4%) are above their null p95 (5% by chance).
  No cell reaches P5 .60 and none beats its account's bar under intraday (evals: old pilot's best .36 / .40 / .42 / .42 / .40; Pro DLL funded 1,520; Apex
  50K PA 936; Apex 300K PA 2,111; no bar yet for Flex / Flex+DLL / Pro noDLL funded). Best L2 cells: Pro noDLL eval .41 (bimb_follow-tf5 mid), Flex funded
  1,058, Apex 300K PA 1,571 (sweep_follow-tf1 pm, loses money at 1 NQ). Gates G1-G3: none improves an approved pick beyond its permutation null.
  THE ONE CLEAN LEAD: bimb_follow-tf5 mid (713 trades, +67.0k at 1 NQ, t +2.5, PF 1.27; twins -39k / -32k; build +38.6k, 2024 +28.4k; +64.0k under stress;
  median stop $765 per NQ; on the shortlist of 11 of 12 accounts, the only entry without a flag), then bimb_follow-tf5 nyam (+48.3k, t +2.0). Picked after
  the fact among 122 configs: re-test before believing. Edge-library candidates by the raw rule (net > 0 in build AND 2024, above both twins, > 0 stressed):
  9 of 122, listed in section 7.
## Queue status
_screen runner; updated 2026-10-02 01:38 ET (from `ledger.csv`: `python screen.py status`, `python gates.py status`)_
- stages: screen: done 75 of 75 (real 25, C2 50), error 0, pending 0; gate: done 54 of 54 (real 18, perm 36); stress: 12 (analyst, 2026-10-02 09:11 + 11:43 ET; not counted); gate_guard: 0
- caps used: screening runs 129/400 (screen 75 + gate 54 + screen_error 0; 271 left), grid cells 0/3,000, walk-forwards 0/15
- holdout (2025+) runs: 0 (sealed)
- running: none
- last error: none
- 2026-10-02 07:50 ET: APPROACH CHANGE → edge library + stacks (SPEC last section). Lucid primary = intraday. Caps raised (SPEC USER FACTS).
- 2026-10-02 08:00 ET: user approved ES + GC for non-L2 library members. Straddle nyam/pm = first library candidates (uncapped, micros).
- 2026-10-02 08:30 ET LIVE: gc_nfp fired 08:29:59 on LTE...0014 (LucidPro eval), buy 4217.8, TP filled 4243.5 (target was 4225.5; gap through), +$10,276, held ~1 s; user confirms the eval PASSED. Micro-scalping rule risk flagged to the user.
- [x] A Screen DONE + verified 2026-10-02 12:45 ET (wf_a10cf61f-56b): 129 runs. VERDICT (intraday primary): 0 of 14 L2 families beat
  their shuffled book under the pre-declared rule (open_dir_flow "pass" was an after-the-fact amendment → rejected by the verifier);
  no cell reaches P5 .60 or beats its account bar (best: Pro noDLL .41 vs bar .42); gates add nothing beyond permutation nulls.
  ONE LEAD: bimb_follow-tf5 mid: 713 tr, +$66,993 @1 NQ, t 2.5, PF 1.27, C2 twins −39k / −32k, build +38.6k / 2024 +28.4k, stress +64.0k,
  median stop $765/NQ. Caveats: build profit mostly 2022, neighbouring configs lose, picked post hoc among 122. → carried into the
  edge-library run (D1 with the menu + z variants). Stage B of this pilot is superseded by research/edge-library.
