# Charts page — TradingView-style redesign + drawing tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the chart page (homebase chart service, :8852) look and behave like TradingView — one top toolbar acting on the selected chart, a left drawing rail, a DOM legend with indicator rows, TradingView-style menus and dialogs, a bottom status bar — and add trend line / horizontal line / rectangle / measure tools whose drawings are saved per symbol on the server.

**Architecture:** Plain scripts, no bundler. `charts.html` (shell) + `charts/charts.css` (tokens + styles) + `charts/icons.js` (Lucide SVG strings) + `charts/catalog.js` (pure: indicator catalog, migration, formatting) + `charts/primitives.js` (existing canvas layers) + `charts/drawings.js` (pure geometry + store, then the canvas primitive + pointer controller) + `charts/cell.js` (one chart) + `charts/app.js` (the page). Pure JS is unit-tested with Node's built-in runner through pytest. The server gains `GET/PUT /api/drawings/{root}` and Origin checks on HTTP writes; the websocket protocol and every number the server computes stay exactly as they are.

**Tech Stack:** Python 3 / FastAPI / pytest; Lightweight Charts 5.2.1 (vendored standalone build, `window.LightweightCharts`); Lucide icons 1.48.0 (ISC; Feather-derived icons MIT) inlined; Node ≥ 20 (`node --test`) for JS unit tests.

**Spec:** `docs/superpowers/specs/2026-09-26-charts-tv-redesign-design.md`

## Global Constraints

- Work only inside the worktree `/Users/ramoscapital/ramos-quant-homebase/.worktrees/charts-ui` (branch `feat/charts-ui`). Never modify, check out, stash or commit anything in `/Users/ramoscapital/ramos-quant-homebase` outside `.worktrees/` — that checkout runs the LIVE trading desk.
- Python is `.venv/bin/python` (a symlink to the live venv — never `pip install` into it). Full suite: `.venv/bin/python -m pytest -q` (baseline 221 passed).
- Never start servers from Bash (no `python -m homebase.charts`, no uvicorn), never run `deploy/install.sh`, never `launchctl`. The controller does all browser verification on a replay (`homebase-charts-ui-replay`, port 8854).
- Tests never open network or broker connections, never read tokens, and never write to `~/futures_ticks` (use pytest's `tmp_path`).
- A shell hook blocks `rm -rf`; delete single files with `git rm` / `rm`.
- No native dialogs (`alert`, `confirm`, `prompt`) — the desktop viewer blocks them. Every error or confirmation is inline DOM, written with `textContent`.
- No new runtime dependencies: no npm packages, no CDN at runtime; the page loads only `/static/...` files.
- Design tokens (spec, verbatim):

  | token | light | dark |
  |---|---|---|
  | `--frame` | `#EBEBEB` | `#0A0A0A` |
  | `--panel` | `#FFFFFF` | `#0F0F0F` |
  | `--text` | `#0F0F0F` | `#DBDBDB` |
  | `--text-2` | `#787B86` | `#8C8C8C` |
  | `--border` | `#E0E3EB` | `#2E2E2E` |
  | `--grid` | `#F0F3FA` | `#1C1C1C` |
  | `--hover` | `#F0F3FA` | `#2A2A2A` |
  | `--pill` | `#EBEBEB` | `#2A2A2A` |
  | `--accent` | `#2962FF` | `#2962FF` |
  | `--accent-soft` | `rgba(41,98,255,.10)` | `rgba(41,98,255,.20)` |
  | `--up` / `--down` | `#089981` / `#F23645` | same |
  | volume up / down | `rgba(8,153,129,.5)` / `rgba(242,54,69,.5)` | same |
  | crosshair | `#9598A1` dashed, label bg `#131722` | same |
  | watermark | `rgba(15,15,15,.06)` | `rgba(219,219,219,.06)` |

- Font `-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif`; toolbar/menus 14px; legend title 16px (1–2 charts) / 14px (4–6 charts); legend values 13px; axes 12px; bottom bar 12px; numbers `font-variant-numeric: tabular-nums`. Radii: panels 6px, menus/dialogs 8px, pill 14px, rail buttons 4px. Shadows: menus `0 2px 8px rgba(0,0,0,.16)`, dialogs `0 8px 32px rgba(0,0,0,.24)`. Focus: 2px `--accent` outline on `:focus-visible`.
- Icons: Lucide `lucide-static@1.48.0` only (plus one custom trend-line glyph drawn in the same stroke style), inlined with the license notice. Never TradingView's icons, logo or branding; the only TradingView text on the page is the bottom-bar credit link "Charts: TradingView Lightweight Charts™".
- Every JS file is one IIFE with `'use strict'` exposing exactly one `window.HB*` namespace. The pure modules (`catalog.js`, and `drawings.js` until Task 6 adds its browser half) also set `module.exports` when `module` exists and touch no browser global at load time (browser globals only inside functions that run in the page).
- Wire protocol unchanged: client `{"op":"sub",id,root,spec,studies,fp}` / `{"op":"unsub",id}`; server `history` / `update` / `reset` / `error` / `status`.
- Lightweight Charts v5 quirk: `timeScale().logicalToCoordinate(i)` is only right for INTEGER `i` (it returns 0 for a fractional logical) — interpolate between the two integer coordinates.
- Commit at the end of each task (conventional message) ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Plan-level rulings (refinements of the spec, decided before execution)

- **R-P1** Volume and Delta legend rows show the name only; the OHLC row already carries `Vol` and `Δ`.
- **R-P2** Price-pane indicator lines show a coloured last-value tag on the price axis with no name (`title: ''`) — TradingView's default (value labels on, name labels off).
- **R-P3** Moving-average lines use `lineWidth: 1` (Lightweight Charts' `LineWidth` is 1|2|3|4); VWAP 2.
- **R-P4** Volume-profile rows: outside the value area `--accent-soft`, inside `rgba(41,98,255,.28)` (dark `.40`), POC `#F7A600` — accent-soft alone is too faint to read as a profile.
- **R-P5** The symbol pill is a magnifier icon + the root (TradingView's pill), no chevron.
- **R-P6** Gestures the drawing controller owns call `preventDefault()` on `pointerdown` (Lightweight Charts 5.2.1 listens to mouse events only, so this suppresses its compatibility `mousedown/mousemove/mouseup` and it cannot pan) and also switch `handleScroll/handleScale` off for the gesture. Wheel zoom stays available while a tool is merely selected, as on TradingView.
- **R-P7** A refused subscription (server `error`) reverts the chart to its last working config and resubscribes it; the reason shows inline in the interval menu when that menu caused it, else as a red note in the legend for 8 s. (Closes Build 1's parked "rejected re-sub" item.)
- **R-P8** Hide/show is client-only (the server keeps computing a hidden study), so toggles are instant; adding/removing an indicator resubscribes only when it needs a study key the stream does not already carry.
- **R-P9** The chart view (scroll/zoom) is kept across theme toggles, indicator changes and resubscribes of the same root + interval; a symbol or interval change jumps to the latest bar.
- **R-P10** A layout is stored as `{grid, cells: [{root, spec, indicators}]}`; the page remembers the loaded layout's name as `name` inside localStorage `hb_charts_last`.

---

### Task 1: Drawings API + Origin check on HTTP writes (server)

**Files:**
- Modify: `homebase/charts/server.py`
- Test: `tests/test_charts_server.py`

**Interfaces:**
- Consumes: `origin_ok(origin, host)` (existing, `server.py`), `create_app(..., state=...)` (existing).
- Produces:
  - `GET /api/drawings/{root}` → the root's JSON list (`[]` when none); root is case-insensitive; unknown root → 404.
  - `PUT /api/drawings/{root}` with a JSON list → `{"ok": true, "count": n}`; stores the cleaned list; 400 with a `detail` message on anything invalid; 404 unknown root; 403 for a foreign `Origin`.
  - `PUT /api/layouts/{name}` and `DELETE /api/layouts/{name}` → 403 for a foreign `Origin` (no `Origin` header = not a browser = allowed, like `/ws`).
  - Module-level `MAX_DRAWINGS = 500` and `check_drawings(body) -> list` (the cleaned list; `ValueError` with a human message on anything invalid).
  - Storage: `<state>/drawings.json` = `{"NQ": [...], ...}`, written via temp file + `os.replace`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_charts_server.py` (add `check_drawings` and `MAX_DRAWINGS` to the existing `from homebase.charts.server import ...` line):

```python
TREND = {"id": "d1", "type": "trend", "color": "#2962FF",
         "points": [{"t": 1790000000000, "p": 30900.25}, {"t": 1790000600000, "p": 30950.0}]}
HLINE = {"id": "d2", "type": "hline", "points": [{"p": 30925.5}]}
RECT = {"id": "d3", "type": "rect",
        "points": [{"t": 1790000000000, "p": 30900}, {"t": 1790000300000, "p": 30880.75}]}


def test_drawings_roundtrip_per_root(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "drawings.json").write_text(json.dumps({"ES": [HLINE]}))   # another root's drawings
    with TestClient(replay_app(tmp_path)) as client:
        assert client.get("/api/drawings/NQ").json() == []
        r = client.put("/api/drawings/NQ", json=[TREND, HLINE, RECT])
        assert r.status_code == 200 and r.json() == {"ok": True, "count": 3}
        assert client.get("/api/drawings/NQ").json() == [TREND, HLINE, RECT]
        assert client.get("/api/drawings/nq").json() == [TREND, HLINE, RECT]
        assert json.loads((state / "drawings.json").read_text()) == {"ES": [HLINE], "NQ": [TREND, HLINE, RECT]}
        assert client.put("/api/drawings/NQ", json=[]).status_code == 200
        assert client.get("/api/drawings/NQ").json() == []
        assert client.get("/api/drawings/ZZ").status_code == 404
        assert client.put("/api/drawings/ZZ", json=[]).status_code == 404


def test_drawings_keep_only_what_the_page_draws():
    """Unknown keys are dropped; a horizontal line keeps only its price."""
    body = [{"id": "a", "type": "hline", "points": [{"p": 1.5, "t": 7, "x": 1}], "junk": True},
            {"id": "b", "type": "trend", "points": [{"t": 1, "p": 2, "q": 0}, {"t": 3, "p": 4}]}]
    assert check_drawings(body) == [{"id": "a", "type": "hline", "points": [{"p": 1.5}]},
                                    {"id": "b", "type": "trend", "points": [{"t": 1, "p": 2}, {"t": 3, "p": 4}]}]


H1 = {"id": "a", "type": "hline", "points": [{"p": 1}]}
BAD = [
    ("not a list", {"id": "x"}),
    ("item not an object", ["x"]),
    ("id missing", [{"type": "hline", "points": [{"p": 1}]}]),
    ("id empty", [{**H1, "id": ""}]),
    ("id too long", [{**H1, "id": "x" * 41}]),
    ("id not a string", [{**H1, "id": 7}]),
    ("unknown type", [{**H1, "type": "fib"}]),
    ("trend with one point", [{"id": "a", "type": "trend", "points": [{"t": 1, "p": 1}]}]),
    ("hline with two points", [{**H1, "points": [{"p": 1}, {"p": 2}]}]),
    ("points not a list", [{**H1, "points": {"p": 1}}]),
    ("point not an object", [{**H1, "points": [1]}]),
    ("t missing", [{"id": "a", "type": "rect", "points": [{"p": 1}, {"t": 2, "p": 2}]}]),
    ("t a float", [{"id": "a", "type": "trend", "points": [{"t": 1.5, "p": 1}, {"t": 2, "p": 2}]}]),
    ("t a bool", [{"id": "a", "type": "trend", "points": [{"t": True, "p": 1}, {"t": 2, "p": 2}]}]),
    ("p missing", [{**H1, "points": [{}]}]),
    ("p a string", [{**H1, "points": [{"p": "1"}]}]),
    ("p a bool", [{**H1, "points": [{"p": False}]}]),
    ("p not finite", [{**H1, "points": [{"p": float("inf")}]}]),
    ("colour a name", [{**H1, "color": "red"}]),
    ("colour too short", [{**H1, "color": "#12345"}]),
]


@pytest.mark.parametrize("why,body", BAD, ids=[b[0] for b in BAD])
def test_check_drawings_refuses_malformed_bodies(why, body):
    with pytest.raises(ValueError):
        check_drawings(body)


def test_check_drawings_caps_the_list():
    assert len(check_drawings([H1] * MAX_DRAWINGS)) == MAX_DRAWINGS
    with pytest.raises(ValueError):
        check_drawings([H1] * (MAX_DRAWINGS + 1))


def test_a_bad_drawings_body_is_a_400_and_saves_nothing(tmp_path):
    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/drawings/NQ", json=[H1]).status_code == 200
        r = client.put("/api/drawings/NQ", json=[{**H1, "type": "fib"}])
        assert r.status_code == 400 and "type" in r.json()["detail"]
        nan = '[{"id": "a", "type": "hline", "points": [{"p": NaN}]}]'
        assert client.put("/api/drawings/NQ", content=nan,
                          headers={"content-type": "application/json"}).status_code == 400
        assert client.put("/api/drawings/NQ", content="not json",
                          headers={"content-type": "application/json"}).status_code == 400
        assert client.get("/api/drawings/NQ").json() == [H1]


def test_browser_writes_from_another_site_are_refused(tmp_path):
    """Any page open in the desk machine's browser could otherwise rewrite
    or delete saved layouts and drawings (same rule as the /ws handshake)."""
    lay = {"grid": 2, "cells": [{"root": "NQ", "spec": "time:60", "indicators": []}]}
    evil = {"origin": "https://evil.example"}
    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/layouts/main", json=lay, headers=evil).status_code == 403
        assert client.put("/api/drawings/NQ", json=[H1], headers=evil).status_code == 403
        assert client.put("/api/layouts/main", json=lay).status_code == 200            # no Origin: not a browser
        assert client.delete("/api/layouts/main", headers=evil).status_code == 403
        assert client.get("/api/layouts").json() == {"main": lay}
        assert client.get("/api/drawings/NQ").json() == []
        for ok in ("http://localhost:8852", "http://127.0.0.1:8852", "http://testserver"):
            assert client.put("/api/drawings/NQ", json=[H1], headers={"origin": ok}).status_code == 200
        assert client.delete("/api/layouts/main", headers={"origin": "http://localhost:8852"}).status_code == 200


def test_a_failed_drawings_write_leaves_the_saved_drawings_intact(tmp_path, monkeypatch):
    real_write_text = Path.write_text

    def torn(self, data, *a, **k):
        real_write_text(self, data[: len(data) // 2], *a, **k)
        raise OSError(28, "No space left on device")

    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/drawings/NQ", json=[H1]).status_code == 200
        with monkeypatch.context() as m:
            m.setattr(Path, "write_text", torn)
            with pytest.raises(OSError):
                client.put("/api/drawings/NQ", json=[TREND])
        assert client.get("/api/drawings/NQ").json() == [H1]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_server.py -q -k "drawings or another_site"`
Expected: collection error / FAIL — `check_drawings` cannot be imported.

- [ ] **Step 3: Implement** in `homebase/charts/server.py`.

Add `import math` and `import re` to the imports. Next to `MAX_STUDIES`, add:

```python
MAX_DRAWINGS = 500            # per symbol
DRAWING_POINTS = {"trend": 2, "rect": 2, "hline": 1}
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
```

After `origin_ok`, add:

```python
def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_drawings(body) -> list:
    """The page's drawings for one symbol, validated and stripped to what
    the page draws: [{id, type, points: [{t?, p}], color?}]. ValueError
    (with a message for the page) on anything else."""
    if not isinstance(body, list) or len(body) > MAX_DRAWINGS:
        raise ValueError(f"drawings are a list of at most {MAX_DRAWINGS}")
    out = []
    for d in body:
        if not isinstance(d, dict):
            raise ValueError("each drawing is an object")
        did, kind, pts = d.get("id"), d.get("type"), d.get("points")
        if not isinstance(did, str) or not 1 <= len(did) <= 40:
            raise ValueError("id: a string of 1-40 characters")
        n = DRAWING_POINTS.get(kind)
        if n is None:
            raise ValueError("type: trend, hline or rect")
        if not isinstance(pts, list) or len(pts) != n or not all(isinstance(p, dict) for p in pts):
            raise ValueError(f"a {kind} has exactly {n} point(s)")
        clean = []
        for p in pts:
            if not _finite(p.get("p")):
                raise ValueError("a point's p is a finite number")
            if kind == "hline":
                clean.append({"p": p["p"]})
                continue
            t = p.get("t")
            if not isinstance(t, int) or isinstance(t, bool):
                raise ValueError("a point's t is an integer (epoch ms)")
            clean.append({"t": t, "p": p["p"]})
        item = {"id": did, "type": kind, "points": clean}
        if "color" in d:
            if not isinstance(d["color"], str) or not _HEX_COLOR.fullmatch(d["color"]):
                raise ValueError("color: #RRGGBB")
            item["color"] = d["color"]
        out.append(item)
    return out
```

Note: a key order difference matters for the round-trip test only through JSON equality of dicts (order-insensitive), so `TREND`'s `color` before `points` is fine.

Inside `create_app`, replace `write_layouts` with a shared atomic writer and add the drawings store and routes. After `layouts_path = sd / "layouts.json"` add `drawings_path = sd / "drawings.json"`. Replace the `read_layouts` / `write_layouts` / layout routes block with:

```python
    def read_json(path: Path) -> dict:
        try:
            v = json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}

    def write_json(path: Path, data: dict) -> None:
        """Via a temp file + atomic rename: a crash or a full disk mid-write
        must never tear the file (torn, it reads back as {} and the next
        save would wipe everything in it)."""
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    def browser_write_ok(request: Request) -> None:
        """Browsers send a cross-site PUT/DELETE after a preflight that this
        app never answers, but a simple no-CORS request could still reach
        us; refuse any write from a page that is not this service's own
        (same rule as the /ws handshake)."""
        if not origin_ok(request.headers.get("origin"), request.headers.get("host")):
            raise HTTPException(403, "writes from another site are refused")

    def known_root(root: str) -> str:
        r = root.upper()
        if r not in roots:
            raise HTTPException(404, f"{root!r} is not a charted symbol")
        return r

    @app.get("/api/layouts")
    async def get_layouts():
        return read_json(layouts_path)

    @app.put("/api/layouts/{name:path}")
    async def put_layout(name: str, request: Request):
        browser_write_ok(request)
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("cells"), list):
            raise HTTPException(400, "a layout is {grid, cells: [...]}")
        all_ = read_json(layouts_path)
        all_[name] = body
        write_json(layouts_path, all_)
        return {"ok": True}

    @app.delete("/api/layouts/{name:path}")
    async def delete_layout(name: str, request: Request):
        browser_write_ok(request)
        all_ = read_json(layouts_path)
        all_.pop(name, None)
        write_json(layouts_path, all_)
        return {"ok": True}

    @app.get("/api/drawings/{root}")
    async def get_drawings(root: str):
        return read_json(drawings_path).get(known_root(root), [])

    @app.put("/api/drawings/{root}")
    async def put_drawings(root: str, request: Request):
        browser_write_ok(request)
        r = known_root(root)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        try:
            clean = check_drawings(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        all_ = read_json(drawings_path)
        all_[r] = clean
        write_json(drawings_path, all_)
        return {"ok": True, "count": len(clean)}
```

Also update the module docstring's first line to mention drawings: `"""The chart service: FastAPI on :8852 — the page, the websocket, layouts, drawings,` (keep the rest of the docstring).

- [ ] **Step 4: Run the new tests, then the whole suite**

Run: `.venv/bin/python -m pytest tests/test_charts_server.py -q` then `.venv/bin/python -m pytest -q`
Expected: all pass (221 + the new tests); the existing layout tests (`test_layouts_roundtrip`, `test_a_failed_layout_write_leaves_the_saved_layouts_intact`) still pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/server.py tests/test_charts_server.py
git commit -m "feat(charts): drawings saved per symbol (GET/PUT /api/drawings/{root}) and Origin-checked HTTP writes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Indicator catalog + the JS test runner

**Files:**
- Create: `homebase/static/charts/catalog.js`
- Create: `tests/js/catalog.test.mjs`
- Create: `tests/test_charts_js.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces `window.HBCatalog` (and `module.exports`) with:
  - data: `CATALOG` (defs `{id, group, name, params: [{key, label, type: 'int'|'num'|'bool'|'choice', min?, max?, step?, choices?: [[value, label]], def}]}`), `GROUPS`, `ROOT_NAMES`, `FAVOURITES` (`[[label, spec]]`), `INTERVAL_GROUPS` (`[[group, [spec...]]]`), `LINE_COLORS`.
  - `uid() -> string`; `def(id) -> def|null`; `clampParams(id, params) -> params`; `instance(id, params?) -> {uid, id, params, visible: true}|null`; `defaults() -> instance[]`.
  - `serverKey(inst) -> string|null`; `serverKeys(list) -> string[]` (deduplicated, first-seen order).
  - `migrate(cfg) -> {root, spec, indicators}`; `migrateLayout(v) -> {grid, cells}`.
  - `label(inst) -> string`; `legendValues(inst, bar, colors, tick) -> [{text, color}]` where `colors = {line, text, up, down, vwap, cum}`.
  - `decimals(tick) -> int`; `fmtPrice(v, tick) -> string`; `fmtCompact(v) -> string`; `fmtSigned(v) -> string`; `change(bar, prev, tick) -> {up, text}`.
  - `parseSpec(spec) -> {kind, n}|null`; `specLabel(spec)`; `longLabel(spec)`; `toSpec(text) -> spec|null`; `rootName(root)`; `filter(query, group) -> def[]`.
- `tests/test_charts_js.py` runs every `tests/js/*.test.mjs` with `node --test` (skipped when `node` is missing). Later tasks add test files there; they are picked up automatically.

- [ ] **Step 1: Write the pytest bridge** — `tests/test_charts_js.py`:

```python
"""The chart page's pure JavaScript (indicator catalog, drawing geometry),
tested with Node's built-in runner. Skipped where Node is not installed."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = Path(__file__).parent / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_chart_page_javascript():
    files = sorted(str(p) for p in JS_TESTS.glob("*.test.mjs"))
    assert files, "no JS tests found"
    r = subprocess.run(["node", "--test", *files], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout + r.stderr)[-6000:]
```

- [ ] **Step 2: Write the failing JS tests** — `tests/js/catalog.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const C = require('../../homebase/static/charts/catalog.js');
const strip = (list) => list.map(({ id, params, visible }) => ({ id, params, visible }));

test('a new chart gets volume, VWAP (ETH), session levels and a 3x footprint', () => {
  assert.deepEqual(strip(C.defaults()), [
    { id: 'volume', params: {}, visible: true },
    { id: 'vwap', params: { anchor: 'eth', bands: false }, visible: true },
    { id: 'levels', params: {}, visible: true },
    { id: 'footprint', params: { imbalance: 3 }, visible: true }]);
});

test('every instance gets its own short uid', () => {
  const a = C.instance('ema'), b = C.instance('ema');
  assert.notEqual(a.uid, b.uid);
  assert.ok(a.uid.length >= 1 && a.uid.length <= 40);
  assert.equal(C.instance('nope'), null);
});

test('server keys follow the study wire names and are deduplicated', () => {
  const list = ['vwap', ['vwap', { anchor: 'rth' }], ['ema', { length: 20 }], ['ema', { length: 20 }], 'sma',
    ['vwma', { length: 9 }], 'adx', 'levels', 'cumdelta', 'profile', 'volume', 'delta', 'footprint', 'bigprints']
    .map((x) => (Array.isArray(x) ? C.instance(...x) : C.instance(x)));
  assert.deepEqual(C.serverKeys(list), ['vwap', 'vwap:rth', 'ema:20', 'sma:50', 'vwma:9', 'adx:14', 'levels', 'cumdelta', 'profile']);
  assert.deepEqual(C.serverKeys([]), []);
});

test('params are clamped to their range and type', () => {
  assert.deepEqual(C.clampParams('ema', { length: 0 }), { length: 1 });
  assert.deepEqual(C.clampParams('ema', { length: 5000 }), { length: 1000 });
  assert.deepEqual(C.clampParams('ema', { length: '12.6' }), { length: 13 });
  assert.deepEqual(C.clampParams('ema', { length: 'abc' }), { length: 20 });
  assert.deepEqual(C.clampParams('ema', {}), { length: 20 });
  assert.deepEqual(C.clampParams('footprint', { imbalance: 2.5 }), { imbalance: 2.5 });
  assert.deepEqual(C.clampParams('footprint', { imbalance: -1 }), { imbalance: 0 });
  assert.deepEqual(C.clampParams('bigprints', { min: 0 }), { min: 1 });
  assert.deepEqual(C.clampParams('vwap', { anchor: 'xyz', bands: 'yes' }), { anchor: 'eth', bands: false });
  assert.deepEqual(C.clampParams('vwap', { anchor: 'rth', bands: true, junk: 1 }), { anchor: 'rth', bands: true });
  assert.deepEqual(C.clampParams('volume', { any: 1 }), {});
});

test('a Build-1 chart (st form) migrates field by field', () => {
  const st = { vwap: true, vwapAnchor: 'rth', vwapBands: true, ema1: 9, ema2: 21, sma: 50, vwma: 20, levels: true,
    volume: true, delta: true, cumdelta: true, adx: 14, footprint: true, imbalance: 4, profile: true, bigMin: 30 };
  const m = C.migrate({ root: 'es', spec: 'tick:1000', st });
  assert.equal(m.root, 'ES');
  assert.equal(m.spec, 'tick:1000');
  assert.deepEqual(strip(m.indicators), [
    { id: 'vwap', params: { anchor: 'rth', bands: true }, visible: true },
    { id: 'ema', params: { length: 9 }, visible: true },
    { id: 'ema', params: { length: 21 }, visible: true },
    { id: 'sma', params: { length: 50 }, visible: true },
    { id: 'vwma', params: { length: 20 }, visible: true },
    { id: 'levels', params: {}, visible: true },
    { id: 'volume', params: {}, visible: true },
    { id: 'delta', params: {}, visible: true },
    { id: 'cumdelta', params: {}, visible: true },
    { id: 'adx', params: { length: 14 }, visible: true },
    { id: 'footprint', params: { imbalance: 4 }, visible: true },
    { id: 'profile', params: {}, visible: true },
    { id: 'bigprints', params: { min: 30 }, visible: true }]);
});

test('an empty Build-1 st means the Build-1 defaults', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', st: {} });
  assert.deepEqual(m.indicators.map((x) => x.id), ['vwap', 'levels', 'volume', 'footprint']);
});

test('switched-off Build-1 studies are dropped', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', st: { vwap: false, levels: false, volume: false, footprint: false } });
  assert.deepEqual(m.indicators, []);
});

test('new-form configs are sanitised: unknown ids dropped, params clamped, uid and visible kept', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:300', indicators: [
    { uid: 'keep', id: 'ema', params: { length: 0 }, visible: false }, { uid: 'x', id: 'nope' }, null] });
  assert.deepEqual(m.indicators, [{ uid: 'keep', id: 'ema', params: { length: 1 }, visible: false }]);
  const fresh = C.migrate({ root: 'NQ', spec: 'time:60', indicators: [{ id: 'sma' }] }).indicators[0];
  assert.ok(fresh.uid);
  assert.equal(fresh.visible, true);
});

test('garbage configs become a default NQ 1m chart', () => {
  const m = C.migrate(null);
  assert.equal(m.root, 'NQ');
  assert.equal(m.spec, 'time:60');
  assert.equal(m.indicators.length, 4);
});

test('layouts migrate every cell and keep only known grids', () => {
  const l = C.migrateLayout({ grid: 3, cells: [{ root: 'NQ', spec: 'time:60', st: {} }] });
  assert.equal(l.grid, 4);
  assert.equal(l.cells.length, 1);
  assert.equal(l.cells[0].indicators[0].id, 'vwap');
  assert.equal(C.migrateLayout({ grid: 6, cells: [] }).grid, 6);
  assert.deepEqual(C.migrateLayout(undefined), { grid: 4, cells: [] });
});

test('legend labels', () => {
  assert.equal(C.label(C.instance('ema', { length: 20 })), 'EMA 20');
  assert.equal(C.label(C.instance('sma')), 'SMA 50');
  assert.equal(C.label(C.instance('vwap')), 'VWAP');
  assert.equal(C.label(C.instance('vwap', { anchor: 'rth' })), 'VWAP RTH');
  assert.equal(C.label(C.instance('adx')), 'ADX 14');
  assert.equal(C.label(C.instance('footprint')), 'Footprint 3×');
  assert.equal(C.label(C.instance('footprint', { imbalance: 0 })), 'Footprint');
  assert.equal(C.label(C.instance('bigprints')), 'Big prints ≥25');
  assert.equal(C.label(C.instance('cumdelta')), 'Cumulative delta');
  assert.equal(C.label(C.instance('levels')), 'Session levels');
});

test('legend values per indicator', () => {
  const colors = { line: '#2962FF', text: '#0F0F0F', up: '#089981', down: '#F23645', vwap: '#9C27B0', cum: '#FF6D00' };
  const bar = { sv: { 'ema:20': 30900.5, vwap: { vwap: 30901.25, sd: 3 }, 'adx:14': { adx: 25.123, pdi: 30, mdi: null }, cumdelta: -1500 } };
  assert.deepEqual(C.legendValues(C.instance('ema'), bar, colors, 0.25), [{ text: '30,900.50', color: '#2962FF' }]);
  assert.deepEqual(C.legendValues(C.instance('vwap'), bar, colors, 0.25), [{ text: '30,901.25', color: '#9C27B0' }]);
  assert.deepEqual(C.legendValues(C.instance('adx'), bar, colors, 0.25),
    [{ text: '25.12', color: '#0F0F0F' }, { text: '30.00', color: '#089981' }, { text: '—', color: '#F23645' }]);
  assert.deepEqual(C.legendValues(C.instance('cumdelta'), bar, colors, 0.25), [{ text: '-1.50K', color: '#FF6D00' }]);
  assert.deepEqual(C.legendValues(C.instance('sma'), bar, colors, 0.25), [{ text: '—', color: '#2962FF' }]);
  for (const id of ['volume', 'delta', 'levels', 'footprint', 'profile', 'bigprints']) {
    assert.deepEqual(C.legendValues(C.instance(id), bar, colors, 0.25), [], id);
  }
});

test('prices use the tick size decimals with thousands separators', () => {
  assert.equal(C.decimals(0.25), 2);
  assert.equal(C.decimals(0.1), 1);
  assert.equal(C.decimals(0.005), 3);
  assert.equal(C.decimals(1), 0);
  assert.equal(C.decimals(0.015625), 6);
  assert.equal(C.fmtPrice(30919.25, 0.25), '30,919.25');
  assert.equal(C.fmtPrice(2650.3, 0.1), '2,650.3');
  assert.equal(C.fmtPrice(null, 0.25), '—');
  assert.equal(C.fmtPrice(NaN, 0.25), '—');
});

test('volumes are compact and deltas signed', () => {
  assert.equal(C.fmtCompact(950), '950');
  assert.equal(C.fmtCompact(1234), '1.23K');
  assert.equal(C.fmtCompact(4560000), '4.56M');
  assert.equal(C.fmtCompact(-12346), '-12.35K');
  assert.equal(C.fmtCompact(999994), '999.99K');
  assert.equal(C.fmtCompact(999995), '1.00M');
  assert.equal(C.fmtSigned(62), '+62');
  assert.equal(C.fmtSigned(-62), '-62');
  assert.equal(C.fmtSigned(0), '0');
  assert.equal(C.fmtSigned(null), '—');
});

test('change is against the previous close, else the open', () => {
  assert.deepEqual(C.change({ o: 30918, c: 30919.25 }, { c: 30916.5 }, 0.25), { up: true, text: '+2.75 (+0.01%)' });
  assert.deepEqual(C.change({ o: 100, c: 99 }, null, 0.25), { up: false, text: '-1.00 (-1.00%)' });
  assert.deepEqual(C.change({ o: 100, c: 100 }, { c: 100 }, 0.25), { up: true, text: '0.00 (0.00%)' });
});

test('interval labels', () => {
  assert.equal(C.specLabel('time:60'), '1m');
  assert.equal(C.specLabel('time:14400'), '4h');
  assert.equal(C.specLabel('time:86400'), '1D');
  assert.equal(C.specLabel('time:90'), '90s');
  assert.equal(C.specLabel('tick:1000'), '1000T');
  assert.equal(C.specLabel('volume:2000'), '2000V');
  assert.equal(C.specLabel('range:10'), '10R');
  assert.equal(C.specLabel('weird'), 'weird');
  assert.equal(C.longLabel('time:5'), '5 seconds');
  assert.equal(C.longLabel('time:60'), '1 minute');
  assert.equal(C.longLabel('time:14400'), '4 hours');
  assert.equal(C.longLabel('time:86400'), '1 day');
  assert.equal(C.longLabel('tick:500'), '500 ticks');
  assert.equal(C.longLabel('volume:2000'), '2,000 volume');
  assert.equal(C.longLabel('range:10'), '10 range');
});

test('the interval menus only offer the server timeframes', () => {
  const all = C.INTERVAL_GROUPS.flatMap(([, specs]) => specs);
  assert.deepEqual(all, ['time:5', 'time:15', 'time:30', 'time:60', 'time:120', 'time:180', 'time:300', 'time:600',
    'time:900', 'time:1800', 'time:3600', 'time:14400', 'time:86400', 'tick:500', 'tick:1000', 'volume:2000', 'range:10', 'range:20']);
  assert.deepEqual(C.FAVOURITES, [['1m', 'time:60'], ['5m', 'time:300'], ['15m', 'time:900'], ['1h', 'time:3600'], ['4h', 'time:14400'], ['D', 'time:86400']]);
});

test('custom interval text becomes a bar spec', () => {
  for (const [t, s] of [['45s', 'time:45'], ['2m', 'time:120'], ['4h', 'time:14400'], ['1D', 'time:86400'], ['750T', 'tick:750'],
    ['3000v', 'volume:3000'], ['8R', 'range:8'], ['tick:750', 'tick:750'], [' TIME:30 ', 'time:30']]) {
    assert.equal(C.toSpec(t), s, t);
  }
  for (const t of ['', 'abc', '0m', 'time:0', '5x', 'tick:', '1.5m', null]) assert.equal(C.toSpec(t), null, String(t));
});

test('root names', () => {
  assert.equal(C.rootName('NQ'), 'E-mini Nasdaq-100');
  assert.equal(C.rootName('HG'), 'Copper');
  assert.equal(C.rootName('ZZ'), '');
});

test('dialog filtering by name and group', () => {
  assert.deepEqual(C.filter('', 'Moving averages').map((d) => d.id), ['ema', 'sma', 'vwma']);
  assert.deepEqual(C.filter('delta').map((d) => d.id), ['delta', 'cumdelta']);
  assert.deepEqual(C.filter('ORDER').map((d) => d.id), ['footprint', 'profile', 'delta', 'cumdelta', 'bigprints']);
  assert.deepEqual(C.filter('zzz'), []);
  assert.equal(C.filter('').length, C.CATALOG.length);
  assert.deepEqual(C.GROUPS, ['All', 'VWAP', 'Moving averages', 'Trend', 'Levels', 'Volume', 'Order flow']);
});
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_js.py -q`
Expected: FAIL — Node reports `Cannot find module '../../homebase/static/charts/catalog.js'`.

- [ ] **Step 4: Implement** `homebase/static/charts/catalog.js`:

```js
/* Homebase Charts — the indicator catalog and the page's pure helpers:
   indicator instances and their server study keys, migration of Build-1
   saved charts, legend and number formatting, interval labels. No DOM and
   no browser globals: the Node tests load this file directly. */
(function () {
'use strict';

const LINE_COLORS = ['#2962FF', '#FF6D00', '#9C27B0', '#00897B', '#E91E63'];
const ROOT_NAMES = { NQ: 'E-mini Nasdaq-100', ES: 'E-mini S&P 500', YM: 'E-mini Dow', RTY: 'E-mini Russell 2000',
  GC: 'Gold', SI: 'Silver', CL: 'Crude Oil', ZN: '10-Year T-Note', NG: 'Natural Gas', HG: 'Copper' };
const GROUPS = ['All', 'VWAP', 'Moving averages', 'Trend', 'Levels', 'Volume', 'Order flow'];
const LENGTH = (def) => ({ key: 'length', label: 'Length', type: 'int', min: 1, max: 1000, def });
const CATALOG = [
  { id: 'volume', group: 'Volume', name: 'Volume', params: [] },
  { id: 'vwap', group: 'VWAP', name: 'VWAP', params: [
    { key: 'anchor', label: 'Anchor', type: 'choice', choices: [['eth', 'ETH'], ['rth', 'RTH']], def: 'eth' },
    { key: 'bands', label: 'Bands (1σ and 2σ)', type: 'bool', def: false }] },
  { id: 'ema', group: 'Moving averages', name: 'EMA', params: [LENGTH(20)] },
  { id: 'sma', group: 'Moving averages', name: 'SMA', params: [LENGTH(50)] },
  { id: 'vwma', group: 'Moving averages', name: 'VWMA', params: [LENGTH(20)] },
  { id: 'adx', group: 'Trend', name: 'ADX / DMI', params: [LENGTH(14)] },
  { id: 'levels', group: 'Levels', name: 'Session levels', params: [] },
  { id: 'footprint', group: 'Order flow', name: 'Footprint', params: [
    { key: 'imbalance', label: 'Imbalance ratio', type: 'num', min: 0, max: 20, step: 0.5, def: 3 }] },
  { id: 'profile', group: 'Order flow', name: 'Volume profile', params: [] },
  { id: 'delta', group: 'Order flow', name: 'Delta', params: [] },
  { id: 'cumdelta', group: 'Order flow', name: 'Cumulative delta', params: [] },
  { id: 'bigprints', group: 'Order flow', name: 'Big prints', params: [
    { key: 'min', label: 'Minimum size', type: 'int', min: 1, max: 100000, def: 25 }] },
];
const BY_ID = Object.fromEntries(CATALOG.map((d) => [d.id, d]));
const FAVOURITES = [['1m', 'time:60'], ['5m', 'time:300'], ['15m', 'time:900'], ['1h', 'time:3600'], ['4h', 'time:14400'], ['D', 'time:86400']];
const INTERVAL_GROUPS = [
  ['Seconds', ['time:5', 'time:15', 'time:30']],
  ['Minutes', ['time:60', 'time:120', 'time:180', 'time:300', 'time:600', 'time:900', 'time:1800']],
  ['Hours', ['time:3600', 'time:14400']],
  ['Days', ['time:86400']],
  ['Ticks', ['tick:500', 'tick:1000']],
  ['Volume', ['volume:2000']],
  ['Range', ['range:10', 'range:20']],
];
// Build 1's per-chart study defaults: a saved `st` is read on top of these.
const ST0 = { vwap: true, vwapAnchor: 'eth', vwapBands: false, ema1: 0, ema2: 0, sma: 0, vwma: 0, levels: true,
  volume: true, delta: false, cumdelta: false, adx: 0, footprint: true, imbalance: 3, profile: false, bigMin: 0 };
const UNITS = [[86400, 'D', 'day'], [3600, 'h', 'hour'], [60, 'm', 'minute'], [1, 's', 'second']];

let seq = 0;
function uid() { return 'i' + Date.now().toString(36) + (seq++).toString(36) + Math.random().toString(36).slice(2, 6); }

function def(id) { return BY_ID[id] || null; }

function clampParams(id, params) {
  const d = def(id), src = params && typeof params === 'object' ? params : {}, out = {};
  if (!d) return out;
  for (const p of d.params) {
    const v = src[p.key];
    if (p.type === 'bool') out[p.key] = typeof v === 'boolean' ? v : p.def;
    else if (p.type === 'choice') out[p.key] = p.choices.some(([c]) => c === v) ? v : p.def;
    else {
      let n = v === null || v === '' || typeof v === 'boolean' ? NaN : Number(v);
      if (!Number.isFinite(n)) n = p.def;
      if (p.type === 'int') n = Math.round(n);
      out[p.key] = Math.min(p.max, Math.max(p.min, n));
    }
  }
  return out;
}

function instance(id, params) {
  return def(id) ? { uid: uid(), id, params: clampParams(id, params), visible: true } : null;
}

function defaults() { return [instance('volume'), instance('vwap'), instance('levels'), instance('footprint')]; }

function serverKey(inst) {
  const p = inst.params || {};
  switch (inst.id) {
    case 'vwap': return p.anchor === 'rth' ? 'vwap:rth' : 'vwap';
    case 'ema': case 'sma': case 'vwma': case 'adx': return `${inst.id}:${p.length}`;
    case 'levels': case 'cumdelta': case 'profile': return inst.id;
    default: return null;
  }
}

function serverKeys(list) { return [...new Set((list || []).map(serverKey).filter(Boolean))]; }

/* A saved chart config of any vintage as {root, spec, indicators}. */
function migrate(cfg) {
  const c = cfg && typeof cfg === 'object' ? cfg : {};
  const root = typeof c.root === 'string' && c.root ? c.root.toUpperCase() : 'NQ';
  const spec = typeof c.spec === 'string' && c.spec ? c.spec : 'time:60';
  if (Array.isArray(c.indicators)) {
    const indicators = c.indicators.filter((x) => x && def(x.id)).map((x) => ({
      uid: typeof x.uid === 'string' && x.uid ? x.uid : uid(), id: x.id,
      params: clampParams(x.id, x.params), visible: x.visible !== false }));
    return { root, spec, indicators };
  }
  if (!c.st || typeof c.st !== 'object') return { root, spec, indicators: defaults() };
  const st = { ...ST0, ...c.st }, out = [];
  const add = (id, params) => out.push(instance(id, params));
  if (st.vwap) add('vwap', { anchor: st.vwapAnchor, bands: !!st.vwapBands });
  for (const f of ['ema1', 'ema2']) if (+st[f] > 0) add('ema', { length: +st[f] });
  if (+st.sma > 0) add('sma', { length: +st.sma });
  if (+st.vwma > 0) add('vwma', { length: +st.vwma });
  if (st.levels) add('levels');
  if (st.volume) add('volume');
  if (st.delta) add('delta');
  if (st.cumdelta) add('cumdelta');
  if (+st.adx > 0) add('adx', { length: +st.adx });
  if (st.footprint) add('footprint', { imbalance: +st.imbalance });
  if (st.profile) add('profile');
  if (+st.bigMin > 0) add('bigprints', { min: +st.bigMin });
  return { root, spec, indicators: out };
}

function migrateLayout(v) {
  const o = v && typeof v === 'object' ? v : {};
  return { grid: [1, 2, 4, 6].includes(+o.grid) ? +o.grid : 4, cells: (Array.isArray(o.cells) ? o.cells : []).map(migrate) };
}

function label(inst) {
  const d = def(inst.id), p = inst.params || {};
  if (!d) return String(inst.id);
  switch (inst.id) {
    case 'vwap': return p.anchor === 'rth' ? 'VWAP RTH' : 'VWAP';
    case 'ema': case 'sma': case 'vwma': return `${d.name} ${p.length}`;
    case 'adx': return `ADX ${p.length}`;
    case 'footprint': return p.imbalance > 0 ? `Footprint ${p.imbalance}×` : 'Footprint';
    case 'bigprints': return `Big prints ≥${p.min}`;
    default: return d.name;
  }
}

function decimals(tick) {
  if (!(tick > 0)) return 2;
  for (let d = 0; d <= 6; d++) { const x = tick * 10 ** d; if (Math.abs(Math.round(x) - x) < 1e-9) return d; }
  return 6;
}

function fmtPrice(v, tick) {
  if (v == null || !Number.isFinite(v)) return '—';
  const d = decimals(tick);
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

/* 950 · 1.23K · 4.56M (sign kept); inputs are whole contract counts. */
function fmtCompact(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 999995) return s + (a / 1e6).toFixed(2) + 'M';
  if (a >= 999.5) return s + (a / 1e3).toFixed(2) + 'K';
  return s + Math.round(a);
}

function fmtSigned(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  return (v > 0 ? '+' : '') + fmtCompact(v);
}

/* The bar's change against the previous bar's close (its own open for the first bar). */
function change(bar, prev, tick) {
  const base = prev ? prev.c : bar.o, diff = bar.c - base, pct = base ? diff / base * 100 : 0;
  const sign = diff > 0 ? '+' : diff < 0 ? '-' : '';
  return { up: diff >= 0, text: `${sign}${fmtPrice(Math.abs(diff), tick)} (${sign}${Math.abs(pct).toFixed(2)}%)` };
}

/* The values an indicator's legend row shows for one bar, each in its line colour. */
function legendValues(inst, bar, colors, tick) {
  const k = serverKey(inst), v = bar && bar.sv && k ? bar.sv[k] : null;
  const n2 = (x) => (x == null || !Number.isFinite(x) ? '—' : x.toFixed(2));
  switch (inst.id) {
    case 'ema': case 'sma': case 'vwma': return [{ text: fmtPrice(v, tick), color: colors.line }];
    case 'vwap': return [{ text: fmtPrice(v ? v.vwap : null, tick), color: colors.vwap }];
    case 'adx': return [{ text: n2(v && v.adx), color: colors.text }, { text: n2(v && v.pdi), color: colors.up },
      { text: n2(v && v.mdi), color: colors.down }];
    case 'cumdelta': return [{ text: fmtSigned(v), color: colors.cum }];
    default: return [];
  }
}

function parseSpec(spec) {
  const m = /^(time|tick|volume|range):(\d+)$/.exec(String(spec));
  return m && +m[2] > 0 ? { kind: m[1], n: +m[2] } : null;
}

function specLabel(spec) {
  const s = parseSpec(spec);
  if (!s) return String(spec);
  if (s.kind !== 'time') return `${s.n}${{ tick: 'T', volume: 'V', range: 'R' }[s.kind]}`;
  const [sec, unit] = UNITS.find(([u]) => s.n % u === 0);
  return `${s.n / sec}${unit}`;
}

function longLabel(spec) {
  const s = parseSpec(spec);
  if (!s) return String(spec);
  if (s.kind !== 'time') return `${s.n.toLocaleString('en-US')} ${{ tick: 'ticks', volume: 'volume', range: 'range' }[s.kind]}`;
  const [sec, , word] = UNITS.find(([u]) => s.n % u === 0), k = s.n / sec;
  return `${k} ${word}${k === 1 ? '' : 's'}`;
}

/* What the user typed in the custom-interval box as a bar spec, or null:
   "tick:750" as is, or shorthand 45s / 2m / 4h / 1D / 750T / 3000V / 8R. */
function toSpec(text) {
  const t = String(text == null ? '' : text).trim();
  let m = /^(time|tick|volume|range):(\d+)$/i.exec(t);
  if (m) return +m[2] > 0 ? `${m[1].toLowerCase()}:${+m[2]}` : null;
  m = /^(\d+)\s*([smhdtvr])$/i.exec(t);
  if (!m || +m[1] <= 0) return null;
  const n = +m[1], u = m[2].toLowerCase(), mult = { s: 1, m: 60, h: 3600, d: 86400 }[u];
  return mult ? `time:${n * mult}` : `${{ t: 'tick', v: 'volume', r: 'range' }[u]}:${n}`;
}

function rootName(root) { return ROOT_NAMES[root] || ''; }

function filter(query, group = 'All') {
  const q = String(query || '').trim().toLowerCase();
  return CATALOG.filter((d) => (group === 'All' || d.group === group)
    && (!q || d.name.toLowerCase().includes(q) || d.group.toLowerCase().includes(q) || d.id.includes(q)));
}

const api = { CATALOG, GROUPS, ROOT_NAMES, FAVOURITES, INTERVAL_GROUPS, LINE_COLORS, uid, def, clampParams, instance,
  defaults, serverKey, serverKeys, migrate, migrateLayout, label, legendValues, decimals, fmtPrice, fmtCompact,
  fmtSigned, change, parseSpec, specLabel, longLabel, toSpec, rootName, filter };
if (typeof window !== 'undefined') window.HBCatalog = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_charts_js.py -q` (for detail: `node --test tests/js/catalog.test.mjs`)
Expected: PASS. Then the full suite `.venv/bin/python -m pytest -q` passes.

- [ ] **Step 6: Commit**

```bash
git add homebase/static/charts/catalog.js tests/js/catalog.test.mjs tests/test_charts_js.py
git commit -m "feat(charts): indicator catalog (instances, study keys, Build-1 migration, legend formatting) with Node tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Drawing geometry + the per-symbol drawings store (pure)

**Files:**
- Create: `homebase/static/charts/drawings.js`
- Create: `tests/js/drawings.test.mjs`

**Interfaces:**
- Consumes: `HBCatalog.decimals`, `HBCatalog.fmtPrice` (Task 2) — in the page via `window.HBCatalog` (catalog.js loads first), in Node via `require('./catalog.js')`.
- Produces `window.HBDrawings` (and `module.exports`):
  - A drawing is `{id, type: 'trend'|'hline'|'rect', points, color?}`; trend/rect points `[{t, p}, {t, p}]` (`t` = a bar's start, epoch ms; `p` = price on the tick grid); hline `[{p}]`.
  - `ctx` objects: `{bars: [{ms}...ascending], isTime: bool, barMs: number (time bars' length in ms, else 0), coord?: (intLogical) => x|null, tick?: number}`.
  - `barIndexAt(bars, t) -> int` (last bar with `ms <= t`, else -1); `logicalOf(bars, t, isTime, barMs) -> number|null`; `xOfLogical(L, coord) -> x|null`; `timeToX(t, ctx) -> x|null`; `snapTime(L, bars, isTime, barMs) -> ms`; `roundToTick(p, tick) -> number`.
  - `distToSegment(px, py, ax, ay, bx, by) -> number`; `handlePoints(d, geo) -> [[x, y], ...] | null`; `hitTest(d, pt, geo) -> {part: 'handle', index} | {part: 'body'} | null` with `geo = {x: (t) => px|null, y: (p) => px|null, w: paneWidth}`; handle indices: trend 0/1 = its points; rect 0 = (t0,p0), 1 = (t1,p1), 2 = (t0,p1), 3 = (t1,p0); hline 0 = the middle of the pane.
  - `setPoint(d, handleIndex, t, p) -> d'` (new object; for hline only `p` is used); `shiftTime(t, dBars, ctx) -> ms`; `moveDrawing(d, dBars, dPrice, tick, ctx) -> d'`.
  - `fmtDuration(ms) -> string`; `measureLabel(a, b, ctx) -> [line1, line2]` with `a, b = {t, p}` and `ctx.tick`.
  - `newId() -> string` (≤ 40 chars).
  - `class Store({fetchFn = fetch, delay = 300, onError = (root, message) => {}})`: `list(root)`, `ensure(root) -> Promise<bool>` (loads once; false if the load failed), `subscribe(root, fn) -> unsubscribe`, `add(root, d)`, `replace(root, d)`, `remove(root, id)`, `clear(root)`. Every change notifies that root's subscribers immediately and saves the root's whole list with `PUT /api/drawings/{root}` 300 ms after the last change. Saves wait for a successful load and never overwrite drawings the page could not read; edits made before the load finishes are merged with the saved list.
- Task 6 adds the browser half (`Primitive`, `Controller`) to this same file.

- [ ] **Step 1: Write the failing tests** — `tests/js/drawings.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const D = require('../../homebase/static/charts/drawings.js');

const MIN = 60000;
const T0 = 1_790_000_000_000;
const bars = [0, 1, 2, 3, 4].map((i) => ({ ms: T0 + i * MIN }));   // five 1m bars
const coord = (i) => 100 + i * 10;                                // bar i at x = 100 + 10 i
const TIME = { bars, isTime: true, barMs: MIN, coord };
const geo = { x: (t) => D.timeToX(t, TIME), y: (p) => 1000 - p, w: 400 };
const trend = { id: 'a', type: 'trend', points: [{ t: bars[0].ms, p: 900 }, { t: bars[4].ms, p: 860 }] };   // (100,100)-(140,140)
const rect = { id: 'b', type: 'rect', points: [{ t: bars[1].ms, p: 880 }, { t: bars[3].ms, p: 850 }] };     // x 110-130, y 120-150
const hline = { id: 'c', type: 'hline', points: [{ p: 875 }] };                                          // y 125

test('barIndexAt finds the last bar at or before t', () => {
  assert.equal(D.barIndexAt(bars, T0 - 1), -1);
  assert.equal(D.barIndexAt(bars, T0), 0);
  assert.equal(D.barIndexAt(bars, T0 + 90000), 1);
  assert.equal(D.barIndexAt(bars, T0 + 4 * MIN), 4);
  assert.equal(D.barIndexAt(bars, T0 + 99 * MIN), 4);
  assert.equal(D.barIndexAt([], T0), -1);
});

test('logicalOf interpolates between bars, extrapolates time bars, clamps the others', () => {
  assert.equal(D.logicalOf(bars, T0 + 90000, true, MIN), 1.5);
  assert.equal(D.logicalOf(bars, T0 - 2 * MIN, true, MIN), -2);
  assert.equal(D.logicalOf(bars, T0 + 7 * MIN, true, MIN), 7);
  assert.equal(D.logicalOf(bars, T0 - 2 * MIN, false, 0), 0);
  assert.equal(D.logicalOf(bars, T0 + 7 * MIN, false, 0), 4);
  assert.equal(D.logicalOf([], T0, true, MIN), null);
});

test('a point inside a data gap sits proportionally between the two bars', () => {
  const g = [{ ms: 0 }, { ms: 60 }, { ms: 120 }, { ms: 600 }];
  assert.equal(D.logicalOf(g, 360, true, 60), 2.5);
});

test('xOfLogical only ever asks for integer coordinates', () => {
  const asked = [];
  const c = (i) => { asked.push(i); return 100 + i * 10; };
  assert.equal(D.xOfLogical(1.5, c), 115);
  assert.equal(D.xOfLogical(-2, c), 80);
  assert.equal(D.xOfLogical(3, c), 130);
  assert.ok(asked.every(Number.isInteger));
  assert.equal(D.xOfLogical(null, c), null);
  assert.equal(D.xOfLogical(1.5, () => null), null);
});

test('timeToX puts a drawing where its time is on this chart', () => {
  assert.equal(D.timeToX(T0 + 90000, TIME), 115);
  assert.equal(D.timeToX(T0 + 6 * MIN, TIME), 160);
  assert.equal(D.timeToX(T0 - MIN, TIME), 90);
  assert.equal(D.timeToX(T0 + 6 * MIN, { ...TIME, isTime: false, barMs: 0 }), 140);
});

test('snapTime picks the nearest bar; beyond the data, whole bar steps (time bars only)', () => {
  assert.equal(D.snapTime(1.4, bars, true, MIN), bars[1].ms);
  assert.equal(D.snapTime(1.6, bars, true, MIN), bars[2].ms);
  assert.equal(D.snapTime(6.2, bars, true, MIN), T0 + 6 * MIN);
  assert.equal(D.snapTime(-1.8, bars, true, MIN), T0 - 2 * MIN);
  assert.equal(D.snapTime(6.2, bars, false, 0), bars[4].ms);
  assert.equal(D.snapTime(-3, bars, false, 0), bars[0].ms);
});

test('prices round to the tick', () => {
  assert.equal(D.roundToTick(30900.13, 0.25), 30900.25);
  assert.equal(D.roundToTick(30900.12, 0.25), 30900);
  assert.equal(D.roundToTick(2650.34, 0.1), 2650.3);
  assert.equal(D.roundToTick(1.23456, 0.005), 1.235);
});

test('distance from a point to a segment', () => {
  assert.equal(D.distToSegment(5, 5, 0, 0, 10, 0), 5);
  assert.equal(D.distToSegment(13, 4, 0, 0, 10, 0), 5);
  assert.equal(D.distToSegment(3, 4, 0, 0, 0, 0), 5);
});

test('hitTest: a trend line grabs its handles first, then its segment', () => {
  assert.deepEqual(D.hitTest(trend, { x: 101, y: 102 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(D.hitTest(trend, { x: 139, y: 141 }, geo), { part: 'handle', index: 1 });
  assert.deepEqual(D.hitTest(trend, { x: 122, y: 118 }, geo), { part: 'body' });
  assert.equal(D.hitTest(trend, { x: 130, y: 100 }, geo), null);
  assert.equal(D.hitTest(trend, { x: 170, y: 170 }, geo), null);
});

test('hitTest: rectangle corners are handles 0-3 and its inside is the body', () => {
  assert.deepEqual(D.hitTest(rect, { x: 110, y: 120 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(D.hitTest(rect, { x: 130, y: 150 }, geo), { part: 'handle', index: 1 });
  assert.deepEqual(D.hitTest(rect, { x: 110, y: 150 }, geo), { part: 'handle', index: 2 });
  assert.deepEqual(D.hitTest(rect, { x: 130, y: 120 }, geo), { part: 'handle', index: 3 });
  assert.deepEqual(D.hitTest(rect, { x: 120, y: 135 }, geo), { part: 'body' });
  assert.equal(D.hitTest(rect, { x: 160, y: 135 }, geo), null);
});

test('hitTest: a horizontal line is hit anywhere along it; its handle sits mid-pane', () => {
  assert.deepEqual(D.hitTest(hline, { x: 200, y: 126 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(D.hitTest(hline, { x: 20, y: 128 }, geo), { part: 'body' });
  assert.equal(D.hitTest(hline, { x: 20, y: 140 }, geo), null);
});

test('hitTest misses a drawing whose points cannot be placed', () => {
  assert.equal(D.hitTest(trend, { x: 101, y: 102 }, { ...geo, x: () => null }), null);
});

test('handle positions: trend ends, rectangle corners, mid-pane for a horizontal line', () => {
  assert.deepEqual(D.handlePoints(trend, geo), [[100, 100], [140, 140]]);
  assert.deepEqual(D.handlePoints(rect, geo), [[110, 120], [130, 150], [110, 150], [130, 120]]);
  assert.deepEqual(D.handlePoints(hline, geo), [[200, 125]]);
  assert.equal(D.handlePoints(hline, { ...geo, y: () => null }), null);
});

test('dragging a handle moves that point; rectangle side corners mix the two points', () => {
  assert.deepEqual(D.setPoint(trend, 1, 5, 7).points, [trend.points[0], { t: 5, p: 7 }]);
  assert.deepEqual(D.setPoint(trend, 0, 5, 7).points, [{ t: 5, p: 7 }, trend.points[1]]);
  assert.deepEqual(D.setPoint(rect, 0, 5, 7).points, [{ t: 5, p: 7 }, rect.points[1]]);
  assert.deepEqual(D.setPoint(rect, 2, 5, 7).points, [{ t: 5, p: 880 }, { t: bars[3].ms, p: 7 }]);
  assert.deepEqual(D.setPoint(rect, 3, 5, 7).points, [{ t: bars[1].ms, p: 7 }, { t: 5, p: 850 }]);
  assert.deepEqual(D.setPoint(hline, 0, 5, 7), { id: 'c', type: 'hline', points: [{ p: 7 }] });
  assert.deepEqual(trend.points[1], { t: bars[4].ms, p: 860 });
});

test('moving shifts every point by whole bars and by price, on the tick grid', () => {
  assert.deepEqual(D.moveDrawing(trend, 2, 1.1, 0.25, TIME).points, [{ t: bars[2].ms, p: 901 }, { t: T0 + 6 * MIN, p: 861 }]);
  assert.deepEqual(D.moveDrawing(hline, 3, -2.3, 0.25, TIME).points, [{ p: 872.75 }]);
  const between = { ...trend, points: [{ t: T0 + 30000, p: 900 }, trend.points[1]] };
  assert.equal(D.moveDrawing(between, 0, 1, 0.25, TIME).points[0].t, T0 + 30000);   // a price-only move keeps t
  assert.equal(D.shiftTime(T0 + 30000, 1, TIME), bars[2].ms);
});

test('durations read like a clock', () => {
  assert.equal(D.fmtDuration(0), '0s');
  assert.equal(D.fmtDuration(45000), '45s');
  assert.equal(D.fmtDuration(8 * MIN), '8m');
  assert.equal(D.fmtDuration(90000), '1m 30s');
  assert.equal(D.fmtDuration(65 * MIN), '1h 5m');
  assert.equal(D.fmtDuration(120 * MIN), '2h');
  assert.equal(D.fmtDuration(27 * 60 * MIN), '1d 3h');
  assert.equal(D.fmtDuration(-8 * MIN), '8m');
});

test('measure label: price change, ticks, bars and time', () => {
  const ctx = { ...TIME, tick: 0.25 };
  assert.deepEqual(D.measureLabel({ t: bars[0].ms, p: 30900 }, { t: bars[4].ms, p: 30912.5 }, ctx),
    ['+12.50 (+0.04%) · 50 ticks', '4 bars · 4m']);
  assert.deepEqual(D.measureLabel({ t: bars[3].ms, p: 100 }, { t: bars[2].ms, p: 99.75 }, ctx),
    ['-0.25 (-0.25%) · 1 tick', '1 bar · 1m']);
});

test('new ids are short and unique', () => {
  const a = D.newId(), b = D.newId();
  assert.notEqual(a, b);
  assert.ok(a.length >= 1 && a.length <= 40);
});

/* ---- the store ---- */
const H1 = { id: 'h1', type: 'hline', points: [{ p: 1 }] };
const H2 = { id: 'h2', type: 'hline', points: [{ p: 2 }] };
const flush = () => new Promise((r) => setImmediate(r));

function fakeFetch(answer) {
  const calls = [];
  const f = async (url, opts = {}) => {
    const method = opts.method || 'GET';
    calls.push({ url, method, body: opts.body ? JSON.parse(opts.body) : undefined });
    const r = answer(url, method) || { status: 200, body: [] };
    return { ok: r.status < 400, status: r.status, json: async () => r.body };
  };
  f.calls = calls;
  return f;
}

test('the store loads a symbol once and tells its subscribers', async () => {
  const f = fakeFetch(() => ({ status: 200, body: [H1] }));
  const s = new D.Store({ fetchFn: f });
  let told = 0;
  s.subscribe('NQ', () => { told += 1; });
  const [a, b] = await Promise.all([s.ensure('NQ'), s.ensure('NQ')]);
  assert.equal(a, true);
  assert.equal(b, true);
  assert.deepEqual(s.list('NQ'), [H1]);
  assert.deepEqual(f.calls.map((c) => [c.method, c.url]), [['GET', '/api/drawings/NQ']]);
  assert.ok(told >= 1);
  assert.deepEqual(s.list('ES'), []);
});

test('edits reach subscribers at once and are saved once, 300 ms after the last', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const f = fakeFetch(() => null);
  const s = new D.Store({ fetchFn: f });
  await s.ensure('NQ');
  const seen = [];
  const off = s.subscribe('NQ', () => seen.push(s.list('NQ').map((d) => d.id)));
  s.add('NQ', H1);
  s.add('NQ', H2);
  s.replace('NQ', { ...H2, points: [{ p: 3 }] });
  s.remove('NQ', 'h1');
  assert.deepEqual(seen, [['h1'], ['h1', 'h2'], ['h1', 'h2'], ['h2']]);
  t.mock.timers.tick(299);
  await flush();
  assert.equal(f.calls.filter((c) => c.method === 'PUT').length, 0);
  t.mock.timers.tick(1);
  await flush();
  const puts = f.calls.filter((c) => c.method === 'PUT');
  assert.equal(puts.length, 1);
  assert.equal(puts[0].url, '/api/drawings/NQ');
  assert.deepEqual(puts[0].body, [{ ...H2, points: [{ p: 3 }] }]);
  off();
  s.clear('NQ');
  assert.equal(seen.length, 4);
});

test('drawings added before the first load finishes are merged with the saved ones', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let release;
  const gate = new Promise((r) => { release = r; });
  const calls = [];
  const f = async (url, opts = {}) => {
    calls.push({ method: opts.method || 'GET', body: opts.body && JSON.parse(opts.body) });
    if (!opts.method) await gate;
    return { ok: true, status: 200, json: async () => (opts.method ? { ok: true } : [H1]) };
  };
  const s = new D.Store({ fetchFn: f });
  const loading = s.ensure('NQ');
  s.add('NQ', H2);
  release();
  await loading;
  assert.deepEqual(s.list('NQ').map((d) => d.id), ['h1', 'h2']);
  t.mock.timers.tick(300);
  await flush();
  assert.deepEqual(calls.filter((c) => c.method === 'PUT').at(-1).body.map((d) => d.id), ['h1', 'h2']);
});

test('a failed load is reported, retried before saving, and never overwritten', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const errors = [];
  const f = fakeFetch(() => ({ status: 500, body: {} }));
  const s = new D.Store({ fetchFn: f, onError: (root, msg) => errors.push([root, msg]) });
  assert.equal(await s.ensure('NQ'), false);
  s.add('NQ', H1);
  t.mock.timers.tick(300);
  await flush();
  await flush();
  assert.deepEqual(s.list('NQ'), [H1]);
  assert.deepEqual(f.calls.map((c) => c.method), ['GET', 'GET']);
  assert.deepEqual(errors, [['NQ', 'load failed (500)'], ['NQ', 'load failed (500)']]);
});

test('a failed save is reported and the drawings stay on screen', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const errors = [];
  const f = fakeFetch((url, method) => (method === 'PUT' ? { status: 400, body: { detail: 'type: trend, hline or rect' } } : null));
  const s = new D.Store({ fetchFn: f, onError: (root, msg) => errors.push([root, msg]) });
  await s.ensure('NQ');
  s.add('NQ', H1);
  t.mock.timers.tick(300);
  await flush();
  await flush();
  assert.deepEqual(s.list('NQ'), [H1]);
  assert.deepEqual(errors, [['NQ', 'save failed (400): type: trend, hline or rect']]);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/drawings.test.mjs`
Expected: FAIL — `Cannot find module '../../homebase/static/charts/drawings.js'`.

- [ ] **Step 3: Implement** `homebase/static/charts/drawings.js`:

```js
/* Homebase Charts — drawing tools. This half is pure: geometry that maps a
   drawing's (time, price) points through the chart's bars to pixels (so a
   drawing stays on its times across timeframes, like TradingView), hit
   tests, tick rounding, the measure text, and the per-symbol store that
   keeps drawings on the server. No browser globals at load time: the Node
   tests load this file directly. The canvas primitive and the pointer
   controller come after it (Task 6). */
(function () {
'use strict';
const Cat = (typeof window !== 'undefined' && window.HBCatalog) || (typeof require === 'function' ? require('./catalog.js') : null);
const HANDLE_TOL = 6;   // px: a handle this close is grabbed
const LINE_TOL = 5;     // px: a line this close is hit

/* The index of the last bar starting at or before t (bars ascending by ms), else -1. */
function barIndexAt(bars, t) {
  let lo = 0, hi = bars.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].ms <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

/* Time t as a fractional bar index. Between two bars it is interpolated by
   time; before the first / after the last bar, time bars extrapolate by
   their length and other bar types (tick, volume, range) clamp. */
function logicalOf(bars, t, isTime, barMs) {
  const n = bars.length;
  if (!n) return null;
  const i = barIndexAt(bars, t), ext = isTime && barMs > 0;
  if (i < 0) return ext ? (t - bars[0].ms) / barMs : 0;
  if (i === n - 1) return ext ? n - 1 + (t - bars[n - 1].ms) / barMs : n - 1;
  return i + (t - bars[i].ms) / (bars[i + 1].ms - bars[i].ms);
}

/* The x of a fractional logical from the two INTEGER bar coordinates around
   it: Lightweight Charts v5 answers 0 for a fractional logical. */
function xOfLogical(L, coord) {
  if (L == null || !Number.isFinite(L)) return null;
  const i = Math.floor(L), f = L - i, a = coord(i);
  if (a == null) return null;
  if (f === 0) return a;
  const b = coord(i + 1);
  return b == null ? a : a + f * (b - a);
}

function timeToX(t, ctx) { return xOfLogical(logicalOf(ctx.bars, t, ctx.isTime, ctx.barMs), ctx.coord); }

/* The start time of the bar nearest logical L; beyond the loaded bars, time
   bars step by their length and other bar types clamp to the first/last bar. */
function snapTime(L, bars, isTime, barMs) {
  const n = bars.length, i = Math.round(L);
  if (i < 0) return isTime && barMs > 0 ? bars[0].ms + i * barMs : bars[0].ms;
  if (i > n - 1) return isTime && barMs > 0 ? bars[n - 1].ms + (i - (n - 1)) * barMs : bars[n - 1].ms;
  return bars[i].ms;
}

function roundToTick(p, tick) {
  if (!(tick > 0)) return p;
  return +(Math.round(p / tick) * tick).toFixed(Cat.decimals(tick));
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const u = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - (ax + u * dx), py - (ay + u * dy));
}

/* Pixel positions [[x, y], ...] of drawing d's handles, or null when a point
   cannot be placed: trend 0/1 = its points; rect 0 (t0,p0), 1 (t1,p1),
   2 (t0,p1), 3 (t1,p0); hline 0 = the middle of the pane. */
function handlePoints(d, geo) {
  const P = d.points;
  if (d.type === 'hline') {
    const y = geo.y(P[0].p);
    return y == null ? null : [[geo.w / 2, y]];
  }
  const x0 = geo.x(P[0].t), x1 = geo.x(P[1].t), y0 = geo.y(P[0].p), y1 = geo.y(P[1].p);
  if (x0 == null || x1 == null || y0 == null || y1 == null) return null;
  return d.type === 'rect' ? [[x0, y0], [x1, y1], [x0, y1], [x1, y0]] : [[x0, y0], [x1, y1]];
}

/* What of drawing d is under pt: a handle (by index), the body, or nothing. */
function hitTest(d, pt, geo) {
  const hs = handlePoints(d, geo);
  if (!hs) return null;
  for (let i = 0; i < hs.length; i++) {
    if (Math.hypot(pt.x - hs[i][0], pt.y - hs[i][1]) <= HANDLE_TOL) return { part: 'handle', index: i };
  }
  if (d.type === 'hline') return Math.abs(pt.y - hs[0][1]) <= LINE_TOL ? { part: 'body' } : null;
  const [[x0, y0], [x1, y1]] = hs;
  if (d.type === 'trend') return distToSegment(pt.x, pt.y, x0, y0, x1, y1) <= LINE_TOL ? { part: 'body' } : null;
  const inside = pt.x >= Math.min(x0, x1) - LINE_TOL && pt.x <= Math.max(x0, x1) + LINE_TOL
    && pt.y >= Math.min(y0, y1) - LINE_TOL && pt.y <= Math.max(y0, y1) + LINE_TOL;
  return inside ? { part: 'body' } : null;
}

/* d with handle k moved to (t, p); a rectangle's side corners (2, 3) take
   their time from one stored point and their price from the other. */
function setPoint(d, k, t, p) {
  if (d.type === 'hline') return { ...d, points: [{ p }] };
  const [a, b] = d.points;
  let points;
  if (d.type === 'rect') {
    points = [[{ t, p }, b], [a, { t, p }], [{ t, p: a.p }, { t: b.t, p }], [{ t: a.t, p }, { t, p: b.p }]][k];
  } else points = k === 0 ? [{ t, p }, b] : [a, { t, p }];
  return { ...d, points };
}

/* t moved by whole bars; a zero move keeps t exactly (a price-only drag must
   not snap a point that sits between this chart's bars). */
function shiftTime(t, dBars, ctx) {
  if (!dBars) return t;
  const L = logicalOf(ctx.bars, t, ctx.isTime, ctx.barMs);
  return L == null ? t : snapTime(Math.round(L) + dBars, ctx.bars, ctx.isTime, ctx.barMs);
}

function moveDrawing(d, dBars, dPrice, tick, ctx) {
  return { ...d, points: d.points.map((q) => (d.type === 'hline'
    ? { p: roundToTick(q.p + dPrice, tick) }
    : { t: shiftTime(q.t, dBars, ctx), p: roundToTick(q.p + dPrice, tick) })) };
}

function fmtDuration(ms) {
  const s = Math.round(Math.abs(ms) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

/* The measure tool's two lines, e.g. "+12.50 (+0.04%) · 50 ticks" / "8 bars · 8m". */
function measureLabel(a, b, ctx) {
  const diff = b.p - a.p, pct = a.p ? diff / a.p * 100 : 0, sign = diff > 0 ? '+' : diff < 0 ? '-' : '';
  const ticks = Math.round(Math.abs(diff) / ctx.tick);
  const La = logicalOf(ctx.bars, a.t, ctx.isTime, ctx.barMs), Lb = logicalOf(ctx.bars, b.t, ctx.isTime, ctx.barMs);
  const n = La == null || Lb == null ? 0 : Math.abs(Math.round(Lb) - Math.round(La));
  return [`${sign}${Cat.fmtPrice(Math.abs(diff), ctx.tick)} (${sign}${Math.abs(pct).toFixed(2)}%) · ${ticks} tick${ticks === 1 ? '' : 's'}`,
    `${n} bar${n === 1 ? '' : 's'} · ${fmtDuration(b.t - a.t)}`];
}

let seq = 0;
function newId() { return 'd' + Date.now().toString(36) + (seq++).toString(36) + Math.random().toString(36).slice(2, 6); }

/* Drawings per symbol, shared by every chart of that symbol, saved to the
   server as the symbol's whole list, debounced. */
class Store {
  constructor({ fetchFn, delay = 300, onError = () => {} } = {}) {
    this.fetch = fetchFn || ((...a) => fetch(...a));
    this.delay = delay;
    this.onError = onError;
    this.roots = new Map();
  }

  st(root) {
    let s = this.roots.get(root);
    if (!s) { s = { list: [], loaded: false, loading: null, timer: null, subs: new Set() }; this.roots.set(root, s); }
    return s;
  }

  url(root) { return `/api/drawings/${encodeURIComponent(root)}`; }

  list(root) { return this.st(root).list; }

  subscribe(root, fn) { const s = this.st(root); s.subs.add(fn); return () => s.subs.delete(fn); }

  emit(root) { for (const fn of [...this.st(root).subs]) fn(); }

  /* Load the symbol's saved drawings once. Resolves true when loaded, false
     when the load failed (reported; the next ensure() tries again). */
  ensure(root) {
    const s = this.st(root);
    if (s.loaded) return Promise.resolve(true);
    if (!s.loading) s.loading = this.load(root).finally(() => { s.loading = null; });
    return s.loading;
  }

  async load(root) {
    const s = this.st(root);
    try {
      const r = await this.fetch(this.url(root));
      if (!r.ok) throw new Error(`load failed (${r.status})`);
      const saved = await r.json(), mine = new Set(s.list.map((d) => d.id));
      s.list = [...(Array.isArray(saved) ? saved : []).filter((d) => d && !mine.has(d.id)), ...s.list];
      s.loaded = true;
      this.emit(root);
      return true;
    } catch (e) {
      this.onError(root, e && e.message ? e.message : String(e));
      return false;
    }
  }

  add(root, d) { this.set(root, [...this.list(root), d]); }
  replace(root, d) { this.set(root, this.list(root).map((x) => (x.id === d.id ? d : x))); }
  remove(root, id) { this.set(root, this.list(root).filter((x) => x.id !== id)); }
  clear(root) { this.set(root, []); }

  set(root, list) {
    const s = this.st(root);
    s.list = list;
    this.emit(root);
    clearTimeout(s.timer);
    s.timer = setTimeout(() => { s.timer = null; this.save(root); }, this.delay);
  }

  async save(root) {
    if (!(await this.ensure(root))) return;   // never overwrite drawings we could not read
    try {
      const r = await this.fetch(this.url(root), { method: 'PUT', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(this.list(root)) });
      if (!r.ok) {
        let detail = '';
        try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
        throw new Error(`save failed (${r.status})${detail ? ': ' + detail : ''}`);
      }
    } catch (e) {
      this.onError(root, e && e.message ? e.message : String(e));
    }
  }
}

const api = { barIndexAt, logicalOf, xOfLogical, timeToX, snapTime, roundToTick, distToSegment, handlePoints, hitTest,
  setPoint, shiftTime, moveDrawing, fmtDuration, measureLabel, newId, Store, HANDLE_TOL, LINE_TOL };
if (typeof window !== 'undefined') window.HBDrawings = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/drawings.test.mjs` then `.venv/bin/python -m pytest -q`
Expected: PASS (both JS files run through `tests/test_charts_js.py`).

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/drawings.js tests/js/drawings.test.mjs
git commit -m "feat(charts): drawing geometry (time<->x across timeframes, hit tests, measure text) and the per-symbol drawings store

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: The new page — shell, styles, icons, one chart panel, toolbar core, bottom bar

**Files:**
- Rewrite: `homebase/static/charts.html`
- Create: `homebase/static/charts/charts.css`
- Create: `homebase/static/charts/icons.js`
- Create: `homebase/static/charts/cell.js`
- Rewrite: `homebase/static/charts/app.js`
- Modify: `homebase/static/charts/primitives.js` (the gap label's colour/font only)

**Interfaces:**
- Consumes: `window.HBCatalog` (Task 2, whole API), `window.HBLayers` (`Footprint`, `Profile`, `Gaps` in `primitives.js`: constructor `(P)`; `Footprint.set(bars, on, ratio, tick)`, `Footprint.onReadableChange`; `Profile.set(profile, tick)`; `Gaps.set(indices)`; palette keys they read: `fpBg fpText up down poc va vaIn gap text2`), `window.LightweightCharts` 5.2.1, the websocket protocol, `GET /api/symbols` → `{roots, timeframes}`.
- Produces:
  - `window.HBIcons` — `{desk, chevron, search, indicators, cursor, trend, hline, rect, measure, trash, eye, eyeOff, gear, x, check, sun, moon}`, each an SVG string with `class="ic"`.
  - `window.HBCell = {Cell, palette, FONT}`. `new Cell(slot, cfg, host)`: `slot` = an empty div in `#grid`; `cfg` = the layout's `{root, spec, indicators}` object (the cell mutates it in place, so the page's layout stays current); `host` = `{id, send(msg) -> bool, onPick(cell), onLoaded(cell), onRefused(cell, tried, text), changed()}` (Tasks 5 and 6 add `onSettings(cell, uid)`, `tool()`, `toolDone()`, `drawings`). Public members used later: `el, box, cfg, id, chart, candles, bars, tick, P, shown ({root, spec} on screen), rows, lines`; methods `subscribe(keepView)`, `update(patch)`, `restyle()`, `setSelected(on)`, `note(text)`, `onHistory(m)`, `onUpdate(m)`, `onError(text)`, `destroy()`, `isTime()`, `barMs()`, `legendRows()`, `legend(i)`, `visible(id)`, `drawLevels()`, `drawMarkers()`, `syncFootprint()`, `syncProfile()`, `teardown()`, `build(view)`.
  - `app.js` page functions later tasks extend: `hostFor(id)`, `renderToolbar()`, `openMenu(anchor, cls)`, `placeMenu()`, `closeMenu()`, `toggleMenu(anchor, fill)`, `menuItem(text, sub, onPick, active)`, `onKey(e)`, `mk(tag, cls, text)`, `icon(name)`, `cur()`, `select(i)`, `buildGrid()`, `saveLast()`, variables `layout`, `cells`, `selected`, `menuEl`, `menuAnchor`; `window.HBCharts` (debug handle).
- Markup for Task 5 (indicators button, grid picker, layout menu, Save) and Task 6 (the rail) is in the shell from this task on, inert until those tasks wire it; `charts.css` is the whole design, including the styles those tasks use.

This task replaces the Build-1 page entirely: no per-chart controls, no `shadcn.css`, one top toolbar acting on the selected chart. Everything the old page did must still work: history + live updates for time/tick/volume/range bars, footprint (with candle bodies hidden while it is readable), volume profile, gap bands, session levels, big-print markers, VWAP bands, EMA/SMA/VWMA, ADX, delta, cumulative delta, the stale-status greying, reconnect, and last-layout persistence (Build-1 saved layouts migrate through `HBCatalog.migrateLayout`).

- [ ] **Step 1: `primitives.js`** — in `Gaps.draw`, replace the label font and colour:

```js
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif'; ctx.textAlign = 'center';
```
and
```js
        ctx.fillStyle = this.P.text2; ctx.fillText('no data', x, 30);
```
Nothing else in `primitives.js` changes (its palette keys are supplied by `HBCell.palette()`).

- [ ] **Step 2: `icons.js`** (the exact strings; Lucide 1.48.0 inner markup fetched from `https://cdn.jsdelivr.net/npm/lucide-static@1.48.0/icons/<name>.svg`; `trend` is our own glyph in the same style):

```js
/* Homebase Charts — the page's icons, inlined SVG strings.
   Lucide (https://lucide.dev), lucide-static@1.48.0: house, chevron-down, search,
   square-function, mouse-pointer-2, git-commit-horizontal, rectangle-horizontal, ruler,
   trash-2, eye, eye-off, settings, x, check, sun, moon.

   ISC License

   Copyright (c) 2026 Lucide Icons and Contributors

   Permission to use, copy, modify, and/or distribute this software for any
   purpose with or without fee is hereby granted, provided that the above
   copyright notice and this permission notice appear in all copies.

   THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
   WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
   MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
   ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
   WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
   ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
   OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

   check, chevron-down, moon, search, trash-2 and x derive from Feather:
   The MIT License (MIT), Copyright (c) 2013-present Cole Bemis.

   `trend` (a segment between two handles) is drawn for this page in the same style. */
(function () {
'use strict';
const svg = (body) => '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
  + `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${body}</svg>`;
window.HBIcons = {
  desk: svg('<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  chevron: svg('<path d="m6 9 6 6 6-6"/>'),
  search: svg('<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>'),
  indicators: svg('<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M9 17c2 0 2.8-1 2.8-2.8V10c0-2 1-3.3 3.2-3"/><path d="M9 11.2h5.7"/>'),
  cursor: svg('<path d="M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.063z"/>'),
  trend: svg('<circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/><path d="M6.5 17.5 17.5 6.5"/>'),
  hline: svg('<circle cx="12" cy="12" r="3"/><line x1="3" x2="9" y1="12" y2="12"/><line x1="15" x2="21" y1="12" y2="12"/>'),
  rect: svg('<rect width="20" height="12" x="2" y="6" rx="2"/>'),
  measure: svg('<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/><path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/>'),
  trash: svg('<path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
  eye: svg('<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>'),
  eyeOff: svg('<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/>'),
  gear: svg('<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/><circle cx="12" cy="12" r="3"/>'),
  x: svg('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'),
  check: svg('<path d="M20 6 9 17l-5-5"/>'),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>'),
  moon: svg('<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"/>'),
};
})();
```

- [ ] **Step 3: `charts.html`** (whole file):

```html
<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Charts · Homebase</title>
<script>
  try { var _t = localStorage.getItem('hb_theme');
    document.documentElement.setAttribute('data-theme', (_t === 'light' || _t === 'dark') ? _t : 'light');
  } catch (_) { document.documentElement.setAttribute('data-theme', 'light'); }
</script>
<link rel="stylesheet" href="/static/charts/charts.css">
</head>
<body>
<header class="toolbar" role="toolbar" aria-label="Chart toolbar">
  <a class="tb-btn" id="tbDesk" href="#" title="Back to the desk"><span class="icw" data-icon="desk"></span><span class="tb-label">Desk</span></a>
  <span class="tb-sep"></span>
  <button class="tb-pill" id="tbSymbol" type="button" aria-haspopup="menu" aria-expanded="false"><span class="icw" data-icon="search"></span><span id="tbSymbolText">NQ</span></button>
  <span class="tb-sep"></span>
  <div class="tb-group" id="tbFavs" role="group" aria-label="Interval"></div>
  <button class="tb-btn tb-icon" id="tbIntervals" type="button" title="More intervals" aria-haspopup="menu" aria-expanded="false"><span class="icw sm" data-icon="chevron"></span></button>
  <span class="tb-sep"></span>
  <button class="tb-btn" id="tbIndicators" type="button" title="Indicators"><span class="icw" data-icon="indicators"></span><span class="tb-label">Indicators</span></button>
  <span class="tb-sep"></span>
  <button class="tb-btn" id="tbGrid" type="button" title="Chart layout" aria-haspopup="menu" aria-expanded="false"><span class="thumb" id="tbGridThumb"></span><span class="icw sm" data-icon="chevron"></span></button>
  <span class="tb-spacer"></span>
  <button class="tb-btn" id="tbLayout" type="button" title="Saved layouts" aria-haspopup="menu" aria-expanded="false"><span id="tbLayoutName">Unsaved</span><span class="icw sm" data-icon="chevron"></span></button>
  <button class="tb-btn" id="tbSave" type="button" title="Save layout">Save</button>
  <span class="tb-msg" id="tbSaveMsg" role="status"></span>
  <span class="tb-sep"></span>
  <button class="tb-btn tb-icon" id="tbTheme" type="button" title="Dark theme"><span class="icw" data-icon="moon"></span></button>
</header>
<div class="main">
  <nav class="rail" id="rail" aria-label="Drawing tools">
    <button class="rail-btn" type="button" data-tool="cursor" title="Cursor" aria-pressed="true"><span class="icw" data-icon="cursor"></span></button>
    <button class="rail-btn" type="button" data-tool="trend" title="Trend line" aria-pressed="false"><span class="icw" data-icon="trend"></span></button>
    <button class="rail-btn" type="button" data-tool="hline" title="Horizontal line" aria-pressed="false"><span class="icw" data-icon="hline"></span></button>
    <button class="rail-btn" type="button" data-tool="rect" title="Rectangle" aria-pressed="false"><span class="icw" data-icon="rect"></span></button>
    <button class="rail-btn" type="button" data-tool="measure" title="Measure" aria-pressed="false"><span class="icw" data-icon="measure"></span></button>
    <span class="rail-sep"></span>
    <button class="rail-btn" type="button" id="railClear" title="Remove drawings"><span class="icw" data-icon="trash"></span></button>
  </nav>
  <div class="grid" id="grid"></div>
</div>
<footer class="statusbar">
  <span class="sb-dot" id="sbDot"></span><span class="sb-mode" id="sbMode">Connecting…</span><span class="sb-feed" id="sbFeed"></span>
  <span class="sb-spacer"></span>
  <span class="sb-note" id="sbNote" role="status"></span>
  <span class="sb-clock" id="sbClock"></span><span class="sb-opt" id="sbBudget"></span><span class="sb-opt" id="sbRec"></span>
  <a class="sb-credit" id="sbCredit" href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer" title="TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc. · https://www.tradingview.com/">Charts: TradingView Lightweight Charts™</a>
</footer>
<div id="menuRoot"></div>
<div id="dialogRoot"></div>
<div class="rail-tip" id="railTip" role="status" hidden></div>
<script src="/static/vendor/lightweight-charts-5.2.1.js"></script>
<script src="/static/charts/icons.js"></script>
<script src="/static/charts/catalog.js"></script>
<script src="/static/charts/primitives.js"></script>
<script src="/static/charts/drawings.js"></script>
<script src="/static/charts/cell.js"></script>
<script src="/static/charts/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: `charts.css`** (whole file — the design; later tasks only add DOM that uses these classes):

```css
/* Homebase Charts — TradingView-style look, measured on tradingview.com/chart
   (2026-09-26; see docs/superpowers/specs/2026-09-26-charts-tv-redesign-design.md).
   Every colour comes from the tokens below; the chart canvases get the same
   values from HBCell.palette(). */
:root {
  --font: -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif;
  --frame: #EBEBEB; --panel: #FFFFFF; --text: #0F0F0F; --text-2: #787B86; --border: #E0E3EB;
  --grid: #F0F3FA; --hover: #F0F3FA; --pill: #EBEBEB;
  --accent: #2962FF; --accent-hover: #1E53E5; --accent-soft: rgba(41, 98, 255, .10);
  --up: #089981; --down: #F23645; --down-soft: rgba(242, 54, 69, .10); --warn: #F7A600;
  --tip: #131722;
  --shadow-menu: 0 2px 8px rgba(0, 0, 0, .16);
  --shadow-dialog: 0 8px 32px rgba(0, 0, 0, .24);
  --backdrop: rgba(0, 0, 0, .25);
  color-scheme: light;
}
:root[data-theme="dark"] {
  --frame: #0A0A0A; --panel: #0F0F0F; --text: #DBDBDB; --text-2: #8C8C8C; --border: #2E2E2E;
  --grid: #1C1C1C; --hover: #2A2A2A; --pill: #2A2A2A; --accent-soft: rgba(41, 98, 255, .20);
  --down-soft: rgba(242, 54, 69, .18); --tip: #2A2E39;
  --shadow-menu: 0 0 0 1px #2E2E2E, 0 4px 12px rgba(0, 0, 0, .5);
  --shadow-dialog: 0 0 0 1px #2E2E2E, 0 8px 32px rgba(0, 0, 0, .6);
  --backdrop: rgba(0, 0, 0, .5);
  color-scheme: dark;
}

* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { display: flex; flex-direction: column; overflow: hidden; background: var(--frame); color: var(--text);
  font: 14px/1.25 var(--font); -webkit-font-smoothing: antialiased; }
button, input { font: inherit; color: inherit; }
button { margin: 0; padding: 0; border: 0; background: none; cursor: pointer; }
a { color: inherit; }
:focus { outline: none; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
[hidden] { display: none !important; }
.menu, .dlg-list, .dlg-groups { scrollbar-width: thin; }

/* icons: Lucide drawn a little thinner, like TradingView's line icons */
.icw { display: inline-grid; place-items: center; flex: none; }
.ic { display: block; width: 18px; height: 18px; stroke-width: 1.6; }
.icw.sm .ic { width: 14px; height: 14px; }

/* ---- top toolbar: 38px, flat full-height buttons, 1x20 separators ---- */
.toolbar { flex: none; height: 38px; display: flex; align-items: center; padding: 0 4px; background: var(--panel);
  overflow-x: auto; overflow-y: hidden; white-space: nowrap; scrollbar-width: none; }
.toolbar::-webkit-scrollbar { display: none; }
.tb-btn { flex: none; height: 38px; display: inline-flex; align-items: center; gap: 6px; padding: 0 10px;
  color: var(--text); font-size: 14px; text-decoration: none; }
.tb-btn:hover, .tb-btn.open { background: var(--hover); }
.tb-btn.active { color: var(--accent); }
.tb-btn.tb-icon { padding: 0 8px; }
.tb-btn.iv { padding: 0 7px; font-variant-numeric: tabular-nums; }
.tb-group { flex: none; display: flex; }
.tb-sep { flex: none; width: 1px; height: 20px; margin: 0 4px; background: var(--border); }
.tb-spacer { flex: 1 0 8px; }
.tb-pill { flex: none; height: 28px; display: inline-flex; align-items: center; gap: 6px; margin: 0 4px; padding: 0 14px 0 10px;
  border-radius: 14px; background: var(--pill); font-size: 14px; font-weight: 600; }
.tb-pill .ic { width: 16px; height: 16px; color: var(--text-2); }
.tb-pill:hover, .tb-pill.open { background: var(--border); }
.tb-msg { flex: none; padding: 0 6px; color: var(--text-2); font-size: 12px; }
.tb-msg.err { color: var(--down); }
.thumb { display: inline-grid; gap: 2px; width: 20px; height: 15px; }
.thumb i { border: 1.5px solid currentColor; border-radius: 2px; }
@media (max-width: 760px) { .tb-label { display: none; } }

/* ---- drawing rail + the grid of chart panels on the frame ---- */
.main { flex: 1; min-height: 0; display: flex; gap: 4px; padding: 4px 4px 4px 0; }
.rail { flex: none; width: 52px; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 0;
  background: var(--panel); border-radius: 0 6px 6px 0; }
.rail-btn { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 4px; color: var(--text); }
.rail-btn .ic { width: 20px; height: 20px; }
.rail-btn:hover { background: var(--hover); }
.rail-btn[aria-pressed="true"] { color: var(--accent); background: var(--accent-soft); }
.rail-btn.arm { color: var(--down); background: var(--down-soft); }
.rail-sep { width: 28px; height: 1px; margin: 4px 0; background: var(--border); }
.rail-tip { position: fixed; z-index: 40; padding: 6px 10px; border-radius: 6px; background: var(--tip); color: #FFFFFF;
  font-size: 12px; white-space: nowrap; pointer-events: none; }
.grid { flex: 1; min-width: 0; display: grid; gap: 4px; }
.panel { position: relative; min-width: 0; min-height: 0; overflow: hidden; border-radius: 6px; background: var(--panel); }
.panel .chart { position: absolute; inset: 0; }
.panel.selected::after { content: ""; position: absolute; inset: 0; z-index: 6; border-radius: 6px;
  box-shadow: inset 0 0 0 1px var(--accent); pointer-events: none; }
.grid[data-count="1"] .panel.selected::after { display: none; }
.panel[data-cursor="crosshair"] .chart * { cursor: crosshair !important; }
.panel[data-cursor="move"] .chart * { cursor: move !important; }
.panel[data-cursor="grabbing"] .chart * { cursor: grabbing !important; }

/* ---- legend: DOM over the chart; only the badge and indicator rows take the mouse ---- */
.legend { position: absolute; left: 8px; top: 7px; right: 80px; z-index: 5; display: flex; flex-direction: column;
  align-items: flex-start; gap: 1px; font-size: 13px; line-height: 20px; pointer-events: none; }
.lg-title { display: flex; align-items: center; gap: 8px; max-width: 100%; font-size: 16px; line-height: 22px; white-space: nowrap; }
.grid[data-count="4"] .lg-title, .grid[data-count="6"] .lg-title { font-size: 14px; line-height: 20px; }
.lg-name { overflow: hidden; text-overflow: ellipsis; }
.badge { flex: none; padding: 0 5px; border-radius: 4px; background: var(--hover); color: var(--text-2);
  font-size: 11px; line-height: 16px; cursor: help; pointer-events: auto; }
.lg-msg { color: var(--text-2); font-size: 13px; }
.lg-msg.err { color: var(--down); white-space: normal; }
.lg-ohlc { display: flex; flex-wrap: wrap; gap: 0 8px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.kv .k { margin-right: 3px; color: var(--text); }
.lg-inds { display: flex; flex-direction: column; align-items: flex-start; }
.lg-row { display: inline-flex; align-items: center; gap: 8px; height: 22px; margin-left: -4px; padding: 0 4px;
  border-radius: 4px; white-space: nowrap; pointer-events: auto; }
.lg-row:hover { background: var(--hover); }
.lg-label { color: var(--text); }
.lg-vals { display: inline-flex; gap: 8px; font-variant-numeric: tabular-nums; }
.lg-row.off .lg-label, .lg-row.off .lg-vals { opacity: .5; }
.lg-btns { display: none; gap: 2px; }
.lg-row:hover .lg-btns, .lg-row:focus-within .lg-btns { display: inline-flex; }
.ib { width: 18px; height: 18px; display: grid; place-items: center; border-radius: 3px; color: var(--text); }
.ib .ic { width: 14px; height: 14px; }
.ib:hover { background: var(--border); }

/* ---- menus ---- */
.menu { position: fixed; z-index: 50; min-width: 200px; max-width: 340px; max-height: calc(100vh - 56px); overflow: auto;
  padding: 6px 0; background: var(--panel); border-radius: 8px; box-shadow: var(--shadow-menu); font-size: 14px; }
.menu-h { padding: 10px 16px 4px; color: var(--text-2); font-size: 11px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; }
.menu-i { width: 100%; height: 32px; display: flex; align-items: center; gap: 12px; padding: 0 16px; text-align: left;
  white-space: nowrap; }
.menu-i:hover, .menu-i:focus-visible { background: var(--hover); }
.menu-i.active { color: var(--accent); }
.menu-t { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.menu-sub { color: var(--text-2); }
.menu-sym .menu-t { flex: 0 0 44px; font-weight: 600; }
.menu-row { display: flex; align-items: center; padding-right: 8px; }
.menu-row .menu-i { flex: 1; min-width: 0; }
.menu-row:hover { background: var(--hover); }
.menu-row:hover .menu-i { background: none; }
.menu-del { flex: none; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 4px; color: var(--text-2); }
.menu-del:hover { background: var(--border); color: var(--text); }
.menu-sep { height: 1px; margin: 6px 0; background: var(--border); }
.menu-empty { padding: 8px 16px; color: var(--text-2); }
.menu-input { display: block; width: calc(100% - 24px); height: 32px; margin: 4px 12px 6px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 6px; background: var(--panel); font-size: 14px; }
.menu-input:focus { border-color: var(--accent); }
.menu-custom { display: flex; align-items: center; gap: 8px; padding: 4px 12px 6px; }
.menu-custom .menu-input { flex: 1; width: auto; min-width: 0; margin: 0; }
.menu-confirm { display: flex; align-items: center; gap: 8px; min-height: 36px; padding: 2px 12px 2px 16px; }
.menu-confirm span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.menu-err { padding: 2px 16px 8px; color: var(--down); font-size: 12px; white-space: normal; }
.grid-picks { display: flex; gap: 6px; padding: 6px 10px; }
.grid-pick { width: 52px; height: 44px; display: grid; place-items: center; border-radius: 6px; color: var(--text-2); }
.grid-pick .thumb { width: 32px; height: 24px; }
.grid-pick:hover { background: var(--hover); color: var(--text); }
.grid-pick.active { background: var(--accent-soft); color: var(--accent); }

/* ---- buttons in menus and dialogs ---- */
.btn { flex: none; height: 32px; padding: 0 14px; border-radius: 6px; font-size: 14px; }
.btn-primary { background: var(--accent); color: #FFFFFF; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-ghost { box-shadow: inset 0 0 0 1px var(--border); }
.btn-ghost:hover { background: var(--hover); }
.btn-danger { background: var(--down); color: #FFFFFF; }

/* ---- dialogs ---- */
.backdrop { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; background: var(--backdrop); }
.dialog { width: min(720px, 92vw); max-height: 80vh; display: flex; flex-direction: column; overflow: hidden;
  background: var(--panel); border-radius: 8px; box-shadow: var(--shadow-dialog); }
.dialog.small { width: min(380px, 92vw); }
.dlg-head { flex: none; display: flex; align-items: center; justify-content: space-between; padding: 16px 12px 12px 20px;
  font-size: 20px; font-weight: 600; }
.dlg-x { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 6px; color: var(--text); }
.dlg-x .ic { width: 20px; height: 20px; }
.dlg-x:hover { background: var(--hover); }
.dlg-search { flex: none; display: flex; align-items: center; gap: 8px; height: 34px; margin: 0 20px 12px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 8px; }
.dlg-search:focus-within { border-color: var(--accent); }
.dlg-search .ic { color: var(--text-2); }
.dlg-search input { flex: 1; min-width: 0; border: 0; background: none; font-size: 16px; }
.dlg-body { flex: 1; min-height: 0; display: flex; border-top: 1px solid var(--border); }
.dlg-groups { flex: none; width: 180px; padding: 8px 0; overflow: auto; border-right: 1px solid var(--border); }
.dlg-group { width: 100%; height: 32px; padding: 0 20px; text-align: left; color: var(--text); }
.dlg-group:hover { background: var(--hover); }
.dlg-group.active { background: var(--accent-soft); color: var(--accent); }
.dlg-list { flex: 1; min-width: 0; min-height: 320px; padding: 8px 0; overflow: auto; }
.dlg-row { width: 100%; height: 32px; display: flex; align-items: center; gap: 8px; padding: 0 20px; text-align: left; }
.dlg-row:hover, .dlg-row:focus-visible { background: var(--hover); }
.dlg-name { flex: 1; }
.dlg-grp { color: var(--text-2); font-size: 12px; }
.dlg-row .ic { width: 16px; height: 16px; color: var(--accent); }
.dlg-empty { padding: 12px 20px; color: var(--text-2); }
@media (max-width: 560px) { .dlg-groups { display: none; } }
.dlg-fields { padding: 4px 0; }
.field { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 8px 20px; }
.field input[type="number"] { width: 96px; height: 32px; padding: 0 8px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel); font-variant-numeric: tabular-nums; }
.field input[type="number"]:focus { border-color: var(--accent); }
.field input[type="checkbox"] { width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }
.seg { display: inline-flex; padding: 2px; border-radius: 6px; background: var(--hover); }
.seg button { height: 28px; padding: 0 12px; border-radius: 4px; color: var(--text-2); }
.seg button.on { background: var(--panel); color: var(--text); box-shadow: 0 1px 2px rgba(0, 0, 0, .12); }
.dlg-foot { flex: none; display: flex; justify-content: flex-end; gap: 8px; padding: 16px 20px; }

/* ---- bottom bar ---- */
.statusbar { flex: none; height: 30px; display: flex; align-items: center; gap: 12px; padding: 0 12px; overflow: hidden;
  background: var(--panel); color: var(--text-2); font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.sb-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--text-2); }
.sb-dot.ok { background: var(--up); }
.sb-dot.warn { background: var(--warn); }
.sb-dot.bad { background: var(--down); }
.sb-mode { color: var(--text); }
.sb-feed { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.sb-feed.bad, .sb-note { color: var(--down); }
.sb-spacer { flex: 1; }
#sbRec.warn { color: var(--warn); }
.sb-credit { color: var(--text-2); text-decoration: none; }
.sb-credit:hover { color: var(--text); text-decoration: underline; }
@media (max-width: 760px) { .sb-opt { display: none; } }
```

- [ ] **Step 5: `cell.js`** (whole file):

```js
/* Homebase Charts — one chart panel (HBCell.Cell): Lightweight Charts in the
   TradingView-style palette, series built from the chart's indicator
   instances (HBCatalog), the DOM legend, the watermark, and the
   history/update handling. The page (app.js) owns the websocket, the toolbar
   and selection, and gives each cell a `host`:
     {id, send(msg) -> bool, onPick(cell), onLoaded(cell), onRefused(cell, tried, text), changed()}
   Bar times arrive as ET wall-clock seconds, so the axis reads ET; tick,
   volume and range bars sit on an evenly spaced synthetic axis (many can
   share a second) and are labelled with their real times. */
(() => {
'use strict';
const LW = window.LightweightCharts;
const C = window.HBCatalog;
const { Footprint, Profile, Gaps } = window.HBLayers;
const FAKE0 = 946684800;    // synthetic-axis origin for tick/volume/range bars
const FONT = '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
const LEVELS = [['pdh', 'PDH'], ['pdl', 'PDL'], ['pdc', 'PDC'], ['onh', 'ONH'], ['onl', 'ONL'], ['rth_open', 'Open']];
const PANE_H = 90;          // px: the delta / cumulative delta / ADX panes
const NOTE_MS = 8000;       // a refused change's reason stays this long in the legend
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const clone = (x) => JSON.parse(JSON.stringify(x));

/* The chart canvas colours: charts.css's tokens for the current theme. */
function palette() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const P = { up: '#089981', down: '#F23645', upA: 'rgba(8,153,129,.5)', downA: 'rgba(242,54,69,.5)', accent: '#2962FF',
    lines: C.LINE_COLORS, vwap: '#9C27B0', band: 'rgba(156,39,176,.45)', cum: '#FF6D00', poc: '#F7A600',
    gap: 'rgba(120,123,134,.14)', cross: '#9598A1', crossLabel: '#131722' };
  return Object.assign(P, dark
    ? { bg: '#0F0F0F', text: '#DBDBDB', text2: '#8C8C8C', grid: '#1C1C1C', border: '#2E2E2E', accentSoft: 'rgba(41,98,255,.20)',
        downSoft: 'rgba(242,54,69,.18)', watermark: 'rgba(219,219,219,.06)', level: '#8C8C8C', fpText: '#DBDBDB',
        fpBg: 'rgba(255,255,255,.06)', va: 'rgba(41,98,255,.20)', vaIn: 'rgba(41,98,255,.40)' }
    : { bg: '#FFFFFF', text: '#0F0F0F', text2: '#787B86', grid: '#F0F3FA', border: '#E0E3EB', accentSoft: 'rgba(41,98,255,.10)',
        downSoft: 'rgba(242,54,69,.10)', watermark: 'rgba(15,15,15,.06)', level: '#787B86', fpText: '#0F0F0F',
        fpBg: 'rgba(15,15,15,.05)', va: 'rgba(41,98,255,.10)', vaIn: 'rgba(41,98,255,.28)' });
}

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function val(text, color) { const s = mk('span', 'v', text); s.style.color = color; return s; }
function kv(k, v, color) { const s = mk('span', 'kv'); s.append(mk('span', 'k', k), val(v, color)); return s; }

/* Time-axis labels like TradingView's: year, month name, day of month, HH:MM(:SS). */
function tickLabel(t, type) {
  const d = new Date(t * 1000);
  if (type === 0) return String(d.getUTCFullYear());
  if (type === 1) return MONTHS[d.getUTCMonth()];
  if (type === 2) return String(d.getUTCDate());
  return d.toISOString().slice(11, type === 4 ? 19 : 16);
}

class Cell {
  constructor(slot, cfg, host) {
    this.el = slot; this.cfg = cfg; this.host = host; this.id = host.id;
    this.chart = null; this.candles = null; this.markers = null; this.P = null;
    this.bars = []; this.realT = new Map(); this.devel = false; this.sessions = []; this.tick = 0.25;
    this.profile = null; this.keys = new Set(); this.lines = []; this.rows = []; this.colorOf = {}; this.levelLines = {};
    this.shown = null;      // {root, spec} of the bars on screen
    this.lastGood = null;   // the config the server last answered with a history
    this.pending = null;    // the config of the subscription in flight
    this.keepView = null;   // the view to restore when that history arrives
    this.hover = null;      // bar index under the crosshair (null: the last bar)
    this.noteTimer = 0; this.noteUntil = 0;
    slot.className = 'panel';
    slot.innerHTML = `
      <div class="chart"></div>
      <div class="legend">
        <div class="lg-title"><span class="lg-name"></span><span class="badge" hidden>approx. flow</span><span class="lg-msg" role="status"></span></div>
        <div class="lg-ohlc"></div>
        <div class="lg-inds"></div>
      </div>`;
    this.box = slot.querySelector('.chart');
    this.lg = { name: slot.querySelector('.lg-name'), badge: slot.querySelector('.badge'), msg: slot.querySelector('.lg-msg'),
      ohlc: slot.querySelector('.lg-ohlc'), inds: slot.querySelector('.lg-inds') };
    this.lg.badge.title = 'Part of this history has no bid/ask: buys and sells there are split by the tick rule';
    slot.addEventListener('pointerdown', () => host.onPick(this), true);
    this.title();
    this.subscribe();
  }

  cfgNow() { return clone({ root: this.cfg.root, spec: this.cfg.spec, indicators: this.cfg.indicators }); }
  spec() { return (this.shown || this.cfg).spec; }
  isTime() { return this.spec().startsWith('time:'); }
  barMs() { const s = C.parseSpec(this.spec()); return s && s.kind === 'time' ? s.n * 1000 : 0; }
  real(tt) { return this.isTime() ? tt : (this.realT.get(tt) ?? tt); }

  /* The crosshair's time label, e.g. "Tue 22 Sep '26  09:31". */
  fullTime(tt) {
    const d = new Date(this.real(tt) * 1000), s = d.toISOString(), ms = this.barMs();
    const day = `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} '${s.slice(2, 4)}`;
    if (ms >= 86400000) return day;
    return `${day}  ${s.slice(11, ms >= 60000 ? 16 : 19)}`;
  }

  title() {
    const { root, spec } = this.cfg;
    this.lg.name.textContent = [root, C.rootName(root), C.specLabel(spec)].filter(Boolean).join(' · ');
  }
  message(text, err = false) { this.lg.msg.textContent = text || ''; this.lg.msg.classList.toggle('err', !!err); }
  note(text) {   // a refused change: its reason in red for a while
    this.message(text, true);
    this.noteUntil = Date.now() + NOTE_MS;
    clearTimeout(this.noteTimer);
    this.noteTimer = setTimeout(() => this.message(''), NOTE_MS);
  }
  setSelected(on) { this.el.classList.toggle('selected', on); }

  subscribe(keepView = false) {
    this.keepView = keepView && this.chart ? this.viewNow() : null;
    this.pending = this.cfgNow();
    const sent = this.host.send({ op: 'sub', id: this.id, root: this.cfg.root, spec: this.cfg.spec,
      studies: C.serverKeys(this.cfg.indicators), fp: true });
    if (sent && !this.chart) this.message('Loading…');
  }

  /* A change from the toolbar or a dialog. A new symbol or interval reloads
     the chart at the latest bar; indicator changes rebuild it in place and
     resubscribe (keeping the view) only when they need a study the stream
     does not carry yet. */
  update(patch) {
    const was = this.shown;
    Object.assign(this.cfg, patch);
    this.title();
    this.host.changed();
    const same = !!was && was.root === this.cfg.root && was.spec === this.cfg.spec;
    if (same && this.chart && C.serverKeys(this.cfg.indicators).every((k) => this.keys.has(k))) {
      this.lastGood = this.cfgNow();
      this.restyle();
      return;
    }
    this.subscribe(same);
  }

  onHistory(m) {
    const answers = this.pending && this.pending.root === m.root && this.pending.spec === m.spec;
    if (answers || !this.pending) { this.lastGood = answers ? this.pending : this.cfgNow(); this.pending = null; }
    const view = this.keepView && this.shown && this.shown.root === m.root && this.shown.spec === m.spec ? this.keepView : null;
    this.keepView = null;
    this.shown = { root: m.root, spec: m.spec };
    this.tick = m.tick_size; this.sessions = m.sessions || []; this.devel = !!m.live;
    this.keys = new Set(Object.keys(m.studies || {}));
    this.profile = m.profile || null;
    this.bars = []; this.realT = new Map();
    m.bars.forEach((b, i) => { b.sv = {}; for (const k in m.studies) b.sv[k] = m.studies[k][i]; this.append(b); });
    this.build(view);
    if (Date.now() >= this.noteUntil) this.message('');
    this.host.onLoaded(this);
  }

  /* The server refused a subscription. A change it refused goes back to the
     last config it accepted (resubscribed: a refusal can drop the old
     stream); the page shows why. Anything else is shown in the legend. */
  onError(text) {
    const tried = this.pending;
    this.pending = null;
    if (tried && this.lastGood && JSON.stringify(tried) !== JSON.stringify(this.lastGood)) {
      Object.assign(this.cfg, clone(this.lastGood));
      this.title();
      this.host.changed();
      this.host.onRefused(this, tried, text);
      this.subscribe(true);
      return;
    }
    this.message(text, true);
  }

  build(view) {
    this.makeChart();
    this.candles.setData(this.bars.map((b) => this.candle(b)));
    this.buildSeries();
    for (const l of this.lines) l.s.setData(this.bars.map((b) => this.point(l, b)));
    this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint(); this.syncProfile();
    const panes = this.chart.panes();
    for (let i = 1; i < panes.length; i++) panes[i].setHeight(PANE_H);
    if (view) this.setView(view); else this.chart.timeScale().scrollToRealTime();
    this.lg.badge.hidden = !this.sessions.some((s) => s.approx);
    this.legendRows();
    this.legend(null);
  }

  restyle() { if (this.chart) this.build(this.viewNow()); }

  /* The visible range counted from the last bar, so it survives new bars. */
  viewNow() {
    const r = this.chart && this.chart.timeScale().getVisibleLogicalRange();
    return r ? { fromEnd: this.bars.length - r.from, toEnd: this.bars.length - r.to } : null;
  }
  setView(v) {
    const n = this.bars.length;
    this.chart.timeScale().setVisibleLogicalRange({ from: n - v.fromEnd, to: n - v.toEnd });
  }

  makeChart() {
    this.teardown();
    const P = this.P = palette(), sub = this.isTime() && this.barMs() < 60000;
    this.chart = LW.createChart(this.box, {
      autoSize: true,
      layout: { background: { type: 'solid', color: P.bg }, textColor: P.text2, fontSize: 12, fontFamily: FONT,
        attributionLogo: false,   // the credit lives once in the bottom bar
        panes: { separatorColor: P.border, separatorHoverColor: P.accentSoft, enableResize: true } },
      grid: { vertLines: { color: P.grid }, horzLines: { color: P.grid } },
      rightPriceScale: { borderColor: P.border, scaleMargins: { top: 0.1, bottom: 0.15 } },
      timeScale: { borderColor: P.border, timeVisible: true, secondsVisible: sub, rightOffset: 6,
        tickMarkFormatter: (t, type) => tickLabel(this.real(t), type) },
      localization: { timeFormatter: (t) => this.fullTime(t) },
      crosshair: { mode: LW.CrosshairMode.Normal,
        vertLine: { color: P.cross, width: 1, style: LW.LineStyle.Dashed, labelBackgroundColor: P.crossLabel },
        horzLine: { color: P.cross, width: 1, style: LW.LineStyle.Dashed, labelBackgroundColor: P.crossLabel } },
    });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, { upColor: P.up, downColor: P.down, wickUpColor: P.up,
      wickDownColor: P.down, borderVisible: false, priceLineStyle: LW.LineStyle.Dotted,
      priceFormat: { type: 'price', precision: C.decimals(this.tick), minMove: this.tick } });
    this.markers = LW.createSeriesMarkers(this.candles, []);
    LW.createTextWatermark(this.chart.panes()[0], { horzAlign: 'center', vertAlign: 'center',
      lines: [{ text: `${this.shown.root}, ${C.specLabel(this.shown.spec)}`, color: P.watermark, fontSize: 48, fontFamily: FONT }] });
    this.fp = new Footprint(P); this.prof = new Profile(P); this.gaps = new Gaps(P);
    const fp = this.fp;   // pin the instance this callback belongs to
    fp.onReadableChange = (on) => {   // fired async from Footprint.updateAllViews(), after layout
      if (this.fp !== fp || !this.chart) return;
      this.candles.applyOptions(on ? { upColor: 'rgba(0,0,0,0)', downColor: 'rgba(0,0,0,0)' } : { upColor: P.up, downColor: P.down });
    };
    for (const l of [this.gaps, this.prof, this.fp]) this.candles.attachPrimitive(l);
    this.lines = []; this.levelLines = {}; this.colorOf = {}; this.hover = null;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.syncFootprint());
    this.chart.subscribeCrosshairMove((p) => {
      this.hover = p && p.logical != null ? Math.round(p.logical) : null;
      this.legend(this.hover);
    });
  }

  teardown() {
    if (!this.chart) return;
    this.chart.remove();
    this.chart = this.candles = this.markers = this.fp = this.prof = this.gaps = null;   // stale async callbacks can tell
  }

  /* One series per drawn part of each indicator instance, in instance order. */
  buildSeries() {
    const P = this.P;
    let ci = 0, pane = 0;
    const add = (inst, src, part, type, opts, where) => {
      const s = this.chart.addSeries(type, { priceLineVisible: false, visible: inst.visible !== false, ...opts }, where);
      this.lines.push({ uid: inst.uid, s, src, part });
      return s;
    };
    const line = (inst, src, part, color, width, where = 0, extra = {}) => add(inst, src, part, LW.LineSeries,
      { color, lineWidth: width, lastValueVisible: true, crosshairMarkerVisible: false, title: '', ...extra }, where);
    for (const inst of this.cfg.indicators) {
      const k = C.serverKey(inst);
      switch (inst.id) {
        case 'volume':
          add(inst, '__vol', null, LW.HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false }, 0)
            .priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
          break;
        case 'vwap':
          this.colorOf[inst.uid] = P.vwap;
          line(inst, k, null, P.vwap, 2);
          if (inst.params.bands) {
            for (const b of ['u1', 'l1', 'u2', 'l2']) line(inst, k, b, P.band, 1, 0, { lineStyle: LW.LineStyle.Dashed, lastValueVisible: false });
          }
          break;
        case 'ema': case 'sma': case 'vwma': {
          const color = P.lines[ci++ % P.lines.length];
          this.colorOf[inst.uid] = color;
          line(inst, k, null, color, 1);
          break;
        }
        case 'adx': {
          const where = ++pane;
          line(inst, k, null, P.text, 2, where); line(inst, k, 'p', P.up, 1, where); line(inst, k, 'm', P.down, 1, where);
          break;
        }
        case 'delta':
          add(inst, '__delta', null, LW.HistogramSeries, { lastValueVisible: true }, ++pane);
          break;
        case 'cumdelta':
          this.colorOf[inst.uid] = P.cum;
          line(inst, k, null, P.cum, 2, ++pane);
          break;
        default:   // levels, footprint, profile, big prints: price lines, layers and markers
          break;
      }
    }
  }

  legendRows() {
    this.rows = this.cfg.indicators.map((inst) => {
      const row = mk('div', 'lg-row' + (inst.visible === false ? ' off' : '')), vals = mk('span', 'lg-vals');
      row.dataset.uid = inst.uid;
      row.append(mk('span', 'lg-label', C.label(inst)), vals);
      return { inst, row, vals };
    });
    this.lg.inds.replaceChildren(...this.rows.map((r) => r.row));
  }

  /* The OHLC row and every indicator row for bar i (null: the last bar). */
  legend(i) {
    const n = this.bars.length;
    if (!n || !this.P) { this.lg.ohlc.replaceChildren(); return; }
    const k = i == null ? n - 1 : Math.max(0, Math.min(i, n - 1)), b = this.bars[k], prev = k > 0 ? this.bars[k - 1] : null;
    const P = this.P, col = b.c >= b.o ? P.up : P.down, ch = C.change(b, prev, this.tick);
    this.lg.ohlc.replaceChildren(
      ...[['O', b.o], ['H', b.h], ['L', b.l], ['C', b.c]].map(([key, v]) => kv(key, C.fmtPrice(v, this.tick), col)),
      val(ch.text, ch.up ? P.up : P.down),
      kv('Vol', C.fmtCompact(b.v), col),
      kv('Δ', C.fmtSigned(b.d), b.d >= 0 ? P.up : P.down));
    const colors = { text: P.text, up: P.up, down: P.down, vwap: P.vwap, cum: P.cum };
    for (const r of this.rows) {
      const vs = C.legendValues(r.inst, b, { ...colors, line: this.colorOf[r.inst.uid] || P.accent }, this.tick);
      r.vals.replaceChildren(...vs.map((x) => val(x.text, x.color)));
    }
  }

  onUpdate(m) {
    if (!this.chart) return;
    const touched = [];
    const vals = (i, live) => { const o = {}; for (const k in m.studies) o[k] = live ? m.studies[k].live : m.studies[k].closed[i]; return o; };
    m.closed.forEach((b, i) => { b.sv = vals(i, false); if (i === 0 && this.devel) this.replaceLast(b); else this.append(b); touched.push(b); });
    if (m.live) { m.live.sv = vals(0, true); if (!m.closed.length && this.devel) this.replaceLast(m.live); else this.append(m.live); touched.push(m.live); }
    this.devel = !!m.live;
    for (const b of touched) {
      this.candles.update(this.candle(b));
      for (const l of this.lines) l.s.update(this.point(l, b));
    }
    if (m.profile !== undefined) { this.profile = m.profile; this.syncProfile(); }
    if (touched.some((b) => b.big && b.big.length)) this.drawMarkers();
    this.drawLevels(); this.syncFootprint();
    this.legend(this.hover);
  }

  append(b) {
    const last = this.bars[this.bars.length - 1];
    b.tt = this.isTime() ? b.t : FAKE0 + this.bars.length * 60;
    if (last && b.tt <= last.tt) b.tt = last.tt + 1;
    if (!this.isTime()) this.realT.set(b.tt, b.t);
    this.bars.push(b);
  }

  replaceLast(b) {
    const i = this.bars.length - 1;
    b.tt = this.bars[i].tt;
    if (!this.isTime()) this.realT.set(b.tt, b.t);
    this.bars[i] = b;
  }

  candle(b) { return { time: b.tt, open: b.o, high: b.h, low: b.l, close: b.c }; }

  point(l, b) {
    const P = this.P, time = b.tt;
    if (l.src === '__vol') return { time, value: b.v, color: b.d >= 0 ? P.upA : P.downA };
    if (l.src === '__delta') return { time, value: b.d, color: b.d >= 0 ? P.upA : P.downA };
    const v = b.sv ? b.sv[l.src] : null;
    if (v == null) return { time };
    if (typeof v === 'number') return { time, value: v };
    if (l.src.startsWith('vwap')) {
      if (v.vwap == null || (l.part && v.sd == null)) return { time };
      return { time, value: v.vwap + ({ u1: 1, l1: -1, u2: 2, l2: -2 }[l.part] || 0) * (v.sd || 0) };
    }
    if (l.src.startsWith('adx')) {
      const x = l.part === 'p' ? v.pdi : l.part === 'm' ? v.mdi : v.adx;
      return x == null ? { time } : { time, value: x };
    }
    return { time };
  }

  visible(id) { return this.cfg.indicators.filter((x) => x.id === id && x.visible !== false); }

  drawMarkers() {
    if (!this.markers) return;
    const mins = this.visible('bigprints').map((x) => x.params.min), P = this.P;
    if (!mins.length) { this.markers.setMarkers([]); return; }
    const min = Math.min(...mins), out = [];
    for (const b of this.bars) {
      for (const [, , size, side] of (b.big || [])) {
        if (size >= min) out.push({ time: b.tt, position: side > 0 ? 'belowBar' : 'aboveBar',
          color: side > 0 ? P.up : P.down, shape: 'circle', size: 0.6, text: String(size) });
      }
    }
    this.markers.setMarkers(out.slice(-600));
  }

  drawLevels() {
    if (!this.candles) return;
    const last = this.bars[this.bars.length - 1];
    const lv = this.visible('levels').length && last && last.sv ? last.sv.levels : null;
    for (const [k, title] of LEVELS) {
      const px = lv ? lv[k] : null, cur = this.levelLines[k];
      if (px == null) { if (cur) { this.candles.removePriceLine(cur); delete this.levelLines[k]; } continue; }
      if (cur) { if (cur.options().price !== px) cur.applyOptions({ price: px }); continue; }
      this.levelLines[k] = this.candles.createPriceLine({ price: px, color: this.P.level, lineWidth: 1,
        lineStyle: LW.LineStyle.Dashed, axisLabelVisible: true, title });
    }
  }

  drawGaps() {
    const idx = [];
    for (const s of this.sessions) {
      for (const [a] of (s.gaps || [])) {
        let i = -1;
        for (let j = 0; j < this.bars.length && this.bars[j].t <= a; j++) i = j;
        if (i >= 0 && i < this.bars.length - 1) idx.push(i);
      }
    }
    this.gaps.set(idx);
  }

  syncFootprint() {
    if (!this.fp) return;
    const f = this.visible('footprint')[0];
    this.fp.set(this.bars, !!f, f ? f.params.imbalance : 0, this.tick);
  }

  syncProfile() { if (this.prof) this.prof.set(this.visible('profile').length ? this.profile : null, this.tick); }

  destroy() {
    this.host.send({ op: 'unsub', id: this.id });
    clearTimeout(this.noteTimer);
    this.teardown();
  }
}

window.HBCell = { Cell, palette, FONT };
})();
```

- [ ] **Step 6: `app.js`** (whole file for this task; Tasks 5 and 6 extend it):

```js
/* Homebase Charts — the page: layout and selection, the top toolbar (it
   acts on the selected chart), menus, the websocket to the chart service
   (:8852) and the bottom bar. Each grid slot is an HBCell.Cell; the server
   computes everything, the page only draws. */
(() => {
'use strict';
const C = window.HBCatalog, I = window.HBIcons, { Cell } = window.HBCell;
const GRIDS = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] };
const STATUS_STALE_S = 6;   // the server sends a status every 2 s: this long without one = it is stuck
const START = [['NQ', 'time:60'], ['NQ', 'time:300'], ['ES', 'time:60'], ['YM', 'time:60'], ['NQ', 'tick:1000'], ['NQ', 'time:900']];
const ET_CLOCK = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit',
  second: '2-digit', hourCycle: 'h23' });

let meta = { roots: ['NQ'], timeframes: [] };
let ws = null;
let layout = { grid: 4, cells: [], name: '' };
let cells = [];
let selected = 0;
let nextId = 1;
let statusAt = 0, statusLine = '';
let menuEl = null, menuAnchor = null;
let customWait = null;   // {cell, spec, err}: a custom interval sent from the open interval menu, awaiting the server

const $ = (s, root = document) => root.querySelector(s);
const iso = (t) => new Date(t * 1000).toISOString();
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function icon(name) { const s = mk('span', 'icw'); s.innerHTML = I[name] || ''; return s; }   // our own static SVG strings
const cur = () => cells[selected];

/* ---- layout + selection ---- */
function starter(i) { const [root, spec] = START[i % START.length]; return { root, spec, indicators: C.defaults() }; }
function saveLast() { try { localStorage.setItem('hb_charts_last', JSON.stringify(layout)); } catch (_) { /* storage off */ } }
function loadLast() {
  try {
    const v = JSON.parse(localStorage.getItem('hb_charts_last') || 'null');
    if (v && Array.isArray(v.cells)) layout = { ...C.migrateLayout(v), name: typeof v.name === 'string' ? v.name : '' };
  } catch (_) { /* unreadable: start fresh */ }
}

function hostFor(id) {
  return {
    id,
    send(msg) { if (!ws || ws.readyState !== 1) return false; ws.send(JSON.stringify(msg)); return true; },
    onPick(cell) { select(cells.indexOf(cell)); },
    onLoaded,
    onRefused,
    changed() { saveLast(); renderToolbar(); },
  };
}

function buildGrid() {
  for (const c of cells) c.destroy();
  cells = [];
  const grid = $('#grid'), [cols, rows] = GRIDS[layout.grid] || GRIDS[4], n = cols * rows;
  grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  grid.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  grid.dataset.count = String(n);
  grid.replaceChildren();
  while (layout.cells.length < n) layout.cells.push(starter(layout.cells.length));
  for (let i = 0; i < n; i++) {
    const slot = mk('div');
    grid.appendChild(slot);
    cells.push(new Cell(slot, layout.cells[i], hostFor('c' + (nextId++))));
  }
  select(Math.min(selected, n - 1));
}

function select(i) {
  if (i < 0 || i >= cells.length) return;
  selected = i;
  cells.forEach((c, k) => c.setSelected(k === i));
  renderToolbar();
}

/* ---- toolbar ---- */
function renderToolbar() {
  const c = cur();
  if (!c) return;
  const { root, spec } = c.cfg;
  $('#tbSymbolText').textContent = root;
  $('#tbSymbol').title = `${root} · ${C.rootName(root) || 'symbol'} — change symbol`;
  const favs = C.FAVOURITES.slice();
  if (!favs.some(([, s]) => s === spec)) favs.push([C.specLabel(spec), spec]);
  $('#tbFavs').replaceChildren(...favs.map(([label, s]) => {
    const b = mk('button', 'tb-btn iv' + (s === spec ? ' active' : ''), label);
    b.type = 'button';
    b.title = C.longLabel(s);
    b.setAttribute('aria-pressed', String(s === spec));
    b.onclick = () => { if (cur().cfg.spec !== s) cur().update({ spec: s }); };
    return b;
  }));
  const dark = document.documentElement.getAttribute('data-theme') === 'dark', th = $('#tbTheme');
  th.replaceChildren(icon(dark ? 'sun' : 'moon'));
  th.title = dark ? 'Light theme' : 'Dark theme';
}

/* One popup menu at a time, under its toolbar button. */
function openMenu(anchor, cls) {
  closeMenu();
  const m = mk('div', 'menu' + (cls ? ' ' + cls : ''));
  m.setAttribute('role', 'menu');
  $('#menuRoot').appendChild(m);
  menuEl = m; menuAnchor = anchor;
  anchor.classList.add('open');
  anchor.setAttribute('aria-expanded', 'true');
  return m;
}
function placeMenu() {
  if (!menuEl) return;
  const r = menuAnchor.getBoundingClientRect(), w = menuEl.offsetWidth;
  menuEl.style.left = Math.max(4, Math.min(r.left, window.innerWidth - w - 4)) + 'px';
  menuEl.style.top = (r.bottom + 4) + 'px';
}
function closeMenu() {
  if (!menuEl) return;
  menuEl.remove();
  menuAnchor.classList.remove('open');
  menuAnchor.setAttribute('aria-expanded', 'false');
  menuEl = menuAnchor = null;
  customWait = null;
}
function toggleMenu(anchor, fill) {
  if (menuAnchor === anchor) { closeMenu(); return; }
  fill();
  placeMenu();
}
function menuItem(text, sub, onPick, active) {
  const b = mk('button', 'menu-i' + (active ? ' active' : ''));
  b.type = 'button';
  b.setAttribute('role', 'menuitem');
  b.appendChild(mk('span', 'menu-t', text));
  if (sub) b.appendChild(mk('span', 'menu-sub', sub));
  b.onclick = onPick;
  return b;
}

function symbolMenu() {
  const m = openMenu($('#tbSymbol'), 'menu-sym'), input = mk('input', 'menu-input'), list = mk('div');
  input.type = 'text'; input.placeholder = 'Search'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Search symbols');
  const render = () => {
    const q = input.value.trim().toUpperCase(), c = cur();
    const hits = meta.roots.filter((r) => !q || r.includes(q) || C.rootName(r).toUpperCase().includes(q));
    list.replaceChildren(...hits.map((r) => menuItem(r, C.rootName(r), () => {
      closeMenu();
      if (c.cfg.root !== r) c.update({ root: r });
    }, r === c.cfg.root)));
    if (!hits.length) list.appendChild(mk('div', 'menu-empty', 'No matching symbol'));
  };
  input.oninput = render;
  input.onkeydown = (e) => { if (e.key === 'Enter') { const first = list.querySelector('.menu-i'); if (first) first.click(); } };
  m.append(input, list);
  render();
  input.focus();
}

function intervalMenu() {
  const m = openMenu($('#tbIntervals'), 'menu-iv'), c = cur(), spec = c.cfg.spec;
  for (const [group, specs] of C.INTERVAL_GROUPS) {
    m.appendChild(mk('div', 'menu-h', group));
    for (const s of specs) {
      m.appendChild(menuItem(C.longLabel(s), '', () => { closeMenu(); if (c.cfg.spec !== s) c.update({ spec: s }); }, s === spec));
    }
  }
  m.appendChild(mk('div', 'menu-h', 'Custom'));
  const row = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), apply = mk('button', 'btn btn-primary', 'Apply');
  const err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  input.type = 'text'; input.placeholder = 'e.g. 45s, 750T, tick:750'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Custom interval');
  apply.type = 'button';
  const go = () => {
    const s = C.toSpec(input.value);
    if (!s) { err.textContent = 'Use e.g. 45s, 2m, 4h, 1D, 750T, 3000V, 8R or tick:750'; err.hidden = false; return; }
    err.hidden = true;
    if (s === c.cfg.spec) { closeMenu(); return; }
    customWait = { cell: c, spec: s, err };
    c.update({ spec: s });
  };
  apply.onclick = go;
  input.onkeydown = (e) => { if (e.key === 'Enter') go(); };
  row.append(input, apply);
  m.append(row, err);
}

/* A custom interval the open menu sent loaded: close the menu. */
function onLoaded(cell) {
  if (customWait && customWait.cell === cell && cell.cfg.spec === customWait.spec) closeMenu();
}

/* The server refused a change (the cell already went back to its last good
   config): say why inline in the interval menu if that is where it came
   from, else in the chart's legend. */
function onRefused(cell, tried, text) {
  if (customWait && customWait.cell === cell && menuEl) {
    customWait.err.textContent = text;
    customWait.err.hidden = false;
    customWait = null;
    return;
  }
  cell.note(text);
}

function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('hb_theme', next); } catch (_) { /* storage off */ }
  for (const c of cells) c.restyle();
  renderToolbar();
}

/* ---- bottom bar ---- */
function fmtAge(a) { return a == null ? '—' : a < 60 ? `${a.toFixed(1)}s` : `${Math.round(a / 60)}m`; }

function showStatus(s) {
  const roots = s.roots || {}, rec = s.recorder, recErr = rec && rec.error, recBusy = !!(rec && rec.buffered >= 5000);
  const stale = Object.entries(roots).filter(([, x]) => (x.last_tick_age_s ?? 0) > 30)
    .sort((a, b) => b[1].last_tick_age_s - a[1].last_tick_age_s);
  $('#sbDot').className = 'sb-dot ' + (!s.connected || s.error || recErr ? 'bad' : stale.length || recBusy ? 'warn' : 'ok');
  $('#sbMode').textContent = s.mode === 'replay'
    ? `Replay ${s.date} ×${s.speed} · ${iso(s.clock_s || 0).slice(11, 19)} ET${s.done ? ' · done' : ''}`
    : s.mode === 'live' ? `Live · md ${s.md || ''}` : 'Disconnected';
  const feed = $('#sbFeed');
  feed.textContent = s.error || (recErr ? `recorder: ${recErr}` : '')
    || (stale.length ? stale.slice(0, 2).map(([r, x]) => `${r} stale ${fmtAge(x.last_tick_age_s)}`).join(' · ') : '')
    || (Object.keys(roots).length ? 'feeds ok' : '');
  feed.title = Object.entries(roots).map(([r, x]) => `${r} ${fmtAge(x.last_tick_age_s)}`).join('  ·  ');
  feed.classList.toggle('bad', !!(s.error || recErr));
  const budget = $('#sbBudget');
  budget.textContent = s.mode === 'live' ? `md ${s.budget_hour ?? 0}/180` : '';
  budget.title = s.mode === 'live' ? `Chart requests this hour on the md login (limit 180) · ${s.clients ?? 0} page(s)` : '';
  const recEl = $('#sbRec');
  recEl.textContent = s.mode === 'live' && rec ? `rec buffered ${rec.buffered.toLocaleString('en-US')}` : '';
  recEl.classList.toggle('warn', recBusy);
  statusLine = feed.textContent;
}

/* The socket is open but no status came for STATUS_STALE_S (the chart
   service is stuck, or its status broadcast is failing): grey the bar so a
   stale chart is never mistaken for a quiet market. A 'bad' dot stays bad. */
function greyIfStale() {
  if (!statusAt || !ws || ws.readyState !== 1) return;
  const age = (Date.now() - statusAt) / 1000;
  if (age < STATUS_STALE_S) return;
  const dot = $('#sbDot');
  if (!dot.classList.contains('bad')) dot.className = 'sb-dot warn';
  $('#sbFeed').textContent = `no status for ${Math.round(age)}s` + (statusLine ? ` · ${statusLine}` : '');
}

function tick() { $('#sbClock').textContent = `${ET_CLOCK.format(new Date())} ET`; greyIfStale(); }

/* ---- the chart service ---- */
function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { statusAt = Date.now(); for (const c of cells) c.subscribe(true); };
  ws.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.type === 'status') { statusAt = Date.now(); showStatus(m); return; }
    const c = cells.find((x) => x.id === m.id);
    if (!c) return;
    if (m.type === 'history') c.onHistory(m);
    else if (m.type === 'update') c.onUpdate(m);
    else if (m.type === 'reset') c.subscribe(true);
    else if (m.type === 'error') c.onError(m.error);
  };
  ws.onclose = () => { showStatus({ connected: false, error: 'chart service unreachable — retrying' }); setTimeout(connect, 2000); };
}

/* ---- keyboard ---- */
function onKey(e) {
  if (e.key === 'Escape' && menuEl) { e.preventDefault(); closeMenu(); }
}

async function init() {
  for (const n of document.querySelectorAll('[data-icon]')) n.innerHTML = I[n.dataset.icon] || '';
  $('#tbDesk').href = `${location.protocol}//${location.hostname}:8850/`;
  try { const r = await fetch('/api/symbols'); if (r.ok) meta = await r.json(); } catch (_) { /* keep the fallback */ }
  loadLast();
  $('#tbSymbol').onclick = () => toggleMenu($('#tbSymbol'), symbolMenu);
  $('#tbIntervals').onclick = () => toggleMenu($('#tbIntervals'), intervalMenu);
  $('#tbTheme').onclick = toggleTheme;
  document.addEventListener('pointerdown', (e) => {
    if (menuEl && !menuEl.contains(e.target) && !menuAnchor.contains(e.target)) closeMenu();
  }, true);
  window.addEventListener('resize', closeMenu);
  document.addEventListener('keydown', onKey);
  buildGrid();
  connect();
  tick();
  setInterval(tick, 1000);
}

window.HBCharts = { get cells() { return cells; }, get layout() { return layout; }, get selected() { return selected; }, select, buildGrid };
init();
})();
```

- [ ] **Step 7: Syntax-check every script, then run the suite**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done` then `.venv/bin/python -m pytest -q`
Expected: no `FAIL` lines; the suite passes (`test_replay_serves_history_then_live_updates` still gets 200 for `/`).

- [ ] **Step 8: Self-check against the old page** — read the old `app.js` in git (`git show HEAD:homebase/static/charts/app.js`) and confirm each behaviour listed at the top of this task has a home in the new code (write the mapping in your report). Do not start a server: the controller verifies the page in a browser on a replay.

- [ ] **Step 9: Commit**

```bash
git add homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js homebase/static/charts/cell.js homebase/static/charts/app.js homebase/static/charts/primitives.js
git commit -m "feat(charts): TradingView-style page — one toolbar for the selected chart, DOM legend, watermark, volume overlay, bottom bar with ET clock

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check after this task (replay `homebase-charts-ui-replay`, port 8854):** 2×2 grid loads; frame/panel/toolbar look per tokens; symbol pill menu + type-ahead + Enter; favourites switch the selected chart and show active in accent; a custom `tick:50` shows the server's refusal inline in the menu and the chart stays on its old interval; `45s` loads and adds a 45s button; legend title/OHLC colours/change/Vol/Δ follow the crosshair and fall back to the last bar; indicator rows show VWAP value; watermark; volume at the bottom of the price pane; footprint when zoomed in (bodies hidden); dark theme keeps the view; selection outline only with >1 chart; bottom bar replay line + ET clock ticking; zero console errors.

---

### Task 5: Grid picker, saved layouts, the Indicators and Settings dialogs, legend row actions

**Files:**
- Modify: `homebase/static/charts/cell.js`
- Modify: `homebase/static/charts/app.js`

**Interfaces:**
- Consumes: Task 4's page (`layout`, `cells`, `selected`, `menuEl`, `menuAnchor`, `GRIDS`, `mk`, `icon`, `$`, `cur`, `openMenu`, `placeMenu`, `closeMenu`, `toggleMenu`, `menuItem`, `renderToolbar`, `buildGrid`, `saveLast`, `hostFor`, `onKey`, `init`) and Cell (`cfg`, `update(patch)`, `lastGood`, `pending`, `lines`, `rows`, `hover`, `legendRows()`, `legend(i)`, `drawLevels()`, `drawMarkers()`, `syncFootprint()`, `syncProfile()`, `host`); `HBCatalog` (`GROUPS`, `filter`, `instance`, `def`, `clampParams`, `migrateLayout`, `label`); `GET /api/layouts`, `PUT/DELETE /api/layouts/{name}` (same-origin page: passes Task 1's Origin check).
- Produces: `host.onSettings(cell, uid)`; `Cell.setVisible(uid, on)`, `Cell.onLegendClick(e)`; legend rows with `.lg-btns` holding `button.ib[data-act=eye|gear|x]` (gear only for indicators with params); page functions `gridMenu()`, `layoutMenu(saveAsFirst)`, `save()`, `loadLayout(name, saved)`, `putLayout(name)`, `indicatorsDialog()`, `settingsDialog(cell, uid)`, `openDialog(title, cls)`, `closeDialog()`, `trapTab(e)`, variable `dlg` (Task 6's `onKey` builds on this one).

- [ ] **Step 1: `cell.js` — legend row buttons and hide/show.** Add this helper next to `kv()`:

```js
function iconButton(name, title, act) {
  const b = mk('button', 'ib');
  b.type = 'button';
  b.title = title;
  b.dataset.act = act;
  b.setAttribute('aria-label', title);
  b.innerHTML = window.HBIcons[name] || '';   // our own static SVG strings
  return b;
}
```

In the constructor, after the `slot.addEventListener('pointerdown', ...)` line, add:

```js
    this.lg.inds.addEventListener('click', (e) => this.onLegendClick(e));
```

Replace `legendRows()` with:

```js
  legendRows() {
    this.rows = this.cfg.indicators.map((inst) => {
      const off = inst.visible === false, row = mk('div', 'lg-row' + (off ? ' off' : '')), vals = mk('span', 'lg-vals');
      const btns = mk('span', 'lg-btns');
      btns.append(iconButton(off ? 'eyeOff' : 'eye', off ? 'Show' : 'Hide', 'eye'));
      if (C.def(inst.id).params.length) btns.append(iconButton('gear', 'Settings', 'gear'));
      btns.append(iconButton('x', 'Remove', 'x'));
      row.dataset.uid = inst.uid;
      row.append(mk('span', 'lg-label', C.label(inst)), vals, btns);
      return { inst, row, vals };
    });
    this.lg.inds.replaceChildren(...this.rows.map((r) => r.row));
  }

  onLegendClick(e) {
    const b = e.target.closest('button[data-act]');
    if (!b) return;
    const uid = b.closest('.lg-row').dataset.uid, inst = this.cfg.indicators.find((x) => x.uid === uid);
    if (!inst) return;
    if (b.dataset.act === 'eye') this.setVisible(uid, inst.visible === false);
    else if (b.dataset.act === 'gear') this.host.onSettings(this, uid);
    else this.update({ indicators: this.cfg.indicators.filter((x) => x.uid !== uid) });
  }

  /* Client-only: the stream keeps computing a hidden study, so the toggle is instant. */
  setVisible(uid, on) {
    const inst = this.cfg.indicators.find((x) => x.uid === uid);
    if (!inst) return;
    inst.visible = on;
    const good = this.lastGood && this.lastGood.indicators.find((x) => x.uid === uid);
    if (good) good.visible = on;   // a later revert must not undo a hide/show
    this.host.changed();
    for (const l of this.lines) if (l.uid === uid) l.s.applyOptions({ visible: on });
    this.drawLevels(); this.drawMarkers(); this.syncFootprint(); this.syncProfile();
    this.legendRows();
    this.legend(this.hover);
  }
```

- [ ] **Step 2: `app.js` — grid picker.** Add after `GRIDS`:

```js
const GRID_NAMES = { 1: '1 chart', 2: '2 charts side by side', 4: '2 × 2 charts', 6: '3 × 2 charts' };
```

Add these functions in the toolbar section:

```js
function thumb(n, into) {
  const [cols, rows] = GRIDS[n];
  into.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  into.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
  into.replaceChildren(...Array.from({ length: cols * rows }, () => document.createElement('i')));
  return into;
}

function gridMenu() {
  const m = openMenu($('#tbGrid'), 'menu-grid'), picks = mk('div', 'grid-picks');
  for (const n of [1, 2, 4, 6]) {
    const b = mk('button', 'grid-pick' + (layout.grid === n ? ' active' : ''));
    b.type = 'button';
    b.title = GRID_NAMES[n];
    b.setAttribute('aria-label', GRID_NAMES[n]);
    b.appendChild(thumb(n, mk('span', 'thumb')));
    b.onclick = () => { closeMenu(); if (layout.grid !== n) { layout.grid = n; saveLast(); buildGrid(); } };
    picks.appendChild(b);
  }
  m.appendChild(picks);
}
```

At the end of `renderToolbar()` add:

```js
  thumb(layout.grid, $('#tbGridThumb'));
  $('#tbGrid').title = `Chart layout: ${GRID_NAMES[layout.grid]}`;
  $('#tbLayoutName').textContent = layout.name || 'Unsaved';
```

- [ ] **Step 3: `app.js` — saved layouts.** Add a `/* ---- saved layouts ---- */` section:

```js
async function fetchLayouts() {
  try { const r = await fetch('/api/layouts'); return r.ok ? await r.json() : {}; } catch (_) { return {}; }
}

/* PUT the current layout under `name`: '' when saved, else the reason. */
async function putLayout(name) {
  const body = { grid: layout.grid, cells: layout.cells.map(({ root, spec, indicators }) => ({ root, spec, indicators })) };
  let r;
  try {
    r = await fetch('/api/layouts/' + encodeURIComponent(name), { method: 'PUT',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  } catch (e) { return 'save failed: ' + (e && e.message ? e.message : 'network error'); }
  if (r.ok) return '';
  let detail = '';
  try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
  return `save failed (${r.status})` + (detail ? ': ' + detail : '');
}

let saveMsgTimer = 0;
function saveMsg(text, err = false) {
  const m = $('#tbSaveMsg');
  m.textContent = text;
  m.classList.toggle('err', err);
  clearTimeout(saveMsgTimer);
  if (text && !err) saveMsgTimer = setTimeout(() => { m.textContent = ''; }, 2000);
}

/* Save to the loaded layout's name; with none yet, ask for one in the layouts menu. */
async function save() {
  if (!layout.name) { if (menuAnchor !== $('#tbLayout')) toggleMenu($('#tbLayout'), () => layoutMenu(true)); return; }
  const why = await putLayout(layout.name);
  saveMsg(why || 'Saved', !!why);
}

function loadLayout(name, saved) {
  layout = { ...C.migrateLayout(saved), name };
  saveLast();
  selected = 0;
  buildGrid();
}

async function layoutMenu(saveAsFirst = false) {
  const m = openMenu($('#tbLayout'), 'menu-layouts'), list = mk('div'), err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const saveAs = menuItem('Save layout as…', '', () => askName());
  m.append(mk('div', 'menu-h', 'Saved layouts'), list, mk('div', 'menu-sep'), saveAs, err);
  const fail = (text) => { err.textContent = text; err.hidden = false; placeMenu(); };

  function askName() {
    const row = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), ok = mk('button', 'btn btn-primary', 'Save');
    input.type = 'text'; input.placeholder = 'Layout name'; input.maxLength = 80; input.value = layout.name;
    input.setAttribute('aria-label', 'Layout name');
    ok.type = 'button';
    const go = async () => {
      const name = input.value.trim();
      if (!name) { input.focus(); return; }
      const why = await putLayout(name);
      if (why) { fail(why); return; }
      layout.name = name;
      saveLast(); renderToolbar(); closeMenu(); saveMsg('Saved');
    };
    ok.onclick = go;
    input.onkeydown = (e) => { if (e.key === 'Enter') go(); };
    row.append(input, ok);
    saveAs.replaceWith(row);
    input.focus();
    input.select();
  }

  function confirmDelete(row, name) {
    const box = mk('div', 'menu-confirm'), yes = mk('button', 'btn btn-danger', 'Delete'), no = mk('button', 'btn btn-ghost', 'Cancel');
    yes.type = 'button';
    no.type = 'button';
    box.append(mk('span', '', `Delete “${name}”?`), yes, no);
    row.replaceWith(box);
    no.onclick = () => box.replaceWith(row);
    yes.onclick = async () => {
      let r = null;
      try { r = await fetch('/api/layouts/' + encodeURIComponent(name), { method: 'DELETE' }); } catch (_) { /* r stays null */ }
      if (!r || !r.ok) { box.replaceWith(row); fail(`delete failed${r ? ` (${r.status})` : ': network error'}`); return; }
      box.remove();
      if (layout.name === name) { layout.name = ''; saveLast(); renderToolbar(); }
      if (!list.querySelector('.menu-row')) list.replaceChildren(mk('div', 'menu-empty', 'No saved layouts yet'));
    };
  }

  if (saveAsFirst) askName();
  const all = await fetchLayouts();
  if (menuEl !== m) return;   // closed while loading
  const names = Object.keys(all).sort((a, b) => a.localeCompare(b));
  if (!names.length) list.appendChild(mk('div', 'menu-empty', 'No saved layouts yet'));
  for (const name of names) {
    const row = mk('div', 'menu-row'), del = mk('button', 'menu-del');
    del.type = 'button';
    del.title = `Delete ${name}`;
    del.setAttribute('aria-label', `Delete ${name}`);
    del.appendChild(icon('x'));
    del.onclick = () => confirmDelete(row, name);
    row.append(menuItem(name, '', () => { closeMenu(); loadLayout(name, all[name]); }, name === layout.name), del);
    list.appendChild(row);
  }
  placeMenu();
}
```

- [ ] **Step 4: `app.js` — dialogs.** Add `let dlg = null;   // the open dialog: {back, box, focus}` to the state, and a `/* ---- dialogs ---- */` section:

```js
function openDialog(title, cls) {
  closeMenu();
  closeDialog();
  const back = mk('div', 'backdrop'), box = mk('div', 'dialog' + (cls ? ' ' + cls : '')), head = mk('div', 'dlg-head');
  const x = mk('button', 'dlg-x');
  x.type = 'button';
  x.title = 'Close';
  x.setAttribute('aria-label', 'Close');
  x.appendChild(icon('x'));
  x.onclick = closeDialog;
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.setAttribute('aria-label', title);
  head.append(mk('span', '', title), x);
  box.appendChild(head);
  back.appendChild(box);
  back.addEventListener('pointerdown', (e) => { if (e.target === back) closeDialog(); });
  $('#dialogRoot').appendChild(back);
  dlg = { back, box, focus: document.activeElement };
  return box;
}

function closeDialog() {
  if (!dlg) return;
  const { back, focus } = dlg;
  dlg = null;
  back.remove();
  if (focus && typeof focus.focus === 'function' && document.contains(focus)) focus.focus();
}

function trapTab(e) {   // Tab stays inside the open dialog
  const f = [...dlg.box.querySelectorAll('button, input')].filter((x) => !x.disabled && x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/* TradingView's Indicators dialog: search, groups, click a name to add it
   (with defaults) to the selected chart; the dialog stays open. */
function indicatorsDialog() {
  const c = cur();
  if (!c) return;
  const box = openDialog('Indicators');
  const search = mk('label', 'dlg-search'), input = mk('input');
  input.type = 'search'; input.placeholder = 'Search'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Search indicators');
  search.append(icon('search'), input);
  const body = mk('div', 'dlg-body'), groups = mk('div', 'dlg-groups'), list = mk('div', 'dlg-list');
  body.append(groups, list);
  box.append(search, body);
  let group = 'All';
  const render = () => {
    const q = input.value.trim(), hits = C.filter(q, group);
    list.replaceChildren(...hits.map((d) => {
      const row = mk('button', 'dlg-row');
      row.type = 'button';
      row.title = `Add ${d.name}`;
      row.append(mk('span', 'dlg-name', d.name));
      if (q && group === 'All') row.append(mk('span', 'dlg-grp', d.group));
      if (c.cfg.indicators.some((x) => x.id === d.id)) row.append(icon('check'));
      row.onclick = () => { c.update({ indicators: [...c.cfg.indicators, C.instance(d.id)] }); render(); };
      return row;
    }));
    if (!hits.length) list.appendChild(mk('div', 'dlg-empty', 'No indicators match'));
  };
  const renderGroups = () => groups.replaceChildren(...C.GROUPS.map((g) => {
    const b = mk('button', 'dlg-group' + (g === group ? ' active' : ''), g);
    b.type = 'button';
    b.onclick = () => { group = g; renderGroups(); render(); };
    return b;
  }));
  input.oninput = render;
  input.onkeydown = (e) => { if (e.key === 'Enter') { const first = list.querySelector('.dlg-row'); if (first) first.click(); } };
  renderGroups();
  render();
  input.focus();
}

/* The gear on a legend row: one field per param; OK clamps, applies, resubscribes if needed. */
function settingsDialog(cell, uid) {
  const inst = cell.cfg.indicators.find((x) => x.uid === uid), d = inst && C.def(inst.id);
  if (!d || !d.params.length) return;
  const box = openDialog(d.name, 'small'), form = mk('div', 'dlg-fields'), vals = { ...inst.params };
  for (const p of d.params) {
    const row = mk('div', 'field'), id = `f-${uid}-${p.key}`, lab = mk('label', '', p.label);
    let ctl;
    if (p.type === 'bool') {
      ctl = mk('input');
      ctl.type = 'checkbox';
      ctl.checked = !!vals[p.key];
      ctl.onchange = () => { vals[p.key] = ctl.checked; };
    } else if (p.type === 'choice') {
      ctl = mk('div', 'seg');
      ctl.setAttribute('role', 'radiogroup');
      ctl.setAttribute('aria-label', p.label);
      const draw = () => ctl.replaceChildren(...p.choices.map(([v, text]) => {
        const b = mk('button', vals[p.key] === v ? 'on' : '', text);
        b.type = 'button';
        b.setAttribute('role', 'radio');
        b.setAttribute('aria-checked', String(vals[p.key] === v));
        b.onclick = () => { vals[p.key] = v; draw(); };
        return b;
      }));
      draw();
    } else {
      ctl = mk('input');
      ctl.type = 'number';
      ctl.min = p.min; ctl.max = p.max; ctl.step = p.step || 1;
      ctl.value = vals[p.key];
      ctl.oninput = () => { vals[p.key] = ctl.value; };
    }
    ctl.id = id;
    lab.htmlFor = id;
    row.append(lab, ctl);
    form.appendChild(row);
  }
  const foot = mk('div', 'dlg-foot'), cancel = mk('button', 'btn btn-ghost', 'Cancel'), ok = mk('button', 'btn btn-primary', 'OK');
  cancel.type = 'button';
  ok.type = 'button';
  cancel.onclick = closeDialog;
  ok.onclick = () => {
    const params = C.clampParams(inst.id, vals);
    closeDialog();
    cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? { ...x, params } : x)) });
  };
  form.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') ok.click(); });
  foot.append(cancel, ok);
  box.append(form, foot);
  const first = form.querySelector('input, button');
  if (first) first.focus();
}
```

- [ ] **Step 5: `app.js` — wiring.** In `hostFor(id)` add `onSettings(cell, uid) { settingsDialog(cell, uid); },`. Replace `onKey` with:

```js
function onKey(e) {
  if (dlg) {
    if (e.key === 'Escape') { e.preventDefault(); closeDialog(); }
    else if (e.key === 'Tab') trapTab(e);
    return;
  }
  if (e.key === 'Escape' && menuEl) { e.preventDefault(); closeMenu(); }
}
```

In `init()`, next to the other toolbar handlers, add:

```js
  $('#tbIndicators').onclick = indicatorsDialog;
  $('#tbGrid').onclick = () => toggleMenu($('#tbGrid'), gridMenu);
  $('#tbLayout').onclick = () => toggleMenu($('#tbLayout'), () => layoutMenu(false));
  $('#tbSave').onclick = save;
```

- [ ] **Step 6: Syntax-check and run the suite**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done` then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; suite passes.

- [ ] **Step 7: Commit**

```bash
git add homebase/static/charts/cell.js homebase/static/charts/app.js
git commit -m "feat(charts): grid picker, saved layouts menu, Indicators and Settings dialogs, legend hide/settings/remove

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check after this task:** grid picker 1 / 2 / 2×2 / 3×2 (toolbar thumbnail follows); Save with no name opens "Save layout as…", Save again flashes "Saved", load another layout, delete with the inline confirm, a Build-1 layout (st form) loads migrated; Indicators dialog: search, groups, add EMA twice (two rows, two colours), the check mark, Enter adds the first hit, Esc / × / backdrop close, Tab stays inside; gear: EMA 20 → 50 relabels and redraws; VWAP anchor RTH + bands; eye hides instantly (row at 50%); × removes; zero console errors.

---

### Task 6: Drawing tools — rail, canvas layer, pointer controller, per-symbol persistence

**Files:**
- Modify: `homebase/static/charts/drawings.js` (add the browser half)
- Modify: `homebase/static/charts/cell.js`
- Modify: `homebase/static/charts/app.js`

**Interfaces:**
- Consumes: Task 3's pure API and `Store` (same file); Cell (`el`, `box`, `chart`, `candles`, `bars`, `tick`, `P` incl. `accent`, `accentSoft`, `down`, `downSoft`, `bg`; `shown`, `isTime()`, `barMs()`, `build(view)`, `teardown()`, `host`); `HBCell.FONT`; the page (`hostFor`, `cells`, `cur`, `onKey`, `dlg`, `menuEl`, `closeMenu`, `init`, `$`); the `#rail` markup and `.rail-btn[aria-pressed]`, `.rail-btn.arm`, `.rail-tip`, `.panel[data-cursor]` styles (Task 4).
- Produces: `HBDrawings.Primitive`, `HBDrawings.Controller(cell, host)` with `sel`, `root`, `toolChanged()` (re-reads `host.tool()`), `escape() -> bool`, `deleteSelected() -> bool`, `refresh()`, `destroy()`; `Cell.dc` (the chart's controller, rebuilt with the chart); host additions `tool()`, `toolDone()`, `drawings` (one page-wide `Store`); page `setTool(t)`, `sbNote(text)`, `clearDrawings()`.

Interaction contract (spec): pick a tool on the rail (active = accent on accent-soft; clicking the active tool again returns to cursor). Trend/rectangle: press-drag-release, or click, move, click — a live preview follows the pointer. Horizontal line: one click. Measure: same gestures; shows `+12.50 (+0.04%) · 50 ticks` / `8 bars · 8m`, blue up / red down; the next press anywhere in that chart or Esc removes it. After placing, the tool returns to cursor and the new drawing is selected. Cursor mode: hovering a drawing shows a move cursor; press on it selects it (handles: 4px white dots, accent stroke) and dragging moves it; dragging a handle moves that point; release saves; a press on empty chart deselects and pans as usual. Delete/Backspace removes the selected drawing (not while typing); Esc cancels a placement / measure, else deselects, and returns the rail to cursor. Remove all (trash): first click arms it red with a tip "Click again to remove N drawings on NQ" for 3 s; the second click clears that symbol. Only the price pane takes drawings.

- [ ] **Step 1: `drawings.js` — the browser half.** Insert this block just before `const api = {` (it touches no browser global at load time, so the Node tests keep loading the file):

```js
/* ---------------- browser half: canvas primitive + pointer controller ---------------- */
const MOVE_PX = 4;   // a press that moves less than this is a click, not a drag

/* Draws one chart's trend lines and rectangles, the drawing being placed,
   the selected drawing's handles and the measure box, as a series
   primitive on the candles (so only in the price pane). Horizontal lines
   are native price lines kept by the controller, so their price tag sits
   on the axis; this layer only draws a selected one's handle. */
class Primitive {
  constructor(ctl) {
    this.ctl = ctl;
    this.views = [{ zOrder: () => 'top', renderer: () => ({ draw: (target) => this.draw(target) }) }];
  }
  attached({ requestUpdate }) { this.requestUpdate = requestUpdate; }
  detached() { this.requestUpdate = null; }
  updateAllViews() {}
  paneViews() { return this.views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }
  draw(target) {
    const c = this.ctl, geo = c.geo();
    if (!geo) return;
    const P = c.cell.P;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (const d of c.items()) if (d.type !== 'hline') drawShape(ctx, d, geo, P);
      if (c.place) drawShape(ctx, c.place, geo, P);
      const sel = c.selectedDrawing(), hs = sel && handlePoints(sel, geo);
      if (hs) {
        ctx.fillStyle = P.bg;
        ctx.strokeStyle = sel.color || P.accent;
        ctx.lineWidth = 1.5;
        for (const [x, y] of hs) { ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
      }
      if (c.measure) drawMeasure(ctx, c.measure, geo, P, c.ctx(), mediaSize);
    });
  }
}

function drawShape(ctx, d, geo, P) {
  const hs = handlePoints(d, geo);
  if (!hs) return;
  const [[x0, y0], [x1, y1]] = hs;
  ctx.strokeStyle = d.color || P.accent;
  if (d.type === 'trend') {
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    return;
  }
  const x = Math.min(x0, x1), y = Math.min(y0, y1), w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
  ctx.fillStyle = P.accentSoft;
  ctx.fillRect(x, y, w, h);
  ctx.lineWidth = 1;
  ctx.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, Math.round(w), Math.round(h));
}

function drawMeasure(ctx, m, geo, P, mctx, size) {
  const x0 = geo.x(m.a.t), x1 = geo.x(m.b.t), y0 = geo.y(m.a.p), y1 = geo.y(m.b.p);
  if (x0 == null || x1 == null || y0 == null || y1 == null) return;
  const up = m.b.p >= m.a.p, col = up ? P.accent : P.down;
  const left = Math.min(x0, x1), top = Math.min(y0, y1), w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
  ctx.fillStyle = up ? P.accentSoft : P.downSoft;
  ctx.fillRect(left, top, w, h);
  ctx.strokeStyle = col;
  ctx.lineWidth = 1;
  const mx = Math.round(left + w / 2) + 0.5, my = Math.round(top + h / 2) + 0.5;
  ctx.beginPath(); ctx.moveTo(mx, y0); ctx.lineTo(mx, y1); ctx.moveTo(x0, my); ctx.lineTo(x1, my); ctx.stroke();
  const lines = measureLabel(m.a, m.b, mctx);
  ctx.font = `12px ${window.HBCell.FONT}`;
  const bw = Math.max(...lines.map((t) => ctx.measureText(t).width)) + 16, bh = 38;
  const bx = Math.max(2, Math.min(left + w / 2 - bw / 2, size.width - bw - 2));
  const by = Math.max(2, Math.min(up ? top - bh - 6 : top + h + 6, size.height - bh - 2));
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 4); ctx.fill();
  ctx.fillStyle = '#FFFFFF';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(lines[0], bx + bw / 2, by + 11);
  ctx.fillText(lines[1], bx + bw / 2, by + 27);
}

/* One chart's drawing interaction. The tool comes from the page's rail
   (host.tool()); drawings live in the page's per-symbol store
   (host.drawings), so every chart of the symbol shows the same ones. */
class Controller {
  constructor(cell, host) {
    this.cell = cell; this.host = host; this.root = cell.shown.root; this.box = cell.box;
    this.sel = null;       // id of the selected drawing
    this.place = null;     // a trend line / rectangle being placed: {type, points}
    this.measure = null;   // {a, b, done}
    this.mode = null;      // placing: 'drag' (button held since the first point) | 'click' (waiting for the 2nd click)
    this.downAt = null;    // pane point of the press that started placing
    this.drag = null;      // moving / reshaping: {orig, part, index, from, cur}
    this.owned = false;    // this gesture switched the chart's panning off
    this.hlines = new Map();   // drawing id -> its price line
    this.prim = new Primitive(this);
    cell.candles.attachPrimitive(this.prim);
    this.on = { down: (e) => this.onDown(e), move: (e) => this.onMove(e), up: (e) => this.onUp(e),
      hover: (e) => this.onHover(e), leave: () => this.setCursor(null) };
    this.box.addEventListener('pointerdown', this.on.down, true);
    this.box.addEventListener('pointermove', this.on.hover);
    this.box.addEventListener('pointerleave', this.on.leave);
    window.addEventListener('pointermove', this.on.move, true);
    window.addEventListener('pointerup', this.on.up, true);
    this.off = host.drawings.subscribe(this.root, () => this.refresh());
    host.drawings.ensure(this.root);
    this.refresh();
    this.toolChanged();
  }

  destroy() {   // before the chart is removed (it takes its price lines and primitives with it)
    this.box.removeEventListener('pointerdown', this.on.down, true);
    this.box.removeEventListener('pointermove', this.on.hover);
    this.box.removeEventListener('pointerleave', this.on.leave);
    window.removeEventListener('pointermove', this.on.move, true);
    window.removeEventListener('pointerup', this.on.up, true);
    this.off();
    this.release();
    delete this.cell.el.dataset.cursor;
    this.hlines.clear();
  }

  /* The symbol's drawings, with one being dragged shown where it is now. */
  items() {
    const list = this.host.drawings.list(this.root), cur = this.drag && this.drag.cur;
    return cur ? list.map((d) => (d.id === cur.id ? cur : d)) : list;
  }
  selectedDrawing() { return this.sel ? this.items().find((d) => d.id === this.sel) || null : null; }
  ctx() {
    const c = this.cell, ts = c.chart.timeScale();
    return { bars: c.bars, isTime: c.isTime(), barMs: c.barMs(), tick: c.tick, coord: (i) => ts.logicalToCoordinate(i) };
  }
  geo() {
    const c = this.cell;
    if (!c.chart || !c.bars.length) return null;
    const ctx = this.ctx();
    return { x: (t) => timeToX(t, ctx), y: (p) => c.candles.priceToCoordinate(p), w: this.paneW() };
  }
  paneW() { return this.box.clientWidth - this.cell.chart.priceScale('right').width(); }
  paneH() { return this.cell.chart.panes()[0].getHeight(); }
  local(e) { const r = this.box.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  inPane(pt) { return pt.x >= 0 && pt.x < this.paneW() && pt.y >= 0 && pt.y < this.paneH(); }

  /* The bar-snapped time and tick-rounded price under a pane point. */
  at(pt) {
    const c = this.cell, L = c.chart.timeScale().coordinateToLogical(pt.x), p = c.candles.coordinateToPrice(pt.y);
    if (L == null || p == null || !c.bars.length) return null;
    return { t: snapTime(L, c.bars, c.isTime(), c.barMs()), p: roundToTick(p, c.tick), L };
  }

  setCursor(kind) {
    const k = kind || (this.host.tool() === 'cursor' ? null : 'crosshair');
    if (k) this.cell.el.dataset.cursor = k; else delete this.cell.el.dataset.cursor;
  }

  /* Price lines for the horizontal lines; a canvas redraw for the rest. */
  refresh() {
    if (!this.cell.candles) return;
    const P = this.cell.P, seen = new Set();
    for (const d of this.items()) {
      if (d.type !== 'hline') continue;
      seen.add(d.id);
      const opts = { price: d.points[0].p, color: d.color || P.accent, lineWidth: d.id === this.sel ? 2 : 1,
        lineStyle: window.LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: '' };
      const line = this.hlines.get(d.id);
      if (line) line.applyOptions(opts); else this.hlines.set(d.id, this.cell.candles.createPriceLine(opts));
    }
    for (const [id, line] of this.hlines) {
      if (!seen.has(id)) { this.cell.candles.removePriceLine(line); this.hlines.delete(id); }
    }
    if (this.sel && !this.selectedDrawing()) this.sel = null;
    this.prim.redraw();
  }

  /* This gesture is ours. Lightweight Charts 5.2.1 listens to mouse events
     only: preventDefault() on pointerdown suppresses the mousedown/move/up it
     would pan with; panning and zooming also stay off until release(). */
  own(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!this.owned) { this.owned = true; this.cell.chart.applyOptions({ handleScroll: false, handleScale: false }); }
  }
  release() {
    if (!this.owned) return;
    this.owned = false;
    if (this.cell.chart) this.cell.chart.applyOptions({ handleScroll: true, handleScale: true });
  }

  onDown(e) {
    if (e.button !== 0 || !this.cell.chart) return;
    const pt = this.local(e), tool = this.host.tool();
    if (this.measure && this.measure.done) { this.measure = null; this.prim.redraw(); }
    if (!this.inPane(pt)) return;
    if (tool !== 'cursor') {
      const at = this.at(pt);
      if (!at) return;
      this.own(e);
      if (this.mode === 'click') { this.finish(at); return; }
      if (tool === 'hline') { this.commit({ type: 'hline', points: [{ p: at.p }] }); return; }
      const start = { t: at.t, p: at.p };
      if (tool === 'measure') this.measure = { a: start, b: start, done: false };
      else this.place = { type: tool, points: [start, start] };
      this.mode = 'drag';
      this.downAt = pt;
      this.prim.redraw();
      return;
    }
    const geo = this.geo();
    if (!geo) return;
    const sel = this.selectedDrawing();
    let d = null, hit = sel ? hitTest(sel, pt, geo) : null;
    if (hit && hit.part === 'handle') d = sel;
    else {
      hit = null;
      const all = this.items();
      for (let i = all.length - 1; i >= 0 && !d; i--) { const h = hitTest(all[i], pt, geo); if (h) { d = all[i]; hit = h; } }
    }
    if (!d) { if (this.sel) { this.sel = null; this.refresh(); } return; }   // empty chart: deselect, let it pan
    this.own(e);
    this.sel = d.id;
    this.drag = { orig: d, part: hit.part, index: hit.index, from: this.at(pt), cur: null };
    this.setCursor('grabbing');
    this.refresh();
  }

  onMove(e) {
    if (!this.cell.chart) return;
    if (this.place || (this.measure && !this.measure.done)) {
      const at = this.at(this.local(e));
      if (!at) return;
      const end = { t: at.t, p: at.p };
      if (this.place) this.place = { ...this.place, points: [this.place.points[0], end] };
      else this.measure = { ...this.measure, b: end };
      this.prim.redraw();
      return;
    }
    if (!this.drag || !this.drag.from) return;
    const at = this.at(this.local(e));
    if (!at) return;
    const { orig, part, index, from } = this.drag;
    this.drag.cur = part === 'handle' ? setPoint(orig, index, at.t, at.p)
      : moveDrawing(orig, Math.round(at.L) - Math.round(from.L), at.p - from.p, this.cell.tick, this.ctx());
    this.refresh();
  }

  onUp(e) {
    if (!this.cell.chart) return;
    if (this.place || (this.measure && !this.measure.done)) {
      if (this.mode !== 'drag') return;
      const pt = this.local(e);
      if (Math.hypot(pt.x - this.downAt.x, pt.y - this.downAt.y) < MOVE_PX) { this.mode = 'click'; this.release(); return; }
      const at = this.at(pt);
      if (at) this.finish(at);
      return;
    }
    if (!this.drag) return;
    const moved = this.drag.cur;
    this.drag = null;
    this.release();
    this.setCursor(null);
    if (moved) this.host.drawings.replace(this.root, moved); else this.refresh();
  }

  finish(at) {
    const end = { t: at.t, p: at.p };
    this.mode = null;
    this.downAt = null;
    this.release();
    if (this.measure && !this.measure.done) {
      this.measure = { ...this.measure, b: end, done: true };
      this.prim.redraw();
      this.host.toolDone();
      return;
    }
    const d = { ...this.place, points: [this.place.points[0], end] };
    this.place = null;
    const [a, b] = d.points;
    if (a.t === b.t && a.p === b.p) { this.prim.redraw(); this.host.toolDone(); return; }   // nothing to draw
    this.commit(d);
  }

  commit(d) {
    const full = { id: newId(), ...d, color: '#2962FF' };
    this.sel = full.id;
    this.release();
    this.host.drawings.add(this.root, full);   // every chart of this symbol refreshes
    this.host.toolDone();
  }

  toolChanged() {
    if (this.place || (this.measure && !this.measure.done)) {
      this.place = null; this.measure = null; this.mode = null; this.downAt = null;
      this.release();
      this.prim.redraw();
    }
    this.setCursor(null);
  }

  escape() {
    if (this.place || this.measure) {
      this.place = null; this.measure = null; this.mode = null; this.downAt = null;
      this.release();
      this.prim.redraw();
      return true;
    }
    if (this.sel) { this.sel = null; this.refresh(); return true; }
    return false;
  }

  deleteSelected() {
    if (!this.sel) return false;
    const id = this.sel;
    this.sel = null;
    this.host.drawings.remove(this.root, id);
    return true;
  }

  onHover(e) {
    if (this.drag || this.place || e.buttons || this.host.tool() !== 'cursor' || !this.cell.chart) return;
    const pt = this.local(e), geo = this.geo();
    const over = !!geo && this.inPane(pt) && this.items().some((d) => hitTest(d, pt, geo));
    this.setCursor(over ? 'move' : null);
  }
}
```

Add `Primitive, Controller` to the `api` object. Update the file's header comment: the second paragraph now says the file also holds the canvas primitive and the pointer controller (browser half, below the store).

- [ ] **Step 2: `cell.js` — one controller per chart.** In the constructor's field list add `this.dc = null;   // the drawing controller of the current chart`. At the start of `teardown()` (before `this.chart.remove()`), add:

```js
    if (this.dc) { this.dc.destroy(); this.dc = null; }
```

Replace `build(view)` with this version — the same body as Task 4's, plus: it keeps the selected drawing across rebuilds (theme toggle, indicator change) and creates the chart's controller last:

```js
  build(view) {
    const sel = this.dc && this.shown && this.dc.root === this.shown.root ? this.dc.sel : null;
    this.makeChart();
    this.candles.setData(this.bars.map((b) => this.candle(b)));
    this.buildSeries();
    for (const l of this.lines) l.s.setData(this.bars.map((b) => this.point(l, b)));
    this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint(); this.syncProfile();
    // Pane heights as px-sized stretch factors. Not setHeight(): it spreads each change using the laid-out
    // heights, and panes added this pass are still 0 px, so with 2+ sub-panes only the last one got PANE_H.
    const panes = this.chart.panes(), subs = panes.length - 1;
    if (subs) {
      panes[0].setStretchFactor(Math.max(PANE_H, panes[0].getHeight() - subs * PANE_H));   // pane 0 still holds the whole plot
      for (let i = 1; i <= subs; i++) panes[i].setStretchFactor(PANE_H);
    }
    if (view) this.setView(view); else this.chart.timeScale().scrollToRealTime();
    this.lg.badge.hidden = !this.sessions.some((s) => s.approx);
    this.legendRows();
    this.legend(null);
    this.dc = new window.HBDrawings.Controller(this, this.host);
    if (sel) { this.dc.sel = sel; this.dc.refresh(); }
  }
```

- [ ] **Step 3: `app.js` — tools, the store, remove-all, keys.** Add to the state:

```js
let tool = 'cursor';
let noteTimer = 0, armTimer = 0;
const drawings = new window.HBDrawings.Store({ onError: (root, msg) => sbNote(`${root} drawings: ${msg}`) });
```

In `hostFor(id)` add:

```js
    tool: () => tool,
    toolDone() { setTool('cursor'); },
    drawings,
```

Add a `/* ---- drawing rail ---- */` section:

```js
function setTool(t) {
  tool = t;
  for (const b of document.querySelectorAll('#rail [data-tool]')) b.setAttribute('aria-pressed', String(b.dataset.tool === t));
  for (const c of cells) if (c.dc) c.dc.toolChanged();
}

function sbNote(text) {
  const el = $('#sbNote');
  el.textContent = text;
  clearTimeout(noteTimer);
  noteTimer = setTimeout(() => { el.textContent = ''; }, 8000);
}

function showTip(anchor, text) {
  const tip = $('#railTip'), r = anchor.getBoundingClientRect();
  tip.textContent = text;
  tip.hidden = false;
  tip.style.left = `${r.right + 8}px`;
  tip.style.top = `${r.top + r.height / 2 - tip.offsetHeight / 2}px`;
}

function disarm() {
  clearTimeout(armTimer);
  $('#railClear').classList.remove('arm');
  $('#railTip').hidden = true;
}

/* Remove every drawing on the selected chart's symbol: the first click arms, the second (within 3 s) removes. */
function clearDrawings() {
  const c = cur(), btn = $('#railClear');
  if (!c) return;
  const root = c.shown ? c.shown.root : c.cfg.root, n = drawings.list(root).length;
  if (btn.classList.contains('arm')) { disarm(); drawings.clear(root); return; }
  clearTimeout(armTimer);
  if (!n) { showTip(btn, `No drawings on ${root}`); armTimer = setTimeout(disarm, 1500); return; }
  btn.classList.add('arm');
  showTip(btn, `Click again to remove ${n} drawing${n === 1 ? '' : 's'} on ${root}`);
  armTimer = setTimeout(disarm, 3000);
}
```

Replace `onKey` with:

```js
function onKey(e) {
  if (dlg) {
    if (e.key === 'Escape') { e.preventDefault(); closeDialog(); }
    else if (e.key === 'Tab') trapTab(e);
    return;
  }
  if (e.key === 'Escape' && menuEl) { e.preventDefault(); closeMenu(); return; }
  if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
  const c = cur();
  if (e.key === 'Escape') {
    if (c && c.dc) c.dc.escape();
    if (tool !== 'cursor') setTool('cursor');
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && c && c.dc && c.dc.deleteSelected()) {
    e.preventDefault();
  }
}
```

In `init()` add:

```js
  for (const b of document.querySelectorAll('#rail [data-tool]')) {
    b.onclick = () => setTool(b.dataset.tool === tool && tool !== 'cursor' ? 'cursor' : b.dataset.tool);
  }
  $('#railClear').onclick = clearDrawings;
```

- [ ] **Step 4: Syntax-check and run the suite (the Node tests still load `drawings.js`)**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done` then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; suite passes, including `tests/test_charts_js.py`.

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/drawings.js homebase/static/charts/cell.js homebase/static/charts/app.js
git commit -m "feat(charts): drawing tools — trend line, horizontal line, rectangle, measure; select/move/reshape/delete; saved per symbol

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check after this task:** each tool by click-move-click and by drag; horizontal line with its axis tag; the tool returns to cursor and the new drawing is selected; hover shows the move cursor; move a trend line, drag each handle incl. a rectangle's side corners; Delete removes; Esc cancels mid-placement and deselects; remove-all arms then clears; drawings survive a reload, a 1m → 5m switch (same times) and show on a second NQ chart; measure label text and colours; chart does not pan while drawing or dragging, wheel zoom still works with a tool selected; dark theme; zero console errors.
