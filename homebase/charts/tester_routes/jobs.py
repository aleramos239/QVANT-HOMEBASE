"""make_router's job routes, moved verbatim: runs, heat maps (grids), looks, walk-forwards, Monte Carlo and the prop-eval
re-scores of saved runs and cells."""
from __future__ import annotations

import threading
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ... import draftstore
from ...backtest import propsim
from ...backtest.grid import LooksCorrupt
from ...backtest.stats import montecarlo
from ...backtest import walkforward
from ...backtest.runner import _settled


MC_CACHE = 64            # Monte Carlo results kept per service (review I3)
WF_RESULT_CACHE = 64 << 20      # bytes of finished walk-forward results kept per service (an old one runs to 10 MB)
# every file WalkForwardManager.result reads (and oos_view, for a fixed job's test months)
WF_RESULT_FILES = ("grid.json", "result.json", "result-1.json", "result-2.json", "result-3.json", walkforward.LOCK,
                   walkforward.CLAIM, walkforward.OOS, "oos-job.json")


def wf_stamp(d) -> tuple | None:
    """The stamps of the files a walk-forward's result is read from (write_json replaces a file: a new inode); None when one
    cannot be looked at (nothing is then kept or served from memory)."""
    out = []
    for f in WF_RESULT_FILES:
        try:
            s = (d / f).stat()
            out.append((s.st_mtime_ns, s.st_size, s.st_ino))
        except FileNotFoundError:
            out.append(None)
        except OSError:
            return None
    return tuple(out)


def register(r: APIRouter, ctx) -> None:
    write_ok, manager, grids, wfs, known, known_grid, _rescore = (ctx.write_ok, ctx.manager, ctx.grids, ctx.wfs, ctx.known,
                                                                   ctx.known_grid, ctx.rescore)

    @r.get("/prop-rules")
    def prop_rules():
        return propsim.list_rules()

    @r.post("/run")
    def start_run(request: Request, body: dict):
        write_ok(request)
        try:
            # A "Blueprint record" draft places no trades itself; its real result is a saved research-engine run.
            sid = str(body.get("strategy") or "")
            if draftstore.is_draft_id(sid):
                try:
                    src = draftstore.read(draftstore.name_of(sid))
                except Exception:
                    src = ""
                if "# >>> BLUEPRINT RECORD" in src:
                    for x in manager.runs_list(limit=400):
                        if x.get("strategy") == sid and x.get("status") == "done" and (x.get("trades") or 0) > 0:
                            return {"id": x["id"]}
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
        """The stored files as JSON text, never parsed here: a plots.json of a per-bar indicator is 300 MB, and
        FastAPI would encode a parsed dict ON THE EVENT LOOP (20 s, ~5 GB: the 2026-10-11 black Charts page)."""
        known(rid)
        try:
            return Response(manager.bundle_bytes(rid), media_type="application/json")
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/runs")
    def recent_runs(limit: int = 50, strategy: str | None = None):
        return manager.runs_list(max(1, min(int(limit), 500)), strategy)

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
            return Response(grids.cell_bundle_bytes(gid, i), media_type="application/json")
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

    @r.post("/run-match")
    def run_match(request: Request, body: dict):
        """{id}: the newest finished run that this Run body would only repeat (same request, same code), or null."""
        write_ok(request)
        try:
            return {"id": manager.same_done(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.post("/walkforward-match")
    def walkforward_match(request: Request, body: dict):
        """{id}: the newest finished walk-forward that this Run body would only repeat (same settings, months, code), or null."""
        write_ok(request)
        try:
            return {"id": wfs.same_done(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.get("/walkforward/{wid}")
    def walkforward_status(wid: str):
        known_wf(wid)
        return wfs.status(wid)

    wf_bytes: OrderedDict = OrderedDict()       # (wid, test_months) -> (wf_stamp, the response body)
    wf_bytes_lock = threading.Lock()
    claim_at, oos_at = WF_RESULT_FILES.index(walkforward.CLAIM), WF_RESULT_FILES.index(walkforward.OOS)

    @r.get("/walkforward/{wid}/result")
    def walkforward_result(wid: str, test_months: str | None = None):
        d = known_wf(wid)
        n = None
        if test_months is not None:
            if test_months not in ("1", "2", "3"):
                raise HTTPException(400, "test_months: one of 1, 2, 3 (the 1:N walk-forward ratio)")
            n = int(test_months)
        stamp = wf_stamp(d)
        with wf_bytes_lock:
            hit = wf_bytes.get((wid, n))
            if hit is not None and hit[0] == stamp:
                wf_bytes.move_to_end((wid, n))
                return Response(hit[1], media_type="application/json")     # JSONResponse's own headers
        try:
            res = wfs.result(wid, n)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        # FastAPI's own encoding (the same bytes), done here in the threadpool: an old result runs to 10 MB and froze the
        # event loop that carries chart orders and fills while it was encoded there
        out = JSONResponse(jsonable_encoder(res))
        # kept only when no file changed while it was read, none was written in the last 2 s, and no test-month read is under
        # way (its progress moves)
        if stamp is not None and wf_stamp(d) == stamp and (stamp[claim_at] is None or stamp[oos_at] is not None) \
                and _settled(*stamp):
            with wf_bytes_lock:
                wf_bytes[(wid, n)] = (stamp, out.body)
                wf_bytes.move_to_end((wid, n))
                while wf_bytes and sum(len(b) for _, b in wf_bytes.values()) > WF_RESULT_CACHE:
                    wf_bytes.popitem(last=False)
        return out

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

    @r.post("/walkforward/{wid}/pick")
    def pick_walkforward(wid: str, request: Request, body: dict):
        write_ok(request)
        known_wf(wid)
        try:
            return wfs.pick(wid, body.get("cell"))
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.post("/walkforward/{wid}/oos")
    def oos_walkforward(wid: str, request: Request, body: dict):
        write_ok(request)
        known_wf(wid)
        try:
            return wfs.oos(wid, body.get("cell"), body.get("owner_said"))
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/walkforward-scheme")
    def walkforward_scheme(test_months: str | None = None, start: str | None = None, end: str | None = None,
                           select_months: str | None = None, step_months: str | None = None):
        """The page reads its step count from here rather than assuming one (review M5) — now for
        the ratio and the window the range picker currently shows. `test_months` is parsed strictly:
        "2" is 1:2, "2.0" or "5" is a 400, never coerced."""
        try:
            if test_months == "compare":
                return walkforward.compare_scheme(start=start, end=end)
            n = walkforward.TEST_MONTHS if test_months is None else (
                int(test_months) if test_months.isdigit() else test_months)
            sel = walkforward.SELECT_MONTHS if select_months is None else (
                int(select_months) if select_months.isdigit() else select_months)
            step = None if step_months is None else (int(step_months) if step_months.isdigit() else step_months)
            return walkforward.scheme(start=start, end=end, test_months=n, select_months=sel, step_months=step)
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
            load = lambda: grids.cell_bundle(gid, cell, plots=False)   # noqa: E731
        else:
            rid = str(body.get("run_id", ""))
            known(rid)
            load = lambda: manager.bundle(rid, plots=False)      # noqa: E731
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
            out = montecarlo.run(b["trades"] or [], paths=paths, mode=mode, seed=seed, rules=rules, floor=floor,
                                 months=(run_meta.get("range") or {}).get("months"))
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

    @r.post("/runs/{rid}/propsim")
    def rescore_run(rid: str, request: Request, body: dict):
        write_ok(request)
        known(rid)
        return _rescore(("run", rid), lambda: manager.bundle(rid, plots=False), body.get("prop_rules"))

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
            return _rescore(("cell", gid, cell), lambda: grids.cell_bundle(gid, cell, plots=False), body.get("prop_rules"))
        rid = str(body.get("run_id", ""))
        known(rid)
        return _rescore(("run", rid), lambda: manager.bundle(rid, plots=False), body.get("prop_rules"))
