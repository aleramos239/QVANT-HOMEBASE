"""A Lab strategy's book row: {account, qty}, plus optional per-account size, risk, stop-after and most contracts.
One validator (labcfg.book_row) shapes every row."""
from __future__ import annotations

import pytest

from homebase.desk import labcfg


def test_old_row_reads_as_today():
    assert labcfg.book_row({"account": "A", "qty": 2}) == {"account": "A", "qty": 2}


def test_new_fields_kept_and_defaults_dropped():
    r = {"account": "A", "qty": 1, "size": "risk", "risk_usd": 500, "stop_after": "win", "most": 20}
    assert labcfg.book_row(r) == r
    assert labcfg.book_row({"account": "A", "qty": 3, "size": "contracts", "stop_after": "none"}) == \
        {"account": "A", "qty": 3, "size": "contracts"}


@pytest.mark.parametrize("bad", [
    {"account": "A", "qty": 1, "size": "risk"},                       # no risk_usd
    {"account": "A", "qty": 1, "size": "risk", "risk_usd": float("nan")},
    {"account": "A", "qty": 1, "size": "risk", "risk_usd": 100001},
    {"account": "A", "qty": 1, "size": "lots"},
    {"account": "A", "qty": 1, "stop_after": "loss"},
    {"account": "A", "qty": 1, "most": 0},
    {"account": "A", "qty": 1, "most": 1001},
    {"account": "A", "qty": 1, "most": True},
    {"account": "A", "qty": 0},
    {"account": "", "qty": 1},
])
def test_bad_rows_raise(bad):
    with pytest.raises(ValueError):
        labcfg.book_row(bad)


def test_shaped_skips_bad_rows_and_norm_keeps_fields():
    rows = [{"account": "A", "qty": 1, "size": "risk", "risk_usd": 400}, {"account": "B", "qty": 1, "size": "x"}]
    assert labcfg._shaped(rows) == [rows[0]]
    assert labcfg._norm(["m"], None, rows[:1])["book"] == rows[:1]


def test_a_set_row_above_the_cap_survives_the_sync_and_a_legacy_row_does_not():
    from homebase.labrun import store
    from tests.test_labcfg import L3, desk_cfg, rec, side
    cfg = desk_cfg()
    store.put(rec())
    set_row = {"account": "main", "qty": 5, "size": "contracts"}
    store.put_desk("pp_orb", side(book=[set_row, {"account": "eval1", "qty": 5}], limits=L3))
    labcfg.overlay(cfg)
    assert cfg.book["lab_pp_orb"] == [set_row]                  # the legacy row above the cap of 3 is dropped, the set row stays
    assert labcfg.overlay(cfg) == {"added": [], "removed": [], "changed": []}      # the 2 s refresh
    assert cfg.book["lab_pp_orb"] == [set_row]


def test_hold_is_yes_or_no_and_no_is_dropped():
    assert labcfg.book_row({"account": "A", "qty": 1, "hold": True}) == {"account": "A", "qty": 1, "hold": True}
    assert labcfg.book_row({"account": "A", "qty": 1, "hold": False}) == {"account": "A", "qty": 1}
    with pytest.raises(ValueError, match="Hold overnight is yes or no"):
        labcfg.book_row({"account": "A", "qty": 1, "hold": "yes"})


def test_a_row_may_name_its_contract_only_as_the_strategys_market_or_its_micro():
    nq = {"root": "NQ", "exec_root": "MNQ"}
    assert labcfg.book_row({"account": "a1", "qty": 1, "contract": "NQ"})["contract"] == "NQ"
    assert labcfg.row_ok(nq, {"account": "a1", "contract": "NQ"}) is None
    assert labcfg.row_ok(nq, {"account": "a1", "contract": "MNQ"}) is None
    assert labcfg.row_ok(nq, {"account": "a1", "contract": "ES"})          # a sentence
    with pytest.raises(ValueError):
        labcfg.book_row({"account": "a1", "qty": 1, "contract": "XYZ"})
    assert labcfg.row_symbol(nq, {"account": "a1"}) == "MNQ"
    assert labcfg.row_symbol(nq, {"account": "a1", "contract": "NQ"}) == "NQ"
    assert labcfg.row_symbol(nq, {"account": "a1", "contract": "ES"}) == "MNQ"


def test_the_cap_converts_by_point_value():
    rec = {"root": "NQ", "exec_root": "MNQ"}
    assert labcfg.row_cap(rec, {"contract": "NQ"}, 20) == 2
    assert labcfg.row_cap(rec, {"contract": "NQ"}, 5) == 0
    assert labcfg.row_cap(rec, {}, 5) == 5
    assert labcfg.row_cap({"root": "NQ"}, {"contract": "MNQ"}, 2) == 20
    assert labcfg.row_cap({"root": "NQ"}, {"contract": "ES"}, 2) == 2          # a contract it cannot trade: today's cap
