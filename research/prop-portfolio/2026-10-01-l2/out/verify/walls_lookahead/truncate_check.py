"""T4 (verifier): TRUNCATION instead of garbage -- the tape ends at the cut (no print with ts >= cut) and the feature table
ends at the cut (no row with usable_ns > cut). Everything up to the cut must equal the full-day run. Also the public
l2sim.run path (L2Features loader, 1 worker) must give the Spy runs' trades. Counts only."""
import sys, zlib
sys.argv = ["x"]
import numpy as np
import verify_walls as V
S, W, MIN = V.S, V.W, V.MIN
tot = {"cuts": 0, "viol": 0, "run_path_days": 0, "run_path_trades": 0}
DAYS = V.DAYS[:10]
for iso in DAYS:
    d, tape, feats, prior = V.load(iso)
    for cls, base_cls in ((V.Bounce, W.WallBounce), (V.Break, W.WallBreak)):
        for tf in ("1", "5"):
            params = {"tf": tf}
            base = V.run(cls, params, d, tape, feats, prior)
            g = np.random.default_rng(zlib.crc32(f"{iso}{cls.__name__}{tf}".encode()))
            cuts = [S.et_ns(d, "00:00") + int(m) * MIN + int(o) for m, o in zip(g.integers(30, 940, 6), g.integers(0, 60 * S.NS, 6))]
            cuts += [c["t"] for c in base[0].calls] + [t["entry_ns"] + 1 for t in base[1]]
            for cut in cuts:
                k = int(np.searchsorted(tape.ts, cut, side="left"))
                if k == 0:
                    continue
                t2 = S.Tape(tape.root, tape.date, tape.contract, tape.ts[:k], tape.px[:k], tape.size[:k])
                n = int(np.searchsorted(feats.usable_ns, cut, side="right"))
                f2 = S.Features(feats.usable_ns[:n], {c: v[:n] for c, v in feats.cols.items()})
                other = V.run(cls, params, d, t2, f2, prior)
                # a position still open at the cut is flattened by the truncated run's own end of tape ("eod", at the last
                # print before the cut): that row is an artefact of the truncation, not a trade of the day -> its exit side
                # is dropped from the comparison (its ENTRY side is still compared: exit_ns set to the cut)
                tr = [dict(t, exit_ns=cut) if t["exit_reason"] == "eod" else t for t in other[1]]
                n_eod = sum(t["exit_reason"] == "eod" for t in other[1])
                open_at_cut = sum(t["entry_ns"] < cut <= t["exit_ns"] for t in base[1])
                assert n_eod == open_at_cut, (iso, cls.__name__, tf, n_eod, open_at_cut)
                bad = V.invariant(base, (other[0], tr, other[2]), cut)
                tot["open_at_cut"] = tot.get("open_at_cut", 0) + open_at_cut
                tot["cuts"] += 1
                tot["viol"] += bool(bad)
                if bad:
                    print("VIOLATION", iso, cls.__name__, tf, bad)
            # the public path: l2sim.run on this one day, 1 worker, screen options
            kw = getattr(base_cls, "SCREEN_RUN", {})
            res = S.run(base_cls, params, days=[iso], workers=1, features=S.L2Features(base_cls.FEATURES), keep_ns=True, **kw)
            assert res["skipped_by_error"] == 0 and res["both_sides_sessions"] == 0
            a = [{k: v for k, v in t.items()} for t in res["trades"]]
            b = [{k: v for k, v in t.items() if k != "_k"} for t in base[1]]
            assert a == b, (iso, cls.__name__, tf, len(a), len(b))
            tot["run_path_days"] += 1
            tot["run_path_trades"] += len(a)
print(tot)
