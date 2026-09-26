# Charts — Long/Short positions, Weak/Strong magnet, chart Settings, economic calendar, deep history — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the homebase chart page (chart service :8852) TradingView's Long/Short position tools, a Weak/Strong magnet, a per-chart Settings dialog (Symbol, Status line, Scales and lines, Canvas, Events, templates, Apply to all), ForexFactory's economic calendar on the charts, and scroll-back through the whole tick archive.

**Architecture:** Plain scripts, no bundler, as in the redesign. Four new pure modules, each tested in Node: `charts/position.js` (`HBPosition`: the box's geometry, clamps, labels and outcome), `charts/settings.js` (`HBSettings`: the settings model and its Lightweight Charts mappings), `charts/events.js` (`HBEvents`: which calendar events a chart shows, flag layout, tooltip and countdown texts) and `charts/scrollback.js` (`HBScrollBack`: the scroll-back request guard and the prepend). One new browser module: `charts/settings-dialog.js` (`HBSettingsDialog`). `drawings.js` gains the magnet and hands long/short drawings to `HBPosition`. `cell.js` applies settings in place and prepends older history. `app.js` wires the rail, the toolbar gear, the templates and the new socket message. The server gains long/short validation, `point_value` in the history message, `/api/templates`, a ForexFactory calendar (`calendar.py`, `/api/calendar`, a status field), deeper default history, the `older` socket message and a cache warm-up command.

**Tech Stack:** Python 3 / FastAPI / pytest; Lightweight Charts 5.2.1 (vendored `homebase/static/vendor/lightweight-charts-5.2.1.js`, `window.LightweightCharts`); Lucide 1.48.0 icons inlined; Node 26 (`node --test`).

**Spec:** `docs/superpowers/specs/2026-09-26-charts-tools-settings-design.md` (§1–§4; §5 "Deep history" and §6 "Economic calendar" were added on 2026-09-26)

## Global Constraints

- **Plain scripts:** each file is an IIFE exposing one `window.HB*` namespace. Pure halves must load in
  Node (`module.exports`) with no browser globals at load time.
- **Icons:** Lucide only (`lucide-static@1.48.0`, inlined SVG). Never TradingView's icons, logo or branding.
- **Styling:** design tokens as in the redesign spec (`--frame --panel --text --text-2 --border --grid
  --hover --pill --accent --accent-soft --up --down`), light theme default, dark supported. Font stack:
  `-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif`. Menus and dialogs
  have radius 8 and use the shadows from the spec. Every control gets a 2px `--accent` `:focus-visible`
  outline. Numbers use `tabular-nums`.
- **No native dialogs:** no `alert`, `confirm` or `prompt`; the desktop viewer blocks them. All text
  input is inline.
- **RR notation:** risk:reward is written **1:X** (e.g. `RR 1:2`, `RR 1:1.5`), never "2" or "2:1".
- **Dollars:** every P&L figure shows dollars as well as points.
- **Tests:**
  - Tests never open broker connections, never use tokens, and never write under `~/futures_ticks`.
  - Pure logic is tested in Node (`node --test tests/js/`).
  - Server changes are tested in pytest.
  - Both suites stay green.
- **Git and deploy:**
  - Work happens on branch `feat/charts-build2` in `.worktrees/build2`.
  - Never touch the live checkout; never run `deploy/install.sh`; never restart services.
  - Changed page assets bump their cache-bust query from `?v=2` to `?v=3` in `charts.html`.

## Execution notes (plan-level)

- **Where:** `/Users/ramoscapital/ramos-quant-homebase/.worktrees/build2`, branch `feat/charts-build2`. Never modify, check out, stash or commit anything in `/Users/ramoscapital/ramos-quant-homebase` outside `.worktrees/build2`: that checkout runs the LIVE desk.
- **Python** is `.venv/bin/python` (a symlink to the live venv; never `pip install` into it). Whole suite: `.venv/bin/python -m pytest -q`.
- **Node 26 needs file arguments:** `node --test tests/js/` fails with "Cannot find module" on Node 26. Run `node --test tests/js/*.test.mjs` for everything, or name one file. `tests/test_charts_js.py` runs every `tests/js/*.test.mjs` inside pytest, so new test files are picked up by the whole suite automatically.
- **Baseline when this plan was written:** 63 Node tests; 70 tests in `tests/test_charts_server.py tests/test_charts_hub.py tests/test_charts_js.py`.
- **Another agent is editing** `homebase/static/charts/catalog.js`, `tests/js/catalog.test.mjs`, `homebase/charts/tickfeed.py` and `tests/test_charts_tickfeed.py` (a status-bar and feed fix). No task here touches those four files. If a failure shows up only in them, report it and do not fix it.
- **No servers from Bash:** never run `python -m homebase.charts`, uvicorn, `deploy/install.sh` or `launchctl`. The controller checks the page in the browser on the replay entry `homebase-charts-dev-replay` (:8854, 2026-09-22 ×20, roots NQ ES YM BTC, this worktree). Task 9's `python -m homebase.charts.warm` is a one-shot command, not a server, and may be run.
- **Tests never touch the network:** the calendar's fetch function is injected. `create_app(…)` without `calendar_fetch` never fetches, so every existing test stays offline. Only `python -m homebase.charts` passes the real `http_get`.
- **Lightweight Charts 5.2.1 facts, checked in the vendored bundle:**
  - `CrosshairMode` is `Normal 0 · Magnet 1 · Hidden 2 · MagnetOHLC 3`.
  - `LineStyle` is `Solid 0 · Dotted 1 · Dashed 2`.
  - A primitive may return `priceAxisViews()`, whose views have `coordinate(), text(), textColor(), backColor(), visible?(), tickVisible?(), fixedCoordinate?()`. LWC caches its wrapper by the identity of the returned **array**, so always return the same array; the methods are called again at every render.
  - Series option `autoscaleInfoProvider`: returning `null` leaves the series out of autoscale, and `applyOptions({autoscaleInfoProvider: undefined})` restores the default.
  - `createTextWatermark(pane, opts)` returns an object with `applyOptions(opts)` and `detach()`.
  - `pane.setStretchFactor` exists.
- **Known quirks (from Build 1):**
  - LWC listens to mouse events only. A drawing gesture owns a press with `pointerdown.preventDefault()` plus `handleScroll/handleScale: false`, restored on release, on `pointercancel` and on window `blur`. `drawings.js` `own()` / `release()` / `abort()` already do this; new gestures reuse them.
  - `timeScale().logicalToCoordinate(i)` is right only for INTEGER `i`. Use `xOfLogical` / `timeToX`.
- **Script order in `charts.html` once every task is done:** lightweight-charts, icons, catalog, primitives, drawings, position, settings, events, scrollback, cell, settings-dialog, app. A task that changes an asset sets its `?v=` to `3` if it is not already; new files load with `?v=3`.
- **Syntax check** for page scripts: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`.
- **Commits:** a conventional message at the end of each task, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Plan-level rulings (the spec's open points, decided before execution)

- **R1** The server checks a long/short point's `t` with the existing integer epoch-ms rule, the same as trend and rect. The spec says "finite", but the page only ever writes bar starts. The price order is checked strictly. The ≥ 1-tick gaps are enforced by the page (`setHandle` clamps, dialog validation); the server has no tick size inside `check_drawings`.
- **R2** Handle 0 (left edge + entry) keeps its time at least 1 bar before `t1`. This mirrors handle 3's rule, so the box never turns inside out.
- **R3** Label signs follow the trade, for a short exactly as for a long: target `+…`, stop `−…`. The minus sign is U+2212, as in the spec's examples (`−25.00`, `−$500`). A P&L in points (no `point_value`) is the per-contract price move. Dollars show cents only when they are not whole (`$1,000`, `$15.63`).
- **R4** Settings labels and captions use the spec's words exactly, including "Colour bars based on previous close", "Text colour" and "Lines colour".
- **R5** Timezone: the time axis runs on the chosen zone's wall clock, with every bar re-timed, so day breaks follow the zone as on TradingView. The legend shows no times today, so "legend times" needs no change.
- **R6** Status line "Volume" hides both `Vol` and `Δ`. The legend's OHLC values use the candle colours (body up/down), including the previous-close rule when that is on.
- **R7** Precision drives the price scale, the last-price label and the legend values. Drawing and position labels keep the instrument's own precision.
- **R8** "Marks the layout Unsaved": Ok, when a chart's settings changed, sets `layout.dirty`. The toolbar then reads `<name> · Unsaved` until the next save or layout load. An unnamed layout reads `Unsaved`, as today.
- **R9** Cancel, ×, Esc or a backdrop click after `Apply to all` puts **every** chart back to its settings at open.
- **R10** While the footprint is readable, candle bodies **and** borders step aside. Borders are now on by default, and this keeps today's footprint look.
- **R11** The countdown shows only while the last-price label is on and the last bar is still open. It counts to the session close (17:00 ET; 18:00 for 24/7 roots) when that comes first. In replay it runs on the replay clock.
- **R12** Deep history uses the wire protocol's own keys. The spec's `"t": "older"` becomes the page's `{"op": "older", "id", "before"}` and the server's `{"type": "older", "id", "before", "bars", "studies", "repair", "sessions", "done"}` (or `error`). `before` is echoed so that a stale answer is dropped. `studies` and `repair` carry the study values, because the page computes none.
- **R13** An older chunk's studies run over the chunk from a fresh start. They then continue across the join through the page's first bars, for as long as a study still depends on the bars before: a window's length, 5n for an EMA, 10n for ADX, and the rest of a session cut by `HISTORY_MAX`. That second part is `repair`, which the page writes over its own values. The result matches a full reload of the longer range.
- **R14** Older chunks never go into the history memo, because a deep 1-minute scroll-back would fill it and evict the open charts' sessions. A memo hit is still used.
- **R15** Calendar: the Events tab's Holiday checkbox also covers Non-Economic events (both are grey folders). Country codes are upper-case everywhere (`All` becomes `ALL`). The page loads every stored event once, and again whenever the service's `calendar.fetched_at` changes. Each chart filters by its own settings.
- **R16** Calendar fetches follow the spec's rules:
  - at startup, then hourly after a good fetch;
  - 30 minutes after a failed one, which is the floor;
  - the floor is persisted in `calendar/state.json`, so restarts respect it;
  - an empty or unparseable feed counts as a failure and keeps the last good week.
- **R17** The status bar's "Next …" follows the **selected** chart's Events settings. It reads ET (like the bar's clock), looks at most 7 days ahead, and in a replay runs on the replay clock. Flag tooltips use the chart's own time zone.

## File map

The tasks run in order, 1 → 9. Each task's edits assume the code the earlier tasks left; its **Interfaces** block names what it takes from them.

| File | Responsibility | Tasks |
|---|---|---|
| `homebase/charts/server.py` | long/short validation, `/api/templates`, `/api/calendar` + status field + fetch loop, the `older` socket message | 1, 8, 9 |
| `homebase/charts/hub.py` | `point_value` in the history message; `sessions_back` defaults, `warm_bars`, `stream_of`, `older` | 1, 9 |
| `homebase/charts/history.py` | `bars(…, memo=)`, `cached()` | 9 |
| `homebase/charts/calendar.py` (new) | ForexFactory feed: fetch, parse, per-week storage, range query | 8 |
| `homebase/charts/warm.py` (new) | `python -m homebase.charts.warm` | 9 |
| `homebase/charts/__main__.py` | passes the real calendar fetch | 8 |
| `homebase/static/charts/position.js` (new, `HBPosition`) | the box: geometry, clamps, labels, outcome, `drawPosition` | 3, 4 |
| `homebase/static/charts/settings.js` (new, `HBSettings`) | the settings model and mappings; Events fields | 5, 8 |
| `homebase/static/charts/events.js` (new, `HBEvents`) | calendar filtering, flag layout, tooltip / countdown texts | 8 |
| `homebase/static/charts/scrollback.js` (new, `HBScrollBack`) | the scroll-back guard and prepend | 9 |
| `homebase/static/charts/settings-dialog.js` (new, `HBSettingsDialog`) | the Settings dialog | 6, 7, 8 |
| `homebase/static/charts/drawings.js` | magnet; long/short dispatch, placement, double-click | 2, 4 |
| `homebase/static/charts/primitives.js` | layers `EthBg`, `Countdown`, `EventFlags`, `Start` | 7, 8, 9 |
| `homebase/static/charts/cell.js` | magnet crosshair, `pv`, settings applied in place, legend flags, layers, event hover, scroll-back | 2, 4, 6, 7, 8, 9 |
| `homebase/static/charts/app.js` | rail magnet, position dialog, gear + dialog host, layouts carry settings, templates client, clocks, calendar cache + status bar, `older` routing | 2, 4, 6, 7, 8, 9 |
| `homebase/static/charts.html`, `charts/charts.css`, `charts/icons.js` | shell, styles, icons | 2, 4, 6, 7, 8, 9 |
| `tests/test_charts_server.py`, `tests/test_charts_hub.py` | server / hub tests | 1, 9 |
| `tests/test_charts_calendar.py` (new), `tests/test_charts_warm.py` (new), `tests/charts_util.py` | calendar, warm-up, a date helper | 8, 9 |
| `tests/js/drawings.test.mjs`; new `position`, `settings`, `events`, `scrollback` `.test.mjs` | Node tests | 2–5, 8, 9 |

Never touched here: `homebase/static/charts/catalog.js`, `tests/js/catalog.test.mjs`, `homebase/charts/tickfeed.py`, `tests/test_charts_tickfeed.py` (another agent's work in progress).

---

### Task 1: Server — long/short drawings, `point_value` in the history message, chart-settings templates

**Files:**
- Modify: `homebase/charts/server.py`
- Modify: `homebase/charts/hub.py` (`Stream.payload`)
- Test: `tests/test_charts_server.py`, `tests/test_charts_hub.py`

**Interfaces:**
- Consumes (existing): `check_drawings`, `DRAWING_POINTS`, `_finite`, `origin_ok` in `server.py`; `read_json`, `write_json`, `browser_write_ok` inside `create_app`; `Stream.payload`; `homebase.contracts.point_value(root) -> float | None`.
- Produces:
  - `DRAWING_POINTS` gains `"long": 3, "short": 3`. `POSITION_QTY_MAX = 10_000`.
  - `check_drawings` accepts `{id, type: "long"|"short", points: [entry, target, stop], qty?, color?}`, where each point is `{t: int epoch ms, p: finite}`, `points[1].t == points[2].t`, long `stop < entry < target` and short `target < entry < stop`. `qty` is an int 1–10000 and is kept for positions only. Error messages contain `stop < entry < target` / `target < entry < stop`.
  - The history message (`Stream.payload`) gains `"point_value": float | null`.
  - `GET /api/templates` returns `{name: settings}`, or `{}` when there are none.
  - `PUT /api/templates/{name}` takes a JSON object ≤ 16 KB and returns `{"ok": true}`. A bad name, size or body gives 400 with a `detail`; a foreign `Origin` gives 403.
  - `DELETE /api/templates/{name}` returns `{"ok": true}`; a foreign `Origin` gives 403.
  - Module-level `MAX_TEMPLATE_BYTES = 16 * 1024`, `MAX_TEMPLATE_NAME = 40`, and `check_template_name(name) -> str`, which raises `ValueError` for a name that is not 1–40 characters or that contains `/`, `\`, `..` or a control character.
  - Templates are stored in `<state>/templates.json` (i.e. `homebase/.state/charts/templates.json`) through the atomic `write_json`.
- Task 7 calls the templates routes. Task 4 reads `point_value` (as `Cell.pv`) and saves long/short drawings.

- [ ] **Step 1: Write the failing server tests.** In `tests/test_charts_server.py`, change the import line to

```python
from homebase.charts.server import (MAX_DRAWINGS, MAX_TEMPLATE_BYTES, QUIET, Conn, check_drawings,
                                    check_template_name, create_app)
```

In `test_replay_serves_history_then_live_updates`, after the line `assert hist["profile"]["poc"] > 0`, add:

```python
            assert hist["point_value"] == 20.0 and hist["tick_size"] == 0.25
```

Append to the end of the file:

```python
# ---- long / short positions ----
T0_MS, T1_MS = 1790000000000, 1790001200000


def pos(kind, entry, target, stop, t_target=T1_MS, t_stop=T1_MS, **extra):
    return {"id": f"p-{kind}", "type": kind, **extra,
            "points": [{"t": T0_MS, "p": entry}, {"t": t_target, "p": target}, {"t": t_stop, "p": stop}]}


LONG = pos("long", 30900.0, 30950.0, 30875.0, qty=2, color="#2962FF")
SHORT = pos("short", 30900.0, 30850.0, 30925.0)


def test_positions_are_saved_with_their_qty(tmp_path):
    with TestClient(replay_app(tmp_path)) as client:
        r = client.put("/api/drawings/NQ", json=[LONG, SHORT, TREND])
        assert r.status_code == 200 and r.json() == {"ok": True, "count": 3}
        assert client.get("/api/drawings/NQ").json() == [LONG, SHORT, TREND]


def test_qty_is_kept_for_positions_only():
    assert check_drawings([{**TREND, "qty": 3}]) == [TREND]
    assert check_drawings([pos("long", 1.0, 2.0, 0.5, qty=1)])[0]["qty"] == 1
    assert check_drawings([pos("short", 1.0, 0.5, 2.0, qty=10_000)])[0]["qty"] == 10_000
    assert "qty" not in check_drawings([pos("long", 1.0, 2.0, 0.5)])[0]


BAD_POSITIONS = [
    ("long with two points", [{**LONG, "points": LONG["points"][:2]}]),
    ("short with four points", [{**SHORT, "points": SHORT["points"] + SHORT["points"][:1]}]),
    ("target and stop on different right edges", [pos("long", 100, 110, 95, t_stop=T1_MS + 60_000)]),
    ("long stop above the entry", [pos("long", 100, 110, 101)]),
    ("long target below the entry", [pos("long", 100, 99, 95)]),
    ("long entry on the stop", [pos("long", 100, 110, 100)]),
    ("short target above the entry", [pos("short", 100, 101, 105)]),
    ("short stop below the entry", [pos("short", 100, 90, 99)]),
    ("short entry on the target", [pos("short", 100, 100, 105)]),
    ("position t missing", [{**LONG, "points": [{"p": 30900.0}, *LONG["points"][1:]]}]),
    ("position t a float", [{**LONG, "points": [{"t": 1.5, "p": 30900.0}, *LONG["points"][1:]]}]),
    ("position p not finite", [pos("long", float("nan"), 110, 95)]),
    ("qty zero", [{**LONG, "qty": 0}]),
    ("qty too big", [{**LONG, "qty": 10_001}]),
    ("qty a float", [{**LONG, "qty": 1.5}]),
    ("qty a bool", [{**LONG, "qty": True}]),
    ("qty a string", [{**LONG, "qty": "2"}]),
]


@pytest.mark.parametrize("why,body", BAD_POSITIONS, ids=[b[0] for b in BAD_POSITIONS])
def test_check_drawings_refuses_malformed_positions(why, body):
    with pytest.raises(ValueError):
        check_drawings(body)


def test_a_bad_position_is_a_400_that_names_the_rule(tmp_path):
    with TestClient(replay_app(tmp_path)) as client:
        r = client.put("/api/drawings/NQ", json=[pos("long", 100, 110, 101)])
        assert r.status_code == 400 and "stop < entry < target" in r.json()["detail"]
        r = client.put("/api/drawings/NQ", json=[pos("short", 100, 101, 105)])
        assert r.status_code == 400 and "target < entry < stop" in r.json()["detail"]
        assert client.get("/api/drawings/NQ").json() == []


# ---- chart-settings templates ----
TPL = {"prevClose": True, "bodyUp": "#26A69A", "marginTop": 20}


def test_templates_roundtrip(tmp_path):
    other = "My · layout v2"
    with TestClient(replay_app(tmp_path)) as client:
        assert client.get("/api/templates").json() == {}
        assert client.put("/api/templates/Dark candles", json=TPL).json() == {"ok": True}
        assert client.put("/api/templates/" + quote(other, safe=""), json={}).status_code == 200
        assert client.get("/api/templates").json() == {"Dark candles": TPL, other: {}}
        stored = json.loads((tmp_path / "state" / "templates.json").read_text())
        assert stored == {"Dark candles": TPL, other: {}}
        assert client.put("/api/templates/Dark candles", json={"wick": False}).status_code == 200
        assert client.delete("/api/templates/" + quote(other, safe="")).json() == {"ok": True}
        assert client.get("/api/templates").json() == {"Dark candles": {"wick": False}}
        assert client.delete("/api/templates/gone").status_code == 200       # deleting nothing is fine


def test_a_template_is_a_json_object_of_at_most_16_kb(tmp_path):
    def body(size):                     # a JSON object exactly `size` bytes long
        return json.dumps({"x": "a" * (size - len('{"x": ""}'))})

    with TestClient(replay_app(tmp_path)) as client:
        def put(text):
            return client.put("/api/templates/t", content=text, headers={"content-type": "application/json"})

        assert len(body(MAX_TEMPLATE_BYTES)) == MAX_TEMPLATE_BYTES == 16 * 1024
        assert put(body(MAX_TEMPLATE_BYTES)).status_code == 200
        r = put(body(MAX_TEMPLATE_BYTES + 1))
        assert r.status_code == 400 and "16 KB" in r.json()["detail"]
        for bad in ("[1, 2]", '"dark"', "null", "not json", '{"marginTop": NaN}', '{"a": Infinity}'):
            assert put(bad).status_code == 400, bad
        assert client.get("/api/templates").json() == {"t": json.loads(body(MAX_TEMPLATE_BYTES))}


@pytest.mark.parametrize("name", ["", "x" * 41, "a/b", "a\\b", "..", "a..b", "tab\there", "nul\x00", "del\x7f"])
def test_check_template_name_refuses(name):
    with pytest.raises(ValueError):
        check_template_name(name)


def test_template_names_on_the_wire(tmp_path):
    assert check_template_name("x" * 40) == "x" * 40
    assert check_template_name("Dark · v1.2") == "Dark · v1.2"
    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/templates/" + "x" * 40, json={}).status_code == 200
        for bad in ("x" * 41, "a/b", "a\\b", "tab\tname", "a..b"):
            r = client.put("/api/templates/" + quote(bad, safe=""), json={})
            assert r.status_code == 400, bad
        assert list(client.get("/api/templates").json()) == ["x" * 40]


def test_template_writes_from_another_site_are_refused(tmp_path):
    evil = {"origin": "https://evil.example"}
    with TestClient(replay_app(tmp_path)) as client:
        assert client.put("/api/templates/t", json=TPL, headers=evil).status_code == 403
        assert client.get("/api/templates").json() == {}
        assert client.put("/api/templates/t", json=TPL, headers={"origin": "http://localhost:8852"}).status_code == 200
        assert client.delete("/api/templates/t", headers=evil).status_code == 403
        assert client.get("/api/templates").json() == {"t": TPL}
        assert client.delete("/api/templates/t", headers={"origin": "http://127.0.0.1:8852"}).status_code == 200
        assert client.get("/api/templates").json() == {}
```

- [ ] **Step 2: Write the failing hub test.** Append to `tests/test_charts_hub.py`:

```python
def test_the_history_message_carries_the_point_value(tmp_path):
    """The page turns a position's price move into dollars with it (null: the page shows points only)."""
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:60]))
    assert open_stream(hub).payload()["point_value"] == 20.0
    unknown = Stream("ZZ", M1, 0.25, BarBuilder(M1, 0.25, "ZZ"))
    assert unknown.payload()["point_value"] is None
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_server.py tests/test_charts_hub.py -q`
Expected: collection error (`MAX_TEMPLATE_BYTES` / `check_template_name` cannot be imported). With the import line temporarily reverted, the new tests FAIL.

- [ ] **Step 4: Implement `hub.py`.** Change the import to `from ..contracts import point_value, tick_size` and the `return` of `Stream.payload` to:

```python
        return {"root": self.root, "spec": self.spec.key, "tick_size": ts, "point_value": point_value(self.root),
                "bars": bars, "live": live is not None, "studies": studies,
                "profile": self.profile.value(live) if self.profile is not None else None,
                "sessions": self.sessions}
```

- [ ] **Step 5: Implement `server.py`.**

Change the module docstring's first line to `"""The chart service: FastAPI on :8852 — the page, the websocket, layouts, drawings, templates,`, keeping the rest of the docstring.

Replace the constants block `MAX_DRAWINGS = 500 … _HEX_COLOR = …` with:

```python
MAX_DRAWINGS = 500            # per symbol
DRAWING_POINTS = {"trend": 2, "rect": 2, "hline": 1, "long": 3, "short": 3}
POSITION_QTY_MAX = 10_000     # a long/short box's quantity
MAX_TEMPLATE_BYTES = 16 * 1024   # one chart-settings template, as JSON
MAX_TEMPLATE_NAME = 40
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
```

Replace `check_drawings` with the version below. It adds `_check_position`, `check_template_name` and `_no_constant`:

```python
def _check_position(kind: str, pts: list) -> None:
    """A long/short box: [entry, target, stop], target and stop on the box's right edge (one t)."""
    entry, target, stop = (p["p"] for p in pts)
    if pts[1]["t"] != pts[2]["t"]:
        raise ValueError(f"a {kind}'s target and stop share the box's right edge (the same t)")
    if kind == "long" and not stop < entry < target:
        raise ValueError("a long has stop < entry < target")
    if kind == "short" and not target < entry < stop:
        raise ValueError("a short has target < entry < stop")


def check_drawings(body) -> list:
    """The page's drawings for one symbol, validated and stripped to what
    the page draws: [{id, type, points: [{t?, p}], color?, qty?}]. A long /
    short position is [entry, target, stop] with target and stop on the
    box's right edge (same t), stop < entry < target (long) or target <
    entry < stop (short), and an optional qty 1-10000 (kept for positions
    only). ValueError (with a message for the page) on anything else."""
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
            raise ValueError("type: trend, hline, rect, long or short")
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
        if kind in ("long", "short"):
            _check_position(kind, clean)
            if "qty" in d:
                q = d["qty"]
                if not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= POSITION_QTY_MAX:
                    raise ValueError(f"qty: a whole number from 1 to {POSITION_QTY_MAX}")
                item["qty"] = q
        if "color" in d:
            if not isinstance(d["color"], str) or not _HEX_COLOR.fullmatch(d["color"]):
                raise ValueError("color: #RRGGBB")
            item["color"] = d["color"]
        out.append(item)
    return out


def check_template_name(name) -> str:
    """A chart-settings template's name: 1-40 characters, no / \\ .. and no
    control characters (it rides in the URL path). ValueError otherwise."""
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_TEMPLATE_NAME:
        raise ValueError(f"a template name has 1-{MAX_TEMPLATE_NAME} characters")
    if "/" in name or "\\" in name or ".." in name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("a template name has no / \\ .. or control characters")
    return name


def _no_constant(c: str):
    """json.loads hook: NaN / Infinity are not JSON (the page's r.json() could not read them back)."""
    raise ValueError(f"{c} is not JSON")
```

Inside `create_app`, after `drawings_path = sd / "drawings.json"`, add `templates_path = sd / "templates.json"`. After the `put_drawings` route, add:

```python
    @app.get("/api/templates")
    async def get_templates():
        return read_json(templates_path)

    @app.put("/api/templates/{name:path}")
    async def put_template(name: str, request: Request):
        browser_write_ok(request)
        try:
            check_template_name(name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        raw = await request.body()
        if len(raw) > MAX_TEMPLATE_BYTES:
            raise HTTPException(400, f"a template is at most {MAX_TEMPLATE_BYTES // 1024} KB of JSON")
        try:
            body = json.loads(raw, parse_constant=_no_constant)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "a template is a JSON object of chart settings")
        all_ = read_json(templates_path)
        all_[name] = body
        write_json(templates_path, all_)
        return {"ok": True}

    @app.delete("/api/templates/{name:path}")
    async def delete_template(name: str, request: Request):
        browser_write_ok(request)
        all_ = read_json(templates_path)
        all_.pop(name, None)
        write_json(templates_path, all_)
        return {"ok": True}
```

(`{name:path}`: the page's `encodeURIComponent` turns `/` into `%2F`, and Starlette decodes it before routing. A single-segment `{name}` would answer 404 where a 400 with a reason is wanted.)

- [ ] **Step 6: Run the new tests, then the whole suite**

Run: `.venv/bin/python -m pytest tests/test_charts_server.py tests/test_charts_hub.py -q`, then `.venv/bin/python -m pytest -q`
Expected: all pass, including every existing drawings/layouts test unchanged.

- [ ] **Step 7: Commit**

```bash
git add homebase/charts/server.py homebase/charts/hub.py tests/test_charts_server.py tests/test_charts_hub.py
git commit -m "feat(charts): long/short drawings validated and saved, point_value in the history message, chart-settings templates API

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Magnet (Weak / Strong) — pure snap, controller, rail button with flyout, crosshair

**Files:**
- Modify: `homebase/static/charts/drawings.js` (pure snap helpers; `Controller.at` and its call sites)
- Modify: `tests/js/drawings.test.mjs` (the pointer rig gains options; magnet tests)
- Modify: `homebase/static/charts/cell.js` (`setMagnetCrosshair`)
- Modify: `homebase/static/charts/app.js` (magnet state, rail button, flyout, crosshair sync, `openMenu` options)
- Modify: `homebase/static/charts.html`, `homebase/static/charts/charts.css`, `homebase/static/charts/icons.js`

**Interfaces:**
- Consumes: the `Controller` in `drawings.js` (`at`, `onDown`, `onMove`, `onUp`, `own`/`release`); `Cell.makeChart`; the page's `openMenu`, `placeMenu`, `closeMenu`, `toggleMenu`, `menuItem`, `icon`, `setTool`, `select`, `hostFor`, `init`.
- Produces:
  - `HBDrawings.MAGNET_PX = 12` and `HBDrawings.MAGNET_OFF = {on: false, mode: 'weak'}`.
  - `HBDrawings.parseMagnet(text) -> {on, mode}` reads localStorage `hb_charts_magnet`; anything unreadable gives off/weak.
  - `HBDrawings.magnetMode(state, metaKey) -> 'weak'|'strong'|null`: ⌘ inverts the state for one event.
  - `HBDrawings.snapPrice(bar, y, p, mode, yOf) -> price`.
  - `Controller.barAt(t) -> bar|null`.
  - `Controller.at(pt, e = null) -> {t, p, L}|null`: with the pointer event `e`, the magnet applies; without it, never.
  - The host gains `magnet() -> {on, mode}`.
  - `Cell.setMagnetCrosshair(on)` and the field `Cell.magnetXhair`; `makeChart` uses `this.magnetXhair ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal`.
  - Page: `magnet`, `setMagnet(next)`, `renderMagnet()`, `syncCrosshair()`, `magnetMenu()`.
  - `openMenu(anchor, cls, {right} = {})`: `right` opens the menu to the right of a rail button. Task 6 adds a `root` option.
  - Test rig: `pointerRig(saved, {tool, magnet, rigBars})` returning `{ctl, store, gesture(path, metaKey), tool(), puts(), done()}`, plus `ohlc` (OHLC bars) and `withWindow(t)`. Task 4 extends the rig.

- [ ] **Step 1: Write the failing tests.** In `tests/js/drawings.test.mjs`, replace the whole `pointerRig` function (and its comment) with:

```js
/* The pointer controller on a chart that needs no browser: the price pane
   is 400 x 1000 px at the page origin, bar i at x = 100 + 10 i, price p at
   y = 1000 - p (so one pixel is four 0.25 ticks). opts: the rail's tool (it
   returns to the cursor after a placement, as on the page), the magnet, and
   the chart's bars (OHLC ones for the magnet). */
function pointerRig(saved, { tool = 'cursor', magnet = { on: false, mode: 'weak' }, rigBars = bars } = {}) {
  globalThis.window = { addEventListener() {}, removeEventListener() {} };
  const chart = { applyOptions() {}, priceScale: () => ({ width: () => 60 }), panes: () => [{ getHeight: () => 1000 }],
    timeScale: () => ({ logicalToCoordinate: (i) => 100 + i * 10, coordinateToLogical: (x) => (x - 100) / 10 }) };
  const cell = { shown: { root: 'NQ' }, el: { dataset: {} }, P: { accent: '#2962FF' }, chart, bars: rigBars, tick: 0.25,
    isTime: () => true, barMs: () => MIN,
    box: { clientWidth: 460, getBoundingClientRect: () => ({ left: 0, top: 0 }), addEventListener() {}, removeEventListener() {} },
    candles: { attachPrimitive() {}, priceToCoordinate: (p) => 1000 - p, coordinateToPrice: (y) => 1000 - y } };
  const f = fakeFetch((url, method) => (method === 'GET' ? { status: 200, body: saved } : null));
  const store = new D.Store({ fetchFn: f, delay: 0 });
  let now = tool;
  const ctl = new D.Controller(cell, { tool: () => now, toolDone() { now = 'cursor'; }, drawings: store,
    magnet: () => magnet });
  const ev = (x, y, buttons = 1, metaKey = false) => ({ button: 0, buttons, ctrlKey: false, metaKey, clientX: x, clientY: y,
    preventDefault() {}, stopPropagation() {} });
  const gesture = async (path, metaKey = false) => {   // press at path[0], move through the rest, release at the last point
    ctl.onDown(ev(...path[0], 1, metaKey));
    for (const p of path.slice(1)) ctl.onMove(ev(...p, 1, metaKey));
    ctl.onUp(ev(...path.at(-1), 0, metaKey));
    await new Promise((r) => setTimeout(r, 5));   // the store's (0 ms) save debounce
    await flush();
  };
  return { ctl, store, gesture, tool: () => now, puts: () => f.calls.filter((c) => c.method === 'PUT'),
    done() { ctl.destroy(); } };
}
```

The existing test `a click on a drawing selects it…` keeps calling `pointerRig([trend])` unchanged. Append at the end of the file:

```js
/* ---- the magnet ---- */
test('the magnet state reads back from storage; anything else is off / weak', () => {
  assert.deepEqual(D.parseMagnet('{"on":true,"mode":"strong"}'), { on: true, mode: 'strong' });
  assert.deepEqual(D.parseMagnet('{"on":1,"mode":"x"}'), { on: false, mode: 'weak' });
  assert.deepEqual(D.parseMagnet(null), { on: false, mode: 'weak' });
  assert.deepEqual(D.parseMagnet('not json'), { on: false, mode: 'weak' });
  assert.deepEqual(D.MAGNET_OFF, { on: false, mode: 'weak' });
  assert.equal(D.MAGNET_PX, 12);
});

test('⌘ inverts the magnet for one event', () => {
  assert.equal(D.magnetMode({ on: true, mode: 'weak' }, false), 'weak');
  assert.equal(D.magnetMode({ on: true, mode: 'strong' }, false), 'strong');
  assert.equal(D.magnetMode({ on: true, mode: 'strong' }, true), null);
  assert.equal(D.magnetMode({ on: false, mode: 'strong' }, true), 'strong');
  assert.equal(D.magnetMode({ on: false, mode: 'weak' }, false), null);
  assert.equal(D.magnetMode(null, false), null);
});

const BAR = { ms: T0, o: 900, h: 910, l: 880, c: 905 };
const yOf = (p) => 1000 - p;     // one px per 1.00

test('weak magnet: the nearest O/H/L/C within 12 px, else the pointer\'s price', () => {
  assert.equal(D.snapPrice(BAR, yOf(912), 912, 'weak', yOf), 910);          // 2 px from H
  assert.equal(D.snapPrice(BAR, yOf(922), 922, 'weak', yOf), 910);          // exactly 12 px
  assert.equal(D.snapPrice(BAR, yOf(922.25), 922.25, 'weak', yOf), 922.25); // 12.25 px: too far
  assert.equal(D.snapPrice(BAR, yOf(903), 903, 'weak', yOf), 905);          // C (2 px) beats O (3 px)
});

test('strong magnet: always the nearest O/H/L/C', () => {
  assert.equal(D.snapPrice(BAR, yOf(960), 960, 'strong', yOf), 910);
  assert.equal(D.snapPrice(BAR, yOf(850), 850, 'strong', yOf), 880);
});

test('no magnet, no bar (beyond the data) or no placeable candidate: the pointer\'s price', () => {
  assert.equal(D.snapPrice(BAR, 88, 912, null, yOf), 912);
  assert.equal(D.snapPrice(null, 88, 912, 'strong', yOf), 912);
  assert.equal(D.snapPrice(BAR, 88, 912, 'strong', () => null), 912);
});

/* OHLC bars for the magnet: bar i opens 900, closes 905, high 910 + i, low 880 - i. */
const ohlc = bars.map((b, i) => ({ ...b, o: 900, h: 910 + i, l: 880 - i, c: 905 }));
function withWindow(t) {   // the rig installs a fake window: put the real one (none, in Node) back after the test
  const had = globalThis.window;
  t.after(() => { if (had === undefined) delete globalThis.window; else globalThis.window = had; });
}

test('placing snaps each point to its bar\'s O/H/L/C: weak within 12 px, strong always, ⌘ inverts', async (t) => {
  withWindow(t);
  const place = async (magnet, meta = false) => {
    const R = pointerRig([], { tool: 'trend', magnet, rigBars: ohlc });
    await R.store.ensure('NQ');
    // bar 2 at 915 (its high, 912, is 3 px away); bar 4 at 930 (its high, 914, is 16 px away)
    await R.gesture([[120, 85], [140, 70]], meta);
    const [d] = R.store.list('NQ');
    R.done();
    return d.points.map((q) => q.p);
  };
  assert.deepEqual(await place({ on: true, mode: 'weak' }), [912, 930]);
  assert.deepEqual(await place({ on: true, mode: 'strong' }), [912, 914]);
  assert.deepEqual(await place({ on: false, mode: 'strong' }), [915, 930]);
  assert.deepEqual(await place({ on: false, mode: 'strong' }, true), [912, 914]);   // ⌘: an off magnet works, in its mode
  assert.deepEqual(await place({ on: true, mode: 'strong' }, true), [915, 930]);    // ⌘: an on magnet is off
});

test('dragging a handle takes the magnet; moving a whole drawing never does', async (t) => {
  withWindow(t);
  const line = { id: 'm', type: 'trend', points: [{ t: bars[1].ms, p: 900 }, { t: bars[3].ms, p: 860 }] };   // (110,100)-(130,140)
  const R = pointerRig([line], { magnet: { on: true, mode: 'strong' }, rigBars: ohlc });
  await R.store.ensure('NQ');
  await R.gesture([[120, 120], [120, 116], [120, 114]]);               // the body, 6 px up: +6.00, no snap
  assert.deepEqual(R.store.list('NQ')[0].points, [{ t: bars[1].ms, p: 906 }, { t: bars[3].ms, p: 866 }]);
  await R.gesture([[110, 94], [120, 80], [120, 85]]);                 // handle 0 onto bar 2 near 915: its high, 912
  assert.deepEqual(R.store.list('NQ')[0].points, [{ t: bars[2].ms, p: 912 }, { t: bars[3].ms, p: 866 }]);
  R.done();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/drawings.test.mjs`
Expected: FAIL. `D.parseMagnet is not a function`, and the placement tests get unsnapped prices.

- [ ] **Step 3: Implement the pure half in `drawings.js`.** Insert just before the `/* Drawings per symbol, …` comment above `class Store`:

```js
/* ---- the magnet (the rail's Weak / Strong): drawing points snap to a candle's prices ---- */
const MAGNET_PX = 12;   // weak: an O/H/L/C this close (px) to the pointer takes the point
const MAGNET_OFF = Object.freeze({ on: false, mode: 'weak' });

/* The magnet as saved in localStorage (hb_charts_magnet): {on, mode}; anything unreadable is off / weak. */
function parseMagnet(text) {
  let v = null;
  try { v = JSON.parse(text); } catch (_) { /* unreadable: off */ }
  if (!v || typeof v !== 'object') return { ...MAGNET_OFF };
  return { on: v.on === true, mode: v.mode === 'strong' ? 'strong' : 'weak' };
}

/* The magnet for one pointer event: 'weak' | 'strong' | null (off). ⌘ held inverts it (TradingView's Ctrl/Cmd). */
function magnetMode(state, meta) {
  const s = state || MAGNET_OFF, on = meta ? !s.on : s.on;
  return on ? (s.mode === 'strong' ? 'strong' : 'weak') : null;
}

/* A drawing point's price under the magnet. The candidates are the O, H, L, C of `bar`, the bar the point's
   time snaps to (null beyond the loaded bars: no snap). Strong: the candidate nearest the pointer's y. Weak:
   that candidate only within MAGNET_PX, else the pointer's own tick-rounded price p. yOf(price) = its y. */
function snapPrice(bar, y, p, mode, yOf) {
  if (!mode || !bar) return p;
  let best = null, bestD = Infinity;
  for (const q of [bar.o, bar.h, bar.l, bar.c]) {
    const qy = q == null ? null : yOf(q);
    if (qy == null) continue;
    const dist = Math.abs(qy - y);
    if (dist < bestD) { best = q; bestD = dist; }
  }
  if (best == null) return p;
  return mode === 'strong' || bestD <= MAGNET_PX ? best : p;
}
```

Add `MAGNET_PX, MAGNET_OFF, parseMagnet, magnetMode, snapPrice` to the `api` object.

- [ ] **Step 4: Controller integration.** In `class Controller`, replace `at(pt)` (and its comment) with:

```js
  /* The bar a snapped time lands on (null beyond the loaded bars). */
  barAt(t) { const b = this.cell.bars, i = barIndexAt(b, t); return i >= 0 && b[i].ms === t ? b[i] : null; }

  /* The bar-snapped time and tick-rounded price under a pane point. Given the pointer event `e` (placing a
     point, dragging a handle) the magnet may move the price to the bar's O/H/L/C, and ⌘ in `e` inverts it;
     without `e` (moving a whole drawing) it never does. */
  at(pt, e = null) {
    const c = this.cell, L = c.chart.timeScale().coordinateToLogical(pt.x), raw = c.candles.coordinateToPrice(pt.y);
    if (L == null || raw == null || !c.bars.length) return null;
    const t = snapTime(L, c.bars, c.isTime(), c.barMs());
    let p = roundToTick(raw, c.tick);
    if (e) p = snapPrice(this.barAt(t), pt.y, p, magnetMode(this.host.magnet(), e.metaKey), (q) => c.candles.priceToCoordinate(q));
    return { t, p, L };
  }
```

Then change exactly these call sites:
- In `onDown`, tool branch: `const at = this.at(pt);` becomes `const at = this.at(pt, e);`.
- In `onDown`, cursor branch: `from: this.at(pt)` stays as it is. A body move measures its offset without the magnet.
- In `onMove`, placing branch: `const at = this.at(this.local(e));` becomes `const at = this.at(this.local(e), e);`.
- In `onMove`, drag branch: `const at = this.at(pt);` becomes `const at = this.at(pt, part === 'handle' ? e : null);`.
- In `onUp`, placing branch: `const at = this.at(pt);` becomes `const at = this.at(pt, e);`.

Update the file header's second paragraph: "…the pointer controller that places, selects, moves and deletes them (with the rail's magnet)…".

- [ ] **Step 5: Run the Node tests**

Run: `node --test tests/js/drawings.test.mjs`
Expected: PASS, including every earlier drawings test.

- [ ] **Step 6: `cell.js`, the magnet crosshair.** Add `this.magnetXhair = false;   // the rail's magnet is on with a tool picked (MagnetOHLC crosshair)` to the constructor's fields, next to `this.dc = null`. In `makeChart`, change the crosshair's `mode: LW.CrosshairMode.Normal,` to `mode: this.magnetXhair ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal,`. Add the method (after `setSelected`):

```js
  /* The rail's magnet with a drawing tool picked, on the selected chart: the crosshair snaps to O/H/L/C too
     (when this Lightweight Charts has MagnetOHLC); otherwise the normal crosshair. Kept across rebuilds. */
  setMagnetCrosshair(on) {
    const m = !!on && LW.CrosshairMode.MagnetOHLC !== undefined;
    if (this.magnetXhair === m) return;
    this.magnetXhair = m;
    if (this.chart) this.chart.applyOptions({ crosshair: { mode: m ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal } });
  }
```

In the header comment's host list, add `magnet()` next to `tool(), toolDone(), drawings`.

- [ ] **Step 7: `app.js`, state, rail button and flyout.**

Add to the state, after `const drawings = …`:

```js
let magnet = loadMagnet();   // the rail's magnet {on, mode}, per viewer (localStorage hb_charts_magnet)
let menuRight = false;       // the open menu is a rail flyout: it opens to the right of its button
```

Replace `openMenu` and `placeMenu` with:

```js
/* One popup menu at a time, under its toolbar button (right: to the right of a rail button). */
function openMenu(anchor, cls, { right = false } = {}) {
  closeMenu();
  const m = mk('div', 'menu' + (cls ? ' ' + cls : ''));
  m.setAttribute('role', 'menu');
  $('#menuRoot').appendChild(m);
  menuEl = m; menuAnchor = anchor; menuRight = right;
  anchor.classList.add('open');
  anchor.setAttribute('aria-expanded', 'true');
  return m;
}
function placeMenu() {
  if (!menuEl) return;
  const w = menuEl.offsetWidth, h = menuEl.offsetHeight;
  if (menuRight) {
    const r = (menuAnchor.closest('.rail-split') || menuAnchor).getBoundingClientRect();
    menuEl.style.left = (r.right + 8) + 'px';
    menuEl.style.top = Math.max(4, Math.min(r.top, window.innerHeight - h - 4)) + 'px';
    return;
  }
  const r = menuAnchor.getBoundingClientRect();
  menuEl.style.left = Math.max(4, Math.min(r.left, window.innerWidth - w - 4)) + 'px';
  menuEl.style.top = (r.bottom + 4) + 'px';
}
```

In `hostFor(id)`, add `magnet: () => magnet,`. Add a `/* ---- magnet ---- */` section after the drawing-rail section:

```js
function loadMagnet() {
  try { return window.HBDrawings.parseMagnet(localStorage.getItem('hb_charts_magnet')); }
  catch (_) { return { ...window.HBDrawings.MAGNET_OFF }; }
}
function setMagnet(next) {
  magnet = { on: !!next.on, mode: next.mode === 'strong' ? 'strong' : 'weak' };
  try { localStorage.setItem('hb_charts_magnet', JSON.stringify(magnet)); } catch (_) { /* storage off */ }
  renderMagnet();
  syncCrosshair();
}
function renderMagnet() {
  const b = $('#railMagnet'), tip = magnet.on ? `Magnet (${magnet.mode})` : 'Magnet off';
  b.setAttribute('aria-pressed', String(magnet.on));
  b.title = tip;
  b.setAttribute('aria-label', tip);
}
/* The selected chart's crosshair snaps like the magnet while it is on and a drawing tool is picked. */
function syncCrosshair() {
  cells.forEach((c, k) => c.setMagnetCrosshair(magnet.on && tool !== 'cursor' && k === selected));
}
/* The corner triangle's flyout: Weak / Strong, a check on the current mode; picking one turns the magnet on. */
function magnetMenu() {
  const m = openMenu($('#railMagnetMore'), 'menu-magnet', { right: true });
  for (const [mode, text] of [['weak', 'Weak magnet'], ['strong', 'Strong magnet']]) {
    const b = menuItem(text, '', () => { closeMenu(); setMagnet({ on: true, mode }); }, false), ck = icon('check');
    ck.classList.add('menu-ck');
    if (magnet.mode !== mode) ck.style.visibility = 'hidden';
    b.setAttribute('role', 'menuitemradio');
    b.setAttribute('aria-checked', String(magnet.mode === mode));
    b.prepend(ck);
    m.appendChild(b);
  }
}
```

At the end of `setTool(t)` and at the end of `select(i)`, add `syncCrosshair();`. In `init()`, after `$('#railClear').onclick = clearDrawings;`, add:

```js
  $('#railMagnet').onclick = () => setMagnet({ ...magnet, on: !magnet.on });
  $('#railMagnetMore').onclick = () => toggleMenu($('#railMagnetMore'), magnetMenu);
  renderMagnet();
```

Update the file's header comment: "…the drawing rail (the tool, the magnet and the per-symbol drawings store)…".

- [ ] **Step 8: Shell, styles, icon.**

`icons.js`: add `magnet` to the header's Lucide list, and add the entry (Lucide 1.48.0 `magnet`):

```js
  magnet: svg('<path d="m12 15 4 4"/><path d="M2.352 10.648a1.205 1.205 0 0 0 0 1.704l2.296 2.296a1.205 1.205 0 0 0 1.704 0l6.029-6.029a1 1 0 1 1 3 3l-6.029 6.029a1.205 1.205 0 0 0 0 1.704l2.296 2.296a1.205 1.205 0 0 0 1.704 0l6.365-6.367A1 1 0 0 0 8.716 4.282z"/><path d="m5 8 4 4"/>'),
```

`charts.html`: in `#rail`, between `<span class="rail-sep"></span>` and the `#railClear` button, insert:

```html
    <div class="rail-split">
      <button class="rail-btn" type="button" id="railMagnet" title="Magnet off" aria-label="Magnet off" aria-pressed="false"><span class="icw" data-icon="magnet"></span></button>
      <button class="rail-corner" type="button" id="railMagnetMore" title="Magnet mode" aria-label="Magnet mode" aria-haspopup="menu" aria-expanded="false"></button>
    </div>
```

Set `?v=3` on `charts.css`, `icons.js`, `drawings.js`, `cell.js` and `app.js`.

`charts.css`: after the `.rail-sep` rule add:

```css
.rail-split { position: relative; }
/* the magnet's mode flyout: a 6px triangle in the button's bottom-right corner */
.rail-corner { position: absolute; right: 0; bottom: 0; width: 12px; height: 12px; border-radius: 0 0 4px 0; color: var(--text-2); }
.rail-corner::after { content: ""; position: absolute; right: 2px; bottom: 2px; border-style: solid; border-width: 0 0 6px 6px;
  border-color: transparent transparent currentColor transparent; }
.rail-corner:hover, .rail-corner.open { color: var(--text); background: var(--hover); }
.menu-ck { width: 16px; color: var(--accent); }
.menu-ck .ic { width: 16px; height: 16px; }
```

- [ ] **Step 9: Syntax-check and run the suites**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green.

- [ ] **Step 10: Commit**

```bash
git add homebase/static/charts/drawings.js tests/js/drawings.test.mjs homebase/static/charts/cell.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js
git commit -m "feat(charts): weak/strong magnet — drawing points and handles snap to O/H/L/C, ⌘ inverts, rail button with a mode flyout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check (replay :8854):**
- The magnet button sits between the rail separator and the trash, with the tooltip `Magnet off`.
- A click turns it on: the button looks pressed (accent on accent-soft) and the tooltip reads `Magnet (weak)`. A second click turns it off.
- The corner triangle opens a flyout to the right of the rail, with a check on the current mode. Picking `Strong magnet` turns the magnet on and the tooltip reads `Magnet (strong)`.
- The state survives a reload.
- Weak mode: a trend point clicked about 5 px from a candle's high lands exactly on the high; about 30 px away it stays at the pointer. Strong mode: every point lands on the nearest O/H/L/C. Check the horizontal line, rectangle and measure tools the same way.
- ⌘ held while clicking inverts the magnet for that click.
- Dragging a handle snaps. Dragging a line's body never snaps.
- With the magnet on and a tool picked, the selected chart's crosshair jumps to O/H/L/C, while the other charts' crosshairs stay normal. Back to the cursor, the crosshair is normal again.
- The chart never pans during a placement or drag.
- Dark theme works; zero console errors.

---
### Task 3: `HBPosition` — the Long/Short box, pure (geometry, clamps, labels, outcome)

**Files:**
- Create: `homebase/static/charts/position.js`
- Create: `tests/js/position.test.mjs`

**Interfaces:**
- Consumes: `HBDrawings.roundToTick`, `logicalOf`, `shiftTime`, `barIndexAt`, `timeToX` (tests only), `HANDLE_TOL` (6), `LINE_TOL` (5); `HBCatalog.fmtPrice`. In the page these come from `window.*`, because `position.js` loads after `drawings.js`. In Node they come from `require('./drawings.js')` / `require('./catalog.js')`.
- Produces `window.HBPosition` (and `module.exports`):
  - Constants: `WIDTH_BARS = 20`, `RISK_PANE = 0.08`, `MIN_RISK_TICKS = 4`, `QTY_MAX = 10000`, `MINUS = '−'`.
  - A position: `{id, type: 'long'|'short', points: [entry {t: t0, p}, target {t: t1, p}, stop {t: t1, p}], qty, color?}`.
  - `isPosition(d) -> bool`.
  - `risk(span, tick) -> price`. `span` is the price distance of 8% of the pane height; the result is on the tick grid and at least 4 ticks.
  - `create(type, t0, t1, entry, R, tick) -> {type, points, qty: 1}`, which reads RR 1:2.
  - `handles(d, geo) -> [[x, y] × 4] | null`: 0 (x0, entry), 1 (x0, target), 2 (x0, stop), 3 (x1, entry). `geo = {x(t), y(p)}`.
  - `hitTest(d, pt, geo) -> {part: 'handle', index} | {part: 'body'} | null`.
  - `setHandle(d, k, t, p, ctx) -> d'` (clamped), with `ctx = {bars, isTime, barMs, tick}`.
  - `fmtUsd(v) -> '$1,000' | '$15.63'`; `fmtPnl(move, pv, qty, tick) -> '+$1,000' | '−$500' | '$0' | '+50.00'`; `rr(d) -> '1:2'`.
  - `labels(d, pv, tick) -> {target, stop, center}`.
  - `outcome(d, bars, pv, tick) -> {kind: 'none'|'ambiguous'|'closed'|'open'|'expired', text, path: {a: {t, p}, b: {t, p}} | null}`, where `bars` are `[{ms, o, h, l, c}]`.
  - `validate(type, entry, target, stop, qty, tick) -> '' | message`.
- Task 4 adds `drawPosition(ctx, d, geo, P, pctx)` to this file, and `drawings.js` starts using `handles`, `hitTest` and `setHandle` for long/short drawings.

- [ ] **Step 1: Write the failing tests** — `tests/js/position.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const P = require('../../homebase/static/charts/position.js');
const D = require('../../homebase/static/charts/drawings.js');

const MIN = 60000;
const T0 = 1_790_000_000_000;
const bars = [0, 1, 2, 3, 4].map((i) => ({ ms: T0 + i * MIN }));      // five 1m bars; bar i at x = 100 + 10 i
const CTX = { bars, isTime: true, barMs: MIN, tick: 0.25, coord: (i) => 100 + i * 10 };
const geo = { x: (t) => D.timeToX(t, CTX), y: (p) => 1000 - p };     // price p at y = 1000 - p
const box = (type, entry, target, stop, qty = 1, t0 = bars[1].ms, t1 = bars[3].ms) =>
  ({ id: 'p', type, qty, points: [{ t: t0, p: entry }, { t: t1, p: target }, { t: t1, p: stop }] });
const LONG = box('long', 900, 920, 890);        // x 110..130 · entry y 100, target y 80, stop y 110
const SHORT = box('short', 900, 880, 910);      // target y 120, stop y 90

test('a new box risks 8% of the pane in price, on the tick grid, at least 4 ticks', () => {
  assert.equal(P.RISK_PANE, 0.08);
  assert.equal(P.WIDTH_BARS, 20);
  assert.equal(P.MIN_RISK_TICKS, 4);
  assert.equal(P.risk(80, 0.25), 80);
  assert.equal(P.risk(12.37, 0.25), 12.25);
  assert.equal(P.risk(0.6, 0.25), 1);            // 4 ticks of 0.25
  assert.equal(P.risk(0.37, 0.1), 0.4);          // 4 ticks of 0.1, no float dust
  assert.equal(P.risk(1.234, 0.1), 1.2);
});

test('a new long reads RR 1:2: the stop one risk below, the target two above; a short is mirrored', () => {
  const t1 = T0 + 20 * MIN;
  assert.deepEqual(P.create('long', T0, t1, 30900, 25, 0.25),
    { type: 'long', qty: 1, points: [{ t: T0, p: 30900 }, { t: t1, p: 30950 }, { t: t1, p: 30875 }] });
  assert.deepEqual(P.create('short', T0, t1, 30900, 25, 0.25).points.map((q) => q.p), [30900, 30850, 30925]);
  assert.deepEqual(P.create('long', T0, t1, 2650.3, 0.4, 0.1).points.map((q) => q.p), [2650.3, 2651.1, 2649.9]);
  assert.equal(P.labels(P.create('long', T0, t1, 30900, 25, 0.25), 20, 0.25).center, 'RR 1:2 · Qty 1');
  assert.equal(P.isPosition(LONG), true);
  assert.equal(P.isPosition({ type: 'trend' }), false);
});

test('handles: the left edge on entry, target and stop; the right edge on the entry', () => {
  assert.deepEqual(P.handles(LONG, geo), [[110, 100], [110, 80], [110, 110], [130, 100]]);
  assert.equal(P.handles(LONG, { ...geo, y: () => null }), null);
});

test('hitTest: handles first, then anywhere inside the box', () => {
  assert.deepEqual(P.hitTest(LONG, { x: 111, y: 101 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(P.hitTest(LONG, { x: 109, y: 81 }, geo), { part: 'handle', index: 1 });
  assert.deepEqual(P.hitTest(LONG, { x: 110, y: 112 }, geo), { part: 'handle', index: 2 });
  assert.deepEqual(P.hitTest(LONG, { x: 131, y: 100 }, geo), { part: 'handle', index: 3 });
  assert.deepEqual(P.hitTest(LONG, { x: 120, y: 90 }, geo), { part: 'body' });
  assert.deepEqual(P.hitTest(SHORT, { x: 125, y: 115 }, geo), { part: 'body' });
  assert.equal(P.hitTest(LONG, { x: 140, y: 90 }, geo), null);
  assert.equal(P.hitTest(LONG, { x: 120, y: 70 }, geo), null);
});

test('long handles: the entry stays a tick inside, target and stop a tick beyond it, the edges a bar apart', () => {
  const pts = (d) => d.points.map((q) => [q.t, q.p]);
  assert.deepEqual(pts(P.setHandle(LONG, 0, bars[2].ms, 905, CTX)), [[bars[2].ms, 905], [bars[3].ms, 920], [bars[3].ms, 890]]);
  assert.equal(P.setHandle(LONG, 0, bars[1].ms, 930, CTX).points[0].p, 919.75);
  assert.equal(P.setHandle(LONG, 0, bars[1].ms, 880, CTX).points[0].p, 890.25);
  assert.equal(P.setHandle(LONG, 0, bars[4].ms, 900, CTX).points[0].t, bars[2].ms);      // never past the right edge
  assert.equal(P.setHandle(LONG, 1, bars[0].ms, 950, CTX).points[1].p, 950);
  assert.deepEqual(P.setHandle(LONG, 1, bars[0].ms, 890, CTX).points[1], { t: bars[3].ms, p: 900.25 });   // time ignored
  assert.equal(P.setHandle(LONG, 2, bars[0].ms, 870, CTX).points[2].p, 870);
  assert.equal(P.setHandle(LONG, 2, bars[0].ms, 910, CTX).points[2].p, 899.75);
  assert.deepEqual(pts(P.setHandle(LONG, 3, bars[4].ms, 1, CTX)), [[bars[1].ms, 900], [bars[4].ms, 920], [bars[4].ms, 890]]);
  assert.equal(P.setHandle(LONG, 3, bars[0].ms, 1, CTX).points[1].t, bars[2].ms);         // at least a bar after t0
  assert.equal(P.setHandle(LONG, 3, T0 + 30 * MIN, 1, CTX).points[2].t, T0 + 30 * MIN);   // beyond the data: kept
  assert.deepEqual(LONG.points[0], { t: bars[1].ms, p: 900 });                            // the original is untouched
});

test('short handles mirror the clamps', () => {
  assert.equal(P.setHandle(SHORT, 0, bars[1].ms, 870, CTX).points[0].p, 880.25);
  assert.equal(P.setHandle(SHORT, 0, bars[1].ms, 920, CTX).points[0].p, 909.75);
  assert.equal(P.setHandle(SHORT, 1, bars[1].ms, 905, CTX).points[1].p, 899.75);
  assert.equal(P.setHandle(SHORT, 1, bars[1].ms, 860, CTX).points[1].p, 860);
  assert.equal(P.setHandle(SHORT, 2, bars[1].ms, 895, CTX).points[2].p, 900.25);
  assert.equal(P.setHandle(SHORT, 2, bars[1].ms, 930, CTX).points[2].p, 930);
});

test('labels: price, move, percent of the entry, ticks and dollars (point value × qty)', () => {
  assert.deepEqual(P.labels(box('long', 30900, 30950, 30875), 20, 0.25), {
    target: 'Target 30,950.00 · +50.00 (0.16%) · 200 ticks · +$1,000',
    stop: 'Stop 30,875.00 · −25.00 (0.08%) · 100 ticks · −$500',
    center: 'RR 1:2 · Qty 1' });
  const three = box('long', 30900, 30937.5, 30875, 3);
  assert.equal(P.labels(three, 20, 0.25).target, 'Target 30,937.50 · +37.50 (0.12%) · 150 ticks · +$2,250');
  assert.equal(P.labels(three, 20, 0.25).center, 'RR 1:1.5 · Qty 3');
});

test('without a point value the labels show no dollars', () => {
  const l = P.labels(box('long', 30900, 30950, 30875), null, 0.25);
  assert.equal(l.target, 'Target 30,950.00 · +50.00 (0.16%) · 200 ticks');
  assert.equal(l.stop, 'Stop 30,875.00 · −25.00 (0.08%) · 100 ticks');
});

test('a short\'s target is a gain and its stop a loss', () => {
  const l = P.labels(box('short', 30900, 30850, 30925), 20, 0.25);
  assert.equal(l.target, 'Target 30,850.00 · +50.00 (0.16%) · 200 ticks · +$1,000');
  assert.equal(l.stop, 'Stop 30,925.00 · −25.00 (0.08%) · 100 ticks · −$500');
});

test('odd ticks and cents: one ZN tick is $15.63', () => {
  const zn = box('long', 112.5, 112.515625, 112.484375);
  assert.equal(P.labels(zn, 1000, 0.015625).target, 'Target 112.515625 · +0.015625 (0.01%) · 1 tick · +$15.63');
  assert.equal(P.fmtUsd(1000), '$1,000');
  assert.equal(P.fmtUsd(-0.5), '$0.50');
  assert.equal(P.fmtUsd(1234567.5), '$1,234,567.50');
});

test('RR is 1:X with at most 2 decimals, trailing zeros trimmed', () => {
  assert.equal(P.rr(box('long', 100, 104, 97)), '1:1.33');
  assert.equal(P.rr(box('short', 100, 99, 102)), '1:0.5');
  assert.equal(P.rr(box('long', 100, 110, 95)), '1:2');
});

/* ---- the outcome on the chart's bars ---- */
const run = (...ohlc) => ohlc.map(([o, h, l, c], i) => ({ ms: T0 + i * MIN, o, h, l, c }));
const L100 = (qty = 1, t1 = T0 + 5 * MIN) => box('long', 100, 110, 95, qty, T0 + MIN, t1);   // from bar 1

test('not entered: no bar from the bar holding t0 up to t1 trades the entry', () => {
  const bs = run([100, 101, 99, 100], [102, 104, 101, 103], [103, 105, 102, 104], [104, 106, 103, 105],
    [105, 106, 104, 105], [105, 107, 104, 106]);
  assert.deepEqual(P.outcome(L100(), bs, 20, 0.25), { kind: 'none', text: 'Not entered', path: null });   // bar 0 is before t0
  assert.deepEqual(P.outcome(L100(), [], 20, 0.25), { kind: 'none', text: 'Not entered', path: null });
});

test('closed at the target or the stop, with the path from the entry bar to the exit bar', () => {
  const up = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 106, 99.5, 105], [105, 111, 104, 110],
    [110, 112, 109, 111], [111, 112, 110, 111]);
  assert.deepEqual(P.outcome(L100(), up, 20, 0.25),
    { kind: 'closed', text: 'Closed +$200', path: { a: { t: T0 + MIN, p: 100 }, b: { t: T0 + 3 * MIN, p: 110 } } });
  assert.equal(P.outcome(L100(2), up, 20, 0.25).text, 'Closed +$400');
  assert.equal(P.outcome(L100(), up, null, 0.25).text, 'Closed +10.00');
  const down = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 101, 96, 97], [97, 98, 94, 95],
    [95, 96, 93, 94], [94, 95, 93, 94]);
  assert.deepEqual(P.outcome(L100(), down, 20, 0.25),
    { kind: 'closed', text: 'Closed −$100', path: { a: { t: T0 + MIN, p: 100 }, b: { t: T0 + 3 * MIN, p: 95 } } });
  assert.equal(P.outcome(L100(), down, null, 0.25).text, 'Closed −5.00');
});

test('bars cannot tell: both levels inside one bar, or the entry bar already at a level', () => {
  const both = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 111, 94, 100], [100, 101, 99, 100]);
  assert.deepEqual(P.outcome(L100(), both, 20, 0.25), { kind: 'ambiguous', text: 'Stop and target in one bar', path: null });
  const touch = run([101, 102, 100.5, 101], [101, 102, 94.5, 100], [100, 101, 99, 100]);
  assert.deepEqual(P.outcome(L100(), touch, 20, 0.25),
    { kind: 'ambiguous', text: 'Entry bar touched stop/target', path: null });
});

test('still open at the last close, or "open at end" when t1 is before the last bar', () => {
  const flat = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 102, 99, 101], [101, 104, 100, 103]);
  assert.deepEqual(P.outcome(L100(1, T0 + 10 * MIN), flat, 20, 0.25), { kind: 'open', text: 'Open +$60', path: null });
  assert.equal(P.outcome(L100(1, T0 + 3 * MIN), flat, 20, 0.25).kind, 'open');           // t1 on the last bar: open
  assert.deepEqual(P.outcome(L100(1, T0 + 2 * MIN), flat, 20, 0.25),
    { kind: 'expired', text: 'Open at end +$20', path: null });
  const under = run([101, 102, 100.5, 101], [101, 101, 98, 98.5], [98.5, 99, 97, 98]);
  assert.equal(P.outcome(L100(1, T0 + 9 * MIN), under, 20, 0.25).text, 'Open −$40');
  assert.equal(P.outcome(L100(1, T0 + 9 * MIN), under, null, 0.25).text, 'Open −2.00');
  const even = run([101, 102, 100.5, 101], [101, 101, 99, 100]);
  assert.equal(P.outcome(L100(1, T0 + 9 * MIN), even, 20, 0.25).text, 'Open $0');
});

test('a short is mirrored; the entry may fill on the bar holding t0', () => {
  const s = box('short', 100, 90, 105, 1, T0 + MIN, T0 + 5 * MIN);
  const fall = run([99, 99.5, 98.5, 99], [99, 101, 98, 100], [100, 100.5, 95, 96], [96, 97, 89, 90], [90, 91, 89, 90]);
  assert.deepEqual(P.outcome(s, fall, 20, 0.25),
    { kind: 'closed', text: 'Closed +$200', path: { a: { t: T0 + MIN, p: 100 }, b: { t: T0 + 3 * MIN, p: 90 } } });
  const mid = box('long', 100, 110, 95, 1, T0 + MIN + 30000, T0 + 9 * MIN);
  const bs = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 111, 99.5, 110]);
  assert.equal(P.outcome(mid, bs, 20, 0.25).text, 'Closed +$200');
});

test('the settings dialog\'s check: the order for the type, a tick apart, qty 1-10,000', () => {
  assert.equal(P.validate('long', 100, 110, 95, 1, 0.25), '');
  assert.equal(P.validate('short', 100, 90, 105, 10000, 0.25), '');
  assert.equal(P.validate('long', 2650.3, 2650.4, 2650.2, 1, 0.1), '');          // one tick of 0.1, float dust and all
  assert.match(P.validate('long', 100, 100, 95, 1, 0.25), /stop < entry < target/);
  assert.match(P.validate('long', 100, 110, 100.25, 1, 0.25), /stop < entry < target/);
  assert.match(P.validate('short', 100, 105, 90, 1, 0.25), /target < entry < stop/);
  assert.match(P.validate('long', 100, 110, 95, 0, 0.25), /Qty/);
  assert.match(P.validate('long', 100, 110, 95, 10001, 0.25), /Qty/);
  assert.match(P.validate('long', 100, 110, 95, 1.5, 0.25), /Qty/);
  assert.match(P.validate('long', NaN, 110, 95, 1, 0.25), /prices/);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/position.test.mjs`
Expected: FAIL with `Cannot find module '../../homebase/static/charts/position.js'`.

- [ ] **Step 3: Implement** `homebase/static/charts/position.js`:

```js
/* Homebase Charts — the Long / Short position tool (TradingView's risk/reward
   planner). This half is pure: a box's geometry and handles, the handles'
   clamps, the label texts, and how the planned trade played out on the
   chart's bars. The canvas drawing (drawPosition, at the end of the file)
   runs in the page only. No browser globals at load time: the Node tests
   load this file directly.

   A position is {id, type: 'long'|'short', points: [entry, target, stop], qty, color?}:
     entry  = {t: t0, p}   t0 = the box's left edge (a bar start, epoch ms)
     target = {t: t1, p}   t1 = the box's right edge (target and stop share it)
     stop   = {t: t1, p}
   long: stop < entry < target · short: target < entry < stop · every gap at least 1 tick. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const D = need('HBDrawings', './drawings.js');

const WIDTH_BARS = 20;       // a new box reaches 20 bars to the right
const RISK_PANE = 0.08;      // a new box's risk: the price distance of 8% of the price pane's height ...
const MIN_RISK_TICKS = 4;    // ... and at least 4 ticks
const QTY_MAX = 10000;
const MINUS = '−';      // the labels' minus sign, as in the spec: −25.00, −$500

const isPosition = (d) => !!d && (d.type === 'long' || d.type === 'short');

/* A new box's risk: `span` (the price distance of 8% of the pane's height) on the tick grid, at least 4 ticks. */
function risk(span, tick) {
  return D.roundToTick(Math.max(MIN_RISK_TICKS * tick, Math.abs(span)), tick);
}

/* A new box at (t0, entry) reaching to t1: the stop one risk R away and the target two (RR 1:2); a short is
   mirrored. Quantity 1. */
function create(type, t0, t1, entry, R, tick) {
  const dir = type === 'short' ? -1 : 1, r = (p) => D.roundToTick(p, tick);
  return { type, points: [{ t: t0, p: r(entry) }, { t: t1, p: r(entry + dir * 2 * R) }, { t: t1, p: r(entry - dir * R) }],
    qty: 1 };
}

/* The handles [[x, y] x 4]: 0 (t0, entry), 1 (t0, target), 2 (t0, stop), 3 (t1, entry); null when a point
   cannot be placed. geo = {x: (t) => px | null, y: (p) => px | null}. */
function handles(d, geo) {
  const [E, T, S] = d.points, x0 = geo.x(E.t), x1 = geo.x(T.t), yE = geo.y(E.p), yT = geo.y(T.p), yS = geo.y(S.p);
  if ([x0, x1, yE, yT, yS].some((v) => v == null)) return null;
  return [[x0, yE], [x0, yT], [x0, yS], [x1, yE]];
}

/* A handle (by index) first, then anywhere inside the box (t0 to t1, target to stop). */
function hitTest(d, pt, geo) {
  const hs = handles(d, geo);
  if (!hs) return null;
  for (let i = 0; i < hs.length; i++) {
    if (Math.hypot(pt.x - hs[i][0], pt.y - hs[i][1]) <= D.HANDLE_TOL) return { part: 'handle', index: i };
  }
  const [[x0], [, yT], [, yS], [x1]] = hs, tol = D.LINE_TOL;
  const inside = pt.x >= Math.min(x0, x1) - tol && pt.x <= Math.max(x0, x1) + tol
    && pt.y >= Math.min(yT, yS) - tol && pt.y <= Math.max(yT, yS) + tol;
  return inside ? { part: 'body' } : null;
}

/* d with handle k dragged to (t, p), clamped so the box stays a valid trade:
   0 moves t0 and the entry (the entry at least a tick inside (stop, target); t0 at least a bar before t1);
   1 moves the target (at least a tick beyond the entry); 2 the stop (at least a tick beyond the entry, on the
   risk side); 3 moves t1 (at least a bar after t0). ctx = {bars, isTime, barMs, tick}. */
function setHandle(d, k, t, p, ctx) {
  const tick = ctx.tick, long = d.type === 'long', r = (x) => D.roundToTick(x, tick);
  const L = (x) => D.logicalOf(ctx.bars, x, ctx.isTime, ctx.barMs);
  let [E, T, S] = d.points;
  if (k === 0) {
    const lo = long ? S.p + tick : T.p + tick, hi = long ? T.p - tick : S.p - tick;
    const t0 = L(t) != null && L(t) > L(T.t) - 1 ? D.shiftTime(T.t, -1, ctx) : t;
    E = { t: t0, p: r(Math.min(hi, Math.max(lo, p))) };
  } else if (k === 1) {
    T = { t: T.t, p: r(long ? Math.max(p, E.p + tick) : Math.min(p, E.p - tick)) };
  } else if (k === 2) {
    S = { t: S.t, p: r(long ? Math.min(p, E.p - tick) : Math.max(p, E.p + tick)) };
  } else if (k === 3) {
    const t1 = L(t) != null && L(t) < L(E.t) + 1 ? D.shiftTime(E.t, 1, ctx) : t;
    T = { t: t1, p: T.p };
    S = { t: t1, p: S.p };
  }
  return { ...d, points: [E, T, S] };
}

const sign = (v) => (v > 0 ? '+' : v < 0 ? MINUS : '');

/* "$1,000" · "$15.63": whole dollars show no cents. */
function fmtUsd(v) {
  const cents = Math.round(Math.abs(v) * 100), whole = cents % 100 === 0;
  return '$' + (cents / 100).toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 });
}

/* A P&L for a price move `move` in the trade's favour: dollars (x point value x qty) when the point value is
   known, else the move in points (one contract): "+$1,000" · "−$500" · "$0" · "+50.00". */
function fmtPnl(move, pv, qty, tick) {
  if (pv == null) {
    const m = D.roundToTick(move, tick);
    return sign(m) + Cat.fmtPrice(Math.abs(m), tick);
  }
  const usd = move * pv * qty;
  return sign(Math.round(usd * 100)) + fmtUsd(usd);
}

/* "1:2" · "1:1.5": reward ÷ risk, at most 2 decimals, trailing zeros trimmed. */
function rr(d) {
  const [E, T, S] = d.points, loss = Math.abs(E.p - S.p);
  return `1:${loss > 0 ? Number((Math.abs(T.p - E.p) / loss).toFixed(2)) : '—'}`;
}

/* The box's texts: the target and stop labels ("Target 30,950.00 · +50.00 (0.16%) · 200 ticks · +$1,000")
   and the centre label's first line ("RR 1:2 · Qty 1"). The target is a gain and the stop a loss, for a short
   as for a long. The "· $…" part needs the point value (pv). */
function labels(d, pv, tick) {
  const [E, T, S] = d.points, qty = d.qty || 1;
  const part = (name, px, gain) => {
    const dist = Math.abs(D.roundToTick(px - E.p, tick)), s = gain ? '+' : MINUS, n = Math.round(dist / tick);
    const pct = E.p ? (dist / Math.abs(E.p) * 100).toFixed(2) : '0.00';
    const bits = [`${name} ${Cat.fmtPrice(px, tick)}`, `${s}${Cat.fmtPrice(dist, tick)} (${pct}%)`, `${n} tick${n === 1 ? '' : 's'}`];
    if (pv != null) bits.push(s + fmtUsd(dist * pv * qty));
    return bits.join(' · ');
  };
  return { target: part('Target', T.p, true), stop: part('Stop', S.p, false),
    center: `RR ${rr(d)} · Qty ${qty.toLocaleString('en-US')}` };
}

/* How the planned trade played out on the chart's bars ([{ms, o, h, l, c}] ascending), honest about what bars
   cannot tell. Entered on the first bar from the one holding t0 whose range holds the entry (none up to t1:
   'none'). An entry bar that also reaches the target or stop, or a later bar reaching both, is 'ambiguous'.
   Else the first later bar (up to t1) reaching one closes it ('closed', with the path from the entry bar to
   the exit bar); with no exit, 'open' at the last close when t1 is at or after the last bar, else 'expired'
   ("Open at end") at the close of the last bar at or before t1. */
function outcome(d, bars, pv, tick) {
  const [E, T, S] = d.points, long = d.type === 'long', dir = long ? 1 : -1, qty = d.qty || 1, n = bars.length;
  const none = { kind: 'none', text: 'Not entered', path: null };
  if (!n) return none;
  const from = Math.max(0, D.barIndexAt(bars, E.t)), to = D.barIndexAt(bars, T.t);
  let ie = -1;
  for (let i = from; i <= to; i++) if (bars[i].l <= E.p && E.p <= bars[i].h) { ie = i; break; }
  if (ie < 0) return none;
  const hitT = (b) => (long ? b.h >= T.p : b.l <= T.p), hitS = (b) => (long ? b.l <= S.p : b.h >= S.p);
  const eb = bars[ie];
  if (hitT(eb) || hitS(eb)) return { kind: 'ambiguous', text: 'Entry bar touched stop/target', path: null };
  for (let i = ie + 1; i <= to; i++) {
    const b = bars[i], t = hitT(b), s = hitS(b);
    if (t && s) return { kind: 'ambiguous', text: 'Stop and target in one bar', path: null };
    if (t || s) {
      const px = t ? T.p : S.p;
      return { kind: 'closed', text: `Closed ${fmtPnl((px - E.p) * dir, pv, qty, tick)}`,
        path: { a: { t: eb.ms, p: E.p }, b: { t: b.ms, p: px } } };
    }
  }
  if (T.t >= bars[n - 1].ms) return { kind: 'open', text: `Open ${fmtPnl((bars[n - 1].c - E.p) * dir, pv, qty, tick)}`, path: null };
  return { kind: 'expired', text: `Open at end ${fmtPnl((bars[to].c - E.p) * dir, pv, qty, tick)}`, path: null };
}

/* '' when (entry, target, stop, qty) make a valid box of this type, else why not (the dialog shows it). */
function validate(type, entry, target, stop, qty, tick) {
  if (![entry, target, stop].every(Number.isFinite)) return 'Entry, target and stop are prices';
  if (!Number.isInteger(qty) || qty < 1 || qty > QTY_MAX) return `Qty is a whole number from 1 to ${QTY_MAX.toLocaleString('en-US')}`;
  const above = (a, b) => D.roundToTick(b - a, tick) >= tick;   // b at least a tick above a
  if (type === 'long' && !(above(stop, entry) && above(entry, target))) return 'A long needs stop < entry < target, at least 1 tick apart';
  if (type === 'short' && !(above(target, entry) && above(entry, stop))) return 'A short needs target < entry < stop, at least 1 tick apart';
  return '';
}

const api = { WIDTH_BARS, RISK_PANE, MIN_RISK_TICKS, QTY_MAX, MINUS, isPosition, risk, create, handles, hitTest,
  setHandle, fmtUsd, fmtPnl, rr, labels, outcome, validate };
if (typeof window !== 'undefined') window.HBPosition = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/position.test.mjs`, then `node --test tests/js/*.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/position.js tests/js/position.test.mjs
git commit -m "feat(charts): HBPosition — long/short box geometry, clamped handles, labels in 1:X and dollars, honest outcome on bars

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Long/Short tools on the page — rail, placement, handles, drawing, double-click settings

**Files:**
- Modify: `homebase/static/charts/position.js` (add `drawPosition`, browser only)
- Modify: `homebase/static/charts/drawings.js` (long/short dispatch; primitive; placement; double-click)
- Modify: `tests/js/drawings.test.mjs`
- Modify: `homebase/static/charts/cell.js` (`pv`; palette zone colours)
- Modify: `homebase/static/charts/app.js` (`positionDialog`; `host.onPosition`)
- Modify: `homebase/static/charts.html`, `homebase/static/charts/charts.css`, `homebase/static/charts/icons.js`

**Interfaces:**
- Consumes:
  - Task 3's `HBPosition`: `handles`, `hitTest`, `setHandle`, `create`, `risk`, `labels`, `outcome`, `validate`, `WIDTH_BARS`, `RISK_PANE`, `QTY_MAX`.
  - Task 2's `Controller.at(pt, e)`, which snaps the entry with the magnet, and the rig `pointerRig(saved, {tool, magnet, rigBars})`, `ohlc`, `withWindow`.
  - Task 1's `point_value` in the history message; long/short drawings accepted by `PUT /api/drawings/{root}`.
  - Existing: `shiftTime`, `commit`, `own`/`release`, `openDialog`/`closeDialog`, the page's `drawings` store.
- Produces:
  - `HBPosition.drawPosition(ctx, d, geo, P, pctx)`, where `pctx = {tick, pv, bars, size: {width, height}, font, selected}`.
  - `HBDrawings.setPoint(d, k, t, p, ctx)`: a 5th argument, used by long/short only.
  - `Controller.newPosition(type, at) -> {type, points, qty}` and `Controller.onDbl(e)`.
  - The host gains `onPosition(cell, d)`.
  - `Cell.pv` (number | null).
  - Palette keys `profitZone: 'rgba(8,153,129,.20)'` and `lossZone: 'rgba(242,54,69,.20)'`.
  - Page `positionDialog(cell, d)`.
  - Rail tools `data-tool="long"` / `"short"`.
  - Test rig option `onPosition`.

- [ ] **Step 1: Write the failing tests.** In `tests/js/drawings.test.mjs`, change the rig's signature line to

```js
function pointerRig(saved, { tool = 'cursor', magnet = { on: false, mode: 'weak' }, rigBars = bars, onPosition = () => {} } = {}) {
```

and its controller line to

```js
  const ctl = new D.Controller(cell, { tool: () => now, toolDone() { now = 'cursor'; }, drawings: store,
    magnet: () => magnet, onPosition });
```

Append at the end of the file:

```js
/* ---- long / short boxes ---- */
const Pos = require('../../homebase/static/charts/position.js');
const posBox = { id: 'p', type: 'long', qty: 1,
  points: [{ t: bars[1].ms, p: 900 }, { t: bars[3].ms, p: 920 }, { t: bars[3].ms, p: 890 }] };   // x 110..130, y 80..110

test('long/short boxes go to HBPosition for handles, hits and handle drags; a move shifts all three points', () => {
  assert.deepEqual(D.handlePoints(posBox, geo), Pos.handles(posBox, geo));
  assert.deepEqual(D.hitTest(posBox, { x: 131, y: 100 }, geo), { part: 'handle', index: 3 });
  assert.deepEqual(D.hitTest(posBox, { x: 120, y: 90 }, geo), { part: 'body' });
  assert.deepEqual(D.setPoint(posBox, 1, bars[0].ms, 880, { ...TIME, tick: 0.25 }).points[1], { t: bars[3].ms, p: 900.25 });
  const moved = D.moveDrawing(posBox, 1, 5, 0.25, TIME);
  assert.deepEqual(moved.points, [{ t: bars[2].ms, p: 905 }, { t: bars[4].ms, p: 925 }, { t: bars[4].ms, p: 895 }]);
  assert.equal(moved.qty, 1);
  assert.equal(D.samePoints(posBox, moved), false);
});

test('the long tool places a 1:2 box: risk 8% of the pane, 20 bars wide, the entry on the magnet', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'long', magnet: { on: true, mode: 'weak' }, rigBars: ohlc });
  await R.store.ensure('NQ');
  await R.gesture([[120, 85], [150, 60]]);           // press-drag-release places at the press: the drag is ignored
  const [d] = R.store.list('NQ');
  const t1 = bars[4].ms + 18 * MIN;                   // bar 2 + 20 bars, past the last bar: extrapolated
  assert.deepEqual({ type: d.type, qty: d.qty, points: d.points },
    { type: 'long', qty: 1, points: [{ t: bars[2].ms, p: 912 }, { t: t1, p: 1072 }, { t: t1, p: 832 }] });   // 8% of 1000 px = 80.00
  assert.equal(R.ctl.sel, d.id);
  assert.equal(R.tool(), 'cursor');
  assert.equal(R.puts().length, 1);
  R.done();
});

test('the short tool mirrors it', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'short', rigBars: ohlc });
  await R.store.ensure('NQ');
  await R.gesture([[120, 85]]);
  assert.deepEqual(R.store.list('NQ')[0].points.map((q) => q.p), [915, 755, 995]);
  R.done();
});

test('a double-click on a box opens its settings; on empty chart it does nothing', async (t) => {
  withWindow(t);
  const opened = [];
  const R = pointerRig([posBox], { onPosition: (cell, d) => opened.push(d.id) });
  await R.store.ensure('NQ');
  const dbl = (x, y) => R.ctl.onDbl({ clientX: x, clientY: y, preventDefault() {}, stopPropagation() {} });
  dbl(120, 95);
  dbl(300, 95);
  assert.deepEqual(opened, ['p']);
  assert.equal(R.ctl.sel, 'p');
  R.done();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/drawings.test.mjs`
Expected: FAIL. `handlePoints` treats the box as a trend line, `R.ctl.onDbl` is not a function, and the long tool places nothing.

- [ ] **Step 3: `drawings.js`, the dispatch.** After the `LINE_TOL` constant add:

```js
/* Long / short boxes live in HBPosition (position.js loads after this file and builds on it), looked up when
   first needed; Node requires it. */
let PosLib = null;
function Pos() {
  if (!PosLib) PosLib = (typeof window !== 'undefined' && window.HBPosition) || (typeof require === 'function' ? require('./position.js') : null);
  return PosLib;
}
const isPos = (d) => d.type === 'long' || d.type === 'short';
```

Make the first line of `handlePoints(d, geo)` `if (isPos(d)) return Pos().handles(d, geo);`, and the first line of `hitTest(d, pt, geo)` `if (isPos(d)) return Pos().hitTest(d, pt, geo);`. Replace `setPoint` (and its comment) with:

```js
/* d with handle k moved to (t, p); a rectangle's side corners (2, 3) take
   their time from one stored point and their price from the other; a long /
   short box's handles are clamped by HBPosition.setHandle (ctx = the chart's
   {bars, isTime, barMs, tick}). */
function setPoint(d, k, t, p, ctx) {
  if (isPos(d)) return Pos().setHandle(d, k, t, p, ctx);
  if (d.type === 'hline') return { ...d, points: [{ p }] };
  const [a, b] = d.points;
  let points;
  if (d.type === 'rect') {
    points = [[{ t, p }, b], [a, { t, p }], [{ t, p: a.p }, { t: b.t, p }], [{ t: a.t, p }, { t, p: b.p }]][k];
  } else points = k === 0 ? [{ t, p }, b] : [a, { t, p }];
  return { ...d, points };
}
```

`moveDrawing` and `samePoints` already handle 3 points. Moving a box by its body shifts every point, as the spec wants.

- [ ] **Step 4: `drawings.js`, the primitive draws boxes.** In `Primitive.draw`, replace the line `for (const d of c.items()) if (d.type !== 'hline') drawShape(ctx, d, geo, P);` with:

```js
      const pc = { tick: c.cell.tick, pv: c.cell.pv, bars: c.cell.bars, size: mediaSize, font: `12px ${window.HBCell.FONT}` };
      for (const d of c.items()) {
        if (isPos(d)) Pos().drawPosition(ctx, d, geo, P, { ...pc, selected: d.id === c.sel });
        else if (d.type !== 'hline') drawShape(ctx, d, geo, P);
      }
```

The selected drawing's handle dots still come from the existing code below, through `handlePoints`, which now dispatches.

- [ ] **Step 5: `drawings.js`, the controller.**

In `onDown`, tool branch, right after the `hline` line, add:

```js
      if (tool === 'long' || tool === 'short') { this.commit(this.newPosition(tool, at)); return; }
```

A box is committed on the press. As with the horizontal line, the rest of the press (a drag) changes nothing, and `commit` returns the rail to the cursor with the box selected.

In `onMove`, change `setPoint(orig, index, at.t, at.p)` to `setPoint(orig, index, at.t, at.p, this.ctx())`.

In the constructor, add `dbl: (e) => this.onDbl(e)` to `this.on`, and register it after the `pointerleave` line: `this.box.addEventListener('dblclick', this.on.dbl, true);`. In `destroy()`, add `this.box.removeEventListener('dblclick', this.on.dbl, true);`.

Add the methods (after `commit`):

```js
  /* A new long/short box at the pointer: risk = the price distance of 8% of the price pane's height (on the
     tick grid, at least 4 ticks), target at 2R (RR 1:2), 20 bars wide (time bars extrapolate past the last
     bar, others stop at it). The entry is `at`, already on the magnet. */
  newPosition(type, at) {
    const c = this.cell, P = Pos();
    const span = Math.abs(c.candles.coordinateToPrice(0) - c.candles.coordinateToPrice(P.RISK_PANE * this.paneH()));
    return P.create(type, at.t, shiftTime(at.t, P.WIDTH_BARS, this.ctx()), at.p, P.risk(span, c.tick), c.tick);
  }

  /* Double-click on a long/short box (cursor mode): select it and open its settings (host.onPosition).
     Captured before Lightweight Charts sees it: its own double-click would reset the price scale. */
  onDbl(e) {
    if (this.host.tool() !== 'cursor' || !this.cell.chart) return;
    const pt = this.local(e), geo = this.geo();
    if (!geo || !this.inPane(pt)) return;
    const all = this.items();
    for (let i = all.length - 1; i >= 0; i--) {
      if (!isPos(all[i]) || !hitTest(all[i], pt, geo)) continue;
      e.preventDefault();
      e.stopPropagation();
      this.sel = all[i].id;
      this.refresh();
      this.host.onPosition(this.cell, all[i]);
      return;
    }
  }
```

In the file header, add "long/short boxes (HBPosition)" to the list of what the controller places.

- [ ] **Step 6: Run the Node tests**

Run: `node --test tests/js/drawings.test.mjs tests/js/position.test.mjs`
Expected: PASS. No test draws, and `drawPosition` arrives in Step 7.

- [ ] **Step 7: `position.js`, `drawPosition`** (browser only: touches no global at load time). Insert before `const api = {`, and add `drawPosition` to `api`:

```js
/* ---------------- page only: the canvas drawing ---------------- */
/* One box on the price pane (media coordinates), TradingView's look: the profit and loss zones (no borders),
   the entry line across the box, the outcome's dashed path, a 1px outline when selected, and three labels
   centred on the box (target outside the profit zone, stop outside the loss zone, the centre two lines on the
   entry line), each kept inside the pane. P = HBCell.palette(); pctx = {tick, pv, bars, size: {width,
   height}, font, selected}. The handle dots are drawn by the drawings primitive. */
function drawPosition(ctx, d, geo, P, pctx) {
  const hs = handles(d, geo);
  if (!hs) return;
  const [[x0, yE], [, yT], [, yS], [x1]] = hs, long = d.type === 'long';
  const left = Math.min(x0, x1), w = Math.max(1, Math.abs(x1 - x0)), top = Math.min(yT, yS), bot = Math.max(yT, yS);
  ctx.fillStyle = P.profitZone;
  ctx.fillRect(left, Math.min(yE, yT), w, Math.abs(yT - yE));
  ctx.fillStyle = P.lossZone;
  ctx.fillRect(left, Math.min(yE, yS), w, Math.abs(yS - yE));
  ctx.strokeStyle = P.text2;
  ctx.lineWidth = 1;
  const ye = Math.round(yE) + 0.5;
  ctx.beginPath(); ctx.moveTo(left, ye); ctx.lineTo(left + w, ye); ctx.stroke();
  const out = outcome(d, pctx.bars, pctx.pv, pctx.tick);
  if (out.path) {
    const ax = geo.x(out.path.a.t), bx = geo.x(out.path.b.t), ay = geo.y(out.path.a.p), by = geo.y(out.path.b.p);
    if (ax != null && bx != null && ay != null && by != null) {
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  if (pctx.selected) ctx.strokeRect(Math.round(left) + 0.5, Math.round(top) + 0.5, Math.round(w), Math.round(bot - top));
  const lab = labels(d, pctx.pv, pctx.tick), cx = left + w / 2, GAP = 4;
  ctx.font = pctx.font;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const label = (lines, bg, yAt) => {   // yAt(height) -> the label's top before clamping
    const bw = Math.max(...lines.map((s) => ctx.measureText(s).width)) + 16, bh = lines.length * 16 + 4;
    const bx = Math.max(2, Math.min(cx - bw / 2, pctx.size.width - bw - 2));
    const by = Math.max(2, Math.min(yAt(bh), pctx.size.height - bh - 2));
    ctx.fillStyle = bg;
    ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 4); ctx.fill();
    ctx.fillStyle = P.onAccent;
    lines.forEach((s, i) => ctx.fillText(s, bx + bw / 2, by + 10 + i * 16));
  };
  label([lab.target], P.up, (h) => (long ? top - GAP - h : bot + GAP));
  label([lab.stop], P.down, (h) => (long ? bot + GAP : top - GAP - h));
  label([lab.center, out.text], P.text2, (h) => yE - h / 2);
}
```

- [ ] **Step 8: `cell.js`.**
  - In `palette()`, add `profitZone: 'rgba(8,153,129,.20)', lossZone: 'rgba(242,54,69,.20)',` to the object shared by both themes (next to `handleFill`).
  - In the constructor, after `this.tick = 0.25;` on the fields line, add `this.pv = null;   // USD per 1.00 of price for one contract (the history's point_value; null: unknown)`.
  - In `onHistory`, after `this.tick = m.tick_size;`, add `this.pv = m.point_value ?? null;`.
  - In the header's host list, add `onPosition(cell, d)`.

- [ ] **Step 9: `app.js`, the position settings dialog.** In `hostFor(id)`, add `onPosition(cell, d) { positionDialog(cell, d); },`. After `settingsDialog`, add:

```js
/* Double-click on a long/short box: Entry, Target, Stop (rounded to the tick) and Qty. OK checks the order for
   the type; a wrong one shows why under the fields and saves nothing. */
function positionDialog(cell, d) {
  const Pos = window.HBPosition, D = window.HBDrawings, tick = cell.tick, root = cell.dc ? cell.dc.root : cell.cfg.root;
  const box = openDialog(d.type === 'long' ? 'Long position' : 'Short position', 'small');
  const form = mk('div', 'dlg-fields'), err = mk('div', 'dlg-err'), inputs = {};
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const [E, T, S] = d.points;
  for (const [key, label, v] of [['entry', 'Entry', E.p], ['target', 'Target', T.p], ['stop', 'Stop', S.p], ['qty', 'Qty', d.qty || 1]]) {
    const row = mk('div', 'field'), id = `pos-${key}`, lab = mk('label', '', label), ctl = mk('input', key === 'qty' ? '' : 'price');
    ctl.type = 'number';
    ctl.id = id;
    ctl.step = key === 'qty' ? '1' : String(tick);
    if (key === 'qty') { ctl.min = '1'; ctl.max = String(Pos.QTY_MAX); }
    ctl.value = String(v);
    lab.htmlFor = id;
    row.append(lab, ctl);
    form.appendChild(row);
    inputs[key] = ctl;
  }
  const foot = mk('div', 'dlg-foot'), cancel = mk('button', 'btn btn-ghost', 'Cancel'), ok = mk('button', 'btn btn-primary', 'OK');
  cancel.type = 'button';
  ok.type = 'button';
  cancel.onclick = closeDialog;
  ok.onclick = () => {
    const num = (k) => (inputs[k].value.trim() === '' ? NaN : Number(inputs[k].value));
    const entry = D.roundToTick(num('entry'), tick), target = D.roundToTick(num('target'), tick);
    const stop = D.roundToTick(num('stop'), tick), qty = num('qty');
    const why = Pos.validate(d.type, entry, target, stop, qty, tick);
    if (why) { err.textContent = why; err.hidden = false; return; }
    const now = drawings.list(root).find((x) => x.id === d.id);
    closeDialog();
    if (!now) return;   // removed meanwhile (on another chart of this symbol)
    drawings.replace(root, { ...now, qty, points: [{ t: now.points[0].t, p: entry }, { t: now.points[1].t, p: target },
      { t: now.points[2].t, p: stop }] });
  };
  form.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') ok.click(); });
  foot.append(cancel, ok);
  box.append(form, err, foot);
  inputs.entry.focus();
  inputs.entry.select();
}
```

- [ ] **Step 10: Shell, styles, icons.**

`icons.js`: add `trending-up, trending-down` to the header's Lucide list and to the "derive from Feather" list, and add (Lucide 1.48.0):

```js
  long: svg('<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>'),
  short: svg('<path d="M16 17h6v-6"/><path d="m22 17-8.5-8.5-5 5L2 7"/>'),
```

`charts.html`: in `#rail`, right after the Rectangle button, insert:

```html
    <button class="rail-btn" type="button" data-tool="long" title="Long position" aria-pressed="false"><span class="icw" data-icon="long"></span></button>
    <button class="rail-btn" type="button" data-tool="short" title="Short position" aria-pressed="false"><span class="icw" data-icon="short"></span></button>
```

Also add `<script src="/static/charts/position.js?v=3"></script>` right after the `drawings.js` script tag.

`charts.css`: after `.field input[type="number"]:focus`, add:

```css
.field input.price { width: 128px; }
.dlg-err { padding: 0 20px 4px; color: var(--down); font-size: 12px; }
```

The rail's existing `data-tool` wiring (`init`) and `setCursor` (crosshair for any tool) already cover the two new tools.

- [ ] **Step 11: Syntax-check and run the suites**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green.

- [ ] **Step 12: Commit**

```bash
git add homebase/static/charts/position.js homebase/static/charts/drawings.js tests/js/drawings.test.mjs homebase/static/charts/cell.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js
git commit -m "feat(charts): Long / Short position tools — RR 1:2 box at 8% of the pane, clamped handles, labels with dollars, the outcome on bars, double-click settings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check (replay :8854, NQ 1m):**
- The rail reads cursor · trend · horizontal · rectangle · **Long position** · **Short position** · measure; the tooltips name the tools.
- One click with Long places a box:
  - green profit zone above, red loss zone below, no borders, a grey entry line;
  - the box height is about 24% of the pane (8% risk + 16% reward) and it is 20 bars wide;
  - the rail returns to the cursor and the box is selected (4 white handles, grey outline).
- Boxes placed at different zoom levels all start with the same on-screen height, because the risk is 8% of the pane at the moment of placing. After that their prices are fixed.
- Labels:
  - the target label reads like `Target 30,950.00 · +50.00 (0.16%) · 200 ticks · +$1,000` above the box;
  - the stop label (`−…`, U+2212) sits below;
  - the centre reads `RR 1:2 · Qty 1` over the outcome line;
  - a label pushed off the pane stays inside it.
- Short mirrors all of this.
- Handles: drag the entry handle past the target and it stops a tick short; drag the target below the entry and it stops a tick above; drag the stop above the entry and it stops a tick below; drag the right edge left past the left edge and it stops a bar after; the RR text updates live.
- Magnet (strong) on: the entry, target and stop handles snap to O/H/L/C; the right-edge handle only moves in time.
- Dragging the body moves the whole box without snapping.
- Outcome, on a box placed over past bars:
  - `Closed +$…` with a dashed grey path from the entry bar to the exit bar;
  - a box whose entry is never traded: `Not entered`;
  - a stop inside the entry bar: `Entry bar touched stop/target`;
  - a box reaching past the last bar: `Open ±$…`, updating live;
  - a box that ended in the past with no exit: `Open at end ±$…`.
- Double-click a box: a small dialog titled `Long position` with Entry, Target, Stop and Qty.
  - Wrong values (e.g. a target below the entry) → an inline red error and nothing saved; Esc and Cancel close it.
  - OK with good values → the box updates on every NQ chart.
- The box survives a reload and shows on a second NQ chart.
- Delete removes it; remove-all counts it.
- The chart never pans while placing or dragging; dark theme works; zero console errors.
- On BTC (point_value 5): dollars show. On a root the contracts table lacks: labels show points only.

---
### Task 5: `HBSettings` — the chart-settings model, pure

**Files:**
- Create: `homebase/static/charts/settings.js`
- Create: `tests/js/settings.test.mjs`

**Interfaces:**
- Consumes: `HBCatalog.decimals` (in the page as `window.HBCatalog`, in Node via `require('./catalog.js')`).
- Produces `window.HBSettings` (and `module.exports`):
  - `FIELDS`: `[{key, type: 'bool'|'color'|'int'|'choice'|'precision', def, min?, max?, choices?}]`, in dialog order.
  - `DEFAULTS` (frozen; theme-following colours are `null`).
  - `THEMED`: `{field: paletteKey}` for the theme-following colours.
  - `LINE_STYLE = {solid: 0, dotted: 1, dashed: 2}`.
  - `TIMEZONES` (`[[value, text, IANA|null]]`).
  - `PALETTE` (6 rows × 10 hex).
  - `CLEAR = 'rgba(0,0,0,0)'`.
  - The fields and their defaults: `prevClose false · body/borders/wick true · bodyUp bodyDown borderUp borderDown wickUp wickDown null · precision null (Default) | 0..6 · timezone 'exchange' (utc chicago london local) · ethBg false · ethBgColor 'rgba(120,123,134,.08)' · title true · titleMode 'both' (ticker description) · ohlc barChange volume indTitles indArgs indValues true · scalePriceOnly false · lastLabel lastLine true · lastLineStyle 'dotted' · countdown true · marginTop 10 (0..40) · marginBottom 15 (0..40) · rightOffset 6 (0..100) · bg null · vertGrid horzGrid true · vertGridColor horzGridColor null · crossColor null · crossStyle 'dashed' · crossWidth 1 (1..4) · watermark true · watermarkColor null · scaleText null · scaleFont 12 (10..16) · scaleLines null`.
  - Colours: `parseColor(s) -> {r,g,b,a}|null`; `fmtColor(c) -> '#RRGGBB'|'rgba(r,g,b,.a)'`; `hexOf(s)`; `alphaOf(s)`; `withAlpha(s, a)`.
  - The model: `normalize(obj) -> full`; `overrides(full) -> {non-defaults}`; `resolve(overrides, palette) -> concrete`.
  - Mappings: `chartOptions(r)`, `candleOptions(r, tick)`, `scaleMargins(r)`, `legendFlags(r) -> {title, titleMode, ohlc, change, volume, indTitles, indArgs, indValues}`, `barColor(bar, prev, r)`, `barColorsByPrevClose(bars, r)`.
  - Legend: `splitLabel(label, hasParams)`, `legendLabel(label, hasParams, flags)`, `titleText(root, name, interval, mode)`.
  - Time: `zoneOffsetMs(zone, ms)`, `wallSeconds(ms, tz)`, `outsideRth(etWallS)`, `barCloseEt(bar, barMs, alwaysOpen)`, `fmtCountdown(ms)`.
  - `templateNameError(name) -> '' | message`.
- Tasks 6 and 7 use all of it. Task 8 adds the Events fields and a `list` field type.

- [ ] **Step 1: Write the failing tests** — `tests/js/settings.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const S = require('../../homebase/static/charts/settings.js');

/* HBCell.palette()'s keys that settings resolve against */
const LIGHT = { up: '#089981', down: '#F23645', bg: '#FFFFFF', grid: '#F0F3FA', cross: '#9598A1',
  watermark: 'rgba(15,15,15,.06)', text2: '#787B86', border: '#E0E3EB' };
const DARK = { ...LIGHT, bg: '#0F0F0F', grid: '#1C1C1C', watermark: 'rgba(219,219,219,.06)', text2: '#8C8C8C', border: '#2E2E2E' };

test('the defaults: every field, colours that follow the theme are null, the spec\'s values', () => {
  const d = S.DEFAULTS;
  assert.deepEqual(Object.keys(d), S.FIELDS.map((f) => f.key));
  for (const k of Object.keys(S.THEMED)) assert.equal(d[k], null, k);
  assert.equal(d.prevClose, false);
  assert.equal(d.body && d.borders && d.wick, true);
  assert.equal(d.precision, null);
  assert.equal(d.timezone, 'exchange');
  assert.equal(d.ethBg, false);
  assert.equal(d.ethBgColor, 'rgba(120,123,134,.08)');
  assert.equal(d.title && d.ohlc && d.barChange && d.volume && d.indTitles && d.indArgs && d.indValues, true);
  assert.equal(d.titleMode, 'both');
  assert.equal(d.scalePriceOnly, false);
  assert.equal(d.lastLabel && d.lastLine && d.countdown, true);
  assert.equal(d.lastLineStyle, 'dotted');
  assert.deepEqual([d.marginTop, d.marginBottom, d.rightOffset], [10, 15, 6]);
  assert.equal(d.vertGrid && d.horzGrid && d.watermark, true);
  assert.deepEqual([d.crossStyle, d.crossWidth, d.scaleFont], ['dashed', 1, 12]);
  assert.ok(Object.isFrozen(d));
});

test('colours: #RRGGBB or rgba(r,g,b,a), one spelling each', () => {
  assert.deepEqual(S.parseColor('#26a69a'), { r: 38, g: 166, b: 154, a: 1 });
  assert.deepEqual(S.parseColor(' rgba(120, 123, 134, 0.08) '), { r: 120, g: 123, b: 134, a: 0.08 });
  for (const bad of ['teal', '#12345', '#1234567', 'rgba(256,0,0,1)', 'rgba(1,2,3,1.5)', 'rgb(1,2,3)', null, 7]) {
    assert.equal(S.parseColor(bad), null, String(bad));
  }
  assert.equal(S.fmtColor({ r: 38, g: 166, b: 154, a: 1 }), '#26A69A');
  assert.equal(S.fmtColor({ r: 120, g: 123, b: 134, a: 0.08 }), 'rgba(120,123,134,.08)');
  assert.equal(S.fmtColor({ r: 0, g: 0, b: 0, a: 0 }), S.CLEAR);
  assert.equal(S.hexOf('rgba(15,15,15,.06)'), '#0F0F0F');
  assert.equal(S.alphaOf('rgba(15,15,15,.06)'), 0.06);
  assert.equal(S.alphaOf('#FFFFFF'), 1);
  assert.equal(S.withAlpha('#2962FF', 0.5), 'rgba(41,98,255,.5)');
  assert.equal(S.withAlpha('rgba(41,98,255,.5)', 1), '#2962FF');
});

test('normalize keeps every field, drops the rest, clamps numbers, checks colours and choices', () => {
  const n = S.normalize({ junk: 1, marginTop: 55, marginBottom: '20', rightOffset: -3, crossWidth: 2.6, scaleFont: 9,
    precision: 9, bodyUp: '#26a69a', bg: 'rgba(0, 0, 0, 0.5)', wickUp: 'teal', timezone: 'Mars', lastLineStyle: 'dashed',
    ohlc: 'no', ethBgColor: null });
  assert.equal('junk' in n, false);
  assert.deepEqual(Object.keys(n), S.FIELDS.map((f) => f.key));
  assert.deepEqual([n.marginTop, n.marginBottom, n.rightOffset, n.crossWidth, n.scaleFont, n.precision], [40, 20, 0, 3, 10, 6]);
  assert.equal(n.bodyUp, '#26A69A');
  assert.equal(n.bg, 'rgba(0,0,0,.5)');
  assert.equal(n.wickUp, null);
  assert.equal(n.timezone, 'exchange');
  assert.equal(n.lastLineStyle, 'dashed');
  assert.equal(n.ohlc, true);
  assert.equal(n.ethBgColor, 'rgba(120,123,134,.08)');
  assert.deepEqual([null, 'default', -1, '2', 0].map((p) => S.normalize({ precision: p }).precision), [null, null, 0, 2, 0]);
  assert.deepEqual(S.normalize(null), S.DEFAULTS);
  assert.deepEqual(S.normalize([1, 2]), S.DEFAULTS);
});

test('overrides keep only what differs from the defaults, and round-trip', () => {
  assert.deepEqual(S.overrides(S.DEFAULTS), {});
  assert.deepEqual(S.overrides({}), {});
  assert.deepEqual(S.overrides({ ethBgColor: 'rgba(120, 123, 134, 0.08)', marginTop: 10 }), {});   // the defaults, spelled otherwise
  const o = S.overrides({ prevClose: true, bodyUp: '#26a69a', marginTop: 20, timezone: 'utc', precision: 0, junk: 1 });
  assert.deepEqual(o, { prevClose: true, bodyUp: '#26A69A', precision: 0, timezone: 'utc', marginTop: 20 });
  assert.deepEqual(S.normalize(o), S.normalize({ ...S.DEFAULTS, ...o }));
  assert.deepEqual(S.overrides(S.normalize(o)), o);
});

test('a colour never changed follows the theme; a changed one stays', () => {
  const light = S.resolve({}, LIGHT), dark = S.resolve({}, DARK);
  assert.deepEqual([light.bg, dark.bg], ['#FFFFFF', '#0F0F0F']);
  assert.deepEqual([light.bodyUp, light.bodyDown, light.borderDown, light.wickUp], ['#089981', '#F23645', '#F23645', '#089981']);
  assert.deepEqual([dark.vertGridColor, dark.horzGridColor, dark.scaleText, dark.scaleLines], ['#1C1C1C', '#1C1C1C', '#8C8C8C', '#2E2E2E']);
  assert.deepEqual([light.crossColor, dark.watermarkColor], ['#9598A1', 'rgba(219,219,219,.06)']);
  const mine = { bg: '#131722', bodyUp: '#2962FF' };
  assert.deepEqual([S.resolve(mine, LIGHT).bg, S.resolve(mine, DARK).bg], ['#131722', '#131722']);
  assert.deepEqual([S.resolve(mine, DARK).bodyUp, S.resolve(mine, DARK).bodyDown], ['#2962FF', '#F23645']);
  assert.equal(light.ethBgColor, 'rgba(120,123,134,.08)');
});

test('chartOptions: background, text, font, grid, crosshair, right offset, scale lines', () => {
  assert.deepEqual(S.chartOptions(S.resolve({}, LIGHT)), {
    layout: { background: { type: 'solid', color: '#FFFFFF' }, textColor: '#787B86', fontSize: 12 },
    grid: { vertLines: { visible: true, color: '#F0F3FA' }, horzLines: { visible: true, color: '#F0F3FA' } },
    crosshair: { vertLine: { color: '#9598A1', style: 2, width: 1 }, horzLine: { color: '#9598A1', style: 2, width: 1 } },
    timeScale: { rightOffset: 6, borderColor: '#E0E3EB' },
    rightPriceScale: { borderColor: '#E0E3EB' },
  });
  const o = S.chartOptions(S.resolve({ vertGrid: false, horzGridColor: '#FF0000', crossStyle: 'solid', crossWidth: 3,
    crossColor: '#2962FF', scaleFont: 14, rightOffset: 20, scaleLines: '#000000', scaleText: '#111111', bg: '#131722' }, LIGHT));
  assert.deepEqual(o.grid, { vertLines: { visible: false, color: '#F0F3FA' }, horzLines: { visible: true, color: '#FF0000' } });
  assert.deepEqual(o.crosshair.horzLine, { color: '#2962FF', style: 0, width: 3 });
  assert.deepEqual(o.layout, { background: { type: 'solid', color: '#131722' }, textColor: '#111111', fontSize: 14 });
  assert.deepEqual([o.timeScale.rightOffset, o.timeScale.borderColor, o.rightPriceScale.borderColor], [20, '#000000', '#000000']);
});

test('candleOptions: colours and visibility, precision from the tick or the setting, the last-price label and line', () => {
  assert.deepEqual(S.candleOptions(S.resolve({}, LIGHT), 0.25), {
    upColor: '#089981', downColor: '#F23645', borderVisible: true, borderUpColor: '#089981', borderDownColor: '#F23645',
    wickVisible: true, wickUpColor: '#089981', wickDownColor: '#F23645',
    priceFormat: { type: 'price', precision: 2, minMove: 0.25 },
    lastValueVisible: true, priceLineVisible: true, priceLineStyle: 1,
  });
  const off = S.candleOptions(S.resolve({ body: false, borders: false, wick: false, lastLabel: false, lastLine: false,
    lastLineStyle: 'solid' }, LIGHT), 0.25);
  assert.deepEqual([off.upColor, off.downColor, off.borderVisible, off.wickVisible], [S.CLEAR, S.CLEAR, false, false]);
  assert.deepEqual([off.lastValueVisible, off.priceLineVisible, off.priceLineStyle], [false, false, 0]);
  const pf = (over, tick) => S.candleOptions(S.resolve(over, LIGHT), tick).priceFormat;
  assert.deepEqual(pf({ precision: 0 }, 0.25), { type: 'price', precision: 0, minMove: 1 });
  assert.deepEqual(pf({ precision: 3 }, 0.25), { type: 'price', precision: 3, minMove: 0.001 });
  assert.deepEqual(pf({}, 0.1), { type: 'price', precision: 1, minMove: 0.1 });
  assert.deepEqual(pf({}, 0.015625), { type: 'price', precision: 6, minMove: 0.015625 });
});

test('scale margins and the legend flags', () => {
  assert.deepEqual(S.scaleMargins(S.resolve({}, LIGHT)), { top: 0.1, bottom: 0.15 });
  assert.deepEqual(S.scaleMargins(S.resolve({ marginTop: 0, marginBottom: 40 }, LIGHT)), { top: 0, bottom: 0.4 });
  assert.deepEqual(S.legendFlags(S.resolve({}, LIGHT)), { title: true, titleMode: 'both', ohlc: true, change: true,
    volume: true, indTitles: true, indArgs: true, indValues: true });
  assert.equal(S.legendFlags(S.resolve({ barChange: false }, LIGHT)).change, false);
});

test('colour bars based on previous close: up at or above the previous close (the first bar: its open)', () => {
  const R = S.resolve({ prevClose: true }, LIGHT);
  const bs = [{ o: 10, c: 9 }, { o: 8, c: 9.5 }, { o: 10, c: 9.5 }, { o: 9, c: 9.2 }];
  assert.deepEqual(S.barColorsByPrevClose(bs, R).map((x) => x.color), ['#F23645', '#089981', '#089981', '#F23645']);
  assert.deepEqual(S.barColor(bs[2], bs[1], R), { color: '#089981', borderColor: '#089981', wickColor: '#089981' });
  const hollow = S.resolve({ prevClose: true, body: false }, LIGHT);
  assert.deepEqual(S.barColor(bs[3], bs[2], hollow), { color: S.CLEAR, borderColor: '#F23645', wickColor: '#F23645' });
});

test('legend texts: an indicator\'s title and arguments, the symbol title', () => {
  assert.deepEqual(S.splitLabel('EMA 20', true), ['EMA', '20']);
  assert.deepEqual(S.splitLabel('Big prints ≥25', true), ['Big prints', '≥25']);
  assert.deepEqual(S.splitLabel('Session levels', false), ['Session levels', '']);
  assert.deepEqual(S.splitLabel('VWAP', true), ['VWAP', '']);
  const all = { indTitles: true, indArgs: true };
  assert.equal(S.legendLabel('VWAP RTH', true, all), 'VWAP RTH');
  assert.equal(S.legendLabel('VWAP RTH', true, { ...all, indTitles: false }), 'RTH');
  assert.equal(S.legendLabel('VWAP RTH', true, { ...all, indArgs: false }), 'VWAP');
  assert.equal(S.legendLabel('Session levels', false, { ...all, indArgs: false }), 'Session levels');
  assert.equal(S.titleText('NQ', 'E-mini Nasdaq-100', '1m', 'both'), 'NQ · E-mini Nasdaq-100 · 1m');
  assert.equal(S.titleText('NQ', 'E-mini Nasdaq-100', '1m', 'ticker'), 'NQ · 1m');
  assert.equal(S.titleText('NQ', 'E-mini Nasdaq-100', '1m', 'description'), 'E-mini Nasdaq-100 · 1m');
  assert.equal(S.titleText('ZZ', '', '5m', 'description'), 'ZZ · 5m');
});

const SUMMER = Date.UTC(2026, 8, 22, 13, 30);    // 09:30 EDT
const WINTER = Date.UTC(2026, 0, 15, 14, 30);    // 09:30 EST
const hm = (s) => new Date(s * 1000).toISOString().slice(11, 16);

test('time zones: the axis runs on the zone\'s wall clock', () => {
  assert.deepEqual(['exchange', 'utc', 'chicago', 'london'].map((z) => hm(S.wallSeconds(SUMMER, z))), ['09:30', '13:30', '08:30', '14:30']);
  assert.deepEqual(['exchange', 'utc', 'chicago', 'london'].map((z) => hm(S.wallSeconds(WINTER, z))), ['09:30', '14:30', '08:30', '14:30']);
  assert.equal(S.wallSeconds(SUMMER, 'exchange'), Date.UTC(2026, 8, 22, 9, 30) / 1000);
  assert.equal(S.wallSeconds(SUMMER, 'local'), Math.floor((SUMMER - new Date(SUMMER).getTimezoneOffset() * 60000) / 1000));
  assert.equal(S.wallSeconds(SUMMER + 1500, 'utc'), SUMMER / 1000 + 1);
  assert.equal(S.zoneOffsetMs('America/New_York', Date.UTC(2026, 2, 8, 6, 59)), -5 * 3600000);   // DST starts 07:00 UTC
  assert.equal(S.zoneOffsetMs('America/New_York', Date.UTC(2026, 2, 8, 7, 0)), -4 * 3600000);
  assert.deepEqual(S.TIMEZONES.map(([k]) => k), ['exchange', 'utc', 'chicago', 'london', 'local']);
});

test('regular hours are 09:30-16:00 ET: everything else is shaded', () => {
  const et = (h, m) => Date.UTC(2026, 8, 22, h, m) / 1000;
  assert.deepEqual([et(9, 29), et(9, 30), et(15, 59), et(16, 0), et(18, 0), et(0, 0)].map(S.outsideRth),
    [true, false, false, true, true, true]);
});

test('the countdown: to the bar\'s end, never past its session\'s close', () => {
  const et = (d, h, m = 0) => Date.UTC(2026, 8, d, h, m);
  assert.equal(S.barCloseEt({ t: et(22, 9, 30) / 1000, s: '2026-09-22' }, 60000, false), et(22, 9, 31));
  assert.equal(S.barCloseEt({ t: et(22, 14) / 1000, s: '2026-09-22' }, 4 * 3600000, false), et(22, 17));   // 4h bar: 17:00 close
  assert.equal(S.barCloseEt({ t: et(22, 14) / 1000, s: '2026-09-22' }, 4 * 3600000, true), et(22, 18));    // 24/7: 18:00
  assert.equal(S.barCloseEt({ t: et(21, 18) / 1000, s: '2026-09-22' }, 86400000, false), et(22, 17));      // the daily bar
  assert.equal(S.barCloseEt({ t: et(22, 9) / 1000 }, 3600000, false), et(22, 10));                          // no session: no cap
  assert.deepEqual([0, 59999, 60000, 3599999, 3600000, 3661000, -5].map(S.fmtCountdown),
    ['00:00', '00:59', '01:00', '59:59', '1:00:00', '1:01:01', '00:00']);
});

test('template names: 1-40 characters, no / \\ .. or control characters, not "."', () => {
  for (const bad of ['', 'x'.repeat(41), 'a/b', 'a\\b', '..', 'a..b', '.', 'tab\tx', 'del\x7f']) {
    assert.notEqual(S.templateNameError(bad), '', JSON.stringify(bad));
  }
  assert.equal(S.templateNameError('Dark · v1.2'), '');
  assert.equal(S.templateNameError('x'.repeat(40)), '');
});

test('the swatch palette: 10 hues x 6 shades, all distinct, with the chart\'s up and down', () => {
  assert.equal(S.PALETTE.length, 6);
  assert.ok(S.PALETTE.every((row) => row.length === 10 && row.every((c) => /^#[0-9A-F]{6}$/.test(c))));
  assert.equal(new Set(S.PALETTE.flat()).size, 60);
  assert.ok(S.PALETTE.flat().includes('#089981') && S.PALETTE.flat().includes('#F23645'));
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tests/js/settings.test.mjs`
Expected: FAIL with `Cannot find module '../../homebase/static/charts/settings.js'`.

- [ ] **Step 3: Implement** `homebase/static/charts/settings.js`:

```js
/* Homebase Charts — the chart Settings model (TradingView's Settings dialog,
   for the parts that apply to our charts). Pure: every field with its
   default; normalize (unknown keys dropped, numbers clamped, colours and
   choices checked); the overrides a layout or a template stores (only what
   differs from the defaults); theme resolution (a colour never changed is
   null and follows the theme); the mappings to Lightweight Charts options;
   and the small helpers settings need (time zones, the regular-hours test,
   the bar countdown, the swatch palette, template names). No browser
   globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const Cat = (typeof window !== 'undefined' && window.HBCatalog) || (typeof require === 'function' ? require('./catalog.js') : null);

const LINE_STYLE = { solid: 0, dotted: 1, dashed: 2 };   // Lightweight Charts' LineStyle numbers
const STYLES = Object.keys(LINE_STYLE);
const CLEAR = 'rgba(0,0,0,0)';
/* [value, the dialog's text, IANA zone (null: the browser's own)] */
const TIMEZONES = [['exchange', 'Exchange (New York)', 'America/New_York'], ['utc', 'UTC', 'UTC'],
  ['chicago', 'Chicago', 'America/Chicago'], ['london', 'London', 'Europe/London'], ['local', 'Local', null]];
const ZONE = Object.fromEntries(TIMEZONES.map(([k, , z]) => [k, z]));

const bool = (key, def) => ({ key, type: 'bool', def });
const color = (key, def = null) => ({ key, type: 'color', def });
const int = (key, def, min, max) => ({ key, type: 'int', def, min, max });
const choice = (key, def, choices) => ({ key, type: 'choice', def, choices });
const FIELDS = [
  // Symbol · CANDLES
  bool('prevClose', false),
  bool('body', true), color('bodyUp'), color('bodyDown'),
  bool('borders', true), color('borderUp'), color('borderDown'),
  bool('wick', true), color('wickUp'), color('wickDown'),
  // Symbol · DATA
  { key: 'precision', type: 'precision', def: null },   // null: Default (from the tick size); else 0-6 decimals
  choice('timezone', 'exchange', TIMEZONES.map(([k]) => k)),
  bool('ethBg', false), color('ethBgColor', 'rgba(120,123,134,.08)'),
  // Status line
  bool('title', true), choice('titleMode', 'both', ['ticker', 'description', 'both']),
  bool('ohlc', true), bool('barChange', true), bool('volume', true),
  bool('indTitles', true), bool('indArgs', true), bool('indValues', true),
  // Scales and lines · PRICE SCALE
  bool('scalePriceOnly', false), bool('lastLabel', true), bool('lastLine', true), choice('lastLineStyle', 'dotted', STYLES),
  bool('countdown', true), int('marginTop', 10, 0, 40), int('marginBottom', 15, 0, 40),
  // Scales and lines · TIME SCALE
  int('rightOffset', 6, 0, 100),
  // Canvas · CHART BASIC STYLES
  color('bg'), bool('vertGrid', true), color('vertGridColor'), bool('horzGrid', true), color('horzGridColor'),
  color('crossColor'), choice('crossStyle', 'dashed', STYLES), int('crossWidth', 1, 1, 4),
  bool('watermark', true), color('watermarkColor'),
  // Canvas · SCALES
  color('scaleText'), int('scaleFont', 12, 10, 16), color('scaleLines'),
];
const DEFAULTS = Object.freeze(Object.fromEntries(FIELDS.map((f) => [f.key, f.def])));
/* The colours that follow the theme while never changed, and the HBCell.palette() key each takes. */
const THEMED = { bodyUp: 'up', bodyDown: 'down', borderUp: 'up', borderDown: 'down', wickUp: 'up', wickDown: 'down',
  bg: 'bg', vertGridColor: 'grid', horzGridColor: 'grid', crossColor: 'cross', watermarkColor: 'watermark',
  scaleText: 'text2', scaleLines: 'border' };

/* ---- colours ---- */
const HEX = /^#([0-9a-f]{6})$/i;
const RGBA = /^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d*\.?\d+)\s*\)$/i;

/* '#RRGGBB' or 'rgba(r,g,b,a)' as {r, g, b, a}; null for anything else. */
function parseColor(s) {
  if (typeof s !== 'string') return null;
  const t = s.trim();
  let m = HEX.exec(t);
  if (m) { const n = parseInt(m[1], 16); return { r: n >> 16, g: (n >> 8) & 255, b: n & 255, a: 1 }; }
  m = RGBA.exec(t);
  if (!m) return null;
  const c = { r: +m[1], g: +m[2], b: +m[3], a: +m[4] };
  return c.r <= 255 && c.g <= 255 && c.b <= 255 && c.a <= 1 ? c : null;
}

/* A colour's one spelling: '#RRGGBB' when opaque, else 'rgba(r,g,b,.a)' (alpha to 3 places, no leading 0). */
function fmtColor(c) {
  const a = Math.round(Math.min(1, Math.max(0, c.a)) * 1000) / 1000;
  if (a === 1) return '#' + [c.r, c.g, c.b].map((x) => x.toString(16).padStart(2, '0')).join('').toUpperCase();
  return `rgba(${c.r},${c.g},${c.b},${String(a).replace(/^0\./, '.')})`;
}
const canon = (s) => { const c = parseColor(s); return c ? fmtColor(c) : null; };
/* The swatch popover's pieces: a colour's #RRGGBB, its opacity (0-1), and the same colour at another opacity. */
function hexOf(s) { const c = parseColor(s); return c ? fmtColor({ ...c, a: 1 }) : null; }
function alphaOf(s) { const c = parseColor(s); return c ? c.a : 1; }
function withAlpha(s, a) { const c = parseColor(s); return c ? fmtColor({ ...c, a }) : null; }

/* ---- the model ---- */
const num = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);

/* Every field, each valid: unknown keys dropped, numbers rounded and clamped, colours checked (and spelled one
   way), choices checked; anything missing or invalid takes its default. */
function normalize(obj) {
  const src = obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {}, out = {};
  for (const f of FIELDS) {
    const v = src[f.key];
    let x = f.def;
    if (f.type === 'bool') { if (typeof v === 'boolean') x = v; }
    else if (f.type === 'choice') { if (f.choices.includes(v)) x = v; }
    else if (f.type === 'color') { const c = canon(v); if (c) x = c; }
    else if (v !== null) {
      const n = num(v);
      if (Number.isFinite(n)) {
        x = f.type === 'precision' ? Math.min(6, Math.max(0, Math.round(n))) : Math.min(f.max, Math.max(f.min, Math.round(n)));
      }
    }
    out[f.key] = x;
  }
  return out;
}

/* What a layout or a template stores: only the values that differ from the defaults. */
function overrides(full) {
  const n = normalize(full), out = {};
  for (const f of FIELDS) if (n[f.key] !== f.def) out[f.key] = n[f.key];
  return out;
}

/* Concrete values for a theme: every colour never changed takes the palette's (HBCell.palette()). */
function resolve(over, palette) {
  const n = normalize(over);
  for (const [k, pk] of Object.entries(THEMED)) if (n[k] == null) n[k] = palette[pk];
  return n;
}

/* ---- mappings to Lightweight Charts ---- */
/* Chart-wide options, merged into createChart / applyOptions. */
function chartOptions(r) {
  const cross = () => ({ color: r.crossColor, style: LINE_STYLE[r.crossStyle], width: r.crossWidth });
  return {
    layout: { background: { type: 'solid', color: r.bg }, textColor: r.scaleText, fontSize: r.scaleFont },
    grid: { vertLines: { visible: r.vertGrid, color: r.vertGridColor }, horzLines: { visible: r.horzGrid, color: r.horzGridColor } },
    crosshair: { vertLine: cross(), horzLine: cross() },
    timeScale: { rightOffset: r.rightOffset, borderColor: r.scaleLines },
    rightPriceScale: { borderColor: r.scaleLines },
  };
}

/* The candle series' options. Precision null: the tick size's decimals. */
function candleOptions(r, tick) {
  const p = r.precision;
  return {
    upColor: r.body ? r.bodyUp : CLEAR, downColor: r.body ? r.bodyDown : CLEAR,
    borderVisible: r.borders, borderUpColor: r.borderUp, borderDownColor: r.borderDown,
    wickVisible: r.wick, wickUpColor: r.wickUp, wickDownColor: r.wickDown,
    priceFormat: { type: 'price', precision: p == null ? Cat.decimals(tick) : p,
      minMove: p == null ? tick : Number((10 ** -p).toFixed(p)) },
    lastValueVisible: r.lastLabel, priceLineVisible: r.lastLine, priceLineStyle: LINE_STYLE[r.lastLineStyle],
  };
}

function scaleMargins(r) { return { top: r.marginTop / 100, bottom: r.marginBottom / 100 }; }

function legendFlags(r) {
  return { title: r.title, titleMode: r.titleMode, ohlc: r.ohlc, change: r.barChange, volume: r.volume,
    indTitles: r.indTitles, indArgs: r.indArgs, indValues: r.indValues };
}

/* One candle's colours with "Colour bars based on previous close": up when its close is at or above the
   previous bar's close (the first bar: its own open). */
function barColor(bar, prev, r) {
  const up = bar.c >= (prev ? prev.c : bar.o);
  return { color: r.body ? (up ? r.bodyUp : r.bodyDown) : CLEAR, borderColor: up ? r.borderUp : r.borderDown,
    wickColor: up ? r.wickUp : r.wickDown };
}
function barColorsByPrevClose(bars, r) { return bars.map((b, i) => barColor(b, i ? bars[i - 1] : null, r)); }

/* ---- legend texts ---- */
/* An indicator's legend label cut into its title and its arguments ("EMA 20" -> ["EMA", "20"]); an indicator
   without params has no arguments. */
function splitLabel(label, hasParams) {
  const i = hasParams ? label.lastIndexOf(' ') : -1;
  return i > 0 ? [label.slice(0, i), label.slice(i + 1)] : [label, ''];
}
function legendLabel(label, hasParams, flags) {
  const [t, a] = splitLabel(label, hasParams);
  return [flags.indTitles ? t : '', flags.indArgs ? a : ''].filter(Boolean).join(' ');
}
/* The legend's title row for the Status line's "Symbol title" choice. */
function titleText(root, name, interval, mode) {
  const parts = mode === 'ticker' ? [root, interval] : mode === 'description' ? [name || root, interval] : [root, name, interval];
  return parts.filter(Boolean).join(' · ');
}

/* ---- time ---- */
const FMT = new Map(), OFF = new Map();
/* A zone's UTC offset in ms at an instant (IANA name), cached per hour (these zones change offset on the hour). */
function zoneOffsetMs(zone, ms) {
  if (zone === 'UTC') return 0;
  const hour = Math.floor(ms / 3600000), key = zone + '|' + hour;
  let off = OFF.get(key);
  if (off === undefined) {
    let f = FMT.get(zone);
    if (!f) {
      f = new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric',
        day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric' });
      FMT.set(zone, f);
    }
    const p = {};
    for (const x of f.formatToParts(new Date(hour * 3600000))) p[x.type] = x.value;
    off = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second) - hour * 3600000;
    OFF.set(key, off);
  }
  return off;
}
/* An instant as wall-clock seconds in a chart time zone (a TIMEZONES value): the time axis runs on these. */
function wallSeconds(ms, tz) {
  const off = tz === 'local' ? -new Date(ms).getTimezoneOffset() * 60000 : zoneOffsetMs(ZONE[tz] || ZONE.exchange, ms);
  return Math.floor((ms + off) / 1000);
}
/* Is a bar starting at this ET wall-clock second outside regular hours (09:30-16:00 ET)? */
function outsideRth(etWallS) {
  const m = Math.floor((((etWallS % 86400) + 86400) % 86400) / 60);
  return m < 570 || m >= 960;
}
/* When a bar closes, as ET wall-clock ms: its start + its length, but never after its session's close (17:00
   ET; 18:00 for a 24/7 root), where the server closes a session's last bar. bar = {t: ET wall s, s: session}. */
function barCloseEt(bar, barMs, alwaysOpen) {
  const end = bar.t * 1000 + barMs, m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(bar.s || '');
  return m ? Math.min(end, Date.UTC(+m[1], +m[2] - 1, +m[3], alwaysOpen ? 18 : 17)) : end;
}
/* "04:59" under an hour, "1:04:59" from an hour. */
function fmtCountdown(ms) {
  const s = Math.max(0, Math.floor(ms / 1000)), h = Math.floor(s / 3600), p2 = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${p2(Math.floor((s % 3600) / 60))}:${p2(s % 60)}` : `${p2(Math.floor(s / 60))}:${p2(s % 60)}`;
}

/* ---- templates ---- */
/* Why a template name is refused ('' when fine): 1-40 characters with no / \ .. or control characters (the
   server's rule), and not "." (the browser would resolve /api/templates/. as a path step). */
function templateNameError(name) {
  if (typeof name !== 'string' || name.length < 1 || name.length > 40) return 'A name has 1 to 40 characters';
  if (name === '.' || /[/\\]|\.\.|[\u0000-\u001f\u007f]/.test(name)) return 'A name has no / \\ .. or control characters';
  return '';
}

/* The swatch popover's palette: 10 hue columns (grey, red, orange, yellow, green, teal, cyan, blue, purple,
   pink) x 6 rows, light to dark, TradingView-like. */
const PALETTE = [
  ['#FFFFFF', '#FCCBCD', '#FFE0B2', '#FFF9C4', '#C8E6C9', '#ACE5DC', '#B2EBF2', '#BBD9FB', '#D1C4E9', '#F8BBD0'],
  ['#D6D6D6', '#FAA1A4', '#FFCC80', '#FFF59D', '#A5D6A7', '#70CCBD', '#80DEEA', '#90BFF9', '#B39DDB', '#F48FB1'],
  ['#A8A8A8', '#F77C80', '#FFB74D', '#FFF176', '#81C784', '#42BDA8', '#4DD0E1', '#5B9CF6', '#9575CD', '#F06292'],
  ['#757575', '#F23645', '#FF9800', '#FFEB3B', '#4CAF50', '#089981', '#00BCD4', '#2962FF', '#673AB7', '#E91E63'],
  ['#434343', '#B22833', '#F57C00', '#FBC02D', '#388E3C', '#056656', '#0097A7', '#1848CC', '#512DA8', '#C2185B'],
  ['#000000', '#801922', '#E65100', '#F57F17', '#1B5E20', '#00332A', '#006064', '#0C3299', '#311B92', '#880E4F'],
];

const api = { FIELDS, DEFAULTS, THEMED, LINE_STYLE, TIMEZONES, PALETTE, CLEAR, parseColor, fmtColor, hexOf, alphaOf,
  withAlpha, normalize, overrides, resolve, chartOptions, candleOptions, scaleMargins, legendFlags, barColor,
  barColorsByPrevClose, splitLabel, legendLabel, titleText, zoneOffsetMs, wallSeconds, outsideRth, barCloseEt,
  fmtCountdown, templateNameError };
if (typeof window !== 'undefined') window.HBSettings = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 4: Run the tests**

Run: `node --test tests/js/settings.test.mjs`, then `node --test tests/js/*.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homebase/static/charts/settings.js tests/js/settings.test.mjs
git commit -m "feat(charts): HBSettings — the chart-settings model: defaults, normalize/overrides/resolve, theme-following colours, Lightweight Charts mappings, time zones, countdown

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Chart Settings — dialog shell, Symbol and Canvas tabs, settings applied to the chart, layouts carry them

**Files:**
- Create: `homebase/static/charts/settings-dialog.js`
- Modify: `homebase/static/charts/cell.js`
- Modify: `homebase/static/charts/app.js`
- Modify: `homebase/static/charts.html`, `homebase/static/charts/charts.css`, `homebase/static/charts/icons.js`

**Interfaces:**
- Consumes:
  - Task 5's `HBSettings`: `normalize`, `overrides`, `resolve`, `chartOptions`, `candleOptions`, `scaleMargins`, `barColor`, `wallSeconds`, `TIMEZONES`, `PALETTE`, `hexOf`, `alphaOf`, `withAlpha`, `CLEAR`.
  - Task 2's `Cell.magnetXhair` and `openMenu(anchor, cls, {right})`.
  - Task 4's palette keys and `Cell.pv`.
  - Existing: `openDialog`, `closeDialog`, `trapTab`, `onKey`, `menuEl`, `menuAnchor`, `closeMenu`, `saveLast`, `loadLast`, `loadLayout`, `putLayout`, `save`, `layoutMenu`, `renderToolbar`, `Cell.cfg`, `restyle`, `build`, `viewNow`, `setView`, `append`, `replaceLast`, `legendRows`, `legend`.
- Produces:
  - `Cell.R`: the resolved settings, set in the constructor and in every `makeChart`.
  - `Cell.settings() -> overrides` (a copy); `Cell.setSettings(overrides)`, which stores it in `cfg.settings` (deleted when empty) and applies it in place, without saving the layout.
  - `Cell.applySettings()`, `Cell.candleOpts()`, `Cell.candle(b, prev)`, `Cell.candleData()`, `Cell.resetCandles()`, `Cell.wall(b)`, `Cell.retime()`, `Cell.dtick()`, `Cell.wmLine()`.
  - Fields `Cell.fpHide` and `Cell.wm`.
  - `HBSettingsDialog.mount(box, host) -> {revert()}` and `HBSettingsDialog.TABS`, with `host = {cell, cells(), toggleMenu(anchor, cls, fill(menuEl)), closeMenu(), placeMenu(), commit(changed), cancel()}`. Task 7 adds `host.templates` (the templates API client); Task 8 adds `host.countries()`.
  - Page:
    - `openMenu(anchor, cls, {right, root})`: `root` = the element the menu is appended to; a dialog's box for in-dialog menus.
    - `placeMenu()` flips a menu above its anchor when it does not fit below.
    - `dlg.onClose` (called by `closeDialog`, which also closes an open menu).
    - `readLayout(v)`, `layout.dirty`, `chartSettings()`, and the `#tbSettings` toolbar gear.

- [ ] **Step 1: `cell.js`, settings in the chart.**

At the top, after `const C = window.HBCatalog;`, add:

```js
const S = window.HBSettings;
const CANDLE_KEYS = ['prevClose', 'body', 'bodyUp', 'bodyDown', 'borders', 'borderUp', 'borderDown', 'wick', 'wickUp', 'wickDown'];
```

In the header comment, add: "Its settings (HBSettings: candle colours, precision, time zone, scales, canvas…) live in `cfg.settings` as overrides of the defaults and are applied in place."

In the constructor's field list (before `slot.className = 'panel'`), add:

```js
    this.R = S.resolve(cfg.settings || {}, palette());   // the chart's settings, concrete for the theme
    this.fpHide = false;   // the footprint is readable: candle bodies and borders step aside
    this.wm = null;        // the watermark (its colour and visibility follow the settings)
```

Add these methods after `setMagnetCrosshair`:

```js
  /* The chart's settings as the layout stores them: what differs from the defaults (a copy). */
  settings() { return { ...(this.cfg.settings || {}) }; }

  /* New settings (the dialog's live preview, Ok, Cancel, Apply to all): kept in the chart's config (none when
     all are defaults) and applied in place. Saving the layout is the page's job (on Ok). */
  setSettings(over) {
    const o = S.overrides(over);
    if (Object.keys(o).length) this.cfg.settings = o; else delete this.cfg.settings;
    this.applySettings();
  }

  /* Apply cfg.settings to the chart in place: the dialog previews every change live, and rebuilding the chart
     would flash. A new time zone re-times every bar and rebuilds. */
  applySettings() {
    const was = this.R, R = this.R = S.resolve(this.cfg.settings || {}, this.P || palette());
    this.title();
    if (!this.chart) return;
    if (was.timezone !== R.timezone) { this.retime(); this.restyle(); return; }
    const o = S.chartOptions(R);
    this.chart.applyOptions({ ...o, rightPriceScale: { ...o.rightPriceScale, scaleMargins: S.scaleMargins(R) } });
    this.candles.applyOptions(this.candleOpts());
    this.wm.applyOptions({ visible: R.watermark, lines: [this.wmLine()] });
    if ((R.prevClose || was.prevClose) && CANDLE_KEYS.some((k) => R[k] !== was[k])) this.resetCandles();
    this.legendRows();
    this.legend(this.hover);
  }

  /* The candle series' options for the settings; while the footprint is readable, bodies and borders step
     aside (its numbers sit where the bodies are). */
  candleOpts() {
    const o = S.candleOptions(this.R, this.tick);
    return this.fpHide ? { ...o, upColor: S.CLEAR, downColor: S.CLEAR, borderVisible: false } : o;
  }

  /* The watermark line: "NQ, 1m" in the settings' colour. */
  wmLine() {
    const s = this.shown || this.cfg;
    return { text: `${s.root}, ${C.specLabel(s.spec)}`, color: this.R.watermarkColor, fontSize: 48, fontFamily: FONT };
  }

  /* The price step the legend shows: the tick size, or the Precision setting's 10^-n. */
  dtick() { return this.R.precision == null ? this.tick : 10 ** -this.R.precision; }

  /* A bar's axis time: its start on the chart time zone's wall clock (by default ET: the server's own t). */
  wall(b) { return this.R.timezone === 'exchange' ? b.t : S.wallSeconds(b.ms, this.R.timezone); }

  /* The time zone changed: every bar's axis time again. */
  retime() { const bars = this.bars; this.bars = []; this.realT = new Map(); for (const b of bars) this.append(b); }
```

Replace `makeChart()` with the version below. It keeps Task 2's crosshair mode and every existing layer:

```js
  makeChart() {
    this.teardown();
    const P = this.P = palette(), sub = this.isTime() && this.barMs() < 60000;
    const R = this.R = S.resolve(this.cfg.settings || {}, P), o = S.chartOptions(R);
    this.fpHide = false;
    this.chart = LW.createChart(this.box, {
      autoSize: true,
      layout: { ...o.layout, fontFamily: FONT,
        attributionLogo: false,   // the credit lives once in the bottom bar
        panes: { separatorColor: P.border, separatorHoverColor: P.accentSoft, enableResize: true } },
      grid: o.grid,
      rightPriceScale: { ...o.rightPriceScale, scaleMargins: S.scaleMargins(R) },
      timeScale: { ...o.timeScale, timeVisible: true, secondsVisible: sub,
        tickMarkFormatter: (t, type) => tickLabel(this.real(t), type) },
      localization: { timeFormatter: (t) => this.fullTime(t) },
      crosshair: { mode: this.magnetXhair ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal,
        vertLine: { ...o.crosshair.vertLine, labelBackgroundColor: P.crossLabel },
        horzLine: { ...o.crosshair.horzLine, labelBackgroundColor: P.crossLabel } },
    });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, this.candleOpts());
    this.markers = LW.createSeriesMarkers(this.candles, []);
    this.wm = LW.createTextWatermark(this.chart.panes()[0], { visible: R.watermark, horzAlign: 'center',
      vertAlign: 'center', lines: [this.wmLine()] });
    this.fp = new Footprint(P); this.prof = new Profile(P); this.gaps = new Gaps(P);
    const fp = this.fp;   // pin the instance this callback belongs to
    fp.onReadableChange = (on) => {   // fired async from Footprint.updateAllViews(), after layout
      if (this.fp !== fp || !this.chart) return;
      this.fpHide = on;
      this.candles.applyOptions(this.candleOpts());
      if (this.R.prevClose) this.resetCandles();   // per-bar colours ride in the data
    };
    for (const l of [this.gaps, this.prof, this.fp]) this.candles.attachPrimitive(l);
    this.lines = []; this.levelLines = {}; this.colorOf = {}; this.hover = null;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.syncFootprint());
    this.chart.subscribeCrosshairMove((p) => {
      this.hover = p && p.logical != null ? Math.round(p.logical) : null;
      this.legend(this.hover);
    });
  }
```

In `teardown()`, add `this.wm` to the list of fields set to `null`.

In `build(view)`, replace `this.candles.setData(this.bars.map((b) => this.candle(b)));` with `this.candles.setData(this.candleData());`.

Replace `candle(b)` with:

```js
  /* One candle; with "Colour bars based on previous close" it carries its own colours (up/down against the
     previous close), hidden like the series' while the footprint is readable. */
  candle(b, prev) {
    const c = { time: b.tt, open: b.o, high: b.h, low: b.l, close: b.c };
    if (!this.R.prevClose) return c;
    const k = S.barColor(b, prev, this.R);
    return { ...c, color: this.fpHide ? S.CLEAR : k.color, borderColor: k.borderColor, wickColor: k.wickColor };
  }
  candleData() { return this.bars.map((b, i) => this.candle(b, i ? this.bars[i - 1] : null)); }
  /* Every candle again (per-bar colours changed), the view kept where it is. */
  resetCandles() {
    const v = this.viewNow();
    this.candles.setData(this.candleData());
    if (v) this.setView(v);
  }
```

In `onUpdate`, replace the loop `for (const b of touched) { this.candles.update(this.candle(b)); … }` with:

```js
    for (const b of touched) {
      const i = this.bars.lastIndexOf(b);
      this.candles.update(this.candle(b, i > 0 ? this.bars[i - 1] : null));
      for (const l of this.lines) l.s.update(this.point(l, b));
    }
```

In `append(b)` and `replaceLast(b)`, bars are placed on the zone's wall clock:

```js
  append(b) {
    const last = this.bars[this.bars.length - 1];
    b.tt = this.isTime() ? this.wall(b) : FAKE0 + this.bars.length * 60;
    if (last && b.tt <= last.tt) b.tt = last.tt + 1;
    if (!this.isTime()) this.realT.set(b.tt, this.wall(b));
    this.bars.push(b);
  }

  replaceLast(b) {
    const i = this.bars.length - 1;
    b.tt = this.bars[i].tt;
    if (!this.isTime()) this.realT.set(b.tt, this.wall(b));
    this.bars[i] = b;
  }
```

`fullTime` and `tickLabel` already format `real(tt)`, which is now the chosen zone's wall clock. Gaps (`b.t`), drawings and positions (`b.ms`) are unaffected.

Replace the colour/format part of `legend(i)`. The OHLC values take the candle colours and the previous-close rule; all values use the display precision:

```js
  legend(i) {
    const n = this.bars.length;
    if (!n || !this.P) { this.lg.ohlc.replaceChildren(); return; }
    const k = i == null ? n - 1 : Math.max(0, Math.min(i, n - 1)), b = this.bars[k], prev = k > 0 ? this.bars[k - 1] : null;
    const P = this.P, R = this.R, dt = this.dtick();
    const up = b.c >= (R.prevClose && prev ? prev.c : b.o), col = up ? R.bodyUp : R.bodyDown, ch = C.change(b, prev, dt);
    this.lg.ohlc.replaceChildren(
      ...[['O', b.o], ['H', b.h], ['L', b.l], ['C', b.c]].map(([key, v]) => kv(key, C.fmtPrice(v, dt), col)),
      val(ch.text, ch.up ? R.bodyUp : R.bodyDown),
      kv('Vol', C.fmtCompact(b.v), col),
      kv('Δ', C.fmtSigned(b.d), b.d >= 0 ? P.up : P.down));
    const colors = { text: P.text, up: P.up, down: P.down, vwap: P.vwap, cum: P.cum };
    for (const r of this.rows) {
      const vs = C.legendValues(r.inst, b, { ...colors, line: this.colorOf[r.inst.uid] || P.accent }, dt);
      r.vals.replaceChildren(...vs.map((x) => val(x.text, x.color)));
    }
  }
```

- [ ] **Step 2: `settings-dialog.js`** (new file, browser only):

```js
/* Homebase Charts — the chart Settings dialog (TradingView's Settings, for what applies to our charts): a
   column of tabs, rows of controls, the swatch popover and a footer. Every change previews live on the
   selected chart; Cancel, ×, Esc or a backdrop click put every chart back as it was when the dialog opened;
   Ok keeps the changes. Browser only: the model is HBSettings (settings.js); the page (app.js) owns the
   dialog frame and the menus and hands them over as `host`:
     {cell, cells(), toggleMenu(anchor, cls, fill(menuEl)), closeMenu(), placeMenu(), commit(changed), cancel()} */
(() => {
'use strict';
const S = window.HBSettings, I = window.HBIcons;
const LINE = [['solid', 'Solid'], ['dotted', 'Dotted'], ['dashed', 'Dashed']];
const PRECISION = [['', 'Default'], ...[0, 1, 2, 3, 4, 5, 6].map((n) => [String(n), n ? (10 ** -n).toFixed(n) : '1'])];
const FONT_SIZES = [10, 11, 12, 13, 14, 15, 16].map((n) => [String(n), String(n)]);
const asNumber = (v) => Number(v);
const asPrecision = (v) => (v === '' ? null : Number(v));

/* The tabs, in TradingView's order. A row: {label, check?: key (a checkbox before the label), colors?: [[key,
   what]] (a swatch each), select?: {key, choices: [[value, text]], parse?}, number?: {key, min, max, unit?}}.
   Task 7 inserts Status line and Scales and lines, and the hours-background row; Task 8 adds Events. */
const TABS = [
  { id: 'symbol', label: 'Symbol', icon: 'candles', sections: [
    ['CANDLES', [
      { label: 'Colour bars based on previous close', check: 'prevClose' },
      { label: 'Body', check: 'body', colors: [['bodyUp', 'up'], ['bodyDown', 'down']] },
      { label: 'Borders', check: 'borders', colors: [['borderUp', 'up'], ['borderDown', 'down']] },
      { label: 'Wick', check: 'wick', colors: [['wickUp', 'up'], ['wickDown', 'down']] },
    ]],
    ['DATA', [
      { label: 'Precision', select: { key: 'precision', choices: PRECISION, parse: asPrecision } },
      { label: 'Timezone', select: { key: 'timezone', choices: S.TIMEZONES.map(([k, text]) => [k, text]) } },
    ]],
  ] },
  { id: 'canvas', label: 'Canvas', icon: 'paintbrush', sections: [
    ['CHART BASIC STYLES', [
      { label: 'Background', colors: [['bg', '']] },
      { label: 'Vert grid lines', check: 'vertGrid', colors: [['vertGridColor', '']] },
      { label: 'Horz grid lines', check: 'horzGrid', colors: [['horzGridColor', '']] },
      { label: 'Crosshair', colors: [['crossColor', '']], select: { key: 'crossStyle', choices: LINE },
        number: { key: 'crossWidth', min: 1, max: 4 } },
      { label: 'Watermark', check: 'watermark', colors: [['watermarkColor', '']] },
    ]],
    ['SCALES', [
      { label: 'Text colour', colors: [['scaleText', '']] },
      { label: 'Text size', select: { key: 'scaleFont', choices: FONT_SIZES, parse: asNumber } },
      { label: 'Lines colour', colors: [['scaleLines', '']] },
    ]],
  ] },
];

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function button(cls, text) { const b = mk('button', cls, text); b.type = 'button'; return b; }

function mount(box, host) {
  const cell = host.cell;
  const atOpen = new Map(host.cells().map((c) => [c, c.settings()]));   // Cancel puts every chart back
  let work = S.normalize(cell.settings()), tab = 0, done = false, raf = 0;
  const swatches = new Map();   // colour key -> the <i> inside its swatch button

  const body = mk('div', 'set-body'), tabs = mk('div', 'set-tabs'), pane = mk('div', 'set-pane'), foot = mk('div', 'set-foot');
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-orientation', 'vertical');
  pane.setAttribute('role', 'tabpanel');
  body.append(tabs, pane);
  box.append(body, foot);
  pane.addEventListener('scroll', () => host.closeMenu());   // a popover never floats away from its swatch

  /* Live preview on the selected chart, at most once a frame (a dragged opacity slider fires per pixel). */
  function preview() {
    if (raf || done) return;
    raf = requestAnimationFrame(() => { raf = 0; if (!done) cell.setSettings(S.overrides(work)); });
  }
  function flush() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }
  function set(key, v) { work = S.normalize({ ...work, [key]: v }); preview(); paint(); }
  /* What each colour field shows: its value, or the theme's colour while it follows the theme. */
  const shown = () => S.resolve(S.overrides(work), cell.P || {});
  function paint() { const r = shown(); for (const [k, i] of swatches) i.style.background = r[k] || ''; }

  function renderTabs() {
    const had = tabs.contains(document.activeElement);
    tabs.replaceChildren(...TABS.map((t, i) => {
      const b = button('set-tab' + (i === tab ? ' active' : '')), ic = mk('span', 'icw');
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(i === tab));
      ic.innerHTML = I[t.icon] || '';   // our own static SVG strings
      b.append(ic, mk('span', '', t.label));
      b.onclick = () => { if (tab !== i) { tab = i; renderTabs(); renderPane(); } };
      return b;
    }));
    if (had) tabs.querySelector('.active').focus();
  }

  function renderPane() {
    host.closeMenu();
    swatches.clear();
    pane.replaceChildren(...TABS[tab].sections.flatMap(([cap, rows]) => [mk('div', 'set-cap', cap), ...rows.map(row)]));
    pane.scrollTop = 0;
    paint();
  }

  function row(r) {
    const el = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl');
    if (r.check) {
      const cb = mk('input');
      cb.type = 'checkbox';
      cb.checked = !!work[r.check];
      cb.onchange = () => set(r.check, cb.checked);
      name.append(cb);
    }
    name.append(mk('span', '', r.label));
    for (const [key, what] of r.colors || []) {
      const b = button('swatch'), i = mk('i'), tip = `${r.label}${what ? ` ${what}` : ''} colour`;
      b.title = tip;
      b.setAttribute('aria-label', tip);
      b.setAttribute('aria-haspopup', 'dialog');
      b.append(i);
      swatches.set(key, i);
      b.onclick = () => swatchMenu(b, key);
      ctl.append(b);
    }
    if (r.select) {
      const { key, choices, parse } = r.select, s = mk('select', 'set-select');
      s.setAttribute('aria-label', r.label);
      for (const [v, text] of choices) { const o = mk('option', '', text); o.value = v; s.append(o); }
      s.value = work[key] == null ? '' : String(work[key]);
      s.onchange = () => set(key, parse ? parse(s.value) : s.value);
      ctl.append(s);
    }
    if (r.number) {
      const { key, min, max, unit } = r.number, n = mk('input', 'set-num');
      n.type = 'number'; n.min = String(min); n.max = String(max); n.step = '1';
      n.value = String(work[key]);
      n.setAttribute('aria-label', r.label);
      n.oninput = () => { if (n.value !== '') set(key, Number(n.value)); };
      n.onchange = () => { n.value = String(work[key]); };   // shows the clamped value
      ctl.append(n);
      if (unit) ctl.append(mk('span', 'set-unit', unit));
    }
    el.append(name, ctl);
    return el;
  }

  /* The swatch popover (menu styling): the palette, an opacity slider, a #RRGGBB field and "Default" (back to
     following the theme / the default). Picking a palette colour keeps the opacity. */
  function swatchMenu(anchor, key) {
    host.toggleMenu(anchor, 'menu-swatch', (m) => {
      const cur = () => shown()[key];
      const grid = mk('div', 'sw-grid'), err = mk('div', 'sw-err'), picks = [];
      err.hidden = true;
      err.setAttribute('role', 'alert');
      for (const hex of S.PALETTE.flat()) {
        const b = button('sw-cell');
        b.style.background = hex;
        b.title = hex;
        b.setAttribute('aria-label', hex);
        b.onclick = () => { set(key, S.withAlpha(hex, S.alphaOf(cur()))); sync(); };
        picks.push([hex, b]);
        grid.append(b);
      }
      const opRow = mk('div', 'sw-row'), op = mk('input'), pct = mk('span', 'sw-pct');
      op.type = 'range'; op.min = '0'; op.max = '100'; op.step = '1';
      op.setAttribute('aria-label', 'Opacity');
      op.oninput = () => { set(key, S.withAlpha(S.hexOf(cur()), Number(op.value) / 100)); sync(); };
      opRow.append(mk('span', '', 'Opacity'), op, pct);
      const hexRow = mk('div', 'sw-row'), hex = mk('input', 'sw-hex'), def = button('sw-default', 'Default');
      hex.type = 'text'; hex.maxLength = 7; hex.spellcheck = false;
      hex.setAttribute('aria-label', 'Hex colour');
      const takeHex = () => {
        const v = hex.value.trim();
        if (!/^#[0-9A-Fa-f]{6}$/.test(v)) { err.textContent = 'Use #RRGGBB'; err.hidden = false; return; }
        err.hidden = true;
        set(key, S.withAlpha(v, S.alphaOf(cur())));
        sync();
      };
      hex.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); takeHex(); } };
      hex.onchange = takeHex;
      def.onclick = () => { err.hidden = true; set(key, null); sync(); };
      hexRow.append(hex, def);
      m.append(grid, opRow, hexRow, err);
      function sync() {   // the popover shows the field's colour now
        const c = cur(), h = S.hexOf(c), a = Math.round(S.alphaOf(c) * 100);
        for (const [x, b] of picks) b.classList.toggle('on', x === h);
        op.value = String(a);
        pct.textContent = `${a}%`;
        if (document.activeElement !== hex) hex.value = h || '';
      }
      sync();
      (m.querySelector('.sw-cell.on') || picks[0][1]).focus();
    });
  }

  /* ---- footer ---- */
  const grow = mk('span', 'grow'), cancel = button('btn btn-ghost', 'Cancel'), ok = button('btn btn-solid', 'Ok');
  cancel.onclick = () => host.cancel();
  ok.onclick = () => {
    flush();
    cell.setSettings(S.overrides(work));
    done = true;
    host.commit(host.cells().some((c) => JSON.stringify(c.settings()) !== JSON.stringify(atOpen.get(c) || {})));
  };
  foot.append(grow, cancel, ok);

  renderTabs();
  renderPane();
  tabs.querySelector('.active').focus();

  return {
    /* Cancel, ×, Esc, a backdrop click: every chart back to its settings at open. After Ok: nothing. */
    revert() {
      if (done) return;
      done = true;
      flush();
      const now = host.cells();
      for (const [c, s] of atOpen) if (now.includes(c)) c.setSettings(s);
    },
  };
}

window.HBSettingsDialog = { mount, TABS };
})();
```

- [ ] **Step 3: `app.js`, the frame, menus inside the dialog, layouts.**

At the top: `const C = window.HBCatalog, I = window.HBIcons, S = window.HBSettings, { Cell } = window.HBCell;`.

`openMenu` gains a `root` option. Its first lines become:

```js
function openMenu(anchor, cls, { right = false, root = null } = {}) {
  closeMenu();
  const m = mk('div', 'menu' + (cls ? ' ' + cls : ''));
  m.setAttribute('role', 'menu');
  (root || $('#menuRoot')).appendChild(m);
```

The rest is unchanged. In `placeMenu`, replace the last three lines (the non-`menuRight` branch) with:

```js
  const r = menuAnchor.getBoundingClientRect(), below = r.bottom + 4;
  menuEl.style.left = Math.max(4, Math.min(r.left, window.innerWidth - w - 4)) + 'px';
  // no room below (a dialog footer's menu, a swatch near the bottom): above the anchor instead
  menuEl.style.top = (below + h > window.innerHeight - 4 && r.top - 4 - h >= 4 ? r.top - 4 - h : below) + 'px';
```

Replace `closeDialog` with:

```js
function closeDialog() {
  if (!dlg) return;
  closeMenu();   // a menu or swatch popover open inside the dialog goes with it
  const { back, focus, onClose } = dlg;
  dlg = null;
  back.remove();
  if (onClose) onClose();   // the Settings dialog puts every chart back unless Ok was pressed
  if (focus && typeof focus.focus === 'function' && document.contains(focus)) focus.focus();
}
```

In `trapTab`, change the selector `'button, input'` to `'button, input, select'`. In `onKey`, change the dialog branch to:

```js
  if (dlg) {
    if (e.key === 'Escape') { e.preventDefault(); if (menuEl) closeMenu(); else closeDialog(); }
    else if (e.key === 'Tab') trapTab(e);
    return;
  }
```

Layouts carry each chart's settings. `HBCatalog.migrate` keeps only `{root, spec, indicators}`, and `catalog.js` must not be touched here, so the page re-attaches them. Add after `loadLast`:

```js
/* A saved layout (localStorage or the server) as the page runs it: HBCatalog.migrateLayout gives each chart's
   {root, spec, indicators}; each chart's settings (HBSettings overrides, cleaned) are kept beside them. */
function readLayout(v) {
  const lay = C.migrateLayout(v), raw = v && Array.isArray(v.cells) ? v.cells : [];
  lay.cells.forEach((c, i) => {
    const s = raw[i] && raw[i].settings, o = S.overrides(s && typeof s === 'object' ? s : {});
    if (Object.keys(o).length) c.settings = o;
  });
  return lay;
}
```

Make these one-line changes:
- In `loadLast`, use `layout = { ...readLayout(v), name: typeof v.name === 'string' ? v.name : '', dirty: v.dirty === true };`.
- In `loadLayout`, use `layout = { ...readLayout(saved), name, dirty: false };`.
- Change the initial `let layout = { grid: 4, cells: [], name: '' };` to `let layout = { grid: 4, cells: [], name: '', dirty: false };`.
- In `putLayout`, the body becomes:

```js
  const body = { grid: layout.grid, cells: layout.cells.map(({ root, spec, indicators, settings }) =>
    (settings && Object.keys(settings).length ? { root, spec, indicators, settings } : { root, spec, indicators })) };
```

- In `renderToolbar`: `$('#tbLayoutName').textContent = !layout.name ? 'Unsaved' : layout.dirty ? `${layout.name} · Unsaved` : layout.name;`
- In `save()`, after `const why = await putLayout(layout.name);`, add `if (!why && layout.dirty) { layout.dirty = false; saveLast(); renderToolbar(); }`.
- In `layoutMenu`'s `askName` `go()`: `if (layout === saving) { layout.name = name; layout.dirty = false; saveLast(); renderToolbar(); }`.

Add the dialog opener after `positionDialog`, and bind it in `init()` with `$('#tbSettings').onclick = chartSettings;`:

```js
/* The toolbar gear: the chart Settings dialog for the selected chart (settings-dialog.js). */
function chartSettings() {
  const c = cur();
  if (!c) return;
  const box = openDialog('Settings', 'settings');
  const ctl = window.HBSettingsDialog.mount(box, {
    cell: c,
    cells: () => cells,
    toggleMenu(anchor, cls, fill) {   // menus and popovers open inside the dialog (above its backdrop)
      if (menuAnchor === anchor) { closeMenu(); return; }
      fill(openMenu(anchor, cls, { root: box }));
      placeMenu();
    },
    closeMenu,
    placeMenu,
    commit(changed) {   // Ok: the layout keeps the changes and reads Unsaved until saved
      if (changed) { layout.dirty = true; saveLast(); renderToolbar(); }
      closeDialog();
    },
    cancel: closeDialog,
  });
  dlg.onClose = ctl.revert;   // Cancel, ×, Esc, a backdrop click: every chart back (a no-op after Ok)
}
```

- [ ] **Step 4: Shell, styles, icons.**

`charts.html`:
- In the toolbar, between the last `<span class="tb-sep"></span>` and `#tbTheme`, insert: `<button class="tb-btn tb-icon" id="tbSettings" type="button" title="Chart settings" aria-label="Chart settings" aria-haspopup="dialog"><span class="icw" data-icon="gear"></span></button>`.
- Add `<script src="/static/charts/settings.js?v=3"></script>` after the `position.js` script, and `<script src="/static/charts/settings-dialog.js?v=3"></script>` after `cell.js`.

`icons.js`: add `chart-candlestick, paintbrush` to the header list and:

```js
  candles: svg('<path d="M9 5v4"/><rect width="4" height="6" x="7" y="9" rx="1"/><path d="M9 15v2"/><path d="M17 3v2"/><rect width="4" height="8" x="15" y="5" rx="1"/><path d="M17 13v3"/><path d="M3 3v16a2 2 0 0 0 2 2h16"/>'),
  paintbrush: svg('<path d="m14.622 17.897-10.68-2.913"/><path d="M18.376 2.622a1 1 0 1 1 3.002 3.002L17.36 9.643a.5.5 0 0 0 0 .707l.944.944a2.41 2.41 0 0 1 0 3.408l-.944.944a.5.5 0 0 1-.707 0L8.354 7.348a.5.5 0 0 1 0-.707l.944-.944a2.41 2.41 0 0 1 3.408 0l.944.944a.5.5 0 0 0 .707 0z"/><path d="M9 8c-1.804 2.71-3.97 3.46-6.583 3.948a.507.507 0 0 0-.302.819l7.32 8.883a1 1 0 0 0 1.185.204C12.735 20.405 16 16.792 16 15"/>'),
```

`charts.css`:
- Change the rule `button, input { font: inherit; color: inherit; }` to `button, input, select { font: inherit; color: inherit; }`.
- In `.menu`, change `z-index: 50` to `z-index: 70`, so that menus also open above a dialog.
- Append:

```css
/* ---- chart Settings dialog (settings-dialog.js) ---- */
.dialog.settings { width: min(820px, 94vw); height: min(600px, 88vh); max-height: none; }
.set-body { flex: 1; min-height: 0; display: flex; border-top: 1px solid var(--border); }
.set-tabs { flex: none; width: 220px; display: flex; flex-direction: column; gap: 2px; padding: 8px; overflow: auto;
  border-right: 1px solid var(--border); }
.set-tab { flex: none; width: 100%; height: 40px; display: flex; align-items: center; gap: 12px; padding: 0 12px;
  border-radius: 6px; font-size: 15px; text-align: left; color: var(--text); }
.set-tab .ic { width: 20px; height: 20px; }
.set-tab:hover, .set-tab.active { background: var(--hover); }
.set-pane { flex: 1; min-width: 0; overflow: auto; padding: 4px 24px 16px; scrollbar-width: thin; }
.set-cap { margin: 16px 0 4px; color: var(--text-2); font-size: 12px; letter-spacing: .04em; text-transform: uppercase; }
.set-row { height: 40px; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 16px; }
.set-name { min-width: 0; display: flex; align-items: center; gap: 10px; white-space: nowrap; overflow: hidden; }
.set-name span { overflow: hidden; text-overflow: ellipsis; }
.set-name input[type="checkbox"] { flex: none; width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }
.set-ctl { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.set-unit { color: var(--text-2); font-size: 13px; }
.swatch { flex: none; width: 28px; height: 28px; padding: 4px; border-radius: 4px; box-shadow: inset 0 0 0 1px var(--border); }
.swatch i { display: block; width: 100%; height: 100%; border-radius: 2px; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .06); }
.swatch:hover, .swatch.open { box-shadow: inset 0 0 0 1px var(--text-2); }
.set-select { height: 32px; padding: 0 28px 0 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px;
  appearance: none; background: var(--panel) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23787B86' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 8px center / 14px; }
.set-num { width: 72px; height: 32px; padding: 0 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel);
  font-variant-numeric: tabular-nums; }
.set-select:focus, .set-num:focus { border-color: var(--accent); }
.set-foot { flex: none; display: flex; align-items: center; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--border); }
.set-foot .grow { flex: 1; }
.btn-solid { background: var(--text); color: var(--panel); }
.btn-solid:hover { opacity: .88; }
.menu-swatch { width: 252px; padding: 12px; }
.sw-grid { display: grid; grid-template-columns: repeat(10, 20px); gap: 3px; }
.sw-cell { width: 20px; height: 20px; border-radius: 3px; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .08); }
.sw-cell.on { box-shadow: 0 0 0 2px var(--panel), 0 0 0 3px var(--accent); }
.sw-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 13px; }
.sw-row input[type="range"] { flex: 1; min-width: 0; accent-color: var(--accent); }
.sw-pct { width: 38px; text-align: right; font-variant-numeric: tabular-nums; }
.sw-hex { width: 96px; height: 28px; padding: 0 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel);
  font-variant-numeric: tabular-nums; }
.sw-hex:focus { border-color: var(--accent); }
.sw-default { margin-left: auto; color: var(--accent); font-size: 13px; }
.sw-default:hover { text-decoration: underline; }
.sw-err { margin-top: 6px; color: var(--down); font-size: 12px; }
@media (max-width: 640px) {
  .set-tabs { width: 60px; }
  .set-tab span:last-child { display: none; }
}
```

- [ ] **Step 5: Syntax-check and run the suites**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green. The Node tests do not load `cell.js`, `app.js` or `settings-dialog.js`, which are checked in the browser.

- [ ] **Step 6: Commit**

```bash
git add homebase/static/charts/settings-dialog.js homebase/static/charts/cell.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js
git commit -m "feat(charts): chart Settings dialog — Symbol and Canvas tabs with live preview, swatch popover, Cancel reverts, Ok keeps; settings saved per chart in layouts

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check (replay :8854; a 2×2 layout):**
- Opening:
  - The gear (`Chart settings`) sits just left of the theme button.
  - It opens `Settings` (20px/600) with the × at about 820×600.
  - Tabs `Symbol` and `Canvas` show icons, rows are 40px, and the selected tab is on `--hover`.
  - Captions are uppercase 12px `--text-2`, and the controls line up in a column on the right.
- Symbol tab:
  - Unticking Body leaves hollow candles; Borders and Wick behave the same way.
  - Each swatch opens the popover: a 10×6 palette, opacity with %, a hex field (`#12` shows `Use #RRGGBB` inline) and `Default`.
  - Picking a colour previews immediately on the selected chart only. Dragging the opacity is smooth, with no flashing.
  - "Colour bars based on previous close" recolours candles by the previous close, and the legend's OHLC colours follow.
  - Precision `0.1` shows one decimal on the price axis and in the legend.
  - Timezone `UTC` shifts the axis and crosshair labels by 4h; `Chicago` by −1h; `Local` matches the Mac's clock.
- Canvas tab: the background, grid on/off and colours, crosshair colour/style/width, watermark on/off and colour, axis text colour and size, and the axis lines colour all preview live.
- Cancel reverts everything. So do ×, Esc and a backdrop click. With the swatch popover open, Esc closes only the popover.
- Ok keeps the changes. The toolbar reads `<layout> · Unsaved` (or `Unsaved`), and Save clears the marker.
- A saved layout reloads with each chart's own settings; a reload of the page keeps them too.
- An old layout without `settings` loads with the defaults.
- The theme toggle: never-changed colours follow the theme, while a changed background stays.
- The footprint still hides candle bodies (and borders) when zoomed in.
- Magnet crosshair (Task 2) still works after the rebuilds.
- Tab stays inside the dialog, including in the popover; zero console errors.

---
### Task 7: Chart Settings — Status line and Scales tabs, hours background, countdown, scale price only, templates, Apply to all

**Files:**
- Modify: `homebase/static/charts/settings-dialog.js`
- Modify: `homebase/static/charts/cell.js`
- Modify: `homebase/static/charts/primitives.js` (`EthBg`, `Countdown`)
- Modify: `homebase/static/charts/app.js` (templates client, replay clock, the 1 s tick reaches the charts)
- Modify: `homebase/static/charts.html`, `homebase/static/charts/charts.css`, `homebase/static/charts/icons.js`

**Interfaces:**
- Consumes:
  - Task 5's `legendFlags`, `legendLabel`, `titleText`, `outsideRth`, `barCloseEt`, `fmtCountdown`, `zoneOffsetMs`, `templateNameError`, `overrides`, `normalize`.
  - Task 6's `mount` internals (`work`, `set`, `preview`, `flush`, `renderPane`, `button`, `mk`, `foot`, `grow`, `cancel`, `ok`, `TABS`, `LINE`), `Cell.R`, `Cell.applySettings`, `Cell.setSettings`, `chartSettings()`, and `openMenu(…, {root})`.
  - Task 1's `/api/templates` routes.
  - Existing: the `Layer` base in `primitives.js`, `showStatus`, `tick`, `C.ALWAYS_OPEN`, `C.def`, `C.label`, `C.rootName`, `C.specLabel`.
- Produces:
  - `HBLayers.EthBg`: `set(bars, on, color, isEth)`.
  - `HBLayers.Countdown`: `new Countdown(P, read)`, with `read() -> {text, price, color, font}|null`.
  - `Cell.syncEth()`, `Cell.countdownNow()`, `Cell.tickSecond(nowEt)`, and the fields `Cell.eth`, `Cell.cd`, `Cell.clockEt`.
  - `this.lines[i].overlay`: true for a series on the price pane's own scale.
  - Page: `templates = {list(), save(name, settings), remove(name)}` (the latter two return `''` or a reason), `replayClock`, `clockEt()`.
  - The dialog host gains `templates`. `HBSettingsDialog.TABS` becomes Symbol · Status line · Scales and lines · Canvas.
- Task 9 (deep history) calls `Cell.syncEth()` after a prepend.

- [ ] **Step 1: `primitives.js`, two layers.** Insert before `window.HBLayers = …`, and export both (`window.HBLayers = { Footprint, Profile, Gaps, Layer, EthBg, Countdown };`):

```js
/* Electronic (outside regular) trading hours shaded behind the bars: every bar starting outside
   09:30-16:00 ET, merged into runs. set(bars, on, color, isEth(etWallSeconds)). */
class EthBg extends Layer {
  constructor(P) { super(P); this.bars = []; this.on = false; this.color = ''; this.isEth = () => false; }
  z() { return 'bottom'; }
  set(bars, on, color, isEth) { this.bars = bars; this.on = on; this.color = color; this.isEth = isEth; this.redraw(); }
  draw(target) {
    if (!this.on || !this.chart || !this.bars.length) return;
    const ts = this.chart.timeScale(), r = ts.getVisibleLogicalRange();
    if (!r) return;
    const i0 = Math.max(0, Math.floor(r.from)), i1 = Math.min(this.bars.length - 1, Math.ceil(r.to));
    if (i1 < i0) return;
    const half = Math.max(this.spacing(), 1) / 2;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.fillStyle = this.color;
      let run = null;   // [left, right] of consecutive shaded bars
      const flush = () => { if (run) { ctx.fillRect(run[0], 0, run[1] - run[0], mediaSize.height); run = null; } };
      for (let i = i0; i <= i1; i++) {
        const x = ts.logicalToCoordinate(i);   // integer logicals only (v5)
        if (x == null || !this.isEth(this.bars[i].t)) { flush(); continue; }
        if (run) run[1] = x + half; else run = [x - half, x + half];
      }
      flush();
    });
  }
}

/* The time left in the last bar, as a price-axis label just below the last-price label (TradingView's
   countdown). read() -> {text, price, color, font} | null is asked before every render; the page asks for a
   render once a second. priceAxisViews() returns ONE stable array: Lightweight Charts caches its wrapper by
   the array's identity and calls these methods at every render. */
class Countdown extends Layer {
  constructor(P, read) {
    super(P);
    this.read = read;
    this.cur = null;
    this.axis = [{
      coordinate: () => { const y = this.y(); return y == null ? -100 : y; },
      text: () => (this.cur ? this.cur.text : ''),
      textColor: () => this.P.onAccent,
      backColor: () => (this.cur ? this.cur.color : 'rgba(0,0,0,0)'),
      visible: () => this.y() != null,
      tickVisible: () => false,
    }];
  }
  paneViews() { return []; }
  priceAxisViews() { return this.axis; }
  updateAllViews() { this.cur = this.read(); }
  y() {
    if (!this.cur || !this.series) return null;
    const y = this.series.priceToCoordinate(this.cur.price);
    return y == null ? null : y + Math.round((this.cur.font * 4) / 3) + 2;   // one axis label below the last price
  }
}
```

- [ ] **Step 2: `cell.js`.**

Change the layers import to `const { Footprint, Profile, Gaps, EthBg, Countdown } = window.HBLayers;` and add `const NO_SCALE = () => null;   // autoscaleInfoProvider: the series takes no part in autoscale`.

Constructor fields: add `this.eth = this.cd = null; this.clockEt = null;   // the hours background, the countdown, now (ET wall ms)`.

Replace `title()` with:

```js
  title() {
    const { root, spec } = this.cfg, F = S.legendFlags(this.R);
    this.lg.name.hidden = !F.title;
    this.lg.name.textContent = S.titleText(root, C.rootName(root), C.specLabel(spec), F.titleMode);
  }
```

In `makeChart()`, after the `Footprint/Profile/Gaps` line, add `this.eth = new EthBg(P); this.cd = new Countdown(P, () => this.countdownNow());`. Change the attach line to `for (const l of [this.eth, this.gaps, this.prof, this.fp, this.cd]) this.candles.attachPrimitive(l);`. In `teardown()`, add `this.eth = this.cd = null;` next to the other nulls.

In `build(view)`, change `this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint(); this.syncProfile();` to also call `this.syncEth();` at the end.

In `buildSeries()`, replace the `add` helper with:

```js
    const add = (inst, src, part, type, opts, where) => {
      const overlay = where === 0 && !opts.priceScaleId;   // on the price pane's own scale (not the volume overlay)
      const auto = overlay && this.R.scalePriceOnly ? { autoscaleInfoProvider: NO_SCALE } : {};
      const s = this.chart.addSeries(type, { priceLineVisible: false, visible: inst.visible !== false, ...opts, ...auto }, where);
      this.lines.push({ uid: inst.uid, s, src, part, overlay });
      return s;
    };
```

In `applySettings()`, just before `this.legendRows();`, add:

```js
    if (R.scalePriceOnly !== was.scalePriceOnly) {   // "Scale price chart only": the price pane's lines leave autoscale
      for (const l of this.lines) if (l.overlay) l.s.applyOptions({ autoscaleInfoProvider: R.scalePriceOnly ? NO_SCALE : undefined });
    }
    this.syncEth();
    if (this.cd) this.cd.redraw();
```

Replace `legendRows()` with the version below. Indicator titles and arguments follow the Status line:

```js
  legendRows() {
    const F = S.legendFlags(this.R);
    this.rows = this.cfg.indicators.map((inst) => {
      const off = inst.visible === false, row = mk('div', 'lg-row' + (off ? ' off' : '')), vals = mk('span', 'lg-vals');
      const btns = mk('span', 'lg-btns'), hasParams = C.def(inst.id).params.length > 0;
      btns.append(iconButton(off ? 'eyeOff' : 'eye', off ? 'Show' : 'Hide', 'eye'));
      if (hasParams) btns.append(iconButton('gear', 'Settings', 'gear'));
      btns.append(iconButton('x', 'Remove', 'x'));
      row.dataset.uid = inst.uid;
      row.append(mk('span', 'lg-label', S.legendLabel(C.label(inst), hasParams, F)), vals, btns);
      return { inst, row, vals };
    });
    this.lg.inds.replaceChildren(...this.rows.map((r) => r.row));
  }
```

In `legend(i)` (Task 6's version), replace the `this.lg.ohlc.replaceChildren(…)` call and the values loop with:

```js
    const F = S.legendFlags(R), parts = [];
    if (F.ohlc) parts.push(...[['O', b.o], ['H', b.h], ['L', b.l], ['C', b.c]].map(([key, v]) => kv(key, C.fmtPrice(v, dt), col)));
    if (F.change) parts.push(val(ch.text, ch.up ? R.bodyUp : R.bodyDown));
    if (F.volume) parts.push(kv('Vol', C.fmtCompact(b.v), col), kv('Δ', C.fmtSigned(b.d), b.d >= 0 ? P.up : P.down));
    this.lg.ohlc.replaceChildren(...parts);
    const colors = { text: P.text, up: P.up, down: P.down, vwap: P.vwap, cum: P.cum };
    for (const r of this.rows) {
      const vs = F.indValues ? C.legendValues(r.inst, b, { ...colors, line: this.colorOf[r.inst.uid] || P.accent }, dt) : [];
      r.vals.replaceChildren(...vs.map((x) => val(x.text, x.color)));
    }
```

Add the methods (after `retime`):

```js
  /* The electronic-hours background: intraday time charts only. */
  syncEth() {
    if (!this.eth) return;
    this.eth.set(this.bars, this.R.ethBg && this.isTime() && this.barMs() < 86400000, this.R.ethBgColor, S.outsideRth);
  }

  /* The countdown under the last-price label: {text, price, color, font}, or null when it is off, the label is
     off, the chart is not a time chart, no clock came yet, or the last bar already closed. */
  countdownNow() {
    const R = this.R, n = this.bars.length, ms = this.barMs();
    if (!R.countdown || !R.lastLabel || !ms || !n || this.clockEt == null || !this.shown) return null;
    const last = this.bars[n - 1], left = S.barCloseEt(last, ms, C.ALWAYS_OPEN.has(this.shown.root)) - this.clockEt;
    if (left <= 0) return null;
    const prev = n > 1 ? this.bars[n - 2] : null, up = last.c >= (R.prevClose && prev ? prev.c : last.o);
    return { text: S.fmtCountdown(left), price: last.c, color: up ? R.bodyUp : R.bodyDown, font: R.scaleFont };
  }

  /* Once a second, from the page: now as ET wall-clock ms (a replay's own clock in a replay). */
  tickSecond(nowEt) { this.clockEt = nowEt; if (this.cd) this.cd.redraw(); }
```

- [ ] **Step 3: `settings-dialog.js`, the two tabs and the hours row.** In `TABS`, append to the Symbol tab's `DATA` rows:

```js
      { label: 'Electronic trading hours background', check: 'ethBg', colors: [['ethBgColor', '']] },
```

Between the Symbol and Canvas entries, insert:

```js
  { id: 'status', label: 'Status line', icon: 'list', sections: [
    ['SYMBOL', [
      { label: 'Symbol title', check: 'title', select: { key: 'titleMode',
        choices: [['ticker', 'Ticker'], ['description', 'Description'], ['both', 'Ticker and description']] } },
      { label: 'OHLC values', check: 'ohlc' },
      { label: 'Bar change values', check: 'barChange' },
      { label: 'Volume', check: 'volume' },
    ]],
    ['INDICATORS', [
      { label: 'Indicator titles', check: 'indTitles' },
      { label: 'Indicator arguments', check: 'indArgs' },
      { label: 'Indicator values', check: 'indValues' },
    ]],
  ] },
  { id: 'scales', label: 'Scales and lines', icon: 'measure', sections: [
    ['PRICE SCALE', [
      { label: 'Scale price chart only', check: 'scalePriceOnly' },
      { label: 'Symbol last price label', check: 'lastLabel' },
      { label: 'Symbol last price line', check: 'lastLine', select: { key: 'lastLineStyle', choices: LINE } },
      { label: 'Countdown to bar close', check: 'countdown' },
      { label: 'Top margin', number: { key: 'marginTop', min: 0, max: 40, unit: '%' } },
      { label: 'Bottom margin', number: { key: 'marginBottom', min: 0, max: 40, unit: '%' } },
    ]],
    ['TIME SCALE', [
      { label: 'Right margin', number: { key: 'rightOffset', min: 0, max: 100, unit: 'bars' } },
    ]],
  ] },
```

(`measure` is the Lucide `ruler` icon already in `icons.js`.) Update the TABS comment: "Task 8 adds Events."

- [ ] **Step 4: `settings-dialog.js`, templates and Apply to all.** Extend the header's host list with `templates: {list(), save(name, settings), remove(name)}`. Inside `mount`, before the footer section, add:

```js
  /* A template or "Apply defaults": the dialog's settings become it, previewed live. */
  function applyTemplate(o) { work = S.normalize(o); renderPane(); preview(); }
  function menuBtn(text) {
    const b = button('menu-i');
    b.setAttribute('role', 'menuitem');
    b.append(mk('span', 'menu-t', text));
    return b;
  }

  /* Template ▾: Save as… (an inline name field, Enter saves), Apply defaults, then the saved templates (a click
     applies one to the dialog; × deletes it after an inline "Delete?"). Every error shows inline. */
  function templateMenu(anchor) {
    host.toggleMenu(anchor, 'menu-tpl', (m) => {
      const list = mk('div'), err = mk('div', 'menu-err'), saveAs = menuBtn('Save as…'), defaults = menuBtn('Apply defaults');
      err.hidden = true;
      err.setAttribute('role', 'alert');
      m.append(saveAs, defaults, mk('div', 'menu-sep'), list, err);
      const fail = (text) => { err.textContent = text; err.hidden = false; host.placeMenu(); };
      defaults.onclick = () => { host.closeMenu(); applyTemplate({}); };
      saveAs.onclick = () => {
        const rowEl = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), go = button('btn btn-primary', 'Save');
        input.type = 'text'; input.placeholder = 'Template name'; input.maxLength = 40; input.spellcheck = false;
        input.setAttribute('aria-label', 'Template name');
        const save = async () => {
          const name = input.value.trim(), why = S.templateNameError(name);
          if (why) { fail(why); input.focus(); return; }
          const res = await host.templates.save(name, S.overrides(work));
          if (res) { fail(res); return; }
          host.closeMenu();
        };
        go.onclick = save;
        input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } };
        rowEl.append(input, go);
        saveAs.replaceWith(rowEl);
        input.focus();
      };
      list.append(mk('div', 'menu-empty', 'Loading…'));
      host.templates.list().then((all) => {
        if (!m.isConnected) return;   // closed meanwhile
        if (!all) { list.replaceChildren(); fail('could not load the templates'); return; }
        const names = Object.keys(all).sort((a, b) => a.localeCompare(b));
        list.replaceChildren(...(names.length ? names.map((n) => tplRow(n, all[n])) : [mk('div', 'menu-empty', 'No saved templates')]));
        host.placeMenu();
      });
      function tplRow(name, settings) {
        const r = mk('div', 'menu-row'), pick = menuBtn(name), del = button('menu-del');
        del.title = `Delete ${name}`;
        del.setAttribute('aria-label', `Delete ${name}`);
        del.innerHTML = I.x;   // our own static SVG string
        pick.onclick = () => { host.closeMenu(); applyTemplate(settings); };
        del.onclick = () => {
          const ask = mk('div', 'menu-confirm'), yes = button('btn btn-danger', 'Delete'), no = button('btn btn-ghost', 'Cancel');
          ask.append(mk('span', '', `Delete “${name}”?`), yes, no);
          r.replaceWith(ask);
          no.focus();
          no.onclick = () => { ask.replaceWith(r); del.focus(); };
          yes.onclick = async () => {
            const res = await host.templates.remove(name);
            if (res) { ask.replaceWith(r); fail(res); return; }
            ask.remove();
            if (!list.querySelector('.menu-row, .menu-confirm')) list.replaceChildren(mk('div', 'menu-empty', 'No saved templates'));
          };
        };
        r.append(pick, del);
        return r;
      }
    });
  }
```

In the footer section, create the two buttons and change `foot.append(grow, cancel, ok);` to put them in place:

```js
  const tpl = button('btn btn-ghost tpl-btn'), chev = mk('span', 'icw sm'), applyAll = button('btn btn-ghost', 'Apply to all');
  chev.innerHTML = I.chevron;
  tpl.append(mk('span', '', 'Template'), chev);
  tpl.setAttribute('aria-haspopup', 'menu');
  tpl.onclick = () => templateMenu(tpl);
  applyAll.title = 'Copy these settings to every chart in the layout';
  applyAll.onclick = () => {   // live on every chart; the dialog stays open (Cancel puts them all back)
    flush();
    const o = S.overrides(work);
    for (const c of host.cells()) c.setSettings(o);
  };
  foot.append(tpl, grow, applyAll, cancel, ok);
```

- [ ] **Step 5: `app.js`.**

Add a templates section (after the saved-layouts section):

```js
/* ---- chart-settings templates (shared by every chart, saved on the server) ---- */
const templates = {
  /* {name: settings}, or null when they could not be read. */
  async list() { try { const r = await fetch('/api/templates'); return r.ok ? await r.json() : null; } catch (_) { return null; } },
  /* '' when saved / deleted, else the reason. */
  save: (name, settings) => writeTemplate('PUT', name, settings),
  remove: (name) => writeTemplate('DELETE', name),
};
async function writeTemplate(method, name, body) {
  const what = method === 'PUT' ? 'save' : 'delete';
  let r;
  try {
    r = await fetch('/api/templates/' + encodeURIComponent(name), body === undefined ? { method }
      : { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  } catch (_) { return `${what} failed: network error`; }
  if (r.ok) return '';
  let detail = '';
  try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
  return `${what} failed (${r.status})` + (detail ? ': ' + detail : '');
}
```

In `chartSettings()`, add `templates,` to the host object.

Replay clock and the charts' 1-second tick. Add to the state: `let replayClock = null;   // {etMs, at, speed, done}: a replay's clock from its last status (live: null)`. At the top of `showStatus(s)`, add:

```js
  if (s.mode === 'replay') replayClock = { etMs: (s.clock_s || 0) * 1000, at: Date.now(), speed: s.speed || 1, done: !!s.done };
  else if (s.mode === 'live') replayClock = null;
```

Add the function below and replace `tick()`:

```js
/* Now as ET wall-clock ms: a replay's own clock (run on at its speed between its 2 s status messages), else
   the browser's. The charts' countdowns run on it. */
function clockEt() {
  if (replayClock) return replayClock.etMs + (replayClock.done ? 0 : (Date.now() - replayClock.at) * replayClock.speed);
  const now = Date.now();
  return now + S.zoneOffsetMs('America/New_York', now);
}

function tick() {
  $('#sbClock').textContent = `${ET_CLOCK.format(new Date())} ET`;
  greyIfStale();
  const et = clockEt();
  for (const c of cells) c.tickSecond(et);
}
```

- [ ] **Step 6: Shell, styles, icon.** In `charts.html`, set `primitives.js?v=3`. In `icons.js`, add `list` to the header's Lucide list and to the Feather-derived list, and add `list: svg('<path d="M3 5h.01"/><path d="M3 12h.01"/><path d="M3 19h.01"/><path d="M8 5h13"/><path d="M8 12h13"/><path d="M8 19h13"/>'),`. In `charts.css`, append:

```css
.tpl-btn { display: inline-flex; align-items: center; gap: 6px; }
.menu-tpl { min-width: 240px; }
```

- [ ] **Step 7: Syntax-check and run the suites**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green.

- [ ] **Step 8: Commit**

```bash
git add homebase/static/charts/settings-dialog.js homebase/static/charts/cell.js homebase/static/charts/primitives.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js
git commit -m "feat(charts): Settings — Status line and Scales tabs, hours background, bar-close countdown, scale price chart only, templates, Apply to all

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check (replay :8854; 2×2 layout; add an EMA and VWAP bands to the selected chart):**
- The tabs read Symbol · Status line · Scales and lines · Canvas.
- Status line:
  - Symbol title off hides the name (the approx.-flow badge and messages stay).
  - `Ticker` gives `NQ · 1m`; `Description` gives `E-mini Nasdaq-100 · 1m`.
  - OHLC, bar change and volume (`Vol` and `Δ`) each hide their part of row 2.
  - Indicator titles off leaves `20` for `EMA 20`; arguments off leaves `EMA`; values off hides the numbers.
- Scales and lines:
  - Scale price chart only: the EMA and VWAP bands no longer stretch the price scale (zoom so a band leaves the candles' range).
  - The last price label and line toggle; the line style works.
  - The countdown `mm:ss` sits just below the last-price label on a 1m chart. It ticks each second on the replay clock (×20), switches to `h:mm:ss` on 4h, and is absent on a tick chart.
  - The top/bottom margins and the right margin (bars) move the chart live.
- Symbol → Electronic trading hours background shades bars before 09:30 and from 16:00 ET, on intraday time charts only, and its swatch changes the colour.
- Templates:
  - `Template ▾` → `Save as…` → an inline name field; Enter saves. Names like `a/b` or `.` show the reason inline.
  - The saved name lists under `Apply defaults`; a click applies it to the dialog live.
  - × → `Delete “name”?` → Delete removes it.
  - `Apply defaults` clears every override.
  - `templates.json` appears in the worktree's `homebase/.state/charts/`.
- `Apply to all` copies the settings to all four charts live and keeps the dialog open. Cancel then reverts all four; Ok keeps them and marks the layout Unsaved.
- The theme switch keeps changed colours; unchanged ones follow the theme.
- Zero console errors.

---
### Task 8: Economic calendar (ForexFactory) — the service, flags and lines on the charts, the tooltip, the status-bar countdown, the Events tab

**Files:**
- Create: `homebase/charts/calendar.py`
- Create: `tests/test_charts_calendar.py`
- Modify: `homebase/charts/server.py` (a `calendar_fetch` parameter, the `Calendar`, `/api/calendar`, the status field, the fetch loop)
- Modify: `homebase/charts/__main__.py` (passes the real fetch function)
- Create: `homebase/static/charts/events.js` (`HBEvents`, pure)
- Create: `tests/js/events.test.mjs`
- Modify: `homebase/static/charts/settings.js`, `tests/js/settings.test.mjs` (the Events fields and a `list` field type)
- Modify: `homebase/static/charts/settings-dialog.js` (the Events tab)
- Modify: `homebase/static/charts/primitives.js` (`EventFlags`)
- Modify: `homebase/static/charts/cell.js` (the layer, the hover tooltip)
- Modify: `homebase/static/charts/app.js` (the calendar cache, the status-bar countdown, the host's `events()` / `countries()`)
- Modify: `homebase/static/charts.html`, `homebase/static/charts/charts.css`, `homebase/static/charts/icons.js`

**Interfaces:**
- Consumes:
  - Task 5/7's `HBSettings.wallSeconds`, `zoneOffsetMs`, `normalize`, `overrides` and `FIELDS`.
  - Task 6's dialog `row()` / `TABS`.
  - Task 7's `replayClock`, `clockEt()`, `tick()`, `showStatus()`.
  - Existing: `HBDrawings.timeToX`, the `Layer` base, `create_app`'s `status()` and `lifespan`, `sd` (the state dir).
- Produces:
  - Server:
    - `homebase.charts.calendar`: `FF_URL`, `EVERY_S = 3600`, `MIN_GAP_S = 1800`, `TIMEOUT_S = 10`, `IMPACTS`, `http_get(url) -> bytes`, `parse(raw) -> [{t_ms, title, country, impact, forecast, previous}]`, `week_start(t_ms) -> date`, and `Calendar(folder, fetch=None, now=time.time)` with `refresh() -> bool`, `wait_s() -> float`, `events(frm, to, countries=None) -> list`, `status() -> {ok, fetched_at, error}`.
    - `create_app(…, calendar_fetch=None)`: None never fetches (every existing test), and `python -m homebase.charts` passes `http_get`.
    - `GET /api/calendar?from=&to=&countries=` returns events with `from <= t_ms < to`, countries case-insensitive; a bad number gives 400.
    - `/api/status` gains `calendar: {ok, fetched_at, error}`.
    - Weeks are stored at `<state>/calendar/<YYYY-MM-DD>.json` (the Sunday), and the fetch floor at `<state>/calendar/state.json`.
  - Page:
    - `window.HBEvents`: `COLORS`, `FLAG = 10`, `shown(events, settings)`, `layout(events, xOf, width)`, `flagAt(flags, pt, y)`, `tipLine(e, tz)`, `tipLines(flag, tz)`, `fmtIn(ms)`, `nextText(events, nowMs) -> {text, color}|null`.
    - `HBLayers.EventFlags(P, read)`, with `flags` and `flagY`.
    - HBSettings fields `evHigh true, evMedium true, evLow false, evHoliday false, evCountries ['USD'] (type 'list'), evLines true`.
    - `Cell.eventsNow()`, `Cell.redrawEvents()`, `Cell.onEventHover(e)`, `Cell.evl`.
    - The host gains `events()`; the dialog host gains `countries()`.
    - `calendar`, `loadCalendar()`, `renderNextEvent()`, `clockMs()`, and `#sbEvent`.
- Task 9 needs no change for the calendar: the layer reads the chart's bars at every render.

- [ ] **Step 1: Write the failing server tests** — `tests/test_charts_calendar.py`:

```python
"""The economic calendar (ForexFactory's weekly feed, spec §6): parsing, the 30-minute floor, keeping the
last good data, per-week storage and the range merge, the country filter, the route and the status field.
Every fetch is injected: no test touches the network."""
from __future__ import annotations

import datetime as dt
import json
import time

import pytest
from fastapi.testclient import TestClient

from homebase.charts.calendar import EVERY_S, FF_URL, IMPACTS, MIN_GAP_S, Calendar, parse, week_start
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive

FEED = [
    {"title": "RBNZ Rate Statement", "country": "NZD", "date": "2026-09-20T22:00:00-04:00", "impact": "High",
     "forecast": "", "previous": ""},
    {"title": "German ifo Business Climate", "country": "EUR", "date": "2026-09-22T04:00:00-04:00",
     "impact": "Medium", "forecast": "88.9", "previous": "88.8"},
    {"title": "CPI m/m", "country": "USD", "date": "2026-09-22T08:30:00-04:00", "impact": "High",
     "forecast": "0.3%", "previous": "0.2%"},
    {"title": "Core CPI m/m", "country": "USD", "date": "2026-09-22T08:30:00-04:00", "impact": "High",
     "forecast": "0.3%", "previous": "0.3%"},
    {"title": "Bank Holiday", "country": "JPY", "date": "2026-09-23T00:00:00-04:00", "impact": "Holiday",
     "forecast": "", "previous": ""},
    {"title": "Crude Oil Inventories", "country": "USD", "date": "2026-09-23T10:30:00-04:00", "impact": "Low",
     "forecast": None, "previous": "-1.2M"},
    {"title": "OPEC Meetings", "country": "All", "date": "2026-09-24T03:00:00-04:00", "impact": "Non-Economic",
     "forecast": "", "previous": ""},
]
T0 = 1_790_000_000.0          # a wall clock for the fetch timer (seconds)


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def feed(events=FEED):
    return lambda url: json.dumps(events).encode()


def test_parse_turns_iso_times_with_their_offsets_into_epoch_ms():
    evs = parse(FEED)
    assert [e["title"] for e in evs] == ["RBNZ Rate Statement", "German ifo Business Climate", "CPI m/m",
                                         "Core CPI m/m", "Bank Holiday", "Crude Oil Inventories", "OPEC Meetings"]
    assert evs[2] == {"t_ms": ms("2026-09-22T12:30:00+00:00"), "title": "CPI m/m", "country": "USD",
                      "impact": "High", "forecast": "0.3%", "previous": "0.2%"}
    assert parse([{**FEED[2], "date": "2026-09-22T13:30:00+01:00"}])[0]["t_ms"] == evs[2]["t_ms"]   # any offset
    assert {e["impact"] for e in evs} == set(IMPACTS) == {"High", "Medium", "Low", "Holiday", "Non-Economic"}
    assert evs[5]["forecast"] == "" and evs[6]["country"] == "ALL"


def test_parse_skips_bad_items_and_refuses_a_non_list():
    bad = [{**FEED[2], "impact": "Weird"}, {**FEED[2], "date": "2026-09-22T08:30:00"},      # no offset
           {**FEED[2], "date": "soon"}, {**FEED[2], "title": ""}, "CPI", None]
    assert parse(bad + [FEED[2]]) == parse([FEED[2]])
    with pytest.raises(ValueError):
        parse({"events": FEED})


def test_the_week_is_forexfactorys_sunday_to_saturday_in_et():
    assert week_start(ms("2026-09-20T22:00:00-04:00")) == dt.date(2026, 9, 20)       # Sunday evening
    assert week_start(ms("2026-09-22T08:30:00-04:00")) == dt.date(2026, 9, 20)
    assert week_start(ms("2026-09-26T23:59:00-04:00")) == dt.date(2026, 9, 20)       # Saturday
    assert week_start(ms("2026-09-27T00:00:00-04:00")) == dt.date(2026, 9, 27)


def test_the_feed_is_asked_at_most_once_per_30_minutes_even_across_a_restart(tmp_path):
    clock, calls = [T0], []

    def fetch(url):
        calls.append(url)
        return json.dumps(FEED).encode()

    cal = Calendar(tmp_path / "cal", fetch=fetch, now=lambda: clock[0])
    assert cal.refresh() is True and calls == [FF_URL]
    clock[0] += MIN_GAP_S - 1
    assert cal.refresh() is False and len(calls) == 1                  # too soon
    clock[0] += 1
    assert cal.refresh() is True and len(calls) == 2
    again = Calendar(tmp_path / "cal", fetch=fetch, now=lambda: clock[0] + 60)    # a restart a minute later
    assert again.refresh() is False and len(calls) == 2
    assert again.wait_s() == EVERY_S - 60                               # after a good fetch: the next in an hour
    assert (MIN_GAP_S, EVERY_S) == (1800, 3600)
    assert Calendar(tmp_path / "other").refresh() is False              # no fetch function: never fetches


def test_a_failed_fetch_keeps_the_last_good_events_and_says_why(tmp_path):
    clock, answers = [T0], [json.dumps(FEED).encode()]

    def fetch(url):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    cal = Calendar(tmp_path / "cal", fetch=fetch, now=lambda: clock[0])
    assert cal.refresh()
    good, st = cal.events(0, 2 ** 62), cal.status()
    assert st == {"ok": True, "fetched_at": int(T0 * 1000), "error": None}
    for bad in (TimeoutError("timed out"), b"<html>blocked</html>", b"[]", json.dumps({"x": 1}).encode()):
        answers.append(bad)
        clock[0] += MIN_GAP_S
        assert cal.refresh() is False
        assert cal.events(0, 2 ** 62) == good
        now = cal.status()
        assert now["ok"] is False and now["error"] and now["fetched_at"] == st["fetched_at"]
    assert cal.wait_s() == MIN_GAP_S                                    # a failure is retried at the floor


def test_each_week_is_kept_on_disk_and_ranges_merge_across_weeks(tmp_path):
    folder, clock = tmp_path / "cal", [T0]
    nxt = [{**FEED[2], "title": "Retail Sales m/m", "date": "2026-09-29T08:30:00-04:00"}]
    answers = [json.dumps(FEED).encode(), json.dumps(nxt).encode()]
    cal = Calendar(folder, fetch=lambda url: answers.pop(0), now=lambda: clock[0])
    assert cal.refresh()
    clock[0] += EVERY_S
    assert cal.refresh()
    assert sorted(p.name for p in folder.glob("????-??-??.json")) == ["2026-09-20.json", "2026-09-27.json"]
    fresh = Calendar(folder)                                            # a restart reads every week back
    titles = [e["title"] for e in fresh.events(0, 2 ** 62)]
    assert titles[0] == "RBNZ Rate Statement" and titles[-1] == "Retail Sales m/m" and len(titles) == 8
    assert fresh.status()["ok"] is True


def test_the_query_is_a_time_range_and_a_set_of_countries(tmp_path):
    cal = Calendar(tmp_path / "cal", fetch=feed(), now=lambda: T0)
    cal.refresh()
    tue, wed = ms("2026-09-22T00:00:00-04:00"), ms("2026-09-23T00:00:00-04:00")
    assert [e["title"] for e in cal.events(tue, wed)] == ["German ifo Business Climate", "CPI m/m", "Core CPI m/m"]
    assert [e["title"] for e in cal.events(tue, wed, ["usd"])] == ["CPI m/m", "Core CPI m/m"]
    assert [e["title"] for e in cal.events(0, 2 ** 62, ["ALL", "JPY"])] == ["Bank Holiday", "OPEC Meetings"]
    assert cal.events(wed, tue) == []


def app(tmp_path, **kw):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0] * 60))
    return create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30),
                      state=tmp_path / "state", **kw)


def test_the_route_and_the_status_field(tmp_path):
    with TestClient(app(tmp_path, calendar_fetch=feed())) as client:
        for _ in range(300):                                            # the startup fetch runs off the event loop
            st = client.get("/api/status").json()["calendar"]
            if st["ok"]:
                break
            time.sleep(0.01)
        assert st["ok"] is True and st["error"] is None and st["fetched_at"]
        tue, wed = ms("2026-09-22T00:00:00-04:00"), ms("2026-09-23T00:00:00-04:00")
        got = client.get(f"/api/calendar?from={tue}&to={wed}&countries=USD,eur").json()
        assert [e["title"] for e in got] == ["German ifo Business Climate", "CPI m/m", "Core CPI m/m"]
        assert set(got[0]) == {"t_ms", "title", "country", "impact", "forecast", "previous"}
        assert len(client.get("/api/calendar").json()) == len(FEED)
        assert client.get("/api/calendar?from=soon").status_code == 400
    assert (tmp_path / "state" / "calendar" / "2026-09-20.json").exists()


def test_without_a_fetch_function_the_service_never_fetches(tmp_path):
    with TestClient(app(tmp_path)) as client:
        assert client.get("/api/status").json()["calendar"] == {"ok": False, "fetched_at": None, "error": None}
        assert client.get("/api/calendar").json() == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_calendar.py -q`
Expected: collection error (`No module named 'homebase.charts.calendar'`).

- [ ] **Step 3: Implement** `homebase/charts/calendar.py`:

```python
"""The economic calendar on the charts (spec §6): ForexFactory's weekly feed,
fetched on a timer, kept per week on disk so past weeks accumulate, served
to the page by time range and countries.

Source: FF_URL, the CURRENT week only (Sunday to Saturday, ET); fields title,
country, date (ISO with its ET offset), impact (High | Medium | Low | Holiday
| Non-Economic), forecast, previous. ForexFactory blocks aggressive polling:
at most one request per 30 minutes (the floor survives restarts: the last
try is on disk), otherwise a fetch an hour, with a browser User-Agent and a
10 s timeout. A failed fetch keeps the last good data and says why in
/api/status. The fetch function is injected (tests pass their own); without
one nothing is ever fetched.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
EVERY_S = 3600          # a good fetch is refreshed an hour later
MIN_GAP_S = 1800        # never two requests within 30 minutes (a failed one is retried at this floor)
TIMEOUT_S = 10
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
IMPACTS = ("High", "Medium", "Low", "Holiday", "Non-Economic")
ET = ZoneInfo("America/New_York")
WEEK_FILES = "????-??-??.json"


def http_get(url: str) -> bytes:
    """One GET as a browser sends it, 10 s timeout. certifi's CA bundle: a python.org build ships none."""
    import certifi   # noqa: PLC0415 — declared in requirements.txt; only the live service ever fetches

    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
        return r.read()


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def parse(raw) -> list[dict]:
    """The feed's events as [{t_ms, title, country, impact, forecast, previous}], by time (the feed's order
    within one time). An item without a title, an ISO date with an offset or a known impact is skipped, never
    the whole week. Country codes are upper-case ("All" -> "ALL"). ValueError when the feed is not a list."""
    if not isinstance(raw, list):
        raise ValueError("the feed is not a list of events")
    out = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        title, impact = _text(ev.get("title")), _text(ev.get("impact"))
        try:
            when = dt.datetime.fromisoformat(_text(ev.get("date")))
        except ValueError:
            continue
        if not title or impact not in IMPACTS or when.tzinfo is None:
            continue
        out.append({"t_ms": int(when.timestamp() * 1000), "title": title, "country": _text(ev.get("country")).upper(),
                    "impact": impact, "forecast": _text(ev.get("forecast")), "previous": _text(ev.get("previous"))})
    out.sort(key=lambda e: e["t_ms"])
    return out


def week_start(t_ms: int) -> dt.date:
    """The ForexFactory week (Sunday to Saturday, ET) an instant falls in, named by its Sunday."""
    d = dt.datetime.fromtimestamp(t_ms / 1000, ET).date()
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def _write_json(path: Path, data) -> None:
    """Via a temp file + atomic rename: a torn file would read back empty."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


class Calendar:
    """The feed, fetched on a timer, kept per week at <folder>/<week-start>.json, served by range."""

    def __init__(self, folder: Path, fetch=None, now=time.time):
        self.folder = Path(folder)
        self.fetch = fetch          # url -> bytes; None: never fetch (the stored weeks are still served)
        self.now = now
        self.weeks: dict[str, list[dict]] = {}
        self.ok, self.fetched_at, self.error, self.last_try = False, None, None, 0.0
        self.folder.mkdir(parents=True, exist_ok=True)
        for p in sorted(self.folder.glob(WEEK_FILES)):
            try:
                v = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(v, list):
                self.weeks[p.stem] = v
        try:
            st = json.loads((self.folder / "state.json").read_text())
            self.ok, self.fetched_at, self.error = bool(st.get("ok")), st.get("fetched_at"), st.get("error")
            self.last_try = float(st.get("last_try") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _save_state(self) -> None:
        _write_json(self.folder / "state.json", {"ok": self.ok, "fetched_at": self.fetched_at,
                                                  "error": self.error, "last_try": self.last_try})

    def wait_s(self) -> float:
        """Seconds until the next fetch is due: an hour after a good one, 30 minutes after a failed one."""
        return max(0.0, self.last_try + (EVERY_S if self.ok else MIN_GAP_S) - self.now())

    def refresh(self) -> bool:
        """One fetch (run it in a worker thread: it may block 10 s). Refused (False) without a fetch function
        or within 30 minutes of the last try. A good week replaces its file; a failure keeps the last good data
        and records why."""
        now = self.now()
        if self.fetch is None or now - self.last_try < MIN_GAP_S:
            return False
        self.last_try = now
        self._save_state()          # the floor holds even if this process dies mid-fetch
        try:
            events = parse(json.loads(self.fetch(FF_URL)))
            if not events:
                raise ValueError("the feed has no events")
        except Exception as e:  # noqa: BLE001 — any failure keeps the last good week
            self.ok, self.error = False, f"{type(e).__name__}: {e}"[:200]
            self._save_state()
            return False
        week = week_start(events[0]["t_ms"]).isoformat()
        self.weeks[week] = events
        _write_json(self.folder / f"{week}.json", events)
        self.ok, self.error, self.fetched_at = True, None, int(now * 1000)
        self._save_state()
        return True

    def events(self, frm: int, to: int, countries=None) -> list[dict]:
        """Every stored week's events with frm <= t_ms < to (and a country in `countries`, any case), by time."""
        want = {str(c).upper() for c in countries} if countries else None
        seen, out = set(), []
        for week in sorted(self.weeks):
            for e in self.weeks[week]:
                t = e.get("t_ms") if isinstance(e, dict) else None
                key = (t, e.get("country"), e.get("title")) if t is not None else None
                if not isinstance(t, int) or key in seen or not frm <= t < to:
                    continue
                if want is not None and str(e.get("country", "")).upper() not in want:
                    continue
                seen.add(key)
                out.append(e)
        out.sort(key=lambda e: e["t_ms"])
        return out

    def status(self) -> dict:
        return {"ok": self.ok, "fetched_at": self.fetched_at, "error": self.error}
```

- [ ] **Step 4: `server.py`.** Import `from .calendar import Calendar`. Give `create_app` a new keyword argument `calendar_fetch=None`, added after `state: Path | None = None`. After `drawings_path = …`, add:

```python
    # ForexFactory's calendar; calendar_fetch None never fetches (tests); python -m homebase.charts passes http_get
    cal = Calendar(sd / "calendar", fetch=calendar_fetch)
```

In `status()`, before `return st`, add `st["calendar"] = cal.status()`. After `pump()`, add:

```python
    async def calendar_loop() -> None:
        """The calendar at startup, then hourly (30 min after a failure); never faster: FF blocks polling."""
        while True:
            try:
                await asyncio.to_thread(cal.refresh)
            except Exception as e:  # noqa: BLE001 — the calendar must never take the service down
                log(f"calendar: {type(e).__name__}: {e}")
            await asyncio.sleep(max(cal.wait_s(), 60.0))    # not the `sleep` seam: tests patch it to 0
```

In `lifespan`, after `tasks = [...]`, add `if calendar_fetch is not None: tasks.append(asyncio.create_task(calendar_loop()))`. Add the route next to the templates routes:

```python
    @app.get("/api/calendar")
    async def api_calendar(request: Request):
        q = request.query_params
        try:
            frm, to = int(q.get("from", 0)), int(q.get("to", 2 ** 62))
        except ValueError:
            raise HTTPException(400, "from / to: epoch ms") from None
        countries = [c.strip() for c in q.get("countries", "").split(",") if c.strip()]
        return cal.events(frm, to, countries or None)
```

In `homebase/charts/__main__.py`, import `from .calendar import http_get`, and pass `calendar_fetch=http_get` to `create_app(…)`.

- [ ] **Step 5: Run the server tests**

Run: `.venv/bin/python -m pytest tests/test_charts_calendar.py -q`, then `.venv/bin/python -m pytest -q`
Expected: PASS. The other server tests are unchanged, because they build the app without `calendar_fetch`, so no loop runs.

- [ ] **Step 6: Write the failing Node tests.** Create `tests/js/events.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const E = require('../../homebase/static/charts/events.js');

const at = (h, m, d = 22) => Date.UTC(2026, 8, d, h + 4, m);    // an ET (EDT) wall time on 2026-09-d, as epoch ms
const ev = (title, h, m, impact, country = 'USD', extra = {}) =>
  ({ t_ms: at(h, m), title, country, impact, forecast: '', previous: '', ...extra });
const CPI = ev('CPI m/m', 8, 30, 'High', 'USD', { forecast: '0.3%', previous: '0.2%' });
const CORE = ev('Core CPI m/m', 8, 30, 'High', 'USD', { forecast: '0.3%', previous: '0.3%' });
const IFO = ev('German ifo Business Climate', 4, 0, 'Medium', 'EUR');
const OIL = ev('Crude Oil Inventories', 10, 30, 'Low');
const HOL = ev('Bank Holiday', 0, 0, 'Holiday', 'JPY');
const OPEC = ev('OPEC Meetings', 3, 0, 'Non-Economic', 'ALL');
const SET = { evHigh: true, evMedium: true, evLow: false, evHoliday: false, evCountries: ['USD'] };

test('a chart shows the impacts it ticks, in the currencies it picks', () => {
  const all = [HOL, OPEC, IFO, CPI, CORE, OIL];
  assert.deepEqual(E.shown(all, SET).map((e) => e.title), ['CPI m/m', 'Core CPI m/m']);
  assert.deepEqual(E.shown(all, { ...SET, evLow: true, evCountries: ['usd', 'EUR'] }).map((e) => e.title),
    ['German ifo Business Climate', 'CPI m/m', 'Core CPI m/m', 'Crude Oil Inventories']);
  assert.deepEqual(E.shown(all, { ...SET, evHoliday: true, evCountries: ['JPY', 'ALL'] }).map((e) => e.title),
    ['Bank Holiday', 'OPEC Meetings']);                            // Holiday covers Non-Economic too
  assert.deepEqual(E.shown(all, { ...SET, evCountries: [] }), []);
});

test('flags: one per event time, merged when closer than a flag, coloured by the highest impact', () => {
  const x = (t) => (t - at(0, 0)) / 60000;                            // 1 px per minute from midnight ET
  const late = { ...OIL, title: 'Late', t_ms: at(10, 36) };
  const flags = E.layout([OIL, CPI, CORE, IFO, late], x, 2000);
  assert.deepEqual(flags.map((f) => [f.x, f.events.map((e) => e.title), f.color, f.line]), [
    [240, ['German ifo Business Climate'], '#FF9800', false],
    [510, ['CPI m/m', 'Core CPI m/m'], '#F23645', true],
    [630, ['Crude Oil Inventories', 'Late'], '#F7C600', false],      // 6 px apart: one flag
  ]);
  assert.equal(E.layout([CPI], () => null, 2000).length, 0);          // not on this chart
  assert.equal(E.layout([CPI], () => 2100, 2000).length, 0);          // off the pane
  assert.deepEqual(E.COLORS, { High: '#F23645', Medium: '#FF9800', Low: '#F7C600', Holiday: '#9598A1', 'Non-Economic': '#9598A1' });
  assert.equal(E.FLAG, 10);
});

test('a flag is hit within its radius + 2 px', () => {
  const flags = [{ x: 100, events: [CPI] }, { x: 140, events: [OIL] }];
  assert.equal(E.flagAt(flags, { x: 104, y: 293 }, 290), flags[0]);
  assert.equal(E.flagAt(flags, { x: 108, y: 290 }, 290), null);
  assert.equal(E.flagAt(flags, { x: 140, y: 296 }, 290), flags[1]);
  assert.equal(E.flagAt(flags, { x: 140, y: 298 }, 290), null);
});

test('the tooltip: one line per event, the time in the chart\'s zone', () => {
  assert.equal(E.tipLine(CPI, 'exchange'), '08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%');
  assert.equal(E.tipLine(OIL, 'exchange'), '10:30 Crude Oil Inventories · USD · Low');
  assert.equal(E.tipLine(CPI, 'utc'), '12:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%');
  assert.deepEqual(E.tipLines({ events: [CPI, CORE] }, 'exchange'), [
    '08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%',
    '08:30 Core CPI m/m · USD · High · forecast 0.3% · prev 0.3%',
  ]);
});

test('the status bar: the next event shown, "(in 2h 14m)", coloured by impact; none left: hidden', () => {
  const now = at(6, 16);
  assert.deepEqual(E.nextText([IFO, CPI, CORE, OIL], now), { text: 'Next USD: CPI m/m 08:30 (in 2h 14m)', color: '#F23645' });
  assert.equal(E.nextText([IFO, CPI], at(8, 30)), null);             // at its time it is gone
  assert.equal(E.nextText([], now), null);
  assert.equal(E.nextText([{ ...CPI, t_ms: now + 8 * 86400000 }], now), null);   // not this week
  assert.deepEqual([20000, 59 * 60000, 3600000, 134 * 60000, 27 * 3600000, 48 * 3600000].map(E.fmtIn),
    ['1m', '59m', '1h', '2h 14m', '1d 3h', '2d']);
});
```

In `tests/js/settings.test.mjs`, append:

```js
test('the Events fields: High and Medium on, USD, lines on; currencies cleaned and sorted', () => {
  const d = S.DEFAULTS;
  assert.deepEqual([d.evHigh, d.evMedium, d.evLow, d.evHoliday, d.evLines], [true, true, false, false, true]);
  assert.deepEqual(d.evCountries, ['USD']);
  assert.deepEqual(S.normalize({ evCountries: ['eur', 'USD', 'usd', 'All', 7, 'toolong', ' gbp '] }).evCountries,
    ['ALL', 'EUR', 'GBP', 'USD']);
  assert.deepEqual(S.normalize({ evCountries: 'USD' }).evCountries, ['USD']);
  assert.deepEqual(S.normalize({ evCountries: [] }).evCountries, []);
  assert.deepEqual(S.overrides({ evCountries: ['usd'] }), {});
  assert.deepEqual(S.overrides({ evCountries: ['USD', 'EUR'], evLow: true }), { evLow: true, evCountries: ['EUR', 'USD'] });
  const n = S.normalize({});
  n.evCountries.push('JPY');                                       // a copy: the defaults never change
  assert.deepEqual(S.DEFAULTS.evCountries, ['USD']);
});
```

Run: `node --test tests/js/events.test.mjs tests/js/settings.test.mjs`
Expected: FAIL. `events.js` is missing, and `DEFAULTS.evHigh` is undefined.

- [ ] **Step 7: `settings.js`, the Events fields.** Append to `FIELDS` (after `color('scaleLines')`):

```js
  // Events (the economic calendar)
  bool('evHigh', true), bool('evMedium', true), bool('evLow', false), bool('evHoliday', false),
  { key: 'evCountries', type: 'list', def: Object.freeze(['USD']) },   // currency codes, upper-case, sorted
  bool('evLines', true),
```

In `normalize`, add this branch before `else if (v !== null) {`:

```js
    else if (f.type === 'list') {
      x = Array.isArray(v) ? [...new Set(v.filter((c) => typeof c === 'string').map((c) => c.trim().toUpperCase())
        .filter((c) => /^[A-Z]{2,5}$/.test(c)))].sort() : [...f.def];
    }
```

In `overrides`, compare lists by value:

```js
function overrides(full) {
  const n = normalize(full), out = {};
  for (const f of FIELDS) {
    const same = Array.isArray(f.def) ? JSON.stringify(n[f.key]) === JSON.stringify(f.def) : n[f.key] === f.def;
    if (!same) out[f.key] = n[f.key];
  }
  return out;
}
```

- [ ] **Step 8: `events.js`** (new, pure):

```js
/* Homebase Charts — the economic calendar on the charts (ForexFactory's "folders"). Pure: which events a
   chart shows (its Events settings), where their flags go (events at one time, or closer than a flag, share
   one), what a flag's tooltip and the status bar say. No browser globals at load time: the Node tests load
   this file directly. */
(function () {
'use strict';
const S = (typeof window !== 'undefined' && window.HBSettings) || (typeof require === 'function' ? require('./settings.js') : null);
const COLORS = Object.freeze({ High: '#F23645', Medium: '#FF9800', Low: '#F7C600', Holiday: '#9598A1', 'Non-Economic': '#9598A1' });
const RANK = { High: 3, Medium: 2, Low: 1, Holiday: 0, 'Non-Economic': 0 };
const FLAG = 10;   // px: a flag's diameter

/* The events a chart shows: its impact checkboxes (Holiday also covers Non-Economic) and currencies (any case). */
function shown(events, s) {
  const on = { High: s.evHigh, Medium: s.evMedium, Low: s.evLow, Holiday: s.evHoliday, 'Non-Economic': s.evHoliday };
  const cc = new Set((s.evCountries || []).map((c) => String(c).toUpperCase()));
  return (events || []).filter((e) => on[e.impact] && cc.has(String(e.country).toUpperCase()));
}

/* The flags along the time axis, left to right: [{x, t_ms, events, color, line}]. Events at one time share a
   flag, and a flag closer than FLAG px to the previous one joins it (zoomed out). color: the highest impact's;
   line: a High event is in it. xOf(t_ms) -> px | null (null: no place on this chart); off-pane flags go. */
function layout(events, xOf, width) {
  const pts = [];
  for (const e of events) {
    const x = xOf(e.t_ms);
    if (x == null || x < -FLAG / 2 || x > width + FLAG / 2) continue;
    pts.push({ x, e });
  }
  pts.sort((a, b) => a.x - b.x || a.e.t_ms - b.e.t_ms);
  const out = [];
  for (const { x, e } of pts) {
    const g = out[out.length - 1];
    if (g && (e.t_ms === g.t_ms || x - g.x < FLAG)) g.events.push(e);
    else out.push({ x, t_ms: e.t_ms, events: [e] });
  }
  for (const g of out) {
    const top = g.events.reduce((a, b) => ((RANK[b.impact] || 0) > (RANK[a.impact] || 0) ? b : a));
    g.color = COLORS[top.impact] || COLORS.Holiday;
    g.line = g.events.some((e) => e.impact === 'High');
  }
  return out;
}

/* The flag under a pane point (the flags' centres sit at y): within FLAG / 2 + 2 px. */
function flagAt(flags, pt, y) {
  for (const g of flags) if (Math.hypot(pt.x - g.x, pt.y - y) <= FLAG / 2 + 2) return g;
  return null;
}

const hhmm = (t, tz) => new Date(S.wallSeconds(t, tz) * 1000).toISOString().slice(11, 16);

/* "08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%": the time in the chart's zone (a TIMEZONES value). */
function tipLine(e, tz) {
  return [`${hhmm(e.t_ms, tz)} ${e.title}`, e.country, e.impact, e.forecast ? `forecast ${e.forecast}` : '',
    e.previous ? `prev ${e.previous}` : ''].filter(Boolean).join(' · ');
}
function tipLines(flag, tz) { return flag.events.map((e) => tipLine(e, tz)); }

/* "59m" · "2h 14m" · "1d 3h": the time left, rounded up to the minute (never "0m"). */
function fmtIn(ms) {
  const m = Math.max(1, Math.ceil(ms / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

/* The status bar: the next event among `events` (a chart's shown ones), "Next USD: CPI m/m 08:30 (in 2h 14m)"
   in ET, with its impact's colour; null when none is left within 7 days (the feed holds this week only). */
function nextText(events, nowMs) {
  const next = (events || []).filter((e) => e.t_ms > nowMs && e.t_ms - nowMs <= 7 * 86400000)
    .sort((a, b) => a.t_ms - b.t_ms || (RANK[b.impact] || 0) - (RANK[a.impact] || 0))[0];
  if (!next) return null;
  return { text: `Next ${next.country}: ${next.title} ${hhmm(next.t_ms, 'exchange')} (in ${fmtIn(next.t_ms - nowMs)})`,
    color: COLORS[next.impact] || COLORS.Holiday };
}

const api = { COLORS, FLAG, shown, layout, flagAt, tipLine, tipLines, fmtIn, nextText };
if (typeof window !== 'undefined') window.HBEvents = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

Run: `node --test tests/js/*.test.mjs`
Expected: PASS.

- [ ] **Step 9: `primitives.js`, the flags layer.** Insert before `window.HBLayers = …` and add `EventFlags` to the export:

```js
/* The economic calendar: a 10 px flag per event time at the bottom of the price pane (ForexFactory's folder
   colours) and, for High events, a 1 px dotted line in the event's colour through the pane. read() -> {events,
   xOf, lines} | null is asked before every render (the bars and settings live in the cell); `flags` and
   `flagY` stay for the page's hover test. Layout and colours: HBEvents. */
class EventFlags extends Layer {
  constructor(P, read) {
    super(P);
    this.read = read; this.flags = []; this.lines = false; this.flagY = 0;
    this._views = [
      { zOrder: () => 'bottom', renderer: () => ({ draw: (t) => this.drawLines(t) }) },
      { zOrder: () => 'top', renderer: () => ({ draw: (t) => this.drawFlags(t) }) },
    ];
  }
  updateAllViews() {
    const r = this.chart ? this.read() : null;
    this.lines = !!(r && r.lines);
    this.flags = r ? window.HBEvents.layout(r.events, r.xOf, this.chart.timeScale().width()) : [];
  }
  drawLines(target) {
    if (!this.lines || !this.flags.some((g) => g.line)) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.lineWidth = 1;
      ctx.strokeStyle = window.HBEvents.COLORS.High;
      ctx.setLineDash([1, 3]);
      for (const g of this.flags) {
        if (!g.line) continue;
        const x = Math.round(g.x) + 0.5;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, mediaSize.height); ctx.stroke();
      }
      ctx.setLineDash([]);
    });
  }
  drawFlags(target) {
    if (!this.flags.length) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const r = window.HBEvents.FLAG / 2;
      this.flagY = mediaSize.height - r - 3;
      ctx.lineWidth = 1;
      ctx.strokeStyle = this.P.bg;
      for (const g of this.flags) {
        ctx.beginPath(); ctx.arc(g.x, this.flagY, r, 0, Math.PI * 2);
        ctx.fillStyle = g.color; ctx.fill(); ctx.stroke();
      }
    });
  }
}
```

- [ ] **Step 10: `cell.js`, the layer and the tooltip.**
- Add `EventFlags` to the `window.HBLayers` destructuring.
- In the constructor's `slot.innerHTML`, after the `.legend` div, add `<div class="ev-tip" role="tooltip" hidden></div>`.
- After `this.box = …`, add `this.evTip = slot.querySelector('.ev-tip');`.
- After the `lg.inds` click listener, add:

```js
    this.box.addEventListener('pointermove', (e) => this.onEventHover(e));
    this.box.addEventListener('pointerleave', () => { this.evTip.hidden = true; });
```

In `makeChart()`, add `this.evl = new EventFlags(P, () => this.eventsNow());` next to the other layers and append `this.evl` to the attach list (after `this.cd`). Also change the visible-range subscription to `this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => { this.syncFootprint(); this.evTip.hidden = true; });`: a wheel scroll or zoom moves the flags out from under a shown tooltip, and no pointermove comes to hide it. In `teardown()`, null `this.evl`; in the constructor fields, add `this.evl = null;`. In `applySettings()`, after `if (this.cd) this.cd.redraw();`, add `this.redrawEvents();`. Add the methods:

```js
  /* What the calendar layer draws now: the events this chart shows (its Events settings) and where. A tick,
     volume or range chart has no place for an event outside its bars. */
  eventsNow() {
    const n = this.bars.length;
    if (!n || !this.chart) return null;
    const ts = this.chart.timeScale(), time = this.isTime(), first = this.bars[0].ms, last = this.bars[n - 1].ms;
    const ctx = { bars: this.bars, isTime: time, barMs: this.barMs(), coord: (i) => ts.logicalToCoordinate(i) };
    const xOf = (t) => (!time && (t < first || t > last) ? null : window.HBDrawings.timeToX(t, ctx));
    return { events: window.HBEvents.shown(this.host.events(), this.R), xOf, lines: this.R.evLines };
  }

  redrawEvents() { if (this.evl) this.evl.redraw(); }

  /* Hovering a calendar flag: its events in a tooltip above it (times in the chart's zone). */
  onEventHover(e) {
    const tip = this.evTip, L = this.evl;
    if (!L || e.buttons || !L.flags.length) { tip.hidden = true; return; }
    const r = this.box.getBoundingClientRect();
    const g = window.HBEvents.flagAt(L.flags, { x: e.clientX - r.left, y: e.clientY - r.top }, L.flagY);
    if (!g) { tip.hidden = true; return; }
    tip.replaceChildren(...window.HBEvents.tipLines(g, this.R.timezone).map((s) => mk('div', '', s)));
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.max(4, Math.min(g.x - w / 2, this.box.clientWidth - w - 4))}px`;
    tip.style.top = `${Math.max(4, L.flagY - 12 - h)}px`;
  }
```

In the header's host list, add `events()`.

- [ ] **Step 11: `settings-dialog.js`, the Events tab.** Append to `TABS` (last, after Canvas):

```js
  { id: 'events', label: 'Events', icon: 'calendar', sections: [
    ['ECONOMIC CALENDAR', [
      { label: 'High', check: 'evHigh', dot: '#F23645' },
      { label: 'Medium', check: 'evMedium', dot: '#FF9800' },
      { label: 'Low', check: 'evLow', dot: '#F7C600' },
      { label: 'Holiday', check: 'evHoliday', dot: '#9598A1' },
      { label: 'Currencies', chips: 'evCountries' },
      { label: 'Vertical lines for high impact', check: 'evLines' },
    ]],
  ] },
```

In `row(r)`, after the checkbox block (before `name.append(mk('span', '', r.label));`), add the colour dot:

```js
    if (r.dot) { const d = mk('i', 'set-dot'); d.style.background = r.dot; name.append(d); }
```

After the `r.number` block, add the currencies multi-select:

```js
    if (r.chips) {   // a multi-select: one checkbox per currency in the feed (plus any already picked)
      const key = r.chips, picked = new Set(work[key]), wrap = mk('div', 'set-chips');
      const all = [...new Set([...(host.countries ? host.countries() : []), ...work[key]])].sort();
      for (const c of all) {
        const lab = mk('label', 'set-chip'), cb = mk('input');
        cb.type = 'checkbox';
        cb.checked = picked.has(c);
        cb.onchange = () => set(key, cb.checked ? [...work[key], c] : work[key].filter((x) => x !== c));
        lab.append(cb, mk('span', '', c));
        wrap.append(lab);
      }
      if (!all.length) wrap.append(mk('span', 'set-unit', 'No calendar loaded yet'));
      ctl.append(wrap);
      el.classList.add('tall');
    }
```

Extend the header's host list with `countries()`, and the TABS row comment with `dot?: colour, chips?: key (a multi-select of host.countries())`.

- [ ] **Step 12: `app.js`.** Add to the state: `let calendar = [];   // every stored calendar event (GET /api/calendar), by time` and `let calendarAt;   // the service's calendar.fetched_at they came with (undefined: never loaded)`. Add a `/* ---- economic calendar ---- */` section:

```js
/* The calendar from the chart service: loaded once, then again whenever the service fetched anew. */
async function loadCalendar() {
  try {
    const r = await fetch('/api/calendar');
    if (!r.ok) return;
    const v = await r.json();
    calendar = Array.isArray(v) ? v : [];
  } catch (_) { return; }
  for (const c of cells) c.redrawEvents();
  renderNextEvent();
}

/* Now in epoch ms: a replay's clock in a replay (so its "Next" matches its charts), else the browser's. */
function clockMs() {
  const et = clockEt();
  return replayClock ? et - S.zoneOffsetMs('America/New_York', et) : Date.now();
}

/* The status bar's "Next USD: CPI m/m 08:30 (in 2h 14m)": the next event the selected chart shows. */
function renderNextEvent() {
  const el = $('#sbEvent'), c = cur(), E = window.HBEvents;
  const n = c ? E.nextText(E.shown(calendar, c.R), clockMs()) : null;
  el.hidden = !n;
  if (n) { el.textContent = n.text; el.style.color = n.color; }
}
```

Make these one-line changes:
- In `hostFor(id)`, add `events: () => calendar,`.
- In `chartSettings()`'s host, add `countries: () => [...new Set(calendar.map((e) => e.country))].sort(),`.
- In `showStatus(s)`, after the replay-clock lines, add `if (s.calendar && s.calendar.fetched_at !== calendarAt) { calendarAt = s.calendar.fetched_at; loadCalendar(); }`.
- In `tick()`, add `renderNextEvent();` at the end.

- [ ] **Step 13: Shell, styles, icon.**
- `charts.html`:
  - In the status bar, between `#sbNote` and `#sbClock`, insert `<span class="sb-event" id="sbEvent" hidden></span>`.
  - Add `<script src="/static/charts/events.js?v=3"></script>` right after `settings.js`.
- `icons.js`: add `calendar` to the header list and `calendar: svg('<path d="M8 2v3"/><path d="M16 2v3"/><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/>'),`.
- `charts.css`: append:

```css
.sb-event { font-weight: 600; }
.ev-tip { position: absolute; z-index: 7; padding: 6px 8px; border-radius: 6px; background: var(--tip); color: #FFFFFF;
  font-size: 12px; line-height: 16px; white-space: nowrap; pointer-events: none; font-variant-numeric: tabular-nums; }
.set-dot { flex: none; width: 10px; height: 10px; border-radius: 50%; }
.set-row.tall { height: auto; min-height: 40px; padding: 8px 0; align-items: start; }
.set-chips { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 12px; }
.set-chip { display: inline-flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums; }
.set-chip input { width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }
```

- [ ] **Step 14: Syntax-check and run the suites**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green.

- [ ] **Step 15: Commit**

```bash
git add homebase/charts/calendar.py homebase/charts/server.py homebase/charts/__main__.py tests/test_charts_calendar.py homebase/static/charts/events.js tests/js/events.test.mjs homebase/static/charts/settings.js tests/js/settings.test.mjs homebase/static/charts/settings-dialog.js homebase/static/charts/primitives.js homebase/static/charts/cell.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js
git commit -m "feat(charts): ForexFactory economic calendar — flags, high-impact lines and tooltips on the charts, next-event countdown, Events settings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check.** The replay launch entry builds its app through `python -m homebase.charts`, so it fetches the real feed once at startup; that is one request, within the floor.
- `/api/status` shows `calendar.ok: true` and `homebase/.state/charts/calendar/<Sunday>.json` exists.
- On NQ 1m / 5m and on D: 10 px flags sit at the bottom of the price pane at each USD High / Medium event time, red and orange. High events also get a dotted red line through the pane. Several events at one time share a flag.
- Hovering a flag shows e.g. `08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%`, one line per event, in the chart's time zone (switch Timezone to UTC and the times move).
- The status bar reads `Next USD: … (in 2h 14m)` in the impact's colour for the selected chart's settings, on the replay clock in a replay. It is hidden when nothing is left.
- Settings → Events:
  - Low and Holiday add yellow and grey flags.
  - The currencies list the feed's countries; ticking EUR adds EUR events.
  - `Vertical lines for high impact` off removes the lines.
  - Each chart keeps its own choice, and a saved layout keeps it.
- On a tick chart, flags appear only inside its bars. Dark theme works; zero console errors.

---
### Task 9: Deep history — deeper default load, scroll-back through the whole tick archive, "Start of data", the cache warm-up command

**Files:**
- Modify: `homebase/charts/hub.py` (`sessions_back` defaults, `warm_bars`, `Hub.stream_of`, `Hub.older`)
- Modify: `homebase/charts/history.py` (`bars(…, memo=)`, `cached`)
- Modify: `homebase/charts/server.py` (the `older` socket message)
- Create: `homebase/charts/warm.py`
- Modify: `tests/charts_util.py` (`weekdays_before`)
- Modify: `tests/test_charts_hub.py`, `tests/test_charts_server.py`
- Create: `tests/test_charts_warm.py`
- Create: `homebase/static/charts/scrollback.js` (`HBScrollBack`, pure)
- Create: `tests/js/scrollback.test.mjs`
- Modify: `homebase/static/charts/cell.js`, `homebase/static/charts/primitives.js` (`Start`), `homebase/static/charts/app.js`, `homebase/static/charts.html`

**Interfaces:**
- Consumes:
  - Existing: `History.bars/info/minutes`, `TickStore.sessions/pick`, `Stream` (`root`, `spec`, `studies`, `tick_size`, `subs`), `make`, `HISTORY_MAX`, `session_date`, `Bar.wire`, `Conn.send`, and the ws loop.
  - Page: Task 6's `Cell.append`, `candleData`, `realT`, `setView`/`viewNow`; Task 7's `Cell.syncEth()`; Task 8's `Cell.evTip` and the range subscription it edits; existing `drawMarkers`, `drawGaps`, `syncFootprint`, `legend`, `dc.refresh`, `lines`, `point`.
- Produces:
  - `sessions_back(spec)`: 1 (sub-minute, tick, volume, range) · 5 (≤ 5m) · 20 (≤ 1h) · 250 (> 1h). It is also one scroll-back chunk's size.
  - `warm_bars(key) -> int`.
  - `Hub.stream_of(sub) -> Stream | None`.
  - `Hub.older(s, before_ms) -> {bars, studies, repair, sessions, done}`.
  - `History.bars(root, spec, d, memo=True)` and `History.cached(root, d) -> bool`.
  - `homebase.charts.warm`: `warm(roots, since=None, *, base, cache_dir, today, out) -> {built, skipped}`, `parse_args(argv)`, `main(argv)`.
  - Wire (R12): the page sends `{"op": "older", "id", "before": first bar ms}`. The server answers `{"type": "older", "id", "before", "bars", "studies", "repair", "sessions", "done"}`, or `{"type": "older", "id", "before", "error"}`, one at a time per chart.
  - `window.HBScrollBack`: `ScrollBack({edge = 50, retryMs = 10000, now})` with `reset()`, `want(range, firstMs) -> {before}|null`, `sent(req)`, `take(m) -> bool`, `done`; plus `prepend(bars, m) -> bars` and `mergeSessions(older, sessions)`.
  - `HBLayers.Start` (`set(on)`).
  - `Cell.back`, `Cell.start`, `Cell.askOlder(range)`, `Cell.onOlder(m)`.
- No earlier task's interface changes. The calendar layer (Task 8) reads the chart's bars at every render, so it follows a prepend by itself.

- [ ] **Step 1: A test helper.** Append to `tests/charts_util.py`:

```python
def weekdays_before(d: dt.date, n: int) -> list[dt.date]:
    """The n weekdays before d, oldest first (a classic root files weekend prints into Monday)."""
    out, x = [], d
    while len(out) < n:
        x -= dt.timedelta(days=1)
        if x.weekday() < 5:
            out.append(x)
    return out[::-1]
```

- [ ] **Step 2: Write the failing hub tests.** In `tests/test_charts_hub.py`, change the imports to:

```python
import homebase.charts.hub as hub_mod
from homebase.charts.bars import Bar, BarBuilder, BarSpec
from homebase.charts.history import History
from homebase.charts.hub import Hub, Stream, sessions_back, warm_bars
from homebase.charts.store import TickStore
from homebase.charts.studies import make
from homebase.charts.tick import SideClassifier, from_row
from tests.charts_util import D, rows, session_ms, weekdays_before, write_archive
```

Append:

```python
# ---- deep history: scroll-back chunks (spec §5) ----
def deep(tmp_path, n=8):
    """A hub over n completed weekday sessions before D (3 one-minute bars each, 09:30-09:32; session k
    trades around 100 + k) with D's first minutes as today's tape."""
    base = tmp_path / "ticks"
    days = weekdays_before(D, n)
    for k, d in enumerate(days):
        write_archive(base, "NQ", d, "NQZ6", rows(session_ms(d, 9, 30), [100 + k + 0.25 * (i % 4) for i in range(9)],
                                                  step_ms=20_000, first_id=1000 * (k + 1)))
    hub = Hub(History(TickStore(base), cache_dir=tmp_path / "cache"), lambda: session_ms(D, 9, 31))
    hub.start_today("NQ", D, ticks_of(rows(session_ms(D, 9, 30), [200 + 0.25 * (i % 5) for i in range(30)],
                                           first_id=90_000)))
    return hub, days


def test_the_default_depth_per_bar_type():
    assert [sessions_back(BarSpec(k, n)) for k, n in (("time", 5), ("time", 30), ("tick", 500), ("volume", 2000),
                                                        ("range", 10))] == [1, 1, 1, 1, 1]
    assert [sessions_back(BarSpec("time", n)) for n in (60, 300, 600, 3600, 14400, 86400)] == [5, 5, 20, 20, 250, 250]
    assert [warm_bars(k) for k in ("sma:50", "vwma:20", "ema:20", "adx:14", "vwap", "vwap:rth", "cumdelta",
                                   "levels")] == [50, 20, 100, 140, 0, 0, 0, 0]


def test_older_is_the_next_chunk_strictly_before_the_first_bar_and_ends_at_the_archive_start(tmp_path):
    hub, days = deep(tmp_path)                       # 8 sessions: the chart loads the newest 5
    s = open_stream(hub, keys=("ema:3", "vwap"))
    first = s.bars[0]
    assert first.session == days[3].isoformat()
    ans = hub.older(s, first.t)
    assert [x["date"] for x in ans["sessions"]] == [d.isoformat() for d in days[:3]]
    assert [b["s"] for b in ans["bars"]] == [d.isoformat() for d in days[:3] for _ in range(3)]
    assert all(b["ms"] < first.t for b in ans["bars"]) and ans["done"] is True
    assert set(ans["studies"]) == {"ema:3", "vwap"} and len(ans["studies"]["vwap"]) == 9


def test_older_walks_back_one_chunk_at_a_time(tmp_path):
    hub, days = deep(tmp_path, n=12)
    s = open_stream(hub)
    a = hub.older(s, s.bars[0].t)
    assert [x["date"] for x in a["sessions"]] == [d.isoformat() for d in days[2:7]] and a["done"] is False
    b = hub.older(s, a["bars"][0]["ms"])
    assert [x["date"] for x in b["sessions"]] == [d.isoformat() for d in days[:2]] and b["done"] is True
    c = hub.older(s, b["bars"][0]["ms"])
    assert c["bars"] == [] and c["sessions"] == [] and c["done"] is True


def test_older_respects_history_max_and_repairs_a_session_it_cuts(tmp_path, monkeypatch):
    hub, days = deep(tmp_path)
    s = open_stream(hub, keys=("vwap",))
    monkeypatch.setattr(hub_mod, "HISTORY_MAX", 4)
    a = hub.older(s, s.bars[0].t)                    # all of days[2] + the newest bar of days[1]
    assert [b["s"] for b in a["bars"]] == [days[1].isoformat()] + [days[2].isoformat()] * 3
    assert [x["date"] for x in a["sessions"]] == [days[1].isoformat(), days[2].isoformat()] and a["done"] is False
    b = hub.older(s, a["bars"][0]["ms"])             # the rest of days[1], then the newest 2 bars of days[0]
    assert [x["s"] for x in b["bars"]] == [days[0].isoformat()] * 2 + [days[1].isoformat()] * 2
    # the join is inside days[1]: its VWAP restarts only at the session's open, so the chart's days[1] bar
    # (which came first, alone) gets the value a whole-session run gives it
    vwap = make("vwap")
    want = [vwap.push(x) for x in hub.history.bars("NQ", M1, days[1])]
    assert b["repair"]["vwap"] == want[2:3]


def test_older_studies_run_on_across_the_join(tmp_path):
    """The chunk's values are a fresh run over it; `repair` continues that run through the chart's first bars
    for as long as a study remembers (ema:3 -> 15 bars; the longest wins): together, a full reload of the
    longer range."""
    hub, days = deep(tmp_path)
    s = open_stream(hub, keys=("ema:3", "sma:2", "vwap"))
    ans = hub.older(s, s.bars[0].t)
    every = [b for d in days for b in hub.history.bars("NQ", M1, d)]     # all 8 completed sessions, oldest first
    for key in ("ema:3", "sma:2", "vwap"):
        st = make(key)
        want = [st.push(b) for b in every]
        assert ans["studies"][key] == want[:9], key
        assert ans["repair"][key] == want[9:24], key


def test_older_tick_bars_come_one_session_at_a_time(tmp_path):
    hub, days = deep(tmp_path)
    s = open_stream(hub, spec=BarSpec("tick", 5), keys=())
    assert s.bars[0].session == days[-1].isoformat()             # tick bars load one session back
    ans = hub.older(s, s.bars[0].t)
    assert [x["date"] for x in ans["sessions"]] == [days[-2].isoformat()]
    assert [b["n"] for b in ans["bars"]] == [5, 4] and ans["done"] is False


def test_older_never_returns_todays_session(tmp_path):
    hub, days = deep(tmp_path, n=3)
    s = open_stream(hub)
    ans = hub.older(s, session_ms(D, 9, 45))                     # a `before` inside today's session
    assert D.isoformat() not in {b["s"] for b in ans["bars"]}
    assert [x["date"] for x in ans["sessions"]] == [d.isoformat() for d in days] and ans["done"] is True


def test_older_leaves_the_history_memo_alone(tmp_path):
    hub, days = deep(tmp_path, n=12)
    s = open_stream(hub)
    kept = set(hub.history.memo)
    hub.older(s, s.bars[0].t)
    assert set(hub.history.memo) == kept


def test_a_chart_finds_its_stream(tmp_path):
    hub, _ = deep(tmp_path, n=2)
    s = open_stream(hub, sub=("conn", "c9"))
    assert hub.stream_of(("conn", "c9")) is s and hub.stream_of(("conn", "nope")) is None
```

- [ ] **Step 3: Write the failing server and warm-up tests.** In `tests/test_charts_server.py`, add `weekdays_before` to the `tests.charts_util` import and append:

```python
def test_a_chart_scrolls_back_over_the_socket(tmp_path):
    base, days = tmp_path / "ticks", weekdays_before(D, 7)
    for k, d in enumerate(days):
        write_archive(base, "NQ", d, "NQZ6", rows(session_ms(d, 9, 30), [100.0 + k + 0.25 * (i % 4) for i in range(9)],
                                                  step_ms=20_000, first_id=1000 * (k + 1)))
    write_archive(base, "NQ", D, "NQZ6", rows(session_ms(D, 9, 29), [200.0] * 120, first_id=90_000))
    app = create_app(roots=["NQ"], base=base, replay=D, speed=1, start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"op": "sub", "id": "c1", "root": "NQ", "spec": "time:60", "studies": ["ema:3"]})
        first = next_of(ws, "history")["bars"][0]
        assert first["s"] == days[2].isoformat()                      # the newest 5 of the 7 sessions
        ws.send_json({"op": "older", "id": "c1", "before": first["ms"]})
        ans = next_of(ws, "older")
        assert ans["id"] == "c1" and ans["before"] == first["ms"] and ans["done"] is True
        assert [b["s"] for b in ans["bars"]] == [days[0].isoformat()] * 3 + [days[1].isoformat()] * 3
        assert len(ans["studies"]["ema:3"]) == 6 and len(ans["repair"]["ema:3"]) == 15
        ws.send_json({"op": "older", "id": "nope", "before": first["ms"]})
        assert next_of(ws, "older")["error"] == "not subscribed"
        ws.send_json({"op": "older", "id": "c1", "before": "yesterday"})
        bad = next_of(ws, "older")
        assert bad["before"] == "yesterday" and "epoch ms" in bad["error"]
```

Create `tests/test_charts_warm.py`:

```python
"""The cache warm-up command: every completed session's 1-minute bars built once, built ones skipped, a
session whose ticks changed rebuilt, the archive only read."""
from __future__ import annotations

import datetime as dt
import os

from homebase.charts.warm import parse_args, warm
from tests.charts_util import D, rows, session_ms, weekdays_before, write_archive


def archive(tmp_path, n=3):
    base = tmp_path / "ticks"
    days = weekdays_before(D, n)
    for k, d in enumerate(days + [D]):                             # D: today, still being written
        write_archive(base, "NQ", d, "NQZ6", rows(session_ms(d, 9, 30), [100.0 + k] * 5, first_id=100 * (k + 1)))
    return base, days


def test_warm_builds_each_completed_session_once(tmp_path):
    base, days = archive(tmp_path)
    cache, said = tmp_path / "cache", []
    seen = {p: p.stat().st_mtime_ns for p in base.rglob("*")}
    assert warm(["NQ"], base=base, cache_dir=cache, today=D, out=said.append) == {"built": 3, "skipped": 0}
    assert len(list(cache.glob("*.m1.pkl"))) == 3                   # not today's
    assert warm(["NQ"], base=base, cache_dir=cache, today=D, out=said.append) == {"built": 0, "skipped": 3}
    assert warm(["NQ"], days[1], base=base, cache_dir=cache, today=D, out=said.append) == {"built": 0, "skipped": 2}
    assert {p: p.stat().st_mtime_ns for p in base.rglob("*")} == seen   # the archive is only read
    assert any(days[0].isoformat() in line and "NQ" in line for line in said)


def test_warm_rebuilds_a_session_whose_ticks_changed(tmp_path):
    base, days = archive(tmp_path)
    cache = tmp_path / "cache"
    warm(["NQ"], base=base, cache_dir=cache, today=D, out=lambda line: None)
    src = next((base / "NQ").rglob(f"{days[0].isoformat()}_*.csv.gz"))
    later = src.stat().st_mtime_ns + 5_000_000_000
    os.utime(src, ns=(later, later))                               # a refill rewrote that session's ticks
    assert warm(["NQ"], base=base, cache_dir=cache, today=D, out=lambda line: None) == {"built": 1, "skipped": 2}


def test_the_command_line():
    a = parse_args(["--roots", "nq,ES", "--since", "2021-09-22"])
    assert a.roots == ["NQ", "ES"] and a.since == dt.date(2021, 9, 22)
    a = parse_args([])
    assert a.since is None and "NQ" in a.roots                     # the chart service's roots
```

- [ ] **Step 4: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts_hub.py tests/test_charts_server.py tests/test_charts_warm.py -q`
Expected: ImportError (`sessions_back` still loads 3 sessions, and `warm_bars`, `homebase.charts.warm` do not exist).

- [ ] **Step 5: `history.py`.** Replace the cache path inside `minutes()` with `cp = self._cache_file(root, d, f)`, and add:

```python
    def _cache_file(self, root: str, d: dt.date, f) -> Path:
        return self.cache_dir / (f"v{CACHE_VERSION}_{root}_{d.isoformat()}_{f.contract}_"
                                 f"{'live' if f.live else 'arch'}.m1.pkl")

    def cached(self, root: str, d: dt.date) -> bool:
        """Is session d's 1-minute cache built and current (no older than its tick file)? True with no file."""
        f = self.store.pick(root, d)
        if f is None:
            return True
        try:
            return self._cache_file(root, d, f).stat().st_mtime_ns >= f.path.stat().st_mtime_ns
        except OSError:
            return False
```

Replace `bars()` with the version that can skip the memo:

```python
    def bars(self, root: str, spec: BarSpec, d: dt.date, memo: bool = True) -> list[Bar]:
        """Session d's bars of this type. memo=False (scroll-back): a memoized session is used, but a new
        build is not kept, so a deep scroll-back never evicts the open charts' sessions."""
        key = (root, spec.key, d)
        with self._lock:
            hit = self.memo.get(key)
            if hit is not None:
                self.memo.move_to_end(key)
                return hit
            gen = self._gen
        out = resample(self.minutes(root, d), spec) if spec.from_minutes else self._from_ticks(root, spec, d)
        if memo:
            with self._lock:
                if gen == self._gen:        # else a clear() landed mid-build: its file may have changed
                    self.memo[key] = out
                    while len(self.memo) > self.memo_max:
                        self.memo.popitem(last=False)
        return out
```

- [ ] **Step 6: `hub.py`.** Replace `sessions_back` and add `warm_bars` after it:

```python
def sessions_back(spec: BarSpec) -> int:
    """Completed sessions loaded behind today, per bar type; also the size of one scroll-back chunk."""
    if spec.kind != "time" or spec.size < 60:
        return 1
    if spec.size <= 300:
        return 5
    if spec.size <= 3600:
        return 20
    return 250


def warm_bars(key: str) -> int:
    """How many bars after a join a study's value still depends on the bars before it: a window's length, or
    long enough for an EMA's (5n) / a Wilder ADX's (10n) memory to fade below e^-10. 0: the study restarts
    every session (VWAP, cumulative delta, levels)."""
    name, _, n = str(key).partition(":")
    n = int(n) if n.isdecimal() else 0
    return {"sma": n, "vwma": n, "ema": 5 * n, "adx": 10 * n}.get(name, 0)
```

Add to `class Hub` (after `unsubscribe`):

```python
    def stream_of(self, sub: tuple) -> Stream | None:
        """The stream a chart (conn, chart id) is subscribed to."""
        return next((s for s in self.streams.values() if sub in s.subs), None)

    def older(self, s: Stream, before_ms: int) -> dict:
        """Worker thread: scroll-back. The next chunk of COMPLETED sessions strictly before before_ms (the
        page's first bar), newest first, until sessions_back(spec) sessions or HISTORY_MAX bars (a session
        that does not fit gives its newest bars; the next request continues before them). Built as a history
        message's bars are, but never memoized. Its studies run over it from a fresh start, as a history
        message's do, then on across the join through the page's first bars for as long as a study remembers
        what came before ("repair": the page overwrites those values). done: nothing older is left. Never
        today's session."""
        root, spec = s.root, s.spec
        keys = list(s.studies)
        today = self.today_date.get(root) or session_date(self.now_ms(), root)
        cut = session_date(before_ms, root)
        dates = [d for d in self.store.sessions(root) if d < today]
        back = [d for d in dates if d <= cut]
        chunk: list[Bar] = []
        infos: list[dict] = []
        taken, trimmed, i = 0, False, len(back)
        while i > 0 and taken < sessions_back(spec) and len(chunk) < HISTORY_MAX:
            i -= 1
            bs = [b for b in self.history.bars(root, spec, back[i], memo=False) if b.t < before_ms]
            if not bs:
                continue
            room = HISTORY_MAX - len(chunk)
            if len(bs) > room:
                bs, trimmed = bs[-room:], True
            chunk[:0] = bs
            infos.insert(0, self.history.info(root, back[i]))
            taken += 1
        # across the join: the page's first bars, as far as a study still remembers the chunk, and all of a
        # session the chunk ends inside (VWAP and cumulative delta restart only at a session's open)
        ahead: list[Bar] = []
        if chunk:
            mid = chunk[-1].session == cut.isoformat()
            rest = [b for b in self.history.bars(root, spec, cut, memo=False) if b.t >= before_ms] if mid else []
            span = min(max(len(rest), max((warm_bars(k) for k in keys), default=0)), HISTORY_MAX)
            for d in (x for x in dates if x >= cut):
                if len(ahead) >= span:
                    break
                ahead.extend(b for b in self.history.bars(root, spec, d, memo=False) if b.t >= before_ms)
            ahead = ahead[:span]
        studies, repair = {}, {}
        for k in keys:
            st = make(k)
            studies[k] = [st.push(b) for b in chunk]
            repair[k] = [st.push(b) for b in ahead]
        return {"bars": [b.wire(s.tick_size) for b in chunk], "studies": studies, "repair": repair,
                "sessions": infos, "done": i == 0 and not trimmed}
```

- [ ] **Step 7: `server.py`, the `older` message.** Import `Stream` (`from .hub import Hub, Stream`). Inside `create_app`, after `status()`, add:

```python
    older_busy: set = set()     # (conn, chart id) with a scroll-back chunk being built
    older_tasks: set = set()    # the answering tasks, referenced until they finish

    def ask_older(conn: Conn, cid: str, before) -> None:
        """A chart scrolled back to its first bar ({"op": "older", "id", "before": that bar's ms}): build the
        next chunk of older sessions off the loop and answer {"type": "older", "id", "before", "bars",
        "studies", "repair", "sessions", "done"}, or with an "error" (the page waits, then may ask again).
        One at a time per chart; it never touches the broker."""
        s = hub.stream_of((conn, cid))
        if s is None or not isinstance(before, int) or isinstance(before, bool):
            conn.send({"type": "older", "id": cid, "before": before,
                       "error": "not subscribed" if s is None else "before: the first bar's time (epoch ms)"})
            return
        if (conn, cid) in older_busy:
            return
        older_busy.add((conn, cid))
        task = asyncio.create_task(answer_older(conn, cid, s, before))
        older_tasks.add(task)
        task.add_done_callback(older_tasks.discard)

    async def answer_older(conn: Conn, cid: str, s: Stream, before: int) -> None:
        try:
            ans = await asyncio.to_thread(hub.older, s, before)
        except Exception as e:  # noqa: BLE001 — a failed chunk is the page's to retry, never the socket's end
            log(f"older {cid} ({s.root} {s.spec.key}): {type(e).__name__}: {e}")
            ans = {"error": str(e) or type(e).__name__}
        finally:
            older_busy.discard((conn, cid))
        conn.send({"type": "older", "id": cid, "before": before, **ans})
```

In `ws_endpoint`, right after the `if op == "unsub": …` block, add:

```python
                if op == "older":
                    ask_older(conn, cid, msg.get("before"))
                    continue
```

- [ ] **Step 8: `warm.py`** (new):

```python
"""Warm the chart service's 1-minute bar cache ahead of time, so a deep
scroll-back or a 250-session daily chart never waits on raw ticks:

    python -m homebase.charts.warm --roots NQ,ES --since 2021-09-22

For every COMPLETED session of each root in the tick archive (today's is
still being written), build the per-session 1-minute pickle the charts
resample from, skipping sessions already built and current. Read-only on the
archive (~/futures_ticks); writes only the cache (<state>/charts/cache).
Not scheduled: run it by hand.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from . import DEFAULT_ROOTS
from .history import History
from .session import session_date
from .store import ARCHIVE, TickStore


def warm(roots, since: dt.date | None = None, *, base: Path = ARCHIVE, cache_dir: Path | None = None,
         today: dt.date | None = None, out=print) -> dict:
    """Build each missing or stale 1-minute cache; {"built": n, "skipped": m}. cache_dir None: the service's."""
    history = History(TickStore(base), cache_dir=cache_dir)
    built = skipped = 0
    for root in roots:
        last = today or session_date(int(time.time() * 1000), root)
        dates = [d for d in history.store.sessions(root) if d < last and (since is None or d >= since)]
        for i, d in enumerate(dates, 1):
            if history.cached(root, d):
                skipped += 1
                continue
            t0 = time.monotonic()
            n = len(history.minutes(root, d))
            built += 1
            out(f"{root} {d.isoformat()}: {n} one-minute bars in {time.monotonic() - t0:.1f}s ({i}/{len(dates)})")
        out(f"{root}: {len(dates)} sessions checked")
    return {"built": built, "skipped": skipped}


def parse_args(argv):
    p = argparse.ArgumentParser(prog="python -m homebase.charts.warm",
                                description="Build the charts' 1-minute bar cache ahead of time.")
    p.add_argument("--roots", default=list(DEFAULT_ROOTS),
                   type=lambda s: [r.strip().upper() for r in s.split(",") if r.strip()],
                   help="comma-separated roots (default: the chart service's)")
    p.add_argument("--since", type=dt.date.fromisoformat, default=None,
                   help="the first session, YYYY-MM-DD (default: the archive's first)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    r = warm(a.roots, a.since)
    print(f"done: {r['built']} built, {r['skipped']} already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Run the server-side tests**

Run: `.venv/bin/python -m pytest tests/test_charts_hub.py tests/test_charts_server.py tests/test_charts_warm.py -q`, then `.venv/bin/python -m pytest -q`
Expected: PASS. The existing hub and server tests still pass with the deeper defaults, because their archives hold one or two past sessions.

- [ ] **Step 10: Write the failing Node tests** — `tests/js/scrollback.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const SB = require('../../homebase/static/charts/scrollback.js');

test('the view\'s left edge within 50 bars of the first bar asks once; nothing more until the answer', () => {
  const s = new SB.ScrollBack();
  assert.equal(SB.EDGE, 50);
  assert.equal(s.want({ from: 51, to: 200 }, 1000), null);
  const req = s.want({ from: 50, to: 200 }, 1000);
  assert.deepEqual(req, { before: 1000 });
  s.sent(req);
  assert.equal(s.want({ from: -10, to: 100 }, 1000), null);            // pending: no second request
  assert.equal(s.take({ before: 999, bars: [] }), false);               // not the one pending: stale
  assert.equal(s.want({ from: -10, to: 100 }, 1000), null);            // still pending
  assert.equal(s.take({ before: 1000, bars: [{}], done: false }), true);
  assert.deepEqual(s.want({ from: 3, to: 100 }, 500), { before: 500 }); // free again
});

test('the archive\'s start ends the requests until a new history; a failure waits 10 s', () => {
  let now = 0;
  const s = new SB.ScrollBack({ now: () => now });
  s.sent({ before: 1000 });
  assert.equal(s.take({ before: 1000, bars: [], done: true }), true);
  assert.equal(s.done, true);
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  s.reset();
  assert.deepEqual(s.want({ from: 0, to: 10 }, 1000), { before: 1000 });
  s.sent({ before: 1000 });
  assert.equal(s.take({ before: 1000, error: 'disk' }), false);
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  now = SB.RETRY_MS - 1;
  assert.equal(s.want({ from: 0, to: 10 }, 1000), null);
  now = SB.RETRY_MS;
  assert.deepEqual(s.want({ from: 0, to: 10 }, 1000), { before: 1000 });
  assert.equal(s.want(null, 1000), null);
  assert.equal(s.want({ from: 0, to: 10 }, undefined), null);
});

test('prepend: the older bars in front with their study values; the chart\'s first bars take the repair', () => {
  const mine = [{ ms: 300, sv: { ema: 1, vwap: 9 } }, { ms: 400, sv: { ema: 2, vwap: 9 } }, { ms: 500, sv: { ema: 3 } }];
  const m = { bars: [{ ms: 100 }, { ms: 200 }], studies: { ema: [0.1, 0.2], vwap: [5, 6] }, repair: { ema: [1.5, 2.5] } };
  const all = SB.prepend(mine, m);
  assert.deepEqual(all.map((b) => b.ms), [100, 200, 300, 400, 500]);
  assert.deepEqual(all.map((b) => b.sv.ema), [0.1, 0.2, 1.5, 2.5, 3]);
  assert.deepEqual(all.map((b) => b.sv.vwap), [5, 6, 9, 9, undefined]);
  assert.equal(all[2], mine[0]);                                        // the chart's bar objects are kept
});

test('session labels: the older ones in front, one per date', () => {
  const got = SB.mergeSessions([{ date: '2026-09-18' }, { date: '2026-09-21', approx: true }],
    [{ date: '2026-09-21' }, { date: '2026-09-22' }]);
  assert.deepEqual(got.map((s) => s.date), ['2026-09-18', '2026-09-21', '2026-09-22']);
  assert.equal(got[1].approx, undefined);                               // the chart's own label wins
});
```

Run: `node --test tests/js/scrollback.test.mjs`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 11: `scrollback.js`** (new, pure):

```js
/* Homebase Charts — scroll-back (TradingView's): drag a chart toward its first loaded bar and the next chunk
   of older sessions loads from the server's tick archive. Pure: the request guard (one request at a time,
   none once the archive's start is on the chart, a pause after a failure) and the merge of an answer into
   the chart's bars. No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const EDGE = 50;          // bars: the view's left edge this close to the first loaded bar asks for more
const RETRY_MS = 10000;   // after a failed answer, no new request for this long

class ScrollBack {
  constructor({ edge = EDGE, retryMs = RETRY_MS, now = () => Date.now() } = {}) {
    this.edge = edge; this.retryMs = retryMs; this.now = now;
    this.reset();
  }

  /* A new history on the chart: nothing pending, the archive's start not known. */
  reset() { this.pending = null; this.done = false; this.retryAt = 0; }

  /* The request for this visible logical range (the first loaded bar is logical 0): {before: firstMs} when
     the left edge is within `edge` bars of it and nothing holds it back, else null. The caller sends it and
     then calls sent(). */
  want(range, firstMs) {
    if (!range || firstMs == null || this.pending || this.done || this.now() < this.retryAt) return null;
    return range.from <= this.edge ? { before: firstMs } : null;
  }

  sent(req) { this.pending = req; }

  /* An answer: true when it answers the pending request and is to be applied (bars, or the archive's
     start); false when stale (a reload came between) or failed (then a pause before asking again). */
  take(m) {
    if (!this.pending || !m || m.before !== this.pending.before) return false;
    this.pending = null;
    if (m.error) { this.retryAt = this.now() + this.retryMs; return false; }
    if (m.done) this.done = true;
    return true;
  }
}

/* The chart's bars with an older chunk in front: each older bar gets its study values (sv) from m.studies,
   and the chart's own first bars take m.repair's (the studies re-run across the join). The bar objects are
   reused. */
function prepend(bars, m) {
  const older = (m.bars || []).map((b, i) => {
    b.sv = {};
    for (const k in (m.studies || {})) b.sv[k] = m.studies[k][i];
    return b;
  });
  for (const k in (m.repair || {})) {
    m.repair[k].forEach((v, i) => { const b = bars[i]; if (b) { b.sv = b.sv || {}; b.sv[k] = v; } });
  }
  return older.concat(bars);
}

/* Session labels (gaps, approx. flow) for an older chunk in front of the chart's, one per date (the chart's
   own label wins). */
function mergeSessions(older, sessions) {
  const have = new Set((sessions || []).map((s) => s.date));
  return (older || []).filter((s) => !have.has(s.date)).concat(sessions || []);
}

const api = { ScrollBack, prepend, mergeSessions, EDGE, RETRY_MS };
if (typeof window !== 'undefined') window.HBScrollBack = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

Run: `node --test tests/js/*.test.mjs`
Expected: PASS.

- [ ] **Step 12: `primitives.js`, "Start of data".** Insert before `window.HBLayers = …` and add `Start` to the export:

```js
/* "Start of data": once scroll-back has reached the archive's first bar, a dashed line just before it with
   the words beside it (left of the line when they fit, else right). */
class Start extends Layer {
  constructor(P) { super(P); this.on = false; }
  z() { return 'bottom'; }
  set(on) { if (this.on !== on) { this.on = on; this.redraw(); } }
  draw(target) {
    if (!this.on || !this.chart) return;
    const x0 = this.chart.timeScale().logicalToCoordinate(0);   // bar 0: an integer logical (v5)
    if (x0 == null) return;
    const x = Math.round(x0 - Math.max(this.spacing(), 2) / 2) + 0.5;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (x < 0 || x > mediaSize.width) return;
      ctx.strokeStyle = this.P.text2;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, mediaSize.height); ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
      ctx.fillStyle = this.P.text2;
      ctx.textBaseline = 'middle';
      const left = x - 8 - ctx.measureText('Start of data').width >= 4;
      ctx.textAlign = left ? 'right' : 'left';
      ctx.fillText('Start of data', left ? x - 8 : x + 8, 30);
    });
  }
}
```

- [ ] **Step 13: `cell.js`, the trigger, the prepend, the label.**
- Add `Start` to the `window.HBLayers` destructuring.
- Constructor fields: `this.back = new window.HBScrollBack.ScrollBack();   // scroll-back: older history on demand` and `this.start = null;   // the "Start of data" layer`.
- In `onHistory(m)`, right after `if (this.inflight.length) return;`, add `this.back.reset();`. A new history starts over.
- In `makeChart()`: add `this.start = new Start(P);` next to the other layers, and put `this.start` right after `this.gaps` in the attach list. Change Task 8's range subscription to `this.chart.timeScale().subscribeVisibleLogicalRangeChange((r) => { this.syncFootprint(); this.evTip.hidden = true; this.askOlder(r); });`.
- In `teardown()`, null `this.start` too.
- In `build(view)`, after `this.legend(null);`, add `this.start.set(this.back.done);`.

Add the methods (after `tickSecond`):

```js
  /* TradingView's scroll-back: the view's left edge near the first loaded bar asks the server for the next
     chunk of older sessions (one request at a time; none while a subscription is in flight). */
  askOlder(r) {
    if (!this.chart || this.inflight.length || !this.bars.length) return;
    const req = this.back.want(r, this.bars[0].ms);
    if (req && this.host.send({ op: 'older', id: this.id, before: req.before })) this.back.sent(req);
  }

  /* Older sessions in front of the chart: the bars, their studies (and the repaired first bars) and session
     labels merged, every series re-set in place (no rebuild: no flash, a drag goes on), the view shifted by
     the bars added so it does not move. done: "Start of data" at the first bar. */
  onOlder(m) {
    if (!this.back.take(m) || !this.chart || this.inflight.length) return;
    const k = (m.bars || []).length;
    if (k) {
      const r = this.chart.timeScale().getVisibleLogicalRange(), all = window.HBScrollBack.prepend(this.bars, m);
      this.sessions = window.HBScrollBack.mergeSessions(m.sessions, this.sessions);
      this.bars = []; this.realT = new Map();
      for (const b of all) this.append(b);   // axis times again: tick/volume/range bars sit on an index axis
      this.candles.setData(this.candleData());
      for (const l of this.lines) l.s.setData(this.bars.map((b) => this.point(l, b)));
      if (r) this.chart.timeScale().setVisibleLogicalRange({ from: r.from + k, to: r.to + k });
      if (this.hover != null) this.hover += k;
      this.drawMarkers(); this.drawGaps(); this.syncFootprint(); this.syncEth();
      this.lg.badge.hidden = !this.sessions.some((s) => s.approx);
      this.legend(this.hover);
      if (this.dc) this.dc.refresh();
    }
    this.start.set(this.back.done);
  }
```

- [ ] **Step 14: `app.js` and the shell.** In `connect()`'s `ws.onmessage`, add `else if (m.type === 'older') c.onOlder(m);` after the `history` line. In `charts.html`, add `<script src="/static/charts/scrollback.js?v=3"></script>` right before the `cell.js` script tag.

- [ ] **Step 15: Syntax-check and run everything**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green.

- [ ] **Step 16: Commit**

```bash
git add homebase/charts/hub.py homebase/charts/history.py homebase/charts/server.py homebase/charts/warm.py tests/charts_util.py tests/test_charts_hub.py tests/test_charts_server.py tests/test_charts_warm.py homebase/static/charts/scrollback.js tests/js/scrollback.test.mjs homebase/static/charts/cell.js homebase/static/charts/primitives.js homebase/static/charts/app.js homebase/static/charts.html
git commit -m "feat(charts): deep history — deeper default load, scroll back through the whole tick archive with studies continued across each join, Start of data, cache warm-up command

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check (replay :8854):**
- **Optional first:** `.venv/bin/python -m homebase.charts.warm --roots NQ --since 2026-06-01`. It reads `~/futures_ticks` only and fills the worktree's `homebase/.state/charts/cache`. Without it, a cold D chart may take minutes to load.
- NQ 1m:
  - About 5 sessions load.
  - Drag right until the first bar is near the left edge: older sessions appear and the view does not jump. Watch one candle.
  - Keep dragging: chunk after chunk.
  - Gap bands and the approx.-flow badge cover the older sessions.
  - EMA and VWAP lines run unbroken across each join. A long EMA shows no step.
  - Drawings and positions placed on old bars stay at their times.
  - The legend follows the crosshair on the older bars.
- NQ D:
  - About 250 sessions load.
  - Scroll to the archive's start (2021-09-22): a dashed `Start of data` line with its label appears, and the network panel shows no more `older` requests.
  - Switching the interval clears it, and scroll-back works again.
- NQ 500T: one session per chunk.
- A second chart of the same stream is unaffected by the first one's scroll-back.
- Zero console errors, and no errors in the chart service's log.

---

### Task 10: Chart context menu + moving indicators between panes

Spec §7 ("Chart context menu + moving indicators between panes", added 2026-09-26). It runs after Tasks 1–9 and builds on their code: Task 6's `openMenu(…, {root})`, `chartSettings()` and `closeDialog`; Task 7's `buildSeries` `add` helper (`overlay`, `NO_SCALE`) and `legendRows`; Task 9's `onOlder`, which re-sets every series in `this.lines` (series placed on the price pane are in `this.lines` too, so scroll-back needs no change).

**Files:**
- Create: `homebase/static/charts/chartmenu.js` (`HBChartMenu`, pure: the menu's items, sections and dividers, the extension point, the indicator menu's items, arrow-key stepping)
- Create: `tests/js/chartmenu.test.mjs`
- Modify: `homebase/static/charts/catalog.js` (`pane` in the indicator model: `movable`, `placement`, `instance`, `migrate`)
- Modify: `tests/js/catalog.test.mjs` (append the `pane` tests)
- Modify: `homebase/static/charts/cell.js` (placement in `buildSeries`, `paneUid`, `onMenu`, `paneAt`, `resetView`, `setPlacement`, `removeIndicator`, the legend's `⋯`)
- Modify: `homebase/static/charts/drawings.js` (`Controller.onDbl`: empty space opens the chart menu)
- Modify: `homebase/static/charts/app.js` (menus at the pointer, `chartMenu`, `indicatorMenu`, `MENU_ACTS`, the host callbacks, arrow keys and ⌥R)
- Modify: `homebase/static/charts.html`, `homebase/static/charts/charts.css`, `homebase/static/charts/icons.js`

**Interfaces:**
- Consumes:
  - Task 6: `openMenu(anchor, cls, {right, root})`, `placeMenu()` (flips above), `closeMenu()`, `closeDialog()` (closes a menu first), `chartSettings()` (opens Settings for `cur()`), `readLayout(v)` (runs `C.migrateLayout`, so a saved `pane` survives once `migrate` keeps it), `putLayout` (saves each indicator object whole).
  - Task 7: `buildSeries`'s `add(inst, src, part, type, opts, where)` with `overlay = where === 0 && !opts.priceScaleId` and `NO_SCALE`; `legendRows()` with `S.legendFlags` / `S.legendLabel`; `Cell.R`.
  - Task 9: `Cell.onOlder` (re-sets `this.lines`), `Cell.askOlder` (the range subscription). Neither changes.
  - Task 4: `Controller.onDbl` (a double-click on a long/short box opens its settings; it keeps doing that).
  - Existing: `Cell.update(patch)`, `restyle()`, `build(view)` (stretch factors for however many sub-panes exist), `setVisible`, `onLegendClick`, `iconButton`, `host.onPick`; `drawings.list(root)`, `drawings.clear(root)`; `menuItem(text, sub, onPick, active)`, `select(i)`, `cur()`, `sbNote(text)`, `onKey`, `hostFor(id)`; `HBDrawings.roundToTick(p, tick)`; `HBCatalog.decimals`, `fmtPrice`, `def`, `instance`, `migrate`.
- Produces:
  - `HBCatalog.movable(id) -> bool`, `HBCatalog.placement(inst) -> 'main'|'own'|null`, `HBCatalog.PANES = ['main', 'own']`. Catalog defs of pane-type indicators carry `pane` (their default): `volume: 'main'`, `adx`, `delta`, `cumdelta: 'own'`. `instance(id)` and `migrate(cfg)` give a movable indicator `pane` and give no other indicator the key.
  - `window.HBChartMenu` (and `module.exports`):
    - `SECTIONS = ['view', 'copy', 'trading', 'remove', 'settings']` (top to bottom).
    - `register(section, itemsFn) -> unregister()`: `itemsFn(ctx) -> item[]`, where an extension's item is `{text, sub?, run(ctx)}`. Throws `Error('unknown chart menu section: …')` for an unknown section and `TypeError` for a non-function. **This is the extension point the chart-trading build uses:** `HBChartMenu.register('trading', (ctx) => [{text: 'Buy 1 NQ @ 30,878.00 limit', run(ctx) {…}}, …])`, loaded after `chartmenu.js` and before or after `app.js`; the menu reads the registry every time it opens.
    - `items(ctx) -> (item | {sep: true})[]`: every section's items in order, each stamped with `section`, and one divider between two non-empty sections (never leading, trailing or doubled). A throwing `itemsFn` is skipped, and so is an item without a non-empty `text` or without `run`/`act`.
    - `createRegistry() -> {register, items}` and `builtins(reg) -> reg` (tests build their own registry this way).
    - Built-in items `{act, text, sub?, copy?}`: `reset` (`Reset chart view`, sub `⌥R`), `copy` (`Copy price 30,878.00`, `copy: '30878.00'`), `removeDrawings` (`Remove N drawing(s)`), `removeIndicators` (`Remove N indicator(s)`), `settings` (`Settings…`).
    - `ctx` (built by the page) = `{cell, root, price, tick, nDrawings, nIndicators}`; `price` is tick-rounded, or `null` when the pointer is off the price scale.
    - `paneItems(inst) -> [{act: 'move', pane, text}?, {act: 'remove', text: 'Remove'}]`.
    - `copyText(price, tick)`, `copyLabel(price, tick)`, `armText(n, root)`, `step(i, n, key) -> index`.
  - `Cell.paneUid` (pane index → the uid of the indicator in its own pane; `[null]` for the price pane), `Cell.onMenu(e, dbl = false)`, `Cell.paneAt(clientY) -> index | -1`, `Cell.resetView()`, `Cell.setPlacement(uid, pane)`, `Cell.removeIndicator(uid)`.
  - Host callbacks: `onChartMenu(cell, {x, y, price})`, `onIndicatorMenu(cell, uid, {anchor} | {at: {x, y}})`.
  - Page: `openMenu(anchor | null, cls, {right, root, at: {x, y}})`, where `at` opens the menu at the pointer (then `anchor` is `null`); `menuAt`; `chartMenu(cell, at)`; `indicatorMenu(cell, uid, opts)`; `MENU_ACTS`.

**Task-level rulings (spec §7's open points):**
- **T10-R1 · Reset chart view** is TradingView's reset: `timeScale().resetTimeScale()` (default bar spacing, the latest bar at the right margin) plus `autoScale: true` on every pane's right price scale. The spec says "fit content", but with Task 9's deep history the loaded range can be tens of thousands of bars, and `fitContent()` would squeeze them all into the panel and trigger a scroll-back request.
- **T10-R2 · Which indicators move:** the catalog's pane-type indicators, which are ADX, Delta and Cumulative delta (default `own`), plus Volume (default `main`, which is where it sits today; it can be moved to its own pane, as on TradingView). VWAP, EMA/SMA/VWMA, Session levels, Footprint, Volume profile and Big prints are drawn on the candles and never move.
- **T10-R3 · On `main`:** the series goes on an overlay price scale of its own (`priceScaleId: 'ind:<uid>'`, which has no visible axis) with `scaleMargins {top: 0.75, bottom: 0}` and `lastValueVisible: false`, as Volume is drawn today. It therefore never takes part in the price scale's autoscale, whatever "Scale price chart only" says. Volume on `main` keeps today's `'vol'` scale at `top: 0.8`. Several indicators on `main` share the bottom quarter and overlap, as overlays do on TradingView.
- **T10-R4 · The `⋯` button** appears only on rows of movable indicators, last in the row: eye · gear · × · ⋯ (TradingView's legend order). Right-clicking inside an indicator's own pane opens the same menu.
- **T10-R5 · Where each gesture opens a menu:**
  - Right-click anywhere in the price pane opens the chart menu, even over a drawing (drawing menus are out of scope). Right-click in an indicator's own pane opens that indicator's menu. Right-click on the price or time axis opens no menu.
  - The browser's own menu never shows over a chart.
  - A double-click opens the chart menu only on empty price-pane space with the cursor tool. On any drawing it keeps the drawing's own behaviour: position settings for long/short boxes, and nothing for the others. It never opens a menu in an indicator pane, or while a drawing tool is picked (those clicks place points).
- **T10-R6 · Copy price:** the menu row reads `Copy price 30,878.00`, while the clipboard gets `30878.00` (no thousands separator, the instrument's decimals), so the value pastes into an order ticket or a number field.
- **T10-R7 · Counts** are singular for one: `Remove 1 drawing`, `Remove 1 indicator`. `N indicators` counts every indicator on the chart (Volume, VWAP, levels, footprint…), which is what the item removes. `N drawings` counts the drawings of the chart's symbol, which is what the rail's Remove all removes. The armed text is the rail's own: `Click again to remove 3 drawings on NQ` (3 s; the menu stays open while armed).
- **T10-R8 · A move re-creates the series; it does not call `moveToPane`.** The vendored Lightweight Charts 5.2.1 has `ISeriesApi.moveToPane(index)`: it creates the pane at `index` if needed and drops the pane the series left once it is empty. It also has `IPaneApi.moveTo(index)`, `chart.removePane(index)` and `chart.priceScale(id, paneIndex)`. A move, however, renumbers the panes below and leaves their stretch factors, `paneUid`, the overlay scale margins and Task 7's autoscale flags stale. All of those are computed in one place, `build()`. So a placement change goes through `Cell.update({indicators})`, which calls `restyle()` → `build(viewNow())` (the view is kept), as the legend's × already does.
- **T10-R9 · `catalog.js` is edited here.** The Execution notes keep it off-limits because another agent was editing it; that work has landed (`e3efed2`, the status-bar staleness fix). The indicator model lives in `catalog.js`, and Task 6's page-side re-attach trick (`readLayout`) would have to be repeated in `instance`, `migrate` and every `C.migrate` path. Step 1 checks that no one else is editing it.
- **T10-R10 · Arrow keys** walk the items of any open menu (↓/↑ wrap, Home/End jump), except while a text field in the menu has focus. Enter and Space press the focused item, because items are native buttons. A menu opened at the pointer takes focus itself (`tabindex=-1`), so the first ↓ lands on its first item. ⌥R (`e.code === 'KeyR'` with Alt: on macOS `e.key` is `®`) resets the selected chart's view.

- [ ] **Step 1: Check that `catalog.js` is free**

Run: `git status --short homebase/static/charts/catalog.js tests/js/catalog.test.mjs`
Expected: no output. If either file shows as modified, another agent is editing it again: STOP and report. Do not edit or stash it.

- [ ] **Step 2: Write the failing catalog tests.** Append to `tests/js/catalog.test.mjs`:

```js
// ---- pane placement (spec §7) ----
test('pane-type indicators carry a placement with today as the default; price-pane-only ones carry none', () => {
  assert.deepEqual(C.PANES, ['main', 'own']);
  assert.equal(C.instance('volume').pane, 'main');
  for (const id of ['delta', 'cumdelta', 'adx']) {
    assert.equal(C.instance(id).pane, 'own', id);
    assert.equal(C.movable(id), true, id);
  }
  assert.equal(C.movable('volume'), true);
  for (const id of ['vwap', 'ema', 'sma', 'vwma', 'levels', 'footprint', 'profile', 'bigprints']) {
    assert.equal('pane' in C.instance(id), false, id);
    assert.equal(C.movable(id), false, id);
  }
  assert.equal(C.movable('nope'), false);
});

test('placement: a valid saved pane, else the default; null for what cannot move', () => {
  assert.equal(C.placement({ id: 'delta' }), 'own');
  assert.equal(C.placement({ id: 'delta', pane: 'main' }), 'main');
  assert.equal(C.placement({ id: 'volume', pane: 'own' }), 'own');
  assert.equal(C.placement({ id: 'cumdelta', pane: 'sideways' }), 'own');
  assert.equal(C.placement({ id: 'ema', pane: 'own' }), null);
  assert.equal(C.placement({ id: 'nope', pane: 'main' }), null);
  assert.equal(C.placement(null), null);
});

test('migrate keeps a saved placement and gives a missing or bad one today\'s', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', indicators: [
    { uid: 'a', id: 'delta', params: {}, visible: true, pane: 'main' },
    { uid: 'b', id: 'cumdelta', params: {} },
    { uid: 'c', id: 'volume', params: {}, pane: 'sideways' },
    { uid: 'd', id: 'adx', params: { length: 14 }, pane: 'own' },
    { uid: 'e', id: 'ema', params: { length: 9 }, pane: 'own' }] });
  assert.deepEqual(m.indicators.map((x) => [x.uid, x.pane]),
    [['a', 'main'], ['b', 'own'], ['c', 'main'], ['d', 'own'], ['e', undefined]]);
  assert.equal('pane' in m.indicators[4], false);
});

test('Build-1 charts migrate with today\'s placement', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', st: { volume: true, delta: true, cumdelta: true, adx: 14 } });
  const by = Object.fromEntries(m.indicators.map((x) => [x.id, x.pane]));
  assert.equal(by.volume, 'main');
  assert.equal(by.delta, 'own');
  assert.equal(by.cumdelta, 'own');
  assert.equal(by.adx, 'own');
  assert.equal(by.vwap, undefined);
});

test('a saved layout round-trips each placement', () => {
  const lay = { grid: 1, cells: [{ root: 'NQ', spec: 'time:60', indicators: [
    { uid: 'a', id: 'delta', params: {}, visible: true, pane: 'main' },
    { uid: 'b', id: 'volume', params: {}, visible: true, pane: 'own' }] }] };
  const back = C.migrateLayout(JSON.parse(JSON.stringify(C.migrateLayout(lay))));
  assert.deepEqual(back.cells[0].indicators.map((x) => x.pane), ['main', 'own']);
});
```

- [ ] **Step 3: Write the failing menu tests** — `tests/js/chartmenu.test.mjs`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const M = require('../../homebase/static/charts/chartmenu.js');

const texts = (list) => list.map((x) => (x.sep ? '—' : x.text));
const CTX = { price: 30878, tick: 0.25, nDrawings: 0, nIndicators: 0 };
const fresh = () => M.builtins(M.createRegistry());
const noop = () => {};

test('no drawings and no indicators: Reset, Copy price, Settings, each in its own section', () => {
  assert.deepEqual(M.SECTIONS, ['view', 'copy', 'trading', 'remove', 'settings']);
  assert.deepEqual(texts(fresh().items(CTX)), ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Settings…']);
});

test('Remove N drawings / Remove N indicators only when N > 0, drawings first, singular for one', () => {
  const reg = fresh();
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 3, nIndicators: 1 })),
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 3 drawings', 'Remove 1 indicator', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 1 })).slice(4, 5), ['Remove 1 drawing']);
  assert.deepEqual(texts(reg.items({ ...CTX, nIndicators: 4 })).slice(4, 5), ['Remove 4 indicators']);
});

test('each built-in names its action; Reset shows ⌥R; Copy carries the plain price', () => {
  const list = fresh().items({ ...CTX, nDrawings: 2, nIndicators: 2 }).filter((x) => !x.sep);
  assert.deepEqual(list.map((x) => x.act), ['reset', 'copy', 'removeDrawings', 'removeIndicators', 'settings']);
  assert.deepEqual(list.map((x) => x.section), ['view', 'copy', 'remove', 'remove', 'settings']);
  assert.equal(list[0].sub, '⌥R');
  assert.equal(list[1].copy, '30878.00');
});

test('Copy price is tick-rounded; no price (the pointer off the scale) = no Copy item and no stray divider', () => {
  const reg = fresh();
  const at = reg.items({ ...CTX, price: 30878.13 }).find((x) => x.act === 'copy');
  assert.equal(at.text, 'Copy price 30,878.25');
  assert.equal(at.copy, '30878.25');
  assert.deepEqual(texts(reg.items({ ...CTX, price: null })), ['Reset chart view', '—', 'Settings…']);
  assert.deepEqual(texts(reg.items({ ...CTX, price: NaN })), ['Reset chart view', '—', 'Settings…']);
  assert.equal(M.copyText(2650.34, 0.1), '2650.3');
  assert.equal(M.copyLabel(2650.34, 0.1), 'Copy price 2,650.3');
});

test('the extension point: a trading section between Copy and Remove, dividers around it, ctx passed in', () => {
  const reg = fresh();
  let seen = null;
  const off = reg.register('trading', (ctx) => {
    seen = ctx;
    return [{ text: `Buy 1 NQ @ ${ctx.price} limit`, run: noop }, { text: 'Sell 1 NQ @ stop', run: noop }];
  });
  const ctx = { ...CTX, nDrawings: 2 };
  const list = reg.items(ctx);
  assert.deepEqual(texts(list), ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Buy 1 NQ @ 30878 limit',
    'Sell 1 NQ @ stop', '—', 'Remove 2 drawings', '—', 'Settings…']);
  assert.equal(seen, ctx);
  assert.equal(list[4].section, 'trading');
  assert.equal(typeof list[4].run, 'function');
  off();
  assert.deepEqual(texts(reg.items(ctx)),
    ['Reset chart view', '—', 'Copy price 30,878.00', '—', 'Remove 2 drawings', '—', 'Settings…']);
  off();   // a second call is harmless
});

test('registrations keep their order in a section; an extension comes after the built-ins of its section', () => {
  const reg = fresh();
  reg.register('trading', () => [{ text: 'A', run: noop }]);
  reg.register('trading', () => [{ text: 'B', run: noop }]);
  reg.register('remove', () => [{ text: 'Remove alerts', run: noop }]);
  assert.deepEqual(texts(reg.items({ ...CTX, nDrawings: 1 })), ['Reset chart view', '—', 'Copy price 30,878.00', '—',
    'A', 'B', '—', 'Remove 1 drawing', 'Remove alerts', '—', 'Settings…']);
});

test('unknown sections and non-functions are refused; a throwing or junk extension is skipped', () => {
  const reg = fresh();
  assert.throws(() => reg.register('orders', () => []), /unknown chart menu section: orders/);
  assert.throws(() => reg.register('trading', 5), TypeError);
  reg.register('trading', () => { throw new Error('broken'); });
  reg.register('trading', () => [null, 'junk', { text: '', run: noop }, { text: 'no action' }]);
  reg.register('trading', () => 'not a list');
  assert.deepEqual(texts(reg.items(CTX)), texts(fresh().items(CTX)));
});

test('the page-wide HBChartMenu has the built-ins and the same extension point', () => {
  assert.deepEqual(texts(M.items(CTX)), texts(fresh().items(CTX)));
  const off = M.register('trading', () => [{ text: 'Buy', run: noop }]);
  assert.ok(texts(M.items(CTX)).includes('Buy'));
  off();
  assert.ok(!texts(M.items(CTX)).includes('Buy'));
});

test('the indicator menu: move to the other placement, then Remove; Remove only for what cannot move', () => {
  assert.deepEqual(M.paneItems({ id: 'delta', pane: 'own' }),
    [{ act: 'move', pane: 'main', text: 'Move to main chart' }, { act: 'remove', text: 'Remove' }]);
  assert.deepEqual(M.paneItems({ id: 'cumdelta', pane: 'main' }),
    [{ act: 'move', pane: 'own', text: 'Move to new pane below' }, { act: 'remove', text: 'Remove' }]);
  assert.deepEqual(M.paneItems({ id: 'volume' }).map((x) => x.text), ['Move to new pane below', 'Remove']);
  assert.deepEqual(M.paneItems({ id: 'ema', params: { length: 9 } }), [{ act: 'remove', text: 'Remove' }]);
});

test('the armed Remove-drawings text is the rail\'s', () => {
  assert.equal(M.armText(3, 'NQ'), 'Click again to remove 3 drawings on NQ');
  assert.equal(M.armText(1, 'ES'), 'Click again to remove 1 drawing on ES');
});

test('arrow keys walk the items and wrap; Home/End jump; nothing to walk = -1', () => {
  assert.equal(M.step(-1, 3, 'ArrowDown'), 0);
  assert.equal(M.step(0, 3, 'ArrowDown'), 1);
  assert.equal(M.step(2, 3, 'ArrowDown'), 0);
  assert.equal(M.step(-1, 3, 'ArrowUp'), 2);
  assert.equal(M.step(0, 3, 'ArrowUp'), 2);
  assert.equal(M.step(1, 3, 'Home'), 0);
  assert.equal(M.step(1, 3, 'End'), 2);
  assert.equal(M.step(1, 3, 'Tab'), 1);
  assert.equal(M.step(-1, 0, 'ArrowDown'), -1);
});
```

- [ ] **Step 4: Run them to verify they fail**

Run: `node --test tests/js/catalog.test.mjs tests/js/chartmenu.test.mjs`
Expected: FAIL. `chartmenu.test.mjs` fails with "Cannot find module …/chartmenu.js", and the new catalog tests fail on `C.PANES` / `C.movable` / `C.placement` (the old catalog tests still pass).

- [ ] **Step 5: `catalog.js`, the `pane` placement.** In `CATALOG`, give the four pane-type defs their default placement (the rest stay as they are):

```js
  { id: 'volume', group: 'Volume', name: 'Volume', params: [], pane: 'main' },
```
```js
  { id: 'adx', group: 'Trend', name: 'ADX / DMI', params: [LENGTH(14)], pane: 'own' },
```
```js
  { id: 'delta', group: 'Order flow', name: 'Delta', params: [], pane: 'own' },
  { id: 'cumdelta', group: 'Order flow', name: 'Cumulative delta', params: [], pane: 'own' },
```

After `function def(id) { … }`, add:

```js
/* Where an indicator that can live in its own pane is drawn (spec §7): 'own' = a pane of its own below the price
   pane, 'main' = on the price pane (an overlay at the bottom, out of the price autoscale). A catalog def's `pane`
   is its default, i.e. where it was drawn before placements existed; the price-pane-only ones (VWAP, MAs,
   levels, footprint, profile, big prints) have none and never move. */
const PANES = ['main', 'own'];
function movable(id) { const d = def(id); return !!(d && d.pane); }
function placement(inst) {
  const d = inst && def(inst.id);
  if (!d || !d.pane) return null;
  return PANES.includes(inst.pane) ? inst.pane : d.pane;
}
```

Replace `instance`:

```js
function instance(id, params) {
  const d = def(id);
  if (!d) return null;
  const inst = { uid: uid(), id, params: clampParams(id, params), visible: true };
  if (d.pane) inst.pane = d.pane;
  return inst;
}
```

In `migrate`, replace the new-form `map`:

```js
    const indicators = c.indicators.filter((x) => x && def(x.id)).map((x) => {
      const o = { uid: typeof x.uid === 'string' && x.uid ? x.uid : uid(), id: x.id,
        params: clampParams(x.id, x.params), visible: x.visible !== false };
      if (movable(x.id)) o.pane = placement(x);
      return o;
    });
```

(The Build-1 `st` form goes through `instance()`, so it gets the defaults.) Add `PANES, movable, placement` to `api`.

- [ ] **Step 6: `chartmenu.js`** (new, pure):

```js
/* Homebase Charts — the chart's context menu (TradingView's right-click menu), pure: which items a chart's menu
   shows, in which order, with dividers; the extension point other builds add items through; the items of an
   indicator's own menu; arrow-key stepping. The page (app.js) renders the items and runs them. No browser
   globals at load time: the Node tests load this file directly.

   An item is {text, sub?, act, …} (a built-in: the page runs MENU_ACTS[act]) or {text, sub?, run(ctx)} (an
   extension's: the page calls run). ctx is the page's {cell, root, price, tick, nDrawings, nIndicators}; price
   is tick-rounded, or null when the pointer is off the price scale. This file reads only price, tick, nDrawings
   and nIndicators.

   The chart-trading build adds its Buy/Sell items without editing this file:
     HBChartMenu.register('trading', (ctx) => [{ text: 'Buy 1 NQ @ 30,878.00 limit', run(ctx) { … } }]); */
(function () {
'use strict';
const Cat = (typeof window !== 'undefined' && window.HBCatalog) || (typeof require === 'function' ? require('./catalog.js') : null);

/* The menu's sections, top to bottom, with a divider between two that have items. 'trading' stays empty until
   the chart-trading build registers its items. */
const SECTIONS = ['view', 'copy', 'trading', 'remove', 'settings'];
const SEP = Object.freeze({ sep: true });

function roundTick(p, tick) { return tick > 0 ? +(Math.round(p / tick) * tick).toFixed(Cat.decimals(tick)) : p; }
/* What Copy price puts on the clipboard: the plain number, e.g. 30878.00 (it pastes into any number field). */
function copyText(price, tick) { return roundTick(price, tick).toFixed(Cat.decimals(tick)); }
/* The menu row: Copy price 30,878.00. */
function copyLabel(price, tick) { return `Copy price ${Cat.fmtPrice(roundTick(price, tick), tick)}`; }
function count(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }
/* The armed Remove-drawings row: the rail's Remove-all text. */
function armText(n, root) { return `Click again to remove ${count(n, 'drawing')} on ${root}`; }

/* A registry of item providers per section. register() returns its own unregister. */
function createRegistry() {
  const fns = Object.fromEntries(SECTIONS.map((s) => [s, []]));
  function register(section, itemsFn) {
    if (!SECTIONS.includes(section)) throw new Error(`unknown chart menu section: ${section}`);
    if (typeof itemsFn !== 'function') throw new TypeError('HBChartMenu.register: itemsFn must be a function');
    const entry = { fn: itemsFn };   // its own object: one function registered twice is two entries
    fns[section].push(entry);
    return () => { const i = fns[section].indexOf(entry); if (i >= 0) fns[section].splice(i, 1); };
  }
  function items(ctx) {
    const out = [];
    for (const s of SECTIONS) {
      const got = [];
      for (const { fn } of fns[s]) {
        let list;
        try { list = fn(ctx); } catch (_) { continue; }   // a broken extension never takes the menu down
        for (const it of Array.isArray(list) ? list : []) {
          const ok = it && typeof it === 'object' && typeof it.text === 'string' && it.text
            && (typeof it.run === 'function' || typeof it.act === 'string');
          if (ok) got.push({ ...it, section: s });
        }
      }
      if (got.length) { if (out.length) out.push(SEP); out.push(...got); }
    }
    return out;
  }
  return { register, items };
}

/* The built-in items (spec §7), registered like any extension. */
function builtins(reg) {
  reg.register('view', () => [{ act: 'reset', text: 'Reset chart view', sub: '⌥R' }]);
  reg.register('copy', (ctx) => (ctx.price == null || !Number.isFinite(ctx.price) ? []
    : [{ act: 'copy', text: copyLabel(ctx.price, ctx.tick), copy: copyText(ctx.price, ctx.tick) }]));
  reg.register('remove', (ctx) => [
    ...(ctx.nDrawings > 0 ? [{ act: 'removeDrawings', text: `Remove ${count(ctx.nDrawings, 'drawing')}` }] : []),
    ...(ctx.nIndicators > 0 ? [{ act: 'removeIndicators', text: `Remove ${count(ctx.nIndicators, 'indicator')}` }] : [])]);
  reg.register('settings', () => [{ act: 'settings', text: 'Settings…' }]);
  return reg;
}

/* An indicator's own menu (its legend ⋯, or a right-click in its pane): move it to the other placement, then
   Remove. An indicator that cannot move gets Remove only. */
function paneItems(inst) {
  const where = Cat.placement(inst), out = [];
  if (where === 'own') out.push({ act: 'move', pane: 'main', text: 'Move to main chart' });
  if (where === 'main') out.push({ act: 'move', pane: 'own', text: 'Move to new pane below' });
  out.push({ act: 'remove', text: 'Remove' });
  return out;
}

/* The item the arrow keys go to from item i of n (-1: none focused yet); ↓/↑ wrap, Home/End jump. */
function step(i, n, key) {
  if (n <= 0) return -1;
  if (key === 'Home') return 0;
  if (key === 'End') return n - 1;
  if (key === 'ArrowDown') return i < 0 ? 0 : (i + 1) % n;
  if (key === 'ArrowUp') return i < 0 ? n - 1 : (i - 1 + n) % n;
  return i;
}

const main = builtins(createRegistry());   // the page's menu
const api = { SECTIONS, createRegistry, builtins, register: main.register, items: main.items, paneItems, copyText,
  copyLabel, armText, step };
if (typeof window !== 'undefined') window.HBChartMenu = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
```

- [ ] **Step 7: Run the Node tests to verify they pass**

Run: `node --test tests/js/catalog.test.mjs tests/js/chartmenu.test.mjs`, then `node --test tests/js/*.test.mjs`
Expected: PASS, with every earlier test still green.

- [ ] **Step 8: `cell.js`, placement, the menus, reset.**

In the header comment, extend the host list with `onChartMenu(cell, {x, y, price}), onIndicatorMenu(cell, uid, {anchor} | {at})` (the chart menu and an indicator's menu, app.js), and add the sentence: "Indicators that can live in their own pane (HBCatalog.placement) are drawn there or on the price pane on an overlay scale of their own."

Next to `PANE_H`, add:

```js
const VOL_TOP = 0.8;    // Volume on the price pane: its bars in the bottom 20%
const MAIN_TOP = 0.75;  // another pane-type indicator on the price pane: the bottom quarter, on its own scale
```

Constructor fields (before `slot.className = 'panel'`): `this.paneUid = [null];   // pane index -> the uid of the indicator in its own pane (0: the price pane)`.

After `this.lg.inds.addEventListener('click', …)`, add:

```js
    this.box.addEventListener('contextmenu', (e) => this.onMenu(e));
```

Replace `buildSeries()`. It keeps Task 7's `add` helper as it is, and places every pane-type indicator by `C.placement`:

```js
  /* One series per drawn part of each indicator instance, in instance order. A pane-type indicator goes where
     its placement says: 'own' = the next pane below; 'main' = the price pane, on an overlay scale of its own
     pinned to the bottom (as Volume), so it never moves the price autoscale. */
  buildSeries() {
    const P = this.P;
    let ci = 0, pane = 0;
    this.paneUid = [null];
    const add = (inst, src, part, type, opts, where) => {
      const overlay = where === 0 && !opts.priceScaleId;   // on the price pane's own scale (not the volume overlay)
      const auto = overlay && this.R.scalePriceOnly ? { autoscaleInfoProvider: NO_SCALE } : {};
      const s = this.chart.addSeries(type, { priceLineVisible: false, visible: inst.visible !== false, ...opts, ...auto }, where);
      this.lines.push({ uid: inst.uid, s, src, part, overlay });
      return s;
    };
    const line = (inst, src, part, color, width, where = 0, extra = {}) => add(inst, src, part, LW.LineSeries,
      { color, lineWidth: width, lastValueVisible: true, crosshairMarkerVisible: false, title: '', ...extra }, where);
    // {where, scale}: the pane index, and the series options that put it on its overlay scale when on 'main'
    const spot = (inst) => {
      if (C.placement(inst) === 'own') { this.paneUid.push(inst.uid); return { where: ++pane, scale: {} }; }
      return { where: 0, scale: { priceScaleId: 'ind:' + inst.uid, lastValueVisible: false } };
    };
    const pin = (s, where, top) => { if (where === 0) s.priceScale().applyOptions({ scaleMargins: { top, bottom: 0 } }); };
    for (const inst of this.cfg.indicators) {
      const k = C.serverKey(inst);
      switch (inst.id) {
        case 'volume': {
          const { where } = spot(inst);
          const s = add(inst, '__vol', null, LW.HistogramSeries, { priceFormat: { type: 'volume' },
            ...(where === 0 ? { priceScaleId: 'vol', lastValueVisible: false } : { lastValueVisible: true }) }, where);
          pin(s, where, VOL_TOP);
          break;
        }
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
          const { where, scale } = spot(inst);
          const a = line(inst, k, null, P.text, 2, where, scale);
          line(inst, k, 'p', P.up, 1, where, scale); line(inst, k, 'm', P.down, 1, where, scale);
          pin(a, where, MAIN_TOP);   // the three lines share the one scale
          break;
        }
        case 'delta': {
          const { where, scale } = spot(inst);
          pin(add(inst, '__delta', null, LW.HistogramSeries, { lastValueVisible: true, priceFormat: { ...WHOLE }, ...scale }, where),
            where, MAIN_TOP);
          break;
        }
        case 'cumdelta': {
          this.colorOf[inst.uid] = P.cum;
          const { where, scale } = spot(inst);
          pin(line(inst, k, null, P.cum, 2, where, { priceFormat: { ...WHOLE }, ...scale }), where, MAIN_TOP);
          break;
        }
        default:   // levels, footprint, profile, big prints: price lines, layers and markers
          break;
      }
    }
  }
```

`build()` needs no change: its stretch-factor loop already sizes however many sub-panes `buildSeries` made. Task 9's `onOlder` re-sets every entry of `this.lines`, including the ones on the price pane.

In `legendRows()` (Task 7's version), after `btns.append(iconButton('x', 'Remove', 'x'));`, add:

```js
      if (C.movable(inst.id)) {   // TradingView's "More": move to the price pane / to a pane below
        const more = iconButton('ellipsis', 'More', 'more');
        more.setAttribute('aria-haspopup', 'menu');
        more.setAttribute('aria-expanded', 'false');
        btns.append(more);
      }
```

In `onLegendClick`, replace the last two branches with:

```js
    else if (b.dataset.act === 'gear') this.host.onSettings(this, uid);
    else if (b.dataset.act === 'more') this.host.onIndicatorMenu(this, uid, { anchor: b });
    else this.removeIndicator(uid);
```

Add these methods after `setVisible`:

```js
  removeIndicator(uid) { this.update({ indicators: this.cfg.indicators.filter((x) => x.uid !== uid) }); }

  /* Move a pane-type indicator to 'main' (the price pane) or 'own' (a pane below). The chart is rebuilt
     through update() (view kept, no resubscribe: the studies are the same), as the legend's × does. */
  setPlacement(uid, pane) {
    const inst = this.cfg.indicators.find((x) => x.uid === uid);
    if (!inst || !C.movable(inst.id) || !C.PANES.includes(pane) || C.placement(inst) === pane) return;
    this.update({ indicators: this.cfg.indicators.map((x) => (x.uid === uid ? { ...x, pane } : x)) });
  }

  /* The pane under a viewport y: its index, or -1 (a separator, outside the chart). */
  paneAt(clientY) {
    const panes = this.chart ? this.chart.panes() : [];
    for (let i = 0; i < panes.length; i++) {
      const el = panes[i].getHTMLElement();
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (clientY >= r.top && clientY < r.bottom) return i;
    }
    return -1;
  }

  /* Right-click (and, from the drawing controller, a double-click on empty price-pane space: dbl): the chart
     menu on the price pane with the tick-rounded price under the pointer; an indicator's own menu in its pane
     (right-click only); nothing on the axes. The browser's own menu never shows over a chart. */
  onMenu(e, dbl = false) {
    e.preventDefault();
    if (!this.chart || !this.bars.length) return;
    const r = this.box.getBoundingClientRect(), x = e.clientX - r.left;
    if (x < 0 || x >= this.box.clientWidth - this.chart.priceScale('right').width()) return;   // the price axis
    const i = this.paneAt(e.clientY), at = { x: e.clientX, y: e.clientY };
    if (i === 0) {
      const top = this.chart.panes()[0].getHTMLElement().getBoundingClientRect().top;
      const raw = this.candles.coordinateToPrice(e.clientY - top);
      this.host.onChartMenu(this, { ...at, price: raw == null ? null : window.HBDrawings.roundToTick(raw, this.tick) });
    } else if (i > 0 && !dbl && this.paneUid[i]) {
      this.host.onIndicatorMenu(this, this.paneUid[i], { at });
    }
  }

  /* Reset chart view (the menu, ⌥R): the default bar spacing with the latest bar at the right margin, and every
     pane's price scale back to auto (T10-R1). */
  resetView() {
    if (!this.chart) return;
    this.chart.timeScale().resetTimeScale();
    this.chart.panes().forEach((_, i) => this.chart.priceScale('right', i).applyOptions({ autoScale: true }));
  }
```

- [ ] **Step 9: `drawings.js`, a double-click on empty space.** In `Controller.onDbl`, keep the position loop, and after it (before the method's closing brace) add:

```js
    // on any other drawing: its own behaviour (none yet), no menu
    if (all.some((d) => hitTest(d, pt, geo))) return;
    // empty chart space: the chart menu (spec §7), and not Lightweight Charts' own double-click
    e.stopPropagation();
    this.cell.onMenu(e, true);
```

Update the method's comment to: `/* Double-click (cursor mode): on a long/short box, select it and open its settings (host.onPosition); on empty price-pane space, the chart menu (Cell.onMenu). Captured before Lightweight Charts sees it: its own double-click would reset the price scale. */`. The early returns (a drawing tool picked, outside the price pane) stay, so neither case opens a menu.

- [ ] **Step 10: `app.js`, menus at the pointer, the chart menu, the indicator menu, keys.**

Next to `let menuRight = false;`, add `let menuAt = null;   // the open menu is a context menu at this viewport point {x, y}`.

Replace `openMenu` (Task 6's version) and `closeMenu`, and add the pointer branch at the top of `placeMenu`:

```js
/* One popup menu at a time: under its toolbar button, right of a rail button (right), or at the pointer (at: a
   context menu, anchor null). root: the element it is appended to (a dialog's box for in-dialog menus). */
function openMenu(anchor, cls, { right = false, root = null, at = null } = {}) {
  closeMenu();
  const m = mk('div', 'menu' + (cls ? ' ' + cls : ''));
  m.setAttribute('role', 'menu');
  (root || $('#menuRoot')).appendChild(m);
  menuEl = m; menuAnchor = anchor; menuRight = right; menuAt = at;
  if (anchor) { anchor.classList.add('open'); anchor.setAttribute('aria-expanded', 'true'); }
  return m;
}
```

```js
function placeMenu() {
  if (!menuEl) return;
  const w = menuEl.offsetWidth, h = menuEl.offsetHeight;
  if (menuAt) {   // a context menu: at the pointer, kept inside the window
    menuEl.style.left = Math.max(4, Math.min(menuAt.x, window.innerWidth - w - 4)) + 'px';
    menuEl.style.top = Math.max(4, Math.min(menuAt.y, window.innerHeight - h - 4)) + 'px';
    return;
  }
  // … the rest of Task 6's placeMenu, unchanged (the menuRight branch, then below / flipped above the anchor)
}
```

```js
function closeMenu() {
  if (!menuEl) return;
  const back = menuAnchor && menuEl.contains(document.activeElement) ? menuAnchor : null;   // keyboard focus goes back to the button
  menuEl.remove();
  if (menuAnchor) { menuAnchor.classList.remove('open'); menuAnchor.setAttribute('aria-expanded', 'false'); }
  menuEl = menuAnchor = menuAt = null;
  customWait = null;
  if (back) back.focus();
}
```

In `init()`, the outside-click listener becomes:

```js
  document.addEventListener('pointerdown', (e) => {
    if (menuEl && !menuEl.contains(e.target) && !(menuAnchor && menuAnchor.contains(e.target))) closeMenu();
  }, true);
```

(A right-click's pointerdown closes an open menu before its `contextmenu` opens the new one.)

In `hostFor`, add:

```js
    onChartMenu(cell, at) { chartMenu(cell, at); },
    onIndicatorMenu(cell, uid, o) { indicatorMenu(cell, uid, o); },
```

Add after `chartSettings()`:

```js
/* ---- the chart's context menu (spec §7) ---- */
/* The built-in items' actions (HBChartMenu items carry `act`; an extension's carry their own run). */
const MENU_ACTS = {
  reset: (ctx) => ctx.cell.resetView(),
  copy: (ctx, it) => {   // silent when the clipboard is unavailable or refused
    try { navigator.clipboard.writeText(it.copy).catch(() => {}); } catch (_) { /* no clipboard */ }
  },
  removeDrawings: (ctx) => drawings.clear(ctx.root),
  removeIndicators: (ctx) => ctx.cell.update({ indicators: [] }),
  settings: () => chartSettings(),
};

/* Right-click on a chart's price pane, or a double-click on its empty space: the chart menu at the pointer, for
   that chart (it becomes the selected one). Remove N drawings asks twice, like the rail's Remove all: the first
   click arms it for 3 s (the menu stays open), the second removes. */
function chartMenu(cell, at) {
  const i = cells.indexOf(cell);
  if (i < 0) return;
  select(i);
  const root = cell.shown ? cell.shown.root : cell.cfg.root;
  const ctx = { cell, root, price: at.price, tick: cell.tick, nDrawings: drawings.list(root).length,
    nIndicators: cell.cfg.indicators.length };
  const m = openMenu(null, 'menu-chart', { at });
  let armed = 0;
  for (const it of window.HBChartMenu.items(ctx)) {
    if (it.sep) { m.appendChild(mk('div', 'menu-sep')); continue; }
    const b = menuItem(it.text, it.sub || '', () => {
      if (it.act === 'removeDrawings' && !armed) {
        b.classList.add('arm');
        b.querySelector('.menu-t').textContent = window.HBChartMenu.armText(ctx.nDrawings, root);
        armed = setTimeout(() => { armed = 0; b.classList.remove('arm'); b.querySelector('.menu-t').textContent = it.text; }, 3000);
        return;
      }
      clearTimeout(armed);
      closeMenu();
      if (it.run) {
        try { it.run(ctx); } catch (e) { sbNote(`menu: ${e && e.message ? e.message : e}`); }
        return;
      }
      if (MENU_ACTS[it.act]) MENU_ACTS[it.act](ctx, it);
    });
    m.appendChild(b);
  }
  placeMenu();
  m.tabIndex = -1;   // the arrow keys start from the menu
  m.focus({ preventScroll: true });
}

/* An indicator's own menu: from its legend ⋯ (anchor; a second click closes it) or a right-click in its pane (at). */
function indicatorMenu(cell, uid, { anchor = null, at = null } = {}) {
  if (anchor && menuAnchor === anchor) { closeMenu(); return; }
  const inst = cell.cfg.indicators.find((x) => x.uid === uid), i = cells.indexOf(cell);
  if (!inst || i < 0) return;
  select(i);
  const m = openMenu(anchor, 'menu-ind', { at });
  for (const it of window.HBChartMenu.paneItems(inst)) {
    m.appendChild(menuItem(it.text, '', () => {
      closeMenu();
      if (it.act === 'move') cell.setPlacement(uid, it.pane); else cell.removeIndicator(uid);
    }));
  }
  placeMenu();
  if (at) { m.tabIndex = -1; m.focus({ preventScroll: true }); }
}
```

In `onKey`, right after `const c = cur();`, add:

```js
  if (menuEl && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {   // walk the open menu's items
    const items = [...menuEl.querySelectorAll('.menu-i')].filter((b) => !b.disabled && b.offsetParent !== null);
    const k = window.HBChartMenu.step(items.indexOf(document.activeElement), items.length, e.key);
    if (k >= 0) { e.preventDefault(); items[k].focus(); }
    return;
  }
  if (e.altKey && !e.metaKey && !e.ctrlKey && e.code === 'KeyR') {   // ⌥R: Reset chart view (e.key is ® on macOS)
    e.preventDefault();
    if (c) c.resetView();
    return;
  }
```

These run after the input/textarea check, so a menu's search or name field keeps its own arrow keys, and a dialog's keys never reach them (the dialog branch returns first).

- [ ] **Step 11: Shell, styles, icons.**

`icons.js`: add `ellipsis` to the header's Lucide list and add:

```js
  ellipsis: svg('<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>'),
```

`charts.html`:
- Add `<script src="/static/charts/chartmenu.js?v=3"></script>` right before the `app.js` script tag (after `settings-dialog.js`).
- Set `catalog.js` to `?v=3` if it is not already.

The script order becomes: lightweight-charts, icons, catalog, primitives, drawings, position, settings, events, scrollback, cell, settings-dialog, chartmenu, app.

`charts.css`: change `.lg-row:hover .lg-btns, .lg-row:focus-within .lg-btns { display: inline-flex; }` to

```css
.lg-row:hover .lg-btns, .lg-row:focus-within .lg-btns, .lg-btns:has(.ib.open) { display: inline-flex; }
```

(the ⋯ stays visible while its menu is open), and append:

```css
/* ---- the chart's context menu and an indicator's menu (chartmenu.js) ---- */
.menu:focus { outline: none; }   /* a context menu takes focus itself; its items show the focus ring */
.menu-chart { min-width: 240px; }
.menu-chart .menu-sub { font-variant-numeric: tabular-nums; }
.menu-i.arm .menu-t { color: var(--down); }
.ib.open { background: var(--border); }
```

- [ ] **Step 12: Syntax-check and run the suites**

Run: `for f in homebase/static/charts/*.js; do node --check "$f" || echo "FAIL $f"; done`, then `node --test tests/js/*.test.mjs`, then `.venv/bin/python -m pytest -q`
Expected: no `FAIL`; all green. `tests/test_charts_js.py` picks up `chartmenu.test.mjs` by itself.

- [ ] **Step 13: Commit**

```bash
git add homebase/static/charts/chartmenu.js tests/js/chartmenu.test.mjs homebase/static/charts/catalog.js tests/js/catalog.test.mjs homebase/static/charts/cell.js homebase/static/charts/drawings.js homebase/static/charts/app.js homebase/static/charts.html homebase/static/charts/charts.css homebase/static/charts/icons.js
git commit -m "feat(charts): chart context menu (right-click / double-click: Reset view, Copy price, Remove drawings/indicators, Settings) with an extension point for trading items; Volume, Delta, Cumulative delta and ADX move between their own pane and the price chart

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Controller browser check (replay :8854; a 2×2 layout; NQ 1m with Volume, VWAP, Delta and Cumulative delta):**
- Opening the chart menu:
  - Right-click in the price pane opens the menu at the pointer, with no browser menu. Near the window's right or bottom edge it stays inside the window.
  - The chart under the pointer becomes the selected one.
  - Order and dividers: `Reset chart view ⌥R` │ `Copy price 30,878.00` │ `Remove N drawings` · `Remove N indicators` │ `Settings…`.
  - With no drawings on the symbol, `Remove … drawings` is absent; with no indicators, `Remove … indicators` is absent. Neither case leaves a doubled divider.
  - Right-click on the price axis or the time axis opens no menu (and no browser menu).
- Double-click:
  - On empty price-pane space with the cursor tool, it opens the same menu.
  - On a long/short box, it still opens the position settings, not the menu.
  - On a trend line, it opens no menu.
  - With a drawing tool picked, a double-click places points and opens no menu.
- Closing and keys: Esc and an outside click close the menu. ↓/↑ walk the items and wrap, Home/End jump, and Enter runs the focused item. Every item shows the 2px `--accent` focus ring.
- The actions:
  - `Reset chart view` returns a zoomed and panned chart to the default spacing at the latest bar, with each pane's scale on auto. ⌥R does the same on the selected chart.
  - `Copy price`: the row's price matches the crosshair's axis label (tick-rounded). Pasting in a text field gives `30878.00`.
  - `Remove 3 drawings`: the first click turns the row red with `Click again to remove 3 drawings on NQ` and keeps the menu open; a second click within 3 s removes them on every chart of NQ; waiting 3 s restores the row.
  - `Remove N indicators` removes all of them in one click.
  - `Settings…` opens the chart Settings dialog (Task 6) for this chart.
- Moving indicators:
  - Hovering Delta's legend row shows eye · × · ⋯. VWAP's row has no ⋯.
  - ⋯ → `Move to main chart`: Delta's pane disappears, and its histogram sits in the bottom quarter of the price pane. The price scale's range does not change (compare the axis before and after), and zooming out does not stretch the price scale to fit Delta.
  - ⋯ → `Move to new pane below` brings the pane back at 90 px.
  - The same works for Cumulative delta and ADX.
  - Volume's ⋯ offers `Move to new pane below`; in its own pane its histogram has a visible axis.
  - Right-clicking inside Cumulative delta's pane opens its menu (Move to main chart / Remove), not the chart menu.
  - `Remove` in that menu removes the indicator.
- Persistence:
  - Save the layout and reload the page: every placement is restored.
  - Change the symbol and the interval: placements are kept.
  - An old saved layout without `pane` loads as before (Volume on the price pane; Delta, Cumulative delta and ADX in panes).
- Deep history (Task 9): with Delta on the main chart, scroll back. Delta's bars continue into the older sessions, and the view does not jump.
- The extension point: in the console, run `HBChartMenu.register('trading', (ctx) => [{ text: 'Buy test @ ' + ctx.price, run: (c) => console.log('buy', c.price) }])`, then right-click. A new section appears between Copy price and Remove, and clicking it logs the price. Reload afterwards; the registration is not persisted.
- Dark theme: the menu and the ⋯ button follow the tokens. Zero console errors.

---
