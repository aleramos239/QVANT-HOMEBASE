"""orb830 -- the 08:30 ET data-release candle and range rules the owner tested by hand on 2026-10-10, kept as two toolkit families so they are
taken from the toolkit and never built again. No Level-2 feature is read (FEATURES = ()): NQ, ES and GC, 1 contract, hold_to = 'day' (flat
15:58 ET). Every number and rule below is the one that produced the stored tables of that day (research/edge-library/manual_lane/).

orb_close -- the opening range, broken on a CLOSE.
  * RANGE      = the high and low of the first `or_min` minutes (5 | 15 | 30 | 60) from `start`: 08:30 ET (default;
                 the US data release; ONE session 08:30-11:00, id "pre", the engine's own 08:25-09:30 window replaced for this family only, so
                 entries stop 5 minutes before 11:00) or 09:30 ET (NY sessions nyam / mid / pm).
  * SIGNAL     = the first tf bar that closes after the range and closes above its high (long) / below its low (short); dir = both | long |
                 short. One trade a session (max_tr 1).
  * ENTRY      = `market`: a market order at that close. `limit`: a LIMIT rests AT the broken edge (the retest; a buy at the range high after a
                 close above) for `wait` minutes (0 | 5 | 15 | 30; 0 = to the session's last 5 minutes); the signal is used up whether or not it fills.
  * STOP       = the exit cell's, or -- the owner's "stop at the range" -- stop_mode "struct" = the OTHER side of the range (the family's own
                 exit table, `unit_exits`: struct x the six standard targets; `exits: "own"` in a spec file).
  * VWAP RULE  = `vwap` off (default) | on | first: long only when the signal close is ABOVE, short only when BELOW the VWAP anchored at 16:00 ET of
                 the PRIOR session, read at the signal's close. on = a break against it is no signal, the next break may trade; first = the first
                 break decides the day (against it: no trade). `vwap_tf` 0 = the VWAP of every print; 15 = of 15-minute bars (hlc3 x volume) as a
                 chart draws it, the last COMPLETED bar's value (no look-ahead). A roll day (the two tapes are different contracts) has no VWAP
                 and does not trade. BUILD DAYS ONLY (to 2025-06-30): on a later date it raises, it never trades silently.

open_candle -- the candle that opens at `start` (08:30 ET default), followed at its close.
  * START      = 0830 (default: the US data release; ONE session 08:30-11:00, id "pre"), 0200 (the ICT "London open" killzone) or 0300 (the
                 London cash open, 08:00 UK): ONE session start-08:25, id "london" (the engine's own 03:00-08:25 window replaced for this
                 family only). Entries are the one candle; the trade runs to its stop / target or the day's flat 15:58 ET (`exit_bars` N =
                 a time stop after N tf bars, a limit key).
  * SIGNAL     = the `start` ET candle (the first tf bar of that session) closes up (long) or down (short); a doji is no
                 signal. Entry = a market order at that close; the structure stop (stop_mode struct) is the candle's other extreme; one trade a
                 session. (The 09:30 candle and the library's own session opens are the library's first_bar_mom, not this family.)
  * GATES      = every one off at 0 (no displacement): `k` range >= k x ATR(14) of the bars before the candle (A), `body_r` body |close - open|
                 >= body_r x the range (B), `vol_m` the candle's volume >= vol_m x the median of the same clock bar on the 14 dates before (D, the
                 rvol block's own reference, 10 of 14 dates needed), `body_pts` body >= that many points (E). All that are set must hold.

REGISTRATION. families/__init__.py picks this module up by itself (FAMILIES below); join_blocks() puts both families into families/blocks.py's BASES
and WRAPPED, as noise.py does: blocks.py, round1.py, port2.py and l2sim.py stay byte for byte as they were, so no earlier store or lock is marked
"written by other code". Tests: engine/tests/test_orb830.py.
"""
from __future__ import annotations

import numpy as np

import l2sim as S
from l2sim import Template, _hms

OPEN = 34200                                        # 09:30 ET, seconds after 00:00
RELEASE = 30600                                     # 08:30 ET
NY = ("nyam", "mid", "pm")
END_0830 = 39600                                    # the 08:30 session's window ends 11:00 ET
LONDON_END = 30300                                  # the 02:00 / 03:00 candle sessions end 08:25 ET (the engine's own london end)
EVE_END = -60                                       # the 18:00 / 20:00 candle sessions end 23:59 ET of the evening before (the engine's own eve end)
LAST_BUILD_DAY = "2025-06-30"                       # the 16:00 VWAP reads the prior session's tape: the build switch opens to here only
TFS = ("1", "5", "15")
STRUCT_TGT_R = (0.0, 0.5, 0.75, 1.0, 2.0, 3.0)      # the standard targets: none, then x the stop
LOW_TGT_R = (0.25, 0.33, 0.4, 0.5)                  # exits "own_low" (owner 2026-10-12, a prop-firm win rate): targets UNDER the standard 0.5 x the stop

# ---- the 16:00 anchored VWAP -------------------------------------------------------------------------------------------------------
_VW16: dict = {}                                    # (root, trade date, tf) -> VWAP at each minute boundary 08:30 .. 11:01, or None


def vwap16_series(root: str, iso: str, prior_iso: str, tf: int = 0):
    """The volume-weighted average price of every print from 16:00 ET of the PRIOR session date to each minute boundary of the trade date from
    08:30 to 11:01 ET (index (sec - 30600) // 60; a print AT the boundary is not in it) -> array, or None when the prior or the trade date has no
    tape, or the two tapes are different contracts (a roll day: the prices are not comparable). The prior session's tape ends at 17:00 ET; the
    trade date's starts at 18:00 ET the evening before. tf > 0: the VWAP of tf-MINUTE BARS on the clock grid, sum(hlc3 x volume) / sum(volume)
    over the bars COMPLETED by the boundary. A trade date after 2025-06-30 raises (the build switch is the only one wired)."""
    import datetime as dt
    key = (root, iso, tf)
    if key in _VW16:
        return _VW16[key]
    if iso > LAST_BUILD_DAY:
        raise RuntimeError(f"orb_close vwap: {iso} is after {LAST_BUILD_DAY}: the 16:00 VWAP reads the prior session's tape and is wired "
                           "for the build days only (the test switch cannot open a build day)")
    d, p = dt.date.fromisoformat(iso), dt.date.fromisoformat(prior_iso)
    tp = S.load_tape(p, root, allow_holdout=S.ALLOW_BP)
    td = S.load_tape(d, root, allow_holdout=S.ALLOW_BP)
    out = None
    if tp is not None and td is not None and len(tp.ts) and len(td.ts) and tp.contract == td.contract:
        lo = int(np.searchsorted(tp.ts, S.et_ns(p, "16:00"), side="left"))
        grid = S.et_ns(d, "00:00") + np.arange(RELEASE, END_0830 + 61, 60, dtype=np.int64) * S.NS
        if tf <= 0:
            p0 = float((tp.px[lo:] * tp.size[lo:]).sum())
            v0 = float(tp.size[lo:].sum())
            cpv = np.concatenate([[0.0], np.cumsum(td.px * td.size)])
            cv = np.concatenate([[0.0], np.cumsum(td.size, dtype=np.float64)])
            idx = np.searchsorted(td.ts, grid, side="left")
            if v0 > 0:
                out = (p0 + cpv[idx]) / (v0 + cv[idx])
        else:
            w = tf * 60 * S.NS                      # UTC offsets are whole hours: ET quarter hours are UTC's too
            ts = np.concatenate([tp.ts[lo:], td.ts])
            px = np.concatenate([tp.px[lo:], td.px])
            sz = np.concatenate([tp.size[lo:], td.size]).astype(np.float64)
            k = ts // w
            st = np.flatnonzero(np.concatenate([[True], k[1:] != k[:-1]]))
            en = np.concatenate([st[1:], [len(k)]]) - 1
            hi_, lo_, vol = np.maximum.reduceat(px, st), np.minimum.reduceat(px, st), np.add.reduceat(sz, st)
            ok = vol > 0
            tp3 = ((hi_ + lo_ + px[en]) / 3.0)[ok]
            bend = ((k[st] + 1) * w)[ok]
            cum_pv, cum_v = np.cumsum(tp3 * vol[ok]), np.cumsum(vol[ok])
            j = np.searchsorted(bend, grid, side="right") - 1      # the last bar that has completed by the boundary
            if len(bend) and (j >= 0).all():
                out = cum_pv[j] / cum_v[j]
    _VW16[key] = out
    return out


def _bar_end(st) -> int:
    """Nominal close second (after 00:00 ET of the trade date) of the tf bar that has just closed (call in fam_signal)."""
    step = st.tf * 60
    return (st.M[-1][0] // step + 1) * step


# ---- orb_close ---------------------------------------------------------------------------------------------------------------------
class OrbClose(Template):
    """orb_close (module docstring). State per day: r (the range, once it has ended), used (the one signal)."""
    DEFAULTS = {"or_min": "5", "dir": "both", "max_tr": 1, "entry": "market", "wait": "0", "start": "0830", "vwap": "off", "vwap_tf": "0"}
    SCHEMA = {"or_min": ("choice", ("5", "15", "30", "60")), "dir": ("choice", ("both", "long", "short")),
              "entry": ("choice", ("market", "limit")), "wait": ("choice", ("0", "5", "15", "30")),
              "start": ("choice", ("0830", "0930")), "vwap": ("choice", ("off", "on", "first")), "vwap_tf": ("choice", ("0", "15"))}
    SCREEN_TFS = TFS
    SCREEN_RUN = {"strict_limit": True}             # only a limit entry reads it
    FEATURES = ()

    @classmethod
    def unit_exits(cls, root):
        """The family's OWN exit cells (the owner's "stop at the range"): ONE stop, the other side of the range (stop_mode struct: the
        distance from the entry to the far edge), x the six standard targets. A spec file asks for them with exits "own"."""
        return [{"stop_mode": "struct", "stop_val": 1.0, "tgt_r": r} for r in STRUCT_TGT_R]

    @classmethod
    def unit_exits_low(cls, root):
        """exits "own_low": the same stop (the far side of the range) x LOW_TGT_R, the small targets of a win-rate idea. 0.5 is the standard cell again."""
        return [{"stop_mode": "struct", "stop_val": 1.0, "tgt_r": r} for r in LOW_TGT_R]

    def t_open(self) -> int:
        return OPEN if self.p["start"] == "0930" else RELEASE

    def fam_filter(self, ids):
        return [s for s in ids if s in (NY if self.p["start"] == "0930" else ("pre",))]

    def fam_sessions(self):
        return {} if self.p["start"] == "0930" else {"pre": (RELEASE, END_0830)}

    def fam_day(self, ctx):
        self.r = None

    def fam_session(self, ctx, s):
        self.used = False

    def fam_signal(self, ctx):
        r_end = self.t_open() + int(self.p["or_min"]) * 60
        end = _bar_end(self)
        if end <= r_end:
            return
        if self.r is None:
            self.r = self.rng(self.t_open(), r_end)
            if self.r is None:
                return
        hi, lo = self.r
        c = self.C[-1]
        d = self.p["dir"]
        lim = self.p["entry"] == "limit"
        if self.used and (lim or self.p["vwap"] == "first"):     # limit: one signal a session, filled or not; vwap first: the first break decided
            return
        side = "long" if d != "short" and c > hi else "short" if d != "long" and c < lo else None
        if side is None:
            return
        if self.p["vwap"] != "off":
            vs = vwap16_series(self.root, self.day, self.dl[-1]["date"], int(self.p["vwap_tf"])) if self.dl else None
            k = (end - RELEASE) // 60
            if vs is None or not 0 <= k < len(vs):
                return
            if self.p["vwap"] == "first":
                self.used = True
            v = float(vs[k])
            if not (c > v if side == "long" else c < v):
                return
        far = lo if side == "long" else hi
        if lim:
            self.used = True
            w = int(self.p["wait"])
            self._lim(ctx, side, hi if side == "long" else lo, struct=far, ttl=max(1, w // self.tf) if w else None)
        else:
            self._mkt(ctx, side, struct=far)


# ---- open_candle -------------------------------------------------------------------------------------------------------------------
class OpenCandle(Template):
    """open_candle (module docstring). The signal bar is the session's first tf bar (sn == 1)."""
    DEFAULTS = {"k": 0.0, "body_r": 0.0, "vol_m": 0.0, "body_pts": 0.0, "max_tr": 1, "start": "0830"}
    SCHEMA = {"k": ("float", 0, 10), "body_r": ("float", 0, 1), "vol_m": ("float", 0, 50), "body_pts": ("float", 0, 1000),
              "start": ("choice", ("0830", "0200", "0300", "1800", "2000"))}
    OPENS = {"0830": RELEASE, "0200": 7200, "0300": 10800, "1800": -21600, "2000": -14400}      # ET seconds after 00:00 of the candle's open
    EVE_STARTS = ("1800", "2000")                               # the evening BEFORE the trade date (negative seconds), session "eve"
    WARM = 1                                                    # the signal is the session's FIRST bar: an evening restarts the bars at 18:00, so the library's 3-bar warm-up cannot apply
    SCREEN_TFS = TFS
    FEATURES = ()

    def _sid(self) -> str:
        return "pre" if self.p["start"] == "0830" else "eve" if self.p["start"] in self.EVE_STARTS else "london"

    def fam_filter(self, ids):
        return [s for s in ids if s == self._sid()]

    def fam_sessions(self):
        s = self.p["start"]
        if s == "0830":
            return {"pre": (RELEASE, END_0830)}
        return {"eve": (self.OPENS[s], EVE_END)} if s in self.EVE_STARTS else {"london": (self.OPENS[s], LONDON_END)}

    def fam_signal(self, ctx):
        k = float(self.p["k"])
        if self.sn != 1 or (not self.atr_p and (k > 0 or self.p["start"] not in self.EVE_STARTS)):      # an evening candle restarts the bars: no ATR yet, and none is needed at k = 0
            return
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        if c == o or (k > 0 and h - l < k * self.atr_p):
            return
        body = abs(c - o)
        if body < float(self.p["body_r"]) * (h - l) or body < float(self.p["body_pts"]):
            return
        vm = float(self.p["vol_m"])
        if vm > 0:
            rv = getattr(self, "blk_rvol", None)
            if rv is None:
                raise RuntimeError("open_candle vol_m needs the Blocks mixin (blk_rvol): run the wrapped class (families.blocks.WRAPPED)")
            sig = rv()                              # (the bar's volume, the median of the same clock bar over 14 dates) or None
            if sig is None or sig[0] < vm * sig[1]:
                return
        self._mkt(ctx, "long" if c > o else "short", struct=l if c > o else h)


# entry windows, ET seconds after 00:00 [first, last]: the smoke's "entries outside the window" count
ENTRY_WINDOWS = {"orb_close": (RELEASE + 5 * 60, 57480 - 1), "open_candle": (-21600 + 60, 57480 - 1)}

FAMILIES = {
    "orb_close": (OrbClose, {}, False,
                  "orb_close: the opening range (or_min 5 / 15 / 30 / 60 minutes from the 08:30 ET data release, or from 09:30 with start 0930) "
                  "broken on a CLOSE: the first tf bar that closes beyond it goes with it, at market or as a limit at the broken edge (the retest); "
                  "optionally only with the 16:00 ET anchored VWAP (long above, short below; the first break decides, or the next may trade); "
                  "one trade a session, flat 15:58; its own exit table is the stop at the other side of the range",
                  {"rationale": "A close beyond the first minutes' range after a scheduled release shows the side the first reaction chose, and "
                                "the stop at the other side of the range puts the loss where that reading is wrong; the limit at the edge waits "
                                "for the retest that late followers pay for.",
                   "complexity": 6,
                   "variants": [{"or_min": "5"}, {"or_min": "15"}, {"or_min": "30"}]}),
    "open_candle": (OpenCandle, {}, False,
                    "open_candle: the tf candle that opens at 08:30 ET (the data release; start 0200 / 0300 = the London opens, 1800 / 2000 = the evening candles of the Globex day before the trade date) is "
                    "followed at its close in its own direction (green long, red short); optional size gates, all off at 0: range >= k x ATR, "
                    "body >= body_r of its range, volume >= vol_m x the median of the same bar over 14 dates, body >= body_pts points; one trade "
                    "a session, flat 15:58",
                    {"rationale": "The release candle is where the news is priced: its direction is the first read of the surprise and a candle "
                                  "that is large, one-sided, loud or all body shows the buyers or sellers who had to act on it.",
                     "complexity": 5,
                     "variants": [{"k": 0.0}, {"k": 1.0}, {"k": 1.5}, {"k": 2.0}]}),
}


def _own_exits(blocks) -> None:
    """exits "own" = the family's own `unit_exits` cells, for a spec file of the manual lane (run_idea.spec_units asks blocks.exits(kind, ...)).
    Wraps blocks.exits instead of editing it (a hashed file); every other kind goes to the original unchanged. Idempotent."""
    if getattr(blocks.exits, "own_exits", False):
        return
    orig = blocks.exits

    def exits(kind: str, root: str, family: str) -> list:
        if kind not in ("own", "own_low"):
            return orig(kind, root, family)
        cls = blocks.WRAPPED.get(family)
        if cls is None or not hasattr(cls, "unit_exits" if kind == "own" else "unit_exits_low"):
            raise ValueError(f"exits 'own': {family!r} has no exit cells of its own (families that do: "
                             f"{sorted(n for n, c in blocks.WRAPPED.items() if hasattr(c, 'unit_exits'))})")
        if root not in S.MENU_STOP_PTS:
            raise KeyError(f"no menu for root {root!r}: {sorted(S.MENU_STOP_PTS)}")
        return cls.unit_exits(root) if kind == "own" else cls.unit_exits_low(root)

    exits.own_exits = True
    blocks.exits = exits


def join_blocks() -> None:
    """Put the families into families/blocks.py's BASES and WRAPPED (module docstring, REGISTRATION): the wrapped class a card runs, importable
    by name from there (workers import it through the package, which loads this module). Idempotent."""
    from . import blocks
    _own_exits(blocks)
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
