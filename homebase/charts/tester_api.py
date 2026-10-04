"""The Strategy Tester's HTTP API on the chart service (:8852).

    GET  /api/tester/strategies          strategies with input schemas + defaults; DRAFT strategies
                                          (~/.homebase/strategies, homebase.draftstore) follow the built-ins
                                          with `draft: true` (and `error` when its metadata cannot be read) --
                                          read from the file's TEXT (backtest.drafthost, ast): no draft runs
    GET  /api/tester/strategies/{id}/source   the strategy's source text: a built-in's module (+ the
                                          homebase/strategies modules its classes inherit from), or a draft's file
    GET  /api/tester/drafts              the Lab's library: every draft on disk {name, id, bytes, modified, ok,
                                          error?, meta?} -- read from the TEXT only
    GET  /api/tester/drafts/templates    the "New strategy" starters [{id, title, blurb, code}]
    GET  /api/tester/drafts/reference    {text}: the scripting contract (events, orders, reads), for the Lab's reference sheet
    POST /api/tester/drafts/validate     {code} -> {ok, meta} | {ok: false, error, line?} (parse + catalog read)
    PUT  /api/tester/drafts/{name}       {code} -> save <name>.py (draftstore.write: name, size and syntax checked)
    DELETE /api/tester/drafts/{name}     remove it
    POST /api/tester/drafts/{name}/review-request   {run_id?, note?} -> writes a review package (text only) under
                                          ~/.homebase/review-requests; never runs, imports or promotes anything
    POST /api/tester/show                {run_id | grid_id + cell, focus?: {trade_index | date | time_ms}}
                                          -> tells every open chart page (/ws `tester_show`) to load that run or
                                          heat-map cell into the Strategy Tester and show it on a chart
                                          (JSON only; refused 09:20-09:35 ET on weekdays; the page picks the
                                          chart -- testerlayer.showPlan)
    GET  /api/tester/prop-rules          prop-eval rule sets [{id, name, version, confirmed}]
    POST /api/tester/run                 {strategy, inputs, range, qty, commission,
                                          slippage_ticks, capital?, prop_rules?} -> {id}
                                          (any window: nothing is refused for the dates it reads;
                                          a range reaching 2025+ is recorded in spends.jsonl)
    GET  /api/tester/run/{id}            status + progress
    POST /api/tester/run/{id}/cancel
    GET  /api/tester/run/{id}/bundle     run (meta + report + coverage), trades, equity, plots, propsim
    POST /api/tester/runs/{id}/propsim   {prop_rules} -> the run's prop-eval block re-scored under another
                                          eval (same shape as the bundle's propsim). The eval reads only
                                          the finished ledger, so a re-score IS a re-run; it is a VIEW --
                                          the run's saved propsim.json is never overwritten. Cached per
                                          (source, rules id, rules version).
    POST /api/tester/propsim             the same, {run_id | grid_id + cell, prop_rules}
    GET  /api/tester/runs                recent runs, newest first
    POST /api/tester/grid                {strategy, inputs, axes: [{key, values}] x2-3, qty, commission,
                                          slippage_ticks, capital?, prop_rules?} -> {id}
                                          (<= 60 cells, over the body's own range -- 2021-2024
                                          when it names none)
    GET  /api/tester/grid/{id}           the grid, per-cell status + summary, and its strategy's looks
    POST /api/tester/grid/{id}/cancel
    GET  /api/tester/grid/{id}/cell/{i}/bundle   a cell's full run bundle (the same shape as a run's)
    GET  /api/tester/grids               recent grids, newest first
    GET  /api/tester/looks               {strategy: heat-map cells ever run}
    POST /api/tester/walkforward         the grid body + {metric?, min_trades?, test_months? | compare?} -> {id}:
                                          1 month to select, the next N to test, stepping monthly, over the
                                          body's own range; `compare: true` = ONE job (one grid run) selected
                                          and stitched at 1:1, 1:2 and 1:3 (homebase.backtest.walkforward)
    GET  /api/tester/walkforward/{id}    status, per-cell status (never full-window P&L), progress, eta_s
    GET  /api/tester/walkforward/{id}/result   the steps, the stitched OOS equity + stats (409 until done);
                                          ?test_months=N picks a compare job's 1:N scheme (a compare job
                                          without it is a 409)
    GET  /api/tester/walkforward/{id}/compare  a compare job's three stitched OOS results side by side
    POST /api/tester/walkforward/{id}/cancel
    GET  /api/tester/walkforwards        recent walk-forwards, newest first
    GET  /api/tester/walkforward-scheme  ?test_months=1|2|3|compare&start=&end= — the step count for that
                                          ratio and window (compare: the three summed, and each), plus the
                                          metrics and defaults (no job needed)
    POST /api/tester/montecarlo          {run_id | grid_id + cell, paths?, mode?, seed?, floor?} ->
                                          homebase.backtest.stats.montecarlo.run() over a DONE run's trades,
                                          resampled by day (<= 10,000 paths, <= 2,000,000 day-steps; seed
                                          derived from the run id; cached; a plain `def` route, so it runs in
                                          FastAPI's threadpool, off the event loop)

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

import asyncio
import datetime as dt
import inspect
import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import draftstore, netguard, strategies
from ..backtest import drafthost
from ..backtest import propsim
from ..backtest.grid import GridManager, LooksCorrupt
from ..backtest.runner import RunManager, _run_propsim, default_base, read_json
from ..backtest.stats import montecarlo
from ..backtest import walkforward
from ..backtest.walkforward import WalkForwardManager
from ..backtest.slots import Slots
from ..backtest.tape import CACHE
from . import lab_templates, reviewpack

MC_CACHE = 64            # Monte Carlo results kept per service (review I3)
PROP_CACHE = 64          # prop-eval re-scores kept per service
_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)


def host_ok(request: Request) -> None:
    """DNS-rebinding defence: refuse any request whose Host header does not
    literally name this loopback service (127.0.0.1 or localhost, optional
    port) — regardless of Origin, which a rebinding attacker can keep
    agreeing with Host throughout the attack. Applied to every route on this
    router (see make_router), GET and POST alike."""
    if not _HOST_RE.match((request.headers.get("host") or "").strip()):
        raise HTTPException(403, "unexpected Host header")


_STRATEGIES_DIR = Path(strategies.__file__).resolve().parent
FOCUS_KEYS = ("trade_index", "date", "time_ms")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def builtin_source(sid: str) -> list[dict]:
    """A built-in strategy's source: its own module, then every homebase/strategies module one of its
    classes inherits from (the straddles live in straddle.py, the contract in base.py)."""
    cls = strategies.get(sid)
    files: list[Path] = []
    for k in cls.__mro__:
        try:
            f = Path(inspect.getsourcefile(k) or "").resolve()
        except TypeError:
            continue
        if f.parent == _STRATEGIES_DIR and f.suffix == ".py" and f not in files:
            files.append(f)
    return [{"path": f"homebase/strategies/{f.name}", "text": f.read_text(encoding="utf-8")} for f in files]


def check_focus(focus) -> dict | None:
    """None, or exactly one of {trade_index: int >= 0, date: 'YYYY-MM-DD', time_ms: int epoch ms}."""
    if focus is None:
        return None
    if not isinstance(focus, dict) or len(focus) != 1 or next(iter(focus)) not in FOCUS_KEYS:
        raise HTTPException(400, "focus: one of {trade_index}, {date}, {time_ms}")
    k, v = next(iter(focus.items()))
    if k == "date":
        # strictly YYYY-MM-DD, returned in its canonical form: the page compares it to trade dates as a string
        # (3.11+'s fromisoformat alone would also take "20240304" or "2024-W10-1")
        if not isinstance(v, str) or not _DATE_RE.fullmatch(v):
            raise HTTPException(400, "focus.date: YYYY-MM-DD")
        try:
            return {"date": dt.date.fromisoformat(v).isoformat()}
        except ValueError:
            raise HTTPException(400, "focus.date: YYYY-MM-DD") from None
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise HTTPException(400, f"focus.{k}: a whole number >= 0")
    return {k: v}


def make_router(write_ok: Callable[[Request], None], manager: RunManager,
                grids: GridManager, wfs: WalkForwardManager,
                notify: Callable[[dict], int] | None = None) -> APIRouter:
    r = APIRouter(prefix="/api/tester", dependencies=[Depends(host_ok)])

    def known(rid: str):
        try:
            return manager.dir(rid)
        except KeyError:
            raise HTTPException(404, f"no run {rid!r}") from None

    @r.get("/strategies")
    def list_strategies():
        built = strategies.catalog()
        return built + drafthost.catalog(builtin_ids={s["id"] for s in built})

    @r.get("/strategies/{sid}/source")
    def strategy_source(sid: str):
        if draftstore.is_draft_id(sid):
            try:
                name = draftstore.name_of(sid)
                text = draftstore.read(name)
            except (ValueError, FileNotFoundError):
                raise HTTPException(404, f"no draft {sid!r}") from None
            return {"id": sid, "draft": True,
                    "files": [{"path": str(draftstore.path_for(name)), "text": text}]}
        try:
            return {"id": sid, "draft": False, "files": builtin_source(sid)}
        except ValueError:
            raise HTTPException(404, f"no strategy {sid!r}") from None

    # ---- the Lab: a library of drafts, kept as text ---------------------------------------------------------
    def builtin_ids() -> set:
        return {x["id"] for x in strategies.catalog()}

    def json_body(request: Request):
        if not netguard.is_json(request.headers.get("content-type")):
            raise HTTPException(415, "send JSON (Content-Type: application/json)")

    def code_of(body) -> str:
        if not isinstance(body, dict) or not isinstance(body.get("code"), str):
            raise HTTPException(400, "{code: the draft's Python source}")
        return body["code"]

    def meta_or_error(code: str) -> tuple[dict | None, str | None, int | None]:
        try:
            draftstore.check_source(code)
            return draftstore.static_meta(code), None, None
        except ValueError as e:
            m = re.search(r"\(line (\d+)\)", str(e))
            return None, str(e), int(m.group(1)) if m else None

    def brief(meta: dict | None) -> dict | None:
        if meta is None:
            return None
        keep = ("class", "name", "root", "session_window", "bar_minutes", "session_independent", "doc")
        return {**{k: meta[k] for k in keep if k in meta}, "inputs": meta.get("inputs") or []}

    draft_rows: list[dict] = [{}]      # [{(file, mtime_ns, size): its row}] as of the last listing

    @r.get("/drafts")
    def list_drafts():
        """A draft is read and parsed again only when its file's (mtime, size) changed."""
        out, rows = [], {}
        for name, path in draftstore.list_files():
            try:
                st = path.stat()
                key = (str(path), st.st_mtime_ns, st.st_size)
                row = draft_rows[0].get(key)
                if row is None:
                    code = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if row is None:
                meta, err, line = meta_or_error(code)
                row = {"name": name, "id": draftstore.draft_id(name), "bytes": st.st_size,
                       "modified": dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat(timespec="seconds"),
                       "ok": meta is not None, "meta": brief(meta),
                       **({"error": err, "line": line} if err else {})}
            rows[key] = row
            out.append(row)
        draft_rows[0] = rows               # one swap (the route runs in worker threads); gone files drop out
        return out

    @r.get("/drafts/templates")
    def draft_templates():
        return lab_templates.templates()

    @r.get("/drafts/reference")
    def draft_reference():
        return {"text": lab_templates.reference()}

    @r.post("/drafts/validate")
    async def validate_draft(request: Request):
        write_ok(request)
        json_body(request)
        try:
            code = code_of(await request.json())
        except ValueError:
            raise HTTPException(400, "the body is JSON") from None
        meta, err, line = meta_or_error(code)
        return {"ok": True, "meta": brief(meta)} if meta is not None else {"ok": False, "error": err, "line": line}

    @r.put("/drafts/{name}")
    async def save_draft(name: str, request: Request):
        write_ok(request)
        json_body(request)
        try:
            code = code_of(await request.json())
        except ValueError:
            raise HTTPException(400, "the body is JSON") from None
        try:
            draftstore.write(name, code, builtin_ids=builtin_ids())
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True, "name": name, "id": draftstore.draft_id(name), "meta": brief(draftstore.static_meta(code))}

    @r.delete("/drafts/{name}")
    def delete_draft(name: str, request: Request):
        write_ok(request)
        try:
            return {"deleted": draftstore.delete(name)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.post("/drafts/{name}/review-request")
    async def request_review(name: str, request: Request):
        write_ok(request)
        json_body(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is JSON") from None
        if not isinstance(body, dict) or set(body) - {"run_id", "note"}:
            raise HTTPException(400, "{run_id?, note?}")
        try:
            code = draftstore.read(name)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, f"no draft {name!r}") from None
        bundle = None
        if body.get("run_id") is not None:
            rid = str(body["run_id"])
            known(rid)
            try:
                bundle = await asyncio.to_thread(manager.bundle, rid)
            except ValueError as e:
                raise HTTPException(409, str(e)) from None
            if (bundle.get("run") or {}).get("strategy", {}).get("id") != draftstore.draft_id(name):
                raise HTTPException(409, f"run {rid} is not a run of draft_{name}")
        meta, _, _ = meta_or_error(code)
        return await asyncio.to_thread(reviewpack.create, name, code, meta, bundle, str(body.get("note") or ""))

    @r.post("/show")
    async def show(request: Request):
        """Ask every open chart page to load a finished run (or heat-map cell) into the Strategy Tester
        and show it on a chart. JSON only, behind the same Host + Origin guards as every write here;
        async (the page fan-out lives on the event loop) with the one small disk read in a thread.
        Answers how many pages were told -- 0 means no chart page is open."""
        write_ok(request)
        if not netguard.is_json(request.headers.get("content-type")):
            raise HTTPException(415, "send JSON (Content-Type: application/json)")
        if Slots().quiet():       # the desk's 9:30 window: never move a chart or decode history then
            raise HTTPException(409, "not 09:20–09:35 ET on weekdays (the 9:30 window): show it after 09:35")
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is JSON") from None
        if not isinstance(body, dict) or set(body) - {"run_id", "grid_id", "cell", "focus"}:
            raise HTTPException(400, "{run_id | grid_id + cell, focus?}")
        focus = check_focus(body.get("focus"))
        if "grid_id" in body or "cell" in body:
            if "run_id" in body or "grid_id" not in body or "cell" not in body:
                raise HTTPException(400, "either run_id, or grid_id + cell")
            gid, cell = str(body["grid_id"]), body["cell"]
            if isinstance(cell, bool) or not isinstance(cell, int) or cell < 0:
                raise HTTPException(400, "cell: a whole number")
            d = known_grid(gid) / "cells" / f"{cell:02d}"
            msg = {"type": "tester_show", "grid_id": gid, "cell": cell}
        else:
            rid = str(body.get("run_id", ""))
            d = known(rid)
            msg = {"type": "tester_show", "run_id": rid}
        st = await asyncio.to_thread(lambda: read_json(d / "status.json", {}) or {})
        if st.get("status") != "done":
            raise HTTPException(409, f"that run is {st.get('status') or 'missing'}, not done")
        if focus is not None:
            msg["focus"] = focus
        pages = notify(msg) if notify is not None else 0
        return {"ok": True, "pages": pages, **{k: v for k, v in msg.items() if k != "type"}}

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
        try:
            return grids.all_looks()
        except LooksCorrupt as e:           # refused, never shown as a reset counter
            raise HTTPException(409, str(e)) from None

    def known_wf(wid: str):
        try:
            return wfs.dir(wid)
        except KeyError:
            raise HTTPException(404, f"no walk-forward {wid!r}") from None

    @r.post("/walkforward")
    def start_walkforward(request: Request, body: dict):
        write_ok(request)
        try:
            return {"id": wfs.submit(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.get("/walkforward/{wid}")
    def walkforward_status(wid: str):
        known_wf(wid)
        return wfs.status(wid)

    @r.get("/walkforward/{wid}/result")
    def walkforward_result(wid: str, test_months: str | None = None):
        known_wf(wid)
        n = None
        if test_months is not None:
            if test_months not in ("1", "2", "3"):
                raise HTTPException(400, "test_months: one of 1, 2, 3 (the 1:N walk-forward ratio)")
            n = int(test_months)
        try:
            return wfs.result(wid, n)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/walkforward/{wid}/compare")
    def walkforward_compare(wid: str):
        known_wf(wid)
        try:
            return wfs.compare(wid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.post("/walkforward/{wid}/cancel")
    def cancel_walkforward(wid: str, request: Request):
        write_ok(request)
        known_wf(wid)
        return wfs.cancel(wid)

    @r.get("/walkforward-scheme")
    def walkforward_scheme(test_months: str | None = None, start: str | None = None, end: str | None = None):
        """The page reads its step count from here rather than assuming one (review M5) — now for
        the ratio and the window the range picker currently shows. `test_months` is parsed strictly:
        "2" is 1:2, "2.0" or "5" is a 400, never coerced."""
        try:
            if test_months == "compare":
                return walkforward.compare_scheme(start=start, end=end)
            n = walkforward.TEST_MONTHS if test_months is None else (
                int(test_months) if test_months.isdigit() else test_months)
            return walkforward.scheme(start=start, end=end, test_months=n)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.get("/walkforwards")
    def recent_walkforwards():
        return wfs.list()

    def _mc_int(body: dict, key: str, default: int, lo: int, hi: int) -> int:
        v = body.get(key, default)
        if v is None:
            v = default
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            raise HTTPException(400, f"{key}: expected a number")
        if float(v) != int(v):
            raise HTTPException(400, f"{key}: expected a whole number")
        v = int(v)
        if not lo <= v <= hi:
            raise HTTPException(400, f"{key}: must be within [{lo}, {hi}]")
        return v

    mc_cache: OrderedDict = OrderedDict()
    mc_lock = threading.Lock()

    @r.post("/montecarlo")
    def run_montecarlo(request: Request, body: dict):
        """A finished run's (or heat-map cell's, {grid_id, cell}) trades resampled by DAY --
        homebase.backtest.stats.montecarlo.run. The prop race is propsim's own run_eval under the
        run's own rules (skipped when the run's prop eval errored or its rule id is gone). The seed
        defaults to one derived from the run id, and the ruin floor to the rules' trailing max loss
        (else $2,000). Results are cached per (run, mode, seed, paths, floor). A plain `def`: FastAPI's
        threadpool runs it, never this service's event loop."""
        write_ok(request)
        if "grid_id" in body or "cell" in body:
            if "run_id" in body or "grid_id" not in body or "cell" not in body:
                raise HTTPException(400, "either run_id, or grid_id + cell")
            gid, cell = str(body["grid_id"]), body["cell"]
            if isinstance(cell, bool) or not isinstance(cell, int):
                raise HTTPException(400, "cell: a whole number")
            known_grid(gid)
            load = lambda: grids.cell_bundle(gid, cell)          # noqa: E731
        else:
            rid = str(body.get("run_id", ""))
            known(rid)
            load = lambda: manager.bundle(rid)                   # noqa: E731
        mode = body.get("mode", "shuffle")
        if mode not in ("shuffle", "bootstrap"):
            raise HTTPException(400, "mode: shuffle or bootstrap")
        seed = body.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, (int, float))):
            raise HTTPException(400, "seed: a number")
        floor = body.get("floor")
        if floor is not None and (isinstance(floor, bool) or not isinstance(floor, (int, float))
                                  or not 0 < floor < 1e12):
            raise HTTPException(400, "floor: a drawdown in $ above 0")
        paths = _mc_int(body, "paths", 5000, 1, montecarlo.MAX_PATHS)
        try:
            b = load()
        except KeyError:
            raise HTTPException(404, "no such heat-map cell") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        run_meta = b["run"] or {}
        source = run_meta.get("id") or ""
        seed = montecarlo.seed_for(source) if seed is None else int(seed)
        key = (source, mode, seed, paths, None if floor is None else float(floor))
        with mc_lock:
            if key in mc_cache:
                mc_cache.move_to_end(key)
                return mc_cache[key]
        rules = None
        if run_meta.get("prop_rules") and not run_meta.get("propsim_error"):
            try:
                rules = propsim.load_rules(run_meta["prop_rules"])
            except ValueError:
                rules = None    # an unknown/removed rule id: MC still runs, just without P(prop pass)
        try:
            out = montecarlo.run(b["trades"] or [], paths=paths, mode=mode, seed=seed, rules=rules, floor=floor)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        if rules is not None:
            confirmed = rules.get("confirmed") is not False
            out["prop_rules"] = {"id": run_meta["prop_rules"], "name": rules.get("name"), "confirmed": confirmed,
                                 "label": rules.get("name") if confirmed else f"{rules.get('name')} · unconfirmed rules"}
        with mc_lock:
            mc_cache[key] = out
            while len(mc_cache) > MC_CACHE:
                mc_cache.popitem(last=False)
        return out

    prop_cache: OrderedDict = OrderedDict()
    prop_lock = threading.Lock()

    def _rescore(source: tuple, load: Callable[[], dict], rule_id) -> dict:
        """A finished run's (or heat-map cell's) prop eval under `rule_id`, from its stored ledger.
        The run's OWN eval returns its saved propsim.json as is; any other runs the same
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
        if run_meta.get("prop_rules") == rule_id and b.get("propsim") is not None:
            out = b["propsim"]
        else:
            out, _ = _run_propsim(b["trades"] or [], {"prop_rules": rule_id, "prop_rules_data": rules})
        with prop_lock:
            prop_cache[key] = out
            while len(prop_cache) > PROP_CACHE:
                prop_cache.popitem(last=False)
        return out

    @r.post("/runs/{rid}/propsim")
    def rescore_run(rid: str, request: Request, body: dict):
        write_ok(request)
        known(rid)
        return _rescore(("run", rid), lambda: manager.bundle(rid), body.get("prop_rules"))

    @r.post("/propsim")
    def rescore(request: Request, body: dict):
        write_ok(request)
        if "grid_id" in body or "cell" in body:
            if "run_id" in body or "grid_id" not in body or "cell" not in body:
                raise HTTPException(400, "either run_id, or grid_id + cell")
            gid, cell = str(body["grid_id"]), body["cell"]
            if isinstance(cell, bool) or not isinstance(cell, int):
                raise HTTPException(400, "cell: a whole number")
            known_grid(gid)
            return _rescore(("cell", gid, cell), lambda: grids.cell_bundle(gid, cell), body.get("prop_rules"))
        rid = str(body.get("run_id", ""))
        known(rid)
        return _rescore(("run", rid), lambda: manager.bundle(rid), body.get("prop_rules"))

    r.manager = manager   # so the chart service can stop an in-flight child on shutdown
    r.grids = grids       # likewise every grid cell's child
    r.wfs = wfs           # ... and every walk-forward cell's
    return r


def tester_router(write_ok: Callable[[Request], None], archive: Path,
                  state: Path | None = None, notify: Callable[[dict], int] | None = None) -> APIRouter:
    """Production (state None): homebase/.state/tester + the ~/futures_derived tape
    cache. A test passes its tmp dir and gets the runs AND the cache under it."""
    base = Path(state) if state else default_base()
    cache = base / "tape" if state else CACHE
    return make_router(write_ok, RunManager(base, archive=archive, cache=cache),
                       GridManager(base, archive=archive, cache=cache),
                       WalkForwardManager(base, archive=archive, cache=cache), notify=notify)
