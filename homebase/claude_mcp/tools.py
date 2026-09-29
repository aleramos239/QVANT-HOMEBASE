"""The Strategy Tester tools: JSON schemas, handlers, and the compact text each returns.

Every handler goes through Client (loopback :8852, /api/tester/* only) -- except write_strategy /
delete_draft, which write/remove one file in the drafts dir through homebase.draftstore (text only;
the chart service loads drafts in a child process, never in-process).

Long jobs (backtest, heatmap, walkforward) poll until done, up to `wait_s` (default 120 s); past that
they return the job id and its progress, and the same tool called with that id picks the wait back up.
`cancel` stops a run, heat-map or walk-forward (the tester's own cancel routes).
"""
from __future__ import annotations

import datetime as dt
import inspect
import time
import urllib.parse
from collections import OrderedDict
from zoneinfo import ZoneInfo

from .. import draftstore
from .client import Client, ToolError, base_url
from .desk_tools import SPECS as DESK_SPECS
from .desk_tools import DeskMixin

ET = ZoneInfo("America/New_York")
FINAL = ("done", "error", "cancelled")
DEFAULT_WAIT_S = 120           # short: the stdio loop is single-threaded, so a long wait blocks every call
MAX_WAIT_S = 3600
PRESETS = {"2021-2024": ("2021-01-01", "2024-12-31"), "2022-2024": ("2022-01-01", "2024-12-31"),
           "2025-2026": ("2025-01-01", None), "all": ("2021-01-01", None)}
TRADE_SORTS = ("entry", "net", "-net", "mae", "mfe", "duration")
MAX_TRADE_ROWS = 500


def describe_target() -> str:
    try:
        return base_url()
    except ToolError as e:
        return str(e)


# ---------------------------------------------------------------- schemas

_RANGE = {
    "type": "object",
    "description": "The test window. Default: the research window 2021-2024. Presets mirror the page's range "
                   "pill; 2025-2026 and all run to today (ET). custom needs start and end (YYYY-MM-DD).",
    "properties": {"preset": {"type": "string", "enum": [*PRESETS, "custom"], "default": "2021-2024"},
                   "start": {"type": "string", "description": "YYYY-MM-DD (custom only)"},
                   "end": {"type": "string", "description": "YYYY-MM-DD (custom only)"}},
    "additionalProperties": False}
_COSTS = {
    "type": "object", "description": "Sizing and friction. Defaults: qty 1, $4.00 commission per round turn "
                                     "per contract, 1 tick slippage, $50,000 capital.",
    "properties": {"qty": {"type": "integer", "minimum": 1, "maximum": 100},
                   "commission": {"type": "number", "minimum": 0, "maximum": 100},
                   "slippage_ticks": {"type": "number", "minimum": 0, "maximum": 20},
                   "capital": {"type": "number", "minimum": 1}},
    "additionalProperties": False}
_INPUTS = {"type": "object", "description": "Strategy inputs by key (see list_strategies / read_strategy); "
                                            "anything left out takes its default.",
           "additionalProperties": True}
_AXES = {"type": "array", "minItems": 2, "maxItems": 3,
         "description": "2 or 3 numeric/bool/choice inputs to vary, each with its list of values.",
         "items": {"type": "object", "required": ["key", "values"],
                   "properties": {"key": {"type": "string"}, "values": {"type": "array", "minItems": 1}},
                   "additionalProperties": False}}
_PROP = {"type": "string", "description": "A prop-eval rule set id from list_prop_rules (default: the server's)."}
_WAIT = {"type": "integer", "minimum": 0, "maximum": MAX_WAIT_S,
         "description": f"Seconds to wait for the job (default {DEFAULT_WAIT_S}); 0 = start it and return the id."}
_RUN_REF = {"run_id": {"type": "string", "description": "A run id (from backtest / list_runs)."},
            "grid_id": {"type": "string", "description": "A heat-map id; with `cell`, one of its cells."},
            "cell": {"type": "integer", "minimum": 0, "description": "The heat-map cell index (with grid_id)."}}


def _spec(name, description, props=None, required=()):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props or {}, "required": list(required),
                            "additionalProperties": False}}


SPECS = [
    _spec("list_strategies", "List every strategy the Strategy Tester can run: built-ins and DRAFT strategies "
          "(id draft_<name>), each with its root and its inputs (key, type, default, min..max). A draft that does "
          "not load is listed with its error."),
    _spec("read_strategy", "One strategy's catalog entry (inputs, defaults) and its full source text, plus the "
          "DRAFT template: the rules and the ctx API a new strategy must follow. Read this before write_strategy.",
          {"strategy": {"type": "string", "description": "A strategy id from list_strategies."}}, ["strategy"]),
    _spec("backtest", "Run one tick-replay backtest (exactly what the page's Run button does) and wait for it. "
          "Returns net $, Sharpe, win rate, profit factor, max drawdown, trades (all/long/short), a by-year "
          "table, data coverage and the prop-eval headline, plus the run_id for trades / montecarlo / prop_eval / "
          "show_on_chart. Refused 09:20-09:35 ET on weekdays and queued behind the 2-backtest machine cap. "
          "Pass run_id instead to keep waiting on a run started earlier. Walk-forward: use the walkforward tool.",
          {"strategy": {"type": "string"}, "inputs": _INPUTS, "range": _RANGE, "costs": _COSTS,
           "prop_rules": _PROP, "wait_s": _WAIT,
           "run_id": {"type": "string", "description": "Wait on this existing run instead of starting one."}}),
    _spec("heatmap", "Run a parameter heat-map: every combination of 2-3 inputs' values is a full backtest "
          "(<= max_cells, default 60). Returns one row per cell (params, net $, Sharpe, WR, PF, max DD, trades) "
          "and the looks counter (at 5%, ~looks/20 cells look significant by luck). Pass grid_id to keep waiting "
          "on an existing heat-map.",
          {"strategy": {"type": "string"}, "axes": _AXES, "inputs": _INPUTS, "range": _RANGE, "costs": _COSTS,
           "prop_rules": _PROP, "max_cells": {"type": "integer", "minimum": 1, "maximum": 400},
           "wait_s": _WAIT, "grid_id": {"type": "string", "description": "Wait on this existing heat-map."}}),
    _spec("walkforward", "Walk-forward over a heat-map grid: select the best cell on 1 month, test it on the next "
          "`ratio` months, step monthly, stitch the out-of-sample legs. Returns stitched OOS vs in-sample stats "
          "(per month), the drop, pick stability and the per-step table. The strategy must be "
          "session_independent. Pass walkforward_id to keep waiting on an existing one. A 1:1 · 1:2 · 1:3 compare "
          "job (started from the chart page) returns its side-by-side stitched OOS summary; pass test_months with "
          "its walkforward_id for one scheme's full result.",
          {"strategy": {"type": "string"}, "axes": _AXES, "ratio": {"type": "integer", "enum": [1, 2, 3], "default": 3},
           "metric": {"type": "string", "enum": ["net_profit", "sharpe", "profit_factor", "t_stat"]},
           "min_trades": {"type": "integer", "minimum": 1, "maximum": 1000},
           "inputs": _INPUTS, "range": _RANGE, "costs": _COSTS, "prop_rules": _PROP,
           "max_cells": {"type": "integer", "minimum": 1, "maximum": 400}, "wait_s": _WAIT,
           "walkforward_id": {"type": "string", "description": "Wait on this existing walk-forward."},
           "test_months": {"type": "integer", "enum": [1, 2, 3],
                           "description": "With walkforward_id: which scheme's full result (a compare job's 1:N)."}}),
    _spec("montecarlo", "Monte Carlo over a finished run's (or heat-map cell's) trades, resampled by day: "
          "max-drawdown / final-net / losing-streak percentiles, P(ruin) below the floor and P(prop pass).",
          {**_RUN_REF, "paths": {"type": "integer", "minimum": 1, "maximum": 10000},
           "mode": {"type": "string", "enum": ["shuffle", "bootstrap"]},
           "floor": {"type": "number", "description": "Ruin floor: a drawdown in $ (default: the rules' trailing max loss)."},
           "seed": {"type": "integer"}}),
    _spec("prop_eval", "Re-score a finished run (or heat-map cell) under another prop-eval rule set: eval pass %, "
          "bust %, median days to pass, funded payout % and the expected first cheque.",
          {**_RUN_REF, "prop_rules": _PROP}, ["prop_rules"]),
    _spec("list_prop_rules", "The prop-eval rule sets (id, name, version, confirmed)."),
    _spec("list_runs", "Recent jobs, newest first: single runs (default), heat-maps or walk-forwards.",
          {"kind": {"type": "string", "enum": ["runs", "heatmaps", "walkforwards"], "default": "runs"},
           "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 15}}),
    _spec("get_run", "A run's (or heat-map cell's) status, or -- when done -- its full summary (as backtest returns).",
          dict(_RUN_REF)),
    _spec("trades", "A finished run's (or heat-map cell's) trade list, a page at a time. `#` is the trade index "
          "show_on_chart's focus.trade_index takes. Times are ET.",
          {**_RUN_REF, "offset": {"type": "integer", "minimum": 0, "default": 0},
           "limit": {"type": "integer", "minimum": 1, "maximum": MAX_TRADE_ROWS, "default": 50},
           "sort": {"type": "string", "enum": list(TRADE_SORTS), "default": "entry",
                    "description": "entry = chronological; net = worst first; -net = best first; mae / mfe = "
                                   "largest adverse / favourable excursion first; duration = longest first."}}),
    _spec("show_on_chart", "Show a finished run (or heat-map cell) on the user's open chart page: it opens the "
          "Strategy Tester tab, loads the run like a click on Recent runs, puts it on a chart of the run's "
          "instrument and scrolls to the focus. The page never touches a chart in Bar Replay and never changes the "
          "instrument of a chart that has accounts or an algo on it (it says so in its status bar instead).",
          {**_RUN_REF, "focus": {"type": "object", "description": "Optional: exactly one of trade_index (from "
                                 "trades), date (YYYY-MM-DD: the first trade on/after it) or time_ms (epoch ms).",
                                 "properties": {"trade_index": {"type": "integer", "minimum": 0},
                                                "date": {"type": "string"}, "time_ms": {"type": "integer"}},
                                 "additionalProperties": False}}),
    _spec("cancel", "Cancel a queued or running job: a single run (run_id), a heat-map (grid_id) or a "
          "walk-forward (walkforward_id). Uses the Strategy Tester's own cancel; a finished job is left as it is.",
          {"run_id": {"type": "string"}, "grid_id": {"type": "string"}, "walkforward_id": {"type": "string"}}),
    _spec("write_strategy", "Create or replace a DRAFT strategy: writes ~/.homebase/strategies/<name>.py (only "
          "that file) after checking its syntax, and reports the inputs the tester read from its text (nothing "
          "runs). Its tester id is draft_<name>; backtest it like any strategy -- the backtest is the only place "
          "its code runs, inside a sandbox (no network, no files outside its run dir, 20 min max). Drafts never "
          "trade. Follow the template read_strategy returns: literal class attributes and a literal "
          "`return [Input(...), ...]`.",
          {"name": {"type": "string", "description": "a-z, 0-9, '_' (2-40 chars, starting with a letter); not a "
                                                     "built-in strategy's name."},
           "code": {"type": "string", "description": "The complete Python source."}}, ["name", "code"]),
    _spec("delete_draft", "Delete a DRAFT strategy's file (its finished runs stay listed).",
          {"name": {"type": "string", "description": "The draft's name (without draft_)."}}, ["name"]),
] + DESK_SPECS


# ---------------------------------------------------------------- formatting

def _num(v, fmt="{:,.2f}", dash="—"):
    if v is None:
        return dash
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return str(v)


def _usd(v):
    if v is None:
        return "—"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def _pct(v, frac=False):
    if v is None:
        return "—"
    return f"{v * 100:.1f}%" if frac else f"{v:.1f}%"


def _table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


STAT_HEAD = ["", "trades", "net $", "Sharpe", "win %", "PF", "max DD $", "avg $", "t"]


def _stat_row(label, c):
    c = c or {}
    return [label, c.get("trades", 0), _usd(c.get("net_profit")), _num(c.get("sharpe")), _pct(c.get("win_rate")),
            _num(c.get("profit_factor")), _usd(c.get("max_drawdown")), _usd(c.get("avg_trade")), _num(c.get("t_stat"))]


def _et(ms):
    if ms is None:
        return "—"
    return dt.datetime.fromtimestamp(ms / 1000, ET).strftime("%Y-%m-%d %H:%M:%S")


def _kv(d):
    return ", ".join(f"{k}={v}" for k, v in (d or {}).items()) or "(none)"


def _prop_line(p) -> str:
    if not p:
        return "Prop eval: none"
    label = (p.get("rules") or {}).get("label") or (p.get("rules") or {}).get("name") or "?"
    if p.get("error"):
        return f"Prop eval ({label}): error -- {p['error']}"
    if p.get("skipped"):
        return f"Prop eval ({label}): {p['skipped']}"
    h = p.get("headline") or {}
    ci = h.get("eval_pass_ci")
    ci_s = f" [{_pct(ci[0], True)}–{_pct(ci[1], True)}]" if isinstance(ci, (list, tuple)) and len(ci) == 2 else ""
    return (f"Prop eval ({label}): pass {_pct(h.get('eval_pass_p'), True)}{ci_s}, bust {_pct(h.get('bust_p'), True)}, "
            f"timeout {_pct(h.get('timeout_p'), True)}, median days to pass {_num(h.get('median_days_to_pass'), '{:g}')}, "
            f"funded payout {_pct(h.get('funded_payout_p'), True)}, E[cheque] {_usd(h.get('funded_expected_cheque'))}")


def _ref_text(ref: dict) -> str:
    return f"grid_id={ref['grid_id']!r}, cell={ref['cell']}" if "grid_id" in ref else f"run_id={ref['run_id']!r}"


def bundle_summary(b: dict, ref: dict) -> str:
    run = b.get("run") or {}
    rep = run.get("report") or {}
    s = rep.get("summary") or {}
    st = run.get("strategy") or {}
    rng = run.get("range") or {}
    cov = run.get("coverage") or {}
    lines = [f"{'Heat-map cell' if 'grid_id' in ref else 'Run'} {run.get('id')} · {st.get('name')} ({st.get('id')}) on "
             f"{st.get('root')} · {rng.get('label') or rng}"
             + (" · reads 2025+ data" if run.get("holdout") else ""),
             f"Costs: qty {run.get('qty')}, ${_num(run.get('commission'))}/RT, {run.get('slippage_ticks')} tick slip, "
             f"capital {_usd(run.get('capital'))} · engine {run.get('engine')} ({run.get('fill_law')})",
             f"Inputs: {_kv(run.get('inputs'))}", "",
             _table(STAT_HEAD, [_stat_row(k, s.get(k)) for k in ("all", "long", "short")])]
    years = rep.get("by_year") or []
    if years:
        lines += ["", "By year:", _table(["year", "trades", "net $", "Sharpe", "win %", "PF", "max DD $"],
                                         [[y.get("period"), y.get("trades"), _usd(y.get("net")), _num(y.get("sharpe")),
                                           _pct(y.get("win_rate")), _num(y.get("profit_factor")),
                                           _usd(y.get("max_drawdown"))] for y in years])]
    reasons = cov.get("skipped_by_reason") or {}
    lines += ["", f"Coverage: {cov.get('used')}/{cov.get('sessions')} sessions used"
              + (f"; skipped {_kv(reasons)}" if reasons else "")
              + f"; {len(cov.get('no_trade') or [])} no-trade sessions"
              + (f"; {rep.get('skipped_by_error')} STRATEGY ERRORS" if rep.get("skipped_by_error") else ""),
              _prop_line(b.get("propsim")), "",
              f"Next: trades({_ref_text(ref)}), montecarlo(...), prop_eval(...), show_on_chart({_ref_text(ref)})"]
    return "\n".join(lines)


def _progress(st: dict) -> str:
    s = st.get("status")
    bits = [str(s)]
    if st.get("phase") and st.get("phase") != s:
        bits.append(str(st["phase"]))
    if st.get("total"):
        bits.append(f"{st.get('done', 0)}/{st['total']}")
    if st.get("queue_position"):
        bits.append(f"queue #{st['queue_position']}")
    if st.get("paused"):
        bits.append(st["paused"])
    if st.get("eta_s"):
        bits.append(f"eta {st['eta_s']:.0f}s")
    return " · ".join(bits)


# ---------------------------------------------------------------- the toolbox

def range_body(rng, today: str | None = None) -> dict:
    """The page's range pill as the server's range: 2021-2024 is {kind: research} (byte for byte what the
    page sends); the other presets are custom windows, `end: today` (ET) for the open-ended ones."""
    rng = rng or {}
    if not isinstance(rng, dict):
        raise ToolError("range: an object {preset, start?, end?}")
    extra = set(rng) - {"preset", "start", "end"}
    if extra:
        raise ToolError(f"range: unknown key(s) {', '.join(sorted(extra))} (walk-forward: use the walkforward tool)")
    preset = rng.get("preset", "2021-2024")
    if preset == "custom":
        if not rng.get("start") or not rng.get("end"):
            raise ToolError("range: a custom range needs start and end (YYYY-MM-DD)")
        return {"kind": "custom", "start": str(rng["start"]), "end": str(rng["end"])}
    if preset not in PRESETS:
        raise ToolError(f"range.preset: one of {', '.join([*PRESETS, 'custom'])}")
    if rng.get("start") or rng.get("end"):
        raise ToolError("range: start/end go with preset 'custom'")
    if preset == "2021-2024":
        return {"kind": "research"}
    start, end = PRESETS[preset]
    return {"kind": "custom", "start": start, "end": end or today or dt.datetime.now(ET).date().isoformat()}


def _costs(costs) -> dict:
    costs = costs or {}
    if not isinstance(costs, dict):
        raise ToolError("costs: an object")
    extra = set(costs) - {"qty", "commission", "slippage_ticks", "capital"}
    if extra:
        raise ToolError(f"costs: unknown key(s) {', '.join(sorted(extra))}")
    return dict(costs)


def _ref(args: dict) -> dict:
    has_run, has_grid = args.get("run_id") is not None, args.get("grid_id") is not None or args.get("cell") is not None
    if has_run == has_grid:
        raise ToolError("give either run_id, or grid_id + cell")
    if has_run:
        return {"run_id": str(args["run_id"])}
    if args.get("grid_id") is None or args.get("cell") is None:
        raise ToolError("a heat-map cell needs both grid_id and cell")
    return {"grid_id": str(args["grid_id"]), "cell": int(args["cell"])}


def _q(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _compare_text(wid: str, s: dict) -> str:
    """A compare job's summary: the three stitched OUT-OF-SAMPLE results side by side (nothing in-sample)."""
    sc, w, lb = s.get("scheme") or {}, s.get("window") or {}, s.get("looks_basis") or {}
    sm = s.get("shared_months") or {}
    cols = s.get("schemes") or []
    lines = [f"Walk-forward compare {wid} · 1:1 · 1:2 · 1:3 · select by {sc.get('metric_label')} (>= {sc.get('min_trades')} "
             f"trades) · {w.get('start')} -> {w.get('end')} · {s.get('looks')} looks ({lb.get('cells')} cells x "
             f"{lb.get('select_months')} selection months x {lb.get('choice_penalty')} for choosing a ratio)", ""]
    span = "–".join(sm.get("span") or []) or "none"
    lines += [f"Shared months ({span}, {sm.get('n', 0)} months every scheme tests OOS):",
              _table(STAT_HEAD + ["net $/month", "legs", "% legs +", "errors"],
                     [_stat_row(c.get("ratio"), (c.get("shared") or {}).get("stats"))
                      + [_usd(((c.get("shared") or {}).get("per_month") or {}).get("net_profit")),
                         ((c.get("shared") or {}).get("legs") or {}).get("n", "—"),
                         _num(((c.get("shared") or {}).get("legs") or {}).get("pct_profitable"), "{:.1f}%"),
                         ((c.get("shared") or {}).get("stats") or {}).get("skipped_by_error", "—")] for c in cols]), ""]
    rows = []
    for c in cols:
        ps = (c.get("phase_spread") or {}).get("net_profit") or {}
        rows.append(_stat_row(c.get("ratio"), c.get("stats"))
                    + ["–".join(c.get("span") or []) or "—", _usd((c.get("per_month") or {}).get("net_profit")),
                       f"{_usd(ps.get('min'))}..{_usd(ps.get('max'))} (mean {_usd(ps.get('mean'))})",
                       (c.get("legs") or {}).get("n", "—"), _num((c.get("legs") or {}).get("pct_profitable"), "{:.1f}%"),
                       (c.get("stats") or {}).get("skipped_by_error", "—")])
    lines += ["Full spans (each stitched chain as run; spans differ):",
              _table(STAT_HEAD + ["OOS span", "net $/month", "net across start months", "legs", "% legs +", "errors"], rows),
              ""]
    warn = (s.get("phase_check") or {}).get("warning")
    if warn:
        lines.append(f"Phase check: {warn}.")
    lines += [s.get("note") or "", "",
              f"Next: walkforward(walkforward_id={wid!r}, test_months=1|2|3) for one scheme's full result"]
    return "\n".join(lines)


class Toolbox(DeskMixin):
    def __init__(self, client: Client | None = None, *, sleep=time.sleep, clock=time.monotonic,
                 poll_s: float = 1.0, desk=None, charts_export=None):
        self._client = client
        self.sleep, self.clock, self.poll_s = sleep, clock, poll_s
        self._bundles: OrderedDict = OrderedDict()
        self._desk = desk               # a DeskClient, or None to build one lazily (desk_tools.DeskMixin)
        self._charts_export = charts_export

    @property
    def c(self) -> Client:
        if self._client is None:
            self._client = Client()
        return self._client

    def specs(self) -> list[dict]:
        return SPECS

    def names(self) -> list[str]:
        return [s["name"] for s in SPECS]

    def call(self, name: str, args: dict) -> str:
        if name not in self.names():
            raise ToolError(f"unknown tool {name!r}")
        fn = getattr(self, f"t_{name}")
        try:
            inspect.signature(fn).bind(**args)
        except TypeError as e:
            raise ToolError(f"{name}: {e}") from None
        return fn(**args)

    # ---- helpers

    def _wait(self, path: str, wait_s) -> tuple[dict, bool]:
        wait_s = DEFAULT_WAIT_S if wait_s is None else max(0, min(int(wait_s), MAX_WAIT_S))
        t_end = self.clock() + wait_s
        while True:
            st = self.c.get(path)
            if st.get("status") in FINAL:
                return st, True
            if self.clock() >= t_end:
                return st, False
            self.sleep(self.poll_s)

    def _bundle(self, ref: dict) -> dict:
        key = tuple(sorted(ref.items()))
        if key in self._bundles:
            self._bundles.move_to_end(key)
            return self._bundles[key]
        if "run_id" in ref:
            b = self.c.get(f"/api/tester/run/{_q(ref['run_id'])}/bundle")
        else:
            b = self.c.get(f"/api/tester/grid/{_q(ref['grid_id'])}/cell/{ref['cell']}/bundle")
        self._bundles[key] = b
        while len(self._bundles) > 4:
            self._bundles.popitem(last=False)
        return b

    def _catalog(self) -> list[dict]:
        got = self.c.get("/api/tester/strategies")
        return got if isinstance(got, list) else []

    # ---- tools

    def t_list_strategies(self) -> str:
        out = []
        for s in self._catalog():
            head = f"- {s.get('id')}: {s.get('name')} · root {s.get('root', '?')}" + (" · DRAFT" if s.get("draft") else "")
            if s.get("error"):
                out.append(f"{head} · DOES NOT LOAD: {s['error']}")
                continue
            ins = []
            for i in s.get("inputs") or []:
                rng = ""
                if i.get("type") == "choice":
                    rng = f" one of {i.get('choices')}"
                elif i.get("min") is not None or i.get("max") is not None:
                    rng = f" [{_num(i.get('min'), '{:g}')}..{_num(i.get('max'), '{:g}')}]"
                ins.append(f"{i.get('key')} ({i.get('type')}) = {i.get('default')}{rng}")
            out.append(f"{head}\n    inputs: {'; '.join(ins) or 'none'}")
        return "\n".join(out) or "No strategies."

    def t_read_strategy(self, strategy: str) -> str:
        entry = next((s for s in self._catalog() if s.get("id") == strategy), None)
        if entry is None:
            raise ToolError(f"no strategy {strategy!r} (list_strategies shows the ids)")
        src = self.c.get(f"/api/tester/strategies/{_q(strategy)}/source")
        parts = [f"Strategy {strategy}" + (" (DRAFT)" if entry.get("draft") else ""),
                 f"Catalog entry: {entry}", ""]
        for f in src.get("files") or []:
            parts += [f"===== {f.get('path')} =====", f.get("text", ""), ""]
        parts += ["===== DRAFT TEMPLATE (write_strategy follows this) =====", draftstore.DRAFT_TEMPLATE]
        return "\n".join(parts)

    def t_backtest(self, strategy: str | None = None, inputs=None, range=None, costs=None,  # noqa: A002
                   prop_rules=None, wait_s=None, run_id=None) -> str:
        if run_id is None:
            if not strategy:
                raise ToolError("strategy: required (or run_id to wait on an existing run)")
            body = {"strategy": strategy, "inputs": inputs or {}, "range": range_body(range), **_costs(costs)}
            if prop_rules:
                body["prop_rules"] = prop_rules
            run_id = self.c.post("/api/tester/run", body)["id"]
        st, final = self._wait(f"/api/tester/run/{_q(run_id)}", wait_s)
        if not final:
            return (f"Run {run_id} is still going ({_progress(st)}). Call backtest(run_id={run_id!r}) "
                    "or get_run to keep waiting.")
        if st.get("status") != "done":
            raise ToolError(f"Run {run_id} {st.get('status')}: {st.get('error') or ''}".strip())
        return bundle_summary(self._bundle({"run_id": run_id}), {"run_id": run_id})

    def _grid_body(self, strategy, axes, inputs, range, costs, prop_rules, max_cells) -> dict:  # noqa: A002
        if not strategy or not axes:
            raise ToolError("strategy and axes: required")
        body = {"strategy": strategy, "inputs": inputs or {}, "axes": axes, "range": range_body(range), **_costs(costs)}
        if prop_rules:
            body["prop_rules"] = prop_rules
        if max_cells is not None:
            body["max_cells"] = max_cells
        return body

    def t_heatmap(self, strategy=None, axes=None, inputs=None, range=None, costs=None,  # noqa: A002
                  prop_rules=None, max_cells=None, wait_s=None, grid_id=None) -> str:
        if grid_id is None:
            body = self._grid_body(strategy, axes, inputs, range, costs, prop_rules, max_cells)
            grid_id = self.c.post("/api/tester/grid", body)["id"]
        g, final = self._wait(f"/api/tester/grid/{_q(grid_id)}", wait_s)
        axes_l = g.get("axes") or []
        head = (f"Heat-map {grid_id} · {g.get('strategy')} · {(g.get('range') or {}).get('label', '')} · "
                f"{g.get('done', 0)}/{g.get('total', 0)} cells · {_progress(g)}")
        rows = []
        for c in g.get("cells") or []:
            sm = c.get("summary") or {}
            rows.append([c.get("i"), _kv(c.get("params")), c.get("status"), sm.get("trades", "—"),
                         _usd(sm.get("net_profit")), _num(sm.get("sharpe")), _pct(sm.get("win_rate")),
                         _num(sm.get("profit_factor")), _usd(sm.get("max_drawdown")), _num(sm.get("t_stat"))])
        done = [c for c in g.get("cells") or [] if c.get("status") == "done" and (c.get("summary") or {}).get("net_profit") is not None]
        best = max(done, key=lambda c: c["summary"]["net_profit"], default=None)
        looks = g.get("looks")
        lines = [head, f"Axes: {', '.join(a.get('key', '?') for a in axes_l)}", "",
                 _table(["cell", "params", "status", "trades", "net $", "Sharpe", "win %", "PF", "max DD $", "t"], rows), ""]
        if best is not None:
            lines.append(f"Best net: cell {best['i']} ({_kv(best.get('params'))}) {_usd(best['summary']['net_profit'])}")
        if looks is not None:
            lines.append(f"Looks this strategy: {looks} -- expect ~{round(looks / 20)} lucky cells at 5%")
        elif g.get("looks_error"):
            lines.append(f"Looks counter unreadable: {g['looks_error']}")
        if not final:
            lines.append(f"Still running: call heatmap(grid_id={grid_id!r}) to keep waiting.")
        else:
            lines.append(f"Next: get_run / trades / show_on_chart(grid_id={grid_id!r}, cell=N)")
        return "\n".join(lines)

    def t_walkforward(self, strategy=None, axes=None, ratio=3, metric=None, min_trades=None, inputs=None,
                      range=None, costs=None, prop_rules=None, max_cells=None, wait_s=None,  # noqa: A002
                      walkforward_id=None, test_months=None) -> str:
        if test_months is not None and (type(test_months) is not int or test_months not in (1, 2, 3)):
            raise ToolError("test_months: 1, 2 or 3")
        wid = walkforward_id
        if wid is None:
            body = self._grid_body(strategy, axes, inputs, range, costs, prop_rules, max_cells)
            body["test_months"] = ratio
            if metric:
                body["metric"] = metric
            if min_trades is not None:
                body["min_trades"] = min_trades
            wid = self.c.post("/api/tester/walkforward", body)["id"]
        st, final = self._wait(f"/api/tester/walkforward/{_q(wid)}", wait_s)
        if not final:
            return (f"Walk-forward {wid} is still going ({_progress(st)}). "
                    f"Call walkforward(walkforward_id={wid!r}) to keep waiting.")
        if st.get("status") != "done":
            raise ToolError(f"Walk-forward {wid} {st.get('status')}: {st.get('error') or ''}".strip())
        if (st.get("walkforward") or {}).get("compare") and test_months is None:
            return _compare_text(wid, self.c.get(f"/api/tester/walkforward/{_q(wid)}/compare"))
        q = "" if test_months is None else f"?test_months={test_months}"
        r = self.c.get(f"/api/tester/walkforward/{_q(wid)}/result{q}")
        sch, so, si = r.get("scheme") or {}, r.get("stitched") or {}, r.get("stitched_is") or {}
        drop = r.get("drop") or {}
        pm_o, pm_i = so.get("per_month") or {}, si.get("per_month") or {}
        lines = [f"Walk-forward {wid} · {sch.get('ratio')} · select by {sch.get('metric_label')} (>= {sch.get('min_trades')} "
                 f"trades) · {r.get('n_cells')} cells x {r.get('n_steps')} steps = {r.get('looks')} looks · "
                 f"{(r.get('window') or {}).get('start')} -> {(r.get('window') or {}).get('end')}", "",
                 _table(STAT_HEAD + ["months", "net $/month"],
                        [_stat_row("stitched OOS", so.get("stats")) + [so.get("n_months"), _usd(pm_o.get("net_profit"))],
                         _stat_row("its selection months (IS)", si.get("stats")) + [si.get("n_months"), _usd(pm_i.get("net_profit"))]]),
                 "",
                 f"Drop IS->OOS: {_usd(drop.get('net_profit_per_month'))}/month ({_num(drop.get('pct'), '{:+.1f}%')}), "
                 f"Sharpe {_num(drop.get('sharpe'), '{:+.2f}')}",
                 f"Pick stability: {r.get('stability')}", ""]
        rows = []
        for row in r.get("steps") or []:
            oos = row.get("oos") or {}
            ins = row.get("is") or {}
            rows.append([row.get("k"), row.get("select"), "–".join(row.get("test") or []),
                         _kv(row.get("params")) if row.get("params") else "no pick",
                         _usd(ins.get("net_profit")), _usd(oos.get("net_profit")), oos.get("trades", "—"),
                         "yes" if row.get("stitched") else ""])
        lines += [_table(["step", "select", "test", "pick", "IS net", "OOS net", "OOS trades", "stitched"], rows)]
        if so.get("uncovered"):
            lines.append(f"Months never tested OOS: {', '.join(so['uncovered'])}")
        return "\n".join(lines)

    def t_montecarlo(self, run_id=None, grid_id=None, cell=None, paths=None, mode=None, floor=None, seed=None) -> str:
        ref = _ref({"run_id": run_id, "grid_id": grid_id, "cell": cell})
        body = dict(ref)
        for k, v in (("paths", paths), ("mode", mode), ("floor", floor), ("seed", seed)):
            if v is not None:
                body[k] = v
        m = self.c.post("/api/tester/montecarlo", body)

        def pc(d, f=_usd):
            return ", ".join(f"{k} {f(v)}" for k, v in (d or {}).items())
        act = m.get("actual") or {}
        lines = [f"Monte Carlo ({_ref_text(ref)}): {m.get('paths')} paths{' (capped)' if m.get('capped') else ''}, "
                 f"{m.get('mode')} by {m.get('unit')}, {m.get('n_trades')} trades on {m.get('n_days')} days, seed {m.get('seed')}",
                 f"Max drawdown: {pc(m.get('drawdown'))}",
                 f"Final net: {pc(m.get('final_net'))}",
                 f"Losing streak (days): {pc(m.get('losing_streak'), lambda v: _num(v, '{:g}'))}",
                 f"P(drawdown >= {_usd(m.get('floor'))}): {_pct(m.get('p_ruin'), True)}",
                 f"Actual max DD {_usd(act.get('max_dd'))}: worse than {_num(act.get('worse_than_pct'), '{:.1f}')}% of paths"]
        if m.get("p_prop_pass") is not None:
            lines.append(f"P(prop pass, {(m.get('prop_rules') or {}).get('label', '?')}): {_pct(m['p_prop_pass'], True)}")
        return "\n".join(lines)

    def t_prop_eval(self, prop_rules: str, run_id=None, grid_id=None, cell=None) -> str:
        ref = _ref({"run_id": run_id, "grid_id": grid_id, "cell": cell})
        p = self.c.post("/api/tester/propsim", {**ref, "prop_rules": prop_rules})
        extra = f"\nCaveat: {p['caveat']}" if p.get("caveat") else ""
        return f"{_ref_text(ref)}\n{_prop_line(p)}{extra}"

    def t_list_prop_rules(self) -> str:
        rules = self.c.get("/api/tester/prop-rules") or []
        return "\n".join(f"- {r.get('id')}: {r.get('name')} (v{r.get('version')})"
                         + ("" if r.get("confirmed", True) else " · UNCONFIRMED rules") for r in rules) or "none"

    def t_list_runs(self, kind: str = "runs", limit: int = 15) -> str:
        path = {"runs": "/api/tester/runs", "heatmaps": "/api/tester/grids",
                "walkforwards": "/api/tester/walkforwards"}.get(kind)
        if path is None:
            raise ToolError("kind: runs, heatmaps or walkforwards")
        items = (self.c.get(path) or [])[:max(1, min(int(limit), 50))]
        if kind == "runs":
            rows = [[r.get("id"), r.get("strategy"), r.get("status"), (r.get("range") or {}).get("label", ""),
                     r.get("trades", "—"), _usd(r.get("net_profit"))] for r in items]
            return _table(["run_id", "strategy", "status", "range", "trades", "net $"], rows) if rows else "No runs."
        rows = [[g.get("id"), g.get("strategy"), g.get("status"), f"{g.get('done', '?')}/{g.get('total', '?')}",
                 ", ".join(g.get("axes") or [])] for g in items]
        return _table(["id", "strategy", "status", "cells", "axes"], rows) if rows else f"No {kind}."

    def t_get_run(self, run_id=None, grid_id=None, cell=None) -> str:
        ref = _ref({"run_id": run_id, "grid_id": grid_id, "cell": cell})
        if "run_id" in ref:
            st = self.c.get(f"/api/tester/run/{_q(ref['run_id'])}")
            if st.get("status") != "done":
                return f"Run {ref['run_id']}: {_progress(st)}" + (f" -- {st['error']}" if st.get("error") else "")
        return bundle_summary(self._bundle(ref), ref)

    def t_trades(self, run_id=None, grid_id=None, cell=None, offset=0, limit=50, sort="entry") -> str:
        ref = _ref({"run_id": run_id, "grid_id": grid_id, "cell": cell})
        if sort not in TRADE_SORTS:
            raise ToolError(f"sort: one of {', '.join(TRADE_SORTS)}")
        b = self._bundle(ref)
        trades = list(enumerate(b.get("trades") or []))
        keyf = {"entry": lambda it: (it[1].get("entry_ms") or 0, it[0]),
                "net": lambda it: (it[1].get("net") or 0, it[0]),
                "-net": lambda it: (-(it[1].get("net") or 0), it[0]),
                "mae": lambda it: (it[1].get("mae_usd") or 0, it[0]),
                "mfe": lambda it: (-(it[1].get("mfe_usd") or 0), it[0]),
                "duration": lambda it: (-(it[1].get("seconds") or 0), it[0])}[sort]
        trades.sort(key=keyf)
        offset, limit = max(0, int(offset)), max(1, min(int(limit), MAX_TRADE_ROWS))
        page = trades[offset:offset + limit]
        rows = [[i, t.get("date"), t.get("side"), _et(t.get("entry_ms"))[11:], _num(t.get("entry_price"), "{:.10g}"),
                 _et(t.get("exit_ms"))[11:], _num(t.get("exit_price"), "{:.10g}"), t.get("exit_reason"), t.get("qty"),
                 _usd(t.get("net")), _usd(t.get("mae_usd")), _usd(t.get("mfe_usd")), _num(t.get("seconds"), "{:.0f}s")]
                for i, t in page]
        head = f"Trades of {_ref_text(ref)}: {offset + 1 if page else 0}-{offset + len(page)} of {len(trades)} (sort {sort}; times ET)"
        more = f"\nMore: trades({_ref_text(ref)}, offset={offset + limit})" if offset + limit < len(trades) else ""
        return head + "\n" + _table(["#", "date", "side", "entry", "entry px", "exit", "exit px", "reason", "qty",
                                     "net", "MAE", "MFE", "dur"], rows) + more

    def t_show_on_chart(self, run_id=None, grid_id=None, cell=None, focus=None) -> str:
        ref = _ref({"run_id": run_id, "grid_id": grid_id, "cell": cell})
        body = dict(ref)
        if focus:
            body["focus"] = focus
        r = self.c.post("/api/tester/show", body)
        n = r.get("pages", 0)
        if not n:
            return (f"No chart page is open, so nothing was shown. Ask the user to open the Homebase charts "
                    f"({self.c.url}/), then call show_on_chart again.")
        return (f"Sent to {n} open chart page(s): the Strategy Tester loads {_ref_text(ref)}"
                + (f" and scrolls to {focus}" if focus else "")
                + ". If no chart could take the run's instrument safely, the page's status bar says why.")

    def t_cancel(self, run_id=None, grid_id=None, walkforward_id=None) -> str:
        given = [(k, v) for k, v in (("run", run_id), ("grid", grid_id), ("walkforward", walkforward_id))
                 if v is not None]
        if len(given) != 1:
            raise ToolError("give exactly one of run_id, grid_id, walkforward_id")
        kind, jid = given[0]
        st = self.c.post(f"/api/tester/{kind}/{_q(jid)}/cancel", {})
        return f"{kind} {jid}: {st.get('status', '?')}" + (f" -- {st['error']}" if st.get("error") else "")

    def t_write_strategy(self, name: str, code: str) -> str:
        built = [s.get("id") for s in self._catalog() if not s.get("draft")]
        try:
            path = draftstore.write(name, code, builtin_ids=built)
        except ValueError as e:
            raise ToolError(str(e)) from None
        sid = draftstore.draft_id(name)
        entry = next((s for s in self._catalog() if s.get("id") == sid), None)
        if entry is None:
            return f"Wrote {path}, but the tester does not list {sid} yet (is the chart service running this version?)"
        if entry.get("error"):
            raise ToolError(f"Wrote {path}, but the tester cannot read it: {entry['error']}\n"
                            "Fix it and call write_strategy again.")
        ins = "; ".join(f"{i.get('key')}={i.get('default')}" for i in entry.get("inputs") or []) or "none"
        return (f"Wrote {path}. Listed as {sid} ({entry.get('name')}, root {entry.get('root')}, "
                f"session_independent={entry.get('session_independent')}). Inputs: {ins}.\n"
                f"Next: backtest(strategy={sid!r}, ...)")

    def t_delete_draft(self, name: str) -> str:
        try:
            gone = draftstore.delete(name)
        except ValueError as e:
            raise ToolError(str(e)) from None
        return f"Deleted draft {name!r}." if gone else f"No draft {name!r} to delete."
