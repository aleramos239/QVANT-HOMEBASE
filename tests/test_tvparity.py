"""tools/tvparity: the TradingView export loader, the bars, the verdict and the OHLCV pass, on made-up CSV text.

The real-data test at the end runs only when ROOT holds exports (never in CI) and asserts category names from
tests/fixtures/tvparity_expect.json -- no TradingView value is ever in the repo."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from pathlib import Path

import pytest

from homebase.charts.bars import Bar
from homebase.charts.session import ET
from homebase.charts.studies import make
from homebase.paths import repo_root
from tests.test_charts_studies_tv import ref_ema, ref_rma, ref_tr, walk
from tools import tvparity as tp

FAR = dt.datetime(2030, 1, 1, tzinfo=ET)        # a "now" with every session complete
EXPECT = json.loads((Path(__file__).parent / "fixtures" / "tvparity_expect.json").read_text())


def ms(y, m, d, hh, mm=0):
    return int(dt.datetime(y, m, d, hh, mm, tzinfo=ET).timestamp() * 1000)


def minutes(n, start=ms(2025, 10, 8, 18, 0)):
    return [start + i * 60_000 for i in range(n)]


def text(times, extra=None, bom=False, fmt="s"):
    """CSV text in TradingView's shape: time, open, high, low, close, Volume, then `extra` {title: [cells]}."""
    extra = extra or {}
    head = ["time", "open", "high", "low", "close", "Volume", *extra]
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
        rows.append(",".join([cell, str(100 + i), str(101 + i), str(99 + i), f"{100.5 + i}", str(10 * i + 1),
                              *(extra[k][i] for k in extra)]))
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
    ts = minutes(4)
    body = text(ts).splitlines()
    body[2] = body[2].replace(",102,", ",,", 1)                      # no high: no bar
    body[1], body[3] = body[3], body[1]                             # out of order
    x = load(tmp_path, "\n".join(body) + "\n")
    assert x.t_ms == [ts[0], ts[2], ts[3]] and x.o == [100, 102, 103]


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
    assert tp.verdict(None, [1]) == "no-tv"
    assert tp.verdict([], []) == "no-data"
    c = tp.compare([1.0, 2.0, 3.5, None], [1.0, 2.5, 3.0, 1.0], decimals=[1, 1, 1, 1])
    assert (c["n"], c["n_diff"], c["first"], c["max_abs"]) == (4, 3, 1, 0.5)


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
    moved = list((tmp_path / "tvp" / "exports").glob("*/P1_1m.csv"))
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
    assert len(list((tmp_path / "tvp" / "exports").glob("*/P1_1m.csv"))) == 1


def test_a_run_where_no_csv_can_be_read_writes_no_report(tmp_path, monkeypatch):
    inbox = _inbox(tmp_path, monkeypatch)
    (inbox / "b_notes.csv").write_text("Date,Value\n1,1\n2,2\n3,3\n")
    with pytest.raises(SystemExit):
        tp.main(["run"])
    assert (inbox / "b_notes.csv").exists() and not (tmp_path / "tvp" / "reports").exists()


# ------------------------------------------------------------------ the P1 probes end to end
def walk_csv(bars, extra):
    """CSV text in TradingView's shape from Bars, plus `extra` {title: [values]}: ten decimals, None is na."""
    rows = [",".join(["time", "open", "high", "low", "close", "Volume", *extra])]
    for i, b in enumerate(bars):
        rows.append(",".join([str(b.t // 1000), *(f"{x:.10f}" for x in (b.o, b.h, b.l, b.c)), str(b.v),
                              *("" if extra[k][i] is None else f"{extra[k][i]:.10f}" for k in extra)]))
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
