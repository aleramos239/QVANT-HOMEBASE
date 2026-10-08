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
    """The index of the raw() result that moves on: strict before low, then the bigger average trade, a tie = the first;
    None when every one failed."""
    best = None
    for i, r in enumerate(results):
        if r["result"] in BARS:
            key = (-BARS.index(r["result"]), r["avg_trade"])
            if best is None or key > best[0]:
                best = (key, i)
    return None if best is None else best[1]


# ================================================================ stage 3: one indicator on the heat map

def strict_extra(t: dict, others: list) -> list:
    """Rows P3.4 (each side makes money: line 2.6's reading of `t`) and P3.6 (the other markets agree: `others` = the net of
    the average box of each other-market table; none = the row does not apply)."""
    side, nb, need = L.sides(t), [float(a) for a in others or ()], PR.need("indicator", "other_markets")
    k = sum(bool(L._profitable(a)) for a in nb)
    share = k / len(nb) if nb else None
    return [{**side, "line": "P3.4", "text": "P3.4" + side["text"][len(side["line"]):]},
            L._row("P3.6", None if not nb else bool(share >= need), share, need,
                   f"{k} of {len(nb)} other-market heat maps profitable, {L._pc(share)} (need {L._pc(need)} or more)" if nb else
                   f"no other market runs this idea (need {L._pc(need)} or more of them profitable)", profitable=k, tables=len(nb))]


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


def random(p_beat, tries: int) -> dict:
    """Row P4.2: `p_beat` (the share of the random heat maps the table beats; None = none was read) ABOVE the bar of the
    idea's `tries`-th try. No try yet is held to the first bar."""
    k = max(1, int(tries))
    bar, alpha = PR.random_bar(k), PR.need("proof", "random_alpha")
    need = f"need above {_pct(bar)} = 100 - {100 * alpha:g} / {k} tr{'y' if k == 1 else 'ies'}"
    if p_beat is None:
        return L._row("P4.2", False, None, bar, f"no random heat maps to hold it against ({need})", tries=k)
    return L._row("P4.2", bool(p_beat > bar), float(p_beat), bar, f"beats {_pct(p_beat)} of the random heat maps on try {k} ({need})", tries=k)
