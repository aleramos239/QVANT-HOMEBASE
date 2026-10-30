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
