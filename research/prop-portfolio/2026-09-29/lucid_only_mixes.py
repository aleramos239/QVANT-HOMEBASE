#!/usr/bin/python3
"""Lucid-only multi-account mixes N=2..6 (pre-freeze, IN-SAMPLE only; reads out/portfolio_<firm>_final.{json,npz} and the Flex-ext
(`PP_FLEX_TAKE_EXT=1`) files portfolio_lucid_flexext{,fast}.{json,npz} if they exist). Used for the ES holdout manifest because the reported
mixes (portfolio_results.json) contain non-compliant Apex accounts (ES verification, 2026-10-01).

Rule (written before any 2025+ run): for each N the account composition over {lucid, lucidpro, lucidpro_nodll} (every count vector summing to N)
is filled greedily by portfolio.best_mix; the composition with the highest in-sample primary P(>=1 pass <= 5d) wins (tie: lower eval cost).
Output: out/portfolio_multi_lucidonly.json  {"mixes": {"2": best_mix result, ...}}  (labels 'firm:label', fx_* = Flex-ext specs).
Run: PP_PILOT=es PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 lucid_only_mixes.py
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import portfolio as P         # noqa: E402

OUT = E.D / "out"
FIRMS = ("lucid", "lucidpro", "lucidpro_nodll")
FX = (("portfolio_lucid_flexext", {"single": "fx_single", "best2": "fx_best2"}),
      ("portfolio_lucid_flexextfast", {"best2": "fxfast_best2"}))


def load_specs() -> dict:
    specs = {}
    for f in FIRMS:
        j = json.loads((OUT / f"portfolio_{f}_final.json").read_text())
        z = np.load(OUT / f"portfolio_{f}_final.npz")
        labs = ["portfolio", "best2", "single"] + [k for k in j["reports"] if k.startswith("single:")]
        specs[f] = [{"label": "pf" if lab == "portfolio" else lab, "arr": {m: (z[f"{lab}|{m}|o"], z[f"{lab}|{m}|d"]) for m in P.MODELS},
                     "fee": j["fee"]["eval_fee"], "activation": j["fee"]["activation"]}
                    for lab in labs if lab in j["reports"] and f"{lab}|eod|o" in z.files]
    for stem, mp in FX:
        if (OUT / f"{stem}.json").exists():
            j = json.loads((OUT / f"{stem}.json").read_text())
            z = np.load(OUT / f"{stem}.npz")
            for lab, nm in mp.items():
                specs["lucid"].append({"label": nm, "arr": {m: (z[f"{lab}|{m}|o"], z[f"{lab}|{m}|d"]) for m in P.MODELS},
                                       "fee": j["fee"]["eval_fee"], "activation": j["fee"]["activation"]})
    return specs


def compositions(n: int):
    for a in range(n + 1):
        for b in range(n + 1 - a):
            yield {"lucid": a, "lucidpro": b, "lucidpro_nodll": n - a - b}


def main():
    specs = load_specs()
    out = {"note": "Lucid-only mixes, in-sample greedy (see module docstring)", "mixes": {}, "n_specs": {f: len(v) for f, v in specs.items()}}
    for n in range(2, 7):
        best = None
        for c in compositions(n):
            c = {f: k for f, k in c.items() if k}
            r = P.best_mix(specs, c)
            key = (round(r["primary"]["p_any5"], 6), -r["primary"]["total_eval_cost"])
            if best is None or key > best[0]:
                best = (key, r)
        out["mixes"][str(n)] = best[1]
        p = best[1]["primary"]
        print(f"N={n} {best[1]['counts']}: P(>=1 pass<=5d) {p['p_any5']:.3f} eod {best[1]['eod']['p_any5']:.3f} intra {best[1]['intraday']['p_any5']:.3f} "
              f"cost {p['total_eval_cost']:.0f} {best[1]['accounts']}")
    (OUT / "portfolio_multi_lucidonly.json").write_text(json.dumps(out, indent=1, default=P._js))


if __name__ == "__main__":
    main()
