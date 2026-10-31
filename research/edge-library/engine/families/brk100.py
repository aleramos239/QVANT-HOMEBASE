"""brk100 -- six break families from the owner's 100 breakout ideas (2026-10-28), each one trade a day, flat 15:58, exits from the card's table.

pd_cond_bracket    pd_bracket (OCO one tick beyond the prior day's high / low) armed only when the prior day was nr4 / nr7 (its range the
                   narrowest of the last 4 / 7 days), an inside day (inside the day before it) or an outside day.
nd_bracket         the same OCO bracket at the high / low of the last n_d days (2 .. 20) instead of the prior day's.
orb_cond           win_bracket on the 09:30 range (r_end 10:00 = a 30-minute opening range) armed only on a day the prior day was inside /
                   nr7, or the day opens outside the prior day's range (gapout).
on_narrow_bracket  win_bracket on the 00:00-09:30 overnight range, armed only when that range is at most k x the prior day's range.
orb_dtrend         win_bracket on the 09:30-10:00 range, only the side of the daily trend (prior close above / below the mean of the last
                   n_d closes).
atr_contract_break the n bars before a close had a mean true range under k x the mean of the 48 bars before them, and this close is beyond
                   their high / low -> market with it.
Daily bars are ctx.daily (the days before the trade date): no look-ahead. Registration as first5_follow.py: join_blocks(). Tests:
engine/tests/test_brk100.py."""
from __future__ import annotations

import l2sim as S
from l2sim import Template

from . import flex as FX
from .win_dir import PdBracket

NR = {"nr4": 4, "nr7": 7}


def day_cond(dl: list, cond: str) -> bool:
    """True when the last daily bar of dl (the prior day) is nr4 / nr7, inside the day before it, or outside it."""
    if cond in NR:
        n = NR[cond]
        r = [x["h"] - x["l"] for x in dl[-n:]]
        return len(r) == n and r[-1] <= min(r)
    if len(dl) < 2:
        return False
    a, b = dl[-1], dl[-2]
    return (a["h"] <= b["h"] and a["l"] >= b["l"]) if cond == "inside" else (a["h"] > b["h"] and a["l"] < b["l"])


class PdCondBracket(PdBracket):
    DEFAULTS = {**PdBracket.DEFAULTS, "cond": "nr7"}
    SCHEMA = {**PdBracket.SCHEMA, "cond": ("choice", ("nr4", "nr7", "inside", "outside"))}

    def fam_time(self, ctx, sec):
        if self.dl and day_cond(self.dl, self.p["cond"]):
            super().fam_time(ctx, sec)


class NdBracket(PdBracket):
    DEFAULTS = {**PdBracket.DEFAULTS, "n_d": 5}
    SCHEMA = {**PdBracket.SCHEMA, "n_d": ("int", 2, 60)}

    def fam_time(self, ctx, sec):
        s, lp, n = self.sid, ctx.last_price, int(self.p["n_d"])
        if s is None or lp is None or len(self.dl) < n or sec != S.SESS[s][0] + int(self.p["off_min"]) * 60 or not self.can_enter(ctx):
            return
        hi, lo, t = max(x["h"] for x in self.dl[-n:]), min(x["l"] for x in self.dl[-n:]), ctx.tick
        legs = ([("long", hi + t, lo, None)] if lp < hi else []) + ([("short", lo - t, hi, None)] if lp > lo else [])
        if legs:
            self._arm(ctx, legs)


class OrbCond(FX.WinBracket):
    DEFAULTS = {**FX.WinBracket.DEFAULTS, "r_end": "10:00", "cond": "inside"}
    SCHEMA = {**FX.WinBracket.SCHEMA, "cond": ("choice", ("inside", "nr7", "gapout"))}

    def _ok(self) -> bool:
        if not self.dl:
            return False
        if self.p["cond"] != "gapout":
            return day_cond(self.dl, self.p["cond"])
        o = self.mo(FX._clock(self.p["r_start"], "r_start"))
        return o is not None and (o > self.dl[-1]["h"] or o < self.dl[-1]["l"])

    def fam_time(self, ctx, sec):
        if self._ok():
            super().fam_time(ctx, sec)


class OnNarrowBracket(FX.WinBracket):
    DEFAULTS = {**FX.WinBracket.DEFAULTS, "r_start": "00:00", "r_end": "09:30", "k": 0.5}
    SCHEMA = {**FX.WinBracket.SCHEMA, "k": ("float", 0.05, 5)}

    def fam_time(self, ctx, sec):
        a, b, _ = self._plan()
        r = self.rng(a, b)
        if r is not None and self.dl and r[0] - r[1] <= float(self.p["k"]) * (self.dl[-1]["h"] - self.dl[-1]["l"]):
            super().fam_time(ctx, sec)


class OrbDTrend(FX.WinBracket):
    DEFAULTS = {**FX.WinBracket.DEFAULTS, "r_end": "10:00", "n_d": 50}
    SCHEMA = {**FX.WinBracket.SCHEMA, "n_d": ("int", 2, 300)}

    def fam_time(self, ctx, sec):
        a, b, home = self._plan()
        n = int(self.p["n_d"])
        if sec != b or self.sid != home or len(self.dl) < n or not self.can_enter(ctx):
            return
        r, d = self.rng(a, b), self.dl[-1]["c"] - sum(x["c"] for x in self.dl[-n:]) / n
        if r is None or d == 0:
            return
        hi, lo, t = r[0], r[1], ctx.tick
        self._arm(ctx, [("long", hi + t, lo, None)] if d > 0 else [("short", lo - t, hi, None)])


class AtrContractBreak(Template):
    DEFAULTS = {"k": 0.6, "n": 12, "max_tr": 1}
    SCHEMA = {"k": ("float", 0.1, 1.5), "n": ("int", 3, 60)}
    SCREEN_TFS = ("1", "3", "5", "15", "30")
    FEATURES = ()
    LONG = 48

    def fam_signal(self, ctx):
        n = int(self.p["n"])
        if self.nb < n + 1 + self.LONG:
            return
        tr, near = self.TR, self.TR[-n - 1:-1]
        far = tr[-n - 1 - self.LONG:-n - 1]
        if sum(near) / n >= float(self.p["k"]) * sum(far) / self.LONG:
            return
        c = self.C[-1]
        if c > max(self.H[-n - 1:-1]):
            self._mkt(ctx, "long")
        elif c < min(self.L[-n - 1:-1]):
            self._mkt(ctx, "short")


def _entry(cls, text, why, cx, variants, both=True):
    return (cls, {}, both, text, {"rationale": why, "complexity": cx, "variants": variants, "roots": ("NQ",)})


FAMILIES = {
    "pd_cond_bracket": _entry(PdCondBracket, "pd_cond_bracket: pd_bracket armed only after an nr4 / nr7 / inside / outside prior day",
                              "After the narrowest day of 4 or 7 (or an inside day) the market has coiled; the first break of that day's high or low "
                              "is where the stops of the traders on the other side sit.", 3,
                              [{"cond": "nr4"}, {"cond": "nr7"}, {"cond": "inside"}]),
    "nd_bracket": _entry(NdBracket, "nd_bracket: OCO stop entries one tick beyond the high / low of the last n_d days",
                         "A break of a multi-day high or low runs the stops that sit beyond a level more desks watch than the prior day's.", 2,
                         [{"n_d": 2}, {"n_d": 5}, {"n_d": 10}, {"n_d": 20}]),
    "orb_cond": _entry(OrbCond, "orb_cond: the 09:30-10:00 range bracket on an inside / nr7 prior day or a day that opens outside its range",
                       "On a coiled day (inside, nr7) or an open outside yesterday's range the opening range break is the day's first real "
                       "decision, and the stops on its other side feed it.", 3,
                       [{"cond": "inside"}, {"cond": "nr7"}, {"cond": "gapout"}]),
    "on_narrow_bracket": _entry(OnNarrowBracket, "on_narrow_bracket: the 00:00-09:30 range bracket when that range is at most k x the prior day's",
                                "A quiet overnight leaves the cash open to set the day: the break of a narrow overnight range is the first "
                                "real move.", 3,
                                [{"k": 0.3}, {"k": 0.5}, {"k": 0.7}]),
    "orb_dtrend": _entry(OrbDTrend, "orb_dtrend: the 09:30-10:00 range break, only the side of the daily trend (prior close vs the mean of n_d closes)",
                         "In an up trend the stops are mostly below and the opening range break up finds the buyers already in; the other "
                         "side is a counter-trend probe.", 3,
                         [{"n_d": 20}, {"n_d": 50}, {"n_d": 100}]),
    "atr_contract_break": _entry(AtrContractBreak, "atr_contract_break: n bars with a mean true range under k x the 48 bars before them, then a close beyond their high / low",
                                 "Quiet bars after active ones are a coil; the first close out of it carries because the resting orders on "
                                 "both sides sit just outside.", 2,
                                 [{"k": 0.5}, {"k": 0.65}, {"k": 0.8}], both=False),
}


def join_blocks() -> None:
    """Put the families into families/blocks.py's BASES and WRAPPED, as first5_follow does. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
