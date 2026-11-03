"""Teams, read only: the Desk keeps each team as one record (engine_groups.py, <state>/groups.json); the charts service reads
that file directly, like its other .state reads, for the team list and the combined results off the members' 3:1
walk-forwards. (On the Practice Desk the results read the Mac's own .state.)"""
import json
import re
from pathlib import Path

from .. import paths
from ..backtest import walkforward
from ..core.num import float_or_none as _num

STRATEGY_RE = re.compile(r"[a-z][a-z0-9_]{0,59}")      # a Desk strategy id: nq930, lab_nq_vault_break_micro


class GroupError(ValueError):
    """A refusal in words the page may show."""


def load(root: Path | None = None) -> list[dict]:
    """[{id, name, members}] of the Desk's teams, in its order; [] for no file or one that cannot be read."""
    try:
        raw = json.loads(((root or paths.state_dir()) / "groups.json").read_text())
    except (OSError, ValueError):
        return []
    return [{"id": gid, "name": str(g.get("name") or gid),
             "members": [m for m in g.get("members") or [] if isinstance(m, str) and STRATEGY_RE.fullmatch(m)]}
            for gid, g in (raw.items() if isinstance(raw, dict) else ()) if isinstance(g, dict)]


# ---- combined results -------------------------------------------------------------------------------------------------

def merged(named: list[tuple[str, list[dict]]]) -> tuple[list[dict], list[str]]:
    """Several members' trades as one ledger, in the order they closed, and each trade's owner in that same order. (The sim
    reads the ledger as one account's trades; trades open at once are counted together by its own open-loss rule.)"""
    rows = [(owner, t) for owner, ledger in named for t in ledger
            if isinstance(t, dict) and _num(t.get("net")) is not None and isinstance(t.get("date"), str)]
    rows.sort(key=lambda r: (r[1].get("exit_ms") or 0, r[1].get("entry_ms") or 0))
    return [t for _, t in rows], [o for o, _ in rows]


def summarize(trades: list[dict], owners: list[str] | None = None) -> dict | None:
    """What a ledger made, after costs: {net, trades, win_rate, profit_factor, max_drawdown, days, worst_day, best_day,
    together_days (days two or more members traded; needs `owners`, one name per trade, in the ledger's order),
    rr, rr_label, sharpe (the walk-forward's own stats: Sharpe on the traded days only; None for a ledger it cannot read),
    curve: {days, vals}}. None for an empty ledger. max_drawdown is a loss (negative), on closed trades."""
    if not trades:
        return None
    net = [float(t["net"]) for t in trades]
    wins, losses = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    by_day: dict[str, float] = {}
    who: dict[str, set] = {}
    for i, t in enumerate(trades):
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + float(t["net"])
        if owners is not None and i < len(owners):
            who.setdefault(t["date"], set()).add(owners[i])
    peak = cum = worst = 0.0
    for x in net:
        cum += x
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    try:
        st = walkforward._stats(trades, [], 1.0)
    except (KeyError, TypeError, ValueError):      # a trade row the report cannot read: no RR / Sharpe, the rest stays
        st = {}
    days, run, vals = sorted(by_day), 0.0, []
    for d in days:
        run += by_day[d]
        vals.append(round(run, 2))
    return {"net": round(sum(net), 2), "trades": len(net), "win_rate": round(100.0 * sum(x > 0 for x in net) / len(net), 2),
            "profit_factor": round(wins / losses, 3) if losses > 0 else None, "max_drawdown": round(worst, 2),
            "days": len(days), "worst_day": round(min(by_day.values()), 2), "best_day": round(max(by_day.values()), 2),
            "together_days": sum(1 for d in days if len(who.get(d, ())) >= 2) if owners is not None else None,
            "rr": st.get("rr"), "rr_label": st.get("rr_label"), "sharpe": st.get("sharpe"),
            "curve": {"days": days, "vals": vals}}
