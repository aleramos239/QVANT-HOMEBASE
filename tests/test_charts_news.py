"""The news feed (spec `docs/superpowers/specs/2026-09-27-charts-news-design.md`, Part A #1):
RSS parsing (both formats), the tagger, dedup, the 60 s floor, the 2 MB cap,
no fetch in replay, storage + retention, `/api/news` filters, and the Host
allowlist on the new route. Every fetch is injected: no test touches the
network."""
from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from homebase.charts import news as news_module
from homebase.charts.news import FINANCIALJUICE, TRUMPSTRUTH, News, parse_rss, tag
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive

T0 = 1_790_000_000.0

RSS_ITEM = """<rss version="2.0"><channel>
<item><title>Fed's Powell signals a rate cut is coming</title>
<link>https://www.financialjuice.com/story/1</link><guid>fj-1</guid>
<pubDate>Fri, 26 Sep 2026 12:30:00 GMT</pubDate></item>
<item><title>OPEC weighs oil output cut amid crude glut</title>
<link>https://www.financialjuice.com/story/2</link><guid>fj-2</guid>
<pubDate>Fri, 26 Sep 2026 12:31:00 GMT</pubDate></item>
</channel></rss>"""

ATOM_ENTRY = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Just posted about tariffs on China</title>
<link href="https://trumpstruth.org/posts/1"/><id>truth-1</id>
<published>2026-09-26T12:32:00+00:00</published></entry>
</feed>"""


def feed(raw: str):
    return lambda url: raw.encode()


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def test_parse_rss_reads_rss2_items():
    items = parse_rss(RSS_ITEM.encode())
    assert [it["title"] for it in items] == ["Fed's Powell signals a rate cut is coming",
                                             "OPEC weighs oil output cut amid crude glut"]
    assert items[0]["url"] == "https://www.financialjuice.com/story/1"
    assert items[0]["guid"] == "fj-1"
    assert items[0]["t_ms"] == ms("2026-09-26T12:30:00+00:00")


def test_parse_rss_reads_atom_entries_too():
    items = parse_rss(ATOM_ENTRY.encode())
    assert items == [{"title": "Just posted about tariffs on China", "url": "https://trumpstruth.org/posts/1",
                      "guid": "truth-1", "t_ms": ms("2026-09-26T12:32:00+00:00")}]


def test_parse_rss_skips_items_with_no_title_link_or_date_but_keeps_the_rest():
    raw = """<rss><channel>
    <item><title/><link>x</link><guid>a</guid><pubDate>Fri, 26 Sep 2026 12:00:00 GMT</pubDate></item>
    <item><title>ok</title><link>y</link><guid>b</guid></item>
    <item><title>ok2</title><link>z</link><guid>c</guid><pubDate>not a date</pubDate></item>
    <item><title>keep me</title><link>w</link><guid>d</guid><pubDate>Fri, 26 Sep 2026 12:00:00 GMT</pubDate></item>
    </channel></rss>"""
    items = parse_rss(raw.encode())
    assert [it["title"] for it in items] == ["keep me"]


def test_parse_rss_raises_on_unparseable_xml():
    with pytest.raises(ValueError):
        parse_rss(b"<rss><channel><item><title>oops</item></channel>")   # truncated, unbalanced


def test_the_tagger_matches_case_insensitively_and_trump_is_special():
    assert set(tag("financialjuice", "Fed's Powell signals a RATE CUT")) == {"fed"}
    assert set(tag("financialjuice", "OPEC weighs oil output cut amid crude glut")) == {"oil"}
    assert set(tag("financialjuice", "Missile strike near the Iran border")) == {"war", "iran"}
    assert set(tag("financialjuice", "CPI m/m beats expectations")) == {"data"}
    assert set(tag("financialjuice", "BREAKING: ceasefire reached")) == {"breaking", "war"}
    assert set(tag("financialjuice", "Trump threatens new tariffs on China")) == {"trump", "tariff", "china"}
    assert tag("truth", "Just a normal post about the weather") == ["trump"]     # every truth item is tagged
    assert tag("financialjuice", "Nothing notable happens") == []


def test_dedup_by_id_across_polls_and_across_a_restart(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return RSS_ITEM.encode()

    n = News(tmp_path / "news", fetch=fetch, now=lambda: T0)
    first = n.poll()
    assert len(first) == 4                                # 2 items x 2 sources (same feed body, different ids)
    n._last_try = {s: 0.0 for s in n._last_try}          # force past the 60 s floor
    again = n.poll()
    assert again == []                                    # same guids/titles: already seen
    fresh = News(tmp_path / "news", fetch=fetch, now=lambda: T0 + 1000)
    assert fresh.poll() == []                             # dedup survives a restart (loaded from disk)


def test_the_feed_is_polled_at_most_once_per_60_seconds_per_source(tmp_path):
    clock = [T0]
    n = News(tmp_path / "news", fetch=feed(RSS_ITEM), now=lambda: clock[0])
    assert len(n.poll()) == 4                             # 2 items x 2 sources
    clock[0] += 59
    assert n.poll() == []
    clock[0] += 1
    n.fetch = feed(RSS_ITEM.replace("fj-1", "fj-1b").replace("fj-2", "fj-2b"))
    assert len(n.poll()) == 4


def test_without_a_fetch_function_nothing_is_ever_polled(tmp_path):
    n = News(tmp_path / "news", fetch=None, now=lambda: T0)
    assert n.poll() == []
    assert n.status() == {"ok": False, "last_fetch": {"financialjuice": {"at": None, "items": 0, "error": None},
                                                       "truth": {"at": None, "items": 0, "error": None}},
                          "delay_p50_s": None}


def test_http_get_reads_at_most_2mb_and_a_bigger_response_is_a_failure(monkeypatch):
    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def read(self, n=-1):
            n = len(self.data) if n is None or n < 0 else n
            chunk, self.data = self.data[:n], self.data[n:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    body = [b""]
    monkeypatch.setattr(news_module.urllib.request, "urlopen", lambda *a, **k: FakeResponse(body[0]))
    assert news_module.MAX_RESPONSE_BYTES == 2_000_000
    body[0] = b"x" * news_module.MAX_RESPONSE_BYTES
    assert news_module.http_get("https://example.test") == body[0]
    body[0] = b"x" * (news_module.MAX_RESPONSE_BYTES + 1)
    with pytest.raises(ValueError, match="2000000 bytes"):
        news_module.http_get("https://example.test")


def test_an_oversized_or_erroring_fetch_is_a_failure_that_keeps_going(tmp_path):
    # SOURCES is (FINANCIALJUICE, TRUMPSTRUTH): the first answer (an error) is FJ's, the second (a
    # good feed) is truth's -- one source's failure must never stop the other from being polled.
    answers = [ValueError("response over 2000000 bytes"), RSS_ITEM.encode()]

    def fetch(url):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    n = News(tmp_path / "news", fetch=fetch, now=lambda: T0)
    got = n.poll()
    assert len(got) == 2 and {it["source"] for it in got} == {TRUMPSTRUTH.name}
    assert n.status()["last_fetch"][FINANCIALJUICE.name]["error"] is not None
    assert n.status()["last_fetch"][TRUMPSTRUTH.name]["error"] is None
    n._last_try[FINANCIALJUICE.name] = 0.0
    n.fetch = feed(RSS_ITEM)
    got2 = n.poll()
    assert len(got2) == 2 and {it["source"] for it in got2} == {FINANCIALJUICE.name}
    assert n.status()["last_fetch"][FINANCIALJUICE.name]["error"] is None


def test_storage_is_per_day_jsonl_keyed_by_seen_ms_et_and_atomic(tmp_path):
    n = News(tmp_path / "news", fetch=feed(RSS_ITEM), now=lambda: T0)
    n.poll()
    day = dt.datetime.fromtimestamp(T0, news_module.ET).date().isoformat()
    path = tmp_path / "news" / f"{day}.jsonl"
    assert path.exists()
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(lines) == 4                                # 2 items x 2 sources
    assert {"id", "source", "t_ms", "seen_ms", "title", "url", "tags"} <= set(lines[0])
    assert not list((tmp_path / "news").glob("*.tmp"))    # no leftover temp file


def test_retention_deletes_day_files_past_90_days(tmp_path):
    folder = tmp_path / "news"
    folder.mkdir()
    old_day = (dt.datetime.fromtimestamp(T0, news_module.ET).date() - dt.timedelta(days=91)).isoformat()
    recent_day = (dt.datetime.fromtimestamp(T0, news_module.ET).date() - dt.timedelta(days=10)).isoformat()
    (folder / f"{old_day}.jsonl").write_text(json.dumps({"id": "old", "source": "truth", "t_ms": 0,
                                                         "seen_ms": 0, "title": "x", "url": "", "tags": []}) + "\n")
    (folder / f"{recent_day}.jsonl").write_text(json.dumps({"id": "recent", "source": "truth", "t_ms": 0,
                                                            "seen_ms": 0, "title": "x", "url": "", "tags": []}) + "\n")
    n = News(folder, fetch=None, now=lambda: T0, retention_days=90)
    assert not (folder / f"{old_day}.jsonl").exists()      # pruned on load
    assert (folder / f"{recent_day}.jsonl").exists()
    got = n.items(0, 2 ** 62)
    assert [g["id"] for g in got] == ["recent"]             # the old day's item is gone, in memory too


def test_items_filters_by_range_tags_and_sources_newest_first(tmp_path):
    n = News(tmp_path / "news", fetch=None, now=lambda: T0)
    base = int(T0 * 1000)
    for i, (src, title, t_off) in enumerate([
        (FINANCIALJUICE.name, "Fed signals a rate cut", 0),
        (TRUMPSTRUTH.name, "Just talking about tariffs on China", 1000),
        (FINANCIALJUICE.name, "OPEC weighs an oil output cut", 2000),
    ]):
        rec = {"id": f"id{i}", "source": src, "t_ms": base + t_off, "seen_ms": base + t_off + 500,
              "title": title, "url": "", "tags": tag(src, title)}
        n._by_day.setdefault(news_module._day_key(rec["seen_ms"]), []).append(rec)
        n._seen.add(rec["id"])
    got = n.items(base, base + 3000)
    assert [g["id"] for g in got] == ["id2", "id1", "id0"]      # newest first
    assert [g["id"] for g in n.items(base, base + 3000, sources=["truth"])] == ["id1"]
    assert [g["id"] for g in n.items(base, base + 3000, tags=["oil"])] == ["id2"]
    assert n.items(base + 3000, base + 4000) == []


def app(tmp_path, **kw):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0] * 60))
    return create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30),
                      state=tmp_path / "state", **kw)


def test_replay_never_fetches_news(tmp_path):
    calls = []
    with TestClient(app(tmp_path, news_fetch=lambda url: calls.append(url) or RSS_ITEM.encode())):
        pass
    assert calls == []


def test_the_route_serves_stored_items_and_is_host_guarded(tmp_path):
    with TestClient(app(tmp_path), base_url="http://127.0.0.1:8852") as c:
        assert c.get("/api/news").json() == []
        good = c.get("/api/news?from=0&to=99999999999999")
        assert good.status_code == 200
        bad = c.get("/api/news", headers={"host": "evil.example"})
        assert bad.status_code == 403
        assert c.get("/api/news?from=soon").status_code == 400
