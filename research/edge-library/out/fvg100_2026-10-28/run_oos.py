"""OOS (the 3:1 test months, once each) for the 40 best single boxes listed on fvg_top10_heatmaps.html. One store folder per box (symlinks to the idea's in-sample store)."""
import glob, json, os, subprocess, sys
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
SAID = "run all the Best single boxes (all 68 specs) OOS and let me know which are consistent and which were luck"
def sh(*a):
    return subprocess.run([PY, "bp.py"] + list(a), cwd=ED, capture_output=True, text=True)
singles = []
for d in glob.glob(os.path.join(ED, "out/fvg100_2026-10-28/done_f100_*")):
    n = os.path.basename(d)[10:]
    r = sh("wf", "show", "f100_%s-NQ-tf%s" % (n, "15" if n.endswith("15") else "5"), "--json")
    try:
        for b in json.loads(r.stdout)["wf"]["is"]:
            if b["settings"].get("stop_mode") == "pts" and (b["t_stat"] or 0) >= 2.5 and b["years_green"] >= 5 and b["trades"] >= 300:
                singles.append((b["t_stat"], n, b["box"]))
    except Exception:
        pass
singles.sort(reverse=True)
todo = singles[:40]
json.dump(todo, open(os.path.join(ED, "out/fvg100_2026-10-28/oos_boxes.json"), "w"))
only = sys.argv[1:]                       # optional: run just these "idea:box" items
for t, n, box in todo:
    if only and "%s:%s" % (n, box) not in only:
        continue
    tf = "15" if n.endswith("15") else "5"
    parent = "f100_%s-NQ-tf%s" % (n, tf)
    store = "%s__%s" % (parent, box)
    d = os.path.join(ED, "runs_wf", store)
    if os.path.exists(os.path.join(d, "oos")):
        print("done", store); continue
    os.makedirs(d, exist_ok=True)
    for k in ("is", "is.lock"):
        if not os.path.lexists(os.path.join(d, k)):
            os.symlink(os.path.join(ED, "runs_wf", parent, k), os.path.join(d, k))
    p = sh("wf", "pick", store, box, "--who", "Claude, on the owner's word: " + SAID)
    print(store, "pick:", (p.stdout + p.stderr).strip().splitlines()[-1:] , flush=True)
    o = sh("wf", "oos", store, box, "--owner-said", SAID, "--workers", "12", "--wait", "7200")
    print(store, "oos:", (o.stdout + o.stderr).strip().splitlines()[-1:], flush=True)
