"""Second batch: the six brk100 families (engine/families/brk100.py), same rules as make.py (NQ, hm60 fixed-point rows, one trade a day)."""
import json, pathlib
OUT = pathlib.Path(__file__).parent / "specs2"; OUT.mkdir(exist_ok=True)
# (id, name, session, bar, family, params, fixed, why)
I = [
 (101, "pd_cond", "nyam", "5", "pd_cond_bracket", {"cond": ["nr4", "nr7", "inside"]}, {}, "prior day high/low break after a narrow or inside day"),
 (102, "nd_bracket", "nyam", "5", "nd_bracket", {"n_d": [2, 5, 10, 20]}, {}, "break of the multi-day high/low"),
 (103, "orb_cond", "nyam", "5", "orb_cond", {"cond": ["inside", "nr7", "gapout"]}, {}, "30-minute opening range break on a coiled or gap-out day"),
 (104, "on_narrow", "nyam", "5", "on_narrow_bracket", {"k": [0.3, 0.5, 0.7]}, {}, "narrow overnight range break"),
 (105, "orb_dtrend", "nyam", "5", "orb_dtrend", {"n_d": [20, 50, 100]}, {}, "30-minute opening range break with the daily trend"),
 (106, "atr_contract", "nyam", "5", "atr_contract_break", {"k": [0.5, 0.65, 0.8]}, {}, "close out of a contracted-range coil"),
]
for no, nm, sess, bar, fam, params, fixed, why in I:
    name = f"nq_b{no:03d}_{nm}"
    spec = {"name": name, "version": 1,
      "card": {"why": f"Breakout idea #{no} (new family, owner's 100 list, 2026-10-28): {why}, because the stops of the traders on the other side of the break feed the move.",
        "loser": "Traders on the wrong side of the break whose stops get hit.",
        "home": {"market": "NQ", "session": sess, "bar": bar}, "neighbors": [f"NQ {sess} 15"],
        "main_setting": next(iter(params)), "sides": "both" if fam != "atr_contract_break" else "both",
        "sides_why": "A break can go either way, one rule.", "loses_when": "Chop days where the break reverses at once."},
      "run": {"exits": "hm60", "family": fam, "params": params, **({"fixed": fixed} if fixed else {}), "limits": {"max_tr": 1}}}
    (OUT / f"{name}.json").write_text(json.dumps(spec, indent=1))
print(len(I), "specs")
