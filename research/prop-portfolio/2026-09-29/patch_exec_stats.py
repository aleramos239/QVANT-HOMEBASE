#!/usr/bin/python3
"""Add the executed-share diagnostics (portfolio.exec_stats) + flags to the saved Stage-B firm results (single / best2 / portfolio of the main and
fast runs). Search results untouched; originals kept in out/pre_verify/. Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 patch_exec_stats.py"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio as P
import portfolio_final as PF

OUT = P.OUT
(OUT / "pre_verify").mkdir(exist_ok=True)
for f in P.FIRM_ALL:
    fm = P.firm(f)
    ctx, pools = PF.make_ctx((f,))
    by = {b.name: b for b in pools[f]}
    for tag in ("_final", "_finalfast"):
        jp = OUT / f"portfolio_{f}{tag}.json"
        bak = OUT / "pre_verify" / jp.name
        if not bak.exists():
            shutil.copy(jp, bak)
        res = json.loads(jp.read_text())
        for lab in ("single", "best2", "portfolio"):
            rep = res["reports"].get(lab)
            if not rep or "cell" not in rep:
                continue
            members = [(by[m["name"]], int(m["micros"])) for m in rep["members"]]
            rep["exec"] = P.exec_stats(ctx, fm, members, fm.cell_index(rep["cell"]))
            rep["flags"] = [x for x in rep.get("flags", []) if not x.startswith(("DEAD_MEMBERS", "EXEC_NET_SHARE", "NEGATIVE_EXEC_MEMBER"))] + P.exec_flags(rep["exec"], len(members))
        jp.write_text(json.dumps(res, indent=1, default=P._js))
        pf = res["reports"]["portfolio"]
        e = pf["exec"]
        print(f"{f:15s}{tag:11s} portfolio exec trades {[m['executed'] for m in e['members']]} net {[round(m['net']) for m in e['members']]} maxshare {e['max_net_share'] and round(e['max_net_share'], 2)} dead {len(e['dead'])}", flush=True)
