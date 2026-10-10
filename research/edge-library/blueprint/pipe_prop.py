"""pipe_prop.py -- the pipeline's PROP CHECK (pipeline plan A, task 6; spec section 3, stage 5): the two 30-day prop odds of ONE
box and the label they give it. A LABEL, NOT A GATE: nothing here stops an idea.

  odds(x, calendar, account=None, paths=None, seed=None) -> dict
      x         one box's trades, as judge.cellx hands a cell over (the packed arrays: 1 contract after costs)
      calendar  the session days those trades were run on (ISO dates): a day without a trade is a day of $0
      account   a rule file of the app's prop simulator; default = pipeline.json prop.account. An id the app does not have:
                judge.Refuse, naming it
      paths, seed   the Monte Carlo's (tests); default = the app's own (propsim.N_PATHS, propsim.SEED), as propodds.look
      -> {"account": {"id", "name", "confirmed"}, "days": N, "size": micros | None, "payout_size": micros | None,
          "eval": p, "payout": p, "label": "stands alone" | "helper", "need": {"eval", "payout"},
          "table": [{"size", "eval", "payout": p | None}],
          "stress": {"size", "payout_size", "eval", "payout", "table"} (the "live is worse" row), "text": one sentence}
  label(eval_p, payout_p) -> "stands alone" when BOTH are strictly over their bars of pipeline.json, else "helper"

IT IS propodds, WITH ANOTHER DAY COUNT. A sibling of propodds.look that takes the account and cuts the walks at N session days
(N = pipeline.json prop.days). Nothing is re-derived: a size = propodds.ledger (the library's micro cost model, then the
account's soft daily loss limit) · a day = propodds.days (the calendar's session days, each with its worst open loss) · the paths
= propodds.draws · the walks = propodds.eval_walk and funded_walk, so OPEN LOSSES COUNT exactly as they do there.
TWO ROWS (the owner, 2026-10-10: "soften the live-is-worse haircut ... keep it as a stress line, not the main number"):
  THE PLAIN ROW = the build days' own trades. It is THE NUMBER: `eval`, `payout`, `size`, `payout_size`, `table`, the label, the
  pick's order (pipe_stages) and the portfolio's bar all read it.
  THE STRESS ROW = propodds.worse, THE "LIVE IS WORSE" ROW of line 5.2 (win rate -5 points, winners -15 %): `stress`, shown beside it,
  never a gate. For an edge of about $100 a trade it turns the average trade negative: it says how much room an idea has, not
  whether it is any good.
  eval    the share of the paths whose eval walk ends PASS on or before session day N
  payout  the share whose funded walk (a funded account from a flat start) reaches the MAXIMUM payout on or before day N
THE CUT: the paths are propodds' own matrix without a day limit -- draws(pool, paths, horizon(r), seed), the one line 5.5 and
look are read on -- and each walk is handed its first N days. A walk never looks ahead, so a path that passes here passes
there: at one size the number is never above the no-day-limit number, path for path (an eval with its own maximum of days is
cut at the smaller of the two).
THE SIZES (propodds.steps, as propodds.table reads them): the eval at every step up to the account's maximum; the funded
account only at the steps up to the size its scaling plan starts at -- above it a row's payout is None. EACH PHASE IS READ AT
ITS OWN BEST SIZE, as line 5.1 has it and look does: `size` = the step with the highest eval number, `payout_size` = the
funded step with the highest payout number; equal odds = the SMALLER step (the plain highest, not line 5.1's overlap of
intervals: this number is a label). So `eval` and `payout` may be read at two sizes -- the eval and the funded account are
two accounts, each run at its size.
No trade, or no session day: nothing is raised -- size None, both numbers 0, "helper", and a text that says so.
No number is typed here: the account, N and the two bars are pipe_rules.need("prop"). Nothing is run and nothing is written;
homebase/ is only read (propodds.app()). Locked by tests/test_pipe_prop.py.
"""
from __future__ import annotations

import judge as J

from . import lines as L
from . import pipe_rules as PR
from . import propodds as PO

ALONE, HELPER = "stands alone", "helper"


def label(eval_p: float, payout_p: float) -> str:
    """The label of two odds: "stands alone" only when BOTH are strictly over their bars of pipeline.json (prop.eval, prop.payout)."""
    need = PR.need("prop")
    return ALONE if eval_p > need["eval"] and payout_p > need["payout"] else HELPER


def _mic(n: int) -> str:
    return f"{n} micro{'s' * (n != 1)}"


def odds(x: dict, calendar, account=None, paths=None, seed=None) -> dict:
    """The prop check of one box (module docstring): its eval odds and its maximum-payout odds within the days of pipeline.json
    on `account`, each at its best size, on the "live is worse" row, open losses counted -- and the label."""
    need, PS = PR.need("prop"), PO.app()
    rid = need["account"] if account is None else account
    try:
        r = PS.load_rules(rid)
    except ValueError:
        raise J.Refuse(f"account {rid!r}: the app's prop simulator has no such rule file (it has {', '.join(a['id'] for a in PS.list_rules())})") from None
    N, bars = int(need["days"]), {p: need[p] for p, _ in PO.PHASES}
    who = {"id": rid, "name": r.get("name"), "confirmed": r.get("confirmed") is not False}
    head = f"PROP CHECK on {r.get('name')}" + ("" if who["confirmed"] else " · unconfirmed rules")
    cal = [] if calendar is None else [str(d) for d in calendar]
    out = {"account": who, "days": N, "size": None, "payout_size": None, "eval": 0.0, "payout": 0.0, "label": HELPER, "need": bars, "table": [],
           "stress": {"size": None, "payout_size": None, "eval": 0.0, "payout": 0.0, "table": []}}
    if not len(x["net"]) or not cal:
        return {**out, "text": f"{head}: nothing to read, " + ("the box has no trade" if not len(x["net"]) else "no session day was handed over") + f" -- {HELPER.upper()}."}
    (ev, fu), n, sd = PO.steps(r), int(paths or PS.N_PATHS), PS.SEED if seed is None else int(seed)
    de = min(N, int(r.get("max_days") or N))        # an eval with its own maximum of days cannot be passed after them
    rows, srows = [], []
    for size in ev:
        net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
        wnet, wopn = PO.worse(net, traded, opn)     # the stress row: "live is worse"
        idx = PO.draws(len(net), n, max(N, PO.horizon(r)), sd)[:, :N]      # the no-day-limit paths, their first N days
        for dst, (a_, t_, o_) in ((rows, (net, traded, opn)), (srows, (wnet, traded, wopn))):
            P, T, O = a_[idx], t_[idx], o_[idx]
            e = PO.eval_walk(P[:, :de], T[:, :de], O[:, :de], r)
            f = PO.funded_walk(P, O, r) if size in fu else None
            dst.append({"size": size, "eval": int(((e["outcome"] == PO.PASS) & (e["day"] <= N)).sum()) / n,
                        "payout": None if f is None else int(((f["max_payout_at"] > 0) & (f["max_payout_at"] <= N)).sum()) / n})

    def best(tab):                                   # each phase at its own best size; smallest size first: equal odds = the smaller step
        be = max(tab, key=lambda v: v["eval"])
        bp = max((v for v in tab if v["payout"] is not None), key=lambda v: v["payout"], default={"size": None, "payout": 0.0})
        return be, bp
    (be, bp), (se, sp) = best(rows), best(srows)
    lab = label(be["eval"], bp["payout"])
    stress = {"size": se["size"], "payout_size": sp["size"], "eval": se["eval"], "payout": sp["payout"], "table": srows}
    return {**out, "size": be["size"], "payout_size": bp["size"], "eval": be["eval"], "payout": bp["payout"], "label": lab, "table": rows, "stress": stress,
            "text": f"{head}, open losses count: it passes the eval within {N} trading days {PO._pc(be['eval'])} of the time at "
                    f"{_mic(be['size'])} (stands alone needs over {L._pc(bars['eval'])}) and reaches the maximum payout within {N} trading days {PO._pc(bp['payout'])} "
                    + (f"at {_mic(bp['size'])} " if bp["size"] else "") + f"(needs over {L._pc(bars['payout'])}) -- {lab.upper()} (a label, not a gate). "
                    f"Stress, the \"live is worse\" row: eval {PO._pc(se['eval'])}, payout {PO._pc(sp['payout'])}."}
