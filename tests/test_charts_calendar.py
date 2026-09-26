"""The economic calendar (ForexFactory's weekly feed, spec §6): parsing, the 30-minute floor, keeping the
last good data, per-week storage and the range merge, the country filter, the route and the status field.
Every fetch is injected: no test touches the network."""
from __future__ import annotations

import datetime as dt
import json
import time

import pytest
from fastapi.testclient import TestClient

from homebase.charts import calendar as calendar_module
from homebase.charts.calendar import EVERY_S, FF_URL, IMPACTS, MIN_GAP_S, Calendar, parse, week_start
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive

FEED = [
    {"title": "RBNZ Rate Statement", "country": "NZD", "date": "2026-09-20T22:00:00-04:00", "impact": "High",
     "forecast": "", "previous": ""},
    {"title": "German ifo Business Climate", "country": "EUR", "date": "2026-09-22T04:00:00-04:00",
     "impact": "Medium", "forecast": "88.9", "previous": "88.8"},
    {"title": "CPI m/m", "country": "USD", "date": "2026-09-22T08:30:00-04:00", "impact": "High",
     "forecast": "0.3%", "previous": "0.2%"},
    {"title": "Core CPI m/m", "country": "USD", "date": "2026-09-22T08:30:00-04:00", "impact": "High",
     "forecast": "0.3%", "previous": "0.3%"},
    {"title": "Bank Holiday", "country": "JPY", "date": "2026-09-23T00:00:00-04:00", "impact": "Holiday",
     "forecast": "", "previous": ""},
    {"title": "Crude Oil Inventories", "country": "USD", "date": "2026-09-23T10:30:00-04:00", "impact": "Low",
     "forecast": None, "previous": "-1.2M"},
    {"title": "OPEC Meetings", "country": "All", "date": "2026-09-24T03:00:00-04:00", "impact": "Non-Economic",
     "forecast": "", "previous": ""},
]
T0 = 1_790_000_000.0          # a wall clock for the fetch timer (seconds)


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def feed(events=FEED):
    return lambda url: json.dumps(events).encode()


def test_parse_turns_iso_times_with_their_offsets_into_epoch_ms():
    evs = parse(FEED)
    assert [e["title"] for e in evs] == ["RBNZ Rate Statement", "German ifo Business Climate", "CPI m/m",
                                         "Core CPI m/m", "Bank Holiday", "Crude Oil Inventories", "OPEC Meetings"]
    assert evs[2] == {"t_ms": ms("2026-09-22T12:30:00+00:00"), "title": "CPI m/m", "country": "USD",
                      "impact": "High", "forecast": "0.3%", "previous": "0.2%"}
    assert parse([{**FEED[2], "date": "2026-09-22T13:30:00+01:00"}])[0]["t_ms"] == evs[2]["t_ms"]   # any offset
    assert {e["impact"] for e in evs} == set(IMPACTS) == {"High", "Medium", "Low", "Holiday", "Non-Economic"}
    assert evs[5]["forecast"] == "" and evs[6]["country"] == "ALL"


def test_parse_skips_bad_items_and_refuses_a_non_list():
    bad = [{**FEED[2], "impact": "Weird"}, {**FEED[2], "date": "2026-09-22T08:30:00"},      # no offset
           {**FEED[2], "date": "soon"}, {**FEED[2], "title": ""}, "CPI", None]
    assert parse(bad + [FEED[2]]) == parse([FEED[2]])
    with pytest.raises(ValueError):
        parse({"events": FEED})


def test_the_week_is_forexfactorys_sunday_to_saturday_in_et():
    assert week_start(ms("2026-09-20T22:00:00-04:00")) == dt.date(2026, 9, 20)       # Sunday evening
    assert week_start(ms("2026-09-22T08:30:00-04:00")) == dt.date(2026, 9, 20)
    assert week_start(ms("2026-09-26T23:59:00-04:00")) == dt.date(2026, 9, 20)       # Saturday
    assert week_start(ms("2026-09-27T00:00:00-04:00")) == dt.date(2026, 9, 27)


def test_the_feed_is_asked_at_most_once_per_30_minutes_even_across_a_restart(tmp_path):
    clock, calls = [T0], []

    def fetch(url):
        calls.append(url)
        return json.dumps(FEED).encode()

    cal = Calendar(tmp_path / "cal", fetch=fetch, now=lambda: clock[0])
    assert cal.refresh() is True and calls == [FF_URL]
    clock[0] += MIN_GAP_S - 1
    assert cal.refresh() is False and len(calls) == 1                  # too soon
    clock[0] += 1
    assert cal.refresh() is True and len(calls) == 2
    again = Calendar(tmp_path / "cal", fetch=fetch, now=lambda: clock[0] + 60)    # a restart a minute later
    assert again.refresh() is False and len(calls) == 2
    assert again.wait_s() == EVERY_S - 60                               # after a good fetch: the next in an hour
    assert (MIN_GAP_S, EVERY_S) == (1800, 3600)
    assert Calendar(tmp_path / "other").refresh() is False              # no fetch function: never fetches


def test_a_failed_fetch_keeps_the_last_good_events_and_says_why(tmp_path):
    clock, answers = [T0], [json.dumps(FEED).encode()]

    def fetch(url):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    cal = Calendar(tmp_path / "cal", fetch=fetch, now=lambda: clock[0])
    assert cal.refresh()
    good, st = cal.events(0, 2 ** 62), cal.status()
    assert st == {"ok": True, "fetched_at": int(T0 * 1000), "error": None}
    for bad in (TimeoutError("timed out"), b"<html>blocked</html>", b"[]", json.dumps({"x": 1}).encode()):
        answers.append(bad)
        clock[0] += MIN_GAP_S
        assert cal.refresh() is False
        assert cal.events(0, 2 ** 62) == good
        now = cal.status()
        assert now["ok"] is False and now["error"] and now["fetched_at"] == st["fetched_at"]
    assert cal.wait_s() == MIN_GAP_S                                    # a failure is retried at the floor


def test_each_week_is_kept_on_disk_and_ranges_merge_across_weeks(tmp_path):
    folder, clock = tmp_path / "cal", [T0]
    nxt = [{**FEED[2], "title": "Retail Sales m/m", "date": "2026-09-29T08:30:00-04:00"}]
    answers = [json.dumps(FEED).encode(), json.dumps(nxt).encode()]
    cal = Calendar(folder, fetch=lambda url: answers.pop(0), now=lambda: clock[0])
    assert cal.refresh()
    clock[0] += EVERY_S
    assert cal.refresh()
    assert sorted(p.name for p in folder.glob("????-??-??.json")) == ["2026-09-20.json", "2026-09-27.json"]
    fresh = Calendar(folder)                                            # a restart reads every week back
    titles = [e["title"] for e in fresh.events(0, 2 ** 62)]
    assert titles[0] == "RBNZ Rate Statement" and titles[-1] == "Retail Sales m/m" and len(titles) == 8
    assert fresh.status()["ok"] is True


def test_the_query_is_a_time_range_and_a_set_of_countries(tmp_path):
    cal = Calendar(tmp_path / "cal", fetch=feed(), now=lambda: T0)
    cal.refresh()
    tue, wed = ms("2026-09-22T00:00:00-04:00"), ms("2026-09-23T00:00:00-04:00")
    assert [e["title"] for e in cal.events(tue, wed)] == ["German ifo Business Climate", "CPI m/m", "Core CPI m/m"]
    assert [e["title"] for e in cal.events(tue, wed, ["usd"])] == ["CPI m/m", "Core CPI m/m"]
    assert [e["title"] for e in cal.events(0, 2 ** 62, ["ALL", "JPY"])] == ["Bank Holiday", "OPEC Meetings"]
    assert cal.events(wed, tue) == []


def app(tmp_path, **kw):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0] * 60))
    return create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30),
                      state=tmp_path / "state", **kw)


def test_the_route_and_the_status_field(tmp_path):
    with TestClient(app(tmp_path, calendar_fetch=feed())) as client:
        for _ in range(300):                                            # the startup fetch runs off the event loop
            st = client.get("/api/status").json()["calendar"]
            if st["ok"]:
                break
            time.sleep(0.01)
        assert st["ok"] is True and st["error"] is None and st["fetched_at"]
        tue, wed = ms("2026-09-22T00:00:00-04:00"), ms("2026-09-23T00:00:00-04:00")
        got = client.get(f"/api/calendar?from={tue}&to={wed}&countries=USD,eur").json()
        assert [e["title"] for e in got] == ["German ifo Business Climate", "CPI m/m", "Core CPI m/m"]
        assert set(got[0]) == {"t_ms", "title", "country", "impact", "forecast", "previous"}
        assert len(client.get("/api/calendar").json()) == len(FEED)
        assert client.get("/api/calendar?from=soon").status_code == 400
    assert (tmp_path / "state" / "calendar" / "2026-09-20.json").exists()


def test_without_a_fetch_function_the_service_never_fetches(tmp_path):
    with TestClient(app(tmp_path)) as client:
        assert client.get("/api/status").json()["calendar"] == {"ok": False, "fetched_at": None, "error": None}
        assert client.get("/api/calendar").json() == []


class FakeResponse:
    """A urlopen() context manager reading from an in-memory buffer, chunked like a real socket read()."""

    def __init__(self, data: bytes):
        self.data = data

    def read(self, n=-1):
        if n is None or n < 0:
            n = len(self.data)
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_http_get_reads_at_most_2mb_and_a_bigger_response_is_a_failure(monkeypatch):
    body = [b""]

    def fake_urlopen(req, timeout=None, context=None):
        return FakeResponse(body[0])

    monkeypatch.setattr(calendar_module.urllib.request, "urlopen", fake_urlopen)

    assert calendar_module.MAX_RESPONSE_BYTES == 2_000_000
    body[0] = b"{" + b" " * (calendar_module.MAX_RESPONSE_BYTES - 2) + b"}"
    assert calendar_module.http_get("https://example.test") == body[0]         # right at the cap: fine

    body[0] = b"x" * (calendar_module.MAX_RESPONSE_BYTES + 1)
    with pytest.raises(ValueError, match="2000000 bytes"):
        calendar_module.http_get("https://example.test")


def test_an_oversized_feed_response_is_treated_as_a_failed_fetch(tmp_path):
    """refresh() calls the injected fetch function; one that raises (as http_get now does for an
    oversized response) must land exactly like any other failed fetch -- the last good week kept,
    ok=False, and the error recorded."""
    def huge(url):
        raise ValueError("response over 2000000 bytes")

    cal = Calendar(tmp_path / "calendar", fetch=huge, now=lambda: T0)
    assert cal.refresh() is False
    assert cal.ok is False and "2000000 bytes" in cal.error
