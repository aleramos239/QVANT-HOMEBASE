# Chart timeframe switches were slow: an empty bar cache and a quadratic resample

**Date**: 2026-10-11
**Context**: main; Charts service (:8852) `/ws` `sub`; `homebase/charts/{history,bars,warm,hub}.py`. Commit follows `0f4b4e28`.

## What we set out to do

The owner: "switching in between timeframes on the chart is very slow." Time a switch the way the page does and find the cost.

## What we found

A switch is a websocket `sub` with a new `spec`; the server builds the stream with `hub.prepare`, capped by
`BUILD_BUDGET_S = 2.0`. Timed with a client that speaks the page's protocol (cold, NQ):

| Timeframe | Before | After |
|---|---|---|
| 1m / 5m / 15m | 3-90 ms (5 sessions, memoized) / 723 ms | 53 / 5 / 109 ms |
| 1h | 3,052 ms, partial | 157 ms, complete |
| 4h | 2,049 ms, partial (168 bars) | 601 ms, 1,530 bars |
| 1D | 2,095 ms, partial (12-38 bars) | 498 ms, 258 bars (a year) |

ES 4h / 1D are still ~1.7 s (complete): an ES daily bar carries ~29,000 big prints (>= 10 lots), about 660 KB a session.

- **The 1-minute bar cache was nearly empty.** `<state>/charts/cache` held 19 pickles (15 NQ, 4 ES, none older than 2026-09-21);
  GC / YM / RTY / SI had none. `warm.py` says "Not scheduled: run it by hand" and nobody had. A cold session is
  ~1.5 s from raw ticks, 2 ms from its pickle. A 1h chart needs 20 sessions, 4h / 1D need 250.
- **Even cached, a coarse bar was expensive.** 23 ms to unpickle a session's 1,380 one-minute bars, then ~85 ms in
  `Bar.merge`, which copied and re-sorted both the sweep and the bubble list at every one of ~1,380 merges.
  250 sessions came to ~14 s against a 2 s budget, so every switch was cut off, then the page fetched the rest in 2 s chunks.

## Why it happened

The history layer was designed around "a cached 1-minute pickle, resample on demand", and the budget makes a cold
cache degrade quietly into "partial" instead of failing, so nothing ever looked broken. Resampling was fine on a
60-session test chart and quadratic-ish in practice (sorted lists inside a per-bar loop).

## What changes because of this

- `resample` merges with `cap=False` and caps once per output bar (`Bar.finish_merge`). The cap keeps the top rows of
  a total order, so the rows are identical (checked on 450 real resamples; `test_resample_caps_sweeps_and_bubbles_once...`).
- `History._coarse`: 15m / 30m / 1h / 4h / 1D bars are also kept per session beside the minutes pickle, same freshness
  rule (stamped with the tick file's mtime). `warm.py` builds them. Backfilled the last year, all six roots (3.5 GB).
- Open: nothing re-warms the cache. New sessions build once on first view (~1.5 s) and a repair that rewrites a day
  rebuilds it the same way. A twice-daily launchd job like `homebase-tapewarm` would hide both; not installed (the
  owner's call).
- Open: ES's big-print volume. Capping `big` per coarse bar, or loading it lazily, would change what a daily bar
  carries, so it is not done.
- `memo_max = 256` entries is a count, not bytes: an ES 1D chart already holds up to 250 entries of ~660 KB on disk,
  so raising it is not free.

## References

- `homebase/charts/hub.py:285` `prepare` and `BUILD_BUDGET_S`; `homebase/charts/history.py` `_coarse`, `bars`
- `homebase/charts/bars.py` `Bar.merge`, `Bar.finish_merge`, `resample`
- Related: `2026-10-11-app-slow-tab-switch-cold-caches-and-state-walk.md`
