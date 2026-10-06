"""Build the 2021-2024 parity bundle: one 2021-01-01 -> 2024-12-31 run over the synthetic
multi-year archive, with everything that changes between two identical runs stripped out.
(The window is named by its dates: it was the default {kind: research} until the default
became the build days, 2026-10-06.)"""
from __future__ import annotations

import tempfile
from pathlib import Path

from homebase import config
from homebase.backtest.runner import execute, prepare, read_json
from homebase.backtest.tape import TapeStore
from tests.backtest_util import multiyear_archive

VOLATILE = ("id", "created", "finished")          # a run id and its two clocks: never part of the numbers


def parity_bundle() -> dict:
    """{run, trades, equity, plots} of a 2021-2024 nq930 run, run-id/clock free."""
    real = config.config_path
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        config.config_path = lambda: t / "absent.json"     # the frozen desk defaults, not this machine's
        try:
            store = TapeStore(multiyear_archive(t / "ticks"), t / "cache")
            rid = prepare({"strategy": "nq930", "inputs": {"adx_gate": False},
                           "range": {"kind": "custom", "start": "2021-01-01", "end": "2024-12-31"}}, t / "state")
            d = t / "state" / "runs" / rid
            req = read_json(d / "request.json")
            req["propsim"] = False                          # a Monte Carlo is not part of the report
            (d / "request.json").write_text(__import__("json").dumps(req, separators=(",", ":"), default=str))
            execute(d, store)
            run = read_json(d / "run.json")
            for k in VOLATILE:
                run.pop(k, None)
            return {"run": run, "trades": read_json(d / "trades.json"),
                    "equity": read_json(d / "equity.json"), "plots": read_json(d / "plots.json")}
        finally:
            config.config_path = real
