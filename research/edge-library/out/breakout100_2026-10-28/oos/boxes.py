"""List the boxes to read on the test months: the 10 variants of heat/make.py, fixed-point (pts) and structure (own) stops. -> boxes.json"""
import re, json, subprocess
from pathlib import Path
W = Path(__file__).resolve().parents[3]
PY = Path.home() / "ramos-quant-homebase/.venv-research/bin/python"
VARS = [("nq_b033_on_bracket","r_start0100"),("nq_b033_on_bracket","r_start0000"),("nq_b033_on_bracket","r_start0300"),("nq_b089_ib_break","ib_min30"),
        ("nq_b089_ib_break","ib_min15"),("nq_b018_pd_bracket_on","off_min15"),("nq_b044_squeeze","sq_typeinside"),("nq_b039_pre_bracket","r_start0800"),
        ("nq_b032_lon_break","min_rng_atr2"),("nq_b041_london_kz_bracket","r_end0400")]
out = []
for nm in sorted({v[0] for v in VARS}):
    wf = json.loads(subprocess.run([str(PY), str(W/"bp.py"), "wf", "show", nm, "--json"], capture_output=True, text=True, cwd=W).stdout)
    for r in wf["wf"]["is"]:
        m = re.match(r"^(.*)_(pts|own)([\dp]+)-r([\dp]+)$", r["box"])
        if m and (nm, m[1]) in VARS: out.append(dict(store=nm, n=r["n"], box=r["box"], var=m[1], kind=m[2]))
json.dump(out, open(Path(__file__).with_name("boxes.json"), "w"), indent=0)
print(len(out), {k: sum(o["kind"]==k for o in out) for k in ("pts","own")})
