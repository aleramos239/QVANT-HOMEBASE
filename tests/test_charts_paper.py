"""The forward PAPER runner (homebase/charts/paper.py): parity with the backtester on real
archived GC event days, event-day detection, no trading imports, the 1-per-second throttle,
the window, persistence across a restart, and the replay-only --paper-day flag.

Fixtures: tests/fixtures/gc_paper_<date>.csv.gz, trimmed 08:29:30-09:56 ET from the tick
archive by tests/fixtures/make_gc_paper_fixture.py (research window only). No test reads
~/futures_ticks, opens a network connection or starts a service."""
from __future__ import annotations

import ast
from array import array
from bisect import bisect_left
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
          wall: Wall | None = None, states: list | None = None, alive: bool = False) -> int:
    """Play rows through the runner on a simulated clock [frm, to], the service's way:
    ticks as they 'arrive', then due()/step() every step_ms (wall advances with it).
    alive: other roots keep printing (the md socket is alive) at every step."""
    now, end, i = ms(d, frm), ms(d, to), 0
    wall = wall or runner.wall
    while now <= end:
        j = i
        while j < len(rows) and _ns(rows[j]) <= now * 1_000_000:
            j += 1
        if j > i:
            runner.on_ticks(rows[i:j])
            i = j
        if alive:
            runner.window_ms(now)                              # (rolls the day, as the service's poll does)
            runner.note_alive(now)
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
    # earlier prints -> 08:29:20 (carried, before 08:29:50; within the 60 s GC-stall limit of 08:30's prints)
    rows = [{**x, "ts_ms": ms(d, "08:29:20"), "ts_ns": ms(d, "08:29:20") * 1_000_000}
            if x["ts_ms"] < ms(d, "08:29:48") else x for x in rows]
    tape = Tape("GC", d, "", *stable_sorted(array("q", [_ns(x) for x in rows]), array("d", [x["price"] for x in rows]),
                                             array("i", [x["size"] for x in rows])), {})
    direct = run_session(GCNfpCpi(), tape, Costs())
    r = runner(tmp_path)
    drive(r, rows, d, "08:24:00", "09:56:03", step_ms=500, alive=True)   # only GC was quiet
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
    cal = _cal(tmp_path, _ff("Unemployment Claims", "2024-09-12"))          # the week is known: no event
    r = PaperRunner(tmp_path / "paper", cal, wall=Wall(), log=lambda m: None)
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
    r._reset(CPI_DAY, 0)
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

        def wait(self, timeout=None):
            return 0

    def spawn(folder):
        launched.append(folder)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "backtest.json").write_text("{}")
        return Job()

    import time
    with TestClient(_gc_live_app(tmp_path, ms(CPI_DAY, "07:00:00"), paper_backtest=spawn)):
        for _ in range(50):
            if launched:
                break
            time.sleep(0.02)
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


# ================================================================ fix round 1

def _seed(r: PaperRunner, now: int, rows: list[dict], gaps=()):
    r.seed(now, ((_ns(x), x["price"], x["size"]) for x in rows), gaps=gaps)


def _holey(d: dt.date, a: str, b: str) -> list[dict]:
    """The fixture day with every print in [a, b) ET missing."""
    return [x for x in fixture_rows(d) if not ms(d, a) <= x["ts_ms"] < ms(d, b)]


def _no_trade(cur: dict) -> None:
    assert cur["status"] == "no_data" and "feed gap" in cur["error"]
    assert cur["entry"] is None and cur["exit"] is None and cur["pnl_usd"] is None and cur["legs"] == []


# ---- C1: a gap never becomes a trade

def test_c1_a_restart_with_a_recorded_gap_finalises_no_data_never_a_fake_trade(tmp_path):
    """Scenario A: the service was down 08:29:55-08:40 and the refill was skipped (md
    budget): the recorder marked the hole. Without the mark the holey tape DOES trade."""
    d = NFP_DAY
    rows = _holey(d, "08:29:55", "08:40:00")
    ts = array("q", [_ns(x) for x in rows])
    holey = run_session(GCNfpCpi(), Tape("GC", d, "", ts, array("d", [x["price"] for x in rows]),
                                         array("i", [x["size"] for x in rows]), {}), Costs())
    assert holey.trades                                        # the fake trade the gap would have made
    r = runner(tmp_path)
    now = ms(d, "11:00:00")                                    # a restart after the window
    _seed(r, now, rows, gaps=[[ms(d, "08:29:55"), ms(d, "08:40:00")]])
    assert r.due(now)
    r.step(now)
    _no_trade(r.current)
    assert r.current["state"] == "done" and "08:29:55" in r.current["error"]
    rec = json.loads((tmp_path / "paper" / "runs.jsonl").read_text())
    assert rec["status"] == "no_data" and "pnl_usd" not in rec and "entry" not in rec


def test_c1_a_socket_drop_is_flagged_on_reconnect_until_the_refill_resolves_it(tmp_path):
    """Scenario A, live: the socket drops 08:29:55 and reconnects 08:40 while other roots'
    prints kept the feed looking alive; the reconnect flag makes the hole a gap."""
    d = CPI_DAY
    rows, wall = fixture_rows(d), Wall()
    r = runner(tmp_path, wall=wall)
    early = [x for x in rows if x["ts_ms"] < ms(d, "08:29:55")]
    drive(r, early, d, "08:29:40", "08:29:55")
    for s in range(ms(d, "08:29:55"), ms(d, "08:40:00"), 1000):
        r.note_alive(s)
    r.note_gap(ms(d, "08:29:55"), ms(d, "08:40:00"), "reconnect")
    wall.t += 5
    assert r.due(ms(d, "08:40:00")) and r.step(ms(d, "08:40:00")) is not None
    _no_trade(r.current)
    assert r.current["state"] == "waiting"                     # not final: a refill may still fill it
    # the refill fetched everything: the recording is complete, the flag is resolved
    _seed(r, ms(d, "08:40:05"), [x for x in rows if x["ts_ms"] <= ms(d, "08:40:05")], gaps=[])
    r.clear_pending()
    wall.t += 5
    r.step(ms(d, "08:40:05"))
    assert r.current["status"] == "traded" and r.current["pnl_usd"] == 596.0


def test_c1_five_seconds_of_silence_is_a_gap_unless_the_rest_of_the_feed_was_alive(tmp_path):
    d = CPI_DAY
    rows = _holey(d, "08:30:00.500", "08:30:30")
    r = runner(tmp_path / "dead")
    drive(r, rows, d, "08:29:40", "09:56:03")
    _no_trade(r.current)
    assert "silence" in r.current["error"]
    alive = runner(tmp_path / "alive")                         # NQ/ES kept printing: GC was just quiet
    drive(alive, rows, d, "08:29:40", "09:56:03", alive=True)
    assert alive.current["status"] != "no_data"


def test_c1_the_final_run_waits_for_a_gc_refill_until_10_30(tmp_path):
    """Scenario B: the refill is still paging at 09:56:02; the day is not finalised on the
    holey tape, and a reseed that lands later is used."""
    d, busy = CPI_DAY, [True]
    rows = fixture_rows(d)
    r = runner(tmp_path, busy=lambda: busy[0])
    drive(r, [x for x in rows if x["ts_ms"] < ms(d, "08:29:59")], d, "08:29:40", "09:56:03")
    assert not r.final
    r.wall.t += 5
    assert r.due(ms(d, "10:00:00")) is False                   # held while GC's refill runs
    _seed(r, ms(d, "10:10:00"), rows, gaps=[])                 # the refill landed
    busy[0] = False
    r.wall.t += 5
    assert r.due(ms(d, "10:10:00"))
    r.step(ms(d, "10:10:00"))
    assert r.final and r.current["status"] == "traded" and r.current["pnl_usd"] == 596.0
    # a refill still running at 10:30: finalised, as no_data
    r2 = runner(tmp_path / "late", busy=lambda: True)
    drive(r2, [x for x in rows if x["ts_ms"] < ms(d, "08:29:59")], d, "08:29:40", "09:56:03")
    r2.wall.t += 5
    assert r2.due(ms(d, "10:29:59")) is False and r2.due(ms(d, "10:30:00"))
    r2.step(ms(d, "10:30:00"))
    assert r2.final and r2.current["status"] == "no_data" and "refill" in r2.current["error"]


def test_c1_the_service_seeds_the_recorded_gaps_at_startup(tmp_path):
    """End to end: a live recording with a marked hole; the restarted service finalises
    no_data from the recording (sliced to the window, ticks from 18:00 the evening before)."""
    from tests.charts_util import write_gz
    d = NFP_DAY
    rows = [{"ts_ms": ms(d, "08:10:00") - 3600_000 * 13, "price": 2500.0, "size": 1, "id": 1}]
    rows += [{**x, "id": i + 2} for i, x in enumerate(_holey(d, "08:29:55", "08:40:00"))]
    live = tmp_path / "ticks" / "GC" / "2024" / f"{d.isoformat()}_GCZ4.live.csv.gz"
    write_gz(live, rows)
    live.with_name(f"{d.isoformat()}_GCZ4.live.gaps").write_text(
        json.dumps([[ms(d, "08:29:55"), ms(d, "08:40:00")]]))
    with TestClient(_gc_live_app(tmp_path, ms(d, "11:00:00")), base_url="http://127.0.0.1:8852") as c:
        import time
        for _ in range(40):
            h = c.get("/api/paper/history").json()
            if h["runs"]:
                break
            time.sleep(0.1)
    assert [x["status"] for x in h["runs"]] == ["no_data"] and "feed gap" in h["runs"][0]["error"]


# ---- I2: the backtest child

class FakeProc:
    def __init__(self, code=None, polls_until_exit=None):
        self.code, self.left = code, polls_until_exit
        self.killed = self.terminated = False
        self.waited = 0

    def poll(self):
        if self.killed or self.terminated:
            return -9
        if self.left is not None:
            self.left -= 1
            if self.left <= 0:
                return self.code
        return None

    def kill(self):
        self.killed = True

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited += 1
        return -9 if (self.killed or self.terminated) else self.code


def _job(tmp_path, now_ms, proc, wall0=1_800_000_000.0, on_spawn=None):
    import asyncio
    t = {"wall": wall0, "slept": []}

    async def sleep(s):
        t["slept"].append(s)
        t["wall"] += s

    def spawn(folder):
        t.setdefault("spawned", []).append(folder)
        if on_spawn:
            on_spawn(folder)
        return proc

    job = paper_mod.BacktestJob(tmp_path / "paper", spawn, lambda: now_ms, lambda m: None,
                                sleep=sleep, wall=lambda: t["wall"])
    asyncio.run(job.run())
    return job, t


def test_i2_the_backtest_never_starts_between_08_00_and_10_00_et(tmp_path):
    d = CPI_DAY
    assert paper_mod.backtest_delay_s(ms(d, "07:59:59")) == 0
    assert paper_mod.backtest_delay_s(ms(d, "08:00:00")) == 2 * 3600 + 5 * 60
    assert paper_mod.backtest_delay_s(ms(d, "09:25:00")) == 40 * 60      # the QUIET window too
    assert paper_mod.backtest_delay_s(ms(d, "10:00:00")) == 0
    ok = lambda f: (f.mkdir(parents=True), (f / "backtest.json").write_text("{}"))   # noqa: E731
    _, t = _job(tmp_path, ms(d, "08:30:00"), FakeProc(0, 1), on_spawn=ok)
    assert t["slept"][0] == 95 * 60 and t["spawned"]              # waited to 10:05, then launched


def test_i2_a_hung_backtest_is_killed_after_15_minutes_and_blocks_respawn_for_24h(tmp_path):
    proc = FakeProc()                                              # never exits
    _, t = _job(tmp_path, ms(CPI_DAY, "12:00:00"), proc)
    assert proc.killed and proc.waited >= 1                        # killed and reaped
    assert 15 * 60 <= sum(t["slept"]) <= 15 * 60 + 10
    failed = json.loads((tmp_path / "paper" / "backtest.failed").read_text())
    assert "timeout" in failed["reason"]
    _, t2 = _job(tmp_path, ms(CPI_DAY, "12:00:00"), FakeProc(0, 1), wall0=t["wall"] + 3600)
    assert "spawned" not in t2                                     # blocked for 24 h
    _, t3 = _job(tmp_path, ms(CPI_DAY, "12:00:00"), FakeProc(0, 1), wall0=t["wall"] + 86_401)
    assert t3["spawned"]


def test_i2_the_child_is_reaped_and_a_failed_exit_leaves_the_marker(tmp_path):
    ok = FakeProc(0, 2)
    _job(tmp_path / "a", ms(CPI_DAY, "12:00:00"), ok, on_spawn=lambda f: (f.mkdir(parents=True), (f / "backtest.json").write_text("{}")))
    assert ok.waited == 1 and not (tmp_path / "a" / "paper" / "backtest.failed").exists()
    bad = FakeProc(1, 2)
    _job(tmp_path / "b", ms(CPI_DAY, "12:00:00"), bad)
    assert bad.waited == 1
    assert "exit 1" in json.loads((tmp_path / "b" / "paper" / "backtest.failed").read_text())["reason"]


def test_i2_stop_terminates_and_reaps_a_running_child(tmp_path):
    job = paper_mod.BacktestJob(tmp_path / "paper", lambda f: None, lambda: 0, lambda m: None)
    job.proc = FakeProc()
    job.stop()
    assert job.proc.terminated and job.proc.waited == 1


# ---- I3: replay isolation

def test_i3_a_replay_never_reads_or_writes_the_forward_record(tmp_path):
    d = CPI_DAY
    folder = tmp_path / "state" / "paper"
    folder.mkdir(parents=True)
    forward = [{"date": "2024-10-10", "strategy": "gc_nfpcpi", "event": "CPI", "rule": "ff", "status": "traded",
                "legs": [], "pnl_usd": 596.0},
               {"date": d.isoformat(), "strategy": "gc_nfpcpi", "event": "CPI", "rule": "ff",
                "status": "no_fill", "legs": []}]
    (folder / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in forward))
    before = (folder / "runs.jsonl").read_bytes()
    app = create_app(roots=["GC"], base=_replay_archive(tmp_path, d), replay=d, speed=40,
                     start_et=dt.time(8, 29, 55), state=tmp_path / "state", paper_day=True)
    with TestClient(app, base_url="http://127.0.0.1:8852") as c, \
            c.websocket_connect("/ws", headers=WS_HOST) as ws:
        m = next_of(ws, "paper", limit=400)
        assert m["replay"] is True and m["status"] != "no_fill"    # not the stored forward run
        h = c.get("/api/paper/history").json()
        assert all(x.get("replay") for x in h["runs"])            # the forward runs are not listed
        assert h["stats"]["paper"]["n"] == 0
    assert (folder / "runs.jsonl").read_bytes() == before


def test_i3_replay_runs_are_tagged_and_kept_out_of_the_forward_stats(tmp_path):
    r = PaperRunner(None, None, replay=True, force_day=CPI_DAY, persist=False, wall=Wall(), log=lambda m: None)
    drive(r, fixture_rows(CPI_DAY), CPI_DAY, "08:29:40", "09:56:03")
    assert r.final and r.current["replay"] is True and r.runs[0]["replay"] is True
    assert r.runs[0]["status"] == "traded"
    assert r.history()["stats"]["paper"]["n"] == 0


# ---- M4: --paper-day refuses the test days (2025-07-01 on: the blueprint's dates, backtest/discipline.py)

def test_m4_paper_day_refuses_the_test_days_unless_allowed(monkeypatch, capsys):
    captured: dict = {}
    _patch_run(monkeypatch, captured)
    with pytest.raises(SystemExit):
        main_mod.main(["--replay", "2025-07-01", "--paper-day"])                 # the first test day
    assert "dates after 2025-06-30 are the test days" in capsys.readouterr().err and captured == {}
    for build_day in ("2024-12-31", "2025-01-02", "2025-06-30"):                 # the first half of 2025 is build days
        assert main_mod.main(["--replay", build_day, "--paper-day"]) == 0
    assert main_mod.main(["--replay", "2025-10-03", "--paper-day", "--paper-allow-holdout"]) == 0
    assert captured["replay"] == dt.date(2025, 10, 3) and captured["paper_day"] is True
    with pytest.raises(SystemExit):
        main_mod.main(["--replay", "2025-10-03", "--paper-allow-holdout"])


# ---- M5: the tags are re-read at 08:29:50; a missing calendar is recorded

def test_m5_an_event_removed_before_08_29_50_is_not_traded(tmp_path):
    d = dt.date(2026, 10, 2)
    cal = _cal(tmp_path, _ff("Non-Farm Employment Change", "2026-10-02"))
    r = PaperRunner(tmp_path / "paper", cal, wall=Wall(), log=lambda m: None)
    r.due(ms(d, "07:00:00"))
    assert r.tags == frozenset({"NFP"})
    wk = week_start(ms(d, "08:30")).isoformat()
    cal.weeks[wk] = [e for e in cal.weeks[wk] if e["title"] != "Non-Farm Employment Change"]   # postponed
    assert r.due(ms(d, "08:29:50")) is False
    assert r.tags == frozenset() and r.rule == "ff" and r.runs_done == 0


def test_m5_a_missing_calendar_week_is_recorded_not_silently_skipped(tmp_path):
    d = dt.date(2026, 10, 2)                                        # past the CSV, FF week never fetched
    r = PaperRunner(tmp_path / "paper", _cal(tmp_path), wall=Wall(), log=lambda m: None)
    assert r.due(ms(d, "08:00:00")) is False
    assert r.due(ms(d, "08:29:50"))
    r.step(ms(d, "08:29:50"))
    assert r.final and r.current["status"] == "calendar_missing"
    rec = json.loads((tmp_path / "paper" / "runs.jsonl").read_text())
    assert rec["status"] == "calendar_missing" and rec["date"] == d.isoformat()
    assert r.history()["stats"]["paper"]["n"] == 0
    sat = PaperRunner(tmp_path / "sat", _cal(tmp_path), wall=Wall(), log=lambda m: None)
    assert sat.due(ms(dt.date(2026, 10, 3), "08:29:50")) is False  # a weekend is not missing


# ---- M6/M7: nothing is marked done until it succeeded

def test_m6_a_failed_snapshot_is_retried(tmp_path):
    r = runner(tmp_path)
    d = CPI_DAY
    drive(r, fixture_rows(d), d, "08:29:40", "08:29:55")
    real, calls = r.snapshot, []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("boom")
        return real()

    r.snapshot = flaky
    now = ms(d, "08:30:05")
    r.wall.t += 5
    assert r.due(now) and r.step(now) is None
    assert r.phase == 1                                            # not advanced
    r.wall.t += 1
    assert r.due(now)
    assert r.step(now) is not None and r.phase == 2


def test_m7_a_failed_write_keeps_the_day_open_and_retries(tmp_path, monkeypatch):
    r = runner(tmp_path)
    d = CPI_DAY
    drive(r, fixture_rows(d), d, "08:29:40", "09:55:00")
    real, calls = paper_mod._jsonl.append, []

    def flaky(path, obj):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk full")
        return real(path, obj)

    monkeypatch.setattr(paper_mod._jsonl, "append", flaky)
    end = ms(d, "09:56:03")
    r.wall.t += 5
    assert r.due(end)
    r.step(end)
    assert not r.final and r.runs == []
    r.wall.t += 1
    assert r.due(end)
    r.step(end)
    assert r.final and len(r.runs) == 1
    assert len((tmp_path / "paper" / "runs.jsonl").read_text().splitlines()) == 1


# ---- M8: seeding only walks the window

def test_m8_window_ms_bounds_the_seed(tmp_path):
    r = runner(tmp_path)
    assert r.window_ms(ms(CPI_DAY, "07:00:00")) == (ms(CPI_DAY, "08:20:00"), ms(CPI_DAY, "09:56:00"))
    assert runner(tmp_path / "x").window_ms(ms(dt.date(2024, 9, 9), "07:00:00")) is None


# ================================================================ fix round 2

def test_r2_a_gc_only_stall_after_the_fill_is_no_data_never_a_trade(tmp_path):
    """GC's subscription dies at 08:30:05 while NQ/ES keep printing: no 09:55 flat ever
    prints, so the engine's end-of-tape close would be saved as a trade."""
    d = NFP_DAY
    rows = [x for x in fixture_rows(d) if x["ts_ms"] < ms(d, "08:30:05")]
    r = runner(tmp_path)
    drive(r, rows, d, "08:29:40", "09:56:03", alive=True)
    assert r.final
    _no_trade(r.current)
    assert "GC stall" in r.current["error"]


def test_r2_a_gap_ending_just_before_08_29_50_with_a_stale_carried_anchor_is_no_data(tmp_path):
    """No GC print in [08:29:50, 08:30); the anchor is the carried 08:24:59 print and the
    recording marks 08:25:00-08:29:49 missing: the legs would come from a stale anchor."""
    d = CPI_DAY
    real = fixture_rows(d)
    rows = [{**real[0], "ts_ms": ms(d, "08:24:59"), "ts_ns": ms(d, "08:24:59") * 1_000_000}]
    rows += [x for x in real if x["ts_ms"] >= ms(d, "08:30:00")]
    r = runner(tmp_path)
    now = ms(d, "08:29:40")
    _seed(r, now, [x for x in rows if x["ts_ms"] < now], gaps=[[ms(d, "08:25:00"), ms(d, "08:29:49")]])
    drive(r, rows, d, "08:29:40", "09:56:03", alive=True)
    assert r.final
    _no_trade(r.current)
    assert "08:25:00" in r.current["error"]


def test_r2_genuine_lulls_do_not_trip_the_stall_check():
    """The worst real GC lull between 08:31 and 09:55 in the research window is 12.5 s;
    both fixtures' longest GC silence after the anchor is far under 60 s."""
    for d in (NFP_DAY, CPI_DAY):
        ts, _, _ = fixture(d)
        i = bisect_left(ts, et_ns(d, "08:30:00")) - 1
        j = bisect_left(ts, et_ns(d, "09:55:00"))
        pts = list(ts[i:j]) + [et_ns(d, "09:55:00")]
        assert max(b - a for a, b in zip(pts, pts[1:])) < paper_mod.STALL_NS
