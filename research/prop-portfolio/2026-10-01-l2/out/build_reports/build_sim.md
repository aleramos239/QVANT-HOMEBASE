**SIM VALIDATION GATE: PASS.** The offline tick simulator reproduces the tester's bundles trade for trade on all three approved strategies, in-sample 2021-09-22 → 2024-12-31.

## Gate result

| config | scope | tester trades | sim trades | match | tester net | sim net |
|---|---|---|---|---|---|---|
| hm2-straddle-tf30#10 (Flex eval) | all sessions / nyam | 3273 / 820 | 3273 / 820 | 100% | +141,158 / +95,315 | same |
| hm-orb-tf5#10 (Pro noDLL funded) | all sessions / mid | 3272 / 820 | 3272 / 820 | 100% | +16,152 / +62,610 | same |
| fp-donchian-tf15#10 (Pro DLL funded) | all sessions / pm | 3571 / 760 | 3571 / 760 | 100% | −8,064 / +26,940 | same |

- **Match depth:** every trade is identical on all 20 bundle fields, not only the six the gate asks for; net diff is $0.00.
- **Skipped days:** the same 5 coverage-hole days are skipped as in the tester (825 sessions, 820 used).
- **Other baseline picks:** straddle#9, straddle#32, donchian#1 and donchian#15 also match 100%.
- **Whole heat-maps:** all 88 cells of the three source grids match (310,706 trades).
- **Negative controls:** with slippage set to 0 the match drops to 0%; with the 85 ms placement latency removed, donchian drops to 32% and straddle to 99.6%. So the comparison can fail.
- **Donchian config:** "donchian-tf15 pm" was taken as `fp-donchian-tf15#10` (pts 30, tgt_r 0.6), the Pro DLL funded #1 in `funded_summary.md`.

## What I built

- **`l2sim.py`** — a numpy port of the tester engine (`tick-2`), with the same strategy contract (`on_session` / `on_bar` at 1-minute closes / `on_time`).
  - Orders: market, stop and limit entries with sl/tp/tp_rr, OCO, cancel, flatten.
  - `Template` is the port of `R/template.py`: tf aggregation, sessions, atr|pts|struct stops, tgt_r, trail_atr, exit_bars, max_tr, no entries in the last 5 minutes, flat at session end. I added `_lim` for limit entries (needed for B4).
  - `ctx.feat` / `ctx.feat_window` only expose feature rows whose usable time is at or before the decision time; `L2Features` adapts `l2data.load_features`.
  - `run`, `run_many` (a grid shares one tape pass), `write_bundle` (trades.json + run.json that `R/evalcore.load` reads unchanged), and a small CLI.
  - Loaders raise `HoldoutSealed` for any 2025+ date unless `allow_holdout=True`.
  - Each worker checks the compute windows before every session-day; workers are capped at 8.
- **`l2ref.py`** — straddle, orb and donchian re-implemented on `Template`, plus a `FeatureProbe` used only to test feature plumbing.
- **`sim_validate.py`** — runs the gate, the tape identity check, the negative controls and the grid sweep, and writes `SIM_VALIDATION.md` and `out/sim_validation.json`.
- **`cache/daily_NQ.json`** — in-sample daily bars and contracts; the 13 roll dates derived from it equal the drafts' list.

## Which tape

The tester replays `~/futures_ticks/NQ/...csv.gz`, cached at `~/futures_derived/homebase_tape/NQ/<date>.tape`. The ofb_tick parquet is print-identical to that cache on all 825 in-sample sessions (ts_ns, price, size, row order, contract), so the sim reads the ofb_tick tape as the SPEC says.

## Tests

My 60 tests pass (the full directory, including the other agents' tests, was 135 passed / 5 failed on its one full run; the 5 were in `test_apex300.py` and a re-run of that file showed no errors):
- `test_l2sim_fill_law.py` — the fill law on synthetic tapes.
- `test_l2sim_engine_diff.py` — the tester's own `run_session` (imported read-only, no bytecode written) against l2sim on the same tape. It uses a random order-flow fuzz on 12 synthetic tapes and 6 real in-sample days, plus the reference families. This covers limit entries, tp_rr, trail/bar exits and overlapping positions, which the three approved strategies do not exercise.
- `test_l2sim_guards.py` — holdout seal, compute windows, calendar and coverage parity, tape identity, `run_many` against separate runs, evalcore reading a bundle, features through worker processes.
- `test_l2sim_validation.py` — the gate itself and the negative controls.

## Speed

A full in-sample run takes about 3–5 s on 8 workers (target was 60 s). A 36-cell grid in one pass takes about 57 s. These were measured while other agents were using the CPU.

## Open risks

1. **The 100% match is by construction.** Same tape, a line-by-line engine port, same strategy logic. It shows the execution layer adds no drift; it says nothing about how close the tester's fill law is to live fills.
2. **`on_bar` fires only for minutes with prints** (tester convention). A family that must act on an empty minute needs `times()`.
3. **A strategy that reads `l2data` directly bypasses the timestamp guard.** Only `ctx.feat` enforces it.
4. **`L2Features` depends on `l2data.load_features` as it is now** (index `usable_at`). Columns must be named, since each worker holds a copy of the in-sample table. If that API changes, only this adapter breaks.
5. **Strategy exceptions propagate.** The tester would instead drop the session and count it as skipped-by-error.
6. **Apex one-direction compliance is not enforced by the sim.** `_arm` with two legs is an OCO straddle; this has to be handled per family.
7. **Python version difference.** The sim runs on 3.9, the tester on 3.14, where float `sum()` is compensated. It makes no difference for NQ quarter-tick prices, but a family summing non-dyadic feature values could differ in the last bit if later ported to a tester draft.
8. **Compute-window overrun.** Workers check the clock per session-day, so a job can run into a window by one session-day of work (up to about 0.3 s for a 36-cell grid).
9. **Shared test config.** `pytest.ini` and `tests/conftest.py` are used by every agent's tests in this directory.
10. **Engine drift.** If `homebase/backtest/engine.py` changes from `tick-2`, the port must be re-diffed; the differential tests will catch it.

Nothing outside the pilot directory was written, nothing was committed, and no 2025+ row was read. I did not edit `progress.md`.

Files are in `/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2`:
- SIM_VALIDATION.md
- l2sim.py
- l2ref.py
- sim_validate.py
- out/sim_validation.json
- cache/daily_NQ.json
- pytest.ini
- tests/conftest.py
- tests/test_l2sim_fill_law.py
- tests/test_l2sim_engine_diff.py
- tests/test_l2sim_guards.py
- tests/test_l2sim_validation.py