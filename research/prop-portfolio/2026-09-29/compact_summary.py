"""Formatting-only post-processor (no numbers recomputed): out/holdout_summary_full.md -> out/holdout_summary.md (<=70 lines).
Merges the per-firm eval tables into one table and drops blank lines. Not part of the frozen scorer."""
import re, pathlib
import pilot as PL                      # pilot dir (NQ default; PP_PILOT=es / --pilot es)
O = PL.DIR / "out"
L = (O / "holdout_summary_full.md").read_text().splitlines()
out, i, evalhdr = [], 0, None
firms = []
while i < len(L):
    l = L[i]
    if not l.strip(): i += 1; continue
    m = re.match(r"## (lucid\w*|apex\w*) \((.*)\)", l)
    if m:
        firms.append(f"{m.group(1)} = {m.group(2)}")
        hdr, sep = L[i+1], L[i+2]; i += 3
        if evalhdr is None:
            evalhdr = (hdr, sep); idx = len(out); out.append("@@EVAL@@")
        while i < len(L) and L[i].startswith("|"):
            out.append(("@@ROW@@", L[i])); i += 1
        continue
    out.append(l); i += 1
res = []
for o in out:
    if o == "@@EVAL@@":
        res.append("## Eval finalists, all firms (rules: " + "; ".join(firms) + ")"); res += list(evalhdr)
    elif isinstance(o, tuple): res.append(o[1])
    else: res.append(o)
(O / "holdout_summary.md").write_text("\n".join(res) + "\n")
print(len(res), "lines")
