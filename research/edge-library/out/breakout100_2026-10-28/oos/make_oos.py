"""OOS heat maps of the 10 breakout variants: the 3:1 TEST MONTHS (15 months, 309 trading days) of the fixed-point and structure-stop boxes,
each read once (owner, 2026-10-29). Layout = heat/make.py; every cell also shows the box's in-sample avg trade and t."""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "heat"))
HERE = Path(__file__).resolve().parent; W = HERE.parents[2]
DAYS = 309; WEEKS = DAYS / 5.0
CELL = re.compile(r"^(.*)_(pts|atr|own)([\dp]+)-r([\dp]+)$")
src = (HERE.parent / "heat" / "make.py").read_text()
RULE = eval(src[src.index("RULE = ") + 7: src.index("\nnames =")])           # the window text, same as the in-sample pages
DROP = {("nq_b044_squeeze", "sq_typeinside"), ("nq_b039_pre_bracket", "r_start0800"), ("nq_b032_lon_break", "min_rng_atr2"), ("nq_b041_london_kz_bracket", "r_end0400")}   # owner 2026-10-29
KEEP_PTS = {("nq_b018_pd_bracket_on", "off_min15"), ("nq_b089_ib_break", "ib_min30")}   # fixed-stop page only, owner 2026-10-29
boxes = [b for b in json.load(open(HERE / "boxes.json")) if (b["store"], b["var"]) not in DROP]

def stats(D, cell):
    z = np.load(D / "cells.npz"); t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    i = int(t.index[t.cell == cell][0]); c = t.loc[i]; off = z["off"]; s = slice(off[i], off[i + 1]); net = z["net"][s]
    if len(net) == 0: return None
    w, l = net[net > 0], net[net <= 0]
    day = pd.Series(net, index=pd.to_datetime(z["entry_ms"][s], unit="ms").normalize()).groupby(level=0).sum()    # traded days only
    sh = float(day.mean() / day.std() * np.sqrt(252)) if len(day) > 2 and day.std() > 0 else 0.0
    e = pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York")
    em = (e.hour * 60 + e.minute).to_numpy()
    return dict(t=float(c.t), net=float(net.sum()), sharpe=sh, win=float((net > 0).mean() * 100), rr=float(w.mean() / abs(l.mean())) if len(w) and len(l) else None,
                avg=float(net.mean()), perwk=float(net.sum() / WEEKS), trwk=len(net) / WEEKS, trades=len(net), em=em, xm=em + z["dur_s"][s] / 60.0)

V = {}
for b in boxes:
    o = HERE.parents[2] / "runs_wf" / f"{b['store']}-NQ-tf5__{b['box']}" / "oos"
    if not (o / "cells.npz").exists(): print("MISSING", b["store"], b["box"]); continue
    so = stats(o, b["box"]); si = stats(W / "runs_wf" / f"{b['store']}-NQ-tf5" / "is", b["box"])
    m = CELL.match(b["box"])
    if so is None or si is None: so = so or dict(t=0, net=0, sharpe=0, win=0, rr=None, avg=0, perwk=0, trwk=0, trades=0, em=np.array([]), xm=np.array([]))
    if si is None: continue
    V.setdefault((b["store"], b["var"], b["kind"]), []).append(dict(n=b["n"], stop=m[3].replace("p", "."), tgt=m[4].replace("p", "."), **{k: v for k, v in so.items() if k not in ("em", "xm")},
        isavg=si["avg"], ist=si["t"], isnet=si["net"], iswin=si["win"], issh=si["sharpe"], _em=so["em"], _xm=so["xm"]))
rows = []
for (nm, var, kind), cs in V.items():
    em = np.concatenate([c.pop("_em") for c in cs]); xm = np.concatenate([c.pop("_xm") for c in cs])
    hm = lambda v: f"{int(v) // 60:02d}:{int(v) % 60:02d}"
    obs = f"Seen on the test months: entries from {hm(em.min())}, half by {hm(np.median(em))}, last {hm(em.max())}; half out by {hm(np.median(xm))}, 90% by {hm(np.percentile(xm, 90))}, rest flat 15:58." if len(em) else ""
    rows.append(dict(idea=nm, var=var, kind=kind, win=RULE.get((nm, var), "") + " " + obs, cells=cs, nc=len(cs), tpd=np.mean([c["trades"] for c in cs]) / DAYS,
                     t=float(np.mean([c["t"] for c in cs])), ist=float(np.mean([c["ist"] for c in cs])), green=sum(c["net"] > 0 for c in cs), isgreen=sum(c["isnet"] > 0 for c in cs),
                     net=float(np.mean([c["net"] for c in cs])), avg=float(np.mean([c["avg"] for c in cs])), isavg=float(np.mean([c["isavg"] for c in cs]))))
order = [(a, b) for a, b in [(k[0], k[1]) for k in V] if True]
html = (HERE.parent / "heat" / "top10_breakout_variants.html").read_text()
head = html[:html.index("<h1>")]
head = head.replace("in-sample", "TEST MONTHS")
def page(kind, stops, label, note, title, fn):
    sel = sorted([r for r in rows if r["kind"] == kind and (kind != "pts" or (r["idea"], r["var"]) in KEEP_PTS)], key=lambda r: -r["t"])
    tpl = (HERE.parent / "heat" / "top10_breakout_variants.html").read_text()
    # reuse the in-sample page's script, then patch the text and add the in-sample columns
    pre, post = tpl.split("<h1>", 1)
    body = "<h1>" + post
    body = re.sub(r"<h1>.*?</h1>", f"<h1>Top 6 breakout variants: {title}, 3:1 TEST MONTHS only (read once)</h1>", body, count=1, flags=re.S)
    body = re.sub(r'<div class=sub>NQ, 1 contract.*?</div>', f'<div class=sub>NQ, 1 contract, one trade a day at most, flat 15:58 ET. A variant = one idea at one value of its main setting. {note} '
        'These are the 15 out-of-sample months of the 3:1 walk-forward (2022-01 to 2026-09, 309 trading days), each box fixed and read ONCE (owner, 2026-10-29): a fail is final, no re-tune. '
        'Variants are ordered by their mean test-month t. Shade = <select id=by onchange=paint()><option value=net>net $</option><option value=sharpe>Sharpe (traded days)</option><option value=t>t-stat</option></select>, green profit, red loss. '
        'Cell: net $ (bold) · Sharpe (traded days) · win % · realised RR · avg trade $ · $ per week · trades per week · IN-SAMPLE avg trade for the same box. Top-right: the box number in that idea\'s in-sample table. Weeks = 309 / 5.</div>', body, count=1, flags=re.S)
    body = body.replace("avg ${$(c.avg)}", "avg ${$(c.avg)} (in-sample ${$(c.isavg)})")
    body = body.replace("<th>mean t<th>trades/day", "<th>mean t (test)<th>mean t (in-sample)<th>avg trade test / in-sample<th>trades/day")
    body = body.replace("<td>${f(r.t,2)}<td>${f(r.tpd,2)}", "<td>${f(r.t,2)}<td>${f(r.ist,2)}<td>${$(r.avg)} / ${$(r.isavg)}<td>${f(r.tpd,2)}")
    body = body.replace("mean t ${f(r.t,2)} ·", "mean t ${f(r.t,2)} (in-sample ${f(r.ist,2)}) ·")
    body = re.sub(r"const R=.*?;const T=", lambda m: "const R=" + json.dumps(sel) + ";const T=", body, count=1, flags=re.S)
    body = re.sub(r"S=\[.*?\],LB=.*?;\n", f"S={stops},LB={label};\n", body, count=1, flags=re.S)
    out = HERE / fn; out.write_text(re.sub(r"Top \d+ breakout", f"Top {len(sel)} breakout", pre.replace("in-sample", "TEST MONTHS") + body))
    print(out, [(r["var"], r["green"], r["nc"], round(r["t"], 2), round(r["ist"], 2)) for r in sel])
def consistent(c):        # in-sample and test months agree: Sharpe >= 0.5 in both, test avg trade between half and double the in-sample one, win % within 5 points
    return c["issh"] >= 0.5 and c["sharpe"] >= 0.5 and c["isavg"] > 0 and 0.5 <= c["avg"] / c["isavg"] <= 2 and abs(c["win"] - c["iswin"]) <= 5
def edge_ok(r, c):        # no cell touching this one (edge or corner) (stop row / target column) loses money in-sample or on the test months
    S, T = ["15", "25", "40", "60"], ["0.5", "0.75", "1", "1.5", "2"]
    i, j = S.index(c["stop"]), T.index(c["tgt"])
    for di in (-1, 0, 1):
      for dj in (-1, 0, 1):
        if (di, dj) == (0, 0): continue
        if 0 <= i + di < 4 and 0 <= j + dj < 5:
            n = next((x for x in r["cells"] if x["stop"] == S[i + di] and x["tgt"] == T[j + dj]), None)
            if n is None or n["isnet"] <= 0 or n["net"] <= 0: return False
    return True
OK = {f'{r["idea"]}|{r["var"]}|{c["stop"]}|{c["tgt"]}' for r in rows if r["kind"] == "pts" and (r["idea"], r["var"]) in KEEP_PTS for c in r["cells"] if consistent(c) and edge_ok(r, c)}
page("pts", '[15,25,40,60]', 's=>`stop ${s} pts`', "Rows = stop in points, columns = target in R.", "fixed-point stops", "oos_breakout_variants_fixed.html")
page("own", '["0.5","1","1.5","2"]', 's=>`stop = far side x ${s}`', "Rows = structure stop (distance to the FAR SIDE of the range / level) x 0.5 / 1 / 1.5 / 2, columns = target in R.", "structure stops", "oos_breakout_variants_structure.html")
json.dump([{k: v for k, v in r.items() if k != "cells"} for r in rows], open(HERE / "oos_variant_summary.json", "w"), indent=1)

# highlight the consistent boxes on both fixed-stop pages (outline + tick), idempotent
LEG = ("Blue outline + tick = consistent: Sharpe at least 0.5 in BOTH in-sample and test months, the test avg trade between half and double the in-sample avg trade, "
       "and the win % within 5 points; AND no neighbouring box (touching edge or corner) loses money in either period. Not a real-or-luck verdict.")
JS = ("<script>/*CONSISTENT*/const OK=new Set(" + json.dumps(sorted(OK)) + ");const _p=paint;paint=function(){_p();mark()};"
      "function mark(){document.querySelectorAll('#g table').forEach((tb,i)=>{const r=R[i];[...tb.rows].slice(1).forEach((tr,j)=>[...tr.cells].slice(1).forEach((td,k)=>{"
      "if(OK.has(r.idea+'|'+r.var+'|'+S[j]+'|'+T[k])){td.style.outline='3px solid #0a58ca';td.style.outlineOffset='-3px';td.insertAdjacentHTML('afterbegin','<b style=\"color:#0a58ca;font-size:12px\">&#10003;</b>')}}))})}"
      "document.querySelector('.sub').insertAdjacentHTML('beforeend','<br><br><b>" + LEG + " '+OK.size+' of '+R.reduce((a,r)=>a+r.cells.length,0)+' boxes on this page.</b>');mark();</script>")
for f in (HERE / "oos_breakout_variants_fixed.html", HERE.parent / "heat" / "top10_breakout_variants.html"):
    t = re.sub(r"<script>/\*CONSISTENT\*/.*?</script>", "", f.read_text(), flags=re.S); f.write_text(t + JS)
print(len(OK), "consistent boxes"); [print(" ", k) for k in sorted(OK)]
