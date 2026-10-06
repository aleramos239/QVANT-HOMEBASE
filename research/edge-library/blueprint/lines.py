"""lines.py -- one small function per blueprint line (toolkit plan, step 2). A function takes the TABLE DATA of one unit and
returns {"line", "passed", "number", "need", "text"} plus what that line wants kept (counts, seeds, THIN, on pace).
  passed   True / False; None = the line does not apply to this unit (2.7 without a filter)
  number   the unit's own figure for the line · need = the law's figure it is held against
  text     the line as it is printed, plain words with both figures: "2.2 FAIL average trade $41 (need $70)"
Every threshold comes from templates/rules.json through rules.py (the line number is the key); none is typed here.

TABLE DATA = a dict. tables.py fills it from a store; a test fills it by hand. A line reads only its own keys:
  root                 the market: 'NQ' | 'ES' | 'GC'                                                              2.2 2.8
  net, n               (variants x days): net in dollars after costs at 1 contract, and trades, of each judged variant on
                       each session day (a day without a trade = 0)                                    2.1 2.2 2.4 2.8 4.7
  controls             {name: the judge's verdict of one random control: p_beat, replicates, real_replicates, short}   2.3
  round                1 .. 5: which bar of 2.3 applies (default 1)                                              2.3 2.7
  months               the months the days cover, when fewer than the build's: 2.4 is then also read "on pace"         2.4
  neighbors            [net of the average variant of each neighbor table]                                          2.5
  long, short, n_long, n_short     net and trades of each side, all variants together                               2.6
  sides                'both' | 'long' | 'short': what the idea's card says (line 0.6); not given = no card             2.6
  filters              [{"name", "avg_trade", "plain_avg_trade", "p_beat": [...]}]: each filter of the unit against the
                       same strategy without it (or {"name", "why"} when that cannot be read); empty = no filter      2.7
  reason               the reason of this round, as it was written before the run (2.9 also reads `round`)            2.9
"""
from __future__ import annotations

import numpy as np

from . import mc as MC
from . import rules as R

RANDOM = ("c1", "shift", "c2")      # the judge's random controls: random entries · a random minute or direction · a shuffled book


def _row(line: str, passed, number, need, words: str, **more) -> dict:
    """A line's result; `text` = the line as it is printed: `2.2 FAIL average trade $41 (need $70)` (n/a = it does not apply)."""
    mark = "n/a " if passed is None else "PASS" if passed else "FAIL"
    return {"line": line, "passed": passed, "number": number, "need": need, "text": f"{line} {mark} {words}", **more}


def _pc(v) -> str:
    return f"{100 * v:.4g} %"


def _n(v, need=None, unit: str = "") -> str:
    """A figure in whole units ($41, 310); with cents only when the whole figure would read the same as `need` and is not it."""
    whole = need is None or round(v) != round(need) or v == need
    return ("-" if v < 0 else "") + unit + (f"{abs(v):,.0f}" if whole else f"{abs(v):,.2f}")


def _profitable(x):
    """"Profitable" / "makes money" = above $0 (rules.json 2.1): a variant, the average variant, a neighbor table."""
    return x > R.rule("2.1")["also"]["profitable_above"]


def _heat(v) -> tuple:
    """Line 2.1 on the variants' nets, v = (variants,) or (variants x runs) -> (share of variants profitable, net of the
    average variant, met): the share is held against the line AND the average variant is profitable."""
    share, avg = _profitable(v).mean(0), v.mean(0)
    return share, avg, R.OPS[R.rule("2.1")["op"]](share, R.need("2.1")) & _profitable(avg)


def _floor(net, trades, root: str) -> tuple:
    """Line 2.2 -> (average trade = net of all variants / their trades, met); no trade = not met. One value, or one per run."""
    at = np.divide(net, trades, out=np.full(np.shape(net), -np.inf), where=np.asarray(trades) > 0)
    return at, R.OPS[R.rule("2.2")["op"]](at, R.need("2.2", root))


# ================================================================ phase 2: build

def heat(t: dict) -> dict:
    """2.1 Most settings make money: more than 60 % of the variants are profitable, and so is the average variant."""
    v = np.asarray(t["net"]).sum(1)
    share, avg, ok = _heat(v)
    k, need = int(_profitable(v).sum()), R.need("2.1")
    return _row("2.1", bool(ok), float(share), need,
                f"{_pc(share)} of variants profitable ({k} of {len(v)}; need more than {_pc(need)}); average variant {_n(avg, unit='$')}"
                + ("" if _profitable(avg) else " (need it profitable)"), avg=float(avg), profitable=k, variants=len(v))


def floor(t: dict) -> dict:
    """2.2 The average trade is big enough: the net of all variants / their trades, at the market's cost floor or more."""
    net, n, need = float(np.asarray(t["net"]).sum(1).sum()), float(np.asarray(t["n"]).sum()), R.need("2.2", t["root"])
    if not n:
        return _row("2.2", False, None, need, f"no trade (need an average trade of {_n(need, unit='$')})")
    at, ok = _floor(net, n, t["root"])
    return _row("2.2", bool(ok), float(at), need, f"average trade {_n(float(at), need, '$')} (need {_n(need, unit='$')})")


def beats_random(t: dict) -> dict:
    """2.3 It beats random entries with the same stops and targets: ABOVE the round's bar of the random tables (strict), with
    every trade matched. Every random control of the unit must hold; the number is the weakest of them. THIN = it rests on
    fewer real random-entry seeds than the law asks (control.json): said, not failed."""
    rd, want = t.get("round", 1), R.template("control")["seeds"]
    bar = R.need("2.3", rd)
    C = {k: v for k, v in (t.get("controls") or {}).items() if k in RANDOM}
    gone = [f"{k}: {v.get('why') or 'not drawn'}" for k, v in C.items() if "p_beat" not in v]
    if not C or gone:
        return _row("2.3", False, None, bar, f"no random tables to hold it against ({'; '.join(gone) or 'no control'}; need above {_pc(bar)})",
                    round=rd, seeds=0, thin=True, controls=C)
    v = min(C.values(), key=lambda x: x["p_beat"])
    short = sum(int(x.get("short") or 0) for x in C.values())
    seeds = min(x["real_replicates"] for x in C.values())
    ok = all(R.meets("2.3", x["p_beat"], rd) for x in C.values()) and not short
    return _row("2.3", bool(ok), v["p_beat"], bar,
                f"beats {_pc(v['p_beat'])} of {v['replicates']:,} random tables (need above {_pc(bar)}); {seeds} seed{'s' * (seeds != 1)}"
                + (f": THIN (the law asks {want})" if seeds < want else "") + (f"; {short:,} trades had no random match" if short else ""),
                round=rd, seeds=seeds, thin=seeds < want, controls=C)


def trades(t: dict) -> dict:
    """2.4 Enough trades: the average variant's trades, 200 or more. On fewer months than the build has (a dry run on the
    stored days) the line is ALSO read "on pace": the same count against 200 scaled to those months."""
    n, need, full = float(np.asarray(t["n"]).sum(1).mean()), R.need("2.4"), R.template("ranges")["build"]["months"]
    r = _row("2.4", R.meets("2.4", n), n, need, f"{_n(n, need)} trades, average variant (need {need:,})")
    if t.get("months") and t["months"] < full:
        pace = need * t["months"] / full
        ok = bool(R.OPS[R.rule("2.4")["op"]](n, pace))
        r["on_pace"] = {"passed": ok, "need": pace, "months": t["months"]}
        r["text"] += f"; on pace: {'PASS' if ok else 'FAIL'} (need {_n(pace)} on the stored {t['months']} months)"
    return r


def neighbors(t: dict) -> dict:
    """2.5 Its neighbors agree: half or more of the idea's other tables have a profitable average variant. No neighbor table
    = not met (the card names them: line 0.4)."""
    nb, need = list(t.get("neighbors") or []), R.need("2.5")
    k = sum(bool(_profitable(a)) for a in nb)
    share = k / len(nb) if nb else 0.0
    return _row("2.5", bool(nb) and R.meets("2.5", share), share, need,
                f"{k} of {len(nb)} neighbor tables profitable, {_pc(share)} (need {_pc(need)} or more)" if nb else
                f"no neighbor table (need {_pc(need)} or more of them profitable)", profitable=k, tables=len(nb))


def sides(t: dict) -> dict:
    """2.6 Long and short each make money on their own, all variants together; a table without a trade is not met. The
    number is the weaker side. `sides` = what the idea's card says (line 0.6):
      'long' | 'short'   one-sided by its card: judged on that side; a trade on the other side is not the card's rule
      'both'             both sides must make money: a side without a trade made none
      not given          no card (a dry run on stored units): a table with trades on one side only is judged on that side"""
    need, card = R.need("2.6"), t.get("sides")
    usd = lambda v: _n(v, unit="$")  # noqa: E731
    net = {s: float(t[s]) for s in ("long", "short") if t[f"n_{s}"]}
    more = {k: (float if k in ("long", "short") else int)(t[k]) for k in ("long", "short", "n_long", "n_short")}
    if not net:
        return _row("2.6", False, None, need, "no trade", **more)
    if card in ("long", "short"):
        other = "short" if card == "long" else "long"
        text = f"{card} only by its card: " + (f"{usd(net[card])}, all variants together (need above {usd(need)})" if card in net else "no trade on that side") \
            + (f"; {more['n_' + other]:,} {other} trades are not the card's rule" if other in net else "")
        return _row("2.6", card in net and R.meets("2.6", net[card]) and other not in net, net.get(card), need, text, **more)
    if card == "both" or len(net) == 2:
        said = ", ".join(f"{s} {usd(net[s])}" if s in net else f"{s}: no trade" for s in ("long", "short"))
        return _row("2.6", len(net) == 2 and all(R.meets("2.6", v) for v in net.values()), min(net.get(s, 0.0) for s in ("long", "short")), need,
                    f"{said}, all variants together (need both above {usd(need)})", **more)
    (s, v), = net.items()
    return _row("2.6", R.meets("2.6", v), v, need, f"{s} only: {usd(v)}, all variants together (need above {usd(need)})", **more)


def filter_alone(t: dict) -> dict:
    """2.7 A filter is kept only if it wins alone: the plain version plus that one filter has a HIGHER average trade than the
    plain version, and meets that round's random bar (line 2.3 of this table; a day filter also against random day subsets of
    the same size). A unit without a filter: the line does not apply (passed None)."""
    F, rd = list(t.get("filters") or []), t.get("round", 1)
    if not F:
        return _row("2.7", None, None, None, "no filter in this unit")
    gone = [f for f in F if "avg_trade" not in f]
    if gone:
        return _row("2.7", False, None, None, f"{gone[0]['name']}: no plain version to hold it against ({gone[0].get('why')})", filters=F)
    f = min(F, key=lambda x: x["avg_trade"] - x["plain_avg_trade"])
    higher = all(x["avg_trade"] > x["plain_avg_trade"] for x in F)
    bar = bool(beats_random(t)["passed"]) and all(R.meets("2.3", p, rd) for x in F for p in x.get("p_beat", ()))
    return _row("2.7", bool(higher and bar), f["avg_trade"], f["plain_avg_trade"],
                f"{f['name']}: average trade {_n(f['avg_trade'], f['plain_avg_trade'], '$')} with it, {_n(f['plain_avg_trade'], unit='$')} "
                f"without (need higher)" + ("" if bar else f"; the random bar of round {rd} is not met"), higher=bool(higher), random_bar=bar, filters=F)


def monte(t: dict, rng=None) -> dict:
    """2.8 Monte Carlo: lines 2.1 and 2.2 are read again in every reshuffled run of the table (mc.py); both must hold in
    75 % of the runs or more. rng None = the fixed seed of montecarlo.json."""
    tot, cnt = MC.reshuffle(t["net"], t["n"], rng)
    ok = _heat(tot)[2] & _floor(tot.sum(0), cnt, t["root"])[1]
    share, need = float(ok.mean()), R.need("2.8")
    return _row("2.8", R.meets("2.8", share), share, need,
                f"2.1 and 2.2 both hold in {_pc(share)} of {len(ok):,} reshuffled runs (need {_pc(need)} or more)", runs=len(ok))


BUILD = (heat, floor, beats_random, trades, neighbors, sides, filter_alone, monte)        # lines 2.1 .. 2.8, in the law's order


def rounds(t: dict) -> dict:
    """2.9 Rounds: at most 5, each with its reason written before the run. Read off what the run was started with: its
    round (the bar of 2.3 rises with it) and the reason given for it. No reason = not met. The line is not read off a
    table, so it is not in BUILD: a dry run on stored units has no round."""
    rd, need, why = t.get("round", 1), R.need("2.9"), " ".join(str(t.get("reason") or "").split())
    R.need("2.3", rd)                               # a round the law does not have (0, 6) is refused, as in 2.3
    return _row("2.9", bool(R.meets("2.9", rd) and why), rd, need,
                f"round {rd} of at most {need}" + (f", its reason written before the run: {why}" if why else ": no reason was written before the run"),
                reason=why or None)


# ================================================================ phase 4: the out-of-sample test (its Monte Carlo line)

def monte_test(t: dict, rng=None) -> dict:
    """4.7 Monte Carlo: the average variant makes money in 90 % of the reshuffled runs of the test period or more."""
    tot, _ = MC.reshuffle(t["net"], t["n"], rng)
    ok = tot.mean(0) > R.rule("4.7")["also"]["above"]
    share, need = float(ok.mean()), R.need("4.7")
    return _row("4.7", R.meets("4.7", share), share, need,
                f"the average variant makes money in {_pc(share)} of {len(ok):,} reshuffled runs (need {_pc(need)} or more)", runs=len(ok))
