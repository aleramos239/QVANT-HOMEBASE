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
                                          toolkit bp.py as a child process; it saves in the app itself). A long job
                                          answers after LAB_WAIT_S at most with its job id: send it again with job_id
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
    POST /api/tester/desklab/promote     {name, run_id} -> {ok, name, notes} | {ok: false, detail}: a frozen copy of the
                                          draft's text, its settings and that backtest's headline numbers. Refused (in
                                          words) for a draft not in the Lab, a run that is not a finished run of it, code
                                          that changed since, code that cannot be read, one that is not
                                          session_independent, a market this service does not stream, a sandbox that does
                                          not work. No draft runs here and no order goes anywhere; it does queue the copy's
                                          unseen-days backtest (once per code + settings, a tester run like the Lab's Run)
    POST /api/tester/desklab/remove      {name} -> {ok, removed, name}: the record goes, its days and journal stay
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
    POST /api/tester/grid                {strategy, inputs, axes: [{key, values}] x2-3, qty, commission,
                                          slippage_ticks, capital?, prop_rules?} -> {id}
                                          (<= 60 cells, over the body's own range -- the build days,
                                          2021-09-22 -> 2025-06-30, when it names none)
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
import contextlib
import datetime as dt
import hashlib
import inspect
import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .. import arsenal, draftstore, ideastore, netguard, strategies
from ..backtest import drafthost
from ..backtest import propsim, sandbox, slots
from ..backtest.grid import GridManager, LooksCorrupt
from ..backtest.runner import RunManager, _run_propsim, default_base, read_json
from ..backtest.stats import montecarlo
from ..backtest import walkforward
from ..backtest.walkforward import WalkForwardManager
from ..backtest.slots import Slots
from ..backtest.tape import CACHE
from ..claude_mcp import blueprint_tools, pipeline_tools
from ..claude_mcp.client import ToolError
from ..labrun import door, store
from .desk import DESK_URL
from . import groupmix
from ..labrun.host import session_today
from . import DEFAULT_ROOTS, deskgroups, deskresults, lab_forms, lab_templates, reviewpack
from .paperbook import DESK_ORIGINS, _cors, desk_origin_refusal

MC_CACHE = 64            # Monte Carlo results kept per service (review I3)
LAB_WAIT_S = 20          # the longest a blueprint tool started from the Lab waits for a job before it hands back its id
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


DESKLAB_ACTIONS = ("promote", "remove", "onoff", "open", "archive", "filed", "restore", "archive_builtin", "restore_builtin")
ARCHIVE_GROUP = "Archive"     # the Lab group an archived strategy's draft is filed under (the owner, 2026-10-18)
DESKGROUP_ACTIONS = ("create", "rename", "kind", "delete", "move")
DESKLAB_ALIVE_S = 20     # the Lab-strategy runner is alive while its heartbeat is at most this old
ON_THE_DESK = "It is on the Desk. Remove it from the Desk first."   # a draft with a promoted record is not deleted
NOT_TRASHED = "It could not be moved to the trash."   # the move failed (an OSError): nothing was deleted
DESKLAB_TAKE_OFF = "Take its accounts off on the Desk first."   # Promote again / Remove while the desk has it booked
DESKLAB_AUTO_UNSEEN = True   # a promoted strategy's unseen-days run starts by itself, once per code + settings (owner 2026-10-11)
DESKLAB_PROP = "lucid-pro-50k-no-dll@2026-10-11"   # the account every Desk panel's prop sim is scored on (the pipeline's account; owner 2026-10-11)
DESKLAB_DAYS = 10        # day summaries shown under each promoted strategy ...
DESKLAB_DAY_KEYS = ("date", "state", "why", "net", "match")      # ... each cut to these and `rebuilt` (no order or trade rows)
PIPE_KEYS = {"add": ("card", "inbox"), "start": (), "pause": (), "resume": (), "approve": ("name",), "refuse": ("name", "why")}
PIPE_QUIET = ("add", "start", "resume")      # what can start heavy work: not in a quiet window of the tester
PIPE_SHAPE = ("{action: add, card: {...}, inbox?: true | false} | {action: start | pause | resume} | "
              "{action: approve, name} | {action: refuse, name, why}")


class _Blueprint(pipeline_tools.PipelineMixin, blueprint_tools.BlueprintMixin):
    """The blueprint tools as the connector has them (one per phase, each a command of the research toolkit), and the
    pipeline's, for the Lab's own panels: the same code path, so the page and a chat can never disagree about a tool."""
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
                notify: Callable[[dict], int] | None = None, live_roots=DEFAULT_ROOTS) -> APIRouter:
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
        keep = ("class", "name", "root", "session_window", "bar_minutes", "bar_sizes", "session_independent", "doc")
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

    @r.get("/drafts/form")
    def draft_form():
        return lab_forms.schema()

    async def form_body(request: Request):
        write_ok(request)
        json_body(request)
        try:
            body = await request.json()
        except (ValueError, RecursionError):                 # not JSON, or nested too deep to read
            raise HTTPException(400, "the body is JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "send a JSON object")
        return body

    @r.post("/drafts/form/build")
    async def build_draft_form(request: Request):
        body = await form_body(request)
        answers, replace = body.get("answers"), body.get("replace", False)
        if not isinstance(answers, dict) or not isinstance(replace, bool):
            raise HTTPException(400, "{answers: the form's answers, replace?: true}")
        try:
            code = lab_forms.build(answers)
        except lab_forms.FormError as e:
            return {"ok": False, "errors": {e.field: e.sentence}}
        name, taken = answers["name"], {"ok": False, "errors": {"name": "That name is taken."}}
        try:
            draftstore.validate_name(name, builtin_ids())           # the check PUT /drafts/{name} makes
        except ValueError:
            return taken
        path = draftstore.path_for(name)
        if not replace and (path.exists() or path.is_symlink()):
            return taken
        return {"ok": True, "code": code, "name": name, "sentence": lab_forms.sentence(answers)}

    @r.post("/drafts/form/read")
    async def read_draft_form(request: Request):
        body = await form_body(request)
        code = body.get("code")
        if not isinstance(code, str) or len(code.encode("utf-8", "replace")) > draftstore.MAX_BYTES:
            raise HTTPException(400, f"{{code: the draft's text, at most {draftstore.MAX_BYTES:,} bytes}}")
        got = lab_forms.read(code)
        out = {"answers": got["answers"], "intact": got["intact"]} if got else {"answers": None, "intact": False}
        try:
            json.dumps(out, ensure_ascii=False, allow_nan=False).encode("utf-8")   # exactly as the response encodes it
        except (ValueError, TypeError, RecursionError):        # UnicodeEncodeError is a ValueError
            out = {"answers": None, "intact": False}
        return out

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
            with store.write_lock():              # the check and the move are one step: a Promote is not half way in
                if store.has_record_file(name):   # promoted (the record file is there, whether or not it reads)
                    raise HTTPException(409, ON_THE_DESK)
                return {"deleted": draftstore.delete(name)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except OSError:                           # the filesystem refused the move: the file is where it was
            raise HTTPException(500, NOT_TRASHED) from None

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
                bundle = await asyncio.to_thread(manager.bundle, rid, False)
            except ValueError as e:
                raise HTTPException(409, str(e)) from None
            if (bundle.get("run") or {}).get("strategy", {}).get("id") != draftstore.draft_id(name):
                raise HTTPException(409, f"run {rid} is not a run of draft_{name}")
        meta, _, _ = meta_or_error(code)
        return await asyncio.to_thread(reviewpack.create, name, code, meta, bundle, str(body.get("note") or ""))

    # ---- the Lab's groups: which section of the list a strategy is shown under (draftstore, groups.json) --------
    def grouped(edit: Callable[..., dict], *args) -> dict:
        try:
            return edit(*args)
        except draftstore.GroupsUnreadable as e:       # refused, never shown (or written over) as no groups
            raise HTTPException(409, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    def group_body(request: Request, body: dict, *keys: str) -> list:
        write_ok(request)
        json_body(request)
        if set(body) - set(keys):
            raise HTTPException(400, "{" + ", ".join(keys) + "}")
        return [body.get(k) for k in keys]

    @r.get("/groups")
    def list_groups():
        return grouped(draftstore.read_groups)

    @r.post("/groups")
    def add_group(request: Request, body: dict):
        return grouped(draftstore.add_group, *group_body(request, body, "name"))

    @r.post("/groups/rename")
    def rename_group(request: Request, body: dict):
        return grouped(draftstore.rename_group, *group_body(request, body, "name", "to"))

    @r.post("/groups/delete")
    def delete_group(request: Request, body: dict):
        return grouped(draftstore.remove_group, *group_body(request, body, "name"))

    @r.post("/groups/move")
    def move_to_group(request: Request, body: dict):
        sid, group = group_body(request, body, "strategy", "group")
        known_ids = builtin_ids() | {draftstore.draft_id(n) for n, _ in draftstore.list_files()}
        if not isinstance(sid, str) or sid not in known_ids:
            raise HTTPException(404, f"no strategy {sid!r}")
        return grouped(draftstore.set_group, sid, group)

    @r.post("/groups/status")
    def set_status(request: Request, body: dict):
        sid, status = group_body(request, body, "strategy", "status")
        known_ids = builtin_ids() | {draftstore.draft_id(n) for n, _ in draftstore.list_files()}
        if not isinstance(sid, str) or sid not in known_ids:
            raise HTTPException(404, f"no strategy {sid!r}")
        return grouped(draftstore.set_status, sid, status)

    @r.post("/groupmix")
    def group_mix(request: Request, body: dict):
        """The Lab's group builder (groupmix.py): {members: [{strategy, size}], prop_rules} -> each member's latest build-days
        run at its size, cut to the days all of them cover: each one's numbers, the group's as one account, how alike their
        days are, and the prop sim of the merged ledger on `prop_rules`. Reads saved runs only; nothing is run or written."""
        write_ok(request)
        json_body(request)
        ms, rule = body.get("members"), body.get("prop_rules")
        if set(body) - {"members", "prop_rules"} or not isinstance(ms, list) or not 2 <= len(ms) <= 12:
            raise HTTPException(400, "{members: 2 to 12 of {strategy, size}, prop_rules}")
        members, left = [], []
        for m in ms:
            sid, k = (m or {}).get("strategy"), (m or {}).get("size", 1)
            if not isinstance(sid, str) or isinstance(k, bool) or not isinstance(k, (int, float)) \
                    or not groupmix.SIZE_MIN <= k <= groupmix.SIZE_MAX:
                raise HTTPException(400, f"a member is {{strategy, size {groupmix.SIZE_MIN:g} to {groupmix.SIZE_MAX:g}}}")
            run = groupmix.build_run(manager.runs_list(limit=200, strategy=sid))
            trades = ledger_of(run["id"]) if run else None
            if not trades:
                left.append({"strategy": sid, "why": "no finished build-days run with trades: run it on the build days first"})
                continue
            members.append({"name": sid, "size": float(k), "run": run, "trades": trades})
        if len({m["name"] for m in members}) != len(members):
            raise HTTPException(400, "a strategy is in the group twice")
        if len(members) < 2:
            return {"left_out": left, "error": "at least two members need a build-days run"}
        try:
            got = groupmix.mix(members)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        ledger = got.pop("ledger")
        prop = None
        if rule:
            key = ("mix", tuple((m["name"], m["run"]["id"], m["size"]) for m in members))
            prop = deskresults.prop_headline(_rescore(key, lambda: {"run": {}, "trades": ledger, "propsim": None}, rule))
        return {**got, "left_out": left, "prop": prop}

    # ---- the blueprint toolkit in the Lab: the tools every chat has, listed and run from the page ------------
    box = _Blueprint()
    bp_specs = {s["name"]: s for s in blueprint_tools.SPECS}

    @r.get("/blueprint")
    def blueprint_toolkit():
        tools = []
        for s in blueprint_tools.SPECS:
            head, _, text = s["description"].partition(": ")
            tools.append({"name": s["name"], "phase": head, "description": text or head, "inputs": s["inputSchema"]})
        return {"tools": tools, "ideas": ideastore.list_ideas(), "wait_s": LAB_WAIT_S}

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
        if "wait_s" in bp_specs[tool]["inputSchema"]["properties"]:      # a page never holds a request for an hour
            w = args.get("wait_s", LAB_WAIT_S)
            args = {**args, "wait_s": LAB_WAIT_S if isinstance(w, bool) or not isinstance(w, int) else max(0, min(w, LAB_WAIT_S))}
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
        return watch_answer(request, {"strategies": out, "archived": archived, "builtins": desk_strategy_ids(), "runner": {
            "alive": runner_alive(beat.get("seen_utc")), "seen_utc": beat.get("seen_utc"), "prices": beat.get("prices") or {}}})

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

    def ensure_unseen(rec: dict) -> dict:
        """The state of the record's unseen-days run (deskresults.unseen_state); when there is none, start it -- once: a run
        that failed or was cancelled is not started again by itself. A start the tester refuses (a quiet window of the tester,
        a sandbox that is down) leaves the state as it was, and the next ask tries again. Never raises."""
        try:
            with unseen_lock:
                got = deskresults.unseen_state(manager.runs, rec)
                if got["state"] != "none" or not DESKLAB_AUTO_UNSEEN:
                    return got
                try:
                    manager.submit(deskresults.unseen_request(rec, slots.et_now().date()))
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
        ensure_unseen does. {"state": "unfit", "why"} for a strategy the walk-forward cannot search, {"state": "changed"}
        when the Lab's code is no longer the promoted copy (a run of it would never match). Never raises."""
        today = slots.et_now().date()
        try:
            with wf_lock:
                try:
                    got = deskresults.wf_state(wfs.grids, rec, today)
                except ValueError as e:
                    return {"state": "unfit", "why": str(e)}
                if got["state"] != "none" or not DESKLAB_AUTO_UNSEEN:
                    return got
                try:
                    src = draftstore.read(rec["name"])
                except (FileNotFoundError, ValueError, OSError):
                    return {"state": "changed"}
                if hashlib.sha256(src.encode("utf-8")).hexdigest() != rec.get("sha256"):
                    return {"state": "changed"}
                try:
                    wfs.submit(deskresults.wf_request(rec, today))
                except Exception:      # noqa: BLE001 -- not now: refused in words by the tester, or not working
                    return got
                return deskresults.wf_state(wfs.grids, rec, today)
        except Exception:      # noqa: BLE001 -- a panel's research never costs a promote or the list its answer
            return {"state": "none"}

    def wf_block(rec: dict) -> dict:
        """The card's unseen block from the 3:1 walk-forward: {unseen, unseen_state, curve, pick, why, prop_unseen}."""
        got = ensure_wf(rec)
        out = {"unseen": None, "unseen_state": got["state"], "curve": None, "pick": None, "why": got.get("why"),
               "prop_unseen": None}
        if got["state"] != "done":
            return out
        try:
            res = wfs.result(got["id"])
        except (ValueError, KeyError, OSError):
            out["unseen_state"] = "failed"
            return out
        trades = (res.get("stitched") or {}).get("trades") or []
        out.update(unseen=deskresults.wf_summary(got["id"], res), curve=deskresults.curve_of_trades(trades),
                   pick=deskresults.wf_pick(rec, res))
        try:
            out["prop_unseen"] = deskresults.prop_headline(_rescore(("wf", got["id"]), lambda: {"run": {}, "trades": trades},
                                                                    DESKLAB_PROP))
        except (HTTPException, KeyError, ValueError, OSError):
            pass
        return out

    def warm_desklab_results() -> None:
        """Score every promoted strategy's (and the two built-in straddles' twins') saved runs, so the Desk's first results
        ask is a cache hit (about 16 prop sims: 25-90 s cold; a new run was 3-4 s on the next ask). One pass; the chart
        service repeats it every WARM_EVERY_S. Reads saved runs only and never starts one (unlike ensure_unseen). The lock
        is taken per record, so a real ask is never held behind the whole warm-up. Never raises."""
        try:
            for rec in store.listing():
                with desk_res_lock:
                    rid = (rec.get("run") or {}).get("id")
                    if rid:
                        prop_of(rid)
                    try:
                        st = deskresults.wf_state(wfs.grids, rec, slots.et_now().date())
                        if st["state"] == "done":
                            tr = (wfs.result(st["id"]).get("stitched") or {}).get("trades") or []
                            _rescore(("wf", st["id"]), lambda: {"run": {}, "trades": tr}, DESKLAB_PROP)
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
        except Exception:      # noqa: BLE001 -- a warm-up never takes the service down; the route computes it on ask
            pass

    @r.get("/desklab/results")
    def desklab_results(request: Request):
        """The research the Desk's panel shows beside a promoted strategy (deskresults.py). Saved runs and their saved trades
        only: no strategy runs and no test day is read. A plain `def`: FastAPI's threadpool, not the loop."""
        watch_guard(request)
        out = {}
        with desk_res_lock:
            for rec in store.listing():
                # the unseen days ARE the 3:1 walk-forward's stitched out-of-sample record (owner, 2026-10-18)
                build, w = (rec.get("run") or {}).get("id"), wf_block(rec)
                out[rec["name"]] = {"unseen": w["unseen"], "unseen_state": w["unseen_state"], "curve": w["curve"],
                                    "walkforward": True, "pick": w["pick"], "why": w["why"],
                                    "prop": {"build": prop_of(build) if build else None, "unseen": w["prop_unseen"]}}
            # the Desk's own straddles (nq930, gc_nfp): their tester twin's SAVED runs, at the Desk's size and setting. Nothing here
            # starts a run (the unseen days of a built-in are read by hand, once, from the Lab): "manual" says so to the page.
            for desk_id in deskresults.BUILTIN_TWINS:
                try:
                    rec = deskresults.builtin_rec(desk_id)
                    got = deskresults.unseen_state(manager.runs, rec)
                    build, unseen = deskresults.build_run_id(manager.runs, rec), got.get("run")
                    out[desk_id] = {"unseen": unseen, "unseen_state": got["state"], "manual": True, "twin": rec["id"],
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
        ensure_wf(store.get(name))          # its unseen days (the 3:1 walk-forward) run by themselves (owner 2026-10-11, 2026-10-18)
        return {"ok": True, "name": name, "notes": notes}

    def desklab_remove(name: str) -> dict:
        """Refused while accounts are assigned on the Desk (the desk's sidecar holds book rows); the sidecar itself
        is the desk's and is never written here."""
        with store.write_lock():
            if store.booked(name):
                raise HTTPException(409, DESKLAB_TAKE_OFF)
            return {"ok": True, "removed": store.remove(name), "name": name}

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
        if name not in desk_strategy_ids():
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

    open_ask = {"name": None, "run": None, "builtin": False, "at": 0.0}      # the Desk page's "Open in the Lab": one request, kept for a short while

    def desklab_open(name: str, run: str | None = None, builtin: bool = False) -> dict:
        """The Desk page asks the Lab page to show one draft. The Mac app drops a link's #fragment when it switches
        tab, so the ask waits here and the Lab page takes it (GET /lab-open) the moment it is shown. `run`: a finished run of
        it to put on the chart as well (the Desk's "Show on chart"). `builtin`: the name is a built-in tester strategy (the twin
        of one of the Desk's own straddles), not a draft."""
        if builtin:
            if name not in deskresults.BUILTIN_TWINS.values():
                raise HTTPException(404, "That strategy is not in the Lab.")
        else:
            try:
                draftstore.read(name)
            except (FileNotFoundError, ValueError, OSError):
                raise HTTPException(404, "That strategy is not in the Lab.") from None
        open_ask["name"], open_ask["run"], open_ask["builtin"], open_ask["at"] = name, run, bool(builtin), time.monotonic()
        return {"ok": True, "name": name}

    @r.get("/lab-open")
    def lab_open_take():
        """The Lab page takes the Desk's ask, once: {name} (null when none, or one older than two minutes)."""
        name, run, at, builtin = open_ask["name"], open_ask["run"], open_ask["at"], open_ask["builtin"]
        open_ask["name"] = open_ask["run"] = None
        open_ask["builtin"] = False
        fresh = bool(name) and time.monotonic() - at <= 120
        return {"name": name if fresh else None, **({"run": run} if fresh and run else {}),
                **({"builtin": True} if fresh and builtin else {})}

    def desklab_onoff(name: str, on: bool) -> dict:
        if store.set_enabled(name, on) is None:
            raise HTTPException(404, "That strategy is not on the Desk.")
        return {"ok": True, "name": name, "enabled": on}

    @r.post("/desklab/{what}")
    async def desklab_write(what: str, request: Request):
        """promote {name, run_id}: a draft that was backtested goes on the Desk, frozen. remove {name}: its record goes
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
            keys = {"promote": {"name", "run_id"}, "remove": {"name"}, "onoff": {"name", "on"}, "open": {"name"},
                    "archive": {"name"}, "filed": {"name"}, "restore": {"name"},
                    "archive_builtin": {"name"}, "restore_builtin": {"name"}}[what]
            run = body.get("run") if what == "open" and isinstance(body, dict) else None
            if run is not None and (not isinstance(run, str) or not re.fullmatch(r"[0-9a-z_-]{1,120}", run)):
                raise HTTPException(400, "run: a finished run's id")
            builtin = body.get("builtin") if what == "open" and isinstance(body, dict) else None
            if builtin is not None and builtin is not True:
                raise HTTPException(400, "builtin: true")
            if what == "open" and run is not None:
                keys = {"name", "run"}
            if what == "open" and builtin is not None:
                keys = keys | {"builtin"}
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
                elif what == "remove":
                    done = await asyncio.to_thread(desklab_remove, name)
                elif what == "open":
                    done = await asyncio.to_thread(desklab_open, name, run, builtin is True)
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

    # ---- Desk groups (deskgroups.py): named sets of Desk strategies, kept beside the Lab records. Bookkeeping only: a group
    # ---- books no account and switches nothing; its results are read off the members' saved runs.
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
                groups = await asyncio.to_thread(deskgroups.apply, what, body)
            except deskgroups.GroupError as e:
                raise HTTPException(409, str(e)) from None
            return watch_answer(request, {"ok": True, "groups": groups})
        except HTTPException as e:
            return watch_answer(request, {"ok": False, "detail": e.detail}, e.status_code)

    def ledger_of(run_id):
        t = read_json(manager.runs / run_id / "trades.json", None) if isinstance(run_id, str) else None
        t = t.get("trades") if isinstance(t, dict) else t
        return t if isinstance(t, list) else None

    @r.get("/deskgroups/results")
    def deskgroups_results(request: Request):
        """For each group: its members' own unseen-days numbers and, for the members' saved runs put together as one account's
        trades, the same on the build days and on the unseen days (net, win rate, PF, drawdown, days, the curve, the prop sim on
        DESKLAB_PROP). A member that is not a Lab strategy, or has no unseen-days run yet, is left out of the unseen figures and
        named. Saved runs only; a member's missing unseen run is started like the Desk panel's (ensure_unseen)."""
        watch_guard(request)

        def prop_of(ids, ledger):
            if not ledger:
                return None
            try:
                got = _rescore(("group", tuple(sorted(ids))), lambda: {"run": {}, "trades": ledger, "propsim": None}, DESKLAB_PROP)
                return deskresults.prop_headline(got)
            except (HTTPException, KeyError, ValueError, OSError):
                return None
        out = {}
        with desk_res_lock:
            for g in deskgroups.load():
                members, build_in, unseen_in, left_out = [], [], [], []
                for sid in g["members"]:
                    try:
                        rec = store.get(sid[4:]) if sid.startswith("lab_") else None
                    except ValueError:
                        rec = None
                    if not isinstance(rec, dict):
                        left_out.append({"strategy": sid, "why": "not on the Desk any more" if sid.startswith("lab_")
                                         else "built in: it has no unseen-days run to add"})
                        continue
                    got = ensure_unseen(rec)
                    unseen_run = got.get("run")
                    b_id = (rec.get("run") or {}).get("id")
                    members.append({"strategy": sid, "label": rec.get("label") or rec.get("name"), "state": got["state"],
                                    "build": {k: (rec.get("run") or {}).get(k) for k in ("net", "trades", "win_rate", "profit_factor", "max_drawdown")},
                                    "unseen": ({k: unseen_run.get(k) for k in ("net", "trades", "win_rate", "profit_factor", "max_drawdown")}
                                               if unseen_run else None)})
                    if ledger_of(b_id) is not None:
                        build_in.append((sid, b_id))
                    if unseen_run and ledger_of(unseen_run["id"]) is not None:
                        unseen_in.append((sid, unseen_run["id"]))
                    else:
                        left_out.append({"strategy": sid, "why": "no unseen-days run yet"})
                res = {"id": g["id"], "name": g["name"], "kind": g["kind"], "members": members, "left_out": left_out}
                for key, chosen in (("build", build_in), ("unseen", unseen_in)):
                    ledger, owners = deskgroups.merged([(sid, ledger_of(rid) or []) for sid, rid in chosen])
                    res[key] = deskgroups.summarize(ledger, owners)
                    res.setdefault("prop", {})[key] = prop_of([rid for _, rid in chosen], ledger)
                    res.setdefault("in", {})[key] = [sid for sid, _ in chosen]
                out[g["id"]] = res
        return watch_answer(request, {"results": out})

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
        if run_meta.get("prop_rules") == rule_id and (b.get("propsim") or {}).get("breach"):
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

    r.manager = manager   # so the chart service can stop an in-flight child on shutdown
    r.grids = grids       # likewise every grid cell's child
    r.wfs = wfs           # ... and every walk-forward cell's
    r.warm = warm_desklab_results   # the chart service runs it once in a thread after startup
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
