"""The desk's page and readiness know the "levels" strategies and the level timer."""
from __future__ import annotations

from tests.levels_util import levels_cfg
from tests.test_server import client  # noqa: F401  (the desk fixture)


def levels_on(client):                                   # noqa: F811
    cfg = client.app.state.cfg
    cfg.strategies["lv_atr_take"] = levels_cfg("lv_atr_take", enabled=True)
    cfg.book["lv_atr_take"] = [{"account": "main", "qty": 4}]
    cfg.strategies["lv_atr_tiers"] = levels_cfg("lv_atr_tiers")            # off, unbooked
    return cfg


def test_status_carries_the_level_timer_and_the_levels_cfg(client):          # noqa: F811
    levels_on(client)
    d = client.get("/api/status").json()
    assert d["levels"]["date"] and isinstance(d["levels"]["strategies"], dict)
    c = d["strategies"]["lv_atr_take"]["cfg"]
    assert (c["kind"], c["shape"], c["fire_et"], c["day_take"], c["target_take"], c["ack_open_loss"]) == \
        ("levels", "atr_straddle", "09:30:00", 1500.0, True, False)
    assert c["size_tiers"] == [] and d["strategies"]["lv_atr_tiers"]["cfg"]["size_tiers"] == [[0, 2], [1000, 3], [2000, 4]]
    assert d["strategies"]["lv_atr_take"]["cfg"]["enabled"] is True


def test_readiness_does_not_demand_a_9_30_signal_from_a_levels_strategy(client):   # noqa: F811
    """After its window an idle straddle reads "no signal arrived"; a levels strategy answers to its own timer
    (journaled fire / skip / miss), never to the 9:30 pipe check."""
    levels_on(client)
    r = client.get("/api/status").json()["readiness"]
    assert not [c for c in r["checks"] if c["label"] == "lv_atr_take" and "signal" in c["detail"]]


def test_the_engine_reads_the_desks_balance_record(client):          # noqa: F811
    assert client.app.state.engine.balance_history is not None
