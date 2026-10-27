"""What every route module of make_router shares (tester_api.make_router builds one per router): the router's own
run, grid and walk-forward managers, the 404 and 415 checks, and the prop-eval re-score with its per-router cache."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, Request

from ... import netguard
from ...backtest import propsim
from ...backtest.grid import GridManager
from ...backtest.runner import RunManager
from ...backtest.walkforward import WalkForwardManager


# prop-eval re-scores kept per service (~2 KB each). Must exceed the Desk warm-up's set (2 per promoted strategy + the
# twins): at 64 with 35 promoted the LRU missed every time, so the 2-minute warm-up re-ran ~74 sims forever and pinned
# a core, starving the loop that carries chart orders and fills (2026-10-22).
PROP_CACHE = 512


@dataclass(frozen=True)
class Ctx:
    api: Any                    # the tester_api module: names the tests patch there are read from it at call time
    write_ok: Callable[[Request], None]
    manager: RunManager
    grids: GridManager
    wfs: WalkForwardManager
    notify: Callable[[dict], int] | None
    live_roots: tuple
    known: Callable[[str], Path]
    known_grid: Callable[[str], Path]
    json_body: Callable[[Request], None]
    rescore: Callable[[tuple, Callable[[], dict], object], dict]


def make_ctx(api, write_ok: Callable[[Request], None], manager: RunManager, grids: GridManager,
             wfs: WalkForwardManager, notify: Callable[[dict], int] | None, live_roots) -> Ctx:
    def known(rid: str):
        try:
            return manager.dir(rid)
        except KeyError:
            raise HTTPException(404, f"no run {rid!r}") from None

    def known_grid(gid: str):
        try:
            return grids.dir(gid)
        except KeyError:
            raise HTTPException(404, f"no grid {gid!r}") from None

    def json_body(request: Request):
        if not netguard.is_json(request.headers.get("content-type")):
            raise HTTPException(415, "send JSON (Content-Type: application/json)")

    prop_cache: OrderedDict = OrderedDict()
    prop_lock = threading.Lock()

    def _rescore(source: tuple, load: Callable[[], dict], rule_id) -> dict:
        """A finished run's (or heat-map cell's) prop eval under `rule_id`, from its stored ledger.
        The run's OWN eval returns its saved propsim.json as is -- unless it was saved before the
        open-loss rule (no `breach`): that one is scored again; any other runs the same
        _run_propsim a fresh run would (same seed, same paths), so the numbers equal a re-run.
        Never writes to the run dir. A plain-`def` caller: FastAPI's threadpool, not the loop."""
        if not isinstance(rule_id, str) or not rule_id:
            raise HTTPException(400, "prop_rules: required")
        try:
            rules = propsim.load_rules(rule_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        key = (source, rule_id, rules.get("version"))
        with prop_lock:
            if key in prop_cache:
                prop_cache.move_to_end(key)
                return prop_cache[key]
        try:
            b = load()
        except KeyError:
            raise HTTPException(404, "no such heat-map cell") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        run_meta = b["run"] or {}
        rng = run_meta.get("range") or {}          # a 3:1 run's own months: its saved eval (before 2026-10-24) padded the rest
        if run_meta.get("prop_rules") == rule_id and (b.get("propsim") or {}).get("breach") and not rng.get("months"):
            out = b["propsim"]
        else:
            out, _ = api._run_propsim(b["trades"] or [], {"prop_rules": rule_id, "prop_rules_data": rules, "range": rng})
        with prop_lock:
            prop_cache[key] = out
            while len(prop_cache) > PROP_CACHE:
                prop_cache.popitem(last=False)
        return out

    return Ctx(api, write_ok, manager, grids, wfs, notify, live_roots, known, known_grid, json_body, _rescore)
