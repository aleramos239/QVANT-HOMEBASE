# Release release/2026-10-01-algos

Branch `release/2026-10-01-algos` (from main 41b96bd, the gc_nfp desk). Worktree `.worktrees/rel16`.

**Status, checked 2026-10-04: merged.** Every commit listed below is in `main`, and `main` has moved on (42 commits after `9599283`, the last commit of this release). The rest of this file is the record as it was written on 2026-10-01. Read "Deploy" and "Rollback" as history, not as steps to run. For how the app works now, see `README.md`.

## Commits
1. `2da9bbc` Merge `feat/nq-prop-algos-daily-rules` (fc560e1 + da4f215): the four "levels" algos nq_nyam_flex, nq_nyam_pro, nq_orb_pro, nq_pm_flex, daily rules (dayrules.py), their own timer (leveltimer.py).
2. `8891cb6` Remove ym930, nq10am, nq_open_long, nq_open_short (config defaults, strategy classes, rules.py `_open_930` / `nq_10am_continuation`, UI names, test pins).
3. `a1a5546`, `929b4e0` `config.load()` drops any strategy (and its book rows) with no shipped default, logs it, rewrites the file clean once.
4. `263d208` `inactive_today`: a booked strategy that will not trade says why once a day (journal + readiness).
5. The rehearsal test `tests/test_release_rehearsal.py` and this file.

## Merge conflicts resolved (both behaviours kept)
`config.py` (StrategyCfg: gc_nfp's `fire_et` / `only_dates` / `trades_on` plus the levels fields; one `fire_et`), `server.py` (imports `schedule` / `fire_time` for gc_nfp and `LevelTimer`), `strategies/__init__.py` (REGISTRY has GCNfp and the four NQ classes), the pinned research bundle fixture (regenerated: only `desk_cfg` gained keys, no number moved), and three registry-pin tests. `timer.py`, `engine.py`, `trading.py` auto-merged. `tests/test_gc_nfp.py` is untouched and green.

## What changed
- New desk strategies ship `enabled=False`, unbooked. Nothing trades until the user books and enables them. Real (non-paper) accounts also need `ack_open_loss` or they sit out.
- Removed: ym930, nq10am, nq_open_long, nq_open_short, with their tester registry entries and tests. nq930 and gc_nfp kept. `RULES` is now empty (kind "bars" and the feed machinery stay).
- At release time config.json still held ym930 / nq10am / nq_open_long / nq_open_short, and book rows for 4 apex accounts (35 ct each) on the two nq_open_*. On the first start after the merge `load()` drops them, logs `config.json: dropped strategy ...`, and rewrites the file.
- Silent-skip fix (the nq_open_short case): `homebase/inactive.py`. Journal event `inactive_today` (strategy, code, reason), once per day per code, restart-safe, plus a readiness `warn` "inactive today - why". Codes: not_scheduled_today (journal only; readiness stays silent so gc_nfp's readiness is unchanged), not_self_fire, unknown_rule, bad_shape, early_close, every_account_sits_out (ack_open_loss missing / no prop block for target_take / day locked), no_signal (a bar rule gave nothing in its window), and at the fire: no_geometry (no ATR data, no print), contract_changed (roll guard), missed, outside_window, bad_geometry, no_assignments. A 20 s sweep task in the server journals the static ones.

## Tests
Counts are from the release branch on 2026-10-01. The commands are still the right ones.
- Python: 2569 passed (`.venv/bin/python -m pytest -q tests`).
- JS: 985 passed (`node --test tests/js/*.test.mjs homebase/static/*.test.js`).
- Rehearsal (`tests/test_release_rehearsal.py`, 5 tests, fake broker / clock / market data, 07:50-16:00 ET ticked every few seconds): Fri 2026-10-02 gc_nfp fires at 08:29:59 (not at 08:29:58), exact OCO levels, OCO sibling cancelled on a fill, fires once; Mon 2026-10-05 gc_nfp silent and says `not_scheduled_today` once; each levels algo stages and fires at 09:30 / 09:30 / 11:05 / 13:30 on booked paper accounts with the right stops, take sizing, no_fill cancel at 10:55, stop-out (no lock), day_take lock; a locked account makes later algos journal `inactive_today`.

## Deploy (done — kept as the record)
The merge below has happened; do not run it again. The restart command is still the right way to restart the desk.

As written on 2026-10-01: do it outside 09:20-09:35 ET, and after the 2026-10-02 08:29:59 fire if you want zero risk to it. The desk runs from the main checkout.
```
cd ~/ramos-quant-homebase
git status --short          # uncommitted edits (slots.py, conftest.py ...) must be committed or stashed first
cp homebase/config.json homebase/config.json.pre-algos-release     # backup
git merge --ff-only release/2026-10-01-algos
launchctl kickstart -k gui/$(id -u)/com.ramosquant.homebase        # restart the desk
```
Then check the journal for the `dropped strategy` log lines, that the accounts reconnect, and the armed state. At release time gc_nfp was not in config.json: the defaults supply it off and unbooked, so the user books and enables it.

## Rollback (no longer valid — do not run)
`git reset --hard 41b96bd` would now also throw away everything merged after this release (50 commits on `main` since `41b96bd`). The backup file named below is not in the folder either: the copies there are `homebase/config.json.pre-algos-2026-10-01`, `.pre-gc-nfp` and `.pre-metrics-2026-10-01`. The commands are kept only as the record of the plan.
```
cd ~/ramos-quant-homebase
git reset --hard 41b96bd
cp homebase/config.json.pre-algos-release homebase/config.json
launchctl kickstart -k gui/$(id -u)/com.ramosquant.homebase
```

## Not proven
- Real broker acks / fills: the engine ran against `FakeAdapter`. Tradovate behaviour for the "levels" stop-with-bracket orders and the day_take market-flatten backstop is untested outside fakes.
- Broker-fed bars: LevelTimer's ATR comes from md prints plus the chart-history read; the rehearsal serves a synthetic tape. ATR parity with the research tester is unit-tested and audited at runtime (`level_atr_parity`), not proven on a real session.
- target_take on real eval accounts needs `prop` blocks (start_balance, rules, mode) in config.json; none exist for the current accounts, so a booked nq_nyam_pro would journal `every_account_sits_out`.
- Lucid's open-loss rule against the 3 x ATR stop is an assumption (`ack_open_loss`).
