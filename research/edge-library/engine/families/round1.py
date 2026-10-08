"""round1 -- EDGE_SPEC "STAGE 2b -- NEW-IDEA ROUND 1": seven new families, written from the spec text before any result.
No Level-2 feature is read (FEATURES = ()): every family runs on NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET).

    N1 vwap_trend_pull   bar-based 1/5/15/30   nyam / mid / pm, entries 10:30-15:30
    N2 va_reclaim        bar-based 1/5/15/30   all seven sessions
    N3 orb_confirm       bar-based 1/5/15      nyam / mid / pm; LONG-ONLY and SHORT-ONLY are MIRROR units (axis `dir`)
    N4 late_mom          time-fired (tf 30)    one trade at 15:30 ET, flat 15:58
    N5 open_fade         bar-based 1/5         nyam (09:30-11:00)
    N6 vol_spike_break   bar-based 1/5/15/30   all seven sessions
    N7 straddle_tight    time-fired (tf 30)    one registry entry per clock time: straddle_tight_0830 / _0930 / _1000

HOW EACH WRITTEN RULE IS READ (fixed here, before any run; nothing below was chosen after a result):
  * "a day" in "max N trades a day" / "one trade a day" / "stop for the day after 2 losing trades" = ONE SESSION INSTANCE.
    The engine runs each session of a bar-based family as its own instance (run_menus.DAY_PASSES) and a library member
    trades ONE session, so the member's day is that session: the limit is the Template's `max_tr` of the instance.
  * "enter next bar open" = a market order at the signal bar's close (the Template's `_mkt`): it fills at the first print
    after the 85 ms placement latency, i.e. at the next bar's open or later. Signals read completed bars only.
  * N1  VWAP = volume-weighted typical price (h + l + c) / 3 of the 1-minute bars from 09:30 ET (the engine's VWAP rule).
        "VWAP 3 bars ago" = its value 3 tf closes earlier (both after 09:30). "price up >= X over the last 60 min" = this
        close vs the tf close 60 minutes earlier, in percent. "closes against the trend" = a down bar (close < open) in
        an up state, an up bar in a down state; "first" = the bar before it was not such a bar (the first candle of a
        pullback). The state (close vs VWAP, VWAP slope, 60-minute move) is read on the trigger bar itself.
        A "losing trade" = a closed trade of the instance with net < 0 after costs.
  * N2  value area = the smallest band around the busiest price (1-tick rows; ties: the lowest price) that holds >= 70 %
        of the volume printed 09:30-16:00 ET on the PREVIOUS trade date, grown one row at a time toward the larger
        neighbour row (equal: both). None on a contract-roll day (yesterday's prices are another contract).
        "trades below VAL by >= D" = a tf bar's low is below VAL and at least D below it, D = d_atr x ATR14 of the tf at
        that bar. The poke is remembered since the day's restart; the first later (or the same) bar that closes back above
        VAL is the signal and uses the poke up. A bar that signals both sides at once is skipped.
  * N3  range = high / low of the 1-minute bars 09:30 .. 09:30 + or_min. Signal = a tf bar that ends after the range
        end and closes above the range high (long-only unit) / below the range low (short-only unit), inside the
        instance's session.
  * N4  prior close = the Template's `pdc`: the last print of the previous trade date (none on a contract-roll day ->
        no trade). P_signal = the close of the last 1-minute bar that ENDED by the signal time (for 15:30: the 15:29
        bar, strictly before the 15:30 entry). move = P_signal / prior close - 1 in percent; no trade when it is 0 or
        |move| < thr. The stop ATR is ATR30 (time-fired). NULL (`shift_seed` 1, 2 -- the engine's name for the seed of a
        time-fired family's null): the SAME 15:30 trade on the SAME days, direction = a seeded coin flip per date.
  * N5  ref = the close of the last 1-minute bar before 09:30 (the 09:29 bar). ATR(14, 1-min x 30) = Wilder ATR14 of the
        30-minute bars built from the 1-minute bars since 00:00 (the engine's ATR30), completed bars only, running.
        Stretch: a tf bar after 09:30 trades >= K x ATR30 away from ref -> that side is armed; it is disarmed when price
        trades back to ref or when it signals. Signal: armed above ref and a bar closes below the prior bar's low ->
        short (toward ref); mirror for long.
  * N6  "the last 20 bars" = the 20 tf bars BEFORE the signal bar (median volume and high / low); needs 21 bars since
        the day's restart.
  * N7  the bracket is placed at the clock time minus 1 second around the last print; "cancel after 5 min" = 5 minutes
        after it was placed; entries only until the next listed time / session end (08:30 -> 09:30, 09:30 and 10:00 ->
        11:00). Offsets A / B / C and its own 3 stops x 3 targets are scaled per root (OFF, STOP). A 09:30 fill in the
        last second before 09:30 carries the session tag `pre`: judge this family over session 'all'.

AUTHOR CELLS (EDGE_SPEC: "information only, not in the heat map"): `author_cells(root, tf)` -> extra cells per variant,
flagged `info` in the grid and the store; library.plateau leaves them out. N1: stop 80 pts, target 40 pts long / 50 pts
short, NQ tf 15 only. N3: stop at the other side of the range, flat 15:30. N5: target = ref, with each of the 8 menu
stops (the spec names no stop for it).

COMPLEXITY = rules + free parameters, counted as in port1 / timed (one per level / state definition, per trigger, per
extra condition; one per family input). Tests: tests/test_round1.py."""
from __future__ import annotations

import json
import os
import random
from multiprocessing import get_context
from statistics import median

import numpy as np

import l2ref
import l2sim as S
from l2sim import Template, _hms

TFS = ("1", "5", "15", "30")
NY = ("nyam", "mid", "pm")
OPEN = 34200                                        # 09:30 ET, seconds after 00:00


def bar_end(st) -> int:
    """Nominal close second (after 00:00 ET of the trade date) of the tf bar that has just closed (call in fam_update /
    fam_signal: the last 1-minute bar of st.M belongs to that bar)."""
    step = st.tf * 60
    return (st.M[-1][0] // step + 1) * step


# ---- N1 vwap_trend_pull -----------------------------------------------------------------------------------------------
class VwapTrendPull(Template):
    """N1 (module docstring). LONG state at a tf close: close > VWAP(09:30), VWAP > VWAP 3 bars ago, close >= x % above
    the close 60 minutes ago; trigger = the first down bar while the state holds -> market long. SHORT = mirror.
    Entries 10:30 .. 15:30 ET only, max_tr 4, no entry after max_loss (2) losing trades of the instance."""
    DEFAULTS = {"x": 0.10, "max_tr": 4, "max_loss": 2, "auth": "off"}
    SCHEMA = {"x": ("float", 0.0, 5.0), "max_loss": ("int", 1, 20), "auth": ("choice", ("off", "on"))}
    SCREEN_TFS = TFS
    FEATURES = ()
    T0, T1 = 37800, 55800                           # no entry before 10:30 or after 15:30 ET
    LOOK_S, SLOPE = 3600, 3                         # the 60-minute move . VWAP now vs 3 bars ago
    AUTH = {"stop": 80.0, "long": 40.0, "short": 50.0}      # the author cell, NQ points (tf 15)

    @classmethod
    def author_cells(cls, root, tf):
        if root != "NQ" or str(tf) != "15":
            return []
        return [({"auth": "on"}, {"stop_mode": "pts", "stop_val": cls.AUTH["stop"], "tgt_r": 0.0})]

    def fam_filter(self, ids):
        return [s for s in ids if s in NY]

    def fam_day(self, ctx):
        self.vv = self.vp = 0.0                     # VWAP sums from 09:30: volume, volume x typical price
        self.mi = 0                                 # 1-minute bars already added
        self.vwh = []                               # VWAP at every tf close after 09:30
        self.c_at = {}                              # tf close second -> close
        self.was = 0                                # the previous tf bar: +1 up bar, -1 down bar, 0 neither
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        M = self.M
        for i in range(self.mi, len(M)):
            s, _, h, l, c, v = M[i]
            if s >= OPEN and v > 0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
        self.mi = len(M)
        end = bar_end(self)
        o, c = self.O[-1], self.C[-1]
        self.c_at[end] = c
        bar = (c > o) - (c < o)
        first = bar != 0 and bar != self.was        # the first up / down bar after a bar that was not one
        self.was = bar
        if end <= OPEN or self.vv <= 0:
            return
        vw = self.vp / self.vv
        self.vwh.append(vw)
        c60 = self.c_at.get(end - self.LOOK_S)
        if not first or len(self.vwh) <= self.SLOPE or not c60:
            return
        v3 = self.vwh[-1 - self.SLOPE]
        mv = (c / c60 - 1.0) * 100.0
        x = self.p["x"]
        if bar < 0 and c > vw and vw > v3 and mv >= x:
            self.go = 1                             # an up state, the first candle against it
        elif bar > 0 and c < vw and vw < v3 and mv <= -x:
            self.go = -1

    def fam_signal(self, ctx):
        if not self.go or not self.T0 <= bar_end(self) <= self.T1:
            return
        if sum(1 for t in ctx._s.res.trades if t["net"] < 0) >= self.p["max_loss"]:
            return                                  # stop for the day after 2 losing trades
        if self.p["auth"] != "on":
            self._mkt(ctx, "long" if self.go > 0 else "short")
        elif self.go > 0:
            self._mkt(ctx, "long", tp_px=self.C[-1] + self.AUTH["long"])
        else:
            self._mkt(ctx, "short", tp_px=self.C[-1] - self.AUTH["short"])


# ---- N2 va_reclaim: yesterday's value area ------------------------------------------------------------------------------
VA_SHARE = 0.70
RTH = ("09:30", "16:00")                            # the volume profile is built from the prints of this ET window
_VA: dict = {}                                      # (root, date iso) -> (VAL, VAH) | None      (per process)
_VA_FILE: dict = {}                                 # root -> the cache file's content, read once per process


def value_area_of(tape) -> tuple | None:
    """(VAL, VAH) of ONE tape: the 70 % value area of its own 09:30-16:00 ET prints, volume by price in 1-tick rows.
    Start at the row with the most volume (ties: the lowest price); add the larger of the next row above / below (equal:
    both) until >= 70 % of the volume is inside. None without a print in the window."""
    t0, t1 = S.et_ns(tape.date, RTH[0]), S.et_ns(tape.date, RTH[1])
    a, b = (int(x) for x in np.searchsorted(tape.ts, [t0, t1], side="left"))
    if b <= a:
        return None
    tick = S.SPECS[tape.root][1]
    k = np.rint(tape.px[a:b] / tick).astype(np.int64)
    k0 = int(k.min())
    vol = np.bincount(k - k0, weights=tape.size[a:b].astype(np.float64))
    tot = float(vol.sum())
    if tot <= 0:
        return None
    lo = hi = int(vol.argmax())
    acc = float(vol[lo])
    n = len(vol)
    while acc < VA_SHARE * tot and (lo > 0 or hi < n - 1):
        up = vol[hi + 1] if hi < n - 1 else -1.0
        dn = vol[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1
            acc += float(up)
        if dn >= up:
            lo -= 1
            acc += float(dn)
    return round((k0 + lo) * tick, 6), round((k0 + hi) * tick, 6)


def _va_path(root: str):
    return S.CACHE / f"va70_{root}.json"


def value_area(root: str, iso: str) -> tuple | None:
    """(VAL, VAH) of trade date `iso` (value_area_of its tape): the cache file when it holds the date, else computed from
    the tape and remembered for this process. A 2025+ date raises HoldoutSealed (load_tape): the EXAM stays sealed."""
    key = (root, iso)
    if key not in _VA:
        if root not in _VA_FILE:
            p = _va_path(root)
            _VA_FILE[root] = json.loads(p.read_text()) if p.exists() else {}
        if iso in _VA_FILE[root]:
            v = _VA_FILE[root][iso]
        else:
            t = S.load_tape(iso, root)
            v = None if t is None or not len(t.ts) else value_area_of(t)
        _VA[key] = None if v is None else (float(v[0]), float(v[1]))
    return _VA[key]


def _va_one(args):
    iso, root, *rest = args
    S.wait_compute_window()
    t = S.load_tape(iso, root, **(rest[0] if rest else {}))
    return iso, (None if t is None or not len(t.ts) else value_area_of(t))


def build_va(root: str, period="build", workers: int = 1, **allow) -> dict:
    """Fill cache/va70_<root>.json with the value area of every session of `period` (default BUILD: nothing else is read)
    that the file does not hold yet. -> {'path', 'dates', 'added'}. Run in the main process before a va_reclaim pass
    (run_menus calls VaReclaim.prepare); a worker that misses a date computes it itself, with the same function.
    `period` may be a (start, end) pair and `allow` the engine's own seal switch of the stage that opens it (the blueprint's build: allow_holdout=
    "bp_build"; its test: the test switch), handed to the session list and the tape loads unchanged -- never set by anything but a stage."""
    p = _va_path(root)
    have = json.loads(p.read_text()) if p.exists() else {}
    a, b = S.period(period)
    todo = [(d.isoformat(), root, allow) for d in S.sessions(a, b, root, **allow)
            if d.isoformat() not in have and (root == "NQ" or S.hb_tape_path(d, root) is not None)]
    if todo:
        workers = max(1, min(int(workers), S.MAX_WORKERS))
        S.wait_compute_window()
        if workers == 1 or not S.pool_usable():
            res = [_va_one(x) for x in todo]
        else:
            with get_context("spawn").Pool(workers) as pool:
                res = pool.map(_va_one, todo, chunksize=16)
        have.update(dict(res))
        have = dict(sorted(have.items()))
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(have))
        os.replace(tmp, p)
        _VA_FILE.pop(root, None)
    return {"path": str(p), "dates": len(have), "added": len(todo)}


class VaReclaim(Template):
    """N2 (module docstring). LONG: a tf bar trades below yesterday's VAL by >= d_atr x ATR14, then a bar closes back
    above VAL -> market long. SHORT = mirror at VAH. One trade per side per instance (max_tr 2)."""
    DEFAULTS = {"d_atr": 0.25, "max_tr": 2}
    SCHEMA = {"d_atr": ("float", 0.0, 10.0)}
    SCREEN_TFS = TFS
    FEATURES = ()

    @classmethod
    def prepare(cls, root, workers=1, period="build", **allow):
        return build_va(root, period, workers, **allow)

    def fam_day(self, ctx):
        self.poke = {1: False, -1: False}           # +1: traded below VAL (long setup), -1: traded above VAH
        self.used = {1: False, -1: False}           # one trade per side
        self.go = 0
        d1 = self.dl[-1] if self.dl else None
        # self.pdc is None on a contract-roll day: yesterday's prices are another contract -> no value area today
        self.va = value_area(ctx.root, d1["date"]) if d1 and d1.get("date") and self.pdc is not None else None

    def fam_update(self, ctx):
        self.go = 0
        if self.va is None or self.atr is None:
            return
        val, vah = self.va
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        d = self.p["d_atr"] * self.atr
        if l < val and val - l >= d:
            self.poke[1] = True
        if h > vah and h - vah >= d:
            self.poke[-1] = True
        up, dn = self.poke[1] and c > val, self.poke[-1] and c < vah
        if up:
            self.poke[1] = False
        if dn:
            self.poke[-1] = False
        if up != dn:                                # both at once (one bar through the whole value area): no signal
            self.go = 1 if up else -1

    def fam_signal(self, ctx):
        g = self.go
        if g and not self.used[g] and self._mkt(ctx, "long" if g > 0 else "short") is not None:
            self.used[g] = True


# ---- N3 orb_confirm -------------------------------------------------------------------------------------------------------
class OrbConfirm(Template):
    """N3 (module docstring). Range = the first or_min minutes from 09:30; a tf bar that ends after the range and closes
    above its high -> market long (dir long) / below its low -> market short (dir short). One trade per instance.
    The struct stop (author cell) = the other side of the range."""
    DEFAULTS = {"or_min": "15", "dir": "long", "max_tr": 1, "auth": "off"}
    SCHEMA = {"or_min": ("choice", ("15", "30", "60")), "dir": ("choice", ("long", "short")), "auth": ("choice", ("off", "on"))}
    SCREEN_TFS = ("1", "5", "15")
    FEATURES = ()
    X_S = 55800                                     # the author cell: flat 15:30 ET, no entry from then on

    @classmethod
    def author_cells(cls, root, tf):
        return [({"auth": "on"}, {"stop_mode": "struct", "stop_val": 1.5, "tgt_r": 0.0})]

    def fam_filter(self, ids):
        return [s for s in ids if s in NY]

    def fam_day(self, ctx):
        self.r = None

    def fam_times(self):
        return [_hms(self.X_S)] if self.p["auth"] == "on" else []

    def fam_time(self, ctx, sec):
        if self.p["auth"] == "on" and sec == self.X_S:
            self._cancel(ctx)
            ctx.flatten("time")

    def fam_signal(self, ctx):
        r_end = OPEN + int(self.p["or_min"]) * 60
        end = bar_end(self)
        if end <= r_end or (self.p["auth"] == "on" and end >= self.X_S):
            return
        if self.r is None:
            self.r = self.rng(OPEN, r_end)
            if self.r is None:
                return
        hi, lo = self.r
        c = self.C[-1]
        if self.p["dir"] == "long":
            if c > hi:
                self._mkt(ctx, "long", struct=lo)
        elif c < lo:
            self._mkt(ctx, "short", struct=hi)


# ---- N4 late_mom ----------------------------------------------------------------------------------------------------------
class LateMom(Template):
    """N4 (module docstring). At 15:30 ET: market in the direction of sign(P_signal - prior close), where P_signal = the
    last 1-minute close before the signal time `sig`; only if |move| >= thr %. Flat 15:58 (the day's flatten). One trade.
    shift_seed > 0 = the NULL: the same trade on the same days with a seeded random direction."""
    DEFAULTS = {"sig": "10:00", "thr": 0.0, "tf": "30", "max_tr": 1, "shift_seed": 0}
    SCHEMA = {"sig": ("choice", ("10:00", "12:00", "15:30")), "thr": ("float", 0.0, 10.0), "tf": ("choice", ("30",)),
              "shift_seed": ("int", 0, 1000000)}
    SCREEN_TFS = ("30",)
    FEATURES = ()
    AT_S, FLAT_S = 55800, 57480                     # 15:30 . 15:58 ET

    def fam_sessions(self):
        return {"t": (self.AT_S, self.FLAT_S)}

    def fam_filter(self, ids):
        return ["t"]

    def fam_times(self):
        return [_hms(self.AT_S)]

    def move(self):
        """(P_signal, move in percent) from prior data only, or None."""
        p = self.mc(0, S._sec(self.p["sig"]))       # 1-minute bars that START before the signal time = ended by it
        if p is None or not self.pdc:
            return None
        return p, (p / self.pdc - 1.0) * 100.0

    def fam_time(self, ctx, sec):
        if self.sid != "t" or sec != self.AT_S or not self.can_enter(ctx):
            return
        m = self.move()
        lp = ctx.last_price
        if m is None or lp is None or m[1] == 0 or abs(m[1]) < self.p["thr"]:
            return
        up = m[1] > 0
        if self.p["shift_seed"]:
            up = random.Random("%s|%s|late_mom" % (self.p["shift_seed"], self.day)).random() < 0.5
        self._mkt(ctx, "long" if up else "short", ref=lp)


# ---- N5 open_fade ---------------------------------------------------------------------------------------------------------
class Atr30:
    """Wilder ATR(14) of the 30-minute bars built from 1-minute bars (start_sec, o, h, l, c, v), with the Template's own
    rule: the mean of the true ranges for the first 14 bars, then (atr x 13 + tr) / 14. A 30-minute bar counts once its
    last minute (or a later minute) has been added."""

    def __init__(self):
        self.k = self.pc = self.atr = None
        self.h = self.l = self.c = self.sum = 0.0
        self.n = 0

    def add(self, m):
        k = m[0] // 1800
        if self.k is not None and k != self.k:
            self._close()                           # the bucket's last minute had no print
        if self.k is None:
            self.k, self.h, self.l = k, m[2], m[3]
        else:
            self.h, self.l = max(self.h, m[2]), min(self.l, m[3])
        self.c = m[4]
        if m[0] % 1800 == 1740:
            self._close()

    def _close(self):
        tr = self.h - self.l if self.pc is None else max(self.h - self.l, abs(self.h - self.pc), abs(self.l - self.pc))
        self.n += 1
        self.sum += tr
        self.atr = self.sum / self.n if self.n <= 14 else (self.atr * 13.0 + tr) / 14.0
        self.pc, self.k = self.c, None


class OpenFade(Template):
    """N5 (module docstring). ref = the 09:29 close. After 09:30 a tf bar that trades >= k x ATR30 above ref arms the
    short side (below: the long side); a side is disarmed when price trades back to ref. Armed above and a bar closes
    below the prior bar's low -> market short (toward ref); mirror for long. nyam only, max_tr 3."""
    DEFAULTS = {"k": 1.0, "max_tr": 3, "auth": "off"}
    SCHEMA = {"k": ("float", 0.05, 20.0), "auth": ("choice", ("off", "on"))}
    SCREEN_TFS = ("1", "5")
    FEATURES = ()

    @classmethod
    def author_cells(cls, root, tf):                # target = the ref price, with each of the 8 menu stops
        return [({"auth": "on"}, {**st, "tgt_r": 0.0}) for st in S.menu_stops(root)]

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_day(self, ctx):
        self.a30 = Atr30()
        self.mi = 0
        self.ref = None
        self.ref_set = False
        self.up = self.dn = False                   # armed: price stretched above / below ref
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        M = self.M
        for i in range(self.mi, len(M)):
            self.a30.add(M[i])
        self.mi = len(M)
        if bar_end(self) <= OPEN:
            return
        if not self.ref_set:
            self.ref, self.ref_set = self.mc(0, OPEN), True
        ref, atr = self.ref, self.a30.atr
        if ref is None or atr is None or self.nb < 2:
            return
        d = self.p["k"] * atr
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        if h >= ref + d:
            self.up = True
        if l <= ref - d:
            self.dn = True
        if l <= ref:
            self.up = False                         # back at ref: the overshoot above it is over
        if h >= ref:
            self.dn = False
        if self.up and c < self.L[-2]:
            self.go, self.up = -1, False
        elif self.dn and c > self.H[-2]:
            self.go, self.dn = 1, False

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short", tp_px=self.ref if self.p["auth"] == "on" else None)


# ---- N6 vol_spike_break ---------------------------------------------------------------------------------------------------
class VolSpikeBreak(Template):
    """N6 (module docstring). A tf bar closes beyond the high / low of the 20 bars before it AND its volume is >= m x the
    median volume of those 20 bars -> market in that direction. max_tr 2."""
    DEFAULTS = {"m": 3.0, "max_tr": 2}
    SCHEMA = {"m": ("float", 1.0, 50.0)}
    SCREEN_TFS = TFS
    FEATURES = ()
    N = 20

    def fam_signal(self, ctx):
        n = self.N
        if self.nb < n + 1:
            return
        c = self.C[-1]
        side = "long" if c > max(self.H[-n - 1:-1]) else "short" if c < min(self.L[-n - 1:-1]) else None
        if side is None:
            return
        med = median(self.V[-n - 1:-1])
        if med > 0 and self.V[-1] >= self.p["m"] * med:
            self._mkt(ctx, side)


# ---- N7 straddle_tight ----------------------------------------------------------------------------------------------------
TIGHT_TIMES = ("08:30", "09:30", "10:00")           # EDGE_SPEC N7 clock times, ET
TIGHT_OFFS = ("A", "B", "C")


class StraddleTight(l2ref.StraddleT):
    """N7 (module docstring): the engine's clock straddle (l2ref.StraddleT: OCO stop entries around the last print, the
    time-shuffle null through shift_seed) placed 1 second before the clock time, entry offset `off` = A / B / C points
    of the root (OFF), unfilled legs cancelled 5 minutes later, its own exit cells (unit_exits: STOP points x TGT)."""
    OFF = {"NQ": (3.0, 5.0, 8.0), "ES": (0.75, 1.25, 2.0), "GC": (0.6, 1.0, 1.6)}
    STOP = {"NQ": (5.0, 8.0, 10.0), "ES": (1.25, 2.0, 2.5), "GC": (1.0, 1.6, 2.0)}       # NQ / 4 . NQ / 5, as the offsets
    TGT = (1.0, 2.0, 3.0)
    DEFAULTS = {"off": "B", "off_mode": "menu", "cancel_min": 5}
    SCHEMA = {"off": ("choice", ("",) + TIGHT_OFFS), "off_mode": ("choice", ("menu", "atr", "pts"))}

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._menu = self.p["off"]
        if (self.p["off_mode"] == "menu") != bool(self._menu):
            raise ValueError("straddle_tight: either off = A / B / C (off_mode 'menu') or off = '' with off_mode atr / pts + off_val")

    @classmethod
    def unit_exits(cls, root):
        return [{"stop_mode": "pts", "stop_val": s, "tgt_r": r} for s in cls.STOP[root] for r in cls.TGT]

    def on_session(self, ctx):
        if self._menu:
            self.p["off_mode"], self.p["off_val"] = "pts", self.OFF[ctx.root][TIGHT_OFFS.index(self._menu)]
        super().on_session(ctx)


def _tight_entry(t: str) -> tuple:
    at = _hms(S.clock_sec(t) - 1)                   # armed 1 s before the clock time
    flat = S.clock_flat(t)                          # entries only until the next listed time / the session end
    return (StraddleTight, {"at": at, "flat": flat}, True,
            f"N7 straddle_tight {t} ET: OCO stop entries at last price +/- off points (A / B / C: NQ 3 / 5 / 8, ES 0.75 / 1.25 / 2, "
            f"GC 0.6 / 1 / 1.6), placed at {at}, unfilled legs cancelled 5 min later, entries until {flat[:5]}; own exits: stop "
            "NQ 5 / 8 / 10 pts (ES 1.25 / 2 / 2.5, GC 1 / 1.6 / 2) x target 1:1 / 1:2 / 1:3; null = the same bracket at random "
            "minutes (shift_seed). Second chance of the old NQ 09:30 straddle. CARD: the bracket is live within a second of the "
            "event -> the 2 ticks + 250 ms stress is the real gate"
            + ("; a fill in the last second before 09:30 is tagged session pre: judge over session 'all'" if t == "09:30" else ""),
            {"rationale": "The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small "
                          f"stop ({t} ET).",
             "complexity": 6,                       # bracket at the time . cancel after 5 min . flat by 15:58 + time, offset, stop
             "variants": [{"off": k} for k in TIGHT_OFFS]})


FAMILIES = {
    # complexity 9 = VWAP(09:30) + 3 state conditions + trigger + entry window + max 4 a day + stop after 2 losses + X
    "vwap_trend_pull": (VwapTrendPull, {}, False,
                        "N1 vwap_trend_pull: close above a rising 09:30 VWAP and up >= X % over 60 min, first down bar -> "
                        "market long (mirror short); entries 10:30-15:30 ET, max 4 trades and stop after 2 losing trades per "
                        "session instance. Author cell (information only): stop 80 pts, target 40 long / 50 short, NQ tf 15",
                        {"rationale": "When price holds above a rising session VWAP, the day's buyers are in profit and dips get "
                                      "bought; the first candle against the trend gives a better price in the direction of the "
                                      "day's flow.",
                         "complexity": 9,
                         "variants": [{"x": 0.05}, {"x": 0.10}, {"x": 0.20}]}),
    # complexity 5 = value area definition + poke by >= D + close back inside + one trade per side + D
    "va_reclaim": (VaReclaim, {}, False,
                   "N2 va_reclaim: price trades below yesterday's VAL (70 % value area of the 09:30-16:00 volume by price) by "
                   ">= d_atr x ATR14, then a bar closes back above VAL -> market long (mirror short at VAH); one trade per side "
                   "per session instance; no trade on a contract-roll day",
                   {"rationale": "A poke outside yesterday's value area that fails traps the late side; they exit and price "
                                 "returns into value.",
                    "complexity": 5,
                    "variants": [{"d_atr": 0.0}, {"d_atr": 0.25}, {"d_atr": 0.5}]}),
    # complexity 5 = range definition + close beyond it -> market + one direction, one trade + or_min + dir
    "orb_confirm": (OrbConfirm, {}, False,
                    "N3 orb_confirm: range = the first or_min minutes from 09:30; a bar closes above it -> market long (dir "
                    "long) / below it -> market short (dir short); LONG-ONLY and SHORT-ONLY are separate MIRROR units; one "
                    "trade per session instance. Author cell (information only): stop at the other side of the range, flat 15:30",
                    {"rationale": "The opening range is the first balance; a bar CLOSE outside it shows acceptance, and one "
                                  "direction per day never holds opposite positions (Apex rule).",
                     "complexity": 5,
                     "variants": [{"or_min": m, "dir": d} for m in ("15", "30", "60") for d in ("long", "short")]}),
    # complexity 5 = signal sign(P_signal - prior close) + entry 15:30 / flat 15:58 + size filter + signal time + threshold
    "late_mom": (LateMom, {}, False,
                 "N4 late_mom: at 15:30 ET market in the direction of sign(P_signal - prior close), P_signal = the last 1-minute "
                 "close before sig (10:00 / 12:00 / 15:30), only if |move| >= thr %; flat 15:58; one trade a day; no trade on a "
                 "contract-roll day or an equity half day; null (shift_seed) = the same trade with a random direction",
                 {"rationale": "The day's early move predicts the last half hour (hedgers and late traders push the same way into "
                               "the close; documented in the academic literature).",
                  "complexity": 5,
                  "variants": [{"sig": s, "thr": t} for s in ("10:00", "12:00", "15:30") for t in (0.0, 0.25, 0.5)]}),
    # complexity 5 = ref definition + stretch >= K x ATR30 + stall bar -> fade + window / max 3 + K
    "open_fade": (OpenFade, {}, False,
                  "N5 open_fade: ref = the 09:29 close; once price is >= k x ATR30 away from ref and a bar closes back toward ref "
                  "beyond the prior bar's opposite extreme -> market toward ref; 09:30-11:00 (nyam), max 3 trades. Author cell "
                  "(information only): target = the ref price",
                  {"rationale": "The first burst after the open often overshoots while opening orders clear; when it stalls, "
                                "price reverts toward the pre-open price.",
                   "complexity": 5,
                   "variants": [{"k": 0.5}, {"k": 1.0}, {"k": 1.5}]}),
    # complexity 4 = volume condition + 20-bar break -> market + max 2 a day + M
    "vol_spike_break": (VolSpikeBreak, {}, False,
                        "N6 vol_spike_break: a bar closes beyond the high / low of the 20 bars before it with volume >= m x "
                        "their median volume -> market in that direction; max 2 trades per session instance",
                        {"rationale": "A break of the recent range on unusually high volume has real participation behind it; "
                                      "breaks on normal volume are more often noise.",
                         "complexity": 4,
                         "variants": [{"m": 2.0}, {"m": 3.0}, {"m": 4.0}]}),
}
FAMILIES.update({f"straddle_tight_{t.replace(':', '')}": _tight_entry(t) for t in TIGHT_TIMES})

# entry windows, ET seconds after 00:00 of the trade date [first, last]: the smoke's "entries outside the window" count
ENTRY_WINDOWS = {"vwap_trend_pull": (VwapTrendPull.T0, VwapTrendPull.T1 + 59), "late_mom": (LateMom.AT_S, LateMom.AT_S + 59),
                 "open_fade": (OPEN, 39600 - 1), "orb_confirm": (OPEN + 15 * 60, 57480 - 1),
                 **{f"straddle_tight_{t.replace(':', '')}": (S.clock_sec(t) - 1, S.clock_sec(t) + 299) for t in TIGHT_TIMES}}
