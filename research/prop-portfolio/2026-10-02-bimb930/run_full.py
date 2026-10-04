import sys, json, collections, time, csv, datetime as dt, zoneinfo
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S, score as SC
from bimb930 import Imb930
cols = list(Imb930.FEATURES)
OUT = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out/"

NY = zoneinfo.ZoneInfo("America/New_York")

def write_csv(trades, path):
    """Tester-shaped sim trades (1 NQ) -> a 2-NQ ledger the onyx.report loader reads (pnl net of commission + slippage)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry_time", "exit_time", "side", "qty", "pnl", "risk", "runup", "drawdown", "entry_price", "exit_price", "commission", "exit_reason"])
        for t in trades:
            e = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, NY).isoformat(sep=" ", timespec="seconds")
            x = dt.datetime.fromtimestamp(t["exit_ms"] / 1000, NY).isoformat(sep=" ", timespec="seconds")
            risk = abs(t["entry_price"] - t["sl"]) * 20.0 * 2
            w.writerow([e, x, t["side"], 2, round(t["net"] * 2, 2), round(risk, 2), round(t["mfe_usd"] * 2, 2), round(t["mae_usd"] * 2, 2),
                        t["entry_price"], t["exit_price"], round(t["commission"] * 2, 2), t["exit_reason"]])

def stats(res):
    tr = res["trades"]
    def agg(rows):
        n = len(rows)
        w = sum(1 for t in rows if t["net"] > 0)
        net = sum(t["net"] for t in rows) * 2          # 1 NQ in the sim -> 2 NQ
        gw = sum(t["net"] for t in rows if t["net"] > 0); gl = -sum(t["net"] for t in rows if t["net"] <= 0)
        return {"n": n, "wins": w, "win_rate": round(w / n, 4) if n else None, "net_2NQ": round(net, 0),
                "pf": round(gw / gl, 3) if gl else None, "avg_2NQ": round(net / n, 1) if n else None}
    by_year = {y: agg([t for t in tr if t["date"][:4] == y]) for y in sorted({t["date"][:4] for t in tr})}
    by_side = {s: agg([t for t in tr if t["side"] == s]) for s in sorted({t["side"] for t in tr})}
    return {"all": agg(tr), "by_year": by_year, "by_side": by_side, "sessions": res["sessions"], "used": res["used"],
            "skipped_by_error": res.get("skipped_by_error"), "both_sides_sessions": res.get("both_sides_sessions")}

if __name__ == "__main__":
    t0 = time.time()
    out = {}
    real = S.run_many([(Imb930, {"mode": m}) for m in ("imb", "long", "short")], features=S.L2Features(cols))
    for m, r in zip(("imb", "long", "short"), real):
        out[m] = stats(r)
        json.dump(r["trades"], open(OUT + f"trades_{m}.json", "w")); write_csv(r["trades"], OUT + f"ledger_{m}_2NQ.csv")
    json.dump(out, open(OUT + "stats_real.json", "w"), indent=1)
    print("real done", round(time.time() - t0), "s", flush=True)
    nulls = []
    for k in range(1, 21):
        r = S.run(Imb930, {"mode": "imb"}, features=SC.C2Features(cols, seed=k))
        nulls.append(stats(r))
        json.dump(nulls, open(OUT + "stats_nulls.json", "w"), indent=1)
        print("null", k, "done", round(time.time() - t0), "s", flush=True)
    print("ALL DONE", flush=True)
