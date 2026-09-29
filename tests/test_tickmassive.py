"""The manual Massive gap-fill: SigV4, the credential order, what it targets,
the dry run, the fill through the archive's merge. Fakes and tmp dirs only --
never Massive, never S3, never ~/futures_ticks or ~/massive_raw."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json

import httpx
import pytest

from homebase import tickarchive as A
from homebase import tickmassive as M
from homebase import ticks as T

ET = T.ET
NOW = dt.datetime(2026, 9, 29, 17, 30, tzinfo=ET)
KEY, SECRET = "0f9d-access-key-id", "sk-THE-SECRET-api-key"


def minute_ms(date, minutes, root="NQ"):
    start, _ = T.session_bounds(date, root)
    s = int(start.timestamp() * 1000)
    return [s + m * 60_000 for m in minutes]


def raw_file(raw, exchange, date, rows):
    """A Massive daily file: [(ticker, ts_ms, price text, size)]; the ns stamp adds 123 ns."""
    p = M.raw_path(raw, exchange, date)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "timestamp", "sequence_number", "report_sequence", "price", "size",
                    "correction", "exchange", "session_end_date"])
        for i, (tk, ms, px, sz, *corr) in enumerate(rows):
            w.writerow([tk, ms * 1_000_000 + 123, 5_000_000 + i, i, px, sz, corr[0] if corr else 0, 4,
                        date.isoformat()])
    return p


def desk_file(base, root, date, contract, ts_list, first_id=1, ids=None):
    """A nightly file from before merges were logged (8 columns, legacy manifest);
    ids run on from first_id unless given (a lost stretch skips them)."""
    p = T.archive_path(root, date, contract, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    ids = ids if ids is not None else [first_id + i for i in range(len(ts_list))]
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(T.FIELDS)
        for t, i in zip(ts_list, ids):
            w.writerow([t, "20000.0", 1, "19999.75", "20000.0", 3, 4, i])
    start, end = T.session_bounds(date, root)
    A.manifest_path(p).write_text(json.dumps({
        "root": root, "contract": contract, "session_date": date.isoformat(), "ticks": len(ts_list),
        "session_start_utc": start.astimezone(A.UTC).isoformat(),
        "session_end_utc": end.astimezone(A.UTC).isoformat(),
        "first_tick_utc": A.iso_ms(ts_list[0]), "last_tick_utc": A.iso_ms(ts_list[-1]),
        "complete": False, "bytes": p.stat().st_size}))
    return p


# ------------------------------------------------------------------ S3
def test_the_signer_reproduces_awss_published_example():
    """docs.aws.amazon.com AmazonS3 sig-v4-header-based-auth, 'GET Object'."""
    h = M.sigv4("GET", "examplebucket.s3.amazonaws.com", "/test.txt", "AKIAIOSFODNN7EXAMPLE",
                "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                when=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc), extra={"Range": "bytes=0-9"})
    assert h["Authorization"].endswith(
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in h["Authorization"]


class FakeMassive:
    """An httpx transport standing in for files.massive.com: serves `files`
    only to requests signed with `good` (access key id); counts requests."""

    def __init__(self, files, good=KEY):
        self.files, self.good, self.seen = files, good, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        auth = req.headers.get("authorization", "")
        kid = auth.split("Credential=")[1].split("/")[0] if "Credential=" in auth else None
        self.seen.append((req.method, req.url.path, kid))
        if kid != self.good:
            return httpx.Response(403, text="<Error><Code>SignatureDoesNotMatch</Code></Error>")
        body = self.files.get(req.url.path.removeprefix("/flatfiles/"))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-length": str(len(body))},
                              content=b"" if req.method == "HEAD" else body)


def s3(fake):
    return M.S3(KEY, SECRET, client=httpx.Client(transport=httpx.MockTransport(fake)))


def test_the_key_pair_is_tried_in_either_order_and_the_working_one_kept(tmp_path):
    key = M.raw_key("cme", dt.date(2026, 9, 23))
    fake = FakeMassive({key: b"x" * 1000}, good=SECRET)      # the two values were swapped in the env
    c = s3(fake)
    assert c.size(key) == 1000
    assert [k for *_, k in fake.seen] == [KEY, SECRET]
    assert c.download(key, tmp_path / "f.csv.gz") == 1000 and (tmp_path / "f.csv.gz").read_bytes() == b"x" * 1000
    assert fake.seen[-1][2] == SECRET and len(fake.seen) == 3  # straight to the order that works
    assert fake.seen[0][1] == "/flatfiles/us_futures_cme/trades_v1/2026/09/2026-09-23.csv.gz"


def test_refused_credentials_never_show_up_in_a_message(tmp_path):
    fake = FakeMassive({}, good="someone-else")
    with pytest.raises(M.Refused) as e:
        s3(fake).size(M.raw_key("cme", dt.date(2026, 9, 23)))
    assert "both orders" in str(e.value) and KEY not in str(e.value) and SECRET not in str(e.value)


def test_a_short_download_leaves_no_file(tmp_path):
    key = M.raw_key("cme", dt.date(2026, 9, 23))

    def short(req):
        return httpx.Response(200, headers={"content-length": "10"}, content=b"12345")
    c = M.S3(KEY, SECRET, client=httpx.Client(transport=httpx.MockTransport(short)))
    with pytest.raises(M.Refused, match="5 bytes of 10"):
        c.download(key, tmp_path / "f.csv.gz")
    assert list(tmp_path.iterdir()) == []


def test_no_credentials_in_the_environment_is_said_plainly(monkeypatch):
    monkeypatch.delenv("MASSIVE_S3_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_S3_SECRET", raising=False)
    with pytest.raises(M.Refused, match="not set"):
        M.s3_from_env()


# ------------------------------------------------------------------ rows and files
def test_prices_are_written_like_the_research_backfill():
    assert M.price_text("0.000050000") == "0.00005"
    assert M.price_text("30780.000000000") == "30780"
    assert M.price_text("0.006397500") == "0.0063975"
    assert M.price_text("24500.250000000") == "24500.25"


def test_a_crypto_session_is_cut_from_up_to_two_trade_dates():
    d = dt.date
    assert M.raw_dates("NQ", d(2026, 9, 29)) == [d(2026, 9, 29)]
    assert M.raw_dates("BTC", d(2026, 9, 29)) == [d(2026, 9, 29), d(2026, 9, 30)]     # Tue 17:00-18:00: Wed's
    assert M.raw_dates("BTC", d(2026, 9, 25)) == [d(2026, 9, 25), d(2026, 9, 28)]     # Fri: the weekend file
    assert M.raw_dates("MBT", d(2026, 9, 26)) == [d(2026, 9, 28)]                     # Sat: Monday's file
    assert M.raw_dates("BTC", d(2026, 9, 28)) == [d(2026, 9, 28), d(2026, 9, 29)]


def test_scan_keeps_both_spellings_of_the_contract_and_counts_corrections(tmp_path):
    p = raw_file(tmp_path, "nymex", dt.date(2026, 9, 22), [
        ("NGX26", 1000, "2.965000000", 3), ("NGZ26", 1001, "3.1", 1), ("06EF7", 1002, "0.00005", 1),
        ("NGX26", 1003, "2.966000000", 1, 1)])
    got = M.scan_raw(p, {("NG", "X", "6")})
    assert got["rows"][("NG", "X", "6")] == [
        ("1000", "2.965", "3", "", "", "", "", "5000000", "1000000123"),
        ("1003", "2.966", "1", "", "", "", "", "5000003", "1003000123")]
    assert got["corrections"][("NG", "X", "6")] == 1


# ------------------------------------------------------------------ what it fills
def archive(tmp_path):
    base, raw = tmp_path / "ticks", tmp_path / "raw"
    d23, d29 = dt.date(2026, 9, 23), dt.date(2026, 9, 29)
    desk_file(base, "NQ", d23, "NQZ6", minute_ms(d23, range(120, 23 * 60)))             # from 20:00 ET
    kept = [m for m in range(23 * 60) if not 9 * 60 <= m < 15 * 60]                     # a 03:00-09:00 hole
    desk_file(base, "NQ", d29, "NQZ6", minute_ms(d29, kept), ids=kept)                  # its ids skip it
    desk_file(base, "YM", d23, "YMZ6", minute_ms(d23, range(23 * 60)))                   # complete
    nq = [("NQZ6", t, "20000.250000000", 2) for t in minute_ms(d23, range(23 * 60))]
    raw_file(raw, "cme", d23, nq + [("ESZ6", t, "6500.000000000", 1) for t in minute_ms(d23, range(23 * 60))])
    return base, raw


def test_holes_target_what_the_broker_no_longer_has_and_nothing_else(tmp_path):
    base, raw = archive(tmp_path)
    tg = M.targets(("NQ", "ES", "YM"), base, NOW, since=dt.date(2026, 9, 23))
    got = {(t["root"], t["date"].isoformat()): t["what"] for t in tg}
    assert got[("NQ", "2026-09-23")] == ["18:00-20:00 ET"]
    assert got[("ES", "2026-09-23")] == ["the whole session"]
    assert ("NQ", "2026-09-29") not in got          # 03:00-09:00 is still the broker's: the repair's
    assert not any(k[0] == "YM" and k[1] == "2026-09-23" for k in got)                 # complete
    both = M.targets(("NQ",), base, NOW, since=dt.date(2026, 9, 29), include_fetchable=True)
    assert [t["what"] for t in both] == [["03:00-09:00 ET"]]


def test_the_dry_run_lists_files_hours_and_megabytes_and_touches_nothing(tmp_path, capsys):
    base, raw = archive(tmp_path)
    before = {p: p.read_bytes() for p in base.rglob("*") if p.is_file()}
    d24 = dt.date(2026, 9, 24)
    now = dt.datetime(2026, 9, 24, 20, 30, tzinfo=ET)          # the 24th's first hours just left the broker
    fake = FakeMassive({M.raw_key("cme", d24): b"z" * 3_500_000, M.raw_key("cbot", d24): b"z" * 1_200_000})
    out = M.fill(("NQ", "ES", "YM"), base, now, since=dt.date(2026, 9, 23), dry_run=True, raw=raw, s3=s3(fake))
    text = capsys.readouterr().out
    assert out == [] and {p: p.read_bytes() for p in base.rglob("*") if p.is_file()} == before
    assert "merge into NQ/2026/2026-09-23_NQZ6.csv.gz: 18:00-20:00 ET" in text
    assert "new file ES/2026/2026-09-23_ESZ6.csv.gz: the whole session" in text
    assert "new file YM/2026/2026-09-24_YMZ6.csv.gz: the whole session" in text
    assert "YM  2026-09-23" not in text                                       # complete
    assert "raw cme   2026-09-23, 0.0 MB -- on disk" in text
    assert "raw cme   2026-09-24, 3.5 MB -- to download" in text
    assert "total: 5 session file(s); raw files: 1 on disk, 2 to download (4.7 MB)" in text
    assert all(m == "HEAD" for m, *_ in fake.seen) and not list(raw.glob("*/*/*.part"))
    assert KEY not in text and SECRET not in text


def test_a_dry_run_without_credentials_still_lists_everything(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MASSIVE_S3_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_S3_SECRET", raising=False)
    base, raw = archive(tmp_path)
    now = dt.datetime(2026, 9, 24, 20, 30, tzinfo=ET)
    M.fill(("ES",), base, now, since=dt.date(2026, 9, 23), dry_run=True, raw=raw)
    text = capsys.readouterr().out
    assert "raw cme   2026-09-24 -- to download, size unknown without credentials" in text
    assert "1 to download (0.0 MB + 1 of unknown size)" in text


def test_the_fill_merges_only_what_the_archive_lacks(tmp_path, capsys):
    base, raw = archive(tmp_path)
    tg = M.fill(("NQ", "ES"), base, NOW, dates=[dt.date(2026, 9, 23)], raw=raw, s3=s3(FakeMassive({})))
    nq = next(m for m in tg if m["root"] == "NQ")
    with gzip.open(T.archive_path("NQ", dt.date(2026, 9, 23), "NQZ6", base), "rt") as f:
        rows = list(csv.DictReader(f))
    massive = [r for r in rows if r["ts_ns"]]
    broker = [r for r in rows if not r["ts_ns"]]
    open_ms = minute_ms(dt.date(2026, 9, 23), [0])[0]
    assert len(broker) == 23 * 60 - 120 and all(r["bid"] for r in broker)        # untouched
    assert [int(r["ts_ms"]) for r in massive] == minute_ms(dt.date(2026, 9, 23), range(0, 120))
    assert massive[0]["ts_ns"] == str(open_ms * 1_000_000 + 123) and massive[0]["price"] == "20000.25"
    assert nq["complete"] and nq["merge"]["massive_added"] == 120 and not nq["bid_ask"]
    assert nq["sources"][-1]["kind"] == "massive" and nq["sources"][-1]["files"] == ["cme/2026-09-23.csv.gz"]
    es = next(m for m in tg if m["root"] == "ES")
    assert es["source"] == "massive" and es["ticks"] == 23 * 60 and es["complete"]
    assert run_again_adds_nothing(base, raw, capsys)


def run_again_adds_nothing(base, raw, capsys):
    capsys.readouterr()
    out = M.fill(("NQ",), base, NOW, dates=[dt.date(2026, 9, 23)], raw=raw, s3=s3(FakeMassive({})))
    return out == [] and "Massive has nothing the archive lacks" in capsys.readouterr().out


def test_a_download_lands_in_the_raw_layout_and_feeds_the_fill(tmp_path):
    base, raw = tmp_path / "ticks", tmp_path / "raw"
    d = dt.date(2026, 9, 24)
    src = raw_file(tmp_path / "src", "cbot", d, [("YMZ6", t, "46000", 1) for t in minute_ms(d, range(23 * 60))])
    fake = FakeMassive({M.raw_key("cbot", d): src.read_bytes()})
    out = M.fill(("YM",), base, NOW, dates=[d], raw=raw, s3=s3(fake))
    assert M.raw_path(raw, "cbot", d).read_bytes() == src.read_bytes()
    assert out[0]["ticks"] == 23 * 60 and out[0]["source"] == "massive"


def test_a_weekend_crypto_session_comes_from_mondays_file(tmp_path):
    base, raw = tmp_path / "ticks", tmp_path / "raw"
    sat, mon = dt.date(2026, 9, 26), dt.date(2026, 9, 28)
    start, end = T.session_bounds(sat, "BTC")                 # Fri 18:00 -> Sat 18:00
    s = int(start.timestamp() * 1000)
    weekend = [s - 3_600_000 + m * 60_000 for m in range(49 * 60)]          # Fri 17:00 -> Sun 18:00
    raw_file(raw, "cme", mon, [("BTCV6", t, "87185.000000000", 1) for t in weekend])
    out = M.fill(("BTC",), base, NOW, dates=[sat], raw=raw, s3=s3(FakeMassive({})))
    first, last = A.ms_of(out[0]["first_tick_utc"]), A.ms_of(out[0]["last_tick_utc"])
    assert first == s and last == int(end.timestamp() * 1000)                # its own 24 h only
    assert out[0]["ticks"] == 24 * 60 + 1 and out[0]["contract"] == "BTCV6"


def test_the_cli_needs_holes_or_dates(capsys):
    with pytest.raises(SystemExit):
        T.main(["--fill-from-massive"])
    assert "exactly one of --holes or --dates" in capsys.readouterr().err


def test_a_fill_needs_credentials_only_for_what_is_not_on_disk(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MASSIVE_S3_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_S3_SECRET", raising=False)
    base, raw = archive(tmp_path)
    out = M.fill(("NQ",), base, NOW, dates=[dt.date(2026, 9, 23)], raw=raw)     # its raw file is on disk
    assert out[0]["complete"]
    with pytest.raises(M.Refused, match="must be downloaded"):
        M.fill(("NQ",), base, NOW, dates=[dt.date(2026, 9, 24)], raw=raw)
