"""O1 open_dir (SPEC "Families" + "Stage A screen"; the exact definition is pre-registered in FAMILIES.md, section O1).

At each session open (03:00 london, 09:30 nyam, 11:05 mid, 13:30 pm; asia has none) pick ONE side from the pre-open book
and / or flow and rest ONE stop entry at last price +/- off_atr x ATR30 on that side: cancelled if unfilled 60 minutes
later, stop 3 ATR30, no target, flat at the session end, at most one trade per session. One side only: both_sides = False.

    book   sign of the mean imb10 over the 5 minutes before the open (all 5 finite: a NaN / book_ok False row = no signal)
    flow   sign of the summed f_delta over the 15 minutes before the open (>= 8 finite). REVISIT of the refuted 9:30
           delta-direction family (burned-data ledger NQ|1m|930_delta_direction, 2026-09-23)
    both   book and flow must agree

"ATR30" = the Template's ATR at tf = 30: the family is screened at tf 30 only. Features are read through ctx.feat_window
only, at the open (a declared clock time), and only when the rows are exactly the minutes that just ended.
"""
from __future__ import annotations

import numpy as np

import l2sim as S

OPENS = {"london": 3 * 3600, "nyam": 9 * 3600 + 1800, "mid": 11 * 3600 + 300, "pm": 13 * 3600 + 1800}   # s after 00:00 ET
CANCEL_S = 3600                                    # an unfilled entry is cancelled 60 minutes after its open
BOOK_MIN = 5                                       # book: minutes of imb10 before the open, all must be finite
FLOW_MIN, FLOW_VALID = 15, 8                       # flow: minutes of f_delta before the open, min minutes with a print


def book_sign(w) -> int:
    """+1 (bids heavier) / -1 / 0 (no signal) from the BOOK_MIN imb10 rows before the open; any NaN = no signal."""
    w = np.asarray(w, np.float64)
    if len(w) != BOOK_MIN or not np.isfinite(w).all():
        return 0
    s = float(w.sum())                             # the sign of the mean
    return (s > 0) - (s < 0)


def flow_sign(w) -> int:
    """+1 (net buying) / -1 / 0 (no signal) from the FLOW_MIN f_delta rows before the open; a NaN row (a minute
    without a print) adds 0, fewer than FLOW_VALID finite rows = no signal."""
    w = np.asarray(w, np.float64)
    ok = np.isfinite(w)
    if len(w) != FLOW_MIN or int(ok.sum()) < FLOW_VALID:
        return 0
    s = float(w[ok].sum())
    return (s > 0) - (s < 0)


class OpenDir(S.Template):
    """O1 open_dir: one stop entry at the session open on the side the pre-open book / flow points to."""
    DEFAULTS = {"src": "book", "off_atr": 0.25, "stop_val": 3.0, "tgt_r": 0.0, "max_tr": 1}      # SPEC, pre-registered
    SCHEMA = {"src": ("choice", ("book", "flow", "both")), "off_atr": ("float", 0.05, 5.0)}
    SCREEN_TFS = ("30",)                           # ATR30: tf is fixed, the decision is at the open
    FEATURES = ("imb10", "f_delta", "t_utc")

    def fam_filter(self, ids):
        return [s for s in ids if s in OPENS]

    def fam_times(self):
        return [S._hms(OPENS[s] + k) for s in self.sessions() for k in (0, CANCEL_S)]

    def _rows(self, ctx, col, n):
        """The n rows of `col` stamped T - n .. T - 1 min (T = now), or None unless the table holds exactly those."""
        t = ctx.feat_window("t_utc", n)
        now_s = ctx.now_ns // S.NS
        if len(t) != n or not np.array_equal(t, now_s - 60 * np.arange(n, 0, -1)):
            return None
        return ctx.feat_window(col, n)

    def open_side(self, ctx):
        """'long' | 'short' | None at the open, from src."""
        src, sb, sf = self.p["src"], 0, 0
        if src != "flow":
            w = self._rows(ctx, "imb10", BOOK_MIN)
            sb = 0 if w is None else book_sign(w)
            if sb == 0:
                return None
        if src != "book":
            w = self._rows(ctx, "f_delta", FLOW_MIN)
            sf = 0 if w is None else flow_sign(w)
            if sf == 0:
                return None
        if src == "both" and sb != sf:
            return None
        return "long" if (sf if src == "flow" else sb) > 0 else "short"

    def fam_time(self, ctx, sec):
        s = self.sid
        if s not in OPENS:
            return
        if sec == OPENS[s] + CANCEL_S:
            self._cancel(ctx)                      # the unfilled entry only: a position keeps its stop
            return
        if sec != OPENS[s] or not self.can_enter(ctx):
            return
        lp, side = ctx.last_price, self.open_side(ctx)
        if lp is None or side is None:
            return
        off = float(self.p["off_atr"]) * self.atr
        self._arm(ctx, [(side, lp + off if side == "long" else lp - off, None, None)])


class OpenDirBook(OpenDir):
    """src = book. Loads no flow column."""
    DEFAULTS = {"src": "book"}
    SCHEMA = {"src": ("choice", ("book",))}
    FEATURES = ("imb10", "t_utc")


class OpenDirFlow(OpenDir):
    """src = flow: REVISIT of the refuted 9:30 delta-direction family. Loads no book column (trades roll days)."""
    DEFAULTS = {"src": "flow"}
    SCHEMA = {"src": ("choice", ("flow",))}
    FEATURES = ("f_delta", "t_utc")


class OpenDirBoth(OpenDir):
    """src = both: book and flow must agree (contains the REVISIT flow signal as a confirmation)."""
    DEFAULTS = {"src": "both"}
    SCHEMA = {"src": ("choice", ("both",))}
    FEATURES = ("imb10", "f_delta", "t_utc")


FAMILIES = {
    "open_dir_book": (OpenDirBook, {"src": "book"}, False,
                      "O1: at 03:00 / 09:30 / 11:05 / 13:30 ET the sign of the mean imb10 of the last 5 usable minutes -> ONE "
                      "stop entry at last +/- 0.25 ATR30 (60 min), stop 3 ATR30, no target, flat at session end, 1 per session"),
    "open_dir_flow": (OpenDirFlow, {"src": "flow"}, False,
                      "O1 REVISIT of the REFUTED 9:30 delta-direction family (ledger NQ|1m|930_delta_direction, 2026-09-23): "
                      "side = sign of the summed f_delta of the last 15 minutes before the open, same single stop entry"),
    "open_dir_both": (OpenDirBoth, {"src": "both"}, False,
                      "O1: book and flow sides must agree (contains the REVISIT flow signal as a confirmation), same single "
                      "stop entry"),
}
