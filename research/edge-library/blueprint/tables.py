"""tables.py -- the TABLE DATA of lines.py for a unit whose stores are on disk. READ-ONLY: no simulation, no write. Everything
is read through the judge's own functions (judge.unit, build_store, table, table_stats, cellx, and for the random tables
judge.controls = c1_table over pool_arrays / c1_cell, shift_table, c2_table, days_test, base_test, verdict), at the judge's
rule in force (judge.RULE: 4,000 draws, every control seed on disk) and with its seeds: a number here is the judge's number.

THIS STEP READS THE OLD BUILD DAYS ONLY (ranges.json `stored_build` = the engine's and the judge's BUILD, 2021-09-22 ..
2023-12-31, 27 months). The blueprint's own build runs to 2025-06-30 and has no store yet, so what is read here is a DRY RUN,
never a blueprint verdict. guard() is the seal: a store whose date range is not inside those days is refused. (The judge's
index reads the run.json of every store folder to learn its date range; trades are loaded from in-range stores only.)

  unit(x)        a unit address or a uid of out/v2/build_units.csv -> the judge's unit
  stored(x)      its table data: `net`, `n` per (judged variant, session day) and the two sides          lines 2.1 2.2 2.4 2.6 2.8
  controls(t)    + `controls` and `filters`: every control of the unit's type, drawn by the judge                 lines 2.3 2.7
  neighbors(u)   the net of the average variant of the idea's other stored tables                                    line 2.5
"""
from __future__ import annotations

import csv

import numpy as np

import judge as J
import library as LB

from . import rules as R

PERIOD = "build"                    # the judge's name of the stored build days: the only period this module asks it for
STAGES = ("s1", "r1")               # the stored tables of BLUEPRINT.md section 3: 1,881 addresses, 1,875 with a judged variant
UIDS = J.W / "out" / "v2" / "build_units.csv"
_POOL: list = []                    # (address, family, market) of every stored table of STAGES
_AVG: dict = {}                     # address -> net of its average variant (None: no judged variant)
_UID: dict = {}


def guard(rec: dict) -> dict:
    """THE SEAL of this step: a store (its index row) is read only when its whole date range lies inside the stored build
    days of ranges.json. Anything later -- 2024, 2025, the test days -- is refused."""
    rg = R.template("ranges")["stored_build"]
    if not (rec["start"] and rg["start"] <= rec["start"] and rec["end"] <= rg["end"]):
        raise J.Refuse(f"store {J.where(rec)} covers {rec['start'] or '?'} .. {rec['end'] or '?'}: this step reads the stored "
                       f"build days only ({rg['start']} .. {rg['end']})")
    return rec


def unit(x: str) -> dict:
    """A unit address (judge.unit: `orb-NQ-tf15-pre`, `ib-NQ-tf15-mid:mode=break`, the uid `orb-NQ-tf15|pre|`) or any uid
    of out/v2/build_units.csv (`E1-A-NQ`) -> the judge's unit."""
    try:
        return J.unit(x)
    except J.Refuse:
        if not _UID:
            with UIDS.open() as fh:
                _UID.update({r["uid"]: r for r in csv.DictReader(fh)})
        r = _UID.get(x.strip())
        if r is None:
            raise
        filt = r["group"] or r["side"]
        return J.unit(f"{r['key']}-{r['sess']}" + (f":{r['label']}" if r["label"] else "") + (f"@{filt}" if filt else ""))


def catalog() -> list:
    """The addresses of the stored tables of BLUEPRINT.md section 3 (stages s1 + r1), in catalog order."""
    return [a for s in STAGES for a in J.catalog(s)]


def stored(x) -> dict:
    """The table data of ONE stored unit (an address, a uid or a judge unit) on the stored build days:
      ids             its judged variants (library.judged_rows: dead and author cells out, identical trade lists once)
      days            the session days of the range (the engine's calendar of the market)
      net, n          (variants x days) net and trades of each variant on each day
      long, short, n_long, n_short     net and trades of each side, all variants together
      months          the months the stored days cover (2.4 "on pace")
    Refused: a unit without a store or without a judged variant, a store outside the stored build days, a trade dated off the
    session calendar. Keys that start with '_' (the judge's unit, store and table numbers) are for controls()."""
    u = x if isinstance(x, dict) else unit(x)
    st, rec = J.build_store(u)
    guard(rec)
    ts = J.table_stats(J.table(st, u))
    _AVG[u["addr"]] = ts["avg_net"]
    if not ts["cells"]:
        raise J.Refuse(f"{u['addr']}: no judged variant on the stored build days")
    ids, days = ts["ids"], LB._ordinals(J.calendar(PERIOD, u["root"]))
    net, n = np.zeros((len(ids), len(days))), np.zeros((len(ids), len(days)))
    lng = sht = 0.0
    nl = ns = lost = 0
    for i, cid in enumerate(ids):
        c = J.cellx(st, cid, u["sess"], u)
        k = np.minimum(np.searchsorted(days, c["date"]), len(days) - 1)
        ok = days[k] == c["date"]
        lost += int((~ok).sum())
        np.add.at(net[i], k[ok], c["net"][ok])
        np.add.at(n[i], k[ok], 1)
        up = c["side"] > 0
        lng, sht = lng + float(c["net"][up].sum()), sht + float(c["net"][~up].sum())
        nl, ns = nl + int(up.sum()), ns + int((~up).sum())
    if lost:
        raise J.Refuse(f"{u['addr']}: {lost} trades are dated off the session calendar of {u['root']}: the table cannot be read")
    return {"unit": u["addr"], "uid": u["uid"], "family": u["family"], "root": u["root"], "store": J.where(rec), "ids": ids,
            "dead": ts["dead"], "dup": ts["dup"], "days": days, "net": net, "n": n, "long": lng, "short": sht, "n_long": nl,
            "n_short": ns, "months": R.template("ranges")["stored_build"]["months"], "_u": u, "_st": st, "_ts": ts}


def controls(t: dict) -> dict:
    """Adds to a stored table what lines 2.3 and 2.7 read: EVERY control of the unit's type on the build days, drawn by the
    judge itself (judge.controls) with its own seeds and draws, so the numbers are judge.build's:
      controls    {c1 | shift | c2: the verdict against random tables · days | base: the unit against its plain version}
      filters     the unit's filter against the same strategy without it: a Level 2 option of a base family (`base`: the
                  base family's table) or a day filter (`days`: the same table on all days, and random day subsets)
    The judge draws a control only for a table near its test (1); here it is drawn for any table. Every store a control used
    is checked against the seal."""
    u = t["_u"]
    det = J.controls(t["_st"], u, t["_ts"], PERIOD)
    row = {J.where(r): r for r in J.index()}
    for v in det.values():
        for s in v.get("stores") or {}:
            guard(row[s])
    t["controls"], t["filters"] = det, []
    for c, name, mine, plain in (("base", f"{u['family']} against {u['base']} (without the Level 2 option)", "per_trade", "base_per_trade"),
                                 ("days", f"day filter {u['filter']} against all days", "per_trade", "unfiltered_per_trade")):
        if c in det:
            v = det[c]
            t["filters"].append({"name": name, "avg_trade": v[mine], "plain_avg_trade": v[plain], "p_beat": [v["p_beat"]] if "p_beat" in v else []}
                                if mine in v else {"name": name, "why": v.get("why")})
    return t


def pool() -> list:
    """(address, family, market) of every stored table of STAGES."""
    if not _POOL:
        for a in catalog():
            u = J.unit(a)
            _POOL.append((u["addr"], u["family"], u["root"]))
    return _POOL


def avg(addr: str):
    """Net of the average variant of a stored table (None: it has no judged variant). Kept, so a table is read once."""
    if addr not in _AVG:
        u = J.unit(addr)
        st, rec = J.build_store(u)
        guard(rec)
        _AVG[addr] = J.table_stats(J.table(st, u))["avg_net"]
    return _AVG[addr]


def neighbors(u: dict) -> list:
    """Line 2.5 on the stored tables: the idea's OTHER tables = the same family and market at the other bar sizes, sessions
    and mirror values, among the stored tables of STAGES -- out/blueprint/funnel.py's stand-in for the neighbors an idea card
    names (line 0.4). -> [net of the average variant of each] (a table without a judged variant is left out, as there)."""
    nets = [avg(a) for a, fam, root in pool() if (fam, root) == (u["family"], u["root"]) and a != u["addr"]]
    return [x for x in nets if x is not None]
