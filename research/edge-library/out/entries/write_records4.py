"""STAGE 4 records (BUILD only; no 2024 store exists for these units and none is read): ideas/event_entries_<market>/ (notes.md,
units.csv, heatmap.csv, per_x.csv, per_year.csv, per_type.csv), IDEAS.md lines, out/entries/pick_reads.csv (header only: no read).
  python out/entries/write_records4.py   (after judge4_build.py)"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(W / "out" / "events"))
import ev as E  # noqa: E402
import judge_build as JB  # noqa: E402
import judge4_build as J4  # noqa: E402
import library as LB  # noqa: E402

ROWS = json.loads((HERE / "build_units.json").read_text())
TYPE = {"NFP": "jobs report", "CPI": "CPI", "PPI": "PPI", "RETAIL": "retail sales", "GDP": "GDP", "PCE": "PCE", "CLAIMS": "weekly claims",
        "ISM_MFG": "ISM manufacturing", "ISM_SVC": "ISM services", "JOLTS": "JOLTS", "UMICH": "Michigan sentiment",
        "no release at this time": "no release at that time"}
OFF = {"NQ": {"A": 10, "B": 15, "C": 20, "D": 30}, "ES": {"A": 2.5, "B": 4, "C": 5, "D": 8}, "GC": {"A": 2, "B": 3, "C": 4, "D": 6}}
WHAT = {"W": "wide bracket", "D": "market order in the direction of the move"}


def usd(v) -> str:
    if v is None:
        return "n/a"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def pct(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f} %"


def plain(r: dict) -> str:
    cm = r["central"]
    if cm is None:
        return "none"
    if r["unit"] == "W":
        o, rest = cm.split("_")
        off = OFF[r["root"]][o[-1]]
        sx, tg = rest.split("-")
        mult = float(sx.replace("offx", "").replace("p", "."))
        return f"`{cm}` (bracket {off:g} pts each side, stop {off * mult:g} pts, target 1:{tg[1:]})"
    return f"`{cm}`"


def unit_line(r: dict) -> str:
    return (f"| {r['uid']} | {r['family']} · group {r['group']} | {r['trades']} | {pct(r['share_pos'])} of {r['cells']} "
            f"({'yes' if r['v60'] else 'no'} / {'yes' if r['v70'] else 'no'} / {'yes' if r['v80'] else 'no'}) | {usd(r['median_net'])} | {plain(r)} | "
            f"{usd(r['net'])} | {r['t']:.2f} / {r['bar']:.2f} | {usd(r.get('lift_mean'))} | {100 * r['e_p']:.1f} % | "
            f"{usd(r['net'])} / {usd(r['net_fast'])} / {usd(r['net_wo_fast_winners'])} | {r['median_hold_s']:.0f} s | "
            f"{'**pass**' if r['pass'] else 'fail: ' + r['failed']} |")


def year_line(r: dict) -> str:
    return " · ".join(f"{y['period']} {usd(y['net'])} ({y['trades']})" for y in r["years"]["c1"])


def write_market(root: str) -> None:
    d = W / "ideas" / f"event_entries_{root}"
    d.mkdir(parents=True, exist_ok=True)
    rows = [r for r in ROWS if r["root"] == root]
    with (d / "units.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, J4.FLAT, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with (d / "per_x.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, J4.XCOLS)
        w.writeheader()
        for r in rows:
            w.writerows(r["per_x"])
    with (d / "per_type.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["uid", "central", "type", "trades", "net", "t", "win"])
        w.writeheader()
        for r in rows:
            w.writerows(r.get("per_type") or [])
    with (d / "per_year.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["uid", "central", "view", "period", "trades", "net", "win", "pf", "max_dd", "sharpe", "avg_trade", "worst_open_loss", "t"])
        for r in rows:
            for view, k in (("1 contract", "c1"), ("about $1,000 risk", "r1000")):
                for y in (r.get("years") or {}).get(k, []):
                    w.writerow([r["uid"], r["central"], view] + [y[c] for c in ("period", "trades", "net", "win", "pf", "max_dd", "sharpe", "avg_trade", "worst_open_loss", "t")])
    with (d / "heatmap.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["uid", "period", "variant", "trades", "net", "t", "net_under_5s", "net_without_fast_winners", "median_hold_s", "dead", "central"])
        for r in rows:
            u = JB.load(r["key"])
            base = LB.plateau_units(u, r["sess"])[""]
            for t in JB.side_table(u, r["sess"], base, r["group"]):
                f = J4.fast(JB.cell(u, t["id"], r["sess"], r["group"]))
                w.writerow([r["uid"], "build", t["id"], t["trades"], t["net"], t["t"], f["net_fast"], f["net_wo_fast_winners"], f["median_hold_s"],
                            t["dead"], t["id"] == r["central"]])
    L = [f"# event entries on {root} — idea record (stage 4, 2026-10-04)", "",
         "* **Status: OPEN** · deepen rounds used: 0 of 4 · no member saved · 2024 not opened",
         "* Reason written first: a scheduled US data release reprices the market in one burst; the question is only HOW to get in without a tight two-sided bracket (which needs a fill at the stop price and can fill on both sides).",
         f"* Two entries, run on EVERY day at the clock time, judged on release days (`engine/cache/events.csv`, never checked against prices): **W** = the same two-sided bracket placed farther away ({' / '.join(f'{v:g}' for v in OFF[root].values())} points each side, stop 0.5 / 1 / 1.5 x that, target 1:1 / 1:2 / 1:3, armed 1 s before, unfilled orders cancelled after 5 min; 36 variants) · **D** = no bracket: at the release time + X (0.25, 0.5, 1, 2, 5, 15 or 60 s) ONE market order in the direction the price has moved since the last print before the release (no move = no trade); 8 stops x 4 targets = 32 exits; 224 variants.",
         "* Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims) · B = the same without claims-only days · C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).",
         "* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2025+ was never read.",
         "* A unit passes BUILD only with ALL of: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and the median positive · (c) more per trade than the same entry on days without a release at that time · (d) t at or above the unchanged random-entry bar · (e) beats 99.72 % of 4,000 random same-size day subsets · (5 s) the central variant still makes money after its WINNERS held under 5 seconds are taken out (losses kept). The central variant is the one closest to the median, never the best.",
         "", "## The six units on BUILD",
         "| unit | family · days | trades | variants positive (pass at 60 / 70 / 80 %) | median variant | central variant | its net | t / bar | more per trade than on non-release days | beats random day subsets | net / from trades under 5 s / without fast winners | median hold | BUILD |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [unit_line(r) for r in rows]
    L += ["", "Test (a) passes everywhere. Control of the run (information): the central variant against the same entry with a random direction (D) or at a random minute (W), 2 seeds, same days: "
          + " · ".join(f"{r['uid']} {usd(r['net'])} vs {usd(r['null_mean'])}" for r in rows) + ".",
          "", "## Per year, central variant (trades), 2021* = Sep-Dec only"]
    L += [f"* {r['uid']} {plain(r)}: {year_line(r)}." for r in rows]
    L += ["", "## How late can the market order go in? (D, per wait X; release days only; information, the judged unit is all 7 waits together)",
          "| unit | wait X | trades | exits positive (of 32) | median exit net | median without fast winners | per trade: release days vs days without a release | same entry with a RANDOM direction: median net (2 seeds) | exits that beat it |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        for x in r["per_x"]:
            L.append(f"| {r['uid']} | {x['x']:g} s | {x['trades']} | {pct(x['share_pos'])} | {usd(x['median_net'])} | {usd(x['median_net_wo_fast_winners'])} | "
                     f"{usd(x['median_mean_release'])} vs {usd(x['median_mean_nonrelease'])} | {usd(x['null_median_net'])} | {pct(x['beats_null_share'])} |")
    L += ["", "## What each release type did (central variant, BUILD; information only: too few trades per type)"]
    for r in rows:
        L.append(f"* {r['uid']} `{r['central']}`: " + " · ".join(f"{TYPE[p['type']]} {p['trades']} trades {usd(p['net'])}" for p in r["per_type"]) + ".")
    L += ["", "## 2024", "* No unit passed every BUILD test: 2024 was NOT opened for this market (no 2024 run exists for these families; `out/entries/pick_reads.csv` holds no row). No card, no fill probe, no late-cancel probe.",
          "", "## Left on the DONE checklist",
          "* W ran its own 3 stops x 3 targets (not the 8-stop menu, no no-target exit); only 2 control seeds; bar size does not apply (clock-time entries); deepen rounds (0 of 4 used); the table-level re-judge of EDGE_SPEC \"ADMISSION v2\" (written 11:15 ET, after this stage was briefed); verdict.",
          "", "Files here: `units.csv` (the six units with every test), `heatmap.csv` (every variant of every unit on its release days, with the 5-second columns), `per_x.csv` (D per wait), `per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv`. Scripts and raw results: `out/entries/`."]
    (d / "notes.md").write_text("\n".join(L) + "\n")


def ideas_md() -> None:
    p = W / "IDEAS.md"
    txt = p.read_text()
    if "event entries:" in txt:
        return
    lines = txt.split("\n")
    at = max(i for i, s in enumerate(lines) if s.startswith("| event straddle:"))
    new = []
    for root in E.ROOTS:
        rows = [r for r in ROWS if r["root"] == root]
        new.append(f"| event entries: wide bracket (W) and one market order in the direction of the first move (D) on scheduled-release days, 08:30 / 10:00 ET (stage 4) | {root} | OPEN | 0 of 4 | "
                   f"6 / {sum(r['b'] for r in rows)} | W ran 3 stops x 3 targets only; 2 control seeds; deepen rounds; table-level re-judge (ADMISSION v2); verdict | "
                   f"[notes](ideas/event_entries_{root}/notes.md) |")
    lines[at + 1:at + 1] = new
    txt = "\n".join(lines).replace(", 140 open, 0 shelved.", ", 143 open, 0 shelved.", 1)
    txt = txt.replace("Updated 2026-10-04 after the event-straddle round (new-idea round 2;", "Updated 2026-10-04 after the event-entry round (stage 4; event straddles = new-idea round 2;", 1)
    txt = txt.rstrip("\n") + "\nStage 4 (event entries: wide bracket, market order after the release) 2024 reads: NONE (no unit passed BUILD). Summary: `out/entries_summary.md`.\n"
    p.write_text(txt)


def main():
    for root in E.ROOTS:
        write_market(root)
    reads = HERE / "pick_reads.csv"
    if not reads.exists():
        with reads.open("w", newline="") as fh:
            csv.writer(fh).writerow(["utc", "key", "family", "root", "tf", "sess", "what", "cells", "why"])
    ideas_md()
    print("records written")


if __name__ == "__main__":
    main()
