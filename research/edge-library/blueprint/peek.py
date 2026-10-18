"""peek.py -- LINE 1.7 OF THE CODE CHECK: the rule does not look ahead (BLUEPRINT.md phase 1), read BY CODE on every store of
the engine. "Does the rule see only what had already happened?"

THE CARD'S OWN INSTANCES -- the store's family and the inputs of its cells (market, session, bar size, levels, filters, every
block it uses), one exit cell per variant, run as the build ran them (run_idea.cell_specs, runner._engine) -- are replayed on
`days` build days spread over the build range: once on the real tape, and once per CUT with every print from the cut on
garbled (the engine tests' own `garble`, engine/tests/test_blocks.py: price and size rewritten), and every Level-2 row not yet
usable at the cut rewritten when the card reads the book (the tests' rule: usable_ns > cut). The cuts are drawn with a fixed
seed inside the card's own trading window (its sessions' windows), `cuts` a day. Everything the rule did at or before the cut
must be the same on both tapes:
  order   every entry order it placed: its time, side, kind, price, stop and target
  bar     at every close of its own bar size: the bar count, the close, the ATR and the session VWAP it holds
  level   at every close, for a card that reads liquidity levels (the liq trigger, the level / swept filters): every level
  error   a callback that raised
  trade   every fill before the cut (entry time, side, price) and every exit before it
One cut where anything of these moved = FAIL, with the date, the cut, the setting and what moved (`moved`, the first SHOWN).
Nothing is written or booked, no round is counted, the engine is not touched (the tape loader is swapped for the pass only).
A store that is not of the engine (hand-made, a family the registry does not know) and a plain trades file: not read (n/a).
The freeze asks this line TRUE (freeze.PLAIN): a lock always rests on it.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np

import l2sim as S

from . import lines as L
from . import rules as R
from . import runner as RUN

SHOWN = 20                                          # cuts that moved, listed in a result (their count is always whole)
LEVEL_KEYS = ("f_level", "f_swept")                 # filter blocks that read the liquidity levels (engine/levels.py)


def _garble():
    """THE ENGINE TESTS' OWN garble (engine/tests/test_blocks.py): every print at / after the cut rewritten, price and size."""
    p = str(S.L / "tests")
    if p not in sys.path:
        sys.path.append(p)
    from test_blocks import garble
    return garble


class Book:
    """`features=` loader of a garbled pass: the build's own loader with every row NOT yet usable at the cut rewritten (the
    rule of engine/tests/test_blocks.py: late = usable_ns > cut). A decision at or before the cut can read none of them."""

    def __init__(self, inner, cut: int, seed: int):
        self.inner, self.cut, self.seed = inner, int(cut), int(seed)
        self.columns = getattr(inner, "columns", None)

    def __call__(self, d):
        f = self.inner(d)
        if f is None:
            return None
        late = f.usable_ns > self.cut
        n, g, cols = int(late.sum()), np.random.default_rng(self.seed), {}
        for k, v in f.cols.items():
            v = v.copy()
            if n:
                v[late] = (g.integers(0, 2, n).astype(bool) if v.dtype.kind == "b" else g.integers(0, 1000, n) if v.dtype.kind in "iu"
                           else g.normal(0.0, 1000.0, n)).astype(v.dtype)
            cols[k] = v
        return S.Features(f.usable_ns, cols)


def _num(v):
    """A logged number: a float, None for none / NaN (NaN never equals itself)."""
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else v


def _spy(cls, levels):
    """A subclass of the card's class that logs, after every callback, what the rule did (module docstring). `levels` = what to
    ask levels.levels for at each bar close (None: the card reads no level)."""
    import levels as LV

    class Peek(cls):
        log: list = []

        def _seen(self, ctx, t):
            log, s = type(self).log, ctx._s
            last = self.__dict__.get("_pk_o")
            start = last[1] if last is not None and last[0] is s else 0
            for o in s.orders:
                if o.id > start and o.role == "entry":
                    log.append((t, "order", (S.NAME[o.side], o.kind, _num(o.price), _num(o.sl), _num(o.tp))))
            self.__dict__["_pk_o"] = (s, s._ids)
            nb = self.__dict__.get("nb")
            if nb is None or nb == self.__dict__.get("_pk_nb"):
                return
            self.__dict__["_pk_nb"] = nb
            if nb:
                try:
                    w = self.vw()
                    log.append((t, "bar", (nb, _num(self.C[-1]), _num(self.atr), _num(w[0]) if w else None)))
                except Exception as e:  # noqa: BLE001 - a value the class does not hold is logged as such, on both tapes
                    log.append((t, "bar", repr(e)))
            if levels is not None:
                try:
                    got = {k: (_num(a), _num(b)) for k, (a, b) in sorted(LV.levels(self, levels).items())}
                except Exception as e:  # noqa: BLE001
                    got = repr(e)
                log.append((t, "level", got))

        def _call(self, fn, ctx, *a):
            t = ctx.now_ns
            try:
                fn(ctx, *a)
            except Exception as e:
                type(self).log.append((t, "error", f"{type(e).__name__}: {e}"))
                raise
            self._seen(ctx, t)

        def on_session(self, ctx):
            self._call(super().on_session, ctx)

        def on_bar(self, ctx, bar):
            self._call(super().on_bar, ctx, bar)

        def on_time(self, ctx, et_time):
            self._call(super().on_time, ctx, et_time)

    Peek.__name__ = Peek.__qualname__ = f"Peek{cls.__name__}"
    return Peek


def reads_levels(p: dict):
    """What a card's instance asks of the liquidity levels: its `levels` (the liq trigger), "all" for a level / swept filter, or None."""
    if any(str(p.get(k, "off")) != "off" for k in LEVEL_KEYS):
        return "all"
    return p.get("levels") or None


def windows(cls, params: list) -> list:
    """The card's own trading window(s): [(start, end)] in seconds after 00:00 ET of the trade date (negative = the evening
    before), the sessions its instances trade (the Template's session table), else the class's session window."""
    out = set()
    for p in params:
        st = cls(p)
        tab, ids = getattr(st, "S", None), (st.sessions() if hasattr(st, "sessions") else [])
        got = [tuple(tab[s]) for s in ids if tab and s in tab]
        if not got and st.session_window:
            got = [(S._sec(st.session_window[0]), S._sec(st.session_window[1]))]
        out.update(got)
    return sorted((int(a), int(b)) for a, b in out if b - a > 60)


def cut_times(iso: str, wins: list, k: int, seed: int) -> list:
    """`k` cut times (ns, whole seconds) of one trade date inside the windows, drawn with the fixed seed (the same for the same day)."""
    d = dt.date.fromisoformat(iso)
    g = np.random.default_rng([seed, d.toordinal()])
    t0 = S.et_ns(d, "00:00")
    span = np.array([b - a - 60 for a, b in wins], float)
    out = set()
    for _ in range(k):
        i = int(g.choice(len(wins), p=span / span.sum()))
        out.add(t0 + (wins[i][0] + 60 + int(g.integers(0, int(span[i])))) * S.NS)
    return sorted(out)


def _pass(specs, root, iso, tape, eng, feats=None) -> list:
    """ONE engine pass of one day on `tape` (the engine's own run_many, its tape loader swapped for this day only) -> per
    instance (log, result)."""
    real, d = S.load_tape, dt.date.fromisoformat(iso)

    def load(day, r="NQ", *a, **kw):
        return tape if S._date(day) == d and r == root else real(day, r, *a, **kw)

    for cls, _ in specs:
        cls.log = []
    kw = dict(eng) if feats is None else {**eng, "features": feats}
    S.load_tape = load
    try:
        res = S.run_many(specs, period=RUN.PERIOD, days=[iso], root=root, workers=1, **kw)
    finally:
        S.load_tape = real
    return [(list(cls.log), r) for (cls, _), r in zip(specs, res)]


def _fills(r: dict, cut: int) -> list:
    """The fills of a result before the cut: (entry ms, side, entry price) and, when it closed before the cut, its exit."""
    out = []
    for t in r["trades"]:
        if t["entry_ms"] * 1_000_000 < cut:
            out.append((t["entry_ms"], t["side"], _num(t["entry_price"]))
                       + ((t["exit_ms"], _num(t["exit_price"]), t.get("exit_reason")) if t["exit_ms"] * 1_000_000 < cut else ()))
    return out


def _crashed(r: dict) -> bool:
    return any(x["reason"].startswith(S.ERROR_PREFIX) for x in r["no_trade"])


def differ(clean, dirty, cut: int):
    """The first thing decided at or before the cut that is not the same on both tapes: (when ns | ms, kind, clean, garbled), or None."""
    (la, ra), (lb, rb) = clean, dirty
    a, b = [x for x in la if x[0] <= cut], [x for x in lb if x[0] <= cut]
    for x, y in zip(a, b):
        if x != y:
            if x[:2] == y[:2]:                       # the same moment and kind, another value
                return x[0], x[1], x[2], y[2]
            first = x if (x[0], x[1]) <= (y[0], y[1]) else y      # one tape has something the other has not (at that moment)
            return (first[0], first[1], first[2], None) if first is x else (first[0], first[1], None, first[2])
    if len(a) != len(b):
        x = a[len(b)] if len(a) > len(b) else b[len(a)]
        return (x[0], x[1], x[2], None) if len(a) > len(b) else (x[0], x[1], None, x[2])
    if _crashed(ra) or _crashed(rb):                 # a session dropped by an error after the cut keeps no trade: the log above holds its orders
        return None
    fa, fb = _fills(ra, cut), _fills(rb, cut)
    if fa != fb:
        i = next((i for i, (x, y) in enumerate(zip(fa, fb)) if x != y), min(len(fa), len(fb)))
        x, y = (fa[i] if i < len(fa) else None), (fb[i] if i < len(fb) else None)
        return ((x or y)[0] * 1_000_000, "trade", x, y)
    return None


def _day(job) -> dict:
    """WORKER: one build day -- the clean pass, then one garbled pass per cut -> {"iso", "cuts", "moved": [...], "read": {...}}."""
    family, root, iso, insts, eng, seed, cuts = job
    blocks = RUN._blocks()
    garble, cls = _garble(), blocks.WRAPPED[family]
    eng = RUN._engine(eng)
    specs = [(_spy(cls, reads_levels(p)), p) for _, p in insts]
    real = S.load_tape(dt.date.fromisoformat(iso), root, allow_holdout=RUN.PERIOD)
    out = {"iso": iso, "cuts": 0, "moved": [], "read": {"order": 0, "bar": 0, "level": 0, "trade": 0}}
    if real is None or not len(real.ts):
        return out
    clean = _pass(specs, root, iso, real, eng)
    if all(not r["used"] for _, r in clean):         # a day the engine skips (a coverage hole): nothing to hold against
        return out
    for k, cut in enumerate(cuts):
        feats = None if eng.get("features") is None else Book(eng["features"], cut, seed + k)
        dirty = _pass(specs, root, iso, garble(real, cut, seed=seed + k), eng, feats)
        out["cuts"] += 1
        for (name, _), c, g in zip(insts, clean, dirty):
            for x in c[0]:
                if x[0] <= cut and x[1] in out["read"]:
                    out["read"][x[1]] += 1
            out["read"]["trade"] += len(_fills(c[1], cut))
            got = differ(c, g, cut)
            if got is not None:
                out["moved"].append({"date": iso, "cut_ns": int(cut), "setting": name, "at_ns": int(got[0]), "what": got[1],
                                     "clean": got[2], "garbled": got[3]})
    return out


# ================================================================ the line

def _et(ns: int, iso: str) -> str:
    """A moment on the New York clock: 'HH:MM:SS ET', + 'the evening before' when it lies before 00:00 of the trade date."""
    t = dt.datetime.fromtimestamp(ns / 1e9, S.ET)
    return t.strftime("%H:%M:%S ET") + ("" if t.date().isoformat() == iso else " the evening before" if t.date() < dt.date.fromisoformat(iso) else f" on {t.date()}")


def _say(v, what: str) -> str:
    if v is None:
        return "nothing"
    if what == "level" and isinstance(v, dict):
        return ", ".join(f"{k} {_px(a)} / {_px(b)}" for k, (a, b) in v.items()) or "no level"
    if what == "order" and isinstance(v, tuple):
        side, kind, px, sl, tp = v
        return f"{side} {kind}" + (f" at {_px(px)}" if px is not None else "") + f" (stop {_px(sl)}, target {_px(tp)})"
    if what == "bar" and isinstance(v, tuple):
        nb, c, a, w = v
        return f"bar {nb}: close {_px(c)}, ATR {_px(a)}, VWAP {_px(w)}"
    if what == "trade" and isinstance(v, tuple):
        return f"{v[1]} filled at {_px(v[2])}" + (f", out at {_px(v[4])} ({v[5]})" if len(v) > 3 else "")
    return str(v)


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _px(v) -> str:
    return "none" if v is None else f"{v:,.2f}".rstrip("0").rstrip(".")


def _first_level(m: dict) -> str:
    """'level asia2000 15,040 / 14,960 -> 15,398.25 / 14,960' -- the first level that moved, else the whole levels."""
    a, b = m["clean"], m["garbled"]
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                fmt = lambda x: "none" if x is None else f"{_px(x[0])} / {_px(x[1])}"  # noqa: E731
                return f"level {k} {fmt(a.get(k))} -> {fmt(b.get(k))}"
    return f"{m['what']} {_say(a, m['what'])} -> {_say(b, m['what'])}"


def words(m: dict) -> str:
    """One cut that moved, in plain words: date, cut, setting, when and what."""
    return (f"{m['date']}, prints garbled from {_et(m['cut_ns'], m['date'])}, setting {m['setting']}: at {_et(m['at_ns'], m['date'])} "
            + (_first_level(m) if m["what"] == "level" else f"{m['what']} {_say(m['clean'], m['what'])} -> {_say(m['garbled'], m['what'])}"))


def build_days(root: str, n: int) -> list:
    """`n` sessions of the build range, evenly spread over it (the same ones every time)."""
    have = [d.isoformat() for d in S.sessions(*S.period(RUN.PERIOD), root, allow_holdout=RUN.PERIOD)]
    if len(have) <= n:
        return have
    return [have[int(i)] for i in np.unique(np.linspace(0, len(have) - 1, n).round().astype(int))]


def instances(family: str, cells: list, sessions: list, xi=None, most: int | None = None) -> list:
    """The card's instances: one exit cell per variant (exit `xi`, default the first), at most `most` variants spread over the
    list -> [(setting words, params)], one per session the class trades (run_idea.cell_specs)."""
    import run_idea as RI
    cls = RUN._blocks().WRAPPED[family]
    xi = min(c.get("xi", 0) for c in cells) if xi is None else xi
    pick = [c for c in cells if c.get("xi", 0) == xi] or cells[:1]
    if most and len(pick) > most:
        pick = [pick[int(i)] for i in np.unique(np.linspace(0, len(pick) - 1, most).round().astype(int))]
    out = []
    for c in pick:
        name = " ".join(f"{k} {v}" for k, v in (c.get("variant") or {}).items()) or c.get("id") or "the rule"
        out += [(name, p) for _, p in RI.cell_specs({"spec": (cls, dict(c["inputs"]))}, list(sessions))]
    return out


def read(family: str, root: str, sessions: list, cells: list, filt=None, xi=None, days=None, workers: int = 1) -> dict:
    """LINE 1.7 on the card's own instances (module docstring) -> the line's row. `cells` = the store's cells ({id, xi, variant,
    inputs}); `days` = named build days (default: rules.json 1.7, spread over the build range)."""
    need, also = R.need("1.7"), R.rule("1.7")["also"]
    insts = instances(family, cells, sessions, xi, also["settings"])
    if not insts:
        return L._row("1.7", None, None, 0, "the card has no instance to replay")
    wins = windows(RUN._blocks().WRAPPED[family], [p for _, p in insts])
    if not wins:
        return L._row("1.7", None, None, 0, "the card's trading window is not known: no cut can be drawn inside it")
    days = RUN.seal(build_days(root, need["days"]) if days is None else list(days))
    eng = RUN._kw(family, filt)
    jobs = [(family, root, iso, insts, eng, also["seed"], cut_times(iso, wins, need["cuts"], also["seed"])) for iso in days]
    workers = max(1, min(int(workers), len(jobs), S.MAX_WORKERS))
    if workers > 1 and S.pool_usable():
        with get_context("spawn").Pool(workers) as pool:
            got = pool.map(_day, jobs)
    else:
        got = [_day(j) for j in jobs]
    moved = [m for g in got for m in g["moved"]]
    n_cuts, n_days = sum(g["cuts"] for g in got), sum(1 for g in got if g["cuts"])
    bad = len({(m["date"], m["cut_ns"]) for m in moved})
    read_ = {k: sum(g["read"][k] for g in got) for k in ("order", "bar", "level", "trade")}
    where = (f"{n_days} build day{'s' * (n_days != 1)} x {need['cuts']} cut times inside its window ({n_cuts} cuts, "
             f"{len({n for n, _ in insts})} setting{'s' * (len({n for n, _ in insts}) != 1)})")
    shown = [{**m, "text": words(m)} for m in moved[:SHOWN]]
    if not n_cuts:
        return L._row("1.7", None, None, 0, "no build day could be replayed: the look-ahead check read nothing", days=len(days))
    if bad:
        return L._row("1.7", False, bad, 0, f"the rule looks ahead: on {bad} of {n_cuts} cuts ({where}) something it decided at or before the cut "
                      f"changed when the prints after the cut were garbled. First: {shown[0]['text']}", moved=shown, cuts=n_cuts, read=read_)
    return L._row("1.7", True, 0, 0, f"no look-ahead: {where}; with every print{' and book row' if eng.get('features') else ''} from the cut on "
                  f"garbled, nothing decided up to the cut moved ({_count(read_['order'], 'order')}, {_count(read_['bar'], 'bar close')}, "
                  f"{_count(read_['level'], 'level read')}, {_count(read_['trade'], 'fill')} compared)", moved=[], cuts=n_cuts, read=read_)


def of_store(t: dict, cell=None, workers: int = 1, days=None) -> dict:
    """LINE 1.7 of the code check's trade table `t` (checks.load): a store of the engine is replayed; anything else is not read."""
    if t["kind"] != "store":
        return L._row("1.7", None, None, 0, "a trades file cannot be replayed: the look-ahead check runs on a store of the engine (--store)")
    try:
        meta = json.loads((Path(t["where"]) / "run.json").read_text())
    except (OSError, ValueError):
        return L._row("1.7", None, None, 0, f"{t['label']} has no run.json to replay")
    family, cells = meta.get("family"), meta.get("cells") or []
    if family not in RUN._blocks().WRAPPED or not cells or not all("inputs" in c for c in cells):
        return L._row("1.7", None, None, 0, f"{t['label']} is not a store of the engine (family {family!r}): its rule cannot be replayed")
    xi = next((c.get("xi", 0) for c in cells if c.get("id") == cell), None)
    f = meta.get("filter")
    filt = (f["block"], f["side"]) if isinstance(f, dict) else tuple(f) if isinstance(f, list) else f      # run.json keeps {block, side, plain}
    return read(family, meta.get("root") or t["root"], meta.get("sessions") or [], cells, filt, xi, days, workers)
