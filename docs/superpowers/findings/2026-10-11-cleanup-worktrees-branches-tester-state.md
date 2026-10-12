# Clean-up: 30 GB of dead worktrees, 126 merged branches, 6.5 GB of old tester output

**Date**: 2026-10-11
**Context**: main; repo directory was 91 GB. Commits `2aaf03ef` (prune tool), `6768a404` (dead helpers, warm).

## What we set out to do

The owner asked to inspect the app and clean up dead weight, speed it up, clean the code.

## What we found

| Where | Before | After | How |
|---|---|---|---|
| `.claude/worktrees` (agent worktrees, `lead`, toolkit-view) | 30 GB, 11 worktrees | 0 | `git worktree remove`; every one fully merged into main, clean, no process in it |
| `.worktrees/*` merged + clean (9) | ~25 GB | 0 | same; kept the ones with unmerged commits, uncommitted work or active sessions |
| local branches | 139 | 14 | `git branch -d` (merged only); 2 unmerged + worktree-held kept |
| `homebase/.state/tester` | 11 GB (776 runs, 242 grids) | 4.9 GB | new `python -m homebase.backtest.prune --days 7 --yes`: unreferenced from ~/.homebase, not running |
| repo directory | 91 GB | 33 GB (14 GB of it live worktrees, 9.4 GB state, 7.8 GB research) | |

- Nothing in the app ever deleted a run, heat map or walk-forward; the lists the Lab loads grew with them.
- A walk-forward folder holds its own `spends.jsonl` (the test-days ledger). The prune tool appends those lines
  to `tester/spends.jsonl` before it deletes (3 lines moved). Heat-map cells' spends were already in the shared one.
- Code is tidy: vulture at 90% confidence found one unused variable (a `*exc` signature, not a bug) in 49 k lines
  of `homebase/`; at 60%, 86 candidates, 4 truly dead (removed), the rest dispatched by name (MCP tools) or API wrappers.
- Not touched: `research/` (7.8 GB on disk, 17,688 tracked files incl. 70 MB `.npz` per heat-map table and
  `.bak` / `.pre-*` copies; `.git` is 2.4 GB because of it), `.state/charts/cache` (4.8 GB, regenerable but it is what
  makes timeframe switches fast), `~/.homebase/pipeline` (505 MB, the Book).

## What changes because of this

- Run `python -m homebase.backtest.prune` (dry run) now and then; `--yes` deletes. Default keeps 7 days.
- Desk results pre-warm now includes the two straddle twins and repeats every 2 min (first ask 3.8 s / 25-90 s -> 37 ms).
- Open (owner's call): trim `research/` (move big `.npz` / `.bak` out of git), schedule `charts.warm` nightly,
  cap the pipeline poll (a `bp.py` subprocess per 5 s poll while the Lab Pipeline tab is open).

## References

- `homebase/backtest/prune.py`, `tests/test_backtest_prune.py`
- Related: `2026-10-11-charts-black-page-300mb-plots-bundle-on-the-loop.md`
