import json, csv, collections, numpy as np, pandas as pd
from pathlib import Path
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
S = json.loads((W/"out/check_admit/scan.json").read_text())
runs = [s for s in S if s["dir"] == "runs"]; adm = [s for s in S if s["dir"] == "runs_admit"]
print("runs stores", len(runs), "build", sum(s["stage"]=="build" for s in runs), "null", sum(s["stage"]=="null" for s in runs), "| runs_admit", len(adm))
print("total trades runs", sum(s["hold"]["n"] for s in runs))
# --- periods / dates / hold
print("runs periods", collections.Counter(s["period"] for s in runs), "max date", max(s["hold"]["max_date"] for s in runs if s["hold"]["n"]), "min", min(s["hold"]["min_date"] for s in runs if s["hold"]["n"]))
print("admit periods", collections.Counter((s["period"]) for s in adm), "max date", max(s["hold"]["max_date"] for s in adm if s["hold"]["n"]))
for s in adm: print("  ", s["key"], s["period"], s["hold"].get("min_date"), s["hold"].get("max_date"), "sess", s["sess_present"], "cells", s["n_cells"], "hold", s["hold_to"], s["cell_hold"])
print("hold_to meta", collections.Counter(s["hold_to"] for s in S), "cell hold", collections.Counter(str(s["cell_hold"]) for s in S))
rs = collections.Counter(); cm = collections.Counter(); a16 = 0; ead = 0; se = 0; none = 0
for s in S:
    h = s["hold"]
    if not h["n"]: continue
    rs.update(h["reasons"]); cm.update(h["clock_exit_minutes"]); a16 += h["after_1600"]; ead += h["exit_after_trade_date"]; se += h["clock_exit_at_session_end"]; none += s["sess_none"]
print("exit reasons", dict(rs))
print("clock-exit minutes (time/eod/other)", dict(sorted(cm.items())))
print("exits 16:00-18:00:", a16, "| exit calendar day after trade date:", ead, "| clock exits at entry-session end:", se, "| trades with no session:", none)
# --- units vs analyst
mine = {u["uid"]: u for s in runs for u in s["units"]}
meta = {s["key"]: s for s in runs}
B = {r["uid"]: r for r in csv.DictReader((W/"out/admit/build_units.csv").open())}
print("judged units mine", len(mine), "analyst", len(B), "only mine", len(set(mine)-set(B)), "only analyst", len(set(B)-set(mine)))
dp = [u for u in mine if u in B and str(mine[u]["pass"]) != B[u]["plateau"]]
dm = [u for u in mine if u in B and (mine[u]["member"] or "") != B[u]["member"]]
ds = [u for u in mine if u in B and mine[u]["share"] is not None and abs(mine[u]["share"] - float(B[u]["share_pos"])) > 6e-5]
dmed = [u for u in mine if u in B and mine[u]["median"] is not None and abs(mine[u]["median"] - float(B[u]["median_net"])) > 0.011]
dt_ = [u for u in mine if u in B and mine[u]["t"] is not None and B[u].get("m_t") not in ("", None) and abs(mine[u]["t"] - float(B[u]["m_t"])) > 1e-6]
print("differences: pass", len(dp), "member", len(dm), "share", len(ds), "median", len(dmed), "central t", len(dt_))
def root_of(uid): return meta[uid.split("|")[0]]["root"]
def kind(uid): return "stage_d" if meta[uid.split("|")[0]]["base"] else "base"
cnt = collections.Counter((root_of(u), kind(u)) for u in mine); pas = collections.Counter((root_of(u), kind(u)) for u in mine if mine[u]["pass"])
print("judged by root/kind", dict(cnt)); print("plateau pass by root/kind", dict(pas), "total", sum(pas.values()))
# --- null bars
nul = [n for s in runs for n in s["nulls"]]
bars = {}
for g in sorted({n["group"] for n in nul}):
    b = [n["best_t"] for n in nul if n["group"] == g]
    bars[g] = float(np.percentile(b, 95))
    pp = [n for n in nul if n["group"] == g and n["pass"]]
    both = [n for n in pp if (n["t"] or 0) > bars[g]]
    print(f"null {g}: reps {len(b)} bar95 {bars[g]:.4f} plateau-pass {len(pp)} pass-and-central-t>bar {len(both)}")
AB = json.loads((W/"out/admit/null_bars.json").read_text())
print("bar diffs vs analyst", {g: round(bars[g]-AB[g]["bar"], 6) for g in bars})
# --- gates
cand = []
for u, p in mine.items():
    if not p["pass"]: continue
    m = meta[u.split("|")[0]]
    fam = m["base"] or m["family"]
    timed = fam.startswith("straddle_t_")
    l2 = bool(m["base"]) or (m["key"] + "-c2s1") in meta
    bar = bars[("shift-" if timed else "c1-") + m["root"]]
    t = p["t"] or 0.0
    ok = t > bar and (not l2 or t > bars["c2-stage_d" if m["base"] else "c2-l2"]) and (not m["weak"] or t >= 3.0)
    if t > bar: cand.append((u, round(t, 3), round(bar, 3), m["weak"], l2, ok, B[u]["build_pass"], B[u]["fail"], B[u].get("ctrl_lift"), B[u].get("ctrl_p_beat")))
print("plateau passers whose central t > C1/shift bar:", len(cand))
for c in sorted(cand, key=lambda x: -x[1]): print("  ", c)
print("analyst build_pass:", [u for u in B if B[u]["build_pass"] == "True"])
near = sorted(((u, mine[u]["t"] or 0, bars[("shift-" if (meta[u.split('|')[0]]["base"] or meta[u.split('|')[0]]["family"]).startswith("straddle_t_") else "c1-") + root_of(u)]) for u in mine if mine[u]["pass"]), key=lambda x: x[2]-x[1])
print("closest below bar:", [(u, round(t,3), round(b,3)) for u, t, b in near if t <= b][:6])
# --- family / session table spot checks
fam_tab = collections.defaultdict(lambda: [0,0,0,0])
for u, p in mine.items():
    m = meta[u.split("|")[0]]
    if m["base"]: continue
    f = "straddle_t" if m["family"].startswith("straddle_t_") else m["family"]
    k = (f, m["root"]); fam_tab[k][3] += 1
    if p["median"] is not None and p["median"] > 0:
        for i, th in enumerate((0.6, 0.7, 0.8)):
            fam_tab[k][i] += p["share"] >= th - 1e-12
for k in sorted(fam_tab): print("  fam", k, fam_tab[k])
st = {}
for u, p in mine.items():
    m = meta[u.split("|")[0]]
    if m["family"].startswith("straddle_t_") and not m["base"]:
        st[(m["family"][-4:], m["root"])] = (p["cells"], round(100*p["share"]), round(p["median"]), p["pass"], round(p["t"] or 0, 2), u.split("|")[1])
for k in sorted(st): print("  straddle", k, st[k])
sess_tab = collections.defaultdict(lambda: [0,0,0,0])
for u, p in mine.items():
    m = meta[u.split("|")[0]]
    if m["base"]: continue
    k = (u.split("|")[1], m["root"]); sess_tab[k][3] += 1
    if p["median"] is not None and p["median"] > 0:
        for i, th in enumerate((0.6, 0.7, 0.8)): sess_tab[k][i] += p["share"] >= th - 1e-12
for k in sorted(sess_tab): print("  sess", k, sess_tab[k])
json.dump({"bars": bars}, open(W/"out/check_admit/bars.json", "w"))
