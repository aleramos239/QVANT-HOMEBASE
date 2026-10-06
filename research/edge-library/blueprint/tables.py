"""tables.py -- the TABLE DATA of lines.py for a unit whose stores are on disk. READ-ONLY: no simulation, no write. Everything
is read through the judge's own functions (judge.unit, build_store, table, table_stats, cellx, and for the random tables
judge.controls = c1_table over pool_arrays / c1_cell, shift_table, c2_table, days_test, base_test, verdict), at the judge's
rule in force (judge.RULE: 4,000 draws, every control seed on disk) and with its seeds: a number here is the judge's number.

THE OLD BUILD DAYS (ranges.json `stored_build` = the engine's and the judge's BUILD, 2021-09-22 .. 2023-12-31, 27 months): a
DRY RUN, never a blueprint verdict. guard() is its seal: a store whose date range is not inside those days is refused. (The
judge's index reads the run.json of every store folder to learn its date range; trades are loaded from in-range stores only.)
  unit(x)        a unit address or a uid of out/v2/build_units.csv -> the judge's unit
  stored(x)      its table data: `net`, `n` per (judged variant, session day) and the two sides          lines 2.1 2.2 2.4 2.6 2.8
  controls(t)    + `controls` and `filters`: every control of the unit's type, drawn by the judge                 lines 2.3 2.7
  neighbors(u)   the net of the average variant of the idea's other stored tables                                    line 2.5

THE BLUEPRINT'S OWN BUILD RANGE (2021-09-22 .. 2025-06-30; the stores runner.py writes to runs_bp/): the build itself.
  built(spec, home, filt)   the whole table data of ONE table of an idea spec: its market, bar size and session (the home),
                 plain or with one of the spec's filters. The random tables are the judge's too (judge.c1_table, verdict),
                 drawn from the 10 seeds of the control pool through a seed map built here (pool_seeds): judge.seed_stores
                 finds seeds through the judge's index of the four old periods, and a store of the build range lies in
                 none of them. The neighbors are the spec's other tables; a filter is held against the plain table of the
                 same spec (judge.base_test). runner.guard is the seal: nothing after 2025-06-30 is read.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_idea as RI

from . import rules as R
from . import runner as RUN

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
    return {**_data(st, u, ts, LB._ordinals(J.calendar(PERIOD, u["root"])), J.where(rec)), "months": R.template("ranges")["stored_build"]["months"]}


def _data(st: dict, u: dict, ts: dict, days: np.ndarray, where: str) -> dict:
    """The table data of one judged table on a calendar of session days (ordinals): net and trades of each judged variant
    on each day, the two sides. A trade dated off the calendar is refused: the table cannot be read on it."""
    ids = ts["ids"]
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
    return {"unit": u["addr"], "uid": u["uid"], "family": u["family"], "root": u["root"], "store": where, "ids": ids,
            "dead": ts["dead"], "dup": ts["dup"], "days": days, "net": net, "n": n, "long": lng, "short": sht, "n_long": nl,
            "n_short": ns, "_u": u, "_st": st, "_ts": ts}


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


# ================================================================ the blueprint's own build range (runs_bp/)

HOME = re.compile(r"^(?P<root>[A-Z0-9]+)-tf(?P<tf>\d+)-(?P<sess>eve|asia|london|pre|nyam|mid|pm)(?::(?P<label>[^@|]+))?$")


def home_of(spec: dict, home=None) -> tuple:
    """The table an idea is judged on -> (market, bar size, session, mirror label). `home` = <ROOT>-tf<tf>-<session>
    [:<axis>=<value>], one of the spec's own tables; None = the spec's first market, bar size and session (a spec lists its
    home first)."""
    if home is None:
        return spec["markets"][0], spec["bar_sizes"][0], spec["sessions"][0], ""
    m = HOME.match(str(home))
    if not m:
        raise J.Refuse(f"home {home!r}: expected <ROOT>-tf<tf>-<session>[:<axis>=<value>]")
    if m["root"] not in spec["markets"] or m["tf"] not in spec["bar_sizes"] or m["sess"] not in spec["sessions"]:
        raise J.Refuse(f"home {home!r} is not a table of the spec (markets {', '.join(spec['markets'])}; bar sizes {', '.join(spec['bar_sizes'])}; "
                       f"sessions {', '.join(spec['sessions'])})")
    return m["root"], m["tf"], m["sess"], m["label"] or ""


def filter_of(spec: dict, filt=None):
    """A filter of the spec by its name <block>_<side> (as in its store key) -> (block, side); None = the plain table."""
    if not filt:
        return None
    hit = [f for f in spec["filters"] if "_".join(f) == filt]
    if not hit:
        raise J.Refuse(f"{filt!r} is not a filter of the spec (it has {', '.join('_'.join(f) for f in spec['filters']) or 'none'})")
    return hit[0]


def bp_unit(spec: dict, root: str, tf, sess: str, label: str = "", filt=None) -> dict:
    """The judge's unit of one table of an idea spec, built by hand (judge.unit reads runs/ only): what judge.table, cellx,
    c1_table and base_test ask of a unit. Its control is c1, the random entries of the pool."""
    key = RI.unit_key(spec, root, tf, filt)
    return {"addr": f"{key}-{sess}" + (f":{label}" if label else ""), "uid": f"{key}|{sess}|{label}", "key": key, "family": spec["family"],
            "root": root, "tf": str(tf), "sess": sess, "label": label, "filter": None, "group": None, "side": None, "placebo": 0, "controls": ["c1"]}


def _open(out: Path, key: str) -> tuple:
    """A store as the judge reads it -> (store, where). Refused: no store; a range that is not inside the build days
    (runner.guard, the seal: read from run.json BEFORE a trade is loaded); a trade dated after them, whatever run.json says."""
    f, where = out / key / "run.json", f"{out.name}/{key}"
    if not f.exists():
        raise J.Refuse(f"no store {where}: the build has not run it")
    RUN.guard(json.loads(f.read_text()), where)
    st = J.store({"dir": out, "key": key})
    end = R.template("ranges")["build"]["end"]
    if len(st["date"]) and int(st["date"].max()) > S._date(end).toordinal():
        raise J.Refuse(f"store {where} holds a trade dated after {end}: it is not read")
    return st, where


def _labels(st: dict, u: dict) -> dict:
    """The judged tables of a store's session by mirror label (library.plateau_units: '' unless the idea's main setting is
    a mirror axis); the unit's own label must be one of them."""
    tables = LB.plateau_units(st, u["sess"])
    if u["label"] not in tables:
        raise J.Refuse(f"{u['addr']}: the store is judged per value of its mirror axis: name one of {', '.join(k or '(none)' for k in tables)} in the home")
    return tables


def pool_seeds(out, key: str, need: list, want=None) -> dict:
    """The judge's seed map of ONE store of random entries, built by hand: {seed: (the store's row, 's<seed>_')} for every
    seed that holds every exit cell in `need` (what judge.seed_stores returns for the old periods). want = the seeds the
    law asks for (control.json): a pool with fewer is refused -- a build is not judged on a thin control."""
    out = Path(out)
    st, where = _open(out, key)
    row, ids = {"dir": out, "key": key}, st["_idx"]
    seeds = sorted({int(m[1]) for m in (re.match(r"s(\d+)_", i) for i in ids) if m})
    found = {sd: (row, f"s{sd}_") for sd in seeds if all(f"s{sd}_{x}" in ids for x in need)}
    if want is not None and len(found) < want:
        raise J.Refuse(f"control pool {where} holds {len(found)} of the {want} seeds the law asks for (with every exit cell of the table): it is not a "
                       "pool of the build range")
    return found


def against_random(st: dict, u: dict, ts: dict, seeds: dict, what: str) -> dict:
    """Line 2.3's numbers by the judge's own functions: judge.c1_table (coupled draws of the table average from the random
    entries of every seed in the map, day- and session-matched) and judge.verdict -> the verdict in the shape of
    judge.controls: + the seeds and the stores they came from. `what` names the draw seed (judge.seed_of(uid, what))."""
    v = J.verdict(ts["avg_net"], J.c1_table(st, u, ts["ids"], seeds, J.seed_of(u["uid"], what)), True)
    stores: dict = {}
    for sd in sorted(seeds):
        stores.setdefault(J.where(seeds[sd][0]), []).append(sd)
    return {**v, "seeds": sorted(seeds), "stores": stores}


def built(spec: dict, home=None, filt=None, out_dir=None, days=None, round_: int = 1) -> dict:
    """THE TABLE DATA of one table of an idea on the build range, from the stores runner.run_build wrote (module docstring):
      net, n, the sides     its judged variants on the engine's session calendar of the range        lines 2.1 2.2 2.4 2.6 2.8
      controls {c1}         the judge's random tables from the pool's 10 seeds (pool_seeds, against_random)        line 2.3
      neighbors             the average variant's net of every OTHER table of the spec: its other markets, bar sizes,
                            sessions (and mirror values), plain or with the same filter                             line 2.5
      filters               with a filter: its table against the plain table of the same spec (judge.base_test)     line 2.7
      round, months         the round whose bar 2.3 is held against; the build's months (no "on pace" reading)
    days = the named days of a smoke run (the store must have been run on exactly those): the calendar is then those days
    and `months` is None. Refused: a missing store, the seal (runner.guard), a store that is not of the build range or of
    other days, no judged variant, a pool with fewer seeds than the law asks."""
    out = RUN.RUNS if out_dir is None else Path(out_dir)
    root, tf, sess, label = home_of(spec, home)
    f = filter_of(spec, filt)
    u = bp_unit(spec, root, tf, sess, label, f)
    st, where = _open(out, u["key"])
    named = None if days is None else RUN.seal(days)
    if st["meta"].get("period") != RUN.PERIOD or (st["meta"].get("days") or None) != named:
        raise J.Refuse(f"store {where} is not the store asked for: it is of period {st['meta'].get('period')!r}"
                       + (f", run on {len(st['meta']['days'])} named days" if st["meta"].get("days") else "") + f" (asked: {RUN.PERIOD}"
                       + (f", {len(named)} named days)" if named else ", the whole range)"))
    _labels(st, u)
    ts = J.table_stats(J.table(st, u))
    if not ts["cells"]:
        raise J.Refuse(f"{u['addr']}: no judged variant on the build days")
    cal = named if named is not None else [d.isoformat() for d in S.sessions(*S.period(RUN.PERIOD), root, allow_holdout=RUN.PERIOD)]
    t = _data(st, u, ts, LB._ordinals(cal), where)
    need = sorted({i.rsplit("_", 1)[-1] for i in ts["ids"]})
    pool = pool_seeds(out, RUN.pool_key(root, tf), need, R.template("control")["seeds"])
    t["controls"], t["filters"], t["neighbors"] = {"c1": against_random(st, u, ts, pool, f"{RUN.PERIOD}-c1")}, [], []
    for r2 in spec["markets"]:
        for tf2 in spec["bar_sizes"]:
            key2 = RI.unit_key(spec, r2, tf2, f)
            st2 = st if key2 == u["key"] else _open(out, key2)[0]
            for s2 in spec["sessions"]:
                for lab, rows in LB.plateau_units(st2, s2).items():
                    a = None if (key2, s2, lab) == (u["key"], sess, label) else J.table_stats(rows)["avg_net"]
                    if a is not None:               # a table without a judged variant is left out (as in the dry run)
                        t["neighbors"].append(a)
    if f:
        v = J.base_test(st, _open(out, RI.unit_key(spec, root, tf))[0], u, ts["ids"])
        name = f"filter {f[0]} {f[1]} against the plain version"
        t["filters"].append({"name": name, "avg_trade": v["per_trade"], "plain_avg_trade": v["base_per_trade"], "p_beat": []} if "per_trade" in v
                            else {"name": name, "why": v.get("why")})
    t["round"], t["months"] = round_, (R.template("ranges")["build"]["months"] if named is None else None)
    return t
