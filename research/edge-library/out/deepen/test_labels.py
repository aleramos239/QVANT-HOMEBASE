"""No look-ahead proof for the STAGE 2a day labels: the label of day D does not change when D's OWN daily bar (or any later
bar) is altered; it does change when the PRIOR day's bar is altered (the test has teeth).
  "~/ONYX TRADING/.venv/bin/python" -m pytest out/deepen/test_labels.py -q     (or run the file)"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labels as L  # noqa: E402
import l2sim  # noqa: E402


def _check(root: str) -> tuple:
    rows = [r for r in l2sim.load_daily(root) if r["date"] < L.SEAL]
    dates = [r["date"] for r in rows]
    base = L.day_labels(rows, dates)
    same = changed_prior = 0
    for k in range(30, len(rows), 37):                       # 20+ probe days per root, spread over 2021-2024
        d = dates[k]
        own = copy.deepcopy(rows)
        own[k]["h"] += 5000.0                                # wreck D's own bar and every later bar
        own[k]["l"] -= 5000.0
        own[k]["c"] += 2500.0
        for j in range(k + 1, len(own)):
            own[j]["h"] += 900.0
            own[j]["c"] -= 400.0
        assert L.day_labels(own, [d])[d] == base[d], (root, d, "the label of D moved with D's own / later bars")
        same += 1
        prior = copy.deepcopy(rows)
        prior[k - 1]["h"] += 5000.0                          # the prior day IS an input: its label must be able to move
        prior[k - 1]["l"] -= 5000.0
        changed_prior += L.day_labels(prior, [d])[d] != base[d]
    assert changed_prior > 0, (root, "altering the prior day never moved a label: the test would prove nothing")
    return same, changed_prior


def test_labels_do_not_read_their_own_day():
    for root in ("NQ", "ES", "GC"):
        same, moved = _check(root)
        assert same >= 20


def test_warmup_days_have_no_label():
    rows = [r for r in l2sim.load_daily("NQ") if r["date"] < L.SEAL]
    dates = [r["date"] for r in rows]
    lab = L.day_labels(rows, dates)
    assert all(lab[d]["adx"] is None for d in dates[:28]) and lab[dates[28]]["adx"] is not None
    assert all(lab[d]["vol_hi"] is None for d in dates[:20]) and lab[dates[20]]["vol_hi"] is not None


def test_news_calendar_counts():
    nd = L.news_days()
    for y in ("2022", "2023", "2024"):
        for tag, n in (("CPI", 12), ("NFP", 12), ("FOMC", 8)):
            assert sum(1 for d, t in nd.items() if d.startswith(y) and tag in t) == n, (y, tag)
    assert max(nd) < L.SEAL


if __name__ == "__main__":
    for root in ("NQ", "ES", "GC"):
        s, m = _check(root)
        print(root, "probe days", s, "label unchanged when the day's own and later bars are altered: all;",
              "label moved when the PRIOR day was altered:", m)
    test_warmup_days_have_no_label()
    test_news_calendar_counts()
    print("ok")
