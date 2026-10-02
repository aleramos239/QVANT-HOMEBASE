"""The Lab's "Request review": a draft strategy packaged for a human (and Claude) to read before it can
ever reach the desk. It WRITES TEXT ONLY -- one JSON and one Markdown file under
~/.homebase/review-requests (HOMEBASE_REVIEW_DIR overrides it) -- and never imports, runs or promotes
anything. Putting a strategy on the desk is a separate, deliberate act done in the desk's own code
(homebase/strategies + config.json); this file is what that review starts from.
Chart-service side only: the desk never reads this directory."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

ENV = "HOMEBASE_REVIEW_DIR"
MIN_TRADES = 30
# what a person (not a script) still has to look at -- the strategy-review checklist
MANUAL = (
    ("look_ahead", "Look-ahead: no decision uses a price from after its own time"),
    ("repaint", "Repaint: bar values are final when read; nothing is re-written after the fact"),
    ("sizing", "Sizing: qty, tick value and the prop account's contract limit"),
    ("rules", "Prop rules: daily loss, trailing drawdown, consistency, news and the 9:30 window"),
    ("fees", "Fees and slippage are realistic for the account it would run on"),
    ("desk_port", "Desk port: the same orders, brackets and cancel/flat times as the backtest"),
)


def review_dir() -> Path:
    v = os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "review-requests"


def _summary(bundle: dict | None) -> dict | None:
    if not bundle:
        return None
    run = bundle.get("run") or {}
    rep = run.get("report") or {}
    a = (rep.get("summary") or {}).get("all") or {}
    keep = ("net_profit", "trades", "win_rate", "profit_factor", "max_drawdown", "avg_trade", "sharpe", "t_stat")
    return {"run_id": run.get("id") or run.get("run_id"), "range": run.get("range"),
            "inputs": (run.get("strategy") or {}).get("inputs") or run.get("inputs"),
            "qty": run.get("qty"), "commission": run.get("commission"),
            "slippage_ticks": run.get("slippage_ticks"),
            "holdout": bool(run.get("holdout")),
            "coverage": {k: (run.get("coverage") or {}).get(k) for k in ("sessions", "used")},
            "strategy_errors": rep.get("skipped_by_error") or 0,
            "all": {k: a.get(k) for k in keep}}


def checks(meta: dict | None, summary: dict | None) -> list[dict]:
    """The checks a script can do for itself, as {id, label, ok}; ok None = no backtest to judge by."""
    out = [{"id": "valid", "label": "Parses and its catalog metadata reads", "ok": meta is not None},
           {"id": "independent", "label": "Declares session_independent = True",
            "ok": bool(meta and meta.get("session_independent"))}]
    if summary is None:
        out.append({"id": "ran", "label": "Backtest attached", "ok": False})
        return out
    n = (summary["all"] or {}).get("trades") or 0
    out += [{"id": "ran", "label": "Backtest attached", "ok": True},
            {"id": "trades", "label": f"At least {MIN_TRADES} trades (it has {n})", "ok": n >= MIN_TRADES},
            {"id": "holdout", "label": "Stays inside the research window (no 2025+ data)",
             "ok": not summary["holdout"]},
            {"id": "errors", "label": "No session crashed the strategy", "ok": not summary["strategy_errors"]},
            {"id": "costs", "label": "Fees and slippage are on",
             "ok": bool((summary.get("commission") or 0) > 0 and (summary.get("slippage_ticks") or 0) >= 1)}]
    return out


def create(name: str, code: str, meta: dict | None, bundle: dict | None = None, note: str = "",
           now: dt.datetime | None = None, base: Path | None = None) -> dict:
    """Write <ts>-<name>.json + .md and return {id, json, md}. Text only."""
    now = now or dt.datetime.now(dt.timezone.utc)
    base = Path(base) if base is not None else review_dir()
    base.mkdir(parents=True, exist_ok=True)
    rid = f"{now.strftime('%Y%m%d-%H%M%S')}-{name}"
    summary = _summary(bundle)
    pack = {"id": rid, "created": now.isoformat(timespec="seconds"), "strategy": f"draft_{name}",
            "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(), "note": (note or "").strip()[:2000],
            "meta": meta, "backtest": summary, "checks": checks(meta, summary),
            "manual_checks": [{"id": i, "label": t} for i, t in MANUAL], "code": code,
            "status": "requested"}
    jp, mp = base / f"{rid}.json", base / f"{rid}.md"
    jp.write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")
    mp.write_text(_markdown(pack), encoding="utf-8")
    return {"id": rid, "json": str(jp), "md": str(mp), "checks": pack["checks"]}


def _markdown(p: dict) -> str:
    L = [f"# Review request: {p['strategy']}", "", f"Requested {p['created']} · sha256 `{p['sha256'][:12]}`", ""]
    if p["note"]:
        L += ["> " + re.sub(r"\s*\n\s*", "\n> ", p["note"]), ""]
    b = p["backtest"]
    L.append("## Backtest")
    if b:
        a = b["all"]
        L += [f"- run `{b['run_id']}` · range {b['range']} · qty {b['qty']} · commission {b['commission']} · "
              f"slippage {b['slippage_ticks']} ticks",
              f"- net {a.get('net_profit')} · trades {a.get('trades')} · win rate {a.get('win_rate')} · "
              f"profit factor {a.get('profit_factor')} · max drawdown {a.get('max_drawdown')} · "
              f"sharpe {a.get('sharpe')}"]
    else:
        L.append("- none attached")
    L += ["", "## Automatic checks"] + [f"- [{'x' if c['ok'] else ' '}] {c['label']}" for c in p["checks"]]
    L += ["", "## For the reviewer"] + [f"- [ ] {c['label']}" for c in p["manual_checks"]]
    L += ["", "## Code", "", "```python", p["code"].rstrip("\n"), "```", ""]
    return "\n".join(L)
