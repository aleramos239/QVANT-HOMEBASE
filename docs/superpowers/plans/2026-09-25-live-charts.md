# Live Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Charts tab for homebase: multi-chart layouts on live broker ticks (any time/tick/volume/range bars), indicators and order flow (footprint, delta, cumulative delta, big prints, volume profile), running as its own process so it can never delay an order.

**Architecture:** New package `homebase/charts/`, run as `python -m homebase.charts` on port 8852 (own launchd job). One md socket with one Tick subscription per root feeds a recorder (today's ticks on disk) and a hub. Pure modules (`tick`, `bars`, `studies`) turn ticks into bars and indicator values. The hub shares one stream per (root, bar type) across all charts and pushes coalesced updates (≤ 4/s) over a websocket. A browser page (Lightweight Charts v5 plus canvas primitives) only draws. Past sessions come from `~/futures_ticks` (zero broker cost) through a 1-minute bar cache.

**Tech Stack:** Python 3.14, FastAPI/uvicorn/websockets (already in `requirements.txt`), stdlib only (no numpy), pytest; vanilla JS + Lightweight Charts 5.2.1 (vendored), `shadcn.css`.

**Spec:** `docs/superpowers/specs/2026-09-25-live-charts-design.md`

## Global Constraints

- The trading process (`homebase/server.py`, `engine.py`, `timer.py`, `feed.py`) is NOT modified, except for one "Charts" link in `homebase/static/index.html` (Task 15).
- Chart process: `python -m homebase.charts`, host `127.0.0.1`, port **8852**; launchd label `com.ramosquant.homebase-charts`.
- No new Python dependencies. Nothing in `homebase/charts/` may place, modify or cancel an order.
- md budget: 180 chart requests/hour/login. This process spends at most **60/hour** on gap refills and never refills **09:20–09:35 ET**; it subscribes once per root per connection; reconnects back off 5 s → 300 s.
- Sessions: 18:00 ET (D-1) → 17:00 ET (D). No bar spans two sessions.
- Live file: `~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz`, columns `ts_ms,price,size,bid,ask,bid_size,ask_size,id` (= `homebase.ticks.FIELDS`). Gaps: `<date>_<contract>.gaps.json`.
- Per session ONE file: complete archive > live > incomplete archive; on a roll day the contract with the most ticks wins.
- Aggressor side: sane quote (bid ≤ ask) and price ≥ ask → buy, price ≤ bid → sell; otherwise the tick rule.
- Sorting tick rows: Python's `sorted`/`list.sort` only (stable). Never pandas default sort.
- Wire times: `t` = ET wall-clock seconds (the axis displays ET), `ms` = real epoch ms.
- Tests run with `.venv/bin/python -m pytest -q` from the repo root; the existing 124 tests must stay green.
- Commit after every task, on branch `feat/charts`, ending the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `homebase/ticks.py` (modify) | `md_token(prefer_live=True)` / `connect_md(prefer_live=True)`: pick which login's md token |
| `homebase/charts/__init__.py` | constants: `PORT`, `DEFAULT_ROOTS`, `MD_ENV` |
| `homebase/charts/session.py` | session date/range, RTH test, ET wall-clock seconds |
| `homebase/charts/tick.py` | `Tick`, `SideClassifier`, `from_row` |
| `homebase/charts/store.py` | read archive/live files, choose one per session, classify |
| `homebase/charts/bars.py` | `BarSpec`, `Bar` (+footprint), `BarBuilder`, `build`, `resample` |
| `homebase/charts/studies.py` | incremental SMA/EMA/VWMA/VWAP/ADX/CumDelta/Levels, `Profile`, `make` |
| `homebase/charts/history.py` | past-session bars: 1-minute pickle cache + memo |
| `homebase/charts/recorder.py` | `LiveRecorder` (append/dedupe/flush/gaps) + `refill()` |
| `homebase/charts/tickfeed.py` | `TickFeed`: md socket, subscriptions, reconnect, budget |
| `homebase/charts/replay.py` | `ReplayFeed`: archived session through the live path |
| `homebase/charts/hub.py` | `Stream`, `Hub`: shared live streams, fan-out, coalescing |
| `homebase/charts/server.py` | FastAPI app: page, `/ws`, layouts, status, pump, refill wiring |
| `homebase/charts/__main__.py` | CLI entry |
| `homebase/static/charts.html` | page shell |
| `homebase/static/charts/app.js` | grid, cells, websocket, series drawing |
| `homebase/static/charts/primitives.js` | footprint / profile / gap canvas layers |
| `homebase/static/vendor/lightweight-charts-5.2.1.js` | vendored LWC v5 |
| `deploy/com.ramosquant.homebase-charts.plist.template`, `deploy/install.sh` | launchd |
| `tests/charts_util.py` + `tests/test_charts_*.py` | tests |

---

### Task 1: Session maths, ticks, side classifier, md login choice

**Files:**
- Create: `homebase/charts/__init__.py`, `homebase/charts/session.py`, `homebase/charts/tick.py`, `tests/charts_util.py`, `tests/test_charts_tick.py`
- Modify: `homebase/ticks.py` (functions `md_token`, `connect_md`)

**Interfaces:**
- Produces: `session_date(ts_ms) -> date`, `session_range_ms(d) -> (int, int)`, `is_rth(ts_ms, session_iso) -> bool`, `et_wall_s(ts_ms) -> int`, `ET`; `Tick(ts_ms, price, size, side, id=0)` NamedTuple, `BUY=1`, `SELL=-1`, `SideClassifier(last_price=None, last_side=BUY).side(price, bid, ask) -> int`, `from_row(row: dict, clf) -> Tick`; `ticks.md_token(prefer_live=True)`, `ticks.connect_md(prefer_live=True)`; test helpers `D`, `rows()`, `write_gz()`, `write_archive()`, `session_ms()`.

- [ ] **Step 1: Write the test helpers**

`tests/charts_util.py`:
```python
"""Synthetic tick sessions for the chart-engine tests (no network, no real archive)."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
D = dt.date(2026, 9, 24)                     # a Thursday session
FIELDS = ["ts_ms", "price", "size", "bid", "ask", "bid_size", "ask_size", "id"]


def session_ms(d: dt.date, hh: int, mm: int, ss: int = 0) -> int:
    """Epoch ms of an ET wall time in session d (hh >= 18 is the evening before)."""
    day = d - dt.timedelta(days=1) if hh >= 18 else d
    return int(dt.datetime.combine(day, dt.time(hh, mm, ss), ET).timestamp() * 1000)


def rows(start_ms: int, prices, step_ms: int = 1000, size=1, spread: float = 0.25,
         first_id: int = 1, sides=None) -> list[dict]:
    """One trade per price, step_ms apart. sides[i] = +1 trades at the ask,
    -1 at the bid (default: at the ask). size: int or a list per trade."""
    out = []
    for i, p in enumerate(prices):
        s = sides[i] if sides else 1
        bid, ask = (p - spread, p) if s > 0 else (p, p + spread)
        out.append({"ts_ms": start_ms + i * step_ms, "price": p,
                    "size": size[i] if isinstance(size, list) else size,
                    "bid": bid, "ask": ask, "bid_size": 5, "ask_size": 5, "id": first_id + i})
    return out


def write_gz(path: Path, rows_: list[dict], fields=FIELDS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows_)
    path.write_bytes(gzip.compress(buf.getvalue().encode()))
    return path


def write_archive(base: Path, root: str, d: dt.date, contract: str, rows_: list[dict],
                  complete: bool = True, bid_ask: bool = True) -> Path:
    p = Path(base) / root / str(d.year) / f"{d.isoformat()}_{contract}.csv.gz"
    write_gz(p, rows_)
    man = {"root": root, "contract": contract, "session_date": d.isoformat(),
           "ticks": len(rows_), "complete": complete}
    if not bid_ask:
        man["bid_ask"] = False
    p.with_name(p.name[:-len(".csv.gz")] + ".json").write_text(json.dumps(man))
    return p
```

- [ ] **Step 2: Write the failing tests**

`tests/test_charts_tick.py`:
```python
"""Chart engine basics: session maths, aggressor side, md login choice."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from homebase import ticks as T
from homebase.charts.session import et_wall_s, is_rth, session_date, session_range_ms
from homebase.charts.tick import BUY, SELL, SideClassifier, Tick, from_row
from tests.charts_util import ET, session_ms


def ms(y, mo, d, h, mi, s=0, us=0):
    return int(dt.datetime(y, mo, d, h, mi, s, us, ET).timestamp() * 1000)


def test_session_date_rolls_at_18_et_and_skips_weekends():
    assert session_date(ms(2026, 9, 20, 18, 0, 0, 10000)) == dt.date(2026, 9, 21)  # Sun open -> Mon
    assert session_date(ms(2026, 9, 21, 16, 59)) == dt.date(2026, 9, 21)
    assert session_date(ms(2026, 9, 21, 18, 0)) == dt.date(2026, 9, 22)
    assert session_date(ms(2026, 9, 25, 16, 0)) == dt.date(2026, 9, 25)
    s0, s1 = session_range_ms(dt.date(2026, 9, 21))
    assert (s0, s1) == (ms(2026, 9, 20, 18, 0), ms(2026, 9, 21, 17, 0))


def test_is_rth_and_et_wall_clock():
    assert not is_rth(ms(2026, 9, 23, 20, 0), "2026-09-24")     # the evening before
    assert not is_rth(ms(2026, 9, 24, 9, 29), "2026-09-24")
    assert is_rth(ms(2026, 9, 24, 9, 30), "2026-09-24")
    want = int(dt.datetime(2026, 9, 24, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    assert et_wall_s(ms(2026, 9, 24, 9, 30)) == want
    assert et_wall_s(session_ms(dt.date(2026, 9, 24), 9, 30)) == want


def test_side_from_a_sane_quote():
    c = SideClassifier()
    assert c.side(100.25, 100.0, 100.25) == BUY          # at the ask
    assert c.side(100.0, 100.0, 100.25) == SELL          # at the bid
    assert c.side(100.5, 100.0, 100.25) == BUY           # through the ask


def test_side_falls_back_to_the_tick_rule():
    c = SideClassifier()
    assert c.side(100.0, None, None) == BUY              # no history: buy
    assert c.side(99.75, None, None) == SELL             # down-tick
    assert c.side(99.75, None, None) == SELL             # unchanged: previous side
    assert c.side(100.0, 100.5, 99.5) == BUY             # crossed quote ignored -> up-tick
    assert c.side(100.0, 99.75, 100.25) == BUY           # inside the spread, unchanged -> previous


def test_from_row_parses_blank_quotes_and_strings():
    t = from_row({"ts_ms": "5", "price": "10", "size": "3", "bid": "", "ask": "", "id": "7"},
                 SideClassifier())
    assert t == Tick(5, 10.0, 3, BUY, 7)


def test_md_token_prefers_the_requested_login(tmp_path, monkeypatch):
    cfg = SimpleNamespace(accounts={"demo1": SimpleNamespace(live=False),
                                    "live1": SimpleNamespace(live=True)})
    monkeypatch.setattr(T.config_mod, "load", lambda: cfg)
    monkeypatch.setattr(T, "state_dir", lambda: tmp_path)
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    for aid in ("demo1", "live1"):
        (tmp_path / f"{aid}.tokens.json").write_text(
            json.dumps({"md_access_token": f"tok-{aid}", "expiration_time": exp}))
    assert T.md_token() == ("tok-live1", "live")
    assert T.md_token(prefer_live=False) == ("tok-demo1", "demo")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_tick.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts'`

- [ ] **Step 4: Implement**

`homebase/charts/__init__.py`:
```python
"""Live charts: the chart half of the homebase terminal (Build 1).

Runs as its OWN process (python -m homebase.charts, port 8852) so chart work
can never delay an order or crash the trading engine. Nothing in this
package places, modifies or cancels orders.
Spec: docs/superpowers/specs/2026-09-25-live-charts-design.md
"""
from __future__ import annotations

import os

PORT = 8852
DEFAULT_ROOTS = ("NQ", "ES", "YM")
# whose md socket feeds the charts: "demo" = the Apex eval login (default;
# confirmed by the Task 14 spike), "live" = the live account's login
MD_ENV = os.environ.get("HOMEBASE_CHARTS_MD", "demo")
```

`homebase/charts/session.py`:
```python
"""CME session maths for the chart engine (and later the backtester).

Session D runs 18:00 ET on D-1 -> 17:00 ET on D (Monday's opens Sunday
18:00) — the convention of homebase.ticks.session_bounds, reused here.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..ticks import session_bounds

ET = ZoneInfo("America/New_York")
RTH_OPEN = dt.time(9, 30)
_DAY = dt.timedelta(days=1)


def session_date(ts_ms: int) -> dt.date:
    """The session a trade at ts_ms belongs to."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, ET)
    d = t.date() + _DAY if t.time() >= dt.time(18, 0) else t.date()
    while d.weekday() >= 5:
        d += _DAY
    return d


@lru_cache(maxsize=4096)
def session_range_ms(d: dt.date) -> tuple[int, int]:
    """(open, close) of session d in epoch ms."""
    s, e = session_bounds(d)
    return int(s.timestamp() * 1000), int(e.timestamp() * 1000)


def is_rth(ts_ms: int, session: str) -> bool:
    """True from 09:30 ET on the session's own calendar day."""
    t = dt.datetime.fromtimestamp(ts_ms / 1000, ET)
    return t.date().isoformat() == session and t.time() >= RTH_OPEN


@lru_cache(maxsize=65536)
def _et_offset_s(hour: int) -> int:
    return int(dt.datetime.fromtimestamp(hour * 3600, ET).utcoffset().total_seconds())


def et_wall_s(ts_ms: int) -> int:
    """ts as ET wall-clock seconds — for a chart axis that displays UTC."""
    s = ts_ms // 1000
    return s + _et_offset_s(s // 3600)
```

`homebase/charts/tick.py`:
```python
"""A trade, and which side started it."""
from __future__ import annotations

from typing import NamedTuple, Optional

BUY, SELL = 1, -1


class Tick(NamedTuple):
    ts_ms: int
    price: float
    size: int
    side: int          # BUY: lifted the ask · SELL: hit the bid
    id: int = 0


def _num(v) -> Optional[float]:
    return None if v is None or v == "" else float(v)


class SideClassifier:
    """Aggressor side per trade. With a sane quote (bid <= ask): at/above the
    ask = buy, at/below the bid = sell. Inside the spread, no quote, or a
    crossed quote (the feed does send bid > ask) -> tick rule: up-tick buy,
    down-tick sell, unchanged -> the previous side. Sequential: feed trades
    in time order; resume from (last_price, last_side) to continue a tape."""

    def __init__(self, last_price: Optional[float] = None, last_side: int = BUY):
        self.last_price = last_price
        self.last_side = last_side

    def side(self, price: float, bid: Optional[float], ask: Optional[float]) -> int:
        if bid is not None and ask is not None and bid <= ask and (price >= ask or price <= bid):
            s = BUY if price >= ask else SELL
        elif self.last_price is None or price == self.last_price:
            s = self.last_side
        else:
            s = BUY if price > self.last_price else SELL
        self.last_price, self.last_side = price, s
        return s


def from_row(row: dict, clf: SideClassifier) -> Tick:
    """A raw tick row (archive CSV strings or the feed's numbers) -> Tick."""
    price = float(row["price"])
    return Tick(int(row["ts_ms"]), price, int(row["size"]),
                clf.side(price, _num(row.get("bid")), _num(row.get("ask"))),
                int(row.get("id") or 0))
```

In `homebase/ticks.py`, replace the `md_token` signature/docstring/sort line and `connect_md`:
```python
def md_token(prefer_live: bool = True) -> tuple[str, str]:
    """(md token, env) from an account the desk already logged in — never a
    login of its own (logins are rate-limited and precious). prefer_live
    (the default, for bulk paging) takes the LIVE login first so the demo
    login the 9:30 feed rides stays clean; the chart service may prefer the
    demo (Apex eval) login instead."""
    cfg = config_mod.load()
    now = dt.datetime.now(dt.timezone.utc)
    for aid, a in sorted(cfg.accounts.items(), key=lambda kv: kv[1].live != prefer_live):
```
(the rest of the loop body is unchanged), and:
```python
async def connect_md(prefer_live: bool = True) -> TradovateWS:
    tok, env = md_token(prefer_live)
```
(rest unchanged).

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_tick.py tests/test_ticks.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add homebase/charts tests/charts_util.py tests/test_charts_tick.py homebase/ticks.py
git commit -m "feat(charts): session maths, ticks, aggressor-side classifier; md_token can prefer either login

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Tick store

**Files:**
- Create: `homebase/charts/store.py`, `tests/test_charts_store.py`

**Interfaces:**
- Consumes: `Tick`, `SideClassifier` (Task 1).
- Produces: `ARCHIVE`, `LIVE_SUFFIX`, `SessionFile(path, contract, live, complete, ticks, bid_ask)`, `Session(root, date, contract, source, ticks, bid_ask, gaps)`, `read_table(path) -> (header, recs)`, `gaps_path(path) -> Path`, `ticks_from_table(header, recs, live=False) -> (list[Tick], bool)`, `TickStore(base).files/pick/sessions/load/gaps`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_store.py`:
```python
"""Tick store: multi-member/torn gzip, one file per session, live re-sort."""
from __future__ import annotations

import datetime as dt
import gzip

from homebase.charts.store import TickStore, gaps_path, read_table
from tests.charts_util import D, rows, session_ms, write_archive, write_gz


def test_read_table_survives_multi_member_and_a_torn_tail(tmp_path):
    p = tmp_path / "x.csv.gz"
    p.write_bytes(gzip.compress(b"ts_ms,price\n1,10\n") + gzip.compress(b"2,11\n")
                  + gzip.compress(b"3,12\n4,13\n")[:-9])
    header, recs = read_table(p)
    assert header == ["ts_ms", "price"]
    assert recs[:2] == [["1", "10"], ["2", "11"]]
    assert all(len(r) == 2 for r in recs)


def test_pick_prefers_complete_archive_then_live_then_partial(tmp_path):
    r = rows(session_ms(D, 18, 0), [100.0, 100.25])
    write_archive(tmp_path, "NQ", D, "NQZ6", r, complete=False)
    st = TickStore(tmp_path)
    assert st.pick("NQ", D).live is False
    write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", r)
    assert st.pick("NQ", D).live is True
    write_archive(tmp_path, "NQ", D, "NQZ6", r, complete=True)
    f = st.pick("NQ", D)
    assert f.live is False and f.complete


def test_roll_day_picks_the_busiest_contract(tmp_path):
    write_archive(tmp_path, "NQ", D, "NQU6", rows(session_ms(D, 9, 30), [1.0, 2.0]))
    write_archive(tmp_path, "NQ", D, "NQZ6", rows(session_ms(D, 9, 30), [1.0] * 5))
    assert TickStore(tmp_path).pick("NQ", D).contract == "NQZ6"


def test_load_live_sorts_dedupes_and_reads_gaps(tmp_path):
    r = rows(session_ms(D, 9, 30), [100.0, 100.25, 100.5])
    live = write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", [r[2], r[0], r[1], r[0]])
    gaps_path(live).write_text("[[1, 2]]")
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3]
    assert s.source == "live" and s.bid_ask and s.gaps == [[1, 2]] and s.contract == "NQZ6"


def test_massive_file_without_quotes_is_flagged(tmp_path):
    r = rows(session_ms(D, 9, 30), [100.0, 100.25, 100.0])
    for x in r:
        x["bid"] = x["ask"] = ""
    write_archive(tmp_path, "NQ", D, "NQZ6", r, bid_ask=False)
    st = TickStore(tmp_path)
    s = st.load("NQ", D)
    assert s.bid_ask is False and s.source == "archive" and s.gaps == []
    assert [t.side for t in s.ticks] == [1, 1, -1]          # tick rule
    assert st.pick("NQ", D).bid_ask is False


def test_sessions_lists_every_dated_file(tmp_path):
    p = D - dt.timedelta(days=1)
    write_archive(tmp_path, "NQ", p, "NQZ6", rows(session_ms(p, 9, 30), [1.0]))
    write_gz(tmp_path / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz", rows(session_ms(D, 9, 30), [1.0]))
    assert TickStore(tmp_path).sessions("NQ") == [p, D]
    assert TickStore(tmp_path).load("ES", D) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.store'`

- [ ] **Step 3: Implement**

`homebase/charts/store.py`:
```python
"""One read API over the tick files, for charts (and later backtests).

Two kinds of file live side by side under ~/futures_ticks/<ROOT>/<YYYY>/:
  <date>_<contract>.csv.gz       the nightly archive (manifest .json beside
                                 it; Massive backfills carry no bid/ask)
  <date>_<contract>.live.csv.gz  the chart service's own live recording
                                 (+ <date>_<contract>.gaps.json)

Per session ONE file is used, never a merge (Massive and Tradovate ids are
different spaces): complete archive > live > incomplete archive; on a roll
day the contract with the most ticks wins.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .tick import SideClassifier, Tick

ARCHIVE = Path.home() / "futures_ticks"
LIVE_SUFFIX = ".live.csv.gz"


@dataclass(frozen=True)
class SessionFile:
    path: Path
    contract: str
    live: bool
    complete: bool
    ticks: int            # manifest count (archive) or file size (live): ranking only
    bid_ask: bool         # False for a Massive backfill (sides are tick-rule only)


@dataclass
class Session:
    root: str
    date: dt.date
    contract: str
    source: str                            # "archive" | "live"
    ticks: list[Tick]
    bid_ask: bool                          # False -> buy/sell split is approximate
    gaps: list = field(default_factory=list)   # [[start_ms, end_ms], ...]


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    """(header, records) of a gzip CSV that may hold several gzip members
    (the live recorder appends one per flush) and may end in a member torn
    by a crash — the torn tail is dropped, never raised."""
    header: list[str] = []
    recs: list[list[str]] = []
    try:
        with gzip.open(path, "rt", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd, None) or []
            n = len(header)
            for rec in rd:
                if len(rec) == n and rec[0] != header[0]:
                    recs.append(rec)
    except (EOFError, zlib.error, OSError):
        pass
    return header, recs


def gaps_path(path: Path) -> Path:
    stem = path.name.replace(LIVE_SUFFIX, "").replace(".csv.gz", "")
    return path.with_name(stem + ".gaps.json")


def ticks_from_table(header: list[str], recs: list[list[str]],
                     live: bool = False) -> tuple[list[Tick], bool]:
    """Classified ticks + whether the file carries quotes. A live file is
    deduped by id and re-sorted by (time, id) first: a gap refill appends
    OLDER ticks after newer ones. (list.sort is stable.)"""
    if not header:
        return [], False
    ix = {k: i for i, k in enumerate(header)}
    it, ip, isz = ix["ts_ms"], ix["price"], ix["size"]
    ib, ia, iid = ix.get("bid"), ix.get("ask"), ix.get("id")
    if live and iid is not None:
        seen: set[str] = set()
        uniq = []
        for r in recs:
            k = r[iid]
            if k and k in seen:
                continue
            seen.add(k)
            uniq.append(r)
        recs = sorted(uniq, key=lambda r: (int(r[it]), int(r[iid] or 0)))
    clf = SideClassifier()
    out: list[Tick] = []
    quotes = False
    for r in recs:
        b = r[ib] if ib is not None else ""
        a = r[ia] if ia is not None else ""
        if b and a:
            quotes = True
        p = float(r[ip])
        out.append(Tick(int(r[it]), p, int(r[isz]),
                        clf.side(p, float(b) if b else None, float(a) if a else None),
                        int(r[iid]) if iid is not None and r[iid] else 0))
    return out, quotes


class TickStore:
    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)

    def files(self, root: str, d: dt.date) -> list[SessionFile]:
        tag = d.isoformat()
        out = []
        for p in sorted((self.base / root / str(d.year)).glob(f"{tag}_*.csv.gz")):
            contract = p.name[len(tag) + 1:].split(".")[0]
            if p.name.endswith(LIVE_SUFFIX):
                out.append(SessionFile(p, contract, True, False, p.stat().st_size, True))
                continue
            man: dict = {}
            try:
                man = json.loads(p.with_name(p.name[:-len(".csv.gz")] + ".json").read_text())
            except (OSError, ValueError):
                pass
            out.append(SessionFile(p, contract, False, bool(man.get("complete")),
                                   int(man.get("ticks") or p.stat().st_size),
                                   bool(man.get("bid_ask", True))))
        return out

    def pick(self, root: str, d: dt.date) -> SessionFile | None:
        fs = self.files(root, d)
        for group in ([f for f in fs if not f.live and f.complete],
                      [f for f in fs if f.live],
                      [f for f in fs if not f.live]):
            if group:
                return max(group, key=lambda f: f.ticks)
        return None

    def sessions(self, root: str) -> list[dt.date]:
        ds = set()
        for p in (self.base / root).glob("*/*.csv.gz"):
            try:
                ds.add(dt.date.fromisoformat(p.name[:10]))
            except ValueError:
                continue
        return sorted(ds)

    def gaps(self, f: SessionFile) -> list:
        if not f.live:
            return []
        try:
            return json.loads(gaps_path(f.path).read_text())
        except (OSError, ValueError):
            return []

    def load(self, root: str, d: dt.date) -> Session | None:
        f = self.pick(root, d)
        if f is None:
            return None
        header, recs = read_table(f.path)
        ticks, quotes = ticks_from_table(header, recs, live=f.live)
        return Session(root, d, f.contract, "live" if f.live else "archive",
                       ticks, quotes, self.gaps(f))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/store.py tests/test_charts_store.py
git commit -m "feat(charts): tick store — one file per session, torn-tail-safe reader, live re-sort

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Bar builder (all bar types, footprint, resample)

**Files:**
- Create: `homebase/charts/bars.py`, `tests/test_charts_bars.py`

**Interfaces:**
- Consumes: `Tick`, `BUY`, `SELL`; `session_date`, `session_range_ms`, `et_wall_s`.
- Produces: `KINDS`, `BIG_MIN=10`, `BarSpec(kind, size)` with `.parse(key)`, `.key`, `.from_minutes`; `Bar` (fields `t, session, o, h, l, c, v, buy, sell, n, pv, p2v, fp, big, closed`; `.delta`, `.add(tk, tick_size)`, `.copy()`, `.merge(other)`, `.wire(tick_size, fp=True)`); `BarBuilder(spec, tick_size)` with `.cur`, `.add(tk) -> list[Bar]`, `.on_clock(now_ms) -> list[Bar]`; `build(ticks, spec, tick_size) -> (closed, cur)`; `resample(minutes, spec) -> list[Bar]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_bars.py`:
```python
"""Bars: every type, footprint, session anchoring, live == bulk, resample == direct."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.charts.bars import BarBuilder, BarSpec, build, resample
from homebase.charts.tick import BUY, SELL, Tick
from tests.charts_util import D, session_ms

TS = 0.25
M = session_ms(D, 9, 30)


def T(ms, p, q=1, side=BUY, i=0):
    return Tick(ms, p, q, side, i)


def _k(b):
    return (b.t, b.session, b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, b.n,
            round(b.pv, 6), round(b.p2v, 4), b.fp, b.big)


def test_spec_parse():
    assert BarSpec.parse("time:60") == BarSpec("time", 60)
    assert BarSpec.parse("tick:500").key == "tick:500"
    assert BarSpec("time", 300).from_minutes and not BarSpec("time", 30).from_minutes
    for bad in ("time", "time:0", "bogus:5", "tick:x"):
        with pytest.raises(ValueError):
            BarSpec.parse(bad)


def test_time_bars_footprint_and_big_prints():
    ticks = [T(M, 100.0), T(M + 20_000, 100.5, 2, SELL), T(M + 61_000, 101.0, 12)]
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    b = closed[0]
    assert b.t == M and b.closed and not cur.closed
    assert (b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, b.delta) == (100.0, 100.5, 100.0, 100.5, 3, 1, 2, -1)
    assert b.fp == {400: [0, 1], 402: [2, 0]}
    assert b.pv == 100.0 + 201.0
    assert cur.t == M + 60_000 and cur.big == [[M + 61_000, 101.0, 12, BUY]]


def test_four_hour_bars_anchor_at_the_18_et_open():
    t0 = session_ms(D, 18, 0)
    closed, cur = build([T(t0 + 1, 1.0), T(session_ms(D, 22, 0) + 5, 2.0)], BarSpec("time", 14400), TS)
    assert closed[0].t == t0 and cur.t == session_ms(D, 22, 0)


def test_no_bar_spans_two_sessions():
    nxt = D + dt.timedelta(days=1)
    closed, cur = build([T(session_ms(D, 16, 59, 59), 1.0), T(session_ms(nxt, 18, 0), 2.0)],
                        BarSpec("time", 86400), TS)
    assert [x.session for x in closed] == [D.isoformat()] and cur.session == nxt.isoformat()


def test_tick_volume_and_range_bars():
    ticks = [T(M + i, 100 + 0.25 * i, q=3) for i in range(10)]
    closed, cur = build(ticks, BarSpec("tick", 4), TS)
    assert [b.n for b in closed] == [4, 4] and cur.n == 2
    closed, cur = build(ticks, BarSpec("volume", 7), TS)
    assert [b.v for b in closed] == [9, 9, 9] and cur.v == 3
    closed, cur = build(ticks, BarSpec("range", 3), TS)
    assert [(b.l, b.h) for b in closed] == [(100.0, 100.75), (101.0, 101.75)]
    assert (cur.l, cur.h) == (102.0, 102.25)


def test_live_with_a_clock_equals_the_bulk_build():
    ticks = [T(M + i * 7_000, 100 + (i % 5) * 0.25, 1 + i % 3, BUY if i % 2 else SELL, i)
             for i in range(60)]
    spec = BarSpec("time", 30)
    bulk, bulk_cur = build(ticks, spec, TS)
    bb, live = BarBuilder(spec, TS), []
    for tk in ticks:
        live += bb.on_clock(tk.ts_ms - 1)      # the pump's clock, just behind each tick
        live += bb.add(tk)
    assert live == bulk and bb.cur == bulk_cur


def test_a_late_tick_after_a_clock_close_never_duplicates_a_bar():
    bb = BarBuilder(BarSpec("time", 60), TS)
    bb.add(T(M + 1_000, 100.0))
    assert len(bb.on_clock(M + 61_500)) == 1
    bb.add(T(M + 59_000, 100.25))              # late print for the closed minute
    assert bb.cur.t == M + 60_000


def test_on_clock_leaves_non_time_bars_alone():
    bb = BarBuilder(BarSpec("tick", 5), TS)
    bb.add(T(M, 100.0))
    assert bb.on_clock(M + 10 ** 9) == [] and bb.cur is not None


def test_resample_equals_a_direct_build():
    ticks = [T(M + i * 13_000, 100 + (i % 7) * 0.25, 1 + i % 4, BUY if i % 3 else SELL, i)
             for i in range(400)]
    minutes, cur = build(ticks, BarSpec("time", 60), TS)
    cur.closed = True
    minutes.append(cur)
    for size in (300, 900, 3600):
        direct, dcur = build(ticks, BarSpec("time", size), TS)
        rs = resample(minutes, BarSpec("time", size))
        assert [_k(b) for b in rs] == [_k(b) for b in direct + [dcur]]
    assert resample(minutes, BarSpec("time", 60)) is minutes


def test_resample_does_not_mutate_its_input():
    ticks = [T(M + i * 20_000, 100.0 + 0.25 * (i % 3), 2, BUY, i) for i in range(12)]
    minutes, cur = build(ticks, BarSpec("time", 60), TS)
    before = [_k(b) for b in minutes]
    resample(minutes, BarSpec("time", 300))
    assert [_k(b) for b in minutes] == before


def test_wire_is_et_wall_clock_with_priced_footprint():
    closed, _ = build([T(M, 100.0, 2, SELL), T(M + 1, 100.25, 3)], BarSpec("tick", 2), TS)
    w = closed[0].wire(TS)
    assert w["t"] == int(dt.datetime(2026, 9, 24, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    assert w["ms"] == M and w["s"] == D.isoformat()
    assert w["fp"] == [[100.0, 2, 0], [100.25, 0, 3]] and w["d"] == 1
    assert "fp" not in closed[0].wire(TS, fp=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_bars.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.bars'`

- [ ] **Step 3: Implement**

`homebase/charts/bars.py`:
```python
"""Ticks -> bars, for every bar type the charts offer. Pure: no clock, no I/O.

One BarBuilder per (symbol, bar type). add(tick) returns the bars that tick
CLOSED; `cur` is the developing bar. Every bar also carries its footprint
(volume per price: sells at the bid / buys at the ask), buy/sell volume,
sum(price*size) for an exact VWAP, and its big prints. No bar ever spans
two sessions. Time bars are anchored at the session open (18:00 ET), so a
4h bar is 18-22, 22-02, ... and a daily bar is the whole session.

The backtester (Build 3) imports this file unchanged — that is what makes
a backtest see exactly the bars the live chart saw.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .session import et_wall_s, session_date, session_range_ms
from .tick import Tick

KINDS = ("time", "tick", "volume", "range")
BIG_MIN = 10        # prints of >= this many contracts are kept per bar


@dataclass(frozen=True)
class BarSpec:
    kind: str       # time | tick | volume | range
    size: int       # seconds | trades | contracts | price ticks

    @staticmethod
    def parse(key: str) -> "BarSpec":
        kind, _, n = str(key).partition(":")
        if kind not in KINDS or not n.isdigit() or int(n) <= 0:
            raise ValueError(f"bad bar type {key!r} (want e.g. time:60, tick:500, volume:2000, range:10)")
        return BarSpec(kind, int(n))

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.size}"

    @property
    def from_minutes(self) -> bool:
        """True when these bars can be resampled from 1-minute bars."""
        return self.kind == "time" and self.size % 60 == 0


@dataclass
class Bar:
    t: int                  # start, epoch ms (time: bucket start; others: first trade)
    session: str            # session date, ISO
    o: float
    h: float
    l: float
    c: float
    v: int = 0
    buy: int = 0
    sell: int = 0
    n: int = 0
    pv: float = 0.0         # sum(price * size) -> exact VWAP
    p2v: float = 0.0        # sum(price^2 * size) -> VWAP bands
    fp: dict = field(default_factory=dict)    # price in ticks -> [sell at bid, buy at ask]
    big: list = field(default_factory=list)   # [ts_ms, price, size, side], size >= BIG_MIN
    closed: bool = False

    @classmethod
    def open_at(cls, t: int, session: str, price: float) -> "Bar":
        return cls(t=t, session=session, o=price, h=price, l=price, c=price)

    @property
    def delta(self) -> int:
        return self.buy - self.sell

    def add(self, tk: Tick, tick_size: float) -> None:
        p, q = tk.price, tk.size
        if p > self.h:
            self.h = p
        if p < self.l:
            self.l = p
        self.c = p
        self.v += q
        self.n += 1
        self.pv += p * q
        self.p2v += p * p * q
        k = round(p / tick_size)
        cell = self.fp.get(k)
        if cell is None:
            cell = self.fp[k] = [0, 0]
        if tk.side > 0:
            self.buy += q
            cell[1] += q
        else:
            self.sell += q
            cell[0] += q
        if q >= BIG_MIN:
            self.big.append([tk.ts_ms, p, q, tk.side])

    def copy(self) -> "Bar":
        return Bar(self.t, self.session, self.o, self.h, self.l, self.c, self.v,
                   self.buy, self.sell, self.n, self.pv, self.p2v,
                   {k: list(c) for k, c in self.fp.items()},
                   [list(x) for x in self.big], self.closed)

    def merge(self, other: "Bar") -> None:
        """Absorb the NEXT bar in time (resampling)."""
        self.h = max(self.h, other.h)
        self.l = min(self.l, other.l)
        self.c = other.c
        self.v += other.v
        self.buy += other.buy
        self.sell += other.sell
        self.n += other.n
        self.pv += other.pv
        self.p2v += other.p2v
        for k, (s, b) in other.fp.items():
            cell = self.fp.setdefault(k, [0, 0])
            cell[0] += s
            cell[1] += b
        self.big.extend(list(x) for x in other.big)

    def wire(self, tick_size: float, fp: bool = True) -> dict:
        """JSON for the page: t = ET wall-clock seconds (the axis shows ET),
        ms = the real start in epoch ms."""
        d = {"t": et_wall_s(self.t), "ms": self.t, "s": self.session,
             "o": self.o, "h": self.h, "l": self.l, "c": self.c,
             "v": self.v, "d": self.delta, "n": self.n, "big": self.big}
        if fp:
            d["fp"] = [[round(k * tick_size, 6), s, b] for k, (s, b) in sorted(self.fp.items())]
        return d


class BarBuilder:
    def __init__(self, spec: BarSpec, tick_size: float):
        self.spec = spec
        self.tick_size = tick_size
        self.cur: Bar | None = None
        self._sess: str | None = None
        self._s0 = self._s1 = 0
        self._floor = 0     # time bars: no new bar may start before this (set by on_clock)

    def _enter_session(self, ts: int) -> None:
        if self._sess is not None and self._s0 <= ts < self._s1:
            return
        d = session_date(ts)
        self._sess = d.isoformat()
        self._s0, self._s1 = session_range_ms(d)
        self._floor = 0

    def _bucket(self, ts: int) -> int:
        n = self.spec.size * 1000
        return max(self._s0 + (ts - self._s0) // n * n, self._floor)

    def add(self, tk: Tick) -> list[Bar]:
        closed: list[Bar] = []
        self._enter_session(tk.ts_ms)
        cur = self.cur
        if cur is not None and (cur.session != self._sess or self._breaks(cur, tk)):
            closed.append(self._close())
        if self.cur is None:
            t = self._bucket(tk.ts_ms) if self.spec.kind == "time" else tk.ts_ms
            self.cur = Bar.open_at(t, self._sess, tk.price)
        self.cur.add(tk, self.tick_size)
        if self._full(self.cur):
            closed.append(self._close())
        return closed

    def _breaks(self, cur: Bar, tk: Tick) -> bool:
        k = self.spec.kind
        if k == "time":
            return self._bucket(tk.ts_ms) != cur.t
        if k == "range":
            hi, lo = max(cur.h, tk.price), min(cur.l, tk.price)
            return round((hi - lo) / self.tick_size) > self.spec.size
        return False

    def _full(self, cur: Bar) -> bool:
        if self.spec.kind == "tick":
            return cur.n >= self.spec.size
        if self.spec.kind == "volume":
            return cur.v >= self.spec.size
        return False

    def on_clock(self, now_ms: int) -> list[Bar]:
        """Close a TIME bar whose end has passed, so a quiet market doesn't
        hold the last bar open. A tick that arrives later for the closed
        bucket (feed latency beyond the caller's grace) opens the NEXT bucket
        instead of duplicating the closed one — a reload rebuilds from the
        recorded ticks and is the truth."""
        cur = self.cur
        if cur is None or self.spec.kind != "time":
            return []
        end = min(cur.t + self.spec.size * 1000, self._s1)
        if now_ms < end:
            return []
        self._floor = end
        return [self._close()]

    def _close(self) -> Bar:
        b, self.cur = self.cur, None
        b.closed = True
        return b


def build(ticks, spec: BarSpec, tick_size: float) -> tuple[list[Bar], Bar | None]:
    """All bars of a tick sequence: (closed, developing)."""
    bb = BarBuilder(spec, tick_size)
    closed: list[Bar] = []
    for tk in ticks:
        closed.extend(bb.add(tk))
    return closed, bb.cur


def resample(minutes: list[Bar], spec: BarSpec) -> list[Bar]:
    """Closed time bars of `spec` (whole minutes) from closed 1-minute bars,
    anchored at the session open like BarBuilder — equal to building the
    same ticks directly (tested). Never mutates `minutes`; spec 1m returns
    the input list itself."""
    if spec.size == 60:
        return minutes
    n = spec.size * 1000
    out: list[Bar] = []
    cur: Bar | None = None
    for m in minutes:
        s0, _ = session_range_ms(dt.date.fromisoformat(m.session))
        t = s0 + (m.t - s0) // n * n
        if cur is None or cur.session != m.session or cur.t != t:
            if cur is not None:
                out.append(cur)
            cur = m.copy()
            cur.t = t
            cur.closed = True
        else:
            cur.merge(m)
    if cur is not None:
        out.append(cur)
    return out
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_bars.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/bars.py tests/test_charts_bars.py
git commit -m "feat(charts): bar builder — time/tick/volume/range, footprint, session-anchored, resample

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Studies (indicators) and volume profile

**Files:**
- Create: `homebase/charts/studies.py`, `tests/test_charts_studies.py`

**Interfaces:**
- Consumes: `Bar`, `build`, `BarSpec` (Task 3); `is_rth`; `homebase.gate.adx_series` (test only).
- Produces: `Study` (`push(bar)`, `preview(bar)`), `SMA(n)`, `EMA(n)`, `VWMA(n)`, `VWAP(anchor="eth"|"rth")` → `{"vwap","sd"}`, `ADX(n)` → `{"adx","pdi","mdi"}`, `CumDelta()`, `Levels()` → `{"pdh","pdl","pdc","onh","onl","rth_open"}`, `REGISTRY`, `make(key) -> Study`, `profile_from(vol, tick_size, va=0.70) -> dict|None`, `Profile(tick_size)` with `.push(bar)`, `.value(live=None)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_studies.py`:
```python
"""Studies: incremental == full recompute, preview never commits, ADX pinned to the house gate."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from homebase.charts.bars import Bar, BarSpec, build
from homebase.charts.studies import (ADX, EMA, SMA, VWAP, VWMA, CumDelta, Levels, Profile,
                                     make, profile_from)
from homebase.charts.tick import BUY, SELL, Tick
from homebase.gate import adx_series
from tests.charts_util import D, session_ms

TS = 0.25


def bar(c, v=1, session="2026-09-24", t=0, h=None, l=None, o=None):
    return Bar(t=t, session=session, o=c if o is None else o, h=c if h is None else h,
               l=c if l is None else l, c=c, v=v)


def test_preview_values_the_developing_bar_without_committing():
    e = EMA(3)
    e.push(bar(10.0))
    s = e.state
    assert e.preview(bar(20.0)) == e.preview(bar(20.0)) == 10.0 + (20.0 - 10.0) * 0.5
    assert e.state == s


def test_sma_ema_vwma_values():
    sma, ema, vwma = SMA(3), EMA(3), VWMA(2)
    got = [(sma.push(b), ema.push(b), vwma.push(b)) for b in
           (bar(1.0, 1), bar(2.0, 3), bar(3.0, 1), bar(4.0, 1))]
    assert [g[0] for g in got] == [None, None, 2.0, 3.0]
    assert [g[1] for g in got] == [1.0, 1.5, 2.25, 3.125]           # alpha 0.5, seeded with the first close
    assert [g[2] for g in got] == [None, 1.75, 2.25, 3.5]


def test_vwap_is_exact_from_every_trade_and_resets_each_session():
    m = session_ms(D, 9, 30)
    ticks = [Tick(m + i * 20_000, 100 + (i % 4) * 0.25, 1 + i % 3, BUY, i) for i in range(20)]
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    v = VWAP()
    vals = [v.push(b) for b in closed]
    done = [t for t in ticks if t.ts_ms < closed[-1].t + 60_000]
    want = sum(t.price * t.size for t in done) / sum(t.size for t in done)
    assert vals[-1]["vwap"] == pytest.approx(want, abs=1e-9) and vals[-1]["sd"] > 0
    nxt = bar(50.0, session="2026-09-25")
    nxt.pv, nxt.p2v, nxt.v = 50.0, 2500.0, 1
    assert v.push(nxt) == {"vwap": 50.0, "sd": 0.0}


def test_rth_vwap_ignores_the_overnight():
    v = VWAP("rth")
    on = bar(10.0, t=session_ms(D, 3, 0))
    on.pv, on.v = 10.0, 1
    rth = bar(20.0, t=session_ms(D, 9, 30))
    rth.pv, rth.p2v, rth.v = 20.0, 400.0, 1
    assert v.push(on) is None
    assert v.push(rth)["vwap"] == 20.0


def test_adx_matches_the_house_gate_bit_for_bit():
    fix = json.loads((Path(__file__).parent / "fixture_gate_nq2024.json").read_text())
    ref = adx_series(fix["bars"])
    st = ADX(14)
    got = []
    for i, x in enumerate(fix["bars"]):
        v = st.push(Bar(t=i, session="s", o=x["c"], h=x["h"], l=x["l"], c=x["c"]))
        got.append(None if v is None else v["adx"])
    assert got == ref


def test_cum_delta_resets_each_session():
    cd = CumDelta()
    a = bar(1.0); a.buy, a.sell = 5, 2
    b = bar(1.0); b.buy, b.sell = 1, 4
    c = bar(1.0, session="2026-09-25"); c.buy, c.sell = 2, 0
    assert [cd.push(x) for x in (a, b, c)] == [3, 0, 2]


def test_levels_prior_session_overnight_and_rth_open():
    p = D - dt.timedelta(days=1)
    bars = [bar(105, session=p.isoformat(), t=session_ms(p, 10, 0), h=110, l=100),
            bar(104, t=session_ms(D, 18, 0), h=107, l=103),
            bar(106, t=session_ms(D, 3, 0), h=108, l=101),
            bar(111, t=session_ms(D, 9, 30), h=112, l=106, o=106.5)]
    st = Levels()
    vals = [st.push(b) for b in bars]
    assert vals[-1] == {"pdh": 110, "pdl": 100, "pdc": 105, "onh": 108, "onl": 101, "rth_open": 106.5}
    assert vals[1]["rth_open"] is None


def test_profile_poc_and_value_area():
    p = profile_from({400: 10, 401: 50, 402: 30, 403: 5, 404: 5}, TS)
    assert (p["poc"], p["val"], p["vah"]) == (100.25, 100.25, 100.5)
    assert p["rows"][0] == [100.0, 10]
    assert profile_from({}, TS) is None


def test_profile_accumulates_and_previews_the_live_bar():
    m = session_ms(D, 9, 30)
    ticks = [Tick(m + i * 15_000, 100 + (i % 5) * 0.25, 1 + i % 2, BUY if i % 2 else SELL, i)
             for i in range(30)]
    closed, cur = build(ticks, BarSpec("time", 60), TS)
    acc = Profile(TS)
    for b in closed:
        acc.push(b)
    vol: dict = {}
    for b in closed + [cur]:
        for k, (s, bu) in b.fp.items():
            vol[k] = vol.get(k, 0) + s + bu
    assert acc.value(cur) == profile_from(vol, TS)


def test_make_parses_keys():
    assert make("ema:20").n == 20
    assert make("vwap:rth").anchor == "rth"
    assert isinstance(make("levels"), Levels)
    for bad in ("nope", "vwap:xyz"):
        with pytest.raises(ValueError):
            make(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_studies.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.studies'`

- [ ] **Step 3: Implement**

`homebase/charts/studies.py`:
```python
"""Indicators, computed incrementally on bars. Pure.

push(bar) commits a CLOSED bar and returns its value; preview(bar) values
the DEVELOPING bar without committing. State is an immutable tuple, so a
preview can never corrupt it. Values: float, dict, or None (warming up).

Wire keys: "sma:50", "ema:20", "vwma:15", "vwap", "vwap:rth", "adx:14",
"cumdelta", "levels". ("profile" is not a Study — see Profile.)
"""
from __future__ import annotations

import math

from .session import is_rth


class Study:
    def __init__(self):
        self.state = self.initial()

    def initial(self) -> tuple:
        return ()

    def step(self, state: tuple, bar) -> tuple:     # -> (new state, value)
        raise NotImplementedError

    def push(self, bar):
        self.state, v = self.step(self.state, bar)
        return v

    def preview(self, bar):
        return self.step(self.state, bar)[1]


class SMA(Study):
    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, st, bar):
        w = (st + (bar.c,))[-self.n:]
        return w, (sum(w) / self.n if len(w) == self.n else None)


class EMA(Study):
    """pandas ewm(span=n, adjust=False): alpha 2/(n+1), seeded with the first close."""

    def __init__(self, n: int = 20):
        self.n = int(n)
        self.a = 2.0 / (self.n + 1)
        super().__init__()

    def initial(self):
        return (None,)

    def step(self, st, bar):
        prev = st[0]
        v = bar.c if prev is None else prev + (bar.c - prev) * self.a
        return (v,), v


class VWMA(Study):
    """sum(close * volume) / sum(volume) over the last n bars."""

    def __init__(self, n: int = 20):
        self.n = int(n)
        super().__init__()

    def step(self, st, bar):
        w = (st + ((bar.c, bar.v),))[-self.n:]
        if len(w) < self.n:
            return w, None
        vol = sum(v for _, v in w)
        return w, (sum(c * v for c, v in w) / vol if vol else None)


class VWAP(Study):
    """Session VWAP from every trade (bars carry sum(p*q)) + its volume-
    weighted standard deviation for bands. anchor "eth" resets at the 18:00
    open (TradingView's session default); "rth" resets at 09:30 ET and is
    None before it."""

    def __init__(self, anchor: str = "eth"):
        if anchor not in ("eth", "rth"):
            raise ValueError(f"vwap anchor {anchor!r} (eth or rth)")
        self.anchor = anchor
        super().__init__()

    def initial(self):
        return (None, 0.0, 0.0, 0)

    def step(self, st, bar):
        if self.anchor == "rth" and not is_rth(bar.t, bar.session):
            return st, None
        _, pv, p2v, v = st if st[0] == bar.session else (bar.session, 0.0, 0.0, 0)
        pv, p2v, v = pv + bar.pv, p2v + bar.p2v, v + bar.v
        new = (bar.session, pv, p2v, v)
        if not v:
            return new, None
        vw = pv / v
        return new, {"vwap": vw, "sd": math.sqrt(max(p2v / v - vw * vw, 0.0))}


class ADX(Study):
    """Wilder ADX/DI — bit-for-bit the house definition in homebase.gate:
    RMA = prev + (x - prev) * (1/n) seeded with the first value, a 0/0 DX
    carries the previous ADX, and no reading before bar 2n."""

    def __init__(self, n: int = 14):
        self.n = int(n)
        self.a = 1.0 / self.n
        super().__init__()

    def initial(self):
        return (0, None, None, None, None, None, None, None)   # i, ph, pl, pc, atr, p, m, adx

    def _rma(self, prev, x):
        return x if prev is None else prev + (x - prev) * self.a

    def step(self, st, bar):
        i, ph, pl, pc, atr, p, m, adx = st
        h, l, c = bar.h, bar.l, bar.c
        if i == 0:
            tr, up_dm, dn_dm = h - l, 0.0, 0.0
        else:
            tr = max(h - l, abs(h - pc), abs(l - pc))
            up, dn = h - ph, pl - l
            up_dm = up if (up > dn and up > 0) else 0.0
            dn_dm = dn if (dn > up and dn > 0) else 0.0
        atr, p, m = self._rma(atr, tr), self._rma(p, up_dm), self._rma(m, dn_dm)
        pdi = 100.0 * p / atr if atr else 0.0
        mdi = 100.0 * m / atr if atr else 0.0
        s = pdi + mdi
        dx = 100.0 * abs(pdi - mdi) / s if s else None
        if dx is not None:
            adx = self._rma(adx, dx)
        val = {"adx": adx, "pdi": pdi, "mdi": mdi} if i >= 2 * self.n else None
        return (i + 1, h, l, c, atr, p, m, adx), val


class CumDelta(Study):
    """Buy minus sell volume, summed over the session."""

    def initial(self):
        return (None, 0)

    def step(self, st, bar):
        cum = (st[1] if st[0] == bar.session else 0) + bar.delta
        return (bar.session, cum), cum


class Levels(Study):
    """Prior session high/low/close, overnight high/low (18:00 -> 09:30 ET)
    and the RTH open. Exact on bar sizes that split at 09:30 (<= 30m)."""

    def initial(self):
        return (None, None, None, None, None, None, None, None)  # sess, h, l, c, prev, onh, onl, open

    def step(self, st, bar):
        sess, h, l, c, prev, onh, onl, ropen = st
        if sess != bar.session:
            if sess is not None:
                prev = (h, l, c)
            sess, h, l, c, onh, onl, ropen = bar.session, bar.h, bar.l, bar.c, None, None, None
        else:
            h, l, c = max(h, bar.h), min(l, bar.l), bar.c
        if is_rth(bar.t, bar.session):
            if ropen is None:
                ropen = bar.o
        else:
            onh = bar.h if onh is None else max(onh, bar.h)
            onl = bar.l if onl is None else min(onl, bar.l)
        val = {"pdh": prev[0] if prev else None, "pdl": prev[1] if prev else None,
               "pdc": prev[2] if prev else None, "onh": onh, "onl": onl, "rth_open": ropen}
        return (sess, h, l, c, prev, onh, onl, ropen), val


REGISTRY = {"sma": SMA, "ema": EMA, "vwma": VWMA, "vwap": VWAP, "adx": ADX,
            "cumdelta": CumDelta, "levels": Levels}


def make(key: str) -> Study:
    name, *args = str(key).split(":")
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown study {key!r} (have {', '.join(sorted(REGISTRY))}, profile)")
    return cls(*[int(a) if a.isdigit() else a for a in args])


def profile_from(vol: dict, tick_size: float, va: float = 0.70) -> dict | None:
    """POC, value area (grown one price row at a time from the POC toward
    the heavier neighbour until it holds `va` of the volume) and the rows,
    from volume per price-in-ticks."""
    if not vol:
        return None
    keys = sorted(vol)
    total = sum(vol.values())
    i = max(range(len(keys)), key=lambda j: (vol[keys[j]], -j))
    lo = hi = i
    acc = vol[keys[i]]
    while acc < va * total and (lo > 0 or hi < len(keys) - 1):
        up = vol[keys[hi + 1]] if hi < len(keys) - 1 else -1
        dn = vol[keys[lo - 1]] if lo > 0 else -1
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn

    def px(k):
        return round(k * tick_size, 6)

    return {"poc": px(keys[i]), "vah": px(keys[hi]), "val": px(keys[lo]),
            "rows": [[px(k), vol[k]] for k in keys]}


class Profile:
    """Session volume profile, accumulated bar by bar. Not a Study: its value
    is the whole profile, not one number per bar."""

    def __init__(self, tick_size: float):
        self.tick_size = tick_size
        self.session: str | None = None
        self.vol: dict = {}

    def push(self, bar) -> None:
        if bar.session != self.session:
            self.session, self.vol = bar.session, {}
        for k, (s, b) in bar.fp.items():
            self.vol[k] = self.vol.get(k, 0) + s + b

    def value(self, live=None) -> dict | None:
        vol = self.vol
        if live is not None:
            vol = dict(vol) if live.session == self.session else {}
            for k, (s, b) in live.fp.items():
                vol[k] = vol.get(k, 0) + s + b
        return profile_from(vol, self.tick_size)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_studies.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/studies.py tests/test_charts_studies.py
git commit -m "feat(charts): incremental studies (SMA/EMA/VWMA/VWAP/ADX/cum-delta/levels) + volume profile; ADX pinned to the gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: History (past sessions, 1-minute cache)

**Files:**
- Create: `homebase/charts/history.py`, `tests/test_charts_history.py`

**Interfaces:**
- Consumes: `TickStore` (Task 2), `BarSpec`, `build`, `resample` (Task 3), `homebase.contracts.tick_size`, `et_wall_s`.
- Produces: `History(store, cache_dir=None, memo_max=256)` with `.store`, `.minutes(root, d) -> list[Bar]`, `.bars(root, spec, d) -> list[Bar]` (all closed), `.info(root, d) -> {"date","contract","source","approx","gaps"}` (gaps in ET wall seconds), `.clear()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_history.py`:
```python
"""History: 1-minute cache on disk, resampled bars == direct build, invalidation."""
from __future__ import annotations

import os
import time

from homebase.charts.bars import BarSpec, build
from homebase.charts.history import History
from homebase.charts.store import TickStore
from tests.charts_util import D, rows, session_ms, write_archive, write_gz


def _k(b):
    return (b.t, b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, round(b.pv, 6), b.fp)


def setup(tmp_path, n=600):
    r = rows(session_ms(D, 9, 30), [100 + 0.25 * (i % 9) for i in range(n)], step_ms=7_000,
             sides=[1 if i % 3 else -1 for i in range(n)])
    src = write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", r)
    store = TickStore(tmp_path / "ticks")
    return History(store, cache_dir=tmp_path / "cache"), store, src


def test_resampled_history_equals_a_direct_build(tmp_path):
    h, store, _ = setup(tmp_path)
    ticks = store.load("NQ", D).ticks
    for spec in (BarSpec("time", 60), BarSpec("time", 300), BarSpec("tick", 50)):
        closed, cur = build(ticks, spec, 0.25)
        want = closed + ([cur] if cur else [])
        got = h.bars("NQ", spec, D)
        assert [_k(b) for b in got] == [_k(b) for b in want]
        assert all(b.closed for b in got)


def test_minutes_are_cached_on_disk_and_reused(tmp_path):
    h, store, _ = setup(tmp_path)
    first = h.minutes("NQ", D)
    calls = []
    orig = store.load
    store.load = lambda *a: calls.append(a) or orig(*a)
    h2 = History(store, cache_dir=tmp_path / "cache")
    assert [_k(b) for b in h2.minutes("NQ", D)] == [_k(b) for b in first]
    assert calls == []


def test_a_newer_source_file_invalidates_the_cache(tmp_path):
    h, store, src = setup(tmp_path)
    h.minutes("NQ", D)
    future = time.time() + 60
    os.utime(src, (future, future))
    calls = []
    orig = store.load
    store.load = lambda *a: calls.append(a) or orig(*a)
    History(store, cache_dir=tmp_path / "cache").minutes("NQ", D)
    assert len(calls) == 1


def test_info_labels_the_session(tmp_path):
    h, _, _ = setup(tmp_path, n=5)
    assert h.info("NQ", D) == {"date": D.isoformat(), "contract": "NQZ6", "source": "archive",
                               "approx": False, "gaps": []}
    live = write_gz(tmp_path / "ticks" / "ES" / "2026" / f"{D}_ESZ6.live.csv.gz",
                    rows(session_ms(D, 9, 30), [1.0]))
    live.with_name(f"{D}_ESZ6.gaps.json").write_text(f"[[{session_ms(D, 9, 0)}, {session_ms(D, 9, 5)}]]")
    info = h.info("ES", D)
    assert info["source"] == "live" and len(info["gaps"]) == 1
    assert info["gaps"][0][1] - info["gaps"][0][0] == 300
    assert h.info("YM", D)["source"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_history.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.history'`

- [ ] **Step 3: Implement**

`homebase/charts/history.py`:
```python
"""Bars of COMPLETED sessions, fast.

Two caches over the TickStore: a per-session 1-minute bar pickle on disk
(built once from ticks; every time bar >= 1m is resampled from it, so a
60-session daily chart never re-reads ticks) and an in-memory memo per
(root, bar type, date). Today's session is the hub's job, not this file's.
Thread-safe: the hub calls it from worker threads.
"""
from __future__ import annotations

import datetime as dt
import os
import pickle
import threading
from collections import OrderedDict
from pathlib import Path

from ..contracts import tick_size
from ..paths import state_dir
from .bars import Bar, BarSpec, build, resample
from .session import et_wall_s
from .store import TickStore

M1 = BarSpec("time", 60)
CACHE_VERSION = 1


class History:
    def __init__(self, store: TickStore, cache_dir: Path | None = None, memo_max: int = 256):
        self.store = store
        self.cache_dir = Path(cache_dir) if cache_dir else state_dir() / "charts" / "cache"
        self.memo: OrderedDict = OrderedDict()
        self.memo_max = memo_max
        self._lock = threading.Lock()

    def _from_ticks(self, root: str, spec: BarSpec, d: dt.date) -> list[Bar]:
        s = self.store.load(root, d)
        if s is None:
            return []
        closed, cur = build(s.ticks, spec, tick_size(root))
        if cur is not None:
            cur.closed = True
            closed.append(cur)
        return closed

    def minutes(self, root: str, d: dt.date) -> list[Bar]:
        f = self.store.pick(root, d)
        if f is None:
            return []
        cp = self.cache_dir / (f"v{CACHE_VERSION}_{root}_{d.isoformat()}_{f.contract}_"
                               f"{'live' if f.live else 'arch'}.m1.pkl")
        try:
            if cp.stat().st_mtime >= f.path.stat().st_mtime:
                with open(cp, "rb") as fh:
                    return pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError):
            pass
        bars = self._from_ticks(root, M1, d)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cp.with_name(cp.name + f".{threading.get_ident()}.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(bars, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, cp)
        return bars

    def bars(self, root: str, spec: BarSpec, d: dt.date) -> list[Bar]:
        key = (root, spec.key, d)
        with self._lock:
            hit = self.memo.get(key)
            if hit is not None:
                self.memo.move_to_end(key)
                return hit
        out = resample(self.minutes(root, d), spec) if spec.from_minutes else self._from_ticks(root, spec, d)
        with self._lock:
            self.memo[key] = out
            while len(self.memo) > self.memo_max:
                self.memo.popitem(last=False)
        return out

    def info(self, root: str, d: dt.date) -> dict:
        """What the page needs to label a session honestly. Cheap: no ticks read."""
        f = self.store.pick(root, d)
        if f is None:
            return {"date": d.isoformat(), "contract": None, "source": None, "approx": False, "gaps": []}
        return {"date": d.isoformat(), "contract": f.contract,
                "source": "live" if f.live else "archive", "approx": not f.bid_ask,
                "gaps": [[et_wall_s(a), et_wall_s(b)] for a, b in self.store.gaps(f)]}

    def clear(self) -> None:
        with self._lock:
            self.memo.clear()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_history.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/history.py tests/test_charts_history.py
git commit -m "feat(charts): history — per-session 1m pickle cache, resampled bars, session labels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Live recorder and gap refill

**Files:**
- Create: `homebase/charts/recorder.py`, `tests/test_charts_recorder.py`

**Interfaces:**
- Consumes: `read_table`, `gaps_path`, `ARCHIVE`, `LIVE_SUFFIX`, `TickStore` (Task 2); `session_date`; `homebase.ticks.FIELDS`, `.fetch_page`, `.Penalty`, `.PAGE_INTERVAL_S`.
- Produces: `REFILL_MAX_PAGES=20`, `LiveRecorder(base)` with `.path(root, d, contract)`, `.append(root, contract, rows) -> list[dict]` (only new rows), `.last_ts(root, d, contract) -> int|None`, `.flush() -> int`, `.mark_gap(root, d, contract, start_ms, end_ms)`, `.buffered`, `.error`, `.written`; `async refill(ws, contract, from_ms, to_ms, *, page_fn=None, sleep=asyncio.sleep, max_pages=20, on_request=None) -> (rows, reached_ms)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_recorder.py`:
```python
"""Recorder: dedupe, per-session files, crash safety, gaps; refill paging."""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip

from homebase import ticks as T
from homebase.charts.recorder import LiveRecorder, refill
from homebase.charts.store import TickStore, read_table
from tests.charts_util import D, rows, session_ms

M = session_ms(D, 9, 30)


def run(coro):
    return asyncio.run(coro)


async def nosleep(_s):
    return None


def test_append_dedupes_and_flush_writes_a_readable_file(tmp_path):
    rec = LiveRecorder(tmp_path)
    r = rows(M, [100.0, 100.25, 100.5])
    assert len(rec.append("NQ", "NQZ6", r[:2])) == 2
    assert len(rec.append("NQ", "NQZ6", r)) == 1          # r0, r1 already held
    assert rec.buffered == 3
    assert rec.flush() == 3 and rec.buffered == 0
    rec.append("NQ", "NQZ6", rows(M + 5_000, [101.0], first_id=4))
    rec.flush()
    s = TickStore(tmp_path).load("NQ", D)
    assert [t.id for t in s.ticks] == [1, 2, 3, 4] and s.source == "live"


def test_rows_file_by_their_own_session(tmp_path):
    rec = LiveRecorder(tmp_path)
    nxt = D + dt.timedelta(days=1)
    rec.append("NQ", "NQZ6", rows(session_ms(D, 16, 59), [1.0]) + rows(session_ms(nxt, 18, 1), [2.0], first_id=9))
    rec.flush()
    assert rec.path("NQ", D, "NQZ6").exists() and rec.path("NQ", nxt, "NQZ6").exists()


def test_a_restart_remembers_ids_and_the_last_tick(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0, 100.25]))
    rec.flush()
    again = LiveRecorder(tmp_path)
    assert again.last_ts("NQ", D, "NQZ6") == M + 1000
    assert again.append("NQ", "NQZ6", rows(M, [100.0, 100.25])) == []


def test_a_torn_first_member_is_set_aside(tmp_path):
    rec = LiveRecorder(tmp_path)
    p = rec.path("NQ", D, "NQZ6")
    p.parent.mkdir(parents=True)
    p.write_bytes(gzip.compress(b"ts_ms,price,size,bid,ask,bid_size,ask_size,id\n1,2,3,,,,,4\n")[:12])
    assert rec.append("NQ", "NQZ6", rows(M, [100.0])) != []
    rec.flush()
    assert p.with_name(p.name + ".corrupt").exists()
    header, recs = read_table(p)
    assert header and len(recs) == 1


def test_a_failed_flush_keeps_the_rows(tmp_path):
    blocker = tmp_path / "NQ"
    blocker.write_text("not a directory")
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    assert rec.flush() == 0 and rec.error and rec.buffered == 1
    blocker.unlink()
    assert rec.flush() == 1 and rec.error is None


def test_mark_gap_is_read_back_by_the_store(tmp_path):
    rec = LiveRecorder(tmp_path)
    rec.append("NQ", "NQZ6", rows(M, [100.0]))
    rec.flush()
    rec.mark_gap("NQ", D, "NQZ6", 1, 2)
    rec.mark_gap("NQ", D, "NQZ6", 3, 4)
    assert TickStore(tmp_path).load("NQ", D).gaps == [[1, 2], [3, 4]]


def pager(all_rows, page=3, penalty_first=False):
    calls = []

    async def page_fn(ws, contract, before, ticket=None):
        calls.append((before, ticket))
        if penalty_first and len(calls) == 1:
            raise T.Penalty({"p-ticket": "tk", "p-time": 1})
        return [r for r in all_rows if r["ts_ms"] <= before][-page:]
    return page_fn, calls


def test_refill_covers_the_gap_oldest_first():
    rs = rows(M, [100 + 0.25 * i for i in range(10)])
    fn, _ = pager(rs)
    got, reached = run(refill(None, "NQZ6", M + 2000, M + 9000, page_fn=fn, sleep=nosleep))
    assert [r["ts_ms"] for r in got] == [M + i * 1000 for i in range(3, 9)]
    assert reached <= M + 2000


def test_refill_stops_at_the_page_cap_and_reports_the_rest():
    rs = rows(M, [100 + 0.25 * i for i in range(10)])
    fn, calls = pager(rs)
    counted = []
    got, reached = run(refill(None, "NQZ6", M + 2000, M + 9000, page_fn=fn, sleep=nosleep,
                              max_pages=2, on_request=lambda: counted.append(1)))
    assert [r["ts_ms"] for r in got] == [M + i * 1000 for i in range(5, 9)]
    assert reached == M + 5000 and len(calls) == 2 and len(counted) == 2


def test_refill_honors_a_penalty_ticket():
    rs = rows(M, [100.0, 100.25, 100.5])
    fn, calls = pager(rs, penalty_first=True)
    got, _ = run(refill(None, "NQZ6", M - 1, M + 3000, page_fn=fn, sleep=nosleep))
    assert calls[1][1] == "tk" and len(got) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_recorder.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.recorder'`

- [ ] **Step 3: Implement**

`homebase/charts/recorder.py`:
```python
"""The chart service's own tick recording, and the gap refill.

Every raw tick row the live feed delivers is appended to
~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz as one gzip
member per flush (about once a second): a crash loses at most the
unflushed second, and the reader drops a torn tail. Rows are deduped by
tick id, so a refill that overlaps what we hold writes nothing twice.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import gzip
import io
import json
from pathlib import Path

from .. import ticks as T
from .session import session_date
from .store import ARCHIVE, LIVE_SUFFIX, gaps_path, read_table

REFILL_MAX_PAGES = 20


class LiveRecorder:
    def __init__(self, base: Path = ARCHIVE):
        self.base = Path(base)
        self._buf: dict[Path, list[dict]] = {}
        self._seen: dict[Path, set[int]] = {}
        self._last: dict[Path, int] = {}
        self.error: str | None = None
        self.written = 0

    def path(self, root: str, d: dt.date, contract: str) -> Path:
        return self.base / root / str(d.year) / f"{d.isoformat()}_{contract}{LIVE_SUFFIX}"

    @property
    def buffered(self) -> int:
        return sum(len(v) for v in self._buf.values())

    def _open(self, p: Path) -> set[int]:
        seen = self._seen.get(p)
        if seen is not None:
            return seen
        seen = set()
        if p.exists():
            header, recs = read_table(p)
            if not header:                    # first member torn by a crash: set it aside
                p.rename(p.with_name(p.name + ".corrupt"))
            else:
                ii, it = header.index("id"), header.index("ts_ms")
                seen = {int(r[ii]) for r in recs if r[ii]}
                if recs:
                    self._last[p] = max(int(r[it]) for r in recs)
        self._seen[p] = seen
        return seen

    def append(self, root: str, contract: str, rows: list[dict]) -> list[dict]:
        """Buffer the rows not held yet; returns exactly those."""
        new = []
        for r in rows:
            ts = int(r["ts_ms"])
            p = self.path(root, session_date(ts), contract)
            seen = self._open(p)
            tid = r.get("id")
            if tid not in (None, ""):
                if int(tid) in seen:
                    continue
                seen.add(int(tid))
            self._buf.setdefault(p, []).append(r)
            if ts > self._last.get(p, 0):
                self._last[p] = ts
            new.append(r)
        return new

    def last_ts(self, root: str, d: dt.date, contract: str) -> int | None:
        p = self.path(root, d, contract)
        self._open(p)
        return self._last.get(p)

    def flush(self) -> int:
        n, failed = 0, None
        for p, rows in self._buf.items():
            if not rows:
                continue
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                out = io.StringIO()
                w = csv.DictWriter(out, fieldnames=T.FIELDS, extrasaction="ignore")
                if not p.exists():
                    w.writeheader()
                w.writerows(rows)
                with open(p, "ab") as fh:
                    fh.write(gzip.compress(out.getvalue().encode()))
            except OSError as e:
                failed = f"{p.name}: {e}"      # rows stay buffered; the feed keeps running
                continue
            n += len(rows)
            rows.clear()
        self.error = failed
        self.written += n
        return n

    def mark_gap(self, root: str, d: dt.date, contract: str, start_ms: int, end_ms: int) -> None:
        gp = gaps_path(self.path(root, d, contract))
        try:
            gaps = json.loads(gp.read_text())
        except (OSError, ValueError):
            gaps = []
        gaps.append([int(start_ms), int(end_ms)])
        gp.parent.mkdir(parents=True, exist_ok=True)
        gp.write_text(json.dumps(gaps))


async def refill(ws, contract: str, from_ms: int, to_ms: int, *, page_fn=None,
                 sleep=asyncio.sleep, max_pages: int = REFILL_MAX_PAGES,
                 on_request=None) -> tuple[list[dict], int]:
    """Tick rows in (from_ms, to_ms), paging backwards from to_ms at the
    archive job's pace. Returns (rows oldest first, reached_ms): reached_ms
    <= from_ms means the whole gap is covered; otherwise [from_ms,
    reached_ms) is still missing (page cap hit, or the broker's buffer ran
    dry). A second penalty in a row raises — the caller marks the gap."""
    page_fn = page_fn or T.fetch_page
    rows: list[dict] = []
    seen: set = set()
    before = reached = to_ms
    for i in range(max_pages):
        if i:
            await sleep(T.PAGE_INTERVAL_S)
        if on_request:
            on_request()
        try:
            page = await page_fn(ws, contract, before)
        except T.Penalty as pen:
            await sleep(pen.wait_s + 1)
            if on_request:
                on_request()
            page = await page_fn(ws, contract, before, ticket=pen.ticket)
        fresh = [r for r in page if r["id"] not in seen]
        if not fresh:
            break
        seen.update(r["id"] for r in fresh)
        rows.extend(r for r in fresh if from_ms < r["ts_ms"] < to_ms)
        reached = min(reached, page[0]["ts_ms"])
        if reached <= from_ms:
            break
        before = page[0]["ts_ms"]
    rows.sort(key=lambda r: (r["ts_ms"], r["id"] or 0))
    return rows, reached
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_recorder.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/recorder.py tests/test_charts_recorder.py
git commit -m "feat(charts): live tick recorder (crash-safe members, id dedupe, gaps) + bounded gap refill

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Tick feed (md socket, subscriptions, reconnect, budget)

**Files:**
- Create: `homebase/charts/tickfeed.py`, `tests/test_charts_tickfeed.py`

**Interfaces:**
- Consumes: `MD_ENV` (Task 1), `homebase.ticks._unpack`, `.Penalty`, `.connect_md(prefer_live)`, `homebase.symbols.resolve_contract`.
- Produces: `TickFeed(roots, on_ticks, on_subscribed=None, connect=connect_default, sleep=asyncio.sleep, now=time.time)`. `on_ticks(root, contract, rows)` is sync. `on_subscribed(root, contract, since_ms)` is async, where `since_ms` is the last tick time this feed delivered for `root` before this (re)subscription, or None. Methods and properties: `.run()`, `.stop()`, `.ws`, `.connected`, `.count_request()`, `.budget_used() -> int`, `.status() -> dict` (keys `mode, md, connected, error, reconnects, budget_hour, roots{root: {contract, last_tick_age_s}}`), `BACKOFF_S`, `HEALTHY_S`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_tickfeed.py`:
```python
"""Tick feed: one subscription per root, routing by chart id, penalty, reconnect backoff."""
from __future__ import annotations

import asyncio

from homebase import symbols
from homebase.charts.tickfeed import TickFeed


def run(coro):
    return asyncio.run(coro)


class FakeWS:
    def __init__(self, replies=None):
        self.connected = True
        self.event_handlers = []
        self.sent = []
        self.replies = list(replies or [])

    async def request(self, ep, body=""):
        self.sent.append((ep, body))
        if self.replies:
            return self.replies.pop(0)
        n = len(self.sent)
        return {"historicalId": 10 + n, "realtimeId": 100 + n}

    async def close(self):
        self.connected = False

    def push(self, rid, tks):
        for h in list(self.event_handlers):
            h({"e": "chart", "d": {"charts": [{"id": rid, "bp": 400, "bt": 1000, "ts": 0.25, "tks": tks}]}})


async def nosleep(_s):
    await asyncio.sleep(0)


def test_one_subscription_per_root_and_ticks_route_by_chart_id():
    ws, got = FakeWS(), []
    feed = TickFeed(["NQ", "ES"], lambda r, c, rows: got.append((r, c, rows)), sleep=nosleep)
    feed.ws = ws
    ws.event_handlers.append(feed._on_event)
    run(feed.subscribe("NQ"))
    run(feed.subscribe("ES"))
    assert [b["symbol"] for _, b in ws.sent] == [symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")]
    assert ws.sent[0][1]["chartDescription"]["underlyingType"] == "Tick"
    ws.push(101, [{"t": 5, "p": 1, "s": 2, "b": 0, "a": 1, "id": 9}])
    ws.push(11, [{"t": 6, "p": 2, "s": 1, "id": 10}])            # the historical id routes too
    ws.push(999, [{"t": 7, "p": 3, "s": 1, "id": 11}])           # not ours
    assert [(g[0], g[2][0]["price"], g[2][0]["ts_ms"]) for g in got] == [("NQ", 100.25, 1005), ("NQ", 100.5, 1006)]
    assert got[0][2][0]["bid"] == 100.0 and got[0][2][0]["ask"] == 100.25
    assert feed.budget_used() == 2
    st = feed.status()
    assert st["roots"]["NQ"]["contract"] == symbols.resolve_contract("NQ") and st["budget_hour"] == 2


def test_a_penalty_reply_is_resent_with_its_ticket():
    slept = []

    async def sleep(s):
        slept.append(s)
    ws = FakeWS([{"p-ticket": "tk", "p-time": 2}, {"historicalId": 1, "realtimeId": 2}])
    feed = TickFeed(["NQ"], lambda *a: None, sleep=sleep)
    feed.ws = ws
    run(feed.subscribe("NQ"))
    assert ws.sent[1][1]["p-ticket"] == "tk" and slept == [3] and feed.budget_used() == 2


def test_reconnect_backs_off_resubscribes_and_reports_the_last_tick():
    socks, slept, subs = [], [], []

    async def connect():
        ws = FakeWS()
        socks.append(ws)
        return ws

    async def sleep(s):
        slept.append(s)
        await asyncio.sleep(0)
        if s == 1:
            if len(socks) == 1:
                socks[0].push(101, [{"t": 5, "p": 1, "s": 1, "id": 1}])
            socks[-1].connected = False                # the socket drops
            if slept.count(1) >= 3:
                feed.stop()

    async def on_sub(root, contract, since):
        subs.append((root, since))

    feed = TickFeed(["NQ"], lambda *a: None, on_subscribed=on_sub, connect=connect, sleep=sleep)
    run(feed.run())
    assert len(socks) == 3
    assert [s for s in slept if s != 1] == [5, 10]
    assert subs == [("NQ", None), ("NQ", 1005), ("NQ", 1005)]
    assert feed.reconnects == 2 and not feed.connected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_tickfeed.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.tickfeed'`

- [ ] **Step 3: Implement**

`homebase/charts/tickfeed.py`:
```python
"""Live ticks from the broker for the charts: ONE md socket and ONE Tick
chart subscription per root, however many charts are open.

The md budget (180 chart requests/hour/login; a burst penalizes the whole
hour) is shared with the trading process when both ride one login, so:
every request is counted (status shows the hour's total), a rate-limit
reply is honored with its p-ticket, and reconnects back off 5 s doubling
to 5 min, so a flapping socket can neither burn the hour nor trip the auth
captcha. Each (re)connect reads the freshest md token the desk has on disk.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from .. import symbols
from .. import ticks as T
from . import MD_ENV

BACKOFF_S = (5, 10, 20, 40, 80, 160, 300)
HEALTHY_S = 600          # a connection that lived this long resets the backoff


async def connect_default():
    return await T.connect_md(prefer_live=(MD_ENV == "live"))


class TickFeed:
    def __init__(self, roots, on_ticks: Callable[[str, str, list], None],
                 on_subscribed: Optional[Callable[[str, str, Optional[int]], Awaitable[None]]] = None,
                 connect=connect_default, sleep=asyncio.sleep, now=time.time):
        self.roots = [r.upper() for r in roots]
        self.on_ticks = on_ticks
        self.on_subscribed = on_subscribed
        self._connect, self._sleep, self._now = connect, sleep, now
        self.ws = None
        self.subs: dict[int, tuple[str, str]] = {}
        self.contracts: dict[str, str] = {}
        self.last_tick: dict[str, float] = {}      # root -> wall time of the last delivery
        self.last_ms: dict[str, int] = {}          # root -> newest tick timestamp delivered
        self._requests: list[float] = []
        self.reconnects = 0
        self.error: Optional[str] = None
        self._stop = False
        self._tasks: set = set()

    def count_request(self) -> None:
        self._requests.append(self._now())

    def budget_used(self) -> int:
        cut = self._now() - 3600
        self._requests = [t for t in self._requests if t > cut]
        return len(self._requests)

    @property
    def connected(self) -> bool:
        return bool(self.ws is not None and getattr(self.ws, "connected", False))

    def status(self) -> dict:
        now = self._now()
        return {"mode": "live", "md": MD_ENV, "connected": self.connected, "error": self.error,
                "reconnects": self.reconnects, "budget_hour": self.budget_used(),
                "roots": {r: {"contract": self.contracts.get(r),
                              "last_tick_age_s": (round(now - self.last_tick[r], 1)
                                                  if r in self.last_tick else None)}
                          for r in self.roots}}

    def _on_event(self, msg: dict) -> None:
        if msg.get("e") != "chart":
            return
        for ch in (msg.get("d") or {}).get("charts", []) or []:
            sub = self.subs.get(ch.get("id"))
            if sub is None or not ch.get("tks"):
                continue
            rows = T._unpack(ch)
            if rows:
                root = sub[0]
                self.last_tick[root] = self._now()
                self.last_ms[root] = max(self.last_ms.get(root, 0), max(r["ts_ms"] for r in rows))
                self.on_ticks(root, sub[1], rows)

    async def subscribe(self, root: str) -> str:
        contract = symbols.resolve_contract(root)
        body = {"symbol": contract,
                "chartDescription": {"underlyingType": "Tick", "elementSize": 1,
                                     "elementSizeUnit": "UnderlyingUnits", "withHistogram": False},
                "timeRange": {"asMuchAsElements": 1}}
        d = None
        for _ in range(3):
            self.count_request()
            d = await self.ws.request("md/getChart", body)
            if isinstance(d, dict) and d.get("p-ticket"):
                pen = T.Penalty(d)
                await self._sleep(pen.wait_s + 1)
                body = {**body, "p-ticket": pen.ticket}
                continue
            break
        if not isinstance(d, dict) or d.get("realtimeId") is None:
            raise RuntimeError(f"{contract}: getChart refused: {d!r}")
        for k in ("historicalId", "realtimeId"):
            if d.get(k) is not None:
                self.subs[int(d[k])] = (root, contract)
        self.contracts[root] = contract
        return contract

    async def run(self) -> None:
        attempt = 0
        while not self._stop:
            started = self._now()
            try:
                self.ws = await self._connect()
                self.ws.event_handlers.append(self._on_event)
                self.subs = {}
                for r in self.roots:
                    since = self.last_ms.get(r)
                    c = await self.subscribe(r)
                    if self.on_subscribed is not None:
                        t = asyncio.create_task(self.on_subscribed(r, c, since))
                        self._tasks.add(t)
                        t.add_done_callback(self._tasks.discard)
                self.error = None
                while not self._stop and self.connected:
                    await self._sleep(1)
                if not self._stop:
                    self.error = "md socket closed"
            except Exception as e:  # noqa: BLE001 — any failure = reconnect with backoff
                self.error = f"{type(e).__name__}: {e}"
            finally:
                ws, self.ws = self.ws, None
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:  # noqa: BLE001
                        pass
            if self._stop:
                break
            if self._now() - started >= HEALTHY_S:
                attempt = 0
            self.reconnects += 1
            await self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
            attempt += 1

    def stop(self) -> None:
        self._stop = True
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_tickfeed.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/tickfeed.py tests/test_charts_tickfeed.py
git commit -m "feat(charts): tick feed — one Tick subscription per root, budget meter, p-ticket, reconnect backoff

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Hub (shared streams, fan-out, coalescing)

**Files:**
- Create: `homebase/charts/hub.py`, `tests/test_charts_hub.py`

**Interfaces:**
- Consumes: `History` (Task 5), `BarBuilder`, `BarSpec` (Task 3), `make`, `Profile` (Task 4), `from_row`, `SideClassifier`, `BUY` (Task 1), `session_date`, `homebase.contracts.tick_size`.
- Produces: `sessions_back(spec) -> int`; `Stream` (`.key`, `.bars`, `.builder`, `.studies`, `.values`, `.profile`, `.sessions`, `.subs: dict[sub, cursor]`, `.add_study(key)`, `.commit(bar)`, `.payload(fp=True) -> dict`, `.update_since(cursor) -> dict`); `Prepared`; `Hub(history, now_ms)` with `.start_today(root, d, ticks, info=None)`, `.on_ticks(root, rows)`, `.on_clock(now_ms)`, `.prepare(root, spec, study_keys) -> Prepared` (thread-safe), `.attach(prepared) -> Stream`, `.subscribe(stream, sub)`, `.unsubscribe(sub)`, `.drop_conn(conn)`, `.drain() -> list[(sub, msg)]`, `.streams`. A `sub` is a `(conn, chart_id)` tuple.

Wire messages produced:
- history payload: `{"root","spec","tick_size","bars":[wire...],"live":bool,"studies":{key:[value per bar]},"profile":dict|None,"sessions":[info...]}`. The developing bar is the last element when `live` is true.
- update: `{"type":"update","closed":[wire...],"live":wire|None,"studies":{key:{"closed":[...],"live":value}},"profile"?:dict}`.
- reset: `{"type":"reset"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_hub.py`:
```python
"""Hub: history + today, live == fresh rebuild, per-subscriber cursors, reset, roll."""
from __future__ import annotations

import datetime as dt

from homebase.charts.bars import BarSpec
from homebase.charts.history import History
from homebase.charts.hub import Hub
from homebase.charts.store import TickStore
from homebase.charts.tick import SideClassifier, from_row
from tests.charts_util import D, rows, session_ms, write_archive

P = D - dt.timedelta(days=1)
M1 = BarSpec("time", 60)


def setup(tmp_path):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", P, "NQZ6",
                  rows(session_ms(P, 9, 30), [100 + 0.25 * (i % 8) for i in range(300)]))
    clock = [session_ms(D, 9, 31)]
    hub = Hub(History(TickStore(base), cache_dir=tmp_path / "cache"), lambda: clock[0])
    today = rows(session_ms(D, 9, 30), [200 + 0.25 * (i % 5) for i in range(150)],
                 first_id=10_000, sides=[1 if i % 3 else -1 for i in range(150)])
    return hub, today, clock


def ticks_of(rs):
    clf = SideClassifier()
    return [from_row(r, clf) for r in rs]


def open_stream(hub, spec=M1, keys=("vwap", "cumdelta"), sub=("conn", "c1")):
    s = hub.attach(hub.prepare("NQ", spec, list(keys)))
    hub.subscribe(s, sub)
    return s


def test_payload_has_past_sessions_then_today(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:60]), {"date": D.isoformat(), "contract": "NQZ6",
                                                    "source": "live", "approx": False, "gaps": []})
    p = open_stream(hub).payload()
    assert [b["s"] for b in p["bars"]] == [P.isoformat()] * 5 + [D.isoformat()]
    assert p["live"] is True and len(p["studies"]["vwap"]) == 6 and len(p["studies"]["cumdelta"]) == 6
    assert [s["date"] for s in p["sessions"]] == [P.isoformat(), D.isoformat()]
    assert p["tick_size"] == 0.25 and "fp" in p["bars"][0]


def test_live_ticks_end_where_a_fresh_rebuild_starts(tmp_path):
    hub, today, clock = setup(tmp_path)
    hub.start_today("NQ", D, [])
    s = open_stream(hub, keys=("vwap", "cumdelta", "ema:5", "profile"))
    for r in today:
        hub.on_ticks("NQ", [r])
        clock[0] = r["ts_ms"]
        hub.on_clock(r["ts_ms"] - 1500)
    fresh = hub.prepare("NQ", M1, ["vwap", "cumdelta", "ema:5", "profile"]).stream
    assert s.payload() == fresh.payload()


def test_updates_are_per_subscriber_and_coalesced(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, [])
    s = open_stream(hub)
    hub.on_ticks("NQ", today[:130])                 # 2 minutes close, a 3rd develops
    out = hub.drain()
    assert len(out) == 1 and out[0][0] == ("conn", "c1")
    msg = out[0][1]
    assert msg["type"] == "update" and len(msg["closed"]) == 2 and msg["live"] is not None
    assert len(msg["studies"]["vwap"]["closed"]) == 2 and msg["studies"]["vwap"]["live"]
    assert hub.drain() == []                       # nothing new
    late = hub.attach(hub.prepare("NQ", M1, ["vwap"]))
    assert late is s                               # one stream, shared
    hub.subscribe(s, ("conn2", "x"))
    hub.on_ticks("NQ", today[130:131])
    subs = {sub: m for sub, m in hub.drain()}
    assert subs[("conn", "c1")]["closed"] == [] and subs[("conn2", "x")]["closed"] == []


def test_attach_catches_up_ticks_that_arrived_during_prepare(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:50]))
    prep = hub.prepare("NQ", M1, ["vwap"])
    hub.on_ticks("NQ", today[50:140])                # no stream yet: only the tape grows
    s = hub.attach(prep)
    want = hub.prepare("NQ", M1, ["vwap"]).stream
    assert s.payload() == want.payload()


def test_reseeding_today_resets_its_streams(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, [])
    open_stream(hub)
    hub.start_today("NQ", D, ticks_of(today))
    assert hub.drain() == [(("conn", "c1"), {"type": "reset"})]
    assert hub.streams == {}


def test_the_18_et_roll_starts_a_new_tape(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today))
    nxt = D + dt.timedelta(days=1)
    hub.on_ticks("NQ", rows(session_ms(nxt, 18, 1), [300.0], first_id=99_999))
    assert hub.today_date["NQ"] == nxt and len(hub.today["NQ"]) == 1


def test_the_last_unsubscribe_drops_the_stream(tmp_path):
    hub, _, _ = setup(tmp_path)
    hub.start_today("NQ", D, [])
    open_stream(hub, sub=("a", "1"))
    open_stream(hub, sub=("b", "1"))
    hub.unsubscribe(("a", "1"))
    assert len(hub.streams) == 1
    hub.drop_conn("b")
    assert hub.streams == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_hub.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.hub'`

- [ ] **Step 3: Implement**

`homebase/charts/hub.py`:
```python
"""The live chart engine. One Stream per (root, bar type), shared by every
chart showing it. A Stream is built from past sessions (History) plus
today's tape, then advanced tick by tick. The server's pump calls
on_clock()/drain() every 250 ms, so a chart gets at most 4 updates a
second however fast the tape. Each subscriber keeps its own cursor (bars
already sent), so a chart that joins mid-stream never gets a bar twice.

Threading: prepare() does the heavy part (history + today's bars from a
snapshot of the tape) in a worker thread; attach() runs on the event loop,
catches up the ticks that arrived meanwhile, and registers the stream.
Everything else runs on the event loop only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..contracts import tick_size
from .bars import Bar, BarBuilder, BarSpec
from .history import History
from .session import session_date
from .studies import Profile, make
from .tick import BUY, SideClassifier, Tick, from_row


def sessions_back(spec: BarSpec) -> int:
    """Completed sessions loaded behind today, per bar type."""
    if spec.kind != "time" or spec.size < 60:
        return 1
    if spec.size <= 300:
        return 3
    if spec.size <= 3600:
        return 10
    return 60


@dataclass
class Stream:
    root: str
    spec: BarSpec
    tick_size: float
    builder: BarBuilder
    bars: list = field(default_factory=list)       # closed bars, oldest first
    studies: dict = field(default_factory=dict)    # key -> Study
    values: dict = field(default_factory=dict)     # key -> [value per closed bar]
    profile: Profile | None = None
    sessions: list = field(default_factory=list)   # [{date, contract, source, approx, gaps}]
    subs: dict = field(default_factory=dict)       # (conn, chart_id) -> bars already sent
    dirty: bool = False
    reset: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.root, self.spec.key)

    def commit(self, b: Bar) -> None:
        self.bars.append(b)
        for k, st in self.studies.items():
            self.values[k].append(st.push(b))
        if self.profile is not None:
            self.profile.push(b)

    def add_study(self, key: str) -> None:
        if key == "profile":
            if self.profile is None:
                self.profile = Profile(self.tick_size)
                for b in self.bars:
                    self.profile.push(b)
            return
        if key in self.studies:
            return
        st = make(key)
        self.studies[key] = st
        self.values[key] = [st.push(b) for b in self.bars]

    def payload(self, fp: bool = True) -> dict:
        ts, live = self.tick_size, self.builder.cur
        bars = [b.wire(ts, fp) for b in self.bars]
        if live is not None:
            bars.append(live.wire(ts, fp))
        studies = {k: self.values[k] + ([st.preview(live)] if live is not None else [])
                   for k, st in self.studies.items()}
        return {"root": self.root, "spec": self.spec.key, "tick_size": ts, "bars": bars,
                "live": live is not None, "studies": studies,
                "profile": self.profile.value(live) if self.profile is not None else None,
                "sessions": self.sessions}

    def update_since(self, cursor: int) -> dict:
        ts, live = self.tick_size, self.builder.cur
        msg = {"type": "update", "closed": [b.wire(ts) for b in self.bars[cursor:]],
               "live": live.wire(ts) if live is not None else None,
               "studies": {k: {"closed": self.values[k][cursor:],
                               "live": st.preview(live) if live is not None else None}
                           for k, st in self.studies.items()}}
        if self.profile is not None:
            msg["profile"] = self.profile.value(live)
        return msg


@dataclass
class Prepared:
    root: str
    spec: BarSpec
    stream: Stream
    tape: list        # the today-list object the snapshot was taken from
    upto: int         # how many of its ticks the snapshot covered


class Hub:
    def __init__(self, history: History, now_ms):
        self.history = history
        self.store = history.store
        self.now_ms = now_ms
        self.today: dict[str, list[Tick]] = {}
        self.today_date: dict[str, dt.date] = {}
        self.today_info: dict[str, dict] = {}
        self.clf: dict[str, SideClassifier] = {}
        self.streams: dict[tuple[str, str], Stream] = {}

    # ------------------------------------------------------------ today's tape
    def start_today(self, root: str, d: dt.date, ticks: list[Tick], info: dict | None = None) -> None:
        """(Re)seed today's session for root: at startup, after a refill.
        Streams of root are reset (the page resubscribes and rebuilds)."""
        self.today[root] = list(ticks)
        self.today_date[root] = d
        self.today_info[root] = info or {"date": d.isoformat(), "contract": None,
                                         "source": "live", "approx": False, "gaps": []}
        last = ticks[-1] if ticks else None
        self.clf[root] = SideClassifier(last.price if last else None, last.side if last else BUY)
        for s in self.streams.values():
            if s.root == root:
                s.reset = True

    def on_ticks(self, root: str, rows: list[dict]) -> None:
        if not rows:
            return
        if root not in self.clf:
            self.start_today(root, session_date(int(rows[0]["ts_ms"])), [])
        clf = self.clf[root]
        streams = [s for s in self.streams.values() if s.root == root]
        for r in rows:
            tk = from_row(r, clf)
            d = session_date(tk.ts_ms)
            if d != self.today_date[root]:              # 18:00 roll: the old session is on disk
                info = dict(self.today_info[root], date=d.isoformat(), gaps=[])
                self.today[root] = []
                self.today_date[root] = d
                self.today_info[root] = info
                self.history.clear()
                for s in streams:
                    s.sessions.append(info)
            self.today[root].append(tk)
            for s in streams:
                for b in s.builder.add(tk):
                    s.commit(b)
                s.dirty = True

    def on_clock(self, now_ms: int) -> None:
        for s in self.streams.values():
            for b in s.builder.on_clock(now_ms):
                s.commit(b)
                s.dirty = True

    # ------------------------------------------------------------ streams
    def prepare(self, root: str, spec: BarSpec, study_keys: list[str]) -> Prepared:
        """Worker thread: past sessions + today's bars from a snapshot of the tape."""
        ts = tick_size(root)
        today = self.today_date.get(root) or session_date(self.now_ms())
        s = Stream(root, spec, ts, BarBuilder(spec, ts))
        for d in [d for d in self.store.sessions(root) if d < today][-sessions_back(spec):]:
            s.bars.extend(self.history.bars(root, spec, d))
            s.sessions.append(self.history.info(root, d))
        tape = self.today.get(root, [])
        upto = len(tape)
        for tk in tape[:upto]:
            s.bars.extend(s.builder.add(tk))
        info = self.today_info.get(root)
        if info:
            s.sessions.append(info)
        for k in study_keys:
            s.add_study(k)
        return Prepared(root, spec, s, tape, upto)

    def attach(self, p: Prepared) -> Stream:
        """Event loop: register (or reuse) the stream, catching up the ticks
        that arrived while prepare() ran."""
        existing = self.streams.get((p.root, p.spec.key))
        if existing is not None:
            return existing
        s = p.stream
        tape = self.today.get(p.root, [])
        if tape is not p.tape:
            s.reset = True                 # today was reseeded meanwhile: the page resubscribes
        else:
            for tk in tape[p.upto:]:
                for b in s.builder.add(tk):
                    s.commit(b)
        self.streams[s.key] = s
        return s

    def subscribe(self, s: Stream, sub: tuple) -> None:
        s.subs[sub] = len(s.bars)

    def unsubscribe(self, sub: tuple) -> None:
        for k, s in list(self.streams.items()):
            if s.subs.pop(sub, None) is not None and not s.subs:
                del self.streams[k]

    def drop_conn(self, conn) -> None:
        for k, s in list(self.streams.items()):
            for sub in [x for x in s.subs if x[0] is conn]:
                del s.subs[sub]
            if not s.subs:
                del self.streams[k]

    def drain(self) -> list[tuple[tuple, dict]]:
        """(subscriber, message) for everything that changed since the last drain."""
        out: list[tuple[tuple, dict]] = []
        for k, s in list(self.streams.items()):
            if s.reset:
                del self.streams[k]
                out.extend((sub, {"type": "reset"}) for sub in s.subs)
                continue
            n = len(s.bars)
            if not s.dirty and all(c == n for c in s.subs.values()):
                continue
            built: dict[int, dict] = {}
            for sub, c in list(s.subs.items()):
                if c not in built:
                    built[c] = s.update_since(c)
                out.append((sub, built[c]))
                s.subs[sub] = n
            s.dirty = False
        return out
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_charts_hub.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/hub.py tests/test_charts_hub.py
git commit -m "feat(charts): hub — shared streams, per-subscriber cursors, live == fresh rebuild, reset/roll

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Replay feed, server, CLI

**Files:**
- Create: `homebase/charts/replay.py`, `homebase/charts/server.py`, `homebase/charts/__main__.py`, `tests/test_charts_server.py`

**Interfaces:**
- Consumes: everything above; `homebase.paths.state_dir`; `homebase.symbols.resolve_contract`.
- Produces: `ReplayFeed(store, roots, date, on_ticks, speed=10.0, start_et=time(9,25), sleep=asyncio.sleep, wall=time.monotonic)` with `.load() -> {root: rows_before_start}`, `.now_ms()`, `.run()`, `.stop()`, `.status()`, `.contracts`; `create_app(*, roots, base, replay=None, speed=10.0, start_et=time(9,25), feed_factory=None, now_ms=None, state=None) -> FastAPI`; `TIMEFRAMES`; HTTP `GET /`, `GET /api/status`, `GET /api/symbols` → `{"roots":[...],"timeframes":[[label, spec], ...]}`, `GET /api/layouts`, `PUT /api/layouts/{name}`, `DELETE /api/layouts/{name}`, `WS /ws`.
- WS protocol, client → server: `{"op":"sub","id":str,"root":str,"spec":str,"studies":[str],"fp":bool}`, `{"op":"unsub","id":str}`.
- WS protocol, server → client: `{"type":"history","id",...payload}`, `{"type":"update","id",...}`, `{"type":"reset","id"}`, `{"type":"error","id","error"}`, `{"type":"status",...status}`.
- Status includes `mode`, `connected`, `error`, `roots`, `budget_hour`, `recorder`, `streams`, `clients`; replay adds `date`, `speed`, `clock_s`.

- [ ] **Step 1: Write the failing tests**

`tests/test_charts_server.py`:
```python
"""Chart server: replay end-to-end over the websocket, live-mode recording, layouts, errors."""
from __future__ import annotations

import asyncio
import datetime as dt
import queue
import time

from fastapi.testclient import TestClient

from homebase.charts.server import create_app
from homebase.charts.store import read_table
from tests.charts_util import D, rows, session_ms, write_archive

P = D - dt.timedelta(days=1)


def next_of(ws, kind, limit=200):
    for _ in range(limit):
        m = ws.receive_json()
        if m.get("type") == kind:
            return m
    raise AssertionError(f"no {kind!r} message")


def archive(tmp_path):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", P, "NQZ6", rows(session_ms(P, 9, 30), [100.0 + 0.25 * (i % 4) for i in range(120)]))
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0 + 0.25 * (i % 4) for i in range(240)],
                                              first_id=5000))
    return base


def test_replay_serves_history_then_live_updates(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client:
        assert client.get("/api/status").json()["mode"] == "replay"
        assert client.get("/api/symbols").json()["roots"] == ["NQ"]
        assert client.get("/").status_code == 200
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "sub", "id": "a", "root": "nq", "spec": "time:60", "studies": ["vwap", "profile"]})
            hist = next_of(ws, "history")
            assert hist["id"] == "a" and hist["bars"][0]["s"] == P.isoformat()
            assert hist["bars"][-1]["s"] == D.isoformat() and "vwap" in hist["studies"]
            assert hist["profile"]["poc"] > 0
            up = next_of(ws, "update")
            assert up["id"] == "a" and (up["closed"] or up["live"])
    assert not list((tmp_path / "ticks").rglob("*.live.csv.gz"))      # replay never records


def test_bad_requests_get_an_error_not_a_crash(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"op": "sub", "id": "a", "root": "ZZ", "spec": "time:60"})
        assert "not recorded" in next_of(ws, "error")["error"]
        ws.send_json({"op": "sub", "id": "b", "root": "NQ", "spec": "time:0"})
        assert "bad bar type" in next_of(ws, "error")["error"]
        ws.send_json({"op": "sub", "id": "c", "root": "NQ", "spec": "time:60", "studies": ["nope"]})
        assert "unknown study" in next_of(ws, "error")["error"]


def test_layouts_roundtrip(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client:
        lay = {"grid": 2, "cells": [{"root": "NQ", "spec": "time:60", "st": {}}]}
        assert client.put("/api/layouts/main", json=lay).status_code == 200
        assert client.get("/api/layouts").json() == {"main": lay}
        client.delete("/api/layouts/main")
        assert client.get("/api/layouts").json() == {}


def test_live_mode_records_what_the_feed_delivers(tmp_path):
    q: queue.Queue = queue.Queue()

    class FakeFeed:
        def __init__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks, self.ws = on_ticks, None

        async def run(self):
            while True:
                try:
                    self.on_ticks(*q.get_nowait())
                except queue.Empty:
                    await asyncio.sleep(0.01)

        def stop(self):
            pass

        def budget_used(self):
            return 0

        def count_request(self):
            pass

        def status(self):
            return {"mode": "live", "connected": True, "error": None, "roots": {},
                    "budget_hour": 0, "reconnects": 0}

    base = tmp_path / "ticks"
    app = create_app(roots=["NQ"], base=base, feed_factory=FakeFeed,
                     now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state")
    live = base / "NQ" / "2026" / f"{D}_NQZ6.live.csv.gz"
    with TestClient(app) as client:
        q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))
        q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))   # duplicate delivery
        deadline = time.time() + 5
        while not live.exists() and time.time() < deadline:
            time.sleep(0.05)
        st = client.get("/api/status").json()
        assert st["mode"] == "live" and st["recorder"]["error"] is None
    header, recs = read_table(live)
    assert [r[header.index("id")] for r in recs] == ["1", "2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_server.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'homebase.charts.server'`

- [ ] **Step 3: Implement the replay feed**

`homebase/charts/replay.py`:
```python
"""Replay an archived session through the live path — for testing now and
on weekends. Rows go in raw (with quotes), exactly as the broker feed would
deliver them, so the classifier -> bars -> studies -> websocket path is the
live one. Never records. Time is the replay clock.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from .session import ET, et_wall_s
from .store import TickStore, read_table


class ReplayFeed:
    def __init__(self, store: TickStore, roots, date: dt.date, on_ticks, speed: float = 10.0,
                 start_et: dt.time = dt.time(9, 25), sleep=asyncio.sleep, wall=time.monotonic):
        self.store, self.date = store, date
        self.roots = [r.upper() for r in roots]
        self.on_ticks, self.speed = on_ticks, float(speed)
        self._sleep, self._wall = sleep, wall
        day = date - dt.timedelta(days=1) if start_et >= dt.time(18, 0) else date
        self.start_ms = int(dt.datetime.combine(day, start_et, ET).timestamp() * 1000)
        self.rows: dict[str, list[dict]] = {}
        self.contracts: dict[str, str] = {}
        self.last_tick: dict[str, float] = {}
        self._w0: float | None = None
        self._stop = False
        self.done = False

    def load(self) -> dict[str, list[dict]]:
        """Read each root's session. Returns the rows BEFORE the start (the
        page's 'session so far'); the rest is kept for run()."""
        before: dict[str, list[dict]] = {}
        for r in self.roots:
            f = self.store.pick(r, self.date)
            if f is None:
                continue
            header, recs = read_table(f.path)
            allrows = [dict(zip(header, rec)) for rec in recs]
            allrows.sort(key=lambda x: (int(x["ts_ms"]), int(x.get("id") or 0)))
            self.contracts[r] = f.contract
            before[r] = [x for x in allrows if int(x["ts_ms"]) < self.start_ms]
            self.rows[r] = [x for x in allrows if int(x["ts_ms"]) >= self.start_ms]
        return before

    def now_ms(self) -> int:
        if self._w0 is None:
            return self.start_ms
        return int(self.start_ms + (self._wall() - self._w0) * 1000 * self.speed)

    async def run(self) -> None:
        self._w0 = self._wall()
        idx = {r: 0 for r in self.rows}
        while not self._stop and any(idx[r] < len(self.rows[r]) for r in self.rows):
            now = self.now_ms()
            for r, rs in self.rows.items():
                i = j = idx[r]
                while j < len(rs) and int(rs[j]["ts_ms"]) <= now:
                    j += 1
                if j > i:
                    self.on_ticks(r, self.contracts[r], rs[i:j])
                    idx[r] = j
                    self.last_tick[r] = self._wall()
            await self._sleep(0.05)
        self.done = True

    def stop(self) -> None:
        self._stop = True

    def budget_used(self) -> int:
        return 0

    def status(self) -> dict:
        w = self._wall()
        return {"mode": "replay", "date": self.date.isoformat(), "speed": self.speed,
                "clock_s": et_wall_s(self.now_ms()), "connected": True, "error": None,
                "reconnects": 0, "budget_hour": 0, "done": self.done,
                "roots": {r: {"contract": self.contracts.get(r),
                              "last_tick_age_s": (round(w - self.last_tick[r], 1)
                                                  if r in self.last_tick else None)}
                          for r in self.roots}}
```

- [ ] **Step 4: Implement the server**

`homebase/charts/server.py`:
```python
"""The chart service: FastAPI on :8852 — the page, the websocket, layouts,
status. Its own process; the trading app on :8850 only links to it.

    python -m homebase.charts                      # live, from the md feed
    python -m homebase.charts --replay 2026-09-24  # replay a session, records nothing
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import symbols
from ..paths import state_dir
from . import DEFAULT_ROOTS
from .bars import BarSpec
from .history import History
from .hub import Hub
from .recorder import REFILL_MAX_PAGES, LiveRecorder, refill
from .replay import ReplayFeed
from .session import ET, et_wall_s, session_date, session_range_ms
from .store import ARCHIVE, TickStore
from .studies import make
from .tick import SideClassifier, from_row
from .tickfeed import TickFeed

STATIC = Path(__file__).resolve().parent.parent / "static"
PUMP_S = 0.25                 # <= 4 updates a second per chart
CLOSE_GRACE_MS = 1500         # a time bar closes this long after its end if no tick closed it
REFILL_BUDGET = 60            # this process's own chart requests per hour
QUIET = (dt.time(9, 20), dt.time(9, 35))    # never refill across the 9:30 fire
SEND_QUEUE_MAX = 400
TIMEFRAMES = [["5s", "time:5"], ["15s", "time:15"], ["30s", "time:30"], ["1m", "time:60"],
              ["2m", "time:120"], ["3m", "time:180"], ["5m", "time:300"], ["10m", "time:600"],
              ["15m", "time:900"], ["30m", "time:1800"], ["1h", "time:3600"], ["4h", "time:14400"],
              ["1D", "time:86400"], ["500T", "tick:500"], ["1000T", "tick:1000"],
              ["2000V", "volume:2000"], ["10R", "range:10"], ["20R", "range:20"]]


def log(msg: str) -> None:
    print(f"[charts] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", flush=True)


class Conn:
    """One browser socket. Sends go through a bounded queue drained by a
    writer task, so one slow page can never stall the pump; a page that
    falls SEND_QUEUE_MAX messages behind is disconnected (it reconnects)."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.q: asyncio.Queue = asyncio.Queue(maxsize=SEND_QUEUE_MAX)
        self.dead = False
        self.task = asyncio.create_task(self._writer())

    def send(self, msg: dict) -> None:
        if self.dead:
            return
        try:
            self.q.put_nowait(msg)
        except asyncio.QueueFull:
            self.dead = True
            self.task.cancel()
            asyncio.create_task(self._close())

    async def _close(self) -> None:
        try:
            await self.ws.close()
        except Exception:  # noqa: BLE001
            pass

    async def _writer(self) -> None:
        try:
            while True:
                await self.ws.send_json(await self.q.get())
        except Exception:  # noqa: BLE001 — socket gone; the handler cleans up
            self.dead = True


def create_app(*, roots=DEFAULT_ROOTS, base: Path = ARCHIVE, replay: dt.date | None = None,
               speed: float = 10.0, start_et: dt.time = dt.time(9, 25), feed_factory=None,
               now_ms=None, state: Path | None = None) -> FastAPI:
    roots = [r.upper() for r in roots]
    sd = Path(state) if state else state_dir() / "charts"
    sd.mkdir(parents=True, exist_ok=True)
    layouts_path = sd / "layouts.json"
    store = TickStore(base)
    history = History(store, cache_dir=sd / "cache")
    recorder = None if replay else LiveRecorder(base)
    conns: set[Conn] = set()
    start_last: dict[str, int | None] = {}

    def reseed(root: str) -> None:
        """Rebuild today's tape for root from disk (after a refill). Runs on
        the loop and blocks it for a second or two — rare, and this process
        places no orders."""
        if recorder is not None:
            recorder.flush()
        d = session_date(clock())
        sess = store.load(root, d)
        ticks = sess.ticks if sess else []
        hub.start_today(root, d, ticks, {
            "date": d.isoformat(), "contract": sess.contract if sess else symbols.resolve_contract(root),
            "source": "live", "approx": bool(sess and ticks and not sess.bid_ask),
            "gaps": [[et_wall_s(a), et_wall_s(b)] for a, b in (sess.gaps if sess else [])]})

    async def _refill(root: str, contract: str, since_ms: int | None) -> None:
        """After a (re)subscribe: fetch what the socket missed, within budget."""
        d = session_date(clock())
        s0, _ = session_range_ms(d)
        frm = since_ms if since_ms is not None else (start_last.get(root) or s0)
        while QUIET[0] <= dt.datetime.fromtimestamp(clock() / 1000, ET).time() < QUIET[1]:
            await asyncio.sleep(15)
        to = clock()
        if to - frm < 2000:
            return
        rows: list[dict] = []
        reached = to
        if feed.budget_used() + REFILL_MAX_PAGES <= REFILL_BUDGET:
            try:
                rows, reached = await refill(feed.ws, contract, frm, to, on_request=feed.count_request)
            except Exception as e:  # noqa: BLE001 — the missing stretch becomes a marked gap
                log(f"{root}: refill failed: {e}")
        else:
            log(f"{root}: refill skipped — md budget {feed.budget_used()}/h")
        recorder.append(root, contract, rows)
        if reached > frm:
            recorder.mark_gap(root, d, contract, frm, reached)
        log(f"{root}: refilled {len(rows)} ticks"
            + (f", gap {(reached - frm) / 1000:.0f}s marked" if reached > frm else ""))
        reseed(root)

    # the feed is built AFTER reseed/_refill exist (it takes _refill as its
    # callback); every function above only touches feed/hub/clock when called
    if replay:
        feed = ReplayFeed(store, roots, replay, lambda r, c, rows: hub.on_ticks(r, rows),
                          speed=speed, start_et=start_et)
        clock = feed.now_ms
    else:
        clock = now_ms or (lambda: int(time.time() * 1000))

        def on_live(root: str, contract: str, rows: list[dict]) -> None:
            hub.on_ticks(root, recorder.append(root, contract, rows))

        feed = (feed_factory or TickFeed)(roots, on_live, on_subscribed=_refill)
    hub = Hub(history, clock)

    def status() -> dict:
        st = dict(feed.status())
        st["recorder"] = None if recorder is None else {
            "written": recorder.written, "buffered": recorder.buffered, "error": recorder.error}
        st["streams"] = len(hub.streams)
        st["clients"] = len(conns)
        return st

    async def pump() -> None:
        last_flush = last_status = 0.0
        while True:
            await asyncio.sleep(PUMP_S)
            try:
                hub.on_clock(clock() - CLOSE_GRACE_MS)
                for (conn, cid), msg in hub.drain():
                    conn.send({**msg, "id": cid})
                wall = time.monotonic()
                if recorder is not None and wall - last_flush >= 1.0:
                    recorder.flush()
                    last_flush = wall
                if wall - last_status >= 2.0:
                    last_status = wall
                    st = {"type": "status", **status()}
                    for c in list(conns):
                        c.send(st)
            except Exception as e:  # noqa: BLE001 — the pump must never die
                log(f"pump: {type(e).__name__}: {e}")

    @asynccontextmanager
    async def lifespan(_app):
        if replay:
            for r, rs in feed.load().items():
                clf = SideClassifier()
                hub.start_today(r, replay, [from_row(x, clf) for x in rs], {
                    "date": replay.isoformat(), "contract": feed.contracts.get(r),
                    "source": "replay", "approx": False, "gaps": []})
        else:
            d = session_date(clock())
            for r in roots:
                start_last[r] = recorder.last_ts(r, d, symbols.resolve_contract(r))
                reseed(r)
        tasks = [asyncio.create_task(pump()), asyncio.create_task(feed.run())]
        log(f"up — {'replay ' + replay.isoformat() if replay else 'live'} · {', '.join(roots)}")
        try:
            yield
        finally:
            feed.stop()
            for t in tasks:
                t.cancel()
            if recorder is not None:
                recorder.flush()

    app = FastAPI(title="Homebase Charts", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "charts.html")

    @app.get("/api/status")
    async def api_status():
        return status()

    @app.get("/api/symbols")
    async def api_symbols():
        return {"roots": roots, "timeframes": TIMEFRAMES}

    def read_layouts() -> dict:
        try:
            return json.loads(layouts_path.read_text())
        except (OSError, ValueError):
            return {}

    @app.get("/api/layouts")
    async def get_layouts():
        return read_layouts()

    @app.put("/api/layouts/{name}")
    async def put_layout(name: str, request: Request):
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("cells"), list):
            raise HTTPException(400, "a layout is {grid, cells: [...]}")
        all_ = read_layouts()
        all_[name] = body
        layouts_path.write_text(json.dumps(all_, indent=2))
        return {"ok": True}

    @app.delete("/api/layouts/{name}")
    async def delete_layout(name: str):
        all_ = read_layouts()
        all_.pop(name, None)
        layouts_path.write_text(json.dumps(all_, indent=2))
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(sock: WebSocket):
        await sock.accept()
        conn = Conn(sock)
        conns.add(conn)
        conn.send({"type": "status", **status()})
        try:
            while True:
                msg = await sock.receive_json()
                op, cid = msg.get("op"), str(msg.get("id", ""))
                if op == "unsub":
                    hub.unsubscribe((conn, cid))
                    continue
                if op != "sub":
                    continue
                try:
                    root = str(msg.get("root", "")).upper()
                    if root not in roots:
                        raise ValueError(f"{root!r} is not recorded (have {', '.join(roots)})")
                    spec = BarSpec.parse(msg.get("spec", ""))
                    keys = [str(k) for k in msg.get("studies") or []]
                    for k in keys:
                        if k != "profile":
                            make(k)
                except ValueError as e:
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    continue
                hub.unsubscribe((conn, cid))
                s = hub.streams.get((root, spec.key))
                if s is None:
                    s = hub.attach(await asyncio.to_thread(hub.prepare, root, spec, keys))
                for k in keys:
                    s.add_study(k)
                hub.subscribe(s, (conn, cid))
                conn.send({"type": "history", "id": cid, **s.payload(bool(msg.get("fp", True)))})
        except WebSocketDisconnect:
            pass
        finally:
            conns.discard(conn)
            hub.drop_conn(conn)
            conn.task.cancel()

    return app
```

- [ ] **Step 5: Implement the CLI**

`homebase/charts/__main__.py`:
```python
"""python -m homebase.charts [--replay YYYY-MM-DD [--speed 20] [--start 09:25]] [--port 8852]"""
from __future__ import annotations

import argparse
import datetime as dt

import uvicorn

from . import DEFAULT_ROOTS, PORT
from .server import create_app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.charts")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--roots", default=",".join(DEFAULT_ROOTS))
    ap.add_argument("--replay", metavar="YYYY-MM-DD",
                    help="play an archived session instead of the live feed (records nothing)")
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--start", default="09:25", help="replay start, ET HH:MM")
    a = ap.parse_args(argv)
    app = create_app(roots=[r for r in a.roots.split(",") if r],
                     replay=dt.date.fromisoformat(a.replay) if a.replay else None,
                     speed=a.speed, start_et=dt.time.fromisoformat(a.start))
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create a placeholder page so `GET /` works before Task 10: `homebase/static/charts.html` containing `<!doctype html><title>Homebase · Charts</title>` (Task 10 replaces it).

- [ ] **Step 6: Run the tests and the whole suite**

Run: `.venv/bin/python -m pytest tests/test_charts_server.py -q && .venv/bin/python -m pytest -q`
Expected: PASS (all old + new tests)

- [ ] **Step 7: Smoke-run a real replay**

Run: `timeout 20 .venv/bin/python -m homebase.charts --replay 2026-09-24 --speed 30 --port 8853 & sleep 6; curl -s localhost:8853/api/status; wait`
Expected: JSON with `"mode": "replay"` and per-root contracts for NQ/ES/YM (a root with no archive file for that date shows `contract: null`).

- [ ] **Step 8: Commit**

```bash
git add homebase/charts/replay.py homebase/charts/server.py homebase/charts/__main__.py homebase/static/charts.html tests/test_charts_server.py
git commit -m "feat(charts): chart service on :8852 — websocket streams, replay mode, layouts, status, budgeted refill

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Page — grid, candles, live updates

**Files:**
- Create: `homebase/static/vendor/lightweight-charts-5.2.1.js`, `homebase/static/charts/app.js`, `homebase/static/charts/primitives.js`
- Replace: `homebase/static/charts.html`
- Modify: `/Users/ramoscapital/ONYX TRADING/.claude/launch.json` (add a preview config)

**Interfaces:**
- Consumes: the WS protocol and `/api/symbols` (Task 9).
- Produces: a `window.HBLayers` global with `{Footprint, Profile, Gaps}` and a `Cell` class. Task 10 adds candles plus the volume/delta panes; Tasks 11–13 extend the same `Cell` (studies, footprint/profile, status/layouts).

- [ ] **Step 1: Vendor Lightweight Charts v5**

```bash
curl -fsSL -o homebase/static/vendor/lightweight-charts-5.2.1.js https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js
head -c 200 homebase/static/vendor/lightweight-charts-5.2.1.js
```
Expected: the license banner naming `Lightweight Charts™ v5.2.1`.

- [ ] **Step 2: Write the page shell**

`homebase/static/charts.html`:
```html
<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Homebase · Charts</title>
<script>
  try{ var _t = localStorage.getItem('hb_theme');
    document.documentElement.setAttribute('data-theme', (_t==='light'||_t==='dark') ? _t : 'light');
  }catch(_){ document.documentElement.setAttribute('data-theme','light'); }
</script>
<link rel="stylesheet" href="/static/shadcn.css">
<style>
  html, body { height: 100%; margin: 0; }
  body { display: flex; flex-direction: column; background: var(--background); color: var(--foreground); }
  .inset-topbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  .spacer { flex: 1; }
  #grid { flex: 1; display: grid; gap: 4px; padding: 4px; min-height: 0; }
  .cell { position: relative; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden;
          border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--card); }
  .cell-bar { display: flex; gap: 6px; align-items: center; padding: 4px 6px; border-bottom: 1px solid var(--border); font-size: 12px; }
  .cell-bar select, .cell-bar input, .studies-pop select, .studies-pop input, #layoutName {
    font: inherit; font-size: 12px; background: var(--background); color: var(--foreground);
    border: 1px solid var(--border); border-radius: 6px; padding: 2px 4px; }
  .cell-chart { flex: 1; min-height: 0; position: relative; }
  .cell-msg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
              color: var(--muted-foreground); font-size: 13px; pointer-events: none; z-index: 4; }
  .legend { position: absolute; left: 8px; top: 6px; z-index: 3; font: 11px ui-monospace, SFMono-Regular, Menlo, monospace;
            color: var(--muted-foreground); pointer-events: none; white-space: nowrap; }
  .studies-pop { position: absolute; right: 6px; top: 32px; z-index: 6; display: none; padding: 8px 10px; font-size: 12px;
                 background: var(--card); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18);
                 max-height: 70%; overflow: auto; }
  .studies-pop.open { display: block; }
  .studies-pop label { display: flex; align-items: center; gap: 6px; padding: 2px 0; white-space: nowrap; }
  .studies-pop input[type=number] { width: 56px; }
  .studies-pop small { color: var(--muted-foreground); }
  #status { display: flex; gap: 10px; align-items: center; padding: 4px 12px; border-top: 1px solid var(--border);
            font-size: 12px; color: var(--muted-foreground); }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: var(--muted-foreground); }
  .dot.ok { background: #16a34a; } .dot.warn { background: #d97706; } .dot.bad { background: #dc2626; }
</style>
</head>
<body>
<header class="inset-topbar">
  <span style="font-weight:600;font-size:0.9375rem;letter-spacing:-.01em">Homebase</span>
  <a class="btn btn-outline btn-sm" id="navDesk" href="#">Desk</a>
  <span class="pill idle">Charts</span>
  <span class="spacer"></span>
  <select id="gridSel" class="btn btn-outline btn-sm" title="Charts on screen">
    <option value="1">1 chart</option><option value="2">2 charts</option>
    <option value="4">2 × 2</option><option value="6">3 × 2</option>
  </select>
  <select id="layoutSel" class="btn btn-outline btn-sm"></select>
  <input id="layoutName" size="12" placeholder="layout name">
  <button class="btn btn-outline btn-sm" id="saveLayout" type="button">Save layout</button>
  <button class="btn btn-outline btn-sm" id="themeToggle" type="button">Theme</button>
</header>
<div id="grid"></div>
<footer id="status"><span class="dot" id="feedDot"></span><span id="feedText">connecting…</span><span class="spacer"></span><span id="budgetText"></span></footer>
<script src="/static/vendor/lightweight-charts-5.2.1.js"></script>
<script src="/static/charts/primitives.js"></script>
<script src="/static/charts/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Write the layer stubs (filled in Task 12)**

`homebase/static/charts/primitives.js`:
```js
/* Homebase Charts — canvas layers drawn inside Lightweight Charts v5 panes
   (series primitives). Task 12 fills in the drawing. */
(function () {
'use strict';
class Layer {
  constructor(P) { this.P = P; this._views = [{ zOrder: () => this.z(), renderer: () => ({ draw: (t) => this.draw(t) }) }]; }
  z() { return 'top'; }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() {}
  paneViews() { return this._views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }
  draw() {}
}
class Footprint extends Layer { set() {} readable() { return false; } }
class Profile extends Layer { set() {} }
class Gaps extends Layer { set() {} }
window.HBLayers = { Footprint, Profile, Gaps, Layer };
})();
```

- [ ] **Step 4: Write the page logic**

`homebase/static/charts/app.js`:
```js
/* Homebase Charts — the page. One websocket to the chart service (:8852);
   each grid cell is a Cell that subscribes one (root, bar type, studies)
   stream. The server computes everything (bars, footprint, studies,
   profile); this file only draws. Bar times arrive as ET wall-clock
   seconds, so the axis reads ET. Tick/volume/range bars sit on an evenly
   spaced synthetic axis (many can share one second) and are labelled with
   their real times. */
(() => {
'use strict';
const LW = window.LightweightCharts;
const { Footprint, Profile, Gaps } = window.HBLayers;
const FAKE0 = 946684800;
const GRIDS = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] };
const ST0 = { vwap: true, vwapAnchor: 'eth', vwapBands: false, ema1: 0, ema2: 0, sma: 0, vwma: 0,
  levels: true, volume: true, delta: false, cumdelta: false, adx: 0,
  footprint: true, imbalance: 3, profile: false, bigMin: 0 };
const CELLS0 = [['NQ', 'time:60'], ['NQ', 'time:300'], ['ES', 'time:60'], ['YM', 'time:60'],
  ['NQ', 'tick:1000'], ['NQ', 'time:900']].map(([root, spec]) => ({ root, spec, st: { ...ST0 } }));
const FORM = [
  ['vwap', 'VWAP', 'check'], ['vwapAnchor', 'VWAP anchor', 'select', ['eth', 'rth']], ['vwapBands', 'VWAP 1σ / 2σ bands', 'check'],
  ['ema1', 'EMA', 'num'], ['ema2', 'EMA', 'num'], ['sma', 'SMA', 'num'], ['vwma', 'VWMA', 'num'],
  ['levels', 'Session levels', 'check'], ['volume', 'Volume', 'check'], ['delta', 'Delta', 'check'],
  ['cumdelta', 'Cum. delta', 'check'], ['adx', 'ADX', 'num'], ['footprint', 'Footprint', 'check'],
  ['imbalance', 'Imbalance ×', 'num'], ['profile', 'Volume profile', 'check'], ['bigMin', 'Big prints ≥', 'num'],
];
const LEVELS = [['pdh', 'PDH'], ['pdl', 'PDL'], ['pdc', 'PDC'], ['onh', 'ONH'], ['onl', 'ONL'], ['rth_open', 'Open']];

let meta = { roots: ['NQ'], timeframes: [['1m', 'time:60']] };
let ws = null;
let layout = { grid: 4, cells: CELLS0.map((c) => JSON.parse(JSON.stringify(c))) };
const cells = new Map();
let nextId = 1;

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const iso = (t) => new Date(t * 1000).toISOString();

function palette() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return dark
    ? { bg: '#0a0a0a', text: '#a1a1aa', grid: '#1c1c1f', up: '#22c55e', down: '#ef4444',
        upA: 'rgba(34,197,94,.5)', downA: 'rgba(239,68,68,.5)', lines: ['#60a5fa', '#f59e0b', '#c084fc', '#2dd4bf'],
        vwap: '#e879f9', band: 'rgba(232,121,249,.45)', level: '#94a3b8', fpText: '#d4d4d8', fpBg: 'rgba(255,255,255,.06)',
        poc: '#fbbf24', va: 'rgba(96,165,250,.14)', vaIn: 'rgba(96,165,250,.30)', gap: 'rgba(148,163,184,.16)' }
    : { bg: '#ffffff', text: '#52525b', grid: '#f1f1f3', up: '#16a34a', down: '#dc2626',
        upA: 'rgba(22,163,74,.45)', downA: 'rgba(220,38,38,.45)', lines: ['#2563eb', '#d97706', '#9333ea', '#0d9488'],
        vwap: '#c026d3', band: 'rgba(192,38,211,.4)', level: '#64748b', fpText: '#27272a', fpBg: 'rgba(0,0,0,.05)',
        poc: '#d97706', va: 'rgba(37,99,235,.10)', vaIn: 'rgba(37,99,235,.22)', gap: 'rgba(100,116,139,.14)' };
}

function studyKeys(st) {
  const k = [];
  if (st.vwap) k.push(st.vwapAnchor === 'rth' ? 'vwap:rth' : 'vwap');
  for (const [f, name] of [['ema1', 'ema'], ['ema2', 'ema'], ['sma', 'sma'], ['vwma', 'vwma']]) if (+st[f] > 0) k.push(`${name}:${+st[f]}`);
  if (st.levels) k.push('levels');
  if (st.cumdelta) k.push('cumdelta');
  if (+st.adx > 0) k.push(`adx:${+st.adx}`);
  if (st.profile) k.push('profile');
  return [...new Set(k)];
}

class Cell {
  constructor(el, cfg) {
    this.el = el; this.cfg = cfg; this.id = 'c' + (nextId++); cells.set(this.id, this);
    this.bars = []; this.devel = false; this.chart = null; this.sessions = [];
    this.el.innerHTML = `
      <div class="cell-bar">
        <select class="root"></select><select class="spec"></select>
        <input class="custom" size="9" placeholder="tick:750" title="Custom bar type: time:SECONDS, tick:TRADES, volume:CONTRACTS, range:TICKS">
        <span class="spacer"></span>
        <span class="approx pill idle" hidden title="Part of this history has no bid/ask: the buy/sell split there is by tick rule">≈ flow</span>
        <button class="btn btn-outline btn-sm st-btn" type="button">Studies</button>
      </div>
      <div class="cell-chart"><div class="legend"></div><div class="cell-msg">connecting…</div></div>
      <div class="studies-pop"></div>`;
    this.fillControls();
    this.subscribe();
  }

  isTime() { return this.cfg.spec.startsWith('time:'); }

  fillControls() {
    const root = $('.root', this.el), spec = $('.spec', this.el), custom = $('.custom', this.el);
    root.innerHTML = meta.roots.map((r) => `<option ${r === this.cfg.root ? 'selected' : ''}>${esc(r)}</option>`).join('');
    const known = meta.timeframes.some(([, v]) => v === this.cfg.spec);
    spec.innerHTML = meta.timeframes.map(([l, v]) => `<option value="${esc(v)}" ${v === this.cfg.spec ? 'selected' : ''}>${esc(l)}</option>`).join('')
      + (known ? '' : `<option value="${esc(this.cfg.spec)}" selected>${esc(this.cfg.spec)}</option>`);
    root.onchange = () => { this.cfg.root = root.value; this.changed(); };
    spec.onchange = () => { this.cfg.spec = spec.value; this.changed(); };
    custom.onkeydown = (e) => {
      if (e.key !== 'Enter' || !custom.value.trim()) return;
      this.cfg.spec = custom.value.trim(); custom.value = ''; this.fillControls(); this.changed();
    };
    const pop = $('.studies-pop', this.el);
    pop.innerHTML = FORM.map(([k, label, kind, opts]) => {
      const v = this.cfg.st[k];
      if (kind === 'check') return `<label><input type="checkbox" data-k="${k}" ${v ? 'checked' : ''}> ${label}</label>`;
      if (kind === 'num') return `<label>${label} <input type="number" min="0" data-k="${k}" value="${+v || 0}"> <small>0 = off</small></label>`;
      return `<label>${label} <select data-k="${k}">${opts.map((o) => `<option ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select></label>`;
    }).join('');
    pop.onchange = (e) => {
      const k = e.target.dataset.k; if (!k) return;
      this.cfg.st[k] = e.target.type === 'checkbox' ? e.target.checked : (e.target.type === 'number' ? +e.target.value : e.target.value);
      this.changed();
    };
    $('.st-btn', this.el).onclick = () => pop.classList.toggle('open');
  }

  changed() { saveLast(); this.subscribe(); }

  msg(text) { const m = $('.cell-msg', this.el); m.textContent = text || ''; m.hidden = !text; }

  subscribe() {
    if (!ws || ws.readyState !== 1) return;
    this.msg('loading…');
    ws.send(JSON.stringify({ op: 'sub', id: this.id, root: this.cfg.root, spec: this.cfg.spec,
      studies: studyKeys(this.cfg.st), fp: true }));
  }

  destroy() {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ op: 'unsub', id: this.id }));
    if (this.chart) this.chart.remove();
    cells.delete(this.id);
  }

  real(tt) { return this.isTime() ? tt : (this.realT.get(tt) ?? tt); }
  fullTime(tt) { return iso(this.real(tt)).slice(0, 19).replace('T', ' ') + ' ET'; }
  specLabel() { const t = meta.timeframes.find(([, v]) => v === this.cfg.spec); return t ? t[0] : this.cfg.spec; }

  makeChart() {
    if (this.chart) this.chart.remove();
    const P = this.P = palette(), box = $('.cell-chart', this.el);
    const sub = this.isTime() && +this.cfg.spec.split(':')[1] < 60;
    this.chart = LW.createChart(box, {
      autoSize: true,
      layout: { background: { type: 'solid', color: P.bg }, textColor: P.text, fontSize: 11,
        panes: { separatorColor: P.grid, enableResize: true } },
      grid: { vertLines: { color: P.grid }, horzLines: { color: P.grid } },
      rightPriceScale: { borderColor: P.grid },
      timeScale: { borderColor: P.grid, timeVisible: true, secondsVisible: sub,
        tickMarkFormatter: (t, type) => { const s = iso(this.real(t)); return type <= 2 ? s.slice(5, 10) : (type === 4 ? s.slice(11, 19) : s.slice(11, 16)); } },
      localization: { timeFormatter: (t) => this.fullTime(t) },
      crosshair: { mode: LW.CrosshairMode.Normal },
    });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, { upColor: P.up, downColor: P.down,
      wickUpColor: P.up, wickDownColor: P.down, borderVisible: false });
    this.markers = LW.createSeriesMarkers(this.candles, []);
    this.fp = new Footprint(P); this.prof = new Profile(P); this.gaps = new Gaps(P);
    for (const l of [this.gaps, this.prof, this.fp]) this.candles.attachPrimitive(l);
    this.series = {}; this.levelLines = {}; this.paneOf = {}; this.panes = 0; this.fpShown = false;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.syncFootprint());
    this.chart.subscribeCrosshairMove((p) => this.legend(p && p.logical != null ? Math.round(p.logical) : null));
  }

  pane(name) { if (!(name in this.paneOf)) this.paneOf[name] = ++this.panes; return this.paneOf[name]; }

  line(key, color, width = 1, pane = 0, style = 0) {
    const s = this.chart.addSeries(LW.LineSeries, { color, lineWidth: width, lineStyle: style,
      priceLineVisible: false, lastValueVisible: pane > 0, crosshairMarkerVisible: false }, pane);
    this.series[key] = s; return s;
  }

  append(b) {
    const last = this.bars[this.bars.length - 1];
    b.tt = this.isTime() ? b.t : FAKE0 + this.bars.length * 60;
    if (last && b.tt <= last.tt) b.tt = last.tt + 1;
    if (!this.isTime()) this.realT.set(b.tt, b.t);
    this.bars.push(b);
  }

  replaceLast(b) {
    const i = this.bars.length - 1;
    b.tt = this.bars[i].tt;
    if (!this.isTime()) this.realT.set(b.tt, b.t);
    this.bars[i] = b;
  }

  candle(b) { return { time: b.tt, open: b.o, high: b.h, low: b.l, close: b.c }; }

  point(key, b) {
    const P = this.P, time = b.tt;
    if (key === '__vol') return { time, value: b.v, color: b.d >= 0 ? P.upA : P.downA };
    if (key === '__delta') return { time, value: b.d, color: b.d >= 0 ? P.upA : P.downA };
    const [base, part] = key.split('#');
    const v = b.sv ? b.sv[base] : null;
    if (v == null) return { time };
    if (typeof v === 'number') return { time, value: v };
    if (base.startsWith('vwap')) {
      if (v.vwap == null) return { time };
      return { time, value: v.vwap + ({ u1: 1, l1: -1, u2: 2, l2: -2 }[part] || 0) * v.sd };
    }
    if (base.startsWith('adx')) { const x = part === 'p' ? v.pdi : part === 'm' ? v.mdi : v.adx; return x == null ? { time } : { time, value: x }; }
    return { time };
  }

  onHistory(m) {
    this.makeChart();
    this.tick = m.tick_size; this.sessions = m.sessions || [];
    this.bars = []; this.realT = new Map(); this.devel = !!m.live;
    m.bars.forEach((b, i) => { b.sv = {}; for (const k in m.studies) b.sv[k] = m.studies[k][i]; this.append(b); });
    this.candles.setData(this.bars.map((b) => this.candle(b)));
    const st = this.cfg.st;
    if (st.volume) this.series.__vol = this.chart.addSeries(LW.HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, this.pane('volume'));
    if (st.delta) this.series.__delta = this.chart.addSeries(LW.HistogramSeries, { priceLineVisible: false }, this.pane('delta'));
    this.addStudySeries(Object.keys(m.studies || {}));
    this.redrawAll();
    for (const [name, idx] of Object.entries(this.paneOf)) { const pane = this.chart.panes()[idx]; if (pane) pane.setHeight(name === 'volume' ? 70 : 90); }
    $('.approx', this.el).hidden = !this.sessions.some((s) => s.approx);
    this.prof.set(m.profile, this.tick);
    this.msg('');
    this.chart.timeScale().scrollToRealTime();
    this.legend(null);
  }

  addStudySeries() {}          // Task 11

  redrawAll() {
    for (const [key, s] of Object.entries(this.series)) s.setData(this.bars.map((b) => this.point(key, b)));
    this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint();
  }

  onUpdate(m) {
    if (!this.chart) return;
    const touched = [];
    const vals = (i, live) => { const o = {}; for (const k in m.studies) o[k] = live ? m.studies[k].live : m.studies[k].closed[i]; return o; };
    m.closed.forEach((b, i) => { b.sv = vals(i, false); if (i === 0 && this.devel) this.replaceLast(b); else this.append(b); touched.push(b); });
    if (m.live) { m.live.sv = vals(0, true); if (!m.closed.length && this.devel) this.replaceLast(m.live); else this.append(m.live); touched.push(m.live); }
    this.devel = !!m.live;
    for (const b of touched) {
      this.candles.update(this.candle(b));
      for (const [key, s] of Object.entries(this.series)) s.update(this.point(key, b));
    }
    if (m.profile !== undefined) this.prof.set(m.profile, this.tick);
    if (touched.some((b) => b.big && b.big.length)) this.drawMarkers();
    this.drawLevels(); this.syncFootprint();
    this.legend(null);
  }

  drawMarkers() {}             // Task 11
  drawLevels() {}              // Task 11
  drawGaps() {}                // Task 13
  syncFootprint() {}           // Task 12

  legend(i) {
    const el = $('.legend', this.el);
    const b = i == null ? this.bars[this.bars.length - 1] : this.bars[Math.max(0, Math.min(i, this.bars.length - 1))];
    if (!b) { el.textContent = ''; return; }
    el.textContent = `${this.cfg.root} ${this.specLabel()}  ${this.fullTime(b.tt)}  O ${b.o}  H ${b.h}  L ${b.l}  C ${b.c}  V ${b.v}  Δ ${b.d > 0 ? '+' : ''}${b.d}`;
  }
}

function buildGrid() {
  for (const c of [...cells.values()]) c.destroy();
  const grid = $('#grid'), [cols, rows] = GRIDS[layout.grid] || GRIDS[4];
  grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  grid.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  grid.innerHTML = '';
  while (layout.cells.length < cols * rows) {
    const c = CELLS0[layout.cells.length % CELLS0.length];
    layout.cells.push({ root: c.root, spec: c.spec, st: { ...ST0 } });
  }
  for (let i = 0; i < cols * rows; i++) {
    const el = document.createElement('div'); el.className = 'cell'; grid.appendChild(el);
    layout.cells[i].st = { ...ST0, ...(layout.cells[i].st || {}) };
    new Cell(el, layout.cells[i]);
  }
  $('#gridSel').value = String(layout.grid);
}

function showStatus() {}         // Task 13
function loadLayouts() {}        // Task 13
function saveLayout() {}         // Task 13
function saveLast() { try { localStorage.setItem('hb_charts_last', JSON.stringify(layout)); } catch (_) {} }
function loadLast() { try { const v = JSON.parse(localStorage.getItem('hb_charts_last') || 'null'); if (v && Array.isArray(v.cells)) layout = v; } catch (_) {} }

function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { for (const c of cells.values()) c.subscribe(); };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === 'status') { showStatus(m); return; }
    const c = cells.get(m.id); if (!c) return;
    if (m.type === 'history') c.onHistory(m);
    else if (m.type === 'update') c.onUpdate(m);
    else if (m.type === 'reset') c.subscribe();
    else if (m.type === 'error') c.msg(m.error);
  };
  ws.onclose = () => { showStatus({ connected: false, error: 'chart service unreachable — retrying' }); setTimeout(connect, 2000); };
}

async function init() {
  $('#navDesk').href = `${location.protocol}//${location.hostname}:8850/`;
  try { const r = await fetch('/api/symbols'); if (r.ok) meta = await r.json(); } catch (_) {}
  loadLast();
  $('#gridSel').onchange = (e) => { layout.grid = +e.target.value; saveLast(); buildGrid(); };
  $('#saveLayout').onclick = () => saveLayout();
  $('#themeToggle').onclick = () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('hb_theme', next); } catch (_) {}
    for (const c of cells.values()) c.subscribe();
  };
  buildGrid(); loadLayouts(); connect();
}

window.HBCharts = { Cell, cells, palette, studyKeys, LEVELS, get layout() { return layout; }, set layout(v) { layout = v; },
  buildGrid, saveLast, get ws() { return ws; } };
init();
})();
```
(Tasks 11–13 replace the one-line stubs marked with their task number. Always edit these stubs in `app.js`; don't redefine them from outside the file.)

- [ ] **Step 5: Add a preview launcher**

Add this entry to the `configurations` array in `/Users/ramoscapital/ONYX TRADING/.claude/launch.json`. Keep the existing entries.
```json
{
  "name": "homebase-charts-replay",
  "runtimeExecutable": "/bin/sh",
  "runtimeArgs": ["-c", "cd /Users/ramoscapital/ramos-quant-homebase && exec .venv/bin/python -m homebase.charts --replay 2026-09-24 --speed 20 --start 09:25 --port 8853"],
  "port": 8853
}
```

- [ ] **Step 6: Verify in the browser**

`preview_start {name: "homebase-charts-replay"}`. Then `read_console_messages {onlyErrors: true}`, which should show no errors. Take a `computer {action: "screenshot"}`: a 2×2 grid with NQ 1m / NQ 5m / ES 1m / YM 1m candles and a volume pane, with the last candle moving. Switch one cell to `1000T`: the axis shows real HH:MM labels and candles keep streaming.

- [ ] **Step 7: Commit**

```bash
git add homebase/static/charts.html homebase/static/charts homebase/static/vendor/lightweight-charts-5.2.1.js
git commit -m "feat(charts): the page — grid of live candle charts on LWC v5 over the chart websocket

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Page — studies, session levels, big prints

**Files:**
- Modify: `homebase/static/charts/app.js` (replace the `addStudySeries`, `drawMarkers`, `drawLevels` stubs)

- [ ] **Step 1: Implement the three methods in `Cell`**

```js
  addStudySeries(keys) {
    const P = this.P, st = this.cfg.st;
    let ci = 0;
    for (const key of keys) {
      const name = key.split(':')[0];
      if (name === 'ema' || name === 'sma' || name === 'vwma') this.line(key, P.lines[ci++ % P.lines.length]);
      else if (name === 'vwap') {
        this.line(key, P.vwap, 2);
        if (st.vwapBands) for (const b of ['u1', 'l1', 'u2', 'l2']) this.line(`${key}#${b}`, P.band, 1, 0, 2);
      } else if (name === 'cumdelta') this.line(key, P.lines[1], 1, this.pane('cumdelta'));
      else if (name === 'adx') {
        const p = this.pane('adx');
        this.line(key, P.text, 2, p); this.line(`${key}#p`, P.up, 1, p); this.line(`${key}#m`, P.down, 1, p);
      }
    }
  }

  drawMarkers() {
    const min = +this.cfg.st.bigMin || 0, P = this.P;
    if (!min) { this.markers.setMarkers([]); return; }
    const out = [];
    for (const b of this.bars) for (const [, , size, side] of (b.big || [])) {
      if (size >= min) out.push({ time: b.tt, position: side > 0 ? 'belowBar' : 'aboveBar',
        color: side > 0 ? P.up : P.down, shape: 'circle', size: 0.6, text: String(size) });
    }
    this.markers.setMarkers(out.slice(-600));
  }

  drawLevels() {
    const last = this.bars[this.bars.length - 1], lv = last && last.sv ? last.sv.levels : null;
    for (const [k, title] of LEVELS) {
      const px = lv ? lv[k] : null, cur = this.levelLines[k];
      if (px == null) { if (cur) { this.candles.removePriceLine(cur); delete this.levelLines[k]; } continue; }
      if (cur) { if (cur.options().price !== px) cur.applyOptions({ price: px }); continue; }
      this.levelLines[k] = this.candles.createPriceLine({ price: px, color: this.P.level, lineWidth: 1,
        lineStyle: LW.LineStyle.Dashed, axisLabelVisible: true, title });
    }
  }
```

- [ ] **Step 2: Verify in the browser**

Reload the preview (`javascript_tool: location.reload()`). In one NQ 1m cell open Studies and turn on EMA 20, VWAP bands, Cum. delta, ADX 14 and Big prints ≥ 20.

Expected:
- The VWAP (magenta) and its dashed bands and the EMA line track price.
- Dashed PDH/PDL/PDC/ONH/ONL/Open price lines appear with axis labels.
- The volume, cum-delta and ADX panes stack below the price pane.
- Green circles (buys) sit below and red circles (sells) above bars that have ≥ 20-lot prints.
- Everything keeps updating as the replay runs.

Check with `read_console_messages {onlyErrors: true}` (should be none), then take a screenshot.

- [ ] **Step 3: Commit**

```bash
git add homebase/static/charts/app.js
git commit -m "feat(charts): page studies — VWAP/bands, EMA/SMA/VWMA, cum-delta and ADX panes, session levels, big prints

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Page — footprint and volume profile layers

**Files:**
- Modify: `homebase/static/charts/primitives.js` (full implementation), `homebase/static/charts/app.js` (replace the `syncFootprint` stub)

- [ ] **Step 1: Implement the layers**

Replace the whole of `homebase/static/charts/primitives.js`:
```js
/* Homebase Charts — canvas layers drawn inside Lightweight Charts v5 panes
   (series primitives): footprint cells, session volume profile, data gaps.
   Pure drawing: the server already computed every number. */
(function () {
'use strict';
const key = (px) => +(+px).toFixed(6);

class Layer {
  constructor(P) { this.P = P; this._views = [{ zOrder: () => this.z(), renderer: () => ({ draw: (t) => this.draw(t) }) }]; }
  z() { return 'top'; }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() {}
  paneViews() { return this._views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }
  draw() {}
  spacing() {
    const ts = this.chart.timeScale(), a = ts.logicalToCoordinate(0), b = ts.logicalToCoordinate(1);
    return (a == null || b == null) ? 0 : b - a;
  }
  rowH(px, tick) {
    const a = this.series.priceToCoordinate(px), b = this.series.priceToCoordinate(px + tick);
    return (a == null || b == null) ? 0 : Math.abs(a - b);
  }
}

/* Per bar and price: "sells at bid | buys at ask", a volume bar behind, the
   bar's POC boxed, and diagonal imbalances coloured (buys at P vs sells one
   tick below; sells at P vs buys one tick above) at `ratio`:1. Drawn only
   when zoomed in far enough to read. */
class Footprint extends Layer {
  constructor(P) { super(P); this.bars = []; this.ratio = 0; this.tick = 0.25; this.on = false; }
  set(bars, on, ratio, tick) { this.bars = bars; this.on = on; this.ratio = ratio; this.tick = tick; this.redraw(); }
  readable() {
    if (!this.on || !this.chart || !this.series || !this.bars.length) return false;
    const last = this.bars[this.bars.length - 1];
    return this.spacing() >= 56 && this.rowH(last.c, this.tick) >= 9;
  }
  draw(target) {
    if (!this.readable()) return;
    const ts = this.chart.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
    const i0 = Math.max(0, Math.floor(r.from)), i1 = Math.min(this.bars.length - 1, Math.ceil(r.to));
    const w = this.spacing() * 0.86, P = this.P, tick = this.tick;
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const rh = this.rowH(this.bars[i1].c, tick);
      ctx.font = `${Math.max(8, Math.min(11, rh - 2))}px ui-monospace, SFMono-Regular, Menlo, monospace`;
      ctx.textBaseline = 'middle';
      for (let i = i0; i <= i1; i++) {
        const b = this.bars[i]; if (!b || !b.fp || !b.fp.length) continue;
        const x = ts.logicalToCoordinate(i); if (x == null) continue;
        const at = new Map(b.fp.map((row) => [key(row[0]), row]));
        let maxV = 1, poc = b.fp[0];
        for (const row of b.fp) { const v = row[1] + row[2]; if (v > maxV) maxV = v; if (v > poc[1] + poc[2]) poc = row; }
        for (const [px, sv, bv] of b.fp) {
          const y = this.series.priceToCoordinate(px); if (y == null) continue;
          ctx.fillStyle = P.fpBg; ctx.fillRect(x - w / 2, y - rh / 2, w * (sv + bv) / maxV, rh - 1);
          const below = at.get(key(px - tick)), above = at.get(key(px + tick));
          const buyImb = this.ratio > 0 && bv > 0 && bv >= this.ratio * Math.max(below ? below[1] : 0, 1);
          const sellImb = this.ratio > 0 && sv > 0 && sv >= this.ratio * Math.max(above ? above[2] : 0, 1);
          ctx.textAlign = 'right'; ctx.fillStyle = sellImb ? P.down : P.fpText; ctx.fillText(String(sv), x - 3, y);
          ctx.textAlign = 'left'; ctx.fillStyle = buyImb ? P.up : P.fpText; ctx.fillText(String(bv), x + 3, y);
          if (px === poc[0]) { ctx.strokeStyle = P.poc; ctx.lineWidth = 1; ctx.strokeRect(x - w / 2, y - rh / 2, w, rh - 1); }
        }
      }
    });
  }
}

/* Session volume profile on the right edge: POC highlighted, value area darker. */
class Profile extends Layer {
  constructor(P) { super(P); this.p = null; this.tick = 0.25; }
  z() { return 'bottom'; }
  set(p, tick) { this.p = p; this.tick = tick; this.redraw(); }
  draw(target) {
    const p = this.p; if (!p || !this.series || !p.rows || !p.rows.length) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      let maxV = 1; for (const r of p.rows) if (r[1] > maxV) maxV = r[1];
      const W = mediaSize.width * 0.18, rh = Math.max(1, this.rowH(p.poc, this.tick) - 0.5);
      for (const [px, v] of p.rows) {
        const y = this.series.priceToCoordinate(px); if (y == null) continue;
        ctx.fillStyle = px === p.poc ? this.P.poc : (px >= p.val && px <= p.vah ? this.P.vaIn : this.P.va);
        const w = W * v / maxV; ctx.fillRect(mediaSize.width - w, y - rh / 2, w, rh);
      }
    });
  }
}

/* Shaded "no data" bands after the given bar indices (recording gaps). */
class Gaps extends Layer {
  constructor(P) { super(P); this.idx = []; }
  z() { return 'bottom'; }
  set(indices) { this.idx = indices; this.redraw(); }
  draw(target) {
    if (!this.chart || !this.idx.length) return;
    const ts = this.chart.timeScale(), sp = Math.max(this.spacing(), 2);
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.font = '10px system-ui, sans-serif'; ctx.textAlign = 'center';
      for (const i of this.idx) {
        const x = ts.logicalToCoordinate(i + 0.5); if (x == null) continue;
        ctx.fillStyle = this.P.gap; ctx.fillRect(x - sp / 2, 0, sp, mediaSize.height);
        ctx.fillStyle = this.P.text; ctx.fillText('no data', x, 12);
      }
    });
  }
}

window.HBLayers = { Footprint, Profile, Gaps, Layer };
})();
```

- [ ] **Step 2: Implement `syncFootprint` in `Cell` (replace the stub)**

```js
  syncFootprint() {
    if (!this.fp) return;
    this.fp.set(this.bars, !!this.cfg.st.footprint, +this.cfg.st.imbalance || 0, this.tick);
    const on = this.fp.readable(), P = this.P;
    if (on !== this.fpShown) {
      this.fpShown = on;       // footprint visible: hide candle bodies, keep the wicks
      this.candles.applyOptions(on ? { upColor: 'rgba(0,0,0,0)', downColor: 'rgba(0,0,0,0)' } : { upColor: P.up, downColor: P.down });
    }
  }
```

- [ ] **Step 3: Verify in the browser**

Reload. Set a cell to NQ 1m with Footprint and Volume profile on, then zoom in with scroll or pinch until the bars are wide.

Expected:
- Each bar shows `sells | buys` numbers per price over a faint volume bar. The candle bodies disappear (wicks stay) and the POC is boxed.
- Imbalanced cells are coloured green (buy) or red (sell).
- Zooming out restores normal candles.
- The profile shows as horizontal bars on the right edge, with the POC amber and the value area darker.

Check `read_console_messages {onlyErrors: true}` (should be none). Also time the frame budget during the replay with `javascript_tool: performance.now()` deltas across 10 `requestAnimationFrame`s — the page stays interactive. Take a screenshot.

- [ ] **Step 4: Commit**

```bash
git add homebase/static/charts/primitives.js homebase/static/charts/app.js
git commit -m "feat(charts): footprint (bid|ask per price, POC, diagonal imbalances) and session volume profile layers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Page — status strip, layouts, gap bands

**Files:**
- Modify: `homebase/static/charts/app.js` (replace the `showStatus`, `loadLayouts`, `saveLayout` stubs and the `drawGaps` method stub)

- [ ] **Step 1: Implement**

Replace the three function stubs:
```js
function showStatus(s) {
  const dot = $('#feedDot'), txt = $('#feedText'), bud = $('#budgetText');
  const roots = s.roots || {};
  const ages = Object.entries(roots).map(([r, x]) => {
    const a = x.last_tick_age_s;
    return `${r} ${a == null ? '—' : a < 60 ? a.toFixed(1) + 's' : Math.round(a / 60) + 'm'}`;
  });
  const worst = Math.max(0, ...Object.values(roots).map((x) => x.last_tick_age_s ?? 0));
  const recErr = s.recorder && s.recorder.error;
  dot.className = 'dot ' + (!s.connected || s.error || recErr ? 'bad' : worst > 30 ? 'warn' : 'ok');
  const mode = s.mode === 'replay'
    ? `replay ${s.date} ×${s.speed} · ${iso(s.clock_s || 0).slice(11, 19)} ET${s.done ? ' · done' : ''}`
    : s.mode === 'live' ? `live · md ${s.md || ''}` : '';
  txt.textContent = [mode, ...ages, s.error || '', recErr ? 'recorder: ' + recErr : ''].filter(Boolean).join('  ·  ');
  bud.textContent = s.mode === 'live' ? `md budget ${s.budget_hour ?? 0}/180 this hour · ${s.clients ?? 0} page(s)` : '';
}

async function loadLayouts(select) {
  let all = {};
  try { const r = await fetch('/api/layouts'); if (r.ok) all = await r.json(); } catch (_) {}
  const sel = $('#layoutSel');
  sel.innerHTML = '<option value="">Layouts…</option>' + Object.keys(all).map((n) => `<option ${n === select ? 'selected' : ''}>${esc(n)}</option>`).join('');
  sel.onchange = () => { if (all[sel.value]) { layout = JSON.parse(JSON.stringify(all[sel.value])); saveLast(); buildGrid(); } };
}

async function saveLayout() {
  const input = $('#layoutName'), name = input.value.trim();
  if (!name) { input.focus(); return; }
  await fetch('/api/layouts/' + encodeURIComponent(name), { method: 'PUT',
    headers: { 'content-type': 'application/json' }, body: JSON.stringify(layout) });
  input.value = '';
  loadLayouts(name);
}
```
Replace the `drawGaps() {}` stub in `Cell`:
```js
  drawGaps() {
    const idx = [];
    for (const s of this.sessions) for (const [a] of (s.gaps || [])) {
      let i = -1;
      for (let j = 0; j < this.bars.length && this.bars[j].t <= a; j++) i = j;
      if (i >= 0 && i < this.bars.length - 1) idx.push(i);
    }
    this.gaps.set(idx);
  }
```

- [ ] **Step 2: Verify in the browser**

Reload.
- The footer shows `replay 2026-09-24 ×20 · HH:MM:SS ET · NQ 0.1s · ES …` with a green dot.
- Type `test` in the layout name box and click Save layout; `test` appears in the Layouts menu.
- Change the grid to `1 chart`, then pick `test` from the menu: the saved 2×2 comes back.
- Stop the server (`preview_stop`): within 2 s the footer turns red with "chart service unreachable — retrying". Start it again: the charts resubscribe and recover without a reload.
- Delete the test layout with `curl -X DELETE localhost:8853/api/layouts/test`.

Take a screenshot.

- [ ] **Step 3: Commit**

```bash
git add homebase/static/charts/app.js
git commit -m "feat(charts): status strip (feed age, budget, recorder), saved layouts, gap bands

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Spike — can a second md socket share the Apex eval login?

**Gate:** Run this ONLY outside 09:00–16:00 ET on a trading day. For tick flow, run it after the Sunday 18:00 ET open. The result sets `HOMEBASE_CHARTS_MD` for Task 15.

**Files:** none committed (throwaway).

- [ ] **Step 1: Run the probe**

```bash
cd ~/ramos-quant-homebase && .venv/bin/python - <<'EOF'
import asyncio, time
from homebase import ticks as T, symbols

async def main():
    a = await T.connect_md(prefer_live=False)
    b = await T.connect_md(prefer_live=False)
    got, ids = {"a": 0, "b": 0}, set()
    def h(name):
        def f(m):
            if m.get("e") == "chart":
                for ch in m["d"]["charts"]:
                    ids.add(ch.get("id")); got[name] += len(ch.get("tks") or [])
        return f
    a.event_handlers.append(h("a")); b.event_handlers.append(h("b"))
    body = {"symbol": symbols.resolve_contract("NQ"),
            "chartDescription": {"underlyingType": "Tick", "elementSize": 1,
                                 "elementSizeUnit": "UnderlyingUnits", "withHistogram": False},
            "timeRange": {"asMuchAsElements": 1}}
    print("a", await a.request("md/getChart", body))
    print("b", await b.request("md/getChart", body))
    for i in range(20):
        await asyncio.sleep(30)
        print(time.strftime("%H:%M:%S"), "a", a.connected, "b", b.connected, got, sorted(ids))
    await a.close(); await b.close()

asyncio.run(main())
EOF
```
Expected (pass):
- Both replies carry `historicalId`/`realtimeId`, and the chart packet ids match them.
- `a` and `b` stay connected for 10 minutes.
- During market hours, both tick counters grow.

Fail means one socket drops, auth errors appear, or ticks stop on `a`.

- [ ] **Step 2: Record the result**

- Pass: keep `MD_ENV` default `"demo"`.
- Fail: set `HOMEBASE_CHARTS_MD=live` in the launchd plist (Task 15, `EnvironmentVariables`) and re-run the probe with `prefer_live=True`.

Either way, write the finding in the vault (`50-Permanent/Findings/2026-09-2X-tradovate-md-concurrent-sockets.md`) and add its index line.

---

### Task 15: Ship — dashboard link, launchd, docs, first live session

**Files:**
- Create: `deploy/com.ramosquant.homebase-charts.plist.template`
- Modify: `deploy/install.sh`, `homebase/static/index.html`, `README.md`

- [ ] **Step 1: launchd template**

`deploy/com.ramosquant.homebase-charts.plist.template`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ramosquant.homebase-charts</string>
  <key>ProgramArguments</key>
  <array>
    <string>__REPO__/.venv/bin/python</string>
    <string>-m</string>
    <string>homebase.charts</string>
  </array>
  <key>WorkingDirectory</key><string>__REPO__</string>
  <!-- the chart half of the terminal: its OWN process so chart work can never
       delay an order or take the trading app down. Records live ticks. -->
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>__REPO__/homebase/.state/charts.log</string>
  <key>StandardErrorPath</key><string>__REPO__/homebase/.state/charts.log</string>
</dict>
</plist>
```
If the Task 14 spike failed, add inside `<dict>`:
```xml
  <key>EnvironmentVariables</key><dict><key>HOMEBASE_CHARTS_MD</key><string>live</string></dict>
```

- [ ] **Step 2: install.sh**

In `deploy/install.sh`, add `com.ramosquant.homebase-charts` to `LABELS=(...)` and to the `for l in ... ; do sed ...` template loop. Change the last line to:
```bash
echo "installed — dashboard: http://localhost:8850 · charts: http://localhost:8852"
```

- [ ] **Step 3: Charts link on the dashboard**

In `homebase/static/index.html`, insert right after `<span class="pill idle" style="margin-left:2px">Ramos Quant</span>`:
```html
      <a class="btn btn-outline btn-sm" id="chartsLink" href="http://localhost:8852/" style="margin-left:6px">Charts</a>
```
Then insert this line as the first statement inside the main page `<script>` (the one after the markup, currently at line 565):
```js
  (function(){ var a = document.getElementById('chartsLink'); if (a) a.href = location.protocol + '//' + location.hostname + ':8852/'; })();
```

- [ ] **Step 4: README**

Add a `## Charts` section to `README.md`:
```markdown
## Charts

`python -m homebase.charts` (launchd `com.ramosquant.homebase-charts`, port 8852) is the chart half
of the terminal: multi-chart layouts on live ticks — time/tick/volume/range bars, VWAP/EMA/SMA/VWMA/ADX,
session levels, footprint, delta, cumulative delta, big prints, volume profile. Its OWN process: it
cannot place orders and cannot slow the trading app. It records every live tick to
`~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz`; past sessions come from the archive.

- Replay any archived session (records nothing): `python -m homebase.charts --replay 2026-09-24 --speed 20 --port 8853`
- md login: the Apex eval by default; `HOMEBASE_CHARTS_MD=live` switches to the live login.
- Budget: one chart request per root per connection; gap refills ≤ 60/hour, never 09:20–09:35 ET.
- Over Tailscale, serve port 8852 alongside 8850.
- Spec/plan: `docs/superpowers/specs/2026-09-25-live-charts-design.md`, `docs/superpowers/plans/2026-09-25-live-charts.md`.
```

- [ ] **Step 5: Full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (124 existing + the new chart tests).

- [ ] **Step 6: Commit**

```bash
git add deploy homebase/static/index.html README.md
git commit -m "feat(charts): ship — launchd service, Charts link on the dashboard, README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Install and watch the first live session (user-approved step)**

Ask the user before running `./deploy/install.sh`: it restarts the trading app's launchd jobs too. Once they approve, run it at a quiet time (not 09:00–16:00 ET). Then:
- Open `http://localhost:8852`.
- Check `tail -f homebase/.state/charts.log` for `up — live · NQ, ES, YM` and refill lines.
- Confirm `~/futures_ticks/NQ/<year>/<today>_NQZ6.live.csv.gz` grows.
- Confirm the footer shows `live · md demo` with tick ages under a few seconds while the market is open.

Next morning, check `homebase/.state/` logs: the trading app's 09:30 fire timing is unchanged (the `fire` journal event is still at 09:30:00.0xx).
```
