# The Charts page went black: a 300 MB plots file was parsed and JSON-encoded on the event loop

**Date**: 2026-10-11
**Context**: main; Charts service :8852 (also serves the Lab). Commits `d59cf736`, `cd7d5013` (lag watchdog), `e3504ea3` (fix).

## What we set out to do

The owner's Charts tab showed NQ and ES stuck on "Loading…" and "chart service unreachable — retrying".

## What we found

| | Before | After |
|---|---|---|
| `GET /api/tester/run/<id>/bundle` of `draft_nq_6pm_vwap_bands` | 299,650,145 B, 21 s, event loop blocked | same bytes in 3.1 s; `/api/status` probes during it max 0.77 s |
| Service memory while it ran | 4.5-5.1 GB at 100% CPU | ~1.6 GB transient |
| Server-side prop re-score of that run | parsed all of `plots.json` (~3 GB of lists) | `plots=False`: never read |

- **Cause.** The 6 PM VWAP-bands draft calls `ctx.plot()` per bar for 7 series over 4 years: 1.23 M points each,
  8.6 M in all, `plots.json` = 300 MB, written with no cap. Anything that loaded that run hit three costs:
  the bundle route parsed it and FastAPI's `jsonable_encoder` then re-encoded the dict **on the event loop**
  (the stack the lag watchdog logged: `MainThread [GET .../bundle]: serialize_response > jsonable_encoder`);
  `_rescore` / the Desk's pre-warm / Monte Carlo parsed it again only to read `trades.json`.
- Three such runs existed (22:21, 22:29, 22:33). The page loads the latest run when the Lab opens or a run is shown,
  so every app launch or service restart re-triggered it: the 22:25 hang, and the 100% CPU / 5 GB seen 76 s after
  the 22:33 restart.
- My first reading ("JSON/gzip in worker threads") was only the visible side-effect; the sample could not name
  the route because the loop thread's stack is all framework code. The watchdog's `[METHOD /path]` tag did.
- A second, separate stall the watchdog found: websocket permessage-deflate compressing multi-MB history
  messages on the loop (fixed by another session, `8d03dbf0`: `ws_per_message_deflate=False`).

## Why it happened

FastAPI encodes a plain `dict` return value with `jsonable_encoder` on the event loop, whatever the route
function is; nothing capped a strategy's plot series; and `read_bundle` read every file even where only trades
were needed. A per-bar indicator over four years is the first thing to make `plots.json` large.

## What changes because of this

- `runner.read_bundle(d, plots=False)`; the bundle routes answer file bytes (`read_bundle_bytes`), never a parsed dict.
- `runner.thin_plots`: every series kept to 100,000 points when a run is written; `plots.json` gets `thinned: {name: k}`.
- `homebase/charts/lagwatch.py` stays: a loop 3 s late writes the busy threads (and the request each serves) to `charts.log`.
- Rule: a route that can return more than a few MB must return bytes / a streaming response, not a dict.
- Open: the three existing 300 MB runs keep their full files (they are another session's drafts); they now serve in
  ~3 s but the page still parses 300 MB. Deleting them from the Lab list removes it.

## References

- `homebase/backtest/runner.py` `thin_plots`, `read_bundle`, `read_bundle_bytes`; `homebase/charts/tester_api.py` `/run/{rid}/bundle`
- `homebase/charts/lagwatch.py`; related: `2026-10-11-app-slow-tab-switch-cold-caches-and-state-walk.md`
