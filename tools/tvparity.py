"""TradingView parity: the owner's "Export chart data" CSVs against Homebase's studies.

    .venv/bin/python -m tools.tvparity run [dir]        (default: ROOT/inbox)

Two checks per export (docs/tvparity-export-recipe.md says how the CSVs are made):
  - math: each probe column `tv|<homebase key>|<field>` against the same study run on TradingView's OWN bars from the
    CSV -- the `tv:` variant when studies.make has it, else the house key, and the report says which;
  - data: the same study on Homebase's own bars of the same sessions, after an OHLCV pass that tags the sessions whose
    bars cannot match (a holiday folded into the next day, a contract roll one session apart, prints landing across a
    bar boundary) and flags a SET / B-ADJ chart setting left on.
Everything TradingView-derived stays under ROOT (~/.homebase/tvparity, or HOMEBASE_TVPARITY_DIR) and never inside the
repo: the repo is public and the data is display-licensed. The report holds verdicts and counts only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import shutil
import statistics
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from homebase.charts import studies_tv
from homebase.charts.bars import Bar, BarSpec
from homebase.charts.hub import prime_sessions, warm_bars
from homebase.charts.session import ET, session_date, session_range_ms
from homebase.charts.studies import make, split_timeframe
from homebase.charts.studies_tv2 import CUMULATIVE_WARM, WARM
from homebase.contracts import price_root, spec_for, tick_size
from homebase.paths import repo_root
from homebase.ticks import session_complete

ENV = "HOMEBASE_TVPARITY_DIR"
TFS = (60, 300, 900, 3600, 86400)
TF_LABEL = {60: "1m", 300: "5m", 900: "15m", 3600: "1h", 86400: "1D"}
NA = frozenset(("", "nan", "na", "n/a", "null"))
NO_TV = ("tspeed", "press", "vaprev")            # no TradingView source at all (big prints, sweeps, per-row data)
BAR_COLS = {"tv|vol|": "v", "tv|fp|buy": "buy", "tv|fp|sell": "sell"}   # probe columns that are bar fields, not studies
HOUSE_SIGN = {("supertrend", "dir"): -1.0}       # the probe holds Pine's sign (-1 up); the house study says +1 up
VERDICTS = ("identical", "warm-up only", "differs", "no-tv", "no-data")
CUMULATIVE = {n for n, w in WARM.items() if w([]) >= CUMULATIVE_WARM}   # the tv: running sums (obv pvt adl nvi pvi): no finite warm-up repairs them


def root() -> Path:
    """ROOT, never inside the repo (the exports must not be committed)."""
    v = os.environ.get(ENV)
    r = (Path(v).expanduser() if v else Path.home() / ".homebase" / "tvparity").resolve()
    if r.is_relative_to(repo_root()):
        raise RuntimeError(f"{ENV} must point outside the repo, not {r}")
    return r


# ------------------------------------------------------------------ the export
@dataclass
class TvExport:
    path: Path
    tf_s: int               # bar length in seconds, the median spacing matched to TFS (ValueError for any other timeframe)
    group: str              # the probe ids of the file ("P1", or "P2+P3+P4" on layout B), "" without one
    t_ms: list
    o: list
    h: list
    l: list
    c: list
    v: list
    cols: list              # [(title, values, decimals)] in file order, duplicate titles kept
    has_volume: bool = True  # a Volume column or the P2 `tv|vol|` plot holds a volume; False: v is 0 on every bar


def _time_ms(s: str) -> int:
    """Epoch ms from a UNIX cell (seconds or milliseconds) or an ISO cell ("Z", an offset, or naive = UTC)."""
    s = s.strip()
    try:
        x = float(s)
    except ValueError:
        t = dt.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return int(round(t.timestamp() * 1000))
    return int(round(x * 1000)) if x < 1e11 else int(round(x))     # 1e11 s is the year 5138; ms stamps are 13 digits


def _num(s: str):
    s = s.strip()
    if s.lower() in NA:
        return None
    x = float(s)
    return None if math.isnan(x) else x


def _decimals(s: str) -> int:
    s = s.strip()
    if "e" in s.lower():
        return 10
    _, dot, frac = s.partition(".")
    return len(frac) if dot else 0


def load_tv_csv(path, now: dt.datetime | None = None) -> TvExport:
    """A TradingView chart export. Rows without a full OHLC and rows of a session not complete at `now` (the file's
    mtime) are dropped, so the developing bar never counts."""
    path = Path(path)
    rows = [r for r in csv.reader(path.read_text(encoding="utf-8-sig").splitlines()) if any(x.strip() for x in r)]
    if len(rows) < 3:
        raise ValueError(f"{path.name}: fewer than two bars")
    head = [h.strip() for h in rows[0]]
    low = [h.lower() for h in head]
    idx = {}
    for name in ("time", "open", "high", "low", "close"):
        if name not in low:
            raise ValueError(f"{path.name}: no {name!r} column")
        idx[name] = low.index(name)
    # the Volume indicator's column, else the P2 probe's `tv|vol|` plot (layout B has no Volume indicator)
    iv = low.index("volume") if "volume" in low else low.index("tv|vol|") if "tv|vol|" in low else None
    fixed = set(idx.values()) | ({iv} if iv is not None and low[iv] == "volume" else set())
    if now is None:
        now = dt.datetime.fromtimestamp(path.stat().st_mtime, ET)
    recs = []
    for r in rows[1:]:
        r = r + [""] * (len(head) - len(r))
        ohlc = [_num(r[idx[k]]) for k in ("open", "high", "low", "close")]
        if None in ohlc:
            continue
        t = _time_ms(r[idx["time"]])
        if not session_complete(session_date(t), now):
            continue
        recs.append((t, ohlc, _num(r[iv]) if iv is not None else 0.0, r))
    recs.sort(key=lambda x: x[0])
    if len(recs) < 2:
        raise ValueError(f"{path.name}: fewer than two complete bars")
    t_ms = [x[0] for x in recs]
    gaps = [(b - a) // 1000 for a, b in zip(t_ms, t_ms[1:]) if b > a]
    med = statistics.median(gaps)
    tf_s = min(TFS, key=lambda s: abs(s - med))
    if abs(med - tf_s) > 0.1 * tf_s:
        raise ValueError(f"{path.name}: bars {med:g} s apart are not a supported timeframe "
                         f"({', '.join(TF_LABEL.values())}); export the chart on one of those")
    cols, ids = [], []
    for j, title in enumerate(head):
        if j in fixed:
            continue
        parts = title.split("|")
        if len(parts) == 3 and parts[0] == "tv" and parts[1] == "probe":
            if parts[2] not in ids:
                ids.append(parts[2])
            continue
        cols.append((title, [_num(x[3][j]) for x in recs], [_decimals(x[3][j]) for x in recs]))
    return TvExport(path, tf_s, "+".join(ids), t_ms,
                    [x[1][0] for x in recs], [x[1][1] for x in recs], [x[1][2] for x in recs], [x[1][3] for x in recs],
                    [x[2] or 0.0 for x in recs], cols, any(x[2] for x in recs))


def column(x: TvExport, title: str):
    """The first column of that title (values), or None."""
    return next((vals for t, vals, _ in x.cols if t == title), None)


def probe_columns(x: TvExport) -> list:
    """(key, field, values, decimals) of every `tv|<key>|<field>` study column, duplicates kept in file order."""
    out = []
    for title, vals, decs in x.cols:
        parts = title.split("|")
        if len(parts) < 2 or parts[0] != "tv" or title in BAR_COLS or parts[1] in ("probe", "vol", "fp"):
            continue
        out.append((parts[1], parts[2] if len(parts) > 2 else "", vals, decs))
    return out


# ------------------------------------------------------------------ bars
def tv_bars(x: TvExport, root: str = "NQ") -> list[Bar]:
    """TradingView's own bars as Bars: pv / p2v from hlc3 x volume (TradingView's VWAP source), buy / sell from the P4
    footprint columns when the export has them."""
    buy, sell = column(x, "tv|fp|buy"), column(x, "tv|fp|sell")
    out = []
    for i, t in enumerate(x.t_ms):
        o, h, l, c, v = x.o[i], x.h[i], x.l[i], x.c[i], int(x.v[i])
        p = (h + l + c) / 3.0
        b = Bar(t=t, session=session_date(t, root).isoformat(), o=o, h=h, l=l, c=c, v=v, pv=p * v, p2v=p * p * v,
                closed=True, span=x.tf_s * 1000)
        if buy is not None and sell is not None and buy[i] is not None and sell[i] is not None:
            b.buy, b.sell = int(buy[i]), int(sell[i])
        out.append(b)
    return out


def hb_bars(x: TvExport, root: str = "NQ", history=None) -> list[Bar]:
    """Homebase's own bars of every session in the export, from its first bar on (both sides start on the same bar)."""
    if history is None:
        from homebase.charts.history import History
        from homebase.charts.store import TickStore
        history = History(TickStore())
    spec = BarSpec("time", x.tf_s)
    t0 = x.t_ms[0]
    out = []
    for d in sorted({session_date(t, root) for t in x.t_ms}):
        out.extend(b for b in history.bars(root, spec, d) if b.t >= t0)
    return out


# ------------------------------------------------------------------ studies
def run(key: str, bars: list, tick: float = 0.25) -> list:
    """The study's value on each closed bar, in order."""
    st = make(key, tick)
    return [st.push(b) for b in bars]


def field(v, name: str):
    """One number out of a study value: a dict's field, a plain value as is, None while warming up."""
    if isinstance(v, dict):
        if name == "sd" and "sd" not in v and "u1" in v:          # tv:vwap has bands, no sd: the first band's width
            v = {**v, "sd": None if v["u1"] is None else v["u1"] - v["vwap"]}
        v = v.get(name) if name else None
    if v is None:
        return None
    return float(v)


def _tv_args(name: str, args: list) -> list:
    """A house key's arguments in the tv: study's order. Only keltner differs: house n, true-range length, mult; tv n,
    mult, band length."""
    if name == "keltner":
        n, m, mult, *rest = args + ["20", "20", "1.5"][len(args):]
        return [n, mult, m, *rest]
    return args


def _whole(k: str) -> None:
    """ValueError when a fractional value sits in an integer parameter of a tv: key (make_tv would truncate it)."""
    name, *args = k.partition("@")[0].split(":")[1:]
    spec = {**studies_tv.PARAMS, **studies_tv.PARAMS2}.get(name, (None, ()))[1]
    for i, (a, p) in enumerate(zip(args, spec)):
        if len(p) == 3 and isinstance(p[0], int):
            try:
                x = float(a)
            except ValueError:
                continue                                    # not a number: make() refuses it with its own words
            if x % 1:
                raise ValueError(f"{k}: parameter {i + 1} must be a whole number, got {a}")


def tv_key(base: str) -> tuple[str, bool]:
    """("tv:" + base, True) when studies.make accepts the TradingView-match variant, else (base, False): the house key
    stands in and the report says so (studies_tv.py may not exist yet). The key is a house key, so its arguments are
    reordered for the tv: study where the two differ; ValueError for a fractional value in a whole-number parameter."""
    core, at, tf = base.partition("@")
    name, *args = core.split(":")
    k = ":".join(["tv", name, *_tv_args(name, args)]) + at + tf
    _whole(k)
    try:
        make(k)
        return k, True
    except Exception:
        return base, False


def htf_keys(bars: list, sec: int) -> list:
    n = sec * 1000
    return [(b.session, (b.t - session_range_ms(dt.date.fromisoformat(b.session))[0]) // n) for b in bars]


def htf_closes(bars: list, sec: int) -> set:
    """Indices of the bars that close a higher-timeframe bar of `sec` seconds (anchored at the session open like
    studies.HTF): a key with an @tf suffix is compared on those bars only."""
    keys = htf_keys(bars, sec)
    return {i for i, k in enumerate(keys) if i + 1 == len(keys) or keys[i + 1] != k}


def htf_cold(bars: list, sec: int, n: int, starts=(0,)) -> set:
    """Indices of the bars inside `n` higher bars of `sec` seconds counted from each of `starts` (a bar index: the window
    opens in the higher bar that holds it; a day or more = one session). A study on a longer timeframe is cold for its
    window of HIGHER bars, whatever the chart's timeframe: hub.warm_bars counts them as one-minute chart bars and stops at
    the span the hub keeps (20000), which on a day key forgives a whole export."""
    keys = htf_keys(bars, sec)
    order = {}
    for k in keys:
        order.setdefault(k, len(order))
    hit = bytearray(len(order) + n)
    for s in starts:
        hit[order[keys[s]]:order[keys[s]] + n] = b"\1" * n
    return {i for i, k in enumerate(keys) if hit[order[k]]}


def settle_bars(key: str) -> int:
    """Bars after a start (the export's first bar, the bar after a skipped one) in which a study may still differ from
    TradingView's by its seed. hub.warm_bars is the length a chart is repaired to: a window's length, and for a study that
    fades (an EMA: 5 n) the point where its seed gap is down to e^-10, which a print still shows (measured: an RSI or ATR
    seeded 2000 points off keeps differing to 2.3 x that, at same()'s 1e-9). A study that fades gets three times that
    (e^-30), a plain window exactly its own length."""
    w = warm_bars(key)
    n = next((int(t) for t in key.partition("@")[0].split(":")[1:] if t.isdecimal()), 0)
    return w if w <= n else 3 * w


# ------------------------------------------------------------------ the verdict
def same(a, b, decimals: int = 0) -> bool:
    """na equals na; na against a number differs; numbers match within half the last printed digit plus 1e-9 relative."""
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= 0.5 * 10.0 ** -decimals + 1e-9 * abs(a)


def compare(tv, hb, decimals=0, warm: int = 0, restarts=(0,), skip=(), cold=()) -> dict:
    """The verdict and its counts. `decimals` is per cell (a list) or one number; a difference inside `warm` bars after
    any of `restarts`, or at a `cold` index, is warm-up; `skip` indices are not compared (tagged sessions, missing bars,
    open higher bars). `cold`: bars TradingView's study had history for that the export (and so Homebase) does not."""
    if tv is None:
        return {"verdict": "no-tv", "n": 0, "n_diff": 0, "first": None, "max_abs": 0.0}
    warm_idx = {i for r in restarts for i in range(r, r + warm)} | set(cold)
    n = n_diff = late = 0
    first, mx = None, 0.0
    first_late, mx_late = None, 0.0
    for i, (a, b) in enumerate(zip(tv, hb)):
        if i in skip:
            continue
        n += 1
        if same(a, b, decimals[i] if isinstance(decimals, (list, tuple)) else decimals):
            continue
        n_diff += 1
        d = abs(a - b) if a is not None and b is not None else 0.0
        if first is None:
            first = i
        mx = max(mx, d)
        if i not in warm_idx:
            late += 1
            if first_late is None:
                first_late = i
            mx_late = max(mx_late, d)
    if late:       # a 'differs' row points at the first difference past the warm-up; a 'warm-up only' row at where it differed
        first, mx = first_late, mx_late
    verdict = "no-data" if n == 0 else "identical" if not n_diff else "warm-up only" if not late else "differs"
    return {"verdict": verdict, "n": n, "n_diff": n_diff, "first": first, "max_abs": mx}


def verdict(tv, hb, decimals=0, warm: int = 0, restarts=(0,), skip=(), cold=()) -> str:
    return compare(tv, hb, decimals, warm, restarts, skip, cold)["verdict"]


# ------------------------------------------------------------------ the OHLCV pass
def _only(a: Bar, b: Bar, f: str) -> bool:
    """a and b differ in field f and nowhere else in o/h/l/c."""
    return getattr(a, f) != getattr(b, f) and all(getattr(a, g) == getattr(b, g) for g in "ohlc" if g != f)


def _contract_hl(store, root: str, d: dt.date, contract: str):
    """(high, low) of one archived contract's session, from its ticks."""
    from homebase.charts.store import read_table, ticks_from_table
    f = next((f for f in store.files(root, d) if f.contract == contract), None)
    if f is None:
        return None
    header, recs = read_table(f.path)
    ticks, _ = ticks_from_table(header, recs, live=f.live)
    if not ticks:
        return None
    return max(t.price for t in ticks), min(t.price for t in ticks)


def ohlcv_pass(tv: list, hb: list, tf_s: int, root: str = "NQ", store=None, volume: bool = True) -> dict:
    """Each TradingView bar classed same | price | volume | boundary | missing (plus Homebase's extra bars), the sessions
    tagged holiday / roll / boundary, and whether the chart's SET or B-ADJ setting looks left on. The roll tag needs the
    tick store (sessions holding more than one archived contract are read); None skips it. volume=False (the export
    has no volume) leaves the volume out of the comparison."""
    hb_by_t = {b.t: b for b in hb}
    cls = []
    for b in tv:
        m = hb_by_t.get(b.t)
        if m is None:
            cls.append("missing")
        elif (b.o, b.h, b.l, b.c) != (m.o, m.h, m.l, m.c):
            cls.append("price")
        elif volume and b.v != m.v:
            cls.append("volume")
        else:
            cls.append("same")
    tags = {"holiday": set(), "roll": set(), "boundary": set()}
    tv_t = {b.t for b in tv}
    extra = [b for b in hb if b.t not in tv_t]
    if tf_s == 86400:
        # a holiday's short session is folded into the next day's bar: a Homebase session open inside its span
        starts = sorted(tv_t)
        by_t = {b.t: b for b in tv}
        for b in extra:
            j = bisect_right(starts, b.t) - 1
            if j >= 0:
                tags["holiday"].update((by_t[starts[j]].session, b.session))
    for i in range(len(tv) - 1):
        a, b = tv[i], tv[i + 1]
        ma, mb = hb_by_t.get(a.t), hb_by_t.get(b.t)
        if ma and mb and cls[i] == "price" and cls[i + 1] == "price" and _only(a, ma, "c") and _only(b, mb, "o"):
            cls[i] = cls[i + 1] = "boundary"       # a print landed on the other side of the bar boundary
            tags["boundary"].update((a.session, b.session))
    if store is not None:
        by_sess = {}
        for b in tv:
            h, l = by_sess.get(b.session, (b.h, b.l))
            by_sess[b.session] = (max(h, b.h), min(l, b.l))
        for s, hl in by_sess.items():
            d = dt.date.fromisoformat(s)
            contracts = sorted({f.contract for f in store.files(root, d)})
            if len(contracts) < 2:
                continue
            picked = store.pick(root, d).contract
            match = [c for c in contracts if _contract_hl(store, root, d, c) == hl]
            if match and picked not in match:
                tags["roll"].add(s)
    pairs = [(b, hb_by_t[b.t]) for b in tv if b.t in hb_by_t]
    set_on = tf_s == 86400 and len(pairs) >= 20 and \
        sum(_only(b, m, "c") for b, m in pairs) >= 0.8 * len(pairs)
    offs = Counter(round(b.o - m.o, 6) for b, m in pairs if b.o != m.o)
    badj_on = bool(offs) and offs.most_common(1)[0][1] >= 0.5 * len(pairs)
    classes = Counter(cls)
    classes["extra"] = sum(b.session not in tags["holiday"] for b in extra)
    return {"classes": dict(classes), "tags": {k: sorted(v) for k, v in tags.items()},
            "flags": {"set": bool(set_on), "badj": bool(badj_on)}, "by_bar": cls}


# ------------------------------------------------------------------ one export, start to end
def _et(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, ET).strftime("%Y-%m-%d %H:%M")


def cold_sessions(key: str, fld: str = "") -> int:
    """How many sessions at the start of an export the study is still cold in, though TradingView's probe is not: the
    P2 probes of levels / dhl / noise read a daily series with request.security("D"), which holds history from before
    the first exported bar, while Homebase has only the export's own bars. The cells in those sessions that differ read
    'warm-up only' (a difference after them is still a difference). Not hub.prime_sessions: that is 0 for levels, and
    it counts what the app feeds the chart, not what a probe on the daily series already knew."""
    name = key.partition("@")[0].split(":")[0]
    if name == "levels":
        # the prior day, and the one before it when the export starts mid-session; onh / onl / rth_open read the chart
        return 2 if fld in ("pdh", "pdl", "pdc") else 0
    if name == "dhl":
        return prime_sessions(key)  # the n sessions of the range, plus the one before
    if name == "noise":
        # a Wilder ATR(14): its seed fades by 13/14 a session, so 18 x 14 sessions leave 8e-9 of a daily range, under
        # same()'s 1e-9-of-price tolerance (measured: the last session still off was 181 at five times NQ's range)
        return 18 * 14
    return 0


def uses_volume(key: str, bars: list, tick: float) -> bool:
    """True when the study's values change with the bars' volume (run on these bars with volume 0 and with a volume that
    rises and falls, which also moves nvi / pvi: a constant volume leaves them flat); a study that cannot run on zero
    volume counts as using it."""
    def with_volume(vol):
        out = []
        for i, b in enumerate(bars):
            p = (b.h + b.l + b.c) / 3.0
            out.append(replace(b, v=vol(i), pv=p * vol(i), p2v=p * p * vol(i)))
        return out
    try:
        return run(key, with_volume(lambda i: 0), tick) != run(key, with_volume(lambda i: 1 + i % 3), tick)
    except Exception:
        return True


def check_export(x: TvExport, root: str = "NQ", hb: list | None = None, store=None) -> tuple[dict, list]:
    """(meta, rows) of one export: the OHLCV pass, then the math and data check of every probe column. `hb` None reads
    Homebase's own bars; [] skips the data check."""
    tv = tv_bars(x, root)
    if hb is None:
        hb = hb_bars(x, root)
    tick = tick_size(root)
    tf = TF_LABEL.get(x.tf_s, str(x.tf_s))
    meta = {"file": x.path.name, "root": root, "group": x.group, "tf": tf, "bars": len(tv),
            "sessions": len({b.session for b in tv}), "first": _et(tv[0].t), "last": _et(tv[-1].t),
            "no_volume": not x.has_volume}
    rows = []
    hb_t = {b.t: b for b in hb}
    skip, restarts = set(), (0,)
    if hb:
        o = ohlcv_pass(tv, hb, x.tf_s, root, store, volume=x.has_volume)
        meta.update(classes=o["classes"], tags=o["tags"], flags=o["flags"])
        tagged = set().union(*o["tags"].values())
        skip = {i for i, b in enumerate(tv) if b.session in tagged or b.t not in hb_t}
        # the Homebase study still saw the skipped bars (a holiday's extra bar, a gap): its state is off until the warm-up
        restarts = (0,) + tuple(i for i in range(1, len(tv)) if i not in skip and i - 1 in skip)
        for title, attr in BAR_COLS.items():
            col = None if attr == "v" and not x.has_volume else column(x, title)   # an empty tv|vol| is no volume, not zeros
            if col is not None:
                got = [float(getattr(hb_t[b.t], attr)) if b.t in hb_t else None for b in tv]
                rows.append(_row("bar", attr, tf, None, compare(col, got, 0, 0, (0,), skip), "", tv))

    def aligned(vals):
        by_t = dict(zip((b.t for b in hb), vals))
        return [by_t.get(b.t) for b in tv]

    rank = {}
    for b in tv:
        rank.setdefault(b.session, len(rank))
    needs_volume = {}
    for key, fld, vals, decs in probe_columns(x):
        try:
            base, sec = split_timeframe(key)
            make(key, tick)
            kt, has_tv = tv_key(key)
        except ValueError as e:
            rows.append(_row(key, fld, tf, None, None, "", tv, note=f"bad key: {e}"))
            continue
        if sec and sec < x.tf_s:
            rows.append(_row(key, fld, tf, None, None, "", tv, note=f"skipped: @{sec} is below the chart's {tf} bars "
                             "(TradingView reads the last lower-timeframe bar, Homebase has only the chart's bars)"))
            continue
        head, _, name = key.partition(":")
        # a running sum never forgets its start: compare it from the first bar, a warm-up would hide every difference. An @tf
        # key is cold in bars of its own timeframe (below), not in chart bars
        warm = 0 if sec or (head == "tv" and name in CUMULATIVE) else settle_bars(key)
        htf_skip = set(range(len(tv))) - htf_closes(tv, sec) if sec else set()
        k = cold_sessions(key, fld)
        cold = cold_data = {i for i, b in enumerate(tv) if rank[b.session] < k}
        if sec:       # TradingView's higher bars had history the export lacks, for the study's window of them; Homebase's again after a skipped bar
            win = settle_bars(base)
            cold, cold_data = htf_cold(tv, sec, win), htf_cold(tv, sec, win, [0] + [r - 1 for r in restarts[1:]])  # no @tf key has cold sessions
        note = ""
        if not x.has_volume:
            if kt not in needs_volume:
                needs_volume[kt] = uses_volume(kt, tv, tick)
            if needs_volume[kt]:
                note = ("skipped: no volume in this export (put the Volume indicator on the chart, or re-export with "
                        "the current P2 script, which plots the volume itself); the data check below ran on Homebase's volume")
        math_cmp = None if note else compare(vals, [field(v, fld) for v in run(kt, tv, tick)], decs, warm, (0,), htf_skip, cold)
        sign = HOUSE_SIGN.get((key.split(":")[0], fld), 1.0)
        house = compare(vals, [None if (f := field(v, fld)) is None else sign * f for v in run(key, tv, tick)], decs, warm,
                        (0,), htf_skip, cold) if has_tv and not note else None
        data_cmp = compare(vals, aligned([field(v, fld) for v in run(kt, hb, tick)]), decs, warm, restarts,
                           skip | htf_skip, cold_data) if hb else None
        rows.append(_row(key, fld, tf, math_cmp, data_cmp, kt, tv, house=house, note=note))
    for name in NO_TV:
        rows.append(_row(name, "", tf, None, None, "", tv, note="no TradingView source"))
    for r in rows:
        r["file"] = x.path.name
    return meta, rows


def _row(key, fld, tf, math_cmp, data_cmp, kt, tv, house=None, note="") -> dict:
    def pack(c):
        if c is None:
            return {"verdict": "no-tv" if note else "no-data", "n": 0, "n_diff": 0, "first": None, "max_abs": 0.0}
        c = dict(c)
        c["first"] = _et(tv[c["first"]].t) if c["first"] is not None else None
        return c
    return {"key": key, "field": fld, "tf": tf, "tv_key": kt, "math": pack(math_cmp), "data": pack(data_cmp),
            "house": pack(house) if house is not None else None, "note": note}


# ------------------------------------------------------------------ the report
def _cell(c: dict) -> str:
    v = c["verdict"]
    return v if c["n_diff"] == 0 else f"{v} {c['n_diff']}/{c['n']}"


def _md(s) -> str:
    """A free-text table cell: a pipe would end the cell."""
    return str(s).replace("|", "\\|")


def write_report(metas: list, rows: list, out_dir: Path, stamp: str | None = None) -> tuple[Path, Path]:
    """ROOT/reports/<stamp>.md and .json: verdicts and counts, never a TradingView value."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or dt.datetime.now(ET).strftime("%Y%m%d-%H%M%S")
    lines = [f"# TradingView parity {stamp}", ""]
    for m in metas:
        title = " ".join(filter(None, (m.get("root"), m["group"] or m["file"], m["tf"])))
        lines.append(f"## {title}: {m['bars']} bars, {m['sessions']} sessions, {m['first']} to {m['last']} ET")
        if m.get("no_volume"):
            lines.append("- no volume in this export: the volume probes are skipped for the math and checked on Homebase's data only")
        if "classes" in m:
            cl = ", ".join(f"{k} {v}" for k, v in sorted(m["classes"].items()))
            tg = "; ".join(f"{k} {len(v)}: {' '.join(v[:6])}{' ...' if len(v) > 6 else ''}"
                           for k, v in m["tags"].items() if v) or "none"
            fl = ", ".join(k for k, v in m["flags"].items() if v) or "none"
            lines += [f"- OHLCV: {cl}", f"- tagged sessions: {tg}", f"- settings left on: {fl}"]
        else:
            lines.append("- data check: no Homebase bars")
        lines.append("")
    lines += ["| study | field | tf | math | data | first diff (ET) | max abs | ran as | note | file |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        shown = [c for c in (r["math"], r["data"]) if c["verdict"] == "differs"] or [r["math"], r["data"]]   # not a warm-up's bar beside a real difference
        first = next((c["first"] for c in shown if c["first"]), "")
        mx = max(c["max_abs"] for c in shown)
        house = f" (house: {_cell(r['house'])})" if r["house"] else ""
        lines.append(f"| {r['key']} | {r['field']} | {r['tf']} | {_cell(r['math'])}{house} | {_cell(r['data'])} | {first} | "
                     f"{mx:.6g} | {r['tv_key']} | {_md(r['note'])} | {_md(r.get('file', ''))} |")
    md, js = out_dir / f"{stamp}.md", out_dir / f"{stamp}.json"
    md.write_text("\n".join(lines) + "\n")
    js.write_text(json.dumps({"stamp": stamp, "files": metas, "rows": rows}, indent=1))
    return md, js


# ------------------------------------------------------------------ CLI
def file_root(name: str) -> str | None:
    """The market an export is of, read from TradingView's file name ("CME_MINI_ES1!, 1_ab12.csv" -> ES, "MNQ1!" -> NQ)
    or from the name run_dir files it under ("ES_P2_1m.csv" -> ES), or None when the name has neither."""
    tfs = "|".join(TF_LABEL.values())
    for rx in (rf"^([A-Z0-9]{{1,4}})_.+_(?:{tfs})(?:_\d+)?\.csv$", r"(?<![A-Z0-9])([A-Z0-9]{1,5}?)1!"):
        m = re.search(rx, name)
        if m and spec_for(r := price_root(m.group(1))).known:
            return r
    return None


def run_dir(inbox: Path, root_sym: str | None = None, history=None) -> Path:
    """Every CSV in `inbox`: load, move to ROOT/exports/<date>/<root>_<group>_<tf>.csv, check, one report. Returns the
    report's .md path. The market of each file is `root_sym` when given, else read from its name, else NQ. `history` None
    reads the tick archive for a root it holds, else that file's data check is skipped."""
    R = root()
    files = sorted(Path(inbox).glob("*.csv"))
    if not files:
        raise SystemExit(f"nothing to check in {inbox}")
    store, archive = None, {}

    def history_of(r):
        nonlocal store
        if history is not None:
            return history
        if r not in archive:
            if store is None:
                from homebase.charts.store import TickStore
                store = TickStore()
            from homebase.charts.history import History
            archive[r] = History(store) if store.sessions(r) else None
        return archive[r]
    out = R / "exports" / dt.datetime.now(ET).date().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    metas, rows = [], []
    for p in files:
        try:
            x = load_tv_csv(p)
        except (ValueError, OSError, OverflowError) as e:
            print(f"{p.name} skipped, left in {inbox}: {e}")
            continue
        r = root_sym or file_root(p.name)
        if r is None:
            r = "NQ"
            print(f"{p.name}: no market in the file name, checked as NQ (name it like ES_P2_1m.csv, or pass the root)")
        stem = f"{r}_{x.group or p.stem}_{TF_LABEL.get(x.tf_s, x.tf_s)}"
        dest = out / f"{stem}.csv"
        k = 1
        while dest.exists():
            k += 1
            dest = out / f"{stem}_{k}.csv"
        shutil.move(str(p), dest)
        x.path = dest
        h = history_of(r)
        hb = hb_bars(x, r, h) if h is not None else []
        if hb:      # Homebase's bars next to the filed export, for `parity.mjs <script> <filed csv> --bars homebase`
            dest.with_suffix(".bars.json").write_text(json.dumps(
                [{"ms": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v} for b in hb]))
        meta, rs = check_export(x, r, hb, h.store if h is not None else None)
        metas.append(meta)
        rows.extend(rs)
        print(f"{dest.name}: {meta['bars']} bars, {len(rs)} rows")
    if not metas:
        raise SystemExit(f"no CSV in {inbox} could be read")
    md, _ = write_report(metas, rows, R / "reports")
    return md


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.tvparity", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="check every CSV in the inbox (or dir) and write a report")
    r.add_argument("dir", nargs="?", help="folder of TradingView exports (default ROOT/inbox)")
    r.add_argument("--root", default=None, help="the Homebase root every export is of (default: read from each file's name, else NQ)")
    a = ap.parse_args(argv)
    print(run_dir(Path(a.dir) if a.dir else root() / "inbox", a.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
