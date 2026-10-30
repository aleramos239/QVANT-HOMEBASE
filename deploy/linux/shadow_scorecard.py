"""Shadow scorecard: is each Desk Lab strategy doing on live prices what its backtest said it would? (owner, 2026-10-30)

Reads the Lab store (homebase/labrun/store.py layout) and prints one markdown row per strategy that is switched on:
live win rate and $/trade per contract next to the backtest's, how many days the daily match passed, and a verdict.
Read-only, stdlib only. Run on the server, where the shadow days are written:

    ssh root@144.202.51.163 /home/homebase/ramos-quant-homebase/.venv/bin/python - /home/homebase/.homebase/desklab \
        < deploy/linux/shadow_scorecard.py

Per contract (of the record's exec_root: MNQ or full NQ), because a Desk copy may be sized up (`any_size` trades); the
backtest numbers in the record are 1 contract.
Only days written under the record's current promotion count (an older day ran older code).
"""
import json
import math
import sys
from pathlib import Path

MIN_TRADES = 20          # below this the verdict is "too early": a few trades say nothing


def verdict(n: int, wins: int, bt_win_pct: float) -> str:
    if n < MIN_TRADES:
        return f"too early ({n}/{MIN_TRADES})"
    p = bt_win_pct / 100
    sd = math.sqrt(p * (1 - p) / n)
    return "BEHIND" if wins / n < p - 2 * sd else "in line"


def row(rec: dict, folder: Path) -> dict:
    run = rec.get("run") or {}
    days = []
    for f in sorted((folder / "days").glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            continue
        if d.get("promoted_utc") == rec.get("promoted_utc"):
            days.append(d)
    trades = [t for d in days for t in d.get("trades", []) if t.get("qty")]
    n = len(trades)
    wins = sum(t["net"] > 0 for t in trades)
    per_contract = sum(t["net"] / t["qty"] for t in trades)
    checked = [d["match"]["ok"] for d in days if (d.get("match") or {}).get("ok") is not None]
    bt_n = run.get("trades") or 0
    return {
        "name": rec["name"], "days": len(days), "n": n,
        "win": f"{100 * wins / n:.0f}%" if n else "-",
        "bt_win": f"{run['win_rate']:.0f}%" if run.get("win_rate") is not None else "-",
        "avg": f"{per_contract / n:+.1f}" if n else "-",
        "bt_avg": f"{run['net'] / bt_n:+.1f}" if bt_n else "-",
        "net": f"{per_contract:+.0f}",
        "match": f"{sum(checked)}/{len(checked)}",
        "verdict": verdict(n, wins, run["win_rate"]) if run.get("win_rate") is not None else "no backtest",
    }


def main(root: Path) -> None:
    rows = []
    for f in sorted(root.glob("*.json")):
        if f.name.endswith(".desk.json") or f.name == "runner.json":
            continue
        try:
            rec = json.loads(f.read_text())
        except ValueError:
            continue
        if rec.get("enabled") and rec.get("name"):
            rows.append(row(rec, root / rec["name"]))
    print("| strategy | days | trades | win live (backtest) | $/trade per contract live (backtest) | net per contract"
          " | days matched | verdict |")
    print("|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r["verdict"] != "BEHIND", -r["n"])):
        print(f"| {r['name']} | {r['days']} | {r['n']} | {r['win']} ({r['bt_win']}) | {r['avg']} ({r['bt_avg']})"
              f" | {r['net']} | {r['match']} | {r['verdict']} |")


if __name__ == "__main__":
    assert verdict(5, 0, 60) == "too early (5/20)"
    assert verdict(40, 24, 60) == "in line"
    assert verdict(40, 12, 60) == "BEHIND"            # 30% vs 60%: far past 2 sd (~7.7 pts)
    args = [a for a in sys.argv[1:] if a != "-"]
    main(Path(args[0]) if args else Path.home() / ".homebase" / "desklab")
