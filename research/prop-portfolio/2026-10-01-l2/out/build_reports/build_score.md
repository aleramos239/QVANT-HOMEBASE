**Scoring adapter is built and the mandatory equivalence gate passes: file-path scores are identical (`==`) to R's native path for every firm and model.**

## What I built
`/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py` (1,494 lines). It imports R read-only, with bytecode writing off so no `__pycache__` lands in R or `homebase/`. All numbers come from R's own functions.

- **Sources** (`load_trades`): `file:<config>` or a bare config name → `L/trades/<config>.json`; a path; an `l2sim.write_bundle` directory (scored on its `run.json` range, as `evalcore.build` does); an in-memory list; an R run id or `grid#cell`; or a member list for portfolios.
- **Inside R**: `evalcore.load` is wrapped in-process so R's `build` / `evaluate` / `Ctx.base` accept `file:` members. Lists and real paths keep R's own semantics there.
- **Holdout seal**: any 2025+ row (by `date`, `entry_ms` or `exit_ms`), calendar day, or bundle `run.json` range raises `HoldoutError` unless `allow_holdout=True`. Bundles are refused before their trades are read.
- **Calendar**: R's `bundles_cache/nq_sessions.json`, 825 sessions 2021-09-22 → 2024-12-31, read and never rebuilt. It equals the archive listing and the `ofb_tick` file names. Off-calendar trades raise by default.
- **`score_eval(trades, firm, rules, model)`**: P1..P5, bust, block-bootstrap CIs, all three breach models. All R rule dims are supported.
- **`search_rules(trades, firm)`**: R pass-3 grids, stable pick, speed picks. Also `walk_forward(...)`, which is R's `wf_offline` task + aggregation.
- **`score_funded(trades, firm, policy)`**: flex, flex_dll, pro_dll, pro_nodll, apex, plus `apex300_pa` / `apex50_pa` through `L/apex300.py` with start states `fresh` / `plus3000` / `plus7600`. Also `search_funded`.
- **`lift_vs_control(trades, control_trades, ...)`**: C1 day-matched (R's `daymatched_controls`) or `mode='direct'` for ready-made null ledgers; eval or funded.
- **C2 feature-shuffle null** (documented in the C2 section of `score.py`): `c2_donor_map`, `c2_shuffle`, `c2_null`, and `C2Features`, a picklable loader for `l2sim.run(features=...)`.
  - The donor map is a seeded bijection with no session keeping its own features and at least 5 sessions between a session and its donor.
  - The unit is the Globex session matched on `et_min`, so the evening lookback and the day come from one donor.
  - Sessions the real family cannot use (roll block, holidays) keep their own features; only the 825 sim sessions are permuted.
- **Compute windows**: `desk_window_wait()` covers 09:18–09:36 ET weekdays and Fri 2026-10-02 08:15–08:50, and replaces R's gates in-process.
- **Baseline**: `BASELINE`, `export_baseline()`, `score_baseline()`; CLI `score.py export|baseline|eval|funded|search`.

Exports are in `L/trades/R__*.json`: six approved-pick bundles and three control-pool bundles.

## Test results
76 tests in `L/tests/test_score_{equivalence,loader,search,c2,l2sim}.py` pass (about 110 s). The whole L suite, 189 tests including the other components', passes in one session.

- **Equivalence**: six bundles, exported verbatim, scored through the file path and through five native R paths (`portfolio`, `a3_pass2`, `evalcore.evaluate`, the frozen `holdout_score` in in-sample mode, `funded`).
  - Outcome arrays, P1..P5, bust and CIs are identical for all 5 eval firms × 3 models.
  - Every funded metric including E$40 is identical for all 5 variants × 3 models.
  - Day-matched lift, eval and funded, is identical.
- **Frozen numbers reproduced**:

  | Pick | Metric | Value |
  |---|---|---|
  | Flex eval | P5 | 0.69184 |
  | Pro noDLL eval | P5 | 0.70646 |
  | Flex funded | E$40 | 3329.59 |
  | Pro noDLL funded | E$40 | 5426.21 |
  | Pro DLL funded | E$40 | 1995.62 |
  | Apex PA | E$40 | 1093.08 |

- **Searches**: `search_rules` equals `a3p3.search3`, `walk_forward` equals `wf_offline.task` + `agg_task`, `search_funded` equals `funded.search`.
- **Sim end to end**: `l2sim` output scores unchanged as a list, a file and a bundle directory.

## Open risks
1. **`target_stop` default**: `score_eval` defaults it to True (R's pass-2/3 and portfolio convention); R's bare `evaluate.py` defaults to False.
2. **Pro noDLL eval baseline**: SPEC names straddle-tf30#9 nyam; R's manifest and desk review use #10 nyam. Both are in `BASELINE` and tie in-sample at .7065. Orchestrator should pick one.
3. **R code hash**: `R/portfolio.py` no longer matches the frozen manifest's `code_sha256` (file modified Oct 1 10:41, after the freeze). In-sample numbers still reproduce exactly, but R's `holdout_score.py score` would refuse to run.
4. **Holdout stage**: the `allow_holdout=True` path is tested only on synthetic 2025 rows. It needs an explicit calendar from `tape_sessions(..., allow_holdout=True)`, which was not exercised for 2025+. R's holdout bundles run to 2026-09-30, so clipping to 2026-07-08 needs `off_calendar='drop'`.
5. **Partial runs**: a plain trade file or list is assumed to cover the whole in-sample window. A partial sim run must come as a bundle directory with `run.json` or with an explicit calendar.
6. **Seal scope**: only `score.py` functions validate and seal. Lists and real paths passed straight into R functions keep R's semantics (2025+ rows dropped silently).
7. **C2 bias**: the null has about 0.3–0.6 pp fewer valid feature rows than real (measured on `imb10` and `f_delta`), a tiny upward bias on lift; the shares are reported in `.attrs`. Price-carrying flow columns (`f_o/h/l/c`) must not be shuffled; this is documented, not enforced.
8. **Coupling to other components**: `C2Features` mirrors `l2sim.L2Features` internals and the `apex300` backend uses that module's API names. Tests will flag drift.
9. **Search scope**: `search_rules` on a member list applies one micros to all members; R's greedy portfolio search is not wrapped. The `apex_eod` grid is `a3p3`'s single-config grid, which differs from `portfolio.GRIDS`.
10. **In-process patches**: importing `score.py` wraps `evalcore.load` / `_src_dir` / `save` (save now defaults to `L/out`) and replaces `funded.desk_window_wait` and `portfolio.gate`.