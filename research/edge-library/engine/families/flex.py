"""flex -- THREE ENTRY RULES THE OPEN LAYER ADDS (owner 2026-10-11: "any indicator in any setting, any time window"). Written from the rules below
before any result. NQ, ES and GC (no Level-2 feature: FEATURES = ()), 1 contract, hold_to = 'day' (flat 15:58 ET), the standard exit table.
The nine settings of the open layer (families/_flex.py: an entry window, a day rule, an indicator gate) are on every one of them.

ind_signal -- an INDICATOR CROSSES A LINE.
  * INDICATOR = `ind` of flexind.KINDS_DIR (rsi, price_ema, ema_x, macd, zscore, stoch, roc, cci, vwap_dev), its periods `n` (main), `m`
                (slow: ema_x, macd), `s` (macd signal), computed on the closed tf bars since the restart (00:00 ET; 18:00 for an evening).
  * LINE      = the indicator's centre +/- `lvl` (flexind's table: RSI points beyond 50, ATRs, sigmas ...).
  * EVENT     = `edge` enter: the value crosses above the upper line (+1) / below the lower (-1) at THIS bar's close; exit: it comes back
                out of the lower zone (+1) / the upper zone (-1). No value yet (too few bars) = no event.
  * ENTRY     = `mode` follow: a market order at that close in the event's direction; fade: the opposite side. One trade a session
                (max_tr); the exit cell's stop and target.

win_break -- A RANGE OF ANY WINDOW, broken on a CLOSE.
  * RANGE     = the high and low of the 1-minute bars in [`r_start`, `r_end`) on the Globex-day clock ("HH:MM"). It starts at 00:00 ET or
                later (an evening instance, r_end before 24:00: 18:00 or later): the instance holds its own day's bars only.
  * SIGNAL    = the FIRST tf bar that closes after `r_end` and closes beyond the range: above its high (long) / below its low (short). That
                break is the day's one signal, traded or not (a gate or a window that blocks it blocks the day).
  * ENTRY     = `entry` market: at that close. limit: a LIMIT at the broken edge (the retest) for `wait` minutes (0 = to the pass's last 5
                minutes; follow only). `mode` fade: the opposite side of the break at that close (market only). One trade a session.
  * STOP      = struct stop: follow = the other edge of the range; fade = the break bar's extreme.
  * PASS      = the session pass that holds the first tf close after `r_end` (not its last 5 minutes): the instance runs there only, so
                every entry is that pass's and the card's `session` must be that pass. A break after the pass ends is not traded.

win_bracket -- THE SAME RANGE, A BRACKET.
  * OCO stop entries one tick beyond both edges, placed at `r_end`; the stop = the other edge (struct stop). The pass is the one that
    holds `r_end`; one trade a session.

win_candle -- THE CANDLE OF ANY START, followed (or faded) at its close.
  * CANDLE    = the tf bar that opens at `start` ("HH:MM", a whole multiple of the bar size). Entries are decided at its close; the family's
                one session pass is the pass of that close.
  * SIGNAL    = green -> long, red -> short, a doji none; gates all off at 0: `k` range >= k x ATR(14) of the bars before it, `body_r` body
                >= body_r x its range, `vol_m` volume >= vol_m x the median of the same bar over 14 dates, `body_pts` body >= that many points.
  * ENTRY     = `mode` follow: a market order at the close in its direction; fade: against it. Structure stop = the candle's other extreme.

REGISTRATION as orb830.py: join_blocks() puts the families into families/blocks.py's BASES and WRAPPED once. Tests: engine/tests/test_flex.py.
"""
from __future__ import annotations

import flexind as FI
import l2sim as S
from l2sim import Template, _hms

TFS = ("1", "5", "15", "30")


def _bar_end(st) -> int:
    """Nominal close second (after 00:00 ET of the trade date) of the tf bar that has just closed (call in fam_signal)."""
    step = st.tf * 60
    return (st.M[-1][0] // step + 1) * step


def _clock(txt: str, what: str) -> int:
    try:
        return S.clock_sec(txt if txt.count(":") else f"{txt}:00")
    except Exception as e:                           # noqa: BLE001
        raise ValueError(f"{what}: a clock time HH:MM on the Globex day (got {txt!r}): {e}") from None


def _home(first: int, what: str, at_start: bool = False) -> str:
    """The pass in which a decision at second `first` (after 00:00 ET of the trade date) can place an entry: the pass whose window holds it
    with room (no entry in a pass's last 5 minutes); at_start = a decision AT a pass start is that pass's (a bracket placed by the clock).
    A close AT a pass start belongs to the pass before it. ValueError when no pass can take it."""
    for sid in S.ORDER7:
        a, b = S.SESS[sid]
        if (a <= first if at_start else a < first) and first < b - 300:
            return sid
    raise ValueError(f"{what}: a decision at {_hms(first)} ET is in no session pass, or in its last 5 minutes: no entry is placed there")


# ---- ind_signal ----------------------------------------------------------------------------------------------------------------------
class IndSignal(Template):
    """ind_signal (module docstring)."""
    DEFAULTS = {"ind": "rsi", "n": 14, "m": 26, "s": 9, "lvl": 20.0, "edge": "enter", "mode": "follow", "max_tr": 1}
    SCHEMA = {"ind": ("choice", FI.KINDS_DIR), "n": ("int", 1, 500), "m": ("int", 1, 500), "s": ("int", 1, 500), "lvl": ("float", 0.0, 1000.0),
              "edge": ("choice", ("enter", "exit")), "mode": ("choice", ("follow", "fade"))}
    SCREEN_TFS = TFS
    FEATURES = ()
    WARM = 1                                         # the indicator itself says when it has a value

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        FI.make(self.p["ind"], self.p["n"], self.p["m"], self.p["s"])

    def fam_day(self, ctx):
        p = self.p
        self.ind = FI.make(p["ind"], p["n"], p["m"], p["s"])

    def fam_update(self, ctx):
        self.ind.update(self.O[-1], self.H[-1], self.L[-1], self.C[-1], self.V[-1], self.vw() if self.p["ind"] == "vwap_dev" else None)

    def fam_signal(self, ctx):
        ev = FI.event(self.ind, float(self.p["lvl"]), self.p["edge"])
        if ev:
            self._mkt(ctx, "long" if (ev > 0) == (self.p["mode"] == "follow") else "short")


# ---- the range families ----------------------------------------------------------------------------------------------------------------
class _Window(Template):
    """The shared part of win_break and win_bracket: the range [r_start, r_end) and its pass."""
    DEFAULTS = {"r_start": "09:30", "r_end": "09:45", "max_tr": 1}
    SCHEMA = {"r_start": ("str",), "r_end": ("str",)}
    SCREEN_TFS = TFS
    FEATURES = ()
    AT_END = False                                   # True: the decision is AT r_end (a bracket), not at the first tf close after it

    def _plan(self) -> tuple:
        """(range start, range end, home pass) from the inputs; ValueError for a window that cannot trade."""
        p = self.p
        name = getattr(type(self), "BASE", type(self).__name__)
        a, b = _clock(p["r_start"], "r_start"), _clock(p["r_end"], "r_end")
        if b <= a:
            raise ValueError(f"r_end {p['r_end']!r} is not after r_start {p['r_start']!r}")
        step = int(p["tf"]) * 60
        first = b if self.AT_END else (b // step + 1) * step
        home = _home(first, f"{name} r_end {p['r_end']}", at_start=self.AT_END)
        if a < 0 and home != "eve":
            raise ValueError(f"{name}: r_start {p['r_start']!r} is the evening before: only an evening instance holds those bars "
                             f"(r_end {p['r_end']!r} is in the {home} pass)")
        return a, b, home

    def fam_filter(self, ids):
        return [s for s in ids if s == self._plan()[2]]

    def fam_day(self, ctx):
        self.r = None
        self.used = False
        self.ra, self.rb, _ = self._plan()


class WinBreak(_Window):
    """win_break (module docstring)."""
    DEFAULTS = {**_Window.DEFAULTS, "mode": "follow", "entry": "market", "wait": "0"}
    SCHEMA = {**_Window.SCHEMA, "mode": ("choice", ("follow", "fade")), "entry": ("choice", ("market", "limit")),
              "wait": ("choice", ("0", "5", "15", "30"))}

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if self.p["mode"] == "fade" and self.p["entry"] == "limit":
            raise ValueError("win_break: a fade is a market entry (a limit at the broken edge is the retest of a follow)")

    def fam_signal(self, ctx):
        p = self.p
        if self.used or _bar_end(self) <= self.rb:
            return
        if self.r is None:
            self.r = self.rng(self.ra, self.rb)
            if self.r is None:
                return
        hi, lo = self.r
        c = self.C[-1]
        brk = "long" if c > hi else "short" if c < lo else None
        if brk is None:
            return
        self.used = True                             # the FIRST break is the day's one signal, traded or not
        if p["mode"] == "fade":
            side = "short" if brk == "long" else "long"
            self._mkt(ctx, side, struct=self.L[-1] if side == "long" else self.H[-1])
            return
        far = lo if brk == "long" else hi
        if p["entry"] == "limit":
            w = int(p["wait"])
            self._lim(ctx, brk, hi if brk == "long" else lo, struct=far, ttl=max(1, w // self.tf) if w else None)
        else:
            self._mkt(ctx, brk, struct=far)


class WinBracket(_Window):
    """win_bracket (module docstring)."""
    AT_END = True

    def fam_times(self):
        return [_hms(self._plan()[1])] if self.sessions() else []

    def fam_time(self, ctx, sec):
        a, b, home = self._plan()
        if sec != b or self.sid != home or not self.can_enter(ctx):
            return
        r = self.rng(a, b)
        if r is None:
            return
        hi, lo = r
        t = ctx.tick
        self._arm(ctx, [("long", hi + t, lo, None), ("short", lo - t, hi, None)])


class WinCandle(Template):
    """win_candle (module docstring)."""
    DEFAULTS = {"start": "09:30", "k": 0.0, "body_r": 0.0, "vol_m": 0.0, "body_pts": 0.0, "mode": "follow", "max_tr": 1}
    SCHEMA = {"start": ("str",), "k": ("float", 0, 10), "body_r": ("float", 0, 1), "vol_m": ("float", 0, 50), "body_pts": ("float", 0, 1000),
              "mode": ("choice", ("follow", "fade"))}
    WARM = 1                                         # the signal is one bar: an evening restarts the bars at 18:00
    SCREEN_TFS = TFS
    FEATURES = ()

    def _plan(self) -> tuple:
        """(the candle's open second, the second its close decides at, home pass)."""
        a = _clock(self.p["start"], "start")
        step = int(self.p["tf"]) * 60
        if a % step:
            raise ValueError(f"start {self.p['start']!r} is not a whole {self.p['tf']}-minute bar: the candle is one tf bar")
        return a, a + step, _home(a + step, f"win_candle start {self.p['start']}")

    def fam_filter(self, ids):
        return [s for s in ids if s == self._plan()[2]]

    def fam_signal(self, ctx):
        a, b, _ = self._plan()
        if _bar_end(self) != b:
            return
        p = self.p
        k = float(p["k"])
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        if c == o or (k > 0 and (not self.atr_p or h - l < k * self.atr_p)):
            return
        body = abs(c - o)
        if body < float(p["body_r"]) * (h - l) or body < float(p["body_pts"]):
            return
        vm = float(p["vol_m"])
        if vm > 0:
            rv = getattr(self, "blk_rvol", None)
            if rv is None:
                raise RuntimeError("win_candle vol_m needs the Blocks mixin (blk_rvol): run the wrapped class (families.blocks.WRAPPED)")
            sig = rv()
            if sig is None or sig[0] < vm * sig[1]:
                return
        up = c > o
        side = "long" if up == (p["mode"] == "follow") else "short"
        self._mkt(ctx, side, struct=l if side == "long" else h)


FAMILIES = {
    "ind_signal": (IndSignal, {}, False,
                   "ind_signal: an indicator (rsi, price_ema, ema_x, macd, zscore, stoch, roc, cci, vwap_dev; any period) crosses its line "
                   "(centre +/- lvl) at a tf bar's close -> a market entry in the crossing's direction (follow) or against it (fade); "
                   "edge exit = the value comes back out of the zone; one trade a session",
                   {"rationale": "A stretched or turning indicator marks a bar where the crowd has just acted one way: following it rides the "
                                 "move that others then chase, and fading it sells to the late buyers of an extreme.",
                    "complexity": 6,
                    "variants": [{"ind": "rsi", "n": 14, "lvl": 20.0, "mode": "fade"}, {"ind": "zscore", "n": 20, "lvl": 2.0, "mode": "fade"},
                                 {"ind": "ema_x", "n": 9, "m": 21, "lvl": 0.0, "mode": "follow"}]}),
    "win_break": (WinBreak, {}, False,
                  "win_break: the range of the 1-minute bars in [r_start, r_end) (any window of the day) is broken by a tf bar's CLOSE after "
                  "r_end -> a market entry with the break (follow) or against it (fade), or a limit at the broken edge (retest); one trade "
                  "a session in the pass of the break",
                  {"rationale": "A range built in a quiet window shows where the first reaction of the day stopped; a close beyond it after "
                                "the window ends is the first proof that one side had to give way, and the stop at the other edge puts "
                                "the loss where that reading is wrong.",
                   "complexity": 6,
                   "variants": [{"r_start": "09:30", "r_end": "09:45"}, {"r_start": "09:30", "r_end": "10:00"}, {"r_start": "09:30", "r_end": "10:30"}]}),
    "win_bracket": (WinBracket, {}, True,
                    "win_bracket: the range of [r_start, r_end) (any window) -> OCO stop entries one tick beyond both edges, placed at "
                    "r_end; one trade a session in the pass of r_end",
                    {"rationale": "A range that the market built in a quiet window is a coiled spring: resting stop orders beyond both "
                                  "edges ride whichever side the next burst of orders breaks, and trap the other side's late entries.",
                     "complexity": 5,
                     "variants": [{"r_start": "09:30", "r_end": "09:45"}, {"r_start": "09:30", "r_end": "10:00"}, {"r_start": "09:30", "r_end": "10:30"}]}),
    "win_candle": (WinCandle, {}, False,
                   "win_candle: the tf candle that opens at `start` (any clock time, a whole bar) is followed (or faded) at its close: "
                   "green long, red short; optional size gates, all off at 0: range >= k x ATR, body >= body_r of its range, volume >= "
                   "vol_m x the median of the same bar over 14 dates, body >= body_pts points; one trade a session",
                   {"rationale": "A candle that opens a session or a data release is where the news or the first orders are priced: its "
                                 "direction is the first read of who had to act, and a large, one-sided or loud candle shows the buyers "
                                 "or sellers who could not wait.",
                    "complexity": 5,
                    "variants": [{"start": "09:30", "k": 0.0}, {"start": "09:30", "k": 1.0}, {"start": "09:30", "k": 1.5}]}),
}


def join_blocks() -> None:
    """Put the families into families/blocks.py's BASES and WRAPPED (module docstring, REGISTRATION). Idempotent."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
