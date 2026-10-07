"""overlap_check -- how much do the filter blocks say the same thing? A sample of BUILD days (the ten of tests/test_blocks.days_of, then every
k-th other session up to --days), a plain `donchian` n=10 5-minute run that trades nothing: at EVERY tf-bar decision the family is asked at,
each block (batch 4 and the older price / trend blocks, each side) is asked `allowed("long")` ALONE and the decision is recorded when it says
yes. Prints each block's share of all decisions and every pair of DIFFERENT blocks where the share of one block's yes-decisions that the other
also allows is at least 80 % (with the other's own share, the share it would have by chance; a second block that allows 90 % of all decisions
anyway says nothing and is left out). Reads build days only; never deletes a block.

    python overlap_check.py [--root NQ] [--sess nyam] [--days 30]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

L = Path(__file__).resolve().parent
for p in (str(L), str(L.parent), str(L / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

import l2sim as S                                    # noqa: E402
from families import blocks as B                     # noqa: E402

PARAMS = {"tf": "5", "n": 10, "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0}
OLD = (("adx", "strong"), ("adx", "weak"), ("momentum", "with"), ("momentum", "against"), ("ema20", "with"), ("ema20", "against"),
       ("vwap", "with"), ("vwap", "against"), ("channel", "with"), ("channel", "against"), ("trend", "with"), ("trend", "against"),
       ("rvol", "high"), ("rvol", "low"), ("rvol", "spike"))
NEW = tuple((b, s) for b in ("bbw", "atrp", "er", "macd", "rsidiv", "mfi", "deltadiv", "candle") for s in B.FILTERS[b])
CONFIGS = {f"{b} {s}": B.filter_inputs(b, s) for b, s in OLD + NEW}
MIN_N, SHARE, BASE_MAX = 30, 0.80, 0.90          # a pair is listed when the first block has >= MIN_N yes-decisions, SHARE of them are shared and the second does not allow >= BASE_MAX of all decisions anyway


class Rec(B.WRAPPED["donchian"]):
    """donchian that places nothing and records, at every decision it is asked at, which configs allow a long."""
    LOG: dict = {}

    def fam_signal(self, ctx):
        base, at = self.p, (self.day, (ctx.now_ns - self.t0) // S.NS)
        self.LOG.setdefault("*", set()).add(at)
        try:
            for name, inputs in CONFIGS.items():
                self.p = {**base, **inputs}
                if self.allowed("long"):
                    self.LOG.setdefault(name, set()).add(at)
        finally:
            self.p = base


def sample(root: str, n: int) -> list:
    from test_blocks import days_of
    first = days_of(root)
    rest = [d.isoformat() for d in S.sessions(*S.period("build"), root) if d.isoformat() not in first]
    step = max(1, len(rest) // max(1, n - len(first)))
    return sorted(first + rest[::step][:max(0, n - len(first))])


def pairs(log: dict) -> list:
    """[(share of A's yes-decisions B also allows, A, B, |A|, B's own share of all decisions, the share of B's that A allows)] for pairs of different blocks above SHARE."""
    total, out = len(log["*"]), []
    for a, sa in log.items():
        for b, sb in log.items():
            if a != "*" and b != "*" and a.split()[0] != b.split()[0] and len(sa) >= MIN_N:
                x = len(sa & sb) / len(sa)
                if x >= SHARE and len(sb) / total < BASE_MAX:
                    out.append((x, a, b, len(sa), len(sb) / total, len(sa & sb) / len(sb)))
    return sorted(out, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="NQ")
    ap.add_argument("--sess", default="nyam")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    days = sample(a.root, a.days)
    Rec.LOG = {}
    res = S.run_many([(Rec, {**PARAMS, "sess": a.sess})], days=days, root=a.root, workers=1, on_error="raise")[0]
    log = Rec.LOG
    total = len(log["*"])
    print(f"{a.root} {a.sess} 5m donchian n=10: {len(days)} build days, {res['used']} sessions, {total} decisions")
    print("share of all decisions that each block allows (long):")
    for name in CONFIGS:
        print(f"  {name:22s} {len(log.get(name, ())):5d}  {len(log.get(name, ())) / total:6.1%}")
    rows = pairs(log)
    print(f"pairs of different blocks where >= {SHARE:.0%} of the first one's decisions are also allowed by the second ({len(rows)}):")
    for x, p, q, n, base, back in rows:
        print(f"  {p:22s} -> {q:22s} {x:6.1%} of {n:4d}   (the second alone: {base:.1%}; back: {back:.0%})")


if __name__ == "__main__":
    main()
