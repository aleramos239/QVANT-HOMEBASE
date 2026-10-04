"""STAGE 2b ADMIT, step 4: library.admission for every unit whose 2024 table passed (copy of out/admit/admit_members.py, + the
time-fired control, NO moved default: a unit whose BUILD central cell is not in its surviving set is rejected without a member run).
Writes members/<name>/ (or members/_rejected/<name>/ with surviving_set.csv) and out/admit_r1/admission.json."""
import csv
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "admit_r1"
RA = W / "runs_admit_r1"


def sess_cell(u, cid, sess):
    x = LB.unit_cell(u, cid)
    m = x["sess"] == LB.SESS_CODE[sess]
    return {k: v[m] for k, v in x.items()}


def shift_ctrl(net, su, cid):
    nets = [float(LB.unit_cell(su, f"s{sd}_{cid}")["net"].sum()) for sd in (1, 2)]
    return {"lift": round(net - float(np.mean(nets)), 2), "mean": round(float(np.mean(nets)), 2), "p95": round(max(nets), 2),
            "p_beat": float(np.mean([net > v for v in nets])), "fallback_share": 0.0, "short": 0,
            "pool_trades": int(sum(len(LB.unit_cell(su, f"s{sd}_{cid}")["net"]) for sd in (1, 2))), "control": "same bracket at a random minute, 2 seeds"}


def c1_for(trades, pool_unit, xid, seed):
    parts = [LB.unit_cell(pool_unit, f"s{sd}_{xid}") for sd in (1, 2)]
    pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net")}
    return LB.c1_draws(LB.pack(trades), pool, K=200, seed=seed)


def surviving_rows(sv, ub, up, sess, root, cid):
    cal = LB.calendar("build", root) + LB.calendar("pick", root)
    rows, lines = [], []
    for s in sv["surviving"]:
        xb, xp = sess_cell(ub, s["id"], sess), sess_cell(up, s["id"], sess)
        x = {k: np.concatenate([xb[k], xp[k]]) for k in LB.FIELDS}
        z = LB.sized(x, root)
        py, pz = LB.per_year(x, cal), LB.per_year(z, cal, z["cost"])
        for a, b in zip(py, pz):
            rows.append({"cell": s["id"], "default": s["id"] == cid, "period": a["period"], **{k: a[k] for k in LB.METRIC_KEYS}, "t": a["t"],
                         "net_1000risk": round(b["net"], 2), "sharpe_1000risk": b["sharpe"], "max_dd_1000risk": b["max_dd"],
                         "worst_open_loss_1000risk": b["worst_open_loss"], "stress_build": s["build_stress"], "stress_pick": s["pick_stress"]})
        yr, zr = {a["period"]: a for a in py}, {b["period"]: b for b in pz}
        lines.append(f"| `{s['id']}`{' **(default)**' if s['id'] == cid else ''} | " + " | ".join(
            f"{yr[p]['net']:,.0f}" for p in ("2021*", "2022", "2023", "2024", "combined")) +
            f" | {yr['combined']['trades']} | {s['build_stress']:,.0f} / {s['pick_stress']:,.0f} | {zr['combined']['net']:,.0f} | "
            f"{(zr['combined']['sharpe'] or 0):.2f} |")
    return rows, lines


def main():
    J = json.loads((OUT / "pick_judgement.json").read_text())
    SV = json.loads((OUT / "surviving.json").read_text())
    bars = json.loads((OUT / "null_bars.json").read_text())
    B = {r["uid"]: r for r in csv.DictReader((OUT / "build_units.csv").open())}
    results = {}
    for uid, sv in SV.items():
        j = J[uid]
        key, sess, fam, root, tf, timed = j["key"], j["sess"], j["family"], j["root"], j["tf"], j["timed"]
        name = f"{fam}_{root}_tf{tf}_{sess}"
        ub, up = LB.load_unit(key), LB.load_unit(f"{key}-{sess}-pick", RA)
        cid = sv["default"]
        if not sv["central_survives"]:
            c = sv["central"]
            d = LB.MEMBERS / "_rejected" / name
            d.mkdir(parents=True, exist_ok=True)
            rows, _ = surviving_rows(sv, ub, up, sess, root, cid)
            if rows:
                with (d / "surviving_set.csv").open("w", newline="") as fh:
                    w = csv.DictWriter(fh, list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
            why = ("net_pick" if c["pick"] <= 0 else "") or ("stress_pick" if c["pick_stress"] <= 0 else "stress_build")
            (d / "card.md").write_text("\n".join([
                f"# {name} — REJECTED (stage 2b, 2026-10-04)", "",
                f"* BUILD central variant `{cid}`: BUILD ${c['build']:,.0f} (under 2 ticks + 250 ms ${c['build_stress']:,.0f}); "
                f"2024 ${c['pick']:,.0f} (under stress ${c['pick_stress']:,.0f}).",
                f"* BUILD heat map {100 * j['build']['share_pos']:.0f} % of {j['build']['cells']} variants positive, median ${j['build']['median_net']:,.0f}; "
                f"2024 heat map {100 * j['pick']['share_pos']:.0f} %, median ${j['pick']['median_net']:,.0f} (passes).",
                f"* The central variant is not positive in 2024 and under stress. EDGE_SPEC STAGE 2b allows no moved default: **not admitted**.",
                f"* {len(sv['surviving'])} of {sv['judged']} variants are positive in both periods and under stress (`surviving_set.csv`): "
                "kept as a record only, not as a member.", ""]))
            results[uid] = {"name": name, "admit": False, "failed": [why, "no_moved_default"], "default": cid, "surviving": len(sv["surviving"]),
                            "judged": sv["judged"], "central": c, "dir": str(d)}
            print(name, "REJECT", results[uid]["failed"])
            continue
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
        for per, u in (("build", ub), ("pick", up)):               # identity with the stores (the member run is the menu's cell)
            ref = sess_cell(u, cid, sess)
            got = runs[(per, False)]["trades"]
            assert len(got) == len(ref["net"]) and abs(sum(t["net"] for t in got) - float(ref["net"].sum())) < 0.01, (name, per)
        g = f"{'shift' if timed else 'c1'}-{root}"
        member = {"name": name, "root": root, "tf": tf, "sess": sess, "cell": cid, "inputs": runs[("build", False)]["inputs"],
                  **LB.member_meta(fam, sess, cell["variant"]), "plateau": {"build": j["build"], "pick": j["pick"]},
                  "nulls_bar": {**bars[g], "stat": "t"}}
        for per in ("build", "pick"):
            tr = runs[(per, False)]["trades"]
            if timed:
                su = LB.load_unit(f"{key}-shift") if per == "build" else LB.load_unit(f"{key}-{sess}-pick-shift", RA)
                ctl = shift_ctrl(sum(t["net"] for t in tr), su, cid)
            else:
                pool = LB.load_unit(f"c1-{root}-tf{tf}") if per == "build" else LB.load_unit(f"c1-{root}-tf{tf}-{sess}-pick", RA)
                ctl = c1_for(tr, pool, cid.rsplit("_", 1)[-1], LB.default_seed(name, per))
            member[per] = {"trades": tr, "stress": runs[(per, True)]["trades"], "calendar": LB.calendar(per, root), "c1": ctl}
        res = LB.admission(member, write=False)
        note, flag = [], None
        b = B[uid]
        if timed and b.get("bar_flag") == "True":
            flag = (f"FLAGGED ADMISSION: the best-of-random bar of this unit is THIN ({bars[g]['nulls']} random replicates: the round-1 "
                    f"random-minute / random-direction stores of {root}; bar {bars[g]['bar']:.2f}). Its BUILD t is {float(b['m_t']):.2f}: above that bar, "
                    f"but BELOW the same bar with stage 1's random-minute straddles pooled in ({float(b['bar_all']):.2f}, 26 replicates) and below the "
                    f"random-entry bar of {root} bar families ({bars['c1-' + root]['bar']:.2f}). Admitted by the rule written before any number was "
                    "opened (out/admit_r1/judge_build.py); checker / orchestrator: confirm or demote to near miss.")
            res["flag"] = flag
            note.append(flag)
        if note:
            member["notes"] = "; ".join(x for x in (member.get("notes"), *note) if x)
        stale = LB.MEMBERS / ("_rejected" if res["admit"] else "") / name
        if res["admit"] and stale.exists():
            import shutil
            shutil.rmtree(stale)
        d = LB.write_member(member, res)
        rows, lines = surviving_rows(sv, ub, up, sess, root, cid)
        with (d / "surviving_set.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        cal = LB.calendar("build", root) + LB.calendar("pick", root)
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
                        "dir": str(d), "default": cid, "default_moved": False, "surviving": len(sv["surviving"]), "judged": sv["judged"],
                        "trades_per_day": round(tpd, 3), "flag": flag}
        print(name, "ADMIT" if res["admit"] else "REJECT", res["failed"], "| FLAG" if flag else "")
        for k, v in res["tests"].items():
            print("   ", k, {a: (round(x, 3) if isinstance(x, float) else x) for a, x in v.items()})
    (OUT / "admission.json").write_text(json.dumps(results, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


if __name__ == "__main__":
    main()
