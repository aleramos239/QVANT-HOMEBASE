**score.py is verified and fixed: no equivalence blockers, and the whole suite passes (342 tests, 22:14 ET, after the sim/data/rules owners' last edits at 21:55).**

## Equivalence lens — no non-identical number
- **Method:** the native side runs in a separate interpreter that never imports score.py; the file side goes through score.py.
- **Bundles the builder did not use:** squeeze-tf5#21 (heat-map cell, up to 11 trades a day), rsi2-tf1#21 (12k trades), tod_drift-tf30#19, the supertrend-tf5 screen run (a run id), and a tf5 random pool.
- **Members:** multi-session (`nyam+pm`, `["asia","london"]`), single, all sessions, and a 3-member portfolio of multi-session members.
- **Eval:** 65 cases across all 5 firms × 3 breach models, plus 20 cases with odd rules and news filters through R's `evaluate`. Outcome arrays, P1..P5, bust and CIs are identical.
- **Funded:** all 5 R variants × 3 models (45 cases), plus `apex300_pa` / `apex50_pa` × 3 start states (36 cases). Every metric is identical, including the compliance gate and the other consistency reading.
- **Also identical:** C1 lift (eval and funded), `search_rules` against `a3p3.search3`, `search_funded` against `funded.search`.
- **Negative control:** a one-tick change on one trade breaks 12 of 15 eval cases; 50 tampered trades change the funded numbers.

## Control lens — findings and fixes
- **Calendar:** the 825 in-sample sessions equal R's cache, R's `tape_sessions`, `portfolio.Ctx.calendar`, `l2sim.sessions` and `apex300.default_calendar` exactly.
- **C2 leak, fixed:** sessions where only some shuffled features were dead kept all their real features in the null. That was the roll block (39 sessions: book masked, flow live) and the first 10 sessions of `depth10_rel20d`, about 6% of sim sessions. They are now permuted inside their own dead-pattern group, so all 825 sim sessions get a donor; 3–10 of them have a donor closer than 5 sessions, and this is reported.
- **Price columns, now enforced:** `c2_shuffle` and `C2Features` refuse `f_o/f_h/f_l/f_c`, `bid_px/ask_px`, tags and flags, plus any column that looks like an absolute price level.
- **Partial shuffles, now refused:** `C2Features` shuffles every feature column it loads; leaving one real raises unless `allow_partial=True`.
- **C2Features vs L2Features:** it now delegates slicing to `L2Features` itself and only swaps the table, with a guard if that hook disappears. Checked on 9 dates × 3 lookbacks against the current l2sim.
- **End to end:** a timing-only probe produces an identical ledger under the null (lift exactly 0); a feature-driven toy family does not.
- **Seeding:** the donor map is identical in other processes and under different hash seeds; no donor or row is dated 2025+.
- **C1:** draws match the config's per-day, per-session counts, never reuse a pool trade within a draw, take fallbacks only from the same session (1.6% for the straddle), and the pool is sealed.
- **C1 fixes:**
  - in-memory lists all shared one seed; there is now a `label` argument;
  - multi-session seeds have one spelling;
  - a control with no trades counts as never passing instead of voiding the lift;
  - `c1_pool()` exposes R's pool resolver.
- **Remaining bias, not fixed:** the null has about 0.4 percentage points fewer valid feature rows than the real. `strata="year"` is available as a stricter null for finalists.

## Other changes
- **Baseline:** Pro noDLL eval is straddle-tf30#10 nyam; #9 moved to `BASELINE_ALT`.
- **apex300:** `score_funded` and `search_funded` now go through the rewritten `apex300.py`: its grid, its compliance gate (fail closed), its commissions, and both consistency readings. Without `strategy`, `inputs` and `both_sides`, no search row is eligible.
- **Start states:** `start_states()`, `score_funded_starts()` and a `--start` CLI flag.
- **l2sim results as a source:** a result dict can be passed directly; its run range is honoured and a result with `skipped_by_error > 0` is refused.
- **Baseline on the 300K PA:** `score.py baseline --search` writes `out/baseline_insample.json`. The six approved picks reproduce R's frozen numbers. Straddle and ORB fail the gate (OCO), so they never set the 300K bar.

| Start state | E$40 (conservative) | E$40 (other consistency reading) | P(bust before first payout) | Source |
|---|---|---|---|---|
| fresh (the real state per progress.md) | 2,111 | 2,751 | 0.56 | donchian-tf15#1 nyam, 100 micros, take 3000 / lock 3000, policy max (grid search) |
| plus3000 | 2,826 | 3,660 | 0.46 | donchian-tf15#1 nyam, fixed cell |
| plus7600 | 3,427 | 3,878 | 0.21 | donchian-tf15#10 pm, fixed cell |

The grid was searched for `fresh` only; the other two rows are fixed cells.

## Open risks
1. A sim run made with `days=` still reports the full range in its metadata, so it must be scored with `calendar=days`. This is documented but not enforced.
2. `c1_pool` returns a nearest-profile pool, flagged, for exit profiles R never ran (e.g. trailing stops). R used the same tf1 points-stop pool for the tf15 donchian.
3. R's 50K `apex` path keeps R's frozen numbers; its compliance verdict now comes from the apex300 gate on the 50K spec.
4. `apex300.py` changed three times during this task. Any further change needs a re-run of `score.py baseline --search` (about 8 minutes on 6 workers).

Nothing was written outside the pilot directory, nothing committed, no 2025+ row read. `homebase/static/index.html` shows as modified in git; that was not this task.

Files are in `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2`:
- score.py
- SCORING.md
- out/baseline_insample.json
- tests/score_native_ref.py
- tests/test_score_verify.py
- tests/test_score_controls.py
- tests/test_score_equivalence.py