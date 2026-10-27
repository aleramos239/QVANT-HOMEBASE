"""Compare two engine traces (tests/engine_trace.py): python tests/engine_parity.py BASE NEW [BASE2]

Per test: equal, or the first differing fields. Timing keys (ts, *_ms, *_ts, until) and the arguments of timing calls
(request_rtts_ms) are dropped, and pytest's numbered tmp folders are read as one name. Rows are grouped by account,
each account keeping its own order (exits run side by side across accounts by design). With BASE2 (a second run of
BASE's tree) the fields that differ between BASE and BASE2 are noise and are masked; a test whose shape itself differs
between the two base runs is counted as not comparable."""
import json
import os
import re
import sys

VOL = re.compile(r"(^ts$|^until$|_ms$|_ts$)")
TMP = re.compile(r"pytest-of-[^/]+/pytest-\d+/([^/]*?)\d*(?=/|$)")      # .../pytest-20/desklab2095 -> pytest-N/desklabN


def load(d):
    out = {}
    for f in os.listdir(d):
        with open(os.path.join(d, f)) as fh:
            t = json.load(fh)
        out[t["nodeid"]] = t
    return out


def paths(x, p=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from paths(v, p + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from paths(v, p + (i,))
    else:
        yield p, x


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if not VOL.search(str(k))}
    if isinstance(x, list):
        if len(x) > 3 and x[0] in ("call", "ret") and VOL.search(str(x[3])):
            return x[:4]                                     # a timing call: its clock arguments are noise
        return [strip(v) for v in x]
    return TMP.sub(r"pytest-N/\1N", x) if isinstance(x, str) else x


def acct(r):
    if r[0] in ("call", "ret"):
        return str(r[2] or "")
    d = r[2] if len(r) > 2 and isinstance(r[2], dict) else {}
    return str(d.get("account") or "")


def flat(t):
    rows = sorted(strip(t["rows"]), key=acct)          # stable: each account keeps its own order
    return dict(paths({"rows": rows, "files": strip(t["files"])}))


def main(argv):
    a, b = load(argv[1]), load(argv[2])
    c = load(argv[3]) if len(argv) > 3 else None
    same = differ = noisy = 0
    bad = []
    for nid, ta in a.items():
        tb = b.get(nid)
        if tb is None:
            bad.append((nid, "missing in NEW"))
            continue
        fa, fb = flat(ta), flat(tb)
        mask = set()
        if c and nid in c:
            fc = flat(c[nid])
            if set(fa) != set(fc):
                noisy += 1
                continue
            mask = {k for k in fa if fa[k] != fc[k]}
        d = [k for k in sorted((set(fa) | set(fb)) - mask, key=repr) if fa.get(k, "<absent>") != fb.get(k, "<absent>")]
        if d:
            differ += 1
            bad.append((nid, d[:3]))
        else:
            same += 1
    print(f"tests={len(a)} same={same} differ={differ} not-comparable(noisy shape)={noisy} only-in-NEW={len(set(b) - set(a))}")
    for x in bad[:20]:
        print("  ", x)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
