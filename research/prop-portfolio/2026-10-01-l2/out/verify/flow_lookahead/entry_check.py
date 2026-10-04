"""Every order of the flow families on the 10 days: sent at a tf-grid decision T, market, live at T + 85 ms, filled on the
first print stamped >= T + 85 ms at that print +/- 1 tick; stop / target on the right side with target = 2 x stop distance
(stop <= 5 x target). Counts only (no P&L)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

S, NS = H.S, H.NS
tot = 0
for name in H.FAMS:
    for tf in H.TFS:
        n = late = 0
        worst = 0.0
        for iso in H.DAYS:
            d, tape, feats, _ = H.day_data(iso)
            log, trades = H.play(name, tf, iso, flat=False)
            hits = [x for x in log if x["hit"] is not None]
            assert len(hits) == len(trades), (name, tf, iso, len(hits), len(trades))
            by_entry = sorted(trades, key=lambda t: t["entry_ns"])
            for x, t in zip(hits, by_entry):
                T = x["now"]
                assert T % (int(tf) * 60 * NS) == 0
                side, kind, sl, tp, ref, min_i = x["hit"]
                assert kind == "market" and t["side"] == side
                k = int(np.searchsorted(tape.ts, T + 85_000_000, "left"))
                assert min_i == k and t["entry_ns"] == int(tape.ts[k]) and t["entry_ns"] >= T + 85_000_000
                sd = 1 if side == "long" else -1
                assert t["entry_price"] == float(tape.px[k]) + sd * 0.25
                # the newest feature row the decision could see was stamped T - 60 s
                r = int(np.searchsorted(feats.usable_ns, T, "right")) - 1
                assert feats.cols["t_utc"][r] * NS + 60 * NS == T and bool(feats.cols["book_ok"][r])
                stop, tgt = (t["entry_price"] - t["sl"]) * sd, (t["tp"] - t["entry_price"]) * sd
                assert stop > 0 and tgt > 0
                worst = max(worst, stop / tgt)
                late += (t["entry_ns"] - T) > NS
                n += 1
        tot += n
        print(f"{name} tf{tf}: {n} orders, all market, filled on the first print >= T + 85 ms (+1 tick); "
              f"{late} filled more than 1 s after T; worst stop/target {worst:.3f}")
print("total", tot)
