"""LOCK of THE WHOLE PIPELINE, END TO END (pipeline plan A, task 9): cards in through the public entry points -- `bp.py pipe
add` (cli.main) and pipe_runner.add -- and the runner itself (pipe_runner.loop, once) taking them through every stage that
is theirs, on TINY REAL runs. No stage is called by hand, no stage card is written by a test.

1. THE WHOLE WAY. One card with ONE way (orb on NQ in the New York morning: a 1-minute and a 5-minute heat map), a strict
   pass: stage 0 the card, 1 the two raw heat maps, 2 the machine check (the code check's lines and the prices of the
   middle box against the 1-minute bars: real), 3 skipped after the other markets, 4 the reshuffled runs and the random heat
   maps, 5 the code check, the one build round and the lock (real), 6 THE ONE READ OF THE UNSEEN DAYS -- real, on the two
   named test days of TEST_DAYS, through the toolkit's own test switch into <root>/runs_test -- and 7 the book card off
   those test trades. The idea ends "awaiting_owner" at stage 7 with the stage cards 0..7 on disk; the owner's approve puts
   its book card in <root>/book, and `pipe list` / `pipe book` print it.
2. THE OTHER WAY OUT. A card whose raw heat maps fail stops at stage 1 with its why, and the runner ends; a card that
   moves on with a LOW pass and its indicator (stage 3 for real: the heat map `<sub>f1`, three tries) and whose random heat
   maps fail stops at stage 4 -- and THE SAME CARD under another name is refused by the registry.
3. NOTHING OUTSIDE THE TEMP ROOT: the repo's runs_bp/, runs_bp_test/ and ledger.csv, and ~/.homebase, are listed (names and
   times) before the first run and after the last. Other chats write there too, so what fails the test is an entry that
   carries one of THIS file's idea names; the default pipeline root (~/.homebase/pipeline) is not made, no store of the
   pipeline's is a link into the repo, and no store of the build days holds a day from 2025-07-01 on.

WHAT IS PATCHED, and nothing else (two or three days prove no edge; the numbers of the gates and the lines are locked by
their own test files). Every helper is test_pipe_stages' or test_pipe_finish's own, used as their tiny real tests use it:
  the gates of stages 1-4     pipe_gates.raw (answers by bar size: test_pipe_stages.raw), strict_extra, reshuffle, random
                              (their own rows forced: test_pipe_stages.gate)
  line 1.5 of the code check  checks.chart says what `looked` says (test_pipe_finish.chart): 10 trades cannot be looked at
  the build's lines 2.1-2.9   records.LINES forced to pass (test_blueprint_ideas.passing)
  the box's lines 3.3-3.8     `box: "said"` in the tiny run's settings (read, not enforced: the toolkit's own test switch)
  THE READ'S LINES 4.1-4.9    oos.LINES, each line's own row forced to PASS (proven(), below: the one patch that is this
                              file's). The read itself is REAL: its claim in the one-read log before the pass, its three
                              stores (the locked boxes, the same with worse fills, its own 10-seed random pool) on the two
                              named days, test.json, the prop check and the book card off its trades.
EVERYTHING IS IN TEMP FOLDERS of this file's own: the pipeline root, the pools folder pipe_store links from (empty: a tiny
run can never reach a real control pool), the Lab drafts (test_blueprint_ideas' environment). HOMEBASE_PIPELINE_ROOT names
a folder that must never appear: every call names its root. The clock stands on a Saturday; workers 1; three build days,
two exit cells, two test days. Each run is made ONCE (the whole way: whole(); the two that stop: stopped()) and the tests
read what it left and what it answered at the time, so they hold in any order. NO ENGINE CALL AT IMPORT: the runs are
reached from test functions only.

  pytest tests/test_pipe_end_to_end.py -q      (about 10 seconds)     python tests/test_pipe_end_to_end.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge  # noqa: E402,F401  (it puts the engine on the path: l2sim is found after it)
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
import test_pipe_finish as TF  # noqa: E402
import test_pipe_stages as TS  # noqa: E402
from blueprint import oos as OOS  # noqa: E402
from blueprint import pipe_card as PC  # noqa: E402
from blueprint import pipe_prop as PP  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import pipe_runner as RN  # noqa: E402
from blueprint import pipe_stages as ST  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="pipe_e2e_")}
D = Path(_T["keep"].name).resolve()
ROOT, POOLS, STRAY = D / "pipe", D / "pools", D / "stray"      # STRAY: what HOMEBASE_PIPELINE_ROOT names here -- a call without its root would make it
HOME, DEFAULT = Path.home() / ".homebase", Path.home() / ".homebase" / "pipeline"
TEST_DAYS = ["2025-08-20", "2026-03-18"]            # one unseen day of each part of the test range (Jul-Dec 2025, Jan-Sep 2026)
TINY = {**TF.SAID["tiny"], "test_days": TEST_DAYS}  # 3 build days, 2 exit cells, 1 worker, 200 draws, the box's lines read and not enforced + the read's days
CTX = {"root": ROOT, "tiny": TINY}
A, B, C, TWIN = "e2e_orb", "e2e_orb_one", "e2e_orb_four", "e2e_orb_twin"       # the whole way · stops at stage 1 · stops at stage 4 · C again under another name
MINE = "e2e_orb"                                    # every idea of this file (and each of its heat maps and stores) starts with it
SUB, HOME5 = f"{A}_a5", f"{A}_a5-NQ-tf5"            # the heat map of A that moves on, and its home store
MAX_TR = {A: 2, B: 1, C: 3}                         # the most entries a session: what makes them three cards (three signatures)
BOOK = ("name", "label", "prop", "hours", "win_days_month", "winning_months", "biggest_day_share", "fast_profit_share", "worst_day", "worst_drawdown", "rule", "stages")
OWN, ACCOUNTS = PR.need("prop", "account"), PR.need("prop", "book_accounts")
PLACES = (RUN.RUNS, RUN.TESTS, HOME)                # the folders nothing of this file may be written to (+ the repo's ledger.csv)
R_ = f"--root={ROOT}"
_DONE: dict = {}


def card(name: str) -> dict:
    """The orb card of test_pipe_stages under another name, with its most entries a session stated."""
    return {**copy.deepcopy(TS.CARD), "name": name, "ways": [{**TS.CARD["ways"][0], "limits": {"max_tr": MAX_TR[name]}}]}


def listed(d: Path, deep: int) -> dict:
    """{path under d: its time} of what stands in a folder, `deep` levels down (a folder's own time moves when a name in it
    comes or goes). What is gone between the look and the read is not there."""
    out, todo = {}, [(d, 0)]
    while todo:
        at, n = todo.pop()
        try:
            for p in at.iterdir():
                out[str(p.relative_to(d))] = p.lstat().st_mtime_ns
                if n + 1 < deep and p.is_dir() and not p.is_symlink():
                    todo.append((p, n + 1))
        except OSError:
            continue
    return out


def snapshot() -> dict:
    """Names and times: the repo's two stores folders (each store and its files), the repo's ledger, all of ~/.homebase."""
    led = LB.LEDGER.stat() if LB.LEDGER.exists() else None
    return {"folders": {str(d): listed(d, 8 if d == HOME else 2) for d in PLACES}, "ledger": None if led is None else (led.st_mtime_ns, led.st_size),
            "default": DEFAULT.exists()}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    """Temp folders for all the toolkit writes, an empty pools folder to link from, a Saturday, the workers asked for -- and
    the look at the places outside before this file's first run."""
    TI.setup_function()
    POOLS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PS, "pools", lambda: POOLS)
    monkeypatch.setattr(RUN, "clock", lambda: TI.SAT)
    monkeypatch.setattr(RM, "auto_workers", lambda n=None: n)
    monkeypatch.setattr(PR, "mode", lambda: "map")          # these tests lock the legacy whole-map behaviour (tests/test_pipe_variant.py locks variant mode)
    monkeypatch.setenv(PS.ENV, str(STRAY))
    if "before" not in _T:
        _T["before"] = snapshot()
    yield monkeypatch
    TI.teardown_function()


# ---------------------------------------------------------------- the patches (module docstring), and the runs: once each

def gates(mp, b5: str, fail=()) -> None:
    """The gates of stages 1-4 answer for a tiny run: the 5-minute heat map `b5` (the 1-minute one fails), every other gate
    its own rows forced to pass but the lines of `fail`. Line 1.5 says what `looked` says."""
    TS.raw(mp, b1=("fail", None), b5=(b5, 40.0 if b5 != "fail" else 12.0))
    for name in ("strict_extra", "indicator", "reshuffle", "random"):
        TS.gate(mp, name, fail)
    TF.chart(mp)


def proven(mp) -> None:
    """THE READ'S LINES 4.1-4.9 say PASS, each on its own row with its own number (two days prove nothing): oos.LINES, as
    test_blueprint_ideas.passing() does the build's. The read behind them is real."""
    mp.setattr(OOS, "LINES", tuple((lambda t, f=f: {**f(t), "passed": True}) for f in OOS.LINES))


def cli(argv: list, stdin: str = "") -> tuple:
    """`bp.py <argv> --root=<the temp pipeline root> --json` in this process -> (exit code, the one object)."""
    rc, out = TI._run([*argv, R_, "--json"], stdin)
    return rc, json.loads(out)


def once(what: str, name: str) -> bool:
    """Is the run `what` still to make? A run that broke in an earlier test is not made a second time: it fails here, by name."""
    if what in _DONE:
        return False
    assert not (ROOT / "p" / name).exists(), f"the run of {name} broke in an earlier test of this file: see that one"
    return True


def whole(mp) -> dict:
    """THE WHOLE WAY, once: card A in through `bp.py pipe add`, then the runner (once) -> what the two calls answered, and how
    the idea stood when the runner ended (a later test approves it)."""
    if once("whole", A):
        if not hasattr(S, "ALLOW_BT") or not all(S.tape_path(d, "NQ").exists() for d in TEST_DAYS):
            pytest.skip("the read of the unseen days needs the engine's test switch and the NQ tapes of " + ", ".join(TEST_DAYS))
        rc, added = cli(["pipe", "add", "--spec=-"], json.dumps(card(A)))
        assert rc == 0 and added["ok"] is True, added
        gates(mp, "strict")
        proven(mp)
        with TI.passing():
            done = RN.loop(CTX, once=True)
        _DONE["whole"] = {"added": added, "loop": done, "order": PS.order(ROOT), "env": TF.env(), "state": PS.state(A, ROOT), "show": cli(["pipe", "show", A]),
                          "book": (ROOT / "book").exists()}
    return _DONE["whole"]


def stopped(mp) -> dict:
    """THE OTHER WAY OUT, once: card B (its raw heat maps fail) and then card C (a low pass, its indicator, then its random
    heat maps fail), each in through pipe_runner.add and worked by a runner of its own -> the two runners' answers and the
    queue after each."""
    if once("stopped", B):
        got = {}
        for name, b5, fail in ((B, "fail", ()), (C, "low", ("P4.2",))):
            with mp.context() as m:                 # (each card its own gates: taken away again before the next one runs)
                r = RN.add(card(name), ROOT)
                assert r["ok"] is True and r["status"] == "queued", r
                gates(m, b5, fail)
                got[name] = {"loop": RN.loop(CTX, once=True), "order": PS.order(ROOT)}
        _DONE["stopped"] = got
    return _DONE["stopped"]


def meta(folder: str) -> dict:
    """{store: its run.json} of a stores folder of the pipeline root."""
    return {p.parent.name: TI.read(p) for p in sorted((ROOT / folder).glob("*/run.json"))}


# ================================================================ 1. the whole way

def test_one_card_goes_the_whole_way_and_waits_for_the_owner(world):
    got = whole(world)
    added = got["added"]
    assert (added["command"], added["name"], added["status"], added["subs"]) == ("pipe add", A, "queued", [f"{A}_a1", SUB]) and "place 1 of 1" in added["text"]
    assert [x["line"] for x in added["lines"]] == ["P0.1", "P0.2", "P0.3", "P0.4"] and added["saved"] == [str(ROOT / "p" / A)]
    assert got["loop"] == 0 and got["order"] == []                                             # the runner worked the queue empty, and ended
    st = got["state"]
    assert (st["status"], st["stage"], st["stopped_at"], st["why"], st["tries"]) == ("awaiting_owner", 7, None, "", 2), st
    assert st["picked"] == {"sub": SUB, "bar": "5", "way": 0, "filter": None} and (st["family"], st["source"]) == ("orb", "owner")
    cards = PS.stages(A, ROOT)
    assert list(cards) == list(range(8)) == sorted(int(p.stem) for p in (ROOT / "p" / A / "stages").glob("*.json"))
    for n, c in cards.items():                                                                 # every card has every key of the plan's shape
        TS.whole(c, n)
        assert "code_problem" not in c and "refused" not in c and "trace" not in c, (n, c["text"])
    assert [c["passed"] for c in cards.values()] == [True] * 7 + [None]
    assert [c["result"] for c in cards.values()] == ["pass", "strict", "pass", "skipped", "pass", "locked", "proven on history", "awaiting owner"]
    assert [c["tries"] for c in cards.values()] == [0] + [2] * 7 and all(c["picked"] == st["picked"] for n, c in cards.items() if n)
    assert [x["line"] for x in cards[2]["lines"]] == ["1.1", "1.2", "1.3", "1.4", "P2.5"] and all(x["passed"] is True for x in cards[2]["lines"])     # the machine check: real
    assert cards[2]["lines"][4]["trades"] >= 1 and cards[2]["lines"][4]["off"] == 0
    assert [x["line"] for x in cards[4]["lines"]] == ["P4.1", "P4.2"] and cards[4]["rules"]["random_bar"] == PR.random_bar(2)
    assert [x["line"] for x in cards[5]["lines"]] == [*TF.BOXL, "P5.9"] and cards[5]["locked"]["default"] in cards[5]["text"]
    log = [x.split("\t") for x in (ROOT / RN.LOG).read_text().splitlines()]                    # one line a finished stage, in their order
    assert [(x[2], x[3]) for x in log if x[1] == A] == [(str(n), "PASS") for n in range(8)]
    assert got["env"] == {"switch": None, "drafts": TI.ENV[TF.DRAFTS]}                         # the environment is as it was
    rc, r = got["show"]
    assert rc == 0 and r["status"] == "awaiting_owner" and list(r["stages"]) == [str(n) for n in range(8)] and f"bp.py pipe approve {A}" in r["next"]
    assert got["book"] is False                                                                # nothing is in the book before the owner says so


def test_the_unseen_days_were_read_once_for_real_on_the_named_days(world):
    whole(world)
    six, five, d = PS.stages(A, ROOT)[6], PS.stages(A, ROOT)[5], ROOT / "ideas" / SUB
    lock, test = TI.read(d / "lock.json"), TI.read(d / "test.json")
    end = lock["test_range"]["NQ"]["end"]
    assert [x["line"] for x in six["lines"]] == [f"4.{i}" for i in range(1, 10)] and all(x["passed"] is True for x in six["lines"])
    assert six["rules"]["range"] == {"start": R.template("ranges")["test"]["start"], "end": end} == test["range"] and "PROVEN ON HISTORY" in six["text"]
    assert (test["lock"], test["passed"], test["test_run"], test["dry_run"]) == (lock["hash"], True, True, False) and lock["hash"] == five["locked"]["lock"]
    assert test["days"]["named"] == TEST_DAYS and test["days"]["sessions"] == 2 and [p["sessions"] for p in test["days"]["parts"]] == [1, 1]
    # THE ONE READ: claimed in the pipeline's own log before the pass, then judged -- and a second one is the toolkit's refusal
    reads = [json.loads(x) for x in (ROOT / "ideas" / "test_reads.jsonl").read_text().splitlines()]
    assert [(x["name"], x["state"], x["lock"]) for x in reads] == [(SUB, "claimed", lock["hash"]), (SUB, "judged", lock["hash"])]
    with ST._switch(A, CTX), TI.no_engine():
        TS.refused(lambda: OOS.test(SUB, confirm=True, root=ROOT / "ideas", out=ROOT / "runs_test", ledger=PS.ledger(A, ROOT), days=TEST_DAYS), "already on file")
    # its three stores: in the pipeline's own runs_test, of the frozen test range, of this lock's read, of the two named days
    K = RUN.test_keys(HOME5, SUB, "NQ", "5", "nyam")
    stores = meta("runs_test")
    assert set(stores) == set(K.values()) and {s["key"] for s in test["stores"]} == set(K.values())
    for m in stores.values():
        assert (m["period"], m["calendar"], m["days"], m["sessions"]) == (S.ALLOW_BT, TEST_DAYS, TEST_DAYS, ["nyam"]) and m["read"]["lock"] == lock["hash"]
        assert m["range"]["start"] == "2025-07-01" and m["range"]["end"] == end
    # ... and NO store of the build days holds a day past them: only the read's stores do
    build = meta("runs")
    assert {HOME5, f"{A}_a1-NQ-tf1", f"{HOME5}-nyam-worse", "c1-NQ-tf5", f"{SUB}-ES-tf5", f"{SUB}-GC-tf5"} <= set(build)
    assert all(m["days"] == TI.DAYS and max(m["days"]) <= R.template("ranges")["build"]["end"] for m in build.values()), {k: m["days"] for k, m in build.items()}
    # the label and the three accounts: off the default box's TEST trades (stage 6), and the idea's own ledger holds the read's rows
    assert list(six["prop"]) == ACCOUNTS and six["label"] == six["prop"][OWN]["label"] and six["label"] in (PP.ALONE, PP.HELPER)
    rows = LB.read_ledger(ROOT / "p" / A / "ledger.csv")
    assert {(x["key"], x["period"]) for x in rows if x["period"] == S.ALLOW_BT} == {(k, S.ALLOW_BT) for k in K.values()}


def test_the_book_card_holds_what_the_design_asks_and_the_owner_approves_it(world):
    whole(world)
    seven, six, five = (PS.stages(A, ROOT)[n] for n in (7, 6, 5))
    b = seven["book"]
    assert set(BOOK) <= set(b) and seven["lines"] == [] and f"bp.py pipe approve {A}" in seven["text"]
    assert (b["name"], b["sub"], b["family"], b["market"], b["session"], b["bar"], b["filter"], b["tries"]) == (A, SUB, "orb", "NQ", "nyam", "5", None, 2)
    assert b["label"] == six["label"] and list(b["prop"]) == ACCOUNTS and all(tuple(p) == ST.BOOK_PROP for p in b["prop"].values())      # the three accounts
    assert [b["prop"][a]["confirmed"] for a in ACCOUNTS] == [True, True, False] and all(0.0 <= p["eval"] <= 1.0 and 0.0 <= p["payout"] <= 1.0 for p in b["prop"].values())
    lock = TI.read(ROOT / "ideas" / SUB / "lock.json")
    assert b["rule"] == {"spec": lock["spec"], "default": five["locked"]["default"], "lock": lock["hash"]} and b["rule"]["spec"]["run"]["limits"] == {"max_tr": 2}
    # the money facts are the default box's trades of the two unseen days (counts and shapes: no P&L of a test day is asserted)
    st = LB.load_unit(RUN.test_keys(HOME5, SUB, "NQ", "5", "nyam")["table"], ROOT / "runs_test")
    x = LB.unit_cell(st, b["rule"]["default"])
    assert b["trades"] == len(x["net"]) >= 1 and 1 <= b["days_traded"] <= 2 and b["net"] == pytest.approx(float(x["net"].sum()))
    assert len(b["hours"]) == 2 and "09:30" <= b["hours"][0] <= b["hours"][1] <= "11:00"       # the New York morning
    assert b["winning_months"][1] == b["days_traded"] and 0 <= b["winning_months"][0] <= 2     # two days in two months
    assert isinstance(b["worst_day"], float) and b["worst_drawdown"] >= 0.0 and (b["win_days_month"] is None or b["win_days_month"] >= 0.0)
    assert all((b[k] is None) == (b["net"] <= 0) for k in ("biggest_day_share", "fast_profit_share"))      # a share of the profit: only when there is one
    assert list(b["stages"]) == [str(n) for n in range(7)] and all(set(v) == {"passed", "result", "text"} and v["passed"] is True for v in b["stages"].values())
    json.dumps(b)                                                                              # plain numbers: a book card is a JSON file
    # THE OWNER'S YES: the book card of stage 7 is the book's, and the two commands print it
    assert RN.approve(A, ROOT)["status"] == "book" and PS.state(A, ROOT)["stage"] == 7
    assert TI.read(ROOT / "book" / f"{A}.json") == b and PS.book(ROOT) == [b] and [p.name for p in (ROOT / "book").iterdir()] == [f"{A}.json"]
    TS.refused(lambda: RN.approve(A, ROOT), "only an idea that passed every stage and waits for the owner")      # once
    rc, out = TI._run(["pipe", "list", R_])
    row = next(x.split() for x in out.splitlines() if x.startswith(f"{A} "))
    assert rc == 0 and row[:5] == [A, "orb", "book", "7", "2"] and "1 book" in out
    rc, out = TI._run(["pipe", "book", R_])
    assert rc == 0 and out.splitlines()[0].split() == ["name", "label", "family", "market", "session", "bar"]
    assert [x.split("  ")[0] for x in out.splitlines()[1:2]] == [A] and b["label"] in out.splitlines()[1] and out.splitlines()[1].split()[-4:] == ["orb", "NQ", "nyam", "5"]
    assert out.splitlines()[2:] == ["", "luck count: 1 idea read on the unseen days, 1 passed; luck alone gives at most 0.05 (bp.py pipe luck)"]      # the Book's last line
    rc, r = cli(["pipe", "book"])
    assert rc == 0 and r["book"] == [b]


# ================================================================ 2. the other way out

def test_a_card_whose_raw_heat_maps_fail_stops_at_stage_1_and_the_runner_ends(world):
    got = stopped(world)[B]
    assert got["loop"] == 0 and got["order"] == []                                             # the runner ended, with nothing left to work on
    st = PS.state(B, ROOT)
    assert (st["status"], st["stage"], st["stopped_at"], st["tries"], st["picked"]) == ("stopped", 1, 1, 2, None)
    cards = PS.stages(B, ROOT)
    assert list(cards) == [0, 1] and (cards[1]["passed"], cards[1]["result"]) == (False, "fail") and "code_problem" not in TS.whole(cards[1], 1)
    assert st["why"] and st["why"] == next(x["text"] for x in cards[1]["lines"] if x["passed"] is False) and st["why"].startswith(f"{B}_a1: P1.")
    assert "every one of the 2 raw heat maps failed" in cards[1]["text"]
    assert sorted(k for k in meta("runs") if k.startswith(B)) == [f"{B}_a1-NQ-tf1", f"{B}_a5-NQ-tf5"]     # its two home stores, and nothing after them
    assert not (ROOT / "ideas" / f"{B}_a5" / "check.json").exists()


def test_a_card_whose_random_heat_maps_fail_stops_at_stage_4_and_the_same_card_is_refused_under_another_name(world):
    got = stopped(world)[C]
    assert got["loop"] == 0 and got["order"] == []
    st = PS.state(C, ROOT)
    f1 = f"{C}_a5f1"                                                                           # its 5-minute heat map with the card's one indicator on
    assert (st["status"], st["stage"], st["stopped_at"], st["tries"]) == ("stopped", 4, 4, 3) and st["picked"] == {"sub": f1, "bar": "5", "way": 0, "filter": "trend_with"}
    cards = PS.stages(C, ROOT)
    assert list(cards) == [0, 1, 2, 3, 4] and [c["passed"] for c in cards.values()] == [True] * 4 + [False] and "code_problem" not in TS.whole(cards[4], 4)
    assert [c["result"] for c in cards.values()] == ["pass", "low", "pass", "pass", "fail"] and [c["tries"] for c in cards.values()] == [0, 2, 2, 3, 3]
    assert [x["line"] for x in cards[3]["lines"]] == [f"P3.{i}" for i in range(1, 7)] and cards[3]["indicators"][0]["sub"] == f1      # stage 3: the indicator, alone
    assert {f"{f1}-NQ-tf5", f"{f1}__trend_with-NQ-tf5", f"{C}_a5-ES-tf5", f"{C}_a5-GC-tf5"} <= set(meta("runs"))
    assert [(x["line"], x["passed"]) for x in cards[4]["lines"]] == [("P4.1", True), ("P4.2", False)] and st["why"] == cards[4]["lines"][1]["text"]
    assert cards[4]["text"].startswith("the proof fails: P4.2") and cards[4]["lines"][1]["tries"] == 3 and cards[4]["lines"][1]["need"] == PR.random_bar(3)
    d = ROOT / "ideas" / f"{C}_a5"
    assert (d / "check.json").exists() and not [x for x in (d, ROOT / "ideas" / f1) for k in ("rounds", "lock.json", "test.json") if (x / k).exists()]      # the machine check ran; no build, no lock, no read
    assert not [k for k in meta("runs_test") if k.startswith(C)]                               # (and no store of the unseen days is its)
    # THE SAME CARD under another name: the registry knows its signature, whatever became of the first
    twin = {**card(C), "name": TWIN, "why": "A range that breaks after the open runs, and the traders who leaned on it are the ones who pay for it.", "indicators": []}
    assert PC.signature(twin) == PC.signature(card(C)) != PC.signature(card(B))
    rc, r = cli(["pipe", "add", "--spec=-"], json.dumps(twin))
    assert rc == 2 and r["ok"] is False and f"{TWIN!r} is the same card as {C!r}" in r["error"] and "a card is run once" in r["error"]
    TS.refused(lambda: RN.add(twin, ROOT), "is the same card as")
    assert not (ROOT / "p" / TWIN).exists() and TWIN not in (ROOT / PS.SEEN).read_text() and PS.order(ROOT) == []
    rc, out = TI._run(["pipe", "list", R_])
    rows = {x.split()[0]: x.split() for x in out.splitlines() if x.startswith(MINE)}
    assert rc == 0 and rows[B][2:5] == ["stopped", "1", "2"] and rows[C][2:5] == ["stopped", "4", "3"] and TWIN not in rows and "2 stopped" in out


# ================================================================ 3. nothing outside the temp root

def test_nothing_was_written_outside_the_temp_root(world):
    whole(world)
    stopped(world)
    before, after = _T["before"], snapshot()
    # (a) directly: nothing of these ideas in the repo's stores, ledger or the Lab; no pipeline root but the one every call named
    for name in (A, B, C, TWIN):
        TF.no_repo_write(name)
    assert after["default"] == before["default"] and (before["default"] or not DEFAULT.exists()), f"{DEFAULT} was made by a test"
    assert not STRAY.exists(), "a call went without its root: HOMEBASE_PIPELINE_ROOT was read"
    assert not list(POOLS.iterdir()) and not [p.name for d in ("runs", "runs_test") for p in (ROOT / d).iterdir() if p.is_symlink()]      # no way into a real pool
    names = {p.name for p in ROOT.iterdir() if not p.name.startswith("runner.")}               # the pipeline root holds what the store's layout says, and no more
    assert {"ideas", "order.jsonl", "p", "runs", "runs_test", "seen.jsonl"} <= names <= {"book", "ideas", "order.jsonl", "p", "runs", "runs_test", "seen.jsonl"}
    # (b) the look before and after. Other chats write to these places too: what fails is a changed entry that carries a name of THIS file
    for place, was in before["folders"].items():
        now = after["folders"][place]
        changed = sorted(k for k in set(was) | set(now) if was.get(k) != now.get(k))
        assert not [k for k in changed if MINE in k], f"{place}: written by this test -- {[k for k in changed if MINE in k]}"
    if after["ledger"] != before["ledger"]:                                                    # the repo's ledger moved: not by a row of ours
        assert not [x["key"] for x in LB.read_ledger() if MINE in x["key"]]
    assert MINE not in " ".join(k for d in after["folders"].values() for k in d)               # ... and no entry there carries one at all


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-W", "ignore"]))
