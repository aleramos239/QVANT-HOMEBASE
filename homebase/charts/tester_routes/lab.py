"""make_router's Lab routes, moved verbatim: the strategy list and sources, the drafts library, the strategy form,
review requests, the Lab's groups and the group builder (/groupmix)."""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import json
import re
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request

from ... import draftstore, strategies
from ...backtest import drafthost
from ...backtest.runner import read_json
from ...labrun import store
from .. import groupmix
from .. import deskresults, lab_forms, lab_templates, reviewpack


ON_THE_DESK = "It is on the Desk. Remove it from the Desk first."   # a draft with a promoted record is not deleted
NOT_TRASHED = "It could not be moved to the trash."   # the move failed (an OSError): nothing was deleted
_STRATEGIES_DIR = Path(strategies.__file__).resolve().parent


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


def register(r: APIRouter, ctx) -> None:
    write_ok, manager, known, json_body, _rescore = ctx.write_ok, ctx.manager, ctx.known, ctx.json_body, ctx.rescore

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
        keep = ("class", "name", "root", "session_window", "bar_minutes", "bar_sizes", "own_stop", "session_independent", "doc")
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

    def ledger_of(run_id):
        t = read_json(manager.runs / run_id / "trades.json", None) if isinstance(run_id, str) else None
        t = t.get("trades") if isinstance(t, dict) else t
        return t if isinstance(t, list) else None
