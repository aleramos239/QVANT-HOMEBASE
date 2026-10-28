"""fvg_tap_disp -- A HIGHER-TIMEFRAME FAIR VALUE GAP, TAPPED, THEN A 1-MINUTE DISPLACEMENT CLOSE OUT OF IT (the owner's idea of
2026-10-27), written from his words before any result: "take trades when we enter a fvg and bounce or reject off it with displacement,
lets start with 15 minute fvgs, we are on the 1 minute, if we inverse the fvg so the 15 minute candle closes above or below the fvg ...
then no trade, but if the 1 minute candle [closes] above or below the fvg with displacement we enter ... i want to try requiring the
displacement to be above the fvg and another that allows the displacement to also be inside the fvg". No Level-2 feature is read:
NQ, ES and GC, 1 contract, hold_to = 'day' (flat 15:58 ET). Run it on tf 1 (the trade bar); the gaps are built on `gtf` minutes.
tf 5 (the owner, 2026-10-27: "now test 5 minute displacement and 1 hour fvg"): the tap and the displacement candle are 5-minute
bars (ATR = the 5-minute ATR14); everything below that says "1-minute bar" then reads "trade bar".

THE RULE (fixed here, before any run):
  * THE GAP: three `gtf`-minute bars (15 = the owner's), built from the day's 1-minute bars on the ET clock grid. UP gap: bar 3's low
    above bar 1's high -> the zone bar 1's high (bottom) .. bar 3's low (top). DOWN the mirror. Known at bar 3's close.
  * INVERSED = DEAD: a `gtf` bar that closes below an up gap's bottom (above a down gap's top) kills it for the day.
  * THE TAP: a 1-minute bar trades into a live gap (an up gap: its low at or below the top). The tap stays open until a 1-minute bar
    closes back out on the trade side (above an up gap's top); then a new tap is needed.
  * THE TRIGGER, during a tap (the tapping bar itself counts): a 1-minute bar that moves the gap's way with DISPLACEMENT -- its body
    (close - open, up gap) at least k x ATR14 of the 1-minute bars before it (disp = atr) -- and closes
        close = out   beyond the gap (above an up gap's top): the owner's first version
        close = in    inside the gap or beyond it (at or above an up gap's bottom): the owner's second version
    -> a MARKET entry at that close, with the gap (an up gap is bought). One trade per gap: a traded gap is spent.
    When two gaps trigger on the same bar the newest gap is traded.
  * disp = wick (the owner, 2026-10-27: "make the 1 minute candle close above or below the previous candles wick with 2x the body
    size"): the displacement bar closes beyond the PREVIOUS 1-minute bar's wick (above its high for an up gap, below its low for a down
    gap) and its body, the gap's way, is at least k x the previous bar's body (k 2 = the owner's). Replaces the ATR test.
  * THE OWN STOP (stop_mode own / struct): the far end of the tap -- the lowest low (up gap) from the tap's first bar through the trigger
    bar. hm40 also runs ATR stops (ATR14 of the 1-minute bars).
  * WINDOW: ONE instance `start` -> 15:58 (fvg_odir's way); entries `start` .. 15:00 (start 09:30, or 00:00 = the owner's "no window
    to trade, trade until 3pm", 2026-10-27; or 18:00 = the owner's "from 6pm to 3pm flat at 4pm": the evening of the day before
    is the same held segment, the bars and gaps run on through midnight); gaps are built from every 1-minute bar of the trade
    date the engine replays (from 00:00 ET), so an overnight gap counts. max_tr = trades a day (one position at a time).

MY PICKS, NOT THE OWNER'S WORDS (he may change each): displacement = body >= k x the 1-minute ATR14 (k is the main setting); the stop
under the tap's low; market at the trigger close; entries 09:30-15:00; overnight gaps count; a gap trades once.

NO LOOK-AHEAD: a gap is known only after its third `gtf` bar has closed; a 1-minute trigger is read at its own close, against the ATR of
the bars before it; inversion is read at a `gtf` close after that minute's trigger check (a bar that closes inside/above cannot also
close below the bottom).

Tests: engine/tests/test_fvg_tap_disp.py."""
from __future__ import annotations

from l2sim import Template

OPEN, LAST, END_S = 34200, 54000, 57480     # 09:30, 15:00, 15:58 ET, seconds after 00:00


class FvgTapDisp(Template):
    """fvg_tap_disp (module docstring). Per day: gaps = [side, top, bot, tap_extreme | None, spent], HB = closed gtf bars (h, l, c)."""
    DEFAULTS = {"k": 1.0, "close": "out", "gtf": 15, "max_tr": 3, "disp": "atr", "start": "09:30"}
    SCHEMA = {"k": ("float", 0.0, 10.0), "close": ("choice", ("out", "in")), "gtf": ("int", 1, 240),
              "disp": ("choice", ("atr", "wick")), "start": ("choice", ("09:30", "00:00", "18:00"))}
    SCREEN_TFS = ("1", "5")
    ONE_INSTANCE_PASSES = ("nyam", "mid", "pm")
    FEATURES = ()

    def __init__(self, params=None):
        super().__init__(params)
        if self.p["start"] == "18:00":
            self.S["t"] = (-21600, END_S)           # the Template refuses a window across 00:00 in its setup, so it is widened after it

    def fam_sessions(self):
        a = {"09:30": OPEN, "00:00": 0, "18:00": -21600}[self.p["start"]]
        return {"t": (a, -60 if a < 0 else END_S)}      # 18:00: set up as a HELD evening (one segment 18:00 -> 16:10), see __init__

    def fam_filter(self, ids):
        return ["t"] if "nyam" in ids else []

    def fam_day(self, ctx):
        self.gaps, self.HB, self.sig = [], [], None

    def fam_update(self, ctx):
        self.sig = None
        s = self.M[-1][0]                                                      # the last 1-minute bar: the gtf clock
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]            # the trade bar (tf 1 or 5): tap + displacement
        a, k = self.atr_p, self.p["k"]
        if self.p["disp"] == "wick":
            po, ph, pl, pc = (self.O[-2], self.H[-2], self.L[-2], self.C[-2]) if len(self.C) > 1 else (None,) * 4
        hits = []
        for g in self.gaps:
            sd, top, bot, ext, spent = g
            if spent:
                continue
            near, far = (top, bot) if sd > 0 else (bot, top)
            if ext is None and (l - near if sd > 0 else near - h) <= 0:
                ext = l if sd > 0 else h                                       # the tap starts
            if ext is None:
                continue
            g[3] = ext = min(ext, l) if sd > 0 else max(ext, h)
            if self.p["disp"] == "wick":
                disp = po is not None and (c - o) * sd > 0 and (c - (ph if sd > 0 else pl)) * sd > 0 \
                    and (c - o) * sd >= k * abs(pc - po)
            else:
                disp = a is not None and (c - o) * sd >= max(k * a, 1e-9)
            closed = (c - near) * sd > 0 if self.p["close"] == "out" else (c - far) * sd >= 0
            if disp and closed:
                hits.append(g)
            elif (c - near) * sd > 0:
                g[3] = None                                                    # closed back out without displacement: the tap is over
        if hits:
            g = hits[-1]                                                       # the newest gap
            self.sig = ("long" if g[0] > 0 else "short", g[3], hits)
        step = int(self.p["gtf"]) * 60
        if (s + 60) % step == 0:
            self._htf_close(s + 60 - step)

    def _htf_close(self, start):
        xs = [m for m in self.M if m[0] >= start]
        h, l, c = max(m[2] for m in xs), min(m[3] for m in xs), xs[-1][4]
        for g in self.gaps:                                                    # inversion kills the gap
            if (g[0] > 0 and c < g[2]) or (g[0] < 0 and c > g[1]):
                g[4] = True
        self.HB.append((h, l, c))
        if len(self.HB) >= 3:
            (h1, l1, _), _, (h3, l3, _) = self.HB[-3:]
            if l3 > h1:
                self.gaps.append([1, l3, h1, None, False])
            elif h3 < l1:
                self.gaps.append([-1, l1, h3, None, False])

    def fam_signal(self, ctx):
        if self.sig is None or (ctx.now_ns - self.t0) // 1_000_000_000 > LAST:
            return
        side, struct, hits = self.sig
        if self._mkt(ctx, side, struct=struct) is not None:
            for g in hits:
                g[4] = True                                                    # a traded gap is spent


ENTRY_WINDOWS = {"fvg_tap_disp": (-21600, LAST + 59)}     # start 18:00, 00:00 or 09:30

FAMILIES = {
    "fvg_tap_disp": (FvgTapDisp, {}, False,
                     "fvg_tap_disp: a 15-minute fair value gap (gtf) is tapped by a 1-minute bar; a 1-minute displacement bar (body >= k x "
                     "1-minute ATR14) that closes beyond the gap (close out) or inside / beyond it (close in) -> market with the gap; a gtf "
                     "close through the gap (inversion) kills it; own stop = the tap's far end; ONE instance 09:30-15:58, entries to 15:00",
                     {"rationale": "A higher-timeframe gap marks unfilled orders; when price returns into it and a strong 1-minute candle "
                                   "pushes back out, those orders are defending it, and the traders who sold into the gap are trapped "
                                   "on the wrong side.",
                      "complexity": 5,
                      "variants": [{"k": 1.0}, {"k": 1.5}, {"k": 2.0}]}),
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
