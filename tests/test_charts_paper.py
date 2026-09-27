"""The forward PAPER runner (homebase/charts/paper.py): parity with the backtester on real
archived GC event days, event-day detection, no trading imports, the 1-per-second throttle,
the window, persistence across a restart, and the replay-only --paper-day flag.

Fixtures: tests/fixtures/gc_paper_<date>.csv.gz, trimmed 08:29:30-09:56 ET from the tick
archive by tests/fixtures/make_gc_paper_fixture.py (research window only). No test reads
~/futures_ticks, opens a network connection or starts a service."""
from __future__ import annotations

import ast
from array import array
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homebase.backtest.engine import Costs, run_session, to_tick
from homebase.backtest.tape import Tape, et_ns, read_archive_csv, stable_sorted
from homebase.charts import __main__ as main_mod
from homebase.charts import paper as paper_mod
from homebase.charts.calendar import Calendar, parse, week_start
from homebase.charts.paper import (FORBIDDEN_IMPORTS, RUN_EVERY_S, PaperRunner, detect_event,
                                   describe, stats)
from homebase.charts.server import create_app
from homebase.strategies.gc_nfpcpi import GCNfpCpi
from tests.test_charts_desk_server import QuietFeed
from tests.test_charts_server import next_of

FIX = Path(__file__).resolve().parent / "fixtures"
EXPECTED = json.loads((FIX / "gc_paper_expected.json").read_text())
NFP_DAY, CPI_DAY = dt.date(2024, 9, 6), dt.date(2024, 11, 13)      # in the CSV, research window
WS_HOST = {"host": "127.0.0.1:8852"}


def ms(d: dt.date, hhmmss: str) -> int:
    return et_ns(d, hhmmss) // 1_000_000


def fixture(d: dt.date):
    return stable_sorted(*read_archive_csv(FIX / f"gc_paper_{d.isoformat()}.csv.gz"))


def fixture_rows(d: dt.date, ns: bool = True) -> list[dict]:
    ts, px, sz = fixture(d)
    return [{"ts_ms": t // 1_000_000, "price": p, "size": s, **({"ts_ns": t} if ns else {})}
            for t, p, s in zip(ts, px, sz)]


class Wall:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def drive(runner: PaperRunner, rows: list[dict], d: dt.date, frm: str, to: str, step_ms: int = 250,
          wall: Wall | None = None, states: list | None = None) -> int:
    """Play rows through the runner on a simulated clock [frm, to], the service's way:
    ticks as they 'arrive', then due()/step() every step_ms (wall advances with it)."""
    now, end, i = ms(d, frm), ms(d, to), 0
    wall = wall or runner.wall
    while now <= end:
        j = i
        while j < len(rows) and _ns(rows[j]) <= now * 1_000_000:
            j += 1
        if j > i:
            runner.on_ticks(rows[i:j])
            i = j
        if runner.due(now):
            msg = runner.step(now)
            if msg is not None and states is not None and (not states or states[-1] != msg["state"]):
                states.append(msg["state"])
        if now >= end:
            break
        dt_ms = step_ms if now < ms(d, "08:31:00") else max(step_ms, 30_000)    # fine where it trades
        dt_ms = min(dt_ms, end - now)                                             # always ends ON `to`
        now += dt_ms
        wall.t += max(dt_ms, step_ms) / 1000
    return i


def _ns(r: dict) -> int:
    return int(r["ts_ns"]) if r.get("ts_ns") not in (None, "") else int(r["ts_ms"]) * 1_000_000


def runner(tmp_path, **kw) -> PaperRunner:
    kw.setdefault("wall", Wall())
    kw.setdefault("log", lambda m: None)
    return PaperRunner(tmp_path / "paper", None, **kw)


# ---------------------------------------------------------------- parity

@pytest.mark.parametrize("d", [NFP_DAY, CPI_DAY])
def test_parity_with_run_session_on_a_real_archived_event_day(tmp_path, d):
    ts, px, sz = fixture(d)
    direct = run_session(GCNfpCpi(), Tape("GC", d, "", ts, px, sz, {}), Costs())
    assert len(direct.trades) == 1
    # the trimmed fixture trades exactly like the whole archived session did
    assert [t.to_dict() for t in direct.trades] == EXPECTED[d.isoformat()]["trades"]

    r, states = runner(tmp_path), []
    drive(r, fixture_rows(d), d, "08:29:40", "09:56:03", states=states)
    assert r.final and r.rule == "csv" and r.last_result is not None
    assert [t.to_dict() for t in r.last_result.trades] == [t.to_dict() for t in direct.trades]
    t, anchor = direct.trades[0], EXPECTED[d.isoformat()]["anchor"]
    cur = r.current
    assert cur["state"] == "done" and cur["status"] == "traded" and cur["anchor"] == anchor
    assert cur["legs"] == [
        {"side": "long", "price": to_tick(anchor + 2, 0.1), "sl": to_tick(anchor - 1, 0.1),
         "tp": to_tick(anchor + 8, 0.1)},
        {"side": "short", "price": to_tick(anchor - 2, 0.1), "sl": to_tick(anchor + 1, 0.1),
         "tp": to_tick(anchor - 8, 0.1)}]
    assert t.order_price in [g["price"] for g in cur["legs"] if g["side"] == t.side]
    assert cur["entry"] == {"side": t.side, "price": t.entry_price, "ts": t.entry_ns // 1_000_000,
                            "sl": t.sl, "tp": t.tp}
    assert cur["exit"] == {"price": t.exit_price, "ts": t.exit_ns // 1_000_000, "kind": t.exit_reason}
    assert cur["pnl_usd"] == t.net
    assert states[0] == "waiting" and states[-1] == "done"
    rec = [json.loads(x) for x in (tmp_path / "paper" / "runs.jsonl").read_text().splitlines()]
    assert len(rec) == 1 and rec[0]["date"] == d.isoformat() and rec[0]["event"] == ("NFP" if d == NFP_DAY else "CPI")
    assert rec[0]["pnl_usd"] == t.net and rec[0]["entry"] == cur["entry"] and rec[0]["exit"] == cur["exit"]


def test_the_cpi_day_goes_waiting_armed_in_trade_done(tmp_path):
    r, states = runner(tmp_path), []
    drive(r, fixture_rows(CPI_DAY), CPI_DAY, "08:29:40", "09:56:03", step_ms=100, states=states)
    assert states == ["waiting", "armed", "in_trade", "done"]


def test_parity_holds_at_the_live_feeds_millisecond_precision(tmp_path):
    ts, px, sz = fixture(CPI_DAY)
    ms_ts = array("q", (t // 1_000_000 * 1_000_000 for t in ts))
    direct = run_session(GCNfpCpi(), Tape("GC", CPI_DAY, "", ms_ts, px, sz, {}), Costs())
    r = runner(tmp_path)
    drive(r, fixture_rows(CPI_DAY, ns=False), CPI_DAY, "08:29:40", "09:56:03", step_ms=1000)
    assert [t.to_dict() for t in r.last_result.trades] == [t.to_dict() for t in direct.trades]


def test_the_anchor_is_carried_from_before_the_buffer_window(tmp_path):
    """No print in the last 10 s before 08:30: the anchor still equals the full tape's."""
    d = CPI_DAY
    rows = [r for r in fixture_rows(d) if not ms(d, "08:29:48") <= r["ts_ms"] < ms(d, "08:30:00")]
    rows = [{**x, "ts_ms": ms(d, "08:25:00"), "ts_ns": ms(d, "08:25:00") * 1_000_000}
            if x["ts_ms"] < ms(d, "08:29:48") else x for x in rows]      # earlier prints -> 08:25
    tape = Tape("GC", d, "", *stable_sorted(array("q", [_ns(x) for x in rows]), array("d", [x["price"] for x in rows]),
                                             array("i", [x["size"] for x in rows])), {})
    direct = run_session(GCNfpCpi(), tape, Costs())
    r = runner(tmp_path)
    drive(r, rows, d, "08:24:00", "09:56:03", step_ms=500)
    assert r.current["anchor"] == direct.hlines[0]["price"]
    assert [t.to_dict() for t in r.last_result.trades] == [t.to_dict() for t in direct.trades]


# ---------------------------------------------------------------- event days

def _ff(title, day, hhmm="08:30", country="USD", impact="High"):
    when = dt.datetime.combine(dt.date.fromisoformat(day), dt.time.fromisoformat(hhmm), paper_mod.ET)
    return {"title": title, "country": country, "impact": impact, "forecast": "", "previous": "",
            "date": when.isoformat()}                          # the feed's ISO with its ET offset


def _cal(tmp_path, *events) -> Calendar:
    folder = tmp_path / "calendar"
    folder.mkdir(parents=True, exist_ok=True)
    evs = parse(list(events))
    by_week: dict[str, list] = {}
    for e in evs:
        by_week.setdefault(week_start(e["t_ms"]).isoformat(), []).append(e)
    for wk, es in by_week.items():
        (folder / f"{wk}.json").write_text(json.dumps(es))
    return Calendar(folder)


def test_event_day_detection_from_the_forexfactory_calendar(tmp_path):
    cal = _cal(tmp_path,
               _ff("Non-Farm Employment Change", "2026-10-02"), _ff("Unemployment Rate", "2026-10-02"),
               _ff("Unemployment Claims", "2026-10-01"), _ff("ISM Manufacturing PMI", "2026-10-01", "10:00"),
               _ff("CPI m/m", "2026-10-14"), _ff("Core CPI m/m", "2026-10-14"), _ff("CPI y/y", "2026-10-14"),
               _ff("CPI m/m", "2026-10-15", country="EUR"), _ff("CPI y/y", "2026-10-16", impact="Medium"),
               _ff("Core CPI m/m", "2026-10-13", "10:00"))
    assert detect_event(dt.date(2026, 10, 2), cal) == (frozenset({"NFP"}), "ff")
    assert detect_event(dt.date(2026, 10, 14), cal) == (frozenset({"CPI"}), "ff")
    assert detect_event(dt.date(2026, 10, 1), cal) == (frozenset(), "ff")     # claims only: not an event
    for d in (13, 15, 16):                                                  # 10:00 / EUR / Medium
        assert detect_event(dt.date(2026, 10, d), cal) == (frozenset(), "ff")
    both = _cal(tmp_path / "b", _ff("Non-Farm Employment Change", "2026-11-06"), _ff("CPI m/m", "2026-11-06"))
    assert detect_event(dt.date(2026, 11, 6), both) == (frozenset({"NFP", "CPI"}), "ff")
    assert paper_mod.label({"NFP", "CPI"}) == "NFP+CPI"


def test_the_static_csv_only_decides_dates_it_contains_when_the_calendar_has_no_week(tmp_path):
    empty = _cal(tmp_path)
    assert detect_event(NFP_DAY, empty) == (frozenset({"NFP"}), "csv")
    assert detect_event(dt.date(2024, 5, 15), None) == (frozenset({"CPI"}), "csv")    # CPI+EMPIRE+RETAIL
    assert detect_event(dt.date(2024, 9, 9), None) == (frozenset(), "none")           # not in the CSV
    assert detect_event(dt.date(2027, 1, 8), None) == (frozenset(), "none")           # past its coverage
    # the calendar holds the week: it decides, even against the CSV (e.g. a rescheduled release)
    cal = _cal(tmp_path / "w", _ff("Unemployment Rate", "2024-09-06"))
    assert detect_event(NFP_DAY, cal) == (frozenset(), "ff")


def test_a_non_event_day_does_no_work(tmp_path):
    d = dt.date(2024, 9, 9)
    r = runner(tmp_path)
    rows = [{**x, "ts_ms": x["ts_ms"] + 3 * 86_400_000, "ts_ns": x["ts_ns"] + 3 * 86_400 * 10 ** 9}
            for x in fixture_rows(NFP_DAY)]
    drive(r, rows, d, "08:29:00", "09:57:00", step_ms=1000)
    assert r.runs_done == 0 and r.current is None and len(r._ts) == 0
    assert not (tmp_path / "paper" / "runs.jsonl").exists()


def test_the_replay_force_counts_a_date_only_when_forced(tmp_path):
    d = dt.date(2024, 9, 9)
    assert detect_event(d, None, force_day=d) == (frozenset({"NFP", "CPI"}), "forced")
    assert detect_event(NFP_DAY, None, force_day=NFP_DAY) == (frozenset({"NFP"}), "forced")
    assert detect_event(d, None, force_day=NFP_DAY) == (frozenset(), "none")


# ---------------------------------------------------------------- no trading imports

def test_paper_py_imports_no_broker_desk_or_trading_module():
    src = Path(paper_mod.__file__).read_text()
    names = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = ["homebase", "charts"][:max(0, 2 - node.level + 1)] if node.level else []
            mod = ".".join(base + ([node.module] if node.module else []))
            names += [mod] + [f"{mod}.{a.name}" for a in node.names]
    bad = [n for n in names for f in FORBIDDEN_IMPORTS if n == f or n.startswith(f + ".")]
    assert bad == []
    for word in ("DeskLink", "tradovate", "Fanout", "place_order"):
        assert word not in src.split('"""', 2)[2]             # outside the module docstring
    # and nothing on the order path arrives transitively either (fresh interpreter)
    out = subprocess.run([sys.executable, "-c",
                          "import sys, homebase.charts.paper as p; "
                          "print([m for m in sys.modules for f in ('homebase.trading', 'homebase.desk_api', "
                          "'homebase.engine', 'homebase.timer', 'homebase.charts.desk', 'homebase.broker.tradovate', "
                          "'homebase.risk', 'homebase.server') if m == f])"],
                         capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


# ---------------------------------------------------------------- throttle + window

def test_at_most_one_run_a_second(tmp_path):
    wall = Wall()
    calls = []

    def counting(*a, **kw):
        calls.append(wall.t)
        return run_session(*a, **kw)

    r = runner(tmp_path, wall=wall, run=counting)
    drive(r, fixture_rows(CPI_DAY), CPI_DAY, "08:29:40", "08:31:00", step_ms=50, wall=wall)
    assert len(calls) >= 50
    assert all(b - a >= RUN_EVERY_S for a, b in zip(calls, calls[1:]))
    assert len(calls) <= 80 / RUN_EVERY_S + 1                # 80 s of clock: never more than 1/s


def test_no_work_outside_the_window(tmp_path):
    d = CPI_DAY
    r = runner(tmp_path)
    early = [{"ts_ms": ms(d, "08:00:00"), "ts_ns": ms(d, "08:00:00") * 10 ** 6, "price": 2600.0, "size": 1}]
    late = [{"ts_ms": ms(d, "10:30:00"), "ts_ns": ms(d, "10:30:00") * 10 ** 6, "price": 2600.0, "size": 1}]
    assert r.due(ms(d, "08:00:00")) is False                  # an event day, before 08:29:50
    r.on_ticks(early)
    assert r.due(ms(d, "08:29:49")) is False
    assert len(r._ts) == 0 and r._carry is None and r.runs_done == 0
    # after the window, a process that never saw it does nothing
    r2 = runner(tmp_path / "late")
    assert r2.due(ms(d, "10:30:00")) is False
    r2.on_ticks(late)
    assert len(r2._ts) == 0 and r2.runs_done == 0 and r2.current is None
    # inside the window only the window's prints are buffered (+ one carried anchor print)
    r3 = runner(tmp_path / "in")
    drive(r3, fixture_rows(d) + late, d, "08:29:40", "08:35:00", step_ms=1000)
    assert r3._ts[0] >= et_ns(d, "08:29:50") and r3._ts[-1] < et_ns(d, "09:56")
    assert et_ns(d, "08:20") <= r3._carry[0] < et_ns(d, "08:29:50")
    assert r3.runs_done > 0


# ---------------------------------------------------------------- persistence

def test_a_restart_mid_window_rebuilds_the_state_and_runs_jsonl_round_trips(tmp_path):
    d, rows = CPI_DAY, fixture_rows(CPI_DAY)
    a = runner(tmp_path)
    n = drive(a, rows, d, "08:29:40", "08:30:10")
    a.wall.t += 1
    if a.due(ms(d, "08:30:10")):
        a.step(ms(d, "08:30:10"))                             # a's state covers every tick it was fed
    assert a.current["state"] == "in_trade" and "open_pnl_usd" in a.current
    before = a.current
    # the process dies; the new one is seeded from the recording (the chart service's reseed)
    b = runner(tmp_path)
    now = ms(d, "08:30:10")
    b.seed(now, ((_ns(x), x["price"], x["size"]) for x in rows[:n]))
    assert b.due(now) and b.step(now) == before
    drive(b, rows[n:], d, "08:30:10", "09:56:03")
    assert b.current["state"] == "done" and b.current["status"] == "traded"
    # a third process after the window reads the finished run back and does nothing more
    c = runner(tmp_path)
    assert c.due(ms(d, "10:15:00")) is False and c.runs_done == 0
    assert c.current == b.current
    h = c.history()
    assert h["runs"] == b.runs and len(h["runs"]) == 1
    assert h["stats"]["paper"] == {"label": "paper (forward)", **stats([596.0])}


def test_a_restart_after_the_window_finalises_from_the_recorded_ticks(tmp_path):
    d, rows = NFP_DAY, fixture_rows(NFP_DAY)
    r = runner(tmp_path)
    now = ms(d, "11:00:00")
    r.seed(now, ((_ns(x), x["price"], x["size"]) for x in rows))
    assert r.due(now)
    r.step(now)
    assert r.current["status"] == "traded" and r.current["pnl_usd"] == -434.0
    assert r.due(now + 5000) is False


def test_a_re_finalised_day_keeps_one_line(tmp_path):
    r = runner(tmp_path)
    r._reset(CPI_DAY)
    base = {"date": CPI_DAY.isoformat(), "event": "CPI", "rule": "csv", "state": "done", "legs": []}
    r._finish({**base, "status": "no_fill"})
    r._finish({**base, "status": "traded", "pnl_usd": 596.0})
    lines = (tmp_path / "paper" / "runs.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["status"] == "traded"


def test_stats_and_describe():
    assert stats([]) == {"n": 0, "wr": None, "avg": None, "net": 0.0}
    assert stats([596.0, -314.0, 596.0]) == {"n": 3, "wr": 66.7, "avg": 292.67, "net": 878.0}
    assert describe() == {"id": "gc_nfpcpi", "name": "GC NFP/CPI (paper)", "root": "GC",
                          "params": {"offset_pts": 2.0, "sl_pts": 3.0, "tp_pts": 6.0, "qty": 1}}


# ---------------------------------------------------------------- the replay-only flag

def _patch_run(monkeypatch, captured):
    monkeypatch.setattr(main_mod, "create_app", lambda **kw: captured.update(kw) or "app")
    monkeypatch.setattr(main_mod.uvicorn, "run", lambda app, **kw: None)


def test_paper_day_works_only_with_replay(monkeypatch, capsys):
    captured: dict = {}
    _patch_run(monkeypatch, captured)
    with pytest.raises(SystemExit):
        main_mod.main(["--paper-day"])
    assert "--paper-day works only with --replay" in capsys.readouterr().err
    assert captured == {}
    assert main_mod.main(["--replay", "2024-09-06", "--paper-day", "--start", "08:25"]) == 0
    assert captured["paper_day"] is True and captured["paper_backtest"] is None
    captured.clear()
    assert main_mod.main([]) == 0
    assert captured["paper_day"] is False and captured["paper_backtest"] is paper_mod.spawn_backtest
    with pytest.raises(ValueError):
        create_app(roots=["GC"], base=Path("/nonexistent"), paper_day=True)


# ---------------------------------------------------------------- the chart service

def _gc_live_app(tmp_path, now, **kw):
    return create_app(roots=["GC"], base=tmp_path / "ticks", feed_factory=QuietFeed,
                      now_ms=lambda: now, state=tmp_path / "state", **kw)


def test_the_service_routes_and_the_live_ws_push(tmp_path):
    d = CPI_DAY
    now = ms(d, "08:30:10")
    rows = [x for x in fixture_rows(d, ns=False) if x["ts_ms"] <= now]
    (tmp_path / "state" / "paper").mkdir(parents=True)
    (tmp_path / "state" / "paper" / "backtest.json").write_text(json.dumps(
        {"window": "2021-2024", "n": 77, "wr": 67.5, "avg": 296.78, "net": 22852.0, "extra": 1}))
    with TestClient(_gc_live_app(tmp_path, now), base_url="http://127.0.0.1:8852") as c:
        assert c.get("/api/paper/strategies").json() == [describe()]
        assert c.get("/api/paper/history", params={"strategy": "nope"}).status_code == 404
        with c.websocket_connect("/ws", headers=WS_HOST) as ws:
            QuietFeed.last.q.put(("GC", "GCZ4", rows))
            m = next_of(ws, "paper", limit=400)
            assert m["strategy"] == "gc_nfpcpi" and m["date"] == d.isoformat() and m["event"] == "CPI"
            for _ in range(20):
                if m["state"] == "in_trade":
                    break
                m = next_of(ws, "paper", limit=400)
            assert m["state"] == "in_trade"
            assert m["entry"]["side"] == "long" and m["exit"] is None and m["pnl_usd"] is None
        with c.websocket_connect("/ws", headers=WS_HOST) as ws2:     # a new page gets the state at once
            assert ws2.receive_json()["type"] == "status"
            assert ws2.receive_json() == m
        h = c.get("/api/paper/history").json()
        assert h["runs"] == [] and h["current"] == m
        assert h["stats"]["backtest"] == {"window": "2021-2024", "n": 77, "wr": 67.5, "avg": 296.78,
                                          "net": 22852.0}
        assert h["stats"]["paper"]["n"] == 0


def test_the_service_never_launches_the_backtest_unless_asked_and_only_once(tmp_path):
    launched = []

    class Job:
        def poll(self):
            return 0

    with TestClient(_gc_live_app(tmp_path, ms(CPI_DAY, "07:00:00"),
                                 paper_backtest=lambda folder: launched.append(folder) or Job())):
        pass
    assert launched == [tmp_path / "state" / "paper"]
    (tmp_path / "state" / "paper").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "paper" / "backtest.json").write_text("{}")
    with TestClient(_gc_live_app(tmp_path, ms(CPI_DAY, "07:00:00"),
                                 paper_backtest=lambda folder: launched.append(folder) or Job())):
        pass
    assert len(launched) == 1


def _replay_archive(tmp_path, d: dt.date) -> Path:
    import csv
    import gzip
    import io
    base = tmp_path / "ticks"
    p = base / "GC" / str(d.year) / f"{d.isoformat()}_GCZ4.csv.gz"
    p.parent.mkdir(parents=True)
    rows = fixture_rows(d)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["ts_ms", "price", "size", "bid", "ask", "id", "ts_ns"], extrasaction="ignore")
    w.writeheader()
    w.writerows({**r, "id": i + 1} for i, r in enumerate(rows))
    p.write_bytes(gzip.compress(buf.getvalue().encode()))
    p.with_name(p.name[:-len(".csv.gz")] + ".json").write_text(json.dumps(
        {"root": "GC", "contract": "GCZ4", "session_date": d.isoformat(), "ticks": len(rows), "complete": True}))
    return base


def test_a_forced_replay_day_runs_the_paper_and_stores_nothing(tmp_path):
    d = CPI_DAY
    app = create_app(roots=["GC"], base=_replay_archive(tmp_path, d), replay=d, speed=40,
                     start_et=dt.time(8, 29, 55), state=tmp_path / "state", paper_day=True)
    with TestClient(app, base_url="http://127.0.0.1:8852") as c, \
            c.websocket_connect("/ws", headers=WS_HOST) as ws:
        seen = []
        for _ in range(60):
            m = next_of(ws, "paper", limit=400)
            seen.append(m["state"])
            if m["state"] in ("in_trade", "done"):
                break
        assert "in_trade" in seen or "done" in seen
        assert m["rule"] == "forced" and m["event"] == "CPI" and m["entry"]["side"] == "long"
    assert not (tmp_path / "state" / "paper" / "runs.jsonl").exists()


def test_a_replay_without_the_flag_runs_no_paper(tmp_path):
    d = CPI_DAY
    app = create_app(roots=["GC"], base=_replay_archive(tmp_path, d), replay=d, speed=40,
                     start_et=dt.time(8, 29, 55), state=tmp_path / "state")
    with TestClient(app, base_url="http://127.0.0.1:8852") as c:
        import time
        time.sleep(1.5)
        assert c.get("/api/paper/history").json()["current"] is None
