"""Build the "Backtest metrics" artifacts of the five prop algos: homebase/research/<name>_equity.json.

Nothing is typed by hand.  Every point is one real backtest trade; every number is computed from that
trade list or read from the research's own result files.

  nq_nyam_flex, nq_nyam_pro, nq_orb_pro, nq_pm_flex
      The NQ prop-portfolio pilot (research/prop-portfolio/2026-09-29).  The curve is the frozen HOLDOUT run
      (2025-01-01 -> 2026-09-30, tick replay at 1 NQ, $4 a contract round trip, 1 tick of slippage a side)
      that out/holdout_manifest.json names for the algo's finalist, cut to its session, resized to the desk's
      contracts, with the desk's take rule applied the way evalcore._walk_day applies it (one trade a day).
      The prop table is the pilot's own account-level scoring: out/holdout_results.json (holdout) next to
      out/holdout_validate_insample.json (the same frozen code on 2021-09-22 -> 2024-12-31).
  gc_nfp
      The NFP study (research/nfp-2026-10-02).  Every NFP day with a GC tape, replayed from the tick archive
      with the study's own nfp_lib.replay at the DESK's numbers (config: contracts, offset, SL, TP, fire /
      cancel / flat times).  The study's tables (out/summary_IS.csv, out/summary_HO.csv, its variant B) sit
      next to it in the prop table.

The desk side (contracts, takes, size tiers, half-day skip, fire time) is read from homebase.config's
shipped defaults, and the build stops if the research finalist and the desk disagree.  Three choices turn an
account rule into one continuous line; each artifact's note says its own:
  * target_take alone (nq_nyam_pro): every day is day 1 of a fresh eval, so the take is the eval target;
    target_take next to a day_take (nq_nyam_flex): the line carries the day_take only (the target level
    exists on the passing day alone and depends on the account);
  * size tiers (nq_pm_flex): the desk's size_for_profit on the line's OWN running profit, never reset;
  * skip_early_close (nq_orb_pro): the half days the research traded are dropped, as the desk skips them.

Run it with a Python that has numpy + pandas (nfp_lib needs them; the repo venv has neither):
    /usr/bin/python3 homebase/research/build_algo_metrics.py [--verify] [name ...]
--verify also imports the pilot's evalcore.py and checks every day of the four NQ ledgers against its walk.
Paths (--pilot, --nfp, --runs, --ticks, --out) default to the main checkout's research/ and tester state.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True       # this build imports the research's own modules: leave no .pyc next to them

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(REPO), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build_metrics import ledger_table, money, pct          # noqa: E402
from homebase.backtest.propsim import load_rules            # noqa: E402
from homebase.config import _defaults                       # noqa: E402
from homebase.dayrules import size_for_profit               # noqa: E402
from homebase.levels import is_early_close_skip             # noqa: E402

MAIN = Path.home() / "ramos-quant-homebase"                 # research/ and the tester state live in the main checkout
ET = ZoneInfo("America/New_York")
TICK_MICRO = 0.5                                            # $ of one NQ tick on one micro (evalcore.TICK_USD)
SESS = {"nyam": (570, 660), "mid": (660, 810), "pm": (810, 958)}     # evalcore.SESS: ET minutes [from, to)

# algo -> the pilot finalist it was built from (out/holdout_manifest.json ids)
NQ = {
    "nq_nyam_flex": dict(kind="eval", fin="lucid:single", firm="lucid", account="LucidFlex 50K eval"),
    "nq_nyam_pro": dict(kind="eval", fin="lucidpro_nodll:single", firm="lucidpro_nodll",
                        account="LucidPro 50K eval, no DLL"),
    "nq_orb_pro": dict(kind="funded", fin="pro_nodll#1", firm="lucidpro_nodll", account="LucidPro 50K funded, no DLL"),
    "nq_pm_flex": dict(kind="funded", fin="flex#1", firm="lucid", account="LucidFlex 50K funded"),
}
GC = "gc_nfp"
GC_RULES = "lucid-pro-50k-no-dll@2026-09-27b"               # the eval the NFP study sized for ($3,000 / $2,000)
GC_FEE_SIDE = 2.30                                          # $ a side per GC contract (Lucid; the study's verify runs)
GC_STUDY_B = "B_plain_4GC_off2pt_SL2000"                    # results.md variant B = the desk's stop, fired 08:30:00


def usd0(v: float) -> str:
    return ("-$" if v < 0 else "$") + f"{abs(v):,.0f}"


def both(f, ho, ins) -> str:
    """'holdout / in-sample' with one formatter; a missing value prints as n/a."""
    return " / ".join("n/a" if v is None else f(v) for v in (ho, ins))


# ------------------------------------------------------------------ NQ: the pilot's holdout ledgers

def cost(n: int) -> float:
    """evalcore.cost: round-trip commission of n micros, whole minis at $4.00, the rest $1.00 each."""
    return (n // 10) * 4.0 + (n % 10) * 1.0


def trade_pnl(g: float, mfe: float, n: int, day_take: float = 0.0, target: float = 0.0):
    """One trade a day, n micros -> ($ P&L, took?).  evalcore._walk_day with nothing else open:
    p = n * gross/10 - cost; the trade's best point = max(n * MFE/10 - cost, p).  day_take X fires when the
    best point reaches X and books X - 1 tick per micro; target_take L fires at L + 1 tick per micro and books
    exactly L.  With both on, the lower trigger wins."""
    c = cost(n)
    p = n * g / 10.0 - c
    lv = ([(day_take, day_take - TICK_MICRO * n)] if day_take else []) + \
         ([(target + TICK_MICRO * n, target)] if target else [])
    if lv:
        trig, fin = min(lv)
        if max(n * mfe / 10.0 - c, p) >= trig:
            return fin, True
    return p, False


def load_trades(run_dir: Path, sess: str, start: str, end: str) -> list:
    """The run's trades of one session, per 1 NQ, in entry order: dicts date / g / mfe / mae (evalcore.load)."""
    rows = json.loads((run_dir / "trades.json").read_text())
    rows = rows if isinstance(rows, list) else rows.get("trades", [])
    a, b = SESS[sess]
    out = []
    for x in rows:
        t = dt.datetime.fromtimestamp(int(x["entry_ms"]) / 1000, ET)
        if not (a <= t.hour * 60 + t.minute < b and start <= x["date"] <= end):
            continue
        q = max(1.0, float(x.get("qty") or 1))
        g = float(x["gross"]) / q
        mfe = abs(float(x["mfe_usd"])) / q if x.get("mfe_usd") is not None else 0.0
        mae = abs(float(x["mae_usd"])) / q if x.get("mae_usd") is not None else max(0.0, -g)
        out.append(dict(date=x["date"], te=int(x["entry_ms"]), g=g, mfe=max(mfe, g, 0.0), mae=mae))
    out.sort(key=lambda r: r["te"])
    days = [r["date"] for r in out]
    if len(set(days)) != len(days):
        raise SystemExit(f"{run_dir.name}/{sess}: more than one trade a day -- this build only walks one")
    return out


def holdout_runs(pilot: Path) -> dict:
    runs = {}
    for ln in (pilot / "jobs.jsonl").read_text().splitlines():
        if ln.strip():
            j = json.loads(ln)
            if j.get("stage") == "holdout" and j.get("status") == "done":
                runs[j["key"]] = j["id"]
    return runs


def build_nq(name: str, a: argparse.Namespace) -> dict:
    spec, cfg = NQ[name], _defaults().strategies[name]
    man = json.loads((a.pilot / "out/holdout_manifest.json").read_text())
    res = json.loads((a.pilot / "out/holdout_results.json").read_text())
    ins = json.loads((a.pilot / "out/holdout_validate_insample.json").read_text())
    if res["mode"] != "holdout" or ins["mode"] != "insample":
        raise SystemExit("holdout_results.json / holdout_validate_insample.json are not the holdout / in-sample scoring")
    eval_ = spec["kind"] == "eval"
    fin = (man["finalists"] if eval_ else man["funded"])[spec["fin"]]
    mem = fin["members"][0] if eval_ else fin
    if eval_ and len(fin["members"]) != 1:
        raise SystemExit(f"{spec['fin']}: not a single-strategy finalist")
    cid, sess, micros, rules = mem["cfg"], mem["sess"], int(mem["micros"]), fin["rules"]
    if eval_ and fin["firm"] != spec["firm"]:
        raise SystemExit(f"{spec['fin']}: scored under {fin['firm']}, not {spec['firm']}")
    rule_file = load_rules(man["firms"][spec["firm"]]["rules_id"])
    mll = float(rule_file["trailing_mll"])
    sec = "eval" if eval_ else "funded"
    HO, IS = res[sec][spec["fin"]], ins[sec][spec["fin"]]          # the same scorer on the holdout / in-sample

    # the desk must be the research finalist: source line, contracts, take
    if cid not in cfg.metrics["source"]:
        raise SystemExit(f"{name}: the desk source line does not name {cid}")
    if cfg.qty * 10 != micros or cost(micros) != cfg.qty * cfg.fee_rt:
        raise SystemExit(f"{name}: desk {cfg.qty} NQ at ${cfg.fee_rt} vs research {micros} micros")
    if float(cfg.day_take) != float(rules.get("day_take") or 0) or bool(cfg.target_take) != bool(rules.get("target_take")):
        raise SystemExit(f"{name}: desk take rules differ from the finalist's {rules}")
    if cfg.size_tiers:
        sc = rule_file["scaling_micros"]
        if [[lo, q * 10] for lo, q in cfg.size_tiers] != [[0, sc["start"]], [1000, sc["at_1000"]], [2000, sc["at_2000"]]]:
            raise SystemExit(f"{name}: desk size tiers differ from the rule file's scaling")

    h0, h1 = man["holdout"]["start"], man["holdout"]["end"]
    run = holdout_runs(a.pilot)[man["configs"][cid]["job_key"]]
    trs = load_trades(a.runs / run, sess, h0, h1)
    n_res = HO["walk"]["executed"] if eval_ else HO["trades"]
    if len(trs) != n_res:
        raise SystemExit(f"{name}: {len(trs)} trades loaded, the pilot scored {n_res}")

    # target_take on a 21-month ledger: every day is day 1 of a fresh eval when the take is the target alone
    # (Pro: $3,000 on day 1).  With a day_take (Flex) the target level only exists on the passing day, so the
    # ledger carries the day_take; the prop table carries the eval.
    target = float(rule_file["eval_target"]) if (cfg.target_take and not cfg.day_take) else 0.0
    day_take = float(cfg.day_take)
    if eval_:                         # the pilot's own day series for this finalist (walk at the firm cap, day_take on)
        net = sum(trade_pnl(t["g"], t["mfe"], micros, float(rules.get("day_take") or 0))[0] for t in trs)
        if abs(net - HO["series"]["net"]) > 0.01:
            raise SystemExit(f"{name}: ledger net {net} != the pilot's series net {HO['series']['net']}")

    skipped = [t["date"] for t in trs if cfg.skip_early_close
               and is_early_close_skip(cfg.symbol, dt.date.fromisoformat(t["date"]), cfg.flat_et)]
    trs = [t for t in trs if t["date"] not in skipped]

    dates, pnl, sizes, takes, deep = [], [], [], 0, 0
    cum = 0.0
    for t in trs:
        qty = size_for_profit(cfg.size_tiers, cum, cfg.qty) if cfg.size_tiers else cfg.qty
        p, took = trade_pnl(t["g"], t["mfe"], qty * 10, day_take, target)
        cum = round(cum + p, 2)
        dates.append(t["date"]); pnl.append(round(p, 2)); sizes.append(qty)
        takes += took
        deep += (qty * 10 * t["mae"] / 10.0 + cost(qty * 10)) >= mll
    if a.verify:
        verify_nq(name, a, run, sess, micros, rules, trs, pnl, sizes, target, (h0, h1))

    n = len(pnl)
    points, c = [], 0.0
    for d, p in zip(dates, pnl):
        c = round(c + p, 2)
        points.append([d, c])
    losses = [p for p in pnl if p < 0]
    take_txt = (f"${target:,.0f} (the eval target)" if target else f"${day_take:,.0f} net")
    T = [["As traded", "contracts", (" / ".join(str(q) for _, q in cfg.size_tiers) + " NQ by profit") if cfg.size_tiers
          else f"{cfg.qty} NQ"],
         ["As traded", "daily take", take_txt],
         ["As traded", "take days", f"{takes} of {n} ({pct(takes / n)})"],
         ["As traded", "loss days", f"{len(losses)} of {n} ({pct(len(losses) / n)})"],
         ["As traded", "avg loss day", money(sum(losses) / len(losses)) if losses else "n/a"],
         ["As traded", f"open loss past ${mll:,.0f}", f"{pct(deep / n)} of trades"]]
    if cfg.size_tiers:
        qs = sorted({q for _, q in cfg.size_tiers})
        T.append(["As traded", "days at " + " / ".join(str(q) for q in qs) + " NQ",
                  " / ".join(str(sizes.count(q)) for q in qs)])
        for q in qs:
            T.append(["As traded", f"net at a fixed {q} NQ",
                      money(sum(trade_pnl(t["g"], t["mfe"], q * 10, day_take, target)[0] for t in trs))])
    if skipped:
        T.append(["As traded", "half days left out", str(len(skipped))])
    T += ledger_table(dates, pnl)

    prim = HO["primary"]
    if prim != "realized" or IS["primary"] != prim:
        raise SystemExit(f"{name}: the pilot's primary breach model is {prim}, this text says closed balance")
    fire, flat = cfg.fire_et[:5], cfg.flat_et
    size_txt = (f"{cfg.size_tiers[0][1]} NQ, {cfg.size_tiers[1][1]} once this line is ${cfg.size_tiers[1][0]:,.0f} up, "
                f"{cfg.size_tiers[2][1]} from ${cfg.size_tiers[2][0]:,.0f} (the desk's tiers on this line's own profit)"
                if cfg.size_tiers else f"{cfg.qty} NQ")
    if target:
        take_note = (f"Every day is traded like day 1 of a new eval: when price reaches the ${target:,.0f} target "
                     f"the day ends at exactly ${target:,.0f}")
    else:
        qs = sorted({q for _, q in cfg.size_tiers}) or [cfg.qty]
        take_note = (f"The day ends at +${day_take:,.0f} net when price gets there (booked "
                     + " / ".join(f"${day_take - TICK_MICRO * q * 10:,.0f}" for q in qs) + " at "
                     + " / ".join(str(q) for q in qs) + " NQ: one tick of slippage)")
    note = (f"One trade a day at {fire} ET, {size_txt}. {take_note}; otherwise the trade ends at its stop, "
            f"its far target or the {flat} flat. ")
    if skipped:
        note += (f"{len(skipped)} half days the research traded are left out, the desk skips them "
                 f"({', '.join(skipped)}). ")
    if eval_:
        h, i = HO["headline"], IS["headline"]
        if day_take and cfg.target_take:
            note += ("On the day an eval can pass, the desk lowers the take to what is still missing; that depends on "
                     "the account, so this line does not show it. ")
        note += ("This 21-month line is NOT how an eval is used: an eval ends at its first pass or bust, a few days "
                 "in. The prop table below is the number that matters.")
        fall = (f"pass within 5 days falls from {pct(h['p5'])} to {pct(HO['intraday']['p5'])}")
        k = next(d for d, v in enumerate(HO["by_day"][prim]["pass_by_day"], 1) if v > 0)
        first_pass = (f"Under this account's rules no account passes before day {k}." if k > 1
                      else "It can pass on day 1.")
        P = [["account", spec["account"]],
             ["numbers shown", "holdout / in-sample"],
             ["pass within 5 days", both(pct, h["p5"], i["p5"])],
             ["pass on day 1", both(pct, h["p1"], i["p1"])],
             ["pass within 3 days", both(pct, h["p3"], i["p3"])],
             ["bust within 5 days", both(pct, h["bust5"], i["bust5"])],
             ["median days to pass", both(lambda v: f"{v:g}", h["med_days"], i["med_days"])],
             ["pass, open losses count", both(pct, HO["intraday"]["p5"], IS["intraday"]["p5"])],
             ["edge over random entries", both(lambda v: f"{100 * v:+.1f} pts", HO["lift"][prim]["lift"],
                                               IS["lift"][prim]["lift"])],
             ["account starts tested", both(str, HO["n_starts"], IS["n_starts"])]]
    else:
        h, i = HO["headline"], IS["headline"]
        note += (f"Over these 21 months the line ends at {usd0(points[-1][1])}. A funded account does not ride the "
                 f"whole line: one loss day bigger than ${mll:,.0f} closes it. What it earns is the payouts "
                 "taken before that day: the prop table below is the number that matters.")
        fall = (f"the dollars to the trader in 40 days fall from {usd0(h['e_net_40'])} to "
                f"{usd0(HO['intraday']['e_net_40'])}")
        P = [["account", spec["account"]],
             ["numbers shown", "holdout / in-sample"],
             ["payout within 20 days", both(pct, h["p_pay_20"], i["p_pay_20"])],
             ["payout within 40 days", both(pct, h["p_pay_40"], i["p_pay_40"])],
             ["median days to 1st payout", both(lambda v: f"{v:g}", h["med_days_first"], i["med_days_first"])],
             ["$ to trader in 40 days", both(usd0, h["e_net_40"], i["e_net_40"])],
             ["bust before 1st payout", both(pct, h["p_bust_pre_first"], i["p_bust_pre_first"])],
             ["bust within 60 days", both(pct, h["p_bust_any"], i["p_bust_any"])],
             ["$ in 40 d, open losses count", both(usd0, HO["intraday"]["e_net_40"], IS["intraday"]["e_net_40"])],
             ["vs random entries, 40 d", both(lambda v: ("+" if v >= 0 else "-") + usd0(abs(v)),
                                              HO["lift"]["lift_e40"], IS["lift"]["lift_e40"])],
             ["account starts tested", both(str, HO["n_starts"], IS["n_starts"])]]
    table_note = (
        f"Every number above is computed from this trade list: the research's frozen holdout run ({cid}, {sess} "
        f"session, tick replay at 1 NQ, $4 a contract round trip, 1 tick of slippage a side), resized to the desk's "
        f"contracts with the take applied the way the research's rule walk does. \"Open loss past ${mll:,.0f}\" "
        f"counts the research trade's full path, so on a take day the take may have come first. "
        f"Every Lucid number assumes only CLOSED balance counts against the ${mll:,.0f} max loss. If open "
        f"losses count, {fall} (holdout). On file: {cfg.metrics['caveat']}.")
    prop_note = (
        f"The pilot's own account numbers for a {spec['account']}: a new account started on every session, "
        f"{HO['window'][0]} to {HO['window'][1]} (holdout) and {IS['window'][0]} to {IS['window'][1]} (in-sample), "
        f"closed-balance breach. Rules and sizes were frozen before the holdout was opened, but this algo was "
        f"picked among the pilot's {len(man['finalists']) + len(man['funded'])} finalists after the holdout was "
        f"scored: read the holdout column as lightly used, not as a clean exam. "
        + (first_pass if eval_ else
           f"Payout requested once the cheque is ${fin['policy']:,.0f}; dollars are after the 90/10 split."))
    return {
        "label": f"Tick replay · holdout {dates[0]} → {dates[-1]} · {n} trades · "
                 + (f"{min(sizes)}-{max(sizes)} NQ" if cfg.size_tiers else f"{cfg.qty} NQ"),
        "note": note,
        "points": points,
        "table": T,
        "table_note": table_note,
        "prop_title": "PROP ACCOUNT — THE PILOT'S FROZEN HOLDOUT SCORING",
        "prop_table": P,
        "prop_note": prop_note,
    }


def verify_nq(name, a, run, sess, micros, rules, trs, pnl, sizes, target, window) -> None:
    """Every day of the ledger against the pilot's own evalcore walk (numpy; imports the pilot's code)."""
    if str(a.pilot) not in sys.path:
        sys.path.insert(0, str(a.pilot))
    import evalcore as E                                    # noqa: PLC0415
    from homebase.backtest.tape import TapeStore            # noqa: PLC0415
    cal = [d.isoformat() for d in TapeStore().sessions("NQ", dt.date.fromisoformat(window[0]),
                                                        dt.date.fromisoformat(window[1]))]
    P = E.build({"members": [{"src": str(a.runs / run), "sess": sess, "micros": micros}],
                 "start": window[0], "end": window[1]}, calendar=cal, holdout=True)
    rl = E.norm_rules(rules)
    walks = {q: E.walk(P, q * 10, rl, day_take=float(rules.get("day_take") or 0)) for q in set(sizes)}
    pos = {d: i for i, d in enumerate(P.iso)}
    bad = 0
    for t, p, q in zip(trs, pnl, sizes):
        i = pos[t["date"]]
        ref = walks[q].rewalk(i, target)[0] if target else float(walks[q].tot[i])
        bad += abs(ref - p) > 0.005
    print(f"  verify {name}: {len(pnl)} days against evalcore.walk, {bad} differ")
    if bad:
        raise SystemExit(f"{name}: the ledger differs from evalcore's walk on {bad} days")


# ------------------------------------------------------------------ GC: the NFP study at the desk's numbers

def build_gc(a: argparse.Namespace) -> dict:
    cfg = _defaults().strategies[GC]
    if str(a.nfp) not in sys.path:
        sys.path.insert(0, str(a.nfp))
    import numpy as np                                      # noqa: PLC0415
    import nfp_lib as N                                     # noqa: PLC0415
    N.ARCH = a.ticks
    N.CAL = REPO / "homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv"
    rule_file = load_rules(GC_RULES)
    target, mll = float(rule_file["eval_target"]), float(rule_file["trailing_mll"])
    s = N.SPEC[cfg.symbol]
    pv, comm = s["pv"] * cfg.qty, 2 * GC_FEE_SIDE * cfg.qty

    def at(d, hms):
        p = [int(x) for x in hms.split(":")] + [0]
        return N.ns(d, p[0], p[1], p[2])

    rows, missing = [], []
    for d in [d for d, tag in N.events() if tag == "NFP"]:
        tape = N.load_event((cfg.symbol, d))[2]
        if tape is None:
            missing.append(d.isoformat())
            continue
        ts, px = tape
        res = {}
        for key, fire, live in (("desk", at(d, cfg.fire_et), at(d, cfg.fire_et)),                  # orders rest from the fire
                                ("study", at(d, "08:30:00"), at(d, "08:30:00") + N.PLACEMENT_NS)):  # the study's fire
            i = int(np.searchsorted(ts, fire, side="left")) - 1
            if i < 0:
                raise SystemExit(f"{GC}: no print before the fire on {d}")
            t2, p2 = ts[i:], px[i:]
            P = dict(ts=t2, px=p2, anchor=float(p2[0]), t_fire=fire,
                     i0=int(np.searchsorted(t2, live, side="left")),
                     i_c=int(np.searchsorted(t2, at(d, cfg.cancel_et), side="left")),
                     i_f=int(np.searchsorted(t2, at(d, cfg.flat_et), side="right")))
            # house fill model M1: the stop entry pays the gap + 1 tick, the stop + 1 tick, the target is a limit
            net, why = N.replay(P, cfg.offset_pts, cfg.sl_pts, cfg.tp_pts, s["tick"], pv, comm, 1, 1, False)
            res[key] = (round(float(net), 2), why)
        rows.append((d.isoformat(), res["desk"], res["study"]))

    dates = [r[0] for r in rows]
    pnl = [r[1][0] for r in rows]
    n = len(rows)
    points, c = [], 0.0
    for d, p in zip(dates, pnl):
        c = round(c + p, 2)
        points.append([d, c])
    split = N.HO_START.isoformat()
    first_ho = next(i for i, d in enumerate(dates) if d >= split)

    def rate(col, part, test):                # col 1 = the desk's fire, 2 = the study's; part "HO" = 2025+
        x = [r[col][0] for r in rows if (r[0] >= split) == (part == "HO")]
        return sum(1 for v in x if test(v)) / len(x)

    is_pass, is_bust = (lambda v: v >= target), (lambda v: v <= -mll)
    why = [r[1][1] for r in rows]
    flips = [r[0] for r in rows if (is_pass(r[1][0]), is_bust(r[1][0])) != (is_pass(r[2][0]), is_bust(r[2][0]))]

    def study(part, set_, col):
        f = a.nfp / f"out/summary_{part}.csv"       # IS = the whole grid; HO = the 5 frozen finalists, by name
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                b = (r.get("name") == GC_STUDY_B) if part == "HO" else (
                    r["root"] == "GC" and r["arm"] == "const" and r["unit"] == "4xGC" and r["offmode"] == "pts"
                    and float(r["off"]) == cfg.offset_pts and float(r["sl_usd"]) == mll
                    and float(r["tp_usd"]) == target)
                if b and r["model"] == "M1" and r["set"] == set_:
                    return float(r[col])
        raise SystemExit(f"{GC}: variant B ({set_}, M1) not found in {f}")

    T = [["As traded", "contracts", f"{cfg.qty} {cfg.symbol}"],
         ["As traded", "fire", f"{cfg.fire_et} ET"],
         ["As traded", "bracket", f"±{cfg.offset_pts:.1f} / SL {cfg.sl_pts:.1f} / TP {cfg.tp_pts:.1f}"],
         ["As traded", "TP / SL / time / no fill",
          " / ".join(str(why.count(k)) for k in ("TP", "SL", "FLAT", "NOFILL"))],
         ["As traded", f"pass (net ≥ ${target:,.0f})",
          f"{sum(map(is_pass, pnl))} of {n} ({pct(sum(map(is_pass, pnl)) / n)})"],
         ["As traded", f"bust (net ≤ -${mll:,.0f})",
          f"{sum(map(is_bust, pnl))} of {n} ({pct(sum(map(is_bust, pnl)) / n)})"],
         ["As traded", "NFP days with no GC tape", ", ".join(missing) or "none"]]
    T += ledger_table(dates, pnl, period="year", sharpe=False)

    P = [["account", "LucidPro 50K eval, one event"],
         ["numbers shown", "2025-26 / 2021-24"],
         ["events", both(str, n - first_ho, first_ho)],
         [f"pass, fired {cfg.fire_et}", both(pct, rate(1, "HO", is_pass), rate(1, "IS", is_pass))],
         [f"bust, fired {cfg.fire_et}", both(pct, rate(1, "HO", is_bust), rate(1, "IS", is_bust))],
         ["pass, fired 08:30:00", both(pct, rate(2, "HO", is_pass), rate(2, "IS", is_pass))],
         ["bust, fired 08:30:00", both(pct, rate(2, "HO", is_bust), rate(2, "IS", is_bust))],
         ["study B pass, NFP", both(pct, study("HO", "NFP", "p_win"), study("IS", "NFP", "p_win"))],
         ["study B bust, NFP", both(pct, study("HO", "NFP", "p_bust1"), study("IS", "NFP", "p_bust1"))],
         ["study B pass, NFP + CPI", both(pct, study("HO", "ALL", "p_win"), study("IS", "ALL", "p_win"))],
         ["study B bust, NFP + CPI", both(pct, study("HO", "ALL", "p_bust1"), study("IS", "ALL", "p_bust1"))]]
    note = (
        f"One trade per NFP release, {cfg.qty} {cfg.symbol}: stop entries {cfg.offset_pts:.1f} above and below the last "
        f"price before {cfg.fire_et} ET, stop {cfg.sl_pts:.1f}, target {cfg.tp_pts:.1f}, unfilled cancelled {cfg.cancel_et}, "
        f"flat {cfg.flat_et}. Events 1 to {first_ho} ({dates[0]} to {dates[first_ho - 1]}) are the window the "
        f"numbers were picked on. 2025 starts at event {first_ho + 1} ({dates[first_ho]}): those {n - first_ho} "
        f"events had already been used on this strategy family, so they are a consistency check, not a clean exam. "
        f"The line only adds the events up: each eval takes ONE event, a win passes it and a stop-out ends it. "
        f"The prop table below is the number that matters.")
    table_note = (
        f"Every number above is computed from this event list, replayed from the tick archive with the study's own "
        f"engine at the desk's numbers: first-print fills, 1 tick of slippage on the entry and on the stop, "
        f"${GC_FEE_SIDE:.2f} a side per contract. Bust = the trade closes at or below -${mll:,.0f} (closed balance); "
        f"the stop sits at the limit, so every stop-out is a bust and an open-loss rule would change nothing here. "
        f"A real fill at the release can be several points worse than the first print. "
        f"On file: {cfg.metrics['caveat']}.")
    study_tp = N.bracket(pv, N.COMM_MINI * cfg.qty, s["tick"], mll, target)[1]     # the study's own target, in points
    prop_note = (
        f"Per event, for one eval (${target:,.0f} target, ${mll:,.0f} max loss). \"Fired {cfg.fire_et}\" is this "
        f"ledger, the way the desk fires. \"Fired 08:30:00\" is the same bracket placed at the release, the way the "
        f"study fired"
        + (f": the earlier anchor changes pass or bust on {len(flips)} of {n} events ({', '.join(flips)})" if flips else "")
        + f". \"Study B\" is the study's own table (results.md, variant B: same stop, target {study_tp:.1f}, fired "
          f"08:30:00, its first events dropped as warm-up); NFP + CPI is the pooled set the study selected on.")
    return {
        "label": f"Tick replay · NFP days {dates[0]} → {dates[-1]} · {n} events · {cfg.qty} {cfg.symbol}",
        "note": note,
        "points": points,
        "table": T,
        "table_note": table_note,
        "prop_title": "ONE EVAL, ONE EVENT — PASS / BUST PER NFP",
        "prop_table": P,
        "prop_note": prop_note,
    }


# ------------------------------------------------------------------ main

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("names", nargs="*", help=f"algos to build (default: all of {', '.join(list(NQ) + [GC])})")
    ap.add_argument("--pilot", type=Path, default=MAIN / "research/prop-portfolio/2026-09-29")
    ap.add_argument("--nfp", type=Path, default=MAIN / "research/nfp-2026-10-02")
    ap.add_argument("--runs", type=Path, default=MAIN / "homebase/.state/tester/runs")
    ap.add_argument("--ticks", type=Path, default=Path.home() / "futures_ticks")
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--verify", action="store_true", help="check the NQ ledgers against the pilot's evalcore walk")
    a = ap.parse_args(argv)
    for name in a.names or list(NQ) + [GC]:
        if name not in NQ and name != GC:
            raise SystemExit(f"unknown algo {name!r}")
        art = build_gc(a) if name == GC else build_nq(name, a)
        texts = [art[k] for k in ("label", "note", "table_note", "prop_title", "prop_note")]
        if any("<" in t for t in texts + [x for r in art["table"] + art["prop_table"] for x in r]):
            raise SystemExit(f"{name}: a text holds '<', which the page would read as markup")   # openRes writes them as they are
        (a.out / f"{name}_equity.json").write_text(json.dumps(art) + "\n")
        net = art["points"][-1][1]
        dd = next(r[2] for r in art["table"] if r[1] == "max drawdown")
        print(f"{name}: {len(art['points'])} trades, net {money(net)}, max drawdown {dd}")
        for k, v in art["prop_table"]:
            print(f"    {k:34} {v}")


if __name__ == "__main__":
    main()
