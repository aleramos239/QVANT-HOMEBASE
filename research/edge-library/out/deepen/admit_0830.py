"""ORCHESTRATOR RULING 2026-10-04, step 2-3: the 08:30 NQ straddle on news days. The BUILD central variant is the ONLY variant
judged (no moved default): library.admission (unchanged) on its news-day trades; surviving set under 2 ticks + 250 ms saved.
The random-minute control was run on BUILD only (the ruling asked for the 2024 menu and nothing more): beats_c1_pick is NOT RUN.
Writes out/deepen/admission_0830.json and members/<name>/ or members/_rejected/<name>/ (+ surviving_set.csv)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import admit_sides as A  # noqa: E402
import judge_pick_sides as P  # noqa: E402
import judge_sides as J  # noqa: E402
import labels as L  # noqa: E402
import library as LB  # noqa: E402

UID, SIDE, FAM, ROOT, TF, SESS = "straddle_t_0830-NQ-tf30|pre|", "news_only", "straddle_t_0830", "NQ", "30", "pre"
NAME = f"{FAM}_{ROOT}_tf{TF}_{SESS}_{SIDE}"
SAME = ("SAME IDEA as the member orb_NQ_tf1_pre (a straddle of the 08:30 ET data burst): the two never count as two members of a stack.")


def main():
    j = json.loads((HERE / "pick_0830.json").read_text())
    T, TS = P.tables(UID, SIDE, False), P.tables(UID, SIDE, False, stress=True)
    tb, tp = {t["id"]: t for t in T["build"]}, {t["id"]: t for t in T["pick"]}
    sb, sp = {t["id"]: t for t in TS["build"]}, {t["id"]: t for t in TS["pick"]}
    surv = [i for i in j["both_positive"] if sb[i]["net"] > 0 and sp[i]["net"] > 0]
    med, cm = j["build"]["median_net"], j["central"]
    order = sorted(surv, key=lambda i: (round(abs(tb[i]["net"] - med), 6), tb[i]["vi"], tb[i]["xi"]))
    ub = J.load(f"{FAM}-{ROOT}-tf{TF}")
    cell = next(c for c in ub["meta"]["cells"] if c["id"] == cm)
    runs = {}
    for per in ("build", "pick"):
        for stress in (False, True):
            kk = f"{NAME}-{cm}-{per}{'-stress' if stress else ''}"
            p = HERE / "member_runs" / f"{kk}.json"
            if not p.exists():
                res = LB.run_member(FAM, ROOT, TF, cell["variant"], cell["exit"], per, stress=stress, build_plateau=j["build"], key=kk)
                p.parent.mkdir(exist_ok=True)
                p.write_text(json.dumps({"trades": res["trades"], "inputs": res["meta"]["inputs"]}))
            runs[(per, stress)] = json.loads(p.read_text())
    for per, u in (("build", T["ub"]), ("pick", T["up"])):                       # identity with the stores, before the split
        x = LB.unit_cell(u, cm)
        got = runs[(per, False)]["trades"]
        assert len(got) == len(x["net"]) and abs(sum(t["net"] for t in got) - float(x["net"].sum())) < 0.01, per
    member = {"name": NAME, "root": ROOT, "tf": TF, "sess": SESS, "cell": cm, "inputs": runs[("build", False)]["inputs"],
              **LB.member_meta(FAM, SESS, cell["variant"]), "plateau": {"build": j["build"], "pick": j["pick"]},
              "nulls_bar": {**J.BARS[f"shift-{ROOT}"], "stat": "t"}}
    for per in ("build", "pick"):
        tr = A.keep(runs[(per, False)]["trades"], SIDE, ROOT)
        member[per] = {"trades": tr, "stress": A.keep(runs[(per, True)]["trades"], SIDE, ROOT), "calendar": LB.calendar(per, ROOT)}
    su = J.load(f"{FAM}-{ROOT}-tf{TF}-shift")                                    # BUILD control: the same straddle at a random minute
    nets, n = [], 0
    for sd in (1, 2):
        x = LB.unit_cell(su, f"s{sd}_{cm}")
        m = L.side_mask(SIDE, ROOT, x["date"], x["side"])
        nets.append(float(x["net"][m].sum()))
        n += int(m.sum())
    net_b = sum(t["net"] for t in member["build"]["trades"])
    member["build"]["c1"] = {"lift": round(net_b - float(np.mean(nets)), 2), "mean": round(float(np.mean(nets)), 2), "p95": round(max(nets), 2),
                             "p_beat": float(np.mean([net_b > v for v in nets])), "fallback_share": 0.0, "short": 0, "pool_trades": n}
    member["notes"] = "; ".join(x for x in (member.get("notes"),
        f"STAGE 2a FILTERED SIDE `{SIDE}`: trades {L.PLAIN[SIDE]} (72 such days on BUILD, 32 in 2024). Why it should matter: the straddle is a "
        "bet on a burst at 08:30 ET; a CPI or jobs report is the scheduled burst (a Fed day has no 08:30 release and is in the split only because the "
        "pre-registered tool says so). " + SAME + " This is the BUILD central variant; by the orchestrator's ruling no other variant may replace it. "
        "beats_c1_pick: the random-minute control was NOT RUN on 2024 (the ruling asked for the menu only); it is listed as failed only because "
        "library.admission fails closed. The control on BUILD is the same straddle fired at a random minute (2 seeds), news days only.") if x)
    res = LB.admission(member, write=False)
    print(NAME, cm, "ADMIT" if res["admit"] else "REJECT", res["failed"])
    for a, v in res["tests"].items():
        print("   ", a, {x: (round(y, 3) if isinstance(y, float) else y) for x, y in v.items()})
    d = LB.write_member(member, res)
    cal = LB.calendar("build", ROOT) + LB.calendar("pick", ROOT)
    rows = []
    for i in order:
        xb, xp = P.cell(T["ub"], i, SESS, SIDE, ROOT), P.cell(T["up"], i, SESS, SIDE, ROOT)
        x = {f: np.concatenate([xb[f], xp[f]]) for f in LB.FIELDS}
        z = LB.sized(x, ROOT)
        for a, b in zip(LB.per_year(x, cal), LB.per_year(z, cal, z["cost"])):
            rows.append({"cell": i, "build_central": i == cm, "period": a["period"], **{m: a[m] for m in LB.METRIC_KEYS}, "t": a["t"],
                         "t_build": tb[i]["t"], "net_1000risk": round(b["net"], 2), "sharpe_1000risk": b["sharpe"], "max_dd_1000risk": b["max_dd"],
                         "worst_open_loss_1000risk": b["worst_open_loss"], "stress_build": sb[i]["net"], "stress_pick": sp[i]["net"]})
    if rows:
        with (d / "surviving_set.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    xc = LB.pack(member["build"]["trades"] + member["pick"]["trades"])
    py = LB.per_year(xc, cal)
    t = res["tests"]
    extra = ["", f"## Stage 2a record — side `{SIDE}` ({L.PLAIN[SIDE]}), opened on 2024 by the orchestrator's ruling of 2026-10-04",
             f"* {SAME}",
             f"* BUILD (news days): {j['build']['share_pos'] * 100:.0f} % of {j['build']['cells']} variants positive, median {j['build']['median_net']:,.0f}; "
             f"central variant `{cm}`: {j['central_build']['trades']} trades, {j['central_build']['net']:,.0f}, t {j['central_build']['t']:.2f} (bar 2.62).",
             f"* 2024 (news days): {j['pick']['share_pos'] * 100:.1f} % of {j['pick']['cells']} variants positive, median {j['pick']['median_net']:,.0f} -> the table "
             f"{'PASSES' if j['pick']['pass'] else 'FAILS'} (at 60 % only). The BUILD central variant: {j['central_pick']['trades']} trades, {j['central_pick']['net']:,.0f}.",
             f"* Trades BUILD + 2024: {j['trades_build_plus_pick']} (100 needed).",
             f"* Per year (1 contract): " + " · ".join(f"{r['period']} {r['net']:,.0f} ({r['trades']} trades)" for r in py) + ".",
             f"* Stress (2 ticks + 250 ms), central variant: BUILD {t['stress_build']['base']:,.0f} -> {t['stress_build']['stressed']:,.0f}; "
             f"2024 {t['stress_pick']['base']:,.0f} -> {t['stress_pick']['stressed']:,.0f}.",
             f"* Surviving set: {len(surv)} of {j['build']['cells']} variants are positive in both periods and under stress (`surviving_set.csv`); the BUILD central "
             "variant is not one of them, and by the ruling no other variant may take its place.",
             f"* Verdict: {'ADMITTED' if res['admit'] else 'NOT ADMITTED: the BUILD central variant loses money in 2024 (and under stress there)'}.", ""]
    with (d / "card.md").open("a") as fh:
        fh.write("\n".join(extra))
    out = {"name": NAME, "admit": res["admit"], "failed": res["failed"], "tests": res["tests"], "central": cm, "surviving": len(surv),
           "judged": j["build"]["cells"], "both_positive": len(j["both_positive"]), "dir": str(d),
           "per_year": [{k: r[k] for k in ("period", "trades", "net")} for r in py],
           "control_pick": "not run (ruling: the 2024 menu only)"}
    (HERE / "admission_0830.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    print("surviving", len(surv), "of", j["build"]["cells"], "| per year", out["per_year"], "|", d)


if __name__ == "__main__":
    main()
