"""STACK B draft (STACKB_DRAFT.md; NOT pre-registered, nothing ported): the stores Amendment K's S1-S7 passed but stack A did not take,
kept only when their in-sample daily net is LESS tied to stack A than A's typical member is to the rest of A. In-sample months only
(runs_wf/<store>/is, the pinned 14 blocks); no test month, grade or LUCK file is read.

    stackb_draft.py    -> prints the numbers of STACKB_DRAFT.md (writes nothing)
B1-B7 = K's S1-S7 (stack.json "rest" = every S1-S7 store outside stack A; S7 already leaves one store per idea x family, so none
shares an idea x family with A) . B8 corr(store's daily net, stack A's daily net) <= CAP, CAP = the median over A's 8 members of
corr(member, the other 7) . B9 lowest corr first; <= 12 rules; stop at 10 a day."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("HOMEBASE_WF_LAST", "2026-05")
import hmread as HR  # noqa: E402

HERE = Path(__file__).resolve().parent
LB = HR.LB
NY = [LB.SESS_CODE[s] for s in HR.GROUPS["NY"]]
J = [("vh_i10_adx_touch_5_ny-NQ-tf5", "g_lvl30_pts60-r2"), ("vh_i16_emavwap_rv_5_ny-NQ-tf5", "fast_n13_own1-r1p5"),
     ("vh_i17_rvbrk_5_ny-NQ-tf5", "m2_atr2-r2")]                      # the 3 Amendment-J rules already in shadow (SHADOW_BAR.md)


def trades(store: str, box: str) -> dict:
    u = LB.load_unit("is", HR.RUNS / store)
    x = LB.unit_cell(u, [c["id"] for c in u["meta"]["cells"]].index(box))
    k = np.isin(np.asarray(x["sess"]), NY)
    return {"date": np.asarray(x["date"])[k].astype(int), "net": np.asarray(x["net"], float)[k], "sess": np.asarray(x["sess"])[k],
            "days": [dt.date.fromisoformat(d).toordinal() for d in u["meta"]["days"]]}


def corr(a, b) -> float:
    return float(np.corrcoef(a, b)[0, 1])


def main() -> None:
    sj = json.loads((HERE / "stack.json").read_text())
    legs = {(c["store"], c["box"]): trades(c["store"], c["box"]) for c in sj["stack"] + sj["rest"]}
    legs.update({k: trades(*k) for k in J})
    days = legs[next(iter(legs))]["days"]
    assert all(t["days"] == days for t in legs.values()), "stores disagree on the in-sample days"
    di = {d: i for i, d in enumerate(days)}

    def daily(k):
        v = np.zeros(len(days))
        np.add.at(v, [di[d] for d in legs[k]["date"]], legs[k]["net"])
        return v

    A = [(c["store"], c["box"]) for c in sj["stack"]]
    ad = {k: daily(k) for k in A}
    a = sum(ad.values())
    own = {k: corr(ad[k], a - ad[k]) for k in A}
    cap = float(np.median(list(own.values())))
    print(f"in-sample days {len(days)}; stack A {sum(len(legs[k]['net']) for k in A) / len(days):.2f} a day")
    print("A member vs the other 7:", ", ".join(f"{k[0].split('-')[0][3:]} {v:.2f}" for k, v in own.items()), f"-> CAP (median) {cap:.3f}")

    pool = sorted(sj["rest"], key=lambda c: corr(daily((c["store"], c["box"])), a))
    stack, day = [], 0.0
    print("\n| Store | Box | Family | Bars | Trades/day | Avg $ | Win | Break-even | Blocks + | Block t | Months + | Share + | "
          "Corr with A | nyam / mid / pm | B8 |")
    for c in pool:
        k = (c["store"], c["box"])
        r = corr(daily(k), a)
        s = legs[k]["sess"]
        mix = " / ".join(f"{(s == LB.SESS_CODE[x]).mean() * 100:.0f}" for x in HR.GROUPS["NY"])
        take = r <= cap and len(stack) < 12 and day < 10
        if take:
            stack.append(k)
            day += c["per_day"]
        print(f"| {c['store']} | {c['box']} | {c['family']} | {c['tf']}m | {c['per_day']:.2f} | {c['avg']:,.0f} | {c['win'] * 100:.1f} % | "
              f"{(c['be'] or 0) * 100:.1f} % | {c['blocks_pos']}/14 | {c['block_t']:.2f} | {c['cal_pos']}/9 | {c['share'] * 100:.0f} % | "
              f"{r:.2f} | {mix} | {'IN' if take else 'out'} |")

    def port(name, keys):
        v = sum(daily(k) for k in keys)
        n = np.concatenate([legs[k]["net"] for k in keys])
        lo = a < 0
        h = len(days) // 2
        print(f"{name}: {len(keys)} rules, {len(n) / len(days):.2f} a day, avg ${n.mean():,.0f}, sd ${n.std(ddof=1):,.0f}, win {(n > 0).mean() * 100:.1f} %, "
              f"corr with A {corr(v, a):.2f} (first half {corr(v[:h], a[:h]):.2f}, second {corr(v[h:], a[h:]):.2f}), "
              f"on A's losing days ({lo.sum()}): B ${v[lo].mean():,.0f} a day vs A ${a[lo].mean():,.0f}")
        return v

    print()
    b = port("STACK B (B8 cap)", stack)
    port("If the cap is lifted to 0.65", [(c["store"], c["box"]) for c in pool if corr(daily((c["store"], c["box"])), a) <= 0.65])
    port("All 5 not taken (no cap)", [(c["store"], c["box"]) for c in pool])
    j = port("The 3 Amendment-J shadow rules", J)
    port("STACK B + the 3 J rules", stack + J)
    print(f"corr(B, J) {corr(b, j):.2f}")


if __name__ == "__main__":
    main()
