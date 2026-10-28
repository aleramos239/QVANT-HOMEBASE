"""improve_1026 -- the code ideas of the owner's "run all of these" round (2026-10-26): small subclasses of the g93 / noise / g94 / g92 families.

Every original family stays untouched; with the new inputs at their defaults a subclass is its parent. Written from the rule before any result.
  win_bracket_rev   win_bracket + a second trade: after the first trade is over, the first tf close beyond the FAR edge of the range trades that
                    side at market (stop = the near edge: the stop-and-reverse). max_tr 2.
  noise_band_x      noise_band + x_in (a close back inside the band flattens: the natural invalidation) + adx_min (ADX(14) of the day's tf bars
                    >= adx_min at the signal close; none = no trade).
  noise_band_eve_x  the same on the 18:00 evening anchor.
  win_break_vol     win_break + vol_m: a break bar whose volume is under vol_m x the median of the same clock bar over the days before is skipped
                    (the day's one signal stays free for a later break bar).
  pd_bracket_x      pd_bracket + re_min / alive_to (re-arm every re_min minutes until alive_to, the old orders cancelled; ttl to alive_to),
                    lvl (pd | pd_pw | pd_on | all: the extra levels = prior-week high / low, overnight high / low, one OCO group, each level's own
                    opposite edge is the stop) and dgate (off | sma | loc: arm only the side of the prior close vs its n_d mean / of its range middle).
  pd_fade           failed break of the prior day's high / low: a tf bar traded beyond the level, a close back inside within `wait` minutes ->
                    market against the break, stop beyond the extreme (own stop) ; one per side, max_tr 2.
Registration as win_dir.py: join_blocks(). Tests: engine/tests/test_improve_1026.py."""
from __future__ import annotations

import l2sim as S
from l2sim import SESS, _hms

from . import flex as FX
from . import noise as NB
from . import noise_eve as NE
from .win_dir import PdBracket


class WinBracketRev(FX.WinBracket):
    DEFAULTS = {**FX.WinBracket.DEFAULTS, "max_tr": 2}

    def fam_signal(self, ctx):
        if self.n_ent != 1 or not self.sid or FX._bar_end(self) <= self.rb or self.sid != self._plan()[2]:
            return
        if self.r is None:
            self.r = self.rng(self.ra, self.rb)
            if self.r is None:
                return
        hi, lo = self.r
        c = self.C[-1]
        if self.side > 0 and c < lo:
            self._mkt(ctx, "short", struct=hi)
        elif self.side < 0 and c > hi:
            self._mkt(ctx, "long", struct=lo)


class _BandX:
    """x_in + adx_min for the noise bands (mixin over a NoiseBand subclass)."""
    X_DEFAULTS = {"x_in": "off", "adx_min": 0.0}
    X_SCHEMA = {"x_in": ("choice", ("off", "on")), "adx_min": ("float", 0, 100)}

    def _manage(self, ctx):
        if super()._manage(ctx):
            return True
        if self.p["x_in"] == "on" and not ctx.flat and self.fill_ns is not None and ctx.now_ns > self.fill_ns and self.up is not None:
            c = self.C[-1]
            if (self.side > 0 and c < self.up) or (self.side < 0 and c > self.dn):
                ctx.flatten("band")
                return True
        return False

    def fam_signal(self, ctx):
        m = float(self.p["adx_min"])
        if m > 0:
            from .blocks import adx_last
            a = adx_last(self.H, self.L, self.C)
            if a is None or a < m:
                return
        super().fam_signal(ctx)


class NoiseBandX(_BandX, NB.NoiseBand):
    DEFAULTS = {**NB.NoiseBand.DEFAULTS, **_BandX.X_DEFAULTS}
    SCHEMA = {**NB.NoiseBand.SCHEMA, **_BandX.X_SCHEMA}


class NoiseBandEveX(_BandX, NE.NoiseBandEve):
    DEFAULTS = {**NE.NoiseBandEve.DEFAULTS, **_BandX.X_DEFAULTS}
    SCHEMA = {**NE.NoiseBandEve.SCHEMA, **_BandX.X_SCHEMA}


def _rvol_no_seal(rv):
    """blk_rvol, with a reference date the minute-volume cache lacks and the seal refuses (NQ 2026-09-23 / 09-25) counted as a date with no
    tape (cum_volume's own None), not a crash: nothing of that date is read. Before 2026-10-26 such a date killed a test-month read."""
    from . import blocks as B
    real = B.cum_volume

    def safe(root, iso):
        try:
            return real(root, iso)
        except S.HoldoutSealed:
            return None
    B.cum_volume = safe          # shortcut: patches the module global for this one call (single-threaded workers); a fix in blocks.cum_volume is the upgrade
    try:
        return rv()
    finally:
        B.cum_volume = real


class WinBreakVol(FX.WinBreak):
    DEFAULTS = {**FX.WinBreak.DEFAULTS, "vol_m": 1.5}
    SCHEMA = {**FX.WinBreak.SCHEMA, "vol_m": ("float", 0, 50)}

    def fam_signal(self, ctx):
        vm = float(self.p["vol_m"])
        if vm > 0 and not self.used and FX._bar_end(self) > self.rb:
            if self.r is None:
                self.r = self.rng(self.ra, self.rb)
            if self.r is not None and (self.C[-1] > self.r[0] or self.C[-1] < self.r[1]):
                rv = getattr(self, "blk_rvol", None)
                if rv is None:
                    raise RuntimeError("win_break_vol needs the Blocks mixin (blk_rvol): run the wrapped class (families.blocks.WRAPPED)")
                sig = _rvol_no_seal(rv)
                if sig is None or sig[0] < vm * sig[1]:
                    return
        super().fam_signal(ctx)


class PdBracketX(PdBracket):
    DEFAULTS = {"off_min": 0, "max_tr": 1, "re_min": 0, "alive_to": "", "lvl": "pd", "dgate": "off", "n_d": 10}
    SCHEMA = {"off_min": ("int", 0, 240), "re_min": ("int", 0, 240), "alive_to": ("str",), "lvl": ("choice", ("pd", "pd_pw", "pd_on", "all")),
              "dgate": ("choice", ("off", "sma", "loc")), "n_d": ("int", 1, 300)}

    def _pd_times(self, s):
        a = SESS[s][0] + int(self.p["off_min"]) * 60
        re, to = int(self.p["re_min"]) * 60, self.p["alive_to"]
        out = [a]
        if re > 0 and to:
            end = S._sec(to)
            while out[-1] + re < end:
                out.append(out[-1] + re)
        return out

    def fam_times(self):
        return sorted({_hms(t) for s in self.sessions() for t in self._pd_times(s)})

    def _pd_levels(self):
        p, dl = self.p, self.dl
        lv = [(dl[-1]["h"], dl[-1]["l"])]
        if p["lvl"] in ("pd_pw", "all") and len(dl) >= 5:
            lv.append((max(r["h"] for r in dl[-5:]), min(r["l"] for r in dl[-5:])))
        if p["lvl"] in ("pd_on", "all"):
            on = self.rng(0, SESS[self.sid][0])
            if on:
                lv.append(on)
        return lv

    def _pd_sides(self):
        g, dl, n = self.p["dgate"], self.dl, int(self.p["n_d"])
        if g == "off":
            return ("long", "short")
        if g == "loc":
            d = dl[-1]["c"] - (dl[-1]["h"] + dl[-1]["l"]) / 2
        else:
            if len(dl) < n:
                return ()
            d = dl[-1]["c"] - sum(r["c"] for r in dl[-n:]) / n
        return ("long",) if d > 0 else ("short",) if d < 0 else ()

    def fam_time(self, ctx, sec):
        s, lp = self.sid, ctx.last_price
        if s is None or lp is None or not self.dl or sec not in self._pd_times(s):
            return
        if sec != self._pd_times(s)[0]:                         # a re-arm: the old resting orders go first
            if not ctx.flat or self.n_ent >= self.p["max_tr"]:
                return
            for r in self.orders:
                if r[0].status == "working":
                    ctx.cancel(r[0])
            self.orders = []
        if not self.can_enter(ctx):
            return
        t, sides = ctx.tick, self._pd_sides()
        legs = []
        for hi, lo in self._pd_levels():
            if "long" in sides and lp < hi:
                legs.append(("long", hi + t, lo, None))
            if "short" in sides and lp > lo:
                legs.append(("short", lo - t, hi, None))
        if legs:
            to = self.p["alive_to"]
            ttl = max(1, (S._sec(to) - sec) // 60 // self.tf) if to else None
            self._arm(ctx, legs, ttl=ttl)


class PdFade(PdBracket):
    """pd_fade (module docstring). State per day: the first bar index a level was broken at, the extreme since, and a used flag per side."""
    DEFAULTS = {"wait": "15", "max_tr": 2}
    SCHEMA = {"wait": ("choice", ("5", "10", "15", "30"))}

    def fam_times(self):
        return []

    def fam_time(self, ctx, sec):
        return

    def fam_day(self, ctx):
        self.bk = {"hi": None, "lo": None}                   # (first break bar index, extreme)
        self.done = {"hi": False, "lo": False}

    def fam_signal(self, ctx):
        if not self.dl:
            return
        hi, lo, h, l, c, nb = self.dl[-1]["h"], self.dl[-1]["l"], self.H[-1], self.L[-1], self.C[-1], self.nb
        w = max(1, int(self.p["wait"]) // self.tf)
        for k, brk, ext, back in (("hi", h > hi, h, c < hi), ("lo", l < lo, l, c > lo)):
            if self.done[k]:
                continue
            a = self.bk[k]
            if brk:
                a = self.bk[k] = (a[0], max(a[1], ext) if k == "hi" else min(a[1], ext)) if a else (nb, ext)
            if a is None:
                continue
            if nb - a[0] >= w:                               # the window passed without a close back inside
                self.done[k] = True
            elif back:
                self.done[k] = True
                self._mkt(ctx, "short" if k == "hi" else "long", struct=a[1])
                return


FAMILIES = {
    "win_bracket_rev": (WinBracketRev, {}, True,
                        "win_bracket_rev: win_bracket + a second trade, the stop-and-reverse: after the first trade the first tf close beyond the "
                        "far edge of the range trades that side at market (max_tr 2)",
                        {"rationale": "A break that fails and runs through the other side of the range leaves the early traders trapped on the first "
                                      "side, and their stops feed the second move.",
                         "complexity": 3, "variants": [{"r_start": "00:00"}, {"r_start": "01:00"}, {"r_start": "03:00"}], "roots": ("NQ",)}),
    "noise_band_x": (NoiseBandX, {}, False,
                     "noise_band_x: noise_band + x_in (a close back inside the band flattens) + adx_min (ADX(14) of the day's tf bars at the signal)",
                     {"rationale": "A move beyond the usual noise that falls back inside the band was noise after all, and a trend filter keeps only the "
                                   "days when one-way flow is already running.",
                      "complexity": 7, "variants": [{"k": k} for k in (0.2, 0.3, 0.4)]}),
    "noise_band_eve_x": (NoiseBandEveX, {}, False,
                         "noise_band_eve_x: noise_band_eve + x_in (a close back inside the band flattens) + adx_min",
                         {"rationale": "The evening band break that falls back inside the band was noise after all; leave it at the close.",
                          "complexity": 7, "variants": [{"k": k} for k in (0.2, 0.3, 0.4)]}),
    "win_break_vol": (WinBreakVol, {}, True,
                      "win_break_vol: win_break + vol_m: only a break bar whose volume is at least vol_m x the median of the same clock bar over "
                      "the days before counts",
                      {"rationale": "A break through the opening range on heavy volume is a decision by size, a break on thin volume is a probe that "
                                    "the market takes back.",
                       "complexity": 4, "variants": [{"r_end": "09:35"}, {"r_end": "09:40"}, {"r_end": "09:45"}], "roots": ("NQ",)}),
    "pd_bracket_x": (PdBracketX, {}, True,
                     "pd_bracket_x: pd_bracket + re_min / alive_to (re-arm), lvl (prior-week and overnight levels) and dgate (daily trend / close location)",
                     {"rationale": "The prior day's high and low are the levels every desk watches; more levels, a later re-arm or the side of the "
                                   "daily trend only change which of those breaks is taken.",
                      "complexity": 4, "variants": [{"off_min": 0}, {"off_min": 15}, {"off_min": 30}], "roots": ("NQ",)}),
    "pd_fade": (PdFade, {}, True,
                "pd_fade: a tf bar traded beyond yesterday's high / low and closed back inside within `wait` minutes -> market against the break, "
                "stop beyond the extreme; one per side",
                {"rationale": "A break of the prior day's high or low that is taken back at once traps the breakout traders, who then sell into "
                              "the move.",
                 "complexity": 3, "variants": [{"wait": "10"}, {"wait": "15"}, {"wait": "30"}], "roots": ("NQ",)}),
}


def join_blocks() -> None:
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
