# Deploy gc_nfp (GC 8:30 NFP straddle) for Fri 2026-10-02

Nothing here has been run. The branch is built and tested; the live desk (port 8850, armed) is untouched.

- Branch: `nfp-gc-straddle-2026-10-02` (one commit, `1afa357`, on top of main `8fd46ea`)
- Worktree: `/Users/ramoscapital/ramos-quant-homebase/.claude/worktrees/wf_6efdccad-5c5-4`
- Tests: full suite 2402 passed (2382 before, +20 new in `tests/test_gc_nfp.py`)
- Review: `docs/superpowers/findings/2026-10-01-gc-nfp-review.md` on the branch (read its verdict before you buy evals)

## What it is (the exact spec)

GC, 4 contracts per account (you set it per account when you assign), fires 08:30:00.000 ET on 2026-10-02 only.
Anchor = last print before 08:30:00. Buy stop anchor +2.0, sell stop anchor -2.0, stop 3.7 pts from the fill
(-$1,480 at 4 ct before slippage), target 7.7 pts from the fill (+$3,080 gross, +$3,061.60 after Lucid's $2.30 a side).
Unfilled entries cancelled 08:45, anything open flat 09:55. A fire later than 08:31:00 is refused (never re-anchored on a
post-release price). It ships OFF and with nobody booked: you book and switch it on.

What changed in the code (so you know what you are restarting into):

- `timer.py`: each strategy has its own fire time (`fire_et`; default 09:30:00, so nq930/ym930/nq10am behave exactly as
  before, pinned by tests). Gate = fire -10 min, prestage = fire -90 s, done = fire +1 min.
- `config.py`: new fields `fire_et`, `only_dates`; new strategy `gc_nfp` (`only_dates: ["2026-10-02"]`). Any other day it
  has no timer state, no feed subscription, no readiness check, and the engine refuses an alert (`not_a_trading_day`).
- `broker/tradovate.py`: token renewals are kept out of 08:25-08:50 (renewed early at 08:10-08:25 if they would have
  come due). Applies every weekday. The 09:10-09:35 rules are unchanged.
- `trading.py`: the desk's view refresh pauses 08:29:50-08:30:30 only while an enabled 08:30 strategy trades that day.
- `server.py`, `review.py`, `static/index.html`: readiness, journal text and the "will trade real money at the next 8:30
  fire" confirmation follow the strategy's own fire time.
- `strategies/gc_nfp.py`: the tester twin (reads the desk config), registered as `gc_nfp` in the tester.

## 1. Merge (you run it)

```bash
cd /Users/ramoscapital/ramos-quant-homebase
git status --short          # main has your own uncommitted slots.py / tests edits: they do not overlap, leave them
git merge --ff-only nfp-gc-straddle-2026-10-02
```

If it says it cannot fast-forward, main moved since `8fd46ea`: run `git merge nfp-gc-straddle-2026-10-02` instead and
rerun the tests (`.venv/bin/python -m pytest -q`, about 3 minutes).

## 2. Back up the desk config, then restart (you run it)

Do this tonight after 18:00 ET, or tomorrow before 07:45 ET. NEVER 08:15-08:50 or 09:10-09:35 ET (the desk refuses
writes in the second window and the first is the fire). A restart costs one login per Tradovate user (rate-limited), so
do it once, not repeatedly.

```bash
cd /Users/ramoscapital/ramos-quant-homebase
cp homebase/config.json homebase/config.json.pre-gc-nfp          # REQUIRED for the rollback below
launchctl kickstart -k gui/$(id -u)/com.ramosquant.homebase       # the desk, port 8850
launchctl kickstart -k gui/$(id -u)/com.ramosquant.homebase-charts   # optional: only so the tester lists gc_nfp
```

Check after it is back (30-60 s):
`curl -s localhost:8850/api/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['armed'], d['strategies']['gc_nfp']['cfg'])"`
should show `True` and a cfg with `fire_et 08:30:00`, `only_dates ['2026-10-02']`, `enabled False`. All your accounts must
show connected on the page. The desk's `desk_readiness` MCP tool is the same read-only check.

## 3. In the UI (you do it, before 07:45 ET tomorrow)

1. Add the Lucid Pro eval accounts through the Connect wizard if they are not on the desk yet. Not later than 08:00:
   adding accounts, reconnecting and removing are unsafe 08:20-08:50.
2. On the desk page open the `gc_nfp` card ("GC 8:30 NFP Straddle"), click `+ Assign`, pick each Lucid eval, set the qty
   (4 is the spec; whatever you pick is the exact number of GC contracts that account trades). Confirm the "Book live"
   dialog: it should read "...at the next 8:30 fire". Give EVERY eval the same qty (4). Do not mix sizes or offsets:
   Lucid bans long in one account and short in another, and identical straddles from one fire avoid that.
3. Switch `gc_nfp` ON. Check the desk is armed (it is today).
4. You said tomorrow is only the 8:30 straddle: switch OFF `nq930` (on today, booked on paper-5) and `nq10am` (shadow)
   if you do not want them at 9:30. `nq_open_*` are already off. This is your call, nothing in this branch changes them.
5. Do not touch the desk, accounts or chart-trading from 08:20 to 08:50. The tester must not run jobs 08:15-08:45.

Expected journal tomorrow (the Activity feed on the page, or `homebase/.state/journal.jsonl`): `prestage_rtt` (08:28:30),
`timer_fired` (08:30:00, anchor = last print), `placed` per account, then `entry_fill`, `brackets_moved`, and either a
bracket exit, `cancelled_unfilled` at 08:45, or `clock_flat` at 09:55. Run `python -m homebase.review 2026-10-02` after.

## 4. Rollback

Fastest, no restart (use this if you change your mind or anything looks off before 08:20): switch `gc_nfp` OFF on the
desk page, or unassign the evals. It fires on no day other than 2026-10-02, so leaving it ON after tomorrow does nothing,
but switch it off anyway.

If something goes wrong DURING the fire: use the page's Flatten & turn off for `gc_nfp` (flattens every account it acted
on) or Kill. Both are existing desk controls, unchanged.

Full code rollback (only if the new code itself misbehaves; not during 08:15-08:50 or 09:10-09:35):

```bash
cd /Users/ramoscapital/ramos-quant-homebase
git revert --no-edit 1afa357                       # a new commit that undoes it; main stays linear
cp homebase/config.json.pre-gc-nfp homebase/config.json   # REQUIRED: after the desk saved, config.json holds the new
                                                   # fire_et / only_dates keys and the OLD code refuses to load them
launchctl kickstart -k gui/$(id -u)/com.ramosquant.homebase
```

That drops account additions and bookings made after the backup (re-add them). Verify with the same `/api/status`
curl: `gc_nfp` must be gone.

## 5. What to know before the open (the honest list)

- The two entry legs are not an exchange OCO: the desk cancels the sibling after it hears the first fill. In 8 of 57
  historical events the opposite side was touched within 1 s. If both fill, the desk flattens (`both_filled_emergency`)
  and you eat a loss on every eval at once. The study modeled one leg only. This is unchanged desk behaviour (nq930 works
  the same) but it matters far more at an NFP print.
- The desk sends the stops right after 08:30:00.000 (same as nq930), not before. The tick data lags the release by about
  1 s, so the study's fill timing is kinder than live. A stop placed after the price already jumped through it fills at
  market (worse) or is rejected. The $2,000 limit leaves about $500 (about 11 ticks a contract) for slippage and fees.
- Evals bought together win or lose together. About 60% pass (CI 48-73%), 0-13% bust, about 25% of the time a survived
  loss of $1,500-$1,900.
- Lucid micro-scalping rule: 24 of 35 sim wins were held 5 s or less. Expect a possible manual review. Your call.
- Buy the no-daily-loss-limit version (the study assumed it).
- 2025-26 is a spent holdout for this strategy family: the numbers are a consistency check, not a clean test.
- Not done: no live or paper dry run of the 08:30 path, and the tester twin was not re-run against the study's trade
  list. The tests drive the real timer and engine with a fake broker, not Tradovate. Option: set `"shadow": true` for
  gc_nfp in `homebase/config.json` (journals the signal, places nothing) to rehearse.
- To trade another NFP later, add its date to `only_dates` in `homebase/config.json` (strategies -> gc_nfp). Only
  2026-10-02 was verified against the BLS schedule.
