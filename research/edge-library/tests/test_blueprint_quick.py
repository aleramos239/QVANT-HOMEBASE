"""LOCK of THE QUICK LOOKS (blueprint/quick.py: `bp.py heatmap <name> [--place=..] [--round=N]`, `bp.py mc <name>
[--on=build|test]`) and of THE EARLY LOOK at the test days (blueprint/oos.py, freeze.early: `bp.py test <name> --confirm
--early-look`; the owner's decision of 2026-10-06: "warn, then run if I say yes").

(a) THE HEAT MAP of a build round, on a store TYPED BY HAND (every net is a formula, so every number is known): one row per
    value of the main setting, one column per exit cell of the standard table (8 stops x 4 targets, in the menu's order),
    each cell = that variant's net on the build days; a variant that cannot trade there and one with the trades of another
    are shown and not counted; under it what line 2.1 reads, the middle variant, the best and the worst cell (information:
    the law judges the average), and the same in one line for every other place of the card. On a real (tiny) build its
    numbers are the saved line 2.1's.
(b) THE MONTE CARLO: the law's own line -- 2.8 on build, 4.7 on a test that is on file -- with THE number the build or the
    test saved; then the same 1,000 reshuffled runs (mc.py, the fixed seed) as two tables, the average and the default
    variant: final net and worst drawdown at the 5th .. 95th percentile, the share of runs above $0. Held against a slow
    count of every run; the same answer every time.
(c) BOTH VIEWS READ AND NOTHING ELSE: no file of the idea changes, no engine call but the calendar. Refused: no such idea, no
    build yet ("run the build first"), a place or a round the idea does not have, --on=test without a test on file.
(d) THE EARLY LOOK: without --early-look nothing changes (an idea that is not frozen is refused, and the refusal now says the
    owner may ask for one). With it: what is there is frozen under a lock MARKED early_look (the build lines that failed,
    whether the code check stands), the read is CLAIMED in the one-read log before the pass exactly as a test's, lines
    4.1-4.9 are read, and EVERYTHING says "EARLY LOOK — the test days are used for this idea". It is saved beside the idea's
    own files (early_look/lock.json, early_look/test.json), never as its lock.json or test.json: so the app's idea store
    cannot count it, and the idea is NEVER proven on history by it -- whatever its seven lines say, whatever the build says
    later. Afterwards a proper test of the same idea is refused as used; --second-look is the only way past.
(e) THE COMMAND LINES as the connector writes them (--opt=value; --root and --json last) -- and THE CONNECTOR ITSELF: the
    app's blueprint_heatmap, blueprint_mc and blueprint_test (early_look) against this toolkit. Through it an early look
    is only asked for where it is refused before anything is read.

NO TEST DAY IS READ HERE: tests/blueprint_frozen.py `fake_read` stands in for runner.run_test and writes hand-made trades.
The one engine work is the tiny build the other suites share (3 named BUILD days, 2 exit cells, 1 worker). Temp folders only
(--root, HOMEBASE_DRAFTS_DIR); the last test looks.
  pytest tests/test_blueprint_quick.py -q        python tests/test_blueprint_quick.py     one line per test
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_frozen as F  # noqa: E402
import blueprint_synth as SY  # noqa: E402

import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import evalcard as EC  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import jobs as JOBS  # noqa: E402
from blueprint import lines as L  # noqa: E402
from blueprint import mc as MC  # noqa: E402
from blueprint import oos as OOS  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import quick as Q  # noqa: E402
from blueprint import reads as READS  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402

NAME, KEY = "bpl_orb", "bpl_orb-NQ-tf15"            # the lead the suites of the freeze and of the one read build (a tiny real run)
MADE = "bpl_made"                                    # an idea TYPED BY HAND: its stores hold trades no engine made
VALUES = ["5", "15", "30", "60"]                     # its main setting, or_min; "60" trades at midday only: it cannot trade at home
DAYS = ["2022-03-15", "2023-03-22", "2024-06-12", "2025-06-30"]      # 4 build days (the last one is the build's last day)
MENU = R.exit_menu("NQ")[:32]                        # the hand-made tables hold the 32 cells of the old library's menu, stops outer, targets inner (a view shows what a store holds)
HOUR = {"asia": "01:00", "nyam": "10:00", "mid": "12:00"}
BASE = {"nyam": 50.0, "mid": 20.0, "asia": -30.0}
DAY = [-20.0, 60.0, 100.0, 180.0]                    # what each of the 4 days adds to every trade: one poor day, three good ones
PCT = [5, 25, 50, 75, 95]
EARLY = "EARLY LOOK — the test days are used for this idea"
IS = F.IS
RESULTS: dict = {}
_T: dict = {}


def setup_function(_=None):
    F.env_on()


def teardown_function(_=None):
    F.env_off()


def reads(root) -> list:
    f = Path(root) / "test_reads.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def events(d: Path) -> list:
    return [json.loads(x) for x in (d / "log.jsonl").read_text().splitlines()]


def files(d: Path) -> dict:
    """Every file under a folder with its bytes: what a command that only reads leaves as it was."""
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


# ================================================================ an idea typed by hand

def usd(vi: int, xi: int, k: int, sess: str = "nyam", tf: str = "15") -> float:
    """THE NET OF ONE HAND-MADE TRADE: variant vi, exit cell xi, day k. A cell trades once a day in a session, so its net on
    the 4 days is 4 x (the session's base x (vi + 1) - 7 xi [+ 15 on 5-minute bars]) + 320."""
    return BASE[sess] * (vi + 1) - 7.0 * xi + (15.0 if tf == "5" else 0.0) + DAY[k]


def cell_net(vi: int, xi: int, sess: str = "nyam", tf: str = "15") -> float:
    xi = 0 if (tf, vi, xi) == ("15", 0, 1) else xi                               # the planted twin: cell (0, 1) holds the trades of (0, 0)
    return sum(usd(vi, xi, k, sess, tf) for k in range(len(DAYS)))


def cid(vi: int, xi: int) -> str:
    return f"or_min{VALUES[vi]}_{S.cell_id(MENU[xi])}"


def _trade(day: str, k: int, net: float, sess: str) -> dict:
    ms = S.et_ns(dt.date.fromisoformat(day), HOUR[sess]) // 1_000_000
    return {"date": day, "entry_ms": ms, "exit_ms": ms + 60_000, "net": float(net), "side": "long" if k % 2 == 0 else "short", "qty": 1, "exit_reason": "tp",
            "entry_price": 20000.0, "exit_price": 20000.0, "sl": 19990.0, "mae_usd": 0.0}


def _store(tf: str, sessions) -> Path:
    """ONE store of the hand-made idea, in the library's own format: every value x the 32 exit cells; a cell trades once a
    day in each session it trades in (`sessions(vi)`), at the net of usd()."""
    grid = [{"id": cid(vi, xi), "variant": {"or_min": v}, "exit": dict(x), "vi": vi, "xi": xi} for vi, v in enumerate(VALUES) for xi, x in enumerate(MENU)]
    res = []
    for c in grid:
        vi, xi = c["vi"], (0 if (tf, c["vi"], c["xi"]) == ("15", 0, 1) else c["xi"])
        t = sorted((_trade(d, k, usd(vi, xi, k, s, tf), s) for k, d in enumerate(DAYS) for s in sessions(vi)), key=lambda x: (x["exit_ms"], x["entry_ms"]))
        res.append({"trades": t, "sessions": len(DAYS), "used": len(DAYS), "skipped": [], "no_trade": [], "elapsed_s": 0.0, "skipped_by_error": 0,
                    "meta": {"inputs": {}, "engine": "hand-made", "root": "NQ", "range": {"start": "2021-09-22", "end": "2025-06-30", "holdout": True, "period": "bp_build"}}})
    return LB.write_unit(f"{MADE}-NQ-tf{tf}", {"family": "orb", "idea": MADE, "tf": tf, "period": "bp_build", "stage": "bp_build", "days": DAYS, "inputs_hash": "0" * 16},
                         grid, res, MADE_OUT)


MADE_OUT = F.tmp() / "runs_made"
PLAN = {"home": {"market": "NQ", "session": "nyam", "bar": "15", "table": "NQ-tf15-nyam", "said": "home"},
        "neighbors": [{"market": "NQ", "session": "mid", "bar": "15", "table": "NQ-tf15-mid", "said": "midday"},
                      {"market": "NQ", "session": "nyam", "bar": "5", "table": "NQ-tf5-nyam", "said": "5-minute bars"}],
        "not_here": {"market": "NQ", "session": "asia", "bar": "15", "table": "NQ-tf15-asia", "said": "the Asian session"},
        "sides": "both", "filters": [], "main_setting": "or_min", "values": VALUES, "variants": 128,
        "stores": [{"market": "NQ", "bar": "15", "sessions": ["asia", "nyam", "mid"]}, {"market": "NQ", "bar": "5", "sessions": ["nyam"]}]}
JUDGED = [(vi, xi) for vi in range(3) for xi in range(32) if (vi, xi) != (0, 1)]      # at home: "60" cannot trade there, (0, 1) is the twin of (0, 0)


def home_table() -> dict:
    """The hand-made home table as the lines read one: (95 judged variants x 4 days) net and trades."""
    return {"root": "NQ", "net": np.array([[usd(vi, xi, k) for k in range(len(DAYS))] for vi, xi in JUDGED]), "n": np.ones((len(JUDGED), len(DAYS)))}


def middle() -> tuple:
    """The default variant of the hand-made home table by the rule itself: the middle of the variants that make money, by
    net, then by variant order; an even count takes the lower of the two middle ones."""
    surv = sorted(((round(cell_net(vi, xi), 2), vi, xi) for vi, xi in JUDGED if cell_net(vi, xi) > 0))
    return cid(*surv[(len(surv) - 1) // 2][1:]), len(surv)


def made() -> Path:
    """The ideas root of the hand-made idea: ONE build round on file -- its settings, its result, its two stores (home,
    midday and the Asian session in one; 5-minute bars in the other). Written once, through the app's idea store."""
    if "made" not in _T:
        root = F.tmp() / "ideas" / "q_made"
        _store("15", lambda vi: ["mid"] if vi == 3 else ["asia", "nyam", "mid"])
        _store("5", lambda vi: ["nyam"])
        IS.create(MADE, root)
        spec = {"name": MADE, "version": 1, "card": {**F.CARD, "neighbors": ["midday", "5-minute bars"]}, "run": {**F.SETTINGS, "params": {"or_min": VALUES}}}
        IS.write_card(MADE, f"# {MADE} -- idea card (typed by hand)\n", root)
        IS.write_spec(MADE, spec, root)
        IS.write_reason(MADE, 1, "typed by hand", root)
        IS.write_round_spec(MADE, 1, {**spec, "round": 1, "store": MADE, "plan": PLAN}, root)
        t, (cell, n) = home_table(), middle()
        rows = [L.heat(t), L.floor(t), *[L._row(f"2.{i}", None, None, None, "typed by hand") for i in range(3, 8)], L.monte(t),
                L._row("2.9", True, 1, 5, "round 1 of at most 5, its reason written before the run: typed by hand")]
        failed = [x["line"] for x in rows if x["passed"] is False]
        IS.write_build(MADE, 1, {**A.result("build", MADE, round=1, lines=rows, status="idea"), "idea": MADE, "counted": True, "dry_run": False, "store": MADE,
                                 "home": "NQ-tf15-nyam", "home_store": f"{MADE}-NQ-tf15", "filter": None, "failed": failed, "passed": not failed,
                                 "days": {"start": "2021-09-22", "end": "2025-06-30", "months": 45, "sessions": len(DAYS), "named": DAYS},
                                 "stores": [{"key": f"{MADE}-NQ-tf{tf}", "kind": "unit", "root": "NQ", "tf": tf, "path": str(MADE_OUT / f"{MADE}-NQ-tf{tf}")} for tf in ("15", "5")],
                                 "default": {"cell": cell, "survivors": n, "trades": 4, "run_id": None, "note": None}}, root)
        _T["made"] = root
    return _T["made"]


# ================================================================ (a) the heat map

def one_is_not_money(s: dict) -> bool:
    """Midday: 128 cells, the twin out, and of the 76 that do not lose one ends at exactly $0 -- 75 make money."""
    return (s["variants"], s["profitable"]) == (127, 75) and sum(cell_net(vi, xi, "mid") >= 0 for vi in range(4) for xi in range(32) if (vi, xi) != (0, 1)) == 76


def k(v: float) -> str:
    """Dollars in thousands with their mark, as the views write them."""
    return ("+" if v > 0 else "-" if v < 0 else "") + f"${abs(v) / 1000:,.1f}k"


def test_the_heat_map_is_one_row_a_value_and_one_column_an_exit_cell():
    root = made()
    r = Q.heatmap(MADE, root=root)
    assert list(r)[:len(F.CONTRACT)] == list(F.CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "saved", "error")] == [True, "heatmap", MADE, "idea", 2, 1, None, [], None]
    g = r["grid"]
    # ---- the shape: 4 values x the 32 exit cells of the standard table, in the menu's order -- 8 stops, the 4 targets inside each
    assert (g["setting"], g["rows"]) == ("or_min", VALUES) and g["cols"] == [S.cell_id(x) for x in MENU] and len(g["cols"]) == 32
    assert [len(row) for row in g["net"]] == [32] * 4 and g["cells"] == [[cid(vi, xi) for xi in range(32)] for vi in range(4)]
    assert g["stops"][::4] == ["atr 1.5", "atr 3", "pts 10", "pts 20", "pts 30", "pts 45", "pct 0.1", "pct 0.2"] and g["stops"] == [s for s in g["stops"][::4] for _ in range(4)]
    assert g["targets"] == ["no target", "1R", "2R", "3R"] * 8 and g["cols"][:5] == ["atr1p5-r0", "atr1p5-r1", "atr1p5-r2", "atr1p5-r3", "atr3-r0"]
    # ---- the numbers: every cell is that variant's net on the build days (the formula the store was typed with)
    for vi in range(3):
        for xi in range(32):
            assert g["net"][vi][xi] == cell_net(vi, xi), (vi, xi)
    assert g["net"][0][0] == g["net"][0][1] == 520.0 and g["net"][2][31] == 4 * (150.0 - 7 * 31) + 320 == 52.0 and g["net"][0][19] == -12.0
    assert g["net"][3] == [None] * 32                                             # "60" has no trade at home: it cannot trade there, and has no net
    assert r["not_judged"] == {"dead": [cid(3, xi) for xi in range(32)], "duplicates": [cid(0, 1)]}
    # ---- under it: what line 2.1 reads (dead and twin variants out), the middle variant, the two ends
    v = np.array([cell_net(vi, xi) for vi, xi in JUDGED])
    s = r["summary"]
    assert (s["place"], s["table"], s["said"], s["store"]) == ("home", "NQ-tf15-nyam", "home", f"runs_made/{MADE}-NQ-tf15")
    assert (s["variants"], s["profitable"], s["dead"], s["duplicates"]) == (95, int((v > 0).sum()), 32, 1) == (95, 76, 32, 1)
    assert s["share"] == 76 / 95 == 0.8 and s["avg"] == float(v.mean()) and s["median"] == float(np.median(v))
    assert s["best"] == {"cell": cid(2, 0), "net": 920.0} and s["worst"] == {"cell": cid(0, 31), "net": 520.0 - 28 * 31}
    saved = F.by(F.read(root / MADE / "rounds/1/build.json"))["2.1"]              # ... and they ARE line 2.1's, as the round saved it
    assert r["lines"] == [saved] and (s["share"], s["avg"], s["profitable"], s["variants"]) == (saved["number"], saved["avg"], saved["profitable"], saved["variants"])
    # ---- the same in one line for every place of the card: home, the neighbors in the card's order, the place it should NOT work
    P = {p["place"]: p for p in r["places"]}
    assert list(P) == ["home", "1", "2", "not_here"] and P["home"] == s
    mid = np.array([cell_net(vi, xi, "mid") for vi in range(4) for xi in range(32) if (vi, xi) != (0, 1)])
    five = np.array([cell_net(vi, xi, "nyam", "5") for vi in range(4) for xi in range(32)])
    assert (P["1"]["said"], P["1"]["table"], P["1"]["variants"], P["1"]["profitable"], P["1"]["avg"]) == ("midday", "NQ-tf15-mid", 127, int((mid > 0).sum()), float(mid.mean()))
    assert (P["2"]["said"], P["2"]["store"], P["2"]["variants"], P["2"]["profitable"], P["2"]["median"]) == (
        "5-minute bars", f"runs_made/{MADE}-NQ-tf5", 128, int((five > 0).sum()), float(np.median(five))) and (P["1"]["profitable"], P["2"]["profitable"]) == (75, 113)
    assert cell_net(2, 20, "mid") == 0.0 and one_is_not_money(P["1"])           # a variant that ends at exactly $0 does not make money: "above $0"
    assert (P["not_here"]["variants"], P["not_here"]["profitable"], P["not_here"]["share"], P["not_here"]["best"]) == (95, 10, 10 / 95, {"cell": cid(0, 0), "net": 200.0})
    # ---- any place has its own grid; a round is named by its number
    one, two, no = Q.heatmap(MADE, "1", root=root), Q.heatmap(MADE, 2, 1, root), Q.heatmap(MADE, "not-here", root=root)
    assert (one["place"], one["summary"], one["lines"], one["grid"]["net"][3][0]) == ("1", P["1"], [], cell_net(3, 0, "mid"))
    assert two["grid"]["net"] == [[cell_net(vi, xi, "nyam", "5") for xi in range(32)] for vi in range(4)] and two["not_judged"] == {"dead": [], "duplicates": []}
    assert (no["place"], no["grid"]["net"][1][5], no["summary"]["profitable"]) == ("not_here", cell_net(1, 5, "asia"), 10) and [p["place"] for p in no["places"]] == list(P)
    RESULTS["test_the_heat_map_is_one_row_a_value_and_one_column_an_exit_cell"] = (4 * 128, 4 * 128, "cells of 4 grids, each the net its store was typed with")


def mid_avg() -> float:
    return float(np.mean([cell_net(vi, xi, "mid") for vi in range(4) for xi in range(32) if (vi, xi) != (0, 1)]))


def mid_med() -> float:
    return float(np.median([cell_net(vi, xi, "mid") for vi in range(4) for xi in range(32) if (vi, xi) != (0, 1)]))


def test_the_heat_map_reads_well_in_a_chat():
    root = made()
    r = Q.heatmap(MADE, root=root)
    text = r["text"].split("\n")
    assert len(text) <= 60 and max(len(x) for x in text[2:35]) <= 60, (len(text), max(len(x) for x in text[2:35]))      # under 60 lines with 4 values; the grid is narrow
    assert text[0] == f"HEAT MAP of {MADE} · round 1 · HOME NQ New York morning 15-minute bars (NQ-tf15-nyam) · 4 named build days 2022-03-15 .. 2025-06-30"
    assert "$ thousands" in text[1] and "+ makes money" in text[1] and "- loses" in text[1]
    assert text[2].split() == ["or_min", "stop", "no", "target", "1R", "2R", "3R"]
    grid = text[3:3 + 32]                                                         # one line per value and stop, the 4 targets across
    assert [x.split()[0] for x in grid[::8]] == VALUES and [" ".join(x.split()[-6:-4]) for x in grid[:8]] == r["grid"]["stops"][::4]
    assert grid[0].split()[3:] == ["+0.5", "=", "+0.5", "+0.4"] and grid[1].split()[2:] == ["+0.4", "+0.4", "+0.4", "+0.3"]       # thousands; "=" a twin, judged once
    assert grid[4].split()[2:] == ["+0.1", "+0.0", "+0.0", "-0.0"] and grid[7].split()[2:] == ["-0.3"] * 4 and grid[23].split()[2:] == ["+0.1"] * 4 and grid[24].split()[3:] == ["."] * 4
    marks = [c for x in grid for c in x.split()[-4:]]
    assert sum(c.startswith("+") for c in marks) == 76 and sum(c.startswith("-") for c in marks) == 19 and marks.count("=") == 1 and marks.count(".") == 32
    rest, v = text[35:], np.array([cell_net(vi, xi) for vi, xi in JUDGED])
    assert rest[0] == f"MAKE MONEY: 76 of 95 variants (80 %) · average variant {k(v.mean())} · middle variant {k(np.median(v))}" and k(v.mean()) == "+$0.3k"
    assert rest[1].startswith(f"BEST CELL {cid(2, 0)} +$0.9k · WORST CELL {cid(0, 31)} -$0.3k") and "the law judges the average of all variants, never the best cell" in rest[1]
    assert rest[2] == "NOT COUNTED: 32 variants that cannot trade here (.) · 1 with the trades of another variant (=)"
    assert rest[3] == r["lines"][0]["text"] + "   <- line 2.1 of round 1, as the build saved it"
    assert rest[4].startswith("THE OTHER PLACES") and [x.split()[0] for x in rest[5:8]] == ["1", "2", "not_here"]
    assert "midday (NQ-tf15-mid): 75 of 127 variants make money (59.06 %)" in rest[5] and "5-minute bars (NQ-tf5-nyam): 113 of 128" in rest[6]
    assert "the Asian session (NQ-tf15-asia): 10 of 95 variants make money (10.53 %)" in rest[7] and rest[7].endswith("(the card says it should NOT work here; no line reads it)")
    assert rest[5].endswith(f"average {k(mid_avg())} · middle {k(mid_med())} · best +$0.6k · worst -$0.5k")
    assert len(rest) == 8 and "\n" not in r["next"] and "round 2" in r["next"]    # the idea's own next step: its build fails
    other = Q.heatmap(MADE, "2", root=root)["text"].split("\n")                   # another place: its own grid, and home among the other places
    assert other[0].startswith(f"HEAT MAP of {MADE} · round 1 · NEIGHBOR 2 \"5-minute bars\" NQ New York morning 5-minute bars (NQ-tf5-nyam)")
    assert [x.split()[0] for x in other[-3:]] == ["home", "1", "not_here"] and not [x for x in other if "line 2.1" in x] and len(other) <= 60
    assert other[-3].startswith("  home      NQ New York morning 15-minute bars (NQ-tf15-nyam): 76 of 95 variants make money (80 %)")


def test_the_heat_map_of_a_real_build_says_what_its_line_2_1_says():
    """bpl_orb, built for real on 3 build days and 2 exit cells: the grid is the store's, the summary is the saved line's."""
    root = F.fresh(NAME, "q_view")
    b, st = F.read(root / NAME / "rounds/1/build.json"), J.store({"dir": F.OUT, "key": KEY})
    before = files(root)
    with F.no_engine():
        r = Q.heatmap(NAME, root=root)
    g, s, line = r["grid"], r["summary"], F.by(b)["2.1"]
    assert (g["setting"], g["rows"], g["cols"], g["stops"], g["targets"]) == ("or_min", ["5", "15", "30"], ["atr3-r1", "pts20-r0"], ["atr 3", "pts 20"], ["1R", "no target"])
    for i, v in enumerate(g["rows"]):
        for j, x in enumerate(g["cols"]):
            assert g["cells"][i][j] == f"or_min{v}_{x}" and g["net"][i][j] == round(float(J.cellx(st, g["cells"][i][j], "nyam")["net"].sum()), 2)
    assert (s["share"], s["avg"], s["profitable"], s["variants"]) == (line["number"], line["avg"], line["profitable"], line["variants"]) and r["lines"] == [line]
    assert [p["place"] for p in r["places"]] == ["home", "1", "not_here"] and [p["table"] for p in r["places"]] == ["NQ-tf15-nyam", "NQ-tf15-mid", "NQ-tf15-asia"]
    assert [(p["variants"], p["avg"]) for p in r["places"][1:]] == [(x["variants"], x["avg_net"]) for x in (b["neighbors"][0], b["not_here"])]      # what the build showed
    assert (r["status"], r["round"], r["days"]["named"]) == ("lead", 1, F.DAYS) and "3 named build days" in r["text"].split("\n")[0] and files(root) == before
    text = r["text"].split("\n")                                                  # a table of 2 exit cells: the two stops, each with the one target it has
    assert text[2].split() == ["or_min", "stop", "no", "target", "1R"] and len(text[3:9]) == 6 and [x.split()[-3:-1] for x in text[4:9:2]] == [["pts", "20"]] * 3


# ================================================================ (c) what the views refuse, and that they write nothing

def test_what_the_views_refuse_and_that_they_write_nothing():
    root, n = made(), 0
    before, stores = files(root), files(MADE_OUT)

    def no(fn, word: str) -> str:
        nonlocal n
        n += 1
        with F.no_engine():
            return F.refused(fn, word)

    for view in (Q.heatmap, Q.mc):
        no(lambda: view("bpl_nobody", root=root), "no idea bpl_nobody")
        no(lambda: view("Not A Name", root=root), "name")
    bare = F.tmp() / "ideas" / "q_bare"                                           # carded, never built
    assert REC.card("bpl_bare", F.idea("bpl_bare"), bare)["ok"]
    was = files(bare)
    for view in (Q.heatmap, Q.mc):
        why = no(lambda: view("bpl_bare", root=bare), "run the build first")
        assert "no build on file" in why and "bp.py build bpl_bare --reason=" in why and files(bare) == was
    IS.write_reason("bpl_bare", 1, "started and never finished", bare)            # a round that was started and has no result is no build either
    was = files(bare)
    no(lambda: Q.heatmap("bpl_bare", root=bare), "run the build first")
    assert files(bare) == was
    for place in ("3", "0", "pm", "home2", ""):
        assert "home, 1, 2 or not_here" in no(lambda: Q.heatmap(MADE, place, root=root), f"place {place!r}")
    for rd in (2, 0, 6):
        assert "rounds with one: 1" in no(lambda: Q.heatmap(MADE, None, rd, root), f"round {rd} of {MADE} has no result")
    no(lambda: Q.mc(MADE, "sometimes", root), "build or test")
    why = no(lambda: Q.mc(MADE, "test", root), "no out-of-sample test on file")   # --on=test reads a test that was run: it runs none
    assert "bp.py test" in why and "runs nothing" in why
    # ---- a store that is gone, or one that is not of the build days, is refused by the reader's own seal
    gone = F.tmp() / "ideas" / "q_gone"
    shutil.copytree(root, gone)
    b = F.read(gone / MADE / "rounds/1/build.json")
    (gone / MADE / "rounds/1/build.json").write_text(json.dumps({**b, "stores": [{**s, "path": str(F.tmp() / "runs_nowhere" / s["key"])} for s in b["stores"]]}))
    for view in (Q.heatmap, Q.mc):
        no(lambda: view(MADE, root=gone), "no store runs_nowhere/")
    # ---- and reading left every file of both ideas as it was: no idea.json, no lock file, no log line
    with F.no_engine():
        Q.heatmap(MADE, root=root), Q.heatmap(MADE, "1", root=root), Q.mc(MADE, root=root), Q.mc(MADE, "build", root)
    assert files(root) == before and files(MADE_OUT) == stores and not (root / "_jobs").exists()
    RESULTS["test_what_the_views_refuse_and_that_they_write_nothing"] = (n, n, "refusals; no file changed")


# ================================================================ (b) the Monte Carlo

def slow(day, order) -> tuple:
    """A slow count of every run: (the final net, the WORST DRAWDOWN -- the largest fall of the run's P&L from its highest
    point so far, the start counting as a point) of each."""
    final, worst = [], []
    for run in order:
        pnl = high = fall = 0.0
        for i in run:
            pnl += day[i]
            high = max(high, pnl)
            fall = max(fall, high - pnl)
        final.append(pnl)
        worst.append(fall)
    return np.array(final), np.array(worst)


def test_the_runs_of_the_tables_are_the_runs_of_the_laws_line():
    mc = R.template("montecarlo")
    assert mc["view"] == {"command": "mc", "percentiles": PCT} and (mc["runs"], mc["seed"]) == (1000, 20261005)
    for days in (4, 7, 44):
        w, o = MC._fixed(days, mc["runs"], mc["seed"]), MC._order(days, mc["runs"], mc["seed"])
        assert o.shape == (1000, days) and np.array_equal(np.array([np.bincount(run, minlength=days) for run in o]).T, w)      # the same days, as often: only now in an order
        assert np.array_equal(o, MC._order.__wrapped__(days, mc["runs"], mc["seed"])) and not o.flags.writeable                 # the same order every time
    assert len({tuple(run) for run in MC._order(7, 1000, mc["seed"])}) > 900 and not np.array_equal(np.sort(o, axis=1), o)     # an order, not the calendar's
    net = np.array([[100.0, -50.0, 30.0, 10.0, -20.0, 5.0, 60.0], [-100.0, 50.0, -30.0, -10.0, 20.0, -5.0, -60.0]])
    h, (tot, _) = MC.histories(net), MC.reshuffle(net, np.ones_like(net))
    assert h.shape == (2, 1000, 7) and np.allclose(h.sum(2), tot) and np.array_equal(h[0], -h[1])       # the same days for every variant; a run's total is reshuffle()'s
    # ---- the eval card's drawdown, on lists whose answer is known
    cum, dd = EC.falls([[10.0, -30.0, 5.0, 40.0, -20.0], [-5.0, -5.0, 20.0, 1.0, 1.0], [1.0, 2.0, 3.0, 4.0, 5.0]])
    assert cum.tolist() == [[10, -20, -15, 25, 5], [-5, -10, 10, 11, 12], [1, 3, 6, 10, 15]] and dd.tolist() == [[0, 30, 30, 30, 30], [5, 10, 10, 10, 10], [0] * 5]
    final, worst = slow(net[0], MC._order(7, 1000, mc["seed"]))
    assert np.allclose(EC.falls(h[0])[0][:, -1], final) and np.allclose(EC.falls(h[0])[1][:, -1], worst)


def test_the_monte_carlo_tables_on_hand_made_days():
    """Q.tables on a table whose every day is typed: the percentiles are those of a slow count of the 1,000 runs."""
    net = np.array([[300.5, -100.25, 50.75, -40.5, 120.25, -60.75, 10.5], [100.1, -290.3, 90.7, 0.9, -20.2, 80.4, 30.6], [-10.3, 20.9, -30.7, 40.1, -50.3, 60.7, -70.9]])
    t = {"net": net, "n": np.ones_like(net), "ids": ["a", "b", "c"]}
    avg, dfl = Q.tables(t, "b", 0)
    order = MC._order(7, 1000, R.template("montecarlo")["seed"])
    for got, who, cell, day in ((avg, "average", None, net.mean(0)), (dfl, "default", "b", net[1])):
        final, worst = slow(day, order)
        assert not (np.abs(final) < 0.01).any()                                   # (no run ends within a cent of $0: "above $0" has one answer, however the days are added up)
        assert (got["variant"], got["cell"], got["percentiles"], got["runs"]) == (who, cell, PCT, 1000)
        assert np.allclose(got["net"], np.percentile(final, PCT)) and np.allclose(got["drawdown"], np.percentile(worst, PCT)) and got["above_zero"] == float((final > 0).mean())
        assert got["net"] == sorted(got["net"]) and got["drawdown"] == sorted(got["drawdown"]) and got["drawdown"][0] >= 0
    assert avg["above_zero"] == L.monte_test(t)["number"]                         # on a test this IS line 4.7's number: the same runs, the same question
    assert Q.tables(t, "b", 0) == [avg, dfl] and [x["variant"] for x in Q.tables(t, None, 0)] == ["average"] == [x["variant"] for x in Q.tables(t, "gone", 0)]
    up = Q.tables({"net": np.full((2, 5), 25.0), "n": np.ones((2, 5)), "ids": ["a", "b"]}, "a", 0)      # every day makes $25: no run falls, every run ends at $125
    assert all(x["net"] == [125.0] * 5 and x["drawdown"] == [0.0] * 5 and x["above_zero"] == 1.0 for x in up)
    down = Q.tables({"net": np.full((1, 5), -25.0), "n": np.ones((1, 5)), "ids": ["a"]}, "a", 0)        # every day loses $25: the fall is the whole run
    assert all(x["net"] == [-125.0] * 5 and x["drawdown"] == [125.0] * 5 and x["above_zero"] == 0.0 for x in down)


def test_the_monte_carlo_of_a_build_is_line_2_8_and_two_tables():
    root = made()
    t, (cell, n) = home_table(), middle()
    r = Q.mc(MADE, root=root)
    assert list(r)[:len(F.CONTRACT)] == list(F.CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "saved", "error")] == [True, "mc", MADE, "idea", 2, 1, None, [], None]
    # ---- the law's line: 2.8 with ITS OWN number -- the one the build saved, the one lines.monte gives the hand-made table
    saved = F.by(F.read(root / MADE / "rounds/1/build.json"))["2.8"]
    assert r["lines"] == [saved] == [L.monte(t)] and (saved["line"], saved["runs"], 0 < saved["number"] < 1) == ("2.8", 1000, True)
    assert (r["on"], r["default"], r["table"], r["days"]) == ("build", cell, {"store": f"runs_made/{MADE}-NQ-tf15", "variants": 95},
                                                              {"start": DAYS[0], "end": DAYS[-1], "sessions": 4, "named": DAYS})
    assert r["montecarlo"] == {"runs": 1000, "seed": 20261005, "draw": "whole days, with replacement, the same days for every variant", "percentiles": PCT}
    # ---- the two tables, held against a slow count of the same runs
    vi, xi = next(k for k in JUDGED if cid(*k) == cell)
    order = MC._order(4, 1000, 20261005)
    for got, who, c, day in zip(r["tables"], ("average", "default"), (None, cell), (t["net"].mean(0), np.array([usd(vi, xi, k) for k in range(4)]))):
        final, worst = slow(day, order)
        assert (got["variant"], got["cell"]) == (who, c) and np.allclose(got["net"], np.percentile(final, PCT)) and np.allclose(got["drawdown"], np.percentile(worst, PCT))
        assert got["above_zero"] == float((final > 0).mean())
    assert len(r["tables"]) == 2 and 0 < r["tables"][0]["above_zero"] < 1 and r["tables"][0]["drawdown"][0] == 0.0 < r["tables"][0]["drawdown"][-1]
    # ---- the same answer every time (a fresh generator with the fixed seed), with or without --on=build
    again = Q.mc(MADE, "build", root)
    assert json.dumps(again) == json.dumps(r) and json.loads(json.dumps(r))["tables"] == r["tables"]
    # ---- as a chat reads it
    text = r["text"].split("\n")
    assert text[0] == f"MONTE CARLO of {MADE} · round 1 · 4 named build days 2022-03-15 .. 2025-06-30 · home NQ New York morning 15-minute bars · 95 variants · 4 session days"
    assert text[1] == "1,000 reshuffled runs: whole days drawn with replacement, the same days for every variant, fixed seed 20261005."
    assert text[2] == saved["text"] and text[3].split() == ["5th", "25th", "50th", "75th", "95th", "percentile", "of", "the", "runs"]
    assert text[4] == "AVERAGE VARIANT (what the law judges)" and text[5].split()[:2] == ["final", "net"] and text[6].split()[:2] == ["worst", "drawdown"]
    assert text[7] == f"  ends above $0 in {100 * r['tables'][0]['above_zero']:.4g} % of the runs"
    assert text[8] == f"DEFAULT VARIANT {cell} (the middle of the {n} variants that made money on build; never the best)" and n == 76
    assert text[11] == f"  ends above $0 in {100 * r['tables'][1]['above_zero']:.4g} % of the runs"
    cols = lambda vals, sign: [("" if not sign else "+" if x > 0 else "-" if x < 0 else "") + f"${abs(x) / 1000:,.1f}k" for x in vals]  # noqa: E731
    assert text[5].split()[2:] == cols(r["tables"][0]["net"], True) and text[6].split()[2:] == cols(r["tables"][0]["drawdown"], False)
    assert text[12].startswith("HOW TO READ IT:") and len(text) == 13 and "\n" not in r["next"]
    RESULTS["test_the_monte_carlo_of_a_build_is_line_2_8_and_two_tables"] = (2, 2, f"tables against a slow count; line 2.8 = {saved['number']:.3f}, the saved number")


def test_the_monte_carlo_of_a_real_build_is_its_saved_line_2_8():
    root = F.fresh(NAME, "q_mc")
    b, before = F.read(root / NAME / "rounds/1/build.json"), files(root)
    r = Q.mc(NAME, root=root)
    line = F.by(b)["2.8"]
    assert (r["lines"][0]["number"], r["lines"][0]["runs"], r["lines"][0]["need"]) == (line["number"], 1000, 0.75) and r["default"] == b["default"]["cell"]
    assert (r["status"], r["round"], r["table"]["variants"], r["days"]["sessions"], r["days"]["named"]) == ("lead", 1, b["table"]["variants"], 3, F.DAYS)
    assert [x["variant"] for x in r["tables"]] == ["average", "default"] and r["tables"][1]["cell"] == b["default"]["cell"] and files(root) == before
    st = J.store({"dir": F.OUT, "key": KEY})                                      # the default's table against a slow count of its own three days
    x = J.cellx(st, r["default"], "nyam")
    day = np.array([float(x["net"][x["date"] == dt.date.fromisoformat(d).toordinal()].sum()) for d in F.DAYS])
    final, worst = slow(day, MC._order(3, 1000, 20261005))
    assert np.allclose(r["tables"][1]["net"], np.percentile(final, PCT)) and np.allclose(r["tables"][1]["drawdown"], np.percentile(worst, PCT))


def test_the_monte_carlo_of_a_test_is_line_4_7_and_is_refused_without_one():
    """--on=test reads a test that is ON FILE (its lock, its result, the store of its read): here an idea whose saved results
    are typed by hand (tests/blueprint_synth.py). Nothing is run, and nothing of an idea without a test is read."""
    root, folder, name = F.tmp() / "ideas" / "q_syn", F.tmp() / "runs_syn", "bpl_syn"
    days = SY.weekdays()
    cells = {"or_min5_pts20-r1": [SY.trade(d, 30.0 if i % 3 else -45.0) for i, d in enumerate(days)],
             "or_min15_pts20-r1": [SY.trade(d, 12.0 if i % 2 else -9.0) for i, d in enumerate(days[::2])],
             "or_min30_pts20-r1": [SY.trade(d, -4.0 if i % 4 else 55.0) for i, d in enumerate(days)]}
    SY.proven(IS, root, name, folder, cells)
    before = files(root)
    with F.no_engine():
        r = Q.mc(name, "test", root)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "saved")] == [True, "mc", name, "proven_on_history", 4, 1, []]
    ords = [dt.date.fromisoformat(d).toordinal() for d in days]
    net = np.array([[sum(t["net"] for t in rows if dt.date.fromisoformat(t["date"]).toordinal() == o) for o in ords] for rows in cells.values()])
    t = {"net": net, "n": (net != 0).astype(float), "ids": list(cells)}
    assert r["lines"] == [L.monte_test(t)] and r["lines"][0]["line"] == "4.7" and r["tables"] == Q.tables(t, "or_min5_pts20-r1", 0)
    assert r["tables"][0]["above_zero"] == r["lines"][0]["number"]                # the average variant's share above $0 IS line 4.7's number
    assert (r["on"], r["default"], r["lock"], r["days"]) == ("test", "or_min5_pts20-r1", SY.LOCK, {"start": SY.SPAN[0], "end": SY.SPAN[1], "sessions": len(days), "named": None})
    assert r["text"].split("\n")[0] == (f"MONTE CARLO of {name} · the out-of-sample test {SY.SPAN[0]} .. {SY.SPAN[1]} (lock {SY.LOCK}) · home NQ New York morning 15-minute bars "
                                        f"· 3 variants · {len(days)} session days") and files(root) == before
    assert "DEFAULT VARIANT or_min5_pts20-r1 (the lock's default variant)" in r["text"].split("\n")
    # ---- refused: no test on file (a lead; an idea that is frozen and not tested), a result of another lock, a store of another read
    lead = F.fresh(NAME, "q_mc_test")
    with F.no_engine():
        assert "no out-of-sample test on file" in F.refused(lambda: Q.mc(NAME, "test", lead), NAME)
        SY.proven(IS, root, "bpl_syn2", folder, cells, test_lock="0" * 16)
        F.refused(lambda: Q.mc("bpl_syn2", "test", root), "is of lock 0000000000000000")
        SY.proven(IS, root, "bpl_syn3", folder, cells, store_lock="f" * 16)
        F.refused(lambda: Q.mc("bpl_syn3", "test", root), "belongs to the read of another lock")
        d = SY.proven(IS, root, "bpl_syn4", folder, cells)
        IS.write_test("bpl_syn4", {**F.read(d / "test.json"), "dry_run": True}, root)
        F.refused(lambda: Q.mc("bpl_syn4", "test", root), "no out-of-sample test on file")


# ================================================================ (d) the early look

@contextlib.contextmanager
def reading(label: str, seen=None, **kw):
    """F.reading (a hand-made read: no test day is opened), and what was ON FILE when the pass started is kept in `seen`."""
    with F.reading(label, **kw):
        inner = RUN.run_test

        def run_test(name, rd, *a, **k):
            if seen is not None and not k.get("dry"):
                d = IS.idea_dir(name, k.get("ideas"))
                seen.append({"line": IS.read_on_file(name, root=k.get("ideas")), "early_lock": F.read(d / "early_look/lock.json") if (d / "early_look/lock.json").exists() else None,
                             "early_test": (d / "early_look/test.json").exists(), "idea": sorted(p.name for p in d.iterdir()), "out": str(a[7]), "read": dict(rd)})
            return inner(name, rd, *a, **k)

        RUN.run_test = run_test
        yield


def failing(root, lines=("2.2", "2.8"), check: bool = False) -> Path:
    """The lead of `root` as an idea whose BUILD FAILS -- its saved round rewritten by hand, no engine -- and, unless `check`,
    without its code check: what the owner's early look is for."""
    d = root / NAME
    b = F.read(d / "rounds/1/build.json")
    IS.write_build(NAME, 1, {**b, "lines": [{**x, "passed": False} if x["line"] in lines else x for x in b["lines"]], "failed": list(lines), "passed": False}, root)
    if not check:
        (d / "check.json").unlink()
    assert IS.status(NAME, root) == "idea"
    return d


def test_without_early_look_nothing_changes_and_the_refusal_names_it():
    root = F.fresh(NAME, "q_plain")
    d = root / NAME
    for make in (lambda: None, lambda: failing(root)):                           # a lead that is not frozen; an idea whose build fails
        make()
        before = files(root)
        with F.reading("q_plain"), F.no_engine():
            why = F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "not frozen")
            rc, js = F.run_cli(["test", NAME, "--confirm", f"--root={root}", "--json"])
        out = json.loads(js)
        assert "bp.py lock bpl_orb" in why and "EARLY LOOK" in why and f"bp.py test {NAME} --confirm --early-look" in why and "can never prove" in why
        assert rc == 2 and out["error"] == why and out["ok"] is False and list(out) == list(F.CONTRACT)
        assert files(root) == before and reads(root) == [] and not (d / "early_look").exists() and not F.read_out("q_plain").exists()


def test_what_an_early_look_refuses():
    root, n = F.fresh(NAME, "q_no"), 0
    d, out = root / NAME, F.read_out("q_no")

    def no(word: str, name: str = NAME, where=None, **kw) -> str:
        nonlocal n
        n += 1
        at = root if where is None else where
        with F.reading("q_no"), F.no_engine():
            why = F.refused(lambda: OOS.test(name, **{"confirm": True, "early_look": True, **kw}, root=at), word)
        assert reads(at) == [] and not (at / name / "early_look").exists() and not out.exists(), word      # no read was used, nothing was written
        return why

    no("no card", "bpl_nobody")
    for confirm in (False, None, "yes", 1):                                       # the owner has to have said so: warn first, run on his yes
        assert f"bp.py test {NAME} --confirm --early-look" in no("read ONCE", confirm=confirm)
    no("FIRST read", second_look=True)                                            # a second look at nothing
    bare = F.tmp() / "ideas" / "q_no_bare"
    assert REC.card("bpl_bare2", F.idea("bpl_bare2"), bare)["ok"]
    why = no("run the build first", "bpl_bare2", bare)                            # nothing is built: there is nothing to look at early
    assert "no build on file" in why and "bp.py build bpl_bare2 --reason=" in why
    spec = F.read(d / "spec.json")                                                # the card was changed after the round: its stores hold another rule
    (d / "spec.json").write_text(json.dumps({**spec, "run": {**spec["run"], "limits": {"max_tr": 1}}}))
    no("was changed after round 1")
    (d / "spec.json").write_text(json.dumps(spec))
    jd = root / "_jobs" / "20260101T000000-abc123"                                # a job of the idea is at work
    jd.mkdir(parents=True)
    (jd / "job.json").write_text(json.dumps({"id": jd.name, "command": "test", "name": NAME, "state": "running", "pid": os.getpid(), "args": {}}))
    assert jd.name in no("still running")
    shutil.rmtree(root / "_jobs")
    frozen, _ = F.frozen(NAME, "q_no_frozen")                                     # a FROZEN idea has its proper test: an early look is for one that is not
    why = no("is frozen", where=frozen)
    assert "NOT frozen" in why and f"bp.py test {NAME} --confirm" in why and not why.rstrip(")").endswith("--early-look")
    RESULTS["test_what_an_early_look_refuses"] = (n, n, "refusals: nothing run, no read used")


def _early(label: str, make=None, **kw) -> tuple:
    """ONE early look of bpl_orb in a root of its own -> (root, the result, what was on file when the pass started)."""
    if label not in _T:
        root, seen = F.fresh(NAME, label), []
        if make:
            make(root)
        before = files(root / NAME)
        with reading(label, seen, **kw):
            r = OOS.test(NAME, confirm=True, early_look=True, root=root)
        _T[label] = (root, r, seen, before)
    return _T[label]


def test_an_early_look_claims_the_read_first_and_freezes_what_is_there():
    root, r, seen, before = _early("q_idea", failing)
    d, s = root / NAME, seen[0]
    lock, proper = F.read(d / "early_look/lock.json"), F.frozen(NAME, "q_keys")[1]
    rng = {"start": "2025-07-01", "end": lock["test_range"]["NQ"]["end"]}
    # ---- THE CLAIM came first: when the pass started the read was in the one-read log, claimed for THIS lock and its range -- as a test's
    assert len(seen) == 1 and (s["line"]["state"], s["line"]["name"], s["line"]["version"], s["line"]["lock"], s["line"]["range"], s["line"]["verdict"]) == (
        "claimed", NAME, 1, lock["hash"], rng, None) and set(s["line"]) == {"utc", "name", "version", "lock", "range", "state", "verdict"}
    assert s["early_lock"] == lock and s["early_test"] is False and s["read"] == {"version": 1, "lock": lock["hash"], "utc": s["line"]["utc"]}
    assert s["out"] == str(F.read_out("q_idea")) and OOS.EARLY_OUT == LB.W / "runs_bp_early" != RUN.TESTS      # its stores: never among those of THE one read
    log = reads(root)
    assert [(x["state"], x["lock"], x["range"]) for x in log] == [("claimed", lock["hash"], rng), ("judged", lock["hash"], rng)] and log[0] == s["line"]
    ev = [x for x in events(d) if x["event"].startswith("test")]
    assert [(x["event"], x["early_look"], x["lock"]) for x in ev] == [("test_claimed", True, lock["hash"]), ("tested", True, lock["hash"])]
    # ---- THE LOCK: what was there, frozen as it was, MARKED -- the build lines that failed, the code check that is missing
    assert set(proper) < set(lock) and set(lock) - set(proper) == {"early_look", "build_failed", "code_check"} and list(lock)[-1] == "hash"
    assert (lock["early_look"], lock["build_failed"], lock["code_check"]["missing"]) == (True, ["2.2", "2.8"], True) and "no code check on file" in lock["code_check"]["why"]
    assert lock["hash"] == FRZ.digest(lock) != proper["hash"] and (lock["name"], lock["version"], lock["round"], lock["store"]) == (NAME, 1, 1, NAME)
    assert all(lock[k] == proper[k] for k in ("spec", "plan", "variants", "control", "montecarlo", "code")) and lock["test_range"] == {"NQ": proper["test_range"]["NQ"]}
    assert lock["home"] == {**proper["home"], "worse": None} and list(lock["stores"]) == [KEY, "c1-NQ-tf15"] and lock["stores"][KEY] == proper["stores"][KEY]
    st = J.store({"dir": F.OUT, "key": KEY})                                      # no worse-fills table of the build days was run for it: the default is the build's own
    sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
    rows = J.table(st, T.bp_unit(sp, "NQ", "15", "nyam"))
    assert (lock["default"], lock["survivors"]) == REC.middle(rows, lock["variants"]) and lock["default_rule"].startswith("the middle of the variants that made money on BUILD")
    assert lock["costs"] == {"normal": R.template("costs")["normal"], "worse": {"slip_ticks": 2.0, "latency_ms": 250, "oco_cancel_ms": 100, "two_sided": True}}
    # ---- the idea's OWN lock and test were never written: it is not frozen, and the app's idea store has nothing to count
    assert sorted(set(files(d)) - set(before)) == ["early_look/lock.json", "early_look/test.json"] and not (d / "lock.json").exists() and not (d / "test.json").exists()
    assert s["idea"] == sorted({p.split("/")[0] for p in before} | {"early_look"})
    RESULTS["test_an_early_look_claims_the_read_first_and_freezes_what_is_there"] = (2, 2, "lines of the one-read log: claimed before the pass, then judged")


def test_an_early_look_is_labelled_everywhere():
    root, r, seen, _ = _early("q_idea", failing)
    d = root / NAME
    lock, saved = F.read(d / "early_look/lock.json"), F.read(d / "early_look/test.json")
    assert OOS.EARLY == EARLY and A.EARLY_LOOK == "early_look"
    assert list(r)[:len(F.CONTRACT)] == list(F.CONTRACT)
    assert [r[k] for k in ("ok", "command", "name", "status", "phase", "round", "job", "error")] == [True, "test", NAME, "idea", 4, 1, None, None]
    # 1. every line 4.1-4.9 is read, and each says so in its own text
    assert [x["line"] for x in r["lines"]] == F.TEST_LINES and all(x["early_look"] is True and x["text"].endswith(f" [{EARLY}]") and type(x["passed"]) is bool for x in r["lines"])
    assert F.by(r)["4.1"]["text"] == f"4.1 PASS Jul-Dec 2025 $600 · Jan-Sep 2026 $600, average variant (need each above $0) [{EARLY}]"
    # 2. the result: early_look, the label, a verdict that is no verdict of the law, never a pass
    assert (r["early_look"], r["label"], r["verdict"], r["held"], r["failed"], r["passed"], r["second_look"], r["dry_run"]) == (
        True, EARLY, f"{EARLY}: every line 4.1-4.9 holds", True, [], False, False, False)
    assert (r["build_failed"], r["code_check"], r["lock"], r["version"]) == (["2.2", "2.8"], lock["code_check"], lock["hash"], 1)
    # 3. the text a person reads: the first line, the result, the status, the next step
    text = r["text"].split("\n")
    assert text[0] == (f"{EARLY}. NOT the law's test: {NAME} is not frozen -- build lines 2.2, 2.8 failed in round 1; no code check stands for its home store. "
                       "An early look can never prove an idea.")
    assert text[1].startswith("TEST RUN on") or text[1].startswith("OUT-OF-SAMPLE TEST 2025-07-01")
    assert text[2].startswith(f"{NAME} · early-look lock {lock['hash']} · version 1 · home NQ New York morning 15-minute bars · {len(lock['variants'])} locked variants")
    assert text[3:12] == [x["text"] for x in r["lines"]]
    assert text[12] == f"RESULT: {EARLY}: every line 4.1-4.9 holds -- no pass and no fail of the law: an early look proves nothing, and for {NAME} the test days are no longer unseen."
    assert text[13] == f"STATUS: IDEA (as it was: an early look changes no status) · the test days are USED for {NAME}"
    assert r["next"].startswith(f"{EARLY}: ") and "SECOND LOOK" in r["next"] and f"bp.py test {NAME} --confirm --second-look" in r["next"] and "\n" not in r["next"]
    # 4. what is saved: early_look/test.json -- early_look true, the label, every line -- and the read's verdict in the one-read log
    assert (saved["early_look"], saved["label"], saved["verdict"], saved["passed"], saved["status"]) == (True, EARLY, r["verdict"], False, "idea")
    assert saved["lines"] == json.loads(json.dumps(r["lines"])) and saved["next"] == r["next"] and saved["default"] == r["default"]
    assert reads(root)[-1]["verdict"] == r["verdict"] and r["read"] == {**seen[0]["read"], "state": "judged", "verdict": r["verdict"]}
    assert [x["verdict"] for x in events(d) if x["event"] == "tested"] == [r["verdict"]]
    assert sorted(Path(p).name for p in r["saved"]) == sorted([*RUN.test_keys(KEY, NAME, "NQ", "15", "nyam").values(), "test.json", "lock.json", "test_reads.jsonl"])
    assert str(d / "early_look/test.json") in r["saved"] and str(d / "early_look/lock.json") in r["saved"] and str(d / "test.json") not in r["saved"]
    # 5. the default variant's test trades in the tester, when the app's Python is there: the run is named an early look
    dv = r["default"]
    assert dv["cell"] == lock["default"] and dv["trades"] == 8
    if F.APP_PYTHON.exists():
        meta = F.read(F.TESTER / "runs" / dv["run_id"] / "run.json")
        assert "TEST (EARLY LOOK)" in meta["strategy"]["name"] and EARLY in meta["imported"]["note"] and lock["hash"] in meta["imported"]["note"]
    # 6. `status` shows it: the read with its verdict, the seven lines -- under the idea's own status and its build's next step
    s = REC.status(NAME, root)
    assert (s["status"], s["phase"], s["record"]["read"]["verdict"]) == ("idea", 2, r["verdict"]) and s["record"]["early_look"] == {
        "verdict": r["verdict"], "label": EARLY, "held": True, "failed": [], "lock": lock["hash"], "range": r["range"], "build_failed": ["2.2", "2.8"]}
    assert f"TEST DAYS READ · judged {reads(root)[-1]['utc']} · {r['verdict']}" in s["text"].split("\n") and all("  " + x["text"] in s["text"].split("\n") for x in r["lines"])
    assert [x["line"] for x in s["lines"]] == [f"2.{i}" for i in range(1, 10)] and "round 2" in s["next"]      # the idea's latest verdict is still its build
    RESULTS["test_an_early_look_is_labelled_everywhere"] = (7, 7, "lines labelled EARLY LOOK, + the result, the text, early_look/test.json, the log, the tester run")


def test_an_early_look_never_makes_an_idea_proven():
    """THE STATUS IS NEVER PROVEN: seven lines that all hold, for an idea whose build fails AND for a lead that is only not
    frozen -- the app's idea store reads the saved results as it did before, and phase 5 has no test to stand on."""
    cases = (("q_idea", failing, "idea", "Ideas", 2), ("q_lead", None, "lead", "Leads", 2))
    for label, make, status, group, phase in cases:
        root, r, _, _ = _early(label, make)
        d = root / NAME
        assert r["held"] is True and [x["passed"] for x in r["lines"]] == [True] * 9                  # everything held ...
        got = IS.read_idea(NAME, root)
        assert r["status"] == IS.status(NAME, root) == got["status"] == status and (got["group"], got["phase"]) == (group, phase)      # ... and nothing moved
        assert not (d / "test.json").exists() and not (d / "lock.json").exists() and [x["line"][:2] for x in got["lines"]] == ["2."] * 9
        assert "PROVEN ON HISTORY" not in json.dumps(r, ensure_ascii=False) and "proven" not in json.dumps([got, IS.list_ideas(root)])
        assert not [x for x in events(d) if x["event"] == "status" and "proven" in str(x.get("now"))]
        assert f"its out-of-sample test is not on file" in F.refused(lambda: PO.proven(NAME, root), NAME)      # the prop simulator: refused
        with F.no_engine():
            assert "no out-of-sample test on file" in F.refused(lambda: Q.mc(NAME, "test", root), "early look")
    # ---- a lead's result says why it was an early look: its build passed, it was only not frozen
    root, r, _, _ = _early("q_lead")
    lock = F.read(root / NAME / "early_look/lock.json")
    assert (lock["build_failed"], lock["code_check"]) == ([], {"missing": False, "why": None}) and r["status"] == "lead"
    assert "every build line of round 1 passed, and it was never frozen (bp.py lock)" in r["text"].split("\n")[0]
    # ---- the build passes LATER (here: its saved round put back by hand): a lead, with its test days used -- never proven by the early look
    root, r, _, _ = _early("q_later", failing)
    b = F.read(root / NAME / "rounds/1/build.json")
    IS.write_build(NAME, 1, {**b, "lines": [{**x, "passed": None if x["line"] == "2.7" else True} for x in b["lines"]], "failed": [], "passed": True}, root)
    assert IS.status(NAME, root) == "lead" == IS.sync(NAME, root)["idea"]["status"] and IS.read_idea(NAME, root)["group"] == "Leads"
    # ---- lines that do NOT hold shelve nothing either: an early look is no fail of the law
    root, r, _, _ = _early("q_bad", None, net=lambda cell, i, day: 150.0 if day < "2026" else -200.0, worse=lambda cell, i, day: -10.0)
    assert {"4.1", "4.2", "4.5", "4.6"} <= set(r["failed"]) and (r["held"], r["passed"], r["verdict"]) == (False, False, f"{EARLY}: fails {', '.join(r['failed'])}")
    assert r["status"] == IS.status(NAME, root) == "lead" and IS.read_idea(NAME, root)["group"] == "Leads" and "A FAIL IS FINAL" not in r["text"]
    assert f"RESULT: {EARLY}: fails {', '.join(r['failed'])} -- no pass and no fail of the law" in r["text"]
    RESULTS["test_an_early_look_never_makes_an_idea_proven"] = (4, 4, "early looks (2 that hold, 1 that does not, 1 whose build passes later): the status never moved")


def test_after_an_early_look_a_proper_test_is_refused_as_used():
    root, r, _, _ = _early("q_after")
    d, early = root / NAME, F.read(root / NAME / "early_look/lock.json")
    # ---- the same early look again: THE read of that lock is over, whatever is added
    for kw in ({}, {"second_look": True}):
        with reading("q_after"), F.no_engine():
            why = F.refused(lambda kw=kw: OOS.test(NAME, confirm=True, early_look=True, root=root, **kw), "already on file")
        assert "EARLY LOOK" in why and "read once" in why and len(reads(root)) == 2 and F.read(d / "early_look/lock.json") == early
    # ---- the idea goes on: it is frozen properly (its build passed, its code check stands) ...
    with F.tiny():
        lock = FRZ.lock(NAME, root)["lock"]
    assert lock["hash"] != early["hash"] and "early_look" not in lock and IS.status(NAME, root) == "lead"
    step = REC.status(NAME, root)["next"]
    assert "test days are USED" in step and f"bp.py test {NAME} --confirm --second-look" in step and "SECOND LOOK" in step
    # ---- ... and its proper test is REFUSED AS USED
    with F.reading("q_after_2"), F.no_engine():
        why = F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "already on file")
        rc, js = F.run_cli(["test", NAME, "--confirm", f"--root={root}", "--json"])
    assert EARLY in why and "read once" in why and "--second-look" in why and "SECOND LOOK everywhere" in why
    assert rc == 2 and json.loads(js)["error"] == why and len(reads(root)) == 2 and not (d / "test.json").exists() and not F.read_out("q_after_2").exists()
    # ---- --second-look is the only way past, and it is labelled so: a proper read of a frozen idea, into the stores of THE one read
    seen: list = []
    with reading("q_after_2", seen):
        r2 = OOS.test(NAME, confirm=True, second_look=True, root=root)
    assert (r2["second_look"], r2["label"], r2["verdict"], r2["status"]) == (True, "SECOND LOOK", "SECOND LOOK: PROVEN ON HISTORY", "proven_on_history") and "early_look" not in r2
    assert all(x["text"].endswith(" [SECOND LOOK]") and "early_look" not in x for x in r2["lines"]) and r2["text"].startswith(f"SECOND LOOK: not a first read")
    assert seen[0]["out"] == str(F.read_out("q_after_2")) != str(F.read_out("q_after")) and seen[0]["line"]["second_look"] is True
    assert [(x["state"], x["lock"]) for x in reads(root)] == [("claimed", early["hash"]), ("judged", early["hash"]), ("claimed", lock["hash"]), ("judged", lock["hash"])]
    assert F.read(d / "test.json")["verdict"] == r2["verdict"] and F.read(d / "early_look/test.json")["verdict"] == r["verdict"]      # both stay on file
    assert REC.status(NAME, root)["record"]["early_look"]["lock"] == early["hash"]
    # ---- an idea whose build fails cannot be frozen: its proper test stays "not frozen", and a second early look is refused as used
    root, r, _, _ = _early("q_bad_build", failing)
    with reading("q_bad_build_2"), F.no_engine():
        F.refused(lambda: FRZ.lock(NAME, root), "fails 2.2, 2.8")
        F.refused(lambda: OOS.test(NAME, confirm=True, root=root), "not frozen")
        F.refused(lambda: OOS.test(NAME, confirm=True, early_look=True, root=root), "already on file")
    assert len(reads(root)) == 2


def test_an_early_look_of_a_changed_idea_is_a_second_look_and_says_both():
    """After an early look the idea is not frozen: it may change. A changed idea has another lock -- its early look is
    refused as used, and with --second-look it runs and carries BOTH labels."""
    root, r, _, _ = _early("q_twice", failing)
    d, first = root / NAME, F.read(root / NAME / "early_look/lock.json")
    b = F.read(d / "rounds/1/build.json")                                         # the round now fails another line: the idea is not what was looked at
    IS.write_build(NAME, 1, {**b, "lines": [{**x, "passed": False} if x["line"] == "2.4" else x for x in b["lines"]], "failed": ["2.2", "2.4", "2.8"]}, root)
    with reading("q_twice_2"), F.no_engine():
        why = F.refused(lambda: OOS.test(NAME, confirm=True, early_look=True, root=root), "already on file")
    assert "--second-look" in why and len(reads(root)) == 2 and F.read(d / "early_look/lock.json") == first
    with reading("q_twice_2"):
        r2 = OOS.test(NAME, confirm=True, early_look=True, second_look=True, root=root)
    lock = F.read(d / "early_look/lock.json")
    assert lock["hash"] != first["hash"] and lock["build_failed"] == ["2.2", "2.4", "2.8"] and r2["lock"] == lock["hash"]
    assert (r2["label"], r2["verdict"], r2["early_look"], r2["second_look"], r2["status"]) == (
        f"SECOND LOOK · {EARLY}", f"SECOND LOOK: {EARLY}: every line 4.1-4.9 holds", True, True, "idea")
    assert all(x["text"].endswith(f" [SECOND LOOK] [{EARLY}]") and x["early_look"] is True and x["second_look"] is True for x in r2["lines"])
    assert r2["text"].split("\n")[0].startswith(f"{EARLY}. ") and r2["text"].split("\n")[1].startswith("SECOND LOOK: not a first read")
    assert [x.get("second_look") for x in reads(root)] == [None, None, True, None] and not (d / "test.json").exists() and IS.status(NAME, root) == "idea"


def test_an_early_look_uses_the_test_days_up_for_the_ideas_relatives_too():
    """bpl_orb and bpl_two: the same entry trigger on the same market and session -- one idea under two names. An early look
    of the first is a read of the test days for the second: its proper test and its own early look are refused as used."""
    root = F.fresh(NAME, "q_rel", "bpl_two")
    with reading("q_rel"):
        r = OOS.test(NAME, confirm=True, early_look=True, root=root)
    with reading("q_rel_2"), F.no_engine():
        why = F.refused(lambda: OOS.test("bpl_two", confirm=True, early_look=True, root=root), "same-idea relative of bpl_two")
    assert "the idea bpl_orb" in why and r["verdict"] in why and "bp.py test bpl_two --confirm --early-look --second-look" in why and not (root / "bpl_two" / "early_look").exists()
    with F.tiny():
        lock = FRZ.lock("bpl_two", root)["lock"]
    with F.reading("q_rel_2"), F.no_engine():
        why = F.refused(lambda: OOS.test("bpl_two", confirm=True, root=root), "same-idea relative of bpl_two")
        use = READS.used("bpl_two", lock, root)
    assert "the idea bpl_orb" in why and "the same entry trigger, market and session (orb, NQ, New York morning)" in why and EARLY in why and "--second-look" in why
    assert use["own"] is None and [(x["name"], x["kind"], x["state"], x["verdict"]) for x in use["relatives"]] == [(NAME, "idea", "judged", r["verdict"])]
    assert len(reads(root)) == 2 and not (root / "bpl_two" / "test.json").exists() and not F.read_out("q_rel_2").exists()


def test_a_pass_that_fails_leaves_the_early_look_on_file():
    root = F.fresh(NAME, "q_crash")
    d = failing(root)
    with reading("q_crash", fail=J.Refuse("planted: the pass fails")):
        why = F.refused(lambda: OOS.test(NAME, confirm=True, early_look=True, root=root), "planted: the pass fails")
    lock = F.read(d / "early_look/lock.json")
    assert "THE READ STAYS ON FILE" in why and [(x["state"], x["lock"]) for x in reads(root)] == [("claimed", lock["hash"])] and not (d / "early_look/test.json").exists()
    assert [x["event"] for x in events(d)][-2:] == ["test_claimed", "test_did_not_finish"] and IS.status(NAME, root) == "idea"
    for kw in ({}, {"second_look": True}):                                        # the same idea, a moment or an hour later: the same lock, and its read is on file
        with reading("q_crash"), F.no_engine():
            again = F.refused(lambda kw=kw: OOS.test(NAME, confirm=True, early_look=True, root=root, **kw), "already on file")
        assert "the run did not finish" in again and F.read(d / "early_look/lock.json") == lock and len(reads(root)) == 1
    assert "TEST DAYS READ · claimed" in REC.status(NAME, root)["text"]


# ================================================================ (e) the command lines

def test_the_command_lines_of_the_three():
    root, lead = made(), F.fresh(NAME, "q_cmd")
    last = [f"--root={root}", "--json"]
    with F.no_engine():
        for argv, cmd, word in ((["heatmap", "bpl_nobody"], "heatmap", "no idea"), (["heatmap", MADE, "--place=7"], "heatmap", "place '7'"), (["heatmap"], "heatmap", "name"),
                                (["heatmap", MADE, "--round=two"], "heatmap", "--round"), (["mc", MADE, "--on=never"], "mc", "--on"), (["mc", MADE, "--on=test"], "mc", "no out-of-sample test"),
                                (["mc", MADE, "--place=1"], "mc", "unrecognized"), (["heatmap", MADE, "--days=2024-03-15"], "heatmap", "unrecognized")):
            rc, js = F.run_cli([*argv, *last])
            d = json.loads(js)
            assert rc == 2 and list(d) == list(F.CONTRACT) and d["ok"] is False and word in d["error"] and (d["command"], d["lines"], d["saved"]) == (cmd, [], []), (argv, d)
        rc, js = F.run_cli(["heatmap", MADE, "--place=1", "--round=1", *last])
        d = json.loads(js)
        assert rc == 0 and js.count("\n") == 1 and (d["command"], d["place"], d["round"], d["phase"]) == ("heatmap", "1", 1, 2) and d == json.loads(json.dumps(Q.heatmap(MADE, "1", 1, root)))
        rc, js = F.run_cli(["mc", MADE, "--on=build", *last])
        assert rc == 0 and json.loads(js) == json.loads(json.dumps(Q.mc(MADE, "build", root))) and js.isascii()
        for argv, head in ((["heatmap", MADE], "HEAT MAP of"), (["mc", MADE], "MONTE CARLO of")):       # a person: the text, and the idea's next step
            rc, txt = F.run_cli([*argv, f"--root={root}"])
            assert rc == 0 and txt.startswith(head) and txt.rstrip("\n").split("\n")[-1].startswith("NEXT: ") and len(txt.rstrip("\n").split("\n")) <= 60
    # ---- the front door, as the connector starts it: bp.py in its own process, ONE JSON object on stdout
    rc, d = F.bp(["heatmap", MADE, "--place=not_here", *last])
    assert rc == 0 and (d["command"], d["place"], d["summary"]["profitable"], len(d["grid"]["cols"])) == ("heatmap", "not_here", 10, 32)
    rc, d = F.bp(["mc", MADE, *last])
    assert rc == 0 and d["lines"] == json.loads(json.dumps(Q.mc(MADE, root=root)["lines"])) and d["tables"] == Q.mc(MADE, root=root)["tables"]
    rc, d = F.bp(["mc", "bpl_nobody", *last])
    assert rc == 2 and d["ok"] is False and "no idea" in d["error"]
    # ---- test <name> --confirm --early-look
    last = [f"--root={lead}", "--json"]
    with reading("q_cmd"):
        with F.no_engine():
            rc, js = F.run_cli(["test", NAME, "--early-look", *last])           # the owner's yes is --confirm: without it nothing happens
            assert rc == 2 and json.loads(js)["error"].startswith("the test days are read ONCE") and reads(lead) == [] and not (lead / NAME / "early_look").exists()
        rc, js = F.run_cli(["test", NAME, "--confirm", "--early-look", *last])
        d = json.loads(js)
        assert rc == 0 and list(d)[:len(F.CONTRACT)] == list(F.CONTRACT) and (d["command"], d["early_look"], d["label"], d["status"], d["phase"]) == ("test", True, EARLY, "lead", 4)
        assert js.isascii() and js.count("\n") == 1 and len(reads(lead)) == 2 and [x["line"] for x in d["lines"]] == F.TEST_LINES
        with F.no_engine():
            rc, txt = F.run_cli(["test", NAME, "--confirm", "--early-look", f"--root={lead}"])
            assert rc == 2 and txt.startswith("REFUSED: a read of the test days is already on file") and "EARLY LOOK" in txt
            rc, txt = F.run_cli(["status", NAME, f"--root={lead}"])
            assert rc == 0 and txt.startswith(f"{NAME} · LEAD · phase 2") and f"TEST DAYS READ · judged" in txt and EARLY in txt
    # ---- as a job (--wait): the command claims the read, and the job's own call is the same run -- here in this process, on the hand-made read
    job = F.fresh(NAME, "q_job")
    with reading("q_job"):
        kw = json.loads(json.dumps(OOS.start(NAME, True, root=job, early_look=True)))      # (a job keeps its arguments as JSON)
        assert kw["early_look"] is True and kw["out"] == str(F.read_out("q_job")) and [x["state"] for x in reads(job)] == ["claimed"]
        r = JOBS.COMMANDS["test"](**kw, progress=None)
    assert (r["early_look"], r["label"], r["status"]) == (True, EARLY, "lead") and [x["state"] for x in reads(job)] == ["claimed", "judged"]


def test_the_help_names_the_three():
    import bp
    from blueprint import cli as C
    for doc in (bp.__doc__, C.__doc__):
        for word in ("bp.py heatmap <name>", "--place=home|1|2|..|not_here", "--round=N", "bp.py mc <name>", "--on=build|test", "--early-look", "EARLY LOOK"):
            assert word in doc, word
    assert A.PHASE["heatmap"] == A.PHASE["mc"] == 2 and C._parser().parse_args(["test", "x", "--confirm", "--early-look"]).early_look is True
    assert C._parser().parse_args(["test", "x", "--confirm"]).early_look is False


CONNECTOR = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from homebase.claude_mcp import blueprint_tools, tools
from homebase.claude_mcp.client import Client, ToolError
box = tools.Toolbox(Client("http://127.0.0.1:1"), sleep=lambda s: None)
out = []
for tool, args in json.loads(sys.argv[2]):
    try:
        out.append(box.call(tool, args))
    except ToolError as e:
        out.append("ToolError: " + str(e))
out.append(blueprint_tools._report(json.load(open(sys.argv[3]))))      # a finished early look as the tool words it (its result object, from the toolkit)
print(json.dumps(out))
'''


def test_the_apps_connector_against_this_toolkit():
    """homebase/claude_mcp/blueprint_tools.py (the app's Python) starts THIS bp.py. blueprint_heatmap and blueprint_mc answer
    with the views' own text. blueprint_test with early_look is asked ONLY where it is refused before anything is read:
    without the owner's word (the tool's own refusal), and for an idea whose early look is on file (the toolkit's: used).
    The read it words at the end was made in this process, by hand. No test day can be opened: the one day the toolkit's
    child could name is a Sunday."""
    if not F.APP_PYTHON.exists():
        import pytest
        pytest.skip(f"the app's Python is not there: {F.APP_PYTHON}")
    root = F.tmp() / "ideas" / "q_app"
    shutil.copytree(made() / MADE, root / MADE)
    shutil.copytree(F.lead(NAME) / NAME, root / NAME)
    with reading("q_app"):
        r = OOS.test(NAME, confirm=True, early_look=True, root=root)             # (a hand-made read, in this process: the idea's early look is on file)
    done = F.tmp() / "an_early_look.json"
    done.write_text(json.dumps(r))
    calls = [("blueprint_heatmap", {"name": MADE}), ("blueprint_heatmap", {"name": MADE, "place": 2, "round": 1}), ("blueprint_heatmap", {"name": MADE, "place": "not_here"}),
             ("blueprint_heatmap", {"name": MADE, "place": 7}), ("blueprint_heatmap", {"name": MADE, "round": 3}), ("blueprint_mc", {"name": MADE}),
             ("blueprint_mc", {"name": MADE, "on": "test"}), ("blueprint_test", {"name": NAME, "confirm": False, "early_look": True}),
             ("blueprint_test", {"name": NAME, "confirm": True}), ("blueprint_test", {"name": NAME, "confirm": True, "early_look": True, "wait_s": 30}),
             ("blueprint_status", {"name": NAME})]
    drafts, out = F.tmp() / "drafts_q_app", F.tmp() / "runs_test_q_app_child"      # (where a read of the toolkit's child would go: it must stay empty)
    env = {**os.environ, "HOMEBASE_IDEAS_ROOT": str(root), "HOMEBASE_DRAFTS_DIR": str(drafts), "HOMEBASE_BP": str(F.W / "bp.py"), "HOMEBASE_BP_PYTHON": sys.executable,
           REC.TEST_RUN: json.dumps({**F.TINY, "test_days": ["2025-07-06"], "test_out": str(out)})}      # (a Sunday: no session, so nothing of the test days could be opened)
    q = subprocess.run([str(F.APP_PYTHON), "-B", "-c", CONNECTOR, str(S.REPO), json.dumps(calls), str(done)], capture_output=True, text=True, timeout=900, cwd=str(F.tmp()), env=env)
    assert q.returncode == 0, q.stderr[-2000:]
    heat, two, nowhere, bad_place, bad_round, mc, mc_test, unconfirmed, plain, again, status, worded = json.loads(q.stdout)
    _T["blueprint_heatmap"], _T["blueprint_mc"], _T["blueprint_test (an early look, as the tool words it)"] = heat, mc, worded
    # ---- the two views: the toolkit's text under the tool's head, the idea's next step, nothing saved
    text = Q.heatmap(MADE, root=root)["text"]
    assert heat.split("\n")[0] == f"Blueprint heatmap · {MADE} · IDEA · phase 2 · round 1" and text in heat and heat.count("Next: ") == 1 and "Saved: " not in heat
    assert "Lines: 1 passed · 0 FAILED" in heat and "MAKE MONEY: 76 of 95 variants (80 %)" in heat
    assert "NEIGHBOR 2 \"5-minute bars\"" in two.split("\n")[1] and "NOT HERE \"the Asian session\"" in nowhere.split("\n")[1] and "Lines: " not in two
    assert bad_place.startswith("ToolError: Refused (blueprint heatmap): place '7': home, 1, 2 or not_here") and "Nothing was run." in bad_place
    assert bad_round.startswith(f"ToolError: Refused (blueprint heatmap): round 3 of {MADE} has no result on file")
    assert mc.split("\n")[0] == f"Blueprint mc · {MADE} · IDEA · phase 2 · round 1" and Q.mc(MADE, root=root)["text"] in mc and "Lines: 0 passed · 1 FAILED (2.8)" in mc
    assert mc_test.startswith(f"ToolError: Refused (blueprint mc): {MADE} has no out-of-sample test on file") and "Saved: " not in mc
    # ---- the early look: never without the owner's word; an idea that is not frozen is told it may ask for one; a second one is refused as used
    assert unconfirmed.startswith("ToolError: confirm: must be true") and "early look" in unconfirmed
    assert plain.startswith(f"ToolError: Refused (blueprint test): {NAME} is not frozen") and f"bp.py test {NAME} --confirm --early-look" in plain and "Nothing was run." in plain
    assert again.startswith(f"ToolError: Refused (blueprint test): a read of the test days is already on file for {NAME}") and r["verdict"] in again and "Nothing was run." in again
    assert len(reads(root)) == 2 and not out.exists() and not (root / "_jobs").exists() and not (root / NAME / "test.json").exists()
    assert status.split("\n")[0] == f"Blueprint status · {NAME} · LEAD · phase 2 · round 1" and f"TEST DAYS READ · judged {reads(root)[-1]['utc']} · {r['verdict']}" in status
    assert all(status.count("  " + x["text"]) == 1 for x in r["lines"]) and "EARLY LOOK (no verdict of the law" in status
    got = IS.read_idea(NAME, root)                                                # the app's own copies: a lead as before -- and it says an early look is on file
    assert (got["status"], got["phase"], IS.status(NAME, root), got.get("early_look")) == ("lead", 2, "lead", True) and [x["line"][:2] for x in got["lines"]] == ["2."] * 9
    assert (drafts / f"{NAME}.py").read_text(encoding="utf-8").splitlines()[1].startswith(f"# {NAME} · LEAD · phase 2 · round 1")
    # ---- a finished early look as the tool words it: its lines once each, labelled; never a phase that was passed
    head = worded.split("\n")
    assert head[0] == f"Blueprint test · {NAME} · LEAD · phase 4 · round 1" and head[1].startswith(f"{EARLY}. NOT the law's test")
    assert all(worded.count(f"\n4.{i} PASS ") == 1 for i in range(1, 10)) and worded.count(f"[{EARLY}]") == 9 and worded.count("Next: ") == 1
    assert f"Next: {EARLY}: " in worded and "PROVEN ON HISTORY" not in worded and "early_look/test.json" in worded


# ================================================================ nothing outside the temp folder

def test_nothing_was_written_outside_the_temp_folder():
    F.clean()
    assert not OOS.EARLY_OUT.exists() or not [k for k in F._listing(OOS.EARLY_OUT) if k.startswith("bpl_")], "a test wrote into runs_bp_early/"
    assert not [k for k in (F._listing(RUN.TESTS) or []) if k.startswith("bpl_")], "a test wrote into runs_bp_test/"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            ok, n, note = RESULTS.get(name, ("", "", ""))
            print(f"PASS {name}" + (f": {ok} of {n}" if n else "") + (f" -- {note}" if note else "") + f" ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
        except BaseException as e:                          # pytest.skip
            if type(e).__name__ != "Skipped":
                raise
            print(f"SKIP {name} ({e})", flush=True)
        finally:
            teardown_function()
    for what, text in ((k, v) for k, v in _T.items() if isinstance(v, str)):
        print(f"\n--- {what} ---\n{text}", flush=True)
    sys.exit(rc)
