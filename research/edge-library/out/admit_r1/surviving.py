"""STAGE 2b ADMIT, step 3: the surviving set of every unit whose 2024 table passed = cells > 0 on BUILD and on PICK and > 0 under
2 ticks + 250 ms in both. No moved default (EDGE_SPEC STAGE 2b): the BUILD central cell must itself be in the set.
Writes out/admit_r1/surviving.json."""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "admit_r1"
RA = W / "runs_admit_r1"


def net(u, cid, sess):
    x = LB.unit_cell(u, cid)
    return float(x["net"][x["sess"] == LB.SESS_CODE[sess]].sum())


def main():
    J = json.loads((OUT / "pick_judgement.json").read_text())
    out = {}
    for uid, j in J.items():
        if not j["pick"]["pass"]:
            continue
        key, sess, cm = j["key"], j["sess"], j["central"]
        ub, up = LB.load_unit(key), LB.load_unit(f"{key}-{sess}-pick", RA)
        sb, sp = LB.load_unit(f"{key}-{sess}-build-stress", RA), LB.load_unit(f"{key}-{sess}-pick-stress", RA)
        rows = []
        for cid in sorted(set(j["both_positive"]) | {cm}):
            rows.append({"id": cid, "build": round(net(ub, cid, sess), 2), "pick": round(net(up, cid, sess), 2),
                         "build_stress": round(net(sb, cid, sess), 2), "pick_stress": round(net(sp, cid, sess), 2)})
        surv = [r for r in rows if min(r["build"], r["pick"], r["build_stress"], r["pick_stress"]) > 0]
        c = next(r for r in rows if r["id"] == cm)
        ok = any(r["id"] == cm for r in surv)
        out[uid] = {"default": cm, "central": c, "central_survives": ok, "default_moved": False, "judged": j["build"]["cells"],
                    "both_positive": len(j["both_positive"]), "surviving": surv}
        print(f"{uid}: surviving {len(surv)} of {j['build']['cells']} judged (both-positive {len(j['both_positive'])}); central {cm}: "
              f"BUILD {c['build']:,.0f} -> stress {c['build_stress']:,.0f}; 2024 {c['pick']:,.0f} -> stress {c['pick_stress']:,.0f}; "
              f"central survives: {ok}")
    (OUT / "surviving.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
