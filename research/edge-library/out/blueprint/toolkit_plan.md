# The blueprint toolkit — build plan (2026-10-06, night)

Goal: the house blueprint (`BLUEPRINT.md` section 2) runs from ONE saved toolkit. No chat rewrites test code. A new chat calls
`blueprint_*` connector tools; every idea, card, lock and result is saved in the app's folder beside a Lab draft.
Roots: `W` = `research/edge-library`, `H` = `homebase`. Route blueprint work through the research engine (it already has random
controls, worse fills and stores) and put the connector in front of it. `judge.py` stays v2 with its lock green; the new code
imports its functions. Version 1 covers bar-based ideas with the standard exit table. It needs no chart-service restart.

## 1. Reuse as it is
| Need | Reuse |
|---|---|
| Table, dead and duplicate variants, share, average | `judge.table`, `table_stats`, `cellx`; `library.judged_rows`, `plateau_units` |
| Random-entry test, 4,000 coupled draws | `judge.c1_table`, `pool_arrays`, `c1_cell`, `verdict` (takes a hand-built seed map, so it reads new stores unchanged) |
| Filter against plain; same-idea check | `judge.base_test`; `judge.same_idea` |
| Idea settings, grids, smoke run | `run_idea.check_spec`, `spec_units`, `spec_controls`, `cell_specs`, `smoke`; `blocks.WRAPPED`, `FILTERS` |
| One tape pass, stores, ledger | `l2sim.run_many`, `run_menus.merge`, `library.write_unit`, `ledger_add` |
| 10 control seeds | `seeded(RM.c1_grid, …)` in `W/out/check2025/run_check.py` |
| Worse fills | `l2sim.STRESS` + `Costs(oco_cancel_ms=100)` |
| Phase 1 counts | `run_menus.hold_checks`; `run_check._same` (trade-for-trade against a store) |
| One-read pattern | `guard` and `run` in `W/out/exam2026/run_exam.py` (the read is logged before the pass) |
| Monte Carlo and best-3-days math | `W/out/blueprint/funnel.py`, `mc_gates.py`; `W/out/overfit8/overfit8.py` |
| Open loss per day, micro sizing | `library._worst_open`, `metrics`, `sized` |
| "Live is worse" row | `H/backtest/propsim`: `degrade`, the `DEGRADATION` row `(-0.05, 0.15)`, `_floor`, the rule files |
| Draft files | `H/draftstore.py`: `write`, `static_meta` |
| A script-written run the page lists | `RunManager.runs_list` scans the folder each call; `report.build`, `equity`, `to_ms` |
| Live fills | `H/bothistory.py` (`slip_ticks`), `H/metrics.py`, connector `desk_journal` |

## 2. Files
| File | What |
|---|---|
| `W/bp.py`, `W/blueprint/{cli,api,rules,lines,tables,mc,runner,checks,propodds,evalcard,records}.py` | The toolkit: one front door, one function per blueprint line, the one store runner |
| `W/blueprint/templates/{rules,ranges,exit_menu,control,montecarlo,costs,idea,sizes}.json` | Templates as data. `rules.json` holds every threshold keyed by its line number with the quoted BLUEPRINT text |
| `H/ideastore.py` (new, standard library only) | Idea folder, read log, status; atomic writes like `draftstore` |
| `H/claude_mcp/blueprint_tools.py` (new) | A mixin like `DeskMixin`; starts the toolkit with the engine's Python as a subprocess (JSON in / out) and polls job files |
| `H/backtest/importrun.py` (new) | Writes a finished run bundle from a trade list, so the page can show an engine result |
| `W/engine/l2sim.py` (about 30 lines) | A build switch that opens dates to 2025-06-30 and nothing later; old constants untouched |
| `H/claude_mcp/tools.py`, `protocol.py` | Add the mixin; instructions say "use `blueprint_*`" |
| Unchanged | `judge.py`, `library.py`, `run_menus.py`, `run_idea.py`, `tests/test_judge.py` |
New stores go to `W/runs_bp/`, each covering one whole range. Build mode refuses any store that ends after 2025-06-30.

## 3. Data formats
```
~/.homebase/strategies/<name>.py     the Lab draft; card and latest verdict in a marked comment block on top
~/.homebase/ideas/test_reads.jsonl   the one-read log (append only, lock + fsync)
~/.homebase/ideas/<name>/
  idea.json   status, phase, round, pass/fail lines, next step, run ids
  card.md  spec.json  check.json
  rounds/<n>/reason.txt  spec.json  build.json
  lock.json  test.json  sim/<account>.json  eval.json  log.jsonl  jobs/<id>/
```
- `spec.json`: `{"name", "version", "card": {why, loser, home{market, session, bar}, neighbors[], not_here, main_setting, sides,
  sides_why}, "run": {family, params, fixed, filters, exits: "standard", limits}}`. `run` is the existing `run_idea` format.
- `lock.json`: spec, variant list, default, costs (normal and worse), control (10 seeds, 4,000 draws, draw seed), file hashes of the
  engine and family code, store hashes, the test range frozen per market, and `hash` over all of it.
- Read-log line: `{"utc", "name", "version", "lock", "range", "state": "claimed|judged", "verdict"}`.
- Status in `idea.json`, derived only from saved results, mirrored to a Lab group: idea → Ideas · lead (all 2.x true) → Leads ·
  proven_on_history (all 4.x true) → Proven on history · proven_live → Proven live · shelved → Shelved.
- Tests never write to the real `~/.homebase`: the root comes from an environment variable or argument (temp folders in tests).

## 4. Commands (command line = connector tool)
| Phase | `bp.py …` / tool | Inputs | Prints | Refuses when |
|---|---|---|---|---|
| 0 | `card` / `blueprint_card` | name, card fields, settings | Lines 0.1-0.6; writes card, spec, Lab draft | A line is missing; exits not standard; more than 2 filters |
| 1 | `code-check` / `blueprint_code_check` | name; a store key, trades file or tester `run_id`; `looked` | Counts for 1.1-1.4 and 1.6 with exceptions; 10 trade numbers for the chart | Any day on or after 2025-07-01 |
| 2 | `build` / `blueprint_build` | name, reason, `wait_s` or `job_id` | Runs the missing table and control; 2.1-2.9 each pass or fail with its number | No card; round 6; reason not written; fewer than 10 seeds |
| 3 | `lock` / `blueprint_lock` | name | Hash, default, test range | Any build line fails |
| 4 | `test` / `blueprint_test` | name, confirm | Logs the read first; 4.1-4.7 | Not locked; hash mismatch; a read on file for it or a same-idea relative |
| 5 | `sim` / `blueprint_sim` | name, account, attempts, fee budget | Eval pass within 10 days and max payout within 20, per size, plain row and "live is worse" row | Test not passed |
| 6 | `eval-card` / `blueprint_eval_card` | name, live fills | Lines 6.1-6.8; drawdown table after 10, 20, 30, 40 trades | Sim not done |
| any | `status` / `blueprint_status` | name or job id | Ideas with status and next step | – |
A line reads like `2.2 FAIL average trade $41 (need $70)`. Each command also returns JSON.

## 5. Steps (each with its test)
| # | Step | Test | Size |
|---|---|---|---|
| 1 | Templates and `rules.json` | Every numbered line of BLUEPRINT section 2 has an entry whose quoted text is in `BLUEPRINT.md`; menu and costs equal `l2sim` | Small |
| 2 | `lines.py`, `mc.py`, `build --stored` (read-only, on the old stored build days, labelled DRY RUN) | Reproduces `out/blueprint/funnel_units.csv` for all 1,875 tables and `judge.build`'s random numbers for the 57 passers | Medium |
| 3 | Engine build switch | A copy of the check-period test: 2025-06-30 runs, 2025-07-01 raises; identity with stores on 2021-23, 2024 and 2025 H1 days; gates and both suites green | Small |
| 4 | `runner.py`: table and 10-seed control on the build range | 1 worker against 8; identity with `runs/` on smoke days; reruns skip | Medium |
| 5 | `ideastore.py`, `card`, `build` with rounds | Folder format; reason saved before the run; round 6 refused | Medium |
| 6 | Connector tools `blueprint_card`, `_build`, `_status`; the record draft | Fake toolkit binary; tool-name pin; no new `/api` path | Medium |
| 7 | `code-check` and `importrun.py` | Planted bad trades each caught; an imported bundle loads through `RunManager.bundle` | Small-medium |
| 8 | `lock`, `test`, read log | Second read refused; only `runner.run_test` passes the exam key; 4.2, 4.4, 4.5, 4.6 reproduce `oos.json` and the overfit8 numbers | Medium |
| 9 | `sim` | With zero open loss the walks equal `propsim.run_eval` and `run_funded` path for path | Medium |
| 10 | `eval-card` | Hand-made lists with known percentiles | Small |
| 11 | Restart window: ideas route, latency fields, Lab panel | Route tests; golden run unchanged | Small-medium |
| 12 | Runnable tester drafts (needed before any eval, line 6.1) | Trade-for-trade against the engine | Large |

## 6. Decisions taken for the owner while he slept (2026-10-06; each is easy to change)
1. Version 1 saves each idea as a RECORD draft in the Lab (card + settings + verdict; it does not trade in the tester). Runnable
   tester drafts are step 12.
2. Phase 5 uses the app's prop simulator with the open-loss rule added; sizes come from the pre-set steps in `sizes.json`.
3. Readings of the law: 2.3 "above" is strict · 4.2 "middle variant" = the median · 4.6 is read on the average variant · the default
   is the middle of the variants profitable on build and on build with worse fills · 1.4 "about" = within 2 ticks.
4. After a used test read, a new version is refused unless it is run with an explicit second-look flag; its verdict is then
   labelled SECOND LOOK.
5. The tester page keeps "records, never refuses" (the owner's instruction of 27 Sep). The toolkit and the connector refuse.
6. No idea batch is run tonight. The r3 specs wait for the owner.
7. Idea records may be written to `~/.homebase/ideas` (the owner: "saves everything in the app").
8. Workers: 8 outside desk hours, 4 inside; nothing heavy 09:18-09:36 ET.

## 7. Known limits of version 1
The "first look" (entry alone with a time exit) needs a no-stop exit cell: not in version 1. Clock-time ideas, Level 2 filters and
evening sessions come later. The page's own Monte Carlo and prop tile use the end-of-day rule; `sim` counts open losses: label both.

## 8. The contract between the toolkit and the connector (fixed 2026-10-06 so both sides can be built at once)
Every command takes `--json` and then prints exactly ONE JSON object on stdout (logs go to stderr):
```
{"ok": true|false, "command": "build", "name": "<idea>", "status": "idea|lead|proven_on_history|proven_live|shelved",
 "phase": 0-6, "round": n|null,
 "lines": [{"line": "2.2", "passed": true|false|null, "number": 41.0, "need": 70.0, "text": "2.2 FAIL average trade $41 (need $70)"}],
 "text": "the same result as plain lines for a person", "next": "what to do next, one sentence",
 "job": {"id": "...", "state": "queued|running|done|error", "progress": "..."} | null,
 "saved": ["paths written"], "error": null | "why it was refused"}
```
Exit code 0 = done (lines may still fail), 2 = refused (`ok` false, `error` says why), 1 = crashed.
Long commands (`build`, `test`) take `--wait <seconds>`: past that they return `job.state = running`; `bp.py job <id> --json`
picks the wait back up. `--root <folder>` (or the environment variable `HOMEBASE_IDEAS_ROOT`) moves the idea folder away from
`~/.homebase/ideas` — tests always use a temp folder. `passed: null` = the line does not apply (say why in `text`).
The connector finds the toolkit at `<repo>/research/edge-library/bp.py` and runs it with the engine's Python
(`$HOME/ONYX TRADING/.venv/bin/python`); both paths can be overridden by environment variables (`HOMEBASE_BP`, `HOMEBASE_BP_PYTHON`).
