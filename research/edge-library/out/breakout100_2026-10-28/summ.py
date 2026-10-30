import re, sys, glob, os, collections
D = 947  # in-sample days
for f in sorted(glob.glob("logs/nq_b*.txt")):
    n = os.path.basename(f)[:-4]; rows = []
    for l in open(f):
        m = re.match(r"\s+(\d+)\s+(\S+)\s+(\d+)%\s+(\d+)%\s+(\d+)\s+(-?[\d,]+)\s+([\d.]+)", l)
        if m and "pts" in m[2]: rows.append((m[2], int(m[5]), int(m[6].replace(",", "")), float(m[7])))
    if not rows: print(n, "no table yet"); continue
    by = collections.defaultdict(list)
    for b, t, net, pf in rows: by[re.match(r"[a-z_]*[\d]+(?:p\d+)?", b)[0]].append((net, t))
    for k, v in sorted(by.items()):
        pos = sum(1 for x in v if x[0] > 0); tr = sum(x[1] for x in v) / len(v)
        print(f"{n[3:]:28s} {k:12s} fixed-pts boxes {pos}/{len(v)} green  avg net {sum(x[0] for x in v)/len(v):>8,.0f}  trades {tr:5.0f} ({tr/D:.2f}/day)")
