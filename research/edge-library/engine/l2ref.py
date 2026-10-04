"""Reference re-implementations (on l2sim.Template) of the three approved tester families used by the
SIM VALIDATION GATE: straddle, orb, donchian (R/families/*.py). Parameters as the tester drafts pp_<fam>.

EDGE LIBRARY (engine-owned, used by run_menus / the controls; a family author subclasses them in a families/ module):
  Random     C1 control: the port of R/families/random.py (tester-match gate: tests/test_edge_controls.py)
  StraddleT  family A `straddle_t`: OCO stop entries around the last price at ONE clock time of the Globex day
             (18:00 -> 17:00 ET), the "new clock path"; shift_seed > 0 = its TIME-SHUFFLE NULL."""
from __future__ import annotations

import csv
import datetime as dt
import random

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


class Random(Template):
    """C1 CONTROL (port of R/families/random.py, the tester draft pp_random): at each tf-bar close of a session,
    while flat and under max_tr entries, enter at market with probability p_entry; side random (or `dir`).
    RNG = random.Random(f"{seed}|{date}|{session}"), two draws at EVERY tf close of a session, so the stream does
    not depend on the trade path (session id, not the sess input: a sess=nyam run equals the nyam part of sess=all).
    Same stops / targets / exits as every family. The new sessions eve / pre draw from their own streams."""
    DEFAULTS = {"p_entry": 0.05, "seed": 1}
    SCHEMA = {"p_entry": ("float", 0, 1), "seed": ("int", 0, 1000000)}                                # as pp_random
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_session(self, ctx, s):
        self.rg = random.Random("%s|%s|%s" % (self.p["seed"], ctx.date, s))

    def fam_update(self, ctx):
        self.rr = (self.rg.random(), self.rg.random()) if self.sid is not None else None

    def fam_signal(self, ctx):
        r, d = self.rr, self.p["dir"]
        if r is not None and r[0] < float(self.p["p_entry"]):
            self._mkt(ctx, d if d != "both" else ("long" if r[1] < 0.5 else "short"))


# bounds a (shifted) clock-time window must stay inside, in seconds relative to 00:00 ET of the trade date:
# the evening segment 18:00 .. 23:59, the day segment 00:00 .. 15:58 (the last session end of the tester's day)
SEG_BOUNDS = {"eve": (S.SESS["eve"][0], S.SESS["eve"][1]), "day": (0, S.SESS["pm"][1])}


class StraddleT(Template):
    """Family A `straddle_t` (EDGE_SPEC) on the GLOBEX-DAY CLOCK: at the clock time `at` (any minute of the Globex day;
    18:00 .. 23:59 = the evening BEFORE the trade date, replayed as the evening segment) rest OCO stop entries at the
    last price +/- the offset; one trade per time per day (max_tr 1). Unfilled entries are cancelled `cancel_min`
    minutes later (0 = only by the Template's rule, 5 minutes before the flat time); flat at `flat` ('' = EDGE_SPEC's
    rule l2sim.clock_flat(at): the next listed time or the session end, whichever is first).
      offset   off_mode atr: off_val x ATR30  |  pts: off_val points          (menu: l2sim.menu_offsets(root))
      ATR30    the Template's ATR at tf 30 (tf is fixed). ATR_CARRY: until 3 half-hour bars exist since the last
               restart (18:00 for the evening, 00:00 for the day) the ATR is the closing ATR30 of the most recent
               evening (18:00-24:00) that has ended (prior data only) -- that is what an 18:00 fire (the previous
               trade date's evening) or a 00:00 fire (the evening just ended) uses; 20:00, 02:00, 03:00, 08:30,
               09:30, 11:05, 13:30 use the running value, exactly as the tester's straddle.
      anchor   the last print before `at`. A 00:00 fire takes the last print of the evening (ctx.prev_price); an 18:00
               fire has no print of its own Globex day yet and takes the previous trade date's last print (the 17:00
               close; the orders go live at 18:00:00.085 and a gapped reopen fills at the gap price); on a contract-
               roll day that close is another contract -> no 18:00 trade.
      session  the family's own window 't' = [at, flat): the `sess` input is not used. Offline the trade is tagged by
               its entry time (18:00 / 20:00 -> eve, 00:00 / 02:00 -> asia, 03:00 -> london, 08:30 -> pre, ...).
    With at = 03:00 / 09:30 / 13:30, flat = 08:25 / 11:00 / 15:58 and cancel_min = 0 the trades are identical to
    l2ref.Straddle (sess london / nyam / pm, tf 30, delay_min 0): tests/test_edge_clock.py.

    TIME-SHUFFLE NULL (shift_seed > 0): the SAME straddle (same offset, exits, cancel delay, holding window length)
    fired at a seeded uniformly random minute within +/- shift_max (90) minutes of `at`: per trade date one draw
    random.Random(f"{shift_seed}|{date}|{at}") over the minute shifts that keep the whole window [at, flat] inside
    its own segment (evening 18:00-23:59, day 00:00-15:58). The draw does not depend on any other input, so every
    cell of one seed fires at the same minutes."""
    DEFAULTS = {"at": "09:30", "flat": "", "cancel_min": 60, "off_mode": "atr", "off_val": 0.5, "tf": "30", "max_tr": 1,
                "shift_seed": 0, "shift_max": 90}
    SCHEMA = {"at": ("str",), "flat": ("str",), "cancel_min": ("int", 0, 600), "off_mode": ("choice", ("atr", "pts")),
              "off_val": ("float", 0.01, 1000), "tf": ("choice", ("30",)), "shift_seed": ("int", 0, 1000000),
              "shift_max": ("int", 0, 600)}
    ATR_CARRY = True
    SCREEN_TFS = ("30",)
    FEATURES = ()

    def _base(self) -> tuple:
        a = S.clock_sec(self.p["at"])
        b = S.clock_sec(self.p["flat"] or S.clock_flat(self.p["at"]))
        if b <= a:
            raise ValueError(f"straddle_t: flat {self.p['flat'] or S.clock_flat(self.p['at'])} is not after at {self.p['at']}")
        return a, b

    def shifts(self) -> list:
        """The minute shifts the null may draw: within +/- shift_max, the whole window inside its segment."""
        a, b = self._base()
        lo, hi = SEG_BOUNDS["eve" if a < 0 else "day"]
        m = int(self.p["shift_max"])
        return [k for k in range(-m, m + 1) if a + 60 * k >= lo and b + 60 * k <= hi]

    def shift_of(self, d) -> int:
        """The day's shift in minutes (0 when shift_seed is 0)."""
        if not self.p["shift_seed"]:
            return 0
        ks = self.shifts()
        iso = d.isoformat() if isinstance(d, dt.date) else str(d)
        return ks[random.Random("%s|%s|%s" % (self.p["shift_seed"], iso, self.p["at"])).randrange(len(ks))] if ks else 0

    def begin_day(self, d):                           # called by the runner before times() is read for the day
        a, b = self._base()
        k = 60 * self.shift_of(d)
        self.S["t"] = (a + k, b + k)

    def fam_sessions(self):
        a, b = self._base()
        return {"t": (a, b)}

    def fam_filter(self, ids):
        return ["t"]

    def fam_times(self):
        a = self.S["t"][0]
        cm = int(self.p["cancel_min"]) * 60
        return [_hms(a)] + ([_hms(a + cm)] if cm else [])

    def fam_time(self, ctx, sec):
        if self.sid != "t":
            return
        a, b = self.S["t"]
        cm = int(self.p["cancel_min"]) * 60
        if cm and sec == a + cm:
            self._cancel(ctx)                      # the unfilled entries only: a position keeps its stop / target
            return
        if sec != a or not self.can_enter(ctx):
            return
        lp = ctx.last_price                        # the last print in the window (the tester's straddle)
        if lp is None:
            lp = ctx.prev_price                    # 00:00: the last print of the evening (same Globex session)
        if lp is None:
            lp = self.pdc                          # 18:00: the previous trade date's last print (None on a roll day)
        if lp is None:
            return
        off = float(self.p["off_val"]) * (self.atr if self.p["off_mode"] == "atr" else 1.0)
        self._arm(ctx, [("long", lp + off, None, None), ("short", lp - off, None, None)], lp=lp)


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
