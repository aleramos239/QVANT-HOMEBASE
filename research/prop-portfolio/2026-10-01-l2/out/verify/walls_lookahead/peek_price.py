"""Verifier power check: a family that reads the NEXT print instead of the last one (tape look-ahead) must fail T1."""
import sys, zlib
sys.argv = ["x"]
import numpy as np
import verify_walls as V
S, MIN = V.S, V.MIN
REAL = S.Ctx.last_price
NEXT = property(lambda self: float(self._s.px[self._s.i]) if self._s.i < self._s.hi else None)

def mutant(base):
    class M(base):
        def fam_signal(self, ctx):
            S.Ctx.last_price = NEXT
            try:
                super().fam_signal(ctx)
            finally:
                S.Ctx.last_price = REAL
    return M

tot = {}
for iso in ["2021-11-10", "2022-03-22", "2023-05-18"]:
    d, tape, feats, prior = V.load(iso)
    for base_cls in (V.Bounce, V.Break):
        for cls, tag in ((base_cls, "real"), (mutant(base_cls), "next_print_mutant")):
            params = {"tf": "1", "max_tr": 20, "m": 3.0}
            base = V.run(cls, params, d, tape, feats, prior)
            g = np.random.default_rng(zlib.crc32(iso.encode()))
            dec = [x[0] for x in base[0].seen]
            cuts = [int(c) for c in g.choice(dec, size=40, replace=False)]     # cuts exactly AT decisions
            c = tot.setdefault((base_cls.__name__, tag), {"cuts": 0, "any": 0, "orders_or_trades": 0})
            for n, cut in enumerate(cuts):
                t2, f2 = V.garbage(tape, feats, cut, seed=n + 5)
                bad = V.invariant(base, V.run(cls, params, d, t2, f2, prior), cut)
                c["cuts"] += 1
                c["any"] += bool(bad)
                c["orders_or_trades"] += bool(set(bad) & {"orders", "entries", "closed_trades"})
for k, v in tot.items():
    print(k, v)
