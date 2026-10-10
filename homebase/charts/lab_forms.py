"""The Lab's fill-in form: a small dictionary of answers (market, entry rule, stop, target, times) in, the text of a
normal draft strategy file out. Pure text and stdlib only: the same answers always give the same file, nothing here
runs a draft, places an order or talks to a service. The file is an ordinary draft (one Strategy class, contract
homebase/strategies/base.py) with a header that lets the form read its answers back:

    \"\"\"<sentence(answers)>\"\"\"
    # Made with the Lab's form. ...
    # form: <the answers as one line of JSON, keys sorted>
    # code: <sha256 hex of every line after this one>

build() validates and writes the file (FormError names the field and says why, in one sentence), read() finds the
answers again and says whether the code under the header has been left as it was written (its hash still fits), sentence() describes the
strategy in plain words, schema() gives the page everything it needs to draw the form.
"""
from __future__ import annotations

import builtins
import hashlib
import json
import keyword
import math
import re

from .. import draftstore
from ..contracts import tick_size

MARKETS = ("NQ", "ES", "YM", "RTY", "GC", "SI")
SIDES = (("both", "Both"), ("long", "Long only"), ("short", "Short only"))
RANGE_MINS = (5, 15, 30)
BAR_MINS = (1, 5, 15)
EARLIEST, LATEST = "00:05", "15:55"        # a time the form accepts; a session opens 5 minutes before its first time
MAX_TICKS, MAX_TARGET_TICKS = 2000, 6000   # a distance or points stop / a points target may not be further than this many ticks
PAD = 5                                    # minutes the session window reaches before the first time and past out_by

PICK = "Pick one from the list."
PICK_SIDE = "Pick long or short for this rule."
NEED_STOP = "Every entry needs a stop."
RANGE_STOP = "That stop only works with the opening range."
NEED_TARGET = "Give a target, or pick None."
NEED_DISTANCE = "The distance must be at least one tick."
LOOKBACK = "Between 2 and 40 bars."
TRADES = "Between 1 and 5."
BAD_TIME = "A New York time from 00:05 to 15:55, like 09:30."
AFTER_START = "It must be after the start."
AFTER_RANGE = "It must be after the range ends ({end})."
AFTER_LAST = "It must be after the last entry, and 15:55 at the latest."
TOO_FAR = "Too many bars back for that start time."
TOO_FAR_POINTS = "Too far for this market: at most {n} points."
INCOMPLETE = "The form is incomplete."
TICK_MULTIPLE = "Use a multiple of the tick ({tick})."

HEADER_NOTE = ('# Made with the Lab\'s form. "Edit in the form" opens it again; a change made by hand here is kept '
               'until then.')

LAST_CANCEL = "No new entry after this time. An entry order not filled by then is cancelled."

# the fields each rule draws, in the order the page shows them (name and rule are not fields)
RULE_FIELDS = {
    "open_straddle": ("market", "side", "time", "distance", "stop", "target", "last_entry", "out_by"),
    "opening_range": ("market", "side", "range_from", "range_min", "stop", "target", "last_entry", "out_by"),
    "bar_breakout": ("market", "side", "bar_min", "lookback", "from", "last_entry", "trades", "stop", "target",
                     "out_by"),
    "at_time": ("market", "side", "time", "stop", "target", "out_by"),
}
RULE_TEXT = {
    "open_straddle": ("Stop straddle", "At a time of day, a buy stop above the price and a sell stop below it. "
                                       "The first one to fill cancels the other."),
    "opening_range": ("Opening range", "Measure the high and low of the first minutes, then a buy stop above the "
                                       "range and a sell stop below it."),
    "bar_breakout": ("Bar breakout", "Buy when a bar closes above the highs of the last few bars, sell when it "
                                     "closes below their lows."),
    "at_time": ("At a time", "Buy or sell at the market at a time of day."),
}


class FormError(ValueError):
    """One answer the form cannot use: `.field` is the key, `.sentence` says why in plain words."""

    def __init__(self, field: str, sentence: str):
        super().__init__(sentence)
        self.field, self.sentence = field, sentence


# ---------------------------------------------------------------- small helpers

def _num(v) -> bool:
    """A finite number a float can hold (a bool, a string or None is not one; neither is an int past float range)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(float(v))
    except OverflowError:
        return False


def _whole(v):
    """v as an int when it is a whole number (6 or 6.0), else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, int):
        return v
    return int(v) if math.isfinite(v) and v == int(v) else None


def _on_tick(v, tick: float) -> bool:
    """v is a whole number of ticks (within 1e-9 of a price)."""
    q = v / tick
    return math.isfinite(q) and abs(q - round(q)) * tick <= 1e-9


def _n(x) -> str:
    """15.0 -> "15", 0.25 -> "0.25" (for the sentence and the comments)."""
    return f"{float(x):.6f}".rstrip("0").rstrip(".")


def _pts(x) -> str:
    return "1 point" if float(x) == 1 else f"{_n(x)} points"


def _mins(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _is_time(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", v, re.ASCII) is not None \
        and EARLIEST <= v <= LATEST


def _too_far(ticks: int, tick: float) -> str:
    """The sentence for a number past the bound: the bound in points, written like the tick sentence writes numbers."""
    return TOO_FAR_POINTS.format(n=_n(round(ticks * tick, 6)))


def _hi(v: float) -> float:
    """The top of a points Input: room to tune, and never below the answer."""
    top = float(v) * 10
    return max(1000.0, top if math.isfinite(top) else float(v))


def _rule_start(a: dict) -> str | None:
    """The time the rule first acts (opening range: the moment its range is done). None while it is unreadable."""
    rule = a["rule"]
    if rule == "opening_range":
        if a.get("range_from") and a.get("range_min"):
            return _hhmm(_mins(a["range_from"]) + a["range_min"])
        return None
    return a.get("from") if rule == "bar_breakout" else a.get("time")


def _first_time(a: dict) -> str:
    """The first time the rule needs data for: the session window opens 5 minutes before it. The bar breakout reads
    the bars before its start time too: `lookback` of them for the bar that closes at the start, plus that bar."""
    if a["rule"] == "bar_breakout":
        return _hhmm(_mins(a["from"]) - (a["lookback"] + 1) * a["bar_min"])
    return {"open_straddle": a.get("time"), "at_time": a.get("time"), "opening_range": a.get("range_from")}[a["rule"]]


def _window(a: dict) -> tuple[str, str]:
    return _hhmm(_mins(_first_time(a)) - PAD), _hhmm(_mins(a["out_by"]) + PAD)


# ---------------------------------------------------------------- the answers, checked

def _check(answers) -> dict:
    """The answers as the form will keep them, or FormError for the first field (in the contracts' order) that
    cannot be used. Whole numbers come back as ints; nothing else is changed."""
    if not isinstance(answers, dict):
        raise FormError("form", INCOMPLETE)
    a = dict(answers)
    if isinstance(a.get("rule"), str) and a["rule"] in RULE_FIELDS:       # the keys come before any value
        keys = ["name", "rule", *RULE_FIELDS[a["rule"]]]
        for key in keys:
            if key not in a:
                raise FormError(key, INCOMPLETE)
        for key in sorted((k for k in a if k not in keys), key=str):
            raise FormError(str(key), INCOMPLETE)
    try:
        draftstore.validate_name(a.get("name"))
    except ValueError as e:
        raise FormError("name", str(e)) from None
    if a.get("market") not in MARKETS:
        raise FormError("market", PICK)
    if a.get("rule") not in tuple(RULE_FIELDS):
        raise FormError("rule", PICK)
    if a.get("side") not in tuple(s for s, _ in SIDES):
        raise FormError("side", PICK)
    rule, tick = a["rule"], tick_size(a["market"])
    if rule == "at_time" and a["side"] == "both":
        raise FormError("side", PICK_SIDE)
    _check_stop(a.get("stop"), rule, tick)
    _check_target(a.get("target"), tick)
    if "distance" in a:
        if not (_num(a["distance"]) and a["distance"] >= tick):
            raise FormError("distance", NEED_DISTANCE)
        if not _on_tick(a["distance"], tick):
            raise FormError("distance", TICK_MULTIPLE.format(tick=_n(tick)))
        if a["distance"] > MAX_TICKS * tick + 1e-9:
            raise FormError("distance", _too_far(MAX_TICKS, tick))
    for key, low, high, sentence in (("lookback", 2, 40, LOOKBACK), ("trades", 1, 5, TRADES)):
        if key in a:
            n = _whole(a[key])
            if n is None or not low <= n <= high:
                raise FormError(key, sentence)
            a[key] = n
    for key, allowed in (("range_min", RANGE_MINS), ("bar_min", BAR_MINS)):
        if key in a:
            n = _whole(a[key])
            if n not in allowed:
                raise FormError(key, PICK)
            a[key] = n
    start_key = {"opening_range": "range_from", "bar_breakout": "from"}.get(rule, "time")
    for key in (start_key, "last_entry", "out_by"):
        if key in a and not _is_time(a[key]):
            raise FormError(key, BAD_TIME)
    if rule == "bar_breakout" and _mins(a["from"]) - (a["lookback"] + 1) * a["bar_min"] < _mins(EARLIEST):
        raise FormError("lookback", TOO_FAR)
    start = _rule_start(a)
    if "last_entry" in a and start is not None and a["last_entry"] <= start:
        raise FormError("last_entry", AFTER_RANGE.format(end=start) if rule == "opening_range" else AFTER_START)
    if "out_by" in a:
        end = a.get("last_entry") if rule != "at_time" else a.get("time")
        if end is not None and a["out_by"] <= end:
            raise FormError("out_by", AFTER_LAST)
    return a


def _check_stop(stop, rule: str, tick: float) -> None:
    kind = stop.get("kind") if isinstance(stop, dict) else None
    if kind == "range":
        if rule != "opening_range":
            raise FormError("stop", RANGE_STOP)
        if set(stop) != {"kind"}:
            raise FormError("stop", NEED_STOP)
    elif kind == "points":
        if set(stop) != {"kind", "value"} or not _num(stop["value"]) or stop["value"] < round(2 * tick, 6):
            raise FormError("stop", NEED_STOP)
        if not _on_tick(stop["value"], tick):
            raise FormError("stop", TICK_MULTIPLE.format(tick=_n(tick)))
        if stop["value"] > MAX_TICKS * tick + 1e-9:
            raise FormError("stop", _too_far(MAX_TICKS, tick))
    else:
        raise FormError("stop", NEED_STOP)


def _check_target(target, tick: float) -> None:
    kind = target.get("kind") if isinstance(target, dict) else None
    if kind == "none":
        ok = set(target) == {"kind"}
    elif kind == "points":
        ok = set(target) == {"kind", "value"} and _num(target["value"]) and target["value"] >= tick
    elif kind == "rr":
        ok = set(target) == {"kind", "value"} and _num(target["value"]) and 0.25 <= target["value"] <= 20
    else:
        ok = False
    if not ok:
        raise FormError("target", NEED_TARGET)
    if kind == "points" and not _on_tick(target["value"], tick):
        raise FormError("target", TICK_MULTIPLE.format(tick=_n(tick)))
    if kind == "points" and target["value"] > MAX_TARGET_TICKS * tick + 1e-9:
        raise FormError("target", _too_far(MAX_TARGET_TICKS, tick))


# ---------------------------------------------------------------- plain words

def sentence(answers: dict) -> str:
    """One plain sentence for the strategy; it is also the file's docstring."""
    return _sentence(_check(answers))


def _sentence(a: dict) -> str:
    rule, side = a["rule"], a["side"]
    only = f", {side} only" if side != "both" and rule != "at_time" else ""
    head = f"{a['market']}{only}: "
    if rule == "open_straddle":
        legs = {"both": f"a buy stop {_pts(a['distance'])} above and a sell stop {_pts(a['distance'])} below",
                "long": f"a buy stop {_pts(a['distance'])} above", "short": f"a sell stop {_pts(a['distance'])} below"}
        what = f"at {a['time']} {legs[side]}."
    elif rule == "opening_range":
        legs = {"both": "a buy stop above the range and a sell stop below it", "long": "a buy stop above the range",
                "short": "a sell stop below the range"}
        what = f"after the first {a['range_min']} minutes from {a['range_from']}, {legs[side]}."
    elif rule == "bar_breakout":
        bar = f"a {a['bar_min']}-minute bar closes"
        legs = {"both": f"buys when {bar} above the last {a['lookback']} bars' high and sells when it closes "
                        f"below their low",
                "long": f"buys when {bar} above the last {a['lookback']} bars' high",
                "short": f"sells when {bar} below the last {a['lookback']} bars' low"}
        what = f"{legs[side]}, from {a['from']} to {a['last_entry']}."
    else:
        what = f"{'buys' if side == 'long' else 'sells'} at the market at {a['time']}."
    stop = a["stop"]
    stop_words = "Stop at the other side of the range" if stop["kind"] == "range" else f"Stop {_pts(stop['value'])}"
    t = a["target"]
    target_words = {"none": "no target", "points": f"target {_pts(t.get('value', 0))}",
                    "rr": f"target {_n(t.get('value', 0))} x the stop"}[t["kind"]]
    trades = a.get("trades", 1)
    count = "One trade a day." if trades == 1 else f"Up to {trades} trades a day."
    cancel = f" Unfilled orders are cancelled at {a['last_entry']}." if rule in ("open_straddle", "opening_range") else ""
    return f"{head}{what} {stop_words}, {target_words}. {count}{cancel} Out by {a['out_by']}."


def _label(a: dict) -> str:
    """The strategy's readable title, e.g. "NQ open straddle 09:30"."""
    rule = a["rule"]
    if rule == "open_straddle":
        title = f"open straddle {a['time']}"
    elif rule == "opening_range":
        title = f"opening range {a['range_from']} {a['range_min']} min"
    elif rule == "bar_breakout":
        title = f"{a['bar_min']}-min breakout {a['from']}"
    else:
        title = f"{a['side']} at {a['time']}"
    side = f" {a['side']} only" if a["side"] != "both" and rule != "at_time" else ""
    return f"{a['market']} {title}{side}"


# ---------------------------------------------------------------- the code

def _class_name(name: str) -> str:
    cls = "".join(p.capitalize() for p in name.split("_") if p)
    taken = keyword.iskeyword(cls) or hasattr(builtins, cls) or cls in ("Input", "Strategy")
    return cls + "Draft" if taken else cls


def _inputs(a: dict, tick: float) -> list[tuple]:
    """(key, label, type, default, min, max, step) for each number the owner may tune."""
    out = []
    if "distance" in a:
        out.append(("distance", "Distance (pts)", "float", float(a["distance"]), tick, _hi(a["distance"]), tick))
    if "lookback" in a:
        out.append(("lookback", "Lookback (bars)", "int", a["lookback"], 2, a["lookback"], 1))      # the bars before the start are built for this many
    if "trades" in a:
        out.append(("trades", "Trades a day", "int", a["trades"], 1, 5, 1))
    stop, target = a["stop"], a["target"]
    if stop["kind"] == "points":
        v = float(stop["value"])
        out.append(("sl_pts", "Stop (pts)", "float", v, round(2 * tick, 6), _hi(v), tick))
    if target["kind"] == "points":
        v = float(target["value"])
        out.append(("tp_pts", "Target (pts)", "float", v, tick, _hi(v), tick))
    elif target["kind"] == "rr":
        out.append(("rr", "Target (x the stop)", "float", float(target["value"]), 0.25, 20.0, 0.25))
    return out


def _reads(a: dict) -> list[str]:
    """The `self.p[...]` reads a rule's entry code needs, as "name = self.p[key]" pieces."""
    pairs = [("dist", "distance")] if "distance" in a else []
    if a["stop"]["kind"] == "points":
        pairs.append(("sl", "sl_pts"))
    pairs += {"points": [("tp", "tp_pts")], "rr": [("rr", "rr")], "none": []}[a["target"]["kind"]]
    return pairs


def _read_line(pairs: list[tuple]) -> list[str]:
    if not pairs:
        return []
    names = ", ".join(v for v, _ in pairs)
    keys = ", ".join(f'self.p["{k}"]' for _, k in pairs)
    return [f"{names} = {keys}"]


def _stop_expr(a: dict, side: str, entry: str, far: str) -> str:
    """The stop's price: points behind the entry, or (opening range) the other side of the range."""
    if a["stop"]["kind"] == "range":
        return far
    return f"{entry} - sl" if side == "long" else f"{entry} + sl"


def _target_arg(a: dict, side: str, entry: str, stop_entry: bool) -> str | None:
    """The target as an argument of the order call, or None for no target. A stop entry's rr target is taken from
    the fill (tp_rr); a market entry's is worked out from its reference price."""
    t = a["target"]["kind"]
    sign = "+" if side == "long" else "-"
    if t == "none":
        return None
    if t == "points":
        return f"tp={entry} {sign} tp"
    return "tp_rr=rr" if stop_entry else f"tp={entry} {sign} rr * sl"


def _order(a: dict, call: str, side: str, entry: str, far: str, stop_entry: bool, extra: str = "") -> str:
    args = [f'"{side}"'] + ([entry] if stop_entry else [])
    args.append(f"sl={_stop_expr(a, side, entry, far)}")
    tp = _target_arg(a, side, entry, stop_entry)
    if tp:
        args.append(tp)
    if extra:
        args.append(extra)
    return f"ctx.{call}({', '.join(args)})"


def _sides(a: dict) -> list[str]:
    return ["long", "short"] if a["side"] == "both" else [a["side"]]


MOVE = "ctx.move_brackets_to_fill = True  # the stop and target follow the fill"
STAY = "ctx.move_brackets_to_fill = False  # the stop stays at the other side of the range"


def _stops_block(a: dict, prices: str, guard: list[str] = ()) -> list[str]:
    """Stop entries for each wanted side (an OCO pair when both), remembered in self.entries. `prices` is the line
    that sets up (buy stop) and dn (sell stop); the far side of the range is lo for a buy and hi for a sell. A stop
    at the other side of the range is an absolute price: it is not moved to the fill like a stop of N points."""
    names = {"long": "buy", "short": "sell"}
    entry = {"long": "up", "short": "dn"}
    far = {"long": "lo", "short": "hi"}
    lines = [prices, *guard, STAY if a["stop"]["kind"] == "range" else MOVE]
    for s in _sides(a):
        lines.append(f"{names[s]} = " + _order(a, "stop_entry", s, entry[s], far[s], True))
    if a["side"] == "both":
        lines.append("ctx.oco(buy, sell)")
    lines.append("self.entries = [" + ", ".join(names[s] for s in _sides(a)) + "]")
    return lines


def _straddle(a: dict) -> dict:
    t = a["time"]
    comment = {"both": "stop entries either side of the last price; the first to fill cancels the other",
               "long": "a buy stop above the last price", "short": "a sell stop below the last price"}[a["side"]]
    up_dn = {"both": "up, dn = px + dist, px - dist", "long": "up = px + dist", "short": "dn = px - dist"}[a["side"]]
    lines = [f"# {comment}", "px = ctx.last_price", "if px is None:", f'    ctx.skip("no print before {t}")',
             "    return", *_read_line(_reads(a))]
    lines += _stops_block(a, up_dn)
    return {"first": t, "start": [(t, lines)], "session": ["self.entries = []"], "bar": None, "attrs": []}


def _opening_range(a: dict) -> dict:
    end = _rule_start(a)
    long_, short = "long" in _sides(a), "short" in _sides(a)
    by_range = a["stop"]["kind"] == "range"
    need_hi, need_lo = long_ or (by_range and short), short or (by_range and long_)
    levels = {(True, True): "hi, lo = max(self.highs), min(self.lows)", (True, False): "hi = max(self.highs)",
              (False, True): "lo = min(self.lows)"}[(need_hi, need_lo)]
    where = {"both": "each end of it", "long": "the high", "short": "the low"}[a["side"]]
    ups = {"both": "up, dn = hi + ctx.tick, lo - ctx.tick", "long": "up = hi + ctx.tick",
           "short": "dn = lo - ctx.tick"}[a["side"]]
    lines = [f"# the range is done: a stop entry one tick beyond {where}",
             "if not self.highs:", '    ctx.skip("no prices in the opening range")', "    return",
             levels, *_read_line(_reads(a))]
    guard = []
    if by_range:                          # a stop less than 2 ticks from the entry is no stop: no trade today
        gap = "up - lo" if long_ else "hi - dn"
        guard = [f"if round(({gap}) / ctx.tick) < 2:", '    ctx.skip("the opening range is too small")', "    return"]
    lines += _stops_block(a, ups, guard)
    return {"first": a["range_from"], "start": [(end, lines)],
            "session": ["self.highs, self.lows, self.entries = [], [], []"],
            "bar": ["self.highs.append(bar.h)", "self.lows.append(bar.l)"],
            "attrs": ["bar_minutes = 1", f'bar_window = ("{a["range_from"]}", "{end}")  # only the range becomes bars']}


def _breakout(a: dict) -> dict:
    first, (w0, w1) = _first_time(a), _window(a)
    gap = lambda t: _mins(t) - _mins(w0)                    # noqa: E731 -- minutes from the session start to a time
    levels = {"both": "hi, lo = max(self.highs[-n:]), min(self.lows[-n:])", "long": "hi = max(self.highs[-n:])",
              "short": "lo = min(self.lows[-n:])"}[a["side"]]
    inner = [levels, *_read_line(_reads(a)), MOVE]
    branches = [("bar.c > hi", "long"), ("bar.c < lo", "short")]
    for i, (cond, s) in enumerate(b for b in branches if b[1] in _sides(a)):
        inner += [("if " if i == 0 else "elif ") + cond + ":",
                  "    " + _order(a, "market", s, "bar.c", "", False, "ref=bar.c"), "    self.taken += 1"]
    lines = ['n = self.p["lookback"]',
             'if self.t_from <= bar.end_ns <= self.t_last and ctx.flat and self.taken < self.p["trades"] and len(self.highs) >= n:',
             *["    " + x for x in inner],
             "self.highs.append(bar.h)", "self.lows.append(bar.l)"]
    consts = [f'FROM_MIN = {gap(a["from"])}  # a bar that closes at {a["from"]} or later may enter: minutes from the session start ({w0})',
              f'LAST_MIN = {gap(a["last_entry"])}  # ... up to and including the bar that closes at {a["last_entry"]}']
    return {"first": first, "start": [], "consts": consts,
            "session": ["self.highs, self.lows, self.taken = [], [], 0",
                        "self.t_from = ctx.now_ns + FROM_MIN * 60_000_000_000",
                        "self.t_last = ctx.now_ns + LAST_MIN * 60_000_000_000"],
            "bar": lines,
            "attrs": [f"bar_minutes = {a['bar_min']}", f'bar_window = ("{first}", "{w1}")']}


def _at_time(a: dict) -> dict:
    t, side = a["time"], a["side"]
    lines = [f"# {'buy' if side == 'long' else 'sell'} at the market; the stop and target are measured from the price",
             "px = ctx.last_price", "if px is None:", f'    ctx.skip("no print before {t}")', "    return",
             *_read_line(_reads(a)),
             MOVE, _order(a, "market", side, "px", "", False, "ref=px")]
    return {"first": t, "start": [(t, lines)], "session": [], "bar": None, "attrs": []}


_RULES = {"open_straddle": _straddle, "opening_range": _opening_range, "bar_breakout": _breakout,
          "at_time": _at_time}


def _on_time(blocks: list[tuple]) -> list[str]:
    out = []
    for i, (t, lines) in enumerate(blocks):
        out.append(f'{"if" if i == 0 else "elif"} et_time == "{t}":')
        out += ["    " + x if x else x for x in lines]
    return out


def _body(a: dict) -> str:
    rule = a["rule"]
    tick = tick_size(a["market"])
    parts = _RULES[rule](a)
    w0, w1 = _window(a)
    blocks = list(parts["start"])
    if rule in ("open_straddle", "opening_range"):
        blocks.append((a["last_entry"], ["# no new entry after this: a stop that has not filled is cancelled",
                                         "for order in self.entries:", "    ctx.cancel(order)"]))
    blocks.append((a["out_by"], ['ctx.flatten("time")  # flat for the day']))
    times = ", ".join(f'"{t}"' for t, _ in blocks)
    ins = _inputs(a, tick)
    items = [f'Input("{k}", "{lab}", "{typ}", {d!r}, {lo!r}, {hi!r}, {step!r})' for k, lab, typ, d, lo, hi, step in ins]
    out = ["", "",
           f"class {_class_name(a['name'])}(Strategy):",
           f'    name = "{_label(a)}"',
           f'    root = "{a["market"]}"',
           f'    session_window = ("{w0}", "{w1}")  # ET [start, end) the tape must cover',
           *["    " + x for x in parts["attrs"]],
           "    session_independent = True",
           "",
           "    @classmethod",
           "    def inputs(cls):"]
    if items:
        out.append("        return [" + (",\n                ").join(items) + "]")
    else:
        out.append("        return []")
    out += ["", "    def times(self):", f"        return [{times}]"]
    if parts["session"]:
        out += ["", "    def on_session(self, ctx):"] + ["        " + x for x in parts["session"]]
    if parts["bar"]:
        out += ["", "    def on_bar(self, ctx, bar):"] + ["        " + x for x in parts["bar"]]
    out += ["", "    def on_time(self, ctx, et_time):"] + ["        " + x for x in _on_time(blocks)]
    consts = ["", *parts.get("consts", [])] if parts.get("consts") else []
    return "from __future__ import annotations\n\nfrom homebase.strategies.base import Input, Strategy\n" \
        + "\n".join(consts + out) + "\n"


def build(answers: dict) -> str:
    """The draft file's text for these answers; FormError when an answer cannot be used. The file is checked
    with the draft store's own checks before it is returned: a failure there is this generator's bug (RuntimeError)."""
    a = _check(answers)
    body = _body(a)
    code = (f'"""{_sentence(a)}"""\n{HEADER_NOTE}\n# form: {json.dumps(a, sort_keys=True)}\n'
            f'# code: {hashlib.sha256(body.encode("utf-8")).hexdigest()}\n{body}')
    try:
        draftstore.check_source(code)
        draftstore.static_meta(code)
    except ValueError as e:
        raise RuntimeError(f"the form wrote a draft the draft store refuses (a bug in the form): {e}") from None
    return code


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")            # NaN / Infinity / -Infinity: Python reads them, JSON has none


def _clean_json(value) -> bool:
    """Only what a response can carry: finite numbers, strings that encode as UTF-8 (keys and values), at most
    20 levels deep and 1,000 values. Walked with a stack: a hostile header cannot recurse."""
    stack, seen = [(value, 0)], 0
    while stack:
        v, depth = stack.pop()
        seen += 1
        if seen > 1000 or depth > 20:
            return False
        if isinstance(v, float):
            if not math.isfinite(v):
                return False
        elif isinstance(v, str):
            try:
                v.encode("utf-8")
            except UnicodeEncodeError:
                return False
        elif isinstance(v, dict):
            for k, x in v.items():
                stack.append((k, depth + 1))
                stack.append((x, depth + 1))
        elif isinstance(v, list):
            stack.extend((x, depth + 1) for x in v)
    return True


def read(code: str) -> dict | None:
    """{"answers", "intact"} from a file the form made, else None. intact: the sha256 on the `# code:` line is the
    sha256 of every line after it, so nobody has edited the code by hand (whatever today's template would write: a
    file an older form made is intact too, and Update rewrites it). An edit of the docstring, the note or the
    `# form:` line does not change it. Reads text only: nothing in `code` is run or imported; it never raises."""
    if not isinstance(code, str):
        return None
    try:
        lines = code.split("\n")
        for i in range(len(lines) - 1):
            if lines[i].startswith("# form: ") and re.fullmatch(r"# code: [0-9a-f]{64}\r?", lines[i + 1]):
                break
        else:
            return None
        answers = json.loads(lines[i][len("# form: "):], parse_constant=_no_constant)
        if not isinstance(answers, dict) or not _clean_json(answers):
            return None
    except (ValueError, RecursionError, MemoryError):
        return None
    try:
        body = "\n".join(lines[i + 2:])
        intact = hashlib.sha256(body.encode("utf-8")).hexdigest() == lines[i + 1][len("# code: "):len("# code: ") + 64]
    except (UnicodeEncodeError, MemoryError):          # a lone surrogate in the code: not a file the form wrote
        intact = False
    return {"answers": answers, "intact": intact}


# ---------------------------------------------------------------- the page's schema

def _field_defs() -> dict:
    return {
        "market": {"label": "Market", "words": "The futures market to trade.", "type": "choice",
                   "choices": list(MARKETS), "default": "NQ"},
        "side": {"label": "Trade", "words": "Buy, sell, or both.",
                 "words_by_rule": {r: "Buy or sell." if r == "at_time" else "Buy, sell, or both." for r in RULE_FIELDS},
                 "type": "choice", "choices": [s for s, _ in SIDES], "default": "both"},
        "time": {"label": "Time", "words": "The New York time it acts, like 09:30.", "type": "time",
                 "default": "09:30"},
        "distance": {"label": "Distance (points)", "words": "How far from the price each stop entry sits.",
                     "type": "number", "min_ticks": 1, "max_ticks": MAX_TICKS, "tick_multiple": True, "default": 15.0},
        "range_from": {"label": "Range starts", "words": "Where the range starts, a New York time like 09:30.",
                       "type": "time", "default": "09:30"},
        "range_min": {"label": "Range length (minutes)", "words": "How many minutes the range is measured over.",
                      "type": "choice", "choices": list(RANGE_MINS), "default": 15},
        "bar_min": {"label": "Bar size (minutes)", "words": "How long each bar is.", "type": "choice",
                    "choices": list(BAR_MINS), "default": 5},
        "lookback": {"label": "Look back (bars)", "words": "How many bars back it looks. To look further back, change it here in the form.",
                     "type": "int", "min": 2, "max": 40, "step": 1, "default": 6},
        "from": {"label": "Start at", "words": "The first time it may enter. The bars before it set the high and low.",
                 "type": "time", "default": "09:30"},
        "trades": {"label": "Trades a day", "words": "Most entries it takes in one day.", "type": "int",
                   "min": 1, "max": 5, "step": 1, "default": 1},
        "last_entry": {"label": "Last entry", "words": "No new entry after this time.",
                       "words_by_rule": {"open_straddle": LAST_CANCEL, "opening_range": LAST_CANCEL,
                                         "bar_breakout": "No new entry after this time."},
                       "type": "time", "default": "11:00"},
        "stop": {"label": "Stop", "words": "Every entry carries a stop.", "type": "stop",
                 "kinds": [{"id": "points", "label": "Points", "min_ticks": 2, "max_ticks": MAX_TICKS, "tick_multiple": True},
                           {"id": "range", "label": "Other side of the range", "rules": ["opening_range"]}],
                 "default": {"kind": "points", "value": 50.0}},
        "target": {"label": "Target", "words": "Where to take profit, or none.", "type": "target",
                   "kinds": [{"id": "points", "label": "Points", "min_ticks": 1, "max_ticks": MAX_TARGET_TICKS, "tick_multiple": True},
                             {"id": "rr", "label": "x the stop", "min": 0.25, "max": 20, "step": 0.25},
                             {"id": "none", "label": "None"}],
                 "default": {"kind": "rr", "value": 3.0}},
        "out_by": {"label": "Out by", "words": "Anything still open is closed at this time. 15:55 at the latest.",
                   "type": "time", "default": "15:55"},
    }


def _defaults() -> dict:
    common = {"market": "NQ", "side": "both", "out_by": "15:55"}
    mid = {"last_entry": "11:00"}
    pts = lambda v: {"kind": "points", "value": v}          # noqa: E731
    return {
        "open_straddle": {**common, **mid, "rule": "open_straddle", "time": "09:30", "distance": 15.0,
                          "stop": pts(50.0), "target": {"kind": "rr", "value": 3.0}},
        "opening_range": {**common, **mid, "rule": "opening_range", "range_from": "09:30", "range_min": 15,
                          "stop": {"kind": "range"}, "target": {"kind": "rr", "value": 2.0}},
        "bar_breakout": {**common, **mid, "rule": "bar_breakout", "bar_min": 5, "lookback": 6, "from": "09:30",
                         "trades": 1, "stop": pts(20.0), "target": pts(40.0)},
        "at_time": {**common, "rule": "at_time", "side": "long", "time": "09:30", "stop": pts(20.0),
                    "target": pts(40.0)},
    }


# a market's size against NQ's: the starting distance, points stop and points target of every rule are its NQ default times this
SIZE_FACTOR = {"NQ": 1, "ES": 0.25, "YM": 2, "RTY": 0.2, "GC": 0.125, "SI": 0.003}


def _sizes() -> dict:
    """{market: {rule: {"distance"?, "stop"?, "target_points"?}}}: each rule's NQ default times the market's factor,
    in whole ticks and never below the field's least (a distance and a target: 1 tick, a stop: 2 ticks). A rule has a
    number only where its NQ default has one (a range stop or a ratio target has none)."""
    out = {}
    for m in MARKETS:
        tick, factor = tick_size(m), SIZE_FACTOR[m]
        fit = lambda v, least: round(max(least, math.floor(v * factor / tick + 0.5)) * tick, 6)       # noqa: E731
        out[m] = {}
        for rule, d in _defaults().items():
            one = {}
            if "distance" in d:
                one["distance"] = fit(d["distance"], 1)
            if d["stop"]["kind"] == "points":
                one["stop"] = fit(d["stop"]["value"], 2)
            if d["target"]["kind"] == "points":
                one["target_points"] = fit(d["target"]["value"], 1)
            out[m][rule] = one
    return out


def schema() -> dict:
    """Everything the page needs to draw the form with no knowledge of the rules."""
    return {
        "markets": list(MARKETS),
        "ticks": {m: tick_size(m) for m in MARKETS},
        "sizes": _sizes(),
        "sides": [list(s) for s in SIDES],
        "rules": [{"id": r, "label": RULE_TEXT[r][0], "words": RULE_TEXT[r][1], "fields": list(RULE_FIELDS[r]),
                   "sides": ["long", "short"] if r == "at_time" else [s for s, _ in SIDES]} for r in RULE_FIELDS],
        "fields": _field_defs(),
        "defaults": _defaults(),
    }
