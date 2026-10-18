# One pipeline, two tags: implementation plan

> For agentic workers: executed natively in the session (superpowers:executing-plans), one fresh reviewer at the end.

**Goal:** the pipeline judges a strategy by size-free numbers at one contract and tags each pass Live or Live + Prop.
**Architecture:** gates mode "prop" becomes "edge": the same label machinery, minus the eval odds, plus row P3.15. The
book card gains the shown numbers and the tag. The profiles, the switch's extra choices and the group step go.
**Tech:** Python 3.9 research venv (`.venv-research/bin/python -m pytest tests/`), FastAPI tester_api, vanilla JS lab.js.
**Spec:** `docs/superpowers/specs/2026-10-18-one-pipeline-two-tags-design.md`

## Global constraints
- Every number in `blueprint/templates/pipeline.json`: `edge.wr_cushion 0.03`, `edge.min_trades 200`, `edge.prop.sharpe 1.0`,
  `edge.prop.months_positive 0.6`.
- Never write `payout_enabled`; never run `pipe payout enable`.
- Win = trade net above $0 after costs (as P3.11).

## Review focus
- A box with no losing trade: realized R:R undefined -> P3.15 passes, text says so.
- A box with no winning trade: win rate 0, breakeven undefined -> P3.15 fails.
- A stale `~/.homebase/pipeline_profile` word ("funded", "wr") reads as live, no raise.
- Sharpe on a box whose daily P&L has zero spread -> None, tag cannot be Live + Prop.
- An old stage card on disk with eval-odds fields still renders in `pipe show` and the Lab Book.

## Task 1: rules and switch
Files: `blueprint/pipe_rules.py`, `blueprint/pipe_switch.py`, `blueprint/templates/pipeline.json`, delete
`pipeline_wr.json`, `pipeline_payout.json`, `pipeline_funded.json`; tests `test_pipe_rules.py`, `test_pipe_switch.py`,
`test_pipe_profiles.py`.
- `GATES = ("law", "edge")`, `edge_gates() -> bool`; `PROFILES = {"live": ...}`; `active()` returns "live" for any stored word.
- `set_settings` refused always. `edge` block parsed; the old `gates.variant` overlay applies in edge mode.
- `CHOICES = ("off", "live")`, `LOCKED = {}`.

## Task 2: row P3.15 and the pick
Files: `blueprint/pipe_gates.py`, `blueprint/pipe_stages.py`; test `test_pipe_gates.py` (new P3.15 tests), `test_pipe_prop_gates.py` -> edge.
- `pipe_gates.wr_rr(net: np.ndarray) -> row` P3.15: win rate, realized R:R = mean(win) / |mean(loss)|, breakeven 1/(1+rr),
  passed = rate >= breakeven + cushion.
- `_box_rows` adds P3.15 (a stop in edge mode); `_holding` asks no eval odds; `_outward`/`_pick` rank by average trade.

## Task 3: stages 5 to 7
- Stage 5: no P5.9 prop row in edge mode. Stage 6: P3.15 on the unseen trades is a stop next to box and 4.4; no prop block.
- `_facts` adds win_rate, realized_rr, breakeven_wr, avg_r, net_per_year, sharpe, months_positive, worst_drawdown_r, month_wr.
- Stage 7 book card: `tag` "live" | "live+prop", the numbers for build and unseen.

## Task 4: removals and surfaces
- Delete `pipe_mix.py`, `pipe_portfolio.py`, their tests, the `mix`/`portfolio` blocks, `pipe mix|portfolio|profile|settings|payout`
  CLI verbs, runner `_idle` payout work and `portfolio` sub, tester_api `/pipeline/profile|settings|payout`, MCP pipeline_profile /
  payout, Lab WR settings + Payout view; Book shows the tag.

## Task 5: verify
- Full research suite + `tests/` app suite for touched files; one fresh reviewer on the diff; vault note.
