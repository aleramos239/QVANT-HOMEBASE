# Strategy pipeline — plan A: the core (command line only)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (one fresh subagent per task,
> review between tasks). TDD inside every task: write the test, watch it fail, write the code, watch it pass, commit.

**Goal:** `bp.py pipe ...` takes pipeline idea cards and runs each one through stages 0-7 of the design by itself,
stopping an idea at the first gate it fails and saving a stage card for every stage.

**Spec:** `docs/superpowers/specs/2026-10-07-strategy-pipeline-design.md` (read sections 2-4 first).
**Interface map of what exists:** `docs/superpowers/plans/2026-10-07-blueprint-interface-map.md` (exact signatures and
shapes of the toolkit; read the sections a task names before writing code).

**Later plans (not in this one):** B the app (connector tools, API routes, the Lab's Queue / Book / Guide) · C the luck
rate and the score since the lock · D the portfolio builder and the Apex rule file · E the hunter and the ideas inbox.

## Architecture

The pipeline is an ORCHESTRATOR on top of the toolkit, not a second toolkit.

- A pipeline idea `x` with ways a, b, c on bars 1 and 5 becomes up to six ordinary toolkit ideas (`x_a1`, `x_a5`,
  `x_b1`, ...), each a standard card: one family, one main setting with 3 values, home = the card's market, session and
  that bar, neighbors = the other two markets, no filter. They live in the pipeline's own ideas root, so the Lab is not
  flooded and the toolkit files nothing in the app.
- Stage 1 and stage 3 run the tables with `RUN.run_build(..., stage="units")` and judge them with NEW gates
  (`pipe_gates.py`) that reuse the toolkit's raw numbers. Stage 4 uses `mc.reshuffle` and the control pools.
- From stage 5 on the winning sub-idea goes through the toolkit's own commands, unchanged in shape: `REC.build` (its
  stores are on disk, so it only reads its lines, every one of which is equal to or weaker than a pipeline gate),
  `api.code_check`, `FRZ.lock`, `OOS.test(confirm=True)`. The pipeline never forges a toolkit record.
- State is files: one folder an idea, one JSON a stage. The runner is a detached process that can be killed at any
  point and carries on from the last finished stage.

## Global constraints

- Python: research code runs under `<repo>/.venv-research/bin/python` (it was `~/ONYX TRADING/.venv` until that folder was deleted on 2026-10-08) (3.9: no `match`, no `X | Y` at runtime outside
  annotations under `from __future__ import annotations`). Tests: from `research/edge-library`,
  `../../.venv-research/bin/python -m pytest tests/<file> -q -p no:cacheprovider`.
- Build days 2021-09-22 .. 2025-06-30. Nothing before stage 6 may read 2025-07-01 or later (the toolkit seals it; do
  not add a way around the seal).
- Costs on, one contract, floors NQ $70 / ES $75 / GC $140 (`R.need("2.2", root)`).
- Every gate number comes from `templates/pipeline.json` or `templates/rules.json`. No number in code.
- Match the package's style: dense modules with a docstring that states the contract, `J.Refuse` for refusals,
  `api.result(...)` for command results, line rows from `lines._row`.
- Pipeline files never go in git: everything it writes at run time is under the pipeline root
  (`HOMEBASE_PIPELINE_ROOT`, default `~/.homebase/pipeline`).
- Work in the main checkout (`/Users/ramoscapital/ramos-quant-homebase`): tiny engine runs need its caches. Touch
  nothing under `homebase/` in this plan. Do not restart any service.
- Commit after every task: `git add <the task's files>` (never `git add -A`: `runs_bp/c1o-*` must stay out).

## File map

| File (under `research/edge-library/`) | Responsibility |
|---|---|
| `blueprint/templates/pipeline.json` | every pipeline gate number |
| `blueprint/pipe_rules.py` | reads it: `need(key)`, `random_bar(tries)` |
| `blueprint/pipe_card.py` | the pipeline card: check, signature, sub-idea specs |
| `blueprint/pipe_store.py` | the pipeline root: idea folders, stage cards, registry of seen cards, queue order, book |
| `blueprint/pipe_gates.py` | pure gates on table data: raw (strict / low / fail), indicator, reshuffle, random bar |
| `blueprint/pipe_prop.py` | the two 30-day prop odds and the label |
| `blueprint/pipe_stages.py` | one function a stage; calls the toolkit; returns a stage card |
| `blueprint/pipe_runner.py` | the queue loop: next idea, next stage, pause, resume, one instance |
| `blueprint/cli.py` (modify) | `bp.py pipe add / list / show / start / pause / resume / approve / refuse / book` |
| `blueprint/templates/rules.json`, `montecarlo.json`, `blueprint/lines.py` (modify) | 80 % reshuffles, best 1 % of days, the new box line |
| `tests/test_pipe_*.py` | one test file a module |

## Shapes used by every task

**Pipeline card** (what `bp.py pipe add --spec=-` takes):
```json
{"name": "fvg_open", "why": "Late buyers chase the first gap after the open.", "loser": "Traders who fade the first move.",
 "source": "owner", "market": "NQ", "session": "nyam", "sides": "both", "sides_why": "",
 "ways": [{"family": "fvg", "main_setting": "min_gap", "values": ["0.1", "0.25", "0.5"], "fixed": {"mode": "touch"}, "limits": {}}],
 "indicators": [{"block": "trend", "side": "with", "why": "A gap with the trend has more room."}]}
```
Limits: 1-3 ways, exactly 3 values a way, 0-5 indicators, each with a `why`. `sides` both | long | short (`sides_why`
required unless both). `source` owner | video | claude | wiki. Name `^[a-z][a-z0-9_]{1,33}$`.

**Sub-idea name:** `<name>_<a|b|c><1|5>` (way letter, bar size). **Sub-idea spec** (a toolkit spec, map section 1):
`card.why` = the card's why, `card.loser` = loser, `home` = {market, session, bar}, `neighbors` = the other two of NQ / ES / GC
that the family runs on, `main_setting`, `sides`, `sides_why` (default "both sides: the rule is symmetric"),
`loses_when` = "not named on a pipeline card"; `run` = {family, params {main_setting: values}, fixed, filters [], exits
"standard", limits}.

**Stage card** (`<idea>/stages/<n>.json`, also what a stage function returns):
```json
{"stage": 1, "name": "raw heat map", "passed": true, "result": "low", "lines": [<line rows>], "text": "...",
 "picked": {"sub": "fvg_open_a5", "bar": "5", "way": 0, "filter": null}, "tries": 2, "rules": {"...": "the numbers it was judged by"},
 "utc": "2026-10-08T03:10:00+00:00", "seconds": 1180}
```
**Idea state** (`<idea>/state.json`): `{"name", "status": "queued"|"running"|"stopped"|"code_problem"|"awaiting_owner"|"book"|"refused",
"stage": <last finished>, "stopped_at": <stage or null>, "why": "<one line>", "tries": n, "picked": {...}, "added_utc", "updated_utc", "source", "family"}`.

**Pipeline root layout:**
```
<root>/ideas/<sub-idea>/...      toolkit ideas (HOMEBASE_IDEAS_ROOT for every toolkit call)
<root>/runs/                     stores (out=); c1-* control pools are symlinks to research/edge-library/runs_bp/c1-*
<root>/p/<name>/card.json, state.json, stages/<n>.json, ledger.csv
<root>/seen.jsonl                one line a card ever added: {"sig", "name", "utc"}
<root>/order.jsonl               the queue order: {"name", "utc", "inbox": bool}
<root>/pause                     present = the runner stops after the stage in hand
<root>/runner.lock, runner.log
<root>/book/<name>.json
```

---

### Task 1: the rules file and the law's three changed numbers

**Files:** create `blueprint/templates/pipeline.json`, `blueprint/pipe_rules.py`, `tests/test_pipe_rules.py`; modify
`blueprint/templates/rules.json`, `blueprint/templates/montecarlo.json`, `blueprint/lines.py`, and the tests that pin the
old numbers (`tests/test_blueprint_lines.py`, others the run shows).

`pipeline.json`:
```json
{"card": {"ways": [1, 3], "values": 3, "indicators": [0, 5], "bars": ["1", "5"], "markets": ["NQ", "ES", "GC"]},
 "raw": {"low": {"share": 0.5, "floor_part": 0.5, "trades": 300}, "strict": {"share": 0.6, "floor_part": 1.0, "trades": 200}},
 "indicator": {"share": 0.6, "floor_part": 1.0, "trades": 200, "other_markets": 0.5},
 "proof": {"reshuffle": 0.75, "random_alpha": 0.05},
 "box": {"best_days_share": 0.01},
 "prop": {"account": "lucid-pro-50k-no-dll@2026-09-27b", "days": 30, "eval": 0.5, "payout": 0.5},
 "portfolio": {"eval": {"days": 5, "odds": 0.6}, "payout": {"days": 14, "odds": 0.75}}}
```
`pipe_rules.py`: `need(*keys)` walks the file (`need("raw", "low", "share")`), raising `R.RuleError` for an unknown key;
`random_bar(tries: int) -> float` = `1 - alpha / max(1, tries)`; `floor(root, part)` = `R.need("2.2", root) * part`.
On load it checks `raw.strict.share == R.need("2.1")`, `raw.strict.trades == R.need("2.4")`, `proof.reshuffle == R.need("2.8")`
and `random_bar(k) == R.need("2.3", k)` to 3 decimals for k = 1..5 (the two files must never disagree).

Law changes (spec section 3, stages 5 and 6):
- `rules.json` `"3.7".need` 0.9 -> 0.8 and `"4.7".need` 0.9 -> 0.8; `montecarlo.json` `test.need` to match.
- `"4.6".need` `{best_days: 3, above: 0}` -> `{best_share: 0.01, above: 0}`; `lines.best_days` takes out
  `max(1, ceil(share * days))` days (315 test days -> 4; say the count in its text).
- New box line 3.8 `box_best_days(b)` in `lines.py`, appended to `L.BOX`: the box's net without its best
  `max(1, ceil(0.01 * days))` days must be above 0. Add `"3.8"` to `rules.json` with text, need and op like 4.6.
  Check `freeze.py` and `ideastore.LINES` for places that list the box lines by number and add 3.8 there.

Tests: `need` paths and the unknown-key error; the agreement check fails loudly when a number is edited in one file
only (write a temp copy); `random_bar(1, 2, 5, 11)` = 0.95, 0.975, 0.99, 0.99545...; `box_best_days` on a hand-made box
(one huge day carries it -> fail; steady -> pass); `best_days` with the share; the full existing suite still passes
(`tests/` 220 tests: fix the pins that named 0.9 and 3 days).

### Task 2: the pipeline card

**Files:** create `blueprint/pipe_card.py`, `tests/test_pipe_card.py`. Read map sections 1 and 2.

- `check(card: dict) -> (rows: list[line rows], subs: list[dict] | None)`: line rows "P0.1" why and loser (one sentence
  each, 8+ words together), "P0.2" ways (count, family exists in `RUN._blocks().WRAPPED`, main setting is a setting of the
  family, exactly 3 unique values, the family runs on the market / session / at least one of bars 1 and 5), "P0.3" indicators
  (count, block and side exist in `RUN._blocks().FILTERS`, each has a why, no block twice, a Level 2 block only on NQ),
  "P0.4" sides. `subs` is None when a row fails. A way whose family does not run on one of the two bars gets that one
  bar only.
- Each sub: `{"name", "way": i, "bar": "1"|"5", "spec": <toolkit spec>}`. Every spec must pass the toolkit's own
  `REC.card_lines(spec)` (call it; a refusal there is a P0.2 failure with its text).
- `signature(card) -> str`: sha1 of the canonical JSON of {market, session, sides, sorted ways as (family, main_setting,
  sorted values, sorted fixed items, sorted limits items)}. Name, why, source and indicators are NOT in it.
- `family_of(card) -> str`: the first way's family.

Tests: a good card gives 2 subs a way; each refusal by line; a family without 1-minute bars gives one sub; the same
card under another name has the same signature; another value list has another.

### Task 3: the pipeline store

**Files:** create `blueprint/pipe_store.py`, `tests/test_pipe_store.py`.

`root(arg=None) -> Path` (arg, env `HOMEBASE_PIPELINE_ROOT`, `~/.homebase/pipeline`). Atomic JSON writes (temp + fsync +
`os.replace`). Functions: `add(card, subs, root, inbox=False) -> state` (refuses a name on file and a signature in
`seen.jsonl`, naming the earlier card; appends to `seen.jsonl` and `order.jsonl`; writes card.json and state.json
"queued"), `state(name, root)`, `set_state(name, root, **changes)`, `write_stage(name, n, card, root)`,
`stages(name, root) -> {n: card}`, `order(root) -> [names]` (inbox entries first, then by time), `ideas(root) -> [states]`,
`paused(root)`, `pause(root)`, `resume(root)`, `ideas_root(root)`, `runs(root)` (creates `runs/` and symlinks every
`EL/runs_bp/c1-*` folder into it once), `ledger(name, root)`, `book(root)`, `write_book(name, card, root)`.

Tests in a temp root: add / refuse a repeat signature / refuse a repeat name; order with an inbox entry; stage cards
round-trip; the pool symlinks point at the real pools and are not copied; a crash mid-write leaves the old file.

### Task 4: the gates (pure functions)

**Files:** create `blueprint/pipe_gates.py`, `tests/test_pipe_gates.py`. Read map section 4 ("Raw-number helpers").

Input is the toolkit's table data `t` (`net`, `n`: variants x days; `root`; `long`, `short`, `n_long`, `n_short`; `sides`).
- `numbers(t) -> {"share", "avg_trade", "trades", "avg_variant", "long", "short"}` from `L._profitable(t["net"].sum(1)).mean()`,
  `net.sum() / n.sum()`, `n.sum(1).mean()`.
- `raw(t) -> {"result": "strict"|"low"|"fail", "lines": [rows "P1.1" share, "P1.2" average trade, "P1.3" trades]}`. Each
  row says which bar it met ("strict", "low" or neither) in its text; `passed` is False only below the low bar.
- `rank(results: list) -> index | None`: strict before low, then the bigger average trade; None when all fail.
- `indicator(tf, traw, others: list[float]) -> rows` "P3.1".."P3.6" (spec stage 3, in order). `others` = the average
  variant net of each other-market table.
- `strict_extra(t, others) -> rows` P3.4 and P3.6 only (a strict pass from stage 1 before the proof).
- `reshuffle(t, rng=None) -> row "P4.1"`: `mc.reshuffle`, then the share of runs in which the strict share AND the full
  floor both hold (use `L._heat` / `L._floor` per run), against `need("proof", "reshuffle")`.
- `random(p_beat: float, tries: int) -> row "P4.2"`: `p_beat > random_bar(tries)` (strict), text naming tries and bar.

Tests with hand-made tables (the style of `tests/test_blueprint_lines.py::table`): exact boundary cases for every
threshold (exactly 50 % is not "over half"; average trade exactly at half the floor passes; 299 vs 300 trades), strict vs
low vs fail, rank order, each indicator line alone, the random bar at 1, 5 and 11 tries.

### Task 5: stages 1 to 4

**Files:** create `blueprint/pipe_stages.py`, `tests/test_pipe_stages.py`. Read map sections 2, 3, 4, 10 and
`blueprint/records.py:686-760` (how a round runs its tables: copy its calls, not its round counting).

Common: `ctx = {"root": <pipeline root>, "tiny": None | {"days": [...], "cells": [...], "workers": 1, "draws": 200}}`.
Every toolkit call gets `root=pipe_store.ideas_root(root)`, `out=pipe_store.runs(root)`, `ledger=pipe_store.ledger(name, root)`,
and `days` / `cells` / `workers` from `tiny` when set. A stage function is `stage_n(name, ctx, progress=None) -> stage card`;
it reads card.json and the earlier stage cards, and writes nothing itself (the runner writes the card).

- `stage0(name, ctx)`: `pipe_card.check` again; saves every sub's toolkit card with `REC.card(sub["name"], sub["spec"], ideas_root)`.
- `stage1`: for each sub, the HOME store only: `specs = [RUN.checked(e) for e in REC.engine(rspec, plan, sub_name)][:1]`,
  `RUN.run_build(specs, stage="units", ...)`, then `t = T.built(specs[0], plan["home"]["table"], None, out, days, 1, control=False)`
  and `pipe_gates.raw(t)`. `tries` = number of subs judged. `picked` = `rank`. A strategy error (`ok: False` store
  row) stops the idea as a code problem (`"code_problem": True` on the card). All fail -> `passed: False`.
- `stage2`: the machine check on the picked sub's home store: `api.code_check(sub, store=<home key>, looked=True, root=..., out=...)`
  lines 1.1-1.4 must each be True or None-with-reason; any False -> `passed: False, code_problem: True`. Then the price
  check on the middle cell: `cell, _ = REC.middle(J.table(st, u), ids)`; `rows = RUN.cell_trades(spec, key, cell, sess, days)`;
  every row's entry and exit price must lie inside the low-high of the 1-minute bar at that time (find the engine's bar
  loader in `l2sim.py`: the function `load_tape` / the bar builder `cell_trades` itself uses; if no price fields come
  back for a family, the line is None with the reason). Row "P2.5".
- `stage3` (skipped with `result: "skipped"` after a strict pass, after `strict_extra` on the other markets): run the
  other-market stores of the picked sub (the rest of `REC.engine(...)`), then for each indicator in card order: save the
  sub's card again with `run.filters = [that one]` under a filter-specific sub name `<sub>f<k>` (k = 1..5; a new toolkit
  idea, so each indicator's stores have their own name), run its units, `tf = T.built(spec, home_table, "<block>_<side>", ...)`,
  `pipe_gates.indicator(tf, traw, others)`. `tries` += indicators tried. `picked.filter` = the passing one with the
  biggest average trade; none -> `passed: False`.
- `stage4`: on the picked sub (plain or `<sub>f<k>`): `pipe_gates.reshuffle(t)`; only if it passes, `RUN.run_build(specs, stage="pools", ...)`
  and `t = T.built(..., control=True)`; `pipe_gates.random(t["controls"]["c1"]["p_beat"], tries)`.

Tests: tiny real runs in the style of `tests/test_blueprint_staged.py` (3 named days, 2 cells; `TI.tiny`'s clock and
worker patches) for the plumbing: stage 0 writes the sub cards; stage 1 writes only `<sub>-NQ-tf1` / `-tf5` stores and
no pool; with `pipe_gates.raw` patched to "low" / "strict" / "fail" the card's `result`, `picked` and `tries` follow;
stage 3 creates `<sub>f1` and judges it; stage 4 runs no pool when the reshuffle fails. Gates are patched in these tests
(3 days prove no edge): the numbers are Task 4's.

### Task 6: the 30-day prop odds

**Files:** create `blueprint/pipe_prop.py`, `tests/test_pipe_prop.py`. Read map section 9.

`odds(x, calendar, account=None, paths=None, seed=None) -> {"account", "size", "eval": p, "payout": p, "label": "stands alone"|"helper", "days": 30, "table": [per size]}`:
`r = propodds.app().load_rules(account or need("prop", "account"))`; for each size of `propodds.steps(r)`: `pnl, traded, open_, _ = propodds.days(propodds.ledger(x, size, r), r, calendar)`;
the "live is worse" row via `propodds.worse(pnl, traded, open_)`; paths from `propodds.draws(len(pnl), paths, horizon, seed)`;
`eval` = share of paths with `eval_walk(...)["outcome"] == PASS` and `day <= 30`; `payout` = share with `0 < funded_walk(...)["max_payout_at"] <= 30`.
The size with the best `eval` is the one reported (ties: the smaller). `label` = stands alone when both are above the
file's 0.5. Open losses count (they do in these walks).

Tests with `tests/blueprint_synth.py` trades: a strong steady strategy is "stands alone"; a flat one is "helper"; the
day limit matters (a strategy that passes on day 40 on average has a lower 30-day number than its no-limit number).

### Task 7: stages 5 to 7 and the book card

**Files:** modify `blueprint/pipe_stages.py`; create `tests/test_pipe_finish.py`. Read map sections 6, 7, 8.

- `stage5`: `REC.build(picked, "pipeline: stages 1-4 passed", root=..., out=..., ledger=...)` (its stores are there: it only
  reads lines 2.1-2.9; if one is False the pipeline and the toolkit disagree -> stop as a code problem with both
  numbers), `FRZ.lock(picked, ...)` (box lines 3.3-3.8; a refusal that names a box line -> `passed: False` with that
  line; the default cell is the toolkit's middle survivor: never a second box), then `pipe_prop.odds` on
  `J.cellx(st, default, session, u)` and the build calendar -> a "P5.9" row with `passed: None` and the label.
- `stage6`: `OOS.test(picked, confirm=True, root=..., out=...)`; `passed` = its `passed`; lines = its lines; the label is
  computed again from the TEST trades of the default cell (`pipe_prop.odds`) and replaces the stage 5 one.
- `stage7(name, ctx)`: builds the book card and returns it with `passed: None` (the owner decides):
  `{"name", "sub", "family", "source", "market", "session", "bar", "rule": <lock.json spec + default cell>, "label",
  "prop": {account id: {"size", "eval", "payout"}} for LucidPro no-DLL, LucidFlex, Apex 300K (an account whose rule file
  is not confirmed is listed with "unconfirmed": true),
  "hours": [first, last entry HH:MM ET], "win_days_month", "winning_months": [won, of], "biggest_day_share",
  "fast_profit_share" (profit from trades with dur_s <= 5 over total profit), "worst_day", "worst_drawdown",
  "stages": {n: {"passed", "text"}}}`. All facts from the default cell's TEST trades (`J.cellx` on the test store).
- `approve(name, root)` / `refuse(name, root, why)`: only from `awaiting_owner`; approve writes `book/<name>.json` and
  status "book"; refuse sets "refused" with the reason.

Tests: `blueprint_synth.proven(...)` gives a sub-idea that is already locked and tested without the engine: stage 7's
facts on hand-made trades (fast share with 3 of 10 dollars from 4-second trades = 0.3; biggest day share; winning
months); approve / refuse and their refusals from the wrong status. Stage 5 and 6 plumbing with `REC.build`, `FRZ.lock`
and `OOS.test` monkeypatched to canned results (their own tests cover them): a build line False -> code problem; a
lock refusal on 3.4 -> stopped at stage 5 with that line; a failed test -> stopped at 6, final.

### Task 8: the runner and the commands

**Files:** create `blueprint/pipe_runner.py`, `tests/test_pipe_runner.py`; modify `blueprint/cli.py`,
`tests/test_blueprint_cli.py` (or the file that tests the parser).

- `step(name, ctx) -> state`: runs the NEXT stage of one idea, writes its card and the new state. Rules: a stage with
  `passed is False` -> status "stopped" (or "code_problem"), `stopped_at`, `why` = the first failed line's text; stage 6
  passed -> stage 7 -> "awaiting_owner"; `J.Refuse` / `api.REFUSALS` from a stage -> "stopped" with the refusal as
  `why` unless it is `RUN.may_start`'s window refusal (then the state is unchanged and the loop sleeps to the window's
  end); any other exception -> "code_problem" with the exception text, and the loop goes on with the next idea.
- `loop(ctx, once=False)`: holds `runner.lock` (flock; a second runner exits 0 saying one is running); repeatedly takes
  the first idea in `order` whose status is queued or running, calls `step` until it stops or waits; checks `paused()`
  between stages; with nothing to do sleeps 60 s (`once=True`: returns). Logs one line a stage to `runner.log`.
- `start(root)`: detached `bp.py pipe _loop --root=...` (`start_new_session=True`, like `jobs.start`), writes its pid.
- CLI (`--json` like every command): `pipe add --spec=-|FILE [--inbox]` (stage 0's check runs first: a card that is not
  whole is refused with its rows and nothing is saved), `pipe list`, `pipe show <name>`, `pipe start`, `pipe pause`,
  `pipe resume`, `pipe approve <name>`, `pipe refuse <name> --why=TEXT`, `pipe book`. Text output of `list`: one row
  an idea: name, family, status, stage, tries, why.

Tests: stages monkeypatched to canned cards: an idea that fails stage 1 stops there with the line in `why` and the next
idea starts; a crash in a stage marks code_problem and the loop continues; kill-and-resume (run `step` twice with the
state on disk: the second call starts at the next stage, never repeats one); pause stops between stages; two loops: the
second exits; the window refusal leaves the state as it was; the CLI commands end to end through `C.main` in a temp
root.

### Task 9: end to end, and the law's text

**Files:** `tests/test_pipe_end_to_end.py`; modify `research/edge-library/BLUEPRINT.md` (a new section "The pipeline"
that points at the spec and lists the changed numbers: 3.7, 3.8, 4.6, 4.7).

One real tiny run through `bp.py pipe add` + `loop(once=True)` with the gates patched to pass and `BP_TEST_RUN`-style
tiny days for the build, lock and test (see `tests/test_blueprint_test.py` for how a tiny test range is given): the idea
ends "awaiting_owner" with seven stage cards, `approve` puts it in the book, and nothing was written outside the temp
root except the tiny stores' folder. Then the whole suite: `tests/` (all green) and `engine/tests`.

### Task 10: speed (the owner, 2026-10-07 evening: "run even more at once")

Measure first, then change; report the numbers.

- **Batch stage 1.** `RUN.run_build` already runs every store of one (market, bar, engine settings) in ONE tape pass
  (its `groups`). Measure a pass with 1, 3 and 6 sub-ideas' home stores on NQ 5-minute bars (wall time, peak memory).
  If a batch is clearly cheaper than its parts, `pipe_runner.loop` takes stage 1 of every queued idea of the same
  market and bar in one `run_build` call (each idea keeps its own stage card; the per-idea ledger becomes one ledger a
  batch, split afterwards by key).
- **More workers off desk hours.** Measure peak memory a worker on NQ 1-minute bars. If 12 workers fit in 24 GB with
  4 GB spare, raise `compute.json` `workers.other` 8 -> 12 and `l2sim.MAX_WORKERS`' ceiling 8 -> 12 (the tests that pin
  8 change with it). Desk hours stay at 4 while the desk runs on this machine.

## Known limits of this plan (tell the owner)

- "The entry signal was really there, re-derived by separate code" (spec, stage 2) is NOT built: there is no second
  implementation of the 28 entry rules. Stage 2 checks every trade's session, single position, count and payoff, and the
  middle box's prices against the raw bars. Each block keeps its own unit tests.
- Two indicators at once, the Lab screens, the luck rate, the score since the lock, portfolios and the hunter are the
  later plans.
