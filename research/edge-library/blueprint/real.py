"""REAL OR LUCK: the few lines a 3:1 walk-forward idea must pass, and nothing else (owner, 2026-10-25: "make the requirements just enough
for the strategy to be real robust and not luck or fake"). Pure: it reads hmwf.show()'s dict and runs nothing.

The lines judge the PICKED box (or, before a pick, are shown for no box: only the box-spread line). Profit factor, Sharpe, drawdown and
the average trade size are shown in the table and never block (no dollar floor: profit after costs and the t-statistic are the test).
The prop sim and the eval card are not a line here: off until the owner asks."""

MIN_TRADES_IS, MIN_TRADES_OOS = 200, 60     # enough trades to say anything (in-sample; on the test months)
MIN_YEARS_GREEN, MAX_BEST_YEAR = 2 / 3, 0.5     # most years green (4 of 6), and no year carries more than half the net
MIN_BOXES_PROFIT = 0.6                      # judge the average of the boxes: this share of all boxes made money
T_BAR, T_PER_TRY = 2.0, 0.25                # t-statistic of the per-trade net; the bar rises by T_PER_TRY for each try after the first


def _line(name: str, ok, said: str) -> dict:
    return {"line": name, "ok": ok, "said": said}      # ok: True | False | None (not known yet: the step is not run)


def check(s: dict, tries: int = 1) -> list:
    """s = hmwf.show(): {"is": rows, "lock", "oos"} -> the lines, each {"line", "ok", "said"}."""
    rows, lock, oos = s["is"], s["lock"], s["oos"]
    out = []
    prof = [r["net"] > 0 for r in rows if r["net"] is not None]
    out.append(_line("boxes", (sum(prof) / len(prof) >= MIN_BOXES_PROFIT) if prof else None,
                     f"{sum(prof)} of {len(prof)} boxes made money in-sample (need {MIN_BOXES_PROFIT:.0%}): the average of the boxes, not the best"))
    box = next((r for r in rows if lock and r["box"] == lock["box"]), None)
    if box is None:
        return out + [_line("picked box", None, "not picked yet: the owner picks a box, then the other lines are read")]
    bar = T_BAR + T_PER_TRY * (max(tries, 1) - 1)
    out.append(_line("trades", box["trades"] >= MIN_TRADES_IS, f"{box['trades']} in-sample trades (need {MIN_TRADES_IS}+)"))
    out.append(_line("luck", box["t_stat"] is not None and box["t_stat"] >= bar and box["net"] > 0,
                     f"t {box['t_stat'] if box['t_stat'] is None else round(box['t_stat'], 2)} in-sample (need {bar:g}+ after {tries} {'try' if tries == 1 else 'tries'}), net {box['net']:,.0f}"
                     + (f", beats {box['beats_random']:.0%} of random entries" if box["beats_random"] is not None else "")))
    yn, yg, sh = box["years_n"], box["years_green"], box["best_year_share"]
    out.append(_line("years", bool(yn) and yg / yn >= MIN_YEARS_GREEN and sh is not None and sh <= MAX_BEST_YEAR,
                     f"{yg} of {yn} years green" + ("" if sh is None else f", best year {sh:.0%} of the net") + f" (need {MIN_YEARS_GREEN:.0%} green, no year over {MAX_BEST_YEAR:.0%})"))
    w = box["worse_fills_net"]
    out.append(_line("worse fills", None if w is None else w > 0, "worse-fills run not on file" if w is None else f"net {w:,.0f} with worse fills (need above 0)"))
    if oos is None or oos.get("state"):
        return out + [_line("test months", None, "not run: only when the owner says so")]
    x = oos["record"]
    out.append(_line("test months", x["net"] > 0 and box["net"] > 0 and x["trades"] >= MIN_TRADES_OOS,
                     f"{x['trades']} trades (need {MIN_TRADES_OOS}+), net {x['net']:,.0f} (need above 0, same direction as in-sample {box['net']:,.0f})"))
    return out


def text(lines: list) -> str:
    mark = {True: "PASS", False: "FAIL", None: " .. "}
    return "REAL OR LUCK (the only lines that block; PF, Sharpe, drawdown and avg trade are shown, never block):\n" + "\n".join(
        f"  [{mark[r['ok']]}] {r['line']:<12s} {r['said']}" for r in lines)
