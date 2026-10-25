"""Audit: re-grade Gate 1 from the CELLS (not the stored average), independent of gate.py. Reads only; writes nothing."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path.home() / ".homebase" / "taught"
names = sys.argv[1:] or sorted(p.name for p in ROOT.iterdir() if p.name.startswith("hunt_"))
print(f"{'name':40} tf cells sess  tr/day  avg$    win    rr_avg  be     need   P4.2c  G1 G2 G3 | stored-avg-diff")
for n in names:
    r = json.loads((ROOT / n / "result.json").read_text())
    for tf, b in r["bars"].items():
        cells = b["cells"]
        M = lambda k: float(np.mean([c["metrics"][k] for c in cells if c["metrics"].get(k) is not None]))
        tr, net, win, aw, al = M("trades"), M("net"), M("win"), M("avg_win"), M("avg_loss")
        avg = net / tr
        rr = aw / abs(al)
        be = 1 / (1 + rr)
        need = be + 0.03
        cen = [c for c in cells if c["centre"]]
        assert len(cen) == 1 and cen[0]["id"] == b["centre"]["id"]
        p42 = [l for l in cen[0]["lines"] if l["line"] == "P4.2"]
        p42ok = bool(p42 and p42[0]["passed"])
        sess = b["range"]["sessions"]
        g1, g2, g3 = win >= need, avg > 0 and p42ok, tr / 948 >= 0.5
        a = b["average"]
        diff = max(abs(a["trades"] - tr), abs(a["net"] - net), abs(a["win"] - win) * 1e4)
        print(f"{n:40} {tf:>2} {len(cells):>3} {sess:>5} {tr/948:6.2f} {avg:7.1f} {win*100:5.1f}% {rr:5.2f} {be*100:5.1f}% {need*100:5.1f}% "
              f"{(p42[0]['number'] if p42 else float('nan')):6.4f} {'Y' if g1 else '.'}  {'Y' if g2 else '.'}  {'Y' if g3 else '.'} | {diff:.3g}"
              f"  centre={cen[0]['id']} wl_avg={a['win_loss']:.3f}")
