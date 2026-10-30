"""eve_rules -- THE ASIA / EVENING (18:00-23:55 ET) RULES OF THE 2026-10-29 LIST that no earlier family builds (ideas-100-asia-evening, A-D).

ONE family, `eve_rule`, one rule per run (`rule`), written from the idea text before any result. Home session eve only; the card's w_flat ends the night.
`mode` follow takes the rule's side, fade the opposite. dow: the trade-date weekdays that may trade ("" = all, "0" = Monday = SUNDAY NIGHT).
rg quiet / wide (+ rq): the prior daily bar's range is under / over rq x the mean range of the 10 days before it; else no trade that night.
Daily bars (`self.dl`) are Globex days ending 17:00 ET (no RTH split): every "RTH" level below is that whole Globex day -- a PROXY, said here.

  TIME RULES (decided at 18:00 + off_min on the last print; one trade a night)
    loc10       the prior day closed in its top q (long) / bottom q (short) of its range              (ideas 15-17)
    newext      which hi: the prior day made an n_d-day high -> long; lo: an n_d-day low -> long (the bounce)   (23, 24)
    first_move  the return from the 18:00 open to the last print sets the side (wide-day fade: rg wide, mode fade)   (22)
    wkgap       last print vs the prior daily close, |gap| >= k x daily ATR -> follow it (fade: back to the close)   (12)
    above_both  last print above both the 18:00 open and the eve VWAP -> long, below both -> short                     (33)
  BAR RULES (decided at a tf close)
    brk_win     first close beyond the [r_start, r_end) range (follow: stop at the other edge)                          (21 with rg quiet)
    lvl_touch   first touch of the prior day's high / low coming from inside: follow it, fade it                        (27, 28)
    away_lim    a close >= k x daily ATR from the anchor (pdc: prior daily close, o18: the 18:00 open) -> a limit AT the anchor, ttl bars   (26, 31)
    sweep       a bar in (r_end, s_end] trades through the [r_start, r_end) high / low and closes back inside -> fade   (4, 40)
    c18         the 18:00 candle with range >= k x daily ATR: ent fade = against it at its close; ent mid = limit at its 50 % with it   (37, 38)
    gap_disagree the 18:00 open vs the prior daily close and the 18:00 candle point opposite ways -> trade the candle  (36)
    cross_open  the first close back across the 18:00 open after r_end                                                  (39)
    fvg         the newest fair value gap on the 18:00-open side, limit at its near edge, stop = the middle candle's far end   (41-43)
    pcb         a close beyond the previous bar's high / low on the 18:00-open side, stop = its other end; nr > 0: that bar's range < nr x ATR  (44, 45)
    outside     a bar that engulfs the previous bar's range: follow its close                                          (46)
    pin         a wick >= `wick` of the range at the evening's high / low -> the other way                              (48)
    ob          a body >= k x ATR displacement: limit at the open of the last opposite candle before it                (49)
    streak      nbars same-colour bars: follow / fade                                                                   (50, 51)
    doji        a doji (body <= dj x range) at the evening's high / low -> OCO stops beyond it, ttl bars               (52)
Registration as eve_gap_follow.py: join_blocks(). Tests: engine/tests/test_eve_rules.py."""
from __future__ import annotations

import datetime as dt

from l2sim import Template, _hms, clock_sec

from .flex import _bar_end

E0 = clock_sec("18:00")                                 # -21600
RULES = ("loc10", "newext", "first_move", "wkgap", "above_both", "brk_win", "lvl_touch", "away_lim", "sweep", "c18", "gap_disagree",
         "cross_open", "fvg", "pcb", "outside", "pin", "ob", "streak", "doji")
TIME_RULES = ("loc10", "newext", "first_move", "wkgap", "above_both")


class EveRule(Template):
    DEFAULTS = {"rule": "loc10", "mode": "follow", "dow": "", "rg": "", "rq": 1.0, "off_min": 30, "q": 0.9, "n_d": 20, "which": "hi", "k": 0.1,
                "r_start": "18:00", "r_end": "19:00", "s_end": "20:00", "anchor": "pdc", "ttl": 12, "nbars": 3, "wick": 0.6, "dj": 0.1,
                "nr": 0.0, "min_gap": 0.0, "ent": "fade", "max_tr": 1}
    SCHEMA = {"rule": ("choice", RULES), "mode": ("choice", ("follow", "fade")), "dow": ("str",), "rg": ("choice", ("", "quiet", "wide")),
              "rq": ("float", 0, 10), "off_min": ("int", 0, 300), "q": ("float", 0.5, 1), "n_d": ("int", 2, 300), "which": ("choice", ("hi", "lo")),
              "k": ("float", 0, 10), "r_start": ("str",), "r_end": ("str",), "s_end": ("str",), "anchor": ("choice", ("pdc", "o18")),
              "ttl": ("int", 1, 100), "nbars": ("int", 2, 10), "wick": ("float", 0, 1), "dj": ("float", 0, 1), "nr": ("float", 0, 10),
              "min_gap": ("float", 0, 10), "ent": ("choice", ("fade", "mid"))}
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()
    WARM = 1

    def fam_filter(self, ids):
        return [s for s in ids if s == "eve"]

    def fam_times(self):
        return [_hms(self._at())] if self.p["rule"] in TIME_RULES and self.sessions() else []

    def _at(self) -> int:
        return E0 + int(self.p["off_min"]) * 60

    def fam_day(self, ctx):
        self.used, self.r, self.touched, self.placed, self.last, self.want, self.seen = False, None, set(), False, {}, None, 0

    def _ok(self) -> bool:
        p, dl = self.p, self.dl
        if p["dow"] and str(dt.date.fromisoformat(self.day).weekday()) not in p["dow"]:
            return False
        if p["rg"]:
            if len(dl) < 11:
                return False
            m = sum(x["h"] - x["l"] for x in dl[-11:-1]) / 10.0
            r = dl[-1]["h"] - dl[-1]["l"]
            return m > 0 and (r < float(p["rq"]) * m if p["rg"] == "quiet" else r >= float(p["rq"]) * m)
        return True

    def _side(self, d):
        return "long" if (d > 0) == (self.p["mode"] == "follow") else "short"

    # ---- time rules ------------------------------------------------------------------------------------------------------------------
    def fam_time(self, ctx, sec):
        r = self.p["rule"]
        lp = ctx.last_price
        if r not in TIME_RULES or sec != self._at() or self.sid != "eve" or lp is None or not self.dl or not self._ok() or not self.can_enter(ctx):
            return
        p, dl, d1 = self.p, self.dl, self.dl[-1]
        d = 0.0
        if r == "loc10":
            rg = d1["h"] - d1["l"]
            pos = (d1["c"] - d1["l"]) / rg if rg > 0 else 0.5
            d = 1 if pos >= float(p["q"]) else -1 if pos <= 1 - float(p["q"]) else 0
        elif r == "newext":
            lb = dl[-int(p["n_d"]):]
            if len(lb) == int(p["n_d"]):
                hit = d1["h"] >= max(x["h"] for x in lb) if p["which"] == "hi" else d1["l"] <= min(x["l"] for x in lb)
                d = 1 if hit else 0
        elif r == "first_move":
            o, c = self.mo(E0), self.mc(E0, sec)
            d = 0 if o is None or c is None else c - o
        elif r == "wkgap":
            a = self.datr()
            g = lp - d1["c"]
            d = g if a and abs(g) >= float(p["k"]) * a else 0
        else:                                           # above_both
            o, w = self.mo(E0), self.vw()
            if o is not None and w is not None:
                d = 1 if lp > o and lp > w[0] else -1 if lp < o and lp < w[0] else 0
        if not d:
            return
        side = self._side(d)
        rg = self.rng(E0, sec)
        self._mkt(ctx, side, ref=lp, struct=None if rg is None else (rg[1] if side == "long" else rg[0]))

    # ---- bar rules -------------------------------------------------------------------------------------------------------------------
    def fam_update(self, ctx):
        if self.p["rule"] != "fvg":
            return
        if self.n_ent != self.seen:                     # a trade has closed: only gaps formed after it count
            self.last, self.seen = {}, self.n_ent
        if len(self.H) >= 3 and self.atr:
            h1, l1, h3, l3, t = self.H[-3], self.L[-3], self.H[-1], self.L[-1], 0.25
            for sd, near, far, struct in ((1, l3, h1, self.L[-2]), (-1, h3, l1, self.H[-2])):
                if (near - far) * sd >= max(float(self.p["min_gap"]) * self.atr, t) and (near - struct) * sd > 0:
                    self.last[sd] = (near, struct)
        o = self.mo(E0)
        sd = 0 if o is None else (self.C[-1] > o) - (self.C[-1] < o)
        g = self.last.get(sd) if sd else None
        self.want = ("long" if sd > 0 else "short", g[0], g[1]) if g else None
        if self.orders and self.want != self.placed:
            self._cancel(ctx)

    def fam_signal(self, ctx):
        r = self.p["rule"]
        if r in TIME_RULES or not self._ok():
            return
        getattr(self, "_b_" + r)(ctx, _bar_end(self))

    def _c(self, txt: str) -> int:
        return clock_sec(txt)

    def _b_brk_win(self, ctx, end):
        p, rb = self.p, self._c(self.p["r_end"])
        if self.used or end <= rb:
            return
        if self.r is None:
            self.r = self.rng(self._c(p["r_start"]), rb)
            if self.r is None:
                return
        hi, lo = self.r
        c = self.C[-1]
        brk = "long" if c > hi else "short" if c < lo else None
        if brk is None:
            return
        self.used = True
        if p["mode"] == "follow":
            self._mkt(ctx, brk, struct=lo if brk == "long" else hi)
        else:
            side = "short" if brk == "long" else "long"
            self._mkt(ctx, side, struct=self.L[-1] if side == "long" else self.H[-1])

    def _b_lvl_touch(self, ctx, end):
        if self.nb < 2 or not self.dl:
            return
        d1 = self.dl[-1]
        for key, lv, up in (("h", d1["h"], True), ("l", d1["l"], False)):
            if key in self.touched:
                continue
            if (self.H[-1] >= lv) if up else (self.L[-1] <= lv):
                self.touched.add(key)
                if (self.C[-2] < lv) if up else (self.C[-2] > lv):          # it came from inside
                    side = self._side(1 if up else -1)
                    self._mkt(ctx, side, struct=self.L[-1] if side == "long" else self.H[-1])
                    return

    def _b_away_lim(self, ctx, end):
        p = self.p
        a, da = (self.dl[-1]["c"] if self.dl else None) if p["anchor"] == "pdc" else self.mo(E0), self.datr()
        if self.placed or a is None or not da:
            return
        dist = self.C[-1] - a
        if abs(dist) >= float(p["k"]) * da:
            self.placed = True
            self._lim(ctx, "long" if dist > 0 else "short", a, ttl=int(p["ttl"]))

    def _b_sweep(self, ctx, end):
        p, rb = self.p, self._c(self.p["r_end"])
        if end <= rb or end > self._c(p["s_end"]):
            return
        if self.r is None:
            self.r = self.rng(self._c(p["r_start"]), rb)
            if self.r is None:
                return
        hi, lo = self.r
        if self.H[-1] > hi and self.C[-1] < hi:
            self._mkt(ctx, "short", struct=self.H[-1])
        elif self.L[-1] < lo and self.C[-1] > lo:
            self._mkt(ctx, "long", struct=self.L[-1])

    def _b_c18(self, ctx, end):
        p, da = self.p, self.datr()
        o, c, h, l = self.O[-1], self.C[-1], self.H[-1], self.L[-1]
        if end != E0 + self.tf * 60 or not da or c == o or h - l < float(p["k"]) * da:
            return
        up = c > o
        if p["ent"] == "fade":
            self._mkt(ctx, "short" if up else "long", struct=h if up else l)
        else:
            self._lim(ctx, "long" if up else "short", (h + l) / 2.0, struct=l if up else h, ttl=int(p["ttl"]))

    def _b_gap_disagree(self, ctx, end):
        o18 = self.mo(E0)
        if end != E0 + self.tf * 60 or not self.dl or o18 is None:
            return
        gap, cd = o18 - self.dl[-1]["c"], self.C[-1] - self.O[-1]
        if gap * cd < 0:
            self._mkt(ctx, self._side(cd), struct=self.L[-1] if cd > 0 else self.H[-1])

    def _b_cross_open(self, ctx, end):
        o18 = self.mo(E0)
        if self.used or o18 is None or self.nb < 2 or end <= self._c(self.p["r_end"]):
            return
        a, b = self.C[-2] - o18, self.C[-1] - o18
        if a * b < 0:
            self.used = True
            side = self._side(b)
            self._mkt(ctx, side, struct=self.L[-1] if side == "long" else self.H[-1])

    def _b_fvg(self, ctx, end):
        if self.want is not None and self._lim(ctx, *self.want[:2], struct=self.want[2]) is not None:
            self.placed = self.want

    def _b_pcb(self, ctx, end):
        o18, nr = self.mo(E0), float(self.p["nr"])
        if self.nb < 2 or o18 is None or (nr > 0 and not (self.atr_p and self.H[-2] - self.L[-2] < nr * self.atr_p)):
            return
        c = self.C[-1]
        if c > self.H[-2] and c > o18:
            self._mkt(ctx, "long", struct=self.L[-2])
        elif c < self.L[-2] and c < o18:
            self._mkt(ctx, "short", struct=self.H[-2])

    def _b_outside(self, ctx, end):
        if self.nb < 2 or not (self.H[-1] > self.H[-2] and self.L[-1] < self.L[-2]) or self.C[-1] == self.O[-1]:
            return
        side = self._side(self.C[-1] - self.O[-1])
        self._mkt(ctx, side, struct=self.L[-1] if side == "long" else self.H[-1])

    def _b_pin(self, ctx, end):
        h, l, o, c, w = self.H[-1], self.L[-1], self.O[-1], self.C[-1], float(self.p["wick"])
        rg = h - l
        if self.nb < 4 or rg <= 0:
            return
        if h >= max(self.H) and h - max(o, c) >= w * rg:
            self._mkt(ctx, "short", struct=h)
        elif l <= min(self.L) and min(o, c) - l >= w * rg:
            self._mkt(ctx, "long", struct=l)

    def _b_ob(self, ctx, end):
        body = self.C[-1] - self.O[-1]
        if not self.atr_p or abs(body) < float(self.p["k"]) * self.atr_p:
            return
        up = body > 0
        for i in range(-2, -7, -1):
            if len(self.C) < -i:
                return
            if (self.C[i] < self.O[i]) if up else (self.C[i] > self.O[i]):
                self._lim(ctx, "long" if up else "short", self.O[i], struct=self.L[i] if up else self.H[i], ttl=int(self.p["ttl"]))
                return

    def _b_streak(self, ctx, end):
        n = int(self.p["nbars"])
        if self.nb < n:
            return
        o, c = self.O[-n:], self.C[-n:]
        up = all(x > y for x, y in zip(c, o))
        if not (up or all(x < y for x, y in zip(c, o))):
            return
        side = self._side(1 if up else -1)
        self._mkt(ctx, side, struct=min(self.L[-n:]) if side == "long" else max(self.H[-n:]))

    def _b_doji(self, ctx, end):
        h, l, o, c = self.H[-1], self.L[-1], self.O[-1], self.C[-1]
        if self.nb < 4 or h <= l or abs(c - o) > float(self.p["dj"]) * (h - l) or not (h >= max(self.H) or l <= min(self.L)):
            return
        t = ctx.tick
        self._arm(ctx, [("long", h + t, l, None), ("short", l - t, h, None)], ttl=int(self.p["ttl"]))


FAMILIES = {
    "eve_rule": (EveRule, {}, False,
                 "eve_rule: the 18:00-23:55 ET rules of the 2026-10-29 Asia list (prior-day location / extreme / wide-day fade, weekend gap, "
                 "above both open and VWAP, quiet-day break, level touch, anchor limit, sweep-reclaim, 18:00 candle, FVG limit, previous-bar "
                 "break, outside bar, pin, order block, streak, doji); `rule` picks one, held to the card's w_flat; see the module docstring",
                 {"rationale": "The evening has few traders, so what the day just ended did (its close location, extreme, range) and the first "
                               "Asia candles set the side, and thin books overshoot levels they then give back. Who loses: the traders who "
                               "ignore the cash day's lean and the ones who chase the first thin move.",
                  "complexity": 3,
                  "variants": [{"off_min": 0}, {"off_min": 30}, {"off_min": 60}],
                  "roots": ("NQ",)}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as eve_gap_follow.py)."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
