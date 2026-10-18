"""Run controls: the trade rules a person sets on the run, not in the strategy's code (2026-10-12).

Every field is OFF by default and a run with none set is exactly the run it always was. They are enforced by the engine
(engine.py), outside the strategy's code, so they hold for every Lab strategy -- a draft cannot step round them -- and
they are part of the request, so a run's bundle shows what was set.

  entry_from / entry_to   NY "HH:MM": entries only inside [from, to). Orders still waiting at `to` are cancelled; a
                          position already open is NOT touched (that is flat_at).
  flat_at                 NY "HH:MM": cancel everything and close what is open; no entry from then on.
  direction               both | long | short.
  max_trades              entries filled in a day (0 = no cap).
  stop_wins / stop_losses no new entry once the day has this many winning / losing closed trades (net of fees).
  max_consec_losses       no new entry after this many losing trades in a row.
  day_loss / day_profit   no new entry once the day's CLOSED net P&L is at or below -x / at or above +x dollars.
  cooldown_min            minutes with no new entry after a losing trade.
  max_hold_min            a position older than this is closed at the next print (checked each minute).
  stop_mode               own (the strategy's) | fixed (stop_pts) | atr (stop_atr x ATR) | candle | none.
                          candle: just past the last CLOSED signal candle's extreme at the entry (a long's below its low,
                          a short's above its high) by stop_candle_ticks; at least a tick past the fill.
  target_mode             own | fixed (target_pts) | atr (target_atr x ATR) | rr (target_rr x the stop distance) | none.
  be_after_pts / be_offset_ticks   breakeven: once a print reaches the fill + be_after_pts in profit, the stop goes to
                          the fill + be_offset_ticks (default 1 tick into profit); never looser, never at or past the price.
  trail_pts / trail_after_pts       a tick trailing stop: the stop follows the best print since the fill by trail_pts,
                          only tighter; from the fill, or once a print is trail_after_pts in profit.
  exit_line / exit_line_min         close when an exit_line_min bar CLOSES back through the line -- vwap (from the tape's
                          start, the Globex open), vwap_rth (from 09:30), ema20, ema50 (of those bars' closes) -- a long
                          below it, a short above; at the next print.
  (the owner, 2026-10-18: the Lab's Exit lab sweeps these as heat-map axes)
  bar_minutes             signal bar size: 0 = the strategy's own, else 1 | 5 | 15. Only a strategy that lists the size in
                          its `bar_sizes` takes it (a candle-body rule cannot read other candles); for any other the
                          run says so in `blocked` and keeps the strategy's own bars.
  atr_minutes / atr_period  the ATR: mean true range of the last `atr_period` CLOSED `atr_minutes` bars before the
                          entry (overnight included); fewer than that = the entry is refused ("atr warming up").

A fixed or ATR bracket is measured from the FILL, like a broker bracket; it replaces the strategy's own level, for the
stop and the target separately. Every refused entry is counted by reason in the run's `controls.blocked`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DIRECTIONS = ("both", "long", "short")
STOP_MODES = ("own", "fixed", "atr", "candle", "none")
EXIT_LINES = ("", "vwap", "vwap_rth", "ema20", "ema50")
LINE_MINUTES = (1, 5, 15)
TARGET_MODES = ("own", "fixed", "atr", "rr", "none")
ATR_MINUTES = (1, 5, 15)
BAR_MINUTES = (0, 1, 5, 15)

# key -> (kind, default, lo, hi): the one list the request validates against and a page can mirror.
SPEC: dict[str, tuple] = {
    "entry_from": ("time", "", None, None),
    "entry_to": ("time", "", None, None),
    "flat_at": ("time", "", None, None),
    "direction": ("choice", "both", DIRECTIONS, None),
    "max_trades": ("int", 0, 0, 50),
    "stop_wins": ("int", 0, 0, 50),
    "stop_losses": ("int", 0, 0, 50),
    "max_consec_losses": ("int", 0, 0, 50),
    "day_loss": ("float", 0.0, 0.0, 1e6),
    "day_profit": ("float", 0.0, 0.0, 1e6),
    "cooldown_min": ("int", 0, 0, 600),
    "max_hold_min": ("int", 0, 0, 1440),
    "stop_mode": ("choice", "own", STOP_MODES, None),
    "stop_pts": ("float", 0.0, 0.0, 5000.0),
    "stop_atr": ("float", 0.0, 0.0, 50.0),
    "target_mode": ("choice", "own", TARGET_MODES, None),
    "target_pts": ("float", 0.0, 0.0, 5000.0),
    "target_atr": ("float", 0.0, 0.0, 50.0),
    "target_rr": ("float", 0.0, 0.0, 50.0),
    "stop_candle_ticks": ("int", 0, 0, 200),
    "be_after_pts": ("float", 0.0, 0.0, 5000.0),
    "be_offset_ticks": ("int", 1, 0, 100),
    "trail_pts": ("float", 0.0, 0.0, 5000.0),
    "trail_after_pts": ("float", 0.0, 0.0, 5000.0),
    "exit_line": ("choice", "", EXIT_LINES, None),
    "exit_line_min": ("choice", 5, LINE_MINUTES, None),
    "bar_minutes": ("choice", 0, BAR_MINUTES, None),
    "atr_minutes": ("choice", 5, ATR_MINUTES, None),
    "atr_period": ("int", 14, 2, 200),
}
# which number each mode reads; a number a mode does not read is dropped from the request, so the same rules
# always make the same request (and the same cache key)
NEEDS = {("stop_mode", "fixed"): "stop_pts", ("stop_mode", "atr"): "stop_atr",
         ("target_mode", "fixed"): "target_pts", ("target_mode", "atr"): "target_atr",
         ("target_mode", "rr"): "target_rr"}
ATR_USERS = (("stop_mode", "atr"), ("target_mode", "atr"))


def coerce(k: str, v):
    """One field's value as the engine reads it (ValueError with a message for the page). A time may be "" (off)."""
    kind, default, lo, hi = SPEC[k]
    if kind == "time":
        if v in (None, ""):
            return ""
        if not isinstance(v, str) or not TIME.match(v):
            raise ValueError(f"controls.{k}: a New York time as HH:MM")
        return v
    if kind == "choice":
        val = v
        if isinstance(val, str) and k in ("atr_minutes", "bar_minutes", "exit_line_min") and val.isdigit():
            val = int(val)
        if isinstance(val, bool) or val not in lo:
            raise ValueError(f"controls.{k}: one of {', '.join(str(c) for c in lo)}")
        return val
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"controls.{k}: a number")
    if kind == "int" and float(v) != int(v):
        raise ValueError(f"controls.{k}: a whole number")
    if not lo <= v <= hi:
        raise ValueError(f"controls.{k}: must be within [{lo:g}, {hi:g}]")
    return int(v) if kind == "int" else float(v)


# what a heat-map axis (or a page) calls each field
LABELS = {
    "entry_from": "Trade from (NY)", "entry_to": "Trade until (NY)", "flat_at": "Flat at (NY)", "direction": "Direction",
    "max_trades": "Trades a day", "stop_wins": "Stop after wins", "stop_losses": "Stop after losses",
    "max_consec_losses": "Losses in a row", "day_loss": "Daily loss ($)", "day_profit": "Daily profit ($)",
    "cooldown_min": "Cool off after a loss (min)", "max_hold_min": "Close after (min held)",
    "stop_mode": "Stop type", "stop_pts": "Stop (points)", "stop_atr": "Stop (x ATR)",
    "target_mode": "Target type", "target_pts": "Target (points)", "target_atr": "Target (x ATR)",
    "target_rr": "Target (x stop)", "stop_candle_ticks": "Candle stop buffer (ticks)", "be_after_pts": "Breakeven after (points)",
    "be_offset_ticks": "Breakeven + (ticks)", "trail_pts": "Trailing stop (points)", "trail_after_pts": "Trail after (points)",
    "exit_line": "Exit on close through", "exit_line_min": "Exit line bars (min)", "bar_minutes": "Signal bar (min)", "atr_minutes": "ATR bars (min)",
    "atr_period": "ATR length",
}
# a number that only means something under one mode: a heat-map axis on it switches that mode on (0 = leave it)
IMPLIES = {"stop_pts": ("stop_mode", "fixed"), "stop_atr": ("stop_mode", "atr"),
           "target_pts": ("target_mode", "fixed"), "target_atr": ("target_mode", "atr"), "target_rr": ("target_mode", "rr"),
           "stop_candle_ticks": ("stop_mode", "candle")}


def value_label(k: str, v) -> str:
    """A value the way a heat-map header reads it."""
    if v in ("", 0, 0.0):
        return "own" if k == "bar_minutes" else "off"
    return f"{v:g}" if isinstance(v, float) else str(v)


def parse(raw) -> dict:
    """The rules as the engine will run them: only what differs from OFF, or {} when nothing is set. ValueError (a
    message for the page) on an unknown key, a wrong type, a value out of range, or a mode without its number."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("controls: a JSON object")
    extra = sorted(set(raw) - set(SPEC))
    if extra:
        raise ValueError(f"controls: unknown field(s): {', '.join(extra)}")
    out: dict = {}
    for k, v in raw.items():
        val = coerce(k, v)
        if SPEC[k][0] == "time" and val == "":
            continue
        if val != SPEC[k][1]:
            out[k] = val
    for (mode, name), num in NEEDS.items():
        if out.get(mode) == name:
            if not out.get(num):
                raise ValueError(f"controls.{num}: needed when {mode} is {name}")
        else:
            out.pop(num, None)
    # a number another field switches on means nothing without it (the same rules always make the same request)
    for num, on in (("stop_candle_ticks", out.get("stop_mode") == "candle"), ("be_offset_ticks", bool(out.get("be_after_pts"))),
                    ("trail_after_pts", bool(out.get("trail_pts"))), ("exit_line_min", bool(out.get("exit_line")))):
        if not on:
            out.pop(num, None)
    if not any(out.get(m) == n for m, n in ATR_USERS):
        out.pop("atr_minutes", None)
        out.pop("atr_period", None)
    if out.get("entry_from") and out.get("entry_to") and out["entry_from"] >= out["entry_to"]:
        raise ValueError("controls: the entry window ends before it starts")
    if out.get("flat_at") and out.get("entry_from") and out["flat_at"] <= out["entry_from"]:
        raise ValueError("controls: flat time is before the entry window opens")
    return out


@dataclass(frozen=True)
class Controls:
    entry_from: str = ""
    entry_to: str = ""
    flat_at: str = ""
    direction: str = "both"
    max_trades: int = 0
    stop_wins: int = 0
    stop_losses: int = 0
    max_consec_losses: int = 0
    day_loss: float = 0.0
    day_profit: float = 0.0
    cooldown_min: int = 0
    max_hold_min: int = 0
    stop_mode: str = "own"
    stop_pts: float = 0.0
    stop_atr: float = 0.0
    target_mode: str = "own"
    target_pts: float = 0.0
    target_atr: float = 0.0
    target_rr: float = 0.0
    stop_candle_ticks: int = 0
    be_after_pts: float = 0.0
    be_offset_ticks: int = 1
    trail_pts: float = 0.0
    trail_after_pts: float = 0.0
    exit_line: str = ""
    exit_line_min: int = 5
    bar_minutes: int = 0
    atr_minutes: int = 5
    atr_period: int = 14

    @staticmethod
    def from_dict(d) -> "Controls | None":
        """None when nothing is set: the engine then takes the path it always took."""
        d = parse(d)
        return Controls(**d) if d else None
