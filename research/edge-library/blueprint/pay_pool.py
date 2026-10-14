"""pay_pool.py -- THE POOL AND THE SLOTS of the payout pipeline (design step 3). An idea of the pipeline is a MEMBER when the runner
picked a box for it (the middle one of its boxes that make money on the build days: never the best) and that box's trades fit ONE of
the owner's three sessions. A member is asked nothing else: the set is what is judged (pay_build).

  clock(ms) -> the minute of the day in New York (0 .. 1439)
  fits(x, slot=None) -> (slot id | None, keep, share)
        the slot most of a box's trades are ENTERED AND CLOSED inside (or the slot named), the trades that are (keep), and their share. A trade that is
        still open when its slot ends is left out: the owner is flat before the next session, so its stored result is not what he gets
  micro(x) -> the trades at ONE MICRO, by the library's micro cost model (as propodds.sized): {"net", "cost" (mae + commission)}
  daily(x, keep, days) -> {"net", "open", "up", "n"}: one entry a session day of `days` (ordinals), at one micro
        net = the day's P&L · open = its WORST OPEN LOSS (library._worst_open) · up = the highest point of its closed trades · n = trades
  geometry(cell) -> {"stop", "target_r", "kind"}: the box's stop and its target in R; kind "tight" (a target under 1 R), "even"
        (1 R to under 2 R), "wide" (2 R or more) or "none" (no target: it leaves at the session's end)
  calendar(markets) -> the build days of those markets together, as ordinals (a day one market has and another has not is a day)
  members(root=None) -> (members, left_out)
        member = {"name", "family", "market", "session", "slot", "both_sides", "read" (None = not yet, True = its one read of the
        unseen days passed; an idea whose read FAILED is left out: that read is final), "options": [option]}; option = {"cell", "kind", "geometry", "trades", "win_rate", "kept", "net"
        (one contract, the kept trades), "x" (the kept trades), "sub", "bar"}. The FIRST option is the runner's pick. The others are
        the middle box (by eval odds, as the pick is) of each other kind of target among the boxes that held every line at stage 1:
        the tuner may choose a tighter or a wider target, never a best box.
        left_out = [{"name", "why"}]: an idea with a pick that is no member, and why
  unseen(member, option, root=None) -> (the box's trades on the unseen days, their session days) or None
        ONLY what the idea's ONE read left on file and only of an idea whose read passed (propodds.handed: nothing is run here)

Reads the pipeline's stores; runs nothing; writes nothing. Locked by tests/test_pay_pool.py.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

import judge as J
import l2sim as S
import library as LB

from . import pay_rules as PY
from . import pipe_store as PS
from . import propodds as PO
from . import rules as R

KINDS = ("tight", "even", "wide", "none")


def clock(ms) -> int:
    t = dt.datetime.fromtimestamp(int(ms) / 1000, S.ET)
    return t.hour * 60 + t.minute


def _inside(x: dict) -> tuple:
    """(each trade's slot by its entry, whether the trade is entered AND closed inside that slot)."""
    ent = np.asarray(x["entry_ms"], np.int64)
    out = ent + np.asarray(x["dur_s"], np.int64) * 1000
    a = np.array([PY.slot_of(clock(v)) for v in ent], object)
    b = [PY.slot_of(clock(v - 1)) for v in out]                       # (a trade closed on the slot's last second is inside it)
    return a, np.array([s is not None and s == e and o - i < 86_400_000 for s, e, i, o in zip(a, b, ent, out)], bool)


def fits(x: dict, slot=None) -> tuple:
    a, inside = _inside(x)
    if slot is None:
        if not inside.any():
            return None, inside, 0.0
        ids, n = np.unique(a[inside], return_counts=True)
        slot = str(ids[int(np.argmax(n))])
    keep = inside & (a == slot)
    return slot, keep, float(keep.mean()) if len(keep) else 0.0


def micro(x: dict) -> dict:
    div = R.template("sizes")["micros_per_contract"]
    return {"net": (np.asarray(x["net"], np.float64) + LB.COMM_RT) / div - LB.MICRO_RT_USD,
            "cost": np.abs(np.asarray(x["mae"], np.float64)) / div + LB.MICRO_RT_USD}


def daily(x: dict, keep, days: np.ndarray) -> dict:
    m, keep = micro(x), np.asarray(keep, bool)
    d, ent = np.asarray(x["date"], np.int64)[keep], np.asarray(x["entry_ms"], np.int64)[keep]
    out, net, cost = ent + np.asarray(x["dur_s"], np.int64)[keep] * 1000, m["net"][keep], m["cost"][keep]
    by: dict = {}
    for i in np.lexsort((ent, d)):
        by.setdefault(int(d[i]), []).append((int(ent[i]), int(out[i]), float(net[i]), float(cost[i])))
    got = {k: np.zeros(len(days)) for k in ("net", "open", "up", "n")}
    at = {int(v): i for i, v in enumerate(days)}
    for day, rows in by.items():
        i = at.get(day)
        if i is None:                               # a trade on a day the calendar does not have is not a day of the pool
            continue
        run = np.cumsum([t[2] for t in sorted(rows, key=lambda t: t[1])])
        got["net"][i], got["n"][i] = float(run[-1]), len(rows)
        got["open"][i], got["up"][i] = LB._worst_open(rows) + 0.0, max(0.0, float(run.max()))
    return got


def geometry(cell: dict) -> dict:
    e = cell.get("exit") or {}
    r = float(e.get("tgt_r") or 0.0)
    return {"stop": f"{e.get('stop_val')} {e.get('stop_mode')}", "target_r": r,
            "kind": "none" if r <= 0 else "tight" if r < 1 else "even" if r < 2 else "wide"}


def calendar(markets) -> np.ndarray:
    seen = set()
    for m in sorted(set(markets)):
        seen.update(d.toordinal() for d in S.sessions(*S.period(S.ALLOW_BP), m, allow_holdout=S.ALLOW_BP))
    return np.array(sorted(seen), np.int64)


def _option(u: dict, cells: dict, cid: str, slot, sub: str, bar: str):
    """One box of a loaded store as an option of its member, or the reason it is none."""
    if cid not in cells:
        return None, f"box {cid} is not in its store"
    x = {k: np.asarray(v) for k, v in LB.unit_cell(u, cid).items()}
    if not len(x["net"]):
        return None, f"box {cid} has no trade"
    s, keep, share = fits(x)
    need = PY.need("pool")
    if s is None or share < need["in_slot"] or (slot is not None and s != slot):
        return None, (f"only {100 * share:.0f} % of box {cid}'s trades are entered and closed inside one session (need {100 * need['in_slot']:.0f} %)"
                      if slot is None or s == slot else f"box {cid} trades the {s} session, the pick the {slot} one")
    kept = {k: v[keep] for k, v in x.items()}
    n, net = int(keep.sum()), float(kept["net"].sum())
    if n < need["trades"] or net <= 0:
        return None, (f"box {cid} has {n} trades inside its session (need {need['trades']})" if n < need["trades"] else
                      f"box {cid} loses money on the trades inside its session")
    g = geometry(cells[cid])
    return {"cell": cid, "kind": g["kind"], "geometry": g, "trades": n, "win_rate": float((kept["net"] > 0).mean()), "kept": share, "net": net,
            "x": kept, "slot": s, "sub": sub, "bar": bar}, None


def _alternates(cands: list, picked: dict, cells: dict) -> list:
    """The middle box (by eval odds) of each OTHER kind of target among the stage-1 boxes of the pick's own heat map."""
    mine = [c for c in cands or [] if c.get("sub") == picked["sub"] and str(c.get("bar")) == str(picked["bar"]) and c.get("cell") in cells]
    own = geometry(cells[picked["cell"]])["kind"] if picked["cell"] in cells else None
    out = []
    for kind in KINDS:
        rows = sorted((c for c in mine if geometry(cells[c["cell"]])["kind"] == kind), key=lambda c: (c.get("eval") or 0.0, c["cell"]))
        if kind != own and rows:
            out.append(rows[len(rows) // 2]["cell"])
    return out


def members(root=None) -> tuple:
    from . import pipe_portfolio as PF              # (the block list's word for a family that rests orders on both sides)
    got, left = [], []
    for st in PS.ideas(root):
        p, name = st.get("picked"), st["name"]
        if not isinstance(p, dict) or not p.get("cell"):
            continue                                # no pick yet: the runner has not got that far (it is no member and no news)
        try:
            card, stages = PS.card(name, root), PS.stages(name, root)
            u = LB.load_unit(f"{p['sub']}-{card['market']}-tf{p['bar']}", PS.runs(root))
        except (OSError, ValueError, KeyError) as e:
            left.append({"name": name, "why": f"its store cannot be read ({type(e).__name__})"})
            continue
        if str(u["meta"].get("period") or "") != S.ALLOW_BP:
            left.append({"name": name, "why": "its store is not the build days'"})
            continue
        cells = {c["id"]: c for c in u["meta"]["cells"]}
        first, why = _option(u, cells, p["cell"], None, p["sub"], str(p["bar"]))
        if first is None:
            left.append({"name": name, "why": why})
            continue
        opts = [first]
        for cid in _alternates((stages.get(1) or {}).get("candidates"), p, cells):
            o, _ = _option(u, cells, cid, first["slot"], p["sub"], str(p["bar"]))
            if o is not None:
                opts.append(o)
        six = stages.get(6)
        if six and not six.get("passed"):           # the house law: a read of the unseen days is final. A strategy that failed it trades no account
            left.append({"name": name, "why": "its one read of the unseen days failed: that is final"})
            continue
        got.append({"name": name, "family": st.get("family"), "market": card["market"], "session": card.get("session"), "slot": first["slot"],
                    "both_sides": PF.both_sides(st.get("family")), "read": None if not six else bool(six.get("passed")), "options": opts})
    return got, left


def unseen(member: dict, option: dict, root=None):
    try:
        h = PO.handed(option["sub"], PS.ideas_root(root))
        x = {k: np.asarray(v) for k, v in PO.cell(h, option["cell"]).items()}
    except J.Refuse:
        return None
    _, keep, _ = fits(x, member["slot"])
    return {k: v[keep] for k, v in x.items()}, np.array([dt.date.fromisoformat(d).toordinal() for d in h["calendar"]], np.int64)
