"""COUNTS ONLY: how much the parity and the worker tests of tests/test_blocks.py compare (no net is read)."""
import sys
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
for p in (W, W + "/engine", W + "/engine/tests"):
    sys.path.insert(0, p)
if __name__ == "__main__":
    import families, l2sim as S, run_menus as RM
    from families import blocks as B
    import test_blocks as T
    for root in ("NQ", "ES", "GC"):
        days = T.days_of(root)
        exits = [S.menu(root)[k] for k in (2, 9, 28)]
        specs, pairs = [], []
        for name in T.PARITY + ["ib"]:
            cls = families.REGISTRY[name][0]
            for v in families.library(name)["variants"]:
                for x in exits:
                    for sess, hold in [(s, "day") for s in RM.DAY_PASSES] + [("all", "session")]:
                        p = {**v, **x, "tf": "5", "sess": sess, "hold_to": hold}
                        if not cls(p).sessions():
                            continue
                        q = {**p, "ib_min": "60"} if name == "ib" else p
                        pairs.append((name, len(specs)))
                        specs += [(cls, p), (B.WRAPPED["ib_n" if name == "ib" else name], q)]
        res = S.run_many(specs, days=days, root=root, workers=4)
        cnt, diff = {}, 0
        for name, k in pairs:
            c = cnt.setdefault(name, [0, 0])
            c[0] += 1
            c[1] += len(res[k]["trades"])
            diff += res[k]["trades"] != res[k + 1]["trades"]
        print(root, "days", len(days), "pairs", len(pairs), "pairs that differ", diff, "| per family (pairs, trades compared):", cnt, flush=True)
    for root in ("NQ", "GC"):
        days = T.days_of(root)
        specs = T._on_specs(root)
        f = S.L2Features(B.BOOK_COLS) if root == "NQ" else None
        a = S.run_many(specs, days=days, root=root, workers=1, features=f)
        b = S.run_many(specs, days=days, root=root, workers=8, features=f)
        print(root, "blocks ON, 1 vs", b[0]["meta"]["workers"], "workers:", len(specs), "specs,", sum(len(x["trades"]) for x in a), "trades, specs that differ",
              sum(x["trades"] != y["trades"] for x, y in zip(a, b)), "| trades per spec", [len(x["trades"]) for x in a], flush=True)
