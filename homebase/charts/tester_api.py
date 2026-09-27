"""The Strategy Tester's HTTP API on the chart service (:8852).

    GET  /api/tester/strategies          strategies with input schemas + defaults
    GET  /api/tester/prop-rules          prop-eval rule sets [{id, name, version, confirmed}]
    POST /api/tester/run                 {strategy, inputs, range, qty, commission,
                                          slippage_ticks, capital?, prop_rules?,
                                          holdout?: {reason}} -> {id}
    GET  /api/tester/run/{id}            status + progress
    POST /api/tester/run/{id}/cancel
    GET  /api/tester/run/{id}/bundle     run (meta + report + coverage), trades, equity, plots, propsim
    GET  /api/tester/runs                recent runs, newest first
    POST /api/tester/grid                {strategy, inputs, axes: [{key, values}] x2-3, qty, commission,
                                          slippage_ticks, capital?, prop_rules?} -> {id}
                                          (<= 60 cells, research window 2021-2024 ONLY: a range or
                                          holdout other than research is refused)
    GET  /api/tester/grid/{id}           the grid, per-cell status + summary, and its strategy's looks
    POST /api/tester/grid/{id}/cancel
    GET  /api/tester/grid/{id}/cell/{i}/bundle   a cell's full run bundle (the same shape as a run's)
    GET  /api/tester/grids               recent grids, newest first
    GET  /api/tester/looks               {strategy: heat-map cells ever run}

Grid cells run as the same `runner exec` child a single run uses, 2 at a time, from the
GridManager's worker threads (homebase.backtest.grid) -- never in this process's event loop.

Runs execute in a child process (homebase.backtest.runner), never in this process; and
every route is a plain `def`, so FastAPI runs it in its threadpool and
the chart pump's event loop never waits on disk. Every route here — GET and POST
alike — first passes a Host allowlist (below): a DNS-rebinding attacker keeps
Origin and Host in lockstep, so the Origin check alone (browser_write_ok, passed in
by create_app) would agree with a rebound Host; the Host header itself must still
name this loopback service. None of these GETs is secret, but the check is applied
uniformly rather than routed around it. POSTs additionally pass browser_write_ok.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import strategies
from ..backtest import propsim
from ..backtest.grid import GridManager
from ..backtest.runner import RunManager, default_base
from ..backtest.tape import CACHE

_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)


def host_ok(request: Request) -> None:
    """DNS-rebinding defence: refuse any request whose Host header does not
    literally name this loopback service (127.0.0.1 or localhost, optional
    port) — regardless of Origin, which a rebinding attacker can keep
    agreeing with Host throughout the attack. Applied to every route on this
    router (see make_router), GET and POST alike."""
    if not _HOST_RE.match((request.headers.get("host") or "").strip()):
        raise HTTPException(403, "unexpected Host header")


def make_router(write_ok: Callable[[Request], None], manager: RunManager,
                grids: GridManager) -> APIRouter:
    r = APIRouter(prefix="/api/tester", dependencies=[Depends(host_ok)])

    def known(rid: str):
        try:
            return manager.dir(rid)
        except KeyError:
            raise HTTPException(404, f"no run {rid!r}") from None

    @r.get("/strategies")
    def list_strategies():
        return strategies.catalog()

    @r.get("/prop-rules")
    def prop_rules():
        return propsim.list_rules()

    @r.post("/run")
    def start_run(request: Request, body: dict):
        write_ok(request)
        try:
            return {"id": manager.submit(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.get("/run/{rid}")
    def run_status(rid: str):
        known(rid)
        return manager.status(rid)

    @r.post("/run/{rid}/cancel")
    def cancel_run(rid: str, request: Request):
        write_ok(request)
        known(rid)
        try:
            return manager.cancel(rid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/run/{rid}/bundle")
    def run_bundle(rid: str):
        known(rid)
        try:
            return manager.bundle(rid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/runs")
    def recent_runs():
        return manager.runs_list()

    def known_grid(gid: str):
        try:
            return grids.dir(gid)
        except KeyError:
            raise HTTPException(404, f"no grid {gid!r}") from None

    @r.post("/grid")
    def start_grid(request: Request, body: dict):
        write_ok(request)
        try:
            return {"id": grids.submit(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.get("/grid/{gid}")
    def grid_status(gid: str):
        known_grid(gid)
        return grids.status(gid)

    @r.post("/grid/{gid}/cancel")
    def cancel_grid(gid: str, request: Request):
        write_ok(request)
        known_grid(gid)
        return grids.cancel(gid)

    @r.get("/grid/{gid}/cell/{i}/bundle")
    def grid_cell_bundle(gid: str, i: int):
        known_grid(gid)
        try:
            return grids.cell_bundle(gid, i)
        except KeyError:
            raise HTTPException(404, f"no cell {i} in grid {gid!r}") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/grids")
    def recent_grids():
        return grids.list()

    @r.get("/looks")
    def looks():
        return grids.all_looks()

    r.manager = manager   # so the chart service can stop an in-flight child on shutdown
    r.grids = grids       # likewise every grid cell's child
    return r


def tester_router(write_ok: Callable[[Request], None], archive: Path,
                  state: Path | None = None) -> APIRouter:
    """Production (state None): homebase/.state/tester + the ~/futures_derived tape
    cache. A test passes its tmp dir and gets the runs AND the cache under it."""
    base = Path(state) if state else default_base()
    cache = base / "tape" if state else CACHE
    return make_router(write_ok, RunManager(base, archive=archive, cache=cache),
                       GridManager(base, archive=archive, cache=cache))
