> **EDGE LIBRARY (2026-10-02):** the contract for edge-library families (5-tuple entries with a mandatory `rationale` and
> `complexity`, family-parameter `variants`, roots NQ / ES / GC, `FEATURES = ()` for a family without Level-2 features, the
> Globex clock, the menu, the counts-only smoke test `run_menus.py smoke`) is **`../../ENGINE.md`**. The text below is the
> L2 pilot's Stage A screen contract (4-tuple entries, `screen.py`), kept for the 14 screen families registered here.

# families/ — the Stage A screen registry (contract for family authors)

One Python module per family group in this directory (`b_imbalance.py`, `b_walls.py`, `f_flow.py`, `o_open.py`, …; a
name starting with `_` is ignored). Each module ends with

```python
FAMILIES = {                      # name -> (StrategyClass, default_inputs, both_sides, notes)
    "bimb_follow": (BimbFollow, {}, False, "B1: |z(imb10, 60 min)| >= 2 at a tf close -> follow the heavier side"),
    "bimb_fade":   (BimbFade,   {}, False, "B2: same trigger, fade"),
}
```

`import families` imports every module, checks every entry (`families.check_entry`) and fills `families.REGISTRY`.
A module that fails to import or an entry that breaks the contract is **not registered** and is listed in
`families.ERRORS`; `screen.py` refuses to run and `tests/test_families.py` fails while that dict is not empty.
`python -m families` prints the registry and the errors. You only add your own file: never edit `__init__.py`,
`l2sim.py`, `score.py`, `screen.py` or another author's module.

## The entry
| field | rule |
|---|---|
| name | lower-case letters, digits, `_`. It becomes the run key `<name>-tf<tf>` (ledger, `runs/<key>/`). One name per screened config: a second pre-registered variant (B1 with N = 3, O1 with `src="flow"`) is a second name with its own `default_inputs`. |
| StrategyClass | a subclass of `l2sim.Template`, defined in **your** module (worker processes import it by name). |
| default_inputs | overrides of the class `DEFAULTS` (`{}` = the class defaults). Never `tf` (the screen runs every tf of `SCREEN_TFS`), never a `sess` other than `"all"` (sessions are split offline), `f_depth` stays `"off"` (B6 is screened as gate G2 only). |
| both_sides | `True` if the family can have entry orders of **opposite sides working at the same time** (`_arm` with two legs = an OCO pair, or two separate opposite entries); else `False`. Non-compliant at Apex when `True`. The simulator checks you: every trade row carries `oco` / `both_sides`, the result `both_sides_sessions`; a family declared `False` that shows a both-side session fails its test. |
| notes | the SPEC id + one line (trigger). Write `REVISIT` where the SPEC says so (O1 flow-only direction). |

## The class
```python
import numpy as np
import l2sim as S

class BimbFollow(S.Template):
    """B1 bimb_follow (SPEC "Stage A screen"): ..."""
    DEFAULTS = {"k": 2.0, "n_lv": "10"}                            # = the SPEC's pre-registered defaults, nothing else
    SCHEMA = {"k": ("float", 0.5, 6.0), "n_lv": ("choice", ("3", "10"))}       # every key of DEFAULTS: choices / range
    SCREEN_TFS = ("1", "5")                                        # the tfs the screen runs (SPEC: 1 and 5; O1: its one tf)
    FEATURES = ("imb10", "imb3")                                   # EVERY column read through ctx.feat / ctx.feat_window
    # SCREEN_RUN = {"strict_limit": True}                          # only B4 wall_bounce (SPEC); nothing else is allowed here
    # session_independent = False                                  # ONLY if state must survive a session (see below)

    def fam_signal(self, ctx):                                     # at every tf-bar close inside a session, when flat
        w = ctx.feat_window("imb10" if self.p["n_lv"] == "10" else "imb3", 61)
        ...
        self._mkt(ctx, "long" if z > 0 else "short")               # market entry + the Template's stop / target
```
* **Subclass `l2sim.Template`.** The common inputs (tf, sess, dir, stop_mode, stop_val, tgt_r, trail_atr, exit_bars,
  max_tr, f_trend, f_vwap, f_depth) and their SPEC defaults (atr 1.5, tgt_r 2.0, max_tr 3, dir both, sess all) come with
  it. Override a common default only where the SPEC's family line says so (O1: stop 3 ATR, no target → `"stop_val": 3.0,
  "tgt_r": 0.0` in your `DEFAULTS`).
* **Features ONLY through `ctx.feat(name, back=k)` / `ctx.feat_window(name, n)` / `ctx.feat_n()`** (FEATURES.md). Never
  import `l2data`, never read a file, never keep a reference to `ctx._feat`. A negative `back` / `n` raises
  `LookAheadError` and aborts the whole run. Missing is NaN: test `v is None or v != v`; a NaN is "no signal".
  A column that is not in `FEATURES` is not loaded: reading it is a `KeyError`, i.e. a dropped session.
  Only deployable columns (book, flow, the price anchors, `t_utc`, `et_min`, flags); `rt_*` is refused.
* **Signals at minute boundaries only**: `fam_signal` (tf-bar close, called when flat and entries are allowed) or
  `fam_times()` + `fam_time(ctx, sec)` for clock times (O1: guard with `self.can_enter(ctx)` yourself). Entries through
  `self._mkt` (market), `self._arm` (stop entries; two legs = OCO = `both_sides=True`), `self._lim` (limit, B4);
  `struct=` gives a structure stop (with `stop_mode="struct"`), `tp_px=` an explicit target, `ttl=` tf bars to live.
* **`DEFAULTS` = the SPEC's pre-registered defaults. `SCHEMA` declares every family input.** No default, threshold or
  definition changes after the family's first screen run; a bug fix is a bug fix and is reported, a parameter change is not.
  At most 2 family parameters, 1 trigger + ≤ 2 filters (SPEC "less is more").
* **`session_independent`** is `True` on `Template`: every piece of state must be (re)built in `fam_day` / `fam_session`
  from the current session's bars and `ctx.feat_window` (the feature slice starts 18:01 ET the evening before, 360
  rows before the asia open). If your family needs state from earlier sessions that the features do not give (e.g. the
  G3-style 250-session terciles), set `session_independent = False`: it then runs on ONE process, days in order.
  A family that keeps cross-day state and leaves the flag `True` gives different trades at 1 and 8 workers: that is
  what `tests/test_families.py` catches.
* **Apex gate, for information** (nothing to code): one direction is proven from the rows the simulator stamps; a trade
  needs a stop and a target with stop ≤ 5 × target measured from the fill (no tolerance: keep `tgt_r` ≥ 0.25 if you want
  margin for tick rounding). A family without a target (O1 as pre-registered) fails `stop_5x_target` at Apex by design.

## What the screen runs for you (`screen.py`)
For every registered name × every tf of `SCREEN_TFS`: one real run (`sess=all`, all 825 in-sample sessions, 1 NQ, the
tester fill law, `features=l2sim.L2Features(FEATURES)`, + `SCREEN_RUN`) and two C2 nulls (`score.C2Features(FEATURES,
seed=1|2)`: every book / flow column of `FEATURES` shuffled, prices / anchors / flags left alone). Bundles go to
`runs/<key>/`, one row per run to `ledger.csv`. 400 screening runs in total, hard cap. You do not run the screen.

## Smoke test (bugs only — never look at P&L while developing)
```
"~/ONYX TRADING/.venv/bin/python" -m families                      # is my entry registered? any contract error?
"~/ONYX TRADING/.venv/bin/python" screen.py smoke bimb_follow --tf 5 --days 10 --workers 1
"~/ONYX TRADING/.venv/bin/python" -m pytest tests/test_families.py -k bimb_follow
```
`screen.py smoke` runs the family on 10 fixed in-sample days (early sample, a roll day and roll + 1 with the book
masked, two half days, an FOMC day, plain days), at most 2 workers, writes nothing and prints **counts only**:
sessions, sessions dropped by a strategy error (with the first error), trades, long / short, trades per session of the
day and per day, market vs resting entries, the both-side evidence against your declaration, 1-worker = 2-worker
parity, and the C2 null's trade count. No net, no exit reasons, no win rate. `ok: true` = no dropped session, parity
holds, the declaration matches the evidence, the null runs. Zero trades on the masked days is expected for a book
family; zero trades everywhere is a bug or a threshold that never fires — check the feature's distribution in
FEATURES.md, not the P&L. The pytest line runs the same family at 1 and 8 workers on 8 days and compares every trade.
Respect the compute windows (no run 09:18–09:36 ET on weekdays, Fri 2026-10-02 08:15–08:50 ET); the tools wait by
themselves.
