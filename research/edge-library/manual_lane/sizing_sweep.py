"""Sizing sweep: the prop sim of every cell of one manual-lane store at EVERY micro size, one page.

    <venv-python> manual_lane/sizing_sweep.py STORE_DIR OUT.html [--title T] [--cells ID,ID] [--account RULE_FILE] [--days N] [--root NQ]

For each cell, each size of 1 .. the account's maximum in micros (every trade at that size, the library's micro cost model), the plain row
(the build days' own trades) and the stress row ("live is worse"), open losses counted, the account's soft daily limit applied:
  eval  = the share of Monte Carlo paths that PASS on or before day k (k = 5, 10, 15, 20, N), bust = a bust on or before day N
  payout = the maximum payout of a funded account on or before day N, at the sizes the scaling plan starts at (an eval size above it has none)
Account / N default to pipeline.json prop.account / prop.days (the pipeline's own); the walks are blueprint.propodds'. Nothing is run on the test days.
It reads the same arrays as by_year.py and blueprint.pipe_prop, so the best size here is the one of pipe_prop.odds' table, on a finer grid
(propodds.steps is 1,2,3,5,7,10,15,20,30,40 -- a pre-set list; this page walks every whole micro, to show the curve).
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "engine")]

import library as LB  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from by_year import label  # noqa: E402  (same folder)

KS = (5, 10, 15, 20)                     # the days a pass is counted at, besides N


def sweep(x: dict, r: dict, cal: list, N: int, paths: int, seed: int) -> list:
    """[{size, eval: {k: p}, bust, payout | None, stress: {k: p}}] for every whole micro 1 .. the account's maximum."""
    cap, start = int(r.get("cap_micros") or 40), int((r.get("scaling_micros") or {}).get("start") or 0) or int(r.get("cap_micros") or 40)
    de = min(N, int(r.get("max_days") or N))
    idx = PO.draws(len(cal), paths, max(N, PO.horizon(r)), seed)[:, :N]
    ks = [k for k in KS if k < N] + [N]
    out = []
    for size in range(1, cap + 1):
        net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
        wnet, wopn = PO.worse(net, traded, opn)
        row = {"size": size}
        for tag, (a_, t_, o_) in (("plain", (net, traded, opn)), ("stress", (wnet, traded, wopn))):
            P, T, O = a_[idx], t_[idx], o_[idx]
            e = PO.eval_walk(P[:, :de], T[:, :de], O[:, :de], r)
            win = e["outcome"] == PO.PASS
            row[tag] = {k: float((win & (e["day"] <= k)).sum()) / paths for k in ks}
            if tag == "plain":
                row["bust"] = float(((e["outcome"] == PO.BUST) & (e["day"] <= N)).sum()) / paths
                row["payout"] = None
                if size <= start:
                    f = PO.funded_walk(P, O, r)
                    row["payout"] = float(((f["max_payout_at"] > 0) & (f["max_payout_at"] <= N)).sum()) / paths
        out.append(row)
    return out


def best(rows: list, key) -> dict:
    """The highest number; equal numbers = the smaller size (rows come smallest first)."""
    have = [v for v in rows if key(v) is not None]
    return max(have, key=lambda v: (key(v), -v["size"]))


def pc(v) -> str:
    return "n/a" if v is None else f"{100 * v:.1f}"


def shade(v, lo=0.0, hi=0.5) -> str:
    """A green wash by value (alpha only: light and dark pages both read it)."""
    a = 0 if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo))) * 0.55
    return f' style="background:rgba(52,168,83,{a:.2f})"'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("store")
    ap.add_argument("out")
    ap.add_argument("--title", default="Sizing sweep: prop sim at every size")
    ap.add_argument("--cells", default=None)
    ap.add_argument("--account", default=None)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--root", default="NQ")
    a = ap.parse_args(argv)
    need, PS = PR.need("prop"), PO.app()
    rid, N = a.account or need["account"], int(a.days or need["days"])
    r = PS.load_rules(rid)
    p = Path(a.store)
    u = LB.load_unit(p.name, p.parent)
    import l2sim
    cal = [d.isoformat() for d in l2sim.sessions(*l2sim.period("bp_build"), a.root, allow_holdout=l2sim.ALLOW_BP)]
    pv = l2sim.SPECS[a.root][0] / LB.MICRO_DIV                        # dollars a micro earns per point
    order = a.cells.split(",") if a.cells else None
    cells = [(i, c) for i, c in enumerate(u["meta"]["cells"]) if not order or c["id"] in order]
    if order:
        cells.sort(key=lambda t: order.index(t[1]["id"]))
    res = []
    for i, c in cells:
        x = LB.unit_cell(u, i)
        if not len(x["net"]):
            continue
        risk1 = float(np.nanmedian(np.asarray(x["risk"], np.float64))) * pv      # a micro's risk a trade, dollars (the stop, before slippage)
        res.append((c, risk1, sweep(x, r, cal, N, int(PS.N_PATHS), int(PS.SEED))))
    if not res:
        print("no cell with trades")
        return 1
    ks = [k for k in KS if k < N] + [N]
    # ---- the summary: each cell at its best size for the eval within N days, and for the eval within 10 days
    top = ("<table><tr><th rowspan=2>Cell</th><th colspan=5>Best size for the eval within %d days</th><th colspan=3>Best size within 10 days</th>"
           "<th colspan=2>Best payout</th></tr><tr><th>Micros</th><th>Risk a trade $</th><th>Eval %%</th><th>Bust %%</th><th>Stress eval %%</th>"
           "<th>Micros</th><th>Risk $</th><th>Eval 10 d %%</th><th>Micros</th><th>Payout %%</th></tr>") % N
    for n, (c, risk1, rows) in enumerate(res):
        b, b10, bp = best(rows, lambda v: v["plain"][N]), best(rows, lambda v: v["plain"][10] if 10 in v["plain"] else None), best(rows, lambda v: v["payout"])
        top += (f'<tr><td><a href="#c{n}">{html.escape(label(c))}</a></td><td>{b["size"]}</td><td>{b["size"] * risk1:,.0f}</td>'
                f'<td{shade(b["plain"][N])}>{pc(b["plain"][N])}</td><td>{pc(b["bust"])}</td><td>{pc(b["stress"][N])}</td>'
                f'<td>{b10["size"]}</td><td>{b10["size"] * risk1:,.0f}</td><td{shade(b10["plain"][10], 0, 0.4)}>{pc(b10["plain"][10])}</td>'
                f'<td>{bp["size"]}</td><td{shade(bp["payout"], 0, 0.3)}>{pc(bp["payout"])}</td></tr>')
    top += "</table>"
    # ---- the grid: eval odds within N days by cell x risk a trade (the nearest whole micros; over the account's maximum = blank)
    levels = [100, 200, 300, 400, 500, 600, 800, 1000, 1500]
    grid = "<table><tr><th>Cell</th>" + "".join(f"<th>${v:,}</th>" for v in levels) + "</tr>"
    for c, risk1, rows in res:
        grid += f"<tr><td>{html.escape(label(c))}</td>"
        for v in levels:
            m = int(round(v / risk1))
            if m < 1 or m > len(rows):
                grid += "<td class=na>-</td>"
            else:
                e = rows[m - 1]["plain"][N]
                grid += f'<td{shade(e)} title="{m} micros">{pc(e)}</td>'
        grid += "</tr>"
    grid += "</table>"
    body = ""
    for n, (c, risk1, rows) in enumerate(res):
        t = (f'<h2 id="c{n}">{html.escape(label(c))}</h2><p class=note>a micro risks about ${risk1:,.2f} a trade (the stop, before slippage)</p>'
             "<table><tr><th>Micros</th><th>Risk a trade $</th>" + "".join(f"<th>Eval {k} d %</th>" for k in ks) +
             f"<th>Bust {N} d %</th><th>Payout {N} d %</th><th>Stress eval {N} d %</th></tr>")
        for v in rows:
            if v["size"] not in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 20, 25, 30, 35, 40):
                continue
            t += (f'<tr><td>{v["size"]}</td><td>{v["size"] * risk1:,.0f}</td>' +
                  "".join(f"<td{shade(v['plain'][k])}>{pc(v['plain'][k])}</td>" for k in ks) +
                  f'<td>{pc(v["bust"])}</td><td>{pc(v["payout"])}</td><td>{pc(v["stress"][N])}</td></tr>')
        body += t + "</table>"
    css = ("body{font:14px -apple-system,Helvetica,sans-serif;margin:24px;color:#1d1d1f;background:#fff}"
           "@media(prefers-color-scheme:dark){body{background:#161618;color:#e8e8ea}th{background:#2a2a2d}}"
           "h1{font-size:20px}h2{font-size:15px;margin:28px 0 4px}table{border-collapse:collapse;margin-bottom:8px;font-variant-numeric:tabular-nums}"
           "th,td{padding:5px 9px;border-bottom:1px solid #8884;text-align:right;white-space:nowrap}th{background:#f0f0f2;font-weight:600}"
           "td:first-child,th:first-child{text-align:left}.note{max-width:900px;line-height:1.4;margin:4px 0 8px}.na{color:#8888}a{color:inherit}")
    page = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(a.title)}</title><style>{css}</style></head><body><h1>{html.escape(a.title)}</h1>"
            f"<p class=note>{html.escape(r.get('name', rid))} &middot; every trade at the same size, 1 to {int(r.get('cap_micros') or 40)} micros &middot; open losses count "
            f"&middot; plain = the build days' own trades (2021-09-22 to 2025-06-30), stress = the \"live is worse\" row &middot; eval = a pass on or before the "
            f"day, bust = a bust within {N} days &middot; payout = the maximum payout of a funded account within {N} days, only at sizes up to the "
            f"scaling plan's start ({int((r.get('scaling_micros') or {}).get('start') or 0)} micros). The pipeline's bar: over {100 * need['eval']:.0f} % eval odds in {N} days. "
            f"Test days not read.</p><h2>Each cell at its best size</h2>{top}"
            f"<h2>Eval odds within {N} days, by risk a trade</h2><p class=note>The size is the whole number of micros nearest the dollar risk "
            f"(hover shows it); blank = under 1 micro or over the account's maximum.</p>{grid}{body}</body></html>")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page)
    print(f"ok: {len(res)} cells, {len(page):,} bytes -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
