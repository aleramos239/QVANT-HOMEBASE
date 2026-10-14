"""pay_build.py -- THE SET BUILDER of the payout pipeline (design steps 3 to 5; `bp.py pipe payout build | show`). From the pool
(pay_pool) it builds, for each funded account's rule file, THE SET that pays the most: ONE strategy a slot, a size, a day rule and the
rotation rule -- judged together on the group score (pay_score), on the BUILD DAYS ONLY. Then it says what the set did on the unseen
days, which it never used to choose anything.

  combine(parts, size, gain=None, loss=None) -> the DAY of an account: {"net", "traded", "open", "up"}, one entry a session day
        parts = the slots' strategies in the day's order (each {"net", "open", "up", "n"} at one micro, or None = the slot is empty),
        all at `size` micros. THE DAY RULE: once a slot has ended with the day up `gain` dollars or down `loss` dollars, the later
        slots do not trade. A slot's worst open loss and highest point are read from where the day stood when the slot began.
  eligible(member, option, rule_id) -> why it may not trade this account, or None
        Apex funded (pay_rules firms.apex): no entry rule that rests orders on both sides, and a target of min_target_r or more
  build(root=None, paths=None, seed=None, desk=None) -> the result; saved as <pipeline root>/payout/set.json, one row added to
        score.jsonl (the main score over time), a notice when the set's strategies changed
        FOR EACH RULE FILE that an account that is `on` is scored on:
          THE SEARCH, slot by slot until nothing changes: every strategy that may trade the slot (and "nobody") is tried with the
          others as they are, each at ITS OWN BEST SETTING -- every size step the funded account may trade, every day rule. A SIZE
          COUNTS WITH ITS NEIGHBOURS: a setting's number is the average of its size step and the steps beside it, so one lucky size
          is not chosen. A strategy takes the slot only when the set pays more with it than with anybody else or nobody.
          WHAT EACH MEMBER ADDS = the set's number minus the set without it (the others at their own best setting).
          THE RESERVES of a slot = the next best strategies of another family; THE ROTATION RULE (pay_rotate.form) is tried at every
          setting of pay_rules `rotation` and kept only when it beats no rule AND the settings beside it beat no rule too.
        THE GROUP SCORE = every account on the SAME drawn days, from its own balance: expected payout a week over score.days and
        score.short_days, the chance of any payout, how many accounts survive; beside it the "live is worse" row (propodds.worse).
        THE UNSEEN DAYS: when every strategy of the set has its ONE read on file and passed it, the same score on those days.
        PROVEN = it pays there, and at least proof.keep of what it paid on the build days. A member that has no read yet, or whose
        read failed, is named: the set is then NOT PROVEN and may not go on a real account.
  show(root=None) -> the result on file, as it was built (nothing is run)
  series(root=None) -> a function name -> (its box's P&L a day at one micro, the last day): what pay_rotate.evening reads
  idle(root=None) -> the runner's call while the queue is idle: a new build when the pool, the accounts or the rules changed, and the
        evening's rotation once a day after the close

HONEST LIMITS, said in every result: the search looked at many sets on the build days and took the best, so its number there flatters
it -- the unseen days are the judge. An account whose floor trails the intraday high is read on the friendly side (pay_score.FRIENDLY).
A funded account is walked at ONE size: a scaling plan's later steps, Apex's half size and its 30 % open-loss rule are not simulated.
Nothing here places an order, and nothing here reads an unseen day that an idea's own one read did not leave on file.
Locked by tests/test_pay_build.py.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import numpy as np

import judge as J
import l2sim as S

from . import api
from . import pay_accounts as PA
from . import pay_pool as PP
from . import pay_rotate as RO
from . import pay_rules as PY
from . import pay_score as SC
from . import pipe_store as PS
from . import propodds as PO

SET, SCORES = "set.json", "score.jsonl"
EVENING = (17, 15)                                  # New York: the rotation is read after the close
BETTER = 1.02                                       # a change must pay 2 % more to be taken (two equal sets do not swap places each build)
LIMITS = ("The search tried many sets on the build days and kept the best: its build-day number flatters it. The unseen days are the judge.",
          "A strategy whose own read of the unseen days failed is never used, so the set's unseen-days number is helped by that choice. Live and shadow results are the last judge.",
          "One size for the whole walk: a scaling plan's later steps, Apex's half size and its 30 % open-loss rule are not simulated.")


def combine(parts: list, size: float, gain=None, loss=None) -> dict:
    n = len(next(p for p in parts if p is not None)["net"])
    cum, worst, high, traded, stop = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n, bool), np.zeros(n, bool)
    for p in parts:
        if p is None:
            continue
        on = ~stop
        worst = np.maximum(worst, np.where(on, p["open"] * size - cum, 0.0))
        high = np.maximum(high, np.where(on, cum + p["up"] * size, 0.0))
        cum = cum + np.where(on, p["net"] * size, 0.0)
        traded |= on & (p["n"] > 0)
        if gain is not None:
            stop |= cum >= gain
        if loss is not None:
            stop |= cum <= -loss
    return {"net": cum, "traded": traded, "open": worst, "up": high}


def eligible(member: dict, option: dict, rule_id: str):
    need = PY.firm_need(rule_id)
    if need.get("one_side") and member.get("both_sides") is not False:
        return "its entry rule rests orders on both sides" if member.get("both_sides") else "the block list does not say whether its entry rule rests orders on both sides"
    if need.get("min_target_r") and option["geometry"]["target_r"] < need["min_target_r"]:
        return f"its target is under {need['min_target_r']} R (the stop may be at most 5x the target)"
    return None


def _steps(r: dict) -> list:
    top = min(r.get("cap_micros") or 10 ** 9, (r.get("scaling_micros") or {}).get("start") or 10 ** 9)
    return [s for s in PY.need("sizes") if s <= top]


class _Scorer:
    """The expected dollars a week one rule file's accounts are paid for a day pool, on the drawn days `idx`."""

    def __init__(self, rid: str, r: dict, accounts: list, idx: np.ndarray):
        self.rid, self.r, self.idx, self.week = rid, r, idx, PY.need("score", "week")
        starts: dict = {}
        for a in accounts:
            st = PA.start(a)
            starts.setdefault((round(st["profit"], 2), round(st["peak"], 2)), [st, 0])[1] += 1
        self.starts = list(starts.values())

    def walks(self, day: dict) -> list:
        return [(SC.account(day, self.r, self.idx, st, self.rid), n) for st, n in self.starts]

    def read(self, day: dict) -> tuple:
        """(the expected dollars a week over these accounts, the share of the futures in which an account is lost: the worst of them)."""
        ws = self.walks(day)
        return (sum(float(w["paid"].mean()) * n for w, n in ws) * self.week / self.idx.shape[1], max(float((w["bust"] > 0).mean()) for w, _ in ws))

    def value(self, day: dict) -> float:
        return self.read(day)[0]


def _setting(parts: list, sc: _Scorer) -> dict:
    """The best setting of a set of slot strategies: every size step and day rule, a size judged with the steps beside it. SURVIVAL: a
    setting that loses an account in more than score.max_bust of the futures cannot be chosen; none that can = no setting (size None)."""
    none = {"value": 0.0, "raw": 0.0, "size": None, "gain": None, "loss": None, "bust": 0.0}
    if all(p is None for p in parts):
        return none
    steps, rule, mll, cap = _steps(sc.r), PY.need("day_rule"), float(sc.r["trailing_mll"]), PY.need("score", "max_bust")
    many = sum(p is not None for p in parts) > 1     # (the day rule acts between two slots: with one strategy it is no setting)
    best = none
    for g in (rule["gain"] if many else [None]):
        for lo in (rule["loss"] if many else [None]):
            row = [sc.read(combine(parts, s, g and g * mll, lo and lo * mll)) for s in steps]
            for i, s in enumerate(steps):
                near = float(np.mean([v for v, _ in row[max(0, i - 1):i + 2]]))
                if row[i][1] <= cap and near > best["value"]:
                    best = {"value": near, "raw": row[i][0], "size": s, "gain": g, "loss": lo, "bust": row[i][1]}
    return best


def _search(cands: dict, order: list, sc: _Scorer) -> tuple:
    """(choice {slot: candidate | None}, its setting, bench {slot: [candidates]}) -- slot by slot until nothing changes."""
    choice = dict.fromkeys(order)
    part = lambda c: None if c is None else c[1]["day"]  # noqa: E731
    now = _setting([part(choice[s]) for s in order], sc)
    ranked: dict = {}
    for _ in range(3):
        moved = False
        for slot in sorted(order, key=lambda s: -len(cands.get(s, []))):
            rows = []
            for c in [None, *cands.get(slot, [])]:
                got = _setting([part(c if s == slot else choice[s]) for s in order], sc)
                rows.append((got["value"], c, got))
            rows.sort(key=lambda t: -t[0])
            ranked[slot] = rows
            top = rows[0]
            if top[1] is not choice[slot] and top[0] > now["value"] * BETTER:
                choice[slot], now, moved = top[1], top[2], True
        if not moved:
            break
    bench = {}
    for slot in order:
        took, seen, out = choice[slot], set(), []
        if took is not None:
            seen.add(took[0]["family"])
            for v, c, _ in ranked.get(slot, []):
                if c is not None and c[0]["name"] != took[0]["name"] and c[0]["family"] not in seen and v > 0 and len(out) < PY.need("rotation", "bench"):
                    seen.add(c[0]["family"])
                    out.append(c)
        bench[slot] = out
    return choice, now, bench


def _parts(choice: dict, bench: dict, order: list, rot=None) -> list:
    """The slots' day arrays in the day's order: the first choice, or -- with a rotation rule -- whoever of the slot's list is in form."""
    out = []
    for slot in order:
        c = choice[slot]
        if c is None:
            out.append(None)
        elif rot is None:
            out.append(c[1]["day"])
        else:
            opts = [c[1]["day"], *[b[1]["day"] for b in bench[slot]]]
            out.append(RO.rotated(opts, [RO.form(o["net"], rot["lookback"], rot["within"]) for o in opts]))
    return out


def _rotation(choice: dict, bench: dict, order: list, st: dict, sc: _Scorer) -> tuple:
    """(the rotation rule kept | None, every setting tried) at the set's own setting: kept only when it AND its neighbours beat no rule."""
    need, mll = PY.need("rotation"), float(sc.r["trailing_mll"])
    at = lambda rot: sc.value(combine(_parts(choice, bench, order, rot), st["size"], st["gain"] and st["gain"] * mll, st["loss"] and st["loss"] * mll))  # noqa: E731
    off = at(None)
    tried = [{"lookback": w, "within": k, "value": at({"lookback": w, "within": k})} for w in need["lookback"] for k in need["within"]]
    kept = None
    for t in sorted(tried, key=lambda t: -t["value"]):
        near = [x["value"] for x in tried if x["lookback"] == t["lookback"] and abs(need["within"].index(x["within"]) - need["within"].index(t["within"])) <= 1]
        if t["value"] > off * BETTER and min(near) > off:
            kept = {"lookback": t["lookback"], "within": t["within"], "value": t["value"], "off": off}
            break
    return kept, {"off": off, "tried": tried}


def _stats(day: dict) -> dict:
    net, on = day["net"], day["traded"]
    run = best = 0
    for v in net:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    return {"days": int(len(net)), "traded": int(on.sum()), "win_days": float((net[on] > 0).mean()) if on.any() else 0.0, "avg_day": float(net.mean()),
            "worst_day": float(net.min()), "worst_open": float(day["open"].max()), "losing_streak": int(best), "net": float(net.sum())}


def _member(c, adds=None) -> dict:
    m, o = c
    return {"name": m["name"], "family": m["family"], "market": m["market"], "session": m["session"], "cell": o["cell"], "kind": o["kind"],
            "stop": o["geometry"]["stop"], "target_r": o["geometry"]["target_r"], "trades": o["trades"], "win_rate": o["win_rate"], "read": m["read"],
            **({"adds": adds} if adds is not None else {})}


def _day_of(s: dict, cal: np.ndarray, x_of) -> dict | None:
    """A built set's DAY on another calendar (the unseen days): each strategy's trades from `x_of(name, cell)`, or None when one has none."""
    parts, order, mll = [], [k["id"] for k in PY.slots()], float(s["mll"])
    for slot in order:
        m = s["slots"].get(slot)
        if not m:
            parts.append(None)
            continue
        opts = []
        for who in [m, *(m.get("bench") or [] if s.get("rotation") else [])]:
            got = x_of(who["name"], who["cell"])
            if got is None:
                if who is m:
                    return None
                continue                            # a reserve with no read never trades there
            opts.append(got)
        if s.get("rotation"):
            rot = s["rotation"]
            parts.append(RO.rotated([o[1] for o in opts], [RO.form(np.concatenate([o[0], o[1]["net"]]), rot["lookback"], rot["within"])[len(o[0]):] for o in opts]))
        else:
            parts.append(opts[0][1])
    return combine(parts, s["size"], s["gain"] and s["gain"] * mll, s["loss"] and s["loss"] * mll)


def _sig(members: list, accounts: list) -> str:
    what = {"m": [(m["name"], m["read"], [o["cell"] for o in m["options"]]) for m in members],
            "a": [(a["id"], a.get("rules"), a.get("on"), a.get("balance"), a.get("peak")) for a in accounts], "r": PY.need()}
    return hashlib.sha256(json.dumps(what, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def show(root=None) -> dict | None:
    return _read(PS.root(root) / "payout" / SET)


def _names(the_set) -> dict:
    return {rid: {k: (v or {}).get("name") for k, v in s["slots"].items()} for rid, s in ((the_set or {}).get("sets") or {}).items()}


def build(root=None, paths=None, seed=None, desk=None) -> dict:
    need, order = PY.need("score"), [s["id"] for s in PY.slots()]
    accounts = PA.sync(root, desk)
    members, left = PP.members(root)
    on = [a for a in accounts if a.get("on") and a.get("connected", True) and a.get("rules") and a.get("size")]      # (an account the Desk no longer has is not scored)
    cal = PP.calendar([m["market"] for m in members] or ["NQ"])
    for m in members:
        for o in m["options"]:
            o["day"] = PP.daily(o["x"], np.ones(len(o["x"]["net"]), bool), cal)
    seed = need["seed"] if seed is None else int(seed)
    idx_s = SC.blocks(len(cal), int(paths or need["search_paths"]), need["days"], need["block"], seed)
    idx = SC.blocks(len(cal), int(paths or need["paths"]), need["days"], need["block"], seed)
    sets, walks, worse, short_walks, short = {}, [], [], [], need["short_days"]
    for rid in sorted({a["rules"] for a in on}):
        r, mine = PO.app().load_rules(rid), [a for a in on if a["rules"] == rid]
        sc = _Scorer(rid, r, mine, idx_s)
        cands, barred = {s: [] for s in order}, []
        for m in members:
            for o in m["options"]:
                why = eligible(m, o, rid)
                if why is None:
                    cands[m["slot"]].append((m, o))
                elif o is m["options"][0]:
                    barred.append({"name": m["name"], "why": why})
        choice, st, bench = _search(cands, order, sc)
        slots = {}
        for slot in order:
            c = choice[slot]
            if c is None:
                slots[slot] = None
                continue
            without = _setting([None if s == slot or choice[s] is None else choice[s][1]["day"] for s in order], sc)
            slots[slot] = {**_member(c, st["value"] - without["value"]), "bench": [_member(b) for b in bench[slot]]}
        rot, tried = (None, None)
        if st["size"] is not None:
            rot, tried = _rotation(choice, bench, order, st, sc)
        one = {"rules": rid, "account_name": r.get("name"), "confirmed": bool(r.get("confirmed")), "accounts": [a["id"] for a in mine], "mll": r["trailing_mll"],
               "slots": slots, "size": st["size"], "gain": st["gain"], "loss": st["loss"], "rotation": rot, "rotation_tried": tried,
               "candidates": {s: len(cands[s]) for s in order}, "barred": barred, "friendly": SC.FRIENDLY if r.get("trail") == "intraday" else None}
        if st["size"] is not None:
            mll = float(r["trailing_mll"])
            day = combine(_parts(choice, bench, order, rot), st["size"], st["gain"] and st["gain"] * mll, st["loss"] and st["loss"] * mll)
            one["stats"] = _stats(day)
            full = _Scorer(rid, r, mine, idx)
            wnet, wopn = PO.worse(day["net"], day["traded"], day["open"])
            bad = {**day, "net": wnet, "open": wopn}
            for a in mine:
                walks.append((a["id"], SC.account(day, r, idx, PA.start(a), rid)))
                worse.append((a["id"], SC.account(bad, r, idx, PA.start(a), rid)))
                short_walks.append((a["id"], SC.account(day, r, idx[:, :short], PA.start(a), rid)))      # its own walk: a payout after it does not count
            one["per_week"] = full.value(day)
        else:
            one["per_week"] = 0.0
            for a in mine:                          # nobody trades it: it pays nothing and is never lost
                zero = {k: np.zeros(len(idx), np.int64 if k != "paid" else np.float64) for k in ("paid", "pays", "first", "bust")}
                walks.append((a["id"], zero))
                worse.append((a["id"], zero))
                short_walks.append((a["id"], zero))
        sets[rid] = one
    out = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "sig": _sig(members, accounts), "accounts": accounts,
           "pool": {"members": len(members), "by_slot": {s: sum(m["slot"] == s for m in members) for s in order},
                    "read": sum(m["read"] is True for m in members), "left_out": left},
           "slots": [{"id": s["id"], "label": s["label"], "from": s["from"], "to": s["to"]} for s in PY.slots()],
           "sets": sets, "group": None, "short": None, "worse": None, "unseen": None, "proven": None, "notes": list(LIMITS)}
    if walks:
        out["group"], out["short"] = SC.group(walks, need["days"], need["week"]), SC.group(short_walks, short, need["week"])
        out["worse"] = SC.group(worse, need["days"], need["week"])["per_week"]
    out.update(_unseen(out, members, on, root, int(paths or need["paths"]), seed))
    out["text"] = said(out)
    was = show(root)
    PS._write(PA.folder(root) / SET, out)
    with open(PA.folder(root) / SCORES, "a", encoding="utf-8") as f:
        f.write(json.dumps({"utc": out["built_utc"], "per_week": (out["group"] or {}).get("per_week", 0.0), "short": (out["short"] or {}).get("per_week"),
                            "worse": out["worse"], "unseen": (out["unseen"] or {}).get("per_week"), "proven": out["proven"], "members": len(members)}) + "\n")
    if _names(was) != _names(out):
        RO.notice(root, "built", "A new set was built. " + out["text"].split("\n")[0], sets=_names(out))
    return out


def _unseen(out: dict, members: list, on: list, root, paths: int, seed: int) -> dict:
    """The built sets on the unseen days their members' own reads left on file -> {"unseen", "proven", "waiting"}."""
    need, by = PY.need("score"), {m["name"]: m for m in members}
    waiting, got, cals = [], {}, []
    for s in out["sets"].values():
        for m in filter(None, s["slots"].values()):
            for who in [m, *m.get("bench", [])]:
                key = (who["name"], who["cell"])
                if key in got:
                    continue
                mem = by[who["name"]]
                opt = next(o for o in mem["options"] if o["cell"] == who["cell"])
                got[key] = PP.unseen(mem, opt, root)
                if got[key] is None and who is m:
                    waiting.append({"name": who["name"], "why": "its read of the unseen days failed" if mem["read"] is False else
                                    "it has not read the unseen days yet" if mem["read"] is None else "its read does not hold this box"})
                elif got[key] is not None:
                    cals.append(got[key][1])
    filled = [s for s in out["sets"].values() if s["size"] is not None]
    if waiting or not filled or not cals:
        return {"unseen": None, "proven": False if waiting and filled else None, "waiting": waiting}
    cal = np.unique(np.concatenate(cals))
    build_cal = PP.calendar([m["market"] for m in members])

    def x_of(name, cell):
        g = got.get((name, cell))
        if g is None:
            return None
        o = next(o for o in by[name]["options"] if o["cell"] == cell)
        return PP.daily(o["x"], np.ones(len(o["x"]["net"]), bool), build_cal)["net"], PP.daily(g[0], np.ones(len(g[0]["net"]), bool), cal)

    idx, walks = SC.blocks(len(cal), paths, need["days"], need["block"], seed), []
    for rid, s in out["sets"].items():
        if s["size"] is None:
            continue
        day, r = _day_of(s, cal, x_of), PO.app().load_rules(rid)
        for a in (x for x in on if x["rules"] == rid):
            walks.append((a["id"], SC.account(day, r, idx, PA.start(a), rid)))
    g = SC.group(walks, need["days"], need["week"])
    g["span"] = [dt.date.fromordinal(int(cal[0])).isoformat(), dt.date.fromordinal(int(cal[-1])).isoformat()]
    base = (out["group"] or {}).get("per_week", 0.0)
    return {"unseen": g, "proven": bool(g["per_week"] > 0 and g["per_week"] >= PY.need("proof", "keep") * base), "waiting": []}


def said(out: dict) -> str:
    """The result in plain words, the answer first."""
    usd, g = PO.usd, out.get("group")
    if not out["sets"]:
        return "No account is on: nothing to build a set for (payout/accounts.json)."
    if not g or all(s["size"] is None for s in out["sets"].values()):
        return (f"No set: none of the {out['pool']['members']} strategies in the pool pays on these accounts by itself or together. "
                "The pool grows as the runner takes ideas through their stages.")
    weeks = PY.need("score", "days") // PY.need("score", "week")
    head = (f"Expected payout: {usd(round(g['per_week']))} a week over {weeks} weeks across {len(g['accounts'])} account{'s' * (len(g['accounts']) != 1)} "
            f"(build days; with worse fills {usd(round(out['worse']))}). At least one payout in {100 * g['p_paid']:.0f} % of the simulated futures; "
            f"{g['survivors']:.1f} of {len(g['accounts'])} accounts survive on average.")
    lines = [head]
    if out["proven"]:
        lines.append(f"PROVEN on the unseen days: {usd(round(out['unseen']['per_week']))} a week there.")
    elif out["unseen"]:
        lines.append(f"NOT PROVEN: on the unseen days it pays {usd(round(out['unseen']['per_week']))} a week (it must pay, and at least "
                     f"{100 * PY.need('proof', 'keep'):.0f} % of the build days' number).")
    elif out.get("waiting"):
        lines.append("NOT PROVEN yet: " + "; ".join(f"{w['name']}: {w['why']}" for w in out["waiting"]) + ".")
    for s in out["sets"].values():
        who = ", ".join(f"{slot}: {(m or {}).get('name') or 'nobody'}" for slot, m in s["slots"].items())
        size = f"{s['size']} micros each" if s["size"] else "no size"
        rule = ("always trade" if s["gain"] is None and s["loss"] is None else
                "stop for the day " + " or ".join(x for x in (s["gain"] and f"up {usd(round(s['gain'] * s['mll']))}", s["loss"] and f"down {usd(round(s['loss'] * s['mll']))}") if x))
        rot = f"; rotation: a {s['rotation']['lookback']}-day high within {s['rotation']['within']} days" if s.get("rotation") else "; no rotation rule (it did not beat no rule)"
        lines.append(f"{s['account_name']} x{len(s['accounts'])}: {who}; {size}; {rule}{rot}; {usd(round(s['per_week']))} a week.")
    if any(s.get("friendly") for s in out["sets"].values()):
        lines.append("The Apex numbers are the friendly reading: " + SC.FRIENDLY + ".")
    empty = [s for s in out["slots"] if not out["pool"]["by_slot"].get(s["id"])]
    if empty:
        lines.append("No strategy in the pool for: " + ", ".join(s["label"] for s in empty) + ".")
    return "\n".join(lines)


def series(root=None):
    """name -> (its picked box's P&L a day at one micro on every day on file: the build days, then its unseen days when read; the last day)."""
    members, _ = PP.members(root)
    by, cal = {m["name"]: m for m in members}, PP.calendar([m["market"] for m in members] or ["NQ"])

    def one(name: str) -> tuple:
        m = by.get(name)
        if m is None:
            return np.zeros(0), None
        o = m["options"][0]
        net, last = PP.daily(o["x"], np.ones(len(o["x"]["net"]), bool), cal)["net"], int(cal[-1])
        un = PP.unseen(m, o, root)
        if un is not None and len(un[1]):
            net, last = np.concatenate([net, PP.daily(un[0], np.ones(len(un[0]["net"]), bool), un[1])["net"]]), int(un[1][-1])
        return net, dt.date.fromordinal(last).isoformat()
    return one


def idle(root=None, now=None) -> dict:
    """The runner's call while the queue is idle -> {"built": bool, "evening": notice | None}. Nothing is built when nothing changed."""
    now = now or dt.datetime.now(S.ET)
    was, did = show(root), {"built": False, "evening": None}
    members, _ = PP.members(root)
    if was is None or was.get("sig") != _sig(members, PA.sync(root)):
        build(root)
        did["built"] = True
    mark = PA.folder(root) / "evening"
    today = now.date().isoformat()
    if (now.hour, now.minute) >= EVENING and (not mark.exists() or mark.read_text(encoding="utf-8").strip() != today):
        did["evening"] = RO.evening(root)
        mark.write_text(today, encoding="utf-8")
    return did


def requeue(root=None) -> dict:
    """`pipe payout requeue`: every idea that STOPPED before the runner picked a box and that has not read the unseen days goes round again
    (pipe_runner.rerun), so that it is judged by the payout rules -- money on the build days, not eval odds of its own. Only while the
    PAYOUT PIPELINE is the one that is on: under another profile it would stop at the same line again."""
    from . import pipe_runner as PRN
    from . import pipe_switch as SW
    if SW.now(root) != "payout":
        raise J.Refuse("the PAYOUT PIPELINE is not the one that is on: under another pipeline's rules the ideas would stop at the same line again (bp.py pipe mode payout)")
    names = [s["name"] for s in PS.ideas(root) if s.get("status") == "stopped" and not s.get("picked") and 6 not in PS.stages(s["name"], root)]
    for n in names:
        PRN.rerun(n, root)
    return api.result("pipe payout requeue", requeued=names, text=f"{len(names)} stopped idea{'s' * (len(names) != 1)} go round again under the payout rules.")


def command(what: str, root=None) -> dict:
    """`bp.py pipe payout <what>` -> the command's one result object (show | build | tonight)."""
    cmd = f"pipe payout {what}"
    if what == "build":
        out = build(root)
        return api.result(cmd, payout=out, text=out["text"], saved=[str(PA.folder(root) / SET)])
    if what == "tonight":
        got = RO.evening(root)
        now = _read(PA.folder(root) / RO.TONIGHT)
        return api.result(cmd, tonight=now, notice=got, text=(got or {}).get("text") or "Nothing changed: the set that ran yesterday runs tonight.")
    out = show(root)
    scores = [json.loads(x) for x in (PA.folder(root) / SCORES).read_text(encoding="utf-8").splitlines() if x.strip()] if (PA.folder(root) / SCORES).exists() else []
    return api.result(cmd, payout=out, scores=scores[-200:], notices=RO.notices(root), tonight=_read(PA.folder(root) / RO.TONIGHT),
                      text=out["text"] if out else "No set is built yet: bp.py pipe payout build.")
