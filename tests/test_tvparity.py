"""tools/tvparity: the TradingView export loader, the bars, the verdict and the OHLCV pass, on made-up CSV text.

The real-data test at the end runs only when ROOT holds exports (never in CI) and asserts category names from
tests/fixtures/tvparity_expect.json -- no TradingView value is ever in the repo."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import re
from pathlib import Path

import pytest

from homebase.charts.bars import Bar
from homebase.charts.session import ET
from homebase.charts.studies import make
from homebase.paths import repo_root
from tests.test_charts_studies_tv import ref_ema, ref_rma, ref_tr, walk, weekdays
from tools import tvparity as tp

FAR = dt.datetime(2030, 1, 1, tzinfo=ET)        # a "now" with every session complete
EXPECT = json.loads((Path(__file__).parent / "fixtures" / "tvparity_expect.json").read_text())


def ms(y, m, d, hh, mm=0):
    return int(dt.datetime(y, m, d, hh, mm, tzinfo=ET).timestamp() * 1000)


def minutes(n, start=ms(2025, 10, 8, 18, 0)):
    return [start + i * 60_000 for i in range(n)]


def text(times, extra=None, bom=False, fmt="s", volume=True):
    """CSV text in TradingView's shape: time, open, high, low, close, Volume, then `extra` {title: [cells]}. volume=False
    leaves the Volume column out, as a chart without the Volume indicator exports."""
    extra = extra or {}
    head = ["time", "open", "high", "low", "close", *(["Volume"] if volume else []), *extra]
    rows = [",".join(head)]
    for i, t in enumerate(times):
        if fmt == "s":
            cell = str(t // 1000)
        elif fmt == "ms":
            cell = str(t)
        elif fmt == "z":
            cell = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            cell = dt.datetime.fromtimestamp(t / 1000, ET).isoformat()
        rows.append(",".join([cell, str(100 + i), str(101 + i), str(99 + i), f"{100.5 + i}",
                              *([str(10 * i + 1)] if volume else []), *(extra[k][i] for k in extra)]))
    return ("﻿" if bom else "") + "\n".join(rows) + "\n"


def load(tmp_path, body, name="x.csv", now=FAR):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return tp.load_tv_csv(p, now=now)


def bar(t, o, h, l, c, v=1, session=None):
    return Bar(t=t, session=session or tp.session_date(t).isoformat(), o=o, h=h, l=l, c=c, v=v, closed=True)


# ------------------------------------------------------------------ the loader
def test_time_formats_agree(tmp_path):
    ts = minutes(5)
    got = [load(tmp_path, text(ts, fmt=f), name=f"{f}.csv").t_ms for f in ("s", "ms", "z", "iso")]
    assert got == [ts] * 4
    assert tp._time_ms("2025-10-08T22:00:00+00:00") == tp._time_ms("2025-10-08T18:00:00-04:00") == ts[0]
    assert tp._time_ms("2025-10-08T22:00:00") == ts[0]           # naive ISO = UTC


def test_bom_na_decimals_and_duplicate_titles(tmp_path):
    ts = minutes(4)
    body = text(ts).splitlines()                   # two columns of the same title, by hand
    body[0] += ",tv|ema:3|,tv|ema:3|"
    cells = [("", "7"), ("NaN", "7.125"), ("1.25", "nan"), ("2.5", "8")]
    for i in range(4):
        body[i + 1] += "," + ",".join(cells[i])
    x = load(tmp_path, "﻿" + "\n".join(body) + "\n")
    assert [t for t, _, _ in x.cols] == ["tv|ema:3|", "tv|ema:3|"]
    assert x.cols[0][1] == [None, None, 1.25, 2.5] and x.cols[0][2] == [0, 0, 2, 1]
    assert x.cols[1][1] == [7.0, 7.125, None, 8.0] and x.cols[1][2] == [0, 3, 0, 0]
    assert x.o[0] == 100 and x.v[3] == 31 and x.tf_s == 60


def test_timeframe_from_spacing(tmp_path):
    assert load(tmp_path, text(minutes(5))).tf_s == 60
    hours = [ms(2025, 10, 8, h) for h in range(18, 24)] + [ms(2025, 10, 9, h) for h in range(0, 17)] + \
            [ms(2025, 10, 9, h) for h in range(18, 24)]                 # the 17:00 hole does not move the median
    assert load(tmp_path, text(hours)).tf_s == 3600
    days = [ms(2025, 10, d, 18) for d in (5, 6, 7, 8, 9, 12, 13, 14, 15, 16)]   # weekends gap, median is a day
    assert load(tmp_path, text(days)).tf_s == 86400


def test_daily_bars_key_to_the_session_they_open(tmp_path):
    days = [ms(2025, 10, 7, 18), ms(2025, 10, 8, 18), ms(2025, 10, 9, 18), ms(2025, 10, 12, 18)]
    x = load(tmp_path, text(days))
    assert [b.session for b in tp.tv_bars(x)] == ["2025-10-08", "2025-10-09", "2025-10-10", "2025-10-13"]
    b = tp.tv_bars(x)[0]
    p = (b.h + b.l + b.c) / 3
    assert b.span == 86_400_000 and b.pv == p * b.v and b.p2v == p * p * b.v and b.closed


def test_rows_of_an_unfinished_session_are_dropped(tmp_path):
    ts = minutes(3, ms(2025, 10, 8, 18)) + minutes(3, ms(2025, 10, 9, 18))     # sessions 10-09 and 10-10
    x = load(tmp_path, text(ts), now=dt.datetime(2025, 10, 10, 12, 0, tzinfo=ET))
    assert x.t_ms == ts[:3]
    assert len(load(tmp_path, text(ts)).t_ms) == 6


def test_rows_without_a_bar_are_dropped_and_sorted(tmp_path):
    ts = minutes(8)
    body = text(ts).splitlines()
    body[2] = body[2].replace(",102,", ",,", 1)                      # no high: no bar
    body[1], body[3] = body[3], body[1]                             # out of order
    x = load(tmp_path, "\n".join(body) + "\n")
    assert x.t_ms == [ts[0], *ts[2:]] and x.o == [100, *range(102, 108)]


def test_probe_columns_and_group(tmp_path):
    x = load(tmp_path, text(minutes(3), {"tv|probe|P1": ["1"] * 3, "tv|vol|": ["1", "2", "3"], "tv|fp|buy": ["1"] * 3,
                                        "tv|sma:2|": ["1"] * 3, "tv|macd:12:26:9|hist": ["0"] * 3, "Plot": ["0"] * 3}))
    assert x.group == "P1"
    assert [(k, f) for k, f, _, _ in tp.probe_columns(x)] == [("sma:2", ""), ("macd:12:26:9", "hist")]
    assert tp.column(x, "tv|vol|") == [1.0, 2.0, 3.0] and tp.column(x, "nope") is None


def test_loader_rejects_a_file_without_bars(tmp_path):
    with pytest.raises(ValueError):
        load(tmp_path, "time,open\n1,2\n3,4\n")
    with pytest.raises(ValueError):
        load(tmp_path, text(minutes(1)))


# ------------------------------------------------------------------ the verdict
def test_same_rules():
    assert tp.same(None, None) and not tp.same(None, 1.0) and not tp.same(1.0, None)
    assert tp.same(1.004, 1.0, 2) and not tp.same(1.006, 1.0, 2)      # half the last printed digit
    assert tp.same(1e6, 1e6 + 1e-4, 10)                                 # plus 1e-9 relative


def test_verdicts():
    assert tp.verdict([1, 2, 3], [1, 2, 3]) == "identical"
    assert tp.verdict([None, 2, 3], [None, 2, 3]) == "identical"
    assert tp.verdict([1, 2, 3], [9, 2, 3], warm=1) == "warm-up only"
    assert tp.verdict([1, 2, 3], [9, 2, 3], warm=0) == "differs"
    assert tp.verdict([1, 2, 3, 4], [1, 2, 9, 4], warm=1, restarts=(0, 2)) == "warm-up only"
    assert tp.verdict([1, 2, 3, 4], [1, 2, 9, 4], warm=1, restarts=(0,)) == "differs"
    assert tp.verdict([1, 2, 3], [1, 9, 3], skip={1}) == "identical"
    assert tp.verdict([1, 2, 3], [1, 9, 3], cold={1}) == "warm-up only"      # a cold cell is forgiven, not skipped
    assert tp.verdict([1, 2, 3], [1, 2, 9], cold={1}) == "differs"
    assert tp.verdict(None, [1]) == "no-tv"
    assert tp.verdict([], []) == "no-data"
    c = tp.compare([1.0, 2.0, 3.5, None], [1.0, 2.5, 3.0, 1.0], decimals=[1, 1, 1, 1])
    assert (c["n"], c["n_diff"], c["first"], c["max_abs"]) == (4, 3, 1, 0.5)


def test_a_differs_row_points_at_the_first_difference_after_the_warm_up_not_at_a_forgiven_cell():
    tv, hb = [1.0] * 300, [1.0] * 300
    tv[0:5] = [9.0] * 5                       # cold cells: forgiven
    cold = range(252)
    c = tp.compare(tv, hb, decimals=1, warm=0, restarts=(0,), cold=cold)
    assert (c["verdict"], c["n_diff"]) == ("warm-up only", 5)
    assert (c["first"], c["max_abs"]) == (0, 8.0)             # nothing late: the row still shows where the warm-up differed
    tv[260] = 3.0                             # a real mismatch past the cold window
    c = tp.compare(tv, hb, decimals=1, warm=0, restarts=(0,), cold=cold)
    assert (c["verdict"], c["n"], c["n_diff"]) == ("differs", 300, 6)       # the counts still cover every differing cell
    assert (c["first"], c["max_abs"]) == (260, 2.0)
    c = tp.compare([1.0, 5.0, 1.0, 7.0], [1.0, 1.0, 1.0, 2.0], warm=2, restarts=(0,))      # the same through `warm`
    assert (c["verdict"], c["first"], c["max_abs"]) == ("differs", 3, 5.0)


def test_field():
    assert tp.field(None, "") is None and tp.field(2, "") == 2.0
    assert tp.field({"k": 3, "d": None}, "k") == 3.0 and tp.field({"k": 3}, "d") is None and tp.field({"k": 3}, "") is None
    # tv:vwap has bands and no sd: the probe's sd is the first band's width; a house vwap's own sd is untouched
    assert tp.field({"vwap": 10.0, "u1": 12.5}, "sd") == 2.5 and tp.field({"vwap": 10.0, "sd": 3.0}, "sd") == 3.0
    assert tp.field({"vwap": 10.0, "u1": None}, "sd") is None


def test_htf_closes_marks_the_bar_that_closes_the_higher_bar():
    bars = [bar(t, 1, 2, 0, 1) for t in minutes(12)]
    assert tp.htf_closes(bars, 300) == {4, 9, 11}
    nxt = [bar(t, 1, 2, 0, 1) for t in minutes(3, ms(2025, 10, 9, 18))]
    assert tp.htf_closes(bars[:3] + nxt, 300) == {2, 5}               # a new session closes the open higher bar


def test_tv_key_falls_back_to_the_house_key():
    assert tp.tv_key("nonsense") == ("nonsense", False)
    k, has = tp.tv_key("sma:2")
    try:
        make("tv:sma:2")
        assert (k, has) == ("tv:sma:2", True)
    except ValueError:
        assert (k, has) == ("sma:2", False)


def test_tv_key_reorders_a_house_keltner_and_refuses_a_fractional_whole_number():
    # house keltner is (n, true-range length, mult), tv:keltner is (n, mult, band length): the probe title is the house key
    assert tp.tv_key("keltner:20:20:1.5") == ("tv:keltner:20:1.5:20", True)
    assert tp.tv_key("keltner") == ("tv:keltner:20:1.5:20", True)            # the house defaults, not TradingView's
    assert tp.tv_key("keltner:10:14:2") == ("tv:keltner:10:2:14", True)
    assert tp.tv_key("sma:50@86400") == ("tv:sma:50@86400", True) and tp.tv_key("vwap:rth") == ("vwap:rth", False)
    with pytest.raises(ValueError, match="whole number"):                     # a tv-order title: make_tv would truncate 1.5
        tp.tv_key("keltner:20:1.5:20")
    with pytest.raises(ValueError, match="whole number"):
        tp.tv_key("sma:2.5")


def test_a_tv_order_keltner_title_is_a_bad_key_row_not_a_silent_study(tmp_path):
    x = load(tmp_path, text(minutes(30), {"tv|keltner:20:1.5:20|up": [""] * 30}))
    row = next(r for r in tp.check_export(x, "NQ", hb=[])[1] if r["key"] == "keltner:20:1.5:20")
    assert row["note"].startswith("bad key") and row["math"]["verdict"] == "no-tv" and row["tv_key"] == ""


def test_root_refuses_the_repo(monkeypatch, tmp_path):
    monkeypatch.setenv(tp.ENV, str(repo_root() / "tvparity"))
    with pytest.raises(RuntimeError):
        tp.root()
    monkeypatch.setenv(tp.ENV, str(tmp_path / "tvp"))
    assert tp.root() == (tmp_path / "tvp").resolve()


# ------------------------------------------------------------------ the OHLCV pass
def test_ohlcv_pass_classes_tags_and_flags():
    ts = minutes(6)
    tv = [bar(t, 10, 12, 9, 11, v=5) for t in ts]
    hb = [bar(t, 10, 12, 9, 11, v=5) for t in ts]
    hb[1].h = 13                       # price
    hb[2].v = 6                        # volume
    hb[3].c, hb[4].o = 11.25, 10.25    # a boundary print: close then the next open, nothing else
    del hb[5]                          # missing in Homebase
    hb.append(bar(ts[-1] + 60_000, 1, 1, 1, 1))    # extra in Homebase
    o = tp.ohlcv_pass(tv, hb, 60)
    assert o["by_bar"] == ["same", "price", "volume", "boundary", "boundary", "missing"]
    assert o["classes"] == {"same": 1, "price": 1, "volume": 1, "boundary": 2, "missing": 1, "extra": 1}
    assert o["tags"] == {"holiday": [], "roll": [], "boundary": ["2025-10-09"]}
    assert o["flags"] == {"set": False, "badj": False}


def test_ohlcv_pass_daily_holiday_merge_and_set_flag():
    days = [ms(2025, 1, 15, 18), ms(2025, 1, 16, 18), ms(2025, 1, 19, 18), ms(2025, 1, 21, 18)]   # TV skips Mon 01-20's bar
    tv = [bar(t, 10, 12, 9, 11) for t in days]
    hb = [bar(t, 10, 12, 9, 11) for t in days[:3]] + [bar(ms(2025, 1, 20, 18), 10, 12, 9, 11), bar(days[3], 10, 12, 9, 11)]
    o = tp.ohlcv_pass(tv, hb, 86400)
    assert o["tags"]["holiday"] == ["2025-01-20", "2025-01-21"] and o["classes"]["extra"] == 0
    # settlement left on: every daily close off, O/H/L right
    days = [ms(2025, 3, 2, 18) + i * 86_400_000 for i in range(25)]
    tv = [bar(t, 10, 12, 9, 11) for t in days]
    hb = [bar(t, 10, 12, 9, 11.5) for t in days]
    assert tp.ohlcv_pass(tv, hb, 86400)["flags"] == {"set": True, "badj": False}
    hb = [bar(t, 12, 14, 11, 13) for t in days]                         # a constant offset: back-adjusted
    assert tp.ohlcv_pass(tv, hb, 86400)["flags"]["badj"]


# ------------------------------------------------------------------ one export
def tv_ema(xs, n):
    """Pine's ta.ema: na until n values, then an SMA seed, then alpha = 2 / (n + 1)."""
    out, a, e = [], 2.0 / (n + 1), None
    for i, x in enumerate(xs):
        if i + 1 < n:
            out.append(None)
            continue
        e = sum(xs[:n]) / n if e is None else a * x + (1 - a) * e
        out.append(e)
    return out


def cells(vals):
    return ["" if v is None else f"{v:.4f}" for v in vals]


def test_check_export_math_and_data(tmp_path):
    ts = minutes(40)
    closes = [100.5 + i for i in range(40)]
    sma2 = [None] + [(closes[i - 1] + closes[i]) / 2 for i in range(1, 40)]
    x = load(tmp_path, text(ts, {"tv|probe|P1": ["1"] * 40, "tv|vol|": [str(10 * i + 1) for i in range(40)],
                                 "tv|sma:2|": cells(sma2), "tv|ema:3|": cells(tv_ema(closes, 3)),
                                 "tv|sma:2@300|": cells(sma2), "tv|bogus:1|": cells(sma2)}))
    hb = tp.tv_bars(x)
    meta, rows = tp.check_export(x, "NQ", hb=hb)
    assert meta["group"] == "P1" and meta["bars"] == 40 and meta["classes"]["same"] == 40
    by = {(r["key"], r["field"]): r for r in rows}
    assert by[("bar", "v")]["data"]["verdict"] == "identical"
    assert by[("sma:2", "")]["math"]["verdict"] == "identical" and by[("sma:2", "")]["data"]["verdict"] == "identical"
    assert by[("ema:3", "")]["math"]["verdict"] in ("identical", "warm-up only")     # the house EMA seeds differently
    assert by[("sma:2@300", "")]["math"]["n"] == 8                                   # only the bars closing a 5m bar
    assert by[("bogus:1", "")]["note"].startswith("bad key") and by[("bogus:1", "")]["math"]["verdict"] == "no-tv"
    assert {r["key"] for r in rows} >= set(tp.NO_TV)
    assert all(r["math"]["verdict"] in tp.VERDICTS and r["data"]["verdict"] in tp.VERDICTS for r in rows)
    # a gap in Homebase's bars: the bars are skipped and the warm-up restarts after it (the first SMA after the gap
    # still holds the close before it)
    meta2, rows2 = tp.check_export(x, "NQ", hb=hb[:10] + hb[12:])
    r = next(r for r in rows2 if r["key"] == "sma:2")
    assert meta2["classes"]["missing"] == 2 and r["data"]["verdict"] == "warm-up only" and r["data"]["n"] == 38
    assert r["data"]["n_diff"] == 1 and r["data"]["first"] == "2025-10-08 18:12"
    # no Homebase bars at all
    _, rows3 = tp.check_export(x, "NQ", hb=[])
    assert next(r for r in rows3 if r["key"] == "sma:2")["data"]["verdict"] == "no-data"


def test_report_and_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(tp.ENV, str(tmp_path / "tvp"))
    monkeypatch.setattr("homebase.charts.store.TickStore.sessions", lambda self, root: [])    # no archive: math only
    inbox = tmp_path / "tvp" / "inbox"
    inbox.mkdir(parents=True)
    ts = minutes(10)
    sma2 = [None] + [(100.5 + i - 1 + 100.5 + i) / 2 for i in range(1, 10)]
    (inbox / "CME_MINI_NQ1!, 1.csv").write_text(text(ts, {"tv|probe|P1": ["1"] * 10, "tv|sma:2|": cells(sma2)}))
    assert tp.main(["run"]) == 0
    md = Path(capsys.readouterr().out.strip().splitlines()[-1])
    assert md.exists() and md.with_suffix(".json").exists() and md.parent == tmp_path / "tvp" / "reports"
    assert not list(inbox.iterdir())
    moved = list((tmp_path / "tvp" / "exports").glob("*/NQ_P1_1m.csv"))
    assert len(moved) == 1
    body = md.read_text()
    assert "| sma:2 |  | 1m | identical" in body and "| no-data |" in body and "100.5" not in body
    with pytest.raises(SystemExit):
        tp.main(["run"])


def test_the_first_bar_after_a_tagged_session_restarts_the_warm_up(tmp_path):
    days = [ms(2025, 10, 6 + i, 18) for i in range(14)]
    closes = [100.5 + i for i in range(14)]
    sma5 = [None] * 4 + [sum(closes[i - 4:i + 1]) / 5 for i in range(4, 14)]
    x = load(tmp_path, text(days, {"tv|sma:5|": cells(sma5)}))
    hb = tp.tv_bars(x)
    hb.insert(7, bar(days[6] + 12 * 3600_000, 100, 1000, 100, 1000))      # a holiday session TradingView folds into bar 6
    meta, rows = tp.check_export(x, "NQ", hb=hb)
    r = next(r for r in rows if r["key"] == "sma:5")
    assert len(meta["tags"]["holiday"]) == 1 and r["math"]["verdict"] == "identical"
    # the extra bar sits in the next four windows: warm-up after the tagged session, not four late differences
    assert r["data"]["verdict"] == "warm-up only" and r["data"]["n_diff"] == 4


def _inbox(tmp_path, monkeypatch):
    monkeypatch.setenv(tp.ENV, str(tmp_path / "tvp"))
    monkeypatch.setattr("homebase.charts.store.TickStore.sessions", lambda self, root: [])    # no archive: math only
    inbox = tmp_path / "tvp" / "inbox"
    inbox.mkdir(parents=True)
    return inbox


def test_one_unreadable_csv_is_named_and_left_in_the_inbox_and_the_rest_are_checked(tmp_path, monkeypatch, capsys):
    inbox = _inbox(tmp_path, monkeypatch)
    sma2 = [None] + [(100.5 + i - 1 + 100.5 + i) / 2 for i in range(1, 10)]
    (inbox / "a_good.csv").write_text(text(minutes(10), {"tv|probe|P1": ["1"] * 10, "tv|sma:2|": cells(sma2)}))
    (inbox / "b_notes.csv").write_text("Date,Value\n2025-10-08,1\n2025-10-09,2\n2025-10-10,3\n")
    (inbox / "c_midsession.csv").write_text(text(minutes(1)))                # fewer than two bars
    assert tp.main(["run"]) == 0
    out = capsys.readouterr().out
    md = Path(out.strip().splitlines()[-1])
    assert md.exists() and "| sma:2 |  | 1m | identical" in md.read_text()
    assert sorted(p.name for p in inbox.iterdir()) == ["b_notes.csv", "c_midsession.csv"]      # still there, to fix and re-run
    assert "b_notes.csv skipped, left in" in out and "no 'time' column" in out and "c_midsession.csv skipped, left in" in out
    assert len(list((tmp_path / "tvp" / "exports").glob("*/NQ_P1_1m.csv"))) == 1


def test_a_run_where_no_csv_can_be_read_writes_no_report(tmp_path, monkeypatch):
    inbox = _inbox(tmp_path, monkeypatch)
    (inbox / "b_notes.csv").write_text("Date,Value\n1,1\n2,2\n3,3\n")
    with pytest.raises(SystemExit):
        tp.main(["run"])
    assert (inbox / "b_notes.csv").exists() and not (tmp_path / "tvp" / "reports").exists()


# ------------------------------------------------------------------ the P1 probes end to end
def walk_csv(bars, extra, dec=10):
    """CSV text in TradingView's shape from Bars, plus `extra` {title: [values]}: ten decimals (or `dec`), None is na."""
    rows = [",".join(["time", "open", "high", "low", "close", "Volume", *extra])]
    for i, b in enumerate(bars):
        rows.append(",".join([str(b.t // 1000), *(f"{x:.{dec}f}" for x in (b.o, b.h, b.l, b.c)), str(b.v),
                              *("" if extra[k][i] is None else f"{extra[k][i]:.{dec}f}" for k in extra)]))
    return "\n".join(rows) + "\n"


def ref_vwap(bars, period):
    """ta.vwap(hlc3) and its first band's width, restarting when `period(session date)` changes."""
    out, acc = [], {}
    for b in bars:
        k = period(dt.date.fromisoformat(b.session))
        pv, p2v, v = acc.get(k, (0.0, 0.0, 0))
        p = (b.h + b.l + b.c) / 3
        pv, p2v, v = pv + p * b.v, p2v + p * p * b.v, v + b.v
        acc = {k: (pv, p2v, v)}
        vw = pv / v
        out.append((vw, math.sqrt(max(p2v / v - vw * vw, 0.0))))
    return out


def test_the_p1_keltner_supertrend_and_vwap_probes_pass_math_and_data_end_to_end(tmp_path):
    bars = walk(per=60)
    for b in bars:                                  # the file's ten decimals, so the reference sees the doubles the harness reads
        b.o, b.h, b.l, b.c = (round(x, 10) for x in (b.o, b.h, b.l, b.c))
    mid, band = ref_ema([b.c for b in bars], 20), ref_rma(ref_tr(bars, True), 20)       # Pine: ema +/- 1.5 x ta.atr(20)
    line = [None if v is None else v["line"] for v in tp.run("tv:supertrend:10:3", bars)]
    cols = {"tv|probe|P1": [1.0] * len(bars),
            "tv|keltner:20:20:1.5|mid": mid,
            "tv|keltner:20:20:1.5|up": [None if m is None or w is None else m + 1.5 * w for m, w in zip(mid, band)],
            "tv|keltner:20:20:1.5|dn": [None if m is None or w is None else m - 1.5 * w for m, w in zip(mid, band)],
            "tv|supertrend:10:3|line": line,
            # Pine's sign: -1 while the line is the lower band under the close, 1 while it is the upper band over it
            "tv|supertrend:10:3|dir": [None if ln is None else -1.0 if ln < b.c else 1.0 for ln, b in zip(line, bars)]}
    for key, period in (("vwap", lambda d: d), ("vwap:week", lambda d: d.isocalendar()[:2])):
        v = ref_vwap(bars, period)
        cols[f"tv|{key}|vwap"] = [a for a, _ in v]
        cols[f"tv|{key}|sd"] = [sd for _, sd in v]                         # P1 plots vwUp - vw
    x = load(tmp_path, walk_csv(bars, cols))
    meta, rows = tp.check_export(x, "NQ", hb=tp.tv_bars(x))
    by = {(r["key"], r["field"]): r for r in rows}
    assert len(by) >= 12 and meta["classes"] == {"same": len(bars), "extra": 0}
    for k, r in by.items():
        if k[0] in tp.NO_TV:
            continue
        assert r["math"]["verdict"] == "identical" and r["data"]["verdict"] == "identical", (k, r)
        assert r["tv_key"].startswith("tv:") and r["math"]["n"] > 0, (k, r)
    assert by[("keltner:20:20:1.5", "up")]["tv_key"] == "tv:keltner:20:1.5:20"
    # the house study says +1 for up: with the sign flipped for it, its supertrend differs only while warming up
    assert by[("supertrend:10:3", "dir")]["house"]["verdict"] in ("identical", "warm-up only")


def test_the_p1_pine_titles_are_house_keys_and_supertrend_plots_pines_own_sign():
    pine = Path(repo_root(), "tools", "pine")
    keys = {m.group(1) for f in pine.glob("*.pine") for m in re.finditer(r'plot\([^\n]*"tv\|([^|"]+)\|', f.read_text())}
    keys -= {"probe", "vol", "fp"}
    assert "keltner:20:20:1.5" in keys
    for k in keys:
        make(k)                                    # a title is a house key, in the house order
        tp.tv_key(k)                               # and reaches its tv: study without a truncated argument
    p1 = (pine / "hb_parity_p1.pine").read_text()
    assert 'plot(stDir, "tv|supertrend:10:3|dir"' in p1 and "-stDir" not in p1       # tv:supertrend keeps Pine's sign


# ------------------------------------------------------------------ review round 2: groups, volume, root, timeframe, cold sessions
def test_a_layout_b_export_is_labelled_with_every_probe_id(tmp_path):
    ids = {"tv|probe|P2": ["1"] * 3, "tv|probe|P3": ["1"] * 3, "tv|probe|P4": ["1"] * 3}
    assert load(tmp_path, text(minutes(3), ids)).group == "P2+P3+P4"
    assert load(tmp_path, text(minutes(3), {"tv|probe|P1": ["1"] * 3}), name="a.csv").group == "P1"


@pytest.mark.parametrize("gap_s", [180, 1800, 7200, 14400, 604800])
def test_an_unsupported_timeframe_is_refused_not_snapped(tmp_path, gap_s):
    ts = [ms(2025, 10, 6, 18) + i * gap_s * 1000 for i in range(8)]       # 3m, 30m, 2h, 4h, 1W
    with pytest.raises(ValueError, match="1m, 5m, 15m, 1h, 1D"):
        load(tmp_path, text(ts))


def test_a_3m_csv_is_named_and_left_in_the_inbox_and_the_rest_are_checked(tmp_path, monkeypatch, capsys):
    inbox = _inbox(tmp_path, monkeypatch)
    sma2 = [None] + [(100.5 + i - 1 + 100.5 + i) / 2 for i in range(1, 10)]
    (inbox / "a_good.csv").write_text(text(minutes(10), {"tv|probe|P1": ["1"] * 10, "tv|sma:2|": cells(sma2)}))
    (inbox / "b_three_minutes.csv").write_text(text([ms(2025, 10, 8, 18) + i * 180_000 for i in range(8)]))
    assert tp.main(["run"]) == 0
    out = capsys.readouterr().out
    assert "b_three_minutes.csv skipped, left in" in out and "1m, 5m, 15m, 1h, 1D" in out
    assert [p.name for p in inbox.iterdir()] == ["b_three_minutes.csv"]


def test_a_chart_without_the_volume_indicator_takes_its_volume_from_the_tv_vol_probe(tmp_path):
    ts = minutes(5)
    x = load(tmp_path, text(ts, {"tv|vol|": [str(10 * i + 1) for i in range(5)]}, volume=False))
    assert x.has_volume and x.v == [1.0, 11.0, 21.0, 31.0, 41.0]
    assert tp.column(x, "tv|vol|") == x.v                      # still a column: the bar-field check compares it
    y = load(tmp_path, text(ts, volume=False), name="n.csv")
    assert not y.has_volume and y.v == [0.0] * 5
    assert load(tmp_path, text(ts), name="w.csv").has_volume


def test_with_no_volume_at_all_the_volume_probes_are_skipped_with_a_reason_not_reported_as_differs(tmp_path):
    ts = minutes(60)
    bars = tp.tv_bars(load(tmp_path, text(ts), name="full.csv"))           # the same bars WITH their volume: Homebase's
    closes = [100.5 + i for i in range(60)]
    sma2 = [None] + [(closes[i - 1] + closes[i]) / 2 for i in range(1, 60)]
    vwap = [tp.field(v, "vwap") for v in tp.run("tv:vwap", bars)]
    vwma = [tp.field(v, "") for v in tp.run("vwma:3", bars)]
    x = load(tmp_path, text(ts, {"tv|probe|P2": ["1"] * 60, "tv|vwap|vwap": cells(vwap), "tv|vwma:3|": cells(vwma),
                                 "tv|sma:2|": cells(sma2)}, volume=False), name="nov.csv")
    assert not x.has_volume
    meta, rows = tp.check_export(x, "NQ", hb=bars)
    by = {(r["key"], r["field"]): r for r in rows}
    assert meta["no_volume"] and meta["classes"] == {"same": 60, "extra": 0}      # not "volume 60"
    for k in (("vwap", "vwap"), ("vwma:3", "")):
        r = by[k]
        assert r["note"].startswith("skipped") and "no volume" in r["note"], r
        assert "|" not in r["note"], r                           # a raw pipe splits the markdown report row
        assert r["math"]["verdict"] == "no-tv" and r["math"]["n"] == 0
        assert r["data"]["verdict"] == "identical"            # TradingView's column against Homebase's real volume stays valid
    assert by[("sma:2", "")]["note"] == "" and by[("sma:2", "")]["math"]["verdict"] == "identical"
    assert not any(r["field"] == "v" for r in rows)           # and no bar-volume row against a column that is not there


def _cells(line):
    """The cells of a markdown table row: a cell break is a pipe with no backslash before it."""
    return re.split(r"(?<!\\)\|", line)[1:-1]


def _report_row(tmp_path, row, key):
    meta = {"file": "x.csv", "root": "NQ", "group": "P2", "tf": "1m", "bars": 3, "sessions": 1,
            "first": "2025-10-08 18:00", "last": "2025-10-08 18:02"}
    md, js = tp.write_report([meta], [row], tmp_path, stamp="t")
    lines = md.read_text().splitlines()
    return next(l for l in lines if l.startswith("| study")), next(l for l in lines if l.startswith(f"| {key} ")), js


def test_a_pipe_in_the_note_or_the_file_name_keeps_the_report_row_at_ten_cells(tmp_path):
    row = tp._row("vwap", "vwap", "1m", None, None, "", [], note="skipped: plots tv|vol| and more")
    row["file"] = "odd|name.csv"
    head, line, js = _report_row(tmp_path, row, "vwap")
    assert len(_cells(line)) == len(_cells(head)) == 10
    assert _cells(line)[-1].strip() == "odd\\|name.csv" and _cells(line)[-2].strip() == "skipped: plots tv\\|vol\\| and more"
    assert json.loads(js.read_text())["rows"][0]["note"] == "skipped: plots tv|vol| and more"      # the json keeps the text as is


def test_the_report_shows_the_first_diff_of_the_check_that_differs_not_of_a_warm_up_beside_it(tmp_path):
    bars = [bar(t, 1, 2, 0, 1) for t in minutes(300)]
    tvc = [1.0] * 300
    cold = list(tvc)
    cold[0] = 9.0
    late = list(tvc)
    late[260] = 3.0
    math_cmp = tp.compare(tvc, cold, 1, 0, (0,), cold=range(252))          # warm-up only, 8 off at the first bar
    data_cmp = tp.compare(tvc, late, 1, 0, (0,), cold=range(252))          # differs, 2 off at bar 260
    assert math_cmp["verdict"] == "warm-up only" and data_cmp["verdict"] == "differs"
    head, line, _ = _report_row(tmp_path, tp._row("noise:0.3:rth", "up", "1m", math_cmp, data_cmp, "", bars), "noise:0.3:rth")
    assert [c.strip() for c in _cells(line)[3:7]] == ["warm-up only 1/300", "differs 1/300", "2025-10-08 22:20", "2"]
    both = tp._row("noise:0.3:rth", "up", "1m", math_cmp, math_cmp, "", bars)              # nothing differs late: where the warm-up differed
    assert [c.strip() for c in _cells(_report_row(tmp_path, both, "noise:0.3:rth")[1])[5:7]] == ["2025-10-08 18:00", "8"]


def test_ohlcv_pass_without_volume_does_not_class_every_bar_volume():
    ts = minutes(3)
    tv = [bar(t, 10, 12, 9, 11, v=0) for t in ts]
    hb = [bar(t, 10, 12, 9, 11, v=5) for t in ts]
    assert tp.ohlcv_pass(tv, hb, 60)["classes"] == {"volume": 3, "extra": 0}
    assert tp.ohlcv_pass(tv, hb, 60, volume=False)["classes"] == {"same": 3, "extra": 0}


def test_the_p2_pine_plots_volume_so_a_layout_b_export_carries_it():
    p2 = (Path(repo_root(), "tools", "pine") / "hb_parity_p2.pine").read_text()
    assert 'plot(volume, "tv|vol|", display=D)' in p2


def test_the_root_comes_from_the_file_name():
    for name, root in (("CME_MINI_ES1!, 1_ab12.csv", "ES"), ("CME_MINI_NQ1!, 5_x.csv", "NQ"), ("COMEX_GC1!, 60_y.csv", "GC"),
                       ("CME_MINI_MNQ1!, 1_z.csv", "NQ"), ("CME_MINI_NQ1!, 1_a (2).csv", "NQ"), ("export.csv", None)):
        assert tp.file_root(name) == root, name


class _Hist:
    """A History stand-in: remembers the root of every session asked for and has no bars."""
    store = None

    def __init__(self):
        self.roots = set()

    def bars(self, root, spec, d):
        self.roots.add(root)
        return []


def test_an_es_export_is_checked_against_es_and_filed_and_reported_under_its_root(tmp_path, monkeypatch):
    inbox = _inbox(tmp_path, monkeypatch)
    sma2 = [None] + [(100.5 + i - 1 + 100.5 + i) / 2 for i in range(1, 10)]
    body = text(minutes(10), {"tv|probe|P2": ["1"] * 10, "tv|sma:2|": cells(sma2)})
    (inbox / "CME_MINI_NQ1!, 1_aa.csv").write_text(body)
    (inbox / "CME_MINI_ES1!, 1_bb.csv").write_text(body)
    h = _Hist()
    md = tp.run_dir(inbox, history=h)
    assert h.roots == {"NQ", "ES"}                             # each file asked its own market's bars
    filed = sorted(p.name for p in (tmp_path / "tvp" / "exports").glob("*/*.csv"))
    assert filed == ["ES_P2_1m.csv", "NQ_P2_1m.csv"]
    report = md.read_text()
    assert "## ES P2 1m" in report and "## NQ P2 1m" in report
    assert "| ES_P2_1m.csv |" in report and "| NQ_P2_1m.csv |" in report         # the file column, last
    # an explicit root wins over the name
    for p in (tmp_path / "tvp" / "exports").glob("*/*.csv"):
        p.rename(inbox / p.name)
    h2 = _Hist()
    tp.run_dir(inbox, "GC", history=h2)
    assert h2.roots == {"GC"}


def test_an_export_with_no_market_in_its_name_is_checked_as_nq_and_says_so(tmp_path, monkeypatch, capsys):
    inbox = _inbox(tmp_path, monkeypatch)
    body = text(minutes(10), {"tv|probe|P2": ["1"] * 10})
    (inbox / "my_chart.csv").write_text(body)
    (inbox / "CME_MINI_ES1!, 1_bb.csv").write_text(body)
    tp.run_dir(inbox, history=_Hist())
    out = capsys.readouterr().out
    assert "my_chart.csv: no market in the file name" in out and "ES1!" not in out


def test_a_probe_on_a_timeframe_below_the_chart_is_skipped_not_compared(tmp_path):
    days = [ms(2025, 10, 5, 18) + i * 86_400_000 for i in range(25)]
    x = load(tmp_path, text(days, {"tv|ema:20@3600|": ["100.0"] * 25, "tv|sma:50@86400|": ["100.0"] * 25,
                                   "tv|sma:2|": ["100.0"] * 25}))
    assert x.tf_s == 86400
    by = {r["key"]: r for r in tp.check_export(x, "NQ", hb=[])[1]}
    r = by["ema:20@3600"]
    assert r["note"].startswith("skipped") and "below" in r["note"] and r["math"]["verdict"] == "no-tv" and r["math"]["n"] == 0
    assert by["sma:50@86400"]["note"] == "" and by["sma:2"]["note"] == ""       # a day on a day chart, and plain keys, run
    m = load(tmp_path, text(minutes(30), {"tv|sma:2@60|": ["100.0"] * 30}), name="m.csv")
    assert tp.check_export(m, "NQ", hb=[])[1][0]["note"] == ""                  # the same length as the chart is not below it


def test_studies_primed_from_earlier_sessions_read_warm_up_only_in_the_cold_sessions_not_differs(tmp_path):
    dates = weekdays(24)
    allb = walk(dates=dates, per=1000, seed=11)             # 18:00 -> 10:39 ET: reaches the 09:30 anchor of the noise band
    for b in allb:
        b.o, b.h, b.l, b.c = (round(x, 10) for x in (b.o, b.h, b.l, b.c))
    last = {d.isoformat() for d in dates[16:]}              # TradingView's request.security("D") saw the 16 sessions before
    idx = [i for i, b in enumerate(allb) if b.session in last]
    exp = [allb[i] for i in idx]
    cols = {"tv|probe|P2": [1.0] * len(exp)}
    for key, flds in (("levels", ("pdh", "pdl", "pdc")), ("dhl:5", ("hi", "lo")), ("noise:0.3:rth", ("up", "dn"))):
        vals = tp.run(key, allb)
        for f in flds:
            cols[f"tv|{key}|{f}"] = [tp.field(vals[i], f) for i in idx]
    per = 1000

    def check(cols):
        x = load(tmp_path, walk_csv(exp, cols), name="cold.csv")
        _, rows = tp.check_export(x, "NQ", hb=tp.tv_bars(x))
        return {(r["key"], r["field"]): r for r in rows}

    by = check(cols)
    for k in [("levels", "pdh"), ("levels", "pdl"), ("levels", "pdc"), ("dhl:5", "hi"), ("dhl:5", "lo"),
              ("noise:0.3:rth", "up"), ("noise:0.3:rth", "dn")]:
        for side in ("math", "data"):
            assert by[k][side]["verdict"] == "warm-up only", (k, side, by[k][side])
    # a late difference is still a difference: the cold sessions are forgiven, not skipped
    late = dict(cols)
    late["tv|levels|pdh"] = [v + 1.0 if v is not None and 5 * per <= i < 6 * per else v for i, v in enumerate(cols["tv|levels|pdh"])]
    late["tv|dhl:5|hi"] = [v + 1.0 if v is not None and i >= 7 * per else v for i, v in enumerate(cols["tv|dhl:5|hi"])]
    by = check(late)
    assert by[("levels", "pdh")]["math"]["verdict"] == "differs" and by[("dhl:5", "hi")]["data"]["verdict"] == "differs"
    assert by[("levels", "pdl")]["math"]["verdict"] == "warm-up only"


def test_a_running_sum_is_compared_from_its_first_bar_not_forgiven_as_warm_up(tmp_path):
    exp = walk(dates=weekdays(4), per=300, seed=5)
    for b in exp:
        b.o, b.h, b.l, b.c = (round(x, 10) for x in (b.o, b.h, b.l, b.c))
    vals = [tp.field(v, "") for v in tp.run("tv:obv", exp)]
    assert tp.warm_bars("tv:obv") >= tp.CUMULATIVE_WARM                         # the hub's repair length, longer than this export

    def check(col):
        x = load(tmp_path, walk_csv(exp, {"tv|probe|P2": [1.0] * len(exp), "tv|tv:obv|": col}), name="obv.csv")
        return next(r for r in tp.check_export(x, "NQ", hb=tp.tv_bars(x))[1] if r["key"] == "tv:obv")

    assert check(vals)["math"]["verdict"] == "identical"
    off = check([v + 5.0 if i == 700 and v is not None else v for i, v in enumerate(vals)])
    assert off["math"]["verdict"] == "differs" and off["data"]["verdict"] == "differs"      # not "warm-up only"


def test_only_the_running_sums_are_compared_from_their_first_bar():
    assert tp.CUMULATIVE == {"obv", "pvt", "adl", "nvi", "pvi"}        # derived from studies_tv2.WARM: a new running sum joins by itself


def test_a_daily_probe_on_a_short_intraday_export_reads_warm_up_only(tmp_path):
    days = weekdays(62)
    allb = walk(dates=days, per=30, seed=3)                       # 1-minute bars; TradingView's daily series saw 52 sessions first
    for b in allb:
        b.o, b.h, b.l, b.c = (round(x, 10) for x in (b.o, b.h, b.l, b.c))
    keep = {d.isoformat() for d in days[52:]}
    idx = [i for i, b in enumerate(allb) if b.session in keep]
    exp = [allb[i] for i in idx]
    key = "sma:50@86400"
    vals = tp.run(tp.tv_key(key)[0], allb)
    x = load(tmp_path, walk_csv(exp, {"tv|probe|P1": [1.0] * len(exp), f"tv|{key}|": [tp.field(vals[i], "") for i in idx]}), name="d.csv")
    r = next(r for r in tp.check_export(x, "NQ", hb=tp.tv_bars(x))[1] if r["key"] == key)
    # TradingView has a value at each of the 10 session closes, Homebase's own 10 sessions hold no 50 daily closes yet
    for side in ("math", "data"):
        assert r[side]["verdict"] == "warm-up only" and r[side]["n"] == r[side]["n_diff"] == 10, (side, r[side])


def htf_row(tmp_path, key, prior, n, bad=(), hb_drop=None, bad_bars=(), dec=10, seed=3):
    """The check_export row of the probe `key` on a 15m export of n sessions whose TradingView column was run with
    `prior` more sessions behind it (request.security reads history the export lacks), printed to `dec` decimals; the
    export sessions in `bad` (0-based) and the export bars in `bad_bars` are 5 off in that column; hb_drop(bar) -> True
    leaves a bar out of Homebase's own bars."""
    allb = long_15m(prior + n, seed=seed, dec=dec)
    sessions = sorted({b.session for b in allb})
    idx = [i for i, b in enumerate(allb) if b.session in set(sessions[prior:])]
    exp = [allb[i] for i in idx]
    off = {sessions[prior + j] for j in bad}
    vals = tp.run(tp.tv_key(key)[0], allb)
    col = [tp.field(vals[i], "") for i in idx]
    col = [v + 5.0 if v is not None and (b.session in off or j in bad_bars) else v for j, (v, b) in enumerate(zip(col, exp))]
    x = load(tmp_path, walk_csv(exp, {"tv|probe|P1": [1.0] * len(exp), f"tv|{key}|": col}, dec), name="htf.csv")
    hb = tp.tv_bars(x)
    if hb_drop:
        hb = [b for b in hb if not hb_drop(b)]
    return next(r for r in tp.check_export(x, "NQ", hb=hb)[1] if r["key"] == key)


def test_a_daily_probe_forgives_its_first_50_sessions_and_a_difference_after_them_is_one(tmp_path):
    key = "sma:50@86400"
    r = htf_row(tmp_path, key, prior=55, n=70)
    for side in ("math", "data"):       # Homebase holds no 50 daily closes until the 50th session: 49 cells off, all forgiven
        assert r[side]["verdict"] == "warm-up only" and r[side]["n"] == 70 and r[side]["n_diff"] == 49, (side, r[side])
    r = htf_row(tmp_path, key, prior=55, n=70, bad=(67, 68, 69))
    for side in ("math", "data"):
        assert r[side]["verdict"] == "differs" and r[side]["n_diff"] == 52, (side, r[side])
    assert r["math"]["max_abs"] == pytest.approx(5.0)          # the 5 that was added, not a seed gap from the cold sessions


def test_a_probe_on_a_longer_timeframe_forgives_its_own_window_of_higher_bars_whatever_the_chart(tmp_path):
    key = "sma:5@3600"                                  # 5 hourly bars: 20 chart bars at 15m, 300 at the hub's one-minute reckoning
    r = htf_row(tmp_path, key, prior=3, n=20)
    for side in ("math", "data"):
        assert r[side]["verdict"] == "warm-up only" and r[side]["n_diff"] == 4, (side, r[side])
    r = htf_row(tmp_path, key, prior=3, n=20, bad=(2,))     # session 3 is bar 128-191, inside the hub's 300 bars, past 5 hours
    for side in ("math", "data"):
        assert r[side]["verdict"] == "differs", (side, r[side])


def test_a_bar_missing_from_homebase_does_not_make_a_correct_daily_probe_differ(tmp_path):
    """A skipped bar restarts the data check: the study saw the wrong close, so the sessions that depend on it stay forgiven."""
    gone = weekdays(125)[55 + 20].isoformat()                  # export session 20: its last hour is missing, so Homebase's close is another bar's
    r = htf_row(tmp_path, "sma:50@86400", prior=55, n=70,
                hb_drop=lambda b: b.session == gone and dt.datetime.fromtimestamp(b.t / 1000, ET).hour == 9)
    assert r["data"]["verdict"] in ("identical", "warm-up only") and r["math"]["verdict"] == "warm-up only", r


def test_after_a_skipped_bar_a_daily_probe_is_cold_for_50_sessions_not_for_the_hubs_20000_chart_bars(tmp_path):
    gone = weekdays(125)[55 + 5].isoformat()                   # export session 5: its last hour is missing, so Homebase's close is another bar's
    drop = lambda b: b.session == gone and dt.datetime.fromtimestamp(b.t / 1000, ET).hour == 9
    r = htf_row(tmp_path, "sma:50@86400", prior=55, n=70, hb_drop=drop)
    # 69 cells (session 5's own close is skipped); 48 before Homebase holds 50 closes, and 49-54 still average the wrong one
    assert r["data"]["verdict"] == "warm-up only" and r["data"]["n"] == 69 and r["data"]["n_diff"] == 54, r["data"]
    r = htf_row(tmp_path, "sma:50@86400", prior=55, n=70, bad=(67, 68, 69), hb_drop=drop)
    assert r["data"]["verdict"] == "differs" and r["data"]["n_diff"] == 57, r["data"]      # sessions 55 on are Homebase's own again
    assert r["math"]["verdict"] == "differs" and r["math"]["n_diff"] == 52, r["math"]


def test_the_cold_window_of_a_longer_timeframe_probe_ends_after_its_last_higher_bar_exactly(tmp_path):
    # (key, chart bars in a higher bar, higher bars it is cold for, prior sessions, export sessions): an error in the last
    # cold higher bar is warm-up, one higher bar later it is a difference. sma:5 is a window of 5; ema:3 fades, 3 x the hub's 15
    for key, per, win, prior, n in (("sma:5@3600", 4, 5, 3, 6), ("ema:3@3600", 4, 45, 3, 6), ("sma:50@86400", 64, 50, 55, 70)):
        for h, want in ((win - 1, "warm-up only"), (win, "differs")):
            r = htf_row(tmp_path, key, prior=prior, n=n, bad_bars=(per * h + per - 1,))       # the higher bar's closing chart bar
            for side in ("math", "data"):
                assert r[side]["verdict"] == want, (key, h, side, r[side])


def test_a_skipped_bar_makes_a_probe_cold_for_its_window_of_higher_bars_from_the_higher_bar_that_holds_it(tmp_path):
    first = weekdays(9)[3].isoformat()                          # the export's first session
    drop = lambda b: b.session == first and dt.datetime.fromtimestamp(b.t / 1000, ET).strftime("%H:%M") == "04:45"
    # export bar 43 closes hour 10: Homebase's hour 10 closes on bar 42, so its sma:5 is off in hours 11-14 (the window holds hour 10)
    for at, want in ((59, "warm-up only"), (63, "differs")):       # the closing bar of hour 14 / of hour 15
        r = htf_row(tmp_path, "sma:5@3600", prior=3, n=6, hb_drop=drop, bad_bars=(at,))
        assert r["data"]["verdict"] == want, (at, r["data"])


def test_a_correct_ema_never_reads_differs_at_two_decimals_on_its_own_timeframe_or_a_longer_one(tmp_path):
    # TradingView prints two decimals: half the last digit, 0.005, is all the room a seed gap has left
    for key in ("ema:20", "ema:20@3600"):
        r = htf_row(tmp_path, key, prior=120, n=30, dec=2, seed=1)     # on this walk the hub's own 100 bars leave a tail past 0.005
        for side in ("math", "data"):
            assert r[side]["verdict"] in ("warm-up only", "identical"), (key, side, r[side])


def test_settle_bars_is_the_hubs_repair_for_a_window_and_three_times_it_for_a_study_that_fades():
    assert [tp.settle_bars(k) for k in ("sma:50", "tv:wma:20", "bb:20", "levels", "dhl:5", "noise:0.3:rth")] == [50, 20, 20, 0, 0, 0]
    for k in ("ema:20", "ema:20:hlc3", "tv:ema:20", "tv:rsi:14", "tv:atr:14", "tv:macd"):
        assert tp.settle_bars(k) == 3 * tp.warm_bars(k) > 0, k


# ------------------------------------------------------------------ review round 3: seed fade, per-field cold, empty volume, bars file
def long_15m(n, seed, per=64, dec=10):
    """n weekday sessions of 15-minute bars from 18:00 to 09:30 ET (the 09:30 bar is the noise band's anchor), NQ-sized,
    prices rounded to `dec` decimals."""
    r, px, out = random.Random(seed), 20000.0, []
    for d in weekdays(n):
        t0 = int((dt.datetime(d.year, d.month, d.day, 18, 0, tzinfo=ET) - dt.timedelta(days=1)).timestamp() * 1000)
        for i in range(per):
            o = px
            px += r.uniform(-12, 12.5)
            h, l = max(o, px) + r.uniform(0, 6), min(o, px) - r.uniform(0, 6)
            out.append(Bar(t=t0 + i * 900_000, session=d.isoformat(), o=round(o, dec), h=round(h, dec), l=round(l, dec),
                           c=round(px, dec), v=r.randint(5, 80), closed=True, span=900_000))
    return out


def test_a_long_export_stays_warm_up_only_until_the_daily_atr_seed_has_faded_then_a_difference_is_one(tmp_path):
    allb = long_15m(420, seed=2)                       # the noise band's last differing session is 164 here, past 140
    sessions = sorted({b.session for b in allb})
    idx = [i for i, b in enumerate(allb) if b.session in set(sessions[120:])]       # 300 sessions; TradingView saw 120 before
    exp = [allb[i] for i in idx]
    key = "noise:0.3:rth"
    vals = tp.run(key, allb)
    cols = {"tv|probe|P2": [1.0] * len(exp), **{f"tv|{key}|{f}": [tp.field(vals[i], f) for i in idx] for f in ("up", "dn")}}

    def check(cols):
        x = load(tmp_path, walk_csv(exp, cols), name="long.csv")
        _, rows = tp.check_export(x, "NQ", hb=tp.tv_bars(x))
        return {(r["key"], r["field"]): r for r in rows}

    by = check(cols)
    for f in ("up", "dn"):
        for side in ("math", "data"):
            assert by[(key, f)][side]["verdict"] == "warm-up only", (f, side, by[(key, f)][side])
    late = {**cols, f"tv|{key}|up": [v + 1.0 if v is not None and i >= 260 * 64 else v for i, v in enumerate(cols[f"tv|{key}|up"])]}
    assert check(late)[(key, "up")]["math"]["verdict"] == "differs"


def test_the_levels_cold_allowance_is_for_the_prior_day_fields_not_the_overnight_ones(tmp_path):
    assert [tp.cold_sessions("levels", f) for f in ("pdh", "pdl", "pdc", "onh", "onl", "rth_open")] == [2, 2, 2, 0, 0, 0]
    exp = walk(dates=weekdays(4), per=300, seed=5)
    for b in exp:
        b.o, b.h, b.l, b.c = (round(x, 10) for x in (b.o, b.h, b.l, b.c))
    vals = tp.run("levels", exp)
    cols = {"tv|probe|P2": [1.0] * len(exp), **{f"tv|levels|{f}": [tp.field(v, f) for v in vals] for f in ("pdh", "onh")}}
    cols["tv|levels|onh"] = [v + 1.0 if i < 50 else v for i, v in enumerate(cols["tv|levels|onh"])]     # wrong in session 0
    cols["tv|levels|pdh"] = [1.0 if i < 50 else v for i, v in enumerate(cols["tv|levels|pdh"])]         # TradingView knew the prior day
    x = load(tmp_path, walk_csv(exp, cols), name="lv.csv")
    by = {(r["key"], r["field"]): r for r in tp.check_export(x, "NQ", hb=tp.tv_bars(x))[1]}
    assert by[("levels", "onh")]["math"]["verdict"] == "differs"          # it reads the chart's own bars: no history to excuse it
    assert by[("levels", "pdh")]["math"]["verdict"] == "warm-up only"


def test_an_empty_or_all_zero_volume_column_is_no_volume_not_a_volume_of_zero(tmp_path):
    for name, cell in (("e.csv", ""), ("z.csv", "0")):
        x = load(tmp_path, text(minutes(5), {"tv|vol|": [cell] * 5}, volume=False), name=name)
        assert not x.has_volume and x.v == [0.0] * 5, name


def test_an_empty_or_all_zero_volume_column_leaves_no_bar_volume_row_to_differ(tmp_path):
    ts = minutes(30)
    hb = tp.tv_bars(load(tmp_path, text(ts)))                       # Homebase's side holds a real volume
    for name, cell in (("e.csv", ""), ("z.csv", "0")):
        x = load(tmp_path, text(ts, {"tv|probe|P2": ["1"] * 30, "tv|vol|": [cell] * 30}, volume=False), name=name)
        meta, rows = tp.check_export(x, "NQ", hb=hb)
        assert meta["no_volume"] and not [r for r in rows if r["key"] == "bar" and r["field"] == "v"], name
    x = load(tmp_path, text(ts, {"tv|probe|P2": ["1"] * 30, "tv|vol|": [str(10 * i + 1) for i in range(30)]}, volume=False))
    _, rows = tp.check_export(x, "NQ", hb=hb)                       # a real tv|vol| is still compared
    assert next(r for r in rows if r["key"] == "bar" and r["field"] == "v")["data"]["verdict"] == "identical"


def test_uses_volume_sees_nvi_and_pvi_which_a_constant_volume_leaves_flat(tmp_path):
    bars = tp.tv_bars(load(tmp_path, text(minutes(30))))
    for k in ("tv:nvi", "tv:pvi", "tv:obv", "tv:vwap", "vwma:3"):
        assert tp.uses_volume(k, bars, 0.25), k
    for k in ("sma:3", "atr:14", "tv:ema:3"):
        assert not tp.uses_volume(k, bars, 0.25), k


def test_a_filed_export_is_read_for_its_root_when_the_folder_is_run_again(tmp_path, monkeypatch):
    for name, root in (("ES_P2_1m.csv", "ES"), ("NQ_P2+P3+P4_5m.csv", "NQ"), ("GC_P1_1D_2.csv", "GC"), ("6E_P1_15m.csv", "6E"),
                       ("CME_1_1m.csv", None), ("ES_P2_2m.csv", None)):
        assert tp.file_root(name) == root, name
    inbox = _inbox(tmp_path, monkeypatch)
    (inbox / "CME_MINI_ES1!, 1_bb.csv").write_text(text(minutes(10), {"tv|probe|P2": ["1"] * 10}))
    tp.run_dir(inbox, history=_Hist())
    for p in (tmp_path / "tvp" / "exports").glob("*/*.csv"):
        p.rename(inbox / p.name)                                    # the filed name: ES_P2_1m.csv
    h = _Hist()
    tp.run_dir(inbox, history=h)
    assert h.roots == {"ES"}


class _OwnBars:
    """A History stand-in whose Homebase bars are the given ones."""
    store = None

    def __init__(self, bars):
        self.own = bars

    def bars(self, root, spec, d):
        return [b for b in self.own if b.session == d.isoformat()]


def test_run_writes_homebase_bars_next_to_the_filed_export_for_parity_mjs(tmp_path, monkeypatch):
    inbox = _inbox(tmp_path, monkeypatch)
    body = text(minutes(10), {"tv|probe|P1": ["1"] * 10})
    (inbox / "a.csv").write_text(body)
    own = tp.tv_bars(load(tmp_path, body, name="own.csv"))
    tp.run_dir(inbox, history=_OwnBars(own))
    p = next((tmp_path / "tvp" / "exports").glob("*/NQ_P1_1m.bars.json"))
    got = json.loads(p.read_text())
    assert [g["ms"] for g in got] == [b.t for b in own] and set(got[0]) == {"ms", "o", "h", "l", "c", "v"}
    assert [(g["o"], g["c"], g["v"]) for g in got] == [(b.o, b.c, b.v) for b in own]


# ------------------------------------------------------------------ the owner's exports (never in CI)
def _exports():
    try:
        return sorted(tp.root().glob("exports/*/*.csv"))
    except RuntimeError:
        return []


@pytest.mark.skipif(not _exports(), reason="needs TradingView exports under ROOT/exports")
def test_real_exports_math_matches_the_expected_categories():
    seen = {}
    for p in _exports():
        x = tp.load_tv_csv(p)
        _, rows = tp.check_export(x, "NQ", hb=[])
        for r in rows:
            if r["key"] in EXPECT and r["tv_key"].startswith("tv:"):
                seen[(r["key"], r["field"], r["tf"])] = r["math"]["verdict"]
                assert r["math"]["verdict"] == EXPECT[r["key"]]["math"], (p.name, r["key"], r["field"], r["math"])
    assert seen, "no probe column of an expected study found in the exports"
