"""Offline exact-P(pass <= 5 trading days) evaluator for NQ prop portfolios (see SPEC.md).

Run with /usr/bin/python3 (has numpy 2.0.2; the repo venv has none). Pure functions, no I/O
beyond reading trades.json bundles. Research window only: dates >= 2025-01-01 are dropped at
load unless holdout=True is passed explicitly.

Pipeline: members (trade source + session + micros) -> merged trades -> per-firm day walk
(cost model, day rules, overlaps) -> daily series (tot / worst intraday point) -> vectorised
eval race (`race`, identical semantics to propsim.run_eval under breach='eod') -> rolling
starts, block-bootstrap CI, i.i.d. Monte Carlo, eventual pass (propsim.run), funded race.

INTRADAY TAKE RULES (walked trade by trade inside a day, next to day_stop / day_lock / max_day_tr).
Notation for a trade of n micros: best = n*MFE/10 - cost(n) (its best point, net of costs; never below its final
P&L p), realised = P&L of closed trades that day, op = final P&L of trades still open when this one enters
(portfolio overlaps: the same conservative aggregation as day_stop, other trades are NOT credited their MFE).

* day_take X (`rules["day_take"]`, any account state, funded too): if realised + op + best >= X the trade is closed
  by a market flatten of the book at day total X - 1 tick*n (trade P&L = X - realised - op - 0.5*n), and the day
  stops (later trades are skipped, like day_stop).
* target_take (`rules["target_take"]`, EVAL ONLY, applied inside `race` because the level depends on the account):
  same, with X = the account's remaining distance to the pass condition, `take_level(r, profit, largest, td)`:
    Apex (no consistency, 1 min day): profit + today >= eval_target, i.e. X = target - profit.
    Lucid: smallest today-P&L L with profit + L >= target AND td + 1 >= eval_min_days AND
    max(largest, L) <= consistency*(profit + L) (today's P&L capped at L in the check). If consistency would fail at
    the target, L rises to the smallest value where it passes (L <= c*profit/(1-c) must still hold); if no such L
    exists, or today cannot be the min-days day, there is no level today (nan).
  Deviation from day_take: the day total after the flatten is exactly L (the trigger is L + 1 tick*n), otherwise
  the 1-tick slippage would leave the account a tick short of the pass condition forever.
  With both rules on the lower trigger fires. target_take supersedes target_stop (its truncation is ignored).
* Ordering (tick order inside a trade is unknown, so PESSIMISTIC): if the same trade touches a take level (via MFE)
  and a stop level (day_stop / the rule file's daily limit via MAE) the stop came first: the trade ends at the stop,
  no take. In the intraday breach model the trade's worst point (its MAE) stays in the day's worst even when the take
  fires, so a floor touch by the MAE beats the take (bust). day_lock only ever acts on CLOSED P&L, so a take below
  day_lock simply ends the day first; max_day_tr counts the taking trade as an entry. With X = None/0 nothing
  changes (bit-identical to before).

BREACH MODELS (`race(..., breach=)`; the eval floor is always the EOD-set one in force at the start of the day):
* 'eod'      bust iff the EOD profit <= floor (Homebase rule files; optimistic bound).
* 'realized' bust iff the REALISED balance after any trade close (trades of the day in EXIT order, portfolio-aware:
             the sum of the P&L of the closed trades, open trades not marked) is <= floor, or the EOD profit is.
             Open drawdowns alone never breach (Lucid: "account balance reached the MLL"; balance = realised).
             A day_stop / take flattens the WHOLE book at once: every open trade closes with the flattening trade (its p
             already absorbs the others' P&L), so the realised balance goes straight to the day total. Simultaneous
             natural exits of separate trades are still counted one by one, worst first (p ascending).
* 'intraday' also bust if realised + the open trades' worst points (MAE) touch the floor (conservative bound).
For one daily series worst <= wreal <= tot, so bust(eod) <= bust(realized) <= bust(intraday) attempt-wise and
P(pass) is monotone: P5(intraday) <= P5(realized) <= P5(eod) (the take rules included: the walk does not depend on the
model). PRIMARY (`PRIMARY`, `primary_model`): lucid / lucidpro / lucidpro_nodll -> 'realized' (bounds eod, intraday);
apex (UNCONFIRMED) and apex_eod (real-time incl. unrealised P&L on the Apex site) -> 'intraday'.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import math
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

R = Path(__file__).resolve().parent                # CODE dir
REPO = R.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(R) not in sys.path:
    sys.path.insert(0, str(R))
import pilot as PL                                  # noqa: E402  (PP_PILOT=es -> root ES, pilot dir; NQ default)
D = PL.DIR                                          # the pilot's DATA dir (ledger, jobs, out/, caches); = R for NQ
ROOT = PL.ROOT
from homebase.backtest import propsim as PKG              # noqa: E402  (rule loader)
from homebase.backtest.propsim import propsim as PS       # noqa: E402  (engine: run_eval, _floor, ...)

HOLDOUT = "2025-01-01"
FIRMS = {"lucid": "lucid-flex-50k@2026-09-27", "apex": "apex-legacy-50k@2026-09-27b"}
# other rule sets, resolvable by firm_rules() but not part of the default firm list
EXTRA_FIRMS = {"lucidpro": "lucid-pro-50k@2026-09-27b", "lucidpro_nodll": "lucid-pro-50k-no-dll@2026-09-27b",
               "apex_eod": "apex-eod-50k@2026-09-27b"}
MODELS = ("eod", "realized", "intraday")        # optimistic -> conservative
# headline breach model per firm (by short name; primary_model() also takes a rule id)
PRIMARY = {"lucid": "realized", "lucidpro": "realized", "lucidpro_nodll": "realized",
           "apex": "intraday", "apex_eod": "intraday"}
RUNS = REPO / "homebase/.state/tester/runs"
GRIDS = REPO / "homebase/.state/tester/grids"
ET = ZoneInfo("America/New_York")
TICK_USD = PL.TICK_USD             # 1 tick on ONE micro (NQ $0.50, ES $1.25)
PT_USD = PL.PV_MICRO               # $ per point on ONE micro (NQ $2, ES $5)
SESS = {"asia": (0, 180), "london": (180, 505), "nyam": (570, 660), "mid": (660, 810), "pm": (810, 958)}
SESS_CODE = {k: i for i, k in enumerate(SESS)}
H_EVAL, H_FUNDED, H_EVENT = 5, 20 * 3, 250
SEED = 20260929


# ------------------------------------------------------------------ cost model / rules

def cost(n: int) -> float:
    """Round-trip commission for n micros: whole NQ (10 micros) legs at $4.00, rest $1.00 each."""
    return (n // 10) * 4.0 + (n % 10) * 1.0


def norm_rules(d: dict | None) -> tuple:
    """-> (max_day_tr, day_stop, day_lock, after_loss, after_win, target_stop); 0/None = off."""
    d = d or {}
    return (int(d.get("max_day_tr") or 0), float(d.get("day_stop") or 0.0), float(d.get("day_lock") or 0.0),
            float(d.get("after_loss", 1.0) or 1.0), float(d.get("after_win", 1.0) or 1.0),
            bool(d.get("target_stop", False)))


def take_rules(d: dict | None) -> tuple:
    """-> (day_take X, target_take flag) from a rules dict; kept apart from norm_rules' 6-tuple. X 0/None = off."""
    d = d or {}
    return float(d.get("day_take") or 0.0), bool(d.get("target_take", False))


def firm_rules(name: str) -> tuple[str, dict]:
    rid = FIRMS.get(name) or EXTRA_FIRMS.get(name, name)
    return rid, PKG.load_rules(rid)


def primary_model(name: str) -> str:
    """Headline breach model of a firm (short name or rule id); unknown firms -> 'eod' (the Homebase model)."""
    if name in PRIMARY:
        return PRIMARY[name]
    for k, rid in {**FIRMS, **EXTRA_FIRMS}.items():
        if rid == name:
            return PRIMARY.get(k, "eod")
    return "eod"


# ------------------------------------------------------------------ trade loading

class TR:
    """Trades of one source as numpy arrays (all per 1 NQ, dates < HOLDOUT unless holdout)."""


_CACHE: dict = {}
_NEWS: dict = {}


def _cell_dir(gid: str, cell: int) -> Path:
    for p in (GRIDS / gid / "cells").iterdir():
        if p.name.isdigit() and int(p.name) == cell:
            return p
    raise FileNotFoundError(f"grid {gid} has no cell {cell}")


def _src_dir(src) -> Path | None:
    if isinstance(src, str):
        if "#" in src:
            g, c = src.split("#")
            return _cell_dir(g, int(c))
        p = Path(src).expanduser()
        return p if p.exists() else RUNS / src
    if isinstance(src, dict):
        if "grid" in src:
            return _cell_dir(src["grid"], int(src["cell"]))
        if "run" in src:
            return RUNS / src["run"]
        if "path" in src:
            return Path(src["path"]).expanduser()
    return None


def load(src, holdout: bool = False) -> TR:
    """src: run id | 'grid_id#cell' | path | {'run'|'grid'+'cell'|'path'} | list of trade dicts."""
    d = _src_dir(src)
    key = (str(d), holdout) if d is not None else None
    if key in _CACHE:
        return _CACHE[key]
    rng = (None, None)
    if d is None:
        rows, label = list(src), "inline"
    else:
        f = d if d.is_file() else d / "trades.json"
        rows = json.loads(f.read_text())
        rows = rows if isinstance(rows, list) else rows.get("trades", [])
        label = d.name
        rj = (d if d.is_dir() else d.parent) / "run.json"
        if rj.exists():
            r = json.loads(rj.read_text()).get("range") or {}
            rng = (r.get("start"), r.get("end"))
    rows = [t for t in rows if holdout or t["date"] < HOLDOUT]
    t = TR()
    t.label, t.range, t.n = label, rng, len(rows)
    t.date = np.array([dt.date.fromisoformat(x["date"]).toordinal() for x in rows], np.int64)
    t.te = np.array([int(x["entry_ms"]) for x in rows], np.int64)
    t.tx = np.array([int(x.get("exit_ms", x["entry_ms"] + 1)) for x in rows], np.int64)
    t.side = np.array([1 if x.get("side", "long") == "long" else -1 for x in rows], np.int8)
    q = np.array([max(1.0, float(x.get("qty") or 1)) for x in rows])          # bundles are per run qty: normalise to 1 NQ
    t.g = np.array([float(x["gross"]) for x in rows]) / q
    t.mae = np.array([abs(float(x["mae_usd"])) if x.get("mae_usd") is not None else max(0.0, -float(x["gross"]))
                      for x in rows]) / q
    t.mfe = np.maximum(np.array([abs(float(x["mfe_usd"])) if x.get("mfe_usd") is not None else 0.0 for x in rows]) / q,
                       np.maximum(t.g, 0.0))                       # best point >= exit P&L (and >= 0)
    t.risk = np.array([abs(float(x["entry_price"]) - float(x["sl"])) if x.get("sl") is not None
                       and x.get("entry_price") is not None else np.nan for x in rows])
    mod = np.array([(lambda a: a.hour * 60 + a.minute)(dt.datetime.fromtimestamp(m / 1000, ET)) for m in t.te], np.int64)
    t.sess = np.full(len(rows), -1, np.int8)
    for k, (a, b) in SESS.items():
        t.sess[(mod >= a) & (mod < b)] = SESS_CODE[k]
    t.iso = [x["date"] for x in rows]
    if key:
        _CACHE[key] = t
    return t


def news_days() -> set:
    if "s" not in _NEWS:
        p, s = PL.shared("news_days.csv"), set()
        if p.exists():
            for ln in p.read_text().splitlines()[1:]:
                if ln.strip():
                    s.add(dt.date.fromisoformat(ln.split(",")[0].strip()).toordinal())
        _NEWS["s"] = s
    return _NEWS["s"]


def _sess_mask(t: TR, sess) -> np.ndarray:
    names = sess if isinstance(sess, (list, tuple)) else str(sess or "all").split("+")
    if "all" in names:
        return np.ones(t.n, bool)
    return np.isin(t.sess, [SESS_CODE[s] for s in names])


def tape_sessions(start: str, end: str) -> list[str]:
    """Weekdays with a tape (NQ archive manifests), cached in bundles_cache/. Research window only."""
    cf = D / "bundles_cache" / f"{ROOT.lower()}_sessions.json"
    if not cf.exists():
        from homebase.backtest.tape import TapeStore
        s = TapeStore().sessions(ROOT, dt.date(2021, 1, 1), dt.date(2024, 12, 31))
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps([d.isoformat() for d in s]))
    return [d for d in json.loads(cf.read_text()) if start <= d <= end]


# ------------------------------------------------------------------ portfolio

class Port:
    """Merged member trades on a session calendar. days[i] = list of trade tuples for session i,
    sorted by entry time: (te, tx, side, gross1, mae1, micros, risk_pts, member)."""


def build(cfg: dict, calendar: list[str] | None = None, holdout: bool = False) -> Port:
    holdout = holdout or bool(cfg.get("holdout"))
    start, end = cfg.get("start", "2021-01-01"), cfg.get("end", "2024-12-31")
    if end >= HOLDOUT and not holdout:
        raise ValueError(f"end {end} reaches the holdout ({HOLDOUT}); pass holdout=True explicitly")
    loaded = [load(m["src"], holdout) for m in cfg["members"]]
    for t in loaded:                       # never evaluate a member outside the span its run covered
        start = max(start, t.range[0] or start)
        end = min(end, t.range[1] or end)
    o0, o1 = dt.date.fromisoformat(start).toordinal(), dt.date.fromisoformat(end).toordinal()
    nd, rows, info = news_days(), [], []
    for i, (m, t) in enumerate(zip(cfg["members"], loaded)):
        mask = _sess_mask(t, m.get("sess", "all")) & (t.date >= o0) & (t.date <= o1)
        nw = m.get("news", "all")
        if nw != "all":
            isn = np.isin(t.date, list(nd)) if nd else np.zeros(t.n, bool)
            mask &= ~isn if nw == "skip" else isn
        idx = np.flatnonzero(mask)
        mi = int(m.get("micros", 10))
        rows += [(int(t.date[j]), int(t.te[j]), int(t.tx[j]), int(t.side[j]), float(t.g[j]), float(t.mae[j]),
                  mi, float(t.risk[j]), i, t.iso[j], float(t.mfe[j])) for j in idx]
        info.append({"label": t.label, "sess": m.get("sess", "all"), "micros": mi, "news": nw, "trades": len(idx)})
    rows.sort(key=lambda r: (r[0], r[1], r[8]))
    cal = sorted({dt.date.fromisoformat(d).toordinal() for d in (calendar if calendar is not None
                                                                 else tape_sessions(start, end))
                  if start <= d <= end} | {r[0] for r in rows})
    P = Port()
    P.cal, P.info, P.window = cal, info, (start, end)
    P.iso = [dt.date.fromordinal(o).isoformat() for o in cal]
    pos = {o: i for i, o in enumerate(cal)}
    P.days, P.mfe = [[] for _ in cal], [[] for _ in cal]                       # mfe[i][k] = best point of days[i][k]
    for r in rows:
        P.days[pos[r[0]]].append((r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))
        P.mfe[pos[r[0]]].append(r[10])
    P.n_trades = len(rows)
    return P


# ------------------------------------------------------------------ day walk

class DayArr:
    """Daily series after sizing + day rules. tot/worst are $ per session (worst = the day's worst
    intraday point relative to the day's start); cr/ct/cw = target_stop truncation versions."""

    def __init__(self, tot, worst, trd, cr=None, ct=None, cw=None, st=None, rewalk=None, wreal=None, cwr=None):
        self.tot, self.worst, self.trd, self.cr, self.ct, self.cw = tot, worst, trd, cr, ct, cw
        self.st = st or {}
        # wreal = the day's lowest REALISED balance after a trade close (exit order), relative to the day's start;
        # hand-built series without it fall back to `worst` (conservative). cwr = target_stop truncation version.
        self.wreal, self.cwr = worst if wreal is None else wreal, cwr
        self.rewalk = rewalk        # (day index, target_take level) -> (tot, worst, traded[, wreal]); used by race(target_take=True)


def _new_st() -> dict:
    return dict(executed=0, skipped=0, clipped=0, conflicts=0, overlap=0, max_conc=0, cap_viol=0, cost=0.0, risk=0.0)


def _walk_day(trs, cap, mt, ds, dl, al, aw, chk, micros, st, mfes=None, tk=0.0, tt=0.0):
    """One session's trades. tk = day_take X, tt = target_take level L (0 = off); mfes[k] = best point of trs[k]
    per 1 NQ ($). See the module docstring for the take rules."""
    realised, mult, nent, stop, rmin = 0.0, 1.0, 0, False, 0.0
    opens, ep, ee, cr, cm, crm = [], [], [], [], [], []

    def flush(upto):
        nonlocal realised, mult, stop, rmin
        opens.sort()
        while opens and opens[0][0] <= upto:
            _, p, _, _, _ = opens.pop(0)
            realised += p
            mult = al if p < 0 else (aw if p > 0 else 1.0)
            if dl and realised >= dl:
                stop = True
            rmin = min(rmin, realised)
            if chk:
                cr.append(realised)
                cm.append(nent)
                crm.append(rmin)

    for k, (te, tx, sd, g, mae, m, rk, mem) in enumerate(trs):
        if opens:
            flush(te)
        if stop or (mt and nent >= mt):
            st["skipped"] += 1
            continue
        n = micros or m
        if mult != 1.0:
            n = max(1, int(n * mult + 1e-9))
        if n > cap:
            n, st["clipped"] = cap, st["clipped"] + 1
        c = cost(n)
        p = n * g / 10.0 - c
        w = min(p, -mae * n / 10.0 - c)
        ow = op = 0.0
        flat = False                                          # True: day_stop / a take flattened the whole book at te
        conc, opp = n, False
        for o in opens:
            ow, op, conc, opp = ow + o[2], op + o[1], conc + o[4], opp or o[3] != sd
        e = realised + ow + w
        if ds and e <= -ds:                                   # day_stop: closed at -Y (+1 tick/contract)
            p = -ds - (realised + op) - TICK_USD * n
            w, stop, flat = p, True, True                         # stopped out here: nothing worse happens after
            e = realised + ow + w
        elif tk or tt:                                        # take rules; the stop above wins a same-trade conflict
            lv = ([(tk, tk - TICK_USD * n)] if tk else []) + ([(tt + TICK_USD * n, tt)] if tt else [])
            trig, fin = min(lv)                               # (trigger for the day total, day total after the flatten)
            best = max(n * mfes[k] / 10.0 - c, p) if mfes is not None else p
            if realised + op + best >= trig:
                p = fin - (realised + op)
                w, stop, flat = min(w, p), True, True         # worst keeps the trade's MAE (adverse first)
                e = realised + ow + w
        if opens:
            st["overlap"] += 1
        st["conflicts"] += opp
        st["max_conc"] = max(st["max_conc"], conc)
        st["cap_viol"] += conc > cap
        if rk == rk:                                           # cost/risk ratio only over trades that carry a stop
            st["cost"] += c + n * 2 * TICK_USD                  # commission + 2 ticks/RT slippage
            st["risk"] += rk * PT_USD * n
        nent += 1
        ep.append(p)
        ee.append(e)
        if "exec" in st:                                       # attribution of the executed trades (walk(collect=True)): member -> [entries, net P&L]
            x = st["exec"].setdefault(mem, [0, 0.0])
            x[0] += 1
            x[1] += p
        if flat:                                               # the flatten closes every open trade together with this one at te:
            realised += op + p                                 # the realised balance goes straight to the day total (this trade's p
            rmin = min(rmin, realised)                         # already absorbs op), not through a lower value in exit order
            opens.clear()
            if chk:
                cr.append(realised)
                cm.append(nent)
                crm.append(rmin)
        else:
            opens.append((tx, p, w, sd, n))
    flush(float("inf"))
    st["executed"] += nent
    if not ep:
        return 0.0, 0.0, 0, [], [], [], 0.0, []
    tot = sum(ep)
    wr = min(rmin, tot)
    if not chk:
        return tot, min(min(ee), tot), nent, [], [], [], wr, []
    cum = np.cumsum(ep)
    pmin = np.minimum.accumulate(np.array(ee))
    ct = [float(cum[k - 1]) for k in cm]
    cw = [float(min(pmin[k - 1], cum[k - 1])) for k in cm]
    cwr = [min(max(a, w), c) for a, w, c in zip(crm, cw, ct)]          # realised low so far, kept between worst and total
    return tot, min(min(ee), tot), nent, cr, ct, cw, wr, cwr


def walk(P: Port, cap: int, rl: tuple, want_chk: bool = False, micros: int | None = None, dll: float = 0.0,
         day_take: float = 0.0, collect: bool = False) -> DayArr:
    """Daily series for a firm cap and rules tuple. `dll` (rule-file soft daily limit) tightens day_stop.
    `day_take` is applied here; target_take is applied in race() through the returned A.rewalk."""
    mt, ds, dl, al, aw, ts = rl
    dtk = float(day_take or 0.0)
    if dll and (not ds or dll < ds):
        ds = dll
    D = len(P.days)
    tot, wst, trd, wrl = np.zeros(D), np.zeros(D), np.zeros(D, bool), np.zeros(D)
    st = _new_st()
    if collect:
        st["exec"] = {}                                    # member id -> [executed entries, executed net P&L] (A.st["exec"])
    mf = getattr(P, "mfe", None) or [None] * D
    chk = want_chk and ts
    cr, ct, cw, cwr = {}, {}, {}, {}
    for i, trs in enumerate(P.days):
        if trs:
            a, b, n, r1, r2, r3, wr, r4 = _walk_day(trs, cap, mt, ds, dl, al, aw, chk, micros, st, mf[i], dtk)
            tot[i], wst[i], trd[i], wrl[i] = a, b, n > 0, wr
            if chk and r1:
                cr[i], ct[i], cw[i], cwr[i] = r1, r2, r3, r4
    memo = {}

    def rewalk(i, tt):
        if (i, tt) not in memo:
            a, b, n, _, _, _, wr, _ = _walk_day(P.days[i], cap, mt, ds, dl, al, aw, False, micros, _new_st(), mf[i], dtk, tt)
            memo[i, tt] = (a, b, n > 0, wr)
        return memo[i, tt]

    A = DayArr(tot, wst, trd, st=st, rewalk=rewalk, wreal=wrl)
    if chk:
        K = max([len(v) for v in cr.values()] or [1])
        A.cr, A.ct, A.cw, A.cwr = (np.full((D, K), np.nan) for _ in range(4))
        for i in cr:
            k = len(cr[i])
            A.cr[i, :k], A.ct[i, :k], A.cw[i, :k], A.cwr[i, :k] = cr[i], ct[i], cw[i], cwr[i]
    return A


# ------------------------------------------------------------------ races

def take_level(r: dict, profit, largest, td) -> np.ndarray:
    """target_take level per attempt (arrays): the smallest today-P&L L at which the account passes today
    (profit + L >= target, td + 1 >= min days, and with consistency c: max(largest, L) <= c*(profit + L)), else nan."""
    profit, largest, td = (np.asarray(x, float) for x in (profit, largest, td))
    L = r["eval_target"] - profit
    c = r.get("consistency")
    if c is not None:
        L = np.maximum(L, largest / c - profit)
        L = np.where(L <= (c * profit / (1 - c) if c < 1 else np.inf) + 1e-9, L, np.nan)
    L = np.where(td + 1 >= r["eval_min_days"], L, np.nan)
    return np.where(L > 0, L, np.nan)


def race(idx: np.ndarray, A: DayArr, r: dict, breach: str = "eod", target_stop: bool = False,
         target_take: bool = False):
    """Vectorised eval race. idx[P,H] = day indices into A. -> (outcome[P] 0 timeout|1 pass|2 bust, day[P] 1-based).
    breach='eod' == propsim.run_eval exactly; 'realized' also busts when the lowest realised balance after a trade
    close <= floor in force; 'intraday' also busts when the day's worst point (open MAE included) <= floor in force.
    target_take: each active attempt's day is re-walked with its own take level (`take_level`); needs A.rewalk
    (from walk()). It supersedes target_stop."""
    if breach not in MODELS:
        raise ValueError(f"breach model {breach!r} not in {MODELS}")
    P, H = idx.shape
    mll, lock_at, lock_floor = r["trailing_mll"], r["lock_at"], r["lock_floor"]
    tgt, mind, cons, dll = r["eval_target"], r["eval_min_days"], r.get("consistency"), PS._dll(r)
    profit, peak, floor = np.zeros(P), np.zeros(P), np.full(P, -float(mll))
    largest, td = np.zeros(P), np.zeros(P, np.int64)
    out, dayn = np.zeros(P, np.int8), np.zeros(P, np.int16)
    use_chk = target_stop and A.cr is not None and not target_take
    take = target_take and A.rewalk is not None
    for k in range(H):
        act = out == 0
        if not act.any():
            break
        d = idx[:, k]
        pnl, wst, tr, wrl = A.tot[d], A.worst[d], A.trd[d], A.wreal[d]
        if take:
            L = take_level(r, profit, largest, td)
            for j in np.flatnonzero(act & A.trd[d] & ~np.isnan(L)):
                x = A.rewalk(int(d[j]), float(L[j]))
                pnl[j], wst[j], tr[j] = x[:3]
                wrl[j] = x[3] if len(x) > 3 else x[1]
        if use_chk:
            cr = A.cr[d]
            cond = (profit[:, None] + cr >= tgt) & ((td + 1)[:, None] >= mind)
            if cons is not None:
                cond &= np.maximum(largest[:, None], cr) <= cons * (profit[:, None] + cr)
            has, kk = cond.any(1), cond.argmax(1)
            pnl = np.where(has, A.ct[d, kk], pnl)
            wst = np.where(has, A.cw[d, kk], wst)
            wrl = np.where(has, A.cwr[d, kk] if A.cwr is not None else A.cw[d, kk], wrl)
        if dll:
            pnl = np.maximum(pnl, -dll)
        new = profit + pnl
        bust = act & (new <= floor)
        if breach == "intraday":
            bust |= act & (profit + wst <= floor)
        elif breach == "realized":
            bust |= act & (profit + wrl <= floor)
        live = act & ~bust
        profit = np.where(live, new, profit)
        td = td + (tr & live)
        largest = np.where(live, np.maximum(largest, pnl), largest)
        peak = np.where(live & (new > peak), new, peak)
        floor = np.where(peak >= lock_at, float(lock_floor), peak - mll)
        ok = live & (new >= tgt) & (td >= mind)
        if cons is not None:
            ok &= largest <= cons * new
        out[bust], dayn[bust] = 2, k + 1
        out[ok], dayn[ok] = 1, k + 1
    return out, dayn


def race_funded(idx: np.ndarray, As: list, thr, r: dict, breach: str = "eod") -> dict:
    """Funded race from a flat account, run_funded semantics. As[j] = day series at scaling level j,
    thr = ascending profit thresholds (level j+1 once EOD profit >= thr[j])."""
    P, H = idx.shape
    TOT, WST = np.stack([a.tot for a in As]), np.stack([a.worst for a in As])
    WRL = np.stack([a.wreal for a in As])
    if breach not in MODELS:
        raise ValueError(f"breach model {breach!r} not in {MODELS}")
    thr, dll = np.asarray(thr, float), PS._dll(r)
    mll, lock_at, lock_floor = r["trailing_mll"], r["lock_at"], r["lock_floor"]
    profit, peak, floor = np.zeros(P), np.zeros(P), np.full(P, -float(mll))
    wins, alive = np.zeros(P, np.int64), np.ones(P, bool)
    pay, mx, bust = np.zeros(P, np.int16), np.zeros(P, np.int16), np.zeros(P, np.int16)
    chq = np.zeros(P)
    for k in range(H):
        d = idx[:, k]
        lv = np.searchsorted(thr, profit, side="right") if len(thr) else np.zeros(P, np.int64)
        pnl, wst, wrl = TOT[lv, d], WST[lv, d], WRL[lv, d]
        if dll:
            pnl = np.maximum(pnl, -dll)
        new = profit + pnl
        wins = wins + (alive & (pnl >= r["win_day"]))
        b = alive & (new <= floor)
        if breach == "intraday":
            b |= alive & (profit + wst <= floor)
        elif breach == "realized":
            b |= alive & (profit + wrl <= floor)
        bust[b] = k + 1
        alive = alive & ~b
        profit = np.where(alive, new, profit)
        peak = np.where(alive & (new > peak), new, peak)
        floor = np.where(peak >= lock_at, float(lock_floor), peak - mll)
        npay = alive & (pay == 0) & (wins >= r["payout_win_days"]) & (profit > 0)
        pay[npay] = k + 1
        chq[npay] = np.minimum(r["payout_share"] * profit[npay], r["payout_cap"])
        nmx = alive & (mx == 0) & (wins >= r["payout_win_days"]) & (profit >= r["max_payout_profit"])
        mx[nmx] = k + 1
        alive = alive & ~nmx
    return dict(pay=pay, chq=chq, mx=mx, bust=bust)


# ------------------------------------------------------------------ summaries

def _med(x):
    return float(np.median(x)) if len(x) else None


def summarize(out, day, H=H_EVAL) -> dict:
    ps, bs = out == 1, out == 2
    return {"n": int(len(out)), "p_pass": float(ps.mean()), "p_bust": float(bs.mean()),
            "p_neither": float(1 - ps.mean() - bs.mean()), "med_days_pass": _med(day[ps]),
            "pass_by": [float((ps & (day <= k)).mean()) for k in range(1, H + 1)],
            "bust_by": [float((bs & (day <= k)).mean()) for k in range(1, H + 1)]}


def block_ci(xs: list, block: int = 20, boots: int = 2000, seed: int = SEED) -> list:
    """Moving-block bootstrap 95% CIs for the means of aligned 0/1 arrays (one CI per array)."""
    N = len(xs[0])
    B = min(block, N)
    rng = np.random.default_rng(seed)
    nb = -(-N // B)
    ix = (rng.integers(0, N - B + 1, (boots, nb))[:, :, None] + np.arange(B)).reshape(boots, -1)[:, :N]
    return [[float(np.percentile(x[ix].mean(1), q)) for q in (2.5, 97.5)] for x in xs]


def _series(A: DayArr) -> dict:
    tp = A.tot[A.trd]
    return {"n_sessions": int(len(A.tot)), "trade_days": int(A.trd.sum()), "net": float(A.tot.sum()),
            "mean_day": float(tp.mean()) if len(tp) else 0.0, "median_day": _med(tp) or 0.0,
            "worst_day": float(tp.min()) if len(tp) else 0.0, "best_day": float(tp.max()) if len(tp) else 0.0}


def _fees() -> dict:
    return json.loads(PL.shared("fees.json").read_text())


def _funded_levels(P, r, rl, day_take: float = 0.0):
    cap, sc = r["cap_micros"], r.get("scaling_micros")
    caps = [min(sc["start"], cap), min(sc["at_1000"], cap), min(sc["at_2000"], cap)] if sc else [cap]
    thr = [1000.0, 2000.0] if sc else []
    rl_f = rl[:5] + (False,)                                    # day_take applies when funded; target_take is eval only
    cache = {}
    return [cache.setdefault(c, walk(P, c, rl_f, dll=PS._dll(r) or 0.0, day_take=day_take)) for c in caps], thr, caps


# ------------------------------------------------------------------ evaluate

def evaluate(cfg: dict, *, mc: int = 10000, boots: int = 2000, eventual: int = 2000, funded: bool = True,
             seed: int = SEED, port: Port | None = None, calendar: list[str] | None = None) -> dict:
    """One config -> dict per firm. cfg = {members:[{src,sess,micros,news}], rules:{...}, firms:[...], start,end,tag}."""
    T0 = time.perf_counter()
    P = port or build(cfg, calendar)
    tm = {"build": time.perf_counter() - T0}
    D, rl, fees = len(P.days), norm_rules(cfg.get("rules")), _fees()
    dtk, ttk = take_rules(cfg.get("rules"))
    res = {"tag": cfg.get("tag") or "cfg_" + hashlib.sha1(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:10],
           "cfg": {k: v for k, v in cfg.items() if k != "members"} | {"members": P.info},
           "window": {"start": P.iso[0] if D else None, "end": P.iso[-1] if D else None, "sessions": D,
                      "trades": P.n_trades}, "firms": {}}
    if D < H_EVAL or not P.n_trades:
        res["skipped"] = "no trades or window shorter than 5 sessions"
        return res
    rng = np.random.default_rng(seed)
    idx5 = np.arange(D - H_EVAL + 1)[:, None] + np.arange(H_EVAL)
    for name in cfg.get("firms") or list(FIRMS):
        rid, r = firm_rules(name)
        prim = primary_model(name)
        f = res["firms"][rid] = {"confirmed": r.get("confirmed") is not False, "cap_micros": r["cap_micros"],
                                 "primary": prim, "models": list(MODELS)}
        if not f["confirmed"]:
            f["flag"] = "UNCONFIRMED rules; payout terms are Lucid placeholders"
        t = time.perf_counter()
        A = walk(P, r["cap_micros"], rl, want_chk=True, dll=PS._dll(r) or 0.0, day_take=dtk)
        tm["walk"] = tm.get("walk", 0) + time.perf_counter() - t
        st = A.st
        f["walk"] = {"executed": st["executed"], "skipped": st["skipped"], "clipped": st["clipped"],
                     "overlap_entries": st["overlap"], "opposite_conflicts": int(st["conflicts"]),
                     "max_concurrent_micros": st["max_conc"], "cap_violations": int(st["cap_viol"]),
                     "cap_ok": st["cap_viol"] == 0 and st["clipped"] == 0}
        f["cost"] = {"rt_over_risk": (st["cost"] / st["risk"]) if st["risk"] else None,
                     "ok_lt_3pct": bool(st["risk"] and st["cost"] / st["risk"] < 0.03)}
        f["series"] = _series(A)
        t = time.perf_counter()
        races = {b: race(idx5, A, r, b, rl[5], ttk) for b in MODELS}
        for b, (o, d) in races.items():
            f[b] = summarize(o, d)
        for b in dict.fromkeys(("eod", prim)):
            ci = block_ci([races[b][0] == 1, races[b][0] == 2], boots=boots, seed=seed) if boots else [None, None]
            f[b]["ci95_pass"], f[b]["ci95_bust"] = ci
        tm["race"] = tm.get("race", 0) + time.perf_counter() - t
        t = time.perf_counter()
        if mc:
            o, d = race(rng.integers(0, D, (mc, H_EVAL)), A, r, prim, rl[5], ttk)
            f["mc_iid"] = summarize(o, d)
            f["mc_iid"]["model"] = prim
            f["mc_iid"]["ci95_pass"] = list(PS.wilson_ci(int((o == 1).sum()), mc))
        tm["mc"] = tm.get("mc", 0) + time.perf_counter() - t
        t = time.perf_counter()
        p_ev = None
        if eventual:
            e = PS.run([float(x) for x in A.tot], trade_flags=[bool(x) for x in A.trd], rules=r, n_paths=eventual,
                       horizon=H_EVENT, seed=seed, sweep=(), degradation=())["eval"]
            f["eventual"] = {"p_pass": e["p"], "ci95": e["ci"], "p_bust": e["bust_p"], "p_timeout": e["timeout_p"],
                             "med_days": e["days"]["median"], "paths": eventual, "note": "i.i.d., ignores target_stop/target_take"}
            p_ev = e["p"]
        tm["eventual"] = tm.get("eventual", 0) + time.perf_counter() - t
        t = time.perf_counter()
        if funded and D >= H_FUNDED:
            As, thr, caps = _funded_levels(P, r, rl, dtk)
            idxf = np.arange(D - H_FUNDED + 1)[:, None] + np.arange(H_FUNDED)
            f["funded"] = {"horizon": H_FUNDED, "level_caps": caps, "starts": int(len(idxf))}
            for b in MODELS:
                x = race_funded(idxf, As, thr, r, b)
                paid, bust = x["pay"] > 0, x["bust"] > 0
                f["funded"][b] = {"p_payout": float(paid.mean()), "p_bust_before_payout": float((bust & ~paid).mean()),
                                  "p_bust_any": float(bust.mean()), "p_max_payout": float((x["mx"] > 0).mean()),
                                  "med_days_payout": _med(x["pay"][paid]), "e_first_cheque": float(x["chq"].mean()),
                                  "e_cheque_if_paid": float(x["chq"][paid].mean()) if paid.any() else None}
        tm["funded"] = tm.get("funded", 0) + time.perf_counter() - t
        fee = fees.get(rid, {"eval_fee": 0.0, "activation": 0.0})
        p5 = f[prim]["p_pass"]
        f["econ"] = {"model": prim, "eval_fee": fee["eval_fee"], "activation": fee["activation"], "fees_are_assumptions": True,
                     "e_evals_5d": 1 / p5 if p5 > 0 else None,
                     "cost_per_funded_5d": fee["eval_fee"] / p5 + fee["activation"] if p5 > 0 else None,
                     "e_evals_eventual": 1 / p_ev if p_ev else None,
                     "cost_per_funded_eventual": fee["eval_fee"] / p_ev + fee["activation"] if p_ev else None}
    tm["total"] = time.perf_counter() - T0
    tm["core"] = tm["total"] - tm.get("eventual", 0) - tm.get("funded", 0) - tm.get("mc", 0)
    res["timing_s"] = {k: round(v, 3) for k, v in tm.items()}
    return res


def line(res: dict) -> str:
    """One compact stdout line per config (all firms)."""
    out = [f"{res['tag']} [{res['window']['start']}..{res['window']['end']} {res['window']['sessions']}s"
           f" {res['window']['trades']}tr]"]
    for rid, f in res.get("firms", {}).items():
        e, i, rl_ = f["eod"], f["intraday"], f["realized"]
        ci = e.get("ci95_pass")
        s = (f"{rid.split('-')[0]}{'(UNCONF)' if not f['confirmed'] else ''} P5={e['p_pass']:.3f}"
             + (f"[{ci[0]:.2f},{ci[1]:.2f}]" if ci else "") + f" bust={e['p_bust']:.3f} real={rl_['p_pass']:.3f}/{rl_['p_bust']:.3f}"
             + f" intra={i['p_pass']:.3f}/{i['p_bust']:.3f} prim={f['primary']}")
        if "mc_iid" in f:
            s += f" mc={f['mc_iid']['p_pass']:.3f}"
        if "eventual" in f:
            s += f" evt={f['eventual']['p_pass']:.3f}"
        if "funded" in f:
            fe = f["funded"]["eod"]
            s += f" fund pay={fe['p_payout']:.2f} bust={fe['p_bust_before_payout']:.2f} E$={fe['e_first_cheque']:.0f}"
        if f["econ"]["cost_per_funded_5d"]:
            s += f" $/funded={f['econ']['cost_per_funded_5d']:.0f}"
        if not f["walk"]["cap_ok"]:
            s += " CAP!"
        out.append(s)
    return " | ".join(out) + f" | {res['timing_s']['total']:.2f}s (core {res['timing_s']['core']:.2f}s)"


def save(res: dict, out_dir: Path | None = None) -> Path:
    p = (out_dir or D / "out") / f"{res['tag']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return p


# ------------------------------------------------------------------ search helper

GRID = {"micros": [10, 20, 30, 40], "day_lock": [0, 300, 600, 900], "day_stop": [0, 500, 800, 1200],
        "max_day_tr": [0, 1, 2, 3], "after_loss": [1.0, 0.5], "target_stop": [False, True]}


def search(cfg: dict, grid: dict | None = None, port: Port | None = None, firms=None) -> list[dict]:
    """Grid over micros x day_lock x day_stop x max_day_tr x after_loss x target_stop per firm (eod race,
    rolling 5-day starts). `micros` = micros for every member. Adds `stab` = median p_pass of the
    cell's grid neighbours (one step on one axis)."""
    g = {**GRID, **(grid or {})}
    P = port or build(cfg)
    D = len(P.days)
    idx5 = np.arange(D - H_EVAL + 1)[:, None] + np.arange(H_EVAL)
    axes = list(g)
    rows = []
    for name in firms or cfg.get("firms") or list(FIRMS):
        rid, r = firm_rules(name)
        dll, wc, cell = PS._dll(r) or 0.0, {}, {}
        for combo in itertools.product(*[range(len(g[a])) for a in axes]):
            v = {a: g[a][i] for a, i in zip(axes, combo)}
            if v["micros"] > r["cap_micros"]:
                continue
            rl = norm_rules(v)
            dtk, ttk = take_rules(v)
            k = (v["micros"],) + rl[:5] + (dtk,)
            if k not in wc:
                wc[k] = walk(P, r["cap_micros"], rl[:5] + (True,), want_chk=True, micros=v["micros"], dll=dll, day_take=dtk)
            A = wc[k]
            o, d = race(idx5, A, r, "eod", rl[5], ttk)
            row = {"firm": rid.split("-")[0], **v, "n_rules": sum(bool(v.get(a)) for a in
                   ("day_lock", "day_stop", "max_day_tr", "target_stop", "day_take", "target_take")) + (v["after_loss"] != 1.0), "p_pass": float((o == 1).mean()), "p_bust": float((o == 2).mean()),
                   "med_days": _med(d[o == 1]), "executed": A.st["executed"],
                   "cost_ratio": A.st["cost"] / A.st["risk"] if A.st["risk"] else None}
            cell[combo] = row
            rows.append((combo, row))
        for combo, row in rows[-len(cell):]:
            nb = []
            for ax in range(len(axes)):
                for dlt in (-1, 1):
                    c = list(combo)
                    c[ax] += dlt
                    if tuple(c) in cell:
                        nb.append(cell[tuple(c)]["p_pass"])
            row["stab"] = float(np.median(nb)) if nb else row["p_pass"]
    return [r for _, r in rows]


# ------------------------------------------------------------------ day-matched random control
# The screen's thinned control matched only the total trade COUNT, so a config that spreads its trades over more
# days than the thinned control got an edge_lift confounded by day-spread. This builder matches the (date, session)
# trade counts exactly instead. Cross-checked by test_daymatch.py.

DAY_MS = 86_400_000
_EXIT_KEYS = ("tf", "stop_mode", "stop_val", "tgt_r", "exit_bars", "trail_atr", "max_tr")
DRAFT_PREFIX = "draft_" + PL.PREFIX          # tester ids of this pilot's drafts (NQ: draft_pp_, ES: draft_pp_es_)
_CTRL_STRATEGY = DRAFT_PREFIX + "random"


def daymatched_pick(cfg_date, cfg_sess, pool_date, pool_te, pool_tx, pool_sess, seed, no_overlap: bool = True) -> dict:
    """One day-matched draw. For every (date, sess) on which the config has k trades pick k pool trades on the same
    date+session (uniform, without replacement; result sorted by entry time). With no_overlap (default) a pick may not
    overlap an already picked trade of that day (a config runs one position at a time; pooled seeds otherwise stack).
    Shortfalls are filled in a second pass from the same session on the NEAREST dates (unused pool trades, shifted onto
    the config's date by whole days), so a date's own pool is never stolen by an earlier date's fallback.
    -> dict(pi=pool index, date=control date, shift=ms shift applied to te/tx, fb=fallback flag, short=#unfilled,
    n_cfg=#config trades). Deterministic given `seed` (int or list of ints)."""
    rng = np.random.default_rng(seed)
    cd, cs = np.asarray(cfg_date, np.int64), np.asarray(cfg_sess, np.int64)
    pd_, pte, ptx, ps_ = (np.asarray(a) for a in (pool_date, pool_te, pool_tx, pool_sess))
    pool_by: dict = {}
    for j in np.lexsort((pte, ps_, pd_)):
        pool_by.setdefault((int(pd_[j]), int(ps_[j])), []).append(int(j))
    sdates: dict = {}
    for (d, s) in pool_by:
        sdates.setdefault(s, []).append(d)
    sdates = {s: np.array(sorted(v), np.int64) for s, v in sdates.items()}
    groups: dict = {}
    for d, s in zip(cd.tolist(), cs.tolist()):
        groups[(d, s)] = groups.get((d, s), 0) + 1
    used = np.zeros(len(pd_), bool)
    picked: dict = {}                                    # (d,s) -> [(pool idx, shift_ms, fb)]

    def fits(cur, j, sh):
        a, b = int(pte[j]) + sh, int(ptx[j]) + sh
        return all(not (a < int(ptx[i]) + s2 and b > int(pte[i]) + s2) for i, s2, _ in cur)

    short_list = []
    for key in sorted(groups):
        k, cur = groups[key], []
        cand = pool_by.get(key, [])
        for j in (cand[i] for i in rng.permutation(len(cand))):
            if len(cur) >= k:
                break
            if not no_overlap or fits(cur, j, 0):
                cur.append((j, 0, False))
                used[j] = True
        picked[key] = cur
        if len(cur) < k:
            short_list.append(key)
    short = 0
    for key in short_list:
        d, s = key
        cur, need = picked[key], groups[key] - len(picked[key])
        dates = sdates.get(s)
        if dates is not None and len(dates):
            pos = int(np.searchsorted(dates, d))
            lo, hi = pos - 1, pos                          # lo walks left, hi walks right
            while need > 0 and (lo >= 0 or hi < len(dates)):
                dl = d - int(dates[lo]) if lo >= 0 else 10**9
                dh = int(dates[hi]) - d if hi < len(dates) else 10**9
                if dl < dh or (dl == dh and rng.random() < 0.5):
                    d2, lo = int(dates[lo]), lo - 1
                else:
                    d2, hi = int(dates[hi]), hi + 1
                if d2 == d:
                    continue
                sh = (d - d2) * DAY_MS
                cand = [j for j in pool_by[(d2, s)] if not used[j]]
                for j in (cand[i] for i in rng.permutation(len(cand))):
                    if need <= 0:
                        break
                    if not no_overlap or fits(cur, j, sh):
                        cur.append((j, sh, True))
                        used[j] = True
                        need -= 1
        short += max(0, need)
    pi, nd, sh, fb = [], [], [], []
    for (d, s), cur in picked.items():
        for j, s2, f in cur:
            pi.append(j), nd.append(d), sh.append(s2), fb.append(f)
    pi, nd, sh, fb = np.array(pi, np.int64), np.array(nd, np.int64), np.array(sh, np.int64), np.array(fb, bool)
    o = np.lexsort((pte[pi] + sh, nd)) if len(pi) else np.zeros(0, np.int64)
    return {"pi": pi[o], "date": nd[o], "shift": sh[o], "fb": fb[o], "short": short, "n_cfg": int(len(cd))}


def daymatched_controls(cfg, pool, K: int = 10, seed: int = SEED, mask=None, no_overlap: bool = True,
                        carry=("side", "g", "mae", "risk", "sess")) -> list:
    """K day-matched control ledgers for a config (`cfg`, optional boolean `mask`, e.g. one session) drawn from `pool`
    (TR-like objects with date/te/tx/sess + carry arrays; concatenate seeds' TRs first). Each control is a dict of
    arrays date/te/tx/<carry...> (dates and times moved onto the config's dates) + fb_share, short, n."""
    m = np.ones(cfg.n, bool) if mask is None else np.asarray(mask, bool)
    out = []
    for k in range(K):
        r = daymatched_pick(cfg.date[m], cfg.sess[m], pool.date, pool.te, pool.tx, pool.sess, [SEED, int(seed), k], no_overlap)
        pi = r["pi"]
        c = {"date": r["date"], "te": pool.te[pi] + r["shift"], "tx": pool.tx[pi] + r["shift"], "fb": r["fb"],
             "pi": pi, "short": r["short"], "n": int(len(pi)), "n_cfg": r["n_cfg"],
             "fb_share": float(r["fb"].mean()) if len(pi) else 0.0}
        for a in carry:
            c[a] = getattr(pool, a)[pi]
        out.append(c)
    return out


def concat_tr(parts) -> "TR":
    """Pool several runs' TR objects into one (arrays concatenated; .iso/.label dropped)."""
    t = TR()
    t.n, t.label, t.range = sum(p.n for p in parts), "pool", (None, None)
    for a in ("date", "te", "tx", "side", "g", "mae", "mfe", "risk", "sess"):
        setattr(t, a, np.concatenate([getattr(p, a) for p in parts]))
    return t


# ---- profile -> pool resolver

def _profile_defaults() -> dict:
    fi = json.loads(PL.shared("family_inputs.json").read_text())
    return {k: v for k, v, *_ in fi["common"] if k in _EXIT_KEYS}, fi


def profile_from(fam: str | None, inputs: dict | None = None) -> dict:
    """Exit profile (tf, stop_mode, stop_val, tgt_r, exit_bars, trail_atr, max_tr) of a config: template defaults, then
    the family's own defaults for those keys (tod_drift: tgt_r 0, exit_bars 6, max_tr 1), then the run inputs."""
    base, fi = _profile_defaults()
    for row in fi.get(fam or "", []):
        if row[0] in _EXIT_KEYS:
            base[row[0]] = row[2]
    base.update({k: v for k, v in (inputs or {}).items() if k in _EXIT_KEYS})
    p = {"tf": int(base["tf"]), "stop_mode": str(base["stop_mode"]), "stop_val": float(base["stop_val"]),
         "tgt_r": float(base["tgt_r"]), "exit_bars": int(base["exit_bars"]), "trail_atr": float(base["trail_atr"]),
         "max_tr": int(base["max_tr"])}
    return p


def _ctrl_catalog(ledger=None, jobs=None) -> dict:
    """{profile tuple: {'srcs': [run id | 'grid#cell'], 'keys': [...]}} over the random-control rows of ledger.csv whose
    job (jobs.jsonl) is done. Profile = template defaults + the control's own inputs/cell params."""
    import csv
    ledger, jobs = Path(ledger or D / "ledger.csv"), Path(jobs or D / "jobs.jsonl")
    done = set()
    if jobs.exists():
        for ln in jobs.read_text().splitlines():
            if ln.strip():
                j = json.loads(ln)
                if j.get("status") == "done":
                    done.add(j["key"])
    cat: dict = {}
    with ledger.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["stage"] != "ctrl" or r["strategy"] != _CTRL_STRATEGY or (done and r["key"] not in done):
                continue
            src = r["run_id"] if r["run_id"] else (f"{r['grid_id']}#{r['cell']}" if r["grid_id"] and r["cell"] != "" else None)
            if not src:
                continue
            p = profile_from("random", json.loads(r["params_json"]))
            e = cat.setdefault(tuple(p[k] for k in _EXIT_KEYS), {"srcs": [], "keys": []})
            e["srcs"].append(src), e["keys"].append(r["key"])
    return cat


def _dist(a: dict, b: tuple) -> float:
    b = dict(zip(_EXIT_KEYS, b))
    return (10.0 * (a["tf"] != b["tf"]) + 5.0 * (a["stop_mode"] != b["stop_mode"]) + abs(a["stop_val"] - b["stop_val"])
            + abs(a["tgt_r"] - b["tgt_r"]) + abs(a["exit_bars"] - b["exit_bars"]) / 6.0
            + abs(a["trail_atr"] - b["trail_atr"]) + 0.1 * abs(a["max_tr"] - b["max_tr"]))


def resolve_pool(profile: dict, ledger=None, jobs=None) -> dict:
    """Random-control pool with the same exit profile (tf, stop_mode/val, tgt_r, exit_bars, trail, max_tr ignored for
    'exact'). Screen defaults (atr 1.5 x 2R) hit the ctrl + ctrl2 random runs of that tf, tod_drift (2R off, 6 bars)
    the randomtod runs, a heat-map cell the hmctrl cell with equal tf/stop_val/tgt_r; anything else -> the nearest
    profile in the catalog, flagged. -> {srcs, keys, profile (the pool's), exact, dist, flag}. srcs load via load()."""
    cat = _ctrl_catalog(ledger, jobs)
    if not cat:
        return {"srcs": [], "keys": [], "profile": None, "exact": False, "dist": None, "flag": "no control runs finished"}
    ex = [k for k in cat if all(k[i] == profile[n] for i, n in enumerate(_EXIT_KEYS) if n != "max_tr")]
    if ex:
        # same exit profile: pool every matching run (max_tr / entry-prob differences ride along)
        srcs = [s for k in ex for s in cat[k]["srcs"]]
        keys = [s for k in ex for s in cat[k]["keys"]]
        return {"srcs": srcs, "keys": keys, "profile": dict(zip(_EXIT_KEYS, ex[0])), "exact": True, "dist": 0.0, "flag": ""}
    best = min(cat, key=lambda k: (_dist(profile, k), k))
    d = _dist(profile, best)
    return {"srcs": list(cat[best]["srcs"]), "keys": list(cat[best]["keys"]), "profile": dict(zip(_EXIT_KEYS, best)),
            "exact": False, "dist": d, "flag": f"NEAREST profile (dist {d:.2f}): {dict(zip(_EXIT_KEYS, best))}"}
