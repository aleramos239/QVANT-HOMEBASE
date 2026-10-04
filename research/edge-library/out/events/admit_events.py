"""STAGE 3, step 3: admission of every unit whose 2024 table passed and whose BUILD central variant is positive in 2024.
The BUILD central variant is the ONLY variant judged (no moved default). library.admission (unchanged) on its trades on the
group's days: net > 0 in both periods, heat map, the random-minute control on the same days in BOTH periods (run on 2024 too),
t above the bar, 2 ticks + 250 ms in both periods, >= 100 trades, the open loss fits $2,000.
Full trade records come from library.run_member (4 member runs per distinct cell; identity with the stores is asserted).
RULE FIXED BEFORE ANY ADMISSION RESULT: E1-A-GC and E1-B-GC are the SAME variant and B's days are a subset of A's -> at most ONE
member folder for that market / time: the wider filter A if it is admitted (B's table goes on its card), else B.
Writes out/events/admission.json, out/events/member_runs/, members/<name>/ or members/_rejected/<name>/."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev as E  # noqa: E402
import judge_build as JB  # noqa: E402
import judge_pick as JP  # noqa: E402
import library as LB  # noqa: E402

RUNS = HERE / "member_runs"
OLD = {"straddle_tight_0830|NQ|offB_pts5-r3": E.W / "out" / "admit_r1" / "member_runs" / "straddle_tight_0830_NQ_tf30_pre-offB_pts5-r3"}
REASON = ("STAGE 3 reason (written before any event-split number): a scheduled US data release reprices the market in one burst in "
          "the first seconds; a bracket placed just before catches it whichever way.")


def name_of(r: dict) -> str:
    return f"{r['family']}_{r['root']}_tf{JB.TF}_{r['sess']}_ev{r['group']}"


def keep(trades: list, group: str) -> list:
    gd = E.days(group)
    return [t for t in trades if t["date"] in gd]


def member_runs(fam, root, sess, cm, cellmeta, plateau) -> dict:
    RUNS.mkdir(exist_ok=True)
    runs = {}
    old = OLD.get(f"{fam}|{root}|{cm}")
    for per in ("build", "pick"):
        for stress in (False, True):
            sfx = f"{per}{'-stress' if stress else ''}"
            p = RUNS / f"{fam}_{root}_tf{JB.TF}_{sess}-{cm}-{sfx}.json"
            if not p.exists() and old is not None and Path(f"{old}-{sfx}.json").exists():
                p.write_text(Path(f"{old}-{sfx}.json").read_text())          # the stage-2b member run of the same cell
            if not p.exists():
                res = LB.run_member(fam, root, JB.TF, cellmeta["variant"], cellmeta["exit"], per, stress=stress, build_plateau=plateau,
                                    key=f"{fam}_{root}_tf{JB.TF}_{sess}_ev-{cm}-{sfx}")
                p.write_text(json.dumps({"trades": res["trades"], "inputs": res["meta"]["inputs"]}))
            runs[(per, stress)] = json.loads(p.read_text())
    return runs


def main():
    bu = {r["uid"]: r for r in json.loads((HERE / "build_units.json").read_text()) if r["pass"]}
    pj = json.loads((HERE / "pick_judgement.json").read_text())
    out = {}
    for uid, j in pj.items():
        r = bu[uid]
        fam, root, sess, g, cm = r["family"], r["root"], r["sess"], r["group"], r["central"]
        name = name_of(r)
        if not j["go_stress"]:
            out[uid] = {"name": name, "admit": False, "failed": ["plateau_pick" if not j["pick_table_pass"] else "net_pick"],
                        "note": "no admission test is run"}
            continue
        rd, _ = JP.STORES[fam]
        ub, up = JB.load(r["key"]), JB.load(JP.pick_key(fam, root, sess), rd)
        cellmeta = next(c for c in ub["meta"]["cells"] if c["id"] == cm)
        runs = member_runs(fam, root, sess, cm, cellmeta, j["build"])
        for per, u in (("build", ub), ("pick", up)):                              # identity with the stores, before the split
            x = LB.unit_cell(u, cm)
            m = x["sess"] == LB.SESS_CODE[sess]
            got = runs[(per, False)]["trades"]
            assert len(got) == int(m.sum()) and abs(sum(t["net"] for t in got) - float(x["net"][m].sum())) < 0.01, (uid, per)
        for per in ("build", "pick"):                                             # the stressed store cell = the stressed member run
            su = JB.load(f"{fam}-{root}-tf{JB.TF}-{sess}-{per}-stress", rd)
            x = LB.unit_cell(su, cm)
            got = runs[(per, True)]["trades"]
            assert len(got) == len(x["net"]) and abs(sum(t["net"] for t in got) - float(x["net"].sum())) < 0.01, (uid, per, "stress")
        member = {"name": name, "root": root, "tf": JB.TF, "sess": sess, "cell": cm, "inputs": runs[("build", False)]["inputs"],
                  **LB.member_meta(fam, sess, cellmeta["variant"]), "plateau": {"build": j["build"], "pick": j["pick"]},
                  "nulls_bar": {"bar": E.BAR[root], "nulls": 26 if root != "ES" else 18, "thin": False, "stat": "t"}}
        if r["second_look"]:
            member["second_look"] = "SECOND LOOK ON 2024: " + r["second_look"] + " (and 2025+ was never read)"
        for per in ("build", "pick"):
            tr = keep(runs[(per, False)]["trades"], g)
            member[per] = {"trades": tr, "stress": keep(runs[(per, True)]["trades"], g), "calendar": LB.calendar(per, root)}
            sc = JB.shift_control(fam, root, cm, g, per, None if per == "build" else rd,
                                  None if per == "build" else JP.pick_key(fam, root, sess, "-shift"))
            net = sum(t["net"] for t in tr)
            member[per]["c1"] = {"lift": round(net - sc["mean"], 2), "mean": round(sc["mean"], 2), "p95": round(max(sc["nets"]), 2),
                                 "p_beat": float(np.mean([net > v for v in sc["nets"]])), "fallback_share": 0.0, "short": 0,
                                 "pool_trades": sc["trades"]}
        member["notes"] = "; ".join(x for x in (member.get("notes"),
            f"STAGE 3 EVENT FILTER `{g}`: trades only on {E.PLAIN[g]} ({r['event_days_build']} such sessions on BUILD, {r['event_days_2024']} "
            f"in 2024; calendar = engine/cache/events.csv, official release dates, never checked against prices). {REASON} The control in "
            "both periods is the same bracket fired at a random minute (2 seeds) on the same days. This is the BUILD central variant "
            "(library.plateau on the filtered table); no other variant may replace it.") if x)
        res = LB.admission(member, write=False)
        print(uid, name, cm, "ADMIT" if res["admit"] else "REJECT", res["failed"])
        for a, v in res["tests"].items():
            print("   ", a, {x: (round(y, 3) if isinstance(y, float) else y) for x, y in v.items()})
        out[uid] = {"name": name, "admit": res["admit"], "failed": res["failed"], "tests": res["tests"], "central": cm, "member": None}
        out[uid]["_member"] = member
        out[uid]["_res"] = res
    # one folder per strategy: the nested GC pair
    a, b = out.get("E1-A-GC"), out.get("E1-B-GC")
    skip = set()
    if a and b and a.get("admit") and b.get("admit"):
        skip.add("E1-B-GC")
        b["folder_note"] = "same variant, days are a subset of E1-A-GC: recorded on that member's card, no folder of its own"
    for uid, o in out.items():
        member, res = o.pop("_member", None), o.pop("_res", None)
        if member is None:
            continue
        if uid not in skip:
            d = LB.write_member(member, res)
            o["dir"] = str(d)
        cal = LB.calendar("build", member["root"]) + LB.calendar("pick", member["root"])
        xc = LB.pack(member["build"]["trades"] + member["pick"]["trades"])
        z = LB.sized(xc, member["root"])
        o["per_year"] = [{k: r[k] for k in ("period", "trades", "net", "win", "pf", "max_dd", "sharpe", "worst_open_loss")} for r in LB.per_year(xc, cal)]
        o["per_year_r1000"] = [{k: r[k] for k in ("period", "trades", "net", "max_dd", "sharpe", "worst_open_loss")} for r in LB.per_year(z, cal, z["cost"])]
        o["micros_median"] = int(np.median(z["micros"][z["micros"] > 0]))
    (HERE / "admission.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    for uid, o in out.items():
        print(uid, o["name"], "ADMIT" if o["admit"] else "REJECT", o.get("failed"), o.get("dir", o.get("folder_note", "")))
        if o.get("per_year"):
            print("   per year", [(r["period"], r["trades"], r["net"]) for r in o["per_year"]])


if __name__ == "__main__":
    main()
