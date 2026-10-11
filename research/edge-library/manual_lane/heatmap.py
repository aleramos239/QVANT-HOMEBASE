"""A stop x target heat map for every variant of one or more manual-lane stores, on one colour scale.

    <venv-python> manual_lane/heatmap.py OUT.html STORE_DIR [STORE_DIR ...] [--title T] [--risk USD] [--root NQ]

One card per variant of each store (the first store is usually the no-filter baseline, so every card is read against it). Rows are stops,
columns are targets (a multiple of the stop; the last one is no target). A cell shows the metric you pick above the grid (Net $, Average trade $,
Win %); colour is the box's net profit on ONE scale for the whole page (--shade net, the default; --shade metric scales to the shown number); hover a cell for its trades, long / short split and exit mix. --risk USD sizes every
trade to about that risk in micros (library.sized), otherwise one contract. A card's header says how many of its cells are profitable.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "engine")]

import library as LB  # noqa: E402

REASON = {0: "stop", 1: "target", 2: "flat at end of day"}
METRICS = [("net", "Net $", lambda c: c["net"], lambda v: f"{v:,.0f}", 0.0),
           ("avg", "Average trade $", lambda c: c["avg"], lambda v: f"{v:,.0f}", 0.0),
           ("win", "Win rate %", lambda c: c["win"], lambda v: f"{v:.0f}%", 50.0)]


def stop_label(e) -> str:
    m, v = e["stop_mode"], e["stop_val"]
    return {"atr": f"{v:g}x ATR", "pts": f"{v:g} pts", "pct": f"{v:g}%", "struct": "far side of the structure",
            "rng": f"{v:g} x range"}.get(m, f"{m} {v:g}")


def tgt_label(t) -> str:
    return "no target" if not t else f"{t:g}R"


def read(path: Path, risk, root):
    u = LB.load_unit(path.name, path.parent)
    out = []
    for i, c in enumerate(u["meta"]["cells"]):
        x = LB.unit_cell(u, i)
        if risk:
            x = LB.sized(x, root, risk)
        n, s, q = np.asarray(x["net"], float), np.asarray(x["side"]), np.asarray(x["reason"])
        d = dict(variant=json.dumps(c["variant"], sort_keys=True), vlabel=", ".join(f"{k} {v}" for k, v in c["variant"].items()) or "base",
                 stop=(c["exit"]["stop_mode"], c["exit"]["stop_val"]), tgt=c["exit"]["tgt_r"], exit=c["exit"], trades=len(n))
        d.update(net=float(n.sum()) if len(n) else 0.0, avg=float(n.mean()) if len(n) else 0.0, win=float((n > 0).mean() * 100) if len(n) else 0.0,
                 long=float(n[s > 0].sum()), short=float(n[s < 0].sum()), nl=int((s > 0).sum()), ns=int((s < 0).sum()),
                 mix={REASON.get(k, str(k)): int((q == k).sum()) for k in np.unique(q)} if len(n) else {})
        out.append(d)
    return u["meta"].get("idea", path.name), out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("stores", nargs="+")
    ap.add_argument("--title", default="Stop x target heat map")
    ap.add_argument("--risk", type=float, default=None)
    ap.add_argument("--root", default="NQ")
    ap.add_argument("--shade", choices=("net", "metric"), default="net",
                    help="net = colour is the box's net profit on one scale for the whole page (default); metric = the shown number's own scale")
    a = ap.parse_args(argv)
    groups = []                                                   # [(store idea, variant label, {(stop, tgt): cell})]
    for s in a.stores:
        idea, cells = read(Path(s), a.risk, a.root)
        for v in dict.fromkeys(c["variant"] for c in cells):
            cs = [c for c in cells if c["variant"] == v]
            groups.append((idea, cs[0]["vlabel"], {(c["stop"], c["tgt"]): c for c in cs}))
    stops = list(dict.fromkeys(k[0] for _, _, g in groups for k in g))
    tgts = sorted({k[1] for _, _, g in groups for k in g}, key=lambda t: (t == 0, t))
    allc = [c for _, _, g in groups for c in g.values()]
    radios = "".join(f'<input type="radio" name="m" id="m-{mk}" class="mr"{" checked" if mk == "net" else ""}>' for mk, *_ in METRICS)
    css_m = "".join(f"#m-{mk}:checked ~ .bar label[for=m-{mk}]{{background:var(--ink);color:var(--bg);border-color:var(--ink)}}"
                    f"#m-{mk}:checked ~ .sets .set-{mk}{{display:block}}" for mk, *_ in METRICS)
    labels = "".join(f'<label for="m-{mk}">{n}</label>' for mk, n, *_ in METRICS)
    sets = ""
    for mk, mname, get, fmt, centre in METRICS:
        sets += f'<div class="set set-{mk}">{_cards(groups, stops, tgts, allc, get, fmt, centre, a)}</div>'
    sizing = f"sized to about ${a.risk:,.0f} of risk a trade (micros)" if a.risk else "1 contract"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(a.title)}</title><style>
:root{{--bg:#f6f5f2;--panel:#fff;--ink:#1c1c1a;--mute:#6b6a64;--line:#dcdad2;--pos:#1f8a4c;--neg:#c23b30}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#141413;--panel:#1d1d1b;--ink:#ecebe5;--mute:#a09f97;--line:#34332f;--pos:#46c07a;--neg:#ec6a5d}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;padding:24px 16px 48px}}
.wrap{{max-width:1180px;margin:0 auto}}h1{{font-size:22px;margin:0 0 4px;font-weight:650}}.sub{{color:var(--mute);margin:0 0 14px}}
.mr{{position:absolute;opacity:0;pointer-events:none}}.bar{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}}
.bar label{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer}}
.set{{display:none}}{css_m}
.grids{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 14px 12px}}
.card h2{{font-size:15px;margin:0 0 2px;font-weight:650}}.meta{{color:var(--mute);font-size:13px;margin:0 0 10px}}
table{{border-collapse:separate;border-spacing:3px;width:100%;table-layout:fixed}}th{{font-weight:550;font-size:12px;color:var(--mute);text-align:center;padding:2px 0}}
th.rl{{text-align:right;padding-right:6px;width:96px;white-space:nowrap}}td{{height:36px;border-radius:6px;text-align:center;font-variant-numeric:tabular-nums;font-size:12px}}
.note{{color:var(--mute);font-size:13px;margin:14px 0 0}}
</style></head><body><div class="wrap"><h1>{html.escape(a.title)}</h1>
<p class="sub">{sizing} &middot; build days 2021-09-22 to 2025-06-30 &middot; costs as the engine books them &middot; test days not read</p>
{radios}<div class="bar">{labels}</div><div class="sets">{sets}</div>
<p class="note">Rows are stops, columns are targets as a multiple of the stop. Colour is the box's net profit on one scale for the page (green makes money, red loses). Hover a cell for its full numbers.</p>
</div></body></html>"""
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(page)
    print(f"ok: {len(groups)} variants, {len(allc)} cells -> {a.out}")
    return 0


def _cards(groups, stops, tgts, allc, get, fmt, centre, a) -> str:
    by_net = a.shade == "net"
    if by_net:                                   # colour = the box's net profit, ONE scale for every grid, whatever number is shown
        get_c, centre_c = (lambda c: c["net"]), 0.0
    else:
        get_c, centre_c = get, centre
    mx = max((abs(get_c(c) - centre_c) for c in allc if c["trades"]), default=1.0) or 1.0
    cards = ""
    for idea, vlabel, g in groups:
        rows = ""
        for st in stops:
            tds = ""
            for t in tgts:
                c = g.get((st, t))
                if c is None or not c["trades"]:
                    tds += "<td>-</td>"
                    continue
                v = get(c)
                sv = get_c(c)
                pct = min(1.0, abs(sv - centre_c) / mx) * 75
                col = "var(--pos)" if sv >= centre_c else "var(--neg)"
                tip = (f"{idea} {vlabel}, {stop_label(c['exit'])}, {tgt_label(t)}: net ${c['net']:,.0f}, {c['trades']} trades, avg ${c['avg']:,.0f}, "
                       f"wins {c['win']:.0f}%, long ${c['long']:,.0f} ({c['nl']}), short ${c['short']:,.0f} ({c['ns']}); exits "
                       + ", ".join(f"{n} {k}" for k, n in c["mix"].items()))
                tds += f'<td style="background:color-mix(in srgb,{col} {pct:.0f}%,var(--panel))" title="{html.escape(tip)}">{fmt(v)}</td>'
            rows += f'<tr><th class="rl">{html.escape(stop_label(dict(stop_mode=st[0], stop_val=st[1])))}</th>{tds}</tr>'
        cs = [c for c in g.values() if c["trades"]]
        prof = sum(c["net"] > 0 for c in cs)
        tr = sum(c["trades"] for c in cs) / max(1, len(cs))
        head = "".join(f"<th>{tgt_label(t)}</th>" for t in tgts)
        cards += (f'<section class="card"><h2>{html.escape(vlabel)}</h2><p class="meta">{html.escape(idea)} &middot; {prof} of {len(g)} cells '
                  f"profitable &middot; about {tr:,.0f} trades a cell</p><table><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table></section>")
    return f'<div class="grids">{cards}</div>'


if __name__ == "__main__":
    raise SystemExit(main())
