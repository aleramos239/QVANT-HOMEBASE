"""The stack's in-sample portfolio study (STACK.md / stack.json: 8 picked versions, NY sessions) -> STACK_STUDY.md.
Reads the in-sample stores only (runs_wf/<store>/is), never a test month. 1 contract a leg, the store's own costs.

    stack_study.py      writes STACK_STUDY.md next to this file"""
from __future__ import annotations

import datetime as dt
import heapq
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).resolve().parent
EL = HERE.parents[2]
sys.path[:0] = [str(EL), str(EL / "engine")]
os.environ.setdefault("HOMEBASE_WF_LAST", "2026-05")
import library as LB  # noqa: E402

ET = ZoneInfo("America/New_York")
NY = [LB.SESS_CODE[s] for s in ("nyam", "mid", "pm")]
ACCOUNTS = 5
SHORT = {"orb_confirm": "orbc long 5m", "rvol_break": "rvol break", "displace": "displace", "donchian": "donchian",
         "orb_vwap_pb": "orb vwap pb", "win_break": "win break 9:45", "onr_orb": "onr orb", "noise_band": "noise long 5m"}


def load():
    st = json.loads((HERE / "stack.json").read_text())["stack"]
    legs, T, days = [], [], None
    for li, s in enumerate(st):
        u = LB.load_unit("is", EL / "runs_wf" / s["store"])
        assert u["meta"]["wf"] == "is"                                   # in-sample store only
        d = u["meta"]["days"]
        days = d if days is None else days
        assert d == days, s["store"]
        x = LB.unit_cell(u, s["box"])
        k = np.isin(x["sess"], NY)
        assert int(k.sum()) == s["trades"] and abs(float(x["net"][k].sum()) - s["net"]) < 1, s["store"]   # = stack.json
        for i in np.flatnonzero(k):
            e = int(x["entry_ms"][i])
            T.append({"leg": li, "date": dt.date.fromordinal(int(x["date"][i])).isoformat(), "in": e, "out": e + int(x["dur_s"][i]) * 1000,
                      "net": float(x["net"][i]), "side": int(x["side"][i]), "reason": LB.REASONS[int(x["reason"][i])],
                      "hour": dt.datetime.fromtimestamp(e / 1000, ET).hour})
        legs.append({**s, "name": SHORT.get(s["family"], s["family"])})
    T.sort(key=lambda t: (t["in"], t["leg"]))
    return legs, T, days


def dd_of(x):
    eq = np.cumsum(x)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    dd = eq - peak
    j = int(dd.argmin())
    i = int(np.flatnonzero(eq[: j + 1] == peak[j])[0]) + 1 if peak[j] > 0 else 0
    return float(dd.min()), i, j


def underwater_days(daily):
    eq, peak, run, best = 0.0, 0.0, 0, 0
    for v in daily:
        eq += v
        if eq >= peak:
            peak, run = eq, 0
        else:
            run += 1
            best = max(best, run)
    return best


def streak(vals):
    best = cur = 0
    for v in vals:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return best


def accounts_sim(T, n):
    """Time order; a signal is skipped only when n positions are open (a position frees its account at its exit)."""
    open_, kept, skipped = [], [], []
    for t in T:
        while open_ and open_[0] <= t["in"]:
            heapq.heappop(open_)
        if len(open_) >= n:
            skipped.append(t)
        else:
            heapq.heappush(open_, t["out"])
            kept.append(t)
    return kept, skipped


def side_clusters(T):
    """For each trade: the number of distinct legs open on its side at its entry (itself included)."""
    out = []
    for t in T:
        legs = {u["leg"] for u in T_by_day[t["date"]] if u["side"] == t["side"] and u["in"] <= t["in"] < u["out"]}
        out.append(len(legs | {t["leg"]}))
    return np.array(out)


def ny_session_days():
    """NY session (09:30-16:00 ET) high, low and a mid-price move (first 5m bar mid -> last 5m bar mid) per date, from the 5m h/l cache."""
    z = np.load(EL / "engine" / "cache" / "bars5m_NQ.npz")
    out = {}
    for di, d in enumerate(z["dates"]):
        a, b = int(z["off"][di]), int(z["off"][di + 1])
        ends = z["end"][a:b] // 10**6
        hm = np.array([(lambda t: t.hour * 60 + t.minute)(dt.datetime.fromtimestamp(e / 1000, ET)) for e in ends])
        k = (hm > 570) & (hm <= 960)
        if k.sum() < 60:
            continue
        h, l = z["h"][a:b][k], z["l"][a:b][k]
        mid = (h + l) / 2
        out[str(d)] = {"rng": float(h.max() - l.min()), "move": float(mid[-1] - mid[0])}
    return out


def money(v, d=0):
    return f"-${abs(v):,.{d}f}" if v < 0 else f"${v:,.{d}f}"


def pct(a, b):
    return f"{100 * a / b:.1f} %" if b else "-"


def main():
    global T_by_day
    legs, T, days = load()
    nd = len(days)
    T_by_day = defaultdict(list)
    for t in T:
        T_by_day[t["date"]].append(t)
    net = np.array([t["net"] for t in T])
    daily = np.array([sum(t["net"] for t in T_by_day[d]) for d in days])
    ntr = np.array([len(T_by_day[d]) for d in days])
    traded = ntr > 0
    L = ["# The stack, in-sample: a day-by-day study (8 picked versions, NY sessions, 1 contract each)", "",
         f"Read from the in-sample stores only (runs_wf/<store>/is: {nd} in-sample days, {days[0]} .. {days[-1]}; no test month). "
         f"Script: stack_study.py. Every leg's trade count and net match stack.json. Nets are after the store's costs, 1 full NQ "
         f"contract a leg, no extra tick.", "",
         "## The legs", "", "| # | Leg | Trades | Net | Avg | Win | Long share | Avg hold | Exit: target / stop / time-or-close |",
         "|---|---|---|---|---|---|---|---|---|"]
    for li, g in enumerate(legs):
        x = [t for t in T if t["leg"] == li]
        n = np.array([t["net"] for t in x])
        rs = defaultdict(int)
        for t in x:
            rs[t["reason"]] += 1
        hold = np.mean([(t["out"] - t["in"]) / 60000 for t in x])
        L.append(f"| {li + 1} | {g['name']} ({g['box']}) | {len(x)} | {money(n.sum())} | {money(n.mean())} | {pct((n > 0).sum(), len(n))} | "
                 f"{pct(sum(t['side'] > 0 for t in x), len(x))} | {hold:.0f} min | {pct(rs['tp'], len(x))} / {pct(rs['sl'], len(x))} / "
                 f"{pct(len(x) - rs['tp'] - rs['sl'], len(x))} |")
    L.append(f"| | **Stack** | **{len(T)}** | **{money(net.sum())}** | **{money(net.mean())}** | **{pct((net > 0).sum(), len(net))}** | "
             f"{pct(sum(t['side'] > 0 for t in T), len(T))} | {np.mean([(t['out'] - t['in']) / 60000 for t in T]):.0f} min | |")

    # (a) trades a day + per hour
    b = [("0 (data-gap days)", ntr == 0), ("1-4", (ntr >= 1) & (ntr <= 4)), ("5-10", (ntr >= 5) & (ntr <= 10)), (">10", ntr > 10)]
    L += ["", "## (a) Trades a day", "",
          f"Average {ntr.mean():.2f} a day, median {np.median(ntr):.0f}, most {ntr.max()} (on {days[int(ntr.argmax())]}).", "",
          "| Trades that day | Days | Share of days | Net of those days | Avg day |", "|---|---|---|---|---|"]
    for lab, m in b:
        L.append(f"| {lab} | {m.sum()} | {pct(m.sum(), nd)} | {money(daily[m].sum())} | {money(daily[m].mean()) if m.any() else '-'} |")
    L += ["", "Entries by hour (ET):", "", "| Hour | Trades | Share | Net | Avg trade | Win |", "|---|---|---|---|---|---|"]
    for h in sorted({t["hour"] for t in T}):
        n = np.array([t["net"] for t in T if t["hour"] == h])
        L.append(f"| {h:02d}:00 | {len(n)} | {pct(len(n), len(T))} | {money(n.sum())} | {money(n.mean())} | {pct((n > 0).sum(), len(n))} |")

    # (b) daily net
    dd, i0, i1 = dd_of(daily)
    tdd, _, _ = dd_of(np.array([t["net"] for t in sorted(T, key=lambda t: t["out"])]))
    td = daily[traded]
    top = np.argsort(td)[::-1][: round(0.1 * len(td))]
    L += ["", "## (b) Daily net (1 contract a leg)", "",
          f"On the {traded.sum()} days with a trade: average {money(td.mean())}, spread (sd) {money(td.std(ddof=1))}, "
          f"{pct((td > 0).sum(), len(td))} of them positive.", "",
          "| Percentile | 5 % | 10 % | 25 % | 50 % | 75 % | 90 % | 95 % |", "|---|---|---|---|---|---|---|---|",
          "| Day net | " + " | ".join(money(np.percentile(td, p)) for p in (5, 10, 25, 50, 75, 90, 95)) + " |", "",
          "| Risk number | Value |", "|---|---|",
          f"| Max drawdown, daily closes | {money(dd)} ({days[i0] if i0 < nd else days[0]} .. {days[i1]}) |",
          f"| Max drawdown, trade by trade (exit order) | {money(tdd)} |",
          f"| Longest losing streak (trading days in a row below 0) | {streak(td)} days |",
          f"| Longest losing streak (trades in a row below 0, entry order) | {streak(net)} trades |",
          f"| Longest time under a high (days) | {underwater_days(daily)} days |",
          f"| Worst day / best day | {money(td.min())} / {money(td.max())} |",
          f"| The best 10 % of trading days ({len(top)}) | {money(td[top].sum())} = {pct(td[top].sum(), td.sum())} of the net; "
          f"the other 90 % {money(np.delete(td, top).sum())} |", "",
          "The equity line joins the in-sample months only (each block's test month is left out), so drawdowns, streaks and "
          "'days under a high' run across those gaps.", "",
          "Worst 10 days:", "", "| Date | Net | Trades | Legs that traded | Longs / shorts |", "|---|---|---|---|---|"]
    for j in np.argsort(daily)[:10]:
        x = T_by_day[days[j]]
        L.append(f"| {days[j]} | {money(daily[j])} | {len(x)} | {len({t['leg'] for t in x})} | "
                 f"{sum(t['side'] > 0 for t in x)} / {sum(t['side'] < 0 for t in x)} |")

    # (c) the owner's account rule
    kept, skipped = accounts_sim(T, ACCOUNTS)
    kn, sn = np.array([t["net"] for t in kept]), np.array([t["net"] for t in skipped])
    kd = defaultdict(float)
    for t in kept:
        kd[t["date"]] += t["net"]
    kdaily = np.array([kd[d] for d in days])
    kdd, _, _ = dd_of(kdaily)
    # most positions open at once on each day
    peak = []
    for d in days:
        ev = sorted([(t["in"], 1) for t in T_by_day[d]] + [(t["out"], -1) for t in T_by_day[d]], key=lambda e: (e[0], e[1]))
        c = m = 0
        for _, s in ev:
            c += s
            m = max(m, c)
        peak.append(m)
    peak = np.array(peak)
    L += ["", f"## (c) The owner's account rule: one position per account, {ACCOUNTS} accounts", "",
          "All trades in time order; a signal is skipped only when 5 positions are already open; a position frees its account at its exit.", "",
          "| | Trades | Net | Avg trade | Win | Max drawdown (daily) |", "|---|---|---|---|---|---|",
          f"| All signals | {len(T)} | {money(net.sum())} | {money(net.mean())} | {pct((net > 0).sum(), len(net))} | {money(dd)} |",
          f"| Kept | {len(kn)} | {money(kn.sum())} | {money(kn.mean())} | {pct((kn > 0).sum(), len(kn))} | {money(kdd)} |",
          f"| Skipped | {len(sn)} ({pct(len(sn), len(T))}) | {money(sn.sum()) if len(sn) else '$0'} | "
          f"{money(sn.mean()) if len(sn) else '-'} | {pct((sn > 0).sum(), len(sn)) if len(sn) else '-'} | |", "",
          f"Net kept = {pct(kn.sum(), net.sum())} of the full stack's net. Days on which 6+ positions would be open at once: "
          f"{(peak > ACCOUNTS).sum()} of {nd} ({pct((peak > ACCOUNTS).sum(), nd)}).", "",
          "| Most positions open at once that day | 0 | 1 | 2 | 3 | 4 | 5 | 6+ |", "|---|---|---|---|---|---|---|---|",
          "| Days | " + " | ".join(str(int((peak == k).sum())) for k in range(6)) + f" | {int((peak >= 6).sum())} |"]
    if len(sn):
        L += ["", "Skipped by leg: " + ", ".join(f"{legs[li]['name']} {sum(t['leg'] == li for t in skipped)}"
                                                  for li in range(len(legs)) if any(t["leg"] == li for t in skipped)) + "."]

    # (d) correlation
    M = np.zeros((len(legs), nd))
    di = {d: i for i, d in enumerate(days)}
    for t in T:
        M[t["leg"], di[t["date"]]] += t["net"]
    C = np.corrcoef(M)
    off = C[~np.eye(len(legs), dtype=bool)]
    rest = [float(np.corrcoef(M[li], M.sum(0) - M[li])[0, 1]) for li in range(len(legs))]
    L += ["", "## (d) How the legs move together", "",
          f"Daily net correlation (all {nd} days, 0 on a leg's no-trade days): average pair {off.mean():+.2f}, "
          f"lowest {off.min():+.2f}, highest {off.max():+.2f}. With that average, the 8 legs act like about "
          f"{len(legs) / (1 + (len(legs) - 1) * off.mean()):.1f} independent bets (8 / (1 + 7 x average pair)).", "",
          "| Leg | " + " | ".join(str(i + 1) for i in range(len(legs))) + " | vs rest of stack |", "|---|" + "---|" * (len(legs) + 1)]
    for li, g in enumerate(legs):
        L.append(f"| {li + 1} {g['name']} | " + " | ".join("" if a == li else f"{C[li, a]:+.2f}" for a in range(len(legs)))
                 + f" | {rest[li]:+.2f} |")
    cl = side_clusters(T)
    dmax = defaultdict(int)
    for t, c in zip(T, cl):
        dmax[t["date"]] = max(dmax[t["date"]], c)
    dm = np.array([dmax.get(d, 0) for d in days])
    c3 = cl >= 3
    d3 = dm >= 3
    L += ["", "Same direction at once (distinct legs holding the same side at the same moment, the trade itself counted):", "",
          "| Legs on one side at once (at entry) | Trades | Share | Net | Avg trade | Win |", "|---|---|---|---|---|---|"]
    for lab, m in [("1", cl == 1), ("2", cl == 2), ("3", cl == 3), ("4+", cl >= 4)]:
        n = net[m]
        L.append(f"| {lab} | {m.sum()} | {pct(m.sum(), len(T))} | {money(n.sum())} | {money(n.mean()) if len(n) else '-'} | "
                 f"{pct((n > 0).sum(), len(n)) if len(n) else '-'} |")
    L += ["", f"Days with 3+ legs on one side at some moment: {d3.sum()} of {traded.sum()} trading days ({pct(d3.sum(), traded.sum())}); "
          f"their net {money(daily[d3].sum())} ({pct(daily[d3].sum(), daily.sum())} of the total), avg day {money(daily[d3].mean())}; "
          f"the other trading days avg {money(daily[traded & ~d3].mean())}. Most legs on one side at once: {cl.max()}."]
    agree = []
    for d in days:
        x = T_by_day[d]
        if len({t["leg"] for t in x}) >= 2:
            lo = sum(t["side"] > 0 for t in x)
            agree.append(max(lo, len(x) - lo) / len(x))
    agree = np.array(agree)
    L += [f"On days with 2+ legs trading ({len(agree)}), the day's majority side holds {100 * agree.mean():.0f} % of its trades on average; "
          f"all trades on one side on {pct((agree == 1).sum(), len(agree))} of those days."]

    # (e) per year, per month
    yrs = sorted({d[:4] for d in days})
    L += ["", "## (e) By year and by month (in-sample months only)", "",
          "| Year | Days | Trades | Trades/day | Net | Avg trade | Win | Days > 0 | Max drawdown (daily) |", "|---|---|---|---|---|---|---|---|---|"]
    for y in yrs:
        m = np.array([d[:4] == y for d in days])
        n = np.array([t["net"] for t in T if t["date"][:4] == y])
        ddy, _, _ = dd_of(daily[m])
        L.append(f"| {y} | {m.sum()} | {len(n)} | {len(n) / m.sum():.1f} | {money(n.sum())} | {money(n.mean())} | {pct((n > 0).sum(), len(n))} | "
                 f"{pct((daily[m & traded] > 0).sum(), (m & traded).sum())} | {money(ddy)} |")
    mon = defaultdict(float)
    for d, v in zip(days, daily):
        mon[d[:7]] += v
    mv = np.array(list(mon.values()))
    L += ["", f"Net per month, $k (blank = a test month, not used): {(mv > 0).sum()} of {len(mv)} in-sample months positive; "
          f"worst {money(mv.min())}, best {money(mv.max())}.", "",
          "| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for y in yrs:
        L.append(f"| {y} | " + " | ".join(f"{mon[f'{y}-{k:02d}'] / 1000:+.1f}" if f"{y}-{k:02d}" in mon else "" for k in range(1, 13)) + " |")
    cal = defaultdict(list)
    for k, v in mon.items():
        cal[int(k[5:])].append(v)
    L += ["", "| Calendar month (years pooled) | " + " | ".join(dt.date(2000, k, 1).strftime("%b") for k in range(1, 13)) + " |",
          "|---|" + "---|" * 12,
          "| Net $k | " + " | ".join(f"{sum(cal[k]) / 1000:+.1f}" if cal[k] else "" for k in range(1, 13)) + " |",
          "| Months > 0 | " + " | ".join(f"{sum(v > 0 for v in cal[k])}/{len(cal[k])}" if cal[k] else "" for k in range(1, 13)) + " |"]

    # (f) long vs short
    L += ["", "## (f) Long vs short", "", "| Side | Trades | Net | Avg trade | Win | Share of the stack's net |", "|---|---|---|---|---|---|"]
    for lab, s in [("Long", 1), ("Short", -1)]:
        n = np.array([t["net"] for t in T if t["side"] == s])
        L.append(f"| {lab} | {len(n)} | {money(n.sum())} | {money(n.mean())} | {pct((n > 0).sum(), len(n))} | {pct(n.sum(), net.sum())} |")
    L += ["", "| Leg | Long trades | Long net | Long avg | Short trades | Short net | Short avg |", "|---|---|---|---|---|---|---|"]
    for li, g in enumerate(legs):
        lo = np.array([t["net"] for t in T if t["leg"] == li and t["side"] > 0])
        sh = np.array([t["net"] for t in T if t["leg"] == li and t["side"] < 0])
        L.append(f"| {li + 1} {g['name']} | {len(lo)} | {money(lo.sum())} | {money(lo.mean()) if len(lo) else '-'} | {len(sh)} | "
                 f"{money(sh.sum())} | {money(sh.mean()) if len(sh) else '-'} |")

    # (g) what days pay: the NY session's range and its direction (5m high/low cache; in-sample dates only)
    S = ny_session_days()
    have = [i for i, d in enumerate(days) if d in S and traded[i]]
    rng = np.array([S[days[i]]["rng"] for i in have])
    mv_ = np.array([S[days[i]]["move"] for i in have])
    tr = np.abs(mv_) / np.where(rng > 0, rng, 1)
    dn = daily[have]
    L += ["", "## (g) What kind of day pays (NY 09:30-16:00 range and how far it went one way; hindsight, descriptive only)", "",
          f"{len(have)} trading days with a full NY session in the 5m cache. 'One-way' = |last 5m mid - first 5m mid| / the session range.", "",
          "| Days, by | Third | Days | Avg range (pts) | Stack avg day | Share of these days' net | Days > 0 |", "|---|---|---|---|---|---|---|"]
    for lab, v in [("session range", rng), ("one-way", tr)]:
        q = np.quantile(v, [1 / 3, 2 / 3])
        for nm, m in [("low", v <= q[0]), ("middle", (v > q[0]) & (v <= q[1])), ("high", v > q[1])]:
            L.append(f"| {lab} | {nm} | {m.sum()} | {rng[m].mean():.0f} | {money(dn[m].mean())} | {pct(dn[m].sum(), dn.sum())} | "
                     f"{pct((dn[m] > 0).sum(), m.sum())} |")
    w = a = 0.0
    nw = na = 0
    for i in have:
        sgn = np.sign(S[days[i]]["move"])
        for t in T_by_day[days[i]]:
            if t["side"] == sgn:
                w += t["net"]
                nw += 1
            else:
                a += t["net"]
                na += 1
    L += ["", "| Trades, by the NY session's eventual direction | Trades | Net | Avg trade |", "|---|---|---|---|",
          f"| With it | {nw} | {money(w)} | {money(w / nw)} |", f"| Against it | {na} | {money(a)} | {money(a / na)} |"]

    out = "\n".join(L) + "\n"
    f = HERE / "STACK_STUDY.md"
    old = f.read_text() if f.exists() else ""
    if "\n## Conclusions" in old:                          # the hand-written conclusions survive a re-run
        out += "\n## Conclusions" + old.split("\n## Conclusions", 1)[1]
    f.write_text(out)
    print(out)


if __name__ == "__main__":
    main()
