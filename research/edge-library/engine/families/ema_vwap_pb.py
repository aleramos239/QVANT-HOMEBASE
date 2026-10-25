"""ema_vwap_pb -- THE REGIME-FILTERED EMA PULLBACK (Bhatti 2026, "A Regime-Filtered Intraday Trading Framework for Gold: Integrating VWAP
Microstructure and EMA-Based Dynamic Exit Mechanisms", SSRN 6650958), written from the owner's reading of the paper before any result. The
paper is spot gold, 15-minute bars, one simulated year (2024) and no out-of-sample test. No Level-2 feature (FEATURES = ()): GC, 1 contract.

THE RULE (New York time; bars = the idea's own tf, 15 minutes as taught):
  * TREND: the close is above (below) the EMA(200) of the tf closes -> longs (shorts) only.
  * LOCATION: the EMA(n) is above (below) the session VWAP -> longs (shorts). n = the pullback EMA, the main setting (50 as taught).
  * REJECTION: the bar's low is at or below the EMA(n) (high at or above it) and the bar CLOSES back above (below) it. The EMAs include
    the signal bar's own close, as a chart draws them.
  * All three on the SAME bar close -> market entry (fills at the next bar's open). Struct stop = the rejection bar's low (high): the paper's
    abstract does not name an initial stop; hm40's "own stop" cells take it.
  * The EMAs run on across days as a chart's do: today's closes from 18:00 ET of the evening before, before them the sessions before today
    (each 18:00 of its evening before to 17:00), newest back, until 3 x 200 closes are held, a roll day (one contract only) or LOOK sessions;
    seeded with the oldest close, e += 2 / (n + 1) x (close - e). Fewer than 2 x 200 closes = no EMA = no trade (so ~4 sessions after a roll
    day do not trade). The sessions before today are read with the build key by their own date (as candle_sweep): a prior session that
    cannot be opened ends the history.
  * The VWAP is the session VWAP anchored at 18:00 ET (the Globex open, barstore's anchor): the 1-minute bars' typical price (h + l + c) / 3,
    volume weighted, from the evening before's 18:00 to this close (avwap.evening for the evening, the Template's minutes after 00:00).
SESSION. One pass, 00:00-15:55 ET (the family stretches "asia" to the whole day; asia is the card's home session), flat 15:58 (hold_to=day). The
evening 18:00-24:00 trades nothing (version 1 refuses an evening session) but feeds the EMAs and the VWAP. WARM = 14 tf bars since 00:00 (the
first entry at 03:30), so the Template's ATR(14) that hm40's ATR stops use is a full 14-bar value. max_tr 3 a day (a cap of ours, the paper
names none); one position at a time.
EXITS: the card's (hm40). The paper's own exit -- a trailing stop at the EMA(50), triggered by a 15-minute CLOSE beyond it -- is NOT built:
version 1 refuses exits of its own (limits.trail_atr / exit_bars; the toolkit's stop / target table only).
NOT BUILT (the paper's extras): ATR position sizing, the daily loss limit, the news filter (the toolkit's `days` rule skips whole days, not the
minutes around a release).
NO LOOK-AHEAD: every close used ended at or before this decision (a bucket ends <= now floored to the tf); a prior session is a date before
today; today's tape is cut at the decision exactly as avwap.evening is.
REGISTRATION as pd_vwap_adx.py: join_blocks(). Tests: engine/tests/test_ema_vwap_pb.py."""
from __future__ import annotations

import datetime as dt

import numpy as np

import l2sim as S
from l2sim import HoldoutSealed, Template

TREND = 200                                         # the trend EMA, held at the paper's value
NEED = 2 * TREND                                    # fewest closes an EMA(200) may stand on
HOLD = 3 * TREND                                    # closes gathered when the history has them
LOOK = 14                                           # prior sessions looked back at most (GC: about 92 15-minute closes a session; 46 at tf 30)
DAY_END_S = 57300                                   # 15:55 ET: the pass ends (no entry in its last 5 minutes); hold_to=day flattens at 15:58
EVE0 = -21600                                       # 18:00 ET of the evening before, seconds after 00:00 ET
_C: dict = {}                                       # (root, iso, tf) -> (end_ns, close) of a whole session, per process


def session_closes(root: str, iso: str, tf: int):
    """(end_ns, close) of the tf-minute buckets with prints of trade date `iso`, 18:00 ET of its evening before to 17:00 (a bucket ends at
    its edge; epoch-aligned like the Template's), from its tape under the seal of its OWN date; None = no tape or a sealed date."""
    key = (root, iso, tf)
    if key not in _C:
        d = S._date(iso)
        try:
            t = S.load_tape(iso, root, allow_holdout=S.ALLOW_BP if d <= S.BP_BUILD[1] else S.ALLOW_BT)
        except HoldoutSealed:
            t = None
        out = None
        if t is not None and len(t.ts):
            step = tf * S.MIN_NS
            i0 = int(np.searchsorted(t.ts, S.et_ns(d - dt.timedelta(days=1), "18:00"), side="left"))
            i1 = int(np.searchsorted(t.ts, S.et_ns(d, "17:00"), side="left"))
            if i1 > i0:
                k = t.ts[i0:i1] // step
                last = np.flatnonzero(np.concatenate((k[1:] != k[:-1], [True])))
                out = ((k[last] + 1) * step, np.asarray(t.px[i0:i1], np.float64)[last])
        _C[key] = out
    return _C[key]


def prior_closes(st, tf: int, need: int):
    """The tf closes of the sessions before today, one contract, oldest first (module docstring)."""
    out, n = [], 0
    if st.day not in st.ROLLS:
        for r in reversed(st.dl[-LOOK:]):
            if S._date(r["date"]) >= S._date(st.day):
                raise S.LookAheadError(f"ema_vwap_pb: prior session {r['date']} is not before {st.day}")
            got = session_closes(st._cx.root, r["date"], tf)
            if got is None:
                break
            out.append(got[1])
            n += len(got[1])
            if r["date"] in st.ROLLS or n >= need:
                break
    return np.concatenate(out[::-1]) if out else np.zeros(0)


def ema_run(closes, n: int):
    """EMA(n) after the last of `closes` (module docstring: seeded with the first), or None for none."""
    if not len(closes):
        return None
    a, e = 2.0 / (n + 1), float(closes[0])
    for c in closes[1:]:
        e += a * (float(c) - e)
    return e


class EmaVwapPb(Template):
    """ema_vwap_pb (module docstring). Per day: the EMAs of the closes before today (e_t, e_n, cnt), today's closes (tc) read up to a pointer
    (ti), the VWAP sums (vv, vp), and the signal (sig)."""
    DEFAULTS = {"n": 50, "max_tr": 3}
    SCHEMA = {"n": ("int", 10, 100), "max_tr": ("int", 1, 5)}
    SCREEN_TFS = ("5", "15", "30")                  # 15 as taught; 5 and 30 are its neighbors
    FEATURES = ()
    WARM = 14

    def fam_filter(self, ids):
        return [s for s in ids if s == "asia"]

    def fam_sessions(self) -> dict:
        return {"asia": (0, DAY_END_S)}

    def fam_day(self, ctx):
        self.vv = self.vp = 0.0                     # VWAP sums from 18:00: volume, volume x typical price
        self.mi = 0                                 # 1-minute bars read into the VWAP
        self.sig = None
        self.ti = 0                                 # today's closes already stepped into the EMAs
        self.e_t = self.e_n = None
        self.cnt = 0
        self.tc = session_closes(ctx.root, self.day, self.tf)
        if self.tc is None:
            return
        pri = prior_closes(self, self.tf, HOLD)
        self.cnt = len(pri)
        self.e_t, self.e_n = ema_run(pri, TREND), ema_run(pri, int(self.p["n"]))
        from families import avwap as AV
        ev = AV.evening(ctx.root, self.day)
        if ev is not None:
            self.vv, self.vp = float(ev["v"].sum()), float(ev["tpv"].sum())

    def fam_update(self, ctx):
        self.sig = None
        M = self.M
        for i in range(self.mi, len(M)):
            s, _, h, l, c, v = M[i]
            if v > 0:
                self.vv += v
                self.vp += v * (h + l + c) / 3.0
        self.mi = len(M)
        if self.tc is None or self.e_t is None or self.vv <= 0:
            return
        end, close = self.tc
        cut = ctx.now_ns - ctx.now_ns % self.step           # the buckets that have ended by this decision
        at = int(np.searchsorted(end, cut, side="right"))
        a_t, a_n = 2.0 / (TREND + 1), 2.0 / (int(self.p["n"]) + 1)
        for j in range(self.ti, at):
            self.e_t += a_t * (close[j] - self.e_t)
            self.e_n += a_n * (close[j] - self.e_n)
            self.cnt += 1
        self.ti = max(self.ti, at)
        if self.cnt < NEED:
            return
        h, l, c, vw = self.H[-1], self.L[-1], self.C[-1], self.vp / self.vv
        if c > self.e_t and self.e_n > vw and l <= self.e_n < c:
            self.sig = "long"
        elif c < self.e_t and self.e_n < vw and h >= self.e_n > c:
            self.sig = "short"

    def fam_signal(self, ctx):
        if self.sig is not None:
            self._mkt(ctx, self.sig, struct=self.L[-1] if self.sig == "long" else self.H[-1])


FAMILIES = {
    "ema_vwap_pb": (EmaVwapPb, {}, False,
                    "ema_vwap_pb: close above (below) the EMA(200), EMA(n) above (below) the 18:00 session VWAP, and the bar's low (high) touches "
                    "the EMA(n) and closes back above (below) it -> market with the trend; struct stop = the rejection bar's low (high); "
                    "00:00-15:55, max 3 a day. Bhatti 2026 (SSRN 6650958), one simulated year, no out-of-sample",
                    {"rationale": "Gold wicks hard and trends in swells: in an established trend, with the faster average on the winning side of "
                                  "the day's volume-weighted price, a dip that tags the pullback average and is rejected is a continuation "
                                  "entry. Who loses: the traders fading the trend at its pullback, and the stops sitting just behind the average.",
                     "complexity": 5,
                     "variants": [{"n": 40}, {"n": 50}, {"n": 60}],
                     "roots": ("NQ", "ES", "GC")}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as pd_vwap_adx.py): the wrapped class a card runs, importable by name."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
