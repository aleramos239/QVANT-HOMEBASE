"""Does judge.py (read-only here) discover every control seed this stage wrote? Seed lists and store names only."""
import sys
from pathlib import Path
W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W)); sys.path.insert(0, str(W / "engine"))
import judge as J  # noqa: E402

UNITS = [("straddle_t_0830-NQ-tf30-pre", "shift"), ("straddle_tight_0830-NQ-tf30-pre", "shift"), ("straddle_tight_0830-GC-tf30-pre", "shift"),
         ("straddle_tight_1000-NQ-tf30-nyam", "shift"), ("straddle_tight_1000-GC-tf30-nyam", "shift"), ("straddle_t_1800-NQ-tf30-eve", "shift"),
         ("first_bar_mom-NQ-tf30-mid", "c1"), ("first_bar_mom-NQ-tf15-mid", "c1"), ("first_bar_mom-ES-tf15-mid", "c1"), ("orb-NQ-tf15-pre", "c1"),
         ("tema_slope-NQ-tf30-eve", "c1"), ("donchian-NQ-tf30-nyam", "c1"),
         ("vol_spike_break-NQ-tf5-pm", "c1"), ("donchian-NQ-tf5-pm", "c1"), ("vwap_z-NQ-tf30-mid", "c1")]
bad = 0
for addr, kind in UNITS:
    u = J.unit(addr)
    ids = sorted(J.menu_ids(u))
    need = sorted({i.rsplit("_", 1)[-1] for i in ids}) if kind == "c1" else list(ids)
    for per in (("build",) if addr.split("-")[0] in ("vol_spike_break", "vwap_z") or addr == "donchian-NQ-tf5-pm" else ("build", "pick", "check")):
        S = J.seed_stores(u, per, kind, need)
        rows = [r if isinstance(r, dict) else next(x for x in r if isinstance(x, dict)) for r in S.values()]
        names = sorted({f"{r['dir'].name}/{r['key']}" for r in rows})
        ok = sorted(S) == list(range(1, 11))
        bad += not ok
        print(f"{addr:34s} {per:5s} {kind:5s} seeds {sorted(S)} {'OK' if ok else 'INCOMPLETE'} <- {names}")
print("ALL 10 SEEDS FOUND" if not bad else f"{bad} unit x period without 10 seeds")
