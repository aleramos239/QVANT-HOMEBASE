"""By year, then combined: the house metric set (library.per_year, decision 7) for every cell of one manual-lane store.

    <venv-python> manual_lane/by_year.py STORE_DIR OUT.html [--title T] [--risk USD] [--cells ID,ID] [--root NQ] [--prop [ACCOUNT]]

STORE_DIR = a unit folder `bp.py build ... --out=<scratch>` wrote (it holds run.json and cells.npz). --risk USD sizes every trade to about that
risk in micros (library.sized: micros = max(1, round(risk / (stop points x $0.50))), net of the micro commission); without it one contract.
--cells = cell ids to show, in that order (default: all). --prop = also the prop sim of each cell (blueprint.pipe_prop.odds: the pipeline's
account unless one is named, its days and bars; the plain row on the 1-contract trades at each size step, open losses counted, the "live is worse"
row as a stress line). Years come from the TRADE date, a part year is starred (build days start 2021-09-22 and end
2025-06-30). One page: the combined table of every cell, the net by year of every cell, then each cell's full metric set per year.
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "engine")]

import library as LB  # noqa: E402

COLS = [("trades", "Trades", "{:,.0f}"), ("net", "Net $", "{:,.0f}"), ("avg_trade", "Avg $", "{:,.0f}"), ("win", "Win %", "pct"),
        ("pf", "PF", "{:.2f}"), ("max_dd", "Max DD $", "{:,.0f}"), ("sharpe", "Sharpe", "{:.2f}"), ("worst_open_loss", "Worst open loss $", "{:,.0f}")]


def fmt(v, f):
    if v is None:
        return "n/a"
    if f == "pct":
        return f"{100.0 * float(v):.1f}"
    return f.format(v)


def label(c) -> str:
    v = ", ".join(f"{k} {x}" for k, x in c["variant"].items()) or "base"
    e = c["exit"]
    t = "no target" if not e["tgt_r"] else f"{e['tgt_r']:g}R target"
    return f"{v} · {e['stop_mode']} {e['stop_val']:g} · {t}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("store")
    ap.add_argument("out")
    ap.add_argument("--title", default="By year, then combined")
    ap.add_argument("--risk", type=float, default=None, help="size every trade to about this many dollars of risk (micros)")
    ap.add_argument("--cells", default=None)
    ap.add_argument("--root", default="NQ")
    ap.add_argument("--prop", nargs="?", const="", default=None, metavar="ACCOUNT", help="add the prop sim (default account: pipeline.json prop.account)")
    a = ap.parse_args(argv)
    p = Path(a.store)
    u = LB.load_unit(p.name, p.parent)
    import l2sim                                                  # the blueprint's build days 2021-09-22 .. 2025-06-30 (its own seal switch)
    cal = [d.isoformat() for d in l2sim.sessions(*l2sim.period("bp_build"), a.root, allow_holdout=l2sim.ALLOW_BP)]
    order = a.cells.split(",") if a.cells else None
    PP = None
    if a.prop is not None:
        from blueprint import pipe_prop as PP                     # noqa: PLC0415 (the prop sim is read only when asked for)
    rows, props = [], []
    for i, c in enumerate(u["meta"]["cells"]):
        if order and c["id"] not in order:
            continue
        x = LB.unit_cell(u, i)
        if not len(x["net"]):
            continue
        pr = PP.odds(x, cal, a.prop or None) if PP else None       # the prop sim reads the 1-contract trades: it sizes them itself, by micros
        cm = LB.COMM_RT
        if a.risk:
            x = LB.sized(x, a.root, a.risk)
            cm = x["cost"]
        rows.append((c, LB.per_year(x, cal, cm)))
        props.append(pr)
    if order:
        k = {cid: n for n, cid in enumerate(order)}
        both = sorted(zip(rows, props), key=lambda t: k[t[0][0]["id"]])
        rows, props = [t[0] for t in both], [t[1] for t in both]
    if not rows:
        print("no cell with trades")
        return 1
    years = [r["period"] for r in rows[0][1][:-1]]
    sizing = f"sized to about ${a.risk:,.0f} of risk a trade (micros)" if a.risk else "1 NQ contract"
    PCOLS = ["Eval odds, plain", "Payout odds, plain", "Eval odds, stress", "Eval size"]
    top = ("<table><tr><th>Cell</th>" + "".join(f"<th>{h}</th>" for _, h, _ in COLS) +
           ("".join(f"<th>{h}</th>" for h in PCOLS) if PP else "") + "</tr>")
    yrs = "<table><tr><th>Cell</th>" + "".join(f"<th>{y}</th>" for y in years) + "<th>Combined</th></tr>"
    body = ""
    for n, (c, per) in enumerate(rows):
        comb = per[-1]
        top += f'<tr><td><a href="#c{n}">{html.escape(label(c))}</a></td>' + "".join(
            f'<td class="{"neg" if k in ("net", "avg_trade") and (comb[k] or 0) < 0 else ""}">{fmt(comb[k], f)}</td>' for k, _, f in COLS)
        if PP:
            pr = props[n]
            top += "".join(f"<td>{v}</td>" for v in (f"{100 * pr['eval']:.1f} %", f"{100 * pr['payout']:.1f} %",
                                                      f"{100 * pr['stress']['eval']:.1f} %", f"{pr['size']} micros" if pr["size"] else "n/a"))
        top += "</tr>"
        yrs += f"<tr><td>{html.escape(label(c))}</td>" + "".join(
            f'<td class="{"neg" if (r["net"] or 0) < 0 else ""}">{fmt(r["net"], "{:,.0f}")}</td>' for r in per) + "</tr>"
        t = f'<h2 id="c{n}">{html.escape(label(c))}</h2><table><tr><th>Year</th>' + "".join(f"<th>{h}</th>" for _, h, _ in COLS) + "</tr>"
        for r in per:
            t += f'<tr{" class=all" if r["period"] == "combined" else ""}><td>{r["period"]}</td>' + "".join(
                f'<td class="{"neg" if k in ("net", "avg_trade") and (r[k] or 0) < 0 else ""}">{fmt(r[k], f)}</td>' for k, _, f in COLS) + "</tr>"
        body += t + "</table>"
        if PP:
            pr = props[n]
            body += (f"<p class=note>{html.escape(pr['text'])}</p><table><tr><th>Micros</th><th>Eval, plain</th><th>Payout, plain</th><th>Eval, stress</th>"
                     "<th>Payout, stress</th></tr>")
            pct = lambda v: "n/a" if v is None else f"{100 * v:.1f} %"             # noqa: E731 (a funded step above the scaling start has no payout)
            for r, sr in zip(pr["table"], pr["stress"]["table"]):
                body += (f"<tr><td>{r['size']}</td><td>{pct(r['eval'])}</td><td>{pct(r['payout'])}</td>"
                         f"<td>{pct(sr['eval'])}</td><td>{pct(sr['payout'])}</td></tr>")
            body += "</table>"
    css = ("body{font:14px -apple-system,Helvetica,sans-serif;margin:24px;color:#1d1d1f;background:#fff}"
           "@media(prefers-color-scheme:dark){body{background:#161618;color:#e8e8ea}th{background:#2a2a2d}tr.all td{background:#242427}}"
           "h1{font-size:20px}h2{font-size:15px;margin:28px 0 8px}table{border-collapse:collapse;margin-bottom:8px;font-variant-numeric:tabular-nums}"
           "th,td{padding:5px 9px;border-bottom:1px solid #8884;text-align:right;white-space:nowrap}th{background:#f0f0f2;font-weight:600}"
           "td:first-child,th:first-child{text-align:left}tr.all td{font-weight:600;background:#f7f7f9}.neg{color:#c0392b}a{color:inherit}.note{max-width:900px;line-height:1.4}")
    prop_note = ("<p class=note>Prop sim: LucidPro 50K, no daily loss limit; eval = pass within 30 trading days, payout = the maximum payout within 30 days, "
                 "each at its best size of micros, open losses counted. Plain = the build days' own trades; stress = the \"live is worse\" row "
                 "(a label, not a gate). The pipeline's bar: 40 % eval odds.</p>") if PP else ""
    page = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(a.title)}</title><style>{css}</style></head><body><h1>{html.escape(a.title)}</h1>"
            f"<p>{html.escape(u['meta'].get('idea', p.name))} &middot; {sizing} &middot; build days 2021-09-22 to 2025-06-30 &middot; costs as the engine books them. "
            f"Test days not read.</p>{prop_note}<h2>Combined</h2>{top}</table><h2>Net $ by year</h2>{yrs}</table>{body}</body></html>")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page)
    print(f"ok: {len(rows)} cells, {len(page):,} bytes -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
