"""One HTML heat map per hm40 in-sample table (+ index). Reads runs_wf/<idea>-NQ-tf*/is/{run.json,cells.npz}. Run from research/edge-library."""
import glob, json, os, sys, datetime as dt
import numpy as np
import library as L

L._worst_open = lambda *a, **k: 0.0           # the page shows no drawdown; skips the slow intraday pass. Sharpe = library.metrics (traded days only)

OUT = "out/daily_ideas_heatmaps_2026-10-26"
os.makedirs(OUT, exist_ok=True)
SPECS = {os.path.basename(f)[:-5]: json.load(open(f)) for f in sorted(glob.glob("/tmp/dfg/specs/*.json") + glob.glob("/tmp/dfg/specs2/*.json"))}
SESS = {"asia": (0, 10800), "london": (10800, 30300), "nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480),
        "pre": (30300, 34200), "eve": (-21600, -60)}
SESS_TXT = {"asia": "Asia (00:00-03:00 ET)", "london": "London (03:00-08:25)", "nyam": "New York morning (09:30-11:00)", "mid": "midday (11:00-13:30)",
            "pm": "afternoon (13:30-15:58)", "pre": "pre-open (08:25-09:30)", "eve": "the evening before (18:00-23:59 ET)"}


def hm(sec):
    sec %= 86400
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"


def hmin(s):                                    # "HH:MM" -> seconds
    return int(s[:2]) * 3600 + int(s[3:]) * 60


SRC = {
    "gap": "where price is versus yesterday's 16:00 close (above = long, below = short)",
    "smad": "yesterday's close versus the average of the last {n_d} daily closes (above = long)",
    "loc": "where yesterday closed inside its own range (top half = long, bottom half = short)",
    "ret": "the price move from {a_start} to {a_end} ET (up = long, down = short)",
    "open": "price now versus the {a_start} open (above = long)",
    "vwap": "price now versus the day's VWAP (above = long)",
    "pret": "yesterday's price move from {a_start} to {a_end} (up = long)",
    "rexp": "yesterday's close-to-close move, kept as is when yesterday's range was wider than its {n_d}-day average and flipped when it was narrower",
    "gapagree": "the {a_start}-{a_end} move, only on days when it points the same way as the overnight gap (otherwise no trade)",
    "vol5": "the {a_start}-{a_end} move, kept as is when its volume is at least the 14-day average of that same window and flipped when it is quieter",
    "delta": "net buyer-minus-seller volume from {a_start} to {a_end} (more buying = long)",
    "vslope": "whether the VWAP rose or fell between {a_end} and the entry (rising = long)",
}


def explain(name, sp):
    c, r = sp["card"], sp["run"]
    fam, P, F, lim = r["family"], r["params"], r.get("fixed") or {}, r.get("limits") or {}
    sess, bar = c["home"]["session"], c["home"]["bar"]
    flat = F.get("w_flat") or "15:58"
    mx = lim.get("max_tr", 1)
    start = SESS[sess][0]
    if fam == "win_dir":
        d = {"a_start": "09:30", "a_end": "10:00", "n_d": 5, **{k: v for k, v in F.items()}}
        main = c["main_setting"]
        if main in ("a_start", "a_end", "n_d"):
            d[main] = "/".join(str(x) for x in P[main])
        src = SRC[F["src"]].format(**d)
        if "off_min" in P:
            t = " / ".join(hm(start + o * 60) for o in P["off_min"])
            when = f"at {t} ET (three entry times tried)"
        else:
            when = f"at {hm(start + int(F.get('off_min', 0)) * 60)} ET"
        way = "It trades the way that points." if F["mode"] == "follow" else "It trades AGAINST what that points to (a fade)."
        return (f"Once a day, {when}, it buys or sells at market with {bar}-minute bars. The side comes from {src}. {way} "
                f"No signal (flat, or data missing) = no trade. It then holds until the stop, the target, or {flat} ET.")
    if fam == "candle_sweep":
        return (f"On {bar}-minute bars during {SESS_TXT[sess]}: goes LONG when a bar closes above the previous bar's high and SHORT when it closes below "
                f"the previous bar's low, but only if the net aggressor volume (delta) of the 5 minutes before the signal points the same way and is at "
                f"least as strong as the median of that same clock window over the last 20 days. Market order at the close, filled at the next bar's open. "
                f"Up to {mx} trades a day, flat {flat}. The 'back' setting (range / body / far) is not read in this mode, so its three rows are the same boxes.")
    if fam in ("noise_band", "noise_band_eve"):
        anc = {"rth": "the 09:30 open", "globex": "the 01:00 ET open"}.get(F.get("anchor"), "the 18:00 evening open")
        return (f"Draws a band around {anc}: open +/- k x the daily ATR (k = {', '.join(str(x) for x in P['k'])}). Goes LONG when a {bar}-minute bar closes above "
                f"the upper line AND above the VWAP since that open; SHORT when it closes below the lower line AND below VWAP. Only inside {SESS_TXT[sess]}. "
                f"Up to {mx} trades a day, either side, flat {flat}.")
    if fam == "win_bracket":
        rs = F.get("r_start") or "/".join(P.get("r_start", []))
        re_ = F.get("r_end") or "/".join(P.get("r_end", []))
        return (f"Marks the high and low from {rs} to {re_} ET (the range). After it closes, a buy-stop sits just above the high and a sell-stop just below "
                f"the low; the first one hit is the day's trade, the other is cancelled. One trade a day inside {SESS_TXT[sess]}, {bar}-minute bars, flat {flat}.")
    if fam == "straddle":
        dl = int(F.get("delay_min", 0))
        return (f"At {hm(start + dl * 60)} ET it places a buy-stop above and a sell-stop below the price, each {'/'.join(str(x) for x in P['off_atr'])} x ATR away. "
                f"The first one to fill is the trade, the other is cancelled. One trade a day, {bar}-minute bars, flat {flat}.")
    if fam == "pd_bracket":
        return (f"At the start of {SESS_TXT[sess]} (+0/15/30 minutes) it places a buy-stop one tick above yesterday's high and a sell-stop one tick below yesterday's low "
                f"(a side whose level price has already passed is not armed). First one hit trades, the stop is the other level. One trade a day, flat {flat}.")
    return ""


def num(v, nd=2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def analyse(name):
    d = glob.glob(f"runs_wf/{name}-NQ-tf*/is/")
    if not d:
        return None
    d = d[0]
    run, z = json.load(open(d + "run.json")), np.load(d + "cells.npz")
    cells, off = run["cells"], z["off"]
    n = len(cells)
    date, net, side = z["date"], z["net"], z["side"]
    yr = np.array([dt.date.fromordinal(int(x)).year for x in date])
    years = sorted(set(yr.tolist()))
    rows = []
    per = {y: 0.0 for y in years}
    sd = {1: 0.0, -1: 0.0}
    for i, cl in enumerate(cells):
        a, b = int(off[i]), int(off[i + 1])
        x = {k: z[k][a:b] for k in z.files if k != "off"}
        if b == a:
            m = None
        else:
            m = L.metrics(x)
            w, lo = net[a:b][net[a:b] > 0], net[a:b][net[a:b] < 0]
            rr = float(w.mean() / -lo.mean()) if len(w) and len(lo) else None
            m = dict(tr=m["trades"], net=m["net"], sh=m["sharpe"], win=m["win"], rr=rr, pf=m["pf"], t=m["t"], avg=m["avg_trade"])
        rows.append(m)
        for y in years:
            per[y] += net[a:b][yr[a:b] == y].sum() / n
        for s in (1, -1):
            sd[s] += net[a:b][side[a:b] == s].sum() / n
    ok = [m for m in rows if m]
    cov = run.get("coverage") or {}
    used = cov.get("used") or len(run.get("days", [])) or 1
    avg = lambda k: num(np.mean([m[k] for m in ok if m[k] is not None]), 3) if ok else None   # noqa: E731
    summ = dict(boxes=n, green=sum(1 for m in ok if m["net"] > 0), pct=sum(1 for m in ok if m["net"] > 0) / n if n else 0,
                net=avg("net"), sh=avg("sh"), win=avg("win"), rr=avg("rr"), tr=avg("tr"), t=avg("t"), pf=avg("pf"),
                trday=(np.mean([m["tr"] for m in ok]) / used) if ok else 0, days=used, yrs=len([y for y in years if per[y] > 0]), ny=len(years))
    # grid
    var = []
    stops, tg = [], []
    for cl in cells:
        v = " ".join(f"{k} {vv}" for k, vv in cl["variant"].items())
        if v not in var:
            var.append(v)
        e = cl["exit"]
        sl = ("ATR x" if e["stop_mode"] == "atr" else "Own x" if e["stop_mode"] == "own" else "Fixed ") + f"{e['stop_val']:g}"
        if sl not in stops:
            stops.append(sl)
        tl = f"{e['tgt_r']:g}R"
        if tl not in tg:
            tg.append(tl)
    keys = ("tr", "net", "sh", "win", "rr", "pf", "t", "avg")
    G = {k: [[[None] * len(tg) for _ in stops] for _ in var] for k in keys}
    for cl, m in zip(cells, rows):
        v = " ".join(f"{k} {vv}" for k, vv in cl["variant"].items())
        e = cl["exit"]
        sl = ("ATR x" if e["stop_mode"] == "atr" else "Own x" if e["stop_mode"] == "own" else "Fixed ") + f"{e['stop_val']:g}"
        vi, si, ti = var.index(v), stops.index(sl), tg.index(f"{e['tgt_r']:g}R")
        for k in keys:
            G[k][vi][si][ti] = num(m[k], 4) if m else None
    return dict(weeks=round(used / 5.0, 1), name=name, var=var, stops=stops, tgts=tg, G=G, summ=summ, per={str(y): int(per[y]) for y in years}, sd={"long": int(sd[1]), "short": int(sd[-1])})


def F(v, f="%.2f", mult=1):
    return "n/a" if v is None or v != v else f % (v * mult)


def fmt_money(v):
    return "n/a" if v is None else (f"-${abs(v)/1000:.1f}k" if v < 0 else f"${v/1000:.1f}k") if abs(v) >= 1000 else f"${v:.0f}"


CSS = """body{font:14px/1.45 -apple-system,Segoe UI,Helvetica,sans-serif;margin:0;background:#0f1216;color:#e6e9ee}
.w{max-width:1100px;margin:0 auto;padding:14px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:26px 0 8px;color:#9fb0c5;text-transform:uppercase;letter-spacing:.06em}
.sub{color:#8b97a8;margin-bottom:14px}.card{overflow-x:auto;background:#171c23;border:1px solid #232b36;border-radius:10px;padding:14px 16px;margin-bottom:12px}
.kpis{display:flex;flex-wrap:wrap;gap:10px}.k{background:#171c23;border:1px solid #232b36;border-radius:10px;padding:10px 14px;min-width:120px}
.k b{display:block;font-size:19px}.k span{color:#8b97a8;font-size:12px}.pos{color:#4cc38a}.neg{color:#ef6b6b}
table{border-collapse:collapse}td,th{padding:6px 9px;text-align:center}th{color:#9fb0c5;font-weight:600;font-size:12px}
.hm td{min-width:96px;line-height:1.25;border:1px solid #0f1216;font-variant-numeric:tabular-nums;font-size:13px}.hm .n{font-size:15px;font-weight:700}.hm .m{font-size:11.5px;color:#d5dbe4;opacity:.9}.hm th.r{text-align:right;white-space:nowrap}
@media(max-width:600px){.hm td{min-width:78px;padding:4px 5px}.hm .n{font-size:13px}.hm .m{font-size:10px}h1{font-size:18px}.k{min-width:96px;padding:8px 10px}}button{background:#171c23;color:#cfd8e3;border:1px solid #2a3340;border-radius:7px;padding:6px 12px;margin:0 6px 6px 0;cursor:pointer;font-size:13px}
button.on{background:#2c5fd8;border-color:#2c5fd8;color:#fff}a{color:#7fb0ff;text-decoration:none}
.note{color:#8b97a8;font-size:12.5px}.tag{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600}
.tg{background:#12372a;color:#4cc38a}.tm{background:#3a3112;color:#e6c04c}.td{background:#3a1818;color:#ef6b6b}
.idx td,.idx th{text-align:left;border-bottom:1px solid #232b36}.idx td.n{text-align:right;font-variant-numeric:tabular-nums}tr:hover td{background:#171c23}"""

JS = """
const mon=v=>v==null?'':(Math.abs(v)>=1000?(v<0?'-':'')+'$'+(Math.abs(v)/1000).toFixed(1)+'k':'$'+Math.round(v));
function init(id,D){const root=document.getElementById(id);const net=D.G.net.flat(2).filter(x=>x!=null);const mx=Math.max(1,...net.map(Math.abs));
 const g=(k,vi,si,ti)=>D.G[k][vi][si][ti];
 let out='';
 D.var.forEach((vn,vi)=>{let h=`<div class="card"><b>${vn}</b><table class="hm"><tr><th></th>${D.tgts.map(t=>`<th>target ${t}</th>`).join('')}</tr>`;
 D.stops.forEach((s,si)=>{h+=`<tr><th class="r">stop ${s}</th>`;D.tgts.forEach((t,ti)=>{const n=g('net',vi,si,ti);
  if(n==null){h+='<td style="background:#1a2028">no trades</td>';return}
  const a=Math.min(1,Math.abs(n)/mx)*0.8,bg=n>=0?`rgba(34,170,95,${0.08+a})`:`rgba(230,70,70,${0.08+a})`;
  const sh=g('sh',vi,si,ti),rr=g('rr',vi,si,ti),tw=g('tr',vi,si,ti)/D.weeks;
  h+=`<td style="background:${bg}" title="PF ${g('pf',vi,si,ti)} | t ${g('t',vi,si,ti)} | ${g('tr',vi,si,ti)} trades"><div class=n>${mon(n)}</div><div class=m>Sharpe ${sh==null?'n/a':sh.toFixed(2)}</div><div class=m>win ${(g('win',vi,si,ti)*100).toFixed(0)}%</div><div class=m>R:R ${rr==null?'n/a':rr.toFixed(2)}</div><div class=m>${mon(g('avg',vi,si,ti))}/trade</div><div class=m>${tw.toFixed(1)} trades/wk</div></td>`});h+='</tr>'});
 out+=h+'</table></div>'});
 root.querySelector('.maps').innerHTML=out}
"""



def mon(v):
    if v is None:
        return ""
    return ("-" if v < 0 else "") + (f"${abs(v)/1000:.1f}k" if abs(v) >= 1000 else f"${abs(v):.0f}")


def maps_html(a):
    G, weeks = a["G"], a["weeks"] or 1
    net = [x for v in G["net"] for r in v for x in r if x is not None]
    mx = max([abs(x) for x in net] + [1])
    out = ""
    for vi, vn in enumerate(a["var"]):
        h = f'<div class="card"><b>{vn}</b><table class="hm"><tr><th></th>' + "".join(f"<th>target {t}</th>" for t in a["tgts"]) + "</tr>"
        for si, sl in enumerate(a["stops"]):
            h += f'<tr><th class="r">stop {sl}</th>'
            for ti, _ in enumerate(a["tgts"]):
                g = lambda k: G[k][vi][si][ti]   # noqa: E731
                n = g("net")
                if n is None:
                    h += '<td style="background:#1a2028">no trades</td>'
                    continue
                al = 0.08 + min(1.0, abs(n) / mx) * 0.8
                bg = f"rgba(34,170,95,{al:.2f})" if n >= 0 else f"rgba(230,70,70,{al:.2f})"
                sh, rr = g("sh"), g("rr")
                h += (f'<td style="background:{bg}" title="PF {g("pf")} | t {g("t")} | {g("tr")} trades"><div class=n>{mon(n)}</div>'
                      f'<div class=m>Sharpe {"n/a" if sh is None else f"{sh:.2f}"}</div><div class=m>win {g("win")*100:.0f}%</div>'
                      f'<div class=m>R:R {"n/a" if rr is None else f"{rr:.2f}"}</div><div class=m>{mon(g("avg"))}/trade</div>'
                      f'<div class=m>{g("tr")/weeks:.1f} trades/wk</div></td>')
            h += "</tr>"
        out += h + "</table></div>"
    return out


def verdict(s):
    if s["pct"] >= 0.6 and (s["net"] or 0) > 0:
        return "tg", "green on average"
    if s["pct"] >= 0.4:
        return "tm", "mixed"
    return "td", "red on average"


def page(a):
    name, s = a["name"], a["summ"]
    sp = SPECS[name]
    c = sp["card"]
    cls, vtxt = verdict(s)
    kp = lambda lab, val, cl="": f'<div class="k"><b class="{cl}">{val}</b><span>{lab}</span></div>'   # noqa: E731
    pos = lambda v: "pos" if v and v > 0 else "neg"   # noqa: E731
    yrs = "".join(f"<th>{y}</th>" for y in a["per"])
    yv = "".join(f'<td class="{pos(v)}">{fmt_money(v)}</td>' for v in a["per"].values())
    data = json.dumps({k: a[k] for k in ("var", "stops", "tgts", "G", "weeks")})
    own = any(x.startswith("Own") for x in a["stops"])
    return f"""<div id="s_{name}" class=sec>
<h1>{name} <span class="tag {cls}">{vtxt}</span></h1>
<div class=sub>NQ, {c['home']['session']} {c['home']['bar']}m, family {sp['run']['family']}. hm40 in-sample 3:1 months only (2021-10 to 2026-08). Test months NOT read. Nothing picked.</div>
<div class=card><b>What it does</b><br>{explain(name, sp)}</div>
<div class=card><b>Why it should work</b><br>{c['why']}<br><span class=note>Who loses: {c.get('loser','')} &nbsp;|&nbsp; When it should lose: {c.get('loses_when','')}</span></div>
<h2>Average of all {s['boxes']} boxes</h2><div class=kpis>
{kp('boxes green', f"{s['green']} of {s['boxes']}", 'pos' if s['pct']>=.6 else 'neg')}{kp('avg net per box', fmt_money(s['net']), pos(s['net']))}
{kp('avg Sharpe', F(s['sh']), pos(s['sh']))}{kp('avg win rate', F(s['win'],'%.0f%%',100))}
{kp('avg realized R:R', F(s['rr']))}{kp('avg trades / box', F(s['tr'],'%.0f'))}{kp('trades per day', F(s['trday']))}{kp('avg t-stat', F(s['t']), pos(s['t']))}</div>
<h2>Average box by year, and by side</h2><div class=card><table><tr>{yrs}<th>long</th><th>short</th></tr><tr>{yv}
<td class="{pos(a['sd']['long'])}">{fmt_money(a['sd']['long'])}</td><td class="{pos(a['sd']['short'])}">{fmt_money(a['sd']['short'])}</td></tr></table>
<div class=note>{s['yrs']} of {s['ny']} years green on the average box. 2021 starts 2021-10, 2026 ends 2026-08.</div></div>
<h2>Heat map</h2>
<div class=note style="margin:4px 0 10px">Rows = stop: <b>ATR x n</b> = n times the ATR of the card's own bars{'; <b>Own x n</b> = n times the idea\'s own stop (its structural stop)' if own else ''}. Columns = target in R (multiples of the stop). Each box: net, Sharpe, win rate, realized R:R, average $ per trade, trades per week. Shade = net (green profit, red loss, darker = bigger within this idea). Hover for PF, t and trade count. 1 contract, after costs.</div>
<div class=maps>{maps_html(a)}</div>
<div class=note>Sharpe = mean/sd of the daily net x sqrt(252) over days that had a trade only (house rule). Realized R:R = average winning trade / average losing trade (after costs). In-sample table: the average of all boxes is the read, never the best box. Many ideas were tried (about 140 ideas and 10,000+ boxes in all), so a good-looking average still needs the test months before it means anything.</div>
</div>"""


def wrap(body, title, back=True):
    return f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{title}</title><style>{CSS}.sec{{margin-bottom:60px;padding-bottom:30px;border-bottom:2px solid #232b36}}</style><div class=w>{body}</div>"


def index(items):
    rows = ""
    for a in sorted(items, key=lambda a: -(a["summ"]["net"] or -9e9)):
        s, sp = a["summ"], SPECS[a["name"]]
        cls, vtxt = verdict(s)
        c = sp["card"]
        rows += (f'<tr><td><a href="{a["name"]}.html">{a["name"]}</a></td><td>{c["home"]["session"]} {c["home"]["bar"]}m</td><td>{sp["run"]["family"]}</td>'
                 f'<td><span class="tag {cls}">{vtxt}</span></td><td class=n>{s["green"]}/{s["boxes"]}</td><td class="n {"pos" if (s["net"] or 0)>0 else "neg"}">{fmt_money(s["net"])}</td>'
                 f'<td class=n>{F(s["sh"])}</td><td class=n>{F(s["win"],"%.0f%%",100)}</td>'
                 f'<td class=n>{F(s["rr"])}</td><td class=n>{F(s["t"])}</td><td class=n>{s["yrs"]}/{s["ny"]}</td><td class=n>{F(s["trday"])}</td></tr>')
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>NQ daily ideas heat maps</title><style>{CSS}</style><div class=w><h1>NQ daily ideas: {len(items)} in-sample heat maps</h1>"
            f"<div class=sub>hm40, 3:1 in-sample months only, 1 contract. Every number is the AVERAGE of the idea's boxes. Test months not read; nothing picked. Click a name for its explanation and heat map.</div>"
            f"<table class=idx><tr><th>idea</th><th>window</th><th>family</th><th>verdict</th><th>green boxes</th><th>avg net</th><th>avg Sharpe</th><th>avg win</th><th>avg R:R</th><th>avg t</th><th>years green</th><th>trades/day</th></tr>{rows}</table></div>")


if __name__ == "__main__":
    items = []
    for n in SPECS:
        a = analyse(n)
        if a is None:
            print("missing", n)
            continue
        a["html"] = page(a)
        open(f"{OUT}/{n}.html", "w").write(wrap('<a href="index.html">&larr; index</a>' + a["html"], n))
        items.append(a)
    open(f"{OUT}/index.html", "w").write(index(items))
    items.sort(key=lambda a: -(a["summ"]["net"] or -9e9))
    parts, cur, size = [], [], 0
    for a in items:                                     # parts stay under 400 KB (the Browser pane opens files up to 512 KB)
        if cur and size + len(a["html"]) > 380_000:
            parts.append(cur)
            cur, size = [], 0
        cur.append(a)
        size += len(a["html"])
    parts.append(cur)
    for old in glob.glob(f"{OUT}/all*.html"):
        os.remove(old)
    pl = " | ".join(f'<a href="all_{i+1}.html">part {i+1}: {p[0]["name"][3:]} ... {p[-1]["name"][3:]}</a>' for i, p in enumerate(parts))
    for i, p in enumerate(parts):
        nav = "".join(f'<a href="#s_{a["name"]}" style="margin-right:12px;white-space:nowrap">{a["name"]}</a>' for a in p)
        open(f"{OUT}/all_{i+1}.html", "w").write(wrap(f'<h1>Heat maps, part {i+1} of {len(parts)} (best average net first)</h1><div class=sub>hm40, 3:1 in-sample months only. Test months not read, nothing picked.</div><div class=card style="line-height:2">{nav}</div><div class=note style="margin-bottom:20px">All parts: {pl}</div>' + "".join(a["html"] for a in p), f"heat maps part {i+1}"))
    print(len(parts), "parts", [len(p) for p in parts])
    print(len(items), "pages ->", OUT)

