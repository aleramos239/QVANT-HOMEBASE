# The app felt slow between tabs: cold server caches, one of them a 108,000-entry directory walk

**Date**: 2026-10-11
**Context**: main; Homebase desktop app (Desk :8850, Charts + Lab :8852). Commits `7b4b8e0f`, `0f4b4e28`.

## What we set out to do

The owner said the app "feels really slow, especially when I go in between tabs". Find out why, with numbers.

## What we found

The pages themselves are light: Desk 683 nodes / 180 ms load, Charts 472 nodes / 190 ms, no long tasks, 3-13 ms polls.
The cost is the **first request after a cache lapses**, and the Lab load fires three of them at once.

| Request (cold) | Before | After |
|---|---|---|
| Lab page load | 6,930 ms | not re-measured in the app |
| `/api/tester/strategies` (asked twice) and `/api/tester/drafts` | 6,812 / 6,774 ms | 489 / 477 ms |
| `draftstore._shadow_names()` walk | 2.45 s, 1,344 names | 0.001 s, 124 names |
| `/api/tester/desklab/results`, first ask after a restart | 25,852 ms; 92,544 ms under load | 136 ms (pre-warmed) |

- **Cause 1 (fixed, `7b4b8e0f`).** `draftstore._shadow_names()` did `homebase/.rglob("*")`. `homebase/.state` holds every
  tester run and heat-map cell: 107,888 entries, 16 GB (76,620 in `grids/`). `validate_name()` calls it for every draft
  listed; its 60 s cache lapsed, and every concurrent caller then walked the tree itself. The code's own docstring
  said "Walking the package is slow (it holds the service's state directory)".
- **Cause 2 (fixed, `0f4b4e28`).** `/desklab/results` re-scores ~16 saved runs through the prop sim (~1.5 s each unloaded);
  the cache is in-process, so every Charts restart made the first Desk ask pay all of it, and the Desk asks on every
  tab-visibility change. Now a daemon thread scores them once after startup (saved runs only, starts nothing).
- **Contributor, mitigated.** The pipeline's worker pools (6-12 processes at 70-95% CPU) ran at nice 0 while the Charts
  service ran at nice 5: load average 17-30 on 15 cores, and `/api/status` took 350-580 ms instead of 4 ms. The runner
  now nices itself to 10 (workers inherit it); the running one was reniced live. Load average fell to ~5.5
  afterwards, but the pipeline was also between bursts, so that drop is not proof.
- **Not a cause (my first guess was wrong).** The directory walk does NOT stall other endpoints: probes stayed 2-14 ms
  while a cold walk ran. Only the requests that need the draft-name check pay it.

## Why it happened

`.state` grew from nothing to 16 GB while a walk written when it was small stayed in the request path. A cache with a
60 s TTL hides this from anyone who is active in the app: the cost lands on the first request after a pause, which is
exactly "switching to another tab". It is also why timing a warm endpoint says everything is fine (3-5 ms).

## What changes because of this

- Never walk `homebase/` (or anything above `.state`) from a request path. `draftstore._shadow_names()` skips hidden dirs;
  `tests/test_claude_drafts.py::test_shadow_names_skip_hidden_directories` locks it in.
- To judge "slow" in this app, time the endpoints **cold** (right after a restart or after the TTL), not warm.
- A Charts restart knocks the paper accounts off the desk: the first restart left `PAPER` and `9:30 Straddle`
  disconnected until a forced `account_reconnect` (which reconnects all nine accounts, not just those two). The second
  restart needed nothing. Check `desk_readiness` after every restart.
- Open: the other session's "Desk straddle twins" block in the same results route is not pre-warmed (it was uncommitted
  and not mine to wire). The in-app feel after the restart is not yet confirmed by the owner.
- Open: `tests/test_charts_settings_server.py::test_m2_get_settings_carries_an_accounts_block` fails in the main checkout
  because it assumes no `config.json` (it passes in a bare worktree). Unrelated to this change.

## References

- `homebase/draftstore.py:87` `_shadow_names()`; `homebase/charts/tester_api.py` `warm_desklab_results`, `desklab_results`
- `homebase/charts/server.py` lifespan (starts `desklab-warm`); `research/edge-library/blueprint/pipe_runner.py` `_loop`
- Related: `docs/superpowers/findings/` tape-cache note (draft heat maps 10x slower with a cold shared cache), vault
  `30-Projects/Onyx-Trading/tape-cache-must-stay-warm.md`
