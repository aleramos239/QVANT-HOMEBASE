"""Top-10 variants of the 100-breakouts run as one HTML of heat maps (read-only: the saved 3:1 in-sample stores, no test month).
Variant = idea x one value of its main setting. Only the fixed-point stop cells (NQ 15/25/40/60 pts) x targets 0.5-2 R.
Rank = mean t over the variant's fixed-point cells, among variants trading 0.85-1.05 times a day (one trade a day)."""
import re, json, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd

W = Path(__file__).resolve().parents[3]
PY = Path.home() / "ramos-quant-homebase/.venv-research/bin/python"
DAYS = 947                                   # in-sample trading days (the job log: "days ... of 947")
WEEKS = DAYS / 5.0
CELL = re.compile(r"^(.*)_(pts|atr|own)([\dp]+)-r([\dp]+)$")
RULE = {
 ("nq_b033_on_bracket", "r_start0100"): "Window: range 01:00-09:30 ET, entries 09:30-10:55 (NY AM session), one trade a day.",
 ("nq_b033_on_bracket", "r_start0000"): "Window: range 00:00-09:30 ET, entries 09:30-10:55 (NY AM session), one trade a day.",
 ("nq_b033_on_bracket", "r_start0300"): "Window: range 03:00-09:30 ET, entries 09:30-10:55 (NY AM session), one trade a day.",
 ("nq_b089_ib_break", "ib_min30"): "Window: range 09:30-10:00 ET, entries 10:00-10:55, one trade a day.",
 ("nq_b089_ib_break", "ib_min15"): "Window: range 09:30-09:45 ET, entries 09:45-10:55, one trade a day.",
 ("nq_b018_pd_bracket_on", "off_min15"): "Window: prior-day / overnight levels armed at 09:45 ET (15 min after the open), entries 09:45-10:55, one trade a day.",
 ("nq_b044_squeeze", "sq_typeinside"): "Window: inside-bar break, entries 09:30-10:55 ET (NY AM session), one trade a day.",
 ("nq_b039_pre_bracket", "r_start0800"): "Window: range 08:00-09:30 ET, entries 09:30-10:55 (NY AM session), one trade a day.",
 ("nq_b032_lon_break", "min_rng_atr2"): "Window: London range, entries 09:30-10:55 ET (NY AM session), one trade a day.",
 ("nq_b041_london_kz_bracket", "r_end0400"): "Window: London killzone range 02:00-04:00 ET, entries 04:00-08:20 (London session), one trade a day.",
}
names = sorted({p.name.rsplit("-NQ-tf5", 1)[0] for p in (W / "runs_wf").glob("nq_b*-NQ-tf5")})
TW = {}
V = {}                                       # (idea, variant) -> {cells}
for nm in names:
    D = W / f"runs_wf/{nm}-NQ-tf5/is/"
    if not (D / "cells.npz").exists(): continue
    wf = json.loads(subprocess.run([str(PY), str(W / "bp.py"), "wf", "show", f"{nm}-NQ-tf5", "--json"], capture_output=True, text=True, cwd=W).stdout)
    rank = {r["box"]: r["n"] for r in wf["wf"]["is"]}
    z = np.load(D / "cells.npz"); off = z["off"]
    t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    day_of = pd.to_datetime(z["entry_ms"], unit="ms").normalize()
    for i, c in t.iterrows():
        m = CELL.match(c.cell)
        if not m or c.trades == 0: continue
        s = slice(off[i], off[i + 1]); net = z["net"][s]
        w, l = net[net > 0], net[net <= 0]
        day = pd.Series(net, index=day_of[s]).groupby(level=0).sum()      # Sharpe: only the days that had a trade
        sh = float(day.mean() / day.std() * np.sqrt(252)) if len(day) > 2 and day.std() > 0 else 0.0
        e = pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York")
        em = (e.hour * 60 + e.minute).to_numpy(); xm = em + z["dur_s"][s] / 60.0
        TW.setdefault((nm, m[1], m[2]), [[], []]); TW[(nm, m[1], m[2])][0].append(em); TW[(nm, m[1], m[2])][1].append(xm)
        V.setdefault((nm, m[1], m[2]), []).append(dict(n=rank[c.cell], stop=m[3].replace("p", "."), tgt=m[4].replace("p", "."), t=float(c.t), net=float(net.sum()), sharpe=sh,
            win=float((net > 0).mean() * 100), rr=float(w.mean() / abs(l.mean())) if len(w) and len(l) else None, avg=float(net.mean()),
            perwk=float(net.sum() / WEEKS), trwk=len(net) / WEEKS, trades=len(net)))
rows = []
for (nm, var, kind), cs in V.items():
    tpd = np.mean([c["trades"] for c in cs]) / DAYS
    em, xm = (np.concatenate(a) for a in TW[(nm, var, kind)])
    hm = lambda v: f"{int(v) // 60:02d}:{int(v) % 60:02d}"
    obs = f"Seen: entries from {hm(em.min())}, half by {hm(np.median(em))}, 95% by {hm(np.percentile(em, 95))}, last {hm(em.max())}. Trades are out: half by {hm(np.median(xm))}, 90% by {hm(np.percentile(xm, 90))} (stop / target), the rest flat at 15:58."
    rows.append(dict(idea=nm, var=var, kind=kind, win=RULE.get((nm, var), "") + " " + obs, cells=cs, tpd=tpd, t=float(np.mean([c["t"] for c in cs])), green=sum(c["net"] > 0 for c in cs), nc=len(cs),
                     net=float(np.mean([c["net"] for c in cs]))))
pool = [r for r in rows if r["kind"] == "pts" and 0.85 <= r["tpd"] <= 1.05 and r["nc"] >= 20]
top = sorted(pool, key=lambda r: -r["t"])[:10]
DROP = {("nq_b044_squeeze", "sq_typeinside"), ("nq_b039_pre_bracket", "r_start0800"), ("nq_b032_lon_break", "min_rng_atr2"), ("nq_b041_london_kz_bracket", "r_end0400")}   # owner 2026-10-29: #7-#10 out
top = [r for r in top if (r["idea"], r["var"]) not in DROP]
KEEP_PTS = {("nq_b018_pd_bracket_on", "off_min15"), ("nq_b089_ib_break", "ib_min30")}
for r in top: print(f'{r["idea"]:26s} {r["var"]:18s} t {r["t"]:.2f} green {r["green"]}/{r["nc"]} net {r["net"]:,.0f} {r["tpd"]:.2f}/day')
html = """<!doctype html><meta charset=utf-8><title>Top 6 breakout variants: @KIND@, in-sample</title>
<style>
body{font:13px -apple-system,Helvetica,sans-serif;margin:20px;color:#222}h1{font-size:18px}h2{font-size:15px;margin:28px 0 4px}
table{border-collapse:collapse}th{font-weight:600;padding:4px 8px;color:#555}td{width:150px;padding:5px 7px;border:2px solid #fff;font-size:11.5px;line-height:1.35;vertical-align:top}
td b{font-size:14px;display:block}.n{float:right;color:#555;font-size:10px}.sub{color:#666;margin:4px 0 12px;max-width:1000px}select{font-size:13px}
#sum td{width:auto;font-size:12.5px;border:1px solid #ddd}#sum th{border:1px solid #ddd;background:#f4f4f4}
</style>
<h1>Top 6 breakout variants: @KIND@, 3:1 in-sample months only (no test month)</h1>
<div class=sub>NQ, 1 contract, one trade a day at most, flat 15:58 ET. A variant = one idea at one value of its main setting. @ROWSNOTE@ Same variants as the fixed-point page (ranked there by mean t of the 20 fixed-point boxes, 0.85-1.05 trades a day). This is a screen, not a pick and not a real-or-luck verdict: the numbers are the sample the boxes were found in. Shade = <select id=by onchange=paint()><option value=net>net $</option><option value=sharpe>Sharpe (traded days)</option><option value=t>t-stat</option></select>, green profit, red loss, same scale in all grids.
Cell: net $ (bold) · Sharpe (days that traded, mean/sd x sqrt 252) · win % · realised RR (avg win / avg loss) · avg trade $ · $ per week · trades per week. Top-right: the box's table number in that idea's saved table (pick by it). Weeks = 947 trading days / 5.</div>
<table id=sum></table><div id=g></div>
<script>
const R=@ROWS@;const T=["0.5","0.75","1","1.5","2"],S=@STOPS@,LB=@LABEL@;
const f=(x,d=0)=>x.toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const $=x=>(x<0?"-":"")+"$"+f(Math.abs(x));
function col(v,m){const a=Math.min(Math.abs(v)/m,1),h=v>=0?135:0;return `hsl(${h} 60% ${96-a*52}%)`}
document.getElementById("sum").innerHTML="<tr><th>#<th>idea<th>variant<th>boxes green<th>avg net per box<th>mean t<th>trades/day"+R.map((r,i)=>`<tr><td>${i+1}<td>${r.idea}<td>${r.var}<td>${r.green} of ${r.nc}<td>${$(r.net)}<td>${f(r.t,2)}<td>${f(r.tpd,2)}`).join("");
function paint(){const by=document.getElementById("by").value,m=Math.max(...R.flatMap(r=>r.cells.map(c=>Math.abs(c[by]))));let h="";
R.forEach((r,i)=>{h+=`<h2>${i+1}. ${r.idea} · ${r.var} <span style="font-weight:400;color:#666">— ${r.green} of ${r.nc} boxes green · avg ${$(r.net)} · mean t ${f(r.t,2)} · ${f(r.tpd,2)} trades/day</span></h2><div class=sub style="margin:0 0 6px">${r.win}</div><table><tr><th>`+T.map(t=>`<th>target ${t} R`).join("");
for(const s of S){h+=`<tr><th>${LB(s)}`;for(const t of T){const c=r.cells.find(c=>c.stop==s&&c.tgt==t);if(!c){h+="<td>";continue}
h+=`<td style="background:${col(c[by],m)}"><span class=n>#${c.n}</span><b>${$(c.net)}</b>Sharpe ${f(c.sharpe,2)} · win ${f(c.win)}%<br>RR ${c.rr==null?"-":f(c.rr,2)} · avg ${$(c.avg)}<br>${$(c.perwk)}/wk · ${f(c.trwk,1)} tr/wk</td>`}}h+="</table>"});
document.getElementById("g").innerHTML=h}paint();
</script>"""
for kind, stops, label, note, title, fn in (
        ("pts", '[15,25,40,60]', 's=>`stop ${s} pts`', "Rows = stop in points, columns = target in R (target = stop x R).", "fixed-point stops and targets", "top10_breakout_variants.html"),
        ("atr", '["0.5","1","1.5","2"]', 's=>`stop ATR x ${s}`', "Rows = stop in ATR(14 bars of the 5-minute chart) x 0.5 / 1 / 1.5 / 2, columns = target in R (target = stop x R). The stop is set at entry from the ATR, so its size in points varies by day.", "ATR stops, targets in R", "top10_breakout_variants_atr.html"),
        ("own", '["0.5","1","1.5","2"]', 's=>`stop = far side x ${s}`', "Rows = stop = the distance from the entry to the FAR SIDE of the range / level the idea breaks (the structure stop) x 0.5 / 1 / 1.5 / 2, columns = target in R (target = stop x R). The stop is a different size in points every day.", "structure stops (far side of the range), targets in R", "top10_breakout_variants_structure.html")):
    sel = []
    for r in top:
        if kind == "pts" and (r["idea"], r["var"]) not in KEEP_PTS: continue      # owner 2026-10-29: fixed-stop page keeps 3
        a = next((x for x in rows if (x["idea"], x["var"], x["kind"]) == (r["idea"], r["var"], kind)), None)
        if a is None: print("NO", kind, "cells for", r["idea"], r["var"]); continue
        sel.append(a)
    out = Path(__file__).with_name(fn)
    out.write_text(re.sub(r"Top \d+ breakout", f"Top {len(sel)} breakout", html).replace("@ROWS@", json.dumps(sel)).replace("@STOPS@", stops).replace("@LABEL@", label).replace("@ROWSNOTE@", note).replace("@KIND@", title))
    print(out, [(a["var"], a["green"], a["nc"], round(a["tpd"], 2)) for a in sel])
