"""make_router's Desk routes, moved verbatim: the Lab strategies on the Desk (/desklab*: list, shadow calendar, results,
promote / remove / archive ...), the Lab-open handoff and the Desk groups (/deskgroups*), with the Desk results warm-up.
tester_api keeps desk_strategy_ids and DESKLAB_AUTO_UNSEEN (the tests patch them there): read as api.<name>."""
from __future__ import annotations

import asyncio
import contextlib
import copy
import datetime as dt
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ...store import draftstore
from ...backtest import propsim, sandbox, slots, walkforward
from ...backtest.runner import _settled, read_json
from ...backtest.tape import TapeStore
from ...labrun import door, store
from ..desk import DESK_URL
from ...labrun.host import session_today
from .. import deskfamilies, deskgroups, deskresults
from ..paperbook import DESK_ORIGINS, _cors, desk_origin_refusal
from .jobs import WF_RESULT_FILES, wf_stamp


DESKLAB_ACTIONS = ("promote", "remove", "delete", "onoff", "open", "archive", "filed", "restore", "archive_builtin",
                   "restore_builtin")
ARCHIVE_GROUP = "Archive"     # the Lab group an archived strategy's draft is filed under (the owner, 2026-10-18)
DESKGROUP_ACTIONS = ("create", "rename", "kind", "delete", "move")
DESKLAB_ALIVE_S = 20     # the Lab-strategy runner is alive while its heartbeat is at most this old
DESKLAB_TAKE_OFF = "Take its accounts off on the Desk first."   # Promote again / Remove while the desk has it booked
DESKLAB_TO = ("mac", "vps", "both")   # where Promote puts it: "vps" and "both" also send the record to the server's Desk (OFF, no account)
DESKLAB_PROP = "lucid-pro-50k-no-dll@2026-10-11"   # the account every Desk panel's prop sim is scored on (the pipeline's account; owner 2026-10-11)
DESKLAB_SHADOW_DAYS = 800    # the shadow calendar: about three years of session days
DESKLAB_DAYS = 10        # day summaries shown under each promoted strategy ...
DESKLAB_DAY_KEYS = ("date", "state", "why", "net", "match")      # ... each cut to these and `rebuilt` (no order or trade rows)
DESKLAB_BLOCKS = 256     # card blocks kept per service (one per Desk strategy and month: ~20 KB each, curves included)


def send_to_vps(name: str) -> list[str]:
    """Send the promoted record to the server's Desk, the way deploy/linux/send_strategy.py does (same checks, never --replace):
    the lines to show. Nothing here raises: a server that cannot take it is a line, and the Mac's record stays."""
    import importlib.util
    from pathlib import Path
    try:
        path = Path(__file__).resolve().parents[3] / "deploy" / "linux" / "send_strategy.py"
        spec = importlib.util.spec_from_file_location("send_strategy", path)
        ss = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ss)
        why = ss.server_ready()
        return [f"Not sent to the VPS: {why}"] if why else ss.send(name, go=True)[1]
    except Exception as e:      # ssh missing, a timeout, the script gone: the promote on this Mac already happened
        return [f"Not sent to the VPS: {type(e).__name__}: {e}"]


def register(r: APIRouter, ctx) -> Callable[[], None]:
    write_ok, manager, wfs, live_roots, json_body, _rescore = ctx.write_ok, ctx.manager, ctx.wfs, ctx.live_roots, ctx.json_body, ctx.rescore
    api = ctx.api

    # ---- the Desk page's cross-origin guard and answer, shared by the desklab routes below (the watch list was removed 2026-10-10) ----
    def watch_guard(request: Request) -> None:
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)

    def watch_answer(request: Request, body: dict, status: int = 200):
        return _cors(JSONResponse(body, status_code=status), request)

    # ---- Lab strategies on the Desk (labrun/store.py): a frozen copy of a draft, kept as a record. Text and files only:
    # ---- nothing here runs a draft's code, places an order or talks to the desk (the runner process reads the store).
    @r.get("/desklab")
    def desklab_list(request: Request):
        watch_guard(request)
        now_ms = int(slots.et_now().timestamp() * 1000)
        out = []
        for rec in store.listing():
            # `today` is the session day the runner is on for that market (it rolls at 18:00 ET; a weekend has none),
            # and a day counts only when THIS promotion wrote it: another promotion's day is never shown as this one's
            name, date = rec["name"], session_today(now_ms, rec.get("root"))
            today = store.get_day(name, date.isoformat()) if date is not None else None
            out.append({**{k: v for k, v in rec.items() if k != "source"},
                        "today": today if store.same_promotion(today, rec) else None,
                        "days": [{**{k: d.get(k) for k in DESKLAB_DAY_KEYS}, "rebuilt": d.get("rebuilt") is True}
                                 for d in store.days(name, DESKLAB_DAYS) if store.same_promotion(d, rec)]})
        beat = store.get_runner() or {}
        archived = [{k: rec.get(k) for k in ("name", "label", "root", "run", "archived_utc", "promoted_utc")} for rec in store.archived()]
        archived += [{"name": k, "builtin": True, "archived_utc": v.get("archived_utc")} for k, v in store.archived_builtins().items()]
        return watch_answer(request, {"strategies": out, "archived": archived, "builtins": api.desk_strategy_ids(),
                                      "runner": {
            "alive": runner_alive(beat.get("seen_utc")), "seen_utc": beat.get("seen_utc"), "prices": beat.get("prices") or {}}})

    @r.get("/desklab/shadow")
    def desklab_shadow(request: Request, name: str = ""):
        """The Desk's shadow calendar (the owner, 2026-10-19): every day THIS promotion wrote, oldest first, with its trades."""
        watch_guard(request)
        rec = store.get(name) if draftstore.NAME_RE.fullmatch(name or "") else None
        if rec is None:
            raise HTTPException(404, "not on the Desk")
        days = []
        for d in store.days(name, DESKLAB_SHADOW_DAYS):
            if not store.same_promotion(d, rec):
                continue
            if d.get("mode") == "desk":      # a booked day: its shadow copy (the runner's, 2026-10-20), never its real trades
                try:
                    d = store.get_shadow_day(name, d.get("date"))
                except ValueError:
                    continue
                if not store.same_promotion(d, rec):
                    continue                 # booked before the copy existed: nothing would-be to show
            days.append({k: d.get(k) for k in DESKLAB_DAY_KEYS + ("trades",)})
        return watch_answer(request, {"name": name, "days": days[::-1]})

    def runner_alive(seen) -> bool:
        try:
            t = dt.datetime.fromisoformat(seen)
        except (TypeError, ValueError):
            return False
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return abs((dt.datetime.now(dt.timezone.utc) - t).total_seconds()) <= DESKLAB_ALIVE_S

    desk_res_lock = threading.Lock()     # one asker at a time: a run's first prop sim takes about 1.5 s, then it is kept
    unseen_lock = threading.Lock()

    def covers(rec: dict, req: dict) -> bool:
        """This host's tick archive holds the run's first month. The VPS keeps only recent ticks: a run there read 47 days and
        the card called them 45 + 15 months (2026-10-24, nq_wick_break_28) -- such a run is made on the Mac and copied over."""
        a = dt.date.fromisoformat(req["range"]["start"])
        return bool(TapeStore(manager.archive, manager.cache).sessions(rec.get("root") or "NQ", a, a + dt.timedelta(days=31)))

    def ensure_unseen(rec: dict) -> dict:
        """The state of the record's unseen-days run (deskresults.unseen_state); when there is none, start it -- once: a run
        that failed or was cancelled is not started again by itself. A start the tester refuses (a quiet window of the tester,
        a sandbox that is down) leaves the state as it was, and the next ask tries again. Never raises."""
        try:
            with unseen_lock:
                got = deskresults.unseen_state(manager.runs, rec)
                if got["state"] != "none" or not api.DESKLAB_AUTO_UNSEEN:
                    return got
                req = deskresults.unseen_request(rec, slots.et_now().date())
                if not covers(rec, req):
                    return got
                try:
                    manager.submit(req)
                except Exception:      # noqa: BLE001 -- not now: refused in words by the tester, or not working
                    return got
                return deskresults.unseen_state(manager.runs, rec)
        except Exception:      # noqa: BLE001 -- a panel's research never costs a promote or the list its answer
            return {"state": "none"}

    def prop_of(rid):
        try:
            return deskresults.prop_headline(_rescore(("run", rid), lambda: manager.bundle(rid, plots=False), DESKLAB_PROP))
        except (HTTPException, KeyError, ValueError, OSError):      # a run that was deleted or cannot be read: nothing to show
            return None

    wf_lock = threading.Lock()

    def ensure_wf(rec: dict) -> dict:
        """The state of the record's 3:1 walk-forward (deskresults.wf_state); when there is none, start it -- once, as
        ensure_unseen does, and only while DESKLAB_AUTO_UNSEEN is on. Off (S4) nothing starts: the newest done one of this copy
        that ends a month or more earlier is shown, with the month it reaches. {"state": "changed"} when the Lab's code is no
        longer the promoted copy (a run of it would never match). Never raises."""
        today = slots.et_now().date()
        try:
            with wf_lock:
                got = deskresults.wf_state(wfs.grids, rec, today, older=not api.DESKLAB_AUTO_UNSEEN)
                if got["state"] != "none":
                    return got
                try:
                    src = draftstore.read(rec["name"])
                except (FileNotFoundError, ValueError, OSError):
                    return {"state": "changed"}
                if hashlib.sha256(src.encode("utf-8")).hexdigest() != rec.get("sha256"):
                    return {"state": "changed"}
                req = deskresults.wf_request(rec, today)
                if not covers(rec, req):
                    return {"state": "no_data"}
                if not api.DESKLAB_AUTO_UNSEEN:      # only the start is off (S4): "changed" and "no_data" above still say so
                    return got
                try:
                    wfs.submit(req)
                except Exception:      # noqa: BLE001 -- not now: refused in words by the tester, or not working
                    return got
                return deskresults.wf_state(wfs.grids, rec, today)
        except Exception:      # noqa: BLE001 -- a panel's research never costs a promote or the list its answer
            return {"state": "none"}

    def wf_prop(key: tuple, trades: list, months=None, failed: list | None = None):
        try:        # months: the side's own (1 in 4 for the unseen side): the others are no flat days of it (2026-10-24)
            return deskresults.prop_headline(_rescore(key, lambda: {"run": {"range": {"months": months}}, "trades": trades}, DESKLAB_PROP))
        except (HTTPException, KeyError, ValueError, OSError):
            if failed is not None:
                failed.append(key)
            return None

    blocks: OrderedDict = OrderedDict()     # walk-forward id -> (block_key, the card's block): wf_block
    blocks_lock = threading.Lock()
    claim_at, oos_at = WF_RESULT_FILES.index(walkforward.CLAIM), WF_RESULT_FILES.index(walkforward.OOS)

    def block_key(wid: str):
        """What a done walk-forward's card block is made from: the stamps of the files its result is read from and the prop
        account's rules version; None when it cannot be kept (a file under 2 s old or not to be looked at, a test-month read
        under way, rules that do not load)."""
        now = time.time_ns()
        try:
            stamp, version = wf_stamp(wfs.dir(wid)), propsim.load_rules(DESKLAB_PROP).get("version")
        except (KeyError, ValueError, OSError):
            return None
        if stamp is None or not _settled(now, *stamp) or (stamp[claim_at] is not None and stamp[oos_at] is None):
            return None
        return stamp, version

    def wf_block(rec: dict, state=None) -> dict:
        """The card's block from the 3:1 walk-forward of the strategy as set: {build, unseen, both, unseen_state, curve, prop_build,
        prop_unseen, prop_both} -- build = its in-sample months, unseen = its out-of-sample months, both = all of them as one run.
        state: where the walk-forward stands (ensure_wf, which may start it; the warm-up passes the read-only wf_state). A done
        one's block is kept until one of its files or the prop rules change; it is worked out under desk_res_lock (one prop sim
        at a time), a kept one is not."""
        got = (state or ensure_wf)(rec)
        out = {"build": None, "unseen": None, "both": None, "unseen_state": got["state"], "curve": None, "curve_build": None,
               "prop_build": None, "prop_unseen": None, "prop_both": None}
        if got["state"] != "done":
            return out
        wid, key = got["id"], block_key(got["id"])

        def kept():
            with blocks_lock:
                hit = blocks.get(wid)
                if key is not None and hit is not None and hit[0] == key:
                    blocks.move_to_end(wid)
                    return copy.deepcopy(hit[1])
            return None
        hit = kept()
        if hit is not None:
            return hit
        with desk_res_lock:
            hit = kept()                    # worked out by another ask while this one waited
            if hit is not None:
                return hit
            try:
                res = wfs.result(wid)
            except (ValueError, KeyError, OSError):
                out["unseen_state"] = "failed"
                return out
            failed: list = []
            oos, ins = (res.get("stitched") or {}).get("trades") or [], (res.get("stitched_is") or {}).get("trades") or []
            out.update(unseen=deskresults.wf_summary(wid, res), build=deskresults.wf_summary(wid, res, "stitched_is"),
                       curve=deskresults.curve_of_trades(oos), curve_build=deskresults.curve_of_trades(ins),
                       prop_unseen=wf_prop(("wf", wid), oos, (res.get("stitched") or {}).get("months"), failed),
                       prop_build=wf_prop(("wf-is", wid), ins, (res.get("stitched_is") or {}).get("months"), failed),
                       both=deskresults.wf_both(wid, res), prop_both=wf_prop(("wf-both", wid), *both_side(res), failed=failed))
            if key is not None and not failed and block_key(wid) == key:     # nothing changed while it was read
                with blocks_lock:
                    blocks[wid] = (key, copy.deepcopy(out))
                    blocks.move_to_end(wid)
                    while len(blocks) > DESKLAB_BLOCKS:
                        blocks.popitem(last=False)
        return out

    def both_side(res: dict) -> tuple:
        """(trades, months) of Build + Unseen together, in date order (the prop sim of the whole walk-forward)."""
        ins, oos = res.get("stitched_is") or {}, res.get("stitched") or {}
        trades = sorted((ins.get("trades") or []) + (oos.get("trades") or []), key=lambda t: (t.get("entry_ms") or 0))
        return trades, sorted(set(ins.get("months") or []) | set(oos.get("months") or []))

    def read_wf(rec: dict) -> dict:
        """ensure_wf without the start: the warm-up reads saved walk-forwards only."""
        return deskresults.wf_state(wfs.grids, rec, slots.et_now().date(), older=not api.DESKLAB_AUTO_UNSEEN)

    def warm_desklab_results() -> None:
        """Score every promoted strategy's (and the two built-in straddles' twins') saved runs, so the Desk's first results
        ask is a cache hit (about 16 prop sims: 25-90 s cold; a new run was 3-4 s on the next ask). One pass; the chart
        service repeats it every WARM_EVERY_S. Reads saved runs only and never starts one (unlike ensure_unseen). The lock
        is taken per record (and per group: the Desk groups' prop sims too), so a real ask is never held behind the whole
        warm-up. Never raises."""
        try:
            for rec in store.listing():
                try:                        # the card's block and its three prop sims: the 3:1's in-sample, test months and Both
                    wf_block(rec, read_wf)
                except Exception:      # noqa: BLE001 -- the route computes it on ask
                    pass
            for desk_id in deskresults.BUILTIN_TWINS:      # the Desk's own straddles: their twin's saved runs
                try:
                    rec = deskresults.builtin_rec(desk_id)
                    with desk_res_lock:
                        for rid in (deskresults.build_run_id(manager.runs, rec),
                                    (deskresults.unseen_state(manager.runs, rec) or {}).get("run", {}).get("id")):
                            if rid:
                                prop_of(rid)
                except Exception:      # noqa: BLE001 -- a twin that cannot be read is skipped, as the route does
                    continue
            for g in deskgroups.load():     # each group's three prop sims, from its members' saved walk-forwards
                try:
                    with desk_res_lock:
                        for side, chosen in group_sides(g, read_wf)[2].items():
                            ledger, _, key = side_ledger(side, chosen)
                            group_prop(key, ledger)
                except Exception:      # noqa: BLE001 -- the route computes it on ask
                    continue
        except Exception:      # noqa: BLE001 -- a warm-up never takes the service down; the route computes it on ask
            pass

    @r.get("/desklab/results")
    def desklab_results(request: Request):
        """The research the Desk's panel shows beside a promoted strategy (deskresults.py). Saved runs and their saved trades
        only: no strategy runs and no test day is read. A plain `def`: FastAPI's threadpool, not the loop."""
        watch_guard(request)
        out = {}
        for rec in store.listing():
            # build and unseen days ARE the 3:1 walk-forward's in- and out-of-sample months, the strategy as set (owner, 2026-10-18)
            got = ensure_wf(rec)
            w = wf_block(rec, lambda _: got)    # takes desk_res_lock itself, only to work a block out
            out[rec["name"]] = {"build": w["build"], "unseen": w["unseen"], "both": w["both"], "unseen_state": w["unseen_state"],
                                "curve": w["curve"], "curve_build": w["curve_build"], "walkforward": True,
                                "prop": {"build": w["prop_build"], "unseen": w["prop_unseen"], "both": w["prop_both"]}}
            if got.get("through") and w["unseen"]:      # an older 3:1 (S4): the card names the months it lacks
                out[rec["name"]].update(through=got["through"], to=got["to"])
        with desk_res_lock:
            # the Desk's own straddles (nq930, gc_nfp): their tester twin's SAVED runs, at the Desk's size and setting. Nothing here
            # starts a run (the unseen days of a built-in are read by hand, once, from the Lab): "manual" says so to the page.
            for desk_id in deskresults.BUILTIN_TWINS:
                try:
                    rec = deskresults.builtin_rec(desk_id)
                    got = deskresults.unseen_state(manager.runs, rec)
                    build, unseen = deskresults.build_run_id(manager.runs, rec), got.get("run")
                    out[desk_id] = {"unseen": unseen, "unseen_state": got["state"], "manual": True, "twin": rec["id"],
                                    "build": deskresults.run_summary(manager.runs, build) if build else None,
                                    "curve": deskresults.curve_of(manager.runs, unseen["id"]) if unseen else None,
                                    "prop": {"build": prop_of(build) if build else None,
                                             "unseen": prop_of(unseen["id"]) if unseen else None}}
                except Exception:      # noqa: BLE001 -- a twin that cannot be read leaves the Desk's page as it was
                    continue
        return watch_answer(request, {"results": out})

    @r.options("/desklab/{what}")
    def desklab_preflight(what: str, request: Request):
        """The desk page's CORS preflight: for its exact origins only."""
        o = request.headers.get("origin")
        if what not in DESKLAB_ACTIONS or o not in DESK_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return Response(status_code=204, headers={
            "access-control-allow-origin": o, "vary": "Origin", "access-control-allow-methods": "POST",
            "access-control-allow-headers": "content-type", "access-control-max-age": "600"})

    def desklab_promote(name: str, run_id: str) -> dict:
        """The refusals, in order; then the record. Reads text and small files only (draftstore, static_meta, read_source)."""
        try:
            source = draftstore.read(name)
        except (FileNotFoundError, ValueError, OSError):
            raise HTTPException(404, "That strategy is not in the Lab.") from None
        run_first = HTTPException(409, "Run a backtest of this strategy first.")
        try:
            d = manager.dir(run_id)
        except KeyError:
            raise run_first from None
        status, req, run = (read_json(d / f, None) for f in ("status.json", "request.json", "run.json"))
        if not isinstance(status, dict) or status.get("status") != "done" or not isinstance(run, dict) \
                or not isinstance(req, dict) or req.get("strategy") != draftstore.draft_id(name):
            raise run_first
        if req.get("draft_sha256") != hashlib.sha256(source.encode("utf-8")).hexdigest():
            raise HTTPException(409, "The code changed since this backtest. Run it again, then promote.")
        # The Desk runs the strategy's own on_bar / on_time only: the trade rules (run controls) and a print-by-print
        # `scan` entry are tester-side, so a run that used either is not what would run there (2026-10-12).
        if req.get("controls"):
            raise HTTPException(409, "This backtest used Trade rules (" + ", ".join(sorted(req["controls"])) + "), which the Desk does "
                                "not apply. Run it again with them off, then promote.")
        ins = req.get("inputs") if isinstance(req.get("inputs"), dict) else {}
        if ins.get("trigger") == "instant" and re.search(r"^\s*def scan\(", source, re.M):
            raise HTTPException(409, "Entry is set to instant, which the Desk does not run (it acts on bar closes). "
                                "Run it again with Entry = bar_close, then promote.")
        try:
            meta = draftstore.static_meta(source)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        if meta.get("session_independent") is not True:
            raise HTTPException(409, "It must not carry anything from one day to the next (set session_independent = True).")
        if meta["root"] not in live_roots:
            raise HTTPException(409, f"No live prices for {meta['root']} here.")
        if not sandbox.available():
            raise HTTPException(503, "The sandbox is not working, so it cannot run.")
        notes = door.read_source(source)
        with store.write_lock():             # the check and the write are one step: the desk may book an account now
            if store.booked(name):
                raise HTTPException(409, DESKLAB_TAKE_OFF)
            trades = read_json(d / "trades.json", None)
            trades = trades.get("trades") if isinstance(trades, dict) else trades
            store.put(store.snapshot(name, source, meta, {"run": run, "trades": trades}, run_id, notes))
        ensure_wf(store.get(name))          # starts its 3:1 walk-forward only while DESKLAB_AUTO_UNSEEN is on (off, S4)
        return {"ok": True, "name": name, "notes": notes}

    def desklab_remove(name: str) -> dict:
        """Refused while accounts are assigned on the Desk (the desk's sidecar holds book rows); the sidecar itself
        is the desk's and is never written here."""
        with store.write_lock():
            if store.booked(name):
                raise HTTPException(409, DESKLAB_TAKE_OFF)
            return {"ok": True, "removed": store.remove(name), "name": name}

    def desklab_delete(name: str, draft: bool = False) -> dict:
        """Remove's second step when the owner deletes (2026-10-20): the history goes too (store.delete). Refused while it
        is still on the Desk, and while a live runner still hosts it -- letting a day go writes its last day file, which
        would put the folder back. draft (the Archive's Delete, 2026-10-22): the Lab draft goes as well, into the drafts'
        trash, and off its Lab group."""
        beat = store.get_runner() or {}
        if runner_alive(beat.get("seen_utc")) and name in (beat.get("hosting") or []):
            raise HTTPException(409, "The runner is still letting it go. Try again in a few seconds.")
        done = store.delete(name)
        if done is None:
            raise HTTPException(409, "Remove it from the Desk first.")
        if draft:
            with store.write_lock():              # not while a Promote is putting it back on the Desk
                if store.has_record_file(name):
                    raise HTTPException(409, "Remove it from the Desk first.")
                try:
                    done = draftstore.delete(name) or done
                    draftstore.set_group(draftstore.draft_id(name), None)
                except (OSError, ValueError, draftstore.GroupsUnreadable):
                    raise HTTPException(500, "Its history is deleted, but its Lab draft could not be moved to the trash.") from None
        return {"ok": True, "deleted": done, "name": name}

    # ---- Archive (the owner, 2026-10-18): off the Desk, kept, put back on with one click. The page runs it in three steps
    # ---- so the Desk's own Remove (with its "Flatten it first." and its accounts coming off) stays the one way off the Desk:
    # ---- archive = a copy is kept; the Desk removes it; filed = its Lab draft goes under the "Archive" group.
    def desklab_archive(name: str) -> dict:
        if store.archive_copy(name) is None:
            raise HTTPException(404, "That strategy is not on the Desk.")
        return {"ok": True, "name": name}

    def lab_group(sid: str):
        try:
            return draftstore.read_groups()["members"].get(sid)
        except draftstore.GroupsUnreadable:
            return None

    def desklab_filed(name: str) -> dict:
        sid, was = draftstore.draft_id(name), lab_group(draftstore.draft_id(name))
        if store.archive_note(name, was, keep=was == ARCHIVE_GROUP) is None:
            raise HTTPException(409, "It is still on the Desk, so it was not archived.")
        if name in {n for n, _ in draftstore.list_files()}:
            with contextlib.suppress(draftstore.GroupsUnreadable, ValueError):     # the archive holds it either way
                draftstore.set_group(sid, ARCHIVE_GROUP)
        return {"ok": True, "name": name}

    def desklab_restore(name: str) -> dict:
        try:
            rec = store.restore(name)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        if rec is None:
            raise HTTPException(404, "That strategy is not in the archive.")
        sid = draftstore.draft_id(name)
        if lab_group(sid) == ARCHIVE_GROUP:
            with contextlib.suppress(draftstore.GroupsUnreadable, ValueError):
                draftstore.set_group(sid, rec.get("group_was"))
        return {"ok": True, "name": name}

    def desklab_archive_builtin(name: str) -> dict:
        """One of the Desk's own strategies (nq930, gc_nfp): the page has switched it off, after the Desk's checks; here it is noted
        as archived (the page hides it) and its tester twin is filed under the Lab's "Archive" group."""
        if name not in api.desk_strategy_ids():
            raise HTTPException(404, "That is not one of the Desk's own strategies.")
        twin = deskresults.BUILTIN_TWINS.get(name)
        was = lab_group(twin) if twin else None
        store.archive_builtin(name, was, keep=was == ARCHIVE_GROUP)
        if twin:
            with contextlib.suppress(draftstore.GroupsUnreadable, ValueError):
                draftstore.set_group(twin, ARCHIVE_GROUP)
        return {"ok": True, "name": name}

    def desklab_restore_builtin(name: str) -> dict:
        rec = store.restore_builtin(name)
        if rec is None:
            raise HTTPException(404, "That strategy is not in the archive.")
        twin = deskresults.BUILTIN_TWINS.get(name)
        if twin and lab_group(twin) == ARCHIVE_GROUP:
            with contextlib.suppress(draftstore.GroupsUnreadable, ValueError):
                draftstore.set_group(twin, rec.get("group_was"))
        return {"ok": True, "name": name}

    open_ask = {"name": None, "run": None, "wf": None, "builtin": False, "at": 0.0}      # the Desk page's "Open in the Lab": one request, kept for a short while

    def desklab_open(name: str, run: str | None = None, builtin: bool = False, wf: str | None = None) -> dict:
        """The Desk page asks the Lab page to show one draft. The Mac app drops a link's #fragment when it switches
        tab, so the ask waits here and the Lab page takes it (GET /lab-open) the moment it is shown. `run`: a finished run of
        it to put on the chart as well (the Desk's "Show on chart"). `builtin`: the name is a built-in tester strategy (the twin
        of one of the Desk's own straddles), not a draft. `wf`: its 3:1 walk-forward, opened as "3:1 out-of-sample" (the Desk's
        "Open in the Lab" for a promoted strategy, 2026-10-18)."""
        if builtin:
            if name not in deskresults.BUILTIN_TWINS.values():
                raise HTTPException(404, "That strategy is not in the Lab.")
        else:
            try:
                draftstore.read(name)
            except (FileNotFoundError, ValueError, OSError):
                raise HTTPException(404, "That strategy is not in the Lab.") from None
        if wf is not None:
            try:
                wfs.dir(wf)
            except KeyError:
                raise HTTPException(404, "That walk-forward is not saved.") from None
        open_ask["name"], open_ask["run"], open_ask["builtin"], open_ask["at"] = name, run, bool(builtin), time.monotonic()
        open_ask["wf"] = wf
        return {"ok": True, "name": name}

    @r.get("/lab-open")
    def lab_open_take():
        """The Lab page takes the Desk's ask, once: {name} (null when none, or one older than two minutes)."""
        name, run, at, builtin, wf = open_ask["name"], open_ask["run"], open_ask["at"], open_ask["builtin"], open_ask["wf"]
        open_ask["name"] = open_ask["run"] = open_ask["wf"] = None
        open_ask["builtin"] = False
        fresh = bool(name) and time.monotonic() - at <= 120
        return {"name": name if fresh else None, **({"run": run} if fresh and run else {}), **({"wf": wf} if fresh and wf else {}),
                **({"builtin": True} if fresh and builtin else {})}

    def desklab_onoff(name: str, on: bool) -> dict:
        if store.set_enabled(name, on) is None:
            raise HTTPException(404, "That strategy is not on the Desk.")
        return {"ok": True, "name": name, "enabled": on}

    @r.post("/desklab/{what}")
    async def desklab_write(what: str, request: Request):
        """promote {name, run_id, to?}: a draft that was backtested goes on the Desk, frozen. remove {name}: its record goes
        (the history stays). onoff {name, on}: the runner hosts it or leaves it be. A refusal the page may read is answered
        with its own words ({ok: false, detail})."""
        watch_guard(request)
        try:
            write_ok(request)
            json_body(request)
            if what not in DESKLAB_ACTIONS:
                raise HTTPException(404, f"unknown desklab action {what!r}")
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(400, "the body is JSON") from None
            keys = {"promote": {"name", "run_id"}, "remove": {"name"}, "delete": {"name"}, "onoff": {"name", "on"},
                    "open": {"name"},
                    "archive": {"name"}, "filed": {"name"}, "restore": {"name"},
                    "archive_builtin": {"name"}, "restore_builtin": {"name"}}[what]
            run = body.get("run") if what == "open" and isinstance(body, dict) else None
            if run is not None and (not isinstance(run, str) or not re.fullmatch(r"[0-9a-z_-]{1,120}", run)):
                raise HTTPException(400, "run: a finished run's id")
            wf = body.get("wf") if what == "open" and isinstance(body, dict) else None
            if wf is not None and (not isinstance(wf, str) or not re.fullmatch(r"[0-9a-z_-]{1,160}", wf)):
                raise HTTPException(400, "wf: a walk-forward's id")
            builtin = body.get("builtin") if what == "open" and isinstance(body, dict) else None
            if builtin is not None and builtin is not True:
                raise HTTPException(400, "builtin: true")
            if what == "open" and run is not None:
                keys = {"name", "run"}
            if what == "open" and builtin is not None:
                keys = keys | {"builtin"}
            if what == "open" and wf is not None:
                keys = keys | {"wf"}
            if what == "promote" and isinstance(body, dict) and "owner_said" in body:
                keys = keys | {"owner_said"}      # an older page still sends its words: no longer asked for, ignored (the owner, 2026-10-28)
            to = body.get("to") if what == "promote" and isinstance(body, dict) else None
            if to is not None and to not in DESKLAB_TO:
                raise HTTPException(400, "to: mac, vps or both")
            if to is not None:
                keys = keys | {"to"}
            draft = body.get("draft") if what == "delete" and isinstance(body, dict) else None
            if draft is not None and draft is not True:
                raise HTTPException(400, "draft: true")
            if draft is not None:
                keys = keys | {"draft"}
            if not isinstance(body, dict) or set(body) != keys or not isinstance(body["name"], str) \
                    or not draftstore.NAME_RE.fullmatch(body["name"]):
                raise HTTPException(400, "{" + ", ".join(sorted(keys)) + "}: a Lab strategy's name" + (
                    ", the backtest's run id" if what == "promote" else ", on: true or false" if what == "onoff" else ""))
            name = body["name"]
            if what == "promote" and not isinstance(body["run_id"], str):
                raise HTTPException(400, "run_id: the backtest's run id")
            if what == "onoff" and not isinstance(body["on"], bool):
                raise HTTPException(400, "on: true or false")
            try:
                if what == "promote":
                    done = await asyncio.to_thread(desklab_promote, name, body["run_id"])
                    if to in ("vps", "both"):
                        done["vps"] = await asyncio.to_thread(send_to_vps, name)
                elif what == "remove":
                    done = await asyncio.to_thread(desklab_remove, name)
                elif what == "delete":
                    done = await asyncio.to_thread(desklab_delete, name, draft is True)
                elif what == "open":
                    done = await asyncio.to_thread(desklab_open, name, run, builtin is True, wf)
                elif what in ("archive", "filed", "restore", "archive_builtin", "restore_builtin"):
                    done = await asyncio.to_thread({"archive": desklab_archive, "filed": desklab_filed, "restore": desklab_restore,
                                                    "archive_builtin": desklab_archive_builtin,
                                                    "restore_builtin": desklab_restore_builtin}[what], name)
                else:
                    done = await asyncio.to_thread(desklab_onoff, name, body["on"])
            except ValueError as e:                  # a name the store will not take (the heartbeat's own file name)
                raise HTTPException(400, str(e)) from None
            return watch_answer(request, done)
        except HTTPException as e:
            return watch_answer(request, {"ok": False, "detail": e.detail}, e.status_code)

    # ---- Desk groups (deskgroups.py): named sets of Desk strategies, kept beside the Lab records. A group trades only through
    # ---- its account cycle, kept by the Desk's engine and made to follow here, server side, before a change is written.
    def desk_post(path_: str, payload: dict) -> tuple:
        """POST JSON to this host's Desk -> (HTTP status, detail); (None, why) when it does not answer."""
        req = urllib.request.Request(f"{DESK_URL}{path_}", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as r:
                return r.status, None
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}").get("detail")
            except ValueError:
                return e.code, None
        except (OSError, ValueError) as e:
            return None, type(e).__name__

    async def cycle_follow(what: str, body: dict) -> str | None:
        """Before a delete, a rename or a move is written: the Desk's account cycle of each group it changes follows it
        (delete: the cycle goes; move / rename: its strategies and name). None when in step or there is no cycle to follow;
        else the sentence that refuses the change -- nothing is written then, so the two never fall out of step."""
        if what not in ("delete", "move", "rename"):
            return None
        before = {g["id"]: g for g in deskgroups.load()}
        after = await asyncio.to_thread(deskgroups.preview, what, body)
        calls = [("/api/groups/delete", {"id": body.get("id")})] if what == "delete" else [
            ("/api/groups/follow", {"id": g["id"], "name": g["name"], "members": g["members"]})
            for g in after if g["id"] in before and (before[g["id"]]["members"], before[g["id"]]["name"]) != (g["members"], g["name"])]
        for path_, payload in calls:
            code, detail = await asyncio.to_thread(desk_post, path_, payload)
            if code not in (200, 404):                      # 404: that group has no cycle
                return (f"The Desk refused the account cycle's change: {detail}" if code else
                        "The Desk did not answer, so the group's account cycle could not follow. Nothing changed: try again.")
        return None

    @r.get("/deskgroups")
    def deskgroups_list(request: Request):
        watch_guard(request)
        return watch_answer(request, {"groups": deskgroups.load()})

    @r.options("/deskgroups/{what}")
    def deskgroups_preflight(what: str, request: Request):
        o = request.headers.get("origin")
        if what not in DESKGROUP_ACTIONS or o not in DESK_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return Response(status_code=204, headers={
            "access-control-allow-origin": o, "vary": "Origin", "access-control-allow-methods": "POST",
            "access-control-allow-headers": "content-type", "access-control-max-age": "600"})

    @r.post("/deskgroups/{what}")
    async def deskgroups_write(what: str, request: Request):
        """create {name, kind?} | rename {id, name} | kind {id, kind} | delete {id} | move {strategy, group: id | null}
        -> {ok: true, groups} | {ok: false, detail} (a refusal in words)."""
        watch_guard(request)
        try:
            write_ok(request)
            json_body(request)
            if what not in DESKGROUP_ACTIONS:
                raise HTTPException(404, f"unknown group action {what!r}")
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(400, "the body is JSON") from None
            if not isinstance(body, dict):
                raise HTTPException(400, "the body is a JSON object")
            try:
                why = await cycle_follow(what, body)
                if why is not None:
                    raise HTTPException(409, why)
                groups = await asyncio.to_thread(deskgroups.apply, what, body)
            except deskgroups.GroupError as e:
                raise HTTPException(409, str(e)) from None
            return watch_answer(request, {"ok": True, "groups": groups})
        except HTTPException as e:
            return watch_answer(request, {"ok": False, "detail": e.detail}, e.status_code)

    # ---- Desk families (deskfamilies.py): variants of one idea folded under one sidebar row. Display only: nothing trades.
    @r.get("/deskfamilies")
    def deskfamilies_list(request: Request):
        watch_guard(request)
        return watch_answer(request, {"families": deskfamilies.load()})

    @r.options("/deskfamilies/{what}")
    def deskfamilies_preflight(what: str, request: Request):
        o = request.headers.get("origin")
        if what not in deskfamilies.ACTIONS or o not in DESK_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return Response(status_code=204, headers={
            "access-control-allow-origin": o, "vary": "Origin", "access-control-allow-methods": "POST",
            "access-control-allow-headers": "content-type", "access-control-max-age": "600"})

    @r.post("/deskfamilies/{what}")
    async def deskfamilies_write(what: str, request: Request):
        """create {name} | rename {id, name} | delete {id} | move {strategy, family: id | null, short?} | short {strategy, short}
        -> {ok: true, families} | {ok: false, detail} (a refusal in words)."""
        watch_guard(request)
        try:
            write_ok(request)
            json_body(request)
            if what not in deskfamilies.ACTIONS:
                raise HTTPException(404, f"unknown family action {what!r}")
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(400, "the body is JSON") from None
            if not isinstance(body, dict):
                raise HTTPException(400, "the body is a JSON object")
            try:
                fams = await asyncio.to_thread(deskfamilies.apply, what, body)
                return watch_answer(request, {"ok": True, "families": fams})
            except deskgroups.GroupError as e:
                raise HTTPException(409, str(e)) from None
        except HTTPException as e:
            return watch_answer(request, {"ok": False, "detail": e.detail}, e.status_code)

    def group_prop(key, ledger):
        if not ledger:
            return None
        try:
            got = _rescore(("group", key), lambda: {"run": {}, "trades": ledger, "propsim": None}, DESKLAB_PROP)
            return deskresults.prop_headline(got)
        except (HTTPException, KeyError, ValueError, OSError):
            return None

    def group_sides(g: dict, state_of) -> tuple:
        """A group's (members, left_out, sides): each member's own numbers, those left out and why, and per side the (sid, wf
        id, trades) of the members whose 3:1 walk-forward is done. state_of: ensure_wf on an ask, read_wf in the warm-up."""
        heads = ("net", "trades", "win_rate", "profit_factor", "max_drawdown")
        members, left_out, sides = [], [], {"build": [], "unseen": [], "both": []}
        for sid in g["members"]:
            try:
                rec = store.get(sid[4:]) if sid.startswith("lab_") else None
            except ValueError:
                rec = None
            if not isinstance(rec, dict):
                left_out.append({"strategy": sid, "why": "not on the Desk any more" if sid.startswith("lab_")
                                 else "built in: it has no 3:1 walk-forward to add"})
                continue
            got, res = state_of(rec), None
            if got["state"] == "done":
                try:
                    res = wfs.result(got["id"])
                except (ValueError, KeyError, OSError):
                    res = None
            ins = ((res or {}).get("stitched_is") or {}).get("trades") or []
            oos = ((res or {}).get("stitched") or {}).get("trades") or []
            members.append({"strategy": sid, "label": rec.get("label") or rec.get("name"),
                            "state": "done" if res else ("failed" if got["state"] == "done" else got["state"]),
                            "build": {k: v for k, v in deskresults.wf_summary(got["id"], res, "stitched_is").items() if k in heads}
                            if res else None,
                            "unseen": {k: v for k, v in deskresults.wf_summary(got["id"], res).items() if k in heads} if res else None})
            if res and got.get("through"):      # an older 3:1 (S4): the group page names the months this member lacks
                members[-1].update(through=got["through"], to=got["to"])
            if res is None:
                left_out.append({"strategy": sid, "why": "no 3:1 walk-forward"})
                continue
            sides["build"].append((sid, got["id"], ins))
            sides["unseen"].append((sid, got["id"], oos))
            sides["both"].append((sid, got["id"], ins + oos))
        return members, left_out, sides

    def side_ledger(side: str, chosen: list) -> tuple:
        """(ledger, owners, prop-sim key) of one side of a group: its members' trades as one account's."""
        ledger, owners = deskgroups.merged([(sid, trades) for sid, _, trades in chosen])
        return ledger, owners, (side,) + tuple(sorted(w for _, w, _ in chosen))

    @r.get("/deskgroups/results")
    def deskgroups_results(request: Request):
        """For each group: its members' own 3:1 walk-forward numbers and, for their trades put together as one account's, the
        same on the in-sample months (build), the out-of-sample months (unseen) and all of them together (both): net, win
        rate, PF, drawdown, days, the curve, the prop sim on DESKLAB_PROP (owner 2026-10-25: the group's curve is the 3:1, three
        lines -- as each strategy's card). A member that is not a Lab strategy, or whose 3:1 walk-forward is not done, is left
        out and named. Reads saved walk-forwards only: nothing starts one while DESKLAB_AUTO_UNSEEN is off (S4), and a member
        with none to the last whole month counts its newest done 3:1 of the same copy (code, settings, size)."""
        watch_guard(request)
        out = {}
        with desk_res_lock:
            for g in deskgroups.load():
                members, left_out, sides = group_sides(g, ensure_wf)
                res_g = {"id": g["id"], "name": g["name"], "kind": g["kind"], "members": members, "left_out": left_out,
                         "walkforward": True}
                for key, chosen in sides.items():
                    ledger, owners, prop_key = side_ledger(key, chosen)
                    res_g[key] = deskgroups.summarize(ledger, owners)
                    res_g.setdefault("prop", {})[key] = group_prop(prop_key, ledger)
                    res_g.setdefault("in", {})[key] = [sid for sid, _, _ in chosen]
                out[g["id"]] = res_g
        return watch_answer(request, {"results": out})

    return warm_desklab_results
