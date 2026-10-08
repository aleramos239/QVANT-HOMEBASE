> Reference for the pipeline build: what the blueprint toolkit exposes today (read from source 2026-10-07, at commit c5f7d85b). Not a plan.

# Interface map: `research/edge-library/blueprint/`

Everything below was read from source; nothing was run except `--version` checks and read-only prints of files on disk.

Path prefixes:
- `EL` = `/Users/ramoscapital/ramos-quant-homebase/research/edge-library`
- `BP` = `EL/blueprint`
- `HB` = `/Users/ramoscapital/ramos-quant-homebase/homebase`

Module aliases used in the code: `R` rules, `L` lines, `T` tables, `MC` mc, `RUN` runner, `REC` records, `CH` checks, `FRZ` freeze, `OOS` oos, `JOBS` jobs, `J` = `EL/judge.py`, `LB` = `EL/library.py`, `RI` = `EL/run_idea.py`, `RM` = `EL/run_menus.py`, `S` = `EL/engine/l2sim.py`, `IS` = `HB/ideastore.py` (obtained through `api.ideastore()`).

Repo state: branch `fix/swing-bars-whole-globex-day`, 12 commits ahead of `origin/main`, 0 behind (HEAD `c5f7d85b`, "merge: GitHub main into the running folder's branch").

## 0. Shared shapes

- **Command result** — `BP/api.py:43` `result(command: str, name=None, **more) -> dict`:
  ```json
  {"ok": true, "command": "build", "name": "x", "status": null, "phase": 2, "round": null,
   "lines": [], "text": "", "next": "", "job": null, "saved": [], "error": null}
  ```
  `phase` comes from `api.PHASE` (`api.py:37`): card 0, code-check 1, build/pools/heatmap/mc 2, lock 3, test 4, sim/portfolio 5, eval-card 6.
- **Refusal** — `api.py:49` `refused(command, why: str, name=None) -> dict` gives `ok: false`, `error: why`, `text: "REFUSED: ..."`.
- **Refusal exceptions** — `api.REFUSALS = (J.Refuse, R.RuleError, LB.CapExceeded, S.HoldoutSealed)` (`api.py:40`). The CLI maps these to exit 2; exit 1 is a crash; exit 0 is done (lines may still fail).
- **Line row** — `BP/lines.py:37` `_row(line: str, passed, number, need, words: str, **more) -> dict`:
  ```json
  {"line": "2.2", "passed": false, "number": 41.0, "need": 70, "text": "2.2 FAIL average trade $41 (need $70)"}
  ```
  `passed` is `True`, `False`, or `None` (shown as `n/a`). Extra keys are per line; `skipped: True` marks a line deferred by staging.
- **Idea store accessor** — `api.py:54` `ideastore()` imports `homebase.ideastore` by repo path and sets `sys.dont_write_bytecode = True`.
- **CLI** — `EL/bp.py` calls `BP/cli.py:317` `main(argv=None) -> int`. The parser is at `cli.py:141`. A detached job child is `bp.py _job <folder>` (`cli.py:319`). `--json` prints one JSON object on one line.

## 1. The idea card

**Entry points**
- `cli.py:283` `_card(a)` reads `--spec=-|FILE` and calls `REC.card`.
- `BP/records.py:427` `card(name, spec, root=None) -> dict`.

**Spec accepted** (`records.py:348` `_spec(name, spec) -> dict`; returns `{name, version, card: dict, run: dict}`):
```json
{"name": "bpi_orb", "version": 1,
 "card": {"why": "...one sentence.", "loser": "...",
          "home": {"market": "NQ", "session": "nyam", "bar": "15"},
          "neighbors": ["midday", "5-minute bars", "ES"],
          "not_here": "the Asian session",
          "main_setting": "or_min", "sides": "both", "sides_why": "...", "loses_when": "..."},
 "run": {"family": "orb", "params": {"or_min": ["5", "15", "30"]}, "fixed": {},
         "filters": [{"block": "momentum", "side": "with"}],
         "exits": "standard", "filter_exits": "standard", "limits": {"max_tr": 1, "dir": "long"}}}
```
- `CARD_KEYS` (`records.py:75`): `why, loser, home, neighbors, not_here, main_setting, sides, sides_why, loses_when`. `not_here` is optional.
- `RUN_KEYS` (`:76`): `family, params, fixed, filters, exits, filter_exits, limits`.
- `SIDES` (`:77`): `("both", "long", "short")`.
- `OWN_EXITS` (`:79`): `("trail_atr", "exit_bars")`.
- Limit keys the engine takes (`RI.LIMIT_KEYS`): `max_tr, dir, exit_bars, trail_atr`.
- Sessions (`RM.DAY_PASSES`): `asia, london, pre, nyam, mid, pm, eve`. Word forms are in `records.SESSIONS` (`:84`).
- Markets: `S.SPECS` = NQ, ES, GC; words in `MARKETS` (`:83`) map gold→GC and nasdaq→NQ.
- Bar sizes: the family class's `SCREEN_TFS` (per family; registry `TFS = ("1","5","15","30")`).
- Families: `RUN._blocks().WRAPPED` (name → class). Filters: `RUN._blocks().FILTERS` (`{block: {side: inputs}}`, `EL/engine/families/blocks.py:202`). `bp.py blocks` (`BP/blocklist.py:83` `blocks() -> dict`) lists them all.
- Idea name: `HB/draftstore.py:36` `NAME_RE = ^[a-z][a-z0-9_]{1,39}$`, plus `records._name` (`:333`).

**Validation** — `records.py:221` `card_lines(spec: dict) -> (rows: list[7 line rows 0.1..0.7], plan: dict | None)`. The plan is `None` when any line fails. It mutates `spec["run"]["params"/"fixed"]`: a numeric choice becomes text when the family default is a string.

Helpers:
- `:126` `place(said, home: dict) -> {market, session, bar, table, said}` (raises `ValueError`)
- `:157` `_filters(run) -> ([(block, side)], "") | (None, why)`
- `:167` `_home(card, known) -> (home | None, why)`
- `:188` `_places(card, home, known, run) -> (neighbors, not_here, why)`

**Refusals raised as `J.Refuse`** (nothing written):
- From `_name` (`:333`): invalid name; name is an engine family; starts with `c1`; contains `__`; ends like `_r\d[a-h]?`.
- From `_spec` (`:348`): not a JSON object; unknown top-level fields (allowed `name, version, card, run`); `spec.name` differs from `name`; `card` or `run` not objects; `version` not an int ≥ 1; unknown fields inside card or run.
- From `card` (`:427`): idea is frozen (`lock.json` exists); a round is on file with a different `run.family`.
- From `cli._card`: no `--spec`; spec not readable; not JSON; empty.

**Refusals returned as a result** (`ok: false`, `lines` = 7 rows, `error` = "the card is not whole: ..."; nothing saved), one per line:

| Line | Fails when |
|---|---|
| 0.1 | no `why`; no `loser`; sentence count ≠ `R.need("0.1")["sentences"]` (1) |
| 0.2 | unknown family; bad filters (not a list of `{block, side}`, more than `max_filters` = 2, two sides of one block); `fixed`/`limits` not objects; `exits` not in `R.EXIT_KINDS` or `filter_exits` ≠ `exits`; `limits.trail_atr` / `exit_bars` set; Level 2 filter with any non-NQ place; a `BLOCK_MARKETS` filter on a market it does not run on; the engine's own `RUN.checked` refusal |
| 0.3 | home lacks market/session/bar; says `"all"`; market, session or bar not available for the family |
| 0.4 | `neighbors` empty or not a list of non-empty strings; an entry unreadable as a place or naming two of one kind; a neighbor equal to home or listed twice; `not_here` equal to home or to a neighbor; market or bar not run by the family; family never trades there |
| 0.5 | no `main_setting`; not a key of `params`; `params` has more than one key; values not a list of 3–4 unique (`R.need("0.5")["values"] = [3, 4]`); it is the family's mirror axis |
| 0.6 | `sides` not in `SIDES`; no `sides_why`; `limits.dir` contradicts `sides` |
| 0.7 | no `loses_when` |

An engine refusal containing "reason is REQUIRED" (the combined reason has fewer than 8 words, `RI.check_spec`) fails row 0.1.

**Files written on success** under `<ideas root>/<name>/` (all through `IS`):

| File | Holds | Writer |
|---|---|---|
| `card.md` | plain-words card, lines 0.1–0.7 (`records._card_md`, `:375`) | `IS.write_card` (`ideastore.py:198`) |
| `spec.json` | `{name, version, card, run}`; `card.home` normalised to engine names | `IS.write_spec` (`:205`) |
| `idea.json` | mirror of saved results (see below); never authoritative | `IS._refresh` (`:433`) on every write |
| `log.jsonl` | one `{"utc", "event", ...}` per line | `IS.append_log(name, event, root=None, **fields)` (`:286`) |
| `.lock` | flock file for `idea.json` | `IS._locked` |
| `rounds/<n>/reason.txt`, `spec.json`, `build.json` | written by the build (section 3) | |
| `check.json`, `lock.json`, `test.json`, `sim/<account>.json`, `eval.json`, `early_look/{lock,test}.json` | later phases | |

- `idea.json` example: `{"name", "created", "status", "phase", "round", "lines": [{"line", "passed", "text"}], "next", "early_look": false, "runs": ["<tester run id>"], "group": "Ideas"}`.
- Log events seen: `created`, `status {was, now}`, `group`, `locked`, `test_claimed`, `test_did_not_finish`, `tested`.
- Also written: the Lab draft `<drafts dir>/<name>.py` and `groups.json`, via `records._lab` (`:418`) → `IS.sync(name, root=None, drafts=None) -> {"idea", "filed", "notes"}` (`ideastore.py:630`).

**`card` result extras**: `status`, `lines`, `saved` (card.md, spec.json, draft path), `plan`, `lab {filed, notes}`.

**Ideas folder location**
- `ideastore.py:98` `ideas_root(root=None) -> Path`: argument, else env `HOMEBASE_IDEAS_ROOT`, else `~/.homebase/ideas`.
- `jobs.py:72` `root(arg=None)` follows the same rule.
- Lab drafts: env `HOMEBASE_DRAFTS_DIR` (`draftstore.ENV`). `ideastore.py:537` `lab_dir(root=None, drafts=None)` raises `ValueError` for a moved ideas root without it (the Lab is then skipped with a note, not an error).
- `records.py:105` `_own(root) -> bool`: is this the app's own folder.

**Status is derived, never set** — `ideastore.py:371` `_status(d)`, `:384` `status(name, root=None) -> str`:
- `STATUSES = ("idea", "lead", "proven_on_history", "proven_live", "shelved")`.
- `lead` = the latest finished build has every line of `LINES[2]` (2.1..2.9) present and none `False`, and at least one `True` (`_passed`, `:348`).
- `shelved` = a failed build at round ≥ `MAX_ROUNDS` (5, `:64`), or a finished `test.json` that did not pass.
- `_finished(r)` (`:329`): `ok` is not `False`, not `dry_run`, has `lines`, and `job` is absent or `state == "done"`.
- Other readers: `rounds(name, root=None) -> [1, 2, ...]` (`:320`), `read_idea` (`:291`), `list_ideas(root=None) -> [idea.json, ...]` (`:299`), `refresh` (`:445`), `exists` (`:114`), `idea_dir` (`:110`), `create(name, root=None, exist_ok=False)` (`:171`).

## 2. The plan, stores, variants, cells

**Plan** (second return of `card_lines`; saved in `rounds/<n>/spec.json` as `plan` and in `lock.json`):
```json
{"home": {"market": "NQ", "session": "nyam", "bar": "15", "table": "NQ-tf15-nyam", "said": "home"},
 "neighbors": [{"market": "NQ", "session": "nyam", "bar": "5", "table": "NQ-tf5-nyam", "said": "5-minute bars"}],
 "not_here": {"market": "NQ", "session": "pm", "bar": "15", "table": "NQ-tf15-pm", "said": "..."},
 "sides": "both", "filters": ["momentum_with"], "main_setting": "ib_min", "values": ["5", "15", "30", "60"],
 "exits": "standard", "variants": 192,
 "stores": [{"market": "NQ", "bar": "15", "sessions": ["nyam", "pm"]}, {"market": "NQ", "bar": "5", "sessions": ["nyam"]}]}
```
- `not_here` may be `None`.
- `variants` = `len(values) * len(R.exit_cells(kind, market))`.
- `plan["stores"][0]` is always the home's market and bar.
- There is one store per (market, bar); its `sessions` are every session named there.

**Plan to engine specs** — `records.py:321` `engine(spec: dict, plan: dict, store: str) -> list[dict]`. One run_idea-format spec per `plan["stores"]` entry:
```
{"name": store, "reason": "<why> Losing side: <loser>", "family", "markets": [m], "bar_sizes": [bar],
 "sessions": [...], "params", "fixed", "filters": [...(+ {"all": [...]} when 2)], "exits", "limits"}
```
- `limits.dir` is added for a one-sided card.
- `RUN.checked(spec) -> dict` (`runner.py:128`) runs `RI.check_spec` (`run_idea.py:118`) and adds `variants` (list of param dicts) and `filter_exits`. It rewrites `exits` `"standard"` to `RUN.EXITS = "blueprint"`.
- `records.py:312` `rule_filter(plan) -> str | None` returns `"block_side"`; for two filters it returns the combined unit (`"a+b_x+y"`).

**Keys and ids**
- Unit store key: `run_idea.py:212` `unit_key(spec, root, tf, filt=None) -> "<name>[__<block>_<side>]-<ROOT>-tf<tf>"`, e.g. `fvg_delta_nq__delta_with-NQ-tf5`.
- Pool key: `runner.py:236` `pool_key(root, tf, exits=EXITS) -> "c1-<ROOT>-tf<tf>"` (`c1o-...` for `exits == "open"`).
- Worse-fills key: `runner.py:326` `worse_key(key, sess) -> "<key>-<sess>-worse"`.
- Test keys: `runner.py:752` `test_keys(key, store, root, tf, sess) -> {"table": "<key>-<sess>-test", "worse": "<key>-<sess>-test-worse", "pool": "<store>__c1-<ROOT>-tf<tf>-<sess>-test"}`.
- Table name: `"<ROOT>-tf<tf>-<session>"` (regex `tables.HOME`, `tables.py:176`).
- Judge unit (`tables.py:204` `bp_unit(spec, root, tf, sess, label="", filt=None) -> dict`): `{"addr": "<key>-<sess>", "uid": "<key>|<sess>|<label>", "key", "family", "root", "tf", "sess", "label", "filter": None, "group": None, "side": None, "placebo": 0, "controls": ["c1"]}`. Only `spec["name"]` and `spec["family"]` are read.
- `EL/engine/l2sim.py:2257` `cell_id(params: dict) -> str`: exit cell → `"atr1p5-r2"`, `"pts20-r0"`, `"pct0p1-r0p5"`; other keys are prefixed as `key+value` joined by `_`.
- Grid cell id (`l2sim.py:2269` `menu_grid`): `"<variant id>_<exit id>"`, e.g. `ib_min5_atr1p5-r0`. Each grid row is `{"id", "variant": {...}, "exit": {stop_mode, stop_val, tgt_r}, "vi", "xi", "spec": (cls, params)}`.
- Pool cell id: `"s<seed>_<exit id>"`.
- "Variant" in the lines means one cell (main-setting value × exit cell). `vi` is the index of the main-setting value; `xi` is the index of the exit cell.

**Exit menu**
- `rules.py:102` `exit_menu(root: str) -> list[48 × {"stop_mode", "stop_val", "tgt_r"}]`. Order: the 32 old cells (8 stops outer × targets `[0, 1, 2, 3]`), then the same 8 stops × `[0.5, 0.75]`.
- `rules.py:116` `exit_cells(kind: str, root: str) -> list`: `"standard"` → `exit_menu(root)`; `"open"` → 60 session-anchored cells.
- `rules.py:113` `EXIT_KINDS = ("standard", "open")`. The freeze refuses `"open"` (`freeze.py:222`).
- Per market: `RUN.parts(spec, cells, stage)` → `RI.spec_units(spec, roots, tfs)` (`run_idea.py:216`) → `[{key, root, tf, filter, exits, grid, cells, book}]`.

## 3. The build

**Entries**
- `cli.py:258` `_build(a)`.
- `records.py:787` `build(name, reason, root=None, **kw) -> dict` = `run(**start(name, reason, root, **kw))`.
- `records.py:531` `start(name, reason, root=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, tester=None) -> dict`. Returns JSON-able kwargs for `run`: `{idea, round_, reason, rspec, counted, test, root, workers, out, ledger, days, cells, block, tester, draws}`.
- `records.py:686` `run(idea, round_, reason, rspec, counted, test=False, root=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, tester=None, draws=None, progress=None) -> dict`.

**`start` refusals**: no card (`_carded`, `:485`); empty reason; frozen; round > `R.need("2.9")` (5); card on file no longer whole; no free store name; thin control pool on disk (`_seeds`, `:517`); a job of the idea still running (`JOBS.running`); `BP_TEST_RUN` set for the app's own folder; everything `RUN.run_build(..., dry=True)` refuses.

**`start` side effects** (only when `counted` = `days is None or bool(test)`): `IS.write_reason(name, n, reason, root)` writes `rounds/<n>/reason.txt`; `IS.write_round_spec(name, n, rspec, root)` writes `rounds/<n>/spec.json` = `{**spec, "round": n, "store": store, "plan": plan}`.

**Rounds**
- `n = max(rounds with build.json, default=0) + 1`. A round without `build.json` is not used up.
- Store name (`_store`, `:497`): the first of [earlier rounds' store names, latest first; `<name>` (round 1) or `<name>_r<n>`; `<name>_r<n>b..h`] whose on-disk stores have the same `inputs_hash`.
- Result is saved by `IS.write_build(name, n, r, root)` (`ideastore.py:237`) to `rounds/<n>/build.json`. It refuses without `reason.txt`. `IS._round` refuses `n` outside 1..5.

**`run` flow** (`records.py:707–733`)
- `STAGED` (`:78`) = `os.environ.get("BP_STAGED", "1") != "0"`. It is a module global that tests flip.
- Stage 1: `RUN.run_build(specs, ..., stage="units" if STAGED else "all")`, then lines read with `control=False`, `mc_skipped=True`.
- Stage 2 (only when no line is `False`): the lines are read again with Monte Carlo on (`mc_skipped=False`).
- Stage 3 (only when still clean): `RUN.run_build(..., stage="pools")`, then the lines are read with `control=True`.
- Inner `read(control, mc)`: `t = T.built(specs[0], h["table"], filt, out, days, n, control=control)`; then `t.update(neighbors=[...], copies=[...], sides=plan["sides"], reason=reason, mc_skipped=not mc)`; rows = `[fn(t) for fn in REC.LINES]`.
- `REC.LINES = (*L.BUILD, L.rounds)` (`:80`). Tests monkeypatch it.
- Neighbors: `T.place(store, market, bar, session, f, out, like)` per card neighbor; `like = T.sigs(...)` of the home.
- `draws` temporarily overrides `J.RULE["draws"]` (default 4000).

**`run` result extras**
```
idea, counted, dry_run, smoke, bar (R.need("2.3", n)), store, home ("NQ-tf15-nyam"), unit ("x-NQ-tf15-nyam"),
home_store ("x-NQ-tf15"), filter, reason, days {start, end, months, sessions, named}, table {store, variants, dead, duplicates},
neighbors [{market, session, bar, table, said, store, variants, avg_net, positive, profitable, same, copy}], not_here,
sides, stores [run_build rows], failed [...], not_applicable [...], skipped [...], thin [...], passed (bool),
default {cell, survivors, trades, run_id, note}, code_check {on_file, passed}, notes [...], lab, test_run
```
- `status` = `"lead"` if nothing failed, else `"shelved"` if `n >= 5`, else `"idea"`; it is then overwritten by the idea store's own reading.
- When `counted`: `show(...)` (`:588`) re-runs the default cell through the engine for prices (`RUN.cell_trades`) and imports it as a tester run via a subprocess (`imported`, `:615`: `<repo>/.venv/bin/python -m homebase.backtest.importrun ...`, timeout 300 s). Without `tester=` and with a non-own root, nothing is shown and a `note` is set. It is never a gate.

**`RUN.run_build`** — `runner.py:364`
`run_build(spec, workers=None, out_dir=None, *, ledger=None, days=None, cells=None, progress=None, block=None, dry=False, stage: str = "all") -> list[dict]`
- `spec` is one spec or a list of specs.
- `STAGES = ("all", "units", "pools")` (`:278`). `parts(spec, cells=None, stage="all") -> list` (`:281`): `"units"` leaves out pools; `"pools"` gives pools only.
- Row per store: `{"key", "kind": "pool"|"unit"|"filter"|"worse", "root", "tf", "cells", "stage": "bp_build"|"null_bp"|"bp_build_worse", "path", "inputs_hash", "skipped": bool, "ok": True|False|None, "trades", "code_same", ["error"], ["grown"]}`.
- `skipped: True` = already on disk with the same inputs. `ok: False` = strategy error, no store written. `ok: None` = dry.
- `progress` is a callable taking a message string.
- `out_dir=None` → `RUN.RUNS = EL/runs_bp`. `ledger=None` → `EL/ledger.csv`.
- **Shrinking for tests**: `days=[ISO, ...]` and/or `cells=["atr3-r1", "pts20-r0"]` require `days`, `out_dir` and `ledger` all given (refused otherwise, `_run`, `:508`). `days` must lie inside the build range (`seal`, `:96`). `block=` overrides `compute.json` `block_days` (60).
- **Refusals before a pass**: `may_start()`; missing tapes (ES/GC); ledger cap (`LB.ledger_check`); a store on disk with another `inputs_hash` (`_stored`, `:425`); workers outside `1..S.MAX_WORKERS`; another run holding a non-pool store lock.
- **Other run entries**: `run_pools(roots, tfs, workers=None, out_dir=None, *, ledger, days, cells, progress, block, dry) -> list` (`:399`); `run_worse(spec, key, sess, workers=None, out_dir=None, *, ledger, days, cells, progress, block, dry=False) -> list` (`:345`); `cell_trades(spec, key, cell, sess, days=None, workers=1) -> list[trade rows with prices]` (`:380`; re-runs the engine, writes nothing).

**A store on disk** — `<out>/<key>/` in `library.write_unit` format (`library.py:248`):
- `run.json` keys: `family, idea, tf, rationale, filter, exits, sessions, variants, fixed, limits, both_sides_declared, notes, complexity, weak, penalty, penalty_sess, second_look, mirror, note, stage, period ("bp_build"), run_kw, hold_to ("day"), inputs_hash, code {file: sha16}, key, engine, root, range {start, end, holdout, period}, segments, passes, features, features_loader, exec_guard, coverage {sessions, used, skipped, eve_skipped}, elapsed_s, cells [...]`. Also `days` (smoke only) and `grown` (if the table grew).
- `run.json["cells"][i]` = `{"id", "vi", "xi", "variant", "exit", "inputs", "trades", "both_sides_sessions", "skipped_by_error", "unrealistic_winners"}`.
- `cells.npz`: `off` (int64, `len(cells) + 1` offsets) plus one flat array per `LB.FIELDS = ("date", "entry_ms", "dur_s", "net", "mae", "side", "sess", "reason", "risk")`. `date` is the ordinal of the trade date; `net` is USD at 1 contract after costs; `mae` is USD ≥ 0; `side` is ±1; `sess` is the index in `LB.SESS7`; `reason` is the index in `LB.REASONS = ("sl", "tp", "time", "eod", "trail", "bars", "book", "other")`; `risk` is the stop distance in points.
- `table.csv`: one row per (cell, session) with `cell, vi, xi, sess, trades, net, t, pf, win, max_mae_usd`.
- Beside the stores: `<out>/<key>.lock` (per-store flock), `runner.lock`, `prep.lock`, `runner.log`.

**A store in memory**
- `judge.py:356` `store({"dir": Path, "key": str}) -> dict` = `LB.load_unit(key, dir)` plus `"_idx": {cell id: i}`. Cached in `J._STORE`.
- `tables.py:212` `_open(out: Path, key: str) -> (st, where)` applies `RUN.guard` and refuses a trade dated after the build end.
- `judge.py:434` `cellx(st, cid, sess, u=None) -> {field: array}` for one cell in one session (`None`/`"all"` = every session).
- `judge.py:445` `table(st, u) -> list[rows]`. A row is `library.session_table`'s: `{"id", "vi", "xi", "net", "trades", "t", "stop_mode", "tgt_r", "sig", "info", "dead"}`.
- `judge.py:480` `table_stats(rows) -> {"cells", "ids", "share_pos", "avg_net", "median_net", "avg_trades", "positive", "dead", "dup", "v60", "v70", "v80"}`. Judged = dead and duplicate-signature rows removed (`LB.judged_rows`, `library.py:400`).
- `library.py:360` `plateau_units(u, sess) -> {label: rows}` (`{"": rows}` without a mirror axis).

**Smoke versus counted**: `days` given with no `BP_TEST_RUN` → `counted=False`, nothing saved, `dry_run: True`. `BP_TEST_RUN` (`records.TEST_RUN`, `:74`) is env JSON `{days, cells, out, ledger, workers, tester, draws, box, build_avg_trade}` (plus `test_days`, `test_out` for oos). It makes a tiny run count and is refused for the app's own ideas folder (`_test_run`, `:468`).

## 4. The lines

**Table data** (the dict every build line takes; `lines.py` docstring `:8–26`):
```
root 'NQ'|'ES'|'GC' · net, n: (variants × days) arrays · controls {name: verdict} · control_skipped · round · months ·
neighbors [avg-variant net per neighbor table] · copies · long, short, n_long, n_short · sides · filters [...] · reason · mc_skipped
```
Added by `T._data`: `unit, uid, family, store, ids, dead, dup, days (ordinals), _u, _st, _ts`.

**Builders**
- `tables.py:286` `built(spec: dict, home=None, filt=None, out_dir=None, days=None, round_: int = 1, control: bool = True) -> dict`. `spec` is a checked engine spec. `control=False` gives `controls = {}` and `control_skipped = True`. Its own `neighbors` (every other table of that one spec) are overwritten by `records.run`. Refuses: missing store; store not of period `bp_build` or of other days; no judged variant; thin pool.
- `tables.py:99` `_data(st, u, ts, days: np.ndarray, where: str) -> dict`. `ts` needs `ids, dead, dup`; `days` are sorted ordinals (`LB._ordinals(calendar)`, `library.py:629`). Refuses trades dated off the calendar.
- `tables.py:269` `place(name, root, tf, sess, filt=None, out_dir=None, like=None) -> {"table", "store", "variants", "avg_net", "positive", "profitable", "same", "copy"}`.
- `tables.py:261` `sigs(name, root, tf, sess, filt=None, out_dir=None) -> {cell id: sig}`.
- `tables.py:235` `pool_seeds(out, key, need: list[exit ids], want=None) -> {seed: (row, "s<seed>_")}`.
- `tables.py:250` `against_random(st, u, ts, seeds, what: str) -> verdict + {"seeds", "stores"}`.
- `tables.py:359` `box(st, u, cell: str, days=None) -> {"trades": net per trade, "day": net per session day, "n": trades per day, "open": worst open loss per day}`.
- `tables.py:372` `avg_trade(st, u, ids) -> float | None`.
- `tables.py:353` `build_days(u, days=None) -> list[ISO]`.
- `tables.py:383` `tested(spec, lock, out_dir=None) -> dict` (adds `parts, worse, worse_fills, build_avg_trade, box, calendar, range`).
- Dry-run only: `stored(x)` (`:80`), `controls(t)` (`:123`), `neighbors(u)` (`:166`).

**Build lines** — `L.BUILD = (heat, floor, beats_random, trades, neighbors, sides, filter_alone, monte)` (`lines.py:206`). Each has the signature `fn(t: dict) -> row`.

| Line | Function | Reads | `number` | Threshold source | Extra keys |
|---|---|---|---|---|---|
| 2.1 | `heat(t)` `:74` | `net` | share profitable (also needs the average variant > 0) | `R.need("2.1")` 0.6, op `>` | `avg, profitable, variants` |
| 2.2 | `floor(t, line="2.2")` `:84` | `net, n, root` | Σnet / Σn | `R.need("2.2", root)`, op `>=` | — |
| 2.3 | `beats_random(t, line="2.3")` `:94` | `controls, round, control_skipped` | min `p_beat` | `R.need("2.3", round)`, op `>` (strict) | `round, seeds, thin, controls, skipped` |
| 2.4 | `trades(t)` `:119` | `n, months` | mean trades per variant | `R.need("2.4")` 200, `>=` | `on_pace` |
| 2.5 | `neighbors(t)` `:132` | `neighbors, copies` | share of neighbor tables > 0 | `R.need("2.5")` 0.5, `>=` | `profitable, tables, copies` |
| 2.6 | `sides(t)` `:145` | `long, short, n_long, n_short, sides` | weaker side's net | `R.need("2.6")` 0, `>` | `long, short, n_long, n_short` |
| 2.7 | `filter_alone(t)` `:170` | `filters, round, controls` | filtered average trade (`need` = plain average trade) | higher, plus the 2.3 bar | `higher, random_bar, filters, skipped` |
| 2.8 | `monte(t, rng=None)` `:193` | `net, n, root, mc_skipped` | share of runs where 2.1 and 2.2 both hold | `R.need("2.8")` 0.75, `>=` | `runs, skipped` |
| 2.9 | `rounds(t)` `:209` | `round, reason` | round | `R.need("2.9")` 5, `<=` | `reason` |

- 2.3 with `control_skipped` returns `passed: None`. With no controls it returns `False`.
- 2.7 with no `filters` returns `passed: None`.
- `rounds` and `beats_random` call `R.need("2.3", rd)`, which raises `RuleError` for `rd` outside 1..5.

**Raw-number helpers** (threshold-free or separable):
- `lines.py:53` `_profitable(x)` = `x > R.rule("2.1")["also"]["profitable_above"]` (0); array-safe.
- `lines.py:58` `_heat(v) -> (share, avg, met)`. `v` is `(variants,)` or `(variants × runs)`.
- `lines.py:65` `_floor(net, trades, root, line="2.2") -> (avg_trade, met)`; scalar or per run.
- Share profitable: `_profitable(net.sum(1)).mean()`.
- Average trade: `net.sum() / n.sum()`.
- Trades per variant: `n.sum(1)` (mean = the 2.4 number).
- Per side: `t["long"], t["short"], t["n_long"], t["n_short"]` (all variants together, from `_data`).
- Average variant net: `net.sum(1).mean()`.
- Per-day average variant: `net.mean(0)`.
- From stored rows without the day matrix: `J.table_stats(J.table(st, u))`.
- Random: `t["controls"]["c1"]` = `judge.verdict` (`judge.py:688`): `{"pass", "lift", "p_beat" (4 dp), "ctl_mean", "ctl_p95", "ctl_sd", "replicates", "real_replicates", "thin", ["short"], "seeds", "stores"}`.
- Formatting: `_pc(v)` (`:43`), `_n(v, need=None, unit="")` (`:47`).

**Monte Carlo** — `BP/mc.py`
- `:44` `reshuffle(net, n, rng=None) -> (tot: (variants × runs), cnt: (runs,))`. 1,000 runs, whole days with replacement, same days for every variant, fixed seed `montecarlo.json` `seed` 20261005 when `rng is None`.
- `:67` `histories(net) -> (variants × runs × days)` (ordered day paths; used for drawdowns in `quick.tables`).
- `:26` `generator()`. `:31` `draw(days, rng, runs)`.

**Box lines** — `L.BOX = (box_pf, box_ratio, box_sharpe, box_fits, box_monte)` (`:296`). Input `b` = `T.box(...)`.

| Line | Function | `number` | Threshold |
|---|---|---|---|
| 3.3 | `box_pf(b, line="3.3")` `:244` | profit factor (`_pf(trades)`, `:222`) | `R.need("3.3")` 1.2, `>=`; extra `trades` |
| 3.4 | `box_ratio(b)` `:254` | net / `_drawdown(day, open)` | `R.need("3.4")` 3, `>=`; extras `net, drawdown` |
| 3.5 | `box_sharpe(b)` `:264` | daily mean/sd × √252 | `R.need("3.5")` 1, `>=`; extra `days` |
| 3.6 | `box_fits(b)` `:275` | drawdown × micros / 10 | strict `< R.need("3.6")["limit"]` (2000); extra `account` |
| 3.7 | `box_monte(b, rng=None)` `:285` | share of reshuffles ending > 0 | `R.need("3.7")` 0.9, `>=`; extra `runs` |

- `lines.py:231` `_drawdown(day, open_) -> float` counts open losses and trails the end-of-day high.
- UNKNOWN: no function for "without its best 1 % of days" on a box, nor an 80 % reshuffle bar. `best_days` (4.6) takes out a fixed `R.need("4.6")["best_days"]` = 3 on the average variant.

**Test lines** — `L.TEST` (`:401`), each `fn(t)`: `parts` 4.1 (`:309`), `whole` 4.2 (`:325`), `floor_test` 4.3, `random_test` 4.4, `worse_fills` 4.5 (`:346`), `best_days` 4.6 (`:358`), `monte_test` 4.7 (`:371`), `like_build` 4.8 (`:380`), `box_test` 4.9 (`:396`).

## 5. Rules and templates

- Template folder: `BP/templates/` (`rules.T`, `rules.py:24`). `NAMES = ("rules", "ranges", "exit_menu", "control", "montecarlo", "costs", "idea", "sizes", "compute")`.
- `rules.py:66` `template(name: str) -> dict`. Loaded once (`_all`, `lru_cache`) and cross-checked by `check(t)` (`:42`); a disagreement raises `RuleError`. An unknown name raises `RuleError`.
- `rules.py:78` `rule(line) -> {"text", ["number"], ["need"], ["op"], ["also"], ["note"]}`.
- `rules.py:86` `need(line, key=None)`; `key` picks from a dict need (market for 2.2/4.3, round for 2.3) and is looked up as `str(key)`.
- `rules.py:96` `meets(line, value, key=None) -> bool` uses the line's own `op` via `OPS = {">": gt, ">=": ge, "<=": le}` (`:26`).
- `rules.py:73` `lines() -> ["0.1", ..., "6.9"]`.

**Where each threshold lives** (`rules.json`, keyed by line number, entry `{text, number, need, op, also, note}`):

| Number | Location |
|---|---|
| 60 % | `"2.1".need = 0.6`, op `>`; `also.profitable_above = 0` |
| Floors 70/75/140 | `"2.2".need = {"NQ": 70, "ES": 75, "GC": 140}`, op `>=`; repeated in `"4.3".need` and `costs.json` `floor` (all three must be equal or the load fails) |
| Random ladder | `"2.3".need = {"1": 0.95, "2": 0.975, "3": 0.983, "4": 0.9875, "5": 0.99}`, op `>`; test `"4.4".need = 0.95` |
| 200 trades | `"2.4".need = 200`, op `>=` |
| Neighbors 50 % | `"2.5".need = 0.5`; `also.copy_share = 0.5` |
| Sides | `"2.6".need = 0`, op `>` |
| MC 75 % | `"2.8".need = 0.75` (mirrored in `montecarlo.json` `build.need`) |
| Rounds | `"2.9".need = 5`, op `<=` |
| Box | `"3.3"` 1.2; `"3.4"` 3; `"3.5"` 1 (`also.days_per_year` 252); `"3.6" {micros: 1, limit: 2000, account: "LucidPro 50K"}`, `also.rule_file = "lucid-pro-50k@2026-09-27b"`; `"3.7"` 0.9 |
| Test | `"4.5".need {slip_ticks 2, latency_ms 250, oco_cancel_ms 100}`; `"4.6" {best_days 3, above 0}`; `"4.7"` 0.9; `"4.8"` 0.5; `"4.9"` 1.2 |
| Prop | `"5.2".need {win_rate: -0.05, winners: -0.15}`; `"5.3".need {eval: {days 10, odds 0.6}, payout: {days 20, odds 0.75}}`; `"5.5".need {eval 0.5, payout 0.5}` |

**Other templates**
- `exit_menu.json`: `stop_order ["atr", "pts", "pct"]`; `stops {atr [1.5, 3.0], pts {NQ [10, 20, 30, 45], ES [2.5, 5, 8, 12], GC [2, 3, 5, 7]}, pct [0.1, 0.2]}`; `targets_r [0, 1, 2, 3]`; `small_targets_r [0.5, 0.75]`; `cells 48`; `open {stop_order, stops {atropen[5], rngopen[5]}, targets_r[6], cells 60}`; `hold "day"`; `flat_et "15:58"`; `flat_et_half_day "13:13"`.
- `ranges.json`: `build {start 2021-09-22, end 2025-06-30, months 45}`; `test {start 2025-07-01, end "latest", parts [{Jul-Dec 2025}, {Jan-Sep 2026 ... "latest"}]}`; `stored_build {.. 2023-12-31, months 27}`.
- `control.json`: `{kind "c1", seeds 10, draws 4000}`.
- `montecarlo.json`: `{runs 1000, seed 20261005, build {line, need}, test {line, need}, eval_card.percentiles, view.percentiles [5, 25, 50, 75, 95]}`.
- `costs.json`: `floor`; `normal`; `worse {slip_ticks 2.0, latency_ms 250, oco_cancel_ms 100}`; `contract {NQ {point_value 20, tick 0.25}, ES {50, 0.25}, GC {100, 0.1}}`.
- `sizes.json`: `{micros_per_contract 10, steps [1, 2, 3, 5, 7, 10, 15, 20, 30, 40], stage_a 1}`.
- `compute.json`: `{workers {desk_hours 4, other 8}, desk_hours_et ["08:00", "16:15"], no_start_et ["09:18", "09:36"], block_days 60}`.
- `idea.json`: the empty spec.

**Constraints a new caller will hit**
- `R.need("2.3", k)` exists only for `k` in 1..5.
- `IS.MAX_ROUNDS = 5`.
- `IS.LINES[2]` requires 2.1..2.9 all present in a build result for `lead`.
- `card_lines` enforces one varied setting with 3–4 values, at most 2 filters, and one home.

## 6. The default variant (middle survivor)

`records.py:576` `middle(rows: list, ids: list, worse=None) -> (cell | None, survivors: list)`
- `rows` = `J.table(st, u)` rows (needs `id, net, vi, xi`). `ids` = judged ids (`J.table_stats(rows)["ids"]`).
- Survivors = ids with `L._profitable(net)`; when `worse={cell: net with worse fills}` is given, also `L._profitable(worse[c])`.
- Sort key `(round(net, 2), vi, xi)`; pick `surv[(len(surv) - 1) // 2]` (an even count takes the lower middle). Rule text: `J.TIE_RULE` (`judge.py:1006`).
- At build (`records.run`, `:739`): `middle(J.table(t["_st"], t["_u"]), t["ids"])`.
- At lock (`freeze.run`, `:283`): `middle(rows, ids, wnet)`.
- Early look fallback: the middle of all ids when there are no survivors (`freeze.py:414`).

## 7. The code check

**Entry** — `api.py:190` `code_check(name, store=None, trades=None, run_id=None, same_as=None, looked=False, cell=None, market=None, sessions=None, window=None, max_per_day=None, root=None, out=None) -> dict`
- Give exactly one of `store` (a key in `out`/`runs_bp`, or a path) or `trades` (a file). `run_id` is refused (not built). With no source it re-reads `check.json["asked"]`.
- Saved as `<idea>/check.json` via `IS.write_check` only when the idea folder exists.
- Result extras: `source {kind, where, market, lists, trades}`, `asked`, `look` (the 10 trades), `failed`, `not_applicable`, `passed`.
- `passed` = no failed line and 1.1–1.5 all `True`. 1.5 is `True` only with `looked=True`.

**Loaders** (`BP/checks.py`)
- `:190` `load(store=None, trades=None, out=None, market=None, sessions=None, window=None, max_per_day=None) -> trade table` (sealed: refuses any trade on or after 2025-07-01).
- `:100` `from_store(d: Path, sessions=None, window=None, max_per_day=None)`.
- `:133` `from_trades(rows, market, sessions=None, window=None, max_per_day=None, name="trades", where="")`. Rows need `side, entry_ms, exit_ms, net`; optional `date, entry_price, sl, tp, exit_reason, qty`.
- `:180` `find(source, out=None) -> Path`.

**Trade table** (dict of arrays, one row per trade): `cell, date, entry, exit, net, side, qty, sess, reason, stop_usd, target_usd, slack_usd, own, stated_off, stop_pts, stated_stop, num`, plus `lists [{id, max}], sessions, window, per_session, unit, root, pv, tick, name, kind, where, label`.

**Lines** (each returns a row plus `exceptions`, capped at `SHOWN = 20`):

| Line | Function | Checks | Needs |
|---|---|---|---|
| 1.1 | `window(t)` `:243` | every entry inside the stated sessions and/or `HH:MM-HH:MM` window | `sessions` (a store states its own) or `window`; else `None` |
| 1.2 | `one_position(t)` `:266` | no overlap per (cell, session); flat by 15:58 (13:13 on half days) + 60 s | — (store exits have 1 s resolution) |
| 1.3 | `count(t)` `:298` | trades per (cell, date, session) ≤ `max_tr`; no trade at all = fail | cell `inputs.max_tr` or `max_per_day`; else `None` |
| 1.4 | `payoff(t)` `:322` | tp exits pay about the target, sl exits cost about the stop (within 2 ticks, `rules 1.4 also.within_ticks`); gapped stops listed | stop distance (`risk`); else `None` |
| 1.5 | `chart(t, looked=False, cell=None)` `:370` | names the first 5 + 5 seeded-random trades of one list; `True` only if `looked` | owner flag; pops `look` |
| 1.6 | `reproduced(t, earlier=None)` `:400` | the earlier trade list equal field for field on `FIELDS = (date, entry, exit, net, side, reason, stop_usd, target_usd)` | `--same-as`; else `None` |

**Per-trade records from a store**
- Packed arrays for one cell and session: `J.cellx(J.store({"dir": out, "key": key}), cell_id, sess)`.
- All cells as one table: `CH.from_store(Path(out) / key)`.
- Full engine rows with prices (re-runs the engine for that cell): `RUN.cell_trades(spec, key, cell, sess, days)`.
- UNKNOWN: no function re-derives "the entry signal was really there" from raw bars.

**Freeze dependency** (`freeze._checked`, `freeze.py:163`): `check.json` must exist; lines 1.1–1.5 all `True`; `source.kind == "store"` and `source.where` equal to the home store path (or `asked.same_as` equal to it with 1.6 `True`); if the store's `code` hashes differ from today's, 1.6 must be `True`.

## 8. Lock and the one read

### freeze.py

- `freeze.py:364` `lock(name, root=None, **kw)` = `run(**start(...))`.
- `:189` `start(name, root=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None) -> dict`. Returns `{"idea", "root", "frozen": True}` when already locked, else `{idea, root, frozen: False, round_, heavy (bool: the worse-fills table must run), workers, out, ledger, days, cells, block, draws, box, build_avg_trade}`.
- `:247` `run(idea, root=None, frozen=False, round_=None, heavy=None, workers=None, out=None, ledger=None, days=None, cells=None, block=None, draws=None, progress=None, box=None, build_avg_trade=None) -> dict`.
- `cli._lock` (`cli.py:239`) always runs a heavy lock as a job and waits `LOCK_WAIT = 240` s.

**`start` refusals**: no card; unreadable `lock.json`; a running job; no rounds; latest round lacks `build.json` or `spec.json`; build not counted (`ok` false, `dry_run`, job not done); any of 2.1–2.9 missing or failed, or `IS.status != "lead"`; card changed since the round; `exits != "standard"`; home store missing; code-check conditions (section 7); home store lacks exit-menu cells; `run_worse(dry=True)` refusals.

**`run` refusals**: strategy error in the worse pass; no judged variant; worse table lacks a variant; no survivor (`middle` → `None`); any box line 3.3–3.7 not passed (unless test-only `box == "said"`).

**Writes**
- Worse-fills store `<out>/<key>-<sess>-worse`.
- `<idea>/lock.json` via `IS.write_lock`:
  ```
  {name, version, locked_utc, round, store, spec {name, version, card, run}, plan,
   home {market, session, bar, table, unit, uid, key, folder, filter, worse},
   variants [...], default, survivors [...], default_rule,
   box [{line, passed, number, need, text} × 5], prop {...propodds.look}, build {avg_trade},
   costs {normal, worse {slip_ticks, latency_ms, [oco_cancel_ms], two_sided}},
   control {kind, pool, seeds [1..10], draws, draw_seed {build, test}}, montecarlo {runs, seed},
   code {file: sha16}, stores {key: {folder, inputs_hash, run, cells}},
   test_range {market: {start, end, sessions, parts [{name, start, end, sessions}], no_tape, stops}}, hash}
  ```
- Log event `locked`.

**Result extras**: `lock, hash, default, survivors (count), variants (count), test_range, range {market, start, end}, stores, already, matches, mismatches, notes, lab`. `lines` = 3.1, 3.2 plus the box rows.

**Other functions**: `digest(lock) -> sha16` (`:72`); `verify(lock, spec=None) -> list[str mismatches]` (`:102`); `store_hash(folder, key)` (`:92`); `early(name, root=None, out=None, draws=None) -> lock dict marked early_look` (`:371`; writes nothing); `RUN.test_range(root, cap=None) -> dict` (`runner.py:773`; reads manifests only).

### oos.py

- `oos.py:292` `test(name, confirm=False, second_look=False, root=None, **kw)`.
- `:99` `start(name, confirm=False, second_look=False, root=None, workers=None, out=None, ledger=None, days=None, block=None, tester=None, early_look=False) -> dict`.
- `:192` `run(idea, read, rng, second_look=False, second_of=None, root=None, workers=None, out=None, ledger=None, days=None, block=None, tester=None, test=False, early_look=False, progress=None) -> dict`.

**`start` refusals, in order**: no card; not frozen (unless `early_look`; then `FRZ.early`'s refusals); `FRZ.verify` mismatches; `confirm is not True`; running job; own read on file (same lock always; another lock unless `second_look`); a relative's read on file without `second_look` (`READS.used(name, lock, root) -> {"own", "relatives": [{name, kind, why, utc, verdict, state, unit, in_log}]}`, `reads.py:218`); `second_look` with nothing on file; `RUN.run_test(dry=True)` refusals; a store of this read already on disk; `IS.ReadOnFile` from the claim.

**`start` writes** (the last thing before running): `IS.claim_read(name, *, version, lock, rng, second_look=False, root=None)` (`ideastore.py:519`), then log `test_claimed`. For an early look, also `<idea>/early_look/lock.json`.

**`run`**
- `RUN.run_test(name, read, spec, key, sess, variants, store, end, workers=None, out_dir=None, *, ideas=None, ledger=None, days=None, block=None, progress=None, dry=False, keep=()) -> {"stores": [rows], "calendar": [ISO], "trades": {cell: [rows]}}` (`runner.py:832`). It re-checks that the claim is `claimed` and writes 3 stores to `EL/runs_bp_test` (`RUN.TESTS`; `runs_bp_early` for an early look).
- Then `T.tested(sp, lock, out)` and `[f(t) for f in L.TEST]`.
- Verdict: `PROVEN ON HISTORY` → status `proven_on_history`; `NOT PROVEN` → `shelved`.
- Writes `<idea>/test.json` (`IS.write_test`; twice), `IS.log_read(..., state="judged", verdict=label)`, log `tested`, and the tester run import.
- If the pass fails after the claim: log `test_did_not_finish` and raise `J.Refuse`. The read stays claimed for good.

**Result extras**: `verdict, passed, failed, second_look, label, second_look_of, lock, version, range, home, unit, dry_run: False, days {start, end, sessions, named, parts}, table, stores, read {version, lock, utc, state, verdict}, default {cell, trades, run_id, note}, notes, lab`, plus `early_look, held, build_failed, code_check` for an early look.

### One-read log

- File: `<ideas root>/test_reads.jsonl` (`IS.READS_FILE`). Append-only under flock, fsynced.
- Line: `{"utc", "name", "version", "lock", "range": {"start", "end"}, "state": "claimed"|"judged", "verdict", ["second_look": true]}`.
- Readers and writers (`HB/ideastore.py`): `reads(root=None) -> list` (`:469`); `read_on_file(name, version=None, lock=None, root=None) -> latest matching line | None` (`:477`); `claim_read` (raises `ReadOnFile`; `:519`); `log_read(name, *, version, lock, rng, state, verdict=None, root=None)` (`:509`).
- An unparseable line raises `ReadLogUnreadable`.
- Pre-blueprint reads are seeded by `READS.seed(dry_run=False, root=None)` with `version: 0`, `lock: "old:<unit address>"`.

## 9. Prop odds

App simulator: `propodds.app()` (`propodds.py:85`) returns `homebase.backtest.propsim` (`HB/backtest/propsim/__init__.py`).
- `list_rules() -> [{id, name, version, confirmed}]` (newest per family); `load_rules(rule_id) -> dict` (raises `ValueError`); `limit_trades(trades, r)`; `weekday_grid`; `engine` (with `degrade`, `wilson_ci`, `_dll`, `run_eval`, `run_funded`).
- Constants: `N_PATHS = 20_000`, `HORIZON = 250`, `SEED = 20260801`, `CAVEAT`.

**Rule ids on disk** (`HB/backtest/propsim/rules/*.json`):
`lucid-pro-50k@2026-09-27b` (soft $1,200 daily limit), `lucid-pro-50k-no-dll@2026-09-27b`, `lucid-pro-50k@2026-09-27` (superseded), `lucid-flex-50k@2026-09-27` (the default), `lucid-flex-50k@2026-08` (superseded), `lucid-flex-50k-dll@2026-09-27b`, `apex-legacy-300k@2026-09-28`, `apex-legacy-50k@2026-09-27b`, `apex-eod-50k@2026-09-27b`, `topstep-50k@2026-09-27b`.

**Rule file keys** (LucidPro no-DLL example): `name, version, confirmed, account_size 50000, eval_target 3000, eval_min_days 1, consistency null, trailing_mll 2000, lock_at 2100, lock_floor 100, win_day 150, payout_win_days 5, payout_share 0.5, payout_cap 2000, max_payout_profit 4000, daily_loss_limit null, max_days null, scaling_micros {start 20, at_1000 30, at_2000 40}, cap_micros 40, ...`.

**Entries**
- `:369` `look(x: dict, calendar, paths=None, seed=None) -> dict`. `x` = `J.cellx(...)` of one build cell; `calendar` = ISO session days. The account is fixed to `R.rule("3.6")["also"]["rule_file"]` (`lucid-pro-50k@2026-09-27b`); there is no account argument. Returns `{"account": {id, name}, "rule": "open losses count", "days", "eval": {size, p, ci, bust, plain, fast}, "payout": {same}, "text"}`, or `{account, text}` when there is no rule file or no trade. `p` is the no-day-limit odds on the "live is worse" row; `fast` is the 10/20-day odds at that size.
- `:470` `sim(name, account, attempts, fee_budget, root=None, paths=None, seed=None) -> dict`. Requires status `proven_on_history`/`proven_live` (`proven()`, `:395`) and the test stores (`handed()`, `:415`). Writes `<idea>/sim/<account>.json` (`IS.write_sim`). `lines` = 5.1, 5.2, 5.3 (`passed: None`), 5.4, 5.5. Extras: `account {id, name, label, confirmed}, attempts, fee_budget, rule, label, paths, seed, lock, range, pool {days, traded}, days {eval 10, payout 20}, horizon, locked, survivors, variants [read()], middle, meeting, chosen {variant, eval, payout, margin}, table, caveat, lab`.
- `:589` `portfolio(names, account, root=None, paths=None, seed=None) -> dict`. Writes `<ideas root>/_portfolios/<account>__<a>+<b>.json`. `lines` = 5.2, 5.3, 5.6, 5.7. Extras: `members [{name, market, session, bar, variant, survivor, lock, trades, without {eval}, helps}], chosen, table, doubles, passed`.

**Building blocks**
- `:125` `sized(x, size) -> {date, entry_ms, exit_ms, net, mae, cost}` (micros).
- `:135` `ledger(x, size, r) -> rows after the daily limit`.
- `:150` `together(cells_, size, r, calendar)`.
- `:158` `days(rows, r, calendar=()) -> (net[], traded[], open[], dates[])`.
- `:173` `worse(pnl, traded, open_) -> (net, open)`. This is where the "live is worse" row is applied: `app().engine.degrade(pnl, flags, R.need("5.2")["win_rate"], -R.need("5.2")["winners"])`. It is called inside `table()` (`:320`).
- `:190` `draws(days_, paths, horizon, seed) -> (paths × horizon) index matrix` (cached).
- `:210` `eval_walk(pnl, traded, open_, r) -> {"outcome": PASS=1|BUST=2|0, "day", "trade_days"}` (arrays over paths).
- `:238` `funded_walk(pnl, open_, r) -> {"payout_at", "max_payout_at", "bust_at", "cheque"}` (1-based day; 0 = not reached).
- `:264` `odds(pnl, traded, open_, r, paths=None, seed=None, funded=True) -> {"eval": {"p", "ci", "bust", "free": {p, ci, bust}}, "payout": {same} | None}`.
- `:299` `steps(r) -> (eval sizes, funded sizes)`.
- `:309` `table(x, r, calendar=(), paths=None, seed=None) -> [{"size", "eval": {"plain", "worse"}, "payout": {...} | None, "days", "traded", "flipped"}]`. `x` is one cell or a list (portfolio).
- `:338` `best(rows, phase, line="5.3")`; `:348` `bar(ch, line)`; `:355` `read(vid, rows, line="5.5") -> {"id", "eval": {size, p, ci, bust, plain, fast}, "payout": {...}, "margin"}`; `:291` `horizon(r)`.

**What odds exist**
- Top-level `p` = pass within `R.need("5.3")["eval"]["days"]` (10) session days, and maximum payout within 20. The day counts come only from `rules.json` 5.3; `odds()` has no day-count argument.
- `free.p` = pass before bust (and first payout before bust) with no day limit (horizon 250 or the rule's `max_days`).
- There is no ready-made "within 30 days" number. `eval_walk()["day"]` and `funded_walk()["max_payout_at"]` hold the day of the verdict per path, so an N-day figure can be computed from `draws(len(pnl), n, N, seed)` and the walks.
- A "day" is one entry of the calendar passed in (session days).
- The open-loss rule is always on here; the tester's own prop tile uses end-of-day.

## 10. Jobs and concurrency

**`BP/jobs.py`**
- A job is a detached subprocess: `start(d)` (`:116`) runs `Popen([sys.executable, EL/bp.py, "_job", str(d)], stdin=DEVNULL, stdout/stderr → log.txt, start_new_session=True, cwd=EL)` and writes `pid`.
- Folder: `<ideas root>/_jobs/<YYYYMMDDTHHMMSS>-<6 hex>/` holding `job.json, [spec.json], result.json, log.txt, pid`.
- `job.json`: `{"id", "command", "name", "args": {kwargs of the command}, "wait", "state": "queued"|"running"|"done"|"error", "progress": "<last runner message>", "pid", "exit", "created_utc", "started_utc", "finished_utc"}`.
- `COMMANDS = {"build": _build, "lock": _lock, "test": _test}` (`:64`). `new()` refuses any other command.
- `:103` `new(command, name, args: dict, root_, wait=0) -> Path`.
- `:123` `work(d) -> int` (the child): calls `COMMANDS[cmd](**args, progress=lambda msg: ...)`, then `_finish` writes `result.json` first and `job.json` second.
- `:189` `wait(job_id, root_, seconds=None) -> dict`: polls every 0.2 s; returns `result.json` when final, else `api.result(..., job={"id", "state", "progress"})`. A dead process becomes a crashed result (`crashed: True`, exit 1).
- `:175` `running(name, root_) -> job id | None` (one live job per idea name).
- `:149` `find(job_id, root_)`; `:67` `command(job_id, root_)`; `:98` `code(r) -> 0|1|2`.
- `cli._job(kw, a, command="build", wait=None)` (`cli.py:231`) = `new` + `start` + `wait`.
- Progress is read from `job.json["progress"]` (one overwritten string), `<store folder>/runner.log` (appended by `runner._talk`, `:577`), and the job's `log.txt` (stderr).

**Limits enforced by the toolkit** (`BP/runner.py`)
- `:77` `default_workers(at=None) -> int`: `compute.json` gives 4 in desk hours (weekdays 08:00–16:15 ET), else 8; capped by `S.MAX_WORKERS` (≤ 8; env `EDGE_MAX_WORKERS`).
- Then `RM.auto_workers(asked)` (`run_menus.py:125`) = `min(asked, MAX_WORKERS, cpu_count − 2 − busy python processes above 50 % CPU)`.
- `:85` `may_start(at=None)` raises `J.Refuse` inside the engine's no-compute window (text from `compute.json` `no_start_et`, 09:18–09:36 ET weekdays; the definition is `S.compute_window_end`). It is called only when something is pending. Running passes call `S.wait_compute_window()`.
- `:72` `clock()` is patched by tests.
- Locks:
  - `_stores(out, keys, wait=(), say=None, poll=5.0)` (`:459`): per-store flock `<out>/<key>.lock`. Pool keys are waited for; any other held key is refused ("another run is writing").
  - `_alone(out)` (`:444`): whole-folder `runner.lock`, used by `run_test`.
  - `_prep(out)` (`:492`): `prep.lock` for shared caches (blocking).
- Ledger cap: `LB.ledger_check(cells=..., path=ledger, caps=RI.CAPS)` (`CAPS = {"runs": 2000, "cells": 80000, "wfs": 40}`). Unit and worse cells count; pool cells do not.

**The "2 at a time in desk hours, 4 outside" budget is not in the toolkit.** It is `HB/backtest/slots.py`: `CAP = 2`, `CAP_OFF_HOURS = 4`, `DESK_HOURS = (08:00, 16:15)`, `QUIET = (09:20, 09:35)`; `class Slots(d=None, *, cap=None, clock=None, poll=0.5)` with `.quiet()`, `.cap`, `.try_acquire()`, `.acquire(cancelled)` (flock files in `~/.homebase/tester/slots/`, env `HOMEBASE_TESTER_SHARED`). The blueprint path uses only `Slots().quiet()`, in `tester_api.blueprint_run`. Runs of different ideas go side by side; each is limited by its own worker count.

## 11. How the app calls the toolkit

**`HB/claude_mcp/blueprint_tools.py`**
- `:73` `toolkit() -> (python, bp.py)`: python = env `HOMEBASE_BP_PYTHON` or `~/ONYX TRADING/.venv/bin/python`; script = env `HOMEBASE_BP` or `<repo>/research/edge-library/bp.py`.
- `:465` `BlueprintMixin._bp(self, args: list, *, stdin=None, timeout=SHORT_S) -> dict`: `subprocess.run([python, script, *args, f"--root={ideastore.ideas_root()}", "--json"], capture_output=True, cwd=<bp.py folder>, input=json.dumps(stdin) | stdin=DEVNULL, timeout=...)`.
- `_answer(command, p)` (`:391`) parses the one JSON object. Exit 2 or `ok: false` raises `ToolError("Refused ...")`; any other non-zero exit raises `ToolError("crashed")`.
- Timeouts: `SHORT_S = 300`; a job-style tool uses `wait_s + GRACE_S (60)`. `DEFAULT_WAIT_S = 120`, `MAX_WAIT_S = 3600`.
- `:506` `_finish(r, keep) -> str` (the tool's text) calls `_lab(r)` (`:487`) → `ideastore.sync(name)`.
- `SPECS` (`:190`) = tool schemas (`name, description, inputSchema`). `Toolbox` inherits the mixin (`HB/claude_mcp/tools.py:24–25`).

| Tool | Command line |
|---|---|
| `t_blueprint_blocks()` `:521` | `blocks` |
| `block_code()` `:524` (not a tool) | `blockcode` → `{groups, sources, counts}` |
| `t_blueprint_card(name, card, settings)` `:532` | `card <name> --spec=-`, stdin `{"name", "card", "run": settings}` |
| `t_blueprint_code_check(name, store=None, trades_file=None, run_id=None, looked=False)` `:538` | `code-check <name> [--store=|--trades=|--run-id=] [--looked]` |
| `t_blueprint_build(name, reason=None, wait_s=None, job_id=None)` `:552` | `build <name> --reason=... --wait=S` or `job <id> --wait=S` |
| `t_blueprint_lock(name)` `:567` | `lock <name>` |
| `t_blueprint_test(name, confirm, early_look=False, wait_s=None, job_id=None)` `:572` | `test <name> --confirm [--early-look] --wait=S` or `job <id>` |
| `t_blueprint_sim(name, account, attempts, fee_budget)` `:590` | `sim <name> --account= --attempts= --fee-budget=` |
| `t_blueprint_portfolio(names, account)` `:602` | `portfolio <n1> <n2> ... --account=` |
| `t_blueprint_eval_card(name, fills=None, account=None, replay_since_stop=None)` `:613` | `eval-card <name> [--account=] [--fills=-]` |
| `t_blueprint_status(name=None, job_id=None)` `:631` | `status [<name>]` or `job <id> --wait=0` |
| `t_blueprint_heatmap(name, place=None, round=None)` `:641` | `heatmap <name> [--place=] [--round=]` |
| `t_blueprint_mc(name, on=None)` `:651` | `mc <name> [--on=build|test]` |

**`HB/charts/tester_api.py`** (router prefix `/api/tester`)
- `:127` `class _Blueprint(blueprint_tools.BlueprintMixin)`; `box = _Blueprint()` (`:378`).
- `GET /api/tester/blueprint` (`:381`) → `{"tools": [{"name", "phase", "description", "inputs": <inputSchema>}], "ideas": ideastore.list_ideas(), "wait_s": 20}`.
- `POST /api/tester/blueprint/run` (`:406`), body `{"tool": "<blueprint_*>", "args": {...}}` → `{"ok": bool, "tool", "text"}`. `write_ok(request)` is required. 400 on bad shape; 409 when `Slots().quiet()` (09:20–09:35 ET). `wait_s` is clamped to `LAB_WAIT_S = 20` (`:124`). `ToolError` becomes `ok: false` with the text.
- `GET /api/tester/arsenal` (`:392`) → `{groups, sources, counts, ...}`.
- No route returns the toolkit's raw JSON result; the page gets text only. Structured data reaches the page only as `idea.json` via `ideas`.

**Lab Blueprint tab** (`HB/static/charts/lab.js`)
- State `S.view` in `'lib' | 'bp' | 'tk'`; `S.bp`; `S.bpIdea`.
- `loadBlueprint()` (`:59`) does `GET /api/tester/blueprint` → `S.bp`.
- `blueprintList()` (`:682`) renders `B.ideas` (reads `i.name`, and through `C.bpIdeaLine(i)` in `labcode.js:222`: `status`, `phase`, `round`) and `B.tools` (`name, phase, description`).
- `toolSheet(name, preset={}, runNow=false)` (`:703`) builds a form from `t.inputs` via `C.bpFields`, posts `/api/tester/blueprint/run` with `{tool, args}`, and shows `r.json.text`. It extracts a job id from the text with `C.bpJob(text)` and puts it into a `job_id` field ("Keep waiting"). It calls `loadBlueprint()` after every run.
- Clicking an idea runs `toolSheet('blueprint_status', {name}, true)` (`:961`).

**`HB/ideastore.py`** — covered in sections 1 and 8. Standard library only (the toolkit imports it under Python 3.9). `GROUPS` maps status to Lab group. `write_*` functions: `write_card, write_spec, write_check, write_reason, write_round_spec, write_build, write_lock, write_test, write_sim, write_eval, add_run` (`:198–268`); each calls `_refresh`.

## 12. Test conventions

- **Runner**: from `EL`, `"$HOME/ONYX TRADING/.venv/bin/python" -m pytest tests/<file> -q` (Python 3.9.6, pytest 8.4.2). There is no `conftest.py`, `pytest.ini` or `pyproject.toml`. Each test file does `W = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(W))`, then `from blueprint import ...` and `import judge as J`, `import l2sim as S`, `import library as LB`. Files are also runnable as `python tests/<file>.py`.
- **Isolation, no tmp HOME**:
  - Every call passes `root=<tmp>/ideas`.
  - Env `HOMEBASE_IDEAS_ROOT` and `HOMEBASE_DRAFTS_DIR` are set to tmp in a module-level `setup_function` / `teardown_function` (`tests/test_blueprint_ideas.py:85–98`).
  - Stores, ledger and tester go to tmp via `BP_TEST_RUN`.
- **Tiny real runs** (they do run the engine on 3 days): `TI.tiny(**more)` (`test_blueprint_ideas.py:122`) sets `BP_TEST_RUN = {"days": ["2022-03-15", "2023-03-22", "2025-06-30"], "cells": ["atr3-r1", "pts20-r0"], "out", "ledger", "workers": 1, "draws": 200}` and patches `RUN.clock` to a Saturday and `RM.auto_workers` to identity.
- **Other helpers in `test_blueprint_ideas.py`**:
  - `idea(name=NAME, card=None, run=None, **top) -> spec` (`:116`); constants `CARD`, `SETTINGS`, `DAYS`, `CELLS`, `REASONS`.
  - `passing()` (`:153`) forces every read line to PASS by swapping `REC.LINES`.
  - `no_engine()` (`:136`) makes `S.run_many / load_tape / sessions / load_daily` raise.
  - `refused(fn, word)`; `by(r) -> {line: row}`; `stores(out)`; `tree(d)`; `read(p)`.
  - `bp(argv, stdin=None, **env) -> (rc, json)` runs the real `bp.py` in a subprocess.
  - `_run(argv, stdin="")` calls `C.main` in-process.
  - `life(upto)` runs one shared idea stage by stage, once.
  - The module sets `REC.STAGED = False`; `tests/test_blueprint_staged.py` sets it `True` in a fixture.
- **Hand-made tables, no engine** (`tests/test_blueprint_lines.py:68`): `table(nets, trades=None, root="NQ", **kw) -> {"root", "net": np.array, "n": ones | trades, **kw}`, fed straight to `L.heat / L.floor / ...`. `Draws` (`:75`) is a fake rng for `mc.draw`.
- **Hand-made stores and ideas, no engine** (`tests/blueprint_synth.py`):
  - `trade(day, micro_net, micro_mae=0.0, at="09:45", mins=10, side="long", reason="tp") -> row`
  - `store(folder, key, cells: {cell id: [trades]}, span=SPAN, calendar=None, name=None, lock=LOCK, **meta) -> Path` (through `LB.write_unit`)
  - `lines(phase, fail=(), na=())`; `result(command, phase, name, **more)`
  - `proven(IS, root, name, folder=None, cells=None, worse=None, survivors=None, test_fail=(), span=SPAN, **odd) -> Path` (an idea folder up to a passed test; `cells=None` gives a lead)
  - `no_engine()`; `weekdays()`; `ms()`
  - `tests/blueprint_frozen.py` is the helper for locked ideas (not read in detail).

**Representative test A** — card plus tiny staged build (`EL/tests/test_blueprint_staged.py:32–72`, condensed):
```python
import test_blueprint_ideas as TI
from blueprint import records as REC

NAME = "bps_orb"

@pytest.fixture()
def folders():
    TI.setup_function()
    REC.STAGED = True
    with tempfile.TemporaryDirectory(prefix="bp_staged_") as d:
        d = Path(d)
        yield {"root": d / "ideas", "out": d / "runs", "ledger": d / "ledger.csv", "tester": d / "tester"}
    TI.teardown_function()

def tiny(f):
    return TI.tiny(out=str(f["out"]), ledger=str(f["ledger"]), tester=str(f["tester"]))

def test_a_round_with_a_failed_line_runs_no_control_pool(folders):
    f = folders
    REC.card(NAME, TI.idea(NAME), f["root"])
    with tiny(f):
        r = REC.build(NAME, TI.REASONS[1], root=f["root"])
    assert stores(f) == [f"{NAME}-NQ-tf15", f"{NAME}-NQ-tf5"]                  # the tables, no c1-... pool
    assert [s["kind"] for s in r["stores"]] == ["unit", "unit"]
    b = TI.by(r)
    assert b["2.3"]["passed"] is None and b["2.3"]["skipped"] is True and "not run" in b["2.3"]["text"]
    assert r["skipped"] == ["2.3", "2.8"] and r["failed"] and not r["passed"]
    assert [x["line"] for x in r["lines"]] == TI.BUILD_LINES
```

**Representative test B** — judging a fake table, no compute (`EL/tests/test_blueprint_lines.py:68, 213–222`):
```python
def table(nets, trades=None, root="NQ", **kw) -> dict:
    net = np.array(nets, float)
    return {"root": root, "net": net, "n": np.ones(net.shape) if trades is None else np.array(trades, float), **kw}

def test_line_2_1_share_of_variants_profitable():
    r = L.heat(table([[5], [5], [5], [-1], [-1]]))                      # 3 of 5 = exactly 60 %: "more than" is strict
    assert r["passed"] is False and r["number"] == 0.6 and r["need"] == 0.60 and r["line"] == "2.1" and (r["profitable"], r["variants"]) == (3, 5)
    assert r["text"] == "2.1 FAIL 60 % of variants profitable (3 of 5; need more than 60 %); average variant $3"
    assert L.heat(table([[5], [5], [5], [5], [-1]]))["passed"] is True
    r = L.floor(table([[100, 40], [70, 70]]))                            # 280 / 4 trades = exactly $70: "or more"
    assert r["passed"] is True and r["number"] == 70.0 and r["text"] == "2.2 PASS average trade $70 (need $70)"
```

## UNKNOWN / not determined

- `BP/evalcard.py`, `blockcode.py` and `blocklist.py` internals beyond their entry signatures (`evalcard.card(name, fills, root, account)`, `blocklist.blocks()`, `blockcode.toolkit()`).
- `tests/blueprint_frozen.py` helper signatures.
- `HB/backtest/importrun.py` arguments beyond those passed in `records.imported`.
- `labcode.js` `bpFields` / `bpArgs` / `bpJob` internals.
- Which families list `"1"` in `SCREEN_TFS`: only grep hits were seen (fvg, liq, flow, book, port1, port3 include `"1"`; a class at `blocks.py:1020` has `("5", "15", "30")`). The per-family truth is `RUN._blocks().WRAPPED[family].SCREEN_TFS`, or `bp.py blocks`.
- Whether `apex-legacy-300k@2026-09-28.json` says `"confirmed": false` (the file was not opened).
