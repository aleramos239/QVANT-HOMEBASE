"""avwap -- ANCHORED VWAP LINES as entry triggers (the owner's VWAP hunt, 2026-10-20: ideas 11-15 of the brief
prompt-vwap-5-10-a-day-3to1-blocks; the owner: "if you need build new blocks, just make sure to save and add them so we dont need to
rebuild them"). Written from the rules below before any result. No Level-2 feature (FEATURES = ()): NQ, ES and GC, 1 contract,
hold_to = 'day' (flat 15:58 ET); the exits are the sheet's (or the standard table's).

THE LINES (`line`; `also` = a second line the close must be on the trade's side of when the order is decided). Each is the volume-
weighted typical price (h + l + c) / 3 of 1-minute bars (the engine's VWAP rule), summed from its anchor to the last minute that has ended:
    rth       09:30 ET of the trade date                      (New York passes only)
    london    03:00 ET                                        (london, pre, New York)
    midnight  00:00 ET
    globex    18:00 ET of the evening before (the Globex day's open; the "session VWAP" of a trader's screen)
    week      18:00 ET of the evening before the week's first trade date (the ISO week; a holiday session inside the week counts;
              a contract roll inside the week restarts it)
    (globex / onh / onl / week: "the evening before" is 18:00-24:00 even when the tape after a holiday starts 30 hours back)
    pdvwap    a FIXED level: the previous trade date's 09:30-16:00 VWAP at its 16:00 close ("yesterday's closing VWAP")
    pdh, pdl  anchored at the minute of the previous trade date's 09:30-16:00 high / low (the first minute that printed it), summed
              through the rest of that session (to 17:00), every minute traded since (a holiday session too) and today
    onh, onl  anchored at the minute of the overnight high / low (18:00 the evening before .. 09:30), known at 09:30: New York passes only
A contract-roll day (Template.ROLLS) has no previous-day line (the prior contract); a missing tape: no line, no trade.

WHERE THE MINUTES COME FROM. Today from 00:00 ET: the instance's own 1-minute bars (Template.M), fed in order. Before 00:00 ET (this
evening) and the days before: the session tapes, built into 1-minute bars exactly as the engine builds them (buckets of epoch minutes,
o / h / l / c / v), each tape opened with the seal of ITS OWN date -- the build switch up to 2025-06-30, the test switch after
(candle_sweep.session_closes, 2026-10-20): a test-day run reads the build days before it, a build run never reaches a test date because
only dates BEFORE today are opened, and of today's tape only the minutes before 00:00 ET are ever read (LookAheadError otherwise).

THE FAMILIES
  avwap_touch   price closes at least `away` ticks from the line (1-minute closes) -> a LIMIT AT the line, re-priced at every tf close,
                on the side price came from (above -> long); the first 1-minute bar that comes within `near` ticks of the line (as it
                stood when that minute began) uses the arm up, filled or not (vwap_touch's rule, families/vwap_touch.py, on any line).
  avwap_flip    a tf close crosses the line and the next `hold` closes stay on the new side -> market with it at that close
                (vwap_flip's rule on any line). `vol_m` > 0: the CROSSING bar's volume must be at least vol_m x the median volume of the
                same clock window on the 14 trade dates before (the rvol idea: "a reclaim with volume"); a cross that fails it is no cross.
  orb_vwap_pb   the 09:30 range of `or_min` minutes broken by a tf CLOSE after it ends -> armed that way; then a LIMIT AT the 09:30 VWAP
                (re-priced at every tf close) for the first pullback to it; the first 1-minute bar that comes within `near` ticks of
                the VWAP uses the arm up, filled or not; one arm a day. Structure stop = the range's other edge.
  `also` (every family): at the decision the close must be on the trade's side of that line (a long above it); no line yet = no trade.
  Idea 11 "two anchors agree" = line rth + also globex; idea 14 "London VWAP side" = also london; idea 15 = pdvwap, pdh / pdl / onh / onl,
  week; idea 13 "reclaim with volume" = avwap_flip vol_m; idea 12 = orb_vwap_pb.
REGISTRATION as vwap_touch.py: join_blocks() puts the families into families/blocks.py's BASES and WRAPPED (blocks.py is not edited).
Tests: engine/tests/test_avwap.py."""
from __future__ import annotations

import datetime as dt

import numpy as np

import l2sim as S
from l2sim import Template

TFS = ("1", "5", "15", "30")
LINES = ("rth", "london", "midnight", "globex", "week", "pdvwap", "pdh", "pdl", "onh", "onl")
START = {"rth": 34200, "london": 10800, "midnight": 0, "globex": 0, "week": 0, "pdvwap": 0, "pdh": 0, "pdl": 0, "onh": 34200, "onl": 34200}
RTH = (34200, 57600)                                 # 09:30-16:00 ET
OPEN = 34200
VOL_DAYS, VOL_MIN = 14, 10                           # vol_m: the dates compared, the fewest with a tape (as blocks.blk_rvol)
_MIN: dict = {}                                      # (root, iso) -> the minutes of that session (a small per-process memory)
_KEEP = 40


# ---- the minutes of a session tape ----------------------------------------------------------------------------------------------
def minutes(root: str, iso: str):
    """1-minute bars of trade date `iso`'s Globex day from its tape -> {"sec": start second after 00:00 ET of iso (negative = the evening
    before), "h", "l", "tpv": volume x (h + l + c) / 3, "v"}; None = no tape. The tape opens with the seal of ITS OWN date (module
    docstring). Remembered per process (the last _KEEP dates)."""
    key = (root, iso)
    if key in _MIN:
        return _MIN[key]
    d = S._date(iso)
    t = S.load_tape(iso, root, allow_holdout=S.ALLOW_BP if d <= S.BP_BUILD[1] else S.ALLOW_BT)
    out = None
    if t is not None and len(t.ts):
        k = (t.ts - S.et_ns(d, "00:00")) // S.MIN_NS
        st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
        en = np.concatenate((st[1:], [len(k)]))
        h, lo = np.maximum.reduceat(t.px, st), np.minimum.reduceat(t.px, st)
        c, v = t.px[en - 1], np.add.reduceat(t.size, st).astype(np.float64)
        out = {"sec": (k[st] * 60).astype(np.int64), "h": h, "l": lo, "tpv": v * (h + lo + c) / 3.0, "v": v}
    _MIN[key] = out
    while len(_MIN) > _KEEP:
        _MIN.pop(next(iter(_MIN)))
    return out


EVE0 = -21600                                        # 18:00 ET of the evening before (l2sim EVE_WINDOW)


def evening(root: str, iso: str, since=EVE0):
    """The minutes of trade date `iso` BEFORE 00:00 ET: from 18:00 the evening before (since=EVE0), or every minute the tape holds before
    midnight (since=None: after a holiday the tape starts 30 hours back and holds the holiday session). The only part of today's tape
    ever read."""
    m = minutes(root, iso)
    if m is None:
        return None
    k = (m["sec"] < 0) if since is None else (m["sec"] >= since) & (m["sec"] < 0)
    return {f: x[k] for f, x in m.items()}


def _whole_after(root: str, iso: str):
    """Every minute of session `iso` from 18:00 ET of its evening before (a holiday session ahead of that left out)."""
    m = minutes(root, iso)
    if m is None:
        return None
    k = m["sec"] >= EVE0
    return {f: x[k] for f, x in m.items()}


def _before(day: str, prior: list) -> list:
    out = [str(r["date"]) for r in prior]
    if out and out[-1] >= day:
        raise S.LookAheadError(f"avwap: a prior session {out[-1]} is not before {day}")
    return out


def vol_ref(root: str, dates: list, a: int, b: int):
    """The median volume of the clock window [a, b) (seconds after 00:00 ET, whole minutes) over the last VOL_DAYS `dates`, from the
    minute-volume cache when it holds the date (blocks._mv_file, the rvol block's) and from the date's own tape (sealed by its date)
    otherwise; None with fewer than VOL_MIN dates or a median of 0."""
    from . import blocks as B
    idx, vol = B._mv_file(root)
    ref = []
    for iso in dates[-VOL_DAYS:]:
        if iso in idx:
            i, j = a // 60 - B.MIN0, b // 60 - B.MIN0
            if 0 <= i < j <= B.NMIN:
                ref.append(float(vol[idx[iso]][i:j].sum()))
            continue
        m = minutes(root, iso)
        if m is not None:
            ref.append(float(m["v"][(m["sec"] >= a) & (m["sec"] < b)].sum()))
    if len(ref) < VOL_MIN:
        return None
    med = float(np.median(ref))
    return med if med > 0 else None


# ---- one anchored line of one trade date ----------------------------------------------------------------------------------------
class Line:
    """One line (module docstring) of one trade date, fed the instance's 1-minute bars in order. value() = the line as of the last
    minute fed, or None."""

    def __init__(self, kind: str, root: str, day: str, prior: list, rolls):
        self.kind, self.vv, self.vp, self.fixed, self.on, self.dead = kind, 0.0, 0.0, None, None, False
        self.feed_from = START[kind] if kind in ("rth", "london", "midnight") else None
        dates = _before(day, prior)
        roll = day in rolls
        if kind in ("globex", "week", "pdh", "pdl"):
            parts, since = [], EVE0
            if kind == "week":
                wk = S._date(day).isocalendar()[:2]
                same = [p for p in dates if S._date(p).isocalendar()[:2] == wk]
                cut = [p for p in same + [day] if p in rolls]
                same = [p for p in same if not cut or p >= max(cut)]
                # the week starts 18:00 the evening before its first trade date; a holiday session inside the week counts
                parts = [_whole_after(root, p) if k == 0 else minutes(root, p) for k, p in enumerate(same)]
                if same:
                    since = None                     # today is not the week's first date: every minute of this evening counts
            elif kind in ("pdh", "pdl"):
                pm = minutes(root, dates[-1]) if dates and not roll else None
                if pm is None:
                    self.dead = True
                    return
                r = (pm["sec"] >= RTH[0]) & (pm["sec"] < RTH[1])
                if not r.any():
                    self.dead = True
                    return
                ix = np.flatnonzero(r)
                at = ix[int(np.argmax(pm["h"][ix]))] if kind == "pdh" else ix[int(np.argmin(pm["l"][ix]))]
                parts = [{f: x[at:] for f, x in pm.items()}]
                since = None                         # every minute since the anchor, a holiday session included
            parts.append(evening(root, day, since))
            if any(p is None for p in parts):
                self.dead = True
                return
            for p in parts:
                self.vv += float(p["v"].sum())
                self.vp += float(p["tpv"].sum())
            self.feed_from = 0
        elif kind == "pdvwap":
            pm = minutes(root, dates[-1]) if dates and not roll else None
            r = None if pm is None else (pm["sec"] >= RTH[0]) & (pm["sec"] < RTH[1])
            if r is None or float(pm["v"][r].sum()) <= 0:
                self.dead = True
                return
            self.fixed = float(pm["tpv"][r].sum() / pm["v"][r].sum())
        elif kind in ("onh", "onl"):
            ev = evening(root, day)
            if ev is None:
                self.dead = True
                return
            self.on = [(int(s), float(h), float(lo), float(tp), float(v)) for s, h, lo, tp, v in zip(ev["sec"], ev["h"], ev["l"], ev["tpv"], ev["v"])]

    def _anchor_on(self):
        on, self.on = self.on, None
        if not on:
            self.dead = True
            return
        x = np.array(on)
        at = int(np.argmax(x[:, 1])) if self.kind == "onh" else int(np.argmin(x[:, 2]))
        self.vp, self.vv = float(x[at:, 3].sum()), float(x[at:, 4].sum())
        self.feed_from = OPEN

    def feed(self, m) -> None:
        """One completed 1-minute bar (sec, o, h, l, c, v) of the instance, in order."""
        if self.dead or self.fixed is not None:
            return
        s, h, lo, c, v = m[0], m[2], m[3], m[4], m[5]
        if self.on is not None:
            if s < OPEN:
                self.on.append((int(s), h, lo, v * (h + lo + c) / 3.0, float(v)))
                return
            self._anchor_on()
        if self.feed_from is not None and s >= self.feed_from and v > 0:
            self.vv += v
            self.vp += v * (h + lo + c) / 3.0

    def value(self):
        if self.dead:
            return None
        if self.fixed is not None:
            return self.fixed
        return self.vp / self.vv if self.feed_from is not None and self.vv > 0 else None


# ---- the families -------------------------------------------------------------------------------------------------------------
class _Lines(Template):
    """The shared part: the line and the `also` line of the day, fed every 1-minute bar; the sessions where both exist."""
    DEFAULTS = {"line": "globex", "also": "off"}
    SCHEMA = {"line": ("choice", LINES), "also": ("choice", ("off",) + LINES)}
    SCREEN_TFS = TFS
    FEATURES = ()

    def _start_s(self) -> int:
        return max(START[self.p["line"]], START.get(self.p["also"], 0))

    def fam_filter(self, ids):
        a = self._start_s()
        return [s for s in ids if self.S[s][0] >= 0 and self.S[s][1] > a]

    def fam_day(self, ctx):
        root, prior = ctx.root, self.dl
        self.ln = Line(self.line_kind(), root, self.day, prior, self.ROLLS)
        self.al = None if self.p["also"] == "off" else Line(self.p["also"], root, self.day, prior, self.ROLLS)
        self.mi = 0

    def agrees(self, side: str) -> bool:
        if self.al is None:
            return True
        w = self.al.value()
        return w is not None and (self.C[-1] - w) * (1 if side == "long" else -1) > 0

    def line_kind(self) -> str:
        return self.p["line"]

    def _minute(self, m, w0) -> None:
        """Hook: one minute `m` after it entered the lines; w0 = the line before it, w1 = self.ln.value() after."""

    def _read(self, ctx):
        M = self.M
        for i in range(self.mi, len(M)):
            w0 = self.ln.value()
            self.ln.feed(M[i])
            if self.al is not None:
                self.al.feed(M[i])
            self._minute(M[i], w0)
        self.mi = len(M)

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        self._read(ctx)

    def fam_update(self, ctx):
        self._read(ctx)


class _Touch(_Lines):
    """The limit-at-the-line mechanics of vwap_touch (arm, touch, re-price), on self.target()."""

    def can_enter(self, ctx):
        """The Template's rule, but the family's own resting order does not stand in the way of its re-pricing (vwap_touch)."""
        self._sync(ctx)
        rest, self.orders = self.orders, []
        ok = super().can_enter(ctx)
        self.orders = rest
        return ok

    def touched(self, ctx):
        for r in self.orders:
            ctx.cancel(r[0])                         # an order that is not working any more is left alone by the engine

    def target(self):
        return self.ln.value()

    def place(self, ctx, side, px):
        self._lim(ctx, side, px)                     # no structure level (taught.passes_structure reads this)

    def fam_signal(self, ctx):
        w = self.target()
        keep = [r for r in self.orders if r[0].status != "working"]
        for r in self.orders:
            if r[0].status == "working":
                ctx.cancel(r[0])                     # re-priced at this close (or dropped when the arm is gone)
        self.orders = keep
        if w is None or not self.arm:
            return
        side = "long" if self.arm > 0 else "short"
        if self.agrees(side):
            self.place(ctx, side, w)


class AvwapTouch(_Touch):
    """avwap_touch (module docstring)."""
    DEFAULTS = {**_Lines.DEFAULTS, "away": 160, "near": 3, "max_tr": 3}
    SCHEMA = {**_Lines.SCHEMA, "away": ("int", 2, 400), "near": ("int", 0, 20), "max_tr": ("int", 1, 20)}
    SCREEN_RUN = {"strict_limit": True}

    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.arm = 0

    def _read(self, ctx):
        self._tk = ctx.tick
        self._hit = False
        super()._read(ctx)
        if self._hit:
            self.touched(ctx)

    def _minute(self, m, w0):
        tk = self._tk
        if w0 is not None and m[3] <= w0 + self.p["near"] * tk and m[2] >= w0 - self.p["near"] * tk:
            self.arm, self._hit = 0, True            # the first touch is used up (filled or not)
        w1 = self.ln.value()
        if w1 is not None:
            if m[4] >= w1 + self.p["away"] * tk:
                self.arm = 1
            elif m[4] <= w1 - self.p["away"] * tk:
                self.arm = -1


class OrbVwapPb(_Touch):
    """orb_vwap_pb (module docstring): line = the 09:30 VWAP."""
    DEFAULTS = {"line": "rth", "also": "off", "or_min": 30, "near": 0, "max_tr": 1}          # the line is always the 09:30 VWAP
    SCHEMA = {"line": ("choice", ("rth",)), "also": ("choice", ("off",) + LINES), "or_min": ("choice", (15, 30, 60)), "near": ("int", 0, 20),
              "max_tr": ("int", 1, 5)}
    SCREEN_RUN = {"strict_limit": True}

    def _start_s(self) -> int:
        return max(OPEN, START.get(self.p["also"], 0))

    def line_kind(self) -> str:
        return "rth"                                 # the line is the 09:30 VWAP (not a setting of this family)

    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.arm, self.brk, self.used, self.hi, self.lo = 0, 0, False, None, None

    def _read(self, ctx):
        self._tk = ctx.tick
        self._hit = False
        super()._read(ctx)
        if self._hit:
            self.touched(ctx)

    def _minute(self, m, w0):
        end = OPEN + int(self.p["or_min"]) * 60
        if OPEN <= m[0] < end:
            self.hi = m[2] if self.hi is None else max(self.hi, m[2])
            self.lo = m[3] if self.lo is None else min(self.lo, m[3])
        if self.arm and w0 is not None:
            tk = self._tk * self.p["near"]
            if m[3] <= w0 + tk and m[2] >= w0 - tk:
                self.arm, self.used, self._hit = 0, True, True

    def fam_update(self, ctx):
        super().fam_update(ctx)
        end = OPEN + int(self.p["or_min"]) * 60
        b = (self.M[-1][0] // (self.tf * 60) + 1) * self.tf * 60 if self.M else 0
        if self.brk or self.used or self.hi is None or b <= end:
            return
        c = self.C[-1]
        if c > self.hi:
            self.brk = self.arm = 1
        elif c < self.lo:
            self.brk = self.arm = -1

    def place(self, ctx, side, px):
        self._lim(ctx, side, px, struct=self.lo if side == "long" else self.hi)      # structure stop = the range's other edge


class AvwapFlip(_Lines):
    """avwap_flip (module docstring)."""
    DEFAULTS = {**_Lines.DEFAULTS, "hold": 2, "vol_m": 0.0, "max_tr": 3}     # line globex: the broadest default (the taught lane asks which sessions the defaults trade)
    SCHEMA = {**_Lines.SCHEMA, "hold": ("int", 1, 6), "vol_m": ("float", 0.0, 20.0), "max_tr": ("int", 1, 20)}

    def fam_day(self, ctx):
        super().fam_day(ctx)
        self.pside = self.pend = self.cnt = self.go = 0
        self._prior = [str(r["date"]) for r in self.dl]

    def fam_session(self, ctx, s):
        self.pside = self.pend = self.cnt = self.go = 0          # as port3.VwapFlip: every session starts without a side

    def _vol_ok(self) -> bool:
        if self.p["vol_m"] <= 0:
            return True
        b = (self.M[-1][0] // (self.tf * 60) + 1) * self.tf * 60
        ref = vol_ref(self._cx.root, self._prior, b - self.tf * 60, b)
        return ref is not None and self.V[-1] >= self.p["vol_m"] * ref

    def fam_update(self, ctx):
        super().fam_update(ctx)
        self.go = 0
        if self.sid is None:
            return
        w = self.ln.value()
        if w is None:
            return
        c = self.C[-1]
        sd = 1 if c > w else -1 if c < w else 0
        if not sd:
            return
        if self.pside and sd != self.pside:
            self.pend, self.cnt = (sd, 0) if self._vol_ok() else (0, 0)
        elif self.pend:
            self.cnt += 1
            if self.cnt >= int(self.p["hold"]):
                self.go, self.pend = sd, 0
        self.pside = sd

    def fam_signal(self, ctx):
        if self.go:
            side = "long" if self.go > 0 else "short"
            if self.agrees(side):
                self._mkt(ctx, side)


_WHY_LINE = ("The anchored VWAP is the average price paid by everyone who traded since the anchor; the side that holds it is in profit and "
             "defends it, so its first test holds and a decided cross changes who is in control. Who loses: the traders who fade the line "
             "or hold the wrong side of it.")
FAMILIES = {
    "avwap_touch": (AvwapTouch, {}, False,
                    "avwap_touch: price closes at least `away` ticks from an anchored VWAP line (globex 18:00 / week / yesterday's closing "
                    "VWAP / VWAP anchored at the prior-day or overnight high or low / 09:30 / 03:00 / 00:00) -> a limit AT the line, "
                    "re-priced every tf close, on the side price came from; the first touch uses the arm up; `also` = a second line the "
                    "close must agree with; the sheet's stop and target; flat 15:58 (VWAP hunt 2026-10-20, ideas 11-15)",
                    {"rationale": _WHY_LINE, "complexity": 5,
                     "variants": [{"line": "globex"}, {"line": "week"}, {"line": "pdvwap"}, {"line": "pdh"}, {"line": "pdl"}]}),
    "avwap_flip": (AvwapFlip, {}, False,
                   "avwap_flip: a tf close crosses an anchored VWAP line and the next `hold` closes stay on the new side -> market with "
                   "it; vol_m > 0 = the crossing bar's volume >= vol_m x the median of the same clock window on the 14 dates before; "
                   "`also` = a second line the close must agree with (VWAP hunt 2026-10-20, ideas 11, 13, 14, 15)",
                   {"rationale": _WHY_LINE, "complexity": 4,
                    "variants": [{"line": "rth", "also": "globex", "vol_m": 0.0}, {"line": "globex", "also": "off", "vol_m": 0.0},
                                 {"line": "week", "also": "off", "vol_m": 0.0}, {"line": "rth", "also": "off", "vol_m": 1.0}]}),     # same keys (bp.py blocks)
    "orb_vwap_pb": (OrbVwapPb, {}, False,
                    "orb_vwap_pb: the 09:30 range of or_min minutes broken by a tf close -> a limit AT the 09:30 VWAP for the first "
                    "pullback to it, the way of the break; one arm a day; structure stop = the range's other edge (VWAP hunt 2026-10-20, "
                    "idea 12)",
                    {"rationale": "After the opening range breaks, the first return to the day's average price is where the breakout's "
                                  "buyers add and late sellers are trapped. Who loses: those who fade the break at the VWAP.",
                     "complexity": 5,
                     "variants": [{"or_min": 15}, {"or_min": 30}, {"or_min": 60}]}),
}


def join_blocks() -> None:
    """Put the families into families/blocks.py's BASES and WRAPPED (as vwap_touch): the wrapped class a card runs. Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
