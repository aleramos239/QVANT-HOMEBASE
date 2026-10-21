"""The 3:1 block months (blueprint/wfmonths.py) and the engine's in-sample / out-of-sample switches (ALLOW_WF_IS / ALLOW_WF_OOS).
Every calendar here is synthetic (weekdays): no tape is opened."""
import datetime as dt

import pytest

import l2ref
import l2sim as S
from blueprint import wfmonths as WM


def _weekdays(a: str, b: str) -> list:
    d, end, out = dt.date.fromisoformat(a), dt.date.fromisoformat(b), []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


@pytest.fixture(autouse=True)
def _fresh():
    WM._sets.cache_clear()                                        # the engine's memo of the month sets: never a synthetic one left over
    yield
    WM._sets.cache_clear()


def _cal(monkeypatch, cal, stops=None):
    monkeypatch.setattr(WM, "_sessions", lambda root, today: (tuple(cal), stops))
    WM._sets.cache_clear()


@pytest.fixture
def nq(monkeypatch):
    cal = _weekdays("2021-09-22", "2026-09-30")
    _cal(monkeypatch, cal)
    return cal


def test_blocks_layout(nq):
    b = WM.blocks("NQ", last="2026-09")
    assert b[:3] == [{"i": 0, "is": ["2021-10", "2021-11", "2021-12"], "oos": "2022-01"},
                     {"i": 1, "is": ["2022-02", "2022-03", "2022-04"], "oos": "2022-05"},
                     {"i": 2, "is": ["2022-06", "2022-07", "2022-08"], "oos": "2022-09"}]
    assert len(b) == 15 and sum(len(x["is"]) for x in b) == 45 and b[-1] == {"i": 14, "is": ["2026-06", "2026-07", "2026-08"], "oos": "2026-09"}
    assert WM.blocks("NQ") == b                                   # the calendar's own last whole month
    assert WM.is_days("NQ")[0] == "2021-10-01" and not any(d[:7] in ("2021-09", "2022-01") for d in WM.is_days("NQ"))
    assert WM.oos_days("NQ", "2022-01") == _weekdays("2022-01-01", "2022-01-31")
    with pytest.raises(ValueError, match="not a test month"):
        WM.oos_days("NQ", "2021-11")                              # an in-sample month is no test month


def test_blocks_drop_a_trailing_part_block(nq):
    b = WM.blocks("NQ", last="2026-07")
    assert b[-1]["oos"] == "2026-05"
    assert not any(m in ("2026-06", "2026-07") for x in b for m in x["is"] + [x["oos"]])


def test_blocks_start_at_first_whole_month_of_the_market(monkeypatch):
    _cal(monkeypatch, _weekdays("2021-11-03", "2026-09-30"))
    assert WM.blocks("ES")[0] == {"i": 0, "is": ["2021-12", "2022-01", "2022-02"], "oos": "2022-03"}
    _cal(monkeypatch, _weekdays("2024-01-02", "2026-09-30"))      # Jan 1 a holiday: still whole
    assert WM.blocks("GC")[0]["is"][0] == "2024-01"


def test_a_month_the_complete_sessions_do_not_run_past_is_in_no_block(monkeypatch):
    _cal(monkeypatch, _weekdays("2021-09-22", "2026-09-22"), stops="2026-09-23")      # NQ today: Sep 2026 stops on the 22nd
    b = WM.blocks("NQ")
    assert len(b) == 14 and b[-1]["oos"] == "2026-05"             # Jun-Aug 2026: a trailing part-block, in no block
    assert not any(d[:7] == "2026-09" for d in WM.calendar("NQ") + WM.is_days("NQ"))
    with pytest.raises(ValueError, match="not a test month"):
        WM.oos_days("NQ", "2026-09")
    for d in ("2026-09-15", "2026-09-28"):                        # the switch and oos_days agree: the whole month stays shut
        with pytest.raises(S.HoldoutSealed, match="not in an out-of-sample month"):
            S.check_holdout(d, S.ALLOW_WF_OOS)


def test_wf_is_switch_refuses_an_oos_day(nq):
    S.check_holdout("2021-11-10", S.ALLOW_WF_IS)
    S.check_holdout("2025-08-04", S.ALLOW_WF_IS, "NQ")            # an in-sample month after the build days opens too
    for d in ("2022-01-05", "2021-09-23", "2026-10-01"):           # a test month, the partial first month, the month under way
        with pytest.raises(S.HoldoutSealed, match="not in an in-sample month"):
            S.check_holdout(d, S.ALLOW_WF_IS)
    with pytest.raises(S.HoldoutSealed, match="no range by name"):
        S.period(S.ALLOW_WF_IS)
    with pytest.raises(S.HoldoutSealed, match="names its dates"):
        S.run(l2ref.Donchian, {}, workers=1, allow_holdout=S.ALLOW_WF_IS)          # no dates named
    with pytest.raises(S.HoldoutSealed, match="not in an in-sample month"):
        S.run(l2ref.Donchian, {}, workers=1, days=["2021-11-10", "2022-01-05"], allow_holdout=S.ALLOW_WF_IS)
    assert S.allow_level(S.ALLOW_WF_IS, allow_exam=True) == S.ALLOW_WF_IS          # never widened


def test_wf_oos_switch_refuses_an_is_day(nq):
    S.check_holdout("2022-01-05", S.ALLOW_WF_OOS)
    for d in ("2021-11-10", "2025-08-04", "2026-10-01"):
        with pytest.raises(S.HoldoutSealed, match="not in an out-of-sample month"):
            S.check_holdout(d, S.ALLOW_WF_OOS)
    with pytest.raises(S.HoldoutSealed, match="no range by name"):
        S.period(S.ALLOW_WF_OOS)
    with pytest.raises(S.HoldoutSealed, match="ONE month"):        # ONE test month a call, never two
        S.run(l2ref.Donchian, {}, workers=1, days=["2022-01-05", "2022-05-04"], allow_holdout=S.ALLOW_WF_OOS)
