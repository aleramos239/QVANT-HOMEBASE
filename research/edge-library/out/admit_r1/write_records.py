"""STAGE 2b records for the user: ideas/<family>_<root>/{notes.md, heatmap.csv, per_year.csv, nulls.csv} for the 27 round 1 ideas
and their lines in IDEAS.md. Reads only what the earlier steps wrote + BUILD stores (and the 2024 stores already opened)."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import library as LB  # noqa: E402

OUT = W / "out" / "admit_r1"
IDEAS = W / "ideas"
PLAIN = {"vwap_trend_pull": "VWAP trend pullback", "va_reclaim": "value-area reclaim", "orb_confirm": "opening-range close break, one direction",
         "late_mom": "late-day momentum (15:30)", "open_fade": "open fade", "vol_spike_break": "volume-spike breakout",
         "straddle_tight_0830": "tight straddle at 08:30 ET", "straddle_tight_0930": "tight straddle at 09:30 ET",
         "straddle_tight_1000": "tight straddle at 10:00 ET"}
LEFT = {"vwap_trend_pull": "", "va_reclaim": "the delta-flip version (spec: only if this shows life); ", "orb_confirm": "30-minute bars; ",
        "late_mom": "", "open_fade": "15- and 30-minute bars; ", "vol_spike_break": "",
        "straddle_tight_0830": "the standard 8-stop menu and the no-target exit (it ran its own 3 stops x 3 targets); more random-minute seeds (thin bar); ",
        "straddle_tight_0930": "the standard 8-stop menu and the no-target exit; ", "straddle_tight_1000": "the standard 8-stop menu and the no-target exit; "}
TOOLS = ("deepen rounds (0 of 4 used): daily ADX trend, volatility regime (quiet / active days), news days, long-only / short-only, RSI direction, "
         "inverse, time exit (Level 2 tools: NQ only); verdict")


def money(v) -> str:
    return "n/a" if v is None or v == "" else f"${float(v):,.0f}".replace("$-", "-$")


def pct(v) -> str:
    return "n/a" if v in (None, "") else f"{100 * float(v):.0f} %"


def show(uid: str) -> str:
    return " · ".join(x for x in uid.split("|") if x)


def cell_sess(u, cid, sess):
    x = LB.unit_cell(u, cid)
    if sess == "all":
        return x
    m = x["sess"] == LB.SESS_CODE[sess]
    return {k: v[m] for k, v in x.items()}


def main():
    B = list(csv.DictReader((OUT / "build_units.csv").open()))
    Q = defaultdict(dict)
    for r in csv.DictReader((OUT / "quiet_active.csv").open()):
        Q[r["uid"]][r["side"]] = r
    A = defaultdict(list)
    for r in csv.DictReader((OUT / "author_cells.csv").open()):
        A[r["uid"]].append(r)
    J = json.loads((OUT / "pick_judgement.json").read_text())
    SV = json.loads((OUT / "surviving.json").read_text())
    AD = json.loads((OUT / "admission.json").read_text())
    groups = defaultdict(list)
    for r in B:
        groups[(r["family"], r["root"])].append(r)
    lines_ideas = []
    for (fam, root), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], ("NQ", "ES", "GC").index(kv[0][1]))):
        d = IDEAS / f"{fam}_{root}"
        d.mkdir(parents=True, exist_ok=True)
        stores = {k: LB.load_unit(k) for k in sorted({r["key"] for r in rows})}
        meta = next(iter(stores.values()))["meta"]
        cal = LB.calendar("build", root)
        heat, py, nulls = [], [], []
        for r in rows:
            u = stores[r["key"]]
            for t in LB.plateau_units(u, r["sess"])[r["label"]]:
                heat.append({"unit": r["uid"], "cell": t["id"], "dead": t["dead"], "author_cell": t["info"], "trades": t["trades"], "net": t["net"],
                             "t": "" if t["t"] is None else round(t["t"], 3)})
            if r["plateau"] == "True":
                x = cell_sess(u, r["member"], r["sess"])
                z = LB.sized(x, root)
                for view, rr in (("1 contract", LB.per_year(x, cal)), ("$1,000 risk (micros)", LB.per_year(z, cal, z["cost"]))):
                    for a in rr:
                        py.append({"unit": r["uid"], "central": r["member"], "view": view, "period": a["period"], **{k: a[k] for k in LB.METRIC_KEYS}, "t": a["t"]})
                nulls.append({"unit": r["uid"], "central": r["member"], "t": r["m_t"], "bar_best_of_random": r["bar"], "control": r["ctrl"],
                              "lift_vs_control": r["ctrl_lift"], "beats_share_of_200_draws": r.get("ctrl_p_beat", ""), "control_nets": r.get("ctrl_nets", ""),
                              "bar_with_stage1_random_minutes": r.get("bar_all", ""), "failed": r["fail"]})
        for name, data in (("heatmap.csv", heat), ("per_year.csv", py), ("nulls.csv", nulls)):
            if data:
                with (d / name).open("w", newline="") as fh:
                    w = csv.DictWriter(fh, list(data[0]))
                    w.writeheader()
                    w.writerows(data)
        n = len(rows)
        v = [sum(r[k] == "True" for r in rows) for k in ("v60", "v70", "v80")]
        ctl = sum(r["plateau"] == "True" and "c1" not in r["fail"] and "shift" not in r["fail"] for r in rows)
        bp = [r for r in rows if r["build_pass"] == "True"]
        admitted = [a for uid, a in AD.items() if a["admit"] and any(r["uid"] == uid for r in rows)]
        status = "**ADMITTED (FLAGGED)**" if admitted else "OPEN"
        L = [f"# {PLAIN[fam]} (`{fam}`) on {root} — idea record (stage 2b = new-idea round 1, 2026-10-04)", "",
             f"* **Status: {status.strip('*')}** · deepen rounds used: 0 of 4",
             f"* Reason written first: {meta['rationale']}",
             f"* Rules as run: {meta['notes']}",
             "* BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only); 1 contract, after costs. 2024 was opened only where this note says so. 2025+ was never read.",
             f"* Units judged: {n}. Heat map passes at 60 / 70 / 80 % of variants positive: {v[0]} / {v[1]} / {v[2]}. Also beat the matched random control: {ctl}. "
             f"Also reach the best-of-random bar (= pass BUILD): {len(bp)}.", "",
             "## Every unit on BUILD (sorted by the share of variants positive)",
             "| unit | variants | positive | median variant | pass 60/70/80 | central variant | trades | net | t | bar | lift vs random | beats | failed |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: -float(r["share_pos"] or 0)):
            ok = r["plateau"] == "True"
            L.append(f"| {show(r['uid'])} | {r['cells']} | {pct(r['share_pos'])} | {money(r['median_net'])} | "
                     f"{'/'.join('Y' if r[k] == 'True' else 'n' for k in ('v60', 'v70', 'v80'))} | `{r['member'] or 'none'}` | {int(float(r['m_trades'])) if r.get('m_trades') else ''} | "
                     f"{money(r['member_net'])} | {float(r['m_t']):.2f} | " if r.get("m_t") else
                     f"| {show(r['uid'])} | {r['cells']} | {pct(r['share_pos'])} | {money(r['median_net'])} | n/n/n | none | | | | ")
            L[-1] += (f"{float(r['bar']):.2f} | {money(r['ctrl_lift'])} | {pct(r['ctrl_p_beat']) if r.get('ctrl_p_beat') else 'n/a'} | {r['fail'] or 'none: passes BUILD'} |"
                      if ok else " | | | heat map |")
        L += ["", "Failed: `heat map` = fewer than 60 % of variants positive or median not positive · `c1` / `shift` = the central variant does not beat matched random "
                  "entries / the same trade at a random minute or with a random direction · `bar` = its t is below what the best variant of a random menu reaches.", ""]
        ql = sum(Q[r["uid"]]["vol_lo"]["v60"] == "True" for r in rows)
        qh = sum(Q[r["uid"]]["vol_hi"]["v60"] == "True" for r in rows)
        L += ["## Quiet / active days (information only, not a test)",
              f"Heat map on quiet days only (prior-day range at or below its 20-day median) passes in {ql} of {n} units; on active days only in {qh} of {n}; on all days in {v[0]}.",
              "| unit | quiet: variants positive / median | active: variants positive / median |", "|---|---|---|"]
        for r in sorted(rows, key=lambda r: -float(r["share_pos"] or 0))[:8]:
            a, b = Q[r["uid"]]["vol_lo"], Q[r["uid"]]["vol_hi"]
            L.append(f"| {show(r['uid'])} | {pct(a['share_pos'])} / {money(a['median_net'])} | {pct(b['share_pos'])} / {money(b['median_net'])} |")
        L += ["(the 8 units with the highest share of positive variants; all units: `out/admit_r1/quiet_active.csv`)", ""]
        auth = [a for r in rows for a in A.get(r["uid"], [])]
        if auth:
            nets = np.array([float(a["net"]) for a in auth])
            best = max(auth, key=lambda a: float(a["t"] or -9))
            L += ["## Author cells (information only: never in the heat map, never the member)",
                  f"{len(auth)} author cells: {int((nets > 0).sum())} positive, median {money(np.median(nets))}, best {money(nets.max())}, worst {money(nets.min())}. "
                  f"Highest t: `{best['cell']}` in {show(best['uid'])}: {best['trades']} trades, {money(best['net'])}, t {float(best['t']):.2f}. All: `out/admit_r1/author_cells.csv`.", ""]
        opened = [(uid, j) for uid, j in J.items() if any(r["uid"] == uid for r in rows)]
        if opened:
            L += ["## 2024 (opened only for the units that passed every BUILD test; passing session only)"]
            for uid, j in opened:
                c, sv, ad = j["central_pick"], SV.get(uid), AD.get(uid)
                s = (f"* {show(uid)}: 2024 heat map {pct(j['pick']['share_pos'])} of {j['pick']['cells']} variants positive, median {money(j['pick']['median_net'])} -> "
                     f"{'PASSES' if j['pick']['pass'] else 'FAILS'}. BUILD central variant `{j['central']}` in 2024: {money(c['net'])} ({c['trades']} trades), "
                     f"lift over its random control {money(c['c1_lift'])}.")
                if sv:
                    x = sv["central"]
                    s += (f" Under 2 ticks + 250 ms: BUILD {money(x['build'])} -> {money(x['build_stress'])}; 2024 {money(x['pick'])} -> {money(x['pick_stress'])}. "
                          f"{len(sv['surviving'])} of {sv['judged']} variants are positive in both periods and under stress.")
                if ad and ad["admit"]:
                    s += f" **ADMITTED, FLAGGED** -> `members/{ad['name']}/card.md` (read its flags: thin random bar; same idea as orb_NQ_tf1_pre)."
                else:
                    s += (" **NOT ADMITTED**: " + ("the 2024 heat map fails." if not j["pick"]["pass"] else
                                                   "the BUILD central variant is not positive in 2024 and no moved default is allowed "
                                                   f"(record: `members/_rejected/{ad['name']}/`)."))
                L.append(s)
            L += ["These units' 2024 is now spent: information only from here.", ""]
        L += ["## Left on the DONE checklist", f"* {LEFT[fam]}{TOOLS}", "",
              "Files here: `heatmap.csv` (every variant of every unit), `per_year.csv` (central variant of each unit that passes the heat map: per year then combined, "
              "1 contract and about $1,000 of risk), `nulls.csv` (controls and bars of those units).", ""]
        (d / "notes.md").write_text("\n".join(L))
        link = f"[notes](ideas/{fam}_{root}/notes.md)"
        if admitted:
            link = f"[card](members/{admitted[0]['name']}/card.md) · " + link
        lines_ideas.append(f"| {PLAIN[fam]} (`{fam}`, stage 2b) | {root} | {status} | 0 of 4 | {n} / {v[0]} | {LEFT[fam]}{TOOLS} | {link} |")
    # ---------------------------------------------------------------- IDEAS.md: add the round 1 lines once
    p = W / "IDEAS.md"
    S = p.read_text().split("\n")
    S = [x for x in S if ", stage 2b) |" not in x and not x.startswith("Stage 2b (new-idea round 1)")]
    k = next(i for i, x in enumerate(S) if " admitted" in x and " open, " in x and " shelved" in x)
    last = max(i for i, x in enumerate(S[:k]) if x.startswith("| "))
    S[last + 1:last + 1] = lines_ideas
    k = next(i for i, x in enumerate(S) if " admitted" in x and " open, " in x and " shelved" in x)
    body = [x for x in S if x.startswith("| ") and not x.startswith("| idea ")]
    n_adm = sum("ADMITTED" in x for x in body)
    S[k] = (f"{n_adm} admitted (1 clean: orb_NQ_tf1_pre; 1 flagged: straddle_tight_0830_NQ_tf30_pre, the same 08:30 idea), {len(body) - n_adm} open, 0 shelved. "
            "Near misses and what was opened on 2024: `out/deepen_summary.md` (stage 2a), `out/round1_summary.md` (stage 2b).")
    S.insert(k + 1, "Stage 2b (new-idea round 1) 2024 already read, not admitted (information only from here): vwap_trend_pull NQ 5-min afternoon, "
                    "vol_spike_break NQ 30-min afternoon, straddle_tight_0830 GC. Records: `members/_rejected/`, `ideas/`.")
    S = [x.replace("Updated 2026-10-04 after stage 2a (deepen round 1 on stored trades).", "Updated 2026-10-04 after stage 2b (new-idea round 1; stage 2a = deepen round 1 on stored trades).") for x in S]
    p.write_text("\n".join(S))
    print("ideas", len(lines_ideas), "IDEAS.md rows", len(body), "admitted", n_adm)


if __name__ == "__main__":
    main()
