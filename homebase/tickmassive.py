"""Fill the tick archive from Massive (ex-Polygon) flat files -- a manual,
one-shot command, off by default (the plan ends with September 2026):

    python -m homebase.ticks --fill-from-massive --holes --dry-run   # every file, hour and MB it would touch
    python -m homebase.ticks --fill-from-massive --holes             # what the broker no longer has, since 09-22
    python -m homebase.ticks --fill-from-massive --dates 2026-09-23,2026-09-24 [--roots NQ,ES]

--holes takes every root's sessions since --since (default 2026-09-22) and
fills each one the coverage check (homebase.tickcoverage) finds missing or
with a hole -- hours without a tick, or ticks that stop short of the open or
the close -- once the broker's history no longer has it (the nightly and the
repair fetch those with bid/ask; --include-fetchable fills them anyway).

Massive's daily file per exchange, s3://flatfiles/us_futures_<exchange>/
trades_v1/YYYY/MM/YYYY-MM-DD.csv.gz, holds every trade of that trade date
with its exchange ns stamp: no bid/ask, one row per match and price level.
Each target -- root, session, the contract the archive records -- gets its
rows through the archive's merge (homebase.tickarchive): a Massive row lands
only where no broker tick is within 2 s, so it fills holes and never doubles
a trade, and a missing session is written whole. The rows come out exactly as
research/massive_ticks.py writes them (ts_ms, the price without trailing
zeros, size, the sequence number as `id`, `ts_ns`). Massive files a crypto
weekend under Monday's trade date and rolls it at 17:00 ET, so a BTC/MBT
session (18:00 -> 18:00, every day) is cut from up to two files.

Credentials: env MASSIVE_S3_KEY / MASSIVE_S3_SECRET, tried in either order
(the research script's rule), never printed. Downloads land in
~/massive_raw/<exchange>/<YYYY>/ (the research script's layout: a file
already there is used as is). S3 requests are signed here (SigV4, stdlib +
httpx): the desk's venv carries no boto3 and is never pip-installed into.
"""
from __future__ import annotations

import csv
import datetime as dt
import decimal
import gzip
import hashlib
import hmac
import os
import zlib
from pathlib import Path
from urllib.parse import quote

from . import symbols
from . import tickarchive as A
from . import tickcoverage as C
from . import ticks as T

RAW = Path.home() / "massive_raw"
SINCE = dt.date(2026, 9, 22)
BUCKET = "flatfiles"
ENDPOINT = "https://files.massive.com"
EXCHANGE = {"NQ": "cme", "ES": "cme", "RTY": "cme", "6E": "cme", "6J": "cme", "6B": "cme",
            "BTC": "cme", "MBT": "cme", "YM": "cbot", "ZN": "cbot", "GC": "comex", "SI": "comex",
            "HG": "comex", "CL": "nymex", "NG": "nymex"}
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def log(msg: str) -> None:
    T.log(f"massive: {msg}")


# ------------------------------------------------------------------ S3 (SigV4)
def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4(method: str, host: str, path: str, key_id: str, secret: str, *, when: dt.datetime,
          region: str = "us-east-1", service: str = "s3", extra: dict | None = None,
          payload_hash: str = EMPTY_SHA256) -> dict:
    """The headers that sign one request with AWS Signature Version 4 (no
    query string, no body) -- checked against AWS's published example."""
    amz_date = when.astimezone(A.UTC).strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    hdrs = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date,
            **{k.lower(): str(v).strip() for k, v in (extra or {}).items()}}
    names = sorted(hdrs)
    signed = ";".join(names)
    canonical = "\n".join([method, quote(path, safe="/-_.~"), "",
                           "".join(f"{n}:{hdrs[n]}\n" for n in names), signed, payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), day), region), service), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {n: hdrs[n] for n in names if n != "host"}
    out["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, "
                            f"SignedHeaders={signed}, Signature={sig}")
    return out


class Refused(RuntimeError):
    """Massive would not serve a file (both credential orders refused, or no such file)."""


class S3:
    """The flat-files bucket, read-only: HEAD (a file's size) and GET (a file
    to disk). The key pair is tried as given, then swapped, and the order that
    works is kept. Nothing here ever prints or raises with a key in it."""

    def __init__(self, key: str, secret: str, *, endpoint: str = ENDPOINT, region: str = "us-east-1",
                 client=None, clock=lambda: dt.datetime.now(A.UTC)):
        import httpx
        self._pairs = [(key, secret), (secret, key)]
        self.endpoint, self.region, self._clock = endpoint.rstrip("/"), region, clock
        self.host = self.endpoint.split("://", 1)[-1].split("/")[0]
        self._http = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))

    def _url_path(self, key: str) -> str:
        return f"/{BUCKET}/{key}"

    def _send(self, method: str, key: str, stream: bool = False):
        last = None
        for i, (kid, sec) in enumerate(self._pairs):
            headers = sigv4(method, self.host, self._url_path(key), kid, sec, when=self._clock(),
                            region=self.region)
            req = self._http.build_request(method, self.endpoint + self._url_path(key), headers=headers)
            resp = self._http.send(req, stream=stream)
            if resp.status_code != 403:
                if i:
                    self._pairs = [self._pairs[1], self._pairs[0]]     # keep the order that works
                return resp
            last = resp.status_code
            resp.close()
        raise Refused(f"Massive refused both orders of the credentials (HTTP {last}) for {key}")

    def size(self, key: str) -> int | None:
        r = self._send("HEAD", key)
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise Refused(f"HEAD {key}: HTTP {r.status_code}")
        return int(r.headers.get("content-length", 0))

    def download(self, key: str, dest: Path) -> int:
        """GET `key` into `dest` through dest.part, renamed only when whole."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        r = self._send("GET", key, stream=True)
        try:
            if r.status_code == 404:
                raise Refused(f"no such file on Massive: {key}")
            if r.status_code != 200:
                raise Refused(f"GET {key}: HTTP {r.status_code}")
            n = 0
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    n += len(chunk)
                f.flush()
                os.fsync(f.fileno())
            want = r.headers.get("content-length")
            if want is not None and int(want) != n:
                raise Refused(f"GET {key}: {n} bytes of {want}")
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        finally:
            r.close()
        os.replace(part, dest)
        return n


def s3_from_env(client=None) -> S3:
    key, secret = os.environ.get("MASSIVE_S3_KEY"), os.environ.get("MASSIVE_S3_SECRET")
    if not key or not secret:
        raise Refused("MASSIVE_S3_KEY / MASSIVE_S3_SECRET are not set (they are never printed)")
    return S3(key, secret, endpoint=os.environ.get("MASSIVE_S3_ENDPOINT", ENDPOINT),
              region=os.environ.get("MASSIVE_S3_REGION", "us-east-1"), client=client)


# ------------------------------------------------------------------ the raw files
def raw_key(exchange: str, date: dt.date) -> str:
    return f"us_futures_{exchange}/trades_v1/{date:%Y}/{date:%m}/{date.isoformat()}.csv.gz"


def raw_path(raw: Path, exchange: str, date: dt.date) -> Path:
    return raw / exchange / str(date.year) / f"{date.isoformat()}.csv.gz"


def raw_dates(root: str, date: dt.date) -> list[dt.date]:
    """The Massive trade dates holding session `date` of `root`. Classic roots:
    the same date. CME crypto: Massive rolls its trade date at 17:00 ET and files
    the weekend under Monday, so an 18:00 -> 18:00 session also needs the next
    weekday's file (a weekend session only Monday's)."""
    if not T.always_open(root):
        return [date]
    nxt = date + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return [nxt] if date.weekday() >= 5 else [date, nxt]


def price_text(text: str) -> str:
    """Massive's price as research/massive_ticks.py writes it: the shortest
    decimal that is the same float, positional, no trailing zeros
    ("0.000050000" -> "0.00005", "30780.000000000" -> "30780")."""
    s = format(decimal.Decimal(repr(float(text))), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def scan_raw(path: Path, wanted: set) -> dict:
    """{contract key: [archive rows]} for the wanted contracts in one raw file,
    streamed; the columns are named by the file's own header. Counts the rows
    Massive flags as corrections (kept, as the research backfill kept them)."""
    out: dict = {k: [] for k in wanted}
    corrections: dict = {k: 0 for k in wanted}
    try:
        with gzip.open(path, "rt", newline="") as fh:
            rd = csv.reader(fh)
            head = next(rd, None) or []
            ix = {c: i for i, c in enumerate(head)}
            it, its, isq, ipx, isz = (ix["ticker"], ix["timestamp"], ix["sequence_number"],
                                      ix["price"], ix["size"])
            ic = ix.get("correction")
            for r in rd:
                k = C.contract_key(r[it]) if len(r) == len(head) else None
                if k not in out:
                    continue
                ns = int(r[its])
                out[k].append((str(ns // 1_000_000), price_text(r[ipx]), str(int(float(r[isz]))),
                               "", "", "", "", str(int(r[isq])), str(ns)))
                if ic is not None and r[ic] not in ("", "0"):
                    corrections[k] += 1
    except (EOFError, zlib.error, OSError) as e:
        raise Refused(f"{path.name}: not a whole gzip file ({e}) -- delete it and download again") from None
    return {"rows": out, "corrections": corrections}


# ------------------------------------------------------------------ what to fill
def targets(roots, base: Path, now: dt.datetime, *, dates=None, since: dt.date = SINCE,
            include_fetchable: bool = False) -> list[dict]:
    """What to fill: every (root, session) of `dates`, or with dates None every
    session since `since` the coverage check finds missing, or holed, or cut
    short at the open or the close -- once the broker's history no longer has
    that part (include_fetchable: even while it does). Gaps under 2 s between
    broker ticks (missing ids only) are left out: no Massive row can land there."""
    out = []
    for root in roots:
        if dates is not None:
            days = [d for d in dates if T.is_session_day(d, root)]
        else:
            days = [d for d in T.sessions_to_record(now, (now.astimezone(T.ET).date() - since).days, root)
                    if d >= since]
        for d in sorted(days):
            start, end = T.session_bounds(d, root)
            s_ms, e_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
            e = C.session_entry(base, root, d, {}, now)
            contract = symbols.front_month(root, d)
            path = T.archive_path(root, d, contract, base)
            if e["status"] == "missing":
                spans = [(s_ms, e_ms, "the whole session")]
            else:
                holes = e.get("holes", [])
                spans = [(A.ms_of(h["start_utc"]), A.ms_of(h["end_utc"]), f"{h['from_et']}-{h['to_et']} ET")
                         for h in holes]
                if not e.get("head_ok", True) and not any(h["at"] == "open" for h in holes):
                    spans.append((s_ms, s_ms + A.EDGE_MS, "ticks start late"))
                if not e.get("tail_ok", True) and not any(h["at"] == "close" for h in holes):
                    spans.append((e_ms - A.EDGE_MS, e_ms, "ticks stop early"))
            if dates is None:
                spans = [sp for sp in spans if include_fetchable or C.gone(sp[0], now)]
                if not spans:
                    continue
            if e.get("file"):                              # the archive file that holds it now
                name = Path(e["file"]).name
                contract = name[len(d.isoformat()) + 1:].split(".")[0]
                path = T.archive_path(root, d, contract, base)   # (live-only: the file the merge creates)
            out.append({"root": root, "date": d, "contract": contract, "path": path,
                        "status": e["status"], "start": start, "end": end,
                        "what": [sp[2] for sp in spans] or ["any stretch >= 2 s without a broker tick"],
                        "raw": [(EXCHANGE[root], rd) for rd in raw_dates(root, d)]})
    return out


def _mb(n) -> str:
    return f"{n / 1e6:,.1f} MB"


def plan_downloads(tg: list[dict], raw: Path, s3: S3 | None) -> list[dict]:
    """Each raw file the targets need, once: on disk already, or its size on
    Massive (a HEAD request; None without credentials, or if Massive has no such
    file -- e.g. a trade date not published yet)."""
    out, seen = [], set()
    for t in tg:
        for ex, d in t["raw"]:
            if (ex, d) in seen:
                continue
            seen.add((ex, d))
            p = raw_path(raw, ex, d)
            if p.exists():
                out.append({"exchange": ex, "date": d, "path": p, "on_disk": True, "bytes": p.stat().st_size})
            else:
                size = s3.size(raw_key(ex, d)) if s3 is not None else None
                out.append({"exchange": ex, "date": d, "path": p, "on_disk": False, "bytes": size,
                            "on_massive": None if s3 is None else size is not None})
    return out


def describe(tg: list[dict], dl: list[dict], base: Path) -> list[str]:
    lines = []
    for t in tg:
        verb = "new file" if not t["path"].exists() and t["status"] == "missing" else "merge into"
        lines.append(f"  {t['root']:<4}{t['date']} {t['contract']:<7}{verb} "
                     f"{t['path'].relative_to(base)}: {', '.join(t['what'])}")
    for d in dl:
        state = ("on disk" if d["on_disk"] else "to download" if d.get("on_massive")
                 else "NOT on Massive (not published yet?)" if d.get("on_massive") is False
                 else "to download, size unknown without credentials")
        size = f", {_mb(d['bytes'])}" if d["bytes"] is not None else ""
        lines.append(f"  raw {d['exchange']:<6}{d['date']}{size} -- {state}")
    get = [d for d in dl if not d["on_disk"] and d.get("on_massive") is not False]
    unknown = sum(1 for d in get if d["bytes"] is None)
    absent = sum(1 for d in dl if d.get("on_massive") is False)
    lines.append(f"  total: {len(tg)} session file(s); raw files: {len(dl) - len(get) - absent} on disk, "
                 f"{len(get)} to download ({_mb(sum(d['bytes'] or 0 for d in get))}"
                 + (f" + {unknown} of unknown size" if unknown else "") + ")"
                 + (f", {absent} not on Massive" if absent else ""))
    return lines


# ------------------------------------------------------------------ the fill
def fill(roots, base: Path, now: dt.datetime, *, dates=None, since: dt.date = SINCE,
         include_fetchable: bool = False, dry_run: bool = False, raw: Path = RAW,
         s3: S3 | None = None) -> list[dict]:
    """The command. Returns the manifests written (dry run: none)."""
    tg = targets(roots, base, now, dates=dates, since=since, include_fetchable=include_fetchable)
    if not tg:
        log("nothing to fill")
        return []
    if s3 is None:
        try:
            s3 = s3_from_env()
        except Refused as e:                        # fine as long as every raw file is on disk
            log(f"{e} -- files not on disk can be neither sized nor downloaded")
    dl = plan_downloads(tg, raw, s3)
    head = "DRY RUN, nothing downloaded or written" if dry_run else "filling"
    for line in [f"{head}:"] + describe(tg, dl, base):
        T.log(line)
    if dry_run:
        return []
    for d in dl:
        if not d["on_disk"] and d.get("on_massive") is not False:
            if s3 is None:
                raise Refused(f"{d['exchange']} {d['date']} must be downloaded: set MASSIVE_S3_KEY / "
                              "MASSIVE_S3_SECRET")
            log(f"downloading {d['exchange']} {d['date']} ({_mb(d['bytes'] or 0)})")
            n = s3.download(raw_key(d["exchange"], d["date"]), d["path"])
            log(f"  {d['path'].name}: {_mb(n)}")
    written = []
    by_file: dict = {}
    for t in tg:
        need = [(ex, d) for ex, d in t["raw"] if raw_path(raw, ex, d).exists()]
        if len(need) < len(t["raw"]):
            log(f"{t['root']} {t['date']} {t['contract']}: a raw file is not on Massive yet — skipped")
            continue
        k = C.contract_key(t["contract"])
        rows, corr, files = [], 0, []
        s_ms, e_ms = int(t["start"].timestamp() * 1000), int(t["end"].timestamp() * 1000)
        for ex, d in need:
            key = (ex, d)
            if key not in by_file:
                wanted = {C.contract_key(x["contract"]) for x in tg if (ex, d) in x["raw"]}
                by_file[key] = scan_raw(raw_path(raw, ex, d), wanted)
            got = by_file[key]
            rows += [r for r in got["rows"][k] if s_ms <= int(r[A.TS]) <= e_ms]
            corr += got["corrections"][k]
            files.append(f"{ex}/{d.isoformat()}.csv.gz")
        rows.sort(key=lambda r: (int(r[A.TSNS]), int(r[A.ID])))
        over = now >= t["end"] + dt.timedelta(minutes=T.SESSION_GRACE_MIN)
        try:
            man = A.merge_session(t["path"], root=t["root"], contract=t["contract"], date=t["date"],
                                  start=t["start"], end=t["end"], include_live=over,
                                  massive_new=rows, only_if_added=True,
                                  massive_source={"kind": "massive", "files": files, "offered": len(rows),
                                                  "correction_rows": corr})
        except A.MergeRefused as e:
            log(f"{t['root']} {t['date']} {t['contract']}: MERGE REFUSED, left as it was — {e}")
            continue
        if man is None:
            log(f"{t['root']} {t['date']} {t['contract']}: Massive has nothing the archive lacks "
                f"({len(rows):,} rows offered, {', '.join(t['what'])})")
            continue
        cov = man["coverage"]
        log(f"{t['root']} {t['date']} {t['contract']}: +{man['merge'].get('massive_added', 0):,} Massive rows "
            f"— file {man['ticks']:,} ticks, " + ("complete" if man["complete"] else
                                                   f"still {cov['hole_hours']:g} hole-hours"))
        written.append(man)
    return written
