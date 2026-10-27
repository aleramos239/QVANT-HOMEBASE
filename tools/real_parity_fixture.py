"""The Lab's six real-or-luck lines (homebase/static/charts/reallines.js) are a copy of research blueprint/real.py check().
This writes tests/js/fixtures/real_parity.json: inputs that drive every line to PASS, FAIL and not-run, every verdict, tries 1, 4
and 500 (a cut count), with real.check()'s own output for each. tests/js/reallines.test.mjs compares the JS copy line by line.

    .venv/bin/python tools/real_parity_fixture.py --real research/edge-library/blueprint/real.py

Run it again whenever real.py changes (the worktree has no research/, so the fixture is committed). It reads real.py, writes the
fixture and nothing else. verdict() below is the Lab's verdict rule (plan_final.md section 3); reallines.js has the same one."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

NEXT = {"boxes": "the in-sample table", "picked box": "your pick", "luck": "the luck test", "worse fills": "worse fills",
        "test months": "the test months"}


def verdict(lines, s, cut=False):
    """REAL / LUCK / FAKE / NOT YET and why. FAKE: the test months ran and lost, or went the other way from in-sample. LUCK: any
    other line failed (the first, named). NOT YET: nothing failed but a line is not run (the first is the next step); a tries count
    that may be cut short never lets the luck line pass. REAL: all six pass."""
    rows, lock, oos = s["is"], s["lock"], s["oos"]
    box = next((r for r in rows if lock and r["box"] == lock["box"]), None)
    by = {x["line"]: x for x in lines}
    if box is not None and oos is not None and not oos.get("state") and not (oos["record"]["net"] > 0 and box["net"] > 0):
        return {"word": "FAKE", "why": by["test months"]["said"]}
    bad = next((x for x in lines if x["ok"] is False), None)
    if bad:
        return {"word": "LUCK", "why": bad["said"]}
    for x in lines:
        if x["ok"] is None or (cut and x["line"] == "luck"):
            return {"word": "NOT YET", "why": "next, " + ("a full count of tries" if x["ok"] and cut else NEXT[x["line"]])}
    return {"word": "REAL", "why": "all six lines pass"}


def row(box, net=5000.0, trades=250, t=2.5, yn=5, yg=4, sh=0.3, wf=None, br=None):
    return {"box": box, "net": net, "trades": trades, "t_stat": t, "years_n": yn, "years_green": yg, "best_year_share": sh,
            "worse_fills_net": wf, "beats_random": br}


def done(net=900.0, trades=80):
    return {"record": {"net": net, "trades": trades}}


def table(pick, n_up=3, n_down=1):
    """n_up boxes that made money and n_down that lost; `pick` replaces box 0 (the picked one)."""
    rows = [dict(pick, box=0)] + [row(i, net=100.0 * i) for i in range(1, n_up)] + [row(n_up + i, net=-50.0) for i in range(n_down)]
    return rows


def cases():
    good = row(0, net=5000.0, trades=250, t=3.1, yn=5, yg=4, sh=0.3, wf=1200.0, br=0.875)
    lock = {"box": 0}
    out = [
        ("no table yet", {"is": [], "lock": None, "oos": None}, 1, False),
        ("table, no pick", {"is": table(good), "lock": None, "oos": None}, 1, False),
        ("table, most boxes lose, no pick", {"is": table(good, 1, 3), "lock": None, "oos": None}, 1, False),
        ("a box with no numbers is left out", {"is": table(good) + [row(9, net=None)], "lock": None, "oos": None}, 1, False),
        ("a pick that names no box in the table", {"is": table(good), "lock": {"box": 99}, "oos": None}, 1, False),
        ("all pass, worse fills not on file, no test months", {"is": table(dict(good, worse_fills_net=None)), "lock": lock, "oos": None}, 1, False),
        ("all six pass", {"is": table(good), "lock": lock, "oos": done()}, 1, False),
        ("all six pass but the tries count is cut", {"is": table(dict(good, t_stat=150.0)), "lock": lock, "oos": done()}, 500, True),
        ("a cut count still fails a low t", {"is": table(good), "lock": lock, "oos": done()}, 500, True),
        ("too few in-sample trades", {"is": table(dict(good, trades=199)), "lock": lock, "oos": done()}, 1, False),
        ("200 trades is enough", {"is": table(dict(good, trades=200)), "lock": lock, "oos": done()}, 1, False),
        ("t not on file", {"is": table(dict(good, t_stat=None)), "lock": lock, "oos": None}, 1, False),
        ("t under the bar after 4 tries", {"is": table(dict(good, t_stat=2.7)), "lock": lock, "oos": None}, 4, False),
        ("t on the bar after 4 tries", {"is": table(dict(good, t_stat=2.75)), "lock": lock, "oos": done()}, 4, False),
        ("t rounds half to even (2.125)", {"is": table(dict(good, t_stat=2.125)), "lock": lock, "oos": None}, 1, False),
        ("t 2.675 rounds down (binary)", {"is": table(dict(good, t_stat=2.675)), "lock": lock, "oos": None}, 1, False),
        ("t 2.0 prints 2.0", {"is": table(dict(good, t_stat=2.0)), "lock": lock, "oos": None}, 2, False),
        ("a tiny negative t prints -0.0", {"is": table(dict(good, t_stat=-0.001)), "lock": lock, "oos": None}, 1, False),
        ("t exactly -0.0 prints -0.0", {"is": table(dict(good, t_stat=-0.0)), "lock": lock, "oos": None}, 1, False),
        ("t not on file, all else passes, test months won", {"is": table(dict(good, t_stat=None)), "lock": lock, "oos": done()}, 1, False),
        ("0 tries counts as 1", {"is": table(good), "lock": lock, "oos": None}, 0, False),
        ("good t but a losing box", {"is": table(dict(good, net=-0.4)), "lock": lock, "oos": None}, 1, False),
        ("losing box, winning test months = the other way", {"is": table(dict(good, net=-120.0)), "lock": lock, "oos": done()}, 1, False),
        ("no years", {"is": table(dict(good, years_n=0, years_green=0, best_year_share=None)), "lock": lock, "oos": None}, 1, False),
        ("4 of 6 years green is enough", {"is": table(dict(good, years_n=6, years_green=4, best_year_share=0.125)), "lock": lock, "oos": None}, 1, False),
        ("3 of 5 years green is not", {"is": table(dict(good, years_n=5, years_green=3)), "lock": lock, "oos": None}, 1, False),
        ("best year exactly half", {"is": table(dict(good, best_year_share=0.5)), "lock": lock, "oos": None}, 1, False),
        ("best year over half (62.5% prints 62%)", {"is": table(dict(good, best_year_share=0.625)), "lock": lock, "oos": None}, 1, False),
        ("best year share not known", {"is": table(dict(good, best_year_share=None)), "lock": lock, "oos": None}, 1, False),
        ("worse fills lose", {"is": table(dict(good, worse_fills_net=-10.0)), "lock": lock, "oos": done()}, 1, False),
        ("worse fills exactly 0", {"is": table(dict(good, worse_fills_net=0.0)), "lock": lock, "oos": None}, 1, False),
        ("worse fills 1234.5 prints 1,234", {"is": table(dict(good, worse_fills_net=1234.5)), "lock": lock, "oos": None}, 1, False),
        ("worse fills 1235.5 prints 1,236", {"is": table(dict(good, worse_fills_net=1235.5)), "lock": lock, "oos": None}, 1, False),
        ("beats 84.5% prints 84%", {"is": table(dict(good, beats_random=0.845)), "lock": lock, "oos": None}, 1, False),
        ("a read that is used, no record", {"is": table(good), "lock": lock, "oos": {"state": "used", "claim": {}}}, 1, False),
        ("test months thin (59 trades)", {"is": table(good), "lock": lock, "oos": done(trades=59)}, 1, False),
        ("test months 60 trades is enough", {"is": table(good), "lock": lock, "oos": done(trades=60)}, 1, False),
        ("test months lose", {"is": table(good), "lock": lock, "oos": done(net=-5.0)}, 1, False),
        ("test months flat", {"is": table(good), "lock": lock, "oos": done(net=0.0)}, 1, False),
        ("big nets print with commas, half to even", {"is": table(dict(good, net=1234567.5)), "lock": lock, "oos": done(net=2.5)}, 1, False),
        ("60% of the boxes exactly", {"is": table(good, 3, 2), "lock": lock, "oos": None}, 1, False),
        ("2 of 3 boxes made money", {"is": table(good, 2, 1), "lock": None, "oos": None}, 1, False),
    ]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--real", required=True, help="path to research/edge-library/blueprint/real.py (read only)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "tests" / "js" / "fixtures" / "real_parity.json"))
    a = ap.parse_args()
    src = Path(a.real).resolve()
    spec = importlib.util.spec_from_file_location("real_for_parity", src)
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    out = []
    for name, s, tries, cut in cases():
        lines = real.check(s, tries)
        out.append({"name": name, "s": s, "tries": tries, "cut": cut, "lines": lines, "verdict": verdict(lines, s, cut)})
    words = {c["verdict"]["word"] for c in out}
    assert words == {"REAL", "LUCK", "FAKE", "NOT YET"}, words
    for ln in ("boxes", "picked box", "trades", "luck", "years", "worse fills", "test months"):
        seen = {x["ok"] for c in out for x in c["lines"] if x["line"] == ln}
        assert seen >= ({None} if ln == "picked box" else {True, False}), (ln, seen)
    doc = {"made_by": "tools/real_parity_fixture.py", "real_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
           "constants": {k: getattr(real, k) for k in ("MIN_TRADES_IS", "MIN_TRADES_OOS", "MIN_YEARS_GREEN", "MAX_BEST_YEAR",
                                                       "MIN_BOXES_PROFIT", "T_BAR", "T_PER_TRY")},
           "cases": out}
    Path(a.out).write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{len(out)} cases -> {a.out}")


if __name__ == "__main__":
    main()
