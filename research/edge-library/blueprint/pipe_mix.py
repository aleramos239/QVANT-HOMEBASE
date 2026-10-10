"""pipe_mix.py -- THE MIX ON THE BUILD DAYS (the owner, 2026-10-10: "judge the mix on steadiness, not each idea"; `bp.py pipe mix`).

A PROPOSAL IN CODE, build days only. Nothing here reads a day from 2025-07-01 on, writes a pipeline state, moves an idea, or reads
the unseen days: that is a separate read, one read for the whole mix, and it waits for the owner's word on this rule.

THE IDEA. One idea's money comes in lumps: a box that makes $100 a trade still has losing months, long losing runs and one big month.
Those are properties of a SINGLE strategy that mixing removes (days of one rule are mostly not the days of another). So the lines that
ask for steadiness are asked of the MIX; each member is asked only for an edge of its own.

THE RULE (pipeline.json `mix`, every number is an existing number of the pipeline; the only thing new is WHICH idea is asked WHICH line):
  MEMBERS. An idea is a member when it reached a picked box (it stopped at stage 3, 4 or 5, or it is a finisher that has not read the
  unseen days), no row of its cards that was READ and FAILED is outside `mix.member_may_fail` (the steadiness rows P3.8 P3.9 P3.10, the
  reshuffle row P4.1, and the lock's net/drawdown, Sharpe and drawdown-at-one-micro rows 3.4 3.5 3.6), AND its picked box holds the EDGE
  rows P3.2 P3.3 P3.4 P3.7 as they are read TODAY on its own trades (an old card may predate a row: the rows are recomputed, not trusted).
  An idea that failed an edge row (average trade, 200 trades, a side that loses, the best 5 % of trades, beating random entries, profit
  factor) is not a member. An idea that has read the unseen days is never a member (that read is final). No search over subsets: the
  members are what the rule admits.
  ONE MARKET A MIX (the prop odds are in micros of one market).
  THE MIX. Every member's picked box on the build days, one contract each, all trades of a day together. The mix is read on the SAME rows a
  box is read on: P3.2 P3.3 P3.4 P3.7 (the edge rows), P3.8 P3.9 P3.10 (the steadiness rows), the lock's 3.3 to 3.8, and P4.1 the reshuffle,
  each on the mix's own days. Then what a person asks next: the prop check (plain row = the number, "live is worse" = the stress), each
  member's own steadiness rows beside the mix's, the daily correlation between members, per-year money, and what taking each member out does.

WHAT IT CANNOT SAY. The members were picked by the pipeline on these same days: the mix is in-sample, like every build-day read. A mix of
rules that are all long-only NQ continuation is one bet on NQ going up with trend; the correlation table shows it, the unseen read is what
tests it. Beating random entries (P4.2) is NOT read for a member that stopped at P4.1 (the pipeline stops there) and is read on the
unseen days (line 4.4); the mix says so.

API: members(root=None) -> {market: [member]}, left_out; read(market, root=None, names=None) -> the result; command(root=None, market=None).
Locked by tests/test_pipe_mix.py.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

import judge as J
import library as LB
import l2sim as S

from . import api
from . import lines as L
from . import pipe_gates as G
from . import pipe_prop as PP
from . import pipe_rules as PR
from . import pipe_store as PS

NEEDS = ("P3.2", "P3.3", "P3.4", "P3.7")
STEADY = ("P3.8", "P3.9", "P3.10")


def _failed(cards: dict) -> list:
    """Every row that was READ and FAILED over the stage cards of an idea -> [line]. A row with passed None (shown, not asked) is no fail."""
    out = []
    for n in sorted(k for k in cards if int(k) >= 3):            # stages 3-5 read the PICKED BOX; stage 1's rows are the maps' (the other bar's map too)
        for x in cards[n].get("lines") or []:
            if isinstance(x, dict) and x.get("passed") is False:
                out.append(str(x.get("line")))
    return out


def members(root=None, strict: bool = True) -> tuple:
    """-> ({market: [member]}, left_out [{name, why}]). member = {name, market, session, bar, sub, cell, failed (the rows it failed that the
    mix takes over), edge (its edge rows today), stopped, admitted}. Deterministic: every idea of the pipeline in the order of its name.
    strict False (a person's what-if: `--names`): an idea whose own box fails an edge row is KEPT, with admitted False and its rows."""
    may, by, left = set(PR.need("mix", "member_may_fail")), {}, []
    for name in sorted(str(s["name"]) for s in PS.ideas(root)):
        st, cards = PS.state(name, root), PS.stages(name, root)
        picked = st.get("picked") or {}
        if not picked.get("cell"):
            left.append({"name": name, "why": "no picked box (it stopped before stage 1 chose one)"})
            continue
        if any(int(n) >= 6 for n in cards) or st.get("status") in ("book", "awaits"):
            left.append({"name": name, "why": "it has read the unseen days (that read is final) or finished"})
            continue
        bad = [x for x in _failed(cards) if x not in may]
        if bad:
            left.append({"name": name, "why": "it fails an edge row of its own: " + ", ".join(sorted(set(bad)))})
            continue
        card = PS.card(name, root)
        market = card.get("market")
        m = {"name": name, "market": market, "session": card.get("session"), "bar": picked.get("bar"), "sub": picked.get("sub"), "cell": picked.get("cell"),
             "failed": sorted(set(_failed(cards))), "stopped": st.get("stopped_at"), "sides": card.get("sides")}
        try:
            x = _trades(m, root)
        except Exception as e:                       # a store that is gone or not the build days': named, never fatal
            left.append({"name": name, "why": f"its picked box's trades cannot be read: {str(e)[:100]}"})
            continue
        days = _days(market)
        rows = {r["line"]: r for r in G.variant_rows(_box(x, days, market, name, card.get("sides") or "both"), []) if r["line"] in NEEDS}
        off = sorted(k for k, r in rows.items() if r["passed"] is False)
        m["edge"] = {k: rows[k]["passed"] for k in sorted(rows)}
        m["edge_text"] = {k: rows[k]["text"] for k in sorted(rows)}
        m["admitted"] = not off
        if off and strict:
            left.append({"name": name, "why": "its own box fails an edge row today: " + "; ".join(rows[k]["text"][:110] for k in off)})
            continue
        by.setdefault(market, []).append(m)
    return by, left


def _trades(m: dict, root=None):
    """The picked box's trades on the build days, from its store: packed arrays (library.FIELDS)."""
    u = LB.load_unit(f"{m['sub']}-{m['market']}-tf{m['bar']}", PS.runs(root))
    if str(u["meta"].get("period") or "") != S.ALLOW_BP:
        raise J.Refuse(f"{m['name']}: its store is not the build days' ({u['meta'].get('period')!r}): it is not read")
    x = LB.unit_cell(u, m["cell"])
    return {k: np.asarray(x[k]) for k in LB.FIELDS}


def _calendar(market: str) -> list:
    return [d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), market, allow_holdout=S.ALLOW_BP)]


_DAYS = {}


def _days(market: str) -> np.ndarray:
    if market not in _DAYS:
        _DAYS[market] = np.array([dt.date.fromisoformat(d).toordinal() for d in _calendar(market)])
    return _DAYS[market]


def _box(x: dict, days: np.ndarray, root: str, name: str, sides: str = "both") -> dict:
    """A trade list as the box the line functions read (tables.box's shape, built from the trades): per trade net, per day net / count /
    worst open loss, the sides, and the trade list the steadiness rows read."""
    d = np.asarray(x["date"], np.int64)
    idx = np.searchsorted(days, d)
    net = np.zeros(len(days)); n = np.zeros(len(days))
    np.add.at(net, idx, x["net"]); np.add.at(n, idx, 1.0)
    by = {}
    for dd, ent, dur, v, mae in zip(d, x["entry_ms"], x["dur_s"], x["net"], x["mae"]):
        by.setdefault(int(dd), []).append((int(ent), int(ent) + int(dur) * 1000, float(v), abs(float(mae)) + LB.COMM_RT))
    up = np.asarray(x["side"]) > 0
    return {"root": root, "net": net[None, :], "n": n[None, :], "ids": [name], "unit": name, "days": days, "sides": sides,
            "long": float(np.asarray(x["net"])[up].sum()), "short": float(np.asarray(x["net"])[~up].sum()), "n_long": int(up.sum()), "n_short": int((~up).sum()),
            "trade_net": np.asarray(x["net"], np.float64), "trade_date": d, "trades": np.asarray(x["net"], np.float64), "day": net, "open": np.array(
                [LB._worst_open(by.get(int(dd), [])) + 0.0 for dd in days])}


def _rows(b: dict) -> list:
    """The mix's rows: the box rows of the pipeline (P3.2 .. P3.10), the lock's 3.3-3.8 and P4.1 -- each by the pipeline's own function."""
    rows = G.variant_rows(b, [])
    rows += [fn(b) for fn in L.BOX]
    rows.append(G.reshuffle_box(b))
    return rows


def _pack(parts: list) -> dict:
    x = {k: np.concatenate([p[k] for p in parts]) for k in LB.FIELDS}
    o = np.argsort(x["entry_ms"], kind="stable")
    return {k: v[o] for k, v in x.items()}


def _steady(x: dict, days: np.ndarray) -> dict:
    d = np.zeros(len(days)); np.add.at(d, np.searchsorted(days, np.asarray(x["date"], np.int64)), x["net"])
    ym = np.array([dt.date.fromordinal(int(v)).year * 12 + dt.date.fromordinal(int(v)).month for v in days])
    mu, mi = np.unique(ym, return_inverse=True)
    mon = np.zeros(len(mu)); np.add.at(mon, mi, d)
    run = best = 0
    for v in d:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    pos = mon[mon > 0].sum()
    sd = d.std(ddof=1)
    return {"months_won": float((mon > 0).mean()), "best_month_share": float(mon.max() / pos) if pos > 0 else 1.0, "losing_run": int(best),
            "sharpe": float(d.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0, "daily": d}


def read(market: str, root=None, names=None) -> dict:
    """THE MIX of one market on the build days (module docstring). `names` = an explicit list (a person's what-if; the result says so); None =
    the members the rule admits."""
    by, left = members(root, strict=names is None)
    ms = by.get(market, [])
    if names is not None:
        ms = [m for m in ms if m["name"] in set(names)]
        if len(ms) != len(set(names)):
            raise J.Refuse(f"not members of the {market} mix: {sorted(set(names) - {m['name'] for m in ms})}")
    if len(ms) < 2:
        return {"market": market, "members": [m["name"] for m in ms], "left_out": left, "text": f"{market}: {len(ms)} member(s): a mix needs two or more.", "rows": []}
    cal = _calendar(market)
    days = _days(market)
    xs = {m["name"]: _trades(m, root) for m in ms}
    mix = _pack(list(xs.values()))
    sides = {m["sides"] for m in ms}
    rows = _rows(_box(mix, days, market, "the mix", "both" if len(sides) != 1 else next(iter(sides)) or "both"))
    tail = {n: _tail(x) for n, x in [("the mix", mix), *xs.items()]}
    steady = {n: _steady(x, days) for n, x in xs.items()}
    ms_ = _steady(mix, days)
    names_ = [m["name"] for m in ms]
    C = np.corrcoef(np.array([steady[n]["daily"] for n in names_]))
    drop = {}
    for n in names_:
        rest = _pack([xs[k] for k in names_ if k != n])
        s = _steady(rest, days)
        drop[n] = {"months_won": s["months_won"], "sharpe": s["sharpe"], "avg_trade": float(rest["net"].mean())}
    prop = PP.odds(mix, cal)
    years = {}
    for n, x in [("mix", mix), *xs.items()]:
        d = steady["mix"]["daily"] if n == "mix" and "mix" in steady else (ms_["daily"] if n == "mix" else steady[n]["daily"])
        yr = np.array([dt.date.fromordinal(int(v)).year for v in days])
        years[n] = {int(y): float(d[yr == y].sum()) for y in sorted(set(yr))}
    mix_row = {"trades": int(len(mix["net"])), "net": float(mix["net"].sum()), "avg_trade": float(mix["net"].mean()), "months_won": ms_["months_won"],
               "best_month_share": ms_["best_month_share"], "losing_run": ms_["losing_run"], "sharpe": ms_["sharpe"]}
    text = _text(market, ms, rows, mix_row, steady, drop, C, prop, years, left, names is not None, tail)
    return {"market": market, "members": ms, "left_out": left, "rows": rows, "mix": mix_row, "single": {n: {k: v for k, v in s.items() if k != "daily"} for n, s in steady.items()},
            "without": drop, "tail": tail, "correlation": {"names": names_, "matrix": C.round(3).tolist()}, "prop": prop, "years": years, "what_if": names is not None,
            "note": "build days only; the members were picked by the pipeline on these days (in-sample); the unseen days are not read", "text": text}


def _tail(x: dict) -> dict:
    """What is left of the net without the best 1 / 2 / 5 % of trades (P3.7 reads the 5 %; the others are shown so the cut is visible)."""
    t = np.sort(np.asarray(x["net"], np.float64))
    out = {}
    for share in (0.01, 0.02, 0.05):
        k = max(1, int(round(share * len(t) + 1e-9)))
        out[f"{int(round(share * 100))} %"] = float(t[:-k].sum()) if len(t) > k else 0.0
    out["all"] = float(t.sum())
    return out


def _pc(v) -> str:
    return "-" if v is None else f"{100 * v:.0f} %"


def _text(market, ms, rows, mix, steady, drop, C, prop, years, left, what_if, tail=None) -> str:
    out = [f"THE {market} MIX on the build days, {len(ms)} members" + (" (a what-if: the members were named by a person)" if what_if else " (the rule's members)") +
           f": {mix['trades']:,} trades, average trade ${mix['avg_trade']:,.0f}, months won {_pc(mix['months_won'])}, Sharpe {mix['sharpe']:.2f}, "
           f"longest losing run {mix['losing_run']} days. Build days only; the unseen days are NOT read."]
    out.append("")
    out.append("member".ljust(24) + "session  stopped at   avg trade  months won  best month  losing run  Sharpe  failed rows it hands to the mix")
    for m in ms:
        s = steady[m["name"]]
        own = "" if m.get("admitted", True) else "  [fails its own edge row: " + ", ".join(k for k, v in m["edge"].items() if v is False) + "]"
        out.append(f"{m['name']:24s}{str(m['session']):9s}{str(m['stopped']):13s}{'':10s}{_pc(s['months_won']):>10s}  {_pc(s['best_month_share']):>10s}  {s['losing_run']:>10d}  {s['sharpe']:6.2f}  {', '.join(m['failed']) or '-'}{own}")
    out.append("")
    out.append("The mix, row by row (the pipeline's own functions):")
    for r in rows:
        mark = {True: "PASS", False: "FAIL", None: "shown"}[r.get("passed")]
        out.append(f"  {mark:5s} {r['text'][:150]}")
    out.append("")
    p, st = prop, prop.get("stress") or {}
    out.append(f"Prop check, {p['account']['name']}: eval within {p['days']} days {_pc(p['eval'])} at {p['size']} micros each, payout {_pc(p['payout'])}"
               f" (stress, live is worse: {_pc(st.get('eval'))} / {_pc(st.get('payout'))}). The mix at 1 contract each has a worst open drawdown the account's limit is measured against: see row 3.6.")
    out.append("")
    if tail:
        out.append("What is left of the net without the best 1 / 2 / 5 % of trades (row P3.7 reads the 5 %):")
        for n, t_ in tail.items():
            out.append(f"  {n:28s} all ${t_['all']:>10,.0f}   without best 1 % ${t_['1 %']:>10,.0f}   2 % ${t_['2 %']:>10,.0f}   5 % ${t_['5 %']:>10,.0f}")
        out.append("")
    out.append("Taking one member out (what it adds):")
    for n, d in drop.items():
        out.append(f"  without {n:24s} months won {_pc(d['months_won'])}  Sharpe {d['sharpe']:.2f}  avg trade ${d['avg_trade']:,.0f}")
    out.append("")
    iu = np.triu_indices(len(ms), 1)
    out.append(f"Daily correlation between members: mean {C[iu].mean():.2f}, highest {C[iu].max():.2f}.")
    ys = sorted(years["mix"])
    out.append("Per year, the mix: " + ", ".join(f"{y} ${years['mix'][y]:,.0f}" for y in ys))
    out.append("Beating random entries (P4.2) is not read for a member that stopped at P4.1 (the pipeline stops there): it is read on the unseen days (line 4.4).")
    out.append(f"Left out ({len(left)} ideas): they have no picked box, have read the unseen days, or fail an edge row of their own. Use `bp.py pipe mix --left-out` to list them.")
    return "\n".join(out)


def command(root=None, market=None, names=None, left_out: bool = False) -> dict:
    by, left = members(root)
    if left_out:
        txt = "\n".join(f"{x['name']:34s} {x['why']}" for x in left) or "nobody is left out"
        return api.result("pipe mix", left_out=left, text=txt)
    marks = [market] if market else sorted(by, key=lambda k: -len(by[k]))
    got = [read(m, root, names) for m in marks if m in by]
    if not got:
        return api.result("pipe mix", mixes=[], text="no market has a member: no idea has a picked box that fails only steadiness rows")
    return api.result("pipe mix", mixes=got, text="\n\n".join(g["text"] for g in got))
