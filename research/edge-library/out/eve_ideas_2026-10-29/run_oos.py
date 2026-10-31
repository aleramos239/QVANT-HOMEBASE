"""OOS (the 3:1 test months, once each) for every ATR and fixed-point box of ideas 15-16 and 23. One store folder per box (symlinks to the idea's in-sample store)."""
import json, os, subprocess, sys
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
SAID = "run 15,16,23 OOS and let me know which boxes are consistent and dont border any unprofitable boxes"
IDEAS = ["i15_16_close_loc_follow", "i23_new_high_long"]
def sh(*a):
    return subprocess.run([PY, "bp.py"] + list(a), cwd=ED, capture_output=True, text=True)
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
n_done = 0
for n in IDEAS:
    parent = "%s-NQ-tf5" % n
    boxes = [b["box"] for b in json.loads(sh("wf", "show", parent, "--json").stdout)["wf"]["is"] if b["settings"].get("stop_mode") != "own"]
    for box in boxes:
        store = "%s__%s" % (parent, box)
        d = os.path.join(ED, "runs_wf", store)
        if os.path.exists(os.path.join(d, "oos")):
            continue
        if n_done >= limit:
            sys.exit(0)
        os.makedirs(d, exist_ok=True)
        for k in ("is", "is.lock"):
            if not os.path.lexists(os.path.join(d, k)):
                os.symlink(os.path.join(ED, "runs_wf", parent, k), os.path.join(d, k))
        p = sh("wf", "pick", store, box, "--who", "Claude, on the owner's word: " + SAID)
        o = sh("wf", "oos", store, box, "--owner-said", SAID, "--workers", "12", "--wait", "7200")
        print(store, "|", (p.stdout + p.stderr).strip().splitlines()[-1:], "|", (o.stdout + o.stderr).strip().splitlines()[-1:], flush=True)
        n_done += 1
