# Homebase — rules for assistants working in this repo

## Strategy work follows the blueprint (house law, 2026-10-05)

Any request to build, test, backtest, optimize or judge a strategy or a strategy idea follows
`research/edge-library/BLUEPRINT.md`, section 2 (skill: `strategy-blueprint`). Read it before the first run.

- Phases, in order: idea card → code check → build → lock → one out-of-sample test → before the eval → the eval.
- Build days: 2021-09-22 → 2025-06-30. All tuning happens here.
- Test days: 2025-07-01 → latest. One read, only for a locked strategy. Never for a quick look or "all data".
- Judge the average of all variants, never the best cell.
- `research/edge-library/judge.py` still scores the old rules (v2). A v2 verdict is not a blueprint verdict.
- Talk to the owner in simple, minimal words: the answer first, a small table, no jargon.
