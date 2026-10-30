"""fvg_lab -- ONE PARAMETRIC FAIR VALUE GAP FAMILY for the owner's "100 FVG ideas" batch (2026-10-28), NQ, 1 contract, hold_to = 'day'
(flat 15:58 ET). Every idea of the batch is one setting combination of this family; the exits are the fixed-point cells of hm60 only
(the owner: "only use set sl and tp"). Written from the ideas before any result. Tests: engine/tests/test_fvg_lab.py.

THE GAP (fvg's): three tf bars, bar 1 the oldest. UP: bar 3's low above bar 1's high (near = bar 3's low, far = bar 1's high); DOWN the
mirror. Read at bar 3's close, on completed bars; all three bars start at or after `start`; size >= max(min_gap x ATR14 of the tf, a
tick). A tf close through the far edge kills the gap (inversion); trig 'ifvg' then trades the retest the other way.
ENTRIES only between `start` and `end`; ONE instance (window start .. 15:58); one position at a time; max_tr a day.

SETTINGS (each default = off / the plain fvg rule):
  mode   touch (limit at near edge) | mid (limit at the middle) | go (market at bar 3's close) | rej (a later tf bar wicks to the near edge
         and CLOSES back outside it: market at that close) | sec (the second distinct tap closes outside: market)
  side   the day's bias; a gap trades only WITH it (fade 1: only AGAINST it):
         both | open (price vs the 09:30 open) | pdc (vs prior close) | vwap (vs the 09:30-anchored VWAP) | pdmid (vs prior-day mid) |
         ema (slope of the tf EMA50) | onb (overnight high / low taken since 09:30) | gap (09:30 open vs prior close) | fc (first 5-minute
         candle) | ycol (prior day close vs the day before) | sma (prior close vs its 20-day mean) | ohr (break of the 09:30-10:30 range) |
         drive (09:30-10:00 move >= dk x daily ATR) | htf (newest live 1h gap) | dfvg (nearest unfilled daily gap pulls)
  pd     off | day (longs below the RTH range mid, shorts above) | prev (same vs the prior-day mid)
  q      gap quality: off | big (bar 2 range >= 2 ATR) | body (bar 2 body >= 70 % of range) | clean (bar 2 does not trade back into bar 1) |
         vol (bar 2 volume >= 1.5 x its 20-bar mean) | wick1 (bar 1 has a >= 50 % wick against the gap) | b3 (bar 3 closes beyond bar 2) |
         round (a multiple of 50 inside the zone) | newterr (zone outside the prior-day range) | cons (6 quiet bars before bar 1)
  conf   zone confluence: off | ema50 | vwap | vband (near edge inside VWAP +- 1 sd) | pdlvl | orlvl | onlvl | rsi (long < 35, short > 65)
  nest   1: the gap sits inside a live 1h gap of the same side
  stack  1: an earlier live gap of the same side exists
  pick   newest | first | second | big (only the largest so far)
  age    0 or the most tf bars a resting order / a tap may be old; agemin: at least that old (stale gaps)
  trig   gap | ifvg | sweep (a swept level sets the bias, lvl pdhl | onhl | f15) | fill (market AGAINST the thrust at bar 3's close)
  regime off | fills3 (3+ gaps already inverted today: fade instead of follow) ; vol off | hi (5-day range above its 60-day median)
NO LOOK-AHEAD: gaps and biases read completed bars only; the 09:30 open, first candle, OR and 10:00 drive are read only after they ended."""
from __future__ import annotations

import math
import statistics

from l2sim import Template

HM = lambda s: int(s[:2]) * 3600 + int(s[3:]) * 60          # noqa: E731
OPEN, LAST, END_S = 34200, 54000, 57480                     # 09:30, 15:00, 15:58 ET
STARTS = ("00:00", "03:00", "08:30", "09:30", "09:35", "10:00", "11:30", "13:30", "15:00")
ENDS = ("05:00", "10:30", "11:30", "13:00", "15:00", "15:50")
MODES = ("touch", "mid", "go", "rej", "sec")
SIDES = ("both", "open", "pdc", "vwap", "pdmid", "ema", "onb", "gap", "fc", "ycol", "sma", "ohr", "drive", "htf", "dfvg", "ovw", "act")
QS = ("off", "big", "body", "clean", "vol", "wick1", "b3", "round", "newterr", "cons")
CONFS = ("off", "ema50", "vwap", "vband", "pdlvl", "orlvl", "onlvl", "rsi")


class FvgLab(Template):
    """fvg_lab (module docstring)."""
    DEFAULTS = {"min_gap": 0.1, "mode": "touch", "side": "both", "fade": 0, "pd": "off", "q": "off", "conf": "off", "nest": 0, "stack": 0,
                "pick": "newest", "age": 0, "agemin": 0, "trig": "gap", "lvl": "pdhl", "regime": "off", "vol": "off", "dk": 0.1,
                "start": "09:30", "end": "15:00", "max_tr": 3}
    SCHEMA = {"min_gap": ("float", 0.0, 10.0), "mode": ("choice", MODES), "side": ("choice", SIDES), "fade": ("int", 0, 1),
              "pd": ("choice", ("off", "day", "prev")), "q": ("choice", QS), "conf": ("choice", CONFS), "nest": ("int", 0, 1),
              "stack": ("int", 0, 1), "pick": ("choice", ("newest", "first", "second", "big")), "age": ("int", 0, 200),
              "agemin": ("int", 0, 200), "trig": ("choice", ("gap", "ifvg", "sweep", "fill")), "lvl": ("choice", ("pdhl", "onhl", "f15")),
              "regime": ("choice", ("off", "fills3")), "vol": ("choice", ("off", "hi")), "dk": ("float", 0.0, 2.0),
              "start": ("choice", STARTS), "end": ("choice", ENDS), "max_tr": ("int", 1, 20)}
    SCREEN_TFS = ("1", "5", "15")
    SCREEN_RUN = {"strict_limit": True}
    ONE_INSTANCE_PASSES = ("nyam", "mid", "pm")
    FEATURES = ()

    def _onr(self):
        """Overnight (00:00-09:30) high, low: the bars arrive as the day runs, so it is read when used, once the open has passed."""
        r = self.rng(0, OPEN) if self.M and self.M[-1][0] + 60 >= OPEN else None
        return r if r else (None, None)

    def fam_sessions(self):
        need_on = self.p["side"] == "onb" or self.p["conf"] == "onlvl" or (self.p["trig"] == "sweep" and self.p["lvl"] == "onhl")
        return {"t": (0 if need_on else min(HM(self.p["start"]), OPEN), END_S)}

    def fam_filter(self, ids):
        return ["t"] if "nyam" in ids else []

    def fam_day(self, ctx):
        self.gaps, self.qual, self.fills, self.gap, self.hb, self.sw, self.ordg, self.sw_nb = [], 0, 0, None, [], 0, None, 0
        self.fc_done = self.volok = self.dmag = None
        self.volok = self._vol_ok()
        self.dmag = self._daily_pull()

    # ---------------------------------------------------------------- daily context (prior days only)
    def _vol_ok(self):
        if self.p["vol"] == "off":
            return True
        r = [d["h"] - d["l"] for d in self.dl[-66:]]
        if len(r) < 66:
            return False
        m5 = [sum(r[i - 5:i]) / 5.0 for i in range(5, len(r) + 1)]
        return m5[-1] >= statistics.median(m5[-60:])

    def _daily_pull(self):
        """Direction (+1 / -1) of the nearest unfilled daily gap among the last 40 days, or None."""
        dl = self.dl[-40:]
        best = None
        for i in range(2, len(dl)):
            if dl[i]["l"] > dl[i - 2]["h"]:
                lo, hi = dl[i - 2]["h"], dl[i]["l"]
            elif dl[i]["h"] < dl[i - 2]["l"]:
                lo, hi = dl[i]["h"], dl[i - 2]["l"]
            else:
                continue
            if any(dl[j]["l"] <= hi and dl[j]["h"] >= lo for j in range(i + 1, len(dl))):
                continue                                                    # touched since: filled
            if self.pdc is None:
                return None
            d = abs((lo + hi) / 2.0 - self.pdc)
            if best is None or d < best[0]:
                best = (d, 1 if (lo + hi) / 2.0 > self.pdc else -1)
        return best[1] if best else None

    # ---------------------------------------------------------------- the day's bias
    def _vwap_now(self):
        xs = [m for m in self.M if m[0] >= OPEN and m[5] > 0]
        v = sum(m[5] for m in xs)
        if v <= 0:
            return None
        tp = [(m[2] + m[3] + m[4]) / 3.0 for m in xs]
        mean = sum(t * m[5] for t, m in zip(tp, xs)) / v
        sd = math.sqrt(max(sum(t * t * m[5] for t, m in zip(tp, xs)) / v - mean * mean, 0.0))
        return mean, sd

    def _bias_of(self, side, now):
        p = self.p
        self.p = {**p, "side": side}
        try:
            return self._bias(now)
        finally:
            self.p = p

    def _bias(self, now):
        """+1 / -1 = the allowed side, 0 = no trade, None = both sides."""
        s, c = self.p["side"], self.C[-1]
        sgn = lambda x: (x > 0) - (x < 0)           # noqa: E731
        if s == "both":
            return None
        if s == "open":
            o = self.mo(OPEN)
            return sgn(c - o) if o is not None and now > OPEN else 0
        if s == "pdc":
            return sgn(c - self.pdc) if self.pdc is not None else 0
        if s == "pdmid":
            return sgn(c - (self.pdh + self.pdl) / 2.0) if self.pdh is not None else 0
        if s == "vwap":
            w = self._vwap_now()
            return sgn(c - w[0]) if w else 0
        if s == "ema":
            e, ep = self.E[50], self.Ep[50]
            return sgn(e - ep) if ep is not None else 0
        if s == "onb":
            if self._onr()[0] is None or now <= OPEN:
                return 0
            hi = max((m[2] for m in self.M if m[0] >= OPEN), default=None)
            lo = min((m[3] for m in self.M if m[0] >= OPEN), default=None)
            up, dn = hi is not None and hi > self._onr()[0], lo is not None and lo < self._onr()[1]
            return 1 if up and not dn else -1 if dn and not up else 0
        if s == "gap":
            o = self.mo(OPEN)
            return sgn(o - self.pdc) if o is not None and self.pdc is not None and now > OPEN else 0
        if s == "fc":
            if now < OPEN + 300:
                return 0
            o, k = self.mo(OPEN), self.mc(OPEN, OPEN + 300)
            return sgn(k - o) if o is not None and k is not None else 0
        if s == "ycol":
            return sgn(self.dl[-1]["c"] - self.dl[-2]["c"]) if len(self.dl) > 1 and self.pdc is not None else 0
        if s == "sma":
            return sgn(self.pdc - sum(d["c"] for d in self.dl[-20:]) / 20.0) if len(self.dl) >= 20 and self.pdc is not None else 0
        if s == "ohr":
            r = self.rng(OPEN, OPEN + 3600)
            return sgn(c - r[0]) if r and now > OPEN + 3600 and c > r[0] else sgn(c - r[1]) if r and now > OPEN + 3600 and c < r[1] else 0
        if s == "drive":
            o, k, a = self.mo(OPEN), self.mc(OPEN, OPEN + 1800), self.datr()
            if o is None or k is None or a is None or now < OPEN + 1800:
                return 0
            return sgn(k - o) if abs(k - o) >= self.p["dk"] * a else 0
        if s == "ovw":                                       # the 09:30 open and VWAP agree
            a, b = self._bias_of("open", now), self._bias_of("vwap", now)
            return a if a == b else 0
        if s == "act":                                       # a live opening half hour: range >= dk x daily ATR, both sides
            r, a = self.rng(OPEN, OPEN + 1800), self.datr()
            return None if r and a is not None and now >= OPEN + 1800 and r[0] - r[1] >= self.p["dk"] * a else 0
        if s == "htf":
            g = next((g for g in reversed(self.hb) if not g["dead"]), None)
            return g["side"] if g else 0
        return self.dmag or 0                                             # dfvg

    def _sweep(self, now):
        """trig 'sweep': the first close back inside a level that the bar's range had taken sets the bias (+1 after a low, -1 after a high)."""
        if self.sw or now <= OPEN + 300:
            return
        lv = self.p["lvl"]
        if lv == "pdhl":
            hi, lo = self.pdh, self.pdl
        elif lv == "onhl":
            hi, lo = self._onr()[0], self._onr()[1]
        else:
            r = self.rng(OPEN, OPEN + 900)
            hi, lo = (r if r and now > OPEN + 900 else (None, None))
        if hi is None or lo is None:
            return
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        if h > hi and c < hi:
            self.sw, self.sw_nb = -1, self.nb
        elif l < lo and c > lo:
            self.sw, self.sw_nb = 1, self.nb

    # ---------------------------------------------------------------- gap tests
    def _q_ok(self, g, o, h, l, c, v, atr):
        q, up = self.p["q"], g["side"] > 0
        o1, h1, l1, c1 = o[0], h[0], l[0], c[0]
        o2, h2, l2, c2 = o[1], h[1], l[1], c[1]
        if q == "off":
            return True
        if q == "big":
            return h2 - l2 >= 2.0 * atr
        if q == "body":
            return h2 > l2 and abs(c2 - o2) >= 0.7 * (h2 - l2)
        if q == "clean":
            return l2 >= h1 if up else h2 <= l1
        if q == "vol":
            base = self.V[-22:-2]
            return len(base) >= 5 and v[1] >= 1.5 * (sum(base) / len(base))
        if q == "wick1":
            rg = h1 - l1
            return rg > 0 and ((min(o1, c1) - l1 if up else h1 - max(o1, c1)) >= 0.5 * rg)
        if q == "b3":
            return c[2] > h2 if up else c[2] < l2
        if q == "round":
            lo, hi = min(g["near"], g["far"]), max(g["near"], g["far"])
            return math.floor(hi / 50.0) * 50.0 >= lo
        if q == "newterr":
            if self.pdh is None:
                return False
            lo, hi = min(g["near"], g["far"]), max(g["near"], g["far"])
            return lo > self.pdh or hi < self.pdl
        if q == "cons":
            hs, ls = self.H[-9:-3], self.L[-9:-3]
            return len(hs) == 6 and max(hs) - min(ls) <= 2.5 * atr
        return True

    def _conf_ok(self, g, atr):
        cf = self.p["conf"]
        if cf == "off":
            return True
        lo, hi = min(g["near"], g["far"]) - 0.25 * atr, max(g["near"], g["far"]) + 0.25 * atr
        inz = lambda x: x is not None and lo <= x <= hi        # noqa: E731
        if cf == "ema50":
            return inz(self.E[50])
        if cf in ("vwap", "vband"):
            w = self._vwap_now()
            if not w:
                return False
            return inz(w[0]) if cf == "vwap" else abs(g["near"] - w[0]) <= w[1]
        if cf == "pdlvl":
            return inz(self.pdh) or inz(self.pdl)
        if cf == "orlvl":
            r = self.rng(OPEN, OPEN + 1800)
            return bool(r) and (inz(r[0]) or inz(r[1]))
        if cf == "onlvl":
            return inz(self._onr()[0]) or inz(self._onr()[1])
        d = [b - a for a, b in zip(self.C[-15:], self.C[-14:])]               # rsi
        if len(d) < 14:
            return False
        up, dn = sum(x for x in d if x > 0), -sum(x for x in d if x < 0)
        rsi = 100.0 if dn == 0 else 100.0 - 100.0 / (1.0 + up / dn)
        return rsi < 35 if g["side"] > 0 else rsi > 65

    def _pd_ok(self, side, now):
        pd = self.p["pd"]
        if pd == "off":
            return True
        if pd == "prev":
            if self.pdh is None:
                return False
            return (self.C[-1] < (self.pdh + self.pdl) / 2.0) == (side > 0)
        r = self.rng(OPEN, now)
        return bool(r) and ((self.C[-1] < (r[0] + r[1]) / 2.0) == (side > 0))

    def _hour(self, now):
        """The 1h gaps (module docstring: nest, htf): rebuilt when an hour closes."""
        if now % 3600 or len(self.M) < 180:
            return
        hrs = {}
        for m in self.M:
            b = hrs.setdefault(m[0] // 3600, [m[2], m[3], m[4]])
            b[0], b[1], b[2] = max(b[0], m[2]), min(b[1], m[3]), m[4]
        ks = sorted(hrs)
        gaps = []
        for i in range(2, len(ks)):
            h1, l1 = hrs[ks[i - 2]][0], hrs[ks[i - 2]][1]
            h3, l3 = hrs[ks[i]][0], hrs[ks[i]][1]
            if l3 > h1:
                gaps.append({"side": 1, "near": l3, "far": h1, "dead": False, "k": ks[i]})
            elif h3 < l1:
                gaps.append({"side": -1, "near": h3, "far": l1, "dead": False, "k": ks[i]})
        c = hrs[ks[-1]][2]
        for g in gaps:
            g["dead"] = (g["side"] > 0 and c < g["far"]) or (g["side"] < 0 and c > g["far"])
        self.hb = gaps

    # ---------------------------------------------------------------- the close
    def fam_update(self, ctx):
        self.gap = None
        p = self.p
        step = self.tf * 60
        now = (self.M[-1][0] // step + 1) * step                       # the clock close of this tf bar
        start, end = HM(p["start"]), HM(p["end"])
        if now > end:
            if self.orders and ctx.flat:
                self._cancel(ctx)
            return
        if self.sid is None or len(self.H) < 3:
            return
        self._sync(ctx)
        if p["nest"] or p["side"] == "htf":
            self._hour(now)
        c, atr = self.C[-1], self.atr
        for g in self.gaps:                                             # inversion kills a gap (and may trade its retest)
            if not g["dead"] and ((g["side"] > 0 and c < g["far"]) or (g["side"] < 0 and c > g["far"])):
                g["dead"] = True
                self.fills += 1
                if p["trig"] == "ifvg" and g["ok"] and now - start >= 0:
                    self.gaps.append({"side": -g["side"], "near": g["far"], "far": g["near"], "dead": False, "ok": True, "used": False,
                                      "born": self.nb, "size": g["size"], "taps": 0, "prev": False, "inv": True, "struct": None})
                    break
        if self.ordg is not None and self.ordg["dead"] and self.orders and ctx.flat:
            self._cancel(ctx)
        if p["trig"] == "sweep":
            self._sweep(now)
        if now - 3 * step >= start and atr is not None:                 # a new gap at this close
            o, h, l, cl, v = self.O[-3:], self.H[-3:], self.L[-3:], self.C[-3:], self.V[-3:]
            up, dn = l[2] > h[0], h[2] < l[0]
            if up or dn:
                near, far = (l[2], h[0]) if up else (h[2], l[0])
                if abs(near - far) >= max(p["min_gap"] * atr, ctx.tick):
                    g = {"side": 1 if up else -1, "near": near, "far": far, "dead": False, "used": False, "born": self.nb,
                         "size": abs(near - far), "taps": 0, "prev": any((not x["dead"]) and x["side"] == (1 if up else -1) for x in self.gaps),
                         "inv": False, "struct": l[1] if up else h[1]}
                    g["ok"] = self._qualifies(g, o, h, l, cl, v, atr, now)
                    self.gaps.append(g)
        self._pick(ctx, now, atr)

    def _qualifies(self, g, o, h, l, cl, v, atr, now):
        p = self.p
        if not self.volok or not self._q_ok(g, o, h, l, cl, v, atr) or not self._conf_ok(g, atr) or not self._pd_ok(g["side"], now):
            return False
        if p["stack"] and not g["prev"]:
            return False
        if p["nest"] and not any((not x["dead"]) and x["side"] == g["side"] and min(x["near"], x["far"]) <= max(g["near"], g["far"])
                                 and max(x["near"], x["far"]) >= min(g["near"], g["far"]) for x in self.hb):
            return False
        n = self.qual
        pk = p["pick"]
        okp = pk == "newest" or (pk == "first" and n == 0) or (pk == "second" and n == 1) \
            or (pk == "big" and all(g["size"] >= x["size"] for x in self.gaps if x["ok"]))
        self.qual += 1
        return okp

    def _side_ok(self, side, now):
        p = self.p
        if p["trig"] == "sweep":
            b = self.sw or 0
        else:
            b = self._bias(now)
        if b is None:
            return True
        if b == 0:
            return False
        return (side == b) != bool(p["fade"])

    def _pick(self, ctx, now, atr):
        p, mode = self.p, self.p["mode"]
        c, h, l = self.C[-1], self.H[-1], self.L[-1]
        fade_all = p["trig"] == "fill" or (p["regime"] == "fills3" and self.fills >= 3)
        cand = None
        for g in self.gaps:
            if g["dead"] or g["used"] or not g["ok"] or (p["trig"] == "ifvg" and not g["inv"]):
                continue
            if p["trig"] == "sweep" and (not self.sw or g["born"] < self.sw_nb):
                continue                                                # only gaps formed after the sweep
            age = self.nb - g["born"]
            if (p["age"] and age > p["age"]) or age < p["agemin"]:
                continue
            fresh = age == 0
            side = g["side"]
            if fade_all:
                if not fresh or not self._side_ok(-side, now):
                    continue
                cand = (g, -side, c, "mkt")
                continue
            if not self._side_ok(side, now):
                continue
            near, far = g["near"], g["far"]
            if g["inv"]:
                if fresh:
                    cand = (g, side, g["near"], "lim")
                continue
            if mode in ("touch", "mid", "go"):
                if fresh:
                    cand = (g, side, c if mode == "go" else near if mode == "touch" else (near + far) / 2.0, "mkt" if mode == "go" else "lim")
                continue
            tapped = (l <= near) if side > 0 else (h >= near)
            if mode == "rej" and tapped and not fresh and ((c > near) if side > 0 else (c < near)):
                cand = (g, side, c, "mkt")
            elif mode == "sec" and tapped and not fresh:
                prev_tapped = g.get("pt", False)
                g["pt"] = True
                if not prev_tapped:
                    g["taps"] += 1
                if g["taps"] == 2 and ((c > near) if side > 0 else (c < near)):
                    cand = (g, side, c, "mkt")
            elif mode == "sec":
                g["pt"] = False
        if cand is None:
            return
        g, side, px, kind = cand
        g["used"] = True
        if ctx.flat and self.orders:
            self._cancel(ctx)
        self.ordg = g
        self.gap = ("long" if side > 0 else "short", px, kind, g["struct"] if side == g["side"] else None)

    def fam_signal(self, ctx):
        if self.gap is None:
            return
        side, px, kind, struct = self.gap
        if kind == "mkt":
            self._mkt(ctx, side, struct=struct)
        else:
            self._lim(ctx, side, px, struct=struct, ttl=self.p["age"] or None)


ENTRY_WINDOWS = {"fvg_lab": (0, HM("15:50") + 59)}

FAMILIES = {
    "fvg_lab": (FvgLab, {}, False,
                "fvg_lab: one parametric fair value gap family (module docstring): the gap, a side bias, quality / confluence filters, "
                "limit or market entries, flat 15:58; the batch's exits are the fixed-point cells only",
                {"rationale": "A fair value gap is the footprint of one-sided urgency: orders that wanted in during the move were left "
                              "unfilled, so the return to it meets that waiting interest and the traders who faded the move pay.",
                 "complexity": 6,
                 "variants": [{"min_gap": 0.1}, {"min_gap": 0.25}, {"min_gap": 0.5}]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as fvg_odir.py does). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
