"""D1 = the L2 screen's bimb_follow tf 5? TRADE IDENTITY against the L2 pilot's screen bundle (L/runs/bimb_follow-tf5) on 20
BUILD days (my 10 + the author's 10). Only rows of those BUILD days are compared; identity fields only, no P&L is read out."""
import sys, json, datetime as dt
from pathlib import Path
ENG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ENG)); sys.path.insert(0, str(ENG.parent))
import l2sim as S, families, run_menus as RM
from families import l2ideas as L2
DAYS = sorted(set(["2021-11-08", "2021-11-26", "2022-03-14", "2022-03-16", "2022-08-17", "2022-11-07", "2023-01-03", "2023-03-15",
        "2023-06-20", "2023-11-24"]) | set(RM.SMOKE_DAYS))
KEYS = ("date", "side", "entry_ms", "entry_price", "exit_ms", "exit_price", "exit_reason")
def main():
    b = Path.home() / "ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/runs/bimb_follow-tf5"
    meta = json.loads((b / "run.json").read_text())
    assert meta["range"]["end"] <= "2024-12-31" and not meta["range"]["holdout"]
    ref = [tuple(t[k] for k in KEYS) for t in json.loads((b / "trades.json").read_text()) if t["date"] in DAYS]
    inp = {k: meta["inputs"][k] for k in ("tf", "sess", "stop_mode", "stop_val", "tgt_r", "max_tr", "k")}
    r = S.run(L2.BimbFollowD1, inp, days=DAYS[:10], workers=1, features=families.features_for("bimb_follow_d1"))
    r2 = S.run(L2.BimbFollowD1, inp, days=DAYS[10:], workers=1, features=families.features_for("bimb_follow_d1"))
    got = [tuple(str(t[k]) if k == "date" else t[k] for k in KEYS) for t in r["trades"] + r2["trades"]]
    a, c = set(ref), set(got)
    print(json.dumps({"days": len(DAYS), "screen_trades": len(ref), "d1_trades": len(got), "identical": len(a & c),
                      "only_screen": len(a - c), "only_d1": len(c - a), "inputs": inp,
                      "first_only_screen": [list(x[:3]) for x in sorted(a - c)[:5]], "first_only_d1": [list(x[:3]) for x in sorted(c - a)[:5]]}, indent=1))
if __name__ == "__main__":
    main()
