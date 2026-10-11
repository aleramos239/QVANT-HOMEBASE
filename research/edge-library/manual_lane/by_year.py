"""By year, then combined: the house metric set (library.per_year, decision 7) for every cell of one manual-lane store.

    <venv-python> manual_lane/by_year.py STORE_DIR OUT.html [--title T] [--risk USD] [--cells ID,ID] [--root NQ]

STORE_DIR = a unit folder `bp.py build ... --out=<scratch>` wrote (it holds run.json and cells.npz). --risk USD sizes every trade to about that
risk in micros (library.sized: micros = max(1, round(risk / (stop points x $0.50))), net of the micro commission); without it one contract.
--cells = cell ids to show (default: all). Years come from the TRADE date, a part year is starred (build days start 2021-09-22 and end
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
    a = ap.parse_args(argv)
    p = Path(a.store)
    u = LB.load_unit(p.name, p.parent)
    import l2sim                                                  # the blueprint's build days 2021-09-22 .. 2025-06-30 (its own seal switch)
    cal = [d.isoformat() for d in l2sim.sessions(*l2sim.period("bp_build"), a.root, allow_holdout=l2sim.ALLOW_BP)]
    want = set(a.cells.split(",")) if a.cells else None
    rows = []
    for i, c in enumerate(u["meta"]["cells"]):
        if want and c["id"] not in want:
            continue
        x = LB.unit_cell(u, i)
        if not len(x["net"]):
            continue
        cm = LB.COMM_RT
        if a.risk:
            x = LB.sized(x, a.root, a.risk)
            cm = x["cost"]
        rows.append((c, LB.per_year(x, cal, cm)))
    if not rows:
        print("no cell with trades")
        return 1
    years = [r["period"] for r in rows[0][1][:-1]]
    sizing = f"sized to about ${a.risk:,.0f} of risk a trade (micros)" if a.risk else "1 NQ contract"
    top = "<table><tr><th>Cell</th>" + "".join(f"<th>{h}</th>" for _, h, _ in COLS) + "</tr>"
    yrs = "<table><tr><th>Cell</th>" + "".join(f"<th>{y}</th>" for y in years) + "<th>Combined</th></tr>"
    body = ""
    for n, (c, per) in enumerate(rows):
        comb = per[-1]
        top += f'<tr><td><a href="#c{n}">{html.escape(label(c))}</a></td>' + "".join(
            f'<td class="{"neg" if k in ("net", "avg_trade") and (comb[k] or 0) < 0 else ""}">{fmt(comb[k], f)}</td>' for k, _, f in COLS) + "</tr>"
        yrs += f"<tr><td>{html.escape(label(c))}</td>" + "".join(
            f'<td class="{"neg" if (r["net"] or 0) < 0 else ""}">{fmt(r["net"], "{:,.0f}")}</td>' for r in per) + "</tr>"
        t = f'<h2 id="c{n}">{html.escape(label(c))}</h2><table><tr><th>Year</th>' + "".join(f"<th>{h}</th>" for _, h, _ in COLS) + "</tr>"
        for r in per:
            t += f'<tr{" class=all" if r["period"] == "combined" else ""}><td>{r["period"]}</td>' + "".join(
                f'<td class="{"neg" if k in ("net", "avg_trade") and (r[k] or 0) < 0 else ""}">{fmt(r[k], f)}</td>' for k, _, f in COLS) + "</tr>"
        body += t + "</table>"
    css = ("body{font:14px -apple-system,Helvetica,sans-serif;margin:24px;color:#1d1d1f;background:#fff}"
           "@media(prefers-color-scheme:dark){body{background:#161618;color:#e8e8ea}th{background:#2a2a2d}tr.all td{background:#242427}}"
           "h1{font-size:20px}h2{font-size:15px;margin:28px 0 8px}table{border-collapse:collapse;margin-bottom:8px;font-variant-numeric:tabular-nums}"
           "th,td{padding:5px 9px;border-bottom:1px solid #8884;text-align:right;white-space:nowrap}th{background:#f0f0f2;font-weight:600}"
           "td:first-child,th:first-child{text-align:left}tr.all td{font-weight:600;background:#f7f7f9}.neg{color:#c0392b}a{color:inherit}")
    page = (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(a.title)}</title><style>{css}</style></head><body><h1>{html.escape(a.title)}</h1>"
            f"<p>{html.escape(u['meta'].get('idea', p.name))} &middot; {sizing} &middot; build days 2021-09-22 to 2025-06-30 &middot; costs as the engine books them. "
            f"Test days not read.</p><h2>Combined</h2>{top}</table><h2>Net $ by year</h2>{yrs}</table>{body}</body></html>")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page)
    print(f"ok: {len(rows)} cells, {len(page):,} bytes -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
