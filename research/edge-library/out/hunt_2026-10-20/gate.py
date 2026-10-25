"""Hunt 2026-10-20: grade every hunt_* taught result against PREREG.md (Gate 1 build days; Gate 2 walk-forward when on file).

Run: .venv-research/bin/python research/edge-library/out/hunt_2026-10-20/gate.py [names...]   (default: every hunt_* store)
Reads ~/.homebase/taught/<name>/result.json (and wf/result.json). Writes nothing but stdout and gate.json beside this file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path.home() / ".homebase" / "taught"
SESSIONS = 948          # build days 2021-09-22 .. 2025-06-30
CUSHION = 0.03


def g1_need(avg: dict) -> tuple[float | None, float | None]:
    """Breakeven win rate of the realized reward-to-risk of the average, and the need (+3 points)."""
    w, lo = avg.get("avg_win"), avg.get("avg_loss")
    if not w or not lo or lo >= 0:
        return None, None
    be = 1.0 / (1.0 + w / abs(lo))
    return be, be + CUSHION


def grade(name: str) -> list[dict]:
    base = ROOT / name
    rf = base / "result.json"
    if not rf.exists():
        return [{"name": name, "status": "no result"}]
    r = json.loads(rf.read_text())
    if r.get("smoke"):
        return [{"name": name, "status": "smoke only"}]
    out = []
    wf = json.loads((base / "wf" / "result.json").read_text()) if (base / "wf" / "result.json").exists() else None
    for tf, b in r["bars"].items():
        avg = b.get("average") or {}
        be, need = g1_need(avg)
        win = avg.get("win")
        rr = (avg["avg_win"] / abs(avg["avg_loss"])) if avg.get("avg_win") and avg.get("avg_loss") else None
        p42 = next((ln for ln in b["centre"].get("lines", []) if ln.get("line") == "P4.2"), {})
        # a one-side rule must also beat random entries on ITS side (P4.2s, the drift control): audit 2026-10-20
        p42s = next((ln for ln in b["centre"].get("lines", []) if ln.get("line") == "P4.2s"), None)
        one_side = r.get("plan", {}).get("dir") in ("long", "short")
        tpd = (avg.get("trades") or 0) / SESSIONS
        yrs = b.get("years_average") or []
        g1 = bool(need is not None and win is not None and win >= need)
        g2 = bool((avg.get("avg_trade") or 0) > 0 and p42.get("passed") and (not one_side or (p42s or {}).get("passed")))
        g3 = bool(tpd >= 0.5)
        row = {"name": name, "tf": tf, "status": "ok", "trades": avg.get("trades"), "per_day": round(tpd, 2),
               "avg_trade": round(avg.get("avg_trade") or 0, 1), "win": win, "rr": rr, "breakeven": be, "need": need,
               "pf": avg.get("pf"), "p42": p42.get("number"), "years_up": f"{sum(1 for y in yrs if (y.get('net') or 0) > 0)}/{len(yrs)}",
               "G1": g1, "G2": g2, "G3": g3, "gate1": g1 and g2 and g3}
        if wf:
            sp = wf.get("split") or {}
            blind = (sp.get("test_days") or {}).get("net")
            row.update(wf_passed=bool(wf.get("passed")), wf_net=(wf.get("metrics") or {}).get("net"),
                       wf_trades=(wf.get("metrics") or {}).get("trades"), wf_win=(wf.get("metrics") or {}).get("win"),
                       blind_net=blind, blind_trades=(sp.get("test_days") or {}).get("trades"),
                       gate2=bool(wf.get("passed")) and blind is not None and blind > 0)
        out.append(row)
    return out


def main(argv: list[str]) -> None:
    names = argv or sorted(p.name for p in ROOT.iterdir() if p.name.startswith("hunt_"))
    rows = [x for n in names for x in grade(n)]
    def pc(v):
        return "  -  " if v is None else f"{v * 100:4.1f}%"
    print(f"{'name':44} tf  per_day  avg$   win    need   rr    p42   yrs  G1 G2 G3 | WF net  blind  pass")
    for x in rows:
        if x["status"] != "ok":
            print(f"{x['name']:44} {x['status']}")
            continue
        wf = ""
        if "wf_passed" in x:
            wf = f"| {x['wf_net'] or 0:>7,.0f} {x['blind_net'] or 0:>6,.0f}  {'PASS' if x['gate2'] else 'fail'}"
        print(f"{x['name']:44} {x['tf']:>2}  {x['per_day']:>5}  {x['avg_trade']:>6} {pc(x['win'])} {pc(x['need'])} "
              f"{(x['rr'] or 0):4.2f} {(x['p42'] or 0):5.3f} {x['years_up']:>4}  {'Y' if x['G1'] else '.'}  {'Y' if x['G2'] else '.'}  "
              f"{'Y' if x['G3'] else '.'} {wf}")
    (Path(__file__).parent / "gate.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
