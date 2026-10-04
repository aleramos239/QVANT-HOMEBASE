"""Stage D filters on RESTING entries: how old is the verdict at the fill, and what did the book say AT the fill?
Timing / counts only (no P&L). Same 10 BUILD days, 1 worker."""
import sys, datetime as dt, json
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
        if not hasattr(st, "_lab") or not c.__name__.startswith("Opt"):
            continue
        opt = "fbook" if st.p["f_book"] == "on" else "thin" if st.p["f_thin"] == "on" else None
        if opt is None:
            continue
        name = c.__name__[3:] + (":" + st.p["at"] if "at" in st.p else "") + ":" + opt
        allows = [x for x in rec if x[0] == "allow" and x[1] == st._lab and x[5]]
        o = out.setdefault(name, {"trades": 0, "lag_min": [], "opposed_at_fill": 0, "no_signal_at_fill": 0, "not_thin_at_fill": 0})
        for t in r["trades"]:
            a = [x[3] for x in allows if x[2] == t["date"] and x[4] == t["side"] and x[3] <= t["entry_ns"]]
            if not a:
                continue
            o["trades"] += 1
            o["lag_min"].append((t["entry_ns"] - max(a)) / 60e9)
            sd = 1 if t["side"] == "long" else -1
            if opt == "fbook":
                m = tab.mean5(t["date"], t["entry_ns"])
                if m is None:
                    o["no_signal_at_fill"] += 1
                elif m * sd < 0:
                    o["opposed_at_fill"] += 1
            else:
                th = tab.thin(t["date"], t["entry_ns"], sd)
                if th is None:
                    o["no_signal_at_fill"] += 1
                elif not th:
                    o["not_thin_at_fill"] += 1
    for k, o in out.items():
        l = o.pop("lag_min")
        o["lag_min_median"] = round(float(np.median(l)), 1) if l else None
        o["lag_min_max"] = round(float(np.max(l)), 1) if l else None
        o["share_lag_over_5min"] = round(float(np.mean(np.array(l) > 5)), 2) if l else None
    Path(__file__).with_name("d_lag.json").write_text(json.dumps(out, indent=1))
    for k, o in out.items():
        print(k, o)
if __name__ == "__main__":
    main()
