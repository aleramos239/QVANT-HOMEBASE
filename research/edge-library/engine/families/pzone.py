"""pzone -- STACKED PROFILE ZONES TRADED ON THE FIRST TOUCH (the owner, 2026-10-23), written from the rule before any result. The zones are
the chart's "Stacked profile zones" indicator (homebase/static/charts/flowmath.js profileZones, from cabatrades' "three profiles, one level"),
restated here on the tick tape. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

THE OWNER'S WORDS: "if we are below a level and we tap it we short and when we are above and tap it we long, lets try 1:1 and 1,2 x atr stop".

THE ZONES (one trade date = one Globex session tape, 18:00 ET the evening before -> 17:00 ET; the chart's `bar.s`):
  * ROWS of `rows` ticks (default 4 = 1 NQ point); a price's row = floor(round(px / tick) / rows).
  * VOLUME PROFILE = the prints' size per row. DELTA PROFILE = buys minus sells per row, the side of each print by the TICK RULE (up from the
    print before = a buy, down = a sell, the same price = the side before): an ESTIMATE, the tape carries no aggressor side (flowtab.py's
    minute delta does the same where no quote was recorded). The chart reads the vendor's side; the two can differ.
  * TPO = letters of `period` minutes (30) counted from the session's first minute; a letter marks every row from its low to its high
    (Sierra's range mode). A SINGLE PRINT = a row with one letter that is not the session's last letter.
  * A ZONE = a row whose |delta| >= `outlier` (3) x a median |delta|, with a single print AND a low volume node (a TPO row with volume <=
    `lvn` % (30) of the busiest row) within one row of it. Its price span is the row: lo .. lo + rows - 1 ticks. The median (`base`):
      session (the first runs) = of the session's traded rows;
      leg (the owner 2026-10-23, "a delta outlier from the last leg", the chart's rule since) = of ONE LEG: a run of at least 3 single-print
      rows next to each other (one fast move), its traded rows; the zone is a row of that run.
  * A zone a later minute of its own session already traded back into (after the end of its letter) is not kept: the chart ends it there.
THE LEVELS A DAY TRADES: the zones of the `back` (5) trade dates before it that no later minute has touched -- a touch = a 1-minute bar whose
  low .. high reaches the zone's span -- read through the dates in order, then through the trade date's own evening (18:00 -> 00:00), then
  minute by minute as the day is replayed. A zone touched is gone, with or without a trade there.
  A prior date this run may not open (a sealed test month, a hole in the tape) breaks the chain: the zones from before it are dropped (whether
  price touched them meanwhile is unknown), and a date more than 10 calendar days before the trade date is never read.
THE ORDERS (the owner's rule): at each tf close inside the idea's session, flat, entries left: the nearest live zone ABOVE the close gets a
  limit SELL at its low (price below the level taps it -> short) and the nearest live zone BELOW gets a limit BUY at its high (price above taps
  it -> long). The two are one OCO pair (as ib_touch). An order whose zone is no longer the nearest, or is gone, is cancelled and replaced at
  that close. A limit fills on a one-tick trade-through (the engine's law), so a bare touch is no fill but uses the zone up.
EVERY ZONE (`orders` all, the owner 2026-10-23 "put an order at every live zone"): every live zone gets its order at the tf close (a sell at
  the low of each one above the close, a buy at the high of each one below; with `match`, only the matching colour), all one OCO group: the
  first fill cancels the rest; the others come back at the next tf close once flat. nearest (default) = the nearest zone each side only.
6PM VWAP (`vwap18` zone = the order's zone price on the owner's side of the VWAP; fix = the side set once at `vfix`; with = the owner 2026-10-23 "try adding a 6pm vwap filter only long above and short below"): the VWAP of the 1-minute bars
  from 18:00 ET of the evening before (avwap.py's globex line, its minutes and typical price): at the tf close, above it only the buys rest,
  below it only the sells; no VWAP yet = no order. A day instance starts from the evening's minutes on the tape (before 00:00: the past);
  an evening instance builds it from its own minutes as they come.
COLOUR MATCH (`match` on, the owner 2026-10-23 "are we only longing on buyer zone or support and shorting on selling zone or resistance"):
  only a SELLERS' zone (delta < 0) above the close gets the sell, only a BUYERS' zone (delta > 0) below it gets the buy; a zone of the other
  colour is never traded (its first touch still uses it up). off (default) = the side from where price is, the colour ignored.
EXITS: STRUCTURE STOP = entry -/+ `stop_atr` x ATR(14) of the idea's own bars at the moment the order is placed (1 or 2: the owner's two
  stops; 0 = no level, the menu's ATR stop); the target is the sheet's tgt_r x that distance (1 = 1:1). strict_limit, as ib_touch.

NO LOOK-AHEAD: a date's zones are its own prints, read only on later trade dates; the trade date's file is read for its 18:00 -> 00:00
minutes only (the day after is replayed from the tape, minute by minute); the orders are placed at a tf close before the bar that fills them.

CACHE: engine/cache/pzone_<ROOT>/<date>.npz, one file a trade date, the raw profile (no setting in it: every setting is applied when read):
  k0, vol, dlt (per tick from k0), mmin (each minute's start, minutes after the session's first), mlo, mhi (its low / high in ticks), eve (the
  number of minutes before 00:00 ET). `prepare` builds it under the stage's own seal switch; a worker that misses a date tries the tape itself.
REGISTRATION as ib_touch.py (join_blocks). Tests: engine/tests/test_pzone.py."""
from __future__ import annotations

import datetime as dt
import os
from multiprocessing import get_context

import numpy as np

import l2sim as S
from l2sim import Template

SIDE = {-1: "short", 1: "long"}
NS_MIN = 60 * S.NS
EVE0 = -21600                                       # 18:00 ET of the evening before, seconds after 00:00 of the trade date
LEG_MIN = 3                                         # single-print rows in a run to make a leg (base "leg")
MAX_GAP_DAYS = 10
_RAW: dict = {}                                     # (root, iso) -> raw dict | None   (per process)


def _dir(root: str):
    return S.CACHE / f"pzone_{root}"


def raw_of(tape) -> dict | None:
    """The raw profile of ONE session tape (module docstring, CACHE). None without a print."""
    if tape is None or not len(tape.ts):
        return None
    tick = S.SPECS[tape.root][1]
    tk = np.rint(tape.px / tick).astype(np.int64)
    sz = tape.size.astype(np.float64)
    step = np.sign(np.diff(tk, prepend=tk[0]))
    idx = np.where(step != 0, np.arange(len(step)), 0)        # tick rule: carry the last non-zero step forward
    np.maximum.accumulate(idx, out=idx)
    side = step[idx]
    k0 = int(tk.min())
    vol = np.bincount(tk - k0, weights=sz)
    dlt = np.bincount(tk - k0, weights=sz * side)
    m = tape.ts // (60 * S.NS)
    mins, first = np.unique(m, return_index=True)
    ends = np.append(first[1:], len(m))
    mlo = np.minimum.reduceat(tk, first)
    mhi = np.maximum.reduceat(tk, first)
    mid = S.et_ns(tape.date, "00:00") // (60 * S.NS)
    return {"k0": k0, "vol": vol, "dlt": dlt, "mmin": (mins - mins[0]).astype(np.int64), "mlo": mlo, "mhi": mhi,
            "eve": int(np.searchsorted(mins, mid)), "n": int(len(ends))}


def zones_of(raw: dict, rows: int, period: int, outlier: float, lvn: float, base: str = "session") -> list:
    """[(lo_tick, hi_tick, side, delta)] of one session's raw profile: flowmath.js profileZones on ticks; a zone its own session traded back
    into after its letter is left out."""
    if raw is None:
        return []
    rt = max(1, int(rows))
    k0, vol, dlt = raw["k0"], raw["vol"], raw["dlt"]
    tk = np.arange(len(vol)) + k0
    traded = vol > 0
    rv, rd = {}, {}
    for r, v, d in zip(np.floor_divide(tk[traded], rt), vol[traded], dlt[traded]):
        rv[int(r)] = rv.get(int(r), 0.0) + float(v)
        rd[int(r)] = rd.get(int(r), 0.0) + float(d)
    if not rv:
        return []
    mper = raw["mmin"] // int(period)
    rlo, rhi = np.floor_divide(raw["mlo"], rt), np.floor_divide(raw["mhi"], rt)
    periods = int(mper.max()) + 1
    lets: dict = {}
    for p in range(periods):
        sel = mper == p
        if sel.any():
            for r in range(int(rlo[sel].min()), int(rhi[sel].max()) + 1):
                lets.setdefault(r, set()).add(p)
    single = {r for r, ps in lets.items() if len(ps) == 1 and next(iter(ps)) < periods - 1}
    lvn_max = max(rv.values()) * lvn / 100.0
    is_lvn = lambda r: r in lets and rv.get(r, 0.0) <= lvn_max            # noqa: E731
    if base == "leg":
        cand = set()
        ks = sorted(single)
        a = 0
        while a < len(ks):
            b = a + 1
            while b < len(ks) and ks[b] == ks[b - 1] + 1:
                b += 1
            leg = [k for k in range(ks[a], ks[b - 1] + 1) if k in rd]
            if b - a >= LEG_MIN and leg:
                absd = sorted(abs(rd[k]) for k in leg)
                med = absd[len(absd) // 2]
                if med > 0:
                    cand |= {k for k in leg if abs(rd[k]) >= outlier * med}
            a = b
        picked = [(r, rd[r]) for r in cand if any(is_lvn(j) for j in (r - 1, r, r + 1))]
    else:
        absd = sorted(abs(x) for x in rd.values())
        med = absd[len(absd) // 2]
        if not med > 0:
            return []
        picked = [(r, d) for r, d in rd.items() if abs(d) >= outlier * med and any(j in single for j in (r - 1, r, r + 1))
                  and any(is_lvn(j) for j in (r - 1, r, r + 1))]
    out = []
    for r, d in picked:
        cov = (rlo <= r) & (r <= rhi)
        i = int(np.argmax(cov))                                          # the first minute that traded the row
        later = cov & (mper > mper[i])
        if later.any():
            continue                                                     # traded back into after its letter: the chart ended it that day
        out.append((r * rt, r * rt + rt - 1, int(np.sign(d)), d))
    return sorted(out)


def _save(root: str, iso: str, raw: dict | None) -> None:
    p = _dir(root) / f"{iso}.npz"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{iso}.{os.getpid()}.tmp.npz")
    if raw is None:
        np.savez(tmp, none=np.array(1))
    else:
        np.savez(tmp, **{k: np.asarray(v) for k, v in raw.items()})
    os.replace(tmp, p)


def raw(root: str, iso: str) -> dict | None:
    """The raw profile of trade date `iso`: the cache file, else the tape (under the process's own seal: a sealed date is None)."""
    key = (root, iso)
    if key not in _RAW:
        p = _dir(root) / f"{iso}.npz"
        if p.exists():
            z = np.load(p)
            v = None if "none" in z.files else {k: (int(z[k]) if z[k].ndim == 0 else z[k]) for k in z.files}
        else:
            try:
                v = raw_of(S.load_tape(iso, root))
            except S.HoldoutSealed:
                v = None
                _RAW[key] = v
                return v
        _RAW[key] = v
    return _RAW[key]


def _one(args):
    iso, root, allow = args
    S.wait_compute_window()
    t = S.load_tape(iso, root, **allow)
    _save(root, iso, raw_of(t))
    return iso


def build(root: str, period="build", workers: int = 1, **allow) -> dict:
    """Fill cache/pzone_<root>/ with every session of `period` it does not hold yet (round1.build_va's way, under the stage's own switch)."""
    a, b = S.period(period)
    have = {p.stem for p in _dir(root).glob("*.npz")} if _dir(root).exists() else set()
    todo = [(d.isoformat(), root, allow) for d in S.sessions(a, b, root, **allow)
            if d.isoformat() not in have and (root == "NQ" or S.hb_tape_path(d, root) is not None)]
    if todo:
        workers = max(1, min(int(workers), S.MAX_WORKERS))
        S.wait_compute_window()
        if workers == 1 or not S.pool_usable():
            for x in todo:
                _one(x)
        else:
            with get_context("spawn").Pool(workers) as pool:
                pool.map(_one, todo, chunksize=8)
    return {"path": str(_dir(root)), "added": len(todo)}


def _touch(z, lo, hi):
    return [x for x in z if not (lo <= x[1] and hi >= x[0])]


class PZone(Template):
    """pzone (module docstring). State per day: live = [(lo_tick, hi_tick, side, delta)] the zones not touched yet, mi = the 1-minute bars
    already read for a touch, tick."""
    DEFAULTS = {"rows": 4, "period": "30", "outlier": 3.0, "lvn": 30, "back": 5, "stop_atr": 1.0, "match": "off", "base": "session", "orders": "nearest", "vwap18": "off", "vfix": 570, "ema1h": 0, "emaside": "with", "reuse": "off", "max_tr": 10}
    SCHEMA = {"rows": ("int", 1, 40), "period": ("choice", ("15", "30", "60")), "outlier": ("float", 1.5, 20.0), "lvn": ("int", 5, 80),
              "back": ("int", 1, 30), "stop_atr": ("float", 0.0, 10.0), "match": ("choice", ("off", "on")), "base": ("choice", ("session", "leg")), "orders": ("choice", ("nearest", "all")), "vwap18": ("choice", ("off", "with", "fix", "zone")), "vfix": ("int", 0, 960),
              "ema1h": ("int", 0, 500), "emaside": ("choice", ("with", "against")), "reuse": ("choice", ("off", "on"))}
    SCREEN_TFS = ("1", "5", "15")
    SCREEN_RUN = {"strict_limit": True}
    FEATURES = ()

    @classmethod
    def prepare(cls, root, workers=1, period="build", **allow):
        return build(root, period, workers, **allow)

    def fam_day(self, ctx):
        self.tick = S.SPECS[ctx.root][1]
        self.mi = 0
        self.oz = {}                                     # order id -> the zone (lo, hi) it rests at (Order has __slots__)
        p, day = self.p, ctx.date
        args = (int(p["rows"]), int(p["period"]), float(p["outlier"]), float(p["lvn"]), p["base"])
        prior = [x["date"] for x in self.dl if x.get("date") and x["date"] < day.isoformat()][-int(p["back"]):]
        live: list = []
        for iso in prior:
            if (day - dt.date.fromisoformat(iso)).days > MAX_GAP_DAYS:
                continue
            r = raw(ctx.root, iso)
            if r is None:
                live = []                                # unknown whether the zones before it were touched
                continue
            if p["reuse"] == "off":
                for lo, hi in zip(r["mlo"], r["mhi"]):
                    live = _touch(live, int(lo), int(hi))
            live += zones_of(r, *args)
        own = raw(ctx.root, day.isoformat()) if not self.off else None     # an evening instance replays its 18:00 -> 00:00 itself
        if own is not None and p["reuse"] == "off":      # the trade date's own evening (18:00 -> 00:00) only
            for lo, hi in zip(own["mlo"][:own["eve"]], own["mhi"][:own["eve"]]):
                live = _touch(live, int(lo), int(hi))
        self.live = live
        self.vv = self.vp = 0.0
        self.fixed = 0                                   # vwap18 "fix": the side set once at vfix (+1 / -1), 0 = not yet
        if self.p["vwap18"] != "off" and not self.off:
            from families import avwap as AV
            ev = AV.evening(ctx.root, day.isoformat())
            if ev is None:
                self.vv = float("nan")                   # no evening on the tape: no line today
            else:
                self.vv, self.vp = float(ev["v"].sum()), float(ev["tpv"].sum())

    def _read(self, ctx):
        M = self.M
        for i in range(self.mi, len(M)):
            sec, _, h, l, c, v = M[i]
            if self.p["reuse"] == "off":
                self.live = _touch(self.live, int(round(l / self.tick)), int(round(h / self.tick)))
            if v > 0 and sec >= EVE0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
        self.mi = len(M)
        keep = {(z[0], z[1]) for z in self.live}
        for r in self.orders:
            if self.oz.get(r[0].id) not in keep:
                ctx.cancel(r[0])

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        self._read(ctx)

    def fam_update(self, ctx):
        self._read(ctx)

    def can_enter(self, ctx):
        """The Template's rule; this family's own resting orders do not stand in the way of the other side's (ib_touch)."""
        self._sync(ctx)
        rest, self.orders = self.orders, []
        ok = super().can_enter(ctx)
        self.orders = rest
        return ok

    def fam_signal(self, ctx):
        c = int(round(self.C[-1] / self.tick))
        m = self.p["match"] == "on"
        allow = {-1, 1}
        if self.p["vwap18"] != "off":                   # above the 6pm VWAP: buys only; below (or on it): sells only; none yet: nothing
            allow = set() if not self.vv > 0 else {1} if c * self.tick > self.vp / self.vv else {-1}
        if self.p["vwap18"] == "fix":                   # the side is read once, at the first tf close from vfix (ET minutes) on
            if not self.fixed and self.vv > 0 and (ctx.now_ns - S.et_ns(ctx.date, "00:00")) // NS_MIN >= int(self.p["vfix"]):
                self.fixed = 1 if c * self.tick > self.vp / self.vv else -1
            allow = {self.fixed} if self.fixed else set()
        if int(self.p["ema1h"]) and allow:              # the 1-hour EMA (candle_sweep's): with = buys above it, sells below
            from families.candle_sweep import ema_last, hour_closes, prior_closes
            n, d = int(self.p["ema1h"]), ctx.date
            today = hour_closes(ctx._s.ts, ctx._s.px, S.et_ns(d - dt.timedelta(days=1), "18:00"), ctx.now_ns)
            e = ema_last(np.concatenate((prior_closes(self, 3 * n - len(today)), today)), n)
            if e is None:
                allow = set()
            else:
                up = 1 if self.C[-1] > e else -1
                allow &= {up if self.p["emaside"] == "with" else -up}
        side = lambda z: -1 if z[0] > c else 1 if z[1] < c else 0              # noqa: E731
        ok = [z for z in self.live if side(z) in allow and (not m or z[2] * side(z) > 0)]
        if self.p["vwap18"] == "zone":                  # the zone's own price against the 6pm VWAP: a buy needs its zone above it, a sell below
            ok = [] if not self.vv > 0 else [z for z in ok if (z[1] * self.tick > self.vp / self.vv if side(z) > 0 else z[0] * self.tick < self.vp / self.vv)]
        above = min((z for z in ok if side(z) < 0), default=None, key=lambda z: z[0])
        below = max((z for z in ok if side(z) > 0), default=None, key=lambda z: z[1])
        if self.p["orders"] == "all":
            want = {(z[0], z[1]): side(z) for z in ok}
        else:
            want = {(z[0], z[1]): sd for sd, z in ((-1, above), (1, below)) if z is not None}
        work = {}                                        # zone -> its working order
        for r in self.orders:
            o = r[0]
            if o.status != "working":
                continue
            zk = self.oz.get(o.id)
            if want.get(zk) != o.side or zk in work:
                ctx.cancel(o)                            # its zone is gone, no longer wanted, or now on the other side: replaced below
            else:
                work[zk] = o
        self.orders = [r for r in self.orders if r[0] in work.values()]
        k = float(self.p["stop_atr"])
        for zk, sd in sorted(want.items()):
            if zk in work:
                continue
            px = (zk[0] if sd < 0 else zk[1]) * self.tick
            struct = None if k <= 0 or self.atr is None else px - sd * k * self.atr
            o = self._lim(ctx, SIDE[sd], round(px, 6), struct=struct)
            if o is not None:
                self.oz[o.id] = zk
                work[zk] = o
        if len(work) >= 2:
            ctx.oco(*work.values())                      # one group: the first fill cancels the rest


FAMILIES = {
    "pzone": (PZone, {}, True,
              "pzone: the stacked profile zones of the 5 trade dates before (a delta outlier with a TPO single print and a low volume node "
              "next to it, 4-tick rows, tick-rule delta) not touched since; at a tf close a limit SELL at the low of the nearest zone above "
              "and a limit BUY at the high of the nearest zone below (one OCO pair); a zone is used up by its first touch; structure stop "
              "stop_atr x ATR from the entry; flat 15:58",
              {"rationale": "A price where one side was far more aggressive and the market passed fast, leaving a thin spot, is where that "
                            "side defends on the first return; the losers are the late traders pushing into it from the other side.",
               "complexity": 7,
               "variants": [{"outlier": 2.0}, {"outlier": 3.0}, {"outlier": 4.0}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as ib_touch.py)."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
