"""The strategy contract shared by the Strategy Tester (now) and the desk (later).

A strategy is one class: metadata, an input schema, and event handlers that
act through a context (`ctx`) the tick engine provides. Stdlib only — the
chart service lists strategies in-process, so nothing here may import numpy
or the engine.

    class MyStraddle(Strategy):
        id, name, root = "x", "X straddle", "NQ"
        session_window = ("09:25", "16:00")        # ET [start, end) the tape must cover
        @classmethod
        def inputs(cls): return [Input("offset_pts", "Offset (pts)", "float", 10.0, 0.25, 100, 0.25)]
        def times(self): return ["09:30:00", "15:55"]
        def on_time(self, ctx, et_time): ...

Events (all times ET, all run BEFORE the first print at or after their time):
  on_session(ctx)            at session_window[0]
  on_bar(ctx, bar)           at each bar's close, when bar_minutes > 0
  on_time(ctx, et_time)      at each time in times(), et_time exactly as listed
Orders (see homebase/backtest/engine.py for the fill law):
  ctx.stop_entry / ctx.limit_entry / ctx.market -> Order;  ctx.oco(a, b);
  ctx.cancel(order);  ctx.flatten();  ctx.move_brackets_to_fill = True;
  ctx.plot(name, t_ns, value);  ctx.hline(name, price);  ctx.skip(reason)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

TYPES = ("int", "float", "bool", "choice")


@dataclass(frozen=True)
class Input:
    key: str
    label: str
    type: str                       # int | float | bool | choice
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["choices"] = list(self.choices)
        return d


def resolve_inputs(schema: list[Input], values: dict | None) -> dict:
    """Defaults overlaid with `values`, each checked against its Input.
    ValueError (naming the key) on an unknown key, a wrong type or a value
    outside [min, max] — never clamped: a tester that silently moves a
    parameter reports a run nobody asked for."""
    values = dict(values or {})
    by_key = {i.key: i for i in schema}
    unknown = sorted(set(values) - set(by_key))
    if unknown:
        raise ValueError(f"unknown input(s): {', '.join(unknown)}")
    out: dict = {}
    for i in schema:
        v = values.get(i.key, i.default)
        if i.type == "bool":
            if not isinstance(v, bool):
                raise ValueError(f"{i.key}: expected true/false")
        elif i.type == "choice":
            if v not in i.choices:
                raise ValueError(f"{i.key}: one of {', '.join(map(str, i.choices))}")
        elif i.type in ("int", "float"):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{i.key}: expected a number")
            if i.type == "int":
                if float(v) != int(v):
                    raise ValueError(f"{i.key}: expected a whole number")
                v = int(v)
            else:
                v = float(v)
            if v != v or (i.min is not None and v < i.min) or (i.max is not None and v > i.max):
                raise ValueError(f"{i.key}: must be within [{i.min}, {i.max}]")
        else:
            raise ValueError(f"{i.key}: unknown input type {i.type!r}")
        out[i.key] = v
    return out


class Strategy:
    id: str = ""
    name: str = ""
    root: str = ""
    session_window: tuple[str, str] = ("09:25", "16:00")   # ET [start, end)
    bar_minutes: int = 0                  # > 0: on_bar gets bars of this size
    bar_window: tuple[str, str] | None = None   # ET span bars are built over (default: session_window)
    placement_ms: int = 85                # measured order-placement latency (research)
    # True = every session is independent: day state resets in on_session and anything older comes from
    # ctx.daily (the store), never from an earlier session of the SAME run. The walk-forward relies on it
    # (a month sliced out of a full-window run == a run over that month) and refuses a strategy without it.
    session_independent: bool = True

    def __init__(self, params: dict | None = None):
        self.p = resolve_inputs(self.inputs(), params)

    @classmethod
    def inputs(cls) -> list[Input]:
        return []

    @classmethod
    def describe(cls) -> dict:
        return {"id": cls.id, "name": cls.name, "root": cls.root,
                "session_window": list(cls.session_window),
                "bar_minutes": cls.bar_minutes,
                "inputs": [i.to_dict() for i in cls.inputs()]}

    def times(self) -> list[str]:
        return []

    def trades_on(self, d: dt.date) -> bool:
        """False = the session is not even loaded (e.g. not an event day)."""
        return True

    def needs_daily(self) -> bool:
        """True = ctx.daily must carry the completed daily bars before today."""
        return False

    def provenance(self) -> dict:
        """The resolved runtime configuration a run actually used -- cancel/flat
        times, any config.json-derived geometry, a bars strategy's rule config --
        so a bundle stays reproducible even after config.json (or the frozen
        defaults) later change. Base default: nothing beyond the run's own
        `inputs`, which the bundle already stores separately."""
        return {}

    def on_session(self, ctx) -> None:
        pass

    def on_time(self, ctx, et_time: str) -> None:
        pass

    def on_bar(self, ctx, bar) -> None:
        pass
