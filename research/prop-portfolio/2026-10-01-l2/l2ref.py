"""Reference re-implementations (on l2sim.Template) of the three approved tester families used by the
SIM VALIDATION GATE: straddle, orb, donchian (R/families/*.py). Parameters as the tester drafts pp_<fam>."""
from __future__ import annotations

import csv

import l2sim as S
from l2sim import SESS, Template, _hms


def _news() -> dict:
    """date -> 'N' (CPI/NFP 08:30) / 'F' (FOMC 14:00) / 'NF', from R/news_days.csv (as gen_drafts.build_news)."""
    out = {}
    p = S.R / "news_days.csv"
    if p.exists():
        for r in csv.DictReader(p.open()):
            tags = set(r["tags"].split("|"))
            out[r["date"]] = ("N" if tags & {"CPI", "NFP"} else "") + ("F" if "FOMC" in tags else "")
    return out


class Straddle(Template):
    """At session start + delay_min: OCO stop entries at last price +/- off_atr x ATR."""
    DEFAULTS = {"delay_min": 0, "off_atr": 0.5, "news_only": False}
    SCHEMA = {"delay_min": ("int", 0, 120), "off_atr": ("float", 0.1, 5), "news_only": ("bool",)}   # as pp_straddle
    NEWS: dict | None = None

    def _nw(self):
        if Straddle.NEWS is None:
            Straddle.NEWS = _news()
        return Straddle.NEWS

    def fam_filter(self, ids):
        return ["news", "fomc"] if self.p["news_only"] else ids

    def sess_on(self, s):
        if not self.p["news_only"]:
            return True
        return ("N" if s == "news" else "F") in self._nw().get(self.day, "")

    def trades_on(self, d):
        return (not self.p["news_only"]) or d.isoformat() in self._nw()

    def fam_times(self):
        dm = int(self.p["delay_min"]) * 60
        return [] if self.p["news_only"] else [_hms(SESS[s][0] + dm) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s = self.sid
        if s is None:
            return
        at = SESS[s][0] + (0 if s in ("news", "fomc") else int(self.p["delay_min"]) * 60)
        if sec != at or not self.can_enter(ctx):
            return
        lp = ctx.last_price
        if lp is None:
            return
        off = float(self.p["off_atr"]) * self.atr
        self._arm(ctx, [("long", lp + off, None, None), ("short", lp - off, None, None)])


class Orb(Template):
    """Opening range of the first or_min minutes; OCO stop entries one tick beyond, struct stop = other side."""
    DEFAULTS = {"or_min": "15"}
    SCHEMA = {"or_min": ("choice", ("5", "15", "30"))}                                                # as pp_orb

    def fam_times(self):
        m = int(self.p["or_min"]) * 60
        return [_hms(SESS[s][0] + m) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s = self.sid
        if s is None or sec != SESS[s][0] + int(self.p["or_min"]) * 60 or not self.can_enter(ctx):
            return
        r = self.rng(SESS[s][0], sec)
        if r is None:
            return
        hi, lo = r
        t = ctx.tick
        self._arm(ctx, [("long", hi + t, lo, None), ("short", lo - t, hi, None)])


class Donchian(Template):
    """Close beyond the prior n-bar channel -> market entry; struct stop = opposite channel side."""
    DEFAULTS = {"n": 20}
    SCHEMA = {"n": ("int", 2, 200)}                                                                   # as pp_donchian
    WARM = 5

    def fam_signal(self, ctx):
        n = int(self.p["n"])
        if self.nb <= n:
            return
        hh, ll, c = max(self.H[-n - 1:-1]), min(self.L[-n - 1:-1]), self.C[-1]
        if c > hh:
            self._mkt(ctx, "long", struct=ll)
        elif c < ll:
            self._mkt(ctx, "short", struct=hh)


class FeatureProbe(S.Strategy):
    """PLUMBING PROBE, not a strategy: goes long at a fixed clock time whatever the features say, tagging the
    trade with the feature values the engine exposed at that decision (tests the timestamp law end to end),
    and is flat `hold_min` minutes later."""
    session_window = ("09:30", "16:00")
    session_independent = True                  # stateless: safe on several workers (the base default is False)
    DEFAULTS = {"at": "10:00:00", "hold_min": 5}
    SCHEMA = {"hold_min": ("int", 1, 300)}

    def times(self):
        h, m, s = (int(x) for x in self.p["at"].split(":"))
        e = h * 60 + m + int(self.p["hold_min"])
        return [self.p["at"], "%02d:%02d:%02d" % (e // 60, e % 60, s)]

    def on_time(self, ctx, t):
        if t == self.p["at"]:
            ctx.market("long", tag={"n": ctx.feat_n(), "imb10": ctx.feat("imb10"), "f_delta": ctx.feat("f_delta")})
        else:
            ctx.flatten("time")


class ClockProbe(S.Strategy):
    """PLUMBING PROBE, not a strategy: the INDEPENDENT-CLOCK check of the feature adapter. At every 1-minute
    bar close the newest feature row the engine exposes must be the flow row of the minute that just closed:
    its f_o / f_h / f_l / f_c / f_volume equal the bar the engine built from the tape's own timestamps. A
    constant shift in the adapter (a minute early = look-ahead, a minute late = stale, an hour = a time-zone
    or DST slip) breaks the equality on every bar. Never trades; reports "clock <same>/<bars>" as the
    session's no_trade reason (the only channel back through worker processes). Needs CLOCK_COLS."""
    session_independent = True
    CLOCK_COLS = ("f_o", "f_h", "f_l", "f_c", "f_volume")

    def on_session(self, ctx):
        self.n = self.same = 0

    def on_bar(self, ctx, bar):
        self.n += 1
        self.same += tuple(ctx.feat(c) for c in self.CLOCK_COLS) == (bar.o, bar.h, bar.l, bar.c, float(bar.v))
        ctx.skip(f"clock {self.same}/{self.n}")


FAMILIES = {"straddle": Straddle, "orb": Orb, "donchian": Donchian}
