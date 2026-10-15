# The FUNDED PIPELINE (2026-10-15)

**What the owner asked for:** "add a new pipeline in homebase based off this finding" — the 75 % table of
`docs/superpowers/findings/2026-10-15-75pct-payout-20-weekdays-win-rate-by-rr.txt` (the lowest win rate that still gives a 75 %
chance of the MAXIMUM payout within 20 weekdays on a funded LucidFlex 50K, by reward-to-risk and trades a day). His rule:
**"the unseen data metrics must fall into at least one of"** the table's rows. Name: **FUNDED PIPELINE** (button "Funded").

## How it is built

A fourth PROFILE of the same idea runner (`pipe_rules.PROFILES["funded"]`, `templates/pipeline_funded.json`), chosen in the
Lab's Pipeline bar or `bp.py pipe mode funded`. One pipeline works at a time, as before. It has no lock (it trades nothing).

The rules file is the WR PIPELINE's (prop gates, variant mode) with the win-rate lane OFF and one new block, `funded`:

| Where | Row | Asks |
|---|---|---|
| Build days, the pick | P3.14 | the box's trades fall into a row (the pick is made among boxes on the line) |
| Unseen days, the one read | P6.2 | the box's unseen trades fall into a row (with P6.1: it makes money) |
| The group, `bp.py pipe portfolio` | PF.1 | the mix's trades together fall into a row WITH its trades a day, and the max payout within 20 session days is 75 % or more on LucidFlex 50K funded |

"Falls into a row" (`pipe_funded.fits`): a row whose reward is at or under the box's AND whose win rate is at or under the box's.
One strategy is not held to the trades a day (they are the whole portfolio's); the group is. Win = a trade with a net above $0
after costs; reward = average win / average loss in R (R = net / (stop points x point value)). A box needs 30 trades with a
stop (`funded.min_trades`) before its numbers are read.

With the line on, one box's eval odds are shown, not asked. The group is judged on the funded account alone (`funded_only`), so
the account's consistency rule (LucidFlex: its eval's) is not applied. Labels on the group, asking nothing: daily Sharpe 0.5+,
the highest correlation of two members under 0.3, the worst day at the payout size at most 40 % of the drawdown.

A book card filed under another pipeline is held to P6.2 in the group stage (left out with the reason when it misses).

## Files

`blueprint/pipe_funded.py` (new) · `blueprint/pipe_rules.py` (profile, `funded()`) · `blueprint/pipe_gates.py` (`funded`, P3.14) ·
`blueprint/pipe_stages.py` (trade stops on a box, eval odds not asked, P6.2) · `blueprint/pipe_portfolio.py` (account, PF.1,
labels, members off the line) · `blueprint/pipe_switch.py`, `blueprint/cli.py`, `homebase/claude_mcp/pipeline_tools.py`,
`homebase/static/charts/lab.js` (the choice) · tests: `tests/test_pipe_funded.py` (new), `test_pipe_switch.py`, `test_pipe_finish.py`,
`tests/js/labpipe.test.mjs`, `tests/test_tester_pipeline.py`.

## First read on the real book (2026-10-15, read-only)

The three book strategies all miss P6.2: `nq_donch_first_nyam` 18.8 % at 1 : 5.9, `nq_noise_gx_mid_long` 34.2 % at 1 : 2.6 (the
1 : 2.5 row needs 40 %), `nq_supertrend_nyam_short` 61.3 % at 1 : 1.0 (needs 62.5 %). No mix can be made yet.
