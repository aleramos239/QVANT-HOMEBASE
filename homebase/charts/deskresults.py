"""What the Desk's panel shows of a promoted Lab strategy's research: its saved run on the unseen days, and the prop sim's
headline of a run. READ-ONLY and small: run folders as the tester left them (request.json, status.json, run.json).
Nothing here runs a strategy, and no test day is read: a strategy with no saved run on the unseen days has none to show."""
import calendar
import datetime as dt
from pathlib import Path

from .. import strategies
from ..backtest import discipline, drafthost
from ..backtest.runner import read_json
from ..labrun.store import HEADLINE

PROP_KEYS = ("eval_pass_p", "bust_p", "median_days_to_pass", "funded_payout_p", "funded_expected_cheque")


def _value(v):
    """One setting, as a value to compare: 7, 7.0 and "7" are one (a record's settings may be saved as text)."""
    if isinstance(v, bool):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def same_settings(a, b) -> bool:
    a, b = a or {}, b or {}
    return a.keys() == b.keys() and all(_value(a[k]) == _value(b[k]) for k in a)


def resolved_params(rec: dict) -> dict:
    """The record's settings as a run resolves them: a setting the record leaves out is the code's default (the record's
    own text, read as text -- never run). The record's bare settings when its text cannot be read (or it has none: a
    built-in's record carries its settings already resolved)."""
    params = rec.get("params") or {}
    if not rec.get("source"):
        return params
    try:
        cls = drafthost.stub_class(str(rec.get("name")), rec.get("source") or "")
        return strategies.resolve_inputs(cls.inputs(), params)
    except Exception:  # noqa: BLE001 -- unreadable text or an unknown key: compare what the record says
        return params


def unseen_only(rng) -> bool:
    """The run read the unseen days and nothing before them (a run over all the data is not a read of the unseen days)."""
    rng = rng if isinstance(rng, dict) else {}
    return rng.get("holdout") is True and str(rng.get("start") or "") >= discipline.HOLDOUT_START.isoformat()


PENDING = ("queued", "running", None)      # a run's status.json while it is waiting or going (None: not written yet)


# Read off the unseen run's summary besides the headline: the realized reward:risk (avg win / avg loss) and its label, the Sharpe.
EXTRA = ("rr", "rr_label", "sharpe")


def unseen_state(runs: Path, rec: dict) -> dict:
    """Where the unseen-days run of THIS copy stands -- the same code, settings and size, read off the saved requests:
    {"state": "done", "run": {id, range, net, trades, win_rate, profit_factor, max_drawdown, rr, rr_label, sharpe}} for the newest finished one,
    {"state": "pending"} while one waits or goes, {"state": "failed"} for one that ended in error or was cancelled (it is
    never started again by itself), {"state": "none"} when there is none."""
    want = resolved_params(rec)
    seen = set()
    for d in sorted(runs.glob(f"*-{rec.get('id')}-*"), key=lambda p: p.name, reverse=True):
        req, st = (read_json(d / f, None) for f in ("request.json", "status.json"))
        if not isinstance(req, dict) or req.get("strategy") != rec.get("id") or req.get("draft_sha256") != rec.get("sha256"):
            continue
        if not unseen_only(req.get("range")) or req.get("qty") != rec.get("qty") or not same_settings(req.get("inputs"), want):
            continue
        status = st.get("status") if isinstance(st, dict) else None
        if status == "done":
            run = run_summary(runs, d.name)
            if run:
                return {"state": "done", "run": run}
        seen.add("pending" if status in PENDING else "failed")
    return {"state": "pending" if "pending" in seen else "failed" if seen else "none"}


def run_summary(runs: Path, run_id: str) -> dict | None:
    """A finished run's headline as the panel shows it: {id, range, net, trades, win_rate, profit_factor, max_drawdown, rr,
    rr_label, sharpe}; None for a run whose run.json cannot be read."""
    run = read_json(runs / run_id / "run.json", None)
    summary = (((run or {}).get("report") or {}).get("summary") or {}).get("all") if isinstance(run, dict) else None
    if not isinstance(summary, dict):
        return None
    return {"id": run_id, "range": run.get("range"),
            **{ours: summary.get(theirs) for ours, theirs in HEADLINE},
            **{k: summary.get(k) for k in EXTRA}}


def build_run_id(runs: Path, rec: dict) -> str | None:
    """The newest finished run of this record over the build days and nothing else (same code, settings and size), or None.
    A promoted strategy carries its build run in its record; a built-in has no record, so its run is found here."""
    want = resolved_params(rec)
    for d in sorted(runs.glob(f"*-{rec.get('id')}-*"), key=lambda p: p.name, reverse=True):
        req, st = (read_json(d / f, None) for f in ("request.json", "status.json"))
        if not isinstance(req, dict) or req.get("strategy") != rec.get("id") or req.get("draft_sha256") != rec.get("sha256"):
            continue
        rng = req.get("range") if isinstance(req.get("range"), dict) else {}
        if (rng.get("kind"), rng.get("start"), rng.get("end")) != ("research", discipline.RESEARCH_START.isoformat(),
                                                                    discipline.RESEARCH_END.isoformat()):
            continue
        if req.get("qty") != rec.get("qty") or not same_settings(req.get("inputs"), want):
            continue
        if isinstance(st, dict) and st.get("status") == "done":
            return d.name
    return None


# The Desk's own straddles are not Lab copies, but the tester holds an exact twin of each (it reads the Desk's config at call time):
# Desk strategy id -> the tester strategy that mirrors it. gc_nfp is the NFP-and-CPI spec of 2026-10-08, so its twin is gc_nfpcpi.
BUILTIN_TWINS = {"nq930": "nq930", "gc_nfp": "gc_nfpcpi"}


def builtin_rec(desk_id: str) -> dict | None:
    """A built-in Desk straddle as a record the functions above can match runs against: its tester twin, the Desk's size, and
    the settings the Desk runs now (so a run read before the Desk's setting changed stops matching, as a promoted copy's would).
    None for a strategy with no twin."""
    twin = BUILTIN_TWINS.get(desk_id)
    if twin is None:
        return None
    from ..strategies.straddle import desk_cfg
    c = desk_cfg(desk_id)
    want = {"offset_pts": c.offset_pts, "sl_pts": c.sl_pts, "tp_pts": c.tp_pts}
    if twin == "nq930":
        want["adx_gate"] = bool(c.gated)
    else:
        want["events"] = "NFP+CPI"
    return {"name": twin, "id": twin, "sha256": None, "qty": c.qty, "source": "",
            "params": strategies.resolve_inputs(strategies.get(twin).inputs(), want)}


def unseen_run(runs: Path, rec: dict) -> dict | None:
    """The newest finished unseen-days run of this copy (see unseen_state), or None."""
    return unseen_state(runs, rec).get("run")


def unseen_request(rec: dict, today) -> dict:
    """The tester request that reads the unseen days (2025-07-01 .. today) for this copy: as it was promoted -- its own
    settings, size and costs."""
    return {"strategy": rec["id"], "inputs": dict(rec.get("params") or {}),
            "range": {"kind": "custom", "start": discipline.HOLDOUT_START.isoformat(), "end": today.isoformat()},
            "qty": rec.get("qty") or 1, "commission": rec.get("commission"), "slippage_ticks": rec.get("slippage_ticks")}


def curve_of(runs: Path, run_id: str) -> dict | None:
    """The run's running total by day, after costs, from its saved trades: {days: [YYYY-MM-DD], vals: [cumulative net]}.
    One point per day with a trade, in date order (a day without one holds the line flat, as the Desk's own curve does).
    None for a run with fewer than two trading days or trades that cannot be read."""
    t = read_json(runs / run_id / "trades.json", None)
    return curve_of_trades(t.get("trades") if isinstance(t, dict) else t)


def curve_of_trades(t) -> dict | None:
    """curve_of over a trade list itself (a walk-forward's stitched trades)."""
    if not isinstance(t, list):
        return None
    by_day: dict[str, float] = {}
    for x in t:
        day, net = (x.get("date"), x.get("net")) if isinstance(x, dict) else (None, None)
        if isinstance(day, str) and isinstance(net, (int, float)) and not isinstance(net, bool):
            by_day[day] = by_day.get(day, 0.0) + net
    days = sorted(by_day)
    if len(days) < 2:
        return None
    total, vals = 0.0, []
    for day in days:
        total += by_day[day]
        vals.append(round(total, 2))
    return {"days": days, "vals": vals}


def prop_headline(prop) -> dict | None:
    """A prop sim's headline and the account it was scored on; None for one that failed or was never scored."""
    head = prop.get("headline") if isinstance(prop, dict) else None
    if not isinstance(head, dict):
        return None
    return {"account": (prop.get("rules") or {}).get("label"), **{k: head.get(k) for k in PROP_KEYS}}


# ---------------------------------------------------------------- the 3:1 walk-forward on the Desk card (owner, 2026-10-18)
# The card shows the strategy AS SET (its own settings, no search -- "i just want it to show the metrics for the one i have set"), run
# through the 3:1 walk-forward in BLOCKS over all the data: Build = its in-sample months (3 of every 4), Unseen = its out-of-sample
# months (the 4th). Started by itself once per code, settings, size and last whole month.
WF_START = discipline.RESEARCH_START


def wf_end(today) -> str:
    """The last day of the last whole month: the job stays the same all month and runs again when a month completes."""
    return (today.replace(day=1) - dt.timedelta(days=1)).isoformat()


def wf_request(rec: dict, today) -> dict:
    """The tester walk-forward 3:1 (blocks) of this copy as set: all the data to the last whole month, its settings, size and costs."""
    return {"strategy": rec["id"], "inputs": dict(rec.get("params") or {}), "axes": [],
            "range": {"kind": "custom", "start": WF_START.isoformat(), "end": wf_end(today)},
            "qty": rec.get("qty") or 1, "commission": rec.get("commission"), "slippage_ticks": rec.get("slippage_ticks"),
            "select_months": 3, "test_months": 1, "step_months": 4}


def wf_state(grids: Path, rec: dict, today) -> dict:
    """Where this copy's 3:1 walk-forward stands (same code, settings, size and window, nothing searched), newest first:
    {"state": "done", "id"}, {"state": "pending"}, {"state": "failed"} (never started again by itself), {"state": "none"}."""
    want, base = wf_request(rec, today), resolved_params(rec)
    seen = set()
    for d in sorted(grids.glob(f"*-{rec.get('id')}-*"), key=lambda p: p.name, reverse=True):
        g, c0 = read_json(d / "grid.json", None), read_json(d / "cells" / "00" / "request.json", None)
        if not isinstance(g, dict) or not isinstance(c0, dict) or g.get("strategy") != rec.get("id"):
            continue
        cfg, rng = g.get("walkforward") or {}, g.get("range") or {}
        if c0.get("draft_sha256") != rec.get("sha256") or cfg.get("select_months") != 3 or g.get("qty") != want["qty"] \
                or cfg.get("step_months") != 4 or g.get("axes"):         # blocks, the strategy as set: never a search
            continue
        if (rng.get("start"), rng.get("end")) != (want["range"]["start"], want["range"]["end"]) \
                or not same_settings(g.get("base"), base):
            continue
        if g.get("status") == "done":
            return {"state": "done", "id": d.name}
        seen.add("failed" if g.get("status") in ("error", "cancelled") else "pending")
    return {"state": "pending" if "pending" in seen else "failed" if seen else "none"}


def wf_summary(wid: str, result: dict, side: str = "stitched") -> dict:
    """One side of the walk-forward in the card's shape (run_summary's keys): "stitched" = the out-of-sample months (Unseen),
    "stitched_is" = the in-sample months (Build)."""
    so = result.get(side) or {}
    st, ms = so.get("stats") or {}, so.get("months") or []
    last = f"{ms[-1]}-{calendar.monthrange(*map(int, ms[-1].split('-')))[1]:02d}" if ms else None
    return {"id": wid, "range": {"start": f"{ms[0]}-01", "end": last} if ms else None,
            "walkforward": (result.get("scheme") or {}).get("ratio"),
            **{ours: st.get(theirs) for ours, theirs in HEADLINE},
            "rr": st.get("rr"), "rr_label": st.get("rr_label"), "sharpe": st.get("sharpe")}
