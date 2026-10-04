"""ADMIT stage, step 4: out/near_misses.md (+ out/admit/near_misses.csv) and out/library_summary.md (<= 120 lines) from the files the
earlier steps wrote. Reads no tape and no PICK store that was not already opened (out/admit/pick_reads.csv)."""
import json
from pathlib import Path

import pandas as pd

W = Path(__file__).resolve().parents[2]
OUT = W / "out"
A = OUT / "admit"


def money(v) -> str:
    return "n/a" if v is None or pd.isna(v) else (f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}")


def pct(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{100 * v:.0f} %"


def main():
    d = pd.read_csv(A / "build_units.csv")
    J = json.loads((A / "pick_judgement.json").read_text())
    AD = json.loads((A / "admission.json").read_text())
    rate = json.loads((A / "null_passrate.json").read_text())
    bars = json.loads((A / "null_bars.json").read_text())
    led = pd.read_csv(W / "ledger.csv")
    base = d[d.kind == "base"].copy()
    base["fam"] = base.family.str.replace(r"straddle_t_\d+", "straddle_t (9 clock times)", regex=True)

    # ------------------------------------------------------------------ near misses
    nm = d[d.plateau & ~d.build_pass.astype(bool)].copy()
    nm["gap_to_bar"] = nm.m_t - nm.bar
    nm.sort_values(["fail", "gap_to_bar"], ascending=[True, False]).to_csv(A / "near_misses.csv", index=False)
    one = nm[nm.fail.isin(["bar", "weak_t3"])].sort_values("gap_to_bar", ascending=False)
    L = ["# Near misses — units that pass the BUILD heat map but were not admitted (2026-10-04)", "",
         "BUILD = 22 Sep 2021 to end 2023, 1 contract, after costs. A unit = family x bar size (or clock time) x session x market.",
         "Heat-map rule: at least 60 % of the menu variants positive and the median variant positive.",
         f"{len(d[d.plateau])} units pass the heat map; {int(d.build_pass.sum())} also pass every BUILD control; the other {len(nm)} are listed here "
         "and in `out/admit/near_misses.csv` (all columns). Their 2024 was NOT opened, so it is still clean for the DEEPEN round.", "",
         "## A. Units whose 2024 was opened and that were not admitted", "",
         "| unit | BUILD: variants positive / median | 2024: variants positive / median | why not admitted |", "|---|---|---|---|"]
    for uid, j in J.items():
        a = AD.get(uid)
        if a and a["admit"]:
            continue
        why = ("2024 heat map fails" if not j["pick"]["pass"] else "; ".join(a["failed"]).replace("min_trades", "too few trades (15 in BUILD + 2024; 100 needed)"))
        pen = d[d.uid == uid].penalty.iloc[0]
        L.append(f"| {uid.strip('|').replace('|', ' ')} | {pct(j['build']['share_pos'])} / {money(j['build']['median_net'])} | "
                 f"{pct(j['pick']['share_pos'])} / {money(j['pick']['median_net'])} | {why}{' — carries the 2025-26 failure penalty' if pen else ''} |")
    L += ["", "The afternoon channel breakout (donchian pm), whose old favourite failed on 2025-26, passes BUILD on NQ and ES and fails 2024 on both: "
              "the penalty was deserved.", "",
          f"## B. Units that fail ONE test only ({len(one)}): the central variant does not beat the best-of-random bar", "",
          "They beat their matched random entries (lift > 0) but the central variant's t is below what the best of a random menu reaches "
          "(95th percentile). `t gap` = central t minus the bar; the closest are first. `beats` = share of 200 random draws the central variant beats.", "",
          "| unit | variants positive | median net | central variant | trades | t | bar | t gap | lift over random | beats |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in one.to_dict("records"):
        L.append(f"| {r['uid'].strip('|').replace('|', ' ')} | {pct(r['share_pos'])} | {money(r['median_net'])} | `{r['member']}` | {int(r['m_trades'])} | "
                 f"{r['m_t']:.2f} | {r['bar']:.2f} | {r['gap_to_bar']:+.2f} | {money(r['ctrl_lift'])} | {pct(r.get('ctrl_p_beat'))} |")
    rest = nm[~nm.fail.isin(["bar", "weak_t3"])]
    names = {"c1": "loses to matched random entries", "shift": "loses to the same straddle at a random minute", "c2": "loses to the shuffled book",
             "bar": "below the best-of-random bar", "bar_c2": "below the shuffled-book bar", "weak_t3": "weak rationale needs t >= 3"}
    L += ["", f"## C. Units that fail two or more tests ({len(rest)})", "", "| failed tests | units | of which NQ / ES / GC | Level-2 variants |", "|---|---|---|---|"]
    for f, g in rest.groupby("fail"):
        b = g[g.kind == "base"]
        L.append(f"| {'; '.join(names[x] for x in f.split(','))} | {len(g)} | {(b.root == 'NQ').sum()} / {(b.root == 'ES').sum()} / {(b.root == 'GC').sum()} | "
                 f"{(g.kind == 'stage_d').sum()} |")
    L += ["", "Read with care: on NQ about 1 in 9 heat maps of RANDOM entries also passes the heat-map rule (6 of 56), and 5 of 18 random-minute "
              "straddles do. A heat-map pass on NQ alone is weak evidence; on ES and GC no random heat map passed (0 of 56 each).", ""]
    (OUT / "near_misses.md").write_text("\n".join(L))

    # ------------------------------------------------------------------ summary
    g = base.groupby(["fam", "root"]).agg(u=("uid", "size"), a=("v60", "sum"), b=("v70", "sum"), c=("v80", "sum"))
    fams = sorted(base.fam.unique())

    def cellf(f, r):
        if (f, r) not in g.index:
            return "—"
        x = g.loc[(f, r)]
        return f"{int(x.a)} / {int(x.b)} / {int(x.c)} of {int(x.u)}"

    sg = base.groupby(["sess", "root"]).agg(u=("uid", "size"), a=("v60", "sum"), b=("v70", "sum"), c=("v80", "sum"))
    st = base[base.family.str.startswith("straddle_t_")].copy()
    st["time"] = st.family.str[-4:].str.replace(r"(\d\d)(\d\d)", r"\1:\2", regex=True)
    order = ["18:00", "20:00", "00:00", "02:00", "03:00", "08:30", "09:30", "11:05", "13:30"]

    def stc(t, r):
        x = st[(st.time == t) & (st.root == r)].iloc[0]
        return f"{pct(x.share_pos)} · {money(x.median_net)}{' · PASS 60' + ('/70/80' if x.v80 else ('/70' if x.v70 else '')) if x.v60 else ''}"

    cand = int(led[led.kind == "grid"].cells.sum())
    nullc = int(led.null_cells.sum())
    val = int(led[led.stage.isin(["null_pick", "null_stress"])].null_cells.sum())
    S = ["# Edge library — admission summary (2026-10-04)", "",
         "Plain words; dollars are 1 contract after costs unless said otherwise. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec only), PICK = 2024.",
         "**BUILD and PICK were both used to choose, so neither is proof. Forward (paper) trading is still needed. 2025+ (EXAM) was not read.**", "",
         "## 1. What was tested",
         f"* 32 families, 279 runs, {cand:,} menu variants (8 stops x 4 targets x each family setting) on NQ, ES, GC; {nullc - val:,} random / shuffled control variants.",
         f"* {len(d):,} judged units (family x bar size or clock time x session x market; long/short, break/fade, fill/go judged apart): NQ {len(base[base.root == 'NQ'])} "
         f"+ {len(d[d.kind == 'stage_d'])} Level-2 filter/exit variants, ES {len(base[base.root == 'ES'])}, GC {len(base[base.root == 'GC'])}.",
         f"* Heat map passes on BUILD (>= 60 % of variants positive, median positive): {int(d.plateau.sum())} units (NQ {int(base[base.root == 'NQ'].plateau.sum())}, "
         f"ES {int(base[base.root == 'ES'].plateau.sum())}, GC {int(base[base.root == 'GC'].plateau.sum())}, Level-2 variants {int(d[d.kind == 'stage_d'].plateau.sum())}).",
         f"* Also beat matched random entries AND the best-of-random bar: **{int(d.build_pass.sum())} units**. Only these had 2024 opened (`out/admit/pick_reads.csv`).",
         "* 2024 heat map passes for 3 of the 5. After stress and the trade-count rule: **2 admitted (1 clean, 1 flagged)**. The rest: `out/near_misses.md`.", "",
         "## 2. Verdict by family and market (BUILD): units passing at 60 / 70 / 80 % of variants positive, of units judged",
         "| family | NQ | ES | GC |", "|---|---|---|---|"]
    for f in fams:
        S.append(f"| {f} | {cellf(f, 'NQ')} | {cellf(f, 'ES')} | {cellf(f, 'GC')} |")
    S += ["", "By session (same counts): " + "; ".join(
        f"**{s}** NQ {int(sg.loc[(s, 'NQ')].a)}/{int(sg.loc[(s, 'NQ')].b)}/{int(sg.loc[(s, 'NQ')].c)} of {int(sg.loc[(s, 'NQ')].u)}, "
        f"ES {int(sg.loc[(s, 'ES')].a)}/{int(sg.loc[(s, 'ES')].b)}/{int(sg.loc[(s, 'ES')].c)}, GC {int(sg.loc[(s, 'GC')].a)}/{int(sg.loc[(s, 'GC')].b)}/{int(sg.loc[(s, 'GC')].c)}"
        for s in ("eve", "asia", "london", "pre", "nyam", "mid", "pm")) + ".",
        "A heat-map pass alone is weak on NQ: random entries pass it too (section 7). mid_fade and vwap_ema_x pass nowhere that counts.", ""]
    S += (A / "summary_members.md").read_text().rstrip("\n").split("\n")
    S += ["", "## 4. Straddle at a clock time (BUILD): share of the 160 variants positive · median variant net",
          "| time ET | NQ | ES | GC |", "|---|---|---|---|"]
    for t in order:
        S.append(f"| {t}{' (weak reason)' if t in ('00:00', '11:05') else ''} | {stc(t, 'NQ')} | {stc(t, 'ES')} | {stc(t, 'GC')} |")
    S += (A / "summary_tail.md").read_text().rstrip("\n").split("\n")
    text = "\n".join(S) + "\n"
    n = text.count("\n")
    assert n <= 120, n
    (OUT / "library_summary.md").write_text(text)
    print("near_misses.md lines", len(L), "| library_summary.md lines", n)


if __name__ == "__main__":
    main()
