"""ADVERSARIAL VERIFIER: the REGISTERED straddle_t class (families/timed.StraddleT, menu offset by name) against the Homebase
tester's own straddle bundles (screen-straddle-tf30, NQ and ES) on 10 BUILD days nobody used for this family.
Trade IDENTITY only (date, side, entry instant, entry / exit price, exit reason, order price, sl, tp). No P&L is printed."""
import sys, json, datetime as dt
sys.dont_write_bytecode = True
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine")
import l2sim as S
import families
from families import timed as T

RUNS = S.REPO / "homebase" / ".state" / "tester" / "runs"
BUNDLE = {"NQ": "20260929-214113-draft_pp_straddle-5d7d", "ES": "20260930-172655-draft_pp_es_straddle-3074"}
DAYS = ["2021-10-12", "2022-02-03", "2022-05-18", "2022-08-26", "2022-10-13", "2023-01-06", "2023-02-14", "2023-05-03", "2023-09-20", "2023-12-13"]
F = ("date", "side", "entry_ms", "entry_price", "exit_price", "exit_reason", "order_price", "sl", "tp")
AT = {"london": "03:00", "nyam": "09:30", "pm": "13:30"}

for root, rid in BUNDLE.items():
    run = json.loads((RUNS / rid / "run.json").read_text())
    assert run["range"]["end"] < "2025-01-01" and not run["range"].get("holdout")
    inp = run["inputs"]
    assert (inp["tf"], inp["sess"], inp["off_atr"], inp["delay_min"], inp["stop_mode"], inp["stop_val"], inp["tgt_r"]) == ("30", "all", 0.5, 0, "atr", 1.5, 2.0), inp
    ref = [t for t in json.loads((RUNS / rid / "trades.json").read_text()) if t["date"] in DAYS]     # BUILD days only; rows of other dates are never looked at
    assert all(S.BUILD[0].isoformat() <= t["date"] <= S.BUILD[1].isoformat() for t in ref)
    ex = {"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}
    specs = [(T.StraddleT, {"at": at, "off": "atr0p5", "tf": "30", "cancel_min": cm, **ex}) for at in AT.values() for cm in (0, 60)]
    res = S.run_many(specs, days=DAYS, root=root, workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res)
    for (sess, at), k in zip(AT.items(), range(0, 6, 2)):
        want = sorted(tuple(t[f] for f in F) for t in ref if S.session_of(t["entry_ms"]) == sess)
        got0 = sorted(tuple(t[f] for f in F) for t in res[k]["trades"])
        got60 = sorted(tuple(t[f] for f in F) for t in res[k + 1]["trades"])
        fire = {d: S.et_ns(dt.date.fromisoformat(d), at) // 10**6 for d in DAYS}
        want60 = [w for w in want if w[2] < fire[w[0]] + 3600_000]
        print(f"{root} {sess} {at}: tester trades={len(want)} | registry class cancel 0: {len(got0)} identical={got0 == want} | "
              f"registered (cancel 60): {len(got60)} = tester trades entered within 60 min ({len(want60)}): {got60 == want60}")
        if got0 != want:
            print("   only tester:", [w[:3] for w in want if w not in got0][:5], "only sim:", [g[:3] for g in got0 if g not in want][:5])
