"""The day's geometry for the "levels" strategies, and what each booked account gets of it.

One definition, used by the desk (homebase/leveltimer.py) and by the tester strategies
(homebase/strategies/prop_nq.py), so a backtest and a live fire cannot drift apart.

  atr_straddle   anchor = the last print before the fire; buy stop anchor + off_atr x ATR, sell stop
                 anchor - off_atr x ATR.            (nyam 09:30 / pm 13:30 straddles)
  orb            the 1-minute bars of the or_min minutes before the fire: buy stop high + 1 tick, sell stop
                 low - 1 tick.                       (11:05 opening-range breakout)

Both: stop = sl_atr x ATR from the TRIGGER (floored at 2 ticks), one OCO pair, prices on the tick grid.  The
desk then re-prices stop and take to the actual fill (engine._move_brackets), like the tester's
move_brackets_to_fill.  The stop distance is PER LEG (sl_pts = the buy leg's, sl_sell_pts = the sell leg's): the
research placed the stop at tick(raw trigger -/+ 3 ATR) and then shifted it by (fill - raw trigger), and the
straddle's raw trigger (anchor +/- off_atr x ATR) is not on the tick grid, so after rounding the two legs' stops
can sit a tick apart in distance (leg_stop below).  Desk and tester use the same number, so they match the
research's stop price to the tick.  The take is a distance from the fill: take_points(day_take / target_take, qty).

Pure logic; no I/O.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Optional

from .atrbars import MIN_MS, WARM_BARS, TickBars
from .backtest.tape import EQUITY_EARLY_CLOSE_ET, EQUITY_INDEX_ROOTS, _build_early_closes
from .contracts import point_value, tick_size
from .dayrules import DayBook, DayRules, ceil_to_tick, size_for_profit, take_points
from .rules import _to_tick

SHAPES = ("atr_straddle", "orb")


@dataclass(frozen=True)
class Geometry:
    shape: str
    upper: float            # buy stop
    lower: float            # sell stop
    sl_pts: float           # stop distance from the trigger
    atr: float
    atr_bars: int
    anchor: Optional[float] = None       # straddle: the last print before the fire
    range_hi: Optional[float] = None     # orb: the opening range
    range_lo: Optional[float] = None
    last_px: Optional[float] = None      # the last print before the fire
    sl_sell_pts: Optional[float] = None  # the sell leg's stop distance (None: the same as sl_pts, the buy leg's)

    def sl_for(self, side: str) -> float:
        """Stop distance from the trigger / fill of the leg that fills: side "Buy" | "Sell" (or long | short)."""
        sell = str(side).lower() in ("sell", "short")
        return self.sl_pts if (not sell or self.sl_sell_pts is None) else self.sl_sell_pts

    @property
    def sl_max(self) -> float:
        return max(self.sl_pts, self.sl_sell_pts if self.sl_sell_pts is not None else self.sl_pts)

    def to_dict(self) -> dict:
        return asdict(self)


def leg_stop(raw_trigger: float, atr: float, sl_atr: float, tick: float, buy: bool) -> float:
    """One leg's stop distance from its trigger/fill, exactly as the research's tester ran it: the stop order
    is tick(raw trigger -/+ d) (d = sl_atr x ATR, floored at 2 ticks) and it moves by (fill - raw trigger) with the
    fill on the tick grid, so the stop sits tick(raw trigger - tick(raw trigger - d)) from the fill (buy leg;
    mirrored for the sell leg).  On a raw trigger that is already on the grid this is tick(d)."""
    d = max(sl_atr * atr, 2 * tick)
    if buy:
        return _to_tick(raw_trigger - _to_tick(raw_trigger - d, tick), tick)
    return _to_tick(_to_tick(raw_trigger + d, tick) - raw_trigger, tick)


def straddle_geometry(anchor: float, atr: float, off_atr: float, sl_atr: float, tick: float,
                      atr_bars: int = 0) -> Geometry:
    off = off_atr * atr
    return Geometry("atr_straddle", _to_tick(anchor + off, tick), _to_tick(anchor - off, tick),
                    leg_stop(anchor + off, atr, sl_atr, tick, True), atr, atr_bars,
                    anchor=anchor, last_px=anchor,
                    sl_sell_pts=leg_stop(anchor - off, atr, sl_atr, tick, False))


def orb_geometry(hi: float, lo: float, atr: float, sl_atr: float, tick: float,
                 last_px: Optional[float] = None, atr_bars: int = 0) -> Geometry:
    return Geometry("orb", _to_tick(hi + tick, tick), _to_tick(lo - tick, tick),
                    leg_stop(hi + tick, atr, sl_atr, tick, True), atr, atr_bars,
                    range_hi=hi, range_lo=lo, last_px=last_px,
                    sl_sell_pts=leg_stop(lo - tick, atr, sl_atr, tick, False))


def compute_geometry(cfg, bars: TickBars, fire_ms: int, tick: float,
                     last_ms: Optional[int] = None) -> tuple[Optional[Geometry], str]:
    """The day's geometry from the day's bars at `fire_ms`, or (None, why not).  The ATR and the opening
    range are the bars CLOSED by the fire; the anchor / last print is the last one stamped before `last_ms`
    (default: the fire -- a late fire passes "now": the stops sit around the market as it is).  Fail-safe:
    no ATR, fewer than WARM_BARS closed bars, no anchor / no range, or a leg already through the last print
    -> no fire."""
    atr, n = bars.atr(int(cfg.atr_tf), fire_ms)
    if atr is None or n < WARM_BARS or atr <= 0:
        return None, f"no ATR ({n} closed {cfg.atr_tf}-minute bars of the day)"
    last = bars.last_before(fire_ms if last_ms is None else last_ms)
    if last is None:
        return None, "no print before the fire"
    if cfg.shape == "atr_straddle":
        g = straddle_geometry(last, atr, float(cfg.off_atr), float(cfg.sl_atr), tick, n)
    elif cfg.shape == "orb":
        hi, lo, k = bars.range(fire_ms - int(cfg.or_min) * MIN_MS, fire_ms)
        if k == 0:
            return None, f"no 1-minute bars in the {cfg.or_min}-minute opening range"
        g = orb_geometry(hi, lo, atr, float(cfg.sl_atr), tick, last, n)
    else:
        return None, f"unknown shape {cfg.shape!r}"
    if not (g.upper > last > g.lower):          # the tester's _arm skips such a leg; the desk places both or none
        return None, f"a leg is already through the last print ({last}: {g.lower}..{g.upper})"
    return g, "ok"


def is_early_close_skip(root: str, d: dt.date, flat_et: str) -> bool:
    """True on a half day (13:15 ET close: the day after Thanksgiving, Dec 24, Jul 3 -- the tester's own
    calendar, backtest/tape.py) when the strategy's flat time is after the early close: it would arm, or
    have to flatten, in a closed market (an open position would carry past the close).  The calendar is
    built for the day's own year, not only the tester's table."""
    if root not in EQUITY_INDEX_ROOTS or d not in _build_early_closes([d.year]):
        return False
    return flat_et[:5] > EQUITY_EARLY_CLOSE_ET


@dataclass(frozen=True)
class AccountLeg:
    account: str
    qty: int
    tp_pts: float                 # from the fill
    take_usd: Optional[float]     # the net $ the take is sized for (None: the fallback target)
    take_src: str                 # day_take | target_take | fallback
    stop_usd: float               # worst-case loss at the stop, before costs

    def to_dict(self) -> dict:
        return asdict(self)


def account_leg(cfg, account: str, book_qty: int, rules: DayRules, book: DayBook, geo: Geometry,
                profit: Optional[float]) -> tuple[Optional[AccountLeg], str]:
    """What one account gets: qty by profit tier (capped at its booked qty), a take sized to the lower of
    day_take and target_take net of what the day already closed.  (None, why) = this account sits out."""
    tick, pv = tick_size(cfg.symbol) or 0.25, point_value(cfg.symbol) or 0.0
    if pv <= 0:
        return None, f"no point value for {cfg.symbol}"
    if book.locked:
        return None, f"stopped for the day ({book.locked})"
    if cfg.size_tiers:
        if profit is None:
            qty = size_for_profit(cfg.size_tiers, float("-inf"), book_qty)   # unknown standing: the smallest size
        else:
            qty = size_for_profit(cfg.size_tiers, profit, book_qty)
    else:
        qty = int(book_qty)
    if qty <= 0:
        return None, "size is 0"
    need = book.take_net(rules)
    if need is not None:
        need -= book.closed_net                      # the day total is what counts: closed trades already paid part
        if need <= 0:
            return None, "the day's take is already in"
        pts = take_points(need, qty, pv, cfg.fee_rt, tick)
        src = ("target_take" if rules.target_take and book.target_level is not None
               and (not rules.day_take or book.target_level < rules.day_take) else "day_take")
        return AccountLeg(account, qty, pts, round(need, 2), src, round(geo.sl_max * pv * qty, 2)), "ok"
    if rules.target_take and not rules.day_take:
        return None, "target_take has no level today (standing unknown, min days, consistency or passed)"
    pts = ceil_to_tick(float(cfg.tgt_r) * geo.sl_pts, tick)
    return AccountLeg(account, qty, pts, None, "fallback", round(geo.sl_max * pv * qty, 2)), "ok"
