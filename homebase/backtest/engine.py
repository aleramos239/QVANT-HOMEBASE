"""The Strategy Tester's tick engine: one strict-order pass over a session's prints.

House fill law (research/nq_930_straddle_ticks.py L22-31, generalised):
  * STOP orders (stop entries and stop-losses) are market-on-touch. A buy stop
    triggers on the first print >= its price and fills at max(price, print) + slip;
    a sell stop on the first print <= its price, at min(price, print) - slip.
    Gapping through the level costs the gap.
  * LIMIT orders (limit entries and targets) are resting limits that need 1-TICK
    PENETRATION: a buy limit fills only on a print <= price - tick, a sell limit
    only on a print >= price + tick, AT the limit price, no slip.
  * MARKET orders fill at the first print at/after they go live, +/- slip.
  * Commission is flat per round turn per contract.
  * Prints sharing one ts_ns resolve in ROW ORDER (the tape is stable-sorted);
    orders that trigger on the same print fill oldest first.
Orders the strategy sends go live `placement_ms` after the event that sent them.
Scheduled events (session start, bar closes, on_time) run BEFORE the first print
at or after their time; ctx.cancel / ctx.flatten act at once, so a flat fills on
that first print at or after the time. A position's SL/TP ride on the entry (OSO)
and can trigger from the print AFTER the entry print.
  * MAE/MFE are measured against the entry PRINT (the segment starts at
    `pos.entry_i`, the fill's own index), not the (slipped) fill price -- a stop
    entry's MAE therefore always includes at least the entry print's own slippage.
  * Every order/SL/TP price is snapped to the tick grid with `to_tick` when it is
    created or re-priced, and every `>=`/`<=` price comparison (touch, 1-tick
    penetration) is epsilon-tolerant (see `tick_cmp`) -- raw float64 arithmetic on
    a non-power-of-two tick (CL 0.01, GC 0.1, SI 0.005) routinely lands a hair off
    the clean grid value (e.g. `64.01 + 0.01 == 64.02000000000001`), which would
    otherwise reject a real print sitting exactly at that level.
  * A strategy callback that raises is caught for that session only: the session
    is recorded as skipped (`skip = "strategy error: <msg>"`), not propagated.
    Every working order is cancelled and any open position is flattened AT THE
    CURRENT PRINT (not run to end of day) so the crash cannot keep trading; the
    session's trades are then dropped from the result entirely (Item 3) — a
    crashed session is counted under `skipped_by_error`, never as a quiet trade.

Stdlib only (array + bisect): the desk's venv carries no numpy.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass, field

from ..contracts import exec_ok, point_value, tick_size
from .tape import et_ns

ENGINE_VERSION = "tick-2"      # tick-2: a strategy's own no-trade day is a flat 0.0 on the Sharpe grid (review C1)
SIDE = {"long": 1, "short": -1}
NAME = {1: "long", -1: "short"}
ROLES = ("anchor", "entry", "sl", "tp", "level")   # Ctx.hline: what the page styles a level by
CHUNK = 4096                    # prefilter block for the trigger scan


def to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


def tick_cmp(a: float, b: float, tick: float) -> int:
    """Compare a to b on a tick grid, tolerant of float64 noise (eps = tick*1e-6):
    -1 if a < b, 0 if equal within eps, 1 if a > b. Every >=/<= price comparison
    in the fill law goes through this (a raw `a >= b` breaks on grids like CL's
    0.01 or GC's 0.1, where `64.01 + 0.01 == 64.02000000000001`)."""
    eps = tick * 1e-6
    if a > b + eps:
        return 1
    if a < b - eps:
        return -1
    return 0


def first_at_or_above(px, level: float, a: int, b: int, tick: float) -> int:
    """First index k in [a, b) with px[k] >= level (tick-grid tolerant), else b."""
    k = a
    while k < b:
        e = min(k + CHUNK, b)
        if tick_cmp(max(px[k:e]), level, tick) >= 0:
            for i in range(k, e):
                if tick_cmp(px[i], level, tick) >= 0:
                    return i
        k = e
    return b


def first_at_or_below(px, level: float, a: int, b: int, tick: float) -> int:
    """First index k in [a, b) with px[k] <= level (tick-grid tolerant), else b."""
    k = a
    while k < b:
        e = min(k + CHUNK, b)
        if tick_cmp(min(px[k:e]), level, tick) <= 0:
            for i in range(k, e):
                if tick_cmp(px[i], level, tick) <= 0:
                    return i
        k = e
    return b


@dataclass
class Costs:
    commission_rt: float = 4.00     # USD per round turn per contract
    slippage_ticks: float = 1.0     # per side, on market and stop fills only


@dataclass(eq=False)
class Order:
    id: int
    side: int                       # +1 buy, -1 sell
    kind: str                       # "stop" | "limit" | "market"
    price: float | None             # trigger (stop) / limit price; None for market
    qty: int
    min_i: int                      # first print index this order may fill on
    role: str = "entry"             # "entry" | "sl" | "tp"
    sl: float | None = None         # entries: bracket levels, absolute prices
    tp: float | None = None
    tp_rr: float | None = None      # entries: TP re-derived from the fill at this RR
    ref: float | None = None        # entries: the price the brackets were sized from
    oco: int | None = None
    status: str = "working"         # working | filled | cancelled
    pos: "Position | None" = None   # exits: the position they close
    # Recording only (never read by the fill law): what an ENTRY actually became, so a strategy
    # can draw the bracket as it ended up -- re-priced to the fill -- next to the one it planned.
    fill_px: float | None = None
    fill_sl: float | None = None
    fill_tp: float | None = None
    fill_ms: int | None = None      # when it filled (the print's time): where the moved bracket starts
    # run controls only (controls.py): ("dist" | "none" | "own", pts) for the stop, same for the target
    ov: tuple | None = None


@dataclass(eq=False)
class Position:
    side: int
    qty: int
    entry_px: float
    entry_i: int
    order_price: float | None
    sl: Order | None = None
    tp: Order | None = None
    be: Order | None = None         # run controls: the breakeven's trigger (a touch, never a fill)
    trail: Order | None = None      # run controls: the trailing stop's next ratchet (a touch)


@dataclass
class Bar:
    start_ns: int
    end_ns: int
    o: float
    h: float
    l: float
    c: float
    v: int


@dataclass
class Trade:
    date: str
    side: str
    qty: int
    entry_ns: int
    entry_price: float
    exit_ns: int
    exit_price: float
    exit_reason: str                # tp | sl | time | eod
    order_price: float | None       # the entry's trigger / limit (None: market)
    sl: float | None                # the brackets as they rode the position
    tp: float | None
    gross: float
    commission: float
    net: float
    mae_pts: float
    mfe_pts: float
    mae_usd: float
    mfe_usd: float
    bars: int                       # 1-minute bars touched, entry to exit
    seconds: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SessionResult:
    date: str
    trades: list = field(default_factory=list)
    plots: dict = field(default_factory=dict)     # name -> [[t_ms, value], ...]
    hlines: list = field(default_factory=list)    # [{name, price, date, role, t_ms, end_ms}]
    marks: list = field(default_factory=list)     # [{name, t_ms, price, text, side, pos}]: ctx.mark, drawn on the chart only
    skip: str | None = None                       # the strategy's reason for no trade
    blocked: dict = field(default_factory=dict)   # run controls: entries refused, by reason


class Ctx:
    """What a strategy sees. Created per session by run_session."""

    def __init__(self, sim: "_Sim", qty: int, daily: list):
        self._s = sim
        self.root = sim.root
        self.date = sim.date
        self.tick = sim.tick
        self.point_value = sim.pv
        self.qty = qty
        self.daily = daily
        self.move_brackets_to_fill = False

    @property
    def now_ns(self) -> int:
        return self._s.now

    @property
    def last_price(self) -> float | None:
        """The last print strictly before the current event time (in the window)."""
        s = self._s
        return s.px[s.i - 1] if s.i > s.lo else None

    @property
    def flat(self) -> bool:
        return not self._s.positions

    def _entry(self, kind, side, price, qty, sl, tp, tp_rr, ref) -> Order:
        if side not in SIDE:
            raise ValueError(f"side must be 'long' or 'short', not {side!r}")
        tick = self._s.tick
        price = None if price is None else to_tick(price, tick)
        sl = None if sl is None else to_tick(sl, tick)
        tp = None if tp is None else to_tick(tp, tick)
        n = int(qty or self.qty)
        s, ov = self._s, None
        if s.ctl is not None:                       # run controls: refuse here, or re-size the brackets
            why = s.gate(s.now, SIDE[side])
            if not why:
                ov, sl, tp, tp_rr, why = s.override(SIDE[side], price, ref, sl, tp, tp_rr)
            if why:
                s.refuse(why)
                return Order(0, SIDE[side], kind, price, n, 0, sl=sl, tp=tp, tp_rr=tp_rr, ref=ref,
                             status="cancelled")
        return s.new_order(SIDE[side], kind, price, n, sl=sl, tp=tp, tp_rr=tp_rr, ref=ref, ov=ov)

    def stop_entry(self, side: str, price: float, qty: int | None = None, sl=None, tp=None,
                   tp_rr=None) -> Order:
        return self._entry("stop", side, price, qty, sl, tp, tp_rr, price)

    def limit_entry(self, side: str, price: float, qty: int | None = None, sl=None, tp=None,
                    tp_rr=None) -> Order:
        return self._entry("limit", side, price, qty, sl, tp, tp_rr, price)

    def market(self, side: str, qty: int | None = None, sl=None, tp=None, tp_rr=None,
               ref: float | None = None) -> Order:
        return self._entry("market", side, None, qty, sl, tp, tp_rr, ref)

    def oco(self, *orders: Order) -> None:
        g = orders[0].id
        for o in orders:
            o.oco = g

    def cancel(self, order: Order) -> None:
        self._s.cancel(order)

    def flatten(self, reason: str = "time") -> None:
        self._s.flatten(reason)

    def plot(self, name: str, t_ns: int, value: float) -> None:
        self._s.res.plots.setdefault(name, []).append([t_ns // 1_000_000, value])

    def mark(self, name: str, t_ns: int, price: float, text: str = "", side: str = "", pos: str = "") -> None:
        """A point the strategy wants SEEN on the chart (a divergence, a signal that was not traded): a marker on
        the bar covering `t_ns`, for the chart only -- it never reaches an order. `side` is "long" | "short" | ""
        (colour); `pos` is "above" | "below" (default: above for a short, below otherwise). `name` groups the
        marks of one kind (the legend of the page shows it on hover)."""
        if price != price or price in (float("inf"), float("-inf")):
            return
        self._s.res.marks.append({"name": str(name), "t_ms": int(t_ns) // 1_000_000, "price": price,
                                  "text": str(text)[:12], "side": side if side in ("long", "short") else "",
                                  "pos": pos if pos in ("above", "below") else ("above" if side == "short" else "below")})

    def hline(self, name: str, price: float, role: str = "level") -> dict:
        """Record a level the strategy placed this session, for the chart only -- it never
        reaches an order. `role` is one of ROLES, so the page can style it without parsing
        the name. Returns the record, which a strategy may still rename (the straddle marks
        the leg that never filled) before the session ends."""
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}, not {role!r}")
        # t_ms: when the strategy placed it; the page starts the line there (end_ms, the session
        # window's close, is stamped by run_session) instead of at the session's first bar.
        rec = {"name": name, "price": price, "date": self.date.isoformat(), "role": role,
               "t_ms": self._s.now // 1_000_000}
        self._s.res.hlines.append(rec)
        return rec

    def skip(self, reason: str) -> None:
        self._s.res.skip = reason


class _Sim:
    def __init__(self, root, d, ts, px, lo, hi, costs: Costs, placement_ms: int, exec_root: str = "",
                 controls=None):
        self.root, self.date = root, d
        self.ts, self.px, self.lo, self.hi = ts, px, lo, hi
        self.tick = tick_size(root)
        self.pv = point_value(exec_root or root) or 0.0     # the dollars are the contract's the ORDERS go to (a micro's)
        self.slip = costs.slippage_ticks * self.tick
        self.comm = costs.commission_rt
        self.place_ns = placement_ms * 1_000_000
        self.i = lo                   # next print to process
        self.now = 0
        self.orders: list[Order] = []  # working, in creation order
        self.positions: list[Position] = []
        self.res = SessionResult(d.isoformat())
        self._ids = 0
        self._ctx: Ctx | None = None   # set by run_session
        self.ctl = controls            # run controls (controls.Controls) or None: the engine's one old path
        self.sig_min = 1               # run controls: the signal bar (minutes) a candle stop reads (run_session sets it)
        self.lines: dict = {}          # run controls: bar end ns -> (close, line) for exit_line (run_session fills it)
        self.st = {"entries": 0, "wins": 0, "losses": 0, "consec": 0, "pnl": 0.0, "last_loss": None}

    # ---- orders
    def new_order(self, side, kind, price, qty, **kw) -> Order:
        self._ids += 1
        o = Order(self._ids, side, kind, price, qty,
                  bisect_left(self.ts, self.now + self.place_ns, self.i, self.hi), **kw)
        self.orders.append(o)
        return o

    def cancel(self, o: Order) -> None:
        if o.status == "working":
            o.status = "cancelled"
            self.orders.remove(o)

    # ---- run controls (controls.py): all of this is skipped when `self.ctl` is None
    def refuse(self, why: str) -> None:
        self.res.blocked[why] = self.res.blocked.get(why, 0) + 1

    def gate(self, t: int, side: int) -> str | None:
        """Why a NEW entry on `side` may not be taken at time t (ns), or None."""
        c, st, d = self.ctl, self.st, self.date
        if c.entry_from and t < et_ns(d, c.entry_from):
            return "outside the entry window"
        if (c.entry_to and t >= et_ns(d, c.entry_to)) or (c.flat_at and t >= et_ns(d, c.flat_at)):
            return "outside the entry window"
        if c.direction != "both" and side != SIDE[c.direction]:
            return "direction"
        if c.max_trades and st["entries"] >= c.max_trades:
            return "max trades a day"
        if c.stop_wins and st["wins"] >= c.stop_wins:
            return "stopped after wins"
        if c.stop_losses and st["losses"] >= c.stop_losses:
            return "stopped after losses"
        if c.max_consec_losses and st["consec"] >= c.max_consec_losses:
            return "losses in a row"
        if c.day_loss and st["pnl"] <= -c.day_loss:
            return "daily loss reached"
        if c.day_profit and st["pnl"] >= c.day_profit:
            return "daily profit reached"
        if c.cooldown_min and st["last_loss"] is not None and t < st["last_loss"] + c.cooldown_min * 60_000_000_000:
            return "cooling off"
        return None

    def atr(self, minutes: int, period: int) -> float | None:
        """Mean true range of the last `period` closed `minutes` bars before now (the bar in progress is not
        used), looking back over the whole tape (overnight included). None when there are not that many."""
        step = minutes * 60_000_000_000
        b1 = self.now - self.now % step
        j1 = bisect_left(self.ts, b1, 0, self.hi)
        rows, guard = [], period * 4 + 4
        while len(rows) < period + 1 and guard > 0 and j1 > 0:
            b0 = b1 - step
            j0 = bisect_left(self.ts, b0, 0, j1)
            if j1 > j0:
                seg = self.px[j0:j1]
                rows.append((max(seg), min(seg), seg[-1]))
            b1, j1, guard = b0, j0, guard - 1
        if len(rows) < period + 1:
            return None
        rows.reverse()
        trs = [max(h - l, abs(h - pc), abs(l - pc)) for (h, l, _), (_, _, pc) in zip(rows[1:], rows)]
        return sum(trs) / len(trs)

    def candle(self) -> tuple | None:
        """(low, high) of the last CLOSED signal bar (sig_min minutes) before now -- at a bar's close, that bar -- or None."""
        step = self.sig_min * 60_000_000_000
        b1 = self.now - self.now % step
        j0, j1 = bisect_left(self.ts, b1 - step, 0, self.hi), bisect_left(self.ts, b1, 0, self.hi)
        if j1 <= j0:
            return None
        seg = self.px[j0:j1]
        return min(seg), max(seg)

    def set_stop(self, pos: "Position", price: float, k: int) -> None:
        """Breakeven / trailing: the position's stop to `price` -- only tighter, and only at least a tick on the safe side
        of print k (a stop at or through the price would be refused at a broker); it can trigger from the NEXT print."""
        t = self.tick
        price = to_tick(price, t)
        if tick_cmp(pos.side * (self.px[k] - price), t, t) < 0:
            return
        if pos.sl is not None:
            if tick_cmp(pos.side * (price - pos.sl.price), 0.0, t) <= 0:
                return
            pos.sl.price, pos.sl.min_i = price, max(pos.sl.min_i, k + 1)
            return
        self._ids += 1
        pos.sl = Order(self._ids, -pos.side, "stop", price, pos.qty, k + 1, role="sl", pos=pos)
        self.orders.append(pos.sl)

    def touch(self, pos: "Position", role: str, level: float, k: int) -> Order:
        """A breakeven / trailing trigger: a stop-type touch on the position's own side (a long's at or above the level),
        that moves the stop when it triggers and never fills."""
        self._ids += 1
        o = Order(self._ids, pos.side, "stop", to_tick(level, self.tick), pos.qty, k + 1, role=role, pos=pos)
        self.orders.append(o)
        return o

    def arm(self, pos: "Position", k: int) -> None:
        """Run controls on a fresh position: its breakeven trigger and its trailing stop."""
        c = self.ctl
        if c.be_after_pts:
            pos.be = self.touch(pos, "be", pos.entry_px + pos.side * c.be_after_pts, k)
        if c.trail_pts:
            if c.trail_after_pts:
                pos.trail = self.touch(pos, "trail", pos.entry_px + pos.side * c.trail_after_pts, k)
            else:
                self.set_stop(pos, pos.entry_px - pos.side * c.trail_pts, k)
                pos.trail = self.touch(pos, "trail", pos.entry_px + pos.side * self.tick, k)

    def ratchet(self, o: Order, k: int) -> None:
        """A breakeven / trailing trigger touched at print k: the stop moves (BE once; the trail follows print k, the best
        since the last ratchet, and waits for the next tick beyond it)."""
        pos, c = o.pos, self.ctl
        if o.role == "be":
            pos.be = None
            self.set_stop(pos, pos.entry_px + pos.side * c.be_offset_ticks * self.tick, k)
            return
        best = self.px[k]
        self.set_stop(pos, best - pos.side * c.trail_pts, k)
        pos.trail = self.touch(pos, "trail", best + pos.side * self.tick, k)

    def override(self, side: int, price, ref, sl, tp, tp_rr):
        """The stop / target the run controls ask for, as (ov, sl, tp, tp_rr, refusal). The planned levels are
        measured from the entry's own reference; `_fill` re-measures them from the fill."""
        c = self.ctl
        if c.stop_mode == "own" and c.target_mode == "own":
            return None, sl, tp, tp_rr, None
        r = ref if ref is not None else price
        if r is None:
            r = self.px[self.i - 1] if self.i > self.lo else None
        if r is None:
            return None, sl, tp, tp_rr, "no price to size the bracket from"
        a = None
        if c.stop_mode == "atr" or c.target_mode == "atr":
            a = self.atr(c.atr_minutes, c.atr_period)
            if a is None:
                return None, sl, tp, tp_rr, "atr warming up"

        def dist(mode, pts, mult):
            return max(pts if mode == "fixed" else mult * (a or 0.0), self.tick)

        ov_sl, ov_tp = ("own", 0.0), ("own", 0.0)
        if c.stop_mode == "none":
            sl, ov_sl = None, ("none", 0.0)
        elif c.stop_mode == "candle":
            ext = self.candle()
            if ext is None:
                return None, sl, tp, tp_rr, "no closed signal candle"
            buf = c.stop_candle_ticks * self.tick
            sl = to_tick(ext[0] - buf if side > 0 else ext[1] + buf, self.tick)
            ov_sl = ("level", sl)
        elif c.stop_mode != "own":
            d = dist(c.stop_mode, c.stop_pts, c.stop_atr)
            sl, ov_sl = to_tick(r - side * d, self.tick), ("dist", d)
        if c.target_mode != "own":
            tp_rr = None
            if c.target_mode == "none":
                tp, ov_tp = None, ("none", 0.0)
            elif c.target_mode == "rr":
                tp_rr, tp = c.target_rr, None
            else:
                d = dist(c.target_mode, c.target_pts, c.target_atr)
                tp, ov_tp = to_tick(r + side * d, self.tick), ("dist", d)
        return (ov_sl, ov_tp), sl, tp, tp_rr, None

    def control(self, what: str) -> None:
        """A scheduled control event: flat_at, the end of the entry window, or the minute's time-stop check."""
        if what == "flat":
            self.flatten("time")
        elif what == "close":
            for o in [o for o in self.orders if o.role == "entry"]:
                self.cancel(o)
                self.refuse("outside the entry window")
        elif what == "line" and self.positions:
            v = self.lines.get(self.now)                    # this bar's close and the line, both at its close
            if v is not None:
                close, line = v
                k = self.i if self.i < self.hi else self.hi - 1
                for pos in [p for p in self.positions if self.ts[p.entry_i] < self.now and p.side * (close - line) < 0]:
                    self._close(pos, to_tick(self.px[k] - pos.side * self.slip, self.tick), k, "line")
        elif what == "hold" and self.positions:
            limit = self.ctl.max_hold_min * 60_000_000_000
            k = self.i if self.i < self.hi else self.hi - 1
            for pos in [p for p in self.positions if self.now - self.ts[p.entry_i] >= limit]:
                self._close(pos, to_tick(self.px[k] - pos.side * self.slip, self.tick), k, "hold")

    def _trigger(self, o: Order, a: int, b: int) -> int:
        if o.kind == "market":
            return a
        if o.kind == "stop":
            return (first_at_or_above(self.px, o.price, a, b, self.tick) if o.side > 0
                    else first_at_or_below(self.px, o.price, a, b, self.tick))
        lvl = (to_tick(o.price - self.tick, self.tick) if o.side > 0
               else to_tick(o.price + self.tick, self.tick))
        return (first_at_or_below(self.px, lvl, a, b, self.tick) if o.side > 0
                else first_at_or_above(self.px, lvl, a, b, self.tick))

    def _fill_price(self, o: Order, p: float) -> float:
        if o.kind == "limit":
            return o.price
        if o.kind == "stop":
            raw = max(o.price, p) + self.slip if o.side > 0 else min(o.price, p) - self.slip
        else:
            raw = p + o.side * self.slip
        return to_tick(raw, self.tick)

    def advance(self, j: int) -> None:
        """Process prints [i, j): fill whatever triggers, earliest print first."""
        while self.orders and self.i < j:
            best_k, best = j, None
            for o in self.orders:
                a = max(self.i, o.min_i)
                if a >= best_k:
                    continue
                k = self._trigger(o, a, best_k)
                if k < best_k:
                    best_k, best = k, o
            if best is None:
                break
            self._fill(best, best_k)
            self.i = best_k           # other orders may still trigger on this same print
        self.i = max(self.i, j)

    def _fill(self, o: Order, k: int) -> None:
        if o.role in ("be", "trail"):                       # run controls: a touch moves the stop, nothing fills
            o.status = "filled"
            self.orders.remove(o)
            self.ratchet(o, k)
            return
        if self.ctl is not None and o.role == "entry":
            why = self.gate(int(self.ts[k]), o.side)        # a working order meets the rules at its FILL
            if why:
                self.cancel(o)
                self.refuse(why)
                return
            self.st["entries"] += 1
        fill = self._fill_price(o, self.px[k])
        o.status = "filled"
        self.orders.remove(o)
        if o.role != "entry":
            self._close(o.pos, fill, k, o.role)
            return
        if o.oco is not None:
            for x in [x for x in self.orders if x.oco == o.oco]:
                self.cancel(x)
        pos = Position(o.side, o.qty, fill, k, o.price)
        sl, tp = o.sl, o.tp
        # Fix round 1 ruling: the SL moves FIRST (keeping its distance to `ref`),
        # independent of tp_rr; only then is a tp_rr target derived, from the
        # fill and that (possibly moved) SL's distance -- not from the raw entry
        # sl and an unrelated gap-affected fill.
        if self._ctx.move_brackets_to_fill and o.ref is not None:
            d = fill - o.ref
            sl = None if sl is None else to_tick(sl + d, self.tick)
            if o.tp_rr is None:
                tp = None if tp is None else to_tick(tp + d, self.tick)
        if o.ov is not None:                                # run controls: fixed / ATR distances from the FILL
            (m_sl, d_sl), (m_tp, d_tp) = o.ov
            if m_sl == "dist":
                sl = to_tick(fill - o.side * d_sl, self.tick)
            elif m_sl == "level":                           # the candle's extreme: at least a tick past the fill
                sl = d_sl if tick_cmp(o.side * (fill - d_sl), self.tick, self.tick) >= 0 else to_tick(fill - o.side * self.tick, self.tick)
            elif m_sl == "none":
                sl = None
            if m_tp == "dist":
                tp = to_tick(fill + o.side * d_tp, self.tick)
            elif m_tp == "none":
                tp = None
        if o.tp_rr is not None and sl is not None:
            tp = to_tick(fill + o.side * o.tp_rr * abs(fill - sl), self.tick)
        self._ids += 1
        if sl is not None:
            pos.sl = Order(self._ids, -o.side, "stop", sl, o.qty, k + 1, role="sl", pos=pos)
            self.orders.append(pos.sl)
        self._ids += 1
        if tp is not None:
            pos.tp = Order(self._ids, -o.side, "limit", tp, o.qty, k + 1, role="tp", pos=pos)
            self.orders.append(pos.tp)
        o.fill_px, o.fill_sl, o.fill_tp = fill, sl, tp      # recording only (Order.fill_px)
        o.fill_ms = int(self.ts[k]) // 1_000_000
        self.positions.append(pos)
        if self.ctl is not None:
            self.arm(pos, k)

    def _close(self, pos: Position, fill: float, k: int, reason: str) -> None:
        for x in (pos.sl, pos.tp, pos.be, pos.trail):
            if x is not None:
                self.cancel(x)
        self.positions.remove(pos)
        seg = self.px[pos.entry_i:k + 1]
        hi, lo = max(seg), min(seg)
        s, e = pos.side, pos.entry_px
        mfe = max(0.0, (hi - e) if s > 0 else (e - lo))
        mae = max(0.0, (e - lo) if s > 0 else (hi - e))
        gross = s * (fill - e) * self.pv * pos.qty
        comm = self.comm * pos.qty
        t0, t1 = self.ts[pos.entry_i], self.ts[k]
        self.res.trades.append(Trade(
            date=self.date.isoformat(), side=NAME[s], qty=pos.qty,
            entry_ns=t0, entry_price=e, exit_ns=t1, exit_price=fill, exit_reason=reason,
            order_price=pos.order_price,
            sl=pos.sl.price if pos.sl else None, tp=pos.tp.price if pos.tp else None,
            gross=round(gross, 2), commission=round(comm, 2), net=round(gross - comm, 2),
            mae_pts=round(mae, 6), mfe_pts=round(mfe, 6),
            mae_usd=round(mae * self.pv * pos.qty, 2), mfe_usd=round(mfe * self.pv * pos.qty, 2),
            bars=int(t1 // 60_000_000_000 - t0 // 60_000_000_000 + 1),
            seconds=round((t1 - t0) / 1e9, 3)))
        if self.ctl is not None:
            net, st = gross - comm, self.st
            st["pnl"] += net
            if net > 0:
                st["wins"] += 1
                st["consec"] = 0
            elif net < 0:
                st["losses"] += 1
                st["consec"] += 1
                st["last_loss"] = t1

    def flatten(self, reason: str) -> None:
        for o in list(self.orders):
            if o.role == "entry":
                self.cancel(o)
        if not self.positions:
            return
        k = self.i if self.i < self.hi else self.hi - 1
        if k < self.i:
            reason = "eod"
        for pos in list(self.positions):
            self._close(pos, to_tick(self.px[k] - pos.side * self.slip, self.tick), k, reason)


def build_bars(ts, px, size, lo: int, hi: int, t0: int, t1: int, minutes: int) -> list[Bar]:
    """Time bars from prints [lo, hi), aligned to multiples of `minutes` in epoch
    time (ET-aligned: offsets are whole hours), covering [t0, t1). Empty buckets
    make no bar."""
    step = minutes * 60_000_000_000
    out = []
    b0 = t0 - t0 % step
    i0 = bisect_left(ts, b0, lo, hi)
    while b0 < t1:
        b1 = b0 + step
        i1 = bisect_left(ts, b1, i0, hi)
        if i1 > i0:
            seg = px[i0:i1]
            out.append(Bar(b0, b1, px[i0], max(seg), min(seg), px[i1 - 1], sum(size[i0:i1])))
        b0, i0 = b1, i1
    return out


def exit_lines(ts, px, size, hi: int, d, t0: int, t1: int, kind: str, minutes: int) -> dict:
    """Run controls' exit_line: {bar end ns: (close, line)} for every `minutes` bar ending inside (t0, t1), the line at
    that bar's close -- vwap from the tape's first print (the Globex open), vwap_rth from 09:30, ema20 / ema50 of the bar
    closes from the tape's first print. Bars before a line exists are left out."""
    if hi <= 0:
        return {}
    step = minutes * 60_000_000_000
    start = et_ns(d, "09:30") if kind == "vwap_rth" else int(ts[0])
    bars = build_bars(ts, px, size, 0, hi, start - start % step, t1, minutes)
    n = int(kind[3:]) if kind.startswith("ema") else 0
    a, ema, pv, vol, out = (2.0 / (n + 1)) if n else 0.0, None, 0.0, 0, {}
    i0 = 0
    for b in bars:
        if n:
            ema = b.c if ema is None else ema + a * (b.c - ema)
            line = ema
        else:
            i0 = bisect_left(ts, b.start_ns, i0, hi)
            i1 = bisect_left(ts, b.end_ns, i0, hi)
            pv += sum(p * s for p, s in zip(px[i0:i1], size[i0:i1]))
            vol += sum(size[i0:i1])
            i0 = i1
            line = pv / vol if vol else None
        if line is not None and t0 < b.end_ns < t1:
            out[b.end_ns] = (b.c, line)
    return out


def split_flow(ts, px, size, lo: int, hi: int, bars: list[Bar]) -> None:
    """Give each bar `buy` / `sell` volume by the tick rule (an uptick is a buy, a downtick a sell, an
    unchanged price keeps the last side), carried across bars; the first print of the window has no side
    yet and counts for neither. Opt-in (`needs_flow = True` on the strategy): set as plain attributes, so
    a bar's fields, `asdict` and equality are what they always were. An estimate of the aggressor side,
    not the desk's flow archive: the tester's tape holds price and size only."""
    if not bars:
        return
    k = bisect_left(ts, bars[0].start_ns, lo, hi)
    prev, side = (px[k] if k < hi else 0.0), 0
    for b in bars:
        k0 = bisect_left(ts, b.start_ns, k, hi)
        k1 = bisect_left(ts, b.end_ns, k0, hi)
        buy = sell = 0
        for j in range(k0, k1):
            p = px[j]
            if p > prev:
                side = 1
            elif p < prev:
                side = -1
            prev = p
            if side > 0:
                buy += size[j]
            elif side < 0:
                sell += size[j]
        b.buy, b.sell = buy, sell
        k = k1


def run_session(strategy, tape, costs: Costs, qty: int = 1, daily: list | None = None,
                controls=None) -> SessionResult:
    """Replay one session's tape through one strategy instance."""
    d = tape.date
    w0, w1 = strategy.session_window
    t0, t1 = et_ns(d, w0), et_ns(d, w1)
    ts, px = tape.ts, tape.px
    lo, hi = bisect_left(ts, t0), bisect_left(ts, t1)
    ex = getattr(strategy, "exec_root", "") or ""
    if ex and not exec_ok(tape.root, ex):          # orders to a market's own micro only: never priced on another contract
        raise ValueError(f"exec_root: {tape.root} has no micro named {ex} here")
    sim = _Sim(tape.root, d, ts, px, lo, hi, costs, strategy.placement_ms, ex, controls)
    ctx = sim._ctx = Ctx(sim, qty, daily or [])
    events: list[tuple] = [(t0, 0, 0, "session", None)]
    bm = strategy.bar_minutes
    if bm and controls is not None and controls.bar_minutes:     # run control: the signal bar size
        if controls.bar_minutes in (getattr(strategy, "bar_sizes", ()) or ()):
            bm = controls.bar_minutes
        else:
            sim.refuse("signal bar size not offered by this strategy (its own bars used)")
    strategy.bar_min_eff = bm                       # what scan() / on_bar read when the bar size was swapped
    sim.sig_min = bm or 1                           # run controls: the candle a candle stop reads
    if bm:
        b0, b1 = strategy.bar_window or strategy.session_window
        bars = build_bars(ts, px, tape.size, lo, hi, et_ns(d, b0), et_ns(d, b1), bm)
        if getattr(strategy, "needs_flow", False):
            split_flow(ts, px, tape.size, lo, hi, bars)
        for n, b in enumerate(bars):
            events.append((b.end_ns, 1, n, "bar", b))
    scan = getattr(strategy, "scan", None)          # opt-in: the strategy names the prints it acts on (no candle close)
    if scan is not None:
        strategy.scan_daily = daily or []           # the prior daily bars (what ctx.daily holds), for a scan that needs them
        try:
            for n, (t, sig) in enumerate(scan(tape, lo, hi, t0, t1) or ()):
                events.append((t, 1, 1_000_000 + n, "sig", sig))
        except Exception as e:                      # noqa: BLE001 - one bad session, not a crashed run
            sim.res.skip = f"strategy error: scan: {e}"
            return sim.res
    for n, t in enumerate(strategy.times()):
        events.append((et_ns(d, t), 2, n, "time", t))
    if controls is not None:                        # run controls: the scheduled halves (controls.py)
        if controls.flat_at:
            events.append((et_ns(d, controls.flat_at), 2, 10_000, "ctl", "flat"))
        if controls.entry_to:
            events.append((et_ns(d, controls.entry_to), 2, 10_001, "ctl", "close"))
        if controls.max_hold_min:
            events += [(t, 3, 0, "ctl", "hold") for t in range(t0 + 60_000_000_000, t1, 60_000_000_000)]
        if controls.exit_line:
            sim.lines = exit_lines(ts, px, tape.size, hi, d, t0, t1, controls.exit_line, controls.exit_line_min)
            events += [(t, 3, 1, "ctl", "line") for t in sim.lines]
    events.sort(key=lambda e: e[:3])
    for t, _, _, kind, arg in events:
        if t >= t1:
            break
        sim.advance(bisect_left(ts, t, sim.i, hi))
        sim.now = t
        try:
            if kind == "session":
                strategy.on_session(ctx)
            elif kind == "bar":
                strategy.on_bar(ctx, arg)
            elif kind == "sig":
                strategy.on_signal(ctx, arg)
            elif kind == "ctl":
                sim.control(arg)
            else:
                strategy.on_time(ctx, arg)
        except Exception as e:                      # noqa: BLE001 - one bad session, not a crashed run
            sim.res.skip = f"strategy error: {e}"
            # Cancel every working order and flatten any open position AT THE CURRENT
            # PRINT (sim.i, not end of day) -- the crash must not keep trading. The
            # whole session is skipped, so its trades (including this cleanup close)
            # are dropped from the ledger; the runner counts it under skipped_by_error.
            sim.flatten("strategy error")
            sim.res.trades = []
            return sim.res
    sim.advance(hi)
    sim.i = hi
    sim.flatten("eod")
    for rec in sim.res.hlines:
        rec["end_ms"] = t1 // 1_000_000
    return sim.res
