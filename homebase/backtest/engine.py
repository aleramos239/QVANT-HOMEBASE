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

Stdlib only (array + bisect): the desk's venv carries no numpy.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass, field

from ..contracts import point_value, tick_size
from .tape import et_ns

ENGINE_VERSION = "tick-1"
SIDE = {"long": 1, "short": -1}
NAME = {1: "long", -1: "short"}
CHUNK = 4096                    # prefilter block for the trigger scan


def to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


def first_at_or_above(px, level: float, a: int, b: int) -> int:
    """First index k in [a, b) with px[k] >= level, else b."""
    k = a
    while k < b:
        e = min(k + CHUNK, b)
        if max(px[k:e]) >= level:
            for i in range(k, e):
                if px[i] >= level:
                    return i
        k = e
    return b


def first_at_or_below(px, level: float, a: int, b: int) -> int:
    """First index k in [a, b) with px[k] <= level, else b."""
    k = a
    while k < b:
        e = min(k + CHUNK, b)
        if min(px[k:e]) <= level:
            for i in range(k, e):
                if px[i] <= level:
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


@dataclass(eq=False)
class Position:
    side: int
    qty: int
    entry_px: float
    entry_i: int
    order_price: float | None
    sl: Order | None = None
    tp: Order | None = None


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
    hlines: list = field(default_factory=list)    # [{name, price, date}]
    skip: str | None = None                       # the strategy's reason for no trade


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
        return self._s.new_order(SIDE[side], kind, price, int(qty or self.qty),
                                 sl=sl, tp=tp, tp_rr=tp_rr, ref=ref)

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

    def hline(self, name: str, price: float) -> None:
        self._s.res.hlines.append({"name": name, "price": price, "date": self.date.isoformat()})

    def skip(self, reason: str) -> None:
        self._s.res.skip = reason


class _Sim:
    def __init__(self, root, d, ts, px, lo, hi, costs: Costs, placement_ms: int):
        self.root, self.date = root, d
        self.ts, self.px, self.lo, self.hi = ts, px, lo, hi
        self.tick = tick_size(root)
        self.pv = point_value(root) or 0.0
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

    def _trigger(self, o: Order, a: int, b: int) -> int:
        if o.kind == "market":
            return a
        if o.kind == "stop":
            return (first_at_or_above(self.px, o.price, a, b) if o.side > 0
                    else first_at_or_below(self.px, o.price, a, b))
        return (first_at_or_below(self.px, o.price - self.tick, a, b) if o.side > 0
                else first_at_or_above(self.px, o.price + self.tick, a, b))

    def _fill_price(self, o: Order, p: float) -> float:
        if o.kind == "limit":
            return o.price
        if o.kind == "stop":
            return max(o.price, p) + self.slip if o.side > 0 else min(o.price, p) - self.slip
        return p + o.side * self.slip

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
        if o.tp_rr is not None and sl is not None:
            tp = to_tick(fill + o.side * o.tp_rr * abs(fill - sl), self.tick)
        elif self._ctx.move_brackets_to_fill and o.ref is not None:
            d = fill - o.ref
            sl = None if sl is None else to_tick(sl + d, self.tick)
            tp = None if tp is None else to_tick(tp + d, self.tick)
        self._ids += 1
        if sl is not None:
            pos.sl = Order(self._ids, -o.side, "stop", sl, o.qty, k + 1, role="sl", pos=pos)
            self.orders.append(pos.sl)
        self._ids += 1
        if tp is not None:
            pos.tp = Order(self._ids, -o.side, "limit", tp, o.qty, k + 1, role="tp", pos=pos)
            self.orders.append(pos.tp)
        self.positions.append(pos)

    def _close(self, pos: Position, fill: float, k: int, reason: str) -> None:
        for x in (pos.sl, pos.tp):
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
            self._close(pos, self.px[k] - pos.side * self.slip, k, reason)


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


def run_session(strategy, tape, costs: Costs, qty: int = 1, daily: list | None = None) -> SessionResult:
    """Replay one session's tape through one strategy instance."""
    d = tape.date
    w0, w1 = strategy.session_window
    t0, t1 = et_ns(d, w0), et_ns(d, w1)
    ts, px = tape.ts, tape.px
    lo, hi = bisect_left(ts, t0), bisect_left(ts, t1)
    sim = _Sim(tape.root, d, ts, px, lo, hi, costs, strategy.placement_ms)
    ctx = sim._ctx = Ctx(sim, qty, daily or [])
    events: list[tuple] = [(t0, 0, 0, "session", None)]
    if strategy.bar_minutes:
        b0, b1 = strategy.bar_window or strategy.session_window
        for n, b in enumerate(build_bars(ts, px, tape.size, lo, hi, et_ns(d, b0), et_ns(d, b1),
                                         strategy.bar_minutes)):
            events.append((b.end_ns, 1, n, "bar", b))
    for n, t in enumerate(strategy.times()):
        events.append((et_ns(d, t), 2, n, "time", t))
    events.sort(key=lambda e: e[:3])
    for t, _, _, kind, arg in events:
        if t >= t1:
            break
        sim.advance(bisect_left(ts, t, sim.i, hi))
        sim.now = t
        if kind == "session":
            strategy.on_session(ctx)
        elif kind == "bar":
            strategy.on_bar(ctx, arg)
        else:
            strategy.on_time(ctx, arg)
    sim.advance(hi)
    sim.i = hi
    sim.flatten("eod")
    return sim.res
