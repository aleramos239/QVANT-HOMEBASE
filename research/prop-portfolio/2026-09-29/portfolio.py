#!/usr/bin/python3
"""Stage B portfolio engine: members (trade source, session, micros) + ONE shared daily-rules cell, scored per firm under its
PRIMARY breach model (lucid* = realized, apex* = intraday; eod / realized / intraday always all reported).

Everything runs on evalcore (same day walk, same races, same cost model); this file only adds the portfolio layer.
Run with /usr/bin/python3 and PYTHONPATH=~/ramos-quant-homebase (numpy). Research window only (evalcore drops 2025+).
CLI: portfolio.py run --firms lucid,lucidpro,... [--workers 4] [--top 20] | multi | wf | diag   (see main()).

Pieces
  Base / PV        one (trade source, session) trade set, and a merged multi-member "portfolio view" on a session calendar
                   (members' trades in time order with their own micros; day walk = evalcore._walk_day, so overlap-aware worst
                   points, conflicts and max concurrent micros come straight from evalcore).
  rules cell       (day_lock, day_take, day_stop, max_day_tr, target_take) shared by all members (pass-2 grids of the firm; the
                   micros axis of the pass-2 grid is replaced by the per-member micros). target_stop is always on (as in pass 2).
  scoring          P5 per rolling start under the primary model; "stable" P5 = median over the rules cell and its +-1-step grid
                   neighbours (pass-2 criterion); ties -> fewer active rules, then the earlier grid index.
  search           greedy forward selection from the best single (micros choices up to the cap; same family+session duplicates
                   penalised; >= 3 members for the reported 'portfolio', the best 2-member reported too; no member > 50% of the
                   portfolio's raw net P&L once there are 3+ members), then local resize / swap passes; the shared rules cell is
                   re-optimised for every candidate (full grid). Stops when no gain > MIN_GAIN.
  controls         each member replaced by its own day-matched random control (evalcore.daymatched_controls; identical micros, rules).
  walk-forward     quarterly 2022Q3..2024Q4, selection on the trailing 12 months (attempts END before the test quarter), two variants:
                   'fixed set' (micros + rules re-selected, member SET from the full-window search: a known look-ahead bias) and
                   'reselect' (the whole greedy search re-run per quarter on the pool).
  multi-account    N accounts (firms mixed), one strategy/portfolio per account, attempts aligned by start day.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import math
import os
import sys
import time
import zlib
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402

PS = E.PS
R, OUT = E.D, E.D / "out"
ET = ZoneInfo("America/New_York")
H = E.H_EVAL
MIN_GAIN = 0.005
DUP_PEN = 0.02                 # score penalty per existing member of the same family + session
MAX_SHARE = 0.5                # no member above this share of the portfolio's raw net P&L (3+ members)
MAX_MEMBERS = 5
FIRM_ALL = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
MODELS = E.MODELS
AX5 = ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")
_LUCIDPRO = {"day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000], "day_stop": [0, 1000, 2000],
             "max_day_tr": [1, 0], "target_take": [0, 1]}
GRIDS = {     # pass-2 rule grids minus the micros axis (lucid: a3_pass2.GR; lucidpro*: a3p2_lp._G; apex: a3_pass2.GR; apex_eod: new)
    "lucid": {"day_lock": [0, 750, 1000, 1500], "day_take": [0, 1000, 1250, 1500], "day_stop": [0, 1000, 2000],
              "max_day_tr": [1, 0], "target_take": [0, 1]},
    "lucidpro": _LUCIDPRO, "lucidpro_nodll": _LUCIDPRO,
    "apex": {"day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000], "day_stop": [0, 1000, 2000, 3000],
             "max_day_tr": [1, 0], "target_take": [0, 1]},
    # apex_eod has no earlier search: lock / take like apex, stops below its own $1,000 soft DLL (rule file applies it anyway)
    "apex_eod": {"day_lock": [0, 1000, 2000], "day_take": [0, 1000, 1500, 2000, 3000], "day_stop": [0, 500, 750],
                 "max_day_tr": [1, 0], "target_take": [0, 1]},
}
if os.environ.get("PP_APEX_COMPLIANT") == "1":      # Apex compliance: a day_stop >= $2,000 would be the trailing threshold used as a stop
    GRIDS["apex"] = dict(GRIDS["apex"], day_stop=[0, 1000])
if os.environ.get("PP_FLEX_TAKE_EXT") == "1":       # Flex 2-day pass needs a day_take fill >= $1,500 per day: 1,500 minus 1 tick x n (n=40: $50) is $1,450 -> two days $2,900 < $3,000
    GRIDS["lucid"] = dict(GRIDS["lucid"], day_take=[0, 1000, 1250, 1500, 1560, 1600])
MICROS = {"lucid": [10, 20, 30, 40], "lucidpro": [10, 20, 30, 40], "lucidpro_nodll": [10, 20, 30, 40],
          "apex": [20, 40, 60, 80, 100], "apex_eod": [20, 30, 40, 50, 60]}
_P2 = "a3p2_snap" if E.PL.NAME == "nq" else "a3p3s_snap"          # pass-2 snapshot (ES: the screen-config pass a3p3_screen.py)
SNAP_L, SNAP_J = OUT / f"{_P2}_ledger.csv", OUT / f"{_P2}_jobs.jsonl"


# ------------------------------------------------------------------ desk-window gate

def gate():
    """Block while the ET clock is inside the 09:18-09:36 weekday desk window (called before every uncached grid evaluation)."""
    while True:
        n = dt.datetime.now(ET)
        lo, hi = n.replace(hour=9, minute=18, second=0, microsecond=0), n.replace(hour=9, minute=36, second=0, microsecond=0)
        if n.weekday() < 5 and lo <= n < hi:
            s = (hi - n).total_seconds() + 5
            print(f"[gate] {n:%H:%M} ET in the desk window, sleeping {s:.0f}s", flush=True)
            time.sleep(s)
        else:
            return


# ------------------------------------------------------------------ firm context

class Firm:
    """Rules, primary model, rule grid (5 axes), micros choices and fees of one firm short name."""

    def __init__(self, name: str):
        self.name = name
        self.rid, self.r = E.firm_rules(name)
        self.dll = PS._dll(self.r) or 0.0
        self.cap = int(self.r["cap_micros"])
        self.prim = E.primary_model(name)
        self.confirmed = self.r.get("confirmed") is not False
        self.grid = GRIDS[name]
        self.shape = tuple(len(self.grid[a]) for a in AX5)
        self.cells = list(itertools.product(*[self.grid[a] for a in AX5]))         # C order == reshape(self.shape)
        self.ncell = len(self.cells)
        self.nr = np.array([(c[0] > 0) + (c[1] > 0) + (c[2] > 0) + (c[3] > 0) + c[4] for c in self.cells], float)
        self.micros = [m for m in MICROS[name] if m <= self.cap]
        fee = E._fees().get(self.rid, {"eval_fee": 0.0, "activation": 0.0})
        self.fee, self.activation = float(fee["eval_fee"]), float(fee.get("activation", 0.0))

    def cell_dict(self, ci: int) -> dict:
        return dict(zip(AX5, self.cells[ci]))

    def cell_index(self, cell) -> int:
        return self.cells.index(tuple(cell[a] for a in AX5) if isinstance(cell, dict) else tuple(cell))


_FIRMS: dict = {}


def firm(name: str) -> Firm:
    if name not in _FIRMS:
        _FIRMS[name] = Firm(name)
    return _FIRMS[name]


def stable(v: np.ndarray) -> np.ndarray:
    """Median of a cell and its +-1-step neighbours on every axis (N-D array; edges use the neighbours that exist)."""
    st = [v]
    for ax in range(v.ndim):
        for s in (-1, 1):
            w = np.full_like(v, np.nan)
            dst, src = [slice(None)] * v.ndim, [slice(None)] * v.ndim
            dst[ax], src[ax] = (slice(0, -1), slice(1, None)) if s == 1 else (slice(1, None), slice(0, -1))
            w[tuple(dst)] = v[tuple(src)]
            st.append(w)
    return np.nanmedian(np.stack(st), 0)


# ------------------------------------------------------------------ trade sets

class Base:
    """One trade set (source x session) on the session calendar: arrays sorted by (day, entry). `rows(n)` -> walk tuples at n micros."""
    _n = 0

    def __init__(self, name: str, cal: np.ndarray, date, te, tx, side, g, mae, mfe, risk, meta: dict | None = None):
        Base._n += 1
        self.bid, self.name, self.meta = Base._n, name, dict(meta or {})
        o = np.lexsort((te, date))
        date = np.asarray(date, np.int64)[o]
        pos = np.searchsorted(cal, date)
        if len(date) and (pos.max() >= len(cal) or not np.array_equal(cal[pos], date)):
            raise ValueError(f"{name}: trade dates off the session calendar")
        self.d = pos
        self.te, self.tx, self.side, self.g, self.mae, self.mfe, self.risk = (np.asarray(a)[o] for a in (te, tx, side, g, mae, mfe, risk))
        self.n = len(date)
        self.D = len(cal)
        self._rows: dict = {}
        self._daily: dict = {}

    @staticmethod
    def from_tr(name, cal, tr, sess="all", meta=None) -> "Base":
        m = E._sess_mask(tr, sess)
        return Base(name, cal, tr.date[m], tr.te[m], tr.tx[m], tr.side[m], tr.g[m], tr.mae[m], tr.mfe[m], tr.risk[m], meta)

    @property
    def fam(self):
        return self.meta.get("fam")

    @property
    def sess(self):
        return self.meta.get("sess")

    def rows(self, n: int) -> list:
        """[(day index, [(te, bid, walk tuple, mfe), ...])] for non-empty days at n micros."""
        if n not in self._rows:
            out, cur, last = [], None, -1
            for k in range(self.n):
                i = int(self.d[k])
                if i != last:
                    cur = []
                    out.append((i, cur))
                    last = i
                cur.append((int(self.te[k]), self.bid, (int(self.te[k]), int(self.tx[k]), int(self.side[k]), float(self.g[k]),
                                                        float(self.mae[k]), n, float(self.risk[k]), self.bid), float(self.mfe[k])))
            self._rows[n] = out
        return self._rows[n]

    def daily(self, n: int) -> np.ndarray:
        """Raw sized (no day rules) P&L per session at n micros."""
        if n not in self._daily:
            self._daily[n] = np.bincount(self.d, weights=n * self.g / 10.0 - E.cost(n), minlength=self.D) if self.n else np.zeros(self.D)
        return self._daily[n]

    def net(self, n: int, upto: int | None = None) -> float:
        """Raw sized net P&L; `upto` = only the sessions with calendar index < upto (walk-forward: no data from the test period on)."""
        d = self.daily(n)
        return float((d if upto is None else d[:upto]).sum())


class PV:
    """Port-like object (days / mfe lists for evalcore.walk) for a list of members [(Base, micros)]."""

    def __init__(self, members, D: int):
        self.members = list(members)
        per = [[] for _ in range(D)]
        for b, n in self.members:
            for i, lst in b.rows(int(n)):
                per[i].extend(lst)
        self.days, self.mfe = [], []
        for lst in per:
            if len(lst) > 1:
                lst.sort(key=lambda x: (x[0], x[1]))
            self.days.append([x[2] for x in lst])
            self.mfe.append([x[3] for x in lst])
        self.mx = max((len(x) for x in self.days), default=0)
        self.n_trades = sum(len(x) for x in self.days)
        self._U = None

    @property
    def U(self) -> np.ndarray:
        """Per-day upper bound of any take trigger: sum of the trades' positive best points (exact shortcut for target_take re-walks)."""
        if self._U is None:
            self._U = np.array([sum(max(t[5] * f / 10.0 - E.cost(t[5]), 0.0) for t, f in zip(ts, fs)) for ts, fs in zip(self.days, self.mfe)])
        return self._U


def sig_of(members) -> tuple:
    return tuple(sorted((b.bid, int(n)) for b, n in members))


# ------------------------------------------------------------------ context (calendar, bases, controls)

def _read_ledger(path):
    return list(csv.DictReader(Path(path).open()))


def sources(ledger=SNAP_L, prefixes=("hm-", "hm2-", "fp-")) -> dict:
    """{key -> dict(src, fam, tf, params)} for heat-map cells (ledger stage sizing, key prefix in `prefixes`) + screen runs.
    Keys are 'hm-...#cell' for cells and the job key for screen runs (matching out/shortlist*.csv strategy_id parts)."""
    out = {}
    for r in _read_ledger(ledger):
        if r["stage"] in ("sizing",) and r["key"].startswith(prefixes) and r["grid_id"] and r["cell"] != "":
            p = json.loads(r["params_json"])
            tf = int(p.pop("tf"))
            p.pop("sess", None)
            out[f"{r['key']}#{r['cell']}"] = dict(src=f"{r['grid_id']}#{r['cell']}", fam=r["strategy"].replace(E.DRAFT_PREFIX, ""), tf=tf, params=p)
        elif r["stage"] == "screen" and r["run_id"]:
            p = json.loads(r["params_json"])
            out[r["key"]] = dict(src=r["run_id"], fam=r["strategy"].replace(E.DRAFT_PREFIX, ""), tf=int(p["tf"]), params={})
    return out


class Ctx:
    """Session calendar + lazily built Base objects (real candidates and their day-matched controls)."""

    def __init__(self, cal, ledger=SNAP_L, jobs=SNAP_J, K: int = 10):
        self.cal = np.asarray(cal, np.int64)
        self.D = len(self.cal)
        self.S = self.D - H + 1
        self.idx5 = np.arange(self.S)[:, None] + np.arange(H)
        self.ledger, self.jobs, self.K = ledger, jobs, K
        self.bases: dict = {}
        self._ctl: dict = {}
        self._pools: dict = {}
        self.cands: dict = {}

    @staticmethod
    def calendar(extra_dates=()) -> np.ndarray:
        ords = {dt.date.fromisoformat(d).toordinal() for d in E.tape_sessions("2021-01-01", "2024-12-31")}
        return np.array(sorted(ords | {int(x) for x in extra_dates}), np.int64)

    def base(self, cand: dict) -> Base:
        """cand = {cid, src, sess, fam, tf, params, key?, ctrl_srcs?}."""
        cid = cand["cid"]
        if cid not in self.bases:
            tr = E.load(cand["src"])
            b = Base.from_tr(cid, self.cal, tr, cand.get("sess", "all"), meta=cand)
            self.bases[cid] = b
            self.cands[cid] = cand
        return self.bases[cid]

    def pool_tr(self, cand: dict):
        if cand.get("ctrl_srcs") is not None:
            srcs = list(cand["ctrl_srcs"])
            flag = "given"
        else:
            pl = E.resolve_pool(E.profile_from(cand.get("fam"), dict(cand.get("params") or {}, tf=cand.get("tf", 5))), self.ledger, self.jobs)
            srcs, flag = pl["srcs"], pl["flag"] or "exact"
            if not srcs:
                raise RuntimeError(f"no control pool for {cand['cid']}: {flag}")
        k = tuple(x if isinstance(x, str) else id(x) for x in srcs)
        if k not in self._pools:
            self._pools[k] = E.concat_tr([E.load(s) for s in srcs])
        return self._pools[k], flag

    def controls(self, cand_or_base) -> list:
        """K day-matched control Bases of a candidate (same dates / session trade counts; seeded by the candidate id)."""
        b = cand_or_base if isinstance(cand_or_base, Base) else self.base(cand_or_base)
        if b.bid not in self._ctl:
            cand = self.cands[b.name]
            pool, flag = self.pool_tr(cand)
            tr = E.load(cand["src"])
            m = E._sess_mask(tr, cand.get("sess", "all"))
            sub = SimpleNamespace(date=tr.date[m], sess=tr.sess[m], n=int(m.sum()))
            cs = E.daymatched_controls(sub, pool, K=self.K, seed=zlib.crc32(b.name.encode()) % 100000, mask=None,
                                       carry=("side", "g", "mae", "mfe", "risk", "sess"))
            self._ctl[b.bid] = [Base(f"{b.name}~c{k}", self.cal, c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["mfe"], c["risk"],
                                     dict(b.meta, control=k, pool_flag=flag)) for k, c in enumerate(cs)]
        return self._ctl[b.bid]


# ------------------------------------------------------------------ walk / race of one rules cell

def norm_key(pv: PV, dl, dtk, ds, mt) -> tuple:
    """Cache key of a walk: rules that cannot matter are zeroed (one trade a day -> max_day_tr / day_lock no-ops)."""
    mt_e = 0 if mt >= pv.mx else mt
    dl_e = 0 if (pv.mx <= 1 or mt_e == 1) else dl
    if pv.mx <= 1:
        mt_e = 0
    return (dl_e, dtk, ds, mt_e)


def make_A(pv: PV, fm: Firm, key: tuple) -> E.DayArr:
    """Day walk for one rule key at the members' own micros; target_take re-walks of days that cannot reach the level are skipped (exact)."""
    dl, dtk, ds, mt = key
    A = E.walk(pv, fm.cap, (int(mt), float(ds), float(dl), 1.0, 1.0, True), want_chk=True, micros=None, dll=fm.dll, day_take=float(dtk))
    orig, U = A.rewalk, pv.U

    def rw(i, tt):
        if tt > U[i] + 1e-6:
            return float(A.tot[i]), float(A.worst[i]), bool(A.trd[i]), float(A.wreal[i])
        return orig(i, tt)

    A.rewalk = rw
    return A


def race_cell(ctx: Ctx, fm: Firm, A: E.DayArr, tt: int, model: str):
    return E.race(ctx.idx5, A, fm.r, model, True, bool(tt))


def grid_outcomes(ctx: Ctx, fm: Firm, pv: PV, models, cells=None, keep_A: bool = False):
    """Outcome / day arrays [ncell, S] per model for the firm's whole rules grid (or the listed cell indices)."""
    cells = range(fm.ncell) if cells is None else list(cells)
    res = {m: (np.zeros((fm.ncell, ctx.S), np.int8), np.zeros((fm.ncell, ctx.S), np.int16)) for m in models}
    cache, As = {}, {}
    for ci in cells:
        dl, dtk, ds, mt, tt = fm.cells[ci]
        key = norm_key(pv, dl, dtk, ds, mt)
        if key not in cache:
            cache[key] = make_A(pv, fm, key)
        A = cache[key]
        for m in models:
            o, d = race_cell(ctx, fm, A, tt, m)
            res[m][0][ci], res[m][1][ci] = o, d
        if keep_A:
            As[ci] = A
    return (res, As) if keep_A else res


# ------------------------------------------------------------------ scoring with memo

OBJECTIVES = {"p5": {5: 1.0}, "fast": {1: 0.25, 2: 0.25, 3: 0.25, 5: 0.25}}      # weights on P(pass <= k days)


class Scorer:
    """Memoised grid scores. W = start weights [S, Q] (column 0 = uniform = the full window; other columns: train windows).
    score(members) -> dict(P=[ncell,Q] objective under the primary model, ST=[ncell,Q] stable version). Objective `obj` = weights on
    P(pass <= k days): 'p5' (default, the spec's stable P5) or 'fast' (mean of P1, P2, P3, P5: the user's short-time priority)."""

    def __init__(self, ctx: Ctx, fm: Firm, W: np.ndarray | None = None, model: str | None = None, cap_entries: int = 4000, obj="p5"):
        self.ctx, self.fm = ctx, fm
        self.W = np.full((ctx.S, 1), 1.0 / ctx.S) if W is None else np.asarray(W, float)
        self.model = model or fm.prim
        self.memo: OrderedDict = OrderedDict()
        self.cap = cap_entries
        self.evals = 0
        self.obj = OBJECTIVES[obj] if isinstance(obj, str) else dict(obj)

    def score(self, members) -> dict:
        k = sig_of(members)
        if k in self.memo:
            self.memo.move_to_end(k)
            return self.memo[k]
        gate()
        pv = PV(members, self.ctx.D)
        o, d = grid_outcomes(self.ctx, self.fm, pv, (self.model,))[self.model]
        if list(self.obj) == [5]:
            F = (o == 1).astype(np.float64)
        else:
            F = sum(w * ((o == 1) & (d <= kk)) for kk, w in self.obj.items()).astype(np.float64)
        P = np.einsum('cs,sq->cq', F, self.W).astype(np.float32)
        ST = np.stack([stable(P[:, q].reshape(self.fm.shape)).reshape(-1) for q in range(P.shape[1])], 1)
        self.memo[k] = r = {"P": P, "ST": ST, "trades": pv.n_trades}
        self.evals += 1
        if len(self.memo) > self.cap:
            self.memo.popitem(last=False)
        return r

    def best(self, members, q: int = 0) -> tuple:
        """-> (cell index, stable P5, cell P5): argmax of the stable score with the pass-2 tie-breaks."""
        r = self.score(members)
        sc = r["ST"][:, q] - 1e-7 * self.fm.nr - 1e-9 * np.arange(self.fm.ncell)
        ci = int(np.argmax(sc))
        return ci, float(r["ST"][ci, q]), float(r["P"][ci, q])


# ------------------------------------------------------------------ guards

def feasible(fm: Firm, members) -> bool:
    """Static cap: members whose sessions can overlap (same session, or 'all') share the firm cap."""
    tot = {}
    for b, n in members:
        s = b.sess or "all"
        tot.setdefault(s, 0)
        tot[s] += int(n)
    if any(v > fm.cap for v in tot.values()):
        return False
    alls = tot.get("all", 0)
    return not alls or all(v + alls <= fm.cap for k, v in tot.items() if k != "all")


def net_shares(members, upto: int | None = None) -> list:
    """Each member's share of the portfolio's POSITIVE raw sized net P&L (no day rules; losing members count 0); nan when nothing is positive.
    upto: calendar-index cutoff (sessions >= upto are ignored), used by the walk-forward so the guard never sees the test period."""
    pos = [max(b.net(int(n), upto), 0.0) for b, n in members]
    tot = sum(pos)
    return [x / tot if tot > 0 else float("nan") for x in pos]


def share_ok(members, upto: int | None = None) -> bool:
    if len(members) < 3:
        return True
    s = net_shares(members, upto)
    return all(x == x and x <= MAX_SHARE + 1e-12 for x in s)


def dup_count(members) -> int:
    """# of member pairs sharing family + session."""
    c = 0
    for (a, _), (b, _) in itertools.combinations(members, 2):
        c += (a.fam is not None and a.fam == b.fam and a.sess == b.sess)
    return c


# ------------------------------------------------------------------ search

def _adj(sc: Scorer, members, q: int = 0, dup_pen: float = DUP_PEN):
    ci, st, p = sc.best(members, q)
    return st - dup_pen * dup_count(members), ci, st, p


def greedy(ctx: Ctx, sc: Scorer, pool: list, q: int = 0, max_members: int = MAX_MEMBERS, min_gain: float = MIN_GAIN,
           dup_pen: float = DUP_PEN, verbose: bool = False, start: list | None = None, force_min: int = 3,
           passes: int = 3, share_upto: int | None = None) -> dict:
    """Greedy forward selection + local resize/swap passes. pool = [Base]. -> dict(history, best2, final, singles).
    history[i] = {members:[(cid,micros)], cell, stable, p5, adj, gain}; `final` = the reported portfolio (>= force_min members when the
    pool allows: forced additions are flagged)."""
    fm = sc.fm
    t0 = time.time()
    hist, singles = [], []
    cur = list(start or [])
    if not cur:
        best = None
        for b in pool:
            for n in fm.micros:
                m = [(b, n)]
                adj, ci, st, p = _adj(sc, m, q, dup_pen)
                singles.append((adj, b.name, n, ci, st, p))
                if best is None or adj > best[0] + 1e-12:
                    best = (adj, m, ci, st, p)
        cur = best[1]
        hist.append(_step(fm, cur, best[2], best[3], best[4], best[0], None))
        if verbose:
            print(f"[{fm.name}] single {_lab(cur)} stable={best[3]:.3f} ({time.time()-t0:.0f}s, {sc.evals} evals)", flush=True)
    cur_adj = hist[-1]["adj"] if hist else _adj(sc, cur, q, dup_pen)[0]
    while len(cur) < max_members:
        bestc = None
        used = {b.bid for b, _ in cur}
        for b in pool:
            if b.bid in used:
                continue
            for n in fm.micros:
                m = cur + [(b, n)]
                if not feasible(fm, m) or not share_ok(m, share_upto):
                    continue
                adj, ci, st, p = _adj(sc, m, q, dup_pen)
                if bestc is None or adj > bestc[0] + 1e-12:
                    bestc = (adj, m, ci, st, p)
        if bestc is None:
            break
        gain = bestc[0] - cur_adj
        forced = gain <= min_gain and len(cur) < force_min
        if gain <= min_gain and not forced:
            break
        cur, cur_adj = bestc[1], bestc[0]
        hist.append(_step(fm, cur, bestc[2], bestc[3], bestc[4], bestc[0], gain, forced))
        if verbose:
            print(f"[{fm.name}] +{_lab(cur[-1:])} -> {len(cur)} members stable={bestc[3]:.3f} gain={gain:+.3f}{' FORCED' if forced else ''}"
                  f" ({time.time()-t0:.0f}s, {sc.evals} evals)", flush=True)
    hist = _local(ctx, sc, pool, hist, cur, cur_adj, q, dup_pen, min_gain, verbose, passes, share_upto)
    two = [h for h in hist if len(h["members"]) == 2]
    full = [h for h in hist if len(h["members"]) >= 3]
    final = max(full, key=lambda h: h["adj"]) if full else hist[-1]
    return {"history": hist, "best2": (max(two, key=lambda h: h["adj"]) if two else None), "final": final,
            "single": hist[0], "singles": sorted(singles, key=lambda x: -x[0])[:10], "evals": sc.evals, "secs": time.time() - t0}


def _lab(members) -> str:
    return "+".join(f"{b.name}@{n}" for b, n in members)


def _step(fm, members, ci, st, p, adj, gain, forced=False) -> dict:
    return {"members": [(b.name, int(n)) for b, n in members], "_m": list(members), "cell": fm.cell_dict(ci), "ci": ci, "stable": st, "p5": p,
            "adj": adj, "gain": gain, "forced": bool(forced)}


def _local(ctx, sc, pool, hist, cur, cur_adj, q, dup_pen, min_gain, verbose, passes: int = 3, share_upto: int | None = None):
    """Local passes on the final member set: resize one member, then swap one member for a pool candidate; accept the best gain > min_gain."""
    fm = sc.fm
    if len(cur) < 2:
        return hist
    for _ in range(passes):
        bestc = None
        used = {b.bid for b, _ in cur}
        for i, (b0, n0) in enumerate(cur):
            opts = [(b0, n) for n in fm.micros if n != n0] + [(b, n) for b in pool if b.bid not in used for n in fm.micros]
            for b, n in opts:
                m = cur[:i] + [(b, n)] + cur[i + 1:]
                if not feasible(fm, m) or not share_ok(m, share_upto):
                    continue
                adj, ci, st, p = _adj(sc, m, q, dup_pen)
                if bestc is None or adj > bestc[0] + 1e-12:
                    bestc = (adj, m, ci, st, p, i)
        if bestc is None or bestc[0] - cur_adj <= min_gain:
            break
        gain = bestc[0] - cur_adj
        cur, cur_adj = bestc[1], bestc[0]
        hist.append(_step(fm, cur, bestc[2], bestc[3], bestc[4], bestc[0], gain) | {"local": True})
        if verbose:
            print(f"[{fm.name}] local -> {_lab(cur)} stable={bestc[3]:.3f} gain={gain:+.3f}", flush=True)
    return hist


# ------------------------------------------------------------------ candidate pool (current shortlist + wf survivors)

FIRM_CSV = {"lucid": "lucid", "lucidpro": "lucidpro", "lucidpro_nodll": "lucidpro_nodll", "apex": "apex", "apex_eod": "apex"}
WF_FIRM = {"lucid": "lucid_flex", "lucidpro": "lucidpro", "lucidpro_nodll": "lucidpro_nodll", "apex": "apex", "apex_eod": "apex"}


def current_pool(fname: str, top: int = 20, ledger=SNAP_L, shortlist=OUT / "shortlist_all_models.csv", wf=OUT / "wf_offline.csv") -> list:
    """Candidate dicts for a firm: top `top` rows of the shortlist by the firm's primary-model P5 (apex*: max with the intraday-optimal
    rules' P5) + the wf_offline survivors (survive == 1; best `top` by OOS P5 per model). Deduplicated on (source, session).
    apex_eod has no shortlist of its own: it reuses the apex pool."""
    src = sources(ledger)
    out, seen = [], set()

    def add(key, sess, how, **kw):
        d = src.get(key)
        if d is None:
            return
        k = (d["src"], sess)
        if k in seen:
            return
        seen.add(k)
        out.append(dict(cid=f"{key}|{sess}", key=key, sess=sess, how=how, **d, **kw))

    fm = firm(fname)
    rows = [r for r in _read_ledger(shortlist) if r["firm"] == FIRM_CSV[fname]]

    def rk(r):
        p = float(r["primary_p5"] or 0)
        return max(p, float(r.get("intra_opt_p5") or 0)) if fm.prim == "intraday" else p
    for r in sorted(rows, key=rk, reverse=True)[:top]:
        add(r["strategy_id"].split("|")[1], r["sess"], "shortlist", rank_p5=rk(r))
    if Path(wf).exists():
        w = [r for r in _read_ledger(wf) if r["firm"] == WF_FIRM[fname] and r["survive"] == "1"]
        for mod in ("intraday", "eod") if fm.prim == "intraday" else ("eod", "intraday"):
            for r in sorted([x for x in w if x["model"] == mod], key=lambda x: -float(x["oos_p5"]))[:top]:
                add(r["is_cfg"], r["sess"], f"wf_{mod}", wf_oos_p5=float(r["oos_p5"]))
    return out


def make_ctx(fnames=FIRM_ALL, top: int = 20, K: int = 10, ledger=SNAP_L, jobs=SNAP_J):
    """-> (ctx, {firm: [Base]}) over the union of the firms' current pools, on one shared calendar."""
    pools = {f: current_pool(f, top, ledger) for f in fnames}
    allc = {c["cid"]: c for p in pools.values() for c in p}
    trs = {cid: E.load(c["src"]) for cid, c in allc.items()}
    cal = Ctx.calendar(np.concatenate([t.date for t in trs.values()]) if trs else ())
    ctx = Ctx(cal, ledger, jobs, K)
    return ctx, {f: [ctx.base(c) for c in pools[f]] for f in fnames}


# ------------------------------------------------------------------ diagnostics

def overlap_stats(pv: PV, cap: int) -> dict:
    """Raw (before day rules) overlap of the merged trades: entries while another trade is open, opposite-side overlaps
    (same-time opposite positions), max concurrent micros vs the firm cap."""
    ov = opp = cv = mc = 0
    for trs in pv.days:
        opens = []                                              # (tx, side, n)
        for te, tx, sd, _, _, n, _, _ in trs:
            opens = [o for o in opens if o[0] > te]
            if opens:
                ov += 1
                opp += any(o[1] != sd for o in opens)
            conc = n + sum(o[2] for o in opens)
            mc = max(mc, conc)
            cv += conc > cap
            opens.append((tx, sd, n))
    return {"overlap_entries": ov, "opposite_conflicts": opp, "max_concurrent_micros": mc, "cap_violations": cv, "cap": cap,
            "cap_ok": cv == 0}


def corr_matrix(bases: list, n: int = 10):
    """Daily-P&L correlation (1 NQ = 10 micros, costs in, raw) over every session of the calendar + the drawdown-day overlap matrix.
    Drawdown day of a member = a session it traded with P&L in its worst 20% of trade days (and < 0). overlap[i][j] = share of i's
    drawdown days on which j ALSO has a drawdown day; lose[i][j] = share on which j ends the day negative."""
    X = np.stack([b.daily(n) for b in bases])
    C = np.corrcoef(X) if len(bases) > 1 else np.ones((1, 1))
    C = np.nan_to_num(C, nan=0.0)
    traded = np.stack([np.bincount(b.d, minlength=b.D) > 0 for b in bases])
    dd = np.zeros_like(traded)
    for i in range(len(bases)):
        xi = X[i][traded[i]]
        thr = min(np.percentile(xi, 20), 0.0) if len(xi) else 0.0
        dd[i] = traded[i] & (X[i] <= thr) & (X[i] < 0)
    lose = X < 0
    ov = np.array([[float((dd[i] & dd[j]).sum() / max(dd[i].sum(), 1)) for j in range(len(bases))] for i in range(len(bases))])
    lo = np.array([[float((dd[i] & lose[j]).sum() / max(dd[i].sum(), 1)) for j in range(len(bases))] for i in range(len(bases))])
    return {"names": [b.name for b in bases], "corr": C, "dd_overlap": ov, "lose_overlap": lo, "dd_days": dd.sum(1).tolist(),
            "multi_dd_share": float((dd.sum(0) >= 2).sum() / max((dd.sum(0) >= 1).sum(), 1))}


# ------------------------------------------------------------------ report of one portfolio

def _detail(o, d, boots: int, seed: int = E.SEED) -> dict:
    ps, bs = o == 1, o == 2
    x = {f"p{k}": float((ps & (d <= k)).mean()) for k in (1, 2, 3, 5)}
    x["bust5"] = float(bs.mean())
    x["med_days"] = float(np.median(d[ps])) if ps.any() else None
    if boots:
        cis = E.block_ci([ps & (d <= k) for k in (1, 2, 3, 5)], boots=boots, seed=seed)
        for k, c in zip((1, 2, 3, 5), cis):
            x[f"ci_p{k}"] = c
    return x


def exec_stats(ctx: Ctx, fm: Firm, members, ci: int) -> dict:
    """Who actually trades under the shared rules cell: executed entries and executed net P&L per member over the whole calendar (base day walk:
    day rules + the firm's daily limit, no target_take truncation). The raw net guard (net_shares) looks at each member alone; with max_day_tr / day_lock
    / day_take / day_stop the merged stream starves later-session members (e.g. max_day_tr=1: only the first signal of the day trades), so this is the
    guard that matches what the account really does. -> dict(members=[{name, micros, executed, net, trade_share, net_share}], max_net_share, dead)."""
    pv = PV(members, ctx.D)
    dl, dtk, ds, mt = norm_key(pv, *fm.cells[ci][:4])
    A = E.walk(pv, fm.cap, (int(mt), float(ds), float(dl), 1.0, 1.0, False), want_chk=False, micros=None, dll=fm.dll, day_take=float(dtk), collect=True)
    ex = A.st["exec"]
    rows = [{"name": b.name, "micros": int(n), "executed": int(ex.get(b.bid, [0, 0.0])[0]), "net": float(ex.get(b.bid, [0, 0.0])[1])} for b, n in members]
    tc, pos = sum(r["executed"] for r in rows), sum(max(r["net"], 0.0) for r in rows)
    for r in rows:
        r["trade_share"] = r["executed"] / tc if tc else float("nan")
        r["net_share"] = max(r["net"], 0.0) / pos if pos > 0 else float("nan")
    ns = [r["net_share"] for r in rows if r["net_share"] == r["net_share"]]
    return {"members": rows, "max_net_share": max(ns) if ns else None, "dead": [r["name"] for r in rows if r["trade_share"] == r["trade_share"] and r["trade_share"] < 0.05],
            "negative": [r["name"] for r in rows if r["net"] <= 0 and r["executed"] > 0]}


def exec_flags(ex: dict, n_members: int) -> list:
    """Report flags from exec_stats (only meaningful with >= 2 members)."""
    out = []
    if n_members < 2:
        return out
    if ex["dead"]:
        out.append(f"DEAD_MEMBERS: {len(ex['dead'])}/{n_members} members execute <5% of the portfolio's trades under the shared rules ({', '.join(ex['dead'])})")
    if ex["max_net_share"] is not None and ex["max_net_share"] > MAX_SHARE and n_members >= 3:
        top = max(ex["members"], key=lambda r: r["net_share"] if r["net_share"] == r["net_share"] else -1)
        out.append(f"EXEC_NET_SHARE {ex['max_net_share']:.0%}: {top['name']} earns that share of the positive executed P&L under the shared rules (raw guard is on standalone P&L)")
    if ex["negative"]:
        out.append(f"NEGATIVE_EXEC_MEMBER: {', '.join(ex['negative'])} lose money under the shared rules")
    return out


def report(ctx: Ctx, fm: Firm, members, ci: int, controls: bool = True, boots: int = 2000, ref_single=None) -> dict:
    """Full report of (members, rules cell ci) under all three breach models + controls lift + diagnostics."""
    pv = PV(members, ctx.D)
    res, As = grid_outcomes(ctx, fm, pv, MODELS, cells=[ci], keep_A=True)
    A = As[ci]
    out = {"firm": fm.name, "rules_id": fm.rid, "unconfirmed": not fm.confirmed, "primary": fm.prim, "cell": fm.cell_dict(ci),
           "members": [{"name": b.name, "micros": int(n), "fam": b.fam, "sess": b.sess, "trades": b.n, "raw_net": b.net(int(n))} for b, n in members]}
    sh = net_shares(members)
    for m, s in zip(out["members"], sh):
        m["net_share"] = s
    out["guards"] = {"n_members": len(members), "ge3": len(members) >= 3, "max_net_share": max(sh) if sh and all(x == x for x in sh) else None,
                     "share_ok": share_ok(members), "dup_pairs": dup_count(members), "static_cap_ok": feasible(fm, members)}
    ps_all = {}
    for m in MODELS:
        o, d = res[m][0][ci], res[m][1][ci]
        out[m] = _detail(o, d, boots if m in (fm.prim, "eod", "intraday") else 0)
        ps_all[m] = (o == 1, d)
    P = out[fm.prim]
    out["headline"] = {k: P[k] for k in ("p1", "p2", "p3", "p5", "bust5", "med_days")} | {"ci_p5": P.get("ci_p5"), "model": fm.prim}
    out["consistency"] = ({"enforced": True, "pct": fm.r["consistency"], "note": "satisfied at pass by construction of the race"}
                          if fm.r.get("consistency") else {"enforced": False})
    st = A.st
    out["walk"] = {"executed": st["executed"], "skipped": st["skipped"], "clipped": st["clipped"], "opposite_conflicts_executed": int(st["conflicts"]),
                   "overlap_entries_executed": st["overlap"], "max_concurrent_micros": st["max_conc"], "cap_violations": int(st["cap_viol"])}
    out["raw_overlap"] = overlap_stats(pv, fm.cap)
    out["exec"] = exec_stats(ctx, fm, members, ci)
    out["series"] = E._series(A)
    if len(members) > 1:              # member attribution under the SAME rules: standalone walk and leave-one-out marginal net
        key = norm_key(pv, *fm.cells[ci][:4])
        for i, (b, n) in enumerate(members):
            solo = PV([(b, n)], ctx.D)
            out["members"][i]["net_standalone_rules"] = float(make_A(solo, fm, norm_key(solo, *fm.cells[ci][:4])).tot.sum())
            rest = PV([m for j, m in enumerate(members) if j != i], ctx.D)
            out["members"][i]["net_marginal_rules"] = float(A.tot.sum() - make_A(rest, fm, norm_key(rest, *fm.cells[ci][:4])).tot.sum())
        ps_ = [max(m["net_standalone_rules"], 0.0) for m in out["members"]]
        if sum(ps_) > 0 and len(members) >= 3 and max(ps_) / sum(ps_) > MAX_SHARE:
            out["flags"] = out.get("flags", []) + [f"MEMBER_SHARE_UNDER_RULES {max(ps_) / sum(ps_):.0%} of positive standalone net"]
    yrs = np.array([dt.date.fromordinal(int(o)).year for o in ctx.cal])
    ynet = {int(y): float(A.tot[yrs == y].sum()) for y in np.unique(yrs)}
    tot = sum(ynet.values())
    out["year_net"] = ynet
    out.setdefault("flags", [])
    out["flags"] += exec_flags(out["exec"], len(members))
    if tot > 0 and max(ynet.values()) / tot > 0.6:
        out["flags"].append(f"ONE_YEAR_CONCENTRATION {max(ynet, key=ynet.get)}: {max(ynet.values())/tot:.0%} of net")
    if tot <= 0:
        out["flags"].append("NET_NOT_POSITIVE under the rules")
    if out["guards"]["max_net_share"] is None and len(members) >= 3:
        out["flags"].append("RAW_NET_NOT_POSITIVE")
    p5 = P["p5"]
    out["econ"] = {"model": fm.prim, "eval_fee": fm.fee, "activation": fm.activation, "fees_are_assumptions": True,
                   "cost_per_funded_5d": (fm.fee / p5 + fm.activation) if p5 > 0 else None}
    if controls:
        out["lift"] = control_lift(ctx, fm, members, ci, ps_all, boots)
        L = out["lift"][fm.prim]
        if L["ci"][0] <= 0:
            out["flags"].append(f"WARN_NO_EDGE: lift {L['lift']:+.3f} vs day-matched random, 95% CI [{L['ci'][0]:+.3f},{L['ci'][1]:+.3f}] includes 0")
    if ref_single is not None:
        out["vs_single"] = {"single": ref_single.get("label"), "single_stable_p5": ref_single["stable"], "single_cell_p5": ref_single["p5"],
                            "delta_cell_p5": float(out["headline"]["p5"]) - ref_single["p5"]}
    return out


def control_lift(ctx: Ctx, fm: Firm, members, ci: int, ps_all: dict, boots: int = 2000) -> dict:
    """Day-matched control portfolio k = every member replaced by its own k-th control (same micros, same rules cell). Lift per model =
    P5(real) - mean_k P5(control k); CI = block bootstrap of the paired per-start difference."""
    ctrls = [ctx.controls(b) for b, _ in members]
    K = min(len(c) for c in ctrls)
    cp = {m: [] for m in MODELS}
    for k in range(K):
        pv = PV([(c[k], n) for c, (_, n) in zip(ctrls, members)], ctx.D)
        r = grid_outcomes(ctx, fm, pv, MODELS, cells=[ci])
        for m in MODELS:
            cp[m].append(r[m][0][ci] == 1)
    out = {"K": K, "pool_flag": [c[0].meta.get("pool_flag") for c in ctrls]}
    for m in MODELS:
        c = np.mean(np.stack(cp[m]), 0)
        real = ps_all[m][0].astype(float)
        diff = real - c
        ci_ = E.block_ci([diff], boots=boots)[0] if boots else [None, None]
        out[m] = {"real_p5": float(real.mean()), "ctrl_p5": float(c.mean()), "ctrl_p5_sd": float(np.std([x.mean() for x in cp[m]])),
                  "lift": float(diff.mean()), "ci": ci_}
    return out


# ------------------------------------------------------------------ walk-forward (quarterly, trailing 12 months)

QUARTERS = [(y, q) for y in (2022, 2023, 2024) for q in (1, 2, 3, 4) if (y, q) >= (2022, 3)]          # 10 test quarters


def _o(y, m, d=1):
    return dt.date(y, m, d).toordinal()


def q_bounds(y, q):
    """(test start, test end (excl), train start = 12 months before) as ordinals."""
    m = 3 * (q - 1) + 1
    return _o(y, m), (_o(y, m + 3) if q < 4 else _o(y + 1, 1)), _o(y - 1, m)


def wf_windows(cal: np.ndarray):
    """-> (W [S, Q] normalised train weights, tests = per-quarter arrays of start indices, oos = all test start indices).
    Start i runs sessions i..i+4. Train starts: the 12 months before Q whose 5th session is before Q (no leakage)."""
    D = len(cal)
    S = D - H + 1
    d0, d4 = cal[:S], cal[H - 1:]
    W, tests = np.zeros((S, len(QUARTERS))), []
    for j, (y, q) in enumerate(QUARTERS):
        a, b, lo = q_bounds(y, q)
        tr = (d0 >= lo) & (d4 < a)
        W[:, j] = tr / max(tr.sum(), 1)
        tests.append(np.flatnonzero((d0 >= a) & (d0 < b)))
    return W, tests, np.concatenate(tests)


def _combos(fm: Firm, members, full: bool):
    """Micros combinations for the fixed-set walk-forward: all choices when few, else the chosen micros +-1 step per member."""
    ch = fm.micros
    per = []
    for _, n in members:
        if full:
            per.append(list(ch))
        else:
            i = ch.index(n) if n in ch else int(np.argmin([abs(n - c) for c in ch]))
            per.append([ch[j] for j in (i - 1, i, i + 1) if 0 <= j < len(ch)])
    out = [c for c in itertools.product(*per)]
    return out


def wf_fixed(ctx: Ctx, fm: Firm, bases: list, micros0: list, W, tests, combos_full_max: int = 130) -> dict:
    """Member SET fixed; per test quarter select (micros per member, rules cell) on the trailing-12-month window by stable P5 of the
    primary model; test on the quarter's start days. -> dict(flags [S] (nan outside the OOS starts), picks per quarter, train_p5)."""
    members0 = list(zip(bases, micros0))
    allc = _combos(fm, members0, True)
    combos = allc if len(allc) <= combos_full_max else _combos(fm, members0, False)
    combos = [c for c in combos if feasible(fm, list(zip(bases, c)))]
    Q = W.shape[1]
    best = [None] * Q                                # (score, combo idx, cell)
    store = []
    for k, c in enumerate(combos):
        gate()
        pv = PV(list(zip(bases, c)), ctx.D)
        ps = grid_outcomes(ctx, fm, pv, (fm.prim,))[fm.prim][0] == 1
        store.append(ps)
        P = np.einsum('cs,sq->cq', ps.astype(np.float64), W)
        for j in range(Q):
            st = stable(P[:, j].reshape(fm.shape)).reshape(-1)
            sc = st - 1e-7 * fm.nr - 1e-9 * np.arange(fm.ncell) - 1e-10 * sum(c)
            ci = int(np.argmax(sc))
            if best[j] is None or sc[ci] > best[j][0] + 1e-12:
                best[j] = (float(sc[ci]), k, ci, float(st[ci]), float(P[ci, j]))
    flags = np.full(ctx.S, np.nan)
    picks = []
    for j in range(Q):
        _, k, ci, st, p = best[j]
        flags[tests[j]] = store[k][ci, tests[j]]
        picks.append({"quarter": f"{QUARTERS[j][0]}Q{QUARTERS[j][1]}", "micros": list(combos[k]), "cell": fm.cell_dict(ci), "train_stable": st,
                      "train_p5": p, "test_p5": float(store[k][ci, tests[j]].mean()) if len(tests[j]) else None})
    return {"flags": flags, "picks": picks, "combos": len(combos), "full_combos": len(combos) == len(allc)}


def _stitch(flags, oos):
    return np.asarray(flags)[oos]


def wf_fixed_with_controls(ctx: Ctx, fm: Firm, members, W, tests, oos, kc: int = 5, boots: int = 2000) -> dict:
    """wf_fixed on the real members and on kc day-matched control replicates (independent selection on each: the selection bias is
    replicated). -> stitched OOS P5 + CI, control OOS P5, lift (paired per start) + CI."""
    bases, micros0 = [b for b, _ in members], [n for _, n in members]
    real = wf_fixed(ctx, fm, bases, micros0, W, tests)
    x = _stitch(real["flags"], oos)
    out = {"variant": "fixed_set", "note": "member SET fixed from the full-window search (known look-ahead bias); micros + rules re-selected per quarter",
           "oos_p5": float(x.mean()), "ci_p5": E.block_ci([x], boots=boots)[0], "n_starts": int(len(x)), "picks": real["picks"],
           "mean_train_p5": float(np.mean([p["train_p5"] for p in real["picks"]])), "combos": real["combos"]}
    ctrls = [ctx.controls(b) for b in bases]
    reps = []
    for k in range(min(kc, min(len(c) for c in ctrls))):
        r = wf_fixed(ctx, fm, [c[k] for c in ctrls], micros0, W, tests)
        reps.append(_stitch(r["flags"], oos))
    if reps:
        c = np.mean(np.stack(reps), 0)
        diff = x - c
        out["ctrl_oos_p5"] = float(c.mean())
        out["ctrl_oos_p5_reps"] = [float(r.mean()) for r in reps]
        out["lift"] = float(diff.mean())
        out["lift_ci"] = E.block_ci([diff], boots=boots)[0]
    yrs = np.array([dt.date.fromordinal(int(ctx.cal[i])).year for i in oos])
    out["oos_p5_by_year"] = {int(y): float(x[yrs == y].mean()) for y in np.unique(yrs)}
    return out


def wf_reselect(ctx: Ctx, fm: Firm, pool: list, W, tests, oos, kc: int = 5, passes: int = 1, boots: int = 2000, verbose=False,
                picks_override: list | None = None) -> dict:
    """Whole greedy search (set + micros + rules) re-run per quarter on the trailing-12-month weights; tested on the next quarter.
    Lift: the chosen sets/rules of each quarter re-evaluated on kc day-matched control portfolios (same params; the selection is not
    replicated on controls, so this lift is an upper bound on the true edge).
    The 50%-net-share guard of the search only sees sessions before the test quarter (share_upto; fixed 2026-09-30: it used the whole window).
    picks_override = per-quarter picks [{members: [[name, micros]], cell, train_stable, train_p5}] from an audited search (e.g.
    wf_truncate.py, which re-runs the search on data truncated at each test-quarter start): skips the search, keeps the test + control logic."""
    sc = Scorer(ctx, fm, W=W)
    byname = {b.name: b for b in pool}
    picks, flags = [], np.full(ctx.S, np.nan)
    ctl_flags = [np.full(ctx.S, np.nan) for _ in range(kc)]
    for j in range(W.shape[1]):
        cut = int(np.searchsorted(ctx.cal, q_bounds(*QUARTERS[j])[0]))          # sessions before the test quarter: the only P&L the share guard may see
        if picks_override is not None:
            po = picks_override[j]
            h = {"_m": [(byname[n], int(m)) for n, m in po["members"]], "members": [(n, int(m)) for n, m in po["members"]], "cell": po["cell"],
                 "ci": fm.cell_index(po["cell"]), "stable": po["train_stable"], "p5": po["train_p5"]}
        else:
            g = greedy(ctx, sc, pool, q=j, passes=passes, share_upto=cut)
            h = g["final"]
        members = h["_m"]
        res = grid_outcomes(ctx, fm, PV(members, ctx.D), (fm.prim,), cells=[h["ci"]])[fm.prim][0][h["ci"]] == 1
        flags[tests[j]] = res[tests[j]]
        ctrls = [ctx.controls(b) for b, _ in members]
        for k in range(min(kc, min(len(c) for c in ctrls))):
            r = grid_outcomes(ctx, fm, PV([(c[k], n) for c, (_, n) in zip(ctrls, members)], ctx.D), (fm.prim,), cells=[h["ci"]])
            ctl_flags[k][tests[j]] = r[fm.prim][0][h["ci"]][tests[j]] == 1
        picks.append({"quarter": f"{QUARTERS[j][0]}Q{QUARTERS[j][1]}", "members": h["members"], "cell": h["cell"], "train_stable": h["stable"],
                      "train_p5": h["p5"], "test_p5": float(res[tests[j]].mean()) if len(tests[j]) else None,
                      "n_members": len(members)})
        if verbose:
            print(f"[{fm.name}] wf-reselect {picks[-1]['quarter']}: {picks[-1]['members']} train {h['stable']:.3f} test {picks[-1]['test_p5']}", flush=True)
    x = _stitch(flags, oos)
    cf = np.mean(np.stack([_stitch(f, oos) for f in ctl_flags]), 0)
    diff = x - cf
    yrs = np.array([dt.date.fromordinal(int(ctx.cal[i])).year for i in oos])
    return {"variant": "reselect", "oos_p5": float(x.mean()), "ci_p5": E.block_ci([x], boots=boots)[0], "n_starts": int(len(x)), "picks": picks,
            "mean_train_p5": float(np.mean([p["train_p5"] for p in picks])), "ctrl_oos_p5": float(cf.mean()), "lift": float(diff.mean()),
            "lift_ci": E.block_ci([diff], boots=boots)[0], "lift_note": "same-params control (selection not replicated on controls): upper bound",
            "oos_p5_by_year": {int(y): float(x[yrs == y].mean()) for y in np.unique(yrs)}, "evals": sc.evals}


# ------------------------------------------------------------------ multi-account

def multi_metrics(entries: list, boots: int = 2000) -> dict:
    """entries = [{firm, label, o, d, fee, activation}] (outcome / day arrays [S] of each account's eval attempt, all starting the same
    day). One eval attempt per account (5-day policy: abandon/reset after day 5). -> P(>=1 pass by day k), E[funded], costs."""
    o = np.stack([np.asarray(e["o"]) for e in entries], 1)
    d = np.stack([np.asarray(e["d"]) for e in entries], 1)
    ps, bs = o == 1, o == 2
    n = len(entries)
    any5 = ps.any(1)
    npass = ps.sum(1)
    fee = float(sum(e["fee"] for e in entries))
    act = float(sum(e["activation"] * ps[:, j].mean() for j, e in enumerate(entries)))
    ef = float(npass.mean())
    out = {"n": n, "accounts": [f"{e['firm']}:{e['label']}" for e in entries], "p_any5": float(any5.mean()),
           "ci_p_any5": E.block_ci([any5], boots=boots)[0] if boots else None,
           "p_any_by_day": [float((ps & (d <= k)).any(1).mean()) for k in range(1, H + 1)],
           "e_funded": ef, "e_funded_by_day": [float((ps & (d <= k)).sum(1).mean()) for k in range(1, H + 1)],
           "p_all_pass": float((npass == n).mean()), "dist_npass": [float((npass == j).mean()) for j in range(n + 1)],
           "e_busted": float(bs.sum(1).mean()), "p_all_bust": float((bs.sum(1) == n).mean()),
           "total_eval_cost": fee, "e_activation_cost": act,
           "cost_per_funded": (fee + act) / ef if ef > 0 else None, "cost_per_attempt_with_a_pass": fee / float(any5.mean()) if any5.any() else None,
           "per_account_p5": [float(ps[:, j].mean()) for j in range(n)]}
    if n > 1:
        c = np.corrcoef(ps.astype(float).T)
        out["pass_corr_mean"] = float(np.nanmean(c[np.triu_indices(n, 1)]))
    return out


def spec_arrays(ctx: Ctx, fm: Firm, members, ci: int) -> dict:
    """(outcome, day) per breach model of one spec over all rolling starts."""
    r = grid_outcomes(ctx, fm, PV(members, ctx.D), MODELS, cells=[ci])
    return {m: (r[m][0][ci].copy(), r[m][1][ci].copy()) for m in MODELS}


DEFAULT_MIXES = {2: {"lucid": 1, "apex": 1}, 3: {"lucid": 1, "lucidpro": 1, "apex": 1}, 4: {"lucid": 2, "lucidpro": 1, "apex": 1},
                 5: {"lucid": 2, "lucidpro": 2, "apex": 1}}


def best_mix(specs: dict, counts: dict) -> dict:
    """specs = {firm: [{label, arr: {model: (o, d)}, fee, activation}]}. Greedy slot filling: each slot takes the firm's spec that maximises
    P(>=1 pass <= 5d) of the accounts so far (tie: E[funded]); a spec is reused only when the firm has none left. Returns the chosen mix
    under the primary models plus the eod / intraday bounds of the SAME mix, and the 'same best strategy on every account' baseline."""
    prim = {f: E.primary_model(f) for f in specs}
    chosen, used = [], {f: set() for f in specs}

    def ent(f, sp, model):
        o, d = sp["arr"][model]
        return {"firm": f, "label": sp["label"], "o": o, "d": d, "fee": sp["fee"], "activation": sp["activation"]}

    for f, cnt in counts.items():
        for _ in range(cnt):
            opts = [i for i in range(len(specs[f])) if i not in used[f]] or list(range(len(specs[f])))
            best = None
            for i in opts:
                es = [ent(ff, sp, prim[ff]) for ff, sp in chosen] + [ent(f, specs[f][i], prim[f])]
                m = multi_metrics(es, boots=0)
                key = (m["p_any5"], m["e_funded"])
                if best is None or key > best[0]:
                    best = (key, i)
            used[f].add(best[1])
            chosen.append((f, specs[f][best[1]]))
    res = {"counts": dict(counts), "accounts": [f"{f}:{sp['label']}" for f, sp in chosen]}
    res["primary"] = multi_metrics([ent(f, sp, prim[f]) for f, sp in chosen])
    for m in ("eod", "intraday"):
        res[m] = multi_metrics([ent(f, sp, m) for f, sp in chosen], boots=0)
    res["realized"] = multi_metrics([ent(f, sp, "realized") for f, sp in chosen], boots=0)
    base = []
    for f, cnt in counts.items():
        base += [(f, specs[f][0])] * cnt
    res["same_strategy_baseline"] = {"accounts": [f"{f}:{sp['label']}" for f, sp in base],
                                     "primary": multi_metrics([ent(f, sp, prim[f]) for f, sp in base], boots=0)}
    return res


# ------------------------------------------------------------------ one firm end to end

def _js(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Base):
        return o.name
    return str(o)


def _clean(h: dict) -> dict:
    return {k: v for k, v in h.items() if k != "_m"}


def run_firm(fname: str, top: int = 20, K: int = 10, verbose: bool = True, passes: int = 3, boots: int = 2000, extra_singles: int = 3,
             out_dir: Path = OUT, tag: str = "", obj: str = "p5") -> dict:
    """Greedy search + reports + multi-account specs for one firm -> out/portfolio_<firm><tag>.json (+ .npz with the outcome arrays)."""
    t0 = time.time()
    fm = firm(fname)
    ctx, pools = make_ctx((fname,), top, K)
    pool = pools[fname]
    sc = Scorer(ctx, fm, obj=obj)
    g = greedy(ctx, sc, pool, verbose=verbose, passes=passes)
    single = g["single"]
    ref = {"label": _lab(single["_m"]), "stable": single["stable"], "p5": single["p5"]}
    items = [("single", single)] + ([("best2", g["best2"])] if g["best2"] else []) + [("portfolio", g["final"])]
    rep, arrs = {}, {}
    for lab, h in items:
        rep[lab] = report(ctx, fm, h["_m"], h["ci"], True, boots, ref_single=None if lab == "single" else ref)
        rep[lab]["search"] = {"stable_p5": h["stable"], "adj_score": h["adj"], "forced_to_3": any(x.get("forced") for x in g["history"]) and len(h["members"]) >= 3}
        arrs[lab] = spec_arrays(ctx, fm, h["_m"], h["ci"])
    if len(g["final"]["members"]) < 3:
        rep["portfolio"]["flags"].append("FEWER_THAN_3_MEMBERS: no feasible 3rd member under the guards (cap / net-share); this is the best 2-member")
    if any(h.get("forced") for h in g["history"]):
        rep["portfolio"]["flags"].append("FORCED_TO_3: the 3rd member added with gain <= 0.005 (stop rule overridden for the >=3 guard)")
    if "portfolio" in rep:
        rep["portfolio"]["vs_single"]["delta_stable"] = g["final"]["stable"] - single["stable"]
        if "best2" in rep:
            rep["best2"]["vs_single"]["delta_stable"] = g["best2"]["stable"] - single["stable"]
    # a few more distinct singles as alternative accounts for the multi-account mixes
    seen, specs = {b.name for b, _ in single["_m"]}, []
    for adj, name, n, ci, st, p in g["singles"]:
        if name in seen or len(specs) >= extra_singles:
            continue
        seen.add(name)
        specs.append((f"single:{name}@{n}", [(ctx.bases[name], n)], ci, st, p))
    for lab, ms, ci, st, p in specs:
        arrs[lab] = spec_arrays(ctx, fm, ms, ci)
        rep[lab] = {"members": [{"name": b.name, "micros": n} for b, n in ms], "cell": fm.cell_dict(ci), "search": {"stable_p5": st, "p5": p}}
    dg = corr_matrix([b for b, _ in g["final"]["_m"]])
    res = {"firm": fname, "rules_id": fm.rid, "primary": fm.prim, "unconfirmed": not fm.confirmed, "preliminary": True, "objective": obj,
           "preliminary_note": "pool = pass-2 shortlist top-N + wf_offline survivors only; pass-3 candidates (hm2-*, fp-*) not included yet",
           "pool": [{k: c.get(k) for k in ("cid", "src", "fam", "tf", "sess", "how")} for c in (ctx.cands[b.name] for b in pool)],
           "history": [_clean(h) for h in g["history"]], "singles_top": [(a, nm, n, st, p) for a, nm, n, ci, st, p in g["singles"]],
           "reports": rep, "diag": {k: v for k, v in dg.items()}, "evals": g["evals"], "secs": time.time() - t0, "calendar_sessions": ctx.D,
           "starts": ctx.S, "fee": {"eval_fee": fm.fee, "activation": fm.activation, "assumption": True}}
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"portfolio_{fname}{tag}.json").write_text(json.dumps(res, indent=1, default=_js))
    np.savez_compressed(out_dir / f"portfolio_{fname}{tag}.npz", **{f"{lab}|{m}|{k}": a[m][i] for lab, a in arrs.items() for m in MODELS
                                                                     for i, k in enumerate(("o", "d"))})
    if verbose:
        print(brief(res), flush=True)
    return res


def brief(res: dict) -> str:
    lines = [f"== {res['firm']} ({res['rules_id']}{' UNCONFIRMED' if res['unconfirmed'] else ''}) primary={res['primary']} PRELIMINARY " \
             f"({res['evals']} evals, {res['secs']:.0f}s)"]
    for lab in ("single", "best2", "portfolio"):
        r = res["reports"].get(lab)
        if not r:
            continue
        h, e, rl, i = r["headline"], r["eod"], r["realized"], r["intraday"]
        ci = h.get("ci_p5") or [float("nan")] * 2
        lf = r.get("lift", {}).get(res["primary"], {})
        mem = " + ".join(f"{m['name']}@{m['micros']}" for m in r["members"])
        c = r["cell"]
        lines.append(f"  {lab:9s} P1/2/3/5={h['p1']:.2f}/{h['p2']:.2f}/{h['p3']:.2f}/{h['p5']:.3f} [{ci[0]:.2f},{ci[1]:.2f}] bust5={h['bust5']:.2f} "
                     f"med={h['med_days']} | eod {e['p5']:.2f} real {rl['p5']:.2f} intra {i['p5']:.2f} | lift {lf.get('lift', float('nan')):+.3f} "
                     f"| L{c['day_lock']} K{c['day_take']} S{c['day_stop']} T{c['max_day_tr']} TT{c['target_take']} | {mem}"
                     + (f" | FLAGS {r['flags']}" if r["flags"] else ""))
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI

def _run_firm_task(a):
    fname, kw = a
    return run_firm(fname, **kw)


def _wf_task(a):
    fname, kw = a
    return run_wf(fname, **kw)


def run_wf(fname: str, top: int = 20, K: int = 10, kc: int = 5, reselect: bool = True, passes: int = 1, boots: int = 2000, verbose: bool = True,
           out_dir: Path = OUT, tag: str = "") -> dict:
    """Portfolio walk-forward of the firm's reported portfolio (+ its best single for reference): fixed-set and re-selected-set variants."""
    t0 = time.time()
    fm = firm(fname)
    src = json.loads((out_dir / f"portfolio_{fname}{tag}.json").read_text())
    ctx, pools = make_ctx((fname,), top, K)
    pool = pools[fname]
    byname = {b.name: b for b in pool}
    W, tests, oos = wf_windows(ctx.cal)
    res = {"firm": fname, "primary": fm.prim, "preliminary": True, "oos_starts": int(len(oos)), "quarters": [f"{y}Q{q}" for y, q in QUARTERS]}
    for lab in ("portfolio", "single"):
        members = [(byname[m["name"]], m["micros"]) for m in src["reports"][lab]["members"]]
        res[f"{lab}_fixed"] = wf_fixed_with_controls(ctx, fm, members, W, tests, oos, kc=kc, boots=boots)
        if verbose:
            x = res[f"{lab}_fixed"]
            print(f"[{fname}] wf {lab} fixed-set: OOS P5 {x['oos_p5']:.3f} ctrl {x.get('ctrl_oos_p5', float('nan')):.3f} lift {x.get('lift', float('nan')):+.3f}"
                  f" (train {x['mean_train_p5']:.3f}; {time.time()-t0:.0f}s)", flush=True)
    if reselect:
        res["portfolio_reselect"] = wf_reselect(ctx, fm, pool, W, tests, oos, kc=kc, passes=passes, boots=boots, verbose=verbose)
        if verbose:
            x = res["portfolio_reselect"]
            print(f"[{fname}] wf portfolio reselect: OOS P5 {x['oos_p5']:.3f} ctrl {x['ctrl_oos_p5']:.3f} lift {x['lift']:+.3f} ({time.time()-t0:.0f}s)", flush=True)
    res["secs"] = time.time() - t0
    (out_dir / f"portfolio_wf_{fname}{tag}.json").write_text(json.dumps(res, indent=1, default=_js))
    return res


def run_multi(firms=FIRM_ALL, mixes: dict | None = None, out_dir: Path = OUT, tag: str = "") -> dict:
    """Multi-account alternatives from the saved per-firm specs (portfolio_<firm>.json/.npz)."""
    specs = {}
    for f in firms:
        jp = out_dir / f"portfolio_{f}{tag}.json"
        if not jp.exists():
            continue
        j = json.loads(jp.read_text())
        z = np.load(out_dir / f"portfolio_{f}{tag}.npz")
        labs = ["portfolio", "best2", "single"] + [k for k in j["reports"] if k.startswith("single:")]
        specs[f] = [{"label": ("pf" if lab == "portfolio" else lab) if lab in j["reports"] else lab,
                     "arr": {m: (z[f"{lab}|{m}|o"], z[f"{lab}|{m}|d"]) for m in MODELS}, "fee": j["fee"]["eval_fee"], "activation": j["fee"]["activation"]}
                    for lab in labs if lab in j["reports"] and f"{lab}|eod|o" in z.files]
    out = {"preliminary": True, "mixes": {}}
    for n, cnt in (mixes or DEFAULT_MIXES).items():
        if all(f in specs for f in cnt):
            out["mixes"][str(n)] = best_mix(specs, cnt)
    (out_dir / f"portfolio_multi{tag}.json").write_text(json.dumps(out, indent=1, default=_js))
    return out


def run_diag(fnames=FIRM_ALL, top: int = 20, out_dir: Path = OUT):
    """Correlation + drawdown-overlap matrices of the union candidate pool -> out/portfolio_corr.csv / portfolio_ddoverlap.csv."""
    ctx, pools = make_ctx(fnames, top)
    seen = {}
    for f in fnames:
        for b in pools[f]:
            seen[b.name] = b
    bs = list(seen.values())
    d = corr_matrix(bs)
    for nm, key in (("portfolio_corr.csv", "corr"), ("portfolio_ddoverlap.csv", "dd_overlap"), ("portfolio_loseoverlap.csv", "lose_overlap")):
        with (out_dir / nm).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([""] + d["names"])
            for n_, row in zip(d["names"], d[key]):
                w.writerow([n_] + [f"{x:.3f}" for x in row])
    C = d["corr"]
    iu = np.triu_indices(len(bs), 1)
    return {"n": len(bs), "corr_mean": float(C[iu].mean()), "corr_p90": float(np.percentile(C[iu], 90)), "corr_max": float(C[iu].max()),
            "dd_overlap_mean_offdiag": float((d["dd_overlap"].sum() - len(bs)) / max(len(bs) * (len(bs) - 1), 1))}


def digest(firms=FIRM_ALL, tag: str = "", out_dir: Path = OUT) -> str:
    """Compact text digest of the saved results (search, walk-forward, multi-account)."""
    L = []
    for f in firms:
        jp = out_dir / f"portfolio_{f}{tag}.json"
        if jp.exists():
            L.append(brief(json.loads(jp.read_text())))
        wp = out_dir / f"portfolio_wf_{f}{tag}.json"
        if wp.exists():
            w = json.loads(wp.read_text())
            for k in ("portfolio_fixed", "single_fixed", "portfolio_reselect"):
                if k in w:
                    x = w[k]
                    L.append(f"  WF {k:18s} OOS P5 {x['oos_p5']:.3f} [{x['ci_p5'][0]:.2f},{x['ci_p5'][1]:.2f}] train {x['mean_train_p5']:.3f} ctrl {x.get('ctrl_oos_p5', float('nan')):.3f} "
                             f"lift {x.get('lift', float('nan')):+.3f} [{(x.get('lift_ci') or [float('nan')]*2)[0]:+.2f},{(x.get('lift_ci') or [float('nan')]*2)[1]:+.2f}] by-year {x['oos_p5_by_year']}")
    mp = out_dir / f"portfolio_multi{tag}.json"
    if mp.exists():
        for n, m in json.loads(mp.read_text())["mixes"].items():
            p, e, i = m["primary"], m["eod"], m["intraday"]
            L.append(f"  MULTI N={n} {m['counts']} P(>=1 pass<=5d) {p['p_any5']:.3f} [eod {e['p_any5']:.3f} / intra {i['p_any5']:.3f}] by-day {[round(x, 2) for x in p['p_any_by_day']]} "
                     f"E[funded] {p['e_funded']:.2f} cost ${p['total_eval_cost']:.0f} $/funded {p['cost_per_funded']:.0f} | same-strategy baseline {m['same_strategy_baseline']['primary']['p_any5']:.3f}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["run", "wf", "multi", "diag", "digest"])
    ap.add_argument("--firms", default=",".join(FIRM_ALL))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--no-reselect", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--obj", default="p5", choices=list(OBJECTIVES))
    a = ap.parse_args(argv)
    firms = [f for f in a.firms.split(",") if f]
    workers = min(a.workers, 4 if True else 8)
    if a.cmd in ("run", "wf"):
        import multiprocessing as mp
        fn = _run_firm_task if a.cmd == "run" else _wf_task
        kw = dict(top=a.top, tag=a.tag) | ({"passes": a.passes, "obj": a.obj} if a.cmd == "run" else {"reselect": not a.no_reselect})
        with mp.get_context("spawn").Pool(min(workers, len(firms))) as pool:
            for r in pool.imap_unordered(fn, [(f, kw) for f in firms]):
                pass
    elif a.cmd == "multi":
        r = run_multi(firms, tag=a.tag)
        for n, m in r["mixes"].items():
            p = m["primary"]
            print(f"N={n} {m['accounts']}: P(>=1 pass<=5d)={p['p_any5']:.3f} E[funded]={p['e_funded']:.2f} cost={p['total_eval_cost']:.0f} $/funded={p['cost_per_funded']}")
    elif a.cmd == "digest":
        print(digest(firms, a.tag))
    else:
        print(run_diag(firms, a.top))


if __name__ == "__main__":
    main()
