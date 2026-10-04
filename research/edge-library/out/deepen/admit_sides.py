"""STAGE 2a, admission of a side whose 2024 heat map passed: library.admission (unchanged) on the side's default variant with the
split applied to its trades. Default = the BUILD central variant if it is in the surviving set, else the surviving variant
closest to the BUILD median (stage-1 rule D); a moved default must pass library.admission ON ITS OWN (the checker's precedent:
donchian_NQ_tf30_nyam was demoted for exactly that). Both variants are judged and printed.
Writes out/deepen/admission.json, members/<name>/ (admitted) or members/_rejected/<name>/ (+ surviving_set.csv either way)."""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_pick_sides as P  # noqa: E402
import judge_sides as J  # noqa: E402
import labels as L  # noqa: E402
import library as LB  # noqa: E402

RD = J.W / "runs_deepen"
REASON = {"vol_lo": "After a quiet day (range at or below its 20-day median) the market is coiled: stops sit close to the range and a "
                    "morning break of the channel has room to run; after a wide day much of the move is already done and breaks get "
                    "faded. (This reason was written AFTER the BUILD split was seen; the tool itself was fixed before any number.)"}


def keep(trades: list, side: str, root: str) -> list:
    lab = L.root_labels(root)
    if side in ("long", "short"):
        return [t for t in trades if t["side"] == side]
    return [t for t in trades if L.day_in_side(side, lab.get(dt.date.fromisoformat(t["date"]).toordinal()))]


def c1_ready(trades, pool_unit, xid, side, root, seed):
    parts = [LB.unit_cell(pool_unit, f"s{sd}_{xid}") for sd in (1, 2)]
    pool = {k: np.concatenate([p[k] for p in parts]) for k in ("date", "sess", "net", "side")}
    pm = L.side_mask(side, root, pool["date"], pool["side"])
    return LB.c1_draws(LB.pack(trades), {k: v[pm] for k, v in pool.items()}, K=200, seed=seed)


def main():
    Jd = json.loads((HERE / "pick_judgement.json").read_text())
    bars = J.BARS
    results = {}
    for k, j in Jd.items():
        if not j["pick"]["pass"]:
            results[k] = {"admit": False, "failed": ["plateau_pick"], "note": "2024 heat map fails: no admission test is run"}
            continue
        uid, side, exact = j["uid"], j["side"], j["exact"]
        key, sess, fam, root, tf = j["key"], j["sess"], j["family"], j["root"], j["tf"]
        T, TS = P.tables(uid, side, exact), P.tables(uid, side, exact, stress=True)
        tb, tp = {t["id"]: t for t in T["build"]}, {t["id"]: t for t in T["pick"]}
        sb, sp = {t["id"]: t for t in TS["build"]}, {t["id"]: t for t in TS["pick"]}
        surv = [i for i in j["both_positive"] if sb[i]["net"] > 0 and sp[i]["net"] > 0]
        med, cm = j["build"]["median_net"], j["central"]
        order = sorted(surv, key=lambda i: (round(abs(tb[i]["net"] - med), 6), tb[i]["vi"], tb[i]["xi"]))
        moved = cm not in surv
        default = cm if not moved else (order[0] if order else None)
        name = f"{fam}_{root}_tf{tf}_{sess}_{side}"
        ub = J.load(key)
        cells = {c["id"]: c for c in ub["meta"]["cells"]}
        pools = {"build": J.load(f"c1-{root}-tf{tf}"), "pick": LB.load_unit(f"c1-{root}-tf{tf}-{sess}-pick", RD)}
        res_all = {}
        for cid in dict.fromkeys([cm, default]):
            if cid is None:
                continue
            cell = cells[cid]
            runs = {}
            for per in ("build", "pick"):
                for stress in (False, True):
                    kk = f"{name}-{cid}-{per}{'-stress' if stress else ''}"
                    p = HERE / "member_runs" / f"{kk}.json"
                    if not p.exists():
                        res = LB.run_member(fam, root, tf, {**cell["variant"], **({"dir": side} if exact else {})}, cell["exit"], per, sess=sess,
                                            stress=stress, build_plateau=j["build"], key=kk)
                        p.parent.mkdir(exist_ok=True)
                        p.write_text(json.dumps({"trades": res["trades"], "inputs": res["meta"]["inputs"]}))
                    runs[(per, stress)] = json.loads(p.read_text())
            # identity with the stores (the member run is the menu's cell), before the split
            for per, u in (("build", T["ub"]), ("pick", T["up"])):
                x = LB.unit_cell(u, cid)
                x = J.masked(x, x["sess"] == LB.SESS_CODE[sess])
                got = runs[(per, False)]["trades"]
                assert len(got) == len(x["net"]) and abs(sum(t["net"] for t in got) - float(x["net"].sum())) < 0.01, (name, cid, per)
            flt = (lambda tr: tr) if exact else (lambda tr: keep(tr, side, root))
            member = {"name": name, "root": root, "tf": tf, "sess": sess, "cell": cid, "inputs": runs[("build", False)]["inputs"],
                      **LB.member_meta(fam, sess, cell["variant"]), "plateau": {"build": j["build"], "pick": j["pick"]},
                      "nulls_bar": {**bars[f"c1-{root}"], "stat": "t"}}
            for per in ("build", "pick"):
                tr = flt(runs[(per, False)]["trades"])
                member[per] = {"trades": tr, "stress": flt(runs[(per, True)]["trades"]), "calendar": LB.calendar(per, root),
                               "c1": c1_ready(tr, pools[per], J.exit_id(cid), side, root, LB.default_seed(f"{name}|{cid}", per))}
            member["notes"] = "; ".join(x for x in (member.get("notes"),
                f"STAGE 2a FILTERED SIDE `{side}`: trades {L.PLAIN[side]}. Why it should matter: {REASON.get(side, 'not written')} "
                f"Labels use daily bars through the PRIOR day only (out/deepen/test_labels.py). "
                + (f"DEFAULT MOVED: the BUILD central variant `{cm}` is not in the surviving set (2024 net {tp[cm]['net']:,.0f}); "
                   f"`{cid}` is the surviving variant closest to the BUILD median." if cid != cm else
                   "This is the BUILD central variant (the one tests (c)-(e) of stage 2a were run on).")) if x)
            res = LB.admission(member, write=False)
            res_all[cid] = {"admit": res["admit"], "failed": res["failed"], "tests": res["tests"], "summary": res["summary"]}
            print(name, cid, "ADMIT" if res["admit"] else "REJECT", res["failed"])
            for a, v in res["tests"].items():
                print("   ", a, {x: (round(y, 3) if isinstance(y, float) else y) for x, y in v.items()})
            if cid == default:
                dmember, dres = member, res
        admit = bool(default is not None and res_all[default]["admit"])
        if moved and admit:
            dres["flag"] = "default moved; library.admission passes on the moved default alone"
        d = LB.write_member(dmember, dres)
        # the surviving set, per year then combined (1 contract + $1,000 risk), with the stressed nets
        cal = LB.calendar("build", root) + LB.calendar("pick", root)
        rows = []
        for i in order:
            xb, xp = P.cell(T["ub"], i, sess, T["filter"], root), P.cell(T["up"], i, sess, T["filter"], root)
            x = {f: np.concatenate([xb[f], xp[f]]) for f in LB.FIELDS}
            z = LB.sized(x, root)
            for a, b in zip(LB.per_year(x, cal), LB.per_year(z, cal, z["cost"])):
                rows.append({"cell": i, "default": i == default, "build_central": i == cm, "period": a["period"],
                             **{m: a[m] for m in LB.METRIC_KEYS}, "t": a["t"], "t_build": tb[i]["t"], "net_1000risk": round(b["net"], 2),
                             "sharpe_1000risk": b["sharpe"], "max_dd_1000risk": b["max_dd"], "worst_open_loss_1000risk": b["worst_open_loss"],
                             "stress_build": sb[i]["net"], "stress_pick": sp[i]["net"]})
        if rows:
            with (d / "surviving_set.csv").open("w", newline="") as fh:
                w = csv.DictWriter(fh, list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        bar = bars[f"c1-{root}"]["bar"]
        extra = ["", f"## Stage 2a record — side `{side}` ({L.PLAIN[side]})",
                 f"* BUILD (side): {j['build']['share_pos'] * 100:.0f} % of {j['build']['cells']} variants positive, median {j['build']['median_net']:,.0f}; "
                 f"central variant `{cm}` passed (a)-(e).",
                 f"* 2024 (side): {j['pick']['share_pos'] * 100:.0f} % positive, median {j['pick']['median_net']:,.0f} -> the table PASSES; "
                 f"but the BUILD central variant made {tp[cm]['net']:,.0f} in 2024 (lift over random entries {j['central_pick']['c1_lift']:,.0f}).",
                 f"* Surviving set: {len(surv)} of {j['build']['cells']} variants are positive in both periods and under 2 ticks + 250 ms "
                 f"(`surviving_set.csv`); {sum((tb[i]['t'] or 0) >= bar for i in surv)} of them have a BUILD t at or above the bar {bar:.2f}.",
                 f"* library.admission on the BUILD central variant `{cm}`: {'ADMIT' if res_all[cm]['admit'] else 'REJECT (' + ', '.join(res_all[cm]['failed']) + ')'}."]
        if moved and default:
            extra.append(f"* library.admission on the rule-moved default `{default}`: "
                         f"{'ADMIT' if res_all[default]['admit'] else 'REJECT (' + ', '.join(res_all[default]['failed']) + ')'}.")
        extra += [f"* Verdict: {'ADMITTED' if admit else 'NOT ADMITTED (near miss; the orchestrator may rule on the surviving set)'}.", ""]
        with (d / "card.md").open("a") as fh:
            fh.write("\n".join(extra))
        results[k] = {"name": name, "admit": admit, "default": default, "default_moved": moved, "central": cm, "surviving": len(surv),
                      "judged": j["build"]["cells"], "surviving_t_above_bar": int(sum((tb[i]["t"] or 0) >= bar for i in surv)),
                      "by_cell": res_all, "dir": str(d)}
    (HERE / "admission.json").write_text(json.dumps(results, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


if __name__ == "__main__":
    main()
