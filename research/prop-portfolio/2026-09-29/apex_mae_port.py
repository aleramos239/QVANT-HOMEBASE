#!/usr/bin/python3
"""Apex PA 30% negative-P&L (MAE) proxy for the saved Stage-B Apex portfolios: share of each member's trades whose worst open loss at the
member's micros reaches the $750 floor (30% x max(start-of-day profit, $2,500)); the compliance gate wants <= 2%. -> out/portfolio_apex_mae.json
Run: PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es /usr/bin/python3 apex_mae_port.py [--tag _final]"""
import json
import sys

import numpy as np

import evalcore as E

OUT = E.D / "out"
tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "_final"
res = {}
for f in ("apex", "apex_eod"):
    p = OUT / f"portfolio_{f}{tag}.json"
    if not p.exists():
        continue
    j = json.loads(p.read_text())
    for lab, r in j["reports"].items():
        if "extras" not in r:
            continue
        rows = []
        for sp in r["extras"]["specs"]:
            t = E.load(sp["trade_source"])
            m = E._sess_mask(t, sp["sess"])
            sc = t.mae[m] * sp["micros"] / 10.0
            rows.append({"member": f"{sp['strategy_id']}|{sp['sess']}@{sp['micros']}", "trades": int(m.sum()), "mae750_share": float((sc >= 750).mean()), "median_mae_usd": float(np.median(sc))})
        res[f"{f}:{lab}"] = rows
(OUT / f"portfolio_apex_mae{tag}.json").write_text(json.dumps(res, indent=1))
for k, v in res.items():
    print(k, [(x["member"], round(x["mae750_share"], 2)) for x in v])
