"""pipe_gates.py -- the pipeline's gates (pipeline plan A, task 4; spec section 3, stages 1, 3 and 4). PURE FUNCTIONS on the
toolkit's TABLE DATA (lines.py: `net`, `n` = variants x days, `root`; for the sides `long`, `short`, `n_long`, `n_short`,
`sides`): no store, no engine, no file but the rules. A gate is a sibling of a blueprint line with another number, so it reads
the SAME raw numbers lines.py reads and returns the same rows (lines._row: line, passed, number, need, text).
A "box" = one variant of the table (a stop/target box at one setting value); "profitable" = its build net above $0.

  numbers(t)                      {"share", "avg_trade", "trades", "avg_variant", "long", "short"}: the share of boxes
                                  profitable (2.1's number) · net of all boxes / their trades (2.2's; None = no trade) · the
                                  trades a box, mean over the boxes (2.4's) · the net of the average box · the net of each side
                                  (2.6's; None = no trade on it, or a table without its sides)
  raw(t)                          STAGE 1 -> {"result": "strict" | "low" | "fail", "avg_trade", "lines": [P1.1 share, P1.2
                                  average trade, P1.3 trades a box], "text"}. Each row is held against BOTH bars: `need` =
                                  {"strict", "low"}, `meets` = {"strict": bool, "low": bool}, `bar` = "strict" when it meets the
                                  strict number, else "low", else None; `passed` is False only when it meets NEITHER; the text
                                  says the bar where a line says PASS: "P1.2 LOW average trade $41 (strict needs $70, low needs $35)"
                                    strict = all three strict numbers · else low = all three low numbers · else fail
                                  THE LOW BAR ASKS MORE TRADES (300) THAN THE STRICT ONE (200): a table can be strict and not
                                  low (strict wins), and a table can fail with no row failed (the low share with the strict
                                  count of trades) -- `text` names the rows each bar is missed by
  rank(results)                   which heat map moves on, of a list of raw() results: its index -- a strict pass before a low
                                  pass, then the bigger average trade, a tie = the first; None = every one failed
  indicator(tf, traw, others)     STAGE 3, one indicator alone: `tf` the table with it, `traw` the raw table, `others` = the net
                                  of the average box of each other-market table -> the six rows, in the spec's order:
                                    P3.1 over 60 % of boxes profitable      P3.2 average trade at the FULL floor
                                    P3.3 200+ trades a box                  P3.4 long and short each make money = LINE 2.6'S
                                    READING (lines.sides) under this number: a one-sided card is judged on its side, and a
                                    trade on the other side is not the card's rule
                                    P3.5 it beats the raw table on BOTH the average trade and the share of boxes, each strictly
                                    P3.6 at least half of the other-market tables are profitable; no other market -> passed None
  strict_extra(t, others)         rows P3.4 and P3.6 alone: what a strict pass of stage 1 must also meet before the proof
  reshuffle(t, rng=None)          STAGE 4 -> row P4.1: line 2.8's own computation (mc.reshuffle, then lines._heat and
                                  lines._floor in every run -- the strict share and the full floor), the share of the runs in
                                  which both hold, 75 % or more. rng None = the fixed seed of montecarlo.json
  random(p_beat, tries)           STAGE 4 -> row P4.2: `p_beat` = the share of the random heat maps the table beats, ABOVE
                                  (strict) the bar of its `tries`-th try, 100 - 5 / tries % (pipe_rules.random_bar)

VARIANT MODE (pipeline.json "mode": "variant"; the owner, 2026-10-08: "i dont think we need the entire heatmap to reach all the requirements,
some should just be for the individual strategy that will pass"). The map gets a LOOSE check and the hard rules are read on ONE box:
  variant_map(t)                  STAGE 1 -> {"result": "pass" | "fail", "avg_trade" (the whole map's, for the tables list), "qualifying": the
                                  boxes at the floor with enough trades, "cells": their ids in table order, "lines": [P1.1 over `map_share`
                                  of the boxes profitable, P1.2 at least `region_boxes` boxes with an average trade at the floor and
                                  `region_trades` trades], "text"}
  rank(results)                   (above) a variant_map result is ranked by the number of qualifying boxes, then the bigger average trade
  variant_rows(b, others)         STAGE 3 on the picked box `b` = a one-box table (net and n of shape 1 x days, the box's `long` / `short` /
                                  `n_long` / `n_short`, the card's `sides`): P3.2 average trade at the floor, P3.3 `region_trades` trades,
                                  P3.4 each side makes money (line 2.6's reading of the one box), P3.6 the other markets (shown, never False)
  reshuffle_box(b, rng=None)      STAGE 4 -> row P4.1 for the one box: its average trade is at the floor in `proof.reshuffle` of the
                                  reshuffled runs (the same runs as line 2.8's)
  random(p_beat, tries, what)     (above) `what` names the random tables the share was read against
THE COMPARISONS: a share of boxes is "over" (strict) · an average trade "at or above" · trades "or more" · an indicator "higher"
than the raw table (strict) · the other markets "at least" · the reshuffled runs "or more" · the random bar "above" (strict).
EVERY NUMBER IS READ: pipe_rules.need / floor / random_bar (templates/pipeline.json) and, where a gate IS a line of the law
(2.6 in P3.4, 2.1 and 2.2 in P4.1, "profitable"), rules.json through lines.py. None is typed here.
A STRICT PASS MEETS THE LAW: the same numbers under the same comparisons as lines 2.1, 2.2 and 2.4 (an average trade at a
floor above $0 makes the average box profitable, the other half of 2.1), so the toolkit's own build reads no line harder.
numpy + the package. Locked by tests/test_pipe_gates.py.
"""
from __future__ import annotations

import numpy as np

from . import lines as L
from . import mc as MC
from . import pipe_rules as PR
from . import rules as R

BARS = ("strict", "low")                            # the two bars of the raw heat map, the better one first


def _fig(v, held=(), unit: str = "") -> str:
    """A figure in whole units ($41, 310); with cents when a figure it is `held` against would read the same and the two
    are not one whole number -- so a need with cents is printed with them: _fig(need, (need,), "$")."""
    cents = any(round(v) == round(h) and not v == h == round(h) for h in held)
    return ("-" if v < 0 else "") + unit + (f"{abs(v):,.2f}" if cents else f"{abs(v):,.0f}")


def _pct(v) -> str:
    """A share as a percent with up to four decimals: the bar of one try is told from the bar of the next."""
    return f"{100 * v:.4f}".rstrip("0").rstrip(".") + " %"


def _boxes(t: dict) -> tuple:
    """(the boxes that are profitable, the boxes)."""
    v = np.asarray(t["net"], np.float64).sum(1)
    return int(L._profitable(v).sum()), len(v)


def numbers(t: dict) -> dict:
    """The raw numbers of a table, each as its blueprint line reads it (module docstring)."""
    net, n = np.asarray(t["net"], np.float64), np.asarray(t["n"], np.float64)
    v, k, some = net.sum(1), float(n.sum()), bool(net.shape[0])
    return {"share": float(L._profitable(v).mean()) if some else 0.0, "avg_trade": float(v.sum() / k) if k else None,
            "trades": float(n.sum(1).mean()) if some else 0.0, "avg_variant": float(v.mean()) if some else 0.0,
            **{s: float(t[s]) if t.get(f"n_{s}") else None for s in ("long", "short")}}


# ================================================================ stage 1: the raw heat map

def _two(line: str, number, need: dict, met, words: str, said, first: str = "", **more) -> dict:
    """A row of the raw heat map: `number` held against BOTH bars with `met(number, need)`; `said(need)` = a need in words,
    `first` = what the bracket says before the needs."""
    meets = {b: bool(met(number, need[b])) for b in BARS}
    bar = next((b for b in BARS if meets[b]), None)
    words = f"{words} ({first}{', '.join(f'{b} needs {said(need[b])}' for b in BARS)})"
    return {**L._row(line, bar is not None, number, need, words, bar=bar, meets=meets, **more), "text": f"{line} {(bar or 'fail').upper()} {words}"}


def raw(t: dict) -> dict:
    """Stage 1: the raw heat map against the strict bar and the low one -> {"result", "avg_trade", "lines", "text"}."""
    x, bar = numbers(t), {b: PR.need("raw", b) for b in BARS}
    (k, m), at = _boxes(t), x["avg_trade"]
    floor = {b: PR.floor(t["root"], bar[b]["floor_part"]) for b in BARS}
    count = {b: bar[b]["trades"] for b in BARS}
    rows = [_two("P1.1", x["share"], {b: bar[b]["share"] for b in BARS}, lambda v, n: v > n,
                 f"{L._pc(x['share'])} of boxes profitable", lambda n: f"over {L._pc(n)}", f"{k} of {m}; ", profitable=k, variants=m),
            _two("P1.2", at, floor, lambda v, n: v is not None and v >= n,
                 "no trade" if at is None else f"average trade {_fig(at, floor.values(), '$')}", lambda n: _fig(n, (n,), "$")),
            _two("P1.3", x["trades"], count, lambda v, n: v >= n, f"{_fig(x['trades'], count.values())} trades a box", lambda n: _fig(n, (n,)))]
    missed = {b: ", ".join(r["line"] for r in rows if not r["meets"][b]) for b in BARS}
    result = next((b for b in BARS if not missed[b]), "fail")
    text = (f"fail: the strict bar is missed by {missed['strict']}; the low bar by {missed['low']}" if result == "fail" else
            f"{result} pass: the three numbers meet the {result} bar" + (f"; the strict bar is missed by {missed['strict']}" if missed["strict"] else ""))
    return {"result": result, "avg_trade": at, "lines": rows, "text": text}


def rank(results: list):
    """The index of the result that moves on: a raw() result - strict before low, then the bigger average trade; a variant_map()
    result - the more qualifying boxes, then the bigger average trade; a tie = the first; None when every one failed."""
    best = None
    for i, r in enumerate(results):
        if r["result"] == "pass" and "qualifying" in r:
            key = (r["qualifying"], r["avg_trade"])
        elif r["result"] in BARS:
            key = (-BARS.index(r["result"]), r["avg_trade"])
        else:
            continue
        if best is None or key > best[0]:
            best = (key, i)
    return None if best is None else best[1]


# ================================================================ stage 1, variant mode: the loose check of the map

def variant_map(t: dict) -> dict:
    """Stage 1 of variant mode: over `map_share` of the boxes make money AND at least `region_boxes` boxes are at the floor (an average
    trade of `floor_part` of line 2.2's cost floor or more) with `region_trades` trades or more -> the result (module docstring)."""
    need, x = PR.need("variant"), numbers(t)
    net, n = np.asarray(t["net"], np.float64).sum(1), np.asarray(t["n"], np.float64).sum(1)
    floor = PR.floor(t["root"], need["floor_part"])
    ids = list(t.get("ids") or range(len(net)))
    with np.errstate(all="ignore"):
        at = np.where(n > 0, net / np.where(n > 0, n, 1.0), -np.inf)
    ok = (at >= floor) & (n >= need["region_trades"])
    cells, q, (k, m) = [ids[i] for i in np.flatnonzero(ok)], int(ok.sum()), _boxes(t)
    rows = [L._row("P1.1", bool(x["share"] > need["map_share"]), x["share"], need["map_share"],
                   f"{L._pc(x['share'])} of boxes profitable ({k} of {m}; need over {L._pc(need['map_share'])})", profitable=k, variants=m),
            L._row("P1.2", q >= need["region_boxes"], q, need["region_boxes"],
                   f"{q} of {m} boxes have an average trade of {_fig(floor, (floor,), '$')} or more with {_fig(need['region_trades'])} or more trades "
                   f"(need at least {need['region_boxes']})", boxes=m, floor=floor, trades=need["region_trades"])]
    bad = [r["line"] for r in rows if not r["passed"]]
    return {"result": "fail" if bad else "pass", "avg_trade": x["avg_trade"], "qualifying": q, "cells": cells, "lines": rows,
            "text": f"fail: {', '.join(bad)} {'is' if len(bad) == 1 else 'are'} missed" if bad else
            f"pass: over {L._pc(need['map_share'])} of boxes profitable and {q} boxes at the floor with enough trades"}


# ================================================================ stage 3: one indicator on the heat map

def others_bar():
    """The share of the other-market heat maps that must be profitable (pipeline.json indicator.other_markets), or None: the
    other markets are SHOWN and ask nothing of an idea (the owner, 2026-10-08: "the same idea could work on another market,
    but not the exact same")."""
    return PR.need("indicator", "other_markets")


def strict_extra(t: dict, others: list) -> list:
    """Rows P3.4 (each side makes money: line 2.6's reading of `t`) and P3.6 (the other markets agree: `others` = the net of
    the average box of each other-market table; none = the row does not apply; no bar in pipeline.json = shown, never False)."""
    side, nb, need = L.sides(t), [float(a) for a in others or ()], others_bar()
    k = sum(bool(L._profitable(a)) for a in nb)
    share = k / len(nb) if nb else None
    asked = "shown: the other markets ask nothing of an idea" if need is None else f"need {L._pc(need)} or more"
    return [{**side, "line": "P3.4", "text": "P3.4" + side["text"][len(side["line"]):]},
            L._row("P3.6", None if not nb or need is None else bool(share >= need), share, need,
                   f"{k} of {len(nb)} other-market heat maps profitable, {L._pc(share)} ({asked})" if nb else
                   f"no other market runs this idea ({asked}{'' if need is None else ' of them profitable'})", profitable=k, tables=len(nb))]


def indicator(tf: dict, traw: dict, others: list) -> list:
    """Stage 3: the heat map with one indicator (`tf`) against its own bar, the raw heat map (`traw`) and the other
    markets (`others`) -> rows P3.1 .. P3.6."""
    x, was, need = numbers(tf), numbers(traw), PR.need("indicator")
    (k, m), at, plain = _boxes(tf), x["avg_trade"], was["avg_trade"]
    floor = PR.floor(tf["root"], need["floor_part"])
    usd = lambda v, o: "no trade" if v is None else _fig(v, () if o is None else (o,), "$")  # noqa: E731
    side, markets = strict_extra(tf, others)
    return [L._row("P3.1", bool(x["share"] > need["share"]), x["share"], need["share"],
                   f"{L._pc(x['share'])} of boxes profitable ({k} of {m}; need over {L._pc(need['share'])})", profitable=k, variants=m),
            L._row("P3.2", at is not None and bool(at >= floor), at, floor, f"no trade (need an average trade of {_fig(floor, (floor,), '$')})" if at is None else
                   f"average trade {_fig(at, (floor,), '$')} (need {_fig(floor, (floor,), '$')})"),
            L._row("P3.3", bool(x["trades"] >= need["trades"]), x["trades"], need["trades"],
                   f"{_fig(x['trades'], (need['trades'],))} trades a box (need {_fig(need['trades'], (need['trades'],))})"),
            side,
            L._row("P3.5", at is not None and plain is not None and bool(at > plain and x["share"] > was["share"]), at, plain,
                   f"{'' if at is None else 'average trade '}{usd(at, plain)} with it, {usd(plain, at)} without; {L._pc(x['share'])} of boxes profitable with it, "
                   f"{L._pc(was['share'])} without (need both higher)", share=x["share"], raw_share=was["share"], raw_avg_trade=plain),
            markets]


# ================================================================ stage 3, variant mode: the picked box

def variant_rows(b: dict, others: list) -> list:
    """Stage 3 of variant mode on the picked box `b` (module docstring) -> rows P3.2, P3.3, P3.4, P3.6. `others` = the net of the average
    box of each other-market table (shown, as strict_extra shows them)."""
    need, x = PR.need("variant"), numbers(b)
    at, floor = x["avg_trade"], PR.floor(b["root"], PR.need("variant", "floor_part"))
    n, count = float(np.asarray(b["n"], np.float64).sum()), need["region_trades"]
    side, markets = strict_extra(b, others)
    side = {**side, "text": side["text"].replace(", all variants together", "")}       # (line 2.6's words say "all variants together": this is one box)
    return [L._row("P3.2", at is not None and bool(at >= floor), at, floor, f"no trade (need an average trade of {_fig(floor, (floor,), '$')})" if at is None else
                   f"average trade {_fig(at, (floor,), '$')} (need {_fig(floor, (floor,), '$')})"),
            L._row("P3.3", bool(n >= count), n, count, f"{_fig(n, (count,))} trades (need {_fig(count, (count,))})"),
            side, markets]


# ================================================================ stage 4: the proof

def reshuffle(t: dict, rng=None) -> dict:
    """Row P4.1: the share of the reshuffled runs of the table in which the strict share AND the full floor both hold --
    lines.monte's computation for line 2.8, with the same helpers -- against the pipeline's own number for it."""
    tot, cnt = MC.reshuffle(t["net"], t["n"], rng)
    ok = L._heat(tot)[2] & L._floor(tot.sum(0), cnt, t["root"])[1]
    share, need, floor = float(ok.mean()), PR.need("proof", "reshuffle"), R.need("2.2", t["root"])
    return L._row("P4.1", bool(share >= need), share, need,
                  f"over {L._pc(R.need('2.1'))} of boxes profitable and an average trade of {_fig(floor, (floor,), '$')} or more both hold in {L._pc(share)} of "
                  f"{len(ok):,} reshuffled runs (need {L._pc(need)} or more)", runs=len(ok))


def random(p_beat, tries: int, what: str = "random heat maps") -> dict:
    """Row P4.2: `p_beat` (the share of the random heat maps the table beats; None = none was read) ABOVE the bar of the
    idea's `tries`-th try. No try yet is held to the first bar. `what` = the random tables in words (variant mode: those of the same box)."""
    k = max(1, int(tries))
    bar, alpha = PR.random_bar(k), PR.need("proof", "random_alpha")
    need = f"need above {_pct(bar)} = 100 - {100 * alpha:g} / {k} tr{'y' if k == 1 else 'ies'}"
    if p_beat is None:
        return L._row("P4.2", False, None, bar, f"no {what} to hold it against ({need})", tries=k)
    return L._row("P4.2", bool(p_beat > bar), float(p_beat), bar, f"beats {_pct(p_beat)} of the {what} on try {k} ({need})", tries=k)


def reshuffle_box(b: dict, rng=None) -> dict:
    """Row P4.1 of variant mode: the one box `b` (a table of one variant) is reshuffled like line 2.8's table (mc.reshuffle: whole days drawn
    with replacement, the fixed seed) and its average trade is held against the floor in every run; the share of the runs that hold it
    against `proof.reshuffle`. A run without a trade has no average trade: it does not hold."""
    tot, cnt = MC.reshuffle(b["net"], b["n"], rng)
    floor = PR.floor(b["root"], PR.need("variant", "floor_part"))
    with np.errstate(all="ignore"):
        ok = np.where(cnt > 0, tot[0] / np.where(cnt > 0, cnt, 1.0), -np.inf) >= floor
    share, need = float(ok.mean()), PR.need("proof", "reshuffle")
    return L._row("P4.1", bool(share >= need), share, need,
                  f"the box's average trade is {_fig(floor, (floor,), '$')} or more in {L._pc(share)} of {len(ok):,} reshuffled runs (need {L._pc(need)} or more)", runs=len(ok))
