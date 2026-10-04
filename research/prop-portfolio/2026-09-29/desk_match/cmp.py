"""desk (tester prop_nq strategies, qty 4 NQ) vs frozen research trades (qty 1 NQ, sess=all runs), per day."""
import json, sys, glob, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
HB = Path.home() / "ramos-quant-homebase"
RUNS = HB / "homebase/.state/tester/runs"; GRIDS = HB / "homebase/.state/tester/grids"
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
BASE = SP / "dm/base3/runs"

# strategy -> (desk run prefix, frozen IS cell, frozen HO run, session minute-of-day window of ENTRY, take_usd)
CFG = {
 "nq_nyam_flex": dict(IS=GRIDS/"20260930-001526-draft_pp_straddle-67c2/cells/10", HO=RUNS/"20260930-224006-draft_pp_straddle-4166", win=(570, 660), X=1500.0),
 "nq_orb_pro":   dict(IS=GRIDS/"20260929-231930-draft_pp_orb-5276/cells/10",      HO=RUNS/"20260930-224226-draft_pp_orb-e64e",      win=(660, 810), X=1000.0),
 "nq_pm_flex":   dict(IS=GRIDS/"20260930-001526-draft_pp_straddle-67c2/cells/32", HO=RUNS/"20260930-224650-draft_pp_straddle-50cf", win=(810, 958), X=600.0),
}
def mod(ms): a = dt.datetime.fromtimestamp(ms/1000, ET); return a.hour*60 + a.minute
def frozen(c):
    out = {}
    for d in (c["IS"], c["HO"]):
        for t in json.load(open(d/"trades.json")):
            if c["win"][0] <= mod(t["entry_ms"]) < c["win"][1]:
                assert t["date"] not in out, t["date"]
                out[t["date"]] = t
    return out
def desk(name):
    d = sorted(BASE.glob(f"*-{name}-*"))[-1]
    ts = {}
    for t in json.load(open(d/"trades.json")):
        assert t["date"] not in ts, (name, t["date"]); ts[t["date"]] = t
    return ts, json.load(open(d/"run.json"))
