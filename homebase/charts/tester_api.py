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
    GET  /api/tester/drafts/form         the strategy form's schema (homebase.charts.lab_forms.schema): markets, rules,
                                          fields with their words, and a complete default answer set per rule
    POST /api/tester/drafts/form/build   {answers, replace?} -> {ok, code, name, sentence} | {ok: false, errors: {field:
                                          sentence}} (status 200: a refusal is an answer; a name already on file or a
                                          built-in's is refused unless replace). Builds TEXT only: nothing is written or run
    POST /api/tester/drafts/form/read    {code} -> {answers: {...} | null, intact} (null: not a file the form made;
                                          intact: the code under the header was not edited by hand)
    PUT  /api/tester/drafts/{name}       {code} -> save <name>.py (draftstore.write: name, size and syntax checked)
    DELETE /api/tester/drafts/{name}     remove it: the file moves to <drafts dir>/.trash (never unlinked); 409 while the
                                          Desk holds a promoted copy of it (ON_THE_DESK); 500 when the filesystem
                                          refuses the move (NOT_TRASHED: the file stays where it was)
    POST /api/tester/drafts/{name}/review-request   {run_id?, note?} -> writes a review package (text only) under
                                          ~/.homebase/review-requests; never runs, imports or promotes anything
    GET  /api/tester/groups              the Lab's strategy groups {groups: [names, in order], members: {strategy
                                          id: its group}} -- one file beside the drafts (draftstore, groups.json).
                                          Each write below answers the same shape, and none of them ever edits,
                                          moves or deletes a strategy file
    POST /api/tester/groups              {name} -> a new, empty group
    POST /api/tester/groups/rename       {name, to}
    POST /api/tester/groups/delete       {name} -> its strategies go back to no group (none is deleted)
    POST /api/tester/groups/move         {strategy, group} -> that strategy (a built-in or a draft id) is in that
                                          one group, made when it is new; group null or "" = in no group
    GET  /api/tester/arsenal             every tool we have (blocks, chat tools, skills, scripts), each with its code: {groups, sources, counts} (homebase/arsenal.py)
    GET  /api/tester/blueprint           the blueprint toolkit as the Lab lists it: {tools: [{name, phase, description,
                                          inputs: its JSON schema}], ideas: [each idea's idea.json]} -- THE SAME tool
                                          definitions every chat has (claude_mcp.blueprint_tools.SPECS)
    POST /api/tester/blueprint/run       {tool, args} -> {ok, text}: that tool run as a chat runs it (the research
                                          toolkit bp.py as a child process; it saves in the app itself)
    GET  /api/tester/pipeline            the strategy pipeline as the Lab shows it (its Queue, Book and Guide):
                                          {runner: {running, paused}, counts: {label: n}, ideas: [the toolkit's state
                                          rows, each with the page's `label`], book: [the book cards], stages: [{n,
                                          name, words}]} -- two commands of the research toolkit (bp.py pipe list,
                                          pipe book), kept for PIPE_CACHE_S; the labels and the stages' words are
                                          claude_mcp.pipeline_tools' own, typed nowhere else. And what the add-idea
                                          form is built from, off ONE `bp.py blocks` for the life of the service:
                                          rules: [{name, words, markets, sessions, bars, settings: [{name, kind: number
                                          | whole | choice | bool | text, min, max, choices, default, tried}]}],
                                          indicators: [{block, sides: [{side, words}], markets}], sessions: [{name, words}]
    GET  /api/tester/pipeline/idea/{name}   one idea: {card, state, stages: [{n, name, passed, result, lines: [{line,
                                          passed, text}], text}]} (bp.py pipe show); 404 for a name not on file.
                                          Every text is plain: the toolkit's own command line is taken out
    POST /api/tester/pipeline/run        {action: add, card, inbox?} | {action: start | pause | resume} |
                                          {action: approve, name} | {action: refuse, name, why} -> {ok, text}: the
                                          checks and the ONE command of the pipeline tool every chat has; `text` is one
                                          plain sentence for the page (pipeline_tools.page_said), and for a refusal of
                                          the toolkit ok false with its own reason, without its command line. add /
                                          start / resume are refused in a quiet window of the tester (they can start heavy
                                          work); pause and the owner's yes or no never are
    GET  /api/tester/desklab             Lab strategies promoted to the Desk (homebase.labrun.store): {strategies: [each
                                          record WITHOUT its code, plus `today` (the day summary of the session day the
                                          runner is on, or null) and `days` (of the last 10, those this promotion wrote,
                                          each cut to {date, state, why, net, match, rebuilt})],
                                          runner: {alive, seen_utc, prices}} -- alive = the runner's heartbeat is under
                                          20 s old
    GET  /api/tester/desklab/results     {results: {name: {unseen, prop: {build, unseen}}}}: for each promoted strategy, its
                                          saved run on the unseen days (the newest finished run of the same code, settings
                                          and size; cut as the record's `run`, or null when none is saved) and the prop
                                          sim's headline of its build run and of that run, scored on DESKLAB_PROP (LucidPro 50K no-DLL)
                                          from the runs' saved trades ({account, eval_pass_p, bust_p, median_days_to_pass,
                                          funded_payout_p, funded_expected_cheque} | null). Reads saved runs only: nothing
                                          is run by this route. `curve` = {days, vals}: that run's running total by day,
                                          after costs. A strategy with no unseen-days run of its code + settings
                                          gets one started by itself, once (its `unseen_state`: done | pending | failed |
                                          none; a failed or cancelled one is not started again). A promote starts it too.
                                          The Desk's own straddles (nq930, gc_nfp) answer under their Desk id with `twin` (the
                                          tester strategy that mirrors them) and `manual: true`: their saved runs at the Desk's
                                          size and setting; nothing starts one (it is read by hand, from the Lab)
    POST /api/tester/desklab/open        {name[, run][, builtin: true]} -> {ok, name}: the Desk page's "Open in the Lab" leaves its ask
                                          (the Mac app drops a link's #fragment when it switches tab); `builtin`: name is a
                                          built-in tester strategy (a Desk straddle's twin). GET /api/tester/lab-open ->
                                          {name[, run][, builtin]} hands it to the Lab page once (null when none, or one older
                                          than two minutes)
    GET  /api/tester/desklab/shadow?name= {name, days: [{date, state, why, net, match, trades}]}: the shadow calendar, every day
                                          this promotion wrote (oldest first, at most DESKLAB_SHADOW_DAYS); a booked day
                                          shows its shadow copy (store.get_shadow_day) or is left out; 404 off the Desk
    POST /api/tester/desklab/promote     {name, run_id} -> {ok, name, notes} | {ok: false, detail}: a frozen copy of the
                                          draft's text, its settings and that backtest's headline numbers. Refused (in
                                          words) for a draft not in the Lab, a run that is not a finished run of it, code
                                          that changed since, code that cannot be read, one that is not
                                          session_independent, a market this service does not stream, a sandbox that does
                                          not work. No draft runs here and no order goes anywhere; it does queue the copy's
                                          unseen-days backtest (once per code + settings, a tester run like the Lab's Run)
    POST /api/tester/desklab/remove      {name} -> {ok, removed, name}: the record goes, its days and journal stay
    POST /api/tester/desklab/delete      {name} -> {ok, deleted, name}: once removed, its history goes too (409 while on the
                                          Desk or while the runner still hosts it); {name, draft: true} (the Archive's Delete) also
                                          moves its Lab draft to the drafts' trash and off its Lab group
                                          (promote and remove answer 409 "Take its accounts off on the Desk first."
                                          while the desk's sidecar, <name>.desk.json, holds book rows)
    POST /api/tester/desklab/onoff       {name, on} -> {ok, name, enabled}; 404 for a name not on the Desk
                                          (the desklab routes answer the desk page's exact origins)
    POST /api/tester/desklab/archive     {name} -> {ok, name}: Archive, step 1 -- a switched-off copy is kept (store.ARCHIVE_DIR);
                                          step 2 is the Desk's own Remove; step 3, filed {name}, files its Lab draft under the
                                          "Archive" group (409 while it is still on the Desk). GET /desklab lists them as `archived`
    POST /api/tester/desklab/restore     {name} -> {ok, name}: back on the Desk, switched off, no account; its Lab group as before
    POST /api/tester/desklab/archive_builtin | restore_builtin {name}: one of the Desk's own strategies (nq930, gc_nfp), switched
                                          off by the page first, noted as archived (the page hides it) / shown again; its tester
                                          twin goes to / leaves the Lab's "Archive" group. Listed in `archived` with builtin: true
    POST /api/tester/show                {run_id | grid_id + cell, focus?: {trade_index | date | time_ms}}
                                          -> tells every open chart page (/ws `tester_show`) to load that run or
                                          heat-map cell into the Strategy Tester and show it on a chart
                                          (JSON only; refused in a quiet window of the tester; the page picks the
                                          chart -- testerlayer.showPlan)
    GET  /api/tester/prop-rules          prop-eval rule sets [{id, name, version, confirmed}]
    POST /api/tester/run                 {strategy, inputs, range, qty, commission,
                                          slippage_ticks, capital?, prop_rules?} -> {id}
                                          (any window: nothing is refused for the dates it reads;
                                          a range reaching the test days, 2025-07-01 on, is recorded
                                          in spends.jsonl)
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
    POST /api/tester/run-match           a Run body -> {id}: the newest finished run it would only repeat (the same
                                          request, its code included), or null -- the Lab's result on opening
    POST /api/tester/grid                {strategy, inputs, axes: [{key, values}] x2-3, qty, commission,
                                          slippage_ticks, capital?, prop_rules?} -> {id}
                                          (<= 60 cells, over the body's own range -- the build days,
                                          2021-09-22 -> 2025-06-30, when it names none)
    GET  /api/tester/grid/{id}           the grid, per-cell status + summary, and its strategy's looks
    POST /api/tester/grid/{id}/cancel
    GET  /api/tester/grid/{id}/cell/{i}/bundle   a cell's full run bundle (the same shape as a run's)
    GET  /api/tester/grids               recent grids, newest first
    GET  /api/tester/looks               {strategy: heat-map cells ever run}
    POST /api/tester/walkforward         the grid body + {scheme?, step_months?} -> {id}: scheme "fixed" (the default)
                                          = every cell as set (the hm40 cells when no axes) on the 3:1 in-sample months,
                                          nothing picked by code; scheme "pick" (or a body with test_months / compare /
                                          metric / min_trades) = the old one: + {metric?, min_trades?, test_months? | compare?}:
                                          1 month to select, the next N to test, stepping monthly, over the
                                          body's own range; `compare: true` = ONE job (one grid run) selected
                                          and stitched at 1:1, 1:2 and 1:3 (homebase.backtest.walkforward)
    GET  /api/tester/walkforward/{id}    status, per-cell status (never full-window P&L), progress, eta_s
    GET  /api/tester/walkforward/{id}/result   the steps, the stitched OOS equity + stats (409 until done);
                                          ?test_months=N picks a compare job's 1:N scheme (a compare job
                                          without it is a 409)
    GET  /api/tester/walkforward/{id}/compare  a compare job's three stitched OOS results side by side
    POST /api/tester/walkforward/{id}/cancel
    POST /api/tester/walkforward/{id}/pick   {cell} -> a fixed job's lock (the owner's pick, written once)
    POST /api/tester/walkforward/{id}/oos    {cell, owner_said} -> the picked cell's test months, on the owner's words
                                          (verbatim, non-empty), once; the result route then carries "oos"
    GET  /api/tester/walkforwards        recent walk-forwards, newest first
    POST /api/tester/walkforward-match   the same for a walk-forward body: the newest finished job it would only repeat
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
import contextlib
import datetime as dt
import hashlib
import inspect
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..store import arsenal, draftstore, ideastore
from .. import netguard, strategies
from ..backtest import drafthost
from ..backtest import propsim, sandbox, slots
from ..backtest.grid import GridManager, LooksCorrupt
from ..backtest.runner import RunManager, _run_propsim, default_base, read_json
from ..backtest.stats import montecarlo
from ..backtest import walkforward
from ..backtest.walkforward import WalkForwardManager
from ..backtest.slots import Slots
from ..backtest.tape import CACHE, TapeStore
from ..claude_mcp import blueprint_tools, pipeline_tools
from ..claude_mcp.client import ToolError
from ..labrun import door, store
from .desk import DESK_URL
from . import groupmix
from ..labrun.host import session_today
from . import DEFAULT_ROOTS, deskgroups, deskresults, lab_forms, lab_templates, reviewpack
from .paperbook import DESK_ORIGINS, _cors, desk_origin_refusal
# make_router's routes live in tester_routes/ (moved verbatim, 2026-10-26). Every name this module had is still here: the
# tests patch desk_strategy_ids, DESKLAB_AUTO_UNSEEN and _run_propsim on THIS module, so the route modules read them
# through ctx.api at call time; the rest are re-exported.
from .tester_routes import common, desklab, jobs, lab
from .tester_routes.common import PROP_CACHE    # noqa: F401
from .tester_routes.desklab import (ARCHIVE_GROUP, DESKGROUP_ACTIONS, DESKLAB_ACTIONS, DESKLAB_ALIVE_S,  # noqa: F401
                                    DESKLAB_DAY_KEYS, DESKLAB_DAYS, DESKLAB_PROP, DESKLAB_SHADOW_DAYS, DESKLAB_TAKE_OFF)
from .tester_routes.jobs import MC_CACHE    # noqa: F401
from .tester_routes.lab import NOT_TRASHED, ON_THE_DESK, _STRATEGIES_DIR, builtin_source    # noqa: F401

PIPE_CACHE_S = 2.0       # the pipeline's Queue / Book answer is kept this long: a page asks every 5 s, and several may be open
pipe_clock = time.monotonic      # ... by this clock (a test moves it)
CURVE_CACHE_S = 30.0     # an idea's equity curve is kept this long
def desk_strategy_ids() -> list[str]:
    """The built-in strategies the Desk itself runs (its status' strategies that are not Lab ones), by id. [] when it does not
    answer: the Lab page then simply shows no built-in as being on the Desk."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{DESK_URL}/api/status", timeout=1.5) as r:
            got = json.loads(r.read())
    except (OSError, ValueError):
        return []
    strategies = got.get("strategies") if isinstance(got, dict) else None
    if not isinstance(strategies, dict):
        return []
    return sorted(k for k, v in strategies.items()
                  if isinstance(k, str) and isinstance(v, dict) and (v.get("cfg") or {}).get("kind") != "lab")


DESKLAB_AUTO_UNSEEN = True   # a promoted strategy's unseen-days run starts by itself, once per code + settings (owner 2026-10-11)
PIPE_KEYS = {"add": ("card", "inbox"), "start": (), "pause": (), "resume": (), "approve": ("name",), "refuse": ("name", "why")}
PIPE_QUIET = ("add", "start", "resume")      # what can start heavy work: not in a quiet window of the tester
PIPE_SHAPE = ("{action: add, card: {...}, inbox?: true | false} | {action: start | pause | resume} | "
              "{action: approve, name} | {action: refuse, name, why}")


class _Blueprint(pipeline_tools.PipelineMixin, blueprint_tools.BlueprintMixin):
    """The blueprint tools as the connector has them (one per phase, each a command of the research toolkit), and the
    pipeline's, for the Lab's own panels: the same code path, so the page and a chat can never disagree about a tool."""


_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)


def host_ok(request: Request) -> None:
    """DNS-rebinding defence: refuse any request whose Host header does not
    literally name this loopback service (127.0.0.1 or localhost, optional
    port) — regardless of Origin, which a rebinding attacker can keep
    agreeing with Host throughout the attack. Applied to every route on this
    router (see make_router), GET and POST alike."""
    if not _HOST_RE.match((request.headers.get("host") or "").strip()):
        raise HTTPException(403, "unexpected Host header")


FOCUS_KEYS = ("trade_index", "date", "time_ms")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
                notify: Callable[[dict], int] | None = None, live_roots=DEFAULT_ROOTS) -> APIRouter:
    r = APIRouter(prefix="/api/tester", dependencies=[Depends(host_ok)])
    ctx = common.make_ctx(sys.modules[__name__], write_ok, manager, grids, wfs, notify, live_roots)
    known, known_grid, json_body = ctx.known, ctx.known_grid, ctx.json_body
    lab.register(r, ctx)                      # /strategies ... /groupmix

    # ---- the blueprint toolkit in the Lab: the tools every chat has, listed and run from the page ------------
    box = _Blueprint()
    bp_specs = {s["name"]: s for s in blueprint_tools.SPECS}

    @r.get("/blueprint")
    def blueprint_toolkit():
        tools = []
        for s in blueprint_tools.SPECS:
            head, _, text = s["description"].partition(": ")
            tools.append({"name": s["name"], "phase": head, "description": text or head, "inputs": s["inputSchema"]})
        return {"tools": tools, "ideas": ideastore.list_ideas()}

    code_cache: dict = {"stamp": None, "body": None}
    code_lock = threading.Lock()

    @r.get("/arsenal")
    def arsenal_catalog():
        """Every tool we have, with its code: {groups, sources, counts, built, notes} (homebase/arsenal.py). Saved in the app
        (~/.homebase/arsenal.json) and built again only when a file it is made from changes."""
        with code_lock:
            rs = arsenal.research_stamp()
            now = arsenal.stamp(rs)
            if code_cache["body"] is None or code_cache["stamp"] != now:
                try:
                    code_cache.update(body=arsenal.get(arsenal.research, rs), stamp=now)
                except Exception as e:      # noqa: BLE001 -- the page says why, whatever broke
                    raise HTTPException(503, str(e)) from None
            return code_cache["body"]

    @r.post("/blueprint/run")
    def blueprint_run(request: Request, body: dict):
        write_ok(request)
        json_body(request)
        tool, args = body.get("tool"), body.get("args", {})
        if set(body) - {"tool", "args"} or not isinstance(tool, str) or tool not in bp_specs or not isinstance(args, dict):
            raise HTTPException(400, "{tool: one of " + ", ".join(bp_specs) + ", args: {...}}")
        if Slots().quiet():       # a quiet window of the tester: nothing is started from the page then
            raise HTTPException(409, "paused for a quiet window of the tester (tester_slots.json): run it later")
        fn = getattr(box, f"t_{tool}")
        try:
            inspect.signature(fn).bind(**args)
        except TypeError as e:
            raise HTTPException(400, f"{tool}: {e}") from None
        try:
            return {"ok": True, "tool": tool, "text": fn(**args)}
        except ToolError as e:    # a refusal of the toolkit (or a bad input): the tool's own words, nothing was changed
            return {"ok": False, "tool": tool, "text": str(e)}

    # ---- the strategy pipeline in the Lab: its Queue, its Book and its Guide (claude_mcp.pipeline_tools) -----------
    pipe_cache: dict = {"at": None, "body": None, "error": None}
    pipe_lock = threading.Lock()

    def pipe_parts() -> dict:
        """What the add-idea form is built from (the entry rules with their settings, the indicators, the sessions): ONE
        `bp.py blocks` for the life of this service (pipeline_tools.PipelineMixin.pipeline_parts). A toolkit that cannot
        list them leaves the lists empty -- the form then takes text -- and never takes the Queue down with it."""
        try:
            return box.pipeline_parts()
        except ToolError:
            return pipeline_tools.parts(None)

    @r.get("/pipeline")
    def pipeline_state():
        """Where the pipeline stands, in one answer. Two commands of the toolkit at most, and the answer is kept for
        PIPE_CACHE_S: pages that ask together wait for the one who asked first and read what it got. A toolkit that
        is not installed (or does not answer a look in time) is a 503 with its own words -- kept as long, so that
        the pages behind a slow toolkit never each start it again and use this service's threads up."""
        with pipe_lock:
            if pipe_cache["at"] is None or pipe_clock() - pipe_cache["at"] >= PIPE_CACHE_S:
                try:
                    got = {"body": {**box.pipeline_state(), **pipe_parts()}, "error": None}
                except ToolError as e:
                    got = {"body": None, "error": str(e)}
                pipe_cache.update(got, at=pipe_clock())
            if pipe_cache["error"] is not None:
                raise HTTPException(503, pipe_cache["error"])
            return pipe_cache["body"]

    @r.post("/pipeline/mode")
    def pipeline_mode(request: Request, body: dict):
        """The switch: {mode: "off" | "live"} -- the pipeline works, or it does not (one pipeline since 2026-10-18)."""
        write_ok(request)
        json_body(request)
        if body.get("mode") != "off" and Slots().quiet():     # switching one ON starts heavy work: not in a quiet window of the tester (as PIPE_QUIET)
            raise HTTPException(409, "paused for a quiet window of the tester (tester_slots.json): do it later")
        try:
            return {"ok": True, "text": box.pipeline_set_mode(body.get("mode"))}
        except blueprint_tools.Refused as e:
            return {"ok": False, "text": pipeline_tools.page_refusal(e)}
        except ToolError as e:
            return {"ok": False, "text": str(e)}
        finally:
            with pipe_lock:
                pipe_cache["at"] = None

    @r.get("/pipeline/idea/{name}")
    def pipeline_idea(name: str):
        if not pipeline_tools.NAME_RE.fullmatch(name):
            raise HTTPException(404, f"no idea {name!r}")
        try:
            return box.pipeline_idea(name)
        except blueprint_tools.Refused as e:      # the toolkit has no such idea on file
            raise HTTPException(404, str(e)) from None
        except ToolError as e:
            raise HTTPException(503, str(e)) from None

    @r.post("/pipeline/run")
    def pipeline_run(request: Request, body: dict):
        write_ok(request)
        json_body(request)
        action = body.get("action")
        keys = PIPE_KEYS.get(action) if isinstance(action, str) else None
        card, inbox, name, why = (body.get(k) for k in ("card", "inbox", "name", "why"))
        if (keys is None or set(body) - {"action", *keys}
                or (action == "add" and not (isinstance(card, dict) and isinstance(body.get("inbox", False), bool)))
                or ("name" in keys and not isinstance(name, str))
                or ("why" in keys and not (isinstance(why, str) and why.strip()))):
            raise HTTPException(400, PIPE_SHAPE)
        if action in PIPE_QUIET and Slots().quiet():     # a quiet window of the tester: nothing is started from the page then
            raise HTTPException(409, "paused for a quiet window of the tester (tester_slots.json): do it later")
        try:                      # the checks and the ONE command of the tool a chat has, answered in one plain sentence
            return {"ok": True, "text": box.pipeline_do(action, card=card, inbox=bool(inbox), name=name, why=why)}
        except blueprint_tools.Refused as e:     # the toolkit said no: its own reason, without its command line; nothing was changed
            return {"ok": False, "text": pipeline_tools.page_refusal(e)}
        except ToolError as e:    # a bad input, or a toolkit that is not there: said as it is
            return {"ok": False, "text": str(e)}
        finally:
            with pipe_lock:       # whatever it did, the next look is a new one
                pipe_cache["at"] = None

    # ---- what an idea did, as a person looks at it: its equity curve and its executions on the chart (2026-10-09) ----
    curve_cache: OrderedDict = OrderedDict()

    def curve_of(name: str) -> dict:
        """`pipe curve`, kept CURVE_CACHE_S per idea: the curve changes only when a stage writes a new store."""
        if not pipeline_tools.NAME_RE.fullmatch(name):
            raise HTTPException(404, f"no idea {name!r}")
        hit = curve_cache.get(name)
        if hit is not None and pipe_clock() - hit[0] < CURVE_CACHE_S:
            return hit[1]
        try:
            body = box.pipeline_curve(name)
        except blueprint_tools.Refused as e:      # no pick yet, or no stored trades: said as it is
            raise HTTPException(409, pipeline_tools.page_refusal(e)) from None
        except ToolError as e:
            raise HTTPException(503, str(e)) from None
        curve_cache[name] = (pipe_clock(), body)
        while len(curve_cache) > 64:
            curve_cache.popitem(last=False)
        return body

    @r.get("/pipeline/curve/{name}")
    def pipeline_curve(name: str):
        return curve_of(name)

    async def executions_shown(name: str) -> dict:
        """The idea's picked box as a tester run (written once), then every open chart page is asked to show it at its
        last traded day. Answers {run_id, trades, of, start, end, pages}."""
        if not pipeline_tools.NAME_RE.fullmatch(name):
            raise HTTPException(404, f"no idea {name!r}")
        if Slots().quiet():       # a quiet window of the tester: never move a chart or decode history then
            raise HTTPException(409, "paused for a quiet window of the tester (tester_slots.json): show it later")
        try:
            got = await asyncio.to_thread(box.pipeline_executions, name)
        except blueprint_tools.Refused as e:
            raise HTTPException(409, pipeline_tools.page_refusal(e)) from None
        except ToolError as e:
            raise HTTPException(503, str(e)) from None
        msg = {"type": "tester_show", "run_id": got["run_id"]}
        if got.get("end"):
            msg["focus"] = {"date": got["end"]}
        pages = notify(msg) if notify is not None else 0
        return {"ok": True, "pages": pages, **got}

    @r.post("/pipeline/executions")
    async def pipeline_executions(request: Request):
        write_ok(request)
        json_body(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is JSON") from None
        if not isinstance(body, dict) or set(body) != {"name"} or not isinstance(body["name"], str):
            raise HTTPException(400, "{name}")
        return await executions_shown(body["name"])

    warm_desklab_results = desklab.register(r, ctx)      # /desklab ... /deskgroups/results

    # /show stays here: test_tester_pipeline reads the /pipeline/run route out of this file, up to this one
    @r.post("/show")
    async def show(request: Request):
        """Ask every open chart page to load a finished run (or heat-map cell) into the Strategy Tester
        and show it on a chart. JSON only, behind the same Host + Origin guards as every write here;
        async (the page fan-out lives on the event loop) with the one small disk read in a thread.
        Answers how many pages were told -- 0 means no chart page is open."""
        write_ok(request)
        if not netguard.is_json(request.headers.get("content-type")):
            raise HTTPException(415, "send JSON (Content-Type: application/json)")
        if Slots().quiet():       # a quiet window of the tester: never move a chart or decode history then
            raise HTTPException(409, "paused for a quiet window of the tester (tester_slots.json): show it later")
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

    jobs.register(r, ctx)                     # /prop-rules ... /propsim

    r.manager = manager   # so the chart service can stop an in-flight child on shutdown
    r.grids = grids       # likewise every grid cell's child
    r.wfs = wfs           # ... and every walk-forward cell's
    def warm() -> None:
        """The Lab's strategy list (a cold read of ~500 drafts is ~5 s; each is kept until its file changes), then the Desk's
        results. Never raises."""
        try:
            drafthost.catalog(builtin_ids={s["id"] for s in strategies.catalog()})
        except Exception:      # noqa: BLE001 -- the route reads it on ask
            pass
        warm_desklab_results()

    r.warm = warm                   # the chart service runs it in a thread after startup, then every WARM_EVERY_S
    return r


def tester_router(write_ok: Callable[[Request], None], archive: Path,
                  state: Path | None = None, notify: Callable[[dict], int] | None = None,
                  live_roots=DEFAULT_ROOTS) -> APIRouter:
    """Production (state None): homebase/.state/tester + the ~/futures_derived tape
    cache. A test passes its tmp dir and gets the runs AND the cache under it."""
    base = Path(state) if state else default_base()
    cache = base / "tape" if state else CACHE
    return make_router(write_ok, RunManager(base, archive=archive, cache=cache),
                       GridManager(base, archive=archive, cache=cache),
                       WalkForwardManager(base, archive=archive, cache=cache), notify=notify, live_roots=live_roots)
