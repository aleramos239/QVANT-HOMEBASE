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
  place(name, root, tf, sess)   one table of an idea by the place its card names: the average variant of a neighbor (line
                 2.5 of an idea's record reads the neighbors the CARD names: records.py) or of the place it should not work
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


def sigs(name: str, root: str, tf, sess: str, filt=None, out_dir=None) -> dict:
    """{variant id: the fingerprint of its trade list} of one table of an idea (library.trade_sig): what place() holds a
    neighbor against to tell a table of its own from the home table's trades under another name."""
    out = RUN.RUNS if out_dir is None else Path(out_dir)
    st, _ = _open(out, RI.unit_key({"name": name}, root, tf, filt))
    return {r["id"]: r.get("sig") for r in LB.plateau_units(st, sess)[""] if r.get("sig") is not None}


def place(name: str, root: str, tf, sess: str, filt=None, out_dir=None, like=None) -> dict:
    """ONE table of an idea by its place -- a market, bar size and session the idea's card names (a neighbor of line 2.5, or
    the place it should NOT work) -- from the store `<name>[__<filter>]-<ROOT>-tf<tf>` the build wrote: its judged variants,
    the net of its average variant (None: no variant traded there), how many are profitable. The seal is _open's.
    `like` = the home table's sigs(): `same` then counts the variants whose trade list IS the home table's (an opening range
    in minutes trades alike on 5-, 15- and 30-minute bars), and `copy` says the table is the home table again -- the law
    counts tables that are the same trades once (rules.json 2.5 also.copy_share of its variants or more)."""
    out = RUN.RUNS if out_dir is None else Path(out_dir)
    st, where = _open(out, RI.unit_key({"name": name}, root, tf, filt))
    rows = LB.plateau_units(st, sess)[""]
    ts = J.table_stats(rows)
    same = sum(1 for r in rows if r.get("sig") is not None and (like or {}).get(r["id"]) == r["sig"])
    return {"table": f"{root}-tf{tf}-{sess}", "store": where, "variants": ts["cells"], "avg_net": ts["avg_net"], "positive": ts["positive"],
            "profitable": bool(ts["cells"] and ts["avg_net"] > R.rule("2.1")["also"]["profitable_above"]),
            "same": same, "copy": bool(like and rows and same >= R.rule("2.5")["also"]["copy_share"] * len(rows))}


def built(spec: dict, home=None, filt=None, out_dir=None, days=None, round_: int = 1, control: bool = True) -> dict:
    """THE TABLE DATA of one table of an idea on the build range, from the stores runner.run_build wrote (module docstring):
      net, n, the sides     its judged variants on the engine's session calendar of the range        lines 2.1 2.2 2.4 2.6 2.8
      controls {c1}         the judge's random tables from the pool's 10 seeds (pool_seeds, against_random)        line 2.3
      neighbors             the average variant's net of every OTHER table of the spec: its other markets, bar sizes,
                            sessions (and mirror values), plain or with the same filter                             line 2.5
      filters               with a filter: its table against the plain table of the same spec (judge.base_test)     line 2.7
      round, months         the round whose bar 2.3 is held against; the build's months (no "on pace" reading)
    control False = the random tables are NOT read (the idea's own tables were run, its control pool was not: the 10-seed control
    runs only for an idea that passes every other line): `controls` is empty and `control_skipped` says so, line 2.3 reads that.
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
    if control:
        pool = pool_seeds(out, RUN.pool_key(root, tf, spec["exits"]), need, R.template("control")["seeds"])
        t["controls"] = {"c1": against_random(st, u, ts, pool, f"{RUN.PERIOD}-c1")}
    else:
        t["controls"], t["control_skipped"] = {}, True
    t["filters"], t["neighbors"] = [], []
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
        plain_st = _open(out, RI.unit_key(spec, root, tf))[0]
        blocks = RUN._blocks()

        def held(name, a_st, a_u, b_st, ids):
            v = J.base_test(a_st, b_st, a_u, ids)
            t["filters"].append({"name": name, "avg_trade": v["per_trade"], "plain_avg_trade": v["base_per_trade"], "p_beat": []} if "per_trade" in v
                                else {"name": name, "why": v.get("why")})
        held(f"filter {' '.join(f)} against the plain version" if len(blocks.parts(f)) == 1 else
             f"both filters {' and '.join(' '.join(p) for p in blocks.parts(f))} against the plain version", st, u, plain_st, ts["ids"])
        if len(blocks.parts(f)) > 1:               # two filters on: each must win alone (against plain), and the pair must beat each one alone
            for one in blocks.parts(f):
                su = bp_unit(spec, root, tf, sess, label, one)
                sst = _open(out, su["key"])[0]
                _labels(sst, su)
                sids = J.table_stats(J.table(sst, su))["ids"]
                held(f"filter {' '.join(one)} alone against the plain version", sst, su, plain_st, sids)
                held(f"both filters against {' '.join(one)} alone", st, u, sst, ts["ids"])
    t["round"], t["months"] = round_, (R.template("ranges")["build"]["months"] if named is None else None)
    return t


def build_days(u: dict, days=None) -> list:
    """The session days of the build range for a unit's market, as ISO dates (days = the named days of a smoke run, sealed)."""
    named = None if days is None else RUN.seal(days)
    return named if named is not None else [d.isoformat() for d in S.sessions(*S.period(RUN.PERIOD), u["root"], allow_holdout=RUN.PERIOD)]


def box(st: dict, u: dict, cell: str, days=None) -> dict:
    """THE BOX DATA of lines 3.3-3.8: ONE variant of a build store alone -- the net of each of its trades, and its net, its
    trades and its worst open loss (library._worst_open on each trade's MAE + the round-turn commission, as library.metrics
    reads it) on every session day of the build range (days = the named days of a smoke run, as in built())."""
    cal = build_days(u, days)
    t = _data(st, u, {"ids": [cell], "dead": 0, "dup": 0}, LB._ordinals(cal), "")
    c, by = J.cellx(st, cell, u["sess"], u), {}
    for d, ent, dur, net, mae in zip(c["date"], c["entry_ms"], c["dur_s"], c["net"], c["mae"]):
        by.setdefault(int(d), []).append((int(ent), int(ent) + int(dur) * 1000, float(net), abs(float(mae)) + LB.COMM_RT))
    return {"trades": np.asarray(c["net"], np.float64), "day": t["net"][0], "n": t["n"][0],
            "open": np.array([LB._worst_open(by.get(int(d), [])) + 0.0 for d in t["days"]])}


def avg_trade(st: dict, u: dict, ids: list):
    """Line 2.2's number of a table: the net of the listed variants / their trades (None: no trade)."""
    net = n = 0.0
    for cid in ids:
        x = J.cellx(st, cid, u["sess"], u)["net"]
        net, n = net + float(np.sum(x)), n + len(x)
    return net / n if n else None


# ================================================================ the test days: the stores of the ONE read (runner.run_test)

def tested(spec: dict, lock: dict, out_dir=None) -> dict:
    """THE TABLE DATA OF THE ONE READ of a frozen idea, from the three stores runner.run_test wrote for its lock:
      net, n            the LOCKED variants (the lock's list: no second look at which ones count) on the session days the
                        read replayed (the store's own `calendar`)                                    lines 4.1 4.2 4.3 4.6 4.7
      parts             the two parts of the frozen range as masks over those days                                 line 4.1
      controls {c1}     the judge's random tables (judge.c1_table, verdict) from the idea's own 10-seed pool of the test
                        days, with the draws and the draw seed THE LOCK holds                                      line 4.4
      worse, worse_fills    each locked variant's net with worse fills, and those fills in words                   line 4.5
      build_avg_trade   the average trade of the frozen table on the build days, as the lock holds it              line 4.8
      box {trades}      the lock's default variant alone on the test days                                          line 4.9
    READ-ONLY, and no engine call: the days are the stores'. runner.guard_test is the seal -- a store that is not of the
    frozen range, or not of this lock's read, is refused; so is a trade dated outside the range, a locked variant a store
    does not hold, a pool with fewer seeds than the lock froze. spec = the engine's settings of the home's store."""
    out, h = (RUN.TESTS if out_dir is None else Path(out_dir)), lock["home"]
    root, tf, sess = h["market"], str(h["bar"]), h["session"]
    u = bp_unit(spec, root, tf, sess, "", filter_of(spec, h["filter"]))
    if u["key"] != h["key"]:
        raise J.Refuse(f"the settings name the unit {u['key']}, the lock froze {h['key']}")
    rng, K = lock["test_range"][root], RUN.test_keys(u["key"], lock["store"], root, tf, sess)
    lo, hi = S._date(rng["start"]).toordinal(), S._date(rng["end"]).toordinal()

    def opened(key: str) -> tuple:
        f, where = out / key / "run.json", f"{out.name}/{key}"
        if not f.exists():
            raise J.Refuse(f"no store {where}: the read of the test days has not written it")
        RUN.guard_test(json.loads(f.read_text()), where, rng["start"], rng["end"], lock["hash"])
        st = J.store({"dir": out, "key": key})
        if len(st["date"]) and (int(st["date"].min()) < lo or int(st["date"].max()) > hi):
            raise J.Refuse(f"store {where} holds a trade dated outside {rng['start']} .. {rng['end']}: it is not read")
        return st, where

    (st, where), (wst, _), (pst, pwhere) = opened(K["table"]), opened(K["worse"]), opened(K["pool"])
    ids = list(lock["variants"])
    for s, key in ((st, K["table"]), (wst, K["worse"])):
        gone = [c for c in ids if c not in s["_idx"]]
        if gone:
            raise J.Refuse(f"store {out.name}/{key} lacks the locked variant {gone[0]}: it is not the read of this lock")
    cal = st["meta"].get("calendar")
    if not cal:
        raise J.Refuse(f"store {where} does not say which session days were replayed: it is not read")
    t = _data(st, u, {"ids": ids, "dead": 0, "dup": 0}, LB._ordinals(cal), where)
    day = lambda iso: S._date(iso).toordinal()  # noqa: E731
    t["calendar"], t["range"] = list(cal), {"start": rng["start"], "end": rng["end"]}
    t["parts"] = [{"name": p["name"], "start": p["start"], "end": p["end"], "days": (t["days"] >= day(p["start"])) & (t["days"] <= day(p["end"]))} for p in rng["parts"]]
    c, need = lock["control"], sorted({i.rsplit("_", 1)[-1] for i in ids})
    seeds = {int(sd): ({"dir": out, "key": K["pool"]}, f"s{sd}_") for sd in c["seeds"] if all(f"s{sd}_{x}" in pst["_idx"] for x in need)}
    if len(seeds) < len(c["seeds"]):
        raise J.Refuse(f"control pool {pwhere} holds {len(seeds)} of the {len(c['seeds'])} seeds the lock froze (with every exit cell of the table)")
    keep = J.RULE["draws"]
    try:
        J.RULE["draws"] = int(c["draws"])           # the draws the lock froze (the law's 4,000)
        v = J.verdict(float(t["net"].sum(1).mean()), J.c1_table(st, u, ids, seeds, int(c["draw_seed"]["test"])), True)
    finally:
        J.RULE["draws"] = keep
    t["controls"] = {"c1": {**v, "seeds": sorted(seeds), "stores": {pwhere: sorted(seeds)}}}
    t["worse"] = np.array([float(J.cellx(wst, x, sess, u)["net"].sum()) for x in ids])
    t["worse_fills"] = RUN.worse_words(wst["meta"]["worse"])
    t["build_avg_trade"] = (lock.get("build") or {}).get("avg_trade")
    t["box"] = {"trades": np.asarray(J.cellx(st, lock["default"], sess, u)["net"], np.float64)}
    return t
