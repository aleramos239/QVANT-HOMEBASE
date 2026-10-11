"""What the Desk's panel shows of a promoted Lab strategy's research: its saved run on the unseen days, and the prop sim's
headline of a run. READ-ONLY and small: run folders as the tester left them (request.json, status.json, run.json).
Nothing here runs a strategy, and no test day is read: a strategy with no saved run on the unseen days has none to show."""
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


def unseen_state(runs: Path, rec: dict) -> dict:
    """Where the unseen-days run of THIS copy stands -- the same code, settings and size, read off the saved requests:
    {"state": "done", "run": {id, range, net, trades, win_rate, profit_factor, max_drawdown}} for the newest finished one,
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
            run = read_json(d / "run.json", None)
            summary = (((run or {}).get("report") or {}).get("summary") or {}).get("all") if isinstance(run, dict) else None
            if isinstance(summary, dict):
                return {"state": "done", "run": {"id": d.name, "range": run.get("range"),
                                                 **{ours: summary.get(theirs) for ours, theirs in HEADLINE}}}
        seen.add("pending" if status in PENDING else "failed")
    return {"state": "pending" if "pending" in seen else "failed" if seen else "none"}


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
    t = t.get("trades") if isinstance(t, dict) else t
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
