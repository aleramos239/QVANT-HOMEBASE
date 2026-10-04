"""STAGE 2a records for the user: IDEAS.md (one line per idea = family x market, every family judged so far) and
ideas/<family>_<root>/{notes.md, sides.csv, per_year.csv, nulls.csv, heatmap.csv} for the ideas touched in this round.
Reads only what the stage already wrote (out/deepen/*.json|csv, out/admit/build_units.csv) + the BUILD stores for the heat maps."""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_sides as J  # noqa: E402
import labels as L  # noqa: E402
import library as LB  # noqa: E402

W = J.W
IDEAS = W / "ideas"
TOOLS_2A = ["daily ADX trend", "volatility regime", "news days", "long-only / short-only"]
STAGE_D = {"fbook": "book filter at the trade (skip when the 5-min book opposes)", "thin": "thin-book filter (trade only into a thin book)",
           "xbook": "book exit (leave on a book flip)"}
CLOCK = {"1800": "18:00", "2000": "20:00", "0000": "00:00", "0200": "02:00", "0300": "03:00", "0830": "08:30", "0930": "09:30",
         "1105": "11:05", "1330": "13:30"}


def money(v) -> str:
    return "n/a" if v is None or v == "" else f"${float(v):,.0f}".replace("$-", "-$")


def heat_rows(r: dict) -> list:
    u = J.load(r["key"])
    base = LB.plateau_units(u, r["sess"])[r.get("label") or ""]
    out = []
    for side in (None,) + L.SIDES:
        for t in J.side_table(u, r["sess"], base, side, r["root"]):
            out.append({"unit": r["uid"], "side": side or "all", "cell": t["id"], "dead": t["dead"], "trades": t["trades"], "net": t["net"],
                        "t": "" if t["t"] is None else round(t["t"], 3)})
    return out


def show(uid: str) -> str:
    """A unit id without the pipe characters (they would break a Markdown table)."""
    return " · ".join(x for x in uid.split("|") if x)


def idea_name(fam: str) -> str:
    if fam.startswith("straddle_t_"):
        p = fam.split("_")
        return f"straddle at {CLOCK[p[2]]} ET" + (f" + {STAGE_D[p[3]].split(' (')[0]}" if len(p) > 3 else "")
    for k, v in STAGE_D.items():
        if fam.endswith("_" + k):
            return f"{fam[:-len(k) - 1]} + {v.split(' (')[0]}"
    return fam


def main():
    units = J.units()
    sides = json.loads((HERE / "sides.json").read_text())
    by_uid = {x["uid"]: x["rows"] for x in sides}
    placebo = list(csv.DictReader((HERE / "placebo.csv").open()))
    exact = json.loads((HERE / "exact_t4.json").read_text())
    pick = json.loads((HERE / "pick_judgement.json").read_text())
    adm = json.loads((HERE / "admission.json").read_text())
    B = list(csv.DictReader((W / "out" / "admit" / "build_units.csv").open()))
    touched = defaultdict(list)
    for r in units:
        touched[(r["family"], r["root"])].append(r)
    with Pool(8) as pool:
        heat = dict(zip([r["uid"] for r in units], pool.map(heat_rows, units, chunksize=1)))
    stage_d_bases = {r["base"] for r in B if r["kind"] == "stage_d"}
    metas = {}

    def meta(fam, root):
        if (fam, root) not in metas:
            ks = sorted({r["key"] for r in B if r["family"] == fam and r["root"] == root})
            metas[(fam, root)] = json.loads((LB.RUNS / ks[0] / "run.json").read_text()) if ks else {}
        return metas[(fam, root)]

    def left(fam, root, kind, is_touched) -> str:
        m = meta(fam, root)
        rows = [r for r in B if r["family"] == fam and r["root"] == root]
        tfs = sorted({r["tf"] for r in rows}, key=int)
        items = []
        if kind == "stage_d":
            return "book shuffles beyond 2 (thin null); result so far: it lowered the median variant; counted as a tool of its base idea"
        timed = fam.startswith("straddle_t_")
        miss = [t for t in ("1", "5", "15", "30") if t not in tfs]
        if miss and not timed:
            items.append("bar sizes " + " / ".join(miss))
        nv = len(m.get("variants") or [])
        axis = m.get("mirror")
        if nv and not axis and nv < 3:
            items.append(f"main parameter at 3-4 values (has {nv})")
        tools = []
        if not is_touched:
            tools += [t for t in TOOLS_2A if not (t.startswith("long-only") and axis == "dir")]
        if root == "NQ":
            if fam not in stage_d_bases:
                tools += ["book filter at the trade", "book exit"]
            tools.append("flow+book AGREE marker")
        tools += ["RSI direction", "inverse"]
        items.append("deepen tools: " + ", ".join(tools) + ("" if root == "NQ" else " (Level 2 tools: NQ only)"))
        if not is_touched:
            items.append("per-year and $1,000-risk tables saved to ideas/")
        items.append("verdict")
        return "; ".join(items)

    # ---------------------------------------------------------------- ideas/<family>_<root>/
    IDEAS.mkdir(exist_ok=True)
    for (fam, root), rs in sorted(touched.items()):
        d = IDEAS / f"{fam}_{root}"
        d.mkdir(exist_ok=True)
        m = meta(fam, root)
        srows, yrows, nrows, hrows = [], [], [], []
        for r in rs:
            for x in by_uid[r["uid"]]:
                srows.append({k: x.get(k) for k in J.FLAT})
                for view in ("c1", "r1000"):
                    for y in (x.get("years") or {}).get(view, []):
                        yrows.append({"unit": r["uid"], "side": x["side"], "central": x["central"], "view": "1 contract" if view == "c1" else "$1,000 risk (micros)", **y})
                nrows.append({"unit": r["uid"], "side": x["side"], "central": x["central"], "t": x.get("t"), "bar_best_of_random": x.get("bar"),
                              "control_mean": x.get("ctrl_mean"), "lift_vs_control": x.get("ctrl_lift"), "beats_share_of_200_draws": x.get("ctrl_p_beat"),
                              "e_test": x.get("e_kind"), "e_beats_share_of_4000": x.get("e_p"), "e_null_mean": x.get("e_null_mean"),
                              "e_null_99p4": x.get("e_null_p994"), "days_side": x.get("days_side"), "days_universe": x.get("days_universe")})
            for p in placebo:
                if p["root"] == root and p["tf"] == str(r["tf"]) and p["sess"] == r["sess"]:
                    nrows.append({"unit": p["uid"], "side": p["side"], "central": p["central"], "t": p["t"], "bar_best_of_random": p["bar"],
                                  "lift_vs_control": p["ctrl_lift"], "beats_share_of_200_draws": p["ctrl_p_beat"], "e_test": "placebo: " + (p["e_kind"] or ""),
                                  "e_beats_share_of_4000": p["e_p"], "days_side": p["days_side"], "days_universe": p["days_universe"]})
            hrows += heat[r["uid"]]
        for name, rows in (("sides.csv", srows), ("per_year.csv", yrows), ("nulls.csv", nrows), ("heatmap.csv", hrows)):
            cols = []
            for x in rows:
                cols += [c for c in x if c not in cols]
            with (d / name).open("w", newline="") as fh:
                w = csv.DictWriter(fh, cols)
                w.writeheader()
                w.writerows(rows)
        admitted = fam == "orb" and root == "NQ"
        N = [f"# {fam} on {root} — idea record (stage 2a = deepen round 1, 2026-10-04)", "",
             f"* **Status: {'ADMITTED (member orb_NQ_tf1_pre; its other units stay open)' if admitted else 'OPEN'}** · deepen rounds used: 1 of 4"
             + (" (+ the stage-1 book filter / book exit)" if fam in stage_d_bases else ""),
             f"* Reason written first: {m.get('rationale') or 'see engine/families'}",
             "* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.",
             f"* Units touched: {len(rs)} near-misses (pass the heat map and beat matched random entries, but the central variant's t is below the best-of-random bar).",
             "", "## The units before any split",
             "| unit | variants positive | median variant | central variant | trades | net | t | bar |", "|---|---|---|---|---|---|---|---|"]
        for r in rs:
            a = by_uid[r["uid"]][0]
            N.append(f"| {show(r['uid'])} | {100 * a['share_pos']:.0f} % of {a['cells']} | {money(a['median_net'])} | `{a['central']}` | {a['trades']} | {money(a['net'])} | "
                     f"{a['t']:.2f} | {a['bar']:.2f} |")
        N += ["", "## The 8 sides (each one a filter on the unit's own stored BUILD trades)",
              "Tests: a = at least 100 trades on BUILD · b = heat map (>= 60 % of variants positive, median > 0) · c = central variant beats matched random entries "
              "restricted the same way · d = its t reaches the best-of-random bar · e = it beats 99.4 % of 4,000 random same-size day subsets (long / short: of same-side random-entry draws).",
              "| unit | side | variants positive | median | pass 60/70/80 | central variant | trades | net | t | lift vs random | (e) beats | a b c d e | result |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rs:
            for x in by_uid[r["uid"]][1:]:
                flags = " ".join("Y" if x.get(k) else "n" for k in "abcde")
                sp = "n/a" if x["share_pos"] is None else f"{100 * x['share_pos']:.0f} %"
                ep = "n/a" if x.get("e_p") is None else "%.1f %%" % (100 * x["e_p"])
                N.append(f"| {show(r['uid'])} | {x['side']} | {sp} | {money(x['median_net'])} | {'Y' if x['v60'] else 'n'}/{'Y' if x['v70'] else 'n'}/{'Y' if x['v80'] else 'n'} | "
                         f"`{x['central']}` | {x['trades']} | {money(x['net'])} | {(x['t'] or 0):.2f} | {money(x.get('ctrl_lift'))} | "
                         f"{ep} | {flags} | {'PASS on BUILD' if x['pass'] else '-'} |")
        N += ["", "Sides: " + "; ".join(f"`{s}` = {L.PLAIN[s]}" for s in L.SIDES) + ".",
              "Day splits (ADX, volatility, news) are exact: every trade date is simulated on its own and every position is flat by 15:58, so dropping a day "
              "cannot change another day's trades. Long / short splits of stored trades are APPROXIMATE (one position at a time, a cap on entries per session: "
              "without the other side the strategy could have taken trades that are not in the store); a long / short side is only trusted after an exact "
              "re-run with the family's own `dir` input.", "", "## What happened to sides that passed BUILD"]
        hit = False
        for r in rs:
            for x in by_uid[r["uid"]][1:]:
                if not x["pass"]:
                    continue
                hit = True
                k = f"{r['uid']}{x['side']}"
                if k in exact:
                    e = exact[k]
                    N.append(f"* `{show(r['uid'])}` {x['side']}: exact re-run with dir = {x['side']} on BUILD: {100 * e['share_pos']:.0f} % of variants positive, central "
                             f"`{e['central']}` {e['trades']} trades, {money(e['net'])}, t {(e['t'] or 0):.2f} (bar {e['bar']:.2f}), lift {money(e['ctrl_lift'])}"
                             + (f", beats {100 * e['e_p']:.1f} % of 4,000 draws from a 30-seed long-only random pool" if e.get("e_p") is not None else "")
                             + f" -> {'PASSES BUILD' if e.get('pass') else 'FAILS BUILD (the stored-trade split had flattered it)'}.")
                if k in pick:
                    p = pick[k]
                    N.append(f"* `{show(r['uid'])}` {x['side']}: 2024 opened (whole menu, same split): {100 * p['pick']['share_pos']:.0f} % of variants positive, median "
                             f"{money(p['pick']['median_net'])} -> the 2024 table {'PASSES' if p['pick']['pass'] else 'FAILS'}. The BUILD central variant `{p['central']}` made "
                             f"{money(p['central_pick']['net'])} in 2024 ({p['central_pick']['trades']} trades; lift over random entries {money(p['central_pick']['c1_lift'])}).")
                if k in adm and adm[k].get("name"):
                    a = adm[k]
                    N.append(f"* Admission: {a['surviving']} of {a['judged']} variants are positive in both periods and under 2 ticks + 250 ms "
                             f"(`members/_rejected/{a['name']}/surviving_set.csv`), but the BUILD central variant is not one of them. The rule-chosen replacement "
                             f"`{a['default']}` fails library.admission ({', '.join(a['by_cell'][a['default']]['failed'])}). **{'ADMITTED' if a['admit'] else 'NOT ADMITTED'}**. "
                             "Only 17 of the 84 surviving variants beat random entries with the same exits on the same days in both periods "
                             "(`out/deepen/surviving_donchian_vs_random.csv`): on quiet days the NQ morning itself paid, not the breakout.")
        if not hit and not (fam == "straddle_t_0830" and (HERE / "admission_0830.json").exists()):
            N.append("* None passed all of (a)-(e). 2024 stays unread for these units.")
        if admitted:
            ms = list(csv.DictReader((HERE / "member_orb_default_splits.csv").open()))
            mb = json.loads((HERE / "member_orb_sides.json").read_text())["rows"]
            N += ["", "## Member orb_NQ_tf1_pre — the same splits, INFORMATION ONLY (nothing here changes the member)",
                  "Default variant `or_min5_atr1p5-r2`, BUILD + 2024, 1 contract after costs (819 trades, $28,799):",
                  "| side | trades | net | 2021* | 2022 | 2023 | 2024 | avg trade | t |", "|---|---|---|---|---|---|---|---|---|"]
            N += [f"| {r['side']} | {r['trades']} | {money(r['net'])} | {money(r['2021'])} | {money(r['2022'])} | {money(r['2023'])} | {money(r['2024'])} | "
                  f"{money(r['avg'])} | {r['t']} |" for r in ms]
            N += ["", "Its whole BUILD heat map by side (96 variants; each side has its own central variant):",
                  "| side | variants positive | median | central variant | trades | net | t |", "|---|---|---|---|---|---|---|"]
            N += [f"| {x['side']} | {100 * x['share_pos']:.0f} % | {money(x['median_net'])} | `{x['central']}` | {x['trades']} | {money(x['net'])} | {(x['t'] or 0):.2f} |"
                  for x in mb]
            N.append("News days (CPI 39 trades $8,364; jobs report 37 trades $3,527; Fed days 27 trades $452) are 12 % of the trades and 45 % of the profit, "
                     "but in 2024 they gave only $856 of $12,437. Shorts earn $22,352, longs $6,447. Long / short here is a split of stored trades (approximate).")
        if fam == "straddle_t_0830" and (HERE / "admission_0830.json").exists():
            p8 = json.loads((HERE / "pick_0830.json").read_text())
            a8 = json.loads((HERE / "admission_0830.json").read_text())
            yrs = " · ".join(f"{y['period']} {money(y['net'])} ({y['trades']} trades)" for y in a8["per_year"])
            N += ["* `news_only` passed b, c, d and e on BUILD (t 3.59 against a bar of 2.62; beats 99.98 % of random day subsets) with 71 trades. "
                  "The analyst had counted the 100 trades on BUILD alone; the ORCHESTRATOR RULED (2026-10-04) that the rule counts BUILD + 2024 and that 2024 be opened.",
                  f"* 2024 opened (whole menu, news days only): {100 * p8['pick']['share_pos']:.1f} % of {p8['pick']['cells']} variants positive, median "
                  f"{money(p8['pick']['median_net'])} -> the table PASSES (at 60 % only). Trades BUILD + 2024 of the central variant: {p8['trades_build_plus_pick']}.",
                  f"* The BUILD central variant `{p8['central']}` per year: {yrs}. Under 2 ticks + 250 ms: BUILD {money(a8['tests']['stress_build']['stressed'])}, "
                  f"2024 {money(a8['tests']['stress_pick']['stressed'])}.",
                  f"* {a8['surviving']} of {a8['judged']} variants are positive in both periods and under stress "
                  f"(`members/_rejected/{a8['name']}/surviving_set.csv`), but the central variant is not one of them and the ruling allows no replacement. "
                  f"**{'ADMITTED' if a8['admit'] else 'NOT ADMITTED'}**: the central variant loses money in 2024. The random-minute control was not run on 2024.",
                  "* It is the SAME IDEA as the member orb_NQ_tf1_pre (a straddle of the 08:30 data burst); the member's own news-day profit also faded in 2024 ($856)."]
        N += ["", "## Left on the DONE checklist", "* " + left(fam, root, "base", True),
              "", "Files here: `sides.csv` (the 8 sides, shares at 60 / 70 / 80 %), `per_year.csv` (central variant per year then combined, 1 contract and about $1,000 of risk), "
              "`nulls.csv` (controls + the placebo rows of the same market, bar size and session), `heatmap.csv` (every variant of every side).", ""]
        (d / "notes.md").write_text("\n".join(N))

    # ---------------------------------------------------------------- IDEAS.md
    groups = defaultdict(list)
    for r in B:
        groups[(r["kind"], r["family"], r["root"])].append(r)
    lines = ["# IDEAS — every idea tested so far in the edge library (one line per idea = family x market)", "",
             "Updated 2026-10-04 after stage 2a (deepen round 1 on stored trades). BUILD = 22 Sep 2021 to end 2023; 2025+ never read.",
             "Status: **ADMITTED** = a member is saved · **OPEN** = its DONE checklist is not complete (a fail does not count yet) · **SHELVED** = checklist complete, no edge.",
             "No idea is SHELVED yet: none has used its 4 deepen rounds. Rounds: stage 2a = round 1 (four tools at once: daily ADX trend, volatility regime, news days, long / short).",
             "Done for every idea (not repeated per line): reason written first · 4 fixed + 2 ATR + 2 percent stops · targets none / 1:1 / 1:2 / 1:3 · flat by 15:58 · "
             "random-entry / time-shuffle / shuffled-book controls. The last column lists only what is LEFT.", "",
             "| idea | market | status | deepen rounds used | units judged / pass heat map (BUILD) | left on the DONE checklist | record |", "|---|---|---|---|---|---|---|"]
    n_open = n_adm = 0
    for (kind, fam, root), rows in sorted(groups.items(), key=lambda kv: (kv[0][0] != "base", kv[0][1], ("NQ", "ES", "GC").index(kv[0][2]))):
        is_t = (fam, root) in touched
        hp = sum(r["plateau"] == "True" for r in rows)
        admitted = kind == "base" and fam == "orb" and root == "NQ"
        status = "**ADMITTED**" if admitted else "OPEN"
        n_adm += admitted
        n_open += not admitted
        if kind == "stage_d":
            rounds = "tool of its base idea (stage 1)"
            link = "[stage_d_paired.csv](out/admit/stage_d_paired.csv)"
        else:
            rounds = ("1 of 4" if is_t else "0 of 4") + (" (+ stage-1 book filter / exit)" if fam in stage_d_bases and root == "NQ" else "")
            link = f"[notes](ideas/{fam}_{root}/notes.md)" if is_t else "[build_units.csv](out/admit/build_units.csv)"
            if admitted:
                link = "[card](members/orb_NQ_tf1_pre/card.md) · " + link
        weak = " (WEAK reason: needs t >= 3)" if rows[0]["weak"] == "True" else ""
        lines.append(f"| {idea_name(fam)}{weak} | {root} | {status} | {rounds} | {len(rows)} / {hp} | {left(fam, root, kind, is_t)} | {link} |")
    lines += ["", f"{n_adm} admitted, {n_open} open, 0 shelved. Near misses of round 1 and what was opened on 2024: `out/deepen_summary.md`.",
              "2024 already read in round 1, none admitted (these units are information only from here): donchian NQ 5-min morning (quiet days), "
              "rsi2 NQ 30-min evening (long only), straddle at 08:30 ET NQ (news days; opened by the orchestrator's ruling). "
              "Their records: `members/_rejected/`.", ""]
    (W / "IDEAS.md").write_text("\n".join(lines))
    print("ideas folders", len(touched), "IDEAS.md lines", n_adm + n_open)


if __name__ == "__main__":
    main()
