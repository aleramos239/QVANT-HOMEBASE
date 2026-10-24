"""The prop sim's fast walk (propsim._walk_fast) gives exactly what the reference walk (propsim._walk, the
rules as written) gives: the same JSON, byte for byte, for every rule file on every kind of ledger."""
from __future__ import annotations

import datetime as dt
import json
import random

import pytest

from homebase.backtest.propsim import RULES_DIR, evaluate, load_rules
from homebase.backtest.propsim import propsim as engine

MON = dt.date(2024, 3, 4)
RULE_IDS = sorted(p.stem for p in RULES_DIR.glob("*.json"))
_rng = random.Random(11)

# Each case: one list of trade nets per traded weekday, `every` weekdays apart.
CASES = {
    "dense": ([[_rng.choice((-1, 1)) * _rng.uniform(40, 900) for _ in range(_rng.randint(1, 3))]
               for _ in range(120)], 1),
    "sparse": ([[_rng.choice((-1, 1, 1)) * _rng.uniform(200, 1600)] for _ in range(31)], 13),
    "all losses": ([[-_rng.uniform(100, 700)] for _ in range(40)], 1),
    "all wins": ([[_rng.uniform(100, 1400)] for _ in range(40)], 2),
    "one day": ([[1800.0]], 1),
    "negative and zero days": ([[0.0], [-350.0], [0.0, 0.0], [520.0], [-80.0, 80.0], [-1200.0], [900.0]], 1),
    # -1,500 on two trades, a trade that dips 1,300 and wins, -1,100 then a dip of 900 (every limit is hit)
    "daily loss limit": ([[-700.0, -800.0], [400.0], [-1100.0, 300.0], [650.0], [-200.0], [1250.0]] * 6, 1),
}


def ledger(days, every, excursions):
    """The trades of `days` from MON, a traded weekday every `every` weekdays. excursions: each trade
    also carries timed entry / exit, a tick-level mae_usd and mfe_usd and a commission (open losses
    count, an intraday trail can be read); without them a ledger is bare {date, net}."""
    out, d, n = [], MON, 0
    for nets in days:
        for _ in range(every):
            d += dt.timedelta(days=1)
            while d.weekday() >= 5:
                d += dt.timedelta(days=1)
        for j, net in enumerate(nets):
            t = {"date": d.isoformat(), "net": net}
            if excursions:
                n += 1
                t.update(entry_ns=n * 10**12 + j, exit_ns=n * 10**12 + j + 1, commission=4.2,
                         mae_usd=max(0.0, -net) + (900.0 if net > 0 and n % 5 == 0 else 60.0 * (n % 4)),
                         mfe_usd=max(0.0, net) + 35.0 * (n % 3))
            out.append(t)
    return out


def reference(monkeypatch, fn, *a, **kw):
    """`fn` with every path raced through the reference walk."""
    with monkeypatch.context() as m:
        m.setattr(engine, "_walk_fast", engine._walk)
        return fn(*a, **kw)


def dump(res):
    return json.dumps(res, sort_keys=True)


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_the_fast_walk_is_the_reference_walk_for_every_rule_file(monkeypatch, rule_id):
    r = load_rules(rule_id)
    for name, (days, every) in CASES.items():
        for excursions in (True, False):
            trades = ledger(days, every, excursions)
            fast = evaluate(trades, rule_id, n_paths=120, rules=r)
            assert dump(fast) == dump(reference(monkeypatch, evaluate, trades, rule_id, n_paths=120, rules=r)), \
                (name, excursions)
            assert ("close_only" in fast) is excursions


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_the_fast_walk_is_the_reference_walk_in_the_sweep_and_degradation(monkeypatch, rule_id):
    pnls = [d[0] for d in CASES["dense"][0]] + [0.0] * 20
    kw = dict(rules=load_rules(rule_id), day_opens=[max(0.0, -p) + 75.0 for p in pnls], n_paths=60, sweep_paths=60)
    assert dump(engine.run(pnls, **kw)) == dump(reference(monkeypatch, engine.run, pnls, **kw))


def test_only_an_intraday_trail_takes_the_reference_walk(monkeypatch):
    monkeypatch.setattr(engine, "_walk", None)
    trades = ledger(*CASES["dense"], True)
    assert evaluate(trades, "lucid-pro-50k@2026-10-11", n_paths=50)["headline"]["eval_pass_p"] is not None
    with pytest.raises(TypeError):
        evaluate(trades, "apex-legacy-50k@2026-10-11b", n_paths=50)
