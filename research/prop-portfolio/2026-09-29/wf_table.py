#!/usr/bin/python3
"""Tabulate the Homebase tester walk-forwards of a pilot (stage wf in jobs.jsonl) -> <pilot dir>/out/wf_summary.md (+ wf_summary.csv).
Stitched OOS = phase-0 steps (each holding its pick for its 3-month test window; windows tile the OOS months once), raw P&L at qty 1.
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 wf_table.py [--pilot es]"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import pilot as PL

STATE = PL.CODE.parents[2] / "homebase" / ".state" / "tester" / "walkforward"
OUT = PL.DIR / "out"
PV = {"NQ": 20.0, "ES": 50.0}[PL.ROOT]


def main():
    jobs = [json.loads(x) for x in (PL.DIR / "jobs.jsonl").read_text().splitlines() if x.strip()]
    rows = []
    for j in jobs:
        if j.get("kind") != "walkforward" or j.get("status") != "done":
            continue
        res = json.loads((STATE / j["id"] / "result.json").read_text())
        st, si, dr = res["stitched"]["stats"], res["stitched_is"]["stats"], res["drop"]
        ph = res["phases"]
        stab = res["stability"]
        sp = j["spec"]
        rows.append(dict(key=j["key"], family=sp["strategy"].replace("draft_pp_es_", "").replace("draft_pp_", ""), sess=sp["inputs"].get("sess"), tf=sp["inputs"].get("tf"),
                         fp="fp" if j["key"].endswith("-fp") else "", oos_net=st["net_profit"], oos_trades=st["trades"], oos_pf=st["profit_factor"], oos_sharpe=st["sharpe"],
                         oos_wr=st["win_rate"], oos_maxdd=st["max_drawdown"], oos_avg=st["avg_trade"], oos_t=st["t_stat"], is_net=si["net_profit"], is_pf=si["profit_factor"],
                         is_sharpe=si["sharpe"], drop_sharpe=dr.get("sharpe"), ph_nets=[round(p["net_profit"]) for p in ph], ph_pos=sum(p["net_profit"] > 0 for p in ph),
                         ph_sharpe=[round(p["sharpe"], 2) for p in ph], distinct=stab["distinct"], changes=stab["changes"], no_pick=stab["no_pick"], id=j["id"]))
    rows.sort(key=lambda r: -r["oos_net"])
    with (OUT / "wf_summary.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows)
    pos = [r for r in rows if r["oos_net"] > 0]
    L = [f"# {PL.ROOT} Homebase walk-forwards ({len(rows)} jobs, {dt.date.today()}): param pick on 1 month by t_stat, test next 3 months, stitched OOS (phase 0), raw P&L at 1 {PL.ROOT}",
         f"Window 2021-01..2024-12 (ticks from 2021-09-22). {len(pos)}/{len(rows)} positive OOS; costs: $4 RT/contract + 1 tick/side. 'fp' = fast-pass grid (tight stops/targets). ph = net of the 3 stitch phases (a robustness view of the same data).",
         "| WF | OOS net $ | PF | Sharpe | trades | WR% | maxDD $ | avg $/tr | t | IS net $ | IS PF | phases net $ (0/1/2) | picks distinct/changes |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['key'][3:]} | {r['oos_net']:+,.0f} | {r['oos_pf']:.2f} | {r['oos_sharpe']:.2f} | {r['oos_trades']} | {r['oos_wr']:.0f} | {r['oos_maxdd']:,.0f} | {r['oos_avg']:+.1f} | {r['oos_t']:.2f} | "
                 f"{r['is_net']:+,.0f} | {r['is_pf']:.2f} | {'/'.join(f'{x:+,}' for x in r['ph_nets'])} | {r['distinct']}/{r['changes']} |")
    L += ["", "## Read", f"- Positive OOS in phase 0 (k/3 = stitch phases positive): " + ", ".join(f"{r['key'][3:]} ({r['ph_pos']}/3 phases)" for r in pos) if pos else "- none positive",
          f"- Sum of OOS net over all {len(rows)}: {sum(r['oos_net'] for r in rows):+,.0f}; median OOS net {sorted(r['oos_net'] for r in rows)[len(rows)//2]:+,.0f}; "
          f"median OOS PF {sorted(r['oos_pf'] for r in rows)[len(rows)//2]:.2f}."]
    (OUT / "wf_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
