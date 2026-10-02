"""Starter scripts for the Lab's "New strategy" menu. Pure text (stdlib only): nothing here runs a draft --
a template is read, shown in the editor and, when the person saves it, written by homebase.draftstore like
any other draft. Every template must pass draftstore.check_source (tests/test_lab_api.py pins it, and runs
the bar template end to end in the sandbox)."""
from __future__ import annotations

import ast

from .. import draftstore

BLANK = '''"""<One line: what this strategy does.>"""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy


class MyStrategy(Strategy):
    name = "My strategy"
    root = "NQ"
    session_window = ("09:25", "16:00")   # ET [start, end) the tape must cover
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("sl_pts", "Stop (pts)", "float", 5.0, 0.25, 100, 0.25),
                Input("tp_pts", "Target (pts)", "float", 15.0, 0.25, 400, 0.25)]

    def times(self):
        return ["09:30:00", "15:55"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            px = ctx.last_price
            if px is None:
                ctx.skip("no print before 09:30")
                return
            # ctx.market("long", sl=px - self.p["sl_pts"], tp=px + self.p["tp_pts"])
        elif et_time == "15:55":
            ctx.flatten("time")
'''

BAR_BREAKOUT = '''"""Buy a close above the last N bars' high, sell a close below their low: one trade a session."""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy


class BarBreakout(Strategy):
    name = "Bar breakout"
    root = "NQ"
    session_window = ("09:30", "11:30")
    bar_minutes = 5
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("lookback", "Lookback (bars)", "int", 6, 2, 40, 1),
                Input("sl_pts", "Stop (pts)", "float", 20.0, 1, 200, 0.25),
                Input("tp_pts", "Target (pts)", "float", 40.0, 1, 400, 0.25)]

    def times(self):
        return ["11:25"]

    def on_session(self, ctx):
        self.highs, self.lows, self.traded = [], [], False

    def on_bar(self, ctx, bar):
        n = self.p["lookback"]
        if not self.traded and ctx.flat and len(self.highs) >= n:
            hi, lo = max(self.highs[-n:]), min(self.lows[-n:])
            sl, tp = self.p["sl_pts"], self.p["tp_pts"]
            if bar.c > hi:
                ctx.market("long", sl=bar.c - sl, tp=bar.c + tp)
                self.traded = True
            elif bar.c < lo:
                ctx.market("short", sl=bar.c + sl, tp=bar.c - tp)
                self.traded = True
        self.highs.append(bar.h)
        self.lows.append(bar.l)

    def on_time(self, ctx, et_time):
        ctx.flatten("time")
'''


def _split_template() -> tuple[str, str]:
    """(the rules a draft follows, the template's code without them): DRAFT_TEMPLATE opens with one long docstring
    that documents the whole contract -- right for a file Claude writes, too much to open an editor on."""
    doc = ast.get_docstring(ast.parse(draftstore.DRAFT_TEMPLATE)) or ""
    body = draftstore.DRAFT_TEMPLATE.split('"""', 2)[2].lstrip("\n")
    return doc, body


def reference() -> str:
    """The scripting reference the Lab shows on request: the contract, as DRAFT_TEMPLATE documents it."""
    doc = _split_template()[0]
    return doc.split("\n", 2)[2].strip() if doc.count("\n") >= 2 else doc


STRADDLE = '"""Stop entries either side of the 9:30 open, one cancels the other; flat at 15:55."""\n' + _split_template()[1]


def templates() -> list[dict]:
    """[{id, title, blurb, code}] -- the first is the one a new strategy opens with."""
    return [
        {"id": "straddle", "title": "Stop straddle", "blurb": "Stop entries either side of the open, OCO",
         "code": STRADDLE},
        {"id": "bar_breakout", "title": "Bar breakout", "blurb": "Price action on 5-minute bar closes",
         "code": BAR_BREAKOUT},
        {"id": "blank", "title": "Blank", "blurb": "The contract, nothing else", "code": BLANK},
    ]
