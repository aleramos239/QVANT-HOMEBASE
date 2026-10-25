"""Audit: grade EVERY taught store (Gate 1 from the cells; Gate 2 from wf/result.json) to check amendments A and B. Reads only."""
import json
from pathlib import Path
import numpy as np
ROOT = Path.home() / ".homebase" / "taught"
rows = []
for d in sorted(ROOT.iterdir()):
    f = d / "result.json"
    if not f.exists():
        continue
    try:
        r = json.loads(f.read_text())
    except Exception:
        continue
    if r.get("smoke") or not r.get("bars"):
        continue
    wf = json.loads((d / "wf" / "result.json").read_text()) if (d / "wf" / "result.json").exists() else None
    for tf, b in r["bars"].items():
        cells = b["cells"]
        M = lambda k: float(np.mean([c["metrics"][k] for c in cells if c["metrics"].get(k) is not None]))
        try:
            tr, net, win, aw, al = M("trades"), M("net"), M("win"), M("avg_win"), M("avg_loss")
        except Exception:
            continue
        need = 1 / (1 + aw / abs(al)) + 0.03 if al < 0 and aw > 0 else None
        cen = next(c for c in cells if c["centre"])
        p42 = next((l for l in cen["lines"] if l["line"] == "P4.2"), {})
        p42s = next((l for l in cen["lines"] if l["line"] == "P4.2s"), None)
        g1 = need is not None and win >= need
        g2 = net / tr > 0 and bool(p42.get("passed")) if tr else False
        g3 = tr / 948 >= 0.5
        row = dict(name=d.name, tf=tf, fam=r["plan"]["family"], dir=r["plan"].get("dir"), per_day=tr / 948, avg=net / tr if tr else 0, win=win, need=need,
                   g1=g1, g2=g2, g3=g3, gate1=g1 and g2 and g3, p42s=None if p42s is None else p42s.get("passed"), wf=wf is not None)
        if wf:
            bl = wf["split"]["test_days"]
            row.update(wf_pass=wf["passed"], wf_net=wf["metrics"]["net"], wf_tr=wf["metrics"]["trades"], blind=bl["net"], gate2=wf["passed"] and bl["net"] > 0)
        rows.append(row)
print("stores graded:", len(rows), " with wf:", sum(r["wf"] for r in rows))
print("\n== WITH a walk-forward on file ==")
for r in rows:
    if r["wf"]:
        print(f"{r['name']:46} {r['fam']:16} G1={'Y' if r['gate1'] else '.'} (g1 {int(r['g1'])} g2 {int(r['g2'])} g3 {int(r['g3'])}) win {r['win']*100:4.1f} need {(r['need'] or 0)*100:4.1f} "
              f"| wf {'PASS' if r['wf_pass'] else 'fail'} net {r['wf_net']:>8,.0f} tr {r['wf_tr']:3} blind {r['blind']:>7,.0f} GATE2={'Y' if r['gate2'] else '.'}")
print("\n== Gate 1 PASS, NO walk-forward on file ==")
for r in rows:
    if r["gate1"] and not r["wf"]:
        print(f"{r['name']:46} {r['fam']:16} {r['dir']:5} {r['per_day']:.2f}/day avg ${r['avg']:6.1f} win {r['win']*100:4.1f} need {r['need']*100:4.1f} p42s={r['p42s']}")
