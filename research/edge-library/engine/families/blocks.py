"""blocks -- EXIT and FILTER BLOCKS for every bar-based library family, the `ib_n` family, the extended exit menu.

WHY: a new idea should be SETTINGS built from blocks that are tested once (ideas/specs/<name>.json, run_idea.py), not new
strategy code plus new look-ahead tests. Nothing in l2sim.py or in another family module is changed: `Blocks` is a mixin put
IN FRONT of a family class. With every block off a wrapped family is trade-for-trade the original (tests/test_blocks.py).

    WRAPPED[name]    = class B_<name>(Blocks, <the family's registered class>)   every bar-based library family without
                       Level-2 features of port1 / port2 / port3 / round1 / timed, and ib_n (time-fired families are left out)
    CONTROLS[name]   = class R_<name>(Blocks, l2ref.Random)   the random-entry control of a range stop: a random entry that
                       carries the family's own structure height (same stop rule, random time and side)

WHEN A BLOCK IS READ: at the moment the family places its order -- inside `allowed(side)`, which the Template calls for every
market entry (the signal bar's close) and for every leg of a resting bracket (the instant the bracket is placed: orb / ib_n at
the range end). A filter never looks at a fill that comes later; a direction filter on a two-sided bracket keeps the leg it
allows. Every filter has two sides; a filter WITHOUT A SIGNAL (too little history, a missing book) blocks the entry on BOTH.

EXIT BLOCKS
  stop_mode = "rng"   stop distance = stop_val x the HEIGHT of the structure the family trades, read at the order (HEIGHTS):
        orb            high - low of the first or_min minutes of the session
        orb_confirm    high - low of the first or_min minutes from 09:30
        ib / ib_n      high - low of 09:30 .. 10:30 / of the first ib_min minutes from 09:30
        lon_break      high - low of 03:00 .. 08:25
        donchian       high - low of the n tf bars before the signal bar (the channel)
        vol_spike_break  high - low of the 20 tf bars before the signal bar
        first_bar_mom  high - low of the signal bar
      floored at 2 ticks like every stop; no structure yet (or height 0) -> no entry. A family that is not in HEIGHTS has no
      structure and REFUSES the mode (ValueError at construction).
  more ATR stops / targets: the Template takes any stop_val / tgt_r; they are only menu cells: menu_extended(root).
  MENU "extended" = the 32 standard cells first (same order, same ids), then the 8 standard stops x targets {1.5, 4}, then the
      new stops (ATR x 1 and x 2, then range x 0.25 / 0.5 / 1) x targets {0, 1, 2, 3, 1.5, 4}: 78 cells, 60 without a structure.

FILTER BLOCKS (FILTERS: block -> side -> the inputs that switch it on)
  volatility  high | low    f_dvol = hi | lo     the PRIOR trade date's range (h - l) above / not above the median of the 20
        daily ranges ending with that day (ctx.daily = bars dated before today only; the definition of out/deepen/labels.py
        T2, checked against it). Fewer than 20 daily bars -> no entry.
  momentum    with | against  f_rsi              Wilder RSI(14) of the tf closes since the indicator restart (00:00 ET; 18:00
        for a held evening), closed bars only, at the signal bar's close. with: long needs RSI > 50, short < 50; against: the
        mirror. Fewer than 15 closes, or RSI exactly 50 -> no entry.
  volume      high | low    f_cvol = hi | lo     the volume traded from the SESSION'S ANCHOR to the decision (completed
        1-minute bars only) above / below the median, over the 20 trade dates before today, of the volume of the same clock
        window. Anchor = the Template's anchored-VWAP anchor: asia 00:00, london 03:00, pre 08:25, nyam / mid / pm 09:30 (the
        cash open: a midday or afternoon signal reads the volume since 09:30), eve 18:00. Fewer than 20 prior dates, a prior
        date without a tape, equality, or a decision AT the anchor (an empty window) -> no entry.
        Prior days come from cache/minvol_<ROOT>.npz (build_minvol; per ET minute of the Globex day, by trade date).
  news        yes | no      f_news               the trade date has / has not a row at 08:30 or 10:00 ET in cache/events.csv
        (the STAGE 3 calendar: groups A and C; the 14:00 FOMC rows are not release days here). A schedule: known in advance.
  book        agree | disagree  (NQ only)        agree = the Template's own f_book = "on" (the 5-minute mean of the top-10
        imbalance imb10 does not oppose the side: long needs mean >= 0); disagree = f_bookopp = "on": the same signal
        (l2sim.book_mean5) OPPOSES the side (long needs mean < 0). No signal -> no entry. Needs features (BOOK_COLS).

ib_n = port1.Ib with the range length as an input: ib_min 5 | 15 | 30 | 60 minutes from 09:30 (60 = ib, trade for trade).
"""
from __future__ import annotations

import csv
import os
from multiprocessing import get_context

import numpy as np

import l2ref
import l2sim as S
from l2sim import NS, SESS, _hms

from . import port1, port2, port3, round1, timed

OPEN = 34200                                        # 09:30 ET, seconds after 00:00
VOL_DAYS = 20                                       # volatility and volume blocks: the 20 trade dates before today
RSI_N = 14
NEWS_TIMES = ("08:30", "10:00")                     # the release groups of cache/events.csv that make a "release day"
BOOK_COLS = ("imb10", "t_utc")                      # what the book block reads through ctx.feat (l2sim.L2_OPTION_COLS["f_book"])
MIN0, NMIN = -360, 1380                             # minute volume: index 0 = 18:00 ET of the evening before .. 17:00 ET
# volume block: where "the session so far" starts -- the Template's anchored-VWAP anchors (asia 00:00, london 03:00, pre 08:25,
# the three NY sessions 09:30, eve 18:00); a family's own session window starts at its own start
VOL_ANCHOR = {"asia": 0, "london": 10800, "pre": 30300, "nyam": OPEN, "mid": OPEN, "pm": OPEN, "eve": -21600}

X_STOP_ATR = (1.0, 2.0)                             # the extended menu's new stops and targets
X_STOP_RNG = (0.25, 0.5, 1.0)
X_TGT_R = (1.5, 4.0)

FILTERS = {"volatility": {"high": {"f_dvol": "hi"}, "low": {"f_dvol": "lo"}},
           "momentum": {"with": {"f_rsi": "with"}, "against": {"f_rsi": "against"}},
           "volume": {"high": {"f_cvol": "hi"}, "low": {"f_cvol": "lo"}},
           "news": {"yes": {"f_news": "yes"}, "no": {"f_news": "no"}},
           "book": {"agree": {"f_book": "on"}, "disagree": {"f_bookopp": "on"}}}
L2_BLOCKS = ("book",)                               # NQ only: they read the Level-2 feature table
PLAIN = {("volatility", "high"): "only after a day whose range was above its own 20-day median",
         ("volatility", "low"): "only after a day whose range was at or below its own 20-day median",
         ("momentum", "with"): "only when RSI(14) on the idea's bars points the trade's way (long above 50, short below 50)",
         ("momentum", "against"): "only when RSI(14) on the idea's bars points against the trade (long below 50, short above 50)",
         ("volume", "high"): "only when the session's volume so far is above its 20-day median for that time of day",
         ("volume", "low"): "only when the session's volume so far is below its 20-day median for that time of day",
         ("news", "yes"): "only on days with an 08:30 or 10:00 ET US data release",
         ("news", "no"): "never on days with an 08:30 or 10:00 ET US data release",
         ("book", "agree"): "only when the top-10 order book leans the trade's way (5-minute mean imbalance)",
         ("book", "disagree"): "only when the top-10 order book leans against the trade (5-minute mean imbalance)"}


# ---- the menu ---------------------------------------------------------------------------------------------------------------
def menu_extended(root: str, rng: bool = True) -> list:
    """The EXTENDED exit menu of `root` (module docstring): the 32 standard cells, then the cells with a new target or a new
    stop. rng False (a family without a structure) leaves the range stops out. Cells shared by both forms keep their index."""
    stops = S.menu_stops(root)
    new = [{"stop_mode": "atr", "stop_val": v} for v in X_STOP_ATR]
    if rng:
        new += [{"stop_mode": "rng", "stop_val": v} for v in X_STOP_RNG]
    return (S.menu(root) + [{**st, "tgt_r": r} for st in stops for r in X_TGT_R]
            + [{**st, "tgt_r": r} for st in new for r in S.MENU_TGT_R + X_TGT_R])


def exits(kind: str, root: str, family: str) -> list:
    """The exit cells of an idea: 'standard' = l2sim.menu(root); 'extended' = menu_extended (range stops only when the
    family has a structure)."""
    if kind == "standard":
        return S.menu(root)
    if kind == "extended":
        return menu_extended(root, rng=family in HEIGHTS)
    raise ValueError(f"exits {kind!r}: 'standard' or 'extended'")


def filter_inputs(block: str, side: str, root: str = "NQ") -> dict:
    """The inputs that switch ONE filter block on, on one of its two sides."""
    if block not in FILTERS or side not in FILTERS[block]:
        raise ValueError(f"filter {block!r} / {side!r}: blocks and sides are {({b: tuple(s) for b, s in FILTERS.items()})}")
    if block in L2_BLOCKS and root not in S.L2_ROOTS:
        raise ValueError(f"the {block} block reads Level 2: {sorted(S.L2_ROOTS)} only, not {root}")
    return dict(FILTERS[block][side])


# ---- volatility: the prior day's range against its own 20-day median ------------------------------------------------------------
def day_vol(rows: list, iso: str):
    """'hi' | 'lo' | None for trade date `iso` from daily bars [{date, h, l, ...}] ascending: ONLY rows dated before `iso`
    are read. hi = the last such bar's range is above the median of the last 20 such ranges (itself included); lo = not
    above; None with fewer than 20."""
    j = len(rows)
    while j and rows[j - 1]["date"] >= iso:           # the engine hands bars dated < iso only; a longer list is cut here
        j -= 1
    if j < VOL_DAYS:
        return None
    rng = [rows[k]["h"] - rows[k]["l"] for k in range(j - VOL_DAYS, j)]
    return "hi" if rng[-1] > float(np.median(rng)) else "lo"


# ---- momentum: Wilder RSI ---------------------------------------------------------------------------------------------------------
def rsi(closes, n: int = RSI_N):
    """Wilder RSI(n) at the last of `closes` (closed bars, oldest first): the first average gain / loss = the mean of the
    first n changes, then Wilder smoothing. None with fewer than n + 1 closes; 50 when nothing has moved."""
    if len(closes) < n + 1:
        return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            g += d
        else:
            l -= d
    g /= n
    l /= n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (n - 1) + (d if d > 0 else 0.0)) / n
        l = (l * (n - 1) + (-d if d < 0 else 0.0)) / n
    return 50.0 if g + l == 0 else 100.0 * g / (g + l)


# ---- volume: the minute-volume profile of the prior days -----------------------------------------------------------------------
_MV_FILE: dict = {}                                 # root -> ({iso: row}, int64 [dates, NMIN])      read once per process
_CUM: dict = {}                                     # (root, iso) -> int64 [NMIN + 1] prefix sums, or None (no tape)


def minute_volume(tape) -> np.ndarray:
    """Volume per ET clock minute of a tape's Globex day: int64 [NMIN], index 0 = 18:00 ET of the evening before the
    trade date (the same minutes, and the same sums, as the engine's 1-minute bars)."""
    k = (tape.ts - S.et_ns(tape.date, "00:00")) // S.MIN_NS - MIN0
    ok = (k >= 0) & (k < NMIN)
    return np.bincount(k[ok], weights=tape.size[ok], minlength=NMIN).astype(np.int64)


def _mv_path(root: str):
    return S.CACHE / f"minvol_{root}.npz"


def _mv_file(root: str) -> tuple:
    if root not in _MV_FILE:
        p = _mv_path(root)
        if p.exists():
            z = np.load(p)
            _MV_FILE[root] = ({d: i for i, d in enumerate(z["dates"].tolist())}, z["vol"])
        else:
            _MV_FILE[root] = ({}, np.zeros((0, NMIN), np.int64))
    return _MV_FILE[root]


def cum_volume(root: str, iso: str):
    """Prefix sums [NMIN + 1] of trade date `iso`'s minute volume: the cache file when it holds the date, else from the tape
    (None when the date has none; a 2025+ date raises HoldoutSealed in load_tape). Remembered per process."""
    key = (root, iso)
    if key not in _CUM:
        idx, vol = _mv_file(root)
        if iso in idx:
            v = vol[idx[iso]]
        else:
            t = S.load_tape(iso, root)
            v = None if t is None or not len(t.ts) else minute_volume(t)
        _CUM[key] = None if v is None else np.concatenate(([0], np.cumsum(v, dtype=np.int64)))
    return _CUM[key]


def cum_ref(root: str, dates: list, a: int, b: int):
    """Median over `dates` (the 20 trade dates before today, from the daily bars) of the volume traded in the clock window
    [a, b) -- seconds after 00:00 ET of each date, whole minutes. None: fewer than 20 dates, one without a tape, or an empty /
    out-of-day window."""
    i, j = a // 60 - MIN0, b // 60 - MIN0
    if len(dates) < VOL_DAYS or not 0 <= i < j <= NMIN:
        return None
    vals = []
    for iso in dates[-VOL_DAYS:]:
        c = cum_volume(root, iso)
        if c is None:
            return None
        vals.append(int(c[j] - c[i]))
    return float(np.median(vals))


def _mv_one(args):
    iso, root, allow = args
    S.wait_compute_window()
    t = S.load_tape(iso, root, **allow)
    return iso, (None if t is None or not len(t.ts) else minute_volume(t))


def build_minvol(root: str, period: str = "build", workers: int = 1, **allow) -> dict:
    """Fill cache/minvol_<root>.npz with the minute volume of every session of `period` (default BUILD: nothing else is
    read) the file does not hold yet. -> {'path', 'dates', 'added'}. run_idea calls it before a volume-block pass; a worker
    that misses a date computes it from that date's tape with the same function -- WITHOUT a seal switch, so a sealed
    date that is not in the file stops the run (HoldoutSealed). `allow`: the engine's own seal switch of the stage that
    opens a later period (handed to l2sim.sessions / load_tape unchanged, e.g. allow_check=True); never set here."""
    p = _mv_path(root)
    _MV_FILE.pop(root, None)
    idx, vol = _mv_file(root)
    a, b = S.period(period)
    todo = [(d.isoformat(), root, allow) for d in S.sessions(a, b, root, **allow)
            if d.isoformat() not in idx and (root == "NQ" or S.hb_tape_path(d, root) is not None)]
    if todo:
        workers = max(1, min(int(workers), S.MAX_WORKERS))
        S.wait_compute_window()
        if workers == 1 or not S.pool_usable():
            res = [_mv_one(x) for x in todo]
        else:
            with get_context("spawn").Pool(workers) as pool:
                res = pool.map(_mv_one, todo, chunksize=16)
        have = {d: vol[i] for d, i in idx.items()}
        have.update({d: v for d, v in res if v is not None})
        dates = sorted(have)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.stem}.{os.getpid()}.tmp.npz")
        np.savez_compressed(tmp, dates=np.array(dates), vol=np.stack([have[d] for d in dates]) if dates else vol)
        os.replace(tmp, p)
        _MV_FILE.pop(root, None)
        for d, _, _ in todo:
            _CUM.pop((root, d), None)
    return {"path": str(p), "dates": len(_mv_file(root)[0]), "added": len(todo)}


# ---- news: release days ---------------------------------------------------------------------------------------------------------
_NEWS: list = []


def release_days() -> frozenset:
    """ISO dates with a calendar row at 08:30 or 10:00 ET (cache/events.csv: official release schedules, never checked
    against the tape). Read once per process."""
    if not _NEWS:
        with (S.CACHE / "events.csv").open(newline="") as fh:
            _NEWS.append(frozenset(r["date"] for r in csv.DictReader(fh) if r["time_et"] in NEWS_TIMES))
    return _NEWS[0]


# ---- the structure heights (stop_mode = "rng") ---------------------------------------------------------------------------------
def _now_s(st) -> int:
    """Seconds after 00:00 ET of the trade date at this decision."""
    return (st._cx.now_ns - st.t0) // NS


def _range_after(st, a: int, b: int):
    """High - low of the completed 1-minute bars in [a, b), once the window has ended; else None."""
    if _now_s(st) < b:
        return None
    r = st.rng(a, b)
    return None if r is None else r[0] - r[1]


def _h_orb(st):
    if st.sid is None:
        return None
    a = st.S[st.sid][0]
    return _range_after(st, a, a + int(st.p["or_min"]) * 60)


def _h_orb_confirm(st):
    return _range_after(st, OPEN, OPEN + int(st.p["or_min"]) * 60)


def _h_ib(st):
    return _range_after(st, OPEN, OPEN + int(st.p.get("ib_min", "60")) * 60)


def _h_lon(st):
    return _range_after(st, 10800, 30300)


def _channel(st, n: int):
    return max(st.H[-n - 1:-1]) - min(st.L[-n - 1:-1]) if st.nb > n else None


def _h_donchian(st):
    return _channel(st, int(st.p["n"]))


def _h_spike(st):
    return _channel(st, round1.VolSpikeBreak.N)


def _h_bar(st):
    return st.H[-1] - st.L[-1] if st.nb else None


# family -> (the structure in plain words, height function, the family inputs the function reads)
HEIGHTS = {"orb": ("the opening range: the first or_min minutes of the session", _h_orb, ("or_min",)),
           "orb_confirm": ("the opening range: the first or_min minutes from 09:30", _h_orb_confirm, ("or_min",)),
           "ib": ("the initial balance 09:30-10:30", _h_ib, ()),
           "ib_n": ("the opening range: the first ib_min minutes from 09:30", _h_ib, ("ib_min",)),
           "lon_break": ("the London range 03:00-08:25", _h_lon, ()),
           "donchian": ("the channel: the n bars before the signal bar", _h_donchian, ("n",)),
           "vol_spike_break": ("the channel: the 20 bars before the signal bar", _h_spike, ()),
           "first_bar_mom": ("the signal bar's range", _h_bar, ())}


# ---- the mixin ------------------------------------------------------------------------------------------------------------------
class Blocks:
    """The blocks, in front of a family class (module docstring). All default off: the family is then unchanged."""
    DEFAULTS = {"f_dvol": "off", "f_rsi": "off", "f_cvol": "off", "f_news": "off", "f_bookopp": "off"}
    SCHEMA = {"stop_mode": ("choice", ("atr", "pts", "struct", "pct", "rng")),
              "f_dvol": ("choice", ("off", "hi", "lo")), "f_rsi": ("choice", ("off", "with", "against")),
              "f_cvol": ("choice", ("off", "hi", "lo")), "f_news": ("choice", ("off", "yes", "no")),
              "f_bookopp": ("choice", ("off", "on"))}
    BASE = None                                     # the family name the class was built for
    STRUCT = None                                   # its structure in plain words; None = it has none

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if self.p["stop_mode"] == "rng" and self.STRUCT is None:
            raise ValueError(f"stop_mode='rng' needs a structure (an opening range, a channel, a signal bar): {self.BASE or type(self).__name__} "
                             f"has none; families with one: {sorted(HEIGHTS)}")
        if self.p["f_book"] != "off" and self.p["f_bookopp"] != "off":
            raise ValueError("f_book (agree) and f_bookopp (disagree) are the two sides of ONE block: switch on one")

    def height(self):
        """The structure height at this decision (HEIGHTS), or None."""
        return None

    def blk_height(self):
        h = self.height()
        return h if h is not None and h > 0 else None

    def blk_session_volume(self):
        """(a, b, volume): the session's ANCHOR second (VOL_ANCHOR), this decision's second (both after 00:00 ET of the
        trade date) and the volume of the COMPLETED 1-minute bars inside [a, b); None outside a session."""
        if self.sid is None:
            return None
        a, b = VOL_ANCHOR.get(self.sid, self.S[self.sid][0]), _now_s(self)
        return a, b, sum(m[5] for m in self.M if a <= m[0] and m[0] + 60 <= b)

    def blk_cvol(self):
        """'hi' | 'lo' | None: the session's volume so far against the 20-day median of the same clock window."""
        sv = self.blk_session_volume()
        if sv is None:
            return None
        a, b, today = sv
        ref = cum_ref(self._cx.root, [r["date"] for r in self.dl[-VOL_DAYS:]], a, b)
        if ref is None or today == ref:
            return None
        return "hi" if today > ref else "lo"

    def allowed(self, side):
        if not super().allowed(side):
            return False
        p = self.p
        sd = 1 if side == "long" else -1
        if p["stop_mode"] == "rng" and self.blk_height() is None:
            return False                            # no structure yet: nothing to size the stop with
        if p["f_dvol"] != "off" and day_vol(self.dl, self.day) != p["f_dvol"]:
            return False
        if p["f_news"] != "off" and (self.day in release_days()) != (p["f_news"] == "yes"):
            return False
        if p["f_rsi"] != "off":
            r = rsi(self.C)
            if r is None or (r - 50.0) * sd * (1 if p["f_rsi"] == "with" else -1) <= 0:
                return False
        if p["f_cvol"] != "off" and self.blk_cvol() != p["f_cvol"]:
            return False
        if p["f_bookopp"] != "off":
            m = S.book_mean5(self._cx)
            if m is None or m * sd >= 0:
                return False
        return True

    def _dist(self, ctx, ref, struct):
        if self.p["stop_mode"] != "rng":
            return super()._dist(ctx, ref, struct)
        h = self.blk_height()
        if h is None:
            raise RuntimeError("stop_mode='rng': an order was priced without a structure height")
        return max(self.p["stop_val"] * h, 2 * ctx.tick)


# ---- ib_n: the initial balance with a range length -----------------------------------------------------------------------------
class IbN(port1.Ib):
    """port1.Ib with the range length as an input: the range = the first ib_min minutes from 09:30 (5 | 15 | 30 | 60;
    60 = ib, trade for trade). break: OCO stop entries one tick beyond the range, placed at max(range end, session start);
    a leg already through the last print is skipped. fade: as ib, from the range end. NY sessions only (nyam / mid / pm)."""
    DEFAULTS = {"ib_min": "60"}
    SCHEMA = {"ib_min": ("choice", ("5", "15", "30", "60"))}
    SCREEN_TFS = ("5", "15", "30")
    FEATURES = ()

    def _end(self) -> int:
        return OPEN + int(self.p["ib_min"]) * 60

    def fam_times(self):
        return [_hms(self._end())]

    def _ib(self):
        if self.ibh is None:
            r = self.rng(OPEN, self._end())
            if r:
                self.ibh, self.ibl = r
        return self.ibh is not None

    def fam_time(self, ctx, sec):
        s = self.sid
        if (s is None or self.p["mode"] != "break" or sec != max(self._end(), SESS[s][0])
                or not self.can_enter(ctx) or not self._ib()):
            return
        t = ctx.tick
        self._arm(ctx, [("long", self.ibh + t, self.ibl, None), ("short", self.ibl - t, self.ibh, None)])

    def fam_update(self, ctx):
        self.fade = 0
        if self.p["mode"] != "fade" or ctx.now_ns - self.t0 < self._end() * NS or not self._ib():
            return
        c = self.C[-1]
        if c > self.ibh:
            self.brk = 1
        elif c < self.ibl:
            self.brk = -1
        elif self.brk:
            self.fade, self.brk = -self.brk, 0


FAMILIES = {
    # complexity 7 = ib's 6 (range definition + NY sessions only + break: OCO stop entries + fade: close beyond + fade: first
    #                close back inside -> fade to the mid + mode) + ib_min
    "ib_n": (IbN, {}, True,
             "blocks ib_n: the 09:30 range of ib_min minutes (5 / 15 / 30 / 60), NY sessions only. break = OCO stop entries one "
             "tick beyond the range from max(range end, session start); fade = as ib (tgt_r unused). ib_min 60 = ib",
             {"rationale": "The first minutes after the 09:30 open set a range that the rest of the NY day resolves: a break of "
                           "it traps the side that leaned on it and carries; how long that first balance has to be is the "
                           "question the range length asks.",
              "complexity": 7,
              "variants": [{"ib_min": "5"}, {"ib_min": "15"}, {"ib_min": "30"}, {"ib_min": "60"}]}),
}


# ---- the wrapped families and the range-stop controls ---------------------------------------------------------------------------
def _bar_based(entry) -> bool:
    cls = entry[0]
    return len(entry) == 5 and tuple(cls.FEATURES) == () and "shift_seed" not in cls.defaults()


BASES = {n: e for m in (port1, port2, port3, round1, timed) for n, e in m.FAMILIES.items() if _bar_based(e)}
BASES.update(FAMILIES)


def _wrap(name: str, cls):
    body = {"__module__": __name__, "__qualname__": f"B_{name}", "BASE": name,
            "__doc__": f"{name} with the blocks: Blocks in front of {cls.__module__}.{cls.__name__} (all blocks default off)."}
    if name in HEIGHTS:
        body["STRUCT"], body["height"] = HEIGHTS[name][0], HEIGHTS[name][1]
    return type(f"B_{name}", (Blocks, cls), body)


def _control(name: str):
    what, fn, keys = HEIGHTS[name]
    cls = BASES[name][0]
    d, sc = cls.defaults(), cls.schema()
    body = {"__module__": __name__, "__qualname__": f"R_{name}", "BASE": name, "STRUCT": what, "height": fn,
            "DEFAULTS": {k: d[k] for k in keys}, "SCHEMA": {k: sc[k] for k in keys if k in sc},
            "__doc__": f"Random-entry control of a range stop on {name}: l2ref.Random (a market entry at a tf close with "
                       f"probability p_entry, random side) whose 'rng' stop reads {what}."}
    return type(f"R_{name}", (Blocks, l2ref.Random), body)


WRAPPED = {n: _wrap(n, e[0]) for n, e in BASES.items()}     # family name -> the class an idea spec runs
CONTROLS = {n: _control(n) for n in HEIGHTS}                # family name -> its range-stop random-entry control
globals().update({c.__name__: c for c in list(WRAPPED.values()) + list(CONTROLS.values())})      # workers import them by name
