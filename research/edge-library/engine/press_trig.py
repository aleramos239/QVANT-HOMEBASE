"""press_trig -- ENTER WITH THE CHART'S BUY / SELL PRESSURE WHEN IT IS "PUSHING" (owner, 2026-10-27: "longs on buyers solid +25 or more,
vice versa sells at -25 or less ... 1, 3, 5, 15 minute timeframes ... candle extreme as the stop and 1:0.5 RR").

THE NUMBER. tapeflow.pressure(): the chart's own Buy / sell pressure (studies_flow.Pressure, 5 tf bars, -100 .. +100: volume, big prints,
sweeps and orders blended), read from the desk's per-trade tape. One tf bar's value is known when that bar has closed.
THE RULE. At a tf close, flat, inside the entry window: pressure >= lvl -> market long; <= -lvl -> market short (lvl 25 = the chart's
"Buyers pushing" / "Sellers pushing"). No signal (no tape for the date) = no trade. Every qualifying close enters while flat (max_tr a session).
THE STOP. The signal candle's other extreme (the low for a long, the high for a short): stop_mode "own", stop_val 1.0; the Template floors it
at 0.25 x ATR and 2 ticks. Target = tgt_r x the stop distance. Entries stop at t_end (default 15:00 ET); the Template flattens each session at
its end (the last one 15:58 ET).
Lives in engine/, not families/: the registry would list it as a module with no FAMILIES, and it has no 3-minute bar. Run it with
research/edge-library/press_trig_run.py. Tests: engine/tests/test_press_trig.py."""
from __future__ import annotations

import l2sim as S
import tapeflow as TF
from l2sim import NS, Template


class PressTrig(Template):
    DEFAULTS = {"lvl": 25.0, "t_end": "15:00", "max_tr": 20}
    SCHEMA = {"tf": ("choice", ("1", "3", "5", "15", "30")), "lvl": ("float", 1.0, 100.0), "t_end": ("str",), "max_tr": ("int", 1, 50)}
    SCREEN_TFS = ("1", "5", "15")
    FEATURES = ()

    def fam_signal(self, ctx):
        now = (ctx.now_ns - self.t0) // NS                        # seconds after 00:00 ET of the trade date
        if now >= S.clock_sec(self.p["t_end"]):
            return
        p = TF.pressure(ctx.root, self.day, now // 60 * 60, self.tf)
        if p is None:
            return
        lvl = float(self.p["lvl"])
        if p >= lvl:
            self._mkt(ctx, "long", struct=self.L[-1])
        elif p <= -lvl:
            self._mkt(ctx, "short", struct=self.H[-1])
