import sys, datetime as dt, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import verify_bc_options as V
S = V.S
def main():
    sp = V.specs()
    feats = S.L2Features(V.COLS)
    rec0, res0 = V.one_pass(sp, feats)
    dd = [dt.date.fromisoformat(x) for x in V.DAYS]
    cuts = {d.isoformat(): V.et_ns(d, 3, 0) for d in dd}
    g = V.Garble(feats, cuts)
    rec1, res1 = V.one_pass(sp, g, g.tape)
    n = 0
    for (c, p), x, y in zip(sp, res0, res1):
        a = [t for t in x["trades"] if t["exit_ns"] < cuts[t["date"]]]
        b = [t for t in y["trades"] if t["exit_ns"] < cuts[t["date"]]]
        if a != b:
            n += 1
            for t, u in zip(a, b):
                if t != u:
                    keys = [k for k in t if t[k] != u.get(k)]
                    print(c.__name__, {k: p[k] for k in p if k in ("sess", "at", "tf", "f_book", "x_book", "f_thin", "stop_mode")}, t["date"],
                          "differing keys:", keys, "exit_reason", t["exit_reason"], u["exit_reason"],
                          "exit ET", dt.datetime.fromtimestamp(t["exit_ns"] / 1e9, V.ET).strftime("%H:%M:%S.%f"),
                          {k: (t[k], u[k]) for k in keys if k in ("both_sides", "oco", "exit_reason")})
            if len(a) != len(b):
                print("  length differs", len(a), len(b))
    print("specs differing:", n)
if __name__ == "__main__":
    main()
