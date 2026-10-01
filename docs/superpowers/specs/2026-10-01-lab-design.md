# The Lab (the Backtest page, "Code" mode) — design

2026-10-01. The Backtest page becomes **Lab**: a TradingView-Pine-editor-like place to write or paste a Python
strategy, validate it, backtest it, see its trades on a chart and save it. The URL stays `/backtest`; the native Mac
toolbar still says "Backtest" until the app is rebuilt.

## What is on the page
* **Code mode** (default): library (My strategies · Built-in, read-only) | editor | result. **Chart mode** is the
  unchanged chart shell with the Strategy Tester underneath; "Show trades on the chart" switches to it and loads
  the run through the existing `POST /api/tester/show` (refused 09:20–09:35 ET like every chart move).
* **Insert a script** (the Pine "open a new script" flow): *New strategy* ▸ Paste a script / Open a .py file /
  Stop straddle · Bar breakout · Blank. Pasting into an empty new strategy names it from its `name =` or class.
  A .py file can also be dropped on the editor. Saving writes `~/.homebase/strategies/<name>.py`.
* Editor: highlighting, line numbers, Tab/Shift+Tab/Enter indent, ⌘/ comment, ⌘S save, ⌘↵ run, live validation
  with the failing line marked. Run saves first; settings (range, contracts, fees, slippage, the script's own
  inputs) sit under the result. A strategy's last run is shown again when it is reopened.

## Safety (unchanged rules, pinned by tests)
* A draft is text. The chart service lists/validates it from an AST read (`draftstore.static_meta`); the only place
  its code runs is the sandboxed backtest child (`runner exec`). The Lab adds routes that **write and read text
  only**: `GET/PUT/DELETE /api/tester/drafts…`, `POST /drafts/validate`, `GET /drafts/templates`. Every write passes
  the Host allowlist, the Origin check and a JSON content-type check.
* The Lab page calls only `/api/tester/*` (pinned in `tests/js/lab-isolation.test.mjs`): no desk URL, no order,
  no arm/kill. The desk never reads the drafts directory (`tests/test_claude_drafts.py`).

## Draft → live: a reviewed hand-off, never a button
1. Draft and backtest in the Lab (research window by default; 2025+ is flagged and recorded).
2. **Request review…** writes a package under `~/.homebase/review-requests/<ts>-<name>.{json,md}`: the code and its
   sha256, the attached run's numbers, the automatic checks (parses, `session_independent`, ≥30 trades, inside the
   research window, no strategy errors, fees and slippage on) and the manual checklist (look-ahead, repaint,
   sizing, prop rules and the 9:30 window, fees, desk port). Text only: nothing runs, nothing is promoted.
3. A person (and Claude) reviews it and ports the strategy into the desk's own code (`homebase/strategies`,
   `config.json`) — a separate, deliberate change.
4. It first runs on the desk as a **shadow** strategy (journals signals, places nothing); the person switches it
   live themselves. Draft code is never executed in the process that holds broker logins.
A faster path can be added later; it is a product decision, not a code shortcut.

## Not in this pass
Walk-forward / heat-map / Monte Carlo launch from the Lab (they stay in the Strategy Tester under Chart mode);
renaming the native toolbar item; multi-file strategies; an in-editor autocomplete.
