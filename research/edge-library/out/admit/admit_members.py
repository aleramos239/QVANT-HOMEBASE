"""ADMIT stage, step 3: the admission tests of every unit whose 2024 heat map passed (plan D / E), through library.admission.
Default variant cells are re-run with library.run_member (full trade rows: BUILD, PICK, both under 2 ticks + 250 ms).
Writes members/<name>/ (or members/_rejected/<name>/), surviving_set.csv, and out/admit/admission.json."""
import csv
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "admit"
RA = W / "runs_admit"


def sess_cell(u, cid, sess):
    x = LB.unit_cell(u, cid)
    m = x["sess"] == LB.SESS_CODE[sess]
    return {k: v[m] for k, v in x.items()}


def c1_for(trades, pool_unit, xid, seed):
    parts = [LB.unit_cell(pool_unit, f"s{sd}_{xid}") for sd in (1, 2)]
    pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net")}
    return LB.c1_draws(LB.pack(trades), pool, K=200, seed=seed)


def main():
    J = json.loads((OUT / "pick_judgement.json").read_text())
    SV = json.loads((OUT / "surviving.json").read_text())
    bars = json.loads((OUT / "null_bars.json").read_text())
    results = {}
    for uid, sv in SV.items():
        j = J[uid]
        key, sess, fam, root, tf = j["key"], j["sess"], j["family"], j["root"], j["tf"]
        name = f"{fam}_{root}_tf{tf}_{sess}"
        ub, up = LB.load_unit(key), LB.load_unit(f"{key}-{sess}-pick", RA)
        cid = sv["default"]
        cell = next(c for c in ub["meta"]["cells"] if c["id"] == cid)
        runs = {}
        for per in ("build", "pick"):
            for stress in (False, True):
                k = f"{name}-{cid}-{per}{'-stress' if stress else ''}"
                p = OUT / "member_runs" / f"{k}.json"
                if p.exists():
                    runs[(per, stress)] = json.loads(p.read_text())
                    continue
                res = LB.run_member(fam, root, tf, cell["variant"], cell["exit"], per, sess=sess, stress=stress, build_plateau=j["build"], key=k)
                p.parent.mkdir(exist_ok=True)
                p.write_text(json.dumps({"trades": res["trades"], "inputs": res["meta"]["inputs"]}))
                runs[(per, stress)] = {"trades": res["trades"], "inputs": res["meta"]["inputs"]}
        # identity with the stores (the member run is the menu's cell)
        for per, u in (("build", ub), ("pick", up)):
            ref = sess_cell(u, cid, sess)
            got = runs[(per, False)]["trades"]
            assert len(got) == len(ref["net"]) and abs(sum(t["net"] for t in got) - float(ref["net"].sum())) < 0.01, (name, per)
        xid = cid.rsplit("_", 1)[-1]
        pools = {"build": LB.load_unit(f"c1-{root}-tf{tf}"), "pick": LB.load_unit(f"c1-{root}-tf{tf}-{sess}-pick", RA)}
        member = {"name": name, "root": root, "tf": tf, "sess": sess, "cell": cid, "inputs": runs[("build", False)]["inputs"],
                  **LB.member_meta(fam, sess, cell["variant"]),
                  "plateau": {"build": j["build"], "pick": j["pick"]},
                  "nulls_bar": {**bars[f"c1-{root}"], "stat": "t"}}
        for per in ("build", "pick"):
            tr = runs[(per, False)]["trades"]
            member[per] = {"trades": tr, "stress": runs[(per, True)]["trades"], "calendar": LB.calendar(per, root),
                           "c1": c1_for(tr, pools[per], xid, LB.default_seed(name, per))}
        res = LB.admission(member, write=False)
        note = []
        if sv["default_moved"]:
            note.append(f"DEFAULT MOVED: the BUILD central cell `{j['central']}` is not in the surviving set; default = the surviving "
                        f"cell closest to the BUILD median (`{cid}`)")
        if member.get("penalty") and res["admit"]:
            res["admit"] = False
            res["failed"] = res["failed"] + ["penalty_reason_owed"]
            res["tests"]["penalty_reason_owed"] = {"pass": False, "note": "EDGE_SPEC C: a reason why the 2025-26 failure was noise is owed"}
        flag = None
        if sv["default_moved"] and res["failed"] == ["above_best_of_nulls_build"]:
            # plan E (pre-registered 2026-10-04 04:33 ET): the bar and WEAK tests are judged on the BUILD central cell (step B: passed);
            # a moved default needs: controls on PICK, >= 100 trades, open-loss fit, stress. library.admission also applies the bar to
            # the moved default: kept in the table as a FLAG, not as a failure.
            B = {r["uid"]: r for r in csv.DictReader((OUT / "build_units.csv").open())}[uid]
            res["tests"]["bar_on_build_central_cell"] = {"pass": True, "cell": j["central"], "t_build": float(B["m_t"]), "bar": float(B["bar"])}
            flag = (f"FLAGGED ADMISSION: the unit passed BUILD on its central cell `{j['central']}` (t {float(B['m_t']):.2f} > bar {float(B['bar']):.2f}), "
                    f"but that cell's 2024 net under 2 ticks + 250 ms is negative, so the default moved to `{cid}`, whose own BUILD t "
                    f"({res['tests']['above_best_of_nulls_build']['t_build']:.2f}) is BELOW the best-of-nulls bar. Admitted by the Admit stage's "
                    "pre-registered rule (progress.md 2026-10-04 04:33 ET, D / E); library.admission run on the moved default alone says REJECT. "
                    "Checker / orchestrator: confirm or demote to near-miss.")
            res["admit"], res["failed"], res["flag"] = True, [], flag
            note.append(flag)
        if note:
            member["notes"] = "; ".join(x for x in (member.get("notes"), *note) if x)
        stale = LB.MEMBERS / ("_rejected" if res["admit"] else "") / name
        if res["admit"] and stale.exists():
            import shutil
            shutil.rmtree(stale)
        d = LB.write_member(member, res)
        # the surviving set: every variant, per year then combined, 1 contract + $1,000 risk, + the stressed nets
        sb, sp = LB.load_unit(f"{key}-{sess}-build-stress", RA), LB.load_unit(f"{key}-{sess}-pick-stress", RA)
        cal = LB.calendar("build", root) + LB.calendar("pick", root)
        rows, lines = [], []
        for s in sv["surviving"]:
            xb, xp = sess_cell(ub, s["id"], sess), sess_cell(up, s["id"], sess)
            x = {k: np.concatenate([xb[k], xp[k]]) for k in LB.FIELDS}
            z = LB.sized(x, root)
            py, pz = LB.per_year(x, cal), LB.per_year(z, cal, z["cost"])
            for a, b in zip(py, pz):
                rows.append({"cell": s["id"], "default": s["id"] == cid, "period": a["period"],
                             **{k: a[k] for k in LB.METRIC_KEYS}, "t": a["t"],
                             "net_1000risk": round(b["net"], 2), "sharpe_1000risk": b["sharpe"], "max_dd_1000risk": b["max_dd"],
                             "worst_open_loss_1000risk": b["worst_open_loss"],
                             "stress_build": s["build_stress"], "stress_pick": s["pick_stress"]})
            yr = {a["period"]: a for a in py}
            zr = {b["period"]: b for b in pz}
            lines.append(f"| `{s['id']}`{' **(default)**' if s['id'] == cid else ''} | " + " | ".join(
                f"{yr[p]['net']:,.0f}" for p in ("2021*", "2022", "2023", "2024", "combined")) +
                f" | {yr['combined']['trades']} | {s['build_stress']:,.0f} / {s['pick_stress']:,.0f} | {zr['combined']['net']:,.0f} | "
                f"{(zr['combined']['sharpe'] or 0):.2f} |")
        with (d / "surviving_set.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        tr_all = member["build"]["trades"] + member["pick"]["trades"]
        tpd = len(tr_all) / len(cal)
        extra = ["", f"## Surviving set ({len(sv['surviving'])} of {sv['judged']} judged cells: net > 0 on BUILD and on PICK, and > 0 under 2 ticks + 250 ms in both)",
                 "Net per year at 1 contract, then combined; stressed net BUILD / PICK; the same trades at about $1,000 of risk (micros). "
                 "Full metric set per variant per year: `surviving_set.csv`. One variant per account (same trades).",
                 "| variant | 2021* | 2022 | 2023 | 2024 | combined | trades | stressed BUILD / PICK | $1,000-risk net | $1,000-risk Sharpe |",
                 "|---|---|---|---|---|---|---|---|---|---|"] + lines + [
                 "", f"Trades per day (default variant, BUILD + PICK): {tpd:.2f}. BUILD and PICK are both selection data: forward proof is still needed.", ""]
        with (d / "card.md").open("a") as fh:
            fh.write("\n".join(extra))
        results[uid] = {"name": name, "admit": res["admit"], "failed": res["failed"], "tests": res["tests"], "summary": res["summary"],
                        "dir": str(d), "default": cid, "default_moved": sv["default_moved"], "surviving": len(sv["surviving"]),
                        "judged": sv["judged"], "trades_per_day": round(tpd, 3), "flag": flag}
        print(name, "ADMIT" if res["admit"] else "REJECT", res["failed"])
        for k, v in res["tests"].items():
            print("   ", k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
    (OUT / "admission.json").write_text(json.dumps(results, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


if __name__ == "__main__":
    main()
