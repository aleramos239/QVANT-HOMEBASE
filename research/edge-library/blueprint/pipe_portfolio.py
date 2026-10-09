"""pipe_portfolio.py -- STAGE 8, THE PORTFOLIO BUILDER (the design's "Stage 8 - the portfolio"; `bp.py pipe portfolio`). One
strategy alone passes an eval too rarely, so the strategies of THE BOOK are MIXED on one account. For ONE account this module
tries every mix the rules allow and says which is best, and how far that one is from the bar. It RUNS NOTHING of the engine
and opens no tape: it reads what the one read of the unseen days left on file.

  accounts() -> [ids]              the pipeline's own account first, then the accounts of a book card (pipeline.json prop)
  member(card, root) -> strategy   a book card -> {name, family, market, session, bar, box, trades, x, calendar}: the trades
                                   of its LOCKED BOX on the UNSEEN DAYS (propodds.handed + propodds.cell: the read's own store
                                   and the session days it replayed). Refused: a card that does not say where its trades are,
                                   an idea whose read is not on file, a lock on file that is not the card's
  book(root) -> (strategies, unread [{name, why}])     every book card; one that cannot be read is named, never fatal
  odds(cells, calendar, r, paths, seed) -> {size, payout_size, eval, payout, table}     the two odds of ONE mix
  build(account=None, root=None, members=None, paths=None, seed=None) -> the answer for ONE account (below)
  portfolio(root=None, account=None, paths=None, seed=None) -> `bp.py pipe portfolio [--account=ID]` as one result object:
                                   `accounts` = build() of every account of accounts(), or of the one asked for; each is
                                   saved as <pipeline root>/portfolios/<account>.json (the only write; an empty book writes
                                   nothing). An account the app has no rule file for is refused before anything is read

THE RULES (the design's own, fixed) AND HOW EACH IS READ HERE
  Only book strategies.            The members are pipe_store.book(root)'s cards: the command can be handed nothing else.
  No two from the same family on the same market.
                                   Two cards with the same `family` AND the same `market` are never in one mix: such a mix
                                   is not tried (`twins` names the pairs). The same family on another market is another idea.
  Each added strategy must raise the mix's eval odds, or it is left out.
                                   READ AS: A MIX IS ALLOWED ONLY IF TAKING ANY ONE MEMBER AWAY LOWERS ITS EVAL ODDS. For
                                   every member the mix is read again without it -- the rest, on THE SAME session days and
                                   the same drawn paths, at its own best size (fewer members may each trade more) -- and the
                                   whole mix must read STRICTLY higher than each of those (`without`). A member whose removal
                                   leaves the odds equal or higher is in `drags`, and the mix says allowed False: it is
                                   never the best mix while an allowed one exists. One strategy alone has nobody to take
                                   away and is always allowed. (An account without an eval: the payout odds, see below.)
  The account's own rules must hold for the mix.
        fast trades                at most pipeline.json portfolio.fast_share of the mix's profit from trades held
                                   box.fast_seconds or less (every account)
        the biggest day            where the account's rule file has a `consistency` share (LucidFlex): the mix's biggest
                                   day is at most that share of its profit. A rule file that says null asks nothing (holds
                                   None); one without the key is said in `notes`, and nothing is guessed
                                   Both are read off the mix's own ledger at its eval size (propodds.together: the members'
                                   trades in one ledger, after the account's daily limit; without a daily limit the shares
                                   are the same at any size). A mix with no profit has no share of it: the share is None and
                                   the rule does not hold.
        one side only              on an account of pipeline.json portfolio.one_side (Apex: the design's section 13; its
                                   rule file does not say so, and `notes` says that) a strategy whose ENTRY RULE RESTS
                                   ORDERS ON BOTH SIDES cannot go in any mix: it is in `left_out` with the reason. "Rests
                                   orders on both sides" is the block list's word for a family (the engine's registry:
                                   families.blocks.BASES, what blocklist.families calls `bracket` and the lock's worse fills
                                   read). The family is asked, not the card's side: a one-sided card of such a family is
                                   left out too. A family the block list does not know is left out there as well, and says so.
  The bar.                         pipeline.json portfolio: the eval passed within eval.days at eval.odds OR MORE, and the
                                   maximum payout reached within payout.days at payout.odds or more. Both day counts are
                                   session days of the walk (the design's "5 weekdays" and "14 trading days").
        an account without an eval  pipeline.json portfolio.funded_only (Apex, section 13: "funded accounts only ... judged
                                   on the payout odds alone"): `judged` is the payout alone. The eval odds of the rule file
                                   on file are shown and ask nothing, and THE NUMBER A MEMBER MUST RAISE IS THE PAYOUT ODDS
                                   (the design names the eval odds and such an account has none: this module's reading).
  Ranking: fewer days and a higher chance are better.
                                   The odds ARE the chance inside the bar's own days, so a mix that gets there in fewer
                                   days has the higher number. The order: (1) the mixes that are allowed and hold the
                                   account's rules, before the others; (2) the larger `margin` = the smallest of (odds / its
                                   bar) over the judged numbers: the nearest the bar on its WEAKER number (propodds' own
                                   measure; 1 or more = at the bar); (3) the higher eval odds, then the higher payout odds
                                   (the judged ones); (4) fewer members; (5) the one tried first (the book's order, small
                                   mixes first).
  The best mix and how far it is.  `best` = the first of that order, shown whether it meets the bar or not; `gap` = what is
                                   missing: the odds under the bar in each judged number (0 = at it; None = not judged), the
                                   account rules that do not hold, the members that drag. `meets` = allowed, the rules hold,
                                   every judged number at its bar.

THE ODDS OF A MIX are pipe_prop.odds' reading of one box, for several: every member at the SAME size step in micros
(propodds.together; k members at a step each = k x the step inside the account's maximum, as propodds.table has it), on the
session days the members SHARE, the day pool with each day's worst open loss (propodds.days: OPEN LOSSES COUNT), THE "LIVE IS
WORSE" ROW (propodds.worse), the app's paths and seed without a day limit (propodds.draws) cut at the bar's days, the walks
propodds.eval_walk and funded_walk. Each phase at its own best size: `size` = the step with the highest eval odds,
`payout_size` = the funded step with the highest payout odds; equal odds = the smaller step. With the prop check's day count
one strategy reads here exactly as pipe_prop.odds reads it (locked by the test).

build() -> {"account": {id, name, confirmed}, "need": {eval: {days, odds}, payout: {days, odds}}, "judged": ["eval", "payout"] | ["payout"],
            "rules": {fast: {seconds, share}, biggest_day: share | None, one_side: bool, funded_only: bool},
            "notes": [what the account's rule file does not say],
            "members": [{name, family, market, session, bar, box, trades, both_sides}] (the ones that may go in a mix here),
            "left_out": [{name, why}], "unread": [{name, why}], "twins": [{a, b, family, market}],
            "skipped": [{members, why}] (a mix with nothing to read: no shared session day, no trade on them, no size),
            "mixes": [EVERY mix tried, best first: {members, days, size, payout_size, eval, payout, table [{size, eval, payout}],
                      rules {fast: {share, holds}, biggest_day: {share, holds}}, without {member: the odds without it},
                      drags, allowed, rules_hold, margin, meets}],
            "best": the first mix | None, "gap": {eval, payout, rules, drags} | None, "meets": bool, "paths", "seed", "text"}
`members=` hands the strategies over instead of the book (the tests' hand-made trades; member()'s shape).
NOT BUILT (the design's section 13 says more of Apex than its rule file on file does): the Apex mix's biggest day at 30 % of
the profit, a stop at most 5 times the target, the drawdown trailing the live peak. They wait for the Apex rule file the
design asks for; until then Apex is read by the file on file and says "unconfirmed rules".
No number is typed here: the bar, the days, the fast share and the two account lists are pipe_rules.need(...), the rest is
the account's rule file. Every subset of the book is tried (a book is a handful of strategies).
Locked by tests/test_pipe_portfolio.py.
"""
from __future__ import annotations

import math
from itertools import combinations

import judge as J

from . import api
from . import lines as L
from . import pipe_rules as PR
from . import pipe_store as PS
from . import propodds as PO
from . import runner as RUN

EVAL, PAYOUT = (p for p, _ in PO.PHASES)            # the two numbers of a mix, by propodds' own names
RULES = {"fast": "the fast-trades rule", "biggest_day": "the biggest-day rule"}      # the account rules a MIX is held to (one side only is a member's)
MS = 1000                                           # milliseconds a second: a unit, not a rule


def accounts() -> list:
    """The accounts a book is mixed for: the pipeline's own first, then pipeline.json prop.book_accounts (each once)."""
    return list(dict.fromkeys([PR.need("prop", "account"), *PR.need("prop", "book_accounts")]))


def both_sides(family):
    """Does this entry rule rest orders on both sides? The block list's own word (the engine's registry, as the lock reads it for
    the worse fills). None = a family the block list does not know."""
    try:
        return bool(RUN._blocks().BASES[family][2])
    except (KeyError, TypeError):
        return None


def _account(account) -> tuple:
    """(id, the rule file, {id, name, confirmed}) of an account; None = the pipeline's own. An id the app does not have: refused by name."""
    A, rid = PO.app(), PR.need("prop", "account") if account is None else account
    try:
        r = A.load_rules(rid)
    except ValueError:
        raise J.Refuse(f"account {rid!r}: the app's prop simulator has no such rule file (it has {', '.join(a['id'] for a in A.list_rules())})") from None
    return rid, r, {"id": rid, "name": r.get("name"), "confirmed": r.get("confirmed") is not False}


def rules(rid: str, r: dict) -> dict:
    """WHICH RULES A MIX IS HELD TO ON AN ACCOUNT, and where each comes from: the fast trades (pipeline.json, every account), the
    biggest day (the rule file's `consistency`; None = it has none), one side only and no eval to pass (pipeline.json
    portfolio.one_side and funded_only: the design's word, the rule files do not carry it)."""
    need = PR.need("portfolio")
    return {"fast": {"seconds": PR.need("box", "fast_seconds"), "share": need["fast_share"]}, "biggest_day": r.get("consistency"),
            "one_side": rid in need["one_side"], "funded_only": rid in need["funded_only"]}


def _judged(rl: dict) -> list:
    """The numbers a mix is judged on, the one a member must raise first: the eval odds and the payout odds -- the payout odds
    alone on an account that has no eval to pass."""
    return [PAYOUT] if rl["funded_only"] else [EVAL, PAYOUT]


def _notes(r: dict, rl: dict) -> list:
    """What the account's rule file does not say, in plain words (nothing is guessed in its place)."""
    out, where = [], "the design's section 13, pipeline.json portfolio"
    if r.get("confirmed") is False:
        out.append("its rule file is not confirmed by the owner: the odds are of the rules on file")
    if rl["funded_only"]:
        out.append(f"this account has no eval to pass ({where}.funded_only): the mix is judged on the payout odds alone, and a member must raise the payout "
                   "odds; the account's own rule file still has an eval, and its odds are shown and ask nothing")
    if rl["one_side"]:
        out.append(f"orders may rest on one side only here ({where}.one_side); the account's own rule file does not say so")
    if "consistency" not in r:
        out.append("the account's rule file does not say whether a biggest-day rule applies (no `consistency`): none was applied")
    return out


# ================================================================ the book's strategies

def member(card: dict, root=None) -> dict:
    """A BOOK CARD -> the strategy as the builder reads it: the trades of its locked box on the unseen days, and the session days
    its read replayed (module docstring). Refused: what propodds.handed and cell refuse, a card that does not say where its
    trades are, a lock on file that is not the card's."""
    try:
        name, sub, fam, mkt, box, lock = card["name"], card["sub"], card["family"], card["market"], card["rule"]["default"], card["rule"]["lock"]
    except (KeyError, TypeError):
        raise J.Refuse("its book card does not say its sub (the toolkit idea), its family, its market and its rule (default, lock): it is not read") from None
    h = PO.handed(sub, PS.ideas_root(root))
    if h["lock"] != lock:
        raise J.Refuse(f"the lock of {sub} on file ({h['lock']}) is not the one of the book card ({lock}): the trades on file are not the book strategy's")
    x = PO.cell(h, box)
    return {"name": name, "family": fam, "market": mkt, "session": card.get("session"), "bar": card.get("bar"), "box": box, "trades": int(len(x["net"])), "x": x,
            "calendar": list(h["calendar"])}


def book(root=None) -> tuple:
    """Every book card as a strategy -> (the ones read, [{name, why}] the ones that could not be: named, never fatal)."""
    got, bad = [], []
    for card in PS.book(root):
        try:
            got.append(member(card, root))
        except api.REFUSALS as e:
            bad.append({"name": card.get("name"), "why": str(e)})
    return got, bad


# ================================================================ one mix: its odds, and the account's rules on it

def _steps(r: dict, k: int) -> tuple:
    """The size steps k members may EACH trade at (propodds.table's reading): k x the step inside the account's maximum ->
    (the eval's, the funded account's)."""
    ev, fu = PO.steps(r)
    return [s for s in ev if s * k <= max(ev)], [s for s in fu if s * k <= max(fu)]


def odds(cells: list, calendar, r: dict, paths=None, seed=None) -> dict:
    """THE TWO ODDS OF ONE MIX (module docstring): its members' cells at the same size step each, on `calendar`, on the "live is
    worse" row, open losses counted -- the eval passed within the bar's eval days, the maximum payout reached within its payout
    days, each at its best size. Nothing to read (no size the account may hold, no trade on those days): size None, both 0."""
    need, A, cal = PR.need("portfolio"), PO.app(), [str(d) for d in calendar]
    (ev, fu), n, sd = _steps(r, len(cells)), int(paths or A.N_PATHS), A.SEED if seed is None else int(seed)
    ne, np_ = int(need[EVAL]["days"]), int(need[PAYOUT]["days"])
    de, far = min(ne, int(r.get("max_days") or ne)), max(ne, np_)      # an eval with its own maximum of days cannot be passed after them
    if not (cal and ev and PO.together(cells, ev[0], r, cal)):
        return {"size": None, "payout_size": None, EVAL: 0.0, PAYOUT: 0.0, "table": []}
    rows = []
    for size in ev:
        net, traded, opn, _ = PO.days(PO.together(cells, size, r, cal), r, cal)
        wnet, wopn = PO.worse(net, traded, opn)     # the "live is worse" row
        idx = PO.draws(len(net), n, max(far, PO.horizon(r)), sd)[:, :far]       # the no-day-limit paths, their first days
        p, t, o = wnet[idx], traded[idx], wopn[idx]
        e = PO.eval_walk(p[:, :de], t[:, :de], o[:, :de], r)
        f = PO.funded_walk(p[:, :np_], o[:, :np_], r) if size in fu else None
        rows.append({"size": size, EVAL: int(((e["outcome"] == PO.PASS) & (e["day"] <= ne)).sum()) / n,
                     PAYOUT: None if f is None else int(((f["max_payout_at"] > 0) & (f["max_payout_at"] <= np_)).sum()) / n})
    be = max(rows, key=lambda v: v[EVAL])           # smallest size first: equal odds = the smaller step
    bp = max((v for v in rows if v[PAYOUT] is not None), key=lambda v: v[PAYOUT], default={"size": None, PAYOUT: 0.0})
    return {"size": be["size"], "payout_size": bp["size"], EVAL: be[EVAL], PAYOUT: bp[PAYOUT], "table": rows}


def held(cells: list, size: int, r: dict, calendar, rl: dict) -> dict:
    """THE ACCOUNT'S RULES ON ONE MIX, off its own ledger at `size` micros each -> {fast: {share, holds}, biggest_day: {share,
    holds}}. share = of the mix's profit (None when it makes none: the rule then does not hold); holds None = the account has
    no such rule."""
    rows = PO.together(cells, size, r, list(calendar))
    total, day = math.fsum(t["net"] for t in rows), PO.days(rows, r, list(calendar))[0]
    share = (lambda v: float(v) / total) if L._profitable(total) else (lambda v: None)
    fast = share(math.fsum(t["net"] for t in rows if t["exit_ms"] - t["entry_ms"] <= rl["fast"]["seconds"] * MS))
    big = share(day.max()) if len(day) else None
    return {"fast": {"share": fast, "holds": fast is not None and fast <= rl["fast"]["share"]},
            "biggest_day": {"share": big, "holds": None if rl["biggest_day"] is None else big is not None and big <= rl["biggest_day"]}}


def _mix(names: tuple, by: dict, r: dict, rl: dict, need: dict, read) -> dict:
    """ONE MIX, read (module docstring) -- or {members, why} when there is nothing to read of it."""
    cal, judged = tuple(sorted(set.intersection(*[set(by[k]["calendar"]) for k in names]))), _judged(rl)
    got = read(names, cal)
    if got["size"] is None:
        return {"members": list(names), "why": "they share no session day of their reads" if not cal else
                f"{len(names)} members at the smallest size step are more than the account may hold" if not _steps(r, len(names))[0] else
                f"no trade on the {len(cal)} session days they share"}
    without = {m: read(tuple(x for x in names if x != m), cal)[judged[0]] for m in names} if len(names) > 1 else {}
    drags = [m for m in without if not got[judged[0]] > without[m]]    # taking it away does not lower the odds
    rules_ = held([by[k]["x"] for k in names], got["size"], r, cal, rl)
    ok = all(v["holds"] is not False for v in rules_.values())
    return {"members": list(names), "days": len(cal), **got, "rules": rules_, "without": without, "drags": drags, "allowed": not drags, "rules_hold": ok,
            "margin": min(got[p] / need[p]["odds"] for p in judged), "meets": bool(not drags and ok and all(got[p] >= need[p]["odds"] for p in judged))}


def _order(m: dict, judged: list) -> tuple:
    """The rank of a mix, the best first (module docstring): in order before not, then nearest the bar on its weaker number."""
    return (not (m["allowed"] and m["rules_hold"]), -m["margin"], *[-m[p] for p in judged], len(m["members"]))


def gap(m: dict, need: dict, judged: list) -> dict:
    """HOW FAR A MIX IS FROM THE BAR: the odds missing in each judged number (0 = at the bar; None = not judged on this account),
    the account rules that do not hold, the members that do not raise its odds."""
    return {**{p: max(0.0, need[p]["odds"] - m[p]) if p in judged else None for p in (EVAL, PAYOUT)},
            "rules": [k for k in RULES if m["rules"][k]["holds"] is False], "drags": list(m["drags"])}


# ================================================================ one account

def _barred(m: dict, rl: dict):
    """Why a strategy cannot go in ANY mix on this account, or None: the one-side rule, where the account has it."""
    if not rl["one_side"]:
        return None
    two = both_sides(m["family"])
    if two is None:
        return f"the block list does not know its entry rule ({m['family']}): it cannot be shown to rest orders on one side only, as this account asks"
    return f"its entry rule ({m['family']}) rests orders on both sides (the block list), and on this account orders may rest on one side only" if two else None


def build(account=None, root=None, members=None, paths=None, seed=None) -> dict:
    """THE BEST MIX OF THE BOOK FOR ONE ACCOUNT (module docstring): every mix the rules allow is tried, ranked, and the first is
    shown with its distance from the bar. Runs nothing, writes nothing. members = the strategies, instead of the book's."""
    A, (rid, r, who) = PO.app(), _account(account)
    need, rl = {p: PR.need("portfolio", p) for p in (EVAL, PAYOUT)}, rules(rid, r)
    judged = _judged(rl)
    mem, unread = book(root) if members is None else (list(members), [])
    out_ = {m["name"]: _barred(m, rl) for m in mem}
    left, by = [{"name": k, "why": why} for k, why in out_.items() if why], {m["name"]: m for m in mem if not out_[m["name"]]}
    twins = [{"a": a, "b": b, "family": by[a]["family"], "market": by[a]["market"]} for a, b in combinations(by, 2)
             if (by[a]["family"], by[a]["market"]) == (by[b]["family"], by[b]["market"])]
    apart, memo = {frozenset((t["a"], t["b"])) for t in twins}, {}

    def read(names: tuple, cal: tuple) -> dict:
        """The odds of these members on these days: read once, whichever mix asks."""
        if (names, cal) not in memo:
            memo[names, cal] = odds([by[k]["x"] for k in names], cal, r, paths, seed)
        return memo[names, cal]

    tried = [_mix(names, by, r, rl, need, read) for k in range(len(by)) for names in combinations(by, k + 1)      # every subset, the small ones first
             if not any(frozenset(p) in apart for p in combinations(names, 2))]
    mixes = sorted((m for m in tried if "why" not in m), key=lambda m: _order(m, judged))
    best = mixes[0] if mixes else None
    out = {"account": who, "need": need, "judged": judged, "rules": rl, "notes": _notes(r, rl),
           "members": [{**{k: m[k] for k in ("name", "family", "market", "session", "bar", "box", "trades")}, "both_sides": both_sides(m["family"])} for m in by.values()],
           "left_out": left, "unread": unread, "twins": twins, "skipped": [m for m in tried if "why" in m], "mixes": mixes, "best": best,
           "gap": gap(best, need, judged) if best else None, "meets": bool(best and best["meets"]), "paths": int(paths or A.N_PATHS),
           "seed": A.SEED if seed is None else int(seed)}
    return {**out, "text": "\n".join(said(out))}


# ================================================================ in plain words

def _mic(n: int) -> str:
    return f"{n} micro{'s' * (n != 1)}"


def _pts(v: float) -> str:
    return f"{100 * v:.1f} points"


def _held_words(b: dict, rl: dict) -> str:
    """The account's rules on the best mix, one sentence."""
    word = {True: "holds", False: "does NOT hold"}
    f, d = b["rules"]["fast"], b["rules"]["biggest_day"]
    fast = (f"trades held {rl['fast']['seconds']} s or less make {PO._pc(f['share'])} of the profit" if f["share"] is not None else
            "there is no profit to take the fast trades' share of") + f" (at most {L._pc(rl['fast']['share'])}): {word[f['holds']]}"
    if rl["biggest_day"] is None:
        return f"{fast}; no biggest-day rule on this account"
    return fast + "; " + (f"the biggest day is {PO._pc(d['share'])} of the profit" if d["share"] is not None else "there is no profit to take the biggest day's share of") \
        + f" (at most {L._pc(rl['biggest_day'])}): {word[d['holds']]}"


def _tail(a: dict) -> list:
    """What was tried, what was kept apart or left out and why, and what the rule file does not say."""
    n, k = len(a["mixes"]), len(a["members"])
    out = [f"  tried: {n} mix{'es' * (n != 1)} of {k} strateg{'y' if k == 1 else 'ies'}"
           + ("; never together (the same family on the same market): " + ", ".join(f"{t['a']} and {t['b']} ({t['family']} on {t['market']})" for t in a["twins"]) if a["twins"] else "")
           + ("; nothing to read of: " + ", ".join(f"{' + '.join(s['members'])} ({s['why']})" for s in a["skipped"]) if a["skipped"] else "")]
    out += [f"  left out on this account: {x['name']} -- {x['why']}" for x in a["left_out"]]
    out += [f"  not read: {x['name']} -- {x['why']}" for x in a["unread"]]
    return out + [f"  note: {x}" for x in a["notes"]]


def said(a: dict) -> list:
    """One account's answer for a person: the best mix, its odds against the bar, the account's rules on it, what is missing."""
    who, need, rl, b, g, judged = a["account"], a["need"], a["rules"], a["best"], a["gap"], a["judged"]
    head = f"{who['name']} [{who['id']}]" + ("" if who["confirmed"] else " · unconfirmed rules")
    if b is None:
        some = a["members"] or a["left_out"] or a["unread"]
        why = ("the book is empty: there is no strategy to mix" if not some else
               "no strategy of the book can go in a mix on this account" if not a["members"] else "no mix of the book's strategies could be read")
        return [f"{head}: {why}.", *(_tail(a) if some else [])]
    many = len(b["members"]) > 1
    names, each = " + ".join(b["members"]) if many else f"{b['members'][0]} alone", " each" * many
    size = f"{_mic(b['size'])}{each} for the eval, " + (f"{_mic(b['payout_size'])}{each} on the funded account" if b["payout_size"] else "no size the funded account may trade")
    does = {EVAL: "it passes the eval", PAYOUT: "it reaches the maximum payout"}
    short = lambda p: "not judged: this account has no eval to pass" if g[p] is None else f"{_pts(g[p])} short" if g[p] > 0 else "at the bar"  # noqa: E731
    miss = [f"{_pts(g[p])} of {p} odds" for p in judged if g[p] > 0] + [RULES[k] for k in g["rules"]] \
        + ([f"{', '.join(g['drags'])} {'does' if len(g['drags']) == 1 else 'do'} not raise the mix's {judged[0]} odds"] if g["drags"] else [])
    return [f"{head}: the best mix found {'MEETS THE BAR' if b['meets'] else 'does not meet the bar'}. It is {names} ({size}; read on {b['days']} session days"
            + (" they share" * many) + ").",
            *[f"  {p}: {does[p]} within {need[p]['days']} trading days {PO._pc(b[p])} of the time (the bar: {L._pc(need[p]['odds'])} or more) -- {short(p)}" for p in (EVAL, PAYOUT)],
            f"  the account's rules: {_held_words(b, rl)}",
            *([f"  each member must raise the {judged[0]} odds: without {', without '.join(f'{m} {PO._pc(p)}' for m, p in b['without'].items())}; with all {PO._pc(b[judged[0]])}"]
              if many else []),
            f"  missing: {'; '.join(miss) if miss else 'nothing'}", *_tail(a)]


# ================================================================ the command

def _table(got: list) -> list:
    """THE ANSWER FIRST: one row an account -- its best mix, the two odds against their bars, and whether it is at the bar."""
    def odds_(a: dict, p: str) -> str:
        return "-" if a["best"] is None else "not judged" if p not in a["judged"] else f"{PO._pc(a['best'][p])} of {L._pc(a['need'][p]['odds'])}"
    need = got[0]["need"]
    rows = [("account", "best mix", f"eval in {need[EVAL]['days']} days", f"max payout in {need[PAYOUT]['days']} days", "at the bar"),
            *[(a["account"]["name"], "none" if a["best"] is None else " + ".join(a["best"]["members"]), odds_(a, EVAL), odds_(a, PAYOUT), "YES" if a["meets"] else "no") for a in got]]
    wide = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    return ["  ".join(str(c).ljust(w) for c, w in zip(r, wide)).rstrip() for r in rows]


def portfolio(root=None, account=None, paths=None, seed=None) -> dict:
    """`bp.py pipe portfolio [--account=ID]`: the best mix of the book for every account of accounts(), or for the one asked for
    (module docstring) -> ONE result object. Each account's answer is saved as <pipeline root>/portfolios/<account>.json; an
    empty book saves nothing. Refused, with nothing read or written: an account the app has no rule file for."""
    ids = [account] if account else accounts()
    for rid in ids:
        _account(rid)
    names = [c.get("name") for c in PS.book(root)]
    got = [build(rid, root, paths=paths, seed=seed) for rid in ids]
    saved = [str(PS.write_portfolio(a["account"]["id"], a, root)) for a in got] if names else []
    need, k = got[0]["need"], len(names)
    head = (f"THE PORTFOLIO (stage 8): {k} strateg{'y' if k == 1 else 'ies'} in the book" + (f" ({', '.join(str(x) for x in names)})" if names else "")
            + f". A mix must pass the eval within {need[EVAL]['days']} trading days {L._pc(need[EVAL]['odds'])} of the time or more AND reach the maximum payout "
            f"within {need[PAYOUT]['days']} trading days {L._pc(need[PAYOUT]['odds'])} of the time or more. Read on each strategy's unseen-day trades (its locked box), "
            "every member at the same size, on the \"live is worse\" row; open losses count. Nothing was run.")
    return api.result("pipe portfolio", book=names, accounts=got, saved=saved, text="\n".join([head, *_table(got), *[a["text"] for a in got]]))
