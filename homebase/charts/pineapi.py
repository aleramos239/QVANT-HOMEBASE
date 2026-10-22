"""Pine Script on the chart page: the three GET routes the page's Pine Worker needs. The runtime
(PineTS, AGPL) and every .pine script live OUTSIDE the repo, under ~/.homebase/pine
(HOMEBASE_PINE_DIR overrides it; the test suite always does):

    runtime/node_modules/pinets/dist/pinets.min.browser.js   npm install --ignore-scripts --save-exact pinets@0.12.1
    scripts/*.pine                                           the owner's scripts

    GET /api/pine/runtime.js        the runtime file, only when its sha256 is the pinned build (404 otherwise)
    GET /api/pine/scripts           [{name, version, kind, title}] read from each script's header
    GET /api/pine/scripts/{name}    the script's text; a name outside the folder is 404

The server computes nothing for Pine: the Worker (static/charts/pineworker.js) runs the script in the page.
routes() is registered by server.py."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response

from .tester_api import host_ok

ENV = "HOMEBASE_PINE_DIR"
RUNTIME_VERSION = "0.12.1"
RUNTIME_SHA256 = "45e7a7ed89a5796db4b8cb1e215e74bb1d30d7614d514818dccc752396dd2b37"
NAME_RE = re.compile(r"^[\w .-]+\.pine$")
_VERSION_RE = re.compile(r"^\s*//@version\s*=\s*(\d+)", re.M)
_HEAD_RE = re.compile(r"^\s*(indicator|strategy|study)\s*\(\s*(?:title\s*=\s*)?([\"'])(.*?)\2", re.M)


def pine_dir() -> Path:
    v = os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "pine"


def runtime_path() -> Path:
    return pine_dir() / "runtime" / "node_modules" / "pinets" / "dist" / "pinets.min.browser.js"


def scripts_dir() -> Path:
    return pine_dir() / "scripts"


def script_meta(name: str, text: str) -> dict:
    """What the picker shows: the //@version, indicator|strategy and the declared title."""
    v = _VERSION_RE.search(text)
    h = _HEAD_RE.search(text)
    kind = h.group(1) if h else None
    return {"name": name, "version": int(v.group(1)) if v else None,
            "kind": "indicator" if kind == "study" else kind, "title": h.group(3) if h else None}


def list_scripts() -> list[dict]:
    d = scripts_dir()
    out = []
    for p in sorted(d.glob("*.pine")) if d.is_dir() else []:
        if NAME_RE.match(p.name) and p.is_file():
            try:
                out.append(script_meta(p.name, p.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return out


def script_path(name: str) -> Path | None:
    """The file for a name, or None when the name is not a plain file inside the scripts folder."""
    if not NAME_RE.match(name):
        return None
    d = scripts_dir().resolve()
    p = (d / name).resolve()
    if p.parent != d or not p.is_file():
        return None
    return p


def routes() -> APIRouter:
    r = APIRouter(prefix="/api/pine", dependencies=[Depends(host_ok)])

    @r.get("/runtime.js")
    def runtime():
        try:
            data = runtime_path().read_bytes()
        except OSError:
            raise HTTPException(404, "Pine runtime not installed") from None
        if hashlib.sha256(data).hexdigest() != RUNTIME_SHA256:
            raise HTTPException(404, f"Pine runtime is not the pinned build (pinets {RUNTIME_VERSION})")
        return Response(content=data, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})

    @r.get("/scripts")
    def scripts():
        return list_scripts()

    @r.get("/scripts/{name}")
    def script(name: str):
        p = script_path(name)
        if p is None:
            raise HTTPException(404, "no such script")
        return PlainTextResponse(p.read_text(encoding="utf-8", errors="replace"))

    return r
