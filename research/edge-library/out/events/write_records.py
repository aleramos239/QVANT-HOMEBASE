"""STAGE 3 records: the Stage-3 section of every admitted member's card, ideas/event_straddle_<market>/ (notes.md + CSVs), the
IDEAS.md lines, out/events_summary.md and the progress.md lines. Reads only the JSON / CSV results of out/events/ and the stores
already opened by the stage (BUILD; 2024 only for the four BUILD passers). Re-runnable (it replaces its own blocks)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev as E  # noqa: E402
import judge_build as JB  # noqa: E402
import judge_pick as JP  # noqa: E402
import library as LB  # noqa: E402

W = E.W
MARK = "<!-- STAGE 3 RECORD -->"
BU = json.loads((HERE / "build_units.json").read_text())
PJ = json.loads((HERE / "pick_judgement.json").read_text())
ADM = json.loads((HERE / "admission.json").read_text())
FP = json.loads((HERE / "fill_probe.json").read_text())
OD = json.loads((HERE / "odds.json").read_text())
FOMC = json.loads((HERE / "fomc_1400.json").read_text())
BYU = {r["uid"]: r for r in BU}
TYPE_PLAIN = {"NFP": "jobs report (NFP)", "CPI": "CPI", "PPI": "PPI", "RETAIL": "retail sales", "GDP": "GDP", "PCE": "PCE", "CLAIMS": "weekly jobless claims",
              "ISM_MFG": "ISM manufacturing", "ISM_SVC": "ISM services", "JOLTS": "JOLTS", "UMICH": "Michigan sentiment (prelim)"}
RULE = {"E1-A-GC": "On days with an 08:30 ET US data release: at 08:29:59 ET a buy stop 0.6 points above and a sell stop 0.6 points below the gold price (one cancels "
                   "the other; an unfilled bracket is cancelled after 5 minutes); stop 1.6 points, target 1.6 points (1:1); flat by 15:58. One trade a day at most.",
        "E1-B-NQ": "On tier-1 release days only: at 08:29:59 ET a buy stop 5 points above and a sell stop 5 points below the NQ price (one cancels the other; "
                   "cancelled after 5 minutes if unfilled); stop 5 points, target 15 points (1:3); flat by 15:58. One trade a day at most.",
        "E3-C-GC": "On days with a 10:00 ET release: at 09:59:59 ET a buy stop 0.6 points above and a sell stop 0.6 points below the gold price (one cancels the "
                   "other; cancelled after 5 minutes if unfilled); stop 1.6 points, target 1.6 points (1:1); flat by 15:58. One trade a day at most."}
LIVE = ["| real account fills (desk journal, read-only) | fills | adverse slip past the stop price |", "|---|---|---|",
        "| NQ 09:30 straddle | 10 | mean 0.6 pt, median 0.375 pt, worst 1.75 pt |", "| gold, jobs report 2026-10-02 | 1 | 0.0 |",
        "| YM 09:30 | 2 | 4 and 5 pts |",
        "Real fills sit near the engine's base fill (stop price + 1 tick) plus about one tick: far better than the 1 ms probe. None of them is an NQ or gold "
        "fill at an 08:30 / 10:00 release except the one gold jobs-report fill."]


def usd(v) -> str:
    if v is None:
        return "n/a"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def pc(v, d=0) -> str:
    return "n/a" if v is None else f"{100 * v:.{d}f} %"


def years_line(rows) -> str:
    return " · ".join(f"{r['period']} {usd(r['net'])} ({r['trades']})" for r in rows)


def probe_md(uid) -> list:
    p = FP[uid]
    L = ["| entry filled | BUILD net (never better than the stop price) | 2024 net | BUILD net (that print + 1 tick) | 2024 net | mean slip past the stop, BUILD / 2024 |",
         "|---|---|---|---|---|---|"]
    for k, lab in (("0ms", "on the trigger print (engine)"), ("1ms", "1 ms later"), ("5ms", "5 ms later"), ("25ms", "25 ms later")):
        b, q = p["build"], p["pick"]
        L.append(f"| {lab} | {usd(b['floor'][k])} | {usd(q['floor'][k])} | {usd(b['neutral'][k])} | {usd(q['neutral'][k])} | "
                 f"{b['mean_slip_pts'][k]} / {q['mean_slip_pts'][k]} pts |")
    L.append(f"Own tick replay of the stored trades (it reproduces every engine trade to the cent at 0 ms). Median number of prints sharing the trigger "
             f"print's timestamp: {p['build']['median_prints_sharing_trigger_ts']:.0f} (BUILD). "
             + ("**FILL-FRAGILE: the net is negative at 5 ms.**" if p["fill_fragile"] else "Not FILL-FRAGILE by the written rule (positive at 5 ms in both periods)."))
    return L


def odds_md(name) -> list:
    L = ["| account | fill model | size | micros | risk a trade | worst open loss | eval pass <= 10 days, any start | started the day before a tier-1 release | "
         "funded max payout <= 20 days |", "|---|---|---|---|---|---|---|---|---|"]
    for r in OD[name]["rows"]:
        L.append(f"| {r['account']} | {'trigger print' if r['fill'] == 'BASE' else '5 ms later'} | {'largest inside the drawdown' if r['size'] == 'MAX' else 'about $1,000 risk'} | "
                 f"{r['micros']} | {usd(r['risk_usd'])} | {usd(r['worst_open_loss'])} | {pc(r['eval_p10'])} (bust {pc(r['eval_bust10'])}) | "
                 f"{pc(r['eval_p10_before_tier1'])} | {pc(r['funded_p20'])} |")
    L.append("Information only. Bar: 60 % eval / 75 % funded. Sizes are cut to the contract limit (Lucid 40 micros, Apex 100), so on Lucid the two sizes are often the "
             "same. A two-sided bracket is not allowed on Apex. The 5 ms trades keep the same stop and target distances from the later fill.")
    return L


def member_trades(name):
    d = W / "members" / name
    return json.loads((d / "trades_build.json").read_text()), json.loads((d / "trades_pick.json").read_text())


def type_rows(tb, tp, clock) -> list:
    out = []
    for typ in (E.T1000 if clock == "C" else E.T0830):
        ds = E.days(typ)
        b, p = [t["net"] for t in tb if t["date"] in ds], [t["net"] for t in tp if t["date"] in ds]
        out.append((TYPE_PLAIN[typ], len(b), sum(b), len(p), sum(p)))
    return out


def card_section(uid) -> list:
    r, j, a = BYU[uid], PJ[uid], ADM[uid]
    name = a["name"]
    tb, tp = member_trades(name)
    both = tb + tp
    fast = [t for t in both if t["seconds"] < 2]
    t = a["tests"]
    clock = "A" if E.GROUP_TIME[r["group"]] == "08:30" else "C"
    L = ["", MARK, f"## Stage 3 record — event straddle `{uid}` (2026-10-04): ADMITTED, FLAGGED (checker: confirm or demote)",
         f"* **Rule in plain words:** {RULE[uid]}",
         f"* **Event days it trades:** {E.PLAIN[r['group']]}. {r['event_days_build']} such sessions on BUILD, {r['event_days_2024']} in 2024. Calendar: "
         "`engine/cache/events.csv` (official release schedules; never checked against prices).",
         "* **Reason (written before any number):** a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just "
         "before catches it whichever way.",
         f"* **Second look:** {('YES — ' + r['second_look'] + '. 2024 is not a clean test for this member.') if r['second_look'] else 'no: 2024 was opened for the first time for this unit'}",
         f"* BUILD tests: (a) {r['trades']} trades + {r['event_days_2024']} event days in 2024 · (b) {pc(r['share_pos'])} of {r['cells']} variants positive, median "
         f"{usd(r['median_net'])} · (c) {usd(r['mean_event'])} a trade on event days vs {usd(r['mean_nonevent'])} on days without a release at that time "
         f"({r['nonevent_trades']} trades) · (d) t {r['t']:.2f} vs bar {r['bar']:.2f} · (e) beats {pc(r['e_p'], 2)} of 4,000 random same-size day subsets (needs 99.67 %).",
         f"* 2024: {pc(j['pick']['share_pos'])} of {j['pick']['cells']} variants positive, median {usd(j['pick']['median_net'])}; this variant {usd(j['central_pick']['net'])} "
         f"({j['central_pick']['trades']} trades, rank {j['central_pick_rank']} of {j['pick']['cells']}); the same bracket at a random minute on the same days: "
         f"{usd(j['shift_pick']['mean'])}; on days without a release: {usd(j['nonevent_pick']['mean'])} a trade.",
         f"* Per year (1 contract): {years_line(a['per_year'])}.",
         f"* At about $1,000 of risk a trade ({a['micros_median']} micros): {years_line(a['per_year_r1000'])}; worst open loss on one trade "
         f"{usd(a['per_year_r1000'][-1]['worst_open_loss'])}. Worst open loss per micro {usd(t['open_loss_fits']['worst_open_loss_per_micro'])}: at most "
         f"{t['open_loss_fits']['micros_fit_worst']} micros inside $2,000.",
         f"* Stress (2 ticks + 250 ms): BUILD {usd(t['stress_build']['base'])} -> {usd(t['stress_build']['stressed'])}; 2024 {usd(t['stress_pick']['base'])} -> "
         f"{usd(t['stress_pick']['stressed'])}.",
         f"* **Speed flag:** {len(fast)} of {len(both)} trades open AND close inside 2 seconds and earn {usd(sum(x['net'] for x in fast))} of the {usd(sum(x['net'] for x in both))}; "
         f"the median trade lasts {float(np.median([x['seconds'] for x in both])):.1f} s. The profit is the simulator's fills inside the burst.", "",
         "### Event types it trades (BUILD / 2024; a day with two releases is counted under both)", "| release | BUILD trades | BUILD net | 2024 trades | 2024 net |",
         "|---|---|---|---|---|"]
    for nm, nb, sb, np_, sp in type_rows(tb, tp, clock):
        L.append(f"| {nm} | {nb} | {usd(sb)} | {np_} | {usd(sp)} |")
    L += ["", "### Fill realism (information, not a gate): what if the stop entry fills later than the trigger print?"] + probe_md(uid) + [""] + LIVE
    L += ["", "### Odds alone on a prop account (information; open losses count)"] + odds_md(name)
    if uid == "E1-A-GC":
        b, jb, ab = BYU["E1-B-GC"], PJ["E1-B-GC"], ADM["E1-B-GC"]
        L += ["", "### The tier-1-only version (unit E1-B-GC): the same variant on a subset of these days — the SAME strategy, no folder of its own",
              f"* BUILD: {b['trades']} trades, {usd(b['net'])}, t {b['t']:.2f}; {pc(b['share_pos'])} of variants positive; beats {pc(b['e_p'], 2)} of random day subsets. "
              f"2024: {usd(jb['central_pick']['net'])} ({jb['central_pick']['trades']} trades); table {pc(jb['pick']['share_pos'])} positive. Per year: {years_line(ab['per_year'])}.",
              f"* Stress: BUILD {usd(ab['tests']['stress_build']['stressed'])}, 2024 {usd(ab['tests']['stress_pick']['stressed'])}. Entry 5 ms later: BUILD "
              f"{usd(FP['E1-B-GC']['build']['floor']['5ms'])}, 2024 {usd(FP['E1-B-GC']['pick']['floor']['5ms'])}. It passes every admission test too."]
    L += ["", "### Flags", "* The whole profit needs the stop entry to fill on (or within about a tick of) the trigger print. One real gold fill and ten real NQ 09:30 fills "
          "support that; no real fill at an NQ 08:30 or a gold 10:00 release exists yet. Paper / small-size forward fills on release days are the missing evidence."]
    if uid == "E1-B-NQ":
        L.append("* This is the variant the checker DEMOTED on all days (`members/_demoted/straddle_tight_0830_NQ_tf30_pre/`), now on tier-1 days only. Its t now clears the "
                 "unchanged bar (3.35 vs 2.56; on all days 1.98). The second demotion reason still stands: the profit needs the fill on the trigger print, and 2024 "
                 "survives the stress by $173 only.")
        L.append("* SAME IDEA as orb_NQ_tf1_pre (the 08:30 burst on NQ): same side on 77 % of shared days, daily correlation 0.36 on those days. One strategy for a stack, not two.")
    if uid == "E1-A-GC":
        L.append("* Same 08:30 burst as the NQ member on another market: same side on 64 % of shared days, daily correlation 0.19. At 1 ms the BUILD net is negative, at "
                 "25 ms the 2024 net is negative: close to FILL-FRAGILE.")
    if uid == "E3-C-GC":
        L.append("* FILL-FRAGILE. Only 143 trades in all (97 on BUILD). Different days from the 08:30 gold member (43 shared days of 143; daily correlation 0.03).")
    L.append("")
    return L


def write_cards():
    for uid, a in ADM.items():
        if not a.get("dir"):
            continue
        p = Path(a["dir"]) / "card.md"
        s = p.read_text()
        if MARK in s:
            s = s[:s.index(MARK)].rstrip("\n") + "\n"
        p.write_text(s + "\n".join(card_section(uid)))


def unit_row_md(r) -> str:
    f = [k for k in "abcde" if not r[k]]
    t = "n/a" if r["t"] is None else f"{r['t']:.2f}"
    return (f"| {r['uid']} | {r['family']} · {E.GROUP_TIME[r['group']]} · group {r['group']} | {r['trades']} | {pc(r['share_pos'])} of {r['cells']} | {usd(r['median_net'])} | "
            f"`{r['central']}` | {usd(r['net'])} | {t} / {r['bar']:.2f} | {usd(r.get('lift_mean'))} | {pc(r.get('e_p'), 1)} | "
            f"{'**PASS**' if r['pass'] else 'fail: ' + ', '.join(f)} |")


UNIT_HEAD = ["| unit | family · time · days | BUILD trades | variants positive | median variant | central variant | its net | t / bar | lift a trade vs non-event days | "
             "beats random day subsets | BUILD |", "|---|---|---|---|---|---|---|---|---|---|---|"]


def write_ideas():
    for root in E.ROOTS:
        d = W / "ideas" / f"event_straddle_{root}"
        d.mkdir(parents=True, exist_ok=True)
        units = [r for r in BU if r["root"] == root]
        flat = [k for k in JB.FLAT]
        with (d / "units.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, flat, extrasaction="ignore")
            w.writeheader()
            w.writerows(units)
        heat, peryear, ptype = [], [], []
        for r in units:
            u = JB.load(r["key"])
            base = LB.plateau_units(u, r["sess"])[""]
            for t in JB.side_table(u, r["sess"], base, r["group"]):
                heat.append({"uid": r["uid"], "period": "build", "variant": t["id"], "trades": t["trades"], "net": t["net"], "t": t["t"], "dead": t["dead"],
                             "central": t["id"] == r["central"]})
            if r["uid"] in PJ:
                rd, _ = JP.STORES[r["family"]]
                up = JB.load(JP.pick_key(r["family"], root, r["sess"]), rd)
                for t in JB.side_table(up, r["sess"], base, r["group"]):
                    heat.append({"uid": r["uid"], "period": "2024", "variant": t["id"], "trades": t["trades"], "net": t["net"], "t": t["t"], "dead": t["dead"],
                                 "central": t["id"] == r["central"]})
            for view in ("c1", "r1000"):
                rows = list((r.get("years") or {}).get(view) or [])
                if r["uid"] in PJ and view == "c1":
                    rows = rows[:-1] + [x for x in PJ[r["uid"]]["years_pick"]["c1"] if x["period"] != "combined"]
                for y in rows:
                    peryear.append({"uid": r["uid"], "central": r["central"], "view": "1 contract" if view == "c1" else "about $1,000 risk", **y})
            ptype += r.get("per_type") or []
        for fn, rows in (("heatmap.csv", heat), ("per_year.csv", peryear), ("per_type.csv", ptype)):
            if rows:
                with (d / fn).open("w", newline="") as fh:
                    w = csv.DictWriter(fh, list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
        passed = [r for r in units if r["pass"]]
        mem = [ADM[r["uid"]] for r in passed if ADM.get(r["uid"], {}).get("dir")]
        status = "ADMITTED, FLAGGED (" + ", ".join(f"`{m['name']}`" for m in mem) + "; checker: confirm or demote)" if mem else "OPEN"
        L = [f"# event straddle on {root} — idea record (stage 3 = new-idea round 2, 2026-10-04)", "",
             f"* **Status: {status}** · deepen rounds used: 0 of 4",
             "* Reason written first: a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it "
             "whichever way.",
             "* What was done: no new strategy code. The stored BUILD trades of three straddle families that ran on EVERY day were split by an official release "
             "calendar (`engine/cache/events.csv`, never checked against prices): E1 tight straddle at 08:30, E2 ATR straddle at 08:30, E3 tight straddle at 10:00. "
             "Day groups: A = every 08:30 release day (jobs report, CPI, PPI, retail sales, GDP, PCE, weekly claims), B = the same without claims-only days, "
             "C = every 10:00 release day (ISM manufacturing, ISM services, JOLTS, Michigan sentiment).",
             "* BUILD = 22 Sep 2021 to end 2023; 1 contract, after costs. 2024 was opened only for units that passed every BUILD test. 2025+ was never read.",
             "* A unit passes BUILD only with all five: (a) 100 trades reachable with 2024 · (b) at least 60 % of variants positive and median positive · (c) more "
             "per trade than the same bracket on days without a release at that time · (d) t at or above the random-minute bar · (e) beats 99.67 % of 4,000 random "
             "same-size day subsets.", "", "## The five units on BUILD"] + UNIT_HEAD + [unit_row_md(r) for r in units]
        L += ["", "## What each release type did (central variant, BUILD; information only: too few trades per type)"]
        for r in units:
            if r["group"] in ("A", "C") and r.get("per_type"):
                L.append(f"* {r['uid']} `{r['central']}`: " + " · ".join(
                    f"{TYPE_PLAIN.get(x['type'], 'no release at that time')} {x['trades']} trades {usd(float(x['net']))}" for x in r["per_type"]) + ".")
        f = FOMC[root]
        L += ["", "## Fed decision at 14:00 ET (information only; 19 BUILD days, tight straddle armed at 13:59:59)",
              f"* {pc(f['share_pos'])} of {f['cells']} variants positive, median {usd(f['median_net'])}; central variant `{f['central']}`: {f.get('trades')} trades, "
              f"{usd(f.get('net'))}, t {f.get('t', 0):.2f}. Too few trades for any test; never opened on 2024."]
        L += ["", "## 2024 (opened only for the units that passed every BUILD test; whole menu, same day filter, random-minute control run too)"]
        if not passed:
            L.append("* No unit passed BUILD: 2024 was not opened for this market.")
        for r in passed:
            j, a = PJ[r["uid"]], ADM[r["uid"]]
            t = a["tests"]
            L.append(f"* {r['uid']}{' (SECOND LOOK on 2024)' if r['second_look'] else ' (first look)'}: {pc(j['pick']['share_pos'])} of {j['pick']['cells']} variants positive, "
                     f"median {usd(j['pick']['median_net'])} -> passes. BUILD central variant `{r['central']}` in 2024: {usd(j['central_pick']['net'])} "
                     f"({j['central_pick']['trades']} trades); random-minute control {usd(j['shift_pick']['mean'])}. Under 2 ticks + 250 ms: BUILD {usd(t['stress_build']['base'])} -> "
                     f"{usd(t['stress_build']['stressed'])}; 2024 {usd(t['stress_pick']['base'])} -> {usd(t['stress_pick']['stressed'])}. Per year: {years_line(a['per_year'])}. "
                     f"Entry 5 ms after the trigger print: BUILD {usd(FP[r['uid']]['build']['floor']['5ms'])}, 2024 {usd(FP[r['uid']]['pick']['floor']['5ms'])}"
                     f"{' -> FILL-FRAGILE' if FP[r['uid']]['fill_fragile'] else ''}. Admission: every test passes"
                     f"{'' if a.get('dir') else ' (same variant as E1-A-GC on a subset of its days: recorded on that card, no folder of its own)'}.")
        L += ["", "## Left on the DONE checklist",
              "* real (paper or small-size) fills on release days: the profit needs a fill on the trigger print; the standard 8-stop menu and the no-target exit for the "
              "tight straddle (it ran its own 3 stops x 3 targets); more random-minute seeds; deepen rounds (0 of 4 used); the sealed 2025+ exam.", "",
              "Files here: `units.csv` (the five units with every test), `heatmap.csv` (every variant of every unit on its event days; 2024 rows only for opened units), "
              "`per_year.csv` (central variant per year, 1 contract and about $1,000 of risk), `per_type.csv` (per release type). Scripts and raw results: `out/events/`.", ""]
        (d / "notes.md").write_text("\n".join(L))


def write_ideas_md():
    p = W / "IDEAS.md"
    lines = [x for x in p.read_text().split("\n") if "(stage 3)" not in x and not x.startswith("Stage 3 (event straddles)")]
    last = max(i for i, x in enumerate(lines) if x.startswith("| "))
    new = []
    for root in E.ROOTS:
        units = [r for r in BU if r["root"] == root]
        mem = [ADM[r["uid"]]["name"] for r in units if r["pass"] and ADM.get(r["uid"], {}).get("dir")]
        st = ("ADMITTED, FLAGGED (" + ", ".join(mem) + "; needs a fill on the trigger print; checker: confirm or demote)") if mem else "OPEN"
        new.append(f"| event straddle: straddles at 08:30 / 10:00 ET on scheduled-release days only (stage 3) | {root} | {st} | 0 of 4 | 5 / {sum(r['b'] for r in units)} | "
                   "real fills on release days (paper or small size); the standard 8-stop menu and no-target exit; more random-minute seeds; deepen rounds; verdict | "
                   f"[notes](ideas/event_straddle_{root}/notes.md) |")
    lines[last + 1:last + 1] = new
    for i, x in enumerate(lines):
        if x.startswith("1 admitted (orb_NQ_tf1_pre;") or x.startswith("3 ideas admitted"):
            lines[i] = ("3 ideas admitted holding 4 members (orb_NQ_tf1_pre; stage 3, all FLAGGED and waiting for the checker: straddle_tight_0830_GC_tf30_pre_evA, "
                        "straddle_tight_0830_NQ_tf30_pre_evB, straddle_tight_1000_GC_tf30_nyam_evC), 140 open, 0 shelved. straddle_tight_0830_NQ on ALL days stays demoted "
                        "(members/_demoted/). Near misses and what was opened on 2024: `out/deepen_summary.md` (stage 2a), `out/round1_summary.md` (stage 2b), "
                        "`out/events_summary.md` (event straddles).")
        if x.startswith("Updated 2026-10-04 after stage"):
            lines[i] = ("Updated 2026-10-04 after the event-straddle round (new-idea round 2; stage 2b = new-idea round 1; stage 2a = deepen round 1 on stored "
                        "trades). BUILD = 22 Sep 2021 to end 2023; 2025+ never read.")
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("Stage 3 (event straddles) 2024 reads: straddle_tight_1000 GC on 10:00 release days (first look); straddle_tight_0830 NQ and GC on release days "
                 "(SECOND LOOK). Log: `out/events/pick_reads.csv`.")
    p.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    write_cards()
    write_ideas()
    write_ideas_md()
    print("cards, ideas/event_straddle_*, IDEAS.md written")
