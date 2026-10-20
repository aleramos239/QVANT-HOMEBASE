# Homebase architecture review (2026-10-20)

**The answer first.** The app is already split into the right processes (desk :8850, charts :8852, labrun, the
pipeline). What is messy is inside two files: `homebase/engine.py` (one class, 144 methods, 3,899 lines) and
`homebase/server.py` (one function, 1,500 lines). Today four behavior-preserving cuts landed and the full test suite
is the proof; the rest is a sequenced plan, because this folder runs the live desk and nothing here is worth a
surprise at 09:30.

| Done today | Before | After | Proof |
|---|---|---|---|
| The Lab half of the engine gets its own module | `engine.py` 3,899 lines, 144 methods in `Engine` | `engine.py` 1,925 (straddle/levels/bars) + `engine_lab.py` 1,955 (`LabMixin`) + `daystate.py` 65 (shared words) | tests unchanged in meaning, 3 test lines updated |
| The daily balance record leaves the server | ledger + caches inside `server.py` | `homebase/equity.py`, path given by the caller | same tests, 3 calls repointed |
| The research tests find their own checkout | `REPO = Path.home() / "ramos-quant-homebase"` | derived from `__file__` | a worktree now tests its own `homebase/` |
| The desk's 29 routes leave `create_app` (step 2, same day) | `server.py` 1,920 lines, routes inline | `server.py` 1,093 (wiring) + `homebase/routes/` six modules, 4-407 lines each | bodies byte-identical; 50 routes, OpenAPI and 611 requests identical old vs new |

Nothing the user sees changed: same routes, same journal lines, same order bodies, same files on disk.

---

## 1. What is there now

```
 launchd ──┬── homebase.server      :8850  desk   (engine, timers, broker adapters, 29 routes, dashboard)
           ├── homebase.charts      :8852  charts + Lab/tester (30 routes, hub, tick store, tester_api)
           ├── homebase.labrun             runner for promoted Lab strategies (talks to :8850 and :8852)
           ├── research pipeline           bp.py child processes (ideas → runs_bp, ideastore files)
           └── ticks / prune / relay / tunnels
```

| Layer (as it is today) | Modules | Depth of the seam |
|---|---|---|
| Domain words | `daystate.py` (new), `dayrules.py`, `levels.py`, `contracts.py`, `symbols.py`, `config.py` | deep: small types, many callers (`config` has 53 importers) |
| Desk use cases | `engine.py` + `engine_lab.py`, `timer.py`, `leveltimer.py`, `trading.py` (ChartDesk), `labdesk.py` (LabDesk, 93 methods), `inactive.py`, `metrics.py` | shallow where it matters: `Engine` and `LabDesk` expose almost every method |
| Broker and market data | `broker/base.py` + `paper.py` + `tradovate*.py`, `marketdata.py`, `feed.py` | **real seam**: two adapters behind one interface; tests pin it (no real HTTP/socket ever) |
| HTTP / MCP interface | `server.py` (routes inline), `desk_api.py`, `charts/server.py` + `export_router`, `refresh_router`, `register_desk`, `register_paperbook`, `claude_mcp/*` | charts already does routers per concern; the desk server does not |
| Research (own bounded context) | `research/edge-library/*` flat modules on `sys.path`, `blueprint/` package, `bp.py` CLI | deliberate seam: the desk only runs `bp.py` as a child and reads `~/.homebase/ideas` |

Dependency direction is right: `homebase` never imports `research` (only path strings and a child process);
`research` imports `homebase` only in tests of the connector. `charts` never touches the order API.

## 2. Friction found, ranked

### A. `Engine` is one class for four strategy kinds — Strong (step 1 done)
- Files: `homebase/engine.py`, now also `homebase/engine_lab.py`, `homebase/daystate.py`.
- Problem: 1,900 lines of Lab-round lifecycle (`_lab_*`, 85 methods) sat inside the straddle engine. Eight hooks
  in the straddle code call Lab methods; the Lab code reads ~40 Engine attributes. Reading either half meant
  scrolling past the other.
- Done: the Lab half is `LabMixin` in its own module with its own docstring, constants and `LabLeg`; `Engine`
  inherits it, so every caller (`server.py`, `labdesk.py`, tests) is untouched. The words both halves share
  (`DayState`, `WORKING`, `TERMINAL`, the kill poll, the two "check it" sentences, `_hhmm`, `_to_tick`) moved to
  `daystate.py` so neither module imports the other.
- Honest limit: a mixin is a **file seam, not a module seam**. The two halves still share one `self`. Step 2
  (below) is composition behind a small `DeskPrimitives` interface; that is a design conversation, not a cut.

### B. `create_app` holds routes, wiring, readiness and records — Strong (step 1 done)
- Files: `homebase/server.py`.
- Problem: 1,500-line function. 29 routes, adapter construction, the equity loop, readiness text, pmset power
  status, journal readers. Changing a route means reading the wiring; testing the ledger needed the app.
- Done: the balance record is `homebase/equity.py` with the file path as an argument. `server.py` keeps
  `_equity_path()` and three one-line calls. The Engine still receives `equity_by_day` as `balance_history`.
- Done (step 2): the 29 routes live in `homebase/routes/` -- `status`, `control`, `accounts`, `strategies`, `lab`,
  `records` -- each with `register(app, *, deps)`, the pattern of `charts/desk.py` / `paperbook.py`. Each module's
  keyword list IS its interface: the desk state its routes read. Bodies moved byte for byte (still `@app.`), so
  the routes sit flat on the app: FastAPI 0.141 nests an `include_router` router as one entry, which would have
  hidden the moved routes from the tests that prove every POST is guarded. `state_dir` goes in as
  `lambda: state_dir()` (13 tests patch `homebase.server.state_dir`). `_kill_lock` stays in `create_app`: the
  account-removal path takes it too.
- Found while checking, older than this work: `feed_step` reads `deferred` (server.py, the bars feed) since
  60bb7ff7 removed its assignment. A bars strategy switched on after the feed connected would raise NameError
  every second and get no signal. No bars strategy is configured today, so nothing breaks now.

### C. A research pilot is a drifted copy of the engine — Strong (owner's call)
- Files: `research/prop-portfolio/2026-10-01-l2/` vs `research/edge-library/engine/`.
- 40 files in common: 22 byte-identical, 18 drifted (`l2sim.py` by 1,188 lines, `l2ref.py` by 132). The pilot's
  `SPEC.md` says "reuse its code, do not edit it", so this is a frozen snapshot by design.
- Problem: 1.1 GB and 13,144 tracked files in the working tree; `grep` and the agents' searches hit both copies;
  a fix in the engine never reaches the copy and nobody can tell which is current.
- Proposal: move `research/prop-portfolio/` to an archive (a `research-archive` repo, or a tag + delete here).
  No code imports it. Not done today: deleting the owner's research record is his decision.

### D. `research/edge-library` is a pseudo-package on `sys.path` — Worth exploring
- `bp.py` does `sys.path.insert(0, …)`; `blueprint/*` does `import judge`, `import library`, `import l`,
  `import run_menus` as top-level names. The engine tests' `conftest.py` pushes three directories onto the path.
- Problem: names collide with anything else on the path (`l`, `score`, `screen`), tools cannot resolve imports,
  the research venv and the app venv see different roots.
- Proposal: one package `research/edge_library/` with relative imports, `bp.py` as its console entry. Mechanical
  but wide (26 engine modules, 32 blueprint modules, 42 tests, 91 engine tests). Do it on a quiet weekend with
  the pipeline paused.

### E. `homebase/research/` lives inside the app package — Worth exploring
- Two scripts with `sys.path.insert` (`build_metrics.py`, `build_algo_metrics.py`) plus three JSON equity curves the
  desk page serves (`/api/research-equity`). Scripts belong in `tools/`; the JSON is data the desk ships.
- Proposal: scripts → `tools/research/`, JSON stays (or → `homebase/static/research/`). Update `README.md` row.

### F. Hard-coded home paths — Strong (one fixed)
- `research/edge-library/engine/tests/conftest.py` pointed every worktree's tests at the MAIN checkout's
  `homebase/`. Fixed: derived from `__file__`.
- Still there, deliberate or frozen: `research/edge-library/engine/sim_validate.py:24` (`GRIDS`),
  `homebase/research/build_algo_metrics.py:39` ("research lives in the main checkout"), the frozen pilot,
  and `tests/test_claude_sandbox.py:92` (the real live key, on purpose).

### G. Module-level mutable caches — Speculative
- `_SHARED_AUTHS` (tradovate), `_HOUR_CACHE` (labrun host), `_BOOKS` / `_HIST` (chart workers), `LIMITS`
  (paperbook), `_EQUITY_*` (now in `equity.py`), `_POWER_CACHE`.
- Fine for one process each; they are the hidden state a test has to know about. Leave; list them in `GOTCHAS.md`.

### H. Private names crossing modules — Speculative
- `server.py` imported `_hhmm` from `engine`; `charts/tester_api.py` imports `_run_propsim` from `backtest.runner`;
  `charts/server.py` imports `_cors` from `paperbook`. Rename public or move. Five-minute edits, left for a
  normal change.

### I. Repo hygiene — Strong, five minutes
- Tracked stray plot at the repo root: `equity_vwap_flip_1m_tp15_stop1win.svg`. Untracked `fundcard.json` at root.
- Two leftover worktrees: `.worktrees/rel5` (branch `feat/rel5`) and `.claude/worktrees/xenodochial-wilbur-bff547`
  (detached). They double every grep.
- Four `config.json.*` backups inside the package (gitignored; move to `~/.homebase/backups`).
- Research outputs in the tree: `runs_bp` 1.1 GB, `runs` 717 MB, `out` 92 MB, `runs_void` 158 MB (ignored).

### What is good and must not be "cleaned"
- The broker seam (`BrokerAdapter`, two adapters, tests that fail on any real call).
- Process isolation: a chart or tester crash cannot touch an order.
- The pinned test suite (`tests/conftest.py`: tmp state dirs, Monday-noon clock, no broker). 196 test files.
- Broad `except Exception` in the engine and adapters is deliberate ("snapshots must never crash") and the
  conftest makes a test failure a `BaseException` so those handlers cannot swallow it. Leave them.

## 3. Target folder structure (reached in steps, never in one move)

```
homebase/
  domain/        daystate.py dayrules.py levels.py contracts.py symbols.py config.py      # words and rules, no I/O
  desk/          engine.py engine_lab.py timer.py leveltimer.py trading.py labdesk.py     # use cases
                 inactive.py metrics.py equity.py gate.py risk.py review.py
  broker/        base.py paper.py tradovate.py tradovate_auth.py tradovate_ws.py login_budget.py
  marketdata/    marketdata.py feed.py ticks.py tickarchive.py tickcoverage.py tickmassive.py datawatch.py
  api/           server.py (create_app = wiring only) + routes/ status.py control.py accounts.py
                 strategies.py lab.py records.py (done, today in homebase/routes/) ; desk_api.py
  charts/        (as is: already routers + hub + stores)
  backtest/      (as is)
  labrun/        (as is)
  claude_mcp/    (as is)
  static/
tools/           fake_desk.py preopen_check.py sim_adapter.py research/build_metrics.py research/build_algo_metrics.py
research/
  edge_library/  a real package: blueprint/ engine/ families/ manual_lane/ taught/ tests/ ; bp.py entry
  (prop-portfolio/ → archived)
tests/
```

Step order and why:
1. **Done.** `engine_lab.py`, `daystate.py`, `equity.py`. File seams, zero call-site change.
2. **Done.** `server.py` routes → `homebase/routes/*.py` with `register(app, ...)`, `create_app` left as wiring.
3. `homebase/research/` scripts → `tools/research/`. Fix the README row. Not done 2026-10-20: two scripts, small
   gain, and they build paths from their own folder; do it with the next edit to them.
4. Repo hygiene (I): one commit, owner confirms the plot and the worktrees.
5. `research/edge-library` → package (D). Pipeline paused, weekend. Not done 2026-10-20: the pipeline was running
   and two research sessions were editing that folder.
6. Archive `research/prop-portfolio/` (C). Owner's call.
7. Only then, if the Lab half keeps growing: `Engine` by composition. The mixin's upward reads (`states`, `cfg`,
   `adapters`, `journal`, `_save`, `day_states`, `_cancel_brackets`, `each_account`, …) are the candidate
   `DeskPrimitives` interface; the eight downward hooks (`_lab_move`, `_lab_grade`, `_lab_flatten_strategy`,
   `_lab_close_sent`, `_lab_clean`, `_lab_hands_off`, `_lab_kill_readonly`, `_lab_tick`) are the `KindHandler`
   interface a levels or bars kind could also implement. Do not start this without the owner in the room.

Why not moving files into `domain/`, `desk/`, `api/` today: every `from .x import` in 100+ modules and 196 test
files changes, the launchd plists name `homebase.server`, and the autopull restarts the desk when `homebase/`
changes. The layering above is real now (the import graph already obeys it); the folders can follow one package
at a time with `from . import x` shims for one release.

## 4. The refactored code, in one place

| File | Role | Lines |
|---|---|---|
| `homebase/daystate.py` (new) | `DayState`, order words, kill poll, the two "check it" sentences, `_hhmm`, `_to_tick` | 65 |
| `homebase/engine_lab.py` (new) | `LabMixin` (85 methods), `LabLeg`, `LAB_*` words. Imports only `daystate`, `broker.base`, `config`, `contracts` | 1,955 |
| `homebase/engine.py` | `class Engine(LabMixin)`; straddle / levels / bars; re-exports the `LAB_*` names callers read as `engine.LAB_*` | 1,925 (was 3,899) |
| `homebase/equity.py` (new) | the balance record with the path as an argument; its two caches | 60 |
| `homebase/server.py` | wiring: adapters, loops, readiness, `_equity_path()`; calls the six `register`s | 1,093 (was 1,974) |
| `homebase/routes/` (new) | `status` 135, `control` 140, `accounts` 407, `strategies` 145, `lab` 71, `records` 51 lines; `register(app, *, deps)` each | 949 |
| `tests/test_fake_desk_lab.py`, `tools/fake_desk.py` | the route-body check reads `homebase/routes/*.py` too; docstrings point there | 2 + 9 lines |
| `research/edge-library/engine/tests/conftest.py` | `REPO` from `__file__` | 1 line |
| `tests/test_engine_lab.py` | tripwire enumerates `vars(LabMixin)`; the asdict break patches both modules | 3 lines |
| `tests/test_server.py` | ledger tests call `equity.*` with `tmp_path / "equity.jsonl"` | 12 lines |
| `tests/test_claude_drafts.py` | the three new modules join the "desk never loads a draft" list | 3 lines |
| `README.md` | the Desk server row names the new files | 1 line |

How the cut was checked, since no linter is installed in the venv: a 25-line script
(`dis` over every code object) lists each global a module loads but never binds; the three new modules and the
two edited ones report none. Then the engine, Lab, server, labdesk and sandbox tests (742 passed), then the full
suite (see the session's closing note for the count against the baseline).

## 5. Why these improvements, in plain words

- **Locality.** A Lab bug is now in a Lab file; a balance-record bug is in a 60-line module you can read whole.
- **Leverage.** `equity.py` can be tested with a path and no app. `daystate.py` gives the two engine halves one
  vocabulary with no import cycle.
- **Less coupling, honestly measured.** The Lab half still reads ~40 Engine attributes; that list is now visible
  at the top of one file instead of hidden in 3,900 lines, which is what makes step 7 designable.
- **No behavior change.** Same classes, same names from `homebase.engine`, same files on disk, same routes.
- **Scales with the next kind.** The eight hooks that reach the Lab half are the shape of a per-kind handler. When
  a third kind arrives, it goes behind that shape instead of adding a ninth `if cfg.kind ==`.

## 6. Not done, on purpose

- No folder moves (`domain/`, `desk/`, `api/`): too many import edits for a live desk in one sitting; planned as step 2+.
- Private names crossing modules (H): about 15 imports; renaming them touches modules other sessions are editing,
  for a naming signal only. Left for a normal change.
- **Commit all new modules with the files that import them.** `engine_lab.py`, `daystate.py`, `equity.py` and
  `homebase/routes/` are untracked. `deploy/linux/push.sh` ships only `git ls-files`, and `git commit -a` skips
  untracked files: either one now would start a desk that cannot import.
- No deletion of research snapshots, worktrees or the stray plot: the owner's records.
- No change to broad `except Exception`, module caches, or route behavior.
- Three failures exist before this work and sit in the owner's uncommitted changes (new propsim rule files, a
  modified propsim test, the chart page script): `tests/test_backtest_runner.py::test_execute_writes_the_bundle_and_lists_skipped_sessions`,
  `tests/test_charts_js.py::test_chart_page_javascript`, `tests/test_tester_api.py::test_prop_rule_sets_are_listed_with_the_unconfirmed_flag`.
  Baseline: 3 failed, 5,753 passed, 16 skipped in 11 min. The run after the cuts is quoted in the session's closing note.
