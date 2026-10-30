"""The size one booked account sends for a Lab entry (per-account settings 2): pure arithmetic, no desk."""
from homebase.desk.acctsize import BACKSTOP_MINIS, OVER_MOST, ROW_NO_SIZE, most_default, row_size

MNQ, NQ = 2.0, 20.0


def test_constants():
    assert BACKSTOP_MINIS == 10 and OVER_MOST == 1.10
    assert ROW_NO_SIZE == "No contract fits this account's risk for this stop."


def test_legacy_row_is_untouched():
    assert row_size({"account": "A", "qty": 3}, [10], MNQ, NQ, None, 0) == (3, None)
    assert row_size({"account": "A", "qty": 3}, [10], MNQ, NQ, 2, 0) == (2, None)   # own_size: min


def test_contracts_wins_over_own_size():
    assert row_size({"account": "A", "qty": 4, "size": "contracts"}, [10], MNQ, NQ, 1, 0) == (4, None)


def test_risk_rounds_and_rounds_down_when_over_10_pct():
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [25], MNQ, NQ, None, 0) == (10, None)
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 1000}, [83], NQ, NQ, None, 0) == (None, ROW_NO_SIZE)  # 1 NQ = $1,660


def test_pair_uses_wider_stop():
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [10, 25], MNQ, NQ, None, 0)[0] == 10


def test_most_and_backstop_cap():
    r = {"account": "A", "qty": 1, "size": "risk", "risk_usd": 5000}
    assert row_size(dict(r, most=20), [1], MNQ, NQ, None, 0) == (20, None)
    assert row_size(r, [0.25], MNQ, NQ, None, 0) == (100, None)          # backstop: 10 minis = 100 micros
    assert row_size(r, [0.25], NQ, NQ, None, 0) == (10, None)
    c = {"account": "A", "qty": 500, "size": "contracts"}
    assert row_size(c, [10], MNQ, NQ, None, 0) == (100, None) and row_size(dict(c, most=30), [10], MNQ, NQ, None, 0) == (30, None)


def test_cap_usd_and_unmeasurable_stop():
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [25], MNQ, NQ, None, 300) == (6, None)
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [0], MNQ, NQ, None, 0) == (None, ROW_NO_SIZE)
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [None], MNQ, NQ, None, 0) == (None, ROW_NO_SIZE)
    assert row_size({"account": "A", "qty": 1, "size": "risk", "risk_usd": 500}, [float("nan")], MNQ, NQ, None, 0) == (None, ROW_NO_SIZE)
    assert row_size({"account": "A", "qty": 2, "size": "contracts"}, [10], None, NQ, None, 0) == (None, ROW_NO_SIZE)


def test_most_default():
    assert most_default(MNQ, NQ) == 20 and most_default(NQ, NQ) == 2
