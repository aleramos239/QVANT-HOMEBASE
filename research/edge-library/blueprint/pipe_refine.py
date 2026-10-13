"""pipe_refine.py -- THE REFINER (the owner, 2026-10-13: "keep refining ideas until it makes something work"). The pipeline screens: an idea
stops at its first failed line. This turns a NEAR MISS into its next version, one change at a time.

    bp.py pipe refine <name>                          the idea's missed rows and the moves it may take (writes nothing)
    bp.py pipe refine <name> --move KIND=VALUE ... --why=TEXT   files ONE child card (a new idea, queued) with that one change

THE MOVES (one a round -- ONE kind, so a result is read against ONE change). Each rides on the open layer's settings of every family
(engine/families/_flex.py): nothing a card could not already say.
    regime      KIND=er|adx|atr_rank|bbw_rank   a non-directional gate: trade only when the regime reads `with` its level
    indicator   KIND=rsi|price_ema|ema_x|macd|zscore|stoch|roc|cci|vwap_dev   a directional gate on the idea's own side
    days        KIND=a day rule of flexind.DAY_RULES (nonews, mon .. fri, fomc ...)
    window      KIND=HH:MM-HH:MM   entries decided inside that clock window only
    sides       KIND=long|short
  --set key=value (repeat) fine-tunes the gate (g_n, g_m, g_s, g_lvl, g_side=with|against); the defaults are textbook ones.

THE RULES (the blueprint's, not new): the parent STOPPED ON A VERDICT before the unseen days (a near miss, pipe_runner.near) -- an idea
that was read on the unseen days is final; the family has at most ROUNDS (5) children in a line; the reason is 8 words or more and written
BEFORE the run; the child runs on the BUILD days only -- the unseen days stay sealed until a child is locked, the one read as always.
The child's card carries `again_of` = the parent and its `ref` = round, move, reason: that is the family's log. The text says how many
variants the family has tried: a family that needed many rounds is a family with many chances at luck (bp.py pipe luck counts them).
Nothing is run here; the runner takes the child as it takes any card.
"""
from __future__ import annotations

import copy
import re

import flexind as FI
import judge as J

from . import api
from . import pipe_card as PC
from . import pipe_runner as PRN
from . import pipe_store as PS

ROUNDS = 5                                  # children in one line (the blueprint's counted rounds)
WORDS = 8                                   # a reason: as a card's why
KINDS = ("regime", "indicator", "days", "window", "sides")
GATE = {                                    # gate kind -> its textbook settings: (g_n, g_m, g_s, g_lvl)
    "er": (10, 26, 9, 0.3), "adx": (14, 26, 9, 20.0), "atr_rank": (20, 26, 9, 0.5), "bbw_rank": (60, 26, 9, 0.5),
    "rsi": (14, 26, 9, 10.0), "price_ema": (20, 26, 9, 0.5), "ema_x": (9, 21, 9, 0.0), "macd": (12, 26, 9, 0.0), "zscore": (20, 26, 9, 1.0),
    "stoch": (14, 26, 9, 30.0), "roc": (10, 26, 9, 0.2), "cci": (20, 26, 9, 100.0), "vwap_dev": (1, 26, 9, 1.0)}
HINT = {                                    # what a missed row points at: the moves worth a look first (a pointer, never an order)
    "P3.11": ("regime", "indicator", "window"), "P3.12": ("days", "regime", "window"), "P3.13": ("regime", "sides"),
    "P1": ("regime", "sides", "days"), "P2": ("regime", "days", "sides")}
CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
SETKEYS = ("g_n", "g_m", "g_s", "g_lvl", "g_side")


def _line(chain: str, name: str, root) -> list:
    """The names of the line from the first card down to `name` (again_of, parent first)."""
    got, seen = [name], {name}
    while True:
        up = PS.card(got[0], root).get("again_of")
        if not up or up in seen:
            return got
        try:
            PS.card(up, root)
        except (OSError, ValueError):
            return got
        got.insert(0, up)
        seen.add(up)


def family(name: str, root=None) -> list:
    """Every idea of the family `name` belongs to: its first card and every card that runs again from one of them."""
    first = _line("", name, root)[0]
    kids = {first}
    grew = True
    allcards = {x["name"]: PS.card(x["name"], root).get("again_of") for x in PS.ideas(root)}
    while grew:
        grew = False
        for n, up in allcards.items():
            if up in kids and n not in kids:
                kids.add(n)
                grew = True
    return sorted(kids)


def _missed_of(name: str, root) -> dict | None:
    """The near-miss row of `name` (pipe_runner.near), or None: it did not stop on a verdict before the unseen days."""
    return next((r for r in PRN.near(root, top=0)["ideas"] if r["name"] == name), None)


def _hints(missed: list) -> list:
    out = []
    for line in missed:
        for key, moves in HINT.items():
            if str(line).startswith(key):
                out += [m for m in moves if m not in out]
    return out or list(KINDS)


def _parse(moves: list, sets: list, side_of_card: str) -> tuple:
    """--move KIND=VALUE (exactly one) and --set k=v -> (kind, {fixed settings} | {"sides": x}, words)."""
    if len(moves) != 1:
        raise J.Refuse("one move a round: --move KIND=VALUE (one kind, so the result reads against one change). Kinds: " + ", ".join(KINDS))
    kind, _, val = moves[0].partition("=")
    kind, val = kind.strip(), val.strip()
    extra = {}
    for kv in sets:
        k, _, v = kv.partition("=")
        k = k.strip()
        if k not in SETKEYS:
            raise J.Refuse(f"--set {k!r}: one of {', '.join(SETKEYS)}")
        try:
            extra[k] = v.strip() if k == "g_side" else float(v) if k == "g_lvl" else int(v)
        except ValueError:
            raise J.Refuse(f"--set {kv!r}: a number (g_side: with or against)") from None
    if extra.get("g_side", "with") not in ("with", "against"):
        raise J.Refuse("g_side: with or against")
    if kind in ("regime", "indicator"):
        pool = FI.KINDS_REGIME if kind == "regime" else FI.KINDS_DIR
        if val not in pool:
            raise J.Refuse(f"{kind}: one of {', '.join(pool)}")
        n, m, s, lvl = GATE[val]
        fixed = {"gate": val, "g_n": n, "g_m": m, "g_s": s, "g_lvl": lvl, "g_side": "with", **extra}
        return kind, fixed, f"gate {val}" + (f" ({', '.join(f'{k} {v}' for k, v in extra.items())})" if extra else "")
    if extra:
        raise J.Refuse("--set fine-tunes a gate (regime or indicator) only")
    if kind == "days":
        if val not in FI.DAY_RULES or val == "all":
            raise J.Refuse("days: one of " + ", ".join(r for r in FI.DAY_RULES if r != "all"))
        return kind, {"days": val}, f"days {val}"
    if kind == "window":
        if not CLOCK.match(val):
            raise J.Refuse("window: HH:MM-HH:MM (the Globex-day clock, ET), e.g. 09:30-11:30")
        a, b = val.split("-")
        return kind, {"w_start": a, "w_end": b}, f"entries {a}-{b}"
    if kind == "sides":
        if val not in ("long", "short") or val == side_of_card:
            raise J.Refuse("sides: long or short, and not the side the card already has")
        return kind, {"sides": val}, f"{val} side only"
    raise J.Refuse(f"move {kind!r}: one of {', '.join(KINDS)}")


def child_name(first: str, n: int) -> str:
    """`<first>_r<n>`; the first card's name is cut so the card's own name stays at most 34 characters (pipe_card.NAME)."""
    suffix = f"_r{n}"
    return first[: 34 - len(suffix)] + suffix


def refine(name, root=None, *, moves=None, sets=None, why=None) -> dict:
    """`pipe refine`: no move = what the idea missed and what it may try; a move = the child card, filed."""
    try:
        parent = PS.card(name, root)
    except (OSError, ValueError):
        return api.refused("pipe refine", f"no idea named {name!r} is on file", name)
    st = PS.state(name, root)
    line = _line("", name, root)
    tried = len(family(name, root))
    near = _missed_of(name, root)
    if st.get("status") in ("awaiting_owner", "approved", "booked") or st.get("stopped_at") == 6 or st.get("status") == "refused":
        return api.refused("pipe refine", f"{name} was read on the unseen days or is the owner's: it is final, nothing is refined from it", name)
    if near is None:
        return api.refused("pipe refine", f"{name} did not stop on a verdict before the unseen days (status {st.get('status')}, stage {st.get('stopped_at')}): "
                           "only a near miss is refined (bp.py pipe near)", name)
    round_no = len(line)                      # the parent is round len(line)-1 + 1: a first card is round 1
    missed = [f"{l}: " + str(near.get("text") or "") if l == near.get("line") else str(l) for l in near["missed"]]
    hints = _hints(near["missed"])
    if not moves:
        text = [f"{name}: stopped at stage {near['stage']} on {len(near['missed'])} row(s): {', '.join(str(x) for x in near['missed'])}.",
                f"worst row: {near.get('text')}",
                f"round {round_no} of {ROUNDS} used; the family has tried {tried} variant{'s' * (tried != 1)}.",
                "moves to look at first: " + ", ".join(hints) + ". All: " + ", ".join(KINDS) + ".",
                "bp.py pipe refine " + name + " --move KIND=VALUE --why='one change and the reason, 8 words or more'"]
        return api.result("pipe refine", name, round=round_no, rounds=ROUNDS, missed=near["missed"], hints=hints, tried=tried, text="\n".join(text))
    if round_no >= ROUNDS:
        return api.refused("pipe refine", f"the family of {line[0]} is at its {ROUNDS} rounds: it stops here (the blueprint's counted rounds). "
                           "Take the next near miss (bp.py pipe near).", name)
    reason = " ".join(str(why or "").split())
    if len(reason.split()) < WORDS:
        return api.refused("pipe refine", f"--why: the reason for this one change, {WORDS} words or more (written before the run)", name)
    kind, change, words = _parse(list(moves), list(sets or []), str(parent.get("sides")))
    child = copy.deepcopy({k: v for k, v in parent.items() if k != "subs"})
    first = line[0]
    n = round_no + 1
    child["name"] = child_name(first, n)
    child["again_of"] = name
    child["ref"] = f"refine round {n} of {first}: {words}. {reason}"[:PC.REF_MAX]
    if "sides" in change:
        child["sides"] = change["sides"]
        child["sides_why"] = f"{change['sides']} side only: {reason}"[:300]
    else:
        for w in child.get("ways") or []:
            w["fixed"] = {**(w.get("fixed") or {}), **change}
    got = PRN.add(child, root)
    if not got.get("ok", True) or got.get("status") == "refused" or "lines" in got and not got.get("state"):
        return {**got, "text": f"the child card {child['name']} was not filed: " + str(got.get("text") or got.get("error") or "")}
    text = [f"{child['name']} filed: round {n} of {ROUNDS} in the line of {first}, one change from {name}: {words}.",
            f"reason: {reason}", f"the family has now tried {tried + 1} variants; it runs on the build days only, the unseen days stay sealed."]
    return api.result("pipe refine", child["name"], parent=name, round=n, rounds=ROUNDS, move=kind, change=change, tried=tried + 1,
                      text="\n".join(text) + "\n" + str(got.get("text") or ""), next="bp.py pipe start runs the queue (a runner that is working takes it by itself).")
