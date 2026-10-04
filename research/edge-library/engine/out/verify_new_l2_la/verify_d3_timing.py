"""D3 x_book: how soon after the fill does the book exit trigger? (timing / counts only, same 10 BUILD days)"""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import verify_bc_options as V
S = V.S
def main():
    sp = V.specs()
    rec, res = V.one_pass(sp, S.L2Features(V.COLS))
    tab = V.Table()
    out = {}
    for (c, p), r in zip(sp, res):
        st = c(p)
        if not c.__name__.startswith("Opt") or st.p["x_book"] != "on":
            continue
        name = c.__name__[3:] + (":" + st.p["at"] if "at" in st.p else "")
        o = out.setdefault(name, {"trades": 0, "book_exits": 0, "trigger_within_2_closes_of_fill": 0, "opposed_at_fill": 0, "held_min": []})
        fired = [x for x in rec if x[0] == "xb" and x[1] == st._lab and x[8]]
        for t in r["trades"]:
            o["trades"] += 1
            sd = 1 if t["side"] == "long" else -1
            m = tab.mean5(t["date"], t["entry_ns"])
            o["opposed_at_fill"] += bool(m is not None and m * sd < 0)
            if t["exit_reason"] != "book":
                continue
            o["book_exits"] += 1
            f = [x[3] for x in fired if x[2] == t["date"] and t["entry_ns"] < x[3] <= t["exit_ns"]]
            lag = (f[0] - t["entry_ns"]) / 60e9
            o["held_min"].append(lag)
            o["trigger_within_2_closes_of_fill"] += lag <= 2.0
    tot = {"trades": 0, "book_exits": 0, "trigger_within_2_closes_of_fill": 0, "opposed_at_fill": 0}
    for k, o in out.items():
        h = o.pop("held_min")
        o["median_min_fill_to_trigger"] = round(float(np.median(h)), 1) if h else None
        for x in tot:
            tot[x] += o[x]
        print(k, o)
    print("ALL", tot)
    Path(__file__).with_name("d3_timing.json").write_text(json.dumps({"by": out, "all": tot}, indent=1))
if __name__ == "__main__":
    main()
