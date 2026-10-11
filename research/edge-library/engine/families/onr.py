"""onr -- the OVERNIGHT-BIAS OPENING RANGE BREAKOUT entry (Matteo Conti, IQCapital video A0G14JYYVTk, "strategy 3"), written from the
video's rule before any result. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day'.

    onr_orb   bar-based 15 (the video's bars)   ONE pass: the nyam pass, stretched to 09:30-15:30 inside this family (see SESSION)

THE RULE (fixed here, before any run; every time New York, his Central + 1 hour):
  * OVERNIGHT RANGE = the high and the low of the 1-minute bars from `ov_from` (01:00 = midnight Central, what his chart draws; 00:00 =
    his whiteboard's "11 pm Central") to 09:30. Cut in three equal parts.
  * BIAS at the 09:30 open (the open of the first 1-minute bar from 09:30; no bar within 5 minutes = no trade today):
        open strictly above low + 2/3 of the range  -> LONG days      open strictly below low + 1/3 of the range -> SHORT days
        anything else (the middle third, a boundary, an open on a flat range) -> no trade today.
  * OPENING RANGE = the high and the low of the 1-minute bars 09:30-09:45 (his first 15-minute bar).
  * SIGNAL, read at a tf close, never earlier than `earliest` (10:00 = the first bar after the range; 10:30 = his chart's "after 9:30
    Central"): LONG day = the bar CLOSES strictly above the opening range high; SHORT day = strictly below its low; AND Wilder's ADX(14) of
    the tf bars since 00:00 ET, read at that same bar, is strictly above `adx_min` (20; rising or falling does not matter). The order is
    a market order placed at that close: it fills at the next bar's open. A close beyond the range on the OTHER side, a dip into the middle
    third, or a close beyond the range with ADX at or under `adx_min` is no signal and does not end the day: the next qualifying close trades.
  * ONE trade a day (max_tr 1, one pass). EXITS: the stop is `k` x A from the fill (a structure level handed to the Template: the signal
    close -/+ k x A, brackets re-priced to the fill), the target is the sheet's tgt_r x the stop (3 in the video), out at 15:30 if neither.
  * A = the SIMPLE AVERAGE over the last 15 sessions of the daily ATR(14), over the daily bars BEFORE the trade date (his: "a 15 daily
    moving average of ATR ... not an ATR with a look-back of 15, traditional ATR"). Needs 29 prior daily bars; fewer = no trade.

SESSION. The engine runs a bar family once per session pass. This family trades ONE pass, `nyam`, whose window it stretches to
09:30-15:30 (fam_sessions), so the day holds exactly one decision stream: no boundary between two passes loses a bar. Entries stop 5
minutes before the pass ends (the Template's rule): the last signal bar closes at 15:15. The other passes trade nothing (fam_filter).
A trade is flattened at 15:30 by the family (fam_time); the day's 15:58 flatten never comes into play.

KNOWN DIFFERENCES FROM THE VIDEO (the sheet lists them under not_run): the ADX runs over the 15-minute bars since 00:00 ET of the day
(the Template resets its bars daily; his is a continuous series); A uses the engine's daily bars (Globex day) where his sessions run
00:00-16:00 Central; the stop distance is measured from the signal close and re-priced to the fill, so it is the same dollars from the
fill; costs are the engine's own.

REGISTRATION as noise.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED once, so blocks.py stays byte for
byte as it was (its hash is part of every store and lock). Tests: engine/tests/test_onr.py."""
from __future__ import annotations

from l2sim import Template, _hms

TFS = ("5", "15", "30")
OPEN_S = 34200                                      # 09:30 ET, seconds after 00:00 ET
OR_END_S = OPEN_S + 15 * 60                         # the opening range: 09:30-09:45
PASS_END_S = 55800                                  # 15:30 ET: the family's pass ends and a trade is flattened here
OPEN_TOL_S = 300                                    # the 09:30 open's first minute bar may start at most 5 minutes late
OV_FROM_S = {"01:00": 3600, "00:00": 0}
EARLIEST_S = {"10:00": 36000, "10:30": 37800}       # the first signal-bar CLOSE allowed (ET seconds)
A_DAYS = 15                                         # the sessions averaged
ATR_N = 14


class OnrOrb(Template):
    """onr_orb (module docstring). State per day: bias (+1 long day / -1 short day / 0 none, set once at the first signal read), the
    opening range (hi, lo), A."""
    DEFAULTS = {"k": 0.3, "adx_min": 20.0, "ov_from": "01:00", "earliest": "10:00", "max_tr": 1}
    SCHEMA = {"k": ("float", 0.05, 3.0), "adx_min": ("float", 0.0, 100.0), "ov_from": ("choice", tuple(OV_FROM_S)),
              "earliest": ("choice", tuple(EARLIEST_S)), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("15",)
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_sessions(self) -> dict:
        return {"nyam": (OPEN_S, PASS_END_S)}

    def fam_day(self, ctx):
        self.bias = None            # None = not read yet; 0 = no trade today; +1 / -1
        self.orng = None            # the opening range (hi, lo)
        self.a = None               # A: the 15-session average of the daily ATR(14)
        self.adx = None             # the ADX read at the last signal evaluation (for tests)

    def fam_times(self):
        return [_hms(PASS_END_S)]

    def fam_time(self, ctx, sec):
        if sec == PASS_END_S:
            self._cancel(ctx)
            ctx.flatten("time")

    # ---- A
    def a_avg(self):
        """The simple average of the last 15 daily ATR(14) values (Wilder), over the daily bars before today; None below 29 bars."""
        if self.a is None and len(self.dl) >= 1 + 2 * ATR_N:
            dl = self.dl
            trs = [max(dl[i]["h"] - dl[i]["l"], abs(dl[i]["h"] - dl[i - 1]["c"]), abs(dl[i]["l"] - dl[i - 1]["c"])) for i in range(1, len(dl))]
            a = sum(trs[:ATR_N]) / ATR_N
            atrs = [a]
            for x in trs[ATR_N:]:
                a = (a * (ATR_N - 1) + x) / ATR_N
                atrs.append(a)
            if len(atrs) >= A_DAYS:
                self.a = sum(atrs[-A_DAYS:]) / A_DAYS
        return self.a

    # ---- bias and range
    def read_bias(self):
        """+1 / -1 / 0 from the overnight range and the 09:30 open, or None while the open is not known."""
        o = self.mo(OPEN_S)
        first = next((m[0] for m in self.M if m[0] >= OPEN_S), None)
        if o is None or first is None:
            return None
        if first - OPEN_S > OPEN_TOL_S:
            return 0
        r = self.rng(OV_FROM_S[self.p["ov_from"]], OPEN_S)
        if r is None:
            return 0
        hi, lo = r
        if hi <= lo:
            return 0
        third = (hi - lo) / 3.0
        if o > lo + 2.0 * third:
            return 1
        if o < lo + third:
            return -1
        return 0

    def fam_signal(self, ctx):
        step = self.tf * 60
        end = (self.M[-1][0] // step + 1) * step                     # the nominal close second of the tf bar that has just closed
        if end <= OR_END_S or end < EARLIEST_S[self.p["earliest"]]:
            return
        if self.bias is None:
            self.bias = self.read_bias()
        if not self.bias:
            return
        if self.orng is None:
            self.orng = self.rng(OPEN_S, OR_END_S)
            if self.orng is None:
                self.bias = 0
                return
        hi, lo = self.orng
        c = self.C[-1]
        side = 1 if c > hi else -1 if c < lo else 0
        if side == 0 or side != self.bias:
            return
        from . import blocks                                         # adx_last lives in blocks.py (imported lazily: this module loads after it)
        self.adx = blocks.adx_last(self.H, self.L, self.C)
        if self.adx is None or not self.adx > self.p["adx_min"]:
            return
        a = self.a_avg()
        if not a or a <= 0:
            return
        d = self.p["k"] * a
        self._mkt(ctx, "long" if side > 0 else "short", struct=c - d if side > 0 else c + d)


FAMILIES = {
    "onr_orb": (OnrOrb, {}, False,
                "onr_orb: the 09:30 open in the top / bottom third of the 01:00-09:30 ET overnight range sets a long-only / short-only day "
                "(the middle third: no trade); a 15-minute close beyond the 09:30-09:45 opening range on that side with ADX(14) above "
                "adx_min -> market entry at the next bar's open; one trade a day; stop k x A (A = the 15-session average of the daily "
                "ATR(14)) from the fill, target the sheet's multiple of it, flat 15:30. Conti's overnight-bias ORB (A0G14JYYVTk)",
                {"rationale": "The overnight session discovers a price before the cash open; when the open lands in the top or bottom third "
                              "of that range and the opening range then breaks the same way on a trending day, the side that already holds "
                              "the overnight push is the one the day's money follows.",
                 "complexity": 8,
                 "variants": [{"k": k} for k in (0.2, 0.3, 0.4)]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as noise.py does): the wrapped class a card runs, importable by name."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
